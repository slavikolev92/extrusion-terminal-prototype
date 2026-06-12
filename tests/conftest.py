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
