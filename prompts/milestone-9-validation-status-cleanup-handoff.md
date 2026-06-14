# Milestone 9 Validation Status Cleanup Handoff

You are continuing work on the extrusion terminal pilot repository at:

`C:\Users\slavi\Dropbox (Personal)\03 KolevOOD\7 Extrusion Terminal Prototype`

The immediate task is to remove the confusing `validation_status` concept from the admin UI and then clean up the redundant persisted validation field/code path where safe.

## Communication Constraint

Keep user-facing updates short. The user explicitly wants concise answers and no long essays.

Use 30-second or lower timeouts for normal checks. Prefer direct template/code review and automated tests. Do not spend time on browser/server launch unless needed and stable.

## Required First Reads

Read these files before editing:

1. `AGENTS.md`
2. `README.md`
3. `IMPLEMENTATION_PLAN.md`
4. `prompts/milestone-9-bundle-2-admin-detail-redesign-handoff.md`
5. this handoff prompt

Then inspect:

- `app/main.py`
- `app/db.py`
- `app/constants.py`
- `app/rules.py`
- `app/importer.py`
- `app/templates/admin_import.html`
- `app/templates/admin_planning.html`
- `app/templates/admin_cards.html`
- `app/templates/admin_card_detail.html`
- `app/static/css/app.css`
- `tests/test_admin_card_review.py`
- `tests/test_admin_routes.py`
- `tests/test_baseline.py`

## Current Context

Milestone 9 Bundle 2 has an admin card index and admin card detail/review page. The detail page was recently redesigned to follow `ui-prototypes/workstation-v4.html` and Bulgarian operational-card structure.

There are intentional pre-existing working-tree changes. Do not revert them:

- `.gitignore` modified
- `IMPLEMENTATION_HANDOFF.md` deleted
- top-level `excel-macros/` deleted/moved
- `source-files/README.md` modified
- `source-files/excel-macros/` untracked
- `prompts/` untracked
- `INFRASTRUCTURE_IMPLEMENTATION_PLAN.md` untracked
- Bundle 2 changes in app/templates, app/db.py, app/main.py, app/constants.py, app/rules.py, app/static/css/app.css, tests, and `IMPLEMENTATION_PLAN.md`

Do not run destructive git commands. Preserve all user/housekeeping changes.

## User Decision

The user approved removing the `validation_status` concept because it is confusing and mostly redundant.

Reasoning already agreed:

- Real validation is server-side logic that checks import/edit/release invariants.
- The persisted/displayed `validation_status = ready` is mostly a cached label.
- No-extrusion rows are now skipped during import and are not saved as cards.
- Duplicate import outcomes are already represented by `action = skipped` and a message.
- Admin edits that would make a card no-extrusion are blocked directly.
- Saved cards are therefore almost always `ready`, so showing `validation_status` creates UI noise.

## Required Scope

Implement all of this cleanup:

1. Remove `Validation` from Planning and Cards UI entirely.
2. Remove `Validation` from the Import result table too.
   - Keep `Action` and `Message`; those are the useful operator-facing fields.
3. Keep server-side validation behavior.
   - Import must still skip no-extrusion rows.
   - Admin imported-field edits must still block changes that would make a card unusable for extrusion.
   - Release must still only allow cards that are currently valid for extrusion.
4. Remove or stop relying on persisted `validation_status` in code/database if it has no useful purpose.
   - Prefer validating current card fields directly where needed.
   - If dropping the SQLite column is too invasive for this session, stop writing/reading it from UI/business logic and leave a clearly documented compatibility note.
   - But do not leave dead constants, CSS, labels, or tests around if they no longer serve a purpose.

## Important Implementation Guidance

### UI cleanup

Remove validation columns/cells from:

- `app/templates/admin_import.html`
- `app/templates/admin_planning.html`
- `app/templates/admin_cards.html`
- `app/templates/admin_card_detail.html` system metadata section

Remove validation-specific CSS if unused:

- `.pill.validation-ready`
- `.pill.validation-duplicate`
- `.pill.validation-no-extrusion-step`

Do not remove status coloring for actual card workflow statuses.

### Backend cleanup

Current likely code paths:

- `app/constants.py` defines `VALIDATION_READY`, `VALIDATION_DUPLICATE`, `VALIDATION_NO_EXTRUSION_STEP`, and `VALIDATION_STATUSES`.
- `app/importer.py` has `validate_card(card)` and stores `card["validation_status"]`.
- `app/db.py` schema has `cards.validation_status`.
- `release_card()` currently checks `card["validation_status"] == VALIDATION_READY`.
- `update_admin_imported_fields()` validates edited fields and writes `validation_status`.
- tests assert validation status in several places.

Keep `validate_card()` or replace it with a clearer helper, but make it return a direct boolean/result for server-side rules rather than a persisted UI field if practical.

Recommended shape:

- In `app/importer.py`, rename or supplement `validate_card()` with something like `card_has_extrusion_step(card) -> bool` or `validate_importable_extrusion_card(card) -> RuleResult/string`.
- Import no-extrusion rows should be skipped with an import result `action="skipped"` and clear message.
- `ImportRowResult` does not need `validation_status`.
- `insert_imported_card()` should no longer need `validation_status`.
- `update_imported_card_fields()` should no longer write `validation_status`.
- `update_admin_imported_fields()` should directly block if edited fields fail the extrusion check.
- `release_card()` should fetch current relevant card fields and validate them directly, not rely on a stored cached status.

### Database/schema decision

Preferred if SQLite version/environment supports it cleanly:

- Remove `validation_status` from `SCHEMA_SQL`.
- Add a lightweight migration in `init_db()` if needed to rebuild existing DBs without that column, or leave existing DB columns harmlessly ignored.

Pragmatic acceptable option:

- Stop selecting/writing/using `validation_status` everywhere.
- Leave the physical DB column in `SCHEMA_SQL` temporarily for compatibility if dropping it is too much risk.
- Remove UI/tests/constants around it so it no longer exists as a product concept.
- If leaving the column, add a short code comment explaining it is legacy/ignored until a schema cleanup migration.

Do not do a large schema redesign.

### Tests to update

Update tests to assert behavior, not the old validation label:

- import skips no-extrusion rows without creating cards
- duplicate imports are skipped with action/message
- overwrite preserves production data
- release blocks cards whose current imported fields no longer represent usable extrusion work
- admin edits that remove extrusion usability are blocked
- route registration remains unchanged
- card index/planning/import templates no longer include validation columns if existing tests inspect rendered templates; otherwise direct route smoke tests are enough

Remove or update assertions such as:

- `card["validation_status"] == "ready"`
- import row result has `validation_status`
- UI contains `Validation`

## Non-Scope

Do not implement:

- Bundle 3 reassignment/resequencing
- admin-side roll/tare/timing correction
- print output
- login/users/permissions
- unrelated refactors

## Verification Commands

Run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

If tests fail because old tests expected `validation_status`, update those tests to assert the real behavior instead.

Manual UI check is optional for this cleanup unless easy. Do not mutate the real runtime database for manual checks.

## Documentation

Update `IMPLEMENTATION_PLAN.md` with a short note that Bundle 2 cleanup removed redundant validation-status UI/product concept and kept server-side extrusion checks.

Update `README.md` or `AGENTS.md` only if they still describe `validation_status` as a user-facing/admin concept. If they mention validation statuses for older import behavior, revise carefully to say unusable/no-extrusion rows are reported and skipped, while duplicate/overwrite outcomes are shown as import actions/messages.

## Final Response

Keep final answer short:

- what was removed
- what validation behavior remains
- tests passed
- any deliberate compatibility note if the physical DB column remains
