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
  return Boolean(relative)
    && relative !== ".."
    && !relative.startsWith(`..${path.sep}`)
    && !path.isAbsolute(relative);
}


function isAtOrBelow(parent, candidate) {
  return candidate === parent || isStrictChild(parent, candidate);
}


function assertNoSymlinkComponents(base, candidate, message) {
  const relative = path.relative(base, candidate);
  assert(
    relative === ""
      || (
        relative !== ".."
        && !relative.startsWith(`..${path.sep}`)
        && !path.isAbsolute(relative)
      ),
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


function lstatIfPresent(filePath) {
  try {
    return fs.lstatSync(filePath);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}


function assertSingleLink(filePath, message) {
  const linkStat = lstatIfPresent(filePath);
  if (linkStat) {
    assert(!linkStat.isSymbolicLink(), message);
    assert(linkStat.nlink === 1, message);
  }
}


const baseURL = requiredEnvironment("BASE_URL").replace(/\/+$/, "");
const baseOrigin = new URL(baseURL).origin;
const fixtureInput = requiredEnvironment("FIXTURE_JSON");
const artifactInput = requiredEnvironment("ARTIFACT_DIR");
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = fs.realpathSync(path.resolve(scriptDir, ".."));
const runtimeRoot = path.resolve(
  repoRoot,
  ".test-runtime",
  "terminal-timing-correction",
);
const artifactRoot = path.resolve(
  repoRoot,
  "artifacts",
  "ui-checks",
  "terminal-timing-correction",
);
const requestedFixturePath = path.resolve(repoRoot, fixtureInput);
const requestedArtifactDir = path.resolve(repoRoot, artifactInput);

assertNoSymlinkComponents(
  repoRoot,
  runtimeRoot,
  ".test-runtime/terminal-timing-correction guard root must not be a symlink.",
);
assert(
  isStrictChild(runtimeRoot, requestedFixturePath),
  "FIXTURE_JSON must be under .test-runtime/terminal-timing-correction.",
);
assert(
  isAtOrBelow(artifactRoot, requestedArtifactDir),
  "ARTIFACT_DIR must be at or below artifacts/ui-checks/terminal-timing-correction.",
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
  "FIXTURE_JSON must resolve below .test-runtime/terminal-timing-correction.",
);
assert(fs.statSync(fixturePath).isFile(), "FIXTURE_JSON must resolve to a regular file.");
assertSingleLink(fixturePath, "FIXTURE_JSON must not be hard-linked.");

let fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const databaseInput = path.resolve(repoRoot, fixture.db_path);
assert(fs.existsSync(databaseInput), `Fixture database does not exist: ${databaseInput}`);
const databasePath = fs.realpathSync(databaseInput);
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), databasePath),
  "Fixture database must resolve below .test-runtime/terminal-timing-correction.",
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
  assert(
    !lstatIfPresent(target),
    "Artifact target already exists in the dedicated run directory.",
  );
  return target;
}


function openFreshArtifactTemp(target) {
  const extension = path.extname(target);
  const temporaryPath = path.resolve(
    path.dirname(target),
    `.${path.basename(target)}.${process.pid}.${randomUUID()}.tmp${extension}`,
  );
  assert(isStrictChild(artifactDir, temporaryPath), "Temporary artifact escaped ARTIFACT_DIR.");
  const noFollow = fs.constants.O_NOFOLLOW;
  assert(typeof noFollow === "number", "This verifier requires O_NOFOLLOW support.");
  const descriptor = fs.openSync(
    temporaryPath,
    fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | noFollow,
    0o600,
  );
  const descriptorStat = fs.fstatSync(descriptor);
  assert(descriptorStat.isFile(), "Temporary artifact descriptor must be a regular file.");
  assert(descriptorStat.nlink === 1, "Temporary artifact descriptor must have one link.");
  return { temporaryPath, descriptor, descriptorStat };
}


function sameInode(actual, expected) {
  return actual.dev === expected.dev && actual.ino === expected.ino;
}


function writeAll(descriptor, contents) {
  let offset = 0;
  while (offset < contents.length) {
    offset += fs.writeSync(descriptor, contents, offset, contents.length - offset);
  }
}


function cleanupOwnedTemporary(temporaryPath, descriptorStat) {
  if (!temporaryPath || !descriptorStat) return;
  const entryStat = lstatIfPresent(temporaryPath);
  if (
    entryStat
    && !entryStat.isSymbolicLink()
    && sameInode(entryStat, descriptorStat)
  ) {
    fs.unlinkSync(temporaryPath);
  }
}


function atomicWriteArtifactBuffer(target, contents) {
  const relativeTarget = path.relative(artifactDir, target);
  const finalPath = guardedArtifactPath(relativeTarget);
  const buffer = Buffer.isBuffer(contents) ? contents : Buffer.from(contents);
  let temporaryPath;
  let descriptor;
  let descriptorStat;
  try {
    ({ temporaryPath, descriptor, descriptorStat } = openFreshArtifactTemp(finalPath));
    writeAll(descriptor, buffer);
    const afterWrite = fs.fstatSync(descriptor);
    assert(sameInode(afterWrite, descriptorStat), "Temporary artifact descriptor changed while writing.");
    assert(afterWrite.nlink === 1, "Temporary artifact was hard-linked while writing.");
    fs.fsyncSync(descriptor);
    const afterSync = fs.fstatSync(descriptor);
    assert(sameInode(afterSync, descriptorStat), "Temporary artifact descriptor changed after sync.");
    assert(afterSync.nlink === 1, "Temporary artifact was hard-linked after sync.");
    const entryStat = fs.lstatSync(temporaryPath);
    assert(!entryStat.isSymbolicLink(), "Temporary artifact entry became a symlink.");
    assert(sameInode(entryStat, descriptorStat), "Temporary artifact entry was substituted.");
    assert(entryStat.nlink === 1, "Temporary artifact entry must have one link.");
    const validatedFinalPath = guardedArtifactPath(relativeTarget);
    fs.renameSync(temporaryPath, validatedFinalPath);
    temporaryPath = null;
    const publishedStat = fs.lstatSync(validatedFinalPath);
    assert(!publishedStat.isSymbolicLink(), "Published artifact became a symlink.");
    assert(sameInode(publishedStat, descriptorStat), "Published artifact inode is not the written inode.");
    const publishedDescriptorStat = fs.fstatSync(descriptor);
    assert(sameInode(publishedDescriptorStat, descriptorStat), "Published descriptor inode changed.");
    assert(publishedDescriptorStat.nlink === 1, "Published artifact must have one link.");
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    cleanupOwnedTemporary(temporaryPath, descriptorStat);
  }
}


async function atomicScreenshot(page, target) {
  const screenshotBuffer = await page.screenshot({ fullPage: false, type: "png" });
  atomicWriteArtifactBuffer(target, screenshotBuffer);
}


function atomicWriteArtifact(target, contents) {
  atomicWriteArtifactBuffer(target, Buffer.from(contents, "utf8"));
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
  requestQuiescenceWindowMs: 300,
  routeGateTimeouts: [],
  routeGateCleanupErrors: [],
  expectedHttpResponses: [],
  unexpectedHttpResponses: [],
  expectedConsoleErrors: [],
  consoleErrors: [],
  pageErrors: [],
  failedRequests: [],
  abortedPreviewRequests: [],
  unmatchedAbortedPreviewRequests: [],
};


function passed(label) {
  summary.assertions.push(label);
}


function isPreviewRequest(request) {
  if (request.method() !== "POST") return false;
  const pathname = new URL(request.url()).pathname;
  return pathname.endsWith("/timing-ledger/preview")
    || pathname.endsWith("/finish-review/preview");
}


function isExpectedHttpFailure(record) {
  if (
    record.method === "POST"
    && record.status === 422
    && record.pathname.endsWith("/timing-ledger/preview")
    && record.phase === "validation-failures"
  ) return true;
  if (
    record.method === "POST"
    && record.status === 409
    && record.pathname.endsWith("/timing-ledger/preview")
    && record.phase === "stale-takeover"
  ) return true;
  return false;
}


function correlateAbortedPreviews() {
  for (const aborted of summary.abortedPreviewRequests) {
    const superseding = [...previewRequestStates.values()].find(
      (candidate) => candidate.sequence > aborted.sequence
        && candidate.pathname === aborted.pathname
        && candidate.phase === aborted.phase,
    );
    if (superseding) {
      aborted.correlation = `superseded by preview request ${superseding.sequence}`;
    } else if (aborted.expectedAbortReason) {
      aborted.correlation = aborted.expectedAbortReason;
    } else {
      const allowance = explicitPreviewAbortAllowances.find(
        (candidate) => !candidate.used
          && candidate.phase === aborted.phase
          && candidate.pathname === aborted.pathname,
      );
      if (allowance) {
        allowance.used = true;
        aborted.correlation = allowance.reason;
      } else {
        summary.unmatchedAbortedPreviewRequests.push(aborted);
      }
    }
  }
}


async function runPhase(label, callback) {
  currentPhase = label;
  try {
    await callback();
  } finally {
    currentPhase = `${label}:cleanup`;
  }
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

assertNoSymlinkComponents(
  repoRoot,
  requestedArtifactDir,
  "ARTIFACT_DIR guard path must not contain symlinks.",
);
assert(
  fs.existsSync(requestedArtifactDir) && fs.lstatSync(requestedArtifactDir).isDirectory(),
  "ARTIFACT_DIR must be a pre-created, empty, dedicated run directory.",
);
artifactDir = fs.realpathSync(requestedArtifactDir);
assert(
  isAtOrBelow(fs.realpathSync(artifactRoot), artifactDir),
  "ARTIFACT_DIR resolves outside artifacts/ui-checks/terminal-timing-correction.",
);
assert(
  fs.readdirSync(artifactDir).length === 0,
  "ARTIFACT_DIR must be an empty, dedicated run directory.",
);
const ownershipMarkerPath = path.join(
  artifactDir,
  ".terminal-timing-correction-owner.json",
);
atomicWriteArtifact(
  ownershipMarkerPath,
  `${JSON.stringify({ verifier: "terminal-timing-correction-v1" })}\n`,
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
const REQUEST_QUIESCENCE_WINDOW_MS = 300;
const REQUEST_TIMEOUT_MS = 15000;
const ROUTE_GATE_TIMEOUT_MS = 5000;

let currentPhase = "setup";
let requestActivityVersion = 0;
let previewSequence = 0;
const requestPhases = new WeakMap();
const previewRequestStates = new Map();
const explicitPreviewAbortAllowances = [];
const recentPostActivity = [];


function recordPostActivity(event, request) {
  if (request.method() !== "POST") return;
  recentPostActivity.push({
    event,
    phase: requestPhases.get(request) || currentPhase,
    pathname: new URL(request.url()).pathname,
    at: Date.now(),
  });
  if (recentPostActivity.length > 20) recentPostActivity.shift();
}


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


async function withTimeout(promise, milliseconds, label) {
  let timeout;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timeout = setTimeout(
          () => reject(new Error(`${label} timed out after ${milliseconds} ms.`)),
          milliseconds,
        );
      }),
    ]);
  } finally {
    clearTimeout(timeout);
  }
}


async function waitForRequestQuiescence(page, label) {
  const deadline = Date.now() + REQUEST_TIMEOUT_MS;
  let observedVersion = requestActivityVersion;
  let stableSince = Date.now();
  while (Date.now() < deadline) {
    await page.waitForTimeout(25);
    if (requestActivityVersion !== observedVersion) {
      observedVersion = requestActivityVersion;
      stableSince = Date.now();
    }
    if (Date.now() - stableSince >= REQUEST_QUIESCENCE_WINDOW_MS) return;
  }
  throw new Error(
    `${label} did not reach request quiescence within ${REQUEST_TIMEOUT_MS} ms; `
      + `recent POST activity: ${JSON.stringify(recentPostActivity)}.`,
  );
}


async function waitForPreviewSettlement(page, label) {
  const deadline = Date.now() + REQUEST_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const pending = [...previewRequestStates.values()].filter((state) => !state.outcome);
    if (pending.length === 0) {
      await waitForRequestQuiescence(page, label);
      if ([...previewRequestStates.values()].every((state) => state.outcome)) return;
    }
    await page.waitForTimeout(25);
  }
  throw new Error(`${label} did not settle previews within ${REQUEST_TIMEOUT_MS} ms.`);
}


function markOutstandingPreviewAbortsExpected(reason) {
  for (const state of previewRequestStates.values()) {
    if (!state.outcome) state.expectedAbortReason = reason;
  }
}


function allowOneExplicitPreviewAbort({ phase, pathname, reason }) {
  explicitPreviewAbortAllowances.push({ phase, pathname, reason, used: false });
}


function createRouteGate(label) {
  let releaseGate;
  let markEntered;
  let released = false;
  let entered = false;
  let requestCount = 0;
  const releasePromise = new Promise((resolve) => { releaseGate = resolve; });
  const enteredPromise = new Promise((resolve) => { markEntered = resolve; });
  const handler = async (route) => {
    requestCount += 1;
    if (!entered) {
      entered = true;
      markEntered();
    }
    try {
      try {
        await withTimeout(
          releasePromise,
          ROUTE_GATE_TIMEOUT_MS,
          `${label} release`,
        );
      } catch (error) {
        summary.routeGateTimeouts.push({
          label,
          error: error?.message || String(error),
        });
      }
    } finally {
      try {
        await route.continue();
      } catch (error) {
        summary.routeGateCleanupErrors.push({
          label,
          error: error?.message || String(error),
        });
      }
    }
  };
  return {
    handler,
    entered: enteredPromise,
    release() {
      if (!released) {
        released = true;
        releaseGate();
      }
    },
    count() {
      return requestCount;
    },
  };
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
  await waitForRequestQuiescence(page, `${currentPhase}: before fixture reset`);
  markOutstandingPreviewAbortsExpected(`${currentPhase}: explicit page reset`);
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
  await waitForPreviewSettlement(page, "focus boundary preview settlement");
  await page.keyboard.press("Tab");
  await assertFocusInside(page, "[data-timing-dialog]", "forward boundary focus wrap");
  assert(
    await page.locator("[data-timing-dialog]").evaluate(
      () => document.activeElement?.getAttribute("data-timing-field") === "start_date",
    ),
    "Forward boundary did not wrap to the first timing date field.",
  );
  await page.keyboard.press("Shift+Tab");
  await assertFocusInside(page, "[data-timing-dialog]", "reverse boundary focus wrap");
  assert(
    await editor.locator("[data-timing-save]").evaluate(
      (button) => document.activeElement === button,
    ),
    "Reverse boundary did not wrap to Save.",
  );
  await waitForPreviewSettlement(page, "reverse focus boundary preview settlement");
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
  await waitForPreviewSettlement(
    page,
    "validation-failures: invalid preview before form navigation",
  );
  const saveAction = await editor.locator("[data-timing-save-form]").getAttribute("action");
  assert(saveAction, "Validation timing form action is missing.");
  allowOneExplicitPreviewAbort({
    phase: "validation-failures",
    pathname: `${saveAction}/preview`,
    reason: "validation-failures: one blur preview may be aborted by invalid-form navigation",
  });
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
  const validationPath = `/terminal/cards/${cardId}/timing-ledger/preview`;
  const observedValidation = page.waitForResponse(
    (response) => response.request().method() === "POST"
      && new URL(response.url()).pathname === validationPath
      && response.status() === 422,
    { timeout: REQUEST_TIMEOUT_MS },
  );
  const explicitValidation = await page.evaluate(async ({ endpoint }) => {
    const form = document.querySelector("[data-timing-save-form]");
    const body = new FormData();
    body.set("loaded_version", form.querySelector("input[name='loaded_version']").value);
    body.set("timing_draft", "{invalid-json");
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Accept": "application/json" },
      body,
    });
    return { status: response.status, payload: await response.json() };
  }, { endpoint: validationPath });
  const validationResponse = await observedValidation;
  assertEqual(validationResponse.status(), 422, "explicit validation HTTP status");
  assertEqual(explicitValidation.status, 422, "explicit validation fetch status");
  assertEqual(explicitValidation.payload.ok, false, "explicit validation payload status");
  assertEqual(cardSnapshot(cardId), before, "explicit validation database snapshot");
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


async function beginFinishReview(page, cardId) {
  const responsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST"
      && new URL(response.url()).pathname === `/terminal/cards/${cardId}/finish-review`,
    { timeout: REQUEST_TIMEOUT_MS },
  );
  const button = page.locator(`form[action="/terminal/cards/${cardId}/finish"] button[type="submit"]`);
  await button.click();
  const response = await responsePromise;
  const payload = await response.json();
  await page.locator("[data-finish-review-overlay]").waitFor({ state: "visible" });
  return payload;
}


async function beginDoubleSubmittedFinishReview(page, cardId) {
  const finishReviewPattern = `**/terminal/cards/${cardId}/finish-review`;
  const gate = createRouteGate("finish-review double-submit gate");
  await page.route(finishReviewPattern, gate.handler);
  try {
    const responsePromise = page.waitForResponse(
      (response) => response.request().method() === "POST"
        && new URL(response.url()).pathname === `/terminal/cards/${cardId}/finish-review`,
      { timeout: REQUEST_TIMEOUT_MS },
    );
    const button = page.locator(`form[action="/terminal/cards/${cardId}/finish"] button[type="submit"]`);
    await button.evaluate((element) => {
      element.click();
      element.click();
    });
    await withTimeout(
      gate.entered,
      REQUEST_TIMEOUT_MS,
      "finish-review double-submit first request",
    );
    await waitForRequestQuiescence(page, "finish-review double-submit while gated");
    gate.release();
    const response = await responsePromise;
    const payload = await response.json();
    await page.locator("[data-finish-review-overlay]").waitFor({ state: "visible" });
    await waitForRequestQuiescence(page, "finish-review double-submit after response");
    return { payload, requestCount: gate.count() };
  } finally {
    gate.release();
    await page.unroute(finishReviewPattern, gate.handler);
  }
}


async function applyFinishEditor(page) {
  const responsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST"
      && new URL(response.url()).pathname.endsWith("/finish-review/preview"),
    { timeout: REQUEST_TIMEOUT_MS },
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

  const doubleReview = await beginDoubleSubmittedFinishReview(page, cardId);
  let payload = doubleReview.payload;
  assert(payload.ok, "Running finish review did not return an accepted preview.");
  assertEqual(
    doubleReview.requestCount,
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

  const finishPattern = `**/terminal/cards/${cardId}/finish`;
  const finishGate = createRouteGate("Confirm Finish double-submit gate");
  await page.route(finishPattern, finishGate.handler);
  try {
    const navigation = page.waitForURL(
      (url) => url.pathname === `/terminal/cards/${cardId}`
        && url.searchParams.get("notice") === "card_finished",
      { waitUntil: "networkidle", timeout: REQUEST_TIMEOUT_MS },
    );
    await finishOverlay.locator("[data-finish-review-confirm]").evaluate((button) => {
      button.click();
      button.click();
    });
    await withTimeout(
      finishGate.entered,
      REQUEST_TIMEOUT_MS,
      "Confirm Finish double-submit first request",
    );
    await waitForRequestQuiescence(page, "Confirm Finish double-submit while gated");
    finishGate.release();
    await navigation;
    await waitForRequestQuiescence(page, "Confirm Finish after navigation");
  } finally {
    finishGate.release();
    await page.unroute(finishPattern, finishGate.handler);
  }
  const finishRequestCount = finishGate.count();
  assertEqual(finishRequestCount, 1, "double-click Confirm Finish request count");

  const after = cardSnapshot(cardId);
  assertEqual(after.card.status, "completed", "running Confirm Finish status");
  assertEqual(after.card.version, before.card.version + 1, "running Confirm Finish version increment");
  assertEqual(after.card.finished_at, payload.preview.reviewed_at_utc, "frozen finish persisted instant");
  assertEqual(after.timing[0][1], "2026-08-20 07:02:00", "finish-review edited minute precision");
  assertEqual(after.timing.at(-1)[2], payload.preview.reviewed_at_utc, "running final interval frozen closure");
  summary.requestCounts.finishReviewDoubleClick = doubleReview.requestCount;
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
  allowOneExplicitPreviewAbort({
    phase: "stale-takeover",
    pathname: `/terminal/cards/${cardId}/timing-ledger/preview`,
    reason: "stale-takeover: one draft preview may be aborted by the explicit stale lock",
  });
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
  markOutstandingPreviewAbortsExpected(
    "stale-takeover: explicit locked-editor cancellation",
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
      if (message.type() !== "error") return;
      const record = { phase: currentPhase, text: message.text() };
      if (
        currentPhase === "validation-failures"
        && record.text === (
          "Failed to load resource: the server responded with a status of 422 "
          + "(Unprocessable Entity)"
        )
      ) {
        summary.expectedConsoleErrors.push(record);
      } else {
        summary.consoleErrors.push(record);
      }
    });
    page.on("request", (request) => {
      if (request.method() === "POST") requestActivityVersion += 1;
      requestPhases.set(request, currentPhase);
      recordPostActivity("request", request);
      assertEqual(new URL(request.url()).origin, baseOrigin, "browser request origin");
      if (isPreviewRequest(request)) {
        previewSequence += 1;
        previewRequestStates.set(request, {
          sequence: previewSequence,
          phase: currentPhase,
          method: request.method(),
          url: request.url(),
          pathname: new URL(request.url()).pathname,
          outcome: null,
          expectedAbortReason: null,
        });
      }
    });
    page.on("requestfinished", (request) => {
      if (request.method() === "POST") requestActivityVersion += 1;
      recordPostActivity("finished", request);
      const state = previewRequestStates.get(request);
      if (state && !state.outcome) state.outcome = "finished";
    });
    page.on("response", (response) => {
      const request = response.request();
      const status = response.status();
      const state = previewRequestStates.get(request);
      if (state) state.status = status;
      if (status < 400) return;
      const record = {
        phase: requestPhases.get(request) || "unknown",
        method: request.method(),
        pathname: new URL(response.url()).pathname,
        status,
      };
      if (isExpectedHttpFailure(record)) {
        summary.expectedHttpResponses.push(record);
      } else {
        summary.unexpectedHttpResponses.push(record);
      }
    });
    page.on("requestfailed", (request) => {
      if (request.method() === "POST") requestActivityVersion += 1;
      recordPostActivity("failed", request);
      const previewState = previewRequestStates.get(request);
      if (previewState) previewState.outcome = "failed";
      const failure = {
        phase: requestPhases.get(request) || "unknown",
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
        summary.abortedPreviewRequests.push({
          ...failure,
          pathname,
          sequence: previewState?.sequence ?? -1,
          expectedAbortReason: previewState?.expectedAbortReason || null,
          correlation: null,
        });
        return;
      }
      summary.failedRequests.push(failure);
    });

    await runPhase("lifecycle-and-icon", () => verifyLifecycleAndIcon(page));
    await runPhase("cancel-focus-and-trap", () => verifyCancelFocusEscapeAndTrap(page));
    await runPhase("running-ordinary-save", () => verifyRunningOrdinarySave(page));
    await runPhase("paused-ordinary-save", () => verifyPausedOrdinarySave(page));
    await runPhase("validation-failures", () => verifyValidationFailures(page));
    await runPhase("many-row-layout", () => verifyManyRowsAnd1366Screenshot(page));
    await runPhase("running-finish-review", () => verifyRunningFinishReview(page));
    await runPhase("paused-finish-review", () => verifyPausedFinishAnd1920Screenshot(page));
    await runPhase("completed-waiting-legacy", () => verifyCompletedWaitingAbsenceAndLegacyFinish(page));
    await runPhase("stale-takeover", () => verifyStaleTakeover(page));

    await waitForRequestQuiescence(page, "final verifier request accounting");
    correlateAbortedPreviews();

    assertEqual(summary.consoleErrors, [], "error-level browser console messages");
    assertEqual(summary.pageErrors, [], "browser page errors");
    assertEqual(summary.failedRequests, [], "failed browser requests");
    assertEqual(summary.routeGateTimeouts, [], "route gate timeouts");
    assertEqual(summary.routeGateCleanupErrors, [], "route gate cleanup errors");
    assertEqual(summary.unexpectedHttpResponses, [], "unexpected HTTP >=400 responses");
    assertEqual(
      summary.unmatchedAbortedPreviewRequests,
      [],
      "unmatched aborted preview requests",
    );
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
