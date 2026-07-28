# Task 10: Roll-Change Countdown Specification

Status: implemented and verified on July 27, 2026. The accepted behavior below
is implemented without SQLite persistence or production-data coupling. Final
evidence and the durable operating boundary are linked in the implementation
handoff.

## Purpose

Give extrusion operators a lightweight reminder for the next synchronized roll
change on a machine after the film dimensions, thickness, and production speed
have stabilized.

The countdown is an operational pace clock. It is not a production record and
does not claim to capture the physical roll-change timestamp. Operators may
physically change all winding lanes at the scheduled time, then weigh the rolls,
assemble or wrap the pallet, complete other urgent work, and enter the rolls at
the terminal later. Delayed terminal entry must not move the expected schedule.

## Existing Physical Process

- One blown-film extrusion machine may wind one sleeve/tube roll or several
  slit flat-film rolls at the same time.
- When a setup has several winding lanes, the lanes move at the same pace and
  their rolls are normally changed together.
- After the line reaches its correct dimensions, thickness, and stable speed,
  operators can estimate the repeatable time needed to produce the next set of
  rolls.
- Physical roll changing, weighing, pallet work, wrapping, and terminal entry
  are separate activities. Terminal roll-entry time is therefore not a reliable
  physical roll-change time.
- Machines 2 and 3 are the likely initial users, but the feature is optional and
  available on every machine so operators can decide where it is useful.

## Chosen Design

Use one optional repeating schedule for the current production order on each
machine.

The schedule has:

- a previous change/start time;
- one positive interval entered in whole hours and minutes; and
- one next expected change time.

The first next expected change is calculated from the start time plus the
interval. The frequent one-touch action advances from the saved next expected
time, preserving the scheduled cadence. It always advances at least once and,
if several intervals are already overdue, skips whole scheduled intervals until
the new next expected time is strictly in the future.

The less frequent editor allows operators to correct the start time, interval,
or next expected change after a breakdown, pause, speed change, dimension
change, or other disruption.

The alternatives were rejected:

- Linking the countdown to gross-weight entry would inherit the known delay
  between physical roll changing and terminal entry.
- Advancing only one interval when several are already overdue would leave the
  reminder immediately red after a valid acknowledgement and force repeated
  clicks without adding useful information.
- A timer per lane is unnecessary because all lanes on the machine run and are
  changed together.
- Machine/PLC integration, length encoders, roll-diameter measurement, and
  automatic roll-change signals are outside this pilot.
- A database event/history ledger would create production data and reporting
  obligations that this optional reminder does not need.

## Scope And Ownership

- There is at most one countdown for a machine's current production order.
- One countdown represents the complete synchronized winding set, whether that
  set contains one, two, four, or another number of physical rolls.
- The countdown belongs to the current card on the machine, not permanently to
  the machine and not to an individual roll entry.
- The feature is available on all four machine cards but remains inactive until
  an operator deliberately configures it.
- Starting production does not automatically create a countdown. Operators
  configure it only after the line has reached a useful repeatable pace.
- A new order never inherits the previous order's schedule.
- The countdown does not add, change, correct, or delete roll weights, pallet
  numbers, tare weights, timing segments, shift attribution, or imported fields.

## Schedule Calculation

### Initial calculation

Given:

```text
previous change/start time = 12:00
interval                   = 02:00
```

the calculated next expected change is:

```text
next expected change       = 14:00
```

### Normal acknowledgement

The quick action always advances from the saved schedule:

```text
new previous change      = last scheduled boundary before the new next time
new next expected change = first scheduled boundary strictly after the click
```

Example:

```text
current expected change = 14:00
operator clicks          = 14:20
interval                 = 02:00
new previous change      = 14:00
new expected change      = 16:00
```

The acknowledgement preserves the two-hour scheduled cadence. It does not
claim that the physical change occurred when the terminal button was pressed.

One click advances at least one interval. If the saved expected time is several
intervals overdue, the same click skips whole scheduled intervals until the new
expected time is strictly in the future. If the schedule itself has become
materially wrong, the operator corrects it in the editor.

### Manual next-time override

The calculated next expected time is editable.

Example:

```text
calculated next expected change = 16:00
operator override               = 16:30
interval                         = 02:00
```

After saving, the active countdown targets 16:30. That edited value becomes the
scheduled anchor. The next quick acknowledgement advances from 16:30 in whole
two-hour intervals until the next expected time is strictly in the future.

### Time representation

- Inputs use the workstation's local date and time.
- Operators enter hours and minutes only; they never enter seconds.
- Internally, calculations use absolute local timestamps so schedules remain
  correct across midnight and page refreshes.
- The initial start-time control defaults to the current local time. If an
  operator enters only a time of day, it represents the most recent occurrence
  of that time that is not later than the current moment.
- The next expected time displays its date when it falls on a different local
  calendar day; otherwise the normal display may show only `HH:MM`.
- Remaining time is displayed as `HH:MM`. A positive partial minute rounds up,
  so `00:01` remains visible until the due instant and `00:00` never appears
  early. Warning boundaries and the due state use the unrounded internal time.

## Countdown States

### Inactive

- No schedule exists for the current card.
- No timer bubble is rendered in the machine card's top-right position.
- No timer state is inherited from a previous card.
- The machine-state dot remains visible.

### Active, normal

- The machine card and selected-card control show the remaining countdown.
- The selected-card control also exposes the next expected wall-clock time.
- More than five minutes remaining uses the normal countdown treatment.

### Approaching

- From exactly `05:00` remaining through `01:01` remaining, the countdown uses
  the yellow warning treatment.
- Color is accompanied by the numeric time; warning meaning is never conveyed
  by color alone.

### Urgent

- From exactly `01:00` remaining through the due instant, the countdown uses
  the red urgent treatment.
- At the due instant, the display becomes `00:00`.

### Due and unacknowledged

- A running order remains at red `00:00` until the operator uses the quick
  acknowledgement, corrects the schedule in the editor, clears tracking, or
  ends the order.
- The display never counts into negative time.
- The schedule never advances automatically because that would falsely assume
  the physical change happened and could hide a missed change.

### Paused

- Pausing the production order immediately freezes the displayed remaining
  duration.
- A paused countdown uses the yellow paused treatment at every remaining value,
  including `00:00`. Red urgency is suppressed while the machine is paused.
- The paused machine-state dot is also yellow.
- The quick acknowledgement remains available while paused.
- A quick acknowledgement while paused uses the same scheduled-cadence rule:
  it advances at least once and catches up through whole intervals when needed.
  The resulting future duration remains frozen and visibly paused while the
  card remains paused.
- Resuming production does not invent a correction for a disrupted schedule.
  If the countdown was not acknowledged or edited during the pause, it remains
  frozen and visibly unresolved until the operator uses the quick action or
  saves the corrected next expected time in the editor. A positive unresolved
  value uses yellow resynchronization styling. An unresolved `00:00` returns to
  red as soon as the card is running again because the paused override no
  longer applies.
- Once the operator has acknowledged or saved a corrected schedule, normal
  counting and warning colors resume when production is running.
- If the operator acknowledged or saved a corrected schedule while the card was
  paused, that schedule is already resolved and begins normal counting when the
  card resumes.

This deliberately simple first version lets operator feedback determine whether
a later design should automatically preserve remaining production time or shift
the expected time by the pause duration.

### Order ended or replaced

The schedule is cleared when:

- the card is completed;
- the card enters `awaiting_rewinding`;
- the card is archived or cancelled;
- the card returns to a non-running planning state; or
- a different current card takes over the machine.

The next order begins with tracking inactive. Nothing is copied forward.

## Main-Bar Controls

The selected running or paused card places countdown controls beside, but
visually separated from, the existing Start, Pause/Resume, and End actions.

- When tracking is inactive, show only one setup control labelled
  `Смяна на ролка`. It opens the editor.
- When tracking is active, that setup control becomes the countdown/editor
  control and the quick acknowledgement icon appears beside it.
- Pending, awaiting-rewinding, completed, archived, and cancelled cards show no
  countdown controls.

### Countdown/editor control

- The larger control displays the remaining countdown.
- It also displays or exposes the next expected wall-clock time without making
  the machine cards carry excessive text.
- Pressing it opens the full schedule editor.
- Because the countdown itself opens the editor, there is no separate Edit or
  menu button.

### Quick acknowledgement

- A small icon-only button sits immediately beside the countdown control.
- Use a familiar circular-arrow/advance icon from the application's established
  icon source; do not use a text-heavy button.
- Its accessible name is `Потвърди смяна на ролките`.
- It remains available whenever tracking is active, including before the due
  time and while the order is paused.
- It requires one click and no confirmation dialog.
- Every click advances from the saved expected time by at least one whole
  interval, then skips any additional overdue intervals so the new expected
  time is strictly in the future.
- An accidental click can be corrected through the editor. The pilot does not
  add friction to the 95–98 percent normal path in an attempt to prevent every
  possible mistake.

The countdown controls must not reduce the visual priority or hit area of the
three existing production-lifecycle actions.

## Schedule Editor

The countdown control opens one focused modal/editor containing:

1. previous change/start time;
2. interval hours;
3. interval minutes;
4. calculated and editable next expected change;
5. Save;
6. Restart from now; and
7. Clear tracking.

Editor behavior:

- Opening the editor never changes the schedule.
- The previous/start time defaults to now when tracking is inactive.
- Changing the previous/start time or interval immediately recalculates the
  proposed next expected time.
- Directly editing the proposed next expected time overrides that calculation
  for the saved schedule. A later quick acknowledgement uses the edited next
  expected time as its scheduled anchor.
- Save applies the complete valid schedule atomically in browser storage.
- Restart from now changes only the previous/start date and time to the current
  local time. It preserves the next draft, interval values, current validation
  errors, `aria-invalid` state, and browser storage. It performs no validation
  or recalculation; only Save validates and persists the complete draft.
- Clear tracking removes the current card's optional schedule and returns both
  terminal surfaces to their inactive presentation.
- Clear tracking requires no additional confirmation. Its placement inside the
  editor keeps it out of the frequent path, and the schedule can be configured
  again if it is cleared accidentally.
- Cancel, Escape, or a deliberate backdrop click makes no change. A pointer
  gesture that begins inside any editor field must never dismiss the editor,
  even if it ends over the backdrop.
- Invalid input leaves the editor open, preserves the submitted values, and
  shows a concise Bulgarian validation message beside the relevant field.

The editor uses a native date field plus direct, colon-separated hour and minute
text inputs instead of combined native date-time, dropdown, or numeric-spinner
widgets. The three numbered sections `Начало врътка`, `Интервал`, and
`Очаквана смяна на ролките` share one visual treatment. `Използвай текущия час`
belongs to the start section; `Изключи брояча` remains on the left of a compact
footer while the equal-sized `Отказ` / `Запиши` pair remains on the right.

## Validation Rules

- Interval hours and minutes are whole numbers.
- Hours are from `0` through `23`.
- Minutes are from `0` through `59`.
- The combined interval must be at least one minute.
- Seconds are neither requested nor accepted from operators.
- Previous/start and next expected values must resolve to valid local times.
- The resolved next expected timestamp must be later than the resolved
  previous/start timestamp.
- A next expected time may legitimately already be due; saving it immediately
  produces the correct red or paused `00:00` state.
- Invalid editor input never partially replaces a previously valid schedule.
- Browser-storage data that is malformed, has an unsupported schema version,
  references a different card, or cannot be safely interpreted is ignored and
  removed instead of being guessed.

## Machine Navigation Cards

The machine cards remain the cross-machine attention surface.

### Machine-state dot

Replace the current decorative machine/gear icon with a status dot matching the
established shift-status-dot visual language:

- green: the current card is running;
- yellow: the current card is paused; and
- gray: the machine is free or its current queued card has not started.

The dot must have a programmatic text label for assistive technology. Color is
not the only machine-state signal available to screen-reader users.

### Countdown bubble

- Replace the current top-right status pill with the countdown bubble when
  tracking is active.
- When tracking is inactive, leave this top-right area blank and transparent;
  do not show an empty placeholder or retain the old status pill.
- The countdown bubble follows the normal, yellow-warning, red-urgent, due, and
  paused treatments defined above.
- The machine card itself remains the navigation target. Do not nest a second
  interactive button inside its link.
- Timer updates must not change card geometry, cause text reflow, or move the
  operator's click target.

The machine-state dot and timer bubble answer different questions: whether the
machine is running or paused, and when its winding set needs attention.

## Selected-Card Placement And Task 11 Boundary

Task 11 deliberately installed an inert `Смяна на ролка` placeholder beside
`Пренавиване` in the roll panel. That placeholder proved the earlier visual
hierarchy but contained no behavior.

This Task 10 specification supersedes only that placeholder placement:

- remove the inert roll-panel placeholder when Task 10 is implemented;
- place the real countdown/editor and quick acknowledgement controls in the
  selected-card lifecycle bar beside Start, Pause/Resume, and End;
- keep the existing `Пренавиване` control and all Task 11 behavior unchanged;
  and
- show no countdown controls on an `awaiting_rewinding` card because extrusion
  has ended and the machine is free.

## Browser Persistence And Refresh

The countdown is local workstation state, not SQLite production data.

- Persist it in versioned browser local storage under the application's origin.
- Associate each record with both machine ID and card ID.
- Store absolute schedule timestamps, the interval, and the minimum pause/frozen
  state required to restore the approved presentation.
- Derive the displayed remaining duration from stored timestamps and the
  workstation clock. Do not persist a decremented value every second.
- Rehydrate the schedule after navigation, normal refresh, conflict-required
  refresh, browser restart, or backend-originated page reload.
- A record whose card no longer owns that machine's current order is cleared.
- Same-origin terminal tabs should observe local-storage changes so an
  acknowledgement or edit in one open tab does not leave another tab showing a
  contradictory countdown.

Consequences accepted for this optional pilot feature:

- the countdown is available only in the same browser profile/origin;
- it is not synchronized to another workstation or browser;
- clearing browser storage removes it;
- it is not included in SQLite backups or production reports; and
- it is not authoritative evidence of when a physical roll change occurred.

## Data, Migration, And Conflict Safety

The approved design changes no SQLite schema and no stored production-data
meaning. It adds no server route, card column, roll column, event table, or
migration.

- Re-import cannot affect countdown state.
- Countdown actions do not increment card versions.
- Countdown actions do not participate in optimistic production-data conflict
  checks.
- A required production-card refresh preserves the browser-local countdown.
- Existing dirty-form/navigation protections must continue to work; opening or
  editing the countdown must not silently discard roll, tare, pallet, recipe,
  or other unsaved terminal input.

The final implementation diff must still receive the formal migration
assessment required by `v2-files/AGENTS.md`. The expected decision is no
migration because the state is browser-local, but that decision must be based on
the actual finished diff.

## Accessibility And Interaction Safety

- Machine state and countdown urgency are never communicated by color alone.
- The quick icon button has an accessible Bulgarian name and visible focus
  treatment.
- The countdown/editor control exposes both its action and current state.
- `00:00` has one clear meaning: due and unacknowledged, with paused styling
  overriding red only while the card is paused.
- No blinking, flashing, audio alarm, browser notification, or automatic modal
  opening is included.
- Modal focus enters the first relevant field, remains contained while open,
  and returns to the countdown control after close.
- Controls remain usable at the established terminal viewports and do not rely
  on hover-only explanations.

## Testing And Verification

Implementation must add focused automated and live-browser checks without
mutating the runtime database.

### Calculation and state tests

Cover:

- initial start plus interval calculation;
- acknowledgement clicked on time, early, and late preserves the scheduled
  anchor and advances at least one interval;
- multi-interval overdue acknowledgement catches up to the first future
  scheduled boundary in one action;
- manual next-time override remains editable and becomes the anchor for a
  later quick action;
- midnight/date rollover;
- normal, five-minute warning, one-minute urgent, and due boundaries;
- no negative countdown;
- pause freezing at positive remaining time and at `00:00`;
- yellow pause override of red urgency;
- acknowledgement and editor correction while paused;
- resume with resolved and unresolved paused state;
- automatic clearing on completed, waiting-rewinding, archived, cancelled,
  returned-to-planning, replaced-card, and changed-machine context;
- malformed or stale browser-storage records;
- same-origin storage-event synchronization; and
- accidental early acknowledgement followed by editor correction.

### Render and interaction tests

Prove:

- green, yellow, and gray machine dots map to the correct statuses;
- the old top-right machine status pill is replaced as approved;
- inactive tracking leaves the timer area blank;
- active tracking renders on every machine card where configured;
- an inactive running/paused card shows the setup control without a meaningless
  quick action;
- an active selected-card schedule shows exactly the countdown/editor control
  and one quick icon control;
- the Task 11 roll-panel placeholder is removed without changing
  `Пренавиване` behavior;
- pending, completed, awaiting-rewinding, archived, and cancelled cards cannot
  retain active countdown controls;
- editor validation, Save, Cancel, Escape, Restart from now, and Clear behavior;
- refresh and browser restart preserve a valid current-card schedule; and
- roll entry, correction, dirty-form protection, queue navigation, shift UI,
  and lifecycle controls retain their existing behavior.

### Live Playwright verification

Use a temporary SQLite database and the repository-local Playwright install.
Verify at minimum `1920x768` and `1366x768`:

- four machine cards with a mixture of inactive, normal, warning, urgent, and
  paused timer states;
- machine-dot and timer-bubble readability without clipping or reflow;
- the selected-card lifecycle bar and both countdown controls;
- initial setup, late acknowledgement, manual override, pause, resume, clear,
  finish, and next-order reset;
- normal refresh and conflict-required refresh preservation;
- no horizontal overflow, overlap, clipped controls, console errors, or page
  errors; and
- screenshots under `artifacts/ui-checks/roll-change-countdown/`.

## Out Of Scope

- Database persistence, migration, backup, or restore of countdown state.
- Cross-workstation, cross-browser, server, or mobile synchronization.
- Historical roll-change events, missed-change reports, audit trails, KPIs, or
  shift-manager review.
- Treating acknowledgement time as the physical roll-change timestamp or as a
  replacement schedule anchor.
- Automatic coupling to gross roll entry, tare, pallet, shift, recipe, timing
  segments, print output, or production totals.
- A countdown per roll, lane, spindle, shaft, or pallet.
- Machine PLC, HMI, encoder, speed, length, weight, or diameter integration.
- Audio alarms, desktop notifications, SMS, email, or remote alerts.
- Automatic inference of the interval from previous rolls.
- Remaining-roll-count forecasts or other future production calculations.
- Changing Start, Pause/Resume, End, rewinding, or waiting-return business
  rules beyond the explicitly approved countdown presentation.

## Implementation Handoff

Implementation and verification are complete. Continue from these durable
references:

- [July 28 scheduled-cadence correction plan](../docs/superpowers/plans/2026-07-28-scheduled-countdown-and-machine-dot.md)
- [Original Task 10 implementation plan (historical; its click-time cadence is superseded)](../docs/superpowers/plans/2026-07-27-roll-change-countdown.md)
- [Roll-change countdown implementation note](../docs/implementation-notes/roll-change-countdown.md)
- [V2 plan status and final evidence](PLAN.md)

Deployment remains separate work and must retain the repository's existing
M001 production-profile and final release-candidate gates. Browser-local
countdowns are not restored from SQLite backups.
