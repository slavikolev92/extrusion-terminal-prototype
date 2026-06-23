# Terminal Recipe Layout Compacting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compact the live `/terminal` details/recipe layout so the full recipe table fits on normal workstation monitors without adding any new scrollbars.

**Architecture:** This is a focused server-rendered template/CSS change in `app/templates/terminal.html`. The backend data flow, form actions, version checks, recipe autosave hooks, and roll-entry behavior stay unchanged. Verification combines a focused render test with a temporary-database Playwright measurement pass against the live FastAPI app.

**Tech Stack:** FastAPI, Jinja2 templates, inline CSS in `app/templates/terminal.html`, pytest, Playwright via local Node.

---

## Scope And Constraints

- Do not add scrollbars to the details pane, recipe table, workspace, main area, body, or app shell.
- Do not remove the main pane headings `Детайли` and `Ролки`.
- Remove the visible `Рецепта` section heading only.
- Keep the recipe table header row with columns `Вид суровина`, `Заложена суровина`, `Използван материал`, and `Партида`.
- Keep all existing recipe inputs, names, values, `loaded_version`, autosave attributes, and form action.
- Keep the right roll pane behavior and data bindings unchanged.
- Preserve existing roll-list overflow behavior; this plan must not introduce any new scrollbar behavior.
- The Playwright no-scrollbar check intentionally excludes `.roll-list`, because the roll list already has its own overflow behavior and this task must not change it.
- Do not stage or commit unless the user explicitly asks.

## Files

- Modify: `app/templates/terminal.html`
  - Remove the `Рецепта` heading markup.
  - Compact details/recipe spacing.
  - Slightly reduce recipe row heights.
  - Vertically center recipe header and row cell contents.
  - Align the details and rolls pane content rhythm.
- Modify: `tests/test_terminal_v8_render.py`
  - Add a focused render assertion that the visible recipe heading is gone while recipe form/table fields remain.
- Create: none.

## Acceptance Criteria

- `/terminal` still renders the selected card with `Детайли` and `Ролки` headings.
- The visible standalone `Рецепта` heading no longer renders.
- The recipe table still renders all recipe rows and column headings.
- At `1366x768`, the recipe table content fits without clipped rows for a seven-row recipe card shaped like `Screen2.JPG`.
- At `1366x720`, the layout is tighter but must not introduce a new scrollbar on `.details-body`, `.recipe-section`, `.recipe-table`, `.workspace`, `.main`, `.app`, `body`, or `html`.
- Existing material autosave attributes and form field names remain unchanged.

---

### Task 1: Add Focused Render Coverage

**Files:**
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Add a render test for the compact recipe hierarchy**

Add this test near the other `terminal_v8` render tests that inspect selected-card detail content:

```python
def test_terminal_v8_recipe_table_is_part_of_details_without_extra_recipe_heading(connection):
    card_id = release_ready_card("26240", machine_id=1, sequence=1)

    html = render_terminal(card_id)

    assert '<span>Детайли</span>' in html
    assert '<span>Ролки</span>' in html
    assert 'class="recipe-table"' in html
    assert "Вид суровина" in html
    assert "Заложена суровина" in html
    assert "Използван материал" in html
    assert "Партида" in html
    assert 'data-recipe-autosave="true"' in html
    assert f'action="/terminal/cards/{card_id}/materials"' in html
    assert 'name="actual_material__raw_material_a"' in html
    assert 'name="batch_lot__raw_material_a"' in html
    assert 'class="recipe-title"' not in html
    assert ">Рецепта<" not in html
```

- [ ] **Step 2: Run the focused test and verify it fails before the template change**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_v8_recipe_table_is_part_of_details_without_extra_recipe_heading -q
```

Expected result before implementation:

```text
FAILED tests/test_terminal_v8_render.py::test_terminal_v8_recipe_table_is_part_of_details_without_extra_recipe_heading
```

The failure should be caused by the existing `class="recipe-title"` markup and visible `Рецепта` heading.

---

### Task 2: Compact The Details And Recipe Layout

**Files:**
- Modify: `app/templates/terminal.html`

- [ ] **Step 1: Remove the visible recipe heading markup**

Find:

```html
<div class="recipe-section">
  <div class="recipe-title">Рецепта</div>
  <form class="recipe-table" action="/terminal/cards/{{ selected_card.id }}/materials" method="post" data-recipe-autosave="true">
```

Replace it with:

```html
<div class="recipe-section">
  <form class="recipe-table" action="/terminal/cards/{{ selected_card.id }}/materials" method="post" data-recipe-autosave="true">
```

- [ ] **Step 2: Replace the core details/recipe CSS**

In `app/templates/terminal.html`, replace the current `.panel-head`, `.details-body`, `.order-section`, `.recipe-section`, `.recipe-title`, `.recipe-head`, `.recipe-row`, `.recipe-head div, .recipe-row > div`, `.component`, `.material-planned`, and `.recipe-row input` rules with this compact version:

```css
.panel-head {
  min-height: 0;
  padding: 0 0 12px;
  border-bottom: 0;
  background: transparent;
  color: #1f2933;
  font-size: 21px;
  font-weight: 800;
  line-height: 1.15;
}

.details-body {
  display: grid;
  grid-template-rows: auto auto;
  align-content: start;
  gap: 10px;
}

.order-section {
  min-width: 0;
  border: 1px solid #d9dee5;
  border-radius: 9px;
  background: #fff;
  padding: 14px 18px;
  display: grid;
  gap: 12px;
  align-content: start;
}

.recipe-section {
  min-height: 0;
  display: grid;
  grid-template-rows: auto auto;
  gap: 6px;
  margin-top: 0;
}

.recipe-table {
  min-height: 0;
  border: 1px solid var(--line);
  border-radius: 9px;
  overflow: hidden;
  background: #fff;
}

.recipe-head,
.recipe-row {
  display: grid;
  grid-template-columns: 178px minmax(190px, 1fr) minmax(150px, .7fr) minmax(120px, .5fr);
  align-items: stretch;
}

.recipe-head {
  min-height: 32px;
  background: #f1f4f7;
  color: #657383;
  font-size: 14px;
  font-weight: 700;
}

.recipe-row {
  min-height: 48px;
  border-top: 1px solid #dde3e9;
}

.recipe-head div,
.recipe-row > div {
  min-width: 0;
  border-right: 1px solid #dde3e9;
  padding: 5px 9px;
  display: flex;
  align-items: center;
}

.component {
  background: #f8fafc;
  color: #1f2933;
  font-size: 17px;
  font-weight: 800;
  line-height: 1.18;
  overflow-wrap: anywhere;
  white-space: normal;
}

.material-planned {
  min-height: 0;
  border: 1px solid transparent;
  border-radius: 7px;
  background: #fff;
  color: #26323f;
  padding: 0;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.18;
  overflow-wrap: anywhere;
}

.recipe-row input {
  min-height: 34px;
  padding: 5px 8px;
  font-size: 17px;
  font-weight: 700;
}
```

Keep these existing rules unchanged after the replacement:

```css
.recipe-head div:last-child,
.recipe-row > div:last-child {
  border-right: 0;
}
```

- [ ] **Step 3: Remove the obsolete `.recipe-title` rule**

Delete this full rule because the heading no longer exists:

```css
.recipe-title {
  color: #1f2933;
  font-size: 21px;
  font-weight: 800;
  line-height: 1.15;
}
```

- [ ] **Step 4: Tighten the height media overrides without changing behavior**

In the `@media (max-height: 980px)` block, replace:

```css
.panel-head {
  padding-bottom: 10px;
}

.details-body {
  gap: 14px;
}

.order-section {
  padding: 14px 18px;
  gap: 12px;
}

.recipe-section {
  gap: 8px;
}

.recipe-head {
  min-height: 32px;
}

.recipe-row {
  min-height: 46px;
}

.recipe-row input {
  min-height: 32px;
}

.material-planned {
  min-height: 32px;
  padding: 6px 7px;
}
```

with:

```css
.panel-head {
  padding-bottom: 10px;
}

.details-body {
  gap: 8px;
}

.order-section {
  padding: 12px 16px;
  gap: 10px;
}

.recipe-section {
  gap: 6px;
}

.recipe-head {
  min-height: 30px;
}

.recipe-row {
  min-height: 46px;
}

.recipe-row input {
  min-height: 32px;
}
```

In the `@media (max-height: 760px)` block, keep the existing `.recipe-row` and `.recipe-row input` minimums unless the Playwright measurement in Task 4 shows clipping. Do not add `overflow: auto`, `overflow-y: auto`, `overflow: scroll`, or `overflow-y: scroll`.

---

### Task 3: Verify Render Tests

**Files:**
- Test: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Run the new focused render test**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_v8_recipe_table_is_part_of_details_without_extra_recipe_heading -q
```

Expected result:

```text
1 passed
```

- [ ] **Step 2: Run the existing terminal V8 render suite**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py -q
```

Expected result:

```text
passed
```

The exact number of tests may vary if other work has added tests. Any failure in material forms, loaded-version fields, queue navigation, completed-card behavior, or no-cancel/no-restore assertions must be fixed before continuing.

---

### Task 4: Browser Measurement Against A Temporary Database

**Files:**
- No repo file changes required.
- Artifacts: `artifacts/ui-checks/terminal-recipe-layout-compact/`
- Temporary database: `.test-runtime/terminal-recipe-layout-compact/extrusion_terminal.sqlite3`

- [ ] **Step 1: Create the temporary database fixture**

Run:

```bash
mkdir -p .test-runtime/terminal-recipe-layout-compact artifacts/ui-checks/terminal-recipe-layout-compact
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/terminal-recipe-layout-compact/extrusion_terminal.sqlite3 python - <<'PY'
import csv
import io

from app import db
from app.importer import IMPORT_FIELDS, import_cards_from_csv

db.init_db()

def csv_bytes(*rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")

row = {
    "order_number": "25278",
    "customer": "Пелети Пирин PELLITO",
    "product_type": "ТСФ 890/0.082 - Пирин пелет PELLITO / 2026 /",
    "quantity_1": "500",
    "unit_1": "kg",
    "quantity_2": "5",
    "unit_2": "ролки",
    "product_form": "плоско",
    "material": "LDPE",
    "size_thickness": "890/0.082",
    "notes": "Екструдират се ролки по 4500 м. = 310 кг. ; печат на x 1500 м. ; Размера се пуска с 2-3 см. изрезка + ДА СЕ ПОСТАВИ РЕПЕР РАЗПОЛОЖЕН КАТО НА ДРУГИТЕ ПЕЧАТИ",
    "extrusion_flag": "da",
    "extrusion_folding": "single",
    "extrusion_next_operation": "rewind",
    "extrusion_treatment": "corona",
    "raw_material_a": "LDPE тв.- румънско B20/03",
    "raw_material_b": "",
    "raw_material_c": "",
    "linear_pe": "20% без добавки",
    "antistatic": "1%",
    "masterbatch": "",
    "chalk": "",
    "packaging_method": "rolls",
}

result = import_cards_from_csv("terminal-recipe-layout-compact.csv", csv_bytes(row), overwrite_existing=False)
assert result.rows_imported == 1, result

with db.connect() as connection:
    card_id = connection.execute(
        "SELECT id FROM cards WHERE order_number = ?",
        ("25278",),
    ).fetchone()["id"]

release = db.release_card(
    card_id,
    machine_id=1,
    machine_sequence=1,
    loaded_version=db.fetch_admin_card_detail(card_id)["version"],
    max_roll_weight="",
)
assert release.ok, release

start = db.start_production_timing(card_id, db.fetch_terminal_card_detail(card_id)["version"])
assert start.ok, start

tare = db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "5")
assert tare.ok, tare

for gross in ("50", "50", "50"):
    roll = db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], gross)
    assert roll.ok, roll

print(card_id)
PY
```

Expected result:

```text
1
```

- [ ] **Step 2: Start the local app against the temporary database**

Run:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/terminal-recipe-layout-compact/extrusion_terminal.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 18080
```

Expected result:

```text
Uvicorn running on http://127.0.0.1:18080
```

- [ ] **Step 3: Measure layout fit with Playwright**

In a second terminal, run:

```bash
node - <<'JS'
const { chromium } = require("@playwright/test");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const viewports = [
    { width: 2638, height: 1289, name: "screen2-like" },
    { width: 1366, height: 768, name: "kiosk-768" },
    { width: 1366, height: 720, name: "kiosk-720" },
  ];

  const failures = [];

  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport });
    await page.goto("http://127.0.0.1:18080/terminal/cards/1", { waitUntil: "networkidle" });
    await page.screenshot({
      path: `artifacts/ui-checks/terminal-recipe-layout-compact/${viewport.name}.png`,
      fullPage: false,
    });

    const metrics = await page.evaluate(() => {
      const checkedSelectors = [
        "html",
        "body",
        ".app",
        ".main",
        ".workspace",
        ".details-body",
        ".recipe-section",
        ".recipe-table",
      ];
      const boxes = {};
      for (const selector of checkedSelectors) {
        const el = document.querySelector(selector);
        const style = getComputedStyle(el);
        boxes[selector] = {
          clientHeight: el.clientHeight,
          scrollHeight: el.scrollHeight,
          overflowY: style.overflowY,
        };
      }
      const table = document.querySelector(".recipe-table").getBoundingClientRect();
      const rows = Array.from(document.querySelectorAll(".recipe-row")).map((row) => {
        const rect = row.getBoundingClientRect();
        return { top: rect.top, bottom: rect.bottom, height: rect.height };
      });
      return {
        boxes,
        rowCount: rows.length,
        lastRowInsideTable: rows.length > 0 && rows[rows.length - 1].bottom <= table.bottom + 1,
        tableContentFits: document.querySelector(".recipe-table").scrollHeight <= document.querySelector(".recipe-table").clientHeight + 1,
        hasRecipeTitle: Boolean(document.querySelector(".recipe-title")),
      };
    });

    for (const [selector, box] of Object.entries(metrics.boxes)) {
      if (["auto", "scroll"].includes(box.overflowY)) {
        failures.push(`${viewport.name}: ${selector} has overflow-y ${box.overflowY}`);
      }
    }
    if (metrics.hasRecipeTitle) {
      failures.push(`${viewport.name}: recipe title still exists`);
    }
    if (metrics.rowCount !== 7) {
      failures.push(`${viewport.name}: expected 7 recipe rows, saw ${metrics.rowCount}`);
    }
    if (!metrics.lastRowInsideTable) {
      failures.push(`${viewport.name}: last recipe row is clipped by the table`);
    }
    if (!metrics.tableContentFits) {
      failures.push(`${viewport.name}: recipe table content exceeds visible table height`);
    }
    await page.close();
  }

  await browser.close();

  if (failures.length) {
    console.error(failures.join("\n"));
    process.exit(1);
  }
  console.log("terminal recipe layout compact measurement passed");
})();
JS
```

Expected result:

```text
terminal recipe layout compact measurement passed
```

If the measurement fails at `1366x720`, first reduce vertical waste further without adding scrollbars:

```css
@media (max-height: 760px) {
  .order-section {
    padding: 10px 14px;
    gap: 8px;
  }

  .details-body {
    gap: 6px;
  }

  .recipe-row {
    min-height: 44px;
  }
}
```

Do not solve a measurement failure by adding `overflow: auto` or `overflow: scroll`.

- [ ] **Step 4: Stop the temporary server**

Press `Ctrl+C` in the terminal running Uvicorn.

---

### Task 5: Final Verification

**Files:**
- Test: `tests/test_terminal_v8_render.py`
- Check: `app/templates/terminal.html`

- [ ] **Step 1: Run focused terminal tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py tests/test_terminal_sync.py -q
```

Expected result:

```text
passed
```

- [ ] **Step 2: Run the full Python suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected result:

```text
passed
```

- [ ] **Step 3: Check whitespace and patch quality**

Run:

```bash
git diff --check
```

Expected result: no output.

- [ ] **Step 4: Inspect the diff for accidental workflow changes**

Run:

```bash
git diff -- app/templates/terminal.html tests/test_terminal_v8_render.py
```

Confirm the diff only:

- removes the visible `Рецепта` heading;
- compacts vertical spacing;
- centers recipe table cell contents;
- slightly reduces recipe row/input heights;
- adds the focused render test;
- does not change form actions, field names, `loaded_version`, route URLs, backend code, roll controls, timing controls, cancel/restore visibility, or production status behavior.

---

## Self-Review

- Spec coverage: The plan removes the wasteful recipe heading, keeps `Детайли` and `Ролки`, aligns pane rhythm, slightly tightens recipe rows, vertically centers recipe cells, and explicitly forbids new scrollbars.
- Placeholder scan: No `TBD`, `TODO`, or open-ended implementation steps remain.
- Type and selector consistency: Selectors used in tests and Playwright checks match the existing template names: `.details-body`, `.recipe-section`, `.recipe-table`, `.recipe-row`, `.panel-head`, `.workspace`, `.main`, `.app`.
- Repo policy: The plan does not include staging or committing because AGENTS.md requires explicit user approval before stage/commit.
