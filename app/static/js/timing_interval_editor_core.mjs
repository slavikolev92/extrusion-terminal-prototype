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

export function formatFinishBoundary(rawValue) {
  const value = String(rawValue ?? "");
  const match = /^(\d{2})\.(\d{2})\.(\d{4}) (\d{2}:\d{2})$/.exec(value);
  if (!match) {
    return value || "—";
  }
  return `${match[1]}/${match[2]}/${match[3].slice(-2)} ${match[4]}`;
}

export function maskDateInput(rawValue) {
  const digits = String(rawValue ?? "").replace(/\D/g, "").slice(0, 8);
  if (digits.length < 2) {
    return digits;
  }
  if (digits.length < 4) {
    return `${digits.slice(0, 2)}.${digits.slice(2)}`;
  }
  return `${digits.slice(0, 2)}.${digits.slice(2, 4)}.${digits.slice(4)}`;
}

export function dateSegmentsFromValue(rawValue) {
  const value = String(rawValue ?? "");
  const isoMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (isoMatch) {
    return { day: isoMatch[3], month: isoMatch[2], year: isoMatch[1] };
  }

  const displayValue = value.includes(".") ? value : maskDateInput(value);
  const [day = "", month = "", year = ""] = displayValue.split(".");
  return {
    day: day.replace(/\D/g, "").slice(0, 2),
    month: month.replace(/\D/g, "").slice(0, 2),
    year: year.replace(/\D/g, "").slice(0, 4),
  };
}

export function dateValueFromSegments({ day = "", month = "", year = "" } = {}) {
  const segments = {
    day: String(day).replace(/\D/g, "").slice(0, 2),
    month: String(month).replace(/\D/g, "").slice(0, 2),
    year: String(year).replace(/\D/g, "").slice(0, 4),
  };
  if (!segments.day && !segments.month && !segments.year) {
    return "";
  }
  return `${segments.day}.${segments.month}.${segments.year}`;
}

export function maskedCaretPosition(maskedValue, digitCount) {
  if (!Number.isSafeInteger(digitCount) || digitCount <= 0) {
    return 0;
  }
  let seenDigits = 0;
  for (let index = 0; index < maskedValue.length; index += 1) {
    if (/\d/.test(maskedValue[index])) {
      seenDigits += 1;
    }
    if (seenDigits === digitCount) {
      let caret = index + 1;
      while (caret < maskedValue.length && /\D/.test(maskedValue[caret])) {
        caret += 1;
      }
      return caret;
    }
  }
  return maskedValue.length;
}

export function maskedBackspaceEdit(value, selectionStart, selectionEnd) {
  if (
    !Number.isSafeInteger(selectionStart)
    || selectionStart !== selectionEnd
    || selectionStart < 2
    || /\d/.test(value[selectionStart - 1] || "")
    || !/\d/.test(value[selectionStart - 2] || "")
  ) {
    return null;
  }
  return {
    value: `${value.slice(0, selectionStart - 2)}${value.slice(selectionStart - 1)}`,
    caret: selectionStart - 2,
  };
}

export function normalizeDraftDateInputs(rows) {
  return rows.map((row) => ({
    ...row,
    start_date: dateInputDisplayValue(row.start_date),
    stop_date: dateInputDisplayValue(row.stop_date),
  }));
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
  const newRow = {
    segment_id: null,
    start_date: "",
    start_time: "",
    stop_date: "",
    stop_time: "",
    deleted: false,
    display_number: nextDisplayNumber,
  };
  if (status === "paused") {
    return [...numberedRows, newRow];
  }

  const finalActiveIndex = numberedRows
    .map((row, index) => (row.deleted ? null : index))
    .filter((index) => index !== null)
    .at(-1);
  if (finalActiveIndex === undefined) {
    return [...numberedRows, newRow];
  }
  const insertionNumber = numberedRows[finalActiveIndex].display_number;
  const shiftedRows = numberedRows.map((row, index) => (
    index >= finalActiveIndex
      ? { ...row, display_number: row.display_number + 1 }
      : row
  ));
  return [
    ...shiftedRows.slice(0, finalActiveIndex),
    { ...newRow, display_number: insertionNumber },
    ...shiftedRows.slice(finalActiveIndex),
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
    return numberedRows
      .filter((_, index) => index !== sourceIndex)
      .map((row, index) => ({ ...row, display_number: index + 1 }));
  }
  return numberedRows.map((row, index) => (
    index === sourceIndex ? { ...row, deleted: true } : row
  ));
}

export function visibleTimingRows(rows) {
  const visibleRows = [];
  rows.forEach((row, sourceIndex) => {
    if (!row.deleted) {
      visibleRows.push({
        row: { ...row, display_number: visibleRows.length + 1 },
        sourceIndex,
      });
    }
  });
  return visibleRows;
}

export function canDeleteTimingRow(rows, sourceIndex, { mode, status }) {
  const visibleRows = visibleTimingRows(rows);
  const targetIndex = visibleRows.findIndex(
    ({ sourceIndex: visibleSourceIndex }) => visibleSourceIndex === sourceIndex,
  );
  if (targetIndex === -1 || visibleRows.length === 1) {
    return false;
  }
  const targetRow = visibleRows[targetIndex].row;
  return !(
    mode === "ordinary"
    && status === "running"
    && targetIndex === visibleRows.length - 1
    && !targetRow.stop_date
    && !targetRow.stop_time
  );
}

export function mapServerPreview(
  rows,
  preview,
  { normalizeOrder = true } = {},
) {
  const numberedRows = withDisplayNumbers(rows);
  const durationBySourceIndex = new Map(
    preview.intervals.map((interval) => [
      interval.source_index,
      interval.duration_seconds,
    ]),
  );
  const orderedSourceIndexes = [];
  const includedSourceIndexes = new Set();
  if (normalizeOrder) {
    preview.intervals.forEach((interval) => {
      const sourceIndex = interval.source_index;
      if (
        Number.isSafeInteger(sourceIndex)
        && sourceIndex >= 0
        && sourceIndex < numberedRows.length
        && !numberedRows[sourceIndex].deleted
        && !includedSourceIndexes.has(sourceIndex)
      ) {
        orderedSourceIndexes.push(sourceIndex);
        includedSourceIndexes.add(sourceIndex);
      }
    });
    numberedRows.forEach((row, sourceIndex) => {
      if (!row.deleted && !includedSourceIndexes.has(sourceIndex)) {
        orderedSourceIndexes.push(sourceIndex);
        includedSourceIndexes.add(sourceIndex);
      }
    });
    numberedRows.forEach((row, sourceIndex) => {
      if (row.deleted) {
        orderedSourceIndexes.push(sourceIndex);
      }
    });
  } else {
    numberedRows.forEach((_, sourceIndex) => {
      orderedSourceIndexes.push(sourceIndex);
    });
  }

  const sourceIndexMap = Array(numberedRows.length);
  let displayNumber = 0;
  const normalizedRows = orderedSourceIndexes.map((sourceIndex, normalizedIndex) => {
    const row = numberedRows[sourceIndex];
    sourceIndexMap[sourceIndex] = normalizedIndex;
    if (row.deleted) {
      return { ...row, duration_seconds: null };
    }
    displayNumber += 1;
    return {
      ...row,
      display_number: displayNumber,
      duration_seconds: durationBySourceIndex.get(sourceIndex) ?? null,
    };
  });
  const normalizedPreview = {
    ...preview,
    intervals: preview.intervals.flatMap((interval) => {
      const sourceIndex = sourceIndexMap[interval.source_index];
      return Number.isSafeInteger(sourceIndex)
        ? [{ ...interval, source_index: sourceIndex }]
        : [];
    }),
  };
  if (Array.isArray(preview.draft)) {
    normalizedPreview.draft = serializeTimingDraft(normalizedRows);
  }
  return {
    rows: normalizedRows,
    source_index_map: sourceIndexMap,
    normalized_preview: normalizedPreview,
    production_seconds: preview.production_seconds,
    paused_seconds: preview.paused_seconds,
    first_start_display: preview.first_start_display,
    proposed_stop_display: preview.proposed_stop_display,
  };
}

export function remapFocusedTimingField(focusedField, sourceIndexMap) {
  if (!focusedField) {
    return null;
  }
  const sourceIndex = sourceIndexMap[focusedField.sourceIndex];
  if (!Number.isSafeInteger(sourceIndex)) {
    return null;
  }
  return { ...focusedField, sourceIndex };
}

export function serializeTimingDraft(rows) {
  return rows
    .filter((row) => row.segment_id !== null || row.deleted !== true)
    .map((row) => ({
      segment_id: row.segment_id,
      start_date: dateInputServerValue(row.start_date),
      start_time: row.start_time,
      stop_date: dateInputServerValue(row.stop_date),
      stop_time: row.stop_time,
      deleted: row.deleted,
    }));
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
  const parts = dateInputParts(value);
  if (!parts) {
    return false;
  }
  const { year, month, day } = parts;
  const instant = new Date(Date.UTC(year, month - 1, day));
  return year >= 1
    && year <= 9999
    && instant.getUTCFullYear() === year
    && instant.getUTCMonth() === month - 1
    && instant.getUTCDate() === day;
}

function dateInputDisplayValue(rawValue) {
  const value = String(rawValue ?? "");
  const isoMatch = /^(\d+)-(\d{2})-(\d{2})$/.exec(value);
  if (isoMatch) {
    return maskDateInput(`${isoMatch[3]}${isoMatch[2]}${isoMatch[1]}`);
  }
  return maskDateInput(value);
}

function dateInputServerValue(rawValue) {
  const parts = dateInputParts(rawValue);
  if (!parts) {
    return String(rawValue ?? "");
  }
  return `${String(parts.year).padStart(4, "0")}`
    + `-${String(parts.month).padStart(2, "0")}`
    + `-${String(parts.day).padStart(2, "0")}`;
}

function dateInputParts(rawValue) {
  const value = String(rawValue ?? "");
  const displayMatch = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value);
  if (displayMatch) {
    return {
      day: Number(displayMatch[1]),
      month: Number(displayMatch[2]),
      year: Number(displayMatch[3]),
    };
  }
  const isoMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!isoMatch) {
    return null;
  }
  return {
    day: Number(isoMatch[3]),
    month: Number(isoMatch[2]),
    year: Number(isoMatch[1]),
  };
}

function assertSourceIndex(rows, sourceIndex) {
  if (!Number.isSafeInteger(sourceIndex) || sourceIndex < 0 || sourceIndex >= rows.length) {
    throw new RangeError("Invalid interval source index");
  }
}
