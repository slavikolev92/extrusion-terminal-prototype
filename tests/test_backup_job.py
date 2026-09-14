from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from app import db
from app.backup_job import BackupJobError, main, run_backup_job
from app.backups import BackupResult


class RecordingSender:
    def __init__(self):
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)


def create_sample_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES ('preserved')")


def test_backup_job_creates_retains_and_queues_safe_image(tmp_path: Path):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)

    result = run_backup_job(
        source_db_path=source,
        backup_dir=tmp_path / "backups",
        outbox_dir=tmp_path / "outbox",
        state_dir=tmp_path / "state",
        notifier=RecordingSender(),
    )

    assert source.resolve() != db.DB_PATH.resolve()
    assert result.backup_path.exists()
    assert result.queued_artifact.category == "database-backups"
    assert result.queued_artifact.payload_path.exists()
    with sqlite3.connect(result.backup_path) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "preserved"


def test_backup_job_passes_keep_count_144_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)
    backup = tmp_path / "backups" / "created.sqlite3"
    backup.parent.mkdir()
    backup.write_bytes(source.read_bytes())
    captured: dict[str, object] = {}

    def fake_create_backup(*, source_db_path, backup_dir, keep_count):
        captured["keep_count"] = keep_count
        return BackupResult(
            source_path=Path(source_db_path),
            backup_path=backup,
            retained_paths=(backup,),
            removed_paths=(),
        )

    monkeypatch.setattr("app.backup_job.create_backup", fake_create_backup)

    run_backup_job(
        source_db_path=source,
        backup_dir=backup.parent,
        outbox_dir=tmp_path / "outbox",
        state_dir=tmp_path / "state",
        notifier=RecordingSender(),
    )

    assert captured["keep_count"] == 144


def test_backup_failure_enqueues_nothing_and_reports_component_failure(
    tmp_path: Path,
):
    sender = RecordingSender()
    outbox = tmp_path / "outbox"

    with pytest.raises(BackupJobError):
        run_backup_job(
            source_db_path=tmp_path / "missing.sqlite3",
            backup_dir=tmp_path / "backups",
            outbox_dir=outbox,
            state_dir=tmp_path / "state",
            notifier=sender,
        )

    assert not outbox.exists()
    assert len(sender.messages) == 1
    assert "database-backup FAILED" in sender.messages[0]


def test_enqueue_failure_preserves_validated_local_backup_and_reports_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)
    sender = RecordingSender()

    def fail_enqueue(*_args, **_kwargs):
        raise OSError("outbox unavailable")

    monkeypatch.setattr("app.backup_job.enqueue_artifact", fail_enqueue)

    with pytest.raises(BackupJobError, match="outbox unavailable"):
        run_backup_job(
            source_db_path=source,
            backup_dir=tmp_path / "backups",
            outbox_dir=tmp_path / "outbox",
            state_dir=tmp_path / "state",
            notifier=sender,
        )

    backups = tuple((tmp_path / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert len(sender.messages) == 1
    assert "FAILED" in sender.messages[0]


def test_next_success_sends_one_recovery(tmp_path: Path):
    sender = RecordingSender()
    state_dir = tmp_path / "state"
    with pytest.raises(BackupJobError):
        run_backup_job(
            source_db_path=tmp_path / "missing.sqlite3",
            backup_dir=tmp_path / "backups",
            outbox_dir=tmp_path / "outbox",
            state_dir=state_dir,
            notifier=sender,
        )
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)

    run_backup_job(
        source_db_path=source,
        backup_dir=tmp_path / "backups",
        outbox_dir=tmp_path / "outbox",
        state_dir=state_dir,
        notifier=sender,
    )

    assert len(sender.messages) == 2
    assert "FAILED" in sender.messages[0]
    assert "RECOVERED" in sender.messages[1]


def test_backup_job_has_no_raw_live_database_copy():
    source = inspect.getsource(__import__("app.backup_job", fromlist=["*"]))

    assert "shutil" not in source
    assert "copyfile(" not in source
    assert "copy2(" not in source


def test_cli_returns_nonzero_for_backup_failure(monkeypatch: pytest.MonkeyPatch):
    def fail_job(**_kwargs):
        raise BackupJobError("simulated failure")

    monkeypatch.setattr("app.backup_job.run_backup_job", fail_job)

    assert main([]) == 1


def test_successful_backup_reports_notification_state_failure_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)

    def fail_success_state(*_args, **_kwargs):
        raise ValueError("notification state is corrupt")

    monkeypatch.setattr("app.backup_job.record_component_success", fail_success_state)

    result = run_backup_job(
        source_db_path=source,
        backup_dir=tmp_path / "backups",
        outbox_dir=tmp_path / "outbox",
        state_dir=tmp_path / "state",
        notifier=RecordingSender(),
    )

    assert result.backup_path.exists()
    assert result.queued_artifact.payload_path.exists()
    assert result.notification_state_error == "notification state is corrupt"
