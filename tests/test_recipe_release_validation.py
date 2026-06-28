from __future__ import annotations

import asyncio
import csv
import io

import pytest
from starlette.requests import Request

from app import db
from app.constants import STATUS_IMPORTED, STATUS_PENDING
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import app, release_card_to_terminal


RECIPE_RELEASE_PREFIX = "Рецептата не може да бъде пусната"


def csv_bytes(*rows: dict[str, str]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")


def structured_release_row(order_number: str, **overrides: str) -> dict[str, str]:
    row = {
        "order_number": order_number,
        "order_date": "2026-06-25",
        "delivery_date": "2026-06-30",
        "customer": "Structured Release Customer",
        "city": "Sofia",
        "product_type": "PE film",
        "quantity_1": "1000",
        "unit_1": "kg",
        "quantity_2": "",
        "unit_2": "",
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


def import_structured_card(order_number: str, **overrides: str) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(structured_release_row(order_number, **overrides)),
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


def assert_card_still_imported(card_id: int) -> None:
    card = db.fetch_admin_card_detail(card_id)
    assert card["status"] == STATUS_IMPORTED
    assert card["machine_id"] is None
    assert card["machine_sequence"] is None


def make_request(path: str, method: str = "POST") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
            "app": app,
        }
    )


def test_release_allows_valid_structured_recipe_and_target_gross(connection):
    card_id = import_structured_card("RS-REL-001")

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["status"] == STATUS_PENDING
    assert card["machine_id"] == 1
    assert card["machine_sequence"] == 1


@pytest.mark.parametrize(
    ("order_number", "overrides", "expected_reason"),
    [
        (
            "RS-REL-002",
            {"raw_material_a": "LDPE Rompetrol B20/03 80%"},
            "Суровина A: липсва разделител |",
        ),
        (
            "RS-REL-003",
            {"raw_material_a": "mLLDPE Marlex 1018 | 80%"},
            "Суровина A: непозната категория",
        ),
        (
            "RS-REL-004",
            {"raw_material_a": " | 80%"},
            "Суровина A: липсва материал след категория",
        ),
        (
            "RS-REL-005",
            {"raw_material_a": "LDPE Rompetrol B20/03 | 80"},
            "Суровина A: липсва процент",
        ),
        (
            "RS-REL-006",
            {
                "raw_material_a": "LDPE Rompetrol B20/03 | 0%",
                "linear_pe": "LLDPE SABIC 119ZJ | 100%",
            },
            "Суровина A: процентът трябва да е по-голям от 0%",
        ),
    ],
)
def test_release_blocks_recipe_row_contract_failures(
    connection,
    order_number,
    overrides,
    expected_reason,
):
    card_id = import_structured_card(order_number, **overrides)

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)

    assert not result.ok
    assert result.messages == (
        f"{RECIPE_RELEASE_PREFIX}: {expected_reason}. Коригирайте рецептата и опитайте отново.",
    )
    assert_card_still_imported(card_id)


def test_release_blocks_recipe_total_that_is_not_exactly_100(connection):
    card_id = import_structured_card(
        "RS-REL-007",
        raw_material_a="LDPE Rompetrol B20/03 | 80%",
        linear_pe="LLDPE SABIC 119ZJ | 19%",
    )

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)

    assert not result.ok
    assert result.messages == (
        f"{RECIPE_RELEASE_PREFIX}: сборът на процентите трябва да е точно 100%. "
        "Коригирайте рецептата и опитайте отново.",
    )
    assert_card_still_imported(card_id)


@pytest.mark.parametrize(
    ("order_number", "overrides"),
    [
        ("RS-REL-008", {"quantity_1": "", "unit_1": ""}),
        ("RS-REL-009", {"quantity_1": "0", "unit_1": "kg"}),
        ("RS-REL-010", {"quantity_1": "-10", "unit_1": "kg"}),
        ("RS-REL-011", {"quantity_1": "not a number", "unit_1": "kg"}),
        ("RS-REL-017", {"quantity_1": "-10 kg", "unit_1": "kg"}),
        ("RS-REL-018", {"quantity_1": "abc10", "unit_1": "kg"}),
        ("RS-REL-019", {"quantity_1": "10 kg", "unit_1": "kg"}),
        ("RS-REL-020", {"quantity_1": "Infinity", "unit_1": "kg"}),
        ("RS-REL-021", {"quantity_1": "NaN", "unit_1": "kg"}),
    ],
)
def test_release_blocks_missing_zero_or_invalid_target_gross(
    connection,
    order_number,
    overrides,
):
    card_id = import_structured_card(order_number, **overrides)

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)

    assert not result.ok
    assert result.messages == (
        f"{RECIPE_RELEASE_PREFIX}: липсват планирани кг/поръчано количество. "
        "Коригирайте рецептата и опитайте отново.",
    )
    assert_card_still_imported(card_id)


def test_release_accepts_positive_quantity_1_without_unit_1_kg_check(connection):
    card_id = import_structured_card(
        "RS-REL-012",
        quantity_1="1250,5",
        unit_1="бр",
        quantity_2="not target gross",
        unit_2="nonsense",
        raw_material_a="LDPE Rompetrol B20/03 | 97,5%",
        linear_pe="LLDPE SABIC 119ZJ | 2,5%",
    )

    result = db.release_card(card_id, machine_id=2, machine_sequence=3)
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["status"] == STATUS_PENDING
    assert card["machine_id"] == 2
    assert card["machine_sequence"] == 1


def test_release_blocks_invalid_quantity_1_even_when_quantity_2_is_kg_like(connection):
    card_id = import_structured_card(
        "RS-REL-024",
        quantity_1="",
        unit_1="",
        quantity_2="1250,5",
        unit_2="кг",
        raw_material_a="LDPE Rompetrol B20/03 | 97,5%",
        linear_pe="LLDPE SABIC 119ZJ | 2,5%",
    )

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)

    assert not result.ok
    assert result.messages == (
        f"{RECIPE_RELEASE_PREFIX}: липсват планирани кг/поръчано количество. "
        "Коригирайте рецептата и опитайте отново.",
    )
    assert_card_still_imported(card_id)


def test_release_allows_category_only_recipe_rows_from_excel_builder_na_omissions(connection):
    card_id = import_structured_card(
        "RS-REL-022",
        raw_material_a="reLDPE | 80%",
        linear_pe="LLDPE SABIC 119ZJ | 20%",
    )

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["status"] == STATUS_PENDING
    assert card["raw_material_a"] == "reLDPE | 80%"


def test_release_allows_category_only_rows_for_all_approved_categories_without_catalog_lookup(
    connection,
):
    card_id = import_structured_card(
        "RS-REL-023",
        raw_material_a="LDPE | 95%",
        masterbatch="Masterbatch | 5%",
        linear_pe="",
    )

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)

    assert result.ok


def test_import_still_allows_invalid_recipe_for_admin_correction_before_release(connection):
    result = import_cards_from_csv(
        "invalid-draft.csv",
        csv_bytes(
            structured_release_row(
                "RS-REL-014",
                raw_material_a="LDPE Draft Bad Total | 80%",
                linear_pe="LLDPE Draft Bad Total | 19%",
            )
        ),
        overwrite_existing=False,
    )
    with db.connect() as connection:
        imported = connection.execute(
            "SELECT status FROM cards WHERE order_number = 'RS-REL-014'"
        ).fetchone()

    assert result.rows_imported == 1
    assert result.created == 1
    assert imported["status"] == STATUS_IMPORTED


def test_admin_release_route_renders_recipe_gate_errors_inline(connection):
    card_id = import_structured_card(
        "RS-REL-016",
        raw_material_a="LDPE Route Bad Total | 80%",
        linear_pe="LLDPE Route Bad Total | 19%",
    )
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]

    response = asyncio.run(
        release_card_to_terminal(
            make_request(f"/admin/cards/{card_id}/release"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            max_roll_weight="60.0",
            machine_id="1",
            machine_sequence="1",
            return_anchor="unreleased-queue",
        )
    )
    card = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 200
    assert "location" not in response.headers
    assert "release_result" in response.context
    assert response.context["release_result"].messages == (
        f"{RECIPE_RELEASE_PREFIX}: сборът на процентите трябва да е точно 100%. "
        "Коригирайте рецептата и опитайте отново.",
    )
    assert card["status"] == STATUS_IMPORTED
    assert card["machine_id"] is None
    assert card["machine_sequence"] is None
