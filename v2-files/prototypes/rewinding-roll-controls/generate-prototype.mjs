import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";


const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../../..");
const baseURL = String(process.env.BASE_URL || "").replace(/\/+$/, "");
const artifactDir = path.join(repoRoot, "artifacts", "ui-checks", "rewinding-ui-prototype");
const prototypePath = path.join(scriptDir, "prototype.html");
const cssPath = path.join(scriptDir, "prototype.css");
const javascriptPath = path.join(scriptDir, "prototype.js");

if (!baseURL) {
  throw new Error("BASE_URL is required.");
}

fs.mkdirSync(artifactDir, { recursive: true });

function dataURL(filePath, mimeType) {
  return `data:${mimeType};base64,${fs.readFileSync(filePath).toString("base64")}`;
}

const assets = {
  logo: dataURL(path.join(repoRoot, "app", "static", "images", "kolev-logo.png"), "image/png"),
  machine: dataURL(path.join(repoRoot, "app", "static", "assets", "machine-icon.png"), "image/png"),
  rewinding: dataURL(path.join(repoRoot, "app", "static", "images", "shift-ui", "shift-switch.svg"), "image/svg+xml"),
  clock: dataURL(path.join(repoRoot, "app", "static", "images", "shift-ui", "clock.svg"), "image/svg+xml"),
  pencil: dataURL("/usr/share/icons/elementary-xfce/actions/symbolic/document-edit-symbolic.svg", "image/svg+xml"),
  staticImages: {
    "/static/images/shift-ui/calendar-clock.svg": dataURL(path.join(repoRoot, "app", "static", "images", "shift-ui", "calendar-clock.svg"), "image/svg+xml"),
    "/static/images/shift-ui/calendar.svg": dataURL(path.join(repoRoot, "app", "static", "images", "shift-ui", "calendar.svg"), "image/svg+xml"),
    "/static/images/shift-ui/check-circle.svg": dataURL(path.join(repoRoot, "app", "static", "images", "shift-ui", "check-circle.svg"), "image/svg+xml"),
    "/static/images/shift-ui/clock.svg": dataURL(path.join(repoRoot, "app", "static", "images", "shift-ui", "clock.svg"), "image/svg+xml"),
    "/static/images/shift-ui/info-circle.svg": dataURL(path.join(repoRoot, "app", "static", "images", "shift-ui", "info-circle.svg"), "image/svg+xml"),
    "/static/images/shift-ui/play-circle.svg": dataURL(path.join(repoRoot, "app", "static", "images", "shift-ui", "play-circle.svg"), "image/svg+xml"),
    "/static/images/shift-ui/stop-square.svg": dataURL(path.join(repoRoot, "app", "static", "images", "shift-ui", "stop-square.svg"), "image/svg+xml"),
    "/static/images/shift-ui/x.svg": dataURL(path.join(repoRoot, "app", "static", "images", "shift-ui", "x.svg"), "image/svg+xml"),
  },
};

const css = fs.readFileSync(cssPath, "utf8");
const javascript = fs.readFileSync(javascriptPath, "utf8");
const browser = await chromium.launch({ headless: true });

async function installPrototype(page) {
  await page.addStyleTag({ content: css });
  await page.evaluate((prototypeAssets) => {
    window.__REWINDING_PROTOTYPE_ASSETS__ = prototypeAssets;
  }, assets);
  await page.evaluate((source) => {
    Function(source)();
  }, javascript);
}

async function openReference(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto(`${baseURL}/terminal/cards/1`, { waitUntil: "networkidle" });
  await page.locator(".input-panel").waitFor({ state: "visible" });
}

const viewport = { width: 1920, height: 768 };
const page = await browser.newPage({ viewport });
const errors = [];
page.on("console", (message) => {
  if (message.type() === "error") errors.push(message.text());
});
page.on("pageerror", (error) => errors.push(error.message));

await openReference(page, viewport);
await page.locator(".input-panel").screenshot({
  path: path.join(artifactDir, "02b-current-roll-pane-reference.png"),
});
await installPrototype(page);
await page.screenshot({
  path: path.join(artifactDir, "03-prototype-default-1920x768.png"),
  fullPage: true,
});
await page.locator(".input-panel").screenshot({
  path: path.join(artifactDir, "04-prototype-roll-pane-default.png"),
});

await page.locator("[data-rewinding-button]").click();
await page.screenshot({
  path: path.join(artifactDir, "04b-prototype-rewinding-dialog-1920x768.png"),
  fullPage: true,
});
await page.locator("[data-rewinding-count]").fill("2");
await page.locator("[data-rewinding-save]").click();
if ((await page.locator("[data-rewinding-button]").innerText()).trim() !== "Пренавиване: 2") {
  throw new Error("The rewinding marker did not update.");
}
await page.screenshot({
  path: path.join(artifactDir, "05-prototype-rewinding-marked-1920x768.png"),
  fullPage: true,
});

await page.locator(".roll-edit-button").first().click();
if (!(await page.locator(".roll-row.is-editing").isVisible())) {
  throw new Error("The selected roll did not enter edit mode.");
}
await page.screenshot({
  path: path.join(artifactDir, "06-prototype-roll-edit-1920x768.png"),
  fullPage: true,
});
await page.locator(".input-panel").screenshot({
  path: path.join(artifactDir, "07-prototype-roll-pane-edit.png"),
});

await openReference(page, viewport);
await page.evaluate((prototypeAssets) => {
  window.__REWINDING_PROTOTYPE_ASSETS__ = prototypeAssets;
  for (const image of document.querySelectorAll("img")) {
    const source = image.getAttribute("src") || "";
    if (source.includes("/static/images/kolev-logo.png")) image.src = prototypeAssets.logo;
    if (source.includes("/static/assets/machine-icon.png")) image.src = prototypeAssets.machine;
    for (const [suffix, dataURL] of Object.entries(prototypeAssets.staticImages)) {
      if (source.includes(suffix)) image.src = dataURL;
    }
  }
  for (const script of [...document.querySelectorAll("script")]) script.remove();
  for (const form of document.querySelectorAll("form")) form.action = "#";
  for (const anchor of document.querySelectorAll("a")) anchor.href = "#";
}, assets);
await page.addStyleTag({ content: css });
await page.evaluate(({ prototypeAssets, source }) => {
  const assetsScript = document.createElement("script");
  assetsScript.id = "rewinding-prototype-assets";
  assetsScript.type = "application/x-rewinding-prototype";
  assetsScript.textContent = `window.__REWINDING_PROTOTYPE_ASSETS__ = ${JSON.stringify(prototypeAssets)}; window.__REWINDING_PROTOTYPE_STANDALONE__ = true;`;
  document.body.append(assetsScript);

  const prototypeScript = document.createElement("script");
  prototypeScript.id = "rewinding-prototype-script";
  prototypeScript.type = "application/x-rewinding-prototype";
  prototypeScript.textContent = source;
  document.body.append(prototypeScript);
}, { prototypeAssets: assets, source: javascript });

let html = await page.content();
html = html.replaceAll(
  'type="application/x-rewinding-prototype"',
  'type="text/javascript"',
);
html = html.replace(
  "</head>",
  "  <meta name=\"prototype-source\" content=\"Rendered from the current /terminal page; production files are unchanged.\">\n</head>",
);
fs.writeFileSync(prototypePath, html, "utf8");

await page.goto(`file://${prototypePath}`, { waitUntil: "load" });
await page.locator(".input-panel").waitFor({ state: "visible" });
if (!(await page.locator("[data-rewinding-button]").isVisible())) {
  throw new Error("The standalone prototype did not initialize.");
}
await page.screenshot({
  path: path.join(artifactDir, "08-standalone-prototype-1920x768.png"),
  fullPage: true,
});

await page.locator("[data-rewinding-button]").click();
await page.locator("[data-rewinding-count]").fill("3");
await page.locator("[data-rewinding-save]").click();
if ((await page.locator("[data-rewinding-button]").innerText()).trim() !== "Пренавиване: 3") {
  throw new Error("The standalone rewinding interaction failed.");
}

await page.locator("[data-roll-change-button]").click();
await page.locator("[data-roll-change-hours]").fill("1");
await page.locator("[data-roll-change-minutes]").fill("0");
await page.locator("[data-roll-change-start]").click();
if (!(await page.locator("[data-roll-change-button]").evaluate((button) => button.classList.contains("is-running")))) {
  throw new Error("The standalone roll-change timer did not start.");
}

await page.locator(".roll-edit-button").first().click();
if (!(await page.locator(".roll-row.is-editing").isVisible())) {
  throw new Error("The standalone roll editor did not open.");
}
await page.locator("[data-prototype-delete]").click();
if (!(await page.locator("#prototype-delete-modal").isVisible())) {
  throw new Error("The standalone delete confirmation did not open.");
}
await page.screenshot({
  path: path.join(artifactDir, "09-standalone-delete-dialog-1920x768.png"),
  fullPage: true,
});

if (errors.length > 0) {
  throw new Error(`Browser errors: ${errors.join(" | ")}`);
}

await browser.close();
console.log(JSON.stringify({
  prototype: path.relative(repoRoot, prototypePath),
  reference: "artifacts/ui-checks/rewinding-ui-prototype/02-current-terminal-reference-1920x768.png",
  screenshots: [
    "artifacts/ui-checks/rewinding-ui-prototype/03-prototype-default-1920x768.png",
    "artifacts/ui-checks/rewinding-ui-prototype/05-prototype-rewinding-marked-1920x768.png",
    "artifacts/ui-checks/rewinding-ui-prototype/06-prototype-roll-edit-1920x768.png",
    "artifacts/ui-checks/rewinding-ui-prototype/08-standalone-prototype-1920x768.png",
  ],
}, null, 2));
