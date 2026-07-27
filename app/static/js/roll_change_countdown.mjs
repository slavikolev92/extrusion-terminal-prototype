import {
  STORAGE_KEY_PREFIX,
  advanceSchedule,
  buildSchedule,
  calculateNextExpected,
  clearMismatchedSchedules,
  clearSchedule,
  countdownView,
  joinLocalDateTimeParts,
  parseIntervalMinutes,
  parseOperatorLocalMinute,
  readSchedule,
  reconcileCardStatus,
  saveSchedule,
  splitLocalDateTimeParts,
  toLocalDateTimeInputValue,
  validateEditorValues,
} from "./roll_change_countdown_core.mjs";


const TRACKABLE = new Set(["running", "paused"]);
const TONE_CLASSES = ["normal", "warning", "urgent", "paused", "resync"];
const FOCUSABLE_SELECTOR = [
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "a[href]",
  "[tabindex]:not([tabindex='-1'])",
].join(",");


export function bootstrapRollChangeCountdown({
  documentObject = document,
  windowObject = window,
  now = () => Date.now(),
  intervalFactory = (callback) => windowObject.setInterval(callback, 1_000),
} = {}) {
  const storage = windowObject.localStorage;
  const contexts = new Map();
  for (const host of documentObject.querySelectorAll("[data-roll-change-machine]")) {
    const machineId = Number(host.dataset.machineId);
    const cardId = Number(host.dataset.cardId);
    if (!Number.isSafeInteger(machineId) || machineId <= 0) continue;
    contexts.set(machineId, {
      cardId,
      status: host.dataset.cardStatus || "",
      host,
    });
  }

  const controls = documentObject.querySelector("[data-roll-change-controls]");
  const selectedMachineId = Number(controls?.dataset.machineId);
  const selectedCardId = Number(controls?.dataset.cardId);
  const selectedStatus = controls?.dataset.cardStatus || "";
  const openControl = controls?.querySelector("[data-roll-change-open]") ?? null;
  const controlValue = controls?.querySelector("[data-roll-change-control-value]") ?? null;
  const advanceControl = controls?.querySelector("[data-roll-change-advance]") ?? null;

  const overlay = documentObject.querySelector("[data-roll-change-overlay]");
  const dialog = overlay?.querySelector("[data-roll-change-dialog]") ?? null;
  const form = overlay?.querySelector("[data-roll-change-form]") ?? null;
  const previousInput = form?.querySelector("[data-roll-change-previous]") ?? null;
  const previousDateInput = form?.querySelector("[data-roll-change-previous-date]") ?? null;
  const previousHourInput = form?.querySelector("[data-roll-change-previous-hour]") ?? null;
  const previousMinuteInput = form?.querySelector("[data-roll-change-previous-minute]") ?? null;
  const hoursInput = form?.querySelector("[data-roll-change-hours]") ?? null;
  const minutesInput = form?.querySelector("[data-roll-change-minutes]") ?? null;
  const nextInput = form?.querySelector("[data-roll-change-next]") ?? null;
  const nextDateInput = form?.querySelector("[data-roll-change-next-date]") ?? null;
  const nextHourInput = form?.querySelector("[data-roll-change-next-hour]") ?? null;
  const nextMinuteInput = form?.querySelector("[data-roll-change-next-minute]") ?? null;
  const intervalSummary = form?.querySelector("[data-roll-change-interval-summary]") ?? null;
  const restartControl = form?.querySelector("[data-roll-change-restart]") ?? null;
  const clearControl = form?.querySelector("[data-roll-change-clear]") ?? null;
  const cancelControl = form?.querySelector("[data-roll-change-cancel]") ?? null;
  const closeControl = overlay?.querySelector("[data-roll-change-close]") ?? null;
  const errorSlots = new Map(
    Array.from(form?.querySelectorAll("[data-roll-change-error-for]") ?? [], (slot) => [
      slot.dataset.rollChangeErrorFor,
      slot,
    ]),
  );

  let savedSchedule = null;
  let returnFocus = null;
  let backdropPressStarted = false;
  let backdropPressEnded = false;
  let lifecycleReloadRequired = false;
  let synchronizedSelectedStatus = null;
  const listeners = [];

  function listen(target, type, callback) {
    if (!target) return;
    target.addEventListener(type, callback);
    listeners.push(() => target.removeEventListener(type, callback));
  }

  function matchingSchedule(machineId, cardId) {
    if (!Number.isSafeInteger(machineId) || machineId <= 0) return null;
    if (!Number.isSafeInteger(cardId) || cardId <= 0) return null;
    return readSchedule(storage, machineId, cardId);
  }

  function hasNonMatchingStoredRecord(machineId, cardId) {
    if (!Number.isSafeInteger(machineId) || machineId <= 0) return false;
    return (
      storage.getItem(`${STORAGE_KEY_PREFIX}${machineId}`) !== null
      && matchingSchedule(machineId, cardId) === null
    );
  }

  function renderMachine(context, schedule, currentMs) {
    const timer = context.host.querySelector("[data-roll-change-machine-timer]");
    if (!timer) return;
    const renderedStatus = (
      lifecycleReloadRequired
      && context.cardId === selectedCardId
      && synchronizedSelectedStatus
    ) ? synchronizedSelectedStatus : context.status;
    if (!schedule || !TRACKABLE.has(renderedStatus)) {
      timer.hidden = true;
      timer.textContent = "";
      timer.removeAttribute("aria-label");
      timer.classList.remove(...TONE_CLASSES);
      return;
    }
    const view = countdownView(schedule, renderedStatus, currentMs);
    timer.hidden = false;
    timer.textContent = view.display;
    timer.classList.remove(...TONE_CLASSES);
    timer.classList.add(view.tone);
    timer.setAttribute(
      "aria-label",
      view.due
        ? `Машина ${schedule.machineId}, смяната на ролките е дължима`
        : `Машина ${schedule.machineId}, смяна на ролките след ${view.display}`,
    );
  }

  function renderSelected(schedule, currentMs) {
    if (!openControl || !controlValue || !advanceControl) return;
    const renderedStatus = synchronizedSelectedStatus ?? selectedStatus;
    if (!schedule || !TRACKABLE.has(renderedStatus)) {
      controlValue.textContent = "Смяна на ролка";
      advanceControl.hidden = true;
      openControl.classList.remove(...TONE_CLASSES);
      openControl.setAttribute("aria-label", `Настрой смяна на ролките за машина ${selectedMachineId}`);
      return;
    }
    const view = countdownView(schedule, renderedStatus, currentMs);
    controlValue.textContent = view.display;
    advanceControl.hidden = false;
    openControl.classList.remove(...TONE_CLASSES);
    openControl.classList.add(view.tone);
    openControl.setAttribute(
      "aria-label",
      view.due
        ? `Редактирай смяната на ролките за машина ${selectedMachineId}; смяната е дължима; следваща ${view.nextExpectedLabel}`
        : `Редактирай смяната на ролките за машина ${selectedMachineId}; остават ${view.display}, следваща ${view.nextExpectedLabel}`,
    );
  }

  function renderAll() {
    const currentMs = now();
    for (const [machineId, context] of contexts) {
      renderMachine(context, matchingSchedule(machineId, context.cardId), currentMs);
    }
    renderSelected(matchingSchedule(selectedMachineId, selectedCardId), currentMs);
  }

  function reconcileAndPersist(machineId, context, currentMs) {
    if (!context || !TRACKABLE.has(context.status)) return null;
    const record = matchingSchedule(machineId, context.cardId);
    if (!record) return null;
    const reconciled = reconcileCardStatus(record, context.status, currentMs);
    if (reconciled && reconciled !== record) saveSchedule(storage, reconciled);
    return reconciled;
  }

  function refresh() {
    renderAll();
  }

  function clearErrors() {
    for (const slot of errorSlots.values()) slot.textContent = "";
    for (const input of [
      previousDateInput,
      previousHourInput,
      previousMinuteInput,
      hoursInput,
      minutesInput,
      nextDateInput,
      nextHourInput,
      nextMinuteInput,
    ]) input?.removeAttribute("aria-invalid");
  }

  function renderErrors(errors) {
    clearErrors();
    for (const [name, message] of Object.entries(errors)) {
      const slot = errorSlots.get(name);
      if (slot) slot.textContent = message;
      const targets = {
        previous: [previousDateInput, previousHourInput, previousMinuteInput],
        hours: [hoursInput],
        minutes: [minutesInput],
        next: [nextDateInput, nextHourInput, nextMinuteInput],
        form: [hoursInput, minutesInput],
      }[name] ?? [];
      for (const target of targets) target?.setAttribute("aria-invalid", "true");
    }
  }

  function writeDateTimeParts(canonicalInput, dateInput, hourInput, minuteInput, valueMs) {
    if (!canonicalInput || !dateInput || !hourInput || !minuteInput) return;
    if (valueMs === null) {
      canonicalInput.value = "";
      dateInput.value = "";
      hourInput.value = "00";
      minuteInput.value = "00";
      return;
    }
    const parts = splitLocalDateTimeParts(valueMs);
    canonicalInput.value = toLocalDateTimeInputValue(valueMs);
    dateInput.value = parts.dateValue;
    hourInput.value = parts.hourValue;
    minuteInput.value = parts.minuteValue;
  }

  function syncDateTimeParts(canonicalInput, dateInput, hourInput, minuteInput) {
    if (!canonicalInput || !dateInput || !hourInput || !minuteInput) return "";
    const value = joinLocalDateTimeParts(
      dateInput.value,
      hourInput.value,
      minuteInput.value,
    );
    canonicalInput.value = value;
    return value;
  }

  function updateIntervalSummary() {
    if (!intervalSummary || !hoursInput || !minutesInput) return;
    const result = parseIntervalMinutes(hoursInput.value, minutesInput.value);
    if (!result.ok) {
      intervalSummary.textContent = "валиден интервал";
      return;
    }
    const hours = Math.floor(result.value / 60);
    const minutes = result.value % 60;
    intervalSummary.textContent = `${hours} ч. и ${minutes} мин.`;
  }

  function normalizeNumericInput(input, maximum) {
    if (!input || !/^\d{1,2}$/.test(input.value)) return;
    if (Number(input.value) > maximum) return;
    input.value = input.value.padStart(2, "0");
  }

  function recalculateDraft() {
    if (!previousInput || !hoursInput || !minutesInput || !nextInput) return;
    updateIntervalSummary();
    const previousValue = syncDateTimeParts(
      previousInput,
      previousDateInput,
      previousHourInput,
      previousMinuteInput,
    );
    const previousMs = parseOperatorLocalMinute(previousValue, now());
    const intervalResult = parseIntervalMinutes(hoursInput.value, minutesInput.value);
    if (previousMs !== null && intervalResult.ok) {
      writeDateTimeParts(
        nextInput,
        nextDateInput,
        nextHourInput,
        nextMinuteInput,
        calculateNextExpected(previousMs, intervalResult.value),
      );
    }
  }

  function hasOpenRollCorrection() {
    return Boolean(documentObject.querySelector(".roll-row.is-editing"));
  }

  function openEditor(event) {
    if (lifecycleReloadRequired) return;
    if (hasOpenRollCorrection()) return;
    if (!overlay || !previousInput || !previousDateInput || !hoursInput || !minutesInput || !nextInput) return;
    returnFocus = event?.currentTarget ?? openControl;
    savedSchedule = matchingSchedule(selectedMachineId, selectedCardId);
    if (savedSchedule) {
      writeDateTimeParts(previousInput, previousDateInput, previousHourInput, previousMinuteInput, savedSchedule.previousChangeAtMs);
      hoursInput.value = String(Math.floor(savedSchedule.intervalMinutes / 60)).padStart(2, "0");
      minutesInput.value = String(savedSchedule.intervalMinutes % 60).padStart(2, "0");
      writeDateTimeParts(nextInput, nextDateInput, nextHourInput, nextMinuteInput, savedSchedule.nextExpectedAtMs);
    } else {
      writeDateTimeParts(previousInput, previousDateInput, previousHourInput, previousMinuteInput, now());
      hoursInput.value = "00";
      minutesInput.value = "00";
      writeDateTimeParts(nextInput, nextDateInput, nextHourInput, nextMinuteInput, null);
    }
    updateIntervalSummary();
    clearErrors();
    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    openControl?.setAttribute("aria-expanded", "true");
    previousDateInput.focus();
  }

  function closeEditor({ restoreFocus = true } = {}) {
    if (!overlay) return;
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    openControl?.setAttribute("aria-expanded", "false");
    savedSchedule = null;
    if (restoreFocus) returnFocus?.focus();
    returnFocus = null;
  }

  function submitEditor(event) {
    event.preventDefault();
    if (lifecycleReloadRequired) return;
    if (!previousInput || !hoursInput || !minutesInput || !nextInput) return;
    if (hasNonMatchingStoredRecord(selectedMachineId, selectedCardId)) {
      closeEditor();
      renderAll();
      return;
    }
    syncDateTimeParts(previousInput, previousDateInput, previousHourInput, previousMinuteInput);
    syncDateTimeParts(nextInput, nextDateInput, nextHourInput, nextMinuteInput);
    const result = validateEditorValues({
      previousValue: previousInput.value,
      hoursValue: hoursInput.value,
      minutesValue: minutesInput.value,
      nextValue: nextInput.value,
    }, now());
    if (!result.ok) {
      renderErrors(result.errors);
      return;
    }
    const schedule = buildSchedule({
      machineId: selectedMachineId,
      cardId: selectedCardId,
      ...result.value,
      status: selectedStatus,
      nowMs: now(),
    });
    saveSchedule(storage, schedule);
    savedSchedule = schedule;
    closeEditor();
    renderAll();
  }

  function restartDraft() {
    if (!previousInput) return;
    writeDateTimeParts(previousInput, previousDateInput, previousHourInput, previousMinuteInput, now());
    recalculateDraft();
  }

  function clearEditorSchedule() {
    if (lifecycleReloadRequired) return;
    if (matchingSchedule(selectedMachineId, selectedCardId)) {
      clearSchedule(storage, selectedMachineId);
    }
    savedSchedule = null;
    closeEditor();
    renderAll();
  }

  function advance() {
    if (lifecycleReloadRequired) return;
    if (hasOpenRollCorrection()) return;
    const current = readSchedule(storage, selectedMachineId, selectedCardId);
    if (!current) return;
    const advanced = advanceSchedule(current, selectedStatus, now());
    saveSchedule(storage, advanced);
    refresh();
  }

  function handleOverlayPointerDown(event) {
    backdropPressStarted = event.target === overlay;
    backdropPressEnded = false;
  }

  function handleOverlayPointerUp(event) {
    backdropPressEnded = backdropPressStarted && event.target === overlay;
  }

  function handleOverlayPointerCancel() {
    backdropPressStarted = false;
    backdropPressEnded = false;
  }

  function handleOverlayClick(event) {
    const shouldClose = backdropPressStarted && backdropPressEnded && event.target === overlay;
    backdropPressStarted = false;
    backdropPressEnded = false;
    if (shouldClose) closeEditor();
  }

  function handleDialogKeydown(event) {
    if (!overlay || overlay.hidden) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeEditor();
      return;
    }
    if (event.key !== "Tab" || !dialog) return;
    const focusable = Array.from(dialog.querySelectorAll(FOCUSABLE_SELECTOR)).filter(
      (element) => !element.hidden && element.getClientRects().length > 0,
    );
    if (focusable.length === 0) {
      event.preventDefault();
      dialog.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && documentObject.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && documentObject.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function handleStorage(event) {
    if (!event.key?.startsWith(STORAGE_KEY_PREFIX)) return;
    if (event.key === `${STORAGE_KEY_PREFIX}${selectedMachineId}`) {
      const schedule = matchingSchedule(selectedMachineId, selectedCardId);
      if (
        schedule
        && (lifecycleReloadRequired || schedule.observedStatus !== selectedStatus)
      ) {
        lifecycleReloadRequired = true;
        synchronizedSelectedStatus = schedule.observedStatus;
        closeEditor({ restoreFocus: false });
        if (openControl) openControl.disabled = true;
        if (advanceControl) advanceControl.disabled = true;
      }
    }
    renderAll();
  }

  clearMismatchedSchedules(storage, contexts);
  const bootstrapMs = now();
  for (const [machineId, context] of contexts) {
    reconcileAndPersist(machineId, context, bootstrapMs);
  }
  renderAll();

  listen(openControl, "click", openEditor);
  listen(previousDateInput, "input", recalculateDraft);
  for (const [input, maximum, callback] of [
    [previousHourInput, 23, recalculateDraft],
    [previousMinuteInput, 59, recalculateDraft],
    [hoursInput, 23, recalculateDraft],
    [minutesInput, 59, recalculateDraft],
    [nextHourInput, 23, () => syncDateTimeParts(nextInput, nextDateInput, nextHourInput, nextMinuteInput)],
    [nextMinuteInput, 59, () => syncDateTimeParts(nextInput, nextDateInput, nextHourInput, nextMinuteInput)],
  ]) {
    listen(input, "input", () => {
      callback();
    });
    listen(input, "focus", () => input.select());
    listen(input, "blur", () => {
      normalizeNumericInput(input, maximum);
      callback();
    });
  }
  listen(nextDateInput, "input", () => syncDateTimeParts(nextInput, nextDateInput, nextHourInput, nextMinuteInput));
  listen(form, "submit", submitEditor);
  listen(restartControl, "click", restartDraft);
  listen(clearControl, "click", clearEditorSchedule);
  listen(cancelControl, "click", () => closeEditor());
  listen(closeControl, "click", () => closeEditor());
  listen(advanceControl, "click", advance);
  listen(overlay, "pointerdown", handleOverlayPointerDown);
  listen(overlay, "pointerup", handleOverlayPointerUp);
  listen(overlay, "pointercancel", handleOverlayPointerCancel);
  listen(overlay, "click", handleOverlayClick);
  listen(documentObject, "keydown", handleDialogKeydown);
  listen(windowObject, "storage", handleStorage);

  const displayInterval = intervalFactory(renderAll);
  return {
    refresh,
    destroy() {
      windowObject.clearInterval(displayInterval);
      for (const removeListener of listeners.splice(0)) removeListener();
    },
  };
}


if (typeof document !== "undefined" && typeof window !== "undefined") {
  bootstrapRollChangeCountdown();
}
