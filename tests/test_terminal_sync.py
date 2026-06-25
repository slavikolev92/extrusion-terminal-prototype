from __future__ import annotations

import asyncio
import csv
import io

from app import db
from app.constants import STATUS_IMPORTED
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import app, terminal_snapshot_route


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
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "da",
        "raw_material_a": "LDPE A | 100%",
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
        max_roll_weight="60.0",
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
