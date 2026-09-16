from __future__ import annotations

import json
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from app.backup_activity import (
    BACKUP_ACTIVITY_FILENAME,
    record_backup_failure,
    record_backup_success,
    record_delivery_run,
)
from app.backup_summary import (
    BACKUP_SUMMARY_STATE_FILENAME,
    BackupSummaryResult,
    check_backup_freshness,
    load_summary_times,
    maybe_send_backup_summary,
)
from app.pipeline_notifications import record_component_failure


class RecordingSender:
    def __init__(self):
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)


class FailingSender:
    def __init__(self):
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)
        raise RuntimeError("discord unavailable")


def write_config(path: Path, value: str) -> Path:
    path.write_text(f"summary_times={value}\n", encoding="ascii")
    return path


def seed_healthy_activity(state_dir: Path, now: datetime) -> None:
    record_backup_success(
        "a" * 64,
        changed=True,
        state_dir=state_dir,
        now=now,
    )
    record_delivery_run(
        confirmed_uploads=1,
        latest_backup_queued_at_utc=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        failed=False,
        pending_count=0,
        state_dir=state_dir,
        now=now,
    )


def test_missing_summary_configuration_defaults_to_nine_am(tmp_path: Path):
    assert load_summary_times(tmp_path / "missing.conf") == (time(9, 0),)


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ("summary_times=off\n", ()),
        ("summary_times=09:00\n", (time(9, 0),)),
        ("summary_times=09:00,21:00\n", (time(9, 0), time(21, 0))),
    ],
)
def test_summary_configuration_accepts_only_supported_forms(
    tmp_path: Path,
    setting: str,
    expected: tuple[time, ...],
):
    config = tmp_path / "summary.conf"
    config.write_text(setting, encoding="ascii")

    assert load_summary_times(config) == expected


@pytest.mark.parametrize(
    "setting",
    [
        "summary_times=\n",
        "summary_times=09:00\nextra=true\n",
        "summary_times=09:00,09:00\n",
        "summary_times= 09:00\n",
        "summary_times=09:00, 21:00\n",
        "summary_times=9:00\n",
        "summary_times=09:00:00\n",
        "summary_times=24:00\n",
        "summary_times=09:60\n",
        "summary_times=08:00,12:00,20:00\n",
        "other=09:00\n",
        "summary_times=OFF\n",
        "summary_times=09:00\r\n",
    ],
)
def test_summary_configuration_rejects_ambiguous_or_unsupported_forms(
    tmp_path: Path,
    setting: str,
):
    config = tmp_path / "summary.conf"
    config.write_bytes(setting.encode("ascii"))

    with pytest.raises(ValueError, match="summary configuration"):
        load_summary_times(config)


@pytest.mark.parametrize("kind", ["oversized", "symlink", "fifo", "utf8"])
def test_summary_configuration_rejects_untrusted_file(
    tmp_path: Path,
    kind: str,
):
    config = tmp_path / "summary.conf"
    if kind == "oversized":
        config.write_bytes(b"summary_times=09:00\n" + (b" " * 2_000))
    elif kind == "symlink":
        target = tmp_path / "outside.conf"
        target.write_text("summary_times=09:00\n", encoding="ascii")
        config.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(config)
    else:
        config.write_bytes(b"summary_times=09:00\n\xff")

    with pytest.raises(ValueError):
        load_summary_times(config)


def test_summary_configuration_uses_test_environment_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config = tmp_path / "summary.conf"
    config.write_text("summary_times=off\n", encoding="ascii")
    monkeypatch.setenv("EXTRUSION_BACKUP_SUMMARY_CONFIG", str(config))

    assert load_summary_times() == ()


def test_summary_configuration_module_has_no_time_or_network_side_effects():
    # Importing and parsing configuration is deliberately pure. This test also
    # keeps otherwise shared datetime imports ready for later scheduling cases.
    assert datetime(2026, 9, 15, tzinfo=timezone.utc).tzinfo is timezone.utc


def test_missing_state_arms_next_future_summary_without_sending(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "09:00")
    sender = RecordingSender()
    now = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)  # 08:00 Sofia
    seed_healthy_activity(tmp_path, now - timedelta(minutes=10))

    result = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=now,
        config_path=config,
    )

    assert result == BackupSummaryResult(
        state_path=tmp_path / BACKUP_SUMMARY_STATE_FILENAME,
        scheduled_slot=None,
        notification_attempted=False,
        notification_sent=False,
        notification_pending=False,
        notification_error=None,
    )
    assert sender.messages == []


def test_daily_summary_sends_once_at_first_invocation_after_slot(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "09:00")
    sender = RecordingSender()
    initialized = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    seed_healthy_activity(tmp_path, initialized - timedelta(minutes=10))
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=initialized,
        config_path=config,
    )

    due = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 2, tzinfo=timezone.utc),
        config_path=config,
    )
    repeated = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 3, tzinfo=timezone.utc),
        config_path=config,
    )

    assert due.scheduled_slot == "2026-09-15/09:00"
    assert due.notification_sent is True
    assert repeated.notification_attempted is False
    assert len(sender.messages) == 1
    assert "15 Sep 2026 at 09:00" in sender.messages[0]


def test_two_daily_slots_are_independent(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "09:00,21:00")
    sender = RecordingSender()
    start = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    seed_healthy_activity(tmp_path, start)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=start,
        config_path=config,
    )

    results = []
    for now in (
        datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc),
    ):
        results.append(
            maybe_send_backup_summary(
                state_dir=tmp_path,
                pending_count=0,
                notifier=sender,
                now=now,
                config_path=config,
            )
        )

    assert len(sender.messages) == 2
    assert [result.scheduled_slot for result in results] == [
        "2026-09-15/09:00",
        "2026-09-15/21:00",
    ]
    assert "09:00" in sender.messages[0]
    assert "21:00" in sender.messages[1]


def test_off_disables_summaries(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "off")
    sender = RecordingSender()

    for now in (
        datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc),
    ):
        result = maybe_send_backup_summary(
            state_dir=tmp_path,
            pending_count=0,
            notifier=sender,
            now=now,
            config_path=config,
        )
        assert result.notification_attempted is False

    assert sender.messages == []


def test_schedule_change_arms_future_instead_of_replaying_history(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "09:00")
    sender = RecordingSender()
    seed_healthy_activity(
        tmp_path, datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    )
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc),
        config_path=config,
    )

    write_config(config, "08:00")
    changed = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc),
        config_path=config,
    )
    next_day = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 9, 16, 5, 1, tzinfo=timezone.utc),
        config_path=config,
    )

    assert changed.notification_attempted is False
    assert next_day.scheduled_slot == "2026-09-16/08:00"
    assert len(sender.messages) == 1


def test_schedule_change_preserves_the_last_delivered_counter_baselines(
    tmp_path: Path,
):
    config = write_config(tmp_path / "summary.conf", "09:00")
    sender = RecordingSender()
    start = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    seed_healthy_activity(tmp_path, start)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=start,
        config_path=config,
    )
    record_backup_success(
        "a" * 64,
        changed=False,
        state_dir=tmp_path,
        now=start + timedelta(minutes=30),
    )

    write_config(config, "10:00")
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=start + timedelta(minutes=40),
        config_path=config,
    )
    record_backup_success(
        "a" * 64,
        changed=False,
        state_dir=tmp_path,
        now=start + timedelta(minutes=50),
    )
    due = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 9, 15, 7, 0, tzinfo=timezone.utc),
        config_path=config,
    )

    assert due.scheduled_slot == "2026-09-15/10:00"
    assert "Validated database checks: 2" in sender.messages[0]


def test_multi_day_downtime_sends_only_newest_due_slot(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "09:00,21:00")
    sender = RecordingSender()
    start = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    seed_healthy_activity(tmp_path, start)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=start,
        config_path=config,
    )

    result = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 9, 18, 19, 0, tzinfo=timezone.utc),
        config_path=config,
    )

    assert result.scheduled_slot == "2026-09-18/21:00"
    assert len(sender.messages) == 1


def test_repeated_dst_hour_has_one_summary_slot(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "03:30")
    sender = RecordingSender()
    # Europe/Sofia repeats 03:00-03:59 on 25 October 2026.
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 10, 24, 23, 0, tzinfo=timezone.utc),
        config_path=config,
    )
    for now in (
        datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc),
        datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc),
    ):
        maybe_send_backup_summary(
            state_dir=tmp_path,
            pending_count=0,
            notifier=sender,
            now=now,
            config_path=config,
        )

    assert len(sender.messages) == 1
    assert "25 Oct 2026 at 03:30" in sender.messages[0]


def test_initialization_between_repeated_hour_folds_does_not_replay_first_slot(
    tmp_path: Path,
):
    config = write_config(tmp_path / "summary.conf", "03:30")
    sender = RecordingSender()
    # 01:15 UTC is 03:15 in the second occurrence of Sofia's repeated hour.
    initialized = datetime(2026, 10, 25, 1, 15, tzinfo=timezone.utc)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=initialized,
        config_path=config,
    )

    result = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 10, 25, 1, 35, tzinfo=timezone.utc),
        config_path=config,
    )

    assert result.notification_attempted is False
    assert sender.messages == []


def test_skipped_dst_slot_is_due_at_first_later_invocation(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "03:30")
    sender = RecordingSender()
    # Europe/Sofia skips from 02:59 to 04:00 on 29 March 2026.
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 3, 28, 23, 0, tzinfo=timezone.utc),
        config_path=config,
    )

    result = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc),
        config_path=config,
    )

    assert result.scheduled_slot == "2026-03-29/03:30"
    assert len(sender.messages) == 1


def test_healthy_summary_has_human_counter_deltas_and_sofia_times(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "09:00")
    sender = RecordingSender()
    initialized = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    seed_healthy_activity(tmp_path, initialized)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=initialized,
        config_path=config,
    )
    record_backup_success(
        "a" * 64,
        changed=False,
        state_dir=tmp_path,
        now=datetime(2026, 9, 15, 5, 40, tzinfo=timezone.utc),
    )
    record_backup_failure(
        state_dir=tmp_path,
        now=datetime(2026, 9, 15, 5, 45, tzinfo=timezone.utc),
    )
    record_backup_success(
        "b" * 64,
        changed=True,
        state_dir=tmp_path,
        now=datetime(2026, 9, 15, 5, 50, tzinfo=timezone.utc),
    )
    record_delivery_run(
        confirmed_uploads=1,
        latest_backup_queued_at_utc="2026-09-15T05:50:00Z",
        failed=False,
        pending_count=0,
        state_dir=tmp_path,
        now=datetime(2026, 9, 15, 5, 51, tzinfo=timezone.utc),
    )

    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        config_path=config,
    )

    message = sender.messages[0]
    assert message.startswith("✅ Extrusion Terminal — Backup summary")
    assert "Validated database checks: 2" in message
    assert "Failed database checks: 1" in message
    assert "Changed database versions: 1" in message
    assert "Confirmed Hetzner uploads: 1" in message
    assert "Latest validated check: 15 Sep 2026 at 08:50" in message
    assert "Latest changed backup uploaded: 15 Sep 2026 at 08:51" in message
    assert "Waiting backups: 0" in message
    assert "Europe/Sofia" not in message
    assert "T05:" not in message
    assert "host=" not in message
    assert "http" not in message.lower()
    assert "restore" not in message.lower()


def test_counter_regression_warns_and_does_not_lower_summary_baselines(
    tmp_path: Path,
):
    config = write_config(tmp_path / "summary.conf", "09:00")
    start = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    seed_healthy_activity(tmp_path, start)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=RecordingSender(),
        now=start,
        config_path=config,
    )
    backup_path = tmp_path / BACKUP_ACTIVITY_FILENAME
    backup_state = json.loads(backup_path.read_text(encoding="utf-8"))
    backup_state["successful_checks_total"] = 0
    backup_state["changed_versions_total"] = 0
    backup_path.write_text(json.dumps(backup_state), encoding="utf-8")
    delivery_path = tmp_path / "database-delivery-activity.json"
    delivery_state = json.loads(delivery_path.read_text(encoding="utf-8"))
    delivery_state["confirmed_uploads_total"] = 0
    delivery_path.write_text(json.dumps(delivery_state), encoding="utf-8")
    sender = RecordingSender()

    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        config_path=config,
    )

    message = sender.messages[0]
    summary_state = json.loads(
        (tmp_path / BACKUP_SUMMARY_STATE_FILENAME).read_text(encoding="utf-8")
    )
    assert message.startswith(
        "⚠️ Extrusion Terminal — Backup summary needs attention"
    )
    assert "activity counters moved backwards" in message
    assert "Validated database checks: unknown" in message
    assert "Confirmed Hetzner uploads: unknown" in message
    assert summary_state["baseline_successful_checks_total"] == 1
    assert summary_state["baseline_changed_versions_total"] == 1
    assert summary_state["baseline_confirmed_uploads_total"] == 1


@pytest.mark.parametrize("condition", ["never", "malformed", "failed", "stale", "pending"])
def test_unhealthy_or_unverifiable_summary_is_a_warning(
    tmp_path: Path,
    condition: str,
):
    config = write_config(tmp_path / "summary.conf", "09:00")
    sender = RecordingSender()
    initialized = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    if condition not in {"never", "malformed"}:
        seed_healthy_activity(tmp_path, initialized)
    if condition == "malformed":
        (tmp_path / BACKUP_ACTIVITY_FILENAME).write_text("{bad", encoding="utf-8")
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=initialized,
        config_path=config,
    )
    if condition == "failed":
        record_backup_failure(
            state_dir=tmp_path,
            now=datetime(2026, 9, 15, 5, 50, tzinfo=timezone.utc),
        )
    elif condition == "stale":
        pass
    elif condition not in {"never", "malformed"}:
        record_backup_success(
            "a" * 64,
            changed=False,
            state_dir=tmp_path,
            now=datetime(2026, 9, 15, 5, 50, tzinfo=timezone.utc),
        )

    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=2 if condition == "pending" else 0,
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        config_path=config,
    )

    message = sender.messages[0]
    assert message.startswith("⚠️ Extrusion Terminal — Backup summary needs attention")
    if condition in {"never", "malformed"}:
        assert "unknown" in message
    if condition == "pending":
        assert "2 backups are still waiting" in message


def test_failed_summary_send_retries_same_message_without_advancing_baseline(
    tmp_path: Path,
):
    config = write_config(tmp_path / "summary.conf", "09:00")
    initialized = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    seed_healthy_activity(tmp_path, initialized)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=RecordingSender(),
        now=initialized,
        config_path=config,
    )
    record_backup_success(
        "a" * 64,
        changed=False,
        state_dir=tmp_path,
        now=datetime(2026, 9, 15, 5, 50, tzinfo=timezone.utc),
    )
    failing = FailingSender()
    failed = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=failing,
        now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        config_path=config,
    )
    state_after_failure = json.loads(
        (tmp_path / BACKUP_SUMMARY_STATE_FILENAME).read_text(encoding="utf-8")
    )
    record_backup_success(
        "b" * 64,
        changed=True,
        state_dir=tmp_path,
        now=datetime(2026, 9, 15, 6, 1, tzinfo=timezone.utc),
    )
    recovered_sender = RecordingSender()
    retried = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=recovered_sender,
        now=datetime(2026, 9, 15, 6, 2, tzinfo=timezone.utc),
        config_path=config,
    )
    state_after_success = json.loads(
        (tmp_path / BACKUP_SUMMARY_STATE_FILENAME).read_text(encoding="utf-8")
    )

    assert failed.notification_pending is True
    assert state_after_failure["baseline_successful_checks_total"] == 1
    assert retried.notification_sent is True
    assert recovered_sender.messages == failing.messages
    assert state_after_success["baseline_successful_checks_total"] == 2
    assert state_after_success["pending_slot"] is None


def test_urgent_notification_defers_due_summary(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "09:00")
    sender = RecordingSender()
    initialized = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    seed_healthy_activity(tmp_path, initialized)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=initialized,
        config_path=config,
    )

    deferred = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        config_path=config,
        urgent_notification_pending=True,
    )
    delivered = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 1, tzinfo=timezone.utc),
        config_path=config,
    )

    assert deferred.notification_pending is True
    assert deferred.notification_attempted is False
    assert delivered.notification_sent is True
    assert len(sender.messages) == 1


@pytest.mark.parametrize("kind", ["malformed", "oversized", "symlink"])
def test_summary_rejects_untrusted_state(tmp_path: Path, kind: str):
    state_path = tmp_path / BACKUP_SUMMARY_STATE_FILENAME
    if kind == "malformed":
        state_path.write_text("{bad", encoding="utf-8")
    elif kind == "oversized":
        state_path.write_bytes(b"{" + (b" " * 20_000))
    else:
        target = tmp_path / "outside.json"
        target.write_text("{}", encoding="utf-8")
        state_path.symlink_to(target)

    with pytest.raises(ValueError, match="summary state"):
        maybe_send_backup_summary(
            state_dir=tmp_path,
            pending_count=0,
            notifier=RecordingSender(),
            now=datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc),
            config_path=write_config(tmp_path / "summary.conf", "09:00"),
        )


def test_never_run_freshness_waits_thirty_minutes_then_alerts(tmp_path: Path):
    sender = RecordingSender()
    first = check_backup_freshness(
        state_dir=tmp_path,
        notifier=sender,
        now=datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc),
    )
    early = check_backup_freshness(
        state_dir=tmp_path,
        notifier=sender,
        now=datetime(2026, 9, 15, 5, 29, tzinfo=timezone.utc),
    )
    due = check_backup_freshness(
        state_dir=tmp_path,
        notifier=sender,
        now=datetime(2026, 9, 15, 5, 30, tzinfo=timezone.utc),
    )

    assert first is not None and first.notification_attempted is False
    assert early is not None and early.notification_attempted is False
    assert due is not None and due.notification_sent is True
    assert len(sender.messages) == 1
    assert "Database backup process appears stopped" in sender.messages[0]


def test_healthy_producer_stale_for_thirty_minutes_alerts_and_recovers(
    tmp_path: Path,
):
    sender = RecordingSender()
    last_success = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    record_backup_success(
        "a" * 64,
        changed=True,
        state_dir=tmp_path,
        now=last_success,
    )

    warning = check_backup_freshness(
        state_dir=tmp_path,
        notifier=sender,
        now=last_success + timedelta(minutes=31),
    )
    record_backup_success(
        "a" * 64,
        changed=False,
        state_dir=tmp_path,
        now=last_success + timedelta(minutes=32),
    )
    recovery = check_backup_freshness(
        state_dir=tmp_path,
        notifier=sender,
        now=last_success + timedelta(minutes=32),
    )

    assert warning is not None and warning.notification_sent is True
    assert recovery is not None and recovery.notification_sent is True
    assert len(sender.messages) == 2
    assert "last validated database check was at 15 sep 2026 at 08:00" in (
        sender.messages[0].lower()
    )
    assert "backup checks resumed" in sender.messages[1].lower()


def test_explicit_producer_failure_does_not_create_freshness_warning(tmp_path: Path):
    record_backup_failure(
        state_dir=tmp_path,
        now=datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc),
    )
    sender = RecordingSender()

    result = check_backup_freshness(
        state_dir=tmp_path,
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
    )

    assert result is None
    assert sender.messages == []


def test_explicit_producer_failure_cancels_an_unalerted_freshness_incident(
    tmp_path: Path,
):
    sender = RecordingSender()
    start = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    check_backup_freshness(state_dir=tmp_path, notifier=sender, now=start)
    record_backup_failure(state_dir=tmp_path, now=start + timedelta(minutes=10))
    record_component_failure(
        "database-backup",
        "SQLite backup failed",
        state_dir=tmp_path,
        notifier=sender,
        now=start + timedelta(minutes=10),
    )

    result = check_backup_freshness(
        state_dir=tmp_path,
        notifier=sender,
        now=start + timedelta(minutes=40),
    )

    freshness_state = json.loads(
        (tmp_path / "database-backup-freshness.json").read_text(encoding="utf-8")
    )
    assert result is None
    assert len(sender.messages) == 1
    assert "Database backup failed" in sender.messages[0]
    assert freshness_state["health"] == "healthy"


def test_malformed_activity_does_not_duplicate_an_active_producer_alert(
    tmp_path: Path,
):
    sender = RecordingSender()
    start = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    record_component_failure(
        "database-backup",
        "Backup activity state is invalid",
        state_dir=tmp_path,
        notifier=sender,
        now=start,
    )
    (tmp_path / BACKUP_ACTIVITY_FILENAME).write_text("{bad", encoding="utf-8")

    result = check_backup_freshness(
        state_dir=tmp_path,
        notifier=sender,
        now=start + timedelta(hours=1),
    )

    assert result is None
    assert len(sender.messages) == 1


def test_winter_summary_uses_sofia_standard_time(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "09:00")
    sender = RecordingSender()
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc),
        config_path=config,
    )

    result = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 1, 15, 7, 0, tzinfo=timezone.utc),
        config_path=config,
    )

    assert result.scheduled_slot == "2026-01-15/09:00"
    assert "15 Jan 2026 at 09:00" in sender.messages[0]


def test_delivery_failure_makes_summary_a_warning(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "09:00")
    sender = RecordingSender()
    initialized = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    seed_healthy_activity(tmp_path, initialized)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=initialized,
        config_path=config,
    )
    record_backup_success(
        "a" * 64,
        changed=False,
        state_dir=tmp_path,
        now=datetime(2026, 9, 15, 5, 50, tzinfo=timezone.utc),
    )
    record_delivery_run(
        confirmed_uploads=0,
        latest_backup_queued_at_utc=None,
        failed=True,
        pending_count=1,
        state_dir=tmp_path,
        now=datetime(2026, 9, 15, 5, 55, tzinfo=timezone.utc),
    )

    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=1,
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
        config_path=config,
    )

    assert sender.messages[0].startswith(
        "⚠️ Extrusion Terminal — Backup summary needs attention"
    )
    assert "Cloud backup delivery is currently failing" in sender.messages[0]


def test_summary_state_has_exact_schema_and_separate_pending_snapshot(
    tmp_path: Path,
):
    config = write_config(tmp_path / "summary.conf", "09:00")
    now = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    seed_healthy_activity(tmp_path, now)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=RecordingSender(),
        now=now,
        config_path=config,
    )

    state = json.loads(
        (tmp_path / BACKUP_SUMMARY_STATE_FILENAME).read_text(encoding="utf-8")
    )

    assert state == {
        "schema_version": 1,
        "schedule_signature": "09:00",
        "initialized_at_utc": "2026-09-15T05:00:00Z",
        "last_delivered_slot": None,
        "pending_slot": None,
        "pending_message": None,
        "baseline_successful_checks_total": 1,
        "baseline_failed_checks_total": 0,
        "baseline_changed_versions_total": 1,
        "baseline_confirmed_uploads_total": 1,
        "pending_successful_checks_total": None,
        "pending_failed_checks_total": None,
        "pending_changed_versions_total": None,
        "pending_confirmed_uploads_total": None,
    }


def test_summary_state_rejects_invalid_schedule_signature(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "09:00")
    now = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=RecordingSender(),
        now=now,
        config_path=config,
    )
    state_path = tmp_path / BACKUP_SUMMARY_STATE_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["schedule_signature"] = "banana"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="schedule"):
        maybe_send_backup_summary(
            state_dir=tmp_path,
            pending_count=0,
            notifier=RecordingSender(),
            now=now + timedelta(minutes=1),
            config_path=config,
        )


def test_summary_state_rejects_boolean_schema_version(tmp_path: Path):
    config = write_config(tmp_path / "summary.conf", "09:00")
    now = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=RecordingSender(),
        now=now,
        config_path=config,
    )
    state_path = tmp_path / BACKUP_SUMMARY_STATE_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["schema_version"] = True
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="version"):
        maybe_send_backup_summary(
            state_dir=tmp_path,
            pending_count=0,
            notifier=RecordingSender(),
            now=now + timedelta(minutes=1),
            config_path=config,
        )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("last_delivered_slot", "2026-99-99/09:00"),
        ("pending_slot", "2026-09-15/29:00"),
        ("pending_message", "orphaned message"),
        ("pending_successful_checks_total", 4),
    ],
)
def test_summary_state_rejects_semantically_invalid_or_orphaned_values(
    tmp_path: Path,
    key: str,
    value: object,
):
    config = write_config(tmp_path / "summary.conf", "09:00")
    now = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=RecordingSender(),
        now=now,
        config_path=config,
    )
    state_path = tmp_path / BACKUP_SUMMARY_STATE_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state[key] = value
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="summary"):
        maybe_send_backup_summary(
            state_dir=tmp_path,
            pending_count=0,
            notifier=RecordingSender(),
            now=now + timedelta(minutes=1),
            config_path=config,
        )


def test_summary_atomic_replace_failure_preserves_previous_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config = write_config(tmp_path / "summary.conf", "09:00")
    now = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=RecordingSender(),
        now=now,
        config_path=config,
    )
    state_path = tmp_path / BACKUP_SUMMARY_STATE_FILENAME
    original = state_path.read_bytes()

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("simulated summary replace failure")

    monkeypatch.setattr("app.backup_summary.os.replace", fail_replace)
    with pytest.raises(OSError, match="summary replace failure"):
        maybe_send_backup_summary(
            state_dir=tmp_path,
            pending_count=0,
            notifier=RecordingSender(),
            now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
            config_path=config,
        )

    assert state_path.read_bytes() == original


def test_crash_after_discord_acceptance_can_retry_but_never_marks_unsent_done(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config = write_config(tmp_path / "summary.conf", "09:00")
    sender = RecordingSender()
    initialized = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    seed_healthy_activity(tmp_path, initialized)
    maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=initialized,
        config_path=config,
    )
    import app.backup_summary as summary_module

    original_write = summary_module._write_summary_state

    def fail_final_write(path, state):
        if state.last_delivered_slot is not None and state.pending_slot is None:
            raise OSError("simulated post-send crash")
        original_write(path, state)

    monkeypatch.setattr(summary_module, "_write_summary_state", fail_final_write)
    with pytest.raises(OSError, match="post-send crash"):
        maybe_send_backup_summary(
            state_dir=tmp_path,
            pending_count=0,
            notifier=sender,
            now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
            config_path=config,
        )
    pending_state = json.loads(
        (tmp_path / BACKUP_SUMMARY_STATE_FILENAME).read_text(encoding="utf-8")
    )

    monkeypatch.setattr(summary_module, "_write_summary_state", original_write)
    retry = maybe_send_backup_summary(
        state_dir=tmp_path,
        pending_count=0,
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 1, tzinfo=timezone.utc),
        config_path=config,
    )

    assert pending_state["pending_slot"] == "2026-09-15/09:00"
    assert pending_state["last_delivered_slot"] is None
    assert retry.notification_sent is True
    assert sender.messages[0] == sender.messages[1]
