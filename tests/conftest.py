from __future__ import annotations

import sqlite3
import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from app import db


@pytest.fixture
def temp_db_path(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    test_data_dir = Path.cwd() / ".test-runtime" / uuid4().hex
    database_path = test_data_dir / "extrusion_terminal_test.sqlite3"
    monkeypatch.setattr(db, "DATA_DIR", test_data_dir)
    monkeypatch.setattr(db, "DB_PATH", database_path)
    db.init_db()
    try:
        yield database_path
    finally:
        shutil.rmtree(test_data_dir, ignore_errors=True)


@pytest.fixture
def connection(temp_db_path: Path) -> Iterator[sqlite3.Connection]:
    with db.connect() as conn:
        yield conn


@pytest.fixture
def start_test_shift(connection: sqlite3.Connection):
    def start(shift_number: str = "1") -> dict[str, object]:
        configuration = db.fetch_terminal_configuration()
        result = db.start_shift(shift_number, int(configuration["version"]))
        assert result.ok
        active_shift = db.fetch_active_shift()
        assert active_shift is not None
        return active_shift

    return start


@pytest.fixture
def active_test_shift(start_test_shift) -> dict[str, object]:
    return start_test_shift()
