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
- validation status `ready` or `no extrusion step`.
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
- block release unless card is `ready`.
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
- test no-extrusion validation.
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

Status: next

Purpose:

- Before building print output, walk through the complete shift-manager and terminal workflows as the real users would use them.
- Confirm which documented non-print requirements are still needed for the prototype and which are acceptable pilot simplifications.
- Implement the missing non-print functionality that affects operational correctness or print readiness.
- Keep this milestone scoped to workflow completion; do not implement print output here.

Known missing or unresolved items to review and bundle:

- Admin card review/edit:
  - imported drafts should be reviewable beyond the table row summary.
  - shift manager should be able to correct imported/front-card fields in-app when re-import is not the right tool.
  - edits should use simple conflict/version checks and preserve terminal-entered production data.
- Timing correction:
  - existing timing segments are currently read-only.
  - decide and implement the simplest correction workflow needed before printed start/finish/time values become official.
- Machine and sequence correction after release:
  - released cards currently show machine/sequence as read-only in the terminal detail.
  - implement reassignment/resequencing if it is needed for real production changes.
  - preserve backend protection against duplicate active machine sequence and invalid running-card conflicts.
- Admin-side cancel/restore:
  - terminal supports cancel/restore, but admin currently does not.
  - decide whether shift manager needs the same reversible cancellation controls before printing.
- Duplicate import and duplicate sequence UX:
  - current duplicate order imports are skipped unless overwrite is selected.
  - current duplicate active machine sequences are backend-blocked on release.
  - decide whether the README expectation for visible `duplicate` draft status or immediate duplicate sequence flagging should be implemented or documented as a pilot simplification.
- Workflow walkthrough:
  - run through expected shift-manager actions and terminal actions, including exception cases.
  - use findings to update this milestone before implementation if more non-print gaps are discovered.

Suggested implementation bundles:

1. Admin review/edit bundle:
   - card detail/review route for imported and released cards.
   - editable imported/front-card fields with version guard.
   - tests for preserving roll/timing/tare/status data.
2. Queue correction bundle:
   - machine/sequence reassignment for released active cards.
   - admin cancel/restore if confirmed.
   - tests for duplicate sequence, occupied machine, stale edits, and archive behavior.
3. Timing correction bundle:
   - minimal segment correction controls.
   - tests for recalculated total time, stale edits, and completed-card print-readiness.
4. Duplicate UX/documentation bundle:
   - implement duplicate draft/visual flag behavior if still required, or explicitly document current skip/overwrite behavior as the accepted pilot behavior.

Review checkpoint:

- walkthrough completed with the user or with user-confirmed scenarios.
- every remaining non-print README requirement is either implemented, moved into this milestone's implementation list, or explicitly documented as a pilot simplification after user confirmation.
- tests cover new backend validation and conflict behavior.
- focused manual workflow passes with temporary data.
- implementation stays separate from print output.
- commit.

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
