# Implementation Plan

This plan tracks implementation milestones for the extrusion terminal pilot. `README.md` remains the authoritative specification. Each milestone should be reviewed, verified, and committed before moving to the next one.

## Milestone 0 - Foundation

Status: done

Scope:

- FastAPI app entrypoint.
- SQLite database initialization.
- seeded machines `1` through `4`.
- basic `/health`, `/admin`, and `/terminal` routes.
- templates/static structure.
- schema for cards, machines, roll entries, production time segments, and import batches.

Review checkpoint:

- syntax/import checks pass.
- database initializes.
- routes return `200`.
- commit completed.

## Milestone 1 - CSV Import And Excel Export

Status: done

Scope:

- admin CSV upload.
- app-ready CSV template.
- imported cards persist with `imported` status.
- saved cards are checked directly for usable extrusion data; no-extrusion rows are reported and skipped.
- duplicate order numbers skipped by default.
- overwrite option updates imported fields only.
- read-only Excel `.bas` export macro.
- macro exports selected `Database` rows into timestamped CSV files.

Review checkpoint:

- macro-tested with real workbook rows.
- imported rows verified in `/admin`.
- duplicate import behavior verified.
- production data preservation verified in backend checks.
- commit completed.

## Milestone 2 - Admin Release To Terminal

Status: done

Scope:

- machine selection on imported draft rows.
- numeric machine sequence input.
- release one card at a time.
- block release unless the current card fields represent usable extrusion work.
- block invalid machine/sequence.
- prevent persisted duplicate active sequence on the same machine.
- released card becomes `pending`.
- released card appears in terminal active queue.

Review checkpoint:

- release tested manually from `/admin`.
- released card visible in `/terminal`.
- duplicate active sequence prevented by backend check.
- commit completed with Milestones 0-2.

## Milestone 3 - Automated Baseline Tests

Status: done

Scope:

- add a focused test runner and test structure.
- test database initialization.
- test CSV import success.
- test no-extrusion rows are reported and skipped.
- test duplicate import skip.
- test overwrite import preservation.
- test release success.
- test release validation failures.
- test duplicate active machine sequence blocking.

Review checkpoint:

- tests run from a clean command.
- tests use temporary SQLite database paths.
- no test mutates the real runtime database.
- commit after tests pass.

## Milestone 4 - Terminal Card Detail And Conflict Guard

Status: done

Scope:

- clicking a queued card opens its detail view.
- machine quick tile opens running/paused card if present, otherwise next pending card.
- detail view shows imported operational-card fields needed by operators.
- terminal does not expose `/admin` navigation.
- completed cards remain separate from the active queue; cancelled cards are not shown to workstation operators.
- forms/actions carry the loaded card version or `updated_at` value.
- stale edits are blocked with a reload warning instead of silently overwriting newer data.

Review checkpoint:

- released cards can be opened from terminal.
- machine tile navigation works.
- no production data is changed by read-only viewing.
- stale edit protection is verified for the first editable card action introduced in this milestone or the next editable milestone.
- tests and manual workflow pass.
- commit.

## Milestone 5 - Production Timing

Status: done

Scope:

- start production timing.
- pause timing.
- resume timing.
- one running card per machine.
- timing stored as production time segments.
- total time calculated from segments, excluding pauses.
- actions persist immediately.

Review checkpoint:

- start creates an open segment.
- pause closes current segment.
- resume creates a new segment.
- duplicate running card on a machine is blocked.
- tests and manual workflow pass.
- commit.

## Milestone 6 - Tare And Roll Entry

Status: done

Scope:

- order-level tare input.
- fixed gross-weight input for next roll.
- Enter or Add saves immediately.
- roll numbers assigned automatically from `1`.
- previous gross weights editable.
- clearing/correcting roll weights behaves according to the confirmed pilot rules.
- roll deletion renumbers remaining rolls automatically.
- total gross and total net shown.

Review checkpoint:

- roll entry blocked when card is not running.
- gross/net calculations verified.
- roll correction verified.
- persistence after page refresh verified.
- tests and manual workflow pass.
- commit.

## Milestone 7 - Finish, Cancellation, And History

Status: done

Scope:

- finish validation.
- finish closes active timing segment.
- completed cards leave active terminal queue.
- completed cards appear in the workstation completed section.
- cancellation without reason remains supported for shift-manager/admin.
- cancelled cards are reversible back to `pending` from admin.
- completed cards remain editable as confirmed.

Review checkpoint:

- finish blocked without tare, timing, or rolls.
- finish succeeds when requirements are met.
- cancelled card leaves active queue.
- admin cancellation reversal works.
- tests and manual workflow pass.
- commit.

## Milestone 8 - Backup And Recovery

Status: done

Scope:

- SQLite-safe backup behavior.
- timestamped backups.
- simple retention policy.
- documented restore procedure.
- documented startup/restart procedure.

Review checkpoint:

- backup can be created while app is running.
- restore tested against a backup copy.
- docs are clear enough for non-developer recovery.
- commit.

## Milestone 9 - Pre-Print Workflow Completion

Status: in progress

Current state:

- The pre-print workflow and live V8 workstation connection have been implemented.
- The app has been launched and accessed successfully.
- Milestone 9 remains open because V8 workstation bugs and edge cases were observed after launch and must be fixed before print output starts.

Confirmed direction:

- CSV import is persistent, not an unsaved temporary preview state.
- Import means "save these operational cards into the app database for review and planning."
- Release means "send this saved card to the workstation queue for production."
- Imported cards do not appear on `/terminal` until machine and sequence are assigned and release succeeds.
- Duplicate overwrite remains explicit and must update only Excel/imported operational-card fields, preserving production data.
- The admin side should be structured as a temporary but clear prototype tool, not a large ERP dashboard.
- Keep print output out of Milestone 9.

Target admin structure:

- `/admin/import` - CSV import, import result review, duplicate/overwrite clarity.
- `/admin/planning` - unreleased card pool plus four machine queues, release, reassignment, resequencing.
- `/admin/cards` - searchable card index with filters.
- `/admin/cards/{card_id}` - full card review/edit page for shift-manager corrections.
- `/admin` may redirect to `/admin/import` or show a simple navigation page.

Implementation bundles:

1. Admin navigation and import UX cleanup - done
   - Split the current one-page `/admin` workflow into clear admin sections/routes.
   - Keep import persistent on upload; do not create an unsaved temporary import queue.
   - Show an import result table that makes created, skipped duplicate, overwritten, skipped no-extrusion, and row-error outcomes obvious.
   - Keep overwrite as an explicit checkbox/action.
   - Preserve current backend behavior that overwrite updates imported/front-card fields only.
   - Add or update tests for duplicate skip/overwrite result reporting and production-data preservation.
   - Manual check: import a CSV with new, duplicate, overwrite, and skipped no-extrusion rows.

2. Admin card index and full card detail/review - done
   - Add `/admin/cards` with basic filters: order number, customer, product, order/delivery date, and status.
   - Add `/admin/cards/{card_id}` showing the full operational card data, status, machine/sequence, timing, tare, rolls, and terminal material fields.
   - Make imported/front-card fields editable from the admin detail page.
   - Use loaded `version` conflict checks for admin edits.
   - Preserve production data when editing imported/front-card fields.
   - Add tests for admin detail fetch, imported-field editing, stale edit blocking, and preservation of rolls/timing/tare/status.
   - Manual admin-detail behavior was covered later by the broader pre-print workflow walkthrough; no separate pending admin-detail check remains recorded.

   Cleanup note: removed the redundant validation-status UI/product concept from Import, Planning, Cards, and admin card detail. Import outcomes now rely on Action/Message, while import, admin edit, and release still validate current extrusion fields server-side.

3. Planning, release, reassignment, and resequencing - done
   - Build `/admin/planning` around two views: unreleased ready card pool and four machine queues.
   - Release imported ready cards by assigning machine and target queue position.
   - Allow shift manager to change machine and target queue position after release for active cards.
   - Normalize affected active machine queues to contiguous positions starting at `1`.
   - Preserve backend protection against persisted duplicate active machine sequence.
   - Preserve backend protection against assigning a running/paused card into an occupied machine conflict.
   - Show validation errors clearly near the affected card/queue action.
   - Add tests for release, reassignment, resequencing, sequence normalization, occupied machine blocking, and stale edit blocking.
   - Manual check complete with a temporary database: release multiple cards, resequence a queue, move a pending card between machines, normalize sequence gaps, and verify terminal queue order.

3a. Terminal sync awareness - done
   - Added a read-only `/terminal/snapshot` endpoint for active queue and selected-card version/status checks.
   - `/terminal` now polls for queue or selected-card changes and refreshes automatically only when no operator input is focused or dirty.
   - If updates arrive while the operator is typing, the terminal shows an updates-available banner with a manual refresh button.
   - Existing `loaded_version` conflict checks remain the authoritative stale-write protection.

4. Admin workflow controls and production-data correction - done
   - Add admin-side reversible cancel/restore using the same business rules as terminal cancel/restore.
   - Add admin editing for production-side correction fields needed before print: tare, roll gross weights, terminal material fields, and timing segments.
   - Keep completed cards editable, but preserve finish validation invariants needed for print readiness.
   - Implement the simplest timing correction workflow: edit segment start/end values, end reason, and recalculate totals; prevent invalid intervals and multiple open segments.
   - Use loaded `version` conflict checks for all correction forms.
   - Add tests for admin cancel/restore, roll/tare correction, timing correction, recalculated total time, invalid timing rejection, and stale edit blocking.
   - Manual check complete with a temporary database: corrected terminal material fields, tare, roll gross weight, timing segment data, and admin cancel/restore behavior from the admin detail page.

5. Pre-print workflow walkthrough and documentation update - done
   - Run a focused shift-manager workflow using temporary data: import, review, edit, plan, release, reassign/resequence, cancel/restore, correct production data.
   - Run a focused terminal workflow against those cards: queue selection, timing, rolls, finish, archive visibility.
   - Update `README.md`, `AGENTS.md`, and this plan if any accepted simplifications or changed behaviors are confirmed.
   - Run syntax/import checks, relevant automated tests, `git diff --check`, and a focused manual app check.
   - Technical walkthrough complete with a temporary database: import, admin review/edit, planning/resequence, terminal timing/tare/roll/finish, archive visibility, stale-write blocking, admin production correction, admin cancel/restore, and running-card timing invariant checks passed.

6. Workstation V8 terminal UI connection
   - Slice 1 data contract complete: optional `max_roll_weight` is now shift-manager-entered card data with SQLite schema/migration support, admin/planning entry, admin and terminal detail fetches, and focused tests. CSV import leaves it blank, re-import preserves it, and release still requires machine sequence.
   - Slice 3 live terminal connection complete: `/terminal` now uses a server-rendered V8 workstation layout based on `ui-prototypes/workstation-v8.html`, with live four-machine navigation, selected-card detail, recipe rows, material correction fields, tare/roll controls, totals, active queue drawer, completed lookup, and sync banner behavior.
   - Treat `ui-prototypes/workstation-v7.html` as the checkpoint before the top-machine-navigation restructure; do not reconnect V4.
   - Preserve existing backend routes, database rules, loaded-version conflict checks, terminal sync awareness, and production invariants.
   - Prototype demo data/client-only card switching has been removed from the live route; queue and completed rows are navigation-only links that load full server-rendered card state.
   - Do not expose card cancellation or restore controls on the workstation; shift-manager/admin remains responsible for cancellation and restoration.
   - The maximum roll weight field is visible in the live workstation detail pane as read-only operator information.
   - Focused V8 render tests were added for route rendering, machine controls, live selected-card fields, max roll weight, queue/completed content, cancelled-card absence, versioned write forms, and absence of workstation cancel/restore controls.
   - Slice 3 verification passed with syntax/import checks, the full automated suite, `git diff --check`, and a focused in-app browser manual check with a temporary database.
   - The app has been launched/accessed successfully with the live V8 workstation, and the follow-up hardening/admin cleanup work has been completed enough to move into print output.

7. Admin completed-card detail redesign - done
   - `/admin/cards/{card_id}` now uses a compact summary-first correction layout.
   - Order/imported fields are edited in one compact order-details form.
   - Separate recipe and machine-material sections were replaced by one unified materials ledger with a section-level save.
   - Duplicated read-only roll display and per-roll correction forms were replaced by one roll ledger with tare, roll edits, deletes, and new-roll entry.
   - Duplicated timing display and per-segment correction forms were replaced by one timing ledger with segment edits, deletes, and new-segment entry.
   - System data is collapsed into a lower-emphasis details section, while admin cancel/restore and imported-card delete behavior remain available.
   - Section-level material, roll, and timing saves preserve loaded-version conflict checks and production-data invariants.
   - Verification passed with focused redesign tests, existing admin/production behavior suites, the full Python suite, `git diff --check`, and Playwright screenshots against a temporary database.
   - This closes the pre-print admin correction cleanup needed before print output starts.

8. Admin completed-card detail cleanup - done
   - Order details were grouped into order, client, product, operations, and notes subsections while keeping one save action.
   - The materials ledger now keeps row-level material data in the table and no longer exposes the legacy `Марка / клас` field in the admin UI.
   - Roll and timing deletion now use explicit red X row actions with confirmation prompts instead of checkbox-plus-save deletion.
   - Admin detail POST actions return to section anchors for order, materials, rolls, and timing.
   - Verification passed with focused render/backend tests, the full Python suite, `git diff --check`, and Playwright screenshots against a temporary database.

Milestone 9 commit strategy:

- Prefer one commit per implementation bundle if each bundle is complete and verified.
- Do not mix print output into any Milestone 9 commit.
- Do not leave a large uncommitted pile across multiple bundles.

## Milestone 10 - Print Output

Status: complete and accepted for the app; physical printer rehearsal confirmed app output is excellent

Scope:

- completed-card print/reprint route implemented as `GET /cards/{card_id}/print`.
- terminal completed-card print action opens `/cards/{card_id}/print?auto=1` and calls browser print.
- admin completed-card print/reprint access exists from card detail and the admin card list.
- print route uses app data and server-rendered HTML/CSS; it does not fill or print from Excel at runtime.
- output renders exactly two A4 portrait pages: extrusion front card and roll/summary back page.
- front page preserves the extrusion-card structure and has been tuned against `source-files/print-template.pdf`: order/header fields, product/quantity rows, extrusion requested fields, split planned/actual material blocks, notes/packaging, and blank legacy boxes for `ШПУЛИ`, `БРАК`, and `ФОЛИО [kg]`.
- corrective template-fidelity pass rebuilt the front page as a fixed Excel-like HTML table skeleton so blank template cells remain visible instead of being omitted when no app data exists.
- back page keeps the three-group 120-roll grid with blank `Дата / смяна` cells and blank per-group `Общо` rows.
- final back-page polish restored the header as a two-row table, narrowed `Дата / смяна`, centered roll gross `кг.` values, and restored separate left/right timing and weight summary tables.
- roll grid prints gross weights only.
- summary prints start, stop, active production duration excluding pauses, tare, total gross, and total net.
- print readiness is rechecked at print time and blocks missing critical production data, non-completed/cancelled cards, open timing segments, and more than 120 rolls.
- app-only workflow fields such as machine, sequence, status, queue position, internal card id, and max roll weight are not printed.

Verification completed:

- `source .venv/bin/activate && python -m pytest` passed: 194 tests.
- `git diff --check` passed.
- temporary-DB browser verification used `.test-runtime/print-ui-check/extrusion_terminal_print_verify.sqlite3`, not `data/extrusion_terminal.sqlite3`.
- Playwright/browser artifacts:
  - `artifacts/ui-checks/print-output-preview.png`
  - `artifacts/ui-checks/print-output-preview.pdf`
- `pdfinfo artifacts/ui-checks/print-output-preview.pdf` reported 2 pages and A4 page size.
- Browser verification checked two print pages, front/back landmarks, 120 roll rows, blank date/shift cells, gross-only roll values, summary labels, front labels, and app-only field absence.
- Template-fidelity pass added repeatable local verification helpers:
  - `scripts/create_print_template_fixture.py` creates a dense completed-card fixture only under `.test-runtime/`.
  - `scripts/render_print_template.mjs` renders the print route to browser screenshots, PDF, page PNGs, and `pdfinfo` metadata only under `artifacts/ui-checks/`.
- Additional template-fidelity artifacts from temporary-DB browser/PDF checks:
  - `artifacts/ui-checks/template-reference/print-template-1.png`
  - `artifacts/ui-checks/template-reference/print-template-2.png`
  - `artifacts/ui-checks/template-tuning/front-pass-4/current-print-output.pdf`
  - `artifacts/ui-checks/template-tuning/front-pass-4/current-print-output-1.png`
  - `artifacts/ui-checks/template-tuning/front-pass-4/current-print-output-2.png`
  - `artifacts/ui-checks/template-tuning/front-pass-4/current-print-output.metadata.json`
- Corrective front-grid pass artifacts from temporary-DB browser/PDF checks:
  - `artifacts/ui-checks/template-tuning/front-grid-final-r2/current-print-output.pdf`
  - `artifacts/ui-checks/template-tuning/front-grid-final-r2/current-print-output-1.png`
  - `artifacts/ui-checks/template-tuning/front-grid-final-r2/current-print-output-2.png`
  - `artifacts/ui-checks/template-tuning/front-grid-final-r2/current-print-output.metadata.json`
- Final review found no Critical or Important findings. One Minor renderer containment finding was fixed so rejected output directories outside `artifacts/ui-checks/` do not create outside parent directories.
- Final review verification:
  - `source .venv/bin/activate && python -m pytest tests/test_print_output.py tests/test_print_template_fixture_script.py` passed: 45 tests.
  - `source .venv/bin/activate && python -m pytest` passed: 209 tests.
  - `git diff --check` passed.
  - temporary-DB browser verification used `.test-runtime/print-final-review/extrusion_terminal.sqlite3`, not `data/extrusion_terminal.sqlite3`.
  - runtime DB safety check found no fixture rows matching `PRINT-TEMPLATE-%`, `27033`, or `27034` in `data/extrusion_terminal.sqlite3`.
- Final review artifacts from temporary-DB browser/PDF checks:
  - `artifacts/ui-checks/template-tuning/final-review/current-print-output.pdf`
  - `artifacts/ui-checks/template-tuning/final-review/current-print-output-1.png`
  - `artifacts/ui-checks/template-tuning/final-review/current-print-output-2.png`
  - `artifacts/ui-checks/template-tuning/final-review/current-print-output.metadata.json`
- Physical printer calibration:
  - Physical printed output was reviewed and accepted as near-perfect for the operational card.
  - The app-generated print functionality is considered complete and working correctly.
  - One workstation/computer still prints the app output across two physical sheets while other computers print it correctly; this is treated as a local computer/browser/printer-driver/settings issue, not an application print-output defect.

Accepted v1 deviations / notes:

- Browser print/PDF rendering is the v1 output path; silent/kiosk printing remains deployment configuration, not application behavior.
- Excel template fidelity deviations accepted for v1:
  - The output is rebuilt as HTML/CSS instead of using Excel cell geometry at runtime.
  - The tuned output is visually close to the reference PDF but is not a pixel-perfect Excel clone.
  - Margins are intentionally smaller than the reference PDF where that helps preserve clean two-page output.
  - The front page now uses fixed table geometry for visible template boxes, including blank legacy/template-only cells.
  - Back-page roll cells print gross weight only.
  - App-added production summary values are placed in the existing back-page summary area as separate timing and weight blocks.
  - Legacy front-page sections without confirmed app data remain visually present but blank.
- Browser margin handling:
  - The print CSS uses `@page { size: A4 portrait; margin: 0; }` and each `.print-page` defines its own internal padding.
  - Browser print headers/footers must be disabled in the browser/printer dialog to preserve the two-page layout.
  - Duplex/front-back handling depends on printer/browser settings and is not controlled by the app.
- Text wrapping/shrinking behavior:
  - Long text wraps inside fixed boxes with `overflow-wrap`; sections are not expanded beyond the two-page structure.
  - No dynamic shrink-to-fit algorithm is implemented in v1; physical calibration did not identify an app-level text-fit blocker.
- Printer setup notes:
  - Use A4 portrait, default scale/100%, print backgrounds enabled, and browser headers/footers disabled.
  - Silent/kiosk printing remains a future deployment configuration after the physical terminal environment is known.
  - If a specific workstation prints the two app pages onto more physical sheets than expected, troubleshoot that workstation's browser print scaling, page size, margins, printer driver, and OS print settings outside the app.

Review checkpoint:

- software implementation, template-fidelity pass, PDF/browser rehearsal, and physical printer output are accepted for app readiness.
- any remaining printer behavior is workstation/printer-environment setup, not app print-output work.
- commit only when explicitly requested.

## Milestone 11 - Pilot Rehearsal

Status: pending

Completed audit follow-up before rehearsal:

- Implemented pending-card return-to-planning behavior from full workflow audit issue #7: pending cards can be returned to the unreleased planning pool with version checks, queue normalization, terminal removal, and admin planning/detail controls. Started cards (`running` or `paused`) remain in execution and cannot be returned to the pool.
- admin planning unreleased-queue cleanup: compact single-row release table, delivery-date column, scoped control sizing, and PRG anchor return after release.
- terminal recipe-field autosave/silent data-loss prevention: dirty recipe fields save through the existing materials form POST on Enter or first attempted exit from the recipe area, first dirty external clicks save instead of navigating or firing actions, and browser refresh/close uses the native unsaved-change warning as a fallback.

Verification completed for this follow-up:

- `python -m pytest tests/test_admin_planning.py -k unrelease -q` passed.
- `python -m pytest tests/test_admin_planning.py tests/test_production_timing.py -q` passed.
- `python -m pytest tests/test_admin_routes.py -k "unrelease or routes_are_registered" -q` passed.
- `python -m pytest tests/test_admin_routes.py tests/test_admin_planning.py -q` passed.
- `python -m pytest tests/test_admin_routes.py -q` passed.
- `python -m pytest tests/test_terminal_sync.py -q` passed.
- `python -m pytest tests/test_admin_planning.py tests/test_admin_routes.py tests/test_terminal_sync.py -q` passed.
- `python -m pytest` passed.
- `python -m compileall app` passed.
- `git diff --check` passed.
- Live Playwright check against temporary SQLite database `.test-runtime/unrelease-ui/extrusion_terminal-issue7-20260619-001.sqlite3` passed: imported two ready cards, released both to one machine, confirmed terminal visibility, returned one pending card to the unreleased pool from `/admin/planning`, confirmed queue normalization and terminal removal, started the remaining card, confirmed `/admin/cards/{id}` did not show return-to-planning for the running card, and confirmed `/terminal/snapshot` marked the returned selected card missing. Screenshot: `artifacts/ui-checks/pending-unrelease-planning.png`.
- terminal recipe autosave verification passed: focused render/detail/sync tests and full Python suite passed, `git diff --check` passed, and Playwright against temporary SQLite database `.test-runtime/terminal-recipe-autosave/extrusion_terminal.sqlite3` verified first dirty machine click saved recipe fields and stayed on the card, while the second click navigated. Screenshot: `artifacts/ui-checks/terminal-recipe-autosave/recipe-autosave-persisted.png`.

Scope:

- run full workflow with real exported workbook rows.
- import, release, execute, pause/resume, enter rolls, finish, print.
- restart server and verify persisted state.
- verify backup/restore.
- document known limitations and operator instructions.

Review checkpoint:

- full workflow completes without code changes during the rehearsal.
- user accepts pilot readiness or identifies required fixes.
- final pre-pilot commit.
