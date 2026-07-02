# Shift Manager Native Macros

This bundle preserves and homogenizes the native VBA behavior already present
in the shift-manager workbooks.

The canonical native behavior follows Marko's current workbook:

- `Database.Worksheet_Change` watches `C2`, `D2`, and `F2`.
- Changing those cells reapplies filters over `Database!A4:AX30000`.
- `Technology Cards` print buttons keep their existing operation-specific
  macro names.
- Back-side print range is `AS55:BC105`.

This file is installed by the master workbook-tools installer. It should not
be imported as a random standalone utility unless testing a workbook copy.
