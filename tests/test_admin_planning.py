from __future__ import annotations

import csv
import io

from app import db
from app.constants import STATUS_IMPORTED, STATUS_PAUSED, STATUS_PENDING, STATUS_RUNNING
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
        "raw_material_a": "LDPE A | 100%",
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


def test_unrelease_pending_card_returns_it_to_unreleased_pool_and_preserves_data(connection):
    card_id = release_ready_card("25820", machine_id=2, machine_sequence=1)
    before = db.fetch_admin_card_detail(card_id)
    assert before["status"] == STATUS_PENDING
    assert before["machine_id"] == 2
    assert before["machine_sequence"] == 1
    assert before["max_roll_weight"] == "60.0"

    result = db.unrelease_pending_card(card_id, card_version(card_id))
    after = db.fetch_admin_card_detail(card_id)
    draft_cards = db.fetch_cards_by_status((STATUS_IMPORTED,))
    queues = db.fetch_machine_queues()

    assert result.ok
    assert result.messages == ("Поръчка 25820 е върната в неизпратени технологични карти.",)
    assert after["status"] == STATUS_IMPORTED
    assert after["machine_id"] is None
    assert after["machine_sequence"] is None
    assert after["max_roll_weight"] == "60.0"
    assert after["customer"] == before["customer"]
    assert after["raw_material_a"] == before["raw_material_a"]
    assert after["version"] == before["version"] + 1
    assert card_id in {card["id"] for card in draft_cards}
    assert all(
        card["id"] != card_id
        for queue in queues
        for card in queue["cards"]
    )


def test_unrelease_pending_card_normalizes_old_machine_queue(connection):
    first_id = release_ready_card("25821", machine_id=1, machine_sequence=1)
    removed_id = release_ready_card("25822", machine_id=1, machine_sequence=2)
    third_id = release_ready_card("25823", machine_id=1, machine_sequence=3)

    result = db.unrelease_pending_card(removed_id, card_version(removed_id))

    first = db.fetch_admin_card_detail(first_id)
    removed = db.fetch_admin_card_detail(removed_id)
    third = db.fetch_admin_card_detail(third_id)
    machine_1_cards = [
        (card["order_number"], card["machine_sequence"])
        for queue in db.fetch_machine_queues()
        if queue["machine"]["id"] == 1
        for card in queue["cards"]
    ]

    assert result.ok
    assert first["status"] == STATUS_PENDING
    assert first["machine_sequence"] == 1
    assert removed["status"] == STATUS_IMPORTED
    assert removed["machine_id"] is None
    assert removed["machine_sequence"] is None
    assert third["status"] == STATUS_PENDING
    assert third["machine_sequence"] == 2
    assert machine_1_cards == [("25821", 1), ("25823", 2)]


def test_unrelease_pending_card_blocks_stale_loaded_version(connection):
    card_id = release_ready_card("25824", machine_id=3, machine_sequence=1)
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.25").ok

    result = db.unrelease_pending_card(card_id, loaded_version)
    card = db.fetch_admin_card_detail(card_id)

    assert not result.ok
    assert result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert card["status"] == STATUS_PENDING
    assert card["machine_id"] == 3
    assert card["machine_sequence"] == 1


def test_unrelease_blocks_running_and_paused_cards(connection):
    running_id = release_ready_card("25825", machine_id=4, machine_sequence=1)
    paused_id = release_ready_card("25826", machine_id=4, machine_sequence=2)
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    running_result = db.unrelease_pending_card(running_id, card_version(running_id))
    paused_result = db.unrelease_pending_card(paused_id, card_version(paused_id))
    running = db.fetch_admin_card_detail(running_id)
    paused = db.fetch_admin_card_detail(paused_id)

    assert not running_result.ok
    assert running_result.messages == (
        "Само изчакващи технологични карти могат да се връщат за планиране.",
    )
    assert not paused_result.ok
    assert paused_result.messages == (
        "Само изчакващи технологични карти могат да се връщат за планиране.",
    )
    assert running["status"] == STATUS_RUNNING
    assert running["machine_id"] == 4
    assert running["machine_sequence"] == 1
    assert paused["status"] == STATUS_PAUSED
    assert paused["machine_id"] == 4
    assert paused["machine_sequence"] == 2


def test_unrelease_blocks_imported_completed_and_cancelled_cards(connection):
    imported_id = import_ready_card("25827")
    completed_id = release_ready_card("25828", machine_id=2, machine_sequence=1)
    cancelled_id = release_ready_card("25829", machine_id=2, machine_sequence=2)
    assert db.start_production_timing(completed_id, card_version(completed_id)).ok
    assert db.update_tare_weight(completed_id, card_version(completed_id), "1.00").ok
    assert db.add_roll_gross_weight(completed_id, card_version(completed_id), "20.00").ok
    assert db.finish_card(completed_id, card_version(completed_id)).ok
    assert db.cancel_card(cancelled_id, card_version(cancelled_id)).ok

    imported_result = db.unrelease_pending_card(imported_id, card_version(imported_id))
    completed_result = db.unrelease_pending_card(completed_id, card_version(completed_id))
    cancelled_result = db.unrelease_pending_card(cancelled_id, card_version(cancelled_id))

    assert not imported_result.ok
    assert imported_result.messages == (
        "Само изчакващи технологични карти могат да се връщат за планиране.",
    )
    assert not completed_result.ok
    assert completed_result.messages == (
        "Само изчакващи технологични карти могат да се връщат за планиране.",
    )
    assert not cancelled_result.ok
    assert cancelled_result.messages == (
        "Само изчакващи технологични карти могат да се връщат за планиране.",
    )
    assert db.fetch_admin_card_detail(imported_id)["status"] == STATUS_IMPORTED
    assert db.fetch_admin_card_detail(completed_id)["status"] == "completed"
    assert db.fetch_admin_card_detail(cancelled_id)["status"] == "cancelled"
