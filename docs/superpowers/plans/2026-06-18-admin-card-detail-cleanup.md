# Admin Card Detail Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fix the usability regressions introduced by the admin card detail redesign: restore logical grouping inside order details, correct the materials ledger semantics, replace checkbox-based row deletion with explicit red X actions, and preserve section position after saves/deletes.

**Architecture:** Keep the current FastAPI/Jinja/server-rendered architecture. Prefer small template/CSS changes and reuse existing backend delete routes where possible. Add only minimal route support for anchor redirects so POST actions return users to the section they edited.

**Tech Stack:** FastAPI, direct `sqlite3`, Jinja2 templates, existing CSS in `app/static/css/app.css`, pytest, Playwright.

---

## Preconditions

- Work in `/home/sk/projects/extrusion-terminal`.
- Read `AGENTS.md` before starting.
- Use the repo-local Python virtualenv `.venv`.
- Do not mutate the real runtime database at `data/extrusion_terminal.sqlite3`.
- Do not stage or commit unless the user explicitly asks.
- The branch is expected to be `admin-card-detail-redesign`.
- The current page being cleaned up is `/admin/cards/{card_id}` after the admin detail redesign work.

Run before task work:

```bash
git branch --show-current
git status --short
```

Expected branch:

```text
admin-card-detail-redesign
```

Expected status may include existing uncommitted admin redesign files. Do not revert user changes or unrelated files.

---

## Current Problems To Fix

1. The order data pane is too compact and flat.
   - It currently renders one large `admin-compact-grid`.
   - It mixes order, client, product, operations, packaging, and notes without visual grouping.
   - The baseline had a separate `Екструзия` section; the redesign collapsed that useful structure.

2. The materials ledger has the wrong semantic shape.
   - `raw_material_brand_grade` is an existing card-level/raw-material-A field, not a per-row material ledger field.
   - The redesigned table added a `Марка / клас` column that only has an input on `raw_material_a` and dashes for all other rows.
   - This mixes editable and read-only cells in a mostly empty column and makes the table confusing.

3. Roll and timing deletion use checkbox-delete semantics.
   - The UI currently shows a checkbox plus visible `Да` text per row.
   - Deletion happens only when the user also clicks the section save button.
   - This is not how destructive row actions normally work and is hard to understand.

4. Successful POST actions return to the top of the page.
   - `admin_card_post_response()` redirects to `/admin/cards/{card_id}`.
   - Lower-section saves/deletes should return to their section anchor.

---

## File Structure

- Modify `app/templates/admin_card_detail.html`
  - Add section IDs: `order`, `materials`, `rolls`, `timing`, and `system`.
  - Split the order/imported-fields pane into logical groups inside one form.
  - Remove `Марка / клас` from the materials table columns.
  - Do not render the legacy `raw_material_brand_grade` field in the admin materials ledger.
  - Replace roll/timing delete checkboxes with per-row red X delete forms.
  - Add simple `confirm(...)` prompts to destructive X forms.

- Modify `app/static/css/app.css`
  - Add compact group styling inside the order details pane.
  - Add red X row-action button styling.
  - Remove or stop using `delete-check` styles for admin ledger deletion.
  - Ensure grouped order fields remain readable on desktop and mobile.

- Modify `app/main.py`
  - Add anchor support to `admin_card_post_response(...)`.
  - Pass anchors from admin detail POST routes:
    - imported fields -> `#order`
    - materials ledger -> `#materials`
    - roll ledger/add/update/delete -> `#rolls`
    - timing ledger/add/update/delete -> `#timing`
    - cancel/restore/imported-card delete can stay top-level unless a task explicitly changes them.

- Modify `tests/test_admin_card_detail_redesign.py`
  - Add/adjust render tests for order grouping, materials semantics, X delete buttons, and absence of checkbox-delete text.
  - Add route/response tests for anchor redirects.

- Update `IMPLEMENTATION_PLAN.md`
  - Add a short note that admin detail cleanup was completed after the redesign pass.

---

## Design Targets

### Order Details Pane

Keep one form and one save button, but split fields into visual groups:

- `Поръчка`
  - `order_number`
  - `order_date`
  - `delivery_date`

- `Клиент`
  - `customer`
  - `city`

- `Изделие`
  - `product_type`
  - `quantity_1`
  - `unit_1`
  - `quantity_2`
  - `unit_2`
  - `size_thickness`
  - `product_form`
  - `material`
  - `max_roll_weight`

- `Операции`
  - `extrusion_flag`
  - `extrusion_folding`
  - `extrusion_next_operation`
  - `extrusion_treatment`
  - `packaging_method`

- `Забележки`
  - `notes`

### Materials Ledger

Final table columns:

- `Позиция`
- `По карта`
- `Реално използвано`
- `Партида`

Do not expose the legacy `raw_material_brand_grade` value in this admin UI. Keep one materials save button, and preserve any existing legacy `raw_material_brand_grade` value when saving the materials ledger.

### Roll Ledger Delete UX

Per roll row:

- Keep row number.
- Keep editable gross input.
- Keep read-only net display.
- Add a red `×` button in a small action column.
- Do not show checkbox.
- Do not show visible `Да`.

Confirmation text:

```text
Да се изтрие ли ролка {roll_number} с бруто {gross_weight_or_dash} кг?
```

### Timing Ledger Delete UX

Per timing segment row:

- Keep editable start input.
- Keep editable end input.
- Keep reason select.
- Add a red `×` button in a small action column.
- Do not show checkbox.
- Do not show visible `Да`.

Confirmation text:

```text
Да се изтрие ли времеви сегмент {index}: {started_at} - {ended_at_or_in_progress}?
```

Use `в ход` when `ended_at` is blank.

---

## Tasks

### Task 1: Add Render Regression Tests For Cleanup Shape

**Files:**
- Modify: `tests/test_admin_card_detail_redesign.py`
- Read: `app/templates/admin_card_detail.html`

- [x] **Step 1: Add tests for grouped order details, corrected materials table, and X delete controls**

Append these tests near the existing render tests in `tests/test_admin_card_detail_redesign.py`:

```python
def test_admin_order_details_are_grouped_into_logical_sections(connection):
    card_id = prepare_dense_completed_card("27101", roll_count=2)

    html = render_admin_detail(card_id)

    assert 'id="order"' in html
    assert 'class="admin-order-group"' in html
    assert html.count("admin-order-group") >= 5
    assert "Поръчка" in html
    assert "Клиент" in html
    assert "Изделие" in html
    assert "Операции" in html
    assert "Забележки" in html
    assert html.find("Поръчка") < html.find("Клиент") < html.find("Изделие")
    assert html.find("Изделие") < html.find("Операции") < html.find("Забележки")


def test_admin_materials_ledger_omits_brand_class_field(connection):
    card_id = prepare_dense_completed_card("27102", roll_count=2)

    html = render_admin_detail(card_id)

    assert 'id="materials"' in html
    assert "Марка / клас" not in html
    assert 'name="raw_material_brand_grade"' not in html
    assert html.count('name="planned_material__raw_material_a"') == 1
    assert html.count('name="actual_material__raw_material_a"') == 1
    assert html.count('name="batch_lot__raw_material_a"') == 1


def test_admin_roll_and_timing_ledgers_use_explicit_x_delete_actions(connection):
    card_id = prepare_dense_completed_card("27103", roll_count=3)

    html = render_admin_detail(card_id)

    assert 'id="rolls"' in html
    assert 'id="timing"' in html
    assert 'name="delete_roll_id"' not in html
    assert 'name="delete_segment_id"' not in html
    assert ">Да</span>" not in html
    assert html.count("admin-row-delete-button") >= 2
    assert "/rolls/" in html
    assert "/delete" in html
    assert "/timing-segments/" in html
    assert "return confirm(" in html
```

- [x] **Step 2: Run the new render tests and verify they fail**

Run:

```bash
source .venv/bin/activate && python -m pytest \
  tests/test_admin_card_detail_redesign.py::test_admin_order_details_are_grouped_into_logical_sections \
  tests/test_admin_card_detail_redesign.py::test_admin_materials_ledger_keeps_brand_class_outside_row_table \
  tests/test_admin_card_detail_redesign.py::test_admin_roll_and_timing_ledgers_use_explicit_x_delete_actions \
  -q
```

Expected:

```text
FAILED
```

Expected reasons:

- `id="order"` is missing.
- `admin-order-group` is missing.
- `Марка / клас</div>` is still present in the materials table.
- `name="delete_roll_id"` and `name="delete_segment_id"` are still present.
- `admin-row-delete-button` is missing.

Do not change implementation until this red run has happened.

---

### Task 2: Group The Order Details Pane

**Files:**
- Modify: `app/templates/admin_card_detail.html`
- Modify: `app/static/css/app.css`
- Test: `tests/test_admin_card_detail_redesign.py`

- [x] **Step 1: Replace the flat order grid with grouped fieldsets**

In `app/templates/admin_card_detail.html`, find:

```html
<section class="section operational-panel admin-compact-card">
```

Change it to:

```html
<section class="section operational-panel admin-compact-card" id="order">
```

Inside that section, replace the single flat:

```html
<div class="admin-compact-grid">
  ...
</div>
```

with this grouped structure. Preserve the existing input names exactly:

```html
<div class="admin-order-groups">
  <fieldset class="admin-order-group">
    <legend>Поръчка</legend>
    <div class="admin-compact-grid">
      <label class="field-short">
        <span>№ поръчка</span>
        <input name="order_number" value="{{ card.order_number or '' }}" required>
      </label>
      <label class="field-short">
        <span>Дата</span>
        <input name="order_date" value="{{ card.order_date or '' }}">
      </label>
      <label class="field-short">
        <span>Дата доставка</span>
        <input name="delivery_date" value="{{ card.delivery_date or '' }}">
      </label>
    </div>
  </fieldset>

  <fieldset class="admin-order-group">
    <legend>Клиент</legend>
    <div class="admin-compact-grid">
      <label class="field-wide">
        <span>Клиент</span>
        <input name="customer" value="{{ card.customer or '' }}">
      </label>
      <label class="field-medium">
        <span>Град</span>
        <input name="city" value="{{ card.city or '' }}">
      </label>
    </div>
  </fieldset>

  <fieldset class="admin-order-group">
    <legend>Изделие</legend>
    <div class="admin-compact-grid">
      <label class="field-wide">
        <span>Вид изделие</span>
        <input name="product_type" value="{{ card.product_type or '' }}">
      </label>
      <label class="field-short">
        <span>Количество</span>
        <input name="quantity_1" value="{{ card.quantity_1 or '' }}">
      </label>
      <label class="field-short">
        <span>Мярка</span>
        <input name="unit_1" value="{{ card.unit_1 or '' }}">
      </label>
      <label class="field-short">
        <span>Допълнително</span>
        <input name="quantity_2" value="{{ card.quantity_2 or '' }}">
      </label>
      <label class="field-short">
        <span>Мярка</span>
        <input name="unit_2" value="{{ card.unit_2 or '' }}">
      </label>
      <label class="field-medium">
        <span>Размер/дебелина</span>
        <input name="size_thickness" value="{{ card.size_thickness or '' }}">
      </label>
      <label class="field-medium">
        <span>Вид заготовка</span>
        <input name="product_form" value="{{ card.product_form or '' }}">
      </label>
      <label class="field-medium">
        <span>Материал</span>
        <input name="material" value="{{ card.material or '' }}">
      </label>
      <label class="field-short">
        <span>Макс. тегло ролка, кг</span>
        <input name="max_roll_weight" value="{{ card.max_roll_weight or '' }}">
      </label>
    </div>
  </fieldset>

  <fieldset class="admin-order-group">
    <legend>Операции</legend>
    <div class="admin-compact-grid">
      <label class="field-short">
        <span>Екструзия</span>
        <input name="extrusion_flag" value="{{ card.extrusion_flag or '' }}">
      </label>
      <label class="field-medium">
        <span>Фалцоване</span>
        <input name="extrusion_folding" value="{{ card.extrusion_folding or '' }}">
      </label>
      <label class="field-medium">
        <span>Следваща операция</span>
        <input name="extrusion_next_operation" value="{{ card.extrusion_next_operation or '' }}">
      </label>
      <label class="field-medium">
        <span>Третиране</span>
        <input name="extrusion_treatment" value="{{ card.extrusion_treatment or '' }}">
      </label>
      <label class="field-medium">
        <span>Опаковка</span>
        <input name="packaging_method" value="{{ card.packaging_method or '' }}">
      </label>
    </div>
  </fieldset>

  <fieldset class="admin-order-group">
    <legend>Забележки</legend>
    <div class="admin-compact-grid">
      <label class="field-full">
        <span>Забележки</span>
        <textarea name="notes" rows="3">{{ card.notes or "" }}</textarea>
      </label>
    </div>
  </fieldset>
</div>
```

- [x] **Step 2: Add grouped order CSS**

In `app/static/css/app.css`, near the existing `.admin-compact-grid` rules, add:

```css
.admin-order-groups {
  display: grid;
  gap: 12px;
}

.admin-order-group {
  display: grid;
  gap: 10px;
  min-width: 0;
  margin: 0;
  border: 1px solid var(--line);
  border-radius: 7px;
  padding: 12px;
  background: var(--surface);
}

.admin-order-group legend {
  padding: 0 6px;
  color: var(--text);
  font-size: 13px;
  font-weight: 850;
}
```

- [x] **Step 3: Run the order grouping test**

Run:

```bash
source .venv/bin/activate && python -m pytest \
  tests/test_admin_card_detail_redesign.py::test_admin_order_details_are_grouped_into_logical_sections \
  -q
```

Expected:

```text
1 passed
```

- [x] **Step 4: Inspect the diff for this task**

Run:

```bash
git diff -- app/templates/admin_card_detail.html app/static/css/app.css
```

Confirm:

- Only the order details pane and CSS grouping styles changed.
- Input names are unchanged.
- The form still has one submit button: `Запази данните`.

---

### Task 3: Fix The Materials Ledger Semantics

**Files:**
- Modify: `app/templates/admin_card_detail.html`
- Modify: `app/static/css/app.css`
- Test: `tests/test_admin_card_detail_redesign.py`

- [x] **Step 1: Add an anchor to the materials section**

In `app/templates/admin_card_detail.html`, find the materials section:

```html
<section class="section operational-panel">
  <form class="admin-ledger-form" action="/admin/cards/{{ card.id }}/materials-ledger" method="post">
```

Change it to:

```html
<section class="section operational-panel" id="materials">
  <form class="admin-ledger-form" action="/admin/cards/{{ card.id }}/materials-ledger" method="post">
```

- [x] **Step 2: Remove the brand/class column from the materials table**

Change the materials ledger header from:

```html
<div class="admin-ledger-head">
  <div>Позиция</div>
  <div>По карта</div>
  <div>Реално използвано</div>
  <div>Марка / клас</div>
  <div>Партида</div>
</div>
```

to:

```html
<div class="admin-ledger-head">
  <div>Позиция</div>
  <div>По карта</div>
  <div>Реално използвано</div>
  <div>Партида</div>
</div>
```

Each materials row should use only row-level planned, actual, and batch inputs:

```html
<div class="admin-ledger-row material-ledger-row">
  <div class="component">{{ row.label }}</div>
  <div>
    <input name="planned_material__{{ row.field }}" value="{{ row.planned }}">
  </div>
  <div>
    <input name="actual_material__{{ row.field }}" value="{{ row.actual_material or '' }}">
  </div>
  <div>
    <input name="batch_lot__{{ row.field }}" value="{{ row.batch or '' }}">
  </div>
</div>
```

- [x] **Step 3: Preserve legacy brand/class without rendering it**

Do not add a `raw_material_brand_grade` input to the admin materials ledger. If the backend material-ledger save path receives no brand/class value, preserve the existing `cards.raw_material_brand_grade` value instead of clearing it.

- [x] **Step 4: Update material ledger grid CSS**

In `app/static/css/app.css`, change:

```css
.material-ledger .admin-ledger-head,
.material-ledger .admin-ledger-row {
  grid-template-columns: 90px minmax(180px, 1fr) minmax(180px, 1fr) minmax(130px, 0.7fr) minmax(140px, 0.7fr);
}
```

to:

```css
.material-ledger .admin-ledger-head,
.material-ledger .admin-ledger-row {
  grid-template-columns: 90px minmax(180px, 1fr) minmax(180px, 1fr) minmax(140px, 0.8fr);
}
```

In the mobile media query, change:

```css
.material-ledger .admin-ledger-head,
.material-ledger .admin-ledger-row {
  min-width: 760px;
}
```

to:

```css
.material-ledger .admin-ledger-head,
.material-ledger .admin-ledger-row {
  min-width: 640px;
}
```

- [x] **Step 5: Run the materials semantics test**

Run:

```bash
source .venv/bin/activate && python -m pytest \
  tests/test_admin_card_detail_redesign.py::test_admin_materials_ledger_keeps_brand_class_outside_row_table \
  -q
```

Expected:

```text
1 passed
```

- [x] **Step 6: Run existing material ledger backend tests**

Run:

```bash
source .venv/bin/activate && python -m pytest \
  tests/test_admin_card_detail_redesign.py::test_admin_material_ledger_updates_planned_and_actual_fields \
  tests/test_admin_card_detail_redesign.py::test_admin_material_ledger_blocks_stale_version \
  -q
```

Expected:

```text
2 passed
```

---

### Task 4: Replace Checkbox Deletes With Explicit Red X Forms

**Files:**
- Modify: `app/templates/admin_card_detail.html`
- Modify: `app/static/css/app.css`
- Test: `tests/test_admin_card_detail_redesign.py`

- [x] **Step 1: Add anchors to roll and timing sections**

In `app/templates/admin_card_detail.html`, change the roll section from:

```html
<section class="section operational-panel">
  <form class="admin-ledger-form" action="/admin/cards/{{ card.id }}/roll-ledger" method="post">
```

to:

```html
<section class="section operational-panel" id="rolls">
  <form class="admin-ledger-form" action="/admin/cards/{{ card.id }}/roll-ledger" method="post">
```

Change the timing section from:

```html
<section class="section operational-panel">
  <form class="admin-ledger-form" action="/admin/cards/{{ card.id }}/timing-ledger" method="post">
```

to:

```html
<section class="section operational-panel" id="timing">
  <form class="admin-ledger-form" action="/admin/cards/{{ card.id }}/timing-ledger" method="post">
```

- [x] **Step 2: Replace roll delete checkbox cells**

In each roll ledger row, replace:

```html
<label class="delete-check">
  <input type="checkbox" name="delete_roll_id" value="{{ roll.id }}" aria-label="Изтрий ролка {{ roll.roll_number }}">
  <span>Да</span>
</label>
```

with:

```html
<div class="ledger-row-actions">
  <form class="ledger-delete-form" action="/admin/cards/{{ card.id }}/rolls/{{ roll.id }}/delete" method="post" onsubmit="return confirm('Да се изтрие ли ролка {{ roll.roll_number }} с бруто {{ roll.gross_weight if roll.gross_weight is not none else '-' }} кг?');">
    <input type="hidden" name="loaded_version" value="{{ card.version }}">
    <button class="admin-row-delete-button" type="submit" aria-label="Изтрий ролка {{ roll.roll_number }}">×</button>
  </form>
</div>
```

Change the roll table action header from:

```html
<div>Изтрий</div>
```

to this empty visual header with an accessible label:

```html
<div><span class="visually-hidden">Изтриване</span></div>
```

The row button `aria-label` carries the row-specific action name.

- [x] **Step 3: Replace timing delete checkbox cells**

In each timing ledger row, replace:

```html
<label class="delete-check">
  <input type="checkbox" name="delete_segment_id" value="{{ segment.id }}" aria-label="Изтрий времеви сегмент {{ loop.index }}">
  <span>Да</span>
</label>
```

with:

```html
<div class="ledger-row-actions">
  <form class="ledger-delete-form" action="/admin/cards/{{ card.id }}/timing-segments/{{ segment.id }}/delete" method="post" onsubmit="return confirm('Да се изтрие ли времеви сегмент {{ loop.index }}: {{ segment.started_at }} - {{ segment.ended_at or 'в ход' }}?');">
    <input type="hidden" name="loaded_version" value="{{ card.version }}">
    <button class="admin-row-delete-button" type="submit" aria-label="Изтрий времеви сегмент {{ loop.index }}">×</button>
  </form>
</div>
```

Leave the new timing segment row action cell as:

```html
<div class="readonly-cell">Нов</div>
```

- [x] **Step 4: Remove delete IDs from bulk ledger form parsing only if they become unused by tests**

Do not remove `delete_roll_id` or `delete_segment_id` parsing in `app/main.py` yet. Keeping it is harmless compatibility for the bulk backend helper. The render tests should prove the current UI no longer emits those fields.

- [x] **Step 5: Add red X button CSS**

In `app/static/css/app.css`, near ledger styles, add:

```css
.ledger-row-actions {
  display: flex;
  align-items: center;
  justify-content: center;
}

.ledger-delete-form {
  margin: 0;
}

.admin-row-delete-button {
  display: inline-grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--red);
  border-radius: 6px;
  background: #fff5f5;
  color: var(--red);
  font-size: 20px;
  font-weight: 900;
  line-height: 1;
  cursor: pointer;
}

.admin-row-delete-button:hover,
.admin-row-delete-button:focus {
  background: var(--red);
  color: white;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

Do not rely on `.delete-check` for the new UI.

- [x] **Step 6: Run the X delete render test**

Run:

```bash
source .venv/bin/activate && python -m pytest \
  tests/test_admin_card_detail_redesign.py::test_admin_roll_and_timing_ledgers_use_explicit_x_delete_actions \
  -q
```

Expected:

```text
1 passed
```

- [x] **Step 7: Run existing delete behavior tests**

Run:

```bash
source .venv/bin/activate && python -m pytest \
  tests/test_admin_production_corrections.py \
  tests/test_finish_cancel_history.py \
  tests/test_roll_entry.py \
  tests/test_production_timing.py \
  -q
```

Expected:

```text
passed
```

If a test fails because it asserts old checkbox markup, update that test only if it is a render-shape test for the old UI. Do not weaken backend invariant tests.

---

### Task 5: Preserve Section Position After Admin Detail POSTs

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_admin_card_detail_redesign.py`

- [x] **Step 1: Add tests for anchor redirects**

Append these tests to `tests/test_admin_card_detail_redesign.py`:

```python
def test_admin_card_post_response_redirects_to_section_anchor_on_success(connection):
    from app.main import admin_card_post_response
    from app.rules import RuleResult

    card_id = prepare_dense_completed_card("27104", roll_count=1)
    response = admin_card_post_response(
        FormRequest(MultiItemForm([])),
        card_id,
        "roll_result",
        RuleResult(True, ("ok",)),
        anchor="rolls",
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/cards/{card_id}#rolls"


def test_admin_card_post_response_without_anchor_keeps_existing_redirect(connection):
    from app.main import admin_card_post_response
    from app.rules import RuleResult

    card_id = prepare_dense_completed_card("27105", roll_count=1)
    response = admin_card_post_response(
        FormRequest(MultiItemForm([])),
        card_id,
        "workflow_result",
        RuleResult(True, ("ok",)),
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/cards/{card_id}"
```

- [x] **Step 2: Run the anchor tests and verify the first fails**

Run:

```bash
source .venv/bin/activate && python -m pytest \
  tests/test_admin_card_detail_redesign.py::test_admin_card_post_response_redirects_to_section_anchor_on_success \
  tests/test_admin_card_detail_redesign.py::test_admin_card_post_response_without_anchor_keeps_existing_redirect \
  -q
```

Expected:

```text
FAILED
```

Expected reason:

```text
TypeError: admin_card_post_response() got an unexpected keyword argument 'anchor'
```

- [x] **Step 3: Add anchor support to `admin_card_post_response`**

In `app/main.py`, change:

```python
def admin_card_post_response(
    request: Request,
    card_id: int,
    result_name: str,
    result: RuleResult,
):
    if result.ok:
        return RedirectResponse(url=f"/admin/cards/{card_id}", status_code=303)
```

to:

```python
def admin_card_post_response(
    request: Request,
    card_id: int,
    result_name: str,
    result: RuleResult,
    anchor: str | None = None,
):
    if result.ok:
        suffix = f"#{anchor}" if anchor else ""
        return RedirectResponse(url=f"/admin/cards/{card_id}{suffix}", status_code=303)
```

Leave the error-render path unchanged:

```python
context = admin_card_detail_context(card_id, **{result_name: result})
```

Errors should stay on the rendered page with visible messages.

- [x] **Step 4: Pass anchors from admin detail routes**

In `app/main.py`, update these `admin_card_post_response(...)` calls:

Imported fields:

```python
return admin_card_post_response(
    request,
    card_id,
    "imported_field_result",
    imported_field_result,
    anchor="order",
)
```

Materials:

```python
return admin_card_post_response(
    request,
    card_id,
    "material_result",
    material_result,
    anchor="materials",
)
```

Tare, add roll, roll ledger, update roll, delete roll:

```python
return admin_card_post_response(
    request,
    card_id,
    "roll_result",
    roll_result,
    anchor="rolls",
)
```

Add timing, timing ledger, update timing, delete timing:

```python
return admin_card_post_response(
    request,
    card_id,
    "timing_result",
    timing_result,
    anchor="timing",
)
```

Do not add anchors to admin navigation routes, cancel/restore routes, or imported-card delete unless a test requires it.

- [x] **Step 5: Run anchor tests**

Run:

```bash
source .venv/bin/activate && python -m pytest \
  tests/test_admin_card_detail_redesign.py::test_admin_card_post_response_redirects_to_section_anchor_on_success \
  tests/test_admin_card_detail_redesign.py::test_admin_card_post_response_without_anchor_keeps_existing_redirect \
  -q
```

Expected:

```text
2 passed
```

- [x] **Step 6: Run route smoke tests affected by redirect changes**

Run:

```bash
source .venv/bin/activate && python -m pytest \
  tests/test_admin_card_detail_redesign.py \
  tests/test_admin_routes.py \
  tests/test_admin_production_corrections.py \
  -q
```

Expected:

```text
passed
```

---

### Task 6: Focused Visual Verification

**Files:**
- Read/verify: `app/templates/admin_card_detail.html`
- Read/verify: `app/static/css/app.css`
- Create artifacts under: `artifacts/ui-checks/admin-card-detail-cleanup/`

- [x] **Step 1: Create artifact and temp DB directories**

Run:

```bash
mkdir -p artifacts/ui-checks/admin-card-detail-cleanup .test-runtime/admin-card-detail-cleanup
```

Expected:

```text
```

No output.

- [x] **Step 2: Seed a temporary database only**

Run:

```bash
bash -lc 'source .venv/bin/activate && export EXTRUSION_DB_PATH=/home/sk/projects/extrusion-terminal/.test-runtime/admin-card-detail-cleanup/redesign.sqlite3 && python -c "from pathlib import Path; from app import db; p=Path(db.DB_PATH); p.unlink(missing_ok=True); db.init_db(); from tests.test_admin_card_detail_redesign import prepare_dense_completed_card; card_id=prepare_dense_completed_card(\"28101\", roll_count=60); print(card_id)"'
```

Expected:

```text
1
```

Do not use `data/extrusion_terminal.sqlite3`.

- [x] **Step 3: Start the app against the temporary database**

Run:

```bash
bash -lc 'source .venv/bin/activate && EXTRUSION_DB_PATH=/home/sk/projects/extrusion-terminal/.test-runtime/admin-card-detail-cleanup/redesign.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8019'
```

Expected:

```text
Uvicorn running on http://127.0.0.1:8019
```

Keep this server running until screenshots are captured.

- [x] **Step 4: Capture desktop and mobile screenshots**

In a second shell, run:

```bash
bash -lc 'node -e "const { chromium } = require(\"@playwright/test\"); (async () => { const browser = await chromium.launch({ headless: true }); const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } }); await page.goto(\"http://127.0.0.1:8019/admin/cards/1\", { waitUntil: \"networkidle\" }); await page.screenshot({ path: \"artifacts/ui-checks/admin-card-detail-cleanup/desktop-detail.png\", fullPage: true }); const mobile = await browser.newPage({ viewport: { width: 390, height: 1200 }, isMobile: true }); await mobile.goto(\"http://127.0.0.1:8019/admin/cards/1\", { waitUntil: \"networkidle\" }); await mobile.screenshot({ path: \"artifacts/ui-checks/admin-card-detail-cleanup/mobile-detail.png\", fullPage: true }); const metrics = await page.evaluate(() => ({ orderGroups: document.querySelectorAll(\".admin-order-group\").length, brandTableHeaders: [...document.querySelectorAll(\".material-ledger .admin-ledger-head div\")].filter((node) => node.textContent.includes(\"Марка\")).length, rawMaterialBrandInputs: document.querySelectorAll(\"input[name=raw_material_brand_grade]\").length, visibleBrandText: document.body.textContent.includes(\"Марка / клас\"), deleteCheckboxes: document.querySelectorAll(\"input[name=delete_roll_id], input[name=delete_segment_id]\").length, xButtons: document.querySelectorAll(\".admin-row-delete-button\").length, rollRows: document.querySelectorAll(\".admin-roll-ledger-row\").length, timingRows: document.querySelectorAll(\".admin-timing-ledger-row\").length })); console.log(JSON.stringify(metrics, null, 2)); await browser.close(); })();"'
```

Expected metrics:

```json
{
  "orderGroups": 5,
  "brandTableHeaders": 0,
  "standaloneBrandFields": 0,
  "rawMaterialBrandInputs": 0,
  "visibleBrandText": false,
  "deleteCheckboxes": 0,
  "xButtons": 61,
  "rollRows": 60,
  "timingRows": 2
}
```

`xButtons` should equal roll rows plus existing timing segment rows. If the exact timing row count differs because the fixture changes, verify that every persisted roll/timing row has one X button and the new timing row does not have a delete X.

- [x] **Step 5: Stop the temporary server**

Send Ctrl-C to the Uvicorn process.

Expected:

```text
Application shutdown complete.
```

- [x] **Step 6: Inspect screenshots manually**

Open or view:

```text
artifacts/ui-checks/admin-card-detail-cleanup/desktop-detail.png
artifacts/ui-checks/admin-card-detail-cleanup/mobile-detail.png
```

Confirm:

- The order pane is grouped and still compact.
- The materials table no longer has a mostly-empty brand/class column.
- No `Марка / клас` field is visible in the admin materials UI.
- Roll and timing rows use red X buttons, not checkboxes.
- Text does not overlap in desktop or mobile screenshots.

---

### Task 7: Update Milestone Tracker And Run Final Verification

**Files:**
- Modify: `IMPLEMENTATION_PLAN.md`
- Verify: all changed files

- [x] **Step 1: Update `IMPLEMENTATION_PLAN.md`**

Add a short completion note under the current admin detail redesign/milestone area:

```markdown
8. Admin completed-card detail cleanup - done
   - Order details were grouped into order, client, product, operations, and notes subsections while keeping one save action.
   - The materials ledger now keeps row-level material data in the table and no longer exposes the legacy `Марка / клас` field in the admin UI.
   - Roll and timing deletion now use explicit red X row actions with confirmation prompts instead of checkbox-plus-save deletion.
   - Admin detail POST actions return to section anchors for order, materials, rolls, and timing.
   - Verification passed with focused render/backend tests, the full Python suite, `git diff --check`, and Playwright screenshots against a temporary database.
```

Adjust the numbering if `IMPLEMENTATION_PLAN.md` already has a newer item.

- [x] **Step 2: Run focused cleanup tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_admin_card_detail_redesign.py -q
```

Expected:

```text
passed
```

- [x] **Step 3: Run affected admin/production suites**

Run:

```bash
source .venv/bin/activate && python -m pytest \
  tests/test_admin_card_review.py \
  tests/test_admin_production_corrections.py \
  tests/test_finish_cancel_history.py \
  tests/test_roll_entry.py \
  tests/test_production_timing.py \
  -q
```

Expected:

```text
passed
```

- [x] **Step 4: Run the full Python suite**

Run:

```bash
source .venv/bin/activate && python -m pytest
```

Expected:

```text
passed
```

Record the exact pass count in the final response.

- [x] **Step 5: Run whitespace diff check**

Run:

```bash
git diff --check
```

Expected:

```text
```

No output.

- [x] **Step 6: Review the final diff**

Run:

```bash
git diff --stat
git diff -- app/templates/admin_card_detail.html
git diff -- app/static/css/app.css
git diff -- app/main.py
git diff -- tests/test_admin_card_detail_redesign.py
git diff -- IMPLEMENTATION_PLAN.md
```

Confirm:

- No real runtime database files are changed.
- No unrelated refactors were introduced.
- No staging happened.
- No commit happened.

- [x] **Step 7: Final status check**

Run:

```bash
git status --short
```

Expected:

```text
 M IMPLEMENTATION_PLAN.md
 M app/db.py
 M app/main.py
 M app/static/css/app.css
 M app/templates/admin_card_detail.html
?? tests/test_admin_card_detail_redesign.py
```

The exact status may include user-owned unrelated files that existed before this plan execution. Do not revert them. Mention them in the final response if present.

---

## Implementation Notes

- Do not remove the existing backend single-row delete endpoints:
  - `/admin/cards/{card_id}/rolls/{roll_id}/delete`
  - `/admin/cards/{card_id}/timing-segments/{segment_id}/delete`
- Do not remove bulk ledger update helpers.
- Do not introduce modal libraries or a frontend framework.
- The `confirm(...)` prompts are acceptable for this pilot because the app is server-rendered and the user explicitly wants a simple confirmation before row deletion.
- Keep optimistic conflict checks by preserving `loaded_version` hidden inputs in all delete forms.
- The caveat is accepted: if a user edits row values and then clicks a row X before saving, the row delete action will not save unsaved edits in the ledger. That is acceptable for this prototype.

---

## Self-Review Checklist

Before handing off:

- [x] The order details pane has logical visual subsections.
- [x] The materials table has no `Марка / клас` column.
- [x] There is no `raw_material_brand_grade` input in the admin materials UI.
- [x] Roll rows have red X delete buttons, not delete checkboxes.
- [x] Timing segment rows have red X delete buttons, not delete checkboxes.
- [x] There is no visible `Да` beside deletion controls.
- [x] Successful section saves redirect to the relevant page anchor.
- [x] Existing backend invariants and stale-version checks still pass.
- [x] Playwright screenshots are saved under `artifacts/ui-checks/admin-card-detail-cleanup/`.
- [x] No real runtime database was mutated.
- [x] Nothing was staged or committed unless the user explicitly asked.

---

## Execution Handoff

Plan complete. Recommended execution mode is **Subagent-Driven** because the work has independent template/CSS/test/route checks and benefits from review checkpoints after each task.

Execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using `superpowers:executing-plans`, with checkpoints after each task.
