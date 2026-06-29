# Excel Export And Validation Macro

This folder contains the read-only CSV export and validation macro for the
shift-manager workbook.

## What It Does

- Validates selected `Database` rows before CSV export.
- Provides standalone selected-row validation.
- Provides configured-range validation from `ExportConfig!FirstValidationRow`.
- Validates printing ink/anilox cells in `Database!AB:AI` against
  `RecipeCatalogPrinting`.
- Validates extrusion recipe cells in `Database!AM:AS` against
  `RecipeCatalogExtrusion`.
- Requires `Database!G` to contain positive gross kilograms for each validated
  production order row.
- Exports only the extrusion-terminal CSV fields used by the app.
- Creates an `exports` folder next to the `.xlsm` workbook if it does not exist.
- Writes a timestamped CSV such as `extrusion_orders_20260626_143022.csv`.
- Does not edit production-order cells or write terminal production data back to
  Excel.

## Public Macros

- `InstallExportValidation`
  - Ensures `ExportConfig`, `RecipeCatalogPrinting`, and
    `RecipeCatalogExtrusion` exist with expected headers.
  - Creates missing sheets/headers only.
  - Preserves existing catalog/config values.
  - Does not create buttons.

- `ValidateSelectedExportRows`
  - Validates selected production-order rows on `Database`.
  - A production-order row is a row with a value in column `A`.

- `ValidateConfiguredExportRows`
  - Reads `ExportConfig!FirstValidationRow`.
  - Validates every production-order row from that row onward.

- `ExportSelectedExtrusionOrdersCsv`
  - Validates selected production-order rows.
  - Writes CSV only when validation passes.

## Required Helper Sheets

### `ExportConfig`

```text
Setting | Value | Notes
FirstValidationRow | 12206 | First Database row validated by ValidateConfiguredExportRows
```

The sheet is hidden during normal use. `FirstValidationRow` is the first
`Database` row that belongs to the new nomenclature period.

### `RecipeCatalogPrinting`

```text
Type | Value | Notes
```

Use `Type = Ink` for approved color identities and `Type = Anilox` for approved
anilox values.

Printing cells in `Database!AB:AI` may be:

```text
White
White/110
Pantone 485
Pantone 485/255
```

### `RecipeCatalogExtrusion`

```text
Category | Producer | GradeCode | Notes
```

Extrusion cells in `Database!AM:AS` use:

```text
[Category] [Producer] [GradeCode] | [%]
```

`Producer` or `GradeCode` values of `N/A` in the catalog are omitted from the
final `Database` cell text.

## Install For Testing

1. Open a copy of the shift-manager workbook in Excel.
2. Press `Alt+F11`.
3. In the VBA editor, choose `File > Import File...`.
4. Select `interim-costing-process/excel-tools/export-validation/ExportExtrusionOrders.bas`.
5. Run macro `InstallExportValidation`.
6. Set `ExportConfig!FirstValidationRow` to the first row of the new
   nomenclature period.
7. Save the workbook as macro-enabled `.xlsm`.

## Run

1. Open the `Database` sheet.
2. Select one or more production-order rows.
3. Run `ValidateSelectedExportRows` to check selected rows, or
   `ExportSelectedExtrusionOrdersCsv` to validate and export selected rows.
4. Run `ValidateConfiguredExportRows` to validate all production-order rows from
   `FirstValidationRow` onward.
5. Import the created CSV from the app admin page.

The app still validates imported/released extrusion data as a safety backstop.
App-side alignment to treat `Database!G` as the only target gross kg source is
tracked separately in `OI-004`.
