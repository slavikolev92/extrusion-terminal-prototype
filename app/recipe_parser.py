from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping


RECIPE_SOURCE_FIELDS = (
    "raw_material_a",
    "raw_material_b",
    "raw_material_c",
    "linear_pe",
    "antistatic",
    "masterbatch",
    "chalk",
)

APPROVED_RECIPE_CATEGORIES = (
    "LDPE",
    "LLDPE",
    "MDPE",
    "reLDPE",
    "Antistatic",
    "Masterbatch",
    "Filler",
    "UV",
    "Antislip",
)

MISSING_DELIMITER_MESSAGE = "липсва разделител |"
UNKNOWN_CATEGORY_MESSAGE = "непозната категория"
MISSING_MATERIAL_MESSAGE = "липсва материал след категория"
MISSING_PERCENT_MESSAGE = "липсва процент"
INVALID_PERCENT_MESSAGE = "невалиден процент"
NON_POSITIVE_PERCENT_MESSAGE = "процентът трябва да е по-голям от 0%"
TOTAL_PERCENT_MESSAGE = "сборът на процентите трябва да е точно 100%"

TOTAL_PERCENT = Decimal("100")
PERCENT_PATTERN = re.compile(r"^\d+(?:[\.,]\d+)?$")
CATEGORY_BY_NORMALIZED_NAME = {
    category.casefold(): category for category in APPROVED_RECIPE_CATEGORIES
}


@dataclass(frozen=True)
class ParsedRecipeComponent:
    component_key: str
    source_text: str
    material_category: str
    planned_material: str
    recipe_percent: Decimal


@dataclass(frozen=True)
class RecipeParseError:
    component_key: str
    source_text: str
    message: str


@dataclass(frozen=True)
class RecipeParseResult:
    components: tuple[ParsedRecipeComponent, ...]
    errors: tuple[RecipeParseError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def total_percent(self) -> Decimal:
        return sum(
            (component.recipe_percent for component in self.components),
            Decimal("0"),
        )


def parse_recipe_source_fields(source_fields: Mapping[str, str | None]) -> RecipeParseResult:
    components: list[ParsedRecipeComponent] = []
    errors: list[RecipeParseError] = []

    for component_key in RECIPE_SOURCE_FIELDS:
        component, cell_errors = parse_recipe_cell(
            component_key,
            source_fields.get(component_key),
        )
        if component is not None:
            components.append(component)
        errors.extend(cell_errors)

    if not errors:
        parsed_total = sum(
            (component.recipe_percent for component in components),
            Decimal("0"),
        )
        if parsed_total != TOTAL_PERCENT:
            errors.append(
                RecipeParseError(
                    component_key="__total__",
                    source_text="",
                    message=TOTAL_PERCENT_MESSAGE,
                )
            )

    return RecipeParseResult(
        components=tuple(components),
        errors=tuple(errors),
    )


def parse_recipe_cell(
    component_key: str,
    source_text: str | None,
) -> tuple[ParsedRecipeComponent | None, tuple[RecipeParseError, ...]]:
    original_source_text = "" if source_text is None else str(source_text)
    stripped_source_text = original_source_text.strip()
    if not stripped_source_text:
        return None, ()

    if "|" not in stripped_source_text:
        return None, (
            RecipeParseError(
                component_key=component_key,
                source_text=original_source_text,
                message=MISSING_DELIMITER_MESSAGE,
            ),
        )

    identity_text, percent_text = stripped_source_text.rsplit("|", 1)
    normalized_identity = normalize_spaces(identity_text)
    if not normalized_identity:
        return None, (
            RecipeParseError(
                component_key=component_key,
                source_text=original_source_text,
                message=MISSING_MATERIAL_MESSAGE,
            ),
        )

    category_text, planned_material = split_category_and_material(normalized_identity)
    material_category = CATEGORY_BY_NORMALIZED_NAME.get(category_text.casefold())
    if material_category is None:
        return None, (
            RecipeParseError(
                component_key=component_key,
                source_text=original_source_text,
                message=UNKNOWN_CATEGORY_MESSAGE,
            ),
        )

    recipe_percent, percent_error = parse_percent(component_key, original_source_text, percent_text)
    if percent_error is not None:
        return None, (percent_error,)
    assert recipe_percent is not None

    return (
        ParsedRecipeComponent(
            component_key=component_key,
            source_text=original_source_text,
            material_category=material_category,
            planned_material=planned_material,
            recipe_percent=recipe_percent,
        ),
        (),
    )


def split_category_and_material(identity_text: str) -> tuple[str, str]:
    parts = identity_text.split(" ", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1].strip()


def normalize_spaces(value: str) -> str:
    return " ".join(value.split())


def parse_percent(
    component_key: str,
    source_text: str,
    percent_text: str,
) -> tuple[Decimal | None, RecipeParseError | None]:
    stripped_percent_text = percent_text.strip()
    if not stripped_percent_text or not stripped_percent_text.endswith("%"):
        return None, RecipeParseError(
            component_key=component_key,
            source_text=source_text,
            message=MISSING_PERCENT_MESSAGE,
        )

    numeric_text = stripped_percent_text[:-1].strip()
    if not numeric_text or not PERCENT_PATTERN.fullmatch(numeric_text):
        return None, RecipeParseError(
            component_key=component_key,
            source_text=source_text,
            message=INVALID_PERCENT_MESSAGE,
        )

    normalized_numeric_text = numeric_text.replace(",", ".")
    try:
        recipe_percent = Decimal(normalized_numeric_text)
    except InvalidOperation:
        return None, RecipeParseError(
            component_key=component_key,
            source_text=source_text,
            message=INVALID_PERCENT_MESSAGE,
        )

    if recipe_percent <= Decimal("0"):
        return None, RecipeParseError(
            component_key=component_key,
            source_text=source_text,
            message=NON_POSITIVE_PERCENT_MESSAGE,
        )

    return recipe_percent, None
