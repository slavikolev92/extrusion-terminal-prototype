# Editable Executed Recipes And Material Catalogue Implementation Plan

> **DO NOT EXECUTE — SUPERSEDED START GATE (2026-08-26):** This is the retained
> pre-reconciliation Task 20 plan, not an executable implementation plan. Its
> seven-column `RecipeCatalogExtrusion` source, `FullMaterialName` identity,
> name-based matching, schema sketches, tests, session map, and estimate depend
> on assumptions superseded by
> `v2-files/inventory-and-materials/ITEM-MASTER-SKU-DESIGN.md`. Task 20 remains
> the next approved pilot workstream and is unimplemented, but its first step is
> bounded reconciliation of this plan and the Task 20 specification to SKU
> identity, a published Item Master snapshot or extrusion-specific projection,
> and historical snapshot safety. Catalogue-backed executed rows must retain
> SKU and relevant readable snapshots without later refresh rewriting
> production history; free-text exceptions receive no invented SKU. Item Master
> v1 must first confirm its remaining SKU allocation, required-field/family,
> Item Name, alias, lifecycle, and published snapshot schema/version decisions.
> This consolidation does not resolve those decisions or expand the pilot.
> Every implementation instruction below is historical planning context unless
> it is explicitly reconciled and reapproved in both Task 20 documents.

**Retained workflow goal:** Preserve import-owned planned recipes, make a
complete saved/first-started executed recipe authoritative, and let
workers/Admin edit it through the future reconciled Item Master projection.

**Architecture status:** The detailed architecture below predates the SKU and
published-snapshot contract and must be reconciled before any schema or code
choice is approved. The whole-snapshot, transactional, and legacy-preservation
principles remain inputs to that bounded revision.

**Tech Stack:** Python 3, FastAPI, direct `sqlite3`, Jinja2 server-rendered HTML, vanilla JavaScript ES modules, CSS, pytest, Node's built-in test runner, and repo-local Playwright.

## Global Constraints

- `README.md` is authoritative; preserve the bounded FastAPI/SQLite extrusion-terminal pilot.
- Do not use this plan or the current Task 20 specification to begin coding.
  First reconcile both against the latest Item Master design and approve the
  revised contract and implementation plan.
- Follow `docs/implementation-notes/sqlite-migration-and-deployment-playbook.md` for every schema and stored-data-meaning change.
- Derive the next migration version from `app/migrations.py` at implementation time; the current expected version is M007, but do not assume it if the registry has changed.
- The initial migration is schema-only: do not synthesize executed recipes or reinterpret any historical `actual_material_used` text.
- Preserve planned recipe data, legacy actual-material text, batch/lot, rolls, weights, timing, shifts, pallets, statuses, import-source rows, and all unrelated production data.
- An executed recipe is always one complete snapshot; never merge executed and planned rows.
- Recipe rows are limited to seven, percentages must be positive, and the complete recipe must total exactly `100%`.
- First production start creates the executed snapshot in the same transaction as the existing start operation and adds no separate version increment.
- Recipe replacement is atomic and increments the card version exactly once; stale writes require reload.
- Catalogue replacement is atomic, never changes a card version, and never rewrites planned, executed, legacy, or batch data.
- Re-import remains row-atomic and never edits executed recipes. After production has started, block the complete order row when the incoming planned recipe differs semantically from the executed recipe.
- Batch/lot stays independent from executed-recipe saving and is excluded from re-import recipe comparison.
- Use concise Bulgarian user-facing validation messages and preserve unsaved editor input after a rejected save.
- Do not add users, roles, permissions, notifications, historical normalization, or inventory integration in this implementation.
- Tests and browser checks must use temporary SQLite databases, never `data/extrusion_terminal.sqlite3`.
- UI completion requires live Playwright checks at both supported workstation viewport sizes and evidence under `artifacts/ui-checks/editable-executed-recipes/`.
- The implementing agent performs code review and verification. The user reviews only the finished UI and workflow.
- Do not stage or commit any change unless the user explicitly asks. Each checkpoint below replaces the writing-plans skill's default commit step with a recorded clean-test and self-review gate.

---

## Superseded Session Map And Resume Contract

The table below is retained to expose the old plan's dependencies. It is not an
active execution schedule, and its former **10–14 hour** estimate is withdrawn.
Re-estimate only after Item Master v1 is confirmed and both Task 20 documents
are reconciled and approved.

| Session | Tasks | Active-agent estimate | Deliverable | Resume evidence |
| --- | --- | ---: | --- | --- |
| 1. Catalogue and schema foundation | 1–3 | 2–3 h | Pure catalogue parser, M007-equivalent empty schema, atomic catalogue persistence/upload | Focused catalogue and migration tests pass; migration preservation reviewed |
| 2. Executed-recipe domain | 4–5 | 2–3 h | Shared validation, effective resolver, transactional full-snapshot save | Domain and persistence tests pass; legacy/batch preservation reviewed |
| 3. Lifecycle and import safety | 6–7 | 1.5–2 h | First-start snapshot and semantic re-import guard | Timing and import matrices pass; rollback/row-atomic behavior reviewed |
| 4. Shared Admin/Terminal workflow | 8–10 | 3–4 h | Catalogue endpoint, batch-only path, reusable editor, both rendered screens | Python render/route tests and JavaScript unit tests pass |
| 5. Integrated verification and handoff | 11–12 | 1.5–2 h | Live browser evidence, full suite, documentation, final self-review | Screenshots inspected, full verification output recorded, no unresolved diff issues |

At every session boundary, record in the active implementation handoff: completed checkbox numbers, exact commands and results, changed files, open failures, and the next unchecked step. Never mark a task complete solely because code exists; its stated tests and review gate must pass.

## File And Interface Map

### New files

- `app/material_catalog.py` — UTF-8 CSV decoding, exact header validation, whitespace normalization, catalogue dataclasses, duplicate detection, and search-text normalization. It performs no database I/O.
- `app/recipe_execution.py` — executed-recipe request parsing, normalized domain types, complete-snapshot validation, and semantic planned-versus-executed comparison. It performs no connection management.
- `app/static/js/recipe_editor_core.mjs` — pure editor state operations: add/remove rows, seven-row enforcement, category-filtered search, row validation helpers, decimal normalization, and kilogram display.
- `app/static/js/recipe_editor.mjs` — DOM adapter used by both Terminal and Admin, JSON save requests, inline errors, catalogue-version polling, draft preservation, and successful reload.
- `tests/test_material_catalog.py` — parser and catalogue validation tests.
- `tests/test_executed_recipe.py` — pure validation, normalization, and semantic comparison tests.
- `tests/test_executed_recipe_storage.py` — resolver, atomic replacement, version, and preservation tests.
- `tests/test_recipe_reimport_guard.py` — complete re-import compatibility/rejection matrix.
- `tests/js/recipe_editor_core.test.mjs` — pure browser-editor state tests.
- `scripts/create_editable_recipe_fixture.py` — guarded deterministic temporary database builder for live UI verification.
- `scripts/verify_editable_recipe_ui.mjs` — guarded repo-local Playwright workflow and screenshot verifier.
- `tests/test_editable_recipe_ui_scripts.py` — path, database-identity, dependency, and no-install safety tests for both scripts.
- `docs/implementation-notes/editable-executed-recipes.md` — durable implemented-schema, behavior, operations, and verification note; deployment status is recorded separately and never inferred.

### Existing files to modify

- `app/migrations.py` — append the next ordered schema migration and its rollback-safe DDL.
- `app/db.py` — catalogue persistence, executed-recipe fetch/resolution/save, batch-only update, and first-start transaction integration.
- `app/importer.py` — pre-write executed-recipe compatibility guard for overwrite imports.
- `app/main.py` — shared presentation mapping, catalogue settings routes, catalogue JSON/version endpoint, and Terminal/Admin executed-recipe save routes.
- `app/templates/admin_settings.html` — material-catalogue upload/status section.
- `app/templates/terminal.html` — effective-recipe read mode and shared editor hook; remove the legacy actual-material control.
- `app/templates/admin_card_detail.html` — keep planned input separate; add the same effective-recipe editor and independent batch fields.
- `app/static/css/app.css` — common recipe editor/read-mode styling and two supported viewport layouts.
- `tests/test_migrations.py` — empty-schema, predecessor, preservation, rollback, idempotency, integrity, and foreign-key checks.
- `tests/test_backup_recovery.py` — new tables and catalogue metadata survive backup/restore.
- `tests/test_production_timing.py` — first-start snapshot behavior and rollback/version tests.
- `tests/test_recipe_sync.py` — matching and blocked overwrite behavior without executed-row mutation.
- `tests/test_terminal_detail.py` — Terminal recipe read/edit rendering and control removal.
- `tests/test_admin_production_corrections.py` — Admin separation, shared saving, and legacy/batch preservation.
- `tests/test_admin_routes.py` — settings upload and catalogue status responses.
- `tests/test_terminal_sync.py` and `tests/test_terminal_v8_render.py` — catalogue-version notification and script/render safety.
- `v2-files/TASK-20-EDITABLE-EXECUTED-RECIPES.md` and `v2-files/PLAN.md` — after verification only, record source-complete/not-deployed status while retaining the three future follow-ups.

### Stable interfaces established by this plan

```python
# app/material_catalog.py
CATALOGUE_HEADERS: tuple[str, ...]

@dataclass(frozen=True)
class CatalogueItemInput:
    source_line: int
    category: str
    producer: str
    brand_family: str
    grade_code: str
    full_material_name: str
    display_name: str
    notes: str

@dataclass(frozen=True)
class CatalogueParseResult:
    items: tuple[CatalogueItemInput, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    @property
    def ok(self) -> bool: ...

def parse_material_catalog_csv(content: bytes) -> CatalogueParseResult: ...
def normalize_catalogue_text(value: object) -> str: ...
def normalized_identity(value: object) -> str: ...
```

```python
# app/recipe_execution.py
RecipeMaterialSource = Literal["planned_snapshot", "catalogue", "free_text"]

@dataclass(frozen=True)
class ExecutedRecipeRow:
    component_slot: str
    display_position: int
    material_category: str
    material_name: str
    canonical_full_name: str | None
    material_source: RecipeMaterialSource
    recipe_percent: Decimal

@dataclass(frozen=True)
class RecipeValidationResult:
    rows: tuple[ExecutedRecipeRow, ...]
    errors: tuple[str, ...]
    @property
    def ok(self) -> bool: ...

@dataclass(frozen=True)
class EffectiveRecipe:
    source: Literal["planned", "executed"]
    rows: tuple[ExecutedRecipeRow, ...]

RecipeSaveError = Literal[
    "validation", "stale_card", "stale_catalogue", "not_allowed", "shift_required"
]

@dataclass(frozen=True)
class RecipeSaveResult:
    ok: bool
    messages: tuple[str, ...]
    error_code: RecipeSaveError | None = None
    card_version: int | None = None
    effective_recipe: EffectiveRecipe | None = None

def validate_executed_recipe_rows(raw_rows: Sequence[Mapping[str, object]]) -> RecipeValidationResult: ...
def planned_components_to_snapshot(components: Sequence[Mapping[str, object]]) -> tuple[ExecutedRecipeRow, ...]: ...
def recipes_semantically_equal(
    incoming: Sequence[ParsedRecipeComponent],
    executed: Sequence[ExecutedRecipeRow],
    catalogue_items: Sequence[Mapping[str, object]],
) -> bool: ...
```

```python
# app/db.py
def fetch_catalogue_state(connection: sqlite3.Connection) -> dict[str, Any]: ...
def fetch_material_catalogue(connection: sqlite3.Connection) -> list[dict[str, Any]]: ...
def replace_material_catalogue(filename: str, parsed: CatalogueParseResult) -> RuleResult: ...
def fetch_executed_recipe_components(connection: sqlite3.Connection, card_id: int) -> list[dict[str, Any]]: ...
def resolve_effective_recipe(connection: sqlite3.Connection, card_id: int) -> EffectiveRecipe: ...
def replace_executed_recipe(
    card_id: int,
    loaded_version: int,
    catalogue_version: int,
    raw_rows: Sequence[Mapping[str, object]],
    *,
    require_active_shift: bool,
) -> RecipeSaveResult: ...
def update_recipe_batches_only(
    card_id: int,
    loaded_version: int,
    batches: Mapping[str, str],
    *,
    require_active_shift: bool,
) -> RuleResult: ...
```

Keep the existing general-purpose `RuleResult` unchanged. Executed-recipe saving returns the narrow `RecipeSaveResult` so routes can distinguish validation (`422`) from conflicts (`409`) without matching translated message text.

---

### Task 1: Pure Material Catalogue Parser

**Files:**
- Create: `app/material_catalog.py`
- Create: `tests/test_material_catalog.py`

**Interfaces:**
- Consumes: standard-library `csv`, `io`, `re`, and dataclasses only.
- Produces: `CATALOGUE_HEADERS`, `CatalogueItemInput`, `CatalogueParseResult`, `parse_material_catalog_csv()`, `normalize_catalogue_text()`, and `normalized_identity()` exactly as mapped above.

- [ ] **Step 1: Write the contract and successful-parse tests**

```python
def catalogue_csv(*rows: str) -> bytes:
    header = ",".join(CATALOGUE_HEADERS)
    return ("\n".join((header, *rows)) + "\n").encode("utf-8")


def test_parse_catalogue_normalizes_whitespace_and_retains_all_fields():
    result = parse_material_catalog_csv(catalogue_csv(
        " LDPE , ExxonMobil , Exceed , 1018 , LDPE   ExxonMobil 1018 , Exxon 1018 , film grade "
    ))
    assert result.ok
    assert result.items[0] == CatalogueItemInput(
        source_line=2,
        category="LDPE",
        producer="ExxonMobil",
        brand_family="Exceed",
        grade_code="1018",
        full_material_name="LDPE ExxonMobil 1018",
        display_name="Exxon 1018",
        notes="film grade",
    )
```

- [ ] **Step 2: Write one parameterized blocking-validation matrix**

```python
@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "CSV файлът няма заглавен ред"),
        (b"Category,Producer,BrandFamily,GradeCode,FullMaterialName,TechnologyCardDisplayName,Notes\n\xff", "валиден UTF-8"),
        (b"Category,FullMaterialName\nLDPE,LDPE A\n", "точно тези 7 колони"),
        (catalogue_csv(), "поне един материал"),
        (catalogue_csv(",P,B,G,LDPE A,A,N"), "Ред 2, Category"),
        (catalogue_csv("LDPE,P,B,G,,A,N"), "Ред 2, FullMaterialName"),
        (catalogue_csv("LDPE,P,B,G,LDPE A,,N"), "Ред 2, TechnologyCardDisplayName"),
        (catalogue_csv("LDPE,P,B,G,HDPE A,A,N"), "трябва да започва с 'LDPE '"),
        (catalogue_csv("LD;PE,P,B,G,LD;PE A,A,N"), "не може да съдържа ';'"),
    ],
)
def test_parse_catalogue_rejects_invalid_contract(content, message):
    result = parse_material_catalog_csv(content)
    assert not result.ok
    assert any(message in error for error in result.errors)
```

- [ ] **Step 3: Write duplicate identity and warning tests**

```python
def test_duplicate_full_name_is_case_insensitive_and_blocking():
    result = parse_material_catalog_csv(catalogue_csv(
        "LDPE,P,B,1,LDPE Exxon 1018,Exxon,N",
        "LDPE,P,B,2,ldpe exxon 1018,Other,N",
    ))
    assert not result.ok
    assert "Редове 2 и 3" in " ".join(result.errors)


def test_duplicate_display_name_with_distinct_full_names_is_warning():
    result = parse_material_catalog_csv(catalogue_csv(
        "Masterbatch,P,B,1,Masterbatch Green A,Green,N",
        "Masterbatch,P,B,2,Masterbatch Green B,Green,N",
    ))
    assert result.ok
    assert "Green" in " ".join(result.warnings)
```

- [ ] **Step 4: Run the new tests and observe the expected import failure**

Run: `source .venv/bin/activate && python -m pytest tests/test_material_catalog.py -q`

Expected: collection fails because `app.material_catalog` does not exist.

- [ ] **Step 5: Implement the minimal pure parser**

Use `utf-8-sig` decoding so a UTF-8 BOM is harmless but invalid byte sequences fail. Require `tuple(reader.fieldnames) == CATALOGUE_HEADERS`; do not accept reordered or additional columns. Normalize every string with `" ".join(str(value or "").split())`. Compare duplicates with `casefold()`. Accumulate all row/field errors before returning and emit duplicate-display warnings only if no canonical duplicate has collapsed the rows.

```python
CATALOGUE_HEADERS = (
    "Category", "Producer", "BrandFamily", "GradeCode",
    "FullMaterialName", "TechnologyCardDisplayName", "Notes",
)


def normalize_catalogue_text(value: object) -> str:
    return " ".join(str(value or "").split())


def normalized_identity(value: object) -> str:
    return normalize_catalogue_text(value).casefold()
```

- [ ] **Step 6: Run parser tests to green and inspect diagnostics**

Run: `source .venv/bin/activate && python -m pytest tests/test_material_catalog.py -q`

Expected: all catalogue parser tests pass and each failure includes its CSV line and field where applicable.

- [ ] **Step 7: Session-local review gate**

Run: `git diff -- app/material_catalog.py tests/test_material_catalog.py && git diff --check`

Check that the parser has no database dependency, does not silently drop duplicate display names, and does not decode with a replacement-error mode.

---

### Task 2: Schema-Only Executed Recipe And Catalogue Migration

**Files:**
- Create: `app/recipe_execution.py` (domain constants/dataclass needed by persistence)
- Modify: `app/migrations.py`
- Modify: `tests/test_migrations.py`

**Interfaces:**
- Consumes: current `Migration` registry and existing migration-test helpers.
- Produces: the next migration containing `material_catalog_state`, `material_catalog_items`, and `executed_recipe_components`; `EXECUTED_RECIPE_SLOTS` and `ExecutedRecipeRow` in `app/recipe_execution.py`.

- [ ] **Step 1: Add fresh-schema and exact-table tests**

```python
def test_latest_schema_has_empty_executed_recipe_and_catalogue_tables(db_path):
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM executed_recipe_components").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM material_catalog_items").fetchone()[0] == 0
        state = connection.execute(
            "SELECT catalogue_version, source_filename, row_count FROM material_catalog_state WHERE id = 1"
        ).fetchone()
        assert state == (0, None, 0)
```

- [ ] **Step 2: Add preservation and no-backfill fixtures**

Parameterize the existing predecessor builders across every schema version still supported by `tests/test_migrations.py`. In each, create one card with representative planned rows and legacy values available at that version; in the latest predecessor include all seven planned rows, legacy `actual_material_used`, batch/lot, a roll, timing, and import-source data. Capture those rows before migration; initialize; assert byte-for-value equality afterward and assert zero executed rows. Reuse the existing predecessor builders instead of constructing an unsupported schema by hand.

- [ ] **Step 3: Add idempotency, failure rollback, and integrity assertions**

```python
def assert_database_healthy(connection):
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
```

Run initialization twice and compare schema/data. Inject a failure after the first new table creation using the migration module's existing failure-hook pattern; assert none of the new tables or migration-version row survives.

- [ ] **Step 4: Run focused tests to establish the failure**

Run: `source .venv/bin/activate && python -m pytest tests/test_migrations.py -q`

Expected: the new schema assertions fail because the tables and registry entry do not exist.

- [ ] **Step 5: Add the migration DDL**

At implementation time inspect `MIGRATIONS`; use the next integer and name it `editable_executed_recipes`. The expected DDL shape is:

```sql
CREATE TABLE material_catalog_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    catalogue_version INTEGER NOT NULL DEFAULT 0 CHECK (catalogue_version >= 0),
    source_filename TEXT,
    imported_at TEXT,
    row_count INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    warnings_json TEXT NOT NULL DEFAULT '[]'
);
INSERT INTO material_catalog_state (id) VALUES (1);

CREATE TABLE material_catalog_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL CHECK (TRIM(category) <> ''),
    producer TEXT NOT NULL DEFAULT '',
    brand_family TEXT NOT NULL DEFAULT '',
    grade_code TEXT NOT NULL DEFAULT '',
    full_material_name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK (TRIM(full_material_name) <> ''),
    display_name TEXT NOT NULL CHECK (TRIM(display_name) <> ''),
    notes TEXT NOT NULL DEFAULT '',
    source_line INTEGER NOT NULL CHECK (source_line >= 2)
);

CREATE TABLE executed_recipe_components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    component_slot TEXT NOT NULL CHECK (component_slot IN (
        'raw_material_a', 'raw_material_b', 'raw_material_c',
        'linear_pe', 'antistatic', 'masterbatch', 'chalk'
    )),
    display_position INTEGER NOT NULL CHECK (display_position BETWEEN 1 AND 7),
    material_category TEXT NOT NULL CHECK (TRIM(material_category) <> ''),
    material_name TEXT NOT NULL CHECK (TRIM(material_name) <> ''),
    canonical_full_name TEXT,
    material_source TEXT NOT NULL CHECK (material_source IN (
        'planned_snapshot', 'catalogue', 'free_text'
    )),
    recipe_percent NUMERIC NOT NULL CHECK (recipe_percent > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(card_id, component_slot),
    UNIQUE(card_id, display_position),
    CHECK (
        (material_source = 'catalogue' AND TRIM(COALESCE(canonical_full_name, '')) <> '')
        OR (
            material_source IN ('planned_snapshot', 'free_text')
            AND canonical_full_name IS NULL
        )
    )
);
```

Add indexes on `material_catalog_items(category COLLATE NOCASE)` and `executed_recipe_components(card_id, display_position)`. Do not add executed rows or catalogue items in the migration.

- [ ] **Step 6: Run the migration suite and schema checks**

Run: `source .venv/bin/activate && python -m pytest tests/test_migrations.py -q`

Expected: all predecessor, preservation, rollback, idempotency, integrity, and foreign-key tests pass.

- [ ] **Step 7: Review the migration against the deployment playbook**

Run: `sed -n '1,260p' docs/implementation-notes/sqlite-migration-and-deployment-playbook.md && git diff -- app/migrations.py app/recipe_execution.py tests/test_migrations.py && git diff --check`

Confirm there is no data-copy statement from `recipe_actual_entries` or `recipe_components` into the executed table and no DDL alters existing columns.

---

### Task 3: Atomic Catalogue Persistence, Settings Upload, And Backup

**Files:**
- Modify: `app/db.py`
- Modify: `app/main.py`
- Modify: `app/templates/admin_settings.html`
- Modify: `tests/test_material_catalog.py`
- Modify: `tests/test_admin_routes.py`
- Modify: `tests/test_backup_recovery.py`

**Interfaces:**
- Consumes: `CatalogueParseResult` from Task 1 and the catalogue tables from Task 2.
- Produces: `fetch_catalogue_state()`, `fetch_material_catalogue()`, and `replace_material_catalogue()`; `POST /admin/settings/material-catalogue`; catalogue metadata in the existing settings context.

- [ ] **Step 1: Write atomic replacement tests**

Seed a production card and catalogue A, replace with catalogue B, and assert only B is active, metadata shows B's filename/count/warnings, catalogue version changes from `1` to `2`, and the card version/data remain exactly unchanged. Pass a failed parse result after B and assert items, metadata, catalogue version, and card remain exactly unchanged.

```python
result = replace_material_catalogue("catalogue-b.csv", parsed_b)
assert result.ok
with connect() as connection:
    assert fetch_catalogue_state(connection)["catalogue_version"] == 2
    assert [row["full_material_name"] for row in fetch_material_catalogue(connection)] == ["HDPE B"]
```

- [ ] **Step 2: Write route tests for success, warnings, and retained prior data**

Post `multipart/form-data` to `/admin/settings/material-catalogue`. Assert a successful redirect returns to `/admin/settings`, the page shows filename/time/count/version and duplicate-display warning, and an invalid follow-up upload renders line-specific errors while still showing the previous active catalogue metadata.

- [ ] **Step 3: Extend backup/restore coverage**

Import a catalogue, save a representative executed row only after Task 5 is available (initially catalogue alone), run the existing SQLite-safe backup/restore helpers, and assert the catalogue state/items are identical in the restored database. Add the executed-row assertion in Task 5 without duplicating the backup fixture.

- [ ] **Step 4: Run focused tests to establish failures**

Run: `source .venv/bin/activate && python -m pytest tests/test_material_catalog.py tests/test_admin_routes.py tests/test_backup_recovery.py -q`

Expected: persistence and route tests fail because the functions and upload route do not exist.

- [ ] **Step 5: Implement transactional replacement**

`replace_material_catalogue()` must reject `not parsed.ok` before opening a write transaction. For a valid result, use `BEGIN IMMEDIATE`, delete active items, bulk insert all parsed rows, and update the singleton metadata/version in the same transaction. Serialize warnings as UTF-8 JSON with `ensure_ascii=False`. Catch database errors, roll back, and return one non-success `RuleResult` without altering the old catalogue.

- [ ] **Step 6: Add settings context, route, and UI**

Read the file once with `await csv_file.read()`, parse the entire payload, and call replacement only when parsing succeeds. Render blocking errors in the response so the submitted failure is visible; on success redirect with a notice code. Add one section titled `Каталог материали` containing file input, upload button, empty state, and active filename/timestamp/row count/version/warnings. Do not add item-level CRUD controls.

- [ ] **Step 7: Run focused tests to green**

Run: `source .venv/bin/activate && python -m pytest tests/test_material_catalog.py tests/test_admin_routes.py tests/test_backup_recovery.py -q`

Expected: all selected tests pass.

- [ ] **Step 8: Session 1 checkpoint**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_migrations.py tests/test_material_catalog.py tests/test_admin_routes.py tests/test_backup_recovery.py -q
git diff --check
```

Review all Task 1–3 diffs for atomic replacement, empty migration state, exact CSV contract, existing-data preservation, and absence of writes to the runtime database. Record the test count and next task; do not stage or commit.

---
### Task 4: Executed Recipe Validation And Semantic Comparison

**Files:**
- Modify: `app/recipe_execution.py`
- Create: `tests/test_executed_recipe.py`

**Interfaces:**
- Consumes: `RECIPE_SOURCE_FIELDS`, `ParsedRecipeComponent`, `Decimal`, and catalogue rows with `category`, `full_material_name`, and `display_name`.
- Produces: `RecipeValidationResult`, `EffectiveRecipe`, `RecipeSaveError`, `RecipeSaveResult`, `validate_executed_recipe_rows()`, `planned_components_to_snapshot()`, and `recipes_semantically_equal()` exactly as declared in the interface map.

- [ ] **Step 1: Write valid normalization and planned-snapshot tests**

```python
def test_validate_executed_recipe_normalizes_comma_decimal_and_positions():
    result = validate_executed_recipe_rows([
        {
            "component_slot": "raw_material_a",
            "display_position": "1",
            "material_category": " LDPE ",
            "material_name": " Exxon 1018 ",
            "canonical_full_name": "LDPE ExxonMobil 1018",
            "material_source": "catalogue",
            "recipe_percent": "72,5",
        },
        {
            "component_slot": "masterbatch",
            "display_position": "2",
            "material_category": "Masterbatch",
            "material_name": "Blue",
            "canonical_full_name": None,
            "material_source": "free_text",
            "recipe_percent": "27,5",
        },
    ])
    assert result.ok
    assert result.rows[0].recipe_percent == Decimal("72.5")
    assert result.rows[1].canonical_full_name is None
```

Assert `planned_components_to_snapshot()` retains source-slot order, assigns positions `1..n`, copies category/material/percentage, and marks every row `planned_snapshot` with no canonical name.

- [ ] **Step 2: Write the complete invalid-recipe matrix**

Cover zero rows, eight rows, unknown and duplicate slots, positions outside `1..7`, duplicate/gapped positions, blank category/material, unknown source, missing catalogue canonical name, false canonical name on free text, zero/negative/non-finite/non-numeric percentages, and totals `99.99` and `100.01`. Assert row-specific Bulgarian messages and one exact-total message.

```python
@pytest.mark.parametrize("bad_percent", ["0", "-1", "nan", "inf", "word"])
def test_invalid_percent_is_rejected_without_partial_rows(bad_percent):
    rows = valid_recipe_rows()
    rows[0]["recipe_percent"] = bad_percent
    result = validate_executed_recipe_rows(rows)
    assert not result.ok
    assert any("Ред 1" in message for message in result.errors)
```

- [ ] **Step 3: Write semantic-comparison tests before implementation**

Create ordered parsed planned components and executed rows. Prove equality ignores repeated/surrounding whitespace and case and compares decimals numerically. Then prove inequality for category, material, percentage, added row, removed row, and swapped positions.

For a catalogue-backed executed row, test all three cases:

```python
def test_catalogue_comparison_accepts_unambiguous_full_or_display_name():
    assert recipes_semantically_equal(incoming_with("LDPE ExxonMobil 1018"), executed_catalogue_row(), catalogue())
    assert recipes_semantically_equal(incoming_with("Exxon 1018"), executed_catalogue_row(), catalogue())


def test_catalogue_comparison_rejects_ambiguous_display_name():
    duplicate_display_catalogue = catalogue_with_two_full_names(display_name="Green")
    assert not recipes_semantically_equal(
        incoming_with("Green"), executed_green_a(), duplicate_display_catalogue
    )
```

Also assert planned-snapshot/free-text material comparison is normalized-exact only: no substring, edit-distance, or alias guessing.

- [ ] **Step 4: Run tests and observe missing functions**

Run: `source .venv/bin/activate && python -m pytest tests/test_executed_recipe.py -q`

Expected: tests fail because the validation/comparison functions are not implemented.

- [ ] **Step 5: Implement validation as one normalization pass**

Use `Decimal(text.replace(",", "."))`, require `.is_finite()`, sort only after validating positions, and return no normalized rows when any error exists. Require `set(display_position) == set(range(1, len(rows) + 1))`; this forbids hidden gaps. Use the exact `RECIPE_SOURCE_FIELDS` set for slots.

```python
total = sum((row.recipe_percent for row in normalized_rows), Decimal("0"))
if total != Decimal("100"):
    errors.append("Сборът на процентите трябва да бъде точно 100%.")
```

- [ ] **Step 6: Implement position-sensitive semantic comparison**

Order incoming components by `RECIPE_SOURCE_FIELDS` and executed rows by `display_position`; reject unequal lengths before comparing. Normalize category/name with collapsed whitespace plus `casefold()` and compare percentages as `Decimal`. For catalogue-backed rows, resolve the incoming name within the normalized category against active catalogue full and display names; accept only when the candidate set has one canonical full name equal to the executed row's canonical snapshot. Never compare database IDs and never use fuzzy matching.

- [ ] **Step 7: Run domain tests to green and inspect the public types**

Run: `source .venv/bin/activate && python -m pytest tests/test_executed_recipe.py tests/test_recipe_parser.py -q`

Expected: all tests pass without changing existing planned-recipe parsing.

- [ ] **Step 8: Review the domain boundary**

Run: `git diff -- app/recipe_execution.py tests/test_executed_recipe.py && git diff --check`

Confirm full-snapshot validation is independent of FastAPI/forms/database connections, every public signature matches the interface map, and semantic equality cannot accept an ambiguous display name.

---

### Task 5: Effective Resolver And Atomic Executed-Recipe Save

**Files:**
- Modify: `app/db.py`
- Create: `tests/test_executed_recipe_storage.py`
- Modify: `tests/test_backup_recovery.py`

**Interfaces:**
- Consumes: Task 2 tables and Task 4 normalized `ExecutedRecipeRow` values.
- Produces: `fetch_executed_recipe_components()`, `resolve_effective_recipe()`, `replace_executed_recipe()`, and populated `RecipeSaveResult` values described in the interface map.

- [ ] **Step 1: Write resolver fallback and override tests**

```python
def test_effective_recipe_uses_all_planned_rows_when_no_executed_rows(connection, card_id):
    recipe = resolve_effective_recipe(connection, card_id)
    assert recipe.source == "planned"
    assert [row.material_source for row in recipe.rows] == ["planned_snapshot"] * len(recipe.rows)


def test_one_complete_executed_snapshot_overrides_all_planned_rows(connection, card_id):
    seed_executed_recipe(connection, card_id, changed_rows())
    recipe = resolve_effective_recipe(connection, card_id)
    assert recipe.source == "executed"
    assert recipe.rows == tuple(changed_rows())
```

Do not create a test or code path for sparse per-row fallback; it is forbidden.

- [ ] **Step 2: Write successful save and version tests**

Save an unchanged planned recipe and assert executed rows now exist and resolution says `executed`. Save changed material/percentage, add a row, and remove a row; after each valid save assert full replacement and exactly one card-version increment.

- [ ] **Step 3: Write preservation, stale, and rollback tests**

Seed legacy `actual_material_used`, batch values, planned rows, rolls, and timing. Assert successful executed-recipe replacement changes none of them. Assert stale card version leaves the previous snapshot and version unchanged. Inject an exception after deletion but before all inserts and assert the previous snapshot is restored. Submit every Task 4 validation failure and assert no database write.

- [ ] **Step 4: Write catalogue-version behavior tests**

Prove:

- a current catalogue selection is resolved by canonical full name and the server copies active category/display/full name rather than trusting browser text;
- after catalogue replacement, an unchanged already-saved catalogue row can be retained even if its item disappeared;
- a newly selected item from a stale page is accepted only when that canonical item still resolves exactly in the active catalogue;
- a stale selection that disappeared or changed is rejected with a refresh message and the draft/snapshot remain unchanged; and
- a `free_text` row needs no catalogue identity and remains visibly marked; and
- an unchanged planned/executed material absent from the catalogue remains displayable and can be deliberately preserved without being relabelled as a catalogue selection.

- [ ] **Step 5: Write the non-empty-batch removal test**

Seed `batch_lot='LOT-9'` for `masterbatch`, omit that slot from the submitted recipe, and assert the save is rejected. Change the material while retaining the slot and assert `LOT-9` remains. Clear the batch through the independent batch path, then assert row removal succeeds.

- [ ] **Step 6: Run storage tests and observe missing persistence**

Run: `source .venv/bin/activate && python -m pytest tests/test_executed_recipe_storage.py -q`

Expected: tests fail because executed-recipe fetch, resolution, and saving do not exist.

- [ ] **Step 7: Implement fetch and effective resolution**

Convert stored decimals through the existing database-decimal helpers. Planned fallback must call `fetch_recipe_components()` and `planned_components_to_snapshot()`; executed resolution returns every stored row in `display_position, id` order. Treat any executed rows as a whole-snapshot override, while relying on write/migration invariants to prevent invalid partial snapshots.

- [ ] **Step 8: Implement transactional replacement and catalogue revalidation**

Use `BEGIN IMMEDIATE`. In this order: validate lifecycle/shift/card version; normalize the complete request; load current effective rows and non-empty batches; enforce removal protection; revalidate catalogue-backed rows; delete all executed rows; insert all normalized canonical rows; update `cards.version = version + 1`; fetch the resulting effective recipe; commit. Any rejected check returns before delete; any exception after delete rolls back.

Catalogue-backed request handling must use this rule:

1. First compare the submitted row with the same slot in the currently effective executed snapshot. If category, display name, canonical full name, source, and percentage are unchanged after documented normalization, preserve the stored snapshots exactly even when the item disappeared or was renamed in the active catalogue.
2. Otherwise treat it as a new selection and resolve its submitted canonical full name against the current active catalogue.
3. If exactly one current item exists, copy its active category/display/full name and accept it even if the page version is older.
4. Otherwise reject it. Never substitute a same-display-name item.

- [ ] **Step 9: Extend backup/restore and run storage tests to green**

Add representative executed rows with all three sources to the Task 3 backup fixture and compare them exactly after restore.

Run: `source .venv/bin/activate && python -m pytest tests/test_executed_recipe_storage.py tests/test_backup_recovery.py -q`

Expected: all tests pass and restored snapshot provenance/full-name values are unchanged.

- [ ] **Step 10: Session 2 checkpoint**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_executed_recipe.py tests/test_executed_recipe_storage.py tests/test_backup_recovery.py -q
git diff --check
```

Review transaction starts/returns/exceptions, single version increment, whole-snapshot behavior, legacy actual-material preservation, batch protection, and catalogue trust boundaries. Record results; do not stage or commit.

---

### Task 6: Atomic First-Start Snapshot

**Files:**
- Modify: `app/db.py` (`start_production_timing()` and a connection-scoped insert helper)
- Modify: `tests/test_production_timing.py`

**Interfaces:**
- Consumes: `resolve_effective_recipe()`, `planned_components_to_snapshot()`, the executed table, and existing timing/start validation.
- Produces: first pending-to-running transition creates `planned_snapshot` rows when no executed snapshot exists, inside the normal start transaction.

- [ ] **Step 1: Write automatic snapshot and exact-version tests**

```python
def test_first_start_atomically_snapshots_current_plan(db_path, pending_card):
    before_version = fetch_card(pending_card)["version"]
    result = start_production_timing(pending_card, before_version, require_active_shift=True)
    assert result.ok
    card = fetch_card(pending_card)
    assert card["version"] == before_version + 1
    assert resolve_recipe(pending_card).source == "executed"
    assert {row.material_source for row in resolve_recipe(pending_card).rows} == {"planned_snapshot"}
```

Assert copied slot/category/material/percentage/order exactly match the normalized planned rows and the Terminal-visible effective values do not change.

- [ ] **Step 2: Write pre-saved snapshot preservation test**

Save a changed executed recipe while the card is pending, start it, and assert start creates no new executed IDs, changes no recipe value/timestamp, and increments the card version only once for start.

- [ ] **Step 3: Write failed-start rollback matrix**

For stale version, no active shift, occupied machine, missing/invalid planned recipe, existing open timing segment, and injected timing insert failure, assert status/timing/version/executed rows remain unchanged. The invalid planned recipe case applies only when no valid executed snapshot exists; a valid pre-saved executed snapshot is sufficient for recipe execution.

- [ ] **Step 4: Run focused timing tests to establish failures**

Run: `source .venv/bin/activate && python -m pytest tests/test_production_timing.py -q`

Expected: new snapshot assertions fail; existing timing tests remain green.

- [ ] **Step 5: Refactor start to one unconditional immediate transaction**

Start `BEGIN IMMEDIATE` regardless of `require_active_shift` so snapshot existence and lifecycle transition cannot race. Preserve the existing validation order and messages. After all validation and before status/timing writes, fetch executed rows; if absent, parse/fetch the current planned recipe, require a valid non-empty total-100 snapshot, and insert all rows with `planned_snapshot`. Then perform the existing one card update and timing insert. Use the same exception boundary to roll back all three effects.

- [ ] **Step 6: Run the timing and executed-storage tests to green**

Run: `source .venv/bin/activate && python -m pytest tests/test_production_timing.py tests/test_executed_recipe_storage.py -q`

Expected: all tests pass; snapshot IDs appear only on the first start when none existed.

- [ ] **Step 7: Review transaction and lifecycle scope**

Run: `git diff -- app/db.py tests/test_production_timing.py && git diff --check`

Confirm pause, resume, finish, awaiting-rewinding, and finalization do not call the snapshot helper; failed start cannot leave rows; successful start has one card-version increment.

---

### Task 7: Started-Card Re-import Compatibility Guard

**Files:**
- Modify: `app/importer.py`
- Create: `tests/test_recipe_reimport_guard.py`
- Modify: `tests/test_recipe_sync.py`

**Interfaces:**
- Consumes: `parse_recipe_source_fields()`, `fetch_executed_recipe_components()`, `fetch_material_catalogue()`, and `recipes_semantically_equal()`.
- Produces: `validate_started_recipe_overwrite(connection, card_id, incoming_card) -> RuleResult`, called before any overwrite mutation.

- [ ] **Step 1: Write allowed-case tests**

Cover an unstarted card without executed rows, then a started card whose incoming recipe equals executed after case/whitespace/decimal normalization, and a catalogue-backed row matched by unique canonical full or display name. Assert successful matching overwrite updates planned/imported fields and `card_import_sources`, increments the normal import version, and leaves executed rows, batches, and catalogue state byte-for-value unchanged.

- [ ] **Step 2: Write the complete mismatch matrix**

Parameterize category, material, percentage, added row, removed row, and swapped position differences. For each, snapshot the entire card row, planned rows, executed rows, batch rows, card-import-source row, and catalogue state before import. Assert the row is reported blocked with the approved Bulgarian meaning and every snapshot is identical afterward.

```python
RECIPE_CONFLICT_TEXT = (
    "Поръчката е започната или завършена и реално използваната рецепта "
    "(материали или проценти) е променена. Повторният импорт не може да я замени. "
    "Коригирайте реалната рецепта през Админ/Терминал или импортирайте "
    "съвпадаща планирана рецепта."
)
```

- [ ] **Step 3: Write exclusions and row-independence tests**

Change batch/lot only and assert it creates no import conflict. Import a CSV with one blocked started card and one independent valid card; assert the first is untouched, the second updates, `rows_seen/rows_imported/skipped` are correct, and both per-row result records are present. Assert a historical completed card with no executed snapshot retains the initial-phase planned fallback behavior rather than receiving synthesized rows.

- [ ] **Step 4: Run import tests and observe missing guard**

Run: `source .venv/bin/activate && python -m pytest tests/test_recipe_reimport_guard.py tests/test_recipe_sync.py -q`

Expected: mismatch cases incorrectly overwrite planned/imported data until the guard is added.

- [ ] **Step 5: Implement the guard before every card mutation**

Extend `find_existing_import_card()` (or a connection-local follow-up query) to obtain `first_started_at`/`finished_at`. Only compare when production has started and executed rows exist. Parse incoming planned fields once; use the existing import validation failure first, then semantic comparison. Place the guard after stale-source/release/recipe parsing checks but before `update_imported_card_fields()` so no card, source, or planned row write has occurred.

The import batch and its per-row blocked result may record the attempt; `card_import_sources` for the blocked order must not change. Continue the CSV loop after `block_import_row()`.

- [ ] **Step 6: Run the complete focused import matrix**

Run: `source .venv/bin/activate && python -m pytest tests/test_recipe_reimport_guard.py tests/test_recipe_sync.py tests/test_baseline.py -q`

Expected: all matching, mismatch, batch-exclusion, historical-fallback, and independent-row cases pass.

- [ ] **Step 7: Session 3 checkpoint**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_production_timing.py tests/test_executed_recipe.py tests/test_executed_recipe_storage.py tests/test_recipe_reimport_guard.py tests/test_recipe_sync.py -q
git diff --check
```

Review the first-start and import paths together: once a new card starts it must have a snapshot; a matching re-import may update only the plan/imported record; a differing re-import must update nothing owned by that order. Record results; do not stage or commit.

---

### Task 8: Shared Presentation, JSON Routes, And Batch-Only Persistence

**Files:**
- Modify: `app/db.py`
- Modify: `app/main.py`
- Modify: `tests/test_terminal_detail.py`
- Modify: `tests/test_admin_production_corrections.py`
- Modify: `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: Task 3 catalogue reads and Task 5 shared effective-recipe save/resolver.
- Produces: `build_effective_recipe_rows(card)`, `GET /material-catalogue.json`, `POST /terminal/cards/{card_id}/executed-recipe`, `POST /admin/cards/{card_id}/executed-recipe`, and `update_recipe_batches_only()`.

- [ ] **Step 1: Write shared presentation tests**

For a card without executed rows, assert Terminal/Admin row dictionaries show planned category/material/percent/kg and the batch belonging to the same component slot. After saving a changed snapshot, assert both contexts show the same complete executed rows, their `material_source`/canonical metadata, recalculated kilograms, and unchanged batch. Assert Admin's separate planned-source fields still show the imported plan.

- [ ] **Step 2: Write catalogue JSON route tests**

```python
def test_catalogue_json_contains_version_and_disambiguation_fields(client, seeded_catalogue):
    response = client.get("/material-catalogue.json")
    assert response.status_code == 200
    body = response.json()
    assert body["catalogue_version"] == 1
    assert set(body["items"][0]) >= {
        "category", "producer", "brand_family", "grade_code",
        "full_material_name", "display_name",
    }
```

Assert the response has `Cache-Control: no-store` so polling cannot reuse stale metadata.

- [ ] **Step 3: Write Terminal/Admin recipe-save route tests**

Post the same JSON payload to both routes. Terminal must require an active shift and an eligible visible card; Admin uses the existing production-correction lifecycle set without requiring a terminal shift. Success returns `200` with `ok`, new `card_version`, and serialized effective rows. Validation returns `422` with row messages; stale card returns `409`; stale/invalid catalogue selection returns `409`. Every failure response echoes no trusted HTML and leaves database data unchanged.

```json
{
  "loaded_version": 4,
  "catalogue_version": 2,
  "rows": [
    {
      "component_slot": "raw_material_a",
      "display_position": 1,
      "material_category": "LDPE",
      "material_name": "Exxon 1018",
      "canonical_full_name": "LDPE ExxonMobil 1018",
      "material_source": "catalogue",
      "recipe_percent": "100"
    }
  ]
}
```

- [ ] **Step 4: Write batch-only preservation tests**

Submit batch values through Terminal and the Admin production-material endpoint. Seed non-empty legacy `actual_material_used` first. Assert only `batch_lot` (plus the existing mirrored raw-material-A batch field where still required for compatibility) changes; legacy actual-material text is identical and no executed rows are created/replaced. Assert normal stale version and Terminal shift checks still apply. Submit Admin's planned/global Save All form without batch ownership and assert it leaves both batch and executed rows unchanged.

- [ ] **Step 5: Run focused route tests to establish failures**

Run: `source .venv/bin/activate && python -m pytest tests/test_terminal_detail.py tests/test_admin_production_corrections.py tests/test_admin_routes.py -q`

Expected: effective presentation/JSON routes are missing and current material saving would overwrite actual-material text.

- [ ] **Step 6: Attach effective recipe data to Admin and Terminal**

Where card-detail loaders already attach `recipe_components` and `recipe_actual_entries`, also attach resolved effective recipe data for Admin/Terminal consumers. Replace `build_terminal_recipe_rows()` with `build_effective_recipe_rows()` and give every row these keys:

```python
{
    "component_slot": row.component_slot,
    "display_position": row.display_position,
    "material_category": row.material_category,
    "material_name": row.material_name,
    "canonical_full_name": row.canonical_full_name,
    "material_source": row.material_source,
    "recipe_percent_edit": decimal_text(row.recipe_percent),
    "recipe_percent": recipe_percent_display(row.recipe_percent, rounded=True),
    "planned_kg": planned_kg_display(card, row.recipe_percent, rounded=True),
    "batch": batch_by_slot.get(row.component_slot, ""),
}
```

Keep this presentation mapping specific to the Admin and Terminal card contexts so unrelated output paths retain their existing contracts.

- [ ] **Step 7: Implement JSON serialization and shared save routes**

Add one request parser in `app/main.py` that requires integer `loaded_version`, integer `catalogue_version`, and list `rows`. Both routes call the same database function with only `require_active_shift` and terminal-availability validation differing. Map validation/stale/success to the tested statuses and set `Cache-Control: no-store` on catalogue reads.

- [ ] **Step 8: Replace actual-material writes with batch-only writes**

Parse only names beginning `batch_lot__`. In `_upsert_recipe_actual_entry`, add a batch-only SQL path whose conflict update changes `component_label`, `planned_material` where the existing compatibility behavior requires it, `batch_lot`, and `updated_at`—never `actual_material_used`. Change Terminal/Admin material endpoints to use that path. Remove material/batch handling from `save_all_admin_card_changes()` so the global Admin save owns only its existing planned/imported and other non-material ledgers; the dedicated batch form owns batches. Remove `actual_material__*` parsing from active forms while retaining read compatibility for historical data.

- [ ] **Step 9: Run backend route tests to green**

Run: `source .venv/bin/activate && python -m pytest tests/test_terminal_detail.py tests/test_admin_production_corrections.py tests/test_admin_routes.py tests/test_executed_recipe_storage.py -q`

Expected: shared save/resolver responses pass and all legacy actual-material preservation assertions pass.

- [ ] **Step 10: Review endpoint trust and separation**

Run: `git diff -- app/db.py app/main.py tests/test_terminal_detail.py tests/test_admin_production_corrections.py tests/test_admin_routes.py && git diff --check`

Confirm Terminal cannot bypass the active-shift/visible-card rule, Admin save never writes planned fields, Admin planned save never writes executed rows, and no active route sends an empty actual-material replacement.

---

### Task 9: Reusable Recipe Editor State And DOM Controller

**Files:**
- Create: `app/static/js/recipe_editor_core.mjs`
- Create: `app/static/js/recipe_editor.mjs`
- Create: `tests/js/recipe_editor_core.test.mjs`
- Modify: `tests/test_terminal_sync.py`
- Modify: `tests/test_terminal_v8_render.py`

**Interfaces:**
- Consumes: server-rendered JSON blocks containing `{cardId, loadedVersion, catalogueVersion, targetGrossKg, saveUrl, canEdit, rows}` and catalogue endpoint `{catalogue_version, items}`.
- Produces: `attachRecipeEditors(root = document)`, plus pure exports `createEditorState`, `addRecipeRow`, `removeRecipeRow`, `setCategory`, `selectCatalogueItem`, `useFreeText`, `setPercent`, `searchCatalogue`, `calculatedKg`, and `buildRecipePayload`.

- [ ] **Step 1: Write pure initial-state and add/remove tests**

```javascript
test("add uses the first unused stable slot and stops at seven rows", () => {
  let state = createEditorState(fixtureRows.slice(0, 2), fixtureCatalogue);
  state = addRecipeRow(state);
  assert.equal(state.rows[2].componentSlot, "raw_material_c");
  while (state.rows.length < 7) state = addRecipeRow(state);
  assert.throws(() => addRecipeRow(state), /седем/);
});

test("remove compacts positions but refuses a row with a batch", () => {
  assert.throws(() => removeRecipeRow(stateWithBatch, "masterbatch"), /партидата/);
  const next = removeRecipeRow(stateWithoutBatch, "masterbatch");
  assert.deepEqual(next.rows.map(row => row.displayPosition), [1, 2]);
});
```

Also prove at least one row must remain and changing material retains the row's batch value.

- [ ] **Step 2: Write category search and disambiguation tests**

Search category case-insensitively across display name, full name, producer, brand family, and grade code. Assert no cross-category result appears. Category choices are the union of active catalogue categories and categories already present in the current recipe, so an unmatched existing row remains editable; a newly added row receives no invented permanent category. When two items share a display name, assert `resultLabel` includes canonical full name plus producer/grade so each option is distinguishable.

- [ ] **Step 3: Write selection/free-text/payload tests**

Selecting a result must copy its category/display/full name and source `catalogue`; direct typing alone must not become catalogue-backed. `useFreeText()` must require a deliberate call, clear canonical identity, retain category, and mark `free_text`. `buildRecipePayload()` must include every complete row, loaded/card catalogue versions, comma-normalized percentage strings, stable slots, and normalized positions.

- [ ] **Step 4: Write calculation tests**

```javascript
test("calculated kilograms follows ordered gross times entered percent", () => {
  assert.equal(calculatedKg("1250", "12,5"), "156.25");
  assert.equal(calculatedKg("1250", ""), "");
});
```

Use exact decimal-string arithmetic or an integer-scaled helper sufficient for the accepted percentage/weight precision; do not expose binary-float tails.

- [ ] **Step 5: Run JavaScript tests and observe missing modules**

Run: `node --test tests/js/recipe_editor_core.test.mjs`

Expected: module-not-found failure.

- [ ] **Step 6: Implement immutable editor-state operations**

Use this fixed slot order, imported from a single exported constant in the core module:

```javascript
export const RECIPE_SLOTS = [
  "raw_material_a", "raw_material_b", "raw_material_c", "linear_pe",
  "antistatic", "masterbatch", "chalk",
];
```

Return new state/row objects rather than mutating the server snapshot so Cancel can restore it exactly. Assign text only through `textContent`/input values; never interpolate catalogue or free-text values into HTML strings.

- [ ] **Step 7: Implement the DOM lifecycle**

`attachRecipeEditors()` finds `[data-recipe-editor]`, parses its adjacent JSON blocks, and provides:

- read mode with top-right `Редактирай`;
- edit mode with category selector, searchable material result list, percent input, read-only kg, remove, `+`, `Запази`, and `Отказ`;
- explicit `Материал извън каталога` action before free text is accepted;
- inline row/total/server errors without clearing current state;
- disabled surrounding Admin global-save control while recipe edit mode is open;
- JSON `fetch()` save, followed by location reload only on success; and
- Cancel from an untouched clone of the last server state with no request.

Use accessible labels, keyboard-operable result buttons, `aria-expanded`, an error `role="alert"`, and deterministic focus: first editable field on Edit, new row category on add, first error on rejection.

- [ ] **Step 8: Add catalogue polling without draft replacement**

Poll `/material-catalogue.json` every 15 seconds and once when the page regains visibility. When version changes, replace only the in-memory search catalogue/version and show `Каталогът с материали е обновен.` Keep every draft row and typed percentage/material intact. The next save relies on Task 5's current-catalogue revalidation. Do not increment or spoof the card snapshot signature and do not trigger the existing card-change reload warning.

- [ ] **Step 9: Add render/safety tests**

Run the module in the existing V8 render harness with a fake DOM/fetch/timer surface. Assert no page/console exception, polling does not modify editor inputs, a simulated card-snapshot conflict still uses the existing reload-required path, and the module contains no `innerHTML`, `eval`, implicit npm install, or external network dependency.

- [ ] **Step 10: Run JavaScript and integration safety tests**

Run:

```bash
node --test tests/js/recipe_editor_core.test.mjs
source .venv/bin/activate && python -m pytest tests/test_terminal_sync.py tests/test_terminal_v8_render.py -q
```

Expected: all tests pass with fake timers cleaned up at test end.

- [ ] **Step 11: Review state preservation and injection safety**

Run: `git diff -- app/static/js/recipe_editor_core.mjs app/static/js/recipe_editor.mjs tests/js/recipe_editor_core.test.mjs tests/test_terminal_sync.py tests/test_terminal_v8_render.py && git diff --check`

Confirm catalogue refresh cannot overwrite draft rows, Cancel performs no fetch, errors retain state, duplicate labels disambiguate, and untrusted material strings are never parsed as markup.

---

### Task 10: Terminal And Admin Recipe Screens

**Files:**
- Modify: `app/templates/terminal.html`
- Modify: `app/templates/admin_card_detail.html`
- Modify: `app/static/css/app.css`
- Modify: `app/main.py`
- Modify: `tests/test_terminal_detail.py`
- Modify: `tests/test_admin_card_detail_redesign.py`
- Modify: `tests/test_admin_production_corrections.py`

**Interfaces:**
- Consumes: Task 8 contexts/routes and Task 9 `[data-recipe-editor]` contract.
- Produces: one effective-recipe UI on Terminal and the same executed-recipe editor beside a separate planned-recipe area on Admin.

- [ ] **Step 1: Write Terminal render assertions**

Assert the recipe header contains a top-right `Редактирай` when `can_edit_card`, read columns are exactly category/material/%/kg/batch, and neither `Вложени материали` nor any `actual_material__` input exists. Assert server JSON includes all effective rows, versions, target gross, and Terminal save URL. For non-editable lifecycle states, assert read mode remains but Edit is absent/disabled according to existing correction eligibility.

- [ ] **Step 2: Write Admin separation assertions**

Assert Admin renders a clearly labelled planned-recipe table whose inputs retain the existing imported-field names and a separate `Реално използвана рецепта` panel wired to the Admin JSON route. The executed editor must not contain `planned_material__*` names; planned inputs must not contain executed snapshot names. Batch fields remain visible next to effective slots but belong to the dedicated Admin batch form, not Admin Save All.

- [ ] **Step 3: Write lifecycle/free-text/accessibility render assertions**

Cover pending, running, paused, awaiting rewinding, completed, archived, imported, and cancelled cards according to the existing production-correction rules. Assert free-text rows render an `Извън каталога` badge in Admin/read mode, every input/button has a usable label, and JSON is emitted through Jinja's `tojson` escaping.

- [ ] **Step 4: Run template tests and observe old-column failures**

Run: `source .venv/bin/activate && python -m pytest tests/test_terminal_detail.py tests/test_admin_card_detail_redesign.py tests/test_admin_production_corrections.py -q`

Expected: tests fail because the old actual-material column/forms still render and shared editor hooks are absent.

- [ ] **Step 5: Replace Terminal recipe markup**

Keep the existing panel position and visual density. Render five read columns and batch inputs through the independent batch-only form. Add a header Edit button and a sibling editor mount; do not nest forms. Include one `application/json` initial-state block and one module script reference. Ensure recipe Save sends only JSON executed rows; batch continues through its established immediate-save behavior.

- [ ] **Step 6: Split Admin planned and executed meanings**

Retain planned category/material/percentage inputs in the outer `admin-card-save-form`, under an explicit planned heading. Remove all active actual-material inputs. Add a separate effective/executed panel using the shared editor mount. Give batch inputs `form="admin-recipe-batch-form"` so they belong to a dedicated form rendered outside the large outer form; this keeps batch editing available while recipe edit mode is open and excludes batches from global Save All. Recipe editor controls must be `type="button"` and generated editor inputs must have no form names. Disable only the top Admin `Запази Промените` button during recipe edit mode and re-enable it on Cancel/error/success navigation; never disable the batch inputs or their save behavior.

- [ ] **Step 7: Style read/edit modes for both viewports**

Use a five-column grid with min-width guards only inside the recipe panel, clear selected/search/free-text states, touch targets at least as large as existing terminal controls, visible keyboard focus, and a compact inline error region. At the narrower supported viewport, keep category/material context visible without page-level horizontal overflow; allow only the recipe result list to scroll vertically.

- [ ] **Step 8: Run render and route tests to green**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_detail.py tests/test_admin_card_detail_redesign.py tests/test_admin_production_corrections.py tests/test_admin_routes.py tests/test_terminal_sync.py tests/test_terminal_v8_render.py -q
node --test tests/js/recipe_editor_core.test.mjs
```

Expected: all backend/render/browser-core tests pass.

- [ ] **Step 9: Session 4 checkpoint**

Run: `git diff --check`

Review the rendered field names and routes manually in the diff: recipe Save must not submit batches or planned fields; dedicated batch save must not submit or erase legacy actual material; Admin Save All must leave both executed rows and batches untouched; both UI surfaces use the same module and backend validation. Record results; do not stage or commit.

---

### Task 11: Guarded Live Browser Workflow

**Files:**
- Create: `scripts/create_editable_recipe_fixture.py`
- Create: `scripts/verify_editable_recipe_ui.mjs`
- Create: `tests/test_editable_recipe_ui_scripts.py`
- Generate during verification only: `.test-runtime/editable-executed-recipes/**`
- Generate during verification only: `artifacts/ui-checks/editable-executed-recipes/**`

**Interfaces:**
- Consumes: completed Tasks 1–10, `/health` database identity, repo-local `@playwright/test`, and environment variables `BASE_URL`, `FIXTURE_JSON`, and `ARTIFACT_DIR`.
- Produces: deterministic temporary database/fixture metadata, screenshots for both workstations, and `verification-summary.json` containing assertions and captured browser errors.

- [ ] **Step 1: Write fixture/verifier safety tests**

Assert the fixture creator refuses any database path outside `.test-runtime/`, refuses symlink escapes, and never defaults to the runtime database. Assert the verifier requires all three environment variables, realpath-checks the fixture beneath `.test-runtime/` and artifacts strictly beneath `artifacts/ui-checks/`, verifies `/health` reports that exact database before mutations, resolves only repository-local `@playwright/test`, and contains no install command or external URL.

- [ ] **Step 2: Run safety tests and observe missing-script failures**

Run: `source .venv/bin/activate && python -m pytest tests/test_editable_recipe_ui_scripts.py -q`

Expected: tests fail because both guarded scripts are absent.

- [ ] **Step 3: Build the deterministic fixture creator**

Use argparse `--db-path` and `--fixture-json`. Initialize the new schema, import a catalogue containing at least two same-display-name masterbatches with distinct full names, open an active shift, and create/release these cards:

- pending unchanged card for first-start snapshot;
- pending card for editing/add/remove/free-text and stale-card tests;
- completed card with an executed mismatch for Admin correction; and
- card with a non-empty batch on one slot for removal protection.

Write only IDs, expected versions, database realpath, and test labels to fixture JSON; do not include production data or credentials.

- [ ] **Step 4: Implement the guarded Playwright verifier**

Run Chromium at `1366x768` and `1920x1080`. Capture `console` errors, page errors, failed same-origin requests, and assertion failures. At each viewport verify:

1. Terminal read mode has five columns, top-right Edit, no actual-material input, all seven possible rows visible, and no document-level horizontal overflow.
2. Edit/Cancel writes nothing and restores the server recipe.
3. Category selection filters material results; search works by display/full/producer/family/grade; duplicate display names are visibly distinct.
4. Catalogue choice, explicit free text, live percent/kg update, add/remove, seven-row cap, and non-empty-batch removal refusal behave visibly.
5. Invalid total shows an inline Bulgarian error and keeps every entered row; valid Save returns read mode with the effective recipe.
6. Batch edit persists independently and recipe save does not change it.
7. First Start creates an executed snapshot while displayed material/percentage remain unchanged.
8. A second page changes the same card and the stale editor receives reload-required handling without overwriting the winner.
9. While a draft is open, upload a replacement catalogue from another Admin page, wait for the version notice, and assert the draft remains byte-for-input-value unchanged.
10. Admin shows planned and effective/executed sections separately, identifies free text, and can correct the completed card using the same editor.

Write one full-page Terminal read screenshot, one Terminal edit/error screenshot, and one Admin split-recipe screenshot per viewport, plus a JSON summary with zero unexpected errors.

- [ ] **Step 5: Run script-safety tests to green**

Run: `source .venv/bin/activate && python -m pytest tests/test_editable_recipe_ui_scripts.py -q`

Expected: all path, dependency, health-preflight, and no-install assertions pass.

- [ ] **Step 6: Create isolated runtime and confirm local tooling**

Run:

```bash
mkdir -p .test-runtime/editable-executed-recipes artifacts/ui-checks/editable-executed-recipes
source .venv/bin/activate && python scripts/create_editable_recipe_fixture.py \
  --db-path .test-runtime/editable-executed-recipes/extrusion-terminal.sqlite3 \
  --fixture-json .test-runtime/editable-executed-recipes/fixture.json
./node_modules/.bin/playwright --version
```

Expected: fixture creation exits `0`, reports only the guarded temporary path, and repo-local Playwright prints its installed version without downloading anything.

- [ ] **Step 7: Start FastAPI against the fixture database**

Run in a dedicated terminal session:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH="$PWD/.test-runtime/editable-executed-recipes/extrusion-terminal.sqlite3" \
python -m uvicorn app.main:app --host 127.0.0.1 --port 18080
```

Expected: `/health` reports the exact temporary database realpath. If port `18080` is occupied, choose an unused loopback port and use the same value in `BASE_URL`.

- [ ] **Step 8: Execute the live workflow**

Run:

```bash
BASE_URL=http://127.0.0.1:18080 \
FIXTURE_JSON="$PWD/.test-runtime/editable-executed-recipes/fixture.json" \
ARTIFACT_DIR="$PWD/artifacts/ui-checks/editable-executed-recipes" \
node scripts/verify_editable_recipe_ui.mjs
```

Expected: exit `0`; summary says both viewports and every workflow assertion passed; no console/page/request errors are recorded.

- [ ] **Step 9: Inspect visual evidence, not just script status**

Open all six required screenshots. At minimum inspect at original detail:

- `terminal-read-1366x768.png` — complete recipe context and top-right Edit;
- `terminal-edit-error-1366x768.png` — usable controls and visible preserved validation state;
- `admin-recipes-1366x768.png` — unmistakable planned/executed separation;
- the corresponding three `1920x1080` files — balanced spacing without excessive spread.

If clipping, overlapping, unclear provenance, tiny targets, or confusing Save ownership appears, return to Task 10, correct it, rerun focused tests, regenerate all screenshots, and re-inspect them.

- [ ] **Step 10: Session 5 browser checkpoint**

Stop the temporary server cleanly. Run: `git status --short`

Confirm `.test-runtime/`, `artifacts/`, and local databases are untracked/ignored and that no runtime database timestamp or checksum changed.

---

### Task 12: Durable Documentation, Full Verification, And Final Agent Review

**Files:**
- Create: `docs/implementation-notes/editable-executed-recipes.md`
- Modify: `v2-files/TASK-20-EDITABLE-EXECUTED-RECIPES.md`
- Modify: `v2-files/PLAN.md`
- Review: every file changed by Tasks 1–11

**Interfaces:**
- Consumes: actual migration version/schema, final route names, final test commands/counts, and Task 11 evidence.
- Produces: durable implementation/operation record and an evidence-backed completion status for Task 20's initial forward-looking phase.

- [ ] **Step 1: Write the durable implementation note from actual code**

Document:

- actual migration number/name and exact new tables;
- planned/executed/effective meanings and whole-snapshot resolver;
- empty historical state and retained legacy actual-material text;
- catalogue CSV contract, atomic replacement, warnings, version behavior, and maintainer procedure;
- explicit save/first-start snapshot transaction rules;
- shared Admin/Terminal editor, free-text provenance, seven-row/batch rules;
- semantic re-import allow/block behavior and Bulgarian operator resolution;
- backup/restore coverage and production deployment prerequisites;
- exact focused/full/browser verification commands and artifact paths; and
- the still-unimplemented historical normalization, Shift Manager notification, and inventory communication follow-ups without redefining them.

- [ ] **Step 2: Update the Task 20 and master-plan status accurately after a revised plan is approved and implemented**

This retained step is not currently executable. After Item Master v1 is
confirmed, both Task 20 documents are reconciled and approved, and the revised
implementation passes all applicable verification, change Task 20's status
from unimplemented/reconciliation-gated to `implemented and verified in source
on <actual date>; not deployed unless separately recorded`. Preserve all
future-follow-up sections. Update `v2-files/PLAN.md` at workstream level with
actual test totals and evidence path; do not claim production deployment or
close future follow-ups.

- [ ] **Step 3: Run syntax/import and JavaScript verification**

Run:

```bash
source .venv/bin/activate && python -m compileall -q app tests scripts
source .venv/bin/activate && python -c "import app.main"
node --test tests/js/*.test.mjs
```

Expected: all commands exit `0`; the application import completes without creating or mutating the real runtime database. Set `EXTRUSION_DB_PATH` to a disposable `.test-runtime/editable-executed-recipes/import-check.sqlite3` if importing `app.main` invokes startup database work at execution time.

- [ ] **Step 4: Run all focused Task 20 Python tests together**

Run:

```bash
source .venv/bin/activate && python -m pytest \
  tests/test_material_catalog.py \
  tests/test_migrations.py \
  tests/test_executed_recipe.py \
  tests/test_executed_recipe_storage.py \
  tests/test_production_timing.py \
  tests/test_recipe_reimport_guard.py \
  tests/test_recipe_sync.py \
  tests/test_terminal_detail.py \
  tests/test_admin_card_detail_redesign.py \
  tests/test_admin_production_corrections.py \
  tests/test_admin_routes.py \
  tests/test_terminal_sync.py \
  tests/test_terminal_v8_render.py \
  tests/test_backup_recovery.py \
  tests/test_editable_recipe_ui_scripts.py -q
```

Expected: all selected tests pass. Record exact count/duration.

- [ ] **Step 5: Run the complete Python suite**

Run: `source .venv/bin/activate && python -m pytest`

Expected: exit `0` with no failures, errors, or unexpected skips. Record exact count/duration rather than copying an old baseline.

- [ ] **Step 6: Run database health checks on a disposable migrated predecessor copy**

Use the migration-test helper or fixture script to create one predecessor copy under `.test-runtime/editable-executed-recipes/`, initialize it to latest, and run:

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;
SELECT COUNT(*) FROM executed_recipe_components;
SELECT catalogue_version, row_count FROM material_catalog_state WHERE id = 1;
```

Expected: `ok`, zero foreign-key rows, zero synthesized executed rows for untouched history, and internally consistent catalogue metadata.

- [ ] **Step 7: Perform the final database/route review**

Read every changed transaction and route end-to-end. Trace these exact cases from request/import/start through commit/response: valid recipe save, invalid save, injected insert failure, stale card, catalogue replaced mid-edit, first start with/without pre-save, matching re-import, blocked re-import, batch-only save, and Admin planned save. Confirm each mutation set matches Task 20 and every failure leaves the previous authoritative data intact.

- [ ] **Step 8: Perform the final UI/spec review**

Compare Task 11 screenshots and rendered markup against every `Recipe Editing Workflow`, `Admin Workflow`, and `Browser Workflow` bullet in the Task 20 specification. Confirm the user sees one effective recipe, not a redundant actual-material field; planned and executed meanings remain distinct in Admin; button ownership is unambiguous; and no unrelated workflow change entered the diff.

- [ ] **Step 9: Run final repository hygiene checks**

Run:

```bash
git diff --check
git status --short
git diff --stat
git diff -- app app/templates app/static tests scripts docs/implementation-notes v2-files
```

Expected: no whitespace errors, no tracked database/artifact/node files, no unrelated refactor, and no staged changes unless the user separately authorized staging.

- [ ] **Step 10: Correct every issue and rerun affected gates**

For any finding in Steps 3–9, return to its owning task, add or strengthen a regression test, make the smallest correction, rerun that focused suite, rerun the complete Python/JavaScript suites when shared behavior changed, and regenerate/reinspect browser evidence when visible behavior changed.

- [ ] **Step 11: Present the UI/workflow handoff**

Report implemented behavior, migration classification, exact test totals, browser evidence paths, and final review findings. State explicitly that the runtime database was not touched and deployment was not performed. Invite the user to try only the UI/workflow and provide visible-workflow comments. Do not ask the user to review code or tests.

---

## Plan Self-Review Checklist

Run this checklist when the plan is written and again if Task 20 changes before execution:

- **Spec coverage:** Tasks 1–3 cover catalogue contract/administration/refresh foundation/migration/backup; Tasks 4–5 cover validation, full snapshots, resolver, catalogue provenance, versioning, batches, and preservation; Tasks 6–7 cover first start and re-import; Tasks 8–10 cover shared Admin/Terminal workflow and concurrent catalogue editing; Tasks 11–12 cover every required browser, migration-health, full-suite, and final-agent-review gate.
- **Historical safety:** Task 2 explicitly creates zero historical snapshots and Task 12 checks this again on a disposable predecessor database.
- **Future continuity:** Task 12 preserves the three required future follow-ups in Task 20/PLAN but does not implement them.
- **Placeholder scan:** Run `rg -n "T[B]D|T[O]DO|implement l[a]ter|fill in d[e]tails|appropriate e[r]ror handling|write tests for the a[b]ove|Similar to T[a]sk" docs/superpowers/plans/2026-08-12-editable-executed-recipes.md`; expected output is empty.
- **Type consistency:** Compare every name in `Stable interfaces established by this plan` with each task's Consumes/Produces block. The persistence layer always receives normalized `ExecutedRecipeRow`; routes receive mappings/JSON; the browser payload uses the same snake-case keys the route parser validates.
- **Scope check:** Confirm the diff contains no notification tray, historical conversion, inventory/export, role/permission, workbook-writeback, or deployment implementation.
- **Repository policy:** Confirm no step stages/commits without user authorization, all writes/tests use temporary data, and browser evidence is ignored.

## Start Gate

No implementation execution mode is active. The next Task 20 action is the
bounded design/plan reconciliation described in the supersession notice. Only
after the remaining Item Master v1 contract decisions are confirmed and both
Task 20 documents are revised and approved may a new or explicitly reapproved
implementation plan define its execution mode, estimates, schema, tests, and
review checkpoints. Do not start any task above from this retained plan.
