# Task 01: Shift Management Functionality Specification

Status: complete in local code and visually accepted on July 26, 2026. The
final adversarial review findings were corrected and the complete automated and
temporary-database browser gates pass. Production deployment remains separately
gated by the M001 legacy-data profile and final release-candidate rehearsal.

## Purpose

Record which numbered extrusion shift produced each roll and provide a simple
terminal handoff workflow without stopping or changing production orders,
machines, or production timers.

This is a functionality specification. It does not define database structure,
migrations, code structure, or implementation slices. Those decisions belong
in the implementation plan based on the completed post-blocker app/database
exploration.

## Approved visual references

- `source-files/new-design.JPG` is the structural reference for the new terminal
  header only. Its unrelated machine-card and selected-order changes are not
  part of Task 01.
- `source-files/screen_start_shift.png` is the visual reference for the compact
  start-selection state, subject to this specification's blocking behavior,
  Bulgarian copy, existing terminal accent color, and live clock rules.
- `source-files/screen_start_shift_confirmation.png` is the visual reference for
  both start and end confirmation states. Their content and action meaning
  differ, but they should share the same layout and visual language.
- `source-files/main_shift_button.png` is the visual reference for the default
  active-shift and history-preview window, subject to the editable-number,
  no-duration, Bulgarian date, one-decimal weight, and full-history rules below.
- These references define direction, proportions, hierarchy, and polish. Where
  a reference conflicts with an explicit behavior in this specification, the
  explicit behavior controls.

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
- The configured shift count should accept only a positive whole number from
  `1` through `99`. This technical ceiling prevents an unusably large terminal
  dropdown and unsafe integer input.
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
  For example, two occurrences may both be called `Смяна 1`, but they must have
  different internal identities because they happened at different times.
- The internal identity does not need to be visible to terminal operators or
  form a gap-free sequence. Its purpose is to identify exactly one shift
  occurrence.
- Every roll entered through the normal production workflow while a card is
  active must be linked to the one active shift occurrence at the moment the
  roll is created.
- A roll should link to the unique shift occurrence rather than merely storing
  a copied shift number or relying on timestamps to infer its shift later.
- When a brand-new roll is added later to a completed or archived production
  order, it should automatically inherit the chronologically latest shift
  occurrence already linked to another roll on that same order. The operator
  should not be asked to choose a historical shift.
- If an older production order has no roll with a known shift occurrence, then
  there is no reliable last shift to inherit. That late-added roll should remain
  without shift attribution rather than receiving a guessed historical or
  currently active shift.
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
- The terminal should have a dedicated full-width header above the machine
  cards. Adding this header must not otherwise redesign the machine cards,
  selected-order screen, or production controls.
- The company logo should be aligned on the left side of the header.
- Two equal-size global navigation buttons should be centered against the full
  viewport, not merely centered in the space remaining between the logo and
  the right-side action. They should be labelled `Чакащи поръчки` and
  `Произведени поръчки`.
- The shift-management button should be aligned on the right and use the same
  width and height as the two centered buttons. All three labels must remain
  inside their buttons without wrapping, clipping, overlapping, or changing
  the header alignment.
- When no shift is open, the shift button should show the same gray status dot
  used for an inactive machine plus the full label `Няма активна смяна`.
- When a shift is open, the dot should be green and the button should show the
  current label, such as `Смяна 1`. Correcting the active shift number should
  update this label.
- The right-side control is always a shift-management button, not an `exit
  shift` button. Selecting it while a shift is active opens the shift window;
  ending the shift remains a separate action inside that window.
- The main terminal header does not need to show the shift start time. The
  start time is available inside the shift window.
- Starting a shift should automatically record the current time. Operators
  should not type or edit the start timestamp.
- Before the shift is saved, the start-selection and start-confirmation screens
  should display a live current-time preview in the approved Bulgarian date
  format. The authoritative server timestamp is recorded only when the operator
  selects the final confirmation action.
- Before recording the start time, the terminal should require an explicit
  confirmation that shows the selected shift number, such as
  `Да започне ли Смяна 2?`.
- Ending a shift should automatically record the current time. Operators should
  not type or edit the end timestamp.
- The normal start/stop workflow should be deliberately simple and should
  prevent avoidable mistakes through constrained choices and clear actions.

### Shift window

- When a shift is open, selecting the state-aware shift button should open one
  shift-management window titled `Управление на смяната`.
- The default window should contain two visually distinct sections:
  - `Текуща смяна`, with the current shift number, automatically recorded start
    time, and a clearly separated `Приключи смяната` action; it does not need a
    separate active-status badge
  - `История`, with a compact preview of up to the five most recently completed
    shifts and a `Виж всички` action
- The current-shift section must not show a duration or live elapsed-time
  counter.
- The displayed current shift number should itself be the constrained dropdown
  for changing the active shift number. Do not show a separate shift-number
  display and a second correction dropdown.
- Selecting another configured number in that dropdown should update the open
  shift's current number. The correction should not create a separate shift or
  change the original start time.
- The `Приключи смяната` action may be positioned at the top or bottom of the
  current-shift section, but it must remain visually distinct from changing the
  shift number and from opening history.
- The compact history preview and the full history view should show completed
  shifts newest first. `Виж всички` should replace the contents of the same
  modal with a compact, scrollable full-history table; it must not stack a
  second modal. The pilot does not need history search or filters.
- The full history table should show:
  - shift number
  - start date and time
  - end date and time
  - number of distinct items produced during the shift
  - total number of rolls produced during the shift
  - total gross kilograms produced during the shift
  - a `Преглед` action
- The aggregate item, roll, and gross-kilogram values in the history table must
  include only production attributed to that completed shift.
- Selecting `Преглед` should replace the shift window's contents with the
  selected shift's read-only production summary in the same format used
  immediately after ending a shift. Do not stack a second modal window on top
  of the first.
- The historical summary should provide a `Назад` action that returns to the
  completed-shift history without changing the active shift.
- All visible labels, headings, table columns, links, and confirmation actions
  in the shift interface should be in Bulgarian.
- Visible shift timestamps should use a human-readable Bulgarian format such as
  `26 юли 2026, 21:30`. They should not expose raw database timestamps or
  seconds.
- After a dismissible History or historical-summary pane is closed, selecting
  the header shift action again should open the default current-shift overview.
- Gross-kilogram values in shift history and summary views should be displayed
  with one decimal place.
- Dialog widths should match their content: start and confirmation states
  should be compact, while history and production-summary states may be wider
  for their tables. The dialogs should use the terminal's existing accent
  colors, typography, borders, and spacing rather than a separate visual theme.

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
- Example: if the shift starts at 22:00 with `Смяна 2` selected, the operator
  changes the selection to `Смяна 3` at 23:00, and the shift ends at 08:00, the
  completed record is `Смяна 3` from 22:00 to 08:00.

### Recovery

- Reloading the terminal page or restarting the server must restore the same
  open shift with its original start time and latest selected shift number.

### No-open-shift gate and shift ending

- When no shift is open, the terminal should be dimmed behind a blocking
  `Няма активна смяна` window. The operator must not be able to use the normal
  terminal controls or dismiss the gate without starting a shift.
- The no-active-shift view should use the approved compact start layout with a
  shift-number dropdown, live current-time preview, and `Започни смяна`
  action. It should not contain a close control or an `Отказ` action.
- Start and end confirmation states should share the same visual structure:
  clear Bulgarian heading and explanation, compact shift details, `Назад`, and
  a final confirmation action. Returning from start confirmation goes back to
  the number-selection state; it does not dismiss the blocking gate.
- Ending a shift should follow this terminal handoff flow:
  1. The operator clicks `Приключи смяната`.
  2. The terminal asks for confirmation.
  3. On confirmation, the current time is recorded as the shift end.
  4. The shift window is replaced by that shift's production summary while the
     rest of the terminal remains dimmed and unavailable.
  5. The summary remains visible until the operator selects `Продължи`.
  6. The terminal then immediately shows the blocking `Няма активна смяна`
     window
     with the controls for starting the next shift.
  7. The next shift's start time is recorded only when its operator confirms the
     start action.
- The just-completed summary should remain available later through the completed
  shift history in the normal shift-management window.

### End-of-shift summary

- The summary window should use the static Bulgarian title `Произведени
  количества`, not a shift-number title.
- Beneath the title, show the shift number and its human-readable start and end
  timestamps once. Do not repeat the shift number in multiple headings.
- The order rows themselves should show which distinct items were produced by
  the shift. The summary should not show a separate distinct-item counter such
  as `1 артикула`.
- One distinct item means one production order with at least one roll recorded
  during the shift. The order does not need to have been completed during that
  shift.
- The summary table should contain one row per distinct item/production order
  and use these Bulgarian columns:
  - `Производствена поръчка`
  - `Клиент`
  - `Вид изделие`
  - `Брой ролки`
  - `Бруто, кг`
- A shift with no recorded rolls may still be ended normally. Its summary shows
  an empty order table and a Bulgarian empty-state message.
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

## Completion and deployment

The shift backend, M002 schema foundation, attribution behavior, approved
terminal header, complete shift interface, review fixes, and browser workflow
are implemented. M002 leaves historical rolls unattributed and now rejects a
malformed partial schema that contains the attribution column without its
required foreign key. Terminal production writes recheck the active shift
inside their write transaction.

Local Task 01 work is complete. Deployment still requires:

1. Profile an immutable SQLite-safe production backup to resolve the older M001
   legacy import-field deployment gate without guessing values.
2. Rehearse the final release candidate and complete migration chain on a fresh
   clone of a SQLite-safe production backup.
3. Deploy the application and M002 together only after those gates, backup,
   integrity, foreign-key, application smoke, repeat-run, and rollback checks
   pass.
