# Implementation Handoff

Use this file when starting a fresh Codex session or moving to another machine. `README.md` remains the authoritative project specification. `AGENTS.md` contains the process rules. `IMPLEMENTATION_PLAN.md` is the milestone tracker.

## Current Repository State

Completed and committed:

- Milestone 0 - FastAPI + SQLite foundation.
- Milestone 1 - CSV import and read-only Excel export macro.
- Milestone 2 - Admin release to terminal queues.
- Milestone 3 - Automated baseline tests.
- Milestone 4 - Terminal card detail and first conflict guard.
- Milestone 5 - Production timing.
- Milestone 6 - Tare and roll entry.
- Milestone 7 - Finish, cancel, and history.
- Milestone 8 - Backup and recovery.

Latest relevant commits:

- `4788338 Add roll delete renumber correction`
- `f5ccbd3 Add backup and recovery milestone`
- `3f53dde Add finish cancel and history milestone`
- `d0ad54e Add tare and roll entry milestone`
- `910627c Add production timing milestone`
- `8c8fd39 Add terminal card detail and conflict guard`
- `4a6018b Document baseline test command`
- `a735396 Add automated baseline tests`
- `a9ef5ed Document implementation governance`
- `5f946c1 Scaffold extrusion terminal prototype`

Current next milestone:

- Milestone 9 - Pre-Print Workflow Completion.

## First Read In A New Session

1. Read `README.md` fully enough to refresh the confirmed scope.
2. Read `AGENTS.md` for process, validation, test, and commit rules.
3. Read `IMPLEMENTATION_PLAN.md` and confirm Milestone 9 - Pre-Print Workflow Completion is still `next`.
4. Inspect current source under `app/` and tests under `tests/` before editing.

## Implemented App Shape

- One FastAPI app under `app/`.
- SQLite database initialized by `app.db`.
- Runtime database defaults to `data/extrusion_terminal.sqlite3`.
- Backup files default to `backups/extrusion_terminal_YYYYMMDD_HHMMSS_microseconds.sqlite3`.
- Backup and restore commands live in `app.backups` and use SQLite's backup API.
- `/admin` supports CSV import and release of ready imported cards to machine queues.
- `/terminal` shows the active queue and completed/cancelled section.
- `/terminal/cards/{card_id}` opens terminal card detail for released/completed/cancelled cards.
- Terminal machine tiles link to a running/paused card first, otherwise the next pending card.
- Terminal material fields are editable with a loaded `version` guard to block stale saves.
- Terminal tare and roll fields are editable with a loaded `version` guard to block stale saves.
- Roll entries are allowed only while a card is `running`.
- Roll numbers are assigned automatically per card.
- Clearing an existing gross value stores it as blank and removes it from gross/net totals.
- Deleting a roll removes the row and automatically renumbers later rolls so the sequence remains continuous.
- Finish validates tare, at least one timing segment, at least one gross roll, and no empty roll gaps before filled rolls.
- Finish closes an active running segment with `finish`, sets `completed`, and moves the card to archive/history.
- Terminal cancellation sets `cancelled`, closes any open segment with `correction`, and moves the card to archive/history.
- Cancelled cards can be restored to `pending` with duplicate active machine/sequence protection.
- Excel export macro lives under `excel-macros/` and is read-only with respect to workbook data.

## Test And Verification Commands

Use the local virtualenv:

- `.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests`
- `.\.test-runtime\codex-venv\Scripts\python.exe -m pytest`
- `git diff --check`

Current automated suite:

- `53 passed` after roll delete/renumbering correction after Milestone 8.
- Tests use temporary SQLite databases and must not mutate `data/extrusion_terminal.sqlite3`.

When UI behavior changes, also run a focused manual app check with a temporary database. The previous Milestone 4 manual checks verified:

- selected terminal card detail renders,
- material fields save,
- stale material save is blocked,
- in-app browser view shows the terminal detail page and form correctly.

Milestone 6 manual check used a temporary SQLite database and verified:

- import and release a sample card,
- start timing,
- save order-level tare,
- add two gross rolls,
- clear one previous gross value,
- render/reload the terminal detail template,
- verify persisted totals after reload.

Post-Milestone 8 roll correction added:

- delete a roll from the terminal roll table,
- backend deletes the selected roll and renumbers later rolls in one transaction,
- stale delete requests are blocked by the loaded `version` guard,
- delete is allowed only where roll edits are allowed: `running` and `completed`,
- completed cards cannot delete or clear their final gross roll because completed cards must remain print-eligible.

Milestone 7 manual check used a temporary SQLite database and real HTTP routes on an in-process Uvicorn server. It verified:

- import/release a sample card,
- start timing,
- save tare,
- add a gross roll,
- finish the card,
- correct completed-card roll weights,
- verify it leaves the active queue and appears in completed/cancelled history,
- import/release another card,
- cancel it,
- restore it to `pending`,
- verify persistence after reload/render.

Milestone 8 manual check used a temporary SQLite database and verified:

- initialize a temp database,
- import/release a sample card,
- create a SQLite-safe timestamped backup,
- restore that backup into a different temp database path,
- query the restored database for the sample card,
- verify the real runtime database path was not the backup or restore target.

## Runtime And Ignored Files

Do not commit runtime/generated files:

- `data/`
- `extracts/`
- `source-files/extracts/`
- `.test-runtime/`
- `.venv/`
- workbook files under `source-files/`
- Excel lock/temp files

The local workbook, if present, belongs at:

- `source-files/shift-manager-main-file.xlsm`

## Completed Timing Notes

Milestone 5 added production timing only:

- start production timing,
- pause timing,
- resume timing,
- store timing in `production_time_segments`,
- enforce one running/paused occupied card per machine,
- calculate total production time from segments.

Keep future slices separate from this timing work.

## Completed Finish/Cancel Notes

Milestone 7 added finish, cancel, and history behavior only:

- finish validation,
- finish closes any active timing segment,
- completed cards leave the active terminal queue,
- completed/cancelled cards remain available in history,
- cancellation without reason,
- cancelled cards reversible back to `pending`,
- completed cards remain editable as confirmed.

Keep future slices separate from printing.

## Completed Backup/Recovery Notes

Milestone 8 added backup and recovery behavior only:

- `python -m app.backups backup` creates a SQLite-safe timestamped backup.
- `python -m app.backups restore --backup <path> --target <path>` restores through SQLite's backup API.
- default database path is `data/extrusion_terminal.sqlite3`.
- default backup directory is `backups/`.
- default retention keeps the newest `144` matching backup files.
- no scheduler, Windows Task Scheduler job, cron job, service, cloud backup, or UI was installed.

Keep future slices separate from print output.

## Next Milestone Notes

Milestone 9 should complete non-print workflow functionality before print output:

- walk through the shift-manager and terminal workflows with realistic exception cases,
- implement or explicitly confirm simplifications for admin card review/edit,
- implement or explicitly confirm simplifications for timing correction,
- implement or explicitly confirm simplifications for machine/sequence reassignment after release,
- implement or explicitly confirm simplifications for admin-side cancel/restore,
- resolve duplicate import and duplicate sequence UX expectations.

Keep Milestone 9 separate from print output.

Milestone 10 should add print output only:

- create and agree the printable card template before final print implementation,
- completed-card print route,
- two A4 pages: extrusion front and back page,
- back page keeps the 120-roll grid,
- include start time, stop/finish time, tare weight, total gross weight, and total net weight,
- print only allowed after completion.

Do not expand backup/recovery or add unrelated workflow changes in Milestone 10.

## Guardrails

- Keep the scope extrusion-only.
- Do not add users, roles, login, or permissions.
- Do not write terminal-entered data back to Excel.
- Do not modify the Excel workbook unless explicitly asked.
- Do not expose the app to the public internet.
- Preserve imported order-card data separately from terminal-entered production data.
- Backend/database rules must enforce important invariants; UI checks alone are not enough.
