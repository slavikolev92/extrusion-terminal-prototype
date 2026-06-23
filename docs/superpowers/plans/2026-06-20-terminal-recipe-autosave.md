# Terminal Recipe Autosave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent terminal recipe-field data from silently disappearing when an operator types visible recipe values and then clicks away, changes machine, triggers an action, or refreshes.

**Architecture:** Keep the existing server-rendered recipe form and existing `/terminal/cards/{card_id}/materials` POST route. Add small client-side dirty tracking for the recipe form so changed recipe data submits once when the operator presses Enter or attempts to leave the recipe area, and add a browser `beforeunload` fail-safe for true page refresh/close while dirty. Do not add AJAX autosave, per-keystroke saving, sessions, localStorage, new backend routes, or new database structures.

**Tech Stack:** FastAPI, Jinja2 server-rendered template, direct SQLite via existing `app/db.py`, pytest, repo-local Playwright/Node for UI verification.

---

## Repository Rules For Execution

- Work in `/home/sk/projects/extrusion-terminal`.
- Follow `AGENTS.md`.
- Use the repo-local Python virtualenv: `source .venv/bin/activate`.
- Do not mutate `data/extrusion_terminal.sqlite3` in automated tests or UI checks.
- Use temporary SQLite paths under `.test-runtime/`.
- Save UI screenshots under `artifacts/ui-checks/`.
- Do not stage or commit unless the user explicitly asks. This repo rule overrides generic Superpowers examples that mention committing each task.
- Do not implement issue 1 or issue 3 from `TERMINAL_ISSUES_1_AND_3_TEMP_HANDOFF.md` in this plan.

## Behavioral Requirement

If an operator types visible data into a recipe field, that data must not silently disappear.

Required behavior:

- Pressing Enter in any recipe actual-material or batch field saves the recipe form.
- Clicking from one recipe field into another recipe field does not save yet.
- Clicking outside the recipe form while any recipe field is dirty saves the recipe form once.
- Clicking a machine card, queue item, history item, or action button while recipe data is dirty must not navigate or run that external action on the first click. The first click saves the recipe. After the save/reload, the operator may click again to navigate or act.
- Browser refresh/close while recipe data is dirty should trigger the browser's native unsaved-changes warning as a last-resort fail-safe.
- Existing backend loaded-version conflict protection remains authoritative. If the card changed before the recipe save, the existing stale warning behavior should still appear.

Not required:

- No per-keystroke save.
- No background fetch/AJAX save.
- No custom modal asking whether to save.
- No local draft storage.
- No complex merge tool.

## File Structure

Modify:

- `app/templates/terminal.html`
  - Add an explicit marker to the recipe form.
  - Add recipe-form dirty tracking and exit-save JavaScript near the existing terminal scripts.

- `tests/test_terminal_v8_render.py`
  - Add static render tests that verify recipe autosave markup and JavaScript hooks are present.
  - Keep these tests narrow; the real browser event behavior is verified by the Playwright manual check in Task 3.

No backend file changes are expected for issue 2. The route and database persistence already exist:

- `app/main.py`
  - `save_terminal_materials()`
  - `recipe_actual_entries_from_form()`

- `app/db.py`
  - `update_terminal_recipe_actual_entries()`
  - `fetch_terminal_card_detail()`

## Task 1: Add Failing Render Tests For Recipe Autosave Contract

**Files:**
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Add the failing tests**

Append these tests near the existing recipe render test in `tests/test_terminal_v8_render.py`, after the test that verifies recipe input names/values.

```python
def test_terminal_v8_recipe_form_marks_exit_autosave_contract(connection):
    card_id = release_ready_card("26143", machine_id=1, sequence=1)

    html = render_terminal(card_id)

    recipe_form = form_block(
        html,
        f"/terminal/cards/{card_id}/materials",
    )
    assert 'data-recipe-autosave="true"' in recipe_form
    assert 'name="actual_material__raw_material_a"' in recipe_form
    assert 'name="batch_lot__raw_material_a"' in recipe_form
    assert '<button type="submit" hidden>Запази материал</button>' in recipe_form


def test_terminal_v8_recipe_autosave_script_tracks_dirty_exit_and_beforeunload(
    connection,
):
    card_id = release_ready_card("26144", machine_id=1, sequence=1)

    html = render_terminal(card_id)

    assert 'form[data-recipe-autosave="true"]' in html
    assert "const isRecipeDirty" in html
    assert "submitRecipeIfDirty" in html
    assert 'event.key === "Enter"' in html
    assert "recipeForm.contains(nextTarget)" in html
    assert 'document.addEventListener("click"' in html
    assert "event.stopPropagation()" in html
    assert 'window.addEventListener("beforeunload"' in html
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_v8_recipe_form_marks_exit_autosave_contract tests/test_terminal_v8_render.py::test_terminal_v8_recipe_autosave_script_tracks_dirty_exit_and_beforeunload -q
```

Expected result:

- Both tests fail.
- The first failure should mention missing `data-recipe-autosave="true"`.
- The second failure should mention one of the missing JavaScript markers.

Do not change implementation before seeing the expected failure.

## Task 2: Implement Minimal Recipe Exit Autosave

**Files:**
- Modify: `app/templates/terminal.html`

- [ ] **Step 1: Mark the recipe form**

In `app/templates/terminal.html`, find the recipe form:

```html
<form class="recipe-table" action="/terminal/cards/{{ selected_card.id }}/materials" method="post">
```

Replace it with:

```html
<form class="recipe-table" action="/terminal/cards/{{ selected_card.id }}/materials" method="post" data-recipe-autosave="true">
```

- [ ] **Step 2: Add recipe autosave JavaScript**

In `app/templates/terminal.html`, add a new script IIFE after the existing toast IIFE and before the roll-list scroll IIFE. The surrounding area currently starts like this:

```html
  <script>
    (() => {
      const toast = document.querySelector(".terminal-toast");
      const closeButton = toast?.querySelector(".terminal-toast-close");
      const closeToast = () => {
        if (toast) {
          toast.hidden = true;
        }
      };
      closeButton?.addEventListener("click", closeToast);
      if (toast) {
        window.setTimeout(closeToast, 3000);
      }
    })();

    (() => {
      const rollList = document.querySelector(".roll-list[data-scroll-bottom='true']");
```

Insert this complete block between those two existing IIFEs:

```html
    (() => {
      const recipeForm = document.querySelector('form[data-recipe-autosave="true"]');
      if (!recipeForm) {
        return;
      }

      const recipeInputs = Array.from(
        recipeForm.querySelectorAll("input:not([type='hidden']):not([disabled])"),
      );
      if (recipeInputs.length === 0) {
        return;
      }

      const initialValues = new Map(
        recipeInputs.map((input) => [input.name, input.value]),
      );
      let recipeSubmitting = false;

      const isRecipeDirty = () => recipeInputs.some(
        (input) => input.value !== initialValues.get(input.name),
      );

      const rememberRecipeValues = () => {
        recipeInputs.forEach((input) => {
          initialValues.set(input.name, input.value);
        });
      };

      const submitRecipeIfDirty = () => {
        if (recipeSubmitting || !isRecipeDirty()) {
          return false;
        }
        recipeSubmitting = true;
        recipeForm.requestSubmit();
        return true;
      };

      recipeForm.addEventListener("submit", () => {
        recipeSubmitting = true;
        rememberRecipeValues();
      });

      recipeInputs.forEach((input) => {
        input.addEventListener("keydown", (event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            submitRecipeIfDirty();
          }
        });

        input.addEventListener("blur", (event) => {
          const nextTarget = event.relatedTarget;
          if (nextTarget && recipeForm.contains(nextTarget)) {
            return;
          }
          submitRecipeIfDirty();
        });
      });

      document.addEventListener("click", (event) => {
        if (recipeSubmitting || !isRecipeDirty()) {
          return;
        }
        const target = event.target;
        if (target instanceof Node && recipeForm.contains(target)) {
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        submitRecipeIfDirty();
      }, true);

      window.addEventListener("beforeunload", (event) => {
        if (recipeSubmitting || !isRecipeDirty()) {
          return;
        }
        event.preventDefault();
        event.returnValue = "";
      });
    })();
```

Implementation notes:

- This intentionally uses normal form submit/POST, not fetch.
- `blur` saves when focus leaves the recipe form.
- Moving between recipe inputs is allowed without saving because `event.relatedTarget` remains inside `recipeForm`.
- The capture-phase document click is a belt-and-suspenders guard for external clicks. It prevents the first external click from navigating or firing an action when dirty, then submits the recipe form.
- `beforeunload` is only a fail-safe for refresh/close cases.
- The hidden submit button already exists and should remain.

- [ ] **Step 3: Run the focused tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_v8_recipe_form_marks_exit_autosave_contract tests/test_terminal_v8_render.py::test_terminal_v8_recipe_autosave_script_tracks_dirty_exit_and_beforeunload -q
```

Expected result:

- Both tests pass.

- [ ] **Step 4: Run existing terminal render and recipe persistence tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py tests/test_terminal_detail.py -q
```

Expected result:

- All tests pass.

If an existing test fails because the expected form string changed, update only the assertion to allow the new `data-recipe-autosave="true"` attribute. Do not change application behavior to satisfy an outdated string assertion.

## Task 3: Verify Browser Click-Away Behavior With Temporary Database

**Files:**
- No source files should be modified.
- Create verification artifacts only under:
  - `.test-runtime/terminal-recipe-autosave/`
  - `artifacts/ui-checks/terminal-recipe-autosave/`

- [ ] **Step 1: Create temporary runtime directories**

Run:

```bash
mkdir -p .test-runtime/terminal-recipe-autosave artifacts/ui-checks/terminal-recipe-autosave
```

Expected result:

- Both directories exist.

- [ ] **Step 2: Seed a temporary SQLite database**

Run:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH="$PWD/.test-runtime/terminal-recipe-autosave/extrusion_terminal.sqlite3" python - <<'PY'
import csv
import io
import json
from pathlib import Path

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

def extrusion_row(order_number, customer, **overrides):
    row = {
        "order_number": order_number,
        "customer": customer,
        "product_type": "ТСФ 890/0.082",
        "quantity_1": "500",
        "unit_1": "kg",
        "quantity_2": "5",
        "unit_2": "ролки",
        "product_form": "плоско",
        "material": "LDPE",
        "size_thickness": "890 / 0.082",
        "notes": "Recipe autosave verification.",
        "extrusion_flag": "da",
        "raw_material_a": "LDPE A",
        "raw_material_b": "LLDPE B",
        "raw_material_c": "HDPE C",
        "linear_pe": "Linear PE",
        "antistatic": "Antistatic",
        "masterbatch": "Masterbatch",
        "chalk": "Chalk",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row

result = import_cards_from_csv(
    "terminal-recipe-autosave.csv",
    csv_bytes(
        extrusion_row("AUTO-RECIPE-1", "Autosave Customer 1"),
        extrusion_row("AUTO-RECIPE-2", "Autosave Customer 2"),
    ),
    overwrite_existing=False,
)
assert result.rows_imported == 2, result

with db.connect() as connection:
    rows = connection.execute(
        "SELECT id, order_number, version FROM cards ORDER BY order_number"
    ).fetchall()

card_1 = int(rows[0]["id"])
card_2 = int(rows[1]["id"])

assert db.release_card(
    card_1,
    machine_id=1,
    machine_sequence=1,
    loaded_version=int(rows[0]["version"]),
    max_roll_weight="60.0",
).ok
assert db.release_card(
    card_2,
    machine_id=2,
    machine_sequence=1,
    loaded_version=int(rows[1]["version"]),
    max_roll_weight="60.0",
).ok

Path(".test-runtime/terminal-recipe-autosave/cards.json").write_text(
    json.dumps({"card_1": card_1, "card_2": card_2}),
    encoding="utf-8",
)
print(json.dumps({"card_1": card_1, "card_2": card_2}))
PY
```

Expected result:

- Command exits `0`.
- It prints JSON containing `card_1` and `card_2`.
- It creates `.test-runtime/terminal-recipe-autosave/cards.json`.

- [ ] **Step 3: Start the FastAPI server on the temporary database**

Run:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH="$PWD/.test-runtime/terminal-recipe-autosave/extrusion_terminal.sqlite3" python -m uvicorn app.main:app --host 127.0.0.1 --port 8771
```

Expected result:

- Server starts and listens on `http://127.0.0.1:8771`.
- Keep this process running for the next step.

- [ ] **Step 4: Run Playwright browser verification from a second terminal/session**

Run:

```bash
node - <<'JS'
const fs = require('fs');
const { chromium } = require('playwright');

const cards = JSON.parse(
  fs.readFileSync('.test-runtime/terminal-recipe-autosave/cards.json', 'utf8'),
);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 950 } });
  const baseUrl = 'http://127.0.0.1:8771';
  const firstCardUrl = `${baseUrl}/terminal/cards/${cards.card_1}`;

  await page.goto(firstCardUrl, { waitUntil: 'networkidle' });

  const materialInput = page.locator('input[name="actual_material__raw_material_a"]');
  const batchInput = page.locator('input[name="batch_lot__raw_material_a"]');

  await materialInput.fill('Autosaved Material A');
  await batchInput.fill('Batch-Autosave-001');

  await page.locator('.machine-tab').filter({ hasText: 'Машина 2' }).click();
  await page.waitForLoadState('networkidle');

  if (!page.url().includes(`/terminal/cards/${cards.card_1}`)) {
    throw new Error(`First external click should save before navigating; current URL: ${page.url()}`);
  }

  const materialAfterSave = await page.locator('input[name="actual_material__raw_material_a"]').inputValue();
  const batchAfterSave = await page.locator('input[name="batch_lot__raw_material_a"]').inputValue();
  if (materialAfterSave !== 'Autosaved Material A') {
    throw new Error(`Material value was not persisted after click-away save: ${materialAfterSave}`);
  }
  if (batchAfterSave !== 'Batch-Autosave-001') {
    throw new Error(`Batch value was not persisted after click-away save: ${batchAfterSave}`);
  }

  await page.locator('.machine-tab').filter({ hasText: 'Машина 2' }).click();
  await page.waitForLoadState('networkidle');
  if (!page.url().includes(`/terminal/cards/${cards.card_2}`)) {
    throw new Error(`Second click should navigate to machine 2 card; current URL: ${page.url()}`);
  }

  await page.goto(firstCardUrl, { waitUntil: 'networkidle' });
  await page.screenshot({
    path: 'artifacts/ui-checks/terminal-recipe-autosave/recipe-autosave-persisted.png',
    fullPage: true,
  });

  await browser.close();
})().catch(async (error) => {
  console.error(error);
  process.exit(1);
});
JS
```

Expected result:

- Command exits `0`.
- First click on Machine 2 saves the dirty recipe form and remains on card 1 after the POST/redirect.
- The material and batch values are still visible after reload.
- Second click on Machine 2 navigates to card 2.
- Screenshot exists at `artifacts/ui-checks/terminal-recipe-autosave/recipe-autosave-persisted.png`.

- [ ] **Step 5: Stop the temporary server**

Stop the `uvicorn` process from Step 3 with `Ctrl+C`.

Expected result:

- No `uvicorn` process remains running for port `8771`.

## Task 4: Final Verification And Review

**Files:**
- No new source files expected beyond `app/templates/terminal.html` and `tests/test_terminal_v8_render.py`.
- Verification artifacts remain untracked under `.test-runtime/` and `artifacts/ui-checks/`.

- [ ] **Step 1: Run focused automated tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py tests/test_terminal_detail.py tests/test_terminal_sync.py -q
```

Expected result:

- All tests pass.

- [ ] **Step 2: Run the full Python test suite if focused tests pass**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected result:

- All tests pass.

- [ ] **Step 3: Run diff whitespace check**

Run:

```bash
git diff --check
```

Expected result:

- No whitespace errors.

- [ ] **Step 4: Review the changed code**

Run:

```bash
git diff -- app/templates/terminal.html tests/test_terminal_v8_render.py
```

Review checklist:

- The recipe form has only one new marker attribute: `data-recipe-autosave="true"`.
- The JavaScript uses normal form submission, not `fetch`.
- The JavaScript does not save on every keystroke.
- Moving between recipe inputs does not trigger submit.
- External dirty clicks are prevented and converted into one recipe submit.
- `beforeunload` only warns when the recipe form is dirty and not already submitting.
- Existing Core Weight autosubmit behavior remains unchanged.
- Existing terminal snapshot polling remains unchanged.
- No issue 1 or issue 3 changes were made.

- [ ] **Step 5: Confirm artifacts**

Run:

```bash
ls -l artifacts/ui-checks/terminal-recipe-autosave/recipe-autosave-persisted.png
```

Expected result:

- The screenshot file exists and has nonzero size.

## Self-Review Notes

Spec coverage:

- Prevent silent recipe data loss: Task 2 implements dirty tracking, exit submit, and external click blocking; Task 3 verifies the critical machine-card click-away case.
- Keep implementation simple: plan uses existing form POST and no AJAX, no new backend route, no local storage, no modal, no database change.
- Preserve existing conflict behavior: plan does not change backend version checks.
- Playwright verification: Task 3 uses a temporary DB and writes screenshot artifacts under `artifacts/ui-checks/`.

Scope exclusions:

- Issue 1 and issue 3 are deferred and documented in `TERMINAL_ISSUES_1_AND_3_TEMP_HANDOFF.md`.
- No commits or staging are part of this plan unless the user explicitly asks later.
