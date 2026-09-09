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
