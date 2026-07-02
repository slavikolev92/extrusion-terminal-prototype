# Production Actuals Prototype

This is a controlled-entry Excel/VBA prototype for operational-card actuals.

It demonstrates the behavior needed before changing the real shift-manager
workbook:

- the actuals cell is locked against normal manual editing;
- double-clicking the actuals cell opens a VBA form;
- if the cell already contains structured data, the form loads that data;
- saving the form rewrites one structured value into the same cell.

## Structured Cell Format

The prototype writes a versioned key/value string:

```text
v1; gross=1050; tare=5; rolls=10; net=1000; start=2026-07-01 08:15; stop=2026-07-01 10:40
```

This is intentionally more explicit than a positional pipe format such as:

```text
1050 | 1000 | 5 | 10
```

The key/value format is easier to read, safer to parse, and easier to extend
later without breaking old entries.

The prototype also recognizes the legacy pipe order:

```text
gross | net | tare | rolls
```

When a pipe value is opened, the form loads gross, tare, and rolls, recalculates
net, and saves back to the new `v1` key/value format.

## Install In A Test Workbook

Use a workbook copy first.

1. Open the test workbook.
2. Press `Alt+F11`.
3. Use `File > Import File...`.
4. Import `production-actuals-prototype.bas`.
5. Run `InstallProductionActualsPrototype`.
6. Save the workbook as `.xlsm`.

Excel may block form/event installation until this setting is enabled:

```text
File > Options > Trust Center > Trust Center Settings > Macro Settings >
Trust access to the VBA project object model
```

## Test Flow

After installation, Excel creates a `ProductionActualsPrototype` worksheet.

1. Try typing directly into `D2`. Excel should block manual editing because the
   cell is locked.
2. Double-click `D2`. The form should open with the existing sample data loaded.
3. Change gross, tare, rolls, start time, or stop time.
4. Confirm that net weight recalculates in the form.
5. Click `Save`.
6. Double-click `D2` again. The saved values should load back into the form.
7. Double-click blank `D3` to confirm new-entry behavior.

## Important Implementation Detail

The current recipe-builder forms set `TargetCell` after `UserForm_Initialize`.
If the `TargetCell` setter only stores the range, the form cannot load existing
cell data during initialization.

This prototype fixes that by loading inside the setter:

```vb
Public Property Set TargetCell(ByVal cell As Range)
    Set mTargetCell = cell
    LoadExistingValue
End Property
```

That pattern should be used for any controlled-entry form that needs to edit an
existing structured cell.

## Protection Caveat

Worksheet protection prevents normal accidental/manual edits. It is not strong
security. Someone with macro access or the worksheet password can still bypass
it.

The prototype uses `UserInterfaceOnly:=True` so macros can write to locked cells.
Excel does not persist that setting after the workbook is reopened, so a
production version should reapply protection in `Workbook_Open`.
