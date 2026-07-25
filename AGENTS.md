# AGENTS.md

This file defines how future agents should work in this repository. `README.md`
is the authoritative project specification. If this file conflicts with
`README.md`, follow `README.md` and update this file only after the user confirms
the change.

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
- Use simple optimistic conflict detection for admin/terminal edits; stale writes should warn and require reload.

## Implementation Rules

For each feature slice:

1. Define the behavior and validation rules.
2. Implement backend/database behavior first.
3. Add the minimal UI needed for the workflow.
4. Add or update automated checks for the behavior.
5. Run one manual workflow test through the app.
6. Review the changed code.
7. Prepare the change for review. Stage or commit only when the user explicitly asks.

Do not leave large uncommitted feature piles. Do not mix unrelated refactors into a feature slice.

Use `docs/implementation-notes/` for durable implementation notes that future prototype or ERP work may need to understand why a feature was built a certain way. Current contents include `print-output-reference.md`, which preserves the accepted print-output requirements, field mapping, validation/formatting rules, and the note that the remaining two-sheet print issue is local workstation/printer setup rather than an app defect.

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

Maintain automated tests for existing baseline behavior:

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

Playwright installation check:

```bash
./node_modules/.bin/playwright --version
```

There is currently no repository-wide Playwright test suite. For UI changes,
run a task-specific browser check against the live FastAPI app using a temporary
SQLite database, save the evidence under `artifacts/ui-checks/`, and record the
exact verification command. Use the repo-local Playwright installation; do not
download or install browser tooling implicitly during verification.

## Review And Commit Policy

Review every feature slice before asking to commit or when the user explicitly asks for a commit. The review should check:

- data integrity
- validation failures and user-visible messages
- preservation of existing production data
- direct workflow behavior in `/admin` and `/terminal`
- whether the change stayed within the confirmed scope

Before any user-approved commit, run:

- Python syntax/import checks
- relevant automated tests
- `git diff --check`
- a focused manual app check when UI behavior changed

Current baseline test command:

```bash
source .venv/bin/activate
python -m pytest
```

The automated tests live under `tests/` and must use temporary SQLite database paths. They must not mutate the real runtime database at `data/extrusion_terminal.sqlite3`.

Commit messages should describe the completed change, not internal implementation noise.

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

## Active V2 Update Workspace

For work in the July 25-26, 2026 update, read `v2-files/AGENTS.md` and follow its
routing. The phrase “maintain the database migration system” activates the full
assessment, implementation, testing, and recordkeeping workflow defined there.
Do not require the user to repeat technical migration instructions.
