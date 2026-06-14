# Milestone 6 Prompt - Tare And Roll Entry

You are continuing work on the extrusion terminal pilot repository at:

`C:\Users\slavi\Dropbox\03 KolevOOD\7 Extrusion Terminal Prototype`

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

Current state:

- Milestones 0 through 5 are complete and committed.
- Latest completed commit should be `910627c Add production timing milestone`.
- Milestone 5 added terminal production timing:
  - Start / Pause / Resume actions
  - `production_time_segments` storage
  - total production time calculation
  - version conflict checks
  - one running/paused occupied card per machine
  - tests in `tests/test_production_timing.py`
- Current next milestone in `IMPLEMENTATION_PLAN.md` should be `Milestone 6 - Tare And Roll Entry`.

Important environment note:

- Git works.
- Python on this PC may require care. There is a temporary working venv at `.test-runtime\codex-venv`.
- The last successful test command was:

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

Implement only Milestone 6 - Tare And Roll Entry.

Milestone 6 scope:

- Add order-level tare weight input.
- Add one fixed gross-weight input for the next roll.
- Pressing Enter or clicking Add saves the new gross roll immediately.
- Roll numbers are assigned automatically per card starting at `1`.
- Previous gross weights remain editable.
- Clearing a gross-weight value is enough to remove/correct it for this pilot, unless a very simple delete behavior is already easier and still scoped.
- Show total gross weight and total net weight.
- Net per roll is gross minus order-level tare.
- Total net is total gross minus `number_of_rolls * tare`.
- Weight inputs support up to two decimal places.
- Roll entry must be blocked when the card is not running.
- Changes must persist immediately.
- Use backend/database validation, not UI-only validation.
- Preserve existing imported card data and timing data.

Do not implement in Milestone 6:

- Finish validation
- Cancel/reopen behavior
- Completed/cancelled history changes beyond what already exists
- Backup/recovery
- Print output
- User accounts/login/permissions
- Writing anything back to Excel

Recommended implementation approach:

1. Review `app/db.py` current schema:
   - `cards` already has `tare_weight`
   - `roll_entries` already exists with `card_id`, `order_number`, `roll_number`, `gross_weight`, `net_weight`
2. Add backend functions in `app/db.py` for:
   - updating tare weight with loaded version conflict check
   - adding next roll gross weight
   - updating/clearing an existing roll gross weight
   - fetching roll entries and gross/net totals for terminal card detail
3. Enforce rules:
   - tare must be numeric, `>= 0`, max two decimal places
   - gross weight must be numeric, `>= 0`, max two decimal places
   - adding a roll is allowed only when card status is `running`
   - `roll_number` is next max + 1 for that card
   - `net_weight = gross_weight - tare_weight` when tare exists
   - if tare is missing, gross can still be saved if `README.md` allows; totals should show gross and either blank/pending net. Check `README.md` wording before deciding. Finish later requires tare, but roll entry specifically warns if timer inactive.
   - stale loaded versions must be blocked
4. Add routes in `app/main.py` for terminal forms:
   - save tare
   - add roll
   - update/clear existing roll
5. Update `app/templates/terminal.html`:
   - add tare input near timing/material work area
   - add fixed gross roll input
   - show roll table/list with roll number and editable gross
   - show total gross and total net
   - keep UI simple and operator-friendly
6. Update `app/static/css/app.css` minimally to support the roll/tare controls.
7. Add focused tests, probably `tests/test_roll_entry.py`, for:
   - tare update persists and uses version check
   - adding roll while running succeeds and assigns roll `1`
   - adding second roll assigns roll `2`
   - adding roll while pending/paused is blocked
   - gross/net totals calculate correctly with tare
   - stale roll/tare edits are blocked
   - clearing an existing gross removes/corrects it according to chosen pilot behavior
8. Run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

9. Do a focused manual workflow check with a temporary database, not `data/extrusion_terminal.sqlite3`:
   - import/release a sample card
   - start timing
   - enter tare
   - add two gross rolls
   - edit or clear one roll
   - verify totals render and persist after reload
10. Update docs:
   - `IMPLEMENTATION_PLAN.md`: mark Milestone 6 done and Milestone 7 next
   - `AGENTS.md` current milestone state
   - `IMPLEMENTATION_HANDOFF.md` current state, test count, next milestone notes
11. Review changed code for:
   - data integrity
   - conflict protection
   - preservation of timing/imported data
   - scoped changes only
12. Stage and commit with a milestone-level message such as:

```text
Add tare and roll entry milestone
```

Remember:

- Do not mutate the real runtime database.
- Do not leave uncommitted milestone work.
- If browser/manual server startup triggers antivirus due hidden PowerShell process creation, avoid suspicious `ProcessStartInfo` commands. Prefer a straightforward visible/foreground dev server or HTTP-level checks.
