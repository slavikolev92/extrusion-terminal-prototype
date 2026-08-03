# Roll-Change Indicator Thresholds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the resolved running roll-change countdown turn yellow at exactly 15 minutes remaining and red at exactly 5 minutes remaining on both existing Terminal countdown surfaces.

**Architecture:** Keep the threshold policy in the pure browser-side `countdownView(schedule, status, nowMs)` model, expressed as named millisecond constants. The existing controller continues applying the returned tone to the selected-card countdown and each configured machine-navigation countdown; existing HTML, CSS, browser storage, acknowledgement, and lifecycle behavior remain unchanged. Add exact pure-state boundary tests, guarded live-browser tone checks, and current documentation.

**Tech Stack:** JavaScript ES modules, Node's built-in test runner, server-rendered Jinja in FastAPI, pytest, repository-local Playwright 1.61.0, browser `localStorage`, SQLite temporary fixtures.

**Status:** Completed and merged into local `main` through `f1d276f` on
2026-08-01. Fresh source verification on 2026-08-03 passed 975 Python tests and
20 JavaScript tests. Production deployment remains separate and unperformed.

## Global Constraints

- Read and follow `AGENTS.md`, `README.md`, and `docs/superpowers/specs/2026-08-01-roll-change-indicator-thresholds-design.md` before implementation.
- For a resolved running countdown: greater than `15:00` is `normal`; less than or equal to `15:00` and greater than `05:00` is yellow `warning`; less than or equal to `05:00` through overdue is red `urgent`.
- Use the unrounded internal millisecond duration for tone boundaries; retain `Math.ceil` for the visible `HH:MM` value.
- Preserve paused yellow, positive resumed-unresolved yellow `resync`, and resumed-unresolved due red `urgent` precedence.
- Preserve the existing `normal`, `warning`, `urgent`, `paused`, and `resync` class names and colors.
- Do not move, duplicate, redesign, or otherwise change the quick acknowledgement/reset button.
- Do not change template layout, markup, icons, labels, focus order, schedule creation/editing, acknowledgement cadence, storage schema/key, lifecycle cleanup, backend routes, or production rules.
- Do not add configurable thresholds, dependencies, database fields, migrations, production-data writes, reporting, notifications, or machine integration.
- Use `.venv`, the repository-local Node/Playwright installation, temporary databases under `.test-runtime/`, and evidence under `artifacts/ui-checks/`.
- Never open or mutate `data/extrusion_terminal.sqlite3` during tests or browser verification.
- Preserve the pre-existing worktree changes in `design-qa.md`, `v2-files/PLAN.md`, `docs/implementation-notes/excel-csv-import-contract-debug-handoff.md`, and `v2-files/MIGRATION-REPORT-2026-07-28.md`.
- Do not stage or commit unless the user explicitly requests it.

## File Structure

- `app/static/js/roll_change_countdown_core.mjs`: owns the pure remaining-time and tone policy; add the two internal thresholds and change only resolved-running classification.
- `tests/js/roll_change_countdown_core.test.mjs`: owns exact millisecond boundary regression tests.
- `scripts/verify_roll_change_countdown_ui.mjs`: owns guarded real-browser proof that both existing countdown surfaces receive normal, yellow, red, due, and paused tones at both supported viewports.
- `tests/test_roll_change_countdown_ui_script_safety.py`: owns the static contract that the guarded verifier retains explicit threshold-tone coverage without installing browser tooling.
- `README.md`: authoritative project behavior; add the accepted threshold contract.
- `docs/implementation-notes/roll-change-countdown.md`: durable implementation and operational explanation.
- `v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md`: current detailed Task 10 behavior and verification contract; remove superseded 5-minute-warning/1-minute-urgent wording.
- `app/static/js/roll_change_countdown.mjs` and `app/templates/terminal.html`: verify unchanged; they already propagate and style the model's tone on both surfaces.

---

### Task 1: Exact Pure-Model Thresholds

**Files:**
- Modify: `tests/js/roll_change_countdown_core.test.mjs:108-119`
- Modify: `app/static/js/roll_change_countdown_core.mjs:4-6,87-107`
- Verify unchanged: `app/static/js/roll_change_countdown.mjs:216-276`

**Interfaces:**
- Consumes: `countdownView(schedule, status, nowMs)`, where `schedule` is an existing validated version-1 countdown record, `status` is `"running"` or `"paused"`, `nowMs` is an integer timestamp in milliseconds, and `MINUTE_MS` remains `60_000`.
- Produces: an unchanged countdown view object `{ remainingMs, display, tone, due, paused, unresolved, nextExpectedLabel }` whose `tone` uses the approved 15-minute/5-minute resolved-running boundaries.

- [ ] **Step 1: Replace the old boundary test with exact approved cases**

In `tests/js/roll_change_countdown_core.test.mjs`, replace the existing test named `warning boundaries and rounded display use exact milliseconds` with:

```javascript
test("running indicator thresholds and rounded display use exact milliseconds", () => {
  const schedule = runningSchedule();
  for (const [remainingMs, tone, display] of [
    [15 * minute + 1, "normal", "00:16"],
    [15 * minute, "warning", "00:15"],
    [5 * minute + 1, "warning", "00:06"],
    [5 * minute, "urgent", "00:05"],
    [1, "urgent", "00:01"],
  ]) {
    const view = countdownView(
      schedule,
      "running",
      schedule.nextExpectedAtMs - remainingMs,
    );
    assert.deepEqual(
      { tone: view.tone, display: view.display, due: view.due },
      { tone, display, due: false },
    );
  }

  for (const nowMs of [schedule.nextExpectedAtMs, schedule.nextExpectedAtMs + minute]) {
    const view = countdownView(schedule, "running", nowMs);
    assert.deepEqual(
      { tone: view.tone, display: view.display, due: view.due },
      { tone: "urgent", display: "00:00", due: true },
    );
  }
});
```

Do not weaken or remove the adjacent pause/resume tests. They prove that paused and `resync` branches still take precedence over resolved-running thresholds.

- [ ] **Step 2: Run the Node test and verify intentional RED**

Run:

```bash
node --test tests/js/roll_change_countdown_core.test.mjs
```

Expected: the replacement test fails because the current implementation keeps values above 5 minutes normal, keeps exactly 5 minutes yellow, and does not turn red until 1 minute. All unrelated countdown tests should still pass.

- [ ] **Step 3: Add named threshold constants and change only tone classification**

Immediately after `MINUTE_MS` in `app/static/js/roll_change_countdown_core.mjs`, add:

```javascript
const WARNING_THRESHOLD_MS = 15 * MINUTE_MS;
const URGENT_THRESHOLD_MS = 5 * MINUTE_MS;
```

Then replace only the final resolved-running comparisons inside `countdownView()`:

```javascript
  let tone = "normal";
  if (status === "paused") tone = "paused";
  else if (unresolved && !due) tone = "resync";
  else if (remainingMs <= URGENT_THRESHOLD_MS) tone = "urgent";
  else if (remainingMs <= WARNING_THRESHOLD_MS) tone = "warning";
```

Keep the urgent comparison before the warning comparison. Do not export the constants, change `formatRemaining()`, or alter the countdown view's return shape.

- [ ] **Step 4: Run focused GREEN verification**

Run:

```bash
node --test tests/js/roll_change_countdown_core.test.mjs
node --check app/static/js/roll_change_countdown_core.mjs
node --check app/static/js/roll_change_countdown.mjs
```

Expected: all countdown Node tests pass and both syntax checks exit `0`.

- [ ] **Step 5: Review the Task 1 diff**

Run:

```bash
git diff -- \
  app/static/js/roll_change_countdown_core.mjs \
  tests/js/roll_change_countdown_core.test.mjs \
  app/static/js/roll_change_countdown.mjs
```

Confirm the controller has no diff, the runtime change is only two named constants plus two comparisons, the test uses unrounded milliseconds, and reset-button, persistence, acknowledgement, pause/resume, and lifecycle logic are untouched. Do not stage or commit.

---

### Task 2: Guarded Browser Contract For Both Countdown Surfaces

**Files:**
- Modify: `tests/test_roll_change_countdown_ui_script_safety.py:612-635`
- Modify: `scripts/verify_roll_change_countdown_ui.mjs:330-348,477-496,898-915,2319-2341`
- Verify unchanged: `app/templates/terminal.html:379-400,761-781,3921-3935,4073-4089`

**Interfaces:**
- Consumes: valid version-1 browser-local schedule records, `navigate(page, cardId)`, `[data-roll-change-machine-timer]`, `[data-roll-change-open]`, and the tone classes produced by Task 1.
- Produces: `assertThresholdTones(page, viewport): Promise<void>`, which proves one and only one expected tone class on the machine countdown and selected-card countdown for stable normal, warning, urgent, and paused fixtures.

- [ ] **Step 1: Add a failing verifier-source safety contract**

Append this focused test near the other verifier coverage tests in `tests/test_roll_change_countdown_ui_script_safety.py`:

```python
def test_roll_change_verifier_covers_approved_indicator_thresholds_on_both_surfaces():
    source = VERIFIER_SCRIPT.read_text(encoding="utf-8")

    assert "async function assertThresholdTones(page, viewport)" in source
    assert 'tone: "normal"' in source
    assert 'tone: "warning"' in source
    assert 'tone: "urgent"' in source
    assert 'tone: "paused"' in source
    assert 'host.querySelector("[data-roll-change-machine-timer]")' in source
    assert 'page.locator("[data-roll-change-open]")' in source
    assert "await assertThresholdTones(page, viewport);" in source
```

This test protects the guarded workflow contract; it does not replace live Playwright execution.

- [ ] **Step 2: Run the safety test and verify intentional RED**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  tests/test_roll_change_countdown_ui_script_safety.py::test_roll_change_verifier_covers_approved_indicator_thresholds_on_both_surfaces \
  -q
```

Expected: FAIL because `assertThresholdTones()` and its invocation do not yet exist.

- [ ] **Step 3: Seed stable normal, warning, urgent, and paused schedules**

Replace the `records` array in `seedSchedules()` with values safely away from the one-second tick boundaries:

```javascript
  const records = [
    schedule({ machineId: 1, cardId: fixture.cards.machine_1_running, previousChangeAtMs: now - 40 * 60_000, intervalMinutes: 60, nextExpectedAtMs: now + 20 * 60_000, status: "running" }),
    schedule({ machineId: 2, cardId: fixture.cards.machine_2_running, previousChangeAtMs: now - 50 * 60_000, intervalMinutes: 60, nextExpectedAtMs: now + 10 * 60_000, status: "running" }),
    schedule({ machineId: 3, cardId: fixture.cards.machine_3_running, previousChangeAtMs: now - 56 * 60_000, intervalMinutes: 60, nextExpectedAtMs: now + 4 * 60_000, status: "running" }),
    schedule({ machineId: 4, cardId: fixture.cards.machine_4_paused, previousChangeAtMs: now - 60 * 60_000, intervalMinutes: 60, nextExpectedAtMs: now - 1_000, status: "paused", frozenRemainingMs: 0, pauseNeedsResolution: true }),
  ];
```

Also change the schedule created inside `assertLayoutAndInactiveState()` from `nextExpectedAtMs: now + 10 * 60_000` to `nextExpectedAtMs: now + 20 * 60_000`. This makes its final screenshot retain the intended four-machine mixture: normal, warning, urgent, and paused.

- [ ] **Step 4: Add the cross-surface tone assertion helper**

Add this function after `seedSchedules()`:

```javascript
async function assertThresholdTones(page, viewport) {
  const toneClasses = ["normal", "warning", "urgent", "paused", "resync"];
  const cases = [
    { machineId: 1, cardId: fixture.cards.machine_1_running, tone: "normal" },
    { machineId: 2, cardId: fixture.cards.machine_2_running, tone: "warning" },
    { machineId: 3, cardId: fixture.cards.machine_3_running, tone: "urgent" },
    { machineId: 4, cardId: fixture.cards.machine_4_paused, tone: "paused" },
  ];

  for (const { machineId, cardId, tone } of cases) {
    await navigate(page, cardId);
    const machineTones = await page
      .locator(`[data-roll-change-machine][data-machine-id="${machineId}"]`)
      .evaluate((host, classes) => {
        const timer = host.querySelector("[data-roll-change-machine-timer]");
        return classes.filter((name) => timer && timer.classList.contains(name));
      }, toneClasses);
    const selectedTones = await page
      .locator("[data-roll-change-open]")
      .evaluate((element, classes) => classes.filter((name) => element.classList.contains(name)), toneClasses);
    assertEqual(machineTones, [tone], `machine ${machineId} threshold tone`);
    assertEqual(selectedTones, [tone], `selected machine ${machineId} threshold tone`);
  }

  await navigate(page, fixture.cards.machine_1_running);
  passed(`${viewport.width}x${viewport.height}: normal, warning, urgent, and paused tones on both countdown surfaces`);
}
```

Call it immediately after `await seedSchedules(page);` in `runViewport()`:

```javascript
    await seedSchedules(page);
    await assertThresholdTones(page, viewport);
```

The verifier already loops `runViewport()` over `1920x768` and `1366x768`, so do not introduce a second viewport loop.

- [ ] **Step 5: Strengthen the existing due-state assertion on the selected control**

In `assertStorageEventsDueAndCorrection()`, immediately after the existing machine-timer urgent assertion, add:

```javascript
  assert(
    await page.locator("[data-roll-change-open]").evaluate((element) => element.classList.contains("urgent")),
    "Due selected countdown is not red/urgent.",
  );
```

Retain the existing `00:00` hold, no-auto-advance, storage, cross-tab, and SQLite-preservation checks.

- [ ] **Step 6: Run focused verifier checks**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  tests/test_roll_change_countdown_ui_script_safety.py::test_roll_change_verifier_covers_approved_indicator_thresholds_on_both_surfaces \
  tests/test_roll_change_countdown_ui_script_safety.py::test_roll_change_verifier_uses_directional_spacing_and_accepted_geometry_checks \
  -q
node --check scripts/verify_roll_change_countdown_ui.mjs
node --test tests/js/roll_change_countdown_core.test.mjs
```

Expected: both Python tests and all Node tests pass; JavaScript syntax checking exits `0`.

- [ ] **Step 7: Run the guarded live verifier at both supported viewports**

Create only a temporary fixture:

```bash
source .venv/bin/activate
python scripts/create_roll_change_countdown_fixture.py \
  --db-path .test-runtime/roll-change-indicator-thresholds/fixture.sqlite3 \
  --output .test-runtime/roll-change-indicator-thresholds/fixture.json
```

In one terminal, start the temporary app on the established verification port:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/roll-change-indicator-thresholds/fixture.sqlite3 \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8012
```

In a second terminal, run:

```bash
BASE_URL=http://127.0.0.1:8012 \
FIXTURE_JSON=.test-runtime/roll-change-indicator-thresholds/fixture.json \
ARTIFACT_DIR=artifacts/ui-checks/roll-change-indicator-thresholds \
node scripts/verify_roll_change_countdown_ui.mjs
```

Expected: the summary reports both `1920x768` and `1366x768` passed, includes the new cross-surface tone assertion message for each viewport, reports zero console/page errors, and preserves the timer-only SQLite snapshot. Stop the temporary server cleanly after the verifier exits.

- [ ] **Step 8: Inspect the browser evidence**

Open and inspect:

```text
artifacts/ui-checks/roll-change-indicator-thresholds/roll-change-1920x768.png
artifacts/ui-checks/roll-change-indicator-thresholds/roll-change-1366x768.png
artifacts/ui-checks/roll-change-indicator-thresholds/verification-summary.json
```

Confirm that machine 1 is neutral above 15 minutes, machine 2 is yellow between 15 and 5 minutes, machine 3 is red below 5 minutes, machine 4 remains yellow while paused, neither countdown surface clips or moves machine-card geometry, and there are no reset-button or layout changes.

- [ ] **Step 9: Review the Task 2 diff**

Run:

```bash
git diff -- \
  scripts/verify_roll_change_countdown_ui.mjs \
  tests/test_roll_change_countdown_ui_script_safety.py \
  app/templates/terminal.html
```

Confirm `app/templates/terminal.html` has no diff, the verifier uses stable values away from exact tick boundaries, both surfaces are checked, the established viewport loop and safety guards remain intact, and no runtime or production database is referenced. Do not stage or commit.

---

### Task 3: Authoritative Threshold Documentation

**Files:**
- Modify: `README.md:184-200`
- Modify: `docs/implementation-notes/roll-change-countdown.md:37-56`
- Modify: `v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md:156-186,447-475`
- Reference: `docs/superpowers/specs/2026-08-01-roll-change-indicator-thresholds-design.md`

**Interfaces:**
- Consumes: the approved exact boundary contract and unchanged pause/resume precedence.
- Produces: current documentation with one consistent normal/yellow/red policy and an explicit supersession of the old 5-minute-warning/1-minute-urgent wording.

- [ ] **Step 1: Update the authoritative README behavior**

After the acknowledgement/catch-up bullet in `README.md`, add:

```markdown
- For a resolved running countdown, more than `15:00` remaining uses the normal
  treatment, from exactly `15:00` down to more than `05:00` uses yellow, and
  exactly `05:00` through the due/overdue `00:00` hold uses red. Tone boundaries
  use the unrounded internal duration, while the visible positive minute remains
  rounded up.
```

Leave the following browser ownership, reminder boundary, and pause/resume bullets unchanged.

- [ ] **Step 2: Add the durable threshold table to the implementation note**

In `docs/implementation-notes/roll-change-countdown.md`, insert this subsection before `## Pause And Resume States`:

```markdown
## Running Indicator Thresholds

Resolved running schedules use the unrounded internal remaining duration:

| Remaining duration | Tone |
| --- | --- |
| Greater than `15:00` | Normal |
| At most `15:00` and greater than `05:00` | Yellow warning |
| At most `05:00`, due, or overdue | Red urgent |

Positive partial minutes continue to round up for the visible `HH:MM` value, so
the visible transitions occur at yellow `00:15` and red `00:05`. Paused and
unresolved-resume precedence remains defined below.
```

Do not rewrite the storage, acknowledgement, recovery, or verification contracts.

- [ ] **Step 3: Replace superseded Task 10 state and test wording**

In `v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md`, replace the three active-state descriptions with:

```markdown
### Active, normal

- The machine card and selected-card control show the remaining countdown.
- The selected-card control also exposes the next expected wall-clock time.
- More than fifteen minutes remaining uses the normal countdown treatment.

### Approaching

- From exactly `15:00` remaining while the unrounded duration is greater than
  `05:00`, the countdown uses the yellow warning treatment.
- Color is accompanied by the numeric time; warning meaning is never conveyed
  by color alone.

### Urgent

- From exactly `05:00` remaining through the due instant and overdue hold, the
  countdown uses the red urgent treatment.
- At the due instant, the display becomes `00:00`.
```

Replace the calculation-test bullet:

```markdown
- normal above fifteen minutes, yellow at fifteen minutes, red at five minutes,
  exact millisecond boundaries, visible rounding, and due/overdue behavior;
```

Leave all pause, resume, acknowledgement, clearing, storage, accessibility, and out-of-scope statements intact.

- [ ] **Step 4: Scan current documentation for contradictory old thresholds**

Run:

```bash
rg -n \
  'More than five minutes|From exactly `05:00` remaining through `01:01`|From exactly `01:00`|five-minute warning|one-minute urgent' \
  README.md \
  docs/implementation-notes/roll-change-countdown.md \
  v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md
```

Expected: no matches. Do not mass-edit historical implementation plans; the new dated design and plan supersede their historical threshold text.

- [ ] **Step 5: Review the documentation diff**

Run:

```bash
git diff -- \
  README.md \
  docs/implementation-notes/roll-change-countdown.md \
  v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md
```

Confirm every current document agrees on inclusive 15-minute yellow and inclusive 5-minute red boundaries, explicitly retains display rounding and pause/resume overrides, and contains no reset-button relocation. Do not stage or commit.

---

### Task 4: Final Verification, Scope Review, And Migration Assessment

**Files:**
- Verify: every file listed in Tasks 1-3
- Verify unchanged: `app/static/js/roll_change_countdown.mjs`, `app/templates/terminal.html`, `app/main.py`, `app/db.py`, `app/schema.py`, `app/migrations.py`
- Preserve: all pre-existing unrelated worktree changes listed in Global Constraints

**Interfaces:**
- Consumes: the finished threshold logic, tests, guarded browser evidence, and documentation.
- Produces: fresh syntax/test/browser evidence, an explicit no-migration conclusion, and a reviewed unstaged implementation ready for user review.

- [ ] **Step 1: Run syntax, focused Node, and focused Python verification**

Run:

```bash
source .venv/bin/activate
python -m compileall -q app tests scripts
node --check app/static/js/roll_change_countdown_core.mjs
node --check app/static/js/roll_change_countdown.mjs
node --check scripts/verify_roll_change_countdown_ui.mjs
node --test tests/js/roll_change_countdown_core.test.mjs
python -m pytest \
  tests/test_roll_change_countdown_ui_script_safety.py \
  tests/test_terminal_v8_render.py \
  tests/test_rewinding_ui_script_safety.py \
  -q
```

Expected: compilation and syntax checks exit `0`, all countdown Node tests pass, and all focused Python tests pass with zero failures.

- [ ] **Step 2: Run the complete automated suites**

Run:

```bash
source .venv/bin/activate
python -m pytest -q
node --test tests/js/*.test.mjs
```

Expected: both complete suites pass with zero failures. Record exact passed/skipped counts from the fresh output rather than copying historical counts.

- [ ] **Step 3: Reconfirm repository-local browser tooling and saved evidence**

Run:

```bash
./node_modules/.bin/playwright --version
sed -n '1,240p' artifacts/ui-checks/roll-change-indicator-thresholds/verification-summary.json
```

Expected: Playwright reports the repository-installed version, the summary status is `passed`, both supported viewports are present, and console/page error arrays are empty. If runtime code changed after Task 2's live run, repeat Task 2 Steps 7-8 before proceeding.

- [ ] **Step 4: Check whitespace and exact working-tree scope**

Run:

```bash
git diff --check
rg -n "[[:blank:]]+$" \
  docs/superpowers/specs/2026-08-01-roll-change-indicator-thresholds-design.md \
  docs/superpowers/plans/2026-08-01-roll-change-indicator-thresholds.md
git status --short --untracked-files=all
```

Expected: `git diff --check` emits no errors; the trailing-whitespace search emits no matches; status shows the approved feature files plus the preserved pre-existing unrelated changes. Do not delete, restore, stage, or absorb those unrelated files.

- [ ] **Step 5: Perform the final feature diff review**

Run:

```bash
git diff -- \
  app/static/js/roll_change_countdown_core.mjs \
  tests/js/roll_change_countdown_core.test.mjs \
  scripts/verify_roll_change_countdown_ui.mjs \
  tests/test_roll_change_countdown_ui_script_safety.py \
  README.md \
  docs/implementation-notes/roll-change-countdown.md \
  v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md \
  app/static/js/roll_change_countdown.mjs \
  app/templates/terminal.html \
  app/main.py \
  app/db.py \
  app/schema.py \
  app/migrations.py
```

Verify line by line:

- exact `15:00` is yellow and exact `05:00` is red;
- urgent comparison precedes warning comparison;
- `Math.ceil` display rounding is unchanged;
- paused/resync/due precedence is unchanged;
- both existing surfaces still consume the same `tone` result;
- no button placement, markup, CSS, storage, acknowledgement, backend, schema, or migration code changed;
- browser verification uses only temporary fixture paths; and
- documentation matches the implementation and approved design.

- [ ] **Step 6: Record the migration assessment in the handoff report**

Use this conclusion unless the actual final diff contains an unexpected persistent-data change:

```text
Migration assessment
- Decision: No migration
- Why: The feature changes browser-side tone thresholds, tests, guarded UI verification, and documentation only; it changes no SQLite structure or stored-value meaning.
- Existing production data affected: none
- Proposed migration: none
- Transformation: no values changed
- Unknowns or ambiguous rows: none known
- Required tests: temporary-browser fixture, focused countdown/render/verifier tests, and the complete Python/Node suites
- Production snapshot needed now: No
- Deployment constraint: deploy the static JavaScript and documentation change with the application only after the normal review and verification gates; no database transformation is required.
```

Do not modify `app/migrations.py`, the migration registry, or the runtime database for this feature.

- [ ] **Step 7: Hand off for review without committing**

Report:

- the exact behavior implemented;
- the files changed;
- focused and full test counts;
- Playwright version and both viewport results;
- screenshot and summary paths;
- the no-migration decision;
- confirmation that reset-button relocation was excluded; and
- the pre-existing unrelated worktree changes that were preserved.

Do not stage, commit, push, merge, deploy, or mutate production data unless the user gives a separate explicit instruction.
