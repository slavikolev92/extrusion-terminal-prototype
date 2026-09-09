export const VERIFICATION_CONTRACT = Object.freeze({
  expectedLongCustomer: "Дългосрочен индустриален клиент Балкан Пак България АД",
  expectedLongProduct: (
    "Термоусадъчно полиетиленово фолио за групова транспортна опаковка "
    + "850 / 0.060 мм"
  ),
  compactStressLongCustomer: (
    "Дългосрочен индустриален клиент Балкан Пак България АД – регионален "
    + "център за опаковъчни решения и специализирани производствени доставки"
  ),
  compactStressLongProduct: (
    "Термоусадъчно полиетиленово фолио за групова транспортна опаковка с "
    + "усилена устойчивост за многокомпонентни индустриални палетни товари и "
    + "продължително складово съхранение 850 / 0.060 мм"
  ),
  viewportCoverage: Object.freeze([
    Object.freeze({
      width: 1440,
      height: 900,
      checkLongOrderValues: true,
      checkStableTableScroll: true,
    }),
    Object.freeze({
      width: 1366,
      height: 768,
      checkLongOrderValues: true,
      checkStableTableScroll: true,
    }),
  ]),
  screenshots: Object.freeze([
    "active-normal-1440x900.png",
    "active-marked-empty-1366x768.png",
    "waiting-read-only-1440x900.png",
    "waiting-scrolled-1366x768.png",
    "waiting-validation-error-1366x768.png",
  ]),
  screenshotDimensions: Object.freeze([
    Object.freeze({ width: 1440, height: 900 }),
    Object.freeze({ width: 1366, height: 768 }),
    Object.freeze({ width: 1440, height: 900 }),
    Object.freeze({ width: 1366, height: 768 }),
    Object.freeze({ width: 1366, height: 768 }),
  ]),
});


function screenshotFilename(value) {
  return String(value || "").split(/[\\/]/).at(-1);
}


export function assertExactScreenshotEvidence(summary) {
  const screenshots = Array.isArray(summary?.screenshots) ? summary.screenshots : [];
  const dimensions = Array.isArray(summary?.screenshotDimensions)
    ? summary.screenshotDimensions
    : [];
  const expectedNames = VERIFICATION_CONTRACT.screenshots;
  const expectedDimensions = VERIFICATION_CONTRACT.screenshotDimensions;
  if (screenshots.length !== expectedNames.length || dimensions.length !== expectedNames.length) {
    throw new Error("Screenshot evidence must contain exactly the required five files.");
  }
  for (let index = 0; index < expectedNames.length; index += 1) {
    const expectedName = expectedNames[index];
    const expectedSize = expectedDimensions[index];
    const screenshotName = screenshotFilename(screenshots[index]);
    const dimensionName = screenshotFilename(dimensions[index]?.path);
    if (screenshotName !== expectedName || dimensionName !== expectedName) {
      throw new Error(`Screenshot evidence order mismatch at index ${index}.`);
    }
    if (
      dimensions[index]?.width !== expectedSize.width
      || dimensions[index]?.height !== expectedSize.height
    ) {
      throw new Error(`Screenshot dimensions mismatch for ${expectedName}.`);
    }
  }
  return true;
}
