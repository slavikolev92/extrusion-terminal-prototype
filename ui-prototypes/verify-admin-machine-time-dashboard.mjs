import assert from "node:assert/strict";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { chromium } from "playwright";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const prototypePath = path.join(scriptDir, "admin-machine-time-dashboard.html");
const sourceVisualPath = process.env.DASHBOARD_SOURCE_VISUAL
  ? path.resolve(repoRoot, process.env.DASHBOARD_SOURCE_VISUAL)
  : null;
const artifactDir = path.join(
  repoRoot,
  "artifacts",
  "ui-checks",
  "admin-machine-time-dashboard",
);
const screenshotPath = path.join(artifactDir, "dashboard-1440x1024.png");
const viewportScreenshotPath = path.join(
  artifactDir,
  "dashboard-top-1440x1024.png",
);
const timelineScreenshotPath = path.join(
  artifactDir,
  "dashboard-timeline-section-1440.png",
);
const productivityScreenshotPath = path.join(
  artifactDir,
  "dashboard-productivity-section-1440.png",
);
const productivityHoverScreenshotPath = path.join(
  artifactDir,
  "dashboard-productivity-hover-1440.png",
);
const hoverScreenshotPath = path.join(
  artifactDir,
  "dashboard-order-hover-1440x1024.png",
);
const pauseHoverScreenshotPath = path.join(
  artifactDir,
  "dashboard-pause-hover-1440x1024.png",
);
const idleHoverScreenshotPath = path.join(
  artifactDir,
  "dashboard-inactive-hover-1440x1024.png",
);
const responsiveScreenshotPath = path.join(
  artifactDir,
  "dashboard-1024x1024.png",
);
const narrowScreenshotPath = path.join(
  artifactDir,
  "dashboard-820x1024.png",
);
const comparisonPath = path.join(artifactDir, "source-vs-prototype.png");

await mkdir(artifactDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1024 } });
const consoleErrors = [];
const pageErrors = [];

page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => pageErrors.push(error.message));

try {
  await page.goto(pathToFileURL(prototypePath).href, { waitUntil: "load" });

  assert.equal(
    (await page.locator("#dashboard-title").textContent()).trim(),
    "Производствено време по машини",
  );
  assert.equal(await page.locator(".machine-row").count(), 4);
  assert.equal(await page.locator(".timeline-axis time").count(), 9);
  assert.equal(await page.locator('[data-kind="order"]').count(), 8);
  assert.equal(await page.locator('button[data-kind="order"]').count(), 0);
  assert.equal(await page.locator("dialog").count(), 0);
  assert.equal(
    await page.getByText("Нетна производителност", { exact: true }).count(),
    0,
  );
  assert.equal(await page.locator(".updated-at").count(), 0);
  assert.equal(await page.getByText(/Обновено/, { exact: false }).count(), 0);

  const activityLabels = await page.locator(".machine-meta p").allTextContents();
  assert.deepEqual(activityLabels, [
    "Активна 17ч 35м (73%)",
    "Активна 14ч 05м (59%)",
    "Активна 13ч 10м (55%)",
    "Активна 2ч 10м (9%)",
  ]);

  const trackHeights = await page.locator(".machine-track").evaluateAll((tracks) =>
    tracks.map((track) => track.getBoundingClientRect().height),
  );
  assert.ok(trackHeights.every((height) => height >= 88));

  const orderNumbers = await page.locator(".segment-order").allTextContents();
  assert.deepEqual(orderNumbers, [
    "25278",
    "25281",
    "25280",
    "25282",
    "25285",
    "25283",
    "25283",
    "25284",
  ]);
  const orderRates = await page.locator(".segment-rate").allTextContents();
  assert.deepEqual(orderRates, [
    "(74 кг/ч)",
    "(81 кг/ч)",
    "(69 кг/ч)",
    "(76 кг/ч)",
    "(71 кг/ч)",
    "(64 кг/ч)",
    "(64 кг/ч)",
    "(58 кг/ч)",
  ]);
  assert.ok(
    await page.locator(".segment-primary").evaluateAll((labels) =>
      labels.every((label) => label.scrollWidth <= label.clientWidth),
    ),
    "Expected each order and productivity label to fit without clipping",
  );

  const orderLabels = await page.locator('[data-kind="order"]').allTextContents();
  assert.ok(orderLabels.every((label) => !label.includes("№")));

  const customerLabels = page.locator(".segment-customer");
  assert.equal(await customerLabels.count(), 8);
  const customerStyles = await customerLabels.first().evaluate((label) => {
    const styles = getComputedStyle(label);
    return {
      overflow: styles.overflow,
      textOverflow: styles.textOverflow,
      whiteSpace: styles.whiteSpace,
    };
  });
  assert.deepEqual(customerStyles, {
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  });
  assert.ok(
    await customerLabels.evaluateAll((labels) =>
      labels.some((label) => label.scrollWidth > label.clientWidth),
    ),
    "Expected at least one customer name to be visually truncated",
  );

  for (const kind of ["pause", "idle"]) {
    const segments = page.locator(`[data-kind="${kind}"]`);
    for (let index = 0; index < await segments.count(); index += 1) {
      const segment = segments.nth(index);
      assert.equal(
        (await segment.textContent()).trim(),
        await segment.getAttribute("data-duration"),
      );
      assert.equal(await segment.getAttribute("tabindex"), "0");
      assert.equal(await segment.getAttribute("aria-describedby"), "order-tooltip");
      assert.ok(await segment.getAttribute("data-start"));
      assert.ok(await segment.getAttribute("data-end"));
    }
  }

  assert.equal(await page.locator(".insight-footer").count(), 0);
  assert.equal(await page.getByText("Най-дълъг период", { exact: false }).count(), 0);

  const firstOrder = page.locator('[data-kind="order"]').first();
  await firstOrder.hover();
  const tooltip = page.locator("#order-tooltip.is-visible");
  await assert.doesNotReject(() => tooltip.waitFor({ timeout: 2000 }));
  const tooltipText = await tooltip.innerText();
  assert.match(tooltipText, /Поръчка 25278/);
  assert.match(tooltipText, /Пелети Пирин/);
  assert.match(tooltipText, /Производителност\s+74 кг\/ч/);
  assert.match(tooltipText, /Начало\s+14:40/);
  assert.match(tooltipText, /Край\s+23:00/);
  assert.match(tooltipText, /Активно време\s+8ч 20м/);

  await firstOrder.click();
  assert.equal(await page.locator("dialog").count(), 0);

  await page.mouse.move(20, 20);
  await assert.doesNotReject(() =>
    page.locator("#order-tooltip").waitFor({ state: "hidden", timeout: 2000 }),
  );

  await page.getByRole("button", { name: "Обнови" }).focus();
  await firstOrder.focus();
  await assert.doesNotReject(() =>
    page.locator("#order-tooltip.is-visible").waitFor({ timeout: 2000 }),
  );
  await page.getByRole("button", { name: "Обнови" }).focus();
  await assert.doesNotReject(() =>
    page.locator("#order-tooltip").waitFor({ state: "hidden", timeout: 2000 }),
  );

  const firstPause = page.locator('[data-kind="pause"]').first();
  await firstPause.hover();
  await assert.doesNotReject(() => tooltip.waitFor({ timeout: 2000 }));
  const pauseTooltipText = await tooltip.innerText();
  assert.match(pauseTooltipText, /Пауза/);
  assert.match(pauseTooltipText, /Машина 1/);
  assert.match(pauseTooltipText, /Начало\s+23:00/);
  assert.match(pauseTooltipText, /Край\s+23:45/);
  assert.match(pauseTooltipText, /Продължителност\s+45м/);
  assert.doesNotMatch(pauseTooltipText, /Производителност/);

  await page.mouse.move(20, 20);
  const firstIdle = page.locator('[data-kind="idle"]').first();
  await firstIdle.hover();
  await assert.doesNotReject(() => tooltip.waitFor({ timeout: 2000 }));
  const idleTooltipText = await tooltip.innerText();
  assert.match(idleTooltipText, /Без производство/);
  assert.match(idleTooltipText, /Машина 1/);
  assert.match(idleTooltipText, /Начало\s+13:00/);
  assert.match(idleTooltipText, /Край\s+14:40/);
  assert.match(idleTooltipText, /Продължителност\s+1ч 40м/);

  await firstPause.focus();
  await assert.doesNotReject(() => tooltip.waitFor({ timeout: 2000 }));
  assert.match(await tooltip.innerText(), /Пауза/);
  await page.getByRole("button", { name: "Обнови" }).focus();

  assert.equal(
    (await page.locator("#productivity-review-title").textContent()).trim(),
    "Производителност по поръчки",
  );
  const machineGroups = page.locator(".productivity-machine-group");
  assert.equal(await machineGroups.count(), 4);
  assert.deepEqual(
    await machineGroups.locator(".productivity-machine-title").allTextContents(),
    ["Машина 1", "Машина 2", "Машина 3", "Машина 4"],
  );
  assert.deepEqual(
    await machineGroups.evaluateAll((groups) =>
      groups.map((group) =>
        [...group.querySelectorAll(".productivity-row .review-order strong")].map(
          (order) => order.textContent.trim(),
        ),
      ),
    ),
    [
      ["25278", "25281"],
      ["25280", "25282", "25285"],
      ["25283"],
      ["25284"],
    ],
  );
  assert.equal(await page.locator(".productivity-row").count(), 7);
  for (let index = 0; index < 4; index += 1) {
    const group = machineGroups.nth(index);
    assert.deepEqual(await group.locator(".header-label").allTextContents(), [
      "Поръчка",
      "Размер",
      "Произведено",
      "Време",
      "Производителност",
    ]);
    assert.deepEqual(await group.locator(".header-unit").allTextContents(), [
      "(мм)",
      "(кг)",
      "(кг/ч)",
    ]);
  }
  assert.equal(
    await page.getByRole("columnheader", { name: "Машина", exact: true }).count(),
    0,
  );
  assert.equal(
    await page.getByRole("columnheader", {
      name: "Обичайна производителност",
      exact: true,
    }).count(),
    0,
  );
  assert.equal(await page.locator(".review-method").count(), 0);
  assert.equal(await page.locator(".review-summary").count(), 0);
  assert.equal(await page.locator(".status-pill").count(), 0);
  assert.equal(await page.locator(".range-visual").count(), 0);
  const productivityGauges = page.locator(".productivity-gauge");
  const noBaselines = page.locator(".productivity-no-baseline");
  assert.equal(await productivityGauges.count(), 4);
  assert.equal(await noBaselines.count(), 3);

  const exactGaugeData = [
    ["25278", "55", "74", "65", "3"],
    ["25280", "37", "69", "41", "2"],
    ["25282", "36", "76", "36", "1"],
    ["25283", "22", "64", "22", "1"],
  ];
  for (const [order, minimum, current, maximum, sampleCount] of exactGaugeData) {
    const gauge = page.locator(`[data-order-row="${order}"] .productivity-gauge`);
    assert.equal(await gauge.count(), 1);
    assert.equal(await gauge.getAttribute("data-min"), minimum);
    assert.equal(await gauge.getAttribute("data-current"), current);
    assert.equal(await gauge.getAttribute("data-max"), maximum);
    assert.equal(await gauge.getAttribute("data-sample-count"), sampleCount);
  }

  for (const order of ["25281", "25285", "25284"]) {
    const noBaseline = page.locator(
      `[data-order-row="${order}"] .productivity-no-baseline`,
    );
    assert.equal(await noBaseline.count(), 1);
    assert.equal((await noBaseline.textContent()).trim(), "—");
    assert.equal(await noBaseline.getAttribute("data-sample-count"), null);
    assert.equal(await noBaseline.getAttribute("data-samples"), null);
    assert.equal(await noBaseline.getAttribute("tabindex"), null);
    assert.equal(await noBaseline.getAttribute("aria-describedby"), null);
  }

  assert.ok(
    await productivityGauges.evaluateAll((gauges) =>
      gauges.every(
        (gauge) =>
          gauge.getAttribute("tabindex") === "0" &&
          gauge.getAttribute("aria-describedby") === "productivity-tooltip" &&
          Number(gauge.getAttribute("data-sample-count")) >= 1 &&
          (gauge.getAttribute("data-samples") || "").split(";").filter(Boolean)
            .length <= 7,
      ),
    ),
  );
  assert.ok(
    await productivityGauges.evaluateAll((gauges) => {
      const pauseColor = getComputedStyle(
        document.querySelector(".legend-swatch.pause"),
      ).backgroundColor;
      return gauges.every((gauge) => {
        const actual = gauge.closest(".productivity-cell-layout").querySelector(
          ".productivity-actual",
        );
        const marker = gauge.querySelector(".productivity-gauge-marker");
        if (!actual || !marker) return false;
        const actualRect = actual.getBoundingClientRect();
        const gaugeRect = gauge.getBoundingClientRect();
        const markerRect = marker.getBoundingClientRect();
        return (
          actualRect.right + 12 <= gaugeRect.left &&
          markerRect.width >= 3 &&
          getComputedStyle(marker).backgroundColor === pauseColor
        );
      });
    }),
    "Expected actual productivity on the left and an orange marker on the right",
  );

  const multiSampleGauges = page.locator(
    ".productivity-gauge:not(.is-single-sample)",
  );
  assert.equal(await multiSampleGauges.count(), 2);
  assert.ok(
    await multiSampleGauges.evaluateAll((gauges) =>
      gauges.every((gauge) => {
        const band = gauge.querySelector(".productivity-gauge-band");
        const minLabel = gauge.querySelector(".productivity-gauge-min");
        const maxLabel = gauge.querySelector(".productivity-gauge-max");
        if (!band || !minLabel || !maxLabel) return false;
        const bandRect = band.getBoundingClientRect();
        const minRect = minLabel.getBoundingClientRect();
        const maxRect = maxLabel.getBoundingClientRect();
        return (
          Math.abs(minRect.left + minRect.width / 2 - bandRect.left) <= 3 &&
          Math.abs(maxRect.left + maxRect.width / 2 - bandRect.right) <= 3
        );
      }),
    ),
    "Expected multi-order historical bounds beneath their blue range endpoints",
  );

  const singleSampleGauges = page.locator(".productivity-gauge.is-single-sample");
  assert.equal(await singleSampleGauges.count(), 2);
  assert.ok(
    await singleSampleGauges.evaluateAll((gauges) =>
      gauges.every((gauge) => {
        const point = gauge.querySelector(".productivity-gauge-band");
        const label = gauge.querySelector(".productivity-gauge-single");
        return (
          point &&
          label &&
          point.getBoundingClientRect().width >= 5 &&
          gauge.querySelectorAll(".productivity-gauge-min, .productivity-gauge-max")
            .length === 0
        );
      }),
    ),
    "Expected one historical order to render as one blue point with one value label",
  );

  const gauge25278 = page.locator('[data-order-row="25278"] .productivity-gauge');
  await gauge25278.scrollIntoViewIfNeeded();
  await gauge25278.hover();
  const productivityTooltip = page.locator("#productivity-tooltip.is-visible");
  await assert.doesNotReject(() => productivityTooltip.waitFor({ timeout: 2000 }));
  assert.match(await productivityTooltip.innerText(), /3 поръчки със същия размер/);
  assert.match(await productivityTooltip.innerText(), /25412/);
  assert.match(await productivityTooltip.innerText(), /25416/);
  assert.match(await productivityTooltip.innerText(), /25459/);
  assert.match(await productivityTooltip.innerText(), /450 × 0\.060/);
  assert.match(await productivityTooltip.innerText(), /65 кг\/ч/);
  assert.doesNotMatch(await productivityTooltip.innerText(), /25458|25473/);
  assert.equal(await productivityTooltip.locator("li").count(), 3);
  await page.mouse.move(20, 20);
  await assert.doesNotReject(() =>
    page.locator("#productivity-tooltip").waitFor({ state: "hidden", timeout: 2000 }),
  );

  const gauge25280 = page.locator('[data-order-row="25280"] .productivity-gauge');
  await gauge25280.hover();
  await assert.doesNotReject(() => productivityTooltip.waitFor({ timeout: 2000 }));
  assert.match(await productivityTooltip.innerText(), /2 поръчки със същия размер/);
  assert.match(await productivityTooltip.innerText(), /25476/);
  assert.match(await productivityTooltip.innerText(), /25478/);
  assert.equal(await productivityTooltip.locator("li").count(), 2);
  await page.mouse.move(20, 20);

  const gauge25282 = page.locator('[data-order-row="25282"] .productivity-gauge');
  await gauge25282.hover();
  await assert.doesNotReject(() => productivityTooltip.waitFor({ timeout: 2000 }));
  assert.match(await productivityTooltip.innerText(), /1 поръчка със същия размер/);
  assert.match(await productivityTooltip.innerText(), /25449/);
  assert.equal(await productivityTooltip.locator("li").count(), 1);
  await page.mouse.move(20, 20);

  const gauge25283 = page.locator('[data-order-row="25283"] .productivity-gauge');
  await gauge25283.scrollIntoViewIfNeeded();
  await gauge25283.focus();
  await assert.doesNotReject(() => productivityTooltip.waitFor({ timeout: 2000 }));
  assert.match(await productivityTooltip.innerText(), /25463/);
  assert.match(await productivityTooltip.innerText(), /590 × 0\.150/);
  await page.getByRole("button", { name: "Обнови" }).focus();

  const noBaseline25284 = page.locator(
    '[data-order-row="25284"] .productivity-no-baseline',
  );
  await noBaseline25284.scrollIntoViewIfNeeded();
  await noBaseline25284.hover();
  assert.equal(await page.locator("#productivity-tooltip").isVisible(), false);

  await gauge25278.evaluate((gauge) => {
    gauge.dataset.sampleCount = "50";
    gauge.dataset.samples = [
      "25507|450 × 0.060|63",
      "25506|450 × 0.060|62",
      "25505|450 × 0.060|61",
      "25504|450 × 0.060|60",
      "25503|450 × 0.060|59",
      "25502|450 × 0.060|58",
      "25501|450 × 0.060|57",
      "25500|450 × 0.060|56",
    ].join(";");
  });
  await gauge25278.hover();
  await assert.doesNotReject(() => productivityTooltip.waitFor({ timeout: 2000 }));
  assert.match(await productivityTooltip.innerText(), /50 поръчки със същия размер/);
  assert.equal(await productivityTooltip.locator("li").count(), 7);
  assert.match(await productivityTooltip.innerText(), /25507/);
  assert.match(await productivityTooltip.innerText(), /25501/);
  assert.doesNotMatch(await productivityTooltip.innerText(), /25500/);
  await page.reload({ waitUntil: "load" });
  assert.equal(await page.locator("[data-review-status]").count(), 0);
  assert.equal(await page.locator(".productivity-review-head p").count(), 0);
  const reviewText = await page.locator(".productivity-review").innerText();
  assert.match(reviewText, /25280/);
  assert.match(reviewText, /Клиент Екзампъл Интернешънъл/);
  assert.match(reviewText, /345/);
  assert.match(reviewText, /5ч 00м/);
  assert.match(reviewText, /69/);
  assert.match(reviewText, /37/);
  assert.match(reviewText, /41/);
  assert.match(reviewText, /25278/);
  assert.match(reviewText, /55/);
  assert.match(reviewText, /65/);
  assert.match(reviewText, /25283/);
  assert.match(reviewText, /25284/);
  assert.ok(
    await page.locator(".review-size strong").evaluateAll((values) =>
      values.every((value) => !/мм/i.test(value.textContent)),
    ),
  );
  assert.ok(
    await page.locator(".review-produced strong").evaluateAll((values) =>
      values.every((value) => !/кг/i.test(value.textContent)),
    ),
  );
  assert.ok(
    await page.locator(".productivity-cell-layout").evaluateAll((values) =>
      values.every((value) => !/кг\/ч/i.test(value.textContent)),
    ),
  );
  const reviewCustomers = page.locator(".review-order span");
  assert.equal(await reviewCustomers.count(), 7);
  assert.deepEqual(
    await reviewCustomers.first().evaluate((label) => {
      const styles = getComputedStyle(label);
      return {
        overflow: styles.overflow,
        textOverflow: styles.textOverflow,
        whiteSpace: styles.whiteSpace,
      };
    }),
    { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  );
  for (const unwantedCopy of [
    /Какво е „обичайно“/,
    /5-те най-близки/,
    /Материалът все още не участва/,
    /По-бързо от обичайното/,
    /В обичайния диапазон/,
    /Недостатъчна история/,
    /Няма завършена история/,
    /Няма база/,
    /Провери/,
    /В норма/,
  ]) {
    assert.doesNotMatch(reviewText, unwantedCopy);
  }
  assert.equal(await page.getByText(/потвърждение при завършване/i).count(), 0);

  await page.getByRole("button", { name: "Обнови" }).click();
  await assert.doesNotReject(() =>
    page.getByRole("button", { name: "Обновяване…" }).waitFor(),
  );
  await assert.doesNotReject(() =>
    page.getByRole("button", { name: "Обнови" }).waitFor({ state: "visible" }),
  );
  assert.equal(await page.getByText(/Обновено/, { exact: false }).count(), 0);

  const overflow = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
  }));
  assert.ok(
    overflow.documentWidth <= overflow.viewportWidth,
    `Horizontal overflow: ${JSON.stringify(overflow)}`,
  );
  const timelineOverflow = await page.locator(".timeline-scroll").evaluate((node) => ({
    clientWidth: node.clientWidth,
    overflowX: getComputedStyle(node).overflowX,
    scrollWidth: node.scrollWidth,
  }));
  assert.equal(timelineOverflow.overflowX, "visible");
  assert.ok(
    timelineOverflow.scrollWidth <= timelineOverflow.clientWidth,
    `Redundant timeline scrollbar: ${JSON.stringify(timelineOverflow)}`,
  );
  assert.deepEqual(consoleErrors, []);
  assert.deepEqual(pageErrors, []);

  await page.reload({ waitUntil: "load" });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: viewportScreenshotPath });
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await page.locator(".dashboard").screenshot({ path: timelineScreenshotPath });
  await page.locator('[data-kind="order"]').first().hover();
  await page.locator("#order-tooltip.is-visible").waitFor({ timeout: 2000 });
  await page.screenshot({ path: hoverScreenshotPath });
  await page.mouse.move(20, 20);
  await page.locator('[data-kind="pause"]').first().hover();
  await page.locator("#order-tooltip.is-visible").waitFor({ timeout: 2000 });
  await page.screenshot({ path: pauseHoverScreenshotPath });
  await page.mouse.move(20, 20);
  await page.locator('[data-kind="idle"]').first().hover();
  await page.locator("#order-tooltip.is-visible").waitFor({ timeout: 2000 });
  await page.screenshot({ path: idleHoverScreenshotPath });
  await page.mouse.move(20, 20);
  const screenshotGauge = page.locator('[data-order-row="25278"] .productivity-gauge');
  await screenshotGauge.scrollIntoViewIfNeeded();
  await screenshotGauge.hover();
  await page.locator("#productivity-tooltip.is-visible").waitFor({ timeout: 2000 });
  await page.screenshot({ path: productivityHoverScreenshotPath });
  await page.mouse.move(20, 20);
  await page.locator(".productivity-review").screenshot({ path: productivityScreenshotPath });

  for (const width of [1024, 820]) {
    await page.setViewportSize({ width, height: 1024 });
    await page.reload({ waitUntil: "load" });
    await page.evaluate(() => window.scrollTo(0, 0));
    const responsiveOverflow = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
    }));
    assert.ok(
      responsiveOverflow.documentWidth <= responsiveOverflow.viewportWidth,
      `Horizontal overflow at ${width}px: ${JSON.stringify(responsiveOverflow)}`,
    );
    const reviewBox = await page.locator(".productivity-review").boundingBox();
    assert.ok(reviewBox.width <= width, `Productivity review exceeds ${width}px viewport`);
    assert.ok(
      await page.locator(".productivity-table").evaluateAll((tables) =>
        tables.every((table) => {
          const styles = getComputedStyle(table);
          return styles.display !== "none" && table.getBoundingClientRect().height > 0;
        }),
      ),
    );
    if (width === 1024) {
      await page.screenshot({ path: responsiveScreenshotPath, fullPage: true });
    } else {
      await page.screenshot({ path: narrowScreenshotPath, fullPage: true });
    }
  }

  await page.setViewportSize({ width: 1440, height: 1024 });

  if (sourceVisualPath) {
    const sourceDataUrl = `data:image/png;base64,${(await readFile(sourceVisualPath)).toString("base64")}`;
    const prototypeDataUrl = `data:image/png;base64,${(await readFile(viewportScreenshotPath)).toString("base64")}`;
    const comparisonPage = await browser.newPage({ viewport: { width: 1440, height: 560 } });
    await comparisonPage.setContent(`
      <!doctype html>
      <html>
        <head>
          <style>
            * { box-sizing: border-box; }
            body { margin: 0; padding: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; background: #111827; font: 700 14px "Segoe UI", sans-serif; color: white; }
            figure { margin: 0; display: grid; gap: 8px; }
            figcaption { text-align: center; }
            img { display: block; width: 100%; height: 510px; object-fit: fill; background: white; }
          </style>
        </head>
        <body>
          <figure><figcaption>Избран визуален източник</figcaption><img src="${sourceDataUrl}" alt=""></figure>
          <figure><figcaption>HTML прототип</figcaption><img src="${prototypeDataUrl}" alt=""></figure>
        </body>
      </html>
    `);
    await comparisonPage.locator("img").last().waitFor();
    await comparisonPage.screenshot({ path: comparisonPath, fullPage: true });
    await comparisonPage.close();
  }

  process.stdout.write(`Verified dashboard prototype: ${screenshotPath}\n`);
  process.stdout.write(`Saved hover-state evidence: ${hoverScreenshotPath}\n`);
  process.stdout.write(`Saved pause-state evidence: ${pauseHoverScreenshotPath}\n`);
  process.stdout.write(`Saved inactive-state evidence: ${idleHoverScreenshotPath}\n`);
  process.stdout.write(`Saved productivity evidence: ${productivityScreenshotPath}\n`);
  process.stdout.write(`Saved productivity hover evidence: ${productivityHoverScreenshotPath}\n`);
  process.stdout.write(`Saved responsive evidence: ${responsiveScreenshotPath}\n`);
  process.stdout.write(`Saved narrow evidence: ${narrowScreenshotPath}\n`);
  if (sourceVisualPath) {
    process.stdout.write(`Saved visual comparison: ${comparisonPath}\n`);
  } else {
    process.stdout.write(
      "Skipped visual comparison: DASHBOARD_SOURCE_VISUAL is not set.\n",
    );
  }
} finally {
  await browser.close();
}
