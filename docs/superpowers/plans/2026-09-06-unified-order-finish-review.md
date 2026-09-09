# Unified Order-Finish Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two visually different Terminal finish confirmations with the approved common production-summary modal, while preserving editable tokenized timing only on the initial extrusion finish and showing a real `0.0` physical pallet-weight placeholder that a later task can connect to persisted input.

**Architecture:** Keep the existing lifecycle and timing transactions unchanged. Extend the existing pallet-summary view model with a non-persistent physical pallet-weight field, build one server-side finish-review presentation model for the three lifecycle variants, render one shared Jinja modal, retain `timing_interval_editor.mjs` as the controller for active-card reviews, and add a small waiting-only controller for tokenless read-only finalization. The status and `rewinding_roll_count` select presentation copy; the existing backend operations remain authoritative.

**Tech Stack:** FastAPI, Jinja, direct `sqlite3`, Python `Decimal`, plain JavaScript ES modules, pytest, repository-local Playwright, and the existing Segoe UI/Terminal style tokens.

**Spec:** `v2-files/archive/TASK-21-ORDER-FINISH-REVIEW.md`

**Approved visual reference:** `ui-prototypes/caa68a9d-3f9f-4fcc-a0b6-a617ffc4f564.png`

## Global Constraints

- Do not add or reinterpret persistent data. This implementation requires no schema change or migration.
- `Тегло палет, кг` is physical pallet weight, not roll-core tare. It is a `Decimal("0")` / `"0.0"` presentation placeholder in this task and is never written to SQLite.
- Do not change the current net formula. Net remains the sum of saved per-roll `gross_weight - tare_weight`, where tare is `Шпула, кг`.
- Do not create another finish route, timing editor, review token, pallet aggregator, or database transaction.
- Running/paused reviews retain the existing authenticated frozen stop, editable complete timing draft, and atomic `finish_card_with_timing_ledger` operation.
- Awaiting-rewinding reviews remain tokenless and call only `finalize_awaiting_rewinding_card`; they never mutate timing or `finished_at`.
- Use card status plus a positive `rewinding_roll_count` to select the lifecycle variant. Do not use `rewinding_slitting_sequence` or other imported text as the trigger.
- Preserve the current active-shift, version, stale-write, roll/tare/net, gap-free roll sequence, mixed-pallet warning, final-shift, machine-reuse, and queue-normalization rules.
- Keep all visible copy Bulgarian. Reuse the existing Bulgarian Task 22 interval editor rather than the standalone prototype's native datetime inputs.
- Match the approved common layout. Do not reintroduce the old visible overall title, a horizontal order strip, a second confirmation modal, summary metrics, or row actions.
- Never test against `data/extrusion_terminal.sqlite3`. Browser fixtures and outputs must remain under `.test-runtime/` and `artifacts/ui-checks/order-finish-review/`.
- Preserve the user's unrelated untracked files. Do not stage or commit without explicit user permission; the review checkpoints below replace the writing skill's normal commit checkpoints.

## Final Presentation Contract

The server-side `terminal_finish_review` presentation model must have this
stable shape:

```python
{
    "mode": "complete" | "enter_rewinding" | "finalize_rewinding",
    "open": bool,
    "time_editable": bool,
    "requires_review_token": bool,
    "confirm_label": str,
    "outcome_message": str,
    "warning_message": str,
    "locked": bool,
    "reload_required": bool,
    "can_confirm": bool,
    "messages": list[str],
    "product_display": str,
    "rewinding_count_label": str,
    "timing_display": {
        "first_start_display": str,
        "proposed_stop_display": str,
        "production_seconds": int,
        "paused_seconds": int,
    },
}
```

For active cards, the opening JSON response remains the authoritative timing
source and replaces the four rendered timing values. The existing
`data-terminal-timing-model.finish_review` object continues to own transient
review token/draft/error hydration; it must not duplicate the common order,
table, or lifecycle presentation fields. For waiting cards, `timing_display`
comes only from stored closed timing segments. Presentation helpers may add
preformatted boundary/duration strings to this model, but they must not replace
or recompute the authoritative integer seconds.

The pallet-summary contract gains these fields on every ready row and total:

```python
{
    "pallet_weight": Decimal("0"),
    "pallet_weight_display": "0.0",
}
```

The empty state gains an explicit zero total using the same summary-row shape. The error state keeps `total=None` and must never masquerade as a zero result.

---

### Task 1: Add the physical pallet-weight presentation seam

**Files:**

- Modify: `tests/test_terminal_pallet_summary.py`
- Modify: `app/pallet_summary.py`

- [ ] **Step 1: Write exact failing view-model tests**

Extend `test_pallet_summary_groups_one_numbered_pallet_and_builds_total` so both the pallet row and total require:

```python
"pallet_weight": Decimal("0"),
"pallet_weight_display": "0.0",
```

Change `test_pallet_summary_is_empty_when_no_gross_roll_is_entered` to require a zero total rather than `None`:

```python
assert summary == {
    "state": "empty",
    "rows": [],
    "total": {
        "roll_count": 0,
        "gross_weight": Decimal("0"),
        "net_weight": Decimal("0"),
        "pallet_weight": Decimal("0"),
        "gross_display": "0.0",
        "net_display": "0.0",
        "pallet_weight_display": "0.0",
    },
}
```

Add `test_pallet_weight_placeholder_does_not_change_existing_net_calculation`. Use a gross value of `10.00` and roll-core tare of `0.30`; assert net is still `9.70` while physical pallet weight is `0`.

- [ ] **Step 2: Run the focused tests and observe the intended failures**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary.py -q
```

Expected: only the new placeholder/empty-total assertions fail; existing exact-decimal and validation tests continue to pass.

- [ ] **Step 3: Implement one non-persistent placeholder source**

In `app/pallet_summary.py`, define the physical-pallet placeholder beside the existing exact zero:

```python
PALLET_WEIGHT_PLACEHOLDER: ExactDecimal = ZERO
```

Give `_summary_row` a `pallet_weight: ExactDecimal =
PALLET_WEIGHT_PLACEHOLDER` keyword, convert it through the same exact-decimal
and one-decimal display helpers as the other weights, and emit both stable
fields. This leaves a direct parameter seam for the later task without
inventing a persistence source now.

Return `_summary_row(roll_count=0, gross_weight=ZERO, net_weight=ZERO)` as the
empty state's `total`. Do not read roll tare into this field and do not add the
field to a database query.

- [ ] **Step 4: Update every exact-dictionary expectation**

Search for exact pallet-summary dictionaries and update only affected view-model expectations:

```bash
rg -n '"state": "empty"|"gross_display"|"net_display"' tests/test_terminal_pallet_summary.py tests/test_terminal_v8_render.py
```

Keep `attach_terminal_pallet_summary`'s error fallback at `total=None`; this distinguishes invalid data from a legitimate empty order.

- [ ] **Step 5: Re-run the focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_pallet_summary.py -q
```

Expected: pass.

- [ ] **Step 6: Review checkpoint**

Inspect `git diff -- app/pallet_summary.py tests/test_terminal_pallet_summary.py`. Confirm there is no SQL, migration, stored field, tare alias, or net-weight change.

---

### Task 2: Build and test the unified server presentation model

**Files:**

- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_rewinding_workflow.py`
- Modify: `app/main.py`

- [ ] **Step 1: Add failing pure presentation-model tests**

Add tests around a new `build_terminal_finish_review_model` helper covering these exact cases:

| Card state | Marker | `mode` | Editable | Token required | Primary label |
| --- | ---: | --- | --- | --- | --- |
| `running` | `None`/`0` | `complete` | yes | yes | `Потвърди приключване` |
| `paused` | `4` | `enter_rewinding` | yes | yes | `Потвърди край на екструдирането` |
| `awaiting_rewinding` | `4` | `finalize_rewinding` | no | no | `Потвърди приключване` |
| `awaiting_rewinding` | `0` | `finalize_rewinding` | no | no | `Потвърди приключване` |

Also assert:

- `1` formats as `1 ролка`; `2` and `0` use the correct plural/blank behavior.
- Active marked outcome is `След потвърждение: Изчаква пренавиване · 4 ролки`.
- Waiting outcome remains `Изчаква пренавиване` even if the marker was cleared.
- `product_type="Термо фолио"` and `size_thickness="420 × 0.060 мм"` become `Термо фолио 420 × 0.060 мм` without changing `0.060`.
- A missing product part does not create duplicate spaces; both missing render `—`.
- A non-finishable status such as `completed` returns no model unless an explicit locked recovery mode is supplied.
- A card whose imported `rewinding_slitting_sequence` is nonblank but whose marker is zero remains `complete`.

- [ ] **Step 2: Add failing stored-time tests for waiting cards**

In `tests/test_rewinding_workflow.py`, create an `awaiting_rewinding` card with multiple closed productive intervals and a gap. Assert the model shows:

- the first stored start;
- the last stored extrusion end, not current server time;
- productive seconds equal to the sum of closed intervals; and
- paused seconds equal to the gaps exactly once.

Assert boundary presentation is `DD/MM/YY HH:mm` and has no seconds. Assert both durations are exposed as integer seconds and format to hours/minutes without seconds.

- [ ] **Step 3: Run the new tests and observe failure**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py \
  tests/test_rewinding_workflow.py -q
```

Expected: failures report the missing unified model/helper contracts.

- [ ] **Step 4: Implement narrow formatting and variant helpers**

Add small, explicit helpers in `app/main.py` near the existing Terminal timing presentation helpers:

```python
def terminal_finish_boundary_display(value: str | None) -> str:
    match = re.fullmatch(
        r"(\d{2})\.(\d{2})\.(\d{4}) (\d{2}:\d{2})",
        str(value or ""),
    )
    if match is None:
        return str(value or "—")
    day, month, year, clock = match.groups()
    return f"{day}/{month}/{year[-2:]} {clock}"


def terminal_finish_duration_display(total_seconds: int) -> str:
    hours, remainder = divmod(max(total_seconds, 0), 3600)
    minutes = remainder // 60
    return f"{hours} ч {minutes:02d} м" if hours else f"{minutes} м"


def terminal_rewinding_count_label(value: Any) -> str:
    count = int(value or 0)
    if count <= 0:
        return ""
    return f"{count} {'ролка' if count == 1 else 'ролки'}"


def terminal_finish_product_display(card: dict[str, Any]) -> str:
    parts = [str(card.get(name) or "").strip()
             for name in ("product_type", "size_thickness")]
    return " ".join(part for part in parts if part) or "—"
```

Use existing time-zone functions; do not parse timestamps in browser local time and do not change the ordinary timing editor's `DD.MM.YYYY` inputs.

- [ ] **Step 5: Implement `build_terminal_finish_review_model`**

Accept the selected card, current server time, requested open/locked/messages state, and an optional recovery mode. Derive the mode table above. For `finalize_rewinding`, call `terminal_timing_display_from_stored_card`; because the status is not running, its proposed stop is the last stored segment end.

Copy the existing mixed-pallet question into `warning_message` only when it is not the generic question. Do not recalculate the warning or pallet totals in this helper.

Set `can_confirm` false for a pallet-summary error or a locked stale/unavailable
recovery. A legitimate empty summary remains confirmable at the presentation
layer because the existing backend decides whether the selected lifecycle
outcome permits zero rolls.

- [ ] **Step 6: Attach the model once in `terminal_context`**

Build `terminal_finish_review` after `selected_card` has been enriched and after the current server time is available. Pass it to the template as a separate key; do not overload `terminal_timing` to pretend that waiting cards are editable.

Retain the existing `terminal_timing` model unchanged for running/paused timing editing and stale Task 22 recovery.

- [ ] **Step 7: Re-run focused tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py \
  tests/test_rewinding_workflow.py -q
```

Expected: new presentation tests pass without changing lifecycle tests.

- [ ] **Step 8: Review checkpoint**

Inspect the model diff. Confirm only status and the saved informational marker select variants, waiting time never uses `now` as its finish, and no helper performs a write.

---

### Task 3: Render the approved common modal and table

**Files:**

- Create: `app/static/images/terminal-ui/finish-review-close.svg`
- Create: `app/static/images/terminal-ui/finish-review-factory.svg`
- Create: `app/static/images/terminal-ui/finish-review-clock.svg`
- Create: `app/static/images/terminal-ui/finish-review-clipboard-list.svg`
- Create: `app/static/images/terminal-ui/finish-review-pencil.svg`
- Modify: `app/templates/terminal.html`
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Replace old render assertions with failing approved-layout assertions**

Update the focused finish-review render test so it requires:

- one `data-finish-review-overlay` for active and waiting cards;
- `aria-label="Преглед преди приключване на производствена поръчка"` and no visible overall title;
- a close button labelled `Затвори прегледа`;
- three cards headed exactly `Детайли на поръчката`, `Производствено време`, and `Произведена продукция`;
- order rows `Машина`, `Поръчка №`, `Клиент`, and `Продукт` in that order;
- time rows `Начало`, `Край`, `Произв. време`, and `Паузирано време` in that order;
- `Редактирай` plus a pencil only for active cards;
- one five-column `colgroup` and the exact heading `Тегло палет, кг`;
- row and total values from `pallet_weight_display`, both equal to `0.0`;
- an empty table body message plus zero total for the active marked/no-roll state;
- a full-width footer with `Отказ` immediately before the correct primary action; and
- no old `finish-confirm-modal` for waiting finalization.

Delete assertions for the old visible title, horizontal timing strip, dash pallet weights, `Редактирай времето`, and the waiting `Да`/`Не` modal.

- [ ] **Step 2: Run the render tests and observe failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_v8_render.py -q
```

Expected: the new common-layout assertions fail against the old markup.

- [ ] **Step 3: Add durable Lucide-family SVG assets**

Copy the approved Lucide path data from
`artifacts/ui-checks/task-21-operator-prototype/icons/` into the five durable
`app/static/images/terminal-ui/finish-review-*.svg` files. Keep identical
24×24 view boxes, two-pixel rounded strokes, and the approved navy/blue colors.
Do not make runtime source depend on `artifacts/`.

- [ ] **Step 4: Move the finish-review shell outside the active-timing-only condition**

Keep the timing editor and timing JSON under `{% if terminal_timing %}`, but render the common finish-review modal whenever `terminal_finish_review` exists. This makes the same shell available to `awaiting_rewinding` without creating a fake editable timing model.

Remove the old standalone `#finish-confirm-modal` once no finish form references it. Do not disturb roll-delete confirmation markup, which merely shares some legacy class names.

- [ ] **Step 5: Implement the three-card content**

Use semantic `<section>`, `<header>`, and `<dl>` structures from the approved prototype. Render the product through `terminal_finish_review.product_display`. Use identical row markup and CSS for order and time values so the customer/product and all four time values share vertical centering and typography.

Render the edit button only when `time_editable` is true:

```jinja2
{% if terminal_finish_review.time_editable %}
  <button type="button" data-finish-review-edit
          aria-label="Редактирай производственото време">
    ...
    <span>Редактирай</span>
  </button>
{% endif %}
```

- [ ] **Step 6: Implement the fixed-header/fixed-total table**

Use `table-layout: fixed`, a five-column `<colgroup>`, and `width: 20%` for every column. Center `th` and `td` uniformly. Put vertical scrolling on the table wrapper, use `scrollbar-gutter: stable`, make `thead` sticky at `top: 0`, and make `tfoot` sticky at `bottom: 0`.

Render `row.pallet_weight_display` and `total.pallet_weight_display`; never use a literal dash. The empty state remains inside the table body and the zero total remains visible. The error state spans all five body columns, omits misleading totals, and marks the confirmation unavailable.

- [ ] **Step 7: Port only the accepted prototype CSS**

Replace the existing `.finish-review-*` rules with the approved geometry:

- modal maximum `calc(100vw - 28px)` / `calc(100vh - 28px)`;
- compact top bar reserved for close;
- `2fr 3fr` card columns and an 18px gap;
- stacked left cards with the right card spanning their total height;
- matching icon tiles and card padding;
- `Segoe UI`, existing Cyrillic fallbacks, and `font-variant-numeric: tabular-nums`;
- shared label/value sizes and weights;
- full-width restrained footer with right-grouped actions; and
- a `max-height: 820px` density adjustment that reduces space and visible rows without reducing legibility.

Do not copy prototype-only page background, mock editor, result message, or JavaScript.

- [ ] **Step 8: Re-run render tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_v8_render.py -q
```

Expected: common markup and copy assertions pass.

- [ ] **Step 9: Review checkpoint**

Render active, marked-active, and waiting HTML fixtures. Confirm there is exactly one review modal per page, the edit button is absent—not disabled—in waiting mode, and the template does not infer or calculate pallet weight.

---

### Task 4: Adapt the existing active-card timing controller to the new shell

**Files:**

- Modify: `app/static/js/timing_interval_editor.mjs`
- Modify: `app/static/js/timing_interval_editor_core.mjs`
- Modify: `tests/js/timing_interval_editor_core.test.mjs`
- Modify: `tests/test_terminal_timing_correction.py`
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_terminal_sync.py`

- [ ] **Step 1: Add failing behavior assertions for active reviews**

Cover:

- active Finish still calls `/finish-review` before native finish submission;
- the frozen preview populates all four approved time rows;
- boundary formatting remains `DD/MM/YY HH:mm` and duration formatting has no seconds;
- `Редактирай` opens the existing interval editor in finish mode;
- accepted edits return to the common summary with recalculated authoritative totals;
- close, `Отказ`, and Escape write nothing and restore focus to `Приключи`;
- backdrop clicks do not close the review;
- initial focus goes to the dialog or `Отказ`, never the red confirmation action;
- mixed-pallet warning appears in the footer message region and remains non-blocking;
- the marked active variant keeps the accurate outcome text and primary label;
- duplicate confirmation is blocked while submission is pending; and
- card-stale and shift-stale events retain the existing safe lock/suspend behavior.

- [ ] **Step 2: Run JS and active timing tests and observe failures**

Run:

```bash
node --test tests/js/timing_interval_editor_core.test.mjs
.venv/bin/python -m pytest \
  tests/test_terminal_timing_correction.py \
  tests/test_terminal_sync.py \
  tests/test_terminal_v8_render.py -q
```

- [ ] **Step 3: Add one tested active-review duration formatter**

Export `formatFinishDuration` from `timing_interval_editor_core.mjs`, leaving
the ordinary timing editor's existing row/total formatter unchanged. Cover
invalid input, zero, minute-only, and hour-plus-minute values:

```javascript
formatFinishDuration(0) === "0 м";
formatFinishDuration(15 * 60) === "15 м";
formatFinishDuration((2 * 60 + 3) * 60) === "2 ч 03 м";
```

Use it for both finish-review durations. Keep `formatFinishBoundary` as the
sole browser conversion from the server's Sofia display form to
`DD/MM/YY HH:mm`. Task 2's Python formatter must produce the same text for
server-rendered waiting values.

- [ ] **Step 4: Retarget selectors without weakening the active guard**

Add the new close control and footer message elements to the active controller. Active pages still render `data-finish-review-edit`, so the existing initialization guard may continue to require it. Waiting pages are handled by the separate controller in Task 5 and must not initialize editable timing.

- [ ] **Step 5: Preserve review-token submission exactly**

Keep the existing hidden `review_token`, serialized complete `timing_draft`, retained preview, `finishNativeSubmit`, and `requestSubmit()` path. Do not place the review confirmation in a separate POST form or create a second token.

While submitting, disable close, cancel, edit, and confirm; set `aria-busy`; and refuse all duplicate calls. On an ordinary browser-side close, clear only transient review state and never submit.

- [ ] **Step 6: Preserve error hydration and stale locks in the new message region**

Continue reopening an active review after backend validation failure. Validation failures that require order correction keep the operator in the review with an explanation and disabled confirmation; close/cancel returns to the card for correction. Stale failures expose the existing reload action and never submit the retained token again.

- [ ] **Step 7: Re-run focused active tests**

Run:

```bash
node --test tests/js/timing_interval_editor_core.test.mjs
.venv/bin/python -m pytest \
  tests/test_terminal_timing_correction.py \
  tests/test_terminal_sync.py \
  tests/test_terminal_v8_render.py -q
```

Expected: pass.

- [ ] **Step 8: Review checkpoint**

Inspect the active submit path from the visible `Приключи` form through preview, optional edit, and final POST. Confirm the visual rewrite did not change token verification, frozen time, version binding, atomic ledger mutation, or failure recovery.

---

### Task 5: Replace waiting finalization's simple confirm with the read-only common review

**Files:**

- Create: `app/static/js/waiting_finish_review.mjs`
- Modify: `app/templates/terminal.html`
- Modify: `app/main.py`
- Modify: `tests/test_rewinding_workflow.py`
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_terminal_sync.py`

- [ ] **Step 1: Add failing waiting-controller render and workflow tests**

Require the waiting `Приключи` form to use `data-waiting-finish-review="true"`, retain only `loaded_version`, and contain no review token or timing draft.

Test waiting cards with positive and cleared markers. Both open the common modal; neither renders `data-finish-review-edit`. Positive marker copy includes its count, while cleared-marker copy still identifies `Изчаква пренавиване`.

- [ ] **Step 2: Add failing finalization-failure recovery tests**

Exercise a waiting card with no returned gross roll. POST finalization must return HTTP 200, retain the validation message, set the waiting review to `open`, leave status/timing/`finished_at` unchanged, and provide a way to dismiss the review and correct the card.

Exercise a stale waiting version. Require a locked review/reload state when the card remains recoverable. If the card disappeared entirely from Terminal visibility, require the existing top-level unavailable message and no unsafe confirm control.

- [ ] **Step 3: Run waiting-focused tests and observe failure**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_rewinding_workflow.py \
  tests/test_terminal_v8_render.py \
  tests/test_terminal_sync.py -q
```

- [ ] **Step 4: Preserve waiting mode across a failed POST**

In `finish_terminal_card`, capture whether the submitted operation entered through the waiting path before calling finalization. Pass an explicit recovery mode/open flag to `terminal_post_response` when that operation fails. Extend `terminal_context` recovery lookup only as needed to show a locked current snapshot; never reinterpret a changed card as eligible to finalize.

Do not accept or validate `review_token`, `timing_draft`, or `finish_review_preview` on the waiting branch. Existing regression coverage that passes malformed values must continue to prove they are irrelevant and that finalization remains timing-neutral.

- [ ] **Step 5: Implement the waiting-only modal controller**

`waiting_finish_review.mjs` must:

- intercept only `form[data-waiting-finish-review="true"]`;
- open the already-rendered common modal without a network request;
- isolate the Terminal background, trap focus, and focus the dialog or `Отказ`;
- close on `×`, `Отказ`, or Escape with no submission;
- ignore backdrop clicks;
- submit the original waiting form exactly once from the common confirm button;
- disable all review actions and set `aria-busy` while submitting;
- restore focus to `Приключи` after cancellation;
- open automatically when the server model says `open` after failure; and
- lock/suspend on `terminal:card-stale` and `terminal:shift-stale` consistently with existing controllers.

This module must not import or invoke the timing editor and must never create a token or draft field.

- [ ] **Step 6: Delete the obsolete generic waiting confirmation controller**

Remove the inline controller that queries `form[data-finish-confirm-form="true"]` and the obsolete `Да`/`Не` modal. Verify no remaining selector depends on them:

```bash
rg -n 'data-finish-confirm-form|data-finish-confirm-modal|data-finish-confirm-submit' app tests
```

Expected after test updates: no waiting-finish dependency remains. Roll-delete dialog selectors remain untouched.

- [ ] **Step 7: Re-run waiting-focused tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_rewinding_workflow.py \
  tests/test_terminal_v8_render.py \
  tests/test_terminal_sync.py -q
```

Expected: pass, including unchanged waiting timing and `finished_at` assertions.

- [ ] **Step 8: Review checkpoint**

Trace both final POST branches. Confirm active requests still require a verified token and complete draft, while waiting requests remain loaded-version-only and call only `finalize_awaiting_rewinding_card`.

---

### Task 6: Lock all lifecycle, empty/error, and calculation regressions

**Files:**

- Modify: `tests/test_finish_cancel_history.py`
- Modify: `tests/test_rewinding_workflow.py`
- Modify: `tests/test_terminal_timing_correction.py`
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_terminal_pallet_summary.py`

- [ ] **Step 1: Add the three end-to-end route variants**

Test through the real route functions:

1. running, zero marker, valid roll → tokenized review → `completed`;
2. paused, positive marker, zero rolls → tokenized review → `awaiting_rewinding`;
3. awaiting with returned valid rolls → read-only review → `completed` with byte-for-byte-equivalent timing rows and unchanged `finished_at`.

- [ ] **Step 2: Add invariant regressions around the review wrapper**

Cover active-shift loss, stale loaded version, malformed/expired active token, changed status between opening and confirmation, missing roll, invalid tare/net, roll gaps, mixed pallets, and duplicate submission. Assert errors remain Bulgarian and no failed operation partially mutates card, queue, timing, rolls, version, or final-shift attribution.

- [ ] **Step 3: Add placeholder-specific calculation regressions**

For multiple pallets and unassigned rolls, assert:

- all row physical pallet weights are `0.0`;
- total physical pallet weight is `0.0`;
- gross/net totals equal the pre-feature values;
- product `0.060` is not rounded to `0.1`; and
- summary totals include all rows, not only those visible in a scrolled table.

- [ ] **Step 4: Run the complete focused group**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_pallet_summary.py \
  tests/test_terminal_timing_correction.py \
  tests/test_finish_cancel_history.py \
  tests/test_rewinding_workflow.py \
  tests/test_terminal_v8_render.py \
  tests/test_terminal_sync.py -q
node --test tests/js/timing_interval_editor_core.test.mjs
```

Expected: pass.

- [ ] **Step 5: Review checkpoint**

Read the final route and model diff, not only the tests. Confirm no test fixture has accidentally relaxed a backend validation and no placeholder has entered stored application state.

---

### Task 7: Build task-specific safe Playwright verification

**Files:**

- Create: `scripts/create_order_finish_review_fixture.py`
- Create: `scripts/verify_order_finish_review_ui.mjs`
- Create: `tests/test_order_finish_review_ui_script_safety.py`

- [ ] **Step 1: Write failing script-safety tests**

Follow the existing timing and rewinding verifier safety pattern. Require the fixture to reject:

- `data/extrusion_terminal.sqlite3`;
- a database path outside `.test-runtime/`;
- an output JSON path outside `.test-runtime/`;
- symlink escapes; and
- a pre-existing directory where a regular file is expected.

Require the verifier to reject a health response whose exact resolved database path differs from the fixture and to reject artifact output outside `artifacts/ui-checks/`.

- [ ] **Step 2: Run the safety test and observe failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_order_finish_review_ui_script_safety.py -q
```

- [ ] **Step 3: Create a deterministic fixture with all visual states**

Create cards for:

- active normal completion with long but realistic customer/product data and enough pallets to scroll;
- active marked completion with zero rolls;
- active marked completion with mixed assigned/unassigned rolls;
- waiting finalization with returned rolls across at least twelve pallet groups;
- waiting finalization with a cleared marker; and
- waiting finalization that fails because no returned gross roll exists.

Use four fixed machines without violating one-running-card-per-machine. Record card IDs, order numbers, status/version/timing/roll snapshots, and the resolved temporary database path in the fixture JSON.

- [ ] **Step 4: Implement geometric and interaction checks**

At both 1440×900 and 1366×768, assert:

- modal and all three cards fit without page/body scrolling or overlap;
- the left/right proportion is approximately 40/60 and aligned at top/bottom;
- all section icons use identical computed tile size and treatment;
- order/time labels and values are vertically centered within tolerance;
- all four time values have identical computed `font-family`, `font-size`, `font-weight`, `line-height`, and color;
- all five header/body/total column centers align and column widths differ by no more than one CSS pixel;
- pallet number, every numeric cell, and `Общо` are centered;
- no table horizontal scrollbar exists;
- scrolling changes the first visible pallet record while the header, total row, footer, and left cards keep the same bounding boxes;
- every rendered kilogram value matches `^-?\d+\.\d$`, including all `0.0` pallet placeholders;
- normal customer/product values are not clipped and `0.060 мм` remains exact;
- active review has `Редактирай`; waiting review does not contain that control;
- the active editor opens and returns to the review after an authoritative preview;
- close, cancel, and Escape issue no finish POST and restore focus;
- marked initial confirmation enters waiting with the accurate copy/action;
- waiting confirmation remains tokenless and preserves the database timing snapshot;
- the zero-roll waiting-finalization failure leaves the review available with its message;
- rapid double activation produces one finish request; and
- no unexpected console error, page error, failed request, or cross-origin request occurs.

- [ ] **Step 5: Capture required evidence**

Write screenshots and `verification-summary.json` below:

```text
artifacts/ui-checks/order-finish-review/
  active-normal-1440x900.png
  active-marked-empty-1366x768.png
  waiting-read-only-1440x900.png
  waiting-scrolled-1366x768.png
  waiting-validation-error-1366x768.png
  verification-summary.json
```

Screenshots are evidence, not runtime assets.

- [ ] **Step 6: Make the safety tests pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_order_finish_review_ui_script_safety.py -q
```

Expected: pass.

---

### Task 8: Run live verification, document the result, and complete repository review

**Files:**

- Create: `docs/implementation-notes/order-finish-review.md`
- Create: `design-qa.md`
- Modify: `README.md`
- Modify: `v2-files/PLAN.md`
- Modify: `v2-files/archive/TASK-21-ORDER-FINISH-REVIEW.md`

- [ ] **Step 1: Create the temporary UI fixture**

Run:

```bash
mkdir -p .test-runtime/order-finish-review artifacts/ui-checks/order-finish-review
EXTRUSION_DATA_DIR=.test-runtime/order-finish-review \
EXTRUSION_DB_PATH=.test-runtime/order-finish-review/fixture.sqlite3 \
.venv/bin/python scripts/create_order_finish_review_fixture.py \
  --db-path .test-runtime/order-finish-review/fixture.sqlite3 \
  --output .test-runtime/order-finish-review/fixture.json
```

- [ ] **Step 2: Start the live FastAPI app against only that fixture**

Run in a dedicated terminal:

```bash
EXTRUSION_DATA_DIR=.test-runtime/order-finish-review \
EXTRUSION_DB_PATH=.test-runtime/order-finish-review/fixture.sqlite3 \
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8021
```

Verify `/health` reports the exact resolved fixture database path before opening a browser.

- [ ] **Step 3: Run the repository-local browser verifier**

In another terminal, run:

```bash
./node_modules/.bin/playwright --version
BASE_URL=http://127.0.0.1:8021 \
FIXTURE_JSON=.test-runtime/order-finish-review/fixture.json \
ARTIFACT_DIR=artifacts/ui-checks/order-finish-review \
node scripts/verify_order_finish_review_ui.mjs
```

Expected: `verification-summary.json` reports `passed`, all required screenshots have exact viewport dimensions, and all error arrays are empty.

- [ ] **Step 4: Complete the blocking design-QA comparison**

Create one same-state, same-size comparison image that places the approved
source and the active implementation capture side by side, then inspect that
combined image rather than comparing from memory or separate image views. Add
focused combined crops for the time rows and table because their typography
and alignment are too dense to judge only from a full-screen comparison.

Write the result to project-root `design-qa.md` with the source and
implementation paths, viewport, source/implementation pixel dimensions,
density normalization, state, full-view and focused comparison evidence, the
five required fidelity surfaces, interaction/console checks, and comparison
history. Set `final result: passed` only when no actionable P0/P1/P2 issue
remains. If any issue is found, fix it, capture again at the same viewport,
repeat the combined comparison, and record the iteration before proceeding.

- [ ] **Step 5: Write the durable implementation note**

Record:

- the three mode-selection rules and exact action copy;
- why active timing is editable but waiting timing is immutable;
- reuse of Task 22 review tokens and backend operations;
- the physical-pallet placeholder seam and explicit separation from core/tare;
- empty/error summary behavior;
- failure, stale, focus, and duplicate-submit behavior;
- exact automated and Playwright commands/results; and
- mocked/temporary verification boundaries.

Include this migration assessment exactly, updated only if the final diff disproves it:

```text
Migration assessment
- Decision: No migration
- Why: The change adds presentation fields, markup, controller behavior, and tests without changing schema or stored-value meaning.
- Existing production data affected: None.
- Proposed migration: None.
- Transformation: No values changed.
- Unknowns or ambiguous rows: None known; physical pallet weight is intentionally not inferred historically.
- Required tests: Temporary-database render, lifecycle, timing-preservation, and browser interaction checks.
- Production snapshot needed now: No.
- Deployment constraint: Deploy the verified application revision normally; do not add a pallet-weight schema until the separately specified follow-up task.
```

- [ ] **Step 6: Update authoritative project documentation only after behavior passes**

In `README.md`, describe the now-implemented common finish review, active-only time edit, waiting read-only variant, and explicit temporary `0.0` physical pallet-weight display. Do not describe pallet-weight input or persistence as implemented.

In `v2-files/PLAN.md`, mark Task 21 implemented with its verification summary and durable note link. In the Task 21 specification, change only its status to implemented and link the durable note; do not erase the accepted contract.

- [ ] **Step 7: Run syntax and focused verification**

Run:

```bash
.venv/bin/python -m compileall -q app tests scripts
node --check app/static/js/timing_interval_editor.mjs
node --check app/static/js/waiting_finish_review.mjs
node --check scripts/verify_order_finish_review_ui.mjs
node --test tests/js/timing_interval_editor_core.test.mjs
.venv/bin/python -m pytest \
  tests/test_terminal_pallet_summary.py \
  tests/test_terminal_timing_correction.py \
  tests/test_finish_cancel_history.py \
  tests/test_rewinding_workflow.py \
  tests/test_terminal_v8_render.py \
  tests/test_terminal_sync.py \
  tests/test_order_finish_review_ui_script_safety.py -q
git diff --check
```

Expected: every command exits zero.

- [ ] **Step 8: Run the complete Python suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: pass with no mutation of the real runtime database.

- [ ] **Step 9: Perform the final diff and scope review**

Run:

```bash
git status --short
git diff --stat
git diff -- app tests scripts README.md v2-files docs/implementation-notes
```

Confirm:

- no migration/schema/SQL change slipped in;
- no runtime database or generated artifact is tracked;
- unrelated user files remain untouched;
- active and waiting mutations still call their original backend operations;
- all visible copy is Bulgarian;
- no literal dash remains in physical pallet-weight cells;
- no unfinished implementation marker, fake persisted value, or prototype-only mock is present; and
- documentation states pallet-weight entry is a future task.

- [ ] **Step 10: Retain or remove disposable evidence according to repository policy**

Keep `artifacts/ui-checks/order-finish-review/` available while the user reviews the implementation. After acceptance and once the durable note records the result, delete the generated artifacts unless the user explicitly asks to retain them. Do not stage or commit anything unless the user gives separate permission.

## Execution Completion Gate

Do not report Task 21 complete until all checkboxes above are satisfied, the final live screenshots have been visually inspected, the task-specific browser summary passes, the full Python suite passes, and the final diff review confirms the physical pallet placeholder remains presentation-only and waiting finalization remains timing-neutral.
