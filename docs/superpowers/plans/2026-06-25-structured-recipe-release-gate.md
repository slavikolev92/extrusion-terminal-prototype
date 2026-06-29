# Structured Recipe Release Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Block release of imported extrusion cards when structured recipe source fields or target gross weight violate the locked structured recipe contract.

**Architecture:** Keep CSV import, overwrite re-import, and admin source-field edits permissive so bad draft data can be corrected before release. Reuse `app.recipe_parser.parse_recipe_source_fields()` at the release boundary, add a small backend release-gate helper in `app/rules.py`, and call it from `app.db.release_card()` before any status, machine, sequence, or max-roll changes are written.

**Tech Stack:** Python 3, FastAPI route handlers, direct `sqlite3`, existing `app.recipe_parser`, existing `RuleResult`, pytest with temporary SQLite databases.

---

## Repository Rules For Execution

- Work in `/home/sk/projects/extrusion-terminal` on branch `structured-recipe-redesign`.
- Follow `AGENTS.md`; `README.md` is authoritative when repo docs conflict.
- Do not stage or commit unless the user explicitly asks.
- Use the repo-local virtualenv for verification.
- Tests must use temporary SQLite databases and must not mutate `data/extrusion_terminal.sqlite3`.
- This is OI-003 Step 5 only.

## Context Loaded Before This Plan

- `AGENTS.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `open-issues.md`
- `docs/implementation-notes/structured-recipe-contract.md`
- `docs/superpowers/plans/2026-06-25-structured-recipe-sync.md`
- `app/recipe_parser.py`
- `app/db.py`
- `app/importer.py`
- `app/main.py`
- `app/rules.py`
- `tests/test_recipe_parser.py`
- `tests/test_recipe_storage.py`
- `tests/test_recipe_sync.py`
- release/planning/admin tests around `release_card`, stale edits, and admin planning routes

Baseline check run before writing this plan:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_parser.py tests/test_recipe_storage.py tests/test_recipe_sync.py tests/test_baseline.py::test_release_succeeds_for_ready_cards tests/test_baseline.py::test_release_blocks_cards_without_usable_extrusion_fields tests/test_admin_planning.py::test_release_accepts_loaded_version_and_clamps_empty_machine_to_first_position tests/test_admin_planning.py::test_release_blocks_stale_loaded_version tests/test_admin_routes.py::test_failed_release_and_planning_still_render_inline_without_redirect -q
```

Observed output:

```text
44 passed in 1.69s
```

## Current Step 4 State To Preserve

- `cards.raw_material_a` through `cards.chalk` remain the authoritative imported source text for import, print, and current legacy displays.
- `recipe_components` rows are derived from source text during import, overwrite re-import, admin imported-field correction, and admin material-ledger source correction.
- Step 4 intentionally syncs parsed rows permissively and does not block bad draft recipe data.
- `recipe_actual_entries` stores terminal/admin-entered actual material and batch/lot production data and must not be touched by release validation.
- `tests/test_recipe_sync.py::test_import_sync_does_not_block_parser_errors_or_add_release_gate` currently asserts the old Step 4 boundary where release succeeds on a 99% recipe. Step 5 must replace that release-success assertion.

## Step 5 Scope

Release must be blocked when:

- any non-empty recipe source field cannot parse;
- category, material identity, or percentage rules fail;
- parsed recipe percentages do not total exactly `100%`;
- target gross weight is missing, zero, or invalid.

Release must continue to enforce existing checks:

- card exists;
- stale loaded version blocks release;
- status must be `imported`;
- current card fields must represent usable extrusion work;
- machine must exist;
- machine sequence must be `>= 1`;
- queue normalization and duplicate active sequence protection still run only after validation passes.

## Explicit Non-Scope

Do not implement:

- Step 6 terminal/admin structured recipe display redesign;
- print output changes;
- Excel macro/export validation;
- pricing, costing, inventory, ERP behavior, or material catalog management;
- material master/category management UI;
- changes under `interim-costing-process/source-files/recipe-builder-demo/`.

## Files To Modify Or Create

- Create: `tests/test_recipe_release_validation.py`
  - New focused release-gate tests for malformed recipe rows, category/material/percent failures, non-100 totals, target gross failures, successful structured release, draft permissiveness, and admin route error rendering.
- Modify: `tests/test_recipe_sync.py`
  - Replace the Step 4 “does not add release gate” assertion with a Step 4-only import/admin permissiveness assertion.
- Modify: `app/rules.py`
  - Add structured recipe release-gate helpers and target gross parsing.
- Modify: `app/db.py`
  - Call the new release-gate helper inside `release_card()` before database mutation.
- Modify test fixtures in release-success suites so cards expected to release use structured recipe text:
  - `tests/test_baseline.py`
  - `tests/test_admin_planning.py`
  - `tests/test_admin_routes.py`
  - `tests/test_terminal_detail.py`
  - `tests/test_terminal_sync.py`
  - `tests/test_production_timing.py`
  - `tests/test_finish_cancel_history.py`
  - `tests/test_roll_entry.py`
  - `tests/test_admin_card_review.py`
  - `tests/test_admin_card_detail_redesign.py`
  - `tests/test_admin_production_corrections.py`
  - `tests/test_terminal_v8_render.py`
  - `tests/test_print_output.py`
  - `tests/test_backup_recovery.py`
- Modify: `IMPLEMENTATION_PLAN.md`
  - Mark OI-003 Step 5 complete after implementation and verification.

Files that should not change:

- `app/templates/**`
- `app/static/**`
- `app/printing.py`
- `source-files/excel-macros/**`
- `interim-costing-process/source-files/recipe-builder-demo/**`

## Design Details

### Release-Gate Message Format

Use one Bulgarian release-gate message per blocking recipe/target-gross reason:

```text
Рецептата не може да бъде пусната: [reason]. Коригирайте рецептата и опитайте отново.
```

Use these row labels in release messages:

```python
RECIPE_RELEASE_FIELD_LABELS = {
    "raw_material_a": "Суровина A",
    "raw_material_b": "Суровина B",
    "raw_material_c": "Суровина C",
    "linear_pe": "Линеен",
    "antistatic": "Антистатик",
    "masterbatch": "Мастербач",
    "chalk": "Креда",
}
```

Examples:

```text
Рецептата не може да бъде пусната: Суровина A: липсва разделител |. Коригирайте рецептата и опитайте отново.
Рецептата не може да бъде пусната: сборът на процентите трябва да е точно 100%. Коригирайте рецептата и опитайте отново.
Рецептата не може да бъде пусната: липсват планирани кг/поръчано количество. Коригирайте рецептата и опитайте отново.
```

### Target Gross Rule

Treat either quantity line as target gross when:

- `unit_1` or `unit_2` normalizes to `kg`, `kgs`, `кг`, `килограм`, or `килограма`;
- the matching `quantity_1` or `quantity_2` parses to a decimal greater than `0`.

Block release when no quantity line satisfies both requirements.

### Existing Parser Behavior To Reuse

- `parse_recipe_source_fields()` ignores empty source cells.
- It validates all non-empty rows in `RECIPE_SOURCE_FIELDS` order.
- It returns row-level errors for missing delimiter, unknown category, missing material, missing percent, invalid percent, and non-positive percent.
- It adds the exact-total error only when there are no row-level parse errors.
- It accepts comma decimal percentages and normalizes them to `Decimal`.

## Task 1: Add Focused Release-Gate Tests

**Files:**

- Create: `tests/test_recipe_release_validation.py`
- Modify: `tests/test_recipe_sync.py`

- [ ] **Step 1: Create `tests/test_recipe_release_validation.py` with shared helpers**

Add this file:

```python
from __future__ import annotations

import asyncio
import csv
import io

import pytest

from app import db
from app.constants import STATUS_IMPORTED, STATUS_PENDING
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import app, release_card_to_terminal
from starlette.requests import Request


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
```

- [ ] **Step 2: Add test that a valid structured recipe can release**

Append:

```python
def test_release_allows_valid_structured_recipe_and_target_gross(connection):
    card_id = import_structured_card("RS-REL-001")

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["status"] == STATUS_PENDING
    assert card["machine_id"] == 1
    assert card["machine_sequence"] == 1
```

- [ ] **Step 3: Add row-level recipe failure tests**

Append:

```python
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
            {"raw_material_a": "LDPE | 80%"},
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
```

- [ ] **Step 4: Add exact-total failure test**

Append:

```python
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
```

- [ ] **Step 5: Add target gross failure tests**

Append:

```python
@pytest.mark.parametrize(
    ("order_number", "overrides"),
    [
        ("RS-REL-008", {"quantity_1": "", "unit_1": ""}),
        ("RS-REL-009", {"quantity_1": "0", "unit_1": "kg"}),
        ("RS-REL-010", {"quantity_1": "-10", "unit_1": "kg"}),
        ("RS-REL-011", {"quantity_1": "not a number", "unit_1": "kg"}),
        ("RS-REL-012", {"quantity_1": "1000", "unit_1": "pcs"}),
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
```

- [ ] **Step 6: Add acceptance tests for comma decimals and quantity line 2**

Append:

```python
def test_release_accepts_comma_decimal_recipe_percent_and_quantity_2_target_gross(connection):
    card_id = import_structured_card(
        "RS-REL-013",
        quantity_1="200",
        unit_1="бр",
        quantity_2="1250,5",
        unit_2="кг",
        raw_material_a="LDPE Rompetrol B20/03 | 97,5%",
        linear_pe="LLDPE SABIC 119ZJ | 2,5%",
    )

    result = db.release_card(card_id, machine_id=2, machine_sequence=3)
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["status"] == STATUS_PENDING
    assert card["machine_id"] == 2
    assert card["machine_sequence"] == 1
```

- [ ] **Step 7: Add draft permissiveness test**

Append:

```python
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
```

- [ ] **Step 8: Add admin route render test for failed release**

Append:

```python
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
```

- [ ] **Step 9: Run the new release-gate tests and verify they fail**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_release_validation.py -q
```

Expected:

```text
FAILED tests/test_recipe_release_validation.py::test_release_blocks_recipe_row_contract_failures
FAILED tests/test_recipe_release_validation.py::test_release_blocks_recipe_total_that_is_not_exactly_100
FAILED tests/test_recipe_release_validation.py::test_release_blocks_missing_zero_or_invalid_target_gross
FAILED tests/test_recipe_release_validation.py::test_admin_release_route_renders_recipe_gate_errors_inline
```

The valid-release tests may pass only after existing helpers are updated; the negative tests should fail because release currently has no Step 5 gate.

- [ ] **Step 10: Replace the obsolete Step 4 boundary assertion**

In `tests/test_recipe_sync.py`, rename:

```python
def test_import_sync_does_not_block_parser_errors_or_add_release_gate(connection):
```

to:

```python
def test_import_sync_does_not_block_parser_errors_before_release(connection):
```

Delete this release-success block from the test:

```python
    release_result = db.release_card(card_id, machine_id=1, machine_sequence=1)
    released = db.fetch_admin_card_detail(card_id)

    assert release_result.ok
    assert released["status"] == STATUS_PENDING
```

Keep the import and `component_summary()` assertions unchanged.

## Task 2: Implement Backend Release-Gate Helpers

**Files:**

- Modify: `app/rules.py`

- [ ] **Step 1: Add imports**

At the top of `app/rules.py`, change the imports to include decimal parsing and recipe parser helpers:

```python
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .recipe_parser import RECIPE_SOURCE_FIELDS, parse_recipe_source_fields
```

- [ ] **Step 2: Add constants below `RELEASABLE_STATUSES`**

```python
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
TARGET_GROSS_UNITS = {"kg", "kgs", "кг", "килограм", "килограма"}
QUANTITY_NUMBER_PATTERN = re.compile(r"\d+(?:[\.,]\d+)?")
```

- [ ] **Step 3: Add target-gross helper functions below `RuleResult`**

```python
def recipe_release_message(reason: str) -> str:
    return f"{RECIPE_RELEASE_PREFIX}: {reason}. {RECIPE_RELEASE_SUFFIX}"


def normalize_quantity_unit(value: Any) -> str:
    return str(value or "").strip().casefold().rstrip(".")


def decimal_from_quantity_text(value: Any) -> Decimal | None:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        pass

    match = QUANTITY_NUMBER_PATTERN.search(text)
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", "."))
    except InvalidOperation:
        return None


def target_gross_weight_from_card(card: dict[str, Any]) -> Decimal | None:
    for index in (1, 2):
        unit = normalize_quantity_unit(card.get(f"unit_{index}"))
        if unit not in TARGET_GROSS_UNITS:
            continue
        quantity = decimal_from_quantity_text(card.get(f"quantity_{index}"))
        if quantity is not None and quantity > Decimal("0"):
            return quantity
    return None
```

- [ ] **Step 4: Add structured recipe release validator**

Add below the target-gross helpers:

```python
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
```

- [ ] **Step 5: Run focused unit-style import check**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_parser.py -q
```

Expected:

```text
16 passed
```

The exact count may be higher if parser tests were added later. There should be no failures.

## Task 3: Wire Release Validation Into `release_card`

**Files:**

- Modify: `app/db.py`

- [ ] **Step 1: Import the new validator**

Find the existing rules import block in `app/db.py` and add `validate_structured_recipe_release`:

```python
from .rules import (
    RuleResult,
    is_active_terminal_status,
    machine_is_occupied,
    validate_structured_recipe_release,
)
```

If the current import layout differs, preserve the local ordering and add only this symbol.

- [ ] **Step 2: Call the validator inside `release_card()`**

In `release_card()`, after:

```python
        card_fields = {field: str(card[field] or "") for field in IMPORT_FIELDS}
        if not card_has_usable_extrusion_step(card_fields):
            messages.append("Картата трябва да има валидна стъпка за екструдиране преди изпращане.")
```

add:

```python
        recipe_release_result = validate_structured_recipe_release(card_fields)
        messages.extend(recipe_release_result.messages)
```

Do not place this after the `UPDATE cards` block. All release-gate validation must happen before mutation.

- [ ] **Step 3: Run the focused release-gate tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_release_validation.py -q
```

Expected:

```text
passed
```

At this point, old release-success fixtures elsewhere may fail because they still use unstructured `LDPE A`.

## Task 4: Convert Existing Release-Success Fixtures To Structured Recipe Text

**Files:**

- Modify release-success fixtures in the files listed in “Files To Modify Or Create”.

- [ ] **Step 1: Find old unstructured release fixtures**

Run:

```bash
rg -n 'raw_material_a"\s*:\s*"LDPE A"|raw_material_a="LDPE A"|raw_material_a"\s*:\s*"Planned LDPE A"|raw_material_a="Original A"|raw_material_b="LDPE B"|raw_material_b"\s*:\s*"LDPE B"' tests
```

Expected: matches in release helper fixtures and a few assertions.

- [ ] **Step 2: Update helper defaults that should release**

In helper row defaults used by release tests, replace:

```python
"raw_material_a": "LDPE A",
```

with:

```python
"raw_material_a": "LDPE A | 100%",
```

Apply this in:

- `tests/test_baseline.py`
- `tests/test_admin_planning.py`
- `tests/test_terminal_detail.py`
- `tests/test_terminal_sync.py`
- `tests/test_production_timing.py`
- `tests/test_finish_cancel_history.py`
- `tests/test_roll_entry.py`
- `tests/test_admin_card_review.py`
- `tests/test_admin_production_corrections.py`
- `tests/test_terminal_v8_render.py`
- `tests/test_print_output.py`
- `tests/test_backup_recovery.py`

- [ ] **Step 3: Update admin card detail redesign helper default**

In `tests/test_admin_card_detail_redesign.py`, replace:

```python
"raw_material_a": "Planned LDPE A",
```

with:

```python
"raw_material_a": "LDPE Planned A | 100%",
```

Update assertions that expected the old source text:

```python
assert updated["raw_material_a"] == "Planned LDPE A"
```

to:

```python
assert updated["raw_material_a"] == "LDPE Planned A | 100%"
```

- [ ] **Step 4: Update explicit old assertions**

Where tests assert legacy source text for a released card, update the expected text to the new structured source text. Known examples from the context scan:

```python
assert card["raw_material_a"] == "LDPE A | 100%"
assert unchanged["raw_material_a"] == "LDPE A | 100%"
```

For print-output expected maps in `tests/test_print_output.py`, update expected planned material cells only when they come from the release fixture:

```python
("raw_material_a", "A"): "LDPE A | 100%"
```

Do not change expected actual material/batch values such as `"Actual LDPE A"` or `"LOT-A"`.

- [ ] **Step 5: Update tests with additional non-empty recipe rows**

Any card expected to release with more than one non-empty recipe source field must total exactly `100%`.

Use these replacements:

```python
raw_material_a="LDPE A | 60%"
raw_material_b="LDPE B | 40%"
```

or:

```python
raw_material_a="LDPE Original A | 100%"
```

For tests that only import draft cards and do not release them, leave unstructured draft data only when the test is intentionally proving draft permissiveness.

- [ ] **Step 6: Run release/planning-focused tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_baseline.py::test_release_succeeds_for_ready_cards tests/test_baseline.py::test_release_blocks_cards_without_usable_extrusion_fields tests/test_admin_planning.py tests/test_admin_routes.py::test_successful_release_redirects_to_planning_anchor_and_refresh_does_not_resubmit tests/test_admin_routes.py::test_failed_release_and_planning_still_render_inline_without_redirect tests/test_recipe_release_validation.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Run all tests once and fix remaining fixture fallout only**

Run:

```bash
source .venv/bin/activate && python -m pytest -q
```

Expected after fixture cleanup:

```text
passed
```

If failures remain, only update tests/data that expected release to succeed with legacy unstructured recipe text. Do not loosen the Step 5 validator.

## Task 5: Update Milestone Tracker

**Files:**

- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update structured recipe follow-up**

In the “Structured recipe redesign follow-up” section, add this bullet after Step 4:

```markdown
- OI-003 Step 5 complete: release now blocks malformed structured recipe rows, category/material/percent rule failures, recipe totals other than exactly 100%, and missing/zero/invalid target gross weight while keeping import/admin draft correction permissive.
```

- [ ] **Step 2: Keep non-scope explicit**

Do not add any wording that claims Step 6 display redesign, print changes, or Excel macro/export validation are complete.

## Task 6: Final Verification

**Files:**

- No code edits in this task.

- [ ] **Step 1: Run syntax/import checks**

Run:

```bash
source .venv/bin/activate && python -m compileall app
```

Expected:

```text
Listing 'app'...
```

No syntax errors.

- [ ] **Step 2: Run focused structured recipe and release tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_parser.py tests/test_recipe_storage.py tests/test_recipe_sync.py tests/test_recipe_release_validation.py tests/test_admin_planning.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Run the full Python suite**

Run:

```bash
source .venv/bin/activate && python -m pytest
```

Expected:

```text
passed
```

- [ ] **Step 4: Run whitespace diff check**

Run:

```bash
git diff --check
```

Expected: no output and exit code `0`.

- [ ] **Step 5: Manual backend workflow check**

Use a temporary database only. Do not mutate `data/extrusion_terminal.sqlite3`.

Run this focused script from the shell:

```bash
source .venv/bin/activate && python - <<'PY'
import csv
import io
from pathlib import Path
from uuid import uuid4

from app import db
from app.importer import IMPORT_FIELDS, import_cards_from_csv

tmp_dir = Path(".test-runtime") / f"step5-release-gate-{uuid4().hex}"
tmp_dir.mkdir(parents=True, exist_ok=True)
db.DATA_DIR = tmp_dir
db.DB_PATH = tmp_dir / "extrusion_terminal.sqlite3"
db.init_db()

def csv_bytes(row):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")

base = {
    "order_number": "STEP5-MANUAL-1",
    "customer": "Manual Step 5",
    "product_type": "PE film",
    "quantity_1": "1000",
    "unit_1": "kg",
    "material": "LDPE",
    "size_thickness": "600/0.050",
    "extrusion_flag": "da",
    "raw_material_a": "LDPE Manual A | 80%",
    "linear_pe": "LLDPE Manual L | 19%",
    "packaging_method": "rolls",
}

result = import_cards_from_csv("manual-invalid.csv", csv_bytes(base), overwrite_existing=False)
assert result.rows_imported == 1
with db.connect() as connection:
    card_id = int(connection.execute("SELECT id FROM cards WHERE order_number = ?", ("STEP5-MANUAL-1",)).fetchone()["id"])

blocked = db.release_card(card_id, machine_id=1, machine_sequence=1)
print("blocked:", blocked.ok, blocked.messages)
assert not blocked.ok

fields = {field: str(db.fetch_admin_card_detail(card_id)[field] or "") for field in IMPORT_FIELDS}
fields["linear_pe"] = "LLDPE Manual L | 20%"
saved = db.update_admin_imported_fields(card_id, db.fetch_admin_card_detail(card_id)["version"], fields)
assert saved.ok

released = db.release_card(card_id, machine_id=1, machine_sequence=1)
print("released:", released.ok, released.messages)
assert released.ok

print(db.DB_PATH)
PY
```

Expected output includes:

```text
blocked: False
released: True
```

- [ ] **Step 6: Review changed code**

Review:

```bash
git diff -- app/rules.py app/db.py tests/test_recipe_release_validation.py tests/test_recipe_sync.py IMPLEMENTATION_PLAN.md
```

Check specifically:

- all release-gate checks happen before the release `UPDATE cards`;
- stale version still returns only the stale version message;
- invalid release leaves `status`, `machine_id`, and `machine_sequence` unchanged;
- import/admin draft correction remains permissive;
- no display, print, Excel macro, costing, inventory, ERP, or material catalog changes were introduced.
