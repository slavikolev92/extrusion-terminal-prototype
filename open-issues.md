# Open Issues

## Purpose

This file records issues that occur as part of audits and reviews of the extrusion terminal app. Keep entries concise, actionable, and linked to the report or evidence where the issue was found.

## Issues

### OI-001 - Active machine queue is not normalized after finish/archive

- Status: open
- Severity: important
- Found in: Fast Software Audit, 2026-06-24
- Evidence:
  - `reports/fast-audit-20260624.md`
  - `artifacts/ui-checks/fast-audit-20260624/21-admin-planning-after-finish-gap.png`
  - `artifacts/ui-checks/fast-audit-20260624/24-terminal-queue-drawer-after-finish.png`

After order `3118` was completed/archived from Machine 1 sequence `1`, the remaining active order `3117` stayed at sequence `2`. Active machine queues must remain contiguous from `1`.

Recommended fix:

- Add regression tests for queue normalization after finish and cancel.
- Normalize the affected machine queue when a card leaves the active queue through finish, archive, or cancellation paths as appropriate.

### OI-002 - Admin save-all correction has weak visible confirmation

- Status: open
- Severity: minor
- Found in: Fast Software Audit, 2026-06-24
- Evidence:
  - `reports/fast-audit-20260624.md`
  - `artifacts/ui-checks/fast-audit-20260624/18-admin-card-corrections-saved.png`

Admin completed-card corrections persisted correctly, but the captured post-save page did not show an obvious success confirmation near the top of the page.

Recommended follow-up:

- Confirm during the full readiness audit whether a success notice is missing or only displaced by redirect/anchor behavior.
- If missing, add a clear success message for the admin save-all correction flow.

### OI-003 - Structured extrusion recipe display and export validation

- Status: open
- Severity: important
- Found in: Structured recipe redesign discussion, 2026-06-24

The shift-manager workbook will keep its current structure, but extrusion recipe
source cells `AM:AS` will use a structured text convention:

`[Material category] [Producer] [Grade/Brand] | [% of total layer]`

Example:

`LDPE Rompetrol B20/03 | 80%`

The app should keep storing and printing the imported source text as-is. In
parallel, the app should parse and normalize the recipe rows into clean internal
recipe-component records so the terminal/admin display and future app-side
exports can work from structured data. The print output remains unchanged and
continues to show the original imported source text.

Accepted implementation roadmap:

1. Lock the recipe contract.
   - Confirm approved material categories.
   - Confirm accepted text format, percent decimal rules, total-percent tolerance,
     target-gross behavior, and Bulgarian UI labels.
   - Record the contract before implementation plans are written.

2. Build the app parser.
   - Add a central Python parser for non-empty `AM:AS` recipe source cells.
   - Normalize extra spaces and parse category, planned raw material, and percent.
   - Return clear validation errors for malformed rows.
   - Add focused parser tests before downstream changes.

3. Add normalized recipe storage.
   - Keep original imported source fields on `cards`.
   - Add thin recipe-component storage derived from those fields.
   - Store source field, source text, material category, planned material, and
     recipe percent.
   - Do not add material pricing, inventory, costing, or ERP functionality.

4. Sync normalized rows from source fields.
   - Refresh normalized recipe rows on CSV import, overwrite re-import, and admin
     source recipe correction.
   - Ensure empty source cells remove derived rows and changed source cells update
     derived rows.
   - Preserve existing actual material and batch/lot production data.

5. Add the app release gate.
   - Block release when non-empty recipe rows are malformed.
   - Block release when parsed recipe percentages do not total `100%` within the
     accepted tolerance.
   - Keep imported draft storage permissive enough for admin correction before
     release.

6. Redesign terminal/admin recipe display.
   - Replace the rigid recipe grid with parsed columns:
     material category, planned raw material, percent, planned kg, actual material
     used, and batch/lot.
   - Calculate planned kilograms as recipe percent multiplied by target gross
     weight.
   - Keep existing actual material and batch/lot save behavior and loaded-version
     conflict checks.

6.5. Align app parser with Excel recipe-builder `N/A` omissions.
   - Allow final source cells such as `reLDPE | 80%` when the category is
     approved and producer/grade were intentionally omitted by the Excel
     builder.
   - Keep app-side validation limited to the final source-cell contract because
     the app does not import `RecipeCatalog`.
   - Preserve original source text for print and admin correction.
   - Keep malformed rows, invalid percentages, non-100 totals, and missing
     target gross blocked at release.

7. Verify with structured sample CSV data.
   - Create several sample orders using the new convention.
   - Verify import, admin review/correction, release, terminal display, actual
     material/batch save, completion behavior, and unchanged print output.
   - Add automated tests and at least one focused Playwright screenshot for the
     changed UI.

8. Add Excel export macro validation.
   - Update the read-only CSV export macro so it validates selected production
     rows before writing a CSV.
   - Add standalone selected-row validation and configured-range validation from
     `ExportConfig!FirstValidationRow`.
   - Validate `Database!G` as positive gross kilograms for every validated
     production-order row.
   - Validate printing `AB:AI` cells against `RecipeCatalogPrinting`; do not add
     printing fields to the extrusion-terminal CSV.
   - Validate extrusion `AM:AS` cells against the structured recipe contract and
     `RecipeCatalogExtrusion`.
   - Block CSV writing with a clear English row/order/column/value/reason
     message when validation fails.
   - Keep the macro read-only with respect to existing workbook production-order
     cells.

Immediate follow-up after Step 8:

- Address `OI-004` so the app release gate aligns with the workbook/export
  contract that `Database!G` is the only canonical target gross kilograms source.

### OI-004 - App target gross validation should align to canonical Database column G

- Status: open
- Severity: important
- Found in: OI-003 Step 8 export-validation design discussion, 2026-06-26
- Must follow: immediately after OI-003 Step 8 Excel export validation
- Evidence:
  - `docs/implementation-notes/oi-003-step-8-export-validation-interim.md`

The OI-003 Step 8 workbook/export validation design now treats `Database!G` as
the canonical target manufacturing weight for every future validated production
order. Column `G` must contain positive gross kilograms. Columns `H`, `I`, and
`J` are not authoritative for this purpose and should be ignored by the export
validator.

The current app release gate still accepts target gross from either `G/H` or
`I/J` when the unit looks kg-like. That broader app behavior was useful earlier,
but it no longer matches the workbook contract needed for controlled export and
future costing.

Recommended fix:

- After OI-003 Step 8 is complete, update app-side release validation and
  planned-kilogram calculations to use only imported `quantity_1`
  (`Database!G`) as positive gross kilograms.
- Stop using `unit_1`, `quantity_2`, or `unit_2` as alternate target gross
  sources.
- Update focused release-validation tests that currently accept `I/J` kg-like
  values.
- Preserve the app's role as a structural/operational safety backstop; do not
  add app-side workbook catalog validation.

### OI-005 - Consolidate workbook helper macro installation

- Status: open
- Severity: important
- Found in: workbook macro validation discussion, 2026-06-26
- Must consider after: OI-003 Step 8 Excel export validation
- Evidence:
  - `source-files/excel-macros/ExportExtrusionOrders.bas`
  - `interim-costing-process/source-files/recipe-builder-demo/modRecipeBuilderCascadingInstaller.bas`

The workbook helper macro workflow currently requires separate installation
paths for the recipe builder and export validation. In practice this is fragile:
the shift-manager should not have to know which helper module installs which
piece of workbook infrastructure, nor remember to run multiple setup macros in
the correct order.

The target workflow should have one installation command for all workbook helper
functionality needed by the pilot workbook. The underlying implementation may
still keep separate VBA modules for recipe-builder behavior, export validation,
and CSV export, but installation should be a single explicit operation that
ensures all required helper sheets, forms, event handlers, and export validation
prerequisites are present.

Recommended fix:

- Design a single workbook-helper installation entry point that installs or
  verifies both recipe-builder support and export-validation support.
- Keep catalog data preservation as a hard requirement; installation must not
  clear, seed, or rewrite reviewed catalog rows.
- Preserve the existing public export macro `ExportSelectedExtrusionOrdersCsv`.
- Avoid duplicate or competing `Database` worksheet event handlers.
- Make installation messages ASCII/English so VBA import/display remains
  reliable across workstations.
- Document one installation workflow for the shift-manager workbook.

### OI-006 - Restore Bulgarian workbook runtime messages safely

- Status: open
- Severity: important
- Found in: workbook macro validation discussion, 2026-06-26
- Must consider after: OI-005 workbook helper installation consolidation
- Evidence:
  - `source-files/excel-macros/ExportExtrusionOrders.bas`
  - `tests/test_excel_export_macro_contract.py`

The export-validation macro was temporarily converted to English-only messages
because raw Cyrillic string literals in imported `.bas` files displayed as
mojibake in Excel/VBE. This made validation messages unreadable on the target
workstation even though the validation behavior worked.

Installation/setup messages should remain English/ASCII for reliability and
supportability. Runtime messages that operators or shift managers use during
validation and export should be translated back to Bulgarian, but only with an
encoding-safe implementation that survives `.bas` import.

Recommended fix:

- Keep installation/setup messages in English/ASCII.
- Translate non-installation runtime messages to Bulgarian, including selected
  validation, configured validation, export validation failure, and row-level
  validation errors.
- Do not store raw Cyrillic literals directly in `.bas` source files unless the
  workbook import path is proven to preserve them.
- Use an encoding-safe approach such as `ChrW$`/Unicode helper functions, or a
  generated installer path that writes Unicode text inside Excel reliably.
- Keep static tests that prevent accidental raw Cyrillic in imported `.bas`
  source files until the safe message strategy is implemented and verified.
- Verify messages manually in a copied workbook on the target Excel
  workstation.
