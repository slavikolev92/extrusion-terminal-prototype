# Milestone 9 Bundle 3 Prompt - Planning, Reassignment, And Resequencing

You are continuing work on the extrusion terminal pilot repository at:

`C:\Users\slavi\Dropbox (Personal)\03 KolevOOD\7 Extrusion Terminal Prototype`

The user has approved moving to Milestone 9 Bundle 3: planning, release, reassignment, and resequencing.

This prompt is intended for a fresh Codex session with no prior conversation context. Read it fully, then read the required project files before editing.

## Communication Constraint

Keep user-facing updates short. The user prefers concise answers and no long essays.

Use 30-second or lower timeouts for normal checks. Prefer direct code/template review and automated tests. Do not spend time on repeated browser/server launch attempts if they are flaky.

## Required First Reads

Read these files in this order:

1. `AGENTS.md`
2. `README.md`
3. `IMPLEMENTATION_PLAN.md`
4. `prompts/milestone-9-bundle-1-admin-import-ux.md`
5. `prompts/milestone-9-bundle-2-admin-card-review.md`
6. `prompts/milestone-9-bundle-2-admin-detail-redesign-handoff.md`
7. `prompts/milestone-9-validation-status-cleanup-handoff.md`
8. this prompt

Then inspect these implementation files:

- `app/main.py`
- `app/db.py`
- `app/constants.py`
- `app/rules.py`
- `app/importer.py`
- `app/templates/admin_planning.html`
- `app/templates/admin_cards.html`
- `app/templates/admin_card_detail.html`
- `app/templates/terminal.html`
- `app/templates/_admin_nav.html`
- `app/static/css/app.css`
- `tests/conftest.py`
- `tests/test_baseline.py`
- `tests/test_admin_routes.py`
- `tests/test_admin_card_review.py`
- `tests/test_terminal_detail.py`
- `tests/test_production_timing.py`
- `tests/test_finish_cancel_history.py`

Do not rely on old conversation context. The committed baseline before Bundle 3 is:

```text
06a59c8 Complete admin card review cleanup
```

## Current Context

Milestones 0 through 8 are complete. Milestone 9 is in progress.

Bundle 1 is complete:

- admin section split into `/admin/import`, `/admin/planning`, and shared admin nav.
- import result table shows row-level `Action` and `Message`.
- duplicate overwrite remains explicit.
- no-extrusion CSV rows are reported as skipped and are not saved.

Bundle 2 is complete:

- `/admin/cards` exists as a searchable card index.
- `/admin/cards/{card_id}` exists as a full admin review/detail page.
- admin detail page follows the Bulgarian operational-card structure.
- imported/front-card fields are editable with loaded `version` conflict checks.
- edits preserve production-side data.
- unreleased imported cards can be deleted only when safe.
- the redundant validation-status UI/product concept was removed.
- new databases no longer create `cards.validation_status`; existing DBs may still have that legacy column and current code ignores it.
- status colors were simplified:
  - `imported`, `pending`, `running`: light blue
  - `paused`: orange
  - `completed`: green
  - `cancelled`: red

Working tree should be clean at the start of this bundle. Run:

```powershell
git status --short
```

If it is not clean, inspect the changes and preserve them unless the user explicitly asks otherwise.

## Bundle 3 Scope

Implement only Milestone 9 Bundle 3: planning, release, reassignment, and resequencing.

Goals:

1. Improve `/admin/planning` into a useful planning surface with:
   - unreleased card pool
   - four machine queues
   - release controls
   - reassignment/resequencing controls for active queued cards
2. Release imported cards by assigning machine and sequence.
3. Allow shift manager to change machine and sequence after release for active cards.
4. Preserve backend protection against duplicate active machine sequence.
5. Preserve backend protection against assigning a running/paused card into an occupied machine conflict.
6. Show validation/action errors clearly near the affected planning action.
7. Add loaded `version` conflict checks to planning mutations where practical.
8. Add automated tests for release, reassignment, resequencing, duplicate sequence blocking, occupied machine blocking, and stale edit blocking.

## Non-Scope

Do not implement in this bundle:

- admin-side roll/tare correction
- admin-side timing correction
- admin-side terminal material correction
- admin-side cancel/restore controls
- print output
- login/users/permissions
- drag-and-drop ordering
- bulk release
- automatic sequence renumbering unless it is required to make the simple workflow usable and is explicitly justified
- unrelated refactors or schema redesign

Bundle 4 handles workflow controls and production-data correction. Milestone 10 handles print output.

## Important Existing Behavior To Preserve

- Import persists cards before release.
- No-extrusion rows are skipped during import.
- Admin imported-field edits must block changes that would make a card unusable for extrusion.
- Release must validate current extrusion fields directly, not rely on a stored `validation_status`.
- Release must require valid machine and sequence.
- Duplicate active sequence numbers within the same machine queue must be blocked.
- `pending`, `running`, and `paused` are active terminal statuses.
- `completed` and `cancelled` are archive statuses.
- A machine cannot have more than one running card.
- Running and paused cards occupy a machine for planning purposes until completed, cancelled, or reassigned.
- Terminal machine tile focus prefers running/paused card over next pending card.
- Tests must use temporary SQLite database paths and must not mutate `data/extrusion_terminal.sqlite3`.

## Current Implementation Notes

Likely starting points:

- `app/main.py`
  - `admin_planning_context()`
  - `release_card_to_terminal()`
  - `parse_release_form()`
- `app/db.py`
  - `release_card()`
  - `fetch_machine_queues()`
  - `fetch_cards_by_status()`
  - `fetch_occupied_machine_card()`
  - `restore_cancelled_card()` has duplicate sequence logic that may be reusable as a reference
- `app/templates/admin_planning.html`
  - currently shows unreleased cards and four machine queues
  - active queue cards are display-only; Bundle 3 should add simple reassignment/resequencing forms
- `app/static/css/app.css`
  - already has status variables and queue-card styling

Existing route:

- `POST /admin/cards/{card_id}/release`

Potential new route:

- `POST /admin/cards/{card_id}/planning`
  - updates machine/sequence for active cards
  - uses loaded `version`
  - returns the planning page with a visible result message

Alternative route names are fine if they are simple and consistent. Avoid adding routes that imply Bundle 4 behavior.

## Backend Behavior Requirements

Release:

- Keep release limited to `imported` cards.
- Validate machine id and sequence.
- Validate current card fields have usable extrusion data.
- Block duplicate active sequence on the same machine.
- Prefer adding loaded `version` to the release form and backend release function if it stays simple; at minimum, add stale checks to the new reassignment/resequencing mutation.

Reassignment/resequencing:

- Allow only active terminal cards: `pending`, `running`, `paused`.
- Require loaded `version`.
- Require valid machine id and sequence.
- Block duplicate active sequence on the same machine, excluding the same card.
- Block assigning a `running` or `paused` card to a machine already occupied by another `running` or `paused` card.
- If moving a `pending` card into a machine with a running/paused card, that is acceptable as long as the sequence is unique; it waits in queue.
- If changing sequence within the same machine, preserve active queue ordering by numeric sequence.
- Increment `version` and update `updated_at` on successful planning changes.
- Do not touch imported fields, tare, rolls, timing segments, terminal material fields, or workflow timestamps.

Be careful with SQLite unique index behavior:

- There is a unique index on active `(machine_id, machine_sequence)`.
- Still keep explicit checks so the user sees a clear message instead of a raw integrity failure.
- Keep the integrity-error fallback.

## UI Requirements

Keep `/admin/planning` compact and work-focused.

Unreleased pool:

- Show imported cards.
- Provide machine/sequence release controls.
- Include loaded `version` if release gets a stale check.
- Link the order to `/admin/cards/{card_id}` if useful.

Machine queues:

- Keep four machine columns.
- Show active cards sorted by machine sequence.
- For each active card, show:
  - sequence
  - order number
  - customer/product summary
  - status pill
  - simple controls to change machine and sequence
  - link to card detail
- Show action result messages clearly. It is acceptable to show one global notice at the top if the message identifies the affected order; a per-card inline message is better if simple.

Do not use drag-and-drop. Use explicit select/input/button controls.

## Suggested Implementation Steps

1. Check status:

```powershell
git status --short
```

2. Read the required files listed above.

3. Add focused DB helpers in `app/db.py`, likely:

- `update_card_planning(card_id, loaded_version, machine_id, machine_sequence) -> RuleResult`
- optional small helpers for duplicate sequence and occupied machine checks if they reduce duplication with `release_card()`

4. Consider updating `release_card()` to accept `loaded_version` and enforce stale checks, then update current tests and route forms accordingly.

5. Add or update routes in `app/main.py`:

- keep `POST /admin/cards/{card_id}/release`
- add reassignment/resequencing route
- keep parsing behavior in simple helper functions

6. Update `app/templates/admin_planning.html`:

- improve release form if needed
- add queue edit forms
- include loaded versions
- add card detail links
- keep layout compact

7. Add CSS only where needed for planning controls. Reuse existing `.machine-grid`, `.machine-column`, `.queue-card`, `.release-form`, `.pill`, and status variables where possible.

8. Add tests, likely in a new `tests/test_admin_planning.py` or existing admin tests:

- release still succeeds and sets `pending`, machine, sequence
- release blocks stale version if release gets version checking
- reassignment moves a pending card between machines
- resequencing changes queue order
- duplicate active sequence is blocked
- moving a running/paused card to a machine with another running/paused card is blocked
- moving a pending card to a machine with a running/paused card is allowed if sequence is unique
- stale planning edit is blocked
- reassignment/resequencing preserves production data
- route registration includes the new planning route

Use temporary SQLite DB fixtures only.

9. Run checks:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

10. Manual app check if feasible:

- Use a temporary database path if practical.
- Import multiple usable cards.
- Release cards to different machines/sequences.
- Resequence cards within one machine.
- Move a pending card between machines.
- Start/pause one card, then verify moving another running/paused card into that occupied machine is blocked.
- Verify terminal queue order follows admin planning.

Do not mutate the real runtime database for manual checks unless the user explicitly asks.

## Documentation Updates

Update `IMPLEMENTATION_PLAN.md` when Bundle 3 is complete:

- mark Bundle 3 as complete or note any remaining manual check
- keep Bundle 4 as the next intended step

Update `README.md` or `AGENTS.md` only if behavior changes from the documented rules.

Do not mark Milestone 9 complete.

## Commit Guidance

This session should finish Bundle 3 end-to-end if feasible:

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
Add admin planning reassignment
```

If `.git` writes require escalation, request approval for the exact Git action. Do not use destructive Git commands.

## Final Response Expectations

Keep the final answer short:

- what Bundle 3 behavior was added
- what validation protections remain
- tests passed
- manual check status
- commit hash if committed
