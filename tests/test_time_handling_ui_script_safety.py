from __future__ import annotations

import sqlite3
from pathlib import Path

from app import db
from scripts import create_print_template_fixture as fixture


def test_dense_fixture_uses_canonical_utc_times_and_an_active_shift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture_path = tmp_path / ".test-runtime/time-handling/fixture.sqlite3"
    monkeypatch.setattr(fixture, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(db, "DATA_DIR", fixture_path.parent)
    monkeypatch.setattr(db, "DB_PATH", fixture_path)

    resolved_path = fixture.resolve_fixture_db_path(
        ".test-runtime/time-handling/fixture.sqlite3"
    )
    fixture.reset_database(resolved_path)
    card_id = fixture.create_dense_completed_card("TIME-HANDLING-SAFETY")

    connection = sqlite3.connect(resolved_path)
    connection.row_factory = sqlite3.Row
    try:
        card = connection.execute(
            "SELECT first_started_at, finished_at FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()
        segments = connection.execute(
            """
            SELECT started_at, ended_at
            FROM production_time_segments
            WHERE card_id = ?
            ORDER BY id
            """,
            (card_id,),
        ).fetchall()
        active_shift = connection.execute(
            """
            SELECT shift_number, started_at, ended_at
            FROM shift_occurrences
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()

    assert card is not None
    assert card["first_started_at"] == "2026-06-18 21:35:00"
    assert card["finished_at"] == "2026-06-19 04:15:00"
    assert [tuple(row) for row in segments] == [
        ("2026-06-18 21:35:00", "2026-06-18 23:40:00"),
        ("2026-06-19 00:00:00", "2026-06-19 01:50:00"),
        ("2026-06-19 02:20:00", "2026-06-19 04:15:00"),
    ]
    assert tuple(active_shift) == (1, "2026-06-19 04:00:00", None)


def test_ui_verifier_source_contains_required_safety_and_browser_checks() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts/verify_time_handling_ui.mjs"
    ).read_text()

    assert "artifacts/ui-checks" in source
    assert "realpathSync" in source
    assert "19.06.2026 00:35:00" in source
    assert "2026-06-19 00:35:00" in source
    assert "19.06.2026 00:35" in source
    assert "#admin-card-save-form" in source
    assert 'click("#history-open")' in source
    assert "page.pdf" in source
    assert "data/extrusion_terminal.sqlite3" not in source
    assert "production-db" not in source
