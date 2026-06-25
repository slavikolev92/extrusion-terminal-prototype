from __future__ import annotations

import csv
import io

from app import db
from app.constants import STATUS_PAUSED, STATUS_RUNNING
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
    assert card["raw_material_a"] == "LDPE A | 100%"
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


def test_machine_queue_focus_prefers_running_over_earlier_paused(connection):
    paused_card_id = import_ready_card("25305")
    pending_card_id = import_ready_card("25306")
    running_card_id = import_ready_card("25307")
    assert db.release_card(
        paused_card_id,
        machine_id=2,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    assert db.release_card(
        pending_card_id,
        machine_id=2,
        machine_sequence=2,
        max_roll_weight="60.0",
    ).ok
    assert db.release_card(
        running_card_id,
        machine_id=2,
        machine_sequence=3,
        max_roll_weight="60.0",
    ).ok
    connection.execute(
        "UPDATE cards SET status = ? WHERE id = ?",
        (STATUS_PAUSED, paused_card_id),
    )
    connection.execute(
        "UPDATE cards SET status = ? WHERE id = ?",
        (STATUS_RUNNING, running_card_id),
    )
    connection.commit()

    queues = db.fetch_machine_queues()
    machine_2 = next(queue for queue in queues if queue["machine"]["id"] == 2)

    assert machine_2["focus_card"]["order_number"] == "25307"
    assert [card["order_number"] for card in machine_2["cards"]] == [
        "25305",
        "25306",
        "25307",
    ]


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


def recipe_actual_entries() -> dict[str, dict[str, str]]:
    return {
        "raw_material_a": {
            "actual_material_used": "Actual A",
            "batch_lot": "Batch A",
        },
        "raw_material_b": {
            "actual_material_used": "Actual B",
            "batch_lot": "Batch B",
        },
        "raw_material_c": {
            "actual_material_used": "Actual C",
            "batch_lot": "Batch C",
        },
        "linear_pe": {
            "actual_material_used": "Actual Linear",
            "batch_lot": "Batch Linear",
        },
        "antistatic": {
            "actual_material_used": "Actual Antistatic",
            "batch_lot": "Batch Antistatic",
        },
        "masterbatch": {
            "actual_material_used": "Actual Masterbatch",
            "batch_lot": "Batch Masterbatch",
        },
        "chalk": {
            "actual_material_used": "Actual Chalk",
            "batch_lot": "Batch Chalk",
        },
    }


def test_terminal_recipe_actual_entries_persist_all_rows_and_survive_finish(connection):
    card_id = import_ready_card(
        "25340",
        raw_material_a="LDPE A | 50%",
        raw_material_b="LDPE B | 30%",
        raw_material_c="MDPE C | 5%",
        linear_pe="LLDPE Linear PE | 8%",
        antistatic="Antistatic Agent | 1%",
        masterbatch="Masterbatch White | 4%",
        chalk="Filler Chalk | 2%",
    )
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.update_terminal_recipe_actual_entries(
        card_id,
        loaded_version,
        recipe_actual_entries(),
    )

    card = db.fetch_terminal_card_detail(card_id)
    assert result.ok
    assert card["version"] == loaded_version + 1
    assert set(card["recipe_actual_entries"]) == set(recipe_actual_entries())
    assert card["recipe_actual_entries"]["raw_material_a"]["actual_material_used"] == "Actual A"
    assert card["recipe_actual_entries"]["raw_material_b"]["batch_lot"] == "Batch B"
    assert card["recipe_actual_entries"]["chalk"]["actual_material_used"] == "Actual Chalk"

    assert db.start_production_timing(card_id, card["version"]).ok
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.20",
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "510.00",
    ).ok
    assert db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok

    completed_card = db.fetch_terminal_card_detail(card_id)
    assert completed_card["status"] == "completed"
    assert completed_card["recipe_actual_entries"]["linear_pe"]["actual_material_used"] == "Actual Linear"
    assert completed_card["recipe_actual_entries"]["masterbatch"]["batch_lot"] == "Batch Masterbatch"


def test_terminal_recipe_actual_entries_block_stale_version(connection):
    card_id = import_ready_card("25341")
    assert db.release_card(
        card_id,
        machine_id=2,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        loaded_version,
        recipe_actual_entries(),
    ).ok

    stale_result = db.update_terminal_recipe_actual_entries(
        card_id,
        loaded_version,
        {
            "raw_material_a": {
                "actual_material_used": "Stale",
                "batch_lot": "Stale Batch",
            },
        },
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert not stale_result.ok
    assert stale_result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert card["recipe_actual_entries"]["raw_material_a"]["actual_material_used"] == "Actual A"


def test_terminal_recipe_actual_entries_survive_reimport(connection):
    card_id = import_ready_card("25342", raw_material_a="LDPE Original A | 100%")
    assert db.release_card(
        card_id,
        machine_id=3,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        recipe_actual_entries(),
    ).ok

    result = import_cards_from_csv(
        "overwrite.csv",
        csv_bytes(extrusion_row("25342", raw_material_a="Updated A")),
        overwrite_existing=True,
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert result.updated == 1
    assert card["raw_material_a"] == "Updated A"
    assert card["recipe_actual_entries"]["raw_material_a"]["actual_material_used"] == "Actual A"
    assert card["recipe_actual_entries"]["raw_material_a"]["batch_lot"] == "Batch A"


def test_terminal_recipe_actual_entries_reject_unknown_component(connection):
    card_id = import_ready_card("25343")
    assert db.release_card(
        card_id,
        machine_id=4,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok

    result = db.update_terminal_recipe_actual_entries(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        {
            "not_a_recipe_row": {
                "actual_material_used": "Wrong",
                "batch_lot": "Wrong",
            },
        },
    )

    assert not result.ok
    assert result.messages == ("Формата съдържа непознат ред от рецептата.",)


def test_terminal_recipe_actual_update_preserves_omitted_component_entries(connection):
    card_id = import_ready_card(
        "25344",
        raw_material_a="LDPE A | 80%",
        linear_pe="LLDPE Linear PE | 20%",
    )
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        loaded_version,
        {
            "raw_material_a": {
                "actual_material_used": "Actual A",
                "batch_lot": "Batch A",
            },
            "linear_pe": {
                "actual_material_used": "Actual Linear",
                "batch_lot": "Batch Linear",
            },
        },
    ).ok

    result = db.update_terminal_recipe_actual_entries(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        {
            "raw_material_a": {
                "actual_material_used": "Updated Actual A",
                "batch_lot": "Updated Batch A",
            },
        },
    )

    card = db.fetch_terminal_card_detail(card_id)
    assert result.ok
    assert card["recipe_actual_entries"]["raw_material_a"]["actual_material_used"] == (
        "Updated Actual A"
    )
    assert card["recipe_actual_entries"]["raw_material_a"]["batch_lot"] == (
        "Updated Batch A"
    )
    assert card["recipe_actual_entries"]["linear_pe"]["actual_material_used"] == (
        "Actual Linear"
    )
    assert card["recipe_actual_entries"]["linear_pe"]["batch_lot"] == "Batch Linear"


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
