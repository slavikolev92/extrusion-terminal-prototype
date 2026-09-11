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


function multipartField(postData, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return postData.match(new RegExp(`name="${escaped}"\\r?\\n\\r?\\n([^\\r\\n]*)`))?.[1] ?? "";
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
const REQUIRED_SCENARIOS = [
  "empty",
  "all_unassigned",
  "no_weights",
  "partial_weights",
  "complete_weights",
  "mixed_unassigned",
  "awaiting_partial",
  "completed_complete",
  "archived_complete",
  "many_pallets",
];

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
const pendingConsoleErrors = [];
const pendingFailedRequestExpectations = [];
const pendingResponseErrorExpectations = [];
const pendingDialogExpectations = [];


function expectConsoleError(label, pattern) {
  pendingConsoleErrors.push({ label, pattern });
}


function expectFailedRequest(label, {
  method,
  pathname,
  errorPattern,
  origin = baseOrigin,
}) {
  pendingFailedRequestExpectations.push({
    label,
    method,
    pathname,
    errorPattern,
    origin,
  });
}


function expectResponseError(label, {
  method,
  pathname,
  status,
  origin = baseOrigin,
}) {
  pendingResponseErrorExpectations.push({ label, method, pathname, status, origin });
}


function expectDialog(label, {
  type,
  response,
  origin = baseOrigin,
}) {
  pendingDialogExpectations.push({ label, type, response, origin });
}


function consumeExpectedNetworkEvent(queue, item, fields, patternField = null) {
  const expected = queue[0];
  if (!expected) return null;
  const exact = fields.every((field) => expected[field] === item[field]);
  const patternMatches = patternField === null
    || expected[patternField].test(item[patternField.replace("Pattern", "")]);
  if (!exact || !patternMatches) return null;
  queue.shift();
  return expected;
}


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


async function atomicScreenshot(page, target, options) {
  const relativeTarget = path.relative(artifactDir, target);
  const finalPath = guardedArtifactPath(relativeTarget);
  let temporaryPath = freshArtifactTempPath(finalPath);
  try {
    await page.screenshot({ ...options, path: temporaryPath });
    assertSingleLink(temporaryPath, "Temporary screenshot must not be hard-linked.");
    const validatedFinalPath = guardedArtifactPath(relativeTarget);
    fs.renameSync(temporaryPath, validatedFinalPath);
    temporaryPath = null;
  } finally {
    if (temporaryPath && fs.existsSync(temporaryPath)) fs.unlinkSync(temporaryPath);
  }
}


const VIEWPORTS = [
  { name: "desktop-1440", width: 1440, height: 900 },
  { name: "desktop-1366", width: 1366, height: 768 },
  { name: "short-1093", width: 1093, height: 614 },
];
const SCREENSHOT_NAMES = [
  "no-weights-open.png",
  "empty-open.png",
  "many-pallets-scrolled.png",
  "autosave-complete.png",
  "admin-archived.png",
  "finish-blocked.png",
  "finish-review.png",
  "fatal-recovery.png",
  "admin-modal.png",
];


const summary = {
  status: "running",
  url: baseURL,
  databaseIdentity: databasePath,
  fixture: path.relative(repoRoot, fixturePath),
  assertions: [],
  viewports: [],
  screenshots: [],
  consoleErrors: [],
  expectedConsoleErrors: [],
  pageErrors: [],
  failedRequests: [],
  expectedFailedRequests: [],
  expectedResponseErrors: [],
  unexpectedResponseErrors: [],
  unexpectedDialogs: [],
  expectedDialogs: [],
  staleSimulations: [],
  queueIdleReconciliations: [],
  mutationAudits: [],
  interactionGroups: [],
  postRequests: [],
  network: {
    allowedOrigin: baseOrigin,
    allowedPeriodicRequest: { method: "GET", pathname: "/terminal/snapshot" },
    observedOrigins: [],
  },
};
const PALLET_SUMMARY_ERROR_MESSAGE =
  "Обобщението по палети не може да бъде показано. Проверете данните за ролките.";


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
  passed("health database identity matched guarded fixture");
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
for (const viewport of VIEWPORTS) {
  for (const screenshotName of SCREENSHOT_NAMES) {
    guardedArtifactPath(viewport.name, screenshotName);
  }
}
assertEqual(fixture.scenario_order, REQUIRED_SCENARIOS, "fixture scenario order");

const require = createRequire(import.meta.url);
const localNodeModules = fs.realpathSync(path.join(repoRoot, "node_modules"));
const resolvedPlaywright = fs.realpathSync(require.resolve("@playwright/test"));
assert(
  isStrictChild(localNodeModules, resolvedPlaywright),
  "Playwright must resolve from the repository-local node_modules directory.",
);
const { chromium } = require("@playwright/test");


function runPython(program, programArguments, label) {
  const result = spawnSync(
    path.join(repoRoot, ".venv", "bin", "python"),
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
  assert(result.status === 0, `${label}: ${normalized(result.stderr)}`);
  return result.stdout.trim();
}


function runMutationAudit(expectedSaves = []) {
  const auditor = path.join(repoRoot, "scripts", "audit_terminal_pallet_summary_db.py");
  const args = [auditor, "--db-path", databasePath, "--fixture-json", fixturePath];
  for (const expected of expectedSaves) args.push("--expect-save", expected);
  const result = spawnSync(path.join(repoRoot, ".venv", "bin", "python"), args, {
    cwd: repoRoot,
    encoding: "utf8",
  });
  let payload;
  try {
    payload = JSON.parse(result.stdout);
  } catch {
    throw new Error(`mutation audit did not return JSON: ${normalized(result.stderr)}`);
  }
  assert(result.status === 0, `mutation audit failed: ${JSON.stringify(payload)}`);
  assertEqual(payload.mutation_audit, "passed", "mutation audit result");
  assertEqual(payload.expected_saves, expectedSaves.length, "mutation audit save count");
  assertEqual(payload.unexpected_mutations, 0, "mutation audit unrelated changes");
  assertEqual(payload.hash_algorithm, "sha256", "mutation audit hash algorithm");
  assert(payload.pre_hashes && typeof payload.pre_hashes === "object", "mutation audit pre hashes missing");
  assert(payload.post_hashes && typeof payload.post_hashes === "object", "mutation audit post hashes missing");
  summary.mutationAudits.push({ expectedSaves, ...payload });
  return payload;
}


function resetFixtureDatabase() {
  const result = spawnSync(
    path.join(repoRoot, ".venv", "bin", "python"),
    [
      path.join(repoRoot, "scripts", "create_terminal_pallet_summary_fixture.py"),
      "--db-path",
      databasePath,
      "--output",
      fixturePath,
    ],
    { cwd: repoRoot, encoding: "utf8" },
  );
  assert(result.status === 0, `Could not reset guarded fixture: ${normalized(result.stderr)}`);
  const refreshed = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  assertEqual(refreshed.scenarios, fixture.scenarios, "fixture scenarios after reset");
  assertEqual(refreshed.active_shift, fixture.active_shift, "fixture shift after reset");
  assertEqual(
    fs.realpathSync(path.resolve(refreshed.db_path)),
    databasePath,
    "fixture database after reset",
  );
  fixture = refreshed;
  runMutationAudit();
}


async function parkBrowserAndResetFixture(page) {
  await preflightDatabase();
  const response = await page.goto(`${baseURL}/health`, { waitUntil: "networkidle" });
  assert(response?.ok(), `Browser health park returned HTTP ${response?.status()}.`);
  const health = await response.json();
  assertEqual(
    fs.realpathSync(path.resolve(health.database_path)),
    databasePath,
    "browser health database identity before reset",
  );
  resetFixtureDatabase();
  await preflightDatabase();
}


function databaseSnapshot() {
  const program = [
    "import json, sqlite3, sys",
    "connection = sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True)",
    "connection.execute('PRAGMA query_only = ON')",
    "cards = connection.execute('SELECT id, status, version, machine_id, machine_sequence, current_pallet_number FROM cards ORDER BY id').fetchall()",
    "rolls = connection.execute('SELECT id, card_id, roll_number, gross_weight, tare_weight, net_weight, pallet_number, shift_occurrence_id FROM roll_entries ORDER BY id').fetchall()",
    "timing = connection.execute('SELECT id, card_id, started_at, ended_at, end_reason FROM production_time_segments ORDER BY id').fetchall()",
    "counts = {'cards': len(cards), 'rolls': len(rolls), 'timing_rows': len(timing), 'pallet_assignments': sum(row[6] is not None for row in rolls)}",
    "print(json.dumps({'cards': cards, 'rolls': rolls, 'timing': timing, 'counts': counts}))",
  ].join("; ");
  return JSON.parse(runPython(program, [databasePath], "read-only database snapshot failed"));
}


function assertNoHorizontalOverflow(page, label) {
  return page.evaluate((assertionLabel) => {
    const root = document.documentElement;
    const body = document.body;
    const overflow = Math.max(root.scrollWidth, body?.scrollWidth || 0) - root.clientWidth;
    const clippedActions = Array.from(document.querySelectorAll(
      "button:not([hidden]), a[href]:not([hidden]), input:not([type='hidden']):not([hidden])",
    )).filter((element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      if (style.visibility === "hidden" || style.display === "none") return false;
      return rect.right > root.clientWidth + 1 || rect.left < -1;
    }).map((element) => element.outerHTML.slice(0, 120));
    return { assertionLabel, overflow, clippedActions };
  }, label).then((result) => {
    assert(result.overflow <= 1, `${label}: horizontal overflow ${result.overflow}px.`);
    assertEqual(result.clippedActions, [], `${label}: clipped actions`);
    return result;
  });
}


async function assertPalletBackgroundInert(page, label) {
  const overlay = page.locator("[data-pallet-summary-overlay]");
  const pageKind = await overlay.getAttribute("data-page-kind");
  const background = page.locator(
    pageKind === "admin"
      ? "main"
      : ".terminal-toast, .terminal-header, .machine-nav, .main",
  );
  assert(
    (await background.count()) >= (pageKind === "admin" ? 1 : 3),
    `${label}: rendered background targets are missing.`,
  );
  const state = await background.evaluateAll((elements) => elements.map((element) => ({
    inert: element.getAttribute("inert"),
    ariaHidden: element.getAttribute("aria-hidden"),
  })));
  assert(
    state.every(({ inert, ariaHidden }) => inert === "" && ariaHidden === "true"),
    `${label}: background is not inert and ARIA-hidden.`,
  );
}


async function assertSurfaceGeometry(page, {
  dialogSelector,
  headerSelector,
}, label) {
  await assertNoHorizontalOverflow(page, label);
  const geometry = await page.evaluate(({ dialogSelector: dialogQuery, headerSelector: headerQuery }) => {
    const dialog = document.querySelector(dialogQuery);
    if (!dialog) return null;
    const rect = dialog.getBoundingClientRect();
    const visibleActions = Array.from(dialog.querySelectorAll(
      "button:not([hidden]), a[href]:not([hidden]), input:not([type='hidden']):not([hidden])",
    )).filter((element) => {
      const style = getComputedStyle(element);
      return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
    });
    const clippedActions = visibleActions.filter((element) => {
      const action = element.getBoundingClientRect();
      const outsideHorizontalBounds = action.left < -1
        || action.right > window.innerWidth + 1
        || action.left < rect.left - 1
        || action.right > rect.right + 1;
      const insideScrollableTable = element.closest("[data-pallet-summary-scroll]") !== null;
      const outsideVerticalBounds = action.top < -1
        || action.bottom > window.innerHeight + 1
        || action.top < rect.top - 1
        || action.bottom > rect.bottom + 1;
      return outsideHorizontalBounds || (!insideScrollableTable && outsideVerticalBounds);
    }).map((element) => element.outerHTML.slice(0, 120));
    const headers = headerQuery
      ? Array.from(document.querySelectorAll(headerQuery)).filter((element) => element.getClientRects().length > 0)
      : [];
    const overflowingHeaders = headers.filter((element) => (
      element.scrollWidth > element.clientWidth + 1
      || element.scrollHeight > element.clientHeight + 1
    )).map((element) => element.textContent.replace(/\s+/g, " ").trim());
    const overlappingHeaders = headers.slice(0, -1).filter((element, index) => {
      const current = element.getBoundingClientRect();
      const next = headers[index + 1].getBoundingClientRect();
      return current.right > next.left + 1;
    }).map((element) => element.textContent.replace(/\s+/g, " ").trim());
    const overlappingFinishReviewRows = Array.from(
      dialog.querySelectorAll(".finish-review-row"),
    ).flatMap((row) => {
      const label = row.querySelector(":scope > dt");
      const value = row.querySelector(":scope > dd");
      if (
        !label
        || !value
        || label.getClientRects().length === 0
        || value.getClientRects().length === 0
      ) return [];
      const labelRange = document.createRange();
      labelRange.selectNodeContents(label);
      const valueRange = document.createRange();
      valueRange.selectNodeContents(value);
      const labelContent = labelRange.getBoundingClientRect();
      const valueContent = valueRange.getBoundingClientRect();
      const gap = valueContent.left - labelContent.right;
      if (gap >= 1) return [];
      return [{
        label: label.textContent.replace(/\s+/g, " ").trim(),
        value: value.textContent.replace(/\s+/g, " ").trim(),
        gap,
      }];
    });
    return {
      dialog: {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
      },
      contained: rect.left >= -1 && rect.top >= -1
        && rect.right <= window.innerWidth + 1 && rect.bottom <= window.innerHeight + 1,
      clippedActions,
      overflowingHeaders,
      overlappingHeaders,
      overlappingFinishReviewRows,
    };
  }, { dialogSelector, headerSelector });
  assert(geometry !== null, `${label}: dialog geometry is missing.`);
  assert(geometry.contained, `${label}: dialog escapes viewport ${JSON.stringify(geometry.dialog)}.`);
  assertEqual(geometry.clippedActions, [], `${label}: clipped actions`);
  assertEqual(geometry.overflowingHeaders, [], `${label}: overflowing headings`);
  assertEqual(geometry.overlappingHeaders, [], `${label}: overlapping headings`);
  assertEqual(
    geometry.overlappingFinishReviewRows,
    [],
    `${label}: overlapping finish-review label/value pairs`,
  );
  return geometry;
}


function assertFixtureBaseline(snapshot) {
  assertEqual(snapshot.counts, fixture.production_snapshot.counts, "fixture production counts");
  for (const [name, scenario] of Object.entries(fixture.scenarios)) {
    const card = snapshot.cards.find((row) => row[0] === scenario.card_id);
    assert(card, `${name}: card missing from production snapshot.`);
    assertEqual(card[2], fixture.production_snapshot.cards[name].version, `${name}: card version`);
    assertEqual(
      card[5],
      fixture.production_snapshot.cards[name].current_pallet_number,
      `${name}: current pallet`,
    );
  }
}


function mutateCardVersion(cardId) {
  const program = [
    "import sys",
    "from pathlib import Path",
    "from app import db",
    "database_path = Path(sys.argv[1]).resolve()",
    "db.DATA_DIR = database_path.parent",
    "db.DB_PATH = database_path",
    "card = db.fetch_terminal_card_detail(int(sys.argv[2]))",
    "assert card is not None",
    "result = db.update_current_pallet_number(int(sys.argv[2]), int(card['version']), '77')",
    "assert result.ok, result.messages",
  ].join("; ");
  runPython(program, [databasePath, String(cardId)], "legitimate stale-card update failed");
}


function mutateActiveShift(alternateNumber) {
  const program = [
    "import sys",
    "from pathlib import Path",
    "from app import db",
    "database_path = Path(sys.argv[1]).resolve()",
    "db.DATA_DIR = database_path.parent",
    "db.DB_PATH = database_path",
    "active_shift = db.fetch_active_shift()",
    "assert active_shift is not None",
    "result = db.update_active_shift_number(active_shift['id'], active_shift['version'], sys.argv[2])",
    "assert result.ok, result.messages",
  ].join("; ");
  runPython(
    program,
    [databasePath, String(alternateNumber)],
    "legitimate stale-shift update failed",
  );
}


function mutateQueueStructure(cardId) {
  const program = [
    "import sqlite3, sys",
    "connection = sqlite3.connect(sys.argv[1])",
    "connection.execute(\"UPDATE cards SET machine_sequence = machine_sequence + 10, version = version + 1, updated_at = '2026-09-10 08:00:00' WHERE id = ?\", (int(sys.argv[2]),))",
    "connection.commit()",
    "connection.close()",
  ].join("; ");
  runPython(program, [databasePath, String(cardId)], "queue structure mutation failed");
}


function mutateQueueMembership(cardId) {
  const program = [
    "import sqlite3, sys",
    "connection = sqlite3.connect(sys.argv[1])",
    "connection.execute(\"UPDATE cards SET status = 'cancelled', machine_id = NULL, machine_sequence = NULL, version = version + 1, updated_at = '2026-09-10 08:05:00' WHERE id = ?\", (int(sys.argv[2]),))",
    "connection.commit()",
    "connection.close()",
  ].join("; ");
  runPython(program, [databasePath, String(cardId)], "queue membership mutation failed");
}


function endActiveShift() {
  const program = [
    "import sys",
    "from pathlib import Path",
    "from app import db",
    "database_path = Path(sys.argv[1]).resolve()",
    "db.DATA_DIR = database_path.parent",
    "db.DB_PATH = database_path",
    "active = db.fetch_active_shift()",
    "assert active is not None",
    "result = db.end_shift(int(active['id']), int(active['version']))",
    "assert result.ok, result.messages",
  ].join("; ");
  runPython(program, [databasePath], "end active shift simulation failed");
}


function scenario(name) {
  const value = fixture.scenarios[name];
  assert(value, `Fixture scenario is missing: ${name}`);
  return value;
}


async function navigate(page, scenarioName) {
  const card = scenario(scenarioName);
  const response = await page.goto(`${baseURL}/terminal/cards/${card.card_id}`, {
    waitUntil: "networkidle",
  });
  assert(response?.ok(), `${scenarioName}: terminal page failed with HTTP ${response?.status()}.`);
  await page.locator("[data-pallet-summary-open]").waitFor({ state: "visible" });
}


async function modalRows(page) {
  return page.locator("[data-pallet-summary-dialog] tbody tr").evaluateAll((rows) =>
    rows.map((row) => Array.from(row.querySelectorAll("th, td"))
      .map((cell) => {
        const input = cell.querySelector("[data-pallet-weight-input]");
        return input ? input.value : cell.textContent.replace(/\s+/g, " ").trim();
      })),
  );
}


async function modalTotal(page) {
  return page.locator("[data-pallet-summary-total]").evaluate((row) =>
    Array.from(row.querySelectorAll("th, td"))
      .map((cell) => cell.textContent.replace(/\s+/g, " ").trim()),
  );
}


async function assertModalOpenState(page, expectedScenario) {
  const trigger = page.locator("[data-pallet-summary-open]");
  const overlay = page.locator("[data-pallet-summary-overlay]");
  const dialog = page.locator("[data-pallet-summary-dialog]");
  assert(await overlay.isVisible(), `${expectedScenario.order_number}: summary is not visible.`);
  assertEqual(await overlay.getAttribute("hidden"), null, "summary hidden=false");
  assertEqual(await overlay.getAttribute("aria-hidden"), "false", "summary aria-hidden=false");
  assertEqual(await trigger.getAttribute("aria-expanded"), "true", "summary aria-expanded=true");
  assertEqual(normalized(await dialog.locator("#pallet-summary-title").textContent()), "Обобщение по палети", "summary title");
  assertEqual(
    normalized(await dialog.locator("#pallet-summary-context").textContent()),
    `Браузърна проверка (№ ${expectedScenario.order_number})`,
    "summary order context",
  );
  const neutralStatusIconDisplay = await dialog.locator("[data-pallet-weight-status]").evaluate(
    (element) => element.hasAttribute("data-kind")
      ? null
      : getComputedStyle(element, "::before").display,
  );
  assertEqual(neutralStatusIconDisplay, "none", "neutral status decorative icon");
  const pageKind = await overlay.getAttribute("data-page-kind");
  const background = page.locator(
    pageKind === "admin"
      ? "main"
      : ".terminal-toast, .terminal-header, .machine-nav, .main",
  );
  assert(
    (await background.count()) >= (pageKind === "admin" ? 1 : 3),
    `Expected ${pageKind} background targets are missing.`,
  );
  const backgroundState = await background.evaluateAll((elements) => elements.map((element) => ({
    inert: element.getAttribute("inert"),
    ariaHidden: element.getAttribute("aria-hidden"),
  })));
  assert(
    backgroundState.every(({ inert, ariaHidden }) => inert === "" && ariaHidden === "true"),
    "Summary did not make every rendered background target inert and ARIA-hidden.",
  );
}


async function openSummary(page, expectedScenario) {
  await page.locator("[data-pallet-summary-open]").click();
  await assertModalOpenState(page, expectedScenario);
}


async function assertFocusOn(page, selector, label) {
  try {
    await page.waitForFunction(
      (targetSelector) => document.activeElement === document.querySelector(targetSelector),
      selector,
    );
  } catch {
    throw new Error(`${label}: expected element does not own focus.`);
  }
}


async function assertClosedAndFocused(page, label) {
  const overlay = page.locator("[data-pallet-summary-overlay]");
  assert(await overlay.isHidden(), `${label}: summary did not close.`);
  assertEqual(await overlay.getAttribute("aria-hidden"), "true", `${label}: aria-hidden`);
  assertEqual(
    await page.locator("[data-pallet-summary-open]").getAttribute("aria-expanded"),
    "false",
    `${label}: aria-expanded`,
  );
  await assertFocusOn(page, "[data-pallet-summary-open]", label);
}


async function clientOnly(page, state, label, action) {
  const url = page.url();
  const navigationCount = state.navigationCount;
  const requestIndex = state.requests.length;
  await action();
  assertEqual(page.url(), url, `${label}: URL`);
  assertEqual(state.navigationCount, navigationCount, `${label}: navigation count`);
  for (const request of state.requests.slice(requestIndex)) {
    const requestURL = new URL(request.url);
    assertEqual(requestURL.origin, baseOrigin, `${label}: unexpected request origin`);
    assert(
      !["POST", "PUT", "PATCH", "DELETE"].includes(request.method),
      `${label}: unexpected mutation-capable ${request.method} ${requestURL.pathname}.`,
    );
    assertEqual(request.method, "GET", `${label}: unexpected request method`);
    assert(
      !requestURL.pathname.includes("pallet-summary"),
      `${label}: unexpected pallet-summary request ${requestURL.pathname}.`,
    );
    assertEqual(requestURL.pathname, "/terminal/snapshot", `${label}: unexpected GET request`);
  }
}


async function verifyAllStatusTriggers(page) {
  for (const name of fixture.scenario_order) {
    if (!fixture.scenarios[name].editable.terminal) continue;
    await navigate(page, name);
    const trigger = page.locator("[data-pallet-summary-open]");
    assertEqual(await trigger.count(), 1, `${name}: one pallet trigger`);
    assert(await trigger.isEnabled(), `${name}: pallet trigger is disabled.`);
    assertEqual(normalized(await trigger.textContent()), "Палети", `${name}: trigger text`);
  }
  passed("all terminal-visible named statuses expose one enabled Палети button");
}


async function verifyRunningSummary(page, state, viewportDir) {
  await navigate(page, "no_weights");
  const expected = scenario("no_weights");

  await clientOnly(page, state, "running summary open", async () => openSummary(page, expected));
  const headings = await page.locator("[data-pallet-summary-dialog] thead th").allTextContents();
  assertEqual(
    headings.map(normalized),
    ["Палет №", "Брой ролки", "Бруто без палет, кг", "Тегло палет, кг", "Бруто с палет, кг", "Нето, кг"],
    "summary headings",
  );
  assertEqual(await modalRows(page), expected.expected_rows, "running mixed ordered rows");
  assertEqual(await modalTotal(page), expected.expected_total, "running mixed total");
  await atomicScreenshot(
    page,
    guardedArtifactPath(viewportDir, "no-weights-open.png"),
    { fullPage: true },
  );
  summary.screenshots.push(`${viewportDir}/no-weights-open.png`);
  await assertSurfaceGeometry(page, {
    dialogSelector: "[data-pallet-summary-dialog]",
    headerSelector: "[data-pallet-summary-dialog] thead th",
  }, `${viewportDir} pallet summary`);
  assertEqual(
    await page.locator("[data-pallet-weight-input]").count(),
    2,
    "numbered rows always expose blank inputs",
  );
  assertEqual(
    await page.locator("[data-pallet-weight-input]").evaluateAll((inputs) => inputs.map((input) => input.value)),
    ["", ""],
    "no-weight inputs are blank by default",
  );
  assertEqual(await page.getByText("Запази", { exact: true }).count(), 0, "no modal save button");
  assertEqual(await page.getByText("Добави тегла", { exact: true }).count(), 0, "no mode switch");

  for (let index = 0; index < 8; index += 1) {
    await page.keyboard.press("Tab");
    assert(
      await page.locator("[data-pallet-summary-dialog]").evaluate(
        (dialog) => dialog.contains(document.activeElement),
      ),
      "Forward Tab escaped the summary dialog.",
    );
    await page.keyboard.press("Shift+Tab");
    assert(
      await page.locator("[data-pallet-summary-dialog]").evaluate(
        (dialog) => dialog.contains(document.activeElement),
      ),
      "Reverse Tab escaped the summary dialog.",
    );
  }

  await clientOnly(page, state, "explicit summary close", async () => {
    await page.locator('[data-pallet-summary-close="icon"]').click();
    await assertClosedAndFocused(page, "explicit close");
  });
  await clientOnly(page, state, "summary reopen before Escape", async () => {
    await openSummary(page, expected);
  });
  await clientOnly(page, state, "Escape summary close", async () => {
    await page.keyboard.press("Escape");
    await assertClosedAndFocused(page, "Escape close");
  });
  await clientOnly(page, state, "summary reopen before backdrop", async () => {
    await openSummary(page, expected);
  });
  await clientOnly(page, state, "backdrop summary close", async () => {
    await page.locator("[data-pallet-summary-overlay]").click({ position: { x: 4, y: 4 } });
    await assertClosedAndFocused(page, "backdrop close");
  });
  passed("six-column no-weight summary, blank inputs, focus trap, isolation, and close paths");
}


async function verifyEmptyAndAllUnassigned(page, state, viewportDir) {
  await navigate(page, "empty");
  await clientOnly(page, state, "pending empty summary", async () => {
    await openSummary(page, scenario("empty"));
    assertEqual(
      normalized(await page.locator("[data-pallet-summary-empty]").textContent()),
      "Няма въведени ролки.",
      "empty summary message",
    );
    assertEqual(await page.locator("[data-pallet-summary-error]").count(), 0, "empty error state absent");
    assert(
      !(await page.getByText(PALLET_SUMMARY_ERROR_MESSAGE, { exact: true }).isVisible()),
      "empty summary unexpectedly shows the data-error message.",
    );
  });
  await atomicScreenshot(
    page,
    guardedArtifactPath(viewportDir, "empty-open.png"),
    { fullPage: true },
  );
  summary.screenshots.push(`${viewportDir}/empty-open.png`);
  await clientOnly(page, state, "pending empty summary close", async () => {
    await page.locator('[data-pallet-summary-close="footer"]').click();
  });

  await navigate(page, "all_unassigned");
  const expected = scenario("all_unassigned");
  await clientOnly(page, state, "all-unassigned summary", async () => {
    await openSummary(page, expected);
    assertEqual(await modalRows(page), expected.expected_rows, "all-unassigned rows");
    assertEqual(await modalTotal(page), expected.expected_total, "all-unassigned total");
    assertEqual(await page.locator("[data-pallet-weight-input]").count(), 0, "Без палет has no input");
    assertEqual(await page.locator("[data-pallet-summary-error]").count(), 0, "all-unassigned error absent");
    assert(
      !(await page.getByText(PALLET_SUMMARY_ERROR_MESSAGE, { exact: true }).isVisible()),
      "all-unassigned summary unexpectedly shows the data-error message.",
    );
    await page.locator('[data-pallet-summary-close="footer"]').click();
  });
  passed("empty and error-free all-unassigned summary states");
}


async function verifyMutualExclusionAndCorrection(page, state) {
  await navigate(page, "no_weights");
  const expected = scenario("no_weights");
  const surfaces = [
    { name: "queue", trigger: "#queue-open", open: "#queue-overlay.open" },
    { name: "waiting", trigger: "#waiting-open", open: "#waiting-overlay:not([hidden])" },
    { name: "history", trigger: "#history-open", open: "#history-overlay.open" },
    { name: "rewinding", trigger: "[data-rewinding-open]", open: "[data-rewinding-overlay]:not([hidden])" },
  ];
  for (const surface of surfaces) {
    await clientOnly(page, state, `summary opens before ${surface.name}`, async () => {
      await openSummary(page, expected);
    });
    await clientOnly(page, state, `${surface.name} closes summary`, async () => {
      await page.locator(surface.trigger).evaluate((button) => button.click());
      assert(await page.locator("[data-pallet-summary-overlay]").isHidden(), `${surface.name} did not close summary.`);
      assert(await page.locator(surface.open).isVisible(), `${surface.name} did not open.`);
    });
    await clientOnly(page, state, `summary closes ${surface.name}`, async () => {
      await page.locator("[data-pallet-summary-open]").evaluate((button) => button.click());
      assert(await page.locator(surface.open).isHidden(), `summary did not close ${surface.name}.`);
      assert(await page.locator("[data-pallet-summary-overlay]").isVisible(), "summary did not reopen.");
      await page.locator('[data-pallet-summary-close="footer"]').click();
    });
  }

  await clientOnly(page, state, "roll-correction summary lock", async () => {
    const edit = page.locator("button[data-roll-edit-open]").first();
    await edit.click();
    assert(await page.locator("[data-pallet-summary-open]").isDisabled(), "correction mode did not disable summary.");
    await page.locator("[data-roll-actions-for]:not([hidden]) [data-roll-row-cancel]").click();
    assert(await page.locator("[data-pallet-summary-open]").isEnabled(), "leaving correction did not enable summary.");
  });

  await page.locator("[data-timing-menu-button]").click();
  await page.locator("[data-timing-menu-open]").click();
  await page.locator("[data-timing-editor-overlay]").waitFor({ state: "visible" });
  assert(await page.locator("[data-pallet-summary-overlay]").isHidden(), "timing editor stacked over pallet summary");
  assert(
    await page.locator("[data-pallet-summary-open]").evaluate((button) => Boolean(button.closest("[inert]"))),
    "pallet summary trigger remained interactive behind timing editor",
  );
  await page.locator("[data-timing-cancel]").click();
  await page.locator("[data-timing-editor-overlay]").waitFor({ state: "hidden" });

  await openFinishReview(page);
  assert(await page.locator("[data-pallet-summary-overlay]").isHidden(), "finish review stacked over pallet summary");
  assert(
    await page.locator("[data-pallet-summary-open]").evaluate((button) => Boolean(button.closest("[inert]"))),
    "pallet summary trigger remained interactive behind finish review",
  );
  await closeFinishReview(page);

  await openSummary(page, expected);
  assert(await page.locator("[data-timing-editor-overlay]").isHidden(), "pallet summary stacked over timing editor");
  assert(await page.locator("[data-finish-review-overlay]").isHidden(), "pallet summary stacked over finish review");
  assert(
    await page.locator("[data-timing-menu-button]").evaluate((button) => Boolean(button.closest("[inert]"))),
    "timing trigger remained interactive behind pallet summary",
  );
  await page.locator('[data-pallet-summary-close="footer"]').click();
  passed("queue/waiting/history/rewinding plus finish and timing overlays exclude the pallet summary");
}


async function verifyManyPalletScroll(page, state, viewportDir) {
  await navigate(page, "many_pallets");
  const expected = scenario("many_pallets");
  await clientOnly(page, state, "many-pallet summary open", async () => {
    await openSummary(page, expected);
    assertEqual(await modalRows(page), expected.expected_rows, "many-pallet rows");
    assertEqual(await modalTotal(page), expected.expected_total, "many-pallet total");
    const scrolls = await page.locator("[data-pallet-summary-scroll]").evaluate((element) => ({
      scrollHeight: element.scrollHeight,
      clientHeight: element.clientHeight,
      scrolls: element.scrollHeight > element.clientHeight,
    }));
    assert(scrolls.scrollHeight > scrolls.clientHeight, "many-pallet table does not scroll.");
    assert(scrolls.scrolls, "scrollHeight > clientHeight was not satisfied.");
    await page.locator("[data-pallet-summary-scroll]").evaluate((element) => {
      element.scrollTop = element.scrollHeight;
    });
    assert(await page.locator("#pallet-summary-title").isVisible(), "title is not visible after scrolling.");
    assert(await page.locator('[data-pallet-summary-close="footer"]').isVisible(), "footer close is not visible after scrolling.");
    const sticky = await page.locator("[data-pallet-summary-dialog]").evaluate((dialog) => {
      const heading = dialog.querySelector("thead");
      const total = dialog.querySelector("tfoot");
      const footer = dialog.querySelector(".pallet-summary-footer");
      return [heading, total, footer].map((element) => getComputedStyle(element).position);
    });
    assertEqual(sticky, ["sticky", "sticky", "static"], "sticky heading/total and persistent footer");
    await assertSurfaceGeometry(page, {
      dialogSelector: "[data-pallet-summary-dialog]",
      headerSelector: "[data-pallet-summary-dialog] thead th",
    }, `${viewportDir} long pallet summary`);
  });
  await atomicScreenshot(
    page,
    guardedArtifactPath(viewportDir, "many-pallets-scrolled.png"),
    { fullPage: true },
  );
  summary.screenshots.push(`${viewportDir}/many-pallets-scrolled.png`);
  await clientOnly(page, state, "many-pallet summary close", async () => {
    await page.locator('[data-pallet-summary-close="footer"]').click();
  });
  passed("many-pallet summary scrolls with fixed reachable title and close");
}


async function verifyCompletedRows(page, state) {
  await navigate(page, "completed_complete");
  const expected = scenario("completed_complete");
  await clientOnly(page, state, "completed numbered summary", async () => {
    await openSummary(page, expected);
    assertEqual(await modalRows(page), expected.expected_rows, "completed numbered rows");
    assertEqual(await modalTotal(page), expected.expected_total, "completed numbered total");
    await page.locator('[data-pallet-summary-close="footer"]').click();
  });
}


async function verifyModalOnlyMatrix(page, state, viewportDir) {
  const before = databaseSnapshot();
  assertFixtureBaseline(before);
  await verifyAllStatusTriggers(page);
  await verifyRunningSummary(page, state, viewportDir);
  await verifyEmptyAndAllUnassigned(page, state, viewportDir);
  await verifyMutualExclusionAndCorrection(page, state);
  await verifyManyPalletScroll(page, state, viewportDir);
  await verifyCompletedRows(page, state);
  const after = databaseSnapshot();
  assertEqual(after, before, "modal-only production database snapshot");
  passed("modal-only interactions preserve cards, rolls, timing, pallets, and assignments");
}


async function verifyResponsiveBasicAndLong(page, viewportDir) {
  const before = databaseSnapshot();
  assertFixtureBaseline(before);

  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  assertEqual(await modalRows(page), scenario("no_weights").expected_rows, `${viewportDir} basic rows`);
  await assertSurfaceGeometry(page, {
    dialogSelector: "[data-pallet-summary-dialog]",
    headerSelector: "[data-pallet-summary-dialog] thead th",
  }, `${viewportDir} basic pallet summary`);
  await atomicScreenshot(
    page,
    guardedArtifactPath(viewportDir, "no-weights-open.png"),
    { fullPage: true },
  );
  summary.screenshots.push(`${viewportDir}/no-weights-open.png`);
  await page.locator('[data-pallet-summary-close="footer"]').click();

  await navigate(page, "empty");
  await openSummary(page, scenario("empty"));
  assertEqual(
    normalized(await page.locator("[data-pallet-summary-empty]").textContent()),
    "Няма въведени ролки.",
    `${viewportDir} empty summary`,
  );
  await assertSurfaceGeometry(page, {
    dialogSelector: "[data-pallet-summary-dialog]",
    headerSelector: "[data-pallet-summary-dialog] thead th",
  }, `${viewportDir} empty pallet summary`);
  await atomicScreenshot(
    page,
    guardedArtifactPath(viewportDir, "empty-open.png"),
    { fullPage: true },
  );
  summary.screenshots.push(`${viewportDir}/empty-open.png`);
  await page.locator('[data-pallet-summary-close="footer"]').click();

  await navigate(page, "many_pallets");
  await openSummary(page, scenario("many_pallets"));
  const scroll = page.locator("[data-pallet-summary-scroll]");
  await scroll.evaluate((element) => { element.scrollTop = element.scrollHeight; });
  assert(
    await scroll.evaluate((element) => element.scrollHeight > element.clientHeight),
    `${viewportDir}: long pallet summary does not scroll.`,
  );
  await assertSurfaceGeometry(page, {
    dialogSelector: "[data-pallet-summary-dialog]",
    headerSelector: "[data-pallet-summary-dialog] thead th",
  }, `${viewportDir} long pallet summary`);
  await atomicScreenshot(
    page,
    guardedArtifactPath(viewportDir, "many-pallets-scrolled.png"),
    { fullPage: true },
  );
  summary.screenshots.push(`${viewportDir}/many-pallets-scrolled.png`);
  await page.locator('[data-pallet-summary-close="footer"]').click();

  assertEqual(databaseSnapshot(), before, `${viewportDir} responsive state database snapshot`);
  runMutationAudit();
  passed(`${viewportDir} representative basic/empty/long-scroll geometry states fit`);
}


async function verifyViewportStateMatrix(page, state, viewportDir) {
  await parkBrowserAndResetFixture(page);
  await navigate(page, "partial_weights");
  await openFinishReview(page);
  assertEqual(
    !(await page.locator("[data-finish-review-confirm]").isDisabled()),
    scenario("partial_weights").finish_eligibility.normal,
    `${viewportDir} finish-review declared eligibility`,
  );
  await assertSurfaceGeometry(page, {
    dialogSelector: "[data-finish-review-dialog]",
    headerSelector: "[data-finish-review-overlay] thead th",
  }, `${viewportDir} finish review`);
  await atomicScreenshot(
    page,
    guardedArtifactPath(viewportDir, "finish-review.png"),
    { fullPage: true },
  );
  summary.screenshots.push(`${viewportDir}/finish-review.png`);
  await closeFinishReview(page);

  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  const endpoint = `${baseURL}/terminal/cards/${scenario("no_weights").card_id}/pallet-weights/2`;
  let malformed = false;
  await page.route(endpoint, async (route) => {
    if (malformed || route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    malformed = true;
    await route.fulfill({ status: 200, contentType: "text/plain", body: "not json" });
  });
  const postStart = state.postSequence.length;
  await palletInput(page, 2).fill("19");
  await palletInput(page, 2).press("Enter");
  await assertFatalReload(page, `${viewportDir} commit-ambiguous recovery`);
  assertEqual(state.postSequence.length - postStart, 1, `${viewportDir} fatal recovery POST count`);
  await assertSurfaceGeometry(page, {
    dialogSelector: "[data-pallet-summary-dialog]",
    headerSelector: "[data-pallet-summary-dialog] thead th",
  }, `${viewportDir} fatal recovery`);
  await atomicScreenshot(
    page,
    guardedArtifactPath(viewportDir, "fatal-recovery.png"),
    { fullPage: true },
  );
  summary.screenshots.push(`${viewportDir}/fatal-recovery.png`);
  await page.unroute(endpoint);
  runMutationAudit();

  await parkBrowserAndResetFixture(page);
  const archived = scenario("archived_complete");
  const response = await page.goto(`${baseURL}/admin/cards/${archived.card_id}`, { waitUntil: "networkidle" });
  assert(response?.ok(), `${viewportDir} admin modal page failed`);
  await page.locator("[data-pallet-summary-open]").click();
  await assertModalOpenState(page, archived);
  await assertSurfaceGeometry(page, {
    dialogSelector: "[data-pallet-summary-dialog]",
    headerSelector: "[data-pallet-summary-dialog] thead th",
  }, `${viewportDir} admin pallet summary`);
  await atomicScreenshot(
    page,
    guardedArtifactPath(viewportDir, "admin-modal.png"),
    { fullPage: true },
  );
  summary.screenshots.push(`${viewportDir}/admin-modal.png`);
  await page.locator('[data-pallet-summary-close="footer"]').click();
  runMutationAudit();

  passed(`${viewportDir} finish/fatal-recovery/admin geometry states fit without clipping or heading overlap`);
}


function palletInput(page, palletNumber) {
  return page.locator(`[data-pallet-weight-input="${palletNumber}"]`);
}


async function waitForSavedValue(page, palletNumber, value) {
  const input = palletInput(page, palletNumber);
  await input.waitFor({ state: "visible" });
  await page.waitForFunction(
    ({ number, expected }) => {
      const element = document.querySelector(`[data-pallet-weight-input="${number}"]`);
      return element?.value === expected
        && !element.hasAttribute("aria-busy")
        && !element.readOnly;
    },
    { number: palletNumber, expected: value },
  );
}


async function resetQueueIdleCapture(page) {
  await page.evaluate(() => {
    window.__task8QueueIdleEvents = [];
    if (window.__task8QueueIdleListenerInstalled) return;
    window.__task8QueueIdleListenerInstalled = true;
    document.addEventListener("pallet-summary:queue-idle", (event) => {
      window.__task8QueueIdleEvents.push({
        cardId: event.detail?.cardId ?? null,
        expectedVersion: event.detail?.expectedVersion ?? null,
        kind: event.detail?.reconciliation?.kind ?? null,
        reason: event.detail?.reconciliation?.reason ?? null,
      });
    });
  });
}


async function queueIdleEvents(page, expectedCount = 1) {
  await page.waitForFunction(
    (count) => (window.__task8QueueIdleEvents?.length || 0) >= count,
    expectedCount,
  );
  await page.waitForTimeout(100);
  return page.evaluate(() => structuredClone(window.__task8QueueIdleEvents || []));
}


async function verifySerializedAutosave(page, state, viewportDir) {
  await parkBrowserAndResetFixture(page);
  const expected = scenario("no_weights");
  await navigate(page, "no_weights");
  await openSummary(page, expected);
  const scroll = page.locator("[data-pallet-summary-scroll]");
  const initialScroll = await scroll.evaluate((element) => element.scrollTop);
  const postStart = state.postSequence.length;

  const first = palletInput(page, 2);
  await first.fill("20");
  await first.press("Enter");
  assert(
    await first.evaluate((element) => document.activeElement === element),
    "Enter-submitted field lost focus while saving.",
  );
  await waitForSavedValue(page, 2, "20.00");
  assert(await page.locator("[data-pallet-summary-overlay]").isVisible(), "autosave closed modal");

  const rapidSaveURL = `${baseURL}/terminal/cards/${expected.card_id}/pallet-weights/2`;
  let delayedRapidSave = false;
  await page.route(rapidSaveURL, async (route) => {
    if (!delayedRapidSave && route.request().method() === "POST") {
      delayedRapidSave = true;
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    await route.continue();
  });
  await resetQueueIdleCapture(page);
  await first.fill("21");
  const second = palletInput(page, 10);
  await second.focus();
  assert(
    await second.evaluate((element) => document.activeElement === element),
    "direct input-to-input focus was not preserved",
  );
  await second.fill("10.35");
  await second.press("Enter");
  await waitForSavedValue(page, 2, "21.00");
  await waitForSavedValue(page, 10, "10.35");
  const idleEvents = await queueIdleEvents(page);
  assertEqual(idleEvents.length, 1, "successful rapid-save idle reconciliation count");
  assertEqual(idleEvents[0].kind, "accept-local", "successful rapid-save idle reconciliation");
  summary.queueIdleReconciliations.push({ label: "successful local-only path", ...idleEvents[0] });
  await page.unroute(rapidSaveURL);

  const posts = state.postSequence.slice(postStart);
  assertEqual(posts.length, 3, "Enter/blur serialized save request count");
  const submittedVersions = posts.map((entry) => Number(multipartField(entry.postData, "loaded_version")));
  assert(
    submittedVersions[1] === submittedVersions[0] + 1
      && submittedVersions[2] === submittedVersions[1] + 1,
    `serialized saves did not use successive versions: ${submittedVersions}`,
  );
  assertEqual(await scroll.evaluate((element) => element.scrollTop), initialScroll, "autosave table position");
  const versionTokens = await page.locator(`form[action*="/cards/${expected.card_id}/"] input[name="loaded_version"]`).evaluateAll(
    (inputs) => Array.from(new Set(inputs.map((input) => input.value))),
  );
  assertEqual(versionTokens.length, 1, "card-scoped version tokens after saves");
  assertEqual(
    await page.locator("#terminal-refresh-alert").isVisible(),
    false,
    "local saves created a false stale alert",
  );
  await atomicScreenshot(
    page,
    guardedArtifactPath(viewportDir, "autosave-complete.png"),
    { fullPage: true },
  );
  summary.screenshots.push(`${viewportDir}/autosave-complete.png`);
  await page.locator('[data-pallet-summary-close="footer"]').click();
  await page.locator("[data-pallet-summary-overlay]").waitFor({ state: "hidden" });
  await page.locator("[data-pallet-summary-open]").click();
  await page.locator("[data-pallet-summary-overlay]").waitFor({ state: "visible" });
  assertEqual(
    normalized(await page.locator("[data-pallet-weight-status-message]").textContent()),
    "",
    "reopened summary success message",
  );
  assertEqual(
    await page.locator("[data-pallet-weight-status]").getAttribute("data-kind"),
    null,
    "reopened summary status kind",
  );
  await page.locator('[data-pallet-summary-close="footer"]').click();
  await page.locator("[data-pallet-summary-overlay]").waitFor({ state: "hidden" });
  runMutationAudit([
    `${expected.card_id}:2:2000`,
    `${expected.card_id}:2:2100`,
    `${expected.card_id}:10:1035`,
  ]);
  summary.interactionGroups.push("Enter, blur, exact two-decimal preservation, serialized rapid saves, version reconciliation");
  passed("independent Enter/blur saves serialize, preserve two decimals, retain modal position/focus, and reconcile once");
}


async function verifyValidationAndClears(page, state) {
  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  const postStart = state.postSequence.length;
  const first = palletInput(page, 2);
  const second = palletInput(page, 10);
  const rowHeight = await first.locator("xpath=ancestor::tr").evaluate(
    (row) => row.getBoundingClientRect().height,
  );
  await first.fill("abc");
  await second.focus();
  await assertFocusOn(page, '[data-pallet-weight-input="2"]', "client validation focus return");
  assertEqual(await first.inputValue(), "abc", "client-invalid typed value");
  assertEqual(await first.getAttribute("aria-invalid"), "true", "client-invalid field marker");
  for (const invalid of ["1e2", "12.345", "0", "-5", "101"] ) {
    await first.fill(invalid);
    await first.press("Enter");
    await first.waitFor({ state: "visible" });
    assertEqual(await first.getAttribute("aria-invalid"), "true", `invalid ${invalid} feedback`);
    if (invalid === "-5") {
      const message = normalized(
        await page.locator("[data-pallet-weight-status-message]").textContent(),
      );
      assert(message.includes("поне 0.01 кг"), "negative input did not show the minimum-weight message");
      assert(!message.includes("десетич"), "negative input showed a decimal-format message");
    }
  }
  assertEqual(state.postSequence.length, postStart, "client-invalid POST count");
  assertEqual(await page.locator("[data-pallet-weight-error]").count(), 0, "duplicate row-level errors");
  assertEqual(
    await page.locator("[data-pallet-weight-status]").getAttribute("data-kind"),
    "error",
    "client validation banner kind",
  );
  assert(
    normalized(await page.locator("[data-pallet-weight-status-message]").textContent()).length > 0,
    "invalid field has no footer message",
  );
  assertEqual(
    await first.locator("xpath=ancestor::tr").evaluate((row) => row.getBoundingClientRect().height),
    rowHeight,
    "validation changed the table row height",
  );
  runMutationAudit();

  await parkBrowserAndResetFixture(page);
  const complete = scenario("complete_weights");
  await navigate(page, "complete_weights");
  await openSummary(page, complete);
  await palletInput(page, 2).fill("");
  await palletInput(page, 2).press("Enter");
  await waitForSavedValue(page, 2, "");
  assertEqual(normalized(await page.locator("[data-pallet-weight-total]").textContent()), "-", "partial total after first clear");
  await palletInput(page, 7).fill("");
  await palletInput(page, 7).press("Enter");
  await waitForSavedValue(page, 7, "");
  assertEqual(
    await page.locator("[data-pallet-weight-status]").getAttribute("data-pallet-weight-status"),
    "none",
    "last clear returns to no-weights state",
  );
  runMutationAudit([
    `${complete.card_id}:2:clear`,
    `${complete.card_id}:7:clear`,
  ]);
  summary.interactionGroups.push("syntax/bounds validation and independent clear-to-none");
  passed("invalid values write nothing; independent clears return to valid no-weight state");
}


async function verifyDuplicateAnd422Continuation(page, state) {
  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  let delayed = false;
  const palletTwoURL = `${baseURL}/terminal/cards/${scenario("no_weights").card_id}/pallet-weights/2`;
  await page.route(palletTwoURL, async (route) => {
    if (!delayed) {
      delayed = true;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    await route.continue();
  });
  const postStart = state.postSequence.length;
  await palletInput(page, 2).fill("18");
  await palletInput(page, 2).press("Enter");
  await palletInput(page, 2).press("Enter");
  await waitForSavedValue(page, 2, "18.00");
  assertEqual(state.postSequence.length - postStart, 1, "same-field duplicate prevention");
  await page.unroute(palletTwoURL);
  runMutationAudit([`${scenario("no_weights").card_id}:2:1800`]);

  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  let delayedValidation = false;
  await page.route(palletTwoURL, async (route) => {
    if (delayedValidation) return route.continue();
    delayedValidation = true;
    await new Promise((resolve) => setTimeout(resolve, 200));
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        ok: false,
        messages: ["Проверете теглото."],
        field_errors: [{ pallet_number: 2, field: "pallet_weight", message: "Проверете теглото." }],
        reload_required: false,
      }),
    });
  });
  const focusReturnStart = state.postSequence.length;
  expectResponseError("deliberate delayed pallet validation", {
    method: "POST",
    pathname: `/terminal/cards/${scenario("no_weights").card_id}/pallet-weights/2`,
    status: 422,
  });
  expectConsoleError("deliberate delayed pallet validation", /status of 422 \(Unprocessable Entity\)/);
  await palletInput(page, 2).fill("19");
  await palletInput(page, 10).focus();
  await assertFocusOn(page, '[data-pallet-weight-input="10"]', "focus before delayed 422");
  await page.waitForFunction(() => (
    document.querySelector('[data-pallet-weight-input="2"]')?.getAttribute("aria-invalid") === "true"
  ));
  await assertFocusOn(page, '[data-pallet-weight-input="2"]', "delayed 422 focus return");
  assertEqual(await palletInput(page, 2).inputValue(), "19", "422 typed value preservation");
  assertEqual(state.postSequence.length - focusReturnStart, 1, "delayed 422 request count");
  await page.unroute(palletTwoURL);
  runMutationAudit();

  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  let rejected = false;
  await page.route(palletTwoURL, async (route) => {
    if (rejected) return route.continue();
    rejected = true;
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        ok: false,
        messages: ["Проверете теглото."],
        field_errors: [{ pallet_number: 2, field: "pallet_weight", message: "Проверете теглото." }],
        reload_required: false,
      }),
    });
  });
  const continuationStart = state.postSequence.length;
  expectResponseError("deliberate nonfatal pallet validation", {
    method: "POST",
    pathname: `/terminal/cards/${scenario("no_weights").card_id}/pallet-weights/2`,
    status: 422,
  });
  expectConsoleError("deliberate nonfatal pallet validation", /status of 422 \(Unprocessable Entity\)/);
  await palletInput(page, 2).fill("19");
  await palletInput(page, 2).press("Enter");
  await palletInput(page, 10).fill("13");
  await palletInput(page, 10).press("Enter");
  await waitForSavedValue(page, 10, "13.00");
  assertEqual(state.postSequence.length - continuationStart, 2, "422 queue continuation request count");
  assertEqual(await palletInput(page, 2).getAttribute("aria-invalid"), "true", "422 field remains failed");
  await page.unroute(palletTwoURL);
  runMutationAudit([`${scenario("no_weights").card_id}:10:1300`]);
  summary.interactionGroups.push("duplicate suppression and nonfatal 422 continuation");
  passed("same-field active protection prevents duplicates and 422 permits the next queued save");
}


async function queueTwoSaves(page) {
  await palletInput(page, 2).fill("19");
  await palletInput(page, 2).press("Enter");
  await palletInput(page, 10).fill("13");
  await palletInput(page, 10).press("Enter");
}


async function assertFatalReload(page, label) {
  const reload = page.locator("[data-pallet-weight-reload]");
  await reload.waitFor({ state: "visible" });
  await assertFocusOn(page, "[data-pallet-weight-reload]", label);
  assert(await page.locator("[data-pallet-summary-overlay]").isVisible(), `${label}: modal closed`);
  assert(
    await page.locator("[data-pallet-summary-dialog]").evaluate((dialog) => dialog.contains(document.activeElement)),
    `${label}: focus escaped modal`,
  );
  await assertPalletBackgroundInert(page, label);
}


async function verifyFatalFuses(page, state) {
  for (const mode of ["malformed", "network"]) {
    await parkBrowserAndResetFixture(page);
    await navigate(page, "no_weights");
    await openSummary(page, scenario("no_weights"));
    let first = true;
    const matcher = `${baseURL}/terminal/cards/${scenario("no_weights").card_id}/pallet-weights/2`;
    await page.route(matcher, async (route) => {
      if (!first) return route.continue();
      first = false;
      if (mode === "network") {
        expectFailedRequest("deliberate pallet-save network failure", {
          method: "POST",
          pathname: `/terminal/cards/${scenario("no_weights").card_id}/pallet-weights/2`,
          errorPattern: /net::ERR_CONNECTION_FAILED/,
        });
        await route.abort("connectionfailed");
      } else {
        await route.fulfill({ status: 200, contentType: "text/plain", body: "not json" });
      }
    });
    const postStart = state.postSequence.length;
    if (mode === "network") {
      expectConsoleError("deliberate pallet-save network failure", /net::ERR_CONNECTION_FAILED/);
    }
    await queueTwoSaves(page);
    await assertFatalReload(page, `${mode} fatal lock`);
    await page.waitForTimeout(150);
    assertEqual(state.postSequence.length - postStart, 1, `${mode}: zero later POSTs after fuse`);
    await page.unroute(matcher);
    runMutationAudit();
  }

  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  mutateCardVersion(scenario("no_weights").card_id);
  const staleStart = state.postSequence.length;
  expectResponseError("deliberate stale pallet save", {
    method: "POST",
    pathname: `/terminal/cards/${scenario("no_weights").card_id}/pallet-weights/2`,
    status: 409,
  });
  expectConsoleError("deliberate stale pallet save", /status of 409 \(Conflict\)/);
  await queueTwoSaves(page);
  await assertFatalReload(page, "stale fatal lock");
  await page.waitForTimeout(150);
  assertEqual(state.postSequence.length - staleStart, 1, "stale: zero later POSTs after fuse");

  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  const jumpURL = `${baseURL}/terminal/cards/${scenario("no_weights").card_id}/pallet-weights/2`;
  let jumped = false;
  await page.route(jumpURL, async (route) => {
    if (jumped || route.request().method() !== "POST") return route.continue();
    jumped = true;
    const savedResponse = await route.fetch();
    const payload = await savedResponse.json();
    payload.card_version += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
  const jumpStart = state.postSequence.length;
  await queueTwoSaves(page);
  await assertFatalReload(page, "version-jump malformed success fatal lock");
  await page.waitForTimeout(150);
  assertEqual(state.postSequence.length - jumpStart, 1, "version jump: zero later POSTs after fuse");
  await page.unroute(jumpURL);
  runMutationAudit([`${scenario("no_weights").card_id}:2:1900`]);
  summary.interactionGroups.push("fatal stale/network/malformed/version-jump response fuse");
  passed("fatal stale, network, malformed, and version-jump responses expose reload and suppress later queued POSTs");
}


async function verifySaveAwareDismissal(page, state) {
  const dismissals = [
    ["icon", async () => page.locator('[data-pallet-summary-close="icon"]').click()],
    ["footer", async () => page.locator('[data-pallet-summary-close="footer"]').click()],
    ["Escape", async () => page.keyboard.press("Escape")],
    ["backdrop", async () => page.locator("[data-pallet-summary-overlay]").click({ position: { x: 3, y: 3 } })],
  ];
  for (const [name, dismiss] of dismissals) {
    await parkBrowserAndResetFixture(page);
    await navigate(page, "no_weights");
    await openSummary(page, scenario("no_weights"));
    await palletInput(page, 2).fill("20");
    await dismiss();
    await page.locator("[data-pallet-summary-overlay]").waitFor({ state: "hidden" });
    await assertFocusOn(page, "[data-pallet-summary-open]", `${name} dirty dismissal focus return`);
    runMutationAudit([`${scenario("no_weights").card_id}:2:2000`]);
  }

  for (const [name, dismiss] of dismissals) {
    await parkBrowserAndResetFixture(page);
    await navigate(page, "no_weights");
    await openSummary(page, scenario("no_weights"));
    const invalidPostStart = state.postSequence.length;
    await palletInput(page, 2).fill("-5");
    await dismiss();
    await page.locator("[data-pallet-summary-overlay]").waitFor({ state: "hidden" });
    await assertFocusOn(page, "[data-pallet-summary-open]", `${name} invalid dismissal focus return`);
    assertEqual(await palletInput(page, 2).inputValue(), "", `${name} invalid draft restoration`);
    assertEqual(state.postSequence.length, invalidPostStart, `${name} invalid dismissal POST count`);
    runMutationAudit();
  }

  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  const endpoint = `${baseURL}/terminal/cards/${scenario("no_weights").card_id}/pallet-weights/2`;
  await page.route(endpoint, (route) => route.abort("connectionfailed"));
  expectFailedRequest("dirty dismissal network failure", {
    method: "POST",
    pathname: `/terminal/cards/${scenario("no_weights").card_id}/pallet-weights/2`,
    errorPattern: /net::ERR_CONNECTION_FAILED/,
  });
  expectConsoleError("dirty dismissal network failure", /net::ERR_CONNECTION_FAILED/);
  const networkPostStart = state.postSequence.length;
  await palletInput(page, 2).fill("20");
  await palletInput(page, 2).press("Enter");
  await assertFatalReload(page, "dirty dismissal network failure");
  await page.keyboard.press("Escape");
  await assertClosedAndFocused(page, "dirty network failure dismissal");
  assertEqual(state.postSequence.length - networkPostStart, 1, "dirty network dismissal POST count");
  await page.unroute(endpoint);
  runMutationAudit();

  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  mutateCardVersion(scenario("no_weights").card_id);
  expectResponseError("dirty dismissal stale failure", {
    method: "POST",
    pathname: `/terminal/cards/${scenario("no_weights").card_id}/pallet-weights/2`,
    status: 409,
  });
  expectConsoleError("dirty dismissal stale failure", /status of 409 \(Conflict\)/);
  const stalePostStart = state.postSequence.length;
  await palletInput(page, 2).fill("20");
  await palletInput(page, 2).press("Enter");
  await assertFatalReload(page, "dirty dismissal stale failure");
  await page.keyboard.press("Escape");
  await assertClosedAndFocused(page, "dirty stale failure dismissal");
  assertEqual(state.postSequence.length - stalePostStart, 1, "dirty stale dismissal POST count");

  summary.interactionGroups.push(
    "save-aware upper/footer/Escape/backdrop dismissal, invalid-draft discard, and dismissible network/stale recovery",
  );
  passed("all dismissal paths await valid saves, discard invalid drafts, and remain available after network/stale errors");
}


async function verifyAdminCorrection(page, viewportDir) {
  await parkBrowserAndResetFixture(page);
  const archived = scenario("archived_complete");
  let response = await page.goto(`${baseURL}/admin/cards/${archived.card_id}`, { waitUntil: "networkidle" });
  assert(response?.ok(), `archived admin page returned ${response?.status()}`);
  const customer = page.locator('input[name="customer"]');
  assert(await customer.count(), "admin customer input is missing");
  await customer.fill(`${await customer.inputValue()} редакция`);
  await page.locator("[data-pallet-summary-open]").click();
  assert(await page.locator("[data-pallet-summary-overlay]").isHidden(), "admin opened summary over dirty form");
  assert(await page.locator("[data-pallet-summary-open-error]").isVisible(), "admin dirty-form guidance missing");

  expectDialog("discard dirty admin form", {
    type: "beforeunload",
    response: "accept",
  });
  response = await page.reload({ waitUntil: "domcontentloaded" });
  assert(response?.ok(), "admin discard reload failed");
  await page.locator("[data-pallet-summary-open]").click();
  await assertModalOpenState(page, archived);
  await palletInput(page, 6).fill("20");
  await palletInput(page, 6).press("Enter");
  await waitForSavedValue(page, 6, "20.00");
  assertEqual(await modalRows(page), [
    ["6", "1", "45.0", "20.00", "65.00", "44.0"],
    ["9", "1", "55.5", "16.00", "71.50", "54.5"],
  ], "admin archived corrected rows");
  await atomicScreenshot(page, guardedArtifactPath(viewportDir, "admin-archived.png"), { fullPage: true });
  summary.screenshots.push(`${viewportDir}/admin-archived.png`);
  runMutationAudit([`${archived.card_id}:6:2000`]);

  await parkBrowserAndResetFixture(page);
  const completed = scenario("completed_complete");
  response = await page.goto(`${baseURL}/admin/cards/${completed.card_id}`, { waitUntil: "networkidle" });
  assert(response?.ok(), "completed admin page failed");
  await page.locator("[data-pallet-summary-open]").click();
  await palletInput(page, 3).fill("13");
  await palletInput(page, 3).press("Enter");
  await waitForSavedValue(page, 3, "13.00");
  runMutationAudit([`${completed.card_id}:3:1300`]);
  summary.interactionGroups.push("admin dirty-form refusal plus completed/archived correction");
  passed("admin refuses dirty outer form, then corrects completed and archived weights after discard");
}


async function finishRows(page) {
  return page.locator("[data-finish-production-rows] tr").evaluateAll((rows) => rows.map((row) => (
    Array.from(row.querySelectorAll("th, td")).map((cell) => cell.textContent.replace(/\s+/g, " ").trim())
  )));
}


async function openFinishReview(page, waiting = false) {
  const selector = waiting
    ? '[data-waiting-finish-review="true"] [data-waiting-finish-trigger]'
    : '[data-timing-finish-review="true"] button[type="submit"]:not([disabled])';
  const trigger = page.locator(selector).first();
  await trigger.waitFor({ state: "visible" });
  if (waiting) await trigger.waitFor({ state: "attached" });
  await trigger.click();
  await page.locator("[data-finish-review-overlay]").waitFor({ state: "visible" });
}


async function closeFinishReview(page) {
  await page.locator("[data-finish-review-cancel]").click();
  await page.locator("[data-finish-review-overlay]").waitFor({ state: "hidden" });
}


async function assertWaitingReviewFailure(page, {
  label,
  message,
  reloadRequired,
}) {
  const overlay = page.locator("[data-finish-review-overlay]");
  await overlay.waitFor({ state: "visible" });
  const alert = page.locator("[data-finish-review-alert]");
  await alert.waitFor({ state: "visible" });
  assert(
    normalized(await alert.textContent()).includes(message),
    `${label}: actionable message is missing`,
  );
  assert(await page.locator("[data-finish-review-confirm]").isDisabled(), `${label}: confirm remains enabled`);
  assertEqual(
    await page.locator("[data-finish-review-reload]").isVisible(),
    reloadRequired,
    `${label}: reload visibility`,
  );
  const backgroundState = await page.locator(".app, .terminal-toast").evaluateAll(
    (elements) => elements.map((element) => ({
      inert: element.getAttribute("inert"),
      ariaHidden: element.getAttribute("aria-hidden"),
    })),
  );
  assert(
    backgroundState.length >= 1
      && backgroundState.every(({ inert, ariaHidden }) => inert === "" && ariaHidden === "true"),
    `${label}: background is not isolated`,
  );
  if (reloadRequired) {
    await assertFocusOn(page, "[data-finish-review-alert]", `${label}: locked alert focus`);
    await page.keyboard.press("Tab");
    await assertFocusOn(page, "[data-finish-review-reload]", `${label}: keyboard reload recovery`);
    await page.keyboard.press("Escape");
    assert(await overlay.isVisible(), `${label}: Escape hid the only recovery surface`);
    await assertFocusOn(page, "[data-finish-review-reload]", `${label}: reload focus after blocked dismissal`);
  }
}


async function verifyWaitingReviewFailureRecovery(page, state) {
  const waiting = scenario("awaiting_partial");
  const endpoint = `${baseURL}/terminal/cards/${waiting.card_id}/finish-review`;
  const failures = [
    {
      name: "structural 422",
      message: "Добавете тегло за палет №5.",
      reloadRequired: false,
      prepare() {
        expectResponseError("deliberate waiting-review validation", {
          method: "POST",
          pathname: `/terminal/cards/${waiting.card_id}/finish-review`,
          status: 422,
        });
        expectConsoleError("deliberate waiting-review validation", /status of 422 \(Unprocessable Entity\)/);
      },
      fulfill: (route) => route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          ok: false,
          messages: ["Добавете тегло за палет №5."],
          field_errors: [{ source_index: null, field: "form", message: "Добавете тегло за палет №5." }],
        }),
      }),
    },
    {
      name: "stale 409",
      message: "Картата е променена",
      reloadRequired: true,
      prepare() {
        expectResponseError("deliberate waiting-review stale response", {
          method: "POST",
          pathname: `/terminal/cards/${waiting.card_id}/finish-review`,
          status: 409,
        });
        expectConsoleError("deliberate waiting-review stale response", /status of 409 \(Conflict\)/);
      },
      fulfill: (route) => route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          ok: false,
          messages: ["Картата е променена след зареждането на страницата. Презаредете и опитайте отново."],
          field_errors: [{
            source_index: null,
            field: "form",
            message: "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
          }],
        }),
      }),
    },
    {
      name: "malformed JSON",
      message: "Отговорът на сървъра е невалиден.",
      reloadRequired: true,
      prepare() {},
      fulfill: (route) => route.fulfill({ status: 200, contentType: "text/plain", body: "not json" }),
    },
    {
      name: "malformed payload",
      message: "Отговорът на сървъра е невалиден.",
      reloadRequired: true,
      prepare() {},
      fulfill: (route) => route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          finish_review: { mode: "finalize_rewinding", card_version: waiting.card_version },
        }),
      }),
    },
    {
      name: "network",
      message: "Връзката със сървъра прекъсна.",
      reloadRequired: true,
      prepare() {
        expectFailedRequest("deliberate waiting-review network failure", {
          method: "POST",
          pathname: `/terminal/cards/${waiting.card_id}/finish-review`,
          errorPattern: /net::ERR_CONNECTION_FAILED/,
        });
        expectConsoleError("deliberate waiting-review network failure", /net::ERR_CONNECTION_FAILED/);
      },
      fulfill: (route) => route.abort("connectionfailed"),
    },
  ];

  for (const failure of failures) {
    await parkBrowserAndResetFixture(page);
    await navigate(page, "awaiting_partial");
    let handled = false;
    await page.route(endpoint, async (route) => {
      if (handled || route.request().method() !== "POST") return route.continue();
      handled = true;
      await failure.fulfill(route);
    });
    failure.prepare();
    const postStart = state.postSequence.length;
    await page.locator('[data-waiting-finish-review="true"] [data-waiting-finish-trigger]').click();
    await assertWaitingReviewFailure(page, {
      label: failure.name,
      message: failure.message,
      reloadRequired: failure.reloadRequired,
    });
    assertEqual(state.postSequence.length - postStart, 1, `${failure.name}: request count`);
    if (!failure.reloadRequired) {
      await closeFinishReview(page);
      await assertFocusOn(
        page,
        '[data-waiting-finish-review="true"] [data-waiting-finish-trigger]',
        `${failure.name}: trigger focus return`,
      );
    }
    await page.unroute(endpoint);
    runMutationAudit();
  }
  summary.interactionGroups.push("visible waiting-review 422/stale/malformed/network recovery");
  passed("waiting-review failures remain visible, isolated, and keyboard recoverable");
}


async function verifyFinishReviewRefreshes(page, viewportDir) {
  await parkBrowserAndResetFixture(page);
  await navigate(page, "partial_weights");
  await openFinishReview(page);
  assert(await page.locator("[data-finish-review-confirm]").isDisabled(), "partial normal finish is not blocked");
  assert(
    normalized(await page.locator("[data-finish-review-alert]").textContent()).includes("№7"),
    "normal finish blocker does not identify missing pallet 7",
  );
  const blockerGeometry = await page.locator("[data-finish-review-overlay]").evaluate((overlay) => {
    const status = overlay.querySelector(".finish-review-footer-status").getBoundingClientRect();
    const alert = overlay.querySelector("[data-finish-review-alert]").getBoundingClientRect();
    const actions = overlay.querySelector(".finish-review-footer-actions").getBoundingClientRect();
    return {
      statusLeft: status.left,
      statusRight: status.right,
      alertLeft: alert.left,
      alertRight: alert.right,
      actionsLeft: actions.left,
    };
  });
  for (const [actual, expected, label] of [
    [blockerGeometry.alertLeft, blockerGeometry.statusLeft, "finish blocker left edge"],
    [blockerGeometry.alertRight, blockerGeometry.statusRight, "finish blocker right edge"],
    [blockerGeometry.statusRight + 16, blockerGeometry.actionsLeft, "finish blocker action gap"],
  ]) {
    assert(
      Math.abs(actual - expected) <= 1,
      `${label}: expected ${expected}, found ${actual}`,
    );
  }
  await atomicScreenshot(page, guardedArtifactPath(viewportDir, "finish-blocked.png"), { fullPage: true });
  summary.screenshots.push(`${viewportDir}/finish-blocked.png`);
  await closeFinishReview(page);

  await page.locator("[data-pallet-summary-open]").click();
  await palletInput(page, 7).fill("10");
  await palletInput(page, 7).press("Enter");
  await waitForSavedValue(page, 7, "10.00");
  await page.locator('[data-pallet-summary-close="footer"]').click();
  await openFinishReview(page);
  assert(!(await page.locator("[data-finish-review-confirm]").isDisabled()), "complete normal finish remains blocked");
  assertEqual(await finishRows(page), [
    ["2", "1", "60.0", "10.35", "70.35", "59.0"],
    ["7", "1", "40.5", "10.00", "50.50", "39.5"],
  ], "save-then-open normal finish rows");
  assertEqual(
    normalized(await page.locator("[data-finish-pallet-weight-total]").textContent()),
    "20.35",
    "normal finish refreshed pallet total",
  );
  runMutationAudit([`${scenario("partial_weights").card_id}:7:1000`]);

  await parkBrowserAndResetFixture(page);
  await navigate(page, "mixed_unassigned");
  await openFinishReview(page);
  assert(!(await page.locator("[data-finish-review-confirm]").isDisabled()), "partial waiting entry was hard blocked");
  assert(await page.locator("[data-finish-review-warning]").isVisible(), "partial waiting-entry warning missing");
  await closeFinishReview(page);
  await page.locator("[data-pallet-summary-open]").click();
  await palletInput(page, 3).fill("");
  await palletInput(page, 3).press("Enter");
  await waitForSavedValue(page, 3, "");
  await page.locator('[data-pallet-summary-close="footer"]').click();
  await openFinishReview(page);
  assert(!(await page.locator("[data-finish-review-confirm]").isDisabled()), "clear-then-open waiting entry blocked");
  assertEqual(
    normalized(await page.locator("[data-finish-pallet-weight-total]").textContent()),
    "-",
    "waiting entry clear refresh total",
  );
  runMutationAudit([`${scenario("mixed_unassigned").card_id}:3:clear`]);

  await parkBrowserAndResetFixture(page);
  await navigate(page, "awaiting_partial");
  await openFinishReview(page, true);
  assert(await page.locator("[data-finish-review-confirm]").isDisabled(), "partial waiting finalization is not blocked");
  assert(
    normalized(await page.locator("[data-finish-review-alert]").textContent()).includes("№5"),
    "waiting finalization blocker does not identify pallet 5",
  );
  await closeFinishReview(page);
  await page.locator("[data-pallet-summary-open]").click();
  await palletInput(page, 5).fill("12,5");
  await palletInput(page, 5).press("Enter");
  await waitForSavedValue(page, 5, "12.50");
  await page.locator('[data-pallet-summary-close="footer"]').click();
  await openFinishReview(page, true);
  assert(!(await page.locator("[data-finish-review-confirm]").isDisabled()), "complete waiting finalization remains blocked");
  assertEqual(await finishRows(page), [
    ["4", "1", "70.0", "15.50", "85.50", "69.0"],
    ["5", "1", "30.5", "12.50", "43.00", "29.5"],
  ], "save-then-open waiting final rows");
  assertEqual(
    await page.locator("[data-finish-review-edit]").count(),
    0,
    "waiting final review reopened timing editor",
  );
  runMutationAudit([`${scenario("awaiting_partial").card_id}:5:1250`]);
  summary.interactionGroups.push("fresh normal/waiting-entry/waiting-final finish reviews after save/clear");
  passed("server-refreshed finish reviews enforce hard blockers and warning-only waiting entry");
}


async function verifyCardStaleTakeover(page) {
  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  mutateCardVersion(scenario("no_weights").card_id);
  summary.staleSimulations.push("external public card-version change");
  await page.locator("#terminal-refresh-alert").waitFor({ state: "visible", timeout: 15000 });
  assert(await page.locator("[data-pallet-summary-overlay]").isHidden(), "card stale did not close summary.");
  await assertFocusOn(page, "#terminal-refresh-alert-button", "card stale refresh alert");
  passed("existing snapshot poll performs card-stale summary takeover");
}


async function verifyShiftStaleTakeover(page) {
  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  mutateActiveShift(fixture.active_shift.alternate_number);
  summary.staleSimulations.push("external fetch_active_shift/update_active_shift_number change");
  const shiftReload = page.locator("[data-shift-window][data-shift-state='reload']");
  await shiftReload.waitFor({ state: "visible", timeout: 15000 });
  assert(await page.locator("[data-pallet-summary-overlay]").isHidden(), "shift stale did not close summary.");
  await assertFocusOn(page, "[data-shift-reload]", "shift-stale reload surface");
  passed("existing snapshot poll performs shift-stale summary takeover");
}


async function verifyQueueIdleRaceMatrix(page, state) {
  const selectedCard = scenario("no_weights");
  const saveURL = `${baseURL}/terminal/cards/${selectedCard.card_id}/pallet-weights/2`;
  const cases = [
    ["selected version change at idle", () => mutateCardVersion(selectedCard.card_id)],
    ["other active card change at idle", () => mutateCardVersion(scenario("partial_weights").card_id)],
    ["other waiting card change at idle", () => mutateCardVersion(scenario("many_pallets").card_id)],
    ["queue reorder at idle", () => mutateQueueStructure(scenario("empty").card_id)],
    ["queue membership change at idle", () => mutateQueueMembership(scenario("empty").card_id)],
    ["shift structural change at idle", () => mutateActiveShift(fixture.active_shift.alternate_number)],
  ];

  for (const [label, mutate] of cases) {
    await parkBrowserAndResetFixture(page);
    await navigate(page, "no_weights");
    await openSummary(page, selectedCard);
    await resetQueueIdleCapture(page);
    let intercepted = false;
    await page.route(saveURL, async (route) => {
      if (intercepted || route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      intercepted = true;
      const savedResponse = await route.fetch();
      assertEqual(savedResponse.status(), 200, `${label}: delayed local save status`);
      mutate();
      await route.fulfill({ response: savedResponse });
    });
    const postStart = state.postSequence.length;
    await palletInput(page, 2).fill("19");
    await palletInput(page, 2).press("Enter");
    await assertFatalReload(page, label);
    const idleEvents = await queueIdleEvents(page);
    assertEqual(idleEvents.length, 1, `${label}: idle reconciliation count`);
    assertEqual(idleEvents[0].kind, "stale", `${label}: reconciliation outcome`);
    assert(await page.locator("#terminal-refresh-alert").isVisible(), `${label}: refresh alert missing`);
    assertEqual(state.postSequence.length - postStart, 1, `${label}: local save POST count`);
    summary.staleSimulations.push(label);
    summary.queueIdleReconciliations.push({ label, ...idleEvents[0] });
    await page.unroute(saveURL);
  }

  summary.interactionGroups.push(
    "delayed local saves reject selected/other-active/other-waiting/queue-order/queue-membership/shift races at queue idle",
  );
  passed("queue-idle reconciliation rejects every nonlocal delayed-save race");
}


async function verifyStructuredStaleMatrix(page) {
  const cases = [
    ["newer selected card version", () => mutateCardVersion(scenario("no_weights").card_id)],
    ["other active card change", () => mutateCardVersion(scenario("partial_weights").card_id)],
    ["other waiting card change", () => mutateCardVersion(scenario("many_pallets").card_id)],
    ["queue ordering change", () => mutateQueueStructure(scenario("empty").card_id)],
  ];
  for (const [label, mutate] of cases) {
    await parkBrowserAndResetFixture(page);
    await navigate(page, "no_weights");
    await openSummary(page, scenario("no_weights"));
    mutate();
    summary.staleSimulations.push(label);
    await page.locator("#terminal-refresh-alert").waitFor({ state: "visible", timeout: 15000 });
    assert(await page.locator("[data-pallet-summary-overlay]").isHidden(), `${label}: clean modal stayed open`);
    await assertFocusOn(page, "#terminal-refresh-alert-button", `${label} refresh focus`);
  }

  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  await palletInput(page, 2).fill("19");
  mutateCardVersion(scenario("no_weights").card_id);
  summary.staleSimulations.push("dirty selected-card takeover");
  await assertFatalReload(page, "dirty stale takeover");
  assertEqual(await palletInput(page, 2).inputValue(), "19", "dirty stale draft preserved");

  await parkBrowserAndResetFixture(page);
  await navigate(page, "no_weights");
  await openSummary(page, scenario("no_weights"));
  endActiveShift();
  expectResponseError("deliberate inactive-shift pallet save", {
    method: "POST",
    pathname: `/terminal/cards/${scenario("no_weights").card_id}/pallet-weights/2`,
    status: 422,
  });
  expectConsoleError("deliberate inactive-shift pallet save", /status of 422 \(Unprocessable Entity\)/);
  await palletInput(page, 2).fill("19");
  await palletInput(page, 2).press("Enter");
  await page.waitForFunction(() => document.querySelector('[data-pallet-weight-input="2"]')?.getAttribute("aria-invalid") === "true");
  assertEqual(
    await page.locator("[data-pallet-weight-status]").getAttribute("data-kind"),
    "error",
    "inactive-shift save status kind",
  );
  await assertFatalReload(page, "inactive shift polling takeover");
  summary.interactionGroups.push("selected/other-active/waiting/queue/shift stale matrix and dirty takeover");
  passed("structured polling rejects every nonlocal change and preserves dirty drafts under stale takeover");
}


async function main() {
  let browser;
  try {
    browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();
    const state = {
      navigationCount: 0,
      requests: [],
      postSequence: [],
    };
    page.on("framenavigated", (frame) => {
      if (frame === page.mainFrame()) state.navigationCount += 1;
    });
    page.on("request", (request) => {
      const url = request.url();
      const origin = new URL(url).origin;
      const entry = { method: request.method(), url, postData: request.postData() || "" };
      state.requests.push(entry);
      if (request.method() === "POST") {
        state.postSequence.push({ ...entry, postSequence: state.postSequence.length + 1 });
        summary.postRequests.push({ method: request.method(), url, postSequence: state.postSequence.length });
      }
      if (!summary.network.observedOrigins.includes(origin)) {
        summary.network.observedOrigins.push(origin);
      }
    });
    page.on("requestfailed", (request) => {
      const failedURL = new URL(request.url());
      const failure = {
        method: request.method(),
        url: request.url(),
        origin: failedURL.origin,
        pathname: failedURL.pathname,
        error: request.failure()?.errorText || "unknown",
      };
      const expected = consumeExpectedNetworkEvent(
        pendingFailedRequestExpectations,
        failure,
        ["method", "origin", "pathname"],
        "errorPattern",
      );
      if (expected) {
        summary.expectedFailedRequests.push({ label: expected.label, ...failure });
      } else {
        summary.failedRequests.push(failure);
      }
    });
    page.on("pageerror", (error) => summary.pageErrors.push(error.message));
    page.on("response", (response) => {
      if (response.status() < 400) return;
      const responseURL = new URL(response.url());
      const item = {
        method: response.request().method(),
        status: response.status(),
        url: response.url(),
        origin: responseURL.origin,
        pathname: responseURL.pathname,
      };
      const expected = consumeExpectedNetworkEvent(
        pendingResponseErrorExpectations,
        item,
        ["method", "origin", "pathname", "status"],
      );
      if (expected) {
        summary.expectedResponseErrors.push({ label: expected.label, ...item });
      } else {
        summary.unexpectedResponseErrors.push(item);
      }
    });
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const messageText = message.text();
      const expectedIndex = pendingConsoleErrors.findIndex(
        ({ pattern }) => pattern.test(messageText),
      );
      if (expectedIndex === -1) {
        summary.consoleErrors.push(messageText);
        return;
      }
      const [{ label }] = pendingConsoleErrors.splice(expectedIndex, 1);
      summary.expectedConsoleErrors.push({ label, message: messageText });
    });
    page.on("dialog", async (dialog) => {
      const item = {
        type: dialog.type(),
        message: dialog.message(),
        origin: new URL(dialog.page().url()).origin,
      };
      const expected = consumeExpectedNetworkEvent(
        pendingDialogExpectations,
        item,
        ["type", "origin"],
      );
      if (expected) {
        summary.expectedDialogs.push({ label: expected.label, ...item });
        if (expected.response === "accept") {
          await dialog.accept();
        } else {
          await dialog.dismiss();
        }
      } else {
        summary.unexpectedDialogs.push(item);
        await dialog.dismiss();
      }
    });

    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await parkBrowserAndResetFixture(page);
      const viewportDir = viewport.name;
      const resolvedViewportDir = path.resolve(artifactDir, viewportDir);
      assertNoSymlinkComponents(
        artifactDir,
        resolvedViewportDir,
        "Viewport artifact path must not contain symlinks.",
      );
      fs.mkdirSync(resolvedViewportDir, { recursive: true });
      if (viewport.name === "desktop-1440") {
        await verifyModalOnlyMatrix(page, state, viewportDir);
        await verifySerializedAutosave(page, state, viewportDir);
      } else {
        await verifyResponsiveBasicAndLong(page, viewportDir);
      }
      await verifyViewportStateMatrix(page, state, viewportDir);
      summary.viewports.push(viewport);
    }

    await page.setViewportSize({ width: 1440, height: 900 });
    await verifyValidationAndClears(page, state);
    await verifyDuplicateAnd422Continuation(page, state);
    await verifyFatalFuses(page, state);
    await verifySaveAwareDismissal(page, state);
    await verifyAdminCorrection(page, "desktop-1440");
    await verifyFinishReviewRefreshes(page, "desktop-1440");
    await verifyWaitingReviewFailureRecovery(page, state);
    await verifyQueueIdleRaceMatrix(page, state);
    await verifyStructuredStaleMatrix(page);
    await verifyShiftStaleTakeover(page);
    await parkBrowserAndResetFixture(page);
    passed("final guarded database was restored to the canonical fixture");

    assertEqual(summary.consoleErrors, [], "error-level browser console messages");
    assertEqual(
      pendingConsoleErrors.map(({ label }) => label),
      [],
      "expected console error was not observed",
    );
    assertEqual(summary.pageErrors, [], "browser page errors");
    assertEqual(summary.unexpectedResponseErrors, [], "unexpected HTTP error responses");
    assertEqual(summary.failedRequests, [], "failed browser requests");
    assertEqual(summary.unexpectedDialogs, [], "unexpected browser dialogs");
    assertEqual(
      pendingFailedRequestExpectations.map(({ label }) => label),
      [],
      "expected failed request was not observed",
    );
    assertEqual(
      pendingResponseErrorExpectations.map(({ label }) => label),
      [],
      "expected response error was not observed",
    );
    assertEqual(
      pendingDialogExpectations.map(({ label }) => label),
      [],
      "expected dialog was not observed",
    );
    passed("no unexpected browser console message, page error, response error, request failure, or dialog");
    const allowedPostPaths = new Set();
    for (const fixtureScenario of Object.values(fixture.scenarios)) {
      for (const palletNumber of Object.keys(fixtureScenario.expected_inputs)) {
        if (fixtureScenario.editable.terminal) {
          allowedPostPaths.add(
            `/terminal/cards/${fixtureScenario.card_id}/pallet-weights/${palletNumber}`,
          );
        }
        if (fixtureScenario.editable.admin) {
          allowedPostPaths.add(
            `/admin/cards/${fixtureScenario.card_id}/pallet-weights/${palletNumber}`,
          );
        }
      }
      if (fixtureScenario.editable.terminal) {
        allowedPostPaths.add(`/terminal/cards/${fixtureScenario.card_id}/finish-review`);
      }
    }
    allowedPostPaths.add(
      `/terminal/cards/${scenario("no_weights").card_id}/timing-ledger/preview`,
    );
    const unsafeBrowserRequests = state.requests.filter(({ method, url }) => {
      const requestURL = new URL(url);
      return requestURL.origin !== baseOrigin
        || ["PUT", "PATCH", "DELETE"].includes(method)
        || (method === "POST" && !allowedPostPaths.has(requestURL.pathname));
    });
    assertEqual(unsafeBrowserRequests, [], "unexpected-origin or unexpected mutation browser requests");
    passed(`browser requests remained on ${baseOrigin}; POSTs matched the exact guarded pallet, timing-preview, and finish-review endpoint set`);
    summary.status = "passed";
    atomicWriteArtifact(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
    console.log("Terminal pallet-summary UI verification passed.");
    console.log(JSON.stringify(summary, null, 2));
  } finally {
    if (browser) await browser.close();
  }
}


main().catch((error) => {
  summary.status = "failed";
  summary.error = error.stack || String(error);
  try {
    if (summaryPath) {
      atomicWriteArtifact(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
    }
  } catch {
    // Preserve the original guard or verification failure.
  }
  console.error(error.stack || error);
  process.exitCode = 1;
});
