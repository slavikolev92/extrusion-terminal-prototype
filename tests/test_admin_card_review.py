from __future__ import annotations

import csv
import io

from app import db
from app.constants import STATUS_IMPORTED, STATUS_PAUSED
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import admin_card_detail_context


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
        "order_date": "2026-06-14",
        "delivery_date": "2026-06-20",
        "customer": "Admin Customer",
        "city": "Sofia",
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


def current_imported_fields(card_id: int) -> dict[str, str]:
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    return {field: str(card[field] or "") for field in IMPORT_FIELDS}


def test_admin_card_index_filters_by_order_number(connection):
    import_ready_card("25700", customer="Alpha Customer")
    import_ready_card("25701", customer="Beta Customer")

    cards = db.fetch_admin_cards({"order_number": "700"})

    assert [card["order_number"] for card in cards] == ["25700"]


def test_admin_card_index_filters_by_customer_or_product(connection):
    import_ready_card("25702", customer="North Plast", product_type="PE sheet")
    import_ready_card("25703", customer="South Films", product_type="Stretch film")

    customer_cards = db.fetch_admin_cards({"customer": "North"})
    product_cards = db.fetch_admin_cards({"product": "Stretch"})

    assert [card["order_number"] for card in customer_cards] == ["25702"]
    assert [card["order_number"] for card in product_cards] == ["25703"]


def test_admin_card_index_text_filters_are_case_insensitive(connection):
    import_ready_card("25713", customer="Mixed Case Customer", product_type="Blue FILM")

    customer_cards = db.fetch_admin_cards({"customer": "mixed case"})
    product_cards = db.fetch_admin_cards({"product": "blue film"})

    assert [card["order_number"] for card in customer_cards] == ["25713"]
    assert [card["order_number"] for card in product_cards] == ["25713"]


def test_admin_card_detail_includes_full_review_data(connection):
    card_id = import_ready_card("25704")
    assert db.release_card(card_id, machine_id=2, machine_sequence=1).ok
    assert db.update_terminal_material_fields(
        card_id,
        db.fetch_admin_card_detail(card_id)["version"],
        "Actual LDPE",
        "Grade A",
        "Batch 42",
    ).ok
    assert db.start_production_timing(card_id, db.fetch_admin_card_detail(card_id)["version"]).ok
    assert db.update_tare_weight(card_id, db.fetch_admin_card_detail(card_id)["version"], "1.25").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_admin_card_detail(card_id)["version"], "25.50").ok
    assert db.pause_production_timing(card_id, db.fetch_admin_card_detail(card_id)["version"]).ok

    card = db.fetch_admin_card_detail(card_id)

    assert card["order_number"] == "25704"
    assert card["status"] == "paused"
    assert card["machine_id"] == 2
    assert card["machine_sequence"] == 1
    assert card["customer"] == "Admin Customer"
    assert card["actual_raw_material_used"] == "Actual LDPE"
    assert card["raw_material_brand_grade"] == "Grade A"
    assert card["raw_material_batch_lot"] == "Batch 42"
    assert card["tare_weight"] == 1.25
    assert card["roll_count"] == 1
    assert card["total_gross_weight"] == "25.50"
    assert card["total_net_weight"] == "24.25"
    assert len(card["roll_entries"]) == 1
    assert len(card["timing_segments"]) == 1
    assert card["total_production_seconds"] >= 0


def test_admin_card_detail_context_groups_quantities_and_recipe_rows(connection):
    card_id = import_ready_card(
        "25714",
        quantity_1="500",
        unit_1="kg",
        quantity_2="1200",
        unit_2="m",
        raw_material_a="LDPE A",
        raw_material_b="LDPE B",
        linear_pe="20%",
    )
    assert db.release_card(card_id, machine_id=1, machine_sequence=2).ok
    assert db.update_terminal_material_fields(
        card_id,
        db.fetch_admin_card_detail(card_id)["version"],
        "Actual LDPE",
        "Grade A",
        "Batch 42",
    ).ok

    context = admin_card_detail_context(card_id)

    assert context is not None
    assert [line["display"] for line in context["quantity_lines"]] == ["500 kg", "1200 m"]
    assert [row["label"] for row in context["recipe_rows"]] == [
        "A",
        "B",
        "C",
        "Линеен",
        "Антистатик",
        "Мастербач",
        "Креда",
    ]
    assert context["recipe_rows"][0]["planned"] == "LDPE A"
    assert context["recipe_rows"][0]["actual_material"] == "Actual LDPE"
    assert context["recipe_rows"][0]["brand"] == "Grade A"
    assert context["recipe_rows"][0]["batch"] == "Batch 42"
    assert context["recipe_rows"][1]["planned"] == "LDPE B"
    assert context["recipe_rows"][1]["brand"] == ""


def test_admin_imported_field_edit_succeeds_and_increments_version(connection):
    card_id = import_ready_card("25705")
    card = db.fetch_admin_card_detail(card_id)
    fields = current_imported_fields(card_id)
    fields["customer"] = "Corrected Customer"
    fields["notes"] = "Corrected notes"

    result = db.update_admin_imported_fields(card_id, card["version"], fields)
    updated = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert updated["customer"] == "Corrected Customer"
    assert updated["notes"] == "Corrected notes"
    assert updated["version"] == card["version"] + 1


def test_admin_imported_field_edit_blocks_stale_version(connection):
    card_id = import_ready_card("25706")
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]
    fields = current_imported_fields(card_id)
    fields["customer"] = "First Save"
    assert db.update_admin_imported_fields(card_id, loaded_version, fields).ok

    fields["customer"] = "Stale Save"
    stale_result = db.update_admin_imported_fields(card_id, loaded_version, fields)
    card = db.fetch_admin_card_detail(card_id)

    assert not stale_result.ok
    assert stale_result.messages == (
        "Card changed after this page was loaded. Reload the card and try again.",
    )
    assert card["customer"] == "First Save"


def test_admin_imported_field_edit_preserves_production_data(connection):
    card_id = import_ready_card("25707")
    assert db.release_card(card_id, machine_id=3, machine_sequence=1).ok
    assert db.update_terminal_material_fields(
        card_id,
        db.fetch_admin_card_detail(card_id)["version"],
        "Actual material",
        "Grade B",
        "Batch 99",
    ).ok
    assert db.start_production_timing(card_id, db.fetch_admin_card_detail(card_id)["version"]).ok
    assert db.update_tare_weight(card_id, db.fetch_admin_card_detail(card_id)["version"], "1.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_admin_card_detail(card_id)["version"], "20.00").ok
    assert db.pause_production_timing(card_id, db.fetch_admin_card_detail(card_id)["version"]).ok

    before = db.fetch_admin_card_detail(card_id)
    fields = current_imported_fields(card_id)
    fields["order_number"] = "25770"
    fields["customer"] = "Preserved Customer"
    result = db.update_admin_imported_fields(card_id, before["version"], fields)
    after = db.fetch_admin_card_detail(card_id)
    roll_order_numbers = connection.execute(
        "SELECT order_number FROM roll_entries WHERE card_id = ?",
        (card_id,),
    ).fetchall()

    assert result.ok
    assert after["order_number"] == "25770"
    assert after["customer"] == "Preserved Customer"
    assert after["status"] == STATUS_PAUSED
    assert after["machine_id"] == 3
    assert after["machine_sequence"] == 1
    assert after["tare_weight"] == 1
    assert after["actual_raw_material_used"] == "Actual material"
    assert after["raw_material_brand_grade"] == "Grade B"
    assert after["raw_material_batch_lot"] == "Batch 99"
    assert after["roll_entries"][0]["gross_weight"] == 20
    assert len(after["timing_segments"]) == len(before["timing_segments"])
    assert [row["order_number"] for row in roll_order_numbers] == ["25770"]


def test_admin_imported_field_edit_blocks_duplicate_order_number(connection):
    import_ready_card("25708")
    card_id = import_ready_card("25709")
    card = db.fetch_admin_card_detail(card_id)
    fields = current_imported_fields(card_id)
    fields["order_number"] = "25708"

    result = db.update_admin_imported_fields(card_id, card["version"], fields)
    unchanged = db.fetch_admin_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Order number already exists on another card.",)
    assert unchanged["order_number"] == "25709"


def test_admin_imported_field_edit_blocks_no_extrusion_result(connection):
    card_id = import_ready_card("25710")
    card = db.fetch_admin_card_detail(card_id)
    fields = current_imported_fields(card_id)
    fields["extrusion_flag"] = ""
    fields["raw_material_a"] = ""
    fields["packaging_method"] = ""
    fields["extrusion_folding"] = ""
    fields["extrusion_next_operation"] = ""
    fields["extrusion_treatment"] = ""

    result = db.update_admin_imported_fields(card_id, card["version"], fields)
    unchanged = db.fetch_admin_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Imported fields must keep a usable extrusion step before saving.",)
    assert unchanged["extrusion_flag"] == "da"
    assert unchanged["raw_material_a"] == "LDPE A"


def test_admin_delete_removes_unreleased_card(connection):
    cursor = connection.execute(
        """
        INSERT INTO cards (order_number, status, customer, product_type)
        VALUES (?, ?, ?, ?)
        """,
        (
            "25711",
            STATUS_IMPORTED,
            "Invalid Customer",
            "No extrusion product",
        ),
    )
    connection.commit()
    card_id = int(cursor.lastrowid)
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]

    result = db.delete_admin_imported_card(card_id, loaded_version)
    deleted = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert deleted is None


def test_admin_delete_blocks_released_card(connection):
    card_id = import_ready_card("25712")
    assert db.release_card(card_id, machine_id=4, machine_sequence=9).ok
    card = db.fetch_admin_card_detail(card_id)

    result = db.delete_admin_imported_card(card_id, card["version"])
    still_exists = db.fetch_admin_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Only unreleased imported cards can be deleted.",)
    assert still_exists is not None
