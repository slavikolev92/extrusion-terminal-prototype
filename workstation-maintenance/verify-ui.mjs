import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("@playwright/test");
const bundleDir = fileURLToPath(new URL(".", import.meta.url));
const repoRoot = path.dirname(bundleDir);
const pagePath = path.join(bundleDir, "maintenance.html");
const artifactDir = path.join(
  repoRoot,
  "artifacts",
  "ui-checks",
  "workstation-maintenance",
);
const screenshotPath = path.join(artifactDir, "maintenance-screen.png");
const pageUrl = pathToFileURL(pagePath).href;

let browser;

try {
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const page = await context.newPage();
  const loadedUrls = new Set();

  await page.route(/^https?:/, (route) => route.abort());
  page.on("requestfinished", (request) => loadedUrls.add(request.url()));

  await page.goto(pageUrl, { waitUntil: "load" });
  loadedUrls.add(page.url());

  assert.equal(
    await page.getByText("Извършва се техническа поддръжка", { exact: true }).isVisible(),
    true,
  );
  assert.equal(
    await page.getByText("Терминалът временно не е достъпен. Моля, изчакайте.", {
      exact: true,
    }).isVisible(),
    true,
  );
  assert.deepEqual(
    await page.locator(".maintenance img").evaluate((image) => ({
      complete: image.complete,
      naturalWidth: image.naturalWidth,
      naturalHeight: image.naturalHeight,
    })),
    { complete: true, naturalWidth: 512, naturalHeight: 512 },
  );
  assert.equal(
    await page.locator(
      "a, button, input, select, textarea, [role='button'], [contenteditable='true']",
    ).count(),
    0,
  );

  const resourceUrls = await page.evaluate(() =>
    performance.getEntriesByType("resource").map((entry) => entry.name),
  );
  for (const resourceUrl of [...loadedUrls, ...resourceUrls]) {
    assert.equal(new URL(resourceUrl).protocol, "file:", `Non-local resource: ${resourceUrl}`);
  }

  await mkdir(artifactDir, { recursive: true });
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await context.close();
  console.log(`Verified maintenance page: ${screenshotPath}`);
} finally {
  await browser?.close();
}
