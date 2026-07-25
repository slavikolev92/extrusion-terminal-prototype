# Task 01: Shift Management Functionality Specification

Status: functionality approved on July 25, 2026.

## Purpose

Record which numbered extrusion shift produced each roll and provide a simple
terminal handoff workflow without stopping or changing production orders,
machines, or production timers.

This is a functionality specification. It does not define database structure,
migrations, code structure, or implementation slices. Those decisions require a
fresh exploration of the app and database after the prerequisite blocker work
is complete.

## Scope

- There is one active extrusion shift at a time across all four machines.
- Different machines cannot have separate active shifts.
- The terminal should not allow normal production roll entry unless a shift is
  open.

### Shift-count configuration

- The exact number of shifts used by the business is not currently known.
- The first version should default to four available numbered shifts.
- A separate terminal-configuration page in the admin panel should contain a
  simple input for changing the number of available shifts.
- The configured shift count should accept only a positive whole number.
- Workers should not be able to change the configured shift count from the
  terminal.
- If the configured count is `N`, the shift-opening control should offer the
  numbered choices `1` through `N` in a dropdown instead of permanently showing
  four choices or accepting free-form input.
- When starting the next shift, the terminal should suggest the next number in
  a repeating sequence from `1` through `N` and then back to `1`.
- The suggested number is not mandatory. The operator may select a different
  configured shift number when the real handoff does not follow the sequence.
- The start prompt should require only selection or confirmation of a configured
  shift number from the dropdown.
- For now, shift numbers are simple configurable business labels. Do not assume
  they represent fixed time windows.
- Changing the configured count affects future shift choices only. It must not
  alter previously recorded shifts or production history.
- If an open shift's number is removed from the available choices by a count
  reduction, that shift remains open until it is closed normally. Its number is
  unavailable for future shift starts after it closes.

### Shift identity

- Shift tracking starts with simple shift-level information:
  - shift number
  - start timestamp
  - end timestamp
- The app does not need to record named workers or import crew rosters.
- Excel remains the place where the business can identify which people worked a
  numbered shift on a particular day and during a particular time period.
- The app only needs to report which numbered shift, on which date and at which
  times, produced the work.
- Production recorded while a shift is open should ultimately be associated
  with that shift's final selected number when the shift is ended.

### Durable relationship to roll production

- Every shift occurrence must have its own permanent, unique internal identity.
  The internal identity is different from the reusable business shift number.
  For example, two occurrences may both be called `Shift 1`, but they must have
  different internal identities because they happened at different times.
- The internal identity does not need to be visible to terminal operators or
  form a gap-free sequence. Its purpose is to identify exactly one shift
  occurrence.
- Every new roll recorded after shift management is introduced must be linked
  to the one active shift occurrence at the moment the roll is created.
- A roll should link to the unique shift occurrence rather than merely storing
  a copied shift number or relying on timestamps to infer its shift later.
- Correcting the selected number of an open shift must not change its unique
  identity or require rewriting its rolls. All rolls remain linked to the same
  occurrence and therefore report the occurrence's final selected shift number.
- End-of-shift and historical production summaries should be based on the rolls
  linked to the selected shift occurrence.
- Historical shift summaries must use the latest saved values of the rolls
  currently linked to that shift. A later roll correction or valid roll
  deletion must be reflected when the shift summary is opened again.
- The pilot should not preserve a separate frozen copy of the item rows, roll
  totals, or gross-kilogram totals that were shown when the shift originally
  ended.
- Future worker or crew information can be associated with the same shift
  occurrence without changing existing roll history.
- This section defines the required data relationship, not the final table,
  column, key, or migration design. Those technical choices remain part of the
  post-blocker application and database exploration.

### Starting and operating a shift

- Shift opening, changing, and closing should be operated from the terminal
  only in the pilot.
- The normal terminal screen should contain one global button labelled
  `Shift`, positioned with the other global terminal actions such as the queue
  and produced orders.
- The main terminal screen does not need to display the active shift number or
  its start time. Those details should be available after opening the `Shift`
  window.
- Starting a shift should automatically record the current time. Operators
  should not type or edit the start timestamp.
- Before recording the start time, the terminal should require an explicit
  confirmation that shows the selected shift number, such as
  `Start Shift 2 now?`.
- Ending a shift should automatically record the current time. Operators should
  not type or edit the end timestamp.
- The normal start/stop workflow should be deliberately simple and should
  prevent avoidable mistakes through constrained choices and clear actions.

### Shift window

- When a shift is open, selecting the global `Shift` button should open one
  shift window containing:
  - the current shift number
  - the automatically recorded start time
  - a clearly separated `End shift` action
  - a brief, read-only list of all completed shifts
- The displayed current shift number should itself be the constrained dropdown
  for changing the active shift number. Do not show a separate shift-number
  display and a second correction dropdown.
- Selecting another configured number in that dropdown should update the open
  shift's current number. The correction should not create a separate shift or
  change the original start time.
- The `End shift` action may be positioned at the top or bottom of the window,
  but it must remain visually distinct from changing the shift number and from
  opening history.
- Completed shifts should appear newest first in a compact, scrollable history
  table. The pilot does not need history search or filters.
- The history table should show:
  - shift number
  - start date and time
  - end date and time
  - number of distinct items produced during the shift
  - total number of rolls produced during the shift
  - total gross kilograms produced during the shift
  - a `View` action
- The aggregate item, roll, and gross-kilogram values in the history table must
  include only production attributed to that completed shift.
- Selecting `View` should replace the shift window's contents with the selected
  shift's read-only production summary in the same format used immediately
  after ending a shift. Do not stack a second modal window on top of the first.
- The historical summary should provide a `Back` action that returns to the
  completed-shift history without changing the active shift.

### Correcting the active shift number

- While a shift is active, the terminal should always allow the operator to
  change its currently selected shift number to another configured value. This
  is a correction of the open shift's label, not a shift handoff.
- Changing the selected number should not end the shift, show a summary, start a
  new shift, or affect machines, orders, production timers, or other terminal
  behavior.
- Changing the selected number should not change the original automatically
  recorded start time. It changes only the temporary shift-number selection.
- The final selected shift number should be saved as the identity of that shift
  when the operator ends it.
- Every completed shift is a distinct occurrence, even when the same shift
  number is used again on another day.
- Example: if the shift starts at 22:00 with `Shift 2` selected, the operator
  changes the selection to `Shift 3` at 23:00, and the shift ends at 08:00, the
  completed record is `Shift 3` from 22:00 to 08:00.

### Recovery

- Reloading the terminal page or restarting the server must restore the same
  open shift with its original start time and latest selected shift number.

### No-open-shift gate and shift ending

- When no shift is open, the terminal should be dimmed behind a blocking
  `No active shift` window. The operator must not be able to use the normal
  terminal controls or dismiss the gate without starting a shift.
- Ending a shift should follow this terminal handoff flow:
  1. The operator clicks `End shift`.
  2. The terminal asks for confirmation.
  3. On confirmation, the current time is recorded as the shift end.
  4. The shift window is replaced by that shift's production summary while the
     rest of the terminal remains dimmed and unavailable.
  5. The summary remains visible until the operator acknowledges or closes it.
  6. The terminal then immediately shows the blocking `No active shift` window
     with the controls for starting the next shift.
  7. The next shift's start time is recorded only when its operator confirms the
     start action.
- The just-completed summary should remain available later through the completed
  shift history in the normal `Shift` window.

### End-of-shift summary

- The end-of-shift summary should show the number of distinct items produced by
  the shift.
- One distinct item means one production order with at least one roll recorded
  during the shift. The order does not need to have been completed during that
  shift.
- The summary table should contain one row per distinct item/production order
  and show:
  - production order ID
  - customer name
  - product type
  - number of rolls produced for that order during the shift
  - gross kilograms produced for that order during the shift
- A shift with no recorded rolls may still be ended normally. Its summary shows
  zero distinct items and an empty order table.
- The pilot requires this summary as an on-screen view. A separate downloadable
  or printable shift report is not part of the confirmed functionality.

### Separation from production execution

- Ending or changing the active shift must not pause, stop, finish, or otherwise
  change any running machine, production order, or production timer.
- Machines and orders continue across the shift handoff. Starting the next shift
  changes attribution for later production. Correcting the selected number of a
  still-open shift applies its final selected number to all production recorded
  during that open shift.

### Access and exclusions

- The pilot does not need shift cancellation or a separate shift-number
  correction workflow.
- Operator editing of recorded start and end times is not part of the pilot. If
  time correction is later proven necessary, a shift-manager correction feature
  can be designed separately.
- The pilot does not need an admin page for operating shifts, manager approval,
  admin shift review, or admin correction of shift records. The separate admin
  terminal-configuration page is only for settings such as the available shift
  count.
- Operators may manage shifts as needed for their work; the feature does not
  require role-based control or a prescribed manager workflow.
- Shift management and package/pallet tracking are separate concepts:
  - a shift produces rolls
  - a pallet/package groups rolls for transport and label printing

## Deferred technical work

After the prerequisite blocker work is complete:

1. Explore the resulting app and database.
2. Confirm how this approved behavior fits the current workflow and persisted
   data.
3. Decide the implementation slices and write the implementation plan.
4. Design and test the required migration as part of implementation.

Do not infer historical shift assignments for existing rolls during this design
stage.
