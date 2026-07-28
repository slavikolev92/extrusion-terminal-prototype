import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

function requiredEnvironment(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Required environment variable ${name} is missing.`);
  }
  return value;
}

const baseURL = requiredEnvironment("BASE_URL").replace(/\/+$/, "");
const runtimeInput = requiredEnvironment("RUNTIME_DIR");
const artifactInput = requiredEnvironment("ARTIFACT_DIR");
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = fs.realpathSync(path.resolve(scriptDir, ".."));
const runtimeRoot = path.resolve(repoRoot, ".test-runtime");
const artifactRoot = path.resolve(repoRoot, "artifacts", "ui-checks");
const runtimeDir = path.resolve(repoRoot, runtimeInput);
const artifactDir = path.resolve(repoRoot, artifactInput);
const artifactDirRelative = path.relative(repoRoot, artifactDir);
const requestedDatabasePath = path.join(runtimeDir, "shift-ui.sqlite3");
const fixturePath = path.join(runtimeDir, "shift-management-orders.csv");
const summaryPath = path.join(artifactDir, "shift-management-ui-summary.json");
const orderOne = "SHIFT-UI-001";
const orderTwo = "SHIFT-UI-002";
const shiftTimeZone = "Europe/Sofia";
const requiredPostCorrectionHistoryTransitions = 3;

const screenshotNames = [
  "admin-shift-count.png",
  "terminal-header-no-active.png",
  "start-shift-selection.png",
  "start-shift-confirmation.png",
  "terminal-header-active.png",
  "full-recipe-layout.png",
  "active-shift-window.png",
  "end-shift-confirmation.png",
  "full-shift-history.png",
  "ended-shift-summary.png",
  "historical-shift-summary.png",
];
const evidenceOutputNames = [
  ...screenshotNames,
  "qa-start-shift-confirmation-1672x941.png",
  "qa-terminal-header-1077x735.png",
  "shift-management-ui-summary.json",
];

const importFields = [
  "order_number",
  "order_date",
  "delivery_date",
  "customer",
  "city",
  "product_type",
  "ordered_gross_kg",
  "ordered_rolls",
  "ordered_meters",
  "ordered_units",
  "product_form",
  "material",
  "size_thickness",
  "notes",
  "printing_sequence",
  "extrusion_sequence",
  "rewinding_slitting_sequence",
  "confection_sequence",
  "extrusion_next_operation",
  "extrusion_folding",
  "extrusion_treatment",
  "raw_material_a",
  "raw_material_b",
  "raw_material_c",
  "linear_pe",
  "antistatic",
  "masterbatch",
  "chalk",
  "packaging_method",
];

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function assertEqual(actual, expected, label) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `${label}: expected ${JSON.stringify(expected)}, found ${JSON.stringify(actual)}`,
    );
  }
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
    if (fs.existsSync(current)) {
      assert(!fs.lstatSync(current).isSymbolicLink(), message);
    }
  }
}

function assertEvidenceOutputLeaves() {
  for (const outputName of evidenceOutputNames) {
    const outputPath = path.join(artifactDir, outputName);
    const metadata = fs.lstatSync(outputPath, { throwIfNoEntry: false });
    if (!metadata) {
      continue;
    }
    assert(
      !metadata.isSymbolicLink(),
      `Evidence output path must not be a symlink: ${outputPath}`,
    );
    assert(
      metadata.isFile(),
      `Evidence output path must be absent or a regular file: ${outputPath}`,
    );
  }
}

assert(
  isStrictChild(runtimeRoot, runtimeDir),
  "RUNTIME_DIR must be below .test-runtime.",
);
assert(
  isStrictChild(artifactRoot, artifactDir),
  "ARTIFACT_DIR must be below artifacts/ui-checks.",
);
assertNoSymlinkComponents(
  repoRoot,
  runtimeRoot,
  ".test-runtime guard root must not be a symlink.",
);
assertNoSymlinkComponents(
  repoRoot,
  runtimeDir,
  "RUNTIME_DIR guard path must not contain symlinks.",
);
assertNoSymlinkComponents(
  repoRoot,
  artifactDir,
  "ARTIFACT_DIR guard path must not contain symlinks.",
);
assert(fs.existsSync(runtimeDir), `RUNTIME_DIR does not exist: ${runtimeDir}`);
assert(fs.statSync(runtimeDir).isDirectory(), `RUNTIME_DIR is not a directory: ${runtimeDir}`);
assert(fs.existsSync(artifactDir), `ARTIFACT_DIR does not exist: ${artifactDir}`);
assert(fs.statSync(artifactDir).isDirectory(), `ARTIFACT_DIR is not a directory: ${artifactDir}`);

const canonicalRuntimeRoot = fs.realpathSync(runtimeRoot);
const canonicalRuntimeDir = fs.realpathSync(runtimeDir);
const canonicalArtifactRoot = fs.realpathSync(artifactRoot);
const canonicalArtifactDir = fs.realpathSync(artifactDir);
assert(
  isStrictChild(canonicalRuntimeRoot, canonicalRuntimeDir),
  "RUNTIME_DIR resolves outside .test-runtime.",
);
assert(
  isStrictChild(canonicalArtifactRoot, canonicalArtifactDir),
  "ARTIFACT_DIR resolves outside artifacts/ui-checks.",
);
assertEvidenceOutputLeaves();
assert(
  fs.existsSync(requestedDatabasePath),
  `Temporary database does not exist: ${requestedDatabasePath}`,
);
const databasePath = fs.realpathSync(requestedDatabasePath);
assert(
  isStrictChild(canonicalRuntimeDir, databasePath),
  "Temporary database must resolve inside RUNTIME_DIR.",
);
assert(
  fs.statSync(databasePath).isFile(),
  `Temporary database is not a regular file: ${databasePath}`,
);
assertNoSymlinkComponents(
  runtimeDir,
  fixturePath,
  "CSV fixture path must not be a symlink.",
);

async function verifyTerminalHeader(page, expectedLabel, expectedActive) {
  const header = page.locator(".terminal-header");
  const logo = page.locator(".terminal-brand");
  const centerNav = page.locator(".terminal-global-nav");
  const actions = centerNav.locator(".terminal-header-action");
  await header.waitFor({ state: "visible" });
  assertEqual(
    await page.locator(".terminal-header .terminal-header-action").count(),
    4,
    "terminal header total action count",
  );
  assertEqual(await actions.count(), 3, "centered terminal header action count");

  const widths = [];
  for (let index = 0; index < await actions.count(); index += 1) {
    const box = await actions.nth(index).boundingBox();
    assert(box !== null, `Missing header action box ${index}`);
    widths.push(box.width);
    const fits = await actions.nth(index).evaluate((element) => ({
      horizontal: element.scrollWidth <= element.clientWidth,
      vertical: element.scrollHeight <= element.clientHeight,
      whiteSpace: getComputedStyle(element).whiteSpace,
    }));
    assert(fits.horizontal, `Header action ${index} overflows horizontally`);
    assert(fits.vertical, `Header action ${index} overflows vertically`);
    assertEqual(fits.whiteSpace, "nowrap", `Header action ${index} wrapping`);
  }
  assert(Math.max(...widths) - Math.min(...widths) <= 1, "Header action widths differ");

  const viewport = page.viewportSize();
  const headerBox = await header.boundingBox();
  const logoBox = await logo.boundingBox();
  const centerBox = await centerNav.boundingBox();
  const shiftAction = page.locator('[data-terminal-action="shift"]');
  const shiftBox = await shiftAction.boundingBox();
  const headerPadding = await header.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      left: Number.parseFloat(style.paddingLeft),
      right: Number.parseFloat(style.paddingRight),
    };
  });
  assert(
    viewport !== null && headerBox !== null && logoBox !== null
      && centerBox !== null && shiftBox !== null,
    "Missing terminal header geometry",
  );
  assert(
    Math.abs(centerBox.x + centerBox.width / 2 - viewport.width / 2) <= 2,
    "Order actions are not centered against the viewport",
  );
  assert(headerBox.x >= 0, "Terminal header begins outside the viewport");
  assert(
    headerBox.x + headerBox.width <= viewport.width
      && headerBox.y >= 0
      && headerBox.y + headerBox.height <= viewport.height,
    "Terminal header extends outside the viewport",
  );
  assert(
    logoBox.x >= headerBox.x + headerPadding.left
      && logoBox.x + logoBox.width <= headerBox.x + headerBox.width - headerPadding.right
      && logoBox.y >= headerBox.y
      && logoBox.y + logoBox.height <= headerBox.y + headerBox.height
      && logoBox.x >= 0
      && logoBox.x + logoBox.width <= viewport.width,
    "Terminal logo is outside the header or viewport bounds",
  );
  assert(
    shiftBox.x >= headerBox.x + headerPadding.left
      && shiftBox.x + shiftBox.width <= headerBox.x + headerBox.width - headerPadding.right
      && shiftBox.y >= headerBox.y
      && shiftBox.y + shiftBox.height <= headerBox.y + headerBox.height
      && shiftBox.x >= 0
      && shiftBox.x + shiftBox.width <= viewport.width,
    "Shift action is outside the header or viewport bounds",
  );
  assert(
    logoBox.x + logoBox.width <= centerBox.x,
    "Terminal logo overlaps the centered order actions",
  );
  assert(
    centerBox.x + centerBox.width <= shiftBox.x,
    "Centered order actions overlap the shift action",
  );
  assert(
    Math.abs(
      shiftBox.x + shiftBox.width
      - (headerBox.x + headerBox.width - headerPadding.right)
    ) <= 2,
    "Shift action is not aligned to the header right content edge",
  );

  const shiftHeaderLabel = shiftAction.locator("[data-shift-header-label]");
  assertEqual(await shiftHeaderLabel.count(), 1, "shift header status label count");
  const actualShiftLabel = normalizeText(await shiftHeaderLabel.textContent());
  assertEqual(actualShiftLabel, expectedLabel, "shift header label");
  assertEqual(
    /^Смяна\s+\d+$/.test(actualShiftLabel),
    expectedActive,
    "shift header active-label state",
  );
}

async function verifyTerminalHeaderAtBothViewports(page, expectedLabel, expectedActive) {
  await page.setViewportSize({ width: 1536, height: 1024 });
  await verifyTerminalHeader(page, expectedLabel, expectedActive);
  await page.setViewportSize({ width: 1366, height: 768 });
  await verifyTerminalHeader(page, expectedLabel, expectedActive);
  await page.setViewportSize({ width: 1536, height: 1024 });
}

async function verifyLiveClock(clock) {
  const before = await clock.getAttribute("datetime");
  const visible = normalizeText(await clock.textContent());
  const currentYear = String(new Date().getFullYear());
  const visiblePattern = new RegExp(
    `^\\d{1,2} [а-я]+ ${currentYear}, \\d{2}:\\d{2}$`,
  );
  assert(visiblePattern.test(visible), `Bulgarian clock format: ${visible}`);
  assert(!/\d{2}:\d{2}:\d{2}/.test(visible), "Visible clock must not show seconds");
  await clock.page().waitForTimeout(1100);
  const after = await clock.getAttribute("datetime");
  assert(before !== after, "Live clock datetime did not advance");
}

function utcMinute(value) {
  const normalized = /Z$/.test(value) ? value : `${value.replace(" ", "T")}Z`;
  const timestamp = Date.parse(normalized);
  assert(Number.isFinite(timestamp), `Could not parse UTC timestamp: ${value}`);
  return Math.floor(timestamp / 60_000);
}

function assertSavedShiftMinuteMatchesPreview(preview, saved) {
  if (preview.text === saved.text) {
    return;
  }
  assertEqual(
    utcMinute(saved.datetime) - utcMinute(preview.datetime),
    1,
    `saved Sofia minute after preview (${preview.text} -> ${saved.text})`,
  );
}

async function assertShiftStateOpen(page, expectedState, label) {
  const window = page.locator('[data-shift-window="true"]');
  assertEqual(await window.isVisible(), true, `${label} visibility`);
  assertEqual(await window.getAttribute("data-shift-state"), expectedState, `${label} state`);
}

async function verifyShiftFocusWraps(page, label) {
  const focusable = page.locator(
    '[data-shift-dialog] button:not([disabled]):visible, '
      + '[data-shift-dialog] select:not([disabled]):visible, '
      + '[data-shift-dialog] a[href]:visible, '
      + '[data-shift-dialog] [tabindex]:not([tabindex="-1"]):visible',
  );
  const count = await focusable.count();
  assert(count >= 1, `${label} needs at least one focusable control`);
  const first = focusable.first();
  const last = focusable.last();

  await first.focus();
  await page.keyboard.press("Shift+Tab");
  assertEqual(
    await last.evaluate((element) => element === document.activeElement),
    true,
    `${label} Shift+Tab focus wrap`,
  );

  await last.focus();
  await page.keyboard.press("Tab");
  assertEqual(
    await first.evaluate((element) => element === document.activeElement),
    true,
    `${label} Tab focus wrap`,
  );
}

async function verifyBlockingShiftInteractions(page, expectedState, label) {
  const window = page.locator('[data-shift-window="true"]');
  await page.keyboard.press("Escape");
  await assertShiftStateOpen(page, expectedState, `${label} after Escape`);
  await window.click({ position: { x: 4, y: 4 } });
  await assertShiftStateOpen(page, expectedState, `${label} after backdrop`);
}

async function waitForShiftActionFocus(page, label) {
  await page.waitForFunction(() => document.activeElement?.id === "shift-open");
  await page.waitForTimeout(50);
  assertEqual(
    await page.locator("#shift-open").evaluate((element) => element === document.activeElement),
    true,
    label,
  );
}

async function verifyDismissibleShiftInteractions(page, label) {
  const window = page.locator('[data-shift-window="true"]');
  const shiftAction = page.locator("#shift-open");
  await verifyShiftFocusWraps(page, label);

  await page.keyboard.press("Escape");
  await window.waitFor({ state: "hidden" });
  await waitForShiftActionFocus(page, `${label} focus return after Escape`);

  await shiftAction.click();
  await assertShiftStateOpen(page, "overview", `${label} reopened after Escape`);
  await window.click({ position: { x: 4, y: 4 } });
  await window.waitFor({ state: "hidden" });
  await waitForShiftActionFocus(page, `${label} focus return after backdrop`);

  await shiftAction.click();
  await assertShiftStateOpen(page, "overview", `${label} reopened after backdrop`);
}

function assertCanonicalShiftURL(page, expectedPathname, label) {
  const url = new URL(page.url());
  assertEqual(url.pathname, expectedPathname, `${label} selected-card pathname`);
  for (const parameter of ["shift_view", "shift_id", "shift_page", "handoff"]) {
    assertEqual(url.searchParams.has(parameter), false, `${label} transient ${parameter}`);
  }
}

async function verifyDismissibleShiftURLsDoNotSurviveRefresh(
  context,
  cardId,
  completedShiftId,
) {
  const probe = await context.newPage();
  const pathname = `/terminal/cards/${cardId}`;
  try {
    await probe.goto(`${baseURL}${pathname}`, { waitUntil: "networkidle" });
    await probe.locator("#shift-open").click();
    await probe.locator('[data-shift-pane="overview"]').waitFor({ state: "visible" });
    assertEqual(
      await probe.locator('[data-shift-close]:visible').count(),
      1,
      "clean-url overview close control",
    );
    for (const viewport of [
      { width: 1536, height: 1024 },
      { width: 1366, height: 768 },
    ]) {
      await probe.setViewportSize(viewport);
      const dialogBox = await probe.locator("[data-shift-dialog]").boundingBox();
      const currentCardBox = await probe.locator(".shift-current-card").boundingBox();
      const startIconBox = await probe.locator(".shift-start-time > img").boundingBox();
      assert(dialogBox !== null, `Missing shift dialog at ${viewport.width}x${viewport.height}`);
      assert(currentCardBox !== null, `Missing current-shift card at ${viewport.width}x${viewport.height}`);
      assert(startIconBox !== null, `Missing shift start icon at ${viewport.width}x${viewport.height}`);
      assert(
        dialogBox.width <= 1180,
        `Shift dialog remains too wide at ${viewport.width}x${viewport.height}: ${dialogBox.width}`,
      );
      assert(
        currentCardBox.height <= 120,
        `Current-shift card remains too tall at ${viewport.width}x${viewport.height}: ${currentCardBox.height}`,
      );
      assert(
        startIconBox.width <= 36 && startIconBox.height <= 36,
        `Current-shift start icon remains too large at ${viewport.width}x${viewport.height}`,
      );
    }
    await probe.setViewportSize({ width: 1536, height: 1024 });

    const cases = [
      ["overview", `${pathname}?shift_view=overview`],
      ["history", `${pathname}?shift_view=history`],
      ["summary", `${pathname}?shift_view=summary&shift_id=${completedShiftId}&shift_page=1`],
    ];
    for (const [state, relativeURL] of cases) {
      await probe.goto(`${baseURL}${relativeURL}`, { waitUntil: "networkidle" });
      await probe.locator(`[data-shift-pane="${state}"]`).waitFor({ state: "visible" });
      assertCanonicalShiftURL(probe, pathname, `${state} after server render`);
      await probe.locator('[data-shift-close]').click();
      await probe.locator('[data-shift-window="true"]').waitFor({ state: "hidden" });
      assertCanonicalShiftURL(probe, pathname, `${state} after close`);
      await probe.reload({ waitUntil: "networkidle" });
      assertEqual(
        await probe.locator('[data-shift-window="true"]').isHidden(),
        true,
        `${state} remains closed after refresh`,
      );
    }
  } finally {
    await probe.close();
  }
}

async function verifyFullRecipeRemainsReachable(page, cardId) {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto(`${baseURL}/terminal/cards/${cardId}`, { waitUntil: "networkidle" });
  const details = page.locator(".details-body");
  const recipeRows = page.locator(".recipe-row");
  assertEqual(await recipeRows.count(), 7, "full recipe component count");
  const scrollState = await details.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
    overflowY: getComputedStyle(element).overflowY,
  }));
  assert(
    scrollState.scrollHeight > scrollState.clientHeight,
    "Full-recipe fixture did not exercise vertical overflow",
  );
  assert(
    ["auto", "scroll"].includes(scrollState.overflowY),
    `Full recipe cannot be scrolled by the operator: overflow-y=${scrollState.overflowY}`,
  );
  await details.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  const detailsBox = await details.boundingBox();
  const lastRecipeRowBox = await recipeRows.last().boundingBox();
  assert(detailsBox !== null && lastRecipeRowBox !== null, "Missing full-recipe geometry");
  assert(
    lastRecipeRowBox.y >= detailsBox.y
      && lastRecipeRowBox.y + lastRecipeRowBox.height <= detailsBox.y + detailsBox.height + 1,
    "The final recipe component is not reachable after scrolling",
  );
  await page.screenshot({
    path: path.join(artifactDir, "full-recipe-layout.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1536, height: 1024 });
}

function assertGuardedPathSafety() {
  const relativeRuntimePath = path.relative(canonicalRuntimeRoot, canonicalRuntimeDir);
  const relativeArtifactPath = path.relative(canonicalArtifactRoot, canonicalArtifactDir);
  const canonicalDatabaseRelative = path.relative(canonicalRuntimeDir, databasePath);
  const fixtureRelative = path.relative(canonicalRuntimeDir, fixturePath);
  assert(
    relativeRuntimePath && !relativeRuntimePath.startsWith("..") && !path.isAbsolute(relativeRuntimePath),
    `Runtime directory must remain below .test-runtime: ${runtimeDir}`,
  );
  assert(
    relativeArtifactPath && !relativeArtifactPath.startsWith("..") && !path.isAbsolute(relativeArtifactPath),
    `Artifact directory must remain below artifacts/ui-checks: ${artifactDir}`,
  );
  assert(
    canonicalDatabaseRelative === "shift-ui.sqlite3",
    `Temporary database must be a regular file inside RUNTIME_DIR: ${databasePath}`,
  );
  assert(
    fixtureRelative === "shift-management-orders.csv",
    `CSV fixture must be inside RUNTIME_DIR: ${fixturePath}`,
  );
  assert(
    databasePath !== path.join(repoRoot, "data", "extrusion_terminal.sqlite3"),
    "Refusing to use the runtime database",
  );
}

function csvCell(value) {
  const text = String(value ?? "");
  if (!/[",\n\r]/.test(text)) {
    return text;
  }
  return `"${text.replaceAll('"', '""')}"`;
}

function writeCsvFixture() {
  const rows = [
    {
      order_number: orderOne,
      order_date: "2026-07-25",
      delivery_date: "2026-07-28",
      customer: "Shift UI Alpha",
      product_type: "PE film Alpha",
      ordered_gross_kg: "500",
      product_form: "roll",
      material: "LDPE",
      size_thickness: "600/0.050",
      extrusion_sequence: "1",
      raw_material_a: "LDPE; Alpha | 35%",
      raw_material_b: "LDPE; Alpha B | 25%",
      raw_material_c: "MDPE; Alpha C | 15%",
      linear_pe: "LLDPE; Alpha Linear | 15%",
      antistatic: "Antistatic; Alpha Agent | 2%",
      masterbatch: "Masterbatch; Alpha White | 5%",
      chalk: "Filler; Alpha Chalk | 3%",
      packaging_method: "rolls",
    },
    {
      order_number: orderTwo,
      order_date: "2026-07-25",
      delivery_date: "2026-07-29",
      customer: "Shift UI Beta",
      product_type: "PE film Beta",
      ordered_gross_kg: "600",
      product_form: "roll",
      material: "LDPE",
      size_thickness: "700/0.060",
      extrusion_sequence: "1",
      raw_material_a: "LDPE; Beta | 35%",
      raw_material_b: "LDPE; Beta B | 25%",
      raw_material_c: "MDPE; Beta C | 15%",
      linear_pe: "LLDPE; Beta Linear | 15%",
      antistatic: "Antistatic; Beta Agent | 2%",
      masterbatch: "Masterbatch; Beta White | 5%",
      chalk: "Filler; Beta Chalk | 3%",
      packaging_method: "rolls",
    },
  ];
  const lines = [
    importFields.join(","),
    ...rows.map((row) => importFields.map((field) => csvCell(row[field] || "")).join(",")),
  ];
  fs.writeFileSync(fixturePath, `${lines.join("\n")}\n`, "utf8");
}

function databaseSnapshot() {
  const python = String.raw`
import json
import sqlite3
import sys
from pathlib import Path

database_path = Path(sys.argv[1]).resolve()
connection = sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)
connection.row_factory = sqlite3.Row

def one(query, parameters=()):
    row = connection.execute(query, parameters).fetchone()
    return dict(row) if row is not None else None

def many(query, parameters=()):
    return [dict(row) for row in connection.execute(query, parameters).fetchall()]

cards = {}
for order_number in sys.argv[2:]:
    card = one(
        """
        SELECT id, order_number, status, version, tare_weight
        FROM cards
        WHERE order_number = ?
        """,
        (order_number,),
    )
    if card is None:
        continue
    card_id = int(card["id"])
    card["timing_segments"] = many(
        """
        SELECT id, started_at, ended_at
        FROM production_time_segments
        WHERE card_id = ?
        ORDER BY id
        """,
        (card_id,),
    )
    card["rolls"] = many(
        """
        SELECT id, roll_number, gross_weight, tare_weight, net_weight,
               shift_occurrence_id
        FROM roll_entries
        WHERE card_id = ?
        ORDER BY roll_number, id
        """,
        (card_id,),
    )
    cards[order_number] = card

payload = {
    "configuration": one(
        """
        SELECT id, shift_count, version, updated_at
        FROM terminal_configuration
        WHERE id = 1
        """
    ),
    "active_shift": one(
        """
        SELECT id, shift_number, started_at, ended_at, version
        FROM shift_occurrences
        WHERE ended_at IS NULL
        """
    ),
    "completed_shifts": many(
        """
        SELECT id, shift_number, started_at, ended_at, version
        FROM shift_occurrences
        WHERE ended_at IS NOT NULL
        ORDER BY ended_at DESC, id DESC
        """
    ),
    "card_count": connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0],
    "shift_count": connection.execute("SELECT COUNT(*) FROM shift_occurrences").fetchone()[0],
    "cards": cards,
    "integrity_check": connection.execute("PRAGMA integrity_check").fetchone()[0],
    "foreign_key_errors": [list(row) for row in connection.execute("PRAGMA foreign_key_check")],
}
print(json.dumps(payload, sort_keys=True))
connection.close()
`;
  const result = spawnSync(
    path.join(repoRoot, ".venv", "bin", "python"),
    ["-c", python, databasePath, orderOne, orderTwo],
    { cwd: repoRoot, encoding: "utf8" },
  );
  if (result.status !== 0) {
    throw new Error(
      `Could not inspect the temporary database: ${normalizeText(result.stderr || result.stdout)}`,
    );
  }
  return JSON.parse(result.stdout);
}

function writeDatabaseConfiguration(configuration) {
  const python = String.raw`
import sqlite3
import sys
from pathlib import Path

database_path = Path(sys.argv[1]).resolve()
shift_count = int(sys.argv[2])
version = int(sys.argv[3])
updated_at = sys.argv[4]
connection = sqlite3.connect(database_path)
try:
    connection.execute("BEGIN IMMEDIATE")
    updated = connection.execute(
        """
        UPDATE terminal_configuration
        SET shift_count = ?, version = ?, updated_at = ?
        WHERE id = 1
        """,
        (shift_count, version, updated_at),
    )
    if updated.rowcount != 1:
        raise RuntimeError("terminal configuration singleton is missing")
    connection.commit()
finally:
    connection.close()
`;
  const result = spawnSync(
    path.join(repoRoot, ".venv", "bin", "python"),
    [
      "-c",
      python,
      databasePath,
      String(configuration.shift_count),
      String(configuration.version),
      String(configuration.updated_at),
    ],
    { cwd: repoRoot, encoding: "utf8" },
  );
  if (result.status !== 0) {
    throw new Error(
      `Could not set the temporary identity marker: ${normalizeText(result.stderr || result.stdout)}`,
    );
  }
}

function databaseIdentityMarker(configuration) {
  const digest = createHash("sha256")
    .update(`${fs.realpathSync(databasePath)}\0${configuration.version}\0${configuration.updated_at}`)
    .digest();
  const candidateShiftCount = 1 + (digest.readUInt32BE(0) % 99);
  return {
    shift_count: candidateShiftCount === configuration.shift_count
      ? (candidateShiftCount % 99) + 1
      : candidateShiftCount,
    version: 100_000 + (digest.readUInt32BE(4) % 900_000),
    updated_at: configuration.updated_at,
  };
}

async function readServerConfiguration(page) {
  const response = await page.goto(`${baseURL}/admin/settings`, { waitUntil: "networkidle" });
  assert(response?.ok(), `Server identity preflight returned HTTP ${response?.status() || "unknown"}.`);
  return {
    shift_count: Number(await page.locator('input[name="shift_count"]').inputValue()),
    version: Number(await page.locator('input[name="loaded_version"]').inputValue()),
  };
}

async function verifyHealthDatabaseIdentity() {
  const response = await fetch(`${baseURL}/health`);
  assert(response.ok, `Health preflight returned HTTP ${response.status || "unknown"}.`);
  const health = await response.json();
  assertEqual(
    fs.realpathSync(path.resolve(health.database_path)),
    databasePath,
    "server database identity",
  );
}

async function verifyServerDatabaseIdentity(page, initialConfiguration) {
  const marker = databaseIdentityMarker(initialConfiguration);
  let observed;
  try {
    writeDatabaseConfiguration(marker);
    observed = await readServerConfiguration(page);
  } finally {
    writeDatabaseConfiguration(initialConfiguration);
  }

  const restored = databaseSnapshot().configuration;
  assertEqual(restored, initialConfiguration, "runtime configuration restored after identity preflight");
  if (
    observed.shift_count !== marker.shift_count
    || observed.version !== marker.version
  ) {
    throw new Error(
      "Selected HTTP server is not backed by the required runtime database.",
    );
  }

  const normalizedServerConfiguration = await readServerConfiguration(page);
  assertEqual(
    normalizedServerConfiguration,
    {
      shift_count: initialConfiguration.shift_count,
      version: initialConfiguration.version,
    },
    "server configuration restored after identity preflight",
  );
}

function cardIdFromHref(href) {
  const match = String(href || "").match(/\/admin\/cards\/(\d+)(?:[/?#]|$)/);
  assert(match, `Could not read card id from href: ${href}`);
  return Number(match[1]);
}

async function importAndReleaseOrders(page) {
  await page.goto(`${baseURL}/admin/import`, { waitUntil: "networkidle" });
  await page.locator('input[name="csv_file"]').setInputFiles(fixturePath);
  await page.getByRole("button", { name: "Импортирай CSV" }).click();
  await page.waitForLoadState("networkidle");
  await page.locator(".notice", { hasText: "2 импортирани" }).waitFor();

  const cardIds = {};
  for (const orderNumber of [orderOne, orderTwo]) {
    const resultRow = page.locator("tbody tr", { hasText: orderNumber }).first();
    await resultRow.waitFor();
    cardIds[orderNumber] = cardIdFromHref(
      await resultRow.locator('a[href^="/admin/cards/"]').getAttribute("href"),
    );
  }

  await page.goto(`${baseURL}/admin/planning`, { waitUntil: "networkidle" });
  const releases = [
    [orderOne, "1"],
    [orderTwo, "2"],
  ];
  for (const [orderNumber, machineId] of releases) {
    const row = page.locator(`#draft-card-${cardIds[orderNumber]}`);
    await row.waitFor();
    await row.getByRole("button", { name: "Планирай", exact: true }).click();
    const modal = page.locator("#planning-modal");
    await modal.waitFor({ state: "visible" });
    assertEqual(
      await modal.locator("#planning-modal-order").textContent(),
      orderNumber,
      `${orderNumber} planning modal order`,
    );
    assertEqual(
      await modal.locator("#planning-modal-form").getAttribute("action"),
      `/admin/cards/${cardIds[orderNumber]}/release`,
      `${orderNumber} planning modal action`,
    );
    await modal.locator("#planning-modal-machine").selectOption(machineId);
    await modal.locator("#planning-modal-sequence").fill("1");
    await Promise.all([
      page.waitForNavigation({ waitUntil: "networkidle" }),
      modal.getByRole("button", { name: "Запази", exact: true }).click(),
    ]);
    assertEqual(await page.locator(`#draft-card-${cardIds[orderNumber]}`).count(), 0, `${orderNumber} draft row after release`);
    const machineQueue = page.locator("article", {
      has: page.getByRole("heading", { name: `Машина ${machineId}`, exact: true }),
    });
    await machineQueue.locator(`a[href="/admin/cards/${cardIds[orderNumber]}"]`).waitFor();
  }
  return cardIds;
}

async function configureThreeShifts(page) {
  await page.goto(`${baseURL}/admin/settings`, { waitUntil: "networkidle" });
  const countInput = page.locator('input[name="shift_count"]');
  await countInput.fill("3");
  await page.getByRole("button", { name: "Запази" }).click();
  await page.waitForLoadState("networkidle");
  await page.locator(".notice").waitFor();
  assertEqual(await page.locator('input[name="shift_count"]').inputValue(), "3", "saved shift count");
  await page.screenshot({
    path: path.join(artifactDir, "admin-shift-count.png"),
    fullPage: true,
  });
}

async function verifyNoActiveShiftGate(page, expectedSuggestedNumber) {
  const window = page.locator('[data-shift-window="true"]');
  await window.waitFor({ state: "visible" });
  assertEqual(await window.getAttribute("data-shift-state"), "gate", "shift gate state");
  assertEqual(await window.getAttribute("data-shift-blocking"), "true", "shift gate blocking state");
  assertEqual(await page.locator(".app").getAttribute("inert"), "", "underlying terminal inert state");
  assertEqual(
    await window.evaluate((element) => getComputedStyle(element).backgroundColor),
    "rgba(31, 41, 51, 0.46)",
    "gate dimming overlay",
  );
  assertEqual(await window.locator("[data-shift-close]").count(), 0, "non-dismissible gate close controls");
  assertEqual(await window.locator(".shift-window-header").count(), 0, "gate generic header count");
  assertEqual(
    await window.locator("[data-shift-dialog]").getAttribute("aria-labelledby"),
    "shift-start-title",
    "gate accessible title",
  );
  const gateDialogBox = await window.locator("[data-shift-dialog]").boundingBox();
  assert(gateDialogBox !== null, "Missing gate dialog geometry");
  assert(Math.abs(gateDialogBox.width - 600) <= 2, `Gate width drifted: ${gateDialogBox.width}`);
  assert(Math.abs(gateDialogBox.height - 560) <= 2, `Gate height drifted: ${gateDialogBox.height}`);
  for (const selector of [
    '.shift-start-icon--selection img[src$="/shift-switch.svg"]',
    '.shift-live-time-card--start img[src$="/calendar-clock.svg"]',
  ]) {
    const loaded = await window.locator(selector).evaluate((image) => (
      image.complete && image.naturalWidth > 0 && image.naturalHeight > 0
    ));
    assert(loaded, `Gate icon did not load: ${selector}`);
  }
  const selectorBox = await window.locator("[data-shift-start-number]").boundingBox();
  const timeCardBox = await window.locator(".shift-live-time-card--start").boundingBox();
  assert(selectorBox !== null && selectorBox.height >= 52, "Gate selector is too short");
  assert(timeCardBox !== null && timeCardBox.height >= 92, "Gate time card is too short");
  assertEqual(
    await window.locator('[data-shift-start-number] option').evaluateAll((options) =>
      options.map((option) => option.value),
    ),
    ["1", "2", "3"],
    "configured start choices",
  );
  assertEqual(
    await window.locator('[data-shift-start-number]').inputValue(),
    expectedSuggestedNumber,
    "suggested next shift number",
  );
}

async function startShift(page, shiftNumber, captureEvidence = false) {
  const window = page.locator('[data-shift-window="true"]');
  const before = databaseSnapshot();
  assertEqual(before.active_shift, null, "active shift before start confirmation");
  const occurrenceCountBefore = before.shift_count;
  await window.locator('[data-shift-start-number]').selectOption(shiftNumber);
  await verifyLiveClock(
    window.locator('[data-shift-pane="gate"] [data-shift-live-clock]'),
  );
  if (captureEvidence) {
    await page.screenshot({
      path: path.join(artifactDir, "start-shift-selection.png"),
      fullPage: true,
    });
  }
  await window.locator('[data-shift-confirm-open="start"]').click();
  const confirmation = window.locator('[data-shift-pane="start-confirm"]');
  await confirmation.waitFor({ state: "visible" });
  assertEqual(
    normalizeText(await confirmation.locator("h2").textContent()),
    "Потвърждение за начало",
    "start confirmation heading",
  );
  assertEqual(await window.locator(".shift-window-header").count(), 0, "start confirmation generic header count");
  assertEqual(
    await window.locator("[data-shift-dialog]").getAttribute("aria-labelledby"),
    "shift-start-confirmation-title",
    "start confirmation accessible title",
  );
  const confirmationBox = await window.locator("[data-shift-dialog]").boundingBox();
  assert(confirmationBox !== null, "Missing start confirmation geometry");
  assert(Math.abs(confirmationBox.width - 600) <= 2, `Start confirmation width drifted: ${confirmationBox.width}`);
  assert(Math.abs(confirmationBox.height - 560) <= 2, `Start confirmation height drifted: ${confirmationBox.height}`);
  const sharedVisualSelectors = [
    [".shift-state-intro--centered h2", "title", ["color", "fontSize", "fontWeight"]],
    [".shift-state-intro--centered p", "subtitle", ["color", "fontSize", "fontWeight"]],
    [".shift-start-icon", "hero icon", ["height", "width"]],
    [".shift-primary-action", "primary action", ["color", "fontSize", "fontWeight", "minHeight"]],
  ];
  for (const [selector, label, properties] of sharedVisualSelectors) {
    const selectionStyle = await window.locator(`[data-shift-pane="gate"] ${selector}`).evaluate((element, selectedProperties) => {
      const style = getComputedStyle(element);
      return Object.fromEntries(selectedProperties.map((property) => [property, style[property]]));
    }, properties);
    const confirmationStyle = await confirmation.locator(selector).evaluate((element, selectedProperties) => {
      const style = getComputedStyle(element);
      return Object.fromEntries(selectedProperties.map((property) => [property, style[property]]));
    }, properties);
    assertEqual(confirmationStyle, selectionStyle, `shared start ${label} visual style`);
  }
  for (const selector of [
    '.shift-start-icon--confirmation img[src$="/check-circle.svg"]',
    '.shift-start-details-card img[src$="/calendar.svg"]',
    '.shift-start-details-card img[src$="/clock.svg"]',
  ]) {
    const loaded = await confirmation.locator(selector).evaluate((image) => (
      image.complete && image.naturalWidth > 0 && image.naturalHeight > 0
    ));
    assert(loaded, `Start confirmation icon did not load: ${selector}`);
  }
  const confirmationButtonBoxes = await confirmation.locator(".shift-confirm-actions button").evaluateAll(
    (buttons) => buttons.map((button) => button.getBoundingClientRect().width),
  );
  assertEqual(confirmationButtonBoxes.length, 2, "start confirmation button count");
  assert(
    Math.abs(confirmationButtonBoxes[0] - confirmationButtonBoxes[1]) <= 1,
    "Start confirmation buttons are not equal width",
  );
  assertEqual(
    normalizeText(await confirmation.locator("[data-shift-start-selection]").textContent()),
    shiftNumber,
    "start confirmation shift number",
  );
  assertEqual(
    normalizeText(await confirmation.locator("[data-shift-start-question-number]").textContent()),
    shiftNumber,
    "start confirmation question shift number",
  );
  await verifyLiveClock(confirmation.locator("[data-shift-live-clock]"));
  if (captureEvidence) {
    await verifyShiftFocusWraps(page, "start confirmation");
    await verifyBlockingShiftInteractions(
      page,
      "start-confirm",
      "start confirmation",
    );
    await confirmation.locator('[data-shift-confirm-back="gate"]').click();
    await assertShiftStateOpen(page, "gate", "start confirmation explicit Back");
    await window.locator('[data-shift-confirm-open="start"]').click();
    await confirmation.waitFor({ state: "visible" });
  }

  const pending = databaseSnapshot();
  assertEqual(pending.active_shift, null, "active shift before final confirmation");
  assertEqual(
    pending.shift_count,
    occurrenceCountBefore,
    "occurrence count before final confirmation",
  );
  if (captureEvidence) {
    await page.screenshot({
      path: path.join(artifactDir, "start-shift-confirmation.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.screenshot({
      path: path.join(artifactDir, "qa-start-shift-confirmation-1672x941.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 1536, height: 1024 });
  }

  const preview = {
    text: normalizeText(await confirmation.locator("[data-shift-live-clock]").textContent()),
    datetime: await confirmation.locator("[data-shift-live-clock]").getAttribute("datetime"),
  };
  await window.locator('[data-shift-confirm-submit="start"]').click();
  await page.waitForLoadState("networkidle");
  await window.waitFor({ state: "hidden" });

  const after = databaseSnapshot();
  assert(after.active_shift !== null, "Final confirmation did not create an active shift");
  assertEqual(after.active_shift.shift_number, Number(shiftNumber), "started shift number");
  assertEqual(after.shift_count, occurrenceCountBefore + 1, "occurrence count after confirmation");
  assert(
    normalizeText(after.active_shift.started_at) !== "",
    "Server did not persist the active shift start time",
  );
  await page.locator("#shift-open").click();
  const activeWindow = page.locator('[data-shift-window="true"]');
  await activeWindow.locator('[data-shift-pane="overview"]').waitFor({ state: "visible" });
  assertEqual(
    normalizeText(await activeWindow.locator("#shift-window-title").textContent()),
    "Управление на смяната",
    "active overview title after reopening",
  );
  const savedStart = activeWindow.locator(".shift-start-time time");
  assertSavedShiftMinuteMatchesPreview(preview, {
    text: normalizeText(await savedStart.textContent()),
    datetime: await savedStart.getAttribute("datetime"),
  });
  await page.keyboard.press("Escape");
  await activeWindow.waitFor({ state: "hidden" });
  return after.active_shift;
}

async function endActiveShiftAndReturnToGate(page, expectedSuggestedNumber) {
  await page.locator("#shift-open").click();
  const window = page.locator('[data-shift-window="true"]');
  await window.locator('[data-shift-pane="overview"]').waitFor({ state: "visible" });
  await window.locator('[data-shift-confirm-open="end"]').click();
  const confirmation = window.locator('[data-shift-pane="end-confirm"]');
  await confirmation.waitFor({ state: "visible" });
  await verifyLiveClock(confirmation.locator("[data-shift-live-clock]"));
  await window.locator('[data-shift-confirm-submit="end"]').click();
  await page.waitForURL((url) => (
    url.searchParams.get("shift_view") === "summary"
      && url.searchParams.get("handoff") === "1"
  ), { waitUntil: "networkidle" });
  assertEqual(
    await page.locator('[data-shift-window="true"]').getAttribute("data-shift-blocking"),
    "true",
    "supplemental handoff summary blocking state",
  );
  assertEqual(
    await page.locator('[data-shift-window="true"] [data-shift-close]').count(),
    0,
    "supplemental handoff close controls",
  );
  await page.locator("[data-shift-ack]").click();
  await page.waitForURL((url) => !url.searchParams.has("shift_view"), {
    waitUntil: "networkidle",
  });
  await verifyNoActiveShiftGate(page, expectedSuggestedNumber);
}

async function openCard(page, cardId) {
  await page.goto(`${baseURL}/terminal/cards/${cardId}`, { waitUntil: "networkidle" });
  await page.locator(`form[action="/terminal/cards/${cardId}/timing/start"], form[action="/terminal/cards/${cardId}/timing/pause"]`).first().waitFor();
}

async function startCardAndSaveTare(page, cardId, tareWeight) {
  await openCard(page, cardId);
  await page.locator(`form[action="/terminal/cards/${cardId}/timing/start"] button`).click();
  await page.waitForLoadState("networkidle");
  const tareInput = page.locator('input[data-current-tare-input="true"]');
  await tareInput.fill(tareWeight);
  await Promise.all([
    page.waitForURL((url) => url.searchParams.get("notice") === "roll_defaults_saved", {
      waitUntil: "networkidle",
    }),
    tareInput.press("Enter"),
  ]);
}

async function addRoll(page, cardId, grossWeight) {
  await openCard(page, cardId);
  const grossInput = page.locator(`#add-roll-form-${cardId} input[name="gross_weight"]`);
  await grossInput.fill(grossWeight);
  await Promise.all([
    page.waitForURL((url) => url.searchParams.get("notice") === "roll_saved", {
      waitUntil: "networkidle",
    }),
    page.locator(`button[form="add-roll-form-${cardId}"]`).click(),
  ]);
}

function invariantCardState(snapshot) {
  return Object.fromEntries(
    [orderOne, orderTwo].map((orderNumber) => {
      const card = snapshot.cards[orderNumber];
      return [
        orderNumber,
        {
          status: card.status,
          timing_segments: card.timing_segments.map((segment) => ({
            id: segment.id,
            started_at: segment.started_at,
            ended_at: segment.ended_at,
          })),
          rolls: card.rolls.map((roll) => ({
            id: roll.id,
            roll_number: roll.roll_number,
            gross_weight: Number(roll.gross_weight),
            shift_occurrence_id: roll.shift_occurrence_id,
          })),
        },
      ];
    }),
  );
}

async function changeShiftNumberAndVerifyInvariants(page, cardId, before) {
  await openCard(page, cardId);
  await page.locator("#shift-open").click();
  const window = page.locator('[data-shift-window="true"]');
  await window.locator('[data-shift-pane="overview"]').waitFor({ state: "visible" });
  const occurrenceIdBefore = await window.locator('input[name="shift_occurrence_id"]').first().inputValue();
  const startTimeBefore = await window.locator(".shift-start-time time").getAttribute("datetime");
  assertEqual(Number(occurrenceIdBefore), before.active_shift.id, "displayed occurrence id before relabel");
  assertEqual(startTimeBefore, before.active_shift.started_at, "displayed start time before relabel");

  await Promise.all([
    page.waitForURL((url) => url.searchParams.get("notice") === "shift_changed", {
      waitUntil: "networkidle",
    }),
    window.locator('[data-shift-number-select]').selectOption("2"),
  ]);

  const after = databaseSnapshot();
  assertEqual(after.active_shift.id, before.active_shift.id, "occurrence id after relabel");
  assertEqual(after.active_shift.started_at, before.active_shift.started_at, "start time after relabel");
  assertEqual(after.active_shift.shift_number, 2, "corrected shift number");
  assertEqual(
    invariantCardState(after),
    invariantCardState(before),
    "card status, open timing segments, and roll links after relabel",
  );
  assertEqual(
    after.cards[orderOne].rolls[0].shift_occurrence_id,
    before.active_shift.id,
    "existing roll occurrence link after relabel",
  );

  const reloadedWindow = page.locator('[data-shift-window="true"]');
  await reloadedWindow.locator('[data-shift-pane="overview"]').waitFor({ state: "visible" });
  assertEqual(
    Number(await reloadedWindow.locator('input[name="shift_occurrence_id"]').first().inputValue()),
    before.active_shift.id,
    "displayed occurrence id after relabel",
  );
  assertEqual(
    await reloadedWindow.locator(".shift-start-time time").getAttribute("datetime"),
    before.active_shift.started_at,
    "displayed start time after relabel",
  );
  assertEqual(
    await reloadedWindow.locator('[data-shift-number-select]').inputValue(),
    "2",
    "displayed corrected shift number",
  );
  await verifyTerminalHeader(page, "Смяна 2", true);
  assertEqual(
    await reloadedWindow.locator('[data-shift-close]:visible').count(),
    1,
    "active overview close control",
  );
  assertEqual(
    await reloadedWindow.locator("[data-shift-history-preview-id]").count(),
    3,
    "active overview three-row history preview",
  );
  assertEqual(
    (await reloadedWindow.locator(".shift-history-table thead th").allTextContents()).map(normalizeText),
    ["Смяна", "Начало", "Край", "Различни изделия", "Ролки", "Бруто, кг", "Преглед"],
    "active overview history columns",
  );
  await page.screenshot({
    path: path.join(artifactDir, "active-shift-window.png"),
    fullPage: true,
  });
  await reloadedWindow.locator('[data-shift-close]').click();
}

async function summaryRows(page) {
  const result = {};
  const rows = page.locator("[data-shift-summary-orders] tr");
  for (let index = 0; index < await rows.count(); index += 1) {
    const cells = (await rows.nth(index).locator("td").allTextContents()).map(normalizeText);
    result[cells[0]] = {
      customer: cells[1],
      product_type: cells[2],
      roll_count: Number(cells[3]),
      gross_weight_display: cells[4],
      gross_weight: Number(cells[4]),
    };
  }
  return result;
}

async function verifySummary(page, expected) {
  const window = page.locator('[data-shift-window="true"]');
  await window.locator('[data-shift-pane="summary"]').waitFor({ state: "visible" });
  assertEqual(
    (await window.locator(".shift-summary-table thead th").allTextContents()).map(normalizeText),
    ["Производствена поръчка", "Клиент", "Вид изделие", "Брой ролки", "Бруто, кг"],
    "shift summary columns",
  );
  const rows = await summaryRows(page);
  assertEqual(Object.keys(rows).sort(), [orderOne, orderTwo], "summary production orders");
  assertEqual(Object.keys(rows).length, expected.distinctItems, "summary distinct order count");
  assertEqual(rows[orderOne].roll_count, expected.orderOneRolls, `${orderOne} roll total`);
  assertEqual(rows[orderOne].gross_weight, expected.orderOneGross, `${orderOne} gross total`);
  assertEqual(
    rows[orderOne].gross_weight_display,
    expected.orderOneGross.toFixed(1),
    `${orderOne} one-decimal gross display`,
  );
  assertEqual(rows[orderTwo].roll_count, expected.orderTwoRolls, `${orderTwo} roll total`);
  assertEqual(rows[orderTwo].gross_weight, expected.orderTwoGross, `${orderTwo} gross total`);
  assertEqual(
    rows[orderTwo].gross_weight_display,
    expected.orderTwoGross.toFixed(1),
    `${orderTwo} one-decimal gross display`,
  );
  assertEqual(
    Object.values(rows).reduce((total, row) => total + row.roll_count, 0),
    expected.totalRolls,
    "summary total rolls",
  );
  assertEqual(
    Object.values(rows).reduce((total, row) => total + row.gross_weight, 0),
    expected.totalGross,
    "summary total gross",
  );
  return normalizeText(
    `${await window.locator(".shift-summary-metadata").textContent()} ${await window.locator(".shift-summary-table").textContent()}`,
  );
}

async function endShiftAndVerifySummary(page, expectedOccurrenceId) {
  await page.locator("#shift-open").click();
  const window = page.locator('[data-shift-window="true"]');
  await window.locator('[data-shift-confirm-open="end"]').click();
  const confirmation = window.locator('[data-shift-pane="end-confirm"]');
  await confirmation.waitFor({ state: "visible" });
  assertEqual(
    normalizeText(await confirmation.locator("h2").textContent()),
    "Потвърждение за приключване",
    "end confirmation heading",
  );
  const endConfirmationBox = await window.locator("[data-shift-dialog]").boundingBox();
  assert(endConfirmationBox !== null, "Missing end confirmation geometry");
  assert(Math.abs(endConfirmationBox.width - 600) <= 2, `End confirmation width drifted: ${endConfirmationBox.width}`);
  assert(Math.abs(endConfirmationBox.height - 560) <= 2, `End confirmation height drifted: ${endConfirmationBox.height}`);
  assertEqual(
    await window.locator(".shift-window-header:visible").count(),
    0,
    "end confirmation visible shell headers",
  );
  await page.screenshot({
    path: path.join(artifactDir, "end-shift-confirmation.png"),
    fullPage: true,
  });
  assert(
    normalizeText(await confirmation.textContent()).includes("Смяна 2"),
    "End-shift confirmation did not identify corrected shift 2",
  );
  await verifyLiveClock(confirmation.locator("[data-shift-live-clock]"));
  await verifyShiftFocusWraps(page, "end confirmation");
  await verifyBlockingShiftInteractions(page, "end-confirm", "end confirmation");
  await confirmation.locator('[data-shift-confirm-back="overview"]').click();
  await assertShiftStateOpen(page, "overview", "end confirmation explicit Back");
  await window.locator('[data-shift-confirm-open="end"]').click();
  await confirmation.waitFor({ state: "visible" });
  await window.locator('[data-shift-confirm-submit="end"]').click();
  await page.waitForURL((url) => (
    url.searchParams.get("shift_view") === "summary"
      && url.searchParams.get("handoff") === "1"
  ), { waitUntil: "networkidle" });
  const completedId = Number(new URL(page.url()).searchParams.get("shift_id"));
  assertEqual(completedId, expectedOccurrenceId, "completed occurrence id");
  assertEqual(
    await page.locator('[data-shift-window="true"]').getAttribute("data-shift-blocking"),
    "true",
    "handoff summary blocking state",
  );
  assertEqual(
    await page.locator('[data-shift-window="true"] [data-shift-close]').count(),
    0,
    "handoff summary close controls",
  );
  await verifyBlockingShiftInteractions(page, "summary", "handoff summary");
  const text = await verifySummary(page, {
    distinctItems: 2,
    orderOneRolls: 2,
    orderOneGross: 50,
    orderTwoRolls: 1,
    orderTwoGross: 40,
    totalRolls: 3,
    totalGross: 90,
  });
  await verifyTerminalHeaderAtBothViewports(page, "Няма активна смяна", false);
  await page.screenshot({
    path: path.join(artifactDir, "ended-shift-summary.png"),
    fullPage: true,
  });
  return { completedId, text };
}

async function openHistoricalSummary(page, completedId, expectedRolls, expectedGross) {
  const window = page.locator('[data-shift-window="true"]');
  const historyRow = window.locator(`[data-shift-history-id="${completedId}"]`);
  await historyRow.waitFor({ state: "visible" });
  const cells = (await historyRow.locator("td").allTextContents()).map(normalizeText);
  assertEqual(Number(cells[3]), 2, "history distinct items");
  assertEqual(Number(cells[4]), expectedRolls, "history roll total");
  assertEqual(Number(cells[5]), expectedGross, "history gross total");
  assertEqual(cells[5], expectedGross.toFixed(1), "history one-decimal gross display");
  await historyRow.getByRole("link", { name: "Преглед" }).click();
  await page.locator('[data-shift-pane="summary"]').waitFor({ state: "visible" });
  assertCanonicalShiftURL(
    page,
    new URL(page.url()).pathname,
    "historical summary navigation",
  );
  assertEqual(
    await page.locator('[data-shift-window="true"]').getAttribute("data-shift-blocking"),
    "false",
    "historical summary blocking state",
  );
  assertEqual(
    await page.locator('[data-shift-window="true"] [data-shift-close]:visible').count(),
    1,
    "historical summary close control",
  );
}

async function openShiftHistoryFromCurrentOverview(page, expectedPathname, label) {
  await page.locator("#shift-open").click();
  const window = page.locator('[data-shift-window="true"]');
  await window.locator('[data-shift-pane="overview"]').waitFor({ state: "visible" });
  const historyLink = window.getByRole("link", { name: "Виж всички" });
  await historyLink.waitFor({ state: "visible" });
  const historyHref = await historyLink.getAttribute("href");
  assert(historyHref, `${label} History link is missing href`);
  const historyURL = new URL(historyHref, page.url());
  assertEqual(historyURL.pathname, expectedPathname, `${label} History link pathname`);
  assertEqual(
    historyURL.searchParams.get("shift_view"),
    "history",
    `${label} History link state`,
  );

  const response = await page.goto(historyURL.href, { waitUntil: "networkidle" });
  assert(response?.ok(), `${label} History navigation returned HTTP ${response?.status() || "unknown"}`);
  await page.locator('[data-shift-pane="history"]').waitFor({ state: "visible" });
  assertCanonicalShiftURL(page, expectedPathname, label);
}

async function correctFirstRoll(page, cardId, completedId) {
  await openCard(page, cardId);
  const firstRow = page.locator(".roll-row[data-roll-id]").first();
  const firstRollId = await firstRow.getAttribute("data-roll-id");
  assert(firstRollId !== null, "First roll row is missing its row id");
  await firstRow.getByRole("button", {
    name: "Редактирай ролка 1",
    exact: true,
  }).click();
  const firstRollActions = page.locator(`[data-roll-actions-for="${firstRollId}"]`);
  await firstRollActions.waitFor({ state: "visible" });
  assertEqual(await firstRow.getAttribute("data-roll-edit-open"), "true", "first roll editor state");
  assertEqual(
    await page.locator(".roll-row[data-roll-edit-open='true']").count(),
    1,
    "one open roll editor during historical correction",
  );
  const grossInput = firstRow.locator('input[name="gross_weight"]');
  assertEqual(await grossInput.inputValue(), "20", "first roll gross before correction");
  await grossInput.fill("25");
  await Promise.all([
    page.waitForURL((url) => url.searchParams.get("notice") === "roll_updated", {
      waitUntil: "networkidle",
    }),
    firstRollActions.locator("[data-roll-row-save]").click(),
  ]);
  const corrected = databaseSnapshot();
  assertEqual(Number(corrected.cards[orderOne].rolls[0].gross_weight), 25, "corrected roll gross");
  assertEqual(
    corrected.cards[orderOne].rolls[0].shift_occurrence_id,
    completedId,
    "corrected roll occurrence attribution",
  );
}

async function verifySecondPageStaleGate(context, firstPage, cardId, before) {
  const postedFromFirstPage = [];
  firstPage.on("request", (request) => {
    if (request.method() === "POST") {
      postedFromFirstPage.push(request.url());
    }
  });

  await openCard(firstPage, cardId);
  const finishForm = firstPage.locator(
    `form[action="/terminal/cards/${cardId}/finish"][data-finish-confirm-form="true"]`,
  );
  const finishButton = finishForm.getByRole("button", { name: "Приключи" });
  const finishModal = firstPage.locator('[data-finish-confirm-modal]');
  await finishButton.click();
  await finishModal.waitFor({ state: "visible" });
  await firstPage.keyboard.press("Escape");
  await finishModal.waitFor({ state: "hidden" });
  await finishButton.click();
  await finishModal.waitFor({ state: "visible" });
  await finishModal.locator('[data-finish-confirm-cancel]').click();
  await finishModal.waitFor({ state: "hidden" });
  assertEqual(postedFromFirstPage, [], "POST requests after cancelled Finish confirmations");

  const secondPage = await context.newPage();
  await openCard(secondPage, cardId);
  await secondPage.locator("#shift-open").click();
  const secondWindow = secondPage.locator('[data-shift-window="true"]');
  await Promise.all([
    secondPage.waitForURL((url) => url.searchParams.get("notice") === "shift_changed", {
      waitUntil: "networkidle",
    }),
    secondWindow.locator('[data-shift-number-select]').selectOption("1"),
  ]);

  const firstWindow = firstPage.locator('[data-shift-window="true"]');
  await firstWindow.locator('[data-shift-pane="reload"]').waitFor({
    state: "visible",
    timeout: 15000,
  });
  assertEqual(await firstWindow.getAttribute("data-shift-state"), "reload", "stale shift state");
  assertEqual(await firstWindow.getAttribute("data-shift-blocking"), "true", "stale shift blocking state");
  assertEqual(await firstPage.locator(".app").getAttribute("inert"), "", "stale page inert state");
  assertEqual(await firstWindow.locator('[data-shift-close]:visible').count(), 0, "stale gate dismiss controls");
  assert(
    normalizeText(await firstWindow.textContent()).includes("Смяната е променена"),
    "Stale shift reload message was not shown",
  );
  await verifyShiftFocusWraps(firstPage, "stale shift reload");
  await verifyBlockingShiftInteractions(firstPage, "reload", "stale shift reload");

  let underlyingActionWasBlocked = false;
  try {
    await firstPage.locator(".roll-add-button").click({ timeout: 750 });
  } catch {
    underlyingActionWasBlocked = true;
  }
  assert(underlyingActionWasBlocked, "Blocking reload state allowed an underlying terminal action");
  assertEqual(postedFromFirstPage, [], "POST requests from stale first page");
  const after = databaseSnapshot();
  assertEqual(
    invariantCardState(after),
    invariantCardState(before),
    "production state after blocked stale-page action",
  );
  assertEqual(after.active_shift.id, before.active_shift.id, "active occurrence after second-page change");
  assertEqual(after.active_shift.shift_number, 1, "second-page corrected shift number");
  await secondPage.close();
}

async function verifyConfirmedFinishSuspendsPolling(page, cardId) {
  const staleWindow = page.locator('[data-shift-window="true"]');
  await Promise.all([
    page.waitForURL((url) => url.pathname === `/terminal/cards/${cardId}` && !url.search, {
      waitUntil: "networkidle",
    }),
    staleWindow.locator('[data-shift-reload]').click(),
  ]);

  let snapshotRequestCount = 0;
  const countSnapshotRequest = (request) => {
    if (new URL(request.url()).pathname === "/terminal/snapshot") {
      snapshotRequestCount += 1;
    }
  };
  page.on("request", countSnapshotRequest);

  let finishRequestReleased = false;
  let resolveFinishRequestRelease;
  const finishRequestRelease = new Promise((resolve) => {
    resolveFinishRequestRelease = resolve;
  });
  const releaseFinishRequest = () => {
    if (finishRequestReleased) {
      return;
    }
    finishRequestReleased = true;
    resolveFinishRequestRelease();
  };
  let markFinishRouteEntered;
  const finishRouteEntered = new Promise((resolve) => {
    markFinishRouteEntered = resolve;
  });
  const waitForFinishRouteEntry = async () => {
    let timeoutId;
    try {
      await Promise.race([
        finishRouteEntered,
        new Promise((_, reject) => {
          timeoutId = setTimeout(
            () => reject(new Error("Finish request interception timed out")),
            15000,
          );
        }),
      ]);
    } finally {
      clearTimeout(timeoutId);
    }
  };
  const finishRoute = `**/terminal/cards/${cardId}/finish`;
  const holdFinishRequest = async (route) => {
    markFinishRouteEntered();
    await finishRequestRelease;
    await route.continue();
  };
  await page.route(finishRoute, holdFinishRequest);

  let confirmClick;
  let finishNavigation;
  let finishResponse;
  try {
    const finishForm = page.locator(
      `form[action="/terminal/cards/${cardId}/finish"][data-finish-confirm-form="true"]`,
    );
    await finishForm.getByRole("button", { name: "Приключи" }).click();
    const finishModal = page.locator('[data-finish-confirm-modal]');
    await finishModal.waitFor({ state: "visible" });
    confirmClick = finishModal.locator('[data-finish-confirm-submit]').click();
    await waitForFinishRouteEntry();
    const requestsBeforeHold = snapshotRequestCount;
    await page.waitForTimeout(11000);
    assertEqual(
      snapshotRequestCount,
      requestsBeforeHold,
      "snapshot polling during confirmed Finish navigation",
    );
    finishResponse = page.waitForResponse(
      (response) => response.request().method() === "POST"
        && new URL(response.url()).pathname === `/terminal/cards/${cardId}/finish`,
      { timeout: 30000 },
    );
    finishNavigation = page.waitForURL(
      (url) => url.pathname === `/terminal/cards/${cardId}`
        && url.searchParams.get("notice") === "card_finished",
      { waitUntil: "commit", timeout: 30000 },
    );
    releaseFinishRequest();
    const [response] = await Promise.all([
      finishResponse,
      finishNavigation,
      confirmClick,
    ]);
    assertEqual(response.status(), 303, "confirmed Finish response status");
  } finally {
    releaseFinishRequest();
    await Promise.allSettled(
      [confirmClick, finishNavigation, finishResponse].filter(
        (pending) => pending !== undefined,
      ),
    );
    await page.unroute(finishRoute, holdFinishRequest);
    page.off("request", countSnapshotRequest);
  }

  const afterFinish = databaseSnapshot();
  assertEqual(afterFinish.cards[orderTwo].status, "completed", "confirmed Finish status");
}

async function main() {
  assertGuardedPathSafety();
  await verifyHealthDatabaseIdentity();

  const initial = databaseSnapshot();
  assertEqual(initial.card_count, 0, "fresh temporary database card count");
  assertEqual(initial.shift_count, 0, "fresh temporary database occurrence count");
  assertEqual(initial.configuration.shift_count, 4, "default shift count");
  assertEqual(initial.integrity_check, "ok", "initial database integrity");
  assertEqual(initial.foreign_key_errors, [], "initial foreign key errors");

  const browserErrors = [];
  let browser;
  try {
    browser = await chromium.launch();
    const context = await browser.newContext({
      viewport: { width: 1536, height: 1024 },
      timezoneId: shiftTimeZone,
    });
    const monitoredPages = new WeakSet();
    const monitorBrowserErrors = (candidatePage) => {
      if (monitoredPages.has(candidatePage)) {
        return;
      }
      monitoredPages.add(candidatePage);
      candidatePage.on("pageerror", (error) => browserErrors.push(`pageerror: ${error.message}`));
      candidatePage.on("console", (message) => {
        if (message.type() === "error") {
          browserErrors.push(`console: ${message.text()}`);
        }
      });
    };
    context.on("page", monitorBrowserErrors);
    const page = await context.newPage();
    monitorBrowserErrors(page);

    await verifyServerDatabaseIdentity(page, initial.configuration);
    writeCsvFixture();
    const cardIds = await importAndReleaseOrders(page);
    await configureThreeShifts(page);

    await page.goto(`${baseURL}/terminal`, { waitUntil: "networkidle" });
    await verifyNoActiveShiftGate(page, "1");
    await verifyShiftFocusWraps(page, "blocking shift gate");
    await verifyBlockingShiftInteractions(page, "gate", "blocking shift gate");
    await verifyTerminalHeaderAtBothViewports(page, "Няма активна смяна", false);
    await page.screenshot({
      path: path.join(artifactDir, "terminal-header-no-active.png"),
      fullPage: true,
    });

    await startShift(page, "1", true);
    await verifyTerminalHeaderAtBothViewports(page, "Смяна 1", true);
    await page.screenshot({
      path: path.join(artifactDir, "terminal-header-active.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 1077, height: 735 });
    await page.screenshot({
      path: path.join(artifactDir, "qa-terminal-header-1077x735.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 1536, height: 1024 });
    await page.locator("#shift-open").click();
    await page.locator('[data-shift-pane="overview"]').waitFor({ state: "visible" });
    await verifyDismissibleShiftInteractions(page, "active shift overview");
    await page.keyboard.press("Escape");
    await page.locator('[data-shift-window="true"]').waitFor({ state: "hidden" });

    await endActiveShiftAndReturnToGate(page, "2");
    await startShift(page, "2");
    await endActiveShiftAndReturnToGate(page, "3");
    await startShift(page, "3");
    await endActiveShiftAndReturnToGate(page, "1");
    await startShift(page, "1");
    await verifyTerminalHeader(page, "Смяна 1", true);

    await startCardAndSaveTare(page, cardIds[orderOne], "1.50");
    await addRoll(page, cardIds[orderOne], "20");
    await startCardAndSaveTare(page, cardIds[orderTwo], "2.00");

    const beforeRelabel = databaseSnapshot();
    assertEqual(beforeRelabel.active_shift.shift_number, 1, "initial active shift number");
    assertEqual(beforeRelabel.cards[orderOne].status, "running", `${orderOne} running status`);
    assertEqual(beforeRelabel.cards[orderTwo].status, "running", `${orderTwo} running status`);
    assertEqual(
      beforeRelabel.cards[orderOne].timing_segments.filter((segment) => segment.ended_at === null).length,
      1,
      `${orderOne} open timing segment`,
    );
    assertEqual(
      beforeRelabel.cards[orderTwo].timing_segments.filter((segment) => segment.ended_at === null).length,
      1,
      `${orderTwo} open timing segment`,
    );
    assertEqual(beforeRelabel.cards[orderOne].rolls.length, 1, `${orderOne} initial roll count`);
    assertEqual(
      beforeRelabel.cards[orderOne].rolls[0].shift_occurrence_id,
      beforeRelabel.active_shift.id,
      `${orderOne} initial roll attribution`,
    );

    await changeShiftNumberAndVerifyInvariants(
      page,
      cardIds[orderTwo],
      beforeRelabel,
    );
    await addRoll(page, cardIds[orderOne], "30");
    await addRoll(page, cardIds[orderTwo], "40");

    const { completedId, text: endedSummaryText } = await endShiftAndVerifySummary(
      page,
      beforeRelabel.active_shift.id,
    );

    await page.locator('[data-shift-ack]').click();
    await page.waitForURL((url) => !url.searchParams.has("shift_view"), {
      waitUntil: "networkidle",
    });
    await verifyNoActiveShiftGate(page, "3");
    await startShift(page, "3");
    await verifyTerminalHeaderAtBothViewports(page, "Смяна 3", true);
    await verifyDismissibleShiftURLsDoNotSurviveRefresh(
      context,
      cardIds[orderOne],
      completedId,
    );
    await verifyFullRecipeRemainsReachable(page, cardIds[orderOne]);

    await page.locator("#shift-open").click();
    const overviewWindow = page.locator('[data-shift-window="true"]');
    await overviewWindow.locator('[data-shift-pane="overview"]').waitFor({ state: "visible" });
    const completedBeforeCorrection = databaseSnapshot().completed_shifts;
    assertEqual(completedBeforeCorrection.length, 4, "completed shifts before history review");
    assertEqual(
      await overviewWindow.locator("[data-shift-history-preview-id]").count(),
      Math.min(5, completedBeforeCorrection.length),
      "overview history preview row limit",
    );
    await overviewWindow.getByRole("link", { name: "Виж всички" }).click();
    const historyWindow = page.locator('[data-shift-window="true"]');
    await historyWindow.locator('[data-shift-pane="history"]').waitFor({ state: "visible" });
    assertCanonicalShiftURL(page, `/terminal/cards/${cardIds[orderOne]}`, "full history navigation");
    assertEqual(await historyWindow.getAttribute("data-shift-blocking"), "false", "history blocking state");
    assertEqual(
      await historyWindow.locator("[data-shift-history-id]").count(),
      completedBeforeCorrection.length,
      "full history completed row count",
    );
    assertEqual(
      await historyWindow.locator('[data-shift-close]:visible').count(),
      1,
      "full history close control",
    );
    assertEqual(
      await historyWindow.locator('[aria-label="Страници на историята"]').count(),
      1,
      "full history pagination",
    );
    assertEqual(
      normalizeText(await historyWindow.locator('[data-shift-history-page][aria-current="page"]').textContent()),
      "1",
      "full history current page",
    );
    await page.screenshot({
      path: path.join(artifactDir, "full-shift-history.png"),
      fullPage: true,
    });
    await verifyDismissibleShiftInteractions(page, "full shift history");
    await page.locator('[data-shift-window="true"]').getByRole("link", {
      name: "Виж всички",
    }).click();
    await page.locator('[data-shift-pane="history"]').waitFor({ state: "visible" });

    await openHistoricalSummary(page, completedId, 3, 90);
    const initialHistoricalText = await verifySummary(page, {
      distinctItems: 2,
      orderOneRolls: 2,
      orderOneGross: 50,
      orderTwoRolls: 1,
      orderTwoGross: 40,
      totalRolls: 3,
      totalGross: 90,
    });
    assertEqual(initialHistoricalText, endedSummaryText, "handoff and historical modal summary");
    assertEqual(
      await page.locator('[data-shift-window="true"] [data-shift-history-back]').count(),
      1,
      "historical summary Back action",
    );
    await page.locator('[data-shift-history-back]').click();
    await page.locator('[data-shift-pane="history"]').waitFor({ state: "visible" });
    assertCanonicalShiftURL(page, `/terminal/cards/${cardIds[orderOne]}`, "summary Back navigation");
    assertEqual(
      await page.locator('[data-shift-window="true"]').getAttribute("data-shift-state"),
      "history",
      "historical Back destination",
    );
    await openHistoricalSummary(page, completedId, 3, 90);
    await verifyDismissibleShiftInteractions(page, "historical shift summary");
    await page.keyboard.press("Escape");
    await page.locator('[data-shift-window="true"]').waitFor({ state: "hidden" });

    await correctFirstRoll(page, cardIds[orderOne], completedId);
    let completedPostCorrectionHistoryTransitions = 0;
    for (
      let attempt = 1;
      attempt <= requiredPostCorrectionHistoryTransitions;
      attempt += 1
    ) {
      await openShiftHistoryFromCurrentOverview(
        page,
        `/terminal/cards/${cardIds[orderOne]}`,
        `corrected history navigation attempt ${attempt}`,
      );
      completedPostCorrectionHistoryTransitions += 1;
      if (attempt < requiredPostCorrectionHistoryTransitions) {
        await page.keyboard.press("Escape");
        await page.locator('[data-shift-window="true"]').waitFor({ state: "hidden" });
        assertCanonicalShiftURL(
          page,
          `/terminal/cards/${cardIds[orderOne]}`,
          `corrected history close attempt ${attempt}`,
        );
      }
    }
    await openHistoricalSummary(page, completedId, 3, 95);
    const correctedHistoricalText = await verifySummary(page, {
      distinctItems: 2,
      orderOneRolls: 2,
      orderOneGross: 55,
      orderTwoRolls: 1,
      orderTwoGross: 40,
      totalRolls: 3,
      totalGross: 95,
    });
    assert(
      correctedHistoricalText !== initialHistoricalText,
      "Historical summary did not update after the allowed roll correction",
    );
    await page.screenshot({
      path: path.join(artifactDir, "historical-shift-summary.png"),
      fullPage: true,
    });

    const beforeSecondPageChange = databaseSnapshot();
    await verifySecondPageStaleGate(
      context,
      page,
      cardIds[orderTwo],
      beforeSecondPageChange,
    );
    await verifyConfirmedFinishSuspendsPolling(page, cardIds[orderTwo]);

    assertEqual(browserErrors, [], "browser page errors");
    const finalSnapshot = databaseSnapshot();
    assertEqual(finalSnapshot.integrity_check, "ok", "final database integrity");
    assertEqual(finalSnapshot.foreign_key_errors, [], "final foreign key errors");
    assertEqual(finalSnapshot.completed_shifts.length, 4, "completed shift occurrence count");
    assertEqual(finalSnapshot.active_shift.id, beforeSecondPageChange.active_shift.id, "open occurrence id");
    assertEqual(finalSnapshot.active_shift.shift_number, 1, "final active shift number");

    for (const screenshotName of screenshotNames) {
      const screenshotPath = path.join(artifactDir, screenshotName);
      assert(fs.existsSync(screenshotPath), `Missing screenshot: ${screenshotPath}`);
      assert(fs.statSync(screenshotPath).size > 0, `Empty screenshot: ${screenshotPath}`);
    }

    const summary = {
      baseURL,
      database: path.relative(repoRoot, databasePath),
      fixture: path.relative(repoRoot, fixturePath),
      cards: cardIds,
      completedOccurrenceId: completedId,
      finalActiveOccurrenceId: finalSnapshot.active_shift.id,
      postCorrectionHistoryTransitions: completedPostCorrectionHistoryTransitions,
      integrityCheck: finalSnapshot.integrity_check,
      foreignKeyErrors: finalSnapshot.foreign_key_errors.length,
      screenshots: screenshotNames.map((name) => path.join(artifactDirRelative, name)),
    };
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");

    console.log("Shift management UI verification passed.");
    console.log(`Temporary DB: ${summary.database}`);
    console.log(`CSV fixture: ${summary.fixture}`);
    console.log(`Completed occurrence: ${summary.completedOccurrenceId}`);
    console.log(`Final active occurrence: ${summary.finalActiveOccurrenceId}`);
    console.log(
      `Database checks: integrity_check=${summary.integrityCheck}; foreign_key_check=${summary.foreignKeyErrors} rows`,
    );
    console.log("Screenshots:");
    for (const screenshot of summary.screenshots) {
      console.log(`- ${screenshot}`);
    }
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
