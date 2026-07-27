import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";


function requiredEnvironment(name) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Required environment variable ${name} is missing.`);
  return value;
}


function assert(condition, message) {
  if (!condition) throw new Error(message);
}


function assertEqual(actual, expected, label) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `${label}: expected ${JSON.stringify(expected)}, found ${JSON.stringify(actual)}`,
    );
  }
}


function normalized(value) {
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


const baseURL = requiredEnvironment("BASE_URL").replace(/\/+$/, "");
const fixtureInput = requiredEnvironment("FIXTURE_JSON");
const artifactInput = requiredEnvironment("ARTIFACT_DIR");
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = fs.realpathSync(path.resolve(scriptDir, ".."));
const runtimeRoot = path.resolve(repoRoot, ".test-runtime");
const artifactRoot = path.resolve(repoRoot, "artifacts", "ui-checks");
const requestedFixturePath = path.resolve(repoRoot, fixtureInput);
const artifactDir = path.resolve(repoRoot, artifactInput);

assertNoSymlinkComponents(
  repoRoot,
  runtimeRoot,
  ".test-runtime guard root must not be a symlink.",
);

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
assert(fs.existsSync(requestedFixturePath), `Fixture JSON does not exist: ${requestedFixturePath}`);
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

const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const databasePath = fs.realpathSync(path.resolve(repoRoot, fixture.db_path));
assert(
  isStrictChild(fs.realpathSync(runtimeRoot), databasePath),
  "Fixture database must resolve below .test-runtime.",
);

const require = createRequire(import.meta.url);
const { chromium } = require("@playwright/test");
const summaryPath = path.join(artifactDir, "verification-summary.json");
const summary = {
  url: baseURL,
  databaseIdentity: databasePath,
  fixture: path.relative(repoRoot, fixturePath),
  viewports: [],
  assertions: [],
  consoleErrors: [],
  pageErrors: [],
  screenshots: [],
};


function passed(assertion) {
  summary.assertions.push(assertion);
}


function screenshotPath(name) {
  const target = path.join(artifactDir, name);
  summary.screenshots.push(path.relative(repoRoot, target));
  return target;
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
  passed("health database identity matched guarded fixture");
}


function resetFixtureDatabase() {
  const result = spawnSync(
    path.join(repoRoot, ".venv", "bin", "python"),
    [
      path.join(repoRoot, "scripts", "create_rewinding_fixture.py"),
      "--db-path",
      databasePath,
      "--output",
      fixturePath,
    ],
    { cwd: repoRoot, encoding: "utf8" },
  );
  assert(result.status === 0, `Could not reset guarded fixture: ${normalized(result.stderr)}`);
  const refreshed = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  assertEqual(refreshed.cards, fixture.cards, "fixture card IDs after reset");
  assertEqual(refreshed.rolls, fixture.rolls, "fixture roll IDs after reset");
  assertEqual(
    fs.realpathSync(path.resolve(refreshed.db_path)),
    databasePath,
    "fixture database after reset",
  );
}


async function resetForScenario(page) {
  await preflightDatabase(page);
  resetFixtureDatabase();
  await preflightDatabase(page);
}


function databaseSnapshot(cardId) {
  const program = [
    "import json, sqlite3, sys",
    "connection = sqlite3.connect(sys.argv[1])",
    "card_id = int(sys.argv[2])",
    "card = connection.execute('SELECT status, finished_at, first_started_at, rewinding_roll_count FROM cards WHERE id = ?', (card_id,)).fetchone()",
    "timing = connection.execute('SELECT started_at, ended_at, end_reason FROM production_time_segments WHERE card_id = ? ORDER BY id', (card_id,)).fetchall()",
    "rolls = connection.execute('SELECT roll_number, gross_weight, tare_weight, net_weight, pallet_number FROM roll_entries WHERE card_id = ? ORDER BY roll_number', (card_id,)).fetchall()",
    "print(json.dumps({'card': card, 'timing': timing, 'rolls': rolls}))",
  ].join("; ");
  const result = spawnSync(
    path.join(repoRoot, ".venv", "bin", "python"),
    ["-c", program, databasePath, String(cardId)],
    { cwd: repoRoot, encoding: "utf8" },
  );
  assert(result.status === 0, `Could not inspect guarded fixture: ${normalized(result.stderr)}`);
  return JSON.parse(result.stdout);
}


async function navigate(page, cardId) {
  await page.goto(`${baseURL}/terminal/cards/${cardId}`, { waitUntil: "networkidle" });
}


async function submitAndWait(page, action) {
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle" }),
    action(),
  ]);
}


function boxesOverlap(first, second) {
  return !(
    first.x + first.width <= second.x + 0.5
    || second.x + second.width <= first.x + 0.5
    || first.y + first.height <= second.y + 0.5
    || second.y + second.height <= first.y + 0.5
  );
}


async function assertNoOverflow(page, label) {
  const geometry = await page.evaluate(() => {
    const panel = document.querySelector(".input-panel");
    return {
      documentClient: document.documentElement.clientWidth,
      documentScroll: document.documentElement.scrollWidth,
      panelClient: panel?.clientWidth || 0,
      panelScroll: panel?.scrollWidth || 0,
    };
  });
  assert(
    geometry.documentScroll <= geometry.documentClient + 1,
    `${label}: document has horizontal overflow.`,
  );
  assert(
    geometry.panelScroll <= geometry.panelClient + 1,
    `${label}: roll panel has horizontal overflow.`,
  );
}


async function verifyWaitingPane(page, viewport, captureFocused) {
  await navigate(page, fixture.cards.running_mixed);
  const overlay = page.locator("#waiting-overlay");
  assert(await overlay.isHidden(), "Waiting pane auto-opened.");

  const headerActions = page.locator(".terminal-global-nav .terminal-header-action");
  assertEqual(await headerActions.count(), 3, "three terminal header actions");
  const actionBoxes = [];
  for (let index = 0; index < 3; index += 1) {
    const box = await headerActions.nth(index).boundingBox();
    assert(box !== null, `Header action ${index + 1} is not rendered.`);
    actionBoxes.push(box);
  }
  assert(!boxesOverlap(actionBoxes[0], actionBoxes[1]), "First and second header actions overlap.");
  assert(!boxesOverlap(actionBoxes[1], actionBoxes[2]), "Second and third header actions overlap.");
  assertEqual(await page.locator("#waiting-open").getAttribute("data-waiting-count"), "3", "waiting badge count");
  assertEqual(normalized(await page.locator(".waiting-badge").textContent()), "3", "visible waiting badge");

  await page.locator("#waiting-open").click();
  await overlay.waitFor({ state: "visible" });
  const paneBox = await page.locator("[data-waiting-pane]").boundingBox();
  assert(paneBox !== null, "Waiting pane is missing.");
  assert(Math.abs((paneBox.x + paneBox.width / 2) - viewport.width / 2) <= 2, "Waiting pane is not horizontally centered.");
  assert(Math.abs((paneBox.y + paneBox.height / 2) - viewport.height / 2) <= 2, "Waiting pane is not vertically centered.");
  const rowIds = await page.locator("[data-waiting-row]").evaluateAll((rows) =>
    rows.map((row) => Number(new URL(row.href).pathname.split("/").at(-1))),
  );
  assertEqual(rowIds, fixture.waiting_order, "waiting newest-first order");
  if (captureFocused) {
    await page.screenshot({ path: screenshotPath("waiting-pane.png"), fullPage: true });
  }

  await page.keyboard.press("Escape");
  assert(await overlay.isHidden(), "Escape did not close waiting pane.");
  await page.locator("#waiting-open").click();
  await page.locator("#waiting-overlay").click({ position: { x: 4, y: 4 } });
  assert(await overlay.isHidden(), "Backdrop did not close waiting pane.");
  await page.locator("#waiting-open").click();
  await page.locator("#waiting-close").click();
  assert(await overlay.isHidden(), "Close button did not close waiting pane.");
  passed(`waiting pane behavior ${viewport.width}x${viewport.height}`);
}


async function verifyLayout(page, viewport) {
  await navigate(page, fixture.cards.running_mixed);
  const lifecycle = page.locator(".actions [data-lifecycle-slot] button, .actions button[data-lifecycle-slot]");
  assertEqual(await lifecycle.count(), 3, "Start/Pause/Finish control count");
  const lifecycleBoxes = [];
  for (let index = 0; index < 3; index += 1) {
    const box = await lifecycle.nth(index).boundingBox();
    assert(box !== null, `Lifecycle control ${index + 1} is missing.`);
    lifecycleBoxes.push(box);
  }
  for (let index = 1; index < lifecycleBoxes.length; index += 1) {
    assert(Math.abs(lifecycleBoxes[index].width - lifecycleBoxes[0].width) <= 1, "Lifecycle control widths differ.");
    assert(Math.abs(lifecycleBoxes[index].height - lifecycleBoxes[0].height) <= 1, "Lifecycle control heights differ.");
    assert(!boxesOverlap(lifecycleBoxes[index - 1], lifecycleBoxes[index]), "Lifecycle controls overlap.");
  }
  const lifecycleFit = await lifecycle.evaluateAll((buttons) => buttons.map((button) => {
    const buttonBox = button.getBoundingClientRect();
    const visibleChildren = Array.from(button.children).filter((child) => {
      const box = child.getBoundingClientRect();
      return box.width > 0 && box.height > 0;
    });
    return {
      contentFits: button.scrollWidth <= button.clientWidth + 1,
      childrenFit: visibleChildren.every((child) => {
        const box = child.getBoundingClientRect();
        return box.left >= buttonBox.left + 4 && box.right <= buttonBox.right - 4;
      }),
    };
  }));
  assert(
    lifecycleFit.every(({ contentFits, childrenFit }) => contentFits && childrenFit),
    "Lifecycle control content is clipped or crowded.",
  );

  const secondary = page.locator("[data-roll-secondary-actions] button");
  assertEqual(await secondary.count(), 2, "roll secondary action count");
  assert((await secondary.allTextContents()).some((text) => normalized(text) === "Смяна на ролка"), "Roll-change action is missing.");

  const headingCells = page.locator(".roll-head > div");
  const widths = [];
  for (let index = 0; index < 5; index += 1) {
    const box = await headingCells.nth(index).boundingBox();
    assert(box !== null, `Roll heading ${index + 1} is missing.`);
    widths.push(box.width);
  }
  assert(Math.max(...widths) - Math.min(...widths) <= 1, "First five roll-table columns are not equal.");
  const firstRow = page.locator(".roll-row[data-roll-id]").first();
  assertEqual(normalized(await firstRow.locator("[data-roll-display='gross']").textContent()), "20.0", "one-decimal gross");
  assertEqual(normalized(await firstRow.locator("[data-roll-display='tare']").textContent()), "1.0", "one-decimal tare");
  assertEqual(normalized(await firstRow.locator("[data-roll-display='net']").textContent()), "19.0", "one-decimal net");

  const addButton = page.locator(".roll-add-button");
  assert(normalized(await addButton.textContent()).includes("Добави"), "Add-roll copy is missing.");
  const addAlignment = await addButton.evaluate((button) => {
    const buttonBox = button.getBoundingClientRect();
    return Array.from(button.children).every((child) => {
      const box = child.getBoundingClientRect();
      return Math.abs((box.y + box.height / 2) - (buttonBox.y + buttonBox.height / 2)) <= 2;
    });
  });
  assert(addAlignment, "Add-roll icon and text are not vertically aligned.");

  const labels = page.locator(".roll-entry .field-label");
  const labelY = [];
  for (let index = 0; index < await labels.count(); index += 1) {
    const box = await labels.nth(index).boundingBox();
    if (box) labelY.push(box.y);
  }
  assert(Math.max(...labelY) - Math.min(...labelY) <= 2, "Roll-entry field labels are misaligned.");
  await assertNoOverflow(page, `${viewport.width}x${viewport.height}`);
  await page.screenshot({
    path: screenshotPath(`rewinding-${viewport.width}x${viewport.height}-full.png`),
    fullPage: true,
  });
  summary.viewports.push({ ...viewport, layout: "passed", overflow: "none" });
  passed(`terminal layout ${viewport.width}x${viewport.height}`);
}


async function verifyMarkerInteractions(page) {
  await resetForScenario(page);
  await navigate(page, fixture.cards.paused_marked);
  const open = page.locator("[data-rewinding-open]");
  await open.click();
  const overlay = page.locator("[data-rewinding-overlay]");
  await overlay.waitFor({ state: "visible" });
  const input = page.locator("[data-rewinding-input]");
  assertEqual(await input.inputValue(), "4", "saved rewinding count in dialog");
  await input.fill("9");
  await submitAndWait(page, () => page.locator(".rewinding-save").click());
  assert(normalized(await page.locator("[data-rewinding-open]").textContent()).includes("9"), "Saved marker is not rendered.");

  await page.locator("[data-rewinding-open]").click();
  await page.locator("[data-rewinding-input]").fill("0");
  await submitAndWait(page, () => page.locator(".rewinding-save").click());
  assertEqual(normalized(await page.locator("[data-rewinding-open]").textContent()), "Пренавиване", "cleared marker label");

  await page.locator("[data-rewinding-open]").click();
  await page.locator("[data-rewinding-input]").fill("12x");
  await submitAndWait(page, () => page.locator(".rewinding-form").evaluate((form) => form.submit()));
  assert(await page.locator("[data-rewinding-overlay]").isVisible(), "Invalid marker did not reopen dialog.");
  assert(normalized(await page.locator("[data-feedback-target='rewinding']").textContent()).includes("цяло число"), "Invalid marker feedback is missing.");
  await page.screenshot({ path: screenshotPath("marker-dialog.png"), fullPage: true });
  await page.locator("[data-rewinding-cancel]").click();
  assert(await page.locator("[data-rewinding-overlay]").isHidden(), "Marker cancel did not close dialog.");

  await page.locator("[data-rewinding-open]").click();
  await page.locator("[data-rewinding-input]").fill("8");
  await page.locator("[data-rewinding-cancel]").click();
  await page.locator("[data-rewinding-open]").click();
  assertEqual(await page.locator("[data-rewinding-input]").inputValue(), "", "Cancel did not restore saved marker.");
  await page.locator("[data-rewinding-cancel]").click();

  const staleVersion = await page.locator(".rewinding-form input[name='loaded_version']").inputValue();
  const concurrent = await page.request.post(
    `${baseURL}/terminal/cards/${fixture.cards.paused_marked}/rewinding-count`,
    { form: { loaded_version: staleVersion, rewinding_roll_count: "3" }, maxRedirects: 0 },
  );
  assert([303, 200].includes(concurrent.status()), `Concurrent marker write failed with ${concurrent.status()}.`);
  await page.locator("[data-rewinding-open]").click();
  await page.locator("[data-rewinding-input]").fill("8");
  await submitAndWait(page, () => page.locator(".rewinding-save").click());
  assert(await page.locator("#terminal-refresh-alert").isVisible(), "Stale marker write did not require reload.");
  assert(await page.locator("[data-rewinding-overlay]").isHidden(), "Stale marker feedback left dialog open.");
  passed("marker save, clear, invalid, cancel, and stale feedback");
}


async function finishToWaiting(page, cardId, expectedMissingPallets) {
  await navigate(page, cardId);
  await page.locator("form[data-lifecycle-slot='finish'] button").click();
  const modal = page.locator("[data-finish-confirm-modal]");
  await modal.waitFor({ state: "visible" });
  const message = normalized(await modal.locator("#finish-confirm-body").textContent());
  assert(message.includes(`${expectedMissingPallets} ролка`) || message.includes(`${expectedMissingPallets} ролки`), "Mixed-pallet warning is missing.");
  await submitAndWait(page, () => modal.locator("[data-finish-confirm-submit]").click());
  assertEqual(databaseSnapshot(cardId).card[0], "awaiting_rewinding", "active card status after extrusion finish");
  assertEqual(await page.locator(".actions form[data-lifecycle-slot='finish']").count(), 1, "waiting lifecycle action count");
}


async function verifyActiveFinishAndFreedMachine(page, viewport) {
  await resetForScenario(page);
  const activeCard = viewport.width === 1920
    ? fixture.cards.running_mixed
    : fixture.cards.paused_marked;
  const followUpCard = viewport.width === 1920
    ? fixture.cards.follow_up
    : fixture.cards.paused_follow_up;
  await finishToWaiting(page, activeCard, 1);
  await navigate(page, followUpCard);
  await submitAndWait(page, () => page.locator("form[data-lifecycle-slot='start'] button").click());
  assertEqual(databaseSnapshot(followUpCard).card[0], "running", "follow-up status after start");
  passed(`freed machine starts follow-up queue card at ${viewport.width}x${viewport.height}`);
  passed(`${viewport.width === 1920 ? "running" : "paused"} marked card finishes into waiting`);
}


async function verifyWaitingCompletion(page) {
  await resetForScenario(page);
  const cardId = fixture.cards.waiting_zero;
  await navigate(page, cardId);
  await page.screenshot({ path: screenshotPath("waiting-detail.png"), fullPage: true });
  const before = databaseSnapshot(cardId);
  await page.locator("form[data-lifecycle-slot='finish'] button").click();
  await submitAndWait(page, () => page.locator("[data-finish-confirm-submit]").click());
  assertEqual(databaseSnapshot(cardId).card[0], "awaiting_rewinding", "zero-returned-roll finish remains waiting");
  assert(normalized(await page.locator("[data-feedback-target='topbar']").textContent()).includes("ролка"), "Zero-returned-roll blocker is not visible.");

  const initialRows = await page.locator(".roll-row[data-roll-id]").count();
  await page.locator(".add-roll-form input[name='gross_weight']").fill("40");
  await submitAndWait(page, () => page.locator(".roll-add-button").click());
  assertEqual(await page.locator(".roll-row[data-roll-id]").count(), initialRows + 1, "first returned roll cardinality");
  await page.locator("[data-current-pallet-input]").fill("18");
  await submitAndWait(page, () => page.locator("[data-current-pallet-input]").press("Enter"));
  await page.locator(".add-roll-form input[name='gross_weight']").fill("41");
  await submitAndWait(page, () => page.locator(".roll-add-button").click());
  assertEqual(await page.locator(".roll-row[data-roll-id]").count(), initialRows + 2, "second returned roll cardinality");
  assertEqual(normalized(await page.locator(".roll-row[data-roll-id]").last().locator("[data-roll-display='pallet']").textContent()), "18", "optional returned-roll pallet");
  assert(normalized(await page.locator("[data-rewinding-open]").textContent()).includes("5"), "Marker count changed with returned-roll cardinality.");

  const beforeFinal = databaseSnapshot(cardId);
  await page.locator("form[data-lifecycle-slot='finish'] button").click();
  await submitAndWait(page, () => page.locator("[data-finish-confirm-submit]").click());
  const afterFinal = databaseSnapshot(cardId);
  assertEqual(afterFinal.card[0], "completed", "waiting card final status");
  assertEqual(afterFinal.card[1], beforeFinal.card[1], "waiting final finished_at preservation");
  assertEqual(afterFinal.card[2], beforeFinal.card[2], "waiting final first_started_at preservation");
  assertEqual(afterFinal.timing, beforeFinal.timing, "waiting final timing preservation");

  await page.locator("#history-open").click();
  const producedRow = page.locator(`.history-row[href='/terminal/cards/${cardId}']`);
  assert(await producedRow.isVisible(), "Final card did not move to Produced Orders.");
  await producedRow.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshotPath("final-produced-row.png"), fullPage: true });
  passed("waiting blocker, returned rolls, final timing preservation, and Produced move");
  assert(before.card[1] === beforeFinal.card[1], "Adding returned rolls changed finished_at.");
}


async function verifyRollEditingAndDirtyNavigation(page) {
  await resetForScenario(page);
  const cardId = fixture.cards.completed_editable;
  await navigate(page, cardId);
  const firstRow = page.locator(".roll-row[data-roll-id]").first();
  const edit = firstRow.locator("[data-roll-edit-open]");
  assert(await edit.isVisible(), "Pencil row editor is missing.");
  await edit.click();
  assertEqual(await firstRow.getAttribute("data-roll-edit-open"), "true", "row edit opened");
  assertEqual(
    await firstRow.locator("input[name='tare_weight']").inputValue(),
    "1.25",
    "exact two-decimal tare loaded for unchanged save",
  );
  await page.screenshot({ path: screenshotPath("row-edit.png"), fullPage: true });
  await submitAndWait(page, () => page.locator("[data-roll-actions-for]:visible [data-roll-row-save]").click());
  assertEqual(
    normalized(await firstRow.locator("[data-roll-display='tare']").textContent()),
    "1.3",
    "one-decimal tare after unchanged exact save",
  );
  assertEqual(databaseSnapshot(cardId).rolls[0][2], 1.25, "exact tare after unchanged save");
  await page.reload({ waitUntil: "networkidle" });
  assertEqual(
    normalized(await firstRow.locator("[data-roll-display='tare']").textContent()),
    "1.3",
    "one-decimal tare after reload",
  );
  await edit.click();
  assertEqual(
    await firstRow.locator("input[name='tare_weight']").inputValue(),
    "1.25",
    "exact two-decimal tare after reload",
  );
  await page.locator("[data-roll-actions-for]:visible [data-roll-row-cancel]").click();

  await edit.click();
  const grossInput = firstRow.locator("input[name='gross_weight']");
  await grossInput.fill("33");
  for (const selector of ["#queue-open", "#waiting-open", "#history-open"]) {
    const urlBefore = page.url();
    await page.locator(selector).click({ force: true });
    assertEqual(page.url(), urlBefore, `${selector} dirty navigation URL`);
  }
  assert(!await page.locator("#queue-overlay").evaluate((element) => element.classList.contains("open")), "Dirty edit opened queue.");
  assert(await page.locator("#waiting-overlay").isHidden(), "Dirty edit opened waiting pane.");
  assert(!await page.locator("#history-overlay").evaluate((element) => element.classList.contains("open")), "Dirty edit opened Produced pane.");
  await submitAndWait(page, () => page.locator("[data-roll-actions-for]:visible [data-roll-row-save]").click());
  assertEqual(normalized(await page.locator(".roll-row[data-roll-id]").first().locator("[data-roll-display='gross']").textContent()), "33.0", "saved row correction");

  const beforeDelete = databaseSnapshot(cardId);
  const rowsBeforeDelete = await page.locator(".roll-row[data-roll-id]").count();
  const deletedRollNumber = beforeDelete.rolls.at(-1)[0];
  await page.locator(".roll-row[data-roll-id]").last().locator("[data-roll-edit-open]").click();
  await page.locator("[data-roll-actions-for]:visible [data-roll-row-delete]").click();
  const deleteModal = page.locator("[data-roll-delete-modal-for]:visible");
  assert(normalized(await deleteModal.textContent()).includes("Потвърдете номера"), "Delete confirmation is missing.");
  await deleteModal.locator("input[name='confirm_roll_number']").fill(String(deletedRollNumber));
  await submitAndWait(page, () => deleteModal.locator("button[type='submit']").click());
  const afterDelete = databaseSnapshot(cardId);
  assertEqual(afterDelete.rolls, beforeDelete.rolls.slice(0, -1), "persisted roll deletion");
  assertEqual(
    await page.locator(".roll-row[data-roll-id]").count(),
    rowsBeforeDelete - 1,
    "rendered roll count after delete",
  );
  await page.reload({ waitUntil: "networkidle" });
  assertEqual(databaseSnapshot(cardId).rolls, afterDelete.rolls, "roll deletion after reload");
  assertEqual(
    await page.locator(".roll-row[data-roll-id]").count(),
    rowsBeforeDelete - 1,
    "rendered roll count after delete reload",
  );
  assertEqual(afterDelete.rolls[0][2], 1.25, "exact tare after delete reload");
  passed("pencil editor, Cancel, unchanged precision Save, persisted Delete, and dirty pane guards");

  await navigate(page, fixture.cards.running_mixed);
  const snapshot = databaseSnapshot(fixture.cards.running_mixed);
  const url = page.url();
  await page.locator("[data-roll-change]").click();
  assertEqual(page.url(), url, "roll-change URL no-op");
  assertEqual(databaseSnapshot(fixture.cards.running_mixed), snapshot, "roll-change database no-op");
  passed("roll-change action has no effect");
}


async function verifyMutatingScenarios(page, viewport) {
  await verifyMarkerInteractions(page);
  await verifyWaitingCompletion(page);
  await verifyRollEditingAndDirtyNavigation(page);
  await verifyActiveFinishAndFreedMachine(page, viewport);
}


async function main() {
  let browser;
  try {
    browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on("pageerror", (error) => summary.pageErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") summary.consoleErrors.push(message.text());
    });

    await preflightDatabase(page);
    for (const viewport of [
      { width: 1920, height: 768 },
      { width: 1366, height: 768 },
    ]) {
      await page.setViewportSize(viewport);
      await resetForScenario(page);
      await verifyWaitingPane(page, viewport, viewport.width === 1920);
      await verifyLayout(page, viewport);
      await preflightDatabase(page);
      await verifyMutatingScenarios(page, viewport);
    }

    assertEqual(summary.consoleErrors, [], "error-level browser console messages");
    assertEqual(summary.pageErrors, [], "browser page errors");
    summary.status = "passed";
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
    console.log("Rewinding return workflow verification passed.");
    console.log(JSON.stringify(summary, null, 2));
  } finally {
    if (browser) await browser.close();
  }
}


main().catch((error) => {
  summary.status = "failed";
  summary.error = error.stack || String(error);
  try {
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
  } catch {
    // Preserve the original validation failure.
  }
  console.error(error.stack || error);
  process.exitCode = 1;
});
