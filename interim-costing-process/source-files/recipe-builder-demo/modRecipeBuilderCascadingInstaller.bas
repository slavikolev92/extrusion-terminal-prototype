Attribute VB_Name = "modRecipeBuilderCascadingInstallerV2"
Option Explicit

' Cascading Recipe Builder installer.
' Import this module into the workbook, then run:
' InstallRecipeBuilderV2
'
' The installer creates:
' - RecipeCatalogExtrusion helper sheet header if needed
' - RecipeCatalogPrinting helper sheet header if needed
' - extrusion UserForm for AM:AS recipe cells
' - printing UserForm for AB:AI ink/anilox cells
' - Database sheet double-click router for both builders
'
' Excel may block the UserForm/event installation unless this setting is enabled:
' File > Options > Trust Center > Trust Center Settings > Macro Settings >
' Trust access to the VBA project object model.

Private Const EXTRUSION_CATALOG_SHEET_NAME As String = "RecipeCatalogExtrusion"
Private Const LEGACY_EXTRUSION_CATALOG_SHEET_NAME As String = "RecipeCatalog"
Private Const PRINTING_CATALOG_SHEET_NAME As String = "RecipeCatalogPrinting"
Private Const DATABASE_SHEET_NAME As String = "Database"
Private Const PRINTING_FIRST_COLUMN As String = "AB"
Private Const PRINTING_LAST_COLUMN As String = "AI"
Private Const EXTRUSION_FIRST_COLUMN As String = "AM"
Private Const EXTRUSION_LAST_COLUMN As String = "AS"
Private Const EXTRUSION_FORM_NAME As String = "frmRecipeBuilderExtrusion"
Private Const LEGACY_EXTRUSION_FORM_NAME As String = "frmRecipeBuilderCascading"
Private Const PRINTING_FORM_NAME As String = "frmRecipeBuilderPrinting"
Private Const FORM_FONT_NAME As String = "Calibri"
Private Const FORM_LABEL_FONT_SIZE As Long = 14
Private Const FORM_INPUT_FONT_SIZE As Long = 15
Private Const FORM_BUTTON_FONT_SIZE As Long = 14
Private Const FORM_DROPDOWN_VISIBLE_ROWS As Long = 24

Public Sub InstallRecipeBuilderV2()
    CreateExtrusionRecipeCatalogSheet
    CreatePrintingRecipeCatalogSheet

    If Not TryInstallFormAndEvent() Then
        MsgBox _
            "The recipe catalog sheets/headers were created or preserved, but Excel blocked automatic form installation." & vbCrLf & vbCrLf & _
            "Enable this setting and run InstallRecipeBuilderV2 again:" & vbCrLf & _
            "File > Options > Trust Center > Trust Center Settings > Macro Settings >" & vbCrLf & _
            "Trust access to the VBA project object model.", _
            vbExclamation, _
            "Recipe Builder"
        Exit Sub
    End If

    MsgBox _
        "Recipe Builder installed." & vbCrLf & _
        "Double-click a Database cell in columns " & PRINTING_FIRST_COLUMN & ":" & PRINTING_LAST_COLUMN & _
        " for printing or " & EXTRUSION_FIRST_COLUMN & ":" & EXTRUSION_LAST_COLUMN & " for extrusion.", _
        vbInformation, _
        "Recipe Builder"
End Sub

Public Function IsExtrusionRecipeBuilderCellV2(ByVal target As Range) As Boolean
    If target Is Nothing Then
        IsExtrusionRecipeBuilderCellV2 = False
        Exit Function
    End If

    If target.Worksheet.Name <> DATABASE_SHEET_NAME Then
        IsExtrusionRecipeBuilderCellV2 = False
        Exit Function
    End If

    If target.CountLarge <> 1 Then
        IsExtrusionRecipeBuilderCellV2 = False
        Exit Function
    End If

    IsExtrusionRecipeBuilderCellV2 = Not Intersect( _
        target, _
        target.Worksheet.Range(EXTRUSION_FIRST_COLUMN & ":" & EXTRUSION_LAST_COLUMN) _
    ) Is Nothing
End Function

Public Function IsPrintingRecipeBuilderCellV2(ByVal target As Range) As Boolean
    If target Is Nothing Then
        IsPrintingRecipeBuilderCellV2 = False
        Exit Function
    End If

    If target.Worksheet.Name <> DATABASE_SHEET_NAME Then
        IsPrintingRecipeBuilderCellV2 = False
        Exit Function
    End If

    If target.CountLarge <> 1 Then
        IsPrintingRecipeBuilderCellV2 = False
        Exit Function
    End If

    IsPrintingRecipeBuilderCellV2 = Not Intersect( _
        target, _
        target.Worksheet.Range(PRINTING_FIRST_COLUMN & ":" & PRINTING_LAST_COLUMN) _
    ) Is Nothing
End Function

Public Sub OpenExtrusionRecipeBuilderV2(ByVal target As Range)
    Dim form As Object

    If Not IsExtrusionRecipeBuilderCellV2(target) Then
        Exit Sub
    End If

    Set form = VBA.UserForms.Add(EXTRUSION_FORM_NAME)
    CallByName form, "TargetCell", VbSet, target
    form.Show
End Sub

Public Sub OpenPrintingRecipeBuilderV2(ByVal target As Range)
    Dim form As Object

    If Not IsPrintingRecipeBuilderCellV2(target) Then
        Exit Sub
    End If

    Set form = VBA.UserForms.Add(PRINTING_FORM_NAME)
    CallByName form, "TargetCell", VbSet, target
    form.Show
End Sub

Public Sub OpenExtrusionRecipeBuilderForActiveCellV2()
    OpenExtrusionRecipeBuilderV2 ActiveCell
End Sub

Public Sub OpenPrintingRecipeBuilderForActiveCellV2()
    OpenPrintingRecipeBuilderV2 ActiveCell
End Sub

Private Sub CreateExtrusionRecipeCatalogSheet()
    Dim ws As Worksheet

    Set ws = EnsureExtrusionCatalogSheet()
    ws.Range("A1:D1").Value = Array("Category", "Producer", "GradeCode", "Notes")

    ws.Columns("A:D").AutoFit
    ws.Rows(1).Font.Bold = True
End Sub

Private Sub CreatePrintingRecipeCatalogSheet()
    Dim ws As Worksheet

    Set ws = EnsureSheet(PRINTING_CATALOG_SHEET_NAME)
    ws.Range("A1:C1").Value = Array("Type", "Value", "Notes")

    ws.Columns("A:C").AutoFit
    ws.Rows(1).Font.Bold = True
End Sub

Private Function EnsureExtrusionCatalogSheet() As Worksheet
    Set EnsureExtrusionCatalogSheet = GetSheetIfExists(EXTRUSION_CATALOG_SHEET_NAME)
    If Not EnsureExtrusionCatalogSheet Is Nothing Then Exit Function

    Set EnsureExtrusionCatalogSheet = GetSheetIfExists(LEGACY_EXTRUSION_CATALOG_SHEET_NAME)
    If Not EnsureExtrusionCatalogSheet Is Nothing Then
        EnsureExtrusionCatalogSheet.Name = EXTRUSION_CATALOG_SHEET_NAME
        Exit Function
    End If

    Set EnsureExtrusionCatalogSheet = EnsureSheet(EXTRUSION_CATALOG_SHEET_NAME)
End Function

Private Function GetSheetIfExists(ByVal sheetName As String) As Worksheet
    On Error Resume Next
    Set GetSheetIfExists = ThisWorkbook.Worksheets(sheetName)
    On Error GoTo 0
End Function

Private Function EnsureSheet(ByVal sheetName As String) As Worksheet
    On Error Resume Next
    Set EnsureSheet = ThisWorkbook.Worksheets(sheetName)
    On Error GoTo 0

    If EnsureSheet Is Nothing Then
        Set EnsureSheet = ThisWorkbook.Worksheets.Add( _
            After:=ThisWorkbook.Worksheets(ThisWorkbook.Worksheets.Count) _
        )
        EnsureSheet.Name = sheetName
    End If
End Function

Private Function TryInstallFormAndEvent() As Boolean
    On Error GoTo InstallFailed

    InstallExtrusionRecipeBuilderForm
    InstallPrintingRecipeBuilderForm
    InstallDatabaseDoubleClickHandler
    TryInstallFormAndEvent = True
    Exit Function

InstallFailed:
    TryInstallFormAndEvent = False
End Function

Private Sub InstallExtrusionRecipeBuilderForm()
    Dim project As Object
    Dim components As Object
    Dim formComponent As Object
    Dim designer As Object

    Set project = ThisWorkbook.VBProject
    Set components = project.VBComponents

    RemoveComponentIfExists components, EXTRUSION_FORM_NAME
    RemoveComponentIfExists components, LEGACY_EXTRUSION_FORM_NAME

    Set formComponent = components.Add(3)
    formComponent.Properties("Name").Value = EXTRUSION_FORM_NAME
    formComponent.Properties("Caption").Value = "Extrusion Recipe Builder"
    formComponent.Properties("Width").Value = 600
    formComponent.Properties("Height").Value = 390

    Set designer = formComponent.Designer

    AddLabel designer, "lblCategory", "Material Category", 24, 24, 170, 24
    AddCombo designer, "cboCategory", 215, 20, 320, 26

    AddLabel designer, "lblProducer", "Producer", 24, 72, 170, 24
    AddCombo designer, "cboProducer", 215, 68, 320, 26

    AddLabel designer, "lblGrade", "Grade / Code", 24, 120, 170, 24
    AddCombo designer, "cboGrade", 215, 116, 320, 26

    AddLabel designer, "lblPercent", "Percentage", 24, 168, 170, 24
    AddTextBox designer, "txtPercent", 215, 164, 120, 26

    AddLabel designer, "lblPreview", "Preview", 24, 216, 170, 24
    AddTextBox designer, "txtPreview", 215, 212, 320, 58

    AddCommandButton designer, "cmdInsert", "Insert", 365, 302, 82, 34
    AddCommandButton designer, "cmdCancel", "Cancel", 457, 302, 82, 34

    formComponent.CodeModule.AddFromString ExtrusionRecipeBuilderFormCode()
End Sub

Private Sub InstallPrintingRecipeBuilderForm()
    Dim project As Object
    Dim components As Object
    Dim formComponent As Object
    Dim designer As Object

    Set project = ThisWorkbook.VBProject
    Set components = project.VBComponents

    RemoveComponentIfExists components, PRINTING_FORM_NAME

    Set formComponent = components.Add(3)
    formComponent.Properties("Name").Value = PRINTING_FORM_NAME
    formComponent.Properties("Caption").Value = "Printing Recipe Builder"
    formComponent.Properties("Width").Value = 560
    formComponent.Properties("Height").Value = 500

    Set designer = formComponent.Designer

    AddLabel designer, "lblInkSearch", "Find Ink / Color", 24, 24, 235, 24
    AddTextBox designer, "txtInkSearch", 24, 54, 235, 26

    AddLabel designer, "lblInk", "Matching Inks", 24, 98, 235, 24
    AddListBox designer, "lstInk", 24, 128, 235, 280

    AddLabel designer, "lblAnilox", "Anilox Roller", 294, 24, 235, 24
    AddCombo designer, "cboAnilox", 294, 54, 235, 26

    AddLabel designer, "lblPreview", "Preview", 294, 110, 235, 24
    AddTextBox designer, "txtPreview", 294, 140, 235, 70

    AddCommandButton designer, "cmdInsert", "Insert", 355, 374, 82, 34
    AddCommandButton designer, "cmdCancel", "Cancel", 447, 374, 82, 34

    formComponent.CodeModule.AddFromString PrintingRecipeBuilderFormCode()
End Sub

Private Sub RemoveComponentIfExists(ByVal components As Object, ByVal componentName As String)
    Dim component As Object

    For Each component In components
        If component.Name = componentName Then
            components.Remove component
            Exit Sub
        End If
    Next component
End Sub

Private Sub AddLabel( _
    ByVal designer As Object, _
    ByVal name As String, _
    ByVal caption As String, _
    ByVal left As Long, _
    ByVal top As Long, _
    ByVal width As Long, _
    ByVal height As Long _
)
    Dim control As Object

    Set control = designer.Controls.Add("Forms.Label.1", name, True)
    control.Caption = caption
    control.Left = left
    control.Top = top
    control.Width = width
    control.Height = height
    control.Font.Name = FORM_FONT_NAME
    control.Font.Size = FORM_LABEL_FONT_SIZE
End Sub

Private Sub AddCombo( _
    ByVal designer As Object, _
    ByVal name As String, _
    ByVal left As Long, _
    ByVal top As Long, _
    ByVal width As Long, _
    ByVal height As Long _
)
    Dim control As Object

    Set control = designer.Controls.Add("Forms.ComboBox.1", name, True)
    control.Left = left
    control.Top = top
    control.Width = width
    control.Height = height
    control.Style = 2
    control.ListRows = FORM_DROPDOWN_VISIBLE_ROWS
    control.MatchEntry = 1
    control.Font.Name = FORM_FONT_NAME
    control.Font.Size = FORM_INPUT_FONT_SIZE
End Sub

Private Sub AddTextBox( _
    ByVal designer As Object, _
    ByVal name As String, _
    ByVal left As Long, _
    ByVal top As Long, _
    ByVal width As Long, _
    ByVal height As Long _
)
    Dim control As Object

    Set control = designer.Controls.Add("Forms.TextBox.1", name, True)
    control.Left = left
    control.Top = top
    control.Width = width
    control.Height = height
    control.Font.Name = FORM_FONT_NAME
    control.Font.Size = FORM_INPUT_FONT_SIZE
End Sub

Private Sub AddListBox( _
    ByVal designer As Object, _
    ByVal name As String, _
    ByVal left As Long, _
    ByVal top As Long, _
    ByVal width As Long, _
    ByVal height As Long _
)
    Dim control As Object

    Set control = designer.Controls.Add("Forms.ListBox.1", name, True)
    control.Left = left
    control.Top = top
    control.Width = width
    control.Height = height
    control.Font.Name = FORM_FONT_NAME
    control.Font.Size = FORM_INPUT_FONT_SIZE
End Sub

Private Sub AddCommandButton( _
    ByVal designer As Object, _
    ByVal name As String, _
    ByVal caption As String, _
    ByVal left As Long, _
    ByVal top As Long, _
    ByVal width As Long, _
    ByVal height As Long _
)
    Dim control As Object

    Set control = designer.Controls.Add("Forms.CommandButton.1", name, True)
    control.Caption = caption
    control.Left = left
    control.Top = top
    control.Width = width
    control.Height = height
    control.Font.Name = FORM_FONT_NAME
    control.Font.Size = FORM_BUTTON_FONT_SIZE
End Sub

Private Sub InstallDatabaseDoubleClickHandler()
    Dim ws As Worksheet
    Dim codeModule As Object
    Dim startLine As Long
    Dim lineCount As Long

    Set ws = ThisWorkbook.Worksheets(DATABASE_SHEET_NAME)
    Set codeModule = ThisWorkbook.VBProject.VBComponents(ws.CodeName).CodeModule

    On Error Resume Next
    startLine = codeModule.ProcStartLine("Worksheet_BeforeDoubleClick", 0)
    If Err.Number = 0 And startLine > 0 Then
        lineCount = codeModule.ProcCountLines("Worksheet_BeforeDoubleClick", 0)
        codeModule.DeleteLines startLine, lineCount
    End If
    Err.Clear
    On Error GoTo 0

    codeModule.AddFromString _
        "Private Sub Worksheet_BeforeDoubleClick(ByVal Target As Range, Cancel As Boolean)" & vbCrLf & _
        "    If IsPrintingRecipeBuilderCellV2(Target) Then" & vbCrLf & _
        "        Cancel = True" & vbCrLf & _
        "        OpenPrintingRecipeBuilderV2 Target" & vbCrLf & _
        "    ElseIf IsExtrusionRecipeBuilderCellV2(Target) Then" & vbCrLf & _
        "        Cancel = True" & vbCrLf & _
        "        OpenExtrusionRecipeBuilderV2 Target" & vbCrLf & _
        "    End If" & vbCrLf & _
        "End Sub"
End Sub

Private Function ExtrusionRecipeBuilderFormCode() As String
    Dim code As String

    AppendFormCodeLine code, "Option Explicit"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private mTargetCell As Range"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Public Property Set TargetCell(ByVal cell As Range)"
    AppendFormCodeLine code, "    Set mTargetCell = cell"
    AppendFormCodeLine code, "End Property"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub UserForm_Initialize()"
    AppendFormCodeLine code, "    txtPreview.Locked = True"
    AppendFormCodeLine code, "    LoadCategories"
    AppendFormCodeLine code, "    UpdatePreview"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub cboCategory_Change()"
    AppendFormCodeLine code, "    LoadProducers"
    AppendFormCodeLine code, "    UpdatePreview"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub cboProducer_Change()"
    AppendFormCodeLine code, "    LoadGrades"
    AppendFormCodeLine code, "    UpdatePreview"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub cboGrade_Change()"
    AppendFormCodeLine code, "    UpdatePreview"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub txtPercent_Change()"
    AppendFormCodeLine code, "    UpdatePreview"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub cmdInsert_Click()"
    AppendFormCodeLine code, "    Dim message As String"
    AppendFormCodeLine code, "    Dim recipeText As String"
    AppendFormCodeLine code, "    If mTargetCell Is Nothing Then"
    AppendFormCodeLine code, "        MsgBox ""No target cell is selected."", vbExclamation, ""Recipe Builder"""
    AppendFormCodeLine code, "        Exit Sub"
    AppendFormCodeLine code, "    End If"
    AppendFormCodeLine code, "    If Not FormIsValid(message) Then"
    AppendFormCodeLine code, "        MsgBox message, vbExclamation, ""Recipe Builder"""
    AppendFormCodeLine code, "        Exit Sub"
    AppendFormCodeLine code, "    End If"
    AppendFormCodeLine code, "    recipeText = BuildRecipeText()"
    AppendFormCodeLine code, "    mTargetCell.Value = recipeText"
    AppendFormCodeLine code, "    Unload Me"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub cmdCancel_Click()"
    AppendFormCodeLine code, "    Unload Me"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub LoadCategories()"
    AppendFormCodeLine code, "    Dim ws As Worksheet"
    AppendFormCodeLine code, "    Dim lastRow As Long"
    AppendFormCodeLine code, "    Dim rowIndex As Long"
    AppendFormCodeLine code, "    Set ws = ThisWorkbook.Worksheets(""RecipeCatalogExtrusion"")"
    AppendFormCodeLine code, "    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row"
    AppendFormCodeLine code, "    cboCategory.Clear"
    AppendFormCodeLine code, "    cboProducer.Clear"
    AppendFormCodeLine code, "    cboGrade.Clear"
    AppendFormCodeLine code, "    For rowIndex = 2 To lastRow"
    AppendFormCodeLine code, "        AddUnique cboCategory, CStr(ws.Cells(rowIndex, 1).Value)"
    AppendFormCodeLine code, "    Next rowIndex"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub LoadProducers()"
    AppendFormCodeLine code, "    Dim ws As Worksheet"
    AppendFormCodeLine code, "    Dim lastRow As Long"
    AppendFormCodeLine code, "    Dim rowIndex As Long"
    AppendFormCodeLine code, "    Set ws = ThisWorkbook.Worksheets(""RecipeCatalogExtrusion"")"
    AppendFormCodeLine code, "    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row"
    AppendFormCodeLine code, "    cboProducer.Clear"
    AppendFormCodeLine code, "    cboGrade.Clear"
    AppendFormCodeLine code, "    For rowIndex = 2 To lastRow"
    AppendFormCodeLine code, "        If CStr(ws.Cells(rowIndex, 1).Value) = cboCategory.Value Then"
    AppendFormCodeLine code, "            AddUnique cboProducer, CStr(ws.Cells(rowIndex, 2).Value)"
    AppendFormCodeLine code, "        End If"
    AppendFormCodeLine code, "    Next rowIndex"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub LoadGrades()"
    AppendFormCodeLine code, "    Dim ws As Worksheet"
    AppendFormCodeLine code, "    Dim lastRow As Long"
    AppendFormCodeLine code, "    Dim rowIndex As Long"
    AppendFormCodeLine code, "    Set ws = ThisWorkbook.Worksheets(""RecipeCatalogExtrusion"")"
    AppendFormCodeLine code, "    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row"
    AppendFormCodeLine code, "    cboGrade.Clear"
    AppendFormCodeLine code, "    For rowIndex = 2 To lastRow"
    AppendFormCodeLine code, "        If CStr(ws.Cells(rowIndex, 1).Value) = cboCategory.Value And CStr(ws.Cells(rowIndex, 2).Value) = cboProducer.Value Then"
    AppendFormCodeLine code, "            AddUnique cboGrade, CStr(ws.Cells(rowIndex, 3).Value)"
    AppendFormCodeLine code, "        End If"
    AppendFormCodeLine code, "    Next rowIndex"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub AddUnique(ByVal combo As Object, ByVal value As String)"
    AppendFormCodeLine code, "    Dim index As Long"
    AppendFormCodeLine code, "    value = Trim$(value)"
    AppendFormCodeLine code, "    If Len(value) = 0 Then Exit Sub"
    AppendFormCodeLine code, "    For index = 0 To combo.ListCount - 1"
    AppendFormCodeLine code, "        If combo.List(index) = value Then Exit Sub"
    AppendFormCodeLine code, "    Next index"
    AppendFormCodeLine code, "    combo.AddItem value"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub UpdatePreview()"
    AppendFormCodeLine code, "    txtPreview.Value = BuildRecipeText()"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function BuildRecipeText() As String"
    AppendFormCodeLine code, "    BuildRecipeText = BuildMaterialText() & "" | "" & NormalizePercent(txtPercent.Value)"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function BuildMaterialText() As String"
    AppendFormCodeLine code, "    Dim materialText As String"
    AppendFormCodeLine code, "    materialText = Trim$(cboCategory.Value)"
    AppendFormCodeLine code, "    If Not IsOmittedCatalogValue(cboProducer.Value) Then materialText = materialText & "" "" & Trim$(cboProducer.Value)"
    AppendFormCodeLine code, "    If Not IsOmittedCatalogValue(cboGrade.Value) Then materialText = materialText & "" "" & Trim$(cboGrade.Value)"
    AppendFormCodeLine code, "    BuildMaterialText = NormalizeSpaces(materialText)"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function IsOmittedCatalogValue(ByVal value As String) As Boolean"
    AppendFormCodeLine code, "    IsOmittedCatalogValue = (UCase$(Trim$(value)) = ""N/A"")"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function NormalizeSpaces(ByVal value As String) As String"
    AppendFormCodeLine code, "    value = Trim$(value)"
    AppendFormCodeLine code, "    Do While InStr(value, ""  "") > 0"
    AppendFormCodeLine code, "        value = Replace(value, ""  "", "" "")"
    AppendFormCodeLine code, "    Loop"
    AppendFormCodeLine code, "    NormalizeSpaces = value"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function NormalizePercent(ByVal value As String) As String"
    AppendFormCodeLine code, "    value = Trim$(value)"
    AppendFormCodeLine code, "    value = Replace(value, "","", ""."")"
    AppendFormCodeLine code, "    value = Replace(value, "" "", """")"
    AppendFormCodeLine code, "    If Len(value) > 0 And Right$(value, 1) <> ""%"" Then value = value & ""%"""
    AppendFormCodeLine code, "    NormalizePercent = value"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function FormIsValid(ByRef message As String) As Boolean"
    AppendFormCodeLine code, "    Dim percentNumber As String"
    AppendFormCodeLine code, "    If Len(Trim$(cboCategory.Value)) = 0 Then message = ""Choose a material category."": Exit Function"
    AppendFormCodeLine code, "    If Len(Trim$(cboProducer.Value)) = 0 Then message = ""Choose a producer."": Exit Function"
    AppendFormCodeLine code, "    If Len(Trim$(cboGrade.Value)) = 0 Then message = ""Choose a grade/code."": Exit Function"
    AppendFormCodeLine code, "    percentNumber = Replace(NormalizePercent(txtPercent.Value), ""%"", """")"
    AppendFormCodeLine code, "    If Len(percentNumber) = 0 Or Not IsNumeric(percentNumber) Then message = ""Enter a valid percentage."": Exit Function"
    AppendFormCodeLine code, "    If CDbl(percentNumber) <= 0 Then message = ""Percentage must be greater than 0."": Exit Function"
    AppendFormCodeLine code, "    message = """""
    AppendFormCodeLine code, "    FormIsValid = True"
    AppendFormCodeLine code, "End Function"

    ExtrusionRecipeBuilderFormCode = code
End Function

Private Function PrintingRecipeBuilderFormCode() As String
    Dim code As String

    AppendFormCodeLine code, "Option Explicit"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private mTargetCell As Range"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Public Property Set TargetCell(ByVal cell As Range)"
    AppendFormCodeLine code, "    Set mTargetCell = cell"
    AppendFormCodeLine code, "End Property"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub UserForm_Initialize()"
    AppendFormCodeLine code, "    txtPreview.Locked = True"
    AppendFormCodeLine code, "    LoadInkMatches """""
    AppendFormCodeLine code, "    LoadAniloxValues"
    AppendFormCodeLine code, "    UpdatePreview"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub txtInkSearch_Change()"
    AppendFormCodeLine code, "    LoadInkMatches txtInkSearch.Value"
    AppendFormCodeLine code, "    UpdatePreview"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub lstInk_Change()"
    AppendFormCodeLine code, "    UpdatePreview"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub cboAnilox_Change()"
    AppendFormCodeLine code, "    UpdatePreview"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub cmdInsert_Click()"
    AppendFormCodeLine code, "    Dim message As String"
    AppendFormCodeLine code, "    If mTargetCell Is Nothing Then"
    AppendFormCodeLine code, "        MsgBox ""No target cell is selected."", vbExclamation, ""Printing Recipe Builder"""
    AppendFormCodeLine code, "        Exit Sub"
    AppendFormCodeLine code, "    End If"
    AppendFormCodeLine code, "    If Not FormIsValid(message) Then"
    AppendFormCodeLine code, "        MsgBox message, vbExclamation, ""Printing Recipe Builder"""
    AppendFormCodeLine code, "        Exit Sub"
    AppendFormCodeLine code, "    End If"
    AppendFormCodeLine code, "    mTargetCell.Value = BuildPrintingText()"
    AppendFormCodeLine code, "    Unload Me"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub cmdCancel_Click()"
    AppendFormCodeLine code, "    Unload Me"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub LoadInkMatches(ByVal filterText As String)"
    AppendFormCodeLine code, "    Dim ws As Worksheet"
    AppendFormCodeLine code, "    Dim lastRow As Long"
    AppendFormCodeLine code, "    Dim rowIndex As Long"
    AppendFormCodeLine code, "    Dim inkValue As String"
    AppendFormCodeLine code, "    Dim searchableText As String"
    AppendFormCodeLine code, "    filterText = UCase$(Trim$(filterText))"
    AppendFormCodeLine code, "    lstInk.Clear"
    AppendFormCodeLine code, "    Set ws = ThisWorkbook.Worksheets(""RecipeCatalogPrinting"")"
    AppendFormCodeLine code, "    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row"
    AppendFormCodeLine code, "    For rowIndex = 2 To lastRow"
    AppendFormCodeLine code, "        If UCase$(Trim$(CStr(ws.Cells(rowIndex, 1).Value))) = ""INK"" Then"
    AppendFormCodeLine code, "            inkValue = Trim$(CStr(ws.Cells(rowIndex, 2).Value))"
    AppendFormCodeLine code, "            searchableText = UCase$(inkValue & "" "" & CStr(ws.Cells(rowIndex, 3).Value))"
    AppendFormCodeLine code, "            If Len(filterText) = 0 Or InStr(1, searchableText, filterText, vbTextCompare) > 0 Then"
    AppendFormCodeLine code, "                AddUniqueList lstInk, inkValue"
    AppendFormCodeLine code, "            End If"
    AppendFormCodeLine code, "        End If"
    AppendFormCodeLine code, "    Next rowIndex"
    AppendFormCodeLine code, "    If lstInk.ListCount = 1 Then lstInk.ListIndex = 0"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub LoadAniloxValues()"
    AppendFormCodeLine code, "    LoadCatalogValues ""Anilox"", cboAnilox"
    AppendFormCodeLine code, "    cboAnilox.AddItem """", 0"
    AppendFormCodeLine code, "    cboAnilox.ListIndex = 0"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub LoadCatalogValues(ByVal valueType As String, ByVal combo As Object)"
    AppendFormCodeLine code, "    Dim ws As Worksheet"
    AppendFormCodeLine code, "    Dim lastRow As Long"
    AppendFormCodeLine code, "    Dim rowIndex As Long"
    AppendFormCodeLine code, "    combo.Clear"
    AppendFormCodeLine code, "    Set ws = ThisWorkbook.Worksheets(""RecipeCatalogPrinting"")"
    AppendFormCodeLine code, "    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row"
    AppendFormCodeLine code, "    For rowIndex = 2 To lastRow"
    AppendFormCodeLine code, "        If UCase$(Trim$(CStr(ws.Cells(rowIndex, 1).Value))) = UCase$(valueType) Then"
    AppendFormCodeLine code, "            AddUnique combo, CStr(ws.Cells(rowIndex, 2).Value)"
    AppendFormCodeLine code, "        End If"
    AppendFormCodeLine code, "    Next rowIndex"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub AddUnique(ByVal combo As Object, ByVal value As String)"
    AppendFormCodeLine code, "    Dim index As Long"
    AppendFormCodeLine code, "    value = Trim$(value)"
    AppendFormCodeLine code, "    If Len(value) = 0 Then Exit Sub"
    AppendFormCodeLine code, "    For index = 0 To combo.ListCount - 1"
    AppendFormCodeLine code, "        If combo.List(index) = value Then Exit Sub"
    AppendFormCodeLine code, "    Next index"
    AppendFormCodeLine code, "    combo.AddItem value"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub AddUniqueList(ByVal listBox As Object, ByVal value As String)"
    AppendFormCodeLine code, "    Dim index As Long"
    AppendFormCodeLine code, "    value = Trim$(value)"
    AppendFormCodeLine code, "    If Len(value) = 0 Then Exit Sub"
    AppendFormCodeLine code, "    For index = 0 To listBox.ListCount - 1"
    AppendFormCodeLine code, "        If listBox.List(index) = value Then Exit Sub"
    AppendFormCodeLine code, "    Next index"
    AppendFormCodeLine code, "    listBox.AddItem value"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub UpdatePreview()"
    AppendFormCodeLine code, "    txtPreview.Value = BuildPrintingText()"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function BuildPrintingText() As String"
    AppendFormCodeLine code, "    Dim aniloxText As String"
    AppendFormCodeLine code, "    aniloxText = NormalizeAnilox(cboAnilox.Value)"
    AppendFormCodeLine code, "    If Len(aniloxText) = 0 Then"
    AppendFormCodeLine code, "        BuildPrintingText = NormalizeSpaces(SelectedInkValue())"
    AppendFormCodeLine code, "    Else"
    AppendFormCodeLine code, "        BuildPrintingText = NormalizeSpaces(SelectedInkValue()) & ""/"" & aniloxText"
    AppendFormCodeLine code, "    End If"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function SelectedInkValue() As String"
    AppendFormCodeLine code, "    If lstInk.ListIndex < 0 Then"
    AppendFormCodeLine code, "        SelectedInkValue = """""
    AppendFormCodeLine code, "    Else"
    AppendFormCodeLine code, "        SelectedInkValue = CStr(lstInk.List(lstInk.ListIndex))"
    AppendFormCodeLine code, "    End If"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function NormalizeAnilox(ByVal value As String) As String"
    AppendFormCodeLine code, "    NormalizeAnilox = Replace(Trim$(value), "" "", """")"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function NormalizeSpaces(ByVal value As String) As String"
    AppendFormCodeLine code, "    value = Trim$(value)"
    AppendFormCodeLine code, "    Do While InStr(value, ""  "") > 0"
    AppendFormCodeLine code, "        value = Replace(value, ""  "", "" "")"
    AppendFormCodeLine code, "    Loop"
    AppendFormCodeLine code, "    NormalizeSpaces = value"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function FormIsValid(ByRef message As String) As Boolean"
    AppendFormCodeLine code, "    Dim aniloxText As String"
    AppendFormCodeLine code, "    If Len(SelectedInkValue()) = 0 Then message = ""Choose an ink/color from the matching list."": Exit Function"
    AppendFormCodeLine code, "    aniloxText = NormalizeAnilox(cboAnilox.Value)"
    AppendFormCodeLine code, "    If Len(aniloxText) = 0 Then message = """": FormIsValid = True: Exit Function"
    AppendFormCodeLine code, "    If Not IsNumeric(aniloxText) Then message = ""Choose a numeric anilox roller value."": Exit Function"
    AppendFormCodeLine code, "    If CDbl(aniloxText) <= 0 Then message = ""Anilox roller value must be greater than 0."": Exit Function"
    AppendFormCodeLine code, "    message = """""
    AppendFormCodeLine code, "    FormIsValid = True"
    AppendFormCodeLine code, "End Function"

    PrintingRecipeBuilderFormCode = code
End Function

Private Sub AppendFormCodeLine(ByRef code As String, ByVal line As String)
    code = code & line & vbCrLf
End Sub
