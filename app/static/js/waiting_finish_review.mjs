import {
  canOpenWaitingFinishReviewPayload,
  canEnableWaitingFinishTrigger,
  isValidWaitingFinishReviewModel,
} from "./waiting_finish_review_core.mjs";
import {
  applyFinishReviewPalletState,
  validateFinishReviewPalletState,
} from "./finish_review_pallet_state.mjs";


const INVALID_RESPONSE_MESSAGES = Object.freeze([
  "Отговорът на сървъра е невалиден. Презаредете страницата.",
]);
const NETWORK_FAILURE_MESSAGES = Object.freeze([
  "Връзката със сървъра прекъсна. Презаредете страницата.",
]);


function isValidWaitingFinishFailurePayload(payload) {
  return Boolean(
    payload?.ok === false
    && Array.isArray(payload.messages)
    && payload.messages.length > 0
    && payload.messages.every((message) => (
      typeof message === "string" && message.trim().length > 0
    ))
    && Array.isArray(payload.field_errors)
    && payload.field_errors.every((issue) => (
      issue
      && (issue.source_index === null || Number.isSafeInteger(issue.source_index))
      && typeof issue.field === "string"
      && typeof issue.message === "string"
    ))
  );
}


function fatalRequestResult(reason, messages) {
  return {
    kind: "fatal",
    reason,
    messages: [...messages],
    reload_required: true,
  };
}


export async function resolveWaitingFinishReviewRequest({ request, loadedVersion }) {
  let response;
  try {
    response = await request();
  } catch {
    return fatalRequestResult("network", NETWORK_FAILURE_MESSAGES);
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    return fatalRequestResult("malformed-response", INVALID_RESPONSE_MESSAGES);
  }

  if (response.status === 422) {
    if (!response.ok && isValidWaitingFinishFailurePayload(payload)) {
      return {
        kind: "validation",
        messages: [...payload.messages],
        reload_required: false,
      };
    }
    return fatalRequestResult("malformed-response", INVALID_RESPONSE_MESSAGES);
  }
  if (!response.ok) {
    if (response.status === 409 && isValidWaitingFinishFailurePayload(payload)) {
      return fatalRequestResult("stale", payload.messages);
    }
    return fatalRequestResult("malformed-response", INVALID_RESPONSE_MESSAGES);
  }

  const review = validateFinishReviewPalletState(payload?.finish_review);
  if (
    payload?.ok !== true
    || !review
    || !canOpenWaitingFinishReviewPayload(review, loadedVersion)
  ) {
    return fatalRequestResult("malformed-response", INVALID_RESPONSE_MESSAGES);
  }
  return {
    kind: "review",
    review,
    reload_required: false,
  };
}


const waitingForm = document.querySelector(
  'form[data-waiting-finish-review="true"]',
);
const modelElement = document.querySelector(
  "[data-waiting-finish-review-model]",
);
const overlay = document.querySelector("[data-finish-review-overlay]");
const dialog = overlay?.querySelector("[data-finish-review-dialog]");
const alertBox = overlay?.querySelector("[data-finish-review-alert]");
const closeButton = overlay?.querySelector("[data-finish-review-close]");
const cancelButton = overlay?.querySelector("[data-finish-review-cancel]");
const confirmButton = overlay?.querySelector("[data-finish-review-confirm]");
const reloadLink = overlay?.querySelector("[data-finish-review-reload]");
const backgroundTargets = Array.from(
  document.querySelectorAll(".app, .terminal-toast"),
);
const trigger = waitingForm?.querySelector("[data-waiting-finish-trigger]");
const loadedVersionInput = waitingForm?.querySelector(
  'input[name="loaded_version"]',
);

let model = null;
try {
  model = modelElement ? JSON.parse(modelElement.textContent) : null;
} catch {
  model = null;
}

if (
  waitingForm
  && isValidWaitingFinishReviewModel(model)
  && trigger
  && loadedVersionInput
  && loadedVersionInput.value.trim()
  && overlay
  && dialog
  && alertBox
  && closeButton
  && cancelButton
  && confirmButton
  && reloadLink
) {
  const shiftWindow = document.querySelector('[data-shift-window="true"]');
  let backgroundState = null;
  let returnFocus = trigger;
  let nativeSubmit = false;
  let submitting = false;
  let loading = false;
  let suspended = shiftWindow?.dataset.shiftBlocking === "true";
  let controllerReady = false;

  function syncTriggerAvailability() {
    const enabled = controllerReady && canEnableWaitingFinishTrigger(
      model,
      { suspended },
    ) && !loading;
    trigger.disabled = !enabled;
    trigger.setAttribute("aria-disabled", String(!enabled));
  }

  function setBackgroundIsolated(isolated) {
    if (isolated) {
      if (!backgroundState) {
        backgroundState = backgroundTargets.map((background) => ({
          background,
          inert: background.hasAttribute("inert"),
          ariaHidden: background.getAttribute("aria-hidden"),
        }));
      }
      backgroundTargets.forEach((background) => {
        background.setAttribute("inert", "");
        background.setAttribute("aria-hidden", "true");
      });
      return;
    }
    backgroundState?.forEach(({ background, inert, ariaHidden }) => {
      if (inert) {
        background.setAttribute("inert", "");
      } else {
        background.removeAttribute("inert");
      }
      if (ariaHidden === null) {
        background.removeAttribute("aria-hidden");
      } else {
        background.setAttribute("aria-hidden", ariaHidden);
      }
    });
    backgroundState = null;
  }

  function focusableElements() {
    return Array.from(dialog.querySelectorAll(
      'button:not([disabled]), a[href]:not([aria-disabled="true"]), '
      + '[tabindex]:not([tabindex="-1"])',
    )).filter((element) => !element.hidden && !element.closest("[hidden]"));
  }

  function trapFocus(event) {
    const focusable = focusableElements();
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

  function showAlert(messages) {
    alertBox.replaceChildren();
    [...new Set(messages.filter(Boolean))].forEach((message) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = message;
      alertBox.append(paragraph);
    });
    alertBox.hidden = alertBox.childElementCount === 0;
  }

  function applyAvailability() {
    confirmButton.disabled = model.locked || model.can_confirm !== true;
    reloadLink.hidden = model.reload_required !== true;
  }

  function openReview(opener = trigger) {
    if (suspended) {
      return;
    }
    returnFocus = opener || trigger;
    applyAvailability();
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-busy", "false");
    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    setBackgroundIsolated(true);
    window.requestAnimationFrame(() => {
      if (!cancelButton.disabled) {
        cancelButton.focus();
      } else {
        dialog.focus();
      }
    });
  }

  function closeReview() {
    if (submitting) {
      return;
    }
    if (model.locked) {
      window.requestAnimationFrame(() => reloadLink.focus());
      return;
    }
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    dialog.setAttribute("aria-busy", "false");
    setBackgroundIsolated(false);
    const focusTarget = [
      returnFocus,
      document.querySelector("#terminal-refresh-alert-button"),
      document.querySelector("#waiting-open"),
      document.querySelector(".terminal-brand"),
    ].find((candidate) => (
      candidate?.isConnected
      && candidate.hidden !== true
      && candidate.disabled !== true
      && candidate.getAttribute("aria-disabled") !== "true"
      && !candidate.closest("[hidden]")
      && candidate.getClientRects().length > 0
    ));
    focusTarget?.focus({ preventScroll: true });
  }

  function lockReview(messages) {
    model.locked = true;
    model.can_confirm = false;
    model.reload_required = true;
    closeButton.disabled = true;
    cancelButton.disabled = true;
    confirmButton.disabled = true;
    reloadLink.hidden = false;
    showAlert(messages);
    window.requestAnimationFrame(() => alertBox.focus());
  }

  function showFatalReview(messages, opener) {
    model.can_confirm = false;
    model.locked = false;
    model.reload_required = false;
    openReview(opener);
    suspended = true;
    lockReview(messages);
  }

  async function beginReview(opener = trigger) {
    if (loading || submitting || suspended || model.locked) {
      return;
    }
    loading = true;
    syncTriggerAvailability();
    try {
      const body = new FormData();
      body.set("loaded_version", loadedVersionInput.value);
      const result = await resolveWaitingFinishReviewRequest({
        request: () => fetch(`${waitingForm.action}-review`, {
          method: "POST",
          headers: { "Accept": "application/json" },
          body,
        }),
        loadedVersion: loadedVersionInput.value,
      });
      if (result.kind === "validation") {
        model.can_confirm = false;
        model.locked = false;
        model.reload_required = false;
        showAlert(result.messages);
        openReview(opener);
        return;
      }
      if (result.kind === "fatal") {
        showFatalReview(result.messages, opener);
        return;
      }
      const review = result.review;
      if (!applyFinishReviewPalletState(dialog, review)) {
        showFatalReview(INVALID_RESPONSE_MESSAGES, opener);
        return;
      }
      model.can_confirm = review.can_confirm;
      model.locked = false;
      model.reload_required = false;
      openReview(opener);
    } catch {
      showFatalReview(INVALID_RESPONSE_MESSAGES, opener);
    } finally {
      loading = false;
      syncTriggerAvailability();
    }
  }

  function setSubmitting() {
    submitting = true;
    dialog.setAttribute("aria-busy", "true");
    dialog.querySelectorAll("button").forEach((button) => {
      button.disabled = true;
    });
    reloadLink.setAttribute("aria-disabled", "true");
    reloadLink.setAttribute("tabindex", "-1");
  }

  waitingForm.addEventListener("submit", (event) => {
    if (
      nativeSubmit && controllerReady && !suspended
      && model.locked !== true && model.can_confirm === true
    ) {
      return;
    }
    event.preventDefault();
    if (submitting || suspended) {
      return;
    }
    void beginReview(event.submitter || trigger);
  });

  trigger.addEventListener("click", () => {
    void beginReview(trigger);
  });

  closeButton.addEventListener("click", closeReview);
  cancelButton.addEventListener("click", closeReview);
  confirmButton.addEventListener("click", () => {
    if (submitting || suspended || model.locked || model.can_confirm !== true) {
      return;
    }
    setSubmitting();
    nativeSubmit = true;
    try {
      waitingForm.requestSubmit();
    } finally {
      nativeSubmit = false;
    }
  });
  reloadLink.addEventListener("click", (event) => {
    if (submitting) {
      event.preventDefault();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (overlay.hidden) {
      return;
    }
    if (event.key === "Tab") {
      trapFocus(event);
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeReview();
    }
  });

  window.addEventListener("terminal:card-stale", (event) => {
    suspended = true;
    syncTriggerAvailability();
    if (overlay.hidden) {
      return;
    }
    event.preventDefault();
    lockReview([
      "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    ]);
  }, { capture: true });

  window.addEventListener("terminal:shift-stale", () => {
    suspended = true;
    syncTriggerAvailability();
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    dialog.setAttribute("aria-modal", "false");
    setBackgroundIsolated(false);
  }, { capture: true });

  controllerReady = true;
  syncTriggerAvailability();
  if (suspended) {
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    dialog.setAttribute("aria-modal", "false");
  } else if (model.open === true) {
    void beginReview(trigger);
  }
}
