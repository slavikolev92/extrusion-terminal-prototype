from __future__ import annotations

from pathlib import Path

from app import db
from app.constants import STATUS_COMPLETED, STATUS_PENDING
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import admin_card_detail_context, terminal_context
from app.printing import build_print_readiness


FIXTURE_PATH = Path("tests/fixtures/structured_recipe_sample.csv")


def import_sample_csv() -> object:
    return import_cards_from_csv(
        "structured_recipe_sample.csv",
        FIXTURE_PATH.read_bytes(),
        overwrite_existing=False,
    )


def card_id_for_order(order_number: str) -> int:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT id FROM cards WHERE order_number = ?",
            (order_number,),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def component_summary(card_id: int) -> list[tuple[str, str, str, str, str]]:
    with db.connect() as connection:
        return [
            (
                str(row["component_key"]),
                str(row["source_text"]),
                str(row["material_category"]),
                str(row["planned_material"]),
                str(row["recipe_percent"]),
            )
            for row in db.fetch_recipe_components(connection, card_id)
        ]


def current_import_fields(card_id: int) -> dict[str, str]:
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    return {field: str(card[field] or "") for field in IMPORT_FIELDS}


def card_version(card_id: int) -> int:
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    return int(card["version"])


def terminal_card_version(card_id: int) -> int:
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    return int(card["version"])


def release_card(card_id: int, machine_id: int = 1, sequence: int = 1):
    return db.release_card(
        card_id,
        machine_id=machine_id,
        machine_sequence=sequence,
        loaded_version=card_version(card_id),
    )


def complete_card(card_id: int) -> None:
    assert db.start_production_timing(card_id, terminal_card_version(card_id)).ok
    assert db.update_tare_weight(card_id, terminal_card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, terminal_card_version(card_id), "501.20").ok
    assert db.finish_card(card_id, terminal_card_version(card_id)).ok


def test_structured_sample_csv_imports_and_normalizes_recipe_components(connection):
    result = import_sample_csv()

    assert result.rows_seen == 4
    assert result.rows_imported == 4
    assert result.created == 4
    assert result.updated == 0
    assert result.skipped == 0
    assert result.row_errors == []

    full_id = card_id_for_order("SR-SAMPLE-001")
    recycled_id = card_id_for_order("SR-SAMPLE-002")
    one_sided_id = card_id_for_order("SR-SAMPLE-003")
    correction_id = card_id_for_order("SR-SAMPLE-004")

    assert component_summary(full_id) == [
        (
            "raw_material_a",
            "LDPE; Rompetrol Midilena B20/03 | 77%",
            "LDPE",
            "Rompetrol Midilena B20/03",
            "77",
        ),
        ("linear_pe", "LLDPE; SABIC 119ZJ | 18%", "LLDPE", "SABIC 119ZJ", "18"),
        (
            "antistatic",
            "Antistatic; Novachem AT 04673 LD | 2%",
            "Antistatic",
            "Novachem AT 04673 LD",
            "2",
        ),
        (
            "masterbatch",
            "Masterbatch; Polibach White 8000 ET | 3%",
            "Masterbatch",
            "Polibach White 8000 ET",
            "3",
        ),
    ]
    assert component_summary(recycled_id) == [
        ("raw_material_a", "reLDPE; Recycled LDPE | 80%", "reLDPE", "Recycled LDPE", "80"),
        ("linear_pe", "LLDPE; SABIC 119ZJ | 20%", "LLDPE", "SABIC 119ZJ", "20"),
    ]
    assert component_summary(one_sided_id) == [
        ("raw_material_a", "LDPE; B20/03 | 95%", "LDPE", "B20/03", "95"),
        ("masterbatch", "Masterbatch; White MB | 5%", "Masterbatch", "White MB", "5"),
    ]
    assert component_summary(correction_id) == [
        ("raw_material_a", "LDPE; Correction A | 80%", "LDPE", "Correction A", "80"),
        ("linear_pe", "LLDPE; Correction L | 20%", "LLDPE", "Correction L", "20"),
    ]


def test_structured_sample_invalid_total_variant_is_blocked_at_import(connection):
    invalid_bytes = FIXTURE_PATH.read_bytes().replace(
        b"LLDPE; Correction L | 20%",
        b"LLDPE; Correction L | 19%",
    )

    result = import_cards_from_csv(
        "structured_recipe_sample_invalid_total.csv",
        invalid_bytes,
        overwrite_existing=False,
    )

    assert result.rows_seen == 4
    assert result.rows_imported == 3
    assert result.skipped == 1

    blocked_results = [row for row in result.row_results if row.action == "blocked"]
    assert len(blocked_results) == 1
    assert "Рецептата не може да бъде импортирана" in blocked_results[0].message

    with db.connect() as connection:
        imported_orders = {
            str(row["order_number"])
            for row in connection.execute("SELECT order_number FROM cards")
        }

    assert "SR-SAMPLE-004" not in imported_orders
    assert {
        "SR-SAMPLE-001",
        "SR-SAMPLE-002",
        "SR-SAMPLE-003",
    }.issubset(imported_orders)


def test_structured_sample_valid_total_releases_and_admin_correction_stays_structured(
    connection,
):
    import_sample_csv()
    card_id = card_id_for_order("SR-SAMPLE-004")

    fields = current_import_fields(card_id)
    fields["linear_pe"] = "LLDPE; Adjusted Correction L | 20%"
    saved = db.update_admin_imported_fields(card_id, card_version(card_id), fields)
    assert saved.ok
    assert component_summary(card_id) == [
        ("raw_material_a", "LDPE; Correction A | 80%", "LDPE", "Correction A", "80"),
        (
            "linear_pe",
            "LLDPE; Adjusted Correction L | 20%",
            "LLDPE",
            "Adjusted Correction L",
            "20",
        ),
    ]

    released = release_card(card_id, machine_id=2, sequence=1)
    released_card = db.fetch_admin_card_detail(card_id)

    assert released.ok
    assert released_card["status"] == STATUS_PENDING
    assert released_card["machine_id"] == 2
    assert released_card["machine_sequence"] == 1


def test_structured_sample_admin_and_terminal_display_structured_rows(connection):
    import_sample_csv()
    card_id = card_id_for_order("SR-SAMPLE-002")
    assert release_card(card_id, machine_id=1, sequence=1).ok

    admin_context = admin_card_detail_context(card_id)
    terminal = terminal_context(card_id)
    assert admin_context is not None
    admin_rows = {row["field"]: row for row in admin_context["recipe_rows"]}
    terminal_rows = {row["field"]: row for row in terminal["recipe_rows"]}

    assert admin_rows["raw_material_a"]["source_text"] == "reLDPE; Recycled LDPE | 80%"
    assert admin_rows["raw_material_a"]["material_category"] == "reLDPE"
    assert admin_rows["raw_material_a"]["planned_material"] == "Recycled LDPE"
    assert admin_rows["raw_material_a"]["recipe_percent"] == "80%"
    assert admin_rows["raw_material_a"]["planned_kg"] == "1000.00"
    assert admin_rows["raw_material_a"]["is_structured"] is True

    assert terminal_rows["raw_material_a"]["source_text"] == "reLDPE; Recycled LDPE | 80%"
    assert terminal_rows["raw_material_a"]["material_category"] == "reLDPE"
    assert terminal_rows["raw_material_a"]["planned_material"] == "Recycled LDPE"
    assert terminal_rows["raw_material_a"]["recipe_percent"] == "80%"
    assert terminal_rows["raw_material_a"]["planned_kg"] == "1000"
    assert terminal_rows["linear_pe"]["planned_material"] == "SABIC 119ZJ"
    assert "masterbatch" not in terminal_rows


def test_structured_sample_terminal_material_save_and_completion(connection):
    import_sample_csv()
    card_id = card_id_for_order("SR-SAMPLE-001")
    assert release_card(card_id, machine_id=1, sequence=1).ok

    saved = db.update_terminal_recipe_actual_entries(
        card_id,
        terminal_card_version(card_id),
        {
            "raw_material_a": {
                "actual_material_used": "Actual Rompetrol B20/03",
                "batch_lot": "LOT-A-77",
            },
            "linear_pe": {
                "actual_material_used": "Actual SABIC 119ZJ",
                "batch_lot": "LOT-L-18",
            },
            "antistatic": {
                "actual_material_used": "Actual AT 04673",
                "batch_lot": "LOT-AS-2",
            },
            "masterbatch": {
                "actual_material_used": "Actual White 8000",
                "batch_lot": "LOT-MB-3",
            },
        },
    )
    assert saved.ok

    terminal = terminal_context(card_id)
    rows = {row["field"]: row for row in terminal["recipe_rows"]}
    assert rows["raw_material_a"]["actual_material"] == "Actual Rompetrol B20/03"
    assert rows["raw_material_a"]["batch"] == "LOT-A-77"
    assert rows["masterbatch"]["actual_material"] == "Actual White 8000"

    complete_card(card_id)
    completed = db.fetch_admin_card_detail(card_id)
    assert completed["status"] == STATUS_COMPLETED
    assert completed["finished_at"]
    assert completed["total_gross_weight"] is not None
    assert completed["total_net_weight"] is not None


def test_structured_sample_print_output_uses_compact_material_and_percent(connection):
    import_sample_csv()
    card_id = card_id_for_order("SR-SAMPLE-001")
    assert release_card(card_id, machine_id=1, sequence=1).ok
    complete_card(card_id)

    readiness = build_print_readiness(card_id)

    assert readiness.ok
    assert readiness.data is not None
    assert readiness.data["front"]["ordered_gross_display"] == "1000 кг"
    assert readiness.data["front"]["ordered_rolls_display"] == "24 ролки"
    assert readiness.data["front"]["ordered_meters_display"] == "18000 метра"
    assert readiness.data["front"]["ordered_units_display"] == "48000 бр."
    rows = {
        row["component_key"]: row
        for row in readiness.data["front"]["recipe_rows"]
    }
    assert rows["raw_material_a"]["planned_material"] == "Rompetrol Midilena B20/03 77%"
    assert rows["linear_pe"]["planned_material"] == "SABIC 119ZJ 18%"
    assert rows["antistatic"]["planned_material"] == "Novachem AT 04673 LD 2%"
    assert rows["masterbatch"]["planned_material"] == "Polibach White 8000 ET 3%"
    assert "material_category" not in rows["raw_material_a"]
