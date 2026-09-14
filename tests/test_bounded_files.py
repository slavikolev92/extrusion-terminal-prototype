from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.bounded_files import read_bounded_regular_file


def test_bounded_reader_accepts_a_regular_file_at_the_exact_limit(tmp_path: Path):
    source = tmp_path / "exact.bin"
    source.write_bytes(b"x" * 32)

    assert read_bounded_regular_file(source, max_bytes=32, label="Test file") == (
        b"x" * 32
    )


def test_bounded_reader_rejects_sparse_file_before_reading_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "oversized.bin"
    with source.open("wb") as handle:
        handle.truncate(33)

    def unexpected_read(_fd: int, _size: int) -> bytes:
        raise AssertionError("oversized file content must not be read")

    monkeypatch.setattr("app.bounded_files.os.read", unexpected_read)

    with pytest.raises(ValueError, match="too large"):
        read_bounded_regular_file(source, max_bytes=32, label="Test file")


def test_bounded_reader_rejects_fifo_without_waiting_for_a_writer(tmp_path: Path):
    source = tmp_path / "state.json"
    os.mkfifo(source)

    with pytest.raises(ValueError, match="regular file"):
        read_bounded_regular_file(source, max_bytes=32, label="Test file")


def test_bounded_reader_rejects_symlink_to_unbounded_device(tmp_path: Path):
    source = tmp_path / "state.json"
    source.symlink_to("/dev/zero")

    with pytest.raises(ValueError, match="Unable to read"):
        read_bounded_regular_file(source, max_bytes=32, label="Test file")


def test_bounded_reader_completes_short_reads_within_limit_plus_one_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = tmp_path / "exact.bin"
    source.write_bytes(b"x" * 32)
    real_read = os.read
    requested_sizes: list[int] = []

    def recording_short_read(fd: int, size: int) -> bytes:
        requested_sizes.append(size)
        return real_read(fd, min(size, 7))

    monkeypatch.setattr("app.bounded_files.os.read", recording_short_read)

    assert read_bounded_regular_file(source, max_bytes=32, label="Test file") == (
        b"x" * 32
    )
    assert requested_sizes == [33, 26, 19, 12, 5, 1]
    assert all(size <= 33 for size in requested_sizes)
