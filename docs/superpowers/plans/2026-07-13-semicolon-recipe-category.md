# Semicolon Recipe Category Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not commit, stage, or revert unrelated work unless the user explicitly asks.

**Goal:** Support multi-word recipe categories by changing the terminal app recipe contract to `Category; Material name | Percent`, while removing app-side category approval and keeping print output compact.

**Architecture:** Excel remains the owner of category validity. The app parses and stores category, material, and percent as structural data; it does not decide whether a category is approved. Import becomes the first app-side recipe validation gate, while admin saves normalize recipe text to the semicolon format.

**Tech Stack:** Python 3, FastAPI, direct `sqlite3`, server-rendered Jinja templates, pytest.

---

## Files

- Modify: `app/recipe_parser.py`
  - Add semicolon parsing.
  - Remove category allow-list validation from parser behavior.
  - Keep old first-token fallback for legacy rows.
- Modify: `app/db.py`
  - Remove `recipe_components.material_category` allow-list constraint for new databases.
  - Add idempotent migration for existing databases with the old category check.
  - Keep recipe component source sync behavior.
- Modify: `app/importer.py`
  - Validate extrusion recipe structure during CSV import.
  - Block invalid recipe rows per row.
- Modify: `app/main.py`
  - Remove `APPROVED_RECIPE_CATEGORIES` usage.
  - Compose admin-edited recipe source text with `;`.
  - Keep admin recipe validation using parser results.
- Modify: `app/templates/admin_card_detail.html`
  - Change category dropdown to text input.
- Modify: `app/printing.py`
  - Render parsed print recipe rows as `Material name Percent`.
- Modify: `IMPLEMENTATION_PLAN.md`
  - Record the completed terminal-side contract change after implementation.
- Test: `tests/test_recipe_parser.py`
- Test: `tests/test_recipe_storage.py`
- Test: `tests/test_recipe_sync.py`
- Test: `tests/test_recipe_release_validation.py`
- Test: `tests/test_baseline.py`
- Test: `tests/test_admin_card_detail_redesign.py`
- Test: `tests/test_print_output.py`

---

### Task 1: Parser Contract

**Files:**
- Modify: `app/recipe_parser.py`
- Test: `tests/test_recipe_parser.py`

- [ ] **Step 1: Update parser tests for semicolon format**

In `tests/test_recipe_parser.py`, replace the category allow-list contract test with semicolon parsing tests. Add these tests near the existing parser tests:

```python
def test_parse_semicolon_recipe_cell_allows_multi_word_category():
    component, errors = parse_recipe_cell(
        "masterbatch",
        "UV Protection; Additech UV Shield XZ-204 | 2%",
    )

    assert errors == ()
    assert component == ParsedRecipeComponent(
        component_key="masterbatch",
        source_text="UV Protection; Additech UV Shield XZ-204 | 2%",
        material_category="UV Protection",
        planned_material="Additech UV Shield XZ-204",
        recipe_percent=Decimal("2"),
    )


def test_parse_semicolon_recipe_fields_total_100():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "LDPE; Rompetrol Midilena TR-130 B20/03 | 38%",
            "linear_pe": "LLDPE; HIP Petrohemija TR-130 | 60%",
            "masterbatch": "UV Protection; Additech UV Shield XZ-204 | 2%",
        }
    )

    assert result.ok
    assert result.total_percent == Decimal("100")
    assert [
        (component.material_category, component.planned_material)
        for component in result.components
    ] == [
        ("LDPE", "Rompetrol Midilena TR-130 B20/03"),
        ("LLDPE", "HIP Petrohemija TR-130"),
        ("UV Protection", "Additech UV Shield XZ-204"),
    ]


def test_parse_semicolon_recipe_rejects_missing_category_or_material():
    missing_category, missing_category_errors = parse_recipe_cell(
        "raw_material_a",
        "; Rompetrol B20/03 | 38%",
    )
    missing_material, missing_material_errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE; | 38%",
    )

    assert missing_category is None
    assert missing_category_errors[0].message == "липсва категория"
    assert missing_material is None
    assert missing_material_errors[0].message == "липсва материал след категория"


def test_parse_legacy_first_token_recipe_cell_as_fallback():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Rompetrol Midilena B20/03 | 38%",
    )

    assert errors == ()
    assert component == ParsedRecipeComponent(
        component_key="raw_material_a",
        source_text="LDPE Rompetrol Midilena B20/03 | 38%",
        material_category="LDPE",
        planned_material="Rompetrol Midilena B20/03",
        recipe_percent=Decimal("38"),
    )
```

Remove or rewrite tests that assert `APPROVED_RECIPE_CATEGORIES` exactly equals a fixed tuple and tests that assert unknown categories are rejected. Unknown category rejection is no longer app behavior.

- [ ] **Step 2: Run parser tests and confirm failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_parser.py -q
```

Expected: failures for semicolon parsing and removed allow-list behavior.

- [ ] **Step 3: Implement semicolon parser**

In `app/recipe_parser.py`:

1. Remove `APPROVED_RECIPE_CATEGORIES` and `CATEGORY_BY_NORMALIZED_NAME`.
2. Add:

```python
MISSING_CATEGORY_MESSAGE = "липсва категория"
```

3. Replace `split_category_and_material()` with:

```python
def split_category_and_material(identity_text: str) -> tuple[str, str]:
    if ";" in identity_text:
        category, planned_material = identity_text.split(";", 1)
        return category.strip(), planned_material.strip()

    parts = identity_text.split(" ", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1].strip()
```

4. In `parse_recipe_cell()`, replace the allow-list lookup block with:

```python
    category_text, planned_material = split_category_and_material(normalized_identity)
    if not category_text:
        return None, (
            RecipeParseError(
                component_key=component_key,
                source_text=original_source_text,
                message=MISSING_CATEGORY_MESSAGE,
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

    material_category = category_text
```

This makes both semicolon rows and legacy first-token rows require a non-empty material name.

- [ ] **Step 4: Run parser tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_parser.py -q
```

Expected: parser tests pass after old allow-list expectations are updated.

---

### Task 2: Recipe Component Storage Constraint

**Files:**
- Modify: `app/db.py`
- Test: `tests/test_recipe_storage.py`

- [ ] **Step 1: Update storage tests**

In `tests/test_recipe_storage.py`:

1. Replace `test_recipe_components_reject_unknown_material_category` with:

```python
def test_recipe_components_accept_arbitrary_material_category(connection):
    card_id = insert_card(connection)

    connection.execute(
        """
        INSERT INTO recipe_components (
            card_id,
            component_key,
            source_text,
            material_category,
            planned_material,
            recipe_percent
        )
        VALUES (?, 'raw_material_a', 'UV Protection; Additive X | 100%', 'UV Protection', 'Additive X', 100)
        """,
        (card_id,),
    )

    row = connection.execute(
        """
        SELECT material_category, planned_material
        FROM recipe_components
        WHERE card_id = ?
        """,
        (card_id,),
    ).fetchone()

    assert dict(row) == {
        "material_category": "UV Protection",
        "planned_material": "Additive X",
    }
```

2. Add a migration test:

```python
def test_database_initialization_removes_legacy_recipe_category_check(
    tmp_path,
    monkeypatch,
):
    legacy_data_dir = tmp_path / "legacy-recipe-category-data"
    legacy_data_dir.mkdir()
    legacy_db_path = legacy_data_dir / "legacy.sqlite3"
    with sqlite3.connect(legacy_db_path) as legacy_connection:
        legacy_connection.executescript(
            """
            CREATE TABLE cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'imported',
                raw_material_a TEXT
            );
            CREATE TABLE recipe_components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                component_key TEXT NOT NULL CHECK (component_key IN ('raw_material_a')),
                source_text TEXT NOT NULL,
                material_category TEXT NOT NULL CHECK (material_category IN ('LDPE')),
                planned_material TEXT NOT NULL,
                recipe_percent NUMERIC NOT NULL CHECK (recipe_percent > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (card_id, component_key)
            );
            INSERT INTO cards (id, order_number, raw_material_a)
            VALUES (1, 'LEGACY-RC-1', 'LDPE A | 100%');
            INSERT INTO recipe_components (
                card_id, component_key, source_text, material_category,
                planned_material, recipe_percent
            )
            VALUES (1, 'raw_material_a', 'LDPE A | 100%', 'LDPE', 'A', 100);
            """
        )

    monkeypatch.setattr(db, "DATA_DIR", legacy_data_dir)
    monkeypatch.setattr(db, "DB_PATH", legacy_db_path)

    db.init_db()

    with db.connect() as migrated_connection:
        schema_sql = migrated_connection.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'recipe_components'
            """
        ).fetchone()["sql"]
        migrated_connection.execute(
            """
            INSERT INTO recipe_components (
                card_id, component_key, source_text, material_category,
                planned_material, recipe_percent
            )
            VALUES (1, 'raw_material_a', 'UV Protection; Additive X | 100%', 'UV Protection', 'Additive X', 100)
            """
        )
        row_count = migrated_connection.execute(
            "SELECT COUNT(*) AS row_count FROM recipe_components WHERE card_id = 1"
        ).fetchone()["row_count"]

    assert "material_category IN" not in schema_sql
    assert row_count == 2
```

- [ ] **Step 2: Run storage tests and confirm failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_storage.py -q
```

Expected: failures until the schema and migration are updated.

- [ ] **Step 3: Update schema and add migration**

In `app/db.py`:

1. Remove `APPROVED_RECIPE_CATEGORIES` import.
2. Remove `RECIPE_CATEGORY_PLACEHOLDERS`.
3. Change schema line:

```python
    material_category TEXT NOT NULL CHECK (material_category IN ({RECIPE_CATEGORY_PLACEHOLDERS})),
```

to:

```python
    material_category TEXT NOT NULL,
```

4. Add this function near `ensure_cards_status_constraint()` helpers:

```python
def ensure_recipe_components_category_constraint(connection: sqlite3.Connection) -> bool:
    table = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'recipe_components'
        """
    ).fetchone()
    if table is None:
        return False

    schema_sql = str(table["sql"] or "")
    if "material_category TEXT NOT NULL CHECK" not in schema_sql:
        return False

    connection.execute("DROP TABLE IF EXISTS recipe_components_migration")
    connection.execute(
        f"""
        CREATE TABLE recipe_components_migration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            component_key TEXT NOT NULL CHECK (component_key IN ({RECIPE_COMPONENT_KEY_PLACEHOLDERS})),
            source_text TEXT NOT NULL,
            material_category TEXT NOT NULL,
            planned_material TEXT NOT NULL,
            recipe_percent NUMERIC NOT NULL CHECK (recipe_percent > 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (card_id, component_key)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO recipe_components_migration (
            id, card_id, component_key, source_text, material_category,
            planned_material, recipe_percent, created_at, updated_at
        )
        SELECT id, card_id, component_key, source_text, material_category,
               planned_material, recipe_percent, created_at, updated_at
        FROM recipe_components
        """
    )
    connection.execute("DROP TABLE recipe_components")
    connection.execute("ALTER TABLE recipe_components_migration RENAME TO recipe_components")
    return True
```

5. In `init_db()`, after the first `connection.executescript(SCHEMA_SQL)` and before the final `connection.executescript(SCHEMA_SQL)`, call:

```python
        ensure_recipe_components_category_constraint(connection)
```

- [ ] **Step 4: Run storage tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_storage.py -q
```

Expected: storage tests pass.

---

### Task 3: Import-Time Recipe Blocking

**Files:**
- Modify: `app/importer.py`
- Test: `tests/test_baseline.py`
- Test: `tests/test_recipe_sync.py`

- [ ] **Step 1: Add import validation tests**

In `tests/test_baseline.py`, add:

```python
def test_csv_import_blocks_invalid_recipe_row_without_blocking_valid_rows(connection):
    result = import_cards_from_csv(
        "mixed-recipe-validity.csv",
        csv_bytes(
            extrusion_row(
                "25330",
                raw_material_a="UV Protection; Additech UV Shield XZ-204 | 2%",
                linear_pe="LLDPE; HIP Petrohemija TR-130 | 98%",
            ),
            extrusion_row(
                "25331",
                raw_material_a="UV Protection; | 2%",
                linear_pe="LLDPE; HIP Petrohemija TR-130 | 98%",
            ),
        ),
        overwrite_existing=False,
    )

    created = connection.execute(
        "SELECT order_number FROM cards ORDER BY order_number"
    ).fetchall()

    assert result.rows_seen == 2
    assert result.rows_imported == 1
    assert result.created == 1
    assert result.skipped == 1
    assert [row.action for row in result.row_results] == ["created", "blocked"]
    assert "Рецептата не може да бъде импортирана" in result.row_results[1].message
    assert [row["order_number"] for row in created] == ["25330"]
```

In `tests/test_recipe_sync.py`, update structured-row helpers and expectations to use semicolon source text where the test asserts normalized components. Add:

```python
def test_csv_import_syncs_semicolon_recipe_components(connection):
    result = import_cards_from_csv(
        "structured-semicolon-import.csv",
        csv_bytes(
            structured_row(
                "RS-SYNC-SEMICOLON",
                raw_material_a="UV Protection; Additech UV Shield XZ-204 | 2%",
                linear_pe="LLDPE; HIP Petrohemija TR-130 | 98%",
            )
        ),
        overwrite_existing=False,
    )
    card_id = int(
        connection.execute(
            "SELECT id FROM cards WHERE order_number = 'RS-SYNC-SEMICOLON'"
        ).fetchone()["id"]
    )

    assert result.created == 1
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "UV Protection; Additech UV Shield XZ-204 | 2%", "UV Protection", "Additech UV Shield XZ-204"),
        ("linear_pe", "LLDPE; HIP Petrohemija TR-130 | 98%", "LLDPE", "HIP Petrohemija TR-130"),
    ]
```

Update tests that currently expect import to allow invalid recipes. They should now expect row action `blocked` and no card created for invalid recipe source text.

- [ ] **Step 2: Run focused import tests and confirm failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py::test_csv_import_blocks_invalid_recipe_row_without_blocking_valid_rows tests/test_recipe_sync.py -q
```

Expected: failures until importer validates recipes before insert/update.

- [ ] **Step 3: Implement import validation**

In `app/importer.py`:

1. Import `validate_structured_recipe_release` is already present. Add a helper:

```python
def validate_import_recipe_fields(card: dict[str, str]) -> RuleResult:
    release_validity = validate_structured_recipe_release(card)
    messages = tuple(
        message.replace(
            "Рецептата не може да бъде пусната",
            "Рецептата не може да бъде импортирана",
            1,
        )
        for message in release_validity.messages
    )
    return RuleResult(release_validity.ok, messages)
```

2. In `import_cards_from_csv()`, after `card_has_usable_extrusion_step(card)` passes and before duplicate handling, add:

```python
            recipe_validity = validate_import_recipe_fields(card)
            if not recipe_validity.ok:
                block_import_row(
                    result,
                    row_number,
                    order_number,
                    " ".join(recipe_validity.messages),
                    connection,
                )
                continue
```

This validates both created rows and overwrite rows before persistence. Keep stale overwrite checks in place for existing rows.

- [ ] **Step 4: Run focused import tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py tests/test_recipe_sync.py -q
```

Expected: tests pass after expectations are updated for import-time blocking.

---

### Task 4: Admin Semicolon Editing

**Files:**
- Modify: `app/main.py`
- Modify: `app/templates/admin_card_detail.html`
- Test: `tests/test_admin_card_detail_redesign.py`
- Test: `tests/test_recipe_release_validation.py`

- [ ] **Step 1: Update admin tests**

In `tests/test_admin_card_detail_redesign.py`, change expectations for category controls from `select` options to text inputs. Add:

```python
def test_admin_recipe_category_is_free_text_input(connection):
    card_id = import_card("ADMIN-CATEGORY-TEXT")

    response = asyncio.run(admin_card_detail(make_request(f"/admin/cards/{card_id}"), card_id))
    html = response.body.decode()

    assert 'name="material_category__raw_material_a"' in html
    assert '<select name="material_category__raw_material_a"' not in html
```

Add or update a save test:

```python
def test_admin_global_save_writes_semicolon_recipe_source(connection):
    card_id = import_card("ADMIN-SEMICOLON-SAVE")
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]

    form = FormData(
        [
            ("loaded_version", str(loaded_version)),
            ("order_number", "ADMIN-SEMICOLON-SAVE"),
            ("extrusion_flag", "da"),
            ("extrusion_folding", "single"),
            ("material_category__raw_material_a", "UV Protection"),
            ("planned_material__raw_material_a", "Additech UV Shield XZ-204"),
            ("recipe_percent__raw_material_a", "2"),
            ("material_category__linear_pe", "LLDPE"),
            ("planned_material__linear_pe", "HIP Petrohemija TR-130"),
            ("recipe_percent__linear_pe", "98"),
        ]
    )

    response = asyncio.run(
        save_admin_card_all(
            make_form_request(f"/admin/cards/{card_id}/save-all", form),
            card_id,
        )
    )
    card = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert card["raw_material_a"] == "UV Protection; Additech UV Shield XZ-204 | 2%"
    assert card["linear_pe"] == "LLDPE; HIP Petrohemija TR-130 | 98%"
```

Use the existing request/form helper patterns in this test file; keep imports consistent with current test utilities.

In `tests/test_recipe_release_validation.py`, add:

```python
def test_release_allows_semicolon_multi_word_category(connection):
    card_id = import_structured_card(
        "RS-REL-SEMICOLON",
        raw_material_a="UV Protection; Additech UV Shield XZ-204 | 2%",
        linear_pe="LLDPE; HIP Petrohemija TR-130 | 98%",
    )

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)

    assert result.ok
```

Remove release expectations that unknown categories are rejected.

- [ ] **Step 2: Run admin/release tests and confirm failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py tests/test_recipe_release_validation.py -q
```

Expected: failures until the template and compose logic are updated.

- [ ] **Step 3: Update admin compose logic**

In `app/main.py`:

1. Remove `APPROVED_RECIPE_CATEGORIES` import.
2. Remove `"recipe_categories": APPROVED_RECIPE_CATEGORIES` from `admin_card_detail_context()`.
3. Change `compose_recipe_source_text()` identity construction from:

```python
    identity = " ".join(part for part in (category, planned_material) if part)
```

to:

```python
    if category and planned_material:
        identity = f"{category}; {planned_material}"
    else:
        identity = " ".join(part for part in (category, planned_material) if part)
```

The fallback lets validation produce useful messages for incomplete admin forms.

- [ ] **Step 4: Update category control template**

In `app/templates/admin_card_detail.html`, replace:

```html
              <select name="material_category__{{ row.field }}" aria-label="{{ row.source_label }} категория">
                <option value=""></option>
                {% for category in recipe_categories %}
                  <option value="{{ category }}"{% if row.material_category == category %} selected{% endif %}>{{ category }}</option>
                {% endfor %}
              </select>
```

with:

```html
              <input name="material_category__{{ row.field }}" value="{{ row.material_category or '' }}" aria-label="{{ row.source_label }} категория">
```

- [ ] **Step 5: Run admin/release tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py tests/test_recipe_release_validation.py -q
```

Expected: tests pass after test helpers are adjusted to the current request utilities.

---

### Task 5: Compact Print Recipe Output

**Files:**
- Modify: `app/printing.py`
- Test: `tests/test_print_output.py`
- Test: `tests/test_structured_recipe_sample_csv.py`

- [ ] **Step 1: Add print output test**

In `tests/test_print_output.py`, add:

```python
def test_print_recipe_rows_show_material_and_percent_without_category_or_delimiters(connection):
    card_id = make_completed_printable_card("27080", roll_count=1)
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE cards
            SET raw_material_a = ?,
                linear_pe = ?,
                version = version + 1
            WHERE id = ?
            """,
            (
                "UV Protection; Additech UV Shield XZ-204 | 2%",
                "LLDPE; HIP Petrohemija TR-130 | 98%",
                card_id,
            ),
        )
        db.sync_recipe_components_for_card(
            connection,
            card_id,
            {
                "raw_material_a": "UV Protection; Additech UV Shield XZ-204 | 2%",
                "linear_pe": "LLDPE; HIP Petrohemija TR-130 | 98%",
            },
        )

    response = get_print_page(card_id)

    assert response.status_code == 200
    assert "Additech UV Shield XZ-204 2%" in response.text
    assert "HIP Petrohemija TR-130 98%" in response.text
    assert "UV Protection;" not in response.text
    assert " | 2%" not in response.text
```

Update `tests/test_structured_recipe_sample_csv.py` if it asserts print preserves category-only source text. The new print contract is compact parsed material plus percent.

- [ ] **Step 2: Run print tests and confirm failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_print_output.py::test_print_recipe_rows_show_material_and_percent_without_category_or_delimiters -q
```

Expected: failure because print currently uses the raw card field source text.

- [ ] **Step 3: Implement compact print row helper**

In `app/printing.py`, add imports:

```python
from .recipe_parser import parse_recipe_cell
```

Add helper near `build_recipe_rows()`:

```python
def print_recipe_material_display(component_key: str, source_text: Any) -> str:
    component, errors = parse_recipe_cell(component_key, text_value(source_text))
    if errors or component is None:
        return text_value(source_text)
    percent = format_percent(component.recipe_percent)
    return " ".join(part for part in (component.planned_material, percent) if part)


def format_percent(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text}%"
```

In `build_recipe_rows()`, change:

```python
                "planned_material": text_value(card.get(card_field)),
```

to:

```python
                "planned_material": print_recipe_material_display(
                    component_key,
                    card.get(card_field),
                ),
```

This keeps a fallback for unexpected old malformed rows while normal valid rows print compactly.

- [ ] **Step 4: Run print tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_print_output.py tests/test_structured_recipe_sample_csv.py -q
```

Expected: print tests pass after old print expectations are updated.

---

### Task 6: Documentation And Verification

**Files:**
- Modify: `IMPLEMENTATION_PLAN.md`
- Optional modify: `docs/implementation-notes/structured-recipe-contract.md`

- [ ] **Step 1: Update implementation tracker**

In `IMPLEMENTATION_PLAN.md`, add a short completed note under the current milestone area after implementation succeeds:

```markdown
- Semicolon recipe-category contract complete: terminal import now validates `Category; Material name | Percent`, supports multi-word categories without app-side category approval, stores arbitrary recipe categories, normalizes admin recipe saves to semicolon format, and prints compact material-plus-percent recipe rows.
```

- [ ] **Step 2: Update structured recipe implementation note**

In `docs/implementation-notes/structured-recipe-contract.md`, update the accepted cell format section to state:

```text
Category; Material name | Percent
```

Also state that Excel owns category validity and the terminal app validates structure only.

- [ ] **Step 3: Run focused test suite**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_parser.py tests/test_recipe_storage.py tests/test_recipe_sync.py tests/test_recipe_release_validation.py tests/test_baseline.py tests/test_admin_card_detail_redesign.py tests/test_print_output.py tests/test_structured_recipe_sample_csv.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run full test suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected: full suite passes.

- [ ] **Step 5: Run diff check**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 6: Manual UI check**

Start the app with a temporary database:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/semicolon-recipe/extrusion_terminal.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a browser:

1. Import a CSV row containing `UV Protection; Additech UV Shield XZ-204 | 2%` and another row totaling the remaining `98%`.
2. Confirm import succeeds.
3. Confirm admin detail shows category `UV Protection` and material `Additech UV Shield XZ-204` in separate controls.
4. Release the card.
5. Confirm terminal display shows the same category/material split.
6. Complete the card or use an existing completed test card.
7. Confirm print output shows `Additech UV Shield XZ-204 2%` without category, semicolon, or pipe.

Capture at least one screenshot under:

```text
artifacts/ui-checks/semicolon-recipe-category/
```

- [ ] **Step 7: Final review**

Review the diff for:

- no hard-coded category approval remains in app validation;
- semicolon parser supports multi-word categories;
- import blocks invalid recipe rows per row;
- admin save writes semicolon format;
- print output uses compact material-plus-percent display;
- no inventory, material ID, or Excel sync work slipped into scope.

---

## Self-Review

- Spec coverage: all approved design requirements map to Tasks 1 through 6.
- Red-flag scan: no incomplete implementation steps are intentionally left for the implementer.
- Type consistency: parser continues returning `ParsedRecipeComponent`; storage continues using `recipe_components.material_category`, `planned_material`, and `recipe_percent`; admin form field names remain unchanged.
- Scope check: inventory sync, material IDs, and Excel macro changes are excluded from this terminal-side plan.
