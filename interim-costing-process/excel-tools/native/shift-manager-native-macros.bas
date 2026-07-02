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

Private Function DatabaseWorksheetChangeCode() As String
    ' Generated sheet code watches Me.Range("C2,D2,F2").
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
