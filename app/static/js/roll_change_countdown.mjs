import {
  STORAGE_KEY_PREFIX,
  advanceSchedule,
  buildSchedule,
  calculateNextExpected,
  clearMismatchedSchedules,
  clearSchedule,
  countdownView,
  parseIntervalMinutes,
  parseOperatorLocalMinute,
  readSchedule,
  reconcileCardStatus,
  saveSchedule,
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
  const controlNext = controls?.querySelector("[data-roll-change-control-next]") ?? null;
  const advanceControl = controls?.querySelector("[data-roll-change-advance]") ?? null;

  const overlay = documentObject.querySelector("[data-roll-change-overlay]");
  const dialog = overlay?.querySelector("[data-roll-change-dialog]") ?? null;
  const form = overlay?.querySelector("[data-roll-change-form]") ?? null;
  const previousInput = form?.querySelector("[data-roll-change-previous]") ?? null;
  const hoursInput = form?.querySelector("[data-roll-change-hours]") ?? null;
  const minutesInput = form?.querySelector("[data-roll-change-minutes]") ?? null;
  const nextInput = form?.querySelector("[data-roll-change-next]") ?? null;
  const restartControl = form?.querySelector("[data-roll-change-restart]") ?? null;
  const clearControl = form?.querySelector("[data-roll-change-clear]") ?? null;
  const cancelControl = form?.querySelector("[data-roll-change-cancel]") ?? null;
  const errorSlots = new Map(
    Array.from(form?.querySelectorAll("[data-roll-change-error-for]") ?? [], (slot) => [
      slot.dataset.rollChangeErrorFor,
      slot,
    ]),
  );

  let savedSchedule = null;
  let returnFocus = null;
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
    if (!schedule || !TRACKABLE.has(context.status)) {
      timer.hidden = true;
      timer.textContent = "";
      timer.removeAttribute("aria-label");
      timer.classList.remove(...TONE_CLASSES);
      return;
    }
    const view = countdownView(schedule, context.status, currentMs);
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
    if (!openControl || !controlValue || !controlNext || !advanceControl) return;
    if (!schedule || !TRACKABLE.has(selectedStatus)) {
      controlValue.textContent = "Смяна на ролка";
      controlNext.textContent = "";
      controlNext.hidden = true;
      advanceControl.hidden = true;
      openControl.classList.remove(...TONE_CLASSES);
      openControl.setAttribute("aria-label", `Настрой смяна на ролките за машина ${selectedMachineId}`);
      return;
    }
    const view = countdownView(schedule, selectedStatus, currentMs);
    controlValue.textContent = view.display;
    controlNext.textContent = `Следваща ${view.nextExpectedLabel}`;
    controlNext.hidden = false;
    advanceControl.hidden = false;
    openControl.classList.remove(...TONE_CLASSES);
    openControl.classList.add(view.tone);
    openControl.setAttribute(
      "aria-label",
      view.due
        ? `Редактирай смяната на ролките за машина ${selectedMachineId}; смяната е дължима`
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
  }

  function renderErrors(errors) {
    clearErrors();
    for (const [name, message] of Object.entries(errors)) {
      const slot = errorSlots.get(name);
      if (slot) slot.textContent = message;
    }
  }

  function recalculateDraft() {
    if (!previousInput || !hoursInput || !minutesInput || !nextInput) return;
    const previousMs = parseOperatorLocalMinute(previousInput.value, now());
    const intervalResult = parseIntervalMinutes(hoursInput.value, minutesInput.value);
    if (previousMs !== null && intervalResult.ok) {
      nextInput.value = toLocalDateTimeInputValue(
        calculateNextExpected(previousMs, intervalResult.value),
      );
    }
  }

  function hasOpenRollCorrection() {
    return Boolean(documentObject.querySelector(".roll-row.is-editing"));
  }

  function openEditor(event) {
    if (hasOpenRollCorrection()) return;
    if (!overlay || !previousInput || !hoursInput || !minutesInput || !nextInput) return;
    returnFocus = event?.currentTarget ?? openControl;
    savedSchedule = matchingSchedule(selectedMachineId, selectedCardId);
    if (savedSchedule) {
      previousInput.value = toLocalDateTimeInputValue(savedSchedule.previousChangeAtMs);
      hoursInput.value = String(Math.floor(savedSchedule.intervalMinutes / 60));
      minutesInput.value = String(savedSchedule.intervalMinutes % 60);
      nextInput.value = toLocalDateTimeInputValue(savedSchedule.nextExpectedAtMs);
    } else {
      previousInput.value = toLocalDateTimeInputValue(now());
      hoursInput.value = "0";
      minutesInput.value = "0";
      nextInput.value = "";
    }
    clearErrors();
    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    openControl?.setAttribute("aria-expanded", "true");
    previousInput.focus();
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
    if (!previousInput || !hoursInput || !minutesInput || !nextInput) return;
    if (hasNonMatchingStoredRecord(selectedMachineId, selectedCardId)) {
      closeEditor();
      renderAll();
      return;
    }
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
    if (!previousInput || !hoursInput || !minutesInput || !nextInput) return;
    const intervalResult = parseIntervalMinutes(hoursInput.value, minutesInput.value);
    if (!intervalResult.ok) {
      renderErrors(intervalResult.errors);
      return;
    }
    clearErrors();
    const currentMs = now();
    previousInput.value = toLocalDateTimeInputValue(currentMs);
    nextInput.value = toLocalDateTimeInputValue(
      calculateNextExpected(
        parseOperatorLocalMinute(previousInput.value, currentMs),
        intervalResult.value,
      ),
    );
  }

  function clearEditorSchedule() {
    if (matchingSchedule(selectedMachineId, selectedCardId)) {
      clearSchedule(storage, selectedMachineId);
    }
    savedSchedule = null;
    closeEditor();
    renderAll();
  }

  function advance() {
    if (hasOpenRollCorrection()) return;
    const current = readSchedule(storage, selectedMachineId, selectedCardId);
    if (!current) return;
    const advanced = advanceSchedule(current, selectedStatus, now());
    saveSchedule(storage, advanced);
    refresh();
  }

  function handleOverlayClick(event) {
    if (event.target === overlay) closeEditor();
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
    renderAll();
  }

  clearMismatchedSchedules(storage, contexts);
  const bootstrapMs = now();
  for (const [machineId, context] of contexts) {
    reconcileAndPersist(machineId, context, bootstrapMs);
  }
  renderAll();

  listen(openControl, "click", openEditor);
  listen(previousInput, "input", recalculateDraft);
  listen(hoursInput, "input", recalculateDraft);
  listen(minutesInput, "input", recalculateDraft);
  listen(form, "submit", submitEditor);
  listen(restartControl, "click", restartDraft);
  listen(clearControl, "click", clearEditorSchedule);
  listen(cancelControl, "click", () => closeEditor());
  listen(advanceControl, "click", advance);
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
