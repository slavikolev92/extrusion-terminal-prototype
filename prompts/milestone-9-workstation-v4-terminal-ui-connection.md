# Milestone 9 Prompt - Connect Workstation V4 Terminal UI

You are continuing work on the extrusion terminal pilot repository at:

`C:\Users\slavi\Dropbox (Personal)\03 KolevOOD\7 Extrusion Terminal Prototype`

The user has completed the Milestone 9 Bundle 5 technical walkthrough and now wants the workstation terminal route to use the latest prototype UI:

`ui-prototypes/workstation-v4.html`

This prompt is intended for a fresh Codex session. Read it fully, then read the required project files before editing.

## Goal

Replace/adapt the current temporary `/terminal` UI with a live implementation based on `ui-prototypes/workstation-v4.html`.

The prototype is a static/demo HTML file with embedded CSS, JS, and demo data. The goal is **not** to keep demo data or client-only state. The goal is to preserve the V4 workstation layout and interaction model while wiring it to the existing FastAPI/Jinja/SQLite app behavior.

## Required First Reads

Read these files in this order:

1. `AGENTS.md`
2. `README.md`
3. `IMPLEMENTATION_PLAN.md`
4. `prompts/milestone-9-bundle-4-admin-production-corrections.md` if present
5. `prompts/milestone-9-workstation-v4-terminal-ui-connection.md`

Then inspect these implementation/prototype files:

- `ui-prototypes/workstation-v4.html`
- `app/templates/terminal.html`
- `app/static/css/app.css`
- `app/main.py`
- `app/db.py`
- `app/constants.py`
- `tests/test_terminal_detail.py`
- `tests/test_production_timing.py`
- `tests/test_roll_entry.py`
- `tests/test_finish_cancel_history.py`
- `tests/test_terminal_sync.py`
- `tests/test_admin_production_corrections.py`

Run:

```powershell
git status --short
git log --oneline -8
```

At prompt creation time, the latest relevant commits were:

```text
4bedd36 Preserve running timing invariants
060e471 Fix admin correction delete controls
339b7f9 Add admin production corrections
93479fc Add terminal sync awareness
```

There may be unrelated uncommitted infrastructure/hardware files and untracked prompt files. Preserve them unless the user explicitly says otherwise.

## Current App State

Milestone 9 Bundles 1-5 are complete:

- Admin import UX cleanup.
- Admin card index/detail and imported-field editing.
- Admin planning, release, reassignment, resequencing.
- Terminal sync awareness.
- Admin production corrections.
- Pre-print workflow technical walkthrough.

Existing `/terminal` behavior must remain functionally intact:

- Shows active queue and completed/cancelled archive.
- Selecting a card opens details.
- Machine focus prefers running/paused card, otherwise next pending card.
- Start/pause/resume timing actions.
- Tare and roll entry/correction/deletion.
- Terminal material field edits.
- Finish/cancel/restore.
- Loaded-version stale-write protection.
- Terminal snapshot polling/update banner behavior.

The current `/terminal` UI is implementation-simple. The user now wants the actual workstation to look and behave like `ui-prototypes/workstation-v4.html`.

## Scope

Implement only the live workstation UI connection.

Required:

1. Adapt the V4 prototype structure into `app/templates/terminal.html`.
2. Move or merge necessary V4 CSS into `app/static/css/app.css` without breaking admin pages.
3. Remove prototype demo data and client-only order state.
4. Render live active/archive cards from the existing terminal context.
5. Preserve all existing terminal form posts and loaded-version hidden fields.
6. Preserve terminal sync awareness:
   - `/terminal/snapshot`
   - polling
   - auto-refresh only when safe
   - update banner when input is focused/dirty
7. Preserve backend/database invariants. Do not weaken rules to satisfy UI convenience.
8. Keep the workstation operator screen compact, practical, and based on V4.
9. Add/update focused tests for the rendered terminal page and route registration where useful.
10. Run a focused manual/browser check with a temporary DB.

## Non-Scope

Do not implement:

- Print output.
- Printable card template.
- Admin redesign.
- Login/users/permissions.
- WebSockets/SSE/background services.
- New production rules unless the V4 UI reveals a direct mismatch that must be fixed.
- Writing data back to Excel.
- Non-extrusion workflows.

If a UI control from the prototype is not backed by implemented behavior, either wire it to existing behavior or disable/hide it. Do not fake it.

## Prototype Notes

`ui-prototypes/workstation-v4.html` includes:

- `.app` shell with sidebar and main work area.
- Active/completed tabs.
- Queue list.
- Top action bar with Start, Pause, Finish, overflow menu, Cancel, Print.
- Operational card panel.
- Recipe/material panel.
- Production metrics.
- Tare and roll entry panel.
- Embedded demo JS and demo order data.

When connecting it:

- Keep the visual structure and CSS intent.
- Replace demo JS order state with server-rendered Jinja data/forms.
- Keep only small JS needed for:
  - clock/menu/tabs if retained
  - terminal sync polling/update banner
  - basic UI convenience that does not become source of truth
- Server-side forms remain the source of truth for writes.

## Functional Requirements

For selected live card:

- Pending card:
  - Start enabled.
  - Pause disabled.
  - Finish available only as current backend allows; backend still validates.
  - Roll add disabled unless backend permits.
- Running card:
  - Pause enabled.
  - Finish enabled.
  - Roll add/edit enabled.
  - Must have/open timing segment by backend invariant.
- Paused card:
  - Resume/Start-style action available.
  - Pause disabled.
  - Roll add/edit disabled unless backend permits.
- Completed card:
  - Visible in completed/archive tab.
  - Production corrections still available where current terminal rules allow.
  - Print control can be visible but disabled or non-functional until Milestone 10.
- Cancelled card:
  - Visible in archive tab.
  - Restore available.

Every write form must include:

```html
<input type="hidden" name="loaded_version" value="{{ selected_card.version }}">
```

Do not remove backend stale checks.

## Testing

Add or update tests as appropriate. Good targets:

- `/terminal` renders V4 shell structure.
- Active and archive cards render in the expected sections.
- Selected card renders action forms with loaded-version hidden inputs.
- Pending/running/paused/completed/cancelled controls appear or disable appropriately.
- Terminal sync snapshot route remains registered and existing sync tests still pass.

Existing command:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
```

Tests must use temporary SQLite databases and must not mutate `data/extrusion_terminal.sqlite3`.

## Manual Check

Use a temporary DB. Run through at least:

1. Import/release two cards.
2. Open `/terminal`.
3. Confirm V4-style active queue and selected card render.
4. Start, pause, resume a card.
5. Enter tare and rolls.
6. Finish the card and confirm it appears in archive/completed view.
7. Correct a completed card roll or material field if the UI exposes those controls.
8. Verify update banner behavior still works, or document if only automated coverage was used.

Use the Browser plugin/in-app browser for local UI verification if available.

## Verification Commands

Run before commit:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

## Documentation

Update `IMPLEMENTATION_PLAN.md` when complete:

- mark the Workstation V4 terminal UI connection done
- keep Milestone 10 print output as the next step

Update `AGENTS.md` current milestone state if this UI connection is completed.

Update `README.md` only if the behavior changes, not just the visual layout.

## Commit Guidance

Commit this as a focused pre-print UI slice, for example:

```text
Connect workstation V4 terminal UI
```

Do not include unrelated infrastructure/hardware notes or old prompt files unless explicitly asked.

## Final Response Expectations

Keep the final response short:

- what V4 UI behavior was connected
- what existing backend safeguards remain
- tests passed
- manual/browser check status
- commit hash
