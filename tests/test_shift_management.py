from __future__ import annotations

import sqlite3

from app import db


SHIFT_COUNT_FIELD = "Брой смени"
SHIFT_NUMBER_FIELD = "Номер на смяна"


def configuration() -> dict[str, object]:
    return db.fetch_terminal_configuration()


def active_shift() -> dict[str, object]:
    shift = db.fetch_active_shift()
    assert shift is not None
    return shift


def end_active_shift() -> dict[str, object]:
    shift = active_shift()
    result = db.end_shift(int(shift["id"]), int(shift["version"]))
    assert result.ok
    return shift


def production_snapshot(connection: sqlite3.Connection) -> dict[str, tuple[tuple[object, ...], ...]]:
    return {
        table_name: tuple(
            tuple(row)
            for row in connection.execute(
                f"SELECT * FROM {table_name} ORDER BY id"
            ).fetchall()
        )
        for table_name in ("cards", "machines", "production_time_segments")
    }


def test_shift_count_defaults_to_four_and_rejects_non_positive_values(connection):
    initial = configuration()

    assert initial["shift_count"] == 4
    for invalid_value in ("", " ", "0", "-1", "1.5", "four"):
        result = db.update_shift_count(int(initial["version"]), invalid_value)

        assert not result.ok
        assert result.messages == (
            f"{SHIFT_COUNT_FIELD} трябва да е положително цяло число.",
        )
    assert configuration() == initial


def test_shift_count_update_checks_loaded_version_and_preserves_history(connection):
    initial = configuration()
    assert db.start_shift("4", int(initial["version"])).ok
    completed = end_active_shift()

    updated = db.update_shift_count(int(initial["version"]), "3")
    stale = db.update_shift_count(int(initial["version"]), "2")

    assert updated.ok
    assert not stale.ok
    assert stale.messages == (db.STALE_CONFIGURATION_MESSAGE,)
    assert configuration()["shift_count"] == 3
    with db.connect() as read_connection:
        history = read_connection.execute(
            "SELECT * FROM shift_occurrences WHERE id = ?", (completed["id"],)
        ).fetchone()
    assert history is not None
    assert history["shift_number"] == 4
    assert history["ended_at"] is not None


def test_only_one_shift_occurrence_can_be_open_globally(connection):
    initial = configuration()

    first_result = db.start_shift("1", int(initial["version"]))
    second_result = db.start_shift("2", int(initial["version"]))

    assert first_result.ok
    assert not second_result.ok
    assert second_result.messages == (db.STALE_SHIFT_MESSAGE,)
    with db.connect() as read_connection:
        open_shifts = read_connection.execute(
            "SELECT id, shift_number FROM shift_occurrences WHERE ended_at IS NULL"
        ).fetchall()
    assert [(row["shift_number"]) for row in open_shifts] == [1]


def test_next_shift_suggestion_wraps_and_operator_may_override_it(connection):
    initial = configuration()

    assert db.suggest_next_shift_number() == 1
    assert db.start_shift("4", int(initial["version"])).ok
    end_active_shift()
    assert db.suggest_next_shift_number() == 1

    assert db.start_shift("2", int(configuration()["version"])).ok
    assert active_shift()["shift_number"] == 2
    end_active_shift()
    assert db.suggest_next_shift_number() == 3


def test_active_shift_number_correction_preserves_identity_and_start_time(connection):
    initial = configuration()
    assert db.start_shift("1", int(initial["version"])).ok
    before = active_shift()

    result = db.update_active_shift_number(
        int(before["id"]), int(before["version"]), "3"
    )
    after = active_shift()

    assert result.ok
    assert after["id"] == before["id"]
    assert after["started_at"] == before["started_at"]
    assert after["shift_number"] == 3
    assert after["version"] == before["version"] + 1


def test_reduced_shift_count_keeps_removed_open_number_until_normal_end(connection):
    initial = configuration()
    assert db.start_shift("4", int(initial["version"])).ok

    reduced = db.update_shift_count(int(initial["version"]), "3")

    assert reduced.ok
    assert active_shift()["shift_number"] == 4
    end_active_shift()
    assert db.suggest_next_shift_number() == 1


def test_shift_number_validation_uses_current_configuration(connection):
    initial = configuration()
    assert db.start_shift("4", int(initial["version"])).ok
    opened = active_shift()
    assert db.update_shift_count(int(initial["version"]), "3").ok

    invalid_correction = db.update_active_shift_number(
        int(opened["id"]), int(opened["version"]), "4"
    )

    assert not invalid_correction.ok
    assert invalid_correction.messages == (
        "Номер на смяна трябва да е между 1 и 3.",
    )
    assert active_shift()["shift_number"] == 4
    end_active_shift()

    for invalid_value in ("", "0", "four", "4"):
        result = db.start_shift(invalid_value, int(configuration()["version"]))

        assert not result.ok
    assert db.fetch_active_shift() is None


def test_shift_lifecycle_blocks_stale_writes(connection):
    initial = configuration()
    assert db.update_shift_count(int(initial["version"]), "5").ok
    stale_start = db.start_shift("1", int(initial["version"]))

    assert not stale_start.ok
    assert stale_start.messages == (db.STALE_CONFIGURATION_MESSAGE,)
    current_configuration = configuration()
    assert db.start_shift("1", int(current_configuration["version"])).ok
    opened = active_shift()
    assert db.update_active_shift_number(
        int(opened["id"]), int(opened["version"]), "2"
    ).ok

    stale_correction = db.update_active_shift_number(
        int(opened["id"]), int(opened["version"]), "3"
    )
    stale_end = db.end_shift(int(opened["id"]), int(opened["version"]))

    assert not stale_correction.ok
    assert stale_correction.messages == (db.STALE_SHIFT_MESSAGE,)
    assert not stale_end.ok
    assert stale_end.messages == (db.STALE_SHIFT_MESSAGE,)
    assert active_shift()["shift_number"] == 2


def test_init_db_restores_open_shift_and_latest_selected_number(connection):
    initial = configuration()
    assert db.start_shift("3", int(initial["version"])).ok
    opened = active_shift()

    db.init_db()

    restored = active_shift()
    assert restored["id"] == opened["id"]
    assert restored["shift_number"] == 3
    end_active_shift()
    db.init_db()
    assert db.suggest_next_shift_number() == 4


def test_empty_shift_can_end_without_touching_production_state(connection):
    connection.execute(
        "INSERT INTO cards (order_number) VALUES ('shift-isolation-card')"
    )
    card_id = int(
        connection.execute(
            "SELECT id FROM cards WHERE order_number = 'shift-isolation-card'"
        ).fetchone()["id"]
    )
    connection.execute(
        "INSERT INTO production_time_segments (card_id, started_at) VALUES (?, ?)",
        (card_id, "2026-07-25 06:00:00"),
    )
    connection.commit()
    before = production_snapshot(connection)

    assert db.start_shift("1", int(configuration()["version"])).ok
    opened = active_shift()
    assert db.update_active_shift_number(
        int(opened["id"]), int(opened["version"]), "2"
    ).ok
    corrected = active_shift()
    assert db.end_shift(int(corrected["id"]), int(corrected["version"])).ok

    assert production_snapshot(connection) == before


def test_reused_shift_number_creates_distinct_occurrence_identity(connection):
    initial = configuration()
    assert db.start_shift("1", int(initial["version"])).ok
    first = end_active_shift()

    assert db.start_shift("1", int(configuration()["version"])).ok
    second = active_shift()

    assert second["id"] != first["id"]
    assert second["started_at"] >= first["started_at"]
    with db.connect() as read_connection:
        occurrences = read_connection.execute(
            "SELECT id, shift_number, ended_at FROM shift_occurrences ORDER BY id"
        ).fetchall()
    assert [(row["id"], row["shift_number"], row["ended_at"] is None) for row in occurrences] == [
        (first["id"], 1, False),
        (second["id"], 1, True),
    ]
