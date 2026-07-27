from __future__ import annotations

import asyncio
import csv
import io

from app import db
from app.constants import STATUS_AWAITING_REWINDING, STATUS_COMPLETED, STATUS_IMPORTED
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import app, terminal_context, terminal_snapshot_route


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
        "customer": "Sync Customer",
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
                "SELECT id FROM cards WHERE order_number = ?",
                (order_number,),
            ).fetchone()["id"]
        )


def release_ready_card(order_number: str, machine_id: int, machine_sequence: int) -> int:
    card_id = import_ready_card(order_number)
    version = db.fetch_admin_card_detail(card_id)["version"]
    assert db.release_card(
        card_id,
        machine_id,
        machine_sequence,
        version,
    ).ok
    return card_id


def card_version(card_id: int) -> int:
    return int(db.fetch_terminal_card_detail(card_id)["version"])


def test_terminal_snapshot_includes_active_released_cards(connection):
    first_id = release_ready_card("25900", machine_id=1, machine_sequence=1)
    second_id = release_ready_card("25901", machine_id=2, machine_sequence=3)

    snapshot = db.terminal_snapshot()

    cards_by_id = {card["id"]: card for card in snapshot["active_cards"]}
    assert cards_by_id[first_id]["order_number"] == "25900"
    assert cards_by_id[first_id]["status"] == "pending"
    assert cards_by_id[first_id]["machine_id"] == 1
    assert cards_by_id[first_id]["machine_sequence"] == 1
    assert cards_by_id[first_id]["version"] >= 2
    assert cards_by_id[second_id]["machine_id"] == 2
    assert snapshot["active_signature"]
    assert snapshot["selected_card"] is None
    assert snapshot["selected_card_missing"] is False


def test_terminal_snapshot_signature_changes_after_planning_resequence(connection):
    first_id = release_ready_card("25902", machine_id=1, machine_sequence=1)
    second_id = release_ready_card("25903", machine_id=1, machine_sequence=2)
    before = db.terminal_snapshot()

    result = db.update_card_planning(second_id, card_version(second_id), 1, 1)
    after = db.terminal_snapshot()

    assert result.ok
    assert before["signature"] != after["signature"]
    assert [card["id"] for card in after["active_cards"]] == [second_id, first_id]
    assert [card["machine_sequence"] for card in after["active_cards"]] == [1, 2]


def test_terminal_snapshot_selected_card_version_changes_after_terminal_write(connection):
    card_id = release_ready_card("25904", machine_id=3, machine_sequence=1)
    before = db.terminal_snapshot(selected_card_id=card_id)

    assert db.update_tare_weight(card_id, card_version(card_id), "1.25").ok
    after = db.terminal_snapshot(selected_card_id=card_id)

    assert before["selected_card"]["id"] == card_id
    assert after["selected_card"]["id"] == card_id
    assert after["selected_card"]["version"] == before["selected_card"]["version"] + 1
    assert before["signature"] != after["signature"]


def test_terminal_snapshot_marks_selected_card_missing_when_not_terminal_visible(connection):
    card_id = release_ready_card("25905", machine_id=4, machine_sequence=1)
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE cards
            SET status = ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (STATUS_IMPORTED, card_id),
        )

    snapshot = db.terminal_snapshot(selected_card_id=card_id)

    assert snapshot["selected_card"] is None
    assert snapshot["selected_card_missing"] is True
    assert card_id not in {card["id"] for card in snapshot["active_cards"]}
    assert f"missing:{card_id}" in snapshot["signature"]


def test_terminal_snapshot_marks_cancelled_selected_card_missing(connection):
    card_id = release_ready_card("25907", machine_id=4, machine_sequence=1)
    assert db.cancel_card(card_id, card_version(card_id)).ok

    snapshot = db.terminal_snapshot(selected_card_id=card_id)

    assert snapshot["selected_card"] is None
    assert snapshot["selected_card_missing"] is True
    assert card_id not in {card["id"] for card in snapshot["active_cards"]}
    assert f"missing:{card_id}" in snapshot["signature"]


def test_terminal_snapshot_route_is_registered_and_returns_snapshot(connection):
    card_id = release_ready_card("25906", machine_id=1, machine_sequence=1)
    route_paths = {route.path for route in app.routes}

    snapshot = asyncio.run(terminal_snapshot_route(selected_card_id=card_id))

    assert "/terminal/snapshot" in route_paths
    assert snapshot["selected_card"]["id"] == card_id
    assert snapshot["active_cards"][0]["order_number"] == "25906"


def test_terminal_snapshot_marks_unreleased_selected_card_missing(connection):
    card_id = release_ready_card("25908", machine_id=2, machine_sequence=1)
    before = db.terminal_snapshot(selected_card_id=card_id)

    result = db.unrelease_pending_card(card_id, card_version(card_id))
    after = db.terminal_snapshot(selected_card_id=card_id)

    assert result.ok
    assert before["selected_card"]["id"] == card_id
    assert before["selected_card"]["status"] == "pending"
    assert after["selected_card"] is None
    assert after["selected_card_missing"] is True
    assert card_id not in {card["id"] for card in after["active_cards"]}
    assert f"missing:{card_id}" in after["signature"]


def test_terminal_snapshot_shift_signature_changes_on_start_change_end_and_count_update(
    connection,
):
    initial = db.terminal_snapshot()
    initial_configuration = db.fetch_terminal_configuration()

    assert db.update_shift_count(int(initial_configuration["version"]), "3").ok
    after_count_update = db.terminal_snapshot()
    updated_configuration = db.fetch_terminal_configuration()
    assert db.start_shift("2", int(updated_configuration["version"])).ok
    after_start = db.terminal_snapshot()
    active_shift = db.fetch_active_shift()
    assert active_shift is not None
    assert db.update_active_shift_number(
        int(active_shift["id"]),
        int(active_shift["version"]),
        "3",
    ).ok
    after_change = db.terminal_snapshot()
    changed_shift = db.fetch_active_shift()
    assert changed_shift is not None
    assert db.end_shift(int(changed_shift["id"]), int(changed_shift["version"])).ok
    after_end = db.terminal_snapshot()

    snapshots = [initial, after_count_update, after_start, after_change, after_end]
    for before, after in zip(snapshots, snapshots[1:]):
        assert before["shift_signature"] != after["shift_signature"]
        assert before["signature"] != after["signature"]


def test_terminal_snapshot_exposes_only_current_shift_state_needed_for_reload(connection):
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("2", int(configuration["version"])).ok
    active_shift = db.fetch_active_shift()
    assert active_shift is not None
    snapshot = db.terminal_snapshot()

    assert snapshot["shift_signature"] == (
        f"configuration:{configuration['version']}:{configuration['shift_count']}"
        f"||active:{active_shift['id']}:{active_shift['shift_number']}:"
        f"{active_shift['version']}:{active_shift['started_at']}"
    )
    assert "completed_shifts" not in snapshot
    assert "selected_shift_summary" not in snapshot
    assert "shift_history" not in snapshot


def test_terminal_snapshot_tracks_waiting_cards_and_roll_writes(connection, start_test_shift):
    waiting_card_id = release_ready_card("25909", machine_id=1, machine_sequence=1)
    before_waiting = db.terminal_snapshot()
    with db.connect() as setup_connection:
        setup_connection.execute(
            """
            UPDATE cards
            SET status = ?,
                finished_at = '2026-07-26 10:00:00',
                version = version + 1,
                updated_at = '2026-07-26 10:00:00'
            WHERE id = ?
            """,
            (STATUS_AWAITING_REWINDING, waiting_card_id),
        )
        expected_waiting_row = dict(
            setup_connection.execute(
                """
                SELECT id, status, version, updated_at, finished_at, rewinding_roll_count
                FROM cards
                WHERE id = ?
                """,
                (waiting_card_id,),
            ).fetchone()
        )
    entered_waiting = db.terminal_snapshot()

    assert before_waiting["signature"] != entered_waiting["signature"]
    assert entered_waiting["waiting_cards"] == [expected_waiting_row]
    assert entered_waiting["waiting_signature"]

    waiting_version = int(db.fetch_terminal_card_detail(waiting_card_id)["version"])
    assert db.update_rewinding_roll_count(waiting_card_id, waiting_version, 4).ok
    marked = db.terminal_snapshot()
    marked_version = int(db.fetch_terminal_card_detail(waiting_card_id)["version"])
    assert db.update_rewinding_roll_count(waiting_card_id, marked_version, None).ok
    cleared = db.terminal_snapshot()

    assert entered_waiting["signature"] != marked["signature"]
    assert marked["signature"] != cleared["signature"]

    running_card_id = release_ready_card("25910", machine_id=2, machine_sequence=1)
    start_test_shift()
    assert db.start_production_timing(
        running_card_id, card_version(running_card_id), require_active_shift=True
    ).ok
    assert db.update_tare_weight(
        running_card_id, card_version(running_card_id), "1", require_active_shift=True
    ).ok
    before_roll = db.terminal_snapshot()
    assert db.add_roll_gross_weight(
        running_card_id, card_version(running_card_id), "20", require_active_shift=True
    ).ok
    added_roll = db.terminal_snapshot()
    roll_id = db.fetch_terminal_card_detail(running_card_id)["roll_entries"][0]["id"]
    assert db.update_roll_weight(
        running_card_id,
        roll_id,
        card_version(running_card_id),
        "21",
        "1",
        require_active_shift=True,
    ).ok
    edited_roll = db.terminal_snapshot()
    assert db.delete_roll_entry(
        running_card_id,
        roll_id,
        card_version(running_card_id),
        require_active_shift=True,
    ).ok
    deleted_roll = db.terminal_snapshot()

    assert before_roll["signature"] != added_roll["signature"]
    assert added_roll["signature"] != edited_roll["signature"]
    assert edited_roll["signature"] != deleted_roll["signature"]

    with db.connect() as completion_connection:
        completion_connection.execute(
            """
            UPDATE cards
            SET status = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (STATUS_COMPLETED, waiting_card_id),
        )
    completed = db.terminal_snapshot()

    assert cleared["signature"] != completed["signature"]
    assert completed["waiting_cards"] == []


def test_waiting_rewinding_query_and_terminal_context_use_deterministic_display_rows(
    connection,
):
    first_id = release_ready_card("25911", machine_id=1, machine_sequence=1)
    second_id = release_ready_card("25912", machine_id=2, machine_sequence=1)
    latest_id = release_ready_card("25913", machine_id=3, machine_sequence=1)
    with db.connect() as setup_connection:
        setup_connection.executemany(
            """
            UPDATE cards
            SET status = ?,
                finished_at = ?,
                rewinding_roll_count = ?,
                version = version + 1,
                updated_at = ?
            WHERE id = ?
            """,
            (
                (
                    STATUS_AWAITING_REWINDING,
                    "2026-07-26 10:00:00",
                    None,
                    "2026-07-26 10:00:00",
                    first_id,
                ),
                (
                    STATUS_AWAITING_REWINDING,
                    "2026-07-26 10:00:00",
                    4,
                    "2026-07-26 10:00:00",
                    second_id,
                ),
                (
                    STATUS_AWAITING_REWINDING,
                    "2026-07-26 11:00:00",
                    7,
                    "2026-07-26 11:00:00",
                    latest_id,
                ),
            ),
        )

    waiting_rows = db.fetch_waiting_rewinding_cards()
    context = terminal_context(selected_card_id=second_id)

    assert [row["id"] for row in waiting_rows] == [latest_id, second_id, first_id]
    assert waiting_rows[1]["customer"] == "Sync Customer"
    assert waiting_rows[1]["product_type"] == "PE film"
    assert waiting_rows[1]["size_thickness"] == "600/0.050"
    assert waiting_rows[1]["material"] == "LDPE"
    assert context["waiting_rewinding_count"] == 3
    assert [row["id"] for row in context["waiting_rewinding_cards"]] == [
        latest_id,
        second_id,
        first_id,
    ]
    assert [
        row["rewinding_roll_count_label"]
        for row in context["waiting_rewinding_cards"]
    ] == ["7 ролки", "4 ролки", "0 ролки"]
    selected_waiting = next(
        row for row in context["waiting_rewinding_cards"] if row["id"] == second_id
    )
    assert selected_waiting["is_selected"] is True
    assert selected_waiting["status_label"] == "Изчаква пренавиване"
