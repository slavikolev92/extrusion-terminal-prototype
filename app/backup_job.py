from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .artifact_outbox import (
    CATEGORY_SUFFIXES,
    DEFAULT_OUTBOX_DIR,
    QueueEntry,
    QueuedArtifact,
    content_identity_filename,
    enqueue_artifact,
    load_queued_artifact,
    quarantine_queue_entry,
)
from .backup_activity import (
    BackupHandoff,
    begin_backup_handoff,
    clear_backup_handoff,
    load_backup_activity,
    load_backup_handoff,
    record_backup_handoff_validation,
    record_backup_failure,
    record_backup_success,
    sha256_file,
)
from .backups import (
    DEFAULT_BACKUP_KEEP_COUNT,
    apply_retention,
    create_backup,
    next_backup_path,
    resolve_backup_dir,
    validate_sqlite_database,
)
from .pipeline_notifications import (
    NotificationSender,
    record_component_failure,
    record_component_success,
)


_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


class BackupJobError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupJobResult:
    backup_path: Path
    queued_artifact: QueuedArtifact | None
    database_changed: bool
    retained_paths: tuple[Path, ...]
    removed_paths: tuple[Path, ...]
    stale_staging_paths: tuple[Path, ...]
    notification_pending: bool = False
    notification_error: str | None = None
    notification_state_error: str | None = None


def run_backup_job(
    *,
    source_db_path: Path | str | None = None,
    backup_dir: Path | str | None = None,
    outbox_dir: Path | str | None = None,
    keep_count: int = DEFAULT_BACKUP_KEEP_COUNT,
    notifier: NotificationSender | None = None,
    state_dir: Path | str | None = None,
    now: datetime | None = None,
) -> BackupJobResult:
    run_time = now if now is not None else datetime.now(timezone.utc)
    if run_time.tzinfo is None or run_time.utcoffset() is None:
        raise ValueError("Backup job timestamp must be timezone-aware.")
    run_time = run_time.astimezone(timezone.utc).replace(microsecond=0)
    backup_path = None
    stale_staging_paths: tuple[Path, ...] = ()
    try:
        resolved_backup_dir = resolve_backup_dir(backup_dir)
        handoff = load_backup_handoff(state_dir)
        if handoff is None:
            backup_path = next_backup_path(resolved_backup_dir, run_time)
            handoff = begin_backup_handoff(
                backup_path.name,
                state_dir=state_dir,
                now=run_time,
            )
        else:
            backup_path = resolved_backup_dir / handoff.backup_filename
        handoff_time = _parse_utc_timestamp(handoff.started_at_utc)

        if backup_path.exists():
            validate_sqlite_database(backup_path)
        else:
            if handoff.validated_sha256 is not None:
                raise FileNotFoundError(
                    f"Validated backup handoff image is missing: {backup_path}"
                )
            backup_result = create_backup(
                source_db_path=source_db_path,
                backup_dir=resolved_backup_dir,
                keep_count=keep_count,
                timestamp=handoff_time,
                apply_retention_policy=False,
            )
            if backup_result.backup_path != backup_path:
                raise RuntimeError("Backup handoff image path changed unexpectedly.")
            stale_staging_paths = backup_result.stale_staging_paths

        digest = sha256_file(backup_path)
        if handoff.validated_sha256 is None:
            previous_activity = load_backup_activity(state_dir)
            database_changed = digest != previous_activity.last_validated_sha256
            handoff = record_backup_handoff_validation(
                handoff,
                digest,
                changed=database_changed,
                state_dir=state_dir,
            )
        else:
            if digest != handoff.validated_sha256:
                raise ValueError("Validated backup handoff image checksum changed.")
            assert handoff.database_changed is not None
            database_changed = handoff.database_changed

        queued = (
            _ensure_handoff_artifact(
                handoff,
                backup_path=backup_path,
                outbox_dir=outbox_dir,
            )
            if database_changed
            else None
        )
        record_backup_success(
            digest,
            changed=database_changed,
            state_dir=state_dir,
            now=run_time,
            observation_id=handoff.observation_id,
        )
        retained_paths, removed_paths = apply_retention(resolved_backup_dir, keep_count)
        clear_backup_handoff(handoff, state_dir=state_dir)
    except Exception as error:
        bounded_error = _bounded_error(error)
        try:
            record_backup_failure(state_dir=state_dir, now=run_time)
        except Exception as activity_error:
            bounded_error = (
                f"{bounded_error}; backup activity state also failed: "
                f"{_bounded_error(activity_error)}"
            )
        context: dict[str, object] = {}
        if backup_path is not None:
            context["backup"] = backup_path.name
        try:
            record_component_failure(
                "database-backup",
                bounded_error,
                state_dir=state_dir,
                notifier=notifier,
                now=run_time,
                context=context,
            )
        except Exception as notification_error:
            raise BackupJobError(
                f"{bounded_error}; notification state also failed: "
                f"{_bounded_error(notification_error)}"
            ) from error
        raise BackupJobError(bounded_error) from error

    notification_result = None
    notification_state_error = None
    try:
        notification_result = record_component_success(
            "database-backup",
            state_dir=state_dir,
            notifier=notifier,
            now=run_time,
            context={"backup": backup_path.name},
        )
    except Exception as error:
        notification_state_error = _bounded_error(error)
    return BackupJobResult(
        backup_path=backup_path,
        queued_artifact=queued,
        database_changed=database_changed,
        retained_paths=retained_paths,
        removed_paths=removed_paths,
        stale_staging_paths=stale_staging_paths,
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


def _ensure_handoff_artifact(
    handoff: BackupHandoff,
    *,
    backup_path: Path,
    outbox_dir: Path | str | None,
) -> QueuedArtifact:
    if handoff.validated_sha256 is None or handoff.database_changed is not True:
        raise ValueError("Changed backup handoff is not validated.")
    outbox = (
        Path(outbox_dir).resolve()
        if outbox_dir is not None
        else DEFAULT_OUTBOX_DIR.resolve()
    )
    pending_item = outbox / "pending" / "database-backups" / handoff.queue_item_id
    if _path_entry_exists(pending_item):
        artifact = load_queued_artifact(pending_item, outbox_dir=outbox)
        _validate_handoff_artifact(artifact, handoff)
        return artifact

    staging_item = outbox / "staging" / handoff.queue_item_id
    if _path_entry_exists(staging_item):
        quarantine_queue_entry(
            QueueEntry(staging_item, "stale-staging"),
            outbox_dir=outbox,
        )
    artifact = enqueue_artifact(
        backup_path,
        "database-backups",
        outbox_dir=outbox,
        remote_basename=handoff.remote_basename,
        now=_parse_utc_timestamp(handoff.started_at_utc),
        item_id=handoff.queue_item_id,
    )
    _validate_handoff_artifact(artifact, handoff)
    return artifact


def _validate_handoff_artifact(
    artifact: QueuedArtifact,
    handoff: BackupHandoff,
) -> None:
    suffix = CATEGORY_SUFFIXES["database-backups"]
    expected_name = content_identity_filename(
        handoff.remote_basename,
        suffix,
        handoff.validated_sha256 or "",
    )
    if (
        artifact.sha256 != handoff.validated_sha256
        or artifact.remote_filename != expected_name
        or artifact.queued_at_utc != handoff.started_at_utc
    ):
        raise ValueError("Queued artifact conflicts with backup handoff state.")


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _parse_utc_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )


def _bounded_error(error: Exception) -> str:
    text = _URL_PATTERN.sub("[url-redacted]", str(error))
    text = " ".join(text.split())
    return text[:500] or error.__class__.__name__


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description="Create, validate, retain, and queue one SQLite backup."
    )


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    try:
        result = run_backup_job()
    except Exception as error:
        print(f"Database backup job failed: {_bounded_error(error)}")
        return 1
    action = (
        "Queued changed database backup"
        if result.database_changed
        else "Database backup validated; content unchanged and not queued"
    )
    print(
        f"{action}: {result.backup_path.name}; "
        f"retained={len(result.retained_paths)} removed={len(result.removed_paths)} "
        f"stale_staging={len(result.stale_staging_paths)}"
    )
    if result.notification_state_error:
        print(f"Notification state error: {result.notification_state_error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
