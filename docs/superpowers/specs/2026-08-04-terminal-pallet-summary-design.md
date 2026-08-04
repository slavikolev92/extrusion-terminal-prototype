# Terminal Pallet Summary Design

Date: 2026-08-04

## Goal

Give extrusion operators a fast, read-only pallet summary for the operational
card currently open at `/terminal`. The summary supports preparation of pallet
transportation information by showing how many saved rolls belong to each
pallet and the gross and net weight of those rolls.

The feature is informational only. It must not add or change production data,
card lifecycle behavior, pallet assignment behavior, printing, or admin
functionality.

## Confirmed Operator Experience

Every card visible at the terminal has a `Палети` button in the right side of
the `Ролки` panel heading. This includes pending, running, paused,
`awaiting_rewinding`, and completed cards.

When the rewinding action is available, the heading actions are ordered:

1. `Пренавиване`
2. `Палети`

For other terminal-visible card states, `Палети` appears by itself in the same
right-aligned action area. It uses the existing neutral secondary-button
styling so it does not resemble an action that changes production state.

Clicking `Палети` opens a centered modal titled `Обобщение по палети`. The
modal also identifies the selected card as `Поръчка №{order_number}` so an
operator cannot lose the order context while reading transportation totals.
The modal contains no form, link, input, or data-changing control. Its semantic
HTML table has four columns:

| Палет | Брой ролки | Бруто, кг | Нето, кг |
| --- | ---: | ---: | ---: |

Numbered pallet rows sort by pallet number in ascending numeric order. A final
`Без палет` row appears whenever one or more entered rolls have no pallet
assignment, including when every entered roll is unassigned. A visually
distinct `Общо` row follows the pallet rows and shows the total roll count,
gross weight, and net weight across all entered rolls.

Weights use the terminal's established one-decimal display. Numeric cells are
right-aligned. If the card has no entered rolls, the enabled button opens the
modal with `Няма въведени ролки.` instead of displaying a table.

The table uses a header row with scoped column headings, a body for pallet
groups, and a footer for `Общо`. The modal has one explicit `Затвори` button.
It also closes when the operator presses Escape or clicks the shaded
background. Keyboard focus is trapped inside the open modal and returns to the
`Палети` button after close. The underlying terminal is inert and hidden from
assistive technology while the modal is open. A long table scrolls within the
modal while its title and close action remain reachable.

Only one terminal modal or drawer may be active at once. Opening the pallet
summary closes any open queue, waiting, history, or rewinding surface before it
isolates the background. The `Палети` button is disabled while a roll-correction
row is open, matching the terminal's existing protection for unfinished
corrections. Existing finish, shift, and roll-change overlays continue to block
the underlying terminal controls and therefore cannot be stacked with the
pallet summary.

## Data And Calculation Rules

The selected card's already-fetched `roll_entries` are the only data source.
No additional request is made when the modal opens.

An entered roll is a saved roll entry whose `gross_weight` is not `NULL`. For
each entered roll:

- the pallet group is its saved `pallet_number`, or `Без палет` when that value
  is `NULL`;
- the pallet roll count increases by one;
- its saved gross weight contributes to the pallet gross total; and
- its saved net weight contributes to the pallet net total.

Gross, tare, and net values are parsed and summed as `Decimal` values. The
builder verifies that all three values are finite and non-negative and that the
saved net value equals saved gross minus saved tare. It sums the exact saved
values first and rounds each final displayed pallet or overall total once,
using the terminal's established `ROUND_HALF_UP` one-decimal rule. It never
sums binary floating-point values or already-rounded display strings.

The `Общо` row applies the same count and exact-sum rules across all entered
rolls. The card's current pallet default for future rolls does not create an
empty pallet row; only saved roll snapshots participate.

The modal represents the saved card snapshot used to render the page. Existing
save-and-reload and terminal update-awareness behavior remains authoritative;
the modal does not introduce polling or its own refresh request. If the
existing background snapshot check detects that the selected card changed
while this modal is open, it emits a terminal card-stale event, closes the
modal without returning focus to stale controls, reveals the existing reload
alert, and moves focus to that alert's reload action. A blocking shift-stale
event also closes the pallet modal before the shift reload surface takes over.

## Architecture

Add one small terminal-specific module, `app/pallet_summary.py`, containing the
pure Python calculator and its dedicated validation error. The module accepts
roll-entry mappings and either returns ordered pallet rows plus overall totals,
returns an empty result, or raises its validation error for unusable roll data.
It does not import the database or printing layers, log, access SQLite, render
HTML, or catch its own unexpected programming errors. This keeps the logic out
of the already-large route and template files without introducing a framework
or reusable abstraction that the pilot does not need.

The terminal page-context boundary invokes the calculator and creates one of
three explicit view-model states:

- `ready`: ordered pallet rows and overall totals;
- `empty`: no entered rolls; or
- `error`: the calculator or summary integration failed.

This boundary gives the resulting view model to the Jinja template. Keeping
calculation and failure containment separate makes the arithmetic directly
testable while retaining a final safety net around the optional feature.

The browser receives already-calculated and formatted rows. The pallet modal
joins the existing inline terminal drawer/modal coordinator so mutual
exclusion and roll-correction locking have one owner. Do not create a second
modal manager or an event bus for this feature. Vanilla JavaScript only opens
and closes the modal, isolates background controls, responds to existing stale
signals, traps keyboard focus, and restores focus. It does not group rolls or
calculate weights.

This feature does not require:

- a database column, table, constraint, or migration;
- a new HTTP route or write handler;
- a change to roll entry or correction behavior;
- a change to print calculation or print output; or
- a production-data migration or backfill.

## Defensive Failure Boundary

The pallet summary is optional presentation and must not make the terminal
unavailable. Summary construction therefore has a narrow fail-soft boundary.

The calculation validates that each participating roll has usable, finite
gross, tare, and net values; a consistent gross-minus-tare net value; and a
valid nullable pallet number. The terminal page-context boundary wraps only
the call that prepares this optional summary in `try/except Exception`. This
broad catch is intentional at the feature boundary: it covers both malformed
data and an unexpected defect in the summary implementation without hiding
errors in the rest of the terminal. If summary construction fails:

- the exception is contained at the pallet-summary boundary;
- the server records the exception and stack trace with the card ID, without
  logging customer or order contents;
- `/terminal` still returns normally and the rest of the selected card remains
  usable; and
- the modal displays `Обобщението по палети не може да бъде показано. Проверете
  данните за ролките.`

Malformed or inconsistent values must never be ignored, omitted from totals,
recalculated silently, or treated as zero. Any of those choices could produce
plausible but incorrect transportation information. The fail-soft boundary is
limited to this optional summary and is not a general instruction to suppress
unrelated application errors.

## Current Data Evidence

The preserved production snapshot
`production-db/extrusion_terminal_20260728_075318_093595.sqlite3` was inspected
read-only through a temporary copy during design. Its SQLite integrity check
returned `ok`, its foreign-key check returned no rows, and it contained 35
cards and 653 saved rolls.

All 653 rolls had gross, tare, and net weights, and no calculated gross-minus-
tare mismatch was found. All 34 terminal-visible card details loaded through
the current application code; the one imported card was correctly excluded.
All 653 historical roll pallet assignments were blank, so those rolls exercise
the accepted all-`Без палет` behavior. The preserved snapshot was not modified.

The local runtime database dated 2026-08-03 was also inspected read-only. Its
27 rolls had no missing tare or net weights and no gross/net mismatch. This
design does not claim that either inspected file is a live 2026-08-04
production snapshot.

## Testing And Verification

Automated tests must cover the pure summary calculation:

- no entered rolls;
- one numbered pallet;
- multiple numbered pallets sorted numerically, including gaps;
- all entered rolls unassigned;
- mixed numbered and unassigned rolls with `Без палет` last;
- roll counts plus gross and net totals per group;
- the final `Общо` row across every group;
- exact decimal summation followed by one final `ROUND_HALF_UP` display
  rounding per total;
- boundary values that would expose binary-float or sum-of-rounded-values
  errors;
- zero-weight entered rolls;
- malformed, missing, negative, non-finite, or otherwise unusable summary
  values;
- a saved net value that does not equal gross minus tare; and
- an unexpected calculator exception converted to the safe `error` state with
  a diagnostic log record.

Terminal rendering tests must cover:

- the `Палети` button for every terminal-visible status;
- ordering to the right of `Пренавиване` when both buttons are present;
- the four table headings and ordered rows;
- order-number context in the dialog;
- the emphasized `Общо` row;
- the no-roll message;
- the fail-soft error message;
- absence of form fields and modifying controls in the modal;
- no pallet row for the card's future-roll pallet default;
- the disabled summary button during roll correction; and
- automatic close plus reload focus when the selected card becomes stale.

Browser verification against the live FastAPI app must use a temporary SQLite
database and the repository-local Playwright installation. It must verify open,
explicit close, Escape close, background close, focus trapping, focus return,
background isolation, non-stacking with existing terminal surfaces, stale-card
and shift-stale takeover, scroll containment for many pallets, and usability
at minimum at `1366x768` and `1920x1080`. At least one relevant screenshot must
be saved under `artifacts/ui-checks/`. The check must also confirm that opening
and closing the modal sends no modal-specific network request and changes no
card version or production row. No automated or browser check may mutate
`data/extrusion_terminal.sqlite3` or any file under `production-db/`.

Before completion, run focused tests, the full Python test suite, syntax/import
checks, `git diff --check`, and the focused live browser check required by
`AGENTS.md`.

Before production rollout, take the normal SQLite-safe backup and run the
summary calculator across every card in a temporary copy of that newest backup.
The compatibility check must report ready, empty, and error counts without
printing customer or order contents and must not open or modify the live
database. An error result blocks rollout until the affected roll invariant is
understood; it is not silently waived merely because the terminal would fail
softly.

## Out Of Scope

- Editing pallet assignments from the summary modal.
- Creating pallet records or a pallet lifecycle.
- Pallet capacity, full/closed state, labels, printing, barcodes, or scanning.
- Shipping, dispatch, delivery, or transportation persistence.
- Combining rolls from different operational cards.
- Repeating or expanding individual roll rows inside the summary; individual
  gross, tare, net, and pallet values remain available in the existing roll
  ledger.
- Automatic pallet numbering or assignment.
- Live polling or a dedicated pallet-summary endpoint.
- Changes to admin or print output.
- Any write to existing production data.
