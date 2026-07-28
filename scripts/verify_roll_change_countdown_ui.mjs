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


function assertTimestampBetween(actual, startedAt, endedAt, label) {
  assert(
    Number.isFinite(actual) && actual >= startedAt && actual <= endedAt,
    `${label}: expected a timestamp from ${startedAt} through ${endedAt}, found ${actual}`,
  );
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
const lifecycleStoragePrefix = "extrusion-terminal.roll-change-lifecycle.v1.machine.";
const bootstrapCaseFilter = process.env.TASK7_BOOTSTRAP_CASE?.trim() || null;
const bootstrapViewportFilter = process.env.TASK7_BOOTSTRAP_VIEWPORT?.trim() || null;
const summaryPath = path.join(artifactDir, "verification-summary.json");
const configuredViewports = [
  { width: 1920, height: 768 },
  { width: 1366, height: 768 },
];
const viewports = bootstrapViewportFilter
  ? configuredViewports.filter(({ width, height }) => `${width}x${height}` === bootstrapViewportFilter)
  : configuredViewports;
assert(viewports.length > 0, `Unknown TASK7_BOOTSTRAP_VIEWPORT: ${bootstrapViewportFilter}`);
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


function lifecycleStorageKey(machineId) {
  return `${lifecycleStoragePrefix}${machineId}`;
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


async function setDateTimeControl(page, prefix, timestamp) {
  const [dateValue, timeValue] = localMinuteValue(timestamp).split("T");
  const [hourValue, minuteValue] = timeValue.split(":");
  await page.locator(`[data-roll-change-${prefix}-date]`).fill(dateValue);
  await page.locator(`[data-roll-change-${prefix}-hour]`).fill(hourValue);
  await page.locator(`[data-roll-change-${prefix}-minute]`).fill(minuteValue);
}


async function setIntervalControl(page, hoursValue, minutesValue) {
  await page.locator("[data-roll-change-hours]").fill(String(hoursValue));
  await page.locator("[data-roll-change-minutes]").fill(String(minutesValue));
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


async function rawLifecycle(page, machineId) {
  return page.evaluate((key) => localStorage.getItem(key), lifecycleStorageKey(machineId));
}


async function setRawLifecycle(page, machineId, raw) {
  await page.evaluate(({ key, value }) => {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  }, { key: lifecycleStorageKey(machineId), value: raw });
}


async function waitForLifecycle(page, machineId, expected) {
  await page.waitForFunction(
    ({ key, value }) => localStorage.getItem(key) === value,
    { key: lifecycleStorageKey(machineId), value: JSON.stringify(expected) },
    { timeout: 3_000 },
  );
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


function instrumentPage(page, mutationRequests, { expectedConsoleErrors = [] } = {}) {
  page.on("pageerror", (error) => summary.pageErrors.push(error.message));
  page.on("console", (message) => {
    if (
      message.type() === "error"
      && !expectedConsoleErrors.some((expected) => message.text().includes(expected))
    ) summary.consoleErrors.push(message.text());
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


function assertSameVerticalCenter(boxes, label) {
  const centers = boxes.map((box) => box.top + box.height / 2);
  const spread = Math.max(...centers) - Math.min(...centers);
  assert(spread <= 1, `${label} are not vertically centered together (${spread}px spread).`);
}


async function assertShiftAndWaitingButtonWhitespace(page) {
  const whitespace = await page.evaluate(() => {
    const measure = (selector) => {
      const button = document.querySelector(selector);
      const buttonBox = button.getBoundingClientRect();
      const children = Array.from(button.children)
        .filter((child) => !child.hidden)
        .map((child) => child.getBoundingClientRect());
      return {
        left: Math.min(...children.map((box) => box.left)) - buttonBox.left,
        right: buttonBox.right - Math.max(...children.map((box) => box.right)),
      };
    };
    return { queue: measure("#queue-open"), shift: measure("#shift-open") };
  });
  assert(Math.abs(whitespace.shift.left - whitespace.queue.left) <= 1, "Shift button left whitespace differs from Waiting Orders.");
  assert(Math.abs(whitespace.shift.right - whitespace.queue.right) <= 1, "Shift button right whitespace differs from Waiting Orders.");
}


async function assertRollLedgerGeometry(page) {
  const ledger = await page.evaluate(() => {
    const head = document.querySelector(".roll-head");
    const list = document.querySelector(".roll-list");
    const row = list.querySelector(".roll-row[data-roll-id]");
    const box = (element) => {
      const value = element.getBoundingClientRect();
      return { left: value.left, right: value.right };
    };
    return {
      headerGutter: head.offsetWidth - head.clientWidth,
      bodyGutter: list.offsetWidth - list.clientWidth,
      headerCells: Array.from(head.querySelectorAll(":scope > div"), box),
      bodyCells: Array.from(row.querySelectorAll(":scope > div"), box),
    };
  });
  assertEqual(ledger.headerCells.length, ledger.bodyCells.length, "roll ledger column count");
  assert(Math.abs(ledger.headerGutter - ledger.bodyGutter) <= 1, "Roll ledger scrollbar gutters differ.");
  for (const [index, headerCell] of ledger.headerCells.entries()) {
    const bodyCell = ledger.bodyCells[index];
    assert(Math.abs(headerCell.left - bodyCell.left) <= 1, `Roll ledger column ${index + 1} left edge is misaligned.`);
    assert(Math.abs(headerCell.right - bodyCell.right) <= 1, `Roll ledger column ${index + 1} right edge is misaligned.`);
  }
}


async function assertRollValueVerticalCenters(page) {
  const row = page.locator(".roll-row[data-roll-id]").first();
  const displayBoxes = async () => row.locator("[data-roll-display]").evaluateAll((values) => values.map((value) => {
    const box = value.getBoundingClientRect();
    return { top: box.top, height: box.height };
  }));
  const initialErrorSlot = await row.locator("[data-feedback-roll-id]").evaluate((slot) => {
    const box = slot.getBoundingClientRect();
    return { display: getComputedStyle(slot).display, height: box.height };
  });
  assert(initialErrorSlot.display === "none" && initialErrorSlot.height === 0, "Empty gross validation slot reserves vertical space.");
  assertSameVerticalCenter(await displayBoxes(), "Gross, tare, net, and pallet display values before editing");

  await row.locator("[data-roll-edit-open]").click();
  assertEqual(await row.getAttribute("data-roll-edit-open"), "true", "roll edit state");
  const inputBoxes = await row.locator("[data-roll-correction-input]").evaluateAll((inputs) => inputs.map((input) => {
    const box = input.getBoundingClientRect();
    return { top: box.top, height: box.height };
  }));
  assertSameVerticalCenter(inputBoxes, "Gross, tare, and pallet correction inputs");

  const rollId = await row.getAttribute("data-roll-id");
  await page.locator(`[data-roll-actions-for="${rollId}"] [data-roll-row-cancel]`).click();
  assertEqual(await row.getAttribute("data-roll-edit-open"), "false", "roll cancel state");
  assertSameVerticalCenter(await displayBoxes(), "Gross, tare, net, and pallet display values after cancel");
}


async function assertLayoutAndInactiveState(page, viewport) {
  await removeSchedule(page, 1, false);
  await navigate(page, fixture.cards.machine_1_running);
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
    const start = document.querySelector("[data-lifecycle-slot='start'] .action-button, button[data-lifecycle-slot='start']").getBoundingClientRect();
    const rollChange = document.querySelector("[data-roll-change-controls]").getBoundingClientRect();
    return start.left - rollChange.right;
  });
  assert(topbarSpacing >= 12, `Roll-change group is not visibly separated (${topbarSpacing}px).`);
  await assertShiftAndWaitingButtonWhitespace(page);
  await assertRollLedgerGeometry(page);
  await assertRollValueVerticalCenters(page);
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
  assert(await page.evaluate(() => document.activeElement?.hasAttribute("data-roll-change-previous-date")), "Editor did not focus its first field.");
  const modalGeometry = await page.locator("[data-roll-change-dialog]").evaluate((dialog) => {
    const box = dialog.getBoundingClientRect();
    return {
      centeredX: Math.abs((box.left + box.width / 2) - window.innerWidth / 2),
      centeredY: Math.abs((box.top + box.height / 2) - window.innerHeight / 2),
      contained: box.left >= 0 && box.top >= 0 && box.right <= window.innerWidth && box.bottom <= window.innerHeight,
    };
  });
  assert(modalGeometry.centeredX <= 2 && modalGeometry.centeredY <= 2 && modalGeometry.contained, "Editor modal is not centered and contained.");

  const editorStructure = await page.locator("[data-roll-change-dialog]").evaluate((dialog) => {
    const sections = Array.from(dialog.querySelectorAll(".roll-change-editor-section"));
    const fields = Array.from(dialog.querySelectorAll('[data-roll-change-previous-hour], [data-roll-change-previous-minute], [data-roll-change-hours], [data-roll-change-minutes], [data-roll-change-next-hour], [data-roll-change-next-minute]'));
    const start = dialog.querySelector(".roll-change-start-section");
    const interval = dialog.querySelector(".roll-change-interval-section");
    const clear = dialog.querySelector("[data-roll-change-clear]")?.getBoundingClientRect();
    const cancel = dialog.querySelector("[data-roll-change-cancel]")?.getBoundingClientRect();
    const save = dialog.querySelector("button[type='submit']")?.getBoundingClientRect();
    const restart = dialog.querySelector("[data-roll-change-restart]");
    return {
      sectionCount: sections.length,
      sectionsShareStyle: sections.every((section) => {
        const style = getComputedStyle(section);
        return style.display === "grid" && style.borderTopStyle === "solid";
      }),
      allTypedInputs: fields.length === 6 && fields.every((field) => (
        field.tagName === "INPUT"
        && field.type === "text"
        && field.inputMode === "numeric"
        && field.maxLength === 2
      )),
      alignedSectionLefts: start && interval
        ? Math.abs(start.getBoundingClientRect().left - interval.getBoundingClientRect().left)
        : Number.POSITIVE_INFINITY,
      compactActions: clear && cancel && save
        ? Math.max(clear.height, cancel.height, save.height) <= 52
        : false,
      equalConfirmActions: cancel && save
        ? Math.abs(cancel.width - save.width) <= 1 && Math.abs(cancel.height - save.height) <= 1
        : false,
      restartContentFits: restart
        ? restart.scrollWidth <= restart.clientWidth && restart.scrollHeight <= restart.clientHeight
        : false,
    };
  });
  assertEqual(editorStructure.sectionCount, 3, "numbered editor sections");
  assert(editorStructure.sectionsShareStyle, "Editor sections do not share one visual treatment.");
  assert(editorStructure.allTypedInputs, "Hour/minute controls are not direct two-digit numeric text inputs.");
  assert(editorStructure.alignedSectionLefts <= 1, "Start and interval sections are not vertically aligned.");
  assert(editorStructure.compactActions, "Editor footer actions are still oversized.");
  assert(editorStructure.equalConfirmActions, "Cancel and save actions are not equal in size.");
  assert(editorStructure.restartContentFits, "Current-time action content is clipped or overflows its button.");

  const editorTarget = screenshotPath(`editor-${viewport.width}x${viewport.height}.png`);
  await page.screenshot({ path: editorTarget, fullPage: true });
  const editorDialogTarget = screenshotPath(`editor-dialog-${viewport.width}x${viewport.height}.png`);
  await page.locator("[data-roll-change-dialog]").screenshot({ path: editorDialogTarget });

  const dragFields = [
    "[data-roll-change-previous-date]",
    "[data-roll-change-previous-hour]",
    "[data-roll-change-previous-minute]",
    "[data-roll-change-hours]",
    "[data-roll-change-minutes]",
    "[data-roll-change-next-hour]",
    "[data-roll-change-next-minute]",
  ];
  for (const selector of dragFields) {
    const fieldBox = await page.locator(selector).boundingBox();
    assert(fieldBox, `${selector} has no visible geometry.`);
    await page.mouse.move(fieldBox.x + fieldBox.width / 2, fieldBox.y + fieldBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(8, Math.round(viewport.height / 2), { steps: 8 });
    await page.mouse.up();
    assert(await overlay.isVisible(), `A drag beginning in ${selector} closed the editor.`);
  }
  const destinationFieldBox = await page.locator("[data-roll-change-previous-hour]").boundingBox();
  assert(destinationFieldBox, "Start-hour field has no visible geometry for reverse drag test.");
  await page.mouse.move(2, 2);
  await page.mouse.down();
  await page.mouse.move(
    destinationFieldBox.x + destinationFieldBox.width / 2,
    destinationFieldBox.y + destinationFieldBox.height / 2,
    { steps: 8 },
  );
  await page.mouse.up();
  assert(await overlay.isVisible(), "A drag beginning on the backdrop and ending in a field closed the editor.");
  passed(`${viewport.width}x${viewport.height}: field drags cannot dismiss the editor; deliberate backdrop click still can`);

  await page.locator("[data-roll-change-next-minute]").focus();
  await page.locator("[data-roll-change-form] button[type='submit']").press("Tab");
  assert(await page.evaluate(() => document.activeElement?.hasAttribute("data-roll-change-close")), "Editor focus escaped after the last action.");
  await page.keyboard.press("Shift+Tab");
  assert(await page.evaluate(() => document.activeElement?.matches("[data-roll-change-form] button[type='submit']")), "Editor reverse focus trap failed.");

  await setIntervalControl(page, 0, 0);
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  assert(await overlay.isVisible(), "Zero interval closed the editor.");
  assertEqual(normalized(await page.locator('[data-roll-change-error-for="form"]').textContent()), "Изберете интервал поне 1 минута.", "zero interval error");
  assertEqual(await rawSchedule(page, 1), validRaw, "zero interval preserved record");
  if (viewport.width === 1920) {
    const target = screenshotPath("editor-validation.png");
    await page.screenshot({ path: target, fullPage: true });
  }

  await page.locator("[data-roll-change-hours]").fill("5");
  await page.locator("[data-roll-change-hours]").press("Tab");
  assertEqual(await page.locator("[data-roll-change-hours]").inputValue(), "05", "single-digit interval hour normalization");
  assertEqual(normalized(await page.locator("[data-roll-change-interval-summary]").textContent()), "5 ч. и 0 мин.", "typed interval summary");
  await page.locator("[data-roll-change-hours]").fill("24");
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  assertEqual(normalized(await page.locator('[data-roll-change-error-for="hours"]').textContent()), "Часовете трябва да са цяло число от 0 до 23.", "typed hour bound");
  assertEqual(await page.locator("[data-roll-change-hours]").getAttribute("aria-invalid"), "true", "hour aria-invalid state");
  await page.locator("[data-roll-change-hours]").fill("0");
  await page.locator("[data-roll-change-minutes]").fill("60");
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  assertEqual(normalized(await page.locator('[data-roll-change-error-for="minutes"]').textContent()), "Минутите трябва да са цяло число от 0 до 59.", "typed minute bound");

  for (const malformedValue of ["-1", "2x", " 1"]) {
    await page.locator("[data-roll-change-hours]").focus();
    await page.locator("[data-roll-change-hours]").press("Control+A");
    await page.keyboard.insertText(malformedValue);
    await page.locator("[data-roll-change-minutes]").fill("00");
    await page.locator("[data-roll-change-form] button[type='submit']").click();
    assertEqual(await page.locator("[data-roll-change-hours]").inputValue(), malformedValue, `malformed hour preserved: ${JSON.stringify(malformedValue)}`);
    assertEqual(normalized(await page.locator('[data-roll-change-error-for="hours"]').textContent()), "Часовете трябва да са цяло число от 0 до 23.", `malformed hour rejected: ${JSON.stringify(malformedValue)}`);
    assertEqual(await rawSchedule(page, 1), validRaw, `malformed hour preserved storage: ${JSON.stringify(malformedValue)}`);
  }

  const minute = Math.floor(Date.now() / 60_000) * 60_000;
  const previous = minute - 60 * 60_000;
  await setDateTimeControl(page, "previous", previous);
  await setIntervalControl(page, 0, 30);
  assertEqual(await page.locator("[data-roll-change-next]").inputValue(), localMinuteValue(previous + 30 * 60_000), "previous/interval draft recalculation");
  await setDateTimeControl(page, "next", previous);
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  assertEqual(normalized(await page.locator('[data-roll-change-error-for="next"]').textContent()), "Очакваният час трябва да е след началния.", "reversed next-time error");
  assertEqual(await rawSchedule(page, 1), validRaw, "reversed next preserved record");

  const directNext = minute - 10 * 60_000;
  await setDateTimeControl(page, "next", directNext);
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  assert(await overlay.isHidden(), "Valid direct next-time save did not close.");
  const directSaved = await readSchedule(page, 1);
  assertEqual(directSaved.previousChangeAtMs, previous, "direct save previous timestamp");
  assertEqual(directSaved.intervalMinutes, 30, "direct save interval");
  assertEqual(directSaved.nextExpectedAtMs, directNext, "direct next-time anchor");

  const lateClickStarted = Date.now();
  await page.locator("[data-roll-change-advance]").click();
  const lateClickEnded = Date.now();
  const late = await readSchedule(page, 1);
  assertTimestampBetween(late.previousChangeAtMs, lateClickStarted, lateClickEnded, "late acknowledgement click-time anchor");
  assertEqual(late.nextExpectedAtMs - late.previousChangeAtMs, 30 * 60_000, "late acknowledgement exact interval");
  const earlyClickStarted = Date.now();
  await page.locator("[data-roll-change-advance]").click();
  const earlyClickEnded = Date.now();
  const early = await readSchedule(page, 1);
  assertTimestampBetween(early.previousChangeAtMs, earlyClickStarted, earlyClickEnded, "early acknowledgement click-time anchor");
  assertEqual(early.nextExpectedAtMs - early.previousChangeAtMs, 30 * 60_000, "early acknowledgement exact interval");

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
  await page.locator("[data-roll-change-hours]").fill("24");
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  const invalidRestartError = normalized(await page.locator('[data-roll-change-error-for="hours"]').textContent());
  const invalidRestartAria = await page.locator("[data-roll-change-hours]").getAttribute("aria-invalid");
  assertEqual(invalidRestartError, "Часовете трябва да са цяло число от 0 до 23.", "invalid interval precondition for current-time action");
  assertEqual(invalidRestartAria, "true", "invalid interval aria precondition for current-time action");
  const invalidRestartNext = await page.locator("[data-roll-change-next]").inputValue();
  const invalidRestartStarted = Date.now();
  await page.locator("[data-roll-change-restart]").click();
  const invalidRestartPrevious = await page.locator("[data-roll-change-previous]").inputValue();
  assert(
    [localMinuteValue(invalidRestartStarted), localMinuteValue(Date.now())].includes(invalidRestartPrevious),
    "Current-time action did not set the start to the current minute with an invalid interval.",
  );
  assertEqual(await page.locator("[data-roll-change-next]").inputValue(), invalidRestartNext, "current-time action preserved expected timestamp");
  assertEqual(await page.locator("[data-roll-change-hours]").inputValue(), "24", "current-time action preserved interval input");
  assertEqual(normalized(await page.locator('[data-roll-change-error-for="hours"]').textContent()), invalidRestartError, "current-time action preserved interval error");
  assertEqual(await page.locator("[data-roll-change-hours]").getAttribute("aria-invalid"), invalidRestartAria, "current-time action preserved interval aria state");
  assertEqual(await rawSchedule(page, 1), restartBefore, "current-time action preserved storage");
  await page.locator("[data-roll-change-cancel]").click();
  await open.click();
  await setDateTimeControl(page, "next", Math.floor(Date.now() / 60_000) * 60_000 + 2 * 60 * 60_000);
  const restartNextBefore = await page.locator("[data-roll-change-next]").inputValue();
  const restartStarted = Date.now();
  await page.locator("[data-roll-change-restart]").click();
  const restartPrevious = await page.locator("[data-roll-change-previous]").inputValue();
  assert([localMinuteValue(restartStarted), localMinuteValue(Date.now())].includes(restartPrevious), "Restart did not use the current minute.");
  assertEqual(
    await page.locator("[data-roll-change-next]").inputValue(),
    localMinuteValue(new Date(restartPrevious).getTime() + 30 * 60_000),
    "current-time action recalculated expected timestamp from the valid interval",
  );
  assert(
    await page.locator("[data-roll-change-next]").inputValue() !== restartNextBefore,
    "Current-time action did not replace the previous expected timestamp.",
  );
  await page.locator("[data-roll-change-cancel]").click();
  assertEqual(await rawSchedule(page, 1), restartBefore, "restart then cancel storage bytes");

  const machineTwoRaw = await rawSchedule(page, 2);
  await open.click();
  await page.locator("[data-roll-change-clear]").click();
  assertEqual(await rawSchedule(page, 1), null, "clear machine one key");
  assertEqual(await rawSchedule(page, 2), machineTwoRaw, "clear unrelated machine key");
  assert(await page.locator("[data-roll-change-advance]").isHidden(), "Clear left quick action visible.");
  assert(await page.locator('[data-machine-id="1"] [data-roll-change-machine-timer]').isHidden(), "Clear left machine timer visible.");

  const inactiveOpenedAt = Date.now();
  await open.click();
  const inactivePrevious = await page.locator("[data-roll-change-previous]").inputValue();
  assert(
    [localMinuteValue(inactiveOpenedAt), localMinuteValue(Date.now())].includes(inactivePrevious),
    "Inactive editor did not default the start date and time to now.",
  );
  assertEqual(await page.locator("[data-roll-change-hours]").inputValue(), "00", "inactive interval hour default");
  assertEqual(await page.locator("[data-roll-change-minutes]").inputValue(), "00", "inactive interval minute default");
  const rehydratePrevious = minute - 5 * 60_000;
  const rehydrateNext = minute + 25 * 60_000;
  await setDateTimeControl(page, "previous", rehydratePrevious);
  await setIntervalControl(page, 0, 30);
  await setDateTimeControl(page, "next", rehydrateNext);
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

  const crossTabClickStarted = Date.now();
  await page.locator("[data-roll-change-advance]").click();
  const crossTabClickEnded = Date.now();
  const acknowledged = await readSchedule(page, 1);
  await peer.waitForFunction(({ key, expected }) => localStorage.getItem(key) === JSON.stringify(expected), { key: storageKey(1), expected: acknowledged });
  assertTimestampBetween(acknowledged.previousChangeAtMs, crossTabClickStarted, crossTabClickEnded, "cross-tab acknowledgement click-time anchor");
  assertEqual(acknowledged.nextExpectedAtMs - acknowledged.previousChangeAtMs, 30 * 60_000, "cross-tab acknowledgement exact interval");

  await page.locator("[data-roll-change-open]").click();
  const correctedNext = Math.floor((Date.now() + 12 * 60_000) / 60_000) * 60_000;
  await setDateTimeControl(page, "next", correctedNext);
  await page.locator("[data-roll-change-form] button[type='submit']").click();
  const corrected = await readSchedule(page, 1);
  assertEqual(corrected.nextExpectedAtMs, correctedNext, "corrected direct next anchor");
  await peer.waitForFunction(({ key, expected }) => localStorage.getItem(key) === JSON.stringify(expected), { key: storageKey(1), expected: corrected });
  const correctionClickStarted = Date.now();
  await page.locator("[data-roll-change-advance]").click();
  const correctionClickEnded = Date.now();
  const afterCorrection = await readSchedule(page, 1);
  assertTimestampBetween(afterCorrection.previousChangeAtMs, correctionClickStarted, correctionClickEnded, "corrected acknowledgement click-time anchor");
  assertEqual(afterCorrection.nextExpectedAtMs - afterCorrection.previousChangeAtMs, corrected.intervalMinutes * 60_000, "corrected acknowledgement exact interval");

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
  const pausedClickStarted = Date.now();
  await page.locator("[data-roll-change-advance]").click();
  const pausedClickEnded = Date.now();
  const afterPausedAdvance = await readSchedule(page, 2);
  assertTimestampBetween(afterPausedAdvance.previousChangeAtMs, pausedClickStarted, pausedClickEnded, "paused acknowledgement click-time anchor");
  assertEqual(afterPausedAdvance.nextExpectedAtMs - afterPausedAdvance.previousChangeAtMs, beforePausedAdvance.intervalMinutes * 60_000, "paused acknowledgement exact interval");
  assertEqual(afterPausedAdvance.frozenRemainingMs, beforePausedAdvance.intervalMinutes * 60_000, "paused acknowledgement frozen interval");
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
  await setDateTimeControl(page, "previous", editorMinute - 5 * 60_000);
  await setIntervalControl(page, 0, 10);
  await setDateTimeControl(page, "next", editorMinute + 5 * 60_000);
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


async function captureScheduleRemovalState(page, machineId) {
  await page.evaluate((key) => {
    window.__rollChangeRemovalStates = [];
    window.addEventListener("storage", (event) => {
      if (event.key !== key || event.newValue !== null || event.oldValue === null) return;
      const alert = document.querySelector("[data-roll-change-reload-alert]");
      const reload = document.querySelector("[data-roll-change-reload]");
      window.__rollChangeRemovalStates.push({
        alertVisible: Boolean(alert && !alert.hidden),
        editorHidden: Boolean(document.querySelector("[data-roll-change-overlay]")?.hidden),
        openDisabled: Boolean(document.querySelector("[data-roll-change-open]")?.disabled),
        quickDisabled: Boolean(document.querySelector("[data-roll-change-advance]")?.disabled),
        reloadFocused: document.activeElement === reload,
      });
    });
  }, storageKey(machineId));
}


async function capturedScheduleRemovalStates(page) {
  return page.evaluate(() => window.__rollChangeRemovalStates || []);
}


async function captureLifecycleStorageEvents(page, machineId) {
  await page.evaluate((key) => {
    window.__rollChangeLifecycleEvents = [];
    window.addEventListener("storage", (event) => {
      if (event.key === key) {
        window.__rollChangeLifecycleEvents.push({
          oldValue: event.oldValue,
          newValue: event.newValue,
        });
      }
    });
  }, lifecycleStorageKey(machineId));
}


async function capturedLifecycleStorageEvents(page) {
  return page.evaluate(() => window.__rollChangeLifecycleEvents || []);
}


async function captureTerminalHtml(context, cardId) {
  const response = await context.request.get(`${baseURL}/terminal/cards/${cardId}`);
  assert(response.ok(), `Captured terminal document returned HTTP ${response.status()}.`);
  return response.text();
}


async function installCapturedTerminalRoute(page, cardId, html) {
  await page.route(`${baseURL}/terminal/cards/${cardId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/html; charset=utf-8",
      body: html,
    });
  });
}


async function navigateCapturedTerminal(page, cardId) {
  const response = await page.goto(`${baseURL}/terminal/cards/${cardId}`, {
    waitUntil: "domcontentloaded",
  });
  assert(response?.ok(), `Captured terminal navigation returned HTTP ${response?.status() || "unknown"}.`);
}


async function waitForLifecycleState(page, machineId, { cardId, status }) {
  await page.waitForFunction(
    ({ key, expectedCardId, expectedStatus }) => {
      try {
        const value = JSON.parse(localStorage.getItem(key));
        return value.cardId === expectedCardId && value.status === expectedStatus;
      } catch {
        return false;
      }
    },
    {
      key: lifecycleStorageKey(machineId),
      expectedCardId: cardId,
      expectedStatus: status,
    },
    { timeout: 3_000 },
  );
}


async function lifecycleCandidateFromMarkup(page, machineId) {
  return page.locator(`[data-roll-change-machine][data-machine-id="${machineId}"]`).evaluate((host) => {
    const cardId = Number(host.dataset.cardId);
    const cardVersion = Number(host.dataset.cardVersion);
    const hasCard = Number.isSafeInteger(cardId) && cardId > 0;
    return {
      schemaVersion: 2,
      machineId: Number(host.dataset.machineId),
      cardId: hasCard ? cardId : null,
      cardVersion: hasCard && Number.isSafeInteger(cardVersion) && cardVersion >= 0
        ? cardVersion
        : null,
      status: host.dataset.cardStatus || "",
    };
  });
}


async function forceCountdownMutationPaths(page) {
  await page.evaluate(() => {
    const dispatchClick = (target) => target?.dispatchEvent(new MouseEvent("click", {
      bubbles: true,
      cancelable: true,
    }));
    dispatchClick(document.querySelector("[data-roll-change-open]"));

    const now = new Date();
    now.setSeconds(0, 0);
    const previous = new Date(now.getTime() - 5 * 60_000);
    const next = new Date(now.getTime() + 25 * 60_000);
    const pad = (value) => String(value).padStart(2, "0");
    const setParts = (prefix, value) => {
      const date = document.querySelector(`[data-roll-change-${prefix}-date]`);
      const hour = document.querySelector(`[data-roll-change-${prefix}-hour]`);
      const minute = document.querySelector(`[data-roll-change-${prefix}-minute]`);
      if (date) date.value = `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
      if (hour) hour.value = pad(value.getHours());
      if (minute) minute.value = pad(value.getMinutes());
    };
    setParts("previous", previous);
    setParts("next", next);
    const hours = document.querySelector("[data-roll-change-hours]");
    const minutes = document.querySelector("[data-roll-change-minutes]");
    if (hours) hours.value = "00";
    if (minutes) minutes.value = "30";
    document.querySelector("[data-roll-change-form]")?.requestSubmit();
    dispatchClick(document.querySelector("[data-roll-change-clear]"));
    dispatchClick(document.querySelector("[data-roll-change-advance]"));
  });
}


async function assertSelectedLifecycleLocked(
  page,
  machineId,
  expectedLifecycleRaw,
  label,
  expectedScheduleRaw = null,
) {
  await page.waitForFunction(
    () => document.querySelector("[data-roll-change-reload-alert]")?.hidden === false,
    null,
    { timeout: 3_000 },
  );
  assert(await page.locator("[data-roll-change-reload-alert]").isVisible(), `${label} omitted reload alert.`);
  assert(await page.locator("[data-roll-change-open]").isDisabled(), `${label} left editor action enabled.`);
  assert(await page.locator("[data-roll-change-advance]").isDisabled(), `${label} left quick acknowledgement enabled.`);
  assert(await page.locator("[data-roll-change-overlay]").isHidden(), `${label} left editor open.`);
  assert(await page.locator("[data-roll-change-reload]").evaluate((element) => document.activeElement === element), `${label} did not focus reload action.`);
  await forceCountdownMutationPaths(page);
  assertEqual(await rawLifecycle(page, machineId), expectedLifecycleRaw, `${label} lifecycle preservation`);
  assertEqual(await rawSchedule(page, machineId), expectedScheduleRaw, `${label} schedule mutation guard`);
  assert(await page.locator("[data-roll-change-overlay]").isHidden(), `${label} force-opened editor after latch.`);
}


async function finishSelectedCard(page) {
  await page.locator('form[data-lifecycle-slot="finish"] button[type="submit"]').click();
  assert(await page.locator("[data-finish-confirm-modal]").isVisible(), "Bootstrap case finish confirmation did not open.");
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    page.locator("[data-finish-confirm-submit]").click(),
  ]);
}


async function assertDelayedSameCardBootstrap(context, current, late, viewport) {
  const machineId = 3;
  const cardId = fixture.cards.machine_3_running;
  await navigate(current, cardId);
  await removeSchedule(current, machineId, false);
  const staleHtml = await captureTerminalHtml(context, cardId);
  await submitFormAndWait(current, 'form[action$="/timing/pause"]');
  await waitForLifecycleState(current, machineId, { cardId, status: "paused" });
  const newerLifecycleRaw = await rawLifecycle(current, machineId);

  let snapshotRequested;
  let releaseSnapshot;
  const snapshotSeen = new Promise((resolve) => { snapshotRequested = resolve; });
  const snapshotRelease = new Promise((resolve) => { releaseSnapshot = resolve; });
  await late.route("**/terminal/snapshot*", async (route) => {
    snapshotRequested();
    await snapshotRelease;
    await route.continue();
  });
  await installCapturedTerminalRoute(late, cardId, staleHtml);
  await navigateCapturedTerminal(late, cardId);
  await Promise.race([
    snapshotSeen,
    late.waitForTimeout(3_000).then(() => { throw new Error("Delayed same-card bootstrap did not request authoritative snapshot."); }),
  ]);

  assert(await late.locator("[data-roll-change-open]").isDisabled(), "Same-card bootstrap did not lock editor while authority was pending.");
  assert(await late.locator("[data-roll-change-advance]").isDisabled(), "Same-card bootstrap did not lock quick acknowledgement while authority was pending.");
  await forceCountdownMutationPaths(late);
  assertEqual(await rawLifecycle(late, machineId), newerLifecycleRaw, "same-card pending lifecycle preservation");
  assertEqual(await rawSchedule(late, machineId), null, "same-card pending schedule guard");

  releaseSnapshot();
  await assertSelectedLifecycleLocked(late, machineId, newerLifecycleRaw, "same-card stale bootstrap");
  if (viewport.width === 1920) {
    await late.screenshot({ path: screenshotPath("delayed-same-card-lifecycle-alert.png"), fullPage: true });
  }
}


async function assertCorrectionLockDuringDelayedBootstrap(context, current, late) {
  const machineId = 1;
  const cardId = fixture.cards.machine_1_running;
  await navigate(current, cardId);
  await removeSchedule(current, machineId, false);
  const currentHtml = await captureTerminalHtml(context, cardId);
  const expected = await lifecycleCandidateFromMarkup(current, machineId);
  await setRawLifecycle(current, machineId, "{not-json");

  let snapshotRequested;
  let releaseSnapshot;
  const snapshotSeen = new Promise((resolve) => { snapshotRequested = resolve; });
  const snapshotRelease = new Promise((resolve) => { releaseSnapshot = resolve; });
  await late.route("**/terminal/snapshot*", async (route) => {
    snapshotRequested();
    await snapshotRelease;
    await route.continue();
  });
  await installCapturedTerminalRoute(late, cardId, currentHtml);
  await navigateCapturedTerminal(late, cardId);
  await Promise.race([
    snapshotSeen,
    late.waitForTimeout(3_000).then(() => {
      throw new Error("Correction-lock bootstrap did not request authoritative snapshot.");
    }),
  ]);

  const row = late.locator(".roll-row[data-roll-id]").first();
  await row.locator("[data-roll-edit-open]").click();
  assertEqual(await row.getAttribute("data-roll-edit-open"), "true", "pending correction edit state");
  assert(await late.locator("[data-roll-change-open]").isDisabled(), "Pending correction left editor action enabled.");
  assert(await late.locator("[data-roll-change-advance]").isDisabled(), "Pending correction left quick acknowledgement enabled.");

  releaseSnapshot();
  await waitForLifecycle(late, machineId, expected);
  assert(await late.locator("[data-roll-change-reload-alert]").isHidden(), "Current authority incorrectly required reload.");
  assert(await late.locator("[data-roll-change-open]").isDisabled(), "Authority completion undid the active correction editor lock.");
  assert(await late.locator("[data-roll-change-advance]").isDisabled(), "Authority completion undid the active correction quick-action lock.");

  const rollId = await row.getAttribute("data-roll-id");
  await late.locator(`[data-roll-actions-for="${rollId}"] [data-roll-row-cancel]`).click();
  assertEqual(await row.getAttribute("data-roll-edit-open"), "false", "closed correction edit state");
  assert(await late.locator("[data-roll-change-open]").isEnabled(), "Closing correction did not restore editor action.");
  assert(await late.locator("[data-roll-change-advance]").isEnabled(), "Closing correction did not restore quick acknowledgement.");
}


async function assertCorrectionClosePreservesPendingLifecycleLock(context, current, late) {
  const machineId = 1;
  const cardId = fixture.cards.machine_1_running;
  await navigate(current, cardId);
  await removeSchedule(current, machineId, false);
  const currentHtml = await captureTerminalHtml(context, cardId);
  const expected = await lifecycleCandidateFromMarkup(current, machineId);
  await setRawLifecycle(current, machineId, "{not-json");

  let snapshotRequested;
  let releaseSnapshot;
  const snapshotSeen = new Promise((resolve) => { snapshotRequested = resolve; });
  const snapshotRelease = new Promise((resolve) => { releaseSnapshot = resolve; });
  await late.route("**/terminal/snapshot*", async (route) => {
    snapshotRequested();
    await snapshotRelease;
    await route.continue();
  });
  await installCapturedTerminalRoute(late, cardId, currentHtml);
  await navigateCapturedTerminal(late, cardId);
  await Promise.race([
    snapshotSeen,
    late.waitForTimeout(3_000).then(() => {
      throw new Error("Correction-close pending case did not request authoritative snapshot.");
    }),
  ]);

  const row = late.locator(".roll-row[data-roll-id]").first();
  const rollId = await row.getAttribute("data-roll-id");
  await row.locator("[data-roll-edit-open]").click();
  await late.locator(`[data-roll-actions-for="${rollId}"] [data-roll-row-cancel]`).click();
  assertEqual(await row.getAttribute("data-roll-edit-open"), "false", "pending-close correction state");
  assert(await late.locator("[data-roll-change-open]").isDisabled(), "Closing correction unlocked editor while lifecycle authority was pending.");
  assert(await late.locator("[data-roll-change-advance]").isDisabled(), "Closing correction unlocked quick acknowledgement while lifecycle authority was pending.");
  assertEqual(await rawSchedule(late, machineId), null, "pending-close schedule guard");

  releaseSnapshot();
  await waitForLifecycle(late, machineId, expected);
  assert(await late.locator("[data-roll-change-reload-alert]").isHidden(), "Matching authority incorrectly required reload after correction close.");
  assert(await late.locator("[data-roll-change-open]").isEnabled(), "Matching authority did not release editor after correction closed.");
  assert(await late.locator("[data-roll-change-advance]").isEnabled(), "Matching authority did not release quick acknowledgement after correction closed.");
}


async function assertCorrectionClosePreservesReloadLatch(context, current, late) {
  const machineId = 1;
  const cardId = fixture.cards.machine_1_running;
  await navigate(current, cardId);
  await removeSchedule(current, machineId, false);
  const currentHtml = await captureTerminalHtml(context, cardId);
  await setRawLifecycle(current, machineId, "{not-json");
  const snapshotResponse = await context.request.get(`${baseURL}/terminal/snapshot`);
  assert(snapshotResponse.ok(), `Reload-latch snapshot fixture returned HTTP ${snapshotResponse.status()}.`);
  const divergentSnapshot = await snapshotResponse.json();
  const selected = divergentSnapshot.active_cards.find((card) => card.id === cardId);
  assert(selected, "Reload-latch snapshot omitted selected card.");
  selected.version += 1;
  selected.status = "paused";

  let snapshotRequested;
  let releaseSnapshot;
  const snapshotSeen = new Promise((resolve) => { snapshotRequested = resolve; });
  const snapshotRelease = new Promise((resolve) => { releaseSnapshot = resolve; });
  await late.route("**/terminal/snapshot*", async (route) => {
    snapshotRequested();
    await snapshotRelease;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(divergentSnapshot),
    });
  });
  await installCapturedTerminalRoute(late, cardId, currentHtml);
  await navigateCapturedTerminal(late, cardId);
  await Promise.race([
    snapshotSeen,
    late.waitForTimeout(3_000).then(() => {
      throw new Error("Correction-close reload case did not request authoritative snapshot.");
    }),
  ]);

  const row = late.locator(".roll-row[data-roll-id]").first();
  const rollId = await row.getAttribute("data-roll-id");
  await row.locator("[data-roll-edit-open]").click();
  releaseSnapshot();
  await late.waitForFunction(
    () => document.querySelector("[data-roll-change-reload-alert]")?.hidden === false,
    null,
    { timeout: 3_000 },
  );
  await late.locator(`[data-roll-actions-for="${rollId}"] [data-roll-row-cancel]`).click();
  assertEqual(await row.getAttribute("data-roll-edit-open"), "false", "reload-close correction state");
  assert(await late.locator("[data-roll-change-reload-alert]").isVisible(), "Closing correction removed the reload-required alert.");
  assert(await late.locator("[data-roll-change-open]").isDisabled(), "Closing correction unlocked editor after reload latch.");
  assert(await late.locator("[data-roll-change-advance]").isDisabled(), "Closing correction unlocked quick acknowledgement after reload latch.");
  await forceCountdownMutationPaths(late);
  assertEqual(await rawSchedule(late, machineId), null, "reload-close schedule mutation guard");
}


async function assertModalFocusContainment(_context, page, _late, viewport) {
  const cardId = fixture.cards.machine_1_running;
  await navigate(page, cardId);

  const assertBackgroundIsolated = async (selectors, label) => {
    for (const selector of selectors) {
      const element = page.locator(selector);
      assert(await element.getAttribute("inert") !== null, `${label} left ${selector} keyboard-reachable.`);
      assertEqual(await element.getAttribute("aria-hidden"), "true", `${label} ${selector} assistive isolation`);
    }
  };

  const assertDrawer = async ({ opener, overlay, dialog, lastControl, label }) => {
    const openerControl = page.locator(opener);
    await openerControl.focus();
    await openerControl.click();
    const overlayControl = page.locator(overlay);
    const dialogControl = page.locator(dialog);
    assert(await overlayControl.isVisible(), `${label} did not open.`);
    assertEqual(await dialogControl.getAttribute("role"), "dialog", `${label} dialog role`);
    assertEqual(await dialogControl.getAttribute("aria-modal"), "true", `${label} modal state`);
    await assertBackgroundIsolated([".terminal-header", ".machine-nav", ".main"], label);
    const first = dialogControl.locator("button:not([disabled]), input:not([disabled]), a[href]").first();
    const last = page.locator(lastControl).last();
    await last.focus();
    await page.keyboard.press("Tab");
    assert(await first.evaluate((element) => document.activeElement === element), `${label} forward focus did not wrap.`);
    await first.focus();
    await page.keyboard.press("Shift+Tab");
    assert(await last.evaluate((element) => document.activeElement === element), `${label} reverse focus did not wrap.`);
    await page.keyboard.press("Escape");
    assert(await overlayControl.isHidden(), `${label} Escape did not close.`);
    assert(await openerControl.evaluate((element) => document.activeElement === element), `${label} did not restore opener focus.`);
  };

  await assertDrawer({
    opener: "#queue-open",
    overlay: "#queue-overlay",
    dialog: "#queue-overlay [role='dialog']",
    lastControl: "#queue-overlay .queue-card[href]",
    label: "Queue dialog",
  });
  await assertDrawer({
    opener: "#history-open",
    overlay: "#history-overlay",
    dialog: "#history-overlay [role='dialog']",
    lastControl: "#history-overlay .history-row[href]",
    label: "Produced dialog",
  });

  const finishOpener = page.locator('form[data-lifecycle-slot="finish"] button[type="submit"]');
  await finishOpener.focus();
  await finishOpener.click();
  const finishModal = page.locator("[data-finish-confirm-modal]");
  const finishDialog = finishModal.locator("[role='dialog']");
  const finishCancel = finishModal.locator("[data-finish-confirm-cancel]");
  const finishSubmit = finishModal.locator("[data-finish-confirm-submit]");
  assert(await finishModal.isVisible(), "Finish dialog did not open.");
  assertEqual(await finishDialog.getAttribute("role"), "dialog", "Finish dialog role");
  assertEqual(await finishDialog.getAttribute("aria-modal"), "true", "Finish modal state");
  await assertBackgroundIsolated([".app"], "Finish dialog");
  await finishSubmit.focus();
  await page.keyboard.press("Tab");
  assert(await finishCancel.evaluate((element) => document.activeElement === element), "Finish forward focus did not wrap.");
  await finishCancel.focus();
  await page.keyboard.press("Shift+Tab");
  assert(await finishSubmit.evaluate((element) => document.activeElement === element), "Finish reverse focus did not wrap.");
  await page.keyboard.press("Escape");
  assert(await finishModal.isHidden(), "Finish Escape did not close.");
  assert(await finishOpener.evaluate((element) => document.activeElement === element), "Finish did not restore opener focus.");

  await page.screenshot({
    path: screenshotPath(`round4-modal-containment-${viewport.width}x${viewport.height}.png`),
    fullPage: true,
  });
}


async function assertRound4AdminAndAffordances(context, page, _late, viewport) {
  page.removeAllListeners("dialog");
  const dialogDecisions = [];
  const observedDialogs = [];
  page.on("dialog", async (dialog) => {
    const decision = dialogDecisions.shift();
    observedDialogs.push({ type: dialog.type(), message: dialog.message() });
    if (!decision) {
      summary.pageErrors.push(`Unexpected native dialog: ${dialog.type()} ${dialog.message()}`);
      await dialog.dismiss();
      return;
    }
    if (decision.accept) await dialog.accept();
    else await dialog.dismiss();
  });

  const performWithDialogs = async (decisions, action, label) => {
    const start = observedDialogs.length;
    dialogDecisions.push(...decisions);
    await action();
    const deadline = Date.now() + 3_000;
    while (observedDialogs.length - start < decisions.length && Date.now() < deadline) {
      await page.waitForTimeout(25);
    }
    await page.waitForTimeout(150);
    const actual = observedDialogs.slice(start);
    assertEqual(actual.length, decisions.length, `${label} dialog count`);
    assertEqual(dialogDecisions.length, 0, `${label} pending dialog decisions`);
    decisions.forEach((decision, index) => {
      if (decision.type) assertEqual(actual[index].type, decision.type, `${label} dialog ${index + 1} type`);
      if (decision.messageIncludes) {
        assert(
          actual[index].message.includes(decision.messageIncludes),
          `${label} dialog ${index + 1} omitted ${decision.messageIncludes}: ${actual[index].message}`,
        );
      }
    });
    return actual;
  };

  const navigateAdmin = async (cardId) => {
    const response = await page.goto(`${baseURL}/admin/cards/${cardId}`, { waitUntil: "networkidle" });
    assert(response?.ok(), `Admin navigation returned HTTP ${response?.status() || "unknown"}.`);
  };
  const discardDecision = (accept) => ({
    accept,
    type: "confirm",
    messageIncludes: "Има незапазени промени",
  });
  const planningLink = '.admin-nav-link[href="/admin/planning"]';
  const completedId = fixture.cards.completed;
  const discardDirtyToPlanning = (label) => performWithDialogs(
    [discardDecision(true)],
    () => Promise.all([
      page.waitForURL(`${baseURL}/admin/planning`),
      page.locator(planningLink).click(),
    ]),
    label,
  );

  resetFixture();
  const dirtyControls = [
    [completedId, 'input[name="customer"]', "Незаписан клиент", "imported field"],
    [completedId, 'input[name="actual_material__raw_material_a"]', "Незаписан материал", "material field"],
    [completedId, 'input[name="tare_weight"]', "1.25", "roll default"],
    [completedId, 'input[name^="gross_weight__"]', "21.00", "roll correction"],
    [completedId, 'input[name^="started_at__"]', "2026-07-28 09:00:00", "timing correction"],
  ];
  for (const [cardId, selector, value, label] of dirtyControls) {
    await navigateAdmin(cardId);
    const control = page.locator(selector).first();
    await control.fill(value);
    await performWithDialogs(
      [discardDecision(false)],
      () => page.locator(planningLink).click(),
      `${label} navigation cancel`,
    );
    assertEqual(new URL(page.url()).pathname, `/admin/cards/${cardId}`, `${label} retained URL`);
    assertEqual(await control.inputValue(), value, `${label} retained dirty value`);
    await discardDirtyToPlanning(`${label} navigation cleanup`);
  }
  passed(`${viewport.width}x${viewport.height}: imported/material/default/roll/timing dirty navigation protection`);

  await navigateAdmin(completedId);
  await page.locator('input[name="customer"]').fill("Незаписан преди презареждане");
  await performWithDialogs(
    [{ accept: false, type: "beforeunload" }],
    () => page.evaluate(() => { window.location.href = "/admin/import"; }),
    "beforeunload dirty protection",
  );
  assertEqual(new URL(page.url()).pathname, `/admin/cards/${completedId}`, "beforeunload cancelled navigation");

  await page.locator('input[name="customer"]').fill("Записан клиент от браузъра");
  const saveDialogStart = observedDialogs.length;
  await Promise.all([
    page.waitForURL(`${baseURL}/admin/cards/${completedId}`),
    page.locator('.admin-save-button[form="admin-card-save-form"]').click(),
  ]);
  await page.waitForTimeout(150);
  assertEqual(observedDialogs.length, saveDialogStart, "global Save dialog count");
  assertEqual(
    await page.locator('input[name="customer"]').inputValue(),
    "Записан клиент от браузъра",
    "global Save persisted value",
  );

  resetFixture();
  await navigateAdmin(completedId);
  await page.locator('input[name="tare_weight"]').fill("1.25");
  await performWithDialogs(
    [discardDecision(true)],
    () => Promise.all([
      page.waitForURL(`${baseURL}/admin/cards/${completedId}`),
      page.locator(`form[action="/admin/cards/${completedId}/archive"] button`).click(),
    ]),
    "lifecycle approved discard",
  );
  assert(normalized(await page.locator(".admin-card-title-line").textContent()).includes("Завършена"), "Approved lifecycle discard did not archive the card.");

  resetFixture();
  await navigateAdmin(completedId);
  let before = databaseSnapshot();
  await page.locator('input[name="customer"]').fill("Незаписано преди ролка");
  await performWithDialogs(
    [
      { accept: true, type: "confirm", messageIncludes: "Да се изтрие ли ролка 1" },
      discardDecision(false),
    ],
    () => page.locator('button[form^="roll-delete-"]').first().click(),
    "roll deletion dirty cancel",
  );
  assertEqual(databaseSnapshot(), before, "roll deletion dirty cancel database preservation");
  await discardDirtyToPlanning("roll deletion dirty cleanup");

  await navigateAdmin(completedId);
  before = databaseSnapshot();
  await page.locator('input[name="customer"]').fill("Незаписано преди сегмент");
  await performWithDialogs(
    [
      { accept: true, type: "confirm", messageIncludes: "Да се изтрие ли времеви сегмент 1" },
      discardDecision(false),
    ],
    () => page.locator('button[form^="timing-delete-"]').first().click(),
    "timing deletion dirty cancel",
  );
  assertEqual(databaseSnapshot(), before, "timing deletion dirty cancel database preservation");
  await discardDirtyToPlanning("timing deletion dirty cleanup");

  resetFixture();
  const importedId = fixture.cards.imported;
  await navigateAdmin(importedId);
  await page.locator(".admin-system-section summary").click();
  before = databaseSnapshot();
  await performWithDialogs(
    [{ accept: false, type: "confirm", messageIncludes: "Изтриване на поръчка ROLL-CHANGE-UI-08?" }],
    () => page.locator(`form[action="/admin/cards/${importedId}/delete"] button`).click(),
    "permanent delete cancel",
  );
  assertEqual(databaseSnapshot(), before, "permanent delete cancel database preservation");
  await page.locator('input[name="customer"]').fill("Незаписано преди изтриване");
  await performWithDialogs(
    [
      { accept: true, type: "confirm", messageIncludes: "Изтриване на поръчка ROLL-CHANGE-UI-08?" },
      discardDecision(false),
    ],
    () => page.locator(`form[action="/admin/cards/${importedId}/delete"] button`).click(),
    "permanent delete dirty cancel",
  );
  assertEqual(databaseSnapshot(), before, "permanent delete dirty cancel database preservation");
  await discardDirtyToPlanning("permanent delete dirty cleanup");

  resetFixture();
  await navigateAdmin(completedId);
  await page.locator('input[name^="ended_at__"]').first().fill("2026-07-28 09:05:00");
  await performWithDialogs(
    [discardDecision(true)],
    () => Promise.all([
      page.waitForURL(`${baseURL}/admin/planning`),
      page.locator(planningLink).click(),
    ]),
    "navigation approved discard",
  );

  resetFixture();
  await navigateAdmin(importedId);
  assert(await page.locator('input[name="customer"]').isEnabled(), "Imported source editing was disabled.");
  for (const selector of [
    'input[name="actual_material__raw_material_a"]',
    'input[name="batch_lot__raw_material_a"]',
    'input[name="tare_weight"]',
    'input[name="current_pallet_number"]',
    'input[name="new_gross_weight"]',
    'input[name="new_started_at"]',
    'input[name="new_ended_at"]',
    'select[name="new_end_reason"]',
  ]) {
    assert(await page.locator(selector).isDisabled(), `Imported operational control remained enabled: ${selector}`);
  }
  await page.locator('input[name="customer"]').fill("Не трябва да се запише");
  const craftedActual = page.locator('input[name="actual_material__raw_material_a"]');
  await craftedActual.evaluate((input) => { input.disabled = false; });
  await craftedActual.fill("Crafted actual");
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    page.locator('.admin-save-button[form="admin-card-save-form"]').click(),
  ]);
  assert(normalized(await page.locator("body").textContent()).includes("Производствени данни не могат да се записват"), "Imported operational rejection was not explicit.");
  assertEqual(await page.locator('input[name="customer"]').inputValue(), "Клиент 8 за брояч на ролки", "imported operational rejection atomic source value");
  passed(`${viewport.width}x${viewport.height}: imported operational rejection and disabled state`);

  resetFixture();
  const restoredId = fixture.cards.restored_started;
  await navigateAdmin(restoredId);
  assertEqual(
    await page.locator(`form[action="/admin/cards/${restoredId}/unrelease"]`).count(),
    0,
    "restored-started unrelease affordance",
  );
  assert(normalized(await page.locator("body").textContent()).includes("Връщането в планиране е недостъпно след начало на производство"), "Restored-started unrelease explanation missing.");
  const restoredVersion = await page.locator('#admin-card-save-form input[name="loaded_version"]').inputValue();
  before = databaseSnapshot();
  const rejectedUnrelease = await context.request.post(`${baseURL}/admin/cards/${restoredId}/unrelease`, {
    form: { loaded_version: restoredVersion, return_to: "detail" },
  });
  assertEqual(rejectedUnrelease.status(), 200, "restored-started unrelease route status");
  assert(normalized(await rejectedUnrelease.text()).includes("не могат да се връщат за планиране"), "Restored-started unrelease route omitted rejection.");
  assertEqual(databaseSnapshot(), before, "restored-started unrelease preservation");
  passed(`${viewport.width}x${viewport.height}: restored-started unrelease backend and affordance`);

  resetFixture();
  await navigate(page, fixture.cards.machine_1_follow_up);
  const occupiedStart = page.locator('button[data-lifecycle-slot="start"]');
  assert(await occupiedStart.isDisabled(), "occupied pending Start remained enabled.");
  assertEqual(await page.locator('form[action$="/timing/start"]').count(), 0, "occupied pending Start form count");
  assert(normalized(await page.locator("#machine-occupied-reason").textContent()).includes("ROLL-CHANGE-UI-01"), "Occupied pending explanation omitted running order.");

  await navigate(page, fixture.cards.machine_2_paused);
  const occupiedContinue = page.locator('button[data-lifecycle-slot="pause"]');
  assert(await occupiedContinue.isDisabled(), "occupied paused Continue remained enabled.");
  assert(normalized(await occupiedContinue.textContent()).includes("Продължи"), "occupied paused Continue label missing.");
  assertEqual(await page.locator('form[action$="/timing/resume"]').count(), 0, "occupied paused Continue form count");
  assertEqual(await page.locator('form[data-lifecycle-slot="finish"]').count(), 1, "occupied paused Finish availability");
  assert(normalized(await page.locator("#machine-occupied-reason").textContent()).includes("ROLL-CHANGE-UI-03"), "Occupied paused explanation omitted running order.");
  passed(`${viewport.width}x${viewport.height}: occupied pending Start and occupied paused Continue affordances`);

  await navigate(page, fixture.cards.machine_1_running);
  const terminalRoll = page.locator(".roll-row[data-roll-id]").first();
  assertEqual(await terminalRoll.locator('input[name="gross_weight"]').getAttribute("aria-label"), "Ролка 1, бруто", "terminal roll accessible name gross");
  assertEqual(await terminalRoll.locator('input[name="tare_weight"]').getAttribute("aria-label"), "Ролка 1, шпула", "terminal roll accessible name tare");
  assertEqual(await terminalRoll.locator('input[name="pallet_number"]').getAttribute("aria-label"), "Ролка 1, палет", "terminal roll accessible name pallet");

  await navigateAdmin(completedId);
  assertEqual(await page.locator('input[name^="pallet_number__"]').first().getAttribute("aria-label"), "Ролка 1, палет", "admin roll accessible name");
  assertEqual(await page.locator('input[name^="started_at__"]').first().getAttribute("aria-label"), "Сегмент 1, начало", "admin timing accessible name start");
  assertEqual(await page.locator('input[name^="ended_at__"]').first().getAttribute("aria-label"), "Сегмент 1, край", "admin timing accessible name end");
  assertEqual(await page.locator('select[name^="end_reason__"]').first().getAttribute("aria-label"), "Сегмент 1, причина", "admin timing accessible name reason");
  await page.screenshot({
    path: screenshotPath(`round4-admin-guards-${viewport.width}x${viewport.height}.png`),
    fullPage: true,
  });
  passed(`${viewport.width}x${viewport.height}: terminal roll accessible name and admin timing accessible name`);
}


async function assertDelayedReplacementBootstrap(context, current, late) {
  const machineId = 1;
  const cardId = fixture.cards.machine_1_running;
  await navigate(current, cardId);
  await removeSchedule(current, machineId, false);
  const staleHtml = await captureTerminalHtml(context, cardId);
  await finishSelectedCard(current);
  await navigate(current, fixture.cards.machine_1_follow_up);
  await submitFormAndWait(current, 'form[action$="/timing/start"]');
  await waitForLifecycleState(current, machineId, {
    cardId: fixture.cards.machine_1_follow_up,
    status: "running",
  });
  const replacementSchedule = schedule({
    machineId,
    cardId: fixture.cards.machine_1_follow_up,
    previousChangeAtMs: Date.now() - 5 * 60_000,
    intervalMinutes: 30,
    nextExpectedAtMs: Date.now() + 25 * 60_000,
    status: "running",
  });
  await writeSchedule(current, replacementSchedule, false);
  const newerLifecycleRaw = await rawLifecycle(current, machineId);
  const newerScheduleRaw = await rawSchedule(current, machineId);
  await installCapturedTerminalRoute(late, cardId, staleHtml);
  await navigateCapturedTerminal(late, cardId);
  await assertSelectedLifecycleLocked(
    late,
    machineId,
    newerLifecycleRaw,
    "replacement-card stale bootstrap",
    newerScheduleRaw,
  );
}


async function assertDelayedEmptyMachineBootstrap(context, current, late) {
  const machineId = 3;
  const cardId = fixture.cards.machine_3_running;
  await navigate(current, cardId);
  await removeSchedule(current, machineId, false);
  await current.locator(".roll-defaults-form input[name='tare_weight']").fill("1.00");
  await submitFormAndWait(current, ".roll-defaults-form");
  await current.locator(".add-roll-form input[name='gross_weight']").fill("20.00");
  await submitFormAndWait(current, ".add-roll-form");
  const staleHtml = await captureTerminalHtml(context, cardId);
  await finishSelectedCard(current);
  await waitForLifecycleState(current, machineId, { cardId: null, status: "free" });
  const newerLifecycleRaw = await rawLifecycle(current, machineId);
  await installCapturedTerminalRoute(late, cardId, staleHtml);
  await navigateCapturedTerminal(late, cardId);
  await assertSelectedLifecycleLocked(late, machineId, newerLifecycleRaw, "empty-machine stale bootstrap");
}


async function assertLifecycleSchemaTolerance(context, current, late, rawValue, label) {
  const machineId = 3;
  const cardId = fixture.cards.machine_3_running;
  await navigate(current, cardId);
  await removeSchedule(current, machineId, false);
  const staleHtml = await captureTerminalHtml(context, cardId);
  const expected = await lifecycleCandidateFromMarkup(current, machineId);
  assert(Number.isSafeInteger(expected.cardVersion), `${label} markup omitted card version.`);
  await captureLifecycleStorageEvents(current, machineId);
  await setRawLifecycle(current, machineId, rawValue(expected));
  await installCapturedTerminalRoute(late, cardId, staleHtml);
  await navigateCapturedTerminal(late, cardId);
  await waitForLifecycle(late, machineId, expected);
  assert(await late.locator("[data-roll-change-reload-alert]").isHidden(), `${label} incorrectly latched an authoritative current page.`);
  assert(await late.locator("[data-roll-change-open]").isEnabled(), `${label} did not unlock the authoritative current editor.`);
  await late.waitForTimeout(750);
  const lifecycleEvents = await capturedLifecycleStorageEvents(current);
  assertEqual(lifecycleEvents.length, 1, `${label} lifecycle storage event count`);
  assertEqual(lifecycleEvents[0].newValue, JSON.stringify(expected), `${label} repaired lifecycle bytes`);
}


async function assertLifecycleRequestFailure(context, current, late) {
  const machineId = 3;
  const cardId = fixture.cards.machine_3_running;
  await navigate(current, cardId);
  await removeSchedule(current, machineId, false);
  const staleHtml = await captureTerminalHtml(context, cardId);
  const divergent = JSON.stringify({
    schemaVersion: 2,
    machineId,
    cardId,
    cardVersion: 999_999,
    status: "running",
  });
  await setRawLifecycle(current, machineId, divergent);
  await late.route("**/terminal/snapshot*", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "deterministic authority failure" }),
  }));
  await installCapturedTerminalRoute(late, cardId, staleHtml);
  await navigateCapturedTerminal(late, cardId);
  await assertSelectedLifecycleLocked(late, machineId, divergent, "authority-request failure");
}


const bootstrapCases = {
  "same-card": assertDelayedSameCardBootstrap,
  "correction-lock": assertCorrectionLockDuringDelayedBootstrap,
  "correction-close-pending": assertCorrectionClosePreservesPendingLifecycleLock,
  "correction-close-reload-latched": assertCorrectionClosePreservesReloadLatch,
  "round4-modal-containment": assertModalFocusContainment,
  "round4-admin-and-affordances": assertRound4AdminAndAffordances,
  replacement: assertDelayedReplacementBootstrap,
  empty: assertDelayedEmptyMachineBootstrap,
  malformed: (context, current, late) => assertLifecycleSchemaTolerance(
    context,
    current,
    late,
    () => "{not-json",
    "malformed lifecycle tolerance",
  ),
  "schema-v1": (context, current, late) => assertLifecycleSchemaTolerance(
    context,
    current,
    late,
    (expected) => JSON.stringify({
      schemaVersion: 1,
      machineId: expected.machineId,
      cardId: expected.cardId,
      status: expected.status,
    }),
    "schema-v1 lifecycle tolerance",
  ),
  "request-failure": assertLifecycleRequestFailure,
};


async function runBootstrapCase(browser, viewport, name) {
  const assertion = bootstrapCases[name];
  assert(assertion, `Unknown TASK7_BOOTSTRAP_CASE: ${name}`);
  resetFixture();
  const context = await browser.newContext({ viewport });
  const current = await context.newPage();
  const late = await context.newPage();
  const mutationRequests = [];
  instrumentPage(current, mutationRequests);
  instrumentPage(late, mutationRequests, {
    expectedConsoleErrors: name === "request-failure" ? ["status of 503"] : [],
  });
  try {
    await assertion(context, current, late, viewport);
    passed(`${viewport.width}x${viewport.height}: delayed-bootstrap ${name} regression`);
  } finally {
    await context.close();
  }
}


async function assertTwoTabLifecycleAndReplacementStorage(context, page, mutationRequests, viewport) {
  await navigate(page, fixture.cards.machine_3_running);
  await removeSchedule(page, 3, false);
  assertEqual(await rawSchedule(page, 3), null, "schedule-free lifecycle precondition");

  const stale = await context.newPage();
  instrumentPage(stale, mutationRequests);
  await navigate(stale, fixture.cards.machine_3_running);
  await captureStorageEvents(stale, 3);
  await stale.locator("[data-roll-change-open]").click();
  assert(await stale.locator("[data-roll-change-overlay]").isVisible(), "Stale-tab editor precondition did not open.");
  const staleMinute = Math.floor(Date.now() / 60_000) * 60_000;
  await setDateTimeControl(stale, "previous", staleMinute - 5 * 60_000);
  await setIntervalControl(stale, 0, 30);
  await setDateTimeControl(stale, "next", staleMinute + 25 * 60_000);

  await submitFormAndWait(page, 'form[action$="/timing/pause"]');
  assertEqual(await rawSchedule(page, 3), null, "schedule-free remote pause storage");
  await stale.waitForFunction(
    () => document.querySelector("[data-roll-change-reload-alert]")?.hidden === false,
    null,
    { timeout: 3_000 },
  );
  const reloadAlert = stale.locator("[data-roll-change-reload-alert]");
  const reloadAction = stale.locator("[data-roll-change-reload]");
  assert(await stale.locator("[data-roll-change-overlay]").isHidden(), "Remote pause did not close the stale-tab editor.");
  assert(await stale.locator("[data-roll-change-open]").isDisabled(), "Remote pause did not disable the stale-tab editor action.");
  assert(await stale.locator("[data-roll-change-advance]").isDisabled(), "Remote pause did not disable stale-tab quick acknowledgement.");
  assert(await stale.locator("[data-roll-change-open]").evaluate((element) => element.classList.contains("paused")), "Schedule-free stale tab did not expose the remotely observed paused state.");
  assert(await reloadAlert.isVisible(), "Remote pause did not expose the reload-required notice.");
  assertEqual(await reloadAlert.getAttribute("role"), "alert", "reload-required notice role");
  assertEqual(await reloadAlert.getAttribute("aria-live"), "assertive", "reload-required notice live priority");
  assert(normalized(await reloadAlert.textContent()).includes("пауза"), "Reload-required notice omitted synchronized paused state.");
  assert(await reloadAction.isEnabled(), "Reload-required action is not enabled.");
  assert(await reloadAction.evaluate((element) => document.activeElement === element), "Remote pause did not move focus to the reload action.");
  await stale.locator("[data-roll-change-form]").evaluate((form) => form.requestSubmit());
  assertEqual(await rawSchedule(stale, 3), null, "stale schedule-free editor recreation after pause");
  assertEqual((await capturedStorageEvents(stale)).length, 0, "schedule-free pause schedule-event count");

  await submitFormAndWait(page, 'form[action$="/timing/resume"]');
  await stale.waitForFunction(
    () => document.querySelector("[data-roll-change-reload-alert]")?.dataset.synchronizedStatus === "running",
  );
  assertEqual(await rawSchedule(page, 3), null, "schedule-free remote resume storage");
  assert(await stale.locator("[data-roll-change-open]").isDisabled(), "Stale-tab editor action was re-enabled before reload.");
  assert(await stale.locator("[data-roll-change-advance]").isDisabled(), "Stale-tab quick acknowledgement was re-enabled before reload.");
  assert(normalized(await reloadAlert.textContent()).includes("работа"), "Reload-required notice omitted synchronized running state.");
  assertEqual((await capturedStorageEvents(stale)).length, 0, "schedule-free pause/resume schedule-event count");

  await navigate(page, fixture.cards.machine_1_running);
  await navigate(stale, fixture.cards.machine_1_running);
  const now = Date.now();
  await writeSchedule(page, schedule({ machineId: 1, cardId: fixture.cards.machine_1_running, previousChangeAtMs: now - 20 * 60_000, intervalMinutes: 30, nextExpectedAtMs: now + 10 * 60_000, status: "running" }));
  await captureStorageEvents(stale, 1);
  await captureScheduleRemovalState(stale, 1);
  await stale.locator("[data-roll-change-open]").click();
  assert(await stale.locator("[data-roll-change-overlay]").isVisible(), "Finish stale-editor precondition did not open.");
  const finishMinute = Math.floor(Date.now() / 60_000) * 60_000;
  await setDateTimeControl(stale, "previous", finishMinute - 5 * 60_000);
  await setIntervalControl(stale, 0, 30);
  await setDateTimeControl(stale, "next", finishMinute + 25 * 60_000);
  await page.locator('form[data-lifecycle-slot="finish"] button[type="submit"]').click();
  assert(await page.locator("[data-finish-confirm-modal]").isVisible(), "Finish confirmation did not open.");
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    page.locator("[data-finish-confirm-submit]").click(),
  ]);
  assertEqual(await rawSchedule(page, 1), null, "finish storage cleanup");
  await stale.waitForFunction(() => (window.__rollChangeRemovalStates || []).length > 0);
  const [removalState] = await capturedScheduleRemovalStates(stale);
  assert(removalState.alertVisible, "Selected-card schedule removal did not expose reload notice immediately.");
  assert(removalState.editorHidden, "Selected-card schedule removal did not close the stale editor immediately.");
  assert(removalState.openDisabled, "Selected-card schedule removal did not disable stale editor action immediately.");
  assert(removalState.quickDisabled, "Selected-card schedule removal did not disable stale quick action immediately.");
  assert(removalState.reloadFocused, "Selected-card schedule removal did not focus reload action immediately.");
  assertEqual(
    await stale.locator("[data-roll-change-reload-alert]").getAttribute("data-synchronized-status"),
    "ended",
    "finished stale-tab synchronized status",
  );
  await stale.locator("[data-roll-change-form]").evaluate((form) => form.requestSubmit());
  await stale.locator("[data-roll-change-clear]").evaluate((control) => control.click());
  await stale.locator("[data-roll-change-advance]").evaluate((control) => control.click());
  assertEqual(await rawSchedule(stale, 1), null, "finished stale editor recreated old schedule key");
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

  await stale.locator("[data-roll-change-form]").evaluate((form) => form.requestSubmit());
  await assertStableSchedule(page, 1, nextOrder, "stale old-card editor save");

  await stale.locator("[data-roll-change-clear]").evaluate((control) => control.click());
  await assertStableSchedule(page, 1, nextOrder, "stale old-card clear action");
  assertEqual((await capturedStorageEvents(stale)).length, 4, "replacement storage-event count");
  await stale.close();
  passed(`${viewport.width}x${viewport.height}: schedule-free lifecycle latch, finish-removal focus, and next-card ownership`);
}


async function runViewport(browser, viewport) {
  if (bootstrapCaseFilter) {
    await runBootstrapCase(browser, viewport, bootstrapCaseFilter);
    summary.viewports.push({ ...viewport, status: "passed" });
    return;
  }
  for (const name of Object.keys(bootstrapCases)) {
    await runBootstrapCase(browser, viewport, name);
  }
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
