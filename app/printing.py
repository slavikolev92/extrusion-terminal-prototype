from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from . import db
from .constants import STATUS_COMPLETED

MAX_PRINT_ROLLS = 120


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

    return PrintReadiness(True, [], assemble_print_data(card))


def validate_print_readiness(card: dict[str, Any]) -> list[str]:
    messages: list[str] = []

    if card["status"] != STATUS_COMPLETED:
        messages.append("Печатът е разрешен само за завършени карти.")
    if card.get("cancelled_at"):
        messages.append("Анулирани карти не могат да се печатат.")
    if card.get("tare_weight") is None:
        messages.append("Шпула е задължителна преди печат.")
    if not card.get("first_started_at"):
        messages.append("Началният час на производство е задължителен преди печат.")
    if not card.get("finished_at"):
        messages.append("Крайният час на производство е задължителен преди печат.")

    timing_segments = card.get("timing_segments") or []
    if not timing_segments:
        messages.append("Времето трябва да бъде стартирано преди печат.")
    elif any(segment.get("ended_at") is None for segment in timing_segments):
        messages.append("Всички времеви сегменти трябва да са затворени преди печат.")

    gross_rolls = gross_roll_entries(card)
    if not gross_rolls:
        messages.append("Поне едно бруто тегло на ролка е задължително преди печат.")
    elif len(gross_rolls) > MAX_PRINT_ROLLS or any(
        int(roll["roll_number"]) > MAX_PRINT_ROLLS for roll in gross_rolls
    ):
        messages.append("Печатът поддържа най-много 120 ролки.")

    messages.extend(validate_print_weight_values(card, gross_rolls))

    if int(card.get("total_production_seconds") or 0) < 0:
        messages.append("Времето за изработка не може да бъде изчислено за печат.")

    return messages


def validate_print_weight_values(
    card: dict[str, Any],
    gross_rolls: list[dict[str, Any]],
) -> list[str]:
    values = [
        card.get("tare_weight"),
        card.get("total_gross_weight"),
        card.get("total_net_weight"),
        *(roll.get("gross_weight") for roll in gross_rolls),
    ]
    if any(decimal_from_value(value) is None for value in values):
        return ["Критичните тегла за печат трябва да са валидни числа."]

    tare = decimal_from_value(card.get("tare_weight"))
    total_net = decimal_from_value(card.get("total_net_weight"))
    gross_values = [decimal_from_value(roll.get("gross_weight")) for roll in gross_rolls]
    if (
        tare is not None
        and total_net is not None
        and (total_net < 0 or any(gross is not None and gross < tare for gross in gross_values))
    ):
        return ["Нето теглото за печат не може да бъде отрицателно."]

    return []


def assemble_print_data(card: dict[str, Any]) -> dict[str, Any]:
    gross_rolls = gross_roll_entries(card)
    recipe_actual_entries = card.get("recipe_actual_entries") or {}

    front = {
        "order_number": text_value(card.get("order_number")),
        "order_date": text_value(card.get("order_date")),
        "delivery_date": text_value(card.get("delivery_date")),
        "customer": text_value(card.get("customer")),
        "city": text_value(card.get("city")),
        "product_type": text_value(card.get("product_type")),
        "quantity_1": text_value(card.get("quantity_1")),
        "unit_1": text_value(card.get("unit_1")),
        "quantity_2": text_value(card.get("quantity_2")),
        "unit_2": text_value(card.get("unit_2")),
        "product_form": text_value(card.get("product_form")),
        "material": text_value(card.get("material")),
        "size_thickness": text_value(card.get("size_thickness")),
        "extrusion_folding": text_value(card.get("extrusion_folding")),
        "extrusion_next_operation": text_value(card.get("extrusion_next_operation")),
        "extrusion_treatment": text_value(card.get("extrusion_treatment")),
        "notes": text_value(card.get("notes")),
        "packaging_method": text_value(card.get("packaging_method")),
        "recipe_rows": build_recipe_rows(card, recipe_actual_entries),
    }
    back = {
        "order_number": text_value(card.get("order_number")),
        "customer": text_value(card.get("customer")),
        "product_type": text_value(card.get("product_type")),
        "start_display": format_datetime(card.get("first_started_at")),
        "stop_display": format_datetime(card.get("finished_at")),
        "duration_display": format_duration(
            int(card.get("total_production_seconds") or 0)
        ),
        "tare_display": format_weight(card.get("tare_weight")),
        "total_gross_display": format_weight(card.get("total_gross_weight")),
        "total_net_display": format_weight(card.get("total_net_weight")),
    }

    return {
        "card_id": card["id"],
        "front": front,
        "back": back,
        "roll_slots": build_roll_slots(gross_rolls),
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
                "planned_material": text_value(card.get(card_field)),
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


def format_datetime(value: Any) -> str:
    if value is None:
        return ""
    raw_value = str(value).strip()
    if not raw_value:
        return ""

    for candidate in (raw_value, raw_value.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.strftime("%d.%m.%Y %H:%M")
        except ValueError:
            continue

    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(raw_value, pattern)
            return parsed.strftime("%d.%m.%Y %H:%M")
        except ValueError:
            continue

    return raw_value


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
