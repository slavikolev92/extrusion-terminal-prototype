import {
  createSerializedTaskQueue,
  parsePalletWeightDraft,
} from "./pallet_weight_autosave_core.mjs";
import {
  classifyPalletWeightSnapshotReconciliation,
} from "./pallet_weight_terminal_sync_core.mjs";


const FIELD_MESSAGES = {
  format: "Използвайте число с най-много два десетични знака.",
  minimum: "Теглото трябва да бъде поне 0.01 кг.",
  maximum: "Теглото не може да бъде повече от 100.00 кг.",
};


export function bootstrapPalletWeightAutosave({
  documentObject = document,
  windowObject = window,
  fetchImpl = (...args) => windowObject.fetch(...args),
} = {}) {
  const overlay = documentObject.querySelector("[data-pallet-summary-overlay]");
  if (!overlay) return null;
  const cardId = Number(overlay.dataset.cardId);
  let cardVersion = Number(overlay.dataset.cardVersion);
  if (!Number.isSafeInteger(cardId) || cardId <= 0 || !Number.isSafeInteger(cardVersion)) {
    return null;
  }

  const pageKind = overlay.dataset.pageKind;
  const forms = Array.from(overlay.querySelectorAll("[data-pallet-weight-form]"));
  const status = overlay.querySelector("[data-pallet-weight-status]");
  const statusMessage = overlay.querySelector("[data-pallet-weight-status-message]");
  const reloadControl = overlay.querySelector("[data-pallet-weight-reload]");
  const queue = createSerializedTaskQueue();
  const fields = new Map();
  let fatal = false;
  let generation = 0;
  let activeCycle = null;
  let dismissalPending = false;

  if (reloadControl) reloadControl.href = windowObject.location.href;

  for (const form of forms) {
    const input = form.querySelector("[data-pallet-weight-input]");
    const palletNumber = Number(form.dataset.palletWeightForm);
    if (!input || !Number.isSafeInteger(palletNumber) || palletNumber <= 0) continue;
    input.dataset.savedValue = input.value;
    fields.set(input, {
      form,
      input,
      palletNumber,
      savedValue: input.value,
      state: "clean",
      pendingPromise: null,
      generation: 0,
    });
  }

  function setStatus(message = "", kind = "") {
    if (statusMessage) statusMessage.textContent = message;
    if (!status) return;
    if (kind) status.dataset.kind = kind;
    else delete status.dataset.kind;
  }

  function clearTransientSuccess() {
    if (status?.dataset.kind === "success") setStatus();
  }

  function clearFieldError(field) {
    field.input.removeAttribute("aria-invalid");
  }

  function restoreSavedField(field) {
    field.input.value = field.savedValue;
    field.input.dataset.savedValue = field.savedValue;
    field.input.removeAttribute("aria-busy");
    field.state = "clean";
    clearFieldError(field);
  }

  function scheduleFieldFocus(field) {
    windowObject.requestAnimationFrame(() => {
      if (fatal || overlay.hidden || field.state !== "failed") return;
      field.input.focus();
    });
  }

  function showFieldError(field, message) {
    field.state = "failed";
    field.input.setAttribute("aria-invalid", "true");
    setStatus(`Проверете теглото за палет №${field.palletNumber}. ${message}`, "error");
    scheduleFieldFocus(field);
  }

  function freezeInputs(frozen) {
    for (const field of fields.values()) {
      field.input.readOnly = frozen || field.state === "queued" || field.state === "active";
    }
  }

  function hasUnconfirmedWork() {
    return fatal || queue.pendingCount() > 0 || Array.from(fields.values()).some((field) => (
      field.state !== "clean" || field.input.value !== field.savedValue
    ));
  }

  function enterFatalLock(message, focusReload = true, field = null) {
    fatal = true;
    dismissalPending = false;
    if (field) {
      field.state = "failed";
      field.input.setAttribute("aria-invalid", "true");
    }
    freezeInputs(true);
    setStatus(message, "error");
    if (reloadControl) {
      reloadControl.hidden = false;
      if (focusReload) windowObject.requestAnimationFrame(() => reloadControl.focus());
    }
  }

  function beginCycle() {
    let resolveCycle;
    const cycle = {
      baseline: null,
      hadSuccess: false,
      ending: false,
      promise: new Promise((resolve) => { resolveCycle = resolve; }),
      resolve: resolveCycle,
    };
    const detail = { cardId, baseline: null };
    documentObject.dispatchEvent(new CustomEvent("pallet-summary:autosave-started", { detail }));
    cycle.baseline = detail.baseline;
    activeCycle = cycle;
    return cycle;
  }

  async function reconcileTerminalCycle(cycle) {
    if (pageKind !== "terminal" || !cycle.hadSuccess) return !fatal;
    if (!cycle.baseline || typeof cycle.baseline !== "object") {
      enterFatalLock("Състоянието на картата не може да бъде потвърдено. Презаредете страницата.");
      return false;
    }
    try {
      const url = new URL("/terminal/snapshot", windowObject.location.origin);
      url.searchParams.set("selected_card_id", String(cardId));
      const response = await fetchImpl(url, {
        headers: { "Accept": "application/json" },
        cache: "no-store",
      });
      if (!response.ok) throw new Error("snapshot request failed");
      const after = await response.json();
      const reconciliation = classifyPalletWeightSnapshotReconciliation(
        cycle.baseline,
        after,
        { cardId, expectedVersion: cardVersion },
      );
      if (reconciliation.kind !== "accept-local") {
        enterFatalLock("Данните са променени. Презаредете страницата, преди да продължите.");
      }
      documentObject.dispatchEvent(new CustomEvent("pallet-summary:queue-idle", {
        detail: {
          cardId,
          expectedVersion: cardVersion,
          before: cycle.baseline,
          after,
          reconciliation,
        },
      }));
      if (reconciliation.kind === "accept-local") return true;
      return false;
    } catch {
      enterFatalLock("Записът не може да бъде потвърден. Презаредете страницата.");
      return false;
    }
  }

  async function endCycle(cycle) {
    if (cycle.ending || cycle !== activeCycle) return;
    cycle.ending = true;
    const freezesForReconciliation = pageKind === "terminal" && cycle.hadSuccess;
    if (freezesForReconciliation) freezeInputs(true);
    const reconciled = await reconcileTerminalCycle(cycle);
    if (pageKind !== "terminal" || !cycle.hadSuccess) {
      documentObject.dispatchEvent(new CustomEvent("pallet-summary:queue-idle", {
        detail: { cardId, expectedVersion: cardVersion, reconciliation: null },
      }));
    }
    if (activeCycle === cycle) activeCycle = null;
    if (freezesForReconciliation && !fatal && !dismissalPending) {
      freezeInputs(false);
    }
    cycle.resolve(Boolean(reconciled && !fatal));
  }

  function finishTaskCycle(cycle) {
    Promise.resolve().then(() => {
      if (queue.pendingCount() === 0) void endCycle(cycle);
    });
  }

  function formTargetsCurrentCard(form) {
    try {
      const path = new URL(form.action, windowObject.location.origin).pathname;
      const match = path.match(/^\/(?:terminal|admin)\/cards\/(\d+)(?:\/|$)/);
      return match !== null && Number(match[1]) === cardId;
    } catch {
      return false;
    }
  }

  function publishCardVersion(nextVersion) {
    const oldVersion = cardVersion;
    cardVersion = nextVersion;
    overlay.dataset.cardVersion = String(nextVersion);
    for (const form of documentObject.querySelectorAll("form[action]")) {
      if (!formTargetsCurrentCard(form)) continue;
      for (const input of form.querySelectorAll('input[name="loaded_version"]')) {
        input.value = String(nextVersion);
      }
    }
    documentObject.dispatchEvent(new CustomEvent("pallet-summary:card-version-updated", {
      detail: { cardId, oldVersion, newVersion: nextVersion },
    }));
  }

  function validDisplayRow(row, palletNumber) {
    return Boolean(
      row
      && row.pallet_number === palletNumber
      && Number.isSafeInteger(row.roll_count)
      && typeof row.gross_without_pallet_display === "string"
      && typeof row.pallet_weight_display === "string"
      && typeof row.gross_with_pallet_display === "string"
      && typeof row.net_display === "string"
    );
  }

  function validDisplayTotal(total) {
    return Boolean(
      total
      && Number.isSafeInteger(total.roll_count)
      && typeof total.gross_without_pallet_display === "string"
      && typeof total.pallet_weight_display === "string"
      && typeof total.gross_with_pallet_display === "string"
      && typeof total.net_display === "string"
    );
  }

  function validSuccessPayload(payload, field) {
    return Boolean(
      payload?.ok === true
      && Number.isSafeInteger(payload.card_version)
      && payload.card_version === cardVersion + 1
      && payload.pallet_number === field.palletNumber
      && typeof payload.normalized_weight === "string"
      && validDisplayRow(payload.row, field.palletNumber)
      && validDisplayTotal(payload.total)
      && ["none", "partial", "complete"].includes(payload.weight_state)
      && Array.isArray(payload.messages)
      && payload.messages.every((message) => typeof message === "string")
      && payload.reload_required === false
    );
  }

  function validFailurePayload(payload) {
    return Boolean(
      payload?.ok === false
      && Array.isArray(payload.messages)
      && payload.messages.every((message) => typeof message === "string")
      && Array.isArray(payload.field_errors)
      && payload.field_errors.every((issue) => (
        issue
        && (issue.pallet_number === null || Number.isSafeInteger(issue.pallet_number))
        && typeof issue.field === "string"
        && typeof issue.message === "string"
      ))
      && typeof payload.reload_required === "boolean"
    );
  }

  function applySuccess(field, payload) {
    field.input.value = payload.normalized_weight;
    field.savedValue = payload.normalized_weight;
    field.input.dataset.savedValue = payload.normalized_weight;
    field.state = "clean";
    clearFieldError(field);
    const grossWith = overlay.querySelector(`[data-pallet-gross-with="${field.palletNumber}"]`);
    if (grossWith) grossWith.textContent = payload.row.gross_with_pallet_display;
    const totals = {
      "[data-pallet-roll-count-total]": String(payload.total.roll_count),
      "[data-pallet-gross-without-total]": payload.total.gross_without_pallet_display,
      "[data-pallet-weight-total]": payload.total.pallet_weight_display,
      "[data-pallet-gross-with-total]": payload.total.gross_with_pallet_display,
      "[data-pallet-net-total]": payload.total.net_display,
    };
    for (const [selector, value] of Object.entries(totals)) {
      const target = overlay.querySelector(selector);
      if (target) target.textContent = value;
    }
    if (status) status.dataset.palletWeightStatus = payload.weight_state;
    publishCardVersion(payload.card_version);
    setStatus(payload.messages.join(" "), "success");
  }

  function failureMessage(payload, field) {
    const issue = payload.field_errors.find((candidate) => (
      candidate.pallet_number === field.palletNumber
      && candidate.field === "pallet_weight"
    )) ?? payload.field_errors[0];
    return issue?.message || payload.messages[0] || "Теглото не може да бъде записано.";
  }

  async function saveField(field, rawValue, cycle) {
    if (fatal) return false;
    field.state = "active";
    field.input.readOnly = true;
    field.input.setAttribute("aria-busy", "true");
    const formData = new FormData();
    formData.set("loaded_version", String(cardVersion));
    formData.set("pallet_weight", rawValue);
    try {
      const response = await fetchImpl(field.form.action, {
        method: "POST",
        body: formData,
        headers: { "Accept": "application/json" },
      });
      let payload;
      try {
        payload = await response.json();
      } catch {
        enterFatalLock(
          "Отговорът на сървъра е невалиден. Презаредете страницата.",
          true,
          field,
        );
        return false;
      }

      if (response.status === 422 && validFailurePayload(payload) && !payload.reload_required) {
        showFieldError(field, failureMessage(payload, field));
        return false;
      }
      if (!response.ok || !validSuccessPayload(payload, field)) {
        const message = validFailurePayload(payload)
          ? (payload.messages[0] || "Данните са променени.")
          : "Отговорът на сървъра е невалиден.";
        enterFatalLock(`${message} Презаредете страницата.`, true, field);
        return false;
      }

      applySuccess(field, payload);
      cycle.hadSuccess = true;
      return true;
    } catch {
      enterFatalLock(
        "Връзката със сървъра прекъсна. Презаредете страницата.",
        true,
        field,
      );
      return false;
    } finally {
      field.input.removeAttribute("aria-busy");
      if (!fatal) {
        field.input.readOnly = dismissalPending;
      }
    }
  }

  function enqueueField(field) {
    if (fatal) return Promise.resolve(false);
    if (field.state === "queued" || field.state === "active") {
      return field.pendingPromise ?? Promise.resolve(false);
    }
    const rawValue = field.input.value;
    if (rawValue === field.savedValue && field.state !== "failed") {
      field.state = "clean";
      return Promise.resolve(true);
    }
    const parsed = parsePalletWeightDraft(rawValue);
    if (parsed.kind === "invalid") {
      showFieldError(field, FIELD_MESSAGES[parsed.reason] || FIELD_MESSAGES.format);
      return Promise.resolve(false);
    }

    clearFieldError(field);
    const cycle = activeCycle ?? beginCycle();
    field.state = "queued";
    field.input.readOnly = true;
    field.generation = ++generation;
    const pending = queue.enqueue(() => saveField(field, rawValue, cycle));
    field.pendingPromise = pending;
    pending.finally(() => {
      field.pendingPromise = null;
      if (!fatal && field.state === "queued") field.state = "dirty";
      finishTaskCycle(cycle);
    });
    return pending;
  }

  async function prepareDismiss() {
    if (dismissalPending) return false;
    dismissalPending = true;
    if (fatal) {
      dismissalPending = false;
      return true;
    }
    const pending = [];
    let discardedDraft = false;
    for (const field of fields.values()) {
      if (field.state === "queued" || field.state === "active") {
        if (field.pendingPromise) pending.push(field.pendingPromise);
      } else if (field.input.value !== field.savedValue || field.state === "failed") {
        const parsed = parsePalletWeightDraft(field.input.value);
        if (field.state === "failed" || parsed.kind === "invalid") {
          restoreSavedField(field);
          discardedDraft = true;
        } else {
          pending.push(enqueueField(field));
        }
      }
    }
    const cycle = activeCycle;
    freezeInputs(true);
    if (discardedDraft && status?.dataset.kind === "error") setStatus();
    if (pending.length === 0 && !hasUnconfirmedWork() && !fatal && !cycle) {
      dismissalPending = false;
      freezeInputs(false);
      clearTransientSuccess();
      return true;
    }
    const results = await Promise.all(pending.map((promise) => promise.catch(() => false)));
    const cycleReady = cycle ? await cycle.promise : !fatal;
    if (fatal) {
      dismissalPending = false;
      return true;
    }
    if (results.some((result) => !result)) {
      for (const field of fields.values()) {
        if (field.state === "failed") {
          restoreSavedField(field);
          discardedDraft = true;
        }
      }
    }
    if (discardedDraft && status?.dataset.kind === "error") setStatus();
    const accepted = results.every(Boolean) && cycleReady && !fatal && !hasUnconfirmedWork();
    const discardedFailure = discardedDraft && cycleReady && !fatal && !hasUnconfirmedWork();
    dismissalPending = false;
    if (accepted || discardedFailure) {
      freezeInputs(false);
      clearTransientSuccess();
      return true;
    }
    if (!accepted && !fatal) {
      freezeInputs(false);
      const problem = Array.from(fields.values()).find((field) => field.state === "failed");
      windowObject.requestAnimationFrame(() => problem?.input.focus());
    }
    return false;
  }

  for (const field of fields.values()) {
    field.input.addEventListener("input", () => {
      if (fatal) return;
      field.state = "dirty";
      clearFieldError(field);
      if (status?.dataset.kind === "error") setStatus();
    });
    field.input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      void enqueueField(field);
    });
    field.input.addEventListener("blur", () => { void enqueueField(field); });
    field.form.addEventListener("submit", (event) => {
      event.preventDefault();
      void enqueueField(field);
    });
  }

  overlay.addEventListener("pallet-summary:prepare-dismiss", (event) => {
    if (!event.detail || event.detail.decision !== null) {
      if (event.detail) event.detail.decision = Promise.resolve(false);
      return;
    }
    event.detail.decision = prepareDismiss();
  });

  const handleTerminalStale = (event) => {
    if (overlay.hidden || !hasUnconfirmedWork()) return;
    event.preventDefault();
    enterFatalLock("Данните са променени. Презаредете страницата, преди да продължите.");
  };
  windowObject.addEventListener("terminal:card-stale", handleTerminalStale, { capture: true });
  windowObject.addEventListener("terminal:shift-stale", handleTerminalStale, { capture: true });

  return {
    prepareDismiss,
    hasUnconfirmedWork,
    isFatal: () => fatal,
  };
}


if (typeof document !== "undefined" && typeof window !== "undefined") {
  bootstrapPalletWeightAutosave();
}
