from __future__ import annotations

import csv
import io

from app import db
from app.constants import STATUS_PAUSED, STATUS_PENDING, STATUS_RUNNING
from app.importer import IMPORT_FIELDS, import_cards_from_csv


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
        "customer": "Roll Customer",
        "product_type": "PE film",
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "da",
        "raw_material_a": "LDPE A",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def import_and_release_card(
    order_number: str,
    machine_id: int = 1,
    machine_sequence: int = 1,
) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number)),
        overwrite_existing=False,
    )
    assert result.rows_imported == 1
    with db.connect() as connection:
        card_id = int(
            connection.execute(
                "SELECT id FROM cards WHERE order_number = ?",
                (order_number,),
            ).fetchone()["id"]
        )
    assert db.release_card(card_id, machine_id, machine_sequence).ok
    return card_id


def start_card(card_id: int) -> None:
    assert db.start_production_timing(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
    ).ok


def test_tare_update_persists_and_checks_loaded_version(connection):
    card_id = import_and_release_card("25500")
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.update_tare_weight(card_id, loaded_version, "1.25")
    stale_result = db.update_tare_weight(card_id, loaded_version, "1.50")
    card = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert card["tare_weight"] == 1.25
    assert card["version"] == loaded_version + 1
    assert not stale_result.ok
    assert stale_result.messages == (
        "Card changed after this page was loaded. Reload the card and try again.",
    )


def test_add_roll_while_running_assigns_roll_numbers(connection):
    card_id = import_and_release_card("25501")
    start_card(card_id)

    first_result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.50",
    )
    second_result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "30",
    )
    rolls = connection.execute(
        """
        SELECT roll_number, gross_weight
        FROM roll_entries
        WHERE card_id = ?
        ORDER BY roll_number
        """,
        (card_id,),
    ).fetchall()

    assert first_result.ok
    assert first_result.messages == ("Roll 1 saved.",)
    assert second_result.ok
    assert second_result.messages == ("Roll 2 saved.",)
    assert [(roll["roll_number"], roll["gross_weight"]) for roll in rolls] == [
        (1, 25.50),
        (2, 30),
    ]


def test_add_roll_is_blocked_when_card_is_not_running(connection):
    pending_card_id = import_and_release_card("25502", machine_id=2, machine_sequence=1)
    paused_card_id = import_and_release_card("25503", machine_id=3, machine_sequence=1)
    start_card(paused_card_id)
    assert db.pause_production_timing(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
    ).ok

    pending_result = db.add_roll_gross_weight(
        pending_card_id,
        db.fetch_terminal_card_detail(pending_card_id)["version"],
        "25",
    )
    paused_result = db.add_roll_gross_weight(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
        "25",
    )

    assert db.fetch_terminal_card_detail(pending_card_id)["status"] == STATUS_PENDING
    assert db.fetch_terminal_card_detail(paused_card_id)["status"] == STATUS_PAUSED
    assert not pending_result.ok
    assert pending_result.messages == (
        "Roll weights can only be changed while the card is running or completed.",
    )
    assert not paused_result.ok
    assert paused_result.messages == (
        "Roll weights can only be changed while the card is running or completed.",
    )


def test_weight_inputs_reject_more_than_two_decimal_places(connection):
    card_id = import_and_release_card("25507")
    start_card(card_id)

    tare_result = db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.234",
    )
    gross_result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.555",
    )
    roll_count = connection.execute(
        "SELECT COUNT(*) FROM roll_entries WHERE card_id = ?",
        (card_id,),
    ).fetchone()[0]

    assert not tare_result.ok
    assert tare_result.messages == ("Tare weight supports at most two decimal places.",)
    assert not gross_result.ok
    assert gross_result.messages == ("Gross weight supports at most two decimal places.",)
    assert roll_count == 0


def test_gross_and_net_totals_calculate_with_tare(connection):
    card_id = import_and_release_card("25504")
    start_card(card_id)
    assert db.fetch_terminal_card_detail(card_id)["status"] == STATUS_RUNNING
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.25",
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.50",
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "30.00",
    ).ok

    card = db.fetch_terminal_card_detail(card_id)
    rolls = card["roll_entries"]

    assert card["roll_count"] == 2
    assert card["total_gross_weight"] == "55.50"
    assert card["total_net_weight"] == "53.00"
    assert rolls[0]["net_weight"] == 24.25
    assert rolls[1]["net_weight"] == 28.75


def test_stale_roll_add_and_update_are_blocked(connection):
    card_id = import_and_release_card("25505")
    start_card(card_id)
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]
    assert db.add_roll_gross_weight(card_id, loaded_version, "20").ok
    roll_id = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]["id"]

    stale_add = db.add_roll_gross_weight(card_id, loaded_version, "21")
    stale_update = db.update_roll_gross_weight(card_id, roll_id, loaded_version, "22")
    card = db.fetch_terminal_card_detail(card_id)

    assert not stale_add.ok
    assert stale_add.messages == (
        "Card changed after this page was loaded. Reload the card and try again.",
    )
    assert not stale_update.ok
    assert stale_update.messages == (
        "Card changed after this page was loaded. Reload the card and try again.",
    )
    assert card["roll_count"] == 1
    assert card["roll_entries"][0]["gross_weight"] == 20


def test_clearing_existing_gross_weight_removes_it_from_totals(connection):
    card_id = import_and_release_card("25506")
    start_card(card_id)
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.00",
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
    ).ok
    card = db.fetch_terminal_card_detail(card_id)
    roll_id = card["roll_entries"][0]["id"]

    result = db.update_roll_gross_weight(
        card_id,
        roll_id,
        card["version"],
        "",
    )
    cleared_card = db.fetch_terminal_card_detail(card_id)
    cleared_roll = cleared_card["roll_entries"][0]

    assert result.ok
    assert cleared_roll["gross_weight"] is None
    assert cleared_roll["net_weight"] is None
    assert cleared_card["roll_count"] == 0
    assert cleared_card["total_gross_weight"] == "0.00"
    assert cleared_card["total_net_weight"] == "0.00"
