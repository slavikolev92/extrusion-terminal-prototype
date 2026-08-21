export function maskTimeInput(rawValue) {
  const digits = String(rawValue ?? "").replace(/\D/g, "").slice(0, 4);
  const value = digits.length < 2
    ? digits
    : `${digits.slice(0, 2)}:${digits.slice(2)}`;
  const complete = digits.length === 4;
  const valid = complete
    && Number(digits.slice(0, 2)) <= 23
    && Number(digits.slice(2)) <= 59;
  return { value, complete, valid };
}

export function addIntervalDraft(rows, status) {
  if (status !== "running" && status !== "paused") {
    throw new TypeError("Unsupported card status");
  }
  const numberedRows = withDisplayNumbers(rows);
  const nextDisplayNumber = Math.max(
    0,
    ...numberedRows.map((row) => row.display_number),
  ) + 1;
  return [
    ...numberedRows,
    {
      segment_id: null,
      start_date: "",
      start_time: "",
      stop_date: "",
      stop_time: "",
      deleted: false,
      display_number: nextDisplayNumber,
    },
  ];
}

export function incompleteDraftFields(rows, status) {
  if (status !== "running" && status !== "paused") {
    throw new TypeError("Unsupported card status");
  }
  const activeIndexes = rows
    .map((row, index) => (row.deleted ? null : index))
    .filter((index) => index !== null);
  const finalActiveIndex = activeIndexes.at(-1);
  const incomplete = [];

  for (const sourceIndex of activeIndexes) {
    const row = rows[sourceIndex];
    for (const field of ["start_date", "start_time"]) {
      if (!isDraftFieldReady(row[field], field)) {
        incomplete.push({ source_index: sourceIndex, field });
      }
    }
    if (status === "paused" || sourceIndex !== finalActiveIndex) {
      for (const field of ["stop_date", "stop_time"]) {
        if (!isDraftFieldReady(row[field], field)) {
          incomplete.push({ source_index: sourceIndex, field });
        }
      }
    }
  }
  return incomplete;
}

export function markIntervalDeleted(rows, sourceIndex) {
  const numberedRows = withDisplayNumbers(rows);
  assertSourceIndex(numberedRows, sourceIndex);
  if (numberedRows[sourceIndex].segment_id === null) {
    return numberedRows.filter((_, index) => index !== sourceIndex);
  }
  return numberedRows.map((row, index) => (
    index === sourceIndex ? { ...row, deleted: true } : row
  ));
}

export function undoIntervalDelete(rows, sourceIndex) {
  const numberedRows = withDisplayNumbers(rows);
  assertSourceIndex(numberedRows, sourceIndex);
  return numberedRows.map((row, index) => (
    index === sourceIndex ? { ...row, deleted: false } : row
  ));
}

export function mapServerPreview(rows, preview) {
  const durationBySourceIndex = new Map(
    preview.intervals.map((interval) => [
      interval.source_index,
      interval.duration_seconds,
    ]),
  );
  return {
    rows: withDisplayNumbers(rows).map((row, sourceIndex) => ({
      ...row,
      duration_seconds: durationBySourceIndex.get(sourceIndex) ?? null,
    })),
    production_seconds: preview.production_seconds,
    paused_seconds: preview.paused_seconds,
    first_start_display: preview.first_start_display,
    proposed_stop_display: preview.proposed_stop_display,
  };
}

function withDisplayNumbers(rows) {
  return rows.map((row, index) => ({
    ...row,
    display_number: row.display_number ?? index + 1,
  }));
}

function isDraftFieldReady(value, field) {
  if (field.endsWith("_time")) {
    const masked = maskTimeInput(value);
    return masked.valid && masked.value === value;
  }
  return Boolean(value);
}

function assertSourceIndex(rows, sourceIndex) {
  if (!Number.isSafeInteger(sourceIndex) || sourceIndex < 0 || sourceIndex >= rows.length) {
    throw new RangeError("Invalid interval source index");
  }
}
