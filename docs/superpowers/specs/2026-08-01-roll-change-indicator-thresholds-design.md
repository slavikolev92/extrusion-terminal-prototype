# Roll-Change Indicator Thresholds Design

Date: 2026-08-01

Status: Approved by the user on 2026-08-01.

## Goal

Increase the advance-warning window for the browser-local roll-change pace
clock without changing its schedule, persistence, acknowledgement, pause,
resume, lifecycle, or layout behavior.

## Approved Running Thresholds

For a resolved schedule on a running card, classify the unrounded internal
remaining duration as follows:

| Remaining duration | Tone | Existing visual treatment |
| --- | --- | --- |
| Greater than `15:00` | `normal` | Neutral countdown |
| Less than or equal to `15:00` and greater than `05:00` | `warning` | Yellow countdown |
| Less than or equal to `05:00` through the due instant and overdue hold | `urgent` | Red countdown |

The boundaries are inclusive at exactly 15 and 5 minutes. The urgent check must
run before the warning check so the overlapping upper bounds classify exactly
`05:00` as red.

The existing display calculation continues to round a positive partial minute
up with `Math.ceil`. Consequently, the visible transition is aligned with the
displayed minute:

- at `15:00.001`, the display is `00:16` and remains normal;
- at exactly `15:00`, the display is `00:15` and becomes yellow;
- at `05:00.001`, the display is `00:06` and remains yellow;
- at exactly `05:00`, the display is `00:05` and becomes red; and
- at and after the due instant, the display is red `00:00`.

## State Precedence

Only the resolved-running warning thresholds change. Preserve the current state
precedence in `countdownView()`:

1. A paused card uses the yellow `paused` tone at every frozen remaining value,
   including `00:00`.
2. A running card with a positive unresolved frozen value after resume uses the
   yellow `resync` tone, regardless of the 15-minute or 5-minute thresholds.
3. A running unresolved due value uses red `urgent` at `00:00`.
4. All other resolved-running values use the new normal, warning, and urgent
   thresholds above.

No state should blink, flash, play audio, open a modal, or advance the schedule
automatically.

## Architecture And Data Flow

Keep the threshold policy in the pure browser-side countdown model
`app/static/js/roll_change_countdown_core.mjs`. Introduce clear internal
millisecond constants for the 15-minute warning threshold and 5-minute urgent
threshold, and use them in `countdownView()`.

Both existing presentation surfaces already consume the returned `tone`:

- `renderMachine()` applies it to each configured machine-navigation countdown;
- `renderSelected()` applies it to the selected-card countdown/editor control.

The existing `normal`, `warning`, `urgent`, `paused`, and `resync` classes and
CSS colors remain unchanged. Do not duplicate threshold calculations in the
DOM controller or CSS, and do not change template markup merely to implement
the timing policy.

The schedule remains a version-1 browser `localStorage` record. No stored field,
timestamp, interval, acknowledgement calculation, storage key, or cleanup rule
changes. The browser continues to recompute presentation from the absolute
saved next-expected time once per second.

## Approaches Considered

### 1. Central pure-model threshold change — selected

Change the two tone thresholds in `countdownView()`, retain existing tone names,
and prove the exact boundaries in pure Node tests plus live UI verification.
This keeps one policy source for both countdown surfaces and minimizes regression
risk.

### 2. Controller- or CSS-specific threshold behavior — rejected

Deriving urgency separately in `renderMachine()`, `renderSelected()`, or CSS
would duplicate time policy and allow the two surfaces to disagree. CSS cannot
reliably calculate the remaining duration.

### 3. Configurable warning settings — rejected

Adding administrator settings or persisted per-machine thresholds would require
new product rules, storage behavior, validation, and operational decisions. The
requested 15-minute and 5-minute values are fixed, so configurability is outside
the bounded change.

## Error And Safety Behavior

The change introduces no new operator input or error path. Existing malformed
or mismatched browser records continue to be rejected and cleared. Existing
lifecycle synchronization, stale-page locks, dirty-form protection, and
acknowledgement safeguards remain untouched.

Because this is presentation policy over browser-local state:

- no backend route changes;
- no SQLite schema or value changes;
- no card-version changes;
- no production-data writes;
- no migration; and
- no runtime-database test mutation.

## Testing And Verification

Use test-driven development.

### Pure state tests

Replace the old 5-minute-warning/1-minute-urgent expectations with exact
millisecond assertions for:

- `15 minutes + 1 millisecond` -> `normal`, displayed `00:16`;
- exactly `15 minutes` -> `warning`, displayed `00:15`;
- `5 minutes + 1 millisecond` -> `warning`, displayed `00:06`;
- exactly `5 minutes` -> `urgent`, displayed `00:05`;
- a positive sub-minute value -> `urgent`, displayed `00:01`; and
- due/overdue -> `urgent`, displayed `00:00`, with `due: true`.

Keep the existing pause, unresolved resume, due, acknowledgement, storage, and
lifecycle tests passing to prove that threshold changes do not alter their
precedence or behavior.

### Render and live-browser checks

The server-rendered template tests should continue proving that the existing
tone classes have the accepted yellow and red styles and that the countdown
hosts remain available only in the accepted card states.

Update the guarded Playwright verifier to seed stable values away from the exact
tick boundaries and assert both countdown surfaces:

- a running machine above 15 minutes is `normal`;
- a running machine between 15 and 5 minutes is `warning`;
- a running machine below 5 minutes is `urgent`;
- a due running machine remains red `00:00`; and
- a paused due machine remains yellow `paused`.

Run the verifier at `1920x768` and `1366x768` against its temporary SQLite
fixture, check for console/page errors and layout regressions, and capture at
least one relevant screenshot under
`artifacts/ui-checks/roll-change-indicator-thresholds/`.

Run JavaScript syntax checks, the complete countdown Node test file, focused
Python render/verifier-safety tests, the complete Python suite, and
`git diff --check` before completion.

## Documentation

Update the current authoritative behavior descriptions:

- `README.md` with the exact display-aligned 15-minute and 5-minute thresholds;
- `docs/implementation-notes/roll-change-countdown.md` with the durable running
  threshold table and unchanged pause/resume precedence; and
- `v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md` by replacing the superseded
  five-minute-warning/one-minute-urgent requirements and test wording.

Historical implementation plans remain historical records; this approved
design and its implementation plan supersede their old threshold values.

## Explicitly Out Of Scope

- Moving, duplicating, or redesigning the quick acknowledgement/reset button.
- Changing any countdown layout, colors, icons, labels, hit areas, or focus
  order.
- Changing schedule creation, editing, acknowledgement cadence, automatic
  catch-up, pause/resume reconciliation, or lifecycle cleanup.
- Adding configurable thresholds or admin controls.
- Adding database, server, reporting, history, backup, PLC/HMI, notification, or
  cross-workstation coupling.
- Unrelated terminal or backend refactoring.

## Completion Criteria

The feature is complete when both existing countdown surfaces use the approved
15-minute yellow and 5-minute red transitions, every unchanged state override
still behaves as documented, focused and full automated checks pass, guarded
Playwright evidence exists at both supported viewports, documentation is
current, the final diff contains no reset-button relocation, and the migration
assessment remains no migration.
