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
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const artifactDir = path.resolve(requiredEnvironment("ARTIFACT_DIR"));
const artifactDirRelative = path.relative(repoRoot, artifactDir);
const databasePath = path.join(artifactDir, "shift-ui.sqlite3");
const fixturePath = path.join(artifactDir, "shift-management-orders.csv");
const summaryPath = path.join(artifactDir, "shift-management-ui-summary.json");
const orderOne = "SHIFT-UI-001";
const orderTwo = "SHIFT-UI-002";

const screenshotNames = [
  "admin-shift-count.png",
  "no-active-shift-gate.png",
  "active-shift-window.png",
  "ended-shift-summary.png",
  "historical-shift-summary.png",
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

function assertArtifactDatabaseSafety() {
  const relativeDatabasePath = path.relative(artifactDir, databasePath);
  const artifactRoot = path.join(repoRoot, "artifacts", "ui-checks");
  const canonicalArtifactRoot = fs.realpathSync(artifactRoot);
  const canonicalArtifactDir = fs.realpathSync(artifactDir);
  const canonicalDatabasePath = fs.realpathSync(databasePath);
  const relativeArtifactPath = path.relative(canonicalArtifactRoot, canonicalArtifactDir);
  const canonicalDatabaseRelative = path.relative(
    canonicalArtifactDir,
    canonicalDatabasePath,
  );
  assert(
    relativeDatabasePath === "shift-ui.sqlite3",
    `Temporary database must be ${path.join(artifactDir, "shift-ui.sqlite3")}`,
  );
  assert(
    relativeArtifactPath && !relativeArtifactPath.startsWith("..") && !path.isAbsolute(relativeArtifactPath),
    `Artifact directory must remain below artifacts/ui-checks: ${artifactDir}`,
  );
  assert(
    canonicalDatabaseRelative === "shift-ui.sqlite3",
    `Temporary database must be a regular file inside ARTIFACT_DIR: ${databasePath}`,
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
      raw_material_a: "LDPE; Alpha | 100%",
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
      raw_material_a: "LDPE; Beta | 100%",
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
  return {
    shift_count: 100_000 + (digest.readUInt32BE(0) % 900_000),
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
  assertEqual(restored, initialConfiguration, "artifact configuration restored after identity preflight");
  if (
    observed.shift_count !== marker.shift_count
    || observed.version !== marker.version
  ) {
    throw new Error(
      "Selected HTTP server is not backed by the required artifact database.",
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

async function visibleExactTextCount(page, text) {
  const matches = page.getByText(text, { exact: true });
  let visible = 0;
  for (let index = 0; index < await matches.count(); index += 1) {
    if (await matches.nth(index).isVisible()) {
      visible += 1;
    }
  }
  return visible;
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
    await row.locator('select[name="machine_id"]').selectOption(machineId);
    await row.locator('input[name="machine_sequence"]').fill("1");
    await row.getByRole("button", { name: "Изпрати" }).click();
    await page.waitForLoadState("networkidle");
    assertEqual(await page.locator(`#draft-card-${cardIds[orderNumber]}`).count(), 0, `${orderNumber} draft row after release`);
    const machineQueue = page.locator(".machine-column", {
      has: page.getByRole("heading", { name: `Машина ${machineId}` }),
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
    "rgba(31, 41, 51, 0.42)",
    "gate dimming overlay",
  );
  assertEqual(await window.locator("[data-shift-close]").count(), 0, "non-dismissible gate close controls");
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

async function startShift(page, shiftNumber) {
  const window = page.locator('[data-shift-window="true"]');
  await window.locator('[data-shift-start-number]').selectOption(shiftNumber);
  await window.locator('[data-shift-confirm-open="start"]').click();
  await window.locator('[data-shift-pane="start-confirm"]').waitFor({ state: "visible" });
  assert(
    normalizeText(await window.locator('[data-shift-pane="start-confirm"]').textContent()).includes(
      `Стартиране на смяна ${shiftNumber}?`,
    ),
    `Start confirmation did not show shift ${shiftNumber}`,
  );
  await window.locator('[data-shift-confirm-submit="start"]').click();
  await page.waitForLoadState("networkidle");
  await window.waitFor({ state: "hidden" });
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
    page.waitForURL((url) => url.searchParams.get("notice") === "tare_saved", {
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
    ["Production order ID", "Customer", "Product type", "Roll count", "Gross kg"],
    "shift summary columns",
  );
  assert(
    normalizeText(await window.locator(".shift-summary-facts").textContent()).includes(
      `${expected.distinctItems} артикула`,
    ),
    `Expected ${expected.distinctItems} distinct items in shift summary`,
  );
  const rows = await summaryRows(page);
  assertEqual(Object.keys(rows).sort(), [orderOne, orderTwo], "summary production orders");
  assertEqual(rows[orderOne].roll_count, expected.orderOneRolls, `${orderOne} roll total`);
  assertEqual(rows[orderOne].gross_weight, expected.orderOneGross, `${orderOne} gross total`);
  assertEqual(rows[orderTwo].roll_count, expected.orderTwoRolls, `${orderTwo} roll total`);
  assertEqual(rows[orderTwo].gross_weight, expected.orderTwoGross, `${orderTwo} gross total`);
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
    `${await window.locator(".shift-summary-facts").textContent()} ${await window.locator(".shift-summary-table").textContent()}`,
  );
}

async function endShiftAndVerifySummary(page, expectedOccurrenceId) {
  await page.locator("#shift-open").click();
  const window = page.locator('[data-shift-window="true"]');
  await window.locator('[data-shift-confirm-open="end"]').click();
  const confirmation = window.locator('[data-shift-pane="end-confirm"]');
  await confirmation.waitFor({ state: "visible" });
  assert(
    normalizeText(await confirmation.textContent()).includes("Приключване на Смяна 2?"),
    "End-shift confirmation did not identify corrected Shift 2",
  );
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
  const text = await verifySummary(page, {
    distinctItems: 2,
    orderOneRolls: 2,
    orderOneGross: 50,
    orderTwoRolls: 1,
    orderTwoGross: 40,
    totalRolls: 3,
    totalGross: 90,
  });
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
  await historyRow.getByRole("link", { name: "View" }).click();
  await page.waitForURL((url) => (
    url.searchParams.get("shift_view") === "summary"
      && Number(url.searchParams.get("shift_id")) === completedId
  ), { waitUntil: "networkidle" });
  assertEqual(
    await page.locator('[data-shift-window="true"]').getAttribute("data-shift-blocking"),
    "false",
    "historical summary blocking state",
  );
}

async function correctFirstRoll(page, cardId, completedId) {
  await openCard(page, cardId);
  await page.getByRole("button", { name: "Още действия" }).click();
  await page.locator('[data-roll-correction-open]').click();
  const firstRow = page.locator(".roll-row[data-roll-id]").first();
  const grossInput = firstRow.locator('input[name^="gross_weight__"]');
  assertEqual(await grossInput.inputValue(), "20", "first roll gross before correction");
  await grossInput.fill("25");
  await Promise.all([
    page.waitForURL((url) => url.searchParams.get("notice") === "rolls_saved", {
      waitUntil: "networkidle",
    }),
    page.getByRole("button", { name: "Запази данните" }).click(),
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

async function main() {
  assert(fs.existsSync(artifactDir), `ARTIFACT_DIR does not exist: ${artifactDir}`);
  assert(fs.existsSync(databasePath), `Temporary database does not exist: ${databasePath}`);
  assertArtifactDatabaseSafety();

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
    const context = await browser.newContext({ viewport: { width: 1440, height: 950 } });
    const page = await context.newPage();
    page.on("pageerror", (error) => browserErrors.push(error.message));

    await verifyServerDatabaseIdentity(page, initial.configuration);
    writeCsvFixture();
    const cardIds = await importAndReleaseOrders(page);
    await configureThreeShifts(page);

    await page.goto(`${baseURL}/terminal`, { waitUntil: "networkidle" });
    await verifyNoActiveShiftGate(page, "1");
    await page.screenshot({
      path: path.join(artifactDir, "no-active-shift-gate.png"),
      fullPage: true,
    });

    await startShift(page, "1");
    assertEqual(await visibleExactTextCount(page, "Shift"), 1, "visible global Shift labels");
    assert(await page.locator("#shift-open").isVisible(), "Global Shift action is not visible");

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
    await page.waitForLoadState("networkidle");
    await verifyNoActiveShiftGate(page, "3");
    await startShift(page, "3");

    await page.locator("#shift-open").click();
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
    await page.waitForURL((url) => url.searchParams.get("shift_view") === "overview", {
      waitUntil: "networkidle",
    });
    await page.locator('[data-shift-window="true"] [data-shift-close]').click();

    await correctFirstRoll(page, cardIds[orderOne], completedId);
    await page.locator("#shift-open").click();
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

    assertEqual(browserErrors, [], "browser page errors");
    const finalSnapshot = databaseSnapshot();
    assertEqual(finalSnapshot.integrity_check, "ok", "final database integrity");
    assertEqual(finalSnapshot.foreign_key_errors, [], "final foreign key errors");
    assertEqual(finalSnapshot.completed_shifts.length, 1, "completed shift occurrence count");
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
