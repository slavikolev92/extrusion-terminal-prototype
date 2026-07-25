# Admin Visibility Design

This is the temporary design specification for Task 2 of the Shift Manager
downstream cleanup. Delete it after Task 2 is complete and its result is
recorded in `SHIFT_MANAGER_CLEANUP.md`.

## Goal

Make the final Shift Manager import fields visible and understandable across
the four admin surfaces without changing the import contract, database schema,
or production workflow.

## Scope

Task 2 covers:

- successful-row links on the import result page;
- ordered gross kilograms in unreleased planning and active machine queues;
- delivery date and ordered gross kilograms in the admin cards list;
- all four ordered amounts and four route sequences on card detail;
- the workbook label `Фалдиране`; and
- focused automated and live browser verification.

It does not cover terminal displays, printing, legacy-value conversion,
production snapshot profiling, or general admin redesign.

## Existing Behavior To Preserve

- The exact 29-column CSV header remains mandatory and ordered.
- `extrusion_sequence == "1"` remains the extrusion eligibility rule.
- Admin saves continue to use the existing loaded-version conflict check.
- Imported-field edits continue to preserve rolls, timing, tare, status,
  assignment, queue position, and terminal-entered material data.
- Import results remain compact; list pages do not expand to all 29 fields.
- Printing remains admin-only and intentionally unchanged in this task.

## Design

### Import Results

`fetch_import_batch_result()` will resolve the current card by joining the
persisted import-row order number to the unique `cards.order_number` value.
The returned row view model will expose a `card_id` only for `created` and
`updated` actions.

The order number will link to `/admin/cards/{card_id}` when that successful row
still resolves to a current card. Skipped and blocked rows remain plain text. A
successful historical row whose order number no longer resolves also remains
plain text instead of producing a broken link.

This intentionally avoids adding `card_id` or imported field snapshots to
`import_batch_rows`. Links reflect the current card relationship and do not
create a new migration.

### Planning

`fetch_cards_by_status()` already supplies `ordered_gross_kg`, so planning
requires no new database query.

The unreleased table will add a compact `Поръчано бруто, кг` column. Each active
machine queue card will add one compact `Поръчано бруто` line. Populated values
show the stored text followed by `кг`; blank values show `-` without a dangling
unit.

`app/static/css/app.css` will define the gross column width and increase the
unreleased table's narrow-screen minimum width enough to retain readable
columns and release controls.

### Admin Cards List

`fetch_admin_cards()` will select `delivery_date` and `ordered_gross_kg` in
addition to its current overview fields. The cards table will display
`Доставка` and `Поръчано бруто, кг`. Blank values show `-`.

Filtering, ordering, the 100-row limit, status presentation, and the existing
`Отвори` action remain unchanged.

### Admin Card Detail

The existing detail query, template, and generic `IMPORT_FIELDS` save path
already carry the four ordered fields and four route-sequence fields. Task 2
will preserve that structure and add complete regression coverage rather than
introducing another form or save endpoint.

The four ordered inputs are:

- `ordered_gross_kg`;
- `ordered_rolls`;
- `ordered_meters`; and
- `ordered_units`.

The four route inputs are:

- `printing_sequence`;
- `extrusion_sequence`;
- `rewinding_slitting_sequence`; and
- `confection_sequence`.

The visible label and shared import-field label for `extrusion_folding` will be
`Фалдиране`. Old input names such as `quantity_1`, `unit_1`, `quantity_2`,
`unit_2`, and `extrusion_flag` must not be rendered.

## Error And Empty-State Behavior

- Import-result links are optional presentation data; a missing card does not
  change import counts or turn the row into an error.
- Blank compact-display values use `-`.
- Existing import, validation, stale-write, duplicate-order, planning, and save
  messages remain unchanged.
- No fallback to old CSV fields or old stored-field semantics is introduced.

## Testing And Verification

Implementation will follow test-driven development:

1. Add assertions that fail against the current admin output.
2. Confirm the failures describe the missing Task 2 behavior.
3. Make the minimum query, template, label, and CSS changes.
4. Run the focused admin suite:

   ```bash
   .venv/bin/python -m pytest \
     tests/test_admin_routes.py \
     tests/test_admin_planning.py \
     tests/test_admin_card_review.py \
     tests/test_admin_card_detail_redesign.py -q
   ```

5. Run the import and persistence regression suite:

   ```bash
   .venv/bin/python -m pytest tests/test_baseline.py -q
   ```

6. Start the app against a temporary SQLite database, import the verified Shift
   Manager CSV, and inspect import, planning, cards, and detail pages.
7. Save at least one screenshot of each of those four surfaces under
   `artifacts/ui-checks/v2/admin/`.
8. Run `git diff --check` and review data integrity and user-visible messages.

The focused pre-change baseline is 94 passing tests.

## Migration Decision

Task 2 reads and displays columns already introduced by M001. The proposed
queries, templates, labels, tests, and CSS do not change persistent structure or
existing stored meaning. No new migration or production snapshot is expected
for this task.

## Completion Criteria

Task 2 is complete when:

- successful import rows link to their current cards when resolvable;
- planning displays ordered gross kilograms for drafts and active queues;
- the cards list displays delivery date and ordered gross kilograms;
- detail renders and saves all eight final ordered/route fields;
- `Фалдиране` is used and old input names are absent;
- focused and affected regression tests pass;
- all four admin surfaces are verified live using a temporary database;
- screenshots and `git diff --check` provide current evidence;
- no runtime or production database was touched; and
- the temporary cleanup tracker records the result and next task.

## User Acceptance Addendum: Fully Populated Order 26000

- Table headers carry the kilogram unit, so populated gross-weight cells in
  the planning draft table and technology-cards table render only the stored
  number. The active queue line keeps its explicit unit because it has no
  unit-bearing column header.
- The original V14.04 workbook remains read-only. A local one-row CSV derived
  from its newest verified orders uses the exact final 29-column contract.
- Order `26000` populates all 29 exported fields. Recipe values come from the
  workbook's `RecipeCatalogExtrusion`, use all seven recipe fields, and total
  exactly 100%.
- Verification compares all 29 CSV values to the temporary SQLite card and
  checks order `26000` on import results, planning, cards list, and card detail.
