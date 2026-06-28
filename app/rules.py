from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .constants import (
    ACTIVE_TERMINAL_STATUSES,
    STATUS_IMPORTED,
    STATUS_PENDING,
    STATUS_PAUSED,
    STATUS_RUNNING,
)
from .recipe_parser import RECIPE_SOURCE_FIELDS, parse_recipe_source_fields


RELEASABLE_STATUSES = (STATUS_IMPORTED,)

RECIPE_RELEASE_FIELD_LABELS = {
    "raw_material_a": "Суровина A",
    "raw_material_b": "Суровина B",
    "raw_material_c": "Суровина C",
    "linear_pe": "Линеен",
    "antistatic": "Антистатик",
    "masterbatch": "Мастербач",
    "chalk": "Креда",
}

RECIPE_RELEASE_PREFIX = "Рецептата не може да бъде пусната"
RECIPE_RELEASE_SUFFIX = "Коригирайте рецептата и опитайте отново."
TARGET_GROSS_RELEASE_REASON = "липсват планирани кг/поръчано количество"


@dataclass(frozen=True)
class RuleResult:
    ok: bool
    messages: tuple[str, ...] = ()


def recipe_release_message(reason: str) -> str:
    return f"{RECIPE_RELEASE_PREFIX}: {reason}. {RECIPE_RELEASE_SUFFIX}"


def decimal_from_quantity_text(value: Any) -> Decimal | None:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        quantity = Decimal(text)
    except InvalidOperation:
        return None
    if not quantity.is_finite():
        return None
    return quantity


def target_gross_weight_from_card(card: dict[str, Any]) -> Decimal | None:
    quantity = decimal_from_quantity_text(card.get("quantity_1"))
    if quantity is not None and quantity > Decimal("0"):
        return quantity
    return None


def validate_structured_recipe_release(card: dict[str, Any]) -> RuleResult:
    source_fields = {field: card.get(field) for field in RECIPE_SOURCE_FIELDS}
    parse_result = parse_recipe_source_fields(source_fields)
    messages: list[str] = []

    for error in parse_result.errors:
        if error.component_key == "__total__":
            reason = error.message
        else:
            label = RECIPE_RELEASE_FIELD_LABELS.get(error.component_key, error.component_key)
            reason = f"{label}: {error.message}"
        messages.append(recipe_release_message(reason))

    if target_gross_weight_from_card(card) is None:
        messages.append(recipe_release_message(TARGET_GROSS_RELEASE_REASON))

    return RuleResult(ok=not messages, messages=tuple(messages))


def validate_release_fields(card: dict) -> RuleResult:
    messages: list[str] = []

    if card.get("status") not in RELEASABLE_STATUSES:
        messages.append("Само импортирани технологични карти могат да се изпращат.")
    if not card.get("machine_id"):
        messages.append("Изберете машина преди изпращане.")
    if card.get("machine_sequence") in (None, ""):
        messages.append("Въведете ред преди изпращане.")

    return RuleResult(ok=not messages, messages=tuple(messages))


def is_active_terminal_status(status: str) -> bool:
    return status in ACTIVE_TERMINAL_STATUSES


def machine_is_occupied(status: str) -> bool:
    return status in (STATUS_PENDING, STATUS_RUNNING, STATUS_PAUSED)
