# Terminal Pallet Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Use superpowers:test-driven-development for every behavior change and superpowers:verification-before-completion before making any completion claim. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give operators a read-only `Палети` modal on every terminal-visible card, showing saved roll count, gross weight, and net weight by pallet, with an overall total and safe behavior when roll data cannot be summarized.

**Architecture:** Add a pure terminal-specific calculator in `app/pallet_summary.py`, invoke it once while building the selected-card terminal context, and render its explicit `ready`, `empty`, or `error` view state in the existing server-rendered terminal page. Integrate the modal with the existing inline drawer/modal coordinator and background snapshot polling; do not add schema, persistence, routes, client-side arithmetic, print behavior, or a second modal framework. Contain any calculator or summary-integration exception only at this optional view-model boundary so malformed data cannot take down the terminal but can never produce plausible incorrect totals.

**Tech Stack:** Python 3, FastAPI, Jinja2, direct `sqlite3`, `Decimal`, pytest with temporary databases, vanilla JavaScript, repository-local Playwright.

## Global Constraints

- Read `README.md`, the supplied repository `AGENTS.md`, and the approved design at `docs/superpowers/specs/2026-08-04-terminal-pallet-summary-design.md` before implementation. If the authoritative README conflicts with this plan, stop and reconcile the conflict before code changes.
- Preserve the unrelated deleted `design-qa.md` work and every other pre-existing worktree change. Do not restore, rename, stage, or absorb it into this feature.
- Do not stage or commit unless the user explicitly asks. The review checkpoints in this plan replace commit steps.
- Never mutate `data/extrusion_terminal.sqlite3`, a file under `production-db/`, or any production backup. Automated and browser tests use unique files under `.test-runtime/`; generated UI evidence belongs under `artifacts/ui-checks/` and remains untracked.
- This is a read-only terminal feature. Do not add or change database columns, migrations, write routes, card lifecycle rules, roll-entry/correction behavior, admin screens, print calculations, or print output.
- Use only the selected card's already-fetched `roll_entries`. Opening or closing the modal must not make a feature-specific HTTP request or change any card version or production row.
- A participating roll is a saved roll entry whose `gross_weight` is not `NULL`. A card's `current_pallet_number` never creates a summary row.
- Parse each participating roll's saved gross, tare, and net values as finite, non-negative `Decimal` values and require `net_weight == gross_weight - tare_weight`. Require `pallet_number` to be `NULL` or an actual integer from `1` through `999`.
- Sum exact saved decimals, then format each group and overall total once to one decimal with `ROUND_HALF_UP`. Never sum floats or display strings and never silently omit, repair, recalculate, or zero invalid values.
- Numeric pallets sort ascending; append `Без палет` whenever at least one entered roll is unassigned, including all-unassigned cards. `Общо` is a separate footer row.
- The modal is available for pending, running, paused, `awaiting_rewinding`, and completed cards. When both actions exist, the order is `Пренавиване`, then `Палети`.
- Keep all modal ownership in the existing inline terminal drawer/modal coordinator. Opening the summary closes queue, waiting, history, and rewinding surfaces; correction mode disables it; finish, shift, and roll-change overlays must not stack with it.
- Treat stale rendered data as unsafe to read: card-stale closes without restoring focus to stale controls and focuses the existing reload action; shift-stale closes before the shift takeover surface.
- Log only the exception stack and numeric card ID at the fail-soft boundary. Do not log customer, order, material, notes, weights, or roll contents.
- Browser verification must use the repository-local Playwright package and capture relevant screenshots at both `1366x768` and `1920x1080`.

## Final Python Interfaces

Create the pure module with this public contract:

```python
# app/pallet_summary.py
from collections.abc import Iterable, Mapping
from typing import Any


class PalletSummaryDataError(ValueError):
    """A saved roll cannot be represented safely in a pallet summary."""


def build_terminal_pallet_summary(
    roll_entries: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return an empty or ready pallet-summary view model.

    Raises PalletSummaryDataError when any entered roll has unusable saved data.
    Unexpected programming errors are intentionally not caught here.
    """
```

The builder returns exactly one of these shapes:

```python
{
    "state": "empty",
    "rows": [],
    "total": None,
}

{
    "state": "ready",
    "rows": [
        {
            "pallet_number": 2,               # int or None
            "pallet_label": "2",             # or "Без палет"
            "roll_count": 3,
            "gross_weight": Decimal("21.08"),
            "net_weight": Decimal("20.18"),
            "gross_display": "21.1",
            "net_display": "20.2",
        },
    ],
    "total": {
        "roll_count": 3,
        "gross_weight": Decimal("21.08"),
        "net_weight": Decimal("20.18"),
        "gross_display": "21.1",
        "net_display": "20.2",
    },
}
```

The page-context boundary mutates only the already-built selected-card mapping:

```python
def attach_terminal_pallet_summary(card: dict[str, Any]) -> None:
    """Attach ready/empty/error summary state without failing the terminal page."""
```

On any exception from the optional summary call, it attaches:

```python
{"state": "error", "rows": [], "total": None}
```

## Final Browser Contract

Use stable, feature-owned hooks without changing existing IDs:

```html
<button type="button"
        class="roll-secondary-button"
        data-pallet-summary-open
        aria-controls="pallet-summary-overlay"
        aria-expanded="false">Палети</button>

<div id="pallet-summary-overlay"
     data-pallet-summary-overlay
     aria-hidden="true"
     hidden>
  <section role="dialog"
           aria-modal="true"
           aria-labelledby="pallet-summary-title"
           tabindex="-1"
           data-pallet-summary-dialog>
    <h2 id="pallet-summary-title">Обобщение по палети</h2>
    <p>Поръчка №{{ selected_card.order_number }}</p>
    <div data-pallet-summary-content></div>
    <button type="button" data-pallet-summary-close>Затвори</button>
  </section>
</div>
```

The existing snapshot poll emits `terminal:card-stale` once when the selected-card signature changes. The modal listens for `terminal:card-stale` and the existing `terminal:shift-stale`; no feature-specific polling loop or event bus is added.

## File Map

- Create `app/pallet_summary.py`: pure validation, grouping, exact summation, ordering, and one-decimal display formatting.
- Modify `app/main.py`: logger, calculator import, narrow fail-soft attachment helper, and selected-card context integration.
- Modify `app/templates/terminal.html`: always-available button, read-only modal markup and CSS, coordinator integration, stale-card event emission, focus and mutual-exclusion behavior.
- Create `tests/test_terminal_pallet_summary.py`: calculator, context, logging, rendering, semantic markup, and source-level coordinator contracts.
- Create `scripts/create_terminal_pallet_summary_fixture.py`: deterministic, guarded temporary SQLite browser fixture.
- Create `scripts/verify_terminal_pallet_summary_ui.mjs`: live interaction, accessibility, geometry, stale takeover, network, and non-mutation checks.
- Create `scripts/audit_terminal_pallet_summary_db.py`: guarded read-only compatibility audit for a temporary copy of the newest SQLite-safe backup.
- Create `tests/test_terminal_pallet_summary_scripts.py`: fixture, verifier, and production-auditor safety contracts.
- Create `docs/implementation-notes/terminal-pallet-summary.md`: durable behavior, failure-boundary, verification, and rollout-audit notes.

---

### Task 0: Preflight And Baseline

**Files:**
- Inspect only: repository instructions, approved design, current status, baseline tests

**Consumes:** The approved design and the shared worktree as found.

**Produces:** A recorded baseline and explicit list of unrelated changes to preserve.

- [ ] **Step 1: Re-read authoritative instructions and the approved design**

```bash
sed -n '1,360p' README.md
sed -n '1,320p' docs/superpowers/specs/2026-08-04-terminal-pallet-summary-design.md
```

Expected: the read-only pallet summary and its status, arithmetic, fail-soft, interaction, and rollout requirements match this plan. Stop and reconcile any later user-approved change before implementation.

- [ ] **Step 2: Record the shared-worktree state**

```bash
git status --short
git diff -- design-qa.md
```

Expected at plan-writing time: `design-qa.md` is deleted by unrelated work and the approved design plus this plan are untracked. Preserve those states and record any additional concurrent changes before editing overlapping files.

- [ ] **Step 3: Run the unmodified Python baseline**

```bash
.venv/bin/python -m pytest -q
```

Expected: all existing tests pass. Record the exact pass count. If they do not, distinguish a pre-existing failure from the feature before making source changes.

- [ ] **Step 4: Confirm browser tooling without installing anything**

```bash
./node_modules/.bin/playwright --version
```

Expected: the repository-local Playwright executable reports a version. Do not run npm install, download a browser, or use global tooling during this task.

**Review checkpoint:** No application files changed; no database opened for writing; nothing staged or committed.

---

### Task 1: Pure Pallet Summary Calculator

**Files:**
- Create: `tests/test_terminal_pallet_summary.py`
- Create: `app/pallet_summary.py`

**Consumes:** Saved roll-entry mappings from `fetch_roll_entries_and_totals()` and the existing terminal one-decimal `ROUND_HALF_UP` convention.

**Produces:** The exact `build_terminal_pallet_summary()` and `PalletSummaryDataError` interface defined above, with no database, template, logging, or printing dependency.

- [ ] **Step 1: Add the calculator happy-path tests first**

Start `tests/test_terminal_pallet_summary.py` with a small roll factory and these exact tests:

```python
from decimal import Decimal

import pytest

from app.pallet_summary import (
    PalletSummaryDataError,
    build_terminal_pallet_summary,
)

_AUTO_NET = object()


def roll(
    gross: object,
    tare: object = "0.30",
    net: object = _AUTO_NET,
    pallet: object = None,
) -> dict[str, object]:
    if net is _AUTO_NET and gross is None:
        calculated_net = None
    elif net is _AUTO_NET:
        calculated_net = Decimal(str(gross)) - Decimal(str(tare))
    else:
        calculated_net = net
    return {
        "gross_weight": gross,
        "tare_weight": tare,
        "net_weight": calculated_net,
        "pallet_number": pallet,
    }
```

Name the seven tests `test_pallet_summary_is_empty_when_no_gross_roll_is_entered`, `test_pallet_summary_groups_one_numbered_pallet_and_builds_total`, `test_pallet_summary_sorts_numbered_pallets_numerically_with_gaps`, `test_pallet_summary_keeps_all_unassigned_rolls_under_without_pallet`, `test_pallet_summary_places_mixed_unassigned_rolls_last`, `test_pallet_summary_uses_saved_rolls_not_a_current_pallet_default`, and `test_pallet_summary_accepts_a_zero_weight_entered_roll`.

Make the assertions exact. The mixed test must use pallet numbers `10`, `2`, and `None` in unsorted input and assert labels `['2', '10', 'Без палет']`, correct per-row counts/sums, and an overall count equal to every entered roll. The current-default test may add an unrelated `current_pallet_number` key to the input mappings and must prove it has no effect.

- [ ] **Step 2: Add rounding tests that catch both prohibited implementations**

Use values whose correct sum-then-round result differs from summing displayed rows, and a binary-float-sensitive boundary:

```python
def test_pallet_summary_sums_exact_values_before_one_final_rounding():
    summary = build_terminal_pallet_summary([
        roll("10.04", "0.00", pallet=1),
        roll("10.04", "0.00", pallet=1),
    ])

    assert summary["rows"][0]["gross_weight"] == Decimal("20.08")
    assert summary["rows"][0]["gross_display"] == "20.1"
    assert summary["total"]["gross_display"] == "20.1"


def test_pallet_summary_uses_decimal_half_up_at_the_display_boundary():
    summary = build_terminal_pallet_summary([
        roll("0.05", "0.00", pallet=1),
    ])

    assert summary["rows"][0]["gross_display"] == "0.1"
```

Also pass at least one Python `float` such as `10.1` and assert that `Decimal(str(value))` semantics produce the expected exact decimal rather than a binary artifact.

- [ ] **Step 3: Add defensive validation tests**

Parameterize each invalid condition and assert `PalletSummaryDataError`, not silent omission or a partial result:

```python
@pytest.mark.parametrize(
    ("entry", "field_name"),
    [
        (roll("bad", "0.30", "1.00", 1), "gross_weight"),
        (roll("NaN", "0.30", "NaN", 1), "gross_weight"),
        (roll("Infinity", "0.30", "Infinity", 1), "gross_weight"),
        (roll("10.00", None, "9.70", 1), "tare_weight"),
        (roll("10.00", "-0.10", "10.10", 1), "tare_weight"),
        (roll("10.00", "0.30", None, 1), "net_weight"),
        (roll("10.00", "0.30", "-1.00", 1), "net_weight"),
        (roll("10.00", "0.30", "9.71", 1), "net_weight"),
        (roll("10.00", "0.30", "9.70", 0), "pallet_number"),
        (roll("10.00", "0.30", "9.70", 1000), "pallet_number"),
        (roll("10.00", "0.30", "9.70", "7"), "pallet_number"),
        (roll("10.00", "0.30", "9.70", True), "pallet_number"),
    ],
)
def test_pallet_summary_rejects_unusable_saved_roll_data(entry, field_name):
    with pytest.raises(PalletSummaryDataError, match=field_name):
        build_terminal_pallet_summary([entry])
```

Because gross `NULL` means “not entered,” add a separate test proving a wholly unentered row is skipped and does not trigger validation of its other nullable fields.

- [ ] **Step 4: Run the new tests and confirm the intended red state**

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary.py -q
```

Expected: collection fails because `app.pallet_summary` does not exist. Do not weaken or skip the tests.

- [ ] **Step 5: Implement strict conversion and display helpers**

Use this logic in `app/pallet_summary.py`; error messages are internal diagnostics and must identify only the zero-based input index and field name:

```python
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

ONE_DECIMAL = Decimal("0.1")


class PalletSummaryDataError(ValueError):
    """A saved roll cannot be represented safely in a pallet summary."""


def _saved_weight(value: Any, *, field: str, index: int) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise PalletSummaryDataError(
            f"Roll entry {index} has invalid {field}."
        ) from None
    if not parsed.is_finite() or parsed < 0:
        raise PalletSummaryDataError(
            f"Roll entry {index} has invalid {field}."
        )
    return parsed


def _saved_pallet(value: Any, *, index: int) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 1 <= value <= 999:
        raise PalletSummaryDataError(
            f"Roll entry {index} has invalid pallet_number."
        )
    return value


def _weight_display(value: Decimal) -> str:
    return format(value.quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP), "f")
```

Do not import `app.db`, `app.main`, `app.printing`, Jinja, SQLite, or logging.

- [ ] **Step 6: Implement exact grouping and total construction**

Build buckets keyed by `int | None`. For every mapping with non-null gross: validate all four saved fields, require exact net equality, update the bucket and overall accumulators. Then sort integer keys and append `None` only if present:

```python
numbered = sorted(key for key in buckets if key is not None)
ordered_keys: list[int | None] = [*numbered]
if None in buckets:
    ordered_keys.append(None)
```

Use a single row-construction helper so group rows and the total share the same exact-value/display-value behavior. Return the exact shapes in **Final Python Interfaces**. If the entered-roll count is zero, return `empty` before building rows.

- [ ] **Step 7: Run the calculator tests green**

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary.py -q
```

Expected: all calculator tests pass.

**Review checkpoint:** Read the full new module. Confirm it is pure, catches only parse errors locally, never converts through float, validates every participating roll before returning a result, and has no print/database coupling. Do not stage or commit.

---

### Task 2: Selected-Card Context And Fail-Soft Boundary

**Files:**
- Modify: `tests/test_terminal_pallet_summary.py`
- Modify: `app/main.py:1-90` (imports/logger)
- Modify: `app/main.py:2600-2640` (`terminal_context()` selected-card enrichment)
- Add near `terminal_context()`: `attach_terminal_pallet_summary()`

**Consumes:** `fetch_terminal_card_detail()`, its already-attached `roll_entries`, and the pure calculator from Task 1.

**Produces:** Exactly one selected-card `pallet_summary` state; an optional-feature exception never prevents `/terminal` from rendering.

- [ ] **Step 1: Add focused context test setup**

In `tests/test_terminal_pallet_summary.py`, follow existing temp-database patterns from `tests/conftest.py` and `tests/test_terminal_v8_render.py`: import a release-ready card through public database helpers, release it to machine 1, start a shift only when roll-entry APIs require one, and render through `terminal_context(machine_id=1, selected_card_id=card_id)`. Keep all database paths supplied by the `db_path` fixture.

Add `test_terminal_context_attaches_ready_pallet_summary_from_fetched_rolls`, `test_terminal_context_attaches_empty_pallet_summary_for_no_rolls`, and `test_terminal_context_builds_only_the_selected_card_summary`. Each test receives the existing `db_path` fixture and any local card factory introduced at the top of this feature test module.

The selected-card test must monkeypatch `app.main.build_terminal_pallet_summary` with a spy, assert one call, and assert the argument is exactly the selected card's fetched roll list—not active queue summaries and not a second database read.

- [ ] **Step 2: Add the unexpected-exception containment test**

Use an exception message containing tempting data and prove the log stays minimal. Create the card with the same local release-ready card helper used by the context tests, assigning its returned integer ID to `card_id`, before this body:

```python
def test_terminal_context_contains_summary_failure_and_logs_card_id_only(
    db_path, monkeypatch, caplog
):
    card_id = create_released_test_card(
        db_path,
        order_number="PALLET-SUMMARY-ERROR",
        machine_id=1,
    )

    def explode(_roll_entries):
        secret_value = "secret-" + "order-content"
        raise RuntimeError(secret_value)

    monkeypatch.setattr("app.main.build_terminal_pallet_summary", explode)

    with caplog.at_level("ERROR", logger="app.main"):
        context = terminal_context(machine_id=1, selected_card_id=card_id)

    assert context["selected_card"]["pallet_summary"] == {
        "state": "error",
        "rows": [],
        "total": None,
    }
    record = next(
        record for record in caplog.records
        if "Terminal pallet summary failed" in record.getMessage()
    )
    assert f"card_id={card_id}" in record.getMessage()
    assert "secret-order-content" not in record.getMessage()
    assert "exception_type=RuntimeError" in record.getMessage()
```

Define `create_released_test_card()` in this test module by extracting only the release-ready CSV/import/release setup already used in `tests/test_terminal_v8_render.py`; it must use the supplied temporary `db_path` and return the created integer card ID.

- [ ] **Step 3: Prove the context tests fail for the missing integration**

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary.py -k 'terminal_context' -q
```

Expected: FAIL because the context has no `pallet_summary` and the calculator is not called.

- [ ] **Step 4: Add the narrow attachment helper**

At module scope in `app/main.py`, add `logger = logging.getLogger(__name__)`. Import `traceback` and the builder directly. Place this helper close to `terminal_context()`:

```python
def attach_terminal_pallet_summary(card: dict[str, Any]) -> None:
    try:
        card["pallet_summary"] = build_terminal_pallet_summary(
            card.get("roll_entries", [])
        )
    except Exception as error:
        logger.error(
            "Terminal pallet summary failed for card_id=%s "
            "exception_type=%s\n%s",
            card.get("id"),
            type(error).__name__,
            "".join(traceback.format_tb(error.__traceback__)),
        )
        card["pallet_summary"] = {
            "state": "error",
            "rows": [],
            "total": None,
        }
```

`traceback.format_tb()` preserves the diagnostic file/function/line stack without formatting the exception value, so an unexpected exception cannot place a customer, order, weight, or roll value from its message into the log. Do not use `logger.exception()` or pass `exc_info`, because both include the exception value. The broad `Exception` catch belongs only here. Do not wrap `terminal_context()`, card fetching, other enrichment, template rendering, or terminal routes.

- [ ] **Step 5: Attach the summary once during selected-card enrichment**

Inside the existing `if selected_card:` block in `terminal_context()`, call `attach_terminal_pallet_summary(selected_card)` after the roll data is fetched and before returning the context. Do not run the calculator for queue-card summaries and do not add a route or lazy request.

- [ ] **Step 6: Run focused context and calculator tests**

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary.py -q
```

Expected: PASS, including the error state and captured stack information.

**Review checkpoint:** Inspect `app/main.py` and confirm the exception boundary wraps only optional summary construction, logs only card ID in the message, and cannot change any fetched roll or card value. Do not stage or commit.

---

### Task 3: Read-Only Button, Modal, Table, And Responsive CSS

**Files:**
- Modify: `tests/test_terminal_pallet_summary.py`
- Modify: `app/templates/terminal.html:1912-1945` (secondary actions/CSS)
- Modify: `app/templates/terminal.html:4274-4305` (roll panel heading)
- Modify: `app/templates/terminal.html:4500-4555` (modal host, before rewinding overlay)

**Consumes:** `selected_card.pallet_summary`, existing `roll-secondary-actions`/`roll-secondary-button` styles, existing overlay visual language, and terminal-visible status handling.

**Produces:** Server-rendered, semantic, read-only modal contents for all three states and a button on every selected terminal-visible card.

- [ ] **Step 1: Add failing render tests for every visible card status and action order**

Create cards in statuses `pending`, `running`, `paused`, `awaiting_rewinding`, and `completed`; render each selected card. Assert exactly one `[data-pallet-summary-open]` button with text `Палети` per render. For running/paused/awaiting cards with a positive rewinding marker, inspect the heading action block and assert the text positions satisfy:

```python
assert actions.index("Пренавиване") < actions.index("Палети")
```

For pending and completed cards, assert the same right-aligned action wrapper contains `Палети` even though `Пренавиване` is absent. Keep the existing rewinding eligibility rules unchanged.

- [ ] **Step 2: Add failing semantic-table and state-message render tests**

Use BeautifulSoup if already available in the test dependencies; otherwise use the repository's existing HTML substring helpers without adding a package. Assert the ready state contains:

```text
Обобщение по палети
Поръчка №{order_number}
Палет
Брой ролки
Бруто, кг
Нето, кг
Общо
```

Assert all four header cells are `<th scope="col">`, grouped rows are in `<tbody>`, and `Общо` is a `<tfoot>` row. Verify numeric pallet order, `Без палет` last, exact one-decimal text, and a visually named total-row class or data hook.

Add separate renders asserting:

```text
Няма въведени ролки.
Обобщението по палети не може да бъде показано. Проверете данните за ролките.
```

For the error state, monkeypatch the calculator to raise and assert the terminal HTML still renders with the full selected card and the error modal body.

- [ ] **Step 3: Add failing read-only and future-default tests**

Restrict the HTML inspected to `#pallet-summary-overlay` and assert it contains no `<form>`, `<input>`, `<select>`, `<textarea>`, anchor, submit button, or data-changing route. Its only button must be `type="button"` with `data-pallet-summary-close` and text `Затвори`.

Set a non-null `current_pallet_number` on a card with no entered roll assigned to that pallet and prove its number is absent from the modal table.

- [ ] **Step 4: Prove the rendering tests fail for missing markup**

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary.py -k 'render or button or modal' -q
```

Expected: FAIL because the button and modal do not exist.

- [ ] **Step 5: Render the heading actions for every selected card**

Restructure the existing `Ролки` panel heading so `roll-secondary-actions` is always present when a selected card is shown. Keep the existing rewinding button inside its current status/marker condition, then append the summary button from **Final Browser Contract**. The summary button is neutral and contains no form attributes or URL.

- [ ] **Step 6: Render the modal once, immediately before the existing rewinding overlay**

Use Jinja branches only on the explicit state:

```jinja2
{% if selected_card.pallet_summary.state == "ready" %}
  <div class="pallet-summary-table-wrap" data-pallet-summary-scroll>
    <table class="pallet-summary-table">
      <thead>
        <tr>
          <th scope="col">Палет</th>
          <th scope="col">Брой ролки</th>
          <th scope="col">Бруто, кг</th>
          <th scope="col">Нето, кг</th>
        </tr>
      </thead>
      <tbody>
        {% for row in selected_card.pallet_summary.rows %}
          <tr>
            <th scope="row">{{ row.pallet_label }}</th>
            <td class="numeric">{{ row.roll_count }}</td>
            <td class="numeric">{{ row.gross_display }}</td>
            <td class="numeric">{{ row.net_display }}</td>
          </tr>
        {% endfor %}
      </tbody>
      <tfoot>
        <tr class="pallet-summary-total" data-pallet-summary-total>
          <th scope="row">Общо</th>
          <td class="numeric">{{ selected_card.pallet_summary.total.roll_count }}</td>
          <td class="numeric">{{ selected_card.pallet_summary.total.gross_display }}</td>
          <td class="numeric">{{ selected_card.pallet_summary.total.net_display }}</td>
        </tr>
      </tfoot>
    </table>
  </div>
{% elif selected_card.pallet_summary.state == "empty" %}
  <p data-pallet-summary-empty>Няма въведени ролки.</p>
{% else %}
  <p role="alert" data-pallet-summary-error>
    Обобщението по палети не може да бъде показано. Проверете данните за ролките.
  </p>
{% endif %}
```

The surrounding dialog contains the title, escaped `Поръчка №{{ selected_card.order_number }}`, and the one explicit close button. Render no raw Decimal value and no roll-level detail.

- [ ] **Step 7: Add focused responsive styles**

Use the existing terminal palette and spacing tokens where available. The overlay is fixed, shaded, and above ordinary drawers but does not need a new global z-index system. The dialog uses `width: min(42rem, calc(100vw - 2rem))`, a bounded viewport height, and a flex column; only `.pallet-summary-table-wrap` receives `overflow: auto`. Keep the title/context and close action outside that scrolling region. Right-align numeric headings/cells, use tabular numerals, make the total row visually distinct, and preserve a minimum touch target for `Затвори` and `Палети`.

At narrow widths, allow the table wrapper to scroll horizontally rather than collapsing or hiding a column. Do not use fixed pixel heights that work only at one required viewport.

- [ ] **Step 8: Run feature render tests and related existing terminal render tests**

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_pallet_summary.py \
  tests/test_terminal_v8_render.py \
  -q
```

Expected: PASS. Existing rewinding, roll-change, finish, and action-area markup tests remain unchanged or are updated only where their region boundaries legitimately include the new sibling modal.

**Review checkpoint:** Inspect the rendered modal region. Confirm one close button, no form/control that can write, autoescaped order context, correct table semantics, and no accidental dependency on current pallet default or print behavior. Do not stage or commit.

---

### Task 4: Existing Coordinator Integration And Stale Takeover

**Files:**
- Modify: `tests/test_terminal_pallet_summary.py`
- Modify: `app/templates/terminal.html:5290-5370` (background snapshot poll)
- Modify: `app/templates/terminal.html:5380-5913` (existing inline coordinator only)

**Consumes:** Existing queue/waiting/history/rewinding open-close functions, `setDrawerBackgroundIsolated()`, `focusableModalElements()`, `trapModalFocus()`, correction-control locking, `#terminal-refresh-alert-button`, and `terminal:shift-stale`.

**Produces:** One-owner modal behavior with focus safety, surface mutual exclusion, correction locking, and stale-card/shift takeover.

- [ ] **Step 1: Add failing source-contract tests**

Assert the rendered page source contains these hooks and that the HTML has only one summary trigger and one summary overlay. `terminal:card-stale` appears in one dispatch and one listener, while `terminal:shift-stale` retains its existing dispatch/listeners:

```text
data-pallet-summary-open
data-pallet-summary-overlay
data-pallet-summary-dialog
data-pallet-summary-close
terminal:card-stale
terminal:shift-stale
terminal-refresh-alert-button
```

Assert the existing `correctionBlockedControls` selector includes `[data-pallet-summary-open]`. Assert the `terminal:card-stale` dispatch occurs only in the selected-card signature-change branch after the existing reload alert is created/revealed; it must not fire on every polling interval.

- [ ] **Step 2: Add a minimal JavaScript behavior contract to the render tests**

The source assertions must prove the following explicit calls exist, without creating a second IIFE or manager:

```javascript
closePalletSummary(false); // stale takeover
setDrawerBackgroundIsolated(true, "pallet-summary");
trapModalFocus(event, palletSummaryDialog);
```

Also assert open functions for queue, waiting, history, and rewinding close the pallet summary, and the pallet open function closes each of those surfaces before opening itself.

- [ ] **Step 3: Prove the coordinator tests fail before implementation**

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary.py -k 'coordinator or stale or correction' -q
```

Expected: FAIL because the summary has no JavaScript owner and no card-stale event exists.

- [ ] **Step 4: Add modal references and state to the existing coordinator IIFE**

Cache the four hooks, plus a `palletSummaryReturnFocus` variable. Reuse the existing helpers; do not duplicate focusable-element selectors, background target lists, or keydown listeners.

Implement these semantics:

```javascript
function openPalletSummary(trigger) {
  if (!palletSummaryOverlay || correctionModeOpen || trigger.disabled) return;
  closeQueue(false);
  closeWaiting(false);
  closeHistory(false);
  closeRewinding(false);
  palletSummaryReturnFocus = trigger;
  palletSummaryOverlay.hidden = false;
  palletSummaryOverlay.setAttribute("aria-hidden", "false");
  trigger.setAttribute("aria-expanded", "true");
  setDrawerBackgroundIsolated(true, "pallet-summary");
  requestAnimationFrame(() => {
    (palletSummaryClose || palletSummaryDialog).focus();
  });
}

function closePalletSummary(restoreFocus = true) {
  if (!palletSummaryOverlay || palletSummaryOverlay.hidden) return;
  palletSummaryOverlay.hidden = true;
  palletSummaryOverlay.setAttribute("aria-hidden", "true");
  if (palletSummaryReturnFocus) {
    palletSummaryReturnFocus.setAttribute("aria-expanded", "false");
  }
  setDrawerBackgroundIsolated(false, "pallet-summary");
  if (restoreFocus && palletSummaryReturnFocus?.isConnected) {
    palletSummaryReturnFocus.focus();
  }
  palletSummaryReturnFocus = null;
}
```

These are the current coordinator function names and `setDrawerBackgroundIsolated(isolated, owner)` signature. Re-check them immediately before editing in case concurrent work changed the template; update the plan's direct calls to any renamed existing owner rather than adding compatibility wrappers.

- [ ] **Step 5: Connect open, explicit close, backdrop, Escape, and Tab**

Use delegated click handling if the coordinator already does so. Backdrop close only when `event.target === palletSummaryOverlay`. In the existing document keydown owner:

```javascript
if (!palletSummaryOverlay.hidden) {
  if (event.key === "Escape") {
    event.preventDefault();
    closePalletSummary(true);
    return;
  }
  if (event.key === "Tab") {
    trapModalFocus(event, palletSummaryDialog);
  }
}
```

Do not add another global keydown listener if the current coordinator already owns keyboard dismissal.

- [ ] **Step 6: Integrate mutual exclusion and correction locking**

Add `closePalletSummary(false)` at the start of every existing queue, waiting, history, and rewinding open path and before entering roll correction. Add `[data-pallet-summary-open]` to `correctionBlockedControls` so it is disabled while a correction row is open and re-enabled by the existing correction cleanup. Do not alter correction persistence.

Do not modify the separate finish-confirm or roll-change modules. While the summary is open, the existing `.main` background target is inert, so their triggers cannot activate. The manual shift trigger is inert for the same reason; the programmatic shift-stale takeover is handled explicitly in Step 7. Verify these non-stacking facts live rather than adding cross-module events.

- [ ] **Step 7: Emit and handle selected-card staleness**

In the existing card-signature-change branch, preserve the current signature update and reload alert, then emit once:

```javascript
showRefreshAlert();
document.dispatchEvent(new CustomEvent("terminal:card-stale"));
```

Listen in the coordinator:

```javascript
document.addEventListener("terminal:card-stale", () => {
  closePalletSummary(false);
  requestAnimationFrame(() => {
    document.getElementById("terminal-refresh-alert-button")?.focus();
  });
});

document.addEventListener("terminal:shift-stale", () => {
  closePalletSummary(false);
});
```

The card-stale handler must not refocus the stale `Палети` button. Preserve the existing alert text, reload action, and background polling cadence.

- [ ] **Step 8: Run feature and terminal JavaScript/render regressions**

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_pallet_summary.py \
  tests/test_terminal_v8_render.py \
  -q
```

Expected: PASS. This is source-level coverage only; live keyboard, focus, network, and stale behavior is verified in Task 6.

**Review checkpoint:** Follow every open and close path manually in source. Confirm a single coordinator owns background isolation and keyboard handling, no hidden overlay retains inert state, and stale takeover never restores focus to the stale card. Do not stage or commit.

---

### Task 5: Guarded Browser Fixture And Script Safety

**Files:**
- Create: `tests/test_terminal_pallet_summary_scripts.py`
- Create: `scripts/create_terminal_pallet_summary_fixture.py`
- Create: `scripts/verify_terminal_pallet_summary_ui.mjs`

**Consumes:** Safety patterns in `scripts/create_rewinding_fixture.py`, `scripts/verify_rewinding_ui.mjs`, and their tests; public application database operations; repository-local Playwright.

**Produces:** Deterministic temporary cards covering all UI states and a browser verifier that cannot target a runtime/production database accidentally.

- [ ] **Step 1: Add failing fixture safety tests**

Mirror the strict guards already exercised by `tests/test_rewinding_ui_script_safety.py`. Add tests that invoke the fixture script in subprocesses and assert:

- missing `--db-path` or `--output` fails;
- database/output outside `.test-runtime/` fails;
- a symlink resolving outside `.test-runtime/` fails;
- a valid unique directory under `.test-runtime/` succeeds;
- running twice recreates the same named scenarios without appending duplicates;
- no file under `data/` or `production-db/` changes.

The generated JSON must contain IDs and expected table rows for five named scenarios: `pending_empty`; `running_mixed` with pallets `2`, `10`, and `None` in deliberately unsorted input; `paused_all_unassigned`; `awaiting_many_pallets` with enough distinct pallets to require scrolling; and `completed_numbered`.

- [ ] **Step 2: Add failing static verifier-safety tests**

Assert the verifier requires nonblank `BASE_URL`, `FIXTURE_JSON`, and `ARTIFACT_DIR`; resolves the fixture below `.test-runtime/`; resolves artifacts below `artifacts/ui-checks/`; rejects symlink escapes; checks `/health` database identity before any request capable of mutation; imports only the repository-local `playwright`; and contains both required viewports:

```javascript
{ name: "desktop-1366", width: 1366, height: 768 }
{ name: "desktop-1920", width: 1920, height: 1080 }
```

Also require `node --check` to pass as part of the Python test.

- [ ] **Step 3: Prove the script tests fail because the scripts are absent**

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary_scripts.py -q
```

Expected: FAIL because neither script exists.

- [ ] **Step 4: Implement the guarded deterministic fixture**

Copy the path-resolution and symlink-rejection structure from `create_rewinding_fixture.py`; do not weaken it. The script may delete/recreate only the exact validated temporary database path. Initialize through application code, create a terminal shift when required, and use public card/roll operations so normal invariants and timestamps apply.

Build exact saved values that make browser assertions simple and prove numeric sorting, for example:

```text
running_mixed expected rows:
2          | 2 | 200.1 | 198.1
10         | 1 | 120.0 | 119.0
Без палет  | 1 |  80.0 |  79.0
Общо       | 4 | 400.1 | 396.1
```

Use saved per-roll tare/net values that satisfy every database rule. Give `awaiting_many_pallets` at least 24 distinct pallet numbers, within the 120-roll card bound, so the table must scroll at both viewports. Transition cards through real application operations to the desired statuses; do not patch status columns directly just to bypass lifecycle rules.

Write JSON only after all setup succeeds. Include the resolved database path, machine/card IDs, order numbers, scenario names, expected rows, expected totals, and a database snapshot baseline containing relevant card versions and production-row counts—never customer notes or other unrelated contents.

- [ ] **Step 5: Implement verifier startup and health guards**

Use `fs.realpathSync` and repository-root resolution as in existing verifiers. Before browser actions:

1. parse fixture JSON;
2. verify its database path equals the resolved `FIXTURE_JSON` fixture database;
3. request `/health`;
4. verify the returned database identity/path corresponds to the same temporary DB;
5. only then start scenario checks.

Capture console errors, page errors, failed requests, and unexpected dialogs. At the end, write a JSON summary beneath the validated artifact directory and fail if any captured error is unapproved.

- [ ] **Step 6: Encode the complete live-browser assertion matrix**

For both viewports, verify:

- every named status has one enabled `Палети` button;
- running action text order is `Пренавиване`, then `Палети`;
- modal open sets `hidden=false`, `aria-hidden=false`, trigger `aria-expanded=true`, and background terminal targets inert/ARIA-hidden;
- the title, order number, four headings, exact ordered rows, and exact footer total match fixture JSON;
- empty and error-free all-unassigned states show their intended content;
- explicit close, Escape, and true-backdrop click each close the modal and restore focus to the trigger;
- repeated Tab and Shift+Tab cannot move focus outside the dialog;
- opening queue, waiting, history, or rewinding closes the summary, and opening the summary closes any such available surface;
- entering roll-correction mode disables the summary trigger and leaving it re-enables the trigger;
- the many-pallet table wrapper has `scrollHeight > clientHeight`, while the title and close button remain visible and reachable;
- opening and closing makes no navigation, POST/PUT/PATCH/DELETE, or request whose pathname is specific to pallet summary; the existing periodic `/terminal/snapshot` GET is allowed;
- a before/after SQLite snapshot supplied by a read-only helper process has identical card versions, rolls, timing rows, current pallet, and assignments after modal-only interactions.

Save at least these screenshots per viewport:

```text
running-mixed-open.png
pending-empty-open.png
awaiting-many-scrolled.png
```

- [ ] **Step 7: Encode stale-card and shift-stale takeover**

Against the temporary fixture only, use a separate helper process to perform a legitimate external card-version change, wait for the existing poll interval, and assert the open summary closes, the existing refresh alert becomes visible, and `#terminal-refresh-alert-button` owns focus. The write is part of stale-simulation setup, not a modal action; record it separately from the modal non-mutation snapshot.

Then reload/reset the fixture, open the summary, and have a separate Python helper process call `fetch_active_shift()` followed by `update_active_shift_number(active_shift["id"], active_shift["version"], alternate_number)` against the same temporary database. Configure at least two shift numbers in the fixture so `alternate_number` is valid. Assert the next existing snapshot poll detects the changed shift signature, closes the summary, and gives the existing shift-stale reload surface focus. Do not add test-only application routes.

- [ ] **Step 8: Run script safety tests and syntax checks**

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary_scripts.py -q
.venv/bin/python -m compileall -q \
  scripts/create_terminal_pallet_summary_fixture.py
node --check scripts/verify_terminal_pallet_summary_ui.mjs
```

Expected: PASS, without starting the app and without touching runtime/production databases.

**Review checkpoint:** Resolve and inspect every path guard. Confirm browser checks cannot start against a mismatched database, fixture reset is limited to one validated temp path, and modal-only snapshots exclude the deliberate stale-simulation writes. Do not stage or commit.

---

### Task 6: Live UI Verification And Accessibility Evidence

**Files:**
- Exercise: `app/templates/terminal.html`, feature fixture, and verifier
- Generate untracked: `artifacts/ui-checks/terminal-pallet-summary/**`

**Consumes:** The completed feature and guarded scripts from Tasks 1–5.

**Produces:** Reproducible live-browser evidence for both required viewports, including focus, modal coordination, stale behavior, network silence, and database non-mutation.

- [ ] **Step 1: Create unique temporary and artifact directories**

```bash
mkdir -p .test-runtime/terminal-pallet-summary
mkdir -p artifacts/ui-checks/terminal-pallet-summary
```

These paths are intentionally narrow. Do not clear a parent directory.

- [ ] **Step 2: Generate the deterministic temporary database**

```bash
.venv/bin/python scripts/create_terminal_pallet_summary_fixture.py \
  --db-path .test-runtime/terminal-pallet-summary/fixture.sqlite3 \
  --output .test-runtime/terminal-pallet-summary/fixture.json
```

Expected: the script reports only the temp DB/JSON paths and named scenario IDs.

- [ ] **Step 3: Start the app against that exact database**

Run in a dedicated terminal/session and keep its process ID available for clean shutdown:

```bash
EXTRUSION_DB_PATH="$PWD/.test-runtime/terminal-pallet-summary/fixture.sqlite3" \
  .venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8012
```

Expected: startup identifies the temporary fixture database. If port `8012` is occupied, choose another loopback port and use the same port in `BASE_URL`; do not bind the verification server to LAN interfaces.

- [ ] **Step 4: Run the focused browser verifier**

```bash
BASE_URL="http://127.0.0.1:8012" \
FIXTURE_JSON="$PWD/.test-runtime/terminal-pallet-summary/fixture.json" \
ARTIFACT_DIR="$PWD/artifacts/ui-checks/terminal-pallet-summary" \
  node scripts/verify_terminal_pallet_summary_ui.mjs
```

Expected: PASS at `1366x768` and `1920x1080`; JSON summary reports zero unexpected console/page/request errors, exact table results, successful stale/shift takeover, no modal-specific request, and identical production snapshots for modal-only interactions.

- [ ] **Step 5: Inspect screenshots rather than relying only on assertions**

Open the saved screenshots with the available image viewer and inspect:

- button placement and `Пренавиване`/`Палети` order;
- no clipped title, order context, headings, totals, or close button;
- readable alignment and density;
- obvious but non-alarming empty state;
- table scroll containment with the dialog itself inside the viewport;
- visible keyboard focus styling.

If visual defects are found, add a failing render or verifier assertion where practical, fix the smallest CSS/markup behavior, and rerun Steps 2–5.

- [ ] **Step 6: Stop the dedicated verification server**

Send an ordinary interrupt to the exact uvicorn process/session started in Step 3. Do not kill unrelated Python processes.

**Review checkpoint:** Record the exact verifier command, artifact directory, viewports, and JSON outcome in the implementation note. Confirm all generated files are ignored/untracked and no runtime/production database timestamp changed. Do not stage or commit.

---

### Task 7: Guarded Production-Backup Compatibility Auditor

**Files:**
- Modify: `tests/test_terminal_pallet_summary_scripts.py`
- Create: `scripts/audit_terminal_pallet_summary_db.py`

**Consumes:** The pure calculator, an operator-created SQLite-safe backup copied to `.test-runtime/`, and the terminal-visible status set from `app.constants`.

**Produces:** A read-only rollout gate that reports only integrity status and `ready`/`empty`/`error` card counts without exposing business contents.

- [ ] **Step 1: Add failing auditor safety and output tests**

Create temporary databases in tests and assert:

- `--db-path` is required;
- input must resolve to a regular, non-symlink file under `.test-runtime/`;
- `data/extrusion_terminal.sqlite3`, `production-db/**`, and paths outside the repo temp root are rejected;
- the script connects read-only and leaves the input file's SHA-256 hash and modification time unchanged;
- failed `PRAGMA integrity_check` or nonempty `PRAGMA foreign_key_check` returns nonzero before summary calculation;
- valid data prints one JSON object with only `database`, `integrity`, `foreign_key_violations`, `visible_cards`, `ready`, `empty`, and `error` keys;
- malformed roll data increments `error`, produces a nonzero exit status, and never prints order number, customer, material, notes, roll weights, or exception contents.

- [ ] **Step 2: Prove the auditor tests fail because the script is absent**

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_pallet_summary_scripts.py \
  -k 'audit' \
  -q
```

Expected: FAIL because the audit script does not exist.

- [ ] **Step 3: Implement strict path and read-only connection guards**

Resolve repo root and `.test-runtime/`, reject symlinks and non-files, and open SQLite without initialization or migration:

```python
database_uri = f"file:{quote(str(database_path))}?mode=ro"
connection = sqlite3.connect(database_uri, uri=True)
connection.row_factory = sqlite3.Row
```

Use URL quoting suitable for filesystem paths. Do not import or call `db.init_db()`, backup creation, migrations, or any write helper. Set `PRAGMA query_only = ON` immediately after connecting.

- [ ] **Step 4: Audit integrity, foreign keys, and every terminal-visible card**

Run `PRAGMA integrity_check` and `PRAGMA foreign_key_check` first. Query only card IDs/statuses and saved summary fields for statuses in `TERMINAL_VISIBLE_STATUSES`. Group rolls by card ID in memory or fetch them per card; do not use customer/order fields.

For each card, call `build_terminal_pallet_summary(roll_entries)` and increment its returned state. Catch `Exception` per card only to increment `error`; do not print the exception or roll values. Print the minimal JSON result. Exit nonzero when integrity is not `ok`, foreign-key violations exist, or `error > 0`.

- [ ] **Step 5: Run auditor tests and syntax checks**

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary_scripts.py -q
.venv/bin/python -m compileall -q scripts/audit_terminal_pallet_summary_db.py
```

Expected: PASS, including unchanged file hashes/timestamps and redacted output.

**Review checkpoint:** Verify no code path can initialize, migrate, back up, update, or delete the input. Confirm the output does not disclose order/customer/material/roll contents and any error makes rollout fail. Do not stage or commit.

---

### Task 8: Durable Notes, Full Verification, And Adversarial Review

**Files:**
- Create: `docs/implementation-notes/terminal-pallet-summary.md`
- Review: every feature file and the full diff

**Consumes:** Completed code, automated evidence, live-browser evidence, and the guarded compatibility auditor.

**Produces:** Durable operational guidance and a completion report backed by fresh verification.

- [ ] **Step 1: Write the implementation note**

Document:

- the five terminal-visible statuses and button placement/order;
- exact `ready`/`empty`/`error` states and Bulgarian operator copy;
- participating-roll, pallet ordering, exact-decimal, net-consistency, and one-final-rounding rules;
- why the broad catch is intentionally limited to `attach_terminal_pallet_summary()`;
- why invalid rolls show an error instead of partial/recomputed totals;
- no schema/route/write/admin/print change;
- modal coordinator ownership, focus rules, card-stale and shift-stale takeover;
- temporary fixture and exact browser-verification command;
- production rollout procedure below and the rule that any `error` count blocks rollout.

- [ ] **Step 2: Run syntax/import and focused automated verification fresh**

```bash
.venv/bin/python -m compileall -q app tests \
  scripts/create_terminal_pallet_summary_fixture.py \
  scripts/audit_terminal_pallet_summary_db.py
node --check scripts/verify_terminal_pallet_summary_ui.mjs
.venv/bin/python -m pytest \
  tests/test_terminal_pallet_summary.py \
  tests/test_terminal_pallet_summary_scripts.py \
  tests/test_terminal_v8_render.py \
  -q
```

Expected: all commands exit zero.

- [ ] **Step 3: Run the full Python suite**

```bash
.venv/bin/python -m pytest
```

Expected: all tests pass using temporary databases; `data/extrusion_terminal.sqlite3` remains untouched.

- [ ] **Step 4: Rerun the complete live-browser check after the final code change**

Repeat Task 6 exactly, including both viewports, screenshots, error capture, stale-card and shift-stale takeover, allowed-network filtering, and before/after modal-only database snapshots. Evidence generated before the final code change is not sufficient.

- [ ] **Step 5: Run diff hygiene and scope checks**

```bash
git diff --check
git status --short
git diff --stat
git diff -- app/pallet_summary.py app/main.py app/templates/terminal.html \
  tests/test_terminal_pallet_summary.py \
  tests/test_terminal_pallet_summary_scripts.py \
  scripts/create_terminal_pallet_summary_fixture.py \
  scripts/verify_terminal_pallet_summary_ui.mjs \
  scripts/audit_terminal_pallet_summary_db.py \
  docs/implementation-notes/terminal-pallet-summary.md
```

Expected: only feature files plus already-recorded unrelated user/concurrent changes appear; no migration, schema, print, admin, dependency, generated artifact, database, staging, or commit change is present.

- [ ] **Step 6: Perform the adversarial senior review**

Review against these failure questions and fix any real gap with a new failing test first:

- Can malformed data still escape the narrow boundary and return HTTP 500?
- Can malformed data yield a partial or plausible wrong total?
- Can a numeric string, bool, zero, or out-of-range pallet bypass validation?
- Can rounding happen per roll or through binary float before aggregation?
- Can `Без палет` disappear for all-unassigned cards or sort before numeric pallets?
- Can the current future-roll pallet default create a phantom row?
- Can the modal cause a request or write, including a hidden form submit?
- Can two terminal drawers/modals remain active, or can correction/finish/shift/roll-change stack with it?
- Can background isolation or focus remain stuck after any close path?
- Can card-stale restore focus to stale UI instead of the reload action?
- Can a long table hide the title or only close button?
- Can logs or audit output disclose order/customer/roll contents?
- Can any automated or rollout check open a live/production database for writing?

- [ ] **Step 7: Run the pre-rollout compatibility gate on the newest safe backup copy**

This is an operational step immediately before deployment, not an automated test. First create the normal SQLite-safe backup using the repository's documented backup procedure. Then copy that completed backup to this narrow temp path—never copy the live SQLite file directly while the app may be running:

```bash
mkdir -p .test-runtime/terminal-pallet-summary-rollout
cp --no-clobber \
  /absolute/path/to/newest/sqlite-safe-backup.sqlite3 \
  .test-runtime/terminal-pallet-summary-rollout/production-backup.sqlite3
.venv/bin/python scripts/audit_terminal_pallet_summary_db.py \
  --db-path .test-runtime/terminal-pallet-summary-rollout/production-backup.sqlite3
```

Expected: integrity `ok`, zero foreign-key violations, `visible_cards == ready + empty + error`, and `error == 0`. The report contains counts only. Any error blocks rollout until the affected saved-roll invariant is understood and corrected through an approved production-data procedure; do not waive it merely because the page fails softly.

- [ ] **Step 8: Prepare the completion handoff without staging**

Report the files changed, focused/full test results, live-browser result and screenshot directory, rollout-auditor result if run, and any remaining operational step. Explicitly state that nothing was staged or committed. Do not ask the business user to approve architecture already resolved in the design; surface only genuine business-impacting deviations or blockers.

**Review checkpoint:** The feature is complete only after fresh automated and live evidence passes and the adversarial checklist finds no unresolved correctness, safety, accessibility, or scope issue. No staging or commit without a separate explicit user request.

---

## Spec Coverage Self-Review

| Approved requirement | Planned implementation/evidence |
| --- | --- |
| Button on every visible card; right of rewinding | Task 3 render tests and markup; Task 6 live checks |
| Four columns, order context, total, empty message | Task 3 semantic render tests; Task 6 screenshots |
| Numeric sort; `Без палет` always when needed and last | Task 1 exact grouping tests; Task 3/6 rendering checks |
| Exact Decimal sums and final one-decimal `ROUND_HALF_UP` | Task 1 boundary tests and pure implementation |
| Current pallet does not create a row | Task 1 and Task 3 regression tests |
| Read-only/no schema/route/print/admin change | Global constraints; Tasks 3, 5, and 8 scope/non-mutation checks |
| Malformed data cannot crash terminal or yield false totals | Tasks 1–2 validation, boundary, logging, and HTTP/render evidence |
| No modal-specific request | Task 5 verifier request capture |
| Focus trap/return, Escape/backdrop/close, background isolation | Tasks 4 and 6 |
| One terminal surface and correction/overlay locking | Tasks 4 and 6 |
| Card-stale and shift-stale takeover | Tasks 4–6 |
| Long-table usability at 1366x768 and 1920x1080 | Tasks 3, 5, and 6 |
| Temporary DB browser testing and screenshots | Tasks 5–6 |
| Full verification and adversarial review | Task 8 |
| Newest-backup compatibility gate with redacted counts | Tasks 7–8 |

No placeholder interfaces, deferred architectural choices, schema changes, print rules, admin behavior, or implementation commits are part of this plan.
