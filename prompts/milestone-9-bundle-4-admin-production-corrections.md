# Milestone 9 Bundle 4 Prompt - Admin Workflow Controls And Production Corrections

You are continuing work on the extrusion terminal pilot repository at:

`C:\Users\slavi\Dropbox (Personal)\03 KolevOOD\7 Extrusion Terminal Prototype`

The user has approved moving to Milestone 9 Bundle 4: **Admin Workflow Controls And Production Corrections**.

This prompt is intended for a fresh Codex session with no prior conversation context. Read it fully, then read the required project files before editing.

## Goal

Complete the last functional pre-print workflow controls needed before print output work starts.

The shift-manager/admin side already supports:

- CSV import and overwrite behavior.
- Admin card index and imported/front-card detail editing.
- Planning/release/reassignment/resequencing.
- Terminal execution with timing, tare, rolls, finish/cancel/history.
- Terminal sync awareness so the terminal can notice admin planning changes.

Bundle 4 should add the simplest admin-side production correction controls:

- Admin reversible cancel/restore for terminal-visible cards.
- Admin correction of terminal-side material fields.
- Admin correction of order tare weight.
- Admin correction of roll gross weights.
- Admin correction of production timing segments.
- Loaded-version conflict checks on all admin correction forms.

This is still a bounded pilot. Keep the implementation direct, inspectable, server-rendered, and backed by explicit SQLite/database validation.

## Communication Constraint

Keep user-facing updates short. The user prefers concise answers and no long essays.

Use 30-second or lower timeouts for normal checks. Prefer direct code/template review and automated tests. Do not spend time on repeated browser/server launch attempts if they are flaky.

## Required First Reads

Read these files in this order:

1. `AGENTS.md`
2. `README.md`
3. `IMPLEMENTATION_PLAN.md`
4. `prompts/milestone-9-bundle-3-planning-reassignment-resequencing.md` if present
5. `prompts/milestone-9-terminal-sync-awareness.md` if present
6. this prompt

Pay special attention to these README sections:

- `Order Lifecycle And Access Model`
- `Terminal editable fields`
- `Conflict handling`
- `Printing Constraint`
- `Implementation Guardrails`

Then inspect these implementation files:

- `app/main.py`
- `app/db.py`
- `app/constants.py`
- `app/rules.py`
- `app/templates/admin_card_detail.html`
- `app/templates/admin_cards.html`
- `app/templates/admin_planning.html`
- `app/templates/terminal.html`
- `app/static/css/app.css`
- `tests/conftest.py`
- `tests/test_admin_card_review.py`
- `tests/test_admin_planning.py`
- `tests/test_admin_routes.py`
- `tests/test_terminal_detail.py`
- `tests/test_production_timing.py`
- `tests/test_roll_entry.py`
- `tests/test_finish_cancel_history.py`
- `tests/test_terminal_sync.py` if present

Do not rely on old conversation context. Current committed baseline is expected to include:

```text
93479fc Add terminal sync awareness
5da9a89 Normalize admin planning sequences
f44cadf Add admin planning reassignment
06a59c8 Complete admin card review cleanup
```

Run:

```powershell
git status --short
git log --oneline -8
```

If there are uncommitted changes, inspect and preserve them unless the user explicitly asks otherwise. At the time this prompt was created, these prompt files may exist as untracked files:

- `prompts/milestone-9-bundle-3-planning-reassignment-resequencing.md`
- `prompts/milestone-9-terminal-sync-awareness.md`
- `prompts/milestone-9-bundle-4-admin-production-corrections.md`

Do not delete or overwrite them.

## Current Context

Milestones 0 through 8 are complete. Milestone 9 is in progress.

Bundle 1 is complete:

- `/admin/import` handles CSV import.
- Import outcomes use Action/Message.
- Duplicate overwrite remains explicit.
- No-extrusion rows are reported and skipped without creating cards.

Bundle 2 is complete:

- `/admin/cards` exists.
- `/admin/cards/{card_id}` exists.
- Admin imported/front-card edits use loaded `version`.
- Admin imported/front-card edits preserve production data.
- The redundant `validation_status` UI/product concept was removed.

Bundle 3 is complete:

- `/admin/planning` supports release, reassignment, and resequencing.
- Release/reassignment/resequencing treat entered sequence as a target position.
- Active machine queues normalize to contiguous positions starting at `1`.
- Duplicate active sequence protection remains.
- Occupied-machine protection remains for running/paused cards.
- Planning mutations use loaded `version` conflict checks.

Terminal Sync Awareness is complete:

- `/terminal/snapshot` exists.
- `/terminal` polls for active queue and selected-card changes.
- Terminal auto-refreshes only when no operator input is focused or dirty.
- Terminal shows an updates-available banner while an operator is typing.
- Server-side `loaded_version` checks remain the authoritative stale-write protection.

Existing terminal production behavior:

- Operators can edit terminal material fields.
- Operators can edit tare weight.
- Operators can add, edit, and delete roll gross weights.
- Roll deletion renumbers remaining rolls.
- Net weights and totals are recalculated.
- Operators can start, pause, resume, finish, cancel, and restore cancelled cards.
- Completed/cancelled cards remain available for review and correction.
- Finish validation currently blocks completion unless tare, timing, and at least one gross roll exist.

Existing admin behavior:

- Admin detail shows card status, machine/sequence, timing, tare, rolls, and terminal material fields.
- Admin detail can edit imported/front-card fields only.
- Admin planning can release, reassign, and resequence active cards.
- Admin cannot yet correct terminal-side production data.
- Admin cannot yet cancel/restore from the admin side.

## Scope

Implement only Bundle 4: admin workflow controls and production-data correction.

Required behavior:

1. Add admin-side reversible cancel/restore controls.
2. Add admin-side terminal material correction.
3. Add admin-side tare correction.
4. Add admin-side roll gross-weight correction.
5. Add admin-side roll deletion if it can reuse the same business rules as terminal roll deletion.
6. Add admin-side production timing segment correction.
7. Use loaded `version` conflict checks for every admin correction form.
8. Preserve finish/print-readiness invariants for completed cards.
9. Add focused automated tests.
10. Update `IMPLEMENTATION_PLAN.md` and docs with a short note.

## Non-Scope

Do not implement:

- Print output.
- Printable card template.
- Admin user accounts, permissions, roles, or login.
- Drag-and-drop timing or queue editing.
- WebSockets, SSE, background services, or real-time multi-user coordination.
- Complex merge tooling for conflicts.
- Audit trail/user attribution.
- Shift tracking.
- Downtime/performance tracking.
- Writing terminal-entered data back to Excel.
- Non-extrusion workflows.
- Permanent ERP features.

Bundle 4 is about correction controls only. Milestone 10 handles print output.

## Backend Behavior Requirements

Use existing database/business-rule patterns in `app/db.py`. Prefer direct helpers returning `RuleResult`.

### General Rules

- Every production-data correction must increment `cards.version` and update `cards.updated_at`.
- Every correction must require and validate `loaded_version`.
- Stale edits must return the existing stale message:
  - `Card changed after this page was loaded. Reload the card and try again.`
- Admin correction helpers must preserve imported/front-card fields unless the helper is specifically editing imported fields.
- Terminal-side helper behavior should remain unchanged unless you deliberately share/reuse it.
- Do not silently discard roll or timing data.
- Do not mutate the real runtime database in tests.

### Admin Cancel/Restore

Add admin-side actions that reuse the same business rules as terminal cancel/restore where practical:

- Cancelling active terminal cards changes status to `cancelled`.
- Cancelling a running card closes an open timing segment with the existing correction/cancel behavior.
- Cancelled cards remain visible in admin detail/history.
- Restoring a cancelled card changes it back to `pending`.
- Restore must preserve duplicate active machine-sequence protection.
- Restore must preserve occupied-machine/running-card constraints where current terminal restore rules already enforce them or where needed for consistency.
- Stale loaded versions must be blocked.

Potential route shape:

```python
POST /admin/cards/{card_id}/cancel
POST /admin/cards/{card_id}/restore
```

Reuse `cancel_card()` and `restore_cancelled_card()` if their messages and rules are suitable for admin. If you add admin-specific wrappers, keep them thin and tested.

### Admin Material Correction

Admin should be able to correct the same terminal material fields:

- `actual_raw_material_used`
- `raw_material_brand_grade`
- `raw_material_batch_lot`

Use the same validation and storage behavior as terminal material edits unless a stronger admin-specific rule is already documented. These fields should be editable for terminal-visible statuses: active and archive statuses.

Potential route shape:

```python
POST /admin/cards/{card_id}/production-materials
```

### Admin Tare Correction

Admin should be able to correct order-level tare weight.

Reuse existing tare validation where practical:

- Blank clears tare if current backend behavior allows it.
- Non-negative number.
- At most two decimal places.
- Tare cannot be greater than an existing gross roll weight because that would make net weight negative.
- Recalculate net weights for existing gross rolls.
- Increment card version.
- Stale loaded version blocks.

Potential route shape:

```python
POST /admin/cards/{card_id}/tare
```

### Admin Roll Correction

Admin should be able to correct roll gross weights from the card detail page.

Required:

- Edit existing roll gross weights.
- Add a new roll gross weight if it can reuse existing roll-entry rules cleanly.
- Delete an existing roll if it can reuse existing delete behavior cleanly.
- Roll numbers remain per card starting at `1`.
- Deleting rolls renumbers remaining rolls.
- Gross weights support up to two decimal places.
- Net weights are recalculated from current tare.
- Stale loaded version blocks.

Important rule:

- Completed cards must remain print-ready. Do not allow admin corrections that leave a completed card without at least one gross roll, with empty roll gaps, or with invalid net weights.

Existing terminal helpers may already enforce much of this:

- `add_roll_gross_weight`
- `update_roll_gross_weight`
- `delete_roll_entry`
- `update_tare_weight`

It is acceptable to reuse these for admin forms if the status restrictions match confirmed scope. If a terminal helper blocks an admin correction that the README clearly says admin should allow, add a small explicit admin helper with tests rather than weakening terminal behavior accidentally.

Potential route shape:

```python
POST /admin/cards/{card_id}/rolls
POST /admin/cards/{card_id}/rolls/{roll_id}
POST /admin/cards/{card_id}/rolls/{roll_id}/delete
```

### Admin Timing Segment Correction

Implement the simplest timing correction workflow needed before print:

- Admin can edit existing timing segments:
  - `started_at`
  - `ended_at`
  - `end_reason`
- Admin can add a timing segment if needed for correction.
- Admin can delete a timing segment if needed for correction and it does not violate completed-card print-readiness invariants.
- Total production time recalculates from the stored segments, as it already does.
- Prevent invalid intervals:
  - `ended_at` cannot be earlier than `started_at`.
  - `started_at` is required.
  - `end_reason` must be blank only for an open segment, or one of existing allowed values: `pause`, `finish`, `correction`.
  - If `ended_at` is blank, `end_reason` must be blank.
  - If `ended_at` is present, `end_reason` must be present and valid.
- Prevent more than one open timing segment per card.
- Preserve the existing SQLite unique open-segment protection.
- Completed cards must remain print-ready:
  - Do not allow deleting all timing history from a completed card.
  - Do not allow completed cards to have an open segment.
  - Do not allow correction that makes total production time impossible/invalid.
- Stale loaded version blocks.

Keep datetime input simple. Prefer a local form field format compatible with current stored values, for example `YYYY-MM-DD HH:MM:SS`, unless existing template/input conventions suggest otherwise. Do not build timezone conversion or complex date pickers.

Potential route shape:

```python
POST /admin/cards/{card_id}/timing-segments
POST /admin/cards/{card_id}/timing-segments/{segment_id}
POST /admin/cards/{card_id}/timing-segments/{segment_id}/delete
```

Suggested helper names:

```python
update_timing_segment(...)
add_timing_segment(...)
delete_timing_segment(...)
```

or admin-prefixed variants if you need to distinguish admin correction rules from terminal execution rules.

## UI Requirements

Update `app/templates/admin_card_detail.html`.

Keep the admin detail page work-focused and compact. Do not build a dashboard or a large new navigation concept.

Add correction controls near the existing read-only production data sections:

- Workflow/status controls:
  - Show `Cancel` for active cards where cancellation is allowed.
  - Show `Restore` for cancelled cards.
- Terminal material fields:
  - Small form with actual material, brand/grade/mark, and batch/lot.
- Tare:
  - Small numeric form.
- Rolls:
  - Existing rolls with gross-weight inputs and save/delete buttons.
  - Add-roll form.
  - Show totals after correction.
- Timing:
  - Existing timing segments with editable start/end/reason inputs.
  - Add segment form.
  - Delete segment button if safe.
  - Show total production time.

Every form must include:

```html
<input type="hidden" name="loaded_version" value="{{ card.version }}">
```

Result messages should be clear and near the relevant admin detail area. It is acceptable to use one or more existing `.notice` blocks at the top of the admin detail page if that matches the existing pattern.

Do not add explanatory in-app text about implementation details, conflict detection, or pilot architecture.

## CSS

Add only minimal styling in `app/static/css/app.css`.

Reuse existing patterns:

- `.section`
- `.notice`
- `.detail-grid`
- `.compact-table`
- `.field-form`
- `.admin-review-grid`
- `.pill`

Only add small admin correction form/table styles if the existing CSS cannot keep controls readable.

## Tests

Add focused automated tests. A new file such as `tests/test_admin_production_corrections.py` is appropriate.

Do not add new dependencies. Avoid FastAPI `TestClient` if the current project avoids it.

Recommended tests:

1. Admin cancel moves an active card to `cancelled`, closes open timing if running, increments version, and blocks stale loaded versions.
2. Admin restore returns a cancelled card to `pending`, preserves duplicate active sequence protection, increments version, and blocks stale loaded versions.
3. Admin material correction updates terminal material fields and blocks stale loaded versions.
4. Admin tare correction recalculates roll net weights and blocks invalid tare/stale versions.
5. Admin roll add/update/delete reuses roll numbering and net-total behavior; completed-card final gross roll protection remains.
6. Admin timing segment edit recalculates total production time.
7. Admin timing correction rejects invalid intervals and multiple open segments.
8. Admin timing correction blocks deleting all timing from a completed card.
9. Admin correction route registration includes all new admin correction routes.
10. Existing terminal behavior tests still pass unchanged.

Use temporary SQLite database fixtures only. Do not mutate `data/extrusion_terminal.sqlite3`.

If testing async routes directly is simple, use `asyncio.run(...)` as existing route tests do. Otherwise test DB helpers directly and route registration separately.

## Documentation Updates

Update `IMPLEMENTATION_PLAN.md`:

- Mark Bundle 4 as done when implementation, tests, and manual check are complete.
- Keep Bundle 5/pre-print workflow walkthrough as the next intended Milestone 9 step.
- Do not mark Milestone 9 complete unless the walkthrough bundle is also done and accepted.

Update `README.md` only if needed to clarify current behavior:

- Admin can now cancel/restore cards.
- Admin can now correct terminal-side material, tare, rolls, and timing from card detail.
- Loaded-version checks still block stale admin corrections.

Update `AGENTS.md` only if the current milestone state needs to be made clear for future agents. Do not change project scope there unless the user confirms a scope change.

## Verification Commands

Run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

Manual UI check is required if practical, using a temporary database:

1. Start the app against a temporary database.
2. Import/release a card.
3. Start timing, add tare, add at least one roll, and finish it.
4. Open `/admin/cards/{card_id}`.
5. Correct material fields, tare, a roll gross weight, and a timing segment.
6. Verify totals and total duration update.
7. Cancel and restore from admin where applicable.
8. Verify stale-version conflicts by submitting a form after changing the card elsewhere, or document why this was covered only by automated tests.

If browser/server launch is flaky, stop after one attempt and report that manual UI check was not completed.

## Review Checklist

Before committing, review the changed code for:

- data integrity
- stale-version checks on every admin correction
- preservation of imported/front-card data during production corrections
- completed-card print-readiness invariants
- no accidental weakening of terminal execution rules
- direct workflow behavior in `/admin/cards/{card_id}`
- no print output or out-of-scope features

## Commit Guidance

This bundle should be committed separately from terminal sync awareness and print output.

Before committing, run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

Use a focused commit message such as:

```text
Add admin production corrections
```

If `.git` writes require escalation, request approval for the exact Git action. Do not use destructive Git commands.

## Final Response Expectations

Keep the final answer short:

- what Bundle 4 behavior was added
- what validation/conflict protections remain
- tests passed
- manual check status
- commit hash if committed
