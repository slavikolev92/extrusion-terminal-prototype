# Structured Recipe Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and test the central app-side parser for structured extrusion recipe source cells from workbook columns `AM:AS`.

**Architecture:** Add one focused parser module that converts the existing imported recipe source fields into parsed recipe component objects plus concise Bulgarian validation errors. Keep the parser pure and independent from SQLite, FastAPI routes, release actions, template rendering, and Excel macro validation so later roadmap steps can call it from import sync, normalized storage, and release validation without duplicating parsing rules.

**Tech Stack:** Python 3, standard-library `dataclasses`, `decimal.Decimal`, `re`, pytest, existing FastAPI/SQLite codebase conventions.

---

## Repository Rules For Execution

- Work in `/home/sk/projects/extrusion-terminal`.
- Follow `AGENTS.md`.
- Use the repo-local Python virtualenv: `source .venv/bin/activate`.
- Do not mutate `data/extrusion_terminal.sqlite3`.
- Do not run UI checks for this parser-only step.
- Do not stage or commit unless the user explicitly asks. This repository rule overrides generic Superpowers examples that mention committing each task.
- Keep this plan scoped to OI-003 Step 2 only: parser and parser tests.
- Do not add schema, release gates, import sync, UI redesign, Excel macro validation, material pricing, inventory tracking, or material catalog management in this step.

## Source Contract

Use [docs/implementation-notes/structured-recipe-contract.md](/home/sk/projects/extrusion-terminal/docs/implementation-notes/structured-recipe-contract.md) as the authoritative parser contract.

Parser inputs are the existing app fields that map to workbook columns `AM:AS`:

```python
RECIPE_SOURCE_FIELDS = (
    "raw_material_a",
    "raw_material_b",
    "raw_material_c",
    "linear_pe",
    "antistatic",
    "masterbatch",
    "chalk",
)
```

Each non-empty source cell must use:

```text
[Material/Additive Category] [Producer or Brand] [Full Commercial Grade/Code] | [% of final product]
```

The parser must:

- ignore empty source cells;
- split on the final `|`;
- preserve the original source cell text in the parsed result;
- normalize extra whitespace for parsed identity fields;
- match material categories case-insensitively;
- normalize accepted category input to canonical spelling;
- require an approved category;
- require planned material text after the category;
- require the `%` symbol;
- accept dot decimals such as `2.5%`;
- accept comma decimals such as `2,5%` and normalize them to `Decimal("2.5")`;
- reject zero and negative percentages;
- reject malformed percentages;
- require all parsed non-empty rows to total exactly `Decimal("100")`;
- return Bulgarian error messages without raising exceptions for bad recipe text.

Initial approved categories:

```python
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
```

## File Structure

Create:

- `app/recipe_parser.py`
  - Owns the structured recipe parser contract in executable Python.
  - Exposes approved category constants, source field constants, parsed component dataclasses, parser error dataclass, parse result dataclass, `parse_recipe_cell()`, and `parse_recipe_source_fields()`.
  - Has no database, FastAPI, Jinja2, or importer side effects.

- `tests/test_recipe_parser.py`
  - Focused parser tests using pure Python data.
  - Does not initialize or mutate the SQLite database.

Do not modify:

- `app/db.py`
- `app/importer.py`
- `app/main.py`
- `app/templates/*.html`
- `open-issues.md`
- Excel macro files
- files under `interim-costing-process/`

Those files belong to later roadmap steps.

## Public Parser Interface

The implementation should provide this import surface:

```python
from app.recipe_parser import (
    APPROVED_RECIPE_CATEGORIES,
    RECIPE_SOURCE_FIELDS,
    ParsedRecipeComponent,
    RecipeParseError,
    RecipeParseResult,
    parse_recipe_cell,
    parse_recipe_source_fields,
)
```

Expected dataclass fields:

```python
@dataclass(frozen=True)
class ParsedRecipeComponent:
    component_key: str
    source_text: str
    material_category: str
    planned_material: str
    recipe_percent: Decimal
```

```python
@dataclass(frozen=True)
class RecipeParseError:
    component_key: str
    source_text: str
    message: str
```

```python
@dataclass(frozen=True)
class RecipeParseResult:
    components: tuple[ParsedRecipeComponent, ...]
    errors: tuple[RecipeParseError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def total_percent(self) -> Decimal:
        return sum((component.recipe_percent for component in self.components), Decimal("0"))
```

Expected function signatures:

```python
def parse_recipe_cell(
    component_key: str,
    source_text: str | None,
) -> tuple[ParsedRecipeComponent | None, tuple[RecipeParseError, ...]]:
    ...
```

```python
def parse_recipe_source_fields(
    source_fields: Mapping[str, str | None],
) -> RecipeParseResult:
    ...
```

## Error Messages

Use these exact parser-level Bulgarian messages:

```python
MISSING_DELIMITER_MESSAGE = "липсва разделител |"
UNKNOWN_CATEGORY_MESSAGE = "непозната категория"
MISSING_MATERIAL_MESSAGE = "липсва материал след категория"
MISSING_PERCENT_MESSAGE = "липсва процент"
INVALID_PERCENT_MESSAGE = "невалиден процент"
NON_POSITIVE_PERCENT_MESSAGE = "процентът трябва да е по-голям от 0%"
TOTAL_PERCENT_MESSAGE = "сборът на процентите трябва да е точно 100%"
```

The parser returns errors with the `component_key` that failed. The total-percent error uses `component_key="__total__"` and `source_text=""`.

Later release-gate work can wrap these into the user-facing sentence:

```text
Рецептата не може да бъде пусната: [reason]. Коригирайте рецептата и опитайте отново.
```

That release-gate wrapping is not part of this parser step.

## Task 1: Add Failing Parser Tests For Valid Structured Recipes

**Files:**

- Create: `tests/test_recipe_parser.py`

- [ ] **Step 1: Create the test file with valid-recipe tests**

Create `tests/test_recipe_parser.py` with this content:

```python
from __future__ import annotations

from decimal import Decimal

from app.recipe_parser import (
    APPROVED_RECIPE_CATEGORIES,
    ParsedRecipeComponent,
    parse_recipe_cell,
    parse_recipe_source_fields,
)


def error_messages(result):
    return tuple(error.message for error in result.errors)


def test_approved_recipe_categories_match_locked_contract():
    assert APPROVED_RECIPE_CATEGORIES == (
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


def test_parse_structured_recipe_fields_returns_components_and_exact_total():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "LDPE Rompetrol Midilena B20/03 | 77%",
            "linear_pe": "LLDPE SABIC 119ZJ | 18%",
            "antistatic": "Antistatic Novachem AT 04673 LD | 2%",
            "masterbatch": "Masterbatch Polibach White 8000 ET | 3%",
        }
    )

    assert result.ok
    assert result.errors == ()
    assert result.total_percent == Decimal("100")
    assert result.components == (
        ParsedRecipeComponent(
            component_key="raw_material_a",
            source_text="LDPE Rompetrol Midilena B20/03 | 77%",
            material_category="LDPE",
            planned_material="Rompetrol Midilena B20/03",
            recipe_percent=Decimal("77"),
        ),
        ParsedRecipeComponent(
            component_key="linear_pe",
            source_text="LLDPE SABIC 119ZJ | 18%",
            material_category="LLDPE",
            planned_material="SABIC 119ZJ",
            recipe_percent=Decimal("18"),
        ),
        ParsedRecipeComponent(
            component_key="antistatic",
            source_text="Antistatic Novachem AT 04673 LD | 2%",
            material_category="Antistatic",
            planned_material="Novachem AT 04673 LD",
            recipe_percent=Decimal("2"),
        ),
        ParsedRecipeComponent(
            component_key="masterbatch",
            source_text="Masterbatch Polibach White 8000 ET | 3%",
            material_category="Masterbatch",
            planned_material="Polibach White 8000 ET",
            recipe_percent=Decimal("3"),
        ),
    )


def test_parse_ignores_empty_cells_when_non_empty_rows_total_100():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "LDPE Rompetrol B20/03 | 80%",
            "raw_material_b": "",
            "raw_material_c": None,
            "linear_pe": "LLDPE SABIC 119ZJ | 20%",
            "antistatic": "",
            "masterbatch": "",
            "chalk": "",
        }
    )

    assert result.ok
    assert result.total_percent == Decimal("100")
    assert [component.component_key for component in result.components] == [
        "raw_material_a",
        "linear_pe",
    ]


def test_parse_cell_splits_on_final_pipe():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Producer | Internal grade note B20/03 | 100%",
    )

    assert errors == ()
    assert component == ParsedRecipeComponent(
        component_key="raw_material_a",
        source_text="LDPE Producer | Internal grade note B20/03 | 100%",
        material_category="LDPE",
        planned_material="Producer | Internal grade note B20/03",
        recipe_percent=Decimal("100"),
    )
```

- [ ] **Step 2: Run the valid-recipe tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_parser.py -q
```

Expected result:

```text
ModuleNotFoundError: No module named 'app.recipe_parser'
```

Do not create parser implementation before seeing this failure.

## Task 2: Implement The Minimal Parser For Valid Recipes

**Files:**

- Create: `app/recipe_parser.py`

- [ ] **Step 1: Create the parser module**

Create `app/recipe_parser.py` with this content:

```python
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

    if not planned_material:
        return None, (
            RecipeParseError(
                component_key=component_key,
                source_text=original_source_text,
                message=MISSING_MATERIAL_MESSAGE,
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
```

- [ ] **Step 2: Run the valid-recipe tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_parser.py -q
```

Expected result:

```text
4 passed
```

If fewer or more tests exist because this plan has already been partially executed, all current tests in `tests/test_recipe_parser.py` should pass.

## Task 3: Add Failing Parser Tests For Normalization And Validation Errors

**Files:**

- Modify: `tests/test_recipe_parser.py`

- [ ] **Step 1: Append normalization and invalid-recipe tests**

Append this content to `tests/test_recipe_parser.py`:

```python

def test_parse_normalizes_category_case_decimal_comma_and_extra_spaces():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "  ldpe   Rompetrol   B20/03  |  97,5 %  ",
            "masterbatch": "uv Stabilizer 123 | 2.5%",
        }
    )

    assert result.ok
    assert result.total_percent == Decimal("100.0")
    assert result.components[0] == ParsedRecipeComponent(
        component_key="raw_material_a",
        source_text="  ldpe   Rompetrol   B20/03  |  97,5 %  ",
        material_category="LDPE",
        planned_material="Rompetrol B20/03",
        recipe_percent=Decimal("97.5"),
    )
    assert result.components[1] == ParsedRecipeComponent(
        component_key="masterbatch",
        source_text="uv Stabilizer 123 | 2.5%",
        material_category="UV",
        planned_material="Stabilizer 123",
        recipe_percent=Decimal("2.5"),
    )


def test_parse_normalizes_reldpe_to_canonical_spelling():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "reldpe Natural Regranulate | 100%",
        }
    )

    assert result.ok
    assert result.components[0].material_category == "reLDPE"


def test_parse_reports_missing_final_pipe():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Rompetrol B20/03 100%",
    )

    assert component is None
    assert errors[0].component_key == "raw_material_a"
    assert errors[0].source_text == "LDPE Rompetrol B20/03 100%"
    assert errors[0].message == "липсва разделител |"


def test_parse_requires_percent_symbol():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Rompetrol B20/03 | 100",
    )

    assert component is None
    assert errors[0].message == "липсва процент"


def test_parse_rejects_unknown_category():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "mLLDPE Marlex 1018 | 100%",
    )

    assert component is None
    assert errors[0].message == "непозната категория"


def test_parse_rejects_missing_material_after_category():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE | 100%",
    )

    assert component is None
    assert errors[0].message == "липсва материал след категория"


def test_parse_rejects_invalid_percent_text():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Rompetrol B20/03 | one hundred%",
    )

    assert component is None
    assert errors[0].message == "невалиден процент"


def test_parse_rejects_zero_and_negative_percentages():
    zero_component, zero_errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Rompetrol B20/03 | 0%",
    )
    negative_component, negative_errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Rompetrol B20/03 | -1%",
    )

    assert zero_component is None
    assert zero_errors[0].message == "процентът трябва да е по-голям от 0%"
    assert negative_component is None
    assert negative_errors[0].message == "невалиден процент"


def test_parse_requires_total_percent_to_be_exactly_100():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "LDPE Rompetrol B20/03 | 80%",
            "linear_pe": "LLDPE SABIC 119ZJ | 19%",
        }
    )

    assert not result.ok
    assert result.total_percent == Decimal("99")
    assert error_messages(result) == ("сборът на процентите трябва да е точно 100%",)
    assert result.errors[0].component_key == "__total__"


def test_parse_returns_cell_errors_without_adding_total_error():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "LDPE Rompetrol B20/03 | 80%",
            "linear_pe": "LLDPE SABIC 119ZJ | 20",
        }
    )

    assert not result.ok
    assert result.total_percent == Decimal("80")
    assert error_messages(result) == ("липсва процент",)
```

- [ ] **Step 2: Run the expanded parser tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_parser.py -q
```

Expected result:

```text
14 passed
```

## Task 4: Add Parser Boundary Tests For No Database Or App Workflow Coupling

**Files:**

- Modify: `tests/test_recipe_parser.py`

- [ ] **Step 1: Append boundary tests**

Append this content to `tests/test_recipe_parser.py`:

```python

def test_parser_source_fields_match_workbook_recipe_field_order():
    from app.recipe_parser import RECIPE_SOURCE_FIELDS

    assert RECIPE_SOURCE_FIELDS == (
        "raw_material_a",
        "raw_material_b",
        "raw_material_c",
        "linear_pe",
        "antistatic",
        "masterbatch",
        "chalk",
    )


def test_parser_does_not_require_all_mapping_keys_to_be_present():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "LDPE Rompetrol B20/03 | 100%",
            "unrelated_field": "ignored",
        }
    )

    assert result.ok
    assert len(result.components) == 1
    assert result.components[0].component_key == "raw_material_a"
```

- [ ] **Step 2: Run the parser test module**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_parser.py -q
```

Expected result:

```text
16 passed
```

## Task 5: Run Focused And Baseline Verification

**Files:**

- No file edits.

- [ ] **Step 1: Run the focused parser tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_parser.py -q
```

Expected result:

```text
16 passed
```

- [ ] **Step 2: Run the existing baseline suite**

Run:

```bash
source .venv/bin/activate
python -m pytest -q
```

Expected result:

```text
all tests pass
```

The exact count can vary as other branches add tests. There should be no failures or errors.

- [ ] **Step 3: Run whitespace check**

Run:

```bash
git diff --check
```

Expected result:

```text
no output
```

- [ ] **Step 4: Inspect changed files**

Run:

```bash
git status --short
git diff -- app/recipe_parser.py tests/test_recipe_parser.py docs/implementation-notes/structured-recipe-contract.md
```

Expected result:

- `app/recipe_parser.py` is new.
- `tests/test_recipe_parser.py` is new.
- `docs/implementation-notes/structured-recipe-contract.md` may already be modified from Step 1.
- No database files, artifacts, generated reports, or files under `interim-costing-process/` are modified.
- No release gate, storage, UI, or Excel macro files are modified.

## Task 6: Implementation Self-Review

**Files:**

- No file edits unless the review finds a concrete defect.

- [ ] **Step 1: Check parser contract coverage**

Confirm each requirement has an implementation and at least one test:

- empty cells are ignored;
- final `|` is used as the delimiter;
- original `source_text` is preserved;
- extra whitespace is normalized in parsed identity fields;
- category matching is case-insensitive;
- accepted category input normalizes to canonical spelling;
- unknown category is rejected;
- missing planned material is rejected;
- `%` is required;
- dot decimals are accepted;
- comma decimals are accepted and normalized;
- malformed percent text is rejected;
- zero percentages are rejected;
- negative percentages are rejected;
- total percent must equal exactly `100`;
- parser returns errors rather than raising for bad recipe source text.

- [ ] **Step 2: Check dependency boundary**

Run:

```bash
rg -n "sqlite|FastAPI|Request|TemplateResponse|connect\\(|import_cards_from_csv|release_card" app/recipe_parser.py tests/test_recipe_parser.py
```

Expected result:

```text
no output
```

If there is output, remove the coupling unless it is only inside a quoted explanatory string in this plan, not in implementation files.

- [ ] **Step 3: Check for accidental roadmap spillover**

Run:

```bash
git diff --name-only
```

Expected allowed output after implementation:

```text
app/recipe_parser.py
docs/implementation-notes/structured-recipe-contract.md
docs/superpowers/plans/2026-06-24-structured-recipe-parser.md
tests/test_recipe_parser.py
```

If other files appear, inspect them. Keep only changes explicitly required for Step 2 parser work unless the user approved additional scope.

## Completion Criteria

Step 2 is complete when:

- `app/recipe_parser.py` exists and exposes the parser interface described above;
- `tests/test_recipe_parser.py` covers valid parsing, normalization, invalid cells, exact total validation, and parser boundary behavior;
- `python -m pytest tests/test_recipe_parser.py -q` passes;
- `python -m pytest -q` passes;
- `git diff --check` passes;
- no app release gate, normalized storage, UI, Excel macro, or interim-costing-process files were changed;
- no files are staged or committed unless the user explicitly asked for that.
