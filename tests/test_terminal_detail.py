from __future__ import annotations

import csv
import io

from app import db
from app.constants import STATUS_PAUSED
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
        "customer": "Terminal Customer",
        "product_type": "PE film",
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "da",
        "extrusion_folding": "single",
        "extrusion_next_operation": "rewind",
        "extrusion_treatment": "corona",
        "raw_material_a": "LDPE A",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def import_ready_card(order_number: str, **overrides: str) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number, **overrides)),
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


def test_terminal_card_detail_fetches_released_card_fields(connection):
    card_id = import_ready_card("25300")
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        max_roll_weight="62.5",
    ).ok

    card = db.fetch_terminal_card_detail(card_id)

    assert card is not None
    assert card["id"] == card_id
    assert card["order_number"] == "25300"
    assert card["customer"] == "Terminal Customer"
    assert card["max_roll_weight"] == "62.5"
    assert card["extrusion_folding"] == "single"
    assert card["raw_material_a"] == "LDPE A"
    assert card["actual_raw_material_used"] is None
    assert card["version"] >= 2


def test_machine_queue_focus_prefers_occupied_card_over_next_pending(connection):
    pending_card_id = import_ready_card("25301")
    paused_card_id = import_ready_card("25302")
    assert db.release_card(
        pending_card_id,
        machine_id=2,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    assert db.release_card(
        paused_card_id,
        machine_id=2,
        machine_sequence=5,
        max_roll_weight="60.0",
    ).ok
    connection.execute(
        "UPDATE cards SET status = ? WHERE id = ?",
        (STATUS_PAUSED, paused_card_id),
    )
    connection.commit()

    queues = db.fetch_machine_queues()
    machine_2 = next(queue for queue in queues if queue["machine"]["id"] == 2)

    assert machine_2["focus_card"]["order_number"] == "25302"
    assert [card["order_number"] for card in machine_2["cards"]] == ["25301", "25302"]


def test_terminal_material_field_update_checks_loaded_version(connection):
    card_id = import_ready_card("25303")
    assert db.release_card(
        card_id,
        machine_id=3,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.update_terminal_material_fields(
        card_id=card_id,
        loaded_version=loaded_version,
        actual_raw_material_used="Actual LDPE",
        raw_material_brand_grade="Grade A",
        raw_material_batch_lot="Batch 42",
    )

    card = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert card["actual_raw_material_used"] == "Actual LDPE"
    assert card["raw_material_brand_grade"] == "Grade A"
    assert card["raw_material_batch_lot"] == "Batch 42"
    assert card["version"] == loaded_version + 1


def test_terminal_material_field_update_blocks_stale_version(connection):
    card_id = import_ready_card("25304")
    assert db.release_card(
        card_id,
        machine_id=4,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]
    assert db.update_terminal_material_fields(
        card_id=card_id,
        loaded_version=loaded_version,
        actual_raw_material_used="First LDPE",
        raw_material_brand_grade="Grade A",
        raw_material_batch_lot="Batch 42",
    ).ok

    stale_result = db.update_terminal_material_fields(
        card_id=card_id,
        loaded_version=loaded_version,
        actual_raw_material_used="Stale overwrite",
        raw_material_brand_grade="Grade B",
        raw_material_batch_lot="Batch 99",
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert not stale_result.ok
    assert stale_result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert card["actual_raw_material_used"] == "First LDPE"
    assert card["raw_material_brand_grade"] == "Grade A"
    assert card["raw_material_batch_lot"] == "Batch 42"


def test_terminal_card_detail_hides_cancelled_cards(connection):
    card_id = import_ready_card("25305")
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    assert db.cancel_card(card_id, loaded_version).ok

    assert db.fetch_terminal_card_detail(card_id) is None
    assert db.fetch_admin_card_detail(card_id)["status"] == "cancelled"
