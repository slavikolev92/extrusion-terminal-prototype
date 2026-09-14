from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import quote

from .artifact_outbox import (
    CATEGORY_REMOTE_FOLDERS,
    CATEGORY_SUFFIXES,
    CleanupResult,
    DEFAULT_OUTBOX_DIR,
    QueueEntry,
    QueuedArtifact,
    load_queued_artifact,
    quarantine_queue_entry,
    reap_delivered_cleanup,
    remove_delivered_artifact,
    snapshot_queue_entries,
)
from .curl_transport import CurlRunner, run_curl, validate_curl_config
from .pipeline_notifications import (
    DEFAULT_DISCORD_CURL_CONFIG,
    DEFAULT_STATE_DIR,
    DiscordWebhookSender,
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
    "production-data",
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
    elif http_status == 412 and _has_complete_checksum_name(artifact):
        state = "already-present"
    else:
        raise WebDAVDeliveryError(
            f"WebDAV conditional create returned unexpected HTTP {http_status}."
        )

    remove_delivered_artifact(artifact)
    return UploadResult(state=state, http_status=http_status, remote_url=remote_url)


def deliver_pending(
    config: DeliveryConfig,
    *,
    runner: CurlRunner = run_curl,
    notifier: NotificationSender | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> DeliveryBatchResult:
    started_at = monotonic()
    created_count = 0
    already_present_count = 0
    failed_count = 0
    first_error: str | None = None
    failed_category: str | None = None
    budget_expired = False

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
        queue_snapshot = snapshot_queue_entries(
            config.outbox_dir,
            max_entries=MAX_DELIVERY_ITEMS_PER_RUN,
        )
    except Exception as error:
        queue_snapshot = None
        failed_count += 1
        if first_error is None:
            first_error = _bounded_error(error)

    for entry in queue_snapshot.entries if queue_snapshot is not None else ():
        if monotonic() - started_at >= LATEST_UPLOAD_START_SECONDS:
            budget_expired = True
            break
        if entry.kind != "pending-item":
            failed_count += 1
            if first_error is None:
                first_error = _queue_health_error(entry)
            try:
                quarantine_queue_entry(entry, outbox_dir=config.outbox_dir)
            except Exception as error:
                first_error = _append_secondary_error(
                    first_error, "quarantine failed", error
                )
            continue
        try:
            artifact = load_queued_artifact(entry.path, outbox_dir=config.outbox_dir)
        except Exception as error:
            failed_count += 1
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
        final_snapshot = snapshot_queue_entries(config.outbox_dir, max_entries=0)
        pending_count = final_snapshot.pending_count
    except Exception as error:
        pending_count = queue_snapshot.pending_count if queue_snapshot is not None else 0
        failed_count += 1
        if first_error is None:
            first_error = _bounded_error(error)
    if monotonic() - started_at >= LATEST_NOTIFICATION_START_SECONDS:
        notification_sender: NotificationSender = _DeferredNotificationSender()
    else:
        notification_sender = (
            notifier
            if notifier is not None
            else DiscordWebhookSender(config.discord_curl_config)
        )
    context: dict[str, object] = {"pending_count": pending_count}
    if failed_category is not None:
        context["category"] = failed_category
    notification_result = None
    notification_state_error = None
    try:
        if failed_count:
            notification_result = record_component_failure(
                "webdav-delivery",
                first_error or "Artifact delivery failed.",
                state_dir=config.state_dir,
                notifier=notification_sender,
                context=context,
            )
        elif created_count or already_present_count or pending_count == 0:
            notification_result = record_component_success(
                "webdav-delivery",
                state_dir=config.state_dir,
                notifier=notification_sender,
                context=context,
            )
        else:
            notification_result = retry_pending_notification(
                "webdav-delivery",
                state_dir=config.state_dir,
                notifier=notification_sender,
                context=context,
            )
    except Exception as error:
        notification_state_error = _bounded_error(error)

    return DeliveryBatchResult(
        created_count=created_count,
        already_present_count=already_present_count,
        failed_count=failed_count,
        pending_count=pending_count,
        first_error=first_error,
        notification_pending=(
            notification_result.notification_pending
            if notification_result is not None
            else True
        ),
        notification_error=(
            notification_result.notification_error
            if notification_result is not None
            else None
        ),
        notification_state_error=notification_state_error,
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
    if not _has_complete_checksum_name(artifact):
        raise ValueError("Artifact remote filename lacks its complete checksum.")


def _has_complete_checksum_name(artifact: QueuedArtifact) -> bool:
    suffix = CATEGORY_SUFFIXES.get(artifact.category)
    return bool(
        suffix
        and len(artifact.sha256) == 64
        and artifact.remote_filename.endswith(
            f"__sha256-{artifact.sha256}{suffix}"
        )
    )


def _remote_url(artifact: QueuedArtifact, config: DeliveryConfig) -> str:
    segments = (
        *config.webdav_root,
        CATEGORY_REMOTE_FOLDERS[artifact.category],
        artifact.remote_filename,
    )
    quoted_path = "/".join(quote(segment, safe="") for segment in segments)
    return f"{config.webdav_base_url}/{quoted_path}"


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
        "Artifact delivery complete: "
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
