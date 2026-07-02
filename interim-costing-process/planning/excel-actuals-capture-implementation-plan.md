# Excel Actuals Capture V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and install Excel Actuals Capture V1 inside the real
shift-manager workbooks, with a master installer that manages native workbook
macros, Recipe Builder, Export Validation, and Actuals Capture as one coherent
tool bundle.

**Architecture:** Keep actuals data outside `Database` in controlled helper
sheets. Use button-driven macros on `Actuals Entry`, `Actuals Review`, and
`Actuals Validation`; avoid `Database` actuals events. Use one workbook-local
master installer that imports required bundle files, replaces managed code,
preserves itself, and runs setup in a fixed order.

**Tech Stack:** Excel VBA modules/UserForms/sheet code, `.xlsm` shift-manager
workbooks, Python contract tests with `pytest`, read-only workbook inspection
with `.venv/bin/python`, `openpyxl`, and `oletools`.

---

## Ground Rules

- Do not write actuals data to `Database`.
- Do not validate or scan all historical `Database` rows.
- V1 operates only on the configured included row set:
  - rows at or after the configured cutoff row/order;
  - exact configured pre-cutoff row/order inclusions.
- Duplicate production order numbers inside the included set are hard
  validation errors.
- Historical duplicate or messy rows outside the included set are irrelevant to
  V1.
- Treat Marko's current native macros as the canonical native behavior:
  - filter range `A4:AX30000`;
  - back-side print range `AS55:BC105`.
- Homogenize both shift-manager files to one shared native macro behavior.
- Do not stage or commit unless explicitly asked.

## Files

Create:

- `interim-costing-process/excel-tools/workbook-installer/README.md`
  - How to use the master installer and required folder contents.
- `interim-costing-process/excel-tools/workbook-installer/workbook-tools-master-installer.bas`
  - Folder picker, required file checks, managed component cleanup/import,
    installation orchestration, final report.
- `interim-costing-process/excel-tools/native/README.md`
  - Native workbook macro behavior and why Marko is canonical.
- `interim-costing-process/excel-tools/native/shift-manager-native-macros.bas`
  - Installer/support module for managed native sheet-code entry points.
- `interim-costing-process/excel-tools/actuals-capture/README.md`
  - Actuals Capture install/use notes.
- `interim-costing-process/excel-tools/actuals-capture/actuals-capture-installer.bas`
  - Actuals sheets, helper tables, buttons, validation, review, entry, and
    protection setup.
- `tests/test_workbook_tools_master_installer_contract.py`
  - Static contract tests for master installer required files, install order,
    and cleanup behavior.
- `tests/test_shift_manager_native_macro_contract.py`
  - Static contract tests for canonical native macro behavior.
- `tests/test_actuals_capture_macro_contract.py`
  - Static contract tests for Actuals Capture sheet/header/config contracts.

Modify:

- `interim-costing-process/excel-tools/export-validation/export-validation.bas`
  - Standardize target workbook behavior for master-installer use.
- `interim-costing-process/excel-tools/export-validation/README.md`
  - Document master-installer path and direct-install fallback.
- `interim-costing-process/excel-tools/recipe-builder/recipe-builder-installer.bas`
  - Make managed component names explicit for master-installer cleanup.
- `interim-costing-process/excel-tools/recipe-builder/README.md`
  - Document master-installer path and direct-install fallback.
- `interim-costing-process/planning/excel-actuals-capture-plan.md`
  - Apply factual corrections from workbook reality: included set, `да`
    parsing, row 5 start, and `Database!G` numeric scope.
- `interim-costing-process/planning/workbook-inspection-for-actuals-capture.md`
  - Keep updated if implementation discovers new workbook facts.

## Task 1: Align The Functional Spec With Workbook Reality

**Files:**

- Modify: `interim-costing-process/planning/excel-actuals-capture-plan.md`
- Test: manual doc review

- [x] **Step 1: Update expected-operation flag language**

  Replace any statement that exact `Да` alone means expected with:

  ```text
  An operation is expected when the relevant `Database!Q:T` cell, after
  trimming whitespace, case-insensitively equals Bulgarian `да`.
  ```

- [x] **Step 2: Add included-row-set scope**

  Add the rule:

  ```text
  Actuals Capture V1 scans and validates only the configured included row set:
  rows at or after the workbook cutoff row/order plus exact configured
  pre-cutoff row/order inclusions. Historical rows outside that set are ignored.
  ```

- [x] **Step 3: Add duplicate validation rule**

  Add the rule:

  ```text
  Duplicate production order numbers inside the configured included row set are
  validation errors. The shift manager must correct the workbook before V1 can
  treat those orders as valid.
  ```

- [x] **Step 4: Clarify `Database!G`**

  Add:

  ```text
  `Database!G` is the gross ordered quantity source for V1 included rows and is
  expected to be numeric for normalized orders. Historical non-included rows may
  contain text and are not part of V1 validation.
  ```

- [x] **Step 5: Verify no old global-history language remains**

  Run:

  ```bash
  rg -n "all historical|every row|exact `Да`|exact Да|Duplicate" interim-costing-process/planning/excel-actuals-capture-plan.md
  ```

  Expected: any remaining matches are either removed or clearly scoped to the
  configured included row set.

## Task 2: Add Static Contract Tests For Installer And Macro Files

**Files:**

- Create: `tests/test_workbook_tools_master_installer_contract.py`
- Create: `tests/test_shift_manager_native_macro_contract.py`
- Create: `tests/test_actuals_capture_macro_contract.py`

- [x] **Step 1: Add master installer contract tests**

  Create `tests/test_workbook_tools_master_installer_contract.py`:

  ```python
  from pathlib import Path

  ROOT = Path(__file__).resolve().parents[1]
  MASTER = ROOT / "interim-costing-process/excel-tools/workbook-installer/workbook-tools-master-installer.bas"

  REQUIRED_FILES = [
      "shift-manager-native-macros.bas",
      "recipe-builder-installer.bas",
      "export-validation.bas",
      "actuals-capture-installer.bas",
  ]


  def macro_text() -> str:
      return MASTER.read_text(encoding="utf-8")


  def test_master_installer_declares_required_bundle_files():
      text = macro_text()
      for filename in REQUIRED_FILES:
          assert filename in text


  def test_master_installer_stops_before_import_when_required_file_missing():
      text = macro_text()
      assert "ValidateRequiredBundleFiles" in text
      assert "Exit Sub" in text
      assert "Missing required workbook tool file" in text


  def test_master_installer_runs_installers_in_fixed_order():
      text = macro_text()
      native = text.index("InstallShiftManagerNativeMacros")
      recipe = text.index("InstallRecipeBuilder")
      export = text.index("InstallExportValidation")
      actuals = text.index("InstallActualsCapture")
      assert native < recipe < export < actuals


  def test_master_installer_preserves_itself():
      text = macro_text()
      assert "WORKBOOK_TOOLS_MASTER_INSTALLER_MODULE" in text
      assert "Skip managed cleanup for the running master installer" in text
  ```

- [x] **Step 2: Add native macro contract tests**

  Create `tests/test_shift_manager_native_macro_contract.py`:

  ```python
  from pathlib import Path

  ROOT = Path(__file__).resolve().parents[1]
  NATIVE = ROOT / "interim-costing-process/excel-tools/native/shift-manager-native-macros.bas"


  def macro_text() -> str:
      return NATIVE.read_text(encoding="utf-8")


  def test_native_macro_uses_marko_filter_range_as_standard():
      assert 'A4:AX30000' in macro_text()


  def test_native_macro_uses_marko_back_side_print_range_as_standard():
      text = macro_text()
      assert "AS55:BC105" in text
      assert "AS56:BC106" not in text


  def test_native_macro_installs_database_change_handler():
      text = macro_text()
      assert "InstallDatabaseNativeSheetCode" in text
      assert "Worksheet_Change" in text
      assert "ApplyDatabaseFilters" in text
      assert 'Me.Range("C2,D2,F2")' in text


  def test_native_macro_installs_technology_card_print_entry_points():
      text = macro_text()
      for procedure in [
          "PrintFlexprinting",
          "PrintExtrusion",
          "PrintRerolling",
          "PrintConfection",
      ]:
          assert procedure in text
  ```

- [x] **Step 3: Add Actuals Capture contract tests**

  Create `tests/test_actuals_capture_macro_contract.py`:

  ```python
  from pathlib import Path

  ROOT = Path(__file__).resolve().parents[1]
  ACTUALS = ROOT / "interim-costing-process/excel-tools/actuals-capture/actuals-capture-installer.bas"


  def macro_text() -> str:
      return ACTUALS.read_text(encoding="utf-8")


  def test_actuals_capture_owns_expected_sheets():
      text = macro_text()
      for sheet in [
          "Actuals Entry",
          "Actuals Review",
          "Actuals Validation",
          "ActualsData",
          "ActualsStatus",
          "ActualsConfig",
      ]:
          assert sheet in text


  def test_actuals_config_defines_cutoff_and_inclusion_tables():
      text = macro_text()
      assert "WorkbookConfig" in text
      assert "ExplicitInclusions" in text
      assert "FirstIncludedRow" in text
      assert "FirstIncludedProductionOrder" in text


  def test_actuals_validation_checks_duplicates_inside_included_set():
      text = macro_text()
      assert "ValidateDuplicateIncludedProductionOrders" in text
      assert "Duplicate production order number in included Actuals row set" in text


  def test_actuals_operation_flags_trim_and_accept_lowercase_da():
      text = macro_text()
      assert "OperationFlagIsYes" in text
      assert 'LCase$(Trim$(' in text
      assert '"да"' in text
  ```

- [x] **Step 4: Run contract tests and verify they fail before implementation**

  Run:

  ```bash
  source .venv/bin/activate
  python -m pytest tests/test_workbook_tools_master_installer_contract.py tests/test_shift_manager_native_macro_contract.py tests/test_actuals_capture_macro_contract.py -q
  ```

  Expected: tests fail because the new macro files do not exist yet.

## Task 3: Create Canonical Native Macro Bundle

**Files:**

- Create: `interim-costing-process/excel-tools/native/README.md`
- Create: `interim-costing-process/excel-tools/native/shift-manager-native-macros.bas`
- Test: `tests/test_shift_manager_native_macro_contract.py`

- [x] **Step 1: Write native README**

  Create `interim-costing-process/excel-tools/native/README.md`:

  ```markdown
  # Shift Manager Native Macros

  This bundle preserves and homogenizes the native VBA behavior already present
  in the shift-manager workbooks.

  The canonical native behavior follows Marco's current workbook:

  - `Database.Worksheet_Change` watches `C2`, `D2`, and `F2`.
  - Changing those cells reapplies filters over `Database!A4:AX30000`.
  - `Technology Cards` print buttons keep their existing operation-specific
    macro names.
  - Back-side print range is `AS55:BC105`.

  This file is installed by the master workbook-tools installer. It should not
  be imported as a random standalone utility unless testing a workbook copy.
  ```

- [x] **Step 2: Implement native installer module**

  Create `interim-costing-process/excel-tools/native/shift-manager-native-macros.bas`
  with:

  ```vb
  Attribute VB_Name = "ShiftManagerNativeMacros"
  Option Explicit

  Private Const DATABASE_SHEET_NAME As String = "Database"
  Private Const TECHNOLOGY_CARDS_SHEET_NAME As String = "Technology Cards"
  Private Const DATABASE_FILTER_RANGE As String = "A4:AX30000"
  Private Const BACK_SIDE_PRINT_RANGE As String = "AS55:BC105"

  Public Sub InstallShiftManagerNativeMacros()
      InstallDatabaseNativeSheetCode
      InstallTechnologyCardsNativeSheetCode
      MsgBox "Shift-manager native macros installed.", vbInformation, "Workbook Tools"
  End Sub

  Public Sub InstallDatabaseNativeSheetCode()
      Dim ws As Worksheet
      Set ws = ThisWorkbook.Worksheets(DATABASE_SHEET_NAME)

      ReplaceSheetCodeProcedure ws, "Worksheet_Change", DatabaseWorksheetChangeCode()
      ReplaceSheetCodeProcedure ws, "ApplyDatabaseFilters", DatabaseApplyFiltersCode()
  End Sub

  Public Sub InstallTechnologyCardsNativeSheetCode()
      Dim ws As Worksheet
      Set ws = ThisWorkbook.Worksheets(TECHNOLOGY_CARDS_SHEET_NAME)

      ReplaceSheetCodeProcedure ws, "Copy_MoveWS", CopyMoveWorksheetCode()
      ReplaceSheetCodeProcedure ws, "FixPrintMargins", FixPrintMarginsCode()
      ReplaceSheetCodeProcedure ws, "PrintFlexprinting", PrintFlexprintingCode()
      ReplaceSheetCodeProcedure ws, "PrintExtrusion", PrintExtrusionCode()
      ReplaceSheetCodeProcedure ws, "PrintRerolling", PrintRerollingCode()
      ReplaceSheetCodeProcedure ws, "PrintConfection", PrintConfectionCode()
  End Sub

  Private Sub ReplaceSheetCodeProcedure(ByVal ws As Worksheet, ByVal procedureName As String, ByVal procedureCode As String)
      Dim codeModule As Object
      Dim startLine As Long
      Dim lineCount As Long

      Set codeModule = ThisWorkbook.VBProject.VBComponents(ws.CodeName).CodeModule

      On Error Resume Next
      startLine = codeModule.ProcStartLine(procedureName, 0)
      If Err.Number = 0 And startLine > 0 Then
          lineCount = codeModule.ProcCountLines(procedureName, 0)
          codeModule.DeleteLines startLine, lineCount
      End If
      Err.Clear
      On Error GoTo 0

      codeModule.AddFromString procedureCode
  End Sub
  ```

- [x] **Step 3: Add code-string builder functions**

  Add builder functions to the same file:

  ```vb
  Private Function DatabaseWorksheetChangeCode() As String
      DatabaseWorksheetChangeCode = _
          "Private Sub Worksheet_Change(ByVal Target As Range)" & vbCrLf & _
          "    If Intersect(Target, Me.Range(""C2,D2,F2"")) Is Nothing Then Exit Sub" & vbCrLf & _
          "    ApplyDatabaseFilters" & vbCrLf & _
          "End Sub"
  End Function

  Private Function DatabaseApplyFiltersCode() As String
      DatabaseApplyFiltersCode = _
          "Private Sub ApplyDatabaseFilters()" & vbCrLf & _
          "    On Error GoTo CleanUp" & vbCrLf & _
          "    Dim rng As Range" & vbCrLf & _
          "    Set rng = Me.Range(""" & DATABASE_FILTER_RANGE & """)" & vbCrLf & _
          "    Application.ScreenUpdating = False" & vbCrLf & _
          "    Application.EnableEvents = False" & vbCrLf & _
          "    If Not Me.AutoFilterMode Then rng.AutoFilter" & vbCrLf & _
          "    If Len(Me.Range(""C2"").Value) > 0 Then" & vbCrLf & _
          "        If IsDate(Me.Range(""C2"").Value) Then" & vbCrLf & _
          "            rng.AutoFilter Field:=3, Criteria1:="">="" & CLng(CDate(Me.Range(""C2"").Value)), Operator:=xlAnd, Criteria2:=""<"" & CLng(CDate(Me.Range(""C2"").Value)) + 1" & vbCrLf & _
          "        Else" & vbCrLf & _
          "            rng.AutoFilter Field:=3" & vbCrLf & _
          "        End If" & vbCrLf & _
          "    Else" & vbCrLf & _
          "        rng.AutoFilter Field:=3" & vbCrLf & _
          "    End If" & vbCrLf & _
          "    If Len(Me.Range(""D2"").Value) > 0 Then rng.AutoFilter Field:=4, Criteria1:=""*"" & Me.Range(""D2"").Value & ""*"" Else rng.AutoFilter Field:=4" & vbCrLf & _
          "    If Len(Me.Range(""F2"").Value) > 0 Then rng.AutoFilter Field:=6, Criteria1:=""*"" & Me.Range(""F2"").Value & ""*"" Else rng.AutoFilter Field:=6" & vbCrLf & _
          "CleanUp:" & vbCrLf & _
          "    Application.EnableEvents = True" & vbCrLf & _
          "    Application.ScreenUpdating = True" & vbCrLf & _
          "End Sub"
  End Function
  ```

- [x] **Step 4: Add print macro code builders**

  Add:

  ```vb
  Private Function CopyMoveWorksheetCode() As String
      CopyMoveWorksheetCode = _
          "Sub Copy_MoveWS()" & vbCrLf & _
          "    Worksheets(""Technology Cards"").Copy Before:=Worksheets(1)" & vbCrLf & _
          "    ActiveSheet.Move" & vbCrLf & _
          "    Dim ExternalLinks As Variant" & vbCrLf & _
          "    Dim wb As Workbook" & vbCrLf & _
          "    Dim x As Long" & vbCrLf & _
          "    Set wb = ActiveWorkbook" & vbCrLf & _
          "    ExternalLinks = wb.LinkSources(Type:=xlLinkTypeExcelLinks)" & vbCrLf & _
          "    If Not IsEmpty(ExternalLinks) Then" & vbCrLf & _
          "        For x = LBound(ExternalLinks) To UBound(ExternalLinks)" & vbCrLf & _
          "            wb.BreakLink Name:=ExternalLinks(x), Type:=xlLinkTypeExcelLinks" & vbCrLf & _
          "        Next x" & vbCrLf & _
          "    End If" & vbCrLf & _
          "End Sub"
  End Function

  Private Function FixPrintMarginsCode() As String
      FixPrintMarginsCode = _
          "Private Sub FixPrintMargins()" & vbCrLf & _
          "    With ActiveSheet.PageSetup" & vbCrLf & _
          "        .LeftMargin = Application.CentimetersToPoints(0.3)" & vbCrLf & _
          "        .RightMargin = Application.CentimetersToPoints(0.3)" & vbCrLf & _
          "        .TopMargin = Application.CentimetersToPoints(0.3)" & vbCrLf & _
          "        .BottomMargin = Application.CentimetersToPoints(0.3)" & vbCrLf & _
          "        .HeaderMargin = Application.CentimetersToPoints(0)" & vbCrLf & _
          "        .FooterMargin = Application.CentimetersToPoints(0)" & vbCrLf & _
          "        .CenterHorizontally = True" & vbCrLf & _
          "        .CenterVertically = False" & vbCrLf & _
          "        .Zoom = False" & vbCrLf & _
          "        .FitToPagesWide = 1" & vbCrLf & _
          "        .FitToPagesTall = 1" & vbCrLf & _
          "    End With" & vbCrLf & _
          "End Sub"
  End Function

  Private Function PrintFlexprintingCode() As String
      PrintFlexprintingCode = PrintProcedureCode("PrintFlexprinting", "A1:K55")
  End Function

  Private Function PrintExtrusionCode() As String
      PrintExtrusionCode = PrintProcedureCode("PrintExtrusion", "L1:V55")
  End Function

  Private Function PrintRerollingCode() As String
      PrintRerollingCode = PrintProcedureCode("PrintRerolling", "W1:AG55")
  End Function

  Private Function PrintConfectionCode() As String
      PrintConfectionCode = PrintProcedureCode("PrintConfection", "AH1:AR55")
  End Function

  Private Function PrintProcedureCode(ByVal procedureName As String, ByVal frontRange As String) As String
      PrintProcedureCode = _
          "Sub " & procedureName & "()" & vbCrLf & _
          "    FixPrintMargins" & vbCrLf & _
          "    Range(""" & frontRange & "," & BACK_SIDE_PRINT_RANGE & """).PrintOut" & vbCrLf & _
          "End Sub"
  End Function
  ```

- [x] **Step 5: Run native contract tests**

  Run:

  ```bash
  source .venv/bin/activate
  python -m pytest tests/test_shift_manager_native_macro_contract.py -q
  ```

  Expected: pass.

## Task 4: Build Workbook Tools Master Installer

**Files:**

- Create: `interim-costing-process/excel-tools/workbook-installer/README.md`
- Create: `interim-costing-process/excel-tools/workbook-installer/workbook-tools-master-installer.bas`
- Test: `tests/test_workbook_tools_master_installer_contract.py`

- [x] **Step 1: Write master installer README**

  Create `interim-costing-process/excel-tools/workbook-installer/README.md`:

  ```markdown
  # Workbook Tools Master Installer

  Use this installer on a copy first.

  Required folder files:

  - `shift-manager-native-macros.bas`
  - `recipe-builder-installer.bas`
  - `export-validation.bas`
  - `actuals-capture-installer.bas`

  Import `workbook-tools-master-installer.bas` into the target shift-manager
  workbook, run `InstallWorkbookTools`, choose the folder containing the four
  required files, and save the workbook as `.xlsm`.

  Excel must allow trusted access to the VBA project object model.
  ```

- [x] **Step 2: Add master installer constants and entry point**

  Create `interim-costing-process/excel-tools/workbook-installer/workbook-tools-master-installer.bas`:

  ```vb
  Attribute VB_Name = "WorkbookToolsMasterInstaller"
  Option Explicit

  Private Const WORKBOOK_TOOLS_MASTER_INSTALLER_MODULE As String = "WorkbookToolsMasterInstaller"

  Private Const FILE_NATIVE As String = "shift-manager-native-macros.bas"
  Private Const FILE_RECIPE As String = "recipe-builder-installer.bas"
  Private Const FILE_EXPORT As String = "export-validation.bas"
  Private Const FILE_ACTUALS As String = "actuals-capture-installer.bas"

  Public Sub InstallWorkbookTools()
      Dim folderPath As String
      folderPath = ChooseInstallFolder()
      If Len(folderPath) = 0 Then Exit Sub

      If Not ValidateRequiredBundleFiles(folderPath) Then Exit Sub

      On Error GoTo InstallFailed
      Application.ScreenUpdating = False

      RemoveManagedWorkbookToolComponents
      ImportBundleFile folderPath, FILE_NATIVE
      ImportBundleFile folderPath, FILE_RECIPE
      ImportBundleFile folderPath, FILE_EXPORT
      ImportBundleFile folderPath, FILE_ACTUALS

      InstallShiftManagerNativeMacros
      InstallRecipeBuilder
      InstallExportValidation
      InstallActualsCapture

      Application.ScreenUpdating = True
      MsgBox "Workbook tools installed successfully.", vbInformation, "Workbook Tools"
      Exit Sub

  InstallFailed:
      Application.ScreenUpdating = True
      MsgBox "Workbook tools installation failed: " & Err.Description, vbCritical, "Workbook Tools"
  End Sub
  ```

- [x] **Step 3: Add folder picker and required-file validation**

  Add:

  ```vb
  Private Function ChooseInstallFolder() As String
      With Application.FileDialog(msoFileDialogFolderPicker)
          .Title = "Select folder containing workbook tool .bas files"
          .AllowMultiSelect = False
          If .Show <> -1 Then
              ChooseInstallFolder = vbNullString
          Else
              ChooseInstallFolder = .SelectedItems(1)
          End If
      End With
  End Function

  Private Function ValidateRequiredBundleFiles(ByVal folderPath As String) As Boolean
      Dim missing As Collection
      Set missing = New Collection

      AddMissingFileIfNeeded missing, folderPath, FILE_NATIVE
      AddMissingFileIfNeeded missing, folderPath, FILE_RECIPE
      AddMissingFileIfNeeded missing, folderPath, FILE_EXPORT
      AddMissingFileIfNeeded missing, folderPath, FILE_ACTUALS

      If missing.Count > 0 Then
          MsgBox "Missing required workbook tool file:" & vbCrLf & JoinCollection(missing, vbCrLf), vbCritical, "Workbook Tools"
          ValidateRequiredBundleFiles = False
          Exit Function
      End If

      ValidateRequiredBundleFiles = True
  End Function

  Private Sub AddMissingFileIfNeeded(ByVal missing As Collection, ByVal folderPath As String, ByVal filename As String)
      If Len(Dir$(folderPath & Application.PathSeparator & filename)) = 0 Then
          missing.Add filename
      End If
  End Sub
  ```

- [x] **Step 4: Add managed cleanup/import helpers**

  Add:

  ```vb
  Private Sub RemoveManagedWorkbookToolComponents()
      Dim managedNames As Variant
      managedNames = Array( _
          "ShiftManagerNativeMacros", _
          "RecipeBuilderInstaller", _
          "frmRecipeBuilderExtrusion", _
          "frmRecipeBuilderPrinting", _
          "frmRecipeBuilderCascading", _
          "ExportValidation", _
          "ActualsCaptureInstaller" _
      )

      Dim components As Object
      Set components = ThisWorkbook.VBProject.VBComponents

      Dim nameValue As Variant
      For Each nameValue In managedNames
          RemoveComponentIfExists components, CStr(nameValue)
      Next nameValue
  End Sub

  Private Sub RemoveComponentIfExists(ByVal components As Object, ByVal componentName As String)
      Dim component As Object

      If componentName = WORKBOOK_TOOLS_MASTER_INSTALLER_MODULE Then
          ' Skip managed cleanup for the running master installer.
          Exit Sub
      End If

      For Each component In components
          If component.Name = componentName Then
              components.Remove component
              Exit Sub
          End If
      Next component
  End Sub

  Private Sub ImportBundleFile(ByVal folderPath As String, ByVal filename As String)
      ThisWorkbook.VBProject.VBComponents.Import folderPath & Application.PathSeparator & filename
  End Sub

  Private Function JoinCollection(ByVal values As Collection, ByVal delimiter As String) As String
      Dim parts() As String
      Dim i As Long

      ReDim parts(1 To values.Count)
      For i = 1 To values.Count
          parts(i) = CStr(values(i))
      Next i

      JoinCollection = Join(parts, delimiter)
  End Function
  ```

- [x] **Step 5: Run master installer contract tests**

  Run:

  ```bash
  source .venv/bin/activate
  python -m pytest tests/test_workbook_tools_master_installer_contract.py -q
  ```

  Expected: pass.

## Task 5: Standardize Recipe Builder And Export Validation For Master Install

**Files:**

- Modify: `interim-costing-process/excel-tools/recipe-builder/recipe-builder-installer.bas`
- Modify: `interim-costing-process/excel-tools/recipe-builder/README.md`
- Modify: `interim-costing-process/excel-tools/export-validation/export-validation.bas`
- Modify: `interim-costing-process/excel-tools/export-validation/README.md`
- Test: existing export/recipe contract tests

- [x] **Step 1: Keep Recipe Builder `ThisWorkbook` targeting**

  Verify with:

  ```bash
  rg -n "ThisWorkbook|ActiveWorkbook" interim-costing-process/excel-tools/recipe-builder/recipe-builder-installer.bas
  ```

  Expected: workbook mutation targets `ThisWorkbook`, not `ActiveWorkbook`.

- [x] **Step 2: Convert Export Validation installer target to `ThisWorkbook`**

  In `export-validation.bas`, change public macro workbook targets from:

  ```vb
  Dim workbook As Workbook
  Set workbook = ActiveWorkbook
  ```

  to:

  ```vb
  Dim workbook As Workbook
  Set workbook = ThisWorkbook
  ```

  for installer/validation/export entry points that operate on the installed
  target workbook.

- [x] **Step 3: Preserve active-sheet selection checks**

  Keep user workflow checks such as:

  ```vb
  If ActiveSheet.Name <> DATABASE_SHEET_NAME Then
      MsgBox "Open the Database sheet, select rows to validate, and run the macro again.", vbExclamation
      Exit Sub
  End If
  ```

  because row selection still happens through the active UI sheet.

- [x] **Step 4: Update READMEs**

  In both helper READMEs, add:

  ```text
  Preferred installation is through `workbook-tools-master-installer.bas`.
  Direct installation remains available for development/debugging.
  ```

- [x] **Step 5: Run relevant tests**

  Run:

  ```bash
  source .venv/bin/activate
  python -m pytest tests/test_excel_export_macro_contract.py -q
  python -m pytest tests/test_workbook_tools_master_installer_contract.py -q
  ```

  Expected: pass. If existing export contract tests assert `ActiveWorkbook`,
  update them to the approved `ThisWorkbook` master-installer contract.

## Task 6: Create Actuals Capture Installer Skeleton And Sheet Contracts

**Files:**

- Create: `interim-costing-process/excel-tools/actuals-capture/README.md`
- Create: `interim-costing-process/excel-tools/actuals-capture/actuals-capture-installer.bas`
- Test: `tests/test_actuals_capture_macro_contract.py`

- [x] **Step 1: Write Actuals Capture README**

  Create:

  ```markdown
  # Actuals Capture

  Actuals Capture V1 stores completed operational-card actuals inside helper
  sheets in the shift-manager workbook.

  It does not write actuals to `Database`.

  It is normally installed through `workbook-tools-master-installer.bas`.
  ```

- [x] **Step 2: Add installer constants and entry point**

  Create `actuals-capture-installer.bas`:

  ```vb
  Attribute VB_Name = "ActualsCaptureInstaller"
  Option Explicit

  Private Const DATABASE_SHEET_NAME As String = "Database"
  Private Const ENTRY_SHEET_NAME As String = "Actuals Entry"
  Private Const REVIEW_SHEET_NAME As String = "Actuals Review"
  Private Const VALIDATION_SHEET_NAME As String = "Actuals Validation"
  Private Const DATA_SHEET_NAME As String = "ActualsData"
  Private Const STATUS_SHEET_NAME As String = "ActualsStatus"
  Private Const CONFIG_SHEET_NAME As String = "ActualsConfig"
  Private Const SHEET_PASSWORD As String = "actuals-v1"

  Public Sub InstallActualsCapture()
      EnsureActualsSheets
      SetupActualsConfig
      SetupActualsData
      SetupActualsStatus
      SetupActualsEntry
      SetupActualsReview
      SetupActualsValidation
      ApplyActualsProtection
      MsgBox "Actuals Capture installed.", vbInformation, "Actuals Capture"
  End Sub
  ```

- [x] **Step 3: Add sheet creation helpers**

  Add:

  ```vb
  Private Sub EnsureActualsSheets()
      EnsureSheet ENTRY_SHEET_NAME, True
      EnsureSheet REVIEW_SHEET_NAME, True
      EnsureSheet VALIDATION_SHEET_NAME, True
      EnsureSheet DATA_SHEET_NAME, False
      EnsureSheet STATUS_SHEET_NAME, False
      EnsureSheet CONFIG_SHEET_NAME, False
  End Sub

  Private Function EnsureSheet(ByVal sheetName As String, ByVal visibleSheet As Boolean) As Worksheet
      On Error Resume Next
      Set EnsureSheet = ThisWorkbook.Worksheets(sheetName)
      On Error GoTo 0

      If EnsureSheet Is Nothing Then
          Set EnsureSheet = ThisWorkbook.Worksheets.Add(After:=ThisWorkbook.Worksheets(ThisWorkbook.Worksheets.Count))
          EnsureSheet.Name = sheetName
      End If

      If visibleSheet Then
          EnsureSheet.Visible = xlSheetVisible
      Else
          EnsureSheet.Visible = xlSheetHidden
      End If
  End Function
  ```

- [x] **Step 4: Run Actuals contract test**

  Run:

  ```bash
  source .venv/bin/activate
  python -m pytest tests/test_actuals_capture_macro_contract.py -q
  ```

  Expected: fails on `WorkbookConfig`, `ExplicitInclusions`,
  `FirstIncludedRow`, `FirstIncludedProductionOrder`,
  `ValidateDuplicateIncludedProductionOrders`, and `OperationFlagIsYes`. Those
  names are added in Tasks 7 and 12.

## Task 7: Implement `ActualsConfig` Included-Set Configuration

**Files:**

- Modify: `interim-costing-process/excel-tools/actuals-capture/actuals-capture-installer.bas`
- Test: `tests/test_actuals_capture_macro_contract.py`

- [x] **Step 1: Add `ActualsConfig` setup**

  Add:

  ```vb
  Private Sub SetupActualsConfig()
      Dim ws As Worksheet
      Set ws = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)

      ws.Cells.Clear
      ws.Range("A1:D1").Value = Array("WorkbookConfig", "Value", "Notes", "Reserved")
      ws.Range("A2:D2").Value = Array("FirstIncludedRow", "", "First Database row included in V1 actuals.", "")
      ws.Range("A3:D3").Value = Array("FirstIncludedProductionOrder", "", "Production order at the cutoff row.", "")

      ws.Range("A6:D6").Value = Array("ExplicitInclusions", "RowNumber", "ProductionOrder", "Notes")
      ws.Range("A7:D7").Value = Array("Include", "", "", "Add exact pre-cutoff row/order pairs here.")

      ws.Range("A10:C10").Value = Array("OperationCode", "Operation", "DatabaseFlagColumn")
      ws.Range("A11:C11").Value = Array("PRN", "Printing", "Q")
      ws.Range("A12:C12").Value = Array("EXT", "Extrusion", "R")
      ws.Range("A13:C13").Value = Array("RWS", "Rewinding / Slitting", "S")
      ws.Range("A14:C14").Value = Array("CON", "Confection", "T")

      ws.Range("A17:A22").Value = Application.WorksheetFunction.Transpose(Array("StatusList", "Planned", "In Production", "On Hold", "Completed", "Cancelled"))
      ws.Rows(1).Font.Bold = True
      ws.Rows(6).Font.Bold = True
      ws.Rows(10).Font.Bold = True
      ws.Columns("A:D").AutoFit
  End Sub
  ```

- [x] **Step 2: Add config readers**

  Add:

  ```vb
  Private Function FirstIncludedRow() As Long
      FirstIncludedRow = CLng(ConfigValue("FirstIncludedRow"))
  End Function

  Private Function FirstIncludedProductionOrder() As String
      FirstIncludedProductionOrder = Trim$(CStr(ConfigValue("FirstIncludedProductionOrder")))
  End Function

  Private Function ConfigValue(ByVal settingName As String) As Variant
      Dim ws As Worksheet
      Set ws = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)

      Dim rowNumber As Long
      For rowNumber = 2 To 100
          If CStr(ws.Cells(rowNumber, 1).Value) = settingName Then
              ConfigValue = ws.Cells(rowNumber, 2).Value
              Exit Function
          End If
      Next rowNumber

      Err.Raise vbObjectError + 2000, , "Missing ActualsConfig setting: " & settingName
  End Function
  ```

- [x] **Step 3: Add explicit inclusion reader**

  Add:

  ```vb
  Private Function ExplicitInclusionKey(ByVal rowNumber As Long, ByVal productionOrder As String) As String
      ExplicitInclusionKey = CStr(rowNumber) & "|" & Trim$(productionOrder)
  End Function

  Private Function LoadExplicitInclusions() As Object
      Dim inclusions As Object
      Set inclusions = CreateObject("Scripting.Dictionary")

      Dim ws As Worksheet
      Set ws = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)

      Dim rowNumber As Long
      For rowNumber = 7 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
          If LCase$(Trim$(CStr(ws.Cells(rowNumber, 1).Value))) = "include" Then
              inclusions(ExplicitInclusionKey(CLng(ws.Cells(rowNumber, 2).Value), CStr(ws.Cells(rowNumber, 3).Value))) = True
          End If
      Next rowNumber

      Set LoadExplicitInclusions = inclusions
  End Function
  ```

- [x] **Step 4: Add included-row predicate**

  Add:

  ```vb
  Private Function RowIsInActualsScope(ByVal databaseRow As Long, ByVal productionOrder As String, ByVal inclusions As Object) As Boolean
      If databaseRow >= FirstIncludedRow() Then
          RowIsInActualsScope = True
          Exit Function
      End If

      RowIsInActualsScope = inclusions.Exists(ExplicitInclusionKey(databaseRow, productionOrder))
  End Function
  ```

- [x] **Step 5: Run Actuals contract test**

  Run:

  ```bash
  source .venv/bin/activate
  python -m pytest tests/test_actuals_capture_macro_contract.py -q
  ```

  Expected: config-related tests pass.

## Task 8: Implement Actuals Storage Sheet Headers

**Files:**

- Modify: `interim-costing-process/excel-tools/actuals-capture/actuals-capture-installer.bas`

- [x] **Step 1: Add `ActualsData` headers**

  Add:

  ```vb
  Private Sub SetupActualsData()
      Dim ws As Worksheet
      Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

      ws.Range("A1:AD1").Value = Array( _
          "Actual card ID", "Production order", "Database row", "Operation", "Operation code", _
          "Actual card number", "Produces finished product?", "Start date", "Start time", _
          "Stop date", "Stop time", "Start datetime normalized", "Stop datetime normalized", _
          "Pause minutes", "Extra minutes", "Calculated total minutes", "Total minutes override", _
          "Override reason", "Total minutes", "Gross kg", "Tare count", "Tare weight kg", _
          "Calculated net kg", "Manual net kg override", "Net kg", "Waste kg", "Meters produced", _
          "Units", "PP film material", "PP film quantity kg" _
      )
      ws.Range("AE1:AI1").Value = Array("Notes", "Voided?", "Void reason", "CreatedAt", "UpdatedAt")
      ws.Rows(1).Font.Bold = True
      ws.Columns("A:AI").AutoFit
  End Sub
  ```

- [x] **Step 2: Add `ActualsStatus` headers**

  Add:

  ```vb
  Private Sub SetupActualsStatus()
      Dim ws As Worksheet
      Set ws = ThisWorkbook.Worksheets(STATUS_SHEET_NAME)

      ws.Range("A1:C1").Value = Array("Production order", "Status", "UpdatedAt")
      ws.Rows(1).Font.Bold = True
      ws.Columns("A:C").AutoFit
  End Sub
  ```

- [x] **Step 3: Preserve existing data on reinstall**

  Before clearing or rewriting headers in `SetupActualsData` and
  `SetupActualsStatus`, add:

  ```vb
  If Len(Trim$(CStr(ws.Range("A1").Value))) > 0 Then
      EnsureHeaderMatches ws, expectedHeaders
      Exit Sub
  End If
  ```

  Implement `EnsureHeaderMatches` so reinstall fails with a message if a helper
  sheet has unexpected headers instead of overwriting saved actuals.

## Task 9: Build Actuals Entry Sheet And Save/Load Workflow

**Files:**

- Modify: `interim-costing-process/excel-tools/actuals-capture/actuals-capture-installer.bas`

- [x] **Step 1: Create static entry layout**

  `SetupActualsEntry` should create labeled cells for:

  ```text
  Production order
  Database row
  Operation
  Current status
  Customer
  Product/type
  Expected operations
  Produces finished product?
  Start date / Start time / Stop date / Stop time
  Pause minutes / Extra minutes / Total minutes override / Override reason
  Gross kg / Tare count / Tare weight kg / Manual net kg override
  Waste kg / Meters produced / Units
  PP film material / PP film quantity kg
  Notes
  Selected actual card ID
  ```

  Use named ranges for input cells, for example:

  ```vb
  ThisWorkbook.Names.Add Name:="ActualsEntryProductionOrder", RefersTo:=ws.Range("B3")
  ThisWorkbook.Names.Add Name:="ActualsEntryDatabaseRow", RefersTo:=ws.Range("B4")
  ThisWorkbook.Names.Add Name:="ActualsEntryOperation", RefersTo:=ws.Range("B5")
  ```

- [x] **Step 2: Add entry buttons**

  Add form-control buttons assigned to:

  ```text
  LoadActualsEntryOrder
  SaveNewActualCard
  LoadSelectedActualCard
  SaveActualCardChanges
  VoidSelectedActualCard
  ClearActualsEntryFields
  ```

- [x] **Step 3: Implement order load behavior**

  `LoadActualsEntryOrder` should:

  - require production order;
  - locate exactly one included `Database` row for that order;
  - block if no included row exists;
  - block if more than one included row exists;
  - populate customer/product/type/status/expected-operation context;
  - list existing non-deleted saved cards for that order.

- [x] **Step 4: Implement actual-card save behavior**

  `SaveNewActualCard` should:

  - validate order exists in the included row set;
  - validate selected operation is expected;
  - require confirmation when another active card exists for the same
    production order and operation;
  - assign next card number by production order + operation;
  - write one row to `ActualsData`;
  - set `CreatedAt` and `UpdatedAt`.

- [x] **Step 5: Implement edit and void behavior**

  `LoadSelectedActualCard`, `SaveActualCardChanges`, and `VoidSelectedActualCard`
  should operate by `Actual card ID`, not by row position alone.

## Task 10: Implement Time And Quantity Calculations

**Files:**

- Modify: `interim-costing-process/excel-tools/actuals-capture/actuals-capture-installer.bas`

- [x] **Step 1: Add common numeric parsing helpers**

  Implement:

  ```vb
  Private Function TryParseNonNegativeNumber(ByVal value As Variant, ByRef parsedNumber As Double) As Boolean
      If Len(Trim$(CStr(value))) = 0 Then
          parsedNumber = 0
          TryParseNonNegativeNumber = True
          Exit Function
      End If

      If Not IsNumeric(value) Then Exit Function
      parsedNumber = CDbl(value)
      TryParseNonNegativeNumber = (parsedNumber >= 0)
  End Function
  ```

- [x] **Step 2: Add net calculation**

  Implement:

  ```vb
  Private Function CalculatedNetKg(ByVal grossKg As Double, ByVal tareCount As Double, ByVal tareWeightKg As Double) As Double
      CalculatedNetKg = grossKg - (tareCount * tareWeightKg)
  End Function
  ```

- [x] **Step 3: Add time calculation**

  Implement:

  ```vb
  Private Function TotalMinutesForOperation(ByVal operationName As String, ByVal startAt As Date, ByVal stopAt As Date, ByVal pauseMinutes As Double, ByVal extraMinutes As Double) As Double
      If operationName = "Extrusion" Then
          TotalMinutesForOperation = DateDiff("n", startAt, stopAt) - pauseMinutes
      Else
          TotalMinutesForOperation = WorkingMinutesBetween(startAt, stopAt) - pauseMinutes + extraMinutes
      End If
  End Function
  ```

  Add `WorkingMinutesBetween` using `ActualsConfig` working calendar rows. For
  V1, default to Monday-Friday 08:00-17:00 when no exception row is configured.

## Task 11: Build Actuals Review

**Files:**

- Modify: `interim-costing-process/excel-tools/actuals-capture/actuals-capture-installer.bas`

- [x] **Step 1: Add review buttons**

  `SetupActualsReview` creates buttons:

  ```text
  RefreshActualsReview
  SaveActualsReview
  RunActualsValidation
  ```

- [x] **Step 2: Implement review generation**

  `RefreshActualsReview` should:

  - scan only included `Database` rows;
  - generate `In Production / On Hold` table first;
  - generate `Planned` table second;
  - sort each table by production order ascending;
  - show customer, product/type, status, operations entered/expected, gross
    ordered kg, and finished-product actual totals.

- [x] **Step 3: Implement status save**

  `SaveActualsReview` should update `ActualsStatus` rows by production order.
  Missing status rows default to `Planned` during review generation.

## Task 12: Build Actuals Validation

**Files:**

- Modify: `interim-costing-process/excel-tools/actuals-capture/actuals-capture-installer.bas`

- [x] **Step 1: Implement validation report generation**

  `RunActualsValidation` should clear and regenerate `Actuals Validation`, then
  activate that sheet.

- [x] **Step 2: Add included-set duplicate validation**

  Implement:

  ```vb
  Private Sub ValidateDuplicateIncludedProductionOrders(ByVal errors As Collection)
      Dim wsDatabase As Worksheet
      Set wsDatabase = ThisWorkbook.Worksheets(DATABASE_SHEET_NAME)

      Dim inclusions As Object
      Set inclusions = LoadExplicitInclusions()

      Dim seen As Object
      Set seen = CreateObject("Scripting.Dictionary")

      Dim duplicateReported As Object
      Set duplicateReported = CreateObject("Scripting.Dictionary")

      Dim lastRow As Long
      lastRow = wsDatabase.Cells(wsDatabase.Rows.Count, 1).End(xlUp).Row

      Dim rowNumber As Long
      For rowNumber = 5 To lastRow
          Dim productionOrder As String
          productionOrder = Trim$(CStr(wsDatabase.Cells(rowNumber, 1).Value))

          If Len(productionOrder) > 0 Then
              If RowIsInActualsScope(rowNumber, productionOrder, inclusions) Then
                  If seen.Exists(productionOrder) Then
                      If Not duplicateReported.Exists(productionOrder) Then
                          AddValidationIssue errors, productionOrder, "", "", "", _
                              "Duplicate production order number in included Actuals row set.", _
                              "Correct duplicate production order rows in Database.", _
                              "Database rows " & CStr(seen(productionOrder)) & " and " & CStr(rowNumber)
                          duplicateReported.Add productionOrder, True
                      End If
                  Else
                      seen.Add productionOrder, rowNumber
                  End If
              End If
          End If
      Next rowNumber
  End Sub
  ```

  The report issue text must be:

  ```text
  Duplicate production order number in included Actuals row set.
  ```

- [x] **Step 3: Add completed-order validation**

  For any included order with status `Completed`, require at least one active
  actual card for every expected operation from `Database!Q:T`.

- [x] **Step 4: Add actual-card validation**

  Validate:

  - saved actual operation is still expected;
  - required time fields exist;
  - stop is not before start;
  - numeric fields are non-negative;
  - PP film material and quantity are paired;
  - total minutes override has reason;
  - confection has units.

## Task 13: Protection And Reopen Setup

**Files:**

- Modify: `interim-costing-process/excel-tools/actuals-capture/actuals-capture-installer.bas`
- Modify: `interim-costing-process/excel-tools/workbook-installer/workbook-tools-master-installer.bas`

- [x] **Step 1: Implement `ApplyActualsProtection`**

  Protect generated/helper sheets with `UserInterfaceOnly:=True`. Leave actual
  input cells unlocked.

- [x] **Step 2: Install `Workbook_Open` protection reset**

  Add a workbook-open wrapper that calls:

  ```vb
  Private Sub Workbook_Open()
      On Error Resume Next
      ApplyActualsProtection
      On Error GoTo 0
  End Sub
  ```

  Preserve no existing workbook-open code because current `ThisWorkbook` is
  empty in both inspected workbooks.

## Task 14: End-To-End Verification On Workbook Copies

**Files:**

- Use copies of:
  - `interim-costing-process/source-evidence/workbooks/Поръчки-2026-Елена.xlsm`
  - `interim-costing-process/source-evidence/workbooks/Поръчки-2026-Марко.xlsm`
- Save artifacts under: `artifacts/excel-actuals-capture/`

- [x] **Step 1: Run Python tests**

  Run:

  ```bash
  source .venv/bin/activate
  python -m pytest tests/test_workbook_tools_master_installer_contract.py tests/test_shift_manager_native_macro_contract.py tests/test_actuals_capture_macro_contract.py tests/test_excel_export_macro_contract.py -q
  ```

  Expected: pass.

- [x] **Step 2: Run VBA syntax extraction check**

  Run:

  ```bash
  .venv/bin/olevba interim-costing-process/source-evidence/workbooks/Поръчки-2026-Марко.xlsm > artifacts/excel-actuals-capture/marko-before-vba.txt
  .venv/bin/olevba interim-costing-process/source-evidence/workbooks/Поръчки-2026-Елена.xlsm > artifacts/excel-actuals-capture/elena-before-vba.txt
  ```

  Expected: command exits 0.

- [ ] **Step 3: Manual Excel install test on copies**

  Status: not run in the Linux VM; requires Windows desktop Excel and workbook
  copies.

  On a Windows Excel machine:

  1. Copy each real workbook to a test folder.
  2. Open the copy.
  3. Import `workbook-tools-master-installer.bas`.
  4. Run `InstallWorkbookTools`.
  5. Select the folder containing the four required bundle files.
  6. Save the workbook.

  Expected:

  - all required sheets exist;
  - helper sheets are hidden;
  - existing print buttons still work;
  - `Database` search cells `C2,D2,F2` still filter;
  - Recipe Builder double-clicks work in `W:AD` and `AH:AN`;
  - Export Validation installs and validates selected rows;
  - Actuals Entry loads an included order;
  - Actuals Review refreshes;
  - Actuals Validation reports missing config or missing actuals clearly.

- [ ] **Step 4: Manual update test**

  Status: not run in the Linux VM; requires Windows desktop Excel and workbook
  copies.

  Re-run `InstallWorkbookTools` on the same workbook copy.

  Expected:

  - no duplicate modules/forms;
  - existing `ActualsData` rows are preserved;
  - helper sheet headers remain valid;
  - installer final report succeeds.

## Self-Review Checklist

- [x] Every approved workbook-reality correction is represented.
- [x] Included-row-set behavior is scoped to `ActualsConfig`.
- [x] Duplicate production orders are validation errors only inside the included
  row set.
- [x] Master installer requires all four files before changing the workbook.
- [x] Native macros are homogenized to Marko's standard.
- [x] Actuals Capture does not write actuals into `Database`.
- [x] Recipe Builder remains the only owner of `Database.Worksheet_BeforeDoubleClick`.
- [x] No task requires editing original workbook files.
