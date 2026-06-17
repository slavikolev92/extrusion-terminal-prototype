# Workstation V8 Connection Plan

This plan is the execution handoff for connecting `ui-prototypes/workstation-v8.html` to the live `/terminal` route.

`README.md` remains the authoritative product specification. `IMPLEMENTATION_PLAN.md` remains the milestone tracker. This file is the detailed execution plan for the Workstation V8 connection milestone and should be updated as each slice completes.

## Goal

Replace the current temporary `/terminal` UI with the finalized Workstation V8 interface while preserving the existing backend workflow and production-data safety rules.

The connected workstation must:

- Use `ui-prototypes/workstation-v8.html` as the visual and interaction baseline.
- Render live server data from SQLite.
- Show four fixed machines and their current/next cards.
- Show active machine queues and completed-card lookup.
- Show the selected card details, recipe, material fields, tare/core weight, rolls, totals, and timing actions.
- Show `Макс. тегло ролка, кг` as read-only operator information.
- Keep cancellation and restore out of the workstation. Those remain admin/shift-manager actions.
- Preserve loaded-version conflict checks on every write.
- Avoid fake client-side card switching. Selecting a queue/completed row must load a full card state, not just change a title.

## Non-Goals

Do not include these in the V8 connection milestone:

- Print output implementation.
- Printable card template.
- New user/login/permission system.
- WebSockets, SSE, or background services.
- Drag-and-drop planning.
- Writing terminal data back to Excel.
- Reworking admin pages beyond what is necessary for the maximum-roll-weight data contract.
- Reintroducing workstation cancellation or restore controls.

## Starting Rules For The Next Session

At the start of any session executing this plan:

1. Read `AGENTS.md`.
2. Read `README.md`.
3. Read `IMPLEMENTATION_PLAN.md`.
4. Read this file.
5. Inspect:
   - `ui-prototypes/workstation-v8.html`
   - `app/templates/terminal.html`
   - `app/main.py`
   - `app/db.py`
   - `app/importer.py`
   - `app/static/css/app.css`
   - relevant tests under `tests/`
6. Run:

```powershell
git status --short
git log --oneline -8
```

If unrelated uncommitted changes exist, inspect and preserve them. Do not revert user work.

## Slice 1 - Data Contract For Maximum Roll Weight

Status: complete.

Purpose: make `Макс. тегло ролка, кг` real card data before the V8 template depends on it.

Clarification: this value is not imported from the Excel/CSV source. It is entered by the shift manager after import and before release.

### Required Work

1. Add a clear database field, recommended name:

```text
max_roll_weight
```

2. Add it to the `cards` schema in `app/db.py`.

3. Add a SQLite-safe migration for existing pilot databases.

Recommended approach:

- Keep `CREATE TABLE IF NOT EXISTS cards` updated for new databases.
- Add an idempotent helper such as `ensure_column(connection, "cards", "max_roll_weight", "TEXT")` or equivalent inside `init_db()`.
- Do not rely on `CREATE TABLE IF NOT EXISTS` alone because existing DBs will not gain new columns.

4. Keep it out of CSV import:

- do not include it in `IMPORT_FIELDS`
- do not include it in `FIELD_ALIASES`
- do not include it in `csv_template()`
- insert/update import paths must leave it blank/preserved
- re-import overwrite must preserve the shift-manager-entered value

5. Add it to shift-manager/admin entry paths:

- admin card detail imported-field form
- planning release form
- the value is optional; release must work when it is blank

6. Include it in card fetch helpers:

- `fetch_admin_card_detail()`
- `fetch_terminal_card_detail()`
- any list/helper used by the live V8 template if needed

7. Add/update tests:

- Import leaves `max_roll_weight` blank.
- Re-import preserves shift-manager-entered `max_roll_weight`.
- Re-import preserves production data: tare, rolls, timing, material corrections, status, machine assignment.
- Release works when `max_roll_weight` is blank.
- Release can save optional `max_roll_weight` from the planning form.
- Terminal detail fetch includes `max_roll_weight`.

### Verification

Run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest tests/test_baseline.py tests/test_admin_card_review.py tests/test_terminal_detail.py
git diff --check
```

### Checkpoint 1

Stop and review before continuing.

Review questions:

- Does `max_roll_weight` exist in both new and existing SQLite databases?
- Is it treated as shift-manager-entered card data, not CSV-imported data and not terminal-entered production data?
- Does re-import preserve it while preserving production data?
- Do tests cover the data contract?

Required checkpoint updates:

- Update this file: mark Slice 1 complete and record any deviations.
- Update `IMPLEMENTATION_PLAN.md` if the milestone tracker should mention that the max-roll-weight data contract is complete.
- Commit this slice before moving to Slice 2 if tests pass.

Checkpoint 1 result:

- `max_roll_weight` is present in the `cards` schema for new SQLite databases.
- Existing SQLite databases receive `cards.max_roll_weight` through an idempotent `init_db()` migration.
- Corrected after clarification: the field is shift-manager-entered card data, not CSV-imported data.
- CSV import leaves `max_roll_weight` blank and re-import preserves the shift-manager-entered value while preserving status, machine assignment, tare, rolls, timing, and terminal material corrections.
- Admin card detail and the planning release form can save optional `max_roll_weight`; release works when it is blank.
- Admin and terminal card detail fetches include `max_roll_weight`.
- Verification passed with the Slice 1 compile, focused pytest, and `git diff --check` commands.
- Deviation from the original Slice 1 wording: CSV import/template/aliases intentionally do not include `max_roll_weight`.

Recommended commit message:

```text
Add maximum roll weight data contract
```

## Slice 2 - Terminal Cancellation Cleanup

Status: complete.

Purpose: make the live operator route match the confirmed scope before the V8 connection.

### Required Work

1. Remove terminal cancellation routes from `app/main.py`:

- `POST /terminal/cards/{card_id}/cancel`
- `POST /terminal/cards/{card_id}/restore`

2. Keep admin cancellation routes:

- `POST /admin/cards/{card_id}/cancel`
- `POST /admin/cards/{card_id}/restore`

3. Ensure `app/templates/terminal.html` has no:

- cancel button
- restore button
- cancelled-card archive wording
- cancelled-card operator list

4. Decide whether `fetch_terminal_card_detail()` and `terminal_snapshot()` should still treat cancelled cards as terminal-visible.

Recommended behavior for the V8 workstation:

- Active terminal-visible statuses: `pending`, `running`, `paused`.
- Completed lookup: `completed`.
- Cancelled cards should be admin-visible, not workstation-visible.

If changing helper behavior now is low-risk, do it here. If not, do it in Slice 3 while wiring the V8 lists. Do not leave cancelled cards reachable by workstation links after Slice 4.

5. Update route tests:

- Assert terminal cancel/restore routes are absent.
- Assert admin cancel/restore routes remain present.

### Verification

Run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest tests/test_admin_routes.py tests/test_finish_cancel_history.py tests/test_admin_production_corrections.py
git diff --check
```

### Checkpoint 2

Stop and review before continuing.

Review questions:

- Can operators still cancel or restore from any terminal route or template?
- Do admin cancel/restore tests still pass?
- Are cancelled cards hidden from workstation-facing lists?
- Is the README/AGENTS wording still consistent with the implementation?

Required checkpoint updates:

- Update this file: mark Slice 2 complete and record helper behavior chosen for cancelled cards.
- Update `IMPLEMENTATION_PLAN.md` if cancellation cleanup is completed as part of the V8 connection milestone.
- Commit this slice before moving to Slice 3 if tests pass.

Recommended commit message:

```text
Remove workstation cancellation controls
```

Checkpoint 2 result:

- Removed the workstation POST routes `/terminal/cards/{card_id}/cancel` and `/terminal/cards/{card_id}/restore`.
- Kept the admin POST routes `/admin/cards/{card_id}/cancel` and `/admin/cards/{card_id}/restore`.
- Confirmed `app/templates/terminal.html` has no cancel button, restore button, cancelled-card archive wording, or cancelled-card operator list.
- Chosen helper behavior: cancelled cards are now hidden from workstation-facing detail/sync/archive helpers. `fetch_terminal_card_detail()` and `terminal_snapshot()` treat terminal-visible statuses as active (`pending`, `running`, `paused`) plus completed only. `/terminal` passes only completed cards to the completed-card archive context. `fetch_machine_queues()` was already active-status only and needed no change.
- Admin/history behavior remains available through admin detail and the existing admin cancel/restore routes.
- README, AGENTS, and IMPLEMENTATION_PLAN wording remains consistent; no updates were needed there.
- Verification passed:
  - `.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests`
  - `.\.test-runtime\codex-venv\Scripts\python.exe -m pytest tests/test_admin_routes.py tests/test_finish_cancel_history.py tests/test_admin_production_corrections.py`
  - `.\.test-runtime\codex-venv\Scripts\python.exe -m pytest tests/test_terminal_detail.py tests/test_terminal_sync.py`
  - `git diff --check`

## Slice 3 - Convert V8 Prototype Into Live Terminal Template

Status: complete.

Purpose: replace the temporary `/terminal` UI with a live server-rendered V8 layout.

This is the largest slice. Do not combine it with schema or cancellation route work.

### Required Work

1. Replace `app/templates/terminal.html` with a V8-based Jinja template.

Use `ui-prototypes/workstation-v8.html` as the source, but remove prototype-only demo state.

2. Keep the page server-rendered.

Avoid:

- client-side demo card switching
- hard-coded order data
- fake totals
- fake status/action state

3. Preserve the existing terminal sync banner behavior.

The existing polling behavior should remain:

- `/terminal/snapshot`
- auto-refresh only when no operator input is focused/dirty
- banner when updates arrive while input is active/dirty

4. Render top machine navigation from `machine_queues`.

Expected behavior:

- Always render four machines.
- Machine tile focus card should match backend focus-card behavior: running/paused card first, otherwise next pending by sequence.
- Selected machine/card should be visually obvious.
- Machine tile links should load the full selected card server-side.

5. Render selected card detail area.

Map V8 fields:

- `Вид изделие` -> `selected_card.product_type`
- `Фирма` -> `selected_card.customer`
- `Количество` -> quantity display helper from `quantity_1/unit_1` and optionally `quantity_2/unit_2`
- `Размер / дебелина` -> `selected_card.size_thickness`
- `Вид заготовка` -> likely `selected_card.product_form` or `selected_card.extrusion_folding`; confirm against README/source semantics before final mapping
- `Материал` -> `selected_card.material`
- `Макс. тегло ролка, кг` -> `selected_card.max_roll_weight`
- `Забележки` -> `selected_card.notes`

If there is uncertainty about `Вид заготовка`, stop at this mapping point and inspect README/source workbook notes. Do not guess if the source field is ambiguous.

6. Render recipe rows from `build_recipe_rows()` or a terminal equivalent.

Required rows:

- A
- B
- C
- Линеен
- Антистатик
- Мастербач
- Креда

Keep terminal-entered material fields separate from imported planned material fields.

7. Render roll panel.

Required:

- `Шпула, кг` field -> `tare_weight`
- `Нова ролка, кг` add form -> `gross_weight`
- roll list with existing gross values editable
- delete affordance only if still approved for workstation; if not, keep correction-only and leave deletion admin-only
- gross total
- net total
- remaining gross amount

Remaining gross amount should be calculated/displayed carefully. If there is no reliable target gross quantity, show `-` rather than false precision.

8. Render action buttons.

Status behavior:

- Pending: `Старт` enabled, `Пауза` disabled, `Приключи` disabled or backend-blocked according to confirmed workflow.
- Running: `Пауза` enabled, `Приключи` enabled.
- Paused: `Продължи` enabled, `Приключи` behavior follows existing backend finish rules.
- Completed: production actions disabled, reprint access visible in overflow.
- Cancelled: should not be shown on workstation.

Every write form must include:

```html
<input type="hidden" name="loaded_version" value="{{ selected_card.version }}">
```

9. Render queue drawer.

Expected:

- Group by `Машина 1` through `Машина 4`.
- Show compact rows with:
  - sequence
  - customer
  - order number
  - status
  - product/type
  - size/thickness
  - material
  - ordered kilograms
- Row click/link must load the full selected card server-side.
- Do not mutate production state from queue row click.

10. Render completed-card lookup.

Expected:

- Completed cards only.
- Search/filter by customer, product, size/thickness, material.
- Row click/link loads the full selected completed card server-side.
- Production actions disabled for completed cards.
- Reprint access visible in overflow, even if print route is a placeholder until Milestone 10.

11. Keep CSS maintainable.

Options:

- Keep V8 CSS inline inside `terminal.html` for the first connection, then extract later only if needed.
- Or move V8 CSS into `app/static/css/app.css` carefully.

Recommendation:

- Prefer keeping the V8-specific CSS in `terminal.html` during the first connection to reduce cross-page CSS regressions.
- Extract only after the live page is verified.

### Tests

Add or update focused render tests, likely in a new file:

```text
tests/test_terminal_v8_render.py
```

Tests should verify:

- `/terminal` route is registered.
- terminal cancel/restore routes are absent.
- rendered page includes four machine navigation controls.
- rendered page includes selected card details from DB data.
- rendered page includes `Макс. тегло ролка, кг` and the imported max value.
- rendered page includes queue drawer content for active cards.
- rendered page includes completed lookup content for completed cards.
- cancelled cards are not rendered in workstation queue/completed lookup.
- write forms include `loaded_version`.
- no `Анулирай`, `Cancel`, `Restore`, or terminal cancel/restore form action exists.

Avoid brittle full-HTML snapshot tests. Assert key strings/forms/links.

### Verification

Run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

Manual check is required if practical:

- Use a temporary database, not `data/extrusion_terminal.sqlite3`.
- Import/release at least two cards on one machine and one card on another.
- Open `/terminal`.
- Verify four machine nav tiles.
- Verify selected card details and max roll weight.
- Open queue drawer and select a pending row; verify full card changes, not only the title.
- Start, pause, resume, add tare, add roll, finish.
- Verify completed lookup shows completed card.
- Verify cancelled card, if created from admin, does not appear on workstation.

If browser/server launch is flaky, stop after one attempt and report the manual check as not completed. Do not repeatedly retry server launch attempts.

### Checkpoint 3

Stop and review before continuing.

Review questions:

- Does the live `/terminal` visually match V8 closely enough to be accepted as the final workstation UI?
- Does every visible field use live data?
- Is max roll weight visible and read-only?
- Are write forms version-protected?
- Is there any wrong-card data-entry risk?
- Are cancelled cards fully absent from workstation UI?
- Did the full test suite pass?
- Was the manual temporary-DB workflow completed?

Required checkpoint updates:

- Update this file with Slice 3 outcome and any known deviations.
- Update `IMPLEMENTATION_PLAN.md` to mark Workstation V8 connection complete only if tests and manual workflow pass.
- Update `AGENTS.md` current milestone state if this becomes the new committed baseline.
- Commit this slice before moving to Slice 4 if accepted.

Recommended commit message:

```text
Connect workstation V8 terminal UI
```

Checkpoint 3 result:

- Replaced the temporary `/terminal` layout with a live server-rendered V8 workstation template based on `ui-prototypes/workstation-v8.html`.
- `/terminal` now selects the first live machine focus card by default when one exists; direct machine, queue, and completed-card links load full server-rendered card state.
- Top machine navigation renders the four fixed machines from `machine_queues`, with running/paused focus preferred over pending and selected machine/card state visually emphasized.
- Queue and completed drawers are rendered from live data. Queue rows are navigation-only links grouped by machine. Completed lookup is filterable client-side over rendered completed rows.
- Cancelled cards remain absent from the workstation queue, completed lookup, selected-card detail, and terminal snapshot behavior. Workstation cancel/restore routes remain absent; admin cancel/restore routes remain available.
- Selected card details, recipe rows, material correction fields, tare/core weight, roll entry/correction, gross/net/remaining totals, timing actions, max roll weight, and update banner are live data.
- `Макс. тегло ролка, кг` is displayed read-only in the details pane and remains informational only.
- Remaining gross weight is shown only when `quantity_1` has a kg-style unit; otherwise the workstation shows `-`.
- Roll deletion remains supported by the backend route but is not exposed as a prominent V8 workstation control.
- Every workstation write form rendered by the template includes `loaded_version`.
- Print/reprint appears only as a disabled overflow placeholder; no print route, printable template, or print output was implemented.
- Verification passed:
  - `.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests`
  - `.\.test-runtime\codex-venv\Scripts\python.exe -m pytest`
  - `git diff --check`
- Manual temporary-DB browser check passed on `http://127.0.0.1:18080/terminal` using `.test-runtime\manual-v8\manual-v8.sqlite3`: verified four machine tiles, live selected card details, read-only max roll weight, queue row server-side selection, start/pause/resume/tare/roll/finish workflow, completed lookup, cancelled-card absence, disabled completed-card production actions, and no workstation cancel/restore controls.
- Deviation noted: the existing data model has one order-level terminal material/brand/batch correction set. The visible recipe table keeps the V8 four-column shape; the first row binds the real actual-material and batch inputs, the existing brand value is preserved as hidden form data, and the other recipe-row inputs are visual placeholders until per-component actual-material fields are confirmed.

## Slice 4 - Functional Hardening And Edge Cases

Purpose: fix issues found after the first live V8 connection without drifting into print output.

### Required Work

Address issues found at Checkpoint 3, likely in these areas:

- button disabled/enabled state mismatches
- paused/finished edge cases
- stale-write banner placement
- completed-card correction behavior
- roll list overflow and large roll counts
- empty queues and empty completed lookup
- text overflow on real terminal viewport
- route/render test gaps

Do not add new features unless they directly support the confirmed V8 workflow.

### Verification

Run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

Repeat the focused manual temporary-DB workflow if UI behavior changed.

### Checkpoint 4

Stop and review before print work.

Review questions:

- Is the workstation good enough to pilot before print?
- Are there any remaining operator safety risks?
- Is any remaining issue strictly print-related?
- Are docs aligned with implementation?

Required checkpoint updates:

- Update this file with Slice 4 outcome.
- Update `IMPLEMENTATION_PLAN.md`.
- Update `AGENTS.md` current milestone state.
- Commit any hardening changes.

Recommended commit message:

```text
Harden workstation V8 terminal workflow
```

## Final Acceptance Criteria Before Print

Before starting print output, all of these must be true:

- `max_roll_weight` exists in the database, shift-manager entry/release workflow, admin fetch, terminal fetch, and terminal UI.
- `/terminal` uses the V8 layout with live data.
- The terminal exposes no cancel/restore controls or routes.
- Cancelled cards do not appear in workstation queue/completed lookup.
- Queue row selection loads a full selected card state server-side.
- Completed row selection loads a full selected completed card state server-side.
- Every write action includes loaded-version conflict protection.
- Existing backend invariants still pass:
  - one running card per machine
  - finish validation
  - roll numbering
  - tare/net calculations
  - stale write blocking
  - terminal sync awareness
- Full test suite passes.
- `git diff --check` passes.
- A focused manual workflow against a temporary database has passed or is explicitly documented as not completed with a reason.
- `README.md`, `IMPLEMENTATION_PLAN.md`, `AGENTS.md`, and this file are aligned.

## Known Risks To Watch

- Do not accidentally reconnect V4 or use older prototypes.
- Do not reintroduce fake client-side card switching.
- Do not expose admin cancellation controls to operators.
- Do not let completed/cancelled archive behavior leak cancelled cards into the workstation.
- Do not treat maximum roll weight as validation; it is informational only for this pilot.
- Do not mutate the real runtime database during tests or manual checks unless explicitly instructed.
- Do not leave a large uncommitted pile across slices.
