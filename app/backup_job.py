from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from .artifact_outbox import QueuedArtifact, enqueue_artifact
from .backups import DEFAULT_BACKUP_KEEP_COUNT, create_backup
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
    queued_artifact: QueuedArtifact
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
) -> BackupJobResult:
    backup_result = None
    try:
        backup_result = create_backup(
            source_db_path=source_db_path,
            backup_dir=backup_dir,
            keep_count=keep_count,
        )
        queued = enqueue_artifact(
            backup_result.backup_path,
            "database-backups",
            outbox_dir=outbox_dir,
        )
    except Exception as error:
        bounded_error = _bounded_error(error)
        context: dict[str, object] = {}
        if backup_result is not None:
            context["backup"] = backup_result.backup_path.name
        try:
            record_component_failure(
                "database-backup",
                bounded_error,
                state_dir=state_dir,
                notifier=notifier,
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
            context={"backup": backup_result.backup_path.name},
        )
    except Exception as error:
        notification_state_error = _bounded_error(error)
    return BackupJobResult(
        backup_path=backup_result.backup_path,
        queued_artifact=queued,
        retained_paths=backup_result.retained_paths,
        removed_paths=backup_result.removed_paths,
        stale_staging_paths=backup_result.stale_staging_paths,
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
    print(
        f"Queued database backup: {result.backup_path.name}; "
        f"retained={len(result.retained_paths)} removed={len(result.removed_paths)} "
        f"stale_staging={len(result.stale_staging_paths)}"
    )
    if result.notification_state_error:
        print(f"Notification state error: {result.notification_state_error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
