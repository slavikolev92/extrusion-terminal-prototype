import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";


function requiredEnvironment(name) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Required environment variable ${name} is missing.`);
  return value;
}


function assert(condition, message) {
  if (!condition) throw new Error(message);
}


function assertEqual(actual, expected, label) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `${label}: expected ${JSON.stringify(expected)}, found ${JSON.stringify(actual)}`,
    );
  }
}


function normalized(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}


function isStrictChild(parent, candidate) {
  const relative = path.relative(parent, candidate);
  return Boolean(relative)
    && relative !== ".."
    && !relative.startsWith(`..${path.sep}`)
    && !path.isAbsolute(relative);
}


const baseURL = requiredEnvironment("BASE_URL").replace(/\/+$/, "");
const baseOrigin = new URL(baseURL).origin;
const fixtureInput = requiredEnvironment("FIXTURE_JSON");
const artifactInput = requiredEnvironment("ARTIFACT_DIR");
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = fs.realpathSync(path.resolve(scriptDir, ".."));
const runtimeRoot = path.resolve(repoRoot, ".test-runtime");
const artifactRoot = path.resolve(repoRoot, "artifacts", "ui-checks");
const fixturePath = path.resolve(repoRoot, fixtureInput);
const artifactDir = path.resolve(repoRoot, artifactInput);

assert(
  isStrictChild(runtimeRoot, fixturePath),
  "FIXTURE_JSON must be under .test-runtime.",
);
assert(
  isStrictChild(artifactRoot, artifactDir),
  "ARTIFACT_DIR must be below artifacts/ui-checks.",
);
assert(fs.existsSync(fixturePath), `Fixture JSON does not exist: ${fixturePath}`);
assert(fs.statSync(fixturePath).isFile(), "FIXTURE_JSON must name a file.");

let fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const databasePath = path.resolve(repoRoot, fixture.db_path);
assert(
  isStrictChild(runtimeRoot, databasePath),
  "Fixture database must be under .test-runtime.",
);
assert(fs.existsSync(databasePath), `Fixture database does not exist: ${databasePath}`);
assert(fs.statSync(databasePath).isFile(), "Fixture database must name a file.");

const summaryPath = path.join(artifactDir, "verification-summary.json");
const screenshot1366 = path.join(artifactDir, "timing-editor-1366x768.png");
const shortLedgerScreenshot1366 = path.join(
  artifactDir,
  "timing-editor-short-ledger-1366x768.png",
);
const shortLedgerScreenshot1920 = path.join(
  artifactDir,
  "timing-editor-short-ledger-1920x1080.png",
);
const validationScreenshot1366 = path.join(artifactDir, "timing-editor-validation-1366x768.png");
const timeSelectionScreenshot1366 = path.join(
  artifactDir,
  "timing-editor-time-selection-1366x768.png",
);
const deleteConfirmationScreenshot1366 = path.join(
  artifactDir,
  "timing-delete-confirmation-1366x768.png",
);
const screenshot1920 = path.join(artifactDir, "finish-review-1920x1080.png");


function writeSummary() {
  fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
}


function pngDimensions(target) {
  const content = fs.readFileSync(target);
  assert(
    content.length >= 24
      && content.subarray(1, 4).toString("ascii") === "PNG",
    `Screenshot is not a readable PNG: ${target}`,
  );
  return {
    width: content.readUInt32BE(16),
    height: content.readUInt32BE(20),
  };
}


async function captureScreenshot(page, target, expectedDimensions) {
  await page.screenshot({ path: target, fullPage: false });
  const dimensions = pngDimensions(target);
  assertEqual(
    dimensions,
    expectedDimensions,
    `${path.basename(target)} PNG dimensions`,
  );
  summary.screenshotDimensions.push({
    path: path.relative(repoRoot, target),
    ...dimensions,
  });
}


const summary = {
  status: "running",
  baseURL,
  databaseIdentity: databasePath,
  fixture: path.relative(repoRoot, fixturePath),
  assertions: [],
  screenshots: [],
  screenshotDimensions: [],
  viewports: [],
  requestCounts: {},
  consoleErrors: [],
  pageErrors: [],
  failedRequests: [],
  abortedPreviewRequests: [],
};


function passed(label) {
  summary.assertions.push(label);
}


async function preflightDatabase() {
  const response = await fetch(`${baseURL}/health`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  assert(response.ok, `Health preflight returned HTTP ${response.status}.`);
  const health = await response.json();
  assertEqual(
    path.resolve(health.database_path),
    databasePath,
    "server database identity",
  );
  passed("health database identity matched exact resolved fixture");
}


await preflightDatabase();
fs.mkdirSync(artifactDir, { recursive: true });

const require = createRequire(import.meta.url);
const localNodeModules = fs.realpathSync(path.join(repoRoot, "node_modules"));
const resolvedPlaywright = fs.realpathSync(require.resolve("@playwright/test"));
assert(
  isStrictChild(localNodeModules, resolvedPlaywright),
  "Playwright must resolve from the repository-local node_modules directory.",
);
const { chromium } = require("@playwright/test");
const pythonExecutable = path.join(repoRoot, ".venv", "bin", "python");
const fixtureScript = path.join(repoRoot, "scripts", "create_terminal_timing_correction_fixture.py");


function runPython(program, programArguments, label) {
  const result = spawnSync(
    pythonExecutable,
    ["-c", program, ...programArguments],
    {
      cwd: repoRoot,
      encoding: "utf8",
      env: {
        ...process.env,
        EXTRUSION_DATA_DIR: path.dirname(databasePath),
        EXTRUSION_DB_PATH: databasePath,
      },
    },
  );
  assert(result.status === 0, `${label}: ${normalized(result.stderr || result.stdout)}`);
  return result.stdout.trim();
}


function resetFixtureDatabase() {
  const result = spawnSync(
    pythonExecutable,
    [fixtureScript, "--db-path", databasePath, "--output", fixturePath],
    {
      cwd: repoRoot,
      encoding: "utf8",
      env: {
        ...process.env,
        EXTRUSION_DATA_DIR: path.dirname(databasePath),
        EXTRUSION_DB_PATH: databasePath,
      },
    },
  );
  assert(result.status === 0, `Could not reset fixture: ${normalized(result.stderr)}`);
  const refreshed = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  assertEqual(refreshed.cards, fixture.cards, "fixture card identities after reset");
  assertEqual(refreshed.orders, fixture.orders, "fixture order identities after reset");
  assertEqual(refreshed.snapshot, fixture.snapshot, "deterministic fixture snapshot after reset");
  fixture = refreshed;
}


function cardSnapshot(cardId) {
  const program = [
    "import json, sqlite3, sys",
    "connection = sqlite3.connect(sys.argv[1])",
    "connection.row_factory = sqlite3.Row",
    "card_id = int(sys.argv[2])",
    "card = connection.execute(\"SELECT status, version, first_started_at, finished_at, machine_id, machine_sequence, tare_weight, current_pallet_number, rewinding_roll_count, final_extrusion_shift_occurrence_id FROM cards WHERE id = ?\", (card_id,)).fetchone()",
    "timing = connection.execute(\"SELECT id, started_at, ended_at, end_reason FROM production_time_segments WHERE card_id = ? ORDER BY started_at, id\", (card_id,)).fetchall()",
    "rolls = connection.execute(\"SELECT roll_number, gross_weight, tare_weight, net_weight, pallet_number, shift_occurrence_id FROM roll_entries WHERE card_id = ? ORDER BY roll_number\", (card_id,)).fetchall()",
    "print(json.dumps({'card': dict(card), 'timing': [list(row) for row in timing], 'rolls': [list(row) for row in rolls]}))",
  ].join("; ");
  return JSON.parse(runPython(program, [databasePath, String(cardId)], "database snapshot failed"));
}


function mutateCardVersion(cardId) {
  const program = [
    "import sqlite3, sys",
    "connection = sqlite3.connect(sys.argv[1])",
    "connection.execute('BEGIN IMMEDIATE')",
    "connection.execute(\"UPDATE cards SET version = version + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?\", (int(sys.argv[2]),))",
    "connection.commit()",
  ].join("; ");
  runPython(program, [databasePath, String(cardId)], "stale-card mutation failed");
}


async function parkAndReset(page) {
  await page.goto("about:blank");
  resetFixtureDatabase();
  await preflightDatabase();
}


async function navigate(page, scenarioName) {
  const cardId = fixture.cards[scenarioName];
  const response = await page.goto(`${baseURL}/terminal/cards/${cardId}`, {
    waitUntil: "networkidle",
  });
  assert(response?.ok(), `${scenarioName}: terminal page returned HTTP ${response?.status()}.`);
  return cardId;
}


async function openTimingEditor(page) {
  const menuButton = page.locator("[data-timing-menu-button]");
  await menuButton.click();
  const previewResponse = page.waitForResponse(
    (response) => response.request().method() === "POST"
      && new URL(response.url()).pathname.endsWith("/timing-ledger/preview"),
  );
  await page.locator("[data-timing-menu-open]").click();
  const overlay = page.locator("[data-timing-editor-overlay]");
  await overlay.waitFor({ state: "visible" });
  const response = await previewResponse;
  assert(response.ok(), `Initial timing preview returned HTTP ${response.status()}.`);
  await overlay.locator("[data-timing-totals]").waitFor({ state: "visible" });
  await page.waitForFunction(() => (
    document.querySelector("[data-timing-totals]")?.getAttribute("aria-busy") === "false"
  ));
  return overlay;
}


function timingRow(page, index) {
  return page.locator("[data-timing-interval-list] .interval-row").nth(index);
}


async function assertShortLedgerLayout(page, viewport, screenshotTarget) {
  await parkAndReset(page);
  await page.setViewportSize(viewport);
  await navigate(page, "paused");
  const editor = await openTimingEditor(page);
  assertEqual(
    await page.locator("[data-timing-interval-list] .interval-row").count(),
    2,
    `${viewport.width}px short-ledger row count`,
  );

  const layout = await page.locator("[data-timing-dialog]").evaluate((dialog) => {
    const rect = (element) => {
      const box = element.getBoundingClientRect();
      return {
        x: box.x,
        y: box.y,
        width: box.width,
        height: box.height,
        right: box.right,
        bottom: box.bottom,
      };
    };
    const contentRect = (element) => {
      const range = document.createRange();
      range.selectNodeContents(element);
      return rect(range);
    };
    const list = dialog.querySelector("[data-timing-interval-list]");
    const rows = Array.from(list.querySelectorAll(".interval-row"));
    const headings = Array.from(dialog.querySelectorAll("[data-timing-column-headings] > div"));
    const firstRowCells = Array.from(rows[0].children);
    const timestampControls = Array.from(dialog.querySelectorAll(".timestamp-controls"));
    const deleteButtons = Array.from(dialog.querySelectorAll(".interval-delete"));
    const checkedForClipping = Array.from(dialog.querySelectorAll([
      "[data-timing-column-headings] > div",
      ".interval-row > div",
      ".timing-total",
      ".timing-dialog-footer button",
      ".interval-delete",
    ].join(",")));
    const dialogBox = rect(dialog);
    const topLevel = Array.from(dialog.children).map(rect);
    return {
      dialog: dialogBox,
      topLevel,
      list: {
        ...rect(list),
        clientHeight: list.clientHeight,
        scrollHeight: list.scrollHeight,
        rowHeightSum: rows.reduce(
          (total, row) => total + row.getBoundingClientRect().height,
          0,
        ),
      },
      headingEdges: headings.map((element) => {
        const box = rect(element);
        return [box.x, box.right];
      }),
      firstRowEdges: firstRowCells.map((element) => {
        const box = rect(element);
        return [box.x, box.right];
      }),
      separators: [...headings.slice(1), ...firstRowCells.slice(1)].map(
        (element) => getComputedStyle(element).borderLeftWidth,
      ),
      controls: timestampControls.map((controls) => {
        const controlsBox = rect(controls);
        const dateBox = rect(controls.querySelector(".segmented-date-input"));
        const timeBox = rect(controls.querySelector('[data-timing-field$="_time"]'));
        return {
          dateWidth: dateBox.width,
          timeWidth: timeBox.width,
          leftSpace: dateBox.x - controlsBox.x,
          rightSpace: controlsBox.right - timeBox.right,
        };
      }),
      axes: {
        startHeadingLeft: rect(headings[1].querySelector(".timing-column-heading--timestamp")).x,
        startControlLeft: rect(firstRowCells[1].querySelector(".segmented-date-input")).x,
        stopHeadingLeft: rect(headings[2].querySelector(".timing-column-heading--timestamp")).x,
        stopControlLeft: rect(firstRowCells[2].querySelector(".segmented-date-input")).x,
        durationHeadingCenter: (
          contentRect(headings[3]).x + contentRect(headings[3]).right
        ) / 2,
        durationValueCenter: (
          contentRect(firstRowCells[3]).x + contentRect(firstRowCells[3]).right
        ) / 2,
        actionHeadingCenter: (
          contentRect(headings[4]).x + contentRect(headings[4]).right
        ) / 2,
        deleteCenter: (
          rect(firstRowCells[4].querySelector(".interval-delete")).x
          + rect(firstRowCells[4].querySelector(".interval-delete")).right
        ) / 2,
      },
      dateSeparators: Array.from(dialog.querySelectorAll(".date-segment-separator"))
        .map((separator) => separator.textContent),
      visibleText: dialog.textContent,
      deleteButtons: deleteButtons.map(rect),
      clipped: checkedForClipping
        .filter((element) => (
          element.scrollWidth > element.clientWidth + 1
          || element.scrollHeight > element.clientHeight + 1
        ))
        .map((element) => `${element.tagName}.${element.className}`),
    };
  });

  const acceptedCap = Math.min(728, viewport.height - 40);
  assert(
    layout.dialog.height <= 600,
    `${viewport.width}px short-ledger dialog is not materially below the cap: ${layout.dialog.height}px.`,
  );
  assert(
    layout.dialog.height <= acceptedCap + 0.5,
    `${viewport.width}px short-ledger dialog exceeds its viewport cap.`,
  );
  assert(
    layout.dialog.x >= 19.5
      && layout.dialog.y >= 19.5
      && layout.dialog.right <= viewport.width - 19.5
      && layout.dialog.bottom <= viewport.height - 19.5,
    `${viewport.width}px short-ledger dialog violates the 20px viewport margin.`,
  );
  assert(
    layout.list.scrollHeight <= layout.list.clientHeight + 1,
    `${viewport.width}px short ledger unexpectedly scrolls.`,
  );
  assert(
    Math.abs(layout.list.clientHeight - layout.list.rowHeightSum) <= 2,
    `${viewport.width}px short ledger leaves empty list space: ${JSON.stringify(layout.list)}.`,
  );
  assertEqual(layout.headingEdges.length, 5, `${viewport.width}px timing heading count`);
  assertEqual(layout.firstRowEdges.length, 5, `${viewport.width}px timing row column count`);
  layout.headingEdges.forEach((edge, index) => {
    const rowEdge = layout.firstRowEdges[index];
    assert(
      Math.abs(edge[0] - rowEdge[0]) <= 1 && Math.abs(edge[1] - rowEdge[1]) <= 1,
      `${viewport.width}px heading/row column ${index + 1} is misaligned.`,
    );
  });
  assert(
    layout.separators.every((width) => width === "1px"),
    `${viewport.width}px timing separators changed: ${JSON.stringify(layout.separators)}.`,
  );
  layout.controls.forEach((control, index) => {
    assertEqual(Math.round(control.dateWidth), 120, `${viewport.width}px date control ${index + 1} width`);
    assertEqual(Math.round(control.timeWidth), 78, `${viewport.width}px time control ${index + 1} width`);
    assert(
      Math.abs(control.leftSpace - control.rightSpace) <= 1,
      `${viewport.width}px timestamp controls ${index + 1} are not centered.`,
    );
  });
  assert(
    Math.abs(layout.axes.startHeadingLeft - layout.axes.startControlLeft) <= 1,
    `${viewport.width}px Start heading/control axis diverged: ${JSON.stringify(layout.axes)}.`,
  );
  assert(
    Math.abs(layout.axes.stopHeadingLeft - layout.axes.stopControlLeft) <= 1,
    `${viewport.width}px Stop heading/control axis diverged: ${JSON.stringify(layout.axes)}.`,
  );
  assert(
    Math.abs(layout.axes.durationHeadingCenter - layout.axes.durationValueCenter) <= 1,
    `${viewport.width}px Duration heading/value axis diverged: ${JSON.stringify(layout.axes)}.`,
  );
  assert(
    Math.abs(layout.axes.actionHeadingCenter - layout.axes.deleteCenter) <= 1,
    `${viewport.width}px Action heading/Delete axis diverged: ${JSON.stringify(layout.axes)}.`,
  );
  assert(
    layout.dateSeparators.length > 0
      && layout.dateSeparators.every((separator) => separator === "/"),
    `${viewport.width}px segmented date separators regressed: ${JSON.stringify(layout.dateSeparators)}.`,
  );
  assert(normalized(layout.visibleText).includes(" м"), `${viewport.width}px timing durations do not use м.`);
  assert(!normalized(layout.visibleText).includes("мин"), `${viewport.width}px timing durations still use мин.`);
  assert(layout.deleteButtons.length > 0, `${viewport.width}px short ledger has no Delete targets.`);
  layout.deleteButtons.forEach((button, index) => {
    assert(
      button.width >= 72 && button.height >= 40,
      `${viewport.width}px Delete target ${index + 1} is undersized: ${button.width}x${button.height}.`,
    );
  });
  assertEqual(layout.clipped, [], `${viewport.width}px clipped timing content`);
  layout.topLevel.forEach((box, index) => {
    assert(
      box.x >= layout.dialog.x - 0.5
        && box.right <= layout.dialog.right + 0.5
        && box.y >= layout.dialog.y - 0.5
        && box.bottom <= layout.dialog.bottom + 0.5,
      `${viewport.width}px timing section ${index + 1} is outside the dialog.`,
    );
  });

  await captureScreenshot(page, screenshotTarget, viewport);
  summary.screenshots.push(path.relative(repoRoot, screenshotTarget));
  summary.viewports.push({
    ...viewport,
    dialog: "timing editor short ledger",
    dialogHeight: layout.dialog.height,
    listHeight: layout.list.height,
  });
  await editor.locator("[data-timing-cancel]").click();
}


async function verifyShortLedgerLayouts(page) {
  await assertShortLedgerLayout(
    page,
    { width: 1366, height: 768 },
    shortLedgerScreenshot1366,
  );
  await assertShortLedgerLayout(
    page,
    { width: 1920, height: 1080 },
    shortLedgerScreenshot1920,
  );
  passed("content-fitting short-ledger timing editor at 1366x768 and 1920x1080");
}


async function fillTimingField(page, rowIndex, field, value) {
  if (field.endsWith("_date")) {
    const group = timingRow(page, rowIndex).locator(
      `[data-timing-date-field="${field}"]`,
    );
    const [day = "", month = "", year = ""] = String(value).split(".");
    await group.locator('[data-date-segment="day"]').fill(day);
    await group.locator('[data-date-segment="month"]').fill(month);
    await group.locator('[data-date-segment="year"]').fill(year);
    return group.locator('[data-date-segment="day"]');
  }
  const input = timingRow(page, rowIndex).locator(`[data-timing-field="${field}"]`);
  await input.fill(value);
  return input;
}


async function assertFocusInside(page, selector, label) {
  const state = await page.locator(selector).evaluate((element) => ({
    inside: element.contains(document.activeElement),
    activeTag: document.activeElement?.tagName || null,
    activeTimingField: document.activeElement?.getAttribute("data-timing-field") || null,
  }));
  assert(
    state.inside,
    `${label}: focus escaped the dialog (${JSON.stringify(state)}).`,
  );
}


async function verifyLifecycleAndIcon(page) {
  await parkAndReset(page);
  for (const [scenarioName, expectedLabels, expectedDisabled] of [
    ["running", ["Старт", "Пауза", "Приключи"], [true, false, false]],
    ["paused", ["Старт", "Продължи", "Приключи"], [true, false, false]],
  ]) {
    await navigate(page, scenarioName);
    const slots = page.locator(".actions [data-lifecycle-slot]");
    assertEqual(await slots.count(), 3, `${scenarioName} lifecycle control count`);
    const controls = await slots.evaluateAll((elements) => elements.map((element) => {
      const button = element.matches("button") ? element : element.querySelector("button");
      const box = button.getBoundingClientRect();
      return {
        label: button.textContent.replace(/\s+/g, " ").trim(),
        disabled: button.disabled,
        x: box.x,
        right: box.right,
        width: box.width,
        height: box.height,
      };
    }));
    assertEqual(controls.map(({ label }) => label), expectedLabels, `${scenarioName} lifecycle labels`);
    assertEqual(controls.map(({ disabled }) => disabled), expectedDisabled, `${scenarioName} lifecycle eligibility`);
    for (let index = 1; index < controls.length; index += 1) {
      assert(controls[index - 1].right <= controls[index].x + 1, `${scenarioName} lifecycle controls overlap.`);
      assert(Math.abs(controls[index].height - controls[0].height) <= 1, `${scenarioName} lifecycle heights differ.`);
    }
  }

  await navigate(page, "running");
  const menuButton = page.locator("[data-timing-menu-button]");
  await menuButton.click();
  const menuAction = page.locator("[data-timing-menu-open]");
  assertEqual(normalized(await menuAction.textContent()), "Производствено време", "timing menu label");
  const icon = menuAction.locator("img");
  const iconState = await icon.evaluate((image) => ({
    complete: image.complete,
    naturalWidth: image.naturalWidth,
    naturalHeight: image.naturalHeight,
    width: image.getBoundingClientRect().width,
    height: image.getBoundingClientRect().height,
    source: image.currentSrc,
  }));
  assert(iconState.complete, "Clock icon did not finish loading.");
  assert(iconState.naturalWidth > 0 && iconState.naturalHeight > 0, "Clock icon has no natural dimensions.");
  assertEqual([iconState.width, iconState.height], [17, 17], "clock icon rendered dimensions");
  const iconResponse = await page.request.get(iconState.source);
  assert(iconResponse.ok(), `Clock icon returned HTTP ${iconResponse.status()}.`);
  assert(
    String(iconResponse.headers()["content-type"] || "").startsWith("image/png"),
    "Clock icon did not return image/png.",
  );
  const menuFit = await page.locator("[data-timing-menu-panel]").evaluate((panel) => {
    const panelBox = panel.getBoundingClientRect();
    const labelBox = panel.querySelector("span").getBoundingClientRect();
    return {
      labelRight: labelBox.right,
      panelContentRight: panelBox.right - 6,
    };
  });
  assert(
    menuFit.labelRight <= menuFit.panelContentRight + 1,
    `Timing menu label overflows its panel: ${JSON.stringify(menuFit)}.`,
  );
  await page.keyboard.press("Escape");
  passed("clock menu/icon and unchanged running/paused lifecycle controls");
}


async function verifyCancelFocusEscapeAndTrap(page) {
  await parkAndReset(page);
  const cardId = await navigate(page, "running");
  const before = cardSnapshot(cardId);
  const writes = [];
  const listener = (request) => {
    const pathname = new URL(request.url()).pathname;
    if (request.method() === "POST" && pathname === `/terminal/cards/${cardId}/timing-ledger`) {
      writes.push(pathname);
    }
  };
  page.on("request", listener);

  let editor = await openTimingEditor(page);
  await fillTimingField(page, 0, "start_time", "1001");
  await editor.click({ position: { x: 5, y: 5 } });
  assert(await editor.isVisible(), "Timing-editor backdrop discarded the draft.");
  assertEqual(
    await timingRow(page, 0).locator('[data-timing-field="start_time"]').inputValue(),
    "10:01",
    "backdrop retained timing draft",
  );
  await editor.locator("[data-timing-cancel]").click();
  await editor.waitFor({ state: "hidden" });
  assertEqual(cardSnapshot(cardId), before, "ordinary Cancel database snapshot");
  assertEqual(writes, [], "ordinary Cancel timing writes");
  assert(
    await page.locator("[data-timing-menu-button]").evaluate((button) => document.activeElement === button),
    "Cancel did not restore focus to the overflow trigger.",
  );

  editor = await openTimingEditor(page);
  for (let index = 0; index < 6; index += 1) {
    await page.keyboard.press("Tab");
    await assertFocusInside(page, "[data-timing-dialog]", `forward focus trap Tab ${index + 1}`);
  }
  await editor.locator("[data-timing-save]").focus();
  await page.keyboard.press("Tab");
  await assertFocusInside(page, "[data-timing-dialog]", "forward boundary focus wrap");
  await timingRow(page, 0).locator('[data-timing-field="start_date"]').focus();
  await page.keyboard.press("Shift+Tab");
  await assertFocusInside(page, "[data-timing-dialog]", "reverse boundary focus wrap");
  await page.keyboard.press("Escape");
  await editor.waitFor({ state: "hidden" });
  assert(
    await page.locator("[data-timing-menu-button]").evaluate((button) => document.activeElement === button),
    "Escape did not restore focus to the overflow trigger.",
  );
  assertEqual(cardSnapshot(cardId), before, "Escape database snapshot");
  page.off("request", listener);
  passed("Cancel, Escape, focus trap/restoration, and no draft mutation");
}


async function verifyRunningOrdinarySave(page) {
  await parkAndReset(page);
  const cardId = await navigate(page, "running");
  const before = cardSnapshot(cardId);
  const requests = [];
  page.on("request", (request) => {
    const pathname = new URL(request.url()).pathname;
    if (request.method() === "POST" && pathname === `/terminal/cards/${cardId}/timing-ledger`) {
      requests.push(pathname);
    }
  });
  const editor = await openTimingEditor(page);
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 3, "running initial rows");
  assertEqual(await timingRow(page, 2).locator('[data-timing-field^="stop_"]').count(), 0, "blank final open stop");

  assertEqual(
    await timingRow(page, 2).getByRole("button", { name: /Изтрий интервал/ }).count(),
    0,
    "running final open row Delete action",
  );

  await editor.locator("[data-timing-add-interval]").click();
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 4, "running rows after Add Interval");
  assertEqual(await timingRow(page, 2).locator('[data-timing-field^="start_"]').count(), 2, "inserted row start controls");
  const insertedDelete = timingRow(page, 2).getByRole("button", { name: "Изтрий интервал 3" });
  await insertedDelete.click();
  const insertedConfirmation = page.locator("[data-timing-delete-confirm-overlay]");
  await insertedConfirmation.waitFor({ state: "visible" });
  assertEqual(
    normalized(await insertedConfirmation.locator("[data-timing-delete-confirm-prompt]").textContent()),
    "Сигурни ли сте, че искате да изтриете интервал №3?",
    "inserted interval confirmation",
  );
  await insertedConfirmation.locator("[data-timing-delete-confirm-submit]").click();
  assertEqual(
    await page.locator("[data-timing-interval-list] .interval-row").count(),
    3,
    "unsaved inserted row removal",
  );
  await page.waitForTimeout(50);
  assert(
    await timingRow(page, 1).getByRole("button", { name: "Изтрий интервал 2" }).evaluate(
      (button) => document.activeElement === button,
    ),
    "Removing an unsaved interval did not move focus to the previous Delete action.",
  );
  await editor.locator("[data-timing-add-interval]").click();
  assertEqual(
    await page.locator("[data-timing-interval-list] .interval-row").count(),
    4,
    "running rows after re-adding interval",
  );
  await fillTimingField(page, 2, "stop_date", "20.08.2026");
  await fillTimingField(page, 2, "start_date", "20.08.2026");
  const maskedInput = await fillTimingField(page, 2, "start_time", "1202");
  await fillTimingField(page, 2, "stop_time", "1208");
  assertEqual(await maskedInput.inputValue(), "12:02", "1202 numeric time mask");
  assertEqual(await timingRow(page, 3).locator('[data-timing-field="start_time"]').inputValue(), "12:10", "ongoing start remains unchanged");
  assertEqual(await timingRow(page, 3).locator('[data-timing-field^="stop_"]').count(), 0, "ongoing interval remains final");

  await Promise.all([
    page.waitForURL((url) => url.searchParams.get("notice") === "timing_saved", { waitUntil: "networkidle" }),
    editor.locator("[data-timing-save]").click(),
  ]);
  const after = cardSnapshot(cardId);
  assertEqual(requests.length, 1, "ordinary running Save request count");
  assertEqual(after.card.version, before.card.version + 1, "ordinary running version increment");
  assertEqual(after.timing.length, 4, "ordinary running persisted interval count");
  assertEqual(after.timing[0].slice(1), before.timing[0].slice(1), "untouched running seconds preservation");
  assertEqual(after.timing[2].slice(1), ["2026-08-20 09:02:00", "2026-08-20 09:08:00", "correction"], "running inserted historical interval");
  assertEqual(after.timing[3].slice(1), ["2026-08-20 09:10:43", null, null], "running ongoing interval remains unchanged");
  passed("running Save, Add Interval, confirmed draft Delete, blank stop, mask, seconds, and end reasons");
}


async function verifyInAppDeleteConfirmation(page) {
  await parkAndReset(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  let cardId = await navigate(page, "running");
  let before = cardSnapshot(cardId);
  const saveRequests = [];
  const saveListener = (request) => {
    const pathname = new URL(request.url()).pathname;
    if (request.method() === "POST" && pathname === `/terminal/cards/${cardId}/timing-ledger`) {
      saveRequests.push(pathname);
    }
  };
  page.on("request", saveListener);

  let editor = await openTimingEditor(page);
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 3, "delete confirmation initial rows");
  const firstDelete = timingRow(page, 0).getByRole("button", { name: "Изтрий интервал 1" });
  await firstDelete.click();
  const confirmation = page.locator("[data-timing-delete-confirm-overlay]");
  await confirmation.waitFor({ state: "visible" });
  assertEqual(
    normalized(await confirmation.locator("#timing-delete-confirm-title").textContent()),
    "Изтриване на интервал",
    "deletion confirmation title",
  );
  assertEqual(
    normalized(await confirmation.locator("[data-timing-delete-confirm-prompt]").textContent()),
    "Сигурни ли сте, че искате да изтриете интервал №1?",
    "dismissed deletion confirmation",
  );
  assert(
    await confirmation.locator("[data-timing-delete-confirm-cancel]").evaluate(
      (button) => document.activeElement === button,
    ),
    "Delete confirmation did not receive focus.",
  );
  await confirmation.locator("[data-timing-delete-confirm-submit]").focus();
  await page.keyboard.press("Tab");
  assert(
    await confirmation.locator("[data-timing-delete-confirm-cancel]").evaluate(
      (button) => document.activeElement === button,
    ),
    "Delete confirmation forward focus trap did not wrap.",
  );
  await page.keyboard.press("Shift+Tab");
  assert(
    await confirmation.locator("[data-timing-delete-confirm-submit]").evaluate(
      (button) => document.activeElement === button,
    ),
    "Delete confirmation reverse focus trap did not wrap.",
  );
  await captureScreenshot(page, deleteConfirmationScreenshot1366, { width: 1366, height: 768 });
  summary.screenshots.push(path.relative(repoRoot, deleteConfirmationScreenshot1366));
  await page.keyboard.press("Escape");
  await confirmation.waitFor({ state: "hidden" });
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 3, "dismissed deletion rows");
  assertEqual(saveRequests, [], "dismissed deletion timing Save requests");
  assert(await firstDelete.evaluate((button) => document.activeElement === button), "Escape did not restore Delete focus.");

  await firstDelete.click();
  await confirmation.waitFor({ state: "visible" });
  await confirmation.click({ position: { x: 2, y: 2 } });
  await confirmation.waitFor({ state: "hidden" });
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 3, "backdrop-dismissed deletion rows");
  assert(await firstDelete.evaluate((button) => document.activeElement === button), "Backdrop dismissal did not restore Delete focus.");

  await firstDelete.click();
  await confirmation.waitFor({ state: "visible" });
  await confirmation.locator("[data-timing-delete-confirm-cancel]").click();
  await confirmation.waitFor({ state: "hidden" });
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 3, "Cancel-dismissed deletion rows");
  assertEqual(saveRequests, [], "all dismissed deletion timing Save requests");
  assert(await firstDelete.evaluate((button) => document.activeElement === button), "Cancel did not restore Delete focus.");

  await firstDelete.click();
  await confirmation.waitFor({ state: "visible" });
  await confirmation.locator("[data-timing-delete-confirm-submit]").click();
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 2, "accepted deletion rows");
  assertEqual(
    await page.locator("[data-timing-interval-list] .interval-number").allTextContents(),
    ["1", "2"],
    "contiguous visible interval numbers",
  );
  await page.waitForFunction(() => document.activeElement?.getAttribute("aria-label") === "Изтрий интервал 1");
  assertEqual(saveRequests, [], "accepted deletion timing Save requests");

  const remainingDelete = timingRow(page, 0).getByRole("button", { name: "Изтрий интервал 1" });
  await remainingDelete.click();
  await confirmation.locator("[data-timing-delete-confirm-submit]").click();
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 1, "second accepted deletion rows");
  await page.waitForFunction(() => document.activeElement?.hasAttribute("data-timing-add-interval"));
  assertEqual(saveRequests, [], "cascaded deletion timing Save requests");
  await editor.locator("[data-timing-cancel]").click();
  await editor.waitFor({ state: "hidden" });
  assertEqual(cardSnapshot(cardId), before, "accepted deletion then Cancel database snapshot");

  editor = await openTimingEditor(page);
  const middleDelete = timingRow(page, 1).getByRole("button", { name: "Изтрий интервал 2" });
  await middleDelete.click();
  await confirmation.locator("[data-timing-delete-confirm-submit]").click();
  await page.waitForFunction(() => document.activeElement?.getAttribute("aria-label") === "Изтрий интервал 1");
  assertEqual(
    await page.locator("[data-timing-interval-list] .interval-number").allTextContents(),
    ["1", "2"],
    "middle deletion contiguous interval numbers",
  );
  await Promise.all([
    page.waitForURL((url) => url.searchParams.get("notice") === "timing_saved", { waitUntil: "networkidle" }),
    editor.locator("[data-timing-save]").click(),
  ]);
  let after = cardSnapshot(cardId);
  assertEqual(saveRequests.length, 1, "confirmed deletion Save request count");
  assertEqual(after.card.version, before.card.version + 1, "confirmed deletion version increment");
  assertEqual(after.timing.length, before.timing.length - 1, "confirmed deletion persisted count");
  assertEqual(
    after.timing.map((row) => row.slice(1)),
    [before.timing[0].slice(1), before.timing[2].slice(1)],
    "confirmed deletion persisted exactly the selected interval",
  );
  page.off("request", saveListener);

  await parkAndReset(page);
  cardId = await navigate(page, "paused");
  before = cardSnapshot(cardId);
  editor = await openTimingEditor(page);
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 2, "paused initial rows");
  await timingRow(page, 0).getByRole("button", { name: "Изтрий интервал 1" }).click();
  await confirmation.locator("[data-timing-delete-confirm-submit]").click();
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 1, "paused sole remaining row");
  assertEqual(
    await timingRow(page, 0).getByRole("button", { name: /Изтрий интервал/ }).count(),
    0,
    "paused sole row Delete action",
  );
  await editor.locator("[data-timing-cancel]").click();
  assertEqual(cardSnapshot(cardId), before, "paused draft deletion Cancel database snapshot");
  passed("in-app Delete dismissal/acceptance, focus containment/restoration, contiguous numbers, protected rows, Cancel, and atomic Save");
}


async function verifyPausedOrdinarySave(page) {
  await parkAndReset(page);
  const cardId = await navigate(page, "paused");
  const before = cardSnapshot(cardId);
  const editor = await openTimingEditor(page);
  await fillTimingField(page, 0, "start_time", "1031");
  await editor.locator("[data-timing-add-interval]").click();
  const addedIndex = (await page.locator("[data-timing-interval-list] .interval-row").count()) - 1;
  await fillTimingField(page, addedIndex, "start_date", "20.08.2026");
  await fillTimingField(page, addedIndex, "start_time", "1230");
  await fillTimingField(page, addedIndex, "stop_date", "20.08.2026");
  await fillTimingField(page, addedIndex, "stop_time", "1300");
  await Promise.all([
    page.waitForURL((url) => url.searchParams.get("notice") === "timing_saved", { waitUntil: "networkidle" }),
    editor.locator("[data-timing-save]").click(),
  ]);
  const after = cardSnapshot(cardId);
  assertEqual(after.card.version, before.card.version + 1, "ordinary paused version increment");
  assertEqual(after.timing[0][1], "2026-08-20 07:31:00", "changed paused timestamp minute precision");
  assertEqual(after.timing[1].slice(1), before.timing[1].slice(1), "untouched paused seconds preservation");
  assertEqual(after.timing[2].slice(1), ["2026-08-20 09:30:00", "2026-08-20 10:00:00", "correction"], "paused correction row");
  passed("paused atomic Save and changed/untouched second semantics");
}


async function submitServerInvalidEditor(page, editor) {
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    editor.locator("[data-timing-save-form]").evaluate((form) => form.requestSubmit()),
  ]);
  await page.locator("[data-timing-editor-overlay]").waitFor({ state: "visible" });
}


async function verifyValidationFailures(page) {
  await parkAndReset(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  let cardId = await navigate(page, "paused");
  let before = cardSnapshot(cardId);
  let saveRequests = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST"
      && new URL(request.url()).pathname === `/terminal/cards/${cardId}/timing-ledger`
    ) saveRequests += 1;
  });
  let editor = await openTimingEditor(page);
  const dateField = timingRow(page, 0).locator('[data-timing-field-wrapper="true"]').first();
  const day = dateField.locator('[data-date-segment="day"]');
  const month = dateField.locator('[data-date-segment="month"]');
  const year = dateField.locator('[data-date-segment="year"]');
  assertEqual(await dateField.locator("input").count(), 3, "date has day, month, and year segments");
  assertEqual(
    [await day.inputValue(), await month.inputValue(), await year.inputValue()],
    ["20", "08", "2026"],
    "initial Bulgarian date segments",
  );

  await day.click();
  assertEqual(
    await day.evaluate((input) => [input.selectionStart, input.selectionEnd]),
    [0, 2],
    "click selects the complete day",
  );
  await page.keyboard.type("19");
  assertEqual(await day.inputValue(), "19", "typing replaces only the selected day");
  assert(
    await month.evaluate((input) => document.activeElement === input && input.selectionStart === 0 && input.selectionEnd === 2),
    "complete day did not select the month",
  );
  await page.keyboard.type("07");
  assertEqual(await month.inputValue(), "07", "typing replaces only the selected month");
  assert(
    await year.evaluate((input) => document.activeElement === input && input.selectionStart === 0 && input.selectionEnd === 4),
    "complete month did not select the year",
  );
  await page.keyboard.type("262626");
  assertEqual(await year.inputValue(), "2626", "four-digit date year limit");

  await day.click();
  await page.keyboard.press("Backspace");
  assertEqual(
    [await day.inputValue(), await month.inputValue(), await year.inputValue()],
    ["", "07", "2626"],
    "deleting the day preserves month and year positions",
  );
  await page.keyboard.type("20");
  await page.keyboard.type("08");
  await page.keyboard.type("2026");
  assertEqual(
    [await day.inputValue(), await month.inputValue(), await year.inputValue()],
    ["20", "08", "2026"],
    "day-to-month-to-year keyboard replacement",
  );

  const editedHour = timingRow(page, 0).locator('[data-timing-field="start_time"]');
  const timeBox = await editedHour.boundingBox();
  assert(timeBox, "Start-time control has no visible bounding box.");
  await editedHour.click({ position: { x: 12, y: timeBox.height / 2 } });
  assertEqual(
    await editedHour.evaluate((input) => [input.selectionStart, input.selectionEnd]),
    [0, 2],
    "clicking the hour selects the complete hour",
  );
  await captureScreenshot(
    page,
    timeSelectionScreenshot1366,
    { width: 1366, height: 768 },
  );
  summary.screenshots.push(path.relative(repoRoot, timeSelectionScreenshot1366));
  await page.keyboard.type("09");
  assertEqual(await editedHour.inputValue(), "09:30", "selected-hour replacement preserves minutes");
  await editedHour.click({
    position: { x: timeBox.width - 12, y: timeBox.height / 2 },
  });
  assertEqual(
    await editedHour.evaluate((input) => [input.selectionStart, input.selectionEnd]),
    [3, 5],
    "clicking the minutes selects the complete minutes",
  );
  await page.keyboard.type("31");
  assertEqual(await editedHour.inputValue(), "09:31", "selected-minute replacement preserves hours");
  await editedHour.evaluate((input) => input.setSelectionRange(3, 3));
  await page.keyboard.press("Backspace");
  assertEqual(await editedHour.inputValue(), "0:31", "Backspace at the colon removes the preceding digit");
  await page.keyboard.type("9");
  assertEqual(await editedHour.inputValue(), "09:31", "time digit can be re-entered after separator Backspace");
  await editedHour.fill("10:30");
  await editor.locator("[data-timing-add-interval]").click();
  assertEqual(
    normalized(await editor.locator("[data-timing-production-total]").textContent()),
    "—",
    "incomplete Add Interval clears production total",
  );
  assertEqual(
    normalized(await editor.locator("[data-timing-paused-total]").textContent()),
    "—",
    "incomplete Add Interval clears paused total",
  );
  let addedIndex = (await page.locator("[data-timing-interval-list] .interval-row").count()) - 1;
  await fillTimingField(page, addedIndex, "start_date", "20.08.2026");
  const incomplete = await fillTimingField(page, addedIndex, "start_time", "13");
  await fillTimingField(page, addedIndex, "stop_date", "20.08.2026");
  await fillTimingField(page, addedIndex, "stop_time", "1400");
  await editor.locator("[data-timing-save]").click();
  assert(await editor.isVisible(), "Incomplete draft closed the editor.");
  assert(normalized(await editor.locator("[data-timing-alert]").textContent()).includes("Попълнете"), "Incomplete draft warning is missing.");
  assert(await incomplete.evaluate((input) => document.activeElement === input), "Incomplete field did not receive focus.");
  assertEqual(saveRequests, 0, "incomplete draft Save requests");
  assertEqual(cardSnapshot(cardId), before, "incomplete draft database snapshot");

  await incomplete.fill("1300");
  const invalid = await fillTimingField(page, addedIndex, "stop_time", "2500");
  await editor.locator("[data-timing-save]").click();
  assert(await editor.isVisible(), "Impossible time closed the editor.");
  assertEqual(await invalid.inputValue(), "25:00", "invalid time draft retention");
  assert(await invalid.evaluate((input) => document.activeElement === input), "Invalid time did not receive focus.");
  assert(
    normalized(await editor.locator("[data-timing-alert]").textContent()).includes("Попълнете"),
    "Invalid-time warning is missing.",
  );
  assertEqual(saveRequests, 0, "invalid time Save requests");
  assertEqual(cardSnapshot(cardId), before, "invalid time database snapshot");

  await parkAndReset(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  cardId = await navigate(page, "paused");
  before = cardSnapshot(cardId);
  editor = await openTimingEditor(page);
  await fillTimingField(page, 0, "start_date", "01.01.2099");
  await fillTimingField(page, 0, "stop_date", "01.01.2099");
  await submitServerInvalidEditor(page, editor);
  const futureDate = timingRow(page, 0).locator('[data-timing-field="start_date"]');
  assertEqual(await futureDate.getAttribute("aria-invalid"), "true", "future boundary aria state");
  assert(
    await futureDate.evaluate((input) => document.activeElement === input),
    "Explicit Save rejection did not focus the first invalid boundary.",
  );
  assertEqual(await editor.locator("[data-timing-alert] p").count(), 1, "single primary future error");
  assertEqual(await editor.locator("[data-timing-field-error]").count(), 0, "no inline timing errors");
  assertEqual(
    normalized(await timingRow(page, 0).locator(".interval-duration").textContent()),
    "—",
    "invalid row duration",
  );
  await futureDate.click();
  await page.waitForTimeout(300);
  assert(await futureDate.evaluate((input) => document.activeElement === input), "Future preview stole focus from the date correction.");
  assert(
    normalized(await page.locator("[data-timing-dialog]").textContent()).includes("бъдещето"),
    "Future timestamp rejection is missing.",
  );
  await captureScreenshot(
    page,
    validationScreenshot1366,
    { width: 1366, height: 768 },
  );
  summary.screenshots.push(path.relative(repoRoot, validationScreenshot1366));
  assertEqual(
    Math.round((await timingRow(page, 0).locator(".segmented-date-input").first().boundingBox()).width),
    120,
    "invalid date control width",
  );
  assertEqual(cardSnapshot(cardId), before, "future draft database snapshot");
  passed("stable date/time editing and recoverable consolidated validation");
}


async function verifyRunningPreviewDoesNotReplaceInputs(page) {
  await parkAndReset(page);
  await navigate(page, "running");
  const editor = await openTimingEditor(page);
  const date = timingRow(page, 0).locator('[data-timing-field="start_date"]');
  await date.focus();
  await date.evaluate((input) => { input.dataset.previewIdentity = "retained"; });
  const previewResponse = page.waitForResponse(
    (response) => response.request().method() === "POST"
      && new URL(response.url()).pathname.endsWith("/timing-ledger/preview"),
  );
  await page.evaluate(() => document.dispatchEvent(new CustomEvent("terminal:server-time", {
    detail: { serverNowUtc: new Date().toISOString() },
  })));
  assert((await previewResponse).ok(), "Running server-time preview failed.");
  assertEqual(await date.getAttribute("data-preview-identity"), "retained", "preview input DOM identity");
  assert(await date.evaluate((input) => document.activeElement === input), "Running preview moved focus.");
  await editor.locator("[data-timing-cancel]").click();
  passed("running previews update calculations without replacing active inputs");
}


async function verifyStructuralChangesClearTotals(page) {
  await parkAndReset(page);
  await navigate(page, "paused");
  const editor = await openTimingEditor(page);
  assert(
    normalized(await editor.locator("[data-timing-production-total]").textContent()) !== "—",
    "Paused editor did not start with calculated totals.",
  );
  await editor.locator("[data-timing-add-interval]").click();
  assertEqual(
    normalized(await editor.locator("[data-timing-production-total]").textContent()),
    "—",
    "incomplete Add Interval clears production total",
  );
  assertEqual(
    normalized(await editor.locator("[data-timing-paused-total]").textContent()),
    "—",
    "incomplete Add Interval clears paused total",
  );
  await editor.locator("[data-timing-cancel]").click();
  passed("structural draft changes clear calculations until server recalculation");
}


async function verifyPersistenceLocksDismissal(page) {
  await parkAndReset(page);
  let cardId = await navigate(page, "running");
  let editor = await openTimingEditor(page);
  await editor.locator("[data-timing-save-form]").evaluate((form) => {
    form.addEventListener("submit", (event) => event.preventDefault(), { capture: true });
  });
  await editor.locator("[data-timing-save]").click();
  assertEqual(await editor.locator("[data-timing-dialog]").getAttribute("aria-busy"), "true", "timing editor submit busy state");
  assert(await editor.locator("[data-timing-cancel]").isDisabled(), "Timing Cancel remained active during Save.");
  assert(await editor.locator("[data-timing-add-interval]").isDisabled(), "Add Interval remained active during Save.");
  const saveDate = timingRow(page, 0).locator(
    '[data-timing-date-field="start_date"] [data-date-segment="day"]',
  );
  const saveTime = timingRow(page, 0).locator('[data-timing-field="start_time"]');
  const saveDateBefore = await saveDate.inputValue();
  const saveTimeBefore = await saveTime.inputValue();
  await saveDate.focus();
  await page.keyboard.type("19");
  await saveTime.focus();
  await page.keyboard.type("09");
  assertEqual(await saveDate.inputValue(), saveDateBefore, "ordinary Save pending date edit lock");
  assertEqual(await saveTime.inputValue(), saveTimeBefore, "ordinary Save pending time edit lock");
  await page.keyboard.press("Escape");
  assert(await editor.isVisible(), "Escape hid the timing editor during Save.");

  await parkAndReset(page);
  cardId = await navigate(page, "running");
  await beginFinishReview(page, cardId);
  let finishOverlay = page.locator("[data-finish-review-overlay]");
  await finishOverlay.locator("[data-finish-review-edit]").click();
  editor = page.locator("[data-timing-editor-overlay]");
  await editor.waitFor({ state: "visible" });
  const applyPath = `/terminal/cards/${cardId}/finish-review/preview`;
  let releaseApplyResponse;
  let markApplyStarted;
  const applyStarted = new Promise((resolve) => { markApplyStarted = resolve; });
  await page.route(`**${applyPath}`, async (route) => {
    markApplyStarted();
    await new Promise((resolve) => { releaseApplyResponse = resolve; });
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        ok: false,
        messages: ["Проверка на заключването при неуспешно прилагане."],
        field_errors: [{
          source_index: null,
          field: "form",
          message: "Проверка на заключването при неуспешно прилагане.",
        }],
      }),
    });
  });
  await editor.locator("[data-timing-save]").click();
  await applyStarted;
  assertEqual(await editor.locator("[data-timing-dialog]").getAttribute("aria-busy"), "true", "Finish Apply busy state");
  const applyDate = timingRow(page, 0).locator(
    '[data-timing-date-field="start_date"] [data-date-segment="day"]',
  );
  const applyTime = timingRow(page, 0).locator('[data-timing-field="start_time"]');
  const applyDateBefore = await applyDate.inputValue();
  const applyTimeBefore = await applyTime.inputValue();
  await applyDate.focus();
  await page.keyboard.type("19");
  await applyTime.focus();
  await page.keyboard.type("09");
  assertEqual(await applyDate.inputValue(), applyDateBefore, "Finish Apply pending date edit lock");
  assertEqual(await applyTime.inputValue(), applyTimeBefore, "Finish Apply pending time edit lock");
  releaseApplyResponse();
  await page.waitForFunction(() => (
    document.querySelector("[data-timing-dialog]")?.getAttribute("aria-busy") === "false"
  ));
  assert(
    await applyDate.evaluate((input) => !input.readOnly),
    "Finish Apply failure did not restore date editing.",
  );
  assert(
    await applyTime.evaluate((input) => !input.readOnly),
    "Finish Apply failure did not restore time editing.",
  );
  await page.unroute(`**${applyPath}`);
  await editor.locator("[data-timing-cancel]").click();
  await finishOverlay.locator("[data-finish-review-cancel]").click();

  await parkAndReset(page);
  cardId = await navigate(page, "running");
  await beginFinishReview(page, cardId);
  finishOverlay = page.locator("[data-finish-review-overlay]");
  await page.locator('form[data-timing-finish-review="true"]').evaluate((form) => {
    form.addEventListener("submit", (event) => event.preventDefault(), { capture: true });
  });
  await finishOverlay.locator("[data-finish-review-confirm]").click();
  assertEqual(await finishOverlay.locator("[data-finish-review-dialog]").getAttribute("aria-busy"), "true", "finish review submit busy state");
  assert(await finishOverlay.locator("[data-finish-review-cancel]").isDisabled(), "Finish Cancel remained active during confirmation.");
  assert(await finishOverlay.locator("[data-finish-review-edit]").isDisabled(), "Finish Edit remained active during confirmation.");
  await page.keyboard.press("Escape");
  assert(await finishOverlay.isVisible(), "Escape hid Finish review during confirmation.");
  passed("Save, Finish Apply, and Finish confirmation lock edits and dismissal while pending");
}


async function verifyInitialFinishRowErrorRecovery(page) {
  await parkAndReset(page);
  const cardId = await navigate(page, "running");
  const reviewPath = `/terminal/cards/${cardId}/finish-review`;
  await page.route(`**${reviewPath}`, async (route) => {
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        ok: false,
        messages: ["Времето не може да бъде в бъдещето."],
        field_errors: [{
          source_index: 0,
          field: "start_time",
          message: "Времето не може да бъде в бъдещето.",
        }],
      }),
    });
  });
  await page.locator(`form[action="/terminal/cards/${cardId}/finish"] button[type="submit"]`).click();
  const editor = page.locator("[data-timing-editor-overlay]");
  await editor.waitFor({ state: "visible" });
  assertEqual(normalized(await editor.locator("#timing-dialog-title").textContent()), "Корекция на производствено време", "row-error recovery editor mode");
  assertEqual(normalized(await editor.locator("[data-timing-save]").textContent()), "Запиши", "row-error recovery action");
  assert(
    normalized(await editor.locator("[data-timing-alert]").textContent()).includes("запишете"),
    "Row-error recovery did not instruct the operator to save before retrying Finish.",
  );
  await editor.locator("[data-timing-cancel]").click();
  await page.unroute(`**${reviewPath}`);
  passed("initial Finish row errors recover through the ordinary correction editor");
}


async function verifyManyRowsAnd1366Screenshot(page) {
  await parkAndReset(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  await navigate(page, "many_rows");
  const editor = await openTimingEditor(page);
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 18, "many-row interval count");
  const firstControls = timingRow(page, 0).locator(".timestamp-controls").first();
  const dateWidth = await firstControls.locator(".segmented-date-input").evaluate(
    (element) => Math.round(element.getBoundingClientRect().width),
  );
  const timeWidth = await firstControls.locator('[data-timing-field$="_time"]').evaluate(
    (element) => Math.round(element.getBoundingClientRect().width),
  );
  const controlBox = await firstControls.boundingBox();
  const dateBox = await firstControls.locator(".segmented-date-input").boundingBox();
  const timeBox = await firstControls.locator('[data-timing-field$="_time"]').boundingBox();
  assertEqual(dateWidth, 120, "compact date control width");
  assertEqual(timeWidth, 78, "compact time control width");
  assert(controlBox && dateBox && timeBox, "Timing controls could not be measured.");
  const leftSpace = dateBox.x - controlBox.x;
  const rightSpace = controlBox.x + controlBox.width - (timeBox.x + timeBox.width);
  assert(
    Math.abs(leftSpace - rightSpace) <= 1,
    `Timestamp controls are not centered: left ${leftSpace}, right ${rightSpace}.`,
  );
  const list = page.locator("[data-timing-interval-list]");
  const scrollState = await list.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }));
  assert(scrollState.scrollHeight > scrollState.clientHeight, "Many-row interval body does not scroll internally.");
  const fixedChrome = "[data-timing-dialog] header, [data-timing-totals], [data-timing-column-headings], [data-timing-dialog] footer";
  const before = await page.locator(fixedChrome).evaluateAll(
    (elements) => elements.map((element) => element.getBoundingClientRect().y),
  );
  await list.evaluate((element) => { element.scrollTop = element.scrollHeight; });
  const after = await page.locator(fixedChrome).evaluateAll(
    (elements) => elements.map((element) => element.getBoundingClientRect().y),
  );
  assertEqual(after, before, "fixed timing chrome after internal scrolling");
  const dialogBox = await page.locator("[data-timing-dialog]").boundingBox();
  assert(dialogBox !== null && dialogBox.height <= 728.5, "Timing dialog exceeds accepted 728px working height.");
  await captureScreenshot(page, screenshot1366, { width: 1366, height: 768 });
  summary.screenshots.push(path.relative(repoRoot, screenshot1366));
  summary.viewports.push({ width: 1366, height: 768, dialog: "timing editor" });
  await editor.locator("[data-timing-cancel]").click();
  passed("many-row internal scroll with fixed chrome at 1366x768");
}


async function beginFinishReview(page, cardId, { doubleSubmit = false } = {}) {
  const responsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST"
      && new URL(response.url()).pathname === `/terminal/cards/${cardId}/finish-review`,
  );
  const button = page.locator(`form[action="/terminal/cards/${cardId}/finish"] button[type="submit"]`);
  if (doubleSubmit) {
    await button.evaluate((element) => {
      element.click();
      element.click();
    });
  } else {
    await button.click();
  }
  const response = await responsePromise;
  const payload = await response.json();
  await page.locator("[data-finish-review-overlay]").waitFor({ state: "visible" });
  return payload;
}


async function applyFinishEditor(page) {
  const responsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST"
      && new URL(response.url()).pathname.endsWith("/finish-review/preview"),
  );
  await page.locator("[data-timing-save]").click();
  const response = await responsePromise;
  assert(response.ok(), `Finish draft preview returned HTTP ${response.status()}.`);
  await page.locator("[data-finish-review-overlay]").waitFor({ state: "visible" });
}


async function verifyRunningFinishReview(page) {
  await parkAndReset(page);
  const cardId = await navigate(page, "running");
  const before = cardSnapshot(cardId);
  const requests = [];
  page.on("request", (request) => {
    if (request.method() === "POST") requests.push(new URL(request.url()).pathname);
  });

  let payload = await beginFinishReview(page, cardId, { doubleSubmit: true });
  assert(payload.ok, "Running finish review did not return an accepted preview.");
  assertEqual(
    requests.filter((pathname) => pathname === `/terminal/cards/${cardId}/finish-review`).length,
    1,
    "double-click finish-review request count",
  );
  const finishOverlay = page.locator("[data-finish-review-overlay]");
  assertEqual(
    await finishOverlay.locator(".finish-review-intro").count(),
    0,
    "finish explanatory paragraph absence",
  );
  assertEqual(
    normalized(await finishOverlay.locator("[data-finish-first-start]").textContent()),
    "20/08/26 10:00",
    "compact finish start",
  );
  assert(
    /^\d{2}\/\d{2}\/\d{2} \d{2}:\d{2}$/.test(
      normalized(await finishOverlay.locator("[data-finish-proposed-stop]").textContent()),
    ),
    "Finish stop does not use dd/mm/yy hh:mm.",
  );
  assertEqual(
    await finishOverlay.locator("[data-finish-timing-summary]").count(),
    1,
    "single finish timing summary",
  );
  const productionSummary = finishOverlay.locator("[data-finish-production-summary]");
  assertEqual(await productionSummary.count(), 1, "finish production summary table");
  assertEqual(
    await productionSummary.locator("thead th").allTextContents(),
    ["Палет №", "Брой ролки", "Бруто, кг", "Тегло на палета, кг", "Нето, кг"],
    "finish production summary headings",
  );
  assert(
    await productionSummary.locator("[data-finish-pallet-weight]").evaluateAll(
      (cells) => cells.length > 0 && cells.every((cell) => cell.textContent.trim() === "—"),
    ),
    "Pallet-weight placeholder is not visibly unconnected.",
  );
  assertEqual(
    normalized(await finishOverlay.locator("[data-finish-review-warning]").textContent()),
    "В поръчката има 1 ролка без палет. Искате ли да приключите поръчката?",
    "mixed-pallet finish warning",
  );
  const proposedStop = await finishOverlay.locator("[data-finish-proposed-stop]").textContent();
  await page.waitForTimeout(1200);
  assertEqual(await finishOverlay.locator("[data-finish-proposed-stop]").textContent(), proposedStop, "frozen proposed finish display");
  for (let index = 0; index < 5; index += 1) {
    await page.keyboard.press("Tab");
    await assertFocusInside(page, "[data-finish-review-dialog]", "finish-review focus trap");
  }
  await page.keyboard.press("Escape");
  await finishOverlay.waitFor({ state: "hidden" });
  assertEqual(cardSnapshot(cardId), before, "Escape finish-review database snapshot");

  payload = await beginFinishReview(page, cardId);
  const originalFinishTotal = await finishOverlay.locator("[data-finish-production-total]").textContent();
  await finishOverlay.locator("[data-finish-review-edit]").click();
  const editor = page.locator("[data-timing-editor-overlay]");
  await editor.waitFor({ state: "visible" });
  const originalEditorDuration = await timingRow(page, 0).locator(".interval-duration").textContent();
  const livePreviewResponse = page.waitForResponse(
    (response) => response.request().method() === "POST"
      && new URL(response.url()).pathname.endsWith("/finish-review/preview"),
  );
  const editedStop = await fillTimingField(page, 0, "stop_time", "1059");
  await editedStop.press("Tab");
  assert((await livePreviewResponse).ok(), "Automatic Finish-editor preview failed.");
  await page.waitForFunction(() => (
    document.querySelector("[data-timing-totals]")?.getAttribute("aria-busy") === "false"
  ));
  assert(
    await timingRow(page, 0).locator(".interval-delete").evaluate(
      (button) => document.activeElement === button,
    ),
    "Finish-editor preview did not preserve focus on the row action.",
  );
  assert(
    await timingRow(page, 0).locator(".interval-duration").textContent() !== originalEditorDuration,
    "Finish-editor interval duration did not update automatically.",
  );
  await editor.locator("[data-timing-cancel]").click();
  await editor.waitFor({ state: "hidden" });
  await finishOverlay.waitFor({ state: "visible" });
  assertEqual(
    requests.filter((pathname) => pathname.endsWith("/finish-review/preview")).length,
    1,
    "single automatic Finish-editor preview request",
  );
  assertEqual(
    await finishOverlay.locator("[data-finish-production-total]").textContent(),
    originalFinishTotal,
    "Finish-editor Cancel restored the unchanged summary",
  );
  assertEqual(cardSnapshot(cardId), before, "Cancel unapplied finish draft database snapshot");

  await finishOverlay.locator("[data-finish-review-edit]").click();
  await editor.waitFor({ state: "visible" });
  await fillTimingField(page, 0, "start_time", "1001");
  await applyFinishEditor(page);
  assertEqual(cardSnapshot(cardId), before, "Apply finish draft database snapshot");
  await finishOverlay.locator("[data-finish-review-cancel]").click();
  await finishOverlay.waitFor({ state: "hidden" });
  assertEqual(cardSnapshot(cardId), before, "Cancel applied finish draft database snapshot");

  payload = await beginFinishReview(page, cardId);
  await finishOverlay.locator("[data-finish-review-edit]").click();
  await editor.waitFor({ state: "visible" });
  await fillTimingField(page, 0, "start_time", "1002");
  await applyFinishEditor(page);

  let releaseFinish;
  const finishGate = new Promise((resolve) => { releaseFinish = resolve; });
  let finishRequestCount = 0;
  let markFinishEntered;
  const finishEntered = new Promise((resolve) => { markFinishEntered = resolve; });
  const finishPattern = `**/terminal/cards/${cardId}/finish`;
  await page.route(finishPattern, async (route) => {
    finishRequestCount += 1;
    markFinishEntered();
    await finishGate;
    await route.continue();
  });
  const navigation = page.waitForURL(
    (url) => url.pathname === `/terminal/cards/${cardId}`
      && url.searchParams.get("notice") === "card_finished",
    { waitUntil: "networkidle" },
  );
  await finishOverlay.locator("[data-finish-review-confirm]").evaluate((button) => {
    button.click();
    button.click();
  });
  await finishEntered;
  assertEqual(finishRequestCount, 1, "double-click Confirm Finish request count");
  releaseFinish();
  await navigation;
  await page.unroute(finishPattern);

  const after = cardSnapshot(cardId);
  assertEqual(after.card.status, "completed", "running Confirm Finish status");
  assertEqual(after.card.version, before.card.version + 1, "running Confirm Finish version increment");
  assertEqual(after.card.finished_at, payload.preview.reviewed_at_utc, "frozen finish persisted instant");
  assertEqual(after.timing[0][1], "2026-08-20 07:02:00", "finish-review edited minute precision");
  assertEqual(after.timing.at(-1)[2], payload.preview.reviewed_at_utc, "running final interval frozen closure");
  summary.requestCounts.finishReviewDoubleClick = 1;
  summary.requestCounts.confirmFinishDoubleClick = finishRequestCount;
  passed("finish freeze, Edit/Apply/Cancel/Confirm, mixed warning, and double-submit blocking");
}


async function verifyPausedFinishAnd1920Screenshot(page) {
  await parkAndReset(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const cardId = await navigate(page, "paused");
  const before = cardSnapshot(cardId);
  await beginFinishReview(page, cardId);
  const finishOverlay = page.locator("[data-finish-review-overlay]");
  assertEqual(
    normalized(await finishOverlay.locator("[data-finish-proposed-stop]").textContent()),
    "20/08/26 12:15",
    "paused proposed stop uses latest closed interval",
  );
  await captureScreenshot(page, screenshot1920, { width: 1920, height: 1080 });
  summary.screenshots.push(path.relative(repoRoot, screenshot1920));
  summary.viewports.push({ width: 1920, height: 1080, dialog: "finish review" });
  await Promise.all([
    page.waitForURL((url) => url.searchParams.get("notice") === "card_finished", { waitUntil: "networkidle" }),
    finishOverlay.locator("[data-finish-review-confirm]").click(),
  ]);
  const after = cardSnapshot(cardId);
  assertEqual(after.card.status, "completed", "paused Confirm Finish status");
  assertEqual(after.card.finished_at, before.timing.at(-1)[2], "paused finished_at latest stop");
  assertEqual(after.timing, before.timing, "paused Confirm Finish timing preservation");
  passed("paused reviewed Finish and 1920x1080 accepted dialog");
}


async function verifyCompletedWaitingAbsenceAndLegacyFinish(page) {
  await parkAndReset(page);
  await navigate(page, "completed");
  assertEqual(await page.locator("[data-timing-menu]").count(), 0, "completed timing menu absence");
  assertEqual(await page.locator('form[data-timing-finish-review="true"]').count(), 0, "completed finish review absence");
  const completedHref = `/terminal/cards/${fixture.cards.completed}`;
  const waitingHref = `/terminal/cards/${fixture.cards.awaiting_rewinding}`;
  assertEqual(await page.locator(`.queue-card[href="${completedHref}"]`).count(), 0, "completed active-queue absence");
  assertEqual(await page.locator(`.queue-card[href="${waitingHref}"]`).count(), 0, "waiting active-queue absence");

  await navigate(page, "awaiting_rewinding");
  assertEqual(await page.locator("[data-timing-menu]").count(), 0, "waiting timing menu absence");
  assertEqual(await page.locator('form[data-timing-finish-review="true"]').count(), 0, "waiting reviewed Finish absence");
  const legacyForm = page.locator('form[data-lifecycle-slot="finish"][data-finish-confirm-form="true"]');
  assertEqual(await legacyForm.count(), 1, "waiting legacy Finish form");
  const requests = [];
  page.on("request", (request) => {
    if (request.method() === "POST") requests.push(new URL(request.url()).pathname);
  });
  await legacyForm.locator("button").click();
  const legacyModal = page.locator("[data-finish-confirm-modal]");
  await legacyModal.waitFor({ state: "visible" });
  assertEqual(await page.locator("[data-finish-review-overlay]:visible").count(), 0, "waiting reviewed overlay absence");
  await legacyModal.locator("[data-finish-confirm-cancel]").click();
  await legacyModal.waitFor({ state: "hidden" });
  assertEqual(requests, [], "waiting simple Finish Cancel requests");
  passed("completed/waiting non-exposure and explicit waiting simple Finish modal");
}


async function verifyStaleTakeover(page) {
  await parkAndReset(page);
  const cardId = await navigate(page, "running");
  const editor = await openTimingEditor(page);
  const draftInput = await fillTimingField(page, 0, "start_time", "1007");
  const rowsBeforeStale = await page.locator("[data-timing-interval-list] .interval-row").count();
  await timingRow(page, 0).getByRole("button", { name: "Изтрий интервал 1" }).click();
  const deleteConfirmation = page.locator("[data-timing-delete-confirm-overlay]");
  await deleteConfirmation.waitFor({ state: "visible" });
  mutateCardVersion(cardId);
  await page.locator("#terminal-refresh-alert").waitFor({ state: "visible", timeout: 15000 });
  await editor.locator("[data-timing-reload]").waitFor({ state: "visible", timeout: 15000 });
  await deleteConfirmation.waitFor({ state: "hidden" });
  assertEqual(
    await page.locator("[data-timing-interval-list] .interval-row").count(),
    rowsBeforeStale,
    "stale confirmation did not mutate the timing draft",
  );
  assertEqual(await draftInput.inputValue(), "10:07", "stale retained visible draft");
  assert(
    await editor.locator("[data-timing-interval-list] input").evaluateAll((inputs) => inputs.every((input) => input.disabled)),
    "Stale timing fields were not locked.",
  );
  assert(await editor.locator("[data-timing-save]").isDisabled(), "Stale Save remained enabled.");
  assert(await editor.locator("[data-timing-cancel]").isEnabled(), "Stale Cancel was disabled.");
  assert(
    await editor.locator("[data-timing-reload]").evaluate((link) => document.activeElement === link),
    "Stale reload link did not receive focus.",
  );
  await editor.locator("[data-timing-cancel]").click();
  await editor.waitFor({ state: "hidden" });

  await parkAndReset(page);
  const finishCardId = await navigate(page, "running");
  await beginFinishReview(page, finishCardId);
  const finishOverlay = page.locator("[data-finish-review-overlay]");
  await finishOverlay.locator("[data-finish-review-edit]").click();
  const finishEditor = page.locator("[data-timing-editor-overlay]");
  await finishEditor.waitFor({ state: "visible" });
  mutateCardVersion(finishCardId);
  await page.locator("#terminal-refresh-alert").waitFor({ state: "visible", timeout: 15000 });
  await finishEditor.locator("[data-timing-reload]").waitFor({ state: "visible", timeout: 15000 });
  await finishEditor.locator("[data-timing-cancel]").click();
  await finishOverlay.waitFor({ state: "visible" });
  assert(
    normalized(await finishOverlay.locator("[data-finish-review-alert]").textContent()).includes("променена"),
    "Stale Finish summary lost its warning after editor Cancel.",
  );
  assert(await finishOverlay.locator("[data-finish-review-edit]").isDisabled(), "Stale Finish Edit was re-enabled.");
  assert(await finishOverlay.locator("[data-finish-review-confirm]").isDisabled(), "Stale Finish Confirm was re-enabled.");
  assert(await finishOverlay.locator("[data-finish-review-cancel]").isEnabled(), "Stale Finish Cancel was disabled.");
  await finishOverlay.locator("[data-finish-review-cancel]").click();
  passed("ordinary and Finish stale takeovers retain locked drafts and require reload or Cancel");
}


async function main() {
  let browser;
  try {
    browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on("pageerror", (error) => summary.pageErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") summary.consoleErrors.push(message.text());
    });
    page.on("requestfailed", (request) => {
      const failure = {
        method: request.method(),
        url: request.url(),
        error: request.failure()?.errorText || "unknown",
      };
      const pathname = new URL(request.url()).pathname;
      if (
        failure.method === "POST"
        && pathname.endsWith("/timing-ledger/preview")
        && failure.error === "net::ERR_ABORTED"
      ) {
        summary.abortedPreviewRequests.push(failure);
        return;
      }
      summary.failedRequests.push(failure);
    });
    page.on("request", (request) => {
      assertEqual(new URL(request.url()).origin, baseOrigin, "browser request origin");
    });

    await verifyLifecycleAndIcon(page);
    await verifyCancelFocusEscapeAndTrap(page);
    await verifyShortLedgerLayouts(page);
    await verifyInAppDeleteConfirmation(page);
    await verifyRunningOrdinarySave(page);
    await verifyPausedOrdinarySave(page);
    await verifyValidationFailures(page);
    await verifyStructuralChangesClearTotals(page);
    await verifyRunningPreviewDoesNotReplaceInputs(page);
    await verifyPersistenceLocksDismissal(page);
    await verifyInitialFinishRowErrorRecovery(page);
    await verifyManyRowsAnd1366Screenshot(page);
    await verifyRunningFinishReview(page);
    await verifyPausedFinishAnd1920Screenshot(page);
    await verifyCompletedWaitingAbsenceAndLegacyFinish(page);
    await verifyStaleTakeover(page);

    const expectedValidationConsoleMessage =
      "Failed to load resource: the server responded with a status of 422 (Unprocessable Entity)";
    summary.expectedValidationConsoleErrors = summary.consoleErrors.filter(
      (message) => message === expectedValidationConsoleMessage,
    );
    summary.consoleErrors = summary.consoleErrors.filter(
      (message) => message !== expectedValidationConsoleMessage,
    );
    assertEqual(summary.consoleErrors, [], "unexpected error-level browser console messages");
    assertEqual(summary.pageErrors, [], "browser page errors");
    assertEqual(summary.failedRequests, [], "failed browser requests");
    summary.status = "passed";
    writeSummary();
    console.log("Terminal timing-correction UI verification passed.");
    console.log(JSON.stringify(summary, null, 2));
  } finally {
    if (browser) await browser.close();
  }
}


main().catch((error) => {
  summary.status = "failed";
  summary.error = error.stack || String(error);
  try {
    writeSummary();
  } catch {
    // Preserve the original verification failure.
  }
  console.error(error.stack || error);
  process.exitCode = 1;
});
