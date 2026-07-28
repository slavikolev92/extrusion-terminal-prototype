export const STORAGE_VERSION = 1;
export const STORAGE_KEY_PREFIX = "extrusion-terminal.roll-change.v1.machine.";

const MINUTE_MS = 60_000;
const MAX_INTERVAL_MINUTES = 23 * 60 + 59;
const TRACKABLE = new Set(["running", "paused"]);
const DATE_TIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/;
const TIME_PATTERN = /^(\d{2}):(\d{2})$/;
const DIGITS_PATTERN = /^\d+$/;

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
  const intervalMs = schedule.intervalMinutes * MINUTE_MS;
  const intervalsToAdvance = Math.max(
    1,
    Math.floor((nowMs - schedule.nextExpectedAtMs) / intervalMs) + 1,
  );
  const previousChangeAtMs = schedule.nextExpectedAtMs
    + (intervalsToAdvance - 1) * intervalMs;
  const nextExpectedAtMs = calculateNextExpected(
    previousChangeAtMs,
    schedule.intervalMinutes,
  );
  return {
    ...schedule,
    previousChangeAtMs,
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

export function parseOperatorLocalMinute(value, nowMs) {
  if (!Number.isFinite(nowMs)) return null;
  const dateTimeMatch = typeof value === "string" && value.match(DATE_TIME_PATTERN);
  const timeMatch = typeof value === "string" && value.match(TIME_PATTERN);
  if (!dateTimeMatch && !timeMatch) return null;

  let year;
  let month;
  let day;
  let hours;
  let minutes;
  if (dateTimeMatch) {
    [, year, month, day, hours, minutes] = dateTimeMatch;
  } else {
    [, hours, minutes] = timeMatch;
    const now = new Date(nowMs);
    year = String(now.getFullYear());
    month = String(now.getMonth() + 1);
    day = String(now.getDate());
  }

  const candidate = new Date(Number(year), Number(month) - 1, Number(day), Number(hours), Number(minutes), 0, 0);
  if (
    candidate.getFullYear() !== Number(year)
    || candidate.getMonth() !== Number(month) - 1
    || candidate.getDate() !== Number(day)
    || candidate.getHours() !== Number(hours)
    || candidate.getMinutes() !== Number(minutes)
  ) return null;

  if (!dateTimeMatch && candidate.getTime() > nowMs) {
    const previousDay = new Date(candidate.getFullYear(), candidate.getMonth(), candidate.getDate() - 1, Number(hours), Number(minutes), 0, 0);
    const expectedPreviousDate = new Date(candidate.getFullYear(), candidate.getMonth(), candidate.getDate() - 1);
    if (
      previousDay.getFullYear() !== expectedPreviousDate.getFullYear()
      || previousDay.getMonth() !== expectedPreviousDate.getMonth()
      || previousDay.getDate() !== expectedPreviousDate.getDate()
      || previousDay.getHours() !== Number(hours)
      || previousDay.getMinutes() !== Number(minutes)
    ) return null;
    return previousDay.getTime();
  }
  return candidate.getTime();
}

export function toLocalDateTimeInputValue(valueMs) {
  const date = new Date(valueMs);
  if (Number.isNaN(date.getTime())) throw new TypeError("Invalid local timestamp");
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}T${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function splitLocalDateTimeParts(valueMs) {
  const [dateValue, timeValue] = toLocalDateTimeInputValue(valueMs).split("T");
  const [hourValue, minuteValue] = timeValue.split(":");
  return { dateValue, hourValue, minuteValue };
}

export function joinLocalDateTimeParts(dateValue, hourValue, minuteValue) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateValue ?? "")) return "";
  if (!/^\d{1,2}$/.test(hourValue ?? "") || Number(hourValue) > 23) return "";
  if (!/^\d{1,2}$/.test(minuteValue ?? "") || Number(minuteValue) > 59) return "";
  return `${dateValue}T${String(hourValue).padStart(2, "0")}:${String(minuteValue).padStart(2, "0")}`;
}

export function formatNextExpected(nextExpectedAtMs, nowMs) {
  const expected = new Date(nextExpectedAtMs);
  const now = new Date(nowMs);
  if (Number.isNaN(expected.getTime()) || Number.isNaN(now.getTime())) throw new TypeError("Invalid local timestamp");
  const time = `${String(expected.getHours()).padStart(2, "0")}:${String(expected.getMinutes()).padStart(2, "0")}`;
  if (
    expected.getFullYear() === now.getFullYear()
    && expected.getMonth() === now.getMonth()
    && expected.getDate() === now.getDate()
  ) return time;
  return `${String(expected.getDate()).padStart(2, "0")}.${String(expected.getMonth() + 1).padStart(2, "0")} ${time}`;
}

export function parseIntervalMinutes(hoursValue, minutesValue) {
  if (!isBoundedBaseTenInteger(hoursValue, 23)) {
    return { ok: false, errors: { hours: "Часовете трябва да са цяло число от 0 до 23." } };
  }
  if (!isBoundedBaseTenInteger(minutesValue, 59)) {
    return { ok: false, errors: { minutes: "Минутите трябва да са цяло число от 0 до 59." } };
  }
  const intervalMinutes = Number(hoursValue) * 60 + Number(minutesValue);
  if (intervalMinutes === 0) {
    return { ok: false, errors: { form: "Изберете интервал поне 1 минута." } };
  }
  return { ok: true, value: intervalMinutes };
}

export function validateEditorValues(values, nowMs) {
  const errors = {};
  const interval = parseIntervalMinutes(values.hoursValue, values.minutesValue);
  if (!interval.ok) Object.assign(errors, interval.errors);

  const previousChangeAtMs = parseOperatorLocalMinute(values.previousValue, nowMs);
  if (previousChangeAtMs === null) errors.previous = "Въведете валиден начален час.";

  const nextExpectedAtMs = parseOperatorLocalMinute(values.nextValue, nowMs);
  if (nextExpectedAtMs === null) errors.next = "Въведете валиден очакван час.";
  else if (previousChangeAtMs !== null && nextExpectedAtMs <= previousChangeAtMs) {
    errors.next = "Очакваният час трябва да е след началния.";
  }

  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return {
    ok: true,
    value: { previousChangeAtMs, intervalMinutes: interval.value, nextExpectedAtMs },
  };
}

export function decodeSchedule(raw, machineId, cardId) {
  if (typeof raw !== "string") return null;
  try {
    return validateScheduleObject(JSON.parse(raw), machineId, cardId);
  } catch {
    return null;
  }
}

export function loadSchedule(storage, machineId, cardId) {
  const key = storageKey(machineId);
  const raw = storage.getItem(key);
  if (raw === null) return null;
  const schedule = readSchedule(storage, machineId, cardId);
  if (!schedule) storage.removeItem(key);
  return schedule;
}

export function readSchedule(storage, machineId, cardId) {
  return decodeSchedule(storage.getItem(storageKey(machineId)), machineId, cardId);
}

export function saveSchedule(storage, schedule) {
  const valid = validateScheduleObject(schedule, schedule?.machineId, schedule?.cardId);
  if (!valid) throw new TypeError("Invalid roll-change schedule");
  storage.setItem(storageKey(valid.machineId), JSON.stringify(valid));
}

export function clearSchedule(storage, machineId) {
  storage.removeItem(storageKey(machineId));
}

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

function isBoundedBaseTenInteger(value, maximum) {
  return typeof value === "string" && DIGITS_PATTERN.test(value) && Number.isSafeInteger(Number(value)) && Number(value) <= maximum;
}

function validateScheduleObject(candidate, machineId, cardId) {
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return null;
  if (candidate.schemaVersion !== STORAGE_VERSION) return null;
  if (!isPositiveSafeInteger(candidate.machineId) || !isPositiveSafeInteger(candidate.cardId)) return null;
  if (candidate.machineId !== machineId || candidate.cardId !== cardId) return null;
  if (!isRenderableTimestamp(candidate.previousChangeAtMs) || !isRenderableTimestamp(candidate.nextExpectedAtMs)) return null;
  if (!isFiniteInteger(candidate.intervalMinutes) || candidate.intervalMinutes < 1 || candidate.intervalMinutes > MAX_INTERVAL_MINUTES) return null;
  if (candidate.nextExpectedAtMs <= candidate.previousChangeAtMs) return null;
  if (!TRACKABLE.has(candidate.observedStatus)) return null;
  if (candidate.frozenRemainingMs !== null && (!isFiniteInteger(candidate.frozenRemainingMs) || candidate.frozenRemainingMs < 0)) return null;
  if (typeof candidate.pauseNeedsResolution !== "boolean") return null;
  if (candidate.observedStatus === "paused" && candidate.frozenRemainingMs === null) return null;
  if (
    candidate.observedStatus === "running"
    && candidate.pauseNeedsResolution !== (candidate.frozenRemainingMs !== null)
  ) return null;
  return candidate;
}

function isPositiveSafeInteger(value) {
  return Number.isSafeInteger(value) && value > 0;
}

function isFiniteInteger(value) {
  return Number.isFinite(value) && Number.isInteger(value);
}

function isRenderableTimestamp(value) {
  return isFiniteInteger(value) && !Number.isNaN(new Date(value).getTime());
}
