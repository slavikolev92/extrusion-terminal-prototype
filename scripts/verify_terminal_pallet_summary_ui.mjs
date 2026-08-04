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

let fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const databaseInput = path.resolve(repoRoot, fixture.db_path);
assert(fs.existsSync(databaseInput), `Fixture database does not exist: ${databaseInput}`);
const databasePath = fs.realpathSync(databaseInput);
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), databasePath),
  "Fixture database must resolve below .test-runtime.",
);
assert(fs.statSync(databasePath).isFile(), "Fixture database must be a regular file.");

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
  }
  return target;
}


const summary = {
  status: "running",
  url: baseURL,
  databaseIdentity: databasePath,
  fixture: path.relative(repoRoot, fixturePath),
  assertions: [],
  viewports: [],
  screenshots: [],
  consoleErrors: [],
  pageErrors: [],
  failedRequests: [],
  unexpectedDialogs: [],
  staleSimulations: [],
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
      .map((cell) => cell.textContent.replace(/\s+/g, " ").trim())),
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
    `Поръчка №${expectedScenario.order_number}`,
    "summary order context",
  );
  const background = page.locator(
    ".terminal-toast, .terminal-header, .machine-nav, .main",
  );
  assert((await background.count()) >= 3, "Expected terminal background targets are missing.");
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
  assert(
    await page.locator(selector).evaluate((element) => document.activeElement === element),
    `${label}: expected element does not own focus.`,
  );
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
    await navigate(page, name);
    const trigger = page.locator("[data-pallet-summary-open]");
    assertEqual(await trigger.count(), 1, `${name}: one pallet trigger`);
    assert(await trigger.isEnabled(), `${name}: pallet trigger is disabled.`);
    assertEqual(normalized(await trigger.textContent()), "Палети", `${name}: trigger text`);
  }
  passed("all five named statuses expose one enabled Палети button");
}


async function verifyRunningSummary(page, state, viewportDir) {
  await navigate(page, "running_mixed");
  const expected = scenario("running_mixed");
  const actions = await page.locator("[data-roll-secondary-actions] button").allTextContents();
  const rewindingActionLabel = "Пренавиване";
  assertEqual(
    actions.map(normalized),
    [`${rewindingActionLabel}: 1`, "Палети"],
    "running secondary action order",
  );

  await clientOnly(page, state, "running summary open", async () => openSummary(page, expected));
  const headings = await page.locator("[data-pallet-summary-dialog] thead th").allTextContents();
  assertEqual(
    headings.map(normalized),
    ["Палет", "Брой ролки", "Бруто, кг", "Нето, кг"],
    "summary headings",
  );
  assertEqual(await modalRows(page), expected.expected_rows, "running mixed ordered rows");
  assertEqual(await modalTotal(page), expected.expected_total, "running mixed total");
  await page.screenshot({
    path: guardedArtifactPath(viewportDir, "running-mixed-open.png"),
    fullPage: true,
  });
  summary.screenshots.push(`${viewportDir}/running-mixed-open.png`);

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
    await page.locator("[data-pallet-summary-close]").click();
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
  passed("running summary exact content, focus trap, isolation, and close paths");
}


async function verifyEmptyAndAllUnassigned(page, state, viewportDir) {
  await navigate(page, "pending_empty");
  await clientOnly(page, state, "pending empty summary", async () => {
    await openSummary(page, scenario("pending_empty"));
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
  await page.screenshot({
    path: guardedArtifactPath(viewportDir, "pending-empty-open.png"),
    fullPage: true,
  });
  summary.screenshots.push(`${viewportDir}/pending-empty-open.png`);
  await clientOnly(page, state, "pending empty summary close", async () => {
    await page.locator("[data-pallet-summary-close]").click();
  });

  await navigate(page, "paused_all_unassigned");
  const expected = scenario("paused_all_unassigned");
  await clientOnly(page, state, "all-unassigned summary", async () => {
    await openSummary(page, expected);
    assertEqual(await modalRows(page), expected.expected_rows, "all-unassigned rows");
    assertEqual(await modalTotal(page), expected.expected_total, "all-unassigned total");
    assertEqual(await page.locator("[data-pallet-summary-error]").count(), 0, "all-unassigned error absent");
    assert(
      !(await page.getByText(PALLET_SUMMARY_ERROR_MESSAGE, { exact: true }).isVisible()),
      "all-unassigned summary unexpectedly shows the data-error message.",
    );
    await page.locator("[data-pallet-summary-close]").click();
  });
  passed("empty and error-free all-unassigned summary states");
}


async function verifyMutualExclusionAndCorrection(page, state) {
  await navigate(page, "running_mixed");
  const expected = scenario("running_mixed");
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
      await page.locator("[data-pallet-summary-close]").click();
    });
  }

  await clientOnly(page, state, "roll-correction summary lock", async () => {
    const edit = page.locator("button[data-roll-edit-open]").first();
    await edit.click();
    assert(await page.locator("[data-pallet-summary-open]").isDisabled(), "correction mode did not disable summary.");
    await page.locator("[data-roll-actions-for]:not([hidden]) [data-roll-row-cancel]").click();
    assert(await page.locator("[data-pallet-summary-open]").isEnabled(), "leaving correction did not enable summary.");
  });
  passed("queue/waiting/history/rewinding mutual exclusion and correction lock");
}


async function verifyManyPalletScroll(page, state, viewportDir) {
  await navigate(page, "awaiting_many_pallets");
  const expected = scenario("awaiting_many_pallets");
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
    assert(await page.locator("[data-pallet-summary-close]").isVisible(), "close is not visible after scrolling.");
    await assertFocusOn(page, "[data-pallet-summary-close]", "many-pallet close reachability");
  });
  await page.screenshot({
    path: guardedArtifactPath(viewportDir, "awaiting-many-scrolled.png"),
    fullPage: true,
  });
  summary.screenshots.push(`${viewportDir}/awaiting-many-scrolled.png`);
  await clientOnly(page, state, "many-pallet summary close", async () => {
    await page.locator("[data-pallet-summary-close]").click();
  });
  passed("many-pallet summary scrolls with fixed reachable title and close");
}


async function verifyCompletedRows(page, state) {
  await navigate(page, "completed_numbered");
  const expected = scenario("completed_numbered");
  await clientOnly(page, state, "completed numbered summary", async () => {
    await openSummary(page, expected);
    assertEqual(await modalRows(page), expected.expected_rows, "completed numbered rows");
    assertEqual(await modalTotal(page), expected.expected_total, "completed numbered total");
    await page.locator("[data-pallet-summary-close]").click();
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


async function verifyCardStaleTakeover(page) {
  await parkBrowserAndResetFixture(page);
  await navigate(page, "running_mixed");
  await openSummary(page, scenario("running_mixed"));
  mutateCardVersion(scenario("running_mixed").card_id);
  summary.staleSimulations.push("external public card-version change");
  await page.locator("#terminal-refresh-alert").waitFor({ state: "visible", timeout: 15000 });
  assert(await page.locator("[data-pallet-summary-overlay]").isHidden(), "card stale did not close summary.");
  await assertFocusOn(page, "#terminal-refresh-alert-button", "card stale refresh alert");
  passed("existing snapshot poll performs card-stale summary takeover");
}


async function verifyShiftStaleTakeover(page) {
  await parkBrowserAndResetFixture(page);
  await navigate(page, "running_mixed");
  await openSummary(page, scenario("running_mixed"));
  mutateActiveShift(fixture.active_shift.alternate_number);
  summary.staleSimulations.push("external fetch_active_shift/update_active_shift_number change");
  const shiftReload = page.locator("[data-shift-window][data-shift-state='reload']");
  await shiftReload.waitFor({ state: "visible", timeout: 15000 });
  assert(await page.locator("[data-pallet-summary-overlay]").isHidden(), "shift stale did not close summary.");
  await assertFocusOn(page, "[data-shift-reload]", "shift-stale reload surface");
  passed("existing snapshot poll performs shift-stale summary takeover");
}


async function main() {
  let browser;
  try {
    browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();
    const state = { navigationCount: 0, requests: [] };
    page.on("framenavigated", (frame) => {
      if (frame === page.mainFrame()) state.navigationCount += 1;
    });
    page.on("request", (request) => {
      const url = request.url();
      const origin = new URL(url).origin;
      state.requests.push({ method: request.method(), url });
      if (!summary.network.observedOrigins.includes(origin)) {
        summary.network.observedOrigins.push(origin);
      }
    });
    page.on("requestfailed", (request) => {
      summary.failedRequests.push({
        method: request.method(),
        url: request.url(),
        error: request.failure()?.errorText || "unknown",
      });
    });
    page.on("pageerror", (error) => summary.pageErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") summary.consoleErrors.push(message.text());
    });
    page.on("dialog", async (dialog) => {
      summary.unexpectedDialogs.push({ type: dialog.type(), message: dialog.message() });
      await dialog.dismiss();
    });

    for (const viewport of [
      { name: "desktop-1366", width: 1366, height: 768 },
      { name: "desktop-1920", width: 1920, height: 1080 },
    ]) {
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
      await verifyModalOnlyMatrix(page, state, viewportDir);
      await verifyCardStaleTakeover(page);
      await verifyShiftStaleTakeover(page);
      summary.viewports.push(viewport);
    }

    assertEqual(summary.consoleErrors, [], "error-level browser console messages");
    assertEqual(summary.pageErrors, [], "browser page errors");
    assertEqual(summary.failedRequests, [], "failed browser requests");
    assertEqual(summary.unexpectedDialogs, [], "unexpected browser dialogs");
    const unsafeBrowserRequests = state.requests.filter(({ method, url }) => {
      const requestURL = new URL(url);
      return requestURL.origin !== baseOrigin
        || ["POST", "PUT", "PATCH", "DELETE"].includes(method)
        || requestURL.pathname.includes("pallet-summary");
    });
    assertEqual(unsafeBrowserRequests, [], "mutation-capable or pallet-summary browser requests");
    passed(`browser requests remained on ${baseOrigin}; modal-only allowance is GET /terminal/snapshot`);
    summary.status = "passed";
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
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
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
  } catch {
    // Preserve the original guard or verification failure.
  }
  console.error(error.stack || error);
  process.exitCode = 1;
});
