# Fixed Pallet Print Table Design

Date: 2026-07-31

## Goal

Make every printed pallet-summary table retain fixed, predictable cell geometry
regardless of how many pallet rows it contains.

The change is limited to print presentation and its regression coverage. It
does not change pallet calculations, pallet ordering, page capacities, print
eligibility, production data, or database structure.

## Current Failure And Cause

The back-page lower summary is a CSS Grid containing the six-row production
summary and up to two pallet-summary tables. The overflow page is also a CSS
Grid. Neither grid explicitly opts out of the grid default that stretches child
items across the grid row.

The pallet cells already declare physical heights, but a table-cell height is
not an absolute cap when the table itself is stretched. Chromium distributes
the extra table height across its rows. Live print-mode measurements reproduced
the defect:

- one page-2 pallet row grew from `17.38px` to `86.88px`;
- two page-2 pallet rows each grew to `43.44px`;
- with eight pallet rows, the production-summary rows grew from `17.38px` to
  `26.06px`; and
- the single data row on the final overflow page grew to `907.30px`.

This is a CSS layout defect. The rendered values, grouping, splitting, and page
selection are correct.

## Accepted Print Contract

Each pallet table has exactly:

1. one header row containing `Палет`, `Ролки`, `Бруто, кг`, and `Нето, кг`;
2. one fixed-height data row for every pallet summary row assigned to that
   table; and
3. no filler rows or stretched empty area inside the table.

For one pallet, print one header and one data row. For two pallets, print one
header and two data rows. The table ends immediately after its last data row,
and unused page space remains blank below it.

The table and column widths remain fixed by the existing physical print layout
and never depend on the number of rows. Page-2 pallet blocks retain their
existing fixed widths, and an overflow table retains its existing fixed page
width. The change must not make either context wider or narrower.

The production-summary table on the left also retains its own row heights. A
short pallet table must not grow to match the production table, and a taller
pallet table must not grow the production table.

## Pagination

Keep the existing splitting rules:

- page 2 holds up to eight whole pallet rows in the middle block and eight in
  the right block;
- the right block is omitted when it has no rows;
- when more than sixteen pallet rows exist, page 2 contains no partial pallet
  summary and the complete summary starts on page 3; and
- each overflow page holds up to forty-eight whole rows and repeats the order
  identification plus pallet headings.

Every overflow table follows the same no-stretch rule. A partially filled final
overflow page prints only its header and remaining data rows, with blank page
space below. No row may be split, duplicated, or omitted.

The established renderer capacities remain implementation facts rather than
business limits. The CSS correction must preserve the current normal and
overflow A4 page counts.

## Chosen Approach

Keep the existing semantic HTML tables, Jinja rendering, print data builder,
and split capacities. Explicitly top-align children in both grid containers:

```css
.print-summary,
.print-page-pallet-overflow {
  align-items: start;
}
```

The declarations belong in each selector's existing rule rather than in a new
override block. This lets every table use its declared row heights and natural
content height while retaining current fixed widths and page placement.

Do not replace tables with positioned elements, create blank placeholder rows,
calculate visual heights in Python, or add JavaScript to the print route. Those
approaches would duplicate browser layout responsibility and introduce failure
modes without improving the required output.

## Testing And Verification

Add two layers of regression protection.

First, the focused print CSS test must require both grid containers to declare
`align-items: start`. This gives a fast failure if the essential layout contract
is removed.

Second, extend the guarded roll/pallet Playwright fixture and verifier with
printable cards that produce exactly one and exactly two pallet-summary rows.
In Chromium print mode, measure and compare:

- table widths for one-row, two-row, and full page-2 blocks;
- header and data-row heights for one-row, two-row, and full page-2 blocks;
- production-summary row heights beside sparse and full pallet blocks;
- all overflow data-row heights, especially the final sparse overflow page;
- exact source/rendered row counts with no filler rows;
- horizontal cell fit and A4 safe-boundary containment; and
- normal and overflow PDF page counts.

Capture page-2 evidence for the one- and two-row cases and the final sparse
overflow page under `artifacts/ui-checks/`. All browser fixtures must use a
temporary SQLite path under `.test-runtime/`; they must never open or modify the
runtime database.

Run the focused print and verifier-safety tests, JavaScript syntax checking,
the full Python suite, `git diff --check`, and the guarded live Playwright/PDF
verification before completion.

## Documentation And Migration Impact

Update the durable print reference and pallet-assignment implementation note to
state that pallet tables are content-height, fixed-row structures with no
stretching or filler rows on page 2 or overflow pages.

This is a display-only change. It adds no table, column, constraint, stored
value, or new interpretation of existing production data. No database
migration or production snapshot is required.

## Out Of Scope

- Changing pallet grouping, sorting, counts, gross totals, or net totals.
- Changing the `8 + 8` page-2 or `48` overflow capacities.
- Changing the front page, order header, 120-roll grid, or production-summary
  contents.
- Adding or persisting blank pallet rows.
- Redesigning the print card or changing print typography beyond the
  non-stretching alignment correction.
- Changing terminal, admin, production, or database behavior.
