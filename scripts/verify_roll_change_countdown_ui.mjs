import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
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


async function preflightDatabase() {
  const response = await fetch(`${baseURL}/health`);
  assert(response.ok, `Health preflight returned HTTP ${response.status || "unknown"}.`);
  const health = await response.json();
  assertEqual(
    fs.realpathSync(path.resolve(health.database_path)),
    databasePath,
    "server database identity",
  );
  passed("health database identity matched guarded fixture");
}


function resetFixture() {
  const result = spawnSync(
    path.join(repoRoot, ".venv", "bin", "python"),
    [
      path.join(repoRoot, "scripts", "create_roll_change_countdown_fixture.py"),
      "--db-path", databasePath,
      "--output", fixturePath,
    ],
    { cwd: repoRoot, encoding: "utf8" },
  );
  assert(
    result.status === 0,
    `Fixture reset failed: ${normalized(result.stderr) || normalized(result.stdout)}`,
  );
  const resetFixturePayload = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  assertEqual(
    fs.realpathSync(path.resolve(repoRoot, resetFixturePayload.db_path)),
    databasePath,
    "reset fixture database identity",
  );
  assertEqual(resetFixturePayload.cards, fixture.cards, "reset fixture card identities");
  passed("deterministic fixture reset preserved database and card identities");
}


async function navigate(page, cardId) {
  const response = await page.goto(`${baseURL}/terminal/cards/${cardId}`, { waitUntil: "networkidle" });
  assert(response?.ok(), `Terminal navigation returned HTTP ${response?.status() || "unknown"}.`);
}


function storageKey(machineId) {
  return `${storagePrefix}${machineId}`;
}


function schedule({ machineId, cardId, previousChangeAtMs, intervalMinutes,
  nextExpectedAtMs, status, frozenRemainingMs = null, pauseNeedsResolution = false }) {
  return {
    schemaVersion: 1,
    machineId,
    cardId,
    previousChangeAtMs,
    intervalMinutes,
    nextExpectedAtMs,
    observedStatus: status,
    frozenRemainingMs,
    pauseNeedsResolution,
  };
}


function localMinuteValue(timestamp) {
  const value = new Date(timestamp);
  const pad = (number) => String(number).padStart(2, "0");
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
}


async function readSchedule(page, machineId) {
  return page.evaluate((key) => {
    const raw = localStorage.getItem(key);
    return raw === null ? null : JSON.parse(raw);
  }, storageKey(machineId));
}


async function rawSchedule(page, machineId) {
  return page.evaluate((key) => localStorage.getItem(key), storageKey(machineId));
}


async function writeSchedule(page, record, dispatch = true) {
  await page.evaluate(({ key, value, shouldDispatch }) => {
    const oldValue = localStorage.getItem(key);
    const newValue = JSON.stringify(value);
    localStorage.setItem(key, newValue);
    if (shouldDispatch) {
      window.dispatchEvent(new StorageEvent("storage", {
        key,
        oldValue,
        newValue,
        storageArea: localStorage,
        url: window.location.href,
      }));
    }
  }, { key: storageKey(record.machineId), value: record, shouldDispatch: dispatch });
}


async function removeSchedule(page, machineId, dispatch = true) {
  await page.evaluate(({ key, shouldDispatch }) => {
    const oldValue = localStorage.getItem(key);
    localStorage.removeItem(key);
    if (shouldDispatch) {
      window.dispatchEvent(new StorageEvent("storage", {
        key,
        oldValue,
        newValue: null,
        storageArea: localStorage,
        url: window.location.href,
      }));
    }
  }, { key: storageKey(machineId), shouldDispatch: dispatch });
}


function instrumentPage(page, mutationRequests) {
  page.on("pageerror", (error) => summary.pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") summary.consoleErrors.push(message.text());
  });
  page.on("request", (request) => {
    if (!["GET", "HEAD"].includes(request.method())) {
      mutationRequests.push(`${request.method()} ${request.url()}`);
    }
  });
  page.on("dialog", async (dialog) => {
    summary.pageErrors.push(`Unexpected native dialog: ${dialog.message()}`);
    await dialog.dismiss();
  });
}


async function seedSchedules(page) {
  await navigate(page, fixture.cards.machine_1_running);
  const now = Date.now();
  const records = [
    schedule({ machineId: 1, cardId: fixture.cards.machine_1_running, previousChangeAtMs: now - 50 * 60_000, intervalMinutes: 60, nextExpectedAtMs: now + 10 * 60_000, status: "running" }),
    schedule({ machineId: 2, cardId: fixture.cards.machine_2_running, previousChangeAtMs: now - 57 * 60_000, intervalMinutes: 60, nextExpectedAtMs: now + 3 * 60_000, status: "running" }),
    schedule({ machineId: 3, cardId: fixture.cards.machine_3_running, previousChangeAtMs: now - 60 * 60_000, intervalMinutes: 60, nextExpectedAtMs: now - 1_000, status: "running" }),
    schedule({ machineId: 4, cardId: fixture.cards.machine_4_paused, previousChangeAtMs: now - 60 * 60_000, intervalMinutes: 60, nextExpectedAtMs: now - 1_000, status: "paused", frozenRemainingMs: 0, pauseNeedsResolution: true }),
  ];
  await page.evaluate(({ prefix, values }) => {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith(prefix)) localStorage.removeItem(key);
    }
    for (const value of values) {
      localStorage.setItem(`${prefix}${value.machineId}`, JSON.stringify(value));
    }
  }, { prefix: storagePrefix, values: records });
  await navigate(page, fixture.cards.machine_1_running);
}


function databaseSnapshot() {
  const program = String.raw`
import json, sqlite3, sys
database_path = sys.argv[1]
card_ids = json.loads(sys.argv[2])
connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
connection.row_factory = sqlite3.Row
placeholders = ",".join("?" for _ in card_ids)
def rows(query, parameters=()):
    return [dict(row) for row in connection.execute(query, parameters).fetchall()]
payload = {
    "cards": rows(f"SELECT * FROM cards WHERE id IN ({placeholders}) ORDER BY id", card_ids),
    "imports": rows(f"SELECT * FROM card_import_sources WHERE card_id IN ({placeholders}) ORDER BY card_id", card_ids),
    "rolls": rows(f"SELECT * FROM roll_entries WHERE card_id IN ({placeholders}) ORDER BY card_id, id", card_ids),
    "timing": rows(f"SELECT * FROM production_time_segments WHERE card_id IN ({placeholders}) ORDER BY card_id, id", card_ids),
    "recipe": rows(f"SELECT * FROM recipe_components WHERE card_id IN ({placeholders}) ORDER BY card_id, id", card_ids),
    "recipe_actuals": rows(f"SELECT * FROM recipe_actual_entries WHERE card_id IN ({placeholders}) ORDER BY card_id, id", card_ids),
    "shifts": rows("SELECT * FROM shift_occurrences ORDER BY id"),
    "configuration": rows("SELECT * FROM terminal_configuration ORDER BY id"),
}
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
`;
  const result = spawnSync(
    path.join(repoRoot, ".venv", "bin", "python"),
    ["-c", program, databasePath, JSON.stringify(Object.values(fixture.cards))],
    { cwd: repoRoot, encoding: "utf8" },
  );
  assert(result.status === 0, `Read-only database snapshot failed: ${normalized(result.stderr)}`);
  return JSON.parse(result.stdout);
}


async function machineGeometry(page) {
  return page.locator("[data-roll-change-machine]").evaluateAll((hosts) => hosts.map((host) => {
    const rectangle = host.getBoundingClientRect();
    return {
      x: rectangle.x,
      y: rectangle.y,
      width: rectangle.width,
      height: rectangle.height,
    };
  }));
}


async function assertLayoutAndInactiveState(page, viewport) {
  await removeSchedule(page, 1);
  const open = page.locator("[data-roll-change-open]");
  const quick = page.locator("[data-roll-change-advance]");
  assertEqual(normalized(await page.locator("[data-roll-change-control-value]").textContent()), "Смяна на ролка", "inactive selected control label");
  assert(await quick.isHidden(), "Inactive selected card exposed the quick action.");
  const inactiveGeometry = await machineGeometry(page);

  const now = Date.now();
  await writeSchedule(page, schedule({
    machineId: 1,
    cardId: fixture.cards.machine_1_running,
    previousChangeAtMs: now - 20 * 60_000,
    intervalMinutes: 30,
    nextExpectedAtMs: now + 10 * 60_000,
    status: "running",
  }));
  await quick.waitFor({ state: "visible" });
  assertEqual(await machineGeometry(page), inactiveGeometry, "machine geometry after timer activation");

  const measurements = await page.locator("[data-roll-change-machine]").evaluateAll((hosts) => {
    const box = (element) => {
      const value = element.getBoundingClientRect();
      return { left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height };
    };
    return hosts.map((host) => ({
      host: box(host),
      dot: box(host.querySelector(".machine-state-dot")),
      timer: host.querySelector("[data-roll-change-machine-timer]:not([hidden])") ? box(host.querySelector("[data-roll-change-machine-timer]")) : null,
      customer: box(host.querySelector(".machine-tab-customer")),
      product: box(host.querySelector(".machine-tab-product")),
      progress: box(host.querySelector(".progress")),
      quantity: box(host.querySelector(".machine-tab-qty")),
    }));
  });
  const overlaps = (left, right) => (
    left.left < right.right && left.right > right.left
    && left.top < right.bottom && left.bottom > right.top
  );
  for (const [index, measurement] of measurements.entries()) {
    for (const [name, child] of Object.entries(measurement)) {
      if (name === "host" || child === null) continue;
      assert(child.left >= measurement.host.left - 1 && child.right <= measurement.host.right + 1, `Machine ${index + 1} ${name} clips horizontally.`);
      assert(child.top >= measurement.host.top - 1 && child.bottom <= measurement.host.bottom + 1, `Machine ${index + 1} ${name} clips vertically.`);
    }
    if (measurement.timer) assert(!overlaps(measurement.dot, measurement.timer), `Machine ${index + 1} dot overlaps timer.`);
    assert(!overlaps(measurement.customer, measurement.product), `Machine ${index + 1} customer overlaps product.`);
    assert(!overlaps(measurement.progress, measurement.quantity), `Machine ${index + 1} progress overlaps quantity.`);
  }

  const lifecycleBoxes = await page.locator("[data-lifecycle-slot] .action-button, button[data-lifecycle-slot]").evaluateAll((buttons) => buttons.map((button) => {
    const box = button.getBoundingClientRect();
    return { width: box.width, height: box.height };
  }));
  assertEqual(lifecycleBoxes.length, 3, "lifecycle control count");
  assert(lifecycleBoxes.every((box) => box.width === lifecycleBoxes[0].width && box.height === lifecycleBoxes[0].height), "Lifecycle controls do not retain equal dimensions.");
  assert(lifecycleBoxes.every((box) => box.width >= 140 && box.height >= 38), "Lifecycle controls lost their usable hit areas.");
  const topbarSpacing = await page.evaluate(() => {
    const finish = document.querySelector("[data-lifecycle-slot='finish'] .action-button, button[data-lifecycle-slot='finish']").getBoundingClientRect();
    const timer = document.querySelector("[data-roll-change-controls]").getBoundingClientRect();
    return timer.left - finish.right;
  });
  assert(topbarSpacing >= 12, `Timer group is not visibly separated (${topbarSpacing}px).`);
  for (const [label, locator] of [["editor", open], ["quick", quick]]) {
    const box = await locator.boundingBox();
    assert(box && box.width >= 38 && box.height >= 38, `${label} control has an unusable hit area.`);
  }
  assertEqual(await page.locator("a.machine-tab button").count(), 0, "buttons nested in machine links");

  await page.locator("body").click({ position: { x: 4, y: 4 } });
  for (let index = 0; index < 40; index += 1) {
    if (await page.evaluate(() => document.activeElement?.hasAttribute("data-roll-change-open"))) break;
    await page.keyboard.press("Tab");
  }
  assert(await page.evaluate(() => document.activeElement?.hasAttribute("data-roll-change-open")), "Keyboard focus did not reach the editor control.");
  assert(await open.evaluate((element) => {
    const style = getComputedStyle(element);
    return style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth) > 0;
  }), "Editor control lacks visible keyboard focus.");
  await page.keyboard.press("Tab");
  assert(await page.evaluate(() => document.activeElement?.hasAttribute("data-roll-change-advance")), "Keyboard focus did not reach the quick action.");
  assert(await quick.evaluate((element) => {
    const style = getComputedStyle(element);
    return style.outlineStyle !== "none" && Number.parseFloat(style.outlineWidth) > 0;
  }), "Quick action lacks visible keyboard focus.");
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), "Document has horizontal overflow.");

  const target = screenshotPath(`roll-change-${viewport.width}x${viewport.height}.png`);
  await page.screenshot({ path: target, fullPage: true });
  assert(fs.existsSync(target) && fs.statSync(target).size > 0, `Missing screenshot ${target}.`);
  passed(`${viewport.width}x${viewport.height}: stable geometry, non-overlap, hit areas, focus, and overflow`);
}


async function assertEditorAndScheduleMath(page, viewport) {
  const open = page.locator("[data-roll-change-open]");
  const overlay = page.locator("[data-roll-change-overlay]");
  const key = storageKey(1);
  const validRaw = await rawSchedule(page, 1);
  await open.click();
  assertEqual(await rawSchedule(page, 1), validRaw, "editor-open storage bytes");
  assert(await overlay.isVisible(), "Editor did not open.");
  assert(await page.evaluate(() => document.activeElement?.hasAttribute("data-roll-change-previous")), "Editor did not focus its first field.");
  const modalGeometry = await page.locator("[data-roll-change-dialog]").evaluate((dialog) => {
    const box = dialog.getBoundingClientRect();
    return {
      centeredX: Math.abs((box.left + box.width / 2) - window.innerWidth / 2),
      centeredY: Math.abs((box.top + box.height / 2) - window.innerHeight / 2),
      contained: box.left >= 0 && box.top >= 0 && box.right <= window.innerWidth && box.bottom <= window.innerHeight,
    };
  });
  assert(modalGeometry.centeredX <= 2 && modalGeometry.centeredY <= 2 && modalGeometry.contained, "Editor modal is not centered and contained.");

  await page.locator("[data-roll-change-next]").focus();
  await page.locator("[data-roll-change-form] button[type='submit']").press("Tab");
  assert(await page.evaluate(() => document.activeElement?.hasAttribute("data-roll-change-previous")), "Editor focus escaped after the last action.");
  await page.keyboard.press("Shift+Tab");
  assert(await page.evaluate(() => document.activeElement?.matches("[data-roll-change-form] button[type='submit']")), "Editor reverse focus trap failed.");

  await page.locator("[data-roll-change-hours]").fill("0");
  await page.locator("[data-roll-change-minutes]").fill("0");
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  assert(await overlay.isVisible(), "Zero interval closed the editor.");
  assertEqual(normalized(await page.locator('[data-roll-change-error-for="form"]').textContent()), "Изберете интервал поне 1 минута.", "zero interval error");
  assertEqual(await rawSchedule(page, 1), validRaw, "zero interval preserved record");
  if (viewport.width === 1920) {
    const target = screenshotPath("editor-validation.png");
    await page.screenshot({ path: target, fullPage: true });
  }

  await page.locator("[data-roll-change-hours]").fill("24");
  await page.locator("[data-roll-change-minutes]").fill("30");
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  assertEqual(normalized(await page.locator('[data-roll-change-error-for="hours"]').textContent()), "Часовете трябва да са цяло число от 0 до 23.", "hours bounds error");
  await page.locator("[data-roll-change-hours]").fill("0");
  await page.locator("[data-roll-change-minutes]").fill("60");
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  assertEqual(normalized(await page.locator('[data-roll-change-error-for="minutes"]').textContent()), "Минутите трябва да са цяло число от 0 до 59.", "minutes bounds error");

  const minute = Math.floor(Date.now() / 60_000) * 60_000;
  const previous = minute - 60 * 60_000;
  await page.locator("[data-roll-change-previous]").fill(localMinuteValue(previous));
  await page.locator("[data-roll-change-hours]").fill("0");
  await page.locator("[data-roll-change-minutes]").fill("30");
  assertEqual(await page.locator("[data-roll-change-next]").inputValue(), localMinuteValue(previous + 30 * 60_000), "previous/interval draft recalculation");
  await page.locator("[data-roll-change-next]").fill(localMinuteValue(previous));
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  assertEqual(normalized(await page.locator('[data-roll-change-error-for="next"]').textContent()), "Следващата смяна трябва да е след предишната.", "reversed next-time error");
  assertEqual(await rawSchedule(page, 1), validRaw, "reversed next preserved record");

  const directNext = minute - 10 * 60_000;
  await page.locator("[data-roll-change-next]").fill(localMinuteValue(directNext));
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  assert(await overlay.isHidden(), "Valid direct next-time save did not close.");
  const directSaved = await readSchedule(page, 1);
  assertEqual(directSaved.previousChangeAtMs, previous, "direct save previous timestamp");
  assertEqual(directSaved.intervalMinutes, 30, "direct save interval");
  assertEqual(directSaved.nextExpectedAtMs, directNext, "direct next-time anchor");

  await page.locator("[data-roll-change-advance]").click();
  const late = await readSchedule(page, 1);
  assertEqual(late.previousChangeAtMs, directNext, "late acknowledgement previous anchor");
  assertEqual(late.nextExpectedAtMs, directNext + 30 * 60_000, "late acknowledgement next anchor");
  await page.locator("[data-roll-change-advance]").click();
  const early = await readSchedule(page, 1);
  assertEqual(early.previousChangeAtMs, late.nextExpectedAtMs, "early acknowledgement previous anchor");
  assertEqual(early.nextExpectedAtMs, late.nextExpectedAtMs + 30 * 60_000, "early acknowledgement next anchor");

  for (const closeMethod of ["cancel", "escape", "backdrop"]) {
    const before = await rawSchedule(page, 1);
    await open.click();
    await page.locator("[data-roll-change-hours]").fill("2");
    if (closeMethod === "cancel") await page.locator("[data-roll-change-cancel]").click();
    if (closeMethod === "escape") await page.keyboard.press("Escape");
    if (closeMethod === "backdrop") await overlay.click({ position: { x: 2, y: 2 } });
    assertEqual(await rawSchedule(page, 1), before, `${closeMethod} storage bytes`);
    assert(await page.evaluate(() => document.activeElement?.hasAttribute("data-roll-change-open")), `${closeMethod} did not restore focus.`);
  }

  const restartBefore = await rawSchedule(page, 1);
  await open.click();
  const restartStarted = Date.now();
  await page.locator("[data-roll-change-restart]").click();
  const restartPrevious = await page.locator("[data-roll-change-previous]").inputValue();
  assert([localMinuteValue(restartStarted), localMinuteValue(Date.now())].includes(restartPrevious), "Restart did not use the current minute.");
  const restartPreviousMs = new Date(restartPrevious).getTime();
  assertEqual(await page.locator("[data-roll-change-next]").inputValue(), localMinuteValue(restartPreviousMs + early.intervalMinutes * 60_000), "restart draft next timestamp");
  await page.locator("[data-roll-change-cancel]").click();
  assertEqual(await rawSchedule(page, 1), restartBefore, "restart then cancel storage bytes");

  const machineTwoRaw = await rawSchedule(page, 2);
  await open.click();
  await page.locator("[data-roll-change-clear]").click();
  assertEqual(await rawSchedule(page, 1), null, "clear machine one key");
  assertEqual(await rawSchedule(page, 2), machineTwoRaw, "clear unrelated machine key");
  assert(await page.locator("[data-roll-change-advance]").isHidden(), "Clear left quick action visible.");
  assert(await page.locator('[data-machine-id="1"] [data-roll-change-machine-timer]').isHidden(), "Clear left machine timer visible.");

  await open.click();
  const rehydratePrevious = minute - 5 * 60_000;
  const rehydrateNext = minute + 25 * 60_000;
  await page.locator("[data-roll-change-previous]").fill(localMinuteValue(rehydratePrevious));
  await page.locator("[data-roll-change-hours]").fill("0");
  await page.locator("[data-roll-change-minutes]").fill("30");
  await page.locator("[data-roll-change-next]").fill(localMinuteValue(rehydrateNext));
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  const rehydrateRaw = await rawSchedule(page, 1);
  await page.reload({ waitUntil: "networkidle" });
  assertEqual(await rawSchedule(page, 1), rehydrateRaw, "refresh rehydration bytes");
  assert(await page.locator("[data-roll-change-advance]").isVisible(), "Refresh did not rehydrate quick action.");
  passed(`${viewport.width}x${viewport.height}: editor validation, exact anchors, cancellation, restart, clear, and refresh`);
}


async function assertStorageEventsDueAndCorrection(context, page, mutationRequests, viewport) {
  const peer = await context.newPage();
  instrumentPage(peer, mutationRequests);
  await navigate(peer, fixture.cards.machine_1_running);
  const reopened = await readSchedule(peer, 1);
  assertEqual(reopened, await readSchedule(page, 1), "new-page schedule rehydration");

  const now = Date.now();
  const replacement = schedule({
    machineId: 1,
    cardId: fixture.cards.machine_1_running,
    previousChangeAtMs: now - 20 * 60_000,
    intervalMinutes: 30,
    nextExpectedAtMs: now + 10 * 60_000,
    status: "running",
  });
  await writeSchedule(peer, replacement, false);
  await page.waitForFunction(({ key, expected }) => localStorage.getItem(key) === JSON.stringify(expected), { key: storageKey(1), expected: replacement });
  assert(await page.locator("[data-roll-change-advance]").isVisible(), "Native storage save did not update peer UI.");

  await page.locator("[data-roll-change-advance]").click();
  const acknowledged = await readSchedule(page, 1);
  await peer.waitForFunction(({ key, expected }) => localStorage.getItem(key) === JSON.stringify(expected), { key: storageKey(1), expected: acknowledged });
  assertEqual(acknowledged.previousChangeAtMs, replacement.nextExpectedAtMs, "cross-tab acknowledgement previous");
  assertEqual(acknowledged.nextExpectedAtMs, replacement.nextExpectedAtMs + 30 * 60_000, "cross-tab acknowledgement next");

  await page.locator("[data-roll-change-open]").click();
  const correctedNext = Math.floor((Date.now() + 12 * 60_000) / 60_000) * 60_000;
  await page.locator("[data-roll-change-next]").fill(localMinuteValue(correctedNext));
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  const corrected = await readSchedule(page, 1);
  assertEqual(corrected.nextExpectedAtMs, correctedNext, "corrected direct next anchor");
  await peer.waitForFunction(({ key, expected }) => localStorage.getItem(key) === JSON.stringify(expected), { key: storageKey(1), expected: corrected });
  await page.locator("[data-roll-change-advance]").click();
  const afterCorrection = await readSchedule(page, 1);
  assertEqual(afterCorrection.previousChangeAtMs, correctedNext, "corrected acknowledgement previous");
  assertEqual(afterCorrection.nextExpectedAtMs, correctedNext + corrected.intervalMinutes * 60_000, "corrected acknowledgement next");

  const due = schedule({
    machineId: 1,
    cardId: fixture.cards.machine_1_running,
    previousChangeAtMs: now - 31 * 60_000,
    intervalMinutes: 30,
    nextExpectedAtMs: now - 1_000,
    status: "running",
  });
  await writeSchedule(peer, due, false);
  const selectedTimer = page.locator("[data-roll-change-control-value]");
  await selectedTimer.filter({ hasText: "00:00" }).waitFor({ state: "visible" });
  assert(await page.locator('[data-machine-id="1"] [data-roll-change-machine-timer]').evaluate((element) => element.classList.contains("urgent")), "Due timer is not red/urgent.");
  const dueRaw = await rawSchedule(page, 1);
  await page.waitForTimeout(2_200);
  assertEqual(normalized(await selectedTimer.textContent()), "00:00", "due timer after display ticks");
  assertEqual(await rawSchedule(page, 1), dueRaw, "due timer did not self-advance");
  await peer.close();
  passed(`${viewport.width}x${viewport.height}: refresh/reopen, native storage events, due hold, and correction anchors`);
}


async function assertInvalidStorageCleanup(page, viewport) {
  const base = schedule({
    machineId: 1,
    cardId: fixture.cards.machine_1_running,
    previousChangeAtMs: Date.now() - 60_000,
    intervalMinutes: 30,
    nextExpectedAtMs: Date.now() + 29 * 60_000,
    status: "running",
  });
  const cases = [
    ["wrong card", JSON.stringify({ ...base, cardId: 999_999 })],
    ["unsupported version", JSON.stringify({ ...base, schemaVersion: 2 })],
    ["malformed", "{not-json"],
    ["waiting", JSON.stringify({ ...base, observedStatus: "awaiting_rewinding" })],
    ["completed", JSON.stringify({ ...base, observedStatus: "completed" })],
    ["archived", JSON.stringify({ ...base, observedStatus: "archived" })],
    ["cancelled", JSON.stringify({ ...base, observedStatus: "cancelled" })],
  ];
  for (const [label, raw] of cases) {
    await page.evaluate(({ key, value }) => localStorage.setItem(key, value), { key: storageKey(1), value: raw });
    await page.reload({ waitUntil: "networkidle" });
    assertEqual(await rawSchedule(page, 1), null, `${label} cleanup`);
  }
  await page.evaluate(({ key, value }) => localStorage.setItem(key, value), {
    key: storageKey(99),
    value: JSON.stringify({ ...base, machineId: 99, cardId: 99 }),
  });
  await page.reload({ waitUntil: "networkidle" });
  assertEqual(await rawSchedule(page, 99), null, "unknown-machine cleanup");
  passed(`${viewport.width}x${viewport.height}: malformed, mismatched, unsupported, and ended-status cleanup`);
}


async function assertTerminalRegressionSurfaces(page, viewport) {
  await navigate(page, fixture.cards.machine_1_running);
  const now = Date.now();
  await writeSchedule(page, schedule({ machineId: 1, cardId: fixture.cards.machine_1_running, previousChangeAtMs: now - 20 * 60_000, intervalMinutes: 30, nextExpectedAtMs: now + 10 * 60_000, status: "running" }));

  for (const [openSelector, surfaceSelector, closeSelector, openClass] of [
    ["#queue-open", "#queue-overlay", "#queue-close", "open"],
    ["#history-open", "#history-overlay", "#history-close", "open"],
  ]) {
    await page.locator(openSelector).click();
    assert(await page.locator(surfaceSelector).evaluate((element, className) => element.classList.contains(className), openClass), `${surfaceSelector} did not open.`);
    await page.locator(closeSelector).click();
    assert(!await page.locator(surfaceSelector).evaluate((element, className) => element.classList.contains(className), openClass), `${surfaceSelector} did not close.`);
  }
  await page.locator("#waiting-open").click();
  assert(await page.locator("#waiting-overlay").isVisible(), "Waiting window did not open.");
  await page.locator("#waiting-close").click();
  assert(await page.locator("#waiting-overlay").isHidden(), "Waiting window did not close.");
  await page.locator("#shift-open").click();
  assert(await page.locator('[data-shift-window="true"]').isVisible(), "Shift window did not open.");
  await page.locator("[data-shift-close]").click();
  assert(await page.locator('[data-shift-window="true"]').isHidden(), "Shift window did not close.");

  await page.locator("[data-rewinding-open]").click();
  assert(await page.locator("[data-rewinding-overlay]").isVisible(), "Rewinding dialog did not open.");
  assert(await page.evaluate(() => document.activeElement?.hasAttribute("data-rewinding-input")), "Rewinding input did not receive focus.");
  await page.locator("[data-rewinding-input]").fill("12");
  await page.locator("[data-rewinding-cancel]").click();
  assert(await page.locator("[data-rewinding-overlay]").isHidden(), "Rewinding dialog did not close.");
  assertEqual(await page.locator("[data-rewinding-input]").inputValue(), "", "rewinding cancel reset");

  const row = page.locator(".roll-row[data-roll-id]").first();
  await row.locator("[data-roll-edit-open]").click();
  await row.locator("[data-roll-correction-input]").first().fill("26.00");
  const originalUrl = page.url();
  await page.locator(".machine-tab").nth(1).click({ force: true });
  assertEqual(page.url(), originalUrl, "dirty correction navigation block");
  assertEqual(await page.locator(".machine-tab[aria-disabled='true']").count(), 4, "correction link lock count");
  const correctionStorage = await rawSchedule(page, 1);
  assert(await page.locator("[data-roll-change-open]").isDisabled(), "Correction did not visibly lock the countdown editor control.");
  assert(await page.locator("[data-roll-change-advance]").isDisabled(), "Correction did not visibly lock the countdown quick action.");
  assert(await page.locator("[data-roll-change-overlay]").isHidden(), "Correction left the countdown editor open.");
  assertEqual(await rawSchedule(page, 1), correctionStorage, "correction quick-action storage");
  await page.locator("[data-roll-actions-for]:visible [data-roll-row-cancel]").click();
  assertEqual(await page.locator(".machine-tab[aria-disabled='true']").count(), 0, "correction link unlock count");

  const addRoll = page.locator(".add-roll-form input[name='gross_weight']");
  await addRoll.fill("27.25");
  assertEqual(await addRoll.inputValue(), "27.25", "roll-add entry");
  await addRoll.fill("");
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), "Regression surfaces introduced horizontal overflow.");
  passed(`${viewport.width}x${viewport.height}: queue, waiting, produced, shift, rewinding, roll correction, roll entry, and dirty navigation`);
}


async function submitFormAndWait(page, selector) {
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    page.locator(selector).evaluate((form) => form.requestSubmit()),
  ]);
}


async function assertDirtyAutosaveAndConflict(context, page, viewport) {
  await navigate(page, fixture.cards.machine_1_running);
  const storageBefore = await rawSchedule(page, 1);
  const tareForm = page.locator(".roll-defaults-form");
  await tareForm.locator("input[name='tare_weight']").fill("1.20");
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    page.locator("#queue-open").click(),
  ]);
  assert(!await page.locator("#queue-overlay").evaluate((element) => element.classList.contains("open")), "Dirty autosave opened queue before persisting.");
  assertEqual(await rawSchedule(page, 1), storageBefore, "dirty autosave countdown preservation");

  const rollCountBefore = await page.locator(".roll-row[data-roll-id]").count();
  await page.locator(".add-roll-form input[name='gross_weight']").fill("27.25");
  await submitFormAndWait(page, ".add-roll-form");
  assertEqual(await page.locator(".roll-row[data-roll-id]").count(), rollCountBefore + 1, "real roll-add regression");

  const currentVersion = await page.locator(".roll-defaults-form input[name='loaded_version']").inputValue();
  const external = await context.request.post(
    `${baseURL}/terminal/cards/${fixture.cards.machine_1_running}/tare`,
    { form: { loaded_version: currentVersion, tare_weight: "1.30" }, maxRedirects: 0 },
  );
  assertEqual(external.status(), 303, "external version-changing write status");
  const beforeConflict = await rawSchedule(page, 1);
  await page.locator(".roll-defaults-form input[name='tare_weight']").fill("1.40");
  await submitFormAndWait(page, ".roll-defaults-form");
  const alert = page.locator("#terminal-refresh-alert");
  assert(await alert.isVisible(), "Stale production write did not render refresh-required alert.");
  assert(normalized(await alert.textContent()).includes("Данните са променени"), "Conflict alert omitted its Bulgarian title.");
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    page.locator("#terminal-refresh-alert-button").click(),
  ]);
  assertEqual(await rawSchedule(page, 1), beforeConflict, "conflict reload countdown preservation");
  passed(`${viewport.width}x${viewport.height}: dirty autosave, real roll add, stale conflict, and reload preservation`);
}


async function assertPauseResumeLifecycle(page, viewport) {
  await navigate(page, fixture.cards.machine_2_running);
  const now = Date.now();
  await writeSchedule(page, schedule({
    machineId: 2,
    cardId: fixture.cards.machine_2_running,
    previousChangeAtMs: now - 28 * 60_000,
    intervalMinutes: 30,
    nextExpectedAtMs: now + 2 * 60_000,
    status: "running",
  }));
  await submitFormAndWait(page, 'form[action$="/timing/pause"]');
  const paused = await readSchedule(page, 2);
  assertEqual(paused.observedStatus, "paused", "paused observed status");
  assert(paused.pauseNeedsResolution && paused.frozenRemainingMs > 0, "Pause did not freeze a positive unresolved value.");
  const pausedDisplay = normalized(await page.locator("[data-roll-change-control-value]").textContent());
  assert(await page.locator('[data-machine-id="2"] [data-roll-change-machine-timer]').evaluate((element) => element.classList.contains("paused")), "Positive paused timer is not yellow.");
  assert(await page.locator("[data-roll-change-open]").evaluate((element) => element.classList.contains("paused")), "Selected positive paused timer is not yellow.");
  await page.waitForTimeout(1_300);
  assertEqual(normalized(await page.locator("[data-roll-change-control-value]").textContent()), pausedDisplay, "paused display wait");
  await page.reload({ waitUntil: "networkidle" });
  assertEqual(normalized(await page.locator("[data-roll-change-control-value]").textContent()), pausedDisplay, "paused display refresh");

  await submitFormAndWait(page, 'form[action$="/timing/resume"]');
  const unresolved = await readSchedule(page, 2);
  assertEqual(unresolved.observedStatus, "running", "unresolved resumed status");
  assert(unresolved.pauseNeedsResolution && unresolved.frozenRemainingMs === paused.frozenRemainingMs, "Resume did not retain unresolved positive freeze.");
  const unresolvedDisplay = normalized(await page.locator("[data-roll-change-control-value]").textContent());
  assert(await page.locator('[data-machine-id="2"] [data-roll-change-machine-timer]').evaluate((element) => element.classList.contains("resync")), "Unresolved positive resume is not yellow.");
  assert(await page.locator("[data-roll-change-open]").evaluate((element) => element.classList.contains("resync")), "Selected unresolved positive resume is not yellow.");
  await page.waitForTimeout(1_300);
  assertEqual(normalized(await page.locator("[data-roll-change-control-value]").textContent()), unresolvedDisplay, "unresolved resume tick suppression");

  await submitFormAndWait(page, 'form[action$="/timing/pause"]');
  const beforePausedAdvance = await readSchedule(page, 2);
  await page.locator("[data-roll-change-advance]").click();
  const afterPausedAdvance = await readSchedule(page, 2);
  assertEqual(afterPausedAdvance.previousChangeAtMs, beforePausedAdvance.nextExpectedAtMs, "paused acknowledgement previous");
  assertEqual(afterPausedAdvance.nextExpectedAtMs, beforePausedAdvance.nextExpectedAtMs + beforePausedAdvance.intervalMinutes * 60_000, "paused acknowledgement next");
  assertEqual(afterPausedAdvance.pauseNeedsResolution, false, "paused acknowledgement resolution");
  assert(await page.locator('[data-machine-id="2"] [data-roll-change-machine-timer]').evaluate((element) => element.classList.contains("paused")), "Acknowledged paused timer lost paused styling.");
  assert(await page.locator("[data-roll-change-open]").evaluate((element) => element.classList.contains("paused")), "Selected acknowledged paused timer lost paused styling.");

  const editorMinute = Math.floor(Date.now() / 60_000) * 60_000;
  await writeSchedule(page, {
    ...afterPausedAdvance,
    observedStatus: "paused",
    frozenRemainingMs: Math.max(0, afterPausedAdvance.nextExpectedAtMs - Date.now()),
    pauseNeedsResolution: true,
  });
  assertEqual((await readSchedule(page, 2)).pauseNeedsResolution, true, "paused editor unresolved precondition");
  await page.locator("[data-roll-change-open]").click();
  await page.locator("[data-roll-change-previous]").fill(localMinuteValue(editorMinute - 5 * 60_000));
  await page.locator("[data-roll-change-hours]").fill("0");
  await page.locator("[data-roll-change-minutes]").fill("10");
  await page.locator("[data-roll-change-next]").fill(localMinuteValue(editorMinute + 5 * 60_000));
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  const editorResolved = await readSchedule(page, 2);
  assertEqual(editorResolved.pauseNeedsResolution, false, "paused editor save resolution");
  assertEqual(editorResolved.observedStatus, "paused", "paused editor status");

  await submitFormAndWait(page, 'form[action$="/timing/resume"]');
  const resolvedResume = await readSchedule(page, 2);
  assertEqual(resolvedResume.frozenRemainingMs, null, "resolved resume frozen value");
  assertEqual(resolvedResume.pauseNeedsResolution, false, "resolved resume resolution flag");
  const ticking = { ...resolvedResume, previousChangeAtMs: Date.now() - 59_000, nextExpectedAtMs: Date.now() + 1_200 };
  await writeSchedule(page, ticking);
  assertEqual(normalized(await page.locator("[data-roll-change-control-value]").textContent()), "00:01", "resolved running initial tick");
  await page.waitForTimeout(1_600);
  assertEqual(normalized(await page.locator("[data-roll-change-control-value]").textContent()), "00:00", "resolved running timestamp tick");

  await navigate(page, fixture.cards.machine_4_paused);
  const duePaused = schedule({ machineId: 4, cardId: fixture.cards.machine_4_paused, previousChangeAtMs: Date.now() - 60 * 60_000, intervalMinutes: 60, nextExpectedAtMs: Date.now() - 1_000, status: "paused", frozenRemainingMs: 0, pauseNeedsResolution: true });
  await writeSchedule(page, duePaused);
  assertEqual(normalized(await page.locator("[data-roll-change-control-value]").textContent()), "00:00", "paused due display");
  assert(await page.locator('[data-machine-id="4"] [data-roll-change-machine-timer]').evaluate((element) => element.classList.contains("paused")), "Paused due is not yellow.");
  assert(await page.locator("[data-roll-change-open]").evaluate((element) => element.classList.contains("paused")), "Selected paused due is not yellow.");
  assert(normalized(await page.locator('[data-lifecycle-slot="pause"]').textContent()).includes("Продължи"), "Paused state lacks its visible resume text.");
  if (viewport.width === 1920) {
    const target = screenshotPath("paused-due.png");
    await page.screenshot({ path: target, fullPage: true });
  }
  await submitFormAndWait(page, 'form[action$="/timing/resume"]');
  assertEqual(normalized(await page.locator("[data-roll-change-control-value]").textContent()), "00:00", "unresolved zero resume display");
  assert(await page.locator('[data-machine-id="4"] [data-roll-change-machine-timer]').evaluate((element) => element.classList.contains("urgent")), "Unresolved zero resume is not red.");
  assert(await page.locator("[data-roll-change-open]").evaluate((element) => element.classList.contains("urgent")), "Selected unresolved zero resume is not red.");
  passed(`${viewport.width}x${viewport.height}: pause freeze, unresolved resume, paused resolution, and resumed ticking`);
}


async function assertStableSchedule(page, machineId, expected, label, settleMs = 250) {
  await page.waitForFunction(
    ({ key, value }) => localStorage.getItem(key) === value,
    { key: storageKey(machineId), value: JSON.stringify(expected) },
  );
  await page.waitForTimeout(settleMs);
  assertEqual(await readSchedule(page, machineId), expected, `${label} first stability read`);
  await page.waitForTimeout(250);
  assertEqual(await readSchedule(page, machineId), expected, `${label} second stability read`);
}


async function captureStorageEvents(page, machineId) {
  await page.evaluate((key) => {
    window.__rollChangeStorageEvents = [];
    window.addEventListener("storage", (event) => {
      if (event.key === key) {
        window.__rollChangeStorageEvents.push({
          oldValue: event.oldValue,
          newValue: event.newValue,
        });
      }
    });
  }, storageKey(machineId));
}


async function capturedStorageEvents(page) {
  return page.evaluate(() => window.__rollChangeStorageEvents || []);
}


async function assertTwoTabLifecycleAndReplacementStorage(context, page, mutationRequests, viewport) {
  await navigate(page, fixture.cards.machine_3_running);
  const initial = schedule({
    machineId: 3,
    cardId: fixture.cards.machine_3_running,
    previousChangeAtMs: Date.now() - 20 * 60_000,
    intervalMinutes: 30,
    nextExpectedAtMs: Date.now() + 10 * 60_000,
    status: "running",
  });
  await writeSchedule(page, initial);

  const stale = await context.newPage();
  instrumentPage(stale, mutationRequests);
  await navigate(stale, fixture.cards.machine_3_running);
  await captureStorageEvents(stale, 3);

  await submitFormAndWait(page, 'form[action$="/timing/pause"]');
  const paused = await readSchedule(page, 3);
  assertEqual(paused.observedStatus, "paused", "fresh paused tab stored status");
  await assertStableSchedule(page, 3, paused, "stale running tab after pause", 1_250);
  assertEqual((await capturedStorageEvents(stale)).length, 1, "pause storage-event write count");

  await submitFormAndWait(page, 'form[action$="/timing/resume"]');
  const resumed = await readSchedule(page, 3);
  assertEqual(resumed.observedStatus, "running", "fresh resumed tab stored status");
  await assertStableSchedule(page, 3, resumed, "stale running tab after resume", 1_250);
  assertEqual((await capturedStorageEvents(stale)).length, 2, "pause/resume storage-event write count");

  await navigate(page, fixture.cards.machine_1_running);
  await navigate(stale, fixture.cards.machine_1_running);
  const now = Date.now();
  await writeSchedule(page, schedule({ machineId: 1, cardId: fixture.cards.machine_1_running, previousChangeAtMs: now - 20 * 60_000, intervalMinutes: 30, nextExpectedAtMs: now + 10 * 60_000, status: "running" }));
  await captureStorageEvents(stale, 1);
  await page.locator('form[data-lifecycle-slot="finish"] button[type="submit"]').click();
  assert(await page.locator("[data-finish-confirm-modal]").isVisible(), "Finish confirmation did not open.");
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    page.locator("[data-finish-confirm-submit]").click(),
  ]);
  assertEqual(await rawSchedule(page, 1), null, "finish storage cleanup");
  const machineOne = page.locator('[data-roll-change-machine][data-machine-id="1"]');
  assertEqual(Number(await machineOne.getAttribute("data-card-id")), fixture.cards.machine_1_follow_up, "replacement machine focus");
  assertEqual(await machineOne.getAttribute("data-card-status"), "pending", "replacement machine status");
  assert(await machineOne.locator("[data-roll-change-machine-timer]").isHidden(), "Timer transferred to follow-up card.");
  await page.evaluate(({ key, value }) => localStorage.setItem(key, JSON.stringify(value)), {
    key: storageKey(1),
    value: schedule({ machineId: 1, cardId: fixture.cards.machine_1_follow_up, previousChangeAtMs: Date.now() - 60_000, intervalMinutes: 30, nextExpectedAtMs: Date.now() + 29 * 60_000, status: "running" }),
  });
  await page.reload({ waitUntil: "networkidle" });
  assertEqual(await rawSchedule(page, 1), null, "pending replacement cleanup");

  await navigate(page, fixture.cards.machine_1_follow_up);
  await submitFormAndWait(page, 'form[action$="/timing/start"]');
  const nextOrder = schedule({
    machineId: 1,
    cardId: fixture.cards.machine_1_follow_up,
    previousChangeAtMs: Date.now() - 5 * 60_000,
    intervalMinutes: 30,
    nextExpectedAtMs: Date.now() + 25 * 60_000,
    status: "running",
  });
  await writeSchedule(page, nextOrder, false);
  await assertStableSchedule(page, 1, nextOrder, "stale old-card tab after next-order save", 1_250);

  await stale.locator("[data-roll-change-advance]").evaluate((control) => control.click());
  await assertStableSchedule(page, 1, nextOrder, "stale old-card quick acknowledgement");

  await stale.locator("[data-roll-change-open]").click();
  const staleMinute = Math.floor(Date.now() / 60_000) * 60_000;
  await stale.locator("[data-roll-change-previous]").fill(localMinuteValue(staleMinute - 5 * 60_000));
  await stale.locator("[data-roll-change-hours]").fill("0");
  await stale.locator("[data-roll-change-minutes]").fill("30");
  await stale.locator("[data-roll-change-next]").fill(localMinuteValue(staleMinute + 25 * 60_000));
  await stale.locator("[data-roll-change-form] button[type='submit']").click();
  await assertStableSchedule(page, 1, nextOrder, "stale old-card editor save");

  await stale.locator("[data-roll-change-open]").click();
  await stale.locator("[data-roll-change-clear]").click();
  await assertStableSchedule(page, 1, nextOrder, "stale old-card clear action");
  assertEqual((await capturedStorageEvents(stale)).length, 4, "replacement storage-event count");
  await stale.close();
  passed(`${viewport.width}x${viewport.height}: stale-tab pause/resume stability, finish cleanup, and next-card ownership`);
}


async function runViewport(browser, viewport) {
  resetFixture();
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const mutationRequests = [];
  instrumentPage(page, mutationRequests);
  try {
    await seedSchedules(page);
    const timerSnapshotBefore = databaseSnapshot();
    assert(timerSnapshotBefore.recipe_actuals.length > 0, "Guarded fixture has no recipe actual row to preserve.");
    assert(timerSnapshotBefore.recipe_actuals.some((row) => (
      row.card_id === fixture.cards.machine_1_running
      && row.component_key === "raw_material_a"
      && row.actual_material_used === "Fixture actual LDPE"
      && row.batch_lot === "ROLL-CHANGE-ACTUAL-01"
    )), "Guarded fixture recipe actual row is not meaningful and deterministic.");
    await assertLayoutAndInactiveState(page, viewport);
    await assertEditorAndScheduleMath(page, viewport);
    await assertStorageEventsDueAndCorrection(context, page, mutationRequests, viewport);
    await assertInvalidStorageCleanup(page, viewport);
    await assertTerminalRegressionSurfaces(page, viewport);
    assertEqual(mutationRequests, [], "timer-only and open/close mutation requests");
    assertEqual(databaseSnapshot(), timerSnapshotBefore, "timer-only SQLite snapshot");
    passed(`${viewport.width}x${viewport.height}: timer-only actions changed no production database fields`);

    await assertDirtyAutosaveAndConflict(context, page, viewport);
    await assertPauseResumeLifecycle(page, viewport);
    await assertTwoTabLifecycleAndReplacementStorage(context, page, mutationRequests, viewport);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), "Lifecycle result has horizontal overflow.");
    summary.viewports.push({ ...viewport, status: "passed" });
  } finally {
    await context.close();
  }
}


async function main() {
  let browser;
  try {
    await preflightDatabase();
    resetFixture();
    const require = createRequire(path.join(repoRoot, "package.json"));
    const { chromium } = require("@playwright/test");
    browser = await chromium.launch();
    for (const viewport of viewports) await runViewport(browser, viewport);

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
