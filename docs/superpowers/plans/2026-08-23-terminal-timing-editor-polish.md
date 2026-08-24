# Terminal Timing Editor Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the accepted timing-entry behavior while giving the interval editor a coherent, compact layout and replacing the pending-delete/Undo interaction with a nested neutral in-app, draft-only deletion confirmation.

**Architecture:** Keep the existing timing ledger, routes, validation, and save transactions unchanged. Extend the existing pure JavaScript draft helpers only enough to derive visible rows and deletion eligibility, manage the small nested confirmation in the existing editor controller/template, and keep the visual refinement in the current terminal template CSS. The existing Playwright fixture and verifier remain the end-to-end evidence path.

**Tech Stack:** FastAPI/Jinja, plain JavaScript ES modules, CSS, Node's built-in test runner, pytest, and repository-local Playwright.

**Spec:** `docs/superpowers/specs/2026-08-21-terminal-timing-correction-design.md`

## Global Constraints

- Work in `/home/sk/projects/extrusion-terminal/.worktrees/terminal-timing-correction`.
- Do not change `app/db.py`, `app/main.py`, the schema, migrations, or any request/response contract for this refinement.
- Do not change the existing Start, Pause/Resume, Finish, roll, tare, rewinding, or menu behavior.
- Do not alter the accepted Finish Review structure or behavior.
- Preserve the working segmented date and time input logic, including click-to-select, auto-advance, numeric masking, validation, focus retention, and live preview.
- Keep the accepted timestamp control widths: date `120px`, time `78px`.
- Use the approved nested neutral in-app confirmation above the unchanged timing editor. Keep its state and focus trap local to the existing controller; do not add a component framework or abstraction.
- A confirmed deletion remains a draft change until the existing Save operation succeeds. Editor Cancel/Escape must leave the database unchanged.
- All date/time inputs and dismissal controls remain interaction-locked while ordinary Save or Finish Apply is pending, without disabling successful form fields; an asynchronous Apply failure restores editing.
- Keep all test and browser data under `.test-runtime/`; never use `data/extrusion_terminal.sqlite3`.
- Save browser evidence under `artifacts/ui-checks/`; keep it untracked.
- Do not stage or commit. The repository requires explicit user permission for either action.

---

## Task 1: Make Visible-Row And Delete Eligibility Rules Explicit

**Files:**

- Modify: `tests/js/timing_interval_editor_core.test.mjs`
- Modify: `app/static/js/timing_interval_editor_core.mjs`

**Interfaces:**

```javascript
visibleTimingRows(rows)
// -> [{ row, sourceIndex }]
// Omits deleted rows, preserves sourceIndex for serialization/error mapping,
// and assigns contiguous row.display_number values to the visible copies.

canDeleteTimingRow(rows, sourceIndex, { mode, status })
// -> boolean
// False for a missing/deleted row, the only visible row, and the final open
// interval in an ordinary running editor; true for other editable rows.
```

- [ ] Replace the existing Undo-oriented unit test with failing tests proving all of the following:

  - `markIntervalDeleted()` keeps an existing row in the draft with `deleted: true`;
  - `serializeTimingDraft()` still serializes that existing deleted row;
  - an unsaved deleted row is removed entirely;
  - `visibleTimingRows()` omits deleted rows without changing the original source indexes and gives the remaining rows contiguous visible numbers;
  - `canDeleteTimingRow()` rejects the ordinary running final interval and any sole visible interval, but allows another visible row.

- [ ] Run the focused red tests and confirm they fail because the new helpers do not exist:

  ```bash
  node --test --test-name-pattern='delete|visible row' tests/js/timing_interval_editor_core.test.mjs
  ```

- [ ] Implement `visibleTimingRows()` and `canDeleteTimingRow()` as pure functions beside `markIntervalDeleted()`. Do not mutate the input array or its row objects.

- [ ] Remove `undoIntervalDelete()` and its test import. It has no remaining product behavior after the confirmed-delete design and retaining it would be dead maintenance surface.

- [ ] Run the focused tests, then the whole core suite:

  ```bash
  node --test --test-name-pattern='delete|visible row' tests/js/timing_interval_editor_core.test.mjs
  node --test tests/js/timing_interval_editor_core.test.mjs
  ```

- [ ] Review the diff for this task. It must contain only pure draft/view derivation changes and tests; do not stage or commit.

---

## Task 2: Replace Pending Delete/Undo With Nested In-App Draft Confirmation

**Files:**

- Modify: `scripts/verify_terminal_timing_correction_ui.mjs`
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `app/static/js/timing_interval_editor.mjs`
- Modify: `app/templates/terminal.html` only to remove obsolete pending-delete/Undo CSS and expose the neutral action styling needed by this task

**Behavioral contract:**

```text
Button text: Изтрий
Accessible name: Изтрий интервал N
Confirmation: Сигурни ли сте, че искате да изтриете интервал №N?
Dismiss confirmation by Cancel, Escape, or backdrop: draft and database unchanged; initiating Delete focus restored
Accept confirmation: row hidden, database unchanged until Save
Cancel editor after acceptance: database unchanged
Save after acceptance: existing atomic save persists the deletion
```

- [ ] Update the Playwright ordinary-running workflow first so it expects the nested in-app confirmation. Add separate checks that Cancel, Escape, and backdrop dismissal keep the row and restore initiating focus, accepting hides the row, the confirmation traps keyboard focus, and none of those paths sends a timing-ledger Save request.

- [ ] In the same verifier, add coverage that:

  - visible row numbers remain contiguous after a confirmed deletion;
  - the next valid editor control receives focus after the deleted button disappears;
  - the final open row of a running card has no Delete button;
  - the only row of a paused-card draft has no Delete button;
  - accepting a deletion and then cancelling the editor leaves the database snapshot unchanged;
  - accepting a deletion and pressing Save persists exactly that deletion through the existing atomic endpoint.

- [ ] Update `test_terminal_timing_dialog_matches_approved_v2_contract` so it stops requiring `undoIntervalDelete`, the `×`/`Отмяна` branch, and the `pending-delete` state. Require the neutral `Изтрий` label and the exact confirmation text. Keep this pytest assertion limited to the rendered/source contract; interaction remains Playwright's responsibility.

- [ ] Run the focused tests against the current implementation and confirm failure:

  ```bash
  .venv/bin/python -m pytest tests/test_terminal_v8_render.py::test_terminal_timing_dialog_matches_approved_v2_contract -q
  node --test tests/js/timing_interval_editor_core.test.mjs
  ```

- [ ] Update `renderRows()` to iterate over `visibleTimingRows(state.rows)` while retaining the original `sourceIndex` for field edits, preview errors, and serialization.

- [ ] Render a neutral `Изтрий` button only when `canDeleteTimingRow(...)` returns true. Do not render a disabled placeholder button for protected rows.

- [ ] On click, open the nested confirmation with the exact approved title,
  prompt, and neutral actions without rerendering the editor. Dismissal makes no
  state change. Acceptance closes the confirmation, calls the existing
  `markIntervalDeleted()`, clears invalidated calculations and alerts,
  rerenders, updates the hidden draft field, and requests a preview only when
  the remaining draft is complete.

- [ ] After an accepted deletion, restore focus in this order: the next visible row's Delete action, the previous visible row's Delete action, then Add Interval. This avoids leaving focus on a DOM node that was removed.

- [ ] Remove the `undoIntervalDelete` import and all pending-delete/Undo controller branches and CSS. Keep only the small transient nested-confirmation state required for dismissal, focus restoration, and acceptance.

- [ ] Run the focused JS and render suites:

  ```bash
  node --test tests/js/timing_interval_editor_core.test.mjs
  .venv/bin/python -m pytest tests/test_terminal_v8_render.py -q
  ```

- [ ] Start or reuse one FastAPI process against the temporary fixture and run the deletion portion of the Playwright verifier. If the verifier has no focused flag, run the complete script rather than adding a second temporary harness.

- [ ] Review this task's diff for accidental backend, lifecycle-button, Finish Review, or input-control changes; do not stage or commit.

---

## Task 3: Rebalance The Timing Editor As One Coherent Visual Pass

**Files:**

- Modify: `app/templates/terminal.html`
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `scripts/verify_terminal_timing_correction_ui.mjs`

**Accepted layout targets:**

- dialog width: `min(1040px, calc(100vw - 40px))`;
- dialog height: content-based, capped at `min(728px, calc(100vh - 40px))`;
- interval-list maximum: `min(430px, calc(100vh - 338px))`, with the list as the only scrolling area;
- interval row: approximately `72px` minimum height with `8px 24px` padding;
- columns: `48px minmax(0, 1fr) minmax(0, 1fr) 150px 96px`;
- timestamp controls: centered `120px 78px` columns with an `8px` gap;
- Delete action: neutral table colors, at least `72px × 40px`, no red emphasis;
- subtle existing vertical separators remain;
- no structural or visual change to Finish Review.

- [ ] Extend the render contract test first to reject a fixed dialog height and require the content-based maximum, compact row geometry, `96px` action column, and neutral text-button sizing.

- [ ] Extend the Playwright verifier before changing CSS with a short-ledger layout check at `1366×768`:

  - the two/three-row dialog is materially shorter than the `728px` cap;
  - the interval list is content-fitting and has no large empty scroll region;
  - date and time controls remain exactly `120px` and `78px` and centered;
  - the Delete target meets the minimum dimensions;
  - all columns, separators, alert area, totals, and footer remain aligned and unclipped.

- [ ] Retain and strengthen the existing 18-row check: the dialog stays at or below `728px`, the row list scrolls internally, and the title/totals/headings/footer do not move when the list scrolls.

- [ ] Add screenshot targets for the normal short-ledger editor at `1366×768` and `1920×1080`, while retaining the validation, time-selection, many-row, and Finish Review evidence.

- [ ] Run the render test and the live verifier against the current CSS and confirm the new adaptive-height assertions fail.

- [ ] In `.timing-dialog`, remove the fixed `height`, preserve the maximum height and viewport margin, and keep the grid constrained so only `.interval-scroll` can overflow.

- [ ] Apply the accepted row, column, and action dimensions. Remove excess vertical whitespace while retaining comfortable click targets and centered timestamp controls.

- [ ] Treat the segmented date as one field visually: keep the existing five-part DOM and selection behavior, but rebalance segment columns, separator weight/spacing, font size, and padding so `DD/MM/YYYY` reads as a cohesive value rather than disconnected boxes.

- [ ] Keep the time input visually equal in height and typography to the date control. Do not change its masking or selection listeners.

- [ ] Re-run the focused render, JS, and live browser checks:

  ```bash
  .venv/bin/python -m pytest tests/test_terminal_v8_render.py -q
  node --test tests/js/timing_interval_editor_core.test.mjs
  BASE_URL=http://127.0.0.1:8015 \
  FIXTURE_JSON=.test-runtime/terminal-timing-audit/run-cUfFjf/fixture.json \
  ARTIFACT_DIR=artifacts/ui-checks/terminal-timing-editor-polish \
  node scripts/verify_terminal_timing_correction_ui.mjs
  ```

- [ ] Inspect every new screenshot directly, not only its numeric assertions. At both viewports confirm: no large dead area, no clipped text, centered inputs, cohesive dates, aligned rows/columns, neutral Delete actions, stable validation layout, many-row scrollbar, and unchanged Finish Review.

- [ ] If inspection reveals a defect, add a measurable regression assertion when practical, make the smallest CSS correction, rerun the verifier, and inspect the replacement screenshot before continuing.

- [ ] Review the task diff for any accidental JavaScript behavior change; do not stage or commit.

---

## Task 4: Full Regression And Visual Audit

**Files:**

- Modify after successful verification: `docs/implementation-notes/terminal-timing-correction.md`
- Review only: all files changed by Tasks 1–3 plus the pre-existing timing-correction feature diff

- [ ] Recreate the deterministic fixture if its state was changed by earlier browser runs:

  ```bash
  EXTRUSION_DB_PATH=.test-runtime/terminal-timing-audit/run-cUfFjf/fixture.sqlite3 \
  .venv/bin/python scripts/create_terminal_timing_correction_fixture.py \
    --db-path .test-runtime/terminal-timing-audit/run-cUfFjf/fixture.sqlite3 \
    --output .test-runtime/terminal-timing-audit/run-cUfFjf/fixture.json
  ```

- [ ] Ensure exactly one local Uvicorn process serves port `8015`, and that `/health` reports the resolved temporary fixture path before browser verification. Do not start a second server when the existing one is correct.

- [ ] Run all focused feature checks:

  ```bash
  node --test tests/js/timing_interval_editor_core.test.mjs
  .venv/bin/python -m pytest \
    tests/test_terminal_timing_correction.py \
    tests/test_terminal_v8_render.py \
    tests/test_terminal_sync.py \
    tests/test_terminal_timing_correction_ui_script_safety.py -q
  ```

- [ ] Run the complete live Playwright verifier against the reset fixture and a clean `artifacts/ui-checks/terminal-timing-editor-polish/` evidence directory.

- [ ] Inspect all generated screenshots with the image viewer. The audit is not complete until the visual result itself—not only selectors and dimensions—looks coherent at `1366×768` and `1920×1080`.

- [ ] Manually exercise in the live app: date selection, time selection, incomplete input, future-date correction, Add Interval placement, confirmation dismissal, confirmed draft deletion, editor Cancel, ordinary Save, Finish → Edit → Cancel → Finish Review, and many-row scrolling.

- [ ] Run the repository-wide regression and whitespace checks:

  ```bash
  .venv/bin/python -m pytest -q
  git diff --check
  ```

- [ ] Review the complete diff for data integrity, validation messages, preservation of existing production data, `/admin` and `/terminal` regressions, and scope compliance. Specifically confirm that no schema, migration, backend route, modal beyond the approved nested deletion confirmation, new dependency, or unrelated refactor was introduced.

- [ ] Update `docs/implementation-notes/terminal-timing-correction.md` to replace the obsolete pending-delete/Undo description with the confirmed draft-deletion behavior and record the exact final verification commands and artifact paths.

- [ ] Reset the temporary fixture once more and leave exactly one server on port `8015` for user review.

- [ ] Report the result with links to the changed files and evidence. Do not stage or commit unless the user gives separate explicit permission.

---

## Post-review Follow-up — Outstanding Before Merge

Independent code review of `4433b57..66bbc5b` found no critical issues and
identified these two important edge cases. Both were resolved and
regression-tested by the terminal timing confidence audit before merge:

- [x] Preserve and display the operator's locked timing draft when a stale Save
  or Finish submission is rejected after the card changes from running/paused
  to completed or cancelled in another tab or by an admin. The rejected write
  must not mutate production data, and the submitted draft must not disappear
  from the response.

- [x] Keep interval rows and Finish boundaries chronologically consistent when
  edited timestamps cause two valid, non-overlapping intervals to exchange
  order. The displayed numbering, first/last boundaries, production total, and
  paused total must all describe the same chronological ledger, including on a
  rejected Finish submission.
