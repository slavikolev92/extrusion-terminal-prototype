# Terminal Roll Input Focus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically place browser focus in the terminal `Нова ролка, кг` input whenever the selected card is running and no higher-priority correction or reload state is active.

**Architecture:** Keep the behavior in the server-rendered terminal template by rendering a focused data marker only on the running-card new-roll input. A small JavaScript helper runs once after the terminal page loads, skips stale/reload and roll-correction states, and focuses the marked input without changing routes, database rules, validation, admin, or print behavior.

**Tech Stack:** FastAPI, Jinja2 server-rendered HTML, small browser JavaScript, pytest render tests, local Playwright browser verification.

---

## File Structure

- Modify `tests/test_terminal_v8_render.py`: add focused render tests for the new-roll autofocus marker and script guards, using existing helpers (`render_terminal`, `roll_entry_block`, `data_block`, `release_ready_card`, `card_version`, `complete_card`).
- Modify `app/templates/terminal.html`: add the conditional `data-new-roll-autofocus="true"` marker to the existing `gross_weight` input only when `selected_card.status == "running"` and add one small self-contained focus helper in the existing script block.
- Modify `IMPLEMENTATION_PLAN.md`: after implementation and verification, add a concise completed follow-up note under Milestone 12 completed audit follow-ups with the test and Playwright evidence.
- Do not create permanent Playwright fixture scripts for this slice. Browser verification should use a temporary SQLite database under `.test-runtime/terminal-roll-focus/` and one-off local commands.

## Task 1: Add Failing Terminal Render Tests

**Files:**
- Modify: `tests/test_terminal_v8_render.py`

- [x] **Step 1: Add a helper for the new-roll gross input tag**

Add this helper immediately after the existing `roll_entry_block` helper:

```python
def new_roll_input_tag(html: str) -> str:
    match = re.search(
        r'<input[^>]+name="gross_weight"[^>]*>',
        roll_entry_block(html),
        flags=re.S,
    )
    assert match is not None
    return match.group(0)
```

- [x] **Step 2: Add tests for when the marker is rendered**

Add these tests near the existing roll-entry render tests, before `test_terminal_tare_and_correction_forms_use_dirty_autosave_without_new_roll_autosave`:

```python
def test_terminal_new_roll_autofocus_marker_renders_only_for_running_card(connection):
    running_id = release_ready_card("26301", machine_id=1, sequence=1)
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    running_html = render_terminal(running_id)
    running_input = new_roll_input_tag(running_html)
    assert 'data-new-roll-autofocus="true"' in running_input
    assert "disabled" not in running_input

    pending_id = release_ready_card("26302", machine_id=2, sequence=1)
    pending_input = new_roll_input_tag(render_terminal(pending_id))
    assert 'data-new-roll-autofocus="true"' not in pending_input
    assert "disabled" in pending_input

    paused_id = release_ready_card("26303", machine_id=3, sequence=1)
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok
    paused_input = new_roll_input_tag(render_terminal(paused_id))
    assert 'data-new-roll-autofocus="true"' not in paused_input
    assert "disabled" in paused_input

    completed_id = release_ready_card("26304", machine_id=4, sequence=1)
    complete_card(completed_id)
    completed_input = new_roll_input_tag(render_terminal(completed_id))
    assert 'data-new-roll-autofocus="true"' not in completed_input
    assert "disabled" not in completed_input


def test_terminal_new_roll_autofocus_marker_is_absent_without_selected_card(connection):
    html = render_terminal(machine_id=4)

    assert 'data-new-roll-autofocus="true"' not in html
    assert "Няма активна поръчка за Машина 4." in html
```

- [x] **Step 3: Add tests for normal error focus eligibility and guard script text**

Add these tests after the marker tests:

```python
def test_terminal_new_roll_autofocus_validation_error_keeps_marker(connection):
    card_id = release_ready_card("26305", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok

    html = render_terminal(
        card_id,
        roll_result=RuleResult(False, ("new roll failure",)),
        roll_result_target="new_roll",
    )

    new_roll_block = data_block(html, "data-feedback-target", "new_roll")
    assert "new roll failure" in new_roll_block
    assert 'id="terminal-refresh-alert"' not in html
    assert 'data-new-roll-autofocus="true"' in new_roll_input_tag(html)


def test_terminal_new_roll_autofocus_script_guards_reload_and_roll_correction_mode(connection):
    card_id = release_ready_card("26306", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok

    html = render_terminal(card_id)

    assert "focusNewRollInput" in html
    assert "input[data-new-roll-autofocus='true']" in html
    assert 'document.getElementById("terminal-refresh-alert")' in html
    assert "[data-roll-correction-root][data-correction-open='true']" in html
    assert "newRollInput.focus();" in html

    correction_html = render_terminal(
        card_id,
        roll_result=RuleResult(False, ("correction failure",)),
        roll_result_target="roll_corrections",
    )
    assert 'data-correction-open="true"' in correction_html
    assert 'data-new-roll-autofocus="true"' in new_roll_input_tag(correction_html)
```

- [x] **Step 4: Run the focused tests and verify they fail**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_v8_render.py -k "new_roll_autofocus" -q
```

Expected: the new tests fail because `data-new-roll-autofocus`, `focusNewRollInput`, and the guard script do not exist yet. If failures are syntax or fixture errors, fix the test code and rerun until the failures are for the missing feature only.

Task completion review instead of commit:

```bash
git diff -- tests/test_terminal_v8_render.py
git status --short
```

Expected: only `tests/test_terminal_v8_render.py` changed for this task, plus pre-existing untracked files.

## Task 2: Implement The Template Marker And Focus Helper

**Files:**
- Modify: `app/templates/terminal.html`
- Test: `tests/test_terminal_v8_render.py`

- [x] **Step 1: Add the conditional data marker to the existing new-roll input**

Change the existing new-roll `gross_weight` input:

```html
<input type="number" name="gross_weight" min="0" step="0.01" {% if not can_edit_rolls %}disabled{% endif %}>
```

to:

```html
<input
  type="number"
  name="gross_weight"
  min="0"
  step="0.01"
  {% if selected_card.status == "running" %}data-new-roll-autofocus="true"{% endif %}
  {% if not can_edit_rolls %}disabled{% endif %}
>
```

Do not change `can_edit_rolls`; completed cards may still allow correction workflows, but they must not get the autofocus marker.

- [x] **Step 2: Add the small one-shot focus helper**

Add this IIFE in the existing bottom `<script>` block after the finish-confirmation IIFE and before the tare/new-roll-copy IIFE:

```javascript
    (() => {
      const focusNewRollInput = () => {
        const newRollInput = document.querySelector("input[data-new-roll-autofocus='true']");
        if (!newRollInput || newRollInput.disabled) {
          return;
        }
        if (document.getElementById("terminal-refresh-alert")) {
          return;
        }
        if (document.querySelector("[data-roll-correction-root][data-correction-open='true']")) {
          return;
        }
        window.requestAnimationFrame(() => {
          if (newRollInput.disabled) {
            return;
          }
          if (document.getElementById("terminal-refresh-alert")) {
            return;
          }
          if (document.querySelector("[data-roll-correction-root][data-correction-open='true']")) {
            return;
          }
          newRollInput.focus();
        });
      };

      focusNewRollInput();
    })();
```

This intentionally does not call `select()`: the approved behavior is to keep the text cursor in the input, not to select existing text.

- [x] **Step 3: Run the focused render tests and verify they pass**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_v8_render.py -k "new_roll_autofocus" -q
```

Expected: all `new_roll_autofocus` tests pass.

- [x] **Step 4: Run neighboring terminal render tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_v8_render.py -k "roll_entry or roll_correction or dirty_autosave or roll_saved or stale_new_roll" -q
```

Expected: the neighboring roll-entry, correction, dirty-autosave, success-scroll, and stale-new-roll tests pass.

Task completion review instead of commit:

```bash
git diff -- app/templates/terminal.html tests/test_terminal_v8_render.py
git status --short
```

Expected: only `app/templates/terminal.html`, `tests/test_terminal_v8_render.py`, and the plan file are part of this feature's tracked diff; no staging.

## Task 3: Verify In Browser With A Temporary Database

**Files:**
- No permanent code files required.
- Write artifacts under: `artifacts/ui-checks/terminal-roll-focus/`
- Use temporary DB under: `.test-runtime/terminal-roll-focus/extrusion_terminal.sqlite3`

- [x] **Step 1: Create a temp database fixture with a running card**

Run:

```bash
mkdir -p .test-runtime/terminal-roll-focus artifacts/ui-checks/terminal-roll-focus
source .venv/bin/activate && EXTRUSION_DB_PATH=.test-runtime/terminal-roll-focus/extrusion_terminal.sqlite3 python - <<'PY'
import csv
import io
import json
from pathlib import Path

from app import db
from app.importer import IMPORT_FIELDS, import_cards_from_csv

db.init_db()

def csv_bytes(row):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")

row = {
    "order_number": "FOCUS-26301",
    "customer": "Focus Customer",
    "product_type": "ТСФ 890/0.082",
    "quantity_1": "500",
    "unit_1": "kg",
    "product_form": "плоско",
    "material": "LDPE",
    "size_thickness": "890 / 0.082",
    "notes": "Focus verification card.",
    "extrusion_flag": "da",
    "raw_material_a": "LDPE; A | 100%",
    "packaging_method": "rolls",
}
result = import_cards_from_csv("terminal-roll-focus.csv", csv_bytes(row), overwrite_existing=False)
assert result.rows_imported == 1
with db.connect() as connection:
    card_id = int(connection.execute("SELECT id FROM cards WHERE order_number = ?", ("FOCUS-26301",)).fetchone()["id"])
assert db.release_card(card_id, 1, 1, db.fetch_admin_card_detail(card_id)["version"], max_roll_weight="62.5").ok
assert db.start_production_timing(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok
Path("artifacts/ui-checks/terminal-roll-focus/fixture.json").write_text(json.dumps({"card_id": card_id}, indent=2), encoding="utf-8")
print(card_id)
PY
```

Expected: command prints the created `card_id`; the database path is under `.test-runtime/terminal-roll-focus/`, not `data/`.

- [x] **Step 2: Start the live FastAPI app against the temp database**

Run in a long-running shell:

```bash
source .venv/bin/activate && EXTRUSION_DB_PATH=.test-runtime/terminal-roll-focus/extrusion_terminal.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected: Uvicorn starts on `http://127.0.0.1:8000`. If port `8000` is occupied, use `8001` and set `BASE_URL=http://127.0.0.1:8001` in the Playwright command.

- [x] **Step 3: Run a Playwright focus check**

Run:

```bash
BASE_URL=http://127.0.0.1:8000 node - <<'JS'
const { chromium } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const baseURL = process.env.BASE_URL || "http://127.0.0.1:8000";
const fixture = JSON.parse(fs.readFileSync("artifacts/ui-checks/terminal-roll-focus/fixture.json", "utf8"));
const artifactDir = path.join("artifacts", "ui-checks", "terminal-roll-focus");

(async () => {
  fs.mkdirSync(artifactDir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
  try {
    await page.goto(`${baseURL}/terminal/cards/${fixture.card_id}`, { waitUntil: "networkidle" });
    const newRollInput = page.locator(`form[action="/terminal/cards/${fixture.card_id}/rolls"] input[name="gross_weight"]`);
    await newRollInput.waitFor();
    await page.waitForFunction((selector) => document.activeElement === document.querySelector(selector), `form[action="/terminal/cards/${fixture.card_id}/rolls"] input[name="gross_weight"]`);

    await newRollInput.fill("50.00");
    await newRollInput.press("Enter");
    await page.waitForURL(new RegExp(`/terminal/cards/${fixture.card_id}\\\\?notice=roll_saved$`));
    await page.waitForFunction((selector) => document.activeElement === document.querySelector(selector), `form[action="/terminal/cards/${fixture.card_id}/rolls"] input[name="gross_weight"]`);
    await page.locator(".terminal-toast", { hasText: "Ролката е записана." }).waitFor();
    await page.screenshot({ path: path.join(artifactDir, "running-roll-input-focused-after-enter.png"), fullPage: true });

    await page.goto(`${baseURL}/terminal/cards/${fixture.card_id}`, { waitUntil: "networkidle" });
    const staleLoadedVersion = await page.locator(`form[action="/terminal/cards/${fixture.card_id}/rolls"] input[name="loaded_version"]`).inputValue();
    const freshVersion = await page.locator(`form[action="/terminal/cards/${fixture.card_id}/tare"] input[name="loaded_version"]`).inputValue();
    await page.request.post(`${baseURL}/terminal/cards/${fixture.card_id}/tare`, {
      form: {
        loaded_version: freshVersion,
        tare_weight: "1.25",
      },
    });
    await page.locator(`form[action="/terminal/cards/${fixture.card_id}/rolls"] input[name="loaded_version"]`).evaluate((input, value) => {
      input.value = value;
    }, staleLoadedVersion);
    await newRollInput.fill("60.00");
    await newRollInput.press("Enter");
    await page.locator("#terminal-refresh-alert").waitFor();
    const stalePageFocusedNewRoll = await page.evaluate(() => document.activeElement === document.querySelector("input[data-new-roll-autofocus='true']"));
    if (stalePageFocusedNewRoll) {
      throw new Error("new-roll input focused on stale/reload-required result page");
    }
    await page.screenshot({ path: path.join(artifactDir, "stale-new-roll-refresh-alert-no-focus.png"), fullPage: true });
    const staleRollCountText = await page.locator(".roll-row").count();
    if (staleRollCountText !== 1) {
      throw new Error(`Expected stale submit not to add a second roll, found ${staleRollCountText} roll rows`);
    }
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
JS
```

Expected: command exits `0` and writes:

```text
artifacts/ui-checks/terminal-roll-focus/running-roll-input-focused-after-enter.png
artifacts/ui-checks/terminal-roll-focus/stale-new-roll-refresh-alert-no-focus.png
```

- [x] **Step 4: Stop the live FastAPI app**

Stop the Uvicorn process with `Ctrl+C` or terminate the shell session. Do not leave the server running after verification.

## Task 4: Final Verification And Milestone Note

**Files:**
- Modify: `IMPLEMENTATION_PLAN.md`
- Verify: `app/templates/terminal.html`, `tests/test_terminal_v8_render.py`

- [x] **Step 1: Run focused Python tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_v8_render.py -k "new_roll_autofocus or roll_entry or roll_correction or dirty_autosave or roll_saved or stale_new_roll" -q
```

Expected: focused terminal render tests pass.

- [x] **Step 2: Run broader relevant tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_v8_render.py tests/test_roll_entry.py tests/test_terminal_sync.py -q
```

Expected: terminal render, roll entry, and terminal sync tests pass.

- [x] **Step 3: Run diff hygiene check**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [x] **Step 4: Update `IMPLEMENTATION_PLAN.md` only after Steps 1-3 and browser verification pass**

Under `Milestone 12 - Pilot Rehearsal`, in the `Completed audit follow-up before rehearsal:` list, add one concise bullet:

```markdown
- terminal roll input focus follow-up: running-card terminal pages now autofocus `Нова ролка, кг` after machine/card load, successful `Старт`, successful roll entry/Enter submission, and ordinary new-roll validation errors, while stale reload alerts and roll-correction mode suppress the autofocus.
```

Under `Verification completed for this follow-up:`, add concise verification bullets:

```markdown
- terminal roll input focus verification passed: focused render tests covered running-only focus markers, normal new-roll validation errors, stale/reload and roll-correction guards, and preservation of the new-roll form outside dirty autosave.
- live Playwright verification against temporary SQLite database `.test-runtime/terminal-roll-focus/extrusion_terminal.sqlite3` confirmed initial running-card focus, focus return after Enter roll submission, and no autofocus on a stale reload-required roll submission. Screenshots: `artifacts/ui-checks/terminal-roll-focus/running-roll-input-focused-after-enter.png` and `artifacts/ui-checks/terminal-roll-focus/stale-new-roll-refresh-alert-no-focus.png`.
```

- [x] **Step 5: Review the final diff and status without staging or committing**

Run:

```bash
git diff -- app/templates/terminal.html tests/test_terminal_v8_render.py IMPLEMENTATION_PLAN.md docs/superpowers/plans/2026-07-22-terminal-roll-input-focus.md
git status --short
```

Expected: no staged files. The tracked diff is limited to terminal focus behavior, focused tests, this plan file, and the milestone note. Pre-existing unrelated untracked files remain untracked and untouched.

## Self-Review Checklist

- Spec coverage: The plan covers running-only focus, machine/card load via rendered running pages, successful `Старт` via rendered running page after redirect, successful roll save/Enter focus via browser verification, ordinary new-roll validation errors, no selected card, non-running statuses, stale/reload guard, roll-correction guard, no backend/route/database/admin/print changes, tests, temporary DB, and screenshot artifact.
- Placeholder scan: No `TBD`, `TODO`, vague error-handling tasks, or “similar to” task references are left in the plan.
- Type/name consistency: The selected marker name is consistently `data-new-roll-autofocus="true"`, the helper name is consistently `focusNewRollInput`, and test helper names match the code snippets.
