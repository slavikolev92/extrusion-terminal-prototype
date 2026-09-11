# Physical Pallet Weight Acceptance Corrections Implementation Plan

> **Precision amendment (2026-09-11):** The input/storage precision portions of
> this completed correction record are superseded by
> `docs/superpowers/plans/2026-09-11-physical-pallet-weight-two-decimal-precision.md`.
> Its modal dismissal, banners, and icon decisions remain current.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan status:** Completed on 2026-09-11. No files were staged or committed.

**Goal:** Correct the pallet-weight input and dismissal behavior, make finish and pallet-summary feedback unmistakable, and add a consistent icon to the terminal pallet action.

**Architecture:** Keep the existing integer-tenths database contract and single-field autosave route. Change only the shared pure parsers, the pallet autosave controller, the shared modal markup/styles, and the existing terminal Finish Review/status surface; server validation remains authoritative and optimistic concurrency remains unchanged.

**Tech Stack:** Python 3, FastAPI, Jinja2, direct `sqlite3`, pytest, vanilla JavaScript ES modules, Node test runner, repository-local Playwright.

**Spec:** `docs/superpowers/specs/2026-09-09-physical-pallet-weight-design.md`

## Global Constraints

- Work in the existing `feature/physical-pallet-weight` checkout because the feature under correction is uncommitted there; do not copy partial state into another worktree.
- Preserve `TEMP - Task 20 requirements-spec.md` and all unrelated user changes.
- Do not stage or commit without explicit user authorization.
- Keep `card_pallet_weights.weight_tenths` and its `1..1000` SQLite constraint unchanged.
- Accept blank input as clear; accept unsigned integers or one/two decimal places with `.` or `,`; round half-up to one decimal; reject zero/negative, raw values above `100.0`, scientific notation, text, embedded whitespace, and more than two decimals.
- Keep the backend authoritative and keep terminal/admin parsing behavior identical.
- Explicit dismissal discards an invalid unsaved draft and restores the last saved value. Valid dirty values still autosave before dismissal. Stale/network/malformed-response states remain clearly marked and reload-protected but may not trap the operator inside the modal.
- Show one fixed-height status banner, not a second visible error below the input.
- Restrict icon work to the pallet button and status banners touched here; the application-wide icon redesign is follow-on work.
- Use only temporary databases for automated/browser verification.

---

### Task 1: Exact two-decimal input and half-up normalization

**Files:**
- Modify: `tests/test_physical_pallet_weights.py`
- Modify: `tests/js/pallet_weight_autosave_core.test.mjs`
- Modify: `app/pallet_summary.py`
- Modify: `app/static/js/pallet_weight_autosave_core.mjs`
- Modify: `app/static/js/pallet_weight_autosave.mjs`

**Interfaces:**
- Produces: `parse_physical_pallet_weight(raw: str, pallet_number: int) -> tuple[int | None, str | None]`
- Produces: `parsePalletWeightDraft(rawValue) -> {kind: "blank"} | {kind: "valid", tenths: number} | {kind: "invalid", reason: string}`
- Preserves: the existing JSON route contract and integer-tenths persistence.

- [x] **Step 1: Write failing backend parser cases**

Add literal cases proving `10.55 -> 106`, `12.54 -> 125`, `12,55 -> 126`, `100.00 -> 1000`, `0.05 -> 1`, and integer normalization. Add rejection cases proving `-5` and `0.04` use the minimum/range message, `100.01` uses the maximum message, and `12.555` uses the two-decimal format message.

- [x] **Step 2: Write matching failing JavaScript parser cases**

Use the same literal cases and expected integer tenths. The test that previously classified `12.55` and `-1` as `format` must instead expect a valid rounded value and `minimum`, respectively.

- [x] **Step 3: Run the parser tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_physical_pallet_weights.py -k parse_physical_pallet_weight -vv
node --test tests/js/pallet_weight_autosave_core.test.mjs
```

Expected: failures show that two decimals are rejected and negative input is misclassified by the current parsers.

- [x] **Step 4: Implement the exact shared grammar and rounding rule**

Use an anchored grammar equivalent to:

```text
-?[0-9]+(?:[.,][0-9]{1,2})?
```

Classify a leading minus as `minimum`; reject oversized significant whole parts before numeric conversion; compare raw hundredths with `10000`; and calculate stored tenths with integer half-up rounding:

```text
rounded_tenths = whole * 10 + floor((fraction_hundredths + 5) / 10)
```

Update the user-facing format message to say at most two decimal places. Do not use binary floating-point for accepted-value normalization.

- [x] **Step 5: Run focused parser and route tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_physical_pallet_weights.py -k "parse_physical_pallet_weight or route_returns_authoritative" -vv
node --test tests/js/pallet_weight_autosave_core.test.mjs
```

Expected: all selected tests pass and a `10.55` route save returns/stores `10.6`/`106`.

### Task 2: Dismissible drafts and single accessible validation feedback

**Files:**
- Modify: `tests/js/pallet_weight_autosave_core.test.mjs`
- Modify: `app/static/js/pallet_weight_autosave.mjs`
- Modify: `app/templates/_pallet_summary_modal.html`
- Modify: `app/static/css/pallet_summary.css`
- Modify: `scripts/verify_terminal_pallet_summary_ui.mjs`

**Interfaces:**
- Preserves: `pallet-summary:prepare-dismiss` with `detail.decision: Promise<boolean>`.
- Produces: dismissal result `true` after restoring invalid drafts; valid dirty fields still wait for their save/reconciliation.
- Produces: one footer message identified by `pallet-weight-status-message`, referenced by invalid inputs through `aria-errormessage`.

- [x] **Step 1: Write failing controller tests**

Add direct tests around `controller.prepareDismiss()` proving:

```javascript
input.value = "-5";
input.dispatchEvent(new Event("input"));
assert.equal(await controller.prepareDismiss(), true);
assert.equal(input.value, "12.0");
assert.equal(input.attributes.has("aria-invalid"), false);
```

Also prove a fatal stale state returns `true` for explicit dismissal without changing the saved value or claiming success. Keep the existing valid-dirty autosave coverage.

- [x] **Step 2: Run the controller test and verify RED**

Run:

```bash
node --test tests/js/pallet_weight_autosave_core.test.mjs
```

Expected: invalid and fatal dismissal assertions fail under the current modal-trapping behavior.

- [x] **Step 3: Implement discard-on-dismiss without weakening writes**

Add a small `restoreSavedField(field)` helper that restores `field.savedValue`, sets `state = "clean"`, and removes invalid/busy state. In `prepareDismiss()`:

- restore locally invalid dirty/failed drafts instead of resubmitting them;
- await any already active save and any valid dirty save;
- after a nonfatal server validation failure, restore that unsaved field and allow the explicit dismissal;
- after fatal stale/network/malformed response, allow explicit dismissal while leaving the controller fatal and the page's optimistic-concurrency protection intact;
- never emit a success status for discarded input.

- [x] **Step 4: Remove the row-shifting duplicate error**

Remove `.pallet-weight-field-error` markup and CSS. Give the footer message the stable ID `pallet-weight-status-message`; keep `aria-invalid` on the field and connect it through `aria-errormessage`. Keep the footer region live and fixed-height.

- [x] **Step 5: Update the existing browser verifier contract**

Change the invalid-dismissal assertion from “modal stays open” to: every X/footer/Escape/backdrop dismissal closes, restores opener focus, issues no pallet-weight write for the invalid draft, and shows no row-level error node. Keep valid-dirty autosave and fatal reload/error checks, but assert fatal states are explicitly dismissible rather than inescapable.

- [x] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
node --test tests/js/pallet_weight_autosave_core.test.mjs
.venv/bin/python -m pytest tests/test_terminal_pallet_summary.py tests/test_terminal_pallet_summary_scripts.py tests/test_order_finish_review_ui_script_safety.py -vv
```

Expected: all selected tests pass.

### Task 3: Semantic banners and bounded icon alignment

**Files:**
- Create: `app/static/images/terminal-ui/pallet.svg`
- Create: `app/static/images/terminal-ui/status-check-circle.svg`
- Create: `app/static/images/terminal-ui/status-circle-x.svg`
- Create: `app/static/images/terminal-ui/status-triangle-alert.svg`
- Modify: `app/templates/_pallet_summary_modal.html`
- Modify: `app/static/css/pallet_summary.css`
- Modify: `app/templates/terminal.html`
- Modify: `tests/test_order_finish_review_ui_script_safety.py`
- Modify: `tests/test_terminal_pallet_summary.py`

**Interfaces:**
- Produces: reusable `.semantic-status-banner[data-kind="success|error|warning"]` presentation with a decorative `20px` mask icon.
- Preserves: existing status roles, live-region behavior, dynamic text hooks, and Finish Review confirmation logic.

- [x] **Step 1: Write failing rendered-markup tests**

Assert that the terminal pallet button contains the `pallet` icon asset; pallet status uses the shared semantic-banner class; Finish Review blocker and warning elements use the same class with `data-kind="error"` and `data-kind="warning"`; and the inline pallet error element is absent.

- [x] **Step 2: Run template tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary.py tests/test_order_finish_review_ui_script_safety.py -vv
```

Expected: new semantic-banner/icon assertions fail.

- [x] **Step 3: Add the four bounded vector assets**

Use the existing terminal icon language: `24x24` viewBox, no fill, round caps/joins, and `2px` stroke geometry. The pallet action uses a transport-truck asset that remains recognizable at `20px`. Status assets depict check-circle, circle-X, and warning triangle; CSS masks apply `currentColor`.

- [x] **Step 4: Apply one shared banner treatment**

In `pallet_summary.css`, define the shared banner geometry and pale semantic colors. Render its decorative icon with `::before`, selecting the mask from `data-kind`. Keep the pallet modal's existing green/red behavior, add the warning variant, and apply the error/warning variants to Finish Review without changing message generation or lifecycle rules.

- [x] **Step 5: Add the pallet action icon**

Render `terminal_icon("pallet")` before `Палети` and size that touched button icon to `20px`. Do not alter unrelated action icons.

- [x] **Step 6: Run template and JavaScript tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary.py tests/test_order_finish_review_ui_script_safety.py tests/test_terminal_v8_render.py -vv
node --test tests/js/*.test.mjs
```

Expected: all selected tests pass.

### Task 4: Live UI verification and bounded review

**Files:**
- Modify: `scripts/verify_terminal_pallet_summary_ui.mjs`
- Modify: `docs/implementation-notes/physical-pallet-weight.md`
- Create disposable evidence under: `artifacts/ui-checks/physical-pallet-weight-acceptance-corrections/`

**Interfaces:**
- Consumes: the existing temporary fixture builder and repository-local Playwright.
- Produces: screenshots and verifier output proving the corrected UI without touching the runtime database.

- [x] **Step 1: Run the focused live browser workflow on a temporary database**

Start FastAPI with a temporary `EXTRUSION_DB_PATH`, run the repository-local Playwright verifier, and cover at least:

- `10.55` saves as `10.6`;
- `-5` shows one red footer banner naming the pallet, with no row movement;
- X/footer/Escape/backdrop dismiss invalid drafts and restore the saved value;
- valid dirty dismissal saves before close;
- a finish blocker is a pale-red circle-X banner;
- the rewinding-entry notice is a pale-amber warning banner;
- the pallet button shows the new icon.

Capture representative `1440x900` and `1366x768` screenshots under the stated artifacts directory.

- [x] **Step 2: Run full verification**

Run:

```bash
.venv/bin/python -m compileall -q app scripts tests
.venv/bin/python -m pytest
node --test tests/js/*.test.mjs
git diff --check
```

Expected: all commands exit `0` with no unexpected warnings.

- [x] **Step 3: Review the bounded diff**

Confirm that database schema/storage semantics, finish lifecycle rules, print calculations, unrelated icons, Task 20, and runtime data are unchanged. Update the implementation note with the final accepted parsing/dismissal/banner behavior and exact verification commands. Do not stage or commit.
