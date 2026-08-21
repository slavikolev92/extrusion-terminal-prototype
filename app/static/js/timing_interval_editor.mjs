import {
  addIntervalDraft,
  incompleteDraftFields,
  mapServerPreview,
  markIntervalDeleted,
  maskTimeInput,
  serializeTimingDraft,
  undoIntervalDelete,
} from "./timing_interval_editor_core.mjs";

export function createPreviewCoordinator({ apply = () => {} } = {}) {
  let currentGeneration = 0;
  let activeController = null;
  let stale = false;
  let suspended = false;

  const invalidate = ({ stale: markStale = false, suspend = false } = {}) => {
    activeController?.abort();
    activeController = null;
    currentGeneration += 1;
    stale ||= markStale;
    suspended ||= suspend;
    return currentGeneration;
  };

  const request = async (run) => {
    activeController?.abort();
    currentGeneration += 1;
    const requestGeneration = currentGeneration;
    const controller = new AbortController();
    activeController = controller;
    try {
      const value = await run(controller.signal);
      if (
        controller.signal.aborted
        || requestGeneration !== currentGeneration
        || stale
        || suspended
      ) {
        return { applied: false, value: null };
      }
      apply(value);
      return { applied: true, value };
    } catch (error) {
      if (controller.signal.aborted || error?.name === "AbortError") {
        return { applied: false, value: null };
      }
      throw error;
    } finally {
      if (activeController === controller) {
        activeController = null;
      }
    }
  };

  return {
    generation: () => currentGeneration,
    invalidate,
    request,
  };
}

export function timingFieldAccessibleName(displayNumber, field) {
  const boundary = field.startsWith("start_") ? "Начало" : "Край";
  const fieldType = field.endsWith("_date") ? "дата" : "час";
  return `Интервал ${displayNumber}, ${boundary}, ${fieldType}`;
}

export function retainedFinishReviewMessages(finishReview) {
  return [...new Set([
    ...(Array.isArray(finishReview.messages) ? finishReview.messages : []),
    ...(Array.isArray(finishReview.issues) ? finishReview.issues : [])
      .map((issue) => issue.message),
  ].filter(Boolean))];
}

const modelElement = document.querySelector("[data-terminal-timing-model]");
const menu = document.querySelector("[data-timing-menu]");
const menuButton = menu?.querySelector("[data-timing-menu-button]");
const menuPanel = menu?.querySelector("[data-timing-menu-panel]");
const menuAction = menu?.querySelector("[data-timing-menu-open]");
const overlay = document.querySelector("[data-timing-editor-overlay]");
const dialog = overlay?.querySelector("[data-timing-dialog]");
const saveForm = overlay?.querySelector("[data-timing-save-form]");
const draftInput = overlay?.querySelector("[data-timing-draft-input]");
const intervalList = overlay?.querySelector("[data-timing-interval-list]");
const alertBox = overlay?.querySelector("[data-timing-alert]");
const totals = overlay?.querySelector("[data-timing-totals]");
const productionTotal = overlay?.querySelector("[data-timing-production-total]");
const pausedTotal = overlay?.querySelector("[data-timing-paused-total]");
const addButton = overlay?.querySelector("[data-timing-add-interval]");
const reloadLink = overlay?.querySelector("[data-timing-reload]");
const cancelButton = overlay?.querySelector("[data-timing-cancel]");
const saveButton = overlay?.querySelector("[data-timing-save]");
const activeFinishForm = document.querySelector('form[data-timing-finish-review="true"]');
const finishOverlay = document.querySelector("[data-finish-review-overlay]");
const finishDialog = finishOverlay?.querySelector("[data-finish-review-dialog]");
const finishAlert = finishOverlay?.querySelector("[data-finish-review-alert]");
const finishWarning = finishOverlay?.querySelector("[data-finish-review-warning]");
const finishFirstStart = finishOverlay?.querySelector("[data-finish-first-start]");
const finishProposedStop = finishOverlay?.querySelector("[data-finish-proposed-stop]");
const finishProductionTotal = finishOverlay?.querySelector("[data-finish-production-total]");
const finishPausedTotal = finishOverlay?.querySelector("[data-finish-paused-total]");
const finishEditButton = finishOverlay?.querySelector("[data-finish-review-edit]");
const finishCancelButton = finishOverlay?.querySelector("[data-finish-review-cancel]");
const finishConfirmButton = finishOverlay?.querySelector("[data-finish-review-confirm]");
const backgroundTargets = Array.from(
  document.querySelectorAll(".app, .terminal-toast"),
);

let model = null;
try {
  model = modelElement ? JSON.parse(modelElement.textContent) : null;
} catch {
  model = null;
}

if (model?.timing && menu && menuButton && menuPanel && menuAction && overlay
    && dialog && saveForm && draftInput && intervalList && alertBox && totals
    && productionTotal && pausedTotal && addButton && reloadLink && cancelButton
    && saveButton && activeFinishForm && finishOverlay && finishDialog && finishAlert
    && finishWarning && finishFirstStart && finishProposedStop
    && finishProductionTotal && finishPausedTotal && finishEditButton
    && finishCancelButton && finishConfirmButton) {
  const timing = model.timing;
  let state = createInitialState();
  let modalReturnFocus = null;
  let backgroundState = null;
  let submitting = false;
  let finishReview = null;
  let finishReturnFocus = null;
  let finishSubmitting = false;
  let finishNativeSubmit = false;
  let shiftSuspended = false;
  const previewCoordinator = createPreviewCoordinator();

  function cloneRows(rows) {
    return rows.map((row) => ({ ...row }));
  }

  function createInitialState(
    rows = timing.draft,
    previewPayload = timing.display,
    mode = "ordinary",
  ) {
    const preview = mapServerPreview(cloneRows(rows), previewPayload);
    return {
      status: timing.status,
      mode,
      rows: preview.rows,
      productionSeconds: preview.production_seconds,
      pausedSeconds: preview.paused_seconds,
      locked: Boolean(timing.locked),
    };
  }

  function requiredDraftStatus() {
    return state.mode === "finish" ? "paused" : state.status;
  }

  function formatDuration(seconds) {
    if (!Number.isSafeInteger(seconds) || seconds < 0) {
      return "—";
    }
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours} ч ${String(minutes).padStart(2, "0")} мин`;
  }

  function formatDraftBoundary(row, prefix) {
    const date = row?.[`${prefix}_date`] || "";
    const time = row?.[`${prefix}_time`] || "";
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
    if (!match || !/^\d{2}:\d{2}$/.test(time)) {
      return "";
    }
    return `${match[3]}.${match[2]}.${match[1]} ${time}`;
  }

  function retainedFinishPreview(finishModel, draft) {
    if (!finishModel.preview) {
      return timing.display;
    }
    const activeRows = draft.filter((row) => !row.deleted);
    return {
      ...finishModel.preview,
      first_start_display: formatDraftBoundary(activeRows[0], "start"),
      proposed_stop_display: formatDraftBoundary(activeRows.at(-1), "stop"),
    };
  }

  function updateDraftInput() {
    draftInput.value = JSON.stringify(serializeTimingDraft(state.rows));
  }

  function updateTotals() {
    productionTotal.textContent = formatDuration(state.productionSeconds);
    pausedTotal.textContent = formatDuration(state.pausedSeconds);
  }

  function setPreviewLoading(loading) {
    totals.classList.toggle("timing-dialog-loading", loading);
    totals.setAttribute("aria-busy", loading ? "true" : "false");
  }

  function invalidatePreviewDraft() {
    previewCoordinator.invalidate();
    setPreviewLoading(false);
  }

  function clearAlert() {
    alertBox.hidden = true;
    alertBox.classList.remove("stale");
    alertBox.replaceChildren();
    totals.hidden = false;
  }

  function showAlert(messages, { stale = false } = {}) {
    const uniqueMessages = [...new Set(messages.filter(Boolean))];
    alertBox.replaceChildren();
    uniqueMessages.forEach((message) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = message;
      alertBox.append(paragraph);
    });
    alertBox.classList.toggle("stale", stale);
    alertBox.hidden = uniqueMessages.length === 0;
    totals.hidden = uniqueMessages.length > 0;
  }

  function fieldInput(sourceIndex, field) {
    return intervalList.querySelector(
      `[data-source-index="${sourceIndex}"][data-timing-field="${field}"]`,
    );
  }

  function renderServerErrors(
    issues,
    { finish = false, preserveAlert = false } = {},
  ) {
    intervalList.querySelectorAll("[data-timing-field-error]").forEach(
      (element) => {
        element.replaceChildren();
        element.hidden = true;
      },
    );
    intervalList.querySelectorAll("[aria-invalid='true']").forEach((input) => {
      input.removeAttribute("aria-invalid");
      input.removeAttribute("aria-describedby");
    });
    const formMessages = [];
    let firstEditableTarget = null;
    issues.forEach((issue) => {
      if (!Number.isSafeInteger(issue.source_index) || issue.field === "form") {
        formMessages.push(issue.message);
        return;
      }
      const input = fieldInput(issue.source_index, issue.field);
      if (!input) {
        formMessages.push(issue.message);
        return;
      }
      const error = input.closest("[data-timing-field-wrapper]")?.querySelector(
        "[data-timing-field-error]",
      );
      if (!error) {
        formMessages.push(issue.message);
        return;
      }
      error.textContent = error.hidden
        ? issue.message
        : `${error.textContent} ${issue.message}`;
      error.hidden = false;
      input.setAttribute("aria-invalid", "true");
      input.setAttribute("aria-describedby", error.id);
      if (!input.disabled && !firstEditableTarget) {
        firstEditableTarget = input;
      }
    });
    if (!preserveAlert) {
      if (finish && finishOverlay.hidden === false) {
        showFinishAlert(formMessages);
      } else {
        if (formMessages.length > 0) {
          showAlert(formMessages, { stale: state.locked });
        } else {
          clearAlert();
        }
      }
      if (firstEditableTarget) {
        window.requestAnimationFrame(() => firstEditableTarget.focus());
      } else if (formMessages.length > 0) {
        window.requestAnimationFrame(() => {
          (finish && !finishOverlay.hidden ? finishAlert : alertBox).focus?.();
        });
      }
    }
  }

  function lockTimingDraft(messages = ["Данните са променени. Презаредете картата."]) {
    previewCoordinator.invalidate({ stale: true });
    setPreviewLoading(false);
    state.locked = true;
    renderRows();
    addButton.disabled = true;
    saveButton.disabled = true;
    reloadLink.hidden = false;
    finishEditButton.disabled = true;
    finishConfirmButton.disabled = true;
    showAlert(messages, { stale: true });
    reloadLink.focus();
  }

  function createFieldInput(row, sourceIndex, field) {
    const input = document.createElement("input");
    input.value = row[field] || "";
    input.dataset.sourceIndex = String(sourceIndex);
    input.dataset.timingField = field;
    input.disabled = state.locked || row.deleted;
    input.setAttribute(
      "aria-label",
      timingFieldAccessibleName(row.display_number, field),
    );
    if (field.endsWith("_date")) {
      input.type = "date";
    } else {
      input.type = "text";
      input.inputMode = "numeric";
      input.maxLength = 5;
      input.autocomplete = "off";
      input.placeholder = "чч:мм";
    }
    input.addEventListener("input", () => {
      invalidatePreviewDraft();
      let value = input.value;
      if (field.endsWith("_time")) {
        const masked = maskTimeInput(value);
        value = masked.value;
        input.value = value;
      }
      state.rows[sourceIndex] = {
        ...state.rows[sourceIndex],
        [field]: value,
      };
      clearAlert();
      updateDraftInput();
    });
    input.addEventListener("blur", () => {
      if (
        state.mode === "ordinary"
        && incompleteDraftFields(state.rows, requiredDraftStatus()).length === 0
      ) {
        requestOrdinaryPreview();
      }
    });
    return input;
  }

  function createTimestampControls(row, sourceIndex, prefix) {
    const controls = document.createElement("div");
    controls.className = "timestamp-controls";
    controls.append(
      createTimestampField(row, sourceIndex, `${prefix}_date`),
      createTimestampField(row, sourceIndex, `${prefix}_time`),
    );
    return controls;
  }

  function createTimestampField(row, sourceIndex, field) {
    const wrapper = document.createElement("div");
    wrapper.className = "timestamp-field";
    wrapper.dataset.timingFieldWrapper = "true";
    const input = createFieldInput(row, sourceIndex, field);
    const error = document.createElement("span");
    error.id = `timing-field-error-${sourceIndex}-${field}`;
    error.dataset.timingFieldError = "true";
    error.className = "field-error-slot";
    error.hidden = true;
    wrapper.append(input, error);
    return wrapper;
  }

  function renderRows() {
    intervalList.replaceChildren();
    const activeIndexes = state.rows
      .map((row, index) => (row.deleted ? null : index))
      .filter((index) => index !== null);
    const finalActiveIndex = activeIndexes.at(-1);

    state.rows.forEach((row, sourceIndex) => {
      const rowElement = document.createElement("div");
      rowElement.className = `interval-row${row.deleted ? " pending-delete" : ""}`;
      rowElement.dataset.sourceIndex = String(sourceIndex);

      const numberCell = document.createElement("div");
      numberCell.className = "interval-number";
      numberCell.textContent = String(row.display_number ?? sourceIndex + 1);

      const startCell = document.createElement("div");
      startCell.append(createTimestampControls(row, sourceIndex, "start"));

      const stopCell = document.createElement("div");
      const finalOpen = state.mode === "ordinary"
        && state.status === "running"
        && !row.deleted
        && sourceIndex === finalActiveIndex;
      if (finalOpen) {
        stopCell.replaceChildren();
      } else {
        stopCell.append(createTimestampControls(row, sourceIndex, "stop"));
      }

      const durationCell = document.createElement("div");
      durationCell.className = "interval-duration";
      durationCell.textContent = row.deleted ? "—" : formatDuration(row.duration_seconds);

      const actionCell = document.createElement("div");
      const button = document.createElement("button");
      button.type = "button";
      button.className = row.deleted ? "interval-undo" : "interval-delete";
      button.textContent = row.deleted ? "Отмяна" : "×";
      button.setAttribute(
        "aria-label",
        row.deleted
          ? `Отмени изтриването на интервал ${row.display_number}`
          : `Изтрий интервал ${row.display_number}`,
      );
      button.disabled = state.locked;
      button.addEventListener("click", () => {
        invalidatePreviewDraft();
        state.rows = row.deleted
          ? undoIntervalDelete(state.rows, sourceIndex)
          : markIntervalDeleted(state.rows, sourceIndex);
        clearAlert();
        renderRows();
        updateDraftInput();
        if (
          state.mode === "ordinary"
          && incompleteDraftFields(state.rows, requiredDraftStatus()).length === 0
        ) {
          requestOrdinaryPreview();
        }
      });
      actionCell.append(button);
      rowElement.append(numberCell, startCell, stopCell, durationCell, actionCell);
      intervalList.append(rowElement);
    });
  }

  function focusFirstIncomplete() {
    const first = incompleteDraftFields(state.rows, requiredDraftStatus())[0];
    if (!first) {
      return false;
    }
    fieldInput(first.source_index, first.field)?.focus();
    return true;
  }

  function setBackgroundIsolated(isolated) {
    if (isolated) {
      if (!backgroundState) {
        backgroundState = backgroundTargets.map((element) => ({
          element,
          inert: element.hasAttribute("inert"),
          ariaHidden: element.getAttribute("aria-hidden"),
        }));
      }
      backgroundTargets.forEach((element) => {
        element.setAttribute("inert", "");
        element.setAttribute("aria-hidden", "true");
      });
      return;
    }
    backgroundState?.forEach(({ element, inert, ariaHidden }) => {
      if (inert) {
        element.setAttribute("inert", "");
      } else {
        element.removeAttribute("inert");
      }
      if (ariaHidden === null) {
        element.removeAttribute("aria-hidden");
      } else {
        element.setAttribute("aria-hidden", ariaHidden);
      }
    });
    backgroundState = null;
  }

  function focusableDialogElements() {
    return Array.from(dialog.querySelectorAll(
      'button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
    )).filter((element) => !element.hidden && !element.closest("[hidden]"));
  }

  function trapDialogFocus(event) {
    const focusable = focusableDialogElements();
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first || !last) {
      event.preventDefault();
      dialog.focus();
    } else if (!dialog.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function openMenu({ focusItem = false } = {}) {
    if (menuButton.disabled || shiftSuspended) {
      return;
    }
    menuPanel.hidden = false;
    menuButton.setAttribute("aria-expanded", "true");
    if (focusItem) {
      menuAction.focus();
    }
  }

  function closeMenu({ restoreFocus = false } = {}) {
    menuPanel.hidden = true;
    menuButton.setAttribute("aria-expanded", "false");
    if (restoreFocus) {
      menuButton.focus({ preventScroll: true });
    }
  }

  function openEditor({
    opener = menuAction,
    mode = "ordinary",
    rows = timing.draft,
    preview = timing.display,
    previewOnOpen = true,
  } = {}) {
    if (shiftSuspended) {
      return;
    }
    modalReturnFocus = opener;
    state = createInitialState(rows, preview, mode);
    submitting = false;
    saveButton.disabled = state.locked;
    addButton.disabled = state.locked;
    reloadLink.hidden = !state.locked;
    dialog.querySelector("#timing-dialog-title").textContent = mode === "finish"
      ? "Корекция преди приключване"
      : "Корекция на производствено време";
    saveButton.textContent = mode === "finish" ? "Приложи" : "Запиши";
    clearAlert();
    renderRows();
    updateTotals();
    updateDraftInput();
    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    setBackgroundIsolated(true);
    if (state.locked) {
      lockTimingDraft();
    } else {
      dialog.focus();
      if (mode === "ordinary" && previewOnOpen) {
        requestOrdinaryPreview();
      }
    }
  }

  function closeEditor({ restoreFocus = true, preserveBackground = false } = {}) {
    invalidatePreviewDraft();
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    if (!preserveBackground) {
      setBackgroundIsolated(false);
    }
    submitting = false;
    saveButton.disabled = false;
    if (restoreFocus) {
      (modalReturnFocus || menuButton).focus({ preventScroll: true });
    }
    modalReturnFocus = null;
  }

  function cancelEditor() {
    if (state.mode !== "finish") {
      closeEditor();
      return;
    }
    closeEditor({ restoreFocus: false });
    finishReview = null;
    finishSubmitting = false;
    finishNativeSubmit = false;
    finishReturnFocus?.focus({ preventScroll: true });
    finishReturnFocus = null;
  }

  function finishFocusableElements() {
    return Array.from(finishDialog.querySelectorAll(
      'button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
    )).filter((element) => !element.hidden && !element.closest("[hidden]"));
  }

  function trapFinishFocus(event) {
    const focusable = finishFocusableElements();
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first || !last) {
      event.preventDefault();
      finishDialog.focus();
    } else if (!finishDialog.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function showFinishAlert(messages) {
    finishAlert.replaceChildren();
    [...new Set(messages.filter(Boolean))].forEach((message) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = message;
      finishAlert.append(paragraph);
    });
    finishAlert.hidden = finishAlert.childElementCount === 0;
  }

  function focusFinishAlert() {
    window.requestAnimationFrame(() => finishAlert.focus());
  }

  function renderFinishPreview(preview) {
    finishFirstStart.textContent = preview.first_start_display || "—";
    finishProposedStop.textContent = preview.proposed_stop_display || "—";
    finishProductionTotal.textContent = formatDuration(preview.production_seconds);
    finishPausedTotal.textContent = formatDuration(preview.paused_seconds);
    const message = activeFinishForm.dataset.finishConfirmMessage || "";
    const genericMessage = "Сигурни ли сте, че искате да приключите тази поръчка?";
    finishWarning.textContent = message;
    finishWarning.hidden = !message || message === genericMessage;
  }

  function openFinishSummary({ opener = activeFinishForm, focusTarget = finishEditButton } = {}) {
    if (shiftSuspended) {
      return;
    }
    finishReturnFocus ||= opener.querySelector?.("button") || opener;
    showFinishAlert([]);
    renderFinishPreview(finishReview.preview);
    finishOverlay.hidden = false;
    finishOverlay.setAttribute("aria-hidden", "false");
    setBackgroundIsolated(true);
    focusTarget.focus();
  }

  function closeFinishSummary({ restoreFocus = true, preserveBackground = false } = {}) {
    invalidatePreviewDraft();
    finishOverlay.hidden = true;
    finishOverlay.setAttribute("aria-hidden", "true");
    finishConfirmButton.disabled = false;
    finishEditButton.disabled = false;
    if (!preserveBackground) {
      setBackgroundIsolated(false);
    }
    if (restoreFocus) {
      finishReturnFocus?.focus({ preventScroll: true });
    }
    if (!preserveBackground) {
      finishReturnFocus = null;
      finishReview = null;
      finishSubmitting = false;
      finishNativeSubmit = false;
    }
  }

  async function postTimingRequest(url, fields, signal = undefined) {
    const body = new FormData();
    Object.entries(fields).forEach(([name, value]) => body.set(name, value));
    const response = await fetch(url, {
      method: "POST",
      headers: { "Accept": "application/json" },
      body,
      signal,
    });
    const responsePayload = await response.json();
    return { response, responsePayload };
  }

  function applyEditorPreview(preview) {
    const mapped = mapServerPreview(state.rows, preview);
    state.rows = mapped.rows;
    state.productionSeconds = mapped.production_seconds;
    state.pausedSeconds = mapped.paused_seconds;
    clearAlert();
    renderRows();
    updateTotals();
    updateDraftInput();
  }

  async function requestOrdinaryPreview() {
    if (
      shiftSuspended
      || state.locked
      || state.mode !== "ordinary"
      || overlay.hidden
      || incompleteDraftFields(state.rows, requiredDraftStatus()).length > 0
    ) {
      setPreviewLoading(false);
      return;
    }
    setPreviewLoading(true);
    const pendingPreview = previewCoordinator.request((signal) => postTimingRequest(
      `${saveForm.action}/preview`,
      {
        loaded_version: saveForm.querySelector("input[name='loaded_version']").value,
        timing_draft: JSON.stringify(serializeTimingDraft(state.rows)),
      },
      signal,
    ));
    const requestGeneration = previewCoordinator.generation();
    try {
      const outcome = await pendingPreview;
      if (!outcome.applied) {
        return;
      }
      const { response, responsePayload } = outcome.value;
      if (!response.ok || !responsePayload.ok) {
        if (response.status === 409) {
          lockTimingDraft(responsePayload.messages);
        }
        renderServerErrors(responsePayload.field_errors || []);
        return;
      }
      applyEditorPreview(responsePayload.preview);
    } catch {
      showAlert(["Предварителното изчисление не беше обновено. Опитайте отново."]);
    } finally {
      if (previewCoordinator.generation() === requestGeneration) {
        setPreviewLoading(false);
      }
    }
  }

  async function beginFinishReview() {
    if (finishSubmitting) {
      return;
    }
    finishSubmitting = true;
    const trigger = activeFinishForm.querySelector("button[type='submit']");
    trigger.disabled = true;
    const loadedVersion = activeFinishForm.querySelector("input[name='loaded_version']").value;
    try {
      const outcome = await previewCoordinator.request((signal) => postTimingRequest(
        `${activeFinishForm.action}-review`,
        { loaded_version: loadedVersion },
        signal,
      ));
      if (!outcome.applied) {
        return;
      }
      const { response, responsePayload } = outcome.value;
      if (shiftSuspended) {
        return;
      }
      if (!response.ok || !responsePayload.ok) {
        finishReview = {
          reviewToken: "",
          draft: cloneRows(timing.draft),
          preview: timing.display,
        };
        finishReturnFocus = trigger;
        const hasRowErrors = (responsePayload.field_errors || []).some(
          (issue) => Number.isSafeInteger(issue.source_index) && issue.field !== "form",
        );
        if (response.status === 409 || hasRowErrors) {
          openEditor({
            opener: trigger,
            mode: "finish",
            rows: finishReview.draft,
            preview: finishReview.preview,
          });
          if (response.status === 409) {
            lockTimingDraft(responsePayload.messages);
          }
          renderServerErrors(responsePayload.field_errors || []);
          return;
        }
        openFinishSummary({ opener: trigger, focusTarget: finishCancelButton });
        showFinishAlert(responsePayload.messages || ["Действието не беше изпълнено."]);
        focusFinishAlert();
        finishConfirmButton.disabled = true;
        finishEditButton.disabled = true;
        return;
      }
      finishReview = {
        reviewToken: responsePayload.review_token,
        draft: cloneRows(responsePayload.preview.draft),
        preview: responsePayload.preview,
      };
      finishReturnFocus = trigger;
      openFinishSummary({ opener: trigger });
    } catch {
      finishReview = {
        reviewToken: "",
        draft: cloneRows(timing.draft),
        preview: timing.display,
      };
      finishReturnFocus = trigger;
      openFinishSummary({ opener: trigger, focusTarget: finishCancelButton });
      showFinishAlert(["Действието не беше изпълнено. Опитайте отново."]);
      focusFinishAlert();
      finishConfirmButton.disabled = true;
      finishEditButton.disabled = true;
    } finally {
      finishSubmitting = false;
      trigger.disabled = false;
    }
  }

  async function applyFinishDraft() {
    submitting = true;
    saveButton.disabled = true;
    setPreviewLoading(true);
    const loadedVersion = activeFinishForm.querySelector("input[name='loaded_version']").value;
    const pendingPreview = previewCoordinator.request((signal) => postTimingRequest(
      `${activeFinishForm.action}-review/preview`,
      {
        loaded_version: loadedVersion,
        review_token: finishReview.reviewToken,
        timing_draft: JSON.stringify(serializeTimingDraft(state.rows)),
      },
      signal,
    ));
    const requestGeneration = previewCoordinator.generation();
    try {
      const outcome = await pendingPreview;
      if (!outcome.applied) {
        return;
      }
      const { response, responsePayload } = outcome.value;
      if (shiftSuspended) {
        return;
      }
      if (!response.ok || !responsePayload.ok) {
        if (response.status === 409) {
          lockTimingDraft(responsePayload.messages);
        }
        renderServerErrors(responsePayload.field_errors || []);
        return;
      }
      finishReview.draft = cloneRows(responsePayload.preview.draft);
      finishReview.preview = responsePayload.preview;
      closeEditor({ restoreFocus: false, preserveBackground: true });
      openFinishSummary({ opener: finishEditButton, focusTarget: finishEditButton });
    } catch {
      showAlert(["Действието не беше изпълнено. Опитайте отново."]);
    } finally {
      submitting = false;
      saveButton.disabled = state.locked;
      if (previewCoordinator.generation() === requestGeneration) {
        setPreviewLoading(false);
      }
    }
  }

  function hiddenFinishField(name) {
    let input = activeFinishForm.querySelector(`input[name="${name}"]`);
    if (!input) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      activeFinishForm.append(input);
    }
    return input;
  }

  function confirmFinishReview() {
    if (finishSubmitting || !finishReview) {
      return;
    }
    finishSubmitting = true;
    finishConfirmButton.disabled = true;
    const tokenInput = hiddenFinishField("review_token");
    tokenInput.name = "review_token";
    tokenInput.value = finishReview.reviewToken;
    const timingInput = hiddenFinishField("timing_draft");
    timingInput.name = "timing_draft";
    timingInput.value = JSON.stringify(serializeTimingDraft(finishReview.draft));
    finishNativeSubmit = true;
    try {
      activeFinishForm.requestSubmit();
    } finally {
      finishNativeSubmit = false;
    }
  }

  menuButton.addEventListener("click", () => {
    if (menuPanel.hidden) {
      openMenu();
    } else {
      closeMenu({ restoreFocus: true });
    }
  });
  menuButton.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      openMenu({ focusItem: true });
    }
  });
  menuAction.addEventListener("click", () => {
    if (menuButton.disabled) {
      closeMenu();
      return;
    }
    closeMenu();
    openEditor({ opener: menuButton });
  });
  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) {
      const restoreFocus = menuPanel.contains(document.activeElement);
      closeMenu({ restoreFocus });
    }
  });
  document.addEventListener("terminal:roll-correction-open", () => {
    closeMenu({ restoreFocus: menuPanel.contains(document.activeElement) });
  });

  addButton.addEventListener("click", () => {
    invalidatePreviewDraft();
    state.rows = addIntervalDraft(state.rows, requiredDraftStatus());
    clearAlert();
    renderRows();
    updateDraftInput();
    const first = incompleteDraftFields(state.rows, requiredDraftStatus())[0];
    fieldInput(first?.source_index, first?.field)?.focus();
  });
  cancelButton.addEventListener("click", cancelEditor);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay && !state.locked) {
      state.mode === "finish" ? cancelEditor() : closeEditor();
    }
  });
  saveForm.addEventListener("submit", (event) => {
    if (submitting || state.locked) {
      event.preventDefault();
      return;
    }
    if (incompleteDraftFields(state.rows, requiredDraftStatus()).length > 0) {
      event.preventDefault();
      showAlert(["Попълнете всички задължителни дата и час."]);
      focusFirstIncomplete();
      return;
    }
    if (state.mode === "finish") {
      event.preventDefault();
      applyFinishDraft();
      return;
    }
    updateDraftInput();
    submitting = true;
    saveButton.disabled = true;
  });

  activeFinishForm.addEventListener("submit", (event) => {
    if (finishNativeSubmit) {
      return;
    }
    event.preventDefault();
    if (finishSubmitting) {
      return;
    }
    beginFinishReview();
  });
  finishEditButton.addEventListener("click", () => {
    if (!finishReview) {
      return;
    }
    closeFinishSummary({ restoreFocus: false, preserveBackground: true });
    openEditor({
      opener: finishEditButton,
      mode: "finish",
      rows: finishReview.draft,
      preview: finishReview.preview,
    });
  });
  finishCancelButton.addEventListener("click", () => closeFinishSummary());
  finishConfirmButton.addEventListener("click", confirmFinishReview);

  window.addEventListener("terminal:card-stale", (event) => {
    previewCoordinator.invalidate({ stale: true });
    if (overlay.hidden && finishOverlay.hidden) {
      return;
    }
    event.preventDefault();
    const staleMessages = [
      "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    ];
    if (!finishOverlay.hidden && finishReview) {
      closeFinishSummary({ restoreFocus: false, preserveBackground: true });
      openEditor({
        opener: finishReturnFocus,
        mode: "finish",
        rows: finishReview.draft,
        preview: finishReview.preview,
      });
    }
    lockTimingDraft(staleMessages);
  }, { capture: true });

  window.addEventListener("terminal:shift-stale", () => {
    previewCoordinator.invalidate({ suspend: true });
    setPreviewLoading(false);
    shiftSuspended = true;
    closeMenu();
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    dialog.setAttribute("aria-modal", "false");
    finishOverlay.hidden = true;
    finishOverlay.setAttribute("aria-hidden", "true");
    finishDialog.setAttribute("aria-modal", "false");
    setBackgroundIsolated(false);
  }, { capture: true });

  document.addEventListener("terminal:server-time", () => {
    if (
      !overlay.hidden
      && state.mode === "ordinary"
      && state.status === "running"
      && !state.locked
      && incompleteDraftFields(state.rows, requiredDraftStatus()).length === 0
    ) {
      requestOrdinaryPreview();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (!overlay.hidden) {
      if (event.key === "Tab") {
        trapDialogFocus(event);
      } else if (event.key === "Escape") {
        event.preventDefault();
        cancelEditor();
      }
      return;
    }
    if (!finishOverlay.hidden) {
      if (event.key === "Tab") {
        trapFinishFocus(event);
      } else if (event.key === "Escape") {
        event.preventDefault();
        closeFinishSummary();
      }
      return;
    }
    if (!menuPanel.hidden && event.key === "Escape") {
      event.preventDefault();
      closeMenu({ restoreFocus: true });
    }
  });

  if (model.editor_open) {
    openEditor({ opener: menuButton, previewOnOpen: false });
    if (Array.isArray(model.issues) && model.issues.length > 0) {
      renderServerErrors(model.issues);
    }
  }
  if (model.finish_review?.open) {
    const retainedDraft = model.finish_review.draft.length > 0
      ? model.finish_review.draft
      : timing.draft;
    const retainedMessages = retainedFinishReviewMessages(model.finish_review);
    finishReview = {
      reviewToken: model.finish_review.review_token,
      draft: cloneRows(retainedDraft),
      preview: retainedFinishPreview(model.finish_review, retainedDraft),
    };
    const loadedVersionInput = activeFinishForm.querySelector(
      "input[name='loaded_version']",
    );
    loadedVersionInput.value = String(model.finish_review.loaded_version);
    const mustShowEditor = model.finish_review.locked || model.finish_review.issues.some(
      (issue) => Number.isSafeInteger(issue.source_index) && issue.field !== "form",
    );
    if (mustShowEditor) {
      openEditor({
        opener: activeFinishForm.querySelector("button[type='submit']"),
        mode: "finish",
        rows: finishReview.draft,
        preview: finishReview.preview,
      });
      if (model.finish_review.locked) {
        lockTimingDraft(retainedMessages);
      }
      renderServerErrors(model.finish_review.issues, {
        finish: true,
        preserveAlert: model.finish_review.locked,
      });
    } else {
      openFinishSummary({
        opener: activeFinishForm.querySelector("button[type='submit']"),
        focusTarget: finishCancelButton,
      });
      showFinishAlert(retainedMessages);
      finishEditButton.disabled = retainedMessages.length > 0;
      finishConfirmButton.disabled = retainedMessages.length > 0;
      if (retainedMessages.length > 0) {
        focusFinishAlert();
      }
    }
  }
}
