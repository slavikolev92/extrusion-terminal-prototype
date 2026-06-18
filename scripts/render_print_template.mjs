import { execFileSync } from "node:child_process";
import { mkdirSync, realpathSync, writeFileSync } from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const rootDir = process.cwd();

function requiredArg(name, fallback = null) {
  const index = process.argv.indexOf(`--${name}`);
  if (index !== -1 && process.argv[index + 1]) {
    return process.argv[index + 1];
  }
  if (fallback !== null) {
    return fallback;
  }
  throw new Error(`Missing required --${name} argument`);
}

const baseUrl = requiredArg("base-url", "http://127.0.0.1:8010");
const cardId = requiredArg("card-id");
const rawOutputDir = requiredArg("output-dir", "artifacts/ui-checks/template-tuning");
const outputDir = path.resolve(rootDir, rawOutputDir);
const uiChecksDir = path.resolve(rootDir, "artifacts/ui-checks");
mkdirSync(uiChecksDir, { recursive: true });
const realUiChecksDir = realpathSync(uiChecksDir);
const existingOutputParent = path.dirname(outputDir);
mkdirSync(existingOutputParent, { recursive: true });
const realOutputParent = realpathSync(existingOutputParent);

if (
  realOutputParent !== realUiChecksDir &&
  !realOutputParent.startsWith(`${realUiChecksDir}${path.sep}`)
) {
  throw new Error("render output dir must be under artifacts/ui-checks");
}

mkdirSync(outputDir, { recursive: true });

const printUrl = `${baseUrl.replace(/\/$/, "")}/cards/${cardId}/print`;
const pdfPath = path.join(outputDir, "current-print-output.pdf");
const browser = await chromium.launch();

try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 1800 } });
  await page.goto(printUrl, { waitUntil: "networkidle" });
  await page.locator(".print-page-front").screenshot({
    path: path.join(outputDir, "current-front-browser.png"),
  });
  await page.locator(".print-page-back").screenshot({
    path: path.join(outputDir, "current-back-browser.png"),
  });

  await page.pdf({
    path: pdfPath,
    format: "A4",
    printBackground: true,
    margin: {
      top: "0",
      right: "0",
      bottom: "0",
      left: "0",
    },
  });
} finally {
  await browser.close();
}

const imagePrefix = path.join(outputDir, "current-print-output");
execFileSync("pdftoppm", ["-png", "-r", "144", pdfPath, imagePrefix], {
  stdio: "inherit",
});
const pdfInfo = execFileSync("pdfinfo", [pdfPath], { encoding: "utf8" });
writeFileSync(path.join(outputDir, "current-print-output.pdfinfo.txt"), pdfInfo);

const pagesMatch = pdfInfo.match(/^Pages:\s+(\d+)$/m);
const pageSizeMatch = pdfInfo.match(/^Page size:\s+(.+)$/m);
const metadata = {
  printUrl,
  pdfPath,
  pages: pagesMatch ? Number(pagesMatch[1]) : null,
  pageSize: pageSizeMatch ? pageSizeMatch[1] : null,
  browserFront: path.join(outputDir, "current-front-browser.png"),
  browserBack: path.join(outputDir, "current-back-browser.png"),
  pdfFront: path.join(outputDir, "current-print-output-1.png"),
  pdfBack: path.join(outputDir, "current-print-output-2.png"),
};
writeFileSync(
  path.join(outputDir, "current-print-output.metadata.json"),
  JSON.stringify(metadata, null, 2)
);
console.log(JSON.stringify(metadata, null, 2));

if (metadata.pages !== 2) {
  throw new Error(`Expected exactly 2 PDF pages, got ${metadata.pages}`);
}
