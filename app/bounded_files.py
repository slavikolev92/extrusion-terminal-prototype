from __future__ import annotations

import os
import stat
from pathlib import Path


def read_bounded_regular_file(
    path: Path | str,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    """Read one direct regular file without following its final path component."""
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValueError("Maximum file size must be a non-negative integer.")

    file_path = Path(path)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        descriptor = os.open(file_path, flags)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise ValueError(f"Unable to read {label.lower()}: {file_path}") from error

    try:
        try:
            file_status = os.fstat(descriptor)
        except OSError as error:
            raise ValueError(f"Unable to inspect {label.lower()}: {file_path}") from error
        if not stat.S_ISREG(file_status.st_mode):
            raise ValueError(f"{label} is not a regular file: {file_path}")
        if file_status.st_size > max_bytes:
            raise ValueError(f"{label} is too large: {file_path}")
        contents = bytearray()
        try:
            while len(contents) < max_bytes + 1:
                chunk = os.read(descriptor, (max_bytes + 1) - len(contents))
                if not chunk:
                    break
                contents.extend(chunk)
        except OSError as error:
            raise ValueError(f"Unable to read {label.lower()}: {file_path}") from error
        if len(contents) > max_bytes:
            raise ValueError(f"{label} is too large: {file_path}")
        return bytes(contents)
    finally:
        os.close(descriptor)
