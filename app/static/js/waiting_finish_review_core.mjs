const REQUIRED_BOOLEAN_FIELDS = Object.freeze([
  "open",
  "locked",
  "can_confirm",
  "reload_required",
]);


export function isValidWaitingFinishReviewModel(value) {
  return Boolean(
    value
    && typeof value === "object"
    && !Array.isArray(value)
    && REQUIRED_BOOLEAN_FIELDS.every(
      (field) => Object.hasOwn(value, field) && typeof value[field] === "boolean",
    )
  );
}


export function canEnableWaitingFinishTrigger(model, { suspended = false } = {}) {
  return isValidWaitingFinishReviewModel(model)
    && suspended !== true
    && model.locked !== true;
}


export function canOpenWaitingFinishReviewPayload(review, loadedVersion) {
  return Boolean(
    review
    && typeof review === "object"
    && !Array.isArray(review)
    && review.mode === "finalize_rewinding"
    && Number.isSafeInteger(review.card_version)
    && String(review.card_version) === String(loadedVersion)
    && !Object.hasOwn(review, "review_token")
  );
}
