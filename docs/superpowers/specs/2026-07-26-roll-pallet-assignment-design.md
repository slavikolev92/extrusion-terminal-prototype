# Roll Pallet Assignment And Operational-Card Summary Design

Date: 2026-07-26

## Goal

Record which transport pallet contains each produced film roll and summarize
those assignments on the completed operational-card printout.

The feature is deliberately limited to pallet attribution and calculated
summaries. It does not create a pallet-management or shipping subsystem.

## Terminology

- The Bulgarian UI term is `Палет`.
- A roll without a pallet displays `-` in the terminal and admin roll ledgers.
- A printed aggregate for rolls without a pallet is labeled `Без палет`.
- Pallet gross weight means the sum of the assigned rolls' gross weights.
- Pallet net weight means the sum of the assigned rolls' net weights.
- The physical wooden pallet and wrapping material are excluded from all
  weights in this feature.

## Confirmed Business Rules

- A pallet belongs to exactly one operational card. Rolls from different cards
  are never combined in one pallet.
- A roll belongs to at most one pallet.
- Pallet assignment is optional because sample orders may not use pallets.
- Pallet identifiers are positive whole numbers from `1` through `999`. Blank
  is also valid.
- Surrounding whitespace is removed before validation. For example, ` 1 ` is
  stored as integer `1`.
- Zero, negative values, values above `999`, decimals, letters, and mixed
  values are invalid.
- Pallet numbers are scoped to a card, may contain gaps, and are never
  normalized, incremented, or renumbered automatically.
- There is no pallet capacity, full/closed state, or explicit pallet-switch
  action. The worker changes the current pallet number directly.

## Data Model

Use the existing tare-weight persistence pattern, with two nullable positive
integer values that have different responsibilities:

- `cards.current_pallet_number` is the card's current workflow selection. New
  cards start with this value blank.
- `roll_entries.pallet_number` is the permanent pallet snapshot for that roll.

There is no placeholder or empty roll. Changing the current pallet only updates
the card. A roll row is created only when the worker adds a roll, at which time
the current pallet value is copied onto that new row.

Changing `cards.current_pallet_number` never changes existing rolls. Correcting
an individual `roll_entries.pallet_number` never changes the card's current
pallet. Deleting or renumbering rolls never changes the pallet assignments of
the remaining rolls.

Both database columns must constrain non-null values to SQLite integers from
`1` through `999`. Backend parsing remains authoritative even though the HTML
input uses the same minimum, maximum, and whole-number constraints.

Pallet totals are derived from current roll rows whenever data is read for
display or print. Do not persist pallet roll counts, gross totals, or net
totals.

## Migration And Existing-Data Safety

Add the two nullable columns through the next ordered schema migration and add
the same constraints to the fresh-database schema.

The migration is schema-only:

- Existing cards retain all current fields and receive a blank current pallet.
- Existing rolls retain card, order, roll number, gross, tare, net, shift,
  timestamps, and every other value, and receive a blank pallet assignment.
- No historical pallet assignment is guessed or backfilled.
- Existing completed and archived cards remain printable. If every historical
  roll has a blank pallet, their printout simply has no pallet-summary section.
- Import and overwrite-import logic must continue updating imported/front-card
  fields only. Both new pallet fields are production data and must survive
  re-import unchanged.

The migration and its registry record must share the existing caller-owned
transaction and savepoint. A failure must roll back both the schema changes and
the migration record. Migration verification must cover a fresh database,
accepted legacy shapes, a partially upgraded shape, repeat initialization,
injected rollback, `PRAGMA integrity_check`, and `PRAGMA foreign_key_check`.

## Terminal Roll Entry

The normal roll-entry row, from left to right, becomes:

`Нова ролка, кг | Шпула, кг | Палет | Добави`

The pallet input sits immediately to the right of the core input and
immediately to the left of `Добави`. Shorten the new-roll gross and core inputs
to make room. Rebalance the workstation columns slightly toward the roll panel
by narrowing the oversized planned-material recipe column and allowing the roll
section to extend farther left. This is a bounded width adjustment, not a
recipe redesign: every recipe field and value must remain visible and usable at
the supported workstation viewport.

The current pallet input:

- starts blank for a new card;
- accepts blank or a whole number from `1` through `999`;
- autosaves with the same interaction pattern as the current tare/core input;
- survives page reloads, card switching, and application restarts;
- remains unchanged after successful roll entry; and
- is subject to the card's existing status, active-shift, and stale-version
  protections.

Adding a roll copies the current pallet value, including blank, into the new
roll in the same transaction as the roll's gross, tare, net, shift attribution,
and card-version update. A failed validation or stale write creates no partial
roll and changes no pallet data.

## Terminal Roll Ledger And Correction

The roll ledger becomes:

`№ | Палет | Бруто кг | Шпула кг | Нето кг`

Display mode shows the positive pallet number or `-` when blank. The existing
roll-correction mode makes pallet, gross, and tare editable in the same form.
The net value remains calculated.

Correction behavior:

- All submitted roll changes are validated before any are written.
- If any pallet or weight value is invalid, none of that correction form's
  changes are saved.
- Blank pallet values are allowed.
- A successful save updates the chosen roll snapshots and the card version.
- Correcting a roll does not change the current pallet control.
- Existing stale-page handling warns and requires reload.
- Correction mode does not add pallet-specific delete or navigation controls.

## Admin Production Ledger

The admin production ledger receives the same current-pallet control and the
same per-roll pallet column. Admin-added rolls copy the current pallet, and
existing roll pallet assignments can be corrected alongside gross and tare.

Admin saving retains its existing atomic ledger behavior and optimistic
conflict checks. The admin gains no separate pallet page or pallet lifecycle.

## Finish Confirmation

Only saved rolls with a gross weight participate in the finish-time pallet
check.

- If every roll has a blank pallet, use the existing normal finish
  confirmation. This is a valid sample/no-pallet order.
- If every roll has a pallet number, use the existing normal finish
  confirmation.
- If numbered and blank pallet assignments are mixed, replace the normal
  question with a Bulgarian confirmation that includes the number of rolls
  without a pallet. Use grammatically correct singular/plural wording:

  - `В поръчката има 1 ролка без палет. Искате ли да приключите поръчката?`
  - `В поръчката има 3 ролки без палет. Искате ли да приключите поръчката?`

The buttons are `Да` and `Не`.

- `Не` closes the popup and leaves the worker on the normal card screen. It
  does not open correction mode and makes no request or data change.
- `Да` submits the existing finish operation.

This is an operator warning, not a new backend finish blocker or override
protocol. Blank and mixed pallet assignments remain valid production data.

## Pallet Summary Calculation

Print aggregation uses saved rolls with gross weight and groups them by
`roll_entries.pallet_number`.

For each numbered pallet, calculate:

- `Ролки`: count of grouped rolls;
- `Бруто, кг`: sum of grouped roll gross weights; and
- `Нето, кг`: sum of grouped roll net weights.

Numbered groups sort by numeric pallet number. Gaps create no empty rows. When
numbered and blank assignments are mixed, one `Без палет` group appears last
and uses the same count, gross-sum, and net-sum rules.

If all roll pallet assignments are blank, produce no pallet-summary table. The
existing order-level gross and net totals remain sufficient for that case.

Printed weights use the established one-decimal formatting. Existing print
readiness continues to require complete per-roll tare and net information, so
the pallet summary must not invent a missing net value.

## Operational-Card Print Layout

Restructure the lower area of the back page into three side-by-side blocks:

1. A left production-summary block containing start time, stop time, total
   production time, core/tare, order gross total, and order net total.
2. A middle pallet-summary block.
3. A right continuation block for additional pallet-summary rows.

Each pallet block uses the compact repeated headings:

`Палет | Ролки | Бруто, кг | Нето, кг`

Both gross and net are required columns. There is no redundant pallet grand
total because the order-level gross and net totals remain in the left block.
The front page, back-page order header, and fixed 120-roll grid remain
unchanged. Pallet numbers do not replace or populate the existing blank
`Дата / смяна` cells in the per-roll print grid.

The count of pallet rows that fit in each block is a print-layout measurement,
not a business limit. The implementation must use whole rows of fixed height,
fill the middle block to the verified bottom safe boundary, and then continue
in the right block. A browser-generated A4 PDF must prove that the last row does
not clip, overlap, or cross the safe print margin. Do not assume a capacity from
the visual estimate discussed during design.

If all summary rows cannot fit across both page-two pallet blocks:

- render no partial pallet summary on page two;
- move the entire pallet summary to an additional page beginning with page
  three;
- repeat the order number, customer, and product type on every overflow page
  so a detached sheet remains identifiable; and
- permit further automatic overflow pages if an extreme case requires them.

No pallet row may be silently omitted or divided across pages. Completed-card
corrections must be reflected on every reprint because the summary is derived
at request time.

## Validation And Error Handling

- Invalid current-pallet input leaves the stored card value unchanged and
  renders `Палетът трябва да бъде цяло число от 1 до 999.` near that control.
- An invalid new-roll submission creates no roll and does not itself mutate the
  separately autosaved current pallet or other production data.
- Invalid correction input saves none of the correction form.
- Pallet updates participate in existing card-version increments and stale
  conflict behavior.
- Routes must verify that edited roll IDs belong to the addressed card.
- Existing status and active-shift rules remain unchanged.
- Printing is not blocked merely because pallet assignments are blank or mixed.

## Testing And Verification

Automated backend and database checks must cover:

- fresh schema and legacy migration;
- migration repeat-run safety and rollback;
- preservation of all existing production data and recorded migrations;
- import and overwrite-import preservation;
- blank and valid current-pallet saving;
- trimming surrounding whitespace;
- rejection of zero, negatives, values above `999`, decimals, letters, and
  mixed values;
- copying current pallet to new rolls without changing earlier rolls;
- blank pallet roll entry;
- terminal and admin corrections;
- correction atomicity and foreign-roll rejection;
- stale current-pallet, new-roll, and correction submissions;
- roll deletion and renumbering without pallet reassignment; and
- unchanged status, shift, tare, net, timing, and finish invariants.

Automated rendering and print checks must cover:

- pallet input and ledger display on terminal and admin;
- workstation field order, shortened weight inputs, wider roll panel, and
  preserved recipe readability at the supported viewport;
- correction-mode pallet input;
- `-` for blank ledger values;
- normal finish confirmation for all-blank and all-assigned cards;
- mixed-assignment question, count, `Да`, and `Не` behavior;
- numeric pallet sorting and gaps;
- roll count, gross sum, and net sum per pallet;
- mixed `Без палет` aggregation and last position;
- no pallet section for an all-blank card;
- corrected values appearing on reprint;
- one-decimal print formatting;
- page-two middle-to-right flow without clipping; and
- whole-summary overflow with identification and no omitted rows.

Before completion, run syntax/import checks, focused tests, the full Python test
suite, and `git diff --check`. Use the live FastAPI app with a temporary SQLite
database and the repository-local Playwright installation. Save relevant
terminal entry, terminal correction, admin correction, normal print, and
overflow-print evidence under `artifacts/ui-checks/`.

## Out Of Scope

- Pallet capacity or full/closed state.
- Automatic pallet-number incrementing or normalization.
- Separate pallet records, screens, or lifecycle.
- Physical wooden-pallet or wrapping tare.
- Interim pallet labels or label-print routes.
- Product labels, barcodes, or scanners.
- Shipment, dispatch, delivery, or sent-pallet tracking.
- Combining rolls from different operational cards.
- Blocking completion or printing because pallet assignments are blank.
- Any user, role, login, or permission functionality.
