Attribute VB_Name = "ProductionActualsPrototypeInstaller"
Option Explicit

' Production Actuals controlled-entry prototype.
'
' Import this module into a test workbook, then run:
' InstallProductionActualsPrototype
'
' The installer creates:
' - a ProductionActualsPrototype worksheet with locked Actuals cells
' - a UserForm for gross/tare/roll/timing entry
' - a worksheet double-click handler that opens the form
'
' Existing structured cell values are loaded into the form when opened.
' Excel may block the UserForm/event installation unless this setting is enabled:
' File > Options > Trust Center > Trust Center Settings > Macro Settings >
' Trust access to the VBA project object model.

Private Const PROTOTYPE_SHEET_NAME As String = "ProductionActualsPrototype"
Private Const FORM_NAME As String = "frmProductionActualsPrototype"
Private Const ACTUALS_FIRST_ROW As Long = 2
Private Const ACTUALS_LAST_ROW As Long = 1000
Private Const ACTUALS_COLUMN As String = "D"
Private Const SHEET_PASSWORD As String = "actuals-prototype"
Private Const FORM_FONT_NAME As String = "Calibri"
Private Const FORM_LABEL_FONT_SIZE As Long = 12
Private Const FORM_INPUT_FONT_SIZE As Long = 13
Private Const FORM_BUTTON_FONT_SIZE As Long = 12

Public Sub InstallProductionActualsPrototype()
    Dim ws As Worksheet
    Set ws = EnsurePrototypeSheet()

    SetupPrototypeSheet ws
    ApplyProductionActualsPrototypeProtection

    If Not TryInstallFormAndEvent() Then
        MsgBox _
            "The prototype sheet was created, but Excel blocked automatic form installation." & vbCrLf & vbCrLf & _
            "Enable this setting and run InstallProductionActualsPrototype again:" & vbCrLf & _
            "File > Options > Trust Center > Trust Center Settings > Macro Settings >" & vbCrLf & _
            "Trust access to the VBA project object model.", _
            vbExclamation, _
            "Production Actuals Prototype"
        Exit Sub
    End If

    MsgBox _
        "Production Actuals prototype installed." & vbCrLf & _
        "Double-click a cell in " & PROTOTYPE_SHEET_NAME & "!" & ACTUALS_COLUMN & _
        ACTUALS_FIRST_ROW & ":" & ACTUALS_COLUMN & ACTUALS_LAST_ROW & _
        " to open the form.", _
        vbInformation, _
        "Production Actuals Prototype"
End Sub

Public Sub ApplyProductionActualsPrototypeProtection()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(PROTOTYPE_SHEET_NAME)

    On Error Resume Next
    ws.Unprotect Password:=SHEET_PASSWORD
    On Error GoTo 0

    ws.Cells.Locked = False
    ws.Range(ACTUALS_COLUMN & ACTUALS_FIRST_ROW & ":" & ACTUALS_COLUMN & ACTUALS_LAST_ROW).Locked = True
    ws.EnableSelection = xlNoRestrictions
    ws.Protect Password:=SHEET_PASSWORD, UserInterfaceOnly:=True
End Sub

Public Function IsProductionActualsPrototypeCell(ByVal target As Range) As Boolean
    If target Is Nothing Then Exit Function
    If target.Worksheet.Name <> PROTOTYPE_SHEET_NAME Then Exit Function
    If target.CountLarge <> 1 Then Exit Function

    IsProductionActualsPrototypeCell = Not Intersect( _
        target, _
        target.Worksheet.Range(ACTUALS_COLUMN & ACTUALS_FIRST_ROW & ":" & ACTUALS_COLUMN & ACTUALS_LAST_ROW) _
    ) Is Nothing
End Function

Public Sub OpenProductionActualsPrototypeForm(ByVal target As Range)
    Dim form As Object

    If Not IsProductionActualsPrototypeCell(target) Then Exit Sub

    Set form = VBA.UserForms.Add(FORM_NAME)
    CallByName form, "TargetCell", VbSet, target
    form.Show
End Sub

Private Function EnsurePrototypeSheet() As Worksheet
    On Error Resume Next
    Set EnsurePrototypeSheet = ThisWorkbook.Worksheets(PROTOTYPE_SHEET_NAME)
    On Error GoTo 0

    If EnsurePrototypeSheet Is Nothing Then
        Set EnsurePrototypeSheet = ThisWorkbook.Worksheets.Add( _
            After:=ThisWorkbook.Worksheets(ThisWorkbook.Worksheets.Count) _
        )
        EnsurePrototypeSheet.Name = PROTOTYPE_SHEET_NAME
    End If
End Function

Private Sub SetupPrototypeSheet(ByVal ws As Worksheet)
    ws.Range("A1:D1").Value = Array("Order", "Customer", "Product", "Actuals")

    If Len(Trim$(CStr(ws.Range("A2").Value))) = 0 Then
        ws.Range("A2:D2").Value = Array( _
            "25278", _
            "Sample customer", _
            "Extrusion film", _
            "v1; gross=1050; tare=5; rolls=10; net=1000; start=2026-07-01 08:15; stop=2026-07-01 10:40" _
        )
    End If

    If Len(Trim$(CStr(ws.Range("A3").Value))) = 0 Then
        ws.Range("A3:C3").Value = Array("25279", "Blank test row", "Extrusion film")
    End If

    ws.Rows(1).Font.Bold = True
    ws.Range("A:D").VerticalAlignment = xlTop
    ws.Columns("A:C").ColumnWidth = 20
    ws.Columns("D").ColumnWidth = 95
    ws.Range("D:D").WrapText = True
    ws.Range("D" & ACTUALS_FIRST_ROW & ":D" & ACTUALS_LAST_ROW).Interior.Color = RGB(242, 246, 252)
End Sub

Private Function TryInstallFormAndEvent() As Boolean
    On Error GoTo InstallFailed

    InstallProductionActualsPrototypeForm
    InstallPrototypeDoubleClickHandler
    TryInstallFormAndEvent = True
    Exit Function

InstallFailed:
    TryInstallFormAndEvent = False
End Function

Private Sub InstallProductionActualsPrototypeForm()
    Dim project As Object
    Dim components As Object
    Dim formComponent As Object
    Dim designer As Object

    Set project = ThisWorkbook.VBProject
    Set components = project.VBComponents

    RemoveComponentIfExists components, FORM_NAME

    Set formComponent = components.Add(3)
    formComponent.Properties("Name").Value = FORM_NAME
    formComponent.Properties("Caption").Value = "Production Actuals"
    formComponent.Properties("Width").Value = 560
    formComponent.Properties("Height").Value = 390

    Set designer = formComponent.Designer

    AddLabel designer, "lblGross", "Gross Weight (kg)", 24, 24, 155, 22
    AddTextBox designer, "txtGross", 195, 20, 145, 25

    AddLabel designer, "lblTare", "Tare / Core (kg)", 24, 66, 155, 22
    AddTextBox designer, "txtTare", 195, 62, 145, 25

    AddLabel designer, "lblRolls", "Number of Rolls", 24, 108, 155, 22
    AddTextBox designer, "txtRolls", 195, 104, 145, 25

    AddLabel designer, "lblNet", "Net Weight (kg)", 24, 150, 155, 22
    AddTextBox designer, "txtNet", 195, 146, 145, 25

    AddLabel designer, "lblStart", "Start Time", 24, 202, 155, 22
    AddTextBox designer, "txtStart", 195, 198, 210, 25

    AddLabel designer, "lblStop", "Stop Time", 24, 244, 155, 22
    AddTextBox designer, "txtStop", 195, 240, 210, 25

    AddLabel designer, "lblPreview", "Structured cell value", 24, 292, 155, 22
    AddTextBox designer, "txtPreview", 195, 288, 320, 42

    AddCommandButton designer, "cmdSave", "Save", 340, 340, 82, 30
    AddCommandButton designer, "cmdCancel", "Cancel", 432, 340, 82, 30

    formComponent.CodeModule.AddFromString ProductionActualsFormCode()
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

Private Sub InstallPrototypeDoubleClickHandler()
    Dim ws As Worksheet
    Dim codeModule As Object
    Dim startLine As Long
    Dim lineCount As Long

    Set ws = ThisWorkbook.Worksheets(PROTOTYPE_SHEET_NAME)
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
        "    If IsProductionActualsPrototypeCell(Target) Then" & vbCrLf & _
        "        Cancel = True" & vbCrLf & _
        "        OpenProductionActualsPrototypeForm Target" & vbCrLf & _
        "    End If" & vbCrLf & _
        "End Sub"
End Sub

Private Function ProductionActualsFormCode() As String
    Dim code As String

    AppendFormCodeLine code, "Option Explicit"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private mTargetCell As Range"
    AppendFormCodeLine code, "Private mLoading As Boolean"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Public Property Set TargetCell(ByVal cell As Range)"
    AppendFormCodeLine code, "    Set mTargetCell = cell"
    AppendFormCodeLine code, "    LoadExistingValue"
    AppendFormCodeLine code, "End Property"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub UserForm_Initialize()"
    AppendFormCodeLine code, "    txtNet.Locked = True"
    AppendFormCodeLine code, "    txtPreview.Locked = True"
    AppendFormCodeLine code, "    UpdateCalculatedFields"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub txtGross_Change()"
    AppendFormCodeLine code, "    If Not mLoading Then UpdateCalculatedFields"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub txtTare_Change()"
    AppendFormCodeLine code, "    If Not mLoading Then UpdateCalculatedFields"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub txtRolls_Change()"
    AppendFormCodeLine code, "    If Not mLoading Then UpdateCalculatedFields"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub txtStart_Change()"
    AppendFormCodeLine code, "    If Not mLoading Then UpdateCalculatedFields"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub txtStop_Change()"
    AppendFormCodeLine code, "    If Not mLoading Then UpdateCalculatedFields"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub cmdSave_Click()"
    AppendFormCodeLine code, "    Dim message As String"
    AppendFormCodeLine code, "    If mTargetCell Is Nothing Then"
    AppendFormCodeLine code, "        MsgBox ""No target cell is selected."", vbExclamation, ""Production Actuals"""
    AppendFormCodeLine code, "        Exit Sub"
    AppendFormCodeLine code, "    End If"
    AppendFormCodeLine code, "    If Not FormIsValid(message) Then"
    AppendFormCodeLine code, "        MsgBox message, vbExclamation, ""Production Actuals"""
    AppendFormCodeLine code, "        Exit Sub"
    AppendFormCodeLine code, "    End If"
    AppendFormCodeLine code, "    mTargetCell.Value = BuildStructuredValue()"
    AppendFormCodeLine code, "    Unload Me"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub cmdCancel_Click()"
    AppendFormCodeLine code, "    Unload Me"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub LoadExistingValue()"
    AppendFormCodeLine code, "    Dim rawValue As String"
    AppendFormCodeLine code, "    rawValue = Trim$(CStr(mTargetCell.Value))"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "    mLoading = True"
    AppendFormCodeLine code, "    ClearFields"
    AppendFormCodeLine code, "    If Len(rawValue) > 0 Then"
    AppendFormCodeLine code, "        If Left$(LCase$(rawValue), 2) = ""v1"" Then"
    AppendFormCodeLine code, "            LoadKeyValueActuals rawValue"
    AppendFormCodeLine code, "        ElseIf InStr(rawValue, ""|"") > 0 Then"
    AppendFormCodeLine code, "            LoadLegacyPipeActuals rawValue"
    AppendFormCodeLine code, "        End If"
    AppendFormCodeLine code, "    End If"
    AppendFormCodeLine code, "    mLoading = False"
    AppendFormCodeLine code, "    UpdateCalculatedFields"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub ClearFields()"
    AppendFormCodeLine code, "    txtGross.Value = """""
    AppendFormCodeLine code, "    txtTare.Value = """""
    AppendFormCodeLine code, "    txtRolls.Value = """""
    AppendFormCodeLine code, "    txtNet.Value = """""
    AppendFormCodeLine code, "    txtStart.Value = """""
    AppendFormCodeLine code, "    txtStop.Value = """""
    AppendFormCodeLine code, "    txtPreview.Value = """""
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub LoadKeyValueActuals(ByVal rawValue As String)"
    AppendFormCodeLine code, "    Dim parts As Variant"
    AppendFormCodeLine code, "    Dim index As Long"
    AppendFormCodeLine code, "    Dim part As String"
    AppendFormCodeLine code, "    Dim separatorPosition As Long"
    AppendFormCodeLine code, "    Dim key As String"
    AppendFormCodeLine code, "    Dim value As String"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "    parts = Split(rawValue, "";"")"
    AppendFormCodeLine code, "    For index = LBound(parts) To UBound(parts)"
    AppendFormCodeLine code, "        part = Trim$(CStr(parts(index)))"
    AppendFormCodeLine code, "        separatorPosition = InStr(part, ""="")"
    AppendFormCodeLine code, "        If separatorPosition > 0 Then"
    AppendFormCodeLine code, "            key = LCase$(Trim$(Left$(part, separatorPosition - 1)))"
    AppendFormCodeLine code, "            value = Trim$(Mid$(part, separatorPosition + 1))"
    AppendFormCodeLine code, "            Select Case key"
    AppendFormCodeLine code, "                Case ""gross"""
    AppendFormCodeLine code, "                    txtGross.Value = value"
    AppendFormCodeLine code, "                Case ""tare"""
    AppendFormCodeLine code, "                    txtTare.Value = value"
    AppendFormCodeLine code, "                Case ""rolls"""
    AppendFormCodeLine code, "                    txtRolls.Value = value"
    AppendFormCodeLine code, "                Case ""start"""
    AppendFormCodeLine code, "                    txtStart.Value = value"
    AppendFormCodeLine code, "                Case ""stop"""
    AppendFormCodeLine code, "                    txtStop.Value = value"
    AppendFormCodeLine code, "            End Select"
    AppendFormCodeLine code, "        End If"
    AppendFormCodeLine code, "    Next index"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub LoadLegacyPipeActuals(ByVal rawValue As String)"
    AppendFormCodeLine code, "    Dim parts As Variant"
    AppendFormCodeLine code, "    parts = Split(rawValue, ""|"")"
    AppendFormCodeLine code, "    If UBound(parts) >= 0 Then txtGross.Value = Trim$(CStr(parts(0)))"
    AppendFormCodeLine code, "    If UBound(parts) >= 2 Then txtTare.Value = Trim$(CStr(parts(2)))"
    AppendFormCodeLine code, "    If UBound(parts) >= 3 Then txtRolls.Value = Trim$(CStr(parts(3)))"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Sub UpdateCalculatedFields()"
    AppendFormCodeLine code, "    Dim gross As Double"
    AppendFormCodeLine code, "    Dim tare As Double"
    AppendFormCodeLine code, "    Dim rolls As Long"
    AppendFormCodeLine code, "    If TryReadGrossTareRolls(gross, tare, rolls) Then"
    AppendFormCodeLine code, "        txtNet.Value = InvariantNumber(gross - (tare * rolls))"
    AppendFormCodeLine code, "    Else"
    AppendFormCodeLine code, "        txtNet.Value = """""
    AppendFormCodeLine code, "    End If"
    AppendFormCodeLine code, "    txtPreview.Value = BuildStructuredValue()"
    AppendFormCodeLine code, "End Sub"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function BuildStructuredValue() As String"
    AppendFormCodeLine code, "    BuildStructuredValue = ""v1; gross="" & NormalizeNumberText(txtGross.Value) & _"
    AppendFormCodeLine code, "        ""; tare="" & NormalizeNumberText(txtTare.Value) & _"
    AppendFormCodeLine code, "        ""; rolls="" & Trim$(txtRolls.Value) & _"
    AppendFormCodeLine code, "        ""; net="" & NormalizeNumberText(txtNet.Value) & _"
    AppendFormCodeLine code, "        ""; start="" & Trim$(txtStart.Value) & _"
    AppendFormCodeLine code, "        ""; stop="" & Trim$(txtStop.Value)"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function FormIsValid(ByRef message As String) As Boolean"
    AppendFormCodeLine code, "    Dim gross As Double"
    AppendFormCodeLine code, "    Dim tare As Double"
    AppendFormCodeLine code, "    Dim rolls As Long"
    AppendFormCodeLine code, "    If Not TryReadGrossTareRolls(gross, tare, rolls) Then"
    AppendFormCodeLine code, "        message = ""Enter valid gross weight, tare weight, and roll count."""
    AppendFormCodeLine code, "        Exit Function"
    AppendFormCodeLine code, "    End If"
    AppendFormCodeLine code, "    If gross < 0 Then message = ""Gross weight cannot be negative."": Exit Function"
    AppendFormCodeLine code, "    If tare < 0 Then message = ""Tare weight cannot be negative."": Exit Function"
    AppendFormCodeLine code, "    If rolls <= 0 Then message = ""Number of rolls must be greater than 0."": Exit Function"
    AppendFormCodeLine code, "    If gross - (tare * rolls) < 0 Then message = ""Net weight cannot be negative."": Exit Function"
    AppendFormCodeLine code, "    If Len(Trim$(txtStart.Value)) = 0 Then message = ""Enter a start time."": Exit Function"
    AppendFormCodeLine code, "    If Len(Trim$(txtStop.Value)) = 0 Then message = ""Enter a stop time."": Exit Function"
    AppendFormCodeLine code, "    message = """""
    AppendFormCodeLine code, "    FormIsValid = True"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function TryReadGrossTareRolls(ByRef gross As Double, ByRef tare As Double, ByRef rolls As Long) As Boolean"
    AppendFormCodeLine code, "    Dim grossOk As Boolean"
    AppendFormCodeLine code, "    Dim tareOk As Boolean"
    AppendFormCodeLine code, "    grossOk = TryReadDecimal(txtGross.Value, gross)"
    AppendFormCodeLine code, "    tareOk = TryReadDecimal(txtTare.Value, tare)"
    AppendFormCodeLine code, "    If Not IsNumeric(Trim$(txtRolls.Value)) Then Exit Function"
    AppendFormCodeLine code, "    If InStr(Trim$(txtRolls.Value), ""."") > 0 Or InStr(Trim$(txtRolls.Value), "","") > 0 Then Exit Function"
    AppendFormCodeLine code, "    rolls = CLng(Trim$(txtRolls.Value))"
    AppendFormCodeLine code, "    TryReadGrossTareRolls = grossOk And tareOk"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function TryReadDecimal(ByVal rawValue As String, ByRef numberValue As Double) As Boolean"
    AppendFormCodeLine code, "    Dim value As String"
    AppendFormCodeLine code, "    Dim decimalSeparator As String"
    AppendFormCodeLine code, "    value = NormalizeNumberText(rawValue)"
    AppendFormCodeLine code, "    If Len(value) = 0 Then Exit Function"
    AppendFormCodeLine code, "    decimalSeparator = Application.International(xlDecimalSeparator)"
    AppendFormCodeLine code, "    If IsNumeric(Replace(value, ""."", decimalSeparator)) Then"
    AppendFormCodeLine code, "        numberValue = CDbl(Replace(value, ""."", decimalSeparator))"
    AppendFormCodeLine code, "        TryReadDecimal = True"
    AppendFormCodeLine code, "    End If"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function NormalizeNumberText(ByVal rawValue As String) As String"
    AppendFormCodeLine code, "    NormalizeNumberText = Replace(Trim$(rawValue), "","", ""."")"
    AppendFormCodeLine code, "End Function"
    AppendFormCodeLine code, ""
    AppendFormCodeLine code, "Private Function InvariantNumber(ByVal numberValue As Double) As String"
    AppendFormCodeLine code, "    Dim formatted As String"
    AppendFormCodeLine code, "    formatted = Format$(numberValue, ""0.##"")"
    AppendFormCodeLine code, "    InvariantNumber = Replace(formatted, Application.International(xlDecimalSeparator), ""."")"
    AppendFormCodeLine code, "End Function"

    ProductionActualsFormCode = code
End Function

Private Sub AppendFormCodeLine(ByRef code As String, ByVal line As String)
    code = code & line & vbCrLf
End Sub
