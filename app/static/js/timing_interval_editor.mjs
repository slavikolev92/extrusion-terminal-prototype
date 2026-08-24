import {
  addIntervalDraft,
  canDeleteTimingRow,
  dateSegmentsFromValue,
  dateValueFromSegments,
  formatFinishBoundary,
  incompleteDraftFields,
  mapServerPreview,
  markIntervalDeleted,
  maskedBackspaceEdit,
  maskTimeInput,
  maskedCaretPosition,
  normalizeDraftDateInputs,
  remapFocusedTimingField,
  serializeTimingDraft,
  visibleTimingRows,
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

export function initialFinishReviewHydration(
  finishReview,
  timingDraft,
  timingDisplay,
) {
  return {
    draft: finishReview.draft.length > 0 ? finishReview.draft : timingDraft,
    preview: finishReview.preview || timingDisplay,
    locked: Boolean(finishReview.locked),
    lockedMessages: retainedFinishReviewMessages(finishReview),
  };
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
const deleteConfirmOverlay = overlay?.querySelector("[data-timing-delete-confirm-overlay]");
const deleteConfirmDialog = deleteConfirmOverlay?.querySelector("[data-timing-delete-confirm-dialog]");
const deleteConfirmPrompt = deleteConfirmOverlay?.querySelector("[data-timing-delete-confirm-prompt]");
const deleteConfirmCancel = deleteConfirmOverlay?.querySelector("[data-timing-delete-confirm-cancel]");
const deleteConfirmSubmit = deleteConfirmOverlay?.querySelector("[data-timing-delete-confirm-submit]");
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
    && saveButton && deleteConfirmOverlay && deleteConfirmDialog
    && deleteConfirmPrompt && deleteConfirmCancel && deleteConfirmSubmit
    && activeFinishForm && finishOverlay && finishDialog && finishAlert
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
  let timingActionPointerDown = false;
  let previewRenderInProgress = false;
  let pendingDeleteConfirmation = null;
  const previewCoordinator = createPreviewCoordinator();

  function cloneRows(rows) {
    return rows.map((row) => ({ ...row }));
  }

  function createInitialState(
    rows = timing.draft,
    previewPayload = timing.display,
    mode = "ordinary",
    { locked = Boolean(timing.locked) } = {},
  ) {
    const preview = mapServerPreview(
      normalizeDraftDateInputs(cloneRows(rows)),
      previewPayload,
      { normalizeOrder: !locked },
    );
    return {
      status: timing.status,
      mode,
      rows: preview.rows,
      productionSeconds: preview.production_seconds,
      pausedSeconds: preview.paused_seconds,
      locked,
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
    return `${hours} ч ${String(minutes).padStart(2, "0")} м`;
  }

  function retainedFinishPreview(finishModel, draft) {
    void draft;
    if (!finishModel.preview) {
      return timing.display;
    }
    return finishModel.preview;
  }

  function updateDraftInput() {
    draftInput.value = JSON.stringify(serializeTimingDraft(state.rows));
  }

  function updateTotals() {
    productionTotal.textContent = formatDuration(state.productionSeconds);
    pausedTotal.textContent = formatDuration(state.pausedSeconds);
  }

  function updateRenderedDuration(sourceIndex) {
    const row = state.rows[sourceIndex];
    const duration = intervalList.querySelector(
      `.interval-row[data-source-index="${sourceIndex}"] .interval-duration`,
    );
    if (row && duration) {
      duration.textContent = row.deleted ? "—" : formatDuration(row.duration_seconds);
    }
  }

  function focusedTimingField() {
    const activeElement = document.activeElement;
    if (!activeElement || !intervalList.contains(activeElement)) {
      return null;
    }
    const sourceIndex = Number(activeElement.dataset.sourceIndex);
    const field = activeElement.dataset.timingCombinedField
      || activeElement.dataset.timingField;
    if (!Number.isSafeInteger(sourceIndex) || !field) {
      return null;
    }
    return {
      sourceIndex,
      field,
      dateSegment: activeElement.dataset.dateSegment || null,
      selectionStart: activeElement.selectionStart,
      selectionEnd: activeElement.selectionEnd,
    };
  }

  function restoreFocusedTimingField(focusedField, sourceIndexMap) {
    const remappedField = remapFocusedTimingField(focusedField, sourceIndexMap);
    if (!remappedField) {
      return;
    }
    const inputs = fieldInputs(remappedField.sourceIndex, remappedField.field);
    const target = remappedField.dateSegment
      ? inputs.find((input) => input.dataset.dateSegment === remappedField.dateSegment)
      : inputs[0];
    if (!target || target.disabled) {
      return;
    }
    target.focus({ preventScroll: true });
    if (
      Number.isSafeInteger(remappedField.selectionStart)
      && Number.isSafeInteger(remappedField.selectionEnd)
      && typeof target.setSelectionRange === "function"
    ) {
      const selectionStart = Math.min(remappedField.selectionStart, target.value.length);
      const selectionEnd = Math.min(remappedField.selectionEnd, target.value.length);
      target.setSelectionRange(selectionStart, selectionEnd);
    }
  }

  function focusedTimingAction() {
    const activeElement = document.activeElement;
    if (activeElement === addButton) {
      return { action: "add", sourceIndex: null };
    }
    if (
      !activeElement
      || !intervalList.contains(activeElement)
      || activeElement.dataset.timingAction !== "delete"
    ) {
      return null;
    }
    const sourceIndex = Number(activeElement.dataset.sourceIndex);
    return Number.isSafeInteger(sourceIndex)
      ? { action: "delete", sourceIndex }
      : null;
  }

  function restoreFocusedTimingAction(focusedAction, sourceIndexMap) {
    if (!focusedAction) {
      return;
    }
    if (focusedAction.action === "add") {
      if (!addButton.disabled) addButton.focus({ preventScroll: true });
      return;
    }
    const sourceIndex = sourceIndexMap[focusedAction.sourceIndex];
    if (!Number.isSafeInteger(sourceIndex)) {
      return;
    }
    const action = intervalList.querySelector(
      `[data-source-index="${sourceIndex}"]`
        + '[data-timing-action="delete"]:not([disabled])',
    );
    action?.focus({ preventScroll: true });
  }

  function invalidateDisplayedCalculations(sourceIndexes = []) {
    sourceIndexes.forEach((sourceIndex) => {
      if (state.rows[sourceIndex]) {
        state.rows[sourceIndex] = {
          ...state.rows[sourceIndex],
          duration_seconds: null,
        };
        updateRenderedDuration(sourceIndex);
      }
    });
    state.productionSeconds = null;
    state.pausedSeconds = null;
    updateTotals();
  }

  function setPreviewLoading(loading) {
    totals.classList.toggle("timing-dialog-loading", loading);
    totals.setAttribute("aria-busy", loading ? "true" : "false");
  }

  function setEditorSubmitting(active) {
    submitting = active;
    dialog.setAttribute("aria-busy", active ? "true" : "false");
    intervalList.querySelectorAll("input").forEach((input) => {
      input.readOnly = active;
    });
    addButton.disabled = active || state.locked;
    cancelButton.disabled = active;
    saveButton.disabled = active || state.locked;
    intervalList.querySelectorAll("[data-timing-action]").forEach((button) => {
      button.disabled = active || state.locked;
    });
  }

  function invalidatePreviewDraft() {
    previewCoordinator.invalidate();
    setPreviewLoading(false);
  }

  function clearAlert() {
    clearServerErrorState();
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
    return fieldInputs(sourceIndex, field)[0] || null;
  }

  function fieldInputs(sourceIndex, field) {
    const dateGroup = intervalList.querySelector(
      `[data-source-index="${sourceIndex}"][data-timing-date-field="${field}"]`,
    );
    if (dateGroup) {
      return Array.from(dateGroup.querySelectorAll("input"));
    }
    return Array.from(intervalList.querySelectorAll(
      `[data-source-index="${sourceIndex}"][data-timing-field="${field}"]`,
    ));
  }

  function clearServerErrorState() {
    intervalList.querySelectorAll("[aria-invalid='true']").forEach((input) => {
      input.removeAttribute("aria-invalid");
      input.removeAttribute("aria-describedby");
    });
  }

  function renderServerErrors(
    issues,
    { focus = false, preserveAlert = false } = {},
  ) {
    clearServerErrorState();
    const formMessages = [];
    const invalidSourceIndexes = new Set();
    let firstEditableTarget = null;
    issues.forEach((issue) => {
      formMessages.push(issue.message);
      if (!Number.isSafeInteger(issue.source_index) || issue.field === "form") {
        return;
      }
      invalidSourceIndexes.add(issue.source_index);
      const prefix = issue.field.startsWith("start_") ? "start" : "stop";
      const targetFields = issue.field.endsWith("_date")
        ? [issue.field]
        : [`${prefix}_date`, `${prefix}_time`];
      targetFields.forEach((field) => {
        const inputs = fieldInputs(issue.source_index, field);
        if (inputs.length === 0) {
          return;
        }
        inputs.forEach((input) => {
          input.setAttribute("aria-invalid", "true");
          input.setAttribute("aria-describedby", "timing-dialog-alert");
        });
        const input = inputs.find((candidate) => !candidate.disabled);
        firstEditableTarget ||= input || null;
      });
    });
    if (formMessages.length > 0 && !state.locked) {
      invalidateDisplayedCalculations(invalidSourceIndexes);
    }
    if (!preserveAlert) {
      if (formMessages.length > 0) {
        showAlert(formMessages, { stale: state.locked });
      } else {
        clearAlert();
      }
      if (focus && firstEditableTarget) {
        window.requestAnimationFrame(() => firstEditableTarget.focus());
      } else if (focus && formMessages.length > 0) {
        window.requestAnimationFrame(() => {
          alertBox.focus?.();
        });
      }
    }
  }

  function lockTimingDraft(messages = ["Данните са променени. Презаредете картата."]) {
    previewCoordinator.invalidate({ stale: true });
    setPreviewLoading(false);
    closeDeleteConfirmation({ restoreFocus: false });
    state.locked = true;
    if (state.mode === "finish" && finishReview) {
      finishReview.locked = true;
      finishReview.lockMessages = [...new Set(messages.filter(Boolean))];
    }
    renderRows();
    addButton.disabled = true;
    saveButton.disabled = true;
    reloadLink.hidden = false;
    finishEditButton.disabled = true;
    finishConfirmButton.disabled = true;
    showAlert(messages, { stale: true });
    reloadLink.focus();
  }

  function persistFieldValue(sourceIndex, field, value) {
    invalidatePreviewDraft();
    state.rows[sourceIndex] = {
      ...state.rows[sourceIndex],
      [field]: value,
      duration_seconds: null,
    };
    invalidateDisplayedCalculations([sourceIndex]);
    clearAlert();
    updateDraftInput();
  }

  function requestPreviewAfterFieldExit() {
    if (
      !submitting
      && !timingActionPointerDown
      && !previewRenderInProgress
      && incompleteDraftFields(state.rows, requiredDraftStatus()).length === 0
    ) {
      requestEditorPreview();
    }
  }

  function createTimeInput(row, sourceIndex, field) {
    const input = document.createElement("input");
    input.dataset.sourceIndex = String(sourceIndex);
    input.dataset.timingField = field;
    input.disabled = state.locked || row.deleted;
    input.setAttribute(
      "aria-label",
      timingFieldAccessibleName(row.display_number, field),
    );
    input.type = "text";
    input.inputMode = "numeric";
    input.maxLength = 5;
    input.autocomplete = "off";
    input.placeholder = "чч:мм";
    input.value = row[field] || "";
    const selectTimeSegment = () => {
      if (input.disabled) {
        return;
      }
      const caret = input.selectionStart ?? 0;
      const segmentStart = caret >= 3 ? 3 : 0;
      const segmentEnd = Math.min(segmentStart + 2, input.value.length);
      input.setSelectionRange(segmentStart, segmentEnd);
    };
    input.addEventListener("click", selectTimeSegment);
    input.addEventListener("keydown", (event) => {
      if (input.readOnly || event.key !== "Backspace") {
        return;
      }
      const edit = maskedBackspaceEdit(
        input.value,
        input.selectionStart,
        input.selectionEnd,
      );
      if (!edit) {
        return;
      }
      event.preventDefault();
      input.value = edit.value;
      input.setSelectionRange(edit.caret, edit.caret);
      persistFieldValue(sourceIndex, field, edit.value);
    });
    input.addEventListener("input", () => {
      const rawValue = input.value;
      const rawCaret = input.selectionStart ?? rawValue.length;
      const digitsBeforeCaret = rawValue
        .slice(0, rawCaret)
        .replace(/\D/g, "").length;
      const value = maskTimeInput(rawValue).value;
      input.value = value;
      const caret = maskedCaretPosition(value, digitsBeforeCaret);
      input.setSelectionRange(caret, caret);
      persistFieldValue(sourceIndex, field, value);
    });
    input.addEventListener("blur", requestPreviewAfterFieldExit);
    return input;
  }

  function createSegmentedDateInput(row, sourceIndex, field) {
    const group = document.createElement("div");
    group.className = "segmented-date-input";
    group.dataset.sourceIndex = String(sourceIndex);
    group.dataset.timingDateField = field;
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", timingFieldAccessibleName(row.display_number, field));

    const values = dateSegmentsFromValue(row[field] || "");
    const definitions = [
      { key: "day", label: "ден", maxLength: 2, placeholder: "дд" },
      { key: "month", label: "месец", maxLength: 2, placeholder: "мм" },
      { key: "year", label: "година", maxLength: 4, placeholder: "гггг" },
    ];
    const inputs = [];

    const selectInput = (input) => {
      if (!input || input.disabled) {
        return;
      }
      input.focus({ preventScroll: true });
      input.select();
    };

    const combinedValue = () => dateValueFromSegments(Object.fromEntries(
      inputs.map((input) => [input.dataset.dateSegment, input.value]),
    ));

    definitions.forEach((definition, index) => {
      if (index > 0) {
        const separator = document.createElement("span");
        separator.className = "date-segment-separator";
        separator.textContent = "/";
        separator.setAttribute("aria-hidden", "true");
        group.append(separator);
      }

      const input = document.createElement("input");
      input.type = "text";
      input.inputMode = "numeric";
      input.maxLength = definition.maxLength;
      input.autocomplete = "off";
      input.placeholder = definition.placeholder;
      input.value = values[definition.key];
      input.disabled = state.locked || row.deleted;
      input.dataset.sourceIndex = String(sourceIndex);
      input.dataset.dateSegment = definition.key;
      input.dataset.timingCombinedField = field;
      if (index === 0) {
        input.dataset.timingField = field;
      }
      input.setAttribute(
        "aria-label",
        `${timingFieldAccessibleName(row.display_number, field)}, ${definition.label}`,
      );
      input.addEventListener("focus", () => input.select());
      input.addEventListener("click", () => input.select());
      input.addEventListener("input", () => {
        input.value = input.value.replace(/\D/g, "").slice(0, definition.maxLength);
        persistFieldValue(sourceIndex, field, combinedValue());
        if (input.value.length === definition.maxLength) {
          selectInput(inputs[index + 1]);
        }
      });
      input.addEventListener("keydown", (event) => {
        const previous = inputs[index - 1];
        const next = inputs[index + 1];
        const selectionStart = input.selectionStart ?? 0;
        const selectionEnd = input.selectionEnd ?? selectionStart;
        if ((event.key === "." || event.key === "/") && next) {
          event.preventDefault();
          selectInput(next);
        } else if (
          event.key === "ArrowRight"
          && selectionStart === input.value.length
          && selectionEnd === selectionStart
          && next
        ) {
          event.preventDefault();
          selectInput(next);
        } else if (
          event.key === "ArrowLeft"
          && selectionStart === 0
          && selectionEnd === 0
          && previous
        ) {
          event.preventDefault();
          selectInput(previous);
        } else if (
          event.key === "Backspace"
          && input.value === ""
          && selectionStart === 0
          && previous
        ) {
          event.preventDefault();
          selectInput(previous);
        }
      });
      inputs.push(input);
      group.append(input);
    });

    group.addEventListener("focusout", (event) => {
      if (event.relatedTarget && group.contains(event.relatedTarget)) {
        return;
      }
      requestPreviewAfterFieldExit();
    });
    return group;
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
    const input = field.endsWith("_date")
      ? createSegmentedDateInput(row, sourceIndex, field)
      : createTimeInput(row, sourceIndex, field);
    wrapper.append(input);
    return wrapper;
  }

  function closeDeleteConfirmation({ restoreFocus = true } = {}) {
    if (deleteConfirmOverlay.hidden) {
      return;
    }
    const opener = pendingDeleteConfirmation?.opener || null;
    deleteConfirmOverlay.hidden = true;
    deleteConfirmOverlay.setAttribute("aria-hidden", "true");
    dialog.removeAttribute("inert");
    pendingDeleteConfirmation = null;
    if (restoreFocus && opener?.isConnected && !opener.disabled) {
      opener.focus({ preventScroll: true });
    }
  }

  function openDeleteConfirmation({ row, sourceIndex, visibleIndex, opener }) {
    if (state.locked || submitting || opener.disabled) {
      return;
    }
    pendingDeleteConfirmation = {
      sourceIndex,
      visibleIndex,
      opener,
    };
    deleteConfirmPrompt.textContent = `Сигурни ли сте, че искате да изтриете интервал №${row.display_number}?`;
    dialog.setAttribute("inert", "");
    deleteConfirmOverlay.hidden = false;
    deleteConfirmOverlay.setAttribute("aria-hidden", "false");
    deleteConfirmCancel.focus({ preventScroll: true });
  }

  function confirmIntervalDelete() {
    const pending = pendingDeleteConfirmation;
    if (!pending || state.locked || submitting) {
      closeDeleteConfirmation({ restoreFocus: !state.locked });
      return;
    }
    const { sourceIndex, visibleIndex } = pending;
    closeDeleteConfirmation({ restoreFocus: false });
    invalidatePreviewDraft();
    state.rows = markIntervalDeleted(state.rows, sourceIndex);
    invalidateDisplayedCalculations();
    clearAlert();
    renderRows();
    updateDraftInput();
    window.requestAnimationFrame(() => {
      const renderedRows = Array.from(intervalList.querySelectorAll(".interval-row"));
      const nextAction = renderedRows[visibleIndex]?.querySelector(
        '[data-timing-action="delete"]:not([disabled])',
      );
      const previousAction = renderedRows[visibleIndex - 1]?.querySelector(
        '[data-timing-action="delete"]:not([disabled])',
      );
      (nextAction || previousAction || addButton).focus({ preventScroll: true });
    });
    if (incompleteDraftFields(state.rows, requiredDraftStatus()).length === 0) {
      requestEditorPreview();
    }
  }

  function renderRows() {
    intervalList.replaceChildren();
    const visibleRows = visibleTimingRows(state.rows);

    visibleRows.forEach(({ row, sourceIndex }, visibleIndex) => {
      const rowElement = document.createElement("div");
      rowElement.className = "interval-row";
      rowElement.dataset.sourceIndex = String(sourceIndex);

      const numberCell = document.createElement("div");
      numberCell.className = "interval-number";
      numberCell.textContent = String(row.display_number ?? sourceIndex + 1);

      const startCell = document.createElement("div");
      startCell.append(createTimestampControls(row, sourceIndex, "start"));

      const stopCell = document.createElement("div");
      const finalOpen = state.mode === "ordinary"
        && state.status === "running"
        && visibleIndex === visibleRows.length - 1;
      if (finalOpen) {
        stopCell.replaceChildren();
      } else {
        stopCell.append(createTimestampControls(row, sourceIndex, "stop"));
      }

      const durationCell = document.createElement("div");
      durationCell.className = "interval-duration";
      durationCell.textContent = formatDuration(row.duration_seconds);

      const actionCell = document.createElement("div");
      if (canDeleteTimingRow(state.rows, sourceIndex, {
        mode: state.mode,
        status: state.status,
      })) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "interval-delete";
        button.dataset.sourceIndex = String(sourceIndex);
        button.dataset.timingAction = "delete";
        button.textContent = "Изтрий";
        button.setAttribute("aria-label", `Изтрий интервал ${row.display_number}`);
        button.disabled = state.locked;
        button.addEventListener("click", () => openDeleteConfirmation({
          row,
          sourceIndex,
          visibleIndex,
          opener: button,
        }));
        actionCell.append(button);
      }
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

  function trapDeleteConfirmationFocus(event) {
    const focusable = [deleteConfirmCancel, deleteConfirmSubmit].filter(
      (element) => !element.disabled,
    );
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first || !last) {
      event.preventDefault();
      deleteConfirmDialog.focus();
    } else if (!deleteConfirmDialog.contains(document.activeElement)) {
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
    locked = Boolean(timing.locked),
    lockedMessages = null,
  } = {}) {
    if (shiftSuspended) {
      return;
    }
    modalReturnFocus = opener;
    state = createInitialState(rows, preview, mode, { locked });
    setEditorSubmitting(false);
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
      lockTimingDraft(lockedMessages || undefined);
    } else {
      dialog.focus();
      if (mode === "ordinary" && previewOnOpen) {
        requestOrdinaryPreview();
      }
    }
  }

  function closeEditor({ restoreFocus = true, preserveBackground = false } = {}) {
    if (submitting) {
      return;
    }
    invalidatePreviewDraft();
    closeDeleteConfirmation({ restoreFocus: false });
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    if (!preserveBackground) {
      setBackgroundIsolated(false);
    }
    setEditorSubmitting(false);
    if (restoreFocus) {
      (modalReturnFocus || menuButton).focus({ preventScroll: true });
    }
    modalReturnFocus = null;
  }

  function cancelEditor() {
    if (submitting) {
      return;
    }
    if (state.mode !== "finish") {
      if (state.locked && state.status === "cancelled") {
        window.location.assign(reloadLink.href);
        return;
      }
      closeEditor();
      return;
    }
    closeEditor({ restoreFocus: false, preserveBackground: true });
    openFinishSummary({ opener: finishEditButton, focusTarget: finishEditButton });
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
    finishFirstStart.textContent = formatFinishBoundary(preview.first_start_display);
    finishProposedStop.textContent = formatFinishBoundary(preview.proposed_stop_display);
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
    const locked = Boolean(finishReview?.locked);
    showFinishAlert(locked ? finishReview.lockMessages || [] : []);
    renderFinishPreview(finishReview.preview);
    finishDialog.setAttribute("aria-busy", "false");
    finishConfirmButton.disabled = locked;
    finishEditButton.disabled = locked;
    finishCancelButton.disabled = false;
    finishOverlay.hidden = false;
    finishOverlay.setAttribute("aria-hidden", "false");
    setBackgroundIsolated(true);
    (locked ? finishCancelButton : focusTarget).focus();
  }

  function closeFinishSummary({ restoreFocus = true, preserveBackground = false } = {}) {
    if (finishSubmitting) {
      return;
    }
    invalidatePreviewDraft();
    finishOverlay.hidden = true;
    finishOverlay.setAttribute("aria-hidden", "true");
    finishConfirmButton.disabled = false;
    finishEditButton.disabled = false;
    finishCancelButton.disabled = false;
    finishDialog.setAttribute("aria-busy", "false");
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

  function cancelFinishSummary() {
    if (finishReview?.locked && timing.status === "cancelled") {
      window.location.assign(reloadLink.href);
      return;
    }
    closeFinishSummary();
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
    const focusedField = focusedTimingField();
    const focusedAction = focusedTimingAction();
    const mapped = mapServerPreview(state.rows, preview);
    state.rows = mapped.rows;
    state.productionSeconds = mapped.production_seconds;
    state.pausedSeconds = mapped.paused_seconds;
    clearAlert();
    previewRenderInProgress = true;
    try {
      renderRows();
      updateTotals();
      updateDraftInput();
      restoreFocusedTimingField(focusedField, mapped.source_index_map);
      if (!focusedField) {
        restoreFocusedTimingAction(focusedAction, mapped.source_index_map);
      }
    } finally {
      previewRenderInProgress = false;
    }
    return mapped;
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

  function requestEditorPreview() {
    return state.mode === "finish"
      ? requestFinishEditorPreview()
      : requestOrdinaryPreview();
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
        const hasRowErrors = (responsePayload.field_errors || []).some(
          (issue) => Number.isSafeInteger(issue.source_index) && issue.field !== "form",
        );
        if (response.status === 409) {
          finishReview = {
            reviewToken: "",
            draft: cloneRows(timing.draft),
            preview: timing.display,
          };
          finishReturnFocus = trigger;
          openEditor({
            opener: trigger,
            mode: "finish",
            rows: finishReview.draft,
            preview: finishReview.preview,
          });
          lockTimingDraft(responsePayload.messages);
          renderServerErrors(responsePayload.field_errors || [], { focus: true });
          return;
        }
        if (hasRowErrors) {
          finishReview = null;
          finishReturnFocus = null;
          openEditor({
            opener: trigger,
            mode: "ordinary",
            rows: timing.draft,
            preview: timing.display,
            previewOnOpen: false,
          });
          renderServerErrors([
            {
              source_index: null,
              field: "form",
              message: "Коригирайте времето, запишете промените и опитайте да приключите отново.",
            },
            ...(responsePayload.field_errors || []),
          ], { focus: true });
          return;
        }
        finishReview = {
          reviewToken: "",
          draft: cloneRows(timing.draft),
          preview: timing.display,
        };
        finishReturnFocus = trigger;
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

  async function requestFinishEditorPreview({ returnToSummary = false } = {}) {
    if (
      shiftSuspended
      || state.locked
      || state.mode !== "finish"
      || overlay.hidden
      || incompleteDraftFields(state.rows, requiredDraftStatus()).length > 0
    ) {
      setPreviewLoading(false);
      return;
    }
    if (returnToSummary) {
      setEditorSubmitting(true);
    }
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
        renderServerErrors(responsePayload.field_errors || [], {
          focus: returnToSummary,
        });
        return;
      }
      const mapped = applyEditorPreview(responsePayload.preview);
      if (returnToSummary) {
        finishReview.draft = cloneRows(state.rows);
        finishReview.preview = mapped.normalized_preview;
        setEditorSubmitting(false);
        closeEditor({ restoreFocus: false, preserveBackground: true });
        openFinishSummary({ opener: finishEditButton, focusTarget: finishEditButton });
      }
    } catch {
      showAlert(["Действието не беше изпълнено. Опитайте отново."]);
    } finally {
      if (returnToSummary) {
        setEditorSubmitting(false);
      }
      if (previewCoordinator.generation() === requestGeneration) {
        setPreviewLoading(false);
      }
    }
  }

  async function applyFinishDraft() {
    return requestFinishEditorPreview({ returnToSummary: true });
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
    finishCancelButton.disabled = true;
    finishEditButton.disabled = true;
    finishDialog.setAttribute("aria-busy", "true");
    const tokenInput = hiddenFinishField("review_token");
    tokenInput.name = "review_token";
    tokenInput.value = finishReview.reviewToken;
    const timingInput = hiddenFinishField("timing_draft");
    timingInput.name = "timing_draft";
    timingInput.value = JSON.stringify(serializeTimingDraft(finishReview.draft));
    const previewInput = hiddenFinishField("finish_review_preview");
    previewInput.value = JSON.stringify(finishReview.preview);
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
  dialog.addEventListener("pointerdown", (event) => {
    timingActionPointerDown = Boolean(event.target.closest?.("button, a"));
  });
  document.addEventListener("pointerup", () => {
    timingActionPointerDown = false;
  });
  document.addEventListener("pointercancel", () => {
    timingActionPointerDown = false;
  });

  addButton.addEventListener("click", () => {
    invalidatePreviewDraft();
    state.rows = addIntervalDraft(state.rows, state.status);
    invalidateDisplayedCalculations();
    clearAlert();
    renderRows();
    updateDraftInput();
    const first = incompleteDraftFields(state.rows, requiredDraftStatus())[0];
    fieldInput(first?.source_index, first?.field)?.focus();
  });
  cancelButton.addEventListener("click", cancelEditor);
  deleteConfirmCancel.addEventListener("click", () => closeDeleteConfirmation());
  deleteConfirmSubmit.addEventListener("click", confirmIntervalDelete);
  deleteConfirmOverlay.addEventListener("click", (event) => {
    if (event.target === deleteConfirmOverlay) {
      closeDeleteConfirmation();
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
    setEditorSubmitting(true);
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
  finishCancelButton.addEventListener("click", cancelFinishSummary);
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
        locked: true,
        lockedMessages: staleMessages,
      });
      return;
    }
    lockTimingDraft(staleMessages);
  }, { capture: true });

  window.addEventListener("terminal:shift-stale", () => {
    previewCoordinator.invalidate({ suspend: true });
    setPreviewLoading(false);
    shiftSuspended = true;
    closeDeleteConfirmation({ restoreFocus: false });
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
    if (!deleteConfirmOverlay.hidden) {
      if (event.key === "Tab") {
        trapDeleteConfirmationFocus(event);
      } else if (event.key === "Escape") {
        event.preventDefault();
        closeDeleteConfirmation();
      }
      return;
    }
    if (!overlay.hidden) {
      if (event.key === "Tab") {
        trapDialogFocus(event);
      } else if (event.key === "Escape") {
        event.preventDefault();
        if (!submitting) {
          cancelEditor();
        }
      }
      return;
    }
    if (!finishOverlay.hidden) {
      if (event.key === "Tab") {
        trapFinishFocus(event);
      } else if (event.key === "Escape") {
        event.preventDefault();
        if (!finishSubmitting) {
          cancelFinishSummary();
        }
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
      renderServerErrors(model.issues, { focus: true });
    }
  }
  if (model.finish_review?.open) {
    const finishHydration = initialFinishReviewHydration(
      model.finish_review,
      timing.draft,
      timing.display,
    );
    const retainedDraft = finishHydration.draft;
    const retainedMessages = finishHydration.lockedMessages;
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
        locked: finishHydration.locked,
        lockedMessages: retainedMessages,
      });
      renderServerErrors(model.finish_review.issues, {
        focus: true,
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
