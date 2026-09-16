from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from app.artifact_outbox import (
    CATEGORY_REMOTE_FOLDERS,
    enqueue_artifact,
    load_queued_artifact,
    reap_delivered_cleanup,
    remove_delivered_artifact,
    snapshot_queue_entries,
)


def test_enqueue_copies_source_and_uses_short_content_identity_name(tmp_path: Path):
    source = tmp_path / "extrusion-terminal_2026-09-15_14-20-00.sqlite3"
    source.write_bytes(b"sqlite-safe-image")
    outbox = tmp_path / "outbox"

    queued = enqueue_artifact(
        source,
        "database-backups",
        outbox_dir=outbox,
        now=datetime(2026, 9, 14, 12, 1, tzinfo=timezone.utc),
        item_id="item-001",
    )

    digest = sha256(b"sqlite-safe-image").hexdigest()
    assert source.read_bytes() == b"sqlite-safe-image"
    assert queued.payload_path.read_bytes() == b"sqlite-safe-image"
    assert queued.remote_filename == (
        "extrusion-terminal_2026-09-15_14-20-00_"
        f"{digest[:16]}.sqlite3"
    )
    assert queued.sha256 == digest
    assert queued.item_dir.parent == outbox / "pending" / "database-backups"
    assert tuple((outbox / "staging").iterdir()) == ()


def test_loader_accepts_legacy_complete_checksum_name(tmp_path: Path):
    source = tmp_path / "legacy.sqlite3"
    source.write_bytes(b"legacy payload")
    outbox = tmp_path / "outbox"
    queued = enqueue_artifact(
        source,
        "database-backups",
        outbox_dir=outbox,
        item_id="legacy-item",
    )
    metadata = json.loads(queued.metadata_path.read_text(encoding="utf-8"))
    legacy_name = f"legacy__sha256-{queued.sha256}.sqlite3"
    metadata["remote_filename"] = legacy_name
    queued.metadata_path.write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    loaded = load_queued_artifact(queued.item_dir, outbox_dir=outbox)

    assert loaded.remote_filename == legacy_name
    assert loaded.sha256 == queued.sha256


@pytest.mark.parametrize(
    "invalid_identity",
    [
        "0000000000000000",
        "ABCDEFABCDEFABCD",
        "1234567890abcde",
        "1234567890abcdef0",
    ],
)
def test_loader_rejects_nonmatching_short_content_identity(
    tmp_path: Path,
    invalid_identity: str,
):
    source = tmp_path / "backup.sqlite3"
    source.write_bytes(b"payload")
    outbox = tmp_path / "outbox"
    queued = enqueue_artifact(
        source,
        "database-backups",
        outbox_dir=outbox,
        item_id=f"bad-short-{len(invalid_identity)}",
    )
    metadata = json.loads(queued.metadata_path.read_text(encoding="utf-8"))
    metadata["remote_filename"] = f"backup_{invalid_identity}.sqlite3"
    queued.metadata_path.write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="content identity"):
        load_queued_artifact(queued.item_dir, outbox_dir=outbox)


@pytest.mark.parametrize(
    ("category", "name"),
    [
        ("unknown", "report.pdf"),
        ("database-backups", "../escape.sqlite3"),
        ("database-backups", "wrong.pdf"),
        ("shift-reports", "wrong.sqlite3"),
        ("completed-order-pdfs", "bad/name.pdf"),
        ("completed-order-pdfs", "bad\\name.pdf"),
        ("completed-order-pdfs", "."),
        ("completed-order-pdfs", "control\nname.pdf"),
        ("completed-order-pdfs", "control\x7fname.pdf"),
        ("completed-order-pdfs", "direction\u202ename.pdf"),
        ("completed-order-pdfs", " leading.pdf"),
        ("completed-order-pdfs", "trailing.pdf "),
        ("completed-order-pdfs", ("x" * 220) + ".pdf"),
    ],
)
def test_enqueue_rejects_unknown_category_path_or_suffix(
    tmp_path: Path, category: str, name: str
):
    source = tmp_path / "source.bin"
    source.write_bytes(b"payload")

    with pytest.raises(ValueError):
        enqueue_artifact(
            source,
            category,
            outbox_dir=tmp_path / "outbox",
            remote_basename=name,
        )


def test_category_mapping_is_exact():
    assert CATEGORY_REMOTE_FOLDERS == {
        "database-backups": "database-backups",
        "shift-reports": "shift-reports",
        "completed-order-pdfs": "completed-order-pdfs",
    }


@pytest.mark.parametrize("source_kind", ["missing", "directory"])
def test_enqueue_requires_a_regular_source_file(tmp_path: Path, source_kind: str):
    source = tmp_path / "source.sqlite3"
    if source_kind == "directory":
        source.mkdir()

    with pytest.raises((FileNotFoundError, ValueError)):
        enqueue_artifact(
            source,
            "database-backups",
            outbox_dir=tmp_path / "outbox",
        )


def test_metadata_uses_only_the_version_one_schema(tmp_path: Path):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"report")
    queued = enqueue_artifact(
        source,
        "shift-reports",
        outbox_dir=tmp_path / "outbox",
        now=datetime(2026, 9, 14, 12, 34, 56, 999999, tzinfo=timezone.utc),
        item_id="metadata-item",
    )

    metadata = json.loads(queued.metadata_path.read_text(encoding="utf-8"))
    assert metadata == {
        "schema_version": 1,
        "category": "shift-reports",
        "remote_filename": queued.remote_filename,
        "sha256": queued.sha256,
        "size_bytes": 6,
        "queued_at_utc": "2026-09-14T12:34:56Z",
    }


def test_pending_snapshot_is_oldest_first_across_categories(tmp_path: Path):
    outbox = tmp_path / "outbox"
    first_source = tmp_path / "first.pdf"
    second_source = tmp_path / "second.sqlite3"
    first_source.write_bytes(b"first")
    second_source.write_bytes(b"second")
    first = enqueue_artifact(
        first_source,
        "shift-reports",
        outbox_dir=outbox,
        item_id="same-sort-name-a",
    )
    second = enqueue_artifact(
        second_source,
        "database-backups",
        outbox_dir=outbox,
        item_id="same-sort-name-b",
    )
    os.utime(first.item_dir, ns=(10, 10))
    os.utime(second.item_dir, ns=(20, 20))

    snapshot = snapshot_queue_entries(outbox, max_entries=10)
    assert tuple(entry.path for entry in snapshot.entries) == (
        first.item_dir,
        second.item_dir,
    )
    assert load_queued_artifact(first.item_dir, outbox_dir=outbox) == first


def test_queue_snapshot_reports_persisted_quarantine_evidence(tmp_path: Path):
    outbox = tmp_path / "outbox"
    quarantined = outbox / "quarantine" / "database-backups" / "broken-item"
    quarantined.mkdir(parents=True)

    snapshot = snapshot_queue_entries(outbox, max_entries=0)

    assert snapshot.quarantine_count == 1


@pytest.mark.parametrize("corruption", ["payload", "metadata", "extra-file"])
def test_corrupt_item_is_rejected_and_retained(tmp_path: Path, corruption: str):
    source = tmp_path / "backup.sqlite3"
    source.write_bytes(b"valid")
    outbox = tmp_path / "outbox"
    queued = enqueue_artifact(
        source,
        "database-backups",
        outbox_dir=outbox,
        item_id=f"corrupt-{corruption}",
    )

    if corruption == "payload":
        queued.payload_path.write_bytes(b"changed")
    elif corruption == "metadata":
        metadata = json.loads(queued.metadata_path.read_text(encoding="utf-8"))
        metadata["unexpected"] = True
        queued.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    else:
        (queued.item_dir / "unexpected").write_text("unexpected", encoding="utf-8")

    with pytest.raises(ValueError):
        load_queued_artifact(queued.item_dir, outbox_dir=outbox)

    assert queued.item_dir.exists()
    assert source.read_bytes() == b"valid"


def test_oversized_metadata_is_rejected_before_json_processing(tmp_path: Path):
    source = tmp_path / "backup.sqlite3"
    source.write_bytes(b"valid")
    outbox = tmp_path / "outbox"
    queued = enqueue_artifact(
        source,
        "database-backups",
        outbox_dir=outbox,
        item_id="oversized-metadata",
    )
    original = queued.metadata_path.read_bytes()
    queued.metadata_path.write_bytes(original + (b" " * 20_000))

    with pytest.raises(ValueError, match="too large"):
        load_queued_artifact(queued.item_dir, outbox_dir=outbox)

    assert queued.item_dir.exists()


def test_metadata_fifo_is_rejected_without_blocking(tmp_path: Path):
    source = tmp_path / "backup.sqlite3"
    source.write_bytes(b"valid")
    outbox = tmp_path / "outbox"
    queued = enqueue_artifact(
        source,
        "database-backups",
        outbox_dir=outbox,
        item_id="fifo-metadata",
    )
    queued.metadata_path.unlink()
    os.mkfifo(queued.metadata_path)
    probe = (
        "from pathlib import Path\n"
        "import sys\n"
        "from app.artifact_outbox import load_queued_artifact\n"
        "try:\n"
        "    load_queued_artifact(Path(sys.argv[1]), outbox_dir=Path(sys.argv[2]))\n"
        "except ValueError:\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", probe, str(queued.item_dir), str(outbox)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert queued.metadata_path.is_fifo()


def test_post_publication_fsync_failure_reports_published_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "backup.sqlite3"
    source.write_bytes(b"backup")
    outbox = tmp_path / "outbox"
    real_fsync_directory = __import__(
        "app.artifact_outbox", fromlist=["_fsync_directory"]
    )._fsync_directory

    def fail_pending_category(path: Path) -> None:
        if path == outbox / "pending" / "database-backups":
            raise OSError("simulated post-publication fsync failure")
        real_fsync_directory(path)

    monkeypatch.setattr("app.artifact_outbox._fsync_directory", fail_pending_category)

    with pytest.raises(RuntimeError, match="published") as caught:
        enqueue_artifact(
            source,
            "database-backups",
            outbox_dir=outbox,
            item_id="published-before-fsync",
        )

    assert caught.value.artifact.item_dir.exists()
    assert source.read_bytes() == b"backup"


def test_load_refuses_item_outside_configured_pending_root(tmp_path: Path):
    outside = tmp_path / "outside" / "database-backups" / "item"
    outside.mkdir(parents=True)
    (outside / "payload").write_bytes(b"payload")
    (outside / "metadata.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="outside"):
        load_queued_artifact(outside, outbox_dir=tmp_path / "outbox")


def test_delivered_cleanup_removes_only_queue_copy(tmp_path: Path):
    source = tmp_path / "backup.sqlite3"
    source.write_bytes(b"backup")
    queued = enqueue_artifact(
        source,
        "database-backups",
        outbox_dir=tmp_path / "outbox",
        item_id="delivered",
    )

    remove_delivered_artifact(queued)

    assert source.read_bytes() == b"backup"
    assert not queued.item_dir.exists()
    assert queued.item_dir.parent.exists()


def test_delivered_cleanup_refuses_tampered_paths(tmp_path: Path):
    source = tmp_path / "backup.sqlite3"
    source.write_bytes(b"backup")
    queued = enqueue_artifact(
        source,
        "database-backups",
        outbox_dir=tmp_path / "outbox",
        item_id="tampered",
    )
    outside = tmp_path / "outside"
    outside.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError):
        remove_delivered_artifact(replace(queued, payload_path=outside))

    assert outside.read_text(encoding="utf-8") == "keep"
    assert queued.item_dir.exists()


def test_malformed_cleanup_items_are_quarantined_without_starving_later_work(
    tmp_path: Path,
):
    outbox = tmp_path / "outbox"
    cleanup_root = outbox / "cleanup" / "database-backups"
    cleanup_root.mkdir(parents=True)
    malformed = []
    for index in range(25):
        item = cleanup_root / f"malformed-{index:02d}"
        item.mkdir()
        for child_index in range(3):
            (item / f"unexpected-{child_index}").write_text(
                "preserve", encoding="utf-8"
            )
        os.utime(item, ns=(index + 1, index + 1))
        malformed.append(item)
    valid = cleanup_root / "valid-26th"
    valid.mkdir()
    os.utime(valid, ns=(100, 100))

    first = reap_delivered_cleanup(outbox, max_items=25)

    quarantine = outbox / "quarantine" / "cleanup" / "database-backups"
    assert first.reaped_count == 0
    assert first.failed_count == 25
    assert all(not item.exists() for item in malformed)
    assert len(tuple(quarantine.iterdir())) == 25
    assert valid.exists()

    second = reap_delivered_cleanup(outbox, max_items=25)

    assert second.reaped_count == 1
    assert second.failed_count == 0
    assert not valid.exists()


def test_enqueue_failure_removes_staging_and_preserves_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "backup.sqlite3"
    source.write_bytes(b"backup")
    outbox = tmp_path / "outbox"

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("simulated publication failure")

    monkeypatch.setattr("app.artifact_outbox.os.replace", fail_replace)

    with pytest.raises(OSError, match="publication failure"):
        enqueue_artifact(
            source,
            "database-backups",
            outbox_dir=outbox,
            item_id="failed-publication",
        )

    assert source.read_bytes() == b"backup"
    assert tuple((outbox / "staging").iterdir()) == ()
    pending = outbox / "pending" / "database-backups"
    assert not pending.exists() or tuple(pending.iterdir()) == ()
