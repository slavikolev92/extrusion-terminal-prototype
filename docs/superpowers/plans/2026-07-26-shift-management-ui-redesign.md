# Shift Management UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the crowded terminal action rail and unfinished shift dialogs with the approved Kolev-branded header and polished Bulgarian shift workflow while preserving all existing shift persistence, attribution, blocking, and concurrency behavior.

**Architecture:** Keep the existing FastAPI routes, SQLite schema, shift services, server-rendered terminal template, and modal state machine. Add a small presentation layer in `app/main.py` for Bulgarian timestamps, one-decimal shift weights, a three-row history preview, and an explicit full-history view; then restructure the terminal header and `_terminal_shift_window.html` around those presentation fields. Extend the existing fail-closed Playwright workflow to prove layout geometry, live-clock behavior, navigation, localization, and unchanged production invariants against a temporary SQLite database.

**Tech Stack:** Python 3, FastAPI, direct `sqlite3`, Jinja2, server-rendered HTML/CSS, small vanilla JavaScript state handlers, pytest, repository-local Node Playwright.

## Global Constraints

- The approved behavior source is `v2-files/TASK-01-SHIFT-MANAGEMENT.md`.
- Use `source-files/new-design.JPG` only as the terminal-header reference; do not copy its unrelated machine-card or selected-order changes.
- Use `source-files/screen_start_shift.png`, `source-files/screen_start_shift_confirmation.png`, and `source-files/main_shift_button.png` as visual references, with the written specification controlling every conflict.
- Do not read or derive V2 requirements from the repository-root `README.md`.
- Add a full-width terminal header with the Kolev logo on the left, two equal-size actions centered against the full viewport, and one equal-size shift-status action on the right.
- Center actions must be labelled `Чакащи поръчки` and `Произведени поръчки`; labels must never wrap, clip, overlap, or escape their controls.
- The shift action must show a gray status dot plus `Няма активна смяна` when closed, or a green status dot plus `Смяна N` when active.
- The shift action opens management; it must never be labelled as an exit action.
- All visible shift-interface text must be Bulgarian.
- Visible shift timestamps must use `26 юли 2026 г., 21:30` style and omit seconds.
- Start-selection and start-confirmation clocks are live previews; only final confirmation persists the authoritative server timestamp.
- The no-active-shift gate has no close control and no `Отказ` action. `Назад` from start confirmation returns only to number selection.
- Start and end confirmation states share one visual structure.
- The active overview contains a current-shift card and a preview of at most three completed shifts; `Виж всички` opens the full history in the same modal.
- The active shift number remains the one constrained autosaving dropdown. No second correction control is allowed.
- Do not add a duration or elapsed-time display.
- Production summaries use the static title `Произведени количества`, no distinct-item counter, Bulgarian columns, and one-decimal gross kilograms.
- Do not change the shift database schema, M002, roll attribution, start/end services, terminal mutation gate, polling signature, optimistic concurrency, or running machine/order/timer state.
- Do not add worker, roster, time-correction, cancellation, packaging, pallet, print, or downloadable-report functionality.
- Do not mutate `data/extrusion_terminal.sqlite3` or any production database. Tests and browser checks use temporary SQLite databases only.
- Do not add a frontend framework, icon dependency, CDN dependency, or new service. Use the existing logo asset and text/status-dot controls; decorative screenshot icons are not required.
- Preserve unrelated working-tree changes. Stage and commit only the files named by the current task, and only after the user authorizes implementation commits.
- Task 01 remains open until the user accepts the finished live UI.

---

## File Responsibility Map

- `app/main.py` — normalize the allowed shift window states and build display-only shift dictionaries containing Bulgarian timestamp strings and one-decimal weight strings.
- `app/templates/terminal.html` — render the new global header, own its responsive geometry, retain the existing terminal layout, and run the existing modal/focus/polling JavaScript plus the live-clock updater.
- `app/templates/_terminal_shift_window.html` — render the gate, start confirmation, active overview, end confirmation, full history, handoff summary, historical summary, and reload state as one modal surface.
- `tests/test_shift_routes.py` — verify presentation helpers and server-side view-state normalization without relying on CSS.
- `tests/test_terminal_v8_render.py` — verify the exact server-rendered header, Bulgarian modal structure, link destinations, formatted values, and absence of stale English/counter markup.
- `scripts/verify_shift_management_ui.mjs` — verify real browser behavior, exact header geometry, no-overflow controls, live clock, confirmation persistence boundary, history navigation, summaries, stale-page safety, and screenshots.
- `tests/test_shift_management_ui_script_safety.py` — retain fail-closed temporary-database protection and pin the expanded browser evidence contract.
- `docs/implementation-notes/shift-management.md` — record the accepted final UI structure, browser command, and evidence paths after implementation.
- `v2-files/PLAN.md` — keep Task 01 open until live UI acceptance, then record completion separately from production deployment gates.
- `v2-files/AGENTS.md` — append the required final migration assessment; the expected result is `No migration` only if the actual final diff is presentation-only.

---

### Task 0: Establish The Execution Baseline

**Files:**
- Inspect: `AGENTS.md`
- Inspect: `v2-files/AGENTS.md`
- Inspect: `v2-files/TASK-01-SHIFT-MANAGEMENT.md`
- Inspect: `docs/superpowers/plans/2026-07-26-shift-management-ui-redesign.md`

**Interfaces:**
- Consumes: the merged shift-management implementation at commit `91455ab` plus the approved uncommitted V2 documentation updates.
- Produces: an isolated feature worktree with a trustworthy test baseline and no runtime-database access.

- [ ] **Step 1: Create or verify the isolated execution worktree**

Use `superpowers:using-git-worktrees` at execution time. If the approved documentation changes are still uncommitted, preserve only these files before creating the worktree:

```text
v2-files/AGENTS.md
v2-files/PLAN.md
v2-files/TASK-01-SHIFT-MANAGEMENT.md
docs/superpowers/plans/2026-07-26-shift-management-ui-redesign.md
```

Do not include changes from the separate `admin-planning-redesign` worktree.

- [ ] **Step 2: Confirm the worktree and branch identity**

Run:

```bash
git branch --show-current
git status --short --branch
git worktree list
```

Expected: a dedicated shift UI redesign branch/worktree, with no unrelated modified files.

- [ ] **Step 3: Run formatting and baseline tests before source changes**

Run:

```bash
git diff --check
.venv/bin/python -m pytest -q
```

Expected: `git diff --check` exits `0`; the last known merged baseline is `547 passed`. Investigate any changed pre-existing result before modifying source.

- [ ] **Step 4: Record the baseline in the SDD ledger**

Record the exact branch, base commit, test count, and dirty-file list in the SDD workspace ledger. Task 0 creates no source commit.

---

### Task 1: Add The Shift Presentation Model And Full-History State

**Files:**
- Modify: `app/main.py` around `build_terminal_shift_context()` and the existing display helpers
- Modify: `tests/test_shift_routes.py` around `test_history_summary_and_back_use_the_same_window_state`

**Interfaces:**
- Consumes: raw dictionaries returned by `fetch_shift_window_state()` and `fetch_shift_summary()`; `one_decimal_weight_display(value, blank="-")`.
- Produces: `format_shift_datetime(value: Any) -> str`, `build_shift_display(shift: dict[str, Any]) -> dict[str, Any]`, `shift_window_state == "history"`, `recent_completed_shifts`, and display-only `*_display` keys.

- [ ] **Step 1: Write failing tests for Bulgarian timestamp and weight presentation**

Add to `tests/test_shift_routes.py`:

```python
def test_shift_display_helpers_format_bulgarian_values_without_raw_seconds():
    assert main_module.format_shift_datetime("2026-07-26 21:30:59") == (
        "26 юли 2026 г., 21:30"
    )
    assert main_module.format_shift_datetime(None) == "-"
    assert main_module.format_shift_datetime("not-a-timestamp") == "-"

    display = main_module.build_shift_display(
        {
            "id": 8,
            "shift_number": 2,
            "started_at": "2026-07-26 21:30:59",
            "ended_at": "2026-07-27 06:05:02",
            "total_gross_weight": "550.00",
            "orders": [
                {
                    "card_id": 11,
                    "order_number": "26001",
                    "customer": "Клиент",
                    "product_type": "Фолио",
                    "roll_count": 2,
                    "gross_weight": "550.00",
                }
            ],
        }
    )

    assert display["started_at_display"] == "26 юли 2026 г., 21:30"
    assert display["ended_at_display"] == "27 юли 2026 г., 06:05"
    assert display["total_gross_weight_display"] == "550.0"
    assert display["orders"][0]["gross_weight_display"] == "550.0"
```

- [ ] **Step 2: Write a failing test for explicit history state and the three-row preview**

Add:

```python
def test_shift_context_exposes_full_history_state_and_three_recent_rows():
    completed = [
        {
            "id": shift_id,
            "shift_number": shift_id,
            "started_at": f"2026-07-{20 + shift_id:02d} 06:00:00",
            "ended_at": f"2026-07-{20 + shift_id:02d} 14:00:00",
            "distinct_item_count": 0,
            "roll_count": 0,
            "total_gross_weight": "0.00",
        }
        for shift_id in (4, 3, 2, 1)
    ]
    state = {
        "configuration": {"shift_count": 4, "version": 1},
        "active_shift": {
            "id": 5,
            "shift_number": 1,
            "started_at": "2026-07-26 21:30:59",
            "ended_at": None,
            "version": 1,
        },
        "suggested_shift_number": 2,
        "completed_shifts": completed,
    }

    context = main_module.build_terminal_shift_context(
        "history",
        None,
        None,
        state=state,
    )

    assert context["shift_window_state"] == "history"
    assert context["shift_blocking"] is False
    assert [row["id"] for row in context["recent_completed_shifts"]] == [4, 3, 2]
    assert [row["id"] for row in context["completed_shifts"]] == [4, 3, 2, 1]
    assert context["active_shift"]["started_at_display"] == (
        "26 юли 2026 г., 21:30"
    )
```

- [ ] **Step 3: Run the focused tests and confirm the intended failures**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_shift_routes.py::test_shift_display_helpers_format_bulgarian_values_without_raw_seconds \
  tests/test_shift_routes.py::test_shift_context_exposes_full_history_state_and_three_recent_rows \
  -q
```

Expected: FAIL because the presentation helpers, `history` state, and `recent_completed_shifts` do not exist.

- [ ] **Step 4: Implement the Bulgarian presentation helpers**

Add near the other display helpers in `app/main.py`:

```python
BULGARIAN_MONTH_NAMES = (
    "",
    "януари",
    "февруари",
    "март",
    "април",
    "май",
    "юни",
    "юли",
    "август",
    "септември",
    "октомври",
    "ноември",
    "декември",
)


def format_shift_datetime(value: Any) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return "-"
    try:
        parsed = datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return "-"
    return (
        f"{parsed.day} {BULGARIAN_MONTH_NAMES[parsed.month]} "
        f"{parsed.year} г., {parsed:%H:%M}"
    )


def build_shift_display(shift: dict[str, Any]) -> dict[str, Any]:
    display = dict(shift)
    display["started_at_display"] = format_shift_datetime(shift.get("started_at"))
    display["ended_at_display"] = format_shift_datetime(shift.get("ended_at"))
    if "total_gross_weight" in shift:
        display["total_gross_weight_display"] = one_decimal_weight_display(
            shift.get("total_gross_weight"),
            "0.0",
        )
    if "orders" in shift:
        display["orders"] = [
            {
                **order,
                "gross_weight_display": one_decimal_weight_display(
                    order.get("gross_weight"),
                    "0.0",
                ),
            }
            for order in shift["orders"]
        ]
    return display
```

- [ ] **Step 5: Normalize and enrich the shift context**

Update `build_terminal_shift_context()` so it:

```python
raw_active_shift = state["active_shift"]
active_shift = build_shift_display(raw_active_shift) if raw_active_shift else None
completed_shifts = [
    build_shift_display(shift)
    for shift in state["completed_shifts"]
]
normalized_view = (
    shift_view
    if shift_view in {"overview", "history", "summary"}
    else None
)
```

After loading a valid summary, wrap it with `build_shift_display()`. Add a nonblocking `history` branch before `overview`, and return:

```python
"completed_shifts": completed_shifts,
"recent_completed_shifts": completed_shifts[:3],
```

Use `active_shift` rather than the raw dictionary for `shift_options` and the returned context. Preserve the existing gate, handoff-summary, reload, invalid-ID, and no-active-shift precedence.

- [ ] **Step 6: Update the existing state-machine test**

Extend `test_history_summary_and_back_use_the_same_window_state` so it calls:

```python
history = terminal_context(shift_view="history")
```

and asserts:

```python
assert history["shift_window_state"] == "history"
assert history["shift_blocking"] is False
assert history["recent_completed_shifts"] == history["completed_shifts"][:3]
```

The historical-summary `Назад` destination will be verified after the template is changed in Task 4.

- [ ] **Step 7: Run the focused route tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_shift_routes.py -q
```

Expected: all shift route/context tests PASS.

- [ ] **Step 8: Commit the presentation foundation**

```bash
git add app/main.py tests/test_shift_routes.py
git commit -m "Add shift UI presentation context"
```

---

### Task 2: Add The Dedicated Kolev Terminal Header

**Files:**
- Modify: `app/templates/terminal.html` around `.app`, `.machine-nav`, `.machine-nav-actions`, and the terminal header markup
- Modify: `tests/test_terminal_v8_render.py` around `test_terminal_header_has_one_global_shift_button_without_inline_shift_details`

**Interfaces:**
- Consumes: `active_shift`, `active_shift.shift_number`, the existing Kolev logo at `/static/images/kolev-logo.png`, and the existing overlay control IDs `queue-open`, `history-open`, and `shift-open`.
- Produces: `.terminal-header`, `.terminal-global-nav`, three `.terminal-header-action` controls, `.shift-status-dot`, and a machine-navigation row containing only machine cards.

- [ ] **Step 1: Replace the old header render test with active and inactive header contracts**

Update the existing test and add an inactive-state test:

```python
def test_terminal_header_has_centered_global_actions_and_active_shift_status(connection):
    active_shift = db.fetch_active_shift()
    assert active_shift is not None

    html = render_terminal()
    header = re.search(r'<header class="terminal-header".*?</header>', html, re.S)

    assert header is not None
    header_html = header.group(0)
    assert '/static/images/kolev-logo.png' in header_html
    assert header_html.count('class="terminal-header-action') == 3
    assert '>Чакащи поръчки<' in header_html
    assert '>Произведени поръчки<' in header_html
    assert 'id="shift-open"' in header_html
    assert 'class="shift-status-dot is-active"' in header_html
    assert f'>Смяна {active_shift["shift_number"]}<' in header_html
    assert str(active_shift["started_at"]) not in header_html
    assert 'class="machine-nav-actions"' not in html


def test_terminal_header_shows_nonwrapping_no_active_shift_status(connection):
    end_active_test_shift()

    html = render_terminal()
    header = re.search(r'<header class="terminal-header".*?</header>', html, re.S)

    assert header is not None
    header_html = header.group(0)
    assert 'class="shift-status-dot"' in header_html
    assert 'class="shift-status-dot is-active"' not in header_html
    assert '>Няма активна смяна<' in header_html
    assert 'data-terminal-action="shift"' in header_html
```

- [ ] **Step 2: Run the header tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py::test_terminal_header_has_centered_global_actions_and_active_shift_status \
  tests/test_terminal_v8_render.py::test_terminal_header_shows_nonwrapping_no_active_shift_status \
  -q
```

Expected: FAIL because the actions still live beside the machine cards and use the `Shift` label.

- [ ] **Step 3: Render the new three-region header**

Insert immediately inside `.app`, before `.machine-nav`:

```html
<header class="terminal-header" aria-label="Основна навигация">
  <a class="terminal-brand" href="/terminal" aria-label="Терминал Kolev">
    <img src="{{ url_for('static', path='/images/kolev-logo.png') }}" alt="Kolev">
  </a>
  <nav class="terminal-global-nav" aria-label="Поръчки">
    <button class="terminal-header-action" id="queue-open" type="button"
            data-terminal-action="waiting" aria-controls="queue-overlay"
            aria-expanded="false">Чакащи поръчки</button>
    <button class="terminal-header-action" id="history-open" type="button"
            data-terminal-action="produced" aria-controls="history-overlay"
            aria-expanded="false">Произведени поръчки</button>
  </nav>
  <button class="terminal-header-action terminal-shift-action" id="shift-open"
          type="button" data-terminal-action="shift"
          aria-controls="shift-window"
          aria-expanded="{{ 'true' if shift_window_state != 'closed' else 'false' }}">
    <span class="shift-status-dot{% if active_shift %} is-active{% endif %}"
          aria-hidden="true"></span>
    <span data-shift-header-label>
      {% if active_shift %}Смяна {{ active_shift.shift_number }}{% else %}Няма активна смяна{% endif %}
    </span>
  </button>
</header>
```

Remove `.machine-nav-actions` and its three old buttons from `.machine-nav`. Preserve all three IDs so the existing queue, produced-order, and shift JavaScript continues to bind without route changes.

- [ ] **Step 4: Implement fixed equal sizing and true viewport centering**

Update the terminal CSS:

```css
.app {
  grid-template-rows: auto auto minmax(0, 1fr);
}

.terminal-header {
  --terminal-header-action-width: 214px;
  min-width: 0;
  min-height: 68px;
  padding: 10px 24px;
  border-bottom: 1px solid #cfd6de;
  background: var(--surface);
  display: grid;
  grid-template-columns: minmax(var(--terminal-header-action-width), 1fr) auto
    minmax(var(--terminal-header-action-width), 1fr);
  align-items: center;
  gap: 18px;
}

.terminal-brand {
  justify-self: start;
  display: inline-flex;
  align-items: center;
}

.terminal-brand img {
  display: block;
  width: 142px;
  max-height: 40px;
  object-fit: contain;
}

.terminal-global-nav {
  justify-self: center;
  display: grid;
  grid-template-columns: repeat(2, var(--terminal-header-action-width));
  gap: 10px;
}

.terminal-header-action {
  width: var(--terminal-header-action-width);
  min-width: var(--terminal-header-action-width);
  min-height: 46px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: clip;
}

.terminal-shift-action {
  justify-self: end;
}

.shift-status-dot {
  width: 10px;
  height: 10px;
  flex: 0 0 10px;
  border-radius: 50%;
  background: #aeb7c1;
}

.shift-status-dot.is-active {
  background: var(--green);
}
```

Change `.machine-nav` to one full-width column and `.machine-nav-list` to `repeat(4, minmax(0, 1fr))`. At the existing `max-width: 1360px` breakpoint, set `--terminal-header-action-width: 190px` and reduce header action font size to `13px`; do not permit wrapping. At the existing short-height breakpoint, reduce header height and action height without reducing the width below `190px`.

- [ ] **Step 5: Preserve focus visibility and button semantics**

Add `:focus-visible` outlines for `.terminal-brand` and `.terminal-header-action`. Keep the status dot `aria-hidden`; the full Bulgarian text remains the accessible status label.

- [ ] **Step 6: Run the terminal render regression file**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_v8_render.py -q
```

Expected: all render tests PASS after replacing the old header assertion; no queue/history overlay tests regress.

- [ ] **Step 7: Commit the terminal header**

```bash
git add app/templates/terminal.html tests/test_terminal_v8_render.py
git commit -m "Add terminal global action header"
```

---

### Task 3: Redesign The Blocking Start Flow And Shared Confirmations

**Files:**
- Modify: `app/templates/_terminal_shift_window.html` gate, start-confirm, end-confirm, and dialog header
- Modify: `app/templates/terminal.html` shift modal CSS and JavaScript title/live-clock handling
- Modify: `tests/test_terminal_v8_render.py` gate and confirmation tests

**Interfaces:**
- Consumes: `shift_window_state`, `shift_blocking`, `shift_options`, `suggested_shift_number`, `active_shift.started_at_display`, and the existing form endpoints/data attributes.
- Produces: `.shift-selection-pane`, `.shift-confirmation-pane`, `.shift-details-card`, `[data-shift-live-clock]`, `updateShiftClocks()`, and identical start/end confirmation layout contracts.

- [ ] **Step 1: Write failing render tests for the approved Bulgarian start flow**

Replace and extend the gate/confirmation assertions:

```python
def test_no_active_shift_gate_uses_compact_bulgarian_start_flow_without_dismissal(connection):
    end_active_test_shift()

    html = render_terminal()
    shift_window = shift_window_block(html)

    assert 'data-shift-state="gate"' in shift_window
    assert 'data-shift-blocking="true"' in shift_window
    assert 'data-shift-pane="gate"' in shift_window
    assert 'data-shift-pane="start-confirm" hidden' in shift_window
    assert "Начало на смяна" in shift_window
    assert "Изберете номера на смяната, за да започнете работа." in shift_window
    assert "Номер на смяна" in shift_window
    assert "Започни смяна" in shift_window
    assert shift_window.count("data-shift-live-clock") == 2
    assert "data-shift-close" not in shift_window
    assert "Отказ" not in shift_window
    assert ">Back<" not in shift_window
    assert ">Yes<" not in shift_window
    assert "updateShiftClocks" in html
    assert "window.setInterval(updateShiftClocks, 1000)" in html
```

Add:

```python
def test_start_and_end_confirmations_share_the_same_bulgarian_structure(connection):
    html = render_terminal(shift_view="overview")
    shift_window = shift_window_block(html)

    assert shift_window.count('class="shift-window-pane shift-confirmation-pane') == 2
    assert "Потвърждение за начало" in shift_window
    assert "Потвърждение за приключване" in shift_window
    assert shift_window.count("shift-details-card") == 2
    assert shift_window.count(">Назад<") == 2
    assert shift_window.count(">Потвърди<") == 2
    assert ">Back<" not in shift_window
    assert ">Yes<" not in shift_window
    assert "data-shift-nested-modal" not in shift_window
```

- [ ] **Step 2: Run the focused render tests and confirm failure**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py::test_no_active_shift_gate_uses_compact_bulgarian_start_flow_without_dismissal \
  tests/test_terminal_v8_render.py::test_start_and_end_confirmations_share_the_same_bulgarian_structure \
  -q
```

Expected: FAIL on old English actions, missing live clocks, and mismatched confirmation markup.

- [ ] **Step 3: Replace the gate with the compact approved selection state**

Keep the existing start form and hidden concurrency/card fields. Render:

```html
<div class="shift-window-pane shift-selection-pane" data-shift-pane="gate">
  <div class="shift-state-intro">
    <h3>Начало на смяна</h3>
    <p>Изберете номера на смяната, за да започнете работа.</p>
  </div>
  <label class="shift-number-field">
    <span>Номер на смяна</span>
    <select name="shift_number" data-shift-start-number>
      {% for shift_number in shift_options %}
        <option value="{{ shift_number }}"{% if shift_number == suggested_shift_number %} selected{% endif %}>{{ shift_number }}</option>
      {% endfor %}
    </select>
  </label>
  <div class="shift-live-time-card">
    <strong>Начало на смяна</strong>
    <time data-shift-live-clock></time>
  </div>
  <button class="shift-primary-action" type="button"
          data-shift-confirm-open="start">Започни смяна</button>
</div>
```

Do not render a close button or `Отказ` while `shift_blocking` is true.
Retain the existing `shift_result` error rendering inside the selection pane:

```html
{% if shift_result and not shift_result.ok %}
  <div class="shift-window-error" role="alert">
    {% for message in shift_result.messages %}<p>{{ message }}</p>{% endfor %}
  </div>
{% endif %}
```

- [ ] **Step 4: Render start and end confirmation panes from one visual pattern**

Both panes must use `.shift-confirmation-pane`, `.shift-state-intro`, `.shift-details-card`, and `.shift-confirm-actions`.

Start details:

```html
<div class="shift-detail-row">
  <span>Смяна</span>
  <strong data-shift-start-selection>{{ suggested_shift_number }}</strong>
</div>
<div class="shift-detail-row">
  <span>Начало</span>
  <strong><time data-shift-live-clock></time></strong>
</div>
```

End details:

```html
<div class="shift-detail-row">
  <span>Смяна</span>
  <strong>{{ active_shift.shift_number }}</strong>
</div>
<div class="shift-detail-row">
  <span>Начало</span>
  <strong>{{ active_shift.started_at_display }}</strong>
</div>
<div class="shift-detail-row">
  <span>Край</span>
  <strong><time data-shift-live-clock></time></strong>
</div>
```

Use `Назад` for `data-shift-confirm-back` and `Потвърди` for the existing submit data attributes. The start confirmation's `Назад` targets `gate`; the end confirmation's `Назад` targets `overview`.

- [ ] **Step 5: Add the shared live-clock updater**

Inside the existing shift-window JavaScript closure in `terminal.html`, add:

```javascript
const shiftLiveClocks = Array.from(
  shiftWindow?.querySelectorAll("[data-shift-live-clock]") || [],
);
const bulgarianMonths = [
  "януари", "февруари", "март", "април", "май", "юни",
  "юли", "август", "септември", "октомври", "ноември", "декември",
];
const twoDigits = (value) => String(value).padStart(2, "0");
const updateShiftClocks = () => {
  const now = new Date();
  const visibleValue = (
    `${now.getDate()} ${bulgarianMonths[now.getMonth()]} ${now.getFullYear()} г., `
    + `${twoDigits(now.getHours())}:${twoDigits(now.getMinutes())}`
  );
  shiftLiveClocks.forEach((clock) => {
    clock.textContent = visibleValue;
    clock.dateTime = now.toISOString();
  });
};
updateShiftClocks();
window.setInterval(updateShiftClocks, 1000);
```

The form continues to submit no timestamp. `start_shift()` and `end_shift()` remain the only authoritative timestamp writers.

- [ ] **Step 6: Update pane titles entirely in Bulgarian**

Update `showShiftPane()` title mapping:

```javascript
const shiftPaneTitles = {
  gate: "Начало на смяна",
  "start-confirm": "Потвърждение за начало",
  overview: "Управление на смяната",
  "end-confirm": "Потвърждение за приключване",
  history: "История на смените",
  summary: "Произведени количества",
  reload: "Смяната е променена",
};
```

Set the title from this mapping. Preserve the existing focus trap, Escape rules, backdrop rules, inert application handling, and reload behavior.

- [ ] **Step 7: Apply state-specific compact dialog styling**

Use modifier classes or `data-shift-state` selectors so gate/start-confirm/end-confirm use `width: min(640px, calc(100vw - 32px))` and overview/history/summary use `width: min(1080px, calc(100vw - 32px))`. Match existing terminal `--surface`, `--line`, `--primary-text`, `--secondary-text`, `--blue`, and focus styles.

- [ ] **Step 8: Run route and render tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_shift_routes.py tests/test_terminal_v8_render.py -q
```

Expected: all tests PASS, including blocking and stale-shift tests.

- [ ] **Step 9: Commit the start and confirmation redesign**

```bash
git add app/templates/_terminal_shift_window.html app/templates/terminal.html \
  tests/test_terminal_v8_render.py
git commit -m "Redesign shift start and confirmation flows"
```

---

### Task 4: Redesign Active Shift, History, And Production Summaries

**Files:**
- Modify: `app/templates/_terminal_shift_window.html` overview, history, and summary panes
- Modify: `app/templates/terminal.html` overview/history/summary CSS and pane navigation JavaScript
- Modify: `tests/test_terminal_v8_render.py` active/history/summary tests
- Modify: `tests/test_shift_routes.py` history state and historical-summary return expectations

**Interfaces:**
- Consumes: `active_shift` with display keys, `recent_completed_shifts`, `completed_shifts`, `selected_shift_summary` with order display keys, and the `history` state from Task 1.
- Produces: `[data-shift-pane="overview"]`, `[data-shift-pane="history"]`, `[data-shift-pane="summary"]`, `shift_view=history`, Bulgarian history/summary tables, and historical-summary `Назад` routing.

- [ ] **Step 1: Write failing tests for the active current-shift card and three-row preview**

Update the active-window test to assert:

```python
context = terminal_context(shift_view="overview")
active_shift = context["active_shift"]
html = render_terminal(shift_view="overview")
shift_window = shift_window_block(html)

assert "Управление на смяната" in shift_window
assert "Текуща смяна" in shift_window
assert 'name="shift_number" data-shift-number-select' in shift_window
assert active_shift["started_at_display"] in shift_window
assert "Приключи смяната" in shift_window
assert "Продължителност" not in shift_window
assert "Виж всички" in shift_window
assert 'shift_view=history' in shift_window
assert shift_window.count('data-shift-history-preview-id=') == 3
```

Create four completed occurrences before rendering so the preview limit is proven. Keep the existing assertion that the current number is the only correction dropdown.

- [ ] **Step 2: Write failing tests for the full history pane and historical-summary return path**

Add:

```python
def test_full_shift_history_replaces_contents_and_uses_bulgarian_columns(connection):
    completed = end_active_test_shift()
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("2", int(configuration["version"])).ok

    html = render_terminal(shift_view="history")
    shift_window = shift_window_block(html)

    assert html.count('role="dialog" aria-modal="true" data-shift-dialog') == 1
    assert 'data-shift-state="history"' in shift_window
    assert 'data-shift-pane="history"' in shift_window
    for heading in (
        "Смяна",
        "Начало",
        "Край",
        "Различни изделия",
        "Ролки",
        "Бруто, кг",
        "Преглед",
    ):
        assert heading in shift_window
    assert f'data-shift-history-id="{completed["id"]}"' in shift_window
    assert ">Shift<" not in shift_window
    assert ">Start<" not in shift_window
    assert ">End<" not in shift_window
    assert ">View<" not in shift_window
```

Update `test_history_view_and_back_replace_contents_in_one_modal` so the historical summary contains:

```python
assert f'href="/terminal/cards/{card_id}?shift_view=history"' in summary_html
assert ">Назад<" in summary_html
```

- [ ] **Step 3: Write failing summary-localization tests**

Update the populated summary test:

```python
summary_context = terminal_context(
    card_id,
    shift_view="summary",
    shift_id=str(summary["id"]),
    handoff="1",
)
display_summary = summary_context["selected_shift_summary"]

assert "Произведени количества" in shift_window
assert f'Смяна {summary["shift_number"]}' in shift_window
assert display_summary["started_at_display"] in shift_window
assert display_summary["ended_at_display"] in shift_window
assert "артикула" not in shift_window
for heading in (
    "Производствена поръчка",
    "Клиент",
    "Вид изделие",
    "Брой ролки",
    "Бруто, кг",
):
    assert heading in shift_window
assert "60.5" in shift_window
assert "60.50" not in shift_window
```

Update the empty-summary test to assert the Bulgarian empty-state text and no `0 артикула` counter.

- [ ] **Step 4: Run the focused tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py::test_active_window_shows_start_time_separate_end_action_and_newest_history \
  tests/test_terminal_v8_render.py::test_full_shift_history_replaces_contents_and_uses_bulgarian_columns \
  tests/test_terminal_v8_render.py::test_end_summary_renders_header_and_required_order_columns \
  tests/test_terminal_v8_render.py::test_empty_shift_summary_renders_zero_items_and_empty_table \
  tests/test_terminal_v8_render.py::test_history_view_and_back_replace_contents_in_one_modal \
  -q
```

Expected: FAIL on old English labels, raw timestamps, two-decimal values, missing full-history state, and the old item counter.

- [ ] **Step 5: Render the approved active overview**

The overview pane must contain:

```html
<section class="shift-current-section" aria-labelledby="shift-current-title">
  <h3 id="shift-current-title">Текуща смяна</h3>
  <div class="shift-current-card">
    <form action="/terminal/shifts/current/number" method="post"
          data-shift-number-form>
      <input type="hidden" name="shift_occurrence_id" value="{{ active_shift.id }}">
      <input type="hidden" name="loaded_version" value="{{ active_shift.version }}">
      {% if selected_card %}<input type="hidden" name="selected_card_id" value="{{ selected_card.id }}">{% endif %}
      <label class="shift-number-field">
        <span>Смяна</span>
        <select name="shift_number" data-shift-number-select>
          {% for shift_number in shift_options %}
            <option value="{{ shift_number }}"{% if shift_number == active_shift.shift_number %} selected{% if shift_number > shift_configuration.shift_count %} disabled{% endif %}{% endif %}>{{ shift_number }}</option>
          {% endfor %}
        </select>
      </label>
    </form>
    <div class="shift-current-status">
      <span class="shift-status-dot is-active" aria-hidden="true"></span>
      <strong>Активна</strong>
    </div>
    <div class="shift-start-time">
      <span>Начало</span>
      <time datetime="{{ active_shift.started_at }}">{{ active_shift.started_at_display }}</time>
    </div>
    <button class="shift-end-action" type="button"
            data-shift-confirm-open="end">Приключи смяната</button>
  </div>
</section>
```

Retain these hidden occurrence ID, loaded version, and selected-card ID fields exactly. Do not replace the constrained Jinja option loop with free-form input. Render the existing `shift_result` error block immediately after the current-shift card so stale/validation errors remain visible with `role="alert"`.

- [ ] **Step 6: Render the recent preview and full history as separate panes**

At the top of `_terminal_shift_window.html`, add:

```jinja2
{% set shift_history_url = shift_terminal_url ~ shift_query_prefix ~ "shift_view=history" %}
```

In the overview, loop over `recent_completed_shifts` and mark rows with `data-shift-history-preview-id`. Show shift number, formatted start, formatted end, distinct-item count, roll count, one-decimal gross kilograms, and `Преглед`. `Виж всички` uses `href="{{ shift_history_url }}"`.

The server-rendered `history` pane loops over all `completed_shifts`, uses `data-shift-history-id`, and has Bulgarian headers. Each `Преглед` link targets:

```text
<current terminal URL>?shift_view=summary&shift_id=<occurrence id>
```

The full history has a `Назад` link to `shift_view=overview`. Keep the table scrollable and newest-first; do not add filters.

- [ ] **Step 7: Render one localized production-summary pane**

Use `Произведени количества` as the static title. Render one metadata line/card with the shift number, `started_at_display`, and `ended_at_display`. Do not render `distinct_item_count` anywhere in the summary.

Use exact headings:

```html
<th>Производствена поръчка</th>
<th>Клиент</th>
<th>Вид изделие</th>
<th>Брой ролки</th>
<th>Бруто, кг</th>
```

Render `order.gross_weight_display`. A blocking handoff summary uses `Продължи`; a historical summary uses `Назад` and returns to `shift_view=history`.

- [ ] **Step 8: Update pane and close-button behavior**

Allow close only for nonblocking overview, history, and historical summary. Gate, start confirmation, end confirmation, blocking handoff summary, and reload remain nondismissible except through their explicit actions. Escape/backdrop must obey the same rule.

- [ ] **Step 9: Apply the approved hierarchy and responsive table styling**

Style the current card, active badge, history preview, full table, summary metadata, and summary table using existing terminal variables. Compact dialogs use `width: min(640px, calc(100vw - 32px))`; overview/history/summary use `width: min(1080px, calc(100vw - 32px))`. At the `max-height: 760px` breakpoint, reduce padding and make table bodies scroll rather than pushing actions below the viewport.

- [ ] **Step 10: Run focused route and render suites**

Run:

```bash
.venv/bin/python -m pytest tests/test_shift_routes.py tests/test_terminal_v8_render.py -q
```

Expected: all tests PASS.

- [ ] **Step 11: Commit the active/history/summary redesign**

```bash
git add app/templates/_terminal_shift_window.html app/templates/terminal.html \
  tests/test_terminal_v8_render.py tests/test_shift_routes.py
git commit -m "Redesign shift overview history and summaries"
```

---

### Task 5: Expand Fail-Closed Browser Verification And Visual Evidence

**Files:**
- Modify: `scripts/verify_shift_management_ui.mjs`
- Modify: `tests/test_shift_management_ui_script_safety.py`
- Modify: `app/templates/terminal.html` for geometry and responsive corrections discovered by browser comparison
- Modify: `app/templates/_terminal_shift_window.html` for state-layout corrections discovered by browser comparison

**Interfaces:**
- Consumes: stable `data-*` selectors from Tasks 2–4, repository-local Playwright, explicit `BASE_URL`, explicit `ARTIFACT_DIR`, and `shift-ui.sqlite3` inside that artifact directory.
- Produces: geometry assertions, persistence-boundary assertions, expanded screenshot evidence, zero browser errors, and unchanged SQLite integrity/foreign-key guarantees.

- [ ] **Step 1: Pin the expanded screenshot contract in the safety tests**

Add:

```python
def test_verifier_requires_every_shift_redesign_screenshot_name():
    script = VERIFICATION_SCRIPT.read_text(encoding="utf-8")
    required_names = (
        "terminal-header-no-active.png",
        "start-shift-selection.png",
        "start-shift-confirmation.png",
        "terminal-header-active.png",
        "active-shift-window.png",
        "full-shift-history.png",
        "ended-shift-summary.png",
        "historical-shift-summary.png",
    )

    for screenshot_name in required_names:
        assert f'"{screenshot_name}"' in script
```

- [ ] **Step 2: Run the safety test and confirm failure**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_shift_management_ui_script_safety.py::test_verifier_requires_every_shift_redesign_screenshot_name \
  -q
```

Expected: FAIL because the verifier still lists the original screenshot set.

- [ ] **Step 3: Add reusable header geometry and overflow assertions**

Add to the Playwright script:

```javascript
async function verifyTerminalHeader(page, expectedLabel, expectedActive) {
  const header = page.locator(".terminal-header");
  const actions = page.locator(".terminal-header-action");
  const centerNav = page.locator(".terminal-global-nav");
  await header.waitFor({ state: "visible" });
  assertEqual(await actions.count(), 3, "terminal header action count");

  const widths = [];
  for (let index = 0; index < await actions.count(); index += 1) {
    const box = await actions.nth(index).boundingBox();
    assert(box !== null, `Missing header action box ${index}`);
    widths.push(box.width);
    const fits = await actions.nth(index).evaluate((element) => ({
      horizontal: element.scrollWidth <= element.clientWidth,
      vertical: element.scrollHeight <= element.clientHeight,
      whiteSpace: getComputedStyle(element).whiteSpace,
    }));
    assert(fits.horizontal, `Header action ${index} overflows horizontally`);
    assert(fits.vertical, `Header action ${index} overflows vertically`);
    assertEqual(fits.whiteSpace, "nowrap", `Header action ${index} wrapping`);
  }
  assert(Math.max(...widths) - Math.min(...widths) <= 1, "Header action widths differ");

  const viewport = page.viewportSize();
  const centerBox = await centerNav.boundingBox();
  assert(viewport !== null && centerBox !== null, "Missing header center geometry");
  assert(
    Math.abs(centerBox.x + centerBox.width / 2 - viewport.width / 2) <= 2,
    "Order actions are not centered against the viewport",
  );

  const shiftAction = page.locator('[data-terminal-action="shift"]');
  assertEqual(normalizeText(await shiftAction.textContent()), expectedLabel, "shift header label");
  assertEqual(
    await shiftAction.locator(".shift-status-dot").evaluate((element) =>
      element.classList.contains("is-active")
    ),
    expectedActive,
    "shift header active-dot state",
  );
}
```

- [ ] **Step 4: Verify the live clock without delaying a full minute**

Add:

```javascript
async function verifyLiveClock(clock) {
  const before = await clock.getAttribute("datetime");
  const visible = normalizeText(await clock.textContent());
  const currentYear = String(new Date().getFullYear());
  const visiblePattern = new RegExp(
    `^\\d{1,2} [а-я]+ ${currentYear} г\\., \\d{2}:\\d{2}$`,
  );
  assert(visiblePattern.test(visible), "Bulgarian clock format");
  assert(!/\d{2}:\d{2}:\d{2}/.test(visible), "Visible clock must not show seconds");
  await clock.page().waitForTimeout(1100);
  const after = await clock.getAttribute("datetime");
  assert(before !== after, "Live clock datetime did not advance");
}
```

- [ ] **Step 5: Prove that only final confirmation persists the shift**

In `startShift()`:

1. Select the requested number.
2. Verify the gate live clock.
3. Click `Започни смяна`.
4. Verify the confirmation pane and its live clock.
5. Call `databaseSnapshot()` and assert `active_shift === null` and the occurrence count is unchanged.
6. Click `Потвърди`.
7. Wait for navigation and assert the active occurrence now exists with the selected number.

Do not submit or compare a browser-provided timestamp; the server remains authoritative.

- [ ] **Step 6: Update Bulgarian and navigation assertions**

Replace old `Shift`, `View`, `Back`, English table-heading, raw-timestamp, and distinct-item-summary assertions with the approved Bulgarian labels. Verify:

- `Виж всички` loads `shift_view=history` in the same modal.
- Full history contains all completed rows while the overview preview contains at most three.
- `Преглед` loads the selected summary.
- Historical `Назад` returns to `shift_view=history`.
- Handoff `Продължи` returns to the blocking start gate.
- Summary gross cells render one decimal place.
- The active header changes to `Смяна 2` after correction and the inactive header reads `Няма активна смяна` with a gray dot.

- [ ] **Step 7: Capture the expanded screenshot evidence**

Replace `screenshotNames` with:

```javascript
const screenshotNames = [
  "admin-shift-count.png",
  "terminal-header-no-active.png",
  "start-shift-selection.png",
  "start-shift-confirmation.png",
  "terminal-header-active.png",
  "active-shift-window.png",
  "full-shift-history.png",
  "ended-shift-summary.png",
  "historical-shift-summary.png",
];
```

Capture at `1536x1024` for the primary comparison. Repeat the header geometry and overflow assertions after resizing to `1366x768`, then restore the primary viewport before final screenshots.

- [ ] **Step 8: Run static and safety checks**

Run:

```bash
node --check scripts/verify_shift_management_ui.mjs
.venv/bin/python -m pytest tests/test_shift_management_ui_script_safety.py -q
```

Expected: both PASS.

- [ ] **Step 9: Run the full browser workflow against a new ignored temporary database**

Run this exact single-shell block so the temporary directory and server process remain scoped together:

```bash
mkdir -p artifacts/ui-checks
UI_REDESIGN_DIR="$(mktemp -d "$PWD/artifacts/ui-checks/shift-redesign-XXXXXX")"
EXTRUSION_DATA_DIR="$UI_REDESIGN_DIR" \
EXTRUSION_DB_PATH="$UI_REDESIGN_DIR/shift-ui.sqlite3" \
  .venv/bin/python -c "from app.db import init_db; init_db()"
EXTRUSION_DATA_DIR="$UI_REDESIGN_DIR" \
EXTRUSION_DB_PATH="$UI_REDESIGN_DIR/shift-ui.sqlite3" \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8011 \
  >"$UI_REDESIGN_DIR/server.log" 2>&1 &
UI_REDESIGN_SERVER_PID=$!
trap 'kill "$UI_REDESIGN_SERVER_PID" 2>/dev/null || true' EXIT
for attempt in $(seq 1 100); do
  if curl -fsS http://127.0.0.1:8011/health >/dev/null; then
    break
  fi
  sleep 0.1
done
curl -fsS http://127.0.0.1:8011/health >/dev/null
BASE_URL=http://127.0.0.1:8011 \
ARTIFACT_DIR="$UI_REDESIGN_DIR" \
  node scripts/verify_shift_management_ui.mjs
kill "$UI_REDESIGN_SERVER_PID"
wait "$UI_REDESIGN_SERVER_PID" || true
trap - EXIT
```

Expected: the verifier exits `0`, reports `integrity_check=ok`, reports zero foreign-key rows and zero browser errors, and lists every screenshot.

- [ ] **Step 10: Compare implementation screenshots with the supplied references**

Inspect the corresponding reference and implementation screenshots at full resolution:

```text
source-files/new-design.JPG
source-files/screen_start_shift.png
source-files/screen_start_shift_confirmation.png
source-files/main_shift_button.png
```

Correct visibly inconsistent width, whitespace, hierarchy, color, type scale, border radius, and button alignment while preserving the written overrides. Re-run the browser workflow after every material correction. Do not broaden the redesign to machine cards or selected-order content.

- [ ] **Step 11: Run the focused affected suite**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_shift_routes.py \
  tests/test_terminal_v8_render.py \
  tests/test_shift_management_ui_script_safety.py \
  tests/test_shift_management.py \
  tests/test_roll_entry.py \
  tests/test_admin_production_corrections.py \
  -q
```

Expected: all affected tests PASS.

- [ ] **Step 12: Commit the verified browser contract and any visual fixes**

```bash
git add scripts/verify_shift_management_ui.mjs \
  tests/test_shift_management_ui_script_safety.py \
  app/templates/terminal.html app/templates/_terminal_shift_window.html
git commit -m "Verify shift UI redesign in browser"
```

---

### Task 6: Final Review, Migration Assessment, Documentation, And Acceptance

**Files:**
- Modify: `docs/implementation-notes/shift-management.md`
- Modify: `v2-files/PLAN.md`
- Modify: `v2-files/AGENTS.md`
- Verify: all source and test files changed in Tasks 1–5

**Interfaces:**
- Consumes: completed UI commits, passing focused/browser checks, final diff, and user visual acceptance.
- Produces: reviewed final branch, current verification evidence, migration decision, durable notes, and accurate Task 01 status.

- [ ] **Step 1: Run a scoped code review before final verification**

Review the feature-base-to-HEAD diff for:

- accidental backend or schema changes;
- raw timestamps or two-decimal shift weights still rendered;
- English shift labels;
- a dismissible gate or blocking summary;
- duplicate shift-number correction controls;
- header label overflow/wrapping at both viewports;
- altered queue/produced overlay behavior;
- broken focus, Escape, backdrop, inert, polling, or stale-write behavior;
- unrelated machine-card or selected-order redesign.

Address substantive findings through the prescribed review/fix loop, then re-run the affected tests.

- [ ] **Step 2: Run final syntax and automated verification**

Run:

```bash
.venv/bin/python -m compileall app tests
node --check scripts/verify_shift_management_ui.mjs
.venv/bin/python -m pytest -q
git diff --check
```

Expected: all commands exit `0`; the full test count is at least the `547`-test baseline plus the new redesign tests.

- [ ] **Step 3: Re-run the browser verifier from a fresh temporary database**

Repeat Task 5 Step 9 with a new `mktemp` artifact directory. Confirm every screenshot exists, is nonempty, and visually shows the intended state.

- [ ] **Step 4: Perform the required migration decision procedure**

Inspect the actual final diff against `v2-files/AGENTS.md`.

If the diff changes only Python presentation helpers, templates, CSS/JavaScript, tests, browser verification, and documentation, append an assessment row with:

```text
Decision: No migration
Why: Shift UI layout, localized display formatting, and modal navigation only; M002 schema and stored meanings are unchanged.
Existing production data affected: none
Proposed migration: none
Transformation: no values changed
Unknowns or ambiguous rows: none introduced by this UI slice
Required tests: temporary-database render, workflow, browser, integrity, and foreign-key checks
Production snapshot needed now: No
Deployment constraint: existing M001 production profile and final release-candidate rehearsal remain required before deployment
```

If the final diff unexpectedly changes persistent structure or meaning, stop and run the full migration classification rather than recording `No migration` by assumption.

- [ ] **Step 5: Update the durable implementation note**

In `docs/implementation-notes/shift-management.md`, record:

- new header structure and state-aware shift label;
- compact gate and shared confirmation behavior;
- live preview versus authoritative confirmation timestamp;
- active overview, three-row preview, full history, and summary navigation;
- Bulgarian timestamp and one-decimal display rules;
- exact focused/full test counts;
- exact browser command and new screenshot paths;
- unchanged M001 and release-candidate deployment gates.

- [ ] **Step 6: Keep Task 01 status truthful pending user review**

Before user acceptance, update `v2-files/PLAN.md` to say the redesign is implemented and verified but awaiting final visual acceptance. Do not mark Task 01 complete merely because tests pass.

- [ ] **Step 7: Present the live UI and evidence for user acceptance**

Provide the normal LAN start command:

```bash
cd /home/sk/projects/extrusion-terminal && .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Identify the branch/worktree being shown and do not imply that the runtime database was used during automated verification. Ask the user to inspect the header, start selection, confirmation, active overview, full history, and produced-amount summary.

- [ ] **Step 8: Record completion only after explicit visual acceptance**

After the user accepts the live UI, update `v2-files/PLAN.md` and the status line in `v2-files/TASK-01-SHIFT-MANAGEMENT.md` to mark Task 01 complete while keeping the two production deployment gates separate and unresolved.

- [ ] **Step 9: Commit the final documentation after authorization**

```bash
git add docs/implementation-notes/shift-management.md \
  v2-files/PLAN.md v2-files/TASK-01-SHIFT-MANAGEMENT.md v2-files/AGENTS.md
git commit -m "Document accepted shift UI redesign"
```

- [ ] **Step 10: Finish the development branch**

Use `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch`. Do not push, deploy, merge, or open a pull request unless separately authorized.

---

## Final Acceptance Checklist

- [ ] Kolev logo is left aligned in a dedicated terminal header.
- [ ] `Чакащи поръчки` and `Произведени поръчки` are equal-size and centered against the viewport.
- [ ] The shift action is equal-size, right aligned, nonwrapping, and never overflows.
- [ ] No-active shift shows the inactive-machine gray dot and `Няма активна смяна`.
- [ ] Active shift shows a green dot and the corrected `Смяна N` label.
- [ ] The no-active gate has no close or cancel action.
- [ ] Start selection and confirmation show a live Bulgarian clock without seconds.
- [ ] No shift occurrence exists until final start confirmation.
- [ ] Start and end confirmation screens share the approved visual structure.
- [ ] Active overview shows the editable shift number, formatted start time, active state, and separate end action.
- [ ] No duration appears.
- [ ] Overview history shows at most three newest rows and `Виж всички`.
- [ ] Full history replaces the same modal contents and uses Bulgarian headings.
- [ ] Historical `Преглед` opens the correct live summary; `Назад` returns to full history.
- [ ] Handoff and historical summaries use `Произведени количества`.
- [ ] Summary does not show a distinct-item counter.
- [ ] Summary columns are Bulgarian and gross kilograms use one decimal place.
- [ ] Ending/changing a shift does not alter cards, machines, production timers, or roll attribution.
- [ ] Gate, focus, stale-page, polling, and concurrency safeguards still pass.
- [ ] Header geometry and label overflow pass at `1536x1024` and `1366x768`.
- [ ] Browser verification uses a temporary database and produces every required screenshot.
- [ ] Full pytest, compile, Node syntax, integrity, foreign-key, and diff checks pass.
- [ ] Final migration assessment is recorded from the actual diff.
- [ ] Task 01 is marked complete only after explicit user visual acceptance.
