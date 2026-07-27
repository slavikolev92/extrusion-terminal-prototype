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
    if (fs.existsSync(current)) assert(!fs.lstatSync(current).isSymbolicLink(), message);
  }
}


const baseURL = requiredEnvironment("BASE_URL").replace(/\/+$/, "");
const fixtureInput = requiredEnvironment("FIXTURE_JSON");
const artifactInput = requiredEnvironment("ARTIFACT_DIR");
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = fs.realpathSync(path.resolve(scriptDir, ".."));
const runtimeRoot = path.resolve(repoRoot, ".test-runtime");
const artifactRoot = path.resolve(repoRoot, "artifacts", "ui-checks");
const requestedFixturePath = path.resolve(repoRoot, fixtureInput);
const artifactDir = path.resolve(repoRoot, artifactInput);

assertNoSymlinkComponents(
  repoRoot,
  runtimeRoot,
  ".test-runtime guard root must not be a symlink.",
);
assert(isStrictChild(runtimeRoot, requestedFixturePath), "FIXTURE_JSON must be under .test-runtime.");
assert(isStrictChild(artifactRoot, artifactDir), "ARTIFACT_DIR must be below artifacts/ui-checks.");
assertNoSymlinkComponents(
  repoRoot,
  artifactDir,
  "ARTIFACT_DIR guard path must not contain symlinks.",
);
assert(fs.existsSync(requestedFixturePath), `Fixture JSON does not exist: ${requestedFixturePath}`);
const fixturePath = fs.realpathSync(requestedFixturePath);
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), fixturePath),
  "FIXTURE_JSON must resolve below .test-runtime.",
);

fs.mkdirSync(artifactRoot, { recursive: true });
assertNoSymlinkComponents(
  repoRoot,
  artifactDir,
  "ARTIFACT_DIR guard path must not contain symlinks.",
);
let existingArtifactAncestor = artifactDir;
while (!fs.existsSync(existingArtifactAncestor)) {
  existingArtifactAncestor = path.dirname(existingArtifactAncestor);
}
assert(
  existingArtifactAncestor === artifactRoot
    || isStrictChild(fs.realpathSync(artifactRoot), fs.realpathSync(existingArtifactAncestor)),
  "ARTIFACT_DIR resolves outside artifacts/ui-checks.",
);
fs.mkdirSync(artifactDir, { recursive: true });
assert(
  isStrictChild(fs.realpathSync(artifactRoot), fs.realpathSync(artifactDir)),
  "ARTIFACT_DIR resolves outside artifacts/ui-checks.",
);

const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const databasePath = fs.realpathSync(path.resolve(repoRoot, fixture.db_path));
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), databasePath),
  "Fixture database must resolve below .test-runtime.",
);

const require = createRequire(import.meta.url);
const { chromium } = require("@playwright/test");
const storagePrefix = "extrusion-terminal.roll-change.v1.machine.";
const summaryPath = path.join(artifactDir, "verification-summary.json");
const viewports = [
  { width: 1920, height: 768 },
  { width: 1366, height: 768 },
];
const summary = {
  url: baseURL,
  databaseIdentity: databasePath,
  fixture: path.relative(repoRoot, fixturePath),
  viewports: [],
  assertions: [],
  consoleErrors: [],
  pageErrors: [],
  screenshots: [],
};


function passed(assertion) {
  summary.assertions.push(assertion);
}


function screenshotPath(name) {
  const target = path.join(artifactDir, name);
  summary.screenshots.push(path.relative(repoRoot, target));
  return target;
}


async function preflightDatabase(page) {
  const response = await page.goto(`${baseURL}/health`, { waitUntil: "networkidle" });
  assert(response?.ok(), `Health preflight returned HTTP ${response?.status() || "unknown"}.`);
  const health = await response.json();
  assertEqual(
    fs.realpathSync(path.resolve(health.database_path)),
    databasePath,
    "server database identity",
  );
  passed("health database identity matched guarded fixture");
}


async function seedSchedules(context) {
  await context.addInitScript(({ cards, prefix }) => {
    const schedule = ({ machineId, cardId, previousOffsetMinutes, intervalMinutes,
      nextOffsetMinutes, status, frozenRemainingMs = null, pauseNeedsResolution = false }) => ({
      schemaVersion: 1,
      machineId,
      cardId,
      previousChangeAtMs: Date.now() + previousOffsetMinutes * 60_000,
      intervalMinutes,
      nextExpectedAtMs: Date.now() + nextOffsetMinutes * 60_000,
      observedStatus: status,
      frozenRemainingMs,
      pauseNeedsResolution,
    });
    const records = [
      schedule({ machineId: 1, cardId: cards.machine_1_running, previousOffsetMinutes: -50, intervalMinutes: 60, nextOffsetMinutes: 10, status: "running" }),
      schedule({ machineId: 2, cardId: cards.machine_2_running, previousOffsetMinutes: -57, intervalMinutes: 60, nextOffsetMinutes: 3, status: "running" }),
      schedule({ machineId: 3, cardId: cards.machine_3_running, previousOffsetMinutes: -60, intervalMinutes: 60, nextOffsetMinutes: 0, status: "running" }),
      schedule({ machineId: 4, cardId: cards.machine_4_paused, previousOffsetMinutes: -60, intervalMinutes: 60, nextOffsetMinutes: 0, status: "paused", frozenRemainingMs: 0 }),
    ];
    for (const record of records) {
      localStorage.setItem(`${prefix}${record.machineId}`, JSON.stringify(record));
    }
  }, { cards: fixture.cards, prefix: storagePrefix });
}


async function navigate(page, cardId) {
  const response = await page.goto(`${baseURL}/terminal/cards/${cardId}`, { waitUntil: "networkidle" });
  assert(response?.ok(), `Terminal navigation returned HTTP ${response?.status() || "unknown"}.`);
}


async function assertRenderedCountdowns(page) {
  const expectedMachines = [
    { machineId: 1, statusClass: "running", dotColor: "rgb(31, 122, 67)", tone: "normal" },
    { machineId: 2, statusClass: "running", dotColor: "rgb(31, 122, 67)", tone: "warning" },
    { machineId: 3, statusClass: "running", dotColor: "rgb(31, 122, 67)", tone: "urgent" },
    { machineId: 4, statusClass: "paused", dotColor: "rgb(211, 155, 22)", tone: "paused" },
  ];
  for (const expected of expectedMachines) {
    const host = page.locator(`[data-roll-change-machine][data-machine-id="${expected.machineId}"]`);
    const dot = host.locator(".machine-state-dot");
    const timer = host.locator("[data-roll-change-machine-timer]");
    assert(await dot.evaluate((element, statusClass) => element.classList.contains(statusClass), expected.statusClass), `Machine ${expected.machineId} dot class is wrong.`);
    assertEqual(await dot.evaluate((element) => getComputedStyle(element).backgroundColor), expected.dotColor, `machine ${expected.machineId} dot color`);
    assert(await timer.isVisible(), `Machine ${expected.machineId} countdown is hidden.`);
    assert(await timer.evaluate((element, tone) => element.classList.contains(tone), expected.tone), `Machine ${expected.machineId} tone is wrong.`);
    assert(/^\d{2}:\d{2}$/.test(normalized(await timer.textContent())), `Machine ${expected.machineId} countdown format is wrong.`);
  }
  assertEqual(normalized(await page.locator('[data-roll-change-machine][data-machine-id="4"] [data-roll-change-machine-timer]').textContent()), "00:00", "paused due countdown");
  passed("four machine state dots and normal, warning, urgent, and paused countdowns");
}


async function assertSelectedControls(page) {
  const controls = page.locator("[data-roll-change-controls]");
  const open = controls.locator("[data-roll-change-open]");
  const quick = controls.locator("[data-roll-change-advance]");
  assert(await controls.isVisible(), "Selected running countdown controls are missing.");
  assert(/^\d{2}:\d{2}$/.test(normalized(await open.locator("[data-roll-change-control-value]").textContent())), "Selected countdown value is missing.");
  assert(normalized(await open.locator("[data-roll-change-control-next]").textContent()).startsWith("Следваща "), "Selected next-change label is missing.");
  assert(await quick.isVisible(), "One-touch roll-change action is hidden.");
  assertEqual(await quick.getAttribute("aria-label"), "Потвърди смяна на ролките", "quick action accessible label");
  assertEqual(await page.locator("[data-roll-secondary-actions] [data-roll-change-open]").count(), 0, "old roll-panel countdown action count");
  passed("selected countdown controls and exact one-touch accessible label");
}


async function assertInactiveFollowUpHasNoOwnership(page) {
  await navigate(page, fixture.cards.machine_1_follow_up);
  assertEqual(await page.locator("[data-roll-change-controls]").count(), 0, "inactive follow-up selected controls");
  assertEqual(await page.locator(`[data-roll-change-machine][data-card-id="${fixture.cards.machine_1_follow_up}"] [data-roll-change-machine-timer]:not([hidden])`).count(), 0, "inactive follow-up timer ownership");
  passed("inactive follow-up card owns no countdown surface");
}


async function assertDraftAndSave(page) {
  await navigate(page, fixture.cards.machine_1_running);
  const storageBefore = await page.evaluate((key) => localStorage.getItem(key), `${storagePrefix}1`);
  const open = page.locator("[data-roll-change-open]");
  await open.click();
  const overlay = page.locator("[data-roll-change-overlay]");
  assert(await overlay.isVisible(), "Editor did not open.");
  assertEqual(await overlay.getAttribute("aria-hidden"), "false", "editor aria-hidden while open");
  assertEqual(await open.getAttribute("aria-expanded"), "true", "editor trigger aria-expanded");
  assertEqual(await page.evaluate(() => document.activeElement?.hasAttribute("data-roll-change-previous")), true, "editor initial focus");
  await page.locator("[data-roll-change-hours]").fill("2");
  await page.locator("[data-roll-change-cancel]").click();
  assertEqual(await page.evaluate((key) => localStorage.getItem(key), `${storagePrefix}1`), storageBefore, "cancelled draft storage");
  assertEqual(await page.evaluate(() => document.activeElement?.hasAttribute("data-roll-change-open")), true, "focus restored after cancel");

  await open.click();
  await page.locator("[data-roll-change-hours]").fill("1");
  await page.locator("[data-roll-change-minutes]").fill("30");
  const calculatedNext = await page.locator("[data-roll-change-next]").inputValue();
  assert(Boolean(calculatedNext), "Draft recalculation did not populate the next change.");
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  assert(await overlay.isHidden(), "Valid editor save did not close the dialog.");
  const saved = await page.evaluate((key) => JSON.parse(localStorage.getItem(key)), `${storagePrefix}1`);
  assertEqual(saved.intervalMinutes, 90, "saved draft interval");
  passed("editor cancel remains a draft and valid save persists once");
}


async function assertDirtyCorrectionGuard(page) {
  await navigate(page, fixture.cards.machine_1_running);
  const key = `${storagePrefix}1`;
  const storageBefore = await page.evaluate((storageKey) => localStorage.getItem(storageKey), key);
  await page.locator(".roll-row[data-roll-id]").first().locator("[data-roll-edit-open]").click();
  await page.locator("[data-roll-change-open]").click();
  assert(await page.locator("[data-roll-change-overlay]").isHidden(), "Roll correction allowed the countdown editor to open.");
  await page.locator("[data-roll-change-advance]").click();
  assertEqual(await page.evaluate((storageKey) => localStorage.getItem(storageKey), key), storageBefore, "roll-correction countdown storage");
  await page.locator("[data-roll-actions-for]:visible [data-roll-row-cancel]").click();
  passed("active roll correction keeps countdown actions inert");
}


async function assertStorageSyncAndAdvance(context, page, mutationRequests) {
  const peer = await context.newPage();
  peer.on("pageerror", (error) => summary.pageErrors.push(error.message));
  peer.on("console", (message) => {
    if (message.type() === "error") summary.consoleErrors.push(message.text());
  });
  peer.on("request", (request) => {
    if (!["GET", "HEAD"].includes(request.method())) {
      mutationRequests.push(`${request.method()} ${request.url()}`);
    }
  });
  await navigate(peer, fixture.cards.machine_1_running);
  await page.evaluate(({ key }) => {
    localStorage.setItem(key, JSON.stringify({
      schemaVersion: 1,
      machineId: 99,
      cardId: 99,
      previousChangeAtMs: Date.now() - 60_000,
      intervalMinutes: 30,
      nextExpectedAtMs: Date.now() + 29 * 60_000,
      observedStatus: "running",
      frozenRemainingMs: null,
      pauseNeedsResolution: false,
    }));
  }, { key: `${storagePrefix}99` });
  await peer.waitForFunction(
    (key) => localStorage.getItem(key) === null,
    `${storagePrefix}99`,
    { timeout: 1_000 },
  );
  passed("same-origin cleanup removed an unknown machine schedule");

  const replacement = await page.evaluate(({ key, cardId }) => {
    const current = JSON.parse(localStorage.getItem(key));
    const replacementRecord = {
      ...current,
      cardId,
      previousChangeAtMs: Date.now() - 20 * 60_000,
      intervalMinutes: 30,
      nextExpectedAtMs: Date.now() + 10 * 60_000,
      observedStatus: "running",
      frozenRemainingMs: null,
      pauseNeedsResolution: false,
    };
    localStorage.setItem(key, JSON.stringify(replacementRecord));
    return replacementRecord;
  }, { key: `${storagePrefix}1`, cardId: fixture.cards.machine_1_running });
  await peer.locator("[data-roll-change-control-value]").filter({ hasText: /^00:10$/ }).waitFor({ state: "visible" });
  passed("same-origin storage event rerendered the peer tab without reload");

  const beforeAdvance = await peer.evaluate((key) => JSON.parse(localStorage.getItem(key)), `${storagePrefix}1`);
  await peer.locator("[data-roll-change-advance]").click();
  const afterAdvance = await peer.evaluate((key) => JSON.parse(localStorage.getItem(key)), `${storagePrefix}1`);
  assertEqual(afterAdvance.previousChangeAtMs, beforeAdvance.nextExpectedAtMs, "acknowledgement previous anchor");
  assertEqual(afterAdvance.nextExpectedAtMs, beforeAdvance.nextExpectedAtMs + 30 * 60_000, "acknowledgement next anchor");
  assertEqual(afterAdvance.intervalMinutes, replacement.intervalMinutes, "acknowledgement interval preservation");
  assertEqual(mutationRequests, [], "countdown mutation requests");
  passed("one-touch acknowledgement advanced from the expected anchor without a server write");
  await peer.close();
}


async function captureViewport(page, viewport) {
  await page.setViewportSize(viewport);
  await navigate(page, fixture.cards.machine_1_running);
  const target = screenshotPath(`roll-change-countdown-${viewport.width}x${viewport.height}.png`);
  await page.screenshot({ path: target, fullPage: true });
  assert(fs.existsSync(target) && fs.statSync(target).size > 0, `Missing screenshot ${target}.`);
  summary.viewports.push({ ...viewport, status: "passed" });
}


async function main() {
  let browser;
  try {
    browser = await chromium.launch();
    const context = await browser.newContext({ viewport: viewports[0] });
    await seedSchedules(context);
    const page = await context.newPage();
    const mutationRequests = [];
    page.on("pageerror", (error) => summary.pageErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") summary.consoleErrors.push(message.text());
    });
    page.on("request", (request) => {
      if (!['GET', 'HEAD'].includes(request.method())) mutationRequests.push(`${request.method()} ${request.url()}`);
    });

    await preflightDatabase(page);
    await navigate(page, fixture.cards.machine_1_running);
    await assertRenderedCountdowns(page);
    await assertSelectedControls(page);
    await assertInactiveFollowUpHasNoOwnership(page);
    await assertDirtyCorrectionGuard(page);
    await assertDraftAndSave(page);
    await assertStorageSyncAndAdvance(context, page, mutationRequests);
    for (const viewport of viewports) await captureViewport(page, viewport);

    assertEqual(summary.consoleErrors, [], "error-level browser console messages");
    assertEqual(summary.pageErrors, [], "browser page errors");
    summary.status = "passed";
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
    console.log("Roll-change countdown workflow verification passed.");
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
    // Preserve the original validation failure.
  }
  console.error(error.stack || error);
  process.exitCode = 1;
});
