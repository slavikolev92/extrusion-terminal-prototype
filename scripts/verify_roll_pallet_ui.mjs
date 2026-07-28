import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";


function requiredEnvironment(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Required environment variable ${name} is missing.`);
  }
  return value;
}


const baseURL = requiredEnvironment("BASE_URL").replace(/\/+$/, "");
const fixtureInput = requiredEnvironment("FIXTURE_JSON");
const artifactInput = requiredEnvironment("ARTIFACT_DIR");
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = fs.realpathSync(path.resolve(scriptDir, ".."));
const runtimeRoot = path.resolve(repoRoot, ".test-runtime");
const artifactRoot = path.resolve(repoRoot, "artifacts", "ui-checks");
const requestedFixturePath = path.resolve(repoRoot, fixtureInput);
const artifactDir = path.resolve(repoRoot, artifactInput);
const summaryPath = path.join(artifactDir, "verification-summary.json");
const evidenceOutputNames = [
  "verification-summary.json",
  "terminal-pallet-entry-1536x1024.png",
  "terminal-pallet-correction-1366x768.png",
  "terminal-pallet-only-notice-1536x1024.png",
  "admin-pallet-ledger.png",
  "normal-pallet-print.pdf",
  "print-pallet-back-page.png",
  "overflow-pallet-print.pdf",
  "print-pallet-overflow-page-3.png",
];


function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}


function assertEqual(actual, expected, label) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `${label}: expected ${JSON.stringify(expected)}, found ${JSON.stringify(actual)}`,
    );
  }
}


function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}


function isStrictChild(parent, candidate) {
  const relative = path.relative(parent, candidate);
  return Boolean(relative) && !relative.startsWith("..") && !path.isAbsolute(relative);
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


function assertEvidenceOutputLeaves() {
  for (const outputName of evidenceOutputNames) {
    const outputPath = path.join(artifactDir, outputName);
    const metadata = fs.lstatSync(outputPath, { throwIfNoEntry: false });
    if (!metadata) {
      continue;
    }
    assert(
      !metadata.isSymbolicLink(),
      `Evidence output path must not be a symlink: ${outputPath}`,
    );
    assert(
      metadata.isFile(),
      `Evidence output path must be absent or a regular file: ${outputPath}`,
    );
  }
}


assert(
  isStrictChild(runtimeRoot, requestedFixturePath),
  "FIXTURE_JSON must be under .test-runtime.",
);
assert(
  isStrictChild(artifactRoot, artifactDir),
  "ARTIFACT_DIR must be below artifacts/ui-checks.",
);
assertNoSymlinkComponents(
  repoRoot,
  artifactDir,
  "ARTIFACT_DIR guard path must not contain symlinks.",
);
assert(
  fs.existsSync(requestedFixturePath),
  `Fixture JSON does not exist: ${requestedFixturePath}`,
);
const fixturePath = fs.realpathSync(requestedFixturePath);
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), fixturePath),
  "FIXTURE_JSON must resolve below .test-runtime.",
);
fs.mkdirSync(artifactRoot, { recursive: true });
assertNoSymlinkComponents(
  repoRoot,
  artifactDir,
  "ARTIFACT_DIR guard path must not contain symlinks.",
);
let existingArtifactAncestor = artifactDir;
while (!fs.existsSync(existingArtifactAncestor)) {
  existingArtifactAncestor = path.dirname(existingArtifactAncestor);
}
assert(
  existingArtifactAncestor === artifactRoot
    || isStrictChild(fs.realpathSync(artifactRoot), fs.realpathSync(existingArtifactAncestor)),
  "ARTIFACT_DIR resolves outside artifacts/ui-checks.",
);
fs.mkdirSync(artifactDir, { recursive: true });
assert(
  isStrictChild(fs.realpathSync(artifactRoot), fs.realpathSync(artifactDir)),
  "ARTIFACT_DIR resolves outside artifacts/ui-checks.",
);
assertEvidenceOutputLeaves();

const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const databasePath = fs.realpathSync(path.resolve(fixture.db_path));
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), databasePath),
  "Fixture database must resolve below .test-runtime.",
);

const require = createRequire(import.meta.url);
const { chromium } = require("@playwright/test");
const summary = {
  baseURL,
  fixture: path.relative(repoRoot, fixturePath),
  database: path.relative(repoRoot, databasePath),
  artifacts: [],
  viewports: [],
  interactions: [],
  print: {},
};


function recordArtifact(name) {
  const target = path.join(artifactDir, name);
  assert(fs.existsSync(target), `Missing artifact ${target}`);
  assert(fs.statSync(target).size > 0, `Empty artifact ${target}`);
  summary.artifacts.push(path.relative(repoRoot, target));
}


async function preflightDatabase(page) {
  const response = await page.goto(`${baseURL}/health`, { waitUntil: "networkidle" });
  assert(response?.ok(), `Health preflight returned HTTP ${response?.status() || "unknown"}.`);
  const health = await response.json();
  assertEqual(
    fs.realpathSync(path.resolve(health.database_path)),
    databasePath,
    "server database identity",
  );
}


function resetFixtureDatabase() {
  const result = spawnSync(
    path.join(repoRoot, ".venv", "bin", "python"),
    [
      path.join(repoRoot, "scripts", "create_roll_pallet_fixture.py"),
      "--db-path",
      databasePath,
      "--output",
      fixturePath,
    ],
    { cwd: repoRoot, encoding: "utf8" },
  );
  assert(
    result.status === 0,
    `Could not reset guarded fixture: ${normalizeText(result.stderr || result.stdout)}`,
  );
  const refreshed = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  assertEqual(refreshed.cards, fixture.cards, "fixture card IDs after reset");
  assertEqual(
    fs.realpathSync(path.resolve(refreshed.db_path)),
    databasePath,
    "fixture database after reset",
  );
}


function boxesDoNotOverlap(left, right, label) {
  assert(left !== null && right !== null, `Missing ${label} geometry.`);
  const separated = (
    left.x + left.width <= right.x + 0.5
    || right.x + right.width <= left.x + 0.5
    || left.y + left.height <= right.y + 0.5
    || right.y + right.height <= left.y + 0.5
  );
  assert(separated, `${label} controls overlap.`);
}


async function openRollEditor(page, rollId, rollNumber) {
  const row = page.locator(`.roll-row[data-roll-id='${rollId}']`);
  const openButton = row.getByRole("button", {
    name: `Редактирай ролка ${rollNumber}`,
    exact: true,
  });
  await openButton.click();
  const actions = page.locator(`[data-roll-actions-for='${rollId}']`);
  await actions.waitFor({ state: "visible" });
  assertEqual(await row.getAttribute("data-roll-edit-open"), "true", `roll ${rollNumber} editor state`);
  assertEqual(
    await page.locator(".roll-row[data-roll-edit-open='true']").count(),
    1,
    `roll ${rollNumber} only open row`,
  );
  assertEqual(
    await page.locator("[data-roll-actions-for]:visible").count(),
    1,
    `roll ${rollNumber} only visible action panel`,
  );
  assertEqual(
    await row.locator("[data-roll-correction-input]:visible:not([disabled])").count(),
    3,
    `roll ${rollNumber} enabled correction inputs`,
  );
  assertEqual(
    await page.locator("button[data-roll-edit-open]:disabled").count(),
    Math.max(0, await page.locator("button[data-roll-edit-open]").count() - 1),
    `roll ${rollNumber} other pencil controls disabled`,
  );
  return { row, actions };
}


async function closeRollEditor(page, rollId, rollNumber) {
  await page.locator(`[data-roll-actions-for='${rollId}'] [data-roll-row-cancel]`).click();
  const row = page.locator(`.roll-row[data-roll-id='${rollId}']`);
  assertEqual(await row.getAttribute("data-roll-edit-open"), "false", `roll ${rollNumber} closed editor state`);
  assertEqual(
    await page.locator(".roll-row[data-roll-edit-open='true']").count(),
    0,
    `roll ${rollNumber} no open row after cancel`,
  );
  assertEqual(
    await page.locator("[data-roll-correction-input]:visible").count(),
    0,
    `roll ${rollNumber} hidden correction inputs after cancel`,
  );
}


async function verifyTerminalLayout(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto(
    `${baseURL}/terminal/cards/${fixture.cards.running}`,
    { waitUntil: "networkidle" },
  );
  const controls = [
    page.locator(".add-roll-form"),
    page.locator(".core-weight-field"),
    page.locator(".pallet-form"),
    page.locator(".roll-add-button"),
  ];
  const boxes = [];
  for (const control of controls) {
    await control.waitFor({ state: "visible" });
    boxes.push(await control.boundingBox());
  }
  for (let index = 0; index < boxes.length - 1; index += 1) {
    assert(
      boxes[index].x + boxes[index].width <= boxes[index + 1].x + 1,
      `Roll controls are out of order at ${viewport.width}x${viewport.height}.`,
    );
    boxesDoNotOverlap(
      boxes[index],
      boxes[index + 1],
      `roll entry ${index + 1}/${index + 2} at ${viewport.width}x${viewport.height}`,
    );
  }

  assertEqual(
    await page.locator("[data-roll-correction-input]:visible").count(),
    0,
    "read-only roll rows before pencil activation",
  );
  const firstRollId = fixture.running_roll_ids[0];
  const { row: firstRoll } = await openRollEditor(page, firstRollId, 1);
  const currentPalletInput = page.locator("[data-current-pallet-input='true']");
  const rowPalletInput = firstRoll.locator("[data-roll-correction-input][name='pallet_number']");
  for (const [input, label] of [
    [currentPalletInput, "terminal current pallet"],
    [rowPalletInput, "terminal roll pallet"],
  ]) {
    assertEqual(await input.getAttribute("type"), "text", `${label} input type`);
    assertEqual(await input.getAttribute("inputmode"), "numeric", `${label} inputmode`);
    for (const attribute of ["min", "max", "step", "pattern", "maxlength"]) {
      assertEqual(await input.getAttribute(attribute), null, `${label} ${attribute}`);
    }
  }
  const rowPalletGeometry = await rowPalletInput.evaluate((element) => {
    const inputBox = element.getBoundingClientRect();
    const cellBox = element.parentElement.getBoundingClientRect();
    return {
      inputLeft: inputBox.left,
      inputRight: inputBox.right,
      cellLeft: cellBox.left,
      cellRight: cellBox.right,
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth,
    };
  });
  assert(
    rowPalletGeometry.inputLeft >= rowPalletGeometry.cellLeft - 1
      && rowPalletGeometry.inputRight <= rowPalletGeometry.cellRight + 1,
    `Terminal roll pallet input is clipped at ${viewport.width}x${viewport.height}.`,
  );
  assert(
    rowPalletGeometry.scrollWidth <= rowPalletGeometry.clientWidth + 1,
    `Terminal roll pallet value is clipped at ${viewport.width}x${viewport.height}.`,
  );
  await closeRollEditor(page, firstRollId, 1);

  const recipe = page.locator(".recipe-table");
  const recipeRows = recipe.locator(".recipe-row");
  const renderedRecipeRow = async (index) => {
    const row = recipeRows.nth(index);
    return {
      category: normalizeText(await row.locator(".component").textContent()),
      plannedMaterial: normalizeText(await row.locator(".material-planned").textContent()),
      percent: normalizeText(await row.locator(".recipe-percent").textContent()),
      plannedKg: normalizeText(await row.locator(".recipe-kg").textContent()),
    };
  };
  assertEqual(
    await renderedRecipeRow(0),
    {
      category: "LDPE",
      plannedMaterial: "Alpha 2420H",
      percent: "55%",
      plannedKg: "1980",
    },
    `structured first recipe row at ${viewport.width}x${viewport.height}`,
  );
  assertEqual(
    await renderedRecipeRow(2),
    {
      category: "MDPE",
      plannedMaterial: "Gamma 3802",
      percent: "10%",
      plannedKg: "360",
    },
    `structured third recipe row at ${viewport.width}x${viewport.height}`,
  );
  assertEqual(
    await renderedRecipeRow(6),
    {
      category: "Filler",
      plannedMaterial: "Chalk C",
      percent: "1%",
      plannedKg: "36",
    },
    `structured final recipe row at ${viewport.width}x${viewport.height}`,
  );
  assertEqual(
    await recipeRows.count(),
    7,
    `structured recipe row count at ${viewport.width}x${viewport.height}`,
  );
  const lastRecipeRow = recipe.locator(".recipe-row").last();
  await lastRecipeRow.scrollIntoViewIfNeeded();
  const recipeGeometry = await recipe.evaluate((element) => ({
    width: element.getBoundingClientRect().width,
    scrollWidth: element.scrollWidth,
    text: element.textContent,
  }));
  const lastRowBox = await lastRecipeRow.boundingBox();
  assert(recipeGeometry.width > 0, "Recipe has no rendered width.");
  assert(recipeGeometry.scrollWidth <= recipeGeometry.width + 1, "Recipe is horizontally clipped.");
  assert(normalizeText(recipeGeometry.text).includes("Chalk C"), "The complete structured recipe is not readable.");
  assert(lastRowBox !== null, "The final recipe row is not reachable.");
  const overflow = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    rollClientWidth: document.querySelector(".roll-list")?.clientWidth || 0,
    rollScrollWidth: document.querySelector(".roll-list")?.scrollWidth || 0,
  }));
  assert(
    overflow.scrollWidth <= overflow.clientWidth + 1,
    `Terminal has horizontal overflow at ${viewport.width}x${viewport.height}.`,
  );
  assert(
    overflow.rollScrollWidth <= overflow.rollClientWidth + 1,
    `Roll list has horizontal overflow at ${viewport.width}x${viewport.height}.`,
  );
  summary.viewports.push({
    width: viewport.width,
    height: viewport.height,
    controlOrder: ["gross", "tare", "pallet", "add"],
    pencilEditor: true,
    oneEditorAtATime: true,
    structuredRecipeRows: true,
    recipeReachable: true,
    horizontalOverflow: false,
  });
}


async function submitAndWait(page, action) {
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    action(),
  ]);
}


async function verifyTerminalBehavior(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto(
    `${baseURL}/terminal/cards/${fixture.cards.running}`,
    { waitUntil: "networkidle" },
  );
  const beforeUnloadDialogs = [];
  const dialogListener = async (dialog) => {
    if (dialog.type() === "beforeunload") {
      beforeUnloadDialogs.push(dialog.message());
    }
    await dialog.accept();
  };
  page.on("dialog", dialogListener);

  const mutationPosts = [];
  const mutationRequestListener = (request) => {
    if (request.method() === "POST") {
      mutationPosts.push({
        pathname: new URL(request.url()).pathname,
        fields: Object.fromEntries(new URLSearchParams(request.postData() || "")),
      });
    }
  };
  page.on("request", mutationRequestListener);

  let tareInput = page.locator("[data-current-tare-input='true']");
  let palletInput = page.locator("[data-current-pallet-input='true']");

  const terminalCardSnapshot = async () => ({
    version: await page.locator(".add-roll-form input[name='loaded_version']").inputValue(),
    tare: await page.locator("[data-current-tare-input='true']").inputValue(),
    pallet: await page.locator("[data-current-pallet-input='true']").inputValue(),
    rolls: await page.locator(".roll-row[data-roll-id]").evaluateAll((rows) =>
      rows.map((row) => ({
        id: row.dataset.rollId,
        pallet: row.querySelector("[data-roll-display='pallet']")?.textContent.trim(),
        gross: row.querySelector("[data-roll-display='gross']")?.textContent.trim(),
        tare: row.querySelector("[data-roll-display='tare']")?.textContent.trim(),
      })),
    ),
  });

  // A malformed literal must reach the backend unchanged and fail atomically.
  const malformedDefaultBefore = await terminalCardSnapshot();
  await palletInput.fill("15+1");
  const malformedDefaultPostStart = mutationPosts.length;
  await submitAndWait(page, () => palletInput.press("Enter"));
  assertEqual(
    mutationPosts.slice(malformedDefaultPostStart),
    [{
      pathname: `/terminal/cards/${fixture.cards.running}/tare`,
      fields: {
        loaded_version: "1",
        tare_weight: "1.25",
        pallet_number: "15+1",
      },
    }],
    "malformed current pallet request",
  );
  assert(
    normalizeText(await page.locator("[data-feedback-target='pallet']").textContent())
      .includes("Палетът трябва да бъде цяло число от 1 до 999."),
    "Malformed current pallet error is not shown.",
  );
  assertEqual(
    await terminalCardSnapshot(),
    malformedDefaultBefore,
    "state after malformed current pallet",
  );
  tareInput = page.locator("[data-current-tare-input='true']");
  palletInput = page.locator("[data-current-pallet-input='true']");

  // Regression (a): Enter persists both dirty defaults in one optimistic write.
  await tareInput.fill("2.50");
  await palletInput.fill("9");
  const enterPostStart = mutationPosts.length;
  await submitAndWait(page, () => palletInput.press("Enter"));
  assertEqual(
    mutationPosts.slice(enterPostStart),
    [{
      pathname: `/terminal/cards/${fixture.cards.running}/tare`,
      fields: {
        loaded_version: "1",
        tare_weight: "2.50",
        pallet_number: "9",
      },
    }],
    "coordinated Enter autosave request",
  );
  tareInput = page.locator("[data-current-tare-input='true']");
  palletInput = page.locator("[data-current-pallet-input='true']");
  assertEqual(await tareInput.inputValue(), "2.5", "autosaved tare after Enter navigation");
  assertEqual(await palletInput.inputValue(), "9", "autosaved pallet after Enter navigation");
  await page.reload({ waitUntil: "networkidle" });
  tareInput = page.locator("[data-current-tare-input='true']");
  palletInput = page.locator("[data-current-pallet-input='true']");
  assertEqual(await tareInput.inputValue(), "2.5", "autosaved tare after Enter reload");
  assertEqual(await palletInput.inputValue(), "9", "autosaved pallet after Enter reload");

  // Regression (b): leaving the group saves both values before navigation.
  await tareInput.fill("2.75");
  await palletInput.fill("10");
  const outsidePostStart = mutationPosts.length;
  await submitAndWait(page, () => page.locator("#queue-open").click());
  assertEqual(
    mutationPosts.slice(outsidePostStart),
    [{
      pathname: `/terminal/cards/${fixture.cards.running}/tare`,
      fields: {
        loaded_version: "2",
        tare_weight: "2.75",
        pallet_number: "10",
      },
    }],
    "coordinated outside-group autosave request",
  );
  tareInput = page.locator("[data-current-tare-input='true']");
  palletInput = page.locator("[data-current-pallet-input='true']");
  assertEqual(await tareInput.inputValue(), "2.75", "autosaved tare after outside click");
  assertEqual(await palletInput.inputValue(), "10", "autosaved pallet after outside click");
  await page.locator("#queue-open").click();
  await page.locator("#queue-overlay").waitFor({ state: "visible" });
  await page.locator("#queue-close").click();
  await page.locator("#queue-overlay").waitFor({ state: "hidden" });

  // Regression (c): Add Roll snapshots and persists both dirty defaults atomically.
  const rollCountBefore = await page.locator(".roll-row[data-roll-id]").count();
  const grossInput = page.locator(".add-roll-form input[name='gross_weight']");
  await tareInput.fill("3.00");
  await palletInput.fill("11");
  await grossInput.fill("24.50");
  const addPostStart = mutationPosts.length;
  await submitAndWait(page, () => page.locator(".roll-add-button").click());
  const addPosts = mutationPosts.slice(addPostStart);
  assertEqual(addPosts.length, 1, "Add Roll request count");
  assertEqual(
    addPosts[0],
    {
      pathname: `/terminal/cards/${fixture.cards.running}/rolls`,
      fields: {
        loaded_version: "3",
        tare_weight: "3.00",
        pallet_number: "11",
        gross_weight: "24.50",
      },
    },
    "atomic Add Roll request",
  );
  assertEqual(
    await page.locator("[data-current-tare-input='true']").inputValue(),
    "3",
    "current tare retained after adding a roll",
  );
  assertEqual(
    await page.locator("[data-current-pallet-input='true']").inputValue(),
    "11",
    "current pallet retained after adding a roll",
  );
  assertEqual(
    await page.locator(".roll-row[data-roll-id]").count(),
    rollCountBefore + 1,
    "roll count after adding",
  );
  const newestRow = page.locator(".roll-row[data-roll-id]").last();
  assertEqual(
    normalizeText(await newestRow.locator("[data-roll-display='pallet']").textContent()),
    "11",
    "new roll pallet snapshot",
  );
  assertEqual(
    Number(normalizeText(await newestRow.locator("[data-roll-display='tare']").textContent())),
    3,
    "new roll tare snapshot",
  );
  assertEqual(beforeUnloadDialogs, [], "beforeunload dialogs during coordinated saves");
  page.off("dialog", dialogListener);
  if (viewport.width === 1536 && viewport.height === 1024) {
    await page.screenshot({
      path: path.join(artifactDir, "terminal-pallet-entry-1536x1024.png"),
      fullPage: true,
    });
    recordArtifact("terminal-pallet-entry-1536x1024.png");
  }

  const firstRollId = fixture.running_roll_ids[0];
  const clearCandidateRollId = fixture.clear_candidate_roll_id;
  const malformedCorrectionBefore = await terminalCardSnapshot();
  let { row: firstRow, actions: firstActions } = await openRollEditor(page, firstRollId, 1);
  const firstRollLoadedVersion = await firstRow.locator("input[name='loaded_version']").inputValue();
  const firstRollTare = await firstRow.locator("input[name='tare_weight']").inputValue();
  await firstRow.locator("input[name='pallet_number']").fill("15+1");
  await firstRow.locator("input[name='gross_weight']").fill("99.99");
  const malformedCorrectionPostStart = mutationPosts.length;
  await submitAndWait(page, () => firstActions.locator("[data-roll-row-save]").click());
  const malformedCorrectionPosts = mutationPosts.slice(malformedCorrectionPostStart);
  assertEqual(
    malformedCorrectionPosts,
    [{
      pathname: `/terminal/cards/${fixture.cards.running}/rolls/${firstRollId}`,
      fields: {
        loaded_version: firstRollLoadedVersion,
        gross_weight: "99.99",
        tare_weight: firstRollTare,
        pallet_number: "15+1",
      },
    }],
    "malformed row-scoped roll correction request",
  );
  assert(
    normalizeText(await page.locator(`[data-feedback-roll-id='${firstRollId}']`).textContent())
      .includes("Палетът трябва да бъде цяло число от 1 до 999."),
    "Malformed roll pallet error is not shown.",
  );
  assertEqual(
    await terminalCardSnapshot(),
    malformedCorrectionBefore,
    "state after malformed roll correction",
  );

  firstRow = page.locator(`.roll-row[data-roll-id='${firstRollId}']`);
  firstActions = page.locator(`[data-roll-actions-for='${firstRollId}']`);
  assertEqual(await firstRow.getAttribute("data-roll-edit-open"), "true", "malformed row remains open");
  await firstRow.locator("input[name='pallet_number']").fill("22");
  await submitAndWait(page, () => firstActions.locator("[data-roll-row-save]").click());
  assertEqual(
    normalizeText(await firstRow.locator("[data-roll-display='pallet']").textContent()),
    "22",
    "corrected pallet display",
  );

  let { row: clearedRow, actions: clearedActions } = await openRollEditor(
    page,
    clearCandidateRollId,
    2,
  );
  assertEqual(
    await clearedRow.locator("input[name='pallet_number']").inputValue(),
    "6",
    "assigned pallet before clear",
  );
  await clearedRow.locator("input[name='pallet_number']").fill("");
  await submitAndWait(page, () => clearedActions.locator("[data-roll-row-save]").click());
  clearedRow = page.locator(`.roll-row[data-roll-id='${clearCandidateRollId}']`);
  assertEqual(
    normalizeText(await clearedRow.locator("[data-roll-display='pallet']").textContent()),
    "-",
    "cleared pallet display",
  );
  await page.reload({ waitUntil: "networkidle" });
  clearedRow = page.locator(`.roll-row[data-roll-id='${clearCandidateRollId}']`);
  assertEqual(
    normalizeText(await clearedRow.locator("[data-roll-display='pallet']").textContent()),
    "-",
    "cleared pallet display after reload",
  );
  ({ row: clearedRow } = await openRollEditor(page, clearCandidateRollId, 2));
  if (viewport.width === 1366 && viewport.height === 768) {
    await page.screenshot({
      path: path.join(artifactDir, "terminal-pallet-correction-1366x768.png"),
      fullPage: true,
    });
    recordArtifact("terminal-pallet-correction-1366x768.png");
  }
  await closeRollEditor(page, clearCandidateRollId, 2);

  // A pallet-only defaults save uses an accurate generic success notice.
  palletInput = page.locator("[data-current-pallet-input='true']");
  const palletOnlyLoadedVersion = await page
    .locator(".roll-defaults-form input[name='loaded_version']")
    .inputValue();
  const palletOnlyTare = await page
    .locator("[data-current-tare-input='true']")
    .inputValue();
  await palletInput.fill("12");
  const palletOnlyPostStart = mutationPosts.length;
  await submitAndWait(page, () => palletInput.press("Enter"));
  assertEqual(
    mutationPosts.slice(palletOnlyPostStart),
    [{
      pathname: `/terminal/cards/${fixture.cards.running}/tare`,
      fields: {
        loaded_version: palletOnlyLoadedVersion,
        tare_weight: palletOnlyTare,
        pallet_number: "12",
      },
    }],
    "pallet-only defaults request",
  );
  assert(
    normalizeText(await page.locator(".terminal-toast").textContent())
      .includes("Данните са записани."),
    "Pallet-only save does not show the generic saved notice.",
  );
  if (viewport.width === 1536 && viewport.height === 1024) {
    await page.screenshot({
      path: path.join(artifactDir, "terminal-pallet-only-notice-1536x1024.png"),
      fullPage: true,
    });
    recordArtifact("terminal-pallet-only-notice-1536x1024.png");
  }
  page.off("request", mutationRequestListener);

  const requests = [];
  const requestListener = (request) => requests.push(request.url());
  page.on("request", requestListener);
  const requestCountBefore = requests.length;
  const urlBefore = page.url();
  await page.getByRole("button", { name: "Приключи" }).click();
  const modal = page.locator("[data-finish-confirm-modal]");
  await modal.waitFor({ state: "visible" });
  assertEqual(
    normalizeText(await modal.locator("#finish-confirm-body").textContent()),
    "В поръчката има 2 ролки без палет. Искате ли да приключите поръчката?",
    "mixed finish confirmation",
  );
  await modal.locator("[data-finish-confirm-cancel]").click();
  await modal.waitFor({ state: "hidden" });
  await page.waitForTimeout(150);
  assertEqual(requests.length, requestCountBefore, "requests after choosing Не");
  assertEqual(page.url(), urlBefore, "URL after choosing Не");
  assertEqual(
    await page.locator(".roll-row[data-roll-edit-open='true']").count(),
    0,
    "open row editors after choosing Не",
  );
  assertEqual(
    await page.locator("[data-roll-actions-for]:visible").count(),
    0,
    "visible row action panels after choosing Не",
  );
  page.off("request", requestListener);
  summary.interactions.push({
    width: viewport.width,
    height: viewport.height,
    coordinatedEnterSavedBoth: true,
    malformedCurrentPalletRejectedAtomically: true,
    malformedRollPalletRejectedAtomically: true,
    coordinatedOutsideClickSavedBoth: true,
    autosaveSurvivedReload: true,
    addCopiedCurrentTareAndPallet: true,
    beforeUnloadDialogCount: beforeUnloadDialogs.length,
    pencilEditorUsed: true,
    oneEditorAtATime: true,
    assignedPalletClearedAndPersisted: true,
    clearedDisplayAfterReload: "-",
    palletOnlyToastExact: true,
    mixedModalExact: true,
    noRequestOnNo: true,
    correctionClosedOnNo: true,
  });
}


async function verifyAdminLayout(page) {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto(
    `${baseURL}/admin/cards/${fixture.cards.running}`,
    { waitUntil: "networkidle" },
  );
  const currentInput = page.locator(".admin-roll-toolbar input[name='current_pallet_number']");
  const rowInputs = page.locator(".roll-ledger input[name^='pallet_number__']");
  await currentInput.scrollIntoViewIfNeeded();
  assertEqual(await rowInputs.count() > 0, true, "admin pallet row input count");
  for (const [input, label] of [
    [currentInput, "admin current pallet"],
    [rowInputs.first(), "admin roll pallet"],
  ]) {
    assertEqual(await input.getAttribute("type"), "text", `${label} input type`);
    assertEqual(await input.getAttribute("inputmode"), "numeric", `${label} inputmode`);
    for (const attribute of ["min", "max", "step", "pattern", "maxlength"]) {
      assertEqual(await input.getAttribute(attribute), null, `${label} ${attribute}`);
    }
  }
  for (const input of [currentInput, rowInputs.first(), rowInputs.last()]) {
    const result = await input.evaluate((element) => {
      const inputBox = element.getBoundingClientRect();
      const cellBox = element.parentElement.getBoundingClientRect();
      return {
        inputLeft: inputBox.left,
        inputRight: inputBox.right,
        cellLeft: cellBox.left,
        cellRight: cellBox.right,
        scrollWidth: element.scrollWidth,
        clientWidth: element.clientWidth,
      };
    });
    assert(
      result.inputLeft >= result.cellLeft - 1 && result.inputRight <= result.cellRight + 1,
      "Admin pallet input is clipped by its ledger cell.",
    );
    assert(result.scrollWidth <= result.clientWidth + 1, "Admin pallet value is horizontally clipped.");
  }
  await page.screenshot({
    path: path.join(artifactDir, "admin-pallet-ledger.png"),
    fullPage: true,
  });
  recordArtifact("admin-pallet-ledger.png");
}


async function injectCalibrationTables(page) {
  return await page.evaluate(() => {
    const makeTable = (className) => {
      const table = document.createElement("table");
      table.className = className;
      table.innerHTML = `
        <thead><tr><th>Палет</th><th>Ролки</th><th>Бруто, кг</th><th>Нето, кг</th></tr></thead>
        <tbody></tbody>`;
      const body = table.querySelector("tbody");
      for (let value = 1; value <= 120; value += 1) {
        const row = document.createElement("tr");
        row.dataset.palletSummaryRow = String(value);
        row.innerHTML = `<td>${value}</td><td>1</td><td>21.7</td><td>20.5</td>`;
        body.append(row);
      }
      return table;
    };

    const safeCapacity = (printPage, rows) => {
      const pageBox = printPage.getBoundingClientRect();
      const style = getComputedStyle(printPage);
      const safeBottom = pageBox.bottom - Number.parseFloat(style.paddingBottom);
      let count = 0;
      for (const row of rows) {
        const box = row.getBoundingClientRect();
        if (box.top >= pageBox.top && box.bottom <= safeBottom + 0.25) {
          count += 1;
        } else {
          break;
        }
      }
      return { count, safeBottom, pageBottom: pageBox.bottom };
    };

    const backPage = document.querySelector(".print-page-back");
    const summary = backPage.querySelector(".print-summary");
    summary.querySelectorAll(".print-pallet-summary").forEach((node) => node.remove());
    const backTable = makeTable("print-pallet-summary print-pallet-summary-middle");
    summary.append(backTable);
    const back = safeCapacity(backPage, backTable.querySelectorAll("tbody tr"));

    const overflowPage = document.createElement("section");
    overflowPage.className = "print-page print-page-pallet-overflow print-page-last";
    overflowPage.innerHTML = backPage.querySelector(".print-back-header").outerHTML;
    const overflowTable = makeTable("print-pallet-summary print-pallet-overflow-table");
    overflowPage.append(overflowTable);
    document.querySelector(".print-card").append(overflowPage);
    const overflow = safeCapacity(
      overflowPage,
      overflowTable.querySelectorAll("tbody tr"),
    );
    return { back, overflow };
  });
}


async function inspectActualPrint(page, expectedRows, kind) {
  return await page.evaluate(({ expectedRows, kind }) => {
    const tolerance = 0.5;
    const rowData = (row, table, printPage) => {
      const rowBox = row.getBoundingClientRect();
      const tableBox = table.getBoundingClientRect();
      const pageBox = printPage.getBoundingClientRect();
      const pageStyle = getComputedStyle(printPage);
      const safeBottom = pageBox.bottom - Number.parseFloat(pageStyle.paddingBottom);
      const cells = Array.from(row.cells).map((cell) => ({
        text: cell.textContent.trim(),
        horizontalFit: cell.scrollWidth <= cell.clientWidth + 1,
      }));
      return {
        label: row.dataset.palletSummaryRow,
        insideTable: rowBox.top >= tableBox.top - tolerance && rowBox.bottom <= tableBox.bottom + tolerance,
        insidePage: rowBox.top >= pageBox.top - tolerance && rowBox.bottom <= safeBottom + tolerance,
        aboveSafeBottom: rowBox.bottom <= safeBottom + tolerance,
        cells,
      };
    };

    const backPage = document.querySelector(".print-page-back");
    const middle = backPage.querySelector("[data-pallet-summary-table='middle']");
    const right = backPage.querySelector("[data-pallet-summary-table='right']");
    const middleRows = middle ? Array.from(middle.querySelectorAll("tbody tr")) : [];
    const rightRows = right ? Array.from(right.querySelectorAll("tbody tr")) : [];
    const overflowPages = Array.from(document.querySelectorAll(".print-page-pallet-overflow"));
    const overflow = overflowPages.map((printPage) => {
      const table = printPage.querySelector("[data-pallet-summary-table='overflow']");
      const rows = Array.from(table.querySelectorAll("tbody tr"));
      return rows.map((row) => rowData(row, table, printPage));
    });
    const back = [
      ...middleRows.map((row) => rowData(row, middle, backPage)),
      ...rightRows.map((row) => rowData(row, right, backPage)),
    ];
    const renderedRows = back.length + overflow.reduce((total, rows) => total + rows.length, 0);
    const palletTables = Array.from(document.querySelectorAll("[data-pallet-summary-table]"));
    const headersFit = palletTables.every((table) =>
      Array.from(table.querySelectorAll("th")).every((cell) =>
        cell.scrollWidth <= cell.clientWidth + 1
      )
    );
    const productionFits = Array.from(
      document.querySelectorAll("[data-summary-table='production'] th, [data-summary-table='production'] td"),
    ).every((cell) => cell.scrollWidth <= cell.clientWidth + 1);
    return {
      kind,
      expectedRows,
      renderedRows,
      middleCount: middleRows.length,
      rightCount: rightRows.length,
      back,
      overflow,
      overflowPageCount: overflowPages.length,
      backHasPalletTables: Boolean(middle || right),
      headersFit,
      productionFits,
    };
  }, { expectedRows, kind });
}


function assertRowsFit(rows, label) {
  for (const row of rows) {
    assert(row.insideTable, `${label} row ${row.label} is outside its table.`);
    assert(row.insidePage, `${label} row ${row.label} is outside its A4 safe bounds.`);
    assert(row.aboveSafeBottom, `${label} row ${row.label} crosses the safe bottom boundary.`);
    assert(row.cells.every((cell) => cell.horizontalFit), `${label} row ${row.label} has horizontal cell overflow.`);
  }
}


function pdfToPng(pdfPath, pageNumber, outputName) {
  const outputPrefix = path.join(artifactDir, outputName.replace(/\.png$/, ""));
  const result = spawnSync(
    "pdftoppm",
    ["-png", "-r", "144", "-f", String(pageNumber), "-l", String(pageNumber), "-singlefile", pdfPath, outputPrefix],
    { cwd: repoRoot, encoding: "utf8" },
  );
  assert(result.status === 0, `Could not rasterize ${pdfPath}: ${normalizeText(result.stderr)}`);
  recordArtifact(outputName);
}


async function verifyPrints(page) {
  await page.setViewportSize({ width: 1280, height: 1800 });
  await page.goto(
    `${baseURL}/cards/${fixture.cards.completed_mixed}/print`,
    { waitUntil: "networkidle" },
  );
  await page.emulateMedia({ media: "print" });
  const calibration = await injectCalibrationTables(page);
  assert(calibration.back.count > 0, "Measured back-page capacity is not positive.");
  assert(calibration.overflow.count > 0, "Measured overflow-page capacity is not positive.");
  summary.print.measuredBackColumnCapacity = calibration.back.count;
  summary.print.measuredOverflowPageCapacity = calibration.overflow.count;

  await page.goto(
    `${baseURL}/cards/${fixture.cards.completed_mixed}/print`,
    { waitUntil: "networkidle" },
  );
  const normal = await inspectActualPrint(
    page,
    fixture.expected_summary_rows.completed_mixed,
    "normal",
  );
  if (normal.renderedRows === 0 && fixture.expected_summary_rows.completed_mixed > 0) {
    summary.print.calibrationRequired = true;
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
    throw new Error(
      `Calibration measured back=${calibration.back.count}, overflow=${calibration.overflow.count}; production capacities are not wired.`,
    );
  }
  assertEqual(normal.renderedRows, normal.expectedRows, "normal source/rendered pallet rows");
  assertEqual(
    normal.expectedRows,
    2 * calibration.back.count,
    "normal boundary source row count",
  );
  assertEqual(normal.middleCount, calibration.back.count, "middle boundary row count");
  assertEqual(normal.rightCount, calibration.back.count, "right boundary row count");
  assertEqual(normal.overflowPageCount, 0, "normal overflow page count");
  assert(normal.headersFit, "Normal pallet headings overflow horizontally.");
  assert(normal.productionFits, "Production summary cells overflow horizontally.");
  assertRowsFit(normal.back, "page-2 pallet");
  const normalPdf = path.join(artifactDir, "normal-pallet-print.pdf");
  await page.pdf({ path: normalPdf, format: "A4", printBackground: true, margin: { top: "0", right: "0", bottom: "0", left: "0" } });
  recordArtifact("normal-pallet-print.pdf");
  pdfToPng(normalPdf, 2, "print-pallet-back-page.png");

  await page.goto(
    `${baseURL}/cards/${fixture.cards.completed_overflow}/print`,
    { waitUntil: "networkidle" },
  );
  const overflow = await inspectActualPrint(
    page,
    fixture.expected_summary_rows.completed_overflow,
    "overflow",
  );
  assertEqual(overflow.renderedRows, overflow.expectedRows, "overflow source/rendered pallet rows");
  assertEqual(overflow.backHasPalletTables, false, "overflow page-2 pallet tables");
  assert(overflow.headersFit, "Overflow pallet headings overflow horizontally.");
  assert(overflow.overflowPageCount >= 3, "Overflow fixture does not cross a further page boundary.");
  assertEqual(
    overflow.overflow[0].length,
    calibration.overflow.count,
    "overflow boundary row count",
  );
  assert(overflow.overflow[1].length > 0, "Overflow boundary+1 did not create another page.");
  for (let index = 0; index < overflow.overflow.length; index += 1) {
    assertRowsFit(overflow.overflow[index], `overflow page ${index + 3}`);
  }
  const overflowPdf = path.join(artifactDir, "overflow-pallet-print.pdf");
  await page.pdf({ path: overflowPdf, format: "A4", printBackground: true, margin: { top: "0", right: "0", bottom: "0", left: "0" } });
  recordArtifact("overflow-pallet-print.pdf");
  pdfToPng(overflowPdf, 3, "print-pallet-overflow-page-3.png");

  summary.print.normal = normal;
  summary.print.overflow = overflow;
  summary.print.boundaryProof = {
    backBoundaryRowsPerColumn: calibration.back.count,
    backBoundaryPlusOneMovesWholeSummaryToOverflow: true,
    overflowBoundaryRowsPerPage: calibration.overflow.count,
    overflowBoundaryPlusOneCreatesNextPage: true,
  };
}


async function main() {
  let browser;
  const browserErrors = [];
  const consoleErrors = [];
  try {
    browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on("pageerror", (error) => browserErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    for (const viewport of [
      { width: 1536, height: 1024 },
      { width: 1366, height: 768 },
    ]) {
      await page.goto("about:blank");
      resetFixtureDatabase();
      await preflightDatabase(page);
      await verifyTerminalLayout(page, viewport);
      await verifyTerminalBehavior(page, viewport);
    }
    await verifyAdminLayout(page);
    await verifyPrints(page);
    assertEqual(consoleErrors, [], "error-level browser console messages");
    assertEqual(browserErrors, [], "browser page errors");
    summary.consoleErrors = consoleErrors;
    summary.browserErrors = browserErrors;
    summary.status = "passed";
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
    recordArtifact("verification-summary.json");
    console.log("Roll/pallet UI and PDF verification passed.");
    console.log(
      `Measured capacities: back=${summary.print.measuredBackColumnCapacity}; overflow=${summary.print.measuredOverflowPageCapacity}`,
    );
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}


main().catch((error) => {
  summary.status = "failed";
  summary.error = error.stack || String(error);
  try {
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
  } catch {
    // The original validation error is more useful than a secondary report failure.
  }
  console.error(error.stack || error);
  process.exitCode = 1;
});
