# Milestone 9 Bundle 1 Prompt - Admin Navigation And Import UX

You are continuing work on the extrusion terminal pilot repository at:

`C:\Users\slavi\Dropbox (Personal)\03 KolevOOD\7 Extrusion Terminal Prototype`

The user has approved beginning Milestone 9, starting with Bundle 1: admin navigation and import UX cleanup.

This prompt is intended for a fresh Codex session with no prior conversation context. Read it fully, then read the required project files before editing.

## Required First Reads

Read these files in this order:

1. `AGENTS.md`
2. `README.md`
3. `IMPLEMENTATION_PLAN.md`
4. `.gitignore`
5. `pyproject.toml`

Then inspect the current implementation files:

- `app/main.py`
- `app/importer.py`
- `app/db.py`
- `app/constants.py`
- `app/rules.py`
- `app/templates/base.html`
- `app/templates/admin.html`
- `app/static/css/app.css`
- `tests/conftest.py`
- `tests/test_baseline.py`
- any other tests under `tests/` that touch admin/import/release behavior

Do not look for or rely on `IMPLEMENTATION_HANDOFF.md`; it was intentionally removed because `README.md`, `AGENTS.md`, and `IMPLEMENTATION_PLAN.md` are now the sources of truth.

## Current Context To Preserve

Milestones 0 through 8 are complete. Milestone 9 is now the active pre-print workflow completion milestone.

The user has explicitly accepted this import model:

- CSV import is persistent.
- There is no unsafe unsaved temporary import preview state.
- Import means "save these operational cards into the app database for review and planning."
- Release means "send this saved card to the workstation queue for production."
- Imported cards do not appear on `/terminal` until machine and sequence are assigned and release succeeds.
- Duplicate overwrite remains explicit and must update only Excel/imported operational-card fields.
- Overwrite must preserve production data: rolls, timing segments, tare, status, machine/sequence, and terminal material fields.

The user also accepted this target admin structure:

- `/admin/import` - CSV import, import result review, duplicate/overwrite clarity.
- `/admin/planning` - unreleased card pool plus four machine queues, release, later reassignment/resequencing.
- `/admin/cards` - searchable card index with filters, later bundle.
- `/admin/cards/{card_id}` - full card review/edit page, later bundle.
- `/admin` may redirect to `/admin/import` or show a simple navigation page.

The current implementation before this bundle is roughly:

- `GET /admin` renders one large `admin.html`.
- `POST /admin/import` imports immediately into the database.
- `POST /admin/cards/{card_id}/release` releases imported cards.
- The current admin page includes CSV import, imported drafts, recent imports, and machine plan all on one page.
- Import result is currently summarized as counts plus duplicate row numbers/errors.
- Duplicate import without overwrite is skipped.
- Duplicate import with overwrite updates imported fields only and preserves production data.
- Release already requires `ready` validation, machine, sequence, and blocks duplicate active machine sequence.
- Terminal workflow already exists and should not be changed in this bundle.

There may be already-approved housekeeping changes in the working tree from the prior session:

- `IMPLEMENTATION_HANDOFF.md` deleted.
- Excel macro files moved from top-level `excel-macros/` into `source-files/excel-macros/`.
- `.gitignore`, `source-files/README.md`, and `IMPLEMENTATION_PLAN.md` updated.
- `prompts/` may be untracked.

Do not revert those changes. Treat them as intentional unless the user explicitly says otherwise.

## Scope For This Session

Implement only Milestone 9 Bundle 1: admin navigation and import UX cleanup.

Goals:

1. Split the current one-page admin workflow into clearer admin sections/routes.
2. Keep import persistent on upload; do not add an unsaved temporary import queue.
3. Improve import result visibility so the shift manager can understand what happened per row/order.
4. Preserve all existing import/release behavior and backend invariants.
5. Do not implement admin card editing, reassignment/resequencing after release, timing correction, print output, or searchable card index yet.

Recommended route shape for this bundle:

- `GET /admin` should redirect to `/admin/import` or render a very small admin navigation page. Prefer redirect if it keeps the app simpler.
- `GET /admin/import` should show:
  - CSV upload form.
  - explicit overwrite checkbox.
  - recent import batches.
  - clear explanation through labels/buttons, not long instructional text.
  - after upload, a detailed result table for the uploaded CSV.
- `POST /admin/import` should process the CSV and return the import page with the detailed result.
- `GET /admin/planning` should preserve the currently working planning/release functionality:
  - unreleased imported/draft cards.
  - release form with machine and sequence.
  - active machine queues.
- `POST /admin/cards/{card_id}/release` should continue to work, but should return/render the planning page instead of the old combined admin page.

If implementing `/admin/planning` in this bundle requires moving existing draft/release/machine-plan markup out of `admin.html`, do it. Keep the UI simple and consistent with existing styles.

Do not create broken navigation links to future routes unless you implement a harmless placeholder page. Prefer linking only to routes that exist in this bundle.

## Import Result Detail Requirement

The current `ImportResult` only exposes aggregate counters plus `duplicate_rows` and `row_errors`. For this bundle, add enough structured result detail to show a table after import.

The table should make these outcomes obvious:

- created new card
- updated existing card because overwrite was selected
- skipped duplicate because overwrite was not selected
- imported but flagged `no extrusion step`
- skipped row because `order_number` is missing
- skipped duplicate row inside the same CSV
- blocked file-level errors such as missing required columns

Prefer adding a small dataclass such as `ImportRowResult` in `app/importer.py` rather than parsing human-readable strings in the template.

Each row result should include, where available:

- CSV row number
- order number
- outcome/action such as `created`, `updated`, `skipped`
- validation status such as `ready` or `no extrusion step`
- a short message

Keep existing aggregate fields for compatibility with tests and templates unless there is a strong reason to change them.

Important: an imported row with `no extrusion step` is still saved as an imported card but cannot be released. That behavior currently exists and should remain.

## Backend Rules To Preserve

- Import must persist cards immediately.
- Duplicate import without overwrite must not change the existing card.
- Duplicate import with overwrite must update only imported/front-card fields.
- Overwrite must preserve:
  - status
  - machine assignment
  - machine sequence
  - tare weight
  - roll entries
  - production time segments
  - terminal material fields
  - workflow timestamps
- Release must require validation status `ready`.
- Release must require machine and sequence.
- Release must block duplicate active sequence within the same machine queue.
- Tests must use temporary SQLite database paths and must not mutate `data/extrusion_terminal.sqlite3`.

## UI Guidance

This is a temporary prototype admin tool, not a full ERP dashboard.

Keep the UI work-focused:

- clear top navigation between admin sections and terminal
- compact tables
- visible status pills/messages
- no marketing-style layout
- no large hero/dashboard treatment
- no nested cards
- keep form controls stable and simple

Use the existing server-rendered templates and CSS style. Do not introduce a frontend framework.

## Suggested Implementation Steps

1. Check current status:

```powershell
git status --short
```

2. Read the required files listed above.

3. Refactor admin context helpers in `app/main.py` if useful:

- import page context
- planning page context
- shared admin navigation context if needed

4. Split templates:

- keep or replace `admin.html` as a small navigation/redirect target
- add `admin_import.html`
- add `admin_planning.html`
- optionally add a shared admin nav snippet only if it avoids real duplication

5. Add structured row-level import results in `app/importer.py`.

6. Update `POST /admin/import` to render `/admin/import` view with the detailed result.

7. Update release POST to render the planning view.

8. Add or update tests:

- importer returns row-level result for created row
- importer returns row-level result for no-extrusion row
- duplicate without overwrite is row-reported as skipped and preserves existing data
- duplicate with overwrite is row-reported as updated and preserves production data
- missing order number is row-reported as skipped/error
- route-level smoke tests for `GET /admin`, `GET /admin/import`, and `GET /admin/planning` if the current test stack supports FastAPI `TestClient`

If route tests require adding only standard FastAPI/Starlette test support that is already available, add them. Do not add new dependencies unless necessary.

9. Run checks:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

If the local venv is missing or broken, inspect the repo setup and ask the user before doing dependency installation.

10. Manual app check, if feasible:

- Start the app with a temporary database path if practical.
- Open `/admin/import`.
- Import a CSV containing:
  - one new ready row
  - one no-extrusion row
  - one duplicate row without overwrite
  - one duplicate row with overwrite in a second pass
- Verify the import result table is understandable.
- Open `/admin/planning`.
- Verify imported ready cards and machine queues are visible.
- Release a ready card and verify it appears in `/terminal`.

Do not mutate the real runtime database for manual checks unless the user explicitly asks.

## Documentation Updates

Update `IMPLEMENTATION_PLAN.md` only if useful to record Bundle 1 completion or clarify the next bundle. Do not mark Milestone 9 done.

Update `README.md` or `AGENTS.md` only if the implementation changes documented behavior. The accepted import behavior is already represented in the Milestone 9 plan, but if README wording conflicts with the final implementation, adjust it carefully.

## Commit Guidance

This session should finish Bundle 1 end-to-end if feasible:

- implementation
- tests
- manual check if UI changed and feasible
- review
- commit

Before committing, run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

Use a milestone/bundle-level commit message such as:

```text
Improve admin import workflow
```

If `.git` writes require escalation, request approval for the exact Git action. Do not use destructive Git commands.

Do not include print output in this bundle.

