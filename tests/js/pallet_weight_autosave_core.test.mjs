import test from "node:test";
import assert from "node:assert/strict";

import {
  createSerializedTaskQueue,
  parsePalletWeightDraft,
} from "../../app/static/js/pallet_weight_autosave_core.mjs";
import {
  bootstrapPalletWeightAutosave,
} from "../../app/static/js/pallet_weight_autosave.mjs";


class FakeElement extends EventTarget {
  constructor({ dataset = {}, value = "", hidden = false } = {}) {
    super();
    this.dataset = { ...dataset };
    this.value = value;
    this.hidden = hidden;
    this.readOnly = false;
    this.attributes = new Map();
    this.textContent = "";
    this.focusCount = 0;
  }

  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  removeAttribute(name) { this.attributes.delete(name); }
  focus() { this.focusCount += 1; }
}


function palletAutosaveFixture() {
  const input = new FakeElement({ value: "12.0" });
  const status = new FakeElement({ dataset: { palletWeightStatus: "complete" } });
  const statusMessage = new FakeElement();
  const reload = new FakeElement({ hidden: true });
  const form = new FakeElement({ dataset: { palletWeightForm: "2" } });
  form.action = "http://terminal.test/terminal/cards/21/pallet-weights/2";
  form.querySelector = (selector) => (
    selector === "[data-pallet-weight-input]" ? input : null
  );
  const overlay = new FakeElement({
    dataset: { cardId: "21", cardVersion: "7", pageKind: "terminal" },
  });
  overlay.querySelectorAll = (selector) => (
    selector === "[data-pallet-weight-form]" ? [form] : []
  );
  overlay.querySelector = (selector) => ({
    "[data-pallet-weight-status]": status,
    "[data-pallet-weight-status-message]": statusMessage,
    "[data-pallet-weight-reload]": reload,
  }[selector] ?? null);

  const documentObject = new EventTarget();
  documentObject.querySelector = (selector) => (
    selector === "[data-pallet-summary-overlay]" ? overlay : null
  );
  documentObject.querySelectorAll = () => [];
  const windowObject = new EventTarget();
  windowObject.location = {
    href: "http://terminal.test/terminal/cards/21",
    origin: "http://terminal.test",
  };
  windowObject.requestAnimationFrame = (callback) => callback();

  const controller = bootstrapPalletWeightAutosave({
    documentObject,
    windowObject,
    fetchImpl: () => {
      throw new Error("shift takeover must not issue a request");
    },
  });
  let hostClosed = false;
  windowObject.addEventListener("terminal:shift-stale", (event) => {
    if (event.defaultPrevented) return;
    hostClosed = true;
    overlay.hidden = true;
  });
  const dispatchShiftStale = () => {
    const event = new Event("terminal:shift-stale", { cancelable: true });
    windowObject.dispatchEvent(event);
    return event;
  };
  return {
    controller,
    dispatchShiftStale,
    hostClosed: () => hostClosed,
    input,
    overlay,
    reload,
    status,
    statusMessage,
  };
}


test("pallet weight parser mirrors the accepted backend decimal grammar", () => {
  const cases = [
    ["", { kind: "blank" }],
    ["   ", { kind: "blank" }],
    ["12", { kind: "valid", hundredths: 1200 }],
    [" 12.5 ", { kind: "valid", hundredths: 1250 }],
    ["12,5", { kind: "valid", hundredths: 1250 }],
    ["10.35", { kind: "valid", hundredths: 1035 }],
    ["12.54", { kind: "valid", hundredths: 1254 }],
    ["12,55", { kind: "valid", hundredths: 1255 }],
    ["0.01", { kind: "valid", hundredths: 1 }],
    ["000.1", { kind: "valid", hundredths: 10 }],
    ["100.0", { kind: "valid", hundredths: 10000 }],
    ["100.00", { kind: "valid", hundredths: 10000 }],
    ["0", { kind: "invalid", reason: "minimum" }],
    ["0.0", { kind: "invalid", reason: "minimum" }],
    ["-1", { kind: "invalid", reason: "minimum" }],
    ["100.01", { kind: "invalid", reason: "maximum" }],
    ["100.1", { kind: "invalid", reason: "maximum" }],
    ["1000", { kind: "invalid", reason: "maximum" }],
    ["twelve", { kind: "invalid", reason: "format" }],
    ["1e1", { kind: "invalid", reason: "format" }],
    ["12.555", { kind: "invalid", reason: "format" }],
    ["1 2", { kind: "invalid", reason: "format" }],
  ];

  for (const [raw, expected] of cases) {
    assert.deepEqual(parsePalletWeightDraft(raw), expected, raw);
  }
});

test("serialized task queue runs strictly in order and reports pending work", async () => {
  const queue = createSerializedTaskQueue();
  const events = [];
  let releaseFirst;
  let markFirstStarted;
  const firstGate = new Promise((resolve) => { releaseFirst = resolve; });
  const firstStarted = new Promise((resolve) => { markFirstStarted = resolve; });

  const first = queue.enqueue(async () => {
    events.push("first-start");
    markFirstStarted();
    await firstGate;
    events.push("first-end");
    return "first-result";
  });
  const second = queue.enqueue(async () => {
    events.push("second-start");
    return "second-result";
  });

  await firstStarted;
  assert.equal(queue.pendingCount(), 2);
  assert.deepEqual(events, ["first-start"]);

  releaseFirst();
  assert.equal(await first, "first-result");
  assert.equal(await second, "second-result");
  assert.deepEqual(events, ["first-start", "first-end", "second-start"]);
  assert.equal(queue.pendingCount(), 0);
});

test("rejected work does not prevent the next serialized task", async () => {
  const queue = createSerializedTaskQueue();
  const events = [];

  const rejected = queue.enqueue(async () => {
    events.push("rejected");
    throw new Error("expected rejection");
  });
  const continued = queue.enqueue(async () => {
    events.push("continued");
    return 42;
  });

  await assert.rejects(rejected, /expected rejection/);
  assert.equal(await continued, 42);
  assert.deepEqual(events, ["rejected", "continued"]);
  assert.equal(queue.pendingCount(), 0);
});

test("whenIdle resolves only after the current queue generation settles", async () => {
  const queue = createSerializedTaskQueue();
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  let idleResolved = false;

  queue.enqueue(() => gate);
  const idle = queue.whenIdle().then(() => { idleResolved = true; });
  await Promise.resolve();

  assert.equal(idleResolved, false);
  assert.equal(queue.pendingCount(), 1);
  release();
  await idle;
  assert.equal(idleResolved, true);
  assert.equal(queue.pendingCount(), 0);
});

test("clean shift-stale takeover remains dismissible by the modal host", () => {
  const fixture = palletAutosaveFixture();

  const event = fixture.dispatchShiftStale();

  assert.equal(event.defaultPrevented, false);
  assert.equal(fixture.hostClosed(), true);
  assert.equal(fixture.overlay.hidden, true);
  assert.equal(fixture.controller.isFatal(), false);
});

test("dirty shift-stale takeover preserves the draft and permits explicit dismissal", async () => {
  const fixture = palletAutosaveFixture();
  fixture.input.value = "22.5";
  fixture.input.dispatchEvent(new Event("input"));

  const event = fixture.dispatchShiftStale();

  assert.equal(event.defaultPrevented, true);
  assert.equal(fixture.hostClosed(), false);
  assert.equal(fixture.overlay.hidden, false);
  assert.equal(fixture.input.value, "22.5");
  assert.equal(fixture.input.readOnly, true);
  assert.equal(fixture.reload.hidden, false);
  assert.equal(fixture.reload.focusCount, 1);
  assert.equal(fixture.controller.isFatal(), true);
  assert.equal(await fixture.controller.prepareDismiss(), true);
  assert.equal(fixture.input.value, "22.5");
  assert.equal(fixture.status.dataset.kind, "error");
});

test("explicit dismissal discards an invalid draft and restores the saved value", async () => {
  const fixture = palletAutosaveFixture();
  fixture.input.value = "-5";
  fixture.input.dispatchEvent(new Event("input"));

  assert.equal(await fixture.controller.prepareDismiss(), true);
  assert.equal(fixture.input.value, "12.0");
  assert.equal(fixture.input.attributes.has("aria-invalid"), false);
  assert.equal(fixture.statusMessage.textContent, "");
  assert.equal(fixture.status.dataset.kind, undefined);
});

test("explicit dismissal clears transient success feedback before the next open", async () => {
  const fixture = palletAutosaveFixture();
  fixture.status.dataset.kind = "success";
  fixture.statusMessage.textContent = "Теглото за палет №2 е записано.";

  assert.equal(await fixture.controller.prepareDismiss(), true);
  assert.equal(fixture.statusMessage.textContent, "");
  assert.equal(fixture.status.dataset.kind, undefined);
  assert.equal(fixture.status.dataset.palletWeightStatus, "complete");
});
