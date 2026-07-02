# Full Readiness Audit - 2026-07-02

## Scope

Audit target: current FastAPI + SQLite extrusion terminal pilot in `/home/sk/projects/extrusion-terminal`.

Audit method:

- Ran existing automated test suite before changes.
- Spawned four read-only audit agents for terminal/workstation, admin/import/planning, database integrity, and UX/accessibility evidence planning.
- Seeded a disposable audit database at `.test-runtime/audit-2026-07-02/extrusion_audit.sqlite3`.
- Started the app against that temporary database only.
- Ran Playwright against `http://127.0.0.1:8010`.
- Captured screenshots and notes under `artifacts/ui-checks/audit-2026-07-02/`.

The real runtime DB at `data/extrusion_terminal.sqlite3` was not used.

## Evidence

Screenshots:

- `artifacts/ui-checks/audit-2026-07-02/01-terminal-initial.png`
- `artifacts/ui-checks/audit-2026-07-02/02-terminal-queue-drawer.png`
- `artifacts/ui-checks/audit-2026-07-02/03-terminal-produced-filter.png`
- `artifacts/ui-checks/audit-2026-07-02/04-terminal-invalid-roll-decimals.png`
- `artifacts/ui-checks/audit-2026-07-02/05-terminal-tare-enter-save.png`
- `artifacts/ui-checks/audit-2026-07-02/06-terminal-add-roll-success.png`
- `artifacts/ui-checks/audit-2026-07-02/07-terminal-paused-roll-blocked.png`
- `artifacts/ui-checks/audit-2026-07-02/08-admin-planning.png`

Notes:

- `artifacts/ui-checks/audit-2026-07-02/playwright-notes.md`

Audit tooling:

- `artifacts/ui-checks/audit-2026-07-02/seed_audit_db.py`
- `artifacts/ui-checks/audit-2026-07-02/playwright_audit.mjs`

## Verification Run

Baseline before fixes:

- `.venv/bin/python -m compileall app` passed.
- `git diff --check` passed.
- `.venv/bin/python -m pytest` passed with `422 passed`.

Final verification after fixes:

- `.venv/bin/python -m compileall app` passed.
- `git diff --check` passed.
- `.venv/bin/python -m pytest` passed with `432 passed`.
- `node artifacts/ui-checks/audit-2026-07-02/playwright_audit.mjs` passed against the temporary audit DB.

## Fixed During Audit

### 1. Active Queue Gaps After Finish, Cancel, And Restore

Severity: High.

Problem: `finish_card()` and `cancel_card()` moved a card out of the active queue without normalizing the remaining machine queue. `restore_cancelled_card()` restored the old sequence directly and could either block unnecessarily or reintroduce gaps.

Fix:

- `finish_card()` and `cancel_card()` now normalize the affected machine queue after status change.
- `restore_cancelled_card()` now treats the stored sequence as a target insertion position and shifts active cards as needed.
- Added regression tests for finish, cancel, and restore queue normalization.

### 2. Terminal Direct POST Against Archived/Cancelled Cards

Severity: High.

Problem: The terminal UI hid archived/cancelled cards, but direct `/terminal/...` POSTs could still mutate some archived/cancelled card data if an id/version was known.

Fix:

- Added terminal route-layer visibility guard before terminal material, tare, roll, timing, and finish mutations.
- Preserved admin correction routes for intended admin-side correction behavior.
- Added direct route regression tests for cancelled tare edit, archived material edit, and archived roll edit.

### 3. Overlapping Closed Timing Segments

Severity: High.

Problem: Admin timing corrections allowed closed time segments to overlap. Totals then double-counted overlap time.

Fix:

- Added overlap validation for single segment add/update.
- Added final-ledger overlap validation for batch timing ledger saves.
- Adjacent segments where one ends exactly when the next starts remain valid.
- Added tests for overlap rejection and adjacent acceptance.

### 4. Reimport Overwrite Could Degrade Released Recipe Validity

Severity: High.

Problem: `release_card()` validates structured recipe fields, but overwrite reimport could update already released cards with recipe text that would no longer pass release validation.

Fix:

- Overwrite reimport now preserves draft flexibility, but for non-draft cards the incoming import fields must still pass release recipe/target validation.
- Invalid overwrite rows are blocked and existing card data/version are preserved.
- Added tests for blocked invalid overwrite on released card and allowed invalid overwrite on unreleased draft.

### 5. New Roll Field Autosaved On Click-Away

Severity: High for operator safety.

Problem: The new-roll form used dirty autosave. An operator could type a gross weight and click a queue row, finish, or another control, causing a roll to be created without pressing Enter/Add.

Fix:

- Removed dirty autosave from the new-roll form.
- Kept dirty autosave for tare and existing roll corrections.
- Add button flow remains covered by Playwright.
- Added render regression test proving new-roll form is not dirty-autosaved.

## Fixed After Audit

### 6. Roll Entry Allowed Before Tare Was Set

Severity: Important.

Problem: The backend allowed a gross roll to be inserted before an order default tare existed. That created a roll row without roll tare/net values and deferred the failure until finish validation.

Decision: Roll entry is the correct enforcement point. Operators may start timing before tare, but they must set a default tare or submit a roll tare before adding a gross roll. Each new roll stores the tare used for that roll, and later default-tare changes affect future rolls only.

Fix:

- `add_roll_gross_weight()` now rejects new gross roll creation when neither a submitted tare nor the card's current default tare exists.
- The submitted-tare path remains valid and updates the card default tare while storing the same tare/net on the new roll.
- Finish validation still defensively blocks corrupted or legacy rows that have gross weight without valid roll tare/net values.
- Added regression tests for tare-required roll entry, submitted-tare roll entry, and defensive finish validation.

Verification:

- `python -m compileall app` passed.
- `python -m pytest` passed with `434 passed`.
- `git diff --check` passed.

## Remaining Hardening Recommendations

### 1. Atomic Optimistic Version Checks

Severity: Important.

Most mutations compare `version` after reading the card, then later update by `id`. Normal stale pages are blocked, and SQLite’s write locking reduces practical risk, but a tighter pattern would update with `WHERE id = ? AND version = ?` on the first state-changing write and check `rowcount`.

Recommendation: harden the highest-risk mutations first: release, planning/resequence, cancel, restore, archive, terminal tare/roll/material writes.

### 2. Multiple Dirty Autosave Forms

Severity: Important.

Status update: the multiple existing-roll correction risk is fixed. Existing terminal roll rows are now read-only by default; `Корекция на ролки` opens a deliberate correction mode that saves gross/tare roll corrections together through one version-checked transaction. The remaining dirty-autosave risk is recipe plus tare edits before clicking away.

Recommendation: for the remaining recipe/tare case, either block navigation with a clear unsaved-changes warning when more than one form is dirty, or batch/save all dirty forms before reload.

### 3. Backup Integrity Check After Backup Creation

Severity: Medium.

Restore validates the restored DB, but backup creation does not run `PRAGMA integrity_check` on the newly created backup before reporting success.

Recommendation: validate each new backup file before retention pruning.

### 4. UX/Accessibility Follow-Ups

Severity: Medium/Minor.

Observed risks:

- Queue and produced drawers do not visibly trap or move focus into the drawer.
- Finish modal focuses the destructive confirmation button first and may not restore focus on close.
- Admin planning errors are global notices rather than row-local errors.
- Admin correction ledgers should be checked for per-row accessible labels and keyboard flow.
- Sync banner is manual refresh after polling, not automatic refresh.

Recommendation: handle these as a focused UI hardening pass with Playwright keyboard checks and screenshots.

## Pilot Readiness Assessment

Current recommendation: ready for controlled pilot rehearsal after reviewing the remaining recommendations above.

The most serious data-integrity issues found in this audit were fixed and verified. The main remaining risks are concurrency hardening and terminal dirty-autosave edge cases involving multiple dirty forms, plus backup verification and UX/accessibility improvements that affect operator confidence more than core data integrity.
