# AGENTS.md

This file defines how future agents should work in this repository. `README.md` is the authoritative project specification. `IMPLEMENTATION_PLAN.md` is the milestone tracker. If this file conflicts with `README.md`, follow `README.md` and update this file only after the user confirms the change.

## Project Scope

This repository is a bounded pilot app for the extrusion terminal workflow.

Confirmed scope:

- One FastAPI web app.
- SQLite database.
- One terminal route: `/terminal`.
- One shift-manager route: `/admin`.
- Four fixed extrusion machines.
- CSV import from the shift-manager Excel workbook.
- Admin review, machine assignment, sequence assignment, and release.
- Terminal execution of released extrusion operational cards.
- Roll gross-weight entry, order-level tare weight, calculated net totals.
- Production timing with start, pause, resume, and finish segments.
- Completed cards remain available on the workstation for review, correction, and reprint. Cancelled cards remain available to shift-manager/admin, not to workstation operators.
- HTML/CSS print output for completed cards, matching the existing Excel front/back operational card as closely as possible.
- SQLite-safe backups and documented recovery before pilot use.

Explicitly out of scope unless the user confirms otherwise:

- Users, roles, login, or permissions.
- Non-extrusion workflows.
- Detailed machine performance or downtime tracking.
- Writing terminal-entered data back to Excel.
- Public internet exposure.
- Expanding this pilot into a permanent ERP replacement.

## Engineering Principles

- Build one workflow slice at a time.
- Keep the implementation simple, inspectable, and recoverable.
- Prefer explicit Python, direct `sqlite3`, server-rendered templates, and clear SQL.
- Do not add frameworks, background services, or abstractions unless they remove real complexity.
- Backend/database rules must enforce important invariants; the UI must not be the only protection.
- Use SQLite constraints where they cleanly protect data integrity.
- Every operator/admin action that changes production data must persist immediately.
- Do not silently discard or overwrite production data.
- Preserve imported order-card data separately from terminal-entered roll/timing data.
- Keep workbook automation read-only with respect to existing workbook data.
- Use simple optimistic conflict detection for admin/terminal edits once editable card details are implemented.

## Implementation Rules

For each feature slice:

1. Define the behavior and validation rules.
2. Implement backend/database behavior first.
3. Add the minimal UI needed for the workflow.
4. Add or update automated checks for the behavior.
5. Run one manual workflow test through the app.
6. Review the changed code.
7. Commit the milestone.

Do not leave large uncommitted feature piles. Do not mix unrelated refactors into a feature slice.

When a milestone starts or completes, update `IMPLEMENTATION_PLAN.md` in the same branch. The plan should always make the next intended step obvious.

## Validation Rules

Important rules must be enforced in backend code and, where practical, SQLite constraints:

- Imported cards must persist before release.
- Machine assignment is required before release.
- Machine sequence is required before release.
- Active machine queues must be normalized to contiguous sequence positions starting at `1`.
- Release, reassignment, and resequencing treat the entered sequence as a target position and shift other active cards instead of leaving gaps.
- Duplicate active sequence numbers within the same machine queue must still be impossible after saving.
- A machine cannot have more than one running card.
- Re-import must update imported/front-card fields only.
- Re-import must preserve roll entries, timing segments, tare weight, status, machine-side fields, and other production data.
- Admin/terminal edits must not silently overwrite a card that changed after the page was loaded.
- Conflict handling should warn and require reload; do not build complex merge tooling for this pilot.
- Roll numbers are assigned per card starting at `1`.
- Roll gross weights support up to two decimal places.
- Net weight is gross weight minus order tare weight.
- Finish must be blocked unless tare weight exists, the timer was started at least once, and at least one gross roll exists.
- Finish must close any active timing segment.
- Printing is allowed only for completed cards.

## Testing Expectations

Before continuing beyond the current import/release milestone, add automated tests for existing behavior:

- database initialization seeds machines `1` through `4`
- CSV import creates imported cards
- no-extrusion rows are reported and skipped without creating cards
- duplicate imports are skipped by default
- overwrite import preserves production data
- release requires current fields that represent usable extrusion work
- release inserts at the requested target position and normalizes active machine sequence
- released cards appear in machine queues
- version/conflict checks block stale edits once editable card forms exist

As new slices are implemented, add tests for:

- terminal card selection
- start/pause/resume timing segments
- one running card per machine
- tare and roll entry
- roll correction
- finish validation
- completed workstation queue behavior and admin cancelled-card behavior
- backup and restore behavior
- print eligibility

Tests can use temporary SQLite database paths. Do not test by mutating the real runtime database unless the user explicitly asks for that manual test.

## VM Development And UI Verification

- The normal development environment for this repository is the Linux VM checkout.
- Use the repo-local Python virtualenv `.venv`.
- Use local Node Playwright installed in this repo for browser verification.
- Do not run npm with sudo.
- Do not install npm packages globally.
- Do not mutate the real runtime database during tests.
- For UI changes, verify against the live FastAPI app with Playwright before claiming completion.
- Save screenshots/videos/traces under `artifacts/ui-checks/`.
- `artifacts/`, `node_modules/`, Playwright reports, screenshots, videos, traces, and local databases must stay untracked.
- Before saying UI work is complete, run focused tests and capture at least one relevant Playwright screenshot.
- Do not stage or commit unless the user explicitly asks.

Python tests:

```bash
source .venv/bin/activate
python -m pytest
```

Start local server:

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Playwright:

```bash
npx playwright test
```

## Review And Commit Policy

Review every milestone before committing. The review should check:

- data integrity
- validation failures and user-visible messages
- preservation of existing production data
- direct workflow behavior in `/admin` and `/terminal`
- whether the change stayed within the confirmed scope

Before each commit, run:

- Python syntax/import checks
- relevant automated tests
- `git diff --check`
- a focused manual app check when UI behavior changed

Current baseline test command:

- `.\.test-runtime\codex-venv\Scripts\python.exe -m pytest`

The automated tests live under `tests/` and must use temporary SQLite database paths. They must not mutate the real runtime database at `data/extrusion_terminal.sqlite3`.

Commit messages should describe the milestone, not internal implementation noise.

## Operational Safety

Before pilot use, this repository must include:

- documented startup command
- documented shutdown/restart procedure
- database location
- backup location
- SQLite-safe backup command and approved backup job if scheduling is later confirmed
- restore procedure
- basic troubleshooting notes for failed imports, duplicate releases, and server restart

Do not expose the app directly to the public internet. Remote access, if used, should follow the confirmed Tailscale direction from `README.md`.

## Current Milestone State

Completed and committed:

- FastAPI + SQLite scaffold.
- seeded machines `1` through `4`.
- `/health`, `/admin`, and `/terminal`.
- CSV import into persistent imported cards.
- Excel read-only export macro module.
- admin machine/sequence release.
- terminal queue visibility for released cards.
- automated baseline tests for import/release behavior.
- terminal card detail view and first version-checked material-field edit.
- production timing actions: start, pause, resume, one running/occupied card per machine, and timing segments.
- tare and roll entry: order-level tare, gross roll entry, roll corrections, roll deletion with automatic renumbering, and gross/net totals.
- finish and history behavior: finish validation, active segment closure, completed workstation archive visibility, and admin-side reversible cancellation.
- backup and recovery behavior: SQLite-safe timestamped backups, restore helper, retention, startup/restart documentation, and troubleshooting notes.
- admin production corrections: admin-side cancel/restore, terminal material corrections, tare and roll corrections, and timing segment corrections with loaded-version conflict checks.
- pre-print workflow walkthrough: temporary-database pass through import, admin review/edit, planning/resequence, terminal timing/tare/roll/finish, completed archive visibility, stale-write blocking, admin correction, admin cancel/restore, and running-card timing invariant checks.
- workstation V8 live terminal connection: `/terminal` uses the live server-rendered V8 workstation layout with four-machine navigation, active queue drawer, completed lookup, selected-card details, recipe rows, material corrections, tare/roll controls, totals, timing actions, sync banner behavior, read-only maximum roll weight, and no workstation cancellation/restore controls.

Next recommended milestone:

- Continue with Slice 4 from `WORKSTATION_V8_CONNECTION_PLAN.md`: functional hardening and edge cases for the live V8 workstation. Do not start print output yet.
- Keep `workstation-v7.html` as the checkpoint before the top-machine-navigation restructure. The V8 workstation must not expose cancellation or restore controls; cancellation remains an admin/shift-manager action.
