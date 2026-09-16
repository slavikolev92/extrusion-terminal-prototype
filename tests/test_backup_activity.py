from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from app.backup_activity import (
    BACKUP_ACTIVITY_FILENAME,
    BACKUP_HANDOFF_FILENAME,
    DELIVERY_ACTIVITY_FILENAME,
    BackupActivity,
    BackupHandoff,
    DeliveryActivity,
    acknowledge_confirmed_delivery_items,
    begin_backup_handoff,
    clear_backup_handoff,
    load_backup_activity,
    load_backup_handoff,
    load_delivery_activity,
    record_backup_handoff_validation,
    record_backup_failure,
    record_backup_success,
    record_delivery_run,
    remote_backup_basename,
    sha256_file,
)


T0 = datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 9, 15, 6, 10, tzinfo=timezone.utc)
T2 = datetime(2026, 9, 15, 6, 20, tzinfo=timezone.utc)
DIGEST_A = sha256(b"a").hexdigest()
DIGEST_B = sha256(b"b").hexdigest()


def test_missing_backup_activity_is_never_run(tmp_path: Path):
    assert load_backup_activity(tmp_path) == BackupActivity(
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


def test_changed_then_unchanged_success_advances_checks_only(tmp_path: Path):
    first = record_backup_success(
        DIGEST_A,
        changed=True,
        state_dir=tmp_path,
        now=T0,
    )
    second = record_backup_success(
        DIGEST_A,
        changed=False,
        state_dir=tmp_path,
        now=T1,
    )

    assert first.changed_versions_total == 1
    assert second == BackupActivity(
        status="healthy",
        last_attempt_at_utc="2026-09-15T06:10:00Z",
        last_successful_check_at_utc="2026-09-15T06:10:00Z",
        last_change_at_utc="2026-09-15T06:00:00Z",
        last_validated_sha256=DIGEST_A,
        last_observation_id=None,
        successful_checks_total=2,
        failed_checks_total=0,
        changed_versions_total=1,
    )
    assert load_backup_activity(tmp_path) == second


def test_failure_then_changed_success_preserves_monotonic_counters(tmp_path: Path):
    record_backup_success(DIGEST_A, changed=True, state_dir=tmp_path, now=T0)
    failed = record_backup_failure(state_dir=tmp_path, now=T1)
    recovered = record_backup_success(
        DIGEST_B,
        changed=True,
        state_dir=tmp_path,
        now=T2,
    )

    assert failed.status == "failing"
    assert failed.last_successful_check_at_utc == "2026-09-15T06:00:00Z"
    assert failed.failed_checks_total == 1
    assert recovered.status == "healthy"
    assert recovered.successful_checks_total == 2
    assert recovered.failed_checks_total == 1
    assert recovered.changed_versions_total == 2
    assert recovered.last_validated_sha256 == DIGEST_B


@pytest.mark.parametrize("bad_digest", ["", "a" * 63, "A" * 64, "g" * 64])
def test_success_rejects_invalid_complete_digest(tmp_path: Path, bad_digest: str):
    with pytest.raises(ValueError, match="SHA-256"):
        record_backup_success(
            bad_digest,
            changed=True,
            state_dir=tmp_path,
            now=T0,
        )


@pytest.mark.parametrize("kind", ["malformed", "oversized", "symlink"])
def test_backup_activity_rejects_untrusted_state(tmp_path: Path, kind: str):
    state_path = tmp_path / BACKUP_ACTIVITY_FILENAME
    if kind == "malformed":
        state_path.write_text("{invalid", encoding="utf-8")
    elif kind == "oversized":
        state_path.write_bytes(b"{" + (b" " * 20_000))
    else:
        target = tmp_path / "outside.json"
        target.write_text("{}", encoding="utf-8")
        state_path.symlink_to(target)

    with pytest.raises(ValueError):
        load_backup_activity(tmp_path)


def test_backup_activity_rejects_more_changes_than_successful_checks(
    tmp_path: Path,
):
    record_backup_success(DIGEST_A, changed=True, state_dir=tmp_path, now=T0)
    state_path = tmp_path / BACKUP_ACTIVITY_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["changed_versions_total"] = 2
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="counters are inconsistent"):
        load_backup_activity(tmp_path)


def test_state_replace_failure_preserves_previous_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    record_backup_success(DIGEST_A, changed=True, state_dir=tmp_path, now=T0)
    state_path = tmp_path / BACKUP_ACTIVITY_FILENAME
    original = state_path.read_bytes()

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("simulated activity replace failure")

    monkeypatch.setattr("app.backup_activity.os.replace", fail_replace)
    with pytest.raises(OSError, match="activity replace failure"):
        record_backup_success(
            DIGEST_A,
            changed=False,
            state_dir=tmp_path,
            now=T1,
        )

    assert state_path.read_bytes() == original


def test_sha256_file_hashes_the_real_file(tmp_path: Path):
    source = tmp_path / "backup.sqlite3"
    source.write_bytes(b"validated backup")

    assert sha256_file(source) == sha256(b"validated backup").hexdigest()


def test_sha256_file_rejects_a_symlink(tmp_path: Path):
    target = tmp_path / "target.sqlite3"
    target.write_bytes(b"validated backup")
    link = tmp_path / "backup.sqlite3"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="regular file"):
        sha256_file(link)


def test_remote_backup_basename_uses_sofia_civil_time():
    assert remote_backup_basename(T0) == (
        "extrusion-terminal_2026-09-15_09-00-00.sqlite3"
    )


def test_remote_backup_basename_rejects_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        remote_backup_basename(datetime(2026, 9, 15, 9, 0))


def test_remote_backup_basename_distinguishes_repeated_sofia_hour():
    first = datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
    second = datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)

    assert remote_backup_basename(first) == (
        "extrusion-terminal_2026-10-25_03-30-00_utc+03-00.sqlite3"
    )
    assert remote_backup_basename(second) == (
        "extrusion-terminal_2026-10-25_03-30-00_utc+02-00.sqlite3"
    )


def test_activity_file_has_exact_schema(tmp_path: Path):
    record_backup_success(DIGEST_A, changed=True, state_dir=tmp_path, now=T0)

    state = json.loads(
        (tmp_path / BACKUP_ACTIVITY_FILENAME).read_text(encoding="utf-8")
    )

    assert state == {
        "schema_version": 2,
        "status": "healthy",
        "last_attempt_at_utc": "2026-09-15T06:00:00Z",
        "last_successful_check_at_utc": "2026-09-15T06:00:00Z",
        "last_change_at_utc": "2026-09-15T06:00:00Z",
        "last_validated_sha256": DIGEST_A,
        "last_observation_id": None,
        "successful_checks_total": 1,
        "failed_checks_total": 0,
        "changed_versions_total": 1,
    }


def test_backup_activity_rejects_boolean_schema_version(tmp_path: Path):
    record_backup_success(DIGEST_A, changed=True, state_dir=tmp_path, now=T0)
    state_path = tmp_path / BACKUP_ACTIVITY_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["schema_version"] = True
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="version"):
        load_backup_activity(tmp_path)


def test_backup_handoff_round_trip_and_validation(tmp_path: Path):
    handoff = begin_backup_handoff(
        "extrusion_terminal_20260915_060000_000000.sqlite3",
        state_dir=tmp_path,
        now=T0,
    )

    assert load_backup_handoff(tmp_path) == handoff
    validated = record_backup_handoff_validation(
        handoff,
        DIGEST_A,
        changed=True,
        state_dir=tmp_path,
    )
    assert validated == BackupHandoff(
        observation_id=handoff.observation_id,
        started_at_utc="2026-09-15T06:00:00Z",
        backup_filename="extrusion_terminal_20260915_060000_000000.sqlite3",
        remote_basename="extrusion-terminal_2026-09-15_09-00-00.sqlite3",
        queue_item_id=handoff.queue_item_id,
        validated_sha256=DIGEST_A,
        database_changed=True,
    )
    clear_backup_handoff(validated, state_dir=tmp_path)

    assert load_backup_handoff(tmp_path) is None
    assert not (tmp_path / BACKUP_HANDOFF_FILENAME).exists()


def test_backup_handoff_file_has_exact_schema(tmp_path: Path):
    handoff = begin_backup_handoff(
        "extrusion_terminal_20260915_060000_000000.sqlite3",
        state_dir=tmp_path,
        now=T0,
    )

    state = json.loads(
        (tmp_path / BACKUP_HANDOFF_FILENAME).read_text(encoding="utf-8")
    )

    assert state == {
        "schema_version": 1,
        "observation_id": handoff.observation_id,
        "started_at_utc": "2026-09-15T06:00:00Z",
        "backup_filename": "extrusion_terminal_20260915_060000_000000.sqlite3",
        "remote_basename": "extrusion-terminal_2026-09-15_09-00-00.sqlite3",
        "queue_item_id": handoff.queue_item_id,
        "validated_sha256": None,
        "database_changed": None,
    }


def test_delivery_failure_opens_incident_and_counts_same_run_uploads(
    tmp_path: Path,
):
    transition = record_delivery_run(
        confirmed_uploads=2,
        latest_backup_queued_at_utc="2026-09-15T05:50:00Z",
        failed=True,
        pending_count=3,
        state_dir=tmp_path,
        now=T0,
    )

    assert transition.recovered is False
    assert transition.recovered_upload_count == 0
    assert transition.activity == DeliveryActivity(
        status="failing",
        last_attempt_at_utc="2026-09-15T06:00:00Z",
        last_successful_run_at_utc=None,
        last_confirmed_upload_at_utc="2026-09-15T06:00:00Z",
        last_confirmed_backup_queued_at_utc="2026-09-15T05:50:00Z",
        confirmed_uploads_total=2,
        failed_runs_total=1,
        active_incident_upload_count=2,
        unremoved_confirmed_item_ids=(),
    )


def test_delivery_partial_drain_stays_failing_until_queue_is_empty(tmp_path: Path):
    record_delivery_run(
        confirmed_uploads=1,
        latest_backup_queued_at_utc="2026-09-15T05:50:00Z",
        failed=True,
        pending_count=30,
        state_dir=tmp_path,
        now=T0,
    )
    partial = record_delivery_run(
        confirmed_uploads=25,
        latest_backup_queued_at_utc="2026-09-15T06:00:00Z",
        failed=False,
        pending_count=5,
        state_dir=tmp_path,
        now=T1,
    )
    recovered = record_delivery_run(
        confirmed_uploads=5,
        latest_backup_queued_at_utc="2026-09-15T06:10:00Z",
        failed=False,
        pending_count=0,
        state_dir=tmp_path,
        now=T2,
    )

    assert partial.activity.status == "failing"
    assert partial.activity.active_incident_upload_count == 26
    assert partial.recovered is False
    assert recovered.activity.status == "healthy"
    assert recovered.activity.confirmed_uploads_total == 31
    assert recovered.activity.active_incident_upload_count == 0
    assert recovered.recovered is True
    assert recovered.recovered_upload_count == 31


def test_healthy_empty_delivery_poll_does_not_invent_an_upload(tmp_path: Path):
    transition = record_delivery_run(
        confirmed_uploads=0,
        latest_backup_queued_at_utc=None,
        failed=False,
        pending_count=0,
        state_dir=tmp_path,
        now=T0,
    )

    assert transition.recovered is False
    assert transition.activity.status == "healthy"
    assert transition.activity.confirmed_uploads_total == 0
    assert transition.activity.last_confirmed_upload_at_utc is None


def test_delivery_activity_file_has_exact_schema(tmp_path: Path):
    record_delivery_run(
        confirmed_uploads=1,
        latest_backup_queued_at_utc="2026-09-15T05:50:00Z",
        failed=False,
        pending_count=0,
        state_dir=tmp_path,
        now=T0,
    )

    state = json.loads(
        (tmp_path / DELIVERY_ACTIVITY_FILENAME).read_text(encoding="utf-8")
    )

    assert state == {
        "schema_version": 2,
        "status": "healthy",
        "last_attempt_at_utc": "2026-09-15T06:00:00Z",
        "last_successful_run_at_utc": "2026-09-15T06:00:00Z",
        "last_confirmed_upload_at_utc": "2026-09-15T06:00:00Z",
        "last_confirmed_backup_queued_at_utc": "2026-09-15T05:50:00Z",
        "confirmed_uploads_total": 1,
        "failed_runs_total": 0,
        "active_incident_upload_count": 0,
        "unremoved_confirmed_item_ids": [],
    }


def test_missing_delivery_activity_is_never_run(tmp_path: Path):
    assert load_delivery_activity(tmp_path) == DeliveryActivity(
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


def test_delivery_activity_rejects_boolean_schema_version(tmp_path: Path):
    record_delivery_run(
        confirmed_uploads=0,
        latest_backup_queued_at_utc=None,
        failed=False,
        pending_count=0,
        state_dir=tmp_path,
        now=T0,
    )
    state_path = tmp_path / DELIVERY_ACTIVITY_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["schema_version"] = True
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="version"):
        load_delivery_activity(tmp_path)


def test_healthy_delivery_activity_rejects_an_active_incident_count(
    tmp_path: Path,
):
    record_delivery_run(
        confirmed_uploads=0,
        latest_backup_queued_at_utc=None,
        failed=False,
        pending_count=0,
        state_dir=tmp_path,
        now=T0,
    )
    state_path = tmp_path / DELIVERY_ACTIVITY_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["active_incident_upload_count"] = 1
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="incident count is inconsistent"):
        load_delivery_activity(tmp_path)


def test_delivery_confirmation_id_is_counted_once_until_cleanup_acknowledged(
    tmp_path: Path,
):
    first = record_delivery_run(
        confirmed_uploads=1,
        confirmed_item_ids=("item-001",),
        latest_backup_queued_at_utc="2026-09-15T05:50:00Z",
        failed=False,
        pending_count=0,
        state_dir=tmp_path,
        now=T0,
    )
    retried = record_delivery_run(
        confirmed_uploads=1,
        confirmed_item_ids=("item-001",),
        latest_backup_queued_at_utc="2026-09-15T05:50:00Z",
        failed=False,
        pending_count=0,
        state_dir=tmp_path,
        now=T1,
    )

    assert first.activity.confirmed_uploads_total == 1
    assert first.activity.unremoved_confirmed_item_ids == ("item-001",)
    assert retried.activity.confirmed_uploads_total == 1
    assert retried.activity.last_confirmed_upload_at_utc == "2026-09-15T06:00:00Z"
    acknowledged = acknowledge_confirmed_delivery_items(
        ("item-001",),
        state_dir=tmp_path,
    )
    assert acknowledged.unremoved_confirmed_item_ids == ()


def test_delivery_latest_backup_time_never_moves_backward(tmp_path: Path):
    record_delivery_run(
        confirmed_uploads=1,
        latest_backup_queued_at_utc="2026-09-15T06:00:00Z",
        failed=False,
        pending_count=0,
        state_dir=tmp_path,
        now=T1,
    )
    later_old_upload = record_delivery_run(
        confirmed_uploads=1,
        latest_backup_queued_at_utc="2026-09-15T05:50:00Z",
        failed=False,
        pending_count=0,
        state_dir=tmp_path,
        now=T2,
    )

    assert (
        later_old_upload.activity.last_confirmed_backup_queued_at_utc
        == "2026-09-15T06:00:00Z"
    )


@pytest.mark.parametrize("kind", ["malformed", "oversized", "symlink"])
def test_delivery_activity_rejects_untrusted_state(tmp_path: Path, kind: str):
    state_path = tmp_path / DELIVERY_ACTIVITY_FILENAME
    if kind == "malformed":
        state_path.write_text("{invalid", encoding="utf-8")
    elif kind == "oversized":
        state_path.write_bytes(b"{" + (b" " * 20_000))
    else:
        target = tmp_path / "outside-delivery.json"
        target.write_text("{}", encoding="utf-8")
        state_path.symlink_to(target)

    with pytest.raises(ValueError):
        load_delivery_activity(tmp_path)


def test_delivery_state_replace_failure_preserves_previous_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    record_delivery_run(
        confirmed_uploads=1,
        latest_backup_queued_at_utc="2026-09-15T05:50:00Z",
        failed=False,
        pending_count=0,
        state_dir=tmp_path,
        now=T0,
    )
    state_path = tmp_path / DELIVERY_ACTIVITY_FILENAME
    original = state_path.read_bytes()

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("simulated delivery activity replace failure")

    monkeypatch.setattr("app.backup_activity.os.replace", fail_replace)
    with pytest.raises(OSError, match="delivery activity replace failure"):
        record_delivery_run(
            confirmed_uploads=0,
            latest_backup_queued_at_utc=None,
            failed=False,
            pending_count=0,
            state_dir=tmp_path,
            now=T1,
        )

    assert state_path.read_bytes() == original
