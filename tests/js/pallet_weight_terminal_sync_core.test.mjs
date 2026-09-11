import test from "node:test";
import assert from "node:assert/strict";

import {
  classifyPalletWeightSnapshotReconciliation,
} from "../../app/static/js/pallet_weight_terminal_sync_core.mjs";


const selectedCard = (overrides = {}) => ({
  id: 21,
  order_number: "25000",
  status: "running",
  machine_id: 1,
  machine_sequence: 1,
  rewinding_roll_count: null,
  final_extrusion_shift_occurrence_id: null,
  version: 7,
  updated_at: "2026-09-10 08:00:00",
  ...overrides,
});

const otherCard = (overrides = {}) => ({
  id: 22,
  order_number: "25001",
  status: "pending",
  machine_id: 2,
  machine_sequence: 1,
  rewinding_roll_count: null,
  final_extrusion_shift_occurrence_id: null,
  version: 3,
  updated_at: "2026-09-10 07:00:00",
  ...overrides,
});

const snapshot = (overrides = {}) => ({
  server_now_utc: "2026-09-10 08:00:01",
  active_signature: "derived-active-before",
  waiting_signature: "derived-waiting-before",
  shift_signature: "configuration:1:3||active:9:1:1:2026-09-10 06:00:00",
  signature: "derived-before",
  selected_card: selectedCard(),
  selected_card_missing: false,
  active_cards: [selectedCard(), otherCard()],
  waiting_cards: [],
  ...overrides,
});

const localSaveSnapshot = () => snapshot({
  server_now_utc: "2026-09-10 08:00:11",
  active_signature: "derived-active-after",
  signature: "derived-after",
  selected_card: selectedCard({
    version: 8,
    updated_at: "2026-09-10 08:00:10",
  }),
  active_cards: [
    selectedCard({ version: 8, updated_at: "2026-09-10 08:00:10" }),
    otherCard(),
  ],
});

const classify = (before, after, expectedVersion = 8) => (
  classifyPalletWeightSnapshotReconciliation(before, after, {
    cardId: 21,
    expectedVersion,
  })
);


test("terminal reconciliation accepts only the exact local version and timestamp delta", () => {
  assert.deepEqual(classify(snapshot(), localSaveSnapshot()), {
    kind: "accept-local",
    reason: "selected-card-version-updated",
  });
});

test("terminal reconciliation rejects any shift change", () => {
  const after = localSaveSnapshot();
  after.shift_signature = "configuration:1:3||active:10:2:1:2026-09-10 14:00:00";
  assert.equal(classify(snapshot(), after).kind, "stale");
});

test("terminal reconciliation rejects active or waiting membership and order changes", () => {
  const variants = [];
  const removed = localSaveSnapshot();
  removed.active_cards = removed.active_cards.slice(0, 1);
  variants.push(removed);
  const reordered = localSaveSnapshot();
  reordered.active_cards = [...reordered.active_cards].reverse();
  variants.push(reordered);
  const waiting = localSaveSnapshot();
  waiting.waiting_cards = [{
    id: 31,
    status: "awaiting_rewinding",
    version: 4,
    updated_at: "2026-09-10 08:00:09",
    finished_at: "2026-09-10 07:55:00",
    rewinding_roll_count: 2,
  }];
  variants.push(waiting);

  for (const after of variants) {
    assert.equal(classify(snapshot(), after).kind, "stale");
  }
});

test("terminal reconciliation rejects every other-card mutation", () => {
  for (const change of [
    { version: 4 },
    { updated_at: "2026-09-10 08:00:10" },
    { machine_sequence: 2 },
    { status: "running" },
  ]) {
    const after = localSaveSnapshot();
    after.active_cards[1] = otherCard(change);
    assert.equal(classify(snapshot(), after).kind, "stale");
  }
});

test("terminal reconciliation rejects selected-card lifecycle or queue changes", () => {
  for (const change of [
    { status: "paused" },
    { machine_id: 2 },
    { machine_sequence: 2 },
    { rewinding_roll_count: 3 },
  ]) {
    const after = localSaveSnapshot();
    after.selected_card = selectedCard({
      version: 8,
      updated_at: "2026-09-10 08:00:10",
      ...change,
    });
    after.active_cards[0] = { ...after.selected_card };
    assert.equal(classify(snapshot(), after).kind, "stale");
  }
});

test("terminal reconciliation rejects missing, older, newer, and malformed selected cards", () => {
  const missing = localSaveSnapshot();
  missing.selected_card = null;
  missing.selected_card_missing = true;
  missing.active_cards = missing.active_cards.slice(1);

  for (const [after, expectedVersion] of [
    [missing, 8],
    [localSaveSnapshot(), 9],
    [localSaveSnapshot(), 7],
    [{ ...localSaveSnapshot(), active_cards: null }, 8],
  ]) {
    assert.equal(classify(snapshot(), after, expectedVersion).kind, "stale");
  }
});

test("terminal reconciliation rejects an inconsistent selected-card timestamp occurrence", () => {
  const after = localSaveSnapshot();
  after.active_cards[0] = selectedCard({
    version: 8,
    updated_at: "2026-09-10 08:00:09",
  });

  assert.equal(classify(snapshot(), after).kind, "stale");
});
