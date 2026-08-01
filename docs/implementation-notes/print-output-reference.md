# Print Output Reference

This document preserves the accepted print-output requirements, field mapping, validation rules, and implementation history for future maintenance.

**Goal:** Maintain completed-card printing/reprinting for the extrusion terminal pilot, producing a normally two-page A4 operational card that follows `source-files/print-template.xlsx` as closely as practical, with page 3+ used only when the pallet summary overflows.

**Architecture:** The durable requirement is an app-data print output generated independently of Excel: the extrusion front and 120-roll back are the normal two pages, and derived pallet-summary overflow may add page 3+. The implementation is a FastAPI server-rendered HTML/CSS print route that maps SQLite card data into print-only templates matching the workbook layout.

**Tech Stack:** FastAPI, Jinja2 templates, direct `sqlite3`, app-local CSS, browser print, pytest, Playwright/browser visual checks.

**Current status:** The accepted normal two-page layout and conditional pallet-
summary overflow are implemented. The front quantity row uses the four final
Shift Manager ordered amounts. The established browser/PDF and physical-printer
layout remains the reference for verification.

---

## Scope And Source Of Truth

The former sequencing note that placed printing after a V8 workstation
bug/edge-case slice is historical. Printing is implemented and its accepted
normal two-page output, plus conditional pallet-summary overflow, is the current
maintenance reference.

The app must not fill, mutate, print from, or otherwise use `source-files/print-template.xlsx` as a runtime template. The workbook is a visual/content reference only.

The printed output must be generated from completed app data stored in SQLite:

- imported/front-card order fields
- operator/admin material corrections
- tare weight
- roll entries
- timing segments and calculated active production duration
- completion timestamp

The template fields plus confirmed production-summary additions are the boundary
for printed content. The accepted additions are timing, tare, order gross/net,
and the derived pallet summary documented below. Other app workflow fields such
as status, machine number, machine sequence, queue position, and max roll weight
must not be printed unless the user later updates the print contract.

Cancelled cards are never printable. Printing is strictly for completed or
archived cards.

## Definite Functional Requirements

The print output is normally exactly two A4 portrait pages:

1. Front page: extrusion operational card.
2. Back page: roll grid and production summary.

Page 3 and later are permitted only when the complete derived pallet summary
cannot fit in the two pallet blocks on page 2. The fixed roll grid never
overflows: it remains limited to rolls `1-120` on page 2.

The front page must represent only the extrusion card. Do not include the other original workbook operation blocks such as printing/flexo, rewinding/slitting, or confection.

The back page must keep the same 120-roll grid structure, even when fewer rolls were produced.

The output should match the supplied print template as closely as possible, while fixing clearly bad legacy behavior where text becomes unreadable or clipped.

The implementation must preserve the template structure. Fixed boxes/sections should keep their dimensions. Long text may wrap inside the box. If wrapped text still does not fit, shrink the text only as much as needed, down to a readable minimum. Do not expand the front, 120-roll grid, or page-2 production summary in a way that breaks the normal two-page structure.

The `Дата / смяна` columns on the back-page roll grid must remain visually
present but deliberately blank. M002 records durable per-roll shift attribution
in `roll_entries.shift_occurrence_id`, but the accepted print contract does not
render that attribution into these legacy compatibility cells.

Legacy front-page sections such as `ШПУЛИ`, `БРАК`, and `ФОЛИО [kg]` must remain visually present but blank unless a future confirmed template/data mapping explicitly fills them.

## Print Entry Points

Printing is an admin/shift-manager action. The terminal/workstation must not
show print or reprint controls.

Admin:

- Admin can print/reprint completed or archived cards after correcting mistakes.
- Admin print access exists from admin card detail.
- Admin may use a print preview page so layout can be inspected during development and occasional correction workflows.
- The admin preview uses the same rendered print output and backend eligibility
  rules as the print route.

## Print Eligibility And Blocking Rules

The print route must re-check readiness at print time. Do not rely only on completed status.

Printing is allowed only when all of these are true:

- card exists
- card status is `completed` or `archived`
- card is not cancelled
- tare weight exists
- at least one roll gross weight exists
- timing was started at least once
- completion/finish timestamp exists
- all timing segments are closed
- active production duration can be calculated
- roll count is between `1` and `120`

If any condition fails, block printing and show a clear actionable message. Do not silently render blanks for critical production data. Do not silently omit rolls beyond the template capacity.

More than 120 rolls must block printing with a clear error. There is no roll-
grid overflow page; pallet-summary overflow does not expand the 120-roll limit.

## Formatting Rules

Dates and date-times:

- Start/stop print format: `DD.MM.YYYY HH:MM`
- Example: `18.06.2026 14:35`
- Imported order/delivery dates on the front page should preserve the stored/imported value unless there is an existing app formatter already used for these fields.

Durations:

- `Време за изработка` is the app-calculated active production duration excluding pauses.
- Format: `N ч M мин`
- Example: `7 ч 30 мин`
- Do not calculate printed duration as simple stop minus start.

Weights:

- Production weight values print with exactly one decimal using standard rounding.
- Examples: `51.25` prints as `51.3`; `150` prints as `150.0`.
- Implement this as decimal half-up rounding for display, not Python float formatting or banker’s rounding.
- This applies to roll gross weights, tare, total gross, and total net.
- Imported/order quantity fields on the front page must print as stored text. Do not parse, round, validate, or normalize them for print because workbook quantity fields may contain human-entered text.

Roll grid:

- Each roll weight cell prints gross weight only.
- Do not print per-roll net weight in v1.
- Total gross and total net remain printed in the bottom summary area.
- Tare/core weight is printed in the bottom summary area because it explains total net.

## Template Reference: Current Workbook Structure

Reference file:

- `source-files/print-template.xlsx`

Observed sheets:

- `ACTUAL TEMPLATE`
- `DATA-FILLED TEMPLATE`

Both sheets contain the front and back references side by side in `A:V`, with
the print area ending at row `54`:

- front page: columns `A:K`;
- back page: columns `L:V`;
- extrusion front card only;
- no runtime Excel printing or workbook filling is planned.

Current back page:

- 120-roll grid split into three groups:
  - left group: rolls `1-40`
  - middle group: rolls `41-80`
  - right group: rolls `81-120`
- each group has date/shift, roll number, and kg columns
- bottom summary currently contains:
  - `Старт производство`
  - `Стоп производство`
  - `Време за изработка`
  - `Шпула /кг/`
  - `Произведено кол. бруто /кг/`
  - `Произведено кол. нето /кг/`

The bottom summary location in the current back-page template is accepted for v1. New app production summary fields belong there.

## Field Mapping

Only template fields are printed. The field list below is a mapping target, not permission to introduce new visual fields.

Front page order/header fields:

| Template field | App data |
| --- | --- |
| `ПОРЪЧКА №` | `cards.order_number` |
| `ДАТА` | `cards.order_date` |
| `ДАТА НА ДОСТАВКА` | `cards.delivery_date` |
| `ФИРМА` | `cards.customer` |
| `ГРАД` | `cards.city` |
| `ВИД ИЗДЕЛИЕ` | `cards.product_type` |
| first `КОЛИЧЕСТВО` cell | `cards.ordered_gross_kg`, stored text plus fixed `кг` |
| second `КОЛИЧЕСТВО` cell | `cards.ordered_rolls`, stored text plus fixed `ролки` |
| third `КОЛИЧЕСТВО` cell | `cards.ordered_meters`, stored text plus fixed `метра` |
| fourth `КОЛИЧЕСТВО` cell | `cards.ordered_units`, stored text plus fixed `бр.` |

The four cells have equal width. A blank source value leaves its entire cell
blank, including the unit. These are ordered source amounts, never produced
amounts.

Front page extrusion product fields:

| Template field | App data |
| --- | --- |
| `ВИД ЗАГОТОВКА` | `cards.product_form` |
| `МАТЕРИАЛ` | `cards.material` |
| `РАЗМЕР/ДЕБЕЛИНА [mm]` | `cards.size_thickness` |
| `ФАЛДИРАНЕ` | `cards.extrusion_folding` |
| `СЛЕДВАЩА ОПЕРАЦИЯ` | `cards.extrusion_next_operation` |
| `ТРЕТИРАНЕ` | `cards.extrusion_treatment` |

Front page recipe/material fields:

| Template row/column | App data |
| --- | --- |
| planned recipe row A | `cards.raw_material_a` |
| planned recipe row B | `cards.raw_material_b` |
| planned recipe row C | `cards.raw_material_c` |
| planned linear PE | `cards.linear_pe` |
| planned antistatic | `cards.antistatic` |
| planned masterbatch | `cards.masterbatch` |
| planned chalk | `cards.chalk` |
| actual/brand/material-used column | `recipe_actual_entries.actual_material_used` where present; legacy first-row fallback may use `cards.actual_raw_material_used` / `cards.raw_material_brand_grade` only if current app data shape still requires it |
| batch/lot column | `recipe_actual_entries.batch_lot` where present; legacy first-row fallback may use `cards.raw_material_batch_lot` only if current app data shape still requires it |

The printout must show both planned recipe values and actual material/batch values when actual values exist. Blank actual/brand/batch fields stay blank.

Front page notes/packaging:

| Template field | App data |
| --- | --- |
| `ЗАБЕЛЕЖКИ` | `cards.notes` |
| `НАЧИН НА ОПАКОВАНЕ` | `cards.packaging_method` |

Back page header:

| Template field | App data |
| --- | --- |
| `ПОРЪЧКА №` | `cards.order_number` |
| `ФИРМА` | `cards.customer` |
| `ВИД ИЗДЕЛИЕ` | `cards.product_type` |

Back page roll grid:

| Template field | App data |
| --- | --- |
| roll number | fixed template roll number `1-120` |
| `кг.` | gross weight for matching `roll_entries.roll_number`, one decimal |
| `Дата / смяна` | blank in v1 |

Back page summary:

| Template field | App data |
| --- | --- |
| `Старт производство` | `cards.first_started_at`, formatted `DD.MM.YYYY HH:MM` |
| `Стоп производство` | `cards.finished_at`, formatted `DD.MM.YYYY HH:MM` |
| `Време за изработка` | calculated active production duration excluding pauses, formatted `N ч M мин` |
| `Шпула /кг/` | `cards.tare_weight`, one decimal |
| `Произведено кол. бруто /кг/` | sum of roll gross weights, one decimal |
| `Произведено кол. нето /кг/` | total net weight, one decimal |

The start and stop values are canonical stored UTC values converted through
`app.timekeeping.format_print_datetime()` to `DD.MM.YYYY HH:MM` in
`Europe/Sofia`. If either required stored value is malformed, print generation
is blocked with a user-visible validation error; it must never print the raw
value or fabricate a replacement.

Back-page pallet summary:

- The lower area is three side-by-side blocks: the six-row production summary
  on the left, then two independently headed pallet blocks in the middle and
  right.
- Each pallet block repeats `Палет | Ролки | Бруто, кг | Нето, кг`.
- Each row is derived at print time from saved gross roll rows. Numbered pallets
  are sorted numerically; gaps do not create rows.
- Roll count and the gross/net sums are calculated per pallet. Both weight
  totals use the established one-decimal print formatting.
- When numbered and blank assignments are mixed, `Без палет` appears once as
  the final row. When every saved gross roll has a blank pallet, the entire
  pallet summary is omitted, including empty frames.
- The complete summary fills the middle page-2 block before the right block.
  If it cannot fit across both blocks, page 2 contains no partial pallet
  summary and the complete list starts on page 3.
- Every overflow page repeats order number, customer, and product type and uses
  the same pallet headings. Rows remain whole; no row may be split or omitted.
- Corrections are reflected on reprint because the summary is derived from the
  current roll rows rather than persisted as a separate aggregate.
- Every pallet block is a content-height table: one fixed-height header and one
  fixed-height row per rendered pallet. One or two pallets therefore render one
  or two data rows only; no filler row or table-cell stretching is permitted.
- Page-2 pallet tables, the adjacent production summary, and every overflow
  table are top-aligned independently. A short table leaves blank page space
  below it, and a taller table must not stretch a neighboring table.
- Table and column widths remain fixed within their established page-2 and
  overflow layouts and never depend on the number of pallet rows.
- A partially filled final overflow page repeats the identification and pallet
  headings, renders only its remaining fixed-height rows, and leaves the rest
  of the page blank.

Measured Chromium/PDF renderer capacities, recorded on 2026-07-26:

- `8` whole pallet rows per page-2 pallet block (`16` across both blocks);
- `48` whole pallet rows per overflow page.

These capacities are renderer geometry facts for the current CSS, not business
limits. The live boundary fixture proved that 16 rows fit as `8 + 8`, row 17
moves the whole summary to overflow, row 48 fits on an overflow page, and row 49
starts the next page. Recalibrate them after any print typography, spacing, or
page-geometry change.

Do not print `cards.max_roll_weight`. The legacy column is inert and is not part
of the print template.

## Recommended HTML/CSS Implementation Direction

Use a dedicated print route and print-only templates:

- route renders a completed card into two normal A4 `.print-page` blocks plus conditional pallet-summary overflow blocks
- page 1 is the front card
- page 2 is the back grid
- CSS uses `@page { size: A4 portrait; }`
- CSS forces the front/back break and adds positional breaks only when overflow pages follow
- CSS uses physical page dimensions and fixed layout measurements for the main structure
- use CSS grid/absolute page measurements for outer geometry
- use table-like internal blocks where they simplify repeated rows and borders
- use print-specific CSS separate from normal app/workstation CSS where practical

Do not make this a general report framework. Keep it as one extrusion operational-card print renderer.

The HTML/CSS path is recommended because it:

- matches the project’s approved simple stack
- avoids Excel/LibreOffice runtime dependencies
- is easy to test through browser/PDF output
- can be adjusted iteratively for real printer margins
- keeps data rendering inside the current FastAPI/Jinja app model

Known risk: browser print rendering may differ slightly from Excel and from the physical printer. Expect at least one calibration pass with real printer output.

## Possible Fallback Rendering Approaches

If HTML/CSS cannot produce acceptable output, preserve the durable requirements above and evaluate one of these:

1. Static page background with positioned dynamic text.
   - Pros: high visual fidelity for lines/labels.
   - Cons: brittle scaling, harder wrapping/shrinking, harder maintenance.

2. Generated PDF with a Python PDF library.
   - Pros: predictable PDF artifact.
   - Cons: extra dependency and still requires rebuilding the layout.

Do not use Excel workbook filling/printing as the first approach. The workbook is a reference artifact, not a runtime dependency.

## Proposed File Structure

Likely files to create:

- `app/printing.py`
  - print-readiness validation
  - print data assembly
  - date/time/duration/weight formatting
  - roll-slot construction for `1-120`

- `app/templates/print_card.html`
  - normal two-page print document with conditional pallet-summary overflow
  - front page markup
  - back page markup
  - minimal non-print fallback controls such as admin preview print button

- `app/static/css/print.css`
  - all print-specific page sizing, borders, text fitting, and screen preview styles

- `tests/test_print_output.py`
  - focused backend and route tests

Likely files to modify:

- `app/main.py`
  - add print routes
  - pass assembled print view model into template
  - wire admin print behavior

- `app/templates/admin_card_detail.html`
  - add print/reprint action for completed and archived cards

- `app/templates/admin_cards.html`
  - optionally add completed-card print link from card list rows

- `IMPLEMENTATION_PLAN.md`
  - update Milestone 10 status/progress when work starts/completes

## Implementation Tasks

### Task 1: Add Print Data Builder And Validation

**Files:**

- Create: `app/printing.py`
- Test: `tests/test_print_output.py`

- [ ] Add failing tests for completed-only print eligibility.

  Cover:

  - completed card with tare, timing, finish timestamp, and one roll is printable
  - pending/running/paused/imported/cancelled cards are not printable
  - completed card with missing tare is blocked
  - completed card with no rolls is blocked
  - completed card with no timing is blocked
  - completed card with more than 120 rolls is blocked

- [ ] Implement a small print-readiness result object.

  It should return:

  - `ok`
  - message list for user-visible blocking reasons
  - assembled print data only when printable

- [ ] Implement print data assembly from existing card detail data.

  Prefer using existing detail fetches/totals where possible, but keep print formatting in `app/printing.py`.

- [ ] Implement formatting helpers.

  Required behavior:

  - date-time: `DD.MM.YYYY HH:MM`
  - duration: `N ч M мин`
  - weights: one decimal, decimal half-up rounding
  - imported quantities: preserve as text

- [ ] Implement 120 roll slots.

  Required behavior:

  - always produce slots `1-120`
  - each slot has roll number and optional gross display
  - date/shift display is blank
  - more than 120 real rolls blocks print

- [ ] Run focused print tests.

  Command:

  ```bash
  source .venv/bin/activate
  python -m pytest tests/test_print_output.py
  ```

### Task 2: Add Print Routes

**Files:**

- Modify: `app/main.py`
- Create: `app/templates/print_card.html`
- Modify/Test: `tests/test_print_output.py`

- [ ] Add route tests.

  Cover:

  - completed printable card returns `200`
  - non-completed card returns a blocked response
  - card with more than 120 rolls returns a blocked response
  - a normal card without pallet-summary overflow contains exactly two print page containers
  - rendered page includes front/back known labels from the template
  - rendered page includes gross-only roll values and does not include per-roll net values

- [ ] Add a shared print preview route.

  Suggested shape:

  - `GET /cards/{card_id}/print`
  - query parameter or mode flag may control auto-print behavior, for example `?auto=1`

  Keep route naming consistent with current app route style when implementing.

- [ ] Block non-printable cards with a clear user-visible page/message.

  The response should list missing/failing items rather than fail with a generic 400/500.

- [ ] Build initial `print_card.html`.

  Requirements:

  - includes the front and back `.print-page` containers, plus conditional pallet-summary overflow containers
  - includes front and back page landmarks/classes
  - includes a screen-only print button/fallback control
  - calls `window.print()` only when auto-print mode is requested

- [ ] Run focused route tests.

  Command:

  ```bash
  source .venv/bin/activate
  python -m pytest tests/test_print_output.py
  ```

### Task 3: Recreate Front Page Layout

**Files:**

- Modify: `app/templates/print_card.html`
- Create/Modify: `app/static/css/print.css`
- Test: `tests/test_print_output.py`

- [ ] Build the front page layout from columns `A:K` of the accepted reference.

  Required sections:

  - title/header
  - order/date/customer/city row
  - product/quantity row
  - extrusion section title
  - requested product fields
  - planned recipe/material table
  - actual/brand and batch columns
  - notes/packaging
  - legacy blank sections that exist in the template

- [ ] Use fixed page geometry.

  Preserve the visual structure from the workbook while allowing wrapping and controlled font shrink classes for long text.

- [ ] Leave unmapped legacy sections blank.

  Do not fill `ШПУЛИ`, `БРАК`, `ФОЛИО [kg]`, or any other legacy section without an explicit mapping above.

- [ ] Add render tests for field presence/absence.

  Verify:

  - planned recipe values render
  - actual material/batch values render when present
  - blank actual fields remain blank
  - `max_roll_weight`, machine number, and machine sequence are absent

### Task 4: Recreate Back Page Layout

**Files:**

- Modify: `app/templates/print_card.html`
- Modify: `app/static/css/print.css`
- Test: `tests/test_print_output.py`

- [ ] Build the back page layout from columns `L:V` of the accepted reference.

  Required structure:

  - header order/customer/product area
  - three roll groups
  - roll numbers `1-120`
  - visible but blank date/shift columns
  - bottom summary block

- [ ] Render gross-only roll weights.

  Do not render per-roll net values.

- [ ] Render bottom summary.

  Required fields:

  - start
  - stop
  - active production duration
  - tare
  - total gross
  - total net

- [ ] Add tests for all roll grid and summary behavior.

  Verify:

  - 120 roll numbers render
  - roll slots over produced count are blank
  - gross values use one decimal
  - total gross/net/tare use one decimal
  - date/shift cells are blank

### Task 5: Keep The Admin Print Entry Point

**Files:**

- Modify: `app/templates/admin_card_detail.html`
- Modify: `app/templates/admin_cards.html`
- Test: existing terminal/admin render tests plus `tests/test_print_output.py`

- [x] Keep terminal print/reprint controls absent.

- [x] Keep admin print/reprint available on admin card detail for completed and
  archived cards.

  It should open the preview/print route.

- [x] Keep the cards list free of print shortcuts; use card detail.

- [x] Keep render tests proving:

  - terminal cards do not expose print access;
  - admin completed and archived cards expose print access;
  - cancelled cards do not expose print access.

### Task 6: Browser And Print Verification

**Files:**

- Modify if needed: `app/static/css/print.css`
- Artifacts: `artifacts/ui-checks/`

- [ ] Run the full automated test suite.

  Command:

  ```bash
  source .venv/bin/activate
  python -m pytest
  ```

- [ ] Run `git diff --check`.

  Command:

  ```bash
  git diff --check
  ```

- [ ] Start the local app with a temporary/test database.

  Command:

  ```bash
  source .venv/bin/activate
  mkdir -p .test-runtime/print-ui-check
  EXTRUSION_DB_PATH=.test-runtime/print-ui-check/extrusion_terminal_print.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
  ```

  Do not run print UI checks against `data/extrusion_terminal.sqlite3`.

- [ ] Use Playwright/browser verification against a completed sample card.

  Save screenshots or generated PDF preview artifacts under `artifacts/ui-checks/`.

- [ ] Verify print layout characteristics.

  Check:

  - exactly two A4 pages for a normal card, with page 3+ only for pallet-summary overflow
  - front and back page break correctly
  - fields do not overlap
  - long text wraps/shrinks inside fixed boxes
  - back grid remains 120 rolls
  - summary fields are in the template bottom area
  - no app-only fields appear

- [x] Perform one physical printer rehearsal before claiming pilot readiness.

  Physical output was reviewed and accepted as near-perfect for the operational card. The app print functionality is complete. One workstation/computer prints the app output across two physical sheets while other computers print correctly; that remaining issue is workstation/browser/printer-driver/settings specific and is not an app print-output defect.

### Task 7: Update Milestone Documentation

**Files:**

- Modify: `IMPLEMENTATION_PLAN.md`
- Optionally modify: `README.md` if implementation confirms or changes persistent requirements

- [x] Mark Milestone 10 progress accurately.

  Print output may be treated as complete for the app after automated tests, browser verification, and the accepted physical-printer rehearsal.

- [x] Document any accepted deviations from the Excel template.

  Examples:

  - browser print margin adjustment
  - text wrapping/shrinking behavior
  - any printer-specific setup notes

- [ ] Keep future kiosk/silent-print configuration out of v1 completion unless implemented and verified.

## Verification Checklist Before Completion

Before saying print work is complete:

- [x] statuses outside completed/archived are blocked from print
- [x] cancelled cards are blocked from print
- [x] missing print-critical data is blocked with actionable messages
- [x] more than 120 rolls is blocked
- [x] completed printable card renders two normal pages
- [x] front page matches extrusion template structure
- [x] back page keeps 120-roll grid
- [x] roll cells show gross only
- [x] totals show tare, gross, and net
- [x] pallet summaries use numeric order, one-decimal gross/net totals, conditional `Без палет`, and all-blank omission
- [x] page-2 pallet blocks fit 8 whole rows each; overflow pages fit 48 whole rows and repeat card identification
- [x] timing shows start, stop, and active duration excluding pauses
- [x] app-only fields are absent
- [x] automated tests pass
- [x] browser/Playwright check captures relevant artifact
- [x] physical or PDF print rehearsal is reviewed against the template

## Open Non-Requirements

These are intentionally not part of v1:

- silent/kiosk direct printing
- terminal print/reprint controls
- per-roll date/shift capture
- per-roll net display
- overflow page for more than 120 roll-grid entries (pallet-summary overflow remains supported)
- modifying the Excel workbook
- writing app production data back to Excel
- adding app workflow metadata to print
- changing the source import/workbook process
