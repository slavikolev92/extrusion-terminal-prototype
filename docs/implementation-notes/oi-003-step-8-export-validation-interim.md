# OI-003 Step 8 Export Validation Interim Decisions

Status: interim decision record, not an implementation plan.

Created: 2026-06-26.

This note records the export-validation direction agreed during the OI-003 Step
8 design discussion. It is intentionally a temporary working record so future
planning can resume from the agreed context if the chat context is lost.

No implementation has been approved yet. This file records the agreed design
direction that should feed the implementation plan.

## Background

OI-003 is the structured recipe work for the extrusion terminal pilot. Earlier
steps added app-side parsing, normalized recipe storage, release validation,
structured admin/terminal recipe display, and structured sample CSV
verification.

Step 8 remains open: add Excel export-side validation before CSV export.

The app already has validation guardrails. Import remains permissive enough to
allow draft cards to be corrected, while release to the terminal blocks malformed
structured recipe rows, invalid recipe totals, and invalid target gross weight.
That app-side validation is necessary as a safety net, but it is not the desired
primary user experience. Shift managers should be told that workbook data is
wrong while still working in Excel, before a CSV is written and before they try
to import or release cards in the app.

The Excel recipe builder remains useful as a data-entry aid, but it is not the
final validation gate. It cannot catch direct edits, pasted rows, copied legacy
rows, or rows entered without using the builder. The export-side validation must
therefore be independent of the builder.

As of the current workbook-builder design, the builder supports both printing
and extrusion entry:

- `Database!AB:AI` - printing ink/anilox station cells;
- `Database!AM:AS` - extrusion raw-material recipe cells.

The builder owns the double-click routing for these ranges, but Step 8 remains
focused on export-side validation and export behavior.

The current recipe-builder macro was checked during this discussion. It creates
or preserves:

- `RecipeCatalogExtrusion` with `Category | Producer | GradeCode | Notes`;
- `RecipeCatalogPrinting` with `Type | Value | Notes`.

It routes `Database!AB:AI` to the printing builder and `Database!AM:AS` to the
extrusion builder. The printing builder writes either `Ink` or `Ink/Anilox`,
depending on whether an anilox value is selected.

## Agreed Decisions

### 1. Recipe Builder Is Out Of Scope For This Slice

The recipe builder stays separate from Step 8.

It remains responsible only for helping users enter structured text into the
workbook. It should not become the export validation gate and should not be
expanded with additional validation behavior as part of this slice.

Implication: Step 8 work should focus only on the export-side macro bundle and
its validation behavior. The existing recipe-builder installer and helper sheet
should not be changed unless a later decision explicitly reopens that scope.

### 2. Export-Side Module Is The Focus

The Step 8 work belongs on the export side of the workbook workflow.

The export-side installable macro bundle should include:

- the CSV export macro;
- reusable validation logic;
- standalone validation macro entry points.
- a simple setup macro that ensures required backend workbook prerequisites
  exist.

Implication: the export-side bundle becomes the place where shift managers can
both validate workbook rows and export valid selected rows to CSV.

The CSV export schema remains the extrusion-terminal schema. Printing fields
`AB:AI` are validated for workbook/costing discipline but are not added to the
CSV export because there is no printing terminal and the current app import is
for the extrusion terminal workflow only.

Printing fields remain in the shift-manager workbook and may be used later for
month-end unit-cost calculations from the workbook itself.

### 3. Validation Must Be Reusable

Validation should not be embedded only inside the export command.

The same validation logic should be callable in two ways:

- directly by the shift manager as a standalone validation action;
- automatically by the export macro before a CSV is written.

Rationale: shift managers may want to check a newly entered or copied production
order before they are ready to export. Export must still call the same validation
because the standalone check is optional.

Implication: the VBA implementation should avoid duplicating validation logic
between "validate" and "export". Public macros can call shared private
validation functions.

### 4. Export Must Block On Validation Failure

CSV export must be all-or-nothing for the selected rows.

If any selected row fails validation, no CSV should be written.

Standalone validation does not "block" a workbook action. It reports whether the
validated rows pass or fail. The export macro is the action that must stop when
the shared validation returns failures.

Missing required catalog matches, malformed cell structure, invalid percentages,
and invalid column `G` values are validation errors. They make standalone
validation fail and prevent CSV writing only when validation is run as part of
export.

Rationale: partial export would create ambiguity about what was sent to the app
and what was left behind. A failed export should leave the workbook and output
folder unchanged except for the user-visible validation message.

Implication: validation must run before CSV text is built and before any output
file is created.

Validation failure output should be a clear message box only. Step 8 should not
write a validation report sheet and should not create a separate validation
report file.

The message should include enough context for correction, such as row number,
order number, column, offending value, and reason. If many errors exist, the
message may show a capped list and state that additional errors remain.

Validation messages should be in Bulgarian, with technical workbook references
such as column letters, row numbers, sheet names, and raw offending values
preserved as-is.

The message box should show no more than the first 10 validation errors. If more
than 10 errors exist, the message should state the total error count and make
clear that only the first 10 are shown.

Standalone validation success should also use a simple message box:

- selected-row validation reports that the selected production orders passed and
  includes the validated order count;
- configured-range validation reports that all production orders from
  `FirstValidationRow` onward passed and includes the validated order count.

The export macro should keep a successful export message with exported row count
and output file path.

Rationale: message-box-only output keeps the macro simple and preserves the
read-only posture with respect to workbook production data. A separate report
workflow can be added later only if message boxes prove insufficient.

### 5. There Are Two Validation Modes

Validation should support two operating modes:

1. Validate selected rows.
2. Validate all rows from a configured starting row onward.

Selected-row validation is for focused checking and for export, because the
current export workflow is selection-based.

Range validation is for the new nomenclature period. Once the first row of the
new month/new convention is known, shift managers should be able to validate all
future rows from that row onward without touching older historical data.

`FirstValidationRow` only controls configured-range validation. If a user
explicitly selects production-order rows and runs selected-row validation or
export, those selected rows should be validated under the current rules even if
they are above `FirstValidationRow`.

Implication: the export-side macro bundle should expose separate public macros
for selected-row validation and configured-range validation.

`Validate all` means validating every production order from `FirstValidationRow`
onward. There is no separate product-level exception or alternate range
definition.

A production order row is identified by a non-empty order number in
`Database!A`. Configured-range validation should validate rows from
`FirstValidationRow` onward only when column `A` has a value. Blank rows without
an order number are not production orders and should not be validated.

Selected-row export must also require an order number in `Database!A`; rows
without an order number must not be exported.

Approved public macro entry points:

1. installation/setup macro;
2. validation for selected rows;
3. validation for all rows from the configured start row;
4. export macro.

The export macro should keep the existing public name
`ExportSelectedExtrusionOrdersCsv` if practical, so existing workbook wiring is
less likely to break. The exact public names for the setup and standalone
validation macros can be finalized during implementation planning, but the
four-command shape is approved.

The export-side work should remain one installable module/bundle. The preferred
implementation is to update the existing `ExportExtrusionOrders.bas` module in
place rather than splitting validation into a separate `.bas` file. Internal VBA
functions can still be organized by responsibility, but operationally there
should be one export-side module to import/install.

### 6. A Configuration Helper Sheet Is Appropriate

The workbook should have a small export configuration/helper sheet.

Its primary purpose is to store the first `Database` row that belongs to the new
nomenclature period. Rows before this configured start row are historical and
are not validated by the "validate all" mode.

Rationale: hard-coding the cutoff row in VBA would require macro edits when the
starting row changes. Asking the shift manager to enter the row every time would
be repetitive and error-prone.

Implication: the export-side installation/setup should create or ensure this
configuration sheet and place the start-row setting somewhere clear.

Approved configuration shape:

- sheet name: `ExportConfig`;
- sheet visibility: hidden during normal use;
- settings:
  - `FirstValidationRow` - first `Database` row validated by the configured
    range/"validate all" macro.

The sheet should use a simple layout:

```text
Setting | Value | Notes
FirstValidationRow | 12206 | First Database row validated by ValidateAll
```

The setup macro should create the sheet/header/setting if missing and preserve an
existing `FirstValidationRow` value if the sheet already exists. No export-folder
setting and no max-error setting are needed at this stage.

If the configured-range validation macro runs while `FirstValidationRow` is
missing, invalid, or lower than the first production-order row, validation should
stop with a clear message rather than guessing a range.

The export-side setup macro may create `ExportConfig` if missing. If
`ExportConfig` already exists, it must preserve existing data and must not
overwrite the configured `FirstValidationRow` value.

`ExportConfig` must use the exact expected structure. The setup/validation code
should not guess alternate columns if the sheet exists with unexpected headers.

### 7. Historical Rows Are Not Being Cleaned Up

The validation work is not a historical data cleanup.

Rows before the configured start row can remain in the legacy format, even
though they would fail the new validation rules.

Rationale: the new nomenclature is for future production orders. Existing
historical rows should not create a cleanup burden or block the workbook from
being used.

Implication: "validate all" must start from the configured row, not from the
beginning of the `Database` sheet.

### 8. Validate Fixed Raw-Material Columns Directly

Validation should not inspect whether a row has an extrusion or printing
operation. It should validate the fixed material columns directly.

Columns of interest:

- printing ink/anilox stations: `AB:AI`;
- extrusion raw materials: `AM:AS`.

If a row is selected, or if it is within the configured validation range, these
columns are always considered. If a section has no data, that section can pass.
If a section has data, that data must follow the relevant structure.

Rationale: if a row has no extrusion operation, there should be no extrusion
material data in `AM:AS`. If a row has no printing operation, there should be no
printing data in `AB:AI`. If such data is present anyway, the workbook row is
dirty and should be corrected rather than hidden from validation.

Implication: validation should not depend on operation flags or app importer
extrusion detection. The relevant workbook columns are the validation contract.

### 9. Blank Material Sections Can Pass

Because validation does not inspect operation flags, fully blank material
sections are valid.

Rules:

- if all `AM:AS` cells are blank, extrusion recipe validation passes for that
  row;
- if all `AB:AI` cells are blank, printing material validation passes for that
  row;
- if any cells in a section contain data, that section must satisfy its
  validation rules.

Rationale: a selected row may be printing-only, extrusion-only, neither, or may
still be in progress. Blank material sections should not fail just because the
row is selected.

Implication: the extrusion `100%` total rule only applies when there is at least
one non-empty extrusion recipe cell in `AM:AS`.

If a material section has at least one non-empty cell, every non-empty cell in
that section must validate. Empty slots inside the same section remain allowed.

Validation does not check operation flags. If material data exists in a section
even though the related operation was not selected, validation should treat that
data as real and require it to be valid. The shift manager must either correct
the operation/data or delete stale material values.

Whitespace-only cells count as blank. This avoids invisible-cell failures while
preserving strict matching for visible field values. Leading/trailing whitespace
around a full cell can be ignored during parsing; internal spaces inside field
values remain meaningful and must match the catalog/contract.

### 10. Extrusion Validation Uses The Structured Recipe Contract

For non-empty extrusion recipe cells in `AM:AS`, validation should follow the
structured extrusion recipe contract already used by the app:

```text
[Material/Additive Category] [Producer or Brand] [Full Commercial Grade/Code] | [% of final product]
```

Accepted behavior:

- split on the final `|`;
- the text before the final `|` is the material identity;
- the first token of the material identity is the material category;
- category matching is case-insensitive and normalizes to the approved spelling;
- producer and/or grade may be omitted, so category-only rows such as
  `reLDPE | 80%` are valid;
- percentage must include `%`;
- dot and comma decimals are accepted;
- percentage must be greater than `0`;
- all non-empty extrusion recipe percentages in `AM:AS` must total exactly
  `100%`.

Approved extrusion categories from the locked app contract:

- `LDPE`
- `LLDPE`
- `MDPE`
- `reLDPE`
- `Antistatic`
- `Masterbatch`
- `Filler`
- `UV`
- `Antislip`

Implication: malformed extrusion rows should be caught before CSV export rather
than later at app release.

### 10.1. Export Macro Also Validates Against `RecipeCatalogExtrusion`

Workbook/export validation must be stricter than app validation for extrusion
materials because the workbook has access to the extrusion recipe catalog.

The extrusion catalog sheet for export validation is:

```text
RecipeCatalogExtrusion
```

Export validation should not read the older `RecipeCatalog` sheet name as a
fallback. The recipe-builder installer owns migration from the old
`RecipeCatalog` name to `RecipeCatalogExtrusion`.

The export macro should validate both:

1. the structural recipe contract described above; and
2. whether the material identity before `|` is present in
   `RecipeCatalogExtrusion`.

The app remains responsible only for structural/operational safety:

- approved category;
- parseable delimiter and percentage;
- usable normalized fields;
- total recipe percentage;
- target gross quantity needed for app release.

The app does not own or import `RecipeCatalogExtrusion`, so it should not try to
validate producer names, grade codes, or producer/grade pair correctness.

The workbook macro is different. It can and should enforce that the exported
source text matches the workbook catalog. For example:

```text
LDPE WrongProducer B20/03 | 77%
```

must fail export unless the material identity `LDPE WrongProducer B20/03` can be
built from a row in `RecipeCatalogExtrusion`. If the shift manager adds that row
to `RecipeCatalogExtrusion`, it becomes workbook-approved data and can be
exported.

Allowed extrusion material identities should be built from
`RecipeCatalogExtrusion` rows:

```text
Category | Producer | GradeCode | Notes
```

The allowed identity is:

```text
Category Producer GradeCode
```

with `Producer` and/or `GradeCode` omitted when the catalog value is the control
value `N/A`. Internal spaces inside catalog values are meaningful and should not
be normalized away.

Rationale: the app checks whether it can safely use the data. The workbook macro
checks whether the workbook data conforms to the workbook's approved catalogs
before the data ever reaches the app.

Implication: structural-only extrusion validation is not acceptable for the
export macro. Catalog-based validation includes structural validation and should
be the export-side rule.

The export-side setup macro may create `RecipeCatalogExtrusion` with headers
`Category | Producer | GradeCode | Notes` if the sheet is missing. If the sheet
already exists, the setup macro must preserve existing catalog rows and must not
seed, clear, overwrite, or "fix" catalog data.

`RecipeCatalogExtrusion` must match the exact structure created by the
recipe-builder installer:

```text
Category | Producer | GradeCode | Notes
```

If the sheet exists with missing or unexpected headers, validation/setup should
raise a clear error rather than guessing column positions or silently using
malformed catalog data.

The export-side setup macro should not rename older catalog sheets. The
recipe-builder installer owns any old `RecipeCatalog` to
`RecipeCatalogExtrusion` migration.

### 11. Printing Validation Uses `RecipeCatalogPrinting`

Printing validation applies to printing ink/anilox station cells in `AB:AI`.
Solvents are not entered per order in the shift-manager workbook and are not
validated in these fields.

The expected printing cell forms are:

```text
[Ink / Color Identity]/[Anilox lines/cm]
[Ink / Color Identity]
```

Printing uses `/` as the delimiter, not `|`, because that preserves the current
way the second shift manager already enters color/anilox values in the workbook.
This differs from extrusion, where `|` remains the delimiter between material
identity and percentage.

The ink/color identity is mandatory. The anilox value is optional.

The approved catalog sheet is:

```text
RecipeCatalogPrinting
```

The catalog structure is:

```text
Type | Value | Notes
```

Rows with `Type = Ink` define approved ink/color identities. Rows with
`Type = Anilox` define approved anilox roller values.

For each non-empty `AB:AI` cell:

- if `/` is not present, the full cell value must exist in
  `RecipeCatalogPrinting` where `Type = Ink`;
- if `/` is present, there must be exactly one `/`;
- the value before `/` must exist in `RecipeCatalogPrinting` where `Type = Ink`;
- when `/` is present, the value after `/` must be non-empty and must exist in
  `RecipeCatalogPrinting` where `Type = Anilox`.

Example valid entries:

```text
White
White/110
Pantone 485
Pantone 485/255
Reflex Blue/110
```

There is no percentage validation and no total validation for printing.

Rationale: printing material cost/invoicing needs an approved ink/color
identity. The anilox value is optional because it is not required for the current
costing goal, but when it is entered it should still be controlled through the
same printing catalog. Solvents are handled outside these per-order workbook
fields as monthly allocated consumption, not as `AB:AI` station entries.

Implication: the export-side validator must read `RecipeCatalogPrinting`, filter
approved values by `Type`, and validate both sides of the printing cell
delimiter without attempting to validate solvents in `AB:AI`.

The export-side setup macro may create `RecipeCatalogPrinting` with headers
`Type | Value | Notes` if the sheet is missing. If the sheet already exists, the
setup macro must preserve existing catalog rows and must not seed, clear,
overwrite, or "fix" catalog data.

`RecipeCatalogPrinting` must match the exact structure created by the
recipe-builder installer:

```text
Type | Value | Notes
```

If the sheet exists with missing or unexpected headers, validation/setup should
raise a clear error rather than guessing column positions or silently using
malformed catalog data.

### 11.1. Catalog Matching Should Be Strict

Validation should not become a fuzzy matching or autocorrection system.

The only accepted whitespace tolerance is around structural boundaries:

- leading/trailing whitespace around the full cell may be ignored;
- whitespace immediately before or after the delimiter may be ignored;
- leading/trailing whitespace around an extracted field value may be ignored.

Internal spaces inside a field value are meaningful and must not be normalized.
For example, `1 10` must not be treated as `110`, and an ink/color identity with
different internal spacing from the catalog should fail validation.

The same principle applies to extrusion catalog-facing text once catalog-based
extrusion validation is discussed: if a value is in a recipe catalog, the
workbook source text should use that value exactly, apart from harmless
surrounding spaces at delimiters.

Rationale: the recipe builder exists to produce canonical workbook text. If a
shift manager manually edits or pastes an ambiguous value, validation should
make them fix it rather than guessing what they meant. Fuzzy matching creates
more edge cases than it solves and weakens the catalog as the authority.

Implication: the implementation should prefer exact catalog comparisons after
only simple trimming around parsed parts. It should report mismatches rather
than rewriting cells or silently accepting near-matches.

Catalog value matching is case-sensitive after trimming. This keeps the rule
simple for shift managers and implementers: the value in `Database` must match
the value in the relevant recipe catalog exactly. The recipe builder should
produce these exact values during normal use.

### 12. Column G Is Canonical Target Gross Kilograms

Column `G` in `Database` is the canonical target production quantity.

It must mean gross kilograms. It should not be interpreted as pieces, rolls, net
kilograms, or any other unit.

Column `H` is not meaningful for this validation because `G` is required to be
gross kilograms by convention. Columns `I` and `J` may contain whatever
secondary quantity information the shift manager needs and should be ignored by
this validation.

Rationale: the app needs one stable target quantity for planned recipe kilograms
and production expectations. Operationally, orders must be translated into gross
kilograms before entry in column `G`, even if the commercial order was discussed
in net kilograms, pieces, or rolls.

Implication: shift-manager training must emphasize that column `G` is always
gross kilograms. The export-side validation should validate `G` directly instead
of looking for kg-like units in `H`, `I`, or `J`.

Column `G` is required for every validated row. If a row is selected for
validation/export, or if it falls within the configured "validate all" range,
`G` must contain a positive numeric gross-kilogram value. This applies even when
`AB:AI` and `AM:AS` are blank.

Rationale: Step 8 now supports not only app import quality, but also the broader
workbook-costing goal. If `G` is the canonical holder of target manufacturing
weight, every future validated production-order row must have a usable positive
gross weight there.

Important app-side note: the current app release gate accepts target gross from
`G/H` or `I/J` when the unit looks kg-like. The Step 8 export-validation
decision is stricter and uses `G` only. This app-side mismatch is tracked as
`OI-004` and should be handled immediately after OI-003 Step 8.

### 13. Export Folder Is Not Configurable

The export folder should not be configurable through the helper sheet.

The agreed direction is to use a fixed output folder name and not spend design
or implementation effort on making the export folder configurable.

Implication: the export configuration sheet should not include an export-folder
setting.

The fixed output folder name is:

```text
exports
```

The current macro uses an `extracts` folder. Step 8 should change that fixed
folder name to `exports` while keeping it non-configurable.

## Design-Closure Check

The design questions raised during this discussion are considered resolved for
OI-003 Step 8. This section records closed topics and the one immediate
post-Step-8 follow-up.

### Printing Cell Parsing

No current open questions. Printing cells are validated against
`RecipeCatalogPrinting` for both ink/color identity and anilox value. The macro
must not rewrite or canonicalize workbook cells.

### Configuration Sheet

No current open questions. Approved shape is documented in decision 6.

### Validation Output

No current open questions. Approved behavior is message-box-only validation
output for Step 8.

### Installer And Buttons

The export-side setup macro should only ensure backend workbook prerequisites
exist. This includes `ExportConfig` and any other required helper sheets/headers
needed for validation to run.

The setup macro should not create visible workbook buttons. Button placement and
workbook UI wiring will be handled manually outside this implementation.

Approved setup behavior:

- ensure `ExportConfig` exists with `Setting | Value | Notes`;
- ensure `FirstValidationRow` exists in `ExportConfig` if missing, while
  preserving any existing value;
- ensure `RecipeCatalogPrinting` exists with `Type | Value | Notes`;
- ensure `RecipeCatalogExtrusion` exists with
  `Category | Producer | GradeCode | Notes`;
- do not seed real catalog values;
- do not clear, overwrite, or modify existing catalog rows;
- do not create workbook buttons;
- do not rename old catalog sheets.

### App Contract Alignment

The export-side validation decision treats `G` as the only target gross kg
source. The current app release logic can also use `I/J` when those cells appear
to be kg-like.

Approved decision: do not mix this app-side contract cleanup into OI-003 Step 8.
Create and track it as the immediate follow-up after the Excel export validation
work.

Tracking issue:

- `OI-004 - App target gross validation should align to canonical Database column G`

Expected follow-up direction:

- app release validation should use only imported `quantity_1` (`Database!G`) as
  positive gross kilograms;
- app planned-kilogram calculations should align to the same source;
- `unit_1`, `quantity_2`, and `unit_2` should stop acting as alternate target
  gross sources;
- the app should remain a structural/operational safety backstop and should not
  add workbook catalog validation.

## Current Non-Scope

This interim decision record does not approve:

- changes to the recipe builder;
- app-side catalog management;
- adding printing fields to the extrusion-terminal CSV export;
- adding a printing terminal or app-side printing import workflow;
- pricing, costing, inventory, or ERP functionality;
- users, roles, permissions, or authentication;
- print-layout changes;
- writing terminal-entered production data back to Excel;
- historical workbook row cleanup;
- automatic rewriting or normalization of existing workbook cells;
- a final implementation plan.
