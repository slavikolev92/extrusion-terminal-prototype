import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

import {
  VERIFICATION_CONTRACT,
  assertExactScreenshotEvidence,
} from "./order_finish_review_ui_contract.mjs";
import {
  assertSafeGeneratedFileTarget,
  writeGeneratedFileAtomic,
} from "./order_finish_review_output_guard.mjs";


function requiredEnvironment(name) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Required environment variable ${name} is missing.`);
  return value;
}


function assert(condition, message) {
  if (!condition) throw new Error(message);
}


function comparable(value) {
  if (Array.isArray(value)) return value.map(comparable);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, comparable(value[key])]),
    );
  }
  return value;
}


function assertEqual(actual, expected, label) {
  if (JSON.stringify(comparable(actual)) !== JSON.stringify(comparable(expected))) {
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


function assertNoSymlinkComponents(base, candidate, message) {
  const relative = path.relative(base, candidate);
  assert(
    relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative)),
    message,
  );
  let current = base;
  for (const component of relative.split(path.sep).filter(Boolean)) {
    current = path.join(current, component);
    if (fs.existsSync(current)) {
      assert(!fs.lstatSync(current).isSymbolicLink(), message);
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
const artifactDir = path.resolve(repoRoot, artifactInput);

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
  isStrictChild(artifactRoot, artifactDir),
  "ARTIFACT_DIR must be below artifacts/ui-checks.",
);
assertNoSymlinkComponents(
  repoRoot,
  artifactDir,
  "ARTIFACT_DIR guard path must not contain symlinks.",
);
assert(
  fs.existsSync(requestedFixturePath),
  `Fixture JSON does not exist: ${requestedFixturePath}`,
);
assert(fs.statSync(requestedFixturePath).isFile(), "FIXTURE_JSON must name a file.");
assertSafeGeneratedFileTarget(requestedFixturePath, "FIXTURE_JSON reset target");
const fixturePath = fs.realpathSync(requestedFixturePath);
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), fixturePath),
  "FIXTURE_JSON must resolve below .test-runtime.",
);

let fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const requestedDatabasePath = path.resolve(repoRoot, fixture.db_path);
assert(fs.existsSync(requestedDatabasePath), "Fixture database does not exist.");
assert(fs.statSync(requestedDatabasePath).isFile(), "Fixture database must name a file.");
assertSafeGeneratedFileTarget(requestedDatabasePath, "fixture database reset target");
const databasePath = fs.realpathSync(requestedDatabasePath);
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), databasePath),
  "Fixture database must resolve below .test-runtime.",
);

const summary = {
  status: "running",
  baseURL,
  databaseIdentity: databasePath,
  fixture: path.relative(repoRoot, fixturePath),
  viewports: [],
  assertions: [],
  screenshots: [],
  screenshotDimensions: [],
  requestCounts: {},
  consoleErrors: [],
  expectedConsoleErrors: [],
  pageErrors: [],
  failedRequests: [],
  expectedFailedRequests: [],
  crossOriginRequests: [],
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
  artifactDir,
  "ARTIFACT_DIR guard path must not contain symlinks.",
);
let existingArtifactAncestor = artifactDir;
while (!fs.existsSync(existingArtifactAncestor)) {
  existingArtifactAncestor = path.dirname(existingArtifactAncestor);
}
assert(
  existingArtifactAncestor === artifactRoot
    || isStrictChild(
      fs.realpathSync(artifactRoot),
      fs.realpathSync(existingArtifactAncestor),
    ),
  "ARTIFACT_DIR resolves outside artifacts/ui-checks.",
);
fs.mkdirSync(artifactDir, { recursive: true });
assert(
  isStrictChild(fs.realpathSync(artifactRoot), fs.realpathSync(artifactDir)),
  "ARTIFACT_DIR resolves outside artifacts/ui-checks.",
);

const summaryPath = path.join(artifactDir, "verification-summary.json");
assertSafeGeneratedFileTarget(summaryPath, "verification summary target");
for (const screenshotName of VERIFICATION_CONTRACT.screenshots) {
  assertSafeGeneratedFileTarget(
    path.join(artifactDir, screenshotName),
    `screenshot target ${screenshotName}`,
  );
}
const require = createRequire(import.meta.url);
const localNodeModules = fs.realpathSync(path.join(repoRoot, "node_modules"));
const resolvedPlaywright = fs.realpathSync(require.resolve("@playwright/test"));
assert(
  isStrictChild(localNodeModules, resolvedPlaywright),
  "Playwright must resolve from repository-local node_modules.",
);
const { chromium } = require("@playwright/test");
const pythonExecutable = path.join(repoRoot, ".venv", "bin", "python");
const fixtureScript = path.join(
  repoRoot,
  "scripts",
  "create_order_finish_review_fixture.py",
);


function writeSummary() {
  writeGeneratedFileAtomic(
    summaryPath,
    `${JSON.stringify(summary, null, 2)}\n`,
    "verification summary target",
  );
}


function pngDimensions(target) {
  const content = fs.readFileSync(target);
  assert(
    content.length >= 24 && content.subarray(1, 4).toString("ascii") === "PNG",
    `Screenshot is not a readable PNG: ${target}`,
  );
  return {
    width: content.readUInt32BE(16),
    height: content.readUInt32BE(20),
  };
}


async function captureScreenshot(page, name, expectedDimensions) {
  const target = path.join(artifactDir, name);
  assertSafeGeneratedFileTarget(target, `screenshot target ${name}`);
  const content = await page.screenshot({ fullPage: false });
  writeGeneratedFileAtomic(target, content, `screenshot target ${name}`);
  const dimensions = pngDimensions(target);
  assertEqual(dimensions, expectedDimensions, `${name} PNG dimensions`);
  summary.screenshots.push(path.relative(repoRoot, target));
  summary.screenshotDimensions.push({
    path: path.relative(repoRoot, target),
    ...dimensions,
  });
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
  assertSafeGeneratedFileTarget(databasePath, "fixture database reset target");
  assertSafeGeneratedFileTarget(fixturePath, "FIXTURE_JSON reset target");
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


function databaseSnapshot(cardId) {
  const program = [
    "import json, sqlite3, sys",
    "connection = sqlite3.connect(sys.argv[1])",
    "connection.row_factory = sqlite3.Row",
    "card_id = int(sys.argv[2])",
    "card = connection.execute(\"SELECT status, version, first_started_at, finished_at, rewinding_roll_count FROM cards WHERE id = ?\", (card_id,)).fetchone()",
    "timing = connection.execute(\"SELECT started_at, ended_at, end_reason FROM production_time_segments WHERE card_id = ? ORDER BY started_at, id\", (card_id,)).fetchall()",
    "rolls = connection.execute(\"SELECT roll_number, gross_weight, tare_weight, net_weight, pallet_number FROM roll_entries WHERE card_id = ? ORDER BY roll_number\", (card_id,)).fetchall()",
    "print(json.dumps({'card': dict(card), 'timing': [list(row) for row in timing], 'rolls': [list(row) for row in rolls]}))",
  ].join("; ");
  return JSON.parse(
    runPython(program, [databasePath, String(cardId)], "database snapshot failed"),
  );
}


function mutateFixtureState(cardId, action) {
  const program = `
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1])
card_id = int(sys.argv[2])
action = sys.argv[3]
if action == "bump-version":
    connection.execute(
        "UPDATE cards SET version = version + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (card_id,),
    )
elif action == "delete-rolls-without-version":
    connection.execute("DELETE FROM roll_entries WHERE card_id = ?", (card_id,))
elif action == "end-shift":
    connection.execute(
        """
        UPDATE shift_occurrences
        SET ended_at = '2026-09-06 09:00:00',
            updated_at = '2026-09-06 09:00:00'
        WHERE ended_at IS NULL
        """
    )
else:
    raise SystemExit(f"unknown fixture mutation: {action}")
connection.commit()
`;
  runPython(
    program,
    [databasePath, String(cardId), action],
    `fixture mutation ${action} failed`,
  );
}


function monitorPage(page) {
  page.on("pageerror", (error) => summary.pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") summary.consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    summary.failedRequests.push({
      method: request.method(),
      url: request.url(),
      error: request.failure()?.errorText || "unknown",
    });
  });
  page.on("request", (request) => {
    const requestOrigin = new URL(request.url()).origin;
    if (requestOrigin !== baseOrigin) {
      summary.crossOriginRequests.push({
        method: request.method(),
        url: request.url(),
      });
    }
    const pathname = new URL(request.url()).pathname;
    const key = `${request.method()} ${pathname}`;
    summary.requestCounts[key] = (summary.requestCounts[key] || 0) + 1;
  });
}


async function navigate(page, cardId) {
  await page.goto(`${baseURL}/terminal/cards/${cardId}`, { waitUntil: "networkidle" });
}


async function resetForScenario(page) {
  await preflightDatabase();
  resetFixtureDatabase();
  await preflightDatabase();
  await page.goto(`${baseURL}/terminal`, { waitUntil: "networkidle" });
}


async function openActiveReview(page, cardId) {
  await navigate(page, cardId);
  const responsePromise = page.waitForResponse((response) => (
    response.request().method() === "POST"
      && new URL(response.url()).pathname === `/terminal/cards/${cardId}/finish-review`
  ));
  await page.locator('form[data-timing-finish-review="true"] button[type="submit"]').click();
  const response = await responsePromise;
  assert(response.ok(), `Active finish review returned HTTP ${response.status()}.`);
  const overlay = page.locator("[data-finish-review-overlay]");
  await overlay.waitFor({ state: "visible" });
  return overlay;
}


async function openWaitingReview(page, cardId) {
  await navigate(page, cardId);
  const overlay = page.locator("[data-finish-review-overlay]");
  const trigger = page.locator("[data-waiting-finish-trigger]");
  assert(await trigger.isEnabled(), "Waiting trigger was not enabled by its ready controller.");
  assertEqual(
    await trigger.getAttribute("aria-disabled"),
    "false",
    "controller-owned waiting trigger aria-disabled state",
  );
  await trigger.click();
  await overlay.waitFor({ state: "visible" });
  return overlay;
}


async function verifyPreControllerWaitingTriggerSafety(page) {
  await resetForScenario(page);
  const guardPage = await page.context().newPage();
  let finishPosts = 0;
  guardPage.on("request", (request) => {
    if (
      request.method() === "POST"
      && new URL(request.url()).pathname.endsWith("/finish")
    ) {
      finishPosts += 1;
    }
  });
  await guardPage.route("**/static/js/waiting_finish_review.mjs", (route) => route.abort());
  try {
    await guardPage.goto(
      `${baseURL}/terminal/cards/${fixture.cards.waiting_marker_cleared}`,
      { waitUntil: "networkidle" },
    );
    const trigger = guardPage.locator("[data-waiting-finish-trigger]");
    assertEqual(await trigger.getAttribute("type"), "button", "pre-controller trigger type");
    assert(await trigger.isDisabled(), "Pre-controller waiting trigger is enabled.");
    await trigger.evaluate((button) => button.click());
    assertEqual(finishPosts, 0, "pre-controller waiting finish POST count");
    assert(
      await guardPage.locator("[data-finish-review-overlay]").isHidden(),
      "Pre-controller waiting trigger opened a controllerless review.",
    );
  } finally {
    await guardPage.close();
  }
  passed("disabled type=button waiting trigger emits no POST without its controller");
}


function boxesOverlap(first, second) {
  return !(
    first.x + first.width <= second.x + 0.5
    || second.x + second.width <= first.x + 0.5
    || first.y + first.height <= second.y + 0.5
    || second.y + second.height <= first.y + 0.5
  );
}


function assertBoxStable(before, after, label, tolerance = 1) {
  for (const field of ["x", "y", "width", "height"]) {
    assert(
      Math.abs(before[field] - after[field]) <= tolerance,
      `${label} ${field} moved from ${before[field]} to ${after[field]}.`,
    );
  }
}


async function assertReviewGeometry(page, viewport, label) {
  const geometry = await page.evaluate(() => {
    const box = (selector) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    };
    const style = (element) => {
      const computed = getComputedStyle(element);
      return {
        width: computed.width,
        height: computed.height,
        display: computed.display,
        backgroundColor: computed.backgroundColor,
        borderRadius: computed.borderRadius,
      };
    };
    const textStyle = (element) => {
      const computed = getComputedStyle(element);
      return {
        fontFamily: computed.fontFamily,
        fontSize: computed.fontSize,
        fontWeight: computed.fontWeight,
        lineHeight: computed.lineHeight,
        color: computed.color,
      };
    };
    const rowAlignment = Array.from(document.querySelectorAll(".finish-review-row"))
      .map((row) => {
        const labelElement = row.querySelector("dt");
        const valueElement = row.querySelector("dd");
        if (!labelElement || !valueElement) return null;
        const rowBox = row.getBoundingClientRect();
        const labelBox = labelElement.getBoundingClientRect();
        const valueBox = valueElement.getBoundingClientRect();
        const center = (rect) => rect.y + rect.height / 2;
        return {
          labelDelta: Math.abs(center(labelBox) - center(rowBox)),
          valueDelta: Math.abs(center(valueBox) - center(rowBox)),
        };
      })
      .filter(Boolean);
    const timeValues = Array.from(
      document.querySelectorAll("[data-finish-timing-summary] dd"),
    ).map(textStyle);
    const icons = Array.from(document.querySelectorAll(".finish-review-icon")).map(style);
    const table = document.querySelector("[data-finish-production-summary]");
    const rowMetrics = (row) => Array.from(row?.cells || []).map((cell) => {
      const rect = cell.getBoundingClientRect();
      return {
        center: rect.x + rect.width / 2,
        width: rect.width,
        textAlign: getComputedStyle(cell).textAlign,
        text: cell.textContent.replace(/\s+/g, " ").trim(),
        colspan: cell.colSpan,
      };
    });
    const bodyRow = Array.from(table?.tBodies?.[0]?.rows || [])
      .find((row) => row.cells.length === 5);
    const wrap = document.querySelector(".finish-review-table-wrap");
    const customer = document.querySelector(
      '.finish-review-card[aria-labelledby="finish-review-order-title"] .finish-review-row:nth-child(3) dd',
    );
    const product = document.querySelector(
      '.finish-review-card[aria-labelledby="finish-review-order-title"] .finish-review-row:nth-child(4) dd',
    );
    return {
      viewport: { width: innerWidth, height: innerHeight },
      document: {
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        clientHeight: document.documentElement.clientHeight,
        scrollHeight: document.documentElement.scrollHeight,
        bodyScrollWidth: document.body.scrollWidth,
        bodyClientWidth: document.body.clientWidth,
        bodyScrollHeight: document.body.scrollHeight,
        bodyClientHeight: document.body.clientHeight,
        scrollX,
        scrollY,
      },
      dialog: box("[data-finish-review-dialog]"),
      cards: Array.from(document.querySelectorAll(".finish-review-card")).map((card) => {
        const rect = card.getBoundingClientRect();
        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
      }),
      left: box(".finish-review-left-stack"),
      right: box(".finish-review-production-card"),
      icons,
      rowAlignment,
      timeValues,
      table: {
        header: rowMetrics(table?.tHead?.rows?.[0]),
        body: rowMetrics(bodyRow),
        total: rowMetrics(table?.tFoot?.rows?.[0]),
        wrapClientWidth: wrap?.clientWidth || 0,
        wrapScrollWidth: wrap?.scrollWidth || 0,
      },
      customer: customer ? {
        clientWidth: customer.clientWidth,
        scrollWidth: customer.scrollWidth,
        clientHeight: customer.clientHeight,
        scrollHeight: customer.scrollHeight,
      } : null,
      product: product ? {
        text: product.textContent.replace(/\s+/g, " ").trim(),
        clientWidth: product.clientWidth,
        scrollWidth: product.scrollWidth,
        clientHeight: product.clientHeight,
        scrollHeight: product.scrollHeight,
      } : null,
    };
  });

  assertEqual(geometry.viewport, viewport, `${label} viewport`);
  assert(geometry.dialog, `${label}: review dialog is missing.`);
  assertEqual(geometry.cards.length, 3, `${label} review card count`);
  assert(
    geometry.document.scrollWidth <= geometry.document.clientWidth + 1
      && geometry.document.scrollHeight <= geometry.document.clientHeight + 1
      && geometry.document.bodyScrollWidth <= geometry.document.bodyClientWidth + 1
      && geometry.document.bodyScrollHeight <= geometry.document.bodyClientHeight + 1
      && geometry.document.scrollX === 0
      && geometry.document.scrollY === 0,
    `${label}: page or body scrolls behind the review.`,
  );
  assert(
    geometry.dialog.x >= 0
      && geometry.dialog.y >= 0
      && geometry.dialog.x + geometry.dialog.width <= viewport.width + 1
      && geometry.dialog.y + geometry.dialog.height <= viewport.height + 1,
    `${label}: review dialog does not fit the viewport.`,
  );
  geometry.cards.forEach((card, index) => {
    assert(
      card.x >= geometry.dialog.x
        && card.y >= geometry.dialog.y
        && card.x + card.width <= geometry.dialog.x + geometry.dialog.width + 1
        && card.y + card.height <= geometry.dialog.y + geometry.dialog.height + 1,
      `${label}: card ${index + 1} exceeds the dialog.`,
    );
  });
  for (let first = 0; first < geometry.cards.length; first += 1) {
    for (let second = first + 1; second < geometry.cards.length; second += 1) {
      assert(
        !boxesOverlap(geometry.cards[first], geometry.cards[second]),
        `${label}: cards ${first + 1} and ${second + 1} overlap.`,
      );
    }
  }
  const leftShare = geometry.left.width / (geometry.left.width + geometry.right.width);
  assert(
    Math.abs(leftShare - 0.4) <= 0.02,
    `${label}: left/right share is ${(leftShare * 100).toFixed(2)}/`
      + `${((1 - leftShare) * 100).toFixed(2)}, expected approximately 40/60.`,
  );
  assert(
    Math.abs(geometry.left.y - geometry.right.y) <= 1
      && Math.abs(
        geometry.left.y + geometry.left.height - geometry.right.y - geometry.right.height,
      ) <= 1,
    `${label}: left and right card regions are not top/bottom aligned.`,
  );
  assertEqual(new Set(geometry.icons.map((icon) => JSON.stringify(icon))).size, 1, `${label} icon treatments`);
  assert(
    geometry.rowAlignment.every(
      ({ labelDelta, valueDelta }) => labelDelta <= 1 && valueDelta <= 1,
    ),
    `${label}: order/time labels or values are not vertically centered.`,
  );
  assertEqual(geometry.timeValues.length, 4, `${label} time value count`);
  assertEqual(
    new Set(geometry.timeValues.map((value) => JSON.stringify(value))).size,
    1,
    `${label} time value computed styles`,
  );
  for (let index = 0; index < 5; index += 1) {
    const metrics = [
      geometry.table.header[index],
      geometry.table.body[index],
      geometry.table.total[index],
    ];
    assert(metrics.every(Boolean), `${label}: column ${index + 1} is missing.`);
    assert(
      Math.max(...metrics.map((metric) => metric.center))
        - Math.min(...metrics.map((metric) => metric.center)) <= 1,
      `${label}: column ${index + 1} centers do not align.`,
    );
    assert(
      Math.max(...metrics.map((metric) => metric.width))
        - Math.min(...metrics.map((metric) => metric.width)) <= 1,
      `${label}: column ${index + 1} widths differ by more than one pixel.`,
    );
  }
  for (const [section, cells] of Object.entries({
    header: geometry.table.header,
    body: geometry.table.body,
    total: geometry.table.total,
  })) {
    assert(
      Math.max(...cells.map((cell) => cell.width))
        - Math.min(...cells.map((cell) => cell.width)) <= 1,
      `${label}: ${section} column widths differ by more than one pixel.`,
    );
  }
  assert(
    [...geometry.table.body, ...geometry.table.total]
      .every((cell) => cell.textAlign === "center"),
    `${label}: pallet, numeric, or total cells are not centered.`,
  );
  assertEqual(geometry.table.total[0].text, "Общо", `${label} total label`);
  assert(
    geometry.table.wrapScrollWidth <= geometry.table.wrapClientWidth + 1,
    `${label}: production table has a horizontal scrollbar.`,
  );
  passed(`${label} geometry and computed-style contract`);
}


async function assertKilogramFormatting(page, label) {
  const result = await page.evaluate(() => {
    const table = document.querySelector("[data-finish-production-summary]");
    const values = [];
    for (const section of [table?.tBodies?.[0], table?.tFoot]) {
      for (const row of Array.from(section?.rows || [])) {
        if (row.cells.length !== 5) continue;
        for (const index of [2, 3, 4]) {
          values.push(row.cells[index].textContent.replace(/\s+/g, " ").trim());
        }
      }
    }
    return {
      values,
      palletWeights: Array.from(
        document.querySelectorAll("[data-finish-pallet-weight]"),
      ).map((cell) => cell.textContent.replace(/\s+/g, " ").trim()),
    };
  });
  assert(result.values.length > 0, `${label}: no kilogram values were rendered.`);
  assert(
    result.values.every((value) => /^-?\d+\.\d$/.test(value)),
    `${label}: invalid kilogram rendering ${JSON.stringify(result.values)}.`,
  );
  assert(
    result.palletWeights.every((value) => value === "0.0"),
    `${label}: physical pallet placeholders are not all 0.0.`,
  );
  passed(`${label} one-decimal kilogram formatting and 0.0 pallet placeholders`);
}


async function assertLongOrderValues(
  page,
  label = "long customer/product values",
  {
    expectedCustomer = VERIFICATION_CONTRACT.expectedLongCustomer,
    expectedProduct = VERIFICATION_CONTRACT.expectedLongProduct,
  } = {},
) {
  const orderValues = page.locator(
    '.finish-review-card[aria-labelledby="finish-review-order-title"] dd',
  );
  const customer = normalized(await orderValues.nth(2).textContent());
  const product = normalized(await orderValues.nth(3).textContent());
  assert(
    customer === expectedCustomer,
    "Long customer value changed.",
  );
  assert(
    product === expectedProduct,
    `Long product value or 0.060 precision changed: ${product}`,
  );
  const fit = await orderValues.evaluateAll((values) => {
    const longValues = values.slice(2);
    const card = longValues[0]?.closest(".finish-review-card");
    if (!card) return null;
    const overflowY = getComputedStyle(card).overflowY;
    const cardNeedsScroll = card.scrollHeight > card.clientHeight + 1;
    const verticallyUserScrollable = ["auto", "scroll"].includes(overflowY);
    const availability = longValues.map((value) => {
      value.scrollIntoView({ block: "nearest", inline: "nearest" });
      const cardBox = card.getBoundingClientRect();
      const valueBox = value.getBoundingClientRect();
      return {
        horizontal: value.scrollWidth <= value.clientWidth + 1
          && valueBox.left >= cardBox.left - 1
          && valueBox.right <= cardBox.right + 1,
        vertical: value.scrollHeight <= value.clientHeight + 1
          && valueBox.top >= cardBox.top - 1
          && valueBox.bottom <= cardBox.bottom + 1,
      };
    });
    card.scrollTop = 0;
    return {
      cardNeedsScroll,
      verticallyUserScrollable,
      availability,
    };
  });
  assert(
    fit
      && (!fit.cardNeedsScroll || fit.verticallyUserScrollable)
      && fit.availability.every(({ horizontal, vertical }) => horizontal && vertical),
    `${label}: long customer or product value is clipped or unreachable.`,
  );
  passed(`${label} fit or remain user-scrollable and 0.060 remains exact`);
}


async function visiblePalletRecord(page) {
  return page.locator(".finish-review-table tbody tr").evaluateAll((rows) => {
    const wrap = document.querySelector(".finish-review-table-wrap").getBoundingClientRect();
    const header = document.querySelector(".finish-review-table thead").getBoundingClientRect();
    const total = document.querySelector(".finish-review-table tfoot").getBoundingClientRect();
    const visibleTop = Math.max(wrap.top, header.bottom);
    const visibleBottom = Math.min(wrap.bottom, total.top);
    const visible = rows.find((row) => {
      const rect = row.getBoundingClientRect();
      return rect.bottom > visibleTop && rect.top < visibleBottom;
    });
    return visible?.cells?.[0]?.textContent.replace(/\s+/g, " ").trim() || "";
  });
}


async function assertStableTableScroll(page, viewport, captureName = null) {
  const selectors = {
    header: ".finish-review-table thead",
    total: ".finish-review-table tfoot",
    footer: ".finish-review-footer",
    left: ".finish-review-left-stack",
  };
  const before = {};
  for (const [name, selector] of Object.entries(selectors)) {
    before[name] = await page.locator(selector).boundingBox();
    assert(before[name], `${name} is missing before table scroll.`);
  }
  const firstBefore = await visiblePalletRecord(page);
  const scrollState = await page.locator(".finish-review-table-wrap").evaluate((wrap) => {
    wrap.scrollTop = Math.max(1, wrap.scrollHeight - wrap.clientHeight);
    wrap.dispatchEvent(new Event("scroll", { bubbles: true }));
    const header = wrap.querySelector(".finish-review-table thead").getBoundingClientRect();
    const total = wrap.querySelector(".finish-review-table tfoot").getBoundingClientRect();
    const lastRow = wrap.querySelector(".finish-review-table tbody tr:last-child")
      .getBoundingClientRect();
    const wrapBox = wrap.getBoundingClientRect();
    return {
      scrollTop: wrap.scrollTop,
      maxScroll: wrap.scrollHeight - wrap.clientHeight,
      lastRowTop: lastRow.top,
      lastRowBottom: lastRow.bottom,
      visibleTop: Math.max(wrapBox.top, header.bottom),
      visibleBottom: Math.min(wrapBox.bottom, total.top),
    };
  });
  await page.locator(".finish-review-table tbody tr").last().waitFor({ state: "visible" });
  const firstAfter = await visiblePalletRecord(page);
  assert(firstBefore && firstAfter, "Table scrolling lost all visible pallet records.");
  assert(scrollState.maxScroll > 0, "Pallet fixture did not create a scrollable table.");
  assert(
    scrollState.scrollTop >= scrollState.maxScroll - 1,
    "Table did not reach its final scroll position.",
  );
  assert(
    scrollState.lastRowBottom > scrollState.visibleTop
      && scrollState.lastRowTop < scrollState.visibleBottom,
    "The final pallet record is not visible after table scrolling.",
  );
  for (const [name, selector] of Object.entries(selectors)) {
    const after = await page.locator(selector).boundingBox();
    assert(after, `${name} is missing after table scroll.`);
    assertBoxStable(before[name], after, `${name} while table scrolls`);
  }
  if (captureName) await captureScreenshot(page, captureName, viewport);
  passed("table scroll changes pallet record while chrome and left cards stay fixed");
}


async function verifyReviewLayouts(page) {
  const [largeCoverage, compactCoverage] = VERIFICATION_CONTRACT.viewportCoverage;
  const [
    activeNormalScreenshot,
    activeMarkedEmptyScreenshot,
    waitingReadOnlyScreenshot,
    waitingScrolledScreenshot,
  ] = VERIFICATION_CONTRACT.screenshots;
  const largeViewport = {
    width: largeCoverage.width,
    height: largeCoverage.height,
  };
  const compactViewport = {
    width: compactCoverage.width,
    height: compactCoverage.height,
  };
  const effectiveCompactViewport = { width: 1093, height: 614 };
  await resetForScenario(page);
  await page.setViewportSize(largeViewport);
  await openActiveReview(page, fixture.cards.active_normal);
  await assertReviewGeometry(page, largeViewport, "active normal 1440x900");
  await assertKilogramFormatting(page, "active normal");
  if (largeCoverage.checkLongOrderValues) await assertLongOrderValues(page);
  await captureScreenshot(page, activeNormalScreenshot, largeViewport);

  await page.setViewportSize(compactViewport);
  await navigate(page, fixture.cards.active_normal);
  await openActiveReview(page, fixture.cards.active_normal);
  await assertReviewGeometry(page, compactViewport, "active normal 1366x768");
  if (compactCoverage.checkLongOrderValues) await assertLongOrderValues(page);

  await page.setViewportSize(effectiveCompactViewport);
  await navigate(page, fixture.cards.active_normal);
  await openActiveReview(page, fixture.cards.active_normal);
  await assertReviewGeometry(
    page,
    effectiveCompactViewport,
    "active normal effective 1093x614",
  );
  await page.locator(
    '.finish-review-card[aria-labelledby="finish-review-order-title"] dd',
  ).evaluateAll((values, stressValues) => {
    values[2].textContent = stressValues.customer;
    values[3].textContent = stressValues.product;
  }, {
    customer: VERIFICATION_CONTRACT.compactStressLongCustomer,
    product: VERIFICATION_CONTRACT.compactStressLongProduct,
  });
  await assertLongOrderValues(page, "active normal effective 1093x614", {
    expectedCustomer: VERIFICATION_CONTRACT.compactStressLongCustomer,
    expectedProduct: VERIFICATION_CONTRACT.compactStressLongProduct,
  });
  await assertStableTableScroll(page, effectiveCompactViewport);

  await page.setViewportSize(compactViewport);

  await navigate(page, fixture.cards.active_marked_empty);
  await openActiveReview(page, fixture.cards.active_marked_empty);
  assert(
    normalized(await page.locator("[data-finish-review-outcome]").textContent())
      === "След потвърждение: Изчаква пренавиване · 4 ролки",
    "Marked active outcome copy is inaccurate.",
  );
  assertEqual(
    normalized(await page.locator("[data-finish-review-confirm]").textContent()),
    "Потвърди край на екструдирането",
    "marked active action copy",
  );
  await captureScreenshot(page, activeMarkedEmptyScreenshot, compactViewport);

  await openActiveReview(page, fixture.cards.active_marked_mixed);
  assert(
    normalized(await page.locator("[data-finish-review-warning]").textContent())
      === "В поръчката има 1 ролка без палет. Искате ли да приключите поръчката?",
    "Mixed assigned/unassigned roll warning is inaccurate.",
  );
  await assertKilogramFormatting(page, "active marked mixed review");
  passed("active marked mixed assigned/unassigned roll state is rendered accurately");

  await page.setViewportSize(largeViewport);
  await openWaitingReview(page, fixture.cards.waiting_many_pallets);
  await assertReviewGeometry(page, largeViewport, "waiting 1440x900");
  await assertKilogramFormatting(page, "waiting review");
  assertEqual(
    await page.locator("[data-finish-review-edit]").count(),
    0,
    "waiting edit control count",
  );
  assert(
    !(await page.locator("[data-finish-review-dialog]").textContent()).includes("Редактирай"),
    "Waiting review contains an edit control.",
  );
  await captureScreenshot(page, waitingReadOnlyScreenshot, largeViewport);
  if (largeCoverage.checkStableTableScroll) {
    await assertStableTableScroll(page, largeViewport);
  }

  await page.setViewportSize(compactViewport);
  await navigate(page, fixture.cards.waiting_many_pallets);
  await openWaitingReview(page, fixture.cards.waiting_many_pallets);
  await assertReviewGeometry(page, compactViewport, "waiting 1366x768");
  if (compactCoverage.checkStableTableScroll) {
    await assertStableTableScroll(page, compactViewport, waitingScrolledScreenshot);
  }
  summary.viewports.push(
    { ...largeViewport, geometry: "passed" },
    { ...compactViewport, geometry: "passed" },
    { ...effectiveCompactViewport, geometry: "passed", screenshot: false },
  );
}


async function verifyActiveEditorRoundTrip(page) {
  await resetForScenario(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await openActiveReview(page, fixture.cards.active_normal);
  const cardId = fixture.cards.active_normal;
  const before = databaseSnapshot(cardId);
  const firstStartBefore = normalized(
    await page.locator("[data-finish-first-start]").textContent(),
  );
  const productionBefore = normalized(
    await page.locator("[data-finish-production-total]").textContent(),
  );
  assertEqual(
    normalized(await page.locator("[data-finish-review-edit]").textContent()),
    "Редактирай",
    "active edit action",
  );
  await page.locator("[data-finish-review-edit]").click();
  await page.locator("[data-timing-editor-overlay]").waitFor({ state: "visible" });
  assert(await page.locator("[data-finish-review-overlay]").isHidden(), "Finish review remained visible behind the editor.");
  const startTime = page.locator(
    '.interval-row[data-source-index="0"] [data-timing-field="start_time"]',
  );
  assertEqual(await startTime.inputValue(), "09:05", "stored active start time");
  await startTime.fill("09:15");
  assertEqual(await startTime.inputValue(), "09:15", "edited active start time");
  const previewResponse = page.waitForResponse((response) => (
    response.request().method() === "POST"
      && new URL(response.url()).pathname.endsWith("/finish-review/preview")
  ));
  await page.locator("[data-timing-save]").click();
  const response = await previewResponse;
  assert(response.ok(), `Authoritative finish preview returned HTTP ${response.status()}.`);
  await page.locator("[data-finish-review-overlay]").waitFor({ state: "visible" });
  assert(await page.locator("[data-timing-editor-overlay]").isHidden(), "Editor did not return to finish review.");
  const firstStartAfter = normalized(
    await page.locator("[data-finish-first-start]").textContent(),
  );
  const productionAfter = normalized(
    await page.locator("[data-finish-production-total]").textContent(),
  );
  assertEqual(firstStartAfter, "06/09/26 09:15", "edited review first start");
  assert(firstStartAfter !== firstStartBefore, "Edited first start did not change in review.");
  assert(productionAfter !== productionBefore, "Edited production total did not change in review.");
  assertEqual(databaseSnapshot(cardId), before, "preview-only active timing snapshot");
  await finishAndWaitForNavigation(
    page,
    () => page.locator("[data-finish-review-confirm]").click(),
  );
  const after = databaseSnapshot(cardId);
  assertEqual(after.card.status, "completed", "edited active final status");
  assertEqual(after.timing[0][0], "2026-09-06 06:15:00", "persisted edited timing start");
  assert(after.timing[0][1], "Edited active finalization did not close timing.");
  passed("real active timing edit updates authoritative review and persists only on finalization");
}


async function verifyDismissals(page) {
  await resetForScenario(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  const cardId = fixture.cards.active_normal;
  const finishPath = `/terminal/cards/${cardId}/finish`;
  let finishPosts = 0;
  const observe = (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === finishPath) {
      finishPosts += 1;
    }
  };
  page.on("request", observe);
  for (const dismissal of ["close", "cancel", "escape"]) {
    const overlay = await openActiveReview(page, cardId);
    if (dismissal === "close") {
      await overlay.locator("[data-finish-review-close]").click();
    } else if (dismissal === "cancel") {
      await overlay.locator("[data-finish-review-cancel]").click();
    } else {
      await page.keyboard.press("Escape");
    }
    await overlay.waitFor({ state: "hidden" });
    assert(
      await page.locator('form[data-timing-finish-review="true"] button[type="submit"]').evaluate(
        (button) => button === document.activeElement,
      ),
      `${dismissal} did not restore focus to the finish trigger.`,
    );
  }
  page.off("request", observe);
  assertEqual(finishPosts, 0, "finish POST count after close/cancel/Escape");
  passed("close, cancel, and Escape issue no finish POST and restore focus");
}


async function finishAndWaitForNavigation(page, action) {
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    action(),
  ]);
}


async function verifyMarkedTransition(page) {
  await resetForScenario(page);
  const cardId = fixture.cards.active_marked_empty;
  const before = databaseSnapshot(cardId);
  const overlay = await openActiveReview(page, cardId);
  assertEqual(
    normalized(await overlay.locator("[data-finish-review-outcome]").textContent()),
    "След потвърждение: Изчаква пренавиване · 4 ролки",
    "marked transition outcome",
  );
  await finishAndWaitForNavigation(
    page,
    () => overlay.locator("[data-finish-review-confirm]").click(),
  );
  const after = databaseSnapshot(cardId);
  assertEqual(after.card.status, "awaiting_rewinding", "marked active final status");
  assert(after.card.finished_at, "Marked active finish did not record extrusion end.");
  assertEqual(before.timing[0][1], null, "marked active timing before finish");
  assert(after.timing[0][1], "Marked active finish did not close timing.");
  passed("marked initial confirmation enters waiting with accurate copy and action");
}


async function verifyWaitingFinalization(page) {
  await resetForScenario(page);
  const cardId = fixture.cards.waiting_marker_cleared;
  const before = databaseSnapshot(cardId);
  const overlay = await openWaitingReview(page, cardId);
  const waitingForm = page.locator('form[data-waiting-finish-review="true"]');
  assertEqual(await waitingForm.locator('input[name="loaded_version"]').count(), 1, "waiting loaded-version field count");
  assertEqual(await waitingForm.locator('input[name="review_token"]').count(), 0, "waiting review-token field count");
  assertEqual(await waitingForm.locator('input[name="timing_draft"]').count(), 0, "waiting timing-draft field count");
  assertEqual(await waitingForm.locator('input[name="finish_review_preview"]').count(), 0, "waiting preview field count");
  await finishAndWaitForNavigation(
    page,
    () => overlay.locator("[data-finish-review-confirm]").click(),
  );
  const after = databaseSnapshot(cardId);
  assertEqual(after.card.status, "completed", "waiting final status");
  assertEqual(after.card.first_started_at, before.card.first_started_at, "waiting first-start preservation");
  assertEqual(after.card.finished_at, before.card.finished_at, "waiting finished-at preservation");
  assertEqual(after.timing, before.timing, "waiting timing-ledger preservation");
  passed("waiting confirmation is tokenless and preserves timing snapshot");
}


async function verifyWaitingValidationFailure(page) {
  await resetForScenario(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  const cardId = fixture.cards.waiting_zero_rolls;
  const before = databaseSnapshot(cardId);
  const overlay = await openWaitingReview(page, cardId);
  await finishAndWaitForNavigation(
    page,
    () => overlay.locator("[data-finish-review-confirm]").click(),
  );
  const reopened = page.locator("[data-finish-review-overlay]");
  await reopened.waitFor({ state: "visible" });
  const message = normalized(await reopened.locator("[data-finish-review-alert]").textContent());
  assert(message.includes("ролка"), `Waiting zero-roll validation message is missing: ${message}`);
  assert(
    await reopened.locator("[data-finish-review-confirm]").isDisabled(),
    "Waiting validation failure left confirmation enabled.",
  );
  assertEqual(databaseSnapshot(cardId), before, "waiting zero-roll database snapshot");
  await captureScreenshot(
    page,
    VERIFICATION_CONTRACT.screenshots[4],
    { width: 1366, height: 768 },
  );
  passed("zero-roll waiting finalization failure keeps review and message available");
}


async function verifyActiveValidationFailure(page) {
  await resetForScenario(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  const cardId = fixture.cards.active_normal;
  const overlay = await openActiveReview(page, cardId);
  mutateFixtureState(cardId, "delete-rolls-without-version");
  const beforeConfirm = databaseSnapshot(cardId);
  await finishAndWaitForNavigation(
    page,
    () => overlay.locator("[data-finish-review-confirm]").click(),
  );
  const reopened = page.locator("[data-finish-review-overlay]");
  await reopened.waitFor({ state: "visible" });
  const message = normalized(
    await reopened.locator("[data-finish-review-alert]").textContent(),
  );
  assert(message.includes("ролка"), `Active no-roll validation message is missing: ${message}`);
  assert(
    await reopened.locator("[data-finish-review-confirm]").isDisabled(),
    "Active validation failure left confirmation enabled.",
  );
  assert(
    await reopened.locator("[data-finish-review-edit]").isDisabled(),
    "Active validation failure left timing edit enabled.",
  );
  assertEqual(databaseSnapshot(cardId), beforeConfirm, "active no-roll database snapshot");
  passed("failed active confirmation reopens with confirm and edit disabled");
}


async function verifyActiveStaleSafety(page) {
  await resetForScenario(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  const cardId = fixture.cards.active_normal;
  await navigate(page, cardId);
  const consoleErrorCountBefore = summary.consoleErrors.length;
  mutateFixtureState(cardId, "bump-version");
  const competingSnapshot = databaseSnapshot(cardId);
  const responsePromise = page.waitForResponse((response) => (
    response.request().method() === "POST"
      && new URL(response.url()).pathname === `/terminal/cards/${cardId}/finish-review`
  ));
  await page.locator('form[data-timing-finish-review="true"] button[type="submit"]').click();
  const response = await responsePromise;
  assertEqual(response.status(), 409, "active stale review response status");
  const editor = page.locator("[data-timing-editor-overlay]");
  await editor.waitFor({ state: "visible" });
  assert(await editor.locator("[data-timing-save]").isDisabled(), "Active stale Save is enabled.");
  assert(await editor.locator("[data-timing-reload]").isVisible(), "Active stale reload is hidden.");
  assert(
    await page.locator("[data-finish-review-overlay]").isHidden(),
    "Active stale flow left an orphaned finish review visible.",
  );
  assertEqual(databaseSnapshot(cardId), competingSnapshot, "active stale database snapshot");
  const expectedConflictErrors = summary.consoleErrors.splice(consoleErrorCountBefore);
  assert(
    expectedConflictErrors.length === 1
      && expectedConflictErrors[0].includes("409 (Conflict)"),
    `Active stale flow emitted unexpected console errors: ${JSON.stringify(expectedConflictErrors)}.`,
  );
  summary.expectedConsoleErrors.push(...expectedConflictErrors);
  passed("active stale review is reload-only with no completion write");
}


async function verifyWaitingStaleSafety(page) {
  for (const dismissal of ["close", "cancel", "escape"]) {
    await resetForScenario(page);
    await page.setViewportSize({ width: 1366, height: 768 });
    const cardId = fixture.cards.waiting_marker_cleared;
    await navigate(page, cardId);
    const trigger = page.locator("[data-waiting-finish-trigger]");
    assert(await trigger.isEnabled(), "Waiting trigger was not controller-ready before stale test.");
    mutateFixtureState(cardId, "bump-version");
    const competingSnapshot = databaseSnapshot(cardId);
    await trigger.click();
    const overlay = page.locator("[data-finish-review-overlay]");
    await overlay.waitFor({ state: "visible" });
    await finishAndWaitForNavigation(
      page,
      () => overlay.locator("[data-finish-review-confirm]").click(),
    );
    const reopened = page.locator("[data-finish-review-overlay]");
    await reopened.waitFor({ state: "visible" });
    assert(
      await reopened.locator("[data-finish-review-confirm]").isDisabled(),
      "Waiting stale confirmation is enabled.",
    );
    assert(
      await reopened.locator("[data-finish-review-reload]").isVisible(),
      "Waiting stale reload is hidden.",
    );
    assert(
      await page.locator("[data-waiting-finish-trigger]").isDisabled(),
      "Waiting stale topbar trigger is enabled.",
    );
    if (dismissal === "close") {
      await reopened.locator("[data-finish-review-close]").click();
    } else if (dismissal === "cancel") {
      await reopened.locator("[data-finish-review-cancel]").click();
    } else {
      await page.keyboard.press("Escape");
    }
    await reopened.waitFor({ state: "hidden" });
    const safeReload = page.locator("#terminal-refresh-alert-button");
    assert(await safeReload.isVisible(), `${dismissal}: stale page reload control is hidden.`);
    assert(
      await safeReload.evaluate((reload) => reload === document.activeElement),
      `${dismissal}: locked waiting review did not restore focus to the safe reload control.`,
    );
    assert(
      await page.locator("[data-waiting-finish-trigger]").isDisabled(),
      `${dismissal}: locked waiting finish trigger was re-enabled.`,
    );
    assertEqual(
      databaseSnapshot(cardId),
      competingSnapshot,
      `${dismissal}: waiting stale database snapshot`,
    );
  }
  passed(
    "locked waiting Close, Cancel, and Escape preserve data and focus the safe reload control",
  );
}


async function verifyActiveShiftLossSafety(page) {
  await resetForScenario(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  const cardId = fixture.cards.active_normal;
  const overlay = await openActiveReview(page, cardId);
  const before = databaseSnapshot(cardId);
  mutateFixtureState(cardId, "end-shift");
  await finishAndWaitForNavigation(
    page,
    () => overlay.locator("[data-finish-review-confirm]").click({ force: true }),
  );
  assertEqual(databaseSnapshot(cardId), before, "active shift-loss database snapshot");
  assert(
    await page.locator('[data-shift-window="true"][data-shift-blocking="true"]').isVisible(),
    "Active shift loss did not render the shift gate.",
  );
  assert(
    await page.locator("[data-finish-review-overlay]").isHidden(),
    "Active shift loss rendered an open controllerless review.",
  );
  assertEqual(
    await page.locator("[data-finish-review-confirm]:visible:enabled").count(),
    0,
    "active shift-loss actionable confirmation count",
  );
  passed("active shift loss renders only the normal shift gate and no open review");
}


async function verifyWaitingShiftLossWithoutController(page) {
  await resetForScenario(page);
  await page.setViewportSize({ width: 1366, height: 768 });
  const cardId = fixture.cards.waiting_marker_cleared;
  const overlay = await openWaitingReview(page, cardId);
  const before = databaseSnapshot(cardId);
  mutateFixtureState(cardId, "end-shift");
  const consoleErrorCountBefore = summary.consoleErrors.length;
  const failedRequestCountBefore = summary.failedRequests.length;
  const waitingModulePattern = "**/static/js/waiting_finish_review.mjs";
  const abortWaitingModule = (route) => route.abort();
  await page.route(waitingModulePattern, abortWaitingModule);
  try {
    await finishAndWaitForNavigation(
      page,
      () => overlay.locator("[data-finish-review-confirm]").click(),
    );
  } finally {
    await page.unroute(waitingModulePattern, abortWaitingModule);
  }
  const expectedFailedRequests = summary.failedRequests.splice(failedRequestCountBefore);
  assert(
    expectedFailedRequests.length === 1
      && expectedFailedRequests[0].method === "GET"
      && new URL(expectedFailedRequests[0].url).pathname
        === "/static/js/waiting_finish_review.mjs",
    `Waiting shift-loss flow emitted unexpected failed requests: ${JSON.stringify(expectedFailedRequests)}.`,
  );
  summary.expectedFailedRequests.push(...expectedFailedRequests);
  const expectedConsoleErrors = summary.consoleErrors.splice(consoleErrorCountBefore);
  assert(
    expectedConsoleErrors.length === 1
      && expectedConsoleErrors[0].includes("net::ERR_FAILED"),
    `Waiting shift-loss flow emitted unexpected console errors: ${JSON.stringify(expectedConsoleErrors)}.`,
  );
  summary.expectedConsoleErrors.push(...expectedConsoleErrors);
  assertEqual(databaseSnapshot(cardId), before, "waiting shift-loss database snapshot");
  const shiftGate = page.locator(
    '[data-shift-window="true"][data-shift-blocking="true"]',
  );
  assert(await shiftGate.isVisible(), "Waiting shift loss did not render the shift gate.");
  assert(
    (await page.locator("body").textContent()).includes(
      "Отворете смяна, преди да продължите.",
    ),
    "Waiting shift loss did not render the normal no-active-shift error.",
  );
  assert(
    await page.locator("[data-finish-review-overlay]").isHidden(),
    "Waiting shift loss left a controllerless review open above the shift gate.",
  );
  assertEqual(
    await page.locator("[data-finish-review-overlay] button:visible").count(),
    0,
    "waiting shift-loss visible dead review control count",
  );
  const recovery = shiftGate.locator('[data-shift-confirm-open="start"]');
  assert(
    await recovery.isVisible() && await recovery.isEnabled(),
    "Waiting shift-loss recovery control is not accessible.",
  );
  await recovery.focus();
  assert(
    await recovery.evaluate((button) => button === document.activeElement),
    "Waiting shift-loss recovery control cannot receive focus.",
  );
  assert(
    await shiftGate.locator("[data-shift-dialog]").evaluate((dialog) => {
      const box = dialog.getBoundingClientRect();
      const topmost = document.elementFromPoint(
        box.left + box.width / 2,
        box.top + box.height / 2,
      );
      return Boolean(topmost && dialog.contains(topmost));
    }),
    "Waiting shift gate is not the topmost recovery surface.",
  );
  passed(
    "waiting shift loss survives controller failure with only accessible shift recovery",
  );
}


async function verifyActiveRapidDoubleActivation(page) {
  await resetForScenario(page);
  const cardId = fixture.cards.active_marked_empty;
  const finishPath = `/terminal/cards/${cardId}/finish`;
  let finishPosts = 0;
  const observe = (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === finishPath) {
      finishPosts += 1;
    }
  };
  page.on("request", observe);
  const overlay = await openActiveReview(page, cardId);
  await finishAndWaitForNavigation(page, () => (
    overlay.locator("[data-finish-review-confirm]").evaluate((button) => {
      button.click();
      button.click();
    })
  ));
  page.off("request", observe);
  assertEqual(finishPosts, 1, "active finish request count after rapid double activation");
  assertEqual(databaseSnapshot(cardId).card.status, "awaiting_rewinding", "active rapid final status");
  passed("active rapid double activation produces one finish request");
}


async function verifyRapidDoubleActivation(page) {
  await resetForScenario(page);
  const cardId = fixture.cards.waiting_marker_cleared;
  const finishPath = `/terminal/cards/${cardId}/finish`;
  let finishPosts = 0;
  const observe = (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === finishPath) {
      finishPosts += 1;
    }
  };
  page.on("request", observe);
  const overlay = await openWaitingReview(page, cardId);
  await finishAndWaitForNavigation(page, () => (
    overlay.locator("[data-finish-review-confirm]").evaluate((button) => {
      button.click();
      button.click();
    })
  ));
  page.off("request", observe);
  assertEqual(finishPosts, 1, "finish request count after rapid double activation");
  passed("rapid double activation produces one finish request");
}


async function main() {
  let browser;
  try {
    browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();
    monitorPage(page);

    await verifyPreControllerWaitingTriggerSafety(page);
    await verifyReviewLayouts(page);
    await verifyActiveEditorRoundTrip(page);
    await verifyDismissals(page);
    await verifyMarkedTransition(page);
    await verifyWaitingFinalization(page);
    await verifyWaitingValidationFailure(page);
    await verifyActiveValidationFailure(page);
    await verifyActiveStaleSafety(page);
    await verifyWaitingStaleSafety(page);
    await verifyActiveShiftLossSafety(page);
    await verifyWaitingShiftLossWithoutController(page);
    await verifyActiveRapidDoubleActivation(page);
    await verifyRapidDoubleActivation(page);

    assertEqual(summary.consoleErrors, [], "unexpected console errors");
    assertEqual(summary.pageErrors, [], "unexpected page errors");
    assertEqual(summary.failedRequests, [], "unexpected failed requests");
    assertEqual(summary.crossOriginRequests, [], "unexpected cross-origin requests");
    assertExactScreenshotEvidence(summary);
    passed("exact five-file screenshot evidence contract");
    summary.status = "passed";
    writeSummary();
    console.log("Order finish review verification passed.");
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
    // Preserve the original validation failure.
  }
  console.error(error.stack || error);
  process.exitCode = 1;
});
