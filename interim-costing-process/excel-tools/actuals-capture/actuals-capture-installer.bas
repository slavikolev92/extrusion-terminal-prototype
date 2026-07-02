Attribute VB_Name = "ActualsCaptureInstaller"
Option Explicit

Private Const DATABASE_SHEET_NAME As String = "Database"
Private Const ENTRY_SHEET_NAME As String = "Actuals Entry"
Private Const REVIEW_SHEET_NAME As String = "Actuals Review"
Private Const VALIDATION_SHEET_NAME As String = "Actuals Validation"
Private Const DATA_SHEET_NAME As String = "ActualsData"
Private Const STATUS_SHEET_NAME As String = "ActualsStatus"
Private Const CONFIG_SHEET_NAME As String = "ActualsConfig"
Private Const LEGACY_PROTECTION_PASSWORD As String = "actuals-v1"

Public Sub InstallActualsCapture()
    EnsureActualsSheets

    If ActualsWorkbookTemplateExists() Then
        SetupActualsData
        SetupActualsStatus
        ApplyActualsProtection
        MsgBox "Actuals Capture macros installed. Existing Actuals workbook template preserved.", vbInformation, "Actuals Capture"
        Exit Sub
    End If

    SetupActualsConfig
    SetupActualsData
    SetupActualsStatus
    SetupActualsEntry
    SetupActualsReview
    SetupActualsValidation
    ApplyActualsProtection
    MsgBox "Actuals Capture installed.", vbInformation, "Actuals Capture"
End Sub

Private Function ActualsWorkbookTemplateExists() As Boolean
    On Error GoTo MissingTemplate

    ActualsWorkbookTemplateExists = _
        Trim$(CStr(ThisWorkbook.Worksheets(CONFIG_SHEET_NAME).Range("F1").Value)) = "Actuals Setup" _
        And Trim$(CStr(ThisWorkbook.Worksheets(ENTRY_SHEET_NAME).Range("D2").Value)) = "Saved active actual cards for loaded order" _
        And Trim$(CStr(ThisWorkbook.Worksheets(DATA_SHEET_NAME).Range("A1").Value)) = "Actual card ID" _
        And Trim$(CStr(ThisWorkbook.Worksheets(STATUS_SHEET_NAME).Range("A1").Value)) = "Production order"
    Exit Function

MissingTemplate:
    ActualsWorkbookTemplateExists = False
End Function

Private Sub EnsureActualsSheets()
    EnsureSheet ENTRY_SHEET_NAME, True
    EnsureSheet REVIEW_SHEET_NAME, True
    EnsureSheet VALIDATION_SHEET_NAME, True
    EnsureSheet DATA_SHEET_NAME, False
    EnsureSheet STATUS_SHEET_NAME, False
    EnsureSheet CONFIG_SHEET_NAME, True
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

Private Sub SetupActualsConfig()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)

    UnprotectActualsSheet ws
    DeleteActualsConfigButtons ws

    ws.Range("A1:D1").Value = Array("WorkbookConfig", "Value", "Notes", "Reserved")
    ws.Range("A2").Value = "FirstIncludedRow"
    ws.Range("C2:D2").Value = Array("This is the cutoff. Rows at and below this Database row are included.", "Example for dummy orders: 5314")
    ws.Range("A3").Value = "FirstIncludedProductionOrder"
    ws.Range("C3:D3").Value = Array("Production order in Database column A at the cutoff row.", "Example for dummy orders: 30000")

    ws.Range("A6:D6").Value = Array("ExplicitInclusions", "RowNumber", "ProductionOrder", "Notes")
    If ConfigExampleRowCanBeWritten(ws) Then
        ws.Range("A7:D7").Value = Array("Example", "", "", "Optional: change Example to Include only for pre-cutoff rows that should be included.")
    End If

    ws.Range("A10:C10").Value = Array("OperationCode", "Operation", "DatabaseFlagColumn")
    ws.Range("A11:C11").Value = Array("PRN", "Printing", "Q")
    ws.Range("A12:C12").Value = Array("EXT", "Extrusion", "R")
    ws.Range("A13:C13").Value = Array("RWS", "Rewinding / Slitting", "S")
    ws.Range("A14:C14").Value = Array("CON", "Confection", "T")

    ws.Range("A17:A22").Value = Application.WorksheetFunction.Transpose(Array("StatusList", "Planned", "In Production", "On Hold", "Completed", "Cancelled"))
    ws.Range("A25:D25").Value = Array("WorkingCalendar", "DayOrDate", "StartTime", "StopTime")
    If Application.WorksheetFunction.CountA(ws.Range("A26:D26")) = 0 Then
        ws.Range("A26:D26").Value = Array("Example", "Monday or 2026-01-01", "08:00", "17:00")
    End If

    ws.Range("F1").Value = "Actuals Setup"
    ws.Range("F2").Value = "Enter the first Database row to include in Actuals V1, or use the button below."
    ws.Range("F3").Value = "For the dummy orders described in testing: row 5314 should pair with production order 30000."
    AddActualsConfigButton ws, "ActualsConfigButtonSetCutoff", "Set cutoff from Database row", "SetActualsCutoffFromPrompt", 5

    StyleActualsConfig ws
    ws.Columns("A:D").AutoFit
    ws.Columns("F:H").AutoFit
End Sub

Private Function ConfigExampleRowCanBeWritten(ByVal ws As Worksheet) As Boolean
    If Application.WorksheetFunction.CountA(ws.Range("A7:D7")) = 0 Then
        ConfigExampleRowCanBeWritten = True
        Exit Function
    End If

    If LCase$(Trim$(CStr(ws.Range("A7").Value))) = "example" Then
        ConfigExampleRowCanBeWritten = True
        Exit Function
    End If

    ConfigExampleRowCanBeWritten = LCase$(Trim$(CStr(ws.Range("A7").Value))) = "include" _
        And Trim$(CStr(ws.Range("B7").Value)) = "" _
        And Trim$(CStr(ws.Range("C7").Value)) = ""
End Function

Private Function FirstIncludedRow() As Long
    FirstIncludedRow = ConfigRowNumber(CStr(ConfigValue("FirstIncludedRow")), "ActualsConfig FirstIncludedRow must be a positive whole Database row number.")
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
            Dim includedRowText As String
            Dim includedProductionOrder As String
            includedRowText = Trim$(CStr(ws.Cells(rowNumber, 2).Value))
            includedProductionOrder = Trim$(CStr(ws.Cells(rowNumber, 3).Value))

            If includedRowText <> "" Or includedProductionOrder <> "" Then
                If includedRowText = "" Or includedProductionOrder = "" Or Not ConfigRowNumberIsValid(includedRowText) Then
                    Err.Raise vbObjectError + 2001, , "Malformed ActualsConfig explicit inclusion at row " & CStr(rowNumber) & ": Include requires RowNumber and ProductionOrder."
                End If

                inclusions(ExplicitInclusionKey(ConfigRowNumber(includedRowText, "Malformed ActualsConfig explicit inclusion at row " & CStr(rowNumber) & ": RowNumber must be a positive whole Database row number."), includedProductionOrder)) = True
            End If
        End If
    Next rowNumber

    Set LoadExplicitInclusions = inclusions
End Function

Private Function ConfigRowNumberIsValid(ByVal rawValue As String) As Boolean
    rawValue = Trim$(rawValue)

    If rawValue = "" Or Not IsNumeric(rawValue) Then
        ConfigRowNumberIsValid = False
        Exit Function
    End If

    ConfigRowNumberIsValid = CDbl(rawValue) >= 1 And CDbl(rawValue) = Fix(CDbl(rawValue))
End Function

Private Function ConfigRowNumber(ByVal rawValue As String, ByVal errorMessage As String) As Long
    If Not ConfigRowNumberIsValid(rawValue) Then
        Err.Raise vbObjectError + 2002, , errorMessage
    End If

    ConfigRowNumber = CLng(rawValue)
End Function

Private Sub ValidateActualsScopeConfig()
    Dim cutoffRow As Long
    cutoffRow = FirstIncludedRow()

    Dim cutoffProductionOrder As String
    cutoffProductionOrder = FirstIncludedProductionOrder()

    If cutoffProductionOrder = "" Then
        Err.Raise vbObjectError + 2003, , "ActualsConfig FirstIncludedProductionOrder is required."
    End If

    Dim databaseProductionOrder As String
    databaseProductionOrder = Trim$(CStr(ThisWorkbook.Worksheets(DATABASE_SHEET_NAME).Cells(cutoffRow, 1).Value))

    If databaseProductionOrder <> cutoffProductionOrder Then
        Err.Raise vbObjectError + 2004, , "ActualsConfig cutoff mismatch: Database row " & CStr(cutoffRow) & " column A is '" & databaseProductionOrder & "', expected '" & cutoffProductionOrder & "'."
    End If
End Sub

Private Function RowIsInActualsScope(ByVal databaseRow As Long, ByVal productionOrder As String, ByVal inclusions As Object) As Boolean
    ValidateActualsScopeConfig

    If databaseRow >= FirstIncludedRow() Then
        RowIsInActualsScope = True
        Exit Function
    End If

    RowIsInActualsScope = inclusions.Exists(ExplicitInclusionKey(databaseRow, productionOrder))
End Function

Private Sub SetupActualsData()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    UnprotectActualsSheet ws

    Dim dataHeaders As Variant
    dataHeaders = Array( _
        "Actual card ID", "Production order", "Database row", "Operation", "Operation code", _
        "Actual card number", "Produces finished product?", "Start date", "Start time", _
        "Stop date", "Stop time", "Start datetime normalized", "Stop datetime normalized", _
        "Pause minutes", "Extra minutes", "Calculated total minutes", "Total minutes override", _
        "Override reason", "Total minutes", "Gross kg", "Tare count", "Tare weight kg", _
        "Calculated net kg", "Manual net kg override", "Net kg", "Waste kg", "Meters produced", _
        "Units", "PP film material", "PP film quantity kg", _
        "Notes", "Voided?", "Void reason", "CreatedAt", "UpdatedAt" _
    )

    If Len(Trim$(CStr(ws.Range("A1").Value))) > 0 Then
        EnsureHeaderMatches ws, dataHeaders
        Exit Sub
    End If

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

Private Sub SetupActualsStatus()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(STATUS_SHEET_NAME)

    UnprotectActualsSheet ws

    Dim statusHeaders As Variant
    statusHeaders = Array("Production order", "Status", "UpdatedAt")

    If Len(Trim$(CStr(ws.Range("A1").Value))) > 0 Then
        EnsureHeaderMatches ws, statusHeaders
        Exit Sub
    End If

    ws.Range("A1:C1").Value = statusHeaders
    ws.Rows(1).Font.Bold = True
    ws.Columns("A:C").AutoFit
End Sub

Private Sub EnsureHeaderMatches(ByVal ws As Worksheet, ByVal expectedHeaders As Variant)
    Dim headerIndex As Long
    Dim columnNumber As Long
    Dim actualHeader As String
    Dim expectedHeader As String

    For headerIndex = LBound(expectedHeaders) To UBound(expectedHeaders)
        columnNumber = headerIndex - LBound(expectedHeaders) + 1
        actualHeader = Trim$(CStr(ws.Cells(1, columnNumber).Value))
        expectedHeader = CStr(expectedHeaders(headerIndex))

        If actualHeader <> expectedHeader Then
            Err.Raise vbObjectError + 2010, , "Unexpected " & ws.Name & " header in column " & CStr(columnNumber) & ": found '" & actualHeader & "', expected '" & expectedHeader & "'. Reinstall stopped to protect saved actuals/status data."
        End If
    Next headerIndex

    If Len(Trim$(CStr(ws.Cells(1, UBound(expectedHeaders) - LBound(expectedHeaders) + 2).Value))) > 0 Then
        Err.Raise vbObjectError + 2011, , "Unexpected extra " & ws.Name & " header after the expected header range. Reinstall stopped to protect saved actuals/status data."
    End If
End Sub

Private Sub SetupActualsEntry()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(ENTRY_SHEET_NAME)

    UnprotectActualsSheet ws
    DeleteActualsEntryButtons ws
    ws.Cells.Clear

    ws.Range("A1").Value = "Actuals Entry"
    ws.Range("A1").Font.Bold = True
    ws.Range("A1").Font.Size = 16
    ws.Range("A2").Value = "Enter a production order from the included ActualsConfig row set, load it, then save one actual card per operation."

    WriteEntryLabel ws, 3, "Production order", "ActualsEntryProductionOrder"
    WriteEntryLabel ws, 4, "Database row", "ActualsEntryDatabaseRow"
    WriteEntryLabel ws, 5, "Operation", "ActualsEntryOperation"
    WriteEntryLabel ws, 6, "Current status", "ActualsEntryCurrentStatus"
    WriteEntryLabel ws, 7, "Customer", "ActualsEntryCustomer"
    WriteEntryLabel ws, 8, "Product/type", "ActualsEntryProductType"
    WriteEntryLabel ws, 9, "Expected operations", "ActualsEntryExpectedOperations"
    WriteEntryLabel ws, 10, "Produces finished product?", "ActualsEntryProducesFinishedProduct"

    WriteEntryLabel ws, 12, "Start date", "ActualsEntryStartDate"
    WriteEntryLabel ws, 13, "Start time", "ActualsEntryStartTime"
    WriteEntryLabel ws, 14, "Stop date", "ActualsEntryStopDate"
    WriteEntryLabel ws, 15, "Stop time", "ActualsEntryStopTime"
    WriteEntryLabel ws, 16, "Pause minutes", "ActualsEntryPauseMinutes"
    WriteEntryLabel ws, 17, "Extra minutes", "ActualsEntryExtraMinutes"
    WriteEntryLabel ws, 18, "Total minutes override", "ActualsEntryTotalMinutesOverride"
    WriteEntryLabel ws, 19, "Override reason", "ActualsEntryOverrideReason"

    WriteEntryLabel ws, 21, "Gross kg", "ActualsEntryGrossKg"
    WriteEntryLabel ws, 22, "Tare count", "ActualsEntryTareCount"
    WriteEntryLabel ws, 23, "Tare weight kg", "ActualsEntryTareWeightKg"
    WriteEntryLabel ws, 24, "Manual net kg override", "ActualsEntryManualNetKgOverride"
    WriteEntryLabel ws, 25, "Waste kg", "ActualsEntryWasteKg"
    WriteEntryLabel ws, 26, "Meters produced", "ActualsEntryMetersProduced"
    WriteEntryLabel ws, 27, "Units", "ActualsEntryUnits"

    WriteEntryLabel ws, 29, "PP film material", "ActualsEntryPPFilmMaterial"
    WriteEntryLabel ws, 30, "PP film quantity kg", "ActualsEntryPPFilmQuantityKg"
    WriteEntryLabel ws, 31, "Notes", "ActualsEntryNotes"
    WriteEntryLabel ws, 33, "Selected actual card ID", "ActualsEntrySelectedActualCardID"

    ws.Range("D2").Value = "Saved active actual cards for loaded order"
    ws.Range("D2").Font.Bold = True
    ws.Range("D3:K3").Value = Array("Actual card ID", "Card #", "Operation", "Start date", "Stop date", "Total minutes", "Gross kg", "UpdatedAt")
    ws.Range("D3:K3").Font.Bold = True

    AddActualsEntryButton ws, "ActualsEntryButtonLoadOrder", "Load order", "LoadActualsEntryOrder", 3
    AddActualsEntryButton ws, "ActualsEntryButtonSaveNew", "Save new card", "SaveNewActualCard", 5
    AddActualsEntryButton ws, "ActualsEntryButtonLoadSelected", "Load selected card", "LoadSelectedActualCard", 7
    AddActualsEntryButton ws, "ActualsEntryButtonSaveChanges", "Save changes", "SaveActualCardChanges", 9
    AddActualsEntryButton ws, "ActualsEntryButtonVoidSelected", "Void selected card", "VoidSelectedActualCard", 11
    AddActualsEntryButton ws, "ActualsEntryButtonClear", "Clear fields", "ClearActualsEntryFields", 13

    StyleActualsEntry ws
    ws.Range("B31").WrapText = True
    ws.Columns("A:K").AutoFit
    ws.Columns("B").ColumnWidth = 28
    ws.Columns("D:K").ColumnWidth = 16
End Sub

Private Sub SetupActualsReview()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(REVIEW_SHEET_NAME)

    UnprotectActualsSheet ws
    DeleteActualsReviewButtons ws
    ws.Cells.Clear

    ws.Range("A1").Value = "Actuals Review"
    ws.Range("A1").Font.Bold = True
    ws.Range("A1").Font.Size = 16
    ws.Range("A2").Value = "Use Refresh to rebuild the included-scope review tables, then edit Manufacturing status and Save."

    AddActualsReviewButton ws, "ActualsReviewButtonRefresh", "Refresh review", "RefreshActualsReview", 3
    AddActualsReviewButton ws, "ActualsReviewButtonSave", "Save statuses", "SaveActualsReview", 5
    AddActualsReviewButton ws, "ActualsReviewButtonValidate", "Run validation", "RunActualsValidation", 7

    StyleActualsReviewShell ws
    ws.Columns("A:J").AutoFit
    ws.Columns("K").Hidden = True
End Sub

Private Sub SetupActualsValidation()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(VALIDATION_SHEET_NAME)

    UnprotectActualsSheet ws
    ws.Cells.Clear
    WriteActualsValidationHeader ws
    ws.Cells(5, 1).Value = "Run validation from Actuals Review to generate this report."
    ws.Columns("A:H").AutoFit
End Sub

Public Sub ApplyActualsProtection()
    UnprotectActualsSheet ThisWorkbook.Worksheets(ENTRY_SHEET_NAME)
    UnprotectActualsSheet ThisWorkbook.Worksheets(REVIEW_SHEET_NAME)
    UnprotectActualsSheet ThisWorkbook.Worksheets(VALIDATION_SHEET_NAME)
    UnprotectActualsSheet ThisWorkbook.Worksheets(DATA_SHEET_NAME)
    UnprotectActualsSheet ThisWorkbook.Worksheets(STATUS_SHEET_NAME)
    UnprotectActualsSheet ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)
End Sub

Private Sub UnprotectActualsSheet(ByVal ws As Worksheet)
    On Error Resume Next
    ws.Unprotect Password:=LEGACY_PROTECTION_PASSWORD
    ws.Unprotect
    On Error GoTo 0

    ws.Cells.Locked = False
End Sub

Private Sub WriteEntryLabel(ByVal ws As Worksheet, ByVal rowNumber As Long, ByVal labelText As String, ByVal rangeName As String)
    ws.Cells(rowNumber, 1).Value = labelText
    ws.Cells(rowNumber, 1).Font.Bold = True
    SetWorkbookName rangeName, ws.Cells(rowNumber, 2)
End Sub

Private Sub SetWorkbookName(ByVal rangeName As String, ByVal targetRange As Range)
    On Error Resume Next
    ThisWorkbook.Names(rangeName).Delete
    On Error GoTo 0

    ThisWorkbook.Names.Add Name:=rangeName, RefersTo:=targetRange
End Sub

Private Function EntryRange(ByVal rangeName As String) As Range
    Set EntryRange = ThisWorkbook.Names(rangeName).RefersToRange
End Function

Private Sub DeleteActualsConfigButtons(ByVal ws As Worksheet)
    Dim shapeIndex As Long
    For shapeIndex = ws.Shapes.Count To 1 Step -1
        If Left$(ws.Shapes(shapeIndex).Name, Len("ActualsConfigButton")) = "ActualsConfigButton" Then
            ws.Shapes(shapeIndex).Delete
        End If
    Next shapeIndex
End Sub

Private Sub AddActualsConfigButton(ByVal ws As Worksheet, ByVal buttonName As String, ByVal captionText As String, ByVal macroName As String, ByVal rowNumber As Long)
    Dim button As Button
    Set button = ws.Buttons.Add(ws.Range("F" & CStr(rowNumber)).Left, ws.Range("F" & CStr(rowNumber)).Top, 190, 26)
    button.Name = buttonName
    button.Characters.Text = captionText
    button.OnAction = macroName
End Sub

Private Sub DeleteActualsEntryButtons(ByVal ws As Worksheet)
    Dim shapeIndex As Long
    For shapeIndex = ws.Shapes.Count To 1 Step -1
        If Left$(ws.Shapes(shapeIndex).Name, Len("ActualsEntryButton")) = "ActualsEntryButton" Then
            ws.Shapes(shapeIndex).Delete
        End If
    Next shapeIndex
End Sub

Private Sub AddActualsEntryButton(ByVal ws As Worksheet, ByVal buttonName As String, ByVal captionText As String, ByVal macroName As String, ByVal rowNumber As Long)
    Dim button As Button
    Set button = ws.Buttons.Add(ws.Range("M" & CStr(rowNumber)).Left, ws.Range("M" & CStr(rowNumber)).Top, 130, 24)
    button.Name = buttonName
    button.Characters.Text = captionText
    button.OnAction = macroName
End Sub

Private Sub DeleteActualsReviewButtons(ByVal ws As Worksheet)
    Dim shapeIndex As Long
    For shapeIndex = ws.Shapes.Count To 1 Step -1
        If Left$(ws.Shapes(shapeIndex).Name, Len("ActualsReviewButton")) = "ActualsReviewButton" Then
            ws.Shapes(shapeIndex).Delete
        End If
    Next shapeIndex
End Sub

Private Sub AddActualsReviewButton(ByVal ws As Worksheet, ByVal buttonName As String, ByVal captionText As String, ByVal macroName As String, ByVal rowNumber As Long)
    Dim button As Button
    Set button = ws.Buttons.Add(ws.Range("M" & CStr(rowNumber)).Left, ws.Range("M" & CStr(rowNumber)).Top, 130, 24)
    button.Name = buttonName
    button.Characters.Text = captionText
    button.OnAction = macroName
End Sub

Private Sub StyleActualsConfig(ByVal ws As Worksheet)
    ws.Cells.Font.Name = "Calibri"
    ws.Cells.Font.Size = 11

    ws.Range("A1:D1,A6:D6,A10:C10,A25:D25").Interior.Color = RGB(31, 78, 121)
    ws.Range("A1:D1,A6:D6,A10:C10,A25:D25").Font.Color = RGB(255, 255, 255)
    ws.Range("A1:D1,A6:D6,A10:C10,A25:D25").Font.Bold = True

    ws.Range("B2:B3").Interior.Color = RGB(255, 242, 204)
    ws.Range("B2:B3").Font.Bold = True
    ws.Range("A2:D3").Borders.LineStyle = xlContinuous
    ws.Range("A2:D3").Borders.Color = RGB(191, 143, 0)

    ws.Range("F1:H1").Merge
    ws.Range("F1").Interior.Color = RGB(31, 78, 121)
    ws.Range("F1").Font.Color = RGB(255, 255, 255)
    ws.Range("F1").Font.Bold = True
    ws.Range("F1").Font.Size = 14
    ws.Range("F2:H3").Interior.Color = RGB(221, 235, 247)
    ws.Range("F2:H3").WrapText = True

    ws.Range("A7:D9").Interior.Color = RGB(242, 242, 242)
    ws.Range("A18:A22").Interior.Color = RGB(226, 239, 218)
    ws.Range("A26:D26").Interior.Color = RGB(242, 242, 242)
    ws.Columns("C:D").ColumnWidth = 36
    ws.Columns("F:H").ColumnWidth = 24
End Sub

Private Sub StyleActualsEntry(ByVal ws As Worksheet)
    ws.Cells.Font.Name = "Calibri"
    ws.Cells.Font.Size = 11
    ws.Range("A1:K1").Interior.Color = RGB(31, 78, 121)
    ws.Range("A1:K1").Font.Color = RGB(255, 255, 255)
    ws.Range("A1:K1").Font.Bold = True
    ws.Range("A2:K2").Interior.Color = RGB(221, 235, 247)
    ws.Range("A2:K2").WrapText = True
    ws.Range("A3:A33").Font.Bold = True
    ws.Range("B3:B33").Interior.Color = RGB(255, 242, 204)
    ws.Range("B4:B9").Interior.Color = RGB(226, 239, 218)
    ws.Range("D2:K3").Interior.Color = RGB(31, 78, 121)
    ws.Range("D2:K3").Font.Color = RGB(255, 255, 255)
    ws.Range("D2:K3").Font.Bold = True
    ws.Range("A3:B10,A12:B19,A21:B27,A29:B33,D3:K200").Borders.LineStyle = xlContinuous
    ws.Range("A3:B10,A12:B19,A21:B27,A29:B33,D3:K200").Borders.Color = RGB(217, 217, 217)
End Sub

Private Sub StyleActualsReviewShell(ByVal ws As Worksheet)
    ws.Cells.Font.Name = "Calibri"
    ws.Cells.Font.Size = 11
    ws.Range("A1:J1").Interior.Color = RGB(31, 78, 121)
    ws.Range("A1:J1").Font.Color = RGB(255, 255, 255)
    ws.Range("A1:J1").Font.Bold = True
    ws.Range("A2:J2").Interior.Color = RGB(221, 235, 247)
    ws.Range("A2:J2").WrapText = True
End Sub

Public Sub SetActualsCutoffFromPrompt()
    Dim rowInput As Variant
    rowInput = Application.InputBox( _
        Prompt:="Enter the first Database row to include in Actuals V1." & vbCrLf & _
            "For the dummy post-cutoff orders, enter 5314.", _
        Title:="Set Actuals Cutoff", _
        Type:=1)

    If VarType(rowInput) = vbBoolean Then
        If rowInput = False Then Exit Sub
    End If

    If CDbl(rowInput) <> Fix(CDbl(rowInput)) Or CLng(rowInput) < 5 Then
        MsgBox "Cutoff row must be a whole Database row number of 5 or greater.", vbExclamation, "Actuals Setup"
        Exit Sub
    End If

    Dim cutoffRow As Long
    cutoffRow = CLng(rowInput)

    Dim databaseWs As Worksheet
    Set databaseWs = ThisWorkbook.Worksheets(DATABASE_SHEET_NAME)

    Dim productionOrder As String
    productionOrder = Trim$(CStr(databaseWs.Cells(cutoffRow, 1).Value))

    If productionOrder = "" Then
        MsgBox "Database row " & CStr(cutoffRow) & " has no production order in column A.", vbExclamation, "Actuals Setup"
        Exit Sub
    End If

    Dim configWs As Worksheet
    Set configWs = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)
    UnprotectActualsSheet configWs
    configWs.Range("B2").Value = cutoffRow
    configWs.Range("B3").Value = productionOrder
    StyleActualsConfig configWs

    MsgBox "Actuals cutoff set to Database row " & CStr(cutoffRow) & _
        " / production order " & productionOrder & ".", vbInformation, "Actuals Setup"
End Sub

Public Sub RefreshActualsReview()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(REVIEW_SHEET_NAME)

    ws.Range("A1:K" & CStr(ws.Rows.Count)).Clear

    Dim reviewRows As Object
    Set reviewRows = CreateObject("Scripting.Dictionary")

    Dim inProductionRows As Collection
    Set inProductionRows = New Collection
    reviewRows.Add "In Production / On Hold", inProductionRows

    Dim plannedRows As Collection
    Set plannedRows = New Collection
    reviewRows.Add "Planned", plannedRows

    Dim inclusions As Object
    Set inclusions = LoadExplicitInclusions()

    Dim databaseWs As Worksheet
    Set databaseWs = ThisWorkbook.Worksheets(DATABASE_SHEET_NAME)

    Dim lastRow As Long
    lastRow = databaseWs.Cells(databaseWs.Rows.Count, 1).End(xlUp).Row

    Dim processedRows As Object
    Set processedRows = CreateObject("Scripting.Dictionary")

    Dim inclusionKey As Variant
    For Each inclusionKey In inclusions.Keys
        Dim inclusionParts As Variant
        inclusionParts = Split(CStr(inclusionKey), "|")
        If UBound(inclusionParts) >= 1 Then
            Dim includedRowNumber As Long
            includedRowNumber = CLng(inclusionParts(0))
            If Not processedRows.Exists(CStr(includedRowNumber)) Then
                AddIncludedActualsReviewRow databaseWs, includedRowNumber, inclusions, reviewRows
                processedRows(CStr(includedRowNumber)) = True
            End If
        End If
    Next inclusionKey

    Dim rowNumber As Long
    For rowNumber = FirstIncludedRow() To lastRow
        If Not processedRows.Exists(CStr(rowNumber)) Then
            AddIncludedActualsReviewRow databaseWs, rowNumber, inclusions, reviewRows
            processedRows(CStr(rowNumber)) = True
        End If
    Next rowNumber

    Dim outputRow As Long
    outputRow = 1
    outputRow = WriteActualsReviewTable(ws, outputRow, "In Production / On Hold", reviewRows("In Production / On Hold"))
    outputRow = outputRow + 1
    outputRow = WriteActualsReviewTable(ws, outputRow, "Planned", reviewRows("Planned"))

    StyleActualsReviewShell ws
    ws.Columns("A:J").AutoFit
    ws.Columns("K").Hidden = True
    UnprotectActualsSheet ws
    MsgBox "Actuals Review refreshed.", vbInformation, "Actuals Review"
End Sub

Private Sub AddIncludedActualsReviewRow(ByVal databaseWs As Worksheet, ByVal databaseRow As Long, ByVal inclusions As Object, ByVal reviewRows As Object)
    Dim productionOrder As String
    productionOrder = Trim$(CStr(databaseWs.Cells(databaseRow, 1).Value))

    If productionOrder = "" Then
        Exit Sub
    End If

    If Not RowIsInActualsScope(databaseRow, productionOrder, inclusions) Then
        Exit Sub
    End If

    Dim statusValue As String
    statusValue = ProductionOrderStatus(productionOrder)

    Dim tableName As String
    If statusValue = "In Production" Or statusValue = "On Hold" Then
        tableName = "In Production / On Hold"
    ElseIf statusValue = "Planned" Then
        tableName = "Planned"
    Else
        Exit Sub
    End If

    reviewRows(tableName).Add BuildActualsReviewRow(databaseWs, databaseRow, productionOrder, statusValue)
End Sub

Public Sub SaveActualsReview()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(REVIEW_SHEET_NAME)

    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row

    Dim statusUpdates As Collection
    Set statusUpdates = New Collection

    Dim rowNumber As Long
    For rowNumber = 1 To lastRow
        If IsActualsReviewStatusRow(ws, rowNumber) Then
            Dim productionOrder As String
            productionOrder = Trim$(CStr(ws.Cells(rowNumber, 1).Value))

            Dim statusValue As String
            statusValue = Trim$(CStr(ws.Cells(rowNumber, 4).Value))
            If statusValue = "" Then
                statusValue = "Planned"
            End If

            If Not StatusIsApproved(statusValue) Then
                MsgBox "Invalid Manufacturing status '" & statusValue & "' for production order " & productionOrder & ". Use a value from ActualsConfig StatusList.", vbExclamation, "Actuals Review"
                Exit Sub
            End If

            If Not ValidateActualsReviewStatusScope(productionOrder) Then
                Exit Sub
            End If

            statusUpdates.Add Array(productionOrder, statusValue)
        End If
    Next rowNumber

    Dim statusUpdate As Variant
    For Each statusUpdate In statusUpdates
        UpsertProductionOrderStatus CStr(statusUpdate(0)), CStr(statusUpdate(1))
    Next statusUpdate

    MsgBox "Saved " & CStr(statusUpdates.Count) & " Actuals Review status row(s).", vbInformation, "Actuals Review"
End Sub

Public Sub RunActualsValidation()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(VALIDATION_SHEET_NAME)

    ws.Cells.Clear
    WriteActualsValidationHeader ws

    Dim errors As Collection
    Set errors = New Collection

    ValidateDuplicateIncludedProductionOrders errors
    ValidateCompletedIncludedOrders errors
    ValidateActualCards errors

    WriteActualsValidationReport ws, errors
    ws.Columns("A:H").AutoFit
    ws.Activate

    MsgBox "Actuals Validation generated with " & CStr(errors.Count) & " issue(s).", vbInformation, "Actuals Validation"
End Sub

Private Sub WriteActualsValidationHeader(ByVal ws As Worksheet)
    ws.Range("A1").Value = "Actuals Validation"
    ws.Range("A1").Font.Bold = True
    ws.Range("A1").Font.Size = 16
    ws.Range("A2").Value = "Generated at"
    ws.Range("B2").Value = Now
    ws.Range("A4:H4").Value = Array( _
        "Production order", _
        "Actual card ID", _
        "Operation code", _
        "Operation", _
        "Issue", _
        "Recommended action", _
        "Context", _
        "Severity" _
    )
    ws.Range("A4:H4").Font.Bold = True
End Sub

Private Sub WriteActualsValidationReport(ByVal ws As Worksheet, ByVal errors As Collection)
    Dim outputRow As Long
    outputRow = 5

    If errors.Count = 0 Then
        ws.Cells(outputRow, 1).Value = "No validation issues found."
        Exit Sub
    End If

    Dim issue As Variant
    For Each issue In errors
        ws.Range("A" & CStr(outputRow) & ":H" & CStr(outputRow)).Value = issue
        outputRow = outputRow + 1
    Next issue
End Sub

Private Sub AddValidationIssue(ByVal errors As Collection, ByVal productionOrder As String, ByVal actualCardId As String, ByVal operationCode As String, ByVal operationName As String, ByVal issueText As String, ByVal recommendedAction As String, ByVal contextText As String)
    errors.Add Array(productionOrder, actualCardId, operationCode, operationName, issueText, recommendedAction, contextText, "Error")
End Sub

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

Private Sub ValidateCompletedIncludedOrders(ByVal errors As Collection)
    Dim wsDatabase As Worksheet
    Set wsDatabase = ThisWorkbook.Worksheets(DATABASE_SHEET_NAME)

    Dim inclusions As Object
    Set inclusions = LoadExplicitInclusions()

    Dim lastRow As Long
    lastRow = wsDatabase.Cells(wsDatabase.Rows.Count, 1).End(xlUp).Row

    Dim rowNumber As Long
    For rowNumber = 5 To lastRow
        Dim productionOrder As String
        productionOrder = Trim$(CStr(wsDatabase.Cells(rowNumber, 1).Value))

        If Len(productionOrder) > 0 Then
            If RowIsInActualsScope(rowNumber, productionOrder, inclusions) Then
                If ProductionOrderStatus(productionOrder) = "Completed" Then
                    Dim expectedOperationsText As String
                    expectedOperationsText = ExpectedOperationsForDatabaseRow(rowNumber)

                    Dim expectedOperationCodes As Collection
                    Set expectedOperationCodes = ExpectedOperationCodesForDatabaseRow(rowNumber)

                    Dim operationCode As Variant
                    For Each operationCode In expectedOperationCodes
                        If Not ActiveActualCardExists(productionOrder, operationCode, vbNullString) Then
                            AddValidationIssue errors, productionOrder, "", CStr(operationCode), OperationNameForCode(CStr(operationCode)), _
                                "Completed production order is missing an active ActualsData card for an expected operation.", _
                                "Create and save an active actual card for each expected operation before treating the order as complete.", _
                                "Database row " & CStr(rowNumber) & "; expected operations: " & expectedOperationsText
                        End If
                    Next operationCode
                End If
            End If
        End If
    Next rowNumber
End Sub

Private Sub ValidateActualCards(ByVal errors As Collection)
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    Dim rowNumber As Long
    For rowNumber = 2 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If ActualsDataRowIsInCurrentScope(rowNumber) _
            And ActualCardIsActive(rowNumber) Then
            Dim actualCardId As String
            Dim productionOrder As String
            Dim operationName As String
            Dim operationCode As String
            Dim databaseRow As Long

            actualCardId = Trim$(CStr(ws.Cells(rowNumber, 1).Value))
            productionOrder = Trim$(CStr(ws.Cells(rowNumber, 2).Value))
            databaseRow = CLng(ws.Cells(rowNumber, 3).Value)
            operationName = Trim$(CStr(ws.Cells(rowNumber, 4).Value))
            operationCode = Trim$(CStr(ws.Cells(rowNumber, 5).Value))

            If Not OrderExpectsOperation(databaseRow, operationCode) Then
                AddValidationIssue errors, productionOrder, actualCardId, operationCode, operationName, _
                    "Saved actual operation is no longer expected for its production order.", _
                    "Void this actual card or correct the expected operation flags before final review.", _
                    "ActualsData row " & CStr(rowNumber) & "; Database row " & CStr(databaseRow)
            End If

            If Not ActualCardHasRequiredTimeFields(rowNumber) Then
                AddValidationIssue errors, productionOrder, actualCardId, operationCode, operationName, _
                    "Required time fields are missing.", _
                    "Enter start date, start time, stop date, and stop time for the actual card.", _
                    "ActualsData row " & CStr(rowNumber)
            ElseIf CDate(ws.Cells(rowNumber, 13).Value) < CDate(ws.Cells(rowNumber, 12).Value) Then
                AddValidationIssue errors, productionOrder, actualCardId, operationCode, operationName, _
                    "Stop datetime cannot be before start datetime.", _
                    "Correct the actual card start/stop date and time fields.", _
                    "ActualsData row " & CStr(rowNumber)
            End If

            If Not ActualCardNumericFieldsAreNonNegative(rowNumber) Then
                AddValidationIssue errors, productionOrder, actualCardId, operationCode, operationName, _
                    "Numeric fields must be non-negative.", _
                    "Correct numeric ActualsData fields so entered values are numbers greater than or equal to zero.", _
                    "ActualsData row " & CStr(rowNumber)
            End If

            If Not ActualCardPPFilmFieldsArePaired(rowNumber) Then
                AddValidationIssue errors, productionOrder, actualCardId, operationCode, operationName, _
                    "PP film material and quantity must be entered together.", _
                    "Enter both PP film material and PP film quantity, or clear both fields.", _
                    "ActualsData row " & CStr(rowNumber)
            End If

            If Len(Trim$(CStr(ws.Cells(rowNumber, 17).Value))) > 0 _
                And Len(Trim$(CStr(ws.Cells(rowNumber, 18).Value))) = 0 Then
                AddValidationIssue errors, productionOrder, actualCardId, operationCode, operationName, _
                    "Total minutes override requires a reason.", _
                    "Enter an override reason or clear the total minutes override.", _
                    "ActualsData row " & CStr(rowNumber)
            End If

            If operationCode = "CON" _
                And Not CellHasPositiveNumericValue(ws.Cells(rowNumber, 28).Value) Then
                AddValidationIssue errors, productionOrder, actualCardId, operationCode, operationName, _
                    "Confection operations require units.", _
                    "Enter produced units for confection actual cards.", _
                    "ActualsData row " & CStr(rowNumber)
            End If
        End If
    Next rowNumber
End Sub

Private Function BuildActualsReviewRow(ByVal databaseWs As Worksheet, ByVal databaseRow As Long, ByVal productionOrder As String, ByVal statusValue As String) As Variant
    Dim totals As Object
    Set totals = FinishedProductActualTotals(productionOrder)

    BuildActualsReviewRow = Array( _
        productionOrder, _
        databaseWs.Cells(databaseRow, 4).Value, _
        databaseWs.Cells(databaseRow, 6).Value, _
        statusValue, _
        OperationsEnteredExpectedText(productionOrder, databaseRow), _
        databaseWs.Cells(databaseRow, 7).Value, _
        totals("GrossKg"), _
        totals("NetKg"), _
        totals("Meters"), _
        totals("Units") _
    )
End Function

Private Function WriteActualsReviewTable(ByVal ws As Worksheet, ByVal startRow As Long, ByVal titleText As String, ByVal rows As Collection) As Long
    ws.Cells(startRow, 1).Value = titleText
    ws.Cells(startRow, 1).Font.Bold = True
    ws.Range("A" & CStr(startRow) & ":J" & CStr(startRow)).Interior.Color = RGB(31, 78, 121)
    ws.Range("A" & CStr(startRow) & ":J" & CStr(startRow)).Font.Color = RGB(255, 255, 255)

    Dim headerRow As Long
    headerRow = startRow + 1
    ws.Range("A" & CStr(headerRow) & ":J" & CStr(headerRow)).Value = ActualsReviewHeaders()
    ws.Range("A" & CStr(headerRow) & ":J" & CStr(headerRow)).Font.Bold = True
    ws.Range("A" & CStr(headerRow) & ":J" & CStr(headerRow)).Interior.Color = RGB(217, 225, 242)

    Dim outputRow As Long
    outputRow = headerRow + 1

    Dim index As Long
    For index = 1 To rows.Count
        WriteActualsReviewRow ws, outputRow, rows(index)
        outputRow = outputRow + 1
    Next index

    If rows.Count > 1 Then
        SortReviewRowsByProductionOrder ws, headerRow, outputRow - 1
    End If

    If rows.Count = 0 Then
        ws.Cells(outputRow, 1).Value = "No included orders."
        ws.Range("A" & CStr(outputRow) & ":J" & CStr(outputRow)).Interior.Color = RGB(242, 242, 242)
        outputRow = outputRow + 1
    End If

    WriteActualsReviewTable = outputRow
End Function

Private Function ActualsReviewHeaders() As Variant
    ActualsReviewHeaders = Array( _
        "Production order", _
        "Customer", _
        "Product/type", _
        "Manufacturing status", _
        "Operations entered / expected", _
        "Gross ordered kg", _
        "Finished product actual gross kg", _
        "Finished product actual net kg", _
        "Finished product actual meters", _
        "Finished product actual units" _
    )
End Function

Private Sub WriteActualsReviewRow(ByVal ws As Worksheet, ByVal outputRow As Long, ByVal rowValues As Variant)
    ws.Range("A" & CStr(outputRow) & ":J" & CStr(outputRow)).Value = rowValues
    ws.Cells(outputRow, 11).Value = "ActualsReviewDataRow"
End Sub

Private Sub SortReviewRowsByProductionOrder(ByVal ws As Worksheet, ByVal headerRow As Long, ByVal lastDataRow As Long)
    With ws.Sort
        .SortFields.Clear
        .SortFields.Add Key:=ws.Range("A" & CStr(headerRow + 1) & ":A" & CStr(lastDataRow)), SortOn:=xlSortOnValues, Order:=xlAscending, DataOption:=xlSortNormal
        .SetRange ws.Range("A" & CStr(headerRow) & ":J" & CStr(lastDataRow))
        .Header = xlYes
        .Apply
    End With
End Sub

Private Function IsActualsReviewStatusRow(ByVal ws As Worksheet, ByVal rowNumber As Long) As Boolean
    IsActualsReviewStatusRow = Trim$(CStr(ws.Cells(rowNumber, 1).Value)) <> "" _
        And Trim$(CStr(ws.Cells(rowNumber, 1).Value)) <> "Production order" _
        And Trim$(CStr(ws.Cells(rowNumber, 5).Value)) <> "" _
        And Trim$(CStr(ws.Cells(rowNumber, 11).Value)) = "ActualsReviewDataRow"
End Function

Private Function ValidateActualsReviewStatusScope(ByVal productionOrder As String) As Boolean
    Dim matchingRows As Collection
    Set matchingRows = IncludedDatabaseRowsForOrder(productionOrder)

    If matchingRows.Count <> 1 Then
        MsgBox "Actuals Review row is no longer in the current included Actuals scope: production order " & productionOrder & ". Refresh Actuals Review before saving.", vbExclamation, "Actuals Review"
        Exit Function
    End If

    ValidateActualsReviewStatusScope = True
End Function

Private Function StatusIsApproved(ByVal statusValue As String) As Boolean
    Dim statuses As Object
    Set statuses = ApprovedActualsStatuses()

    StatusIsApproved = statuses.Exists(LCase$(Trim$(statusValue)))
End Function

Private Function ApprovedActualsStatuses() As Object
    Dim statuses As Object
    Set statuses = CreateObject("Scripting.Dictionary")

    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)

    Dim rowNumber As Long
    For rowNumber = 18 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        Dim statusValue As String
        statusValue = Trim$(CStr(ws.Cells(rowNumber, 1).Value))
        If statusValue = "" Then
            Exit For
        End If

        statuses(LCase$(statusValue)) = True
    Next rowNumber

    If statuses.Count = 0 Then
        statuses("planned") = True
        statuses("in production") = True
        statuses("on hold") = True
        statuses("completed") = True
        statuses("cancelled") = True
    End If

    Set ApprovedActualsStatuses = statuses
End Function

Private Sub UpsertProductionOrderStatus(ByVal productionOrder As String, ByVal statusValue As String)
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(STATUS_SHEET_NAME)

    Dim rowNumber As Long
    For rowNumber = 2 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If Trim$(CStr(ws.Cells(rowNumber, 1).Value)) = productionOrder Then
            ws.Cells(rowNumber, 2).Value = statusValue
            ws.Cells(rowNumber, 3).Value = Now
            Exit Sub
        End If
    Next rowNumber

    rowNumber = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row + 1
    If rowNumber < 2 Then
        rowNumber = 2
    End If

    ws.Cells(rowNumber, 1).Value = productionOrder
    ws.Cells(rowNumber, 2).Value = statusValue
    ws.Cells(rowNumber, 3).Value = Now
End Sub

Private Function OperationsEnteredExpectedText(ByVal productionOrder As String, ByVal databaseRow As Long) As String
    Dim enteredOperations As String
    enteredOperations = EnteredOperationsForProductionOrder(productionOrder)
    If enteredOperations = "" Then
        enteredOperations = "(none)"
    End If

    Dim expectedOperations As String
    expectedOperations = ExpectedOperationsForDatabaseRow(databaseRow)
    If expectedOperations = "" Then
        expectedOperations = "(none)"
    End If

    OperationsEnteredExpectedText = enteredOperations & " / " & expectedOperations
End Function

Private Function EnteredOperationsForProductionOrder(ByVal productionOrder As String) As String
    Dim operations As Object
    Set operations = CreateObject("Scripting.Dictionary")

    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    Dim rowNumber As Long
    For rowNumber = 2 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If Trim$(CStr(ws.Cells(rowNumber, 2).Value)) = productionOrder _
            And ActualsDataRowIsInCurrentScope(rowNumber) _
            And Not ActualCardIsVoided(rowNumber) Then
            Dim operationName As String
            operationName = Trim$(CStr(ws.Cells(rowNumber, 4).Value))
            If operationName <> "" Then
                operations(operationName) = True
            End If
        End If
    Next rowNumber

    EnteredOperationsForProductionOrder = JoinDictionaryKeys(operations, ", ")
End Function

Private Function FinishedProductActualTotals(ByVal productionOrder As String) As Object
    Dim totals As Object
    Set totals = CreateObject("Scripting.Dictionary")
    totals("GrossKg") = 0#
    totals("NetKg") = 0#
    totals("Meters") = 0#
    totals("Units") = 0#

    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    Dim rowNumber As Long
    For rowNumber = 2 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If Trim$(CStr(ws.Cells(rowNumber, 2).Value)) = productionOrder _
            And ActualsDataRowIsInCurrentScope(rowNumber) _
            And Not ActualCardIsVoided(rowNumber) _
            And ActualsDataRowProducesFinishedProduct(rowNumber) Then
            totals("GrossKg") = totals("GrossKg") + NumericCellValue(ws.Cells(rowNumber, 20).Value)
            totals("NetKg") = totals("NetKg") + NumericCellValue(ws.Cells(rowNumber, 25).Value)
            totals("Meters") = totals("Meters") + NumericCellValue(ws.Cells(rowNumber, 27).Value)
            totals("Units") = totals("Units") + NumericCellValue(ws.Cells(rowNumber, 28).Value)
        End If
    Next rowNumber

    Set FinishedProductActualTotals = totals
End Function

Private Function ActualsDataRowProducesFinishedProduct(ByVal dataRow As Long) As Boolean
    Dim valueText As String
    valueText = LCase$(Trim$(CStr(ThisWorkbook.Worksheets(DATA_SHEET_NAME).Cells(dataRow, 7).Value)))
    ActualsDataRowProducesFinishedProduct = (valueText = "yes" Or valueText = "да" Or valueText = "true" Or valueText = "1")
End Function

Private Function NumericCellValue(ByVal value As Variant) As Double
    If IsNumeric(value) Then
        NumericCellValue = CDbl(value)
    End If
End Function

Private Function JoinDictionaryKeys(ByVal values As Object, ByVal delimiter As String) As String
    Dim result As String
    Dim key As Variant

    For Each key In values.Keys
        If result <> "" Then
            result = result & delimiter
        End If
        result = result & CStr(key)
    Next key

    JoinDictionaryKeys = result
End Function

Public Sub ClearActualsEntryFields()
    ClearEntryFieldsOnly
    ClearActualsCardList
End Sub

Public Sub LoadActualsEntryOrder()
    Dim productionOrder As String
    productionOrder = Trim$(CStr(EntryRange("ActualsEntryProductionOrder").Value))

    If productionOrder = "" Then
        MsgBox "Production order is required.", vbExclamation, "Actuals Entry"
        Exit Sub
    End If

    Dim databaseRow As Long
    databaseRow = SingleIncludedDatabaseRowForOrder(productionOrder)
    If databaseRow = 0 Then
        Exit Sub
    End If

    PopulateOrderContext productionOrder, databaseRow
    ListActualCardsForOrder productionOrder
End Sub

Public Sub SaveNewActualCard()
    Dim productionOrder As String
    Dim databaseRow As Long
    Dim operationCode As String
    Dim operationName As String

    If Not ValidateEntryOrderAndOperation(productionOrder, databaseRow, operationCode, operationName) Then
        Exit Sub
    End If

    If Not ValidateActualEntryCalculations(operationName) Then
        Exit Sub
    End If

    If ActiveActualCardExists(productionOrder, operationCode, vbNullString) Then
        If MsgBox("Another active actual card already exists for this production order and operation. Save another card?", vbQuestion + vbYesNo, "Actuals Entry") <> vbYes Then
            Exit Sub
        End If
    End If

    Dim dataRow As Long
    Dim cardNumber As Long
    Dim cardId As String
    cardNumber = NextActualCardNumber(productionOrder, operationCode)
    cardId = ActualCardID(productionOrder, operationCode, cardNumber)

    dataRow = NextActualsDataRow()
    If Not WriteActualCardRow(dataRow, cardId, productionOrder, databaseRow, operationName, operationCode, cardNumber, Now, Now) Then
        Exit Sub
    End If

    EntryRange("ActualsEntrySelectedActualCardID").Value = cardId
    ListActualCardsForOrder productionOrder
    MsgBox "Actual card saved.", vbInformation, "Actuals Entry"
End Sub

Public Sub LoadSelectedActualCard()
    Dim cardId As String
    cardId = Trim$(CStr(EntryRange("ActualsEntrySelectedActualCardID").Value))

    If cardId = "" Then
        MsgBox "Selected actual card ID is required.", vbExclamation, "Actuals Entry"
        Exit Sub
    End If

    Dim dataRow As Long
    dataRow = ActualsDataRowByID(cardId)
    If dataRow = 0 Then
        MsgBox "Actual card ID was not found.", vbExclamation, "Actuals Entry"
        Exit Sub
    End If

    If Not ActualsDataRowIsInCurrentScope(dataRow) Then
        MsgBox "Selected actual card is outside the current ActualsConfig included row set.", vbExclamation, "Actuals Entry"
        Exit Sub
    End If

    PopulateEntryFromActualCard dataRow
    MsgBox "Actual card loaded.", vbInformation, "Actuals Entry"
End Sub

Public Sub SaveActualCardChanges()
    Dim cardId As String
    cardId = Trim$(CStr(EntryRange("ActualsEntrySelectedActualCardID").Value))

    If cardId = "" Then
        MsgBox "Selected actual card ID is required.", vbExclamation, "Actuals Entry"
        Exit Sub
    End If

    Dim dataRow As Long
    dataRow = ActualsDataRowByID(cardId)
    If dataRow = 0 Then
        MsgBox "Actual card ID was not found.", vbExclamation, "Actuals Entry"
        Exit Sub
    End If

    If Not ActualsDataRowIsInCurrentScope(dataRow) Then
        MsgBox "Selected actual card is outside the current ActualsConfig included row set.", vbExclamation, "Actuals Entry"
        Exit Sub
    End If

    Dim productionOrder As String
    Dim databaseRow As Long
    Dim operationCode As String
    Dim operationName As String

    If Not ValidateEntryOrderAndOperation(productionOrder, databaseRow, operationCode, operationName) Then
        Exit Sub
    End If

    If Not ValidateActualEntryCalculations(operationName) Then
        Exit Sub
    End If

    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    If Trim$(CStr(ws.Cells(dataRow, 2).Value)) <> productionOrder _
        Or Trim$(CStr(ws.Cells(dataRow, 5).Value)) <> operationCode Then
        MsgBox "Changing production order or operation would change the actual card ID. Void this card and create a new one instead.", vbExclamation, "Actuals Entry"
        Exit Sub
    End If

    If ActiveActualCardExists(productionOrder, operationCode, cardId) Then
        If MsgBox("Another active actual card already exists for this production order and operation. Save these changes?", vbQuestion + vbYesNo, "Actuals Entry") <> vbYes Then
            Exit Sub
        End If
    End If

    Dim existingVoided As Variant
    Dim existingVoidReason As Variant
    existingVoided = ws.Cells(dataRow, 32).Value
    existingVoidReason = ws.Cells(dataRow, 33).Value

    If Not WriteActualCardRow(dataRow, CStr(ws.Cells(dataRow, 1).Value), productionOrder, databaseRow, operationName, operationCode, CLng(ws.Cells(dataRow, 6).Value), ws.Cells(dataRow, 34).Value, Now) Then
        Exit Sub
    End If
    ws.Cells(dataRow, 32).Value = existingVoided
    ws.Cells(dataRow, 33).Value = existingVoidReason
    ListActualCardsForOrder productionOrder
    MsgBox "Actual card changes saved.", vbInformation, "Actuals Entry"
End Sub

Public Sub VoidSelectedActualCard()
    Dim cardId As String
    cardId = Trim$(CStr(EntryRange("ActualsEntrySelectedActualCardID").Value))

    If cardId = "" Then
        MsgBox "Selected actual card ID is required.", vbExclamation, "Actuals Entry"
        Exit Sub
    End If

    Dim dataRow As Long
    dataRow = ActualsDataRowByID(cardId)
    If dataRow = 0 Then
        MsgBox "Actual card ID was not found.", vbExclamation, "Actuals Entry"
        Exit Sub
    End If

    If Not ActualsDataRowIsInCurrentScope(dataRow) Then
        MsgBox "Selected actual card is outside the current ActualsConfig included row set.", vbExclamation, "Actuals Entry"
        Exit Sub
    End If

    If MsgBox("Void selected actual card ID " & cardId & "?", vbQuestion + vbYesNo, "Actuals Entry") <> vbYes Then
        Exit Sub
    End If

    Dim voidReason As String
    voidReason = InputBox("Void reason (optional):", "Actuals Entry")

    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)
    ws.Cells(dataRow, 32).Value = "Yes"
    ws.Cells(dataRow, 33).Value = voidReason
    ws.Cells(dataRow, 35).Value = Now

    Dim productionOrder As String
    productionOrder = Trim$(CStr(ws.Cells(dataRow, 2).Value))
    ClearEntryFieldsOnly
    EntryRange("ActualsEntryProductionOrder").Value = productionOrder
    If productionOrder <> "" Then
        ListActualCardsForOrder productionOrder
    Else
        ClearActualsCardList
    End If

    MsgBox "Actual card voided.", vbInformation, "Actuals Entry"
End Sub

Private Sub ClearEntryFieldsOnly()
    Dim fieldNames As Variant
    fieldNames = Array( _
        "ActualsEntryProductionOrder", "ActualsEntryDatabaseRow", "ActualsEntryOperation", _
        "ActualsEntryCurrentStatus", "ActualsEntryCustomer", "ActualsEntryProductType", _
        "ActualsEntryExpectedOperations", "ActualsEntryProducesFinishedProduct", _
        "ActualsEntryStartDate", "ActualsEntryStartTime", "ActualsEntryStopDate", _
        "ActualsEntryStopTime", "ActualsEntryPauseMinutes", "ActualsEntryExtraMinutes", _
        "ActualsEntryTotalMinutesOverride", "ActualsEntryOverrideReason", _
        "ActualsEntryGrossKg", "ActualsEntryTareCount", "ActualsEntryTareWeightKg", _
        "ActualsEntryManualNetKgOverride", "ActualsEntryWasteKg", "ActualsEntryMetersProduced", _
        "ActualsEntryUnits", "ActualsEntryPPFilmMaterial", "ActualsEntryPPFilmQuantityKg", _
        "ActualsEntryNotes", "ActualsEntrySelectedActualCardID" _
    )

    Dim fieldName As Variant
    For Each fieldName In fieldNames
        EntryRange(CStr(fieldName)).ClearContents
    Next fieldName
End Sub

Private Sub ClearActualsCardList()
    ThisWorkbook.Worksheets(ENTRY_SHEET_NAME).Range("D4:K2000").ClearContents
End Sub

Private Function ValidateEntryOrderAndOperation(ByRef productionOrder As String, ByRef databaseRow As Long, ByRef operationCode As String, ByRef operationName As String) As Boolean
    productionOrder = Trim$(CStr(EntryRange("ActualsEntryProductionOrder").Value))
    If productionOrder = "" Then
        MsgBox "Production order is required.", vbExclamation, "Actuals Entry"
        Exit Function
    End If

    databaseRow = SingleIncludedDatabaseRowForOrder(productionOrder)
    If databaseRow = 0 Then
        Exit Function
    End If

    operationCode = OperationCodeForInput(Trim$(CStr(EntryRange("ActualsEntryOperation").Value)))
    If operationCode = "" Then
        MsgBox "Select a valid operation.", vbExclamation, "Actuals Entry"
        Exit Function
    End If

    If Not OrderExpectsOperation(databaseRow, operationCode) Then
        MsgBox "The selected operation is not expected for this production order.", vbExclamation, "Actuals Entry"
        Exit Function
    End If

    operationName = OperationNameForCode(operationCode)
    PopulateOrderContext productionOrder, databaseRow
    ValidateEntryOrderAndOperation = True
End Function

Private Function SingleIncludedDatabaseRowForOrder(ByVal productionOrder As String) As Long
    Dim matchingRows As Collection
    Set matchingRows = IncludedDatabaseRowsForOrder(productionOrder)

    If matchingRows.Count = 0 Then
        MsgBox "No included Database row exists for production order " & productionOrder & ".", vbExclamation, "Actuals Entry"
        Exit Function
    End If

    If matchingRows.Count > 1 Then
        MsgBox "More than one included Database row exists for production order " & productionOrder & ". Load/save is blocked because the order is ambiguous.", vbExclamation, "Actuals Entry"
        Exit Function
    End If

    SingleIncludedDatabaseRowForOrder = CLng(matchingRows(1))
End Function

Private Function IncludedDatabaseRowsForOrder(ByVal productionOrder As String) As Collection
    Dim matchingRows As Collection
    Set matchingRows = New Collection

    Dim inclusions As Object
    Set inclusions = LoadExplicitInclusions()

    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATABASE_SHEET_NAME)

    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row

    Dim rowNumber As Long
    Dim rowProductionOrder As String
    For rowNumber = 5 To lastRow
        rowProductionOrder = Trim$(CStr(ws.Cells(rowNumber, 1).Value))
        If rowProductionOrder = productionOrder Then
            If RowIsInActualsScope(rowNumber, rowProductionOrder, inclusions) Then
                matchingRows.Add rowNumber
            End If
        End If
    Next rowNumber

    Set IncludedDatabaseRowsForOrder = matchingRows
End Function

Private Sub PopulateOrderContext(ByVal productionOrder As String, ByVal databaseRow As Long)
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATABASE_SHEET_NAME)

    EntryRange("ActualsEntryDatabaseRow").Value = databaseRow
    EntryRange("ActualsEntryCurrentStatus").Value = ProductionOrderStatus(productionOrder)
    EntryRange("ActualsEntryCustomer").Value = ws.Cells(databaseRow, 4).Value
    EntryRange("ActualsEntryProductType").Value = ws.Cells(databaseRow, 6).Value
    EntryRange("ActualsEntryExpectedOperations").Value = ExpectedOperationsForDatabaseRow(databaseRow)
End Sub

Private Function ProductionOrderStatus(ByVal productionOrder As String) As String
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(STATUS_SHEET_NAME)

    Dim rowNumber As Long
    For rowNumber = 2 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If Trim$(CStr(ws.Cells(rowNumber, 1).Value)) = productionOrder Then
            ProductionOrderStatus = Trim$(CStr(ws.Cells(rowNumber, 2).Value))
            If ProductionOrderStatus = "" Then
                ProductionOrderStatus = "Planned"
            End If
            Exit Function
        End If
    Next rowNumber

    ProductionOrderStatus = "Planned"
End Function

Private Function ExpectedOperationsForDatabaseRow(ByVal databaseRow As Long) As String
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)

    Dim parts As Collection
    Set parts = New Collection

    Dim rowNumber As Long
    For rowNumber = 11 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If Trim$(CStr(ws.Cells(rowNumber, 1).Value)) = "" Then
            Exit For
        End If

        If OrderExpectsOperation(databaseRow, Trim$(CStr(ws.Cells(rowNumber, 1).Value))) Then
            parts.Add CStr(ws.Cells(rowNumber, 2).Value)
        End If
    Next rowNumber

    ExpectedOperationsForDatabaseRow = JoinCollection(parts, ", ")
End Function

Private Function ExpectedOperationCodesForDatabaseRow(ByVal databaseRow As Long) As Collection
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)

    Dim codes As Collection
    Set codes = New Collection

    Dim rowNumber As Long
    For rowNumber = 11 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        Dim operationCode As String
        operationCode = Trim$(CStr(ws.Cells(rowNumber, 1).Value))
        If operationCode = "" Then
            Exit For
        End If

        If OrderExpectsOperation(databaseRow, operationCode) Then
            codes.Add operationCode
        End If
    Next rowNumber

    Set ExpectedOperationCodesForDatabaseRow = codes
End Function

Private Function JoinCollection(ByVal values As Collection, ByVal delimiter As String) As String
    Dim result As String
    Dim index As Long

    For index = 1 To values.Count
        If result <> "" Then
            result = result & delimiter
        End If
        result = result & CStr(values(index))
    Next index

    JoinCollection = result
End Function

Private Function OperationFlagIsYes(ByVal flagValue As Variant) As Boolean
    OperationFlagIsYes = LCase$(Trim$(CStr(flagValue))) = "да"
End Function

Private Function OrderExpectsOperation(ByVal databaseRow As Long, ByVal operationCode As String) As Boolean
    Dim flagColumn As String
    flagColumn = OperationFlagColumnForCode(operationCode)
    If flagColumn = "" Then
        Exit Function
    End If

    OrderExpectsOperation = OperationFlagIsYes(ThisWorkbook.Worksheets(DATABASE_SHEET_NAME).Range(flagColumn & CStr(databaseRow)).Value)
End Function

Private Function OperationCodeForInput(ByVal operationInput As String) As String
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)

    Dim normalizedInput As String
    normalizedInput = LCase$(Trim$(operationInput))

    Dim rowNumber As Long
    For rowNumber = 11 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If Trim$(CStr(ws.Cells(rowNumber, 1).Value)) = "" Then
            Exit For
        End If

        If normalizedInput = LCase$(Trim$(CStr(ws.Cells(rowNumber, 1).Value))) _
            Or normalizedInput = LCase$(Trim$(CStr(ws.Cells(rowNumber, 2).Value))) Then
            OperationCodeForInput = Trim$(CStr(ws.Cells(rowNumber, 1).Value))
            Exit Function
        End If
    Next rowNumber
End Function

Private Function OperationNameForCode(ByVal operationCode As String) As String
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)

    Dim rowNumber As Long
    For rowNumber = 11 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If Trim$(CStr(ws.Cells(rowNumber, 1).Value)) = "" Then
            Exit For
        End If

        If LCase$(Trim$(CStr(ws.Cells(rowNumber, 1).Value))) = LCase$(Trim$(operationCode)) Then
            OperationNameForCode = Trim$(CStr(ws.Cells(rowNumber, 2).Value))
            Exit Function
        End If
    Next rowNumber
End Function

Private Function OperationFlagColumnForCode(ByVal operationCode As String) As String
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)

    Dim rowNumber As Long
    For rowNumber = 11 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If Trim$(CStr(ws.Cells(rowNumber, 1).Value)) = "" Then
            Exit For
        End If

        If LCase$(Trim$(CStr(ws.Cells(rowNumber, 1).Value))) = LCase$(Trim$(operationCode)) Then
            OperationFlagColumnForCode = Trim$(CStr(ws.Cells(rowNumber, 3).Value))
            Exit Function
        End If
    Next rowNumber
End Function

Private Function NextActualsDataRow() As Long
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    NextActualsDataRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row + 1
    If NextActualsDataRow < 2 Then
        NextActualsDataRow = 2
    End If
End Function

Private Function NextActualCardNumber(ByVal productionOrder As String, ByVal operationCode As String) As Long
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    Dim maxCardNumber As Long
    Dim rowNumber As Long
    For rowNumber = 2 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If Trim$(CStr(ws.Cells(rowNumber, 2).Value)) = productionOrder _
            And Trim$(CStr(ws.Cells(rowNumber, 5).Value)) = operationCode Then
            If IsNumeric(ws.Cells(rowNumber, 6).Value) Then
                If CLng(ws.Cells(rowNumber, 6).Value) > maxCardNumber Then
                    maxCardNumber = CLng(ws.Cells(rowNumber, 6).Value)
                End If
            End If
        End If
    Next rowNumber

    NextActualCardNumber = maxCardNumber + 1
End Function

Private Function ActualCardID(ByVal productionOrder As String, ByVal operationCode As String, ByVal cardNumber As Long) As String
    ActualCardID = "PO" & Trim$(productionOrder) & "-" & Trim$(operationCode) & "-" & CStr(cardNumber)
End Function

Private Function WriteActualCardRow(ByVal dataRow As Long, ByVal cardId As String, ByVal productionOrder As String, ByVal databaseRow As Long, ByVal operationName As String, ByVal operationCode As String, ByVal cardNumber As Long, ByVal createdAt As Variant, ByVal updatedAt As Variant) As Boolean
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    Dim startAt As Variant
    Dim stopAt As Variant
    Dim pauseMinutes As Double
    Dim extraMinutes As Double
    Dim calculatedTotalMinutes As Variant
    Dim totalMinutesOverride As Variant
    Dim totalMinutes As Variant
    Dim grossKg As Double
    Dim tareCount As Double
    Dim tareWeightKg As Double
    Dim calculatedNetKgValue As Double
    Dim manualNetKgOverride As Variant
    Dim netKg As Variant

    If Not BuildActualEntryCalculations(operationName, startAt, stopAt, pauseMinutes, extraMinutes, calculatedTotalMinutes, totalMinutesOverride, totalMinutes, grossKg, tareCount, tareWeightKg, calculatedNetKgValue, manualNetKgOverride, netKg) Then
        Exit Function
    End If

    ws.Cells(dataRow, 1).Value = cardId
    ws.Cells(dataRow, 2).Value = productionOrder
    ws.Cells(dataRow, 3).Value = databaseRow
    ws.Cells(dataRow, 4).Value = operationName
    ws.Cells(dataRow, 5).Value = operationCode
    ws.Cells(dataRow, 6).Value = cardNumber
    ws.Cells(dataRow, 7).Value = EntryRangeValue("ActualsEntryProducesFinishedProduct")
    ws.Cells(dataRow, 8).Value = EntryRangeValue("ActualsEntryStartDate")
    ws.Cells(dataRow, 9).Value = EntryRangeValue("ActualsEntryStartTime")
    ws.Cells(dataRow, 10).Value = EntryRangeValue("ActualsEntryStopDate")
    ws.Cells(dataRow, 11).Value = EntryRangeValue("ActualsEntryStopTime")
    ws.Cells(dataRow, 12).Value = startAt
    ws.Cells(dataRow, 13).Value = stopAt
    ws.Cells(dataRow, 14).Value = NumericEntryValueForStorage("ActualsEntryPauseMinutes", pauseMinutes)
    ws.Cells(dataRow, 15).Value = NumericEntryValueForStorage("ActualsEntryExtraMinutes", extraMinutes)
    ws.Cells(dataRow, 16).Value = calculatedTotalMinutes
    ws.Cells(dataRow, 17).Value = totalMinutesOverride
    ws.Cells(dataRow, 18).Value = EntryRangeValue("ActualsEntryOverrideReason")
    ws.Cells(dataRow, 19).Value = totalMinutes
    ws.Cells(dataRow, 20).Value = NumericEntryValueForStorage("ActualsEntryGrossKg", grossKg)
    ws.Cells(dataRow, 21).Value = NumericEntryValueForStorage("ActualsEntryTareCount", tareCount)
    ws.Cells(dataRow, 22).Value = NumericEntryValueForStorage("ActualsEntryTareWeightKg", tareWeightKg)
    ws.Cells(dataRow, 23).Value = calculatedNetKgValue
    ws.Cells(dataRow, 24).Value = manualNetKgOverride
    ws.Cells(dataRow, 25).Value = netKg
    ws.Cells(dataRow, 26).Value = NumericEntryValueForStorage("ActualsEntryWasteKg", 0)
    ws.Cells(dataRow, 27).Value = NumericEntryValueForStorage("ActualsEntryMetersProduced", 0)
    ws.Cells(dataRow, 28).Value = NumericEntryValueForStorage("ActualsEntryUnits", 0)
    ws.Cells(dataRow, 29).Value = EntryRangeValue("ActualsEntryPPFilmMaterial")
    ws.Cells(dataRow, 30).Value = NumericEntryValueForStorage("ActualsEntryPPFilmQuantityKg", 0)
    ws.Cells(dataRow, 31).Value = EntryRangeValue("ActualsEntryNotes")
    ws.Cells(dataRow, 32).Value = "No"
    ws.Cells(dataRow, 33).Value = vbNullString
    ws.Cells(dataRow, 34).Value = createdAt
    ws.Cells(dataRow, 35).Value = updatedAt
    WriteActualCardRow = True
End Function

Private Function EntryRangeValue(ByVal rangeName As String) As Variant
    EntryRangeValue = EntryRange(rangeName).Value
End Function

Private Function ValidateActualEntryCalculations(ByVal operationName As String) As Boolean
    Dim startAt As Variant
    Dim stopAt As Variant
    Dim pauseMinutes As Double
    Dim extraMinutes As Double
    Dim calculatedTotalMinutes As Variant
    Dim totalMinutesOverride As Variant
    Dim totalMinutes As Variant
    Dim grossKg As Double
    Dim tareCount As Double
    Dim tareWeightKg As Double
    Dim calculatedNetKgValue As Double
    Dim manualNetKgOverride As Variant
    Dim netKg As Variant

    ValidateActualEntryCalculations = BuildActualEntryCalculations(operationName, startAt, stopAt, pauseMinutes, extraMinutes, calculatedTotalMinutes, totalMinutesOverride, totalMinutes, grossKg, tareCount, tareWeightKg, calculatedNetKgValue, manualNetKgOverride, netKg)
End Function

Private Function BuildActualEntryCalculations(ByVal operationName As String, ByRef startAt As Variant, ByRef stopAt As Variant, ByRef pauseMinutes As Double, ByRef extraMinutes As Double, ByRef calculatedTotalMinutes As Variant, ByRef totalMinutesOverride As Variant, ByRef totalMinutes As Variant, ByRef grossKg As Double, ByRef tareCount As Double, ByRef tareWeightKg As Double, ByRef calculatedNetKgValue As Double, ByRef manualNetKgOverride As Variant, ByRef netKg As Variant) As Boolean
    Dim parsedTotalMinutesOverride As Double
    Dim parsedManualNetKgOverride As Double
    Dim ignoredNumber As Double

    If Not ValidateNonNegativeEntryField("ActualsEntryPauseMinutes", "Pause minutes", pauseMinutes) Then Exit Function
    If Not ValidateNonNegativeEntryField("ActualsEntryExtraMinutes", "Extra minutes", extraMinutes) Then Exit Function
    If Not ValidateNonNegativeEntryField("ActualsEntryTotalMinutesOverride", "Total minutes override", parsedTotalMinutesOverride) Then Exit Function
    If Not ValidateNonNegativeEntryField("ActualsEntryGrossKg", "Gross kg", grossKg) Then Exit Function
    If Not ValidateNonNegativeEntryField("ActualsEntryTareCount", "Tare count", tareCount) Then Exit Function
    If Not ValidateNonNegativeEntryField("ActualsEntryTareWeightKg", "Tare weight kg", tareWeightKg) Then Exit Function
    If Not ValidateNonNegativeEntryField("ActualsEntryManualNetKgOverride", "Manual net kg override", parsedManualNetKgOverride) Then Exit Function
    If Not ValidateNonNegativeEntryField("ActualsEntryWasteKg", "Waste kg", ignoredNumber) Then Exit Function
    If Not ValidateNonNegativeEntryField("ActualsEntryMetersProduced", "Meters produced", ignoredNumber) Then Exit Function
    If Not ValidateNonNegativeEntryField("ActualsEntryUnits", "Units", ignoredNumber) Then Exit Function
    If Not ValidateNonNegativeEntryField("ActualsEntryPPFilmQuantityKg", "PP film quantity kg", ignoredNumber) Then Exit Function

    Dim totalMinutesOverrideEntered As Boolean
    totalMinutesOverrideEntered = EntryRangeHasValue("ActualsEntryTotalMinutesOverride")
    If totalMinutesOverrideEntered Then
        totalMinutesOverride = parsedTotalMinutesOverride
        If Len(Trim$(CStr(EntryRangeValue("ActualsEntryOverrideReason")))) = 0 Then
            MsgBox "Total minutes override requires a reason.", vbExclamation, "Actuals Entry"
            Exit Function
        End If
    Else
        totalMinutesOverride = vbNullString
    End If

    Dim manualNetKgOverrideEntered As Boolean
    manualNetKgOverrideEntered = EntryRangeHasValue("ActualsEntryManualNetKgOverride")
    If manualNetKgOverrideEntered Then
        manualNetKgOverride = parsedManualNetKgOverride
    Else
        manualNetKgOverride = vbNullString
    End If

    Dim hasStartAt As Boolean
    Dim hasStopAt As Boolean
    If Not CombineEntryDateTime("ActualsEntryStartDate", "ActualsEntryStartTime", "Start", startAt, hasStartAt) Then Exit Function
    If Not CombineEntryDateTime("ActualsEntryStopDate", "ActualsEntryStopTime", "Stop", stopAt, hasStopAt) Then Exit Function

    calculatedTotalMinutes = vbNullString
    totalMinutes = vbNullString
    If hasStartAt And hasStopAt Then
        If CDate(stopAt) < CDate(startAt) Then
            MsgBox "Stop datetime cannot be before start datetime.", vbExclamation, "Actuals Entry"
            Exit Function
        End If

        Dim calculatedTotalMinutesValue As Double
        Dim workingMinutesError As String
        If Not TotalMinutesForOperation(operationName, CDate(startAt), CDate(stopAt), pauseMinutes, extraMinutes, calculatedTotalMinutesValue, workingMinutesError) Then
            MsgBox workingMinutesError, vbExclamation, "Actuals Entry"
            Exit Function
        End If

        If calculatedTotalMinutesValue < 0 Then
            MsgBox "Calculated total minutes cannot be negative. Check start/stop time and pause minutes.", vbExclamation, "Actuals Entry"
            Exit Function
        End If

        calculatedTotalMinutes = calculatedTotalMinutesValue
        totalMinutes = calculatedTotalMinutes
    End If

    If totalMinutesOverrideEntered Then
        totalMinutes = totalMinutesOverride
    End If

    calculatedNetKgValue = CalculatedNetKg(grossKg, tareCount, tareWeightKg)
    If calculatedNetKgValue < 0 Then
        MsgBox "Calculated net kg cannot be negative. Check gross kg, tare count, and tare weight kg.", vbExclamation, "Actuals Entry"
        Exit Function
    End If

    netKg = calculatedNetKgValue
    If manualNetKgOverrideEntered Then
        netKg = manualNetKgOverride
    End If

    BuildActualEntryCalculations = True
End Function

Private Function ValidateNonNegativeEntryField(ByVal rangeName As String, ByVal fieldLabel As String, ByRef parsedNumber As Double) As Boolean
    If TryParseNonNegativeNumber(EntryRangeValue(rangeName), parsedNumber) Then
        ValidateNonNegativeEntryField = True
        Exit Function
    End If

    MsgBox fieldLabel & " must be numeric and non-negative when entered.", vbExclamation, "Actuals Entry"
End Function

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

Private Function NumericEntryValueForStorage(ByVal rangeName As String, ByVal defaultValue As Double) As Variant
    Dim parsedNumber As Double
    If Len(Trim$(CStr(EntryRangeValue(rangeName)))) = 0 Then
        NumericEntryValueForStorage = vbNullString
        Exit Function
    End If

    If TryParseNonNegativeNumber(EntryRangeValue(rangeName), parsedNumber) Then
        NumericEntryValueForStorage = parsedNumber
    Else
        NumericEntryValueForStorage = defaultValue
    End If
End Function

Private Function EntryRangeHasValue(ByVal rangeName As String) As Boolean
    EntryRangeHasValue = Len(Trim$(CStr(EntryRangeValue(rangeName)))) > 0
End Function

Private Function CombineEntryDateTime(ByVal dateRangeName As String, ByVal timeRangeName As String, ByVal fieldLabel As String, ByRef normalizedDateTime As Variant, ByRef hasDateTime As Boolean) As Boolean
    Dim rawDate As Variant
    Dim rawTime As Variant
    rawDate = EntryRangeValue(dateRangeName)
    rawTime = EntryRangeValue(timeRangeName)

    Dim hasDate As Boolean
    Dim hasTime As Boolean
    hasDate = Len(Trim$(CStr(rawDate))) > 0
    hasTime = Len(Trim$(CStr(rawTime))) > 0

    If Not hasDate And Not hasTime Then
        normalizedDateTime = vbNullString
        hasDateTime = False
        CombineEntryDateTime = True
        Exit Function
    End If

    If Not hasDate Or Not hasTime Or Not IsDate(rawDate) Or Not IsDate(rawTime) Then
        MsgBox fieldLabel & " date and time must both be valid when either is entered.", vbExclamation, "Actuals Entry"
        Exit Function
    End If

    normalizedDateTime = DateValue(CDate(rawDate)) + TimeValue(CDate(rawTime))
    hasDateTime = True
    CombineEntryDateTime = True
End Function

Private Function CalculatedNetKg(ByVal grossKg As Double, ByVal tareCount As Double, ByVal tareWeightKg As Double) As Double
    CalculatedNetKg = grossKg - (tareCount * tareWeightKg)
End Function

Private Function TotalMinutesForOperation(ByVal operationName As String, ByVal startAt As Date, ByVal stopAt As Date, ByVal pauseMinutes As Double, ByVal extraMinutes As Double, ByRef totalOperationMinutes As Double, ByRef workingMinutesError As String) As Boolean
    If operationName = "Extrusion" Then
        totalOperationMinutes = DateDiff("n", startAt, stopAt) - pauseMinutes
    Else
        Dim workingMinutes As Double
        If Not WorkingMinutesBetween(startAt, stopAt, workingMinutes, workingMinutesError) Then
            Exit Function
        End If

        totalOperationMinutes = workingMinutes - pauseMinutes + extraMinutes
    End If

    TotalMinutesForOperation = True
End Function

Private Function WorkingMinutesBetween(ByVal startAt As Date, ByVal stopAt As Date, ByRef totalWorkingMinutes As Double, ByRef workingMinutesError As String) As Boolean
    Dim workDate As Date
    workDate = DateValue(startAt)

    Do While workDate <= DateValue(stopAt)
        Dim workStart As Date
        Dim workStop As Date
        Dim hasWorkingWindow As Boolean

        If Not WorkingWindowForDate(workDate, workStart, workStop, hasWorkingWindow, workingMinutesError) Then
            Exit Function
        End If

        If hasWorkingWindow Then
            Dim segmentStart As Date
            Dim segmentStop As Date
            segmentStart = workStart
            segmentStop = workStop

            If DateValue(startAt) = workDate And startAt > segmentStart Then
                segmentStart = startAt
            End If

            If DateValue(stopAt) = workDate And stopAt < segmentStop Then
                segmentStop = stopAt
            End If

            If segmentStop > segmentStart Then
                totalWorkingMinutes = totalWorkingMinutes + DateDiff("n", segmentStart, segmentStop)
            End If
        End If

        workDate = DateAdd("d", 1, workDate)
    Loop

    WorkingMinutesBetween = True
End Function

Private Function WorkingWindowForDate(ByVal workDate As Date, ByRef workStart As Date, ByRef workStop As Date, ByRef hasWorkingWindow As Boolean, ByRef workingMinutesError As String) As Boolean
    hasWorkingWindow = DefaultWorkingDayMinutes(workDate) > 0
    If hasWorkingWindow Then
        workStart = workDate + DefaultWorkStartTime()
        workStop = workDate + DefaultWorkStopTime()
    End If

    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(CONFIG_SHEET_NAME)

    Dim rowNumber As Long
    For rowNumber = 26 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        Dim rowType As String
        rowType = LCase$(Trim$(CStr(ws.Cells(rowNumber, 1).Value)))

        If (rowType = "workday" Or rowType = "nonworkingday") _
            And CalendarRowMatchesDate(ws.Cells(rowNumber, 2).Value, workDate) Then
            If rowType = "nonworkingday" Then
                hasWorkingWindow = False
                WorkingWindowForDate = True
                Exit Function
            End If

            If Not IsDate(ws.Cells(rowNumber, 3).Value) Or Not IsDate(ws.Cells(rowNumber, 4).Value) Then
                workingMinutesError = "Malformed ActualsConfig WorkingCalendar row " & CStr(rowNumber) & ": Workday rows require valid StartTime and StopTime."
                Exit Function
            End If

            workStart = workDate + TimeValue(CDate(ws.Cells(rowNumber, 3).Value))
            workStop = workDate + TimeValue(CDate(ws.Cells(rowNumber, 4).Value))
            If workStop <= workStart Then
                workingMinutesError = "Malformed ActualsConfig WorkingCalendar row " & CStr(rowNumber) & ": StopTime must be later than StartTime."
                Exit Function
            End If

            hasWorkingWindow = True
            WorkingWindowForDate = True
            Exit Function
        End If
    Next rowNumber

    WorkingWindowForDate = True
End Function

Private Function DefaultWorkingDayMinutes(ByVal workDate As Date) As Double
    If Weekday(workDate, vbMonday) <= 5 Then
        DefaultWorkingDayMinutes = DateDiff("n", DefaultWorkStartTime(), DefaultWorkStopTime())
    End If
End Function

Private Function DefaultWorkStartTime() As Date
    DefaultWorkStartTime = TimeSerial(8, 0, 0)
End Function

Private Function DefaultWorkStopTime() As Date
    DefaultWorkStopTime = TimeSerial(17, 0, 0)
End Function

Private Function CalendarRowMatchesDate(ByVal matchValue As Variant, ByVal workDate As Date) As Boolean
    Dim matchText As String
    matchText = LCase$(Trim$(CStr(matchValue)))
    If matchText = "" Then
        Exit Function
    End If

    If IsNumeric(matchValue) Then
        CalendarRowMatchesDate = CLng(matchValue) = Weekday(workDate, vbMonday)
        Exit Function
    End If

    Select Case matchText
        Case "monday", "mon"
            CalendarRowMatchesDate = Weekday(workDate, vbMonday) = 1
        Case "tuesday", "tue"
            CalendarRowMatchesDate = Weekday(workDate, vbMonday) = 2
        Case "wednesday", "wed"
            CalendarRowMatchesDate = Weekday(workDate, vbMonday) = 3
        Case "thursday", "thu"
            CalendarRowMatchesDate = Weekday(workDate, vbMonday) = 4
        Case "friday", "fri"
            CalendarRowMatchesDate = Weekday(workDate, vbMonday) = 5
        Case "saturday", "sat"
            CalendarRowMatchesDate = Weekday(workDate, vbMonday) = 6
        Case "sunday", "sun"
            CalendarRowMatchesDate = Weekday(workDate, vbMonday) = 7
        Case Else
            If IsDate(matchValue) Then
                CalendarRowMatchesDate = DateValue(CDate(matchValue)) = workDate
            End If
    End Select
End Function

Private Function ActualsDataRowByID(ByVal cardId As String) As Long
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    Dim rowNumber As Long
    For rowNumber = 2 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If Trim$(CStr(ws.Cells(rowNumber, 1).Value)) = cardId Then
            ActualsDataRowByID = rowNumber
            Exit Function
        End If
    Next rowNumber
End Function

Private Function ActualsDataRowIsInCurrentScope(ByVal dataRow As Long) As Boolean
    Dim dataWs As Worksheet
    Set dataWs = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    Dim productionOrder As String
    productionOrder = Trim$(CStr(dataWs.Cells(dataRow, 2).Value))
    If productionOrder = "" Then
        Exit Function
    End If

    Dim databaseRowText As String
    databaseRowText = Trim$(CStr(dataWs.Cells(dataRow, 3).Value))
    If Not ConfigRowNumberIsValid(databaseRowText) Then
        Exit Function
    End If

    Dim databaseRow As Long
    databaseRow = CLng(databaseRowText)

    Dim databaseWs As Worksheet
    Set databaseWs = ThisWorkbook.Worksheets(DATABASE_SHEET_NAME)
    If Trim$(CStr(databaseWs.Cells(databaseRow, 1).Value)) <> productionOrder Then
        Exit Function
    End If

    ActualsDataRowIsInCurrentScope = RowIsInActualsScope(databaseRow, productionOrder, LoadExplicitInclusions())
End Function

Private Function ActiveActualCardExists(ByVal productionOrder As String, ByVal operationCode As String, ByVal excludedCardId As String) As Boolean
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    Dim rowNumber As Long
    For rowNumber = 2 To ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
        If Trim$(CStr(ws.Cells(rowNumber, 2).Value)) = productionOrder _
            And Trim$(CStr(ws.Cells(rowNumber, 5).Value)) = operationCode _
            And Not ActualCardIsVoided(rowNumber) _
            And ActualsDataRowIsInCurrentScope(rowNumber) _
            And Trim$(CStr(ws.Cells(rowNumber, 1).Value)) <> excludedCardId Then
            ActiveActualCardExists = True
            Exit Function
        End If
    Next rowNumber
End Function

Private Function ActualCardIsVoided(ByVal dataRow As Long) As Boolean
    ActualCardIsVoided = LCase$(Trim$(CStr(ThisWorkbook.Worksheets(DATA_SHEET_NAME).Cells(dataRow, 32).Value))) = "yes"
End Function

Private Function ActualCardIsActive(ByVal dataRow As Long) As Boolean
    ActualCardIsActive = Not ActualCardIsVoided(dataRow)
End Function

Private Function ActualCardHasRequiredTimeFields(ByVal dataRow As Long) As Boolean
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    ActualCardHasRequiredTimeFields = Len(Trim$(CStr(ws.Cells(dataRow, 8).Value))) > 0 _
        And Len(Trim$(CStr(ws.Cells(dataRow, 9).Value))) > 0 _
        And Len(Trim$(CStr(ws.Cells(dataRow, 10).Value))) > 0 _
        And Len(Trim$(CStr(ws.Cells(dataRow, 11).Value))) > 0 _
        And IsDate(ws.Cells(dataRow, 12).Value) _
        And IsDate(ws.Cells(dataRow, 13).Value)
End Function

Private Function ActualCardNumericFieldsAreNonNegative(ByVal dataRow As Long) As Boolean
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    Dim columnNumber As Variant
    For Each columnNumber In Array(14, 15, 16, 17, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 30)
        If Not CellIsBlankOrNonNegativeNumber(ws.Cells(dataRow, CLng(columnNumber)).Value) Then
            Exit Function
        End If
    Next columnNumber

    ActualCardNumericFieldsAreNonNegative = True
End Function

Private Function CellIsBlankOrNonNegativeNumber(ByVal value As Variant) As Boolean
    If Len(Trim$(CStr(value))) = 0 Then
        CellIsBlankOrNonNegativeNumber = True
        Exit Function
    End If

    If Not IsNumeric(value) Then
        Exit Function
    End If

    CellIsBlankOrNonNegativeNumber = CDbl(value) >= 0
End Function

Private Function ActualCardPPFilmFieldsArePaired(ByVal dataRow As Long) As Boolean
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    Dim hasMaterial As Boolean
    Dim hasQuantity As Boolean
    hasMaterial = Len(Trim$(CStr(ws.Cells(dataRow, 29).Value))) > 0
    hasQuantity = Len(Trim$(CStr(ws.Cells(dataRow, 30).Value))) > 0

    ActualCardPPFilmFieldsArePaired = (hasMaterial And hasQuantity) Or (Not hasMaterial And Not hasQuantity)
End Function

Private Function CellHasPositiveNumericValue(ByVal value As Variant) As Boolean
    If Not IsNumeric(value) Then
        Exit Function
    End If

    CellHasPositiveNumericValue = CDbl(value) > 0
End Function

Private Sub ListActualCardsForOrder(ByVal productionOrder As String)
    ClearActualsCardList

    Dim dataWs As Worksheet
    Set dataWs = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    Dim entryWs As Worksheet
    Set entryWs = ThisWorkbook.Worksheets(ENTRY_SHEET_NAME)

    Dim outputRow As Long
    outputRow = 4

    Dim rowNumber As Long
    For rowNumber = 2 To dataWs.Cells(dataWs.Rows.Count, 1).End(xlUp).Row
        If Trim$(CStr(dataWs.Cells(rowNumber, 2).Value)) = productionOrder _
            And ActualsDataRowIsInCurrentScope(rowNumber) _
            And Not ActualCardIsVoided(rowNumber) Then
            entryWs.Cells(outputRow, 4).Value = dataWs.Cells(rowNumber, 1).Value
            entryWs.Cells(outputRow, 5).Value = dataWs.Cells(rowNumber, 6).Value
            entryWs.Cells(outputRow, 6).Value = dataWs.Cells(rowNumber, 4).Value
            entryWs.Cells(outputRow, 7).Value = dataWs.Cells(rowNumber, 8).Value
            entryWs.Cells(outputRow, 8).Value = dataWs.Cells(rowNumber, 10).Value
            entryWs.Cells(outputRow, 9).Value = dataWs.Cells(rowNumber, 19).Value
            entryWs.Cells(outputRow, 10).Value = dataWs.Cells(rowNumber, 20).Value
            entryWs.Cells(outputRow, 11).Value = dataWs.Cells(rowNumber, 35).Value
            outputRow = outputRow + 1
        End If
    Next rowNumber

    If outputRow = 4 Then
        entryWs.Range("D4").Value = "No active saved cards."
    End If
End Sub

Private Sub PopulateEntryFromActualCard(ByVal dataRow As Long)
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Worksheets(DATA_SHEET_NAME)

    ClearEntryFieldsOnly
    EntryRange("ActualsEntrySelectedActualCardID").Value = ws.Cells(dataRow, 1).Value
    EntryRange("ActualsEntryProductionOrder").Value = ws.Cells(dataRow, 2).Value
    EntryRange("ActualsEntryDatabaseRow").Value = ws.Cells(dataRow, 3).Value
    EntryRange("ActualsEntryOperation").Value = ws.Cells(dataRow, 4).Value
    EntryRange("ActualsEntryProducesFinishedProduct").Value = ws.Cells(dataRow, 7).Value
    EntryRange("ActualsEntryStartDate").Value = ws.Cells(dataRow, 8).Value
    EntryRange("ActualsEntryStartTime").Value = ws.Cells(dataRow, 9).Value
    EntryRange("ActualsEntryStopDate").Value = ws.Cells(dataRow, 10).Value
    EntryRange("ActualsEntryStopTime").Value = ws.Cells(dataRow, 11).Value
    EntryRange("ActualsEntryPauseMinutes").Value = ws.Cells(dataRow, 14).Value
    EntryRange("ActualsEntryExtraMinutes").Value = ws.Cells(dataRow, 15).Value
    EntryRange("ActualsEntryTotalMinutesOverride").Value = ws.Cells(dataRow, 17).Value
    EntryRange("ActualsEntryOverrideReason").Value = ws.Cells(dataRow, 18).Value
    EntryRange("ActualsEntryGrossKg").Value = ws.Cells(dataRow, 20).Value
    EntryRange("ActualsEntryTareCount").Value = ws.Cells(dataRow, 21).Value
    EntryRange("ActualsEntryTareWeightKg").Value = ws.Cells(dataRow, 22).Value
    EntryRange("ActualsEntryManualNetKgOverride").Value = ws.Cells(dataRow, 24).Value
    EntryRange("ActualsEntryWasteKg").Value = ws.Cells(dataRow, 26).Value
    EntryRange("ActualsEntryMetersProduced").Value = ws.Cells(dataRow, 27).Value
    EntryRange("ActualsEntryUnits").Value = ws.Cells(dataRow, 28).Value
    EntryRange("ActualsEntryPPFilmMaterial").Value = ws.Cells(dataRow, 29).Value
    EntryRange("ActualsEntryPPFilmQuantityKg").Value = ws.Cells(dataRow, 30).Value
    EntryRange("ActualsEntryNotes").Value = ws.Cells(dataRow, 31).Value

    Dim productionOrder As String
    productionOrder = Trim$(CStr(ws.Cells(dataRow, 2).Value))
    Dim databaseRow As Long
    databaseRow = CLng(ws.Cells(dataRow, 3).Value)
    PopulateOrderContext productionOrder, databaseRow
    ListActualCardsForOrder productionOrder
End Sub
