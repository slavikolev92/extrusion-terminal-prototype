# Terminal Timing Correction And Finish Review Design

Date: 2026-08-21

Status: Approved through user discussion and V2 static-prototype review on
2026-08-21.

## Goal

Allow extrusion operators to correct production timing while an operational
card is running or paused, and give them one final opportunity to review and
correct timing before completing the card. After completion, terminal timing
is read-only and only Admin may correct historical timing.

## Terminal Availability And Placement

The timing editor is available for `running` and `paused` cards. A `pending`
card must first use the existing Start action; the operator may then correct
the recorded start. The editor is absent for imported, pending,
awaiting-rewinding, completed, archived, and cancelled cards.

For a running or paused card, the editor opens from a new ellipsis/overflow
menu item labelled `Производствено време`. The item uses the supplied
`ui-prototypes/clock-icon.png` asset.

The implementation must not change the rendering, styling, enabled state,
order, or lifecycle eligibility of the existing Start, Pause/Resume, and Finish
controls. Only active-card Finish submission changes by opening the approved
review before persistence. The prototype's illustrative Print/Reprint menu
item is not part of this feature; terminal printing remains unchanged.

## Interval Model

The existing `production_time_segments` ledger remains authoritative. Each
row is productive machine time with a start and an optional stop. Pauses are
not stored separately: the gap between one interval's stop and the next
interval's start is the pause.

The editor presents chronological rows with:

1. interval number;
2. start date and `HH:MM`;
3. stop date and `HH:MM`, with a completely blank cell for the final open
   interval;
4. calculated interval duration; and
5. a neutral `×`/Undo control.

It shows `Производствено време`, calculated as the sum of productive
intervals, and `Общо паузирано време`, calculated as the sum of the gaps
between consecutive intervals. It does not add a pause record, an Add Pause
action, drag-and-drop editing, or cross-card/machine conflict detection.

While the ordinary editor is open for a running card, the blank final interval
is calculated through current server time for provisional duration and
production total display only. That preview end is never saved.

## Ordinary Timing Correction

The modal provides Add Interval, Save, and Cancel.

- Closed intervals may have their starts and stops corrected.
- A running card must retain exactly one final open interval.
- The final open interval's stop cell is blank and cannot accept an ordinary
  final-stop value while production remains running.
- Adding an interval while running closes the preceding interval and creates a
  new final open interval. The operator must enter the preceding stop and new
  start; their difference is the implied pause. The editor must not silently
  invent either timestamp.
- A paused card contains only closed intervals. A newly added paused-card
  interval starts with required blank fields and requires both a start and a
  stop.
- Delete marks a row for removal and exposes Undo. No deletion is persisted
  before Save.
- Cancel discards the complete draft.
- Save writes the complete proposed ledger atomically.

Manual corrections use minute precision. An untouched stored timestamp keeps
its existing seconds. When an operator changes a timestamp, its saved seconds
become `00`.

The time field accepts numeric input and inserts the colon automatically after
the first two digits: `13` renders as `13:` and `1350` or `13:50` renders as
`13:50`. Non-digits are ignored. Incomplete and invalid 24-hour values cannot
be saved and the first invalid field receives focus. Dates use the native date
input rendered by the workstation browser.

## Finish Review

Clicking Finish freezes the proposed finish time at that click. Time spent
reviewing the confirmation does not extend production. The server binds the
card, loaded version, and frozen time into an authenticated, non-persistent
review token; Preview and Confirm reject a missing, altered, or unverifiable
token. A process restart invalidates any review that was already open.

The finish summary shows:

- first start time;
- proposed stop time;
- `Производствено време`;
- `Общо паузирано време`;
- Edit Intervals;
- Cancel; and
- Confirm Finish.

For a running card, the frozen proposed stop closes the final open interval.
For a paused card, the latest closed interval's stop is the proposed finish
time.

Finish-review edits may move timestamps retrospectively but may not move any
timestamp later than the frozen click time. This ensures that time spent in the
review does not extend production.

Edit Intervals opens the same reusable interval editor in finish-review mode.
Applying draft changes returns to the recalculated summary without persisting
them. Confirm Finish saves the corrected ledger and completes the card in one
transaction. Cancel discards all finish-review changes and leaves the card
unchanged.

If finish validation fails, the card and timing ledger remain unchanged and
the finish review stays available with a clear error. Existing roll, tare,
rewinding, mixed-pallet warning, active-shift, final-shift attribution, and
queue-normalization rules continue to apply. Awaiting-rewinding finalization
keeps its current confirmation flow and must not mutate timing or
`finished_at`.

## Validation

The shared backend correction engine must reject:

- missing, malformed, impossible, or ambiguous Sofia-local dates or times;
- a changed, new, or frozen timestamp later than SQLite's current transaction
  time;
- a closed interval whose stop is not strictly after its start;
- overlapping intervals within the same card;
- more than one open interval;
- an open interval on a non-running card;
- a running card without exactly one chronologically final open interval;
- a paused card without at least one closed interval;
- an unknown segment or a segment belonging to another card; and
- a stale loaded card version.

Adjacent intervals are valid. The browser may provide immediate input help,
but server validation is authoritative. Sofia-to-UTC conversion continues to
use `app/timekeeping.py`. Non-existent local times are rejected. An unchanged
timestamp in a repeated hour preserves its stored UTC instant; a new or changed
repeated-hour minute is rejected as ambiguous because the approved editor does
not expose a UTC-offset selector.

No cross-card or machine-conflict validation is part of this feature.

## Persistence And Concurrency

Admin and Terminal use one internal timing-ledger preparation, validation, and
mutation implementation, with separate access policies. Terminal correction
requires an active shift and a `running` or `paused` card. Admin retains its
existing broader correction access.

Every standalone timing correction uses `BEGIN IMMEDIATE`, checks the loaded
version before mutation, and either writes the whole ledger or writes nothing.
When the shared ledger core is invoked inside the existing Admin Save All
transaction, it participates in that outer transaction and preserves the
existing Admin version behavior. A Terminal timing save increments the card
version exactly once. Confirm Finish applies the timing draft and lifecycle
transition under one version check and increments the card version exactly
once.

Existing end reasons are preserved. A newly created closed correction row uses
`correction`; closing an open row to create another running interval uses
`pause`; the final running closure uses `finish`.

Timing correction may update segments, `first_started_at`, derived totals, and
the completion `finished_at`. It must preserve rolls, roll shift attribution,
materials, machine assignment and sequence, rewinding information, final
extrusion shift attribution, tare/pallet data, and every unrelated card field.

If another page changes the card while either modal is open, the draft becomes
stale. The terminal must retain the visible draft, lock its fields and write
actions, and require reload or Cancel rather than silently overwrite newer
data.

## Approved V2 UI Contract

The accepted visual reference is
`ui-prototypes/terminal-timing-correction.html`. This written specification is
authoritative for data behavior: unlike the prototype's illustrative demo
script, Add Interval must not invent timestamps, and a pending-deleted row
keeps its visible number until Save succeeds.

- The timing dialog is `1040px` wide when space permits and has a `728px`
  working height, both limited by a `20px` viewport margin.
- The title, totals, column headings, and footer remain fixed. Only the interval
  row body scrolls; its vertical scrollbar activates automatically as rows
  exceed the available height.
- Start, Stop, Duration, and Action columns use extra padding and subtle
  low-contrast vertical separators.
- The compact `×` delete control and pending-delete/Undo state use neutral
  table colors, not red emphasis.
- The interaction includes pending deletion, validation error, stale locked
  draft, summary-to-editor-to-summary finish review, focus trapping, Escape,
  Cancel, focus restoration, and double-submit protection.
- The layout was accepted at `1366×768` and `1920×1080`.

The clock may be missing only when the standalone HTML file is copied without
its adjacent PNG. The application implementation must serve a copied static
asset with explicit visible dimensions so the menu icon loads normally.

## Migration

No database migration is required.

## Verification

Focused tests must prove shared Admin/Terminal ledger behavior, terminal
status and active-shift policy, future and interval validation, minute/second
handling, stale-write rejection, atomic finish review, preservation of
unrelated production data, and the existing finish branches.

The completed UI requires a live Playwright check against a temporary SQLite
database, including ordinary save, finish review, cancellation, validation
failure, stale takeover, keyboard focus, overflow-menu icon loading, unchanged
lifecycle controls, blank final stop, numeric time masking, many-row scrolling,
and screenshots at supported terminal viewports. Tests and browser checks must
not mutate the runtime database.
