import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
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
  return Boolean(relative) && !relative.startsWith("..") && !path.isAbsolute(relative);
}


function assertNoSymlinkComponents(base, candidate, message) {
  const relative = path.relative(base, candidate);
  assert(
    relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative)),
    message,
  );
  let current = base;
  for (const component of relative.split(path.sep).filter(Boolean)) {
    current = path.join(current, component);
    try {
      assert(!fs.lstatSync(current).isSymbolicLink(), message);
    } catch (error) {
      if (error?.code === "ENOENT") break;
      throw error;
    }
  }
}


function assertSingleLink(filePath, message) {
  if (fs.existsSync(filePath)) {
    assert(fs.statSync(filePath).nlink === 1, message);
  }
}


const baseURL = requiredEnvironment("BASE_URL").replace(/\/+$/, "");
const baseOrigin = new URL(baseURL).origin;
const fixtureInput = requiredEnvironment("FIXTURE_JSON");
const artifactInput = requiredEnvironment("ARTIFACT_DIR");
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = fs.realpathSync(path.resolve(scriptDir, ".."));
const runtimeRoot = path.resolve(repoRoot, ".test-runtime");
const artifactRoot = path.resolve(repoRoot, "artifacts", "ui-checks");
const requestedFixturePath = path.resolve(repoRoot, fixtureInput);
const requestedArtifactDir = path.resolve(repoRoot, artifactInput);

assertNoSymlinkComponents(
  repoRoot,
  runtimeRoot,
  ".test-runtime guard root must not be a symlink.",
);
assert(
  isStrictChild(runtimeRoot, requestedFixturePath),
  "FIXTURE_JSON must be under .test-runtime.",
);
assert(
  isStrictChild(artifactRoot, requestedArtifactDir),
  "ARTIFACT_DIR must be below artifacts/ui-checks.",
);
assertNoSymlinkComponents(
  repoRoot,
  requestedArtifactDir,
  "ARTIFACT_DIR guard path must not contain symlinks.",
);
assert(fs.existsSync(requestedFixturePath), `Fixture JSON does not exist: ${requestedFixturePath}`);
const fixturePath = fs.realpathSync(requestedFixturePath);
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), fixturePath),
  "FIXTURE_JSON must resolve below .test-runtime.",
);
assert(fs.statSync(fixturePath).isFile(), "FIXTURE_JSON must resolve to a regular file.");
assertSingleLink(fixturePath, "FIXTURE_JSON must not be hard-linked.");

let fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const databaseInput = path.resolve(repoRoot, fixture.db_path);
assert(fs.existsSync(databaseInput), `Fixture database does not exist: ${databaseInput}`);
const databasePath = fs.realpathSync(databaseInput);
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), databasePath),
  "Fixture database must resolve below .test-runtime.",
);
assert(fs.statSync(databasePath).isFile(), "Fixture database must be a regular file.");
assertSingleLink(databasePath, "Fixture database must not be hard-linked.");

let artifactDir;
let summaryPath;


function guardedArtifactPath(...components) {
  assert(artifactDir, "Artifact directory is not initialized.");
  const target = path.resolve(artifactDir, ...components);
  assert(isStrictChild(artifactDir, target), "Artifact target must remain below ARTIFACT_DIR.");
  assertNoSymlinkComponents(
    artifactDir,
    target,
    "Artifact target path must not contain symlinks.",
  );
  if (fs.existsSync(target)) {
    assert(fs.statSync(target).isFile(), "Existing artifact target must be a regular file.");
    assertSingleLink(target, "Existing artifact target must not be hard-linked.");
  }
  return target;
}


function freshArtifactTempPath(target) {
  const extension = path.extname(target);
  const temporaryPath = path.join(
    path.dirname(target),
    `.${path.basename(target)}.${process.pid}.${randomUUID()}.tmp${extension}`,
  );
  const descriptor = fs.openSync(temporaryPath, "wx", 0o600);
  fs.closeSync(descriptor);
  return temporaryPath;
}


function atomicWriteArtifact(target, contents) {
  const relativeTarget = path.relative(artifactDir, target);
  const finalPath = guardedArtifactPath(relativeTarget);
  let temporaryPath = freshArtifactTempPath(finalPath);
  try {
    fs.writeFileSync(temporaryPath, contents, "utf8");
    assertSingleLink(temporaryPath, "Temporary artifact must not be hard-linked.");
    const validatedFinalPath = guardedArtifactPath(relativeTarget);
    fs.renameSync(temporaryPath, validatedFinalPath);
    temporaryPath = null;
  } finally {
    if (temporaryPath && fs.existsSync(temporaryPath)) fs.unlinkSync(temporaryPath);
  }
}


async function atomicScreenshot(page, target) {
  const relativeTarget = path.relative(artifactDir, target);
  const finalPath = guardedArtifactPath(relativeTarget);
  let temporaryPath = freshArtifactTempPath(finalPath);
  try {
    await page.screenshot({ path: temporaryPath, fullPage: false });
    assertSingleLink(temporaryPath, "Temporary screenshot must not be hard-linked.");
    const validatedFinalPath = guardedArtifactPath(relativeTarget);
    fs.renameSync(temporaryPath, validatedFinalPath);
    temporaryPath = null;
  } finally {
    if (temporaryPath && fs.existsSync(temporaryPath)) fs.unlinkSync(temporaryPath);
  }
}


const summary = {
  status: "running",
  baseURL,
  databaseIdentity: databasePath,
  fixture: path.relative(repoRoot, fixturePath),
  assertions: [],
  screenshots: [],
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
    fs.realpathSync(path.resolve(health.database_path)),
    databasePath,
    "server database identity",
  );
  passed("health database identity matched exact resolved fixture");
}


await preflightDatabase();

fs.mkdirSync(artifactRoot, { recursive: true });
assertNoSymlinkComponents(
  repoRoot,
  requestedArtifactDir,
  "ARTIFACT_DIR guard path must not contain symlinks.",
);
fs.mkdirSync(requestedArtifactDir, { recursive: true });
artifactDir = fs.realpathSync(requestedArtifactDir);
assert(
  isStrictChild(fs.realpathSync(artifactRoot), artifactDir),
  "ARTIFACT_DIR resolves outside artifacts/ui-checks.",
);
summaryPath = guardedArtifactPath("verification-summary.json");
const screenshot1366 = guardedArtifactPath("timing-editor-1366x768.png");
const screenshot1920 = guardedArtifactPath("finish-review-1920x1080.png");

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
  assert(result.status === 0, `Could not reset guarded fixture: ${normalized(result.stderr)}`);
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


async function fillTimingField(page, rowIndex, field, value) {
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

  const deleteButton = timingRow(page, 0).getByRole("button", { name: "Изтрий интервал 1" });
  await deleteButton.click();
  assert(await timingRow(page, 0).evaluate((row) => row.classList.contains("pending-delete")), "Delete did not mark the row pending.");
  await timingRow(page, 0).getByRole("button", { name: "Отмени изтриването на интервал 1" }).click();
  assert(!(await timingRow(page, 0).evaluate((row) => row.classList.contains("pending-delete"))), "Undo did not restore the row.");

  await editor.locator("[data-timing-add-interval]").click();
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 4, "running rows after Add Interval");
  await fillTimingField(page, 2, "stop_date", "2026-08-20");
  await fillTimingField(page, 2, "stop_time", "1300");
  await fillTimingField(page, 3, "start_date", "2026-08-20");
  const maskedInput = await fillTimingField(page, 3, "start_time", "1350");
  assertEqual(await maskedInput.inputValue(), "13:50", "1350 numeric time mask");
  assertEqual(await timingRow(page, 3).locator('[data-timing-field^="stop_"]').count(), 0, "new final open stop");

  await Promise.all([
    page.waitForURL((url) => url.searchParams.get("notice") === "timing_saved", { waitUntil: "networkidle" }),
    editor.locator("[data-timing-save]").click(),
  ]);
  const after = cardSnapshot(cardId);
  assertEqual(requests.length, 1, "ordinary running Save request count");
  assertEqual(after.card.version, before.card.version + 1, "ordinary running version increment");
  assertEqual(after.timing.length, 4, "ordinary running persisted interval count");
  assertEqual(after.timing[0].slice(1), before.timing[0].slice(1), "untouched running seconds preservation");
  assertEqual(after.timing[2].slice(1), ["2026-08-20 09:10:43", "2026-08-20 10:00:00", "pause"], "running closed-open interval");
  assertEqual(after.timing[3].slice(1), ["2026-08-20 10:50:00", null, null], "running new open interval");
  passed("running Save, Add Interval, Delete/Undo, blank stop, mask, seconds, and end reasons");
}


async function verifyPausedOrdinarySave(page) {
  await parkAndReset(page);
  const cardId = await navigate(page, "paused");
  const before = cardSnapshot(cardId);
  const editor = await openTimingEditor(page);
  await fillTimingField(page, 0, "start_time", "1031");
  await editor.locator("[data-timing-add-interval]").click();
  const addedIndex = (await page.locator("[data-timing-interval-list] .interval-row").count()) - 1;
  await fillTimingField(page, addedIndex, "start_date", "2026-08-20");
  await fillTimingField(page, addedIndex, "start_time", "1230");
  await fillTimingField(page, addedIndex, "stop_date", "2026-08-20");
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
  await editor.locator("[data-timing-add-interval]").click();
  let addedIndex = (await page.locator("[data-timing-interval-list] .interval-row").count()) - 1;
  await fillTimingField(page, addedIndex, "start_date", "2026-08-20");
  const incomplete = await fillTimingField(page, addedIndex, "start_time", "13");
  await fillTimingField(page, addedIndex, "stop_date", "2026-08-20");
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
  cardId = await navigate(page, "paused");
  before = cardSnapshot(cardId);
  editor = await openTimingEditor(page);
  await fillTimingField(page, 0, "start_date", "2099-01-01");
  await fillTimingField(page, 0, "stop_date", "2099-01-01");
  await submitServerInvalidEditor(page, editor);
  const futureInput = timingRow(page, 0).locator('[aria-invalid="true"]').first();
  assertEqual(await futureInput.getAttribute("aria-invalid"), "true", "future field aria state");
  assert(
    await futureInput.evaluate((input) => document.activeElement === input),
    "Future rejection did not focus the first invalid field.",
  );
  assert(
    normalized(await page.locator("[data-timing-dialog]").textContent()).includes("бъдещето"),
    "Future timestamp rejection is missing.",
  );
  assertEqual(cardSnapshot(cardId), before, "future draft database snapshot");
  passed("incomplete, impossible-time, and future validation with first-field focus");
}


async function verifyManyRowsAnd1366Screenshot(page) {
  await parkAndReset(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  await navigate(page, "many_rows");
  const editor = await openTimingEditor(page);
  assertEqual(await page.locator("[data-timing-interval-list] .interval-row").count(), 18, "many-row interval count");
  const list = page.locator("[data-timing-interval-list]");
  const scrollState = await list.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }));
  assert(scrollState.scrollHeight > scrollState.clientHeight, "Many-row interval body does not scroll internally.");
  const before = await page.locator("[data-timing-dialog] header, [data-timing-totals], [data-timing-dialog] footer").evaluateAll(
    (elements) => elements.map((element) => element.getBoundingClientRect().y),
  );
  await list.evaluate((element) => { element.scrollTop = element.scrollHeight; });
  const after = await page.locator("[data-timing-dialog] header, [data-timing-totals], [data-timing-dialog] footer").evaluateAll(
    (elements) => elements.map((element) => element.getBoundingClientRect().y),
  );
  assertEqual(after, before, "fixed timing chrome after internal scrolling");
  const dialogBox = await page.locator("[data-timing-dialog]").boundingBox();
  assert(dialogBox !== null && dialogBox.height <= 728.5, "Timing dialog exceeds accepted 728px working height.");
  await atomicScreenshot(page, screenshot1366);
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
  await finishOverlay.locator("[data-finish-review-edit]").click();
  const editor = page.locator("[data-timing-editor-overlay]");
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
    "20.08.2026 12:15",
    "paused proposed stop uses latest closed interval",
  );
  await atomicScreenshot(page, screenshot1920);
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
  mutateCardVersion(cardId);
  await page.locator("#terminal-refresh-alert").waitFor({ state: "visible", timeout: 15000 });
  await editor.locator("[data-timing-reload]").waitFor({ state: "visible", timeout: 15000 });
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
  passed("live stale takeover retains and locks draft with reload-or-Cancel response");
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
    await verifyRunningOrdinarySave(page);
    await verifyPausedOrdinarySave(page);
    await verifyValidationFailures(page);
    await verifyManyRowsAnd1366Screenshot(page);
    await verifyRunningFinishReview(page);
    await verifyPausedFinishAnd1920Screenshot(page);
    await verifyCompletedWaitingAbsenceAndLegacyFinish(page);
    await verifyStaleTakeover(page);

    assertEqual(summary.consoleErrors, [], "error-level browser console messages");
    assertEqual(summary.pageErrors, [], "browser page errors");
    assertEqual(summary.failedRequests, [], "failed browser requests");
    summary.status = "passed";
    atomicWriteArtifact(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
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
    if (summaryPath) atomicWriteArtifact(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
  } catch {
    // Preserve the original guard or verification failure.
  }
  console.error(error.stack || error);
  process.exitCode = 1;
});
