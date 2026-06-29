# OI-003 Step 6.5 Recipe N/A Omissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the app structured recipe contract with the Excel recipe-builder behavior that uses `N/A` as a catalog control value and omits those producer/grade values from the final recipe source cell.

**Architecture:** Keep `cards.raw_material_a` through `cards.chalk` as the source of truth for import, correction, and print. Loosen only the parser contract so an approved category may stand alone before the final `|`, store that as an empty normalized `planned_material`, and render a category fallback in structured admin/terminal displays so intentional omissions do not look like missing app data.

**Tech Stack:** Python 3, FastAPI, direct `sqlite3`, Jinja2 templates, pytest, local Playwright against the FastAPI app.

---

## Repository Rules For Execution

- Work in `/home/sk/projects/extrusion-terminal` on branch `structured-recipe-redesign`.
- Follow `AGENTS.md`; `README.md` is authoritative when repo docs conflict.
- This is OI-003 Step 6.5 only.
- Do not add app-side material catalog management.
- Do not add pricing, costing, inventory, ERP behavior, users, roles, or permissions.
- Do not change print layout.
- Do not write terminal data back to Excel.
- Do not implement Step 8 Excel macro validation in this slice.
- Do not stage or commit unless the user explicitly asks. Ignore generic Superpowers examples that recommend commits after each task.
- Use the repo-local virtualenv for Python verification.
- Tests must use temporary SQLite databases and must not mutate `data/extrusion_terminal.sqlite3`.
- UI-display changes require a focused live FastAPI check with Playwright and screenshots under `artifacts/ui-checks/`.

## Context Loaded Before This Plan

- `AGENTS.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `open-issues.md`
- `docs/implementation-notes/structured-recipe-contract.md`
- `interim-costing-process/source-files/recipe-builder-demo/README.md`
- `interim-costing-process/source-files/recipe-builder-demo/modRecipeBuilderCascadingInstaller.bas`
- `docs/superpowers/plans/2026-06-24-structured-recipe-parser.md`
- `docs/superpowers/plans/2026-06-24-structured-recipe-storage.md`
- `docs/superpowers/plans/2026-06-25-structured-recipe-sync.md`
- `docs/superpowers/plans/2026-06-25-structured-recipe-release-gate.md`
- `docs/superpowers/plans/2026-06-25-structured-recipe-display-redesign.md`
- `app/recipe_parser.py`
- `app/db.py`
- `app/main.py`
- `app/rules.py`
- `app/importer.py`
- `tests/test_recipe_parser.py`
- `tests/test_recipe_storage.py`
- `tests/test_recipe_release_validation.py`
- `tests/test_recipe_sync.py`
- `tests/test_admin_card_review.py`
- `tests/test_admin_card_detail_redesign.py`
- `tests/test_terminal_v8_render.py`
- `tests/test_print_output.py`

Current branch status before plan writing showed untracked existing plan/demo files:

```text
?? docs/superpowers/plans/2026-06-24-structured-recipe-storage.md
?? docs/superpowers/plans/2026-06-25-structured-recipe-display-redesign.md
?? docs/superpowers/plans/2026-06-25-structured-recipe-release-gate.md
?? docs/superpowers/plans/2026-06-25-structured-recipe-sync.md
?? interim-costing-process/recipe-catalog-review/
?? interim-costing-process/source-files/recipe-builder-demo/
```

Do not clean up or revert those files during this slice.

## Research Answers And Contract Decision

The Excel builder constructs final source-cell text in `BuildRecipeText()`:

```vb
BuildRecipeText = BuildMaterialText() & " | " & NormalizePercent(txtPercent.Value)
```

`BuildMaterialText()` starts with the selected category and independently omits producer and grade when their catalog values equal `N/A`:

```vb
materialText = Trim$(cboCategory.Value)
If Not IsOmittedCatalogValue(cboProducer.Value) Then materialText = materialText & " " & Trim$(cboProducer.Value)
If Not IsOmittedCatalogValue(cboGrade.Value) Then materialText = materialText & " " & Trim$(cboGrade.Value)
BuildMaterialText = NormalizeSpaces(materialText)
```

Therefore the final source cell can be:

- `Category Producer GradeCode | 80%`
- `Category Producer | 80%` when `GradeCode = N/A`
- `Category GradeCode | 80%` when `Producer = N/A`
- `Category | 80%` when both `Producer = N/A` and `GradeCode = N/A`

The builder requires category, producer, and grade controls to be non-empty, but `N/A` counts as a non-empty catalog control value. `N/A` is not printed into the final recipe cell.

The app should allow category-only rows for every approved app category, not only for `reLDPE`. Reasoning:

- The Excel builder omission rule is generic for `Producer` and `GradeCode`.
- The app imports only the final `AM:AS` source-cell text and does not import or know `RecipeCatalog`.
- Adding category-specific omission permissions would require app-side catalog management, explicitly out of scope.
- The app can realistically enforce only the final source-cell contract: approved category, final `|`, valid positive percent, total percent exactly `100%`, and target gross before release.
- Category-only acceptance is still bounded by the approved category list and release percentage/target-gross checks.

Normalize category-only rows as:

```python
ParsedRecipeComponent(
    component_key="raw_material_a",
    source_text="reLDPE | 80%",
    material_category="reLDPE",
    planned_material="",
    recipe_percent=Decimal("80"),
)
```

Display category-only rows with the category as the planned-material display fallback. A blank planned-material cell looks like missing app data, `-` hides the meaningful source identity, and printing `N/A` would reintroduce a control value that the Excel workflow deliberately omits. The structured display already has a category column, so this fallback is mildly redundant but explicit and stable:

```python
row["material_category"] == "reLDPE"
row["planned_material"] == "reLDPE"
row["source_text"] == "reLDPE | 80%"
```

Storage keeps `planned_material=""`; display applies the fallback.

Step 8 Excel export macro validation should still exist, but its planned validation should target the final source-cell text and the shared app parser contract. It should not require `RecipeCatalog` lookup or require literal `N/A` tokens, because the builder already controls entry and deliberately omits `N/A` from output.

## File Map

- Modify: `docs/implementation-notes/structured-recipe-contract.md`
  - Document `N/A` as an Excel catalog control value that is omitted from final source cells.
  - Document category-only final source cells as valid when the category is approved.
  - Replace the old “missing material identity after category blocks release” rule with “missing whole identity/category blocks release; material detail after an approved category is optional.”
  - Document empty normalized `planned_material` plus category display fallback.

- Modify: `open-issues.md`
  - Add OI-003 Step 6.5 between Steps 6 and 7.
  - Note that Step 6.5 aligns parser/release/display tests with Excel builder `N/A` omissions before sample CSV verification.

- Modify: `IMPLEMENTATION_PLAN.md`
  - Add Step 6.5 in-progress/complete note under the structured recipe redesign follow-up.
  - Keep Step 7 and Step 8 listed as future work.

- Modify: `app/recipe_parser.py`
  - Stop rejecting approved category-only identities.
  - Keep rejecting missing delimiter, empty identity before `|`, unknown category, missing percent, invalid percent, non-positive percent, and non-100 totals.
  - Keep `planned_material` as a string; category-only rows use `""`.

- Modify: `app/main.py`
  - Add a display fallback for structured rows where `planned_material == ""`.
  - Do not change form input names or actual material/batch save behavior.

- Modify: `app/importer.py`
  - Update the generated CSV template from unstructured `LDPE` to a valid structured sample such as `reLDPE | 100%`.

- Modify: `tests/test_recipe_parser.py`
  - Add parser coverage for both omitted producer/grade (`reLDPE | 80%`) and one-sided omissions (`LDPE B20/03 | 20%`).
  - Replace the old category-only rejection expectation.

- Modify: `tests/test_recipe_storage.py`
  - Add storage coverage proving empty-string `planned_material` is stored and fetched for valid category-only components.

- Modify: `tests/test_recipe_release_validation.py`
  - Add release success coverage for category-only rows.
  - Replace the old `LDPE | 80%` failure fixture with an actually malformed row such as `| 80%`.

- Modify: `tests/test_recipe_sync.py`
  - Add import/admin sync coverage for category-only rows and display fallback in admin/terminal contexts.
  - Add or extend print-boundary coverage that original source text remains unchanged.

- Modify: `tests/test_admin_card_review.py`
  - Add a backend admin context assertion for category-only display fallback if not covered in `test_recipe_sync.py`.

- Modify: `tests/test_admin_card_detail_redesign.py`
  - Add rendered admin HTML coverage for category-only structured rows only if backend context tests do not sufficiently cover the behavior.

- Modify: `tests/test_terminal_v8_render.py`
  - Add terminal rendered HTML coverage for category-only structured rows and absence of literal `N/A`.

- Modify: `tests/test_print_output.py`
  - Add print-route boundary coverage proving `reLDPE | 80%` prints exactly as original source text.

Files that should not change:

- `app/printing.py`
- `app/rules.py`, unless only release-message test expectations require no code change because parser behavior drives the rule.
- `app/templates/**`, unless the `app/main.py` display fallback is insufficient because the template explicitly renders `-` for blank planned material.
- `source-files/excel-macros/**`
- `interim-costing-process/source-files/recipe-builder-demo/**`

## Task 1: Update The Contract Documentation First

**Files:**

- Modify: `docs/implementation-notes/structured-recipe-contract.md`
- Modify: `open-issues.md`
- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update accepted cell format in `docs/implementation-notes/structured-recipe-contract.md`**

Change the accepted format section so it says the normal final source-cell format is still:

```text
[Material/Additive Category] [Producer or Brand] [Full Commercial Grade/Code] | [% of final product]
```

Then add this paragraph:

```markdown
The Excel recipe builder also supports intentional producer and/or grade
omissions through `N/A` values in `RecipeCatalog`. `N/A` is a catalog control
value only. It is not printed into the final `AM:AS` source cell. When both
producer and grade are `N/A`, the final source cell is category-only before the
delimiter:

```text
reLDPE | 80%
```

When only one of producer or grade is `N/A`, the final source cell contains the
category plus the remaining non-`N/A` text:

```text
LDPE Midilena | 77%
LDPE B20/03 | 77%
```
```

- [ ] **Step 2: Update normalized row documentation**

In the normalized app rows section, change the `planned_material` row to:

```markdown
| `planned_material` | Remaining material identity after the category; empty string when the Excel builder intentionally omitted both producer and grade |
```

Add this paragraph after the normalized rows table:

```markdown
For structured admin/terminal display, category-only rows should use the
canonical category as the visible planned material fallback. The normalized
stored value remains an empty string so the app does not invent producer or grade
data that did not exist in the workbook.
```

- [ ] **Step 3: Update validation intent**

Replace this old release blocker:

```markdown
- any non-empty row has missing or invalid material identity text;
```

with:

```markdown
- any non-empty row has missing identity text before `|`, an unapproved category,
  or invalid category text;
```

Keep percent, total, and target-gross blockers unchanged.

- [ ] **Step 4: Add locked contract decision 8**

Append this locked decision:

```markdown
8. Intentional producer/grade omissions from the Excel recipe builder are valid
   when represented by omitted text in the final source cell. The app allows
   category-only rows for all approved categories because it imports final cell
   text, not the Excel `RecipeCatalog`.
```

- [ ] **Step 5: Update `open-issues.md` roadmap**

Insert a new Step 6.5 between current Steps 6 and 7:

```markdown
6.5. Align app parser with Excel recipe-builder `N/A` omissions.
   - Allow final source cells such as `reLDPE | 80%` when the category is
     approved and producer/grade were intentionally omitted by the Excel builder.
   - Keep app-side validation limited to the final source-cell contract because
     the app does not import `RecipeCatalog`.
   - Preserve original source text for print and admin correction.
   - Keep malformed rows, invalid percentages, non-100 totals, and missing
     target gross blocked at release.
```

Renumbering later steps is optional. If renumbering creates unnecessary churn, keep the visible `6.5` decimal step.

- [ ] **Step 6: Update `IMPLEMENTATION_PLAN.md` structured recipe follow-up**

Add a Step 6.5 note after the Step 6 note. While executing, use “in progress”; after verification, update to “complete”.

In-progress wording:

```markdown
- OI-003 Step 6.5 in progress: align the app structured recipe contract with
  the Excel recipe-builder `N/A` omission behavior so valid final source cells
  such as `reLDPE | 80%` can import, normalize, release, and display while print
  continues to use original source text.
```

Completion wording:

```markdown
- OI-003 Step 6.5 complete: parser, release validation, normalized sync,
  admin/terminal structured display, sample CSV template, and print-boundary
  tests now accept Excel-builder category-only source cells such as
  `reLDPE | 80%` for approved categories while preserving original source text
  and release protections for malformed rows.
```

- [ ] **Step 7: Run a docs diff check**

Run:

```bash
git diff -- docs/implementation-notes/structured-recipe-contract.md open-issues.md IMPLEMENTATION_PLAN.md
```

Expected: only OI-003 Step 6.5 contract/planning text changed.

## Task 2: Add Failing Parser And Storage Tests

**Files:**

- Modify: `tests/test_recipe_parser.py`
- Modify: `tests/test_recipe_storage.py`

- [ ] **Step 1: Add parser test for category-only and one-sided omissions**

Append this test to `tests/test_recipe_parser.py`:

```python
def test_parse_allows_excel_builder_na_omissions():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "reLDPE | 80%",
            "linear_pe": "LLDPE 119ZJ | 20%",
        }
    )

    assert result.ok
    assert result.total_percent == Decimal("100")
    assert result.components == (
        ParsedRecipeComponent(
            component_key="raw_material_a",
            source_text="reLDPE | 80%",
            material_category="reLDPE",
            planned_material="",
            recipe_percent=Decimal("80"),
        ),
        ParsedRecipeComponent(
            component_key="linear_pe",
            source_text="LLDPE 119ZJ | 20%",
            material_category="LLDPE",
            planned_material="119ZJ",
            recipe_percent=Decimal("20"),
        ),
    )
```

- [ ] **Step 2: Replace old category-only rejection with empty-identity rejection**

Replace `test_parse_rejects_missing_material_after_category` with:

```python
def test_parse_rejects_missing_identity_before_percent_delimiter():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        " | 100%",
    )

    assert component is None
    assert errors[0].message == "липсва материал след категория"
```

This preserves protection for truly malformed rows while no longer rejecting `LDPE | 100%`.

- [ ] **Step 3: Add broad approved-category category-only test**

Append:

```python
def test_parse_category_only_is_allowed_for_any_approved_category():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "LDPE | 95%",
            "masterbatch": "Masterbatch | 5%",
        }
    )

    assert result.ok
    assert [
        (component.material_category, component.planned_material)
        for component in result.components
    ] == [("LDPE", ""), ("Masterbatch", "")]
```

- [ ] **Step 4: Add storage test for empty normalized planned material**

Append this to `tests/test_recipe_storage.py`:

```python
def test_recipe_components_store_category_only_planned_material_as_empty_string(connection):
    card_id = insert_card(connection, raw_material_a="reLDPE | 100%")

    result = db.parse_and_replace_recipe_components_for_card(
        connection,
        card_id,
        {"raw_material_a": "reLDPE | 100%"},
    )

    assert result.ok
    rows = db.fetch_recipe_components(connection, card_id)
    assert len(rows) == 1
    assert rows[0]["source_text"] == "reLDPE | 100%"
    assert rows[0]["material_category"] == "reLDPE"
    assert rows[0]["planned_material"] == ""
    assert rows[0]["recipe_percent"] == Decimal("100")
```

- [ ] **Step 5: Run parser/storage tests and verify they fail before implementation**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_parser.py tests/test_recipe_storage.py -q
```

Expected before implementation: parser tests fail because category-only rows still return `липсва материал след категория`.

## Task 3: Implement Parser Support For Category-Only Rows

**Files:**

- Modify: `app/recipe_parser.py`

- [ ] **Step 1: Change `parse_recipe_cell()` to allow empty `planned_material` after an approved category**

In `app/recipe_parser.py`, remove this block:

```python
    if not planned_material:
        return None, (
            RecipeParseError(
                component_key=component_key,
                source_text=original_source_text,
                message=MISSING_MATERIAL_MESSAGE,
            ),
        )
```

Do not remove the earlier `if not normalized_identity:` block. That earlier block still rejects rows like ` | 100%`.

- [ ] **Step 2: Run focused parser/storage tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_parser.py tests/test_recipe_storage.py -q
```

Expected after implementation: all parser and storage tests pass.

- [ ] **Step 3: Inspect the parser diff**

Run:

```bash
git diff -- app/recipe_parser.py tests/test_recipe_parser.py tests/test_recipe_storage.py
```

Expected: one parser behavior change plus focused tests. No database schema migration should be needed because `planned_material TEXT NOT NULL` accepts `""`.

## Task 4: Add Release, Sync, And Import Template Coverage

**Files:**

- Modify: `tests/test_recipe_release_validation.py`
- Modify: `tests/test_recipe_sync.py`
- Modify: `app/importer.py`

- [ ] **Step 1: Update release failure fixture that used to reject `LDPE | 80%`**

In `tests/test_recipe_release_validation.py`, replace this parameter entry:

```python
(
    "RS-REL-004",
    {"raw_material_a": "LDPE | 80%"},
    "Суровина A: липсва материал след категория",
),
```

with:

```python
(
    "RS-REL-004",
    {"raw_material_a": " | 80%"},
    "Суровина A: липсва материал след категория",
),
```

- [ ] **Step 2: Add release success test for category-only rows**

Append:

```python
def test_release_allows_category_only_recipe_rows_from_excel_builder_na_omissions(connection):
    card_id = import_structured_card(
        "RS-REL-022",
        raw_material_a="reLDPE | 80%",
        linear_pe="LLDPE SABIC 119ZJ | 20%",
    )

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["status"] == STATUS_PENDING
    assert card["raw_material_a"] == "reLDPE | 80%"
```

- [ ] **Step 3: Add broad category-only release success test**

Append:

```python
def test_release_allows_category_only_rows_for_all_approved_categories_without_catalog_lookup(connection):
    card_id = import_structured_card(
        "RS-REL-023",
        raw_material_a="LDPE | 95%",
        masterbatch="Masterbatch | 5%",
        linear_pe="",
    )

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)

    assert result.ok
```

- [ ] **Step 4: Add sync test for category-only normalized rows**

Append to `tests/test_recipe_sync.py`:

```python
def test_import_sync_stores_category_only_rows_with_empty_planned_material(connection):
    card_id = import_card(
        "RS-SYNC-012",
        raw_material_a="reLDPE | 80%",
        linear_pe="LLDPE SABIC 119ZJ | 20%",
    )

    assert component_summary(connection, card_id) == [
        ("raw_material_a", "reLDPE | 80%", "reLDPE", ""),
        ("linear_pe", "LLDPE SABIC 119ZJ | 20%", "LLDPE", "SABIC 119ZJ"),
    ]
```

- [ ] **Step 5: Add admin correction sync test**

Append:

```python
def test_admin_source_correction_syncs_category_only_rows(connection):
    card_id = import_card("RS-SYNC-013")
    card = db.fetch_admin_card_detail(card_id)
    fields = current_import_fields(card_id)
    fields["raw_material_a"] = "reLDPE | 100%"
    fields["linear_pe"] = ""

    result = db.update_admin_imported_fields(card_id, card["version"], fields)

    assert result.ok
    assert component_summary(connection, card_id) == [
        ("raw_material_a", "reLDPE | 100%", "reLDPE", ""),
    ]
```

- [ ] **Step 6: Update CSV template sample in `app/importer.py`**

Change:

```python
"raw_material_a": "LDPE",
```

to:

```python
"raw_material_a": "reLDPE | 100%",
```

This keeps the generated sample import release-valid and demonstrates the Excel-builder omission shape.

- [ ] **Step 7: Add importer template test if no existing test covers it**

If no test currently asserts the CSV template sample, add this to a focused importer or baseline test file such as `tests/test_baseline.py`:

```python
def test_csv_template_uses_valid_structured_recipe_sample():
    from app.importer import csv_template

    content = csv_template()

    assert "raw_material_a" in content
    assert "reLDPE | 100%" in content
    assert "N/A" not in content
```

- [ ] **Step 8: Run release/sync/import template tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_release_validation.py tests/test_recipe_sync.py tests/test_baseline.py -q
```

Expected: all pass after parser support and sample update.

## Task 5: Add Structured Display Fallback

**Files:**

- Modify: `app/main.py`
- Modify: `tests/test_recipe_sync.py`
- Modify if needed: `tests/test_admin_card_review.py`
- Modify if needed: `tests/test_admin_card_detail_redesign.py`
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Add backend display context test**

Append to `tests/test_recipe_sync.py`:

```python
def test_admin_and_terminal_display_use_category_fallback_for_category_only_rows(connection):
    card_id = import_card(
        "RS-SYNC-014",
        quantity_1="1000",
        unit_1="kg",
        raw_material_a="reLDPE | 80%",
        linear_pe="LLDPE SABIC 119ZJ | 20%",
    )
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok

    admin_context = admin_card_detail_context(card_id)
    terminal = terminal_context(card_id)
    admin_rows = {row["field"]: row for row in admin_context["recipe_rows"]}
    terminal_rows = {row["field"]: row for row in terminal["recipe_rows"]}

    assert admin_rows["raw_material_a"]["material_category"] == "reLDPE"
    assert admin_rows["raw_material_a"]["planned_material"] == "reLDPE"
    assert admin_rows["raw_material_a"]["source_text"] == "reLDPE | 80%"
    assert admin_rows["raw_material_a"]["recipe_percent"] == "80%"
    assert admin_rows["raw_material_a"]["planned_kg"] == "800.00"
    assert admin_rows["raw_material_a"]["is_structured"] is True

    assert terminal_rows["raw_material_a"]["material_category"] == "reLDPE"
    assert terminal_rows["raw_material_a"]["planned_material"] == "reLDPE"
    assert terminal_rows["raw_material_a"]["source_text"] == "reLDPE | 80%"
    assert terminal_rows["linear_pe"]["planned_material"] == "SABIC 119ZJ"
```

- [ ] **Step 2: Implement display fallback in `app/main.py`**

In `build_recipe_rows()`, replace:

```python
            planned_material = str(component.get("planned_material") or "")
            material_category = str(component.get("material_category") or "")
```

with:

```python
            material_category = str(component.get("material_category") or "")
            normalized_planned_material = str(component.get("planned_material") or "")
            planned_material = normalized_planned_material or material_category
```

Keep `source_text`, `recipe_percent`, `planned_kg`, actual material, and batch behavior unchanged.

- [ ] **Step 3: Add terminal rendered HTML test**

Append to `tests/test_terminal_v8_render.py`:

```python
def test_terminal_v8_renders_category_only_recipe_without_na_control_value(connection):
    card_id = release_ready_card(
        "26241",
        machine_id=1,
        sequence=1,
        raw_material_a="reLDPE | 80%",
        linear_pe="LLDPE SABIC 119ZJ | 20%",
        raw_material_b="",
        raw_material_c="",
        antistatic="",
        masterbatch="",
        chalk="",
    )

    html = render_terminal(card_id)
    recipe_html = form_block(html, f"/terminal/cards/{card_id}/materials")

    assert "reLDPE" in recipe_html
    assert "80%" in recipe_html
    assert "400.00" in recipe_html
    assert "SABIC 119ZJ" in recipe_html
    assert "N/A" not in recipe_html
    assert 'name="actual_material__raw_material_a"' in recipe_html
    assert 'name="batch_lot__raw_material_a"' in recipe_html
```

With the existing fixture target of `500 kg`, `80%` should display `400.00` kg.

- [ ] **Step 4: Add admin rendered HTML test only if backend context is insufficient**

If the implementation changes templates or if a regression could hide the fallback, add this to `tests/test_admin_card_detail_redesign.py`:

```python
def test_admin_detail_renders_category_only_recipe_without_na_control_value(connection):
    card_id = import_ready_card(
        "27109",
        raw_material_a="reLDPE | 80%",
        linear_pe="LLDPE SABIC 119ZJ | 20%",
        raw_material_b="",
        raw_material_c="",
        antistatic="",
        masterbatch="",
        chalk="",
    )
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="62.50",
    ).ok

    html = render_admin_detail(card_id)

    assert "reLDPE | 80%" in html
    assert "reLDPE" in html
    assert "80%" in html
    assert "2600.40" in html
    assert "N/A" not in html
```

The dense admin fixture uses `quantity_1="3250.50"`, so `80%` should display `2600.40` kg.

- [ ] **Step 5: Run display tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_sync.py tests/test_admin_card_review.py tests/test_admin_card_detail_redesign.py tests/test_terminal_v8_render.py -q
```

Expected: all pass.

## Task 6: Add Print Boundary Coverage

**Files:**

- Modify: `tests/test_print_output.py`
- Modify if needed: `tests/test_recipe_sync.py`

- [ ] **Step 1: Add print-route source-text preservation test**

Append to `tests/test_print_output.py` near the existing planned recipe print tests:

```python
def test_print_route_preserves_category_only_recipe_source_text(connection):
    card_id = make_completed_printable_card(
        "27061",
        raw_material_a="reLDPE | 80%",
        raw_material_b="",
        raw_material_c="",
        linear_pe="LLDPE SABIC 119ZJ | 20%",
        antistatic="",
        masterbatch="",
        chalk="",
    )

    response = get_print_page(card_id)

    assert response.status_code == 200
    planned_a = data_block(response.text, "data-front-recipe-planned", "raw_material_a")
    planned_linear = data_block(response.text, "data-front-recipe-planned", "linear_pe")
    assert rendered_text(planned_a) == "reLDPE | 80%"
    assert rendered_text(planned_linear) == "LLDPE SABIC 119ZJ | 20%"
    assert "N/A" not in response.text
```

If `make_completed_printable_card()` does not currently accept source-field overrides, first change its signature from:

```python
def make_completed_printable_card(
    order_number: str = "27000",
    roll_count: int = 1,
) -> int:
    card_id = import_card(order_number)
```

to:

```python
def make_completed_printable_card(
    order_number: str = "27000",
    roll_count: int = 1,
    **overrides: str,
) -> int:
    card_id = import_card(order_number, **overrides)
```

- [ ] **Step 2: Run print tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_print_output.py -q
```

Expected: all print tests pass and print output remains original-source-text based.

## Task 7: Full Focused Verification

**Files:**

- No code changes unless verification exposes a defect.

- [ ] **Step 1: Run focused structured recipe suite**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  tests/test_recipe_parser.py \
  tests/test_recipe_storage.py \
  tests/test_recipe_release_validation.py \
  tests/test_recipe_sync.py \
  tests/test_admin_card_review.py \
  tests/test_admin_card_detail_redesign.py \
  tests/test_terminal_v8_render.py \
  tests/test_print_output.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full Python suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected: all tests pass.

- [ ] **Step 3: Run diff whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 4: Review changed code**

Run:

```bash
git diff -- app/recipe_parser.py app/main.py app/importer.py docs/implementation-notes/structured-recipe-contract.md open-issues.md IMPLEMENTATION_PLAN.md tests/test_recipe_parser.py tests/test_recipe_storage.py tests/test_recipe_release_validation.py tests/test_recipe_sync.py tests/test_admin_card_review.py tests/test_admin_card_detail_redesign.py tests/test_terminal_v8_render.py tests/test_print_output.py
```

Review for:

- original source text preserved on `cards.raw_material_a` through `cards.chalk`;
- parser accepts only approved category-only rows, not unknown categories;
- release still blocks malformed rows, invalid percentages, non-100 totals, and missing/invalid target gross;
- import/admin draft correction remains permissive;
- normalized `recipe_components.planned_material` stores `""` for category-only rows;
- admin/terminal display uses category fallback for category-only rows;
- print output still uses original source fields unchanged;
- no catalog management, pricing, inventory, ERP, auth, or Excel macro work was added.

## Task 8: Focused Manual/UI Verification

**Files:**

- Artifacts only under `artifacts/ui-checks/recipe-na-omissions/`
- Temporary database only under `.test-runtime/recipe-na-omissions/`

- [ ] **Step 1: Create verification directories**

Run:

```bash
mkdir -p artifacts/ui-checks/recipe-na-omissions .test-runtime/recipe-na-omissions
```

- [ ] **Step 2: Start the app against a temporary database**

Run:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/recipe-na-omissions/extrusion_terminal.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep the server running until the Playwright check is complete. If port `8000` is already in use, use another local port and reflect that in the Playwright script.

- [ ] **Step 3: Use Playwright to import, release, and screenshot admin/terminal**

Run a Playwright script that:

1. Visits `/admin`.
2. Uploads a temporary CSV with:

```text
order_number,customer,product_type,quantity_1,unit_1,material,size_thickness,extrusion_flag,raw_material_a,linear_pe,packaging_method
NA-001,NA Omission Customer,PE film,1000,kg,LDPE,600/0.050,da,reLDPE | 80%,LLDPE SABIC 119ZJ | 20%,rolls
```

3. Opens the imported card detail.
4. Releases it to Machine 1, sequence 1.
5. Confirms the admin material table shows `reLDPE`, `80%`, `800.00`, and no `N/A`.
6. Visits `/terminal`.
7. Confirms the terminal material table shows `reLDPE`, `80%`, `800.00`, and no `N/A`.
8. Saves screenshots:

```text
artifacts/ui-checks/recipe-na-omissions/admin-category-only-recipe.png
artifacts/ui-checks/recipe-na-omissions/terminal-category-only-recipe.png
```

Expected: the card imports and releases; admin and terminal render category-only recipe rows without blank planned material and without literal `N/A`.

- [ ] **Step 4: Stop the dev server**

Stop the uvicorn process before finishing the session.

## Task 9: Final Documentation And Status Check

**Files:**

- Modify: `IMPLEMENTATION_PLAN.md`
- No staging or commit unless explicitly requested.

- [ ] **Step 1: Mark Step 6.5 complete in `IMPLEMENTATION_PLAN.md`**

Use the completion wording from Task 1 Step 6 after all automated and manual checks pass.

- [ ] **Step 2: Final status check**

Run:

```bash
git status --short
```

Expected:

- Modified files are limited to the Step 6.5 docs, parser/display/sample code, and focused tests.
- `artifacts/`, `.test-runtime/`, local databases, screenshots, Playwright output, and `node_modules/` remain untracked/ignored.
- No files are staged.

- [ ] **Step 3: Final verification summary**

Report:

- focused test command and result;
- full test command and result;
- `git diff --check` result;
- Playwright/manual screenshots captured;
- no staging or commit performed.

## Self-Review

- Spec coverage: the plan covers the Excel builder output shapes, category-only scope, realistic app validation limits without `RecipeCatalog`, normalized display choice, release gate, admin/terminal display, CSV template, print boundary, docs, Step 8 impact, and manual UI verification.
- Placeholder scan: no placeholder markers or unqualified test-writing steps remain.
- Type consistency: parser continues returning `ParsedRecipeComponent.planned_material: str`; category-only rows use `""`; `recipe_components.planned_material TEXT NOT NULL` remains valid; display row key remains `planned_material` and uses a category fallback.
