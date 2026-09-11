from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .presentation import next_operation_display

from . import db
from .constants import PRINTABLE_STATUSES
from .pallet_summary import (
    PalletSummaryDataError,
    build_pallet_summary,
)
from .recipe_parser import parse_recipe_cell
from .timekeeping import StoredTimestampError, format_print_datetime, parse_stored_utc

MAX_PRINT_ROLLS = 120
PALLET_BACK_TABLE_CAPACITY = 8
# Retain the public name used by the older roll/pallet verification fixture.
# The value still means total body-row slots; Task 7 no longer treats it as
# capacity for each of two visual columns.
PALLET_BACK_COLUMN_CAPACITY = PALLET_BACK_TABLE_CAPACITY
PALLET_OVERFLOW_PAGE_CAPACITY = 47


@dataclass(frozen=True)
class PrintReadiness:
    ok: bool
    messages: list[str]
    data: dict[str, Any] | None = None


def build_print_readiness(card_id: int) -> PrintReadiness:
    try:
        card = db.fetch_admin_card_detail(card_id)
    except InvalidOperation:
        return PrintReadiness(
            False,
            ["Критичните тегла за печат трябва да са валидни числа."],
            None,
        )
    if card is None:
        return PrintReadiness(False, ["Картата не е намерена."], None)

    messages = validate_print_readiness(card)
    if messages:
        return PrintReadiness(False, messages, None)

    try:
        print_data = assemble_print_data(card)
    except PalletSummaryDataError:
        return PrintReadiness(False, [db.PALLET_SUMMARY_REPAIR_MESSAGE], None)
    return PrintReadiness(True, [], print_data)


def validate_print_readiness(card: dict[str, Any]) -> list[str]:
    messages: list[str] = []

    if card["status"] not in PRINTABLE_STATUSES:
        messages.append("Печатът е разрешен само за произведени или завършени карти.")
    if card.get("cancelled_at"):
        messages.append("Анулирани карти не могат да се печатат.")
    if not card.get("first_started_at"):
        messages.append("Началният час на производство е задължителен преди печат.")
    if not card.get("finished_at"):
        messages.append("Крайният час на производство е задължителен преди печат.")
    for field, invalid_message in (
        (
            "first_started_at",
            "Началният час на производство е невалиден и печатът е блокиран.",
        ),
        (
            "finished_at",
            "Крайният час на производство е невалиден и печатът е блокиран.",
        ),
    ):
        if not card.get(field):
            continue
        try:
            parse_stored_utc(card[field], required=True)
        except StoredTimestampError:
            messages.append(invalid_message)

    timing_segments = card.get("timing_segments") or []
    if not timing_segments:
        messages.append("Времето трябва да бъде стартирано преди печат.")
    elif any(segment.get("ended_at") is None for segment in timing_segments):
        messages.append("Всички времеви сегменти трябва да са затворени преди печат.")
    for segment in timing_segments:
        try:
            parse_stored_utc(segment.get("started_at"), required=True)
            if segment.get("ended_at") is not None:
                parse_stored_utc(segment.get("ended_at"), required=True)
        except StoredTimestampError:
            messages.append(
                "Времевият регистър съдържа невалиден начален или краен час "
                "и печатът е блокиран."
            )
            break

    gross_rolls = gross_roll_entries(card)
    if not gross_rolls:
        messages.append("Поне едно бруто тегло на ролка е задължително преди печат.")
    elif len(gross_rolls) > MAX_PRINT_ROLLS or any(
        int(roll["roll_number"]) > MAX_PRINT_ROLLS for roll in gross_rolls
    ):
        messages.append("Печатът поддържа най-много 120 ролки.")

    if gross_rolls:
        weight_messages = validate_print_weight_values(card, gross_rolls)
        messages.extend(weight_messages)
        if not weight_messages:
            try:
                pallet_summary = build_pallet_summary(
                    card.get("roll_entries", ()),
                    card.get("pallet_weights", {}),
                )
            except PalletSummaryDataError:
                messages.append(db.PALLET_SUMMARY_REPAIR_MESSAGE)
            else:
                if pallet_summary["weight_state"] == "partial":
                    messages.extend(
                        db.pallet_weight_completion_messages(pallet_summary)
                    )

    if int(card.get("total_production_seconds") or 0) < 0:
        messages.append("Времето за изработка не може да бъде изчислено за печат.")

    return messages


def validate_print_weight_values(
    card: dict[str, Any],
    gross_rolls: list[dict[str, Any]],
) -> list[str]:
    if any(
        roll.get("tare_weight") is None or roll.get("net_weight") is None
        for roll in gross_rolls
    ):
        return ["Всяка ролка с бруто тегло трябва да има шпула преди печат."]

    total_gross = decimal_from_value(card.get("total_gross_weight"))
    total_net = decimal_from_value(card.get("total_net_weight"))
    gross_values = [decimal_from_value(roll.get("gross_weight")) for roll in gross_rolls]
    tare_values = [decimal_from_value(roll.get("tare_weight")) for roll in gross_rolls]
    net_values = [decimal_from_value(roll.get("net_weight")) for roll in gross_rolls]

    if any(net is not None and net < 0 for net in net_values):
        return ["Нето теглото за печат не може да бъде отрицателно."]

    values = [total_gross, total_net, *gross_values, *tare_values, *net_values]
    if any(value is None for value in values):
        return ["Критичните тегла за печат трябва да са валидни числа."]

    if total_net is not None and total_net < 0:
        return ["Нето теглото за печат не може да бъде отрицателно."]

    return []


def assemble_print_data(card: dict[str, Any]) -> dict[str, Any]:
    gross_rolls = gross_roll_entries(card)
    recipe_actual_entries = card.get("recipe_actual_entries") or {}
    shared_pallet_summary = build_pallet_summary(
        card.get("roll_entries", ()),
        card.get("pallet_weights", {}),
    )
    pallet_summary = build_print_pallet_summary(shared_pallet_summary)

    front = {
        "order_number": text_value(card.get("order_number")),
        "order_date": text_value(card.get("order_date")),
        "delivery_date": text_value(card.get("delivery_date")),
        "customer": text_value(card.get("customer")),
        "city": text_value(card.get("city")),
        "product_type": text_value(card.get("product_type")),
        "ordered_gross_display": format_ordered_amount(
            card.get("ordered_gross_kg"),
            "кг",
        ),
        "ordered_rolls_display": format_ordered_amount(
            card.get("ordered_rolls"),
            "ролки",
        ),
        "ordered_meters_display": format_ordered_amount(
            card.get("ordered_meters"),
            "метра",
        ),
        "ordered_units_display": format_ordered_amount(
            card.get("ordered_units"),
            "бр.",
        ),
        "product_form": text_value(card.get("product_form")),
        "material": text_value(card.get("material")),
        "size_thickness": text_value(card.get("size_thickness")),
        "extrusion_folding": text_value(card.get("extrusion_folding")),
        "extrusion_next_operation": next_operation_display(
            card.get("extrusion_next_operation")
        ),
        "extrusion_treatment": text_value(card.get("extrusion_treatment")),
        "notes": text_value(card.get("notes")),
        "packaging_method": text_value(card.get("packaging_method")),
        "recipe_rows": build_recipe_rows(card, recipe_actual_entries),
    }
    back = {
        "order_number": text_value(card.get("order_number")),
        "customer": text_value(card.get("customer")),
        "product_type": text_value(card.get("product_type")),
        "start_display": format_print_datetime(card.get("first_started_at")),
        "stop_display": format_print_datetime(card.get("finished_at")),
        "duration_display": format_duration(
            int(card.get("total_production_seconds") or 0)
        ),
        "tare_display": tare_summary_display(card),
        "total_gross_display": format_weight(card.get("total_gross_weight")),
        "total_net_display": format_weight(card.get("total_net_weight")),
    }

    return {
        "card_id": card["id"],
        "front": front,
        "back": back,
        "roll_slots": build_roll_slots(gross_rolls),
        "pallet_summary": pallet_summary,
        "pallet_summary_layout": split_pallet_summary(
            pallet_summary["rows"] if pallet_summary is not None else [],
            pallet_summary["total"] if pallet_summary is not None else None,
            back_table_capacity=PALLET_BACK_TABLE_CAPACITY,
            overflow_page_capacity=PALLET_OVERFLOW_PAGE_CAPACITY,
        ),
    }


def build_recipe_rows(
    card: dict[str, Any],
    recipe_actual_entries: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    row_specs = (
        ("raw_material_a", "A", "raw_material_a"),
        ("raw_material_b", "B", "raw_material_b"),
        ("raw_material_c", "C", "raw_material_c"),
        ("linear_pe", "Линеен PE", "linear_pe"),
        ("antistatic", "Антистатик", "antistatic"),
        ("masterbatch", "Мастербач", "masterbatch"),
        ("chalk", "Креда", "chalk"),
    )
    rows: list[dict[str, str]] = []
    for component_key, label, card_field in row_specs:
        actual_entry = recipe_actual_entries.get(component_key) or {}
        rows.append(
            {
                "component_key": component_key,
                "label": label,
                "planned_material": planned_recipe_display(
                    component_key,
                    card.get(card_field),
                ),
                "actual_material_used": text_value(
                    actual_entry.get("actual_material_used")
                ),
                "batch_lot": text_value(actual_entry.get("batch_lot")),
            }
        )

    if rows and not rows[0]["actual_material_used"]:
        rows[0]["actual_material_used"] = text_value(
            card.get("actual_raw_material_used")
            or card.get("raw_material_brand_grade")
        )
    if rows and not rows[0]["batch_lot"]:
        rows[0]["batch_lot"] = text_value(card.get("raw_material_batch_lot"))

    return rows


def planned_recipe_display(component_key: str, source_text: Any) -> str:
    raw_source_text = text_value(source_text)
    component, errors = parse_recipe_cell(component_key, raw_source_text)
    if component is None or errors:
        return raw_source_text
    return (
        f"{component.planned_material} "
        f"{format_recipe_percent(component.recipe_percent)}%"
    )


def format_recipe_percent(value: Decimal) -> str:
    return format(value.normalize(), "f")


def build_roll_slots(gross_rolls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gross_by_roll_number = {
        int(roll["roll_number"]): format_weight(roll.get("gross_weight"))
        for roll in gross_rolls
    }
    return [
        {
            "roll_number": roll_number,
            "gross_display": gross_by_roll_number.get(roll_number, ""),
            "date_shift_display": "",
        }
        for roll_number in range(1, MAX_PRINT_ROLLS + 1)
    ]


def gross_roll_entries(card: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        roll
        for roll in card.get("roll_entries", [])
        if roll.get("gross_weight") is not None
    ]


def build_print_pallet_summary(
    shared_summary: dict[str, Any],
) -> dict[str, Any] | None:
    """Adapt the shared pallet calculation to the operational-card print model."""
    if not shared_summary["used_pallet_numbers"]:
        return None

    def print_row(row: dict[str, Any], *, label: str | None = None) -> dict[str, Any]:
        return {
            "pallet_label": label if label is not None else row["pallet_label"],
            "roll_count": row["roll_count"],
            "gross_without_pallet_display": row["gross_without_pallet_display"],
            "pallet_weight_display": row["pallet_weight_display"],
            "gross_with_pallet_display": row["gross_with_pallet_display"],
            "net_display": row["net_display"],
        }

    return {
        "rows": [print_row(row) for row in shared_summary["rows"]],
        "total": print_row(shared_summary["total"], label="Общо"),
    }


def split_pallet_summary(
    rows: list[dict[str, Any]],
    total: dict[str, Any] | None,
    *,
    back_table_capacity: int,
    overflow_page_capacity: int,
) -> dict[str, Any]:
    if back_table_capacity < 2 or overflow_page_capacity < 2:
        raise ValueError("Pallet summary capacities must be at least two.")
    if not rows:
        return {
            "page2_table": None,
            "overflow_tables": [],
        }
    if total is None:
        raise ValueError("A non-empty pallet summary requires a total row.")
    if len(rows) + 1 <= back_table_capacity:
        return {
            "page2_table": {"rows": list(rows), "total": total},
            "overflow_tables": [],
        }

    items = [("row", row) for row in rows] + [("total", total)]
    pages = [
        items[index : index + overflow_page_capacity]
        for index in range(0, len(items), overflow_page_capacity)
    ]
    if len(pages) > 1 and pages[-1] == [("total", total)]:
        pages[-1].insert(0, pages[-2].pop())
    return {
        "page2_table": None,
        "overflow_tables": [
            {
                "rows": [value for kind, value in page if kind == "row"],
                "total": next(
                    (value for kind, value in page if kind == "total"),
                    None,
                ),
            }
            for page in pages
        ],
    }


def tare_summary_display(card: dict[str, Any]) -> str:
    tare_values = [
        decimal_from_value(roll.get("tare_weight"))
        for roll in gross_roll_entries(card)
        if roll.get("tare_weight") is not None
    ]
    tare_values = [tare for tare in tare_values if tare is not None]
    if not tare_values:
        return format_weight(card.get("tare_weight"))

    lowest = min(tare_values)
    highest = max(tare_values)
    if lowest == highest:
        return format_weight(lowest)
    return f"{format_weight(lowest)}-{format_weight(highest)}"


def format_duration(seconds: int) -> str:
    total_minutes = max(int(seconds), 0) // 60
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours} ч {minutes} мин"


def format_weight(value: Any) -> str:
    decimal_value = decimal_from_value(value)
    if decimal_value is None:
        return ""
    rounded = decimal_value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(rounded, "f")


def format_ordered_amount(value: Any, unit: str) -> str:
    amount = text_value(value)
    if not amount.strip():
        return ""
    return f"{amount} {unit}"


def decimal_from_value(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    if not parsed.is_finite():
        return None
    return parsed


def text_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
