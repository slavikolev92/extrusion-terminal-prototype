# Task 15: State-Based Lifecycle Buttons And Split Terminal Action Header

Status: design discussion concluded and preserved on July 27, 2026.
Implementation has not started. This task is a bounded workstation presentation
change and does not authorize unrelated terminal redesign or backend workflow
changes.

## Purpose

Make the selected-card production actions reflect only what the operator can do
in the card's current state, and make the header visually align with the two
content panes beneath it.

The current terminal keeps three lifecycle positions visible for active cards.
After an order starts, this leaves a disabled `Старт` button on screen even
though that action can never become valid for that production run again. Before
an order starts, it similarly shows a disabled `Пауза` control that has no
meaning yet. The lifecycle controls and roll-change countdown controls are also
packed into one right-aligned group even though the page below is divided into
separate Details and Rolls panes.

This task removes those obsolete controls, preserves a stable two-button
lifecycle area, and splits the header into two pane-aligned action zones.

## Confirmed Interaction Model

The first lifecycle position is one state-dependent control:

```text
pending -> Старт
running -> Пауза
paused  -> Продължи
```

It occupies the same physical slot while its label, icon, action, and visual
priority change with the current card state. It is not three controls kept in
the DOM for positional consistency.

`Приключи` remains in the second lifecycle position. Its enabled state and
visual priority change with the card state, but it does not move to another
header zone.

### Pending card

- Render `Старт` as the primary dark action.
- Render `Приключи` in its fixed second position as disabled and gray.
- Do not render `Пауза` or `Продължи`.
- Existing active-shift gating, optimistic version checks, and start-route
  validation remain unchanged.

### Running card

- Do not render `Старт`; once timing starts, Start is never an available action
  for that production run again.
- Render `Пауза` in the first lifecycle position as an enabled white secondary
  action.
- Render `Приключи` in the second position as the primary dark action.
- Existing pause and finish routes, validation, confirmation, timing closure,
  shift attribution, and rewinding behavior remain unchanged.

### Paused card

- Do not render `Старт`.
- Replace `Пауза` with `Продължи` in the first lifecycle position.
- Render `Продължи` as the primary dark action because resuming is the expected
  next step from a temporary pause.
- Keep `Приключи` enabled in the second position, but render it as a white
  secondary action. Finishing from pause remains valid and retains the existing
  confirmation and backend rules.
- After a successful resume, the first control returns to secondary `Пауза` and
  `Приключи` returns to the primary treatment.

### Other card states

- `awaiting_rewinding` keeps its existing deliberate single primary
  `Приключи` finalization action. It does not gain Start, Pause, Continue, or
  roll-change countdown controls.
- Completed, archived, and cancelled cards retain their existing action
  exclusions. This task must not make a completed card restartable.
- Empty-machine and no-selected-card presentations retain their current
  behavior unless a minimal spacing adjustment is required by the shared
  header grid.

## Confirmed Visual Hierarchy And Colors

Use the application's existing action treatments:

- dark navy primary: the expected main action in the current state;
- white with the existing border and navy text: enabled secondary action; and
- gray disabled treatment: unavailable action.

A white secondary button is still active and clickable. It must retain the
existing hover, pressed, keyboard-focus, and hit-area behavior and must not look
like the gray disabled End button shown before production starts.

Do not introduce green Start/Continue buttons or a red End button:

- green remains available for running/success status communication;
- red remains available for errors, destructive cancellation, urgent countdown
  states, or genuine emergency meaning; and
- `Приключи` is the normal successful completion path, not a destructive stop or
  emergency-stop control.

At every pending, running, or paused state, exactly one enabled action should
have the primary treatment.

## Confirmed Split-Header Layout

Keep the existing single selected-card header row and its bottom divider. Do not
create inset cards, stacked toolbars, or extra panel-heading rows.

The header should share the exact horizontal column geometry used by the
workspace beneath it:

```text
left column:  Details pane
right column: Rolls pane
```

The two header zones are:

1. **Details-aligned zone**
   - Keep `Машина N: №ORDER` aligned to the left.
   - Place the existing roll-change countdown/editor group at the right edge of
     this same zone.
   - Preserve the current setup/countdown control and quick acknowledgement as
     one local group.

2. **Rolls-aligned zone**
   - Place the state-dependent lifecycle pair at the right edge of this zone.
   - Preserve equal lifecycle button dimensions and the stable first/second
     positions described above.

The header and workspace must derive their columns and gap from the same CSS
values rather than copying unrelated offsets. The current wide layout uses a
flexible Details column plus a `510px` Rolls column with a `28px` gap. At the
existing `max-width: 1360px` breakpoint, the Rolls column becomes `460px` and
the gap becomes `20px`. If these literal values remain, both header and
workspace must change through one shared rule or custom-property source so
future edits cannot make the header drift away from the panes.

The lifecycle pair fits comfortably in the right column once obsolete disabled
Start/Pause controls are no longer rendered. Do not solve alignment with
absolute positioning, blank placeholder buttons, arbitrary margins, or a
full-width spacer.

## Roll-Change Countdown Boundary

Task 10's roll-change countdown behavior is unchanged. This task only moves its
selected-card host within the header.

- Preserve `data-roll-change-controls`, machine ID, card ID, and card-status
  attributes.
- Preserve `data-roll-change-open`, `data-roll-change-control-value`, and
  `data-roll-change-advance` hooks.
- Preserve the editor modal, quick acknowledgement, browser-local schedule,
  pause/resume handling, same-origin synchronization, cleanup rules, accessible
  name, and focus behavior.
- Running and paused cards continue to show the countdown controls; pending and
  inactive lifecycle states do not.
- Do not move the countdown back into the Rolls panel or beside the
  `Пренавиване` marker.
- Moving the host must not cause the countdown to modify card versions or any
  SQLite data.

## Error, Refresh, And Accessibility Behavior

- Timing and finish errors must continue to render in the existing top-bar
  feedback area.
- Conflict-required refresh alerts must remain full-width beneath the header,
  not confined to either header column.
- The DOM and keyboard order should remain logical: the Details-zone
  roll-change controls precede the Rolls-zone lifecycle actions if the visual
  column order is used in markup. Verification must confirm the actual focus
  order is usable and visible.
- Decorative icons remain hidden from assistive technology; button text and the
  countdown quick action's Bulgarian accessible name remain the operative
  labels.
- Color must not be the only distinction between enabled and disabled controls;
  retain semantic `disabled` attributes where an action is unavailable.
- Controls must keep the established minimum hit area and visible focus outline.

## Expected Implementation Surface

The current exploration found a presentation-only implementation surface:

- `app/templates/terminal.html`
  - state-specific Jinja rendering for lifecycle controls;
  - top-bar markup split into two aligned zones; and
  - the template's existing inline terminal CSS and responsive breakpoint.
- `tests/test_terminal_v8_render.py`
  - exact state rendering, classes, enabled/disabled behavior, action paths,
    absence of obsolete controls, and shared-layout expectations.
- `scripts/verify_roll_change_countdown_ui.mjs`
  - state-appropriate lifecycle control count and geometry;
  - header-to-pane alignment; and
  - countdown/lifecycle separation without overlap or overflow.
- `tests/test_roll_change_countdown_ui_script_safety.py` only if verifier-source
  assertions need to change with the geometry checks.

No change is expected in `app/main.py`, `app/db.py`, `app/schema.py`,
`app/migrations.py`, countdown schedule calculations, or countdown storage
code. If implementation discovers a need to change any of those areas, stop and
reassess the task rather than silently expanding this UI slice.

The current worktree already contains substantial uncommitted Task 10 countdown
changes in the template, verifier, tests, and countdown scripts. Task 15 must be
implemented against the settled current version of that work and must preserve
those changes rather than replacing or reverting them.

## Automated Test Expectations

Render tests must prove at least:

1. Pending renders one Start form, no Pause/Continue form, and one semantically
   disabled End control.
2. Running renders one Pause form and one enabled End form, with no Start or
   Continue control.
3. Paused renders one Continue form and one enabled End form, with no Start or
   Pause control.
4. Running gives End the primary class and Pause the secondary class.
5. Paused gives Continue the primary class and End the secondary class.
6. Pending gives Start the primary class and End the disabled treatment.
7. Waiting retains only its existing enabled finalization action.
8. Completed/archived/cancelled cards do not gain lifecycle controls.
9. Lifecycle forms retain `loaded_version` and their current endpoints.
10. The countdown host remains present only for running and paused cards and
    retains every required data attribute.
11. The header and workspace share the same wide and compact column/gap rules.
12. Top-bar feedback and refresh-alert placement remain intact.

The browser verifier must replace its current assumption of exactly three
lifecycle slots with the correct state-specific pair. At both supported
workstation viewports, it must verify:

- Details-zone countdown controls align within the Details column;
- lifecycle controls align within the Rolls column;
- neither group overlaps the title, the other group, or a pane boundary;
- equal lifecycle button sizes and established hit areas are retained;
- active secondary buttons are visibly distinct from disabled gray controls;
- pending, running, and paused states render the approved labels and hierarchy;
- countdown setup, editor, quick acknowledgement, pause, resume, and finish
  still work after the host move;
- there is no horizontal overflow, clipping, console error, or page error; and
- screenshots are saved below `artifacts/ui-checks/` using only a temporary
  SQLite fixture.

Focused verification should include:

```bash
source .venv/bin/activate
python -m pytest \
  tests/test_terminal_v8_render.py \
  tests/test_roll_change_countdown_ui_script_safety.py \
  tests/test_rewinding_ui_script_safety.py \
  -q
node --check scripts/verify_roll_change_countdown_ui.mjs
git diff --check
```

Run the repository's guarded Task 10 Playwright fixture/verifier at
`1920x768` and `1366x768`, saving new Task 15 evidence under a dedicated
`artifacts/ui-checks/terminal-action-header/` directory. Tests and browser
verification must not open or mutate
`data/extrusion_terminal.sqlite3`.

## Data And Migration Assessment

The expected migration decision is **No migration** because this task changes
HTML structure, CSS layout, conditional rendering, verifier geometry, tests,
and documentation only. It neither adds persistent fields nor changes the
meaning of existing stored values.

Implementation must still inspect its final diff and complete the formal
migration assessment required by `v2-files/AGENTS.md`. If the final diff remains
within the expected presentation surface, no production snapshot or data
transformation is needed for Task 15.

## Explicitly Out Of Scope

- changing Start, Pause, Resume, End, waiting, rewinding, or shift business
  rules;
- adding a Stop, Cancel, emergency-stop, restart, or reopen action;
- changing timing segments, `finished_at`, final-shift attribution, roll-entry
  validation, tare/net calculations, or finish eligibility;
- green Start/Continue actions or a red normal End action;
- redesigning the machine navigation, Details content, recipe table, Rolls
  ledger, totals, countdown editor, or rewinding marker;
- new JavaScript state management for server-rendered lifecycle buttons;
- database schema, migration, persisted-value, backup, print, admin, importer,
  or public-route changes; and
- unrelated cleanup or refactoring of the large terminal template.

## Completion Criteria

Task 15 is complete when:

- each card state renders only its meaningful lifecycle actions;
- the first lifecycle control morphs Start -> Pause -> Continue as approved;
- exactly one enabled action is primary in pending, running, and paused states;
- End remains enabled but secondary while paused;
- the roll-change and lifecycle groups align with their respective Details and
  Rolls panes at both supported viewports;
- Task 10 countdown behavior and every existing backend lifecycle invariant are
  preserved;
- focused automated checks and guarded live-browser verification pass against a
  temporary database;
- at least one relevant screenshot is recorded under the Task 15 artifact
  directory;
- the final diff receives review for data integrity, validation messages,
  workstation behavior, and scope; and
- the migration assessment confirms the actual completed diff before any
  deployment decision.
