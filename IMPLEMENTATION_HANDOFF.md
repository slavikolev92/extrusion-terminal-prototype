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

Latest relevant commits:

- `910627c Add production timing milestone`
- `8c8fd39 Add terminal card detail and conflict guard`
- `4a6018b Document baseline test command`
- `a735396 Add automated baseline tests`
- `a9ef5ed Document implementation governance`
- `5f946c1 Scaffold extrusion terminal prototype`

Current next milestone:

- Milestone 7 - Finish, Cancel, And History.

## First Read In A New Session

1. Read `README.md` fully enough to refresh the confirmed scope.
2. Read `AGENTS.md` for process, validation, test, and commit rules.
3. Read `IMPLEMENTATION_PLAN.md` and confirm Milestone 7 is still `next`.
4. Inspect current source under `app/` and tests under `tests/` before editing.

## Implemented App Shape

- One FastAPI app under `app/`.
- SQLite database initialized by `app.db`.
- Runtime database defaults to `data/extrusion_terminal.sqlite3`.
- `/admin` supports CSV import and release of ready imported cards to machine queues.
- `/terminal` shows the active queue and completed/cancelled section.
- `/terminal/cards/{card_id}` opens terminal card detail for released/completed/cancelled cards.
- Terminal machine tiles link to a running/paused card first, otherwise the next pending card.
- Terminal material fields are editable with a loaded `version` guard to block stale saves.
- Terminal tare and roll fields are editable with a loaded `version` guard to block stale saves.
- Roll entries are allowed only while a card is `running`.
- Roll numbers are assigned automatically per card; clearing an existing gross value stores it as blank and removes it from gross/net totals.
- Excel export macro lives under `excel-macros/` and is read-only with respect to workbook data.

## Test And Verification Commands

Use the local virtualenv:

- `.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests`
- `.\.test-runtime\codex-venv\Scripts\python.exe -m pytest`
- `git diff --check`

Current automated suite:

- `26 passed` after Milestone 6.
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

## Next Milestone Notes

Milestone 7 should add finish, cancel, and history behavior only:

- finish validation,
- finish closes any active timing segment,
- completed cards leave the active terminal queue,
- completed/cancelled cards remain available in history,
- cancellation without reason,
- cancelled cards reversible back to `pending`,
- completed cards remain editable as confirmed.

Keep this slice separate from backup/recovery and printing. Add focused tests before or alongside implementation, then run the required checks and commit the milestone.

## Guardrails

- Keep the scope extrusion-only.
- Do not add users, roles, login, or permissions.
- Do not write terminal-entered data back to Excel.
- Do not modify the Excel workbook unless explicitly asked.
- Do not expose the app to the public internet.
- Preserve imported order-card data separately from terminal-entered production data.
- Backend/database rules must enforce important invariants; UI checks alone are not enough.
