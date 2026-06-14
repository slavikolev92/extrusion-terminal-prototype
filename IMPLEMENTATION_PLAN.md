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
- block duplicate active sequence on the same machine.
- released card becomes `pending`.
- released card appears in terminal active queue.

Review checkpoint:

- release tested manually from `/admin`.
- released card visible in `/terminal`.
- duplicate sequence blocked in backend check.
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
- completed/cancelled cards remain separate from the active queue.
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

## Milestone 7 - Finish, Cancel, And History

Status: done

Scope:

- finish validation.
- finish closes active timing segment.
- completed cards leave active terminal queue.
- completed/cancelled cards appear in history/completed section.
- cancellation without reason.
- cancelled cards reversible back to `pending`.
- completed cards remain editable as confirmed.

Review checkpoint:

- finish blocked without tare, timing, or rolls.
- finish succeeds when requirements are met.
- cancelled card leaves active queue.
- cancellation reversal works.
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

2. Admin card index and full card detail/review - implementation, admin detail redesign correction, and automated checks complete; manual UI check pending
   - Add `/admin/cards` with basic filters: order number, customer, product, order/delivery date, and status.
   - Add `/admin/cards/{card_id}` showing the full operational card data, status, machine/sequence, timing, tare, rolls, and terminal material fields.
   - Make imported/front-card fields editable from the admin detail page.
   - Use loaded `version` conflict checks for admin edits.
   - Preserve production data when editing imported/front-card fields.
   - Add tests for admin detail fetch, imported-field editing, stale edit blocking, and preservation of rolls/timing/tare/status.
   - Manual check still pending: find a card, edit imported fields, verify terminal-entered data remains intact.

   Cleanup note: removed the redundant validation-status UI/product concept from Import, Planning, Cards, and admin card detail. Import outcomes now rely on Action/Message, while import, admin edit, and release still validate current extrusion fields server-side.

3. Planning, release, reassignment, and resequencing
   - Build `/admin/planning` around two views: unreleased ready card pool and four machine queues.
   - Release imported ready cards by assigning machine and sequence.
   - Allow shift manager to change machine and sequence after release for active cards.
   - Preserve backend protection against duplicate active machine sequence.
   - Preserve backend protection against assigning a running/paused card into an occupied machine conflict.
   - Show validation errors clearly near the affected card/queue action.
   - Add tests for release, reassignment, resequencing, duplicate sequence blocking, occupied machine blocking, and stale edit blocking.
   - Manual check: release multiple cards, reorder queues, move a card between machines, and verify terminal queue order.

4. Admin workflow controls and production-data correction
   - Add admin-side reversible cancel/restore using the same business rules as terminal cancel/restore.
   - Add admin editing for production-side correction fields needed before print: tare, roll gross weights, terminal material fields, and timing segments.
   - Keep completed cards editable, but preserve finish validation invariants needed for print readiness.
   - Implement the simplest timing correction workflow: edit segment start/end values, end reason, and recalculate totals; prevent invalid intervals and multiple open segments.
   - Use loaded `version` conflict checks for all correction forms.
   - Add tests for admin cancel/restore, roll/tare correction, timing correction, recalculated total time, invalid timing rejection, and stale edit blocking.
   - Manual check: correct a completed card's rolls and timing, then verify it remains ready for later print.

5. Pre-print workflow walkthrough and documentation update
   - Run a focused shift-manager workflow using temporary data: import, review, edit, plan, release, reassign/resequence, cancel/restore, correct production data.
   - Run a focused terminal workflow against those cards: queue selection, timing, rolls, finish, archive visibility.
   - Update `README.md`, `AGENTS.md`, and this plan if any accepted simplifications or changed behaviors are confirmed.
   - Run syntax/import checks, relevant automated tests, `git diff --check`, and a focused manual app check.
   - Commit Milestone 9 only after the non-print workflow is coherent and print-ready.

Milestone 9 commit strategy:

- Prefer one commit per implementation bundle if each bundle is complete and verified.
- Do not mix print output into any Milestone 9 commit.
- Do not leave a large uncommitted pile across multiple bundles.

## Milestone 10 - Print Output

Status: pending

Scope:

- create and agree the printable card template before final print implementation.
- completed-card print route.
- two A4 pages: extrusion front and back page.
- back page keeps 120-roll grid.
- include confirmed additions: start time, stop/finish time, tare weight, total gross weight, total net weight.
- print only allowed after completion.

Review checkpoint:

- print blocked before completion.
- completed card print view renders.
- output visually compared against Excel operational card.
- tests/manual print rehearsal pass.
- commit.

## Milestone 11 - Pilot Rehearsal

Status: pending

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
