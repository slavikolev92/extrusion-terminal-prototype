# Audit Leftover Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining low-risk audit leftovers: clarify two operator-facing messages, verify terminal tare stale-write behavior through the terminal route and live browser flow, and record the admin sticky-summary monitor decision.

**Architecture:** Keep the existing server-rendered FastAPI/Jinja workflow and direct SQLite/version-check model. Make only small copy/validation changes for print readiness and admin import, add focused regression tests around those behaviors, and treat the tare and sticky-summary items as verification-first work.

**Tech Stack:** FastAPI, Jinja2 templates, direct `sqlite3`, pytest, repo-local Playwright via `@playwright/test`, temporary SQLite databases under `.test-runtime/`.

---

## Repository Rules For Execution

- Work in `/home/sk/projects/extrusion-terminal`.
- Follow `AGENTS.md` and `README.md`.
- Use the repo-local virtualenv: `source .venv/bin/activate`.
- Do not mutate `data/extrusion_terminal.sqlite3` during tests or UI checks.
- Use temporary SQLite paths under `.test-runtime/`.
- Save browser screenshots under `artifacts/ui-checks/`.
- Do not stage or commit unless the user explicitly asks. This repo rule overrides generic Superpowers examples that mention committing each task.
- Existing untracked plan files may be present under `docs/superpowers/plans/`; do not delete or stage them unless the user asks.

## File Structure

- Modify: `app/printing.py`
  - Responsibility: print eligibility and print-readiness messages.
  - Change: avoid showing the critical-weight numeric-validity message when the card is merely incomplete, while preserving the message for genuinely invalid stored numeric values.

- Modify: `tests/test_print_output.py`
  - Responsibility: print readiness and print route regression coverage.
  - Change: add a regression test for incomplete print data not producing the scary numeric-validity message.

- Modify: `app/templates/admin_import.html`
  - Responsibility: shift-manager CSV import form.
  - Change: clarify overwrite copy so it says overwrite updates imported/front-card/source fields and preserves production/workstation data.

- Modify: `app/static/css/app.css`
  - Responsibility: global/admin styling.
  - Change: only add small helper styling for the import warning text if the template needs a second explanatory line.

- Modify: `tests/test_admin_routes.py`
  - Responsibility: route/render coverage for admin pages.
  - Change: add a render test for the import overwrite warning copy.

- Modify: `tests/test_terminal_v8_render.py`
  - Responsibility: server-rendered terminal route/template behavior.
  - Change: add route-level stale tare submit coverage.

- Modify: `reports/full-workflow-audit-20260618.md`
  - Responsibility: durable audit status.
  - Change: mark the two copy cleanups complete after implementation, remove the tare stale-write gap after the route and live checks pass, and record the sticky-summary monitor decision.

- Create only during verification, then leave under ignored artifacts if useful: `artifacts/ui-checks/tare-stale-two-browser/`
  - Responsibility: live Playwright screenshot and optional one-off script for the tare stale-write browser check.

---

## Task 1: Print-Block Copy Cleanup

**Files:**
- Modify: `tests/test_print_output.py`
- Modify: `app/printing.py`

- [ ] **Step 1: Add the failing print-readiness regression test**

Add this test in `tests/test_print_output.py` after `test_completed_card_with_missing_tare_is_blocked`:

```python
def test_incomplete_print_readiness_does_not_show_numeric_corruption_message(connection):
    card_id = make_completed_printable_card("27060")
    with db.connect() as connection:
        connection.execute(
            "UPDATE cards SET tare_weight = NULL WHERE id = ?",
            (card_id,),
        )
        connection.execute(
            "DELETE FROM roll_entries WHERE card_id = ?",
            (card_id,),
        )
        connection.commit()

    result = build_print_readiness(card_id)

    assert not result.ok
    assert result.data is None
    assert "Шпула е задължителна преди печат." in result.messages
    assert "Поне едно бруто тегло на ролка е задължително преди печат." in result.messages
    assert "Критичните тегла за печат трябва да са валидни числа." not in result.messages
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_print_output.py::test_incomplete_print_readiness_does_not_show_numeric_corruption_message -q
```

Expected before implementation:

```text
FAILED ... assert 'Критичните тегла за печат трябва да са валидни числа.' not in ...
```

- [ ] **Step 3: Implement the minimal print-readiness change**

In `app/printing.py`, inside `validate_print_readiness()`, replace:

```python
    messages.extend(validate_print_weight_values(card, gross_rolls))
```

with:

```python
    if card.get("tare_weight") is not None and gross_rolls:
        messages.extend(validate_print_weight_values(card, gross_rolls))
```

This keeps the numeric-validity check active when tare and roll data exist, but suppresses it when the card is simply missing required print prerequisites already reported by clearer messages.

- [ ] **Step 4: Run focused print tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_print_output.py::test_incomplete_print_readiness_does_not_show_numeric_corruption_message tests/test_print_output.py::test_completed_card_with_invalid_numeric_weight_is_blocked tests/test_print_output.py::test_completed_card_with_negative_net_total_is_blocked tests/test_print_output.py::test_print_route_non_completed_card_returns_blocked_response -q
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Run the full print test module**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_print_output.py -q
```

Expected: all tests in `tests/test_print_output.py` pass.

---

## Task 2: Admin Import Overwrite Warning Copy

**Files:**
- Modify: `tests/test_admin_routes.py`
- Modify: `app/templates/admin_import.html`
- Modify: `app/static/css/app.css`

- [ ] **Step 1: Add the failing admin import render test**

Add this test in `tests/test_admin_routes.py` after `test_admin_redirects_to_import`:

```python
def test_admin_import_explains_overwrite_scope(connection):
    response = asyncio.run(admin_import(make_request("/admin/import", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "Обнови импортните/лицеви полета за съществуващи поръчки със същия номер" in html
    assert "Запазва ролки, шпула, времена и операторски данни." in html
    assert "По-стари CSV редове, които биха заменили админ корекции, се блокират за преглед." in html
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_import_explains_overwrite_scope -q
```

Expected before implementation:

```text
FAILED ... assert 'Обнови импортните/лицеви полета...' in html
```

- [ ] **Step 3: Update the admin import template copy**

In `app/templates/admin_import.html`, replace the current overwrite checkbox block:

```html
      <label class="checkbox">
        <input type="checkbox" name="overwrite_existing" value="true">
        Обнови данните на съществуващи поръчки със същия номер
      </label>
```

with:

```html
      <label class="checkbox">
        <input type="checkbox" name="overwrite_existing" value="true">
        <span>
          Обнови импортните/лицеви полета за съществуващи поръчки със същия номер
          <small>Запазва ролки, шпула, времена и операторски данни. По-стари CSV редове, които биха заменили админ корекции, се блокират за преглед.</small>
        </span>
      </label>
```

- [ ] **Step 4: Add small helper styling for the explanatory line**

In `app/static/css/app.css`, after the existing `.import-form .checkbox` rule, add:

```css
.import-form .checkbox small {
  display: block;
  margin-top: 4px;
  line-height: 1.35;
  font-weight: 650;
}
```

- [ ] **Step 5: Run focused admin route tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_import_explains_overwrite_scope tests/test_admin_routes.py::test_successful_admin_import_redirects_to_batch_result_get tests/test_admin_routes.py::test_admin_import_without_persisted_batch_still_renders_inline -q
```

Expected:

```text
3 passed
```

---

## Task 3: Terminal Tare Stale-Write Route And Live Browser Verification

**Files:**
- Modify: `tests/test_terminal_v8_render.py`
- No implementation file should change if the regression passes.
- Create verification artifacts under `artifacts/ui-checks/tare-stale-two-browser/`.

- [ ] **Step 1: Add route-level stale tare regression coverage**

Add this test in `tests/test_terminal_v8_render.py` after `test_terminal_success_post_redirects_with_notice_query`:

```python
def test_terminal_stale_tare_submit_renders_refresh_alert_without_overwrite(connection):
    card_id = release_ready_card("26195", machine_id=1, sequence=1)
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.20").ok

    response = asyncio.run(
        save_tare_weight(
            make_test_request(f"/terminal/cards/{card_id}/tare"),
            card_id,
            str(loaded_version),
            "1.50",
        )
    )
    card = db.fetch_terminal_card_detail(card_id)
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "location" not in response.headers
    assert card["tare_weight"] == 1.2
    assert 'id="terminal-refresh-alert"' in html
    assert "Данните са променени" in html
    assert "Презаредете картата, преди да продължите." in html
    assert STALE_CARD_MESSAGE not in html
    assert 'class="terminal-toast"' not in html
```

- [ ] **Step 2: Run the new route-level test**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_stale_tare_submit_renders_refresh_alert_without_overwrite -q
```

Expected on current code:

```text
1 passed
```

If this fails, stop and inspect `app/main.py::save_tare_weight()`, `app/main.py::terminal_post_response()`, and `app/main.py::build_terminal_feedback()` before changing behavior. The expected invariant is: stale tare submits render the terminal page with the reload alert, do not redirect, do not show the stale internal message, and do not overwrite the saved tare value.

- [ ] **Step 3: Run focused terminal tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_roll_entry.py::test_tare_update_persists_and_checks_loaded_version tests/test_terminal_v8_render.py::test_terminal_v8_failed_tare_result_renders_under_tare_field tests/test_terminal_v8_render.py::test_terminal_v8_stale_new_roll_result_renders_refresh_alert_not_chip_or_error_text tests/test_terminal_v8_render.py::test_terminal_stale_tare_submit_renders_refresh_alert_without_overwrite -q
```

Expected:

```text
4 passed
```

- [ ] **Step 4: Seed a temporary live database for the two-browser check**

Run:

```bash
mkdir -p .test-runtime/tare-stale-live artifacts/ui-checks/tare-stale-two-browser
source .venv/bin/activate
```

Then run this Python seed command from the same shell:

```bash
EXTRUSION_DB_PATH=.test-runtime/tare-stale-live/extrusion_terminal.sqlite3 python - <<'PY'
from app import db
from app.importer import import_cards_from_csv
from tests.test_terminal_v8_render import csv_bytes, extrusion_row

db.init_db()
result = import_cards_from_csv(
    "tare-stale-live.csv",
    csv_bytes(extrusion_row("TARE-STALE-001")),
    overwrite_existing=False,
)
assert result.rows_imported == 1, result
with db.connect() as connection:
    card_id = int(connection.execute(
        "SELECT id FROM cards WHERE order_number = ?",
        ("TARE-STALE-001",),
    ).fetchone()["id"])
card = db.fetch_admin_card_detail(card_id)
assert db.release_card(
    card_id,
    machine_id=1,
    machine_sequence=1,
    loaded_version=int(card["version"]),
    max_roll_weight="60.0",
).ok
print(card_id)
PY
```

Expected output:

```text
1
```

- [ ] **Step 5: Start the live server against the temporary database**

In a dedicated terminal, run:

```bash
cd /home/sk/projects/extrusion-terminal
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/tare-stale-live/extrusion_terminal.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Expected:

```text
Uvicorn running on http://127.0.0.1:8765
```

- [ ] **Step 6: Create the one-off Playwright check script**

Create `artifacts/ui-checks/tare-stale-two-browser/tare-stale-check.mjs` with this exact content:

```javascript
import { chromium } from "@playwright/test";

const baseURL = "http://127.0.0.1:8765";
const cardURL = `${baseURL}/terminal/cards/1`;
const screenshotPath = "artifacts/ui-checks/tare-stale-two-browser/stale-tare-refresh-alert.png";

const browser = await chromium.launch();
const freshPage = await browser.newPage({ viewport: { width: 1920, height: 950 } });
const stalePage = await browser.newPage({ viewport: { width: 1920, height: 950 } });

await freshPage.goto(cardURL);
await stalePage.goto(cardURL);

await freshPage.locator('input[name="tare_weight"]').fill("1.20");
await freshPage.locator("h2").click();
await freshPage.waitForURL("**/terminal/cards/1?notice=tare_saved");
await freshPage.waitForSelector(".terminal-toast");

await stalePage.locator('input[name="tare_weight"]').fill("1.50");
await stalePage.locator("h2").click();
await stalePage.waitForSelector("#terminal-refresh-alert");

const bodyText = await stalePage.locator("body").innerText();
if (!bodyText.includes("Данните са променени")) {
  throw new Error("Refresh alert title was not visible after stale tare submit.");
}
if (!bodyText.includes("Презаредете картата, преди да продължите.")) {
  throw new Error("Refresh alert body was not visible after stale tare submit.");
}
if (bodyText.includes("Картата е променена след зареждането на страницата")) {
  throw new Error("Internal stale-card message leaked into the terminal UI.");
}
if (bodyText.includes("Шпула е записана.")) {
  throw new Error("Stale tare submit incorrectly rendered a success notice.");
}

await stalePage.screenshot({ path: screenshotPath, fullPage: true });
await browser.close();
console.log(`Saved ${screenshotPath}`);
```

- [ ] **Step 7: Run the Playwright check**

Run:

```bash
node artifacts/ui-checks/tare-stale-two-browser/tare-stale-check.mjs
```

Expected:

```text
Saved artifacts/ui-checks/tare-stale-two-browser/stale-tare-refresh-alert.png
```

- [ ] **Step 8: Stop the live server**

Return to the server terminal and press:

```text
Ctrl+C
```

Expected:

```text
Application shutdown complete.
```

---

## Task 4: Admin Sticky Summary Monitor Decision

**Files:**
- Inspect: `app/templates/admin_card_detail.html`
- Inspect: `app/static/css/app.css`
- Modify: `reports/full-workflow-audit-20260618.md`
- Modify CSS only if the real monitor check fails.

- [ ] **Step 1: Confirm the current sticky-summary implementation**

Verify these current facts:

- `app/templates/admin_card_detail.html` renders `<section class="section admin-summary-panel">`.
- `app/static/css/app.css` sets `.admin-summary-panel { position: sticky; top: 0; z-index: 2; }`.
- The mobile media section already sets `.admin-summary-panel { position: static; }`.

Run:

```bash
rg -n "admin-summary-panel|position: sticky|position: static" app/templates/admin_card_detail.html app/static/css/app.css
```

Expected output includes:

```text
app/templates/admin_card_detail.html:98:  <section class="section admin-summary-panel">
app/static/css/app.css:510:.admin-summary-panel {
app/static/css/app.css:511:  position: sticky;
app/static/css/app.css:1376:  .admin-summary-panel {
app/static/css/app.css:1377:    position: static;
```

- [ ] **Step 2: Perform the actual monitor check**

On the shift-manager monitor, open a completed card in admin detail:

```text
http://127.0.0.1:8000/admin/cards/<completed-card-id>
```

Scroll through the order details, materials ledger, roll ledger, and timing ledger. The sticky summary is acceptable if all of these are true:

- It does not cover form fields while the user is trying to edit them.
- It does not cover row action buttons.
- It does not hide validation/error notices.
- The user can still scan and edit ledger rows without fighting the sticky panel.

- [ ] **Step 3A: If the monitor check passes, do not change CSS**

Record the decision in `reports/full-workflow-audit-20260618.md` by replacing:

```markdown
- **Open, monitor check only:** Admin detail summary uses sticky positioning. Full-page screenshot stitching made it appear over other sections; check on the actual shift-manager monitor only if the sticky summary feels obstructive in use.
```

with:

```markdown
- **Completed/no app change:** Admin detail summary sticky positioning was treated as a real-monitor usability check. It is not an app defect unless it obstructs shift-manager use on the actual monitor.
```

- [ ] **Step 3B: If the monitor check fails, make the minimal CSS change**

If the sticky summary obstructs real use, replace this CSS in `app/static/css/app.css`:

```css
.admin-summary-panel {
  position: sticky;
  top: 0;
  z-index: 2;
}
```

with:

```css
.admin-summary-panel {
  position: static;
}
```

Then add a note to `reports/full-workflow-audit-20260618.md` replacing the open sticky-summary bullet with:

```markdown
- **Completed:** Admin detail summary sticky positioning was removed after real-monitor verification showed it obstructed shift-manager use.
```

- [ ] **Step 4: If CSS changed, run a focused render/CSS check**

Only run this if Step 3B changed CSS:

```bash
rg -n "admin-summary-panel|position: static|position: sticky" app/static/css/app.css app/templates/admin_card_detail.html
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py -q
```

Expected:

```text
tests/test_admin_card_detail_redesign.py passes
```

---

## Task 5: Update Audit Report Final Status

**Files:**
- Modify: `reports/full-workflow-audit-20260618.md`

- [ ] **Step 1: Update the remediation summary**

After Tasks 1-3 pass, update the current remediation summary near the top of `reports/full-workflow-audit-20260618.md`.

Replace:

```markdown
- Remaining app-level cleanup from this report: 2 low-risk UX copy improvements:
  - simplify the pending-card print-block message so missing totals do not read like data corruption;
  - make the import overwrite checkbox/warning clearer that overwrite updates imported/front-card fields for existing order numbers.
- Remaining verification item from this report: run the exact terminal tare stale-write two-browser check.
```

with:

```markdown
- App-level cleanup from this report is complete: the pending-card print-block copy was clarified, and the import overwrite warning now explains the overwrite scope.
- Terminal tare stale-write verification is complete: the terminal route blocks stale tare submits without overwrite, and the live two-browser check showed the reload warning.
```

- [ ] **Step 2: Update the Non-Bug UX/Process Improvements section**

In `reports/full-workflow-audit-20260618.md`, replace:

```markdown
- **Open, low-risk copy cleanup:** Pending-card print block lists all missing conditions plus `Критичните тегла за печат трябва да са валидни числа.`. That final message is technically produced by missing totals, but it reads like a separate data corruption problem.
```

with:

```markdown
- **Completed:** Pending-card print blocking now avoids the numeric-validity warning when the card is simply missing required print fields; true invalid stored numeric values still use the numeric-validity warning.
```

Also replace:

```markdown
- **Open, low-risk copy cleanup:** Import overwrite still needs a clearer operator warning that it updates imported/front-card fields for existing order numbers, not only “existing orders with same number.”
```

with:

```markdown
- **Completed:** Import overwrite copy now explains that overwrite updates imported/front-card fields for existing order numbers, preserves production/workstation data, and blocks stale CSV rows that would replace admin corrections.
```

- [ ] **Step 3: Update the Not Fully Tested section**

In `reports/full-workflow-audit-20260618.md`, replace:

```markdown
- Terminal tare stale-write was not separately tested after terminal roll stale-write; same backend version guard is used, but this exact form was not repeated in two-browser mode.
```

with:

```markdown
- Terminal tare stale-write was verified after the original audit: stale tare submits are blocked by the terminal route, preserve the newer tare value, and show the reload warning in the live two-browser check.
```

- [ ] **Step 4: Add verification artifact reference**

In the `Main Artifact Paths` list in `reports/full-workflow-audit-20260618.md`, add:

```markdown
- `artifacts/ui-checks/tare-stale-two-browser/stale-tare-refresh-alert.png`
```

---

## Task 6: Final Verification

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run focused test set**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_print_output.py tests/test_admin_routes.py tests/test_terminal_v8_render.py tests/test_roll_entry.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 2: Run full Python suite**

Run:

```bash
source .venv/bin/activate
python -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Run syntax/import check**

Run:

```bash
source .venv/bin/activate
python -m compileall app
```

Expected:

```text
compileall completes without errors
```

- [ ] **Step 4: Run whitespace diff check**

Run:

```bash
git diff --check
```

Expected: no output and exit code `0`.

- [ ] **Step 5: Review changed files**

Run:

```bash
git diff -- app/printing.py app/templates/admin_import.html app/static/css/app.css tests/test_print_output.py tests/test_admin_routes.py tests/test_terminal_v8_render.py reports/full-workflow-audit-20260618.md
```

Review for:

- no unrelated refactors;
- no mutation of runtime database paths;
- no arbitrary message text passed through URLs;
- print invalid-number protection preserved;
- import overwrite backend behavior untouched;
- stale tare route preserves newer tare data;
- audit report accurately reflects what was verified.

---

## Self-Review Checklist

- Spec coverage:
  - Print-block copy cleanup: Task 1 and Task 5.
  - Import overwrite warning copy: Task 2 and Task 5.
  - Terminal tare stale-write two-browser check: Task 3 and Task 5.
  - Admin sticky summary monitor check: Task 4.

- Completeness scan:
  - No task contains unresolved marker text or vague “add tests” instructions.
  - Every code-changing step includes exact code.
  - Every verification step includes exact commands and expected outcomes.

- Type and name consistency:
  - Uses existing `build_print_readiness()`, `validate_print_readiness()`, `save_tare_weight()`, `make_test_request()`, `card_version()`, `STALE_CARD_MESSAGE`, and `admin_import()`.
  - Does not introduce new backend APIs or database fields.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-22-audit-leftover-cleanup.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using `superpowers:executing-plans`, with checkpoints for review.

Recommended choice: **Subagent-Driven** because Tasks 1, 2, 3, and 4 are independent enough to split cleanly, and review between tasks will keep the audit report accurate.
