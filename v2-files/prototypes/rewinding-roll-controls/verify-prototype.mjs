import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";


const prototypeURL = String(process.env.PROTOTYPE_URL || "").trim();
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../../..");
const artifactDir = path.join(repoRoot, "artifacts", "ui-checks", "rewinding-ui-prototype");

if (!prototypeURL) {
  throw new Error("PROTOTYPE_URL is required.");
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 768 } });
const browserErrors = [];

fs.mkdirSync(artifactDir, { recursive: true });

page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});
page.on("pageerror", (error) => browserErrors.push(error.message));

await page.goto(prototypeURL, { waitUntil: "networkidle" });
await page.locator(".input-panel").waitFor({ state: "visible" });

if (process.env.DEBUG_GEOMETRY === "1") {
  const geometry = await page.evaluate(() => {
    const rect = (element) => {
      const box = element?.getBoundingClientRect();
      return box
        ? { left: box.left, right: box.right, top: box.top, bottom: box.bottom, width: box.width, height: box.height }
        : null;
    };
    const textRect = (element) => {
      if (!element?.firstChild) return null;
      const range = document.createRange();
      range.selectNodeContents(element);
      return rect(range);
    };
    const styleSummary = (element) => {
      if (!element) return null;
      const style = getComputedStyle(element);
      return {
        fontFamily: style.fontFamily,
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
        lineHeight: style.lineHeight,
        paddingLeft: style.paddingLeft,
        paddingRight: style.paddingRight,
      };
    };
    const addButton = document.querySelector(".roll-add-button");
    const addIcon = addButton?.querySelector(".button-icon");
    const addText = addButton?.querySelector(".button-icon + span");
    const firstNumberCell = document.querySelector(".roll-row > div:first-child");
    return {
      entryLabels: [...document.querySelectorAll(".roll-entry .field-label")].map((label) => ({
        text: label.textContent.trim(),
        style: styleSummary(label),
        rect: rect(label),
        input: rect(label.parentElement?.querySelector("input")),
      })),
      lifecycleButtons: [...document.querySelectorAll(".actions .action-button")].map((button) => ({
        text: button.innerText.trim(),
        style: styleSummary(button),
        rect: rect(button),
        contentWidth: [...button.children].reduce((total, child) => total + child.getBoundingClientRect().width, 0),
      })),
      addButton: {
        rect: rect(addButton),
        style: styleSummary(addButton),
        iconRect: rect(addIcon),
        textRect: rect(addText),
        iconCenter: addIcon ? (addIcon.getBoundingClientRect().top + addIcon.getBoundingClientRect().bottom) / 2 : null,
        textCenter: addText ? (addText.getBoundingClientRect().top + addText.getBoundingClientRect().bottom) / 2 : null,
      },
      rollNumber: {
        cellRect: rect(firstNumberCell),
        textRect: textRect(firstNumberCell),
        style: styleSummary(firstNumberCell),
      },
    };
  });
  console.log(JSON.stringify(geometry, null, 2));
}

const headings = await page.locator(".roll-head > div").allTextContents();
const normalizedHeadings = headings.map((heading) => heading.trim());
const expectedHeadings = ["№", "Бруто", "Шпула", "Нето", "Палет", ""];
if (JSON.stringify(normalizedHeadings) !== JSON.stringify(expectedHeadings)) {
  throw new Error(`Unexpected roll column order: ${JSON.stringify(normalizedHeadings)}`);
}

const fieldLabels = await page.locator(".roll-entry .field-label").allTextContents();
const normalizedFieldLabels = fieldLabels.map((label) => label.trim());
if (JSON.stringify(normalizedFieldLabels) !== JSON.stringify(["Ролка", "Шпула", "Палет"])) {
  throw new Error(`Unexpected roll-entry labels: ${JSON.stringify(normalizedFieldLabels)}`);
}

const panelBorderWidth = await page.locator(".roll-entry").evaluate(
  (element) => getComputedStyle(element).borderTopWidth,
);
if (panelBorderWidth !== "0px") {
  throw new Error(`The roll-entry group still has a border: ${panelBorderWidth}`);
}

const floatingLabels = page.locator(".roll-entry label.prototype-floating-field");
if ((await floatingLabels.count()) !== 3) {
  throw new Error("All three roll-entry labels must sit in their input borders.");
}

for (let index = 0; index < 3; index += 1) {
  const label = floatingLabels.nth(index);
  const geometry = await label.evaluate((element) => {
    const input = element.querySelector("input");
    const caption = element.querySelector(".field-label");
    const inputBox = input?.getBoundingClientRect();
    const captionBox = caption?.getBoundingClientRect();
    return inputBox && captionBox
      ? {
          inputTop: inputBox.top,
          captionTop: captionBox.top,
          captionBottom: captionBox.bottom,
        }
      : null;
  });
  if (!geometry || !(geometry.captionTop < geometry.inputTop && geometry.captionBottom > geometry.inputTop)) {
    throw new Error(`Field label ${index + 1} is not embedded in the input border.`);
  }
}

const primaryButtonWidths = await page.locator(".actions .action-button").evaluateAll(
  (buttons) => buttons.map((button) => button.getBoundingClientRect().width),
);
if (primaryButtonWidths.length !== 3 || Math.max(...primaryButtonWidths) - Math.min(...primaryButtonWidths) > 1) {
  throw new Error(`Primary buttons are not equal width: ${primaryButtonWidths.join(", ")}`);
}
const primaryButtonInsets = await page.locator(".actions .action-button").evaluateAll((buttons) => (
  buttons.map((button) => {
    const buttonBox = button.getBoundingClientRect();
    const firstChildBox = button.firstElementChild?.getBoundingClientRect();
    const lastChildBox = button.lastElementChild?.getBoundingClientRect();
    return {
      text: button.innerText.trim(),
      left: firstChildBox ? firstChildBox.left - buttonBox.left : 0,
      right: lastChildBox ? buttonBox.right - lastChildBox.right : 0,
    };
  })
));
if (primaryButtonInsets.some(({ left, right }) => left < 11 || right < 11)) {
  throw new Error(`Primary button content is cramped: ${JSON.stringify(primaryButtonInsets)}`);
}

const entryGeometry = await page.locator(".roll-entry").evaluate((entry) => {
  const tare = entry.querySelector("[data-current-tare-input]");
  const pallet = entry.querySelector("[data-current-pallet-input]");
  const roll = entry.querySelector("[data-new-roll-autofocus]");
  const add = entry.querySelector(".roll-add-button");
  const boxes = [roll, tare, pallet, add].map((element) => element?.getBoundingClientRect());
  return {
    widths: boxes.map((box) => box?.width || 0),
    bottoms: boxes.map((box) => box?.bottom || 0),
  };
});
if (Math.abs(entryGeometry.widths[1] - entryGeometry.widths[2]) > 1) {
  throw new Error(`Core and pallet inputs are not equal width: ${entryGeometry.widths.join(", ")}`);
}
if (Math.max(...entryGeometry.bottoms) - Math.min(...entryGeometry.bottoms) > 1) {
  throw new Error(`Add button and inputs are not bottom-aligned: ${entryGeometry.bottoms.join(", ")}`);
}
const addButtonAlignment = await page.locator(".roll-add-button").evaluate((button) => {
  const buttonBox = button.getBoundingClientRect();
  const iconBox = button.querySelector(".button-icon")?.getBoundingClientRect();
  const textBox = button.querySelector(".button-icon + span")?.getBoundingClientRect();
  return iconBox && textBox
    ? {
        leftInset: iconBox.left - buttonBox.left,
        rightInset: buttonBox.right - textBox.right,
        verticalCenterDifference: Math.abs(
          (iconBox.top + iconBox.bottom) / 2 - (textBox.top + textBox.bottom) / 2,
        ),
      }
    : null;
});
if (
  !addButtonAlignment
  || addButtonAlignment.leftInset < 10
  || addButtonAlignment.rightInset < 10
  || addButtonAlignment.verticalCenterDifference > 0.5
) {
  throw new Error(`Add button content is not optically balanced: ${JSON.stringify(addButtonAlignment)}`);
}

const tableColumnWidths = await page.locator(".roll-head > div").evaluateAll(
  (cells) => cells.slice(0, 5).map((cell) => cell.getBoundingClientRect().width),
);
if (Math.max(...tableColumnWidths) - Math.min(...tableColumnWidths) > 1) {
  throw new Error(`The five roll columns are not equal width: ${tableColumnWidths.join(", ")}`);
}

for (const kind of ["gross", "tare", "net"]) {
  const values = await page.locator(`[data-roll-display="${kind}"]`).allTextContents();
  if (values.length === 0 || values.some((value) => !/^\d+\.\d$/.test(value.trim()))) {
    throw new Error(`${kind} values do not consistently use one decimal place: ${values.join(", ")}`);
  }
}
const currentTareValue = await page.locator("[data-current-tare-input]").inputValue();
if (!/^\d+\.\d$/.test(currentTareValue)) {
  throw new Error(`The current core input does not use one decimal place: ${currentTareValue}`);
}

const rollNumberInset = await page.locator(".roll-row > div:first-child").first().evaluate((cell) => {
  const range = document.createRange();
  range.selectNodeContents(cell);
  return range.getBoundingClientRect().left - cell.getBoundingClientRect().left;
});
if (rollNumberInset < 14) {
  throw new Error(`The roll number is still cramped against the left edge: ${rollNumberInset}px`);
}

const rollAndCoreTypography = await page.locator(".roll-entry .field-label").evaluateAll((labels) => (
  labels.slice(0, 2).map((label) => {
    const style = getComputedStyle(label);
    return [style.fontFamily, style.fontSize, style.fontWeight, style.lineHeight].join("|");
  })
));
if (new Set(rollAndCoreTypography).size !== 1) {
  throw new Error(`Roll and core labels use different typography: ${rollAndCoreTypography.join(", ")}`);
}

await page.locator(".roll-edit-button").first().click();
if (!(await page.locator(".roll-row.is-editing").isVisible())) {
  throw new Error("The per-roll editor no longer opens.");
}
const editingRow = page.locator(".roll-row.is-editing");
await editingRow.locator('[name^="gross_weight__"]').fill("21.10");
await editingRow.locator('[name^="tare_weight__"]').fill("1.20");
await editingRow.locator('[name^="pallet_number__"]').fill("8");
await page.locator("[data-prototype-save]").click();
const correctedValues = await page.locator(".roll-row").first().evaluate((row) => ({
  gross: row.querySelector('[data-roll-display="gross"]')?.textContent.trim(),
  tare: row.querySelector('[data-roll-display="tare"]')?.textContent.trim(),
  net: row.querySelector('[data-roll-display="net"]')?.textContent.trim(),
  pallet: row.querySelector('[data-roll-display="pallet"]')?.textContent.trim(),
}));
if (JSON.stringify(correctedValues) !== JSON.stringify({ gross: "21.1", tare: "1.2", net: "19.9", pallet: "8" })) {
  throw new Error(`The reordered roll editor saved unexpected values: ${JSON.stringify(correctedValues)}`);
}

await page.locator("[data-rewinding-button]").click();
await page.locator("[data-rewinding-count]").fill("2");
await page.locator("[data-rewinding-save]").click();
if ((await page.locator("[data-rewinding-button]").innerText()).trim() !== "Пренавиване: 2") {
  throw new Error("The rewinding marker no longer updates.");
}

if (browserErrors.length > 0) {
  throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
}

const focusedScreenshotPath = path.join(artifactDir, "12-refined-roll-pane-1920x768.png");
await page.reload({ waitUntil: "networkidle" });
await page.locator(".input-panel").screenshot({ path: focusedScreenshotPath });

await page.setViewportSize({ width: 1366, height: 768 });
await page.reload({ waitUntil: "networkidle" });
const narrowGeometry = await page.locator(".input-panel").evaluate((panel) => {
  const panelBox = panel.getBoundingClientRect();
  const entryBox = panel.querySelector(".roll-entry")?.getBoundingClientRect();
  const addBox = panel.querySelector(".roll-add-button")?.getBoundingClientRect();
  const editBoxes = [...panel.querySelectorAll(".roll-edit-button")].map((button) => button.getBoundingClientRect());
  return {
    panelLeft: panelBox.left,
    panelRight: panelBox.right,
    entryLeft: entryBox?.left || 0,
    entryRight: entryBox?.right || 0,
    addRight: addBox?.right || 0,
    editRight: Math.max(...editBoxes.map((box) => box.right)),
    viewportWidth: window.innerWidth,
  };
});
if (
  narrowGeometry.panelLeft < 0
  || narrowGeometry.panelRight > narrowGeometry.viewportWidth + 1
  || narrowGeometry.entryLeft < narrowGeometry.panelLeft - 1
  || narrowGeometry.entryRight > narrowGeometry.panelRight + 1
  || narrowGeometry.addRight > narrowGeometry.panelRight + 1
  || narrowGeometry.editRight > narrowGeometry.panelRight + 1
) {
  throw new Error(`The refined roll layout clips at 1366px: ${JSON.stringify(narrowGeometry)}`);
}
await page.screenshot({
  path: path.join(artifactDir, "13-refined-prototype-1366x768.png"),
  fullPage: true,
});

const imageDataURL = (filePath) => (
  `data:image/${path.extname(filePath).slice(1).toLowerCase()};base64,${fs.readFileSync(filePath).toString("base64")}`
);
const sourceImagePath = path.join(scriptDir, "example.JPG");
await page.setViewportSize({ width: 1900, height: 900 });
await page.setContent(`
  <!doctype html>
  <html lang="bg">
    <head>
      <meta charset="utf-8">
      <style>
        * { box-sizing: border-box; }
        body { margin: 0; padding: 24px; background: #e8edf3; font-family: Arial, sans-serif; }
        main { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 24px; align-items: start; }
        figure { margin: 0; padding: 16px; border-radius: 12px; background: #fff; box-shadow: 0 2px 12px rgba(15, 35, 55, .09); }
        figcaption { margin-bottom: 12px; color: #0b355f; font-size: 18px; font-weight: 700; }
        img { display: block; width: 100%; height: auto; border: 1px solid #d5dde6; }
      </style>
    </head>
    <body>
      <main>
        <figure><figcaption>Предоставен пример</figcaption><img src="${imageDataURL(sourceImagePath)}"></figure>
        <figure><figcaption>Обновен терминален прототип</figcaption><img src="${imageDataURL(focusedScreenshotPath)}"></figure>
      </main>
    </body>
  </html>
`, { waitUntil: "load" });
await page.screenshot({
  path: path.join(artifactDir, "14-refined-fields-side-by-side.png"),
  fullPage: true,
});

await browser.close();
console.log("rewinding prototype checks passed");
