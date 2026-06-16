# Milestone 9 Prompt - Terminal Sync Awareness

You are continuing work on the extrusion terminal pilot repository at:

`C:\Users\slavi\Dropbox (Personal)\03 KolevOOD\7 Extrusion Terminal Prototype`

The user has approved a small follow-up slice after Milestone 9 Bundle 3: **Terminal Sync Awareness**.

This prompt is intended for a fresh Codex session with no prior conversation context. Read it fully, then read the required project files before editing.

## Goal

Add the simplest possible synchronization awareness between the shift-manager/admin computer and the workstation terminal page.

The problem:

- `/terminal` is currently server-rendered and only sees fresh data after load, navigation, form submit, or manual refresh.
- Admin planning can release, reassign, or resequence cards while the workstation page is open.
- Operators may be typing roll/tare/material data, so a blind full-page auto-refresh is unsafe.

The desired behavior:

- Terminal periodically checks whether the active queue or selected card changed.
- If changed and the operator is not editing anything, refresh the page automatically.
- If changed while an input is focused or a form has unsaved edits, do **not** refresh. Show a visible banner: updates are available, refresh when ready.
- Keep existing server-side `loaded_version` conflict checks as the real data-integrity protection.

This is not a full real-time system. Do not add WebSockets, background services, complex client state, or partial DOM patching.

## Communication Constraint

Keep user-facing updates short. The user prefers concise answers and no long essays.

Use 30-second or lower timeouts for normal checks. Prefer direct code/template review and automated tests. Do not spend time on repeated browser/server launch attempts if they are flaky.

## Required First Reads

Read these files in this order:

1. `AGENTS.md`
2. `README.md`
3. `IMPLEMENTATION_PLAN.md`
4. `prompts/milestone-9-bundle-3-planning-reassignment-resequencing.md` if present
5. this prompt

Then inspect these implementation files:

- `app/main.py`
- `app/db.py`
- `app/constants.py`
- `app/templates/terminal.html`
- `app/templates/admin_planning.html`
- `app/static/css/app.css`
- `tests/conftest.py`
- `tests/test_terminal_detail.py`
- `tests/test_admin_planning.py` if present
- `tests/test_production_timing.py`
- `tests/test_roll_entry.py`
- `tests/test_finish_cancel_history.py`

Also inspect route registration tests:

- `tests/test_admin_routes.py`

Do not rely on old conversation context. Current committed baseline after Bundle 3 is expected to include:

```text
5da9a89 Normalize admin planning sequences
f44cadf Add admin planning reassignment
06a59c8 Complete admin card review cleanup
```

Run:

```powershell
git status --short
git log --oneline -6
```

If there are uncommitted changes, inspect and preserve them unless the user explicitly asks otherwise. At the time this prompt was created, `prompts/milestone-9-bundle-3-planning-reassignment-resequencing.md` may exist as an untracked prompt file; do not delete or overwrite it.

## Current Context

Milestones 0 through 8 are complete. Milestone 9 is in progress.

Bundle 1 is complete:

- `/admin/import` handles CSV import.
- `/admin/planning` exists.
- no-extrusion import rows are skipped.
- import outcomes use Action/Message.

Bundle 2 is complete:

- `/admin/cards` exists.
- `/admin/cards/{card_id}` exists.
- admin imported/front-card edits use loaded `version`.
- `validation_status` UI/product concept was removed.

Bundle 3 is complete:

- `/admin/planning` supports release, reassignment, and resequencing.
- planning treats entered sequence as target queue position and normalizes affected machine queues to contiguous positions starting at `1`.
- duplicate active machine sequence protection remains.
- occupied machine protection remains for running/paused cards.
- planning mutations use loaded `version` conflict checks.

Existing terminal behavior:

- `/terminal` renders active cards, machine focus tiles, selected card detail, timing controls, roll/tare forms, material fields, and archive cards.
- Most terminal forms include `<input type="hidden" name="loaded_version" value="{{ selected_card.version }}">`.
- Backend terminal write actions block stale versions with `STALE_CARD_MESSAGE`.
- There is no polling, snapshot endpoint, or auto-refresh yet.

## Scope

Implement only the terminal sync awareness slice.

Required behavior:

1. Add a read-only terminal snapshot endpoint.
2. Add lightweight polling on `/terminal`.
3. Detect changes to active queue and selected card version.
4. Auto-refresh only when safe.
5. Show a visible update banner when auto-refresh is not safe.
6. Add focused tests.
7. Update docs/plan with a short note.

## Non-Scope

Do not implement:

- WebSockets
- server-sent events
- background tasks/services
- partial DOM patching of the queue/card
- multi-user auth
- browser notification APIs
- offline support
- local storage synchronization
- any production data correction behavior
- admin cancel/restore
- print output
- Bundle 4 behavior

## Recommended Backend Shape

Add a small DB helper in `app/db.py`, for example:

```python
def terminal_snapshot(selected_card_id: int | None = None) -> dict[str, Any]:
    ...
```

The snapshot should be read-only and cheap.

Recommended JSON shape:

```json
{
  "active_signature": "stable string or number",
  "selected_card": {
    "id": 123,
    "version": 7,
    "status": "running",
    "updated_at": "..."
  },
  "active_cards": [
    {
      "id": 123,
      "order_number": "25277",
      "status": "running",
      "machine_id": 1,
      "machine_sequence": 1,
      "version": 7,
      "updated_at": "..."
    }
  ]
}
```

The exact shape can differ, but it must let the terminal determine:

- active queue membership changed
- order/status/machine/sequence/version changed for any active card
- selected card version/status changed
- selected card disappeared from terminal-visible statuses

Use existing constants:

- `ACTIVE_TERMINAL_STATUSES`
- `ARCHIVE_STATUSES`

For selected card behavior:

- If no selected card id is provided, return `selected_card: null`.
- If a selected card id is provided but is no longer terminal-visible, return a clear null/missing marker so the client can refresh or show the banner.

Add a route in `app/main.py`:

```python
@app.get("/terminal/snapshot")
async def terminal_snapshot_route(selected_card_id: int | None = None):
    ...
```

Keep it read-only. Do not mutate versions or timestamps.

## Recommended Frontend Shape

Add a small script to `app/templates/terminal.html`, preferably at the bottom of the page.

Keep it simple:

- Poll every 10 seconds.
- Call `/terminal/snapshot`.
- Include selected card id if one is open.
- Compare the initial/current snapshot signature to the latest snapshot.
- If different:
  - if no text/number/textarea/select input is focused and no form is dirty: `window.location.reload()`
  - otherwise show a banner and do not reload

Dirty/focused rules:

- Mark the terminal as dirty on `input` or `change` events in editable form controls.
- Clear/ignore dirty state on form submit because the page is already posting.
- Treat focused editable controls as unsafe to refresh, even if no dirty flag has been set yet.

Banner:

- Add a visible banner near the top of the terminal work surface.
- Text should be short and practical, for example:
  - `Updates available. Finish the current entry, then refresh.`
- Include a `Refresh` button/link that calls `window.location.reload()`.
- Hide the banner by default.

Do not use in-app explanatory text about implementation details, polling, or synchronization mechanics.

If JavaScript fails, the app should still work with manual refresh and existing server-side version checks.

## CSS

Add only minimal styling in `app/static/css/app.css`.

Use existing notice styles where practical.

Possible class names:

- `.sync-banner`
- `.sync-banner.visible`

Keep styling calm but visible. This is not an error state unless data entry is stale and blocked by the server.

## Tests

Add focused automated tests. A new file such as `tests/test_terminal_sync.py` is appropriate.

Do not add new dependencies. Avoid FastAPI `TestClient` if the current project avoids it.

Recommended tests:

1. Snapshot includes active released cards with status, machine, sequence, version.
2. Snapshot signature changes when admin planning changes machine/sequence or sequence normalization changes order.
3. Snapshot selected card version changes after a terminal write action such as tare update or roll add.
4. Snapshot selected card returns a missing/null marker when the selected card is no longer terminal-visible, if applicable.
5. Route registration includes `/terminal/snapshot`.

If testing the async route directly is simple, use `asyncio.run(...)` as existing route tests do. Otherwise test the DB helper directly and route registration separately.

Do not test by mutating the real runtime database. Use temporary SQLite database fixtures only.

## Documentation Updates

Update `IMPLEMENTATION_PLAN.md` with a short note after Bundle 3 or before Bundle 4:

- terminal sync awareness added
- terminal polls for queue/selected-card changes
- auto-refresh happens only when no operator input is active/dirty
- existing loaded-version checks remain the authoritative protection

Update `README.md` only if needed, likely in the conflict handling or operational behavior section:

- terminal shows admin changes after refresh/reload, and now can prompt/refresh when updates are detected
- server-side version checks still block stale writes

Do not mark Milestone 9 complete.

## Verification Commands

Run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

Manual UI check is useful but keep it focused and do not mutate the real runtime database:

- start the app against a temporary database if practical
- open `/terminal`
- release/resequence a card from `/admin/planning`
- verify terminal refreshes when idle
- focus/type in a roll or tare input
- make another admin planning change
- verify terminal shows the update banner instead of refreshing and losing typed input

If browser/server launch is flaky, stop after one attempt and report that manual UI check was not completed.

## Commit Guidance

This is a small slice and should be committed separately from Bundle 3 and Bundle 4.

Before committing, run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

Use a focused commit message such as:

```text
Add terminal sync awareness
```

If `.git` writes require escalation, request approval for the exact Git action. Do not use destructive Git commands.

## Final Response Expectations

Keep the final answer short:

- what sync behavior was added
- how it avoids interrupting operator input
- tests passed
- manual check status
- commit hash if committed
