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


def insert_shift_occurrence(
    connection: sqlite3.Connection,
    shift_number: int,
    started_at: str,
    ended_at: str | None = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO shift_occurrences (shift_number, started_at, ended_at)
        VALUES (?, ?, ?)
        """,
        (shift_number, started_at, ended_at),
    )
    return int(cursor.lastrowid)


def insert_summary_card(
    connection: sqlite3.Connection,
    order_number: str,
    customer: str | None,
    product_type: str | None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO cards (order_number, customer, product_type)
        VALUES (?, ?, ?)
        """,
        (order_number, customer, product_type),
    )
    return int(cursor.lastrowid)


def insert_summary_roll(
    connection: sqlite3.Connection,
    card_id: int,
    order_number: str,
    roll_number: int,
    gross_weight: str | None,
    shift_occurrence_id: int | None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO roll_entries (
            card_id, order_number, roll_number, gross_weight, shift_occurrence_id
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (card_id, order_number, roll_number, gross_weight, shift_occurrence_id),
    )
    return int(cursor.lastrowid)


def connect_with_writer_after_query_snapshot(
    monkeypatch,
    query_marker: str,
    writer_action,
) -> list[bool]:
    original_connect = db.connect
    writer_committed = [False]

    def instrumented_connect() -> sqlite3.Connection:
        read_connection = original_connect()
        target_query_started = False

        def trace(statement: str) -> None:
            nonlocal target_query_started
            target_query_started = query_marker in statement

        def progress() -> int:
            if target_query_started and not writer_committed[0]:
                writer_action()
                writer_committed[0] = True
                read_connection.set_progress_handler(None, 0)
            return 0

        read_connection.set_trace_callback(trace)
        read_connection.set_progress_handler(progress, 1)
        return read_connection

    monkeypatch.setattr(db, "connect", instrumented_connect)
    return writer_committed


def test_shift_summary_groups_distinct_orders_roll_count_and_gross_weight(connection):
    first_shift_id = insert_shift_occurrence(
        connection, 1, "2026-07-25 06:00:00"
    )
    other_shift_id = insert_shift_occurrence(
        connection, 2, "2026-07-25 14:00:00", "2026-07-25 22:00:00"
    )
    later_order_card_id = insert_summary_card(
        connection, "ORD-200", "Customer two", "Product two"
    )
    earlier_order_card_id = insert_summary_card(
        connection, "ORD-100", "Customer one", "Product one"
    )
    insert_summary_roll(
        connection, later_order_card_id, "ORD-200", 1, "100.25", first_shift_id
    )
    insert_summary_roll(
        connection, later_order_card_id, "ORD-200", 2, "200", first_shift_id
    )
    insert_summary_roll(
        connection, earlier_order_card_id, "ORD-100", 1, "10", first_shift_id
    )
    insert_summary_roll(
        connection, earlier_order_card_id, "ORD-100", 2, "999", other_shift_id
    )
    insert_summary_roll(
        connection, later_order_card_id, "ORD-200", 3, "500", None
    )
    connection.commit()

    summary = db.fetch_shift_summary(first_shift_id)

    assert summary == {
        "id": first_shift_id,
        "shift_number": 1,
        "started_at": "2026-07-25 06:00:00",
        "ended_at": None,
        "distinct_item_count": 2,
        "roll_count": 3,
        "total_gross_weight": "310.25",
        "orders": [
            {
                "card_id": earlier_order_card_id,
                "order_number": "ORD-100",
                "customer": "Customer one",
                "product_type": "Product one",
                "roll_count": 1,
                "gross_weight": "10.00",
            },
            {
                "card_id": later_order_card_id,
                "order_number": "ORD-200",
                "customer": "Customer two",
                "product_type": "Product two",
                "roll_count": 2,
                "gross_weight": "300.25",
            },
        ],
    }


def test_shift_summary_counts_all_linked_rolls_and_sums_available_gross_weight(connection):
    shift_id = insert_shift_occurrence(connection, 1, "2026-07-25 06:00:00")
    card_id = insert_summary_card(connection, "ORD-100", None, None)
    insert_summary_roll(connection, card_id, "ORD-100", 1, "15.5", shift_id)
    insert_summary_roll(connection, card_id, "ORD-100", 2, None, shift_id)
    connection.commit()

    summary = db.fetch_shift_summary(shift_id)

    assert summary is not None
    assert summary["distinct_item_count"] == 1
    assert summary["roll_count"] == 2
    assert summary["total_gross_weight"] == "15.50"
    assert summary["orders"] == [
        {
            "card_id": card_id,
            "order_number": "ORD-100",
            "customer": None,
            "product_type": None,
            "roll_count": 2,
            "gross_weight": "15.50",
        }
    ]


def test_shift_summary_reflects_current_card_details_roll_corrections_and_deletions(connection):
    shift_id = insert_shift_occurrence(connection, 1, "2026-07-25 06:00:00")
    card_id = insert_summary_card(
        connection, "ORD-100", "Original customer", "Original product"
    )
    retained_roll_id = insert_summary_roll(
        connection, card_id, "ORD-100", 1, "10", shift_id
    )
    deleted_roll_id = insert_summary_roll(
        connection, card_id, "ORD-100", 2, "4", shift_id
    )
    connection.commit()

    before = db.fetch_shift_summary(shift_id)
    connection.execute(
        """
        UPDATE cards
        SET order_number = ?, customer = ?, product_type = ?
        WHERE id = ?
        """,
        ("ORD-050", "Corrected customer", "Corrected product", card_id),
    )
    connection.execute(
        "UPDATE roll_entries SET gross_weight = ? WHERE id = ?",
        ("19.75", retained_roll_id),
    )
    connection.execute("DELETE FROM roll_entries WHERE id = ?", (deleted_roll_id,))
    connection.commit()

    after = db.fetch_shift_summary(shift_id)

    assert before is not None
    assert before["roll_count"] == 2
    assert before["total_gross_weight"] == "14.00"
    assert after is not None
    assert after["distinct_item_count"] == 1
    assert after["roll_count"] == 1
    assert after["total_gross_weight"] == "19.75"
    assert after["orders"] == [
        {
            "card_id": card_id,
            "order_number": "ORD-050",
            "customer": "Corrected customer",
            "product_type": "Corrected product",
            "roll_count": 1,
            "gross_weight": "19.75",
        }
    ]


def test_empty_shift_summary_has_zero_totals_and_no_order_rows(connection):
    shift_id = insert_shift_occurrence(connection, 1, "2026-07-25 06:00:00")
    connection.commit()

    summary = db.fetch_shift_summary(shift_id)
    state = db.fetch_shift_window_state()

    assert summary == {
        "id": shift_id,
        "shift_number": 1,
        "started_at": "2026-07-25 06:00:00",
        "ended_at": None,
        "distinct_item_count": 0,
        "roll_count": 0,
        "total_gross_weight": "0.00",
        "orders": [],
    }
    assert state["active_shift"] == active_shift()
    assert state["completed_shifts"] == []
    assert state["suggested_shift_number"] == 1
    assert state["configuration"] == configuration()


def test_completed_shift_history_is_newest_first_and_uses_live_totals(connection):
    older_shift_id = insert_shift_occurrence(
        connection, 1, "2026-07-24 06:00:00", "2026-07-25 14:00:00"
    )
    newest_shift_id = insert_shift_occurrence(
        connection, 2, "2026-07-25 06:00:00", "2026-07-25 14:00:00"
    )
    older_card_id = insert_summary_card(connection, "ORD-100", None, None)
    newest_card_id = insert_summary_card(connection, "ORD-200", None, None)
    newest_second_card_id = insert_summary_card(connection, "ORD-300", None, None)
    insert_summary_roll(connection, older_card_id, "ORD-100", 1, "5", older_shift_id)
    newest_roll_id = insert_summary_roll(
        connection, newest_card_id, "ORD-200", 1, "10", newest_shift_id
    )
    insert_summary_roll(
        connection, newest_second_card_id, "ORD-300", 1, None, newest_shift_id
    )
    connection.commit()

    initial_history = db.fetch_completed_shifts()
    connection.execute(
        "UPDATE roll_entries SET gross_weight = ? WHERE id = ?",
        ("12.5", newest_roll_id),
    )
    connection.commit()
    corrected_history = db.fetch_completed_shifts()

    assert initial_history == [
        {
            "id": newest_shift_id,
            "shift_number": 2,
            "started_at": "2026-07-25 06:00:00",
            "ended_at": "2026-07-25 14:00:00",
            "distinct_item_count": 2,
            "roll_count": 2,
            "total_gross_weight": "10.00",
        },
        {
            "id": older_shift_id,
            "shift_number": 1,
            "started_at": "2026-07-24 06:00:00",
            "ended_at": "2026-07-25 14:00:00",
            "distinct_item_count": 1,
            "roll_count": 1,
            "total_gross_weight": "5.00",
        },
    ]
    assert corrected_history[0]["total_gross_weight"] == "12.50"


def test_shift_summary_uses_one_snapshot_across_concurrent_roll_deletion(
    connection,
    monkeypatch,
):
    assert connection.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
    shift_id = insert_shift_occurrence(connection, 1, "2026-07-25 06:00:00")
    card_id = insert_summary_card(connection, "ORD-100", None, None)
    insert_summary_roll(connection, card_id, "ORD-100", 1, "10", shift_id)
    deleted_roll_id = insert_summary_roll(connection, card_id, "ORD-100", 2, "4", shift_id)
    connection.commit()

    writer = sqlite3.connect(db.DB_PATH)
    try:
        def delete_roll() -> None:
            writer.execute("DELETE FROM roll_entries WHERE id = ?", (deleted_roll_id,))
            writer.commit()

        writer_committed = connect_with_writer_after_query_snapshot(
            monkeypatch,
            "COUNT(DISTINCT roll_entries.card_id)",
            delete_roll,
        )

        summary = db.fetch_shift_summary(shift_id)
    finally:
        writer.close()

    assert writer_committed == [True]
    assert summary is not None
    assert summary["roll_count"] == sum(
        int(order["roll_count"]) for order in summary["orders"]
    )


def test_shift_window_state_uses_one_snapshot_across_concurrent_shift_end(
    connection,
    monkeypatch,
):
    assert connection.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
    shift_id = insert_shift_occurrence(connection, 1, "2026-07-25 06:00:00")
    connection.commit()

    writer = sqlite3.connect(db.DB_PATH)
    try:
        def end_shift() -> None:
            writer.execute(
                "UPDATE shift_occurrences SET ended_at = ? WHERE id = ?",
                ("2026-07-25 14:00:00", shift_id),
            )
            writer.commit()

        writer_committed = connect_with_writer_after_query_snapshot(
            monkeypatch,
            "WHERE ended_at IS NULL",
            end_shift,
        )

        state = db.fetch_shift_window_state()
    finally:
        writer.close()

    assert writer_committed == [True]
    active_shift = state["active_shift"]
    active_ids = {int(active_shift["id"])} if active_shift is not None else set()
    completed_ids = {int(shift["id"]) for shift in state["completed_shifts"]}
    assert active_ids.isdisjoint(completed_ids)
