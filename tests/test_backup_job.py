from __future__ import annotations

import inspect
import sqlite3
from hashlib import sha256
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import db
from app.backup_activity import BACKUP_ACTIVITY_FILENAME, load_backup_activity
from app.backup_job import BackupJobError, main, run_backup_job
from app.backups import BackupResult, next_backup_path


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
    assert result.database_changed is True
    assert result.queued_artifact is not None
    assert result.queued_artifact.category == "database-backups"
    assert result.queued_artifact.payload_path.exists()
    with sqlite3.connect(result.backup_path) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "preserved"


def test_backup_job_passes_keep_count_144_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)
    backup_dir = tmp_path / "backups"
    captured: dict[str, object] = {}

    def fake_create_backup(
        *,
        source_db_path,
        backup_dir,
        keep_count,
        timestamp,
        apply_retention_policy,
    ):
        captured["keep_count"] = keep_count
        captured["timestamp"] = timestamp
        captured["apply_retention_policy"] = apply_retention_policy
        backup = next_backup_path(Path(backup_dir), timestamp)
        backup.parent.mkdir(exist_ok=True)
        backup.write_bytes(source.read_bytes())
        return BackupResult(
            source_path=Path(source_db_path),
            backup_path=backup,
            retained_paths=(),
            removed_paths=(),
        )

    monkeypatch.setattr("app.backup_job.create_backup", fake_create_backup)

    run_backup_job(
        source_db_path=source,
        backup_dir=backup_dir,
        outbox_dir=tmp_path / "outbox",
        state_dir=tmp_path / "state",
        notifier=RecordingSender(),
    )

    assert captured["keep_count"] == 144
    assert isinstance(captured["timestamp"], datetime)
    assert captured["apply_retention_policy"] is False


def test_unchanged_database_is_validated_but_not_queued_twice(tmp_path: Path):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)
    state_dir = tmp_path / "state"
    outbox = tmp_path / "outbox"
    t0 = datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc)

    first = run_backup_job(
        source_db_path=source,
        backup_dir=tmp_path / "backups",
        outbox_dir=outbox,
        state_dir=state_dir,
        notifier=RecordingSender(),
        now=t0,
    )
    second = run_backup_job(
        source_db_path=source,
        backup_dir=tmp_path / "backups",
        outbox_dir=outbox,
        state_dir=state_dir,
        notifier=RecordingSender(),
        now=t0 + timedelta(minutes=10),
    )

    assert first.database_changed is True
    assert first.queued_artifact is not None
    assert second.database_changed is False
    assert second.queued_artifact is None
    assert len(tuple((tmp_path / "backups").glob("*.sqlite3"))) == 2
    assert len(tuple((outbox / "pending" / "database-backups").iterdir())) == 1
    activity = load_backup_activity(state_dir)
    assert activity.successful_checks_total == 2
    assert activity.changed_versions_total == 1
    assert activity.last_successful_check_at_utc == "2026-09-15T06:10:00Z"


def test_changed_database_queues_a_new_version(tmp_path: Path):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)
    state_dir = tmp_path / "state"
    outbox = tmp_path / "outbox"
    t0 = datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc)
    run_backup_job(
        source_db_path=source,
        backup_dir=tmp_path / "backups",
        outbox_dir=outbox,
        state_dir=state_dir,
        notifier=RecordingSender(),
        now=t0,
    )
    with sqlite3.connect(source) as connection:
        connection.execute("UPDATE sample SET value = 'changed'")

    changed = run_backup_job(
        source_db_path=source,
        backup_dir=tmp_path / "backups",
        outbox_dir=outbox,
        state_dir=state_dir,
        notifier=RecordingSender(),
        now=t0 + timedelta(minutes=10),
    )

    assert changed.database_changed is True
    assert changed.queued_artifact is not None
    assert changed.queued_artifact.remote_filename.startswith(
        "extrusion-terminal_2026-09-15_09-10-00_"
    )
    assert len(tuple((outbox / "pending" / "database-backups").iterdir())) == 2


def test_a_to_b_to_a_queues_each_observed_change(tmp_path: Path):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)
    state_dir = tmp_path / "state"
    outbox = tmp_path / "outbox"
    t0 = datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc)

    original_bytes = source.read_bytes()
    backup_digests = []
    for index in range(3):
        if index == 1:
            with sqlite3.connect(source) as connection:
                connection.execute("UPDATE sample SET value = 'changed'")
        elif index == 2:
            source.write_bytes(original_bytes)
        result = run_backup_job(
            source_db_path=source,
            backup_dir=tmp_path / "backups",
            outbox_dir=outbox,
            state_dir=state_dir,
            notifier=RecordingSender(),
            now=t0 + timedelta(minutes=10 * index),
        )
        assert result.database_changed is True
        backup_digests.append(sha256(result.backup_path.read_bytes()).hexdigest())

    pending = tuple((outbox / "pending" / "database-backups").iterdir())
    assert backup_digests[0] == backup_digests[2]
    assert backup_digests[0] != backup_digests[1]
    assert len(pending) == 3
    assert load_backup_activity(state_dir).changed_versions_total == 3


def test_malformed_activity_preserves_new_local_image_and_queues_nothing(
    tmp_path: Path,
):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / BACKUP_ACTIVITY_FILENAME).write_text("{invalid", encoding="utf-8")
    sender = RecordingSender()

    with pytest.raises(BackupJobError, match="activity state"):
        run_backup_job(
            source_db_path=source,
            backup_dir=tmp_path / "backups",
            outbox_dir=tmp_path / "outbox",
            state_dir=state_dir,
            notifier=sender,
            now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        )

    assert len(tuple((tmp_path / "backups").glob("*.sqlite3"))) == 1
    assert not (tmp_path / "outbox").exists()
    assert len(sender.messages) == 1


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
    assert "Database backup failed" in sender.messages[0]


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
    assert "Database backup failed" in sender.messages[0]


def test_failed_changed_enqueue_is_retried_before_a_later_reversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)
    original_bytes = source.read_bytes()
    state_dir = tmp_path / "state"
    outbox = tmp_path / "outbox"
    backup_dir = tmp_path / "backups"
    sender = RecordingSender()
    start = datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc)
    run_backup_job(
        source_db_path=source,
        backup_dir=backup_dir,
        outbox_dir=outbox,
        state_dir=state_dir,
        notifier=sender,
        now=start,
    )
    with sqlite3.connect(source) as connection:
        connection.execute("UPDATE sample SET value = 'changed'")
    real_enqueue = __import__(
        "app.backup_job", fromlist=["enqueue_artifact"]
    ).enqueue_artifact
    failed_once = False

    def fail_changed_once(*args, **kwargs):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise OSError("simulated outbox outage")
        return real_enqueue(*args, **kwargs)

    monkeypatch.setattr("app.backup_job.enqueue_artifact", fail_changed_once)
    with pytest.raises(BackupJobError, match="outbox outage"):
        run_backup_job(
            source_db_path=source,
            backup_dir=backup_dir,
            outbox_dir=outbox,
            state_dir=state_dir,
            notifier=sender,
            now=start + timedelta(minutes=10),
        )
    source.write_bytes(original_bytes)

    retried_b = run_backup_job(
        source_db_path=source,
        backup_dir=backup_dir,
        outbox_dir=outbox,
        state_dir=state_dir,
        notifier=sender,
        now=start + timedelta(minutes=20),
    )
    later_a = run_backup_job(
        source_db_path=source,
        backup_dir=backup_dir,
        outbox_dir=outbox,
        state_dir=state_dir,
        notifier=sender,
        now=start + timedelta(minutes=30),
    )

    assert retried_b.database_changed is True
    assert later_a.database_changed is True
    assert sha256(retried_b.backup_path.read_bytes()).hexdigest() != sha256(
        later_a.backup_path.read_bytes()
    ).hexdigest()
    assert len(tuple((outbox / "pending" / "database-backups").iterdir())) == 3
    assert load_backup_activity(state_dir).changed_versions_total == 3


def test_activity_write_failure_after_enqueue_reuses_same_queue_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)
    state_dir = tmp_path / "state"
    outbox = tmp_path / "outbox"
    backup_dir = tmp_path / "backups"
    import app.backup_job as backup_job_module

    real_record_success = backup_job_module.record_backup_success
    failed_once = False

    def fail_once(*args, **kwargs):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise OSError("simulated activity write failure")
        return real_record_success(*args, **kwargs)

    monkeypatch.setattr(backup_job_module, "record_backup_success", fail_once)
    with pytest.raises(BackupJobError, match="activity write failure"):
        run_backup_job(
            source_db_path=source,
            backup_dir=backup_dir,
            outbox_dir=outbox,
            state_dir=state_dir,
            notifier=RecordingSender(),
            now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        )
    first_items = tuple((outbox / "pending" / "database-backups").iterdir())

    recovered = run_backup_job(
        source_db_path=source,
        backup_dir=backup_dir,
        outbox_dir=outbox,
        state_dir=state_dir,
        notifier=RecordingSender(),
        now=datetime(2026, 9, 15, 6, 10, tzinfo=timezone.utc),
    )

    assert recovered.database_changed is True
    assert tuple((outbox / "pending" / "database-backups").iterdir()) == first_items
    assert load_backup_activity(state_dir).successful_checks_total == 1


def test_post_commit_failure_replay_restores_activity_without_double_counting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)
    state_dir = tmp_path / "state"
    outbox = tmp_path / "outbox"
    import app.backup_job as backup_job_module

    real_retention = backup_job_module.apply_retention
    failed_once = False

    def fail_once(*args, **kwargs):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise OSError("simulated retention failure")
        return real_retention(*args, **kwargs)

    monkeypatch.setattr(backup_job_module, "apply_retention", fail_once)
    with pytest.raises(BackupJobError, match="retention failure"):
        run_backup_job(
            source_db_path=source,
            backup_dir=tmp_path / "backups",
            outbox_dir=outbox,
            state_dir=state_dir,
            notifier=RecordingSender(),
            now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        )

    run_backup_job(
        source_db_path=source,
        backup_dir=tmp_path / "backups",
        outbox_dir=outbox,
        state_dir=state_dir,
        notifier=RecordingSender(),
        now=datetime(2026, 9, 15, 6, 10, tzinfo=timezone.utc),
    )

    activity = load_backup_activity(state_dir)
    assert activity.status == "healthy"
    assert activity.successful_checks_total == 1
    assert activity.failed_checks_total == 1
    assert activity.last_successful_check_at_utc == "2026-09-15T06:10:00Z"
    assert len(tuple((outbox / "pending" / "database-backups").iterdir())) == 1


def test_malformed_activity_does_not_prune_a_prior_local_backup(
    tmp_path: Path,
):
    source = tmp_path / "source.sqlite3"
    create_sample_database(source)
    backup_dir = tmp_path / "backups"
    state_dir = tmp_path / "state"
    run_backup_job(
        source_db_path=source,
        backup_dir=backup_dir,
        outbox_dir=tmp_path / "outbox",
        state_dir=state_dir,
        notifier=RecordingSender(),
        keep_count=1,
        now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
    )
    prior = tuple(backup_dir.glob("*.sqlite3"))
    (state_dir / BACKUP_ACTIVITY_FILENAME).write_text("{invalid", encoding="utf-8")

    with pytest.raises(BackupJobError, match="activity state"):
        run_backup_job(
            source_db_path=source,
            backup_dir=backup_dir,
            outbox_dir=tmp_path / "outbox",
            state_dir=state_dir,
            notifier=RecordingSender(),
            keep_count=1,
            now=datetime(2026, 9, 15, 6, 10, tzinfo=timezone.utc),
        )

    current = tuple(backup_dir.glob("*.sqlite3"))
    assert len(current) == 2
    assert set(prior).issubset(current)


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
    assert "Database backup failed" in sender.messages[0]
    assert "Database backup recovered" in sender.messages[1]


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
    assert result.queued_artifact is not None
    assert result.queued_artifact.payload_path.exists()
    assert result.notification_state_error == "notification state is corrupt"
