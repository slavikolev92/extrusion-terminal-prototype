# Milestone 7 Prompt - Finish, Cancel, And History

You are continuing work on the extrusion terminal pilot repository at:

`C:\Users\slavi\Dropbox\03 KolevOOD\7 Extrusion Terminal Prototype`

You have express permission to use subagents for tasks that are parallelizable and where they are genuinely useful, such as independent code review, test review, UI review, or documentation review. Do not use subagents to skip reading required project instructions yourself.

First, read these files in this order:

1. `AGENTS.md`
2. `README.md`
3. `IMPLEMENTATION_PLAN.md`
4. `IMPLEMENTATION_HANDOFF.md`

Then inspect the current code under:

- `app/`
- `app/templates/`
- `app/static/css/app.css`
- `tests/`

Also read the prior milestone prompt for continuity:

- `prompts/milestone-6-tare-and-roll-entry.md`

Current state:

- Milestones 0 through 6 are complete and committed.
- Latest completed commit should be `d0ad54e Add tare and roll entry milestone`.
- Milestone 6 added terminal tare and roll entry:
  - order-level tare input
  - fixed gross-weight input for next roll
  - automatic roll numbering
  - editable/clearable previous gross weights
  - gross/net totals
  - backend validation for running-only roll edits
  - loaded-version conflict checks
  - tests in `tests/test_roll_entry.py`
- User manually verified in the live app that adding two gross rolls, refreshing, editing one gross weight, and refreshing again persisted correctly.
- Current next milestone in `IMPLEMENTATION_PLAN.md` should be `Milestone 7 - Finish, Cancel, And History`.

Important environment note:

- Git works, but `.git` writes may require escalation/approval.
- Python on this PC may require the temporary working venv at `.test-runtime\codex-venv`.
- The current successful test command is:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
```

- If needed, verify with:

```powershell
git status --short
git log -1 --oneline
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
```

- If you need to start the app for manual browser testing, avoid hidden/background PowerShell process creation because antivirus objected to it. Prefer the plain visible terminal approach:

```powershell
cmd /c start "Extrusion Terminal App" .\.test-runtime\codex-venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then check:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/health -UseBasicParsing -TimeoutSec 5
```

Implement only Milestone 7 - Finish, Cancel, And History.

Milestone 7 scope:

- Add terminal finish behavior.
- Add terminal cancel behavior.
- Add cancelled-card restore behavior back to `pending`.
- Completed cards must leave the active terminal queue and appear in the completed/cancelled section.
- Cancelled cards must leave the active terminal queue and appear in the completed/cancelled section.
- Completed and cancelled cards remain available for review.
- Completed cards remain editable according to existing terminal edit rules where applicable.
- Cancelled cards can be restored to `pending`.
- Finish must close any active timing segment.
- Finish must persist immediately.
- Cancel/restore must persist immediately.
- Use backend/database validation, not UI-only validation.
- Preserve imported card data, timing data, tare weight, and roll data.

Finish validation rules from `README.md` and `AGENTS.md`:

- Finish must be blocked unless tare weight exists.
- Finish must be blocked unless the timer was started at least once.
- Finish must be blocked unless at least one gross roll exists.
- Finish must close any active timing segment.
- Printing is still out of scope for this milestone.
- Finish validation must be enforced in backend code.

Clarification for this milestone:

- Do not implement print output.
- Do not implement backup/recovery.
- Do not implement user accounts/login/permissions.
- Do not write anything back to Excel.
- Do not implement complex reopen logic for completed cards.
- Do not implement cancellation reasons.
- Do not implement detailed machine downtime tracking.
- Do not implement admin-side broad editing unless it is already present and a tiny scoped change is required for cancellation consistency.
- Keep cancel/restore simple. The confirmed behavior is reversible cancellation: cancelling a card changes status to `cancelled`; restoring a cancelled card changes status back to `pending`.

Recommended implementation approach:

1. Review current status constants in `app/constants.py`.
2. Review existing database functions in `app/db.py`:
   - timing functions
   - roll/tare functions
   - terminal detail fetch
   - queue fetch behavior
3. Add backend functions in `app/db.py` for:
   - finishing a card with loaded-version conflict check
   - cancelling a card with loaded-version conflict check
   - restoring a cancelled card to `pending` with loaded-version conflict check
4. Enforce finish rules:
   - card must exist and be terminal-visible
   - stale loaded versions must be blocked
   - card should be in an active terminal status before finish
   - tare weight must not be null
   - at least one production time segment must exist
   - at least one roll entry with non-null gross weight must exist
   - if status is `running`, close the open segment with `end_reason = 'finish'`
   - if status is `paused`, no open segment should exist, but finishing should still be allowed if requirements are met
   - set status to `completed`
   - set `finished_at`
   - increment `version`
5. Enforce cancel rules:
   - card must exist and be terminal-visible in an active terminal status
   - stale loaded versions must be blocked
   - if cancelling a running card, close any active timing segment with `end_reason = 'correction'` or a clearly chosen existing valid reason; prefer not to expand the schema enum unless necessary
   - set status to `cancelled`
   - set `cancelled_at`
   - increment `version`
6. Enforce restore rules:
   - card must exist with status `cancelled`
   - stale loaded versions must be blocked
   - restore status to `pending`
   - clear `cancelled_at`
   - ensure SQLite constraints still block duplicate active machine sequence on restore
   - ensure restore does not create a machine with more than one running card
   - increment `version`
7. Add routes in `app/main.py` for terminal forms:
   - finish
   - cancel
   - restore cancelled card
8. Update `app/templates/terminal.html`:
   - enable/display `Finished` action when a selected card is active
   - show cancel action for active terminal cards
   - show restore action for cancelled selected cards
   - keep completed/cancelled section usable
   - show validation/user-visible messages
9. Update `app/static/css/app.css` minimally if needed.
10. Add focused tests, probably `tests/test_finish_cancel_history.py`, for:
   - finish blocks without tare
   - finish blocks without timing started
   - finish blocks without at least one gross roll
   - finish succeeds from `running` and closes active segment with `finish`
   - finish succeeds from `paused` when requirements are met
   - completed card leaves active queue and appears in archive/completed list
   - cancel active pending card moves it to cancelled/archive
   - cancel running card closes open timing segment and moves it to cancelled/archive
   - restore cancelled card returns it to pending
   - restore blocks duplicate active machine sequence
   - stale finish/cancel/restore edits are blocked
11. Run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

12. Do a focused manual workflow check with a temporary database, not `data/extrusion_terminal.sqlite3`:
   - import/release a sample card
   - start timing
   - enter tare
   - add at least one gross roll
   - finish the card
   - verify it leaves active queue and appears in completed/cancelled section
   - create/release another card
   - cancel it
   - restore it back to pending
   - verify persistence after reload/render
13. If the user asks to test the live app, start it only with a plain visible terminal command as described above.
14. Update docs:
   - `IMPLEMENTATION_PLAN.md`: mark Milestone 7 done and Milestone 8 next
   - `AGENTS.md`: current milestone state
   - `IMPLEMENTATION_HANDOFF.md`: current state, test count, next milestone notes
15. Review changed code for:
   - data integrity
   - validation failures and user-visible messages
   - preservation of imported/roll/timing data
   - direct workflow behavior in `/terminal`
   - scoped changes only
16. Stage and commit with a milestone-level message such as:

```text
Add finish cancel and history milestone
```

Remember:

- Do not mutate the real runtime database during automated or manual checks unless the user explicitly asks for live-app testing.
- Do not leave uncommitted milestone work.
- Do not include the untracked `prompts/` folder in the milestone commit unless the user explicitly asks you to commit prompts too.
- If `.git` writes require escalation, request approval for `git add` and `git commit`.
- Keep Milestone 7 separate from backup/recovery and printing.
