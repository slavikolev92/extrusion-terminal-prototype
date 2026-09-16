from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.artifact_delivery import (
    DEFAULT_WEBDAV_BASE_URL,
    DEFAULT_WEBDAV_ROOT,
    DeliveryBatchResult,
    DeliveryConfig,
    MAX_DELIVERY_ITEMS_PER_RUN,
    WebDAVDeliveryError,
    deliver_pending,
    main,
    upload_create_only,
)
from app.backup_activity import (
    BACKUP_ACTIVITY_FILENAME,
    load_delivery_activity,
    record_backup_success,
)
from app.backup_job import BackupJobError, run_backup_job
from app.artifact_outbox import enqueue_artifact, load_queued_artifact
from app.curl_transport import CurlResult


class RecordingCurlRunner:
    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str = "201",
        stderr: str = "",
        results: list[CurlResult] | None = None,
    ):
        self.result = CurlResult(returncode, stdout, stderr)
        self.results = list(results) if results is not None else None
        self.calls: list[tuple[list[str], bytes | None]] = []

    def __call__(self, command, *, input_bytes=None):
        self.calls.append((list(command), input_bytes))
        if self.results is not None:
            return self.results.pop(0)
        if command[command.index("--request") + 1] == "MKCOL":
            return CurlResult(0, "405", "")
        return self.result


def calls_for_method(runner: RecordingCurlRunner, method: str):
    return [
        call
        for call in runner.calls
        if call[0][call[0].index("--request") + 1] == method
    ]


class RecordingSender:
    def __init__(self):
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)


class FailingSender:
    def send(self, _message: str) -> None:
        raise RuntimeError("discord unavailable")


@pytest.fixture
def delivery_config(tmp_path: Path) -> DeliveryConfig:
    webdav_config = tmp_path / "webdav.conf"
    webdav_config.write_text(
        'user = "extrusion-backup:fake-password"\n', encoding="utf-8"
    )
    discord_config = tmp_path / "discord.conf"
    discord_config.write_text(
        'url = "https://discord.com/api/webhooks/123/fake-token?wait=true"\n',
        encoding="utf-8",
    )
    summary_config = tmp_path / "summary.conf"
    summary_config.write_text("summary_times=off\n", encoding="ascii")
    record_backup_success(
        "a" * 64,
        changed=True,
        state_dir=tmp_path / "state",
        now=datetime.now(timezone.utc),
    )
    return DeliveryConfig(
        outbox_dir=tmp_path / "outbox",
        state_dir=tmp_path / "state",
        webdav_base_url=DEFAULT_WEBDAV_BASE_URL,
        webdav_root=DEFAULT_WEBDAV_ROOT,
        webdav_curl_config=webdav_config,
        discord_curl_config=discord_config,
        summary_config_path=summary_config,
    )


def queue_artifact(
    tmp_path: Path,
    config: DeliveryConfig,
    *,
    name: str = "backup.sqlite3",
    category: str = "database-backups",
    item_id: str = "item-001",
):
    source = tmp_path / f"source-{item_id}{Path(name).suffix}"
    source.write_bytes(f"payload-{item_id}".encode())
    return enqueue_artifact(
        source,
        category,
        outbox_dir=config.outbox_dir,
        remote_basename=name,
        item_id=item_id,
    )


def test_upload_is_conditional_create_only(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config)
    runner = RecordingCurlRunner(stdout="201")

    result = upload_create_only(queued, delivery_config, runner=runner)

    assert result.state == "created"
    assert len(calls_for_method(runner, "MKCOL")) == 1
    command, input_bytes = calls_for_method(runner, "PUT")[0]
    assert [
        call[0][call[0].index("--request") + 1]
        for call in runner.calls
    ] == ["MKCOL", "PUT"]
    assert input_bytes is None
    assert command[0:2] == ["curl", "--disable"]
    assert command[command.index("--request") + 1] == "PUT"
    assert command[command.index("--header") + 1] == "If-None-Match: *"
    assert str(queued.payload_path) in command
    assert queued.remote_filename in command[-1]
    assert not any(
        method in command
        for method in ("GET", "PROPFIND", "DELETE", "MOVE", "COPY", "HEAD")
    )
    assert not queued.item_dir.exists()


def test_upload_quotes_filename_and_uses_only_fixed_remote_root(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(
        tmp_path,
        delivery_config,
        name="shift report № 1.pdf",
        category="shift-reports",
    )
    runner = RecordingCurlRunner(stdout="201")

    result = upload_create_only(queued, delivery_config, runner=runner)

    assert result.remote_url.startswith(
        DEFAULT_WEBDAV_BASE_URL
        + "/system-backups/extrusion-terminal/shift-reports/"
    )
    assert "%20" in result.remote_url
    assert "%E2%84%96" in result.remote_url
    assert " " not in result.remote_url
    assert len(runner.calls) == 1
    assert calls_for_method(runner, "PUT")


def test_database_backup_creates_only_its_daily_collection_before_upload(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    source = tmp_path / "daily-backup.sqlite3"
    source.write_bytes(b"daily backup payload")
    queued = enqueue_artifact(
        source,
        "database-backups",
        outbox_dir=delivery_config.outbox_dir,
        now=datetime(2026, 9, 15, 12, 34, 56, tzinfo=timezone.utc),
        item_id="daily-backup",
    )
    runner = RecordingCurlRunner(
        results=[
            CurlResult(0, "201", ""),
            CurlResult(0, "201", ""),
        ]
    )

    result = upload_create_only(queued, delivery_config, runner=runner)

    assert result.state == "created"
    assert len(runner.calls) == 2
    collection_command = runner.calls[0][0]
    upload_command = runner.calls[1][0]
    assert (
        collection_command[collection_command.index("--request") + 1] == "MKCOL"
    )
    assert collection_command[-1].endswith(
        "/system-backups/extrusion-terminal/database-backups/2026-09-15"
    )
    assert upload_command[upload_command.index("--request") + 1] == "PUT"
    assert upload_command[-1].startswith(collection_command[-1] + "/")


def test_database_backup_daily_collection_uses_sofia_calendar_date(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    source = tmp_path / "sofia-day.sqlite3"
    source.write_bytes(b"sofia day payload")
    queued = enqueue_artifact(
        source,
        "database-backups",
        outbox_dir=delivery_config.outbox_dir,
        now=datetime(2026, 9, 15, 21, 30, tzinfo=timezone.utc),
        item_id="sofia-day",
    )
    runner = RecordingCurlRunner(
        results=[CurlResult(0, "201", ""), CurlResult(0, "201", "")]
    )

    upload_create_only(queued, delivery_config, runner=runner)

    collection_command = calls_for_method(runner, "MKCOL")[0][0]
    assert collection_command[-1].endswith(
        "/system-backups/extrusion-terminal/database-backups/2026-09-16"
    )


def test_existing_database_backup_daily_collection_proceeds_to_upload(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config)
    runner = RecordingCurlRunner(
        results=[
            CurlResult(0, "405", ""),
            CurlResult(0, "201", ""),
        ]
    )

    result = upload_create_only(queued, delivery_config, runner=runner)

    assert result.state == "created"
    assert len(calls_for_method(runner, "MKCOL")) == 1
    assert len(calls_for_method(runner, "PUT")) == 1


def test_daily_collection_failure_retains_database_backup_without_upload(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config)
    runner = RecordingCurlRunner(
        results=[CurlResult(0, "403", "")]
    )

    with pytest.raises(WebDAVDeliveryError, match="folder creation.*HTTP 403"):
        upload_create_only(queued, delivery_config, runner=runner)

    assert len(calls_for_method(runner, "MKCOL")) == 1
    assert calls_for_method(runner, "PUT") == []
    assert queued.item_dir.exists()


@pytest.mark.parametrize(
    ("curl_result", "expected_error"),
    [
        (CurlResult(28, "000", "timeout"), "curl exit 28"),
        (CurlResult(0, "", ""), "invalid HTTP status"),
        (CurlResult(0, "20x", ""), "invalid HTTP status"),
        (CurlResult(0, "500", ""), "unexpected HTTP 500"),
    ],
)
def test_daily_collection_transport_or_response_failure_retains_backup(
    tmp_path: Path,
    delivery_config: DeliveryConfig,
    curl_result: CurlResult,
    expected_error: str,
):
    queued = queue_artifact(tmp_path, delivery_config)
    runner = RecordingCurlRunner(results=[curl_result])

    with pytest.raises(WebDAVDeliveryError, match=expected_error):
        upload_create_only(queued, delivery_config, runner=runner)

    assert len(calls_for_method(runner, "MKCOL")) == 1
    assert calls_for_method(runner, "PUT") == []
    assert queued.item_dir.exists()


def test_delivery_configuration_refuses_an_arbitrary_remote_root(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config)
    changed = replace(delivery_config, webdav_root=("somewhere-else",))

    with pytest.raises(ValueError, match="fixed"):
        upload_create_only(queued, changed, runner=RecordingCurlRunner())

    assert queued.item_dir.exists()


@pytest.mark.parametrize(
    ("status", "expected_state"),
    [("201", "created"), ("412", "already-present")],
)
def test_success_status_removes_queue_item(
    tmp_path: Path,
    delivery_config: DeliveryConfig,
    status: str,
    expected_state: str,
):
    queued = queue_artifact(tmp_path, delivery_config)

    result = upload_create_only(
        queued, delivery_config, runner=RecordingCurlRunner(stdout=status)
    )

    assert result.state == expected_state
    assert result.http_status == int(status)
    assert not queued.item_dir.exists()


def test_412_accepts_a_matching_legacy_complete_checksum_name(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config, item_id="legacy-412")
    metadata = json.loads(queued.metadata_path.read_text(encoding="utf-8"))
    metadata["remote_filename"] = (
        f"backup__sha256-{queued.sha256}.sqlite3"
    )
    queued.metadata_path.write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    legacy = load_queued_artifact(
        queued.item_dir,
        outbox_dir=delivery_config.outbox_dir,
    )

    result = upload_create_only(
        legacy,
        delivery_config,
        runner=RecordingCurlRunner(stdout="412"),
    )

    assert result.state == "already-present"
    assert not legacy.item_dir.exists()


def test_412_requires_a_matching_content_identity(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config)
    unsafe = replace(queued, remote_filename="backup.sqlite3")
    runner = RecordingCurlRunner(stdout="412")

    with pytest.raises(ValueError, match="content identity"):
        upload_create_only(unsafe, delivery_config, runner=runner)

    assert runner.calls == []
    assert queued.item_dir.exists()


def test_upload_refuses_a_tampered_artifact_object_before_curl(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config)
    unsafe = replace(
        queued,
        remote_filename=(
            f"../escape__sha256-{queued.sha256}.sqlite3"
        ),
    )
    runner = RecordingCurlRunner(stdout="201")

    with pytest.raises(ValueError, match="validated queue metadata"):
        upload_create_only(unsafe, delivery_config, runner=runner)

    assert runner.calls == []
    assert queued.item_dir.exists()


@pytest.mark.parametrize("status", ["200", "204", "400", "401", "403", "500", "000", "n/a"])
def test_every_other_http_status_fails_and_retains_item(
    tmp_path: Path, delivery_config: DeliveryConfig, status: str
):
    queued = queue_artifact(tmp_path, delivery_config)

    with pytest.raises(WebDAVDeliveryError):
        upload_create_only(
            queued, delivery_config, runner=RecordingCurlRunner(stdout=status)
        )

    assert queued.item_dir.exists()


def test_nonzero_curl_exit_is_bounded_and_retains_item(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config)
    runner = RecordingCurlRunner(returncode=28, stdout="000", stderr="x" * 5_000)

    with pytest.raises(WebDAVDeliveryError) as caught:
        upload_create_only(queued, delivery_config, runner=runner)

    assert len(str(caught.value)) < 300
    assert "fake-password" not in str(caught.value)
    assert queued.item_dir.exists()


def test_upload_command_has_bounds_and_only_config_path_credentials(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config)
    runner = RecordingCurlRunner(stdout="201")

    upload_create_only(queued, delivery_config, runner=runner)

    command = calls_for_method(runner, "PUT")[0][0]
    assert command[command.index("--config") + 1] == str(
        delivery_config.webdav_curl_config
    )
    assert command[command.index("--connect-timeout") + 1] == "10"
    assert command[command.index("--max-time") + 1] == "120"
    assert "extrusion-backup:fake-password" not in " ".join(command)


def test_webdav_config_rejects_extra_directive_without_exposing_secret(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    delivery_config.webdav_curl_config.write_text(
        'user = "extrusion-backup:fake-password"\nrequest = "DELETE"\n',
        encoding="utf-8",
    )
    queued = queue_artifact(tmp_path, delivery_config)

    with pytest.raises(WebDAVDeliveryError) as caught:
        upload_create_only(queued, delivery_config, runner=RecordingCurlRunner())

    assert "fake-password" not in str(caught.value)
    assert queued.item_dir.exists()


def test_first_remote_failure_retains_payload_during_notification_grace(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config)
    sender = RecordingSender()

    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
    )

    assert result.failed_count == 1
    assert result.pending_count == 1
    assert queued.payload_path.exists()
    assert sender.messages == []
    assert result.notification_pending is True


def test_batch_processes_only_25_oldest_items(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued_items = []
    for index in range(27):
        queued = queue_artifact(
            tmp_path,
            delivery_config,
            item_id=f"item-{index:03d}",
        )
        os.utime(queued.item_dir, ns=(index + 1, index + 1))
        queued_items.append(queued)
    runner = RecordingCurlRunner(stdout="201")

    result = deliver_pending(delivery_config, runner=runner, notifier=RecordingSender())

    assert len(calls_for_method(runner, "MKCOL")) == 1
    assert len(calls_for_method(runner, "PUT")) == 25
    assert result.created_count == 25
    assert result.failed_count == 0
    assert result.pending_count == 2
    assert not queued_items[0].item_dir.exists()
    assert queued_items[-1].item_dir.exists()


def test_malformed_item_is_retained_while_later_valid_item_is_delivered(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    malformed = queue_artifact(
        tmp_path, delivery_config, item_id="item-malformed"
    )
    valid = queue_artifact(tmp_path, delivery_config, item_id="item-valid")
    os.utime(malformed.item_dir, ns=(1, 1))
    os.utime(valid.item_dir, ns=(2, 2))
    metadata = json.loads(malformed.metadata_path.read_text(encoding="utf-8"))
    metadata["extra"] = True
    malformed.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    sender = RecordingSender()
    runner = RecordingCurlRunner(stdout="201")

    result = deliver_pending(delivery_config, runner=runner, notifier=sender)

    assert result.failed_count == 1
    assert len(calls_for_method(runner, "PUT")) == 1
    assert not malformed.item_dir.exists()
    assert (
        delivery_config.outbox_dir
        / "quarantine"
        / "database-backups"
        / malformed.item_dir.name
    ).exists()
    assert not valid.item_dir.exists()
    assert result.pending_count == 0
    assert "Backup delivery problem" in sender.messages[0]


def test_malformed_batch_does_not_permanently_starve_later_valid_work(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    malformed_items = []
    for index in range(25):
        queued = queue_artifact(
            tmp_path,
            delivery_config,
            item_id=f"malformed-{index:02d}",
        )
        queued.metadata_path.write_text("{}", encoding="utf-8")
        os.utime(queued.item_dir, ns=(index + 1, index + 1))
        malformed_items.append(queued)
    valid = queue_artifact(tmp_path, delivery_config, item_id="valid-after-malformed")
    os.utime(valid.item_dir, ns=(100, 100))
    runner = RecordingCurlRunner(stdout="201")

    first = deliver_pending(delivery_config, runner=runner, notifier=RecordingSender())
    second = deliver_pending(delivery_config, runner=runner, notifier=RecordingSender())

    assert first.failed_count == 25
    assert first.pending_count == 1
    assert second.created_count == 1
    assert second.pending_count == 0
    assert len(calls_for_method(runner, "PUT")) == 1
    assert not valid.item_dir.exists()
    quarantine = delivery_config.outbox_dir / "quarantine" / "database-backups"
    assert {path.name for path in quarantine.iterdir()} == {
        item.item_dir.name for item in malformed_items
    }


def test_max_length_quarantine_collisions_do_not_starve_later_valid_work(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    pending_root = delivery_config.outbox_dir / "pending"
    quarantine = (
        delivery_config.outbox_dir / "quarantine" / "unknown-categories"
    )
    pending_root.mkdir(parents=True)
    quarantine.mkdir(parents=True)
    collision_names = []
    for index in range(25):
        name = f"{index:02d}-" + ("x" * 252)
        assert len(name.encode("utf-8")) == 255
        source = pending_root / name
        source.mkdir()
        os.utime(source, ns=(index + 1, index + 1))
        (quarantine / name).mkdir()
        collision_names.append(name)
    valid = queue_artifact(
        tmp_path,
        delivery_config,
        item_id="valid-after-long-collisions",
    )
    os.utime(valid.item_dir, ns=(100, 100))
    runner = RecordingCurlRunner(stdout="201")

    first = deliver_pending(
        delivery_config, runner=runner, notifier=RecordingSender()
    )
    second = deliver_pending(
        delivery_config, runner=runner, notifier=RecordingSender()
    )

    assert first.failed_count == 25
    assert first.pending_count == 1
    assert second.created_count == 1
    assert second.pending_count == 0
    assert len(calls_for_method(runner, "PUT")) == 1
    assert not valid.item_dir.exists()
    quarantine_names = {path.name for path in quarantine.iterdir()}
    assert set(collision_names) <= quarantine_names
    assert len(quarantine_names) == 50


def test_structural_queue_corruption_is_quarantined_and_reported(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    pending = delivery_config.outbox_dir / "pending"
    category = pending / "database-backups"
    category.mkdir(parents=True)
    stray_file = category / "stray-file"
    stray_file.write_text("retain", encoding="utf-8")
    unknown = pending / "unknown-category"
    unknown.mkdir()
    (unknown / "evidence").write_text("retain", encoding="utf-8")
    stale_staging = delivery_config.outbox_dir / "staging" / "stale-item"
    stale_staging.mkdir(parents=True)
    (stale_staging / "partial").write_text("retain", encoding="utf-8")
    os.utime(stale_staging, (0, 0))
    sender = RecordingSender()

    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
    )

    assert result.failed_count == 3
    assert result.pending_count == 0
    assert len(sender.messages) == 1
    assert "Backup delivery problem" in sender.messages[0]
    quarantine = delivery_config.outbox_dir / "quarantine"
    assert (quarantine / "database-backups" / "stray-file").read_text() == "retain"
    assert (quarantine / "unknown-categories" / "unknown-category" / "evidence").read_text() == "retain"
    assert (quarantine / "staging" / "stale-item" / "partial").read_text() == "retain"


def test_non_directory_category_root_is_quarantined_instead_of_escaping_alerts(
    delivery_config: DeliveryConfig,
):
    category = delivery_config.outbox_dir / "pending" / "database-backups"
    category.parent.mkdir(parents=True)
    category.write_text("retain", encoding="utf-8")
    sender = RecordingSender()

    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
    )

    assert result.failed_count == 1
    assert result.pending_count == 0
    assert (
        delivery_config.outbox_dir
        / "quarantine"
        / "category-roots"
        / "database-backups"
    ).read_text() == "retain"
    assert "Backup delivery problem" in sender.messages[0]


def test_non_directory_staging_root_is_quarantined_and_reported(
    delivery_config: DeliveryConfig,
):
    staging = delivery_config.outbox_dir / "staging"
    staging.parent.mkdir(parents=True)
    staging.write_text("retain", encoding="utf-8")
    sender = RecordingSender()

    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
    )

    assert result.failed_count == 1
    assert (
        delivery_config.outbox_dir
        / "quarantine"
        / "staging-root"
        / "staging"
    ).read_text(encoding="utf-8") == "retain"
    assert "Backup delivery problem" in sender.messages[0]


@pytest.mark.parametrize("broken_name", ["outbox", "cleanup"])
def test_non_directory_queue_or_cleanup_root_is_reported(
    delivery_config: DeliveryConfig,
    broken_name: str,
):
    if broken_name == "outbox":
        delivery_config.outbox_dir.parent.mkdir(parents=True, exist_ok=True)
        delivery_config.outbox_dir.write_text("retain", encoding="utf-8")
    else:
        delivery_config.outbox_dir.mkdir(parents=True)
        (delivery_config.outbox_dir / "cleanup").write_text(
            "retain", encoding="utf-8"
        )
    sender = RecordingSender()

    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
    )

    assert result.failed_count >= 1
    assert result.first_error is not None
    assert "not a directory" in result.first_error.lower()
    assert "Backup delivery problem" in sender.messages[0]


@pytest.mark.parametrize(
    "failure_point",
    [
        "pending-parent-fsync",
        "cleanup-parent-fsync",
        "payload-unlink",
        "metadata-unlink",
        "item-rmdir",
    ],
)
def test_delivery_cleanup_interruption_is_reaped_without_a_second_upload(
    tmp_path: Path,
    delivery_config: DeliveryConfig,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
):
    queued = queue_artifact(tmp_path, delivery_config)
    runner = RecordingCurlRunner(stdout="201")
    real_unlink = Path.unlink
    real_rmdir = Path.rmdir
    outbox_module = __import__("app.artifact_outbox", fromlist=["_fsync_directory"])
    real_fsync_directory = outbox_module._fsync_directory
    cleanup_root = (
        delivery_config.outbox_dir / "cleanup" / "database-backups"
    )

    def interrupt_unlink(path: Path, *args, **kwargs):
        target_name = {
            "payload-unlink": "payload",
            "metadata-unlink": "metadata.json",
        }.get(failure_point)
        if path.name == target_name:
            raise OSError("simulated cleanup interruption")
        return real_unlink(path, *args, **kwargs)

    def interrupt_rmdir(path: Path, *args, **kwargs):
        if failure_point == "item-rmdir" and path.parent == cleanup_root:
            raise OSError("simulated cleanup interruption")
        return real_rmdir(path, *args, **kwargs)

    def interrupt_fsync(path: Path) -> None:
        target = {
            "pending-parent-fsync": queued.item_dir.parent,
            "cleanup-parent-fsync": cleanup_root,
        }.get(failure_point)
        if path == target:
            raise OSError("simulated cleanup interruption")
        real_fsync_directory(path)

    with monkeypatch.context() as patch:
        if failure_point.endswith("-unlink"):
            patch.setattr(Path, "unlink", interrupt_unlink)
        elif failure_point == "item-rmdir":
            patch.setattr(Path, "rmdir", interrupt_rmdir)
        else:
            patch.setattr("app.artifact_outbox._fsync_directory", interrupt_fsync)
        with pytest.raises(OSError, match="cleanup interruption"):
            upload_create_only(queued, delivery_config, runner=runner)

    assert not queued.item_dir.exists()
    cleanup_item = cleanup_root / queued.item_dir.name
    assert cleanup_item.exists()

    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=RecordingSender(),
    )

    assert result.failed_count == 0
    assert not cleanup_item.exists()


def test_cleanup_rename_failure_leaves_item_retryable_via_conditional_put(
    tmp_path: Path,
    delivery_config: DeliveryConfig,
    monkeypatch: pytest.MonkeyPatch,
):
    queued = queue_artifact(tmp_path, delivery_config)
    real_replace = os.replace

    def interrupt_cleanup_rename(source, target):
        if Path(source) == queued.item_dir:
            raise OSError("simulated cleanup rename interruption")
        return real_replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr("app.artifact_outbox.os.replace", interrupt_cleanup_rename)
        with pytest.raises(OSError, match="cleanup rename interruption"):
            upload_create_only(
                queued,
                delivery_config,
                runner=RecordingCurlRunner(stdout="201"),
            )

    assert queued.item_dir.exists()
    retry_runner = RecordingCurlRunner(stdout="412")

    result = deliver_pending(
        delivery_config,
        runner=retry_runner,
        notifier=RecordingSender(),
    )

    assert result.already_present_count == 1
    assert len(calls_for_method(retry_runner, "PUT")) == 1
    assert not queued.item_dir.exists()


def test_cleanup_enumeration_failure_is_reported_through_component_state(
    delivery_config: DeliveryConfig, monkeypatch: pytest.MonkeyPatch
):
    def fail_cleanup(*_args, **_kwargs):
        raise OSError("cleanup enumeration unavailable")

    monkeypatch.setattr("app.artifact_delivery.reap_delivered_cleanup", fail_cleanup)
    sender = RecordingSender()

    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
    )

    assert result.failed_count == 1
    assert result.first_error == "cleanup enumeration unavailable"
    assert load_delivery_activity(
        delivery_config.state_dir
    ).failed_runs_total == 1
    assert "Backup delivery problem" in sender.messages[0]


def test_delivery_stops_before_starting_upload_outside_internal_budget(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    for index in range(3):
        queue_artifact(tmp_path, delivery_config, item_id=f"budget-{index}")
    runner = RecordingCurlRunner(stdout="201")
    clock_values = iter((0.0, 0.0, 0.0, 0.0, 200.0, 200.0))

    result = deliver_pending(
        delivery_config,
        runner=runner,
        notifier=RecordingSender(),
        monotonic=lambda: next(clock_values),
    )

    assert result.created_count == 1
    assert result.failed_count == 0
    assert result.pending_count == 2
    assert len(calls_for_method(runner, "PUT")) == 1


def test_delivery_rechecks_budget_immediately_before_curl(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queue_artifact(tmp_path, delivery_config, item_id="slow-local-validation")
    runner = RecordingCurlRunner(stdout="201")
    sender = RecordingSender()
    clock_values = iter((0.0, 0.0, 500.0, 500.0))

    result = deliver_pending(
        delivery_config,
        runner=runner,
        notifier=sender,
        monotonic=lambda: next(clock_values),
    )

    assert result.created_count == 0
    assert result.failed_count == 1
    assert result.first_error == (
        "Delivery time budget expired before any WebDAV upload could start."
    )
    assert result.pending_count == 1
    assert calls_for_method(runner, "MKCOL") == []
    assert calls_for_method(runner, "PUT") == []
    assert sender.messages == []
    assert result.notification_pending is True
    state = json.loads(
        (delivery_config.state_dir / "webdav-delivery.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["health"] == "failing"
    assert state["last_error"] == result.first_error


def test_budget_only_run_keeps_incident_failing_without_delivery_evidence(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queue_artifact(tmp_path, delivery_config, item_id="still-pending")
    sender = RecordingSender()
    failed = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
    )
    clock_values = iter((0.0, 200.0, 200.0))

    deferred = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
        monotonic=lambda: next(clock_values),
    )

    state = json.loads(
        (delivery_config.state_dir / "webdav-delivery.json").read_text(
            encoding="utf-8"
        )
    )
    assert failed.failed_count == 1
    assert deferred.created_count == 0
    assert deferred.failed_count == 1
    assert "time budget expired" in deferred.first_error
    assert deferred.pending_count == 1
    assert len(sender.messages) == 1
    assert "Backup delivery problem" in sender.messages[0]
    assert state["health"] == "failing"


def test_delivery_defers_network_notification_outside_internal_budget(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queue_artifact(tmp_path, delivery_config, item_id="failed-attempt")
    sender = RecordingSender()
    start = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
    initial = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
        now=start,
    )
    clock_values = iter((0.0, 0.0, 0.0, 0.0, 500.0))

    failed = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
        monotonic=lambda: next(clock_values),
        now=start + timedelta(minutes=10),
    )

    assert initial.notification_pending is True
    assert failed.failed_count == 1
    assert failed.notification_pending is True
    assert failed.notification_error == "RuntimeError: notification delivery failed"
    assert sender.messages == []

    retry_sender = RecordingSender()
    recovered = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=retry_sender,
        now=start + timedelta(minutes=11),
    )

    assert recovered.created_count == 1
    assert recovered.notification_pending is False
    assert len(retry_sender.messages) == 1
    assert "Cloud backup interruption resolved" in retry_sender.messages[0]


def test_first_remote_failure_stops_later_upload_attempts(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    items = [
        queue_artifact(tmp_path, delivery_config, item_id=f"item-{index}")
        for index in range(3)
    ]
    for index, queued in enumerate(items):
        os.utime(queued.item_dir, ns=(index + 1, index + 1))
    runner = RecordingCurlRunner(stdout="503")

    result = deliver_pending(
        delivery_config, runner=runner, notifier=RecordingSender()
    )

    assert len(calls_for_method(runner, "MKCOL")) == 1
    assert len(calls_for_method(runner, "PUT")) == 1
    assert result.failed_count == 1
    assert result.pending_count == 3
    assert all(queued.item_dir.exists() for queued in items)


def test_missing_webdav_config_is_one_fatal_batch_failure_and_stops(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    items = [
        queue_artifact(tmp_path, delivery_config, item_id=f"missing-config-{index}")
        for index in range(2)
    ]
    delivery_config.webdav_curl_config.unlink()
    runner = RecordingCurlRunner(stdout="201")

    result = deliver_pending(delivery_config, runner=runner, notifier=RecordingSender())

    assert result.failed_count == 1
    assert result.pending_count == 2
    assert result.first_error == "Protected WebDAV curl configuration is invalid."
    assert runner.calls == []
    assert all(queued.item_dir.exists() for queued in items)


def test_clean_batch_records_one_recovery(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    sender = RecordingSender()
    queue_artifact(tmp_path, delivery_config, item_id="failed-attempt")
    start = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
    failed = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
        now=start,
    )
    alerted = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
        now=start + timedelta(minutes=10),
    )
    recovered = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
        now=start + timedelta(minutes=11),
    )

    assert failed.failed_count == 1
    assert alerted.failed_count == 1
    assert recovered.created_count == 1
    assert len(sender.messages) == 2
    assert "Cloud backups recovered" in sender.messages[1]


def test_recovery_waits_for_the_entire_multibatch_backlog(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    sender = RecordingSender()
    start = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
    items = [
        queue_artifact(
            tmp_path,
            delivery_config,
            item_id=f"backlog-{index:02d}",
        )
        for index in range(MAX_DELIVERY_ITEMS_PER_RUN + 1)
    ]
    for index, queued in enumerate(items):
        os.utime(queued.item_dir, ns=(index + 1, index + 1))

    first_failure = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
        now=start,
    )
    alerted_failure = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
        now=start + timedelta(minutes=10),
    )
    partial = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
        now=start + timedelta(minutes=11),
    )
    recovered = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
        now=start + timedelta(minutes=12),
    )

    assert first_failure.pending_count == MAX_DELIVERY_ITEMS_PER_RUN + 1
    assert alerted_failure.pending_count == MAX_DELIVERY_ITEMS_PER_RUN + 1
    assert partial.created_count == MAX_DELIVERY_ITEMS_PER_RUN
    assert partial.pending_count == 1
    assert partial.notification_pending is False
    assert recovered.created_count == 1
    assert recovered.pending_count == 0
    assert len(sender.messages) == 2
    assert "Cloud backups delayed" in sender.messages[0]
    assert "Cloud backups recovered" in sender.messages[1]
    assert "26 waiting backups were uploaded" in sender.messages[1]


def test_quarantined_queue_incident_does_not_claim_recovery_until_reviewed(
    delivery_config: DeliveryConfig,
):
    category = delivery_config.outbox_dir / "pending" / "database-backups"
    category.parent.mkdir(parents=True)
    category.write_text("retain", encoding="utf-8")
    sender = RecordingSender()

    failed = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
    )
    still_failing = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
    )

    assert failed.failed_count == 1
    assert still_failing.failed_count == 1
    assert still_failing.pending_count == 0
    assert len(sender.messages) == 1
    assert "recovered" not in sender.messages[0].lower()
    assert "manual review is required" in sender.messages[0].lower()
    assert "retrying automatically" not in sender.messages[0].lower()
    assert "0 backups" not in sender.messages[0].lower()


def test_final_delivery_activity_failure_preserves_confirmation_and_blocks_recovery(
    tmp_path: Path,
    delivery_config: DeliveryConfig,
    monkeypatch: pytest.MonkeyPatch,
):
    queued = queue_artifact(tmp_path, delivery_config, item_id="state-failure")
    sender = RecordingSender()
    start = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
    deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
        now=start,
    )
    deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
        now=start + timedelta(minutes=10),
    )

    def fail_activity(**_kwargs):
        raise OSError("simulated delivery activity failure")

    monkeypatch.setattr("app.artifact_delivery.record_delivery_run", fail_activity)
    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
        now=start + timedelta(minutes=11),
    )

    assert result.failed_count == 1
    assert not queued.item_dir.exists()
    activity = load_delivery_activity(delivery_config.state_dir)
    assert activity.confirmed_uploads_total == 1
    assert activity.unremoved_confirmed_item_ids == ("state-failure",)
    assert "delivery activity failure" in (result.notification_state_error or "")
    assert len(sender.messages) == 1
    assert "recovered" not in sender.messages[-1].lower()


def test_confirmation_checkpoint_failure_reports_retained_item_as_pending(
    tmp_path: Path,
    delivery_config: DeliveryConfig,
    monkeypatch: pytest.MonkeyPatch,
):
    queued = queue_artifact(
        tmp_path,
        delivery_config,
        item_id="checkpoint-state-failure",
    )

    def fail_checkpoint(**_kwargs):
        raise OSError("simulated confirmation checkpoint failure")

    monkeypatch.setattr(
        "app.artifact_delivery.record_delivery_confirmations",
        fail_checkpoint,
    )

    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=RecordingSender(),
    )

    assert result.failed_count == 1
    assert result.pending_count == 1
    assert queued.item_dir.exists()


def test_quarantine_alert_is_immediate_during_simultaneous_remote_failure(
    tmp_path: Path,
    delivery_config: DeliveryConfig,
):
    queue_artifact(tmp_path, delivery_config, item_id="remote-and-quarantine")
    evidence = (
        delivery_config.outbox_dir
        / "quarantine"
        / "database-backups"
        / "requires-review"
    )
    evidence.mkdir(parents=True)
    sender = RecordingSender()

    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
    )

    assert result.failed_count == 1
    assert len(sender.messages) == 1
    assert "manual review is required" in sender.messages[0].lower()


def test_delivery_waits_for_active_backup_handoff_before_uploading(
    tmp_path: Path,
    delivery_config: DeliveryConfig,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "source.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES ('preserved')")
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
    started = datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc)
    with pytest.raises(BackupJobError, match="activity write failure"):
        run_backup_job(
            source_db_path=source,
            backup_dir=backup_dir,
            outbox_dir=delivery_config.outbox_dir,
            state_dir=delivery_config.state_dir,
            notifier=RecordingSender(),
            now=started,
        )

    blocked_runner = RecordingCurlRunner(stdout="201")
    blocked = deliver_pending(
        delivery_config,
        runner=blocked_runner,
        notifier=RecordingSender(),
        now=started + timedelta(minutes=1),
    )

    assert blocked.created_count == 0
    assert blocked.pending_count == 1
    assert calls_for_method(blocked_runner, "PUT") == []

    run_backup_job(
        source_db_path=source,
        backup_dir=backup_dir,
        outbox_dir=delivery_config.outbox_dir,
        state_dir=delivery_config.state_dir,
        notifier=RecordingSender(),
        now=started + timedelta(minutes=2),
    )
    delivered = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=RecordingSender(),
        now=started + timedelta(minutes=3),
    )

    assert delivered.created_count == 1
    assert delivered.pending_count == 0
    assert load_delivery_activity(
        delivery_config.state_dir
    ).confirmed_uploads_total == 1


def test_cleanup_retry_does_not_double_count_a_confirmed_upload(
    tmp_path: Path,
    delivery_config: DeliveryConfig,
    monkeypatch: pytest.MonkeyPatch,
):
    queued = queue_artifact(tmp_path, delivery_config, item_id="cleanup-retry")
    real_remove = __import__(
        "app.artifact_delivery", fromlist=["remove_delivered_artifact"]
    ).remove_delivered_artifact
    failed_once = False

    def fail_once(artifact):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise OSError("simulated post-confirmation cleanup failure")
        return real_remove(artifact)

    monkeypatch.setattr("app.artifact_delivery.remove_delivered_artifact", fail_once)
    first = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=RecordingSender(),
    )
    assert first.created_count == 1
    assert first.failed_count == 1
    assert queued.item_dir.exists()
    first_activity = load_delivery_activity(delivery_config.state_dir)
    assert first_activity.confirmed_uploads_total == 1
    assert first_activity.failed_runs_total == 1
    assert first_activity.active_incident_upload_count == 1

    second = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="412"),
        notifier=RecordingSender(),
    )

    assert second.already_present_count == 1
    assert not queued.item_dir.exists()
    recovered_activity = load_delivery_activity(delivery_config.state_dir)
    assert recovered_activity.confirmed_uploads_total == 1
    assert recovered_activity.active_incident_upload_count == 0


def test_next_run_clears_confirmation_left_after_post_cleanup_crash(
    tmp_path: Path,
    delivery_config: DeliveryConfig,
    monkeypatch: pytest.MonkeyPatch,
):
    queued = queue_artifact(tmp_path, delivery_config, item_id="post-cleanup-crash")

    def crash_after_cleanup(*_args, **_kwargs):
        raise SystemExit("simulated crash after cleanup")

    with monkeypatch.context() as patch:
        patch.setattr(
            "app.artifact_delivery.acknowledge_confirmed_delivery_items",
            crash_after_cleanup,
        )
        with pytest.raises(SystemExit, match="crash after cleanup"):
            deliver_pending(
                delivery_config,
                runner=RecordingCurlRunner(stdout="201"),
                notifier=RecordingSender(),
            )

    assert not queued.item_dir.exists()
    assert load_delivery_activity(
        delivery_config.state_dir
    ).unremoved_confirmed_item_ids == ("post-cleanup-crash",)

    deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=RecordingSender(),
    )

    assert load_delivery_activity(
        delivery_config.state_dir
    ).unremoved_confirmed_item_ids == ()


def test_empty_batch_retries_a_pending_recovery_notice(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queue_artifact(tmp_path, delivery_config, item_id="failed-attempt")
    start = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
    deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=RecordingSender(),
        now=start,
    )
    deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=RecordingSender(),
        now=start + timedelta(minutes=10),
    )
    delivered = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=FailingSender(),
        now=start + timedelta(minutes=11),
    )
    retry_sender = RecordingSender()

    empty_retry = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=retry_sender,
        now=start + timedelta(minutes=12),
    )

    assert delivered.notification_pending is True
    assert empty_retry.created_count == 0
    assert empty_retry.notification_pending is False
    assert len(retry_sender.messages) == 1
    assert "Cloud backups recovered" in retry_sender.messages[0]


def test_notification_state_error_does_not_mask_webdav_failure(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config)
    delivery_config.state_dir.mkdir(parents=True, exist_ok=True)
    (delivery_config.state_dir / "webdav-delivery.json").write_text(
        "{invalid", encoding="utf-8"
    )

    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=RecordingSender(),
    )

    assert result.failed_count == 1
    assert "HTTP 503" in result.first_error
    assert "Notification state" in result.notification_state_error
    assert queued.item_dir.exists()


def test_delivery_worker_sends_due_summary_after_upload_work(
    delivery_config: DeliveryConfig,
):
    summary_config = delivery_config.summary_config_path
    assert summary_config is not None
    summary_config.write_text("summary_times=09:00\n", encoding="ascii")
    sender = RecordingSender()
    initialized = datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc)
    record_backup_success(
        "b" * 64,
        changed=True,
        state_dir=delivery_config.state_dir,
        now=initialized,
    )
    deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(),
        notifier=sender,
        now=initialized,
    )
    record_backup_success(
        "b" * 64,
        changed=False,
        state_dir=delivery_config.state_dir,
        now=datetime(2026, 9, 15, 5, 50, tzinfo=timezone.utc),
    )

    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(),
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
    )

    assert result.failed_count == 0
    assert result.notification_pending is False
    assert len(sender.messages) == 1
    assert "Backup summary" in sender.messages[0]


def test_freshness_warning_takes_priority_over_due_summary(
    delivery_config: DeliveryConfig,
):
    summary_config = delivery_config.summary_config_path
    assert summary_config is not None
    summary_config.write_text("summary_times=08:00\n", encoding="ascii")
    (delivery_config.state_dir / BACKUP_ACTIVITY_FILENAME).unlink()
    sender = RecordingSender()
    first_observation = datetime(2026, 9, 15, 4, 0, tzinfo=timezone.utc)
    deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(),
        notifier=sender,
        now=first_observation,
    )

    priority_run = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(),
        notifier=sender,
        now=first_observation + timedelta(hours=1),
    )
    next_run = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(),
        notifier=sender,
        now=first_observation + timedelta(hours=1, minutes=1),
    )

    assert priority_run.notification_pending is True
    assert len(sender.messages) == 2
    assert "Database backup process appears stopped" in sender.messages[0]
    assert "Backup summary" in sender.messages[1]
    assert next_run.notification_pending is False


def test_webdav_warning_takes_priority_over_due_summary(
    tmp_path: Path,
    delivery_config: DeliveryConfig,
):
    summary_config = delivery_config.summary_config_path
    assert summary_config is not None
    summary_config.write_text("summary_times=09:00\n", encoding="ascii")
    sender = RecordingSender()
    initialized = datetime(2026, 9, 15, 4, 0, tzinfo=timezone.utc)
    record_backup_success(
        "b" * 64,
        changed=True,
        state_dir=delivery_config.state_dir,
        now=initialized,
    )
    deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(),
        notifier=sender,
        now=initialized,
    )
    queue_artifact(tmp_path, delivery_config, item_id="priority")
    deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
        now=datetime(2026, 9, 15, 5, 50, tzinfo=timezone.utc),
    )
    record_backup_success(
        "b" * 64,
        changed=False,
        state_dir=delivery_config.state_dir,
        now=datetime(2026, 9, 15, 5, 59, tzinfo=timezone.utc),
    )

    priority_run = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
        now=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
    )

    assert priority_run.notification_pending is True
    assert len(sender.messages) == 1
    assert "Cloud backups delayed" in sender.messages[0]


def test_invalid_summary_configuration_preserves_delivery_result_and_fails_run(
    delivery_config: DeliveryConfig,
):
    summary_config = delivery_config.summary_config_path
    assert summary_config is not None
    summary_config.write_text("summary_times=maybe\n", encoding="ascii")

    result = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(),
        notifier=RecordingSender(),
    )

    assert result.created_count == 0
    assert result.failed_count == 0
    assert "summary configuration" in result.notification_state_error.lower()


def test_cli_returns_nonzero_without_claiming_completion_when_batch_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    result = DeliveryBatchResult(0, 0, 1, 1, first_error="simulated failure")
    monkeypatch.setattr("app.artifact_delivery.deliver_pending", lambda _config: result)

    assert main(["deliver"]) == 1
    output = capsys.readouterr().out
    assert output.startswith("Artifact delivery result:")
    assert "complete" not in output.lower()
