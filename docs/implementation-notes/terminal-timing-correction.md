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

Add Interval does not invent operator timestamps. For a running card it inserts
a fully blank closed row immediately before the unchanged final open interval;
for a paused card it appends a fully blank closed row. A deletion remains a
draft-only change until Save. An eligible `Изтрий` action opens a small in-app
confirmation above the unchanged timing editor with
`Сигурни ли сте, че искате да изтриете интервал №N?`. Its Cancel action,
Escape key, or backdrop dismisses only the confirmation, leaves the draft
unchanged, and restores focus to the initiating Delete button. Confirmation
hides the row; an existing row remains in the submitted draft with its deletion
marker, while an unsaved row is removed from the draft entirely. The required
final open running interval and a paused card's sole remaining interval have no
Delete action. There is no pending-row or Undo state. Timing-editor Cancel or
Escape discards the entire draft—including confirmed draft deletions—while the
editor backdrop remains inert. Save validates and replaces the proposed ledger
as one atomic operation. Once ordinary Save or Finish Apply begins, all
date/time edit and dismissal controls remain interaction-locked without
disabling successful form fields. An asynchronous Apply failure restores
editing after the request completes.

The timing editor is `min(1040px, calc(100vw - 40px))` wide and follows its
content height for short ledgers, capped at
`min(728px, calc(100vh - 40px))`. Only the interval list scrolls; it is capped
at `min(430px, calc(100vh - 338px))`. Compact rows are at least `72px` high,
date/time controls remain centered at `120px` and `78px`, and neutral Delete
targets are at least `72px × 40px`. The segmented date reads as one cohesive
`DD/MM/YYYY` field without changing its segment-level selection or
serialization behavior. Column headings share the timestamp, duration, and
action axes used by the row contents. Timing durations use the compact `м`
unit in both the editor and Finish Review.

Completed-card timing is read-only on the terminal, including cards opened
through Produced Orders. Admin retains its broader historical timing
correction access. The editor is absent for imported, pending,
`awaiting_rewinding`, archived, and cancelled cards. Awaiting-rewinding
finalization keeps its simple confirmation and never changes timing or
`finished_at`.

## Time Semantics And Validation

The browser displays and accepts `Europe/Sofia` civil dates as separate numeric
day, month, and year segments in `DD/MM/YYYY` order, and times as `HH:MM`.
Clicking selects one complete date segment, completed day/month input advances
to the next segment, and deleting a segment preserves the other two. The year
retains at most four digits. Clicking the hour or minute part of a time selects
that complete part so typing replaces it without disturbing the other part.
The backend converts
through `app/timekeeping.py` and stores canonical UTC text. An untouched
timestamp preserves its stored seconds; a changed or new minute is stored with
seconds `00`. A skipped spring-forward local time is invalid. An unchanged
timestamp in the repeated autumn hour preserves its UTC instant, while a
changed/new ambiguous minute is rejected because the terminal editor has no
offset selector.

The backend rejects missing, malformed, impossible, ambiguous, or future
timestamps; non-positive intervals; overlaps; invalid open-row counts or
placement; a paused card without a closed interval; foreign/unknown segment
IDs; stale versions; and terminal corrections without an active shift. Errors
appear in one stable alert above the table and highlight the invalid timestamp
boundary. An explicit Save focuses the first invalid boundary; background
previews never steal focus or replace input elements. Calculations are cleared
while their inputs are incomplete or invalid. Browser help is immediate, but
server validation is authoritative.

## Frozen Finish Review

Finish on a running or paused card first opens a review and writes nothing. The
server freezes the proposed finish instant at that click and binds the card,
loaded version, and frozen time into an authenticated non-persistent token.
For a running card the frozen instant closes its final open interval; for a
paused card the latest closed stop is the proposed finish.

`Редактирай времето` works on the frozen draft and recalculates complete edits
automatically. Apply returns to the recalculated summary without persistence.
No edited timestamp may be later than the frozen instant. Editor Cancel discards
the editor draft and returns to the unchanged summary; summary Cancel discards
the complete review. Confirm Finish applies the reviewed ledger and lifecycle
transition in one transaction, so time spent reviewing never extends production.
Missing, changed, or unverifiable tokens are rejected, and an application
process restart invalidates every review that was already open.

Existing roll/tare requirements, mixed-pallet warning, rewinding branch,
active-shift gate, final-shift attribution, and queue normalization still apply
at Confirm Finish.

The Finish summary displays `Начало` and `Край` as `DD/MM/YY HH:MM` in one
compact timing strip with the production and paused totals. Below it, the
existing pallet summary view model renders pallet number, roll count, gross,
and net totals. `Тегло на палета, кг` is intentionally an unconnected visual
placeholder (`—`) in each pallet row and the total row; this timing feature does
not add pallet-weight storage or calculations.

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

The temporary browser fixture creates deterministic running, paused, completed,
awaiting-rewinding, and many-interval cards plus an active shift. A simple path
check keeps it below `.test-runtime`, and the verifier confirms the exact
`/health` database identity before running. Attack-oriented symlink, hard-link,
and atomic-artifact machinery is deliberately not part of this local tool.

The deterministic fixture was recreated before browser verification with:

```bash
EXTRUSION_DB_PATH=.test-runtime/terminal-timing-audit/run-cUfFjf/fixture.sqlite3 \
.venv/bin/python scripts/create_terminal_timing_correction_fixture.py \
  --db-path .test-runtime/terminal-timing-audit/run-cUfFjf/fixture.sqlite3 \
  --output .test-runtime/terminal-timing-audit/run-cUfFjf/fixture.json
```

The final focused checks were:

```bash
node --test tests/js/timing_interval_editor_core.test.mjs
.venv/bin/python -m pytest \
  tests/test_terminal_timing_correction.py \
  tests/test_terminal_v8_render.py \
  tests/test_terminal_sync.py \
  tests/test_terminal_timing_correction_ui_script_safety.py -q
```

They passed with 16 JavaScript tests and 241 Python tests. The final live
verification used:

```bash
BASE_URL=http://127.0.0.1:8015 \
FIXTURE_JSON=.test-runtime/terminal-timing-audit/run-cUfFjf/fixture.json \
ARTIFACT_DIR=artifacts/ui-checks/terminal-timing-editor-final-fix \
node scripts/verify_terminal_timing_correction_ui.mjs
```

The verifier passed with the exact fixture database reported by `/health`, no
unexpected failed requests or console/page errors, and one request each for
double-clicked Finish review and confirmation. It also proved date/time values
cannot change during delayed ordinary Save or Finish Apply and that a simulated
failed Apply restores editing. Expected `422` validation responses and
superseded preview aborts are reported separately.

The untracked visual evidence is:

- `artifacts/ui-checks/terminal-timing-editor-final-fix/timing-editor-short-ledger-1366x768.png`
- `artifacts/ui-checks/terminal-timing-editor-final-fix/timing-editor-short-ledger-1920x1080.png`
- `artifacts/ui-checks/terminal-timing-editor-final-fix/timing-delete-confirmation-1366x768.png`
- `artifacts/ui-checks/terminal-timing-editor-final-fix/timing-editor-time-selection-1366x768.png`
- `artifacts/ui-checks/terminal-timing-editor-final-fix/timing-editor-validation-1366x768.png`
- `artifacts/ui-checks/terminal-timing-editor-final-fix/timing-editor-1366x768.png`
- `artifacts/ui-checks/terminal-timing-editor-final-fix/finish-review-1920x1080.png`
- `artifacts/ui-checks/terminal-timing-editor-final-fix/verification-summary.json`

Direct visual inspection confirmed content-fitting short ledgers without dead
space at both viewports, timestamp headings aligned with their controls,
centered duration/action columns, cohesive `/`-separated dates, a compact
neutral confirmation above the unchanged editor, a stable validation alert
without row distortion, fixed editor chrome with internal row scrolling at
`1366×768`, and a centered, legible, unclipped Finish Review at `1920×1080`.
Screenshots do not establish complete screen-reader behavior or full WCAG
compliance. These ignored artifacts are verification evidence, not tracked
application files.

The final repository-wide checks were:

```bash
.venv/bin/python -m pytest -q
git diff --check
```

The full suite passed with 1133 tests; the whitespace check was clean.
