import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const baseURL = process.env.BASE_URL || "http://127.0.0.1:8000";
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const artifactDirRelative = path.join("artifacts", "ui-checks", "structured-sample-csv");
const fixturePathRelative = path.join("tests", "fixtures", "structured_recipe_sample.csv");
const artifactDir = path.join(repoRoot, artifactDirRelative);
const fixturePath = path.join(repoRoot, fixturePathRelative);
const orderNumber = "SR-SAMPLE-002";

async function clickFirstMatching(page, names) {
  for (const name of names) {
    const button = page.getByRole("button", { name }).first();
    if ((await button.count()) > 0) {
      await button.click();
      return;
    }
  }

  throw new Error(`No matching button found for: ${names.map(String).join(", ")}`);
}

function normalizeText(value) {
  return value.replace(/\s+/g, " ").trim();
}

function cardIdFromHref(href) {
  const match = (href || "").match(/\/admin\/cards\/(\d+)(?:[/?#]|$)/);
  if (!match) {
    throw new Error(`Could not read card id from href: ${href}`);
  }

  return match[1];
}

function relativeArtifactPath(filename) {
  return path.join(artifactDirRelative, filename);
}

function terminalMaterialsForm(page, cardId) {
  return page.locator(`form[action="/terminal/cards/${cardId}/materials"]`);
}

async function expectText(locator, expected, label) {
  await locator.waitFor();
  const actual = normalizeText((await locator.textContent()) || "");
  if (actual !== expected) {
    throw new Error(`Expected ${label} "${expected}", found "${actual}"`);
  }
}

async function expectInputValue(locator, expected, label) {
  await locator.waitFor();
  const actual = await locator.inputValue();
  if (actual !== expected) {
    throw new Error(`Expected ${label} "${expected}", found "${actual}"`);
  }
}

async function importFixture(page) {
  await page.goto(`${baseURL}/admin/import`, { waitUntil: "networkidle" });
  await page.locator('input[name="csv_file"]').setInputFiles(fixturePath);
  await page.locator('input[name="overwrite_existing"]').check();
  await clickFirstMatching(page, [/Импортирай CSV/i, /Импортирай/i]);
  await page.locator(".notice", { hasText: "Резултат от импорта:" }).waitFor();
  await page.locator("tr", { hasText: orderNumber }).first().waitFor();
}

async function openAdminSampleCard(page) {
  const cardsUrl = new URL("/admin/cards", baseURL);
  cardsUrl.searchParams.set("order_number", orderNumber);

  await page.goto(cardsUrl.toString(), { waitUntil: "networkidle" });
  const cardRow = page.locator("tr", { hasText: orderNumber }).first();
  await cardRow.waitFor();

  const detailLink = cardRow.locator('a[href^="/admin/cards/"]').first();
  const sampleCardId = cardIdFromHref(await detailLink.getAttribute("href"));
  await detailLink.click();
  await page.waitForLoadState("networkidle");

  return sampleCardId;
}

async function releaseDraftSampleCardIfNeeded(page, cardId) {
  await page.goto(`${baseURL}/admin/planning`, { waitUntil: "networkidle" });
  const planningRow = page.locator(`#draft-card-${cardId}`);

  if ((await planningRow.count()) === 0) {
    return false;
  }

  await planningRow.locator('select[name="machine_id"]').selectOption("1");
  await planningRow.locator('input[name="machine_sequence"]').fill("1");
  await planningRow.locator('input[name="max_roll_weight"]').fill("64.50");
  await clickFirstMatching(planningRow, [/Изпрати/i]);
  await page.waitForLoadState("networkidle");
  return true;
}

async function verifyAdminStructuredRecipeRow(page) {
  const header = page.locator("#materials .material-ledger .admin-ledger-head");
  const plannedMaterialInput = page.locator(
    '#materials input[name="planned_material__raw_material_a"]',
  );
  const row = plannedMaterialInput.locator(
    "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' material-ledger-row ')][1]",
  );

  await expectText(header.locator("div").nth(0), "Категория", "admin category header");
  await expectText(
    header.locator("div").nth(1),
    "Планирани материали",
    "admin planned materials header",
  );
  await expectText(row.locator(".component"), "reLDPE", "admin category");
  await expectText(row.locator(".structured-planned"), "reLDPE", "admin planned material");
  await expectInputValue(
    plannedMaterialInput,
    "reLDPE | 80%",
    "admin planned source input",
  );
  await expectText(row.locator(".recipe-number").nth(0), "80%", "admin percent");
  await expectText(row.locator(".recipe-number").nth(1), "1000.00", "admin planned kg");
}

async function verifyTerminalSampleCardSelected(page, cardId) {
  const materialForm = terminalMaterialsForm(page, cardId);
  await page.locator("h2", { hasText: new RegExp(`№\\s*${orderNumber}`) }).waitFor();
  await materialForm.waitFor();
  await materialForm.locator('input[name="actual_material__raw_material_a"]').first().waitFor();
}

async function terminalRawMaterialRow(page, cardId) {
  const materialForm = terminalMaterialsForm(page, cardId);
  const actualMaterialInput = materialForm.locator(
    'input[name="actual_material__raw_material_a"]',
  );
  const row = actualMaterialInput.locator(
    "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' recipe-row ')][1]",
  );

  return {
    row,
    actualMaterialInput,
    batchLotInput: materialForm.locator('input[name="batch_lot__raw_material_a"]'),
  };
}

async function verifyTerminalStructuredRecipeRow(page, cardId) {
  const { row, actualMaterialInput, batchLotInput } = await terminalRawMaterialRow(
    page,
    cardId,
  );

  await expectText(row.locator(".component"), "reLDPE", "terminal category");
  await expectText(row.locator(".material-planned"), "reLDPE", "terminal planned material");
  await expectText(row.locator(".recipe-number").nth(0), "80%", "terminal percent");
  await expectText(row.locator(".recipe-number").nth(1), "1000.00", "terminal planned kg");
  await actualMaterialInput.waitFor();
  await batchLotInput.waitFor();
}

async function openTerminalSampleCard(page, cardId, { noDraftRow = false } = {}) {
  try {
    const response = await page.goto(`${baseURL}/terminal/cards/${cardId}`, {
      waitUntil: "networkidle",
    });
    if (!response || !response.ok()) {
      throw new Error(`HTTP status ${response ? response.status() : "unknown"}`);
    }
    await verifyTerminalSampleCardSelected(page, cardId);
    await verifyTerminalStructuredRecipeRow(page, cardId);

    const { actualMaterialInput, batchLotInput } = await terminalRawMaterialRow(page, cardId);
    if (!(await actualMaterialInput.isEditable()) || !(await batchLotInput.isEditable())) {
      throw new Error("material inputs are not editable");
    }
  } catch (error) {
    if (noDraftRow) {
      throw new Error(
        `SR-SAMPLE-002 was not present as a draft row and /terminal/cards/${cardId} was not available/editable: ${error.message}`,
      );
    }
    throw error;
  }
}

async function main() {
  fs.mkdirSync(artifactDir, { recursive: true });

  const adminScreenshot = path.join(
    artifactDir,
    "admin-category-only-structured-sample.png",
  );
  const terminalScreenshot = path.join(
    artifactDir,
    "terminal-category-only-structured-sample.png",
  );
  const summaryPath = path.join(artifactDir, "structured-sample-ui-summary.json");
  const summary = {
    baseURL,
    fixturePath: fixturePathRelative,
    importUrl: null,
    adminUrl: null,
    terminalUrl: null,
    screenshots: [],
  };

  let browser;
  try {
    browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });

    await importFixture(page);
    summary.importUrl = page.url();

    const sampleCardId = await openAdminSampleCard(page);
    summary.adminUrl = page.url();

    await verifyAdminStructuredRecipeRow(page);

    await page.screenshot({ path: adminScreenshot, fullPage: true });
    summary.screenshots.push(relativeArtifactPath("admin-category-only-structured-sample.png"));

    const releasedFromDraft = await releaseDraftSampleCardIfNeeded(page, sampleCardId);

    await openTerminalSampleCard(page, sampleCardId, { noDraftRow: !releasedFromDraft });

    const { actualMaterialInput, batchLotInput } = await terminalRawMaterialRow(
      page,
      sampleCardId,
    );
    await actualMaterialInput.fill("Actual reLDPE UI");
    await batchLotInput.fill("LOT-UI-80");
    await batchLotInput.press("Enter");
    await page.waitForLoadState("networkidle");

    await page.reload({ waitUntil: "networkidle" });
    await verifyTerminalSampleCardSelected(page, sampleCardId);
    await verifyTerminalStructuredRecipeRow(page, sampleCardId);

    const actualMaterialValue = await actualMaterialInput.inputValue();
    const batchLotValue = await batchLotInput.inputValue();
    if (actualMaterialValue !== "Actual reLDPE UI") {
      throw new Error(
        `Expected actual material value "Actual reLDPE UI", found "${actualMaterialValue}"`,
      );
    }
    if (batchLotValue !== "LOT-UI-80") {
      throw new Error(`Expected batch lot value "LOT-UI-80", found "${batchLotValue}"`);
    }
    await page.screenshot({ path: terminalScreenshot, fullPage: true });
    summary.terminalUrl = page.url();
    summary.screenshots.push(relativeArtifactPath("terminal-category-only-structured-sample.png"));

    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
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
