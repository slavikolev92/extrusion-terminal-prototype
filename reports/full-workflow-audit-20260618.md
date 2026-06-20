# Full Workflow Audit - 2026-06-18

Audit run: 2026-06-18 21:17 UTC
Repository: `/home/sk/projects/extrusion-terminal`
Branch/commit: `main` at `4e98480`
Server URL: `http://127.0.0.1:8765`
Temporary DB: `.test-runtime/audit-20260618/audit-rerun.sqlite3`
Runtime DB safety: `data/extrusion_terminal.sqlite3` was not used.
Server status: temporary server was stopped after testing.
Confirmed findings after follow-up: 8 total.

## Current State Discovery

Read before testing:

- `AGENTS.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `docs/implementation-notes/print-output-reference.md`
- `source-files/README.md`
- `source-files/print-template.pdf`
- current routes, templates, database/import/print code, and tests

No prior `FULL_WORKFLOW_AUDIT_REPORT.md` or newer tracked report files were present in `reports/` before this report.

Current user-facing routes found:

- `/admin/import`
- `/admin/planning`
- `/admin/cards`
- `/admin/cards/{card_id}`
- `/terminal`
- `/terminal/cards/{card_id}`
- `/terminal/snapshot`
- `/cards/{card_id}/print`

Git status:

- `git status --short` was clean before and after the audit.
- Audit DB/scripts/screenshots were under ignored runtime/artifact paths.

## Test Data

CSV artifact: `artifacts/ui-checks/full-workflow-audit-20260618/audit-import.csv`

Imported rows:

- `31001`: primary full extrusion card, all import fields filled, kg target, seven recipe rows, packaging, notes.
- `31002`: valid queue/resequence/reassignment card.
- `31003`: valid cancel/restore and print-blocking card.
- duplicate `31001`: skipped.
- `31999`: no-extrusion row, skipped.

Import result verified in UI:

- 3 created.
- 2 skipped.
- duplicate row reported.
- no-extrusion row reported.

Overwrite probe artifact:

- `artifacts/ui-checks/full-workflow-audit-20260618/audit-overwrite-import.csv`

## Workflow Coverage

Covered through live FastAPI + Playwright against the temp DB:

- CSV import result and persisted data.
- Duplicate and no-extrusion import handling.
- Admin planning load, release, occupied sequence insertion, resequence, reassignment, invalid sequence.
- Terminal four-machine navigation, empty machine, queue drawer, completed drawer/search.
- Start, pause, resume, finish.
- Tare entry.
- Roll add/correction/delete.
- Max roll weight informational behavior.
- Overproduction remaining clamped to `0.00`.
- Seven recipe actual material/batch rows.
- Completed card terminal review/correction visibility.
- Admin imported-field/material/roll/timing corrections.
- Admin roll add/delete, timing add/delete/update.
- Admin cancel/restore.
- POST refresh behavior on finish, admin detail actions, cancel/restore, planning, import.
- Two-browser stale-write checks.
- Completed-card print route, pending-card blocked print route, PDF generation.

## Previous Audit Regression Status

- `/admin/planning` no longer returns 500: **passed**.
- Admin successful POST refresh cannot repeat:
  - **passed** for admin card detail correction routes, cancel/restore, and terminal finish because successful actions redirected to GET.
  - **failed/partial** for `/admin/import`, `/admin/cards/{id}/release`, and `/admin/cards/{id}/planning`; details below.
- Admin roll-section copy is no longer misleading: **passed** in current redesigned admin roll ledger.
- Terminal failed roll-delete confirmation preserves selected roll: **passed**. Wrong confirmation preserved selected roll id `2` and showed a visible error.

## Bugs Found In Initial Pass

### 1. High - Print Front Page Overlaps And Clips Rich Recipe Data

Status: **completed/stale after follow-up**. Later print-output work corrected the app-level layout/fidelity problems, and the physical printer rehearsal confirmed the generated operational card is near-perfect and works correctly from computers with correct print settings. A remaining case where one specific computer prints across two physical sheets is a workstation/browser/printer-driver/settings issue, not an application print-output defect.

Reproduction:

1. Import/release/complete card `31001`.
2. Fill all seven planned and actual material rows with non-trivial values.
3. Add rolls/timing/tare and open `/cards/1/print`.
4. Generate PDF with Playwright.

Expected:

- Print output should be exactly two A4 pages and visually match `source-files/print-template.pdf` as closely as practical.
- Long text should wrap or shrink without breaking the two-page structure.

Actual:

- Page count and A4 size are correct.
- Front page recipe, notes, and legacy sections overlap.
- The `Креда` row is crossed by the `ЗАБЕЛЕЖКИ`/bottom grid area.
- Several actual material/batch cells wrap into cramped multi-line blocks and become hard to read.

Evidence:

- `artifacts/ui-checks/full-workflow-audit-20260618/print-completed-output.pdf`
- `artifacts/ui-checks/full-workflow-audit-20260618/print-completed-output-page-1.png`
- Reference: `artifacts/ui-checks/print-template-reference-1.png`

Likely code area:

- `app/templates/print_card.html`
- `app/static/css/print.css`

Impact:

- Original audit impact is stale. App print output is now accepted for pilot use; any remaining problem is local workstation/printer-environment configuration.

### 2. High - Import Overwrite Silently Replaces Admin-Corrected Front-Card Fields

Status: **completed** in `audit-fix-import-overwrite-conflicts` at `eb8b574` (`Block stale import overwrites`).

Reproduction:

1. Complete card `31001`.
2. Correct imported/front-card fields in admin, including city/product.
3. Re-import a stale CSV for the same order with `overwrite_existing=true`.

Expected:

- Re-import preserves production data.
- Stale or old source uploads should not silently overwrite newer admin-corrected imported/front-card fields without a conflict warning.

Actual:

- Production data was preserved: roll count `2`, total gross `168`, total net `164`, timing segments remained.
- Imported/front-card fields were overwritten:
  - customer changed to `Overwrite Customer`
  - city changed to `Overwrite City`
  - product changed to `OVERWRITTEN IMPORT PRODUCT`
  - material/size/raw recipe fields changed to overwrite values
- Card version incremented from `24` to `26`.

Evidence:

- `artifacts/ui-checks/full-workflow-audit-20260618/import-overwrite-result.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/import-overwrite-probe.json`
- DB query after probe in temp DB showed overwritten imported fields with production rolls/timing intact.

Likely code area:

- `app/importer.py` `import_cards_from_csv`
- `app/importer.py` `update_imported_card_fields`

Impact:

- A stale workbook export can erase shift-manager corrections to source/front-card data after production is complete.
- This conflicts with the broader stale-write principle for admin edits.

### 3. Important - `/admin/import` POST Is Repeatable By Browser Refresh

Status: **completed** in the `audit-fixes-integrated` branch. Successful import POSTs redirect to `/admin/import?batch_id=<id>`; refreshing the GET result does not repeat the upload.

Reproduction:

1. Open `/admin/import`.
2. Upload `audit-overwrite-import.csv` with overwrite checked.
3. Refresh the result page.

Expected:

- Successful mutation should land on a GET/canonical page or otherwise not repeat by refresh.

Actual:

- Refresh repeated the same POST upload.
- Import batches increased from 2 to 3.
- The same order was overwritten twice and version bumped twice.

Evidence:

- `artifacts/ui-checks/full-workflow-audit-20260618/import-overwrite-refresh.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/import-overwrite-probe.json`
- Temp DB `import_batches` contained two rows for `audit-overwrite-import.csv` at the same timestamp.

Likely code area:

- `app/main.py` `import_csv`, which returns `TemplateResponse` after mutation.

Impact:

- Accidental refresh can create duplicate import batch history and stale other open admin/terminal pages.
- With overwrite enabled, repeated refresh repeats source-field updates.

### 4. Medium - Planning Release/Replanning POSTs Do Not Use PRG

Status: **completed** in the `audit-fixes-integrated` branch. Successful release and replanning POSTs redirect to `/admin/planning`; failed writes still render inline.

Reproduction:

1. Release card `31001` from `/admin/planning`.
2. Browser refresh the success result.

Expected:

- Refresh after a successful admin POST should not resubmit the mutation.

Actual:

- Page remained at `/admin/cards/1/release`.
- Refresh resubmitted POST.
- Version checks prevented duplicate release, but the user saw a stale-write error immediately after a successful release.

Evidence:

- `artifacts/ui-checks/full-workflow-audit-20260618/planning-release-refresh.png`
- `audit-log.json` shows post-release URL and refreshed URL both `/admin/cards/1/release`, with stale warning.

Likely code area:

- `app/main.py` `release_card_to_terminal`
- `app/main.py` `update_admin_card_planning`

Impact:

- Data integrity is protected by version checks, but UX is confusing and still violates the intended no-repeat refresh behavior.

### 5. Medium - Print Fidelity Drifts From Reference Labels And Geometry

Status: **completed/stale after follow-up**. Later template-fidelity work and physical printer rehearsal confirmed the app-generated print output is excellent and close enough to the operational card. Remaining two-sheet behavior on one computer is not an app fidelity issue.

Reproduction:

1. Generate app print PDF for completed card.
2. Compare with `source-files/print-template.pdf`.

Expected:

- Output should match the Excel front/back card as closely as practical.

Actual:

- Front labels/casing drift:
  - `[mm]` / `[kg]` become `[MM]` / `[KG]`.
  - reference row `ЛИНЕЕН /mLLDPE/` appears as `Линеен PE` in print.
- Back page first header label wraps as `ПОРЪЧК А №`.
- Roll grid is structurally present but sized/positioned differently from the reference.

Evidence:

- `artifacts/ui-checks/full-workflow-audit-20260618/print-completed-output-page-1.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/print-completed-output-page-2.png`
- `artifacts/ui-checks/print-template-reference-1.png`
- `artifacts/ui-checks/print-template-reference-2.png`

Likely code area:

- `app/printing.py` recipe labels
- `app/static/css/print.css` text-transform/column widths

Impact:

- Original audit impact is stale. App print fidelity is accepted; no app-level print-output task remains from this finding.

## Non-Bug UX/Process Improvements

- Pending-card print block lists all missing conditions plus `Критичните тегла за печат трябва да са валидни числа.`. That final message is technically produced by missing totals, but it reads like a separate data corruption problem.
- Admin detail summary uses sticky positioning. Full-page screenshot stitching made it appear over other sections; worth checking on the actual shift-manager monitor for whether it obscures rows while scrolling.
- Planning successful actions should likely use the same PRG pattern as admin card detail actions.
- Import overwrite probably needs a clearer operator warning that it replaces imported/front-card fields, not only “existing orders with same number.”

## Things That Behaved Correctly

- Database initialized with machines 1-4.
- Import persisted three valid cards.
- Duplicate-in-file row skipped.
- No-extrusion row skipped.
- Release inserted into occupied sequence and normalized queue positions.
- Reassignment/resequencing normalized active queues.
- Invalid planning sequence showed a visible error.
- Released cards appeared on `/terminal`.
- Machine navigation and empty machine state worked.
- Queue drawer and completed drawer opened and filtered.
- Start/pause/resume/finish worked.
- Finish closed the active segment and completed the card.
- Finish refresh did not resubmit.
- Max roll weight remained informational; over-max roll saved.
- Overproduction remaining displayed `0.00`.
- Roll correction persisted.
- Hidden roll deletion required confirmation and renumbered after correct confirmation.
- Wrong roll-delete confirmation preserved the selected roll.
- All seven recipe actual material/batch rows saved, survived reload, and remained after finish.
- Completed card remained visible/editable on terminal.
- Workstation did not expose cancel/restore.
- Admin cancel/restore worked and refresh did not toggle twice.
- Admin roll/tare/timing corrections recalculated totals/duration.
- Print route was blocked for pending card.
- Print/reprint link appeared for completed card.
- Stale writes were blocked for:
  - terminal material save
  - terminal roll correction
  - admin imported/front-card correction
  - admin materials ledger
  - admin roll ledger
  - admin timing ledger
  - planning/resequence

## Follow-Up Verification Added

After the original report, the user asked to verify three additional suspected problems. All three were confirmed against current code/UI and added below.

### 6. High - Paused Card Blocks Starting Another Card On The Same Machine

Status: **completed** in `audit-fix-paused-machine-occupancy` at `a5e94ba` (`Fix paused machine occupancy`).

Reproduction:

1. Import two cards, `PAUSE1` and `PAUSE2`.
2. Release both to machine 1 at sequences 1 and 2.
3. Start `PAUSE1`.
4. Pause `PAUSE1`.
5. Try to start `PAUSE2`.

Expected, based on clarified desired behavior:

- A paused order is not actively running production.
- Starting another pending card on the same machine should be allowed while the first card is paused.
- Resuming a paused card should be blocked only if another card is currently running on that machine.

Actual:

- Starting `PAUSE2` was blocked.
- The message was `Машина 1 е заета от поръчка PAUSE1.`
- `PAUSE1` remained `paused`; `PAUSE2` remained `pending`.

Evidence:

- `artifacts/ui-checks/full-workflow-audit-20260618/followup-paused-probe.txt`

Likely code area:

- `app/db.py` `fetch_occupied_machine_card`
- `app/db.py` `start_production_timing`
- `app/db.py` `resume_production_timing`
- `app/constants.py` `ACTIVE_TERMINAL_STATUSES`

Notes:

- Current `README.md` still says paused cards occupy a machine. The user clarified on 2026-06-18 that the desired behavior is different, so documentation and tests should be updated with the implementation.

Impact:

- Operators cannot pause one order and temporarily run another order on the same physical machine.

### 7. High - Released Cards Cannot Be Returned To The Unreleased Planning Pool

Reproduction:

1. Import and release a card to the workstation.
2. Open admin planning and admin card detail.
3. Try to return the card to an unreleased/imported planning state without cancelling.

Expected, based on clarified desired behavior:

- Shift manager should be able to unrelease a pending/released card back out of the workstation queue for later planning.
- This should be different from cancellation.

Actual:

- No unrelease/return action exists.
- Registered admin workflow routes include release, planning, cancel, and restore, but no unrelease route.
- Admin detail exposes cancel/restore only for this workflow state change.
- Cancelled cards are a different lifecycle state and remain marked as cancelled, which is not the same as “do this later.”

Evidence:

- Route inventory showed:
  - `/admin/cards/{card_id}/release`
  - `/admin/cards/{card_id}/planning`
  - `/admin/cards/{card_id}/cancel`
  - `/admin/cards/{card_id}/restore`
  - no unrelease/return-to-imported route
- Template review: `app/templates/admin_card_detail.html` exposes cancel/restore but no unrelease action.
- Template review: `app/templates/admin_planning.html` exposes release and replanning controls, but no unrelease control.

Likely code area:

- `app/main.py` admin workflow routes
- `app/db.py` card status transition helpers
- `app/templates/admin_card_detail.html`
- `app/templates/admin_planning.html`

Impact:

- Shift manager must misuse cancellation to remove a released pending card from the workstation queue.
- This makes scheduling/deferment semantically wrong and can hide cards from the workstation as if they were cancelled.

### 8. Medium - Admin Planning UI Repeats Per-Row Field Labels And Looks Cluttered

Reproduction:

1. Open `/admin/planning` with multiple unreleased cards and/or active queue cards.
2. Review the release/planning controls.

Expected:

- Planning should be fast to scan.
- Machine and sequence controls should be visually grouped with column/table headers, not repeated as bulky labels in every row.

Actual:

- The unreleased-card release form repeats labels inside every row:
  - `Макс. тегло ролка, кг`
  - `Ред`
  - `Машина`
- Queue cards use per-card controls without a compact table/header layout.
- This makes the planning screen visually heavy as the number of cards grows.

Evidence:

- `app/templates/admin_planning.html` lines 70-89 repeat labels inside each draft row.
- `app/templates/admin_planning.html` lines 119-127 render per-card machine/sequence controls in each queue card.
- Screenshot: `artifacts/ui-checks/full-workflow-audit-20260618/admin-planning-after-release.png`

Likely code area:

- `app/templates/admin_planning.html`
- `app/static/css/app.css`

Impact:

- The shift-manager planning screen is harder to scan and use than it needs to be, especially with several cards in the queue.

## Print Output Findings

Print status: **completed/stale after follow-up**.

The original audit print artifacts below captured the app before the later print-output fixes. Current app print output has since been browser/PDF verified and physically printed successfully. The generated operational card is near-perfect and works correctly from computers with correct print settings. A remaining case where one specific computer prints across two physical sheets is a local workstation/browser/printer-driver/settings problem and should be handled as environment troubleshooting, not as app print functionality.

What passed:

- Completed card print route returned printable output.
- Pending card print route was blocked.
- Generated PDF was exactly 2 pages.
- Generated PDF page size was A4.
- Back page contained 120 roll slots.
- Gross roll values, tare, total gross, total net, start, stop, and duration rendered.

Original failures, now stale:

- Front page content overlapped.
- Rich material data and notes do not reliably fit.
- Several labels and geometry differ from the reference PDF.

Artifacts:

- `source-files/print-template.pdf`
- `artifacts/ui-checks/print-template-reference-1.png`
- `artifacts/ui-checks/print-template-reference-2.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/print-completed-output.pdf`
- `artifacts/ui-checks/full-workflow-audit-20260618/print-completed-output-page-1.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/print-completed-output-page-2.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/print-blocked-pending-card.png`

## Tests And Checks Run

Commands:

```bash
source .venv/bin/activate && python -m pytest tests/test_print_output.py tests/test_admin_planning.py tests/test_admin_production_corrections.py tests/test_terminal_v8_render.py
source .venv/bin/activate && python -m pytest
source .venv/bin/activate && python -m compileall app
git diff --check
pdfinfo source-files/print-template.pdf
pdfinfo artifacts/ui-checks/full-workflow-audit-20260618/print-completed-output.pdf
pdftotext -layout source-files/print-template.pdf -
pdftotext -layout artifacts/ui-checks/full-workflow-audit-20260618/print-completed-output.pdf -
pdftoppm -png -r 120 source-files/print-template.pdf artifacts/ui-checks/print-template-reference
pdftoppm -png -r 120 artifacts/ui-checks/full-workflow-audit-20260618/print-completed-output.pdf artifacts/ui-checks/full-workflow-audit-20260618/print-completed-output-page
```

Results:

- Focused pytest subset: 95 passed.
- Full pytest suite: 209 passed.
- `compileall app`: passed.
- `git diff --check`: passed.
- Reference PDF: 2 A4 pages.
- App print PDF: 2 A4 pages.
- Follow-up paused-machine probe: current app blocked starting a second card while the first card was paused.

## Main Artifact Paths

- `artifacts/ui-checks/full-workflow-audit-20260618/audit-log.json`
- `artifacts/ui-checks/full-workflow-audit-20260618/import-overwrite-probe.json`
- `artifacts/ui-checks/full-workflow-audit-20260618/stale-extra-probe.json`
- `artifacts/ui-checks/full-workflow-audit-20260618/admin-import-result.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/admin-planning-after-release.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/planning-release-refresh.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/terminal-1920x950-active.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/terminal-queue-drawer.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/terminal-roll-delete-wrong-confirmation.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/terminal-after-finish.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/admin-completed-card-after-corrections.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/import-overwrite-refresh.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/stale-terminal-material.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/stale-terminal-roll.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/stale-admin-order.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/stale-admin-materials.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/stale-admin-roll.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/stale-admin-timing.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/stale-admin-planning.png`
- `artifacts/ui-checks/full-workflow-audit-20260618/print-completed-output.pdf`
- `artifacts/ui-checks/full-workflow-audit-20260618/followup-paused-probe.txt`

## Not Fully Tested

- SQLite backup/restore was not re-run in this workflow audit; it is covered by automated tests.
- Physical printer output was not tested during the original audit, but was later tested and accepted for the app. The remaining one-computer print pagination problem is environment-specific.
- 120-roll and 121-roll print boundary cases were not manually rendered during this audit.
- Mobile/tablet layouts were not a target; workstation was checked at `1920x950`.
- Direct Excel macro export was not exercised.
- Terminal tare stale-write was not separately tested after terminal roll stale-write; same backend version guard is used, but this exact form was not repeated in two-browser mode.

## Server Stop Confirmation

The temporary uvicorn server started on `127.0.0.1:8765` was stopped with Ctrl-C after all browser probes completed.
