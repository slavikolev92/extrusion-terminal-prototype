# Fast Software Audit - 2026-06-24

## Scope

This was a fast software audit, not the full readiness audit or heavy stress audit. It focused on realistic workbook-derived data, core data-recording flows, and screenshot evidence through the main admin and terminal screens.

Physical printing was intentionally out of scope. The app-side print route was checked only by rendering the print preview and generating a PDF.

## Source Data

Workbook sources inspected:

- `interim-costing-process/source-files/PO-OC - Elena.xlsm`
- `interim-costing-process/source-files/PO-OC - Marco.XLSM`

The `.xlsm` files were parsed read-only as zipped workbook XML because `openpyxl` is not installed in the repo virtualenv.

Workbook readability result:

- `PO-OC - Elena.xlsm`: 7,886 order rows found, 1,845 rows matched the app's usable extrusion criteria.
- `PO-OC - Marco.XLSM`: 11,316 order rows found, 10,359 rows matched the app's usable extrusion criteria.

Generated audit CSV:

- `.test-runtime/fast-audit-20260624/fast-audit-real-workbook-sample.csv`
- `.test-runtime/fast-audit-20260624/fast-audit-real-workbook-sample.metadata.json`

The CSV contained:

- 4 real usable extrusion rows from `PO-OC - Marco.XLSM`
- 1 deliberate duplicate row for order `3117`
- 1 real no-extrusion/skipped row for order `3000`

## Verification Commands

Baseline checks:

```bash
source .venv/bin/activate
python -m compileall app
```

Result: passed.

```bash
source .venv/bin/activate
python -m pytest
```

Result: `282 passed in 15.82s`.

```bash
git diff --check
```

Result: passed.

Temporary audit server:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/fast-audit-20260624/extrusion_terminal.sqlite3 \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Health response after workflow:

```json
{
  "status": "ok",
  "database_path": ".test-runtime/fast-audit-20260624/extrusion_terminal.sqlite3",
  "machine_count": 4,
  "card_counts": [
    {"status": "archived", "count": 1},
    {"status": "imported", "count": 1},
    {"status": "pending", "count": 2}
  ]
}
```

Backup/recovery checks:

```bash
source .venv/bin/activate
python -m app.backups backup \
  --source .test-runtime/fast-audit-20260624/extrusion_terminal.sqlite3 \
  --backup-dir .test-runtime/fast-audit-20260624/backups \
  --keep 10
```

Result:

- created `.test-runtime/fast-audit-20260624/backups/extrusion_terminal_20260624_080056_992969.sqlite3`
- source DB `PRAGMA integrity_check`: `ok`
- backup DB `PRAGMA integrity_check`: `ok`

Restore:

```bash
source .venv/bin/activate
python -m app.backups restore \
  --backup .test-runtime/fast-audit-20260624/backups/extrusion_terminal_20260624_080056_992969.sqlite3 \
  --target .test-runtime/fast-audit-20260624/restored/extrusion_terminal_restored.sqlite3
```

Result:

- restored scratch DB created
- restored DB `PRAGMA integrity_check`: `ok`
- restored card counts matched the temporary audit DB

Print route:

```bash
pdfinfo artifacts/ui-checks/fast-audit-20260624/fast-audit-print-preview.pdf
```

Result:

- `Pages: 2`
- `Page size: 595.92 x 842.88 pts (A4)`

## Browser Evidence

Screenshot and note folder:

- `artifacts/ui-checks/fast-audit-20260624/`
- `artifacts/ui-checks/fast-audit-20260624/browser-notes.md`

Captured evidence:

- 29 PNG screenshots
- 1 print preview PDF

Key screenshots:

- `03-admin-import-result.png` - import result with created, duplicate skipped, and no-extrusion skipped rows
- `05-admin-planning-after-release.png` - machine assignment, max roll weight, target sequence insertion
- `12-terminal-second-roll-added.png` - terminal material fields, tare, roll add/edit, totals
- `16-terminal-produced-drawer.png` - produced-card lookup
- `18-admin-card-corrections-saved.png` - admin completed-card corrections persisted
- `19-print-preview.png` - app-side print preview
- `21-admin-planning-after-finish-gap.png` - queue sequence gap after finish
- `24-terminal-queue-drawer-after-finish.png` - terminal queue drawer showing the same active sequence gap
- `29-admin-planning-after-cancel-restore-unrelease.png` - cancel/restore and return-to-planning follow-up state

## Workflow Covered

The fast audit successfully exercised:

- admin CSV import from workbook-derived data
- duplicate row handling
- no-extrusion skipped row handling
- admin planning release
- shift-manager-entered maximum roll weight
- target sequence insertion
- terminal machine selection
- terminal start timing
- terminal material/recipe correction fields
- terminal tare entry
- terminal gross roll entry
- terminal existing roll correction via Enter
- terminal pause and resume
- terminal finish
- terminal produced-card drawer
- admin card detail for a completed card
- admin order-field correction
- admin material ledger correction
- admin print route access
- admin archive/finalization
- admin card index and filtering
- admin cancel and restore
- admin return-to-planning for a pending card
- backup, restore, and SQLite integrity checks

Persisted data confirmed in SQLite:

- imported rows and import row outcomes
- machine assignment and sequence
- max roll weight
- terminal material actuals and batch/lots
- tare weight
- two roll entries with net-weight calculations
- timing pause and finish segments
- completed then archived status
- admin-corrected customer, city, max roll weight, notes, and material fields

## Findings

### Important Finding 1 - Active queue sequence is not normalized after finish/archive

After releasing order `3118` into Machine 1 sequence `1` and order `3117` into Machine 1 sequence `2`, the audit finished and archived order `3118`.

Expected:

- The remaining active Machine 1 card, order `3117`, should become sequence `1`.
- Active machine queues should remain contiguous starting at `1`.

Actual:

- Order `3117` remained `pending` with `machine_sequence = 2`.
- Machine 1 had no active sequence `1`.

Evidence:

- `artifacts/ui-checks/fast-audit-20260624/21-admin-planning-after-finish-gap.png`
- `artifacts/ui-checks/fast-audit-20260624/24-terminal-queue-drawer-after-finish.png`
- final DB query:

```json
{
  "active_machine_sequences": [
    {
      "machine_id": 1,
      "order_number": "3117",
      "status": "pending",
      "machine_sequence": 2
    }
  ]
}
```

Why it matters:

- This violates the repository rule that active machine queues must be normalized to contiguous sequence positions starting at `1`.
- It may confuse shift-manager/admin planning and terminal queue display after a card is finished or removed from the active queue.

Recommended next step:

- Add focused regression tests for queue normalization after `finish_card()` and `cancel_card()`.
- Fix the backend status transition paths so removing an active card normalizes the affected machine queue.

### Minor Finding 1 - Admin save-all correction has weak visible confirmation

The admin completed-card correction save persisted data correctly, but the captured post-save state did not show an obvious success notice near the top of the page.

Evidence:

- `artifacts/ui-checks/fast-audit-20260624/18-admin-card-corrections-saved.png`
- DB confirmed the corrected values persisted.

Why it matters:

- The data is saved, but the shift manager may not get strong confirmation after a large correction save.

Recommended next step:

- During the full readiness audit, confirm whether the notice appears elsewhere or is lost because of redirect/anchor behavior.
- If it is missing, add a visible success message for `save-all`.

## Non-Findings From This Fast Pass

No issue was observed in this pass for:

- basic app startup with a temporary DB
- database initialization and health route
- import result persistence
- duplicate-in-file reporting
- no-extrusion skip reporting
- release with machine and sequence
- target sequence insertion during release
- terminal material field persistence
- tare persistence
- roll add/edit persistence
- net weight calculation for entered tare and gross rolls
- pause/resume timing segment recording
- finish validation for the happy path
- completed-card visibility in terminal produced drawer
- admin correction persistence
- print route rendering
- two-page A4 PDF generation
- archive/finalization happy path
- cancel/restore happy path
- return-to-planning happy path
- backup creation
- backup restore into scratch DB

## Fast Audit Limits

This fast audit did not fully cover:

- stale multi-tab conflict checks
- invalid value matrices for every field
- direct route abuse against wrong statuses
- timing correction edge cases
- overlapping timing segments
- roll deletion and renumbering from the terminal correction panel
- admin roll deletion
- restore conflict when a machine/sequence slot is reused
- re-import overwrite preservation after production data exists
- high-volume import/search/produced-drawer performance
- responsive/mobile workstation layouts
- physical printing

Those belong in the full readiness audit and heavy stress audit described in:

- `reports/final-audit-plan-20260624.md`

## Recommendation

Do not declare final pilot readiness from this fast audit alone.

The core happy path worked and data persisted across the main workflow, but the active queue normalization issue should be fixed before pilot use because it violates a confirmed backend invariant and is visible in both admin planning and terminal queue views.
