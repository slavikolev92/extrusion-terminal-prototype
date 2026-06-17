from __future__ import annotations

import csv
import io

from app import db
from app.constants import STATUS_PENDING, STATUS_RUNNING
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
        "customer": "Planning Customer",
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
    return int(db.fetch_admin_card_detail(card_id)["version"])


def test_release_accepts_loaded_version_and_clamps_empty_machine_to_first_position(connection):
    card_id = import_ready_card("25800")
    loaded_version = card_version(card_id)

    result = db.release_card(
        card_id,
        1,
        3,
        loaded_version,
        max_roll_weight="60.0",
    )
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["status"] == STATUS_PENDING
    assert card["machine_id"] == 1
    assert card["machine_sequence"] == 1
    assert card["version"] == loaded_version + 1


def test_release_blocks_stale_loaded_version(connection):
    card_id = import_ready_card("25801")
    loaded_version = card_version(card_id)
    fields = {field: str(db.fetch_admin_card_detail(card_id)[field] or "") for field in IMPORT_FIELDS}
    fields["customer"] = "Updated Before Release"
    assert db.update_admin_imported_fields(card_id, loaded_version, fields).ok

    result = db.release_card(
        card_id,
        1,
        1,
        loaded_version,
        max_roll_weight="60.0",
    )
    card = db.fetch_admin_card_detail(card_id)

    assert not result.ok
    assert result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert card["status"] == "imported"
    assert card["machine_id"] is None
    assert card["machine_sequence"] is None


def test_planning_reassignment_moves_pending_card_between_machines(connection):
    card_id = release_ready_card("25802", machine_id=1, machine_sequence=2)

    result = db.update_card_planning(card_id, card_version(card_id), 3, 4)
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["status"] == STATUS_PENDING
    assert card["machine_id"] == 3
    assert card["machine_sequence"] == 1


def test_planning_move_closes_old_gap_and_inserts_into_target_queue(connection):
    moving_id = release_ready_card("25813", machine_id=1, machine_sequence=1)
    staying_id = release_ready_card("25814", machine_id=1, machine_sequence=2)
    target_id = release_ready_card("25815", machine_id=4, machine_sequence=1)

    result = db.update_card_planning(moving_id, card_version(moving_id), 4, 2)
    queues = db.fetch_machine_queues()
    machine_1_cards = [
        (card["order_number"], card["machine_sequence"])
        for queue in queues
        if queue["machine"]["id"] == 1
        for card in queue["cards"]
    ]
    machine_4_cards = [
        (card["order_number"], card["machine_sequence"])
        for queue in queues
        if queue["machine"]["id"] == 4
        for card in queue["cards"]
    ]

    assert result.ok
    assert db.fetch_admin_card_detail(staying_id)["machine_sequence"] == 1
    assert db.fetch_admin_card_detail(target_id)["machine_sequence"] == 1
    assert machine_1_cards == [("25814", 1)]
    assert machine_4_cards == [("25815", 1), ("25813", 2)]


def test_planning_resequencing_changes_machine_queue_order(connection):
    first_id = release_ready_card("25803", machine_id=2, machine_sequence=1)
    second_id = release_ready_card("25804", machine_id=2, machine_sequence=3)

    result = db.update_card_planning(second_id, card_version(second_id), 2, 1)
    queues = db.fetch_machine_queues()
    machine_2_orders = [
        card["order_number"]
        for queue in queues
        if queue["machine"]["id"] == 2
        for card in queue["cards"]
    ]

    assert result.ok
    assert db.fetch_admin_card_detail(first_id)["machine_sequence"] == 2
    assert db.fetch_admin_card_detail(second_id)["machine_sequence"] == 1
    assert machine_2_orders == ["25804", "25803"]


def test_planning_inserts_at_existing_position_and_shifts_queue(connection):
    release_ready_card("25805", machine_id=4, machine_sequence=7)
    second_id = release_ready_card("25806", machine_id=4, machine_sequence=8)

    result = db.update_card_planning(second_id, card_version(second_id), 4, 1)
    queues = db.fetch_machine_queues()
    machine_4_cards = [
        (card["order_number"], card["machine_sequence"])
        for queue in queues
        if queue["machine"]["id"] == 4
        for card in queue["cards"]
    ]

    assert result.ok
    assert machine_4_cards == [("25806", 1), ("25805", 2)]


def test_planning_blocks_running_card_into_occupied_machine(connection):
    occupied_id = release_ready_card("25807", machine_id=1, machine_sequence=1)
    moving_id = release_ready_card("25808", machine_id=2, machine_sequence=1)
    assert db.start_production_timing(occupied_id, card_version(occupied_id)).ok
    assert db.start_production_timing(moving_id, card_version(moving_id)).ok

    result = db.update_card_planning(moving_id, card_version(moving_id), 1, 2)
    moving_card = db.fetch_admin_card_detail(moving_id)

    assert not result.ok
    assert result.messages == ("Машина 1 е заета от поръчка 25807.",)
    assert moving_card["status"] == STATUS_RUNNING
    assert moving_card["machine_id"] == 2
    assert moving_card["machine_sequence"] == 1


def test_planning_allows_pending_card_into_occupied_machine_when_sequence_is_unique(connection):
    occupied_id = release_ready_card("25809", machine_id=1, machine_sequence=1)
    pending_id = release_ready_card("25810", machine_id=2, machine_sequence=1)
    assert db.start_production_timing(occupied_id, card_version(occupied_id)).ok

    result = db.update_card_planning(pending_id, card_version(pending_id), 1, 2)
    pending_card = db.fetch_admin_card_detail(pending_id)

    assert result.ok
    assert pending_card["status"] == STATUS_PENDING
    assert pending_card["machine_id"] == 1
    assert pending_card["machine_sequence"] == 2


def test_planning_blocks_stale_loaded_version(connection):
    card_id = release_ready_card("25811", machine_id=3, machine_sequence=1)
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.25").ok

    result = db.update_card_planning(card_id, loaded_version, 3, 2)
    card = db.fetch_admin_card_detail(card_id)

    assert not result.ok
    assert result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert card["machine_sequence"] == 1


def test_planning_preserves_production_data(connection):
    card_id = release_ready_card("25812", machine_id=3, machine_sequence=5)
    assert db.update_terminal_material_fields(
        card_id,
        card_version(card_id),
        "Actual LDPE",
        "Grade A",
        "Batch 42",
    ).ok
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "20.00").ok
    before = db.fetch_admin_card_detail(card_id)

    result = db.update_card_planning(card_id, before["version"], 4, 6)
    after = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert after["status"] == STATUS_RUNNING
    assert after["machine_id"] == 4
    assert after["machine_sequence"] == 1
    assert after["tare_weight"] == 1
    assert after["actual_raw_material_used"] == "Actual LDPE"
    assert after["raw_material_brand_grade"] == "Grade A"
    assert after["raw_material_batch_lot"] == "Batch 42"
    assert after["roll_entries"][0]["gross_weight"] == 20
    assert len(after["timing_segments"]) == len(before["timing_segments"])
    assert after["version"] == before["version"] + 1
