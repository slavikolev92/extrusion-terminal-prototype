from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .artifact_outbox import (
    CATEGORY_REMOTE_FOLDERS,
    CATEGORY_SUFFIXES,
    CleanupResult,
    DEFAULT_OUTBOX_DIR,
    QueueEntry,
    QueuedArtifact,
    has_matching_content_identity,
    load_queued_artifact,
    quarantine_queue_entry,
    reap_delivered_cleanup,
    remove_delivered_artifact,
    snapshot_queue_entries,
)
from .backup_activity import (
    DeliveryRunTransition,
    acknowledge_confirmed_delivery_items,
    load_backup_handoff,
    load_delivery_activity,
    record_delivery_confirmations,
    record_delivery_run,
)
from .backup_summary import check_backup_freshness, maybe_send_backup_summary
from .curl_transport import CurlRunner, run_curl, validate_curl_config
from .pipeline_notifications import (
    DEFAULT_DISCORD_CURL_CONFIG,
    DEFAULT_STATE_DIR,
    DiscordWebhookSender,
    NotificationResult,
    NotificationSender,
    record_component_failure,
    record_component_success,
    retry_pending_notification,
)


DEFAULT_WEBDAV_BASE_URL = (
    "https://nx106226.your-storageshare.de/remote.php/dav/files/"
    "extrusion-backup"
)
DEFAULT_WEBDAV_ROOT = (
    "system-backups",
    "extrusion-terminal",
)
DEFAULT_WEBDAV_CURL_CONFIG = Path(
    os.getenv(
        "EXTRUSION_WEBDAV_CURL_CONFIG",
        "/etc/extrusion-terminal/hetzner-webdav.conf",
    )
)
MAX_DELIVERY_ITEMS_PER_RUN = 25
# The service has a 600-second systemd ceiling and the shared curl runner has a
# 180-second subprocess ceiling. These cutoffs leave time for durable state
# updates while ensuring that no second network operation can overrun systemd.
LATEST_UPLOAD_START_SECONDS = 180
LATEST_NOTIFICATION_START_SECONDS = 410
DATABASE_BACKUP_COLLECTION_TIMEOUT_SECONDS = 30
WEBDAV_FAILURE_GRACE = timedelta(minutes=10)


class WebDAVDeliveryError(RuntimeError):
    pass


class _DeliveryBudgetExpired(RuntimeError):
    pass


class _DeferredNotificationSender:
    def send(self, _message: str) -> None:
        raise RuntimeError(
            "Discord notification deferred until the next run by the service time budget."
        )


@dataclass(frozen=True)
class DeliveryConfig:
    outbox_dir: Path
    state_dir: Path
    webdav_base_url: str
    webdav_root: tuple[str, ...]
    webdav_curl_config: Path
    discord_curl_config: Path
    summary_config_path: Path | None = None


@dataclass(frozen=True)
class UploadResult:
    state: Literal["created", "already-present"]
    http_status: int
    remote_url: str


@dataclass(frozen=True)
class DeliveryBatchResult:
    created_count: int
    already_present_count: int
    failed_count: int
    pending_count: int
    first_error: str | None = None
    notification_pending: bool = False
    notification_error: str | None = None
    notification_state_error: str | None = None


def default_delivery_config() -> DeliveryConfig:
    return DeliveryConfig(
        outbox_dir=DEFAULT_OUTBOX_DIR,
        state_dir=DEFAULT_STATE_DIR,
        webdav_base_url=DEFAULT_WEBDAV_BASE_URL,
        webdav_root=DEFAULT_WEBDAV_ROOT,
        webdav_curl_config=DEFAULT_WEBDAV_CURL_CONFIG,
        discord_curl_config=DEFAULT_DISCORD_CURL_CONFIG,
    )


def upload_create_only(
    artifact: QueuedArtifact,
    config: DeliveryConfig,
    *,
    runner: CurlRunner = run_curl,
    network_start_allowed: Callable[[], bool] | None = None,
) -> UploadResult:
    _validate_fixed_destination(config)
    _validate_artifact_for_upload(artifact, config)
    return _upload_prevalidated_create_only(
        artifact,
        config,
        runner=runner,
        network_start_allowed=network_start_allowed,
    )


def _upload_prevalidated_create_only(
    artifact: QueuedArtifact,
    config: DeliveryConfig,
    *,
    runner: CurlRunner,
    network_start_allowed: Callable[[], bool] | None = None,
    ensured_collections: set[str] | None = None,
    remove_after_upload: bool = True,
) -> UploadResult:
    _validate_fixed_destination(config)
    _validate_artifact_identity(artifact)
    try:
        validate_curl_config(
            config.webdav_curl_config,
            required_options=frozenset({"user"}),
            allowed_options=frozenset({"user"}),
        )
    except ValueError as error:
        raise WebDAVDeliveryError("Protected WebDAV curl configuration is invalid.") from error

    _ensure_database_backup_daily_collection(
        artifact,
        config,
        runner=runner,
        network_start_allowed=network_start_allowed,
        ensured_collections=ensured_collections,
    )
    remote_url = _remote_url(artifact, config)
    command = [
        "curl",
        "--disable",
        "--config",
        str(config.webdav_curl_config),
        "--silent",
        "--show-error",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--connect-timeout",
        "10",
        "--max-time",
        "120",
        "--request",
        "PUT",
        "--upload-file",
        str(artifact.payload_path),
        "--header",
        "If-None-Match: *",
        remote_url,
    ]
    if network_start_allowed is not None and not network_start_allowed():
        raise _DeliveryBudgetExpired(
            "WebDAV upload deferred until the next run by the service time budget."
        )
    try:
        curl_result = runner(command, input_bytes=None)
    except Exception as error:
        raise WebDAVDeliveryError("WebDAV upload process did not complete.") from error
    if curl_result.returncode != 0:
        raise WebDAVDeliveryError(
            f"WebDAV upload failed with curl exit {curl_result.returncode}."
        )

    status_text = curl_result.stdout.strip()
    if len(status_text) != 3 or not status_text.isascii() or not status_text.isdigit():
        raise WebDAVDeliveryError("WebDAV upload returned an invalid HTTP status.")
    http_status = int(status_text)
    if http_status == 201:
        state: Literal["created", "already-present"] = "created"
    elif http_status == 412 and has_matching_content_identity(artifact):
        state = "already-present"
    else:
        raise WebDAVDeliveryError(
            f"WebDAV conditional create returned unexpected HTTP {http_status}."
        )

    if remove_after_upload:
        remove_delivered_artifact(artifact)
    return UploadResult(state=state, http_status=http_status, remote_url=remote_url)


def _ensure_database_backup_daily_collection(
    artifact: QueuedArtifact,
    config: DeliveryConfig,
    *,
    runner: CurlRunner,
    network_start_allowed: Callable[[], bool] | None = None,
    ensured_collections: set[str] | None = None,
) -> None:
    if artifact.category != "database-backups":
        return
    collection_url = _remote_collection_url(artifact, config)
    if ensured_collections is not None and collection_url in ensured_collections:
        return
    command = [
        "curl",
        "--disable",
        "--config",
        str(config.webdav_curl_config),
        "--silent",
        "--show-error",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--connect-timeout",
        "10",
        "--max-time",
        str(DATABASE_BACKUP_COLLECTION_TIMEOUT_SECONDS),
        "--request",
        "MKCOL",
        collection_url,
    ]
    if network_start_allowed is not None and not network_start_allowed():
        raise _DeliveryBudgetExpired(
            "WebDAV upload deferred until the next run by the service time budget."
        )
    try:
        curl_result = runner(command, input_bytes=None)
    except Exception as error:
        raise WebDAVDeliveryError(
            "WebDAV daily backup folder process did not complete."
        ) from error
    if curl_result.returncode != 0:
        raise WebDAVDeliveryError(
            "WebDAV daily backup folder creation failed with "
            f"curl exit {curl_result.returncode}."
        )
    status_text = curl_result.stdout.strip()
    if len(status_text) != 3 or not status_text.isascii() or not status_text.isdigit():
        raise WebDAVDeliveryError(
            "WebDAV daily backup folder creation returned an invalid HTTP status."
        )
    http_status = int(status_text)
    if http_status not in {201, 405}:
        raise WebDAVDeliveryError(
            "WebDAV daily backup folder creation returned unexpected "
            f"HTTP {http_status}."
        )
    if ensured_collections is not None:
        ensured_collections.add(collection_url)


def deliver_pending(
    config: DeliveryConfig,
    *,
    runner: CurlRunner = run_curl,
    notifier: NotificationSender | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    now: datetime | None = None,
) -> DeliveryBatchResult:
    run_time = now if now is not None else datetime.now(timezone.utc)
    if run_time.tzinfo is None or run_time.utcoffset() is None:
        raise ValueError("Delivery timestamp must be timezone-aware.")
    started_at = monotonic()
    created_count = 0
    already_present_count = 0
    failed_count = 0
    first_error: str | None = None
    failed_category: str | None = None
    remote_failure = False
    budget_expired = False
    ensured_collections: set[str] = set()
    confirmed_database_uploads = 0
    latest_backup_queued_at_utc: str | None = None
    confirmed_artifacts: list[QueuedArtifact] = []
    quarantine_present = False

    try:
        cleanup_result = reap_delivered_cleanup(
            config.outbox_dir,
            max_items=MAX_DELIVERY_ITEMS_PER_RUN,
        )
    except Exception as error:
        cleanup_result = CleanupResult(0, 1, _bounded_error(error))
    if cleanup_result.failed_count:
        failed_count += cleanup_result.failed_count
        first_error = cleanup_result.first_error
    try:
        _acknowledge_absent_delivery_confirmations(config)
    except Exception as error:
        failed_count += 1
        if first_error is None:
            first_error = _bounded_error(error)

    try:
        queue_snapshot = snapshot_queue_entries(
            config.outbox_dir,
            max_entries=MAX_DELIVERY_ITEMS_PER_RUN,
        )
    except Exception as error:
        queue_snapshot = None
        failed_count += 1
        if first_error is None:
            first_error = _bounded_error(error)
    if queue_snapshot is not None and queue_snapshot.quarantine_count:
        quarantine_present = True

    active_backup_item_id: str | None = None
    block_database_backups = False
    if queue_snapshot is not None:
        try:
            active_handoff = load_backup_handoff(config.state_dir)
        except Exception as error:
            block_database_backups = True
            failed_count += 1
            if first_error is None:
                first_error = _bounded_error(error)
        else:
            if active_handoff is not None:
                active_backup_item_id = active_handoff.queue_item_id

    for entry in queue_snapshot.entries if queue_snapshot is not None else ():
        if monotonic() - started_at >= LATEST_UPLOAD_START_SECONDS:
            budget_expired = True
            break
        if entry.kind != "pending-item":
            failed_count += 1
            quarantine_present = True
            if first_error is None:
                first_error = _queue_health_error(entry)
            try:
                quarantine_queue_entry(entry, outbox_dir=config.outbox_dir)
            except Exception as error:
                first_error = _append_secondary_error(
                    first_error, "quarantine failed", error
                )
            continue
        if entry.path.parent.name == "database-backups" and (
            block_database_backups or entry.path.name == active_backup_item_id
        ):
            continue
        try:
            artifact = load_queued_artifact(entry.path, outbox_dir=config.outbox_dir)
        except Exception as error:
            failed_count += 1
            quarantine_present = True
            if first_error is None:
                first_error = _bounded_error(error)
            try:
                quarantine_queue_entry(entry, outbox_dir=config.outbox_dir)
            except Exception as quarantine_error:
                first_error = _append_secondary_error(
                    first_error, "quarantine failed", quarantine_error
                )
            continue

        try:
            upload_result = _upload_prevalidated_create_only(
                artifact,
                config,
                runner=runner,
                network_start_allowed=lambda: (
                    monotonic() - started_at < LATEST_UPLOAD_START_SECONDS
                ),
                ensured_collections=ensured_collections,
                remove_after_upload=False,
            )
        except _DeliveryBudgetExpired:
            budget_expired = True
            failed_category = artifact.category
            break
        except WebDAVDeliveryError as error:
            failed_count += 1
            if first_error is None:
                first_error = _bounded_error(error)
                failed_category = artifact.category
                remote_failure = not first_error.startswith(
                    "Protected WebDAV curl configuration is invalid."
                )
            break
        except Exception as error:
            failed_count += 1
            if first_error is None:
                first_error = _bounded_error(error)
                failed_category = artifact.category
            continue

        if upload_result.state == "created":
            created_count += 1
        else:
            already_present_count += 1
        confirmed_artifacts.append(artifact)
        if artifact.category == "database-backups":
            confirmed_database_uploads += 1
            if (
                latest_backup_queued_at_utc is None
                or artifact.queued_at_utc > latest_backup_queued_at_utc
            ):
                latest_backup_queued_at_utc = artifact.queued_at_utc

    if (
        budget_expired
        and created_count == 0
        and already_present_count == 0
        and failed_count == 0
    ):
        failed_count = 1
        first_error = (
            "Delivery time budget expired before any WebDAV upload could start."
        )

    try:
        pre_cleanup_snapshot = snapshot_queue_entries(
            config.outbox_dir,
            max_entries=0,
        )
        pending_count = max(
            pre_cleanup_snapshot.pending_count - len(confirmed_artifacts),
            0,
        )
        if pre_cleanup_snapshot.quarantine_count:
            quarantine_present = True
        if quarantine_present and failed_count == 0:
            failed_count += 1
            if first_error is None:
                first_error = "Quarantined delivery items require manual review."
    except Exception as error:
        pending_count = queue_snapshot.pending_count if queue_snapshot is not None else 0
        failed_count += 1
        if first_error is None:
            first_error = _bounded_error(error)
    notification_state_error = None
    delivery_transition: DeliveryRunTransition | None = None
    confirmation_checkpoint = None
    if confirmed_database_uploads:
        try:
            confirmation_checkpoint = record_delivery_confirmations(
                confirmed_uploads=confirmed_database_uploads,
                confirmed_item_ids=tuple(
                    artifact.item_dir.name
                    for artifact in confirmed_artifacts
                    if artifact.category == "database-backups"
                ),
                latest_backup_queued_at_utc=latest_backup_queued_at_utc,
                state_dir=config.state_dir,
                now=run_time,
            )
        except Exception as error:
            notification_state_error = _bounded_error(error)
            failed_count += 1
            if first_error is None:
                first_error = "Delivery activity state could not be updated."
            try:
                retained_snapshot = snapshot_queue_entries(
                    config.outbox_dir,
                    max_entries=0,
                )
                pending_count = retained_snapshot.pending_count
                if retained_snapshot.quarantine_count:
                    quarantine_present = True
            except Exception as snapshot_error:
                notification_state_error = _combine_state_errors(
                    notification_state_error,
                    _bounded_error(snapshot_error),
                )
                failed_count += 1

    if not confirmed_database_uploads or confirmation_checkpoint is not None:
        removed_confirmation_ids: list[str] = []
        for artifact in confirmed_artifacts:
            try:
                remove_delivered_artifact(artifact)
            except Exception as error:
                failed_count += 1
                if first_error is None:
                    first_error = _bounded_error(error)
            else:
                if artifact.category == "database-backups":
                    removed_confirmation_ids.append(artifact.item_dir.name)
        try:
            final_snapshot = snapshot_queue_entries(config.outbox_dir, max_entries=0)
            pending_count = final_snapshot.pending_count
            if final_snapshot.quarantine_count:
                quarantine_present = True
            if quarantine_present and failed_count == 0:
                failed_count += 1
                if first_error is None:
                    first_error = "Quarantined delivery items require manual review."
        except Exception as error:
            failed_count += 1
            if first_error is None:
                first_error = _bounded_error(error)
        try:
            delivery_transition = record_delivery_run(
                confirmed_uploads=0,
                confirmed_item_ids=(),
                incident_confirmed_uploads=(
                    confirmation_checkpoint.effective_confirmed_uploads
                    if confirmation_checkpoint is not None
                    else 0
                ),
                latest_backup_queued_at_utc=None,
                failed=bool(failed_count),
                pending_count=pending_count,
                state_dir=config.state_dir,
                now=run_time,
            )
            if removed_confirmation_ids:
                acknowledge_confirmed_delivery_items(
                    tuple(removed_confirmation_ids),
                    state_dir=config.state_dir,
                )
        except Exception as error:
            bounded_state_error = _bounded_error(error)
            notification_state_error = _combine_state_errors(
                notification_state_error,
                bounded_state_error,
            )
            failed_count += 1
            if first_error is None:
                first_error = "Delivery activity state could not be finalized."

    if monotonic() - started_at >= LATEST_NOTIFICATION_START_SECONDS:
        notification_sender: NotificationSender = _DeferredNotificationSender()
    else:
        notification_sender = (
            notifier
            if notifier is not None
            else DiscordWebhookSender(config.discord_curl_config)
        )
    remote_failure_only = (
        remote_failure
        and failed_count == 1
        and not quarantine_present
        and notification_state_error is None
    )
    context: dict[str, object] = {
        "pending_count": pending_count,
        "failure_kind": "remote" if remote_failure_only else "local",
        "manual_review_required": quarantine_present,
    }
    if failed_category is not None:
        context["category"] = failed_category
    notification_results: list[NotificationResult] = []
    try:
        if failed_count:
            notification_result = record_component_failure(
                "webdav-delivery",
                first_error or "Artifact delivery failed.",
                state_dir=config.state_dir,
                notifier=notification_sender,
                now=run_time,
                context=context,
                notification_grace=(
                    WEBDAV_FAILURE_GRACE
                    if remote_failure_only
                    else timedelta(0)
                ),
            )
        elif pending_count > 0:
            notification_result = retry_pending_notification(
                "webdav-delivery",
                state_dir=config.state_dir,
                notifier=notification_sender,
                now=run_time,
                context=context,
                notification_grace=WEBDAV_FAILURE_GRACE,
            )
        else:
            if delivery_transition is not None:
                context["recovered_upload_count"] = (
                    delivery_transition.recovered_upload_count
                )
            notification_result = record_component_success(
                "webdav-delivery",
                state_dir=config.state_dir,
                notifier=notification_sender,
                now=run_time,
                context=context,
                notification_grace=WEBDAV_FAILURE_GRACE,
            )
        notification_results.append(notification_result)
    except Exception as error:
        bounded_state_error = _bounded_error(error)
        notification_state_error = (
            bounded_state_error
            if notification_state_error is None
            else f"{notification_state_error}; {bounded_state_error}"
        )

    urgent_notification_pending = notification_state_error is not None or any(
        result.notification_attempted or result.notification_pending
        for result in notification_results
    )
    if not urgent_notification_pending:
        try:
            freshness_result = check_backup_freshness(
                state_dir=config.state_dir,
                notifier=notification_sender,
                now=run_time,
            )
            if freshness_result is not None:
                notification_results.append(freshness_result)
                urgent_notification_pending = (
                    freshness_result.notification_attempted
                    or freshness_result.notification_pending
                )
        except Exception as error:
            notification_state_error = _combine_state_errors(
                notification_state_error,
                _bounded_error(error),
            )
            urgent_notification_pending = True

    summary_result = None
    try:
        summary_result = maybe_send_backup_summary(
            state_dir=config.state_dir,
            pending_count=pending_count,
            notifier=notification_sender,
            now=run_time,
            config_path=config.summary_config_path,
            urgent_notification_pending=urgent_notification_pending,
        )
    except Exception as error:
        notification_state_error = _combine_state_errors(
            notification_state_error,
            _bounded_error(error),
        )

    return DeliveryBatchResult(
        created_count=created_count,
        already_present_count=already_present_count,
        failed_count=failed_count,
        pending_count=pending_count,
        first_error=first_error,
        notification_pending=(
            any(result.notification_pending for result in notification_results)
            or bool(summary_result and summary_result.notification_pending)
        ),
        notification_error=(
            next(
                (
                    result.notification_error
                    for result in notification_results
                    if result.notification_error is not None
                ),
                None,
            )
            or (summary_result.notification_error if summary_result else None)
        ),
        notification_state_error=notification_state_error,
    )


def _combine_state_errors(existing: str | None, added: str) -> str:
    return added if existing is None else f"{existing}; {added}"


def _acknowledge_absent_delivery_confirmations(config: DeliveryConfig) -> None:
    activity = load_delivery_activity(config.state_dir)
    absent_ids: list[str] = []
    for item_id in activity.unremoved_confirmed_item_ids:
        pending_item = (
            config.outbox_dir
            / "pending"
            / "database-backups"
            / item_id
        )
        try:
            pending_item.lstat()
        except FileNotFoundError:
            absent_ids.append(item_id)
    if absent_ids:
        acknowledge_confirmed_delivery_items(
            tuple(absent_ids),
            state_dir=config.state_dir,
        )


def _validate_fixed_destination(config: DeliveryConfig) -> None:
    if (
        config.webdav_base_url != DEFAULT_WEBDAV_BASE_URL
        or config.webdav_root != DEFAULT_WEBDAV_ROOT
    ):
        raise ValueError("WebDAV destination must match the fixed Task 25 destination.")


def _queue_health_error(entry: QueueEntry) -> str:
    return _bounded_error(
        ValueError(f"Queue health issue ({entry.kind}): {entry.path.name}")
    )


def _append_secondary_error(
    primary: str | None, label: str, secondary: Exception
) -> str:
    prefix = primary or "Artifact delivery failed."
    return _bounded_error(RuntimeError(f"{prefix}; {label}: {_bounded_error(secondary)}"))


def _validate_artifact_for_upload(
    artifact: QueuedArtifact, config: DeliveryConfig
) -> None:
    _validate_artifact_identity(artifact)
    validated = load_queued_artifact(
        artifact.item_dir,
        outbox_dir=config.outbox_dir,
    )
    if validated != artifact:
        raise ValueError("Artifact object does not match validated queue metadata.")


def _validate_artifact_identity(artifact: QueuedArtifact) -> None:
    if artifact.category not in CATEGORY_REMOTE_FOLDERS:
        raise ValueError("Artifact category is not allowlisted.")
    suffix = CATEGORY_SUFFIXES[artifact.category]
    if not artifact.remote_filename.endswith(suffix):
        raise ValueError("Artifact remote filename has the wrong suffix.")
    if not has_matching_content_identity(artifact):
        raise ValueError(
            "Artifact remote filename lacks its matching content identity."
        )


def _remote_url(artifact: QueuedArtifact, config: DeliveryConfig) -> str:
    segments = (
        *_remote_directory_segments(artifact, config),
        artifact.remote_filename,
    )
    quoted_path = "/".join(quote(segment, safe="") for segment in segments)
    return f"{config.webdav_base_url}/{quoted_path}"


def _remote_collection_url(artifact: QueuedArtifact, config: DeliveryConfig) -> str:
    quoted_path = "/".join(
        quote(segment, safe="")
        for segment in _remote_directory_segments(artifact, config)
    )
    return f"{config.webdav_base_url}/{quoted_path}"


def _remote_directory_segments(
    artifact: QueuedArtifact, config: DeliveryConfig
) -> tuple[str, ...]:
    segments = (*config.webdav_root, CATEGORY_REMOTE_FOLDERS[artifact.category])
    if artifact.category != "database-backups":
        return segments
    try:
        queued_at = datetime.strptime(
            artifact.queued_at_utc,
            "%Y-%m-%dT%H:%M:%SZ",
        ).replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError("Database backup queue date is invalid.") from error
    daily_segment = queued_at.astimezone(ZoneInfo("Europe/Sofia")).date().isoformat()
    return (*segments, daily_segment)


def _bounded_error(error: Exception) -> str:
    text = " ".join(str(error).split())
    return text[:500] or error.__class__.__name__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deliver pending Task 25 artifacts with conditional WebDAV create."
    )
    parser.add_argument("command", choices=("deliver",))
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    try:
        result = deliver_pending(default_delivery_config())
    except Exception as error:
        print(f"Artifact delivery failed: {_bounded_error(error)}")
        return 1
    print(
        "Artifact delivery result: "
        f"created={result.created_count} "
        f"already_present={result.already_present_count} "
        f"failed={result.failed_count} pending={result.pending_count}"
    )
    if result.first_error:
        print(f"Delivery error: {result.first_error}")
    if result.notification_state_error:
        print(f"Notification state error: {result.notification_state_error}")
    return 1 if result.failed_count or result.notification_state_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
