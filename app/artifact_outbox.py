from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

from . import db
from .bounded_files import read_bounded_regular_file


OUTBOX_SCHEMA_VERSION = 1
CATEGORY_REMOTE_FOLDERS = MappingProxyType(
    {
        "database-backups": "database-backups",
        "shift-reports": "shift-reports",
        "completed-order-pdfs": "completed-order-pdfs",
    }
)
CATEGORY_SUFFIXES = MappingProxyType(
    {
        "database-backups": ".sqlite3",
        "shift-reports": ".pdf",
        "completed-order-pdfs": ".pdf",
    }
)
DEFAULT_OUTBOX_DIR = Path(
    os.getenv(
        "EXTRUSION_ARTIFACT_OUTBOX_DIR",
        db.BASE_DIR / "artifact-delivery" / "outbox",
    )
)

_METADATA_KEYS = frozenset(
    {
        "schema_version",
        "category",
        "remote_filename",
        "sha256",
        "size_bytes",
        "queued_at_utc",
    }
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_ITEM_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_UTC_TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
MAX_REMOTE_FILENAME_BYTES = 240
MAX_METADATA_BYTES = 16 * 1024
STALE_STAGING_AGE_SECONDS = 15 * 60


class ArtifactPublishedDurabilityError(RuntimeError):
    def __init__(self, artifact: "QueuedArtifact") -> None:
        super().__init__(
            f"Queue item was published but directory durability was not confirmed: "
            f"{artifact.item_dir}"
        )
        self.artifact = artifact


@dataclass(frozen=True)
class QueueEntry:
    path: Path
    kind: Literal[
        "pending-item",
        "unexpected-category",
        "category-root",
        "pending-root",
        "staging-root",
        "stale-staging",
    ]


@dataclass(frozen=True)
class QueueSnapshot:
    entries: tuple[QueueEntry, ...]
    pending_count: int
    stale_staging_count: int


@dataclass(frozen=True)
class CleanupResult:
    reaped_count: int
    failed_count: int
    first_error: str | None


@dataclass(frozen=True)
class QueuedArtifact:
    item_dir: Path
    payload_path: Path
    metadata_path: Path
    category: str
    remote_filename: str
    sha256: str
    size_bytes: int
    queued_at_utc: str


def enqueue_artifact(
    source_path: Path | str,
    category: str,
    *,
    outbox_dir: Path | str | None = None,
    remote_basename: str | None = None,
    now: datetime | None = None,
    item_id: str | None = None,
) -> QueuedArtifact:
    suffix = _category_suffix(category)
    source = Path(source_path).resolve(strict=True)
    if not source.is_file():
        raise ValueError(f"Artifact source is not a regular file: {source}")

    basename = remote_basename if remote_basename is not None else source.name
    _validate_plain_basename(basename, suffix)
    resolved_item_id = item_id if item_id is not None else uuid4().hex
    if _ITEM_ID_PATTERN.fullmatch(resolved_item_id) is None:
        raise ValueError("Queue item ID contains unsupported characters.")

    outbox = _resolve_outbox_dir(outbox_dir)
    staging_root = outbox / "staging"
    pending_root = outbox / "pending"
    pending_category_root = outbox / "pending" / category
    _ensure_directory(outbox)
    _ensure_directory(staging_root)
    _ensure_directory(pending_root)
    _ensure_directory(pending_category_root)
    staging_item = staging_root / resolved_item_id
    pending_item = pending_category_root / resolved_item_id
    if pending_item.exists():
        raise FileExistsError(f"Queue item already exists: {pending_item}")

    staging_item.mkdir()
    payload_path = staging_item / "payload"
    metadata_path = staging_item / "metadata.json"
    try:
        shutil.copyfile(source, payload_path)
        _fsync_file(payload_path)
        digest, size_bytes = _hash_and_size(payload_path)
        remote_filename = _checksum_filename(basename, suffix, digest)
        queued_at_utc = _format_utc_timestamp(now)
        metadata = {
            "schema_version": OUTBOX_SCHEMA_VERSION,
            "category": category,
            "remote_filename": remote_filename,
            "sha256": digest,
            "size_bytes": size_bytes,
            "queued_at_utc": queued_at_utc,
        }
        temporary_metadata = staging_item / ".metadata.json.tmp"
        with temporary_metadata.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(metadata, handle, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_metadata, metadata_path)
        _fsync_directory(staging_item)
        _fsync_directory(staging_root)
        os.replace(staging_item, pending_item)
    except Exception:
        if staging_item.exists():
            shutil.rmtree(staging_item)
        raise

    artifact = QueuedArtifact(
        item_dir=pending_item,
        payload_path=pending_item / "payload",
        metadata_path=pending_item / "metadata.json",
        category=category,
        remote_filename=remote_filename,
        sha256=digest,
        size_bytes=size_bytes,
        queued_at_utc=queued_at_utc,
    )
    try:
        _fsync_directory(pending_category_root)
    except Exception as error:
        raise ArtifactPublishedDurabilityError(artifact) from error
    return artifact


def snapshot_queue_entries(
    outbox_dir: Path | str | None = None,
    *,
    max_entries: int,
    now_epoch: float | None = None,
) -> QueueSnapshot:
    """Return a memory-bounded oldest-first snapshot plus exact health counts."""
    if max_entries < 0:
        raise ValueError("max_entries must not be negative.")
    outbox = _resolve_outbox_dir(outbox_dir)
    outbox_stat = _lstat_or_none(outbox)
    if outbox_stat is not None and not _is_directory_mode(outbox_stat.st_mode):
        raise ValueError(f"Queue root is not a directory: {outbox}")
    selected: list[QueueEntry] = []
    pending_count = 0
    stale_staging_count = 0

    def consider(entry: QueueEntry) -> None:
        if max_entries == 0:
            return
        selected.append(entry)
        selected.sort(key=_queue_entry_sort_key)
        if len(selected) > max_entries:
            selected.pop()

    pending_root = outbox / "pending"
    pending_stat = _lstat_or_none(pending_root)
    if pending_stat is not None:
        if not _is_directory_mode(pending_stat.st_mode):
            pending_count += 1
            consider(QueueEntry(pending_root, "pending-root"))
        else:
            with os.scandir(pending_root) as categories:
                for category_entry in categories:
                    category_path = Path(category_entry.path)
                    is_allowed = category_entry.name in CATEGORY_REMOTE_FOLDERS
                    if is_allowed and category_entry.is_dir(follow_symlinks=False):
                        with os.scandir(category_path) as items:
                            for item_entry in items:
                                pending_count += 1
                                consider(
                                    QueueEntry(Path(item_entry.path), "pending-item")
                                )
                    else:
                        pending_count += 1
                        consider(
                            QueueEntry(
                                category_path,
                                "category-root" if is_allowed else "unexpected-category",
                            )
                        )

    cutoff = (time.time() if now_epoch is None else now_epoch) - STALE_STAGING_AGE_SECONDS
    staging_root = outbox / "staging"
    staging_stat = _lstat_or_none(staging_root)
    if staging_stat is not None:
        if not _is_directory_mode(staging_stat.st_mode):
            stale_staging_count += 1
            consider(QueueEntry(staging_root, "staging-root"))
        else:
            with os.scandir(staging_root) as staging_entries:
                for staging_entry in staging_entries:
                    if staging_entry.stat(follow_symlinks=False).st_mtime <= cutoff:
                        stale_staging_count += 1
                        consider(QueueEntry(Path(staging_entry.path), "stale-staging"))

    return QueueSnapshot(
        entries=tuple(selected),
        pending_count=pending_count,
        stale_staging_count=stale_staging_count,
    )


def quarantine_queue_entry(
    entry: QueueEntry,
    *,
    outbox_dir: Path | str | None = None,
) -> Path:
    outbox = _resolve_outbox_dir(outbox_dir)
    source = entry.path
    _validate_queue_entry_location(entry, outbox)
    destination_group = {
        "pending-item": source.parent.name,
        "unexpected-category": "unknown-categories",
        "category-root": "category-roots",
        "pending-root": "pending-root",
        "staging-root": "staging-root",
        "stale-staging": "staging",
    }[entry.kind]
    destination_root = outbox / "quarantine" / destination_group
    _ensure_directory(outbox)
    _ensure_directory(outbox / "quarantine")
    _ensure_directory(destination_root)
    destination = _available_quarantine_destination(destination_root, source.name)
    os.replace(source, destination)
    _fsync_directory(source.parent)
    _fsync_directory(destination_root)
    return destination


def reap_delivered_cleanup(
    outbox_dir: Path | str | None = None,
    *,
    max_items: int = 25,
) -> CleanupResult:
    if max_items < 0:
        raise ValueError("max_items must not be negative.")
    outbox = _resolve_outbox_dir(outbox_dir)
    outbox_stat = _lstat_or_none(outbox)
    if outbox_stat is not None and not _is_directory_mode(outbox_stat.st_mode):
        return CleanupResult(0, 1, f"Queue root is not a directory: {outbox}")
    candidates: list[Path] = []

    def consider(path: Path) -> None:
        if max_items == 0:
            return
        candidates.append(path)
        candidates.sort(
            key=lambda value: (
                _lstat_required(value).st_mtime_ns,
                str(value),
            )
        )
        if len(candidates) > max_items:
            candidates.pop()

    cleanup_root = outbox / "cleanup"
    cleanup_stat = _lstat_or_none(cleanup_root)
    if cleanup_stat is not None and not _is_directory_mode(cleanup_stat.st_mode):
        return CleanupResult(
            0,
            1,
            f"Cleanup root is not a directory: {cleanup_root}",
        )
    for category in CATEGORY_REMOTE_FOLDERS:
        category_root = cleanup_root / category
        category_stat = _lstat_or_none(category_root)
        if category_stat is None:
            continue
        if not _is_directory_mode(category_stat.st_mode):
            return CleanupResult(
                0,
                1,
                f"Cleanup category is not a directory: {category_root}",
            )
        with os.scandir(category_root) as entries:
            for entry in entries:
                consider(Path(entry.path))
    reaped = 0
    failed = 0
    first_error = None
    for candidate in candidates:
        try:
            _reap_cleanup_item(candidate, outbox)
        except Exception as error:
            failed += 1
            if first_error is None:
                first_error = _bounded_error(error)
            try:
                _quarantine_cleanup_item(candidate, outbox)
            except Exception as quarantine_error:
                if first_error is None:
                    first_error = _bounded_error(quarantine_error)
                else:
                    first_error = _bounded_error(
                        RuntimeError(
                            f"{first_error}; cleanup quarantine failed: "
                            f"{_bounded_error(quarantine_error)}"
                        )
                    )
        else:
            reaped += 1
    return CleanupResult(reaped, failed, first_error)


def load_queued_artifact(
    item_dir: Path | str,
    *,
    outbox_dir: Path | str | None = None,
) -> QueuedArtifact:
    outbox = _resolve_outbox_dir(outbox_dir)
    item = Path(item_dir).resolve(strict=True)
    if not item.is_dir():
        raise ValueError(f"Queue item is not a directory: {item}")

    category = item.parent.name
    if category not in CATEGORY_REMOTE_FOLDERS:
        raise ValueError(f"Queue item is outside an allowed category: {item}")
    expected_parent = (outbox / "pending" / category).resolve()
    if item.parent != expected_parent:
        raise ValueError(f"Queue item is outside the configured pending root: {item}")

    children: dict[str, Path] = {}
    for index, path in enumerate(item.iterdir(), start=1):
        if index > 2:
            raise ValueError(
                f"Queue item must contain exactly payload and metadata.json: {item}"
            )
        children[path.name] = path
    if set(children) != {"payload", "metadata.json"}:
        raise ValueError(
            f"Queue item must contain exactly payload and metadata.json: {item}"
        )
    payload_path = children["payload"]
    metadata_path = children["metadata.json"]
    _validate_direct_regular_file(payload_path, item)
    _validate_direct_regular_file(metadata_path, item)

    raw_metadata = read_bounded_regular_file(
        metadata_path,
        max_bytes=MAX_METADATA_BYTES,
        label="Queue metadata",
    )
    try:
        metadata = json.loads(raw_metadata.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Queue metadata is not valid UTF-8 JSON: {item}") from error
    if not isinstance(metadata, dict) or set(metadata) != _METADATA_KEYS:
        raise ValueError(
            f"Queue metadata does not match schema version 1: {item}"
        )
    if type(metadata["schema_version"]) is not int or metadata["schema_version"] != 1:
        raise ValueError(f"Unsupported queue metadata schema: {item}")
    if metadata["category"] != category:
        raise ValueError(f"Queue metadata category does not match its parent: {item}")

    suffix = _category_suffix(category)
    remote_filename = metadata["remote_filename"]
    if not isinstance(remote_filename, str):
        raise ValueError(f"Queue metadata has an invalid remote filename: {item}")
    _validate_plain_basename(remote_filename, suffix)
    digest = metadata["sha256"]
    if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError(f"Queue metadata has an invalid SHA-256 digest: {item}")
    if not remote_filename.endswith(f"__sha256-{digest}{suffix}"):
        raise ValueError(f"Remote filename does not contain the recorded checksum: {item}")
    size_bytes = metadata["size_bytes"]
    if type(size_bytes) is not int or size_bytes < 0:
        raise ValueError(f"Queue metadata has an invalid payload size: {item}")
    queued_at_utc = metadata["queued_at_utc"]
    _validate_utc_timestamp(queued_at_utc, item)

    actual_digest, actual_size = _hash_and_size(payload_path)
    if actual_size != size_bytes:
        raise ValueError(f"Queue payload size does not match metadata: {item}")
    if actual_digest != digest:
        raise ValueError(f"Queue payload checksum does not match metadata: {item}")

    return QueuedArtifact(
        item_dir=item,
        payload_path=payload_path,
        metadata_path=metadata_path,
        category=category,
        remote_filename=remote_filename,
        sha256=digest,
        size_bytes=size_bytes,
        queued_at_utc=queued_at_utc,
    )


def remove_delivered_artifact(artifact: QueuedArtifact) -> None:
    item = artifact.item_dir.resolve(strict=True)
    if not item.is_dir():
        raise ValueError(f"Queue item is not a directory: {item}")
    payload = artifact.payload_path.resolve(strict=True)
    metadata = artifact.metadata_path.resolve(strict=True)
    if payload.parent != item or payload.name != "payload":
        raise ValueError("Refusing to remove a payload outside its queue item.")
    if metadata.parent != item or metadata.name != "metadata.json":
        raise ValueError("Refusing to remove metadata outside its queue item.")
    if not payload.is_file() or not metadata.is_file():
        raise ValueError("Refusing to remove non-file queue contents.")
    children = {path.resolve(strict=True) for path in item.iterdir()}
    if children != {payload, metadata}:
        raise ValueError("Refusing to remove a queue item with unexpected contents.")

    outbox = item.parents[2]
    cleanup_root = outbox / "cleanup" / artifact.category
    _ensure_directory(outbox / "cleanup")
    _ensure_directory(cleanup_root)
    cleanup_item = cleanup_root / item.name
    if _lstat_or_none(cleanup_item) is not None:
        raise ValueError(f"Delivered cleanup item already exists: {cleanup_item}")
    os.replace(item, cleanup_item)
    _fsync_directory(item.parent)
    _fsync_directory(cleanup_root)
    _reap_cleanup_item(cleanup_item, outbox)


def _resolve_outbox_dir(outbox_dir: Path | str | None) -> Path:
    return (Path(outbox_dir) if outbox_dir is not None else DEFAULT_OUTBOX_DIR).resolve()


def _queue_entry_sort_key(entry: QueueEntry) -> tuple[int, str]:
    stat_result = _lstat_required(entry.path)
    return stat_result.st_mtime_ns, str(entry.path)


def _ensure_directory(path: Path) -> None:
    stat_result = _lstat_or_none(path)
    if stat_result is not None:
        if not _is_directory_mode(stat_result.st_mode):
            raise ValueError(f"Queue path is not a directory: {path}")
        return
    path.mkdir(parents=True, exist_ok=False)
    _fsync_directory(path.parent)


def _lstat_or_none(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _lstat_required(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"Queue entry disappeared during inspection: {path}") from error


def _is_directory_mode(mode: int) -> bool:
    return stat.S_ISDIR(mode)


def _validate_queue_entry_location(entry: QueueEntry, outbox: Path) -> None:
    pending_root = outbox / "pending"
    staging_root = outbox / "staging"
    source = entry.path
    valid = False
    if entry.kind == "pending-root":
        valid = source == pending_root
    elif entry.kind in {"unexpected-category", "category-root"}:
        valid = source.parent == pending_root
    elif entry.kind == "pending-item":
        valid = (
            source.parent.parent == pending_root
            and source.parent.name in CATEGORY_REMOTE_FOLDERS
        )
    elif entry.kind == "staging-root":
        valid = source == staging_root
    elif entry.kind == "stale-staging":
        valid = source.parent == staging_root
    if not valid:
        raise ValueError(f"Queue entry is outside its expected root: {source}")


def _reap_cleanup_item(item: Path, outbox: Path) -> None:
    category = item.parent.name
    expected_parent = outbox / "cleanup" / category
    if category not in CATEGORY_REMOTE_FOLDERS or item.parent != expected_parent:
        raise ValueError(f"Cleanup item is outside the configured root: {item}")
    item_stat = _lstat_required(item)
    if not _is_directory_mode(item_stat.st_mode):
        raise ValueError(f"Cleanup item is not a directory: {item}")
    children: dict[str, Path] = {}
    for index, path in enumerate(item.iterdir(), start=1):
        if index > 2:
            raise ValueError(f"Cleanup item contains unexpected evidence: {item}")
        children[path.name] = path
    if not set(children) <= {"payload", "metadata.json"}:
        raise ValueError(f"Cleanup item contains unexpected evidence: {item}")
    for name in ("payload", "metadata.json"):
        path = children.get(name)
        if path is None:
            continue
        _validate_direct_regular_file(path, item)
        path.unlink()
    item.rmdir()
    _fsync_directory(item.parent)


def _quarantine_cleanup_item(item: Path, outbox: Path) -> Path:
    category = item.parent.name
    expected_parent = outbox / "cleanup" / category
    if category not in CATEGORY_REMOTE_FOLDERS or item.parent != expected_parent:
        raise ValueError(f"Cleanup item is outside the configured root: {item}")
    destination_root = outbox / "quarantine" / "cleanup" / category
    _ensure_directory(outbox)
    _ensure_directory(outbox / "quarantine")
    _ensure_directory(outbox / "quarantine" / "cleanup")
    _ensure_directory(destination_root)
    destination = _available_quarantine_destination(destination_root, item.name)
    os.replace(item, destination)
    _fsync_directory(item.parent)
    _fsync_directory(destination_root)
    return destination


def _available_quarantine_destination(root: Path, original_name: str) -> Path:
    destination = root / original_name
    if _lstat_or_none(destination) is None:
        return destination
    for _ in range(10):
        destination = root / uuid4().hex
        if _lstat_or_none(destination) is None:
            return destination
    raise RuntimeError(f"Could not allocate a quarantine name under {root}")


def _bounded_error(error: Exception) -> str:
    return (" ".join(str(error).split())[:500] or error.__class__.__name__)


def _category_suffix(category: str) -> str:
    try:
        return CATEGORY_SUFFIXES[category]
    except KeyError as error:
        raise ValueError(f"Unknown artifact category: {category!r}") from error


def _validate_plain_basename(name: str, suffix: str) -> None:
    if not isinstance(name, str) or not name or name in {".", ".."}:
        raise ValueError("Artifact name must be a non-empty plain basename.")
    if (
        "/" in name
        or "\\" in name
        or any(
            unicodedata.category(character).startswith("C")
            for character in name
        )
    ):
        raise ValueError(
            "Artifact name contains a path separator or control character."
        )
    if name != name.strip():
        raise ValueError("Artifact name has ambiguous leading or trailing whitespace.")
    if Path(name).name != name:
        raise ValueError("Artifact name must not contain a path.")
    if not name.endswith(suffix) or name == suffix:
        raise ValueError(f"Artifact name must end with {suffix}.")
    if len(name.encode("utf-8")) > MAX_REMOTE_FILENAME_BYTES:
        raise ValueError("Artifact name is too long for the remote store.")


def _checksum_filename(basename: str, suffix: str, digest: str) -> str:
    stem = basename[: -len(suffix)]
    remote_filename = f"{stem}__sha256-{digest}{suffix}"
    if len(remote_filename.encode("utf-8")) > MAX_REMOTE_FILENAME_BYTES:
        raise ValueError(
            "Checksum-bearing artifact name is too long for the remote store."
        )
    return remote_filename


def _format_utc_timestamp(value: datetime | None) -> str:
    timestamp = value if value is not None else datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Queue timestamp must be timezone-aware.")
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _validate_utc_timestamp(value: object, item: Path) -> None:
    if not isinstance(value, str) or _UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Queue metadata has an invalid UTC timestamp: {item}")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValueError(f"Queue metadata has an invalid UTC timestamp: {item}") from error


def _hash_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size_bytes += len(chunk)
    return digest.hexdigest(), size_bytes


def _validate_direct_regular_file(path: Path, item_dir: Path) -> None:
    resolved = path.resolve(strict=True)
    if resolved.parent != item_dir or not resolved.is_file():
        raise ValueError(f"Queue file escapes or is not regular: {path}")


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
