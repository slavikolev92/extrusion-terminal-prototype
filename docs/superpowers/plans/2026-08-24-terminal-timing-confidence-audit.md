# Terminal Timing Correction Confidence Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two independent-review findings and establish high confidence that terminal timing correction is consistent, atomic, race-safe, and reliable in the supported Chromium workstation workflow.

**Architecture:** Preserve the existing shared timing-ledger engine and server-rendered terminal. Fix retained stale state at the response-model boundary, make successful preview order authoritative for the editor, then add deterministic ledger, SQLite interleaving, and real-browser race coverage. Verification remains repository-local and uses temporary SQLite databases only.

**Tech Stack:** Python 3, FastAPI, direct `sqlite3`, Jinja templates, browser ES modules, Node `node:test`, repository-local Playwright/Chromium, pytest.

**Spec:** `docs/superpowers/specs/2026-08-21-terminal-timing-correction-design.md`

## Global Constraints

- Do not change the schema or add a migration.
- Do not add a Python or Node dependency.
- Do not modify the real runtime database at `data/extrusion_terminal.sqlite3`.
- Do not add cross-card or machine-conflict validation.
- Do not alter existing Start, Pause/Resume, Finish eligibility, order, styling, or lifecycle behavior outside the approved Finish Review interception.
- Completed-card timing remains read-only to terminal operators; stale drafts are visible only as locked recovery state.
- Use deterministic conditions and database barriers; do not hide races with arbitrary sleeps.
- Chromium is the supported pilot browser. Do not add a multi-browser grid or pixel-perfect screenshot baseline.
- Keep screenshots and temporary databases under ignored `artifacts/ui-checks/` and `.test-runtime/`.
- Follow TDD for every production behavior change: record the expected RED failure before implementation and the GREEN result after it.
- Per repository policy, do not stage or commit without separate user approval.

---

### Task 1: Preserve Locked Drafts Across Status-Transition Races

**Files:**
- Modify: `app/main.py`
- Modify only if the retained model needs an explicit recovery branch: `app/templates/terminal.html`
- Test: `tests/test_terminal_timing_correction.py`
- Test: `tests/test_terminal_v8_render.py`

**Interfaces:**
- Consumes: the existing `terminal_post_response()`, `build_terminal_context()`, `build_terminal_timing_model()`, `finish_terminal_card()`, `TimingDraftRow`, and stale-card message.
- Produces: a locked retained timing model and retained Finish Review response that remain renderable after the current card status leaves `running`/`paused`.

- [ ] **Step 1: Add failing ordinary-Save race tests**

Add a parameterized route test for current status `completed`, `cancelled`, and `awaiting_rewinding`. Open a valid running/paused timing draft, change the stored status and version through a separate committed write, submit the old version and exact draft, then assert:

```python
assert response.context["timing_result"].messages == (db.STALE_CARD_MESSAGE,)
assert response.context["terminal_timing"]["locked"] is True
assert response.context["terminal_timing"]["draft"] == expected_draft_payload
assert stored_finish_snapshot(card_id) == after_competing_write
```

The break this test catches is dropping the submitted draft because current edit eligibility is false.

- [ ] **Step 2: Add failing Finish-confirmation race tests**

Parameterize the same lifecycle transitions after a valid authenticated Finish Review is opened. Submit the original review token and draft and assert the response does not enter the legacy Finish path:

```python
assert response.context["workflow_result"].messages == (db.STALE_CARD_MESSAGE,)
assert response.context["finish_review_open"] is True
assert response.context["finish_review_stale"] is True
assert response.context["finish_review_draft_json"] == submitted_json
assert stored_finish_snapshot(card_id) == after_competing_write
```

The break this test catches is deciding whether a review existed from the card's new status instead of the authenticated submitted review.

- [ ] **Step 3: Run the focused tests and record RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_timing_correction.py -k "status_transition and retained" -q
```

Expected: failures showing the ordinary timing model is absent and/or Finish Review is not reopened.

- [ ] **Step 4: Implement the smallest retained-state response change**

Make retained stale state independent of current edit eligibility:

- Parse an authenticated nonblank Finish Review submission before selecting the legacy Finish branch.
- A stale authenticated review must retain its exact parsed draft and token but remain locked.
- Permit `build_terminal_timing_model()` to build a recovery-only model when `stale=True` and a retained draft/version are present, even if the active shift ended or the card is no longer editable.
- Never grant write eligibility from recovery state; all inputs and write actions remain locked and Reload/Cancel are the only exits.
- Preserve the competing database state exactly.

- [ ] **Step 5: Run GREEN and render checks**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_timing_correction.py -k "status_transition and retained" -q
.venv/bin/python -m pytest tests/test_terminal_v8_render.py -q
```

Expected: all selected tests pass with no warnings.

- [ ] **Step 6: Self-review**

Inspect the diff for any accidental change to normal completed/cancelled visibility, active-shift policy, legacy awaiting-rewinding finalization, or lifecycle buttons.

---

### Task 2: Make Chronological Display Order Authoritative

**Files:**
- Modify: `app/static/js/timing_interval_editor_core.mjs`
- Modify: `app/static/js/timing_interval_editor.mjs`
- Modify only if the preview payload needs an explicit order field: `app/db.py`, `app/main.py`
- Test: `tests/js/timing_interval_editor_core.test.mjs`
- Test: `tests/test_terminal_timing_correction.py`
- Test: `tests/test_terminal_v8_render.py`

**Interfaces:**
- Consumes: chronological `preview.intervals[*].source_index`, server-provided `first_start_display` and `proposed_stop_display`, `mapServerPreview()`, draft serialization, deleted-row representation.
- Produces: one chronological visible order whose numbering, durations, summary boundaries, and serialized follow-up previews agree.

- [ ] **Step 1: Add failing pure-JavaScript ordering tests**

Construct two valid rows in source order B/A while the preview intervals arrive chronologically as source indexes `[1, 0]`. Assert:

```javascript
assert.deepEqual(result.rows.filter((row) => !row.deleted).map((row) => row.segment_id), [101, 202]);
assert.deepEqual(result.rows.filter((row) => !row.deleted).map((row) => row.display_number), [1, 2]);
assert.deepEqual(result.rows.filter((row) => !row.deleted).map((row) => row.duration_seconds), [3600, 7200]);
assert.equal(result.first_start_display, "20.08.2026 08:00");
assert.equal(result.proposed_stop_display, "20.08.2026 12:00");
```

Add a deleted existing row and assert it remains serializable as deleted but is not included in visible numbering. The break caught is preserving source order while applying chronologically calculated totals.

- [ ] **Step 2: Add failing backend/route consistency tests**

Submit two valid non-overlapping intervals whose corrected timestamps exchange order. Cover ordinary preview/save and Finish preview/rejected confirmation. Assert literal chronological starts, durations, first boundary, proposed stop, production seconds, and paused seconds.

- [ ] **Step 3: Run focused tests and record RED**

Run:

```bash
node --test tests/js/timing_interval_editor_core.test.mjs
.venv/bin/python -m pytest tests/test_terminal_timing_correction.py -k "chronological or reordered" -q
```

Expected: the JavaScript row-order assertion and retained-Finish boundary assertion fail against the current implementation.

- [ ] **Step 4: Implement chronological preview normalization**

- Treat the order of successful `preview.intervals` as authoritative for active rows.
- Reorder active draft rows and remap duration values without losing segment IDs, field values, or confirmed draft deletions.
- Recompute contiguous display numbers after normalization.
- Preserve hidden existing deleted rows for atomic serialization.
- Use server-provided `first_start_display` and `proposed_stop_display`; do not derive authoritative boundaries from the first and last submitted array elements.
- Automatic previews must preserve the focused logical field even when its row moves.

- [ ] **Step 5: Run GREEN and regression checks**

Run:

```bash
node --test tests/js/timing_interval_editor_core.test.mjs
.venv/bin/python -m pytest tests/test_terminal_timing_correction.py -k "chronological or reordered" -q
.venv/bin/python -m pytest tests/test_terminal_v8_render.py -q
```

Expected: all selected tests pass with no warnings.

- [ ] **Step 6: Self-review**

Inspect add-before-open-row, draft deletion, incomplete-input, source-index error mapping, focus restoration, and ordinary running final-open-row protection.

---

### Task 3: Add Deterministic Backend And Concurrency Audit Coverage

**Files:**
- Test: `tests/test_terminal_timing_correction.py`
- Test: `tests/js/timing_interval_editor_core.test.mjs`

**Interfaces:**
- Consumes: real timing/Finish routes, two SQLite connections, existing interleaving helpers, and the authoritative editor-core preview mapping.
- Produces: deterministic interval algebra, structural-edit, token-boundary, rollback, and transaction-interleaving coverage without a new framework.

- [ ] **Step 1: Add a bounded interval-oracle matrix**

Using standard-library `itertools`, enumerate hand-bounded 1–4 interval ledgers containing gaps, adjacency, permutations, reversal, equality, and overlap. Expected totals must come from literal interval arithmetic in a small test-only oracle, not production helpers. Assert:

```python
assert preview.production_seconds == expected_production_seconds
assert preview.paused_seconds == expected_paused_seconds
assert [row["source_index"] for row in preview.intervals] == expected_chronological_sources
```

Valid permutations must normalize consistently; invalid ledgers must return the expected field-targeted issue without mutation.

- [ ] **Step 2: Add deterministic SQLite interleaving tests**

Cover ordinary Save and reviewed Finish with a committed competing writer blocked/released by barriers. Assert:

```python
assert sorted(result.ok for result in outcomes) == [False, True]
assert stale_outcome.messages == (db.STALE_CARD_MESSAGE,)
assert after["card"]["version"] == before_version + 1
assert after["timing_rows"] in (winner_expected_ledger,)
```

Also assert no mixed ledger/lifecycle state and unchanged unrelated card/roll fields.

- [ ] **Step 3: Add structural-edit and confirm-boundary coverage**

Add one ordinary multi-row delete/add save and one reviewed-Finish add/delete success case. Assert exact surviving IDs, end reasons, first-start/finish markers, one version increment, and full unrelated-data preservation. Add an actual Finish endpoint matrix for missing, tampered, restart-invalidated, and replayed review tokens, with complete before/after snapshots.

- [ ] **Step 4: Run the focused backend audit suites**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_timing_correction.py tests/test_terminal_v8_render.py -q
node --test tests/js/timing_interval_editor_core.test.mjs
```

Expected: all selected tests pass with no warnings.

- [ ] **Step 5: Self-review**

Confirm every new test names a realistic production break, derives expected values independently, exercises real code, and avoids source-text-only assertions unless protecting verifier safety policy.

---

### Task 4: Add Real-Browser Race And Recovery Audit Coverage

**Files:**
- Modify: `scripts/create_terminal_timing_correction_fixture.py`
- Modify: `scripts/verify_terminal_timing_correction_ui.mjs`
- Test: `tests/test_terminal_timing_correction_ui_script_safety.py`

**Interfaces:**
- Consumes: completed Tasks 1–3, existing guarded temporary fixture, real FastAPI routes, Playwright Chromium, and the editor preview coordinator.
- Produces: condition-driven asynchronous-response, two-page lifecycle-race, stale recovery, failure hydration, and chronological display browser evidence.

- [ ] **Step 1: Add browser race scenarios**

Extend the guarded verifier with condition-based checks for:

- two preview responses released in reverse order: only the newest updates totals/errors;
- a preview released after a field becomes incomplete: calculations remain cleared and focus remains in the edited field;
- a second page changes status to completed/cancelled while ordinary Save or Finish Review is open: the exact draft remains visible, locked, and unpersisted;
- the active shift ends while the editor is open: pending preview work cannot overwrite the shift-reload state;
- a real server-rendered Finish validation failure: modal, message, exact draft, Cancel path, and focus recover correctly;
- reordered valid intervals: visible numbering, durations, totals, stored order after reload, and Finish boundaries remain consistent.

Use response/DOM conditions, not fixed sleeps. Reuse the existing verifier and fixture instead of creating another harness.

- [ ] **Step 2: Extend verifier safety tests only for new behavior**

Assert that the new scenarios still require an explicit temporary fixture, exact `/health` database identity, and ignored artifact root. Do not add adversarial filesystem hardening or installation commands.

- [ ] **Step 3: Run the focused browser-support suites**

```bash
.venv/bin/python -m pytest tests/test_terminal_timing_correction_ui_script_safety.py tests/test_terminal_v8_render.py tests/test_terminal_timing_correction.py -q
node --test tests/js/timing_interval_editor_core.test.mjs
```

- [ ] **Step 4: Run one live guarded Chromium pass**

Create a fresh ignored fixture, start one Uvicorn server against that exact
database, confirm `/health`, and run the complete verifier once. All new race
scenarios must pass without console/page errors.

- [ ] **Step 5: Self-review**

Confirm listeners/routes are scoped and removed, conditions replace arbitrary
sleeps, the verifier cannot target the runtime database, artifacts stay
ignored, and no permanent multi-browser or screenshot-noise machinery was
added.

---

### Task 5: Execute The Final Release-Confidence Gate

**Files:**
- Modify: `docs/implementation-notes/terminal-timing-correction.md`
- Modify: `docs/superpowers/plans/2026-08-23-terminal-timing-editor-polish.md`
- Evidence only: `artifacts/ui-checks/terminal-timing-confidence-audit/`

**Interfaces:**
- Consumes: completed Tasks 1–4, fresh temporary fixture, current feature-branch diff, backup tooling, repository-local Chromium.
- Produces: fresh SHA/diff-tied verification evidence, resolved review findings, final independent-review verdict, and a concise audit report.

- [ ] **Step 1: Run syntax/import and focused checks**

```bash
.venv/bin/python -m compileall -q app tests scripts
node --test tests/js/timing_interval_editor_core.test.mjs
.venv/bin/python -m pytest tests/test_terminal_timing_correction.py tests/test_terminal_v8_render.py tests/test_terminal_timing_correction_ui_script_safety.py -q
```

- [ ] **Step 2: Run the complete repository regression**

```bash
.venv/bin/python -m pytest -q
git diff --check
```

Record exact counts, versions, current HEAD, and dirty paths.

- [ ] **Step 3: Run the live Chromium audit three times**

Create a fresh temporary SQLite fixture for each run. Start one Uvicorn process bound to `127.0.0.1` for verification, confirm `/health` names the exact fixture, and run:

```bash
BASE_URL=http://127.0.0.1:8015 \
FIXTURE_JSON=.test-runtime/terminal-timing-confidence-audit/run-1/fixture.json \
ARTIFACT_DIR=artifacts/ui-checks/terminal-timing-confidence-audit/run-1 \
node scripts/verify_terminal_timing_correction_ui.mjs
```

Use the same command with matching `run-2` and `run-3` fixture/artifact
directories for the second and third executions.

Inspect canonical screenshots at `1366×768` and `1920×1080`. Repetition is a one-time release audit, not a permanent suite multiplier.

- [ ] **Step 4: Verify storage and recovery**

Against a separate temporary database only, run `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, create a SQLite-safe backup, restore it to another temporary path, and compare card/timing/roll snapshots.

- [ ] **Step 5: Request final independent code review**

Review the complete feature range and all uncommitted confidence-audit changes against the approved spec. Critical or Important findings must be fixed and scoped re-reviewed before completion.

- [ ] **Step 6: Update durable records**

- Mark both Post-review Follow-up checkboxes in the polish plan complete only after their regression tests and browser checks pass.
- Update the implementation note with exact commands, test counts, artifact paths, audit findings, supported Chromium contract, and residual limits.
- Record newly discovered defects and their fixes; explicitly state when no additional defect was found.

- [ ] **Step 7: Leave a reviewable workspace**

Stop audit servers, confirm no runtime database changed, keep artifacts ignored, do not stage or commit, and provide the user a concise report covering fixes, audit scope, findings, verification evidence, residual risks, and recommended merge readiness.
