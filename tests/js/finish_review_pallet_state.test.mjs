import test from "node:test";
import assert from "node:assert/strict";

import {
  applyFinishReviewPalletState,
  validateFinishReviewPalletState,
} from "../../app/static/js/finish_review_pallet_state.mjs";


class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this.attributes = new Map();
  }

  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = [...children]; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
}


function validPayload(overrides = {}) {
  return {
    mode: "complete",
    review_token: "signed-review-token",
    card_version: 8,
    pallet_summary: {
      state: "ready",
      weight_state: "partial",
      rows: [{
        pallet_number: 3,
        pallet_label: "3",
        roll_count: 2,
        gross_without_pallet_display: "25.0",
        pallet_weight_display: "-",
        gross_with_pallet_display: "-",
        net_display: "24.0",
      }],
      total: {
        roll_count: 2,
        gross_without_pallet_display: "25.0",
        pallet_weight_display: "-",
        gross_with_pallet_display: "-",
        net_display: "24.0",
      },
    },
    messages: ["Липсва тегло за палет №3."],
    warning_message: "",
    can_confirm: false,
    timing_display: {
      first_start_display: "15.01.2026 10:00",
      proposed_stop_display: "15.01.2026 11:00",
      production_seconds: 3600,
      paused_seconds: 0,
      production_duration_display: "1 ч 00 м",
      paused_duration_display: "0 м",
    },
    ...overrides,
  };
}


function fixture() {
  const documentObject = {
    createElement: (tagName) => new FakeElement(tagName),
  };
  const elements = Object.fromEntries([
    "rows", "totalCount", "totalGross", "totalPallet", "totalGrossWith",
    "totalNet", "alert", "warning", "confirm", "firstStart", "stop",
    "production", "paused",
  ].map((name) => [name, new FakeElement()]));
  elements.rows.ownerDocument = documentObject;
  const selectors = {
    "[data-finish-production-rows]": elements.rows,
    "[data-finish-roll-count-total]": elements.totalCount,
    "[data-finish-gross-total]": elements.totalGross,
    "[data-finish-pallet-weight-total]": elements.totalPallet,
    "[data-finish-gross-with-total]": elements.totalGrossWith,
    "[data-finish-net-total]": elements.totalNet,
    "[data-finish-review-alert]": elements.alert,
    "[data-finish-review-warning]": elements.warning,
    "[data-finish-review-confirm]": elements.confirm,
    "[data-finish-first-start]": elements.firstStart,
    "[data-finish-proposed-stop]": elements.stop,
    "[data-finish-production-total]": elements.production,
    "[data-finish-paused-total]": elements.paused,
  };
  const dialog = new FakeElement();
  dialog.querySelector = (selector) => selectors[selector] ?? null;
  return { dialog, elements };
}


test("finish review validator rejects incomplete or lifecycle-inconsistent payloads", () => {
  const waiting = validPayload({ mode: "finalize_rewinding" });
  delete waiting.review_token;
  assert.deepEqual(validateFinishReviewPalletState(validPayload()), validPayload());
  assert.deepEqual(validateFinishReviewPalletState(waiting), waiting);
  assert.equal(
    validateFinishReviewPalletState(validPayload({ mode: "finalize_rewinding" })),
    null,
  );
  assert.equal(validateFinishReviewPalletState(validPayload({ mode: "other" })), null);
  assert.equal(validateFinishReviewPalletState(validPayload({ card_version: "8" })), null);
  assert.equal(validateFinishReviewPalletState(validPayload({ messages: "blocked" })), null);
  assert.equal(validateFinishReviewPalletState(validPayload({ pallet_summary: {} })), null);
});


test("finish review validator rejects lifecycle policy contradictions", () => {
  const finalPartialConfirmable = validPayload({ can_confirm: true });
  assert.equal(validateFinishReviewPalletState(finalPartialConfirmable), null);

  const finalPartialWithoutBlocker = validPayload({
    messages: [],
    can_confirm: false,
  });
  assert.equal(validateFinishReviewPalletState(finalPartialWithoutBlocker), null);

  const waitingPartialWithWarning = validPayload({
    mode: "finalize_rewinding",
    warning_message: "Допълнете теглата.",
  });
  delete waitingPartialWithWarning.review_token;
  assert.equal(validateFinishReviewPalletState(waitingPartialWithWarning), null);

  const enteringPartialWithoutWarning = validPayload({
    mode: "enter_rewinding",
    messages: [],
    warning_message: "",
    can_confirm: true,
  });
  assert.equal(validateFinishReviewPalletState(enteringPartialWithoutWarning), null);

  const completeWithWarning = validPayload({
    pallet_summary: {
      ...validPayload().pallet_summary,
      weight_state: "complete",
    },
    messages: [],
    warning_message: "Unexpected warning",
    can_confirm: true,
  });
  assert.equal(validateFinishReviewPalletState(completeWithWarning), null);

  const blockerMarkedConfirmable = validPayload({
    pallet_summary: {
      ...validPayload().pallet_summary,
      weight_state: "none",
    },
    messages: ["Blocked"],
    can_confirm: true,
  });
  assert.equal(validateFinishReviewPalletState(blockerMarkedConfirmable), null);
});


test("one apply replaces six-column rows totals messages warning version and eligibility", () => {
  const { dialog, elements } = fixture();
  elements.rows.append(new FakeElement("tr"));
  elements.totalPallet.textContent = "stale";
  elements.warning.textContent = "stale warning";
  const payload = validPayload({
    mode: "enter_rewinding",
    messages: [],
    warning_message: "Допълнете теглата преди окончателното приключване.",
    can_confirm: true,
  });

  assert.equal(applyFinishReviewPalletState(dialog, payload), true);

  assert.equal(dialog.dataset.finishReviewMode, "enter_rewinding");
  assert.equal(dialog.dataset.finishReviewCardVersion, "8");
  assert.equal(elements.rows.children.length, 1);
  assert.deepEqual(
    elements.rows.children[0].children.map((cell) => cell.textContent),
    ["3", "2", "25.0", "-", "-", "24.0"],
  );
  assert.equal(elements.totalCount.textContent, "2");
  assert.equal(elements.totalGross.textContent, "25.0");
  assert.equal(elements.totalPallet.textContent, "-");
  assert.equal(elements.totalGrossWith.textContent, "-");
  assert.equal(elements.totalNet.textContent, "24.0");
  assert.equal(elements.alert.hidden, true);
  assert.equal(elements.warning.textContent, payload.warning_message);
  assert.equal(elements.warning.hidden, false);
  assert.equal(elements.confirm.disabled, false);
});


test("invalid replacement leaves the existing review untouched", () => {
  const { dialog, elements } = fixture();
  const staleRow = new FakeElement("tr");
  elements.rows.append(staleRow);
  elements.totalGross.textContent = "stale total";

  assert.equal(
    applyFinishReviewPalletState(dialog, validPayload({ can_confirm: true })),
    false,
  );
  assert.deepEqual(elements.rows.children, [staleRow]);
  assert.equal(elements.totalGross.textContent, "stale total");
});
