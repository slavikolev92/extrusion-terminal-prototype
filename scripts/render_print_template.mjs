import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

import {
  assertSafeGeneratedFileTarget,
  writeGeneratedFileAtomic,
} from "./order_finish_review_output_guard.mjs";


function requiredArg(name, fallback = null) {
  const index = process.argv.indexOf(`--${name}`);
  if (index !== -1 && process.argv[index + 1]) return process.argv[index + 1];
  if (fallback !== null) return fallback;
  throw new Error(`Missing required --${name} argument`);
}


function assert(condition, message) {
  if (!condition) throw new Error(message);
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


function validateScenario(scenarioName, scenario) {
  assert(/^[a-z0-9_-]+$/.test(scenarioName), `Invalid scenario name: ${scenarioName}`);
  assert(scenario?.scenario === scenarioName, `Scenario identity mismatch: ${scenarioName}`);
  assert(Number.isInteger(scenario.card_id) && scenario.card_id > 0, `${scenarioName} has invalid card_id`);
  assert(
    Number.isInteger(scenario.expected_page_count) && scenario.expected_page_count >= 2,
    `${scenarioName} has invalid expected_page_count`,
  );
  assert(
    Number.isInteger(scenario.expected_pallet_row_count)
      && scenario.expected_pallet_row_count > 0,
    `${scenarioName} has invalid expected_pallet_row_count`,
  );
  assert(
    scenario.expected_total_placement === "page2"
      || /^overflow:[1-9][0-9]*$/.test(scenario.expected_total_placement),
    `${scenarioName} has invalid expected_total_placement`,
  );
}


const baseUrl = requiredArg("base-url", "http://127.0.0.1:8010").replace(/\/+$/, "");
const rawFixturePath = requiredArg("fixture-json");
const rawOutputDir = requiredArg(
  "output-dir",
  "artifacts/ui-checks/physical-pallet-weight-print",
);
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const rootDir = fs.realpathSync(path.resolve(scriptDir, ".."));
const runtimeRoot = path.resolve(rootDir, ".test-runtime");
const uiChecksRoot = path.resolve(rootDir, "artifacts", "ui-checks");
const fixtureCandidate = path.resolve(rootDir, rawFixturePath);
const outputDir = path.resolve(rootDir, rawOutputDir);

assertNoSymlinkComponents(
  rootDir,
  runtimeRoot,
  ".test-runtime guard root must not be a symlink",
);
assert(
  isStrictChild(runtimeRoot, fixtureCandidate),
  "fixture JSON must be under .test-runtime",
);
assert(
  isStrictChild(uiChecksRoot, outputDir),
  "render output dir must be under artifacts/ui-checks",
);
assertNoSymlinkComponents(
  rootDir,
  outputDir,
  "render output dir must be under artifacts/ui-checks and contain no symlinks",
);
assert(fs.existsSync(fixtureCandidate), `fixture JSON does not exist: ${fixtureCandidate}`);
assert(fs.statSync(fixtureCandidate).isFile(), "fixture JSON must name a regular file");
assertSafeGeneratedFileTarget(fixtureCandidate, "fixture JSON");
const fixturePath = fs.realpathSync(fixtureCandidate);
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), fixturePath),
  "fixture JSON must resolve under .test-runtime",
);

const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
assert(Array.isArray(fixture.scenario_order), "fixture scenario_order must be an array");
assert(fixture.scenarios && typeof fixture.scenarios === "object", "fixture scenarios must be an object");
assert(fixture.scenario_order.length > 0, "fixture must contain at least one scenario");
for (const scenarioName of fixture.scenario_order) {
  validateScenario(scenarioName, fixture.scenarios[scenarioName]);
}

const databaseCandidate = path.resolve(rootDir, fixture.db_path || "");
assert(
  isStrictChild(runtimeRoot, databaseCandidate),
  "fixture database must be under .test-runtime",
);
assertNoSymlinkComponents(
  rootDir,
  databaseCandidate,
  "fixture database must not contain symlinks",
);
assert(fs.existsSync(databaseCandidate), "fixture database does not exist");
assert(fs.statSync(databaseCandidate).isFile(), "fixture database must name a regular file");
assertSafeGeneratedFileTarget(databaseCandidate, "fixture database");
const databasePath = fs.realpathSync(databaseCandidate);
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), databasePath),
  "fixture database must resolve under .test-runtime",
);

fs.mkdirSync(uiChecksRoot, { recursive: true });
assertNoSymlinkComponents(
  rootDir,
  outputDir,
  "render output dir must be under artifacts/ui-checks and contain no symlinks",
);
let outputAncestor = outputDir;
while (!fs.existsSync(outputAncestor)) outputAncestor = path.dirname(outputAncestor);
assert(
  outputAncestor === uiChecksRoot
    || isStrictChild(fs.realpathSync(uiChecksRoot), fs.realpathSync(outputAncestor)),
  "render output dir must be under artifacts/ui-checks",
);
fs.mkdirSync(outputDir, { recursive: true });
assert(
  isStrictChild(fs.realpathSync(uiChecksRoot), fs.realpathSync(outputDir)),
  "render output dir must be under artifacts/ui-checks",
);

const summaryPath = path.join(outputDir, "render-summary.json");
assertSafeGeneratedFileTarget(summaryPath, "render summary target");
for (const scenarioName of fixture.scenario_order) {
  const expectedPages = fixture.scenarios[scenarioName].expected_page_count;
  for (const target of [
    `${scenarioName}.pdf`,
    `${scenarioName}.pdfinfo.txt`,
    `${scenarioName}.metadata.json`,
    ...Array.from({ length: expectedPages }, (_, index) => `${scenarioName}-browser-page-${index + 1}.png`),
    ...Array.from({ length: expectedPages }, (_, index) => `${scenarioName}-pdf-page-${index + 1}.png`),
  ]) {
    assertSafeGeneratedFileTarget(path.join(outputDir, target), `${scenarioName} output target`);
  }
}

const require = createRequire(import.meta.url);
const localNodeModules = fs.realpathSync(path.join(rootDir, "node_modules"));
const resolvedPlaywright = fs.realpathSync(require.resolve("playwright"));
assert(
  isStrictChild(localNodeModules, resolvedPlaywright),
  "Playwright must resolve from repository-local node_modules",
);
const { chromium } = require("playwright");

const healthResponse = await fetch(`${baseUrl}/health`, { cache: "no-store" });
assert(healthResponse.ok, `health preflight returned HTTP ${healthResponse.status}`);
const health = await healthResponse.json();
assert(
  fs.realpathSync(path.resolve(health.database_path)) === databasePath,
  "server database identity does not match fixture database",
);

const approvedHeaders = [
  "Палет №",
  "Брой ролки",
  "Бруто без палет, кг",
  "Тегло палет, кг",
  "Бруто с палет, кг",
  "Нето, кг",
];
const browser = await chromium.launch();
const results = [];

try {
  for (const scenarioName of fixture.scenario_order) {
    const scenario = fixture.scenarios[scenarioName];
    const printUrl = `${baseUrl}${scenario.print_path}`;
    const page = await browser.newPage({ viewport: { width: 1280, height: 1800 } });
    await page.goto(printUrl, { waitUntil: "networkidle" });
    await page.emulateMedia({ media: "print" });

    const printPages = page.locator(".print-page");
    const domPageCount = await printPages.count();
    assert(
      domPageCount === scenario.expected_page_count,
      `${scenarioName}: expected ${scenario.expected_page_count} DOM pages, found ${domPageCount}`,
    );
    const rowCount = await page.locator("[data-pallet-summary-row]").count();
    assert(
      rowCount === scenario.expected_pallet_row_count,
      `${scenarioName}: expected ${scenario.expected_pallet_row_count} pallet rows, found ${rowCount}`,
    );
    const totalCount = await page.locator("[data-pallet-summary-total]").count();
    assert(totalCount === 1, `${scenarioName}: expected exactly one pallet total, found ${totalCount}`);

    const totalPlacement = await page.locator("[data-pallet-summary-total]").evaluate((element) => {
      if (element.getAttribute("data-pallet-summary-total") === "page2") return "page2";
      const overflowPage = element.closest("[data-pallet-overflow-page]");
      return `overflow:${overflowPage?.getAttribute("data-pallet-overflow-page") || "missing"}`;
    });
    assert(
      totalPlacement === scenario.expected_total_placement,
      `${scenarioName}: expected total on ${scenario.expected_total_placement}, found ${totalPlacement}`,
    );

    const tables = page.locator("[data-pallet-summary-table]");
    const tableCount = await tables.count();
    const tableMeasurements = [];
    for (let tableIndex = 0; tableIndex < tableCount; tableIndex += 1) {
      const table = tables.nth(tableIndex);
      const headers = await table.locator("thead th").allTextContents();
      assert(
        JSON.stringify(headers.map((value) => value.replace(/\s+/g, " ").trim()))
          === JSON.stringify(approvedHeaders),
        `${scenarioName}: pallet headers do not match the approved six-column order`,
      );
      const measurement = await table.evaluate((element) => {
        const pageElement = element.closest(".print-page");
        const tableBounds = element.getBoundingClientRect();
        const pageBounds = pageElement.getBoundingClientRect();
        const headerCells = [...element.querySelectorAll("thead th")];
        const bodyRows = [...element.querySelectorAll("tbody tr")];
        return {
          location: element.getAttribute("data-pallet-summary-table"),
          tableWidthPx: tableBounds.width,
          tableBottomPx: tableBounds.bottom,
          pageBottomPx: pageBounds.bottom,
          headerWidthsPx: headerCells.map((cell) => cell.getBoundingClientRect().width),
          headerHeightPx: headerCells[0]?.getBoundingClientRect().height || 0,
          headerFontSizePx: Number.parseFloat(getComputedStyle(headerCells[0]).fontSize),
          bodyRowHeightsPx: bodyRows.map((row) => row.getBoundingClientRect().height),
        };
      });
      assert(
        measurement.tableBottomPx <= measurement.pageBottomPx + 0.5,
        `${scenarioName}: pallet table extends beyond its print page: ${JSON.stringify(measurement)}`,
      );
      assert(
        Math.min(...measurement.headerWidthsPx) >= 39,
        `${scenarioName}: a pallet heading column is narrower than 39px`,
      );
      assert(
        measurement.headerFontSizePx >= 8,
        `${scenarioName}: pallet heading text is smaller than 8px`,
      );
      assert(
        Math.min(...measurement.bodyRowHeightsPx) >= 17,
        `${scenarioName}: a pallet body row is shorter than 17px`,
      );
      tableMeasurements.push(measurement);
    }

    if (scenarioName === "no_weight") {
      const missingValues = await page.locator(
        "[data-pallet-summary-row] td:nth-child(4), [data-pallet-summary-row] td:nth-child(5), "
          + "[data-pallet-summary-total] td:nth-child(4), [data-pallet-summary-total] td:nth-child(5)",
      ).allTextContents();
      assert(
        missingValues.every((value) => value.trim() === "-"),
        "no_weight: missing physical and dependent values must render as hyphens",
      );
    }

    for (let pageIndex = 0; pageIndex < domPageCount; pageIndex += 1) {
      await printPages.nth(pageIndex).screenshot({
        path: path.join(outputDir, `${scenarioName}-browser-page-${pageIndex + 1}.png`),
      });
    }

    const pdfPath = path.join(outputDir, `${scenarioName}.pdf`);
    await page.pdf({
      path: pdfPath,
      format: "A4",
      printBackground: true,
      margin: { top: "0", right: "0", bottom: "0", left: "0" },
    });
    await page.close();

    const pdfInfo = execFileSync("pdfinfo", [pdfPath], { encoding: "utf8" });
    const pagesMatch = pdfInfo.match(/^Pages:\s+(\d+)$/m);
    const pageSizeMatch = pdfInfo.match(/^Page size:\s+(.+)$/m);
    const pdfPageCount = pagesMatch ? Number(pagesMatch[1]) : null;
    assert(
      pdfPageCount === scenario.expected_page_count,
      `${scenarioName}: expected ${scenario.expected_page_count} PDF pages, found ${pdfPageCount}`,
    );
    writeGeneratedFileAtomic(
      path.join(outputDir, `${scenarioName}.pdfinfo.txt`),
      pdfInfo,
      `${scenarioName} pdfinfo target`,
    );
    for (let pageNumber = 1; pageNumber <= pdfPageCount; pageNumber += 1) {
      execFileSync(
        "pdftoppm",
        [
          "-png",
          "-r",
          "144",
          "-f",
          String(pageNumber),
          "-l",
          String(pageNumber),
          "-singlefile",
          pdfPath,
          path.join(outputDir, `${scenarioName}-pdf-page-${pageNumber}`),
        ],
        { stdio: "inherit" },
      );
    }

    const metadata = {
      scenario: scenarioName,
      cardId: scenario.card_id,
      printUrl,
      expectedPageCount: scenario.expected_page_count,
      domPageCount,
      pdfPageCount,
      pageSize: pageSizeMatch ? pageSizeMatch[1] : null,
      expectedTotalPlacement: scenario.expected_total_placement,
      actualTotalPlacement: totalPlacement,
      palletRowCount: rowCount,
      totalCount,
      tableMeasurements,
      pdfPath,
      browserPages: Array.from(
        { length: domPageCount },
        (_, index) => path.join(outputDir, `${scenarioName}-browser-page-${index + 1}.png`),
      ),
      pdfPages: Array.from(
        { length: pdfPageCount },
        (_, index) => path.join(outputDir, `${scenarioName}-pdf-page-${index + 1}.png`),
      ),
    };
    writeGeneratedFileAtomic(
      path.join(outputDir, `${scenarioName}.metadata.json`),
      `${JSON.stringify(metadata, null, 2)}\n`,
      `${scenarioName} metadata target`,
    );
    results.push(metadata);
  }
} finally {
  await browser.close();
}

const summary = {
  fixturePath,
  databasePath,
  outputDir,
  scenarios: results,
};
writeGeneratedFileAtomic(
  summaryPath,
  `${JSON.stringify(summary, null, 2)}\n`,
  "render summary target",
);
console.log(JSON.stringify(summary, null, 2));
