import test from "node:test";
import assert from "node:assert/strict";
import * as timingCore from "../../app/static/js/timing_interval_editor_core.mjs";

import {
  addIntervalDraft,
  canDeleteTimingRow,
  incompleteDraftFields,
  markIntervalDeleted,
  mapServerPreview,
  maskDateInput,
  maskTimeInput,
  maskedCaretPosition,
  normalizeDraftDateInputs,
  serializeTimingDraft,
  visibleTimingRows,
} from "../../app/static/js/timing_interval_editor_core.mjs";

test("date mask uses a fixed Bulgarian day-month-year format", () => {
  assert.equal(maskDateInput("2"), "2");
  assert.equal(maskDateInput("20"), "20.");
  assert.equal(maskDateInput("2007"), "20.07.");
  assert.equal(maskDateInput("20072026"), "20.07.2026");
  assert.equal(maskDateInput("20.07.202626"), "20.07.2026");
  assert.equal(maskDateInput(""), "");
});

test("date segments preserve their positions independently", () => {
  assert.deepEqual(timingCore.dateSegmentsFromValue?.("20.08.2026"), {
    day: "20",
    month: "08",
    year: "2026",
  });
  assert.deepEqual(timingCore.dateSegmentsFromValue?.(".08.2026"), {
    day: "",
    month: "08",
    year: "2026",
  });
  assert.equal(timingCore.dateValueFromSegments?.({
    day: "",
    month: "08",
    year: "2026",
  }), ".08.2026");
  assert.equal(timingCore.dateValueFromSegments?.({
    day: "20",
    month: "",
    year: "2026",
  }), "20..2026");
  assert.equal(timingCore.dateValueFromSegments?.({
    day: "",
    month: "",
    year: "",
  }), "");
});

test("finish review boundaries use the compact approved display format", () => {
  assert.equal(
    timingCore.formatFinishBoundary?.("20.08.2026 12:15"),
    "20/08/26 12:15",
  );
  assert.equal(timingCore.formatFinishBoundary?.(""), "—");
});

test("server ISO dates reopen as deterministic Bulgarian date inputs", () => {
  assert.deepEqual(normalizeDraftDateInputs([{
    segment_id: 41,
    start_date: "2026-08-19",
    start_time: "10:00",
    stop_date: "2026-08-20",
    stop_time: "11:00",
    deleted: false,
  }]), [{
    segment_id: 41,
    start_date: "19.08.2026",
    start_time: "10:00",
    stop_date: "20.08.2026",
    stop_time: "11:00",
    deleted: false,
  }]);
});

test("masked caret follows the edited digits instead of jumping to the end", () => {
  assert.equal(maskedCaretPosition("00:0", 1), 1);
  assert.equal(maskedCaretPosition("09:00", 2), 3);
  assert.equal(maskedCaretPosition("20.07.2026", 4), 6);
});

test("Backspace at an inserted separator removes the preceding digit", () => {
  assert.deepEqual(timingCore.maskedBackspaceEdit?.("10:30", 3, 3), {
    value: "1:30",
    caret: 1,
  });
  assert.deepEqual(timingCore.maskedBackspaceEdit?.("20.08.2026", 3, 3), {
    value: "2.08.2026",
    caret: 1,
  });
  assert.equal(timingCore.maskedBackspaceEdit?.("10:30", 1, 1), null);
});

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

test("running add interval inserts a blank closed row before the unchanged open row", () => {
  const draft = addIntervalDraft([
    {
      segment_id: 40,
      start_date: "2026-08-21",
      start_time: "09:00",
      stop_date: "2026-08-21",
      stop_time: "09:30",
      deleted: false,
    },
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
      segment_id: 40,
      start_date: "2026-08-21",
      start_time: "09:00",
      stop_date: "2026-08-21",
      stop_time: "09:30",
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
    {
      segment_id: 41,
      start_date: "2026-08-21",
      start_time: "10:00",
      stop_date: "",
      stop_time: "",
      deleted: false,
      display_number: 3,
    },
  ]);
  assert.deepEqual(incompleteDraftFields(draft, "running"), [
    { source_index: 1, field: "start_date" },
    { source_index: 1, field: "start_time" },
    { source_index: 1, field: "stop_date" },
    { source_index: 1, field: "stop_time" },
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

test("delete keeps an existing row in the draft and serializes its deleted state", () => {
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

  const deleted = markIntervalDeleted(rows, 0);

  assert.equal(deleted.length, 2);
  assert.equal(deleted[0].deleted, true);
  assert.deepEqual(serializeTimingDraft(deleted), [
    {
      segment_id: 41,
      start_date: "2026-08-21",
      start_time: "10:00",
      stop_date: "2026-08-21",
      stop_time: "11:00",
      deleted: true,
    },
    {
      segment_id: 42,
      start_date: "2026-08-21",
      start_time: "11:30",
      stop_date: "2026-08-21",
      stop_time: "12:30",
      deleted: false,
    },
  ]);
});

test("delete removes an unsaved row from the draft", () => {
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
      segment_id: null,
      start_date: "",
      start_time: "",
      stop_date: "",
      stop_time: "",
      deleted: false,
    },
  ];

  assert.deepEqual(markIntervalDeleted(rows, 1), [{
    ...rows[0],
    display_number: 1,
  }]);
});

test("visible rows omit deleted drafts and renumber visible copies", () => {
  const rows = Object.freeze([
    Object.freeze({ segment_id: 41, deleted: false, display_number: 4 }),
    Object.freeze({ segment_id: 42, deleted: true, display_number: 5 }),
    Object.freeze({ segment_id: null, deleted: false, display_number: 6 }),
  ]);

  assert.deepEqual(visibleTimingRows(rows), [
    {
      row: { segment_id: 41, deleted: false, display_number: 1 },
      sourceIndex: 0,
    },
    {
      row: { segment_id: null, deleted: false, display_number: 2 },
      sourceIndex: 2,
    },
  ]);
  assert.deepEqual(rows.map((row) => row.display_number), [4, 5, 6]);
});

test("delete eligibility protects only the open running final interval and a sole visible row", () => {
  const runningRows = [
    {
      segment_id: 41,
      stop_date: "2026-08-21",
      stop_time: "11:00",
      deleted: false,
    },
    { segment_id: 42, stop_date: "", stop_time: "", deleted: false },
  ];
  const closedFinalRows = [
    {
      segment_id: 41,
      stop_date: "2026-08-21",
      stop_time: "11:00",
      deleted: false,
    },
    {
      segment_id: 42,
      stop_date: "2026-08-21",
      stop_time: "12:00",
      deleted: false,
    },
  ];

  assert.equal(
    canDeleteTimingRow(runningRows, 1, { mode: "ordinary", status: "running" }),
    false,
  );
  assert.equal(
    canDeleteTimingRow([{ segment_id: 41, deleted: false }], 0, {
      mode: "ordinary",
      status: "paused",
    }),
    false,
  );
  assert.equal(
    canDeleteTimingRow(closedFinalRows, 1, {
      mode: "ordinary",
      status: "running",
    }),
    true,
  );
  assert.equal(
    canDeleteTimingRow(runningRows, 0, { mode: "ordinary", status: "running" }),
    true,
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
    intervals: [
      { source_index: 0, duration_seconds: 999 },
      { source_index: 2, duration_seconds: 100 },
    ],
  });
  const latest = mapServerPreview(previous.rows, {
    first_start_display: "21.08.2026 10:00",
    proposed_stop_display: "21.08.2026 13:30",
    production_seconds: 5400,
    paused_seconds: 5400,
    intervals: [
      { source_index: 1, duration_seconds: 1800 },
      { source_index: 0, duration_seconds: 3600 },
    ],
  });

  assert.deepEqual(latest.rows.map((row) => row.duration_seconds), [1800, 3600, null]);
  assert.equal(latest.production_seconds, 5400);
  assert.equal(latest.paused_seconds, 5400);
  assert.equal(latest.first_start_display, "21.08.2026 10:00");
  assert.equal(latest.proposed_stop_display, "21.08.2026 13:30");
});

test("successful preview normalizes active rows to chronological server order", () => {
  const rows = [
    {
      segment_id: 202,
      start_date: "20.08.2026",
      start_time: "10:00",
      stop_date: "20.08.2026",
      stop_time: "12:00",
      deleted: false,
    },
    {
      segment_id: 101,
      start_date: "20.08.2026",
      start_time: "08:00",
      stop_date: "20.08.2026",
      stop_time: "09:00",
      deleted: false,
    },
    {
      segment_id: 303,
      start_date: "20.08.2026",
      start_time: "06:00",
      stop_date: "20.08.2026",
      stop_time: "07:00",
      deleted: true,
    },
  ];

  const result = mapServerPreview(rows, {
    first_start_display: "20.08.2026 08:00",
    proposed_stop_display: "20.08.2026 12:00",
    production_seconds: 10_800,
    paused_seconds: 3_600,
    intervals: [
      { source_index: 1, duration_seconds: 3_600 },
      { source_index: 0, duration_seconds: 7_200 },
    ],
  });

  const activeRows = result.rows.filter((row) => !row.deleted);
  assert.deepEqual(activeRows.map((row) => row.segment_id), [101, 202]);
  assert.deepEqual(activeRows.map((row) => row.display_number), [1, 2]);
  assert.deepEqual(activeRows.map((row) => row.duration_seconds), [3_600, 7_200]);
  assert.equal(result.production_seconds, 10_800);
  assert.equal(result.paused_seconds, 3_600);
  assert.equal(result.first_start_display, "20.08.2026 08:00");
  assert.equal(result.proposed_stop_display, "20.08.2026 12:00");
  assert.deepEqual(result.source_index_map, [1, 0, 2]);
  assert.deepEqual(serializeTimingDraft(result.rows), [
    {
      segment_id: 101,
      start_date: "2026-08-20",
      start_time: "08:00",
      stop_date: "2026-08-20",
      stop_time: "09:00",
      deleted: false,
    },
    {
      segment_id: 202,
      start_date: "2026-08-20",
      start_time: "10:00",
      stop_date: "2026-08-20",
      stop_time: "12:00",
      deleted: false,
    },
    {
      segment_id: 303,
      start_date: "2026-08-20",
      start_time: "06:00",
      stop_date: "2026-08-20",
      stop_time: "07:00",
      deleted: true,
    },
  ]);
  assert.deepEqual(
    visibleTimingRows(result.rows).map(({ row }) => row.display_number),
    [1, 2],
  );
});

test("chronological normalization remaps focus without changing its logical field", () => {
  assert.deepEqual(timingCore.remapFocusedTimingField?.({
    sourceIndex: 0,
    field: "start_date",
    dateSegment: "month",
    selectionStart: 0,
    selectionEnd: 2,
  }, [1, 0, 2]), {
    sourceIndex: 1,
    field: "start_date",
    dateSegment: "month",
    selectionStart: 0,
    selectionEnd: 2,
  });
});

test("locked recovery can map display data without reordering the retained draft", () => {
  const rows = [
    { segment_id: 202, deleted: false },
    { segment_id: 101, deleted: false },
  ];

  const result = mapServerPreview(rows, {
    first_start_display: "20.08.2026 08:00",
    proposed_stop_display: "20.08.2026 12:00",
    production_seconds: 10_800,
    paused_seconds: 3_600,
    intervals: [
      { source_index: 1, duration_seconds: 3_600 },
      { source_index: 0, duration_seconds: 7_200 },
    ],
  }, { normalizeOrder: false });

  assert.deepEqual(result.rows.map((row) => row.segment_id), [202, 101]);
  assert.deepEqual(result.rows.map((row) => row.duration_seconds), [7_200, 3_600]);
  assert.deepEqual(result.source_index_map, [0, 1]);
});

test("Finish Apply preview remains idempotent when Edit is reopened", () => {
  const submittedRows = [
    {
      segment_id: 202,
      start_date: "20.08.2026",
      start_time: "10:00",
      stop_date: "20.08.2026",
      stop_time: "12:00",
      deleted: false,
    },
    {
      segment_id: 101,
      start_date: "20.08.2026",
      start_time: "08:00",
      stop_date: "20.08.2026",
      stop_time: "09:00",
      deleted: false,
    },
  ];
  const submittedPreview = {
    first_start_display: "20.08.2026 08:00",
    proposed_stop_display: "20.08.2026 12:00",
    production_seconds: 10_800,
    paused_seconds: 3_600,
    intervals: [
      { source_index: 1, duration_seconds: 3_600 },
      { source_index: 0, duration_seconds: 7_200 },
    ],
  };

  const applied = mapServerPreview(submittedRows, submittedPreview);
  const reopened = mapServerPreview(
    applied.rows,
    applied.normalized_preview ?? submittedPreview,
  );

  assert.deepEqual(
    reopened.rows.map((row) => [
      row.segment_id,
      row.duration_seconds,
      row.display_number,
    ]),
    [[101, 3_600, 1], [202, 7_200, 2]],
  );
  assert.deepEqual(applied.normalized_preview?.intervals, [
    { source_index: 0, duration_seconds: 3_600 },
    { source_index: 1, duration_seconds: 7_200 },
  ]);
  assert.equal(reopened.production_seconds, 10_800);
  assert.equal(reopened.paused_seconds, 3_600);
  assert.equal(reopened.first_start_display, "20.08.2026 08:00");
  assert.equal(reopened.proposed_stop_display, "20.08.2026 12:00");
  assert.deepEqual(serializeTimingDraft(reopened.rows), [
    {
      segment_id: 101,
      start_date: "2026-08-20",
      start_time: "08:00",
      stop_date: "2026-08-20",
      stop_time: "09:00",
      deleted: false,
    },
    {
      segment_id: 202,
      start_date: "2026-08-20",
      start_time: "10:00",
      stop_date: "2026-08-20",
      stop_time: "12:00",
      deleted: false,
    },
  ]);
});

test("Finish summary stale lock retains the applied draft and duration pairing", () => {
  const submittedRows = [
    { segment_id: 202, deleted: false },
    { segment_id: 101, deleted: false },
  ];
  const submittedPreview = {
    first_start_display: "20.08.2026 08:00",
    proposed_stop_display: "20.08.2026 12:00",
    production_seconds: 10_800,
    paused_seconds: 3_600,
    intervals: [
      { source_index: 1, duration_seconds: 3_600 },
      { source_index: 0, duration_seconds: 7_200 },
    ],
  };
  const applied = mapServerPreview(submittedRows, submittedPreview);

  const staleLocked = mapServerPreview(
    applied.rows,
    applied.normalized_preview ?? submittedPreview,
    { normalizeOrder: false },
  );

  assert.deepEqual(
    staleLocked.rows.map((row) => [
      row.segment_id,
      row.duration_seconds,
      row.display_number,
    ]),
    [[101, 3_600, 1], [202, 7_200, 2]],
  );
  assert.equal(staleLocked.production_seconds, 10_800);
  assert.equal(staleLocked.paused_seconds, 3_600);
  assert.equal(staleLocked.first_start_display, "20.08.2026 08:00");
  assert.equal(staleLocked.proposed_stop_display, "20.08.2026 12:00");
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
      start_date: "21.08.2026",
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

test("display dates are complete only when real and serialize back to ISO", () => {
  const row = {
    segment_id: 41,
    start_date: "20.07.2026",
    start_time: "10:00",
    stop_date: "20.07.2026",
    stop_time: "11:00",
    deleted: false,
  };

  assert.deepEqual(incompleteDraftFields([row], "paused"), []);
  assert.deepEqual(incompleteDraftFields([{
    ...row,
    start_date: "31.02.2026",
  }], "paused"), [{ source_index: 0, field: "start_date" }]);
  assert.deepEqual(serializeTimingDraft([row]), [{
    segment_id: 41,
    start_date: "2026-07-20",
    start_time: "10:00",
    stop_date: "2026-07-20",
    stop_time: "11:00",
    deleted: false,
  }]);
});
