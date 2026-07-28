# Scheduled Countdown Catch-Up And Solid Machine Dot Design

Date: 2026-07-28

## Scope

Make two bounded Terminal corrections:

1. Quick roll-change acknowledgement preserves the scheduled cadence and
   catches up to the first future scheduled interval.
2. Machine status dots become solid borderless circles that fill the current
   visible ring footprint.

Task 15 and every backend, database, timing, roll, pallet, rewinding, shift,
print, import, and backup behavior remain out of scope.

## Countdown Behaviour

The saved `nextExpectedAtMs` is the scheduled occurrence being acknowledged.
The acknowledgement click time is used only to decide how many whole scheduled
intervals must be advanced; it never becomes the schedule anchor.

One acknowledgement always advances at least once:

1. Treat the saved `nextExpectedAtMs` as the first occurrence being
   acknowledged.
2. Determine how many whole intervals are needed, with a minimum of one, for
   the resulting next occurrence to be strictly later than the acknowledgement
   time.
3. Set `previousChangeAtMs` to the immediately preceding scheduled occurrence
   and save that first future occurrence as `nextExpectedAtMs`.

The implementation calculates the required interval count directly rather
than iterating once per missed interval, so a very old but otherwise valid
browser-local schedule cannot stall the page.

Examples for a two-hour interval:

| Current scheduled time | Acknowledged | New previous time | New next time |
| --- | --- | --- | --- |
| 10:00 | 09:50 | 10:00 | 12:00 |
| 10:00 | 10:00 | 10:00 | 12:00 |
| 10:00 | 10:07 | 10:00 | 12:00 |
| 10:00 | 12:15 | 12:00 | 14:00 |

A manually overridden next expected time is still the next scheduled
occurrence and therefore becomes the starting anchor for later quick
acknowledgement. The rule works identically across midnight.

Running and paused cards keep their existing availability, storage,
cross-tab, lifecycle-lock, and accessibility behaviour. After acknowledgement,
a paused schedule freezes the positive time remaining until the newly selected
future occurrence. The countdown still never advances automatically without an
operator action.

## Machine Status Dot

The current dot has a 14px border box plus a 1px outer gray shadow, producing a
16px visible footprint. Replace it with a solid 16px circle:

- width, height, and flex basis: 16px;
- border: none;
- box shadow: none;
- border radius: 50%;
- retain the existing green, yellow, and gray status colours;
- retain the existing hidden textual machine-state label.

No surrounding machine-card layout, countdown bubble, navigation, or status
meaning changes.

## Implementation Boundaries

Runtime changes are limited to:

- the pure countdown schedule-advance calculation; and
- the `.machine-state-dot` CSS rule.

Tests, the guarded browser verifier, and contradictory Task 10/README release
documentation must be updated to describe and prove the approved behaviour.
Do not introduce a configurable policy, automatic background catch-up, new
storage fields, a schema migration, or unrelated refactoring.

## Verification

Use test-driven development:

- first replace the click-time unit expectations with early, on-time, late,
  multi-interval, manual-override, paused, and midnight scheduled-cadence
  expectations and observe the intended failures;
- minimally change the pure schedule function until those tests pass;
- update browser-verifier assertions to compare against the saved scheduled
  times rather than click-time ranges;
- assert the machine dot is a 16px solid circle with no border or shadow;
- run the focused Node, template, verifier-safety, and migration checks;
- run the complete Python and Node suites; and
- run the guarded live countdown workflow at 1920x768 and 1366x768 against a
  temporary SQLite database, recording screenshots and checking console/page
  errors, clipping, overlap, and horizontal overflow.

## Data And Migration Assessment

No migration is required. The countdown remains browser-local, the CSS change
is presentation-only, and no database field or persisted production meaning is
changed.
