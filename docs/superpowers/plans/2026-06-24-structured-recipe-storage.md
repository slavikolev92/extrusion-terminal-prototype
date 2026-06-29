# Structured Recipe Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add normalized SQLite storage and backend helpers for parsed extrusion recipe components while preserving the original imported recipe source fields on `cards`.

**Architecture:** Keep `cards.raw_material_a` through `cards.chalk` as the source of truth for imported/printed recipe text. Add one thin derived table, `recipe_components`, that stores only parsed source-field components from `app.recipe_parser`: component key, original source text, canonical material category, planned material, and recipe percent. Step 3 provides schema, migration-safe initialization, explicit storage/fetch helpers, and tests only; it does not wire automatic synchronization into CSV import, overwrite re-import, admin correction, release gates, templates, print, or Excel export.

**Tech Stack:** Python 3, FastAPI app repository, direct `sqlite3`, SQLite constraints/indexes, existing pytest fixtures, existing `app.recipe_parser` dataclasses and constants.

---

## Repository Rules For Execution

- Work in `/home/sk/projects/extrusion-terminal` on branch `structured-recipe-redesign`.
- Follow `AGENTS.md`, `README.md`, `IMPLEMENTATION_PLAN.md`, `open-issues.md`, and `docs/implementation-notes/structured-recipe-contract.md`.
- Use the repo-local virtualenv for verification:

```bash
source .venv/bin/activate
python -m pytest
```

- Do not mutate `data/extrusion_terminal.sqlite3` in tests.
- Do not touch files under `interim-costing-process/source-files/recipe-builder-demo/`.
- Do not stage or commit unless the user explicitly asks. This overrides the generic Superpowers examples that mention committing after each task.
- No UI work is in scope for this step, so no Playwright screenshot is required for Step 3.

## Exact Scope

Implement Step 3 from `open-issues.md` OI-003:

- Keep original imported recipe source fields on `cards`.
- Add normalized recipe-component storage derived from those fields.
- Store:
  - `card_id`
  - source field/component key, such as `raw_material_a`
  - original source text
  - canonical material category
  - planned material
  - recipe percent
- Add backend/database helpers for replacing and fetching normalized rows.
- Add automated tests for schema, constraints, replacement/fetch behavior, parser-error behavior, preservation of `recipe_actual_entries`, and migration-safe initialization.
- Preserve the parser contract in `docs/implementation-notes/structured-recipe-contract.md`.

## Explicit Non-Scope

Do not implement these in Step 3:

- No automatic sync from CSV import in `app/importer.py`.
- No automatic sync during overwrite re-import.
- No automatic sync during admin source recipe correction in `update_admin_imported_fields()` or `update_admin_material_ledger()`.
- No release gate in `release_card()`.
- No terminal/admin template or route changes.
- No print-output changes.
- No Excel macro/export validation changes.
- No pricing, costing, inventory, ERP functionality, material catalog management, or work under `interim-costing-process/`.
- No staging or committing unless explicitly asked.

Step 3 stops after tested storage helpers exist. Step 4 owns calling those helpers from import/re-import/admin source correction paths. Step 5 owns release validation. Step 6 owns UI display changes.

## Files Likely To Change

- Modify: `app/db.py`
  - Add schema SQL for `recipe_components`.
  - Add an index for component lookup.
  - Add helper constants derived from `app.recipe_parser`.
  - Add explicit storage/fetch helpers.
  - Keep existing `recipe_actual_entries` behavior unchanged.
- Create: `tests/test_recipe_storage.py`
  - Focused storage tests using the existing temporary SQLite fixture.
- Modify: `IMPLEMENTATION_PLAN.md`
  - Add a short OI-003 Step 3 note only when the implementation begins or completes, per repository rules.

Files that should not change in Step 3:

- `app/importer.py`
- `app/main.py`
- `app/templates/**`
- `app/static/**`
- `tests/test_terminal_v8_render.py`
- Excel macro files
- print-output files
- anything under `interim-costing-process/source-files/recipe-builder-demo/`

## Schema Design

Add a new table separate from `recipe_actual_entries`:

```sql
CREATE TABLE IF NOT EXISTS recipe_components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    component_key TEXT NOT NULL CHECK (
        component_key IN (
            'raw_material_a',
            'raw_material_b',
            'raw_material_c',
            'linear_pe',
            'antistatic',
            'masterbatch',
            'chalk'
        )
    ),
    source_text TEXT NOT NULL,
    material_category TEXT NOT NULL CHECK (
        material_category IN (
            'LDPE',
            'LLDPE',
            'MDPE',
            'reLDPE',
            'Antistatic',
            'Masterbatch',
            'Filler',
            'UV',
            'Antislip'
        )
    ),
    planned_material TEXT NOT NULL,
    recipe_percent NUMERIC NOT NULL CHECK (recipe_percent > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (card_id, component_key)
);

CREATE INDEX IF NOT EXISTS idx_recipe_components_card
ON recipe_components(card_id);
```

Do not store planned kilograms in Step 3. Planned kilograms are derived later as `recipe_percent * target_gross_weight` in UI/export work.

Do not merge this data into `recipe_actual_entries`. That table stores actual material/batch production entries and must continue surviving re-imports and admin corrections independently.

## Migration And Backfill Considerations

`init_db()` already runs `connection.executescript(SCHEMA_SQL)` and uses idempotent `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` patterns. Adding `recipe_components` to `SCHEMA_SQL` is enough to create the table for new and existing SQLite databases.

Do not automatically backfill existing cards inside `init_db()` in Step 3. Existing databases may contain malformed recipe source text, and the roadmap deliberately keeps imported drafts permissive until release validation is implemented. Automatic import/admin sync and any broad backfill policy belong to Step 4.

Step 3 should provide explicit helpers that can be called by tests and later Step 4 code. A later Step 4 implementation can decide whether to run targeted backfill/sync during import, overwrite re-import, admin source correction, or a one-time migration job.

## Helper Function Interfaces

Add these public helpers to `app/db.py`:

```python
def replace_recipe_components_for_card(
    connection: sqlite3.Connection,
    card_id: int,
    components: tuple[ParsedRecipeComponent, ...] | list[ParsedRecipeComponent],
) -> None:
    """Replace derived normalized recipe rows for one card."""
```

```python
def parse_and_replace_recipe_components_for_card(
    connection: sqlite3.Connection,
    card_id: int,
    source_fields: dict[str, str | None],
) -> RecipeParseResult:
    """Parse source fields and replace rows only when the parser result is valid."""
```

```python
def fetch_recipe_components(
    connection: sqlite3.Connection,
    card_id: int,
) -> list[dict[str, Any]]:
    """Fetch normalized recipe rows in parser source-field order."""
```

Behavior:

- `replace_recipe_components_for_card()` deletes existing `recipe_components` rows for the card and inserts the supplied components in parser field order.
- `parse_and_replace_recipe_components_for_card()` calls `parse_recipe_source_fields()`.
- If parsing succeeds, it calls `replace_recipe_components_for_card()` and returns the parse result.
- If parsing fails, it returns the parse result and does not mutate existing normalized rows.
- Empty valid component input to `replace_recipe_components_for_card()` clears existing normalized rows. This is a storage helper behavior; deciding when empty source cells should clear rows in real workflows is Step 4.
- The helpers do not update `cards.version`, `cards.updated_at`, `card_import_sources`, or `recipe_actual_entries`.
- The helpers accept a caller-owned `sqlite3.Connection`, following existing lower-level DB helper patterns.

## Task 1: Add Failing Storage Tests

**Files:**

- Create: `tests/test_recipe_storage.py`
- Read for patterns: `tests/conftest.py`, `tests/test_recipe_parser.py`, `tests/test_baseline.py`, `tests/test_terminal_detail.py`

- [ ] **Step 1: Create the test file**

Create `tests/test_recipe_storage.py` with this content:

```python
from __future__ import annotations

import csv
import io
import sqlite3
from decimal import Decimal

from app import db
from app.recipe_parser import ParsedRecipeComponent


def insert_card(connection, order_number: str = "RS-001") -> int:
    cursor = connection.execute(
        """
        INSERT INTO cards (
            order_number,
            status,
            extrusion_flag,
            raw_material_a
        )
        VALUES (?, 'imported', 'да', ?)
        """,
        (order_number, "LDPE Rompetrol B20/03 | 100%"),
    )
    connection.commit()
    return int(cursor.lastrowid)


def stored_components(connection, card_id: int):
    return connection.execute(
        """
        SELECT component_key, source_text, material_category,
               planned_material, recipe_percent
        FROM recipe_components
        WHERE card_id = ?
        ORDER BY id
        """,
        (card_id,),
    ).fetchall()


def valid_components():
    return (
        ParsedRecipeComponent(
            component_key="raw_material_a",
            source_text="LDPE Rompetrol Midilena B20/03 | 77%",
            material_category="LDPE",
            planned_material="Rompetrol Midilena B20/03",
            recipe_percent=Decimal("77"),
        ),
        ParsedRecipeComponent(
            component_key="linear_pe",
            source_text="LLDPE SABIC 119ZJ | 23%",
            material_category="LLDPE",
            planned_material="SABIC 119ZJ",
            recipe_percent=Decimal("23"),
        ),
    )


def csv_bytes(rows: list[dict[str, str]]) -> bytes:
    fieldnames = [
        "order_number",
        "customer",
        "product_type",
        "quantity_1",
        "unit_1",
        "material",
        "size_thickness",
        "extrusion_flag",
        "raw_material_a",
        "packaging_method",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fieldnames})
    return output.getvalue().encode("utf-8")


def extrusion_row(order_number: str, **overrides: str) -> dict[str, str]:
    row = {
        "order_number": order_number,
        "customer": "Recipe Storage Customer",
        "product_type": "PE film",
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "да",
        "raw_material_a": "LDPE Rompetrol B20/03 | 100%",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def test_recipe_components_table_exists_after_init(connection):
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(recipe_components)").fetchall()
    }
    schema_sql = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'recipe_components'
        """
    ).fetchone()["sql"]

    assert {
        "id",
        "card_id",
        "component_key",
        "source_text",
        "material_category",
        "planned_material",
        "recipe_percent",
        "created_at",
        "updated_at",
    }.issubset(columns)
    assert "UNIQUE (card_id, component_key)" in schema_sql
    assert "recipe_percent > 0" in schema_sql


def test_replace_recipe_components_for_card_stores_normalized_rows(connection):
    card_id = insert_card(connection)

    db.replace_recipe_components_for_card(connection, card_id, valid_components())
    rows = stored_components(connection, card_id)

    assert len(rows) == 2
    assert dict(rows[0]) == {
        "component_key": "raw_material_a",
        "source_text": "LDPE Rompetrol Midilena B20/03 | 77%",
        "material_category": "LDPE",
        "planned_material": "Rompetrol Midilena B20/03",
        "recipe_percent": 77,
    }
    assert dict(rows[1]) == {
        "component_key": "linear_pe",
        "source_text": "LLDPE SABIC 119ZJ | 23%",
        "material_category": "LLDPE",
        "planned_material": "SABIC 119ZJ",
        "recipe_percent": 23,
    }


def test_fetch_recipe_components_returns_parser_field_order(connection):
    card_id = insert_card(connection)
    db.replace_recipe_components_for_card(
        connection,
        card_id,
        (
            ParsedRecipeComponent(
                component_key="masterbatch",
                source_text="Masterbatch White 8000 | 3%",
                material_category="Masterbatch",
                planned_material="White 8000",
                recipe_percent=Decimal("3"),
            ),
            ParsedRecipeComponent(
                component_key="raw_material_a",
                source_text="LDPE Rompetrol B20/03 | 97%",
                material_category="LDPE",
                planned_material="Rompetrol B20/03",
                recipe_percent=Decimal("97"),
            ),
        ),
    )

    rows = db.fetch_recipe_components(connection, card_id)

    assert [row["component_key"] for row in rows] == ["raw_material_a", "masterbatch"]
    assert rows[0]["recipe_percent"] == Decimal("97")
    assert rows[1]["recipe_percent"] == Decimal("3")
```

- [ ] **Step 2: Run the focused storage tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_storage.py -q
```

Expected failure:

```text
sqlite3.OperationalError: no such table: recipe_components
```

or:

```text
AttributeError: module 'app.db' has no attribute 'replace_recipe_components_for_card'
```

Do not implement more than the schema/helpers needed for these tests.

## Task 2: Add Schema And Minimal Storage Helpers

**Files:**

- Modify: `app/db.py`
- Test: `tests/test_recipe_storage.py`

- [ ] **Step 1: Import parser constants and types in `app/db.py`**

Near the existing imports in `app/db.py`, add:

```python
from .recipe_parser import (
    APPROVED_RECIPE_CATEGORIES,
    RECIPE_SOURCE_FIELDS,
    ParsedRecipeComponent,
    RecipeParseResult,
    parse_recipe_source_fields,
)
```

- [ ] **Step 2: Add SQL helper constants near `_sql_list()`**

Add:

```python
RECIPE_COMPONENT_KEY_PLACEHOLDERS = _sql_list(RECIPE_SOURCE_FIELDS)
RECIPE_CATEGORY_PLACEHOLDERS = _sql_list(APPROVED_RECIPE_CATEGORIES)
RECIPE_COMPONENT_ORDER_SQL = " ".join(
    f"WHEN '{component_key}' THEN {index}"
    for index, component_key in enumerate(RECIPE_SOURCE_FIELDS, start=1)
)
```

If this placement is awkward because `_sql_list()` must be defined first, place these constants immediately after `_sql_list()`.

- [ ] **Step 3: Add the table and index to `SCHEMA_SQL`**

Insert this block after `recipe_actual_entries` and before `production_time_segments`:

```python
CREATE TABLE IF NOT EXISTS recipe_components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    component_key TEXT NOT NULL CHECK (component_key IN ({RECIPE_COMPONENT_KEY_PLACEHOLDERS})),
    source_text TEXT NOT NULL,
    material_category TEXT NOT NULL CHECK (material_category IN ({RECIPE_CATEGORY_PLACEHOLDERS})),
    planned_material TEXT NOT NULL,
    recipe_percent NUMERIC NOT NULL CHECK (recipe_percent > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (card_id, component_key)
);
```

Insert this index near the existing recipe index:

```python
CREATE INDEX IF NOT EXISTS idx_recipe_components_card
ON recipe_components(card_id);
```

- [ ] **Step 4: Add helper functions in `app/db.py` near `fetch_recipe_actual_entries()`**

Add:

```python
def replace_recipe_components_for_card(
    connection: sqlite3.Connection,
    card_id: int,
    components: tuple[ParsedRecipeComponent, ...] | list[ParsedRecipeComponent],
) -> None:
    connection.execute(
        "DELETE FROM recipe_components WHERE card_id = ?",
        (card_id,),
    )
    connection.executemany(
        """
        INSERT INTO recipe_components (
            card_id,
            component_key,
            source_text,
            material_category,
            planned_material,
            recipe_percent
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                card_id,
                component.component_key,
                component.source_text,
                component.material_category,
                component.planned_material,
                decimal_to_storage(component.recipe_percent),
            )
            for component in sorted(
                components,
                key=lambda component: RECIPE_SOURCE_FIELDS.index(component.component_key),
            )
        ],
    )


def parse_and_replace_recipe_components_for_card(
    connection: sqlite3.Connection,
    card_id: int,
    source_fields: dict[str, str | None],
) -> RecipeParseResult:
    result = parse_recipe_source_fields(source_fields)
    if result.ok:
        replace_recipe_components_for_card(connection, card_id, result.components)
    return result


def fetch_recipe_components(
    connection: sqlite3.Connection,
    card_id: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"""
        SELECT id, card_id, component_key, source_text, material_category,
               planned_material, recipe_percent, created_at, updated_at
        FROM recipe_components
        WHERE card_id = ?
        ORDER BY CASE component_key {RECIPE_COMPONENT_ORDER_SQL} ELSE 999 END, id
        """,
        (card_id,),
    ).fetchall()
    components = rows_to_dicts(rows)
    for component in components:
        component["recipe_percent"] = decimal_from_database(component["recipe_percent"])
    return components
```

Keep these helpers connection-oriented. Do not open a new connection inside them.

- [ ] **Step 5: Run focused storage tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_storage.py -q
```

Expected:

```text
3 passed
```

If SQLite returns `77.0` instead of `77` in the raw SQL assertion, update only the raw-row assertion to compare `Decimal(str(row["recipe_percent"])) == Decimal("77")`. Keep `fetch_recipe_components()` returning `Decimal`.

## Task 3: Add Replacement, Parser-Error, And Preservation Tests

**Files:**

- Modify: `tests/test_recipe_storage.py`
- Modify only if needed: `app/db.py`

- [ ] **Step 1: Append replacement and parser-error tests**

Append:

```python

def test_replace_recipe_components_for_card_removes_stale_rows(connection):
    card_id = insert_card(connection)
    db.replace_recipe_components_for_card(connection, card_id, valid_components())

    db.replace_recipe_components_for_card(
        connection,
        card_id,
        (
            ParsedRecipeComponent(
                component_key="raw_material_a",
                source_text="LDPE New Material | 100%",
                material_category="LDPE",
                planned_material="New Material",
                recipe_percent=Decimal("100"),
            ),
        ),
    )
    rows = db.fetch_recipe_components(connection, card_id)

    assert [row["component_key"] for row in rows] == ["raw_material_a"]
    assert rows[0]["source_text"] == "LDPE New Material | 100%"
    assert rows[0]["recipe_percent"] == Decimal("100")


def test_parse_and_replace_recipe_components_for_card_stores_only_valid_parse(connection):
    card_id = insert_card(connection)

    result = db.parse_and_replace_recipe_components_for_card(
        connection,
        card_id,
        {
            "raw_material_a": "LDPE Rompetrol B20/03 | 80%",
            "linear_pe": "LLDPE SABIC 119ZJ | 20%",
        },
    )

    assert result.ok
    rows = db.fetch_recipe_components(connection, card_id)
    assert [row["component_key"] for row in rows] == ["raw_material_a", "linear_pe"]


def test_parse_and_replace_recipe_components_for_card_does_not_mutate_on_parse_error(connection):
    card_id = insert_card(connection)
    db.replace_recipe_components_for_card(connection, card_id, valid_components())

    result = db.parse_and_replace_recipe_components_for_card(
        connection,
        card_id,
        {
            "raw_material_a": "LDPE Rompetrol B20/03 | 80%",
            "linear_pe": "LLDPE SABIC 119ZJ | 19%",
        },
    )

    assert not result.ok
    assert [error.message for error in result.errors] == [
        "сборът на процентите трябва да е точно 100%"
    ]
    rows = db.fetch_recipe_components(connection, card_id)
    assert [row["source_text"] for row in rows] == [
        "LDPE Rompetrol Midilena B20/03 | 77%",
        "LLDPE SABIC 119ZJ | 23%",
    ]
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_storage.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 3: Append production-entry preservation test**

Append:

```python

def test_recipe_component_replacement_does_not_touch_actual_recipe_entries(connection):
    card_id = insert_card(connection)
    connection.execute(
        """
        INSERT INTO recipe_actual_entries (
            card_id,
            component_key,
            component_label,
            planned_material,
            actual_material_used,
            batch_lot
        )
        VALUES (?, 'raw_material_a', 'Вид суровина A', 'Old planned', 'Actual LDPE', 'Batch 42')
        """,
        (card_id,),
    )
    connection.commit()

    db.replace_recipe_components_for_card(connection, card_id, valid_components())

    actual_entry = connection.execute(
        """
        SELECT planned_material, actual_material_used, batch_lot
        FROM recipe_actual_entries
        WHERE card_id = ?
          AND component_key = 'raw_material_a'
        """,
        (card_id,),
    ).fetchone()

    assert dict(actual_entry) == {
        "planned_material": "Old planned",
        "actual_material_used": "Actual LDPE",
        "batch_lot": "Batch 42",
    }
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_storage.py -q
```

Expected:

```text
7 passed
```

## Task 4: Add Constraint And Migration-Safety Tests

**Files:**

- Modify: `tests/test_recipe_storage.py`
- Modify only if needed: `app/db.py`

- [ ] **Step 1: Append constraint tests**

Append:

```python

def test_recipe_components_reject_unknown_component_key(connection):
    card_id = insert_card(connection)

    try:
        connection.execute(
            """
            INSERT INTO recipe_components (
                card_id, component_key, source_text, material_category,
                planned_material, recipe_percent
            )
            VALUES (?, 'not_a_recipe_field', 'LDPE A | 100%', 'LDPE', 'A', 100)
            """,
            (card_id,),
        )
    except sqlite3.IntegrityError as exc:
        assert "CHECK constraint failed" in str(exc)
    else:
        raise AssertionError("recipe_components accepted an unknown component_key")


def test_recipe_components_reject_unknown_material_category(connection):
    card_id = insert_card(connection)

    try:
        connection.execute(
            """
            INSERT INTO recipe_components (
                card_id, component_key, source_text, material_category,
                planned_material, recipe_percent
            )
            VALUES (?, 'raw_material_a', 'mLLDPE A | 100%', 'mLLDPE', 'A', 100)
            """,
            (card_id,),
        )
    except sqlite3.IntegrityError as exc:
        assert "CHECK constraint failed" in str(exc)
    else:
        raise AssertionError("recipe_components accepted an unknown material_category")


def test_recipe_components_cascade_when_card_is_deleted(connection):
    card_id = insert_card(connection)
    db.replace_recipe_components_for_card(connection, card_id, valid_components())

    connection.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    connection.commit()

    remaining = connection.execute(
        "SELECT COUNT(*) FROM recipe_components WHERE card_id = ?",
        (card_id,),
    ).fetchone()[0]
    assert remaining == 0
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_storage.py -q
```

Expected:

```text
10 passed
```

- [ ] **Step 3: Append legacy initialization test**

Append:

```python

def test_database_initialization_adds_recipe_components_to_existing_database(monkeypatch, tmp_path):
    legacy_data_dir = tmp_path / "legacy-data"
    legacy_data_dir.mkdir()
    legacy_db_path = legacy_data_dir / "legacy.sqlite3"
    with sqlite3.connect(legacy_db_path) as legacy_connection:
        legacy_connection.execute(
            """
            CREATE TABLE cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'imported',
                raw_material_a TEXT
            )
            """
        )
        legacy_connection.execute(
            """
            INSERT INTO cards (order_number, raw_material_a)
            VALUES ('LEGACY-RS-1', 'LDPE Legacy A | 100%')
            """
        )

    monkeypatch.setattr(db, "DATA_DIR", legacy_data_dir)
    monkeypatch.setattr(db, "DB_PATH", legacy_db_path)

    db.init_db()
    db.init_db()

    with db.connect() as migrated_connection:
        table = migrated_connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'recipe_components'
            """
        ).fetchone()
        row_count = migrated_connection.execute(
            "SELECT COUNT(*) FROM recipe_components"
        ).fetchone()[0]

    assert table["name"] == "recipe_components"
    assert row_count == 0
```

This test intentionally asserts no automatic backfill in Step 3.

- [ ] **Step 4: Run focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_storage.py -q
```

Expected:

```text
11 passed
```

## Task 5: Add A Narrow Baseline Guard Against Accidental Step 4/5 Scope

**Files:**

- Modify: `tests/test_recipe_storage.py`
- Modify only if needed: `app/db.py`

- [ ] **Step 1: Append non-sync guard tests**

Append:

```python

def test_import_does_not_auto_create_recipe_components_in_step_3(connection):
    from app.importer import import_cards_from_csv

    result = import_cards_from_csv(
        "recipe-storage-step3.csv",
        csv_bytes(
            [
                extrusion_row(
                    "RS-IMPORT-1",
                    raw_material_a="LDPE Rompetrol B20/03 | 100%",
                )
            ]
        ),
        overwrite_existing=False,
    )

    assert result.created == 1
    count = connection.execute("SELECT COUNT(*) FROM recipe_components").fetchone()[0]
    assert count == 0


def test_release_does_not_validate_or_sync_recipe_components_in_step_3(connection):
    card_id = insert_card(connection, "RS-RELEASE-1")

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)

    assert result.ok
    count = connection.execute(
        "SELECT COUNT(*) FROM recipe_components WHERE card_id = ?",
        (card_id,),
    ).fetchone()[0]
    assert count == 0
```

These tests are intentional Step 3 boundary checks. They should be removed or changed in Step 4/Step 5 when sync and release gates are implemented.

- [ ] **Step 2: Run focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_storage.py -q
```

Expected:

```text
13 passed
```

## Task 6: Update Milestone Tracker

**Files:**

- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Add a concise OI-003 Step 3 note**

Add a short note in the active/pending milestone area or a new small section near the current roadmap notes:

```markdown
Structured recipe redesign follow-up:

- OI-003 Step 2 complete: central parser committed in `0de3d33`.
- OI-003 Step 3 in progress: add normalized recipe-component SQLite storage and backend helpers only.
- Step 3 deliberately does not sync normalized rows from CSV import, overwrite re-import, or admin source correction; that is Step 4.
- Step 3 deliberately does not add release gates or UI changes; those are Steps 5 and 6.
```

If the implementation is already complete by the time this task runs, change `in progress` to `complete` and mention that the focused storage tests pass.

- [ ] **Step 2: Check the tracker diff**

Run:

```bash
git diff -- IMPLEMENTATION_PLAN.md
```

Expected:

- The note is short.
- It does not claim Step 4, Step 5, or Step 6 work is complete.
- It does not mention pricing, costing, inventory, ERP, or material catalog work.

## Task 7: Verification

**Files:**

- No edits unless verification finds a concrete defect.

- [ ] **Step 1: Run focused parser and storage tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_parser.py tests/test_recipe_storage.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run relevant DB/import/admin tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py tests/test_terminal_detail.py tests/test_admin_card_detail_redesign.py -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Run the full Python suite**

Run:

```bash
source .venv/bin/activate
python -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 4: Run syntax/import check**

Run:

```bash
source .venv/bin/activate
python -m compileall app
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

- [ ] **Step 6: Inspect changed files**

Run:

```bash
git status --short
git diff --name-only
```

Expected allowed changed files:

```text
M IMPLEMENTATION_PLAN.md
M app/db.py
?? tests/test_recipe_storage.py
```

The unrelated untracked directory may still appear:

```text
?? interim-costing-process/source-files/recipe-builder-demo/
```

Do not touch, stage, or commit that directory.

## Self-Review Checklist

Before reporting Step 3 implementation complete, verify:

- `cards.raw_material_a` through `cards.chalk` remain in place and unchanged as imported source fields.
- `recipe_actual_entries` remains untouched by normalized storage replacement.
- `recipe_components` stores only the thin normalized fields from the contract.
- `recipe_components` has a foreign key to `cards(id)` with `ON DELETE CASCADE`.
- `recipe_components` has `UNIQUE (card_id, component_key)`.
- `recipe_components.component_key` is constrained to parser source fields.
- `recipe_components.material_category` is constrained to approved parser categories.
- `recipe_components.recipe_percent` rejects zero and negative values.
- Helper functions use `ParsedRecipeComponent` / `RecipeParseResult` from `app.recipe_parser`.
- Parser errors do not silently replace existing normalized rows.
- No automatic sync was added to CSV import, overwrite re-import, or admin source correction.
- `release_card()` was not changed to validate recipe format or total percent.
- No terminal/admin templates changed.
- No print or Excel macro files changed.
- No files under `interim-costing-process/source-files/recipe-builder-demo/` changed.
- No files are staged or committed unless the user explicitly asked.

## Completion Criteria

Step 3 is complete when:

- `recipe_components` is created by `db.init_db()` for new and existing SQLite databases.
- Explicit helpers can store, replace, parse-and-store, and fetch normalized recipe-component rows.
- Focused tests cover schema, replacement, fetch ordering, parser-error non-mutation, production-entry preservation, constraints, cascade deletion, legacy initialization, and Step 3 non-sync boundaries.
- Focused parser/storage tests pass.
- Relevant DB/import/admin tests pass.
- The full Python suite passes.
- `python -m compileall app` passes.
- `git diff --check` passes.
- The implementation remains within OI-003 Step 3 scope.
- Nothing is staged or committed unless the user explicitly asked.
