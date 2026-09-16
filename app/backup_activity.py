from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from . import db
from .bounded_files import read_bounded_regular_file


BACKUP_ACTIVITY_FILENAME = "database-backup-activity.json"
BACKUP_HANDOFF_FILENAME = "database-backup-handoff.json"
DELIVERY_ACTIVITY_FILENAME = "database-delivery-activity.json"
BACKUP_ACTIVITY_SCHEMA_VERSION = 2
BACKUP_HANDOFF_SCHEMA_VERSION = 1
DELIVERY_ACTIVITY_SCHEMA_VERSION = 2
DEFAULT_STATE_DIR = Path(
    os.getenv(
        "EXTRUSION_ARTIFACT_STATE_DIR",
        db.BASE_DIR / "artifact-delivery" / "state",
    )
)
_MAX_ACTIVITY_BYTES = 16 * 1024
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_OBSERVATION_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_ITEM_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_MAX_UNREMOVED_CONFIRMATIONS = 256
_BACKUP_FILENAME_PATTERN = re.compile(
    r"extrusion_terminal_[0-9]{8}_[0-9]{6}_[0-9]{6}(?:_[0-9]+)?\.sqlite3"
)
_UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_ACTIVITY_KEYS_V1 = frozenset(
    {
        "schema_version",
        "status",
        "last_attempt_at_utc",
        "last_successful_check_at_utc",
        "last_change_at_utc",
        "last_validated_sha256",
        "successful_checks_total",
        "failed_checks_total",
        "changed_versions_total",
    }
)
_ACTIVITY_KEYS = _ACTIVITY_KEYS_V1 | {"last_observation_id"}
_HANDOFF_KEYS = frozenset(
    {
        "schema_version",
        "observation_id",
        "started_at_utc",
        "backup_filename",
        "remote_basename",
        "queue_item_id",
        "validated_sha256",
        "database_changed",
    }
)
_DELIVERY_ACTIVITY_KEYS_V1 = frozenset(
    {
        "schema_version",
        "status",
        "last_attempt_at_utc",
        "last_successful_run_at_utc",
        "last_confirmed_upload_at_utc",
        "last_confirmed_backup_queued_at_utc",
        "confirmed_uploads_total",
        "failed_runs_total",
        "active_incident_upload_count",
    }
)
_DELIVERY_ACTIVITY_KEYS = _DELIVERY_ACTIVITY_KEYS_V1 | {
    "unremoved_confirmed_item_ids"
}


@dataclass(frozen=True)
class BackupActivity:
    status: Literal["never", "healthy", "failing"]
    last_attempt_at_utc: str | None
    last_successful_check_at_utc: str | None
    last_change_at_utc: str | None
    last_validated_sha256: str | None
    last_observation_id: str | None
    successful_checks_total: int
    failed_checks_total: int
    changed_versions_total: int


@dataclass(frozen=True)
class BackupHandoff:
    observation_id: str
    started_at_utc: str
    backup_filename: str
    remote_basename: str
    queue_item_id: str
    validated_sha256: str | None
    database_changed: bool | None


@dataclass(frozen=True)
class DeliveryActivity:
    status: Literal["never", "healthy", "failing"]
    last_attempt_at_utc: str | None
    last_successful_run_at_utc: str | None
    last_confirmed_upload_at_utc: str | None
    last_confirmed_backup_queued_at_utc: str | None
    confirmed_uploads_total: int
    failed_runs_total: int
    active_incident_upload_count: int
    unremoved_confirmed_item_ids: tuple[str, ...]


@dataclass(frozen=True)
class DeliveryRunTransition:
    activity: DeliveryActivity
    recovered: bool
    recovered_upload_count: int


@dataclass(frozen=True)
class DeliveryConfirmationCheckpoint:
    activity: DeliveryActivity
    effective_confirmed_uploads: int


def load_backup_activity(
    state_dir: Path | str | None = None,
) -> BackupActivity:
    state_path = _activity_path(state_dir)
    state = _load_json_state(state_path, "Backup activity state", missing=None)
    if state is None:
        return _empty_activity()
    schema_version = state.get("schema_version")
    if type(schema_version) is not int or schema_version not in {1, 2}:
        raise ValueError(f"Backup activity state version is unsupported: {state_path}")
    expected_keys = _ACTIVITY_KEYS_V1 if schema_version == 1 else _ACTIVITY_KEYS
    if set(state) != expected_keys:
        raise ValueError(f"Backup activity state schema is invalid: {state_path}")
    if state["status"] not in {"healthy", "failing"}:
        raise ValueError(f"Backup activity status is invalid: {state_path}")
    for key in (
        "last_attempt_at_utc",
        "last_successful_check_at_utc",
        "last_change_at_utc",
    ):
        _validate_optional_utc_timestamp(state[key], state_path)
    digest = state["last_validated_sha256"]
    if digest is not None and (
        not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None
    ):
        raise ValueError(f"Backup activity SHA-256 is invalid: {state_path}")
    observation_id = state.get("last_observation_id")
    if observation_id is not None and (
        not isinstance(observation_id, str)
        or _OBSERVATION_ID_PATTERN.fullmatch(observation_id) is None
    ):
        raise ValueError(f"Backup activity observation ID is invalid: {state_path}")
    for key in (
        "successful_checks_total",
        "failed_checks_total",
        "changed_versions_total",
    ):
        if type(state[key]) is not int or state[key] < 0:
            raise ValueError(f"Backup activity counter is invalid: {state_path}")
    if state["changed_versions_total"] > state["successful_checks_total"]:
        raise ValueError(f"Backup activity counters are inconsistent: {state_path}")
    if state["last_attempt_at_utc"] is None:
        raise ValueError(f"Backup activity attempt time is invalid: {state_path}")
    if state["status"] == "healthy" and (
        state["last_successful_check_at_utc"] is None or digest is None
    ):
        raise ValueError(f"Healthy backup activity is incomplete: {state_path}")
    return BackupActivity(
        status=state["status"],
        last_attempt_at_utc=state["last_attempt_at_utc"],
        last_successful_check_at_utc=state["last_successful_check_at_utc"],
        last_change_at_utc=state["last_change_at_utc"],
        last_validated_sha256=digest,
        last_observation_id=observation_id,
        successful_checks_total=state["successful_checks_total"],
        failed_checks_total=state["failed_checks_total"],
        changed_versions_total=state["changed_versions_total"],
    )


def record_backup_success(
    digest: str,
    *,
    changed: bool,
    state_dir: Path | str | None = None,
    now: datetime | None = None,
    observation_id: str | None = None,
) -> BackupActivity:
    if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError("Backup activity requires a complete lowercase SHA-256 digest.")
    if type(changed) is not bool:
        raise ValueError("Backup activity changed flag must be boolean.")
    if observation_id is not None and (
        not isinstance(observation_id, str)
        or _OBSERVATION_ID_PATTERN.fullmatch(observation_id) is None
    ):
        raise ValueError("Backup activity observation ID is invalid.")
    previous = load_backup_activity(state_dir)
    if observation_id is not None and previous.last_observation_id == observation_id:
        if previous.last_validated_sha256 != digest:
            raise ValueError("Backup observation digest conflicts with activity state.")
        timestamp = _format_utc_timestamp(now)
        replayed = replace(
            previous,
            status="healthy",
            last_attempt_at_utc=timestamp,
            last_successful_check_at_utc=timestamp,
        )
        _write_activity(_activity_path(state_dir), replayed)
        return replayed
    timestamp = _format_utc_timestamp(now)
    activity = BackupActivity(
        status="healthy",
        last_attempt_at_utc=timestamp,
        last_successful_check_at_utc=timestamp,
        last_change_at_utc=timestamp if changed else previous.last_change_at_utc,
        last_validated_sha256=digest,
        last_observation_id=observation_id,
        successful_checks_total=previous.successful_checks_total + 1,
        failed_checks_total=previous.failed_checks_total,
        changed_versions_total=previous.changed_versions_total + int(changed),
    )
    _write_activity(_activity_path(state_dir), activity)
    return activity


def record_backup_failure(
    *,
    state_dir: Path | str | None = None,
    now: datetime | None = None,
) -> BackupActivity:
    previous = load_backup_activity(state_dir)
    activity = BackupActivity(
        status="failing",
        last_attempt_at_utc=_format_utc_timestamp(now),
        last_successful_check_at_utc=previous.last_successful_check_at_utc,
        last_change_at_utc=previous.last_change_at_utc,
        last_validated_sha256=previous.last_validated_sha256,
        last_observation_id=previous.last_observation_id,
        successful_checks_total=previous.successful_checks_total,
        failed_checks_total=previous.failed_checks_total + 1,
        changed_versions_total=previous.changed_versions_total,
    )
    _write_activity(_activity_path(state_dir), activity)
    return activity


def load_backup_handoff(
    state_dir: Path | str | None = None,
) -> BackupHandoff | None:
    state_path = _handoff_path(state_dir)
    state = _load_json_state(state_path, "Backup handoff state", missing=None)
    if state is None:
        return None
    if set(state) != _HANDOFF_KEYS:
        raise ValueError(f"Backup handoff state schema is invalid: {state_path}")
    if (
        type(state["schema_version"]) is not int
        or state["schema_version"] != BACKUP_HANDOFF_SCHEMA_VERSION
    ):
        raise ValueError(f"Backup handoff state version is unsupported: {state_path}")
    observation_id = state["observation_id"]
    if not isinstance(observation_id, str) or (
        _OBSERVATION_ID_PATTERN.fullmatch(observation_id) is None
    ):
        raise ValueError(f"Backup handoff observation ID is invalid: {state_path}")
    started_at_utc = state["started_at_utc"]
    _validate_optional_utc_timestamp(started_at_utc, state_path)
    if started_at_utc is None:
        raise ValueError(f"Backup handoff timestamp is invalid: {state_path}")
    backup_filename = state["backup_filename"]
    if not isinstance(backup_filename, str) or (
        _BACKUP_FILENAME_PATTERN.fullmatch(backup_filename) is None
    ):
        raise ValueError(f"Backup handoff filename is invalid: {state_path}")
    remote_basename = state["remote_basename"]
    if not isinstance(remote_basename, str) or remote_basename != remote_backup_basename(
        _parse_utc(started_at_utc)
    ):
        raise ValueError(f"Backup handoff remote name is invalid: {state_path}")
    queue_item_id = state["queue_item_id"]
    queue_id_prefix = "database-backup-"
    if not isinstance(queue_item_id, str) or (
        not queue_item_id.startswith(queue_id_prefix)
        or _OBSERVATION_ID_PATTERN.fullmatch(queue_item_id[len(queue_id_prefix) :])
        is None
    ):
        raise ValueError(f"Backup handoff queue ID is invalid: {state_path}")
    digest = state["validated_sha256"]
    if digest is not None and (
        not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None
    ):
        raise ValueError(f"Backup handoff SHA-256 is invalid: {state_path}")
    changed = state["database_changed"]
    if (digest is None and changed is not None) or (
        digest is not None and type(changed) is not bool
    ):
        raise ValueError(f"Backup handoff validation state is invalid: {state_path}")
    return BackupHandoff(
        observation_id=observation_id,
        started_at_utc=started_at_utc,
        backup_filename=backup_filename,
        remote_basename=remote_basename,
        queue_item_id=queue_item_id,
        validated_sha256=digest,
        database_changed=changed,
    )


def begin_backup_handoff(
    backup_filename: str,
    *,
    state_dir: Path | str | None = None,
    now: datetime | None = None,
) -> BackupHandoff:
    if not isinstance(backup_filename, str) or (
        _BACKUP_FILENAME_PATTERN.fullmatch(backup_filename) is None
    ):
        raise ValueError("Backup handoff filename is invalid.")
    if load_backup_handoff(state_dir) is not None:
        raise ValueError("A backup handoff is already active.")
    timestamp = _format_utc_timestamp(now)
    handoff = BackupHandoff(
        observation_id=uuid4().hex,
        started_at_utc=timestamp,
        backup_filename=backup_filename,
        remote_basename=remote_backup_basename(_parse_utc(timestamp)),
        queue_item_id=f"database-backup-{uuid4().hex}",
        validated_sha256=None,
        database_changed=None,
    )
    _write_handoff(_handoff_path(state_dir), handoff)
    return handoff


def record_backup_handoff_validation(
    handoff: BackupHandoff,
    digest: str,
    *,
    changed: bool,
    state_dir: Path | str | None = None,
) -> BackupHandoff:
    if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError("Backup handoff SHA-256 is invalid.")
    if type(changed) is not bool:
        raise ValueError("Backup handoff changed flag must be boolean.")
    current = load_backup_handoff(state_dir)
    if current is None or current.observation_id != handoff.observation_id:
        raise ValueError("Backup handoff changed during validation.")
    if current.validated_sha256 is not None:
        if current.validated_sha256 != digest or current.database_changed != changed:
            raise ValueError("Backup handoff validation conflicts with existing state.")
        return current
    validated = replace(
        current,
        validated_sha256=digest,
        database_changed=changed,
    )
    _write_handoff(_handoff_path(state_dir), validated)
    return validated


def clear_backup_handoff(
    handoff: BackupHandoff,
    *,
    state_dir: Path | str | None = None,
) -> None:
    state_path = _handoff_path(state_dir)
    current = load_backup_handoff(state_dir)
    if current is None:
        return
    if current.observation_id != handoff.observation_id:
        raise ValueError("Backup handoff changed before completion.")
    state_path.unlink()
    _fsync_directory(state_path.parent)


def load_delivery_activity(
    state_dir: Path | str | None = None,
) -> DeliveryActivity:
    state_path = _delivery_activity_path(state_dir)
    state = _load_json_state(state_path, "Delivery activity state", missing=None)
    if state is None:
        return _empty_delivery_activity()
    schema_version = state.get("schema_version")
    if type(schema_version) is not int or schema_version not in {1, 2}:
        raise ValueError(f"Delivery activity state version is unsupported: {state_path}")
    expected_keys = (
        _DELIVERY_ACTIVITY_KEYS_V1 if schema_version == 1 else _DELIVERY_ACTIVITY_KEYS
    )
    if set(state) != expected_keys:
        raise ValueError(f"Delivery activity state schema is invalid: {state_path}")
    if state["status"] not in {"never", "healthy", "failing"}:
        raise ValueError(f"Delivery activity status is invalid: {state_path}")
    for key in (
        "last_attempt_at_utc",
        "last_successful_run_at_utc",
        "last_confirmed_upload_at_utc",
        "last_confirmed_backup_queued_at_utc",
    ):
        _validate_optional_utc_timestamp(state[key], state_path)
    if state["status"] != "never" and state["last_attempt_at_utc"] is None:
        raise ValueError(f"Delivery activity attempt time is invalid: {state_path}")
    for key in (
        "confirmed_uploads_total",
        "failed_runs_total",
        "active_incident_upload_count",
    ):
        if type(state[key]) is not int or state[key] < 0:
            raise ValueError(f"Delivery activity counter is invalid: {state_path}")
    if state["status"] == "never" and (
        state["last_attempt_at_utc"] is not None
        or state["last_successful_run_at_utc"] is not None
        or state["failed_runs_total"] != 0
        or state["active_incident_upload_count"] != 0
    ):
        raise ValueError(f"Never-run delivery activity is inconsistent: {state_path}")
    if (
        state["status"] == "healthy"
        and state["active_incident_upload_count"] != 0
    ):
        raise ValueError(
            f"Delivery activity incident count is inconsistent: {state_path}"
        )
    unremoved_ids = state.get("unremoved_confirmed_item_ids", [])
    if (
        not isinstance(unremoved_ids, list)
        or len(unremoved_ids) > _MAX_UNREMOVED_CONFIRMATIONS
        or len(set(unremoved_ids)) != len(unremoved_ids)
        or any(
            not isinstance(item_id, str)
            or _ITEM_ID_PATTERN.fullmatch(item_id) is None
            for item_id in unremoved_ids
        )
    ):
        raise ValueError(
            f"Delivery activity confirmation IDs are invalid: {state_path}"
        )
    return DeliveryActivity(
        status=state["status"],
        last_attempt_at_utc=state["last_attempt_at_utc"],
        last_successful_run_at_utc=state["last_successful_run_at_utc"],
        last_confirmed_upload_at_utc=state["last_confirmed_upload_at_utc"],
        last_confirmed_backup_queued_at_utc=state[
            "last_confirmed_backup_queued_at_utc"
        ],
        confirmed_uploads_total=state["confirmed_uploads_total"],
        failed_runs_total=state["failed_runs_total"],
        active_incident_upload_count=state["active_incident_upload_count"],
        unremoved_confirmed_item_ids=tuple(unremoved_ids),
    )


def record_delivery_run(
    *,
    confirmed_uploads: int,
    latest_backup_queued_at_utc: str | None,
    failed: bool,
    pending_count: int,
    confirmed_item_ids: tuple[str, ...] | None = None,
    incident_confirmed_uploads: int = 0,
    state_dir: Path | str | None = None,
    now: datetime | None = None,
) -> DeliveryRunTransition:
    for label, value in (
        ("confirmed uploads", confirmed_uploads),
        ("incident confirmed uploads", incident_confirmed_uploads),
        ("pending count", pending_count),
    ):
        if type(value) is not int or value < 0:
            raise ValueError(f"Delivery activity {label} must be non-negative.")
    if type(failed) is not bool:
        raise ValueError("Delivery activity failed flag must be boolean.")
    if latest_backup_queued_at_utc is not None:
        _validate_optional_utc_timestamp(
            latest_backup_queued_at_utc,
            _delivery_activity_path(state_dir),
        )
    previous = load_delivery_activity(state_dir)
    if confirmed_item_ids is None:
        effective_confirmed_uploads = confirmed_uploads
        unremoved_ids = previous.unremoved_confirmed_item_ids
    else:
        if (
            len(confirmed_item_ids) != confirmed_uploads
            or len(set(confirmed_item_ids)) != len(confirmed_item_ids)
            or any(
                not isinstance(item_id, str)
                or _ITEM_ID_PATTERN.fullmatch(item_id) is None
                for item_id in confirmed_item_ids
            )
        ):
            raise ValueError("Delivery confirmation item IDs are invalid.")
        previous_ids = set(previous.unremoved_confirmed_item_ids)
        effective_confirmed_uploads = sum(
            item_id not in previous_ids for item_id in confirmed_item_ids
        )
        unremoved_ids = tuple(
            dict.fromkeys(
                (*previous.unremoved_confirmed_item_ids, *confirmed_item_ids)
            )
        )
        if len(unremoved_ids) > _MAX_UNREMOVED_CONFIRMATIONS:
            raise ValueError("Too many unremoved delivery confirmations are pending.")
    timestamp = _format_utc_timestamp(now)
    was_failing = previous.status == "failing"
    recovered = was_failing and not failed and pending_count == 0
    remains_failing = failed or (was_failing and pending_count > 0)
    incident_upload_count = (
        previous.active_incident_upload_count
        if was_failing
        else incident_confirmed_uploads
    ) + effective_confirmed_uploads
    recovered_upload_count = incident_upload_count if recovered else 0
    latest_confirmed_backup = _later_timestamp(
        previous.last_confirmed_backup_queued_at_utc,
        latest_backup_queued_at_utc if effective_confirmed_uploads else None,
    )
    activity = DeliveryActivity(
        status="failing" if remains_failing else "healthy",
        last_attempt_at_utc=timestamp,
        last_successful_run_at_utc=(
            previous.last_successful_run_at_utc if failed else timestamp
        ),
        last_confirmed_upload_at_utc=(
            timestamp
            if effective_confirmed_uploads
            else previous.last_confirmed_upload_at_utc
        ),
        last_confirmed_backup_queued_at_utc=latest_confirmed_backup,
        confirmed_uploads_total=(
            previous.confirmed_uploads_total + effective_confirmed_uploads
        ),
        failed_runs_total=previous.failed_runs_total + int(failed),
        active_incident_upload_count=(incident_upload_count if remains_failing else 0),
        unremoved_confirmed_item_ids=unremoved_ids,
    )
    _write_delivery_activity(_delivery_activity_path(state_dir), activity)
    return DeliveryRunTransition(
        activity=activity,
        recovered=recovered,
        recovered_upload_count=recovered_upload_count,
    )


def record_delivery_confirmations(
    *,
    confirmed_uploads: int,
    confirmed_item_ids: tuple[str, ...],
    latest_backup_queued_at_utc: str | None,
    state_dir: Path | str | None = None,
    now: datetime | None = None,
) -> DeliveryConfirmationCheckpoint:
    if type(confirmed_uploads) is not int or confirmed_uploads < 0:
        raise ValueError(
            "Delivery activity confirmed uploads must be non-negative."
        )
    if (
        len(confirmed_item_ids) != confirmed_uploads
        or len(set(confirmed_item_ids)) != len(confirmed_item_ids)
        or any(
            not isinstance(item_id, str)
            or _ITEM_ID_PATTERN.fullmatch(item_id) is None
            for item_id in confirmed_item_ids
        )
    ):
        raise ValueError("Delivery confirmation item IDs are invalid.")
    if latest_backup_queued_at_utc is not None:
        _validate_optional_utc_timestamp(
            latest_backup_queued_at_utc,
            _delivery_activity_path(state_dir),
        )
    previous = load_delivery_activity(state_dir)
    previous_ids = set(previous.unremoved_confirmed_item_ids)
    effective_confirmed_uploads = sum(
        item_id not in previous_ids for item_id in confirmed_item_ids
    )
    unremoved_ids = tuple(
        dict.fromkeys((*previous.unremoved_confirmed_item_ids, *confirmed_item_ids))
    )
    if len(unremoved_ids) > _MAX_UNREMOVED_CONFIRMATIONS:
        raise ValueError("Too many unremoved delivery confirmations are pending.")
    timestamp = _format_utc_timestamp(now)
    latest_confirmed_backup = _later_timestamp(
        previous.last_confirmed_backup_queued_at_utc,
        latest_backup_queued_at_utc if effective_confirmed_uploads else None,
    )
    activity = replace(
        previous,
        last_confirmed_upload_at_utc=(
            timestamp
            if effective_confirmed_uploads
            else previous.last_confirmed_upload_at_utc
        ),
        last_confirmed_backup_queued_at_utc=latest_confirmed_backup,
        confirmed_uploads_total=(
            previous.confirmed_uploads_total + effective_confirmed_uploads
        ),
        active_incident_upload_count=(
            previous.active_incident_upload_count + effective_confirmed_uploads
            if previous.status == "failing"
            else 0
        ),
        unremoved_confirmed_item_ids=unremoved_ids,
    )
    _write_delivery_activity(_delivery_activity_path(state_dir), activity)
    return DeliveryConfirmationCheckpoint(
        activity=activity,
        effective_confirmed_uploads=effective_confirmed_uploads,
    )


def acknowledge_confirmed_delivery_items(
    item_ids: tuple[str, ...],
    *,
    state_dir: Path | str | None = None,
) -> DeliveryActivity:
    if len(set(item_ids)) != len(item_ids) or any(
        not isinstance(item_id, str) or _ITEM_ID_PATTERN.fullmatch(item_id) is None
        for item_id in item_ids
    ):
        raise ValueError("Delivery cleanup acknowledgement IDs are invalid.")
    previous = load_delivery_activity(state_dir)
    acknowledged = set(item_ids)
    remaining = tuple(
        item_id
        for item_id in previous.unremoved_confirmed_item_ids
        if item_id not in acknowledged
    )
    if remaining == previous.unremoved_confirmed_item_ids:
        return previous
    activity = replace(previous, unremoved_confirmed_item_ids=remaining)
    _write_delivery_activity(_delivery_activity_path(state_dir), activity)
    return activity


def sha256_file(path: Path) -> str:
    file_path = Path(path)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        descriptor = os.open(file_path, flags)
    except OSError as error:
        raise ValueError(f"Backup image is not a direct regular file: {file_path}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"Backup image is not a direct regular file: {file_path}")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)
    finally:
        os.close(descriptor)


def remote_backup_basename(now: datetime) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Backup name timestamp must be timezone-aware.")
    local = now.astimezone(ZoneInfo("Europe/Sofia"))
    disambiguator = ""
    if local.replace(fold=0).utcoffset() != local.replace(fold=1).utcoffset():
        offset = local.strftime("%z")
        disambiguator = f"_utc{offset[:3]}-{offset[3:]}"
    return f"extrusion-terminal_{local:%Y-%m-%d_%H-%M-%S}{disambiguator}.sqlite3"


def _empty_activity() -> BackupActivity:
    return BackupActivity(
        status="never",
        last_attempt_at_utc=None,
        last_successful_check_at_utc=None,
        last_change_at_utc=None,
        last_validated_sha256=None,
        last_observation_id=None,
        successful_checks_total=0,
        failed_checks_total=0,
        changed_versions_total=0,
    )


def _empty_delivery_activity() -> DeliveryActivity:
    return DeliveryActivity(
        status="never",
        last_attempt_at_utc=None,
        last_successful_run_at_utc=None,
        last_confirmed_upload_at_utc=None,
        last_confirmed_backup_queued_at_utc=None,
        confirmed_uploads_total=0,
        failed_runs_total=0,
        active_incident_upload_count=0,
        unremoved_confirmed_item_ids=(),
    )


def _state_root(state_dir: Path | str | None) -> Path:
    return (Path(state_dir) if state_dir is not None else DEFAULT_STATE_DIR).resolve()


def _activity_path(state_dir: Path | str | None) -> Path:
    return _state_root(state_dir) / BACKUP_ACTIVITY_FILENAME


def _handoff_path(state_dir: Path | str | None) -> Path:
    return _state_root(state_dir) / BACKUP_HANDOFF_FILENAME


def _delivery_activity_path(state_dir: Path | str | None) -> Path:
    return _state_root(state_dir) / DELIVERY_ACTIVITY_FILENAME


def _load_json_state(
    state_path: Path,
    label: str,
    *,
    missing: object,
) -> dict[str, object] | object:
    try:
        raw = read_bounded_regular_file(
            state_path,
            max_bytes=_MAX_ACTIVITY_BYTES,
            label=label,
        )
    except FileNotFoundError:
        return missing
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid: {state_path}") from error
    if not isinstance(state, dict):
        raise ValueError(f"{label} schema is invalid: {state_path}")
    return state


def _format_utc_timestamp(value: datetime | None) -> str:
    timestamp = value if value is not None else datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Backup activity timestamp must be timezone-aware.")
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).strftime(
        _UTC_TIMESTAMP_FORMAT
    )


def _parse_utc(value: str) -> datetime:
    return datetime.strptime(value, _UTC_TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)


def _validate_optional_utc_timestamp(value: object, state_path: Path) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError(f"Backup activity timestamp is invalid: {state_path}")
    try:
        parsed = datetime.strptime(value, _UTC_TIMESTAMP_FORMAT)
    except ValueError as error:
        raise ValueError(f"Backup activity timestamp is invalid: {state_path}") from error
    if parsed.strftime(_UTC_TIMESTAMP_FORMAT) != value:
        raise ValueError(f"Backup activity timestamp is invalid: {state_path}")


def _later_timestamp(first: str | None, second: str | None) -> str | None:
    if first is None:
        return second
    if second is None:
        return first
    return max(first, second)


def _write_activity(state_path: Path, activity: BackupActivity) -> None:
    _atomic_write_json(
        state_path,
        {
            "schema_version": BACKUP_ACTIVITY_SCHEMA_VERSION,
            "status": activity.status,
            "last_attempt_at_utc": activity.last_attempt_at_utc,
            "last_successful_check_at_utc": activity.last_successful_check_at_utc,
            "last_change_at_utc": activity.last_change_at_utc,
            "last_validated_sha256": activity.last_validated_sha256,
            "last_observation_id": activity.last_observation_id,
            "successful_checks_total": activity.successful_checks_total,
            "failed_checks_total": activity.failed_checks_total,
            "changed_versions_total": activity.changed_versions_total,
        },
    )


def _write_handoff(state_path: Path, handoff: BackupHandoff) -> None:
    _atomic_write_json(
        state_path,
        {
            "schema_version": BACKUP_HANDOFF_SCHEMA_VERSION,
            "observation_id": handoff.observation_id,
            "started_at_utc": handoff.started_at_utc,
            "backup_filename": handoff.backup_filename,
            "remote_basename": handoff.remote_basename,
            "queue_item_id": handoff.queue_item_id,
            "validated_sha256": handoff.validated_sha256,
            "database_changed": handoff.database_changed,
        },
    )


def _write_delivery_activity(state_path: Path, activity: DeliveryActivity) -> None:
    _atomic_write_json(
        state_path,
        {
            "schema_version": DELIVERY_ACTIVITY_SCHEMA_VERSION,
            "status": activity.status,
            "last_attempt_at_utc": activity.last_attempt_at_utc,
            "last_successful_run_at_utc": activity.last_successful_run_at_utc,
            "last_confirmed_upload_at_utc": activity.last_confirmed_upload_at_utc,
            "last_confirmed_backup_queued_at_utc": (
                activity.last_confirmed_backup_queued_at_utc
            ),
            "confirmed_uploads_total": activity.confirmed_uploads_total,
            "failed_runs_total": activity.failed_runs_total,
            "active_incident_upload_count": activity.active_incident_upload_count,
            "unremoved_confirmed_item_ids": list(
                activity.unremoved_confirmed_item_ids
            ),
        },
    )


def _atomic_write_json(state_path: Path, state: dict[str, object]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_name(f".{state_path.name}.tmp-{uuid4().hex}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                state,
                handle,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, state_path)
        _fsync_directory(state_path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
