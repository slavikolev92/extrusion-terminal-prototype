# Task 21: Unified Order-Finish Review

Status: implemented and locally verified in source; not deployed. The durable
implementation and verification record is
`docs/implementation-notes/order-finish-review.md`.

## Purpose

Every operator `Приключи` action must first open one clear production-summary
screen. The operator reviews the order identity, authoritative production time,
and saved pallet production before confirming the applicable lifecycle change.

Task 21 is a presentation and orchestration extension of the existing Task 22
finish-review implementation. It must reuse the existing tokenized active-card
review, timing editor, pallet aggregation, finish operations, and optimistic
conflict protection. It must not create a second completion transaction or
change established production calculations.

## Approved Visual Source

The approved visual reference is:

`ui-prototypes/caa68a9d-3f9f-4fcc-a0b6-a617ffc4f564.png`

The reviewed interactive prototype is under the disposable verification path:

`artifacts/ui-checks/task-21-operator-prototype/`

The specification in this file governs when the source image and the prototype
differ. In particular, all table cells are centered, the pause label is
`Паузирано време`, all four time values use identical typography, and the
physical pallet-weight column temporarily displays `0.0` without participating
in any calculation.

## Shared Screen Structure

Use a contained, large review dialog over a subdued terminal background. At
normal desktop sizes, keep visible application context around it: target about
94% of the viewport width, cap the dialog near 1360 px wide and 840 px tall,
and retain a safe viewport-height margin. A nearly full-screen fallback is
allowed only for genuinely constrained viewports where preserving readable
content requires it. Do not show a visible overall title such as `Преглед
преди приключване`. Keep a compact `×` close control in the upper-right corner
and give the dialog an accessible name.

The content contains three independent bordered cards:

- upper left: `Детайли на поръчката`;
- lower left: `Производствено време`; and
- right: `Произведена продукция`.

Use approximately 40% of the content width for the left stack and 60% for the
right card, excluding the consistent gap. The production card spans the full
height of the two left cards and their gap. Align the top edges of the upper
left and right cards and the bottom edges of the lower left and right cards.

All three cards use the same white surface, pale blue-gray border, modest
corner radius, internal spacing, plain dark heading, and pale-blue rounded icon
tile. Use one outline icon family with matching factory, clock, and
clipboard/list icons. Do not use heading bars, decorative gradients, dashboard
metrics, or duplicate summaries.

Below the cards, use one full-width footer. Keep the footer and its actions
visible while pallet records scroll. Keep `Отказ` immediately before the dark-
blue primary action at the lower right; it must use the same primary-action
color as the terminal's `Приключи` control. Both footer actions are text-only.
Reserve red for destructive actions.

## Order-Details Card

Display exactly these four read-only label/value rows in this order:

| Label | Source |
| --- | --- |
| `Машина` | `Машина {machine_id}` |
| `Поръчка №` | `order_number` |
| `Клиент` | `customer` |
| `Продукт` | the non-blank `product_type` and `size_thickness`, joined once with a space |

Use a stable label column, a stable value column, subdued labels, stronger
values, and subtle horizontal row separators. Vertically center every label
and value using the same rule. The normal approved example must remain on one
line. Long real values may wrap and must never be silently clipped.

Product text is source text. Preserve measurement precision such as
`0.060 мм`; table weight formatting must never alter product specifications.

## Production-Time Card

Display exactly these four rows in this order:

| Label | Value |
| --- | --- |
| `Начало` | first production start |
| `Край` | proposed or stored extrusion finish |
| `Произв. време` | total productive duration |
| `Паузирано време` | total pause duration |

Show timestamps as `DD/MM/YY HH:mm`. Do not show seconds. Show durations with
hours and minutes only, using the existing authoritative timing-ledger totals.
When hours are positive, use `{H} ч {MM} м`; when hours are zero, use `{M} м`,
as in `2 ч 03 м` and `15 м`. All four values must use the same font family,
size, weight, line height, color, and tabular-number treatment. Do not make only
one duration bold or otherwise more prominent.

For a `running` or `paused` card, place a blue outlined pencil button labelled
`Редактирай` at the lower right inside this card, beneath the rows. Its
accessible name may be `Редактирай производственото време`. It must open the
existing Task 22 interval editor and return to this summary after an accepted
preview.

For an `awaiting_rewinding` card, render no edit button at all. Do not show a
disabled or gray substitute. Waiting-card finalization is deliberately
timing-neutral.

## Produced-Production Card

Render a read-only table with exactly these five columns in this order:

| Column | Exact heading |
| --- | --- |
| 1 | `Палет №` |
| 2 | `Брой ролки` |
| 3 | `Бруто, кг` |
| 4 | `Тегло палет, кг` |
| 5 | `Нето, кг` |

Each column occupies 20% of the available table-column area. Header, body, and
total cells share the same boundaries after accounting for the scrollbar.
Center every heading and every value, including pallet identifiers and
`Общо`. Use one-decimal kilogram formatting and tabular numerals. Preserve the
existing `Без палет` row when saved gross rolls are unassigned.

Use a pale blue-gray header, subtle separators, very light alternating rows,
and a pale-blue bold total row. Do not add row actions, checkboxes, menus,
sorting, filtering, pagination, or another summary strip.

The record area scrolls vertically. The header and total row remain visible,
and the overall modal, left cards, and footer do not scroll at the intended
desktop sizes. Use the available height instead of hard-coding an exact number
of visible records. Do not introduce horizontal scrolling at 1440×900 or
1366×768.

When no gross roll exists, retain the five-column table shell, show
`Няма въведени ролки.` in the record area, and show an aligned zero total row.
This state is valid when active extrusion is being ended into rewinding wait;
the backend remains authoritative about which final outcomes require rolls.

If saved roll data cannot be summarized safely, show an understandable error,
do not display misleading totals, and prevent confirmation until the operator
returns to the order or reloads.

## Physical Pallet-Weight Placeholder

`Тегло палет, кг` means the weight of the physical pallet on which rolls are
placed. It is not the roll-core/tare weight (`Шпула, кг`). The application does
not capture physical pallet weight yet.

Task 21 must nevertheless expose a real, stable presentation contract for the
future feature:

- every pallet-summary row has `pallet_weight = Decimal("0")` and
  `pallet_weight_display = "0.0"`;
- the total has the same fields and values;
- the empty summary has an explicit zero total with the same fields; and
- the template reads these fields instead of rendering a dash or a literal
  unrelated to the pallet-summary model.

This is a view-model placeholder only. Do not add a database column, migration,
input, persistence rule, or invented historic pallet weight in Task 21. Do not
write the placeholder into SQLite.

The placeholder must not change gross or net calculations. Existing net remains
the sum of each roll's `gross_weight - tare_weight`, where tare is the roll-core
weight. The later pallet-weight task will define persistence, ownership, and
any calculation semantics before replacing the placeholder source; Task 21
must not guess those rules.

## Lifecycle Variants

The same modal and cards are used for all three finish contexts. Lifecycle
status—not imported route-sequence text—selects the variant.

### 1. Normal initial completion

Condition: the card is `running` or `paused` and `rewinding_roll_count` is not
positive.

- Freeze and authenticate the proposed stop through the existing Task 22
  review token.
- Show `Редактирай` and allow the existing timing draft workflow.
- Primary action: `Потвърди приключване`.
- Confirmation uses the existing atomic active-card finish path and results in
  `completed` when backend validation succeeds.

### 2. Initial end of extrusion with rewinding expected

Condition: the card is `running` or `paused` and `rewinding_roll_count` is
positive.

- Use the same tokenized review and editable timing behavior as normal initial
  completion.
- Show a restrained footer outcome line:
  `След потвърждение: Изчаква пренавиване · {count label}`.
- Use `1 ролка` for one and `{N} ролки` otherwise.
- Primary action: `Потвърди край на екструдирането`.
- Confirmation uses the existing atomic active-card finish path and results in
  `awaiting_rewinding` when backend validation succeeds.

The marker remains informational. Do not compare it with saved or returned
rolls and do not create placeholders from it.

### 3. Finalization after returned rewinding rolls

Condition: the card status is `awaiting_rewinding`, regardless of whether its
current informational marker is still positive.

- Open the same full summary from `Приключи`.
- Show stored extrusion start, stored finish, productive duration, and paused
  duration read-only.
- Omit `Редактирай` completely.
- Show `Изчаква пренавиване` in the footer; append `· {count label}` only when
  the marker is still positive.
- Primary action: `Потвърди приключване`.
- Keep the existing tokenless waiting-finalization request and dedicated
  backend operation.
- Do not freeze a new stop, create a review token, accept a timing draft, mutate
  timing segments, or change `finished_at`.

This final screen is a review of existing data, not a second opportunity to
correct extrusion timing. Exceptional later corrections remain Admin-only.

## Interaction, Failure, And Concurrency Rules

- `×`, `Отказ`, and Escape dismiss the review without any write or lifecycle
  change and restore focus to the initiating `Приключи` control.
- Do not dismiss the modal from a backdrop click.
- Start with safe focus on the dialog or `Отказ`, not the destructive primary
  action.
- Trap focus while the modal is open and keep visible keyboard focus styles.
- Preserve the existing mixed numbered/unassigned pallet warning in all three
  variants. It remains non-blocking.
- Prevent duplicate confirmation while a request is pending.
- Active-card reviews retain Task 22 token, version, frozen-stop, validation,
  and stale-review behavior.
- Waiting-card reviews remain tokenless but submit the loaded version and rely
  on the dedicated backend operation's transaction-time status, shift, roll,
  tare/net, sequence, and version checks.
- If confirmation fails, do not dismiss as though it succeeded. Re-render or
  keep the summary open with a Bulgarian explanation. Stale or unavailable
  data must lock the action and require reload; correctable roll/tare errors
  must let the operator dismiss the review, correct the card, and reopen it.
- If the active shift disappears while the review is open, suspend the review
  consistently with the existing terminal shift-stale behavior.

## Preserved Backend Invariants

- Every finish still requires timing to have started and an active shift.
- Normal completion and waiting finalization still require a gap-free roll
  sequence, at least one gross roll, and valid copied tare/net values.
- A positive rewinding marker still permits an active card to enter
  `awaiting_rewinding` without tare or roll entries.
- Active finish from `running` still closes the active timing segment; finish
  from `paused` still preserves the already closed ledger.
- Waiting finalization still changes only lifecycle/version/update metadata and
  never mutates timing or `finished_at`.
- Machine reuse, queue normalization, final-shift attribution, pallet
  optionality, immediate persistence, and stale-write protection remain
  unchanged.

## Out Of Scope

- Physical pallet-weight input, persistence, history, correction, or
  calculation behavior.
- New rewinding scheduling, timing, lineage, matching, or department workflow.
- New target-versus-actual cards, dimension/material summaries, or additional
  completion metrics.
- A new time-editor design; reuse the existing Bulgarian Task 22 editor.
- Any schema or migration change.
- Any new completion confirmation step after this review.

## Acceptance Checks

Task 21 is complete only when automated and live-browser verification prove:

- all three variants use the approved common layout and the correct edit/action
  behavior;
- order/customer/product data and timing values are correct, complete, aligned,
  and untruncated;
- the five equal-width centered columns, scrollable record area, fixed header,
  fixed total, and full-width footer remain aligned at 1440×900 and 1366×768;
- the normal desktop dialog remains visibly contained, its body/table/action
  type uses the terminal's compact readable scale, and its confirmation action
  uses the terminal's dark-blue primary color rather than destructive red;
- every table kilogram value, including physical pallet placeholders and
  totals, has exactly one decimal place;
- the physical pallet placeholder is sourced from the pallet-summary view model,
  never confused with tare, never stored, and never used to recalculate net;
- active reviews retain tokenized editable timing and waiting reviews are
  tokenless and timing-neutral;
- close, cancel, edit, confirm, duplicate-submit, validation-failure, stale,
  shift-loss, and status-change paths behave safely; and
- focused tests, the full Python suite, JavaScript tests, syntax checks,
  `git diff --check`, and a task-specific Playwright run against a temporary
  SQLite database pass without unexpected page, console, or request errors.
