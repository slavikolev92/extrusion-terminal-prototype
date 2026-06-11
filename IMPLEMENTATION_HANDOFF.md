# Implementation Handoff

Start here for the first implementation session.

## First Read

1. Read `README.md` fully. Treat it as the authoritative project specification.
2. Inspect `ui-prototypes/workstation-v4.html`. Treat it as the current terminal UI reference, not as production code.
3. Do not commit the local Excel workbook. It belongs in `source-files/shift-manager-main-file.xlsm` locally and is ignored by git.

## Immediate Implementation Goal

Create the first working FastAPI + SQLite app skeleton for the extrusion terminal prototype.

The first deliverable should be a running local app with:

- FastAPI entrypoint
- SQLite database initialization
- seeded machine records `1` through `4`
- basic `/health`, `/admin`, and `/terminal` routes
- templates/static structure
- a concrete schema based on `README.md`

## Recommended Build Order

1. Scaffold the project structure.
2. Define the concrete SQLite schema:
   - orders/cards
   - machines
   - roll entries
   - production time segments
   - import batches
3. Implement status and validation constants:
   - draft/imported
   - pending
   - running
   - paused
   - completed
   - cancelled
4. Implement core backend rules:
   - machine assignment required before release
   - duplicate sequence validation within the same active machine queue
   - one running card per machine
   - re-import overwrites imported/front-card fields only
   - roll/timing data is preserved during re-import
5. Wire simple admin and terminal pages.
6. Adapt the V4 terminal mock into real templates only after the backend data shape is stable.

## Guardrails

- Keep the scope extrusion-only.
- Do not add users, roles, login, or permissions.
- Do not write back to the Excel workbook.
- Do not build the deferred roll-change timer.
- Do not build non-confirmed machine features.
- Do not expose the app to the public internet.
- Keep the implementation simple and inspectable.
