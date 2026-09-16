from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.curl_transport import CurlResult, validate_curl_config
from app.pipeline_notifications import (
    DiscordNotificationError,
    DiscordWebhookSender,
    record_component_failure,
    record_component_success,
    retry_pending_notification,
)


class RecordingSender:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)
        if self.fail:
            raise RuntimeError("discord unavailable")


def test_failure_is_sent_once_and_recovery_is_sent_once(tmp_path: Path):
    sender = RecordingSender()

    first = record_component_failure(
        "webdav-delivery",
        "HTTP 503",
        state_dir=tmp_path,
        notifier=sender,
    )
    repeated = record_component_failure(
        "webdav-delivery",
        "HTTP 503 again",
        state_dir=tmp_path,
        notifier=sender,
    )
    recovered = record_component_success(
        "webdav-delivery",
        state_dir=tmp_path,
        notifier=sender,
    )
    healthy = record_component_success(
        "webdav-delivery",
        state_dir=tmp_path,
        notifier=sender,
    )

    assert first.notification_sent is True
    assert repeated.notification_sent is False
    assert recovered.notification_sent is True
    assert healthy.notification_sent is False
    assert len(sender.messages) == 2
    assert "Cloud backups delayed" in sender.messages[0]
    assert "Cloud backups recovered" in sender.messages[1]


def test_webdav_failure_uses_ten_minute_grace_and_brief_recovery_is_silent(
    tmp_path: Path,
):
    sender = RecordingSender()
    grace = timedelta(minutes=10)
    first = record_component_failure(
        "webdav-delivery",
        "temporary timeout",
        state_dir=tmp_path,
        notifier=sender,
        now=datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc),
        notification_grace=grace,
        context={"pending_count": 1},
    )
    repeated = record_component_failure(
        "webdav-delivery",
        "temporary timeout",
        state_dir=tmp_path,
        notifier=sender,
        now=datetime(2026, 9, 15, 0, 9, tzinfo=timezone.utc),
        notification_grace=grace,
        context={"pending_count": 1},
    )
    recovered = record_component_success(
        "webdav-delivery",
        state_dir=tmp_path,
        notifier=sender,
        now=datetime(2026, 9, 15, 0, 9, 30, tzinfo=timezone.utc),
        notification_grace=grace,
        context={"pending_count": 0},
    )

    assert first.notification_attempted is False
    assert first.notification_pending is True
    assert repeated.notification_attempted is False
    assert recovered.notification_sent is False
    assert recovered.notification_pending is False
    assert sender.messages == []


def test_webdav_failure_alerts_once_after_ten_minute_grace(tmp_path: Path):
    sender = RecordingSender()
    grace = timedelta(minutes=10)
    start = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
    record_component_failure(
        "webdav-delivery",
        "HTTP 503",
        state_dir=tmp_path,
        notifier=sender,
        now=start,
        notification_grace=grace,
        context={"pending_count": 1},
    )
    alerted = record_component_failure(
        "webdav-delivery",
        "HTTP 503",
        state_dir=tmp_path,
        notifier=sender,
        now=start + grace,
        notification_grace=grace,
        context={"pending_count": 2},
    )
    repeated = record_component_failure(
        "webdav-delivery",
        "HTTP 503",
        state_dir=tmp_path,
        notifier=sender,
        now=start + timedelta(minutes=11),
        notification_grace=grace,
        context={"pending_count": 2},
    )

    assert alerted.notification_sent is True
    assert repeated.notification_sent is False
    assert len(sender.messages) == 1
    message = sender.messages[0]
    assert "Cloud backups delayed" in message
    assert "15 Sep 2026 at 03:00" in message
    assert "2 backups are waiting" in message
    assert "host=" not in message
    assert "pending_count=" not in message
    assert "webdav-delivery" not in message
    assert "T00:" not in message
    assert "Z" not in message


def test_notification_state_rejects_boolean_schema_version(tmp_path: Path):
    record_component_failure(
        "webdav-delivery",
        "HTTP 503",
        state_dir=tmp_path,
        notifier=RecordingSender(),
    )
    state_path = tmp_path / "webdav-delivery.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["schema_version"] = True
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="version"):
        retry_pending_notification(
            "webdav-delivery",
            state_dir=tmp_path,
            notifier=RecordingSender(),
        )


@pytest.mark.parametrize(
    "key",
    ["first_failed_at_utc", "last_attempt_at_utc", "notification_attempted_at_utc"],
)
def test_notification_state_rejects_noncanonical_timestamps(
    tmp_path: Path,
    key: str,
):
    record_component_failure(
        "webdav-delivery",
        "HTTP 503",
        state_dir=tmp_path,
        notifier=RecordingSender(),
        now=datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc),
        notification_grace=timedelta(minutes=10),
    )
    state_path = tmp_path / "webdav-delivery.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state[key] = "2026-09-15 00:00"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="timestamp"):
        retry_pending_notification(
            "webdav-delivery",
            state_dir=tmp_path,
            notifier=RecordingSender(),
        )


def test_failure_state_from_the_future_is_rejected_without_rewriting_it(
    tmp_path: Path,
):
    later = datetime(2026, 9, 15, 0, 10, tzinfo=timezone.utc)
    record_component_failure(
        "webdav-delivery",
        "HTTP 503",
        state_dir=tmp_path,
        notifier=RecordingSender(),
        now=later,
        notification_grace=timedelta(minutes=10),
    )
    state_path = tmp_path / "webdav-delivery.json"
    original = state_path.read_bytes()

    with pytest.raises(ValueError, match="future"):
        record_component_failure(
            "webdav-delivery",
            "HTTP 503",
            state_dir=tmp_path,
            notifier=RecordingSender(),
            now=later - timedelta(minutes=1),
            notification_grace=timedelta(minutes=10),
        )

    assert state_path.read_bytes() == original


def test_webdav_recovery_after_unsent_qualified_failure_is_combined(
    tmp_path: Path,
):
    grace = timedelta(minutes=10)
    start = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
    record_component_failure(
        "webdav-delivery",
        "HTTP 503",
        state_dir=tmp_path,
        notifier=RecordingSender(),
        now=start,
        notification_grace=grace,
    )
    record_component_failure(
        "webdav-delivery",
        "HTTP 503",
        state_dir=tmp_path,
        notifier=RecordingSender(fail=True),
        now=start + grace,
        notification_grace=grace,
    )
    sender = RecordingSender()

    recovered = record_component_success(
        "webdav-delivery",
        state_dir=tmp_path,
        notifier=sender,
        now=start + timedelta(minutes=12),
        notification_grace=grace,
        context={"recovered_upload_count": 18, "pending_count": 0},
    )

    assert recovered.notification_sent is True
    assert len(sender.messages) == 1
    assert "Cloud backup interruption resolved" in sender.messages[0]
    assert "18 waiting backups were uploaded" in sender.messages[0]
    assert "Nothing remains waiting" in sender.messages[0]


def test_database_backup_failure_is_immediate_and_human_readable(tmp_path: Path):
    sender = RecordingSender()

    result = record_component_failure(
        "database-backup",
        "SQLite integrity check failed",
        state_dir=tmp_path,
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 10, tzinfo=timezone.utc),
    )

    assert result.notification_sent is True
    assert len(sender.messages) == 1
    assert "Database backup failed" in sender.messages[0]
    assert "15 Sep 2026 at 09:10" in sender.messages[0]
    assert "SQLite integrity check failed" in sender.messages[0]


def test_failed_failure_notice_remains_pending_and_retries(tmp_path: Path):
    failing_sender = RecordingSender(fail=True)
    first = record_component_failure(
        "database-backup",
        "disk unavailable",
        state_dir=tmp_path,
        notifier=failing_sender,
    )
    successful_sender = RecordingSender()
    retry = record_component_failure(
        "database-backup",
        "disk still unavailable",
        state_dir=tmp_path,
        notifier=successful_sender,
    )

    assert first.notification_attempted is True
    assert first.notification_sent is False
    assert first.notification_pending is True
    assert retry.notification_sent is True
    assert retry.notification_pending is False
    assert len(failing_sender.messages) == 1
    assert len(successful_sender.messages) == 1


def test_pending_failure_notice_can_retry_without_asserting_new_component_work(
    tmp_path: Path,
):
    record_component_failure(
        "webdav-delivery",
        "initial outage",
        state_dir=tmp_path,
        notifier=RecordingSender(fail=True),
    )
    sender = RecordingSender()

    retried = retry_pending_notification(
        "webdav-delivery",
        state_dir=tmp_path,
        notifier=sender,
    )

    state = json.loads(retried.state_path.read_text(encoding="utf-8"))
    assert retried.health == "failing"
    assert retried.notification_sent is True
    assert retried.notification_pending is False
    assert len(sender.messages) == 1
    assert "Cloud backups delayed" in sender.messages[0]
    assert "initial outage" in sender.messages[0]
    assert state["health"] == "failing"


def test_failed_recovery_notice_remains_pending_and_retries(tmp_path: Path):
    record_component_failure(
        "database-backup",
        "failure",
        state_dir=tmp_path,
        notifier=RecordingSender(),
    )
    failing_sender = RecordingSender(fail=True)

    first_recovery = record_component_success(
        "database-backup",
        state_dir=tmp_path,
        notifier=failing_sender,
    )
    retry_sender = RecordingSender()
    second_recovery = record_component_success(
        "database-backup",
        state_dir=tmp_path,
        notifier=retry_sender,
    )

    assert first_recovery.health == "healthy"
    assert first_recovery.notification_pending is True
    assert second_recovery.notification_sent is True
    assert second_recovery.notification_pending is False
    assert "Database backup recovered" in retry_sender.messages[0]
    recovered_state = json.loads(second_recovery.state_path.read_text(encoding="utf-8"))
    assert recovered_state["failure_notice_sent"] is True


def test_recovery_notice_closes_an_incident_whose_failure_notice_never_sent(
    tmp_path: Path,
):
    failed_notice = record_component_failure(
        "database-backup",
        "brief failure",
        state_dir=tmp_path,
        notifier=RecordingSender(fail=True),
    )
    recovery_sender = RecordingSender()
    recovered = record_component_success(
        "database-backup",
        state_dir=tmp_path,
        notifier=recovery_sender,
    )

    state = json.loads(recovered.state_path.read_text(encoding="utf-8"))
    assert failed_notice.notification_pending is True
    assert recovered.notification_sent is True
    assert recovered.notification_pending is False
    assert state["failure_notice_sent"] is True
    assert len(recovery_sender.messages) == 1
    assert "Database backup interruption resolved" in recovery_sender.messages[0]


def test_failure_after_unsent_combined_recovery_keeps_the_incident_evidence(
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    record_component_failure(
        "webdav-delivery",
        "initial failure",
        state_dir=state_dir,
        notifier=RecordingSender(fail=True),
    )
    record_component_success(
        "webdav-delivery",
        state_dir=state_dir,
        notifier=RecordingSender(fail=True),
    )
    sender = RecordingSender()

    result = record_component_failure(
        "webdav-delivery",
        "failed again",
        state_dir=state_dir,
        notifier=sender,
    )

    assert result.health == "failing"
    assert result.notification_sent is True
    assert len(sender.messages) == 1
    assert "failed again" in sender.messages[0]
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["first_error"] == "initial failure"
    assert state["last_error"] == "failed again"
    assert state["recovery_notice_pending"] is False


def test_component_names_are_allowlisted(tmp_path: Path):
    with pytest.raises(ValueError, match="component"):
        record_component_failure(
            "../../other",
            "failure",
            state_dir=tmp_path,
            notifier=RecordingSender(),
        )

    assert tuple(tmp_path.iterdir()) == ()


def test_message_and_state_text_are_bounded_and_sanitized(tmp_path: Path):
    sender = RecordingSender()
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    result = record_component_failure(
        "webdav-delivery",
        "bad\nline\x00 " + ("x" * 2_000) + " https://secret.invalid/token",
        state_dir=tmp_path,
        notifier=sender,
        now=now,
        context={"category\nname": "database-backups\r", "pending_count": 12},
    )

    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert len(state["last_error"]) <= 500
    assert "\n" not in state["last_error"]
    assert "\x00" not in state["last_error"]
    assert "secret.invalid" not in state["last_error"]
    assert len(sender.messages[0]) <= 1_800
    assert "\nline" not in sender.messages[0]
    assert "secret.invalid" not in sender.messages[0]


def test_state_replacement_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sender = RecordingSender()
    original = record_component_failure(
        "database-backup",
        "first",
        state_dir=tmp_path,
        notifier=sender,
    )
    original_bytes = original.state_path.read_bytes()

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("simulated state replace failure")

    monkeypatch.setattr("app.pipeline_notifications.os.replace", fail_replace)
    with pytest.raises(OSError, match="state replace failure"):
        record_component_failure(
            "database-backup",
            "second",
            state_dir=tmp_path,
            notifier=sender,
        )

    assert original.state_path.read_bytes() == original_bytes
    assert not tuple(tmp_path.glob("*.tmp-*"))


def test_notification_state_read_is_bounded_before_json_processing(tmp_path: Path):
    result = record_component_failure(
        "database-backup",
        "first",
        state_dir=tmp_path,
        notifier=RecordingSender(),
    )
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    state["last_error"] = "x" * 20_000
    result.state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="too large"):
        record_component_success(
            "database-backup",
            state_dir=tmp_path,
            notifier=RecordingSender(),
        )


def test_notification_state_fifo_is_rejected_without_blocking(tmp_path: Path):
    state_path = tmp_path / "database-backup.json"
    os.mkfifo(state_path)
    probe = (
        "from pathlib import Path\n"
        "import sys\n"
        "from app.pipeline_notifications import record_component_success\n"
        "try:\n"
        "    record_component_success('database-backup', state_dir=Path(sys.argv[1]))\n"
        "except ValueError:\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", probe, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert state_path.is_fifo()


def test_notification_state_symlink_to_device_is_rejected(tmp_path: Path):
    (tmp_path / "database-backup.json").symlink_to("/dev/zero")

    with pytest.raises(ValueError, match="Unable to read|invalid"):
        record_component_success(
            "database-backup",
            state_dir=tmp_path,
            notifier=RecordingSender(),
        )


def test_curl_config_parses_comments_and_one_quoted_directive(tmp_path: Path):
    config = tmp_path / "discord.conf"
    config.write_text(
        '# webhook managed outside Git\nurl = "https://discord.com/api/webhooks/123/fake-token?wait=true"\n',
        encoding="utf-8",
    )

    parsed = validate_curl_config(
        config,
        required_options=frozenset({"url"}),
        allowed_options=frozenset({"url"}),
    )

    assert parsed == {
        "url": "https://discord.com/api/webhooks/123/fake-token?wait=true"
    }


def test_missing_curl_config_is_reported_as_a_bounded_validation_error(
    tmp_path: Path,
):
    config = tmp_path / "missing.conf"

    with pytest.raises(ValueError, match="Unable to read curl config") as caught:
        validate_curl_config(
            config,
            required_options=frozenset({"url"}),
            allowed_options=frozenset({"url"}),
        )

    assert "Errno" not in str(caught.value)


def test_curl_config_oversize_is_rejected_before_parsing(tmp_path: Path):
    config = tmp_path / "discord.conf"
    with config.open("wb") as handle:
        handle.truncate((64 * 1024) + 1)

    with pytest.raises(ValueError, match="too large"):
        validate_curl_config(
            config,
            required_options=frozenset({"url"}),
            allowed_options=frozenset({"url"}),
        )


def test_curl_config_fifo_is_rejected_without_blocking(tmp_path: Path):
    config = tmp_path / "discord.conf"
    os.mkfifo(config)
    probe = (
        "from pathlib import Path\n"
        "import sys\n"
        "from app.curl_transport import validate_curl_config\n"
        "try:\n"
        "    validate_curl_config(Path(sys.argv[1]), required_options=frozenset({'url'}), allowed_options=frozenset({'url'}))\n"
        "except ValueError:\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", probe, str(config)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert config.is_fifo()


def test_curl_config_symlink_to_device_is_rejected(tmp_path: Path):
    config = tmp_path / "discord.conf"
    config.symlink_to("/dev/zero")

    with pytest.raises(ValueError, match="Unable to read"):
        validate_curl_config(
            config,
            required_options=frozenset({"url"}),
            allowed_options=frozenset({"url"}),
        )


@pytest.mark.parametrize(
    "contents",
    [
        'url = "https://discord.com/api/webhooks/123/fake-token?wait=true"\nurl = "duplicate"\n',
        "# missing url\n",
        'url = "https://discord.com/api/webhooks/123/fake-token?wait=true"\nrequest = "DELETE"\n',
        "this is not a directive\n",
    ],
)
def test_rejected_curl_config_never_exposes_values(tmp_path: Path, contents: str):
    config = tmp_path / "discord.conf"
    config.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError) as caught:
        validate_curl_config(
            config,
            required_options=frozenset({"url"}),
            allowed_options=frozenset({"url"}),
        )

    assert "fake-token" not in str(caught.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://discord.com/api/webhooks/123/fake-token?wait=true",
        "https://example.com/api/webhooks/123/fake-token?wait=true",
        "https://discord.com/api/webhooks/123/fake-token",
        "https://discord.com/api/webhooks/123/fake-token?wait=false",
    ],
)
def test_discord_sender_rejects_wrong_webhook_url_without_exposing_token(
    tmp_path: Path, url: str
):
    config = tmp_path / "discord.conf"
    config.write_text(f'url = "{url}"\n', encoding="utf-8")

    with pytest.raises(ValueError) as caught:
        DiscordWebhookSender(config, runner=lambda *_args, **_kwargs: CurlResult(0, "", "")).send(
            "message"
        )

    assert "fake-token" not in str(caught.value)


def test_discord_sender_uses_bounded_curl_and_disables_mentions(tmp_path: Path):
    config = tmp_path / "discord.conf"
    webhook = "https://discord.com/api/webhooks/123/fake-token?wait=true"
    config.write_text(f'url = "{webhook}"\n', encoding="utf-8")
    calls: list[tuple[tuple[str, ...], bytes | None]] = []

    def runner(command, *, input_bytes=None):
        calls.append((tuple(command), input_bytes))
        return CurlResult(0, '{"id":"123456789"}\n200', "")

    DiscordWebhookSender(config, runner=runner).send("Task 25 FAILED")

    command, input_bytes = calls[0]
    assert command[0:2] == ("curl", "--disable")
    assert ("--connect-timeout", "10") == command[
        command.index("--connect-timeout") : command.index("--connect-timeout") + 2
    ]
    assert ("--max-time", "30") == command[
        command.index("--max-time") : command.index("--max-time") + 2
    ]
    assert str(config) in command
    assert webhook not in command
    assert "fake-token" not in " ".join(command)
    assert json.loads(input_bytes.decode("utf-8")) == {
        "content": "Task 25 FAILED",
        "allowed_mentions": {"parse": []},
    }
    assert command[command.index("--write-out") + 1] == "\n%{http_code}"


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "204",
        "{}\n200",
        '{"id":""}\n200',
        '{"id":"123456789"}\n204',
        '{"id":"123456789"}\n302',
        "not-json\n200",
        ("x" * 70_000) + "\n200",
    ],
)
def test_discord_sender_rejects_unconfirmed_or_oversized_response(
    tmp_path: Path, stdout: str
):
    config = tmp_path / "discord.conf"
    config.write_text(
        'url = "https://discord.com/api/webhooks/123/fake-token?wait=true"\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="confirmation"):
        DiscordWebhookSender(
            config,
            runner=lambda _command, input_bytes=None: CurlResult(0, stdout, ""),
        ).send("Task 25 FAILED")


def test_notification_failure_is_recorded_and_reported_without_secret(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    class SecretFailureSender:
        def send(self, _message: str) -> None:
            raise RuntimeError(
                "https://discord.com/api/webhooks/123/fake-token?wait=true"
            )

    result = record_component_failure(
        "database-backup",
        "backup failed",
        state_dir=tmp_path,
        notifier=SecretFailureSender(),
    )

    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    stderr = capsys.readouterr().err
    assert result.notification_pending is True
    assert result.notification_error == "RuntimeError: notification delivery failed"
    assert state["notification_error"] == result.notification_error
    assert "notification_pending=true" in stderr
    assert "fake-token" not in stderr
    assert "fake-token" not in result.state_path.read_text(encoding="utf-8")


def test_long_discord_error_remains_loadable_for_a_later_retry(tmp_path: Path):
    class LongFailureSender:
        def send(self, _message: str) -> None:
            raise DiscordNotificationError("x" * 500)

    first = record_component_failure(
        "database-backup",
        "backup failed",
        state_dir=tmp_path,
        notifier=LongFailureSender(),
    )

    assert first.notification_pending is True
    assert first.notification_error is not None
    assert len(first.notification_error) <= 100

    retried = retry_pending_notification(
        "database-backup",
        state_dir=tmp_path,
        notifier=RecordingSender(),
    )

    assert retried.notification_sent is True


def test_failing_notification_state_requires_complete_incident_evidence(
    tmp_path: Path,
):
    started = datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc)
    first = record_component_failure(
        "webdav-delivery",
        "HTTP 503",
        state_dir=tmp_path,
        notifier=RecordingSender(),
        now=started,
        notification_grace=timedelta(minutes=10),
    )
    state = json.loads(first.state_path.read_text(encoding="utf-8"))
    state["first_failed_at_utc"] = None
    first.state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(ValueError, match="incident evidence is incomplete"):
        record_component_failure(
            "webdav-delivery",
            "HTTP 503",
            state_dir=tmp_path,
            notifier=RecordingSender(),
            now=started + timedelta(hours=1),
            notification_grace=timedelta(minutes=10),
        )


def test_discord_confirmation_failure_keeps_a_safe_actionable_diagnostic(
    tmp_path: Path,
):
    config = tmp_path / "discord.conf"
    config.write_text(
        'url = "https://discord.com/api/webhooks/123/fake-token?wait=true"\n',
        encoding="utf-8",
    )

    result = record_component_failure(
        "database-backup",
        "backup failed",
        state_dir=tmp_path / "state",
        notifier=DiscordWebhookSender(
            config,
            runner=lambda _command, input_bytes=None: CurlResult(
                0, '{"id":"123456789"}\n204', ""
            ),
        ),
    )

    state_text = result.state_path.read_text(encoding="utf-8")
    assert result.notification_pending is True
    assert result.notification_error == (
        "DiscordNotificationError: Discord notification confirmation was not HTTP 200."
    )
    assert "fake-token" not in state_text


def test_injected_curl_timeout_leaves_failure_notice_pending(tmp_path: Path):
    config = tmp_path / "discord.conf"
    config.write_text(
        'url = "https://discord.com/api/webhooks/123/fake-token?wait=true"\n',
        encoding="utf-8",
    )

    def timeout_runner(_command, *, input_bytes=None):
        raise subprocess.TimeoutExpired(cmd=["curl"], timeout=30)

    result = record_component_failure(
        "database-backup",
        "backup failed",
        state_dir=tmp_path / "state",
        notifier=DiscordWebhookSender(config, runner=timeout_runner),
        now=datetime.now(timezone.utc) + timedelta(seconds=1),
    )

    state_text = result.state_path.read_text(encoding="utf-8")
    assert result.notification_pending is True
    assert result.notification_error == (
        "DiscordNotificationError: Discord notification process did not complete."
    )
    assert "fake-token" not in state_text
    assert "curl" not in state_text
