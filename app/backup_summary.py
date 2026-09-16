from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from .backup_activity import (
    BackupActivity,
    DeliveryActivity,
    load_backup_activity,
    load_delivery_activity,
)
from .bounded_files import read_bounded_regular_file
from .pipeline_notifications import (
    NotificationResult,
    NotificationSender,
    component_incident_active,
    record_component_failure,
    record_component_success,
    suppress_unalerted_component_incident,
)


DEFAULT_SUMMARY_CONFIG_PATH = Path(
    "/etc/extrusion-terminal/backup-summary.conf"
)
BACKUP_SUMMARY_STATE_FILENAME = "database-backup-summary.json"
BACKUP_SUMMARY_STATE_SCHEMA_VERSION = 1
PRODUCER_STALE_AFTER = timedelta(minutes=90)
_DEFAULT_SUMMARY_TIMES = (time(9, 0),)
_MAX_CONFIG_BYTES = 1024
_MAX_STATE_BYTES = 16 * 1024
_MAX_MESSAGE_BYTES = 1_800
_UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_SLOT_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}/[0-9]{2}:[0-9]{2}")
_SETTING_PATTERN = re.compile(
    r"summary_times=(off|[0-9]{2}:[0-9]{2}(?:,[0-9]{2}:[0-9]{2})?)\n?"
)
_STATE_KEYS = frozenset(
    {
        "schema_version",
        "schedule_signature",
        "initialized_at_utc",
        "last_delivered_slot",
        "pending_slot",
        "pending_message",
        "baseline_successful_checks_total",
        "baseline_failed_checks_total",
        "baseline_changed_versions_total",
        "baseline_confirmed_uploads_total",
        "pending_successful_checks_total",
        "pending_failed_checks_total",
        "pending_changed_versions_total",
        "pending_confirmed_uploads_total",
    }
)


@dataclass(frozen=True)
class BackupSummaryResult:
    state_path: Path
    scheduled_slot: str | None
    notification_attempted: bool
    notification_sent: bool
    notification_pending: bool
    notification_error: str | None


@dataclass(frozen=True)
class _SummaryState:
    schedule_signature: str
    initialized_at_utc: str
    last_delivered_slot: str | None
    pending_slot: str | None
    pending_message: str | None
    baseline_successful_checks_total: int
    baseline_failed_checks_total: int
    baseline_changed_versions_total: int
    baseline_confirmed_uploads_total: int
    pending_successful_checks_total: int | None
    pending_failed_checks_total: int | None
    pending_changed_versions_total: int | None
    pending_confirmed_uploads_total: int | None


@dataclass(frozen=True)
class _Evidence:
    backup: BackupActivity | None
    delivery: DeliveryActivity | None
    backup_error: bool
    delivery_error: bool


def load_summary_times(path: Path | str | None = None) -> tuple[time, ...]:
    config_path = (
        Path(path)
        if path is not None
        else Path(
            os.getenv(
                "EXTRUSION_BACKUP_SUMMARY_CONFIG",
                str(DEFAULT_SUMMARY_CONFIG_PATH),
            )
        )
    )
    try:
        raw = read_bounded_regular_file(
            config_path,
            max_bytes=_MAX_CONFIG_BYTES,
            label="Backup summary configuration",
        )
    except FileNotFoundError:
        return _DEFAULT_SUMMARY_TIMES
    try:
        setting = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError(
            f"Backup summary configuration is not ASCII: {config_path}"
        ) from error
    match = _SETTING_PATTERN.fullmatch(setting)
    if match is None:
        raise ValueError(f"Backup summary configuration is invalid: {config_path}")
    value = match.group(1)
    if value == "off":
        return ()

    parsed: list[time] = []
    for item in value.split(","):
        hour = int(item[:2])
        minute = int(item[3:])
        if hour > 23 or minute > 59:
            raise ValueError(
                f"Backup summary configuration has an invalid time: {config_path}"
            )
        parsed.append(time(hour, minute))
    if len(set(parsed)) != len(parsed):
        raise ValueError(
            f"Backup summary configuration contains duplicate times: {config_path}"
        )
    return tuple(sorted(parsed))


def maybe_send_backup_summary(
    *,
    state_dir: Path | str,
    pending_count: int,
    notifier: NotificationSender,
    now: datetime | None = None,
    config_path: Path | str | None = None,
    urgent_notification_pending: bool = False,
) -> BackupSummaryResult:
    if type(pending_count) is not int or pending_count < 0:
        raise ValueError("Backup summary pending count must be non-negative.")
    if type(urgent_notification_pending) is not bool:
        raise ValueError("Backup summary urgent-notification flag must be boolean.")
    run_time = now if now is not None else datetime.now(timezone.utc)
    if run_time.tzinfo is None or run_time.utcoffset() is None:
        raise ValueError("Backup summary timestamp must be timezone-aware.")
    run_time = run_time.astimezone(timezone.utc).replace(microsecond=0)
    state_path = Path(state_dir).resolve() / BACKUP_SUMMARY_STATE_FILENAME
    summary_times = load_summary_times(config_path)
    signature = _schedule_signature(summary_times)
    evidence = _load_evidence(Path(state_dir))
    state = _load_summary_state(state_path)

    if state is None:
        state = _new_summary_state(signature, evidence, run_time)
        _write_summary_state(state_path, state)
        return _summary_result(state_path)
    if state.schedule_signature != signature:
        state = _reconfigured_summary_state(state, signature, run_time)
        _write_summary_state(state_path, state)
        return _summary_result(state_path)

    if not summary_times:
        return _summary_result(state_path)

    if state.pending_slot is not None:
        if urgent_notification_pending:
            return _summary_result(
                state_path,
                slot=state.pending_slot,
                pending=True,
            )
        return _send_pending_summary(state_path, state, notifier)

    slot = _newest_due_slot(summary_times, state, run_time)
    if slot is None:
        return _summary_result(state_path)

    pending_state = _prepare_pending_summary(
        state,
        slot=slot,
        evidence=evidence,
        pending_count=pending_count,
        now=run_time,
    )
    _write_summary_state(state_path, pending_state)
    if urgent_notification_pending:
        return _summary_result(state_path, slot=slot, pending=True)
    return _send_pending_summary(state_path, pending_state, notifier)


def check_backup_freshness(
    *,
    state_dir: Path | str,
    notifier: NotificationSender,
    now: datetime | None = None,
) -> NotificationResult | None:
    run_time = now if now is not None else datetime.now(timezone.utc)
    if run_time.tzinfo is None or run_time.utcoffset() is None:
        raise ValueError("Backup freshness timestamp must be timezone-aware.")
    run_time = run_time.astimezone(timezone.utc).replace(microsecond=0)
    try:
        activity = load_backup_activity(state_dir)
    except ValueError:
        if component_incident_active("database-backup", state_dir=state_dir):
            suppress_unalerted_component_incident(
                "database-backup-freshness",
                state_dir=state_dir,
                now=run_time,
            )
            return None
        return record_component_failure(
            "database-backup-freshness",
            "Validated backup activity could not be verified.",
            state_dir=state_dir,
            notifier=notifier,
            now=run_time,
            notification_grace=PRODUCER_STALE_AFTER,
        )
    if activity.status == "failing":
        suppress_unalerted_component_incident(
            "database-backup-freshness",
            state_dir=state_dir,
            now=run_time,
        )
        return None
    if activity.status == "never" or activity.last_successful_check_at_utc is None:
        return record_component_failure(
            "database-backup-freshness",
            "No validated database check has been recorded.",
            state_dir=state_dir,
            notifier=notifier,
            now=run_time,
            notification_grace=PRODUCER_STALE_AFTER,
        )
    if _is_stale(activity.last_successful_check_at_utc, run_time):
        return record_component_failure(
            "database-backup-freshness",
            "No validated database check has been recorded in the last 90 minutes.",
            state_dir=state_dir,
            notifier=notifier,
            now=run_time,
            context={
                "last_successful_check_at_utc": (
                    activity.last_successful_check_at_utc
                )
            },
            notification_grace=timedelta(0),
        )
    return record_component_success(
        "database-backup-freshness",
        state_dir=state_dir,
        notifier=notifier,
        now=run_time,
        notification_grace=PRODUCER_STALE_AFTER,
    )


def _schedule_signature(summary_times: tuple[time, ...]) -> str:
    if not summary_times:
        return "off"
    return ",".join(value.strftime("%H:%M") for value in summary_times)


def _new_summary_state(
    signature: str,
    evidence: _Evidence,
    now: datetime,
) -> _SummaryState:
    backup = evidence.backup
    delivery = evidence.delivery
    return _SummaryState(
        schedule_signature=signature,
        initialized_at_utc=_format_utc(now),
        last_delivered_slot=None,
        pending_slot=None,
        pending_message=None,
        baseline_successful_checks_total=(
            backup.successful_checks_total if backup is not None else 0
        ),
        baseline_failed_checks_total=(
            backup.failed_checks_total if backup is not None else 0
        ),
        baseline_changed_versions_total=(
            backup.changed_versions_total if backup is not None else 0
        ),
        baseline_confirmed_uploads_total=(
            delivery.confirmed_uploads_total if delivery is not None else 0
        ),
        pending_successful_checks_total=None,
        pending_failed_checks_total=None,
        pending_changed_versions_total=None,
        pending_confirmed_uploads_total=None,
    )


def _reconfigured_summary_state(
    state: _SummaryState,
    signature: str,
    now: datetime,
) -> _SummaryState:
    return replace(
        state,
        schedule_signature=signature,
        initialized_at_utc=_format_utc(now),
        last_delivered_slot=None,
        pending_slot=None,
        pending_message=None,
        pending_successful_checks_total=None,
        pending_failed_checks_total=None,
        pending_changed_versions_total=None,
        pending_confirmed_uploads_total=None,
    )


def _newest_due_slot(
    summary_times: tuple[time, ...],
    state: _SummaryState,
    now: datetime,
) -> str | None:
    sofia = ZoneInfo("Europe/Sofia")
    local_date = now.astimezone(sofia).date()
    initialized = _parse_utc(state.initialized_at_utc)
    candidates = []
    for candidate_date in (local_date - timedelta(days=1), local_date):
        for candidate_time in summary_times:
            candidate_instant = _first_valid_slot_instant(
                candidate_date,
                candidate_time,
                sofia,
            )
            if candidate_instant <= now.astimezone(timezone.utc):
                candidates.append(
                    (candidate_instant, candidate_date, candidate_time)
                )
    if not candidates:
        return None
    candidate_instant, candidate_date, candidate_time = max(
        candidates,
        key=lambda candidate: candidate[0],
    )
    slot = _slot_id(candidate_date, candidate_time)
    if candidate_instant <= initialized:
        return None
    if state.last_delivered_slot is not None and slot <= state.last_delivered_slot:
        return None
    return slot


def _first_valid_slot_instant(
    candidate_date,
    candidate_time: time,
    zone: ZoneInfo,
) -> datetime:
    local = datetime.combine(candidate_date, candidate_time)
    for minutes_after in range(181):
        tested_local = local + timedelta(minutes=minutes_after)
        valid_instants = {
            aware.astimezone(timezone.utc)
            for fold in (0, 1)
            for aware in (tested_local.replace(tzinfo=zone, fold=fold),)
            if aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
            == tested_local
        }
        if valid_instants:
            return min(valid_instants)
    raise ValueError("Backup summary slot could not be resolved in Europe/Sofia.")


def _prepare_pending_summary(
    state: _SummaryState,
    *,
    slot: str,
    evidence: _Evidence,
    pending_count: int,
    now: datetime,
) -> _SummaryState:
    backup = evidence.backup
    delivery = evidence.delivery
    backup_counts = (
        _snapshot_counter(
            backup.successful_checks_total if backup is not None else None,
            state.baseline_successful_checks_total,
        ),
        _snapshot_counter(
            backup.failed_checks_total if backup is not None else None,
            state.baseline_failed_checks_total,
        ),
        _snapshot_counter(
            backup.changed_versions_total if backup is not None else None,
            state.baseline_changed_versions_total,
        ),
    )
    delivery_count = _snapshot_counter(
        delivery.confirmed_uploads_total if delivery is not None else None,
        state.baseline_confirmed_uploads_total,
    )
    message = _build_summary_message(
        slot=slot,
        state=state,
        evidence=evidence,
        pending_count=pending_count,
        now=now,
    )
    return replace(
        state,
        pending_slot=slot,
        pending_message=message,
        pending_successful_checks_total=backup_counts[0],
        pending_failed_checks_total=backup_counts[1],
        pending_changed_versions_total=backup_counts[2],
        pending_confirmed_uploads_total=delivery_count,
    )


def _send_pending_summary(
    state_path: Path,
    state: _SummaryState,
    notifier: NotificationSender,
) -> BackupSummaryResult:
    if state.pending_slot is None or state.pending_message is None:
        raise ValueError("Backup summary pending state is incomplete.")
    delivered_slot = state.pending_slot
    try:
        notifier.send(state.pending_message)
    except Exception as error:
        print(
            "Backup summary notification warning: notification remains pending",
            file=sys.stderr,
        )
        return _summary_result(
            state_path,
            slot=state.pending_slot,
            attempted=True,
            pending=True,
            error=f"{error.__class__.__name__}: notification delivery failed",
        )

    delivered = replace(
        state,
        last_delivered_slot=state.pending_slot,
        pending_slot=None,
        pending_message=None,
        baseline_successful_checks_total=_pending_or_baseline(
            state.pending_successful_checks_total,
            state.baseline_successful_checks_total,
        ),
        baseline_failed_checks_total=_pending_or_baseline(
            state.pending_failed_checks_total,
            state.baseline_failed_checks_total,
        ),
        baseline_changed_versions_total=_pending_or_baseline(
            state.pending_changed_versions_total,
            state.baseline_changed_versions_total,
        ),
        baseline_confirmed_uploads_total=_pending_or_baseline(
            state.pending_confirmed_uploads_total,
            state.baseline_confirmed_uploads_total,
        ),
        pending_successful_checks_total=None,
        pending_failed_checks_total=None,
        pending_changed_versions_total=None,
        pending_confirmed_uploads_total=None,
    )
    _write_summary_state(state_path, delivered)
    return _summary_result(
        state_path,
        slot=delivered_slot,
        attempted=True,
        sent=True,
    )


def _pending_or_baseline(pending: int | None, baseline: int) -> int:
    return pending if pending is not None else baseline


def _snapshot_counter(current: int | None, baseline: int) -> int | None:
    if current is None or current < baseline:
        return None
    return current


def _build_summary_message(
    *,
    slot: str,
    state: _SummaryState,
    evidence: _Evidence,
    pending_count: int,
    now: datetime,
) -> str:
    backup = evidence.backup
    delivery = evidence.delivery
    warnings: list[str] = []
    if evidence.backup_error:
        warnings.append("Backup activity details could not be verified.")
    elif backup is None or backup.status == "never":
        warnings.append("No validated database check has been recorded.")
    elif backup.status == "failing":
        warnings.append("The latest database backup check failed.")
    elif _is_stale(backup.last_successful_check_at_utc, now):
        warnings.append("No validated database check was recorded in the last 90 minutes.")
    if backup is not None and any(
        current < baseline
        for current, baseline in (
            (
                backup.successful_checks_total,
                state.baseline_successful_checks_total,
            ),
            (backup.failed_checks_total, state.baseline_failed_checks_total),
            (
                backup.changed_versions_total,
                state.baseline_changed_versions_total,
            ),
        )
    ):
        warnings.append(
            "Backup activity counters moved backwards; interval totals are unknown."
        )
    if evidence.delivery_error:
        warnings.append("Cloud upload activity details could not be verified.")
    elif delivery is None or delivery.status == "never":
        warnings.append("No cloud upload activity has been recorded.")
    elif delivery.status == "failing":
        warnings.append("Cloud backup delivery is currently failing.")
    if (
        delivery is not None
        and delivery.confirmed_uploads_total
        < state.baseline_confirmed_uploads_total
    ):
        warnings.append(
            "Cloud activity counters moved backwards; interval totals are unknown."
        )
    if pending_count:
        noun = "backup is" if pending_count == 1 else "backups are"
        warnings.append(f"{pending_count} {noun} still waiting for upload.")

    successful = _counter_delta(
        backup.successful_checks_total if backup is not None else None,
        state.baseline_successful_checks_total,
    )
    failed = _counter_delta(
        backup.failed_checks_total if backup is not None else None,
        state.baseline_failed_checks_total,
    )
    changed = _counter_delta(
        backup.changed_versions_total if backup is not None else None,
        state.baseline_changed_versions_total,
    )
    uploads = _counter_delta(
        delivery.confirmed_uploads_total if delivery is not None else None,
        state.baseline_confirmed_uploads_total,
    )
    warning = bool(warnings)
    title = (
        "⚠️ Extrusion Terminal — Backup summary needs attention"
        if warning
        else "✅ Extrusion Terminal — Backup summary"
    )
    lines = [
        title,
        "",
        f"Scheduled summary: {_display_slot(slot)}",
        f"Validated database checks: {_display_count(successful)}",
        f"Failed database checks: {_display_count(failed)}",
        f"Changed database versions: {_display_count(changed)}",
        f"Confirmed Hetzner uploads: {_display_count(uploads)}",
        "Latest validated check: "
        + _display_timestamp(
            backup.last_successful_check_at_utc if backup else None
        ),
        "Latest changed backup uploaded: "
        + _display_timestamp(
            delivery.last_confirmed_upload_at_utc if delivery else None
        ),
        f"Waiting backups: {pending_count}",
        "",
    ]
    if warnings:
        lines.append("Status: " + " ".join(warnings))
    else:
        lines.append("Status: Backup checks and cloud delivery are operating normally.")
    return "\n".join(lines)[:_MAX_MESSAGE_BYTES]


def _counter_delta(current: int | None, baseline: int) -> int | None:
    if current is None or current < baseline:
        return None
    return current - baseline


def _display_count(value: int | None) -> str:
    return str(value) if value is not None else "unknown"


def _is_stale(value: str | None, now: datetime) -> bool:
    if value is None:
        return True
    try:
        return now - _parse_utc(value) >= PRODUCER_STALE_AFTER
    except ValueError:
        return True


def _display_slot(slot: str) -> str:
    try:
        parsed = datetime.strptime(slot, "%Y-%m-%d/%H:%M")
    except ValueError:
        return "an unknown time"
    return parsed.strftime("%d %b %Y at %H:%M")


def _display_timestamp(value: str | None) -> str:
    if value is None:
        return "unknown"
    try:
        parsed = _parse_utc(value)
    except ValueError:
        return "unknown"
    return parsed.astimezone(ZoneInfo("Europe/Sofia")).strftime(
        "%d %b %Y at %H:%M"
    )


def _slot_id(day: date, value: time) -> str:
    return f"{day.isoformat()}/{value:%H:%M}"


def _load_evidence(state_dir: Path) -> _Evidence:
    try:
        backup = load_backup_activity(state_dir)
    except ValueError:
        backup = None
        backup_error = True
    else:
        backup_error = False
    try:
        delivery = load_delivery_activity(state_dir)
    except ValueError:
        delivery = None
        delivery_error = True
    else:
        delivery_error = False
    return _Evidence(backup, delivery, backup_error, delivery_error)


def _load_summary_state(state_path: Path) -> _SummaryState | None:
    try:
        raw = read_bounded_regular_file(
            state_path,
            max_bytes=_MAX_STATE_BYTES,
            label="Backup summary state",
        )
    except FileNotFoundError:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Backup summary state is invalid: {state_path}") from error
    if not isinstance(value, dict) or set(value) != _STATE_KEYS:
        raise ValueError(f"Backup summary state schema is invalid: {state_path}")
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != BACKUP_SUMMARY_STATE_SCHEMA_VERSION
    ):
        raise ValueError(f"Backup summary state version is unsupported: {state_path}")
    if not isinstance(value["schedule_signature"], str) or not _valid_signature(
        value["schedule_signature"]
    ):
        raise ValueError(f"Backup summary state schedule is invalid: {state_path}")
    _parse_utc_value(value["initialized_at_utc"], state_path)
    for key in ("last_delivered_slot", "pending_slot"):
        item = value[key]
        if item is not None and (
            not isinstance(item, str) or _SLOT_PATTERN.fullmatch(item) is None
        ):
            raise ValueError(f"Backup summary state slot is invalid: {state_path}")
        if item is not None:
            try:
                parsed_slot = datetime.strptime(item, "%Y-%m-%d/%H:%M")
            except ValueError as error:
                raise ValueError(
                    f"Backup summary state slot is invalid: {state_path}"
                ) from error
            if parsed_slot.strftime("%Y-%m-%d/%H:%M") != item:
                raise ValueError(f"Backup summary state slot is invalid: {state_path}")
    if value["pending_message"] is not None and (
        not isinstance(value["pending_message"], str)
        or len(value["pending_message"].encode("utf-8")) > _MAX_MESSAGE_BYTES
    ):
        raise ValueError(f"Backup summary state message is invalid: {state_path}")
    baseline_keys = (
        "baseline_successful_checks_total",
        "baseline_failed_checks_total",
        "baseline_changed_versions_total",
        "baseline_confirmed_uploads_total",
    )
    pending_keys = (
        "pending_successful_checks_total",
        "pending_failed_checks_total",
        "pending_changed_versions_total",
        "pending_confirmed_uploads_total",
    )
    for key in baseline_keys:
        if type(value[key]) is not int or value[key] < 0:
            raise ValueError(f"Backup summary state counter is invalid: {state_path}")
    for key in pending_keys:
        if value[key] is not None and (type(value[key]) is not int or value[key] < 0):
            raise ValueError(f"Backup summary state counter is invalid: {state_path}")
    pending_values = [value["pending_slot"], value["pending_message"]]
    if (pending_values[0] is None) != (pending_values[1] is None):
        raise ValueError(f"Backup summary pending state is invalid: {state_path}")
    if value["pending_slot"] is None and any(
        value[key] is not None for key in pending_keys
    ):
        raise ValueError(f"Backup summary pending counters are invalid: {state_path}")
    return _SummaryState(
        schedule_signature=value["schedule_signature"],
        initialized_at_utc=value["initialized_at_utc"],
        last_delivered_slot=value["last_delivered_slot"],
        pending_slot=value["pending_slot"],
        pending_message=value["pending_message"],
        baseline_successful_checks_total=value["baseline_successful_checks_total"],
        baseline_failed_checks_total=value["baseline_failed_checks_total"],
        baseline_changed_versions_total=value["baseline_changed_versions_total"],
        baseline_confirmed_uploads_total=value["baseline_confirmed_uploads_total"],
        pending_successful_checks_total=value["pending_successful_checks_total"],
        pending_failed_checks_total=value["pending_failed_checks_total"],
        pending_changed_versions_total=value["pending_changed_versions_total"],
        pending_confirmed_uploads_total=value["pending_confirmed_uploads_total"],
    )


def _write_summary_state(state_path: Path, state: _SummaryState) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    value: Mapping[str, object] = {
        "schema_version": BACKUP_SUMMARY_STATE_SCHEMA_VERSION,
        **state.__dict__,
    }
    temporary = state_path.with_name(f".{state_path.name}.tmp-{uuid4().hex}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                value,
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


def _summary_result(
    state_path: Path,
    *,
    slot: str | None = None,
    attempted: bool = False,
    sent: bool = False,
    pending: bool = False,
    error: str | None = None,
) -> BackupSummaryResult:
    return BackupSummaryResult(
        state_path=state_path,
        scheduled_slot=slot,
        notification_attempted=attempted,
        notification_sent=sent,
        notification_pending=pending,
        notification_error=error,
    )


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(_UTC_TIMESTAMP_FORMAT)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.strptime(value, _UTC_TIMESTAMP_FORMAT)
    if parsed.strftime(_UTC_TIMESTAMP_FORMAT) != value:
        raise ValueError("UTC timestamp is not canonical.")
    return parsed.replace(tzinfo=timezone.utc)


def _parse_utc_value(value: object, state_path: Path) -> None:
    if not isinstance(value, str):
        raise ValueError(f"Backup summary state timestamp is invalid: {state_path}")
    try:
        _parse_utc(value)
    except ValueError as error:
        raise ValueError(
            f"Backup summary state timestamp is invalid: {state_path}"
        ) from error


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _valid_signature(value: str) -> bool:
    if value == "off":
        return True
    if (
        re.fullmatch(
            r"[0-9]{2}:[0-9]{2}(?:,[0-9]{2}:[0-9]{2})?",
            value,
        )
        is None
    ):
        return False
    parsed: list[time] = []
    for item in value.split(","):
        hour = int(item[:2])
        minute = int(item[3:])
        if hour > 23 or minute > 59:
            return False
        parsed.append(time(hour, minute))
    return parsed == sorted(set(parsed))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the Task 25 backup-summary schedule."
    )
    parser.add_argument("command", choices=("validate-config",))
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    try:
        summary_times = load_summary_times()
    except Exception:
        print("Backup summary configuration is invalid.")
        return 1
    print(_schedule_signature(summary_times))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
