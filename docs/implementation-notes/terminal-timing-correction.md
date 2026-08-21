# Terminal Timing Correction And Finish Review

This note records the shipped workstation timing editor and reviewed Finish
flow. The existing `production_time_segments` ledger remains authoritative:
each row is productive time, while the gap between one row's stop and the next
row's start is the implied pause. Production time is the sum of intervals;
paused time is the sum of those gaps. Adjacent intervals are valid.

## Availability And Editing

The terminal overflow action `Производствено време` is available only for
`running` and `paused` cards and only while a terminal shift is active. A
running card must retain exactly one chronologically final open interval. Its
ordinary stop cell stays blank; the current server time is used only for the
live total. A paused card must retain at least one closed interval and cannot
have an open interval.

Add Interval does not invent operator timestamps. For a running card it makes
the operator supply the prior stop and next start; for a paused card it adds a
fully blank closed row. Delete is pending until Save and can be undone. Cancel
discards the entire draft. Save validates and replaces the proposed ledger as
one atomic operation.

Completed-card timing is read-only on the terminal, including cards opened
through Produced Orders. Admin retains its broader historical timing
correction access. The editor is absent for imported, pending,
`awaiting_rewinding`, archived, and cancelled cards. Awaiting-rewinding
finalization keeps its simple confirmation and never changes timing or
`finished_at`.

## Time Semantics And Validation

The browser displays and accepts `Europe/Sofia` civil dates and minute-precision
times. The backend converts through `app/timekeeping.py` and stores canonical
UTC text. An untouched timestamp preserves its stored seconds; a changed or
new minute is stored with seconds `00`. A skipped spring-forward local time is
invalid. An unchanged timestamp in the repeated autumn hour preserves its UTC
instant, while a changed/new ambiguous minute is rejected because the terminal
editor has no offset selector.

The backend rejects missing, malformed, impossible, ambiguous, or future
timestamps; non-positive intervals; overlaps; invalid open-row counts or
placement; a paused card without a closed interval; foreign/unknown segment
IDs; stale versions; and terminal corrections without an active shift. The
first invalid field receives focus. Browser help is immediate, but server
validation is authoritative.

## Frozen Finish Review

Finish on a running or paused card first opens a review and writes nothing. The
server freezes the proposed finish instant at that click and binds the card,
loaded version, and frozen time into an authenticated non-persistent token.
For a running card the frozen instant closes its final open interval; for a
paused card the latest closed stop is the proposed finish.

Edit Intervals works on the frozen draft and Apply returns to a recalculated
summary without persistence. No edited timestamp may be later than the frozen
instant. Cancel discards the review. Confirm Finish applies the reviewed ledger
and lifecycle transition in one transaction, so time spent reviewing never
extends production. Missing, changed, or unverifiable tokens are rejected, and
an application process restart invalidates every review that was already open.

Existing roll/tare requirements, mixed-pallet warning, rewinding branch,
active-shift gate, final-shift attribution, and queue normalization still apply
at Confirm Finish.

## Atomicity, Versions, And Preservation

A standalone terminal correction uses `BEGIN IMMEDIATE`, checks the loaded card
version, and writes the complete ledger or nothing. It increments the card
version exactly once. Confirm Finish performs timing replacement and the
lifecycle transition under one version check and also increments once. The
shared correction engine participates in Admin Save All's existing outer
transaction and version behavior.

Existing segment end reasons are retained. A new closed correction row uses
`correction`; closing an open interval before another running interval uses
`pause`; the final running closure uses `finish`.

Correction may update timing segments, `first_started_at`, calculated totals,
and completion `finished_at`. It preserves rolls and roll-shift links,
materials, machine assignment and sequence, rewinding fields, final extrusion
shift, tare/pallet defaults and snapshots, imported fields, and every unrelated
card value.

If another page changes the card while the editor or Finish review is open,
the visible draft is retained but locked. Save/Apply/Confirm remain unavailable
until reload; Cancel is still allowed. The newer card is never overwritten.

No migration required.

## Verification Record

The guarded browser fixture creates deterministic running, paused, completed,
awaiting-rewinding, and many-interval cards plus an active shift. It refuses the
runtime database, every path outside its dedicated
`.test-runtime/terminal-timing-correction/` subtree, symlinks, hard links, and
conflicting database environment values. Existing DB/JSON targets are replaced
only when matching ownership tokens in both files positively identify a prior
copy of this fixture; regeneration publishes a fresh database file rather than
unlinking the old path.

The verifier accepts fixtures only from that same dedicated subtree and checks
the exact resolved `/health` database identity before claiming an artifact
directory. `ARTIFACT_DIR` must be a pre-created, empty, uniquely named directory
at or below `artifacts/ui-checks/terminal-timing-correction/`. Screenshot and
summary buffers are written once through exclusive no-follow descriptors; the
descriptor and directory-entry inode/link state is checked before and after the
atomic rename. Existing destinations are never replaced.

The live verification used:

```bash
EXTRUSION_DB_PATH=/home/sk/projects/extrusion-terminal/.worktrees/terminal-timing-correction/.test-runtime/terminal-timing-correction/verified-run/fixture.sqlite3 \
EXTRUSION_DATA_DIR=/home/sk/projects/extrusion-terminal/.worktrees/terminal-timing-correction/.test-runtime/terminal-timing-correction/verified-run \
.venv/bin/python scripts/create_terminal_timing_correction_fixture.py \
  --db-path /home/sk/projects/extrusion-terminal/.worktrees/terminal-timing-correction/.test-runtime/terminal-timing-correction/verified-run/fixture.sqlite3 \
  --output /home/sk/projects/extrusion-terminal/.worktrees/terminal-timing-correction/.test-runtime/terminal-timing-correction/verified-run/fixture.json

EXTRUSION_DB_PATH=/home/sk/projects/extrusion-terminal/.worktrees/terminal-timing-correction/.test-runtime/terminal-timing-correction/verified-run/fixture.sqlite3 \
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8014

mkdir -p artifacts/ui-checks/terminal-timing-correction
ARTIFACT_RUN_DIR=$(mktemp -d artifacts/ui-checks/terminal-timing-correction/run-XXXXXX)
BASE_URL=http://127.0.0.1:8014 \
FIXTURE_JSON=.test-runtime/terminal-timing-correction/verified-run/fixture.json \
ARTIFACT_DIR="$ARTIFACT_RUN_DIR" \
node scripts/verify_terminal_timing_correction_ui.mjs
```

The verifier passed with the exact fixture database reported by `/health`, no
unexpected HTTP responses, console errors, page errors, or failed requests, and
one final request each for double-clicked Finish review and confirmation after
a bounded request-quiescence window. The deliberately exercised validation
`422` and its exact browser console line are recorded separately as expected. A
preview `ERR_ABORTED` is accepted only when correlated to a later preview or to
one narrowly declared transition; the summary records the correlation. Route
gates have bounded waits and always release and unregister in cleanup. The
server was stopped after the run.

The untracked visual evidence is:

- `artifacts/ui-checks/terminal-timing-correction/run-XXXXXX/timing-editor-1366x768.png`
- `artifacts/ui-checks/terminal-timing-correction/run-XXXXXX/finish-review-1920x1080.png`
- `artifacts/ui-checks/terminal-timing-correction/run-XXXXXX/verification-summary.json`

Visual inspection confirmed fixed editor chrome with internal row scrolling at
`1366x768`, and a centered, legible, unclipped Finish review with all actions
visible at `1920x1080`. These ignored artifacts are verification evidence, not
tracked application files.

Focused and repository-wide checks use:

```bash
.venv/bin/python -m pytest tests/test_terminal_timing_correction_ui_script_safety.py -q
.venv/bin/python -m pytest tests/test_terminal_timing_correction.py tests/test_terminal_v8_render.py tests/test_terminal_sync.py -q
node --test tests/js/timing_interval_editor_core.test.mjs
.venv/bin/python -m pytest -q
```
