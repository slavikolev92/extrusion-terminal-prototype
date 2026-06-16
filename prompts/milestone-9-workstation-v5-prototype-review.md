# Milestone 9 Prompt - Workstation V5 Prototype Review Before Terminal Connection

You are continuing work on the extrusion terminal pilot repository at:

`C:\Users\slavi\Dropbox (Personal)\03 KolevOOD\7 Extrusion Terminal Prototype`

This prompt is intended for a fresh Codex session. Read it fully before editing anything.

## Current Situation

The project is back at the pre-terminal-UI-connection baseline.

Important recent commits:

```text
51e0a24 Revert workstation V4 terminal UI
6fdfd70 Correct workstation V4 terminal UI
4681c2b Connect workstation V4 terminal UI
db5691a Complete pre-print workflow walkthrough
```

The V4 terminal UI connection was a mistake because the wrong prototype was used. The correct workstation design source is:

```text
ui-prototypes/workstation-v5.html
```

At the time this prompt was written, `ui-prototypes/workstation-v5.html` exists as an untracked file. Preserve it. Do not delete or overwrite it.

The V4 connection commits were reverted with a normal `git revert`, not a reset. This preserves history and returns app/docs/tests touched by that UI work to the pre-UI baseline at `db5691a`.

After revert, verification passed:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

The test suite was back to `98 passed` after the revert.

Unrelated working-tree files may exist and must be preserved unless the user explicitly says otherwise:

```text
M  INFRASTRUCTURE_IMPLEMENTATION_PLAN.md
?? HARDWARE_SETUP.md
?? prompts/milestone-9-bundle-3-planning-reassignment-resequencing.md
?? prompts/milestone-9-bundle-4-admin-production-corrections.md
?? prompts/milestone-9-terminal-sync-awareness.md
?? ui-prototypes/workstation-v5.html
```

## Goal For The Next Session

Do **not** immediately connect V5 to `/terminal`.

First, perform an adversarial exploratory review of `ui-prototypes/workstation-v5.html` as the intended workstation UI. The goal is to decide what should be improved in the prototype before implementation.

The next session should produce a concise but concrete design review and proposed change list for V5. After the user approves the changes, edit the prototype first. Only after V5 is finalized should `/terminal` be connected to it.

## Required First Reads

Read these files in this order:

1. `AGENTS.md`
2. `README.md`
3. `IMPLEMENTATION_PLAN.md`
4. `ui-prototypes/workstation-v5.html`
5. `app/templates/terminal.html`
6. `app/static/css/app.css`
7. `app/main.py`
8. `app/db.py`
9. `tests/test_terminal_detail.py`
10. `tests/test_production_timing.py`
11. `tests/test_roll_entry.py`
12. `tests/test_finish_cancel_history.py`
13. `tests/test_terminal_sync.py`

Then run:

```powershell
git status --short
git log --oneline -8
```

## What Happened With V4 And What To Avoid

The accidental V4 connection mixed the previous live `/terminal` UI with the static V4 prototype. The user was not satisfied, correctly identifying that:

- The connected UI was neither the old implementation nor the intended prototype.
- It kept old machine tiles and fields that did not belong in that prototype.
- It bolted old material fields below the recipe table instead of treating the recipe/material table as the editable surface.
- It introduced backend changes for per-row recipe material persistence before the correct UI was chosen.

Those changes were reverted.

Avoid repeating this failure. The next implementation should not be a partial merge of old terminal UI and prototype UI. When the implementation phase eventually happens, the live `/terminal` should follow the finalized V5 interaction model deliberately.

## Workstation V5 Initial Observations

`workstation-v5.html` is structurally different from V4. It appears to use:

- A framed `.page > .app` shell.
- A left `.rail` focused on machines, not a generic active/completed card list.
- Four machine cards with status, selected state, order/customer, progress, and machine metadata.
- A queue button in the rail.
- A main topbar focused on the selected machine/order.
- A details panel containing card fields, notes, and recipe.
- An input panel focused on roll entry, tare helper, totals, remaining amount, and recent roll list.

This means the design discussion should consider machine-first workflow explicitly.

## Key Design Questions To Review Before Editing

Review V5 against the confirmed README workflow and identify what should change before implementation:

- Should the left rail show only the four machines, or should it also expose pending queue and completed/cancelled history?
- If the rail is machine-first, how should operators select pending cards behind a machine queue?
- How should completed/cancelled cards be reached for review/correction/reprint later?
- Should the main view always be the focused card for a selected machine, or should it support a separate queue/list overlay?
- How should Start/Pause/Resume/Finish/Cancel/Restore/Print appear in V5?
- Which buttons should be disabled for pending/running/paused/completed/cancelled cards?
- Should print be visible but disabled until Milestone 10, or hidden until print exists?
- Should recipe/material rows be editable directly in the table?
- Which recipe cells are imported/read-only and which are terminal-entered?
- If recipe/material rows are editable per row, what backend storage shape is needed?
- Should prior roll weights be editable inline in the V5 roll list, or should roll correction use a separate edit mode/control?
- Where should stale-write/update-banner behavior appear in V5?
- How should validation/result messages fit without breaking the compact workstation layout?
- Does V5 need Bulgarian text normalized from mojibake before implementation?
- Does the layout fit the actual terminal screen size, or should fixed widths/heights be adjusted?
- Is the V5 color/spacing/typography appropriate for a production workstation, or should it be denser/clearer?

## Important Backend Note: Recipe/Material Rows

During the mistaken V4 correction, a possible backend design was briefly implemented and then reverted:

- A separate `recipe_material_entries` table with one row per card/component.
- Component keys such as `a`, `b`, `c`, `linear_pe`, `antistatic`, `masterbatch`, `chalk`.
- Columns for terminal-entered `material`, `brand`, and `batch`.
- A version-checked helper like `update_terminal_recipe_material(...)`.

This may still be the right direction if V5 keeps editable recipe/material table cells. However, it was reverted because it belonged to the wrong UI implementation. If this idea is reintroduced, do it deliberately after V5 is approved, with focused tests and with preservation of imported workbook fields.

Important invariant:

- Imported workbook/front-card material fields must remain separate from terminal-entered material/brand/batch corrections.
- Re-import must not overwrite terminal-entered recipe/material, rolls, tare, timing, status, or other production data.
- All terminal writes must keep `loaded_version` stale-write protection.

## Non-Scope

Do not implement in the next review step unless the user explicitly approves:

- Connecting V5 to `/terminal`.
- Print output.
- Admin redesign.
- User accounts/login/permissions.
- WebSockets/SSE/background services.
- Non-extrusion workflows.
- Writing terminal data back to Excel.

## Recommended Next-Session Flow

1. Read the required files.
2. Inspect `workstation-v5.html` carefully.
3. Compare V5 to README-confirmed workflow and current backend capabilities.
4. Produce an adversarial design review:
   - what is good and should stay
   - what is inconsistent with the workflow
   - what is missing
   - what should be changed before implementation
   - what backend implications each change has
5. Ask the user to choose/approve the V5 changes.
6. After approval, edit `ui-prototypes/workstation-v5.html` first.
7. Only after the prototype is finalized, create a separate implementation plan/prompt to connect V5 to `/terminal`.

## Verification Expectations If Prototype Is Edited

If the next session edits only `ui-prototypes/workstation-v5.html`, at minimum:

- Inspect the file visually in a browser if practical.
- Avoid mutating app/backend files.
- Do not run full backend tests unless app files change.
- Preserve unrelated working-tree files.

If app files are changed later during V5 connection, run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

Use a temporary SQLite database for any manual app workflow checks.

## Final Response Expectations For The Review Session

Keep the response direct and useful:

- state whether V5 is directionally correct
- list the concrete design issues found
- propose a prioritized change list before implementation
- call out any backend/data model implications
- do not start implementation until the user approves the prototype direction
