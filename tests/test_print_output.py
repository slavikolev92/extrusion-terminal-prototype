from __future__ import annotations

import asyncio
import csv
import io
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path

import pytest

from app import db
from app.constants import (
    STATUS_ARCHIVED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_IMPORTED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_RUNNING,
)
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import app
from app.printing import (
    build_print_readiness,
    format_datetime,
    format_duration,
    format_weight,
)

PRINT_CSS_PATH = Path(__file__).resolve().parent.parent / "app/static/css/print.css"


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
        "order_date": "18.06.2026",
        "delivery_date": "25.06.2026",
        "customer": "Print Customer",
        "city": "Sofia",
        "product_type": "PE film",
        "quantity_1": "500.555",
        "unit_1": "kg",
        "quantity_2": "12 rolls",
        "unit_2": "",
        "product_form": "sleeve",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "notes": "Print notes",
        "extrusion_flag": "da",
        "extrusion_folding": "C",
        "extrusion_next_operation": "cutting",
        "extrusion_treatment": "corona",
        "raw_material_a": "LDPE A | 50%",
        "raw_material_b": "LLDPE B | 30%",
        "raw_material_c": "Masterbatch MB C | 5%",
        "linear_pe": "LLDPE Linear PE | 10%",
        "antistatic": "Antistatic Agent | 1%",
        "masterbatch": "Masterbatch Additive | 2%",
        "chalk": "Filler Chalk | 2%",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def import_card(order_number: str, **overrides: str) -> int:
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


def make_completed_printable_card(
    order_number: str = "27000",
    roll_count: int = 1,
) -> int:
    card_id = import_card(order_number)
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE cards
            SET status = ?,
                machine_id = 1,
                machine_sequence = 1,
                tare_weight = 1.25,
                first_started_at = '2026-06-18 08:05:00',
                finished_at = '2026-06-18 10:45:00'
            WHERE id = ?
            """,
            (STATUS_COMPLETED, card_id),
        )
        connection.execute(
            """
            INSERT INTO production_time_segments (
                card_id, started_at, ended_at, end_reason
            )
            VALUES (?, '2026-06-18 08:05:00', '2026-06-18 09:20:00', 'pause')
            """,
            (card_id,),
        )
        connection.execute(
            """
            INSERT INTO production_time_segments (
                card_id, started_at, ended_at, end_reason
            )
            VALUES (?, '2026-06-18 09:35:00', '2026-06-18 10:45:00', 'finish')
            """,
            (card_id,),
        )
        for roll_number in range(1, roll_count + 1):
            gross_weight = "51.25" if roll_number == 1 else "10.00"
            net_weight = "50.00" if roll_number == 1 else "8.75"
            connection.execute(
                """
                INSERT INTO roll_entries (
                    card_id, order_number, roll_number, gross_weight, net_weight
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (card_id, order_number, roll_number, gross_weight, net_weight),
            )
        connection.commit()
    return card_id


def set_card_status(card_id: int, status: str) -> None:
    with db.connect() as connection:
        connection.execute(
            "UPDATE cards SET status = ? WHERE id = ?",
            (status, card_id),
        )
        connection.commit()


def set_roll_gross_weight(card_id: int, roll_number: int, gross_weight: str) -> None:
    with db.connect() as connection:
        tare_weight = connection.execute(
            "SELECT tare_weight FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()["tare_weight"]
        net_weight = db.net_weight_for_gross(
            db.decimal_from_database(gross_weight),
            db.decimal_from_database(tare_weight),
        )
        connection.execute(
            """
            UPDATE roll_entries
            SET gross_weight = ?,
                net_weight = ?
            WHERE card_id = ?
              AND roll_number = ?
            """,
            (
                gross_weight,
                db.decimal_to_storage(net_weight) if net_weight is not None else None,
                card_id,
                roll_number,
            ),
        )
        connection.commit()


def card_version(card_id: int) -> int:
    return int(db.fetch_admin_card_detail(card_id)["version"])


def set_recipe_actual_entries(
    card_id: int,
    entries: dict[str, dict[str, str]],
) -> None:
    result = db.update_terminal_recipe_actual_entries(
        card_id,
        card_version(card_id),
        entries,
    )
    assert result.ok


def test_completed_card_with_required_production_data_is_printable(connection):
    card_id = make_completed_printable_card()

    result = build_print_readiness(card_id)

    assert result.ok
    assert result.messages == []
    assert result.data is not None
    assert result.data["front"]["order_number"] == "27000"
    assert result.data["front"]["quantity_1"] == "500.555"
    assert result.data["front"]["quantity_2"] == "12 rolls"
    assert result.data["back"]["start_display"] == "18.06.2026 08:05"
    assert result.data["back"]["stop_display"] == "18.06.2026 10:45"
    assert result.data["back"]["duration_display"] == "2 ч 25 мин"
    assert result.data["back"]["tare_display"] == "1.3"
    assert result.data["back"]["total_gross_display"] == "51.3"
    assert result.data["back"]["total_net_display"] == "50.0"
    assert len(result.data["roll_slots"]) == 120
    assert result.data["roll_slots"][0] == {
        "roll_number": 1,
        "gross_display": "51.3",
        "date_shift_display": "",
    }
    assert result.data["roll_slots"][119] == {
        "roll_number": 120,
        "gross_display": "",
        "date_shift_display": "",
    }


def test_archived_card_with_required_production_data_is_printable(connection):
    card_id = make_completed_printable_card("27035")
    set_card_status(card_id, STATUS_ARCHIVED)

    result = build_print_readiness(card_id)

    assert result.ok
    assert result.data is not None


@pytest.mark.parametrize(
    "status",
    [
        STATUS_PENDING,
        STATUS_RUNNING,
        STATUS_PAUSED,
        STATUS_IMPORTED,
        STATUS_CANCELLED,
    ],
)
def test_only_produced_or_archived_cards_are_printable(connection, status):
    card_id = make_completed_printable_card(f"27001-{status}")
    set_card_status(card_id, status)

    result = build_print_readiness(card_id)

    assert not result.ok
    assert result.data is None
    assert "Печатът е разрешен само за произведени или завършени карти." in result.messages


def test_completed_card_with_missing_tare_is_blocked(connection):
    card_id = make_completed_printable_card("27002")
    with db.connect() as connection:
        connection.execute("UPDATE cards SET tare_weight = NULL WHERE id = ?", (card_id,))
        connection.commit()

    result = build_print_readiness(card_id)

    assert not result.ok
    assert result.data is None
    assert "Шпула е задължителна преди печат." in result.messages


def test_incomplete_print_readiness_does_not_show_numeric_corruption_message(connection):
    card_id = make_completed_printable_card("27060")
    with db.connect() as connection:
        connection.execute(
            "UPDATE cards SET tare_weight = NULL WHERE id = ?",
            (card_id,),
        )
        connection.execute(
            "DELETE FROM roll_entries WHERE card_id = ?",
            (card_id,),
        )
        connection.commit()

    result = build_print_readiness(card_id)

    assert not result.ok
    assert result.data is None
    assert "Шпула е задължителна преди печат." in result.messages
    assert "Поне едно бруто тегло на ролка е задължително преди печат." in result.messages
    assert "Критичните тегла за печат трябва да са валидни числа." not in result.messages


def test_completed_card_with_no_rolls_is_blocked(connection):
    card_id = make_completed_printable_card("27003")
    with db.connect() as connection:
        connection.execute("DELETE FROM roll_entries WHERE card_id = ?", (card_id,))
        connection.commit()

    result = build_print_readiness(card_id)

    assert not result.ok
    assert result.data is None
    assert "Поне едно бруто тегло на ролка е задължително преди печат." in result.messages


def test_completed_card_with_no_timing_is_blocked(connection):
    card_id = make_completed_printable_card("27004")
    with db.connect() as connection:
        connection.execute(
            "DELETE FROM production_time_segments WHERE card_id = ?",
            (card_id,),
        )
        connection.execute(
            "UPDATE cards SET first_started_at = NULL WHERE id = ?",
            (card_id,),
        )
        connection.commit()

    result = build_print_readiness(card_id)

    assert not result.ok
    assert result.data is None
    assert "Времето трябва да бъде стартирано преди печат." in result.messages


def test_completed_card_with_more_than_120_rolls_is_blocked(connection):
    card_id = make_completed_printable_card("27005", roll_count=121)

    result = build_print_readiness(card_id)

    assert not result.ok
    assert result.data is None
    assert "Печатът поддържа най-много 120 ролки." in result.messages


def test_completed_card_with_invalid_numeric_weight_is_blocked(connection):
    card_id = make_completed_printable_card("27006")
    with db.connect() as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE cards SET tare_weight = 'Infinity' WHERE id = ?",
            (card_id,),
        )
        connection.commit()

    result = build_print_readiness(card_id)

    assert not result.ok
    assert result.data is None
    assert "Критичните тегла за печат трябва да са валидни числа." in result.messages


def test_completed_card_with_negative_net_total_is_blocked(connection):
    card_id = make_completed_printable_card("27007")
    with db.connect() as connection:
        connection.execute(
            "UPDATE cards SET tare_weight = 100 WHERE id = ?",
            (card_id,),
        )
        connection.commit()

    result = build_print_readiness(card_id)

    assert not result.ok
    assert result.data is None
    assert "Нето теглото за печат не може да бъде отрицателно." in result.messages


def test_print_formatting_helpers():
    assert format_datetime("2026-06-18 14:35:29") == "18.06.2026 14:35"
    assert format_duration(27000) == "7 ч 30 мин"
    assert format_weight("51.25") == "51.3"
    assert format_weight("150") == "150.0"
    assert format_weight("NaN") == ""
    assert format_weight("Infinity") == ""


@dataclass(frozen=True)
class RouteResponse:
    status_code: int
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")


async def request_app(path: str, query_string: bytes = b"") -> RouteResponse:
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": query_string,
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
            "app": app,
        },
        receive,
        send,
    )

    status_code = next(
        message["status"]
        for message in messages
        if message["type"] == "http.response.start"
    )
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return RouteResponse(status_code=status_code, body=body)


def get_print_page(card_id: int, auto: bool = False) -> RouteResponse:
    query = "?auto=1" if auto else ""
    return asyncio.run(
        request_app(
            f"/cards/{card_id}/print",
            query_string=query.removeprefix("?").encode("utf-8"),
        )
    )


def data_block(html: str, attribute: str, value: str) -> str:
    pattern = re.compile(
        rf"<(?P<tag>[a-z0-9]+)\b[^>]*\b{attribute}=\"{re.escape(value)}\"[^>]*>"
        rf"(?P<body>.*?)</(?P=tag)>",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(html)
    assert match is not None, f"Missing block with {attribute}={value}"
    return match.group("body")


def back_roll_groups(html: str) -> list[str]:
    return re.findall(
        r"<table\b[^>]*\bdata-roll-group=\"\d+-\d+\"[^>]*>.*?</table>",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )


def print_page_sections(html: str) -> list[str]:
    return re.findall(
        r"<section\b(?=[^>]*\bclass=\"[^\"]*\bprint-page\b)[^>]*>.*?</section>",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )


def roll_row(html: str, roll_number: int) -> str:
    return data_block(html, "data-roll-number", str(roll_number))


def direct_td_count(fragment: str) -> int:
    return len(re.findall(r"<td\b", fragment, flags=re.IGNORECASE))


def rendered_text(fragment: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", fragment)
    return unescape(without_tags).strip()


def page_title(html: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html, flags=re.DOTALL | re.IGNORECASE)
    assert match is not None
    return rendered_text(match.group(1))


def test_print_route_completed_printable_card_returns_200(connection):
    card_id = make_completed_printable_card("27008")

    response = get_print_page(card_id)

    assert response.status_code == 200
    assert "ПОРЪЧКА №" in response.text
    assert "27008" in response.text


def test_print_route_non_completed_card_returns_blocked_response(connection):
    card_id = make_completed_printable_card("27009")
    set_card_status(card_id, STATUS_RUNNING)

    response = get_print_page(card_id)

    assert response.status_code == 200
    assert "Печатът е блокиран" in response.text
    assert "Печатът е разрешен само за произведени или завършени карти." in response.text


def test_print_route_terminal_blocked_response_does_not_link_to_admin(connection):
    card_id = make_completed_printable_card("27025")
    set_card_status(card_id, STATUS_RUNNING)

    response = asyncio.run(
        request_app(
            f"/cards/{card_id}/print",
            query_string=b"auto=1&source=terminal",
        )
    )

    assert response.status_code == 200
    assert "Печатът е блокиран" in response.text
    assert f"/admin/cards/{card_id}" not in response.text
    assert 'href="/terminal"' in response.text


def test_print_route_card_with_more_than_120_rolls_returns_blocked_response(connection):
    card_id = make_completed_printable_card("27010", roll_count=121)

    response = get_print_page(card_id)

    assert response.status_code == 200
    assert "Печатът е блокиран" in response.text
    assert "Печатът поддържа най-много 120 ролки." in response.text


def test_print_route_rendered_page_contains_exactly_two_print_page_containers(
    connection,
):
    card_id = make_completed_printable_card("27011")

    response = get_print_page(card_id)

    assert response.status_code == 200
    pages = print_page_sections(response.text)
    assert len(pages) == 2
    assert any('class="print-page print-page-front"' in page for page in pages)
    assert any('class="print-page print-page-back"' in page for page in pages)


def test_print_route_rendered_page_includes_front_and_back_template_labels(
    connection,
):
    card_id = make_completed_printable_card("27012")

    response = get_print_page(card_id)

    assert response.status_code == 200
    assert "ВИД ЗАГОТОВКА" in response.text
    assert "Дата / смяна" in response.text
    assert "Старт производство" in response.text


def test_print_route_front_page_preserves_fixed_header_and_quantity_cells(
    connection,
):
    card_id = make_completed_printable_card("27028")

    response = get_print_page(card_id)

    assert response.status_code == 200
    expected_cells = {
        "order-number": "27028",
        "order-date": "18.06.2026",
        "delivery-date": "25.06.2026",
        "customer": "Print Customer",
        "city": "Sofia",
        "product-type": "PE film",
        "quantity-1": "500.555",
        "unit-1": "kg",
        "quantity-2": "12 rolls",
        "unit-2": "",
        "quantity-empty": "",
    }
    for cell_name, expected_value in expected_cells.items():
        cell = data_block(response.text, "data-front-template-cell", cell_name)
        assert rendered_text(cell) == expected_value


def test_print_route_front_page_preserves_requested_product_grid_cells(connection):
    card_id = make_completed_printable_card("27029")

    response = get_print_page(card_id)

    assert response.status_code == 200
    expected_cells = {
        "product-form": "sleeve",
        "material": "LDPE",
        "size-thickness": "600/0.050",
        "extrusion-folding": "C",
        "extrusion-next-operation": "cutting",
        "extrusion-treatment": "corona",
    }
    for cell_name, expected_value in expected_cells.items():
        cell = data_block(response.text, "data-front-template-cell", cell_name)
        assert rendered_text(cell) == expected_value


def test_print_route_front_page_preserves_planned_material_abc_grid(connection):
    card_id = make_completed_printable_card("27030")

    response = get_print_page(card_id)

    assert response.status_code == 200
    expected_values = {
        ("raw_material_a", "A"): "LDPE A | 50%",
        ("raw_material_b", "B"): "LLDPE B | 30%",
        ("raw_material_c", "C"): "Masterbatch MB C | 5%",
        ("linear_pe", "A"): "LLDPE Linear PE | 10%",
        ("linear_pe", "B"): "",
        ("linear_pe", "C"): "",
        ("antistatic", "A"): "Antistatic Agent | 1%",
        ("masterbatch", "A"): "Masterbatch Additive | 2%",
        ("chalk", "A"): "Filler Chalk | 2%",
    }
    for (component_key, column_name), expected_value in expected_values.items():
        cell = data_block(
            response.text,
            "data-front-planned-cell",
            f"{component_key}-{column_name}",
        )
        assert rendered_text(cell) == expected_value


def test_print_route_front_page_preserves_actual_material_quantity_brand_batch_grid(
    connection,
):
    card_id = make_completed_printable_card("27031")
    set_recipe_actual_entries(
        card_id,
        {
            "raw_material_a": {
                "actual_material_used": "Actual LDPE A",
                "batch_lot": "LOT-A",
            },
            "raw_material_b": {
                "actual_material_used": "Actual LLDPE B",
                "batch_lot": "LOT-B",
            },
        },
    )

    response = get_print_page(card_id)

    assert response.status_code == 200
    expected_values = {
        "raw_material_a-quantity": "A",
        "raw_material_a-brand": "Actual LDPE A",
        "raw_material_a-batch": "LOT-A",
        "raw_material_b-quantity": "B",
        "raw_material_b-brand": "Actual LLDPE B",
        "raw_material_b-batch": "LOT-B",
        "raw_material_c-quantity": "C",
        "raw_material_c-brand": "",
        "raw_material_c-batch": "",
        "linear_pe-quantity": "",
        "linear_pe-brand": "",
        "linear_pe-batch": "",
    }
    for cell_name, expected_value in expected_values.items():
        cell = data_block(response.text, "data-front-actual-cell", cell_name)
        assert rendered_text(cell) == expected_value


def test_print_route_front_page_actual_material_table_has_fixed_columns(connection):
    card_id = make_completed_printable_card("27032")

    response = get_print_page(card_id)

    assert response.status_code == 200
    actual_table_match = re.search(
        r"<table\b[^>]*\bclass=\"front-actual-table\"[^>]*>.*?</table>",
        response.text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert actual_table_match is not None
    assert re.findall(
        r"<col\b[^>]*\bclass=\"([^\"]+)\"",
        actual_table_match.group(0),
        flags=re.IGNORECASE,
    ) == [
        "front-actual-quantity-label-col",
        "front-actual-quantity-value-col",
        "front-actual-brand-col",
        "front-actual-batch-col",
    ]


def test_print_route_front_page_renders_planned_recipe_values(connection):
    card_id = make_completed_printable_card("27020")

    response = get_print_page(card_id)

    assert response.status_code == 200
    expected_values = {
        "raw_material_a": "LDPE A | 50%",
        "raw_material_b": "LLDPE B | 30%",
        "raw_material_c": "Masterbatch MB C | 5%",
        "linear_pe": "LLDPE Linear PE | 10%",
        "antistatic": "Antistatic Agent | 1%",
        "masterbatch": "Masterbatch Additive | 2%",
        "chalk": "Filler Chalk | 2%",
    }
    for component_key, expected_value in expected_values.items():
        planned_cell = data_block(response.text, "data-front-recipe-planned", component_key)
        assert rendered_text(planned_cell) == expected_value


def test_print_route_front_page_renders_actual_material_and_batch_values(
    connection,
):
    card_id = make_completed_printable_card("27021")
    set_recipe_actual_entries(
        card_id,
        {
            "raw_material_a": {
                "actual_material_used": "Actual LDPE A",
                "batch_lot": "LOT-A",
            },
            "raw_material_b": {
                "actual_material_used": "Actual LLDPE B",
                "batch_lot": "LOT-B",
            },
            "masterbatch": {
                "actual_material_used": "Actual MB",
                "batch_lot": "LOT-MB",
            },
        },
    )

    response = get_print_page(card_id)

    assert response.status_code == 200
    expected_values = {
        "raw_material_a": ("Actual LDPE A", "LOT-A"),
        "raw_material_b": ("Actual LLDPE B", "LOT-B"),
        "masterbatch": ("Actual MB", "LOT-MB"),
    }
    for component_key, (expected_actual, expected_batch) in expected_values.items():
        actual_cell = data_block(response.text, "data-front-recipe-actual", component_key)
        batch_cell = data_block(response.text, "data-front-recipe-batch", component_key)
        assert rendered_text(actual_cell) == expected_actual
        assert rendered_text(batch_cell) == expected_batch


def test_print_route_front_page_blank_actual_recipe_fields_stay_blank(connection):
    card_id = make_completed_printable_card("27022")
    set_recipe_actual_entries(
        card_id,
        {
            "raw_material_a": {
                "actual_material_used": "Actual LDPE A",
                "batch_lot": "LOT-A",
            },
        },
    )

    response = get_print_page(card_id)

    assert response.status_code == 200
    for component_key in ("raw_material_c", "chalk"):
        actual_cell = data_block(response.text, "data-front-recipe-actual", component_key)
        batch_cell = data_block(response.text, "data-front-recipe-batch", component_key)
        assert rendered_text(actual_cell) == ""
        assert rendered_text(batch_cell) == ""


def test_print_route_excludes_app_only_planning_fields(connection):
    card_id = make_completed_printable_card("27023")
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE cards
            SET machine_id = 4,
                machine_sequence = 9,
                max_roll_weight = '77.77'
            WHERE id = ?
            """,
            (card_id,),
        )
        connection.commit()

    response = get_print_page(card_id)

    assert response.status_code == 200
    text = rendered_text(response.text)
    assert "77.77" not in text
    assert "max_roll_weight" not in response.text
    assert "machine_id" not in response.text
    assert "machine_sequence" not in response.text
    assert "Машина" not in text
    assert "ред 9" not in text


def test_print_route_front_page_renders_legacy_sections_as_blank_fields(connection):
    card_id = make_completed_printable_card("27027")

    response = get_print_page(card_id)

    assert response.status_code == 200
    expected_sections = {
        "front-legacy-spools": "ШПУЛИ",
        "front-legacy-waste": "БРАК",
        "front-legacy-foil": "ФОЛИО [kg]",
    }
    for class_name, label in expected_sections.items():
        section = data_block(response.text, "data-front-legacy-section", class_name)
        assert label in rendered_text(section)
        assert rendered_text(data_block(section, "data-front-legacy-value", class_name)) == ""


def test_print_route_title_uses_order_number_not_internal_card_id(connection):
    card_id = make_completed_printable_card("27024")

    response = get_print_page(card_id)

    assert response.status_code == 200
    assert page_title(response.text) == "Печат поръчка 27024"
    assert f"Печат карта {card_id}" not in response.text


def test_print_route_renders_gross_only_roll_values_without_per_roll_net_values(
    connection,
):
    card_id = make_completed_printable_card("27013", roll_count=2)

    response = get_print_page(card_id)

    assert response.status_code == 200
    roll_1 = roll_row(response.text, 1)
    roll_2 = roll_row(response.text, 2)
    assert direct_td_count(roll_1) == 3
    assert direct_td_count(roll_2) == 3
    assert rendered_text(data_block(roll_1, "data-roll-gross", "1")) == "51.3"
    assert rendered_text(data_block(roll_2, "data-roll-gross", "2")) == "10.0"
    assert "50.0" not in rendered_text(roll_1)
    assert "8.8" not in rendered_text(roll_2)


def test_print_route_back_page_renders_three_roll_groups_with_120_numbers(connection):
    card_id = make_completed_printable_card("27015", roll_count=2)

    response = get_print_page(card_id)

    assert response.status_code == 200
    groups = back_roll_groups(response.text)
    assert len(groups) == 3
    assert 'data-roll-group="1-40"' in groups[0]
    assert 'data-roll-group="41-80"' in groups[1]
    assert 'data-roll-group="81-120"' in groups[2]
    for roll_number in range(1, 121):
        assert f'data-roll-number="{roll_number}"' in response.text


def test_print_route_back_page_header_uses_label_and_value_rows(connection):
    card_id = make_completed_printable_card("27033")

    response = get_print_page(card_id)

    assert response.status_code == 200
    header = data_block(response.text, "data-print-back-header", "order")
    assert header.count("<tr") == 2
    for field_name, expected_value in {
        "order": "27033",
        "customer": "Print Customer",
        "product": "PE film",
    }.items():
        assert rendered_text(data_block(header, "data-back-header-value", field_name)) == expected_value


def test_print_route_back_page_renders_blank_total_row_for_each_roll_group(connection):
    card_id = make_completed_printable_card("27026", roll_count=2)

    response = get_print_page(card_id)

    assert response.status_code == 200
    for group in ("1-40", "41-80", "81-120"):
        total_row = data_block(response.text, "data-roll-group-total", group)
        assert "Общо" in rendered_text(total_row)
        assert rendered_text(data_block(total_row, "data-roll-group-total-value", group)) == ""


def test_print_route_back_page_roll_slots_after_produced_count_are_blank(
    connection,
):
    card_id = make_completed_printable_card("27016", roll_count=2)

    response = get_print_page(card_id)

    assert response.status_code == 200
    roll_3 = data_block(response.text, "data-roll-number", "3")
    assert 'data-roll-date-shift="3"' in roll_3
    assert 'data-roll-gross="3"' in roll_3
    assert rendered_text(data_block(roll_3, "data-roll-date-shift", "3")) == ""
    assert rendered_text(data_block(roll_3, "data-roll-gross", "3")) == ""


def test_print_route_back_page_roll_gross_values_use_one_decimal(connection):
    card_id = make_completed_printable_card("27017", roll_count=81)
    boundary_weights = {
        40: "40.25",
        41: "41.25",
        80: "80.25",
        81: "81.25",
    }
    for roll_number, gross_weight in boundary_weights.items():
        set_roll_gross_weight(card_id, roll_number, gross_weight)

    response = get_print_page(card_id)

    assert response.status_code == 200
    roll_1 = roll_row(response.text, 1)
    roll_2 = roll_row(response.text, 2)
    assert rendered_text(data_block(roll_1, "data-roll-gross", "1")) == "51.3"
    assert rendered_text(data_block(roll_2, "data-roll-gross", "2")) == "10.0"
    for roll_number, expected in {
        40: "40.3",
        41: "41.3",
        80: "80.3",
        81: "81.3",
    }.items():
        row = roll_row(response.text, roll_number)
        assert rendered_text(data_block(row, "data-roll-gross", str(roll_number))) == expected


def test_print_route_back_page_summary_weights_use_one_decimal(connection):
    card_id = make_completed_printable_card("27018", roll_count=2)

    response = get_print_page(card_id)

    assert response.status_code == 200
    assert rendered_text(data_block(response.text, "data-summary-field", "tare")) == "1.3"
    assert rendered_text(data_block(response.text, "data-summary-field", "total-gross")) == "61.3"
    assert rendered_text(data_block(response.text, "data-summary-field", "total-net")) == "58.8"


def test_print_route_back_page_date_shift_cells_are_blank(connection):
    card_id = make_completed_printable_card("27019", roll_count=2)

    response = get_print_page(card_id)

    assert response.status_code == 200
    for roll_number in (1, 2, 40, 41, 80, 81, 120):
        cell = data_block(response.text, "data-roll-date-shift", str(roll_number))
        assert rendered_text(cell) == ""


def test_print_css_centers_roll_gross_and_reduces_date_shift_width():
    css = PRINT_CSS_PATH.read_text(encoding="utf-8")

    assert re.search(
        r"\.roll-date-heading,\s*\.roll-date-shift\s*\{[^}]*width:\s*13mm;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.roll-grid td\.roll-gross\s*\{[^}]*text-align:\s*center;",
        css,
        flags=re.DOTALL,
    )


def test_print_css_front_page_uses_measured_dense_recipe_layout():
    css = PRINT_CSS_PATH.read_text(encoding="utf-8")

    assert re.search(
        r"\.print-page-front\s*\{[^}]*padding:\s*12mm\s+13mm\s+7mm;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.front-card-frame\s*\{[^}]*grid-template-rows:\s*12mm\s+22mm\s+9mm\s+9mm\s+9mm\s+27mm\s+96mm\s+47mm;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.front-card-frame\s*\{[^}]*row-gap:\s*3mm;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.front-request-treatment-col\s*\{[^}]*width:\s*14\.5%;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.front-actual-quantity-label-col\s*\{[^}]*width:\s*14%;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.front-actual-quantity-value-col\s*\{[^}]*width:\s*7%;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.front-actual-brand-col\s*\{[^}]*width:\s*41%;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.front-actual-batch-col\s*\{[^}]*width:\s*38%;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.front-bottom-grid\s*\{[^}]*grid-template-columns:\s*58%\s+42%;",
        css,
        flags=re.DOTALL,
    )


def test_print_css_front_page_uses_reference_weight_borders():
    css = PRINT_CSS_PATH.read_text(encoding="utf-8")

    assert re.search(
        r"\.front-section-title\s*\{[^}]*border:\s*1\.5px\s+solid\s+#111;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.front-template-table,\s*\.front-planned-table,\s*\.front-actual-table\s*\{[^}]*border:\s*1\.5px\s+solid\s+#111;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.front-template-table th,[^}]*\.front-actual-table td\s*\{[^}]*border:\s*1px\s+solid\s+#111;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.front-recipe-panel\s*\{[^}]*border:\s*1\.5px\s+solid\s+#111;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.front-planned-table\s*\{[^}]*border-right:\s*1\.5px\s+solid\s+#111;",
        css,
        flags=re.DOTALL,
    )


def test_print_route_back_page_summary_fields_render_in_two_side_by_side_tables(connection):
    card_id = make_completed_printable_card("27034")

    response = get_print_page(card_id)

    assert response.status_code == 200
    timing_table = data_block(response.text, "data-summary-table", "timing")
    weights_table = data_block(response.text, "data-summary-table", "weights")
    assert timing_table.count("<tr") == 3
    assert weights_table.count("<tr") == 3
    for field_name in ("start", "stop", "duration", "tare", "total-gross", "total-net"):
        assert f'data-summary-field="{field_name}"' in response.text


def test_print_route_auto_mode_calls_window_print(connection):
    card_id = make_completed_printable_card("27014")

    preview_response = get_print_page(card_id)
    auto_response = get_print_page(card_id, auto=True)

    assert preview_response.status_code == 200
    assert auto_response.status_code == 200
    assert "window.print()" not in preview_response.text
    assert "window.print()" in auto_response.text
