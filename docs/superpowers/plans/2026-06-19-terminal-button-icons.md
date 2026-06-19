# Terminal Button Icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add decorative icons to the workstation terminal Start, Pause, Resume, Finish, and Add Roll buttons while preserving all existing workflow behavior and Bulgarian labels.

**Architecture:** Keep the change local to the server-rendered V8 terminal template. Add one Jinja macro for reusable button icons, style it with the existing inline terminal CSS, and update only the affected button markup. Add a focused render test that verifies icons are present in the correct forms across pending, running, and paused states.

**Tech Stack:** FastAPI, Jinja2 templates, direct SQLite test fixtures, pytest, Playwright for final UI screenshot verification.

---

## Execution Prompt

You are working in `/home/sk/projects/extrusion-terminal`. Follow `AGENTS.md`: do not stage or commit unless the user explicitly asks, do not mutate `data/extrusion_terminal.sqlite3` during automated tests, and for UI work run focused tests plus capture a Playwright screenshot under `artifacts/ui-checks/` before claiming completion.

Implement small decorative icons on the V8 workstation terminal buttons:

- `Старт`: play icon
- `Продължи`: play icon
- `Пауза`: pause icon
- `Приключи`: check-circle icon
- `Добави`: plus icon

Labels must remain visible. Icons must be decorative with `aria-hidden="true"` and must inherit button color through `currentColor`. Do not add a frontend build step, do not add a runtime dependency, do not change backend behavior, and do not change database schema or workflow rules.

## Files

- Modify: `app/templates/terminal.html`
- Modify: `tests/test_terminal_v8_render.py`
- Create during verification only: `artifacts/ui-checks/terminal-button-icons/terminal-action-icons.png`

## Task 1: Add A Failing Render Test

**Files:**
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Add the focused test**

Add this test after `test_terminal_v8_print_link_is_available_only_for_completed_cards` in `tests/test_terminal_v8_render.py`:

```python
def test_terminal_v8_action_and_roll_add_buttons_render_decorative_icons(connection):
    card_id = release_ready_card("26182", machine_id=1, sequence=1)

    def form_block(html: str, action: str) -> str:
        match = re.search(
            rf'<form action="{re.escape(action)}".*?</form>',
            html,
            flags=re.S,
        )
        assert match is not None
        return match.group(0)

    pending_html = render_terminal(card_id)
    start_form = form_block(
        pending_html,
        f"/terminal/cards/{card_id}/timing/start",
    )
    assert 'data-icon="play"' in start_form
    assert 'aria-hidden="true"' in start_form
    assert "Старт" in start_form
    assert 'data-icon="pause"' in pending_html
    assert 'data-icon="check-circle"' in pending_html
    assert 'data-icon="plus"' in pending_html

    assert db.start_production_timing(card_id, card_version(card_id)).ok
    running_html = render_terminal(card_id)
    pause_form = form_block(
        running_html,
        f"/terminal/cards/{card_id}/timing/pause",
    )
    finish_form = form_block(running_html, f"/terminal/cards/{card_id}/finish")
    roll_form = form_block(running_html, f"/terminal/cards/{card_id}/rolls")
    assert 'data-icon="pause"' in pause_form
    assert "Пауза" in pause_form
    assert 'data-icon="check-circle"' in finish_form
    assert "Приключи" in finish_form
    assert 'data-icon="plus"' in roll_form
    assert "Добави" in roll_form

    assert db.pause_production_timing(card_id, card_version(card_id)).ok
    paused_html = render_terminal(card_id)
    resume_form = form_block(
        paused_html,
        f"/terminal/cards/{card_id}/timing/resume",
    )
    assert 'data-icon="play"' in resume_form
    assert "Продължи" in resume_form
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_v8_render.py::test_terminal_v8_action_and_roll_add_buttons_render_decorative_icons -q
```

Expected result: the test fails because `data-icon="play"` is not present yet.

## Task 2: Add The Icon Macro And Button Styling

**Files:**
- Modify: `app/templates/terminal.html`

- [ ] **Step 1: Add the Jinja macro at the top of the template**

Insert this macro before the current `<!doctype html>` line in `app/templates/terminal.html`:

```jinja
{% macro button_icon(name) -%}
  <span class="button-icon" data-icon="{{ name }}" aria-hidden="true">
    {% if name == "play" -%}
      <svg viewBox="0 0 24 24" focusable="false">
        <polygon points="6 4 20 12 6 20 6 4"></polygon>
      </svg>
    {%- elif name == "pause" -%}
      <svg viewBox="0 0 24 24" focusable="false">
        <path d="M10 5v14"></path>
        <path d="M14 5v14"></path>
      </svg>
    {%- elif name == "check-circle" -%}
      <svg viewBox="0 0 24 24" focusable="false">
        <circle cx="12" cy="12" r="9"></circle>
        <path d="m9 12 2 2 4-4"></path>
      </svg>
    {%- elif name == "plus" -%}
      <svg viewBox="0 0 24 24" focusable="false">
        <path d="M5 12h14"></path>
        <path d="M12 5v14"></path>
      </svg>
    {%- endif %}
  </span>
{%- endmacro %}
```

- [ ] **Step 2: Add shared icon CSS**

In `app/templates/terminal.html`, after the existing `button:disabled` rule near the top of the inline CSS, add:

```css
    .action-button,
    .roll-entry button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }

    .button-icon {
      width: 18px;
      height: 18px;
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }

    .button-icon svg {
      width: 100%;
      height: 100%;
      display: block;
      fill: none;
      stroke: currentColor;
      stroke-width: 2.4;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
```

This keeps icons aligned with the label, preserves disabled colors, and does not affect the overflow menu button.

- [ ] **Step 3: Run the focused test and confirm it still fails**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_v8_render.py::test_terminal_v8_action_and_roll_add_buttons_render_decorative_icons -q
```

Expected result: the test still fails because the button markup has not been updated to use `button_icon(...)`.

## Task 3: Add Icons To The Target Buttons

**Files:**
- Modify: `app/templates/terminal.html`

- [ ] **Step 1: Update the Start button block**

Replace the active and disabled Start buttons with:

```jinja
                  <button class="action-button action-primary" type="submit">{{ button_icon("play") }}<span>Старт</span></button>
```

and:

```jinja
                <button class="action-button" type="button" disabled>{{ button_icon("play") }}<span>Старт</span></button>
```

- [ ] **Step 2: Update the Pause and Resume button block**

Replace the active Pause button with:

```jinja
                  <button class="action-button action-secondary" type="submit">{{ button_icon("pause") }}<span>Пауза</span></button>
```

Replace the active Resume button with:

```jinja
                  <button class="action-button action-primary" type="submit">{{ button_icon("play") }}<span>Продължи</span></button>
```

Replace the disabled Pause button with:

```jinja
                <button class="action-button" type="button" disabled>{{ button_icon("pause") }}<span>Пауза</span></button>
```

- [ ] **Step 3: Update the Finish button block**

Replace the active Finish button with:

```jinja
                  <button class="action-button {% if selected_card.status == 'running' %}action-primary{% else %}action-secondary{% endif %}" type="submit">{{ button_icon("check-circle") }}<span>Приключи</span></button>
```

Replace the disabled Finish button with:

```jinja
                <button class="action-button" type="button" disabled>{{ button_icon("check-circle") }}<span>Приключи</span></button>
```

- [ ] **Step 4: Update the Add Roll button**

Replace the Add Roll submit button with:

```jinja
                    <button class="roll-add-button" type="submit" {% if not can_edit_rolls %}disabled{% endif %}>{{ button_icon("plus") }}<span>Добави</span></button>
```

- [ ] **Step 5: Run the focused test and confirm it passes**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_v8_render.py::test_terminal_v8_action_and_roll_add_buttons_render_decorative_icons -q
```

Expected result: `1 passed`.

## Task 4: Run Focused Regression Tests

**Files:**
- Test only

- [ ] **Step 1: Run terminal render tests**

Run:

```bash
source .venv/bin/activate && python -m pytest tests/test_terminal_v8_render.py -q
```

Expected result: all tests in `tests/test_terminal_v8_render.py` pass.

- [ ] **Step 2: Run syntax/import checks for the app**

Run:

```bash
source .venv/bin/activate && python -m compileall app tests/test_terminal_v8_render.py
```

Expected result: command exits `0`.

## Task 5: Capture A Playwright UI Screenshot

**Files:**
- Create during verification only: `artifacts/ui-checks/terminal-button-icons/terminal-action-icons.png`

- [ ] **Step 1: Confirm the live app is reachable**

Run:

```bash
curl -I http://127.0.0.1:8000/terminal
```

Expected result: `HTTP/1.1 200 OK`. If port `8000` is not running, start the app in a separate terminal with:

```bash
source .venv/bin/activate && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- [ ] **Step 2: Capture the screenshot with Playwright**

Run:

```bash
mkdir -p artifacts/ui-checks/terminal-button-icons && node -e "const { chromium } = require('@playwright/test'); (async () => { const browser = await chromium.launch({ headless: true }); const page = await browser.newPage({ viewport: { width: 1920, height: 950 } }); await page.goto('http://127.0.0.1:8000/terminal', { waitUntil: 'networkidle' }); await page.screenshot({ path: 'artifacts/ui-checks/terminal-button-icons/terminal-action-icons.png', fullPage: true }); await browser.close(); })().catch((error) => { console.error(error); process.exit(1); });"
```

Expected result: command exits `0` and creates `artifacts/ui-checks/terminal-button-icons/terminal-action-icons.png`.

- [ ] **Step 3: Inspect the screenshot**

Open or inspect `artifacts/ui-checks/terminal-button-icons/terminal-action-icons.png`. Confirm the action buttons still fit in the top bar, icon and label are aligned, disabled buttons remain visibly disabled, and the Add Roll button still fits beside the gross-weight input.

## Task 6: Final Review

**Files:**
- Review only

- [ ] **Step 1: Check the diff**

Run:

```bash
git diff -- app/templates/terminal.html tests/test_terminal_v8_render.py docs/superpowers/plans/2026-06-19-terminal-button-icons.md
```

Expected result: diff is limited to this plan, the terminal template icon/styling changes, and the focused render test.

- [ ] **Step 2: Check whitespace**

Run:

```bash
git diff --check
```

Expected result: no whitespace errors.

- [ ] **Step 3: Report completion without staging or committing**

Final report should mention:

- `app/templates/terminal.html` now renders decorative icons for Start, Resume, Pause, Finish, and Add Roll.
- `tests/test_terminal_v8_render.py` has focused coverage for the icon markup.
- Focused pytest command passed.
- `python -m compileall app tests/test_terminal_v8_render.py` passed.
- Playwright screenshot path: `artifacts/ui-checks/terminal-button-icons/terminal-action-icons.png`.
- No files were staged or committed.

## Self-Review

- Spec coverage: The plan covers all requested buttons, keeps labels visible, uses decorative icons, and includes automated plus visual verification.
- Placeholder scan: The plan contains concrete paths, snippets, commands, and expected results.
- Scope check: The plan is one UI-only terminal template slice and does not touch backend logic, database schema, print output, or admin workflows.
