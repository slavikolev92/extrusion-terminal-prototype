from __future__ import annotations

import sqlite3
import shutil
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import Callable
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


@pytest.fixture
def interleave_committed_card_version(monkeypatch: pytest.MonkeyPatch):
    def run(
        card_id: int,
        loaded_version: int,
        action: Callable[[], db.RuleResult],
    ) -> db.RuleResult:
        writer = db.connect()
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(
            """
            UPDATE cards
            SET customer = 'Concurrent writer',
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (card_id,),
        )

        stale_read_reached = Event()
        release_stale_reader = Event()
        original_validate = db.validate_loaded_card_version

        def synchronize_stale_read(card, candidate_version):
            result = original_validate(card, candidate_version)
            if (
                result.ok
                and card is not None
                and int(card["id"]) == card_id
                and candidate_version == loaded_version
            ):
                stale_read_reached.set()
                assert release_stale_reader.wait(timeout=2)
            return result

        monkeypatch.setattr(db, "validate_loaded_card_version", synchronize_stale_read)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(action)
                assert stale_read_reached.wait(timeout=2)
                writer.commit()
                release_stale_reader.set()
                return future.result(timeout=2)
        finally:
            release_stale_reader.set()
            writer.close()

    return run
