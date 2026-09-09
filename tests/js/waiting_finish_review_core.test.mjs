import test from "node:test";
import assert from "node:assert/strict";

import {
  canEnableWaitingFinishTrigger,
  isValidWaitingFinishReviewModel,
} from "../../app/static/js/waiting_finish_review_core.mjs";


const validModel = Object.freeze({
  open: false,
  locked: false,
  can_confirm: true,
  reload_required: false,
});


test("waiting review model validation requires every server boolean", () => {
  assert.equal(isValidWaitingFinishReviewModel(validModel), true);
  assert.equal(isValidWaitingFinishReviewModel(null), false);
  assert.equal(isValidWaitingFinishReviewModel({ ...validModel, open: "false" }), false);
  assert.equal(isValidWaitingFinishReviewModel({ ...validModel, can_confirm: 1 }), false);
  const missing = { ...validModel };
  delete missing.reload_required;
  assert.equal(isValidWaitingFinishReviewModel(missing), false);
});


test("waiting trigger enables only for a ready unlocked controller", () => {
  assert.equal(canEnableWaitingFinishTrigger(validModel, { suspended: false }), true);
  assert.equal(canEnableWaitingFinishTrigger(validModel, { suspended: true }), false);
  assert.equal(
    canEnableWaitingFinishTrigger({ ...validModel, locked: true }, { suspended: false }),
    false,
  );
  assert.equal(canEnableWaitingFinishTrigger({}, { suspended: false }), false);
});
