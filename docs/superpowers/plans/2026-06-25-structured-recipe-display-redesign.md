# Structured Recipe Display Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the terminal and admin recipe displays to show structured planned recipe rows from normalized `recipe_components`, while preserving source-text correction, print source text, release validation, and actual material/batch entry behavior.

**Architecture:** Load normalized recipe components with admin and terminal card details, then build display rows in `app/main.py` that prefer parsed category/material/percent data and calculate planned kilograms from target gross weight. Terminal renders only meaningful structured/fallback rows; admin renders all seven source fields so the shift manager can still correct authoritative source text. Existing `recipe_actual_entries` writes remain version-checked, but omitted component rows must be preserved instead of being blanked by the new reduced terminal form.

**Tech Stack:** Python 3, FastAPI, Jinja2 server-rendered templates, direct `sqlite3`, SQLite temporary test databases, pytest, local Playwright for manual UI verification.

---

## Repository Rules For Execution

- Work in `/home/sk/projects/extrusion-terminal` on branch `structured-recipe-redesign`.
- Follow `AGENTS.md`; `README.md` is authoritative if docs conflict.
- This is OI-003 Step 6 only.
- Do not implement code until this plan is being executed in a later session.
- Do not stage or commit unless the user explicitly asks.
- Use `.venv` for Python commands.
- Tests must use temporary SQLite database paths and must not mutate `data/extrusion_terminal.sqlite3`.
- UI changes require a live FastAPI app check with Playwright and at least one screenshot under `artifacts/ui-checks/`.

## Context Loaded Before This Plan

- `AGENTS.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `open-issues.md`
- `docs/implementation-notes/structured-recipe-contract.md`
- `docs/superpowers/plans/2026-06-24-structured-recipe-parser.md`
- `docs/superpowers/plans/2026-06-24-structured-recipe-storage.md`
- `docs/superpowers/plans/2026-06-25-structured-recipe-sync.md`
- `docs/superpowers/plans/2026-06-25-structured-recipe-release-gate.md`
- `app/recipe_parser.py`
- `app/db.py`
- `app/main.py`
- `app/templates/admin_card_detail.html`
- `app/templates/terminal.html`
- `app/static/css/app.css`
- focused recipe/admin/terminal/print tests listed in this plan

Current Step 5 baseline:

- `cards.raw_material_a` through `cards.chalk` remain authoritative source text for import, correction, and print.
- `recipe_components` stores normalized derived rows and is synced permissively on import, overwrite re-import, and admin source correction.
- `release_card()` blocks malformed structured recipe rows, totals other than exactly `100%`, and missing/zero/invalid target gross weight.
- Import, overwrite re-import, and admin source correction remain permissive.
- `recipe_actual_entries` stores actual material and batch/lot production data separately from source text.

## Scope

Implement only OI-003 Step 6:

- Terminal and admin recipe displays use normalized recipe data where available.
- Display columns:
  - `Категория`
  - `Планирани материали`
  - `%`
  - `КГ`
  - `Вложени материали`
  - `Партида`
- Planned kilograms are calculated as `recipe_percent * target_gross_weight / 100`.
- Terminal actual material and batch/lot inputs keep names `actual_material__{component_key}` and `batch_lot__{component_key}` and keep loaded-version conflict checks.
- Admin source text remains editable for all seven source fields using the existing `planned_material__{component_key}` POST contract.
- Admin source correction continues to update `cards.raw_material_*`, sync `recipe_components`, and preserve actual entries.
- Print output remains based on original source text and must not change.

## Explicit Non-Scope

Do not implement:

- Print output changes.
- Excel macro/export validation.
- Release-gate rule changes.
- Parser/category contract changes.
- Pricing, costing, inventory, ERP behavior, material catalog management, users, roles, or permissions.
- Any behavior outside terminal/admin structured recipe display and the minimal data-preservation changes needed by that display.

## File Map

- Modify: `app/db.py`
  - Attach `recipe_components` to `fetch_admin_card_detail()` and `fetch_terminal_card_detail()`.
  - Preserve omitted `recipe_actual_entries` keys during actual material/batch updates.
  - Preserve legacy `actual_raw_material_used` / `raw_material_batch_lot` when `raw_material_a` is omitted.
- Modify: `app/main.py`
  - Replace legacy recipe row builders with structured row builders.
  - Parse submitted recipe actual form rows from actual submitted field names only.
  - Keep `material_ledger_from_form()` source-text behavior for admin all-field correction.
- Modify: `app/templates/terminal.html`
  - Render the six structured recipe columns.
  - Keep autosave form and input names for actual material/batch entries.
- Modify: `app/templates/admin_card_detail.html`
  - Render the six structured columns.
  - Keep editable source text in the planned-material column for all seven source fields.
- Modify: `app/static/css/app.css`
  - Update admin material ledger grid, compact text styles, and responsive min-widths.
- Modify terminal inline CSS in `app/templates/terminal.html`
  - Update terminal recipe grid columns and responsive rules.
- Modify: `tests/test_recipe_sync.py`
  - Replace Step 4 display-boundary tests with Step 6 expectations.
- Modify: `tests/test_admin_card_review.py`
  - Update admin context recipe-row expectations.
- Modify: `tests/test_admin_card_detail_redesign.py`
  - Update admin render tests for structured columns plus source-text inputs.
  - Add preservation tests for omitted actual entries if best placed here.
- Modify: `tests/test_terminal_detail.py`
  - Add/adjust backend actual-entry preservation tests.
- Modify: `tests/test_terminal_v8_render.py`
  - Update terminal render tests for structured headers, values, planned kilograms, input naming, and autosave.
- Modify only if needed: `tests/test_print_output.py`
  - Add a boundary test if existing coverage does not already prove print still renders source text with `|` and percent unchanged.
- Modify: `IMPLEMENTATION_PLAN.md`
  - Mark OI-003 Step 6 complete after implementation and verification.

Files that should not change:

- `app/printing.py`
- `app/recipe_parser.py`
- `app/rules.py` unless a display bug directly exposes a mismatch and the user approves.
- `source-files/excel-macros/**`
- `interim-costing-process/**`

## Design Details

### Structured Row Shape

Each display row should be a dict with these keys:

```python
{
    "field": "raw_material_a",
    "source_label": "A",
    "material_category": "LDPE",
    "planned_material": "Rompetrol B20/03",
    "recipe_percent": "80%",
    "planned_kg": "800.00",
    "source_text": "LDPE Rompetrol B20/03 | 80%",
    "actual_material": "Actual LDPE",
    "batch": "Batch A",
    "has_actual": True,
    "is_structured": True,
}
```

For a source field with no normalized component, keep a fallback row:

```python
{
    "field": "raw_material_a",
    "source_label": "A",
    "material_category": "",
    "planned_material": "LDPE malformed source 80%",
    "recipe_percent": "",
    "planned_kg": "",
    "source_text": "LDPE malformed source 80%",
    "actual_material": "",
    "batch": "",
    "has_actual": False,
    "is_structured": False,
}
```

Admin rows should include all seven source fields so empty fields can be corrected or filled. Terminal rows should include only rows with a normalized component, non-empty source text, or existing actual/batch values.

### Planned Kilograms

Use the same target gross concept as the Step 5 release gate: a positive kg quantity from quantity line 1 or 2. In `app/main.py`, prefer importing and using `target_gross_weight_from_card()` from `app.rules` to avoid diverging from release behavior.

Calculate:

```python
planned_kg = target_gross * recipe_percent / Decimal("100")
```

Display planned kg with the existing `decimal_weight_display()`, so `1000 kg * 77%` renders as `770.00`.

Display recipe percent with a compact percent formatter:

```python
def decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def recipe_percent_display(value: Any) -> str:
    percent = decimal_from_display(value)
    return f"{decimal_text(percent)}%" if percent is not None else ""
```

### Admin Source Correction

Admin must keep correcting the authoritative source text because import/admin draft correction remains permissive and print still uses source text. Keep the existing `planned_material__{field}` input names and `material_ledger_from_form()` source-text contract.

In the admin six-column table, put the source text input inside the `Планирани материали` cell under the parsed planned-material display. This keeps the table aligned with the Step 6 columns without hiding correction:

```html
<div class="structured-planned">{{ row.planned_material or "-" }}</div>
<input name="planned_material__{{ row.field }}" value="{{ row.source_text }}">
```

### Omitted Actual Rows

Because terminal will no longer render every legacy row, `recipe_actual_entries_from_form()` must not synthesize blank rows for missing fields. It should return only component keys found in submitted `actual_material__*` or `batch_lot__*` field names.

Then `update_terminal_recipe_actual_entries()` should only upsert submitted component keys. Omitted component keys must keep their existing `recipe_actual_entries` values. If `raw_material_a` is omitted, preserve legacy card fields `actual_raw_material_used` and `raw_material_batch_lot`.

Admin still renders all seven material rows, so admin save-all and materials-ledger saves continue to submit all keys.

---

## Task 1: Add Failing Backend Display Row Tests

**Files:**

- Modify: `tests/test_admin_card_review.py`
- Modify: `tests/test_recipe_sync.py`
- Modify later: `app/db.py`, `app/main.py`

- [ ] **Step 1: Update admin context test to expect structured rows**

In `tests/test_admin_card_review.py`, update `test_admin_card_detail_context_groups_quantities_and_recipe_rows` after `context = admin_card_detail_context(card_id)`:

```python
    rows = {row["field"]: row for row in context["recipe_rows"]}

    assert [line["display"] for line in context["quantity_lines"]] == ["500 kg", "1200 m"]
    assert rows["raw_material_a"]["source_label"] == "A"
    assert rows["raw_material_a"]["material_category"] == "LDPE"
    assert rows["raw_material_a"]["planned_material"] == "A"
    assert rows["raw_material_a"]["recipe_percent"] == "60%"
    assert rows["raw_material_a"]["planned_kg"] == "300.00"
    assert rows["raw_material_a"]["source_text"] == "LDPE A | 60%"
    assert rows["raw_material_a"]["actual_material"] == "Actual LDPE"
    assert rows["raw_material_a"]["batch"] == "Batch 42"
    assert rows["raw_material_b"]["material_category"] == "LDPE"
    assert rows["raw_material_b"]["planned_material"] == "B"
    assert rows["raw_material_b"]["recipe_percent"] == "30%"
    assert rows["raw_material_b"]["planned_kg"] == "150.00"
    assert rows["linear_pe"]["material_category"] == "LLDPE"
    assert rows["linear_pe"]["planned_material"] == "Linear PE"
    assert rows["linear_pe"]["planned_kg"] == "50.00"
    assert rows["chalk"]["source_text"] == ""
    assert rows["chalk"]["planned_kg"] == ""
```

Remove the old assertions that expect labels `["A", "B", "C", ...]`, `row["planned"]`, and `row["brand"]`.

- [ ] **Step 2: Replace Step 4 display-boundary test with Step 6 expectations**

In `tests/test_recipe_sync.py`, replace `test_step_4_keeps_admin_and_terminal_recipe_display_on_original_source_text` with:

```python
def test_step_6_admin_and_terminal_display_use_normalized_recipe_rows(connection):
    card_id = import_card(
        "RS-SYNC-008",
        quantity_1="1000",
        unit_1="kg",
        raw_material_a="LDPE Display Source | 80%",
        linear_pe="LLDPE Display Source | 20%",
    )
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        {
            "raw_material_a": {
                "actual_material_used": "Actual Display A",
                "batch_lot": "Batch Display A",
            },
            "linear_pe": {
                "actual_material_used": "Actual Display L",
                "batch_lot": "Batch Display L",
            },
        },
    ).ok

    admin_context = admin_card_detail_context(card_id)
    terminal = terminal_context(card_id=card_id)
    admin_rows = {row["field"]: row for row in admin_context["recipe_rows"]}
    terminal_rows = {row["field"]: row for row in terminal["recipe_rows"]}

    assert admin_rows["raw_material_a"]["source_text"] == "LDPE Display Source | 80%"
    assert admin_rows["raw_material_a"]["material_category"] == "LDPE"
    assert admin_rows["raw_material_a"]["planned_material"] == "Display Source"
    assert admin_rows["raw_material_a"]["recipe_percent"] == "80%"
    assert admin_rows["raw_material_a"]["planned_kg"] == "800.00"
    assert admin_rows["raw_material_a"]["actual_material"] == "Actual Display A"
    assert admin_rows["raw_material_a"]["batch"] == "Batch Display A"

    assert terminal_rows["raw_material_a"]["source_text"] == "LDPE Display Source | 80%"
    assert terminal_rows["raw_material_a"]["material_category"] == "LDPE"
    assert terminal_rows["raw_material_a"]["planned_material"] == "Display Source"
    assert terminal_rows["raw_material_a"]["recipe_percent"] == "80%"
    assert terminal_rows["raw_material_a"]["planned_kg"] == "800.00"
    assert terminal_rows["raw_material_a"]["actual_material"] == "Actual Display A"
    assert terminal_rows["linear_pe"]["planned_material"] == "Display Source"
    assert "chalk" not in terminal_rows
```

- [ ] **Step 3: Add admin fallback test for malformed source text**

Append to `tests/test_recipe_sync.py`:

```python
def test_admin_recipe_display_keeps_source_text_when_row_has_no_normalized_component(connection):
    card_id = import_card(
        "RS-SYNC-010",
        raw_material_a="LDPE Missing Delimiter 80%",
        linear_pe="LLDPE Valid Row | 20%",
    )

    context = admin_card_detail_context(card_id)
    rows = {row["field"]: row for row in context["recipe_rows"]}

    assert rows["raw_material_a"]["source_text"] == "LDPE Missing Delimiter 80%"
    assert rows["raw_material_a"]["planned_material"] == "LDPE Missing Delimiter 80%"
    assert rows["raw_material_a"]["material_category"] == ""
    assert rows["raw_material_a"]["recipe_percent"] == ""
    assert rows["raw_material_a"]["planned_kg"] == ""
    assert rows["raw_material_a"]["is_structured"] is False
    assert rows["linear_pe"]["material_category"] == "LLDPE"
    assert rows["linear_pe"]["planned_material"] == "Valid Row"
```

- [ ] **Step 4: Run focused tests and verify failure**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_admin_card_review.py::test_admin_card_detail_context_groups_quantities_and_recipe_rows tests/test_recipe_sync.py::test_step_6_admin_and_terminal_display_use_normalized_recipe_rows tests/test_recipe_sync.py::test_admin_recipe_display_keeps_source_text_when_row_has_no_normalized_component -q
```

Expected: failures showing missing `recipe_components` on fetched card details and/or old row keys like `planned` instead of `planned_material`.

## Task 2: Load Components And Build Structured Rows

**Files:**

- Modify: `app/db.py`
- Modify: `app/main.py`
- Test: files from Task 1

- [ ] **Step 1: Attach normalized components in detail fetches**

In `app/db.py`, add this line in both `fetch_admin_card_detail()` and `fetch_terminal_card_detail()` after `card["recipe_actual_entries"] = ...`:

```python
        card["recipe_components"] = fetch_recipe_components(connection, card_id)
```

- [ ] **Step 2: Update imports in `app/main.py`**

Add `RECIPE_SOURCE_FIELDS` and `target_gross_weight_from_card` imports:

```python
from .recipe_parser import RECIPE_SOURCE_FIELDS
from .rules import RuleResult, target_gross_weight_from_card
```

If `RuleResult` is already imported separately from `.rules`, merge the import without changing behavior.

- [ ] **Step 3: Add formatting and row helper functions in `app/main.py` near `build_recipe_rows()`**

Replace `build_recipe_rows()` and `build_terminal_recipe_rows()` with helpers shaped like this:

```python
def decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def recipe_percent_display(value: Any) -> str:
    percent = decimal_from_display(value)
    return f"{decimal_text(percent)}%" if percent is not None else ""


def recipe_components_by_key(card: dict[str, Any]) -> dict[str, dict[str, Any]]:
    components = card.get("recipe_components") or []
    if not isinstance(components, list):
        return {}
    return {str(component["component_key"]): component for component in components}


def planned_kg_display(card: dict[str, Any], recipe_percent: Any) -> str:
    target = target_gross_weight_from_card(card)
    percent = decimal_from_display(recipe_percent)
    if target is None or percent is None:
        return ""
    return decimal_weight_display(target * percent / Decimal("100"))


def build_recipe_rows(
    card: dict[str, Any],
    *,
    include_all_source_fields: bool = True,
) -> list[dict[str, Any]]:
    actual_entries = card.get("recipe_actual_entries") or {}
    if not isinstance(actual_entries, dict):
        actual_entries = {}
    components = recipe_components_by_key(card)

    fields: list[str] = []
    for _, field in RECIPE_FIELD_ROWS:
        source_text = str(card.get(field) or "")
        has_component = field in components
        entry = actual_entries.get(field, {})
        has_actual_entry = bool(
            isinstance(entry, dict)
            and (entry.get("actual_material_used") or entry.get("batch_lot"))
        )
        if include_all_source_fields or has_component or source_text.strip() or has_actual_entry:
            fields.append(field)

    labels = dict(RECIPE_FIELD_ROWS)
    rows: list[dict[str, Any]] = []
    for field in fields:
        source_text = str(card.get(field) or "")
        component = components.get(field)
        entry = actual_entries.get(field, {}) if isinstance(actual_entries, dict) else {}
        actual_material = str(entry.get("actual_material_used") or "")
        batch = str(entry.get("batch_lot") or "")
        if field == "raw_material_a" and field not in actual_entries:
            actual_material = str(card.get("actual_raw_material_used") or "")
            batch = str(card.get("raw_material_batch_lot") or "")

        if component:
            planned_material = str(component.get("planned_material") or "")
            material_category = str(component.get("material_category") or "")
            recipe_percent = recipe_percent_display(component.get("recipe_percent"))
            planned_kg = planned_kg_display(card, component.get("recipe_percent"))
            is_structured = True
        else:
            planned_material = source_text
            material_category = ""
            recipe_percent = ""
            planned_kg = ""
            is_structured = False

        rows.append(
            {
                "field": field,
                "source_label": labels.get(field, field),
                "label": labels.get(field, field),
                "material_category": material_category,
                "planned_material": planned_material,
                "recipe_percent": recipe_percent,
                "planned_kg": planned_kg,
                "source_text": source_text,
                "actual_material": actual_material,
                "batch": batch,
                "has_actual": bool(actual_material or batch),
                "is_structured": is_structured,
            }
        )
    return rows


def build_terminal_recipe_rows(card: dict[str, Any]) -> list[dict[str, Any]]:
    return build_recipe_rows(card, include_all_source_fields=False)
```

Keep `TERMINAL_RECIPE_LABELS` in place temporarily if other code still imports it, but terminal display should no longer use it.

- [ ] **Step 4: Run focused backend display tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_admin_card_review.py::test_admin_card_detail_context_groups_quantities_and_recipe_rows tests/test_recipe_sync.py::test_step_6_admin_and_terminal_display_use_normalized_recipe_rows tests/test_recipe_sync.py::test_admin_recipe_display_keeps_source_text_when_row_has_no_normalized_component -q
```

Expected: these tests pass. If they fail due to exact Decimal formatting, fix only the formatting helper.

## Task 3: Preserve Omitted Actual Entries

**Files:**

- Modify: `tests/test_terminal_detail.py`
- Modify: `app/main.py`
- Modify: `app/db.py`

- [ ] **Step 1: Add failing partial-update preservation test**

Append to `tests/test_terminal_detail.py`:

```python
def test_terminal_recipe_actual_update_preserves_omitted_component_entries(connection):
    card_id = import_ready_card(
        "25344",
        raw_material_a="LDPE A | 80%",
        linear_pe="LLDPE Linear PE | 20%",
    )
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        {
            "raw_material_a": {
                "actual_material_used": "Actual A",
                "batch_lot": "Batch A",
            },
            "linear_pe": {
                "actual_material_used": "Actual Linear",
                "batch_lot": "Batch Linear",
            },
        },
    ).ok

    result = db.update_terminal_recipe_actual_entries(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        {
            "raw_material_a": {
                "actual_material_used": "Actual A Changed",
                "batch_lot": "Batch A Changed",
            },
        },
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert card["recipe_actual_entries"]["raw_material_a"]["actual_material_used"] == (
        "Actual A Changed"
    )
    assert card["recipe_actual_entries"]["linear_pe"]["actual_material_used"] == (
        "Actual Linear"
    )
    assert card["recipe_actual_entries"]["linear_pe"]["batch_lot"] == "Batch Linear"
```

- [ ] **Step 2: Run the new test and verify failure**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_detail.py::test_terminal_recipe_actual_update_preserves_omitted_component_entries -q
```

Expected: failure showing `linear_pe` was blanked.

- [ ] **Step 3: Change `recipe_actual_entries_from_form()` to parse submitted keys only**

In `app/main.py`, replace the function with:

```python
def recipe_actual_entries_from_form(form: Any) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for key, value in form.multi_items():
        if key.startswith("actual_material__"):
            field = key.removeprefix("actual_material__")
            entries.setdefault(field, {})["actual_material_used"] = str(value or "")
        elif key.startswith("batch_lot__"):
            field = key.removeprefix("batch_lot__")
            entries.setdefault(field, {})["batch_lot"] = str(value or "")

    for entry in entries.values():
        entry.setdefault("actual_material_used", "")
        entry.setdefault("batch_lot", "")
    return entries
```

- [ ] **Step 4: Change terminal actual-entry DB update to upsert submitted rows only**

In `app/db.py::update_terminal_recipe_actual_entries()`, replace:

```python
        for component_key, component_label in RECIPE_COMPONENT_FIELDS:
            entry = entries.get(component_key, {})
```

with:

```python
        for component_key in entries:
            component_label = component_labels[component_key]
            entry = entries.get(component_key, {})
```

Then replace the legacy raw-material card-field assignment block with:

```python
        raw_material_entry = entries.get("raw_material_a")
        if raw_material_entry is None:
            raw_material_used = str(card["actual_raw_material_used"] or "")
            raw_material_batch_lot = str(card["raw_material_batch_lot"] or "")
        else:
            raw_material_used = str(raw_material_entry.get("actual_material_used") or "").strip()
            raw_material_batch_lot = str(raw_material_entry.get("batch_lot") or "").strip()
```

Update the `SELECT` in this function to include the legacy fields:

```sql
SELECT id, version, raw_material_brand_grade,
       actual_raw_material_used, raw_material_batch_lot, {import_columns}
```

- [ ] **Step 5: Run focused preservation tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_detail.py::test_terminal_recipe_actual_entries_persist_all_rows_and_survive_finish tests/test_terminal_detail.py::test_terminal_recipe_actual_entries_block_stale_version tests/test_terminal_detail.py::test_terminal_recipe_actual_update_preserves_omitted_component_entries -q
```

Expected: all selected tests pass.

## Task 4: Update Terminal Template And CSS

**Files:**

- Modify: `tests/test_terminal_v8_render.py`
- Modify: `app/templates/terminal.html`

- [ ] **Step 1: Update terminal render test for structured headers and values**

In `tests/test_terminal_v8_render.py::test_terminal_v8_recipe_table_is_part_of_details_without_extra_recipe_heading`, replace header assertions with:

```python
    assert "Категория" in html
    assert "Планирани материали" in html
    assert ">%<" in html
    assert ">КГ<" in html
    assert "Вложени материали" in html
    assert "Партида" in html
```

Add assertions:

```python
    assert "LDPE" in html
    assert "A" in html
    assert "50%" in html
    assert "250.00" in html
```

Remove assertions for old headers `Вид суровина` and `Заложена суровина`.

- [ ] **Step 2: Update queue/detail render test for parsed planned material**

In `test_terminal_v8_renders_recipe_queue_and_completed_lookup`, keep assertions for parsed material identity text such as `A`, `B`, `HDPE C`, `Линеен PE`, `Бял мастербач`, and `Креда 5%`, but remove old source-string expectations that rely on full `LDPE A | 50%` style if present.

Add:

```python
    assert "50%" in html
    assert "30%" in html
    assert "250.00" in html
    assert "150.00" in html
```

- [ ] **Step 3: Run terminal render tests and verify failure**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_v8_render.py::test_terminal_v8_recipe_table_is_part_of_details_without_extra_recipe_heading tests/test_terminal_v8_render.py::test_terminal_v8_renders_recipe_queue_and_completed_lookup -q
```

Expected: failures because the template still renders four legacy columns.

- [ ] **Step 4: Update terminal recipe markup**

In `app/templates/terminal.html`, replace the recipe header and row body with:

```html
                    <div class="recipe-head">
                      <div>Категория</div>
                      <div>Планирани материали</div>
                      <div>%</div>
                      <div>КГ</div>
                      <div>Вложени материали</div>
                      <div>Партида</div>
                    </div>
                    {% for row in recipe_rows %}
                      <div class="recipe-row">
                        <div class="component">{{ row.material_category or row.source_label }}</div>
                        <div><div class="material-planned">{{ row.planned_material or row.source_text or "" }}</div></div>
                        <div class="recipe-number">{{ row.recipe_percent or "" }}</div>
                        <div class="recipe-number">{{ row.planned_kg or "" }}</div>
                        <div><input name="actual_material__{{ row.field }}" value="{{ row.actual_material or '' }}" aria-label="{{ row.source_label }} използван материал" {% if not can_edit_card %}disabled{% endif %}></div>
                        <div><input name="batch_lot__{{ row.field }}" value="{{ row.batch or '' }}" aria-label="{{ row.source_label }} партида" {% if not can_edit_card %}disabled{% endif %}></div>
                      </div>
                    {% endfor %}
```

- [ ] **Step 5: Update terminal recipe CSS**

In the main terminal inline CSS block in `app/templates/terminal.html`, change the grid columns for `.recipe-head, .recipe-row` to:

```css
grid-template-columns: 112px minmax(180px, 1fr) 58px 86px minmax(140px, .72fr) minmax(110px, .52fr);
```

Add:

```css
.recipe-number {
  justify-content: flex-end;
  color: #26323f;
  font-size: 17px;
  font-weight: 800;
  text-align: right;
}
```

Update every responsive `.recipe-head, .recipe-row { grid-template-columns: ... }` rule in `app/templates/terminal.html` so six columns remain visible. Use these narrower values for the existing width/height media sections:

```css
grid-template-columns: 96px minmax(150px, 1fr) 50px 76px minmax(118px, .62fr) minmax(92px, .48fr);
```

Do not hide actual/batch columns in terminal media rules; operators must still be able to edit them.

- [ ] **Step 6: Run terminal render tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_v8_render.py::test_terminal_v8_recipe_table_is_part_of_details_without_extra_recipe_heading tests/test_terminal_v8_render.py::test_terminal_v8_renders_recipe_queue_and_completed_lookup tests/test_terminal_v8_render.py::test_terminal_v8_recipe_inputs_are_named_for_all_rows tests/test_terminal_v8_render.py::test_terminal_v8_recipe_form_marks_exit_autosave_contract -q
```

Expected: selected tests pass.

## Task 5: Update Admin Template And CSS

**Files:**

- Modify: `tests/test_admin_card_detail_redesign.py`
- Modify: `app/templates/admin_card_detail.html`
- Modify: `app/static/css/app.css`

- [ ] **Step 1: Update admin render tests for structured columns and source inputs**

In `tests/test_admin_card_detail_redesign.py::test_admin_detail_combines_recipe_and_machine_materials`, add:

```python
    assert "Категория" in html
    assert "Планирани материали" in html
    assert ">%<" in html
    assert ">КГ<" in html
    assert "Вложени материали" in html
    assert 'name="planned_material__raw_material_a"' in html
    assert 'value="LDPE Planned A | 50%"' in html
    assert "Planned A" in html
    assert "50%" in html
    assert "1625.25" in html
```

Keep existing assertions that `actual_material__raw_material_a` and `batch_lot__raw_material_a` appear exactly once and `raw_material_brand_grade` is absent.

In `test_admin_materials_ledger_omits_brand_class_field`, add the same header assertions and keep existing input-name assertions.

- [ ] **Step 2: Run admin render tests and verify failure**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_admin_card_detail_redesign.py::test_admin_detail_combines_recipe_and_machine_materials tests/test_admin_card_detail_redesign.py::test_admin_materials_ledger_omits_brand_class_field -q
```

Expected: failures because the admin template still renders four legacy columns.

- [ ] **Step 3: Update admin material ledger markup**

In `app/templates/admin_card_detail.html`, replace the material ledger header/body with:

```html
        <div class="admin-ledger-head">
          <div>Категория</div>
          <div>Планирани материали</div>
          <div>%</div>
          <div>КГ</div>
          <div>Вложени материали</div>
          <div>Партида</div>
        </div>
        {% for row in recipe_rows %}
          <div class="admin-ledger-row material-ledger-row">
            <div class="component">{{ row.material_category or row.source_label }}</div>
            <div>
              <div class="structured-planned">{{ row.planned_material or "-" }}</div>
              <input name="planned_material__{{ row.field }}" value="{{ row.source_text }}" aria-label="{{ row.source_label }} източник по карта">
            </div>
            <div class="readonly-cell recipe-number">{{ row.recipe_percent or "" }}</div>
            <div class="readonly-cell recipe-number">{{ row.planned_kg or "" }}</div>
            <div>
              <input name="actual_material__{{ row.field }}" value="{{ row.actual_material or '' }}">
            </div>
            <div>
              <input name="batch_lot__{{ row.field }}" value="{{ row.batch or '' }}">
            </div>
          </div>
        {% endfor %}
```

- [ ] **Step 4: Update admin CSS**

In `app/static/css/app.css`, replace the material ledger grid rule:

```css
.material-ledger .admin-ledger-head,
.material-ledger .admin-ledger-row {
  grid-template-columns: 90px minmax(180px, 1fr) minmax(180px, 1fr) minmax(140px, 0.8fr);
}
```

with:

```css
.material-ledger .admin-ledger-head,
.material-ledger .admin-ledger-row {
  grid-template-columns: 110px minmax(220px, 1.2fr) 70px 90px minmax(180px, 1fr) minmax(140px, 0.8fr);
}
```

Add near `.readonly-cell`:

```css
.structured-planned {
  margin-bottom: 5px;
  color: var(--text);
  font-size: 13px;
  font-weight: 850;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.recipe-number {
  justify-content: flex-end;
  text-align: right;
}
```

Update the responsive min-width:

```css
.material-ledger .admin-ledger-head,
.material-ledger .admin-ledger-row {
  min-width: 900px;
}
```

- [ ] **Step 5: Run admin render tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_admin_card_detail_redesign.py::test_admin_detail_combines_recipe_and_machine_materials tests/test_admin_card_detail_redesign.py::test_admin_materials_ledger_omits_brand_class_field tests/test_admin_card_review.py::test_admin_card_detail_context_groups_quantities_and_recipe_rows -q
```

Expected: selected tests pass.

## Task 6: Preserve Print Boundary And Release Gate Behavior

**Files:**

- Modify: `tests/test_recipe_sync.py`
- Modify only if needed: `tests/test_print_output.py`

- [ ] **Step 1: Keep or strengthen print source-text boundary test**

Ensure `tests/test_recipe_sync.py::test_step_4_keeps_print_recipe_rows_on_original_source_text` still exists and still asserts:

```python
    assert by_key["raw_material_a"]["planned_material"] == "LDPE Print Source | 80%"
    assert by_key["linear_pe"]["planned_material"] == "LLDPE Print Source | 20%"
```

If that test was removed during editing, restore it.

- [ ] **Step 2: Add release-gate no-regression test only if coverage is missing**

If `tests/test_recipe_release_validation.py` already has passing coverage for bad totals and valid release, do not add another test. If it does not, add a focused test there that imports `80% + 19%`, verifies release blocks, then fixes admin source text to `80% + 20%` and verifies release succeeds.

- [ ] **Step 3: Run boundary tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py::test_step_4_keeps_print_recipe_rows_on_original_source_text tests/test_recipe_release_validation.py -q
```

Expected: print boundary and release-gate tests pass.

## Task 7: Focused Regression Suite

**Files:** no code changes unless tests expose a Step 6 regression.

- [ ] **Step 1: Run focused recipe/display/admin/terminal tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_parser.py tests/test_recipe_storage.py tests/test_recipe_sync.py tests/test_recipe_release_validation.py tests/test_admin_card_review.py tests/test_admin_card_detail_redesign.py tests/test_terminal_detail.py tests/test_terminal_v8_render.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run print tests to verify non-scope boundary**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_print_output.py -q
```

Expected: print tests pass without changing `app/printing.py` or `app/static/css/print.css`.

- [ ] **Step 3: Run full Python test suite**

Run:

```bash
source .venv/bin/activate && python -m pytest
```

Expected: all tests pass.

- [ ] **Step 4: Run syntax/import and diff checks**

Run:

```bash
source .venv/bin/activate && python -m compileall app
git diff --check
```

Expected: `compileall` succeeds and `git diff --check` reports no whitespace errors.

## Task 8: Manual UI Verification With Playwright

**Files:**

- No tracked source files unless the check exposes a bug.
- Artifacts under `artifacts/ui-checks/structured-recipe-display/`.
- Temporary database under `.test-runtime/structured-recipe-display/`.

- [ ] **Step 1: Create artifact/runtime directories**

Run:

```bash
mkdir -p artifacts/ui-checks/structured-recipe-display .test-runtime/structured-recipe-display
```

- [ ] **Step 2: Start the app against a temporary database**

Run in one terminal:

```bash
source .venv/bin/activate && EXTRUSION_DB_PATH=.test-runtime/structured-recipe-display/extrusion_terminal.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If port `8000` is occupied, use `8001` and update the Playwright script URL.

- [ ] **Step 3: Seed and verify UI with Playwright**

Run from a second terminal:

```bash
node - <<'NODE'
const { chromium } = require('@playwright/test');
const fs = require('fs');

(async () => {
  const baseURL = 'http://127.0.0.1:8000';
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });

  await page.goto(`${baseURL}/admin/import`);
  const csv = [
    'order_number,order_date,delivery_date,customer,city,product_type,quantity_1,unit_1,quantity_2,unit_2,product_form,material,size_thickness,notes,extrusion_flag,extrusion_folding,extrusion_next_operation,extrusion_treatment,raw_material_a,raw_material_b,raw_material_c,linear_pe,antistatic,masterbatch,chalk,packaging_method',
    'SRD-001,2026-06-25,2026-06-30,Structured UI Customer,Sofia,PE film,1000,kg,,rolls,flat,LDPE / LLDPE,600/0.050,Structured recipe UI check,da,single,rewind,corona,LDPE Rompetrol B20/03 | 77%,,,LLDPE SABIC 119ZJ | 18%,Antistatic Novachem AT 04673 LD | 2%,Masterbatch Polibach White 8000 ET | 3%,,rolls'
  ].join('\n');
  fs.writeFileSync('/tmp/structured-recipe-display.csv', csv);
  await page.locator('input[type="file"]').setInputFiles('/tmp/structured-recipe-display.csv');
  await page.getByRole('button', { name: /Импортирай|Import/i }).click();

  await page.goto(`${baseURL}/admin/planning`);
  await page.locator('select[name="machine_id"]').first().selectOption('1');
  await page.locator('input[name="machine_sequence"]').first().fill('1');
  await page.getByRole('button', { name: /Пусни|Изпрати|Release/i }).first().click();

  await page.goto(`${baseURL}/admin/cards`);
  await page.getByText('SRD-001').click();
  await page.screenshot({ path: 'artifacts/ui-checks/structured-recipe-display/admin-structured-recipe.png', fullPage: true });
  await page.getByText('Категория').waitFor();
  await page.getByText('Планирани материали').waitFor();
  await page.getByText('Rompetrol B20/03').waitFor();
  await page.getByText('770.00').waitFor();
  await page.locator('input[name="planned_material__raw_material_a"]').waitFor();

  await page.goto(`${baseURL}/terminal`);
  await page.getByText('SRD-001').waitFor();
  await page.getByText('Категория').waitFor();
  await page.getByText('Rompetrol B20/03').waitFor();
  await page.getByText('770.00').waitFor();
  await page.locator('input[name="actual_material__raw_material_a"]').fill('Actual LDPE UI');
  await page.locator('input[name="batch_lot__raw_material_a"]').fill('LOT-UI-A');
  await page.locator('input[name="batch_lot__raw_material_a"]').press('Enter');
  await page.waitForTimeout(500);
  await page.reload();
  await page.getByDisplayValue('Actual LDPE UI').waitFor();
  await page.getByDisplayValue('LOT-UI-A').waitFor();
  await page.screenshot({ path: 'artifacts/ui-checks/structured-recipe-display/terminal-structured-recipe.png', fullPage: true });

  await browser.close();
})();
NODE
```

Expected:

- Admin screenshot shows six structured recipe columns.
- Admin source text input remains visible/editable for `raw_material_a`.
- Terminal screenshot shows the six structured columns and calculated planned kg.
- Actual material and batch/lot persist after reload.

- [ ] **Step 4: Stop the dev server**

Stop the `uvicorn` process with `Ctrl-C`. Do not leave the server running.

## Task 9: Update Milestone Tracker

**Files:**

- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update structured recipe follow-up note**

In `IMPLEMENTATION_PLAN.md`, change the Step 6 line under “Structured recipe redesign follow-up” to:

```markdown
- OI-003 Step 6 complete: terminal and admin recipe displays now use normalized structured recipe rows with category, planned material, percent, planned kilograms, actual material, and batch/lot columns; admin source-text correction remains available for all seven source fields; terminal/admin actual material and batch/lot saves preserve version checks and existing actual-entry data; print output remains unchanged.
```

If no Step 6 line exists, add it after Step 5.

- [ ] **Step 2: Run final checks after docs update**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_sync.py tests/test_terminal_v8_render.py tests/test_admin_card_detail_redesign.py -q
git diff --check
```

Expected: tests pass and `git diff --check` passes.

## Final Verification Checklist

Before reporting Step 6 implementation complete in the later execution session, run:

```bash
source .venv/bin/activate && python -m pytest tests/test_recipe_parser.py tests/test_recipe_storage.py tests/test_recipe_sync.py tests/test_recipe_release_validation.py tests/test_admin_card_review.py tests/test_admin_card_detail_redesign.py tests/test_terminal_detail.py tests/test_terminal_v8_render.py -q
source .venv/bin/activate && python -m pytest tests/test_print_output.py -q
source .venv/bin/activate && python -m pytest
source .venv/bin/activate && python -m compileall app
git diff --check
```

Also complete the Playwright manual check from Task 8 and save screenshots:

- `artifacts/ui-checks/structured-recipe-display/admin-structured-recipe.png`
- `artifacts/ui-checks/structured-recipe-display/terminal-structured-recipe.png`

## Non-Scope Guardrails For Review

- `app/printing.py` should not change.
- `app/static/css/print.css` should not change.
- `source-files/excel-macros/**` should not change.
- `app/rules.py` release-gate behavior should not change.
- `app/recipe_parser.py` parser/category behavior should not change.
- Import and admin source correction should remain permissive.
- Admin source text inputs must still update `cards.raw_material_*`.
- Terminal actual material/batch saves must not clear omitted component entries.
- No staging or commit steps are part of this plan.

## Self-Review

- Spec coverage: Step 6 display columns, planned kg calculation, original source preservation, actual-entry preservation, release-gate preservation, import/admin permissiveness, print non-scope, tests, and manual UI verification are covered.
- Placeholder scan: no unfinished placeholder markers remain.
- Type consistency: row keys are defined once in “Structured Row Shape” and reused consistently in tests/templates.
