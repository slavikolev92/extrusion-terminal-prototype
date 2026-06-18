# Full Workflow Audit Report

Date/time: 2026-06-17 21:33 UTC

## Temporary Test Setup

- Repository: `/home/sk/projects/extrusion-terminal`
- Server: FastAPI/Uvicorn on `http://127.0.0.1:18086`
- Database: temporary SQLite at `.test-runtime/full-workflow-audit-20260617/audit-final-clean.sqlite3`
- Runtime DB safety: `data/extrusion_terminal.sqlite3` was not used or mutated.
- Browser verification: Playwright Chromium at `1920x950`.
- Screenshots and audit artifacts: `artifacts/ui-checks/full-workflow-audit-20260617/`
- Temporary server status: stopped after the audit.

## Workflow Tested

I tested a realistic full flow with two extrusion orders, one duplicate CSV row, and one no-extrusion row:

1. CSV import with all relevant order fields and all seven recipe material fields.
2. Duplicate import behavior.
3. No-extrusion row skip behavior.
4. Planning/release attempt through `/admin/planning`.
5. Backend-only planning setup against the temp DB after the planning UI blocker, so terminal/admin downstream behavior could still be audited.
6. Terminal machine navigation, empty machines, queue drawer, completed-orders drawer/search.
7. Start, pause, resume, tare entry, multiple roll entries, roll correction, hidden roll deletion confirmation, all seven recipe actual/batch fields.
8. Finish and refresh-after-finish behavior.
9. Completed-card review from admin.
10. Admin imported-field, production-material, tare, roll, timing, overwrite-import, cancel, and restore checks.
11. Final terminal layout at `1920x950`.

## Bugs Found

### 1. Critical: `/admin/planning` returns HTTP 500 and blocks shift-manager planning

Reproduction:

1. Start the app against a clean temp DB.
2. Import a valid extrusion CSV.
3. Open `/admin/planning`.

Expected behavior:

- The planning page renders unreleased cards, machine queues, release forms, and reassignment/resequence controls.

Actual behavior:

- `/admin/planning` returns HTTP 500.
- The shift manager cannot release imported cards or change machine/sequence through the UI.
- The audit had to use `db.release_card()` and `db.update_card_planning()` directly against the temp DB to continue downstream testing.

Evidence:

- Screenshot: `artifacts/ui-checks/full-workflow-audit-20260617/planning-500-release-AUD-90001.png`
- Screenshot: `artifacts/ui-checks/full-workflow-audit-20260617/planning-500-release-AUD-90002.png`
- Server traceback showed `NameError: name 'machines' is not defined`.

Likely code area:

- `app/main.py:136` defines `admin_planning_context()`.
- `app/main.py:140` references `"machines": machines`, but no local `machines` variable is defined.
- `app/main.py:288` routes `/admin/planning` through that context.

### 2. High: Admin correction POSTs can be repeated by browser refresh

Reproduction observed during audit:

1. Open a completed admin card.
2. Submit admin corrections, such as imported fields, tare, roll correction, roll add/delete, or timing correction.
3. Refresh the browser after the POST-rendered response.

Expected behavior:

- Successful admin mutations should use POST-redirect-GET, like the terminal success path, so refreshing does not repeat the mutation.

Actual behavior:

- Admin mutation routes render `admin_card_detail.html` directly after POST.
- During the audit, browser reload after these pages repeated POST requests in the live server log.
- This is most dangerous for non-idempotent actions such as admin roll add/delete and timing segment add/delete.

Evidence:

- Observed repeated live requests during the Playwright run, including repeated POSTs to admin imported-field, tare, roll update, roll add, roll delete, and timing routes.
- Screenshot stages around affected admin forms:
  - `artifacts/ui-checks/full-workflow-audit-20260617/20-admin-imported-corrections.png`
  - `artifacts/ui-checks/full-workflow-audit-20260617/22-admin-tare-roll-correction.png`
  - `artifacts/ui-checks/full-workflow-audit-20260617/23-admin-roll-add-delete.png`
  - `artifacts/ui-checks/full-workflow-audit-20260617/24-admin-timing-correction.png`

Likely code area:

- `app/main.py:332` imported-field correction returns `TemplateResponse` after POST.
- `app/main.py:456` production-material correction returns `TemplateResponse` after POST.
- `app/main.py:478`, `app/main.py:495`, `app/main.py:512`, and `app/main.py:535` admin tare/roll routes return `TemplateResponse` after POST.
- `app/main.py:556`, `app/main.py:581`, and `app/main.py:608` admin timing routes return `TemplateResponse` after POST.

## Non-Bug UX / Process Improvements

- Admin roll section copy says `Само преглед в този пакет`, but the same section contains editable tare, add-roll, roll-save, and roll-delete controls. That copy is now misleading. See `app/templates/admin_card_detail.html:292` and controls beginning at `app/templates/admin_card_detail.html:301`.
- After an incorrect terminal roll-delete confirmation, the panel re-renders and the roll selector returns to the first roll. This is safe, but it means the operator must reselect the intended roll before trying again. Keeping the selected roll would reduce error recovery friction.
- The focused admin route/planning tests passed despite the live `/admin/planning` 500. Add a route-render regression test for `/admin/planning`.

## Behaved Correctly

- CSV import created two valid extrusion cards, skipped the duplicate-in-file row, and skipped the no-extrusion row.
- Duplicate import without overwrite skipped existing orders.
- Backend release/resequence helpers normalized queues correctly in the temp DB.
- Terminal machine tiles for empty machines were clickable and showed the expected empty-machine state.
- Queue drawer and completed-order drawer/search worked.
- Start, pause, resume, tare entry, roll entry, roll correction, and finish persisted.
- Max roll weight remained informational only; rolls above it were accepted.
- Remaining quantity clamped to `0.00` after overproduction.
- Hidden terminal roll deletion required confirmation and renumbered remaining rolls after successful deletion.
- All seven recipe actual-material and batch fields saved, survived reload, and remained visible after completion.
- Finish redirected to the canonical card URL; browser reload did not resubmit finish.
- Completed card remained visible for review/correction.
- Admin production-material corrections were visible in the terminal recipe table.
- Overwrite re-import preserved completed status, tare, rolls, timing, and seven recipe actual entries.
- Admin cancel/restore worked on a pending card, and workstation did not expose cancel/restore controls.
- Terminal layout remained usable at `1920x950` in the tested states.

## Tests / Checks Run

- Playwright browser audit script:
  - `artifacts/ui-checks/full-workflow-audit-20260617/full_workflow_audit.js`
- Focused automated tests:
  - `source .venv/bin/activate && python -m pytest tests/test_admin_routes.py tests/test_admin_planning.py -q`
  - Result: `13 passed in 0.72s`

Important test gap:

- The passing tests did not catch the live `/admin/planning` render failure.

## Key Artifact Paths

- Audit notes JSON: `artifacts/ui-checks/full-workflow-audit-20260617/audit-notes.json`
- Final DB state JSON: `artifacts/ui-checks/full-workflow-audit-20260617/final-db-state.json`
- Import result: `artifacts/ui-checks/full-workflow-audit-20260617/01-admin-import-result.png`
- Planning 500: `artifacts/ui-checks/full-workflow-audit-20260617/planning-500-release-AUD-90001.png`
- Terminal 1920x950 open card: `artifacts/ui-checks/full-workflow-audit-20260617/05-terminal-open-card-1920x950.png`
- Roll deletion confirmation: `artifacts/ui-checks/full-workflow-audit-20260617/14-terminal-roll-delete-wrong-confirm.png`
- Roll deletion success: `artifacts/ui-checks/full-workflow-audit-20260617/15-terminal-roll-delete-success.png`
- Recipe persistence: `artifacts/ui-checks/full-workflow-audit-20260617/16-terminal-recipe-saved-reload.png`
- Finish and reload: `artifacts/ui-checks/full-workflow-audit-20260617/17-terminal-finished-reloaded.png`
- Admin material correction visible in terminal: `artifacts/ui-checks/full-workflow-audit-20260617/21-admin-materials-visible-terminal.png`
- Final layout: `artifacts/ui-checks/full-workflow-audit-20260617/28-terminal-final-layout-1920x950.png`

## Remaining Uncertainty

- Full planning UI behavior could not be audited because `/admin/planning` is currently blocked by HTTP 500.
- Stale-write conflict checks were not exhaustively tested with two simultaneous browser sessions in this audit.
- Print output was not tested; it remains a later milestone.
- This was a functional/UX audit, not a full accessibility audit. Keyboard and screen-reader behavior need separate verification if required.
