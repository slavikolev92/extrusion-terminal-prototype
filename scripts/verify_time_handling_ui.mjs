import { existsSync, mkdirSync, realpathSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { chromium } from "playwright";


function requiredArg(name) {
  const index = process.argv.indexOf(`--${name}`);
  if (index === -1 || !process.argv[index + 1]) {
    throw new Error(`Missing required --${name} argument`);
  }
  return process.argv[index + 1];
}


function nearestExistingAncestor(candidatePath) {
  let currentPath = candidatePath;
  while (!existsSync(currentPath)) {
    const parentPath = path.dirname(currentPath);
    if (parentPath === currentPath) {
      throw new Error(`Could not resolve an existing ancestor for ${candidatePath}`);
    }
    currentPath = parentPath;
  }
  return currentPath;
}


function isAtOrBelow(parentPath, candidatePath) {
  const relative = path.relative(parentPath, candidatePath);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}


async function expectText(page, selectorOrLabel, expected) {
  const isSelector = ["#", ".", "["].some((prefix) => selectorOrLabel.startsWith(prefix));
  let locator;
  if (isSelector) {
    locator = page.locator(selectorOrLabel);
  } else {
    const term = page.locator("dt").filter({ hasText: selectorOrLabel }).first();
    locator = term.locator("xpath=following-sibling::dd[1]");
  }

  const actual = (await locator.innerText()).replace(/\s+/g, " ").trim();
  if (!actual.includes(expected)) {
    throw new Error(`Expected ${selectorOrLabel} to contain ${expected}, found ${actual}`);
  }
}


const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const rootDir = realpathSync(path.resolve(scriptDir, ".."));
const baseUrl = requiredArg("base-url").replace(/\/+$/, "");
const cardId = requiredArg("card-id");
if (!/^\d+$/.test(cardId) || Number(cardId) < 1) {
  throw new Error("--card-id must be a positive integer");
}

const outputDir = path.resolve(rootDir, requiredArg("output-dir"));
const uiChecksDir = path.resolve(rootDir, "artifacts/ui-checks");
mkdirSync(uiChecksDir, { recursive: true });
const realUiChecksDir = realpathSync(uiChecksDir);
const realOutputAncestor = realpathSync(nearestExistingAncestor(outputDir));
if (!isAtOrBelow(realUiChecksDir, realOutputAncestor)) {
  throw new Error("verification output dir must be under artifacts/ui-checks");
}
mkdirSync(outputDir, { recursive: true });
if (!isAtOrBelow(realUiChecksDir, realpathSync(outputDir))) {
  throw new Error("verification output dir must be under artifacts/ui-checks");
}

const artifacts = {
  adminScreenshot: path.join(outputDir, "admin-local-time.png"),
  terminalScreenshot: path.join(outputDir, "terminal-produced-local-time.png"),
  printScreenshot: path.join(outputDir, "print-local-time-back.png"),
  printPdf: path.join(outputDir, "print-local-time.pdf"),
  metadata: path.join(outputDir, "metadata.json"),
};
const expected = {
  startUtc: "2026-06-18 21:35:00",
  finishUtc: "2026-06-19 04:15:00",
  adminStartLocal: "19.06.2026 00:35:00",
  adminStartInputLocal: "2026-06-19 00:35:00",
  terminalFinishLocal: "19.06.2026 07:15:00",
  printStartLocal: "19.06.2026 00:35",
};

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });

  await page.goto(`${baseUrl}/admin/cards/${cardId}`, { waitUntil: "networkidle" });
  await expectText(page, "Първи старт", "19.06.2026 00:35:00");
  const startInput = page.locator('input[name^="started_at__"]').first();
  if (await startInput.inputValue() !== "2026-06-19 00:35:00") {
    throw new Error("Admin timing input is not Sofia local time");
  }
  await page.screenshot({ path: artifacts.adminScreenshot, fullPage: true });
  await page.click('#admin-card-save-form button[type="submit"], button[form="admin-card-save-form"]');
  await page.waitForLoadState("networkidle");
  if (await page.locator('input[name^="started_at__"]').first().inputValue() !== "2026-06-19 00:35:00") {
    throw new Error("Unchanged admin timing input did not round-trip");
  }

  await page.goto(`${baseUrl}/terminal`, { waitUntil: "networkidle" });
  await page.click("#history-open");
  await expectText(page, "#history-overlay", "19.06.2026 07:15:00");
  await page.locator("#history-overlay").screenshot({ path: artifacts.terminalScreenshot });

  await page.goto(`${baseUrl}/cards/${cardId}/print`, { waitUntil: "networkidle" });
  if (await page.locator('[data-summary-field="start"]').innerText() !== "19.06.2026 00:35") {
    throw new Error("Printed start time is not Sofia local time");
  }
  await page.locator(".print-page-back").screenshot({ path: artifacts.printScreenshot });
  await page.pdf({
    path: artifacts.printPdf,
    format: "A4",
    printBackground: true,
    margin: { top: "0", right: "0", bottom: "0", left: "0" },
  });
} finally {
  await browser.close();
}

const metadata = {
  baseUrl,
  cardId: Number(cardId),
  urls: {
    admin: `${baseUrl}/admin/cards/${cardId}`,
    terminal: `${baseUrl}/terminal`,
    print: `${baseUrl}/cards/${cardId}/print`,
  },
  expected,
  artifacts,
};
writeFileSync(artifacts.metadata, `${JSON.stringify(metadata, null, 2)}\n`);
console.log(JSON.stringify(metadata, null, 2));
