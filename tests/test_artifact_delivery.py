from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from app.artifact_delivery import (
    DEFAULT_WEBDAV_BASE_URL,
    DEFAULT_WEBDAV_ROOT,
    DeliveryBatchResult,
    DeliveryConfig,
    WebDAVDeliveryError,
    deliver_pending,
    main,
    upload_create_only,
)
from app.artifact_outbox import enqueue_artifact
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
        return self.result


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
    return DeliveryConfig(
        outbox_dir=tmp_path / "outbox",
        state_dir=tmp_path / "state",
        webdav_base_url=DEFAULT_WEBDAV_BASE_URL,
        webdav_root=DEFAULT_WEBDAV_ROOT,
        webdav_curl_config=webdav_config,
        discord_curl_config=discord_config,
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
    command, input_bytes = runner.calls[0]
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
        + "/system-backups/extrusion-terminal/production-data/shift-reports/"
    )
    assert "%20" in result.remote_url
    assert "%E2%84%96" in result.remote_url
    assert " " not in result.remote_url


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


def test_412_requires_the_complete_checksum_name(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config)
    unsafe = replace(queued, remote_filename="backup.sqlite3")
    runner = RecordingCurlRunner(stdout="412")

    with pytest.raises(ValueError, match="checksum"):
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

    command = runner.calls[0][0]
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


def test_batch_failure_retains_payload_and_records_warning(
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
    assert len(sender.messages) == 1
    assert "FAILED" in sender.messages[0]


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

    assert len(runner.calls) == 25
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
    assert len(runner.calls) == 1
    assert not malformed.item_dir.exists()
    assert (
        delivery_config.outbox_dir
        / "quarantine"
        / "database-backups"
        / malformed.item_dir.name
    ).exists()
    assert not valid.item_dir.exists()
    assert result.pending_count == 0
    assert "FAILED" in sender.messages[0]


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
    assert len(runner.calls) == 1
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
    assert len(runner.calls) == 1
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
    assert "FAILED" in sender.messages[0]


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
    assert "FAILED" in sender.messages[0]


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
    assert "FAILED" in sender.messages[0]


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
    assert len(retry_runner.calls) == 1
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
    assert "FAILED" in sender.messages[0]


def test_delivery_stops_before_starting_upload_outside_internal_budget(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    for index in range(3):
        queue_artifact(tmp_path, delivery_config, item_id=f"budget-{index}")
    runner = RecordingCurlRunner(stdout="201")
    clock_values = iter((0.0, 0.0, 0.0, 200.0, 200.0))

    result = deliver_pending(
        delivery_config,
        runner=runner,
        notifier=RecordingSender(),
        monotonic=lambda: next(clock_values),
    )

    assert result.created_count == 1
    assert result.failed_count == 0
    assert result.pending_count == 2
    assert len(runner.calls) == 1


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
    assert runner.calls == []
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
    assert "FAILED" in sender.messages[0]
    assert state["health"] == "failing"


def test_delivery_defers_network_notification_outside_internal_budget(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queue_artifact(tmp_path, delivery_config, item_id="failed-attempt")
    sender = RecordingSender()
    clock_values = iter((0.0, 0.0, 0.0, 500.0))

    failed = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
        monotonic=lambda: next(clock_values),
    )

    assert failed.failed_count == 1
    assert failed.notification_pending is True
    assert failed.notification_error == "RuntimeError: notification delivery failed"
    assert sender.messages == []

    retry_sender = RecordingSender()
    recovered = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=retry_sender,
    )

    assert recovered.created_count == 1
    assert recovered.notification_pending is False
    assert len(retry_sender.messages) == 1
    assert "FAILED AND RECOVERED" in retry_sender.messages[0]


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

    assert len(runner.calls) == 1
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
    failed = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=sender,
    )
    recovered = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
    )

    assert failed.failed_count == 1
    assert recovered.created_count == 1
    assert len(sender.messages) == 2
    assert "RECOVERED" in sender.messages[1]


def test_clean_empty_run_recovers_a_quarantined_queue_incident(
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
    recovered = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=sender,
    )

    assert failed.failed_count == 1
    assert recovered.failed_count == 0
    assert recovered.pending_count == 0
    assert len(sender.messages) == 2
    assert "RECOVERED" in sender.messages[1]


def test_empty_batch_retries_a_pending_recovery_notice(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queue_artifact(tmp_path, delivery_config, item_id="failed-attempt")
    deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="503"),
        notifier=RecordingSender(),
    )
    delivered = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=FailingSender(),
    )
    retry_sender = RecordingSender()

    empty_retry = deliver_pending(
        delivery_config,
        runner=RecordingCurlRunner(stdout="201"),
        notifier=retry_sender,
    )

    assert delivered.notification_pending is True
    assert empty_retry.created_count == 0
    assert empty_retry.notification_pending is False
    assert len(retry_sender.messages) == 1
    assert "RECOVERED" in retry_sender.messages[0]


def test_notification_state_error_does_not_mask_webdav_failure(
    tmp_path: Path, delivery_config: DeliveryConfig
):
    queued = queue_artifact(tmp_path, delivery_config)
    delivery_config.state_dir.mkdir(parents=True)
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


def test_cli_returns_nonzero_when_batch_has_a_failure(monkeypatch: pytest.MonkeyPatch):
    result = DeliveryBatchResult(0, 0, 1, 1, first_error="simulated failure")
    monkeypatch.setattr("app.artifact_delivery.deliver_pending", lambda _config: result)

    assert main(["deliver"]) == 1
