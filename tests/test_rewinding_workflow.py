from __future__ import annotations

import csv
import io

import pytest

from app import db
from app.constants import (
    STATUS_ARCHIVED,
    STATUS_AWAITING_REWINDING,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_IMPORTED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_RUNNING,
)
from app.importer import IMPORT_FIELDS, import_cards_from_csv


REWINDING_COUNT_ERROR = (
    "Броят за пренавиване трябва да бъде цяло число от 1 до 999."
)


def csv_bytes(*rows: dict[str, str]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")


def extrusion_row(order_number: str, **overrides: str) -> dict[str, str]:
    row = {
        "order_number": order_number,
        "customer": "Rewinding Customer",
        "product_type": "PE film",
        "ordered_gross_kg": "500",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_sequence": "1",
        "raw_material_a": "LDPE; A | 100%",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def import_ready_card(order_number: str) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number)),
        overwrite_existing=False,
    )
    assert result.rows_imported == 1
    with db.connect() as connection:
        return int(
            connection.execute(
                "SELECT id FROM cards WHERE order_number = ?", (order_number,)
            ).fetchone()["id"]
        )


def release_ready_card(order_number: str) -> int:
    card_id = import_ready_card(order_number)
    version = int(db.fetch_admin_card_detail(card_id)["version"])
    assert db.release_card(card_id, 1, 1, version).ok
    return card_id


def set_card_status(card_id: int, status: str) -> None:
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE cards
            SET status = ?,
                finished_at = CASE WHEN ? = ? THEN CURRENT_TIMESTAMP ELSE finished_at END
            WHERE id = ?
            """,
            (status, status, STATUS_AWAITING_REWINDING, card_id),
        )


def card_state(card_id: int) -> dict[str, object]:
    with db.connect() as connection:
        row = connection.execute(
            """
            SELECT status, rewinding_roll_count, version, updated_at
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        assert row is not None
        return dict(row)


def set_rewinding_marker(card_id: int, value: int | None) -> None:
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.update_rewinding_roll_count(card_id, int(card["version"]), value).ok


def timing_snapshot(card_id: int) -> list[dict[str, object]]:
    with db.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, started_at, ended_at, end_reason, created_at, updated_at
                FROM production_time_segments
                WHERE card_id = ?
                ORDER BY id
                """,
                (card_id,),
            ).fetchall()
        ]


def stored_card(card_id: int) -> dict[str, object]:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT * FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()
        assert row is not None
        return dict(row)


def insert_roll(
    card_id: int,
    order_number: str,
    roll_number: int,
    gross_weight: object,
    tare_weight: object,
    net_weight: object,
) -> None:
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO roll_entries (
                card_id, order_number, roll_number,
                gross_weight, tare_weight, net_weight
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                order_number,
                roll_number,
                gross_weight,
                tare_weight,
                net_weight,
            ),
        )


def enter_rewinding_wait(card_id: int) -> None:
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.start_production_timing(card_id, int(card["version"])).ok
    set_rewinding_marker(card_id, 4)
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.finish_card(card_id, int(card["version"])).ok
    assert db.fetch_terminal_card_detail(card_id)["status"] == STATUS_AWAITING_REWINDING


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", None),
        ("   ", None),
        ("0", None),
        ("000", None),
        ("1", 1),
        ("002", 2),
        ("999", 999),
    ],
)
def test_parse_rewinding_roll_count_accepts_supported_values(raw, expected):
    assert db.parse_rewinding_roll_count(raw) == (expected, None)


@pytest.mark.parametrize(
    "raw",
    ["-1", "1.5", "1,5", "1 5", "abc", "1000", "١"],
)
def test_parse_rewinding_roll_count_rejects_invalid_values(raw):
    assert db.parse_rewinding_roll_count(raw) == (None, REWINDING_COUNT_ERROR)


@pytest.mark.parametrize(
    "status",
    [STATUS_RUNNING, STATUS_PAUSED, STATUS_AWAITING_REWINDING],
)
def test_update_rewinding_roll_count_accepts_extrusion_and_waiting_cards(
    connection, status
):
    card_id = release_ready_card(f"610{len(status)}")
    set_card_status(card_id, status)
    before = card_state(card_id)

    result = db.update_rewinding_roll_count(
        card_id, int(before["version"]), 12
    )

    after = card_state(card_id)
    assert result.ok
    assert after["status"] == status
    assert after["rewinding_roll_count"] == 12
    assert after["version"] == int(before["version"]) + 1


def test_update_rewinding_roll_count_clears_waiting_marker_without_changing_status(
    connection,
):
    card_id = release_ready_card("61101")
    set_card_status(card_id, STATUS_AWAITING_REWINDING)
    before = card_state(card_id)
    assert db.update_rewinding_roll_count(card_id, int(before["version"]), 7).ok
    marked = card_state(card_id)

    result = db.update_rewinding_roll_count(card_id, int(marked["version"]), None)

    cleared = card_state(card_id)
    assert result.ok
    assert cleared["status"] == STATUS_AWAITING_REWINDING
    assert cleared["rewinding_roll_count"] is None
    assert cleared["version"] == int(marked["version"]) + 1


@pytest.mark.parametrize(
    "status",
    [STATUS_PENDING, STATUS_COMPLETED, STATUS_ARCHIVED, STATUS_CANCELLED],
)
def test_update_rewinding_roll_count_rejects_cards_outside_allowed_statuses(
    connection, status
):
    card_id = release_ready_card(f"612{len(status)}")
    set_card_status(card_id, status)
    before = card_state(card_id)

    result = db.update_rewinding_roll_count(card_id, int(before["version"]), 4)

    assert not result.ok
    assert card_state(card_id) == before


def test_update_rewinding_roll_count_requires_an_active_shift_for_terminal_writes(
    connection, start_test_shift
):
    card_id = release_ready_card("61301")
    set_card_status(card_id, STATUS_AWAITING_REWINDING)
    before = card_state(card_id)

    blocked = db.update_rewinding_roll_count(
        card_id, int(before["version"]), 8, require_active_shift=True
    )
    start_test_shift()
    allowed = db.update_rewinding_roll_count(
        card_id, int(before["version"]), 8, require_active_shift=True
    )

    assert not blocked.ok
    assert blocked.messages == (db.NO_ACTIVE_SHIFT_MESSAGE,)
    assert allowed.ok
    assert card_state(card_id)["rewinding_roll_count"] == 8


def test_update_rewinding_roll_count_updates_timestamp_and_rejects_stale_write(
    connection,
):
    card_id = release_ready_card("61401")
    set_card_status(card_id, STATUS_AWAITING_REWINDING)
    with db.connect() as setup_connection:
        setup_connection.execute(
            "UPDATE cards SET updated_at = '2000-01-01 00:00:00' WHERE id = ?",
            (card_id,),
        )
    before = card_state(card_id)

    assert db.update_rewinding_roll_count(card_id, int(before["version"]), 9).ok
    saved = card_state(card_id)
    stale = db.update_rewinding_roll_count(card_id, int(before["version"]), 10)

    assert saved["updated_at"] != before["updated_at"]
    assert not stale.ok
    assert stale.messages == (db.STALE_CARD_MESSAGE,)
    assert card_state(card_id) == saved


def test_rewinding_marker_is_exposed_in_terminal_and_admin_card_mappings(connection):
    card_id = release_ready_card("61501")
    set_card_status(card_id, STATUS_RUNNING)
    version = int(card_state(card_id)["version"])
    assert db.update_rewinding_roll_count(card_id, version, 15).ok

    terminal_card = db.fetch_terminal_card_detail(card_id)
    admin_card = db.fetch_admin_card_detail(card_id)
    admin_row = next(card for card in db.fetch_admin_cards() if card["id"] == card_id)
    terminal_row = next(
        card
        for card in db.fetch_cards_by_status((STATUS_RUNNING,))
        if card["id"] == card_id
    )
    with db.connect() as action_connection:
        action_card = db.fetch_admin_production_action_card(
            action_connection, card_id
        )

    assert terminal_card is not None
    assert terminal_card["rewinding_roll_count"] == 15
    assert admin_card is not None
    assert admin_card["rewinding_roll_count"] == 15
    assert admin_row["rewinding_roll_count"] == 15
    assert terminal_row["rewinding_roll_count"] == 15
    assert action_card is not None
    assert action_card["rewinding_roll_count"] == 15


def test_reimport_preserves_rewinding_marker(connection):
    card_id = release_ready_card("61601")
    set_card_status(card_id, STATUS_AWAITING_REWINDING)
    version = int(card_state(card_id)["version"])
    assert db.update_rewinding_roll_count(card_id, version, 21).ok

    result = import_cards_from_csv(
        "replacement.csv",
        csv_bytes(extrusion_row("61601", customer="Replacement Customer")),
        overwrite_existing=True,
    )

    assert result.rows_imported == 1
    detail = db.fetch_admin_card_detail(card_id)
    assert detail is not None
    assert detail["customer"] == "Replacement Customer"
    assert detail["rewinding_roll_count"] == 21


def test_running_card_with_rewinding_marker_ends_extrusion_without_rolls_and_releases_machine(
    connection,
    active_test_shift,
):
    card_id = release_ready_card("61701")
    next_card_id = release_ready_card("61702")
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.start_production_timing(card_id, int(card["version"])).ok
    set_rewinding_marker(card_id, 8)
    before = db.fetch_terminal_card_detail(card_id)
    assert before is not None
    original_machine_id = before["machine_id"]
    original_machine_sequence = before["machine_sequence"]

    result = db.finish_card(card_id, int(before["version"]))

    card = db.fetch_terminal_card_detail(card_id)
    assert result.ok
    assert card is not None
    assert card["status"] == STATUS_AWAITING_REWINDING
    assert card["finished_at"] is not None
    assert card["final_extrusion_shift_occurrence_id"] == active_test_shift["id"]
    assert card["machine_id"] == original_machine_id
    assert card["machine_sequence"] == original_machine_sequence
    with db.connect() as check_connection:
        assert db.fetch_open_timing_segment(check_connection, card_id) is None
        active_queue = check_connection.execute(
            """
            SELECT id, machine_sequence
            FROM cards
            WHERE machine_id = 1
              AND status IN ('pending', 'running', 'paused')
            ORDER BY machine_sequence
            """
        ).fetchall()
    assert [(row["id"], row["machine_sequence"]) for row in active_queue] == [
        (next_card_id, 1),
    ]
    assert card["roll_entries"] == []

    next_card = db.fetch_terminal_card_detail(next_card_id)
    assert next_card is not None
    assert db.start_production_timing(next_card_id, int(next_card["version"])).ok


def test_paused_card_with_rewinding_marker_ends_without_creating_or_moving_timing(
    connection,
    active_test_shift,
):
    card_id = release_ready_card("61801")
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.start_production_timing(card_id, int(card["version"])).ok
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.pause_production_timing(card_id, int(card["version"])).ok
    set_rewinding_marker(card_id, 6)
    before_segments = timing_snapshot(card_id)
    before = db.fetch_terminal_card_detail(card_id)
    assert before is not None

    result = db.finish_card(card_id, int(before["version"]))

    after = db.fetch_terminal_card_detail(card_id)
    assert result.ok
    assert after is not None
    assert after["status"] == STATUS_AWAITING_REWINDING
    assert after["finished_at"] is not None
    assert after["final_extrusion_shift_occurrence_id"] == active_test_shift["id"]
    assert timing_snapshot(card_id) == before_segments


@pytest.mark.parametrize("clear_marker", [False, True])
def test_waiting_card_completion_changes_only_lifecycle_metadata(
    connection,
    active_test_shift,
    clear_marker,
):
    card_id = release_ready_card(f"6190{int(clear_marker)}")
    enter_rewinding_wait(card_id)
    if clear_marker:
        set_rewinding_marker(card_id, None)
    insert_roll(card_id, f"6190{int(clear_marker)}", 1, 25, 1, 24)
    with db.connect() as setup_connection:
        setup_connection.execute(
            "UPDATE cards SET updated_at = '2000-01-01 00:00:00' WHERE id = ?",
            (card_id,),
        )
    before_card = stored_card(card_id)
    before_segments = timing_snapshot(card_id)

    result = db.finish_card(card_id, int(before_card["version"]))

    after_card = stored_card(card_id)
    after_segments = timing_snapshot(card_id)
    changed_columns = {
        key
        for key in before_card
        if before_card[key] != after_card[key]
    }
    assert result.ok
    assert after_card["status"] == STATUS_COMPLETED
    assert after_card["version"] == int(before_card["version"]) + 1
    assert changed_columns == {"status", "version", "updated_at"}
    assert after_segments == before_segments


@pytest.mark.parametrize(
    ("rolls", "expected_message"),
    [
        (
            (),
            "Поне едно бруто тегло на ролка е задължително преди приключване.",
        ),
        (
            ((1, 25, None, None),),
            "Всяка ролка с бруто тегло трябва да има шпула преди приключване.",
        ),
        (
            ((1, 25, 1, None),),
            "Всяка ролка с бруто тегло трябва да има шпула преди приключване.",
        ),
        (
            ((1, None, None, None), (2, 25, 1, 24)),
            "Празните редове между ролките трябва да бъдат коригирани преди приключване.",
        ),
    ],
)
def test_waiting_card_completion_rejects_incomplete_roll_ledger_without_side_effects(
    connection,
    active_test_shift,
    rolls,
    expected_message,
):
    order_number = f"6200{len(rolls)}{sum(1 for row in rolls if row[1] is None)}"
    card_id = release_ready_card(order_number)
    enter_rewinding_wait(card_id)
    for roll_number, gross_weight, tare_weight, net_weight in rolls:
        insert_roll(
            card_id,
            order_number,
            roll_number,
            gross_weight,
            tare_weight,
            net_weight,
        )
    before_card = stored_card(card_id)
    before_segments = timing_snapshot(card_id)

    result = db.finish_card(card_id, int(before_card["version"]))

    assert not result.ok
    assert result.messages == (expected_message,)
    assert stored_card(card_id) == before_card
    assert timing_snapshot(card_id) == before_segments


@pytest.mark.parametrize(
    ("transition", "expected_status"),
    [
        ("active_complete", STATUS_COMPLETED),
        ("active_wait", STATUS_AWAITING_REWINDING),
        ("waiting_complete", STATUS_COMPLETED),
    ],
)
def test_finish_does_not_require_pallet_assignment_for_any_lifecycle_branch(
    connection,
    active_test_shift,
    transition,
    expected_status,
):
    order_number = {
        "active_complete": "62101",
        "active_wait": "62102",
        "waiting_complete": "62103",
    }[transition]
    card_id = release_ready_card(order_number)
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.start_production_timing(card_id, int(card["version"])).ok
    if transition == "active_complete":
        insert_roll(card_id, order_number, 1, 25, 1, 24)
    else:
        set_rewinding_marker(card_id, 5)
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    first_result = db.finish_card(card_id, int(card["version"]))
    assert first_result.ok
    if transition == "waiting_complete":
        insert_roll(card_id, order_number, 1, 25, 1, 24)
        card = db.fetch_terminal_card_detail(card_id)
        assert card is not None
        assert db.finish_card(card_id, int(card["version"])).ok

    final_card = db.fetch_terminal_card_detail(card_id)
    assert final_card is not None
    assert final_card["status"] == expected_status
    assert final_card["current_pallet_number"] is None
    assert all(roll["pallet_number"] is None for roll in final_card["roll_entries"])


def test_active_to_waiting_requires_timing_to_have_started(
    connection,
    active_test_shift,
):
    card_id = release_ready_card("62201")
    with db.connect() as setup_connection:
        setup_connection.execute(
            """
            UPDATE cards
            SET status = ?, rewinding_roll_count = 3
            WHERE id = ?
            """,
            (STATUS_RUNNING, card_id),
        )
    before = stored_card(card_id)

    result = db.finish_card(card_id, int(before["version"]))

    assert not result.ok
    assert result.messages == ("Времето трябва да бъде стартирано преди приключване.",)
    assert stored_card(card_id) == before
    assert timing_snapshot(card_id) == []


def test_stale_active_to_waiting_finish_preserves_open_segment_queue_and_status(
    connection,
    active_test_shift,
):
    card_id = release_ready_card("62301")
    next_card_id = release_ready_card("62302")
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.start_production_timing(card_id, int(card["version"])).ok
    set_rewinding_marker(card_id, 4)
    stale_version = int(db.fetch_terminal_card_detail(card_id)["version"])
    set_rewinding_marker(card_id, 5)
    before_card = stored_card(card_id)
    before_segments = timing_snapshot(card_id)
    with db.connect() as check_connection:
        before_queue = [
            tuple(row)
            for row in check_connection.execute(
                """
                SELECT id, machine_sequence, version
                FROM cards
                WHERE machine_id = 1
                  AND status IN ('pending', 'running', 'paused')
                ORDER BY machine_sequence
                """
            ).fetchall()
        ]

    result = db.finish_card(card_id, stale_version)

    with db.connect() as check_connection:
        after_queue = [
            tuple(row)
            for row in check_connection.execute(
                """
                SELECT id, machine_sequence, version
                FROM cards
                WHERE machine_id = 1
                  AND status IN ('pending', 'running', 'paused')
                ORDER BY machine_sequence
                """
            ).fetchall()
        ]
        assert db.fetch_open_timing_segment(check_connection, card_id) is not None
    assert next_card_id in {row[0] for row in after_queue}
    assert not result.ok
    assert result.messages == (db.STALE_CARD_MESSAGE,)
    assert stored_card(card_id) == before_card
    assert timing_snapshot(card_id) == before_segments
    assert after_queue == before_queue


def test_repeated_active_to_waiting_finish_cannot_reclose_timing_or_change_final_shift(
    connection,
    active_test_shift,
):
    card_id = release_ready_card("62401")
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.start_production_timing(card_id, int(card["version"])).ok
    set_rewinding_marker(card_id, 7)
    loaded_version = int(db.fetch_terminal_card_detail(card_id)["version"])
    assert db.finish_card(card_id, loaded_version).ok
    before_card = stored_card(card_id)
    before_segments = timing_snapshot(card_id)

    repeated = db.finish_card(card_id, loaded_version)

    assert not repeated.ok
    assert repeated.messages == (db.STALE_CARD_MESSAGE,)
    assert stored_card(card_id) == before_card
    assert timing_snapshot(card_id) == before_segments
    assert before_card["final_extrusion_shift_occurrence_id"] == active_test_shift["id"]


def test_waiting_completion_rejects_malformed_open_timing_segment_as_corruption(
    connection,
    active_test_shift,
):
    card_id = release_ready_card("62501")
    enter_rewinding_wait(card_id)
    insert_roll(card_id, "62501", 1, 25, 1, 24)
    with db.connect() as setup_connection:
        setup_connection.execute(
            """
            INSERT INTO production_time_segments (card_id, started_at)
            VALUES (?, '2099-01-01 00:00:00')
            """,
            (card_id,),
        )
    before_card = stored_card(card_id)
    before_segments = timing_snapshot(card_id)

    result = db.finish_card(card_id, int(before_card["version"]))

    assert not result.ok
    assert result.messages == (
        "Карта, изчакваща пренавиване, не трябва да има активен времеви сегмент. Презаредете картата.",
    )
    assert stored_card(card_id) == before_card
    assert timing_snapshot(card_id) == before_segments


def test_active_card_cannot_enter_rewinding_wait_without_active_shift(connection):
    card_id = release_ready_card("62601")
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.start_production_timing(card_id, int(card["version"])).ok
    set_rewinding_marker(card_id, 2)
    before_card = stored_card(card_id)
    before_segments = timing_snapshot(card_id)

    result = db.finish_card(card_id, int(before_card["version"]))

    assert not result.ok
    assert result.messages == (db.NO_ACTIVE_SHIFT_MESSAGE,)
    assert stored_card(card_id) == before_card
    assert timing_snapshot(card_id) == before_segments


@pytest.mark.parametrize("rewinding_roll_count", [None, 5])
def test_running_finish_rejects_closed_only_timing_history_without_side_effects(
    connection,
    active_test_shift,
    rewinding_roll_count,
):
    order_number = f"6270{int(rewinding_roll_count is not None)}"
    card_id = release_ready_card(order_number)
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.start_production_timing(card_id, int(card["version"])).ok
    if rewinding_roll_count is None:
        insert_roll(card_id, order_number, 1, 25, 1, 24)
    else:
        set_rewinding_marker(card_id, rewinding_roll_count)
    with db.connect() as setup_connection:
        setup_connection.execute(
            """
            UPDATE production_time_segments
            SET ended_at = started_at,
                end_reason = 'correction'
            WHERE card_id = ?
              AND ended_at IS NULL
            """,
            (card_id,),
        )
    before_card = stored_card(card_id)
    before_segments = timing_snapshot(card_id)

    result = db.finish_card(card_id, int(before_card["version"]))

    assert not result.ok
    assert result.messages == (
        "Картите в изработване трябва да имат активен времеви сегмент. Презаредете картата.",
    )
    assert stored_card(card_id) == before_card
    assert timing_snapshot(card_id) == before_segments


def test_pending_card_with_historical_timing_cannot_enter_an_unapproved_finish_branch(
    connection,
    active_test_shift,
):
    card_id = release_ready_card("62801")
    insert_roll(card_id, "62801", 1, 25, 1, 24)
    with db.connect() as setup_connection:
        setup_connection.execute(
            """
            INSERT INTO production_time_segments (
                card_id, started_at, ended_at, end_reason
            )
            VALUES (
                ?, '2026-07-26 10:00:00', '2026-07-26 10:05:00', 'correction'
            )
            """,
            (card_id,),
        )
    before_card = stored_card(card_id)
    before_segments = timing_snapshot(card_id)

    result = db.finish_card(card_id, int(before_card["version"]))

    assert not result.ok
    assert result.messages == (
        "Само карти в изработване или паузирани карти могат да приключат екструдирането.",
    )
    assert stored_card(card_id) == before_card
    assert timing_snapshot(card_id) == before_segments


@pytest.mark.parametrize("rewinding_roll_count", [None, 5])
def test_paused_finish_rejects_malformed_open_segment_without_side_effects(
    connection,
    active_test_shift,
    rewinding_roll_count,
):
    order_number = f"6290{int(rewinding_roll_count is not None)}"
    card_id = release_ready_card(order_number)
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.start_production_timing(card_id, int(card["version"])).ok
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.pause_production_timing(card_id, int(card["version"])).ok
    if rewinding_roll_count is None:
        insert_roll(card_id, order_number, 1, 25, 1, 24)
    else:
        set_rewinding_marker(card_id, rewinding_roll_count)
    with db.connect() as setup_connection:
        setup_connection.execute(
            """
            INSERT INTO production_time_segments (card_id, started_at)
            VALUES (?, '2099-01-01 00:00:00')
            """,
            (card_id,),
        )
    before_card = stored_card(card_id)
    before_segments = timing_snapshot(card_id)

    result = db.finish_card(card_id, int(before_card["version"]))

    assert not result.ok
    assert result.messages == (
        "Паузирани карти не трябва да имат активен времеви сегмент. Презаредете картата.",
    )
    assert stored_card(card_id) == before_card
    assert timing_snapshot(card_id) == before_segments


def test_returned_rolls_all_count_toward_the_shift_that_ended_extrusion(
    connection,
    start_test_shift,
):
    shift_one = start_test_shift("1")
    card_id = release_ready_card("63001")
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.start_production_timing(card_id, int(card["version"])).ok
    assert db.end_shift(int(shift_one["id"]), int(shift_one["version"])).ok

    shift_two = start_test_shift("2")
    set_rewinding_marker(card_id, 2)
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    assert db.finish_card(card_id, int(card["version"])).ok
    waiting = db.fetch_terminal_card_detail(card_id)
    assert waiting is not None
    assert waiting["final_extrusion_shift_occurrence_id"] == shift_two["id"]
    assert db.end_shift(int(shift_two["id"]), int(shift_two["version"])).ok

    shift_three = start_test_shift("3")
    assert db.add_roll_gross_weight(
        card_id,
        waiting["version"],
        "20.00",
        tare_weight="1.00",
        require_active_shift=True,
    ).ok
    after_first = db.fetch_terminal_card_detail(card_id)
    assert after_first is not None
    assert db.add_roll_gross_weight(
        card_id,
        after_first["version"],
        "30.00",
        require_active_shift=True,
    ).ok

    rolls = db.fetch_terminal_card_detail(card_id)["roll_entries"]
    shift_two_summary = db.fetch_shift_summary(int(shift_two["id"]))
    shift_three_summary = db.fetch_shift_summary(int(shift_three["id"]))
    assert [roll["shift_occurrence_id"] for roll in rolls] == [
        shift_two["id"],
        shift_two["id"],
    ]
    assert shift_two_summary is not None
    assert shift_two_summary["roll_count"] == 2
    assert shift_two_summary["total_gross_weight"] == "50.00"
    assert shift_three_summary is not None
    assert shift_three_summary["roll_count"] == 0


def test_waiting_material_and_batch_correction_preserves_lifecycle_and_marker(
    connection,
    active_test_shift,
):
    card_id = release_ready_card("63002")
    set_card_status(card_id, STATUS_AWAITING_REWINDING)
    assert db.update_rewinding_roll_count(
        card_id,
        int(card_state(card_id)["version"]),
        6,
    ).ok
    before = stored_card(card_id)

    result = db.update_terminal_recipe_actual_entries(
        card_id,
        int(before["version"]),
        {
            "raw_material_a": {
                "actual_material_used": "Corrected LDPE",
                "batch_lot": "WAIT-42",
            }
        },
        raw_material_brand_grade="Grade W",
        require_active_shift=True,
    )
    after = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert after is not None
    assert after["status"] == STATUS_AWAITING_REWINDING
    assert after["rewinding_roll_count"] == 6
    assert after["actual_raw_material_used"] == "Corrected LDPE"
    assert after["raw_material_brand_grade"] == "Grade W"
    assert after["raw_material_batch_lot"] == "WAIT-42"
    assert after["recipe_actual_entries"]["raw_material_a"]["batch_lot"] == "WAIT-42"


def test_waiting_card_rejects_lifecycle_and_queue_actions(connection, active_test_shift):
    card_id = release_ready_card("63003")
    set_card_status(card_id, STATUS_AWAITING_REWINDING)
    before = stored_card(card_id)

    results = (
        db.start_production_timing(card_id, int(before["version"])),
        db.pause_production_timing(card_id, int(before["version"])),
        db.resume_production_timing(card_id, int(before["version"])),
        db.cancel_card(card_id, int(before["version"])),
        db.archive_completed_card(card_id, int(before["version"])),
        db.update_card_planning(card_id, int(before["version"]), 2, 1),
    )

    assert all(not result.ok for result in results)
    assert stored_card(card_id) == before
