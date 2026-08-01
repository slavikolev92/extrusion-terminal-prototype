import test from "node:test";
import assert from "node:assert/strict";

import {
  STORAGE_KEY_PREFIX,
  advanceSchedule,
  buildSchedule,
  calculateNextExpected,
  clearMismatchedSchedules,
  countdownView,
  decodeSchedule,
  formatNextExpected,
  formatRemaining,
  joinLocalDateTimeParts,
  loadSchedule,
  parseIntervalMinutes,
  parseOperatorLocalMinute,
  readSchedule,
  reconcileCardStatus,
  saveSchedule,
  storageKey,
  splitLocalDateTimeParts,
  toLocalDateTimeInputValue,
  validateEditorValues,
} from "../../app/static/js/roll_change_countdown_core.mjs";

const minute = 60_000;
const localAt = (year, month, day, hour, minutes, seconds = 0) =>
  new Date(year, month - 1, day, hour, minutes, seconds, 0).getTime();

class MemoryStorage {
  constructor() { this.values = new Map(); }
  get length() { return this.values.size; }
  key(index) { return Array.from(this.values.keys())[index] ?? null; }
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

test("initial schedule calculation uses the entered two-hour interval", () => {
  assert.equal(calculateNextExpected(localAt(2026, 7, 27, 12, 0), 120), localAt(2026, 7, 27, 14, 0));
});

test("initial schedule calculation crosses midnight with absolute local time", () => {
  assert.equal(calculateNextExpected(localAt(2026, 7, 27, 23, 30), 120), localAt(2026, 7, 28, 1, 30));
});

test("stable date, hour, and minute controls round-trip one local minute", () => {
  assert.deepEqual(splitLocalDateTimeParts(localAt(2026, 7, 27, 4, 5)), {
    dateValue: "2026-07-27",
    hourValue: "04",
    minuteValue: "05",
  });
  assert.equal(joinLocalDateTimeParts("2026-07-27", "04", "05"), "2026-07-27T04:05");
  assert.equal(joinLocalDateTimeParts("", "04", "05"), "");
  assert.equal(joinLocalDateTimeParts("2026-07-27", "24", "05"), "");
});

test("acknowledgement advances scheduled cadence to the first future interval", () => {
  for (const [clickedAt, expectedPrevious, expectedNext] of [
    [localAt(2026, 7, 27, 13, 50), localAt(2026, 7, 27, 14, 0), localAt(2026, 7, 27, 16, 0)],
    [localAt(2026, 7, 27, 14, 0), localAt(2026, 7, 27, 14, 0), localAt(2026, 7, 27, 16, 0)],
    [localAt(2026, 7, 27, 14, 20), localAt(2026, 7, 27, 14, 0), localAt(2026, 7, 27, 16, 0)],
    [localAt(2026, 7, 27, 16, 15), localAt(2026, 7, 27, 16, 0), localAt(2026, 7, 27, 18, 0)],
  ]) {
    const advanced = advanceSchedule(runningSchedule(), "running", clickedAt);
    assert.equal(advanced.previousChangeAtMs, expectedPrevious);
    assert.equal(advanced.nextExpectedAtMs, expectedNext);
  }
});

test("successive acknowledgement continues from the schedule saved by the prior click", () => {
  const firstClick = localAt(2026, 7, 27, 14, 20);
  const secondClick = localAt(2026, 7, 27, 14, 21);
  const first = advanceSchedule(runningSchedule(), "running", firstClick);
  const second = advanceSchedule(first, "running", secondClick);
  assert.equal(first.previousChangeAtMs, localAt(2026, 7, 27, 14, 0));
  assert.equal(first.nextExpectedAtMs, localAt(2026, 7, 27, 16, 0));
  assert.equal(second.previousChangeAtMs, localAt(2026, 7, 27, 16, 0));
  assert.equal(second.nextExpectedAtMs, localAt(2026, 7, 27, 18, 0));
});

test("scheduled acknowledgement catches up across midnight", () => {
  const schedule = buildSchedule({
    machineId: 2,
    cardId: 22,
    previousChangeAtMs: localAt(2026, 7, 27, 21, 30),
    intervalMinutes: 120,
    nextExpectedAtMs: localAt(2026, 7, 27, 23, 30),
    status: "running",
    nowMs: localAt(2026, 7, 27, 21, 30),
  });
  const advanced = advanceSchedule(schedule, "running", localAt(2026, 7, 28, 0, 10));
  assert.equal(advanced.previousChangeAtMs, localAt(2026, 7, 27, 23, 30));
  assert.equal(advanced.nextExpectedAtMs, localAt(2026, 7, 28, 1, 30));
});

test("running indicator thresholds and rounded display use exact milliseconds", () => {
  const schedule = runningSchedule();
  for (const [remainingMs, tone, display] of [
    [15 * minute + 1, "normal", "00:16"],
    [15 * minute, "warning", "00:15"],
    [5 * minute + 1, "warning", "00:06"],
    [5 * minute, "urgent", "00:05"],
    [1, "urgent", "00:01"],
  ]) {
    const view = countdownView(
      schedule,
      "running",
      schedule.nextExpectedAtMs - remainingMs,
    );
    assert.deepEqual(
      { tone: view.tone, display: view.display, due: view.due },
      { tone, display, due: false },
    );
  }

  for (const nowMs of [schedule.nextExpectedAtMs, schedule.nextExpectedAtMs + minute]) {
    const view = countdownView(schedule, "running", nowMs);
    assert.deepEqual(
      { tone: view.tone, display: view.display, due: view.due },
      { tone: "urgent", display: "00:00", due: true },
    );
  }
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
  assert.equal(resolved.previousChangeAtMs, localAt(2026, 7, 27, 14, 0));
  assert.equal(resolved.nextExpectedAtMs, localAt(2026, 7, 27, 16, 0));
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

test("acknowledgement continues from a manual next-time override", () => {
  const values = validateEditorValues({
    previousValue: "2026-07-27T14:00", hoursValue: "2", minutesValue: "0", nextValue: "2026-07-27T16:30",
  }, localAt(2026, 7, 27, 14, 20));
  assert.equal(values.ok, true);
  const schedule = buildSchedule({ machineId: 2, cardId: 22, ...values.value, status: "running", nowMs: localAt(2026, 7, 27, 14, 20) });
  const advanced = advanceSchedule(schedule, "running", localAt(2026, 7, 27, 16, 50));
  assert.equal(advanced.previousChangeAtMs, localAt(2026, 7, 27, 16, 30));
  assert.equal(advanced.nextExpectedAtMs, localAt(2026, 7, 27, 18, 30));
});

test("time-only values resolve to the most recent non-future local occurrence", () => {
  const now = localAt(2026, 7, 28, 0, 10);
  assert.equal(parseOperatorLocalMinute("23:55", now), localAt(2026, 7, 27, 23, 55));
  assert.equal(parseOperatorLocalMinute("00:05", now), localAt(2026, 7, 28, 0, 5));
});

test("local input and labels preserve local calendar boundaries", () => {
  const midnight = localAt(2026, 7, 28, 0, 5);
  assert.equal(toLocalDateTimeInputValue(midnight), "2026-07-28T00:05");
  assert.equal(joinLocalDateTimeParts("2026-07-28", "0", "5"), "2026-07-28T00:05");
  assert.equal(joinLocalDateTimeParts("2026-07-28", "23", "59"), "2026-07-28T23:59");
  assert.equal(joinLocalDateTimeParts("2026-07-28", "24", "00"), "");
  assert.equal(joinLocalDateTimeParts("2026-07-28", "12", "60"), "");
  assert.equal(joinLocalDateTimeParts("2026-07-28", "1a", "05"), "");
  assert.equal(formatNextExpected(localAt(2026, 7, 27, 23, 55), midnight), "27.07 23:55");
  assert.equal(formatNextExpected(localAt(2026, 7, 28, 1, 30), midnight), "01:30");
});

test("editor rejects interval bounds, zero combined interval, impossible times, and reversed dates", () => {
  assert.deepEqual(parseIntervalMinutes("24", "0"), { ok: false, errors: { hours: "Часовете трябва да са цяло число от 0 до 23." } });
  assert.deepEqual(parseIntervalMinutes("2", "60"), { ok: false, errors: { minutes: "Минутите трябва да са цяло число от 0 до 59." } });
  assert.deepEqual(parseIntervalMinutes("0", "0"), { ok: false, errors: { form: "Изберете интервал поне 1 минута." } });
  assert.equal(parseOperatorLocalMinute("2026-02-30T12:00", localAt(2026, 2, 1, 0, 0)), null);
  assert.deepEqual(
    validateEditorValues({ previousValue: "2026-07-27T14:00", hoursValue: "2", minutesValue: "0", nextValue: "2026-07-27T14:00" }, localAt(2026, 7, 27, 14, 0)),
    { ok: false, errors: { next: "Очакваният час трябва да е след началния." } },
  );
});

test("paused acknowledgement retains a fresh frozen countdown and editor replacement resets pause resolution", () => {
  const paused = reconcileCardStatus(runningSchedule(), "paused", localAt(2026, 7, 27, 13, 50));
  const advanced = advanceSchedule(paused, "paused", localAt(2026, 7, 27, 14, 5));
  assert.equal(advanced.previousChangeAtMs, localAt(2026, 7, 27, 14, 0));
  assert.equal(advanced.nextExpectedAtMs, localAt(2026, 7, 27, 16, 0));
  assert.equal(advanced.frozenRemainingMs, 115 * minute);
  assert.equal(advanced.pauseNeedsResolution, false);
  const replacement = buildSchedule({
    machineId: 2, cardId: 22, previousChangeAtMs: localAt(2026, 7, 27, 13, 0), intervalMinutes: 120,
    nextExpectedAtMs: localAt(2026, 7, 27, 15, 0), status: "paused", nowMs: localAt(2026, 7, 27, 13, 30),
  });
  assert.equal(replacement.frozenRemainingMs, 90 * minute);
  assert.equal(replacement.pauseNeedsResolution, false);
});

test("untrackable status clears a schedule and positive displays can exceed a day", () => {
  assert.equal(reconcileCardStatus(runningSchedule(), "completed", localAt(2026, 7, 27, 12, 0)), null);
  assert.equal(formatRemaining(25 * 60 * minute), "25:00");
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

test("steady-state reads leave a valid different-card schedule untouched", () => {
  const storage = new MemoryStorage();
  const replacement = { ...runningSchedule(), cardId: 99 };
  storage.setItem(storageKey(2), JSON.stringify(replacement));

  assert.equal(readSchedule(storage, 2, 22), null);
  assert.equal(storage.getItem(storageKey(2)), JSON.stringify(replacement));
});

test("storage removes unrenderable timestamps and contradictory lifecycle shapes", () => {
  const storage = new MemoryStorage();
  const key = storageKey(2);
  const base = runningSchedule();
  const invalidSchedules = [
    {
      ...base,
      previousChangeAtMs: 8_640_000_000_000_001,
      nextExpectedAtMs: 8_640_000_000_001_001,
    },
    { ...base, frozenRemainingMs: 1, pauseNeedsResolution: false },
    { ...base, frozenRemainingMs: null, pauseNeedsResolution: true },
    { ...base, observedStatus: "paused", frozenRemainingMs: null, pauseNeedsResolution: false },
  ];

  for (const candidate of invalidSchedules) {
    storage.setItem(key, JSON.stringify(candidate));
    assert.equal(loadSchedule(storage, 2, 22), null);
    assert.equal(storage.getItem(key), null);
  }
});

test("storage accepts every lifecycle shape produced by the state machine", () => {
  const base = runningSchedule();
  const validSchedules = [
    base,
    { ...base, frozenRemainingMs: 5 * minute, pauseNeedsResolution: true },
    { ...base, observedStatus: "paused", frozenRemainingMs: 5 * minute, pauseNeedsResolution: true },
    { ...base, observedStatus: "paused", frozenRemainingMs: 5 * minute, pauseNeedsResolution: false },
  ];

  for (const candidate of validSchedules) {
    assert.deepEqual(decodeSchedule(JSON.stringify(candidate), 2, 22), candidate);
  }
});

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
