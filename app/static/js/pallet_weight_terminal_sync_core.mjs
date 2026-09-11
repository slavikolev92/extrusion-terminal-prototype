const IGNORED_SNAPSHOT_FIELDS = new Set([
  "server_now_utc",
  "signature",
  "active_signature",
  "waiting_signature",
]);


export function classifyPalletWeightSnapshotReconciliation(
  before,
  after,
  { cardId, expectedVersion } = {},
) {
  const stale = (reason) => ({ kind: "stale", reason });
  if (
    !isPlainObject(before)
    || !isPlainObject(after)
    || !isPositiveSafeInteger(cardId)
    || !isNonNegativeSafeInteger(expectedVersion)
  ) return stale("malformed-snapshot");

  for (const candidate of [before, after]) {
    if (
      !Array.isArray(candidate.active_cards)
      || !Array.isArray(candidate.waiting_cards)
      || !isPlainObject(candidate.selected_card)
      || candidate.selected_card_missing !== false
      || typeof candidate.shift_signature !== "string"
    ) return stale("malformed-snapshot");
  }
  if (
    before.selected_card.id !== cardId
    || after.selected_card.id !== cardId
  ) return stale("selected-card-missing");

  const topLevelKeys = new Set([...Object.keys(before), ...Object.keys(after)]);
  for (const key of topLevelKeys) {
    if (
      IGNORED_SNAPSHOT_FIELDS.has(key)
      || key === "active_cards"
      || key === "waiting_cards"
      || key === "selected_card"
    ) continue;
    if (!sameValue(before[key], after[key])) return stale(`${key}-changed`);
  }

  const selectedBeforeTimestamp = before.selected_card.updated_at;
  const selectedAfterTimestamp = after.selected_card.updated_at;
  if (
    typeof selectedBeforeTimestamp !== "string"
    || typeof selectedAfterTimestamp !== "string"
  ) return stale("malformed-selected-card");

  const selectedComparison = compareCardRecord(
    before.selected_card,
    after.selected_card,
    { cardId, expectedVersion },
  );
  if (selectedComparison !== null) return stale(selectedComparison);

  for (const listName of ["active_cards", "waiting_cards"]) {
    const previousCards = before[listName];
    const nextCards = after[listName];
    if (previousCards.length !== nextCards.length) {
      return stale(`${listName}-membership-changed`);
    }
    for (let index = 0; index < previousCards.length; index += 1) {
      const previousCard = previousCards[index];
      const nextCard = nextCards[index];
      if (!isPlainObject(previousCard) || !isPlainObject(nextCard)) {
        return stale(`malformed-${listName}`);
      }
      if (previousCard.id !== nextCard.id) {
        return stale(`${listName}-order-changed`);
      }
      const comparison = compareCardRecord(
        previousCard,
        nextCard,
        { cardId, expectedVersion },
      );
      if (comparison !== null) return stale(comparison);
      if (
        previousCard.id === cardId
        && (
          previousCard.updated_at !== selectedBeforeTimestamp
          || nextCard.updated_at !== selectedAfterTimestamp
        )
      ) return stale("selected-card-snapshot-inconsistent");
    }
  }

  return {
    kind: "accept-local",
    reason: "selected-card-version-updated",
  };
}


function compareCardRecord(before, after, { cardId, expectedVersion }) {
  if (!isPlainObject(before) || !isPlainObject(after)) return "malformed-card";
  if (!isPositiveSafeInteger(before.id) || before.id !== after.id) {
    return "card-identity-changed";
  }
  const beforeKeys = Object.keys(before).sort();
  const afterKeys = Object.keys(after).sort();
  if (!sameValue(beforeKeys, afterKeys)) return "card-shape-changed";

  if (before.id !== cardId) {
    return sameValue(before, after) ? null : "other-card-changed";
  }
  if (
    !isNonNegativeSafeInteger(before.version)
    || before.version >= expectedVersion
    || after.version !== expectedVersion
  ) return "selected-card-version-mismatch";

  for (const key of beforeKeys) {
    if (key === "version" || key === "updated_at") continue;
    if (!sameValue(before[key], after[key])) return "selected-card-changed";
  }
  return null;
}


function sameValue(first, second) {
  if (Object.is(first, second)) return true;
  if (Array.isArray(first) || Array.isArray(second)) {
    if (!Array.isArray(first) || !Array.isArray(second) || first.length !== second.length) {
      return false;
    }
    return first.every((value, index) => sameValue(value, second[index]));
  }
  if (isPlainObject(first) || isPlainObject(second)) {
    if (!isPlainObject(first) || !isPlainObject(second)) return false;
    const firstKeys = Object.keys(first).sort();
    const secondKeys = Object.keys(second).sort();
    return sameValue(firstKeys, secondKeys)
      && firstKeys.every((key) => sameValue(first[key], second[key]));
  }
  return false;
}


function isPlainObject(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}


function isPositiveSafeInteger(value) {
  return Number.isSafeInteger(value) && value > 0;
}


function isNonNegativeSafeInteger(value) {
  return Number.isSafeInteger(value) && value >= 0;
}
