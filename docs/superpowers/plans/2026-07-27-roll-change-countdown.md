# Roll-Change Countdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, refresh-safe countdown for the next synchronized roll change on each machine's current running or paused extrusion card, with one-touch schedule advancement and a correction editor that never changes production data.

**Architecture:** Keep the feature entirely in browser-local state: a pure JavaScript schedule module owns calculation, validation, pause/resume reconciliation, serialization, and warning-state derivation, while a thin DOM controller binds that state to server-rendered machine-card and selected-card hosts. Store one versioned record per machine/card in `localStorage`, derive display values from absolute timestamps without per-second writes, and clear records when the server-rendered current-card context no longer matches. FastAPI routes, SQLite schema, card versions, roll records, and production timing remain unchanged.

**Tech Stack:** Python 3, FastAPI, Jinja2 server-rendered HTML, vanilla JavaScript ES modules, browser `localStorage`, CSS, Node's built-in test runner, pytest, and repo-local Playwright 1.61.0.

## Global Constraints

- [README.md](../../../README.md), [AGENTS.md](../../../AGENTS.md), and [v2-files/AGENTS.md](../../../v2-files/AGENTS.md) govern the implementation. Do not mutate `data/extrusion_terminal.sqlite3`; every automated and browser test uses a temporary database under `.test-runtime/`.
- [v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md](../../../v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md) is the approved behavioral contract. This plan may make implementation details explicit but may not expand the feature.
- There is one optional schedule per machine's current card and one schedule represents every synchronized winding lane on that machine. Do not add per-roll, per-lane, per-pallet, or per-spindle countdowns.
- The frequent acknowledgement uses its click time as the new previous/start anchor and sets the next expected time to exactly one interval after that click; it never jumps by multiple intervals to catch up automatically.
- Track only `running` and `paused` cards. Starting a card does not create a schedule. A pending, awaiting-rewinding, completed, archived, cancelled, replaced, or moved card clears its former schedule.
- Pausing freezes the displayed duration. Paused timers are yellow, including `00:00`; unresolved timers remain frozen after resume until acknowledgement or a valid editor save. A resumed unresolved positive duration stays yellow and a resumed unresolved zero duration is red.
- Warning boundaries use exact milliseconds: more than `05:00` is normal, `05:00` through `01:01` is yellow, and `01:00` through due is red. A positive partial minute rounds up for display; overdue values clamp to `00:00`.
- Operator inputs use local dates/times at minute precision. Interval hours are `0..23`, interval minutes are `0..59`, and the combined interval is `1..1439` minutes. A direct next-time override must be later than the previous/start timestamp.
- Browser storage is versioned and keyed by machine and card. It stores absolute timestamps plus only the pause/frozen facts needed to recover state. It does not store a decremented value every second and is not authoritative production history.
- Preserve Task 11 rewinding behavior. Remove only its inert `Смяна на ролка` roll-panel control; keep `Пренавиване` and all waiting-return behavior unchanged.
- Add no route, database column/table/index/constraint, migration, dependency, background service, notification, audio, flashing, analytics, or history ledger.
- Preserve the three existing production-lifecycle control sizes and priority. The countdown controls are a visually separated sibling group, not additional lifecycle slots.
- Machine dots and countdowns need non-color meaning, keyboard focus, Bulgarian accessible names, and no nested interactive element inside a machine-card link.
- Do not stage or commit unless the user separately authorizes it. The commit commands in this plan are conditional review gates, not authorization.

---

## File And Responsibility Map

### New files

- `app/static/js/roll_change_countdown_core.mjs`: pure schedule types, local-time parsing/formatting, validation, state transitions, countdown presentation, and versioned storage helpers; it has no DOM or FastAPI dependency.
- `app/static/js/roll_change_countdown.mjs`: DOM controller for the four machine cards, selected-card controls, editor modal, ticking, lifecycle reconciliation, cleanup, focus management, and `storage`-event synchronization.
- `tests/js/roll_change_countdown_core.test.mjs`: deterministic Node tests for every calculation, validation, storage, warning, acknowledgement, pause/resume, and stale-context rule.
- `scripts/create_roll_change_countdown_fixture.py`: guarded temporary SQLite fixture with active cards on all four machines plus follow-on/end-state cards for browser verification.
- `scripts/verify_roll_change_countdown_ui.mjs`: guarded Playwright workflow at `1920x768` and `1366x768`, with schedule injection, lifecycle interactions, refresh checks, geometry assertions, screenshots, and a JSON result.
- `tests/test_roll_change_countdown_ui_script_safety.py`: path containment, symlink, explicit-input, fixture determinism, and health-preflight tests for the two browser-verification scripts.
- `docs/implementation-notes/roll-change-countdown.md`: durable operational meaning, storage boundary, state machine, recovery limits, verification command, and no-migration rationale.

### Existing files to modify

- `app/templates/terminal.html`: circular-arrow icon, machine-state dots and timer hosts, selected-card timer controls, editor markup, responsive CSS, and module loading; remove the old inert roll-panel action.
- `tests/test_terminal_v8_render.py`: server-rendered state-dot, host, editor, control-eligibility, Task 11 boundary, and layout-contract tests.
- `README.md`: replace the deferred timer statement with the accepted optional workstation pace-clock behavior and explicitly distinguish it from production timing.
- `v2-files/PLAN.md`: point Task 10 at this implementation plan and record implementation/verification status only after it is actually complete.
- `v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md`: change only its workflow status after implementation and verification; do not rewrite the approved behavioral sections.
- `v2-files/AGENTS.md`: update the migration assessment log only if the user has invoked its migration-maintenance command; the expected completed-diff decision is no migration.

## Shared JavaScript Contracts

The two JavaScript modules must use these exact names and shapes:

```js
/** @typedef {"running" | "paused"} TrackableStatus */
/** @typedef {"normal" | "warning" | "urgent" | "paused" | "resync"} CountdownTone */

/**
 * @typedef {Object} RollChangeSchedule
 * @property {1} schemaVersion
 * @property {number} machineId
 * @property {number} cardId
 * @property {number} previousChangeAtMs
 * @property {number} intervalMinutes
 * @property {number} nextExpectedAtMs
 * @property {TrackableStatus} observedStatus
 * @property {number | null} frozenRemainingMs
 * @property {boolean} pauseNeedsResolution
 */

/**
 * @typedef {Object} CountdownView
 * @property {number} remainingMs
 * @property {string} display
 * @property {CountdownTone} tone
 * @property {boolean} due
 * @property {boolean} paused
 * @property {boolean} unresolved
 * @property {string} nextExpectedLabel
 */
```

Storage keys are exactly:

```text
extrusion-terminal.roll-change.v1.machine.<machine-id>
```

The controller consumes this DOM contract:

```text
[data-roll-change-machine][data-machine-id][data-card-id][data-card-status]
  [data-roll-change-machine-timer]

[data-roll-change-controls][data-machine-id][data-card-id][data-card-status]
  [data-roll-change-open]
  [data-roll-change-control-value]
  [data-roll-change-control-next]
  [data-roll-change-advance]

[data-roll-change-overlay]
  [data-roll-change-dialog]
  [data-roll-change-form]
  [data-roll-change-previous]
  [data-roll-change-hours]
  [data-roll-change-minutes]
  [data-roll-change-next]
  [data-roll-change-error-for="previous|hours|minutes|next|form"]
  [data-roll-change-restart]
  [data-roll-change-clear]
  [data-roll-change-cancel]
```

---

### Task 1: Build The Pure Countdown And Persistence Model

**Files:**

- Create: `app/static/js/roll_change_countdown_core.mjs`
- Create: `tests/js/roll_change_countdown_core.test.mjs`

**Interfaces:**

- Consumes: only standard JavaScript `Date`, `JSON`, and a `Storage`-compatible object with `length`, `key`, `getItem`, `setItem`, and `removeItem`.
- Produces: `STORAGE_VERSION`, `STORAGE_KEY_PREFIX`, `storageKey`, `parseOperatorLocalMinute`, `toLocalDateTimeInputValue`, `formatNextExpected`, `parseIntervalMinutes`, `calculateNextExpected`, `validateEditorValues`, `buildSchedule`, `decodeSchedule`, `loadSchedule`, `saveSchedule`, `clearSchedule`, `reconcileCardStatus`, `advanceSchedule`, `countdownView`, and `formatRemaining`.

- [ ] **Step 1: Write the failing schedule, boundary, and storage tests**

Create the Node test file with deterministic local timestamps and a memory-storage test double:

```js
import test from "node:test";
import assert from "node:assert/strict";

import {
  STORAGE_KEY_PREFIX,
  advanceSchedule,
  buildSchedule,
  calculateNextExpected,
  countdownView,
  decodeSchedule,
  loadSchedule,
  parseOperatorLocalMinute,
  reconcileCardStatus,
  saveSchedule,
  storageKey,
  validateEditorValues,
} from "../../app/static/js/roll_change_countdown_core.mjs";

const minute = 60_000;
const localAt = (year, month, day, hour, minutes, seconds = 0) =>
  new Date(year, month - 1, day, hour, minutes, seconds, 0).getTime();

class MemoryStorage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.has(key) ? this.values.get(key) : null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
}

const runningSchedule = () => buildSchedule({
  machineId: 2,
  cardId: 22,
  previousChangeAtMs: localAt(2026, 7, 27, 12, 0),
  intervalMinutes: 120,
  nextExpectedAtMs: localAt(2026, 7, 27, 14, 0),
  status: "running",
  nowMs: localAt(2026, 7, 27, 12, 0),
});

test("initial schedule calculation crosses midnight with absolute local time", () => {
  assert.equal(
    calculateNextExpected(localAt(2026, 7, 27, 23, 30), 120),
    localAt(2026, 7, 28, 1, 30),
  );
});

test("early, on-time, and late acknowledgement each use click time as the anchor", () => {
  for (const clickedAt of [
    localAt(2026, 7, 27, 13, 50),
    localAt(2026, 7, 27, 14, 0),
    localAt(2026, 7, 27, 14, 20),
  ]) {
    assert.equal(
      advanceSchedule(runningSchedule(), "running", clickedAt).nextExpectedAtMs,
      clickedAt + 120 * minute,
    );
  }
});

test("late acknowledgement advances from click time by exactly one interval", () => {
  const advanced = advanceSchedule(
    runningSchedule(),
    "running",
    localAt(2026, 7, 27, 14, 20),
  );
  assert.equal(advanced.previousChangeAtMs, localAt(2026, 7, 27, 14, 20));
  assert.equal(advanced.nextExpectedAtMs, localAt(2026, 7, 27, 16, 20));
});

test("warning boundaries and rounded display use exact milliseconds", () => {
  const schedule = runningSchedule();
  assert.equal(countdownView(schedule, "running", schedule.nextExpectedAtMs - 5 * minute - 1).tone, "normal");
  assert.equal(countdownView(schedule, "running", schedule.nextExpectedAtMs - 5 * minute).tone, "warning");
  assert.equal(countdownView(schedule, "running", schedule.nextExpectedAtMs - minute - 1).tone, "warning");
  assert.equal(countdownView(schedule, "running", schedule.nextExpectedAtMs - minute).tone, "urgent");
  assert.equal(countdownView(schedule, "running", schedule.nextExpectedAtMs - 1).display, "00:01");
  assert.deepEqual(
    { display: countdownView(schedule, "running", schedule.nextExpectedAtMs + minute).display,
      due: countdownView(schedule, "running", schedule.nextExpectedAtMs + minute).due },
    { display: "00:00", due: true },
  );
});

test("pause, unresolved resume, and acknowledgement preserve the approved state machine", () => {
  const pausedAt = localAt(2026, 7, 27, 13, 50);
  const paused = reconcileCardStatus(runningSchedule(), "paused", pausedAt);
  assert.equal(paused.frozenRemainingMs, 10 * minute);
  assert.equal(paused.pauseNeedsResolution, true);
  assert.equal(countdownView(paused, "paused", pausedAt + 30 * minute).display, "00:10");
  assert.equal(countdownView(paused, "paused", pausedAt + 30 * minute).tone, "paused");

  const resumed = reconcileCardStatus(paused, "running", pausedAt + 30 * minute);
  assert.equal(countdownView(resumed, "running", pausedAt + 90 * minute).display, "00:10");
  assert.equal(countdownView(resumed, "running", pausedAt + 90 * minute).tone, "resync");

  const resolved = advanceSchedule(resumed, "running", pausedAt + 90 * minute);
  assert.equal(resolved.nextExpectedAtMs, pausedAt + 210 * minute);
  assert.equal(resolved.pauseNeedsResolution, false);
  assert.equal(resolved.frozenRemainingMs, null);
});

test("paused due suppresses red but resumed unresolved due restores red", () => {
  const schedule = runningSchedule();
  const paused = reconcileCardStatus(schedule, "paused", schedule.nextExpectedAtMs);
  assert.equal(countdownView(paused, "paused", schedule.nextExpectedAtMs + minute).tone, "paused");
  assert.equal(countdownView(paused, "paused", schedule.nextExpectedAtMs + minute).display, "00:00");
  const resumed = reconcileCardStatus(paused, "running", schedule.nextExpectedAtMs + 10 * minute);
  assert.equal(countdownView(resumed, "running", schedule.nextExpectedAtMs + 20 * minute).tone, "urgent");
});

test("manual next override remains editable but later acknowledgement uses click time", () => {
  const values = validateEditorValues({
    previousValue: "2026-07-27T14:00",
    hoursValue: "2",
    minutesValue: "0",
    nextValue: "2026-07-27T16:30",
  }, localAt(2026, 7, 27, 14, 20));
  assert.equal(values.ok, true);
  const schedule = buildSchedule({
    machineId: 2,
    cardId: 22,
    ...values.value,
    status: "running",
    nowMs: localAt(2026, 7, 27, 14, 20),
  });
  assert.equal(
    advanceSchedule(schedule, "running", localAt(2026, 7, 27, 16, 50)).nextExpectedAtMs,
    localAt(2026, 7, 27, 18, 50),
  );
});

test("time-only values resolve to the most recent non-future local occurrence", () => {
  const now = localAt(2026, 7, 28, 0, 10);
  assert.equal(parseOperatorLocalMinute("23:55", now), localAt(2026, 7, 27, 23, 55));
  assert.equal(parseOperatorLocalMinute("00:05", now), localAt(2026, 7, 28, 0, 5));
});

test("storage rejects malformed, unsupported, wrong-card, and invalid intervals", () => {
  const storage = new MemoryStorage();
  const key = storageKey(2);
  assert.equal(key, `${STORAGE_KEY_PREFIX}2`);
  for (const raw of [
    "not-json",
    JSON.stringify({ ...runningSchedule(), schemaVersion: 2 }),
    JSON.stringify({ ...runningSchedule(), cardId: 99 }),
    JSON.stringify({ ...runningSchedule(), intervalMinutes: 0 }),
  ]) {
    storage.setItem(key, raw);
    assert.equal(loadSchedule(storage, 2, 22), null);
    assert.equal(storage.getItem(key), null);
  }
  saveSchedule(storage, runningSchedule());
  assert.deepEqual(decodeSchedule(storage.getItem(key), 2, 22), runningSchedule());
});
```

Add focused cases in the same file for initial `12:00 + 02:00 = 14:00`, early/on-time acknowledgement, cross-midnight input/labels, interval field bounds, zero combined interval, nonexistent local date/time rejection, `next <= previous`, paused acknowledgement, paused editor replacement, resolved pause resume, untrackable status returning `null`, and positive displays beyond 24 hours.

- [ ] **Step 2: Run the tests and verify the intended red state**

Run:

```bash
node --test tests/js/roll_change_countdown_core.test.mjs
```

Expected: `ERR_MODULE_NOT_FOUND` for `roll_change_countdown_core.mjs`.

- [ ] **Step 3: Implement the pure model with strict validation**

Create the module around these exact constants and transition rules:

```js
export const STORAGE_VERSION = 1;
export const STORAGE_KEY_PREFIX = "extrusion-terminal.roll-change.v1.machine.";
const MINUTE_MS = 60_000;
const MAX_INTERVAL_MINUTES = 23 * 60 + 59;
const TRACKABLE = new Set(["running", "paused"]);

export function storageKey(machineId) {
  if (!Number.isSafeInteger(machineId) || machineId <= 0) throw new TypeError("Invalid machine ID");
  return `${STORAGE_KEY_PREFIX}${machineId}`;
}

export function formatRemaining(remainingMs) {
  const totalMinutes = Math.ceil(Math.max(0, remainingMs) / MINUTE_MS);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export function calculateNextExpected(previousChangeAtMs, intervalMinutes) {
  return previousChangeAtMs + intervalMinutes * MINUTE_MS;
}

export function buildSchedule({
  machineId, cardId, previousChangeAtMs, intervalMinutes,
  nextExpectedAtMs, status, nowMs,
}) {
  const candidate = {
    schemaVersion: STORAGE_VERSION,
    machineId,
    cardId,
    previousChangeAtMs,
    intervalMinutes,
    nextExpectedAtMs,
    observedStatus: status,
    frozenRemainingMs: status === "paused" ? Math.max(0, nextExpectedAtMs - nowMs) : null,
    pauseNeedsResolution: false,
  };
  const decoded = validateScheduleObject(candidate, machineId, cardId);
  if (!decoded) throw new TypeError("Invalid roll-change schedule");
  return decoded;
}

export function reconcileCardStatus(schedule, status, nowMs) {
  if (!TRACKABLE.has(status)) return null;
  if (schedule.observedStatus === status) return schedule;
  if (status === "paused") {
    return {
      ...schedule,
      observedStatus: "paused",
      frozenRemainingMs: Math.max(0, schedule.nextExpectedAtMs - nowMs),
      pauseNeedsResolution: true,
    };
  }
  return {
    ...schedule,
    observedStatus: "running",
    frozenRemainingMs: schedule.pauseNeedsResolution ? schedule.frozenRemainingMs : null,
  };
}

export function advanceSchedule(schedule, status, nowMs) {
  const nextExpectedAtMs = nowMs + schedule.intervalMinutes * MINUTE_MS;
  return {
    ...schedule,
    previousChangeAtMs: nowMs,
    nextExpectedAtMs,
    observedStatus: status,
    frozenRemainingMs: status === "paused" ? Math.max(0, nextExpectedAtMs - nowMs) : null,
    pauseNeedsResolution: false,
  };
}

export function countdownView(schedule, status, nowMs) {
  const unresolved = schedule.pauseNeedsResolution && schedule.frozenRemainingMs !== null;
  const remainingMs = status === "paused" || unresolved
    ? Math.max(0, schedule.frozenRemainingMs ?? 0)
    : Math.max(0, schedule.nextExpectedAtMs - nowMs);
  const due = remainingMs === 0;
  let tone = "normal";
  if (status === "paused") tone = "paused";
  else if (unresolved && !due) tone = "resync";
  else if (remainingMs <= MINUTE_MS) tone = "urgent";
  else if (remainingMs <= 5 * MINUTE_MS) tone = "warning";
  return {
    remainingMs,
    display: formatRemaining(remainingMs),
    tone,
    due,
    paused: status === "paused",
    unresolved,
    nextExpectedLabel: formatNextExpected(schedule.nextExpectedAtMs, nowMs),
  };
}
```

Implement the remaining exported functions with these exact safeguards:

- `parseOperatorLocalMinute(value, nowMs)` accepts only `YYYY-MM-DDTHH:mm` or `HH:mm`; it round-trips constructed local `Date` fields to reject impossible/DST-normalized input, and time-only input moves back one local day only when today's candidate is later than `nowMs`.
- `parseIntervalMinutes(hoursValue, minutesValue)` accepts base-10 digit strings only and checks `0..23` and `0..59`. Invalid hours return `Часовете трябва да са цяло число от 0 до 23.` under `hours`; invalid minutes return `Минутите трябва да са цяло число от 0 до 59.` under `minutes`; a combined zero returns `Изберете интервал поне 1 минута.` under `form`.
- `validateEditorValues(values, nowMs)` returns `{ok: false, errors}` or `{ok: true, value: {previousChangeAtMs, intervalMinutes, nextExpectedAtMs}}`. Invalid previous/start input returns `Въведете валиден начален час.` under `previous`; invalid next input returns `Въведете валиден час за следващата смяна.` under `next`; and `nextExpectedAtMs <= previousChangeAtMs` returns `Следващата смяна трябва да е след предишната.` under `next`.
- `validateScheduleObject` requires the exact schema version, safe positive integer IDs, finite integer minute timestamps, interval `1..1439`, `nextExpectedAtMs > previousChangeAtMs`, a trackable observed status, `null` or non-negative finite integer frozen milliseconds, and a boolean resolution flag. Reject rather than coerce.
- `loadSchedule` removes a present value if JSON, schema, machine, card, or field validation fails. `saveSchedule` writes one JSON record. `clearSchedule` removes exactly one machine key.
- `toLocalDateTimeInputValue` emits `YYYY-MM-DDTHH:mm`. `formatNextExpected` emits `HH:mm` for the same local date as `nowMs`, otherwise `DD.MM HH:mm`.

- [ ] **Step 4: Run the complete core test file**

Run:

```bash
node --test tests/js/roll_change_countdown_core.test.mjs
```

Expected: every countdown-core test passes, with no timer sleeps and no dependence on the machine's UTC offset.

- [ ] **Step 5: Review the pure-state diff and conditionally commit**

Run:

```bash
git diff --check
git diff -- app/static/js/roll_change_countdown_core.mjs tests/js/roll_change_countdown_core.test.mjs
```

If and only if the user has explicitly authorized commits:

```bash
git add app/static/js/roll_change_countdown_core.mjs tests/js/roll_change_countdown_core.test.mjs
git commit -m "Add roll-change countdown state model"
```

---

### Task 2: Add The Server-Rendered Timer Hosts And Editor

**Files:**

- Modify: `app/templates/terminal.html` (icon macro near lines 1-28; machine-card CSS near lines 286-400; action CSS near lines 630-665; modal CSS near lines 2257-2360; machine navigation near lines 3365-3390; lifecycle actions near lines 3510-3555; roll-panel actions near lines 3674-3686; overlays near lines 3910-3975; script include near line 5062)
- Modify: `tests/test_terminal_v8_render.py` (machine navigation tests near lines 320-430; Task 11 boundary tests near lines 1270-1320; lifecycle-slot tests near lines 2230-2260)

**Interfaces:**

- Consumes: the shared DOM contract above and existing Jinja values `queue.machine.id`, `queue.focus_card`, `selected_card.machine_id`, `selected_card.id`, and `selected_card.status`.
- Produces: non-interactive machine timer hosts for all four cards, active-card selected controls, one editor overlay, `refresh-cw` macro icon, and the exact data attributes consumed by `roll_change_countdown.mjs`.

- [ ] **Step 1: Replace the inert-control assertions with failing Task 10 render assertions**

Rename `test_terminal_v8_renders_rewinding_marker_and_inert_roll_change_controls` to `test_terminal_v8_renders_rewinding_and_roll_change_hosts_in_separate_action_areas` and assert:

```python
running_html = render_terminal(running_id)
assert 'data-rewinding-open' in running_html
assert not re.search(
    r'<div class="roll-secondary-actions"[^>]*>.*data-roll-change-open',
    running_html,
    re.S,
)
assert re.search(
    rf'<div class="roll-change-controls"[^>]+data-machine-id="1"'
    rf'[^>]+data-card-id="{running_id}"[^>]+data-card-status="running"',
    running_html,
)
assert 'data-roll-change-open' in running_html
assert 'data-roll-change-advance' in running_html
assert 'aria-label="Потвърди смяна на ролките"' in running_html
assert 'data-roll-change-overlay' in running_html
assert 'src="/static/js/roll_change_countdown.mjs"' in running_html

paused_html = render_terminal(paused_id)
assert 'data-card-status="paused"' in paused_html
assert 'data-roll-change-controls' in paused_html

for unavailable_id in (pending_id, waiting_id, completed_id):
    unavailable_html = render_terminal(unavailable_id)
    assert 'data-roll-change-controls' not in unavailable_html
    assert 'data-roll-change-overlay' not in unavailable_html
```

Add a machine-card test that verifies four `data-roll-change-machine` hosts, no old top-right `.status` pills inside `.machine-tab-top`, and these mappings:

```python
assert re.search(r'class="machine-state-dot running".*>.*Машина 1: работи', html, re.S)
assert re.search(r'class="machine-state-dot paused".*>.*Машина 2: пауза', html, re.S)
assert re.search(r'class="machine-state-dot idle".*>.*Машина 3: чака старт', html, re.S)
assert re.search(r'class="machine-state-dot idle".*>.*Машина 4: свободна', html, re.S)
assert len(re.findall(r'data-roll-change-machine-timer', html)) == 4
```

Keep the existing equal-width lifecycle assertion at exactly three slots and add:

```python
assert len(re.findall(r'data-lifecycle-slot=', running_html)) == 3
assert re.search(r'<div class="roll-change-controls"', running_html)
assert 'data-lifecycle-slot' not in html_between_attributes(
    running_html,
    'class="roll-change-controls"',
    'data-roll-change-controls',
)
```

Use the file's existing HTML helper style; if `html_between_attributes` does not exist, select the timer-group block with one local regular expression instead of adding a general parser.

- [ ] **Step 2: Run the focused render tests and confirm they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py -q -k "roll_change or machine_navigation or lifecycle_slots"
```

Expected: failures because the machine icon/status pill and inert roll-panel action are still rendered and the new hosts/editor do not exist.

- [ ] **Step 3: Render machine-state dots and a stable blank/countdown slot**

Replace the machine-title image and top-right status pill with this structure:

```jinja2
{% if focus_card and focus_card.status == "running" %}
  {% set machine_dot_class = "running" %}
  {% set machine_dot_label = "работи" %}
{% elif focus_card and focus_card.status == "paused" %}
  {% set machine_dot_class = "paused" %}
  {% set machine_dot_label = "пауза" %}
{% elif focus_card %}
  {% set machine_dot_class = "idle" %}
  {% set machine_dot_label = "чака старт" %}
{% else %}
  {% set machine_dot_class = "idle" %}
  {% set machine_dot_label = "свободна" %}
{% endif %}
<a class="machine-tab {% if focus_card %}{{ focus_card.status_display_class }}{% else %}idle{% endif %} {% if queue.is_selected %}selected{% endif %}"
   href="{% if focus_card %}/terminal/cards/{{ focus_card.id }}{% else %}/terminal?machine_id={{ queue.machine.id }}{% endif %}"
   data-roll-change-machine
   data-machine-id="{{ queue.machine.id }}"
   data-card-id="{{ focus_card.id if focus_card else '' }}"
   data-card-status="{{ focus_card.status if focus_card else 'free' }}">
  <span class="machine-tab-top">
    <span class="machine-tab-title">
      <span class="machine-state-dot {{ machine_dot_class }}" aria-hidden="true"></span>
      <span class="visually-hidden">Машина {{ queue.machine.id }}: {{ machine_dot_label }}</span>
      <span class="machine-tab-name">Машина {{ queue.machine.id }}</span>
    </span>
    <span class="machine-countdown" data-roll-change-machine-timer hidden></span>
  </span>
  <span class="machine-tab-meta">
    <span class="machine-tab-customer">{{ focus_card.customer if focus_card else "-" }}</span>
    {% if focus_card %}
      <span class="machine-tab-product">{{ focus_card.product_type or "-" }}</span>
    {% else %}
      <span class="machine-tab-product" aria-hidden="true"></span>
    {% endif %}
  </span>
  <span class="machine-tab-progress">
    <span class="progress"><span style="width:{{ focus_card.progress_percent if focus_card else 0 }}%"></span></span>
    <span class="machine-tab-qty">{{ whole_kg(focus_card.produced_gross_weight if focus_card else "0") }} / {{ whole_kg(focus_card.target_gross_weight if focus_card and focus_card.target_gross_weight else none) }} кг</span>
  </span>
</a>
```

Keep the machine-card metadata and progress expressions and ordering shown above.

Add fixed-geometry styles:

```css
.machine-state-dot {
  width: 14px;
  height: 14px;
  flex: 0 0 14px;
  border: 2px solid rgba(255, 255, 255, .9);
  border-radius: 50%;
  box-shadow: 0 0 0 1px #9aa6b2;
}
.machine-state-dot.running { background: var(--green); }
.machine-state-dot.paused { background: #d39b16; }
.machine-state-dot.idle { background: #87929e; }

.machine-countdown {
  min-width: 72px;
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid #b8c4d1;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #0b355f;
  background: #f5f8fb;
  font-size: 15px;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.machine-countdown.warning,
.machine-countdown.paused,
.machine-countdown.resync { color: #704100; background: #fff2bd; border-color: #d7a13f; }
.machine-countdown.urgent { color: #fff; background: var(--red); border-color: var(--red); }
.machine-countdown[hidden] { display: none; }
```

- [ ] **Step 4: Render selected-card controls without changing lifecycle slots**

For a running or paused selected card, render one `data-roll-change-controls`
group before the lifecycle forms inside `.actions`. The group remains left of the
right-aligned Start, Pause/Resume, and End controls; those lifecycle controls
retain their existing grouping and dimensions. The group has no divider.

The inactive setup button uses the supplied circular rewinding asset and the
label `Смяна на ролка`. When tracking is active, that button shows only the
countdown, and the separate circular-arrow `data-roll-change-advance` button
acknowledges the change. Keep the existing DOM data attributes and the current
template/CSS sizing relationships rather than introducing fixed-width or
two-line assumptions.

- [ ] **Step 5: Add the editor markup and remove only the Task 11 inert action**

Leave the rewinding button and its status/count conditions unchanged. For a
selected running or paused card, render the shipped modal after the rewinding
overlay. Its three numbered sections are `Начало врътка`, `Интервал`, and
`Очаквана смяна на ролките`.

The start and expected sections each use a native date field plus direct text
hour and minute fields with a visible colon separator. The interval section uses
the same split text hour/minute treatment and shows its reminder summary. Keep
the canonical hidden start/next inputs for controller synchronization, the
current field-error slots, the close button, and the shipped actions:
`Използвай текущия час`, `Изключи брояча`, `Отказ`, and `Запиши`.

Use the current modal, section, field, focus, and responsive styles from the
terminal template. Do not introduce alternate field widgets, a new confirmation
layer, or obsolete fixed-size assumptions.

- [ ] **Step 6: Load the controller as a deferred ES module**

After the existing inline script and before `</body>`, add:

```jinja2
<script type="module" src="{{ url_for('static', path='/js/roll_change_countdown.mjs') }}"></script>
```

Do not change `app/main.py`; `/static` is already mounted.

- [ ] **Step 7: Run focused and complete render tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py -q -k "roll_change or machine_navigation or lifecycle_slots or rewinding"
python -m pytest tests/test_terminal_v8_render.py -q
```

Expected: both commands pass; exactly three lifecycle slots remain for running/paused cards, pending/ended selected cards have no countdown controls/editor, and the rewinding control still renders in its approved states.

- [ ] **Step 8: Review the markup/CSS diff and conditionally commit**

Run:

```bash
git diff --check
git diff -- app/templates/terminal.html tests/test_terminal_v8_render.py
```

If and only if the user has explicitly authorized commits:

```bash
git add app/templates/terminal.html tests/test_terminal_v8_render.py
git commit -m "Add roll-change countdown UI hosts"
```

---

### Task 3: Wire Countdown Rendering, Editing, Advancement, And Tab Synchronization

**Files:**

- Create: `app/static/js/roll_change_countdown.mjs`
- Modify: `app/static/js/roll_change_countdown_core.mjs`
- Modify: `tests/js/roll_change_countdown_core.test.mjs`
- Create: `scripts/create_roll_change_countdown_fixture.py`
- Create: `scripts/verify_roll_change_countdown_ui.mjs`

**Interfaces:**

- Consumes: every export from Task 1 and every data attribute from Task 2.
- Produces: `bootstrapRollChangeCountdown({documentObject, windowObject, now, intervalFactory})`, a browser-started controller instance, task-specific fixture JSON, screenshots, and a Playwright verification summary.

- [ ] **Step 1: Add failing storage-cleanup and same-origin synchronization tests to the core file**

Add tests proving that `clearMismatchedSchedules(storage, contexts)` removes only roll-change keys whose machine context is missing, untrackable, or has a different card, while preserving unrelated `localStorage` entries:

```js
import { clearMismatchedSchedules } from "../../app/static/js/roll_change_countdown_core.mjs";

test("context cleanup removes ended and replaced cards but preserves unrelated storage", () => {
  const storage = new MemoryStorage();
  storage.setItem("unrelated", "keep");
  saveSchedule(storage, runningSchedule());
  saveSchedule(storage, buildSchedule({
    machineId: 3,
    cardId: 33,
    previousChangeAtMs: localAt(2026, 7, 27, 12, 0),
    intervalMinutes: 60,
    nextExpectedAtMs: localAt(2026, 7, 27, 13, 0),
    status: "running",
    nowMs: localAt(2026, 7, 27, 12, 0),
  }));
  clearMismatchedSchedules(storage, new Map([
    [2, { cardId: 99, status: "running" }],
    [3, { cardId: 33, status: "completed" }],
  ]));
  assert.equal(storage.getItem(storageKey(2)), null);
  assert.equal(storage.getItem(storageKey(3)), null);
  assert.equal(storage.getItem("unrelated"), "keep");
});
```

Extend the test double before this test:

```js
get length() { return this.values.size; }
key(index) { return Array.from(this.values.keys())[index] ?? null; }
```

Run `node --test tests/js/roll_change_countdown_core.test.mjs` and expect failure because `clearMismatchedSchedules` is not exported.

- [ ] **Step 2: Implement prefix-scoped cleanup**

Export:

```js
export function clearMismatchedSchedules(storage, contexts) {
  const keys = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key?.startsWith(STORAGE_KEY_PREFIX)) keys.push(key);
  }
  for (const key of keys) {
    const machineId = Number(key.slice(STORAGE_KEY_PREFIX.length));
    const context = contexts.get(machineId);
    const schedule = context ? loadSchedule(storage, machineId, context.cardId) : null;
    if (!context || !TRACKABLE.has(context.status) || !schedule) storage.removeItem(key);
  }
}
```

Extend `MemoryStorage` with `length` and `key(index)`, rerun the Node suite, and expect all tests to pass.

- [ ] **Step 3: Create the controller with injected clock/timer seams**

Implement and export `bootstrapRollChangeCountdown({documentObject = document,
windowObject = window, now = () => Date.now(), intervalFactory = (callback) =>
windowObject.setInterval(callback, 1_000)} = {})`. It returns an object with
`refresh: () => void` and `destroy: () => void`.

The body must perform these exact operations:

1. Parse every machine host into `Map<number, {cardId: number, status: string, host: Element}>`.
2. Call `clearMismatchedSchedules(windowObject.localStorage, contexts)` before rendering.
3. For each trackable matching record, call `reconcileCardStatus(record, status, now())`; persist only if reconciliation changed stored state.
4. Render inactive machine slots with `hidden = true`; render active slots with `view.display`, `view.tone`, and `aria-label = "Машина N, смяна на ролките след HH:MM"` or `"Машина N, смяната на ролките е дължима"`.
5. Render the selected inactive open control with the supplied circular rewinding asset and `Смяна на ролка`, then hide the quick button. Render the active control with the remaining countdown and unhide the separate quick button. Its Bulgarian `aria-label` includes the next expected label in both normal and due states.
6. Start one display interval for the page. Each tick rerenders from timestamps; it never calls `saveSchedule`.
7. Listen for `storage` events whose key begins with `STORAGE_KEY_PREFIX`; validate, reconcile for the page's server-rendered status, and rerender all affected surfaces without reloading.
8. Return `destroy()` that clears the display interval and removes the storage listener so the module is testable and does not leak listeners.

At module bottom, bootstrap once after module evaluation:

```js
if (typeof document !== "undefined" && typeof window !== "undefined") {
  bootstrapRollChangeCountdown();
}
```

- [ ] **Step 4: Implement the editor as a draft until Save**

Use one `savedSchedule` and one `returnFocus` variable inside the controller. Opening:

- reads the current valid matching schedule;
- defaults previous/start to the current local minute when inactive;
- uses `0` hours and `0` minutes for an inactive interval and leaves next blank until a positive interval exists;
- fills active values from storage;
- clears errors, unhides the overlay, sets `aria-hidden="false"` and `aria-expanded="true"`, then focuses the previous/start field.

On start-date/start-time or interval input, synchronize the split controls into
the canonical hidden start value, update the interval summary, and recalculate
the split expected fields only when the start and interval are valid. Direct
expected-date/time edits synchronize their canonical hidden value and remain
otherwise untouched. Submit calls `validateEditorValues`, renders each Bulgarian
error in its matching error slot, and writes one complete `buildSchedule` only
when valid. Saving while paused sets a resolved paused schedule; saving while
resumed-unresolved clears the frozen state because `buildSchedule` creates a
corrected schedule. On success, close and rerender.

`Използвай текущия час` updates only the draft previous/start date and time to the
current local time. It leaves the next draft, interval values, validation
errors, `aria-invalid` state, and browser storage unchanged; it neither
validates nor recalculates. Only `Запиши` validates and persists the complete
draft. `Изключи брояча` immediately removes this machine's key, closes, and rerenders
without a confirmation.

Cancel, backdrop click, and Escape close without writing and restore focus to the open control. Trap Tab/Shift+Tab inside the visible dialog. Do not close on an interior dialog click. No modal opens automatically.

- [ ] **Step 5: Wire the one-touch acknowledgement**

On `[data-roll-change-advance]` click:

```js
const current = loadSchedule(storage, selectedMachineId, selectedCardId);
if (!current) return;
const advanced = advanceSchedule(current, selectedStatus, now());
saveSchedule(storage, advanced);
refresh();
```

Do not confirm, navigate, submit a form, modify a card version, or emit a production timestamp. Use click time as the new previous/start anchor and calculate exactly one interval after it. Keep the button enabled for every active running/paused schedule, including early, due, paused, and resumed-unresolved states.

- [ ] **Step 6: Build a guarded deterministic browser fixture**

Follow the path guards in `scripts/create_rewinding_fixture.py`, but create a separate fixture. It must reject the runtime DB, paths outside `.test-runtime`, and symlinked guard roots before any write. Define `SCENARIOS`, `fixture_row`, `import_scenarios`, `card_version`, `require_ok`, `release`, `set_defaults`, `add_roll`, `start`, `pause`, and `finish` with the same signatures as the existing guarded fixture, changing only fixture labels and imported order values. Seed and return these exact scenario names:

```python
SCENARIOS = (
    "machine_1_running",
    "machine_1_follow_up",
    "machine_2_running",
    "machine_3_running",
    "machine_4_paused",
    "completed",
)

def create_fixture(database_path: Path) -> dict[str, object]:
    reset_database(database_path)
    configuration = db.fetch_terminal_configuration()
    require_ok(
        db.start_shift("1", int(configuration["version"])),
        "start active shift",
    )
    cards = import_scenarios()

    release(cards["completed"], 3, 1)
    start(cards["completed"])
    set_defaults(cards["completed"], tare="1.0")
    add_roll(cards["completed"], "20.0")
    finish(cards["completed"])

    release(cards["machine_1_running"], 1, 1)
    release(cards["machine_1_follow_up"], 1, 2)
    release(cards["machine_2_running"], 2, 1)
    release(cards["machine_3_running"], 3, 1)
    release(cards["machine_4_paused"], 4, 1)

    for scenario in (
        "machine_1_running",
        "machine_2_running",
        "machine_3_running",
        "machine_4_paused",
    ):
        start(cards[scenario])
    set_defaults(cards["machine_1_running"], tare="1.0")
    add_roll(cards["machine_1_running"], "25.0")
    pause(cards["machine_4_paused"])

    active_shift_id = int(db.fetch_active_shift()["id"])
    return {
        "db_path": str(database_path),
        "active_shift_id": active_shift_id,
        "cards": cards,
    }
```

Give `machine_1_running` an active shift, valid tare, and one gross roll so normal completion is available. Give every running card one open production segment and the paused card only closed segments. Emit `db_path`, `active_shift_id`, and `cards` in JSON. Use only app database APIs or explicit fixture-only SQL after normal initialization; never copy or open the runtime database.

- [ ] **Step 7: Write the first failing live-browser workflow**

Create `scripts/verify_roll_change_countdown_ui.mjs` with explicit `BASE_URL`, `FIXTURE_JSON`, and `ARTIFACT_DIR` inputs; realpath/symlink guards; a `/health` database-identity preflight; repo-local `createRequire(import.meta.url)("@playwright/test")` resolution; console/page-error capture; and a JSON verification summary.

Before navigation, use `context.addInitScript` to seed relative records based on `Date.now()` for all four machine IDs:

```js
const schedule = ({ machineId, cardId, previousOffsetMinutes, intervalMinutes,
  nextOffsetMinutes, status, frozenRemainingMs = null, pauseNeedsResolution = false }) => ({
  schemaVersion: 1,
  machineId,
  cardId,
  previousChangeAtMs: Date.now() + previousOffsetMinutes * 60_000,
  intervalMinutes,
  nextExpectedAtMs: Date.now() + nextOffsetMinutes * 60_000,
  observedStatus: status,
  frozenRemainingMs,
  pauseNeedsResolution,
});
```

Seed machine 1 normal, machine 2 warning, machine 3 urgent, and machine 4 paused/due. Assert the four dot colors/classes, three visible timer tones plus paused yellow `00:00`, blank timer on inactive follow-on ownership, selected timer controls, exact accessible quick-action label, and no old roll-panel action. The verifier must fail before the controller is complete and pass after it is wired.

- [ ] **Step 8: Run calculation, syntax, render, and first live checks**

Run static checks:

```bash
node --check app/static/js/roll_change_countdown_core.mjs
node --check app/static/js/roll_change_countdown.mjs
node --check scripts/verify_roll_change_countdown_ui.mjs
source .venv/bin/activate
python -m py_compile scripts/create_roll_change_countdown_fixture.py
node --test tests/js/roll_change_countdown_core.test.mjs
python -m pytest tests/test_terminal_v8_render.py -q -k "roll_change or machine_navigation or lifecycle_slots or rewinding"
```

Then create the fixture and start the server in one terminal:

```bash
source .venv/bin/activate
python scripts/create_roll_change_countdown_fixture.py \
  --db-path .test-runtime/roll-change-countdown/fixture.sqlite3 \
  --output .test-runtime/roll-change-countdown/fixture.json
EXTRUSION_DB_PATH=.test-runtime/roll-change-countdown/fixture.sqlite3 \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8012
```

Run the verifier in a second terminal:

```bash
BASE_URL=http://127.0.0.1:8012 \
FIXTURE_JSON=.test-runtime/roll-change-countdown/fixture.json \
ARTIFACT_DIR=artifacts/ui-checks/roll-change-countdown \
node scripts/verify_roll_change_countdown_ui.mjs
```

Expected: zero exit, all first-workflow assertions pass, and screenshots exist for both required viewports.

- [ ] **Step 9: Review the interaction diff and conditionally commit**

Run:

```bash
git diff --check
git diff -- app/static/js/roll_change_countdown_core.mjs app/static/js/roll_change_countdown.mjs tests/js/roll_change_countdown_core.test.mjs scripts/create_roll_change_countdown_fixture.py scripts/verify_roll_change_countdown_ui.mjs
```

If and only if the user has explicitly authorized commits:

```bash
git add app/static/js/roll_change_countdown_core.mjs app/static/js/roll_change_countdown.mjs tests/js/roll_change_countdown_core.test.mjs scripts/create_roll_change_countdown_fixture.py scripts/verify_roll_change_countdown_ui.mjs
git commit -m "Implement roll-change countdown interactions"
```

---

### Task 4: Prove Lifecycle, Refresh, Conflict, And Safety Behavior

**Files:**

- Modify: `scripts/verify_roll_change_countdown_ui.mjs`
- Create: `tests/test_roll_change_countdown_ui_script_safety.py`
- Modify: `tests/test_terminal_v8_render.py`
- Modify only if a failing regression demonstrates a defect: `app/static/js/roll_change_countdown.mjs`, `app/static/js/roll_change_countdown_core.mjs`, or `app/templates/terminal.html`

**Interfaces:**

- Consumes: the complete schedule/controller/browser fixture from Tasks 1-3 and existing terminal Start/Pause/Resume/Finish, stale-write alert, roll correction, rewinding, queue, waiting, history, and shift UI.
- Produces: a guarded task-specific verifier proving all approved workflows at both required viewports without touching the runtime DB.

- [ ] **Step 1: Add failing safety tests before expanding the verifier**

Mirror the current rewinding safety suite with Task 10 names and assert:

```python
FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "create_roll_change_countdown_fixture.py"
VERIFIER_SCRIPT = REPO_ROOT / "scripts" / "verify_roll_change_countdown_ui.mjs"

@pytest.mark.parametrize(
    ("database_path", "output_path"),
    [
        ("data/extrusion_terminal.sqlite3", ".test-runtime/roll-change-safety/output.json"),
        ("{outside}/fixture.sqlite3", "{outside}/fixture.json"),
        (".test-runtime/roll-change-safety/fixture.sqlite3", "{outside}/fixture.json"),
    ],
)
def test_roll_change_fixture_rejects_runtime_and_external_paths(
    tmp_path: Path,
    database_path: str,
    output_path: str,
):
    database_path = database_path.format(outside=tmp_path)
    output_path = output_path.format(outside=tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(FIXTURE_SCRIPT),
            "--db-path",
            database_path,
            "--output",
            output_path,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "must be under .test-runtime" in result.stderr
    if Path(database_path).is_absolute():
        assert not Path(database_path).exists()
    if Path(output_path).is_absolute():
        assert not Path(output_path).exists()
```

The actual test file must include complete versions of these existing safety patterns, adapted to the new scripts:

- deterministic fixture output on two runs;
- fixture DB/output outside `.test-runtime` rejected;
- symlinked `.test-runtime` rejected without altering a sentinel runtime file;
- each of `BASE_URL`, `FIXTURE_JSON`, and `ARTIFACT_DIR` required before browser use;
- fixture symlink escape rejected;
- artifact path/ancestor symlink escapes rejected before writing;
- `/health` DB mismatch prevents fixture reset and every POST/mutation request;
- verifier source resolves Playwright from the repository and contains no npm/npx/install/download command.

Reuse the full guard helpers from `tests/test_rewinding_ui_script_safety.py`, changing only task-specific paths, names, expected scenario keys, and messages.

- [ ] **Step 2: Run the safety suite and confirm the intended failures**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_roll_change_countdown_ui_script_safety.py -q
```

Expected: at least the deterministic scenario and source-policy tests fail until the Task 10 scripts expose the full guarded behavior.

- [ ] **Step 3: Complete script guards and deterministic reset behavior**

Make both scripts pass the safety suite. The verifier must preflight `/health` before calling its fixture reset helper or making a POST. Its reset helper must invoke exactly:

```js
spawnSync(
  path.join(repoRoot, ".venv", "bin", "python"),
  [
    path.join(repoRoot, "scripts", "create_roll_change_countdown_fixture.py"),
    "--db-path", databasePath,
    "--output", fixturePath,
  ],
  { cwd: repoRoot, encoding: "utf8" },
);
```

After reset, compare all emitted card IDs and the real database path to the original fixture JSON.

- [ ] **Step 4: Expand Playwright coverage for the schedule editor and normal path**

At both viewports, exercise and assert:

1. inactive selected card shows only `Смяна на ролка` and no quick action;
2. opening does not write storage;
3. invalid zero/bounds/next-before-previous input remains open with Bulgarian field errors and preserves the prior valid record;
4. previous or interval input recalculates the next draft;
5. direct next-time edit is saved, while a later quick acknowledgement uses its
   click time as the new anchor;
6. late quick acknowledgement sets new previous to the click time and new next to click time plus one interval;
7. a second early acknowledgement again uses its own click time and exactly one interval;
8. Cancel, Escape, and backdrop leave JSON byte-for-byte unchanged and return focus;
9. Restart changes only the previous/start draft to current time and leaves the
   next draft, interval values, errors, aria state, and storage unchanged;
   Cancel still preserves stored state;
10. Clear removes one machine key and hides both terminal timer surfaces without a confirmation;
11. normal refresh and a new browser page in the same context rehydrate the record;
12. a stale production-data write renders the existing conflict-required refresh alert, and clicking its reload control preserves the browser-local countdown unchanged;
13. a second same-origin tab updates after the first tab acknowledges or saves, using the native `storage` event;
14. a due record remains at red `00:00` across multiple display ticks and never advances itself;
15. an accidental early acknowledgement can be corrected through a direct next-time editor save, after which the following quick action uses its own click time as the anchor.

Use direct `page.evaluate(() => JSON.parse(localStorage.getItem(key)))` assertions for exact timestamps. Do not wait two real hours or weaken exact schedule math to visible text checks.

- [ ] **Step 5: Expand Playwright coverage for pause/resume and end-of-order cleanup**

Exercise the real terminal lifecycle forms and assert:

1. pausing a running card freezes the displayed value across a short real wait and refresh;
2. paused urgent/due is yellow, including `00:00`;
3. resume without acknowledgement/edit keeps a positive frozen value yellow and non-ticking;
4. resume of unresolved frozen zero makes it red;
5. acknowledgement while paused uses click time plus one interval, stays visually paused, and becomes resolved;
6. editor Save while paused also resolves it;
7. resolved pause followed by resume returns to timestamp-derived normal/warning/urgent counting;
8. finishing the selected card removes its storage key after redirect, frees/replaces the machine focus, and does not transfer the timer to `machine_1_follow_up`;
9. a manually injected wrong-card, unsupported-version, malformed, pending, waiting, completed, archived, or cancelled record is removed on the next applicable terminal render;
10. no countdown action changes the SQLite snapshot of card version, roll entries, tare, pallet, timing segments, shift attribution, recipe data, or imported fields.

For the “no database mutation” assertion, snapshot the relevant tables through a read-only helper before browser-only timer actions and compare afterward. Lifecycle Pause/Resume/Finish are excluded from that comparison because those existing actions intentionally mutate production timing/status; compare timer-only scenarios separately.

- [ ] **Step 6: Add layout, accessibility, and regression checks**

At `1920x768` and `1366x768`, assert:

- four machine-card geometries do not change between an inactive and active timer;
- dot, timer bubble, customer/product, progress, and quantity do not overlap or clip;
- three lifecycle controls retain equal dimensions, the roll-change group is visually separated from Start using its right edge and Start's left edge, and Shift button side whitespace matches Waiting Orders from rendered geometry;
- roll-ledger header/body columns align with equal scrollbar gutters, and gross/tare/net/pallet values or their editable inputs share vertical centers without an empty gross-error slot reserving space;
- setup/open and quick buttons have usable bounding boxes and visible keyboard focus;
- focus stays inside the editor, Escape restores it, and machine links contain no nested button;
- queue, waiting, Produced Orders, shift window, rewinding dialog, roll add/correction, and dirty-navigation protections still open/close or block exactly as before;
- no horizontal document overflow, error-level console message, or page error occurs.

Capture at least:

```text
artifacts/ui-checks/roll-change-countdown/roll-change-1920x768.png
artifacts/ui-checks/roll-change-countdown/roll-change-1366x768.png
artifacts/ui-checks/roll-change-countdown/editor-validation.png
artifacts/ui-checks/roll-change-countdown/paused-due.png
artifacts/ui-checks/roll-change-countdown/verification-summary.json
```

- [ ] **Step 7: Run focused regression and the complete live verifier**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_roll_change_countdown_ui_script_safety.py tests/test_terminal_v8_render.py tests/test_rewinding_ui_script_safety.py -q
node --test tests/js/roll_change_countdown_core.test.mjs
node --check app/static/js/roll_change_countdown.mjs
node --check scripts/verify_roll_change_countdown_ui.mjs
./node_modules/.bin/playwright --version
```

With the guarded app still running on port `8012`, rerun:

```bash
BASE_URL=http://127.0.0.1:8012 \
FIXTURE_JSON=.test-runtime/roll-change-countdown/fixture.json \
ARTIFACT_DIR=artifacts/ui-checks/roll-change-countdown \
node scripts/verify_roll_change_countdown_ui.mjs
```

Expected: all commands exit zero; the browser summary reports both viewport passes and no console/page errors.

- [ ] **Step 8: Inspect screenshots with the repository image viewer**

Open the four PNGs and verify the machine-card timer never moves the card geometry, urgent and paused states are distinguishable by text as well as color, the topbar controls fit without reducing lifecycle hit areas, and the modal is centered and usable at both viewports. If visual inspection finds a defect, add a failing verifier assertion before changing CSS or controller behavior.

- [ ] **Step 9: Review the lifecycle/safety diff and conditionally commit**

Run:

```bash
git diff --check
git diff -- scripts/verify_roll_change_countdown_ui.mjs tests/test_roll_change_countdown_ui_script_safety.py tests/test_terminal_v8_render.py app/static/js/roll_change_countdown.mjs app/static/js/roll_change_countdown_core.mjs app/templates/terminal.html
```

If and only if the user has explicitly authorized commits:

```bash
git add scripts/verify_roll_change_countdown_ui.mjs tests/test_roll_change_countdown_ui_script_safety.py tests/test_terminal_v8_render.py app/static/js/roll_change_countdown.mjs app/static/js/roll_change_countdown_core.mjs app/templates/terminal.html
git commit -m "Verify roll-change countdown workflow"
```

---

### Task 5: Document The Boundary, Assess Migration Impact, And Run Final Verification

**Files:**

- Create: `docs/implementation-notes/roll-change-countdown.md`
- Modify: `README.md` (workstation behavior near lines 152-225; deferred functionality near lines 812-821)
- Modify: `v2-files/PLAN.md` (Task 10 near lines 260-282)
- Modify: `v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md` (status and handoff sections only)
- Modify only after the repository's migration-maintenance command is authorized: `v2-files/AGENTS.md` (migration assessment log)

**Interfaces:**

- Consumes: the finished implementation diff, test evidence, browser summary, approved Task 10 specification, and the migration-decision procedure in `v2-files/AGENTS.md`.
- Produces: durable operating/design documentation, current task status, an evidence-backed migration decision, and final verification evidence for review.

- [ ] **Step 1: Write the durable implementation note**

Document these exact facts:

- the countdown is an optional synchronized winding-set pace clock, not a physical roll-change timestamp or production record;
- late acknowledgement uses click time as the previous/start anchor and sets exactly one interval from that click;
- direct next-time override remains editable, while a later quick acknowledgement uses its own click time as the new anchor;
- machine/card ownership and every clear condition;
- the paused/resolved/unresolved state table, including yellow paused `00:00` and red resumed-unresolved `00:00`;
- exact storage key and version-1 JSON fields;
- local-browser/origin limits, storage-event tab sync, refresh behavior, and browser-storage loss consequence;
- no SQLite backup, report, version, re-import, shift, roll, pallet, recipe, print, or timing coupling;
- operator recovery: open the editor to correct a mistaken quick action, use Clear to stop tracking, and recreate the schedule after browser storage loss;
- exact Node, pytest, server, and Playwright verification commands and artifact path.

- [ ] **Step 2: Update authoritative and task documentation**

In `README.md`, add the optional pace clock under workstation behavior and remove only the per-machine roll-change timer bullet from Deferred Functionality. Keep future automatic machine integration and historical reporting out of scope.

In `v2-files/PLAN.md`, change Task 10 status to complete only after all tests and browser checks pass; record the browser-local/no-SQLite boundary and the exact verification evidence. Do not alter the user's Task 13 edits.

In the Task 10 specification, change the status to implemented/verified and replace its implementation handoff with links to this plan and the durable note. Preserve the approved examples and all behavior text.

- [ ] **Step 3: Inspect the actual finished diff for migration impact**

Run:

```bash
git diff --name-status
git diff -- app/db.py app/migrations.py app/schema.py app/constants.py
rg -n "CREATE TABLE|ALTER TABLE|CREATE INDEX|schema_migrations|Migration\(" app README.md v2-files docs tests scripts
```

Expected Task 10 decision, provided the finished diff still matches this plan:

```text
Migration assessment
- Decision: No migration
- Why: The feature adds only HTML/CSS/JavaScript, browser-local versioned schedule records, tests, scripts, and documentation; it changes no SQLite structure or stored production-data meaning.
- Existing production data affected: none
- Proposed migration: none
- Transformation: no values changed
- Unknowns or ambiguous rows: none known for Task 10 browser-local state
- Required tests: temporary-database regression tests plus Node schedule tests and guarded Playwright lifecycle/refresh checks
- Production snapshot needed now: No
- Deployment constraint: deploy the static/template change with the application after the repository's existing M001 profile and final release-candidate gates; browser-local countdowns are not restored from SQLite backups
```

If the actual diff adds or reinterprets persistent data, stop and reclassify from the diff; do not force the expected no-migration result. Update the `v2-files/AGENTS.md` assessment log only when its user trigger has been invoked.

- [ ] **Step 4: Run final syntax, focused, and full automated verification**

Run:

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
```

Expected: every command exits zero. Record exact test counts and elapsed times from the actual output rather than copying historical counts.

- [ ] **Step 5: Recreate and rerun the final live workflow from a clean fixture**

Start from a freshly recreated guarded fixture and rerun the Task 10 verifier at both viewports using the Task 3 commands. Confirm the JSON summary identifies the guarded fixture database, every assertion passes, screenshots are current, and no production/runtime database path appears in the summary.

- [ ] **Step 6: Review the complete feature against the approved specification**

Check every specification heading against code/tests: purpose and one-schedule ownership; calculation; all countdown states; controls; editor; validation; machine-card display; Task 11 boundary; persistence and tab sync; conflict safety; accessibility; testing; and all out-of-scope exclusions. Search for accidental backend or production-data coupling:

```bash
rg -n "roll.change|roll_change|countdown" app tests scripts docs README.md v2-files
git diff --stat
git status --short
```

Confirm unrelated existing changes in `v2-files/AGENTS.md`, `v2-files/PLAN.md`, and `v2-files/TASK-13-BACKUP-RESILIENCE.md` were preserved and not staged.

- [ ] **Step 7: Final review checkpoint and conditional documentation commit**

Run:

```bash
git diff --check
git diff -- README.md v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md docs/implementation-notes/roll-change-countdown.md docs/superpowers/plans/2026-07-27-roll-change-countdown.md
git status --short
```

If and only if the user has explicitly authorized commits, stage only reviewed Task 10 paths and commit:

```bash
git add README.md v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md docs/implementation-notes/roll-change-countdown.md docs/superpowers/plans/2026-07-27-roll-change-countdown.md
git commit -m "Document roll-change countdown workflow"
```

Do not stage the user's unrelated `v2-files/PLAN.md` or Task 13 work, or any runtime database, `.test-runtime`, `artifacts`, `node_modules`, screenshot, trace, video, or Playwright-report path.

---

## Execution Checkpoints

1. Stop after Task 1 for schedule/state-model review.
2. Stop after Task 2 for server-rendered UI hierarchy review.
3. Stop after Task 3 for the first complete operator workflow review.
4. Stop after Task 4 for live lifecycle/accessibility evidence review.
5. Stop after Task 5 with the final diff, exact test evidence, screenshots, and migration recommendation. Do not commit, deploy, or touch a production/runtime database without separate user authorization.
