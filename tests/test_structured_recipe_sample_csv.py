from __future__ import annotations

from pathlib import Path

from app import db
from app.constants import STATUS_COMPLETED, STATUS_IMPORTED, STATUS_PENDING
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import admin_card_detail_context, terminal_context
from app.printing import build_print_readiness


FIXTURE_PATH = Path("tests/fixtures/structured_recipe_sample.csv")
RECIPE_RELEASE_PREFIX = "Рецептата не може да бъде пусната"


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
        max_roll_weight="64.50",
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
    category_only_id = card_id_for_order("SR-SAMPLE-002")
    one_sided_id = card_id_for_order("SR-SAMPLE-003")
    correction_id = card_id_for_order("SR-SAMPLE-004")

    assert component_summary(full_id) == [
        (
            "raw_material_a",
            "LDPE Rompetrol Midilena B20/03 | 77%",
            "LDPE",
            "Rompetrol Midilena B20/03",
            "77",
        ),
        ("linear_pe", "LLDPE SABIC 119ZJ | 18%", "LLDPE", "SABIC 119ZJ", "18"),
        (
            "antistatic",
            "Antistatic Novachem AT 04673 LD | 2%",
            "Antistatic",
            "Novachem AT 04673 LD",
            "2",
        ),
        (
            "masterbatch",
            "Masterbatch Polibach White 8000 ET | 3%",
            "Masterbatch",
            "Polibach White 8000 ET",
            "3",
        ),
    ]
    assert component_summary(category_only_id) == [
        ("raw_material_a", "reLDPE | 80%", "reLDPE", "", "80"),
        ("linear_pe", "LLDPE SABIC 119ZJ | 20%", "LLDPE", "SABIC 119ZJ", "20"),
    ]
    assert component_summary(one_sided_id) == [
        ("raw_material_a", "LDPE B20/03 | 95%", "LDPE", "B20/03", "95"),
        ("masterbatch", "Masterbatch | 5%", "Masterbatch", "", "5"),
    ]
    assert component_summary(correction_id) == [
        ("raw_material_a", "LDPE Correction A | 80%", "LDPE", "Correction A", "80"),
        ("linear_pe", "LLDPE Correction L | 19%", "LLDPE", "Correction L", "19"),
    ]


def test_structured_sample_invalid_total_blocks_release_until_admin_correction(connection):
    import_sample_csv()
    card_id = card_id_for_order("SR-SAMPLE-004")

    blocked = release_card(card_id)
    card = db.fetch_admin_card_detail(card_id)

    assert not blocked.ok
    assert blocked.messages == (
        f"{RECIPE_RELEASE_PREFIX}: сборът на процентите трябва да е точно 100%. "
        "Коригирайте рецептата и опитайте отново.",
    )
    assert card["status"] == STATUS_IMPORTED
    assert card["machine_id"] is None
    assert card["machine_sequence"] is None

    fields = current_import_fields(card_id)
    fields["linear_pe"] = "LLDPE Correction L | 20%"
    saved = db.update_admin_imported_fields(card_id, card_version(card_id), fields)
    assert saved.ok
    assert component_summary(card_id) == [
        ("raw_material_a", "LDPE Correction A | 80%", "LDPE", "Correction A", "80"),
        ("linear_pe", "LLDPE Correction L | 20%", "LLDPE", "Correction L", "20"),
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

    assert admin_rows["raw_material_a"]["source_text"] == "reLDPE | 80%"
    assert admin_rows["raw_material_a"]["material_category"] == "reLDPE"
    assert admin_rows["raw_material_a"]["planned_material"] == "reLDPE"
    assert admin_rows["raw_material_a"]["recipe_percent"] == "80%"
    assert admin_rows["raw_material_a"]["planned_kg"] == "1000.00"
    assert admin_rows["raw_material_a"]["is_structured"] is True

    assert terminal_rows["raw_material_a"]["source_text"] == "reLDPE | 80%"
    assert terminal_rows["raw_material_a"]["material_category"] == "reLDPE"
    assert terminal_rows["raw_material_a"]["planned_material"] == "reLDPE"
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


def test_structured_sample_print_output_uses_original_source_text(connection):
    import_sample_csv()
    card_id = card_id_for_order("SR-SAMPLE-001")
    assert release_card(card_id, machine_id=1, sequence=1).ok
    complete_card(card_id)

    readiness = build_print_readiness(card_id)

    assert readiness.ok
    assert readiness.data is not None
    rows = {
        row["component_key"]: row
        for row in readiness.data["front"]["recipe_rows"]
    }
    assert rows["raw_material_a"]["planned_material"] == (
        "LDPE Rompetrol Midilena B20/03 | 77%"
    )
    assert rows["linear_pe"]["planned_material"] == "LLDPE SABIC 119ZJ | 18%"
    assert rows["antistatic"]["planned_material"] == (
        "Antistatic Novachem AT 04673 LD | 2%"
    )
    assert rows["masterbatch"]["planned_material"] == (
        "Masterbatch Polibach White 8000 ET | 3%"
    )
    assert "material_category" not in rows["raw_material_a"]
