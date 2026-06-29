# OI-004 Canonical Target Gross Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align app release validation, planned kilograms, terminal target kilograms, remaining kilograms, and progress percentage to canonical workbook `Database!G` only, imported as `quantity_1`.

**Architecture:** Keep imported workbook fields `quantity_1`, `unit_1`, `quantity_2`, and `unit_2` stored and displayed as source workbook data, but centralize all target-gross calculations on `app.rules.target_gross_weight_from_card(card)`. The helper reads only `quantity_1`, parses it as a finite positive decimal kilogram value, and ignores `unit_1`, `quantity_2`, and `unit_2` for target gross. `app.main` display helpers call that same helper instead of maintaining duplicate kg-unit fallback logic.

**Tech Stack:** Python 3, FastAPI server-rendered templates, direct `sqlite3`, pytest with temporary SQLite databases, local Playwright for focused UI verification.

---

## Repository Rules For Execution

- Work in `/home/sk/projects/extrusion-terminal` on branch `structured-recipe-redesign`.
- Follow `AGENTS.md`; `README.md` is authoritative when repo docs conflict.
- Do not stage or commit unless the user explicitly asks.
- Do not mutate `data/extrusion_terminal.sqlite3`.
- Use the repo-local virtualenv for Python verification.
- Use local Node Playwright for browser verification if UI-visible behavior is checked.
- Keep screenshots, videos, traces, temporary app databases, and Playwright reports under untracked paths such as `artifacts/ui-checks/`.
- Keep this scoped to OI-004 only.

## Context Loaded Before This Plan

- `AGENTS.md`
- `open-issues.md`, especially `OI-004`
- `docs/implementation-notes/oi-003-step-8-export-validation-interim.md`
- `docs/implementation-notes/structured-recipe-contract.md`
- `app/rules.py`
- `app/main.py`
- `app/db.py` release path around `release_card`
- `tests/test_recipe_release_validation.py`
- `tests/test_structured_recipe_sample_csv.py`
- tests and templates found by searching for target gross, planned kilograms, remaining gross, progress percentage, and `quantity_1` through `unit_2`

## Exploration Findings

### Current Target-Gross Derivation Paths

- `app.rules.target_gross_weight_from_card(card)` currently loops over quantity line `1` and line `2`, requires a kg-like unit, and returns the first positive finite quantity.
- `app.rules.validate_structured_recipe_release(card)` calls that helper during release validation.
- `app.main.planned_kg_display(card, recipe_percent)` already calls `target_gross_weight_from_card(card)`, so planned recipe kilograms currently inherit the same quantity-line fallback behavior from `app.rules`.
- `app.main.target_gross_decimal(card)` duplicates target-gross parsing and loops over `quantity_1/unit_1` and `quantity_2/unit_2` with kg-like unit checks.
- `app.main.target_gross_display(card)`, `remaining_gross_display(card)`, and `progress_percent(card)` call `target_gross_decimal(card)`, so terminal target kilograms, remaining kilograms, and progress percentage currently use duplicated fallback logic rather than the backend release helper.
- `app.db.release_card()` fetches `IMPORT_FIELDS`, builds `card_fields`, checks usable extrusion, then calls `validate_structured_recipe_release(card_fields)` before any release mutation. Updating `app.rules` is enough to change the release gate.

### Display Paths To Preserve

- `app.main.build_quantity_lines(card)` and `build_quantity_display(card)` display both imported workbook quantity lines when present.
- `app/templates/admin_card_detail.html` keeps editable source fields for `quantity_1`, `unit_1`, `quantity_2`, and `unit_2`.
- `app/templates/terminal.html` shows `quantity_display` and recipe planned kilograms.
- `app.printing.assemble_print_data(card)` still maps `quantity_1`, `unit_1`, `quantity_2`, and `unit_2` to print data.
- These H/I/J fields should remain imported and displayed as source workbook data. They must be ignored for target gross and production calculations.

### Tests Currently Encoding Old Behavior

- `tests/test_recipe_release_validation.py::test_release_accepts_comma_decimal_recipe_percent_and_quantity_2_target_gross` currently expects release to pass when `quantity_1/unit_1` is non-kg and `quantity_2/unit_2` is kg-like.
- `tests/test_recipe_release_validation.py::test_release_blocks_missing_zero_or_invalid_target_gross` currently treats valid numeric `quantity_1` with non-kg `unit_1` as invalid. Under OI-004, positive finite `quantity_1` must pass regardless of `unit_1`.
- `tests/test_terminal_v8_render.py::test_target_gross_resolves_from_quantity_2_and_remaining_clamps` currently expects terminal target, remaining, and progress to derive from `quantity_2/unit_2`.
- Existing planned kilogram tests mostly use positive `quantity_1`, so they should continue to pass. Add a focused regression proving planned kilograms ignore a kg-like `quantity_2`.

## Behavior Rules

- `quantity_1` is the only app target gross source.
- `quantity_1` maps to workbook `Database!G`.
- `quantity_1` means gross kilograms by contract.
- `unit_1` must not be required or validated for target gross.
- `quantity_2` and `unit_2` must never influence release validation, planned kilograms, terminal target kilograms, remaining kilograms, or progress percentage.
- H/I/J (`unit_1`, `quantity_2`, `unit_2`) remain imported and displayed as original workbook fields.
- `quantity_1` must parse as a finite `Decimal` greater than `0`.
- Preserve existing comma-decimal parsing by keeping `str(value).strip().replace(",", ".")` before `Decimal(...)`.
- Block release when `quantity_1` is missing, empty, zero, negative, non-numeric, `NaN`, `Infinity`, or otherwise invalid.
- Release passes with valid positive `quantity_1` even when `unit_1`, `quantity_2`, or `unit_2` are blank, non-kg, or nonsensical.
- Planned kg is `recipe_percent * quantity_1 / 100`.
- Terminal target kg displays `quantity_1`.
- Terminal remaining kg is `max(quantity_1 - produced_gross, 0)`.
- Terminal progress percent is clamped to `0..100` using `produced_gross / quantity_1`.
- Do not add app-side workbook catalog validation. Catalog validation belongs to workbook/export validation, not the app.

## Non-Goals

- Do not change Excel macros.
- Do not change workbook export validation.
- Do not add workbook catalog validation to the app.
- Do not implement OI-005 workbook helper macro installation consolidation.
- Do not implement OI-006 Bulgarian workbook runtime message restoration.
- Do not change recipe parser category, percentage, or total rules.
- Do not change print layout.
- Do not hide or delete `unit_1`, `quantity_2`, or `unit_2`.
- Do not add authentication, permissions, costing, inventory, ERP, or workbook write-back behavior.

## Files To Modify During Implementation

- Modify: `app/rules.py`
  - Change `target_gross_weight_from_card(card)` to read only `quantity_1`.
  - Remove `TARGET_GROSS_UNITS` and `normalize_quantity_unit()` if they become unused.
  - Keep strict finite decimal parsing in `decimal_from_quantity_text(value)`.
- Modify: `app/main.py`
  - Change `target_gross_decimal(card)` to call `target_gross_weight_from_card(card)`.
  - Remove duplicate target-gross unit parsing helpers if no longer used.
  - Keep `planned_kg_display(card, recipe_percent)` using the central helper.
- Modify: `tests/test_recipe_release_validation.py`
  - Replace old quantity-2 fallback expectations with canonical `quantity_1` expectations.
  - Add release tests proving H/I/J are ignored.
  - Keep invalid `quantity_1` tests for empty, zero, negative, non-numeric, embedded unit text, `Infinity`, and `NaN`.
- Modify: `tests/test_terminal_v8_render.py`
  - Replace terminal quantity-2 fallback test with canonical `quantity_1` display/progress tests.
  - Add a display-helper regression where `quantity_2/unit_2` are kg-like but invalid or missing `quantity_1` yields no target.
- Modify: `tests/test_recipe_sync.py` or `tests/test_structured_recipe_sample_csv.py`
  - Add one planned-kg regression proving `quantity_2/unit_2` do not affect admin and terminal recipe planned kilograms.
- Modify: `IMPLEMENTATION_PLAN.md`
  - After code and verification complete, record OI-004 as complete or update the current milestone note so the next intended step is obvious.

Files that should not change for OI-004:

- `source-files/excel-macros/**`
- `interim-costing-process/source-files/recipe-builder-demo/**`
- `app/recipe_parser.py`
- `app/printing.py`, unless a failing test proves a direct display preservation issue
- `app/templates/**`, unless implementation uncovers a label that explicitly claims H/I/J drive target gross

## Approach Considered

Use one canonical app helper in `app.rules` and route all target-gross calculation paths through it.

Alternative 1 was to update release validation only. That would leave terminal target, remaining, and progress on the old quantity-2 fallback, which would keep the app internally inconsistent.

Alternative 2 was to add a new target-gross module. That is unnecessary for this small pilot because `app.rules` already owns release validation and `app.main` already imports the helper.

Recommended approach: update `app.rules.target_gross_weight_from_card(card)` and make `app.main.target_gross_decimal(card)` delegate to it.

## Task 1: Update Release-Validation Tests First

**Files:**

- Modify: `tests/test_recipe_release_validation.py`

- [ ] **Step 1: Replace the invalid non-kg unit case**

In `test_release_blocks_missing_zero_or_invalid_target_gross`, remove this old case because `unit_1` is no longer relevant:

```python
("RS-REL-012", {"quantity_1": "1000", "unit_1": "pcs"}),
```

Keep these invalid `quantity_1` cases:

```python
@pytest.mark.parametrize(
    ("order_number", "overrides"),
    [
        ("RS-REL-008", {"quantity_1": "", "unit_1": ""}),
        ("RS-REL-009", {"quantity_1": "0", "unit_1": "kg"}),
        ("RS-REL-010", {"quantity_1": "-10", "unit_1": "kg"}),
        ("RS-REL-011", {"quantity_1": "not a number", "unit_1": "kg"}),
        ("RS-REL-017", {"quantity_1": "-10 kg", "unit_1": "kg"}),
        ("RS-REL-018", {"quantity_1": "abc10", "unit_1": "kg"}),
        ("RS-REL-019", {"quantity_1": "10 kg", "unit_1": "kg"}),
        ("RS-REL-020", {"quantity_1": "Infinity", "unit_1": "kg"}),
        ("RS-REL-021", {"quantity_1": "NaN", "unit_1": "kg"}),
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

- [ ] **Step 2: Replace the old quantity-2 acceptance test**

Replace `test_release_accepts_comma_decimal_recipe_percent_and_quantity_2_target_gross` with this canonical-source test:

```python
def test_release_accepts_positive_quantity_1_without_unit_1_kg_check(connection):
    card_id = import_structured_card(
        "RS-REL-012",
        quantity_1="1250,5",
        unit_1="бр",
        quantity_2="not target gross",
        unit_2="nonsense",
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

- [ ] **Step 3: Add a regression that quantity_2 cannot rescue invalid quantity_1**

Add this test near the target-gross release tests:

```python
def test_release_blocks_invalid_quantity_1_even_when_quantity_2_is_kg_like(connection):
    card_id = import_structured_card(
        "RS-REL-024",
        quantity_1="",
        unit_1="",
        quantity_2="1250,5",
        unit_2="кг",
        raw_material_a="LDPE Rompetrol B20/03 | 97,5%",
        linear_pe="LLDPE SABIC 119ZJ | 2,5%",
    )

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)

    assert not result.ok
    assert result.messages == (
        f"{RECIPE_RELEASE_PREFIX}: липсват планирани кг/поръчано количество. "
        "Коригирайте рецептата и опитайте отново.",
    )
    assert_card_still_imported(card_id)
```

- [ ] **Step 4: Run the focused release tests and confirm failure before implementation**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_release_validation.py -q
```

Expected before implementation: the new canonical tests fail because the app still uses unit-based fallback logic.

## Task 2: Implement Canonical Target Gross In Backend Rules

**Files:**

- Modify: `app/rules.py`

- [ ] **Step 1: Change `target_gross_weight_from_card` to use `quantity_1` only**

Replace the current helper with:

```python
def target_gross_weight_from_card(card: dict[str, Any]) -> Decimal | None:
    quantity = decimal_from_quantity_text(card.get("quantity_1"))
    if quantity is not None and quantity > Decimal("0"):
        return quantity
    return None
```

- [ ] **Step 2: Remove unused unit-target constants/helpers**

If no other code imports them after Task 3, remove:

```python
TARGET_GROSS_UNITS = {"kg", "kgs", "кг", "килограм", "килограма"}


def normalize_quantity_unit(value: Any) -> str:
    return str(value or "").strip().casefold().rstrip(".")
```

Keep `decimal_from_quantity_text(value)` strict:

```python
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
```

- [ ] **Step 3: Run the focused release tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_release_validation.py -q
```

Expected after this task: all release-validation tests pass.

## Task 3: Route Terminal Target/Remaining/Progress Through The Canonical Helper

**Files:**

- Modify: `app/main.py`
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Update terminal helper tests**

Replace `test_target_gross_resolves_from_quantity_2_and_remaining_clamps` with:

```python
def test_target_gross_uses_quantity_1_and_ignores_quantity_units_and_secondary_quantity(
    connection,
):
    card_id = release_ready_card(
        "26141",
        machine_id=1,
        sequence=1,
        quantity_1="100",
        unit_1="ролки",
        quantity_2="9999",
        unit_2="kg",
    )
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "140.25").ok

    card = terminal_context(card_id)["selected_card"]

    assert target_gross_decimal(card) == 100
    assert card["target_gross_weight"] == "100.00"
    assert remaining_gross_display(card) == "0.00"
    assert progress_percent(card) == 100
    assert card["remaining_gross_weight"] == "0.00"
```

Replace `test_terminal_v8_does_not_show_fake_zero_target_when_no_kg_quantity` with:

```python
def test_terminal_v8_does_not_show_fake_zero_target_when_quantity_1_is_invalid(
    connection,
):
    card_id = release_ready_card(
        "26142",
        machine_id=1,
        sequence=1,
    )
    card = db.fetch_admin_card_detail(card_id)
    fields = {field: str(card[field] or "") for field in IMPORT_FIELDS}
    fields["quantity_1"] = ""
    fields["unit_1"] = "kg"
    fields["quantity_2"] = "20"
    fields["unit_2"] = "kg"
    assert db.update_admin_imported_fields(card_id, card_version(card_id), fields).ok

    html = render_terminal(card_id)
    card = terminal_context(card_id)["selected_card"]

    assert target_gross_decimal(card) is None
    assert card["target_gross_weight"] is None
    assert card["remaining_gross_weight"] is None
    assert '<span class="machine-tab-qty">0 / - кг</span>' in html
    assert re.search(
        r'<span class="field-label">Оставащи</span>\s*<div class="big">-</div>',
        html,
    )
```

- [ ] **Step 2: Change `target_gross_decimal` to delegate to `app.rules`**

Replace the current `target_gross_decimal` implementation with:

```python
def target_gross_decimal(card: dict[str, Any]) -> Decimal | None:
    return target_gross_weight_from_card(card)
```

- [ ] **Step 3: Remove duplicate target-gross parsing helpers from `app/main.py`**

If no remaining code in `app/main.py` uses them, remove these functions:

```python
def normalize_quantity_unit(value: Any) -> str:
    return str(value or "").strip().casefold().rstrip(".")


def decimal_from_quantity_text(value: Any) -> Decimal | None:
    direct_value = decimal_from_display(value)
    if direct_value is not None:
        return direct_value
    text = str(value or "").strip().replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None
```

Keep `decimal_from_display(value)` because other display helpers use it.

- [ ] **Step 4: Run focused terminal tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_target_gross_uses_quantity_1_and_ignores_quantity_units_and_secondary_quantity tests/test_terminal_v8_render.py::test_terminal_v8_does_not_show_fake_zero_target_when_quantity_1_is_invalid -q
```

Expected: both tests pass.

## Task 4: Add Planned-Kilogram Regression Coverage

**Files:**

- Modify: `tests/test_recipe_sync.py` or `tests/test_structured_recipe_sample_csv.py`

- [ ] **Step 1: Add a test proving planned kg ignores quantity_2**

Add this focused test to `tests/test_recipe_sync.py`, near the existing planned-kg display tests:

```python
def test_admin_and_terminal_planned_kg_use_quantity_1_only(connection):
    card_id = import_card(
        "RS-SYNC-015",
        quantity_1="1000",
        unit_1="rolls",
        quantity_2="9999",
        unit_2="kg",
        raw_material_a="LDPE Display Source | 80%",
        linear_pe="LLDPE Display Source | 20%",
    )
    assert db.release_card(card_id, machine_id=1, machine_sequence=1).ok

    admin_context = admin_card_detail_context(card_id)
    terminal = terminal_context(card_id)
    admin_rows = {row["field"]: row for row in admin_context["recipe_rows"]}
    terminal_rows = {row["field"]: row for row in terminal["recipe_rows"]}

    assert admin_rows["raw_material_a"]["planned_kg"] == "800.00"
    assert admin_rows["linear_pe"]["planned_kg"] == "200.00"
    assert terminal_rows["raw_material_a"]["planned_kg"] == "800.00"
    assert terminal_rows["linear_pe"]["planned_kg"] == "200.00"
```

- [ ] **Step 2: Run the planned-kg regression**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_sync.py::test_admin_and_terminal_planned_kg_use_quantity_1_only -q
```

Expected: test passes.

## Task 5: Verify Imported H/I/J Display Is Preserved

**Files:**

- Modify tests only if existing coverage is insufficient.

- [ ] **Step 1: Check existing display coverage**

Use these existing assertions as preservation coverage:

```python
assert [line["display"] for line in context["quantity_lines"]] == ["500 kg", "1200 m"]
```

from `tests/test_admin_card_review.py::test_admin_card_detail_context_groups_quantities_and_recipe_rows`.

Use print preservation coverage from `tests/test_print_output.py`, which asserts `quantity_1` and `quantity_2` remain in print data.

- [ ] **Step 2: Add a focused display assertion only if a code change touches display helpers**

If implementation changes `build_quantity_lines`, `build_quantity_display`, or `app.printing`, add this assertion to a relevant existing test:

```python
assert [line["display"] for line in context["quantity_lines"]] == [
    "1000 rolls",
    "9999 kg",
]
```

Expected: H/I/J continue displaying as imported workbook fields, while calculations ignore them.

## Task 6: Run Focused Automated Verification

**Files:**

- No source file changes in this task.

- [ ] **Step 1: Run target-gross and structured-recipe tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_release_validation.py tests/test_terminal_v8_render.py tests/test_recipe_sync.py tests/test_structured_recipe_sample_csv.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the baseline suite**

Run:

```bash
source .venv/bin/activate
python -m pytest -q
```

Expected: full test suite passes, with tests using temporary SQLite database paths.

- [ ] **Step 3: Run diff whitespace check**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

## Task 7: Manual App/UI Verification With Temporary Database

**Files:**

- Create untracked artifacts under `artifacts/ui-checks/oi-004-canonical-target-gross/`.
- Do not mutate `data/extrusion_terminal.sqlite3`.

- [ ] **Step 1: Start the app with a temporary database path**

Run:

```bash
mkdir -p .test-runtime artifacts/ui-checks/oi-004-canonical-target-gross
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/oi-004-ui.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected: server starts on `http://127.0.0.1:8000` and initializes `.test-runtime/oi-004-ui.sqlite3`.

- [ ] **Step 2: Use the app workflow with a sample CSV**

Import a CSV row through `/admin/import` with:

```text
quantity_1 = 1000
unit_1 = rolls
quantity_2 = 9999
unit_2 = kg
raw_material_a = LDPE Manual A | 80%
linear_pe = LLDPE Manual L | 20%
```

Expected:

- import succeeds;
- admin planning release succeeds;
- admin/terminal planned kg are `800.00` and `200.00`;
- terminal machine tab shows target `1000.00`, not `9999.00`;
- after adding produced gross above `1000`, remaining clamps to `0.00` and progress clamps to `100`.

- [ ] **Step 3: Capture Playwright screenshot**

Save at least one screenshot under:

```text
artifacts/ui-checks/oi-004-canonical-target-gross/
```

Expected: screenshot shows terminal target/remaining/planned kg values derived from `quantity_1`.

## Task 8: Update Milestone Tracker And Review The Diff

**Files:**

- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update `IMPLEMENTATION_PLAN.md`**

Add a concise current-state line after OI-004 implementation is verified:

```markdown
- OI-004 complete: app release validation, planned kilograms, terminal target kilograms, remaining kilograms, and progress percentage now use canonical `quantity_1` (`Database!G`) only; `unit_1`, `quantity_2`, and `unit_2` remain imported/displayed workbook fields and are ignored for target-gross calculations.
```

- [ ] **Step 2: Review changed code**

Run:

```bash
git diff -- app/rules.py app/main.py tests/test_recipe_release_validation.py tests/test_terminal_v8_render.py tests/test_recipe_sync.py IMPLEMENTATION_PLAN.md
```

Review for:

- data integrity;
- release validation messages;
- preservation of imported H/I/J source data;
- direct `/admin` and `/terminal` workflow behavior;
- no workbook macro changes;
- no OI-005 or OI-006 work.

- [ ] **Step 3: Check git status without staging**

Run:

```bash
git status --short
```

Expected: modified files are visible, artifacts remain untracked/ignored as appropriate, and nothing is staged unless the user explicitly asks.

## Verification Commands Summary

Use these commands before claiming OI-004 implementation is complete:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_release_validation.py tests/test_terminal_v8_render.py tests/test_recipe_sync.py tests/test_structured_recipe_sample_csv.py -q
python -m pytest -q
git diff --check
git status --short
```

For UI-visible verification:

```bash
mkdir -p .test-runtime artifacts/ui-checks/oi-004-canonical-target-gross
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/oi-004-ui.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
npx playwright test
```

If running the full Playwright suite is too broad for the approved implementation window, run a focused Playwright check that imports/releases a temporary-database card and captures a terminal screenshot showing canonical `quantity_1` target-gross behavior.

## Risks

- Existing production cards or test fixtures with invalid `quantity_1` but kg-like `quantity_2` will no longer release or show a target gross. This is intended by OI-004.
- `app.main` currently has a looser `decimal_from_quantity_text` that extracts digits from strings such as `10 kg`; routing display through `app.rules` will make display behavior stricter and consistent with release validation.
- Existing already-released cards can be edited by admin/imported-field correction flows. If `quantity_1` is later cleared, terminal display should show no target/remaining/progress rather than falling back to `quantity_2`.
- `unit_1` labels in the admin UI still say "Мярка" because the field remains imported workbook data. Avoid implying it validates target gross.

## Self-Review

- Spec coverage: this plan covers canonical `quantity_1`, ignored H/I/J, release blocking for invalid `quantity_1`, planned kg, terminal target/remaining/progress, display preservation, no catalog validation, no Excel macro work, and OI-005/OI-006 non-scope.
- Placeholder scan: no unresolved placeholder sections are present.
- Type consistency: helper names match current code: `target_gross_weight_from_card`, `target_gross_decimal`, `planned_kg_display`, `remaining_gross_display`, and `progress_percent`.
- Scope check: the plan is limited to app target-gross alignment and does not implement workbook macro consolidation or workbook runtime-message changes.
