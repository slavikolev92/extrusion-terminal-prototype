# Structured Recipe Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchronize normalized `recipe_components` rows from the imported recipe source fields whenever cards are imported, overwrite re-imported, or corrected by admin, while preserving original source fields and production-entered material/batch data.

**Architecture:** Keep `cards.raw_material_a` through `cards.chalk` as the authoritative source text for import, print, and legacy displays. Add a small workflow-sync helper in `app/db.py` that uses the Step 3 parser/storage helpers to replace derived `recipe_components` rows from current source fields without blocking saves on parser errors; release validation remains Step 5. Call that helper inside the existing CSV import, overwrite re-import, admin imported-field correction, and admin material-ledger source-correction transactions.

**Tech Stack:** Python 3, FastAPI, direct `sqlite3`, SQLite transactions, existing `app.recipe_parser`, existing Step 3 `recipe_components` helpers, pytest.

---

## Repository Rules For Execution

- Work in `/home/sk/projects/extrusion-terminal` on branch `structured-recipe-redesign`.
- Follow `AGENTS.md`; `README.md` is authoritative when repo docs conflict.
- Do not touch anything under `interim-costing-process/source-files/recipe-builder-demo/`.
- Do not change print output, Excel macro/export validation, release gates, terminal/admin recipe display, pricing, costing, inventory, ERP behavior, or material catalog behavior.
- Do not stage or commit unless the user explicitly asks. Ignore Superpowers examples that include commits.
- Use the repo-local virtualenv for verification.
- Tests must use temporary SQLite databases and must not mutate `data/extrusion_terminal.sqlite3`.

## Context Loaded Before This Plan

- `AGENTS.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `open-issues.md`
- `docs/implementation-notes/structured-recipe-contract.md`
- `docs/superpowers/plans/2026-06-24-structured-recipe-storage.md`
- `app/recipe_parser.py`
- `tests/test_recipe_parser.py`
- `app/db.py`
- `tests/test_recipe_storage.py`
- `app/importer.py`
- `app/main.py`
- focused tests around import overwrite, admin imported-field correction, admin material ledger, terminal material entries, print recipe rows, and terminal/admin render behavior

Exploration check run before writing this plan:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_parser.py tests/test_recipe_storage.py -q
```

Observed output:

```text
30 passed in 0.68s
```

## Current Step 3 State To Preserve

- `app.recipe_parser.RECIPE_SOURCE_FIELDS` defines the seven recipe source fields in workbook order:
  - `raw_material_a`
  - `raw_material_b`
  - `raw_material_c`
  - `linear_pe`
  - `antistatic`
  - `masterbatch`
  - `chalk`
- `app.db.recipe_components` stores derived rows only.
- `app.db.replace_recipe_components_for_card(connection, card_id, components)` deletes and replaces derived rows for one card.
- `app.db.parse_and_replace_recipe_components_for_card(connection, card_id, source_fields)` only replaces rows when the full parser result is valid. Keep that behavior; it is useful as a strict storage helper test surface.
- `app.db.fetch_recipe_components(connection, card_id)` returns derived rows in parser source-field order.
- `recipe_actual_entries` stores actual material/batch production data and must not be deleted or overwritten by Step 4 sync.
- Existing Step 3 tests intentionally assert import and release do not sync `recipe_components`. Step 4 must replace those guard tests because sync is now the point of the slice.

## Step 4 Scope

Implement OI-003 Step 4 only:

- Refresh normalized recipe rows on CSV import.
- Refresh normalized recipe rows on overwrite re-import.
- Refresh normalized recipe rows on admin source recipe correction.
- Empty source cells remove derived rows.
- Changed source cells update derived rows.
- Preserve existing actual material and batch/lot production data.
- Preserve original source fields on `cards`.
- Preserve print output based on original source fields.
- Parser errors must not block import or admin save in Step 4. Release validation belongs to Step 5.

## Explicit Non-Scope

Do not implement these:

- Step 5 release gates.
- Step 6 terminal/admin recipe display redesign.
- Print output changes.
- Excel macro/export validation changes.
- Changes to `source-files/excel-macros/ExportExtrusionOrders.bas`.
- Changes under `interim-costing-process/source-files/recipe-builder-demo/`.
- Pricing, costing, inventory, ERP behavior, or material catalog management.
- Any UI redesign or Playwright screenshot requirement for this backend-only sync slice.

## Files To Modify Or Create

- Modify: `app/db.py`
  - Add a permissive sync helper that uses Step 3 parser/storage primitives.
  - Call it from `_update_admin_imported_fields()` after the source-field `cards` update succeeds.
  - Call it from `_update_admin_material_ledger()` after planned recipe source fields are updated.
- Modify: `app/importer.py`
  - Call the sync helper after new card insert.
  - Call the sync helper after overwrite re-import update.
  - Keep duplicate skip, stale-overwrite blocking, no-extrusion skip, and production-data preservation unchanged.
- Modify: `tests/test_recipe_storage.py`
  - Remove or replace the two Step 3 boundary tests:
    - `test_import_does_not_auto_create_recipe_components_in_step_3`
    - `test_release_does_not_validate_or_sync_recipe_components_in_step_3`
  - Keep strict helper tests for `parse_and_replace_recipe_components_for_card()`.
- Create: `tests/test_recipe_sync.py`
  - Focused Step 4 import/admin sync and boundary tests.
- Modify: `IMPLEMENTATION_PLAN.md`
  - Update the structured recipe follow-up note to mark Step 4 in progress or complete after implementation.

Files that should not change:

- `app/templates/**`
- `app/printing.py`
- `source-files/excel-macros/**`
- `interim-costing-process/source-files/recipe-builder-demo/**`
- print-output tests unless a boundary assertion is intentionally added there

## Design Details

### Permissive Sync Helper

Add this helper in `app/db.py` near the existing Step 3 recipe helpers:

```python
def recipe_source_fields_from_mapping(source: dict[str, Any]) -> dict[str, str | None]:
    return {field: source.get(field) for field in RECIPE_SOURCE_FIELDS}


def sync_recipe_components_for_card(
    connection: sqlite3.Connection,
    card_id: int,
    source_fields: dict[str, Any],
) -> RecipeParseResult:
    result = parse_recipe_source_fields(recipe_source_fields_from_mapping(source_fields))
    replace_recipe_components_for_card(connection, card_id, result.components)
    return result
```

Important behavior:

- This helper deliberately differs from `parse_and_replace_recipe_components_for_card()`.
- It always replaces derived rows with successfully parsed components from current source text, even when `result.ok` is false.
- Empty source cells produce no component and therefore remove stale derived rows.
- Malformed source cells produce no component and therefore remove stale derived rows for that field.
- Total-percent mismatch does not block import/admin save and does not prevent the valid parsed rows from being stored.
- The returned `RecipeParseResult` is available for future release validation or diagnostics, but Step 4 callers must not convert parser errors into blocking import/admin messages.
- The helper must not modify `cards`, `card_import_sources`, `recipe_actual_entries`, roll entries, timing segments, status, machine assignment, or version by itself.

### Transaction Placement

- In `app/importer.py`, call `sync_recipe_components_for_card()` inside the existing `with connect() as connection:` transaction.
- In `insert_imported_card()`, call sync after `upsert_card_import_source()`, using the same `card` dict and `cursor.lastrowid`.
- In `update_imported_card_fields()`, call sync after `upsert_card_import_source()`, using the same incoming `card` dict.
- In `app/db.py::_update_admin_imported_fields()`, call sync after the successful `UPDATE cards` and roll-order-number maintenance.
- In `app/db.py::_update_admin_material_ledger()`, call sync after the successful planned recipe source field `UPDATE cards`. This admin route edits `raw_material_a` through `chalk`, so it is a source recipe correction surface.
- Keep stale-version checks before any source field update or sync.
- If any later operation in a compound admin save fails and the connection rolls back, the recipe sync must roll back with it.

## Task 1: Replace Step 3 Non-Sync Guards With Step 4 Failing Tests

**Files:**

- Create: `tests/test_recipe_sync.py`
- Modify: `tests/test_recipe_storage.py`

- [ ] **Step 1: Create `tests/test_recipe_sync.py` with shared fixtures**

Add this file:

```python
from __future__ import annotations

import csv
import io

from app import db
from app.constants import STATUS_PENDING
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import admin_card_detail_context, terminal_context
from app.printing import build_recipe_rows as build_print_recipe_rows


def csv_bytes(*rows: dict[str, str]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")


def structured_row(order_number: str, **overrides: str) -> dict[str, str]:
    row = {
        "order_number": order_number,
        "order_date": "2026-06-25",
        "delivery_date": "2026-06-30",
        "customer": "Structured Recipe Sync Customer",
        "city": "Sofia",
        "product_type": "PE film",
        "quantity_1": "1000",
        "unit_1": "kg",
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


def import_card(order_number: str, **overrides: str) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(structured_row(order_number, **overrides)),
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


def current_import_fields(card_id: int) -> dict[str, str]:
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    return {field: str(card[field] or "") for field in IMPORT_FIELDS}


def component_summary(connection, card_id: int) -> list[tuple[str, str, str, str]]:
    return [
        (
            row["component_key"],
            row["source_text"],
            row["material_category"],
            row["planned_material"],
        )
        for row in db.fetch_recipe_components(connection, card_id)
    ]


def actual_entry(connection, card_id: int, component_key: str = "raw_material_a"):
    return connection.execute(
        """
        SELECT planned_material, actual_material_used, batch_lot
        FROM recipe_actual_entries
        WHERE card_id = ?
          AND component_key = ?
        """,
        (card_id, component_key),
    ).fetchone()
```

- [ ] **Step 2: Add failing CSV import sync test**

Append:

```python
def test_csv_import_creates_normalized_recipe_components(connection):
    result = import_cards_from_csv(
        "structured-import.csv",
        csv_bytes(
            structured_row(
                "RS-SYNC-001",
                raw_material_a="LDPE Rompetrol Midilena B20/03 | 77%",
                linear_pe="LLDPE SABIC 119ZJ | 18%",
                antistatic="Antistatic Novachem AT 04673 LD | 2%",
                masterbatch="Masterbatch Polibach White 8000 ET | 3%",
            )
        ),
        overwrite_existing=False,
    )
    card = connection.execute(
        """
        SELECT id, raw_material_a, linear_pe, antistatic, masterbatch
        FROM cards
        WHERE order_number = 'RS-SYNC-001'
        """
    ).fetchone()

    assert result.created == 1
    assert card["raw_material_a"] == "LDPE Rompetrol Midilena B20/03 | 77%"
    assert component_summary(connection, int(card["id"])) == [
        (
            "raw_material_a",
            "LDPE Rompetrol Midilena B20/03 | 77%",
            "LDPE",
            "Rompetrol Midilena B20/03",
        ),
        ("linear_pe", "LLDPE SABIC 119ZJ | 18%", "LLDPE", "SABIC 119ZJ"),
        (
            "antistatic",
            "Antistatic Novachem AT 04673 LD | 2%",
            "Antistatic",
            "Novachem AT 04673 LD",
        ),
        (
            "masterbatch",
            "Masterbatch Polibach White 8000 ET | 3%",
            "Masterbatch",
            "Polibach White 8000 ET",
        ),
    ]
```

- [ ] **Step 3: Run the new test and verify it fails**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py::test_csv_import_creates_normalized_recipe_components -q
```

Expected:

```text
FAILED tests/test_recipe_sync.py::test_csv_import_creates_normalized_recipe_components
```

The failure should show `component_summary(...) == []` or an `AttributeError` for the missing sync helper.

- [ ] **Step 4: Remove the two obsolete Step 3 guard tests**

In `tests/test_recipe_storage.py`, delete these functions:

```python
def test_import_does_not_auto_create_recipe_components_in_step_3(connection):
    ...


def test_release_does_not_validate_or_sync_recipe_components_in_step_3(connection):
    ...
```

Do not remove the strict helper test:

```python
def test_parse_and_replace_recipe_components_for_card_does_not_mutate_on_parse_error(connection):
    ...
```

That strict helper behavior remains valid.

## Task 2: Implement Minimal Import Sync

**Files:**

- Modify: `app/db.py`
- Modify: `app/importer.py`
- Test: `tests/test_recipe_sync.py`

- [ ] **Step 1: Add the permissive sync helper in `app/db.py`**

Add this code near `parse_and_replace_recipe_components_for_card()`:

```python
def recipe_source_fields_from_mapping(source: dict[str, Any]) -> dict[str, str | None]:
    return {field: source.get(field) for field in RECIPE_SOURCE_FIELDS}


def sync_recipe_components_for_card(
    connection: sqlite3.Connection,
    card_id: int,
    source_fields: dict[str, Any],
) -> RecipeParseResult:
    result = parse_recipe_source_fields(recipe_source_fields_from_mapping(source_fields))
    replace_recipe_components_for_card(connection, card_id, result.components)
    return result
```

- [ ] **Step 2: Wire new-card import in `app/importer.py`**

Change the import at the top from:

```python
from .db import connect, insert_import_batch_row
```

to:

```python
from .db import connect, insert_import_batch_row, sync_recipe_components_for_card
```

Then update `insert_imported_card()`:

```python
def insert_imported_card(connection, batch_id: int, card: dict[str, str]) -> None:
    columns = (
        "import_batch_id",
        "status",
        *IMPORT_FIELDS,
    )
    values = [
        batch_id,
        STATUS_IMPORTED,
        *(card[field] for field in IMPORT_FIELDS),
    ]
    placeholders = ", ".join("?" for _ in columns)

    cursor = connection.execute(
        f"""
        INSERT INTO cards ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        values,
    )
    card_id = int(cursor.lastrowid)
    upsert_card_import_source(connection, card_id, batch_id, card)
    sync_recipe_components_for_card(connection, card_id, card)
```

- [ ] **Step 3: Run the import sync test**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py::test_csv_import_creates_normalized_recipe_components -q
```

Expected:

```text
1 passed
```

## Task 3: Add Overwrite Re-Import Sync Tests

**Files:**

- Modify: `tests/test_recipe_sync.py`
- Modify later: `app/importer.py`

- [ ] **Step 1: Add failing overwrite refresh and preservation test**

Append:

```python
def test_overwrite_reimport_refreshes_components_and_preserves_actual_entries(connection):
    card_id = import_card("RS-SYNC-002")
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        loaded_version,
        {
            "raw_material_a": {
                "actual_material_used": "Actual LDPE",
                "batch_lot": "Batch A",
            },
            "linear_pe": {
                "actual_material_used": "Actual LLDPE",
                "batch_lot": "Batch L",
            },
        },
    ).ok

    result = import_cards_from_csv(
        "structured-overwrite.csv",
        csv_bytes(
            structured_row(
                "RS-SYNC-002",
                raw_material_a="LDPE New Source | 70%",
                raw_material_b="LLDPE Added Source | 30%",
                linear_pe="",
            )
        ),
        overwrite_existing=True,
    )

    card = db.fetch_admin_card_detail(card_id)
    assert result.updated == 1
    assert card["raw_material_a"] == "LDPE New Source | 70%"
    assert card["raw_material_b"] == "LLDPE Added Source | 30%"
    assert card["linear_pe"] == ""
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE New Source | 70%", "LDPE", "New Source"),
        ("raw_material_b", "LLDPE Added Source | 30%", "LLDPE", "Added Source"),
    ]
    assert dict(actual_entry(connection, card_id, "raw_material_a")) == {
        "planned_material": "LDPE Rompetrol B20/03 | 80%",
        "actual_material_used": "Actual LDPE",
        "batch_lot": "Batch A",
    }
    assert dict(actual_entry(connection, card_id, "linear_pe")) == {
        "planned_material": "LLDPE SABIC 119ZJ | 20%",
        "actual_material_used": "Actual LLDPE",
        "batch_lot": "Batch L",
    }
```

This test proves:

- overwrite re-import updates derived rows;
- empty `linear_pe` removes its derived row;
- changed source cells update derived rows;
- original source fields on `cards` still store the exact imported strings;
- `recipe_actual_entries` is preserved.

- [ ] **Step 2: Add duplicate skip leaves components unchanged test**

Append:

```python
def test_duplicate_skip_does_not_refresh_recipe_components(connection):
    card_id = import_card("RS-SYNC-003")

    result = import_cards_from_csv(
        "structured-duplicate-skip.csv",
        csv_bytes(
            structured_row(
                "RS-SYNC-003",
                raw_material_a="LDPE Should Not Apply | 100%",
                linear_pe="",
            )
        ),
        overwrite_existing=False,
    )

    assert result.rows_imported == 0
    assert result.skipped == 1
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Rompetrol B20/03 | 80%", "LDPE", "Rompetrol B20/03"),
        ("linear_pe", "LLDPE SABIC 119ZJ | 20%", "LLDPE", "SABIC 119ZJ"),
    ]
```

- [ ] **Step 3: Add parser-error permissiveness test for import**

Append:

```python
def test_import_sync_does_not_block_parser_errors_or_add_release_gate(connection):
    result = import_cards_from_csv(
        "structured-invalid-total.csv",
        csv_bytes(
            structured_row(
                "RS-SYNC-004",
                raw_material_a="LDPE Rompetrol B20/03 | 80%",
                linear_pe="LLDPE SABIC 119ZJ | 19%",
            )
        ),
        overwrite_existing=False,
    )
    card_id = int(
        connection.execute(
            "SELECT id FROM cards WHERE order_number = 'RS-SYNC-004'"
        ).fetchone()["id"]
    )

    assert result.created == 1
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Rompetrol B20/03 | 80%", "LDPE", "Rompetrol B20/03"),
        ("linear_pe", "LLDPE SABIC 119ZJ | 19%", "LLDPE", "SABIC 119ZJ"),
    ]

    release_result = db.release_card(card_id, machine_id=1, machine_sequence=1)
    released = db.fetch_admin_card_detail(card_id)

    assert release_result.ok
    assert released["status"] == STATUS_PENDING
```

This is the Step 5 boundary test. It must pass in Step 4 because release gates are not in scope.

- [ ] **Step 4: Run the new tests and verify overwrite sync fails**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py -q
```

Expected before implementation:

```text
FAILED tests/test_recipe_sync.py::test_overwrite_reimport_refreshes_components_and_preserves_actual_entries
```

Other tests may pass after Task 2. The overwrite test should fail because `update_imported_card_fields()` is not wired yet.

## Task 4: Implement Overwrite Re-Import Sync

**Files:**

- Modify: `app/importer.py`
- Test: `tests/test_recipe_sync.py`

- [ ] **Step 1: Wire overwrite sync in `update_imported_card_fields()`**

Change `update_imported_card_fields()` to call sync after source-baseline upsert:

```python
def update_imported_card_fields(connection, card_id: int, batch_id: int, card: dict[str, str]) -> None:
    assignments = [
        "import_batch_id = ?",
        *(f"{field} = ?" for field in IMPORT_FIELDS),
        "version = version + 1",
        "updated_at = CURRENT_TIMESTAMP",
    ]
    values = [
        batch_id,
        *(card[field] for field in IMPORT_FIELDS),
        card_id,
    ]

    connection.execute(
        f"""
        UPDATE cards
        SET {", ".join(assignments)}
        WHERE id = ?
        """,
        values,
    )
    upsert_card_import_source(connection, card_id, batch_id, card)
    sync_recipe_components_for_card(connection, card_id, card)
```

- [ ] **Step 2: Run sync tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py -q
```

Expected:

```text
all tests in tests/test_recipe_sync.py pass
```

- [ ] **Step 3: Run focused baseline overwrite tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_baseline.py -k "overwrite_import or duplicate_import" -q
```

Expected:

```text
all selected tests pass
```

## Task 5: Add Admin Imported-Field Sync Tests

**Files:**

- Modify: `tests/test_recipe_sync.py`
- Modify later: `app/db.py`

- [ ] **Step 1: Add admin imported-field correction sync test**

Append:

```python
def test_admin_imported_field_correction_refreshes_recipe_components(connection):
    card_id = import_card("RS-SYNC-005")
    card = db.fetch_admin_card_detail(card_id)
    fields = current_import_fields(card_id)
    fields["raw_material_a"] = "LDPE Admin Corrected | 100%"
    fields["linear_pe"] = ""

    result = db.update_admin_imported_fields(card_id, card["version"], fields)

    assert result.ok
    updated = db.fetch_admin_card_detail(card_id)
    assert updated["raw_material_a"] == "LDPE Admin Corrected | 100%"
    assert updated["linear_pe"] == ""
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Admin Corrected | 100%", "LDPE", "Admin Corrected"),
    ]
```

- [ ] **Step 2: Add admin imported-field parser-error permissiveness test**

Append:

```python
def test_admin_imported_field_correction_does_not_block_parser_errors(connection):
    card_id = import_card("RS-SYNC-006")
    card = db.fetch_admin_card_detail(card_id)
    fields = current_import_fields(card_id)
    fields["raw_material_a"] = "LDPE Admin Invalid Total | 80%"
    fields["linear_pe"] = "LLDPE Admin Invalid Total | 19%"

    result = db.update_admin_imported_fields(card_id, card["version"], fields)

    assert result.ok
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Admin Invalid Total | 80%", "LDPE", "Admin Invalid Total"),
        ("linear_pe", "LLDPE Admin Invalid Total | 19%", "LLDPE", "Admin Invalid Total"),
    ]
```

- [ ] **Step 3: Add stale admin correction boundary test**

Append:

```python
def test_stale_admin_imported_field_correction_does_not_refresh_components(connection):
    card_id = import_card("RS-SYNC-007")
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]
    fields = current_import_fields(card_id)
    fields["customer"] = "First admin save"
    assert db.update_admin_imported_fields(card_id, loaded_version, fields).ok

    stale_fields = current_import_fields(card_id)
    stale_fields["raw_material_a"] = "LDPE Stale Source | 100%"
    stale_fields["linear_pe"] = ""
    stale_result = db.update_admin_imported_fields(
        card_id,
        loaded_version,
        stale_fields,
    )

    assert not stale_result.ok
    assert stale_result.messages == (db.STALE_CARD_MESSAGE,)
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Rompetrol B20/03 | 80%", "LDPE", "Rompetrol B20/03"),
        ("linear_pe", "LLDPE SABIC 119ZJ | 20%", "LLDPE", "SABIC 119ZJ"),
    ]
```

- [ ] **Step 4: Run the admin imported-field tests and verify they fail**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py -k "admin_imported_field or stale_admin" -q
```

Expected before implementation:

```text
FAILED tests/test_recipe_sync.py::test_admin_imported_field_correction_refreshes_recipe_components
FAILED tests/test_recipe_sync.py::test_admin_imported_field_correction_does_not_block_parser_errors
```

The stale test may pass already because stale writes are blocked before source updates.

## Task 6: Implement Admin Imported-Field Sync

**Files:**

- Modify: `app/db.py`
- Test: `tests/test_recipe_sync.py`

- [ ] **Step 1: Wire sync in `_update_admin_imported_fields()`**

Inside `_update_admin_imported_fields()`, after the successful `UPDATE cards` and order-number roll update block, add:

```python
        sync_recipe_components_for_card(connection, card_id, cleaned_fields)
```

The end of the `try` block should look like:

```python
    try:
        connection.execute(
            f"""
            UPDATE cards
            SET {", ".join(assignments)}
            WHERE id = ?
            """,
            values,
        )
        if cleaned_fields["order_number"] != card["order_number"]:
            connection.execute(
                """
                UPDATE roll_entries
                SET order_number = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE card_id = ?
                """,
                (cleaned_fields["order_number"], card_id),
            )
        sync_recipe_components_for_card(connection, card_id, cleaned_fields)
    except sqlite3.IntegrityError:
        connection.rollback()
        return RuleResult(False, ("Номерът на поръчката вече съществува в друга карта.",))
```

- [ ] **Step 2: Run admin imported-field sync tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py -k "admin_imported_field or stale_admin" -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 3: Run existing admin imported-field tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_admin_card_review.py tests/test_admin_routes.py -k "imported_field or stale" -q
```

Expected:

```text
all selected tests pass
```

## Task 7: Add Admin Material-Ledger Source Sync Tests

**Files:**

- Modify: `tests/test_recipe_sync.py`
- Modify later: `app/db.py`

- [ ] **Step 1: Add material-ledger source correction sync test**

Append:

```python
def test_admin_material_ledger_refreshes_components_without_touching_actual_values(connection):
    card_id = import_card("RS-SYNC-008")
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]

    result = db.update_admin_material_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        planned_materials={
            "raw_material_a": "LDPE Ledger Corrected | 60%",
            "raw_material_b": "LLDPE Ledger Added | 40%",
            "raw_material_c": "",
            "linear_pe": "",
            "antistatic": "",
            "masterbatch": "",
            "chalk": "",
        },
        actual_entries={
            "raw_material_a": {
                "actual_material_used": "Actual Ledger A",
                "batch_lot": "Ledger Batch A",
            },
            "raw_material_b": {
                "actual_material_used": "Actual Ledger B",
                "batch_lot": "Ledger Batch B",
            },
        },
    )

    assert result.ok
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Ledger Corrected | 60%", "LDPE", "Ledger Corrected"),
        ("raw_material_b", "LLDPE Ledger Added | 40%", "LLDPE", "Ledger Added"),
    ]
    assert dict(actual_entry(connection, card_id, "raw_material_a")) == {
        "planned_material": "LDPE Ledger Corrected | 60%",
        "actual_material_used": "Actual Ledger A",
        "batch_lot": "Ledger Batch A",
    }
    assert dict(actual_entry(connection, card_id, "raw_material_b")) == {
        "planned_material": "LLDPE Ledger Added | 40%",
        "actual_material_used": "Actual Ledger B",
        "batch_lot": "Ledger Batch B",
    }
```

- [ ] **Step 2: Add material-ledger parser-error permissiveness test**

Append:

```python
def test_admin_material_ledger_does_not_block_parser_errors(connection):
    card_id = import_card("RS-SYNC-009")
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]

    result = db.update_admin_material_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        planned_materials={
            "raw_material_a": "LDPE Ledger Invalid Total | 80%",
            "linear_pe": "LLDPE Ledger Invalid Total | 19%",
        },
        actual_entries={},
    )

    assert result.ok
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "LDPE Ledger Invalid Total | 80%", "LDPE", "Ledger Invalid Total"),
        ("linear_pe", "LLDPE Ledger Invalid Total | 19%", "LLDPE", "Ledger Invalid Total"),
    ]
```

- [ ] **Step 3: Run material-ledger tests and verify they fail**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py -k "material_ledger" -q
```

Expected before implementation:

```text
FAILED tests/test_recipe_sync.py::test_admin_material_ledger_refreshes_components_without_touching_actual_values
FAILED tests/test_recipe_sync.py::test_admin_material_ledger_does_not_block_parser_errors
```

## Task 8: Implement Admin Material-Ledger Source Sync

**Files:**

- Modify: `app/db.py`
- Test: `tests/test_recipe_sync.py`

- [ ] **Step 1: Wire sync in `_update_admin_material_ledger()`**

Inside `_update_admin_material_ledger()`, after the `UPDATE cards` statement and before or after the `recipe_actual_entries` upserts, add:

```python
    sync_recipe_components_for_card(connection, card_id, cleaned_planned)
```

Preferred placement is immediately after the `UPDATE cards` statement, before the loop that upserts `recipe_actual_entries`, so source-derived sync is visibly separate from production actual-entry persistence.

- [ ] **Step 2: Run material-ledger tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py -k "material_ledger" -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 3: Run existing admin material ledger tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_admin_card_detail_redesign.py -k "material_ledger" -q
```

Expected:

```text
all selected tests pass
```

## Task 9: Add Boundary Tests For No UI, Print, Excel, Or Release-Gate Scope

**Files:**

- Modify: `tests/test_recipe_sync.py`

- [ ] **Step 1: Add admin/terminal display boundary test**

Append:

```python
def test_step_4_keeps_admin_and_terminal_recipe_display_on_original_source_text(connection):
    card_id = import_card(
        "RS-SYNC-010",
        raw_material_a="LDPE Display Source | 80%",
        linear_pe="LLDPE Display Source | 20%",
    )
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok

    admin_context = admin_card_detail_context(card_id)
    terminal = terminal_context(selected_card_id=card_id)

    assert admin_context is not None
    admin_rows = {row["field"]: row for row in admin_context["recipe_rows"]}
    terminal_rows = {row["field"]: row for row in terminal["recipe_rows"]}
    assert admin_rows["raw_material_a"]["planned"] == "LDPE Display Source | 80%"
    assert terminal_rows["raw_material_a"]["planned"] == "LDPE Display Source | 80%"
    assert "material_category" not in admin_rows["raw_material_a"]
    assert "recipe_percent" not in terminal_rows["raw_material_a"]
```

This proves Step 6 structured UI columns were not introduced in Step 4.

- [ ] **Step 2: Add print boundary test**

Append:

```python
def test_step_4_keeps_print_recipe_rows_on_original_source_text(connection):
    card_id = import_card(
        "RS-SYNC-011",
        raw_material_a="LDPE Print Source | 80%",
        linear_pe="LLDPE Print Source | 20%",
    )
    card = db.fetch_admin_card_detail(card_id)

    rows = build_print_recipe_rows(card, card["recipe_actual_entries"])
    by_key = {row["component_key"]: row for row in rows}

    assert by_key["raw_material_a"]["planned_material"] == "LDPE Print Source | 80%"
    assert by_key["linear_pe"]["planned_material"] == "LLDPE Print Source | 20%"
```

This proves print output is still built from `cards` source fields.

- [ ] **Step 3: Add malformed-release boundary test if it was not added in Task 3**

If `test_import_sync_does_not_block_parser_errors_or_add_release_gate()` exists from Task 3, do not duplicate it. If it was skipped, add it now exactly as written in Task 3.

- [ ] **Step 4: Add Excel and interim file boundary verification to the final checklist**

Do not write a Python test that reads or asserts macro internals. Use final `git diff --name-only` verification to prove these files are untouched:

```text
source-files/excel-macros/ExportExtrusionOrders.bas
source-files/excel-macros/README.md
interim-costing-process/source-files/recipe-builder-demo/
```

- [ ] **Step 5: Run all sync boundary tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py -q
```

Expected:

```text
all tests in tests/test_recipe_sync.py pass
```

## Task 10: Update Milestone Tracker

**Files:**

- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update the structured recipe redesign follow-up note**

Find the existing `Structured recipe redesign follow-up:` section and change it to this content after implementation is passing:

```markdown
Structured recipe redesign follow-up:

- OI-003 Step 2 complete: central parser committed in `0de3d33`.
- OI-003 Step 3 complete: normalized recipe-component SQLite storage and backend helpers only; focused storage tests pass.
- OI-003 Step 4 complete: normalized recipe rows now sync from CSV import, overwrite re-import, and admin source recipe corrections while preserving original card source fields and production actual material/batch data.
- Step 4 deliberately does not add release gates, terminal/admin recipe display redesign, print changes, or Excel macro/export validation; those remain later OI-003 steps.
```

If implementation is paused before completion, use this wording instead:

```markdown
- OI-003 Step 4 in progress: syncing normalized recipe rows from CSV import, overwrite re-import, and admin source recipe corrections.
```

- [ ] **Step 2: Inspect only the tracker diff**

Run:

```bash
git diff -- IMPLEMENTATION_PLAN.md
```

Expected:

- The note is concise.
- It does not claim Step 5, Step 6, print, or Excel validation work is complete.
- It does not mention pricing, costing, inventory, ERP, or material catalog work.

## Task 11: Focused Verification

**Files:**

- No edits unless verification exposes a concrete defect.

- [ ] **Step 1: Run parser and storage tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_parser.py tests/test_recipe_storage.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run new sync tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Run focused importer/admin tests identified during exploration**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_baseline.py tests/test_admin_card_review.py tests/test_admin_card_detail_redesign.py tests/test_admin_routes.py -k "overwrite_import or duplicate_import or imported_field or material_ledger or stale" -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 4: Run relevant terminal/print preservation tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_detail.py tests/test_print_output.py -k "recipe_actual_entries or recipe" -q
```

Expected:

```text
all selected tests pass
```

## Task 12: Final Verification

**Files:**

- No edits unless verification exposes a concrete defect.

- [ ] **Step 1: Run required focused parser/storage command**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_parser.py tests/test_recipe_storage.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run focused importer/admin tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py tests/test_baseline.py tests/test_admin_card_review.py tests/test_admin_card_detail_redesign.py tests/test_admin_routes.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Run the full Python suite**

Run:

```bash
source .venv/bin/activate && python -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 4: Run syntax/import checks**

Run:

```bash
source .venv/bin/activate && python -m compileall app
```

Expected:

```text
no compile errors
```

- [ ] **Step 5: Run whitespace check**

Run:

```bash
git diff --check
```

Expected:

```text
no output
```

- [ ] **Step 6: Inspect worktree status**

Run:

```bash
git status --short
```

Expected allowed changed files from Step 4 implementation:

```text
M IMPLEMENTATION_PLAN.md
M app/db.py
M app/importer.py
?? tests/test_recipe_sync.py
```

Because this branch already had uncommitted Step 3 work when this plan was written, these pre-existing entries may also appear and must not be reverted:

```text
?? tests/test_recipe_storage.py
?? docs/superpowers/plans/2026-06-24-structured-recipe-storage.md
?? interim-costing-process/source-files/recipe-builder-demo/
```

Do not stage, delete, or modify those unrelated paths unless the user explicitly asks.

- [ ] **Step 7: Inspect changed file list**

Run:

```bash
git diff --name-only
```

Expected allowed implementation files:

```text
IMPLEMENTATION_PLAN.md
app/db.py
app/importer.py
```

`git diff --name-only` does not list untracked files. Confirm untracked test files with `git status --short`, including `tests/test_recipe_sync.py` and the pre-existing `tests/test_recipe_storage.py`.

These paths must not appear:

```text
app/templates/
app/printing.py
source-files/excel-macros/
interim-costing-process/source-files/recipe-builder-demo/
```

## Self-Review Checklist

Before reporting Step 4 complete, verify each item:

- OI-003 Step 4 is covered: CSV import sync, overwrite re-import sync, admin source correction sync.
- Empty source cells remove derived `recipe_components` rows.
- Changed source cells update derived rows.
- Parser errors do not block CSV import, overwrite re-import, or admin saves.
- Parser errors do not create a release gate in Step 4.
- Original source fields on `cards` are preserved exactly and remain the print/display source.
- `recipe_actual_entries` is preserved by import and overwrite re-import.
- Step 4 sync code does not delete or overwrite production actual material/batch rows.
- Existing stale-version checks still block stale admin writes before sync.
- Duplicate import skip does not refresh derived rows.
- Stale overwrite blocking does not refresh derived rows.
- `card_import_sources` behavior remains unchanged except that successful overwrite still updates the source baseline as before.
- No terminal/admin structured recipe display redesign was added.
- No print output behavior changed.
- No Excel macro/export validation changed.
- No files under `interim-costing-process/source-files/recipe-builder-demo/` changed.
- No pricing, costing, inventory, ERP, or material catalog behavior was added.
- No files are staged or committed unless the user explicitly asks.

## Known Uncertainty And How To Handle It

- `parse_and_replace_recipe_components_for_card()` currently refuses to replace rows when total percent is not exactly `100%`. Do not use it for Step 4 workflow sync, because Step 4 must not leave stale derived rows when source cells are empty, changed, malformed, or total-mismatched. Use `parse_recipe_source_fields()` plus `replace_recipe_components_for_card()` inside the new permissive sync helper.
- Exact pytest counts may change because this branch already had uncommitted Step 3 files before this plan was written. Treat "all tests pass" as the expected result rather than relying on a fixed count.
- This plan intentionally does not add user-visible parser warnings during import/admin save. If the user later wants warnings before release, that should be designed with Step 5 release validation, not slipped into Step 4.

## Completion Criteria

Step 4 is complete when:

- Successful CSV import creates normalized recipe rows for parseable source cells.
- Successful overwrite re-import refreshes normalized rows from incoming source fields.
- Duplicate-skip import leaves existing normalized rows unchanged.
- Stale overwrite blocking leaves existing normalized rows unchanged.
- Admin imported-field correction refreshes normalized rows after a valid version check.
- Admin material-ledger source correction refreshes normalized rows after a valid version check.
- Empty source fields clear stale derived rows for those fields.
- Parser errors do not block import/admin save and do not block release in Step 4.
- Actual material and batch/lot production data in `recipe_actual_entries` remains preserved.
- Original source fields remain stored on `cards`.
- Existing UI, print, Excel macro/export, and interim-costing files are untouched.
- Required focused and full verification commands pass.
