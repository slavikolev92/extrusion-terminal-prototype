# Terminal Focus And Notices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the remaining terminal issues: machine cards must focus the running card before paused/pending cards, and successful terminal POST actions must show top-right success toasts after redirect.

**Architecture:** Keep queue ordering and redirect-after-post behavior unchanged. Change only the backend focus-card selector and carry success notices through redirects with whitelisted notice codes mapped server-side to fixed Bulgarian messages.

**Tech Stack:** FastAPI, Jinja2 server-rendered templates, direct SQLite via `app/db.py`, pytest, repo-local Playwright/Node for UI verification.

---

## Repository Rules For Execution

- Work in `/home/sk/projects/extrusion-terminal`.
- Follow `AGENTS.md`.
- Use the repo-local Python virtualenv: `source .venv/bin/activate`.
- Do not mutate `data/extrusion_terminal.sqlite3` in automated tests or UI checks.
- Use temporary SQLite paths under `.test-runtime/`.
- Save UI screenshots under `artifacts/ui-checks/`.
- Do not stage or commit unless the user explicitly asks.
- Implement only issues 1 and 3 from `TERMINAL_ISSUES_1_AND_3_TEMP_HANDOFF.md`.
- Issue 2, recipe-field autosave, is already complete; do not modify it except for unavoidable test interactions.
- Remove `TERMINAL_ISSUES_1_AND_3_TEMP_HANDOFF.md` only if the user explicitly agrees to include that cleanup in the same execution batch. Otherwise leave it untouched.

## Behavioral Requirements

Issue 1: machine card focus priority

- The active queue order remains sorted by machine sequence.
- `queue.focus_card` for each machine must choose:
  1. the running card on that machine,
  2. otherwise the first paused card by queue sequence,
  3. otherwise the first pending card by queue sequence,
  4. otherwise `None`.
- `/terminal?machine_id=N` must default to that same focus card.
- The V8 top machine navigation card must link to and display that focus card.

Issue 3: terminal success notices

- Keep PRG/redirect-after-post for successful terminal writes.
- Successful terminal POST routes redirect to `/terminal/cards/{card_id}?notice=<code>`.
- Notice codes are whitelisted and mapped server-side to fixed Bulgarian messages.
- Do not place arbitrary message text in the URL.
- Do not add sessions, flash middleware, localStorage, client-side persistence, AJAX, or new database state.
- Unknown notice codes are ignored.
- Existing failed POST behavior remains inline without redirect.

## File Structure

Modify:

- `app/db.py`
  - Update only `select_machine_focus_card()`.

- `app/main.py`
  - Add whitelisted terminal notice constants/helpers.
  - Add `notice` query params to terminal GET handlers.
  - Add optional `notice_code` to `terminal_post_response()`.
  - Pass notice codes from terminal POST routes.
  - Teach `build_terminal_feedback()` to render whitelisted notice messages as toast feedback.

- `tests/test_terminal_detail.py`
  - Add backend focus-card priority regression coverage.

- `tests/test_terminal_v8_render.py`
  - Add route/render coverage for machine focus defaulting and top-card rendering.
  - Add redirect notice and notice render/ignore tests.
  - Update existing terminal success redirect expectations to include the new notice query.

- `IMPLEMENTATION_PLAN.md`
  - Add a concise Milestone 11 follow-up bullet and verification note after the implementation is verified.

No template or CSS changes are expected for issue 3. Toast markup, CSS, and auto-dismiss JavaScript already exist in `app/templates/terminal.html`.

## Task 1: Add Failing Tests For Machine Focus Priority

**Files:**
- Modify: `tests/test_terminal_detail.py`
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Add backend focus priority test**

In `tests/test_terminal_detail.py`, update the imports:

```python
from app.constants import STATUS_PAUSED, STATUS_RUNNING
```

Add this test after `test_machine_queue_focus_prefers_occupied_card_over_next_pending`:

```python
def test_machine_queue_focus_prefers_running_over_earlier_paused(connection):
    paused_card_id = import_ready_card("25305")
    pending_card_id = import_ready_card("25306")
    running_card_id = import_ready_card("25307")
    assert db.release_card(
        paused_card_id,
        machine_id=2,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    assert db.release_card(
        pending_card_id,
        machine_id=2,
        machine_sequence=2,
        max_roll_weight="60.0",
    ).ok
    assert db.release_card(
        running_card_id,
        machine_id=2,
        machine_sequence=3,
        max_roll_weight="60.0",
    ).ok
    connection.execute(
        "UPDATE cards SET status = ? WHERE id = ?",
        (STATUS_PAUSED, paused_card_id),
    )
    connection.execute(
        "UPDATE cards SET status = ? WHERE id = ?",
        (STATUS_RUNNING, running_card_id),
    )
    connection.commit()

    queues = db.fetch_machine_queues()
    machine_2 = next(queue for queue in queues if queue["machine"]["id"] == 2)

    assert machine_2["focus_card"]["order_number"] == "25307"
    assert [card["order_number"] for card in machine_2["cards"]] == [
        "25305",
        "25306",
        "25307",
    ]
```

- [ ] **Step 2: Add terminal context/top-card render test**

In `tests/test_terminal_v8_render.py`, add this test after `test_terminal_v8_selects_requested_machine_focus_card`:

```python
def test_terminal_v8_machine_card_and_machine_default_prefer_running_over_paused(
    connection,
):
    paused_id = release_ready_card("26145", machine_id=2, sequence=1)
    release_ready_card("26146", machine_id=2, sequence=2)
    running_id = release_ready_card("26147", machine_id=2, sequence=3)
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    context = terminal_context(selected_machine_id=2)
    html = render_terminal(machine_id=2)

    assert context["selected_card"]["id"] == running_id
    assert context["selected_card"]["order_number"] == "26147"
    assert f'href="/terminal/cards/{running_id}"' in html
    assert "Машина 2: №26147" in html
    machine_tab_match = re.search(
        rf'<a class="machine-tab running selected" href="/terminal/cards/{running_id}">.*?</a>',
        html,
        flags=re.S,
    )
    assert machine_tab_match is not None
    machine_tab = machine_tab_match.group(0)
    assert "Изработване" in machine_tab
    assert "V8 Customer 26147" in machine_tab
```

- [ ] **Step 3: Run focused tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_detail.py::test_machine_queue_focus_prefers_running_over_earlier_paused tests/test_terminal_v8_render.py::test_terminal_v8_machine_card_and_machine_default_prefer_running_over_paused -q
```

Expected result:

- Both tests fail before implementation.
- Failure should show the paused/lower-sequence card is still selected as focus.

## Task 2: Implement Machine Focus Priority

**Files:**
- Modify: `app/db.py`

- [ ] **Step 1: Update `select_machine_focus_card()`**

In `app/db.py`, replace:

```python
def select_machine_focus_card(cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    for card in cards:
        if card["status"] in (STATUS_RUNNING, STATUS_PAUSED):
            return card
    return cards[0] if cards else None
```

with:

```python
def select_machine_focus_card(cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    for status in (STATUS_RUNNING, STATUS_PAUSED, STATUS_PENDING):
        for card in cards:
            if card["status"] == status:
                return card
    return None
```

- [ ] **Step 2: Run focused focus tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_detail.py::test_machine_queue_focus_prefers_running_over_earlier_paused tests/test_terminal_v8_render.py::test_terminal_v8_machine_card_and_machine_default_prefer_running_over_paused -q
```

Expected result:

- Both tests pass.

- [ ] **Step 3: Run existing terminal focus/render tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_detail.py tests/test_terminal_v8_render.py -q
```

Expected result:

- All tests pass.

## Task 3: Add Failing Tests For Terminal Success Notices

**Files:**
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Extend route imports**

In the `from app.main import (...)` block in `tests/test_terminal_v8_render.py`, add:

```python
    save_tare_weight,
```

- [ ] **Step 2: Add redirect notice test**

Add this test near `test_terminal_finish_success_redirects_to_canonical_get`:

```python
def test_terminal_success_post_redirects_with_notice_query(connection):
    card_id = release_ready_card("26190", machine_id=1, sequence=1)
    loaded_version = card_version(card_id)

    response = asyncio.run(
        save_tare_weight(
            make_test_request(f"/terminal/cards/{card_id}/tare"),
            card_id,
            str(loaded_version),
            "1.20",
        )
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=tare_saved"
    )
```

- [ ] **Step 3: Add whitelisted notice render and unknown-code tests**

Add these tests after `test_terminal_v8_success_result_renders_one_dismissible_toast`:

```python
def test_terminal_v8_notice_code_renders_one_dismissible_toast(connection):
    card_id = release_ready_card("26191", machine_id=1, sequence=1)

    html = render_terminal(card_id, terminal_notice="tare_saved")

    assert html.count('class="terminal-toast"') == 1
    assert "Шпула е записана." in html
    assert 'class="terminal-toast-close"' in html
    assert html.count('role="alert"') == 0


def test_terminal_v8_unknown_notice_code_is_ignored(connection):
    card_id = release_ready_card("26192", machine_id=1, sequence=1)

    html = render_terminal(card_id, terminal_notice="not_a_real_notice")

    assert 'class="terminal-toast"' not in html
    assert "not_a_real_notice" not in html
```

- [ ] **Step 4: Add existing error behavior guard**

Existing tests already cover inline failed rendering. Keep `test_terminal_finish_failure_renders_inline_without_redirect` unchanged, and add this assertion to it:

```python
    assert 'class="terminal-toast"' not in response.body.decode("utf-8")
```

- [ ] **Step 5: Run focused notice tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_success_post_redirects_with_notice_query tests/test_terminal_v8_render.py::test_terminal_v8_notice_code_renders_one_dismissible_toast tests/test_terminal_v8_render.py::test_terminal_v8_unknown_notice_code_is_ignored tests/test_terminal_v8_render.py::test_terminal_finish_success_redirects_to_canonical_get tests/test_terminal_v8_render.py::test_terminal_finish_failure_renders_inline_without_redirect -q
```

Expected result:

- New redirect/render tests fail before implementation.
- Existing finish success test may fail once implementation changes redirect location until its assertion is updated in Task 4.

## Task 4: Implement Whitelisted Redirect Notices

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Add notice constants and helper**

In `app/main.py`, add these constants below `SAFE_ANCHOR_PATTERN`:

```python
TERMINAL_NOTICE_MESSAGES = {
    "materials_saved": ("Материалите са записани.",),
    "tare_saved": ("Шпула е записана.",),
    "roll_saved": ("Ролката е записана.",),
    "roll_updated": ("Ролката е коригирана.",),
    "roll_deleted": ("Ролката е изтрита.",),
    "timing_started": ("Времето е стартирано.",),
    "timing_paused": ("Времето е паузирано.",),
    "timing_resumed": ("Времето е продължено.",),
    "card_finished": ("Картата е приключена.",),
}
```

Below `terminal_post_response()`, add:

```python
def terminal_redirect_url(card_id: int, notice_code: str | None = None) -> str:
    base_url = f"/terminal/cards/{card_id}"
    if not notice_code:
        return base_url
    return f"{base_url}?{urlencode({'notice': notice_code})}"


def terminal_notice_result(notice_code: str | None) -> RuleResult | None:
    messages = TERMINAL_NOTICE_MESSAGES.get(str(notice_code or ""))
    if not messages:
        return None
    return RuleResult(True, messages)
```

- [ ] **Step 2: Accept notice query on terminal GET routes**

In `app/main.py`, replace:

```python
@app.get("/terminal")
async def terminal(request: Request, machine_id: int | None = None):
    return terminal_response(request, selected_machine_id=machine_id)
```

with:

```python
@app.get("/terminal")
async def terminal(
    request: Request,
    machine_id: int | None = None,
    notice: str | None = None,
):
    return terminal_response(
        request,
        selected_machine_id=machine_id,
        terminal_notice=notice,
    )
```

Replace:

```python
@app.get("/terminal/cards/{card_id}")
async def terminal_card(request: Request, card_id: int):
    return terminal_response(request, selected_card_id=card_id)
```

with:

```python
@app.get("/terminal/cards/{card_id}")
async def terminal_card(
    request: Request,
    card_id: int,
    notice: str | None = None,
):
    return terminal_response(
        request,
        selected_card_id=card_id,
        terminal_notice=notice,
    )
```

- [ ] **Step 3: Add optional notice code to terminal post helper**

In `app/main.py`, replace:

```python
def terminal_post_response(
    request: Request,
    card_id: int,
    result_name: str,
    result: RuleResult,
    **extra: Any,
):
    if result.ok:
        return RedirectResponse(url=f"/terminal/cards/{card_id}", status_code=303)
    return terminal_response(
        request,
        selected_card_id=card_id,
        **{result_name: result},
        **extra,
    )
```

with:

```python
def terminal_post_response(
    request: Request,
    card_id: int,
    result_name: str,
    result: RuleResult,
    notice_code: str | None = None,
    **extra: Any,
):
    if result.ok:
        return RedirectResponse(
            url=terminal_redirect_url(card_id, notice_code),
            status_code=303,
        )
    return terminal_response(
        request,
        selected_card_id=card_id,
        **{result_name: result},
        **extra,
    )
```

- [ ] **Step 4: Pass notice codes from terminal POST routes**

In `app/main.py`, update terminal POST helper calls as follows:

```python
    return terminal_post_response(
        request,
        card_id,
        "material_result",
        material_result,
        notice_code="materials_saved",
    )
```

```python
    return terminal_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        notice_code="tare_saved",
        roll_result_target="tare",
    )
```

```python
    return terminal_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        notice_code="roll_saved",
        roll_result_target="new_roll",
    )
```

```python
    return terminal_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        notice_code="roll_updated",
        roll_result_target="roll_row",
        roll_result_roll_id=roll_id,
    )
```

For both roll-delete terminal routes, pass:

```python
        notice_code="roll_deleted",
```

For timing routes, pass:

```python
        notice_code="timing_started",
```

```python
        notice_code="timing_paused",
```

```python
        notice_code="timing_resumed",
```

For finish, pass:

```python
        notice_code="card_finished",
```

Keep all failure-only extras such as `roll_result_target`, `roll_result_roll_id`, and `roll_delete_selected_roll_id` unchanged.

- [ ] **Step 5: Render notice messages in terminal feedback**

In `build_terminal_feedback()` in `app/main.py`, after the `feedback` dict is created and before the `for result_name, target in (...)` loop, insert:

```python
    notice_result = terminal_notice_result(results.get("terminal_notice"))
    if notice_result is not None:
        feedback["toast"] = {"messages": notice_result.messages}
```

- [ ] **Step 6: Update existing redirect assertions**

In `tests/test_terminal_v8_render.py`, update successful terminal redirect expectations:

```python
    assert deleted.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=roll_deleted"
    )
```

```python
    assert response.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=card_finished"
    )
```

If any other existing successful terminal POST assertion expects the bare canonical card URL, update it to the route-specific notice URL. Do not change failed POST expectations.

- [ ] **Step 7: Run focused notice tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_success_post_redirects_with_notice_query tests/test_terminal_v8_render.py::test_terminal_v8_notice_code_renders_one_dismissible_toast tests/test_terminal_v8_render.py::test_terminal_v8_unknown_notice_code_is_ignored tests/test_terminal_v8_render.py::test_terminal_finish_success_redirects_to_canonical_get tests/test_terminal_v8_render.py::test_terminal_finish_failure_renders_inline_without_redirect -q
```

Expected result:

- All focused notice tests pass.

- [ ] **Step 8: Run terminal render and detail tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py tests/test_terminal_detail.py -q
```

Expected result:

- All tests pass.

## Task 5: Update Milestone Tracker

**Files:**
- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Add Milestone 11 follow-up bullet**

In `IMPLEMENTATION_PLAN.md`, under `Milestone 11 - Pilot Rehearsal` and `Completed audit follow-up before rehearsal`, add:

```markdown
- terminal focus and success-notice fixes: machine navigation now prioritizes running cards over paused and pending cards without changing queue order, and successful terminal POST actions carry whitelisted redirect notice codes that render top-right success toasts after the redirected GET.
```

- [ ] **Step 2: Add verification note only after verification succeeds**

After Task 6 verification succeeds, add a concise verification bullet under `Verification completed for this follow-up` with the exact commands and artifact path that passed. Use the actual counts from the executed run.

## Task 6: Browser Verification With Temporary Database

**Files:**
- No source changes expected.
- Create artifacts only under:
  - `.test-runtime/terminal-focus-notices/`
  - `artifacts/ui-checks/terminal-focus-notices/`

- [ ] **Step 1: Create temporary runtime directories**

Run:

```bash
mkdir -p .test-runtime/terminal-focus-notices artifacts/ui-checks/terminal-focus-notices
```

- [ ] **Step 2: Seed a temporary SQLite database**

Run:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH="$PWD/.test-runtime/terminal-focus-notices/extrusion_terminal.sqlite3" python - <<'PY'
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

def extrusion_row(order_number, customer):
    return {
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
        "notes": "Terminal focus and notice verification.",
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

result = import_cards_from_csv(
    "terminal-focus-notices.csv",
    csv_bytes(
        extrusion_row("FOCUS-PAUSED", "Focus Customer Paused"),
        extrusion_row("FOCUS-PENDING", "Focus Customer Pending"),
        extrusion_row("FOCUS-RUNNING", "Focus Customer Running"),
    ),
    overwrite_existing=False,
)
assert result.rows_imported == 3, result

with db.connect() as connection:
    rows = connection.execute(
        "SELECT id, order_number, version FROM cards ORDER BY order_number"
    ).fetchall()

ids = {row["order_number"]: int(row["id"]) for row in rows}
versions = {row["order_number"]: int(row["version"]) for row in rows}

assert db.release_card(ids["FOCUS-PAUSED"], 1, 1, versions["FOCUS-PAUSED"], "60.0").ok
assert db.release_card(ids["FOCUS-PENDING"], 1, 2, versions["FOCUS-PENDING"], "60.0").ok
assert db.release_card(ids["FOCUS-RUNNING"], 1, 3, versions["FOCUS-RUNNING"], "60.0").ok

def version(card_id):
    return int(db.fetch_terminal_card_detail(card_id)["version"])

assert db.start_production_timing(ids["FOCUS-PAUSED"], version(ids["FOCUS-PAUSED"])).ok
assert db.pause_production_timing(ids["FOCUS-PAUSED"], version(ids["FOCUS-PAUSED"])).ok
assert db.start_production_timing(ids["FOCUS-RUNNING"], version(ids["FOCUS-RUNNING"])).ok

Path(".test-runtime/terminal-focus-notices/cards.json").write_text(
    json.dumps(ids),
    encoding="utf-8",
)
print(json.dumps(ids))
PY
```

- [ ] **Step 3: Start the FastAPI server on the temporary database**

Run:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH="$PWD/.test-runtime/terminal-focus-notices/extrusion_terminal.sqlite3" python -m uvicorn app.main:app --host 127.0.0.1 --port 8772
```

- [ ] **Step 4: Run Playwright verification from a second terminal/session**

Run:

```bash
node - <<'JS'
const fs = require('fs');
const { chromium } = require('playwright');

const cards = JSON.parse(
  fs.readFileSync('.test-runtime/terminal-focus-notices/cards.json', 'utf8'),
);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 950 } });
  const baseUrl = 'http://127.0.0.1:8772';

  await page.goto(`${baseUrl}/terminal?machine_id=1`, { waitUntil: 'networkidle' });
  if (!page.url().includes(`/terminal/cards/${cards["FOCUS-RUNNING"]}`)) {
    throw new Error(`Machine default did not select running card: ${page.url()}`);
  }
  const selectedTitle = await page.locator('.topbar h2').textContent();
  if (!selectedTitle.includes('FOCUS-RUNNING')) {
    throw new Error(`Selected card is not the running focus card: ${selectedTitle}`);
  }

  await page.locator('form[action$="/timing/pause"] button').click();
  await page.waitForLoadState('networkidle');
  if (!page.url().includes('notice=timing_paused')) {
    throw new Error(`Pause did not redirect with timing notice: ${page.url()}`);
  }
  const toastText = await page.locator('.terminal-toast').textContent();
  if (!toastText.includes('Времето е паузирано.')) {
    throw new Error(`Timing pause toast did not render: ${toastText}`);
  }

  await page.screenshot({
    path: 'artifacts/ui-checks/terminal-focus-notices/focus-running-toast.png',
    fullPage: true,
  });

  await page.waitForTimeout(3500);
  const toastHidden = await page.locator('.terminal-toast').getAttribute('hidden');
  if (toastHidden === null) {
    throw new Error('Toast did not auto-dismiss.');
  }

  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
JS
```

Expected result:

- Command exits `0`.
- `/terminal?machine_id=1` selects the running card, not the earlier paused card.
- Successful pause redirects with `notice=timing_paused`.
- The toast renders and auto-dismisses.
- Screenshot exists at `artifacts/ui-checks/terminal-focus-notices/focus-running-toast.png`.

- [ ] **Step 5: Stop the temporary server**

Stop the `uvicorn` process from Step 3 with `Ctrl+C`.

## Task 7: Final Verification And Review

**Files:**
- Expected source changes:
  - `app/db.py`
  - `app/main.py`
  - `tests/test_terminal_detail.py`
  - `tests/test_terminal_v8_render.py`
  - `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Run focused automated tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_detail.py tests/test_terminal_v8_render.py tests/test_terminal_sync.py -q
```

Expected result:

- All tests pass.

- [ ] **Step 2: Run full Python test suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected result:

- All tests pass.

- [ ] **Step 3: Run Python syntax/import check**

Run:

```bash
source .venv/bin/activate
python -m compileall app
```

Expected result:

- Command exits `0`.

- [ ] **Step 4: Run diff whitespace check**

Run:

```bash
git diff --check
```

Expected result:

- No whitespace errors.

- [ ] **Step 5: Confirm Playwright artifact**

Run:

```bash
ls -l artifacts/ui-checks/terminal-focus-notices/focus-running-toast.png
```

Expected result:

- Screenshot file exists and has nonzero size.

- [ ] **Step 6: Review changed code**

Run:

```bash
git diff -- app/db.py app/main.py app/templates/terminal.html tests/test_terminal_detail.py tests/test_terminal_v8_render.py IMPLEMENTATION_PLAN.md
```

Review checklist:

- Machine queue order remains unchanged.
- `select_machine_focus_card()` prioritizes running, then paused, then pending.
- `/terminal?machine_id=N` uses `queue.focus_card` and now selects the running card in mixed paused/running cases.
- Redirect-after-post remains in place for successful terminal actions.
- Notice messages are fixed server-side strings keyed by whitelisted codes.
- Unknown notice codes are ignored.
- Failure paths still render inline and do not redirect.
- No sessions, localStorage, AJAX, new routes, or database changes were added.
- Issue 2 recipe autosave behavior was not changed.
- No issue outside terminal issues 1 and 3 was implemented.

## Self-Review Notes

Spec coverage:

- Issue 1 is covered by Task 1 tests and Task 2 implementation.
- Issue 3 is covered by Task 3 tests and Task 4 implementation.
- Manual/UI verification in Task 6 covers the combined operator-facing behavior.
- Final verification in Task 7 covers focused suites, full suite, syntax/imports, whitespace, screenshot artifact, and code review.

Scope exclusions:

- No queue ordering changes.
- No admin planning order changes.
- No backend schema or migration changes.
- No sessions, flash middleware, localStorage, AJAX, or client-side persistence.
- No issue 2 changes.
- No commits or staging unless the user explicitly asks after implementation and review.
