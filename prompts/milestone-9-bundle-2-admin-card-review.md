# Milestone 9 Bundle 2 Prompt - Admin Card Index And Review

You are continuing work on the extrusion terminal pilot repository at:

`C:\Users\slavi\Dropbox (Personal)\03 KolevOOD\7 Extrusion Terminal Prototype`

The user has approved continuing Milestone 9 with Bundle 2: admin card index and full card detail/review.

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
- `app/db.py`
- `app/importer.py`
- `app/constants.py`
- `app/rules.py`
- `app/templates/base.html`
- `app/templates/_admin_nav.html`
- `app/templates/admin_import.html`
- `app/templates/admin_planning.html`
- `app/templates/terminal.html`
- `app/static/css/app.css`
- `tests/conftest.py`
- `tests/test_baseline.py`
- `tests/test_admin_routes.py`
- any other tests under `tests/` that touch terminal card detail, conflict/version checks, roll/timing preservation, or release behavior

Do not look for or rely on `IMPLEMENTATION_HANDOFF.md`; it was intentionally removed because `README.md`, `AGENTS.md`, and `IMPLEMENTATION_PLAN.md` are the sources of truth.

## Current Context To Preserve

Milestones 0 through 8 are complete. Milestone 9 is in progress.

Bundle 1 is complete and committed:

- `1ac6f5f Improve admin import workflow`
- `f820c19 Skip non-extrusion import rows`

Bundle 1 created:

- `/admin` redirects to `/admin/import`.
- `/admin/import` handles CSV upload, overwrite checkbox, recent imports, and row-level import result detail.
- `/admin/planning` shows unreleased cards and four machine queues, and keeps the existing release workflow.
- The admin section nav links only to `Import` and `Planning`; the top-right `Terminal` link remains as a shift-manager verification shortcut.
- No-extrusion CSV rows are reported in the import result as skipped and are not saved as cards.
- Duplicate import without overwrite is skipped.
- Duplicate import with overwrite updates imported/front-card fields only and preserves production data.

There may be already-approved housekeeping changes in the working tree:

- `IMPLEMENTATION_HANDOFF.md` deleted.
- Excel macro files moved from top-level `excel-macros/` into `source-files/excel-macros/`.
- `.gitignore` and `source-files/README.md` updated.
- `prompts/` may be untracked.

Do not revert those changes. Treat them as intentional unless the user explicitly says otherwise.

## Scope For This Session

Implement only Milestone 9 Bundle 2: admin card index and full card detail/review.

Goals:

1. Add `/admin/cards`, a searchable/filterable card index.
2. Add `/admin/cards/{card_id}`, a full admin review/detail page.
3. Show imported operational-card data, workflow/status data, machine/sequence, timing summary/segments, tare, rolls, and terminal material fields on the detail page.
4. Allow shift manager/admin to edit imported/front-card fields from the detail page.
5. Use loaded `version` conflict checks for admin edits.
6. Preserve all production-side data when editing imported/front-card fields.
7. Keep the implementation simple, server-rendered, and SQLite-backed.

Do not implement in this bundle:

- reassignment/resequencing after release
- changing machine or sequence for active/released cards
- admin-side cancel/restore controls
- admin editing of tare, rolls, terminal material fields, or timing segments
- print output
- login/users/permissions
- complex merge UI for stale edits

Those are later Milestone 9 bundles.

## Route Shape

Add:

- `GET /admin/cards`
  - shows a card index table
  - supports basic filters through query parameters
  - links each row to `/admin/cards/{card_id}`

- `GET /admin/cards/{card_id}`
  - shows a full card review/detail page
  - includes an edit form for imported/front-card fields
  - includes loaded card `version` in edit forms

- `POST /admin/cards/{card_id}/imported-fields`
  - saves imported/front-card field corrections
  - requires loaded `version`
  - blocks stale edits with the same style of reload warning used elsewhere
  - redirects/renders back to the detail page with a visible success/error message

Update `_admin_nav.html` to add a `Cards` link once `/admin/cards` exists. Keep the top-right `Terminal` link on admin pages. Do not add links to routes that do not exist yet.

## Card Index Requirements

The `/admin/cards` index should be work-focused and compact.

Filters:

- order number
- customer
- product
- status
- order date
- delivery date

Pragmatic implementation details:

- Query parameters can be simple text fields/selects.
- Partial text matching is acceptable for order/customer/product.
- Date filters can be exact text matching against stored workbook values; do not build date parsing unless it is already easy and reliable.
- Include all card statuses, including imported, pending, running, paused, completed, and cancelled.
- Default sort should make recent/current work easy to find. A reasonable default is `updated_at DESC, id DESC`.
- Keep page size simple. A fixed limit such as 100 rows is acceptable for this prototype.

Index table should include:

- order number
- status
- validation status
- customer
- product
- order date
- delivery date
- machine/sequence
- updated timestamp
- link to review/detail

## Card Detail Requirements

The `/admin/cards/{card_id}` page should show enough information for shift-manager review before print work begins.

Show read-only summary sections for:

- status, validation status, version, updated timestamp
- machine and sequence
- imported/front-card fields
- terminal material fields
- tare weight
- roll entries and gross/net totals
- production timing summary and timing segments

Use existing display patterns from `terminal.html` where practical, but avoid duplicating large template blocks if a small admin-specific layout is clearer.

Editing scope in this bundle:

- Editable imported/front-card fields are the fields imported from CSV/workbook:
  - `order_number`
  - `order_date`
  - `delivery_date`
  - `customer`
  - `city`
  - `product_type`
  - `quantity_1`
  - `unit_1`
  - `quantity_2`
  - `unit_2`
  - `product_form`
  - `material`
  - `size_thickness`
  - `notes`
  - `extrusion_flag`
  - `extrusion_folding`
  - `extrusion_next_operation`
  - `extrusion_treatment`
  - `raw_material_a`
  - `raw_material_b`
  - `raw_material_c`
  - `linear_pe`
  - `antistatic`
  - `masterbatch`
  - `chalk`
  - `packaging_method`

Important order-number handling:

- If editing `order_number` is included, it must be safe:
  - non-empty
  - unique across cards
  - update `roll_entries.order_number` for the same `card_id` in the same transaction so existing production data remains linked consistently
  - preserve timing segments, tare, status, machine/sequence, terminal material fields, and roll rows
- If safe order-number editing would make this bundle too large, keep `order_number` read-only in the edit form, show it prominently, and document that order-number correction is deferred. Prefer implementing safe order-number editing if it stays simple.

Validation:

- Editing imported fields should re-evaluate extrusion readiness using the existing importer validation rules where appropriate.
- Because no-extrusion rows are no longer imported, an existing card should normally stay `ready`; however, if an admin edit removes the extrusion flag or all extrusion details, block the save with a clear message instead of turning an existing card into an unusable no-extrusion card.
- Do not allow an edit that would make a released/in-production card no longer usable for extrusion.
- Do not silently overwrite a card when `version` is stale.

## Backend Rules To Preserve

- Duplicate import without overwrite must not change existing cards.
- Duplicate import with overwrite must update only imported/front-card fields.
- Admin imported-field edits must preserve:
  - status
  - machine assignment
  - machine sequence
  - tare weight
  - roll entries
  - production time segments
  - terminal material fields
  - workflow timestamps except the normal `updated_at`/`version` update for the edited card
- Release must still require `ready`, machine, and sequence.
- Release must still block duplicate active sequence within the same machine queue.
- A machine cannot have more than one running card.
- Tests must use temporary SQLite database paths and must not mutate `data/extrusion_terminal.sqlite3`.

## Suggested Implementation Steps

1. Check current status:

```powershell
git status --short
```

2. Read the required files listed above.

3. Add DB helpers in `app/db.py`, likely including:

- `fetch_admin_cards(...)` for index filtering
- `fetch_admin_card_detail(card_id)` for full detail
- `update_admin_imported_fields(card_id, loaded_version, fields)` for version-checked edits

4. Reuse/import field definitions from `app/importer.py` where practical so editable fields stay aligned with CSV import fields.

5. Add routes in `app/main.py`:

- `GET /admin/cards`
- `GET /admin/cards/{card_id}`
- `POST /admin/cards/{card_id}/imported-fields`

6. Add templates:

- `admin_cards.html`
- `admin_card_detail.html`

7. Update `_admin_nav.html` to include `Cards`.

8. Add or update CSS only as needed for compact admin forms/tables. Keep the same visual language.

9. Add tests:

- admin card index backend filter by order number
- admin card index backend filter by customer or product
- admin detail fetch includes imported fields, status, machine/sequence, timing, rolls, totals, and terminal material fields
- admin imported-field edit succeeds and increments version
- stale admin imported-field edit is blocked
- editing imported fields preserves rolls, timing, tare, status, machine/sequence, and terminal material fields
- duplicate order number edit is blocked if order-number editing is implemented
- no-extrusion-causing edit is blocked
- route registration or route-level smoke tests for `/admin/cards` and `/admin/cards/{card_id}` if the current test stack supports it without adding dependencies

Note: previous route tests avoided FastAPI `TestClient` because the installed Starlette test client required an extra `httpx2` dependency. Do not add new dependencies just for route smoke tests unless necessary.

10. Run checks:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

If the local venv is missing or broken, inspect the repo setup and ask the user before dependency installation.

11. Manual app check, if feasible:

- Start the app with a temporary database path if practical.
- Open `/admin/import`, import at least one ready card.
- Open `/admin/cards`, find the card by order/customer/product filters.
- Open `/admin/cards/{card_id}`.
- Edit imported/front-card fields and confirm the success message appears.
- Confirm the edited values appear on the admin detail page.
- If the card is released, confirm production data and terminal visibility are not damaged.
- Confirm stale edit behavior if practical by loading the same detail page twice and saving from the older version.

Do not mutate the real runtime database for manual checks unless the user explicitly asks.

## Documentation Updates

Update `IMPLEMENTATION_PLAN.md` to mark Bundle 2 done only after implementation, tests, review, and manual check are complete.

Update `README.md` or `AGENTS.md` only if the implementation changes documented behavior or if a deliberate simplification is accepted during this bundle.

Do not mark Milestone 9 complete.

## Commit Guidance

This session should finish Bundle 2 end-to-end if feasible:

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

Use a bundle-level commit message such as:

```text
Add admin card review
```

If `.git` writes require escalation, request approval for the exact Git action. Do not use destructive Git commands.

Do not include reassignment/resequencing, timing correction, production-side correction, or print output in this bundle.
