# OI-003 Step 8 Excel Export Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable Excel-side validation to the shift-manager export macro so workbook rows are validated before CSV export and can also be validated directly by shift managers.

**Architecture:** Update the existing `ExportExtrusionOrders.bas` module in place as the single export-side installable module. Add a setup macro, selected-row validation, configured-range validation, shared validation helpers, catalog loaders, and export gating while keeping the CSV schema extrusion-terminal-only. Add lightweight repository tests for the macro contract and document the manual Excel verification path because VBA cannot be executed by the Linux pytest suite.

**Tech Stack:** Excel VBA `.bas` module, Excel `.xlsm` workbook, FastAPI app remains unchanged in this step, pytest for static repository checks, manual Excel verification on a copied workbook.

---

## Source Context

Read these before implementing:

- `AGENTS.md`
- `open-issues.md`
- `docs/implementation-notes/oi-003-step-8-export-validation-interim.md`
- `docs/implementation-notes/structured-recipe-contract.md`
- `source-files/excel-macros/ExportExtrusionOrders.bas`
- `source-files/excel-macros/README.md`
- `interim-costing-process/source-files/recipe-builder-demo/README.md`
- `interim-costing-process/source-files/recipe-builder-demo/modRecipeBuilderCascadingInstaller.bas`

Do not mutate:

- `data/extrusion_terminal.sqlite3`
- the real workbook at `interim-costing-process/source-files/test-shift-manager-file.xlsm`

Use a copied workbook under `.test-runtime/oi-003-step-8/` for manual Excel verification.

Do not stage or commit unless the user explicitly asks.

## File Structure

Modify:

- `source-files/excel-macros/ExportExtrusionOrders.bas`
  - Keep this as the single installable export-side module.
  - Keep public export macro name `ExportSelectedExtrusionOrdersCsv`.
  - Add public setup and validation macros.
  - Add private helpers for sheet setup, strict header validation, catalog loading, row selection/range building, row validation, and message formatting.

- `source-files/excel-macros/README.md`
  - Update export folder from `extracts` to `exports`.
  - Document setup, validation macros, config sheet, catalog dependencies, and manual test workflow.

- `open-issues.md`
  - After implementation and verification, update OI-003 Step 8 text to reflect that validation now covers printing `AB:AI`, extrusion `AM:AS`, catalog checks, `G`, and the fixed `exports` folder.
  - Keep `OI-004` open as immediate follow-up.

Create:

- `tests/test_excel_export_macro_contract.py`
  - Static repository-level checks for the `.bas` macro contract.
  - These tests do not prove VBA runtime behavior, but they protect public macro names, critical constants, fixed CSV schema boundaries, and docs alignment.

Do not create:

- A separate validation `.bas` module.
- App-side catalog management.
- Printing CSV fields.
- App release-gate changes for `G`; that is `OI-004`.

## Chosen Public Macro Names

Use these public macros:

```vb
Public Sub InstallExportValidation()
Public Sub ValidateSelectedExportRows()
Public Sub ValidateConfiguredExportRows()
Public Sub ExportSelectedExtrusionOrdersCsv()
```

Keep `ExportSelectedExtrusionOrdersCsv` for compatibility with any existing workbook wiring.

## Core Validation Contract

Validation row scope:

- `ValidateSelectedExportRows` validates selected production rows on `Database`.
- `ExportSelectedExtrusionOrdersCsv` validates selected production rows before writing CSV.
- `ValidateConfiguredExportRows` reads `ExportConfig.FirstValidationRow` and validates every production order from that row onward.
- A production order row is a row `>= 5` where `Database!A` has a non-empty order number.
- Blank selected rows with no order number are ignored; if no production rows remain, show a Bulgarian message and stop.

Every validated row:

- `Database!G` must contain a positive numeric gross-kilogram value.
- `H`, `I`, and `J` are ignored for validation.
- `AB:AI` are printing ink/anilox station fields.
- `AM:AS` are extrusion raw-material recipe fields.
- Operation flags are ignored.
- Whitespace-only material cells count as blank.

Printing `AB:AI`:

- Blank section passes.
- If a cell is non-empty, validate it.
- Valid forms:
  - `Ink`
  - `Ink/Anilox`
- If `/` is present, exactly one `/` is allowed.
- Ink is mandatory and must match `RecipeCatalogPrinting` where `Type = Ink`.
- Anilox is optional, but if present must be non-empty and match `RecipeCatalogPrinting` where `Type = Anilox`.
- Catalog `Value` matching is case-sensitive after trimming only leading/trailing spaces around parsed parts.

Extrusion `AM:AS`:

- Blank section passes.
- If any non-empty extrusion cell exists, every non-empty extrusion cell validates and percentages must total exactly `100%`.
- Split on the final `|`.
- Text before final `|` is material identity.
- Text after final `|` is percentage.
- First token of identity must be an approved category.
- Material identity must match an allowed identity built from `RecipeCatalogExtrusion`.
- Percentage must include `%`, accept dot/comma decimal separators, and be greater than `0`.
- Approved categories:
  - `LDPE`
  - `LLDPE`
  - `MDPE`
  - `reLDPE`
  - `Antistatic`
  - `Masterbatch`
  - `Filler`
  - `UV`
  - `Antislip`

Catalogs:

- `RecipeCatalogPrinting` exact headers: `Type | Value | Notes`
- `RecipeCatalogExtrusion` exact headers: `Category | Producer | GradeCode | Notes`
- `ExportConfig` exact headers: `Setting | Value | Notes`
- Existing data must be preserved.
- Setup may create missing sheets and headers only.
- Setup must not seed real catalog values.
- Do not read legacy `RecipeCatalog`; recipe-builder installer owns old-name migration.

Messages:

- Bulgarian message boxes.
- Failed validation shows at most first 10 errors and total error count if more exist.
- Each error should identify row, order number, column, offending value where useful, and reason.
- Standalone validation reports pass/fail.
- Export writes no CSV if validation fails.

CSV:

- Keep existing extrusion-terminal CSV headers.
- Do not add printing fields.
- Output folder fixed to `exports`.

---

### Task 1: Add Static Macro Contract Tests

**Files:**
- Create: `tests/test_excel_export_macro_contract.py`

- [ ] **Step 1: Create failing static tests**

Create `tests/test_excel_export_macro_contract.py`:

```python
from __future__ import annotations

import re
from pathlib import Path


MACRO_PATH = Path("source-files/excel-macros/ExportExtrusionOrders.bas")
README_PATH = Path("source-files/excel-macros/README.md")


def macro_text() -> str:
    return MACRO_PATH.read_text(encoding="utf-8")


def readme_text() -> str:
    return README_PATH.read_text(encoding="utf-8")


def array_body(text: str, assignment_name: str) -> str:
    pattern = rf"{assignment_name}\s*=\s*Array\((.*?)\)"
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    assert match, f"{assignment_name} array not found"
    return match.group(1)


def quoted_values(body: str) -> list[str]:
    return re.findall(r'"([^"]*)"', body)


def test_export_macro_exposes_required_public_entry_points():
    text = macro_text()

    assert "Public Sub InstallExportValidation()" in text
    assert "Public Sub ValidateSelectedExportRows()" in text
    assert "Public Sub ValidateConfiguredExportRows()" in text
    assert "Public Sub ExportSelectedExtrusionOrdersCsv()" in text


def test_export_macro_uses_approved_workbook_sheets_and_ranges():
    text = macro_text()

    for expected in (
        'EXPORT_FOLDER_NAME As String = "exports"',
        'DATABASE_SHEET_NAME As String = "Database"',
        'CONFIG_SHEET_NAME As String = "ExportConfig"',
        'PRINTING_CATALOG_SHEET_NAME As String = "RecipeCatalogPrinting"',
        'EXTRUSION_CATALOG_SHEET_NAME As String = "RecipeCatalogExtrusion"',
        'CONFIG_FIRST_VALIDATION_ROW As String = "FirstValidationRow"',
        'PRINTING_FIRST_COLUMN As String = "AB"',
        'PRINTING_LAST_COLUMN As String = "AI"',
        'EXTRUSION_FIRST_COLUMN As String = "AM"',
        'EXTRUSION_LAST_COLUMN As String = "AS"',
    ):
        assert expected in text

    assert 'EXPORT_FOLDER_NAME As String = "extracts"' not in text


def test_export_csv_schema_remains_extrusion_terminal_only():
    text = macro_text()
    headers = quoted_values(array_body(text, "headers"))
    source_columns = quoted_values(array_body(text, "sourceColumns"))

    assert headers == [
        "order_number",
        "order_date",
        "delivery_date",
        "customer",
        "city",
        "product_type",
        "quantity_1",
        "unit_1",
        "quantity_2",
        "unit_2",
        "product_form",
        "material",
        "size_thickness",
        "notes",
        "extrusion_flag",
        "extrusion_folding",
        "extrusion_next_operation",
        "extrusion_treatment",
        "raw_material_a",
        "raw_material_b",
        "raw_material_c",
        "linear_pe",
        "antistatic",
        "masterbatch",
        "chalk",
        "packaging_method",
    ]
    assert source_columns == [
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "J",
        "K",
        "L",
        "M",
        "N",
        "W",
        "AJ",
        "AK",
        "AL",
        "AM",
        "AN",
        "AO",
        "AP",
        "AQ",
        "AR",
        "AS",
        "AT",
    ]
    assert "AB" not in source_columns
    assert "AI" not in source_columns


def test_export_macro_documents_validation_and_exports_folder():
    text = readme_text()

    assert "InstallExportValidation" in text
    assert "ValidateSelectedExportRows" in text
    assert "ValidateConfiguredExportRows" in text
    assert "ExportSelectedExtrusionOrdersCsv" in text
    assert "exports" in text
    assert "RecipeCatalogPrinting" in text
    assert "RecipeCatalogExtrusion" in text
    assert "ExportConfig" in text
    assert "extracts" not in text
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_excel_export_macro_contract.py -q
```

Expected: failures because the new public macros/constants/docs do not exist yet and the macro still uses `extracts`.

### Task 2: Add Export Setup Macro And Constants

**Files:**
- Modify: `source-files/excel-macros/ExportExtrusionOrders.bas`

- [ ] **Step 1: Replace top-level constants**

At the top of `ExportExtrusionOrders.bas`, keep `Attribute VB_Name` and `Option Explicit`, then replace the current constants with:

```vb
Private Const EXPORT_FOLDER_NAME As String = "exports"
Private Const DATABASE_SHEET_NAME As String = "Database"
Private Const CONFIG_SHEET_NAME As String = "ExportConfig"
Private Const PRINTING_CATALOG_SHEET_NAME As String = "RecipeCatalogPrinting"
Private Const EXTRUSION_CATALOG_SHEET_NAME As String = "RecipeCatalogExtrusion"
Private Const CONFIG_FIRST_VALIDATION_ROW As String = "FirstValidationRow"

Private Const FIRST_PRODUCTION_ROW As Long = 5
Private Const MAX_DISPLAYED_VALIDATION_ERRORS As Long = 10

Private Const PRINTING_FIRST_COLUMN As String = "AB"
Private Const PRINTING_LAST_COLUMN As String = "AI"
Private Const EXTRUSION_FIRST_COLUMN As String = "AM"
Private Const EXTRUSION_LAST_COLUMN As String = "AS"
```

- [ ] **Step 2: Add public setup macro**

Add this public macro near the top, before export/validation macros:

```vb
Public Sub InstallExportValidation()
    Dim setupErrors As New Collection

    EnsureExportConfigSheet setupErrors
    EnsureCatalogSheet PRINTING_CATALOG_SHEET_NAME, Array("Type", "Value", "Notes"), setupErrors
    EnsureCatalogSheet EXTRUSION_CATALOG_SHEET_NAME, Array("Category", "Producer", "GradeCode", "Notes"), setupErrors

    If setupErrors.Count > 0 Then
        MsgBox JoinCollection(setupErrors, vbCrLf), vbExclamation, "Проверка за експорт"
        Exit Sub
    End If

    MsgBox _
        "Инсталацията за проверка при експорт е готова." & vbCrLf & _
        "Проверете стойността FirstValidationRow в скрития лист ExportConfig.", _
        vbInformation, _
        "Проверка за експорт"
End Sub
```

- [ ] **Step 3: Add setup helpers**

Add these helpers after `InstallExportValidation`:

```vb
Private Sub EnsureExportConfigSheet(ByVal setupErrors As Collection)
    Dim ws As Worksheet
    Set ws = EnsureSheet(CONFIG_SHEET_NAME)

    If Not HeaderMatches(ws, Array("Setting", "Value", "Notes")) Then
        If SheetHasOnlyBlankHeader(ws, 3) Then
            ws.Range("A1:C1").Value = Array("Setting", "Value", "Notes")
        Else
            AddValidationError setupErrors, "Листът ExportConfig няма очакваните заглавия: Setting | Value | Notes."
            Exit Sub
        End If
    End If

    EnsureConfigSettingRow ws, CONFIG_FIRST_VALIDATION_ROW, "First Database row validated by ValidateAll"
    ws.Visible = xlSheetHidden
End Sub

Private Sub EnsureCatalogSheet(ByVal sheetName As String, ByVal headers As Variant, ByVal setupErrors As Collection)
    Dim ws As Worksheet
    Set ws = EnsureSheet(sheetName)

    If Not HeaderMatches(ws, headers) Then
        If SheetHasOnlyBlankHeader(ws, UBound(headers) - LBound(headers) + 1) Then
            ws.Range(ws.Cells(1, 1), ws.Cells(1, UBound(headers) - LBound(headers) + 1)).Value = headers
        Else
            AddValidationError setupErrors, "Листът " & sheetName & " няма очакваните заглавия."
            Exit Sub
        End If
    End If
End Sub

Private Function EnsureSheet(ByVal sheetName As String) As Worksheet
    On Error Resume Next
    Set EnsureSheet = ActiveWorkbook.Worksheets(sheetName)
    On Error GoTo 0

    If EnsureSheet Is Nothing Then
        Set EnsureSheet = ActiveWorkbook.Worksheets.Add(After:=ActiveWorkbook.Worksheets(ActiveWorkbook.Worksheets.Count))
        EnsureSheet.Name = sheetName
    End If
End Function

Private Function HeaderMatches(ByVal ws As Worksheet, ByVal headers As Variant) As Boolean
    Dim index As Long

    For index = LBound(headers) To UBound(headers)
        If CStr(ws.Cells(1, index - LBound(headers) + 1).Value) <> CStr(headers(index)) Then
            HeaderMatches = False
            Exit Function
        End If
    Next index

    HeaderMatches = True
End Function

Private Function SheetHasOnlyBlankHeader(ByVal ws As Worksheet, ByVal headerColumnCount As Long) As Boolean
    Dim index As Long

    For index = 1 To headerColumnCount
        If Len(Trim$(CStr(ws.Cells(1, index).Value))) > 0 Then
            SheetHasOnlyBlankHeader = False
            Exit Function
        End If
    Next index

    SheetHasOnlyBlankHeader = True
End Function

Private Sub EnsureConfigSettingRow(ByVal ws As Worksheet, ByVal settingName As String, ByVal notes As String)
    Dim rowIndex As Long
    Dim lastRow As Long

    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    For rowIndex = 2 To lastRow
        If CStr(ws.Cells(rowIndex, 1).Value) = settingName Then Exit Sub
    Next rowIndex

    If lastRow < 2 Then lastRow = 1
    ws.Cells(lastRow + 1, 1).Value = settingName
    ws.Cells(lastRow + 1, 2).Value = vbNullString
    ws.Cells(lastRow + 1, 3).Value = notes
End Sub
```

- [ ] **Step 4: Run static test subset**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_excel_export_macro_contract.py::test_export_macro_uses_approved_workbook_sheets_and_ranges -q
```

Expected: still failing until all public macros and README updates are complete, but constants should now satisfy this test.

### Task 3: Add Shared Validation Message And Parsing Helpers

**Files:**
- Modify: `source-files/excel-macros/ExportExtrusionOrders.bas`

- [ ] **Step 1: Add error collection helpers**

Add these private helpers before the existing CSV helpers:

```vb
Private Sub AddValidationError(ByVal errors As Collection, ByVal message As String)
    errors.Add message
End Sub

Private Function ValidationFailedMessage(ByVal errors As Collection) As String
    Dim lines As New Collection
    Dim index As Long
    Dim displayCount As Long

    lines.Add "Проверката откри грешки. Коригирайте данните и опитайте отново."
    lines.Add vbNullString

    displayCount = errors.Count
    If displayCount > MAX_DISPLAYED_VALIDATION_ERRORS Then displayCount = MAX_DISPLAYED_VALIDATION_ERRORS

    For index = 1 To displayCount
        lines.Add CStr(index) & ". " & CStr(errors(index))
    Next index

    If errors.Count > MAX_DISPLAYED_VALIDATION_ERRORS Then
        lines.Add vbNullString
        lines.Add "Показани са първите " & MAX_DISPLAYED_VALIDATION_ERRORS & " грешки от общо " & errors.Count & "."
    End If

    ValidationFailedMessage = JoinCollection(lines, vbCrLf)
End Function

Private Function ValidationPassedMessage(ByVal rowCount As Long, ByVal configuredRange As Boolean) As String
    If configuredRange Then
        ValidationPassedMessage = "Проверката е успешна. Проверени производствени поръчки от FirstValidationRow нататък: " & rowCount & "."
    Else
        ValidationPassedMessage = "Проверката е успешна. Проверени избрани производствени поръчки: " & rowCount & "."
    End If
End Function

Private Function RowContext(ByVal ws As Worksheet, ByVal rowNumber As Long) As String
    RowContext = "Ред " & rowNumber & ", поръчка " & DisplayCellText(ws.Range("A" & rowNumber))
End Function
```

- [ ] **Step 2: Add strict text parsing helpers**

Add:

```vb
Private Function TrimmedCellText(ByVal cell As Range) As String
    TrimmedCellText = Trim$(DisplayCellText(cell))
End Function

Private Function IsBlankText(ByVal value As String) As Boolean
    IsBlankText = (Len(Trim$(value)) = 0)
End Function

Private Function CountOccurrences(ByVal value As String, ByVal needle As String) As Long
    CountOccurrences = (Len(value) - Len(Replace(value, needle, vbNullString, 1, -1, vbBinaryCompare))) / Len(needle)
End Function

Private Function TextBeforeFinalDelimiter(ByVal value As String, ByVal delimiter As String) As String
    TextBeforeFinalDelimiter = Trim$(Left$(value, InStrRev(value, delimiter, -1, vbBinaryCompare) - 1))
End Function

Private Function TextAfterFinalDelimiter(ByVal value As String, ByVal delimiter As String) As String
    TextAfterFinalDelimiter = Trim$(Mid$(value, InStrRev(value, delimiter, -1, vbBinaryCompare) + Len(delimiter)))
End Function

Private Function NormalizeSpacesForBuilderOutput(ByVal value As String) As String
    value = Trim$(value)
    Do While InStr(value, "  ") > 0
        value = Replace(value, "  ", " ")
    Loop
    NormalizeSpacesForBuilderOutput = value
End Function
```

Use `NormalizeSpacesForBuilderOutput` only to reproduce recipe-builder-generated catalog identities. Do not use it on workbook cell field values before matching.

- [ ] **Step 3: Add numeric parsing helpers**

Add:

```vb
Private Function TryParsePositiveNumber(ByVal value As String, ByRef parsedValue As Currency) As Boolean
    Dim normalized As String
    Dim index As Long
    Dim charValue As String
    Dim dotCount As Long

    normalized = Trim$(value)
    normalized = Replace(normalized, ",", ".")

    If Len(normalized) = 0 Then Exit Function

    For index = 1 To Len(normalized)
        charValue = Mid$(normalized, index, 1)
        If charValue = "." Then
            dotCount = dotCount + 1
            If dotCount > 1 Then Exit Function
        ElseIf charValue < "0" Or charValue > "9" Then
            Exit Function
        End If
    Next index

    parsedValue = CCur(Val(normalized))
    TryParsePositiveNumber = (parsedValue > 0)
End Function

Private Function TryParseRecipePercent(ByVal value As String, ByRef parsedValue As Currency) As Boolean
    Dim percentText As String

    percentText = Trim$(value)
    If Len(percentText) = 0 Then Exit Function
    If Right$(percentText, 1) <> "%" Then Exit Function

    percentText = Trim$(Left$(percentText, Len(percentText) - 1))
    TryParseRecipePercent = TryParsePositiveNumber(percentText, parsedValue)
End Function
```

- [ ] **Step 4: Run syntax-oriented static tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_excel_export_macro_contract.py -q
```

Expected: still failing on missing public validation macros and README, but no Python test syntax errors.

### Task 4: Add Catalog Loading And Header Validation

**Files:**
- Modify: `source-files/excel-macros/ExportExtrusionOrders.bas`

- [ ] **Step 1: Add required sheet/header validation**

Add:

```vb
Private Function RequiredWorkbookShapeIsValid(ByVal errors As Collection) As Boolean
    RequiredWorkbookShapeIsValid = True

    If Not SheetExists(DATABASE_SHEET_NAME) Then
        AddValidationError errors, "Липсва лист Database."
        RequiredWorkbookShapeIsValid = False
    End If
    If Not SheetExists(CONFIG_SHEET_NAME) Then
        AddValidationError errors, "Липсва лист ExportConfig. Стартирайте InstallExportValidation."
        RequiredWorkbookShapeIsValid = False
    End If
    If Not SheetExists(PRINTING_CATALOG_SHEET_NAME) Then
        AddValidationError errors, "Липсва лист RecipeCatalogPrinting. Стартирайте InstallExportValidation."
        RequiredWorkbookShapeIsValid = False
    End If
    If Not SheetExists(EXTRUSION_CATALOG_SHEET_NAME) Then
        AddValidationError errors, "Липсва лист RecipeCatalogExtrusion. Стартирайте InstallExportValidation."
        RequiredWorkbookShapeIsValid = False
    End If

    If Not RequiredWorkbookShapeIsValid Then Exit Function

    If Not HeaderMatches(ActiveWorkbook.Worksheets(CONFIG_SHEET_NAME), Array("Setting", "Value", "Notes")) Then
        AddValidationError errors, "Листът ExportConfig трябва да има заглавия Setting | Value | Notes."
        RequiredWorkbookShapeIsValid = False
    End If
    If Not HeaderMatches(ActiveWorkbook.Worksheets(PRINTING_CATALOG_SHEET_NAME), Array("Type", "Value", "Notes")) Then
        AddValidationError errors, "Листът RecipeCatalogPrinting трябва да има заглавия Type | Value | Notes."
        RequiredWorkbookShapeIsValid = False
    End If
    If Not HeaderMatches(ActiveWorkbook.Worksheets(EXTRUSION_CATALOG_SHEET_NAME), Array("Category", "Producer", "GradeCode", "Notes")) Then
        AddValidationError errors, "Листът RecipeCatalogExtrusion трябва да има заглавия Category | Producer | GradeCode | Notes."
        RequiredWorkbookShapeIsValid = False
    End If
End Function

Private Function SheetExists(ByVal sheetName As String) As Boolean
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = ActiveWorkbook.Worksheets(sheetName)
    On Error GoTo 0
    SheetExists = Not ws Is Nothing
End Function
```

- [ ] **Step 2: Add printing catalog loader**

Add:

```vb
Private Function LoadPrintingCatalogValues(ByVal expectedType As String, ByVal errors As Collection) As Object
    Dim values As Object
    Dim ws As Worksheet
    Dim lastRow As Long
    Dim rowIndex As Long
    Dim rowType As String
    Dim rowValue As String

    Set values = CreateObject("Scripting.Dictionary")
    values.CompareMode = vbBinaryCompare

    Set ws = ActiveWorkbook.Worksheets(PRINTING_CATALOG_SHEET_NAME)
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row

    For rowIndex = 2 To lastRow
        rowType = Trim$(CStr(ws.Cells(rowIndex, 1).Value))
        rowValue = Trim$(CStr(ws.Cells(rowIndex, 2).Value))

        If Len(rowType) > 0 Or Len(rowValue) > 0 Then
            If rowType <> "Ink" And rowType <> "Anilox" Then
                AddValidationError errors, "RecipeCatalogPrinting ред " & rowIndex & ": непознат Type """ & rowType & """."
            ElseIf Len(rowValue) = 0 Then
                AddValidationError errors, "RecipeCatalogPrinting ред " & rowIndex & ": липсва Value."
            ElseIf rowType = expectedType Then
                If Not values.Exists(rowValue) Then values.Add rowValue, True
            End If
        End If
    Next rowIndex

    Set LoadPrintingCatalogValues = values
End Function
```

- [ ] **Step 3: Add extrusion catalog loader**

Add:

```vb
Private Function LoadExtrusionMaterialIdentities(ByVal errors As Collection) As Object
    Dim values As Object
    Dim ws As Worksheet
    Dim lastRow As Long
    Dim rowIndex As Long
    Dim category As String
    Dim producer As String
    Dim gradeCode As String
    Dim identity As String

    Set values = CreateObject("Scripting.Dictionary")
    values.CompareMode = vbBinaryCompare

    Set ws = ActiveWorkbook.Worksheets(EXTRUSION_CATALOG_SHEET_NAME)
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row

    For rowIndex = 2 To lastRow
        category = Trim$(CStr(ws.Cells(rowIndex, 1).Value))
        producer = Trim$(CStr(ws.Cells(rowIndex, 2).Value))
        gradeCode = Trim$(CStr(ws.Cells(rowIndex, 3).Value))

        If Len(category) > 0 Or Len(producer) > 0 Or Len(gradeCode) > 0 Then
            If Len(category) = 0 Then
                AddValidationError errors, "RecipeCatalogExtrusion ред " & rowIndex & ": липсва Category."
            ElseIf Len(producer) = 0 Then
                AddValidationError errors, "RecipeCatalogExtrusion ред " & rowIndex & ": липсва Producer."
            ElseIf Len(gradeCode) = 0 Then
                AddValidationError errors, "RecipeCatalogExtrusion ред " & rowIndex & ": липсва GradeCode."
            ElseIf Not IsApprovedExtrusionCategory(category) Then
                AddValidationError errors, "RecipeCatalogExtrusion ред " & rowIndex & ": непозната категория """ & category & """."
            Else
                identity = BuildExtrusionIdentity(category, producer, gradeCode)
                If Len(identity) > 0 And Not values.Exists(identity) Then values.Add identity, True
            End If
        End If
    Next rowIndex

    Set LoadExtrusionMaterialIdentities = values
End Function

Private Function BuildExtrusionIdentity(ByVal category As String, ByVal producer As String, ByVal gradeCode As String) As String
    Dim identity As String

    identity = Trim$(category)
    If UCase$(Trim$(producer)) <> "N/A" Then identity = identity & " " & Trim$(producer)
    If UCase$(Trim$(gradeCode)) <> "N/A" Then identity = identity & " " & Trim$(gradeCode)

    BuildExtrusionIdentity = NormalizeSpacesForBuilderOutput(identity)
End Function
```

- [ ] **Step 4: Add category approval helper**

Add:

```vb
Private Function IsApprovedExtrusionCategory(ByVal category As String) As Boolean
    Select Case category
        Case "LDPE", "LLDPE", "MDPE", "reLDPE", "Antistatic", "Masterbatch", "Filler", "UV", "Antislip"
            IsApprovedExtrusionCategory = True
        Case Else
            IsApprovedExtrusionCategory = False
    End Select
End Function
```

Use exact category spelling for workbook catalog validation. Do not normalize catalog category spelling in the export macro.

### Task 5: Add Row Selection And Configured Range Helpers

**Files:**
- Modify: `source-files/excel-macros/ExportExtrusionOrders.bas`

- [ ] **Step 1: Replace selected-row helper**

Replace `SelectedDataRows` with `SelectedProductionRows`:

```vb
Private Function SelectedProductionRows(ByVal ws As Worksheet, ByVal selectedRange As Range) As Collection
    Dim rows As New Collection
    Dim seen As Object
    Dim area As Range
    Dim rowRange As Range
    Dim rowNumber As Long

    Set seen = CreateObject("Scripting.Dictionary")

    For Each area In selectedRange.Areas
        For Each rowRange In area.Rows
            rowNumber = rowRange.Row
            If rowNumber >= FIRST_PRODUCTION_ROW Then
                If Len(TrimmedCellText(ws.Range("A" & rowNumber))) > 0 Then
                    If Not seen.Exists(CStr(rowNumber)) Then
                        seen.Add CStr(rowNumber), True
                        rows.Add rowNumber
                    End If
                End If
            End If
        Next rowRange
    Next area

    Set SelectedProductionRows = rows
End Function
```

- [ ] **Step 2: Add configured-row helper**

Add:

```vb
Private Function ConfiguredProductionRows(ByVal ws As Worksheet, ByVal errors As Collection) As Collection
    Dim rows As New Collection
    Dim firstRow As Long
    Dim lastRow As Long
    Dim rowNumber As Long

    firstRow = FirstValidationRow(errors)
    If firstRow = 0 Then
        Set ConfiguredProductionRows = rows
        Exit Function
    End If

    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    For rowNumber = firstRow To lastRow
        If Len(TrimmedCellText(ws.Range("A" & rowNumber))) > 0 Then
            rows.Add rowNumber
        End If
    Next rowNumber

    Set ConfiguredProductionRows = rows
End Function

Private Function FirstValidationRow(ByVal errors As Collection) As Long
    Dim ws As Worksheet
    Dim lastRow As Long
    Dim rowIndex As Long
    Dim rawValue As String
    Dim parsedValue As Currency

    Set ws = ActiveWorkbook.Worksheets(CONFIG_SHEET_NAME)
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row

    For rowIndex = 2 To lastRow
        If CStr(ws.Cells(rowIndex, 1).Value) = CONFIG_FIRST_VALIDATION_ROW Then
            rawValue = Trim$(CStr(ws.Cells(rowIndex, 2).Value))
            If Not TryParsePositiveNumber(rawValue, parsedValue) Then
                AddValidationError errors, "ExportConfig: FirstValidationRow трябва да бъде положителен номер на ред."
                FirstValidationRow = 0
                Exit Function
            End If
            If CLng(parsedValue) < FIRST_PRODUCTION_ROW Then
                AddValidationError errors, "ExportConfig: FirstValidationRow трябва да бъде ред " & FIRST_PRODUCTION_ROW & " или по-голям."
                FirstValidationRow = 0
                Exit Function
            End If
            FirstValidationRow = CLng(parsedValue)
            Exit Function
        End If
    Next rowIndex

    AddValidationError errors, "ExportConfig: липсва настройка FirstValidationRow."
    FirstValidationRow = 0
End Function
```

- [ ] **Step 3: Update BuildCsv callers**

Leave `BuildCsv` headers and source columns unchanged. Its callers should now pass `SelectedProductionRows`, not all selected row numbers.

### Task 6: Add Row Validation

**Files:**
- Modify: `source-files/excel-macros/ExportExtrusionOrders.bas`

- [ ] **Step 1: Add shared row validation orchestrator**

Add:

```vb
Private Function ValidateRows(ByVal ws As Worksheet, ByVal rows As Collection, ByVal errors As Collection) As Boolean
    Dim printingInks As Object
    Dim printingAnilox As Object
    Dim extrusionIdentities As Object
    Dim item As Variant
    Dim rowNumber As Long

    If Not RequiredWorkbookShapeIsValid(errors) Then
        ValidateRows = False
        Exit Function
    End If

    Set printingInks = LoadPrintingCatalogValues("Ink", errors)
    Set printingAnilox = LoadPrintingCatalogValues("Anilox", errors)
    Set extrusionIdentities = LoadExtrusionMaterialIdentities(errors)

    If errors.Count > 0 Then
        ValidateRows = False
        Exit Function
    End If

    For Each item In rows
        rowNumber = CLng(item)
        ValidateTargetGross ws, rowNumber, errors
        ValidatePrintingCells ws, rowNumber, printingInks, printingAnilox, errors
        ValidateExtrusionCells ws, rowNumber, extrusionIdentities, errors
    Next item

    ValidateRows = (errors.Count = 0)
End Function
```

- [ ] **Step 2: Add column G validation**

Add:

```vb
Private Sub ValidateTargetGross(ByVal ws As Worksheet, ByVal rowNumber As Long, ByVal errors As Collection)
    Dim rawValue As String
    Dim parsedValue As Currency

    rawValue = TrimmedCellText(ws.Range("G" & rowNumber))
    If Not TryParsePositiveNumber(rawValue, parsedValue) Then
        AddValidationError errors, RowContext(ws, rowNumber) & ", G: планираните бруто килограми трябва да са положително число."
    End If
End Sub
```

- [ ] **Step 3: Add printing validation**

Add:

```vb
Private Sub ValidatePrintingCells( _
    ByVal ws As Worksheet, _
    ByVal rowNumber As Long, _
    ByVal inks As Object, _
    ByVal aniloxValues As Object, _
    ByVal errors As Collection _
)
    Dim col As Long
    Dim cellValue As String
    Dim slashCount As Long
    Dim inkValue As String
    Dim aniloxValue As String
    Dim columnLetter As String

    For col = ws.Range(PRINTING_FIRST_COLUMN & "1").Column To ws.Range(PRINTING_LAST_COLUMN & "1").Column
        cellValue = TrimmedCellText(ws.Cells(rowNumber, col))
        If Not IsBlankText(cellValue) Then
            columnLetter = Split(ws.Cells(1, col).Address(False, False), "$")(0)
            slashCount = CountOccurrences(cellValue, "/")

            If slashCount = 0 Then
                inkValue = Trim$(cellValue)
                If Not inks.Exists(inkValue) Then
                    AddValidationError errors, RowContext(ws, rowNumber) & ", " & columnLetter & ": """ & cellValue & """ не е намерено като Ink в RecipeCatalogPrinting."
                End If
            ElseIf slashCount <> 1 Then
                AddValidationError errors, RowContext(ws, rowNumber) & ", " & columnLetter & ": """ & cellValue & """ трябва да съдържа най-много един разделител /."
            Else
                inkValue = Trim$(Left$(cellValue, InStr(1, cellValue, "/", vbBinaryCompare) - 1))
                aniloxValue = Trim$(Mid$(cellValue, InStr(1, cellValue, "/", vbBinaryCompare) + 1))

                If Len(inkValue) = 0 Then
                    AddValidationError errors, RowContext(ws, rowNumber) & ", " & columnLetter & ": липсва Ink преди /."
                ElseIf Not inks.Exists(inkValue) Then
                    AddValidationError errors, RowContext(ws, rowNumber) & ", " & columnLetter & ": """ & inkValue & """ не е намерено като Ink в RecipeCatalogPrinting."
                End If

                If Len(aniloxValue) = 0 Then
                    AddValidationError errors, RowContext(ws, rowNumber) & ", " & columnLetter & ": липсва Anilox след /."
                ElseIf Not aniloxValues.Exists(aniloxValue) Then
                    AddValidationError errors, RowContext(ws, rowNumber) & ", " & columnLetter & ": """ & aniloxValue & """ не е намерено като Anilox в RecipeCatalogPrinting."
                End If
            End If
        End If
    Next col
End Sub
```

- [ ] **Step 4: Add extrusion validation**

Add:

```vb
Private Sub ValidateExtrusionCells(ByVal ws As Worksheet, ByVal rowNumber As Long, ByVal identities As Object, ByVal errors As Collection)
    Dim col As Long
    Dim cellValue As String
    Dim columnLetter As String
    Dim identity As String
    Dim percentText As String
    Dim percentValue As Currency
    Dim totalPercent As Currency
    Dim hasExtrusionValue As Boolean

    For col = ws.Range(EXTRUSION_FIRST_COLUMN & "1").Column To ws.Range(EXTRUSION_LAST_COLUMN & "1").Column
        cellValue = TrimmedCellText(ws.Cells(rowNumber, col))
        If Not IsBlankText(cellValue) Then
            hasExtrusionValue = True
            columnLetter = Split(ws.Cells(1, col).Address(False, False), "$")(0)

            If InStr(1, cellValue, "|", vbBinaryCompare) = 0 Then
                AddValidationError errors, RowContext(ws, rowNumber) & ", " & columnLetter & ": липсва разделител |."
            Else
                identity = TextBeforeFinalDelimiter(cellValue, "|")
                percentText = TextAfterFinalDelimiter(cellValue, "|")

                If Len(identity) = 0 Then
                    AddValidationError errors, RowContext(ws, rowNumber) & ", " & columnLetter & ": липсва материал преди |."
                Else
                    ValidateExtrusionIdentity ws, rowNumber, columnLetter, identity, identities, errors
                End If

                If Not TryParseRecipePercent(percentText, percentValue) Then
                    AddValidationError errors, RowContext(ws, rowNumber) & ", " & columnLetter & ": процентът трябва да съдържа % и да бъде по-голям от 0."
                Else
                    totalPercent = totalPercent + percentValue
                End If
            End If
        End If
    Next col

    If hasExtrusionValue Then
        If totalPercent <> 100 Then
            AddValidationError errors, RowContext(ws, rowNumber) & ": сборът на процентите в AM:AS е " & CStr(totalPercent) & "%, трябва да е точно 100%."
        End If
    End If
End Sub

Private Sub ValidateExtrusionIdentity( _
    ByVal ws As Worksheet, _
    ByVal rowNumber As Long, _
    ByVal columnLetter As String, _
    ByVal identity As String, _
    ByVal identities As Object, _
    ByVal errors As Collection _
)
    Dim category As String
    Dim spacePosition As Long

    spacePosition = InStr(1, identity, " ", vbBinaryCompare)
    If spacePosition = 0 Then
        category = identity
    Else
        category = Left$(identity, spacePosition - 1)
    End If

    If Not IsApprovedExtrusionCategory(category) Then
        AddValidationError errors, RowContext(ws, rowNumber) & ", " & columnLetter & ": непозната категория """ & category & """."
        Exit Sub
    End If

    If Not identities.Exists(identity) Then
        AddValidationError errors, RowContext(ws, rowNumber) & ", " & columnLetter & ": """ & identity & """ не е намерено в RecipeCatalogExtrusion."
    End If
End Sub
```

### Task 7: Wire Public Validation And Export Macros

**Files:**
- Modify: `source-files/excel-macros/ExportExtrusionOrders.bas`

- [ ] **Step 1: Add selected validation macro**

Add:

```vb
Public Sub ValidateSelectedExportRows()
    Dim ws As Worksheet
    Dim rows As Collection
    Dim errors As New Collection

    If ActiveSheet.Name <> DATABASE_SHEET_NAME Then
        MsgBox "Отворете лист Database и изберете редове за проверка.", vbExclamation, "Проверка за експорт"
        Exit Sub
    End If
    If TypeName(Selection) <> "Range" Then
        MsgBox "Изберете един или повече редове в Database.", vbExclamation, "Проверка за експорт"
        Exit Sub
    End If

    Set ws = ActiveWorkbook.Worksheets(DATABASE_SHEET_NAME)
    Set rows = SelectedProductionRows(ws, Selection)
    If rows.Count = 0 Then
        MsgBox "Няма избрани производствени поръчки с номер в колона A.", vbExclamation, "Проверка за експорт"
        Exit Sub
    End If

    If ValidateRows(ws, rows, errors) Then
        MsgBox ValidationPassedMessage(rows.Count, False), vbInformation, "Проверка за експорт"
    Else
        MsgBox ValidationFailedMessage(errors), vbExclamation, "Проверка за експорт"
    End If
End Sub
```

- [ ] **Step 2: Add configured validation macro**

Add:

```vb
Public Sub ValidateConfiguredExportRows()
    Dim ws As Worksheet
    Dim rows As Collection
    Dim errors As New Collection

    If Not RequiredWorkbookShapeIsValid(errors) Then
        MsgBox ValidationFailedMessage(errors), vbExclamation, "Проверка за експорт"
        Exit Sub
    End If

    Set ws = ActiveWorkbook.Worksheets(DATABASE_SHEET_NAME)
    Set rows = ConfiguredProductionRows(ws, errors)

    If errors.Count > 0 Then
        MsgBox ValidationFailedMessage(errors), vbExclamation, "Проверка за експорт"
        Exit Sub
    End If
    If rows.Count = 0 Then
        MsgBox "Няма производствени поръчки за проверка от FirstValidationRow нататък.", vbExclamation, "Проверка за експорт"
        Exit Sub
    End If

    If ValidateRows(ws, rows, errors) Then
        MsgBox ValidationPassedMessage(rows.Count, True), vbInformation, "Проверка за експорт"
    Else
        MsgBox ValidationFailedMessage(errors), vbExclamation, "Проверка за експорт"
    End If
End Sub
```

- [ ] **Step 3: Replace export macro body**

Update `ExportSelectedExtrusionOrdersCsv` so it uses selected production rows and validates before building/writing CSV:

```vb
Public Sub ExportSelectedExtrusionOrdersCsv()
    Dim ws As Worksheet
    Dim exportRows As Collection
    Dim validationErrors As New Collection
    Dim csvText As String
    Dim exportPath As String
    Dim filename As String

    If ActiveSheet.Name <> DATABASE_SHEET_NAME Then
        MsgBox "Отворете лист Database, изберете редовете за експорт и стартирайте макрото.", vbExclamation, "Експорт"
        Exit Sub
    End If

    If TypeName(Selection) <> "Range" Then
        MsgBox "Изберете една или повече производствени поръчки преди експорт.", vbExclamation, "Експорт"
        Exit Sub
    End If

    Set ws = ActiveWorkbook.Worksheets(DATABASE_SHEET_NAME)
    Set exportRows = SelectedProductionRows(ws, Selection)

    If exportRows.Count = 0 Then
        MsgBox "Няма избрани производствени поръчки с номер в колона A.", vbExclamation, "Експорт"
        Exit Sub
    End If

    If Not ValidateRows(ws, exportRows, validationErrors) Then
        MsgBox ValidationFailedMessage(validationErrors), vbExclamation, "Експортът е спрян"
        Exit Sub
    End If

    csvText = BuildCsv(ws, exportRows)

    exportPath = ExportFolderPath(ActiveWorkbook.Path)
    EnsureFolderExists exportPath

    filename = exportPath & "\extrusion_orders_" & Format(Now, "yyyymmdd_hhnnss") & ".csv"
    WriteUtf8TextFile filename, csvText

    MsgBox "Експортирани редове: " & exportRows.Count & vbCrLf & filename, vbInformation, "Експорт"
End Sub
```

- [ ] **Step 4: Run static tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_excel_export_macro_contract.py -q
```

Expected: README-related test still fails until README is updated. Macro-specific tests should pass.

### Task 8: Update Excel Macro README

**Files:**
- Modify: `source-files/excel-macros/README.md`

- [ ] **Step 1: Replace README content**

Replace `source-files/excel-macros/README.md` with:

```markdown
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
FirstValidationRow | 12206 | First Database row validated by ValidateAll
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
4. Select `source-files/excel-macros/ExportExtrusionOrders.bas`.
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
```

- [ ] **Step 2: Run macro contract tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_excel_export_macro_contract.py -q
```

Expected: pass.

### Task 9: Update Open Issues And Plan Notes

**Files:**
- Modify: `open-issues.md`
- Optionally modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update OI-003 Step 8 scope text**

In `open-issues.md`, update Step 8 bullets so they mention the final approved macro behavior:

```markdown
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
   - Block CSV writing with a clear Bulgarian row/order/column/value/reason
     message when validation fails.
   - Keep the macro read-only with respect to existing workbook production-order
     cells.
```

- [ ] **Step 2: If implementation is completed in this branch, update `IMPLEMENTATION_PLAN.md`**

Add an OI-003 Step 8 note near the structured recipe redesign follow-up section:

```markdown
- OI-003 Step 8 complete: the Excel export macro now provides setup, selected
  validation, configured-range validation, and export-gated validation for
  `Database!G`, printing `AB:AI`, and extrusion `AM:AS`; CSV output remains the
  extrusion-terminal schema and writes to `exports`.
```

Do this only when the macro and manual verification are complete. If writing the plan only, leave `IMPLEMENTATION_PLAN.md` unchanged.

### Task 10: Manual Workbook Verification On A Copy

**Files:**
- Use a copied workbook under `.test-runtime/oi-003-step-8/`
- Do not modify `interim-costing-process/source-files/test-shift-manager-file.xlsm`

- [ ] **Step 1: Prepare copied workbook**

Run:

```bash
mkdir -p .test-runtime/oi-003-step-8
cp interim-costing-process/source-files/test-shift-manager-file.xlsm .test-runtime/oi-003-step-8/test-shift-manager-file-step-8.xlsm
```

Expected: copied workbook exists under `.test-runtime/oi-003-step-8/`.

- [ ] **Step 2: Import macro into copied workbook**

Manual Excel steps:

1. Open `.test-runtime/oi-003-step-8/test-shift-manager-file-step-8.xlsm`.
2. Press `Alt+F11`.
3. Import `source-files/excel-macros/ExportExtrusionOrders.bas`.
4. Run `InstallExportValidation`.
5. Confirm helper sheets exist:
   - `ExportConfig`
   - `RecipeCatalogPrinting`
   - `RecipeCatalogExtrusion`
6. Confirm existing catalog rows were not cleared.

- [ ] **Step 3: Configure validation start row**

In the copied workbook, set:

```text
ExportConfig FirstValidationRow = 12206
```

Use a row appropriate to the copied workbook if row `12206` is not the intended test row.

- [ ] **Step 4: Verify configured validation catches current invalid total**

Run macro:

```text
ValidateConfiguredExportRows
```

Expected if row `12206` still has the inspected recipe totaling `90%`:

- Message box reports validation failure.
- One error says the total percentage in `AM:AS` is not exactly `100%`.
- No CSV is written.

- [ ] **Step 5: Verify invalid printing catalog value fails validation**

In a copied workbook test row at or after `FirstValidationRow`:

1. Ensure column `A` has an order number.
2. Ensure column `G` has a positive number.
3. Enter `NotInCatalog` in `AB`.
4. Run `ValidateSelectedExportRows`.

Expected:

- Message box reports `AB` value is not found as `Ink` in `RecipeCatalogPrinting`.
- No workbook cells are rewritten.

- [ ] **Step 6: Verify valid printing forms pass**

In the copied workbook, ensure `RecipeCatalogPrinting` has:

```text
Ink | White
Ink | Pantone 485
Anilox | 110
Anilox | 255
```

Set printing cells on a selected row:

```text
AB = White
AC = Pantone 485/255
```

Expected:

- Printing validation does not produce errors for `AB` or `AC`.

- [ ] **Step 7: Verify strict matching**

Set:

```text
AB = white
AC = White/1 10
```

Expected:

- `white` fails because catalog value matching is case-sensitive.
- `1 10` fails because internal spaces are not normalized into `110`.

- [ ] **Step 8: Verify export failure writes no CSV**

1. Delete any test CSV files under `.test-runtime/oi-003-step-8/exports/`.
2. Select a row with a known validation error.
3. Run `ExportSelectedExtrusionOrdersCsv`.

Expected:

- Message box reports validation errors.
- No CSV file appears under `exports`.

- [ ] **Step 9: Verify successful export schema**

1. Fix selected row validation errors.
2. Run `ExportSelectedExtrusionOrdersCsv`.
3. Open the generated CSV under `exports`.

Expected:

- CSV exists under `exports`.
- CSV headers match the existing extrusion-terminal import schema.
- No `AB:AI` printing fields appear in the CSV.
- `AM:AS` extrusion fields still export as the original source text.

### Task 11: Run Repository Verification

**Files:**
- No new files beyond previous tasks.

- [ ] **Step 1: Run focused macro contract tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_excel_export_macro_contract.py -q
```

Expected: pass.

- [ ] **Step 2: Run existing relevant app tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_parser.py tests/test_recipe_release_validation.py tests/test_structured_recipe_sample_csv.py -q
```

Expected: pass. These app tests should not need behavior changes in Step 8.

- [ ] **Step 3: Run full test suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected: pass.

- [ ] **Step 4: Run diff checks**

Run:

```bash
git diff --check
git status --short
```

Expected:

- `git diff --check` has no output.
- `git status --short` shows only intended files plus pre-existing unrelated untracked files.

### Task 12: Final Review Checklist

**Files:**
- Review all modified files.

- [ ] **Step 1: Review macro behavior against interim decision record**

Check `source-files/excel-macros/ExportExtrusionOrders.bas` against:

```text
docs/implementation-notes/oi-003-step-8-export-validation-interim.md
```

Expected:

- One module only.
- Four public macros.
- Hidden `ExportConfig`.
- No workbook buttons.
- Printing validated but not exported.
- Extrusion catalog validation included.
- `G` required positive for every validated production row.
- Bulgarian messages.
- Max 10 displayed errors.
- `exports` folder.

- [ ] **Step 2: Review no accidental app scope creep**

Confirm no changes were made for:

- app release gate `G`-only alignment;
- app-side catalog management;
- printing CSV import;
- printing terminal workflows;
- pricing/costing/inventory behavior.

Those remain out of scope. App `G` alignment is tracked in `OI-004`.

- [ ] **Step 3: Prepare review summary**

Prepare a concise summary for the user:

```text
Implemented OI-003 Step 8 export-side validation in the Excel macro.
Validation now covers selected/configured rows, Database!G, printing AB:AI,
extrusion AM:AS, RecipeCatalogPrinting, and RecipeCatalogExtrusion.
CSV output remains extrusion-terminal-only and writes to exports.
Manual Excel verification was run against a copied workbook only.
```

Do not stage or commit unless the user explicitly asks.

## Self-Review

Spec coverage:

- Reusable validation: Tasks 3, 6, 7.
- Standalone selected validation: Task 7.
- Configured validate-all from `FirstValidationRow`: Tasks 5, 7.
- Export gating: Task 7.
- Hidden `ExportConfig`: Task 2.
- Setup macro with prerequisites only: Tasks 2, 4.
- `RecipeCatalogPrinting` and optional anilox: Tasks 4, 6.
- `RecipeCatalogExtrusion` catalog-based validation: Tasks 4, 6.
- Strict matching: Tasks 3, 4, 6.
- `G` positive gross kg: Task 6.
- CSV schema unchanged/no printing fields: Tasks 1, 8, 10.
- `exports` folder: Tasks 1, 7, 8.
- Bulgarian message boxes and max 10 errors: Tasks 3, 8.
- OI-004 follow-up preserved: Tasks 8, 9, 12.

Placeholder scan:

- No `TBD`, `TODO`, or open implementation placeholders.
- The plan chooses final public macro names.
- Manual Excel verification is explicit because Linux pytest cannot execute VBA.

Type/name consistency:

- Public macro names are consistent across tests, README, and VBA plan:
  `InstallExportValidation`, `ValidateSelectedExportRows`,
  `ValidateConfiguredExportRows`, `ExportSelectedExtrusionOrdersCsv`.
- Sheet names are consistent:
  `ExportConfig`, `RecipeCatalogPrinting`, `RecipeCatalogExtrusion`, `Database`.
- Config setting is consistently `FirstValidationRow`.
