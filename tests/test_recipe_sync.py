from __future__ import annotations

import csv
import io
from decimal import Decimal

from app import db
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import admin_card_detail_context, terminal_context
from app.printing import build_recipe_rows as build_print_recipe_rows
from app.recipe_parser import ParsedRecipeComponent


def csv_bytes(*rows: dict[str, str]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")


def structured_row(order_number: str, **overrides: str) -> dict[str, str]:
    row = {
        "order_number": order_number,
        "order_date": "2026-06-25",
        "delivery_date": "2026-06-30",
        "customer": "Structured Recipe Sync Customer",
        "city": "Sofia",
        "product_type": "PE film",
        "quantity_1": "1000",
        "unit_1": "kg",
        "material": "LDPE / LLDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "da",
        "extrusion_folding": "single",
        "extrusion_next_operation": "rewind",
        "extrusion_treatment": "corona",
        "raw_material_a": "LDPE Rompetrol B20/03 | 80%",
        "linear_pe": "LLDPE SABIC 119ZJ | 20%",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def import_card(order_number: str, **overrides: str) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(structured_row(order_number, **overrides)),
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


def current_import_fields(card_id: int) -> dict[str, str]:
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    return {field: str(card[field] or "") for field in IMPORT_FIELDS}


def component_summary(connection, card_id: int) -> list[tuple[str, str, str, str]]:
    return [
        (
            row["component_key"],
            row["source_text"],
            row["material_category"],
            row["planned_material"],
        )
        for row in db.fetch_recipe_components(connection, card_id)
    ]


def actual_entry(connection, card_id: int, component_key: str = "raw_material_a"):
    return connection.execute(
        """
        SELECT planned_material, actual_material_used, batch_lot
        FROM recipe_actual_entries
        WHERE card_id = ?
          AND component_key = ?
        """,
        (card_id, component_key),
    ).fetchone()


def poison_raw_material_a_component(connection, card_id: int) -> None:
    db.replace_recipe_components_for_card(
        connection,
        card_id,
        (
            ParsedRecipeComponent(
                component_key="raw_material_a",
                source_text="LDPE Derived Should Not Display | 100%",
                material_category="LDPE",
                planned_material="Derived Should Not Display",
                recipe_percent=Decimal("100"),
            ),
        ),
    )
    connection.commit()


def test_csv_import_creates_normalized_recipe_components(connection):
    result = import_cards_from_csv(
        "structured-import.csv",
        csv_bytes(
            structured_row(
                "RS-SYNC-001",
                raw_material_a="LDPE Rompetrol Midilena B20/03 | 77%",
                linear_pe="LLDPE SABIC 119ZJ | 18%",
                antistatic="Antistatic Novachem AT 04673 LD | 2%",
                masterbatch="Masterbatch Polibach White 8000 ET | 3%",
            )
        ),
        overwrite_existing=False,
    )
    card = connection.execute(
        """
        SELECT id, raw_material_a, linear_pe, antistatic, masterbatch
        FROM cards
        WHERE order_number = 'RS-SYNC-001'
        """
    ).fetchone()

    assert result.created == 1
    assert card["raw_material_a"] == "LDPE Rompetrol Midilena B20/03 | 77%"
    assert component_summary(connection, int(card["id"])) == [
        (
            "raw_material_a",
            "LDPE Rompetrol Midilena B20/03 | 77%",
            "LDPE",
            "Rompetrol Midilena B20/03",
        ),
        ("linear_pe", "LLDPE SABIC 119ZJ | 18%", "LLDPE", "SABIC 119ZJ"),
        (
            "antistatic",
            "Antistatic Novachem AT 04673 LD | 2%",
            "Antistatic",
            "Novachem AT 04673 LD",
        ),
        (
            "masterbatch",
            "Masterbatch Polibach White 8000 ET | 3%",
            "Masterbatch",
            "Polibach White 8000 ET",
        ),
    ]


def test_import_sync_stores_category_only_rows_with_empty_planned_material(connection):
    card_id = import_card(
        "RS-SYNC-012",
        raw_material_a="reLDPE | 80%",
        linear_pe="LLDPE SABIC 119ZJ | 20%",
    )

    assert component_summary(connection, card_id) == [
        ("raw_material_a", "reLDPE | 80%", "reLDPE", ""),
        ("linear_pe", "LLDPE SABIC 119ZJ | 20%", "LLDPE", "SABIC 119ZJ"),
    ]


def test_overwrite_reimport_refreshes_components_and_preserves_actual_entries(connection):
    card_id = import_card("RS-SYNC-002")
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        loaded_version,
        {
            "raw_material_a": {
                "actual_material_used": "Actual LDPE",
                "batch_lot": "Batch A",
            },
            "linear_pe": {
                "actual_material_used": "Actual LLDPE",
                "batch_lot": "Batch L",
            },
        },
    ).ok

    result = import_cards_from_csv(
        "structured-overwrite.csv",
        csv_bytes(
            structured_row(
                "RS-SYNC-002",
                raw_material_a="LDPE New Source | 70%",
                raw_material_b="LLDPE Added Source | 30%",
                linear_pe="",
            )
        ),
        overwrite_existing=True,
    )

    card = db.fetch_admin_card_detail(card_id)
    assert result.updated == 1
    assert card["raw_material_a"] == "LDPE New Source | 70%"
    assert card["raw_material_b"] == "LLDPE Added Source | 30%"
    assert card["linear_pe"] == ""
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE New Source | 70%", "LDPE", "New Source"),
        ("raw_material_b", "LLDPE Added Source | 30%", "LLDPE", "Added Source"),
    ]
    assert dict(actual_entry(connection, card_id, "raw_material_a")) == {
        "planned_material": "LDPE Rompetrol B20/03 | 80%",
        "actual_material_used": "Actual LDPE",
        "batch_lot": "Batch A",
    }
    assert dict(actual_entry(connection, card_id, "linear_pe")) == {
        "planned_material": "LLDPE SABIC 119ZJ | 20%",
        "actual_material_used": "Actual LLDPE",
        "batch_lot": "Batch L",
    }


def test_duplicate_skip_does_not_refresh_recipe_components(connection):
    card_id = import_card("RS-SYNC-003")

    result = import_cards_from_csv(
        "structured-duplicate-skip.csv",
        csv_bytes(
            structured_row(
                "RS-SYNC-003",
                raw_material_a="LDPE Should Not Apply | 100%",
                linear_pe="",
            )
        ),
        overwrite_existing=False,
    )

    assert result.rows_imported == 0
    assert result.skipped == 1
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Rompetrol B20/03 | 80%", "LDPE", "Rompetrol B20/03"),
        ("linear_pe", "LLDPE SABIC 119ZJ | 20%", "LLDPE", "SABIC 119ZJ"),
    ]


def test_import_sync_does_not_block_parser_errors_before_release(connection):
    result = import_cards_from_csv(
        "structured-invalid-total.csv",
        csv_bytes(
            structured_row(
                "RS-SYNC-004",
                raw_material_a="LDPE Rompetrol B20/03 | 80%",
                linear_pe="LLDPE SABIC 119ZJ | 19%",
            )
        ),
        overwrite_existing=False,
    )
    card_id = int(
        connection.execute(
            "SELECT id FROM cards WHERE order_number = 'RS-SYNC-004'"
        ).fetchone()["id"]
    )

    assert result.created == 1
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Rompetrol B20/03 | 80%", "LDPE", "Rompetrol B20/03"),
        ("linear_pe", "LLDPE SABIC 119ZJ | 19%", "LLDPE", "SABIC 119ZJ"),
    ]


def test_admin_imported_field_correction_refreshes_recipe_components(connection):
    card_id = import_card("RS-SYNC-005")
    card = db.fetch_admin_card_detail(card_id)
    fields = current_import_fields(card_id)
    fields["raw_material_a"] = "LDPE Admin Corrected | 100%"
    fields["linear_pe"] = ""

    result = db.update_admin_imported_fields(card_id, card["version"], fields)

    assert result.ok
    updated = db.fetch_admin_card_detail(card_id)
    assert updated["raw_material_a"] == "LDPE Admin Corrected | 100%"
    assert updated["linear_pe"] == ""
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Admin Corrected | 100%", "LDPE", "Admin Corrected"),
    ]


def test_admin_source_correction_syncs_category_only_rows(connection):
    card_id = import_card("RS-SYNC-013")
    card = db.fetch_admin_card_detail(card_id)
    fields = current_import_fields(card_id)
    fields["raw_material_a"] = "reLDPE | 100%"
    fields["linear_pe"] = ""

    result = db.update_admin_imported_fields(card_id, card["version"], fields)

    assert result.ok
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "reLDPE | 100%", "reLDPE", ""),
    ]


def test_admin_imported_field_correction_does_not_block_parser_errors(connection):
    card_id = import_card("RS-SYNC-006")
    card = db.fetch_admin_card_detail(card_id)
    fields = current_import_fields(card_id)
    fields["raw_material_a"] = "LDPE Admin Invalid Total | 80%"
    fields["linear_pe"] = "LLDPE Admin Invalid Total | 19%"

    result = db.update_admin_imported_fields(card_id, card["version"], fields)

    assert result.ok
    updated = db.fetch_admin_card_detail(card_id)
    assert updated["raw_material_a"] == "LDPE Admin Invalid Total | 80%"
    assert updated["linear_pe"] == "LLDPE Admin Invalid Total | 19%"
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Admin Invalid Total | 80%", "LDPE", "Admin Invalid Total"),
        ("linear_pe", "LLDPE Admin Invalid Total | 19%", "LLDPE", "Admin Invalid Total"),
    ]


def test_stale_admin_imported_field_correction_does_not_refresh_components(connection):
    card_id = import_card("RS-SYNC-007")
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]
    fields = current_import_fields(card_id)
    fields["customer"] = "First admin save"
    assert db.update_admin_imported_fields(card_id, loaded_version, fields).ok
    post_save = db.fetch_admin_card_detail(card_id)
    post_save_version = post_save["version"]

    stale_fields = current_import_fields(card_id)
    stale_fields["raw_material_a"] = "LDPE Stale Source | 100%"
    stale_fields["linear_pe"] = ""
    stale_result = db.update_admin_imported_fields(
        card_id,
        loaded_version,
        stale_fields,
    )

    assert not stale_result.ok
    assert stale_result.messages == (db.STALE_CARD_MESSAGE,)
    post_stale = db.fetch_admin_card_detail(card_id)
    assert post_stale["customer"] == "First admin save"
    assert post_stale["raw_material_a"] == "LDPE Rompetrol B20/03 | 80%"
    assert post_stale["linear_pe"] == "LLDPE SABIC 119ZJ | 20%"
    assert post_stale["version"] == post_save_version
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Rompetrol B20/03 | 80%", "LDPE", "Rompetrol B20/03"),
        ("linear_pe", "LLDPE SABIC 119ZJ | 20%", "LLDPE", "SABIC 119ZJ"),
    ]


def test_admin_material_ledger_refreshes_components_without_touching_actual_values(connection):
    card_id = import_card("RS-SYNC-008")
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        loaded_version,
        {
            "raw_material_a": {
                "actual_material_used": "Existing Actual A",
                "batch_lot": "Existing Batch A",
            },
            "linear_pe": {
                "actual_material_used": "Existing Actual Linear",
                "batch_lot": "Existing Batch Linear",
            },
        },
    ).ok

    result = db.update_admin_material_ledger(
        card_id=card_id,
        loaded_version=db.fetch_admin_card_detail(card_id)["version"],
        planned_materials={
            "raw_material_a": "LDPE Ledger Corrected | 60%",
            "raw_material_b": "LLDPE Ledger Added | 40%",
            "raw_material_c": "",
            "linear_pe": "",
            "antistatic": "",
            "masterbatch": "",
            "chalk": "",
        },
        actual_entries={
            "raw_material_a": {
                "actual_material_used": "Existing Actual A",
                "batch_lot": "Existing Batch A",
            },
            "linear_pe": {
                "actual_material_used": "Existing Actual Linear",
                "batch_lot": "Existing Batch Linear",
            },
        },
    )

    assert result.ok
    assert dict(actual_entry(connection, card_id, "raw_material_a")) == {
        "planned_material": "LDPE Ledger Corrected | 60%",
        "actual_material_used": "Existing Actual A",
        "batch_lot": "Existing Batch A",
    }
    assert dict(actual_entry(connection, card_id, "linear_pe")) == {
        "planned_material": "",
        "actual_material_used": "Existing Actual Linear",
        "batch_lot": "Existing Batch Linear",
    }
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Ledger Corrected | 60%", "LDPE", "Ledger Corrected"),
        ("raw_material_b", "LLDPE Ledger Added | 40%", "LLDPE", "Ledger Added"),
    ]


def test_admin_material_ledger_does_not_block_parser_errors(connection):
    card_id = import_card("RS-SYNC-009")
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        loaded_version,
        {
            "raw_material_a": {
                "actual_material_used": "Parser Error Existing Actual A",
                "batch_lot": "Parser Error Existing Batch A",
            },
            "linear_pe": {
                "actual_material_used": "Parser Error Existing Actual Linear",
                "batch_lot": "Parser Error Existing Batch Linear",
            },
        },
    ).ok

    result = db.update_admin_material_ledger(
        card_id=card_id,
        loaded_version=db.fetch_admin_card_detail(card_id)["version"],
        planned_materials={
            "raw_material_a": "LDPE Ledger Invalid Total | 80%",
            "linear_pe": "LLDPE Ledger Invalid Total | 19%",
        },
        actual_entries={
            "raw_material_a": {
                "actual_material_used": "Parser Error Existing Actual A",
                "batch_lot": "Parser Error Existing Batch A",
            },
            "linear_pe": {
                "actual_material_used": "Parser Error Existing Actual Linear",
                "batch_lot": "Parser Error Existing Batch Linear",
            },
        },
    )

    assert result.ok
    updated = db.fetch_admin_card_detail(card_id)
    assert updated["raw_material_a"] == "LDPE Ledger Invalid Total | 80%"
    assert updated["linear_pe"] == "LLDPE Ledger Invalid Total | 19%"
    assert dict(actual_entry(connection, card_id, "raw_material_a")) == {
        "planned_material": "LDPE Ledger Invalid Total | 80%",
        "actual_material_used": "Parser Error Existing Actual A",
        "batch_lot": "Parser Error Existing Batch A",
    }
    assert dict(actual_entry(connection, card_id, "linear_pe")) == {
        "planned_material": "LLDPE Ledger Invalid Total | 19%",
        "actual_material_used": "Parser Error Existing Actual Linear",
        "batch_lot": "Parser Error Existing Batch Linear",
    }
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Ledger Invalid Total | 80%", "LDPE", "Ledger Invalid Total"),
        ("linear_pe", "LLDPE Ledger Invalid Total | 19%", "LLDPE", "Ledger Invalid Total"),
    ]


def test_step_6_admin_and_terminal_display_use_normalized_recipe_rows(connection):
    card_id = import_card(
        "RS-SYNC-008",
        quantity_1="1000",
        unit_1="kg",
        raw_material_a="LDPE Display Source | 80%",
        linear_pe="LLDPE Display Source | 20%",
    )
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        {
            "raw_material_a": {
                "actual_material_used": "Actual Display A",
                "batch_lot": "Batch Display A",
            },
            "linear_pe": {
                "actual_material_used": "Actual Display L",
                "batch_lot": "Batch Display L",
            },
        },
    ).ok

    admin_context = admin_card_detail_context(card_id)
    terminal = terminal_context(card_id)

    admin_rows = {row["field"]: row for row in admin_context["recipe_rows"]}
    terminal_rows = {row["field"]: row for row in terminal["recipe_rows"]}

    assert admin_rows["raw_material_a"]["source_text"] == "LDPE Display Source | 80%"
    assert admin_rows["raw_material_a"]["material_category"] == "LDPE"
    assert admin_rows["raw_material_a"]["planned_material"] == "Display Source"
    assert admin_rows["raw_material_a"]["recipe_percent"] == "80%"
    assert admin_rows["raw_material_a"]["planned_kg"] == "800.00"
    assert admin_rows["raw_material_a"]["actual_material"] == "Actual Display A"
    assert admin_rows["raw_material_a"]["batch"] == "Batch Display A"

    assert terminal_rows["raw_material_a"]["source_text"] == "LDPE Display Source | 80%"
    assert terminal_rows["raw_material_a"]["material_category"] == "LDPE"
    assert terminal_rows["raw_material_a"]["planned_material"] == "Display Source"
    assert terminal_rows["raw_material_a"]["recipe_percent"] == "80%"
    assert terminal_rows["raw_material_a"]["planned_kg"] == "800"
    assert terminal_rows["raw_material_a"]["actual_material"] == "Actual Display A"
    assert terminal_rows["linear_pe"]["planned_material"] == "Display Source"
    assert "chalk" not in terminal_rows


def test_admin_and_terminal_planned_kg_use_quantity_1_only(connection):
    card_id = import_card(
        "RS-SYNC-015",
        quantity_1="1000",
        unit_1="rolls",
        quantity_2="9999",
        unit_2="kg",
        raw_material_a="LDPE Display Source | 80%",
        linear_pe="LLDPE Display Source | 20%",
    )
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok

    admin_context = admin_card_detail_context(card_id)
    terminal = terminal_context(card_id)
    admin_rows = {row["field"]: row for row in admin_context["recipe_rows"]}
    terminal_rows = {row["field"]: row for row in terminal["recipe_rows"]}

    assert admin_rows["raw_material_a"]["planned_kg"] == "800.00"
    assert admin_rows["linear_pe"]["planned_kg"] == "200.00"
    assert terminal_rows["raw_material_a"]["planned_kg"] == "800"
    assert terminal_rows["linear_pe"]["planned_kg"] == "200"


def test_admin_and_terminal_display_use_category_fallback_for_category_only_rows(connection):
    card_id = import_card(
        "RS-SYNC-014",
        quantity_1="1000",
        unit_1="kg",
        raw_material_a="reLDPE | 80%",
        linear_pe="LLDPE SABIC 119ZJ | 20%",
    )
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok

    admin_context = admin_card_detail_context(card_id)
    terminal = terminal_context(card_id)
    admin_rows = {row["field"]: row for row in admin_context["recipe_rows"]}
    terminal_rows = {row["field"]: row for row in terminal["recipe_rows"]}

    assert admin_rows["raw_material_a"]["material_category"] == "reLDPE"
    assert admin_rows["raw_material_a"]["planned_material"] == "reLDPE"
    assert admin_rows["raw_material_a"]["source_text"] == "reLDPE | 80%"
    assert admin_rows["raw_material_a"]["recipe_percent"] == "80%"
    assert admin_rows["raw_material_a"]["planned_kg"] == "800.00"
    assert admin_rows["raw_material_a"]["is_structured"] is True

    assert terminal_rows["raw_material_a"]["material_category"] == "reLDPE"
    assert terminal_rows["raw_material_a"]["planned_material"] == "reLDPE"
    assert terminal_rows["raw_material_a"]["source_text"] == "reLDPE | 80%"
    assert terminal_rows["raw_material_a"]["recipe_percent"] == "80%"
    assert terminal_rows["raw_material_a"]["planned_kg"] == "800"
    assert terminal_rows["raw_material_a"]["is_structured"] is True
    assert terminal_rows["linear_pe"]["planned_material"] == "SABIC 119ZJ"


def test_admin_recipe_display_keeps_source_text_when_row_has_no_normalized_component(connection):
    card_id = import_card(
        "RS-SYNC-010",
        raw_material_a="LDPE Missing Delimiter 80%",
        linear_pe="LLDPE Valid Row | 20%",
    )

    context = admin_card_detail_context(card_id)
    rows = {row["field"]: row for row in context["recipe_rows"]}

    assert rows["raw_material_a"]["source_text"] == "LDPE Missing Delimiter 80%"
    assert rows["raw_material_a"]["planned_material"] == "LDPE Missing Delimiter 80%"
    assert rows["raw_material_a"]["material_category"] == ""
    assert rows["raw_material_a"]["recipe_percent"] == ""
    assert rows["raw_material_a"]["planned_kg"] == ""
    assert rows["raw_material_a"]["is_structured"] is False
    assert rows["linear_pe"]["material_category"] == "LLDPE"
    assert rows["linear_pe"]["planned_material"] == "Valid Row"


def test_step_4_keeps_print_recipe_rows_on_original_source_text(connection):
    card_id = import_card(
        "RS-SYNC-011",
        raw_material_a="LDPE Print Source | 80%",
        linear_pe="LLDPE Print Source | 20%",
    )
    poison_raw_material_a_component(connection, card_id)
    card = db.fetch_admin_card_detail(card_id)

    rows = build_print_recipe_rows(card, card["recipe_actual_entries"])
    by_key = {row["component_key"]: row for row in rows}

    assert by_key["raw_material_a"]["planned_material"] == "LDPE Print Source | 80%"
    assert by_key["raw_material_a"]["planned_material"] != (
        "LDPE Derived Should Not Display | 100%"
    )
    assert by_key["linear_pe"]["planned_material"] == "LLDPE Print Source | 20%"
