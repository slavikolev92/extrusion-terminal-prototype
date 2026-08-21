import test from "node:test";
import assert from "node:assert/strict";

import {
  addIntervalDraft,
  incompleteDraftFields,
  markIntervalDeleted,
  mapServerPreview,
  maskTimeInput,
  serializeTimingDraft,
  undoIntervalDelete,
} from "../../app/static/js/timing_interval_editor_core.mjs";

test("time mask inserts one colon and rejects incomplete or impossible values", () => {
  assert.deepEqual(maskTimeInput("13"), {
    value: "13:",
    complete: false,
    valid: false,
  });
  assert.deepEqual(maskTimeInput("1350"), {
    value: "13:50",
    complete: true,
    valid: true,
  });
  assert.deepEqual(maskTimeInput("13:50"), {
    value: "13:50",
    complete: true,
    valid: true,
  });
  assert.deepEqual(maskTimeInput("1a3::5b09"), {
    value: "13:50",
    complete: true,
    valid: true,
  });
  assert.deepEqual(maskTimeInput("2460"), {
    value: "24:60",
    complete: true,
    valid: false,
  });
  assert.deepEqual(maskTimeInput("12345"), {
    value: "12:34",
    complete: true,
    valid: true,
  });
  for (const startTime of ["13:", "24:60"]) {
    assert.deepEqual(incompleteDraftFields([{
      segment_id: 41,
      start_date: "2026-08-21",
      start_time: startTime,
      stop_date: "",
      stop_time: "",
      deleted: false,
    }], "running"), [
      { source_index: 0, field: "start_time" },
    ]);
  }
});

test("running add interval creates blank operator-entered boundaries", () => {
  const draft = addIntervalDraft([
    {
      segment_id: 41,
      start_date: "2026-08-21",
      start_time: "10:00",
      stop_date: "",
      stop_time: "",
      deleted: false,
    },
  ], "running");

  assert.deepEqual(draft, [
    {
      segment_id: 41,
      start_date: "2026-08-21",
      start_time: "10:00",
      stop_date: "",
      stop_time: "",
      deleted: false,
      display_number: 1,
    },
    {
      segment_id: null,
      start_date: "",
      start_time: "",
      stop_date: "",
      stop_time: "",
      deleted: false,
      display_number: 2,
    },
  ]);
  assert.deepEqual(incompleteDraftFields(draft, "running"), [
    { source_index: 0, field: "stop_date" },
    { source_index: 0, field: "stop_time" },
    { source_index: 1, field: "start_date" },
    { source_index: 1, field: "start_time" },
  ]);
});

test("paused add interval creates a blank closed-row draft", () => {
  const draft = addIntervalDraft([
    {
      segment_id: 41,
      start_date: "2026-08-21",
      start_time: "10:00",
      stop_date: "2026-08-21",
      stop_time: "11:00",
      deleted: false,
    },
  ], "paused");

  assert.deepEqual(draft[1], {
    segment_id: null,
    start_date: "",
    start_time: "",
    stop_date: "",
    stop_time: "",
    deleted: false,
    display_number: 2,
  });
  assert.deepEqual(incompleteDraftFields(draft, "paused"), [
    { source_index: 1, field: "start_date" },
    { source_index: 1, field: "start_time" },
    { source_index: 1, field: "stop_date" },
    { source_index: 1, field: "stop_time" },
  ]);
});

test("pending delete retains its displayed number and undo restores it", () => {
  const rows = [
    {
      segment_id: 41,
      start_date: "2026-08-21",
      start_time: "10:00",
      stop_date: "2026-08-21",
      stop_time: "11:00",
      deleted: false,
    },
    {
      segment_id: 42,
      start_date: "2026-08-21",
      start_time: "11:30",
      stop_date: "2026-08-21",
      stop_time: "12:30",
      deleted: false,
    },
  ];

  const pending = markIntervalDeleted(rows, 0);
  assert.equal(pending[0].deleted, true);
  assert.equal(pending[0].display_number, 1);
  assert.equal(pending[1].display_number, 2);

  const restored = undoIntervalDelete(pending, 0);
  assert.equal(restored[0].deleted, false);
  assert.equal(restored[0].display_number, 1);
  assert.equal(restored[1].display_number, 2);

  const withUnsaved = addIntervalDraft(restored, "paused");
  assert.deepEqual(markIntervalDeleted(withUnsaved, 2), restored);

  const withTwoUnsaved = addIntervalDraft(withUnsaved, "paused");
  const withoutFirstUnsaved = markIntervalDeleted(withTwoUnsaved, 2);
  const appendedAgain = addIntervalDraft(withoutFirstUnsaved, "paused");
  assert.deepEqual(
    appendedAgain.map((row) => row.display_number),
    [1, 2, 4, 5],
  );
});

test("server preview maps interval productive and paused seconds without Date parsing", () => {
  const rows = [
    {
      segment_id: 41,
      start_date: "2026-08-21",
      start_time: "10:00",
      stop_date: "2026-08-21",
      stop_time: "11:00",
      deleted: false,
    },
    {
      segment_id: 42,
      start_date: "server-authoritative",
      start_time: "11:30",
      stop_date: "2026-08-21",
      stop_time: "12:30",
      deleted: true,
    },
    {
      segment_id: null,
      start_date: "2026-08-21",
      start_time: "13:00",
      stop_date: "",
      stop_time: "",
      deleted: false,
    },
  ];
  const previous = mapServerPreview(rows, {
    first_start_display: "21.08.2026 10:00",
    proposed_stop_display: "21.08.2026 13:15",
    production_seconds: 999,
    paused_seconds: 888,
    intervals: [{ source_index: 0, duration_seconds: 999 }],
  });
  const latest = mapServerPreview(previous.rows, {
    first_start_display: "21.08.2026 10:00",
    proposed_stop_display: "21.08.2026 13:30",
    production_seconds: 5400,
    paused_seconds: 5400,
    intervals: [
      { source_index: 2, duration_seconds: 1800 },
      { source_index: 0, duration_seconds: 3600 },
    ],
  });

  assert.deepEqual(latest.rows.map((row) => row.duration_seconds), [3600, null, 1800]);
  assert.equal(latest.production_seconds, 5400);
  assert.equal(latest.paused_seconds, 5400);
  assert.equal(latest.first_start_display, "21.08.2026 10:00");
  assert.equal(latest.proposed_stop_display, "21.08.2026 13:30");
});

test("draft serializer emits only server fields and omits deleted unsaved rows", () => {
  const rows = Object.freeze([
    Object.freeze({
      segment_id: 41,
      start_date: "server-authoritative",
      start_time: "13:",
      stop_date: "",
      stop_time: "",
      deleted: true,
      display_number: 1,
      duration_seconds: 3600,
      end_reason: "must-not-leak",
    }),
    Object.freeze({
      segment_id: null,
      start_date: "2026-08-21",
      start_time: "14:00",
      stop_date: "2026-08-21",
      stop_time: "15:00",
      deleted: true,
      display_number: 2,
    }),
    Object.freeze({
      segment_id: null,
      start_date: "2026-08-21",
      start_time: "16:00",
      stop_date: "",
      stop_time: "",
      deleted: false,
      display_number: 3,
      duration_seconds: null,
    }),
  ]);

  assert.deepEqual(serializeTimingDraft(rows), [
    {
      segment_id: 41,
      start_date: "server-authoritative",
      start_time: "13:",
      stop_date: "",
      stop_time: "",
      deleted: true,
    },
    {
      segment_id: null,
      start_date: "2026-08-21",
      start_time: "16:00",
      stop_date: "",
      stop_time: "",
      deleted: false,
    },
  ]);
  assert.equal(rows.length, 3);
  assert.equal(rows[0].display_number, 1);
});
