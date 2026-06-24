# Final Pilot Audit Plan - 2026-06-24

This report preserves the audit planning context for the extrusion terminal pilot app so the next session can resume without repeating the discussion.

## Current Decision Context

The app has reached the point where the major pilot workflow is implemented:

- workbook-driven CSV import
- shift-manager admin review and planning
- release to four extrusion machine queues
- terminal execution with timing, tare, rolls, material corrections, and finish
- completed-card correction from admin
- admin-owned print/reprint and archive/finalization
- backup and restore utilities
- live V8 terminal layout connected to the server-rendered app

The next work is not new feature development. It is a final software audit before pilot use. The audit should try to find bugs, gaps, inconsistencies, risky workflow behavior, missing validation, and documentation drift.

The user confirmed:

- The workbook files under `interim-costing-process/source-files/` are current enough for audit purposes.
- These files reflect how the company currently works, even if the backups are not from today.
- The audit may use any local test database or temporary database; nothing in this VM should be treated as live production data.
- Physical printing is out of scope for Codex. The user will verify physical/PDF output where needed.
- Codex may verify app-side print route behavior such as whether a generated PDF has two pages, but should not spend audit effort on physical printer setup.
- The immediate next action should be a fast audit. The fuller audits should be preserved for tomorrow or a later session when usage limits reset.

Workbook sources:

- `interim-costing-process/source-files/PO-OC - Elena.xlsm`
- `interim-costing-process/source-files/PO-OC - Marco.XLSM`

Preferred audit database policy:

- Use a temporary audit DB under `.test-runtime/`, for example `.test-runtime/final-audit/`.
- Do not rely on or mutate `data/extrusion_terminal.sqlite3` unless a later user instruction explicitly chooses that path.

## Audit Levels

There are three possible audit levels. They are designed to build on each other.

### 1. Fast Audit

Purpose: get quick signal today with low token/time cost.

Scope:

- Run the existing automated test suite.
- Run syntax/import checks and `git diff --check`.
- Inspect workbook readability enough to confirm realistic rows can be extracted later.
- Start a local app against a temporary audit DB.
- Run one compact browser workflow:
  - import a small sample
  - release one or more cards
  - open terminal
  - start/pause/resume if feasible
  - enter tare and roll
  - finish
  - view completed card in admin
  - open print route if feasible
- Record obvious findings only.

Expected output:

- Short report or final response with commands run, pass/fail state, and any immediate blockers.
- No broad code changes unless the fast audit finds a clear blocking defect and the user approves fixing it.

Good fit when:

- We need a quick confidence check.
- We have limited tokens/time.
- We are not trying to prove pilot readiness exhaustively.

### 2. Full Readiness Audit

Purpose: determine whether the software is ready for pilot rehearsal, with evidence.

Scope:

#### Audit Data Prep

- Read both `.xlsm` files read-only.
- Identify and extract relevant `Database` worksheet rows.
- Generate audit CSV fixtures from real workbook data:
  - normal happy-path rows
  - duplicate/re-import rows
  - no-extrusion or skipped rows
  - long-text rows
  - enough rows to test admin search and terminal lists
- Keep generated audit data under `.test-runtime/` or `artifacts/`, not as tracked source unless intentionally approved.

#### Baseline Verification

Run:

```bash
source .venv/bin/activate
python -m compileall app
python -m pytest
git diff --check
```

#### Backend/Data Integrity Tests

Add or run focused tests for high-risk invariants:

- Active queue sequence normalization after finish.
- Active queue sequence normalization after cancel.
- Finish/cancel with pending cards behind the affected card.
- Terminal snapshot reflects normalized queue order.
- Stale version checks on admin and terminal mutations.
- Timing correction updates `first_started_at`, `finished_at`, total duration, and print stop/duration consistently.
- Overlapping timing segments are blocked or explicitly documented as accepted behavior.
- Direct terminal POSTs against cancelled or archived cards do not mutate data if backend enforcement is intended.
- Backup creation is followed by `PRAGMA integrity_check`.
- Restore into scratch DB works and restored DB passes integrity checks.

#### Admin Workflow Browser Audit

Use Playwright and/or manual browser checks against a temporary audit DB:

- Import mixed CSV data:
  - created rows
  - skipped duplicates
  - explicit overwrite
  - no-extrusion skipped rows
  - row errors
- Confirm import result table is understandable.
- Confirm recent import history is useful enough after leaving the result page.
- Release three cards to one machine using target sequence positions like `1`, `99`, then `1`.
- Verify queue normalization and terminal order.
- Reassign a pending card while another card is running.
- Block invalid running/paused reassignment where appropriate.
- Return a pending card to planning from `/admin/planning` and `/admin/cards/{id}`.
- Open the same card in two admin tabs and verify stale save/cancel/archive/release attempts are blocked.
- Cancel and restore cards, including restore when the original slot has been reused.
- Complete a card, then edit order fields, materials, tare, rolls, and timing from admin.
- Print/reprint from admin detail.
- Archive/finalize and verify card remains searchable and printable.
- Verify global admin navigation across import, planning, card list, and detail pages.

Admin risks already identified:

- Card index may lack order-date and delivery-date filters mentioned in a prior milestone target.
- Planning errors may render as top-level notices instead of near the affected row/action.
- The global terminal nav label may differ from earlier wording: `Терминал` vs `Към терминала`.
- Admin archive currently appears to be separate from print readiness; print route enforces readiness.
- Restore behavior should be tested when another active card has reused the original machine sequence.

#### Terminal/Workstation Browser Audit

Use Playwright at realistic terminal viewport size:

- Four-machine navigation:
  - running machine
  - paused machine
  - pending machine
  - empty machine
- Verify selection priority and visual clarity.
- Queue drawer:
  - open/close button
  - Escape
  - backdrop
  - grouped by four machines
  - selected machine highlight
  - row click is navigation only
- Produced drawer:
  - completed card visible
  - cancelled card absent
  - archived behavior matches accepted scope
  - filter by customer, product, size/material
- Timing:
  - start
  - pause
  - resume
  - start another card while first is paused if allowed
  - block resume while machine is occupied
  - finish from running and paused states
- Finish validation:
  - missing tare
  - missing timing
  - missing roll
  - stale version
  - success closes active timing segment
- Tare/roll:
  - tare saves on Enter and blur
  - add roll with Enter and button
  - reject more than two decimals
  - edit existing roll, likely via Enter
  - delete roll through correction control
  - completed-card roll correction still works
- Recipe/material dirty behavior:
  - Enter saves
  - first outside click after dirty edit saves and stays
  - second click performs original navigation/action
  - repeat against machine tab, queue row, produced row, and finish action
- Sync:
  - open terminal and admin in two browser contexts
  - resequence, unrelease, cancel, or archive selected card from admin
  - terminal shows update/refresh state within polling interval
  - after refresh, terminal lands in correct visible state
- Exposure:
  - `/terminal` has no visible or linked `/admin`, print, cancel, restore, archive, or finalization actions

Terminal risks already identified:

- Sync behavior may currently show a manual refresh alert rather than automatically refreshing.
- Recipe autosave intentionally intercepts the first outside click, which may feel like a missed click to operators.
- Existing roll correction may rely on pressing Enter with no visible save button.
- Produced lookup appears client-side over all completed cards; test with realistic volume and long strings.
- Direct print/admin routes exist by URL because the pilot has practical separation, not real authentication.

#### Print Route Software Check

Do not test physical printing.

Software-only checks:

- Completed and archived cards can open `/cards/{card_id}/print`.
- Pending/running/paused/imported/cancelled cards are blocked.
- Missing tare, missing timing, open timing segment, missing rolls, or more than 120 rolls are blocked.
- Browser/PDF output has exactly two A4 portrait pages.
- App-only fields such as machine, sequence, status, internal id, and max roll weight are not printed.

The user will handle final PDF/physical validation.

#### Documentation And Operational Readiness Review

Review and report:

- README startup commands for Linux VM correctness.
- Any remaining Windows-only command drift.
- Actual DB path and backup path documentation.
- Backup command, restore command, retention behavior.
- Whether backup scheduling/off-machine backup exists or remains a known operational task.
- Kiosk setup notes and terminal URL.
- Doc drift around print/reprint ownership:
  - current accepted behavior is admin-only print/reprint
  - terminal should not print/reprint
  - any old documentation that says workstation reprint should be corrected or flagged

Expected output:

- `reports/full-readiness-audit-YYYYMMDD.md`
- ranked findings:
  - Blocking
  - Important
  - Minor
  - Accepted limitations
- commands run
- test output summaries
- browser artifact paths
- print PDF artifact path if generated
- final recommendation:
  - Ready
  - Ready with caveats
  - Not ready

Good fit when:

- We want defensible software readiness before pilot rehearsal.
- We are willing to add focused tests and investigate findings.

### 3. Heavy Stress Audit

Purpose: deliberately try to break the pilot app beyond the normal workflow.

This is probably overkill before the next small pilot rehearsal, but useful if the app is about to be used more heavily or if we want higher confidence.

Scope additions beyond the Full Readiness Audit:

#### Data Volume And Search Stress

- Import a large sample from both workbooks, possibly hundreds or all eligible extrusion rows.
- Generate synthetic duplicates and overwrites.
- Generate long customer/product/material/notes values.
- Generate many completed cards for terminal produced lookup.
- Generate many rolls near the 120-roll print limit.
- Check admin card list performance and usability.
- Check terminal produced drawer performance and search responsiveness.

#### Route-Level Abuse Tests

Use direct HTTP requests, not only browser UI:

- POST stale versions to every mutation route.
- POST invalid card IDs.
- POST valid versions against wrong statuses.
- POST missing machine IDs, invalid sequence numbers, negative/decimal sequences.
- POST roll weights with bad formats, too many decimals, blank values, huge values, negative values.
- POST timing segments with:
  - end before start
  - overlapping segments
  - multiple open segments
  - invalid datetime format
  - large future/past timestamps
- POST restore/cancel/archive transitions out of order.
- Confirm errors are controlled and data is unchanged.

#### Browser Stress

- Test terminal at multiple viewport sizes:
  - actual workstation resolution
  - smaller laptop
  - browser zoom if practical
- Test long text wrapping and no overlap in:
  - machine nav
  - details
  - recipe rows
  - queue drawer
  - produced drawer
  - roll table
  - admin detail ledgers
- Test many rows in roll/timing/material ledgers.
- Test repeated dirty-form navigation.
- Test two concurrent browser sessions making competing edits.

#### Backup/Restore Stress

- Backup while the app is running.
- Backup during or immediately after a workflow mutation.
- Restore to scratch DB and run app against restored DB.
- Run integrity checks before and after restore.
- Verify backup retention does not delete unrelated files.

#### Restart/Persistence Stress

- Start workflow, pause mid-card, stop server, restart.
- Verify running/paused state persists.
- Verify active timing segments behave as expected after restart.
- Finish after restart.
- Restart after admin corrections and archive.
- Verify print remains available.

#### Security/Exposure Sanity

The app has no authentication by design. The audit should not turn this into a new requirement, but it should document practical exposure:

- LAN-only binding should be intentional.
- No public internet exposure.
- Terminal has no visible admin navigation.
- Direct admin routes are accessible by URL, as accepted for pilot.
- Direct print route is accessible by URL for printable cards, as accepted unless user changes scope.

Expected output:

- `reports/heavy-stress-audit-YYYYMMDD.md`
- all full readiness outputs
- stress data generator notes if any
- route-level abuse matrix
- performance/usability observations
- list of issues that must be fixed before broader use

Good fit when:

- We have enough token/time budget.
- The pilot will run with larger row counts.
- We want to identify less likely but costly failure modes.

## Subagent Strategy

Subagents are useful because the audit domains are independent.

Recommended parallel agents for full/heavy audits:

1. Backend/data invariants
   - Owns schema, imports, status transitions, queue sequencing, timing, route-level validations.

2. Admin workflow
   - Owns `/admin/import`, `/admin/planning`, `/admin/cards`, `/admin/cards/{id}`.

3. Terminal/workstation
   - Owns `/terminal`, V8 layout behavior, queue/produced drawers, timing/roll/material interactions, dirty form protection.

4. Print/ops/docs
   - Owns print route software checks, backup/restore, startup docs, kiosk/deployment notes, documentation drift.

Main agent responsibilities:

- Coordinate scope.
- Avoid duplicate work.
- Verify subagent claims.
- Integrate findings into one ranked report.
- Decide which issues are blocking before pilot rehearsal.

## Suggested Next Session Start

Start by reading this file, then choose one audit level.

The fast audit has now been completed. Do not repeat it unless a later fix needs regression evidence. Read these files first:

- `reports/fast-audit-20260624.md`
- `open-issues.md`
- `artifacts/ui-checks/fast-audit-20260624/browser-notes.md`

Fast audit summary:

- The main happy path and data-recording flow worked with workbook-derived data.
- Baseline checks passed: `compileall`, full pytest, and `git diff --check`.
- Browser evidence was captured for import, planning, terminal production entry, admin corrections, print preview, archive, cancel/restore, and return-to-planning.
- Two open issues were recorded in `open-issues.md`.

Do not duplicate the detailed fast-audit conclusions here; keep `reports/fast-audit-20260624.md` as the detailed audit record.

What the fast audit did not cover and should remain priority for the following audits:

- stale multi-tab conflict checks
- invalid input matrices for all editable fields
- direct route abuse against wrong statuses
- timing correction edge cases and overlapping timing segments
- terminal and admin roll deletion/renumbering paths
- restore conflict when a machine/sequence slot has been reused
- re-import overwrite behavior after production data exists
- high-volume import/search/produced-drawer performance
- responsive/workstation viewport checks beyond the fast audit viewport

If a new fast audit is intentionally needed:

1. Confirm worktree status.
2. Run baseline checks.
3. Confirm workbook readability.
4. Create temporary audit DB.
5. Start app on local port against audit DB.
6. Run one compact workflow through admin and terminal.
7. Save any screenshots under `artifacts/ui-checks/final-fast-audit/`.
8. Report findings without making broad fixes.

For the later full readiness audit:

1. Dispatch the four subagents listed above.
2. Build real workbook-derived audit fixtures.
3. Add focused invariant tests.
4. Run browser workflows and collect artifacts.
5. Produce `reports/full-readiness-audit-YYYYMMDD.md`.

## Commands Likely To Be Used

Baseline:

```bash
source .venv/bin/activate
python -m compileall app
python -m pytest
git diff --check
```

LAN/local server:

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Local-only server:

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Backup utility checks:

```bash
source .venv/bin/activate
python -m app.backups backup --source .test-runtime/final-audit/extrusion_terminal.sqlite3 --backup-dir .test-runtime/final-audit/backups
```

Playwright:

```bash
npx playwright test
```

## Important Non-Goals

- Do not expand this pilot into a permanent ERP replacement.
- Do not add authentication or permissions unless the user explicitly changes scope.
- Do not write terminal-entered data back to Excel.
- Do not physically test printing from Codex.
- Do not mutate real production data. In this VM, the user says local DBs are test data, but the cleaner audit practice remains to use `.test-runtime/`.
- Do not commit unless the user explicitly asks.
