# Roll-Change Countdown

## Purpose And Boundary

The roll-change countdown is an optional pace clock for one machine's complete
synchronized winding set. One schedule covers all lanes that are expected to
change together. It is not a physical roll-change timestamp, an audit event, or
a production record. Operators may weigh, wrap, and enter rolls later without
moving the expected schedule.

A normal acknowledgement advances exactly once from the current expected time:

```text
previous change      = current expected change
next expected change = current expected change + interval
```

A late click therefore does not restart the interval from the click time and
does not skip missed intervals. A directly edited next expected time becomes
the new schedule anchor; the following acknowledgement adds one interval to
that override.

## Ownership And Clearing

There is at most one schedule per machine, and it belongs to both that machine
and its current running or paused card. It is deliberately inactive until an
operator configures it. The next order never inherits it.

The browser clears a schedule when its card is completed, enters
`awaiting_rewinding`, is archived or cancelled, returns to a non-running
planning state, moves out of the machine's current-card position, or is
replaced by a different current card. An unsupported, malformed, or wrong-card
record is also removed instead of guessed.

## Pause And Resume States

| Card state | Schedule resolution | Display behavior |
| --- | --- | --- |
| Running | Resolved | Counts from the absolute next expected time; normal, yellow warning, red urgent, then red `00:00`. |
| Paused | Unresolved | Freezes the remaining duration immediately and stays yellow, including paused `00:00`. |
| Paused | Resolved by acknowledgement or editor Save | Shows the resolved frozen duration in yellow while paused. |
| Running after pause | Still unresolved, positive | Holds the frozen value with yellow resynchronization styling until acknowledgement or editor Save. |
| Running after pause | Still unresolved, due | Holds red resumed-unresolved `00:00`; the paused yellow override no longer applies. |
| Running after pause | Resolved during pause | Returns to normal timestamp-derived counting and warning thresholds. |

The quick acknowledgement remains available while paused. It advances exactly
one scheduled interval and resolves the pause. Saving a corrected schedule in
the editor also resolves it.

## Browser Storage Contract

Each machine uses this exact key, with the numeric machine ID appended:

```text
extrusion-terminal.roll-change.v1.machine.<machineId>
```

The version-1 JSON record has these exact fields:

```json
{
  "schemaVersion": 1,
  "machineId": 1,
  "cardId": 123,
  "previousChangeAtMs": 1785146400000,
  "intervalMinutes": 120,
  "nextExpectedAtMs": 1785153600000,
  "observedStatus": "running",
  "frozenRemainingMs": null,
  "pauseNeedsResolution": false
}
```

Timestamps and frozen duration are integer milliseconds; the interval is an
integer from 1 through 1439 minutes. `observedStatus` is `running` or `paused`.

The record exists only in `localStorage` for the current browser profile and
application origin. Normal navigation, refresh, conflict-required refresh,
backend-originated reload, and browser restart rehydrate a valid schedule.
Same-origin tabs synchronize through browser `storage` events. Other browsers,
profiles, origins, and workstations do not receive the state. Clearing or
losing browser storage removes the schedule, and SQLite backup/restore cannot
recover it.

The countdown has no SQLite backup, report, card-version, re-import, shift,
roll, tare, pallet, recipe, print, production-total, or timing-segment coupling.
It creates no route, column, event history, or optimistic-conflict write.
Automatic PLC/HMI/machine integration and historical roll-change reporting
remain outside the pilot boundary.

## Operator Recovery

- After a mistaken quick acknowledgement, open the editor and correct the
  previous/start time, interval, or next expected time.
- To stop tracking deliberately, open the editor and use `Изчисти` (Clear).
- After browser-storage loss, recreate the schedule from the known operational
  start/change time and interval. It cannot be restored from an SQLite backup.

## Verification

Use the repository-local Python virtual environment, Node installation, and
Playwright 1.61.0. Automated verification:

```bash
source .venv/bin/activate
python -m compileall app tests scripts
node --check app/static/js/roll_change_countdown_core.mjs
node --check app/static/js/roll_change_countdown.mjs
node --check scripts/verify_roll_change_countdown_ui.mjs
node --test tests/js/roll_change_countdown_core.test.mjs
python -m pytest tests/test_roll_change_countdown_ui_script_safety.py tests/test_terminal_v8_render.py tests/test_rewinding_ui_script_safety.py -q
python -m pytest -q
git diff --check
./node_modules/.bin/playwright --version
```

Recreate the guarded fixture and start the temporary app:

```bash
source .venv/bin/activate
python scripts/create_roll_change_countdown_fixture.py \
  --db-path .test-runtime/roll-change-countdown/fixture.sqlite3 \
  --output .test-runtime/roll-change-countdown/fixture.json
EXTRUSION_DB_PATH=.test-runtime/roll-change-countdown/fixture.sqlite3 \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8012
```

In a second terminal, run the guarded browser workflow:

```bash
BASE_URL=http://127.0.0.1:8012 \
FIXTURE_JSON=.test-runtime/roll-change-countdown/fixture.json \
ARTIFACT_DIR=artifacts/ui-checks/roll-change-countdown \
node scripts/verify_roll_change_countdown_ui.mjs
```

The verifier exercises both `1920x768` and `1366x768`. Screenshots and the JSON
summary are written under `artifacts/ui-checks/roll-change-countdown/`; those
artifacts and the `.test-runtime` fixture remain untracked.
