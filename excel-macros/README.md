# Excel Export Macro

This folder contains the read-only CSV export macro for the shift-manager workbook.

## What It Does

- Reads selected rows from the `Database` worksheet.
- Exports only the extrusion pilot fields used by the app.
- Creates an `extracts` folder next to the `.xlsm` workbook if it does not exist.
- Writes a timestamped CSV such as `extrusion_orders_20260612_143022.csv`.
- Does not edit worksheet cells or write production data back to Excel.

## Install For Testing

1. Open `source-files/shift-manager-main-file.xlsm` in Excel.
2. Press `Alt+F11`.
3. In the VBA editor, choose `File > Import File...`.
4. Select `excel-macros/ExportExtrusionOrders.bas`.
5. Save the workbook as macro-enabled `.xlsm`.

## Run

1. Open the `Database` sheet.
2. Select one or more production-order rows, starting at row `5` or below.
3. Run macro `ExportSelectedExtrusionOrdersCsv`.
4. Import the created CSV from the app admin page.

The app still validates whether each row is usable for extrusion.
