# Shift UI Spacing And Density Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the approved spacing, icon-color, metadata-width, and terminal-density refinements without changing shift behavior.

**Architecture:** Keep the existing templates, routes, and JavaScript intact. Express the refinement through focused CSS changes in `app/templates/terminal.html`, backed by render-level contract assertions and one live-browser visual check.

**Tech Stack:** FastAPI, Jinja2, inline CSS, pytest, repo-local Playwright.

## Global Constraints

- Preserve the 600 × 560 start/end confirmation geometry and existing typography.
- Do not change shift lifecycle behavior, routes, database structure, or stored data.
- Keep the Details scrollbar as a fallback and do not shrink recipe rows or fonts.
- Do not mutate the runtime database during automated or browser verification.

---

### Task 1: Refine shift spacing and terminal vertical density

**Files:**
- Modify: `app/templates/terminal.html`
- Modify: `tests/test_terminal_v8_render.py`
- Verify: `scripts/verify_shift_management_ui.mjs`

**Interfaces:**
- Consumes: existing shift-pane classes, height media queries, and Playwright shift workflow.
- Produces: stable CSS contracts for confirmation spacing, equal summary metadata columns, blue start icons, and compact workstation chrome.

- [x] **Step 1: Write failing render assertions**

Add tests that require:

```python
assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in summary_rules
assert 'stroke="#2865d8"' in play_icon
assert "margin-top: 10px;" in confirmation_question_rules
assert "min-height: 70px;" in compact_height_rules
assert "min-height: 46px;" in compact_height_rules
assert "row-gap: 14px;" in compact_height_rules
```

- [x] **Step 2: Verify the assertions fail for the intended missing CSS contracts**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_v8_render.py -k "targeted_shift_spacing or targeted_terminal_density" -q
```

Expected: the new tests fail because the current first summary column is narrower, the play icon is gray, the confirmation question has no top margin, and the compact chrome/detail values are larger.

- [x] **Step 3: Apply the minimal CSS changes**

In `app/templates/terminal.html`:

- add modest top separation to confirmation questions and rebalance end-confirmation vertical padding;
- use equal thirds for `.shift-summary-metadata`;
- change the shared `play-circle.svg` stroke to the established blue accent used by both start-time placements;
- reduce only the `max-height: 980px` machine-nav, machine-tab, topbar, Details-body, order-section, and info-grid vertical values;
- keep the existing `max-height: 760px` compact behavior coherent and preserve all typography and recipe-row sizes.

- [x] **Step 4: Run focused automated verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_v8_render.py -k "shift or targeted_terminal_density or recipe" -q
```

Expected: PASS.

- [x] **Step 5: Run one live-browser visual check**

Run the existing verifier against a temporary SQLite database and inspect the start confirmation, end confirmation, active-shift overview, produced summary, and fully populated recipe screenshot at 100% zoom.

- [x] **Step 6: Final focused checks**

Run:

```bash
.venv/bin/python -m pytest tests/test_shift_routes.py tests/test_terminal_v8_render.py -q
git diff --check
```

Expected: PASS with no whitespace errors.
