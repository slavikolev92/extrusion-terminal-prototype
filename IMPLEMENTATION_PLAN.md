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

Status: next

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

Status: pending

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

Status: pending

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

Status: pending

Scope:

- order-level tare input.
- fixed gross-weight input for next roll.
- Enter or Add saves immediately.
- roll numbers assigned automatically from `1`.
- previous gross weights editable.
- clearing/correcting roll weights behaves according to the confirmed pilot rules.
- total gross and total net shown.

Review checkpoint:

- roll entry blocked when card is not running.
- gross/net calculations verified.
- roll correction verified.
- persistence after page refresh verified.
- tests and manual workflow pass.
- commit.

## Milestone 7 - Finish, Cancel, And History

Status: pending

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

Status: pending

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

## Milestone 9 - Print Output

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

## Milestone 10 - Pilot Rehearsal

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
