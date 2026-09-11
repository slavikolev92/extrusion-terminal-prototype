const FINISH_REVIEW_MODES = new Set([
  "complete",
  "enter_rewinding",
  "finalize_rewinding",
]);

const SUMMARY_STATES = new Set(["ready", "empty"]);
const WEIGHT_STATES = new Set(["none", "partial", "complete"]);
const DISPLAY_FIELDS = Object.freeze([
  "gross_without_pallet_display",
  "pallet_weight_display",
  "gross_with_pallet_display",
  "net_display",
]);


function isObject(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}


function isDisplayRow(row, { includePallet }) {
  return Boolean(
    isObject(row)
    && Number.isSafeInteger(row.roll_count)
    && row.roll_count >= 0
    && DISPLAY_FIELDS.every((field) => typeof row[field] === "string")
    && (!includePallet || (
      (row.pallet_number === null || Number.isSafeInteger(row.pallet_number))
      && typeof row.pallet_label === "string"
    ))
  );
}


function isLifecyclePolicyConsistent(value) {
  const hasBlockers = value.messages.length > 0;
  if (value.can_confirm !== !hasBlockers) {
    return false;
  }

  const weightState = value.pallet_summary.weight_state;
  const hasWarning = value.warning_message.trim().length > 0;
  if (weightState === "partial") {
    return value.mode === "enter_rewinding"
      ? value.can_confirm && !hasBlockers && hasWarning
      : !value.can_confirm && hasBlockers && !hasWarning;
  }
  if (weightState === "complete" && hasWarning) {
    return false;
  }
  return true;
}


export function validateFinishReviewPalletState(value) {
  if (
    !isObject(value)
    || !FINISH_REVIEW_MODES.has(value.mode)
    || !Number.isSafeInteger(value.card_version)
    || value.card_version < 1
    || !Array.isArray(value.messages)
    || !value.messages.every((message) => typeof message === "string")
    || typeof value.warning_message !== "string"
    || typeof value.can_confirm !== "boolean"
    || !isObject(value.pallet_summary)
    || !SUMMARY_STATES.has(value.pallet_summary.state)
    || !WEIGHT_STATES.has(value.pallet_summary.weight_state)
    || !Array.isArray(value.pallet_summary.rows)
    || !value.pallet_summary.rows.every((row) => isDisplayRow(row, { includePallet: true }))
    || !isDisplayRow(value.pallet_summary.total, { includePallet: false })
    || !isObject(value.timing_display)
    || typeof value.timing_display.first_start_display !== "string"
    || typeof value.timing_display.proposed_stop_display !== "string"
    || !Number.isSafeInteger(value.timing_display.production_seconds)
    || !Number.isSafeInteger(value.timing_display.paused_seconds)
    || typeof value.timing_display.production_duration_display !== "string"
    || typeof value.timing_display.paused_duration_display !== "string"
    || (value.mode === "finalize_rewinding" && Object.hasOwn(value, "review_token"))
    || (
      value.mode !== "finalize_rewinding"
      && (typeof value.review_token !== "string" || !value.review_token)
    )
    || !isLifecyclePolicyConsistent(value)
  ) {
    return null;
  }
  return value;
}


function textCell(documentObject, tagName, value, { scope } = {}) {
  const cell = documentObject.createElement(tagName);
  if (scope) cell.setAttribute("scope", scope);
  cell.textContent = String(value);
  return cell;
}


function buildRows(documentObject, summary) {
  if (summary.state === "empty") {
    const row = documentObject.createElement("tr");
    const cell = textCell(documentObject, "td", "Няма въведени ролки.");
    cell.setAttribute("colspan", "6");
    cell.className = "finish-review-empty";
    row.append(cell);
    return [row];
  }
  return summary.rows.map((source) => {
    const row = documentObject.createElement("tr");
    row.append(
      textCell(documentObject, "th", source.pallet_label, { scope: "row" }),
      textCell(documentObject, "td", source.roll_count),
      textCell(documentObject, "td", source.gross_without_pallet_display),
      textCell(documentObject, "td", source.pallet_weight_display),
      textCell(documentObject, "td", source.gross_with_pallet_display),
      textCell(documentObject, "td", source.net_display),
    );
    return row;
  });
}


export function applyFinishReviewPalletState(dialog, payload) {
  const review = validateFinishReviewPalletState(payload);
  if (!review || !dialog || typeof dialog.querySelector !== "function") {
    return false;
  }
  const hooks = {
    rows: dialog.querySelector("[data-finish-production-rows]"),
    totalCount: dialog.querySelector("[data-finish-roll-count-total]"),
    totalGross: dialog.querySelector("[data-finish-gross-total]"),
    totalPallet: dialog.querySelector("[data-finish-pallet-weight-total]"),
    totalGrossWith: dialog.querySelector("[data-finish-gross-with-total]"),
    totalNet: dialog.querySelector("[data-finish-net-total]"),
    alert: dialog.querySelector("[data-finish-review-alert]"),
    warning: dialog.querySelector("[data-finish-review-warning]"),
    confirm: dialog.querySelector("[data-finish-review-confirm]"),
    firstStart: dialog.querySelector("[data-finish-first-start]"),
    stop: dialog.querySelector("[data-finish-proposed-stop]"),
    production: dialog.querySelector("[data-finish-production-total]"),
    paused: dialog.querySelector("[data-finish-paused-total]"),
  };
  if (Object.values(hooks).some((hook) => !hook)) {
    return false;
  }
  const documentObject = hooks.rows.ownerDocument;
  if (!documentObject || typeof documentObject.createElement !== "function") {
    return false;
  }

  const rows = buildRows(documentObject, review.pallet_summary);
  const messageNodes = review.messages.map((message) => {
    const paragraph = documentObject.createElement("p");
    paragraph.textContent = message;
    return paragraph;
  });
  const total = review.pallet_summary.total;

  dialog.dataset.finishReviewMode = review.mode;
  dialog.dataset.finishReviewCardVersion = String(review.card_version);
  hooks.rows.replaceChildren(...rows);
  hooks.totalCount.textContent = String(total.roll_count);
  hooks.totalGross.textContent = total.gross_without_pallet_display;
  hooks.totalPallet.textContent = total.pallet_weight_display;
  hooks.totalGrossWith.textContent = total.gross_with_pallet_display;
  hooks.totalNet.textContent = total.net_display;
  hooks.alert.replaceChildren(...messageNodes);
  hooks.alert.hidden = messageNodes.length === 0;
  hooks.warning.textContent = review.warning_message;
  hooks.warning.hidden = !review.warning_message;
  hooks.confirm.disabled = review.can_confirm !== true;
  hooks.firstStart.textContent = review.timing_display.first_start_display;
  hooks.stop.textContent = review.timing_display.proposed_stop_display;
  hooks.production.textContent = review.timing_display.production_duration_display;
  hooks.paused.textContent = review.timing_display.paused_duration_display;
  return true;
}
