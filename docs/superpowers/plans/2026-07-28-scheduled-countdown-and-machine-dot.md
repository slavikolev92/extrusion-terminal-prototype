# Scheduled Countdown Catch-Up And Solid Machine Dot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make quick roll-change acknowledgement advance along the saved schedule to the first future interval and replace bordered machine-state indicators with solid 16px status circles.

**Architecture:** Keep the schedule calculation in the existing pure JavaScript core and keep presentation in the existing Terminal template. Update the guarded Playwright verifier and documentation to encode the approved behavior; do not add storage fields, backend behavior, or database migrations.

**Tech Stack:** ES modules, Node's built-in test runner, server-rendered Jinja/HTML/CSS, Python/Pytest source assertions, FastAPI, repo-local Playwright, browser-local storage.

## Global Constraints

- One acknowledgement advances at least one whole scheduled interval.
- Continue advancing until `nextExpectedAtMs` is strictly greater than the acknowledgement timestamp.
- The acknowledgement timestamp determines only how far to catch up; it never becomes the schedule anchor.
- A manual next-time override is the next scheduled anchor.
- The countdown never advances without an operator acknowledgement or editor save.
- The machine dot is a solid 16px green, yellow, or gray circle with no border or shadow.
- Preserve the existing hidden machine-state text, card geometry, lifecycle locks, cross-tab behavior, pause/resume behavior, and countdown bubble.
- Task 15, backend routes, SQLite, production timing, rolls, pallets, rewinding, shifts, printing, importing, and backups are out of scope.
- Use only temporary databases under `.test-runtime/` and evidence under `artifacts/ui-checks/`; never open or mutate `data/extrusion_terminal.sqlite3`.
- Do not stage or commit unless the user explicitly asks.

---

### Task 1: Scheduled-Cadence Catch-Up

**Files:**
- Modify: `tests/js/roll_change_countdown_core.test.mjs:69-89,103-177`
- Modify: `app/static/js/roll_change_countdown_core.mjs:57-68`

**Interfaces:**
- Consumes: `advanceSchedule(schedule, status, nowMs)` with a validated positive `schedule.intervalMinutes` and saved `schedule.nextExpectedAtMs`.
- Produces: an updated schedule whose `previousChangeAtMs` is the scheduled
  boundary immediately before the new `nextExpectedAtMs`, and whose
  `nextExpectedAtMs` is the first scheduled occurrence strictly after `nowMs`.

- [x] **Step 1: Replace click-time unit expectations with scheduled-cadence expectations**

Cover these literal cases using the existing `runningSchedule()` and `localAt()` helpers:

```javascript
test("acknowledgement advances scheduled cadence to the first future interval", () => {
  for (const [clickedAt, expectedPrevious, expectedNext] of [
    [localAt(2026, 7, 27, 13, 50), localAt(2026, 7, 27, 14, 0), localAt(2026, 7, 27, 16, 0)],
    [localAt(2026, 7, 27, 14, 0), localAt(2026, 7, 27, 14, 0), localAt(2026, 7, 27, 16, 0)],
    [localAt(2026, 7, 27, 14, 20), localAt(2026, 7, 27, 14, 0), localAt(2026, 7, 27, 16, 0)],
    [localAt(2026, 7, 27, 16, 15), localAt(2026, 7, 27, 16, 0), localAt(2026, 7, 27, 18, 0)],
  ]) {
    const advanced = advanceSchedule(runningSchedule(), "running", clickedAt);
    assert.equal(advanced.previousChangeAtMs, expectedPrevious);
    assert.equal(advanced.nextExpectedAtMs, expectedNext);
  }
});
```

Use real local timestamps rather than the illustrative minute-zero values where the existing fixture requires them. Add separate assertions that:

- exact-boundary acknowledgement skips the equal timestamp;
- a manual `nextExpectedAtMs` override anchors later catch-up;
- midnight crossing retains exact cadence;
- paused acknowledgement produces a positive `frozenRemainingMs` to the caught-up future occurrence and clears `pauseNeedsResolution`; and
- two successive acknowledgements each begin from the schedule saved by the preceding click.

- [x] **Step 2: Run the Node test and verify intentional RED**

Run:

```bash
node --test tests/js/roll_change_countdown_core.test.mjs
```

Expected: the new early/late/manual/paused assertions fail because `advanceSchedule()` currently writes `nowMs` into `previousChangeAtMs` and calculates from the click.

- [x] **Step 3: Implement the minimal constant-time catch-up calculation**

Replace only the body of `advanceSchedule()` with the scheduled loop:

```javascript
export function advanceSchedule(schedule, status, nowMs) {
  const intervalMs = schedule.intervalMinutes * 60_000;
  const intervalsToAdvance = Math.max(
    1,
    Math.floor((nowMs - schedule.nextExpectedAtMs) / intervalMs) + 1,
  );
  const previousChangeAtMs = schedule.nextExpectedAtMs
    + (intervalsToAdvance - 1) * intervalMs;
  const nextExpectedAtMs = calculateNextExpected(
    previousChangeAtMs,
    schedule.intervalMinutes,
  );
  return {
    ...schedule,
    previousChangeAtMs,
    nextExpectedAtMs,
    observedStatus: status,
    frozenRemainingMs: status === "paused" ? nextExpectedAtMs - nowMs : null,
    pauseNeedsResolution: false,
  };
}
```

Do not add a policy flag, storage version, background timer mutation, or backend call.

- [x] **Step 4: Run focused GREEN verification**

Run:

```bash
node --test tests/js/roll_change_countdown_core.test.mjs
node --check app/static/js/roll_change_countdown_core.mjs
```

Expected: every Node test passes and syntax checking exits `0`.

- [x] **Step 5: Review the Task 1 diff**

Confirm the runtime diff is confined to `advanceSchedule()`, every changed test asserts scheduled timestamps rather than implementation structure, and no production data or unrelated countdown lifecycle behavior changed. Do not stage or commit.

---

### Task 2: Solid Machine Dot And Live Workflow Contract

**Files:**
- Verify unchanged status markup: `tests/test_terminal_v8_render.py:350-370`
- Modify: `app/templates/terminal.html:366-377`
- Modify: `scripts/verify_roll_change_countdown_ui.mjs:489-530,730-880,1030-1080`
- Test: `tests/test_roll_change_countdown_ui_script_safety.py`

**Interfaces:**
- Consumes: saved schedule objects using `previousChangeAtMs`, `nextExpectedAtMs`, and `intervalMinutes`; `.machine-state-dot` elements rendered for all four machine cards.
- Produces: browser evidence that acknowledgement preserves cadence at early, on-time, late, corrected, cross-tab, and paused states, plus a computed 16px borderless/shadowless dot at both supported viewports.

- [x] **Step 1: Add failing computed-style dot assertions to the live verifier**

Extend the existing live machine-card measurement so each real rendered dot
returns its computed border width, box shadow, border radius, and background
colour. Require the real browser result to have:

```javascript
assertEqual(dot.width, 16, "machine dot width");
assertEqual(dot.height, 16, "machine dot height");
assertEqual(dotStyle.borderTopWidth, "0px", "machine dot border");
assertEqual(dotStyle.boxShadow, "none", "machine dot shadow");
```

and retain the existing green/yellow/gray class mappings and visually hidden labels.

- [x] **Step 2: Replace click-time verifier assertions with cadence assertions**

Use literal expected scheduled timestamps from deliberately boundary-safe
fixtures rather than duplicating the production formula in a verifier helper.
Before each quick-action click, retain the full saved schedule; afterwards
assert exact `previousChangeAtMs`, `nextExpectedAtMs`, status, pause fields, and
cross-tab storage against those expected scheduled values.

Apply this to the existing late, early, cross-tab, manually corrected, and paused acknowledgement checks. Remove labels such as `click-time anchor`; do not weaken lifecycle-lock, mutation-guard, cross-tab, or editor assertions.

Add computed-style/geometry assertions at both viewports:

```javascript
assertEqual(dot.width, 16, "machine dot width");
assertEqual(dot.height, 16, "machine dot height");
assertEqual(dotStyle.borderTopWidth, "0px", "machine dot border");
assertEqual(dotStyle.boxShadow, "none", "machine dot shadow");
```

- [x] **Step 3: Run the guarded live verifier and verify dot RED**

Create the existing countdown fixture below `.test-runtime/`, start FastAPI on
an unused loopback port other than `8000`, and run:

```bash
BASE_URL=http://127.0.0.1:<unused-port> \
FIXTURE_JSON=.test-runtime/scheduled-countdown-dot-fix/fixture.json \
ARTIFACT_DIR=artifacts/ui-checks/scheduled-countdown-dot-fix/red \
node scripts/verify_roll_change_countdown_ui.mjs
```

Expected: the verifier fails specifically because the rendered dot is 14px
with a 2px border and outer shadow. Confirm all setup/preflight checks reached
the machine-card assertion normally, then stop the temporary server.

- [x] **Step 4: Make the minimal CSS change**

Change only `.machine-state-dot` sizing/decorations:

```css
.machine-state-dot {
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
  border: 0;
  border-radius: 50%;
  box-shadow: none;
}
```

Keep the three existing status colors and hidden textual labels unchanged.

- [x] **Step 5: Run focused GREEN verification**

Run the Task 2 live verifier again with evidence under a `green/` directory,
plus:

```bash
node --test tests/js/roll_change_countdown_core.test.mjs
node --check scripts/verify_roll_change_countdown_ui.mjs
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py \
  tests/test_roll_change_countdown_ui_script_safety.py -q
git diff --check
```

Expected: all focused Python and Node tests pass; both JavaScript syntax and diff checks exit `0`.

- [x] **Step 6: Review the Task 2 diff**

Confirm the verifier still checks both supported viewports, lifecycle locking, editor validation, cross-tab synchronization, stale-tab behavior, and geometry. Confirm the only Terminal CSS change is the dot footprint and ring removal. Do not stage or commit.

---

### Task 3: Documentation, Migration Record, And Final Verification

**Files:**
- Modify: `README.md:180-200`
- Modify: `v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md:100-145,200-206,289-296,450-456,510-516`
- Modify: `v2-files/PLAN.md:350-405`
- Modify: `v2-files/RELEASE-CANDIDATE-VERDICT.md`
- Modify: `v2-files/RELEASE-CANDIDATE-AUDIT.md`
- Modify: `v2-files/AGENTS.md` migration assessment log
- Verify: `scripts/verify_roll_change_countdown_ui.mjs`

**Interfaces:**
- Consumes: the finished Task 1/2 diff and exact final verification output.
- Produces: documentation matching scheduled catch-up, Task 15 explicitly outside the current release scope, a No migration assessment, and guarded browser evidence for the corrected candidate.

- [x] **Step 1: Correct the durable countdown documentation**

Update README and Task 10 so they state:

```text
Quick acknowledgement advances at least one whole interval from the saved
next expected time, then continues along that cadence until the next expected
time is strictly in the future. The click time is never the schedule anchor.
```

Update examples for early, on-time, late, multi-interval, manual-override, and paused acknowledgement. Remove every contradictory statement that click time becomes `previousChangeAtMs` or that one click can advance only one interval.

- [x] **Step 2: Resolve the two release-record decisions**

Update the V2 plan/audit/verdict to record:

- scheduled-cadence catch-up is the approved and implemented behavior;
- Task 15 remains preserved as a deferred design but is outside the current release scope and is not a production prerequisite;
- production remains `NO-GO` solely for the unperformed production-backup Tasks 8-9; and
- the executable candidate is the working-tree correction until the user separately authorizes a commit, so no fabricated commit SHA is recorded.

- [x] **Step 3: Complete the migration assessment**

Inspect the actual diff and append one `No migration` row to the assessment log:

```text
Scheduled countdown catch-up and solid machine dot | No migration | Changed a
browser-local schedule calculation, Terminal CSS, verifier/tests, and
documentation only. No SQLite structure, stored production value, historical
row, or migration registry entry changed; no production snapshot is needed for
this correction.
```

Do not modify `app/migrations.py`, `app/db.py`, or `tests/test_migrations.py`.

- [x] **Step 4: Run focused automated verification**

Run:

```bash
node --test tests/js/roll_change_countdown_core.test.mjs
node --check app/static/js/roll_change_countdown_core.mjs
node --check app/static/js/roll_change_countdown.mjs
node --check scripts/verify_roll_change_countdown_ui.mjs
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py \
  tests/test_roll_change_countdown_ui_script_safety.py \
  tests/test_rewinding_ui_script_safety.py \
  tests/test_migrations.py -q
.venv/bin/python -m compileall -q app scripts tests
git diff --check
```

Expected: every test passes; syntax, compilation, and diff checks exit `0`.

- [x] **Step 5: Run the guarded live countdown verifier**

Create its fixture only under:

```text
.test-runtime/scheduled-countdown-dot-fix/
```

Start FastAPI on an unused loopback port other than `8000`, with both data environment variables pointing at that temporary directory. Run the established verifier with evidence under:

```text
artifacts/ui-checks/scheduled-countdown-dot-fix/
```

Require both `1920x768` and `1366x768`, exact early/on-time/late/catch-up/manual/paused/cross-tab results, solid-dot computed styles, zero console/page errors, no clipping/overlap/horizontal overflow, and clean server shutdown. Visually inspect the saved full-page machine-navigation screenshots.

- [x] **Step 6: Run the complete suites on the exact final tree**

Run:

```bash
.venv/bin/python -m pytest -q
node --test tests/js/*.test.mjs
git status --short --branch
git diff --check
```

Expected: the complete Python suite retains at least the 912-test baseline, all
19-or-more Node tests pass, the only tracked/untracked changes are this
feature's approved files, and diff checking exits `0`.

- [x] **Step 7: Final review without committing**

Review the complete diff for scheduled-cadence correctness, finite positive-interval catch-up, pause behavior, storage compatibility, machine-card geometry, documentation consistency, migration impact, and scope. Preserve all evidence and report the branch/worktree plus exact results. Do not stage, commit, merge, push, or deploy without a separate explicit user instruction.

Result: the independent adversarial review found no runtime or data issue and
one Minor historical-plan handoff contradiction. The handoff and historical
notice were corrected, and scoped re-review passed with final Critical /
Important / Minor counts of `0 / 0 / 0`. No files were staged or committed.
