Attribute VB_Name = "ExportExtrusionOrders"
Option Explicit

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

Public Sub InstallExportValidation()
    Dim workbook As Workbook
    Set workbook = ActiveWorkbook

    Dim errors As Collection
    Set errors = New Collection

    EnsureExportConfigSheet workbook, errors
    EnsureCatalogSheet workbook, PRINTING_CATALOG_SHEET_NAME, Array("Type", "Value", "Notes"), errors
    EnsureCatalogSheet workbook, EXTRUSION_CATALOG_SHEET_NAME, Array("Category", "Producer", "GradeCode", "Notes"), errors

    If errors.Count > 0 Then
        MsgBox "Export validation setup could not finish:" & vbCrLf & JoinCollection(errors, vbCrLf), vbCritical
        Exit Sub
    End If

    MsgBox "Export validation setup is ready.", vbInformation
End Sub

Public Sub ValidateSelectedExportRows()
    Dim workbook As Workbook
    Set workbook = ActiveWorkbook

    Dim shapeErrors As Collection
    Set shapeErrors = New Collection

    Dim wsDatabase As Worksheet
    Dim wsConfig As Worksheet
    Dim wsPrintingCatalog As Worksheet
    Dim wsExtrusionCatalog As Worksheet

    If Not RequiredWorkbookShapeIsValid(workbook, wsDatabase, wsConfig, wsPrintingCatalog, wsExtrusionCatalog, shapeErrors) Then
        MsgBox "Validation could not start:" & vbCrLf & JoinCollection(shapeErrors, vbCrLf), vbCritical
        Exit Sub
    End If

    If ActiveSheet.Name <> DATABASE_SHEET_NAME Then
        MsgBox "Open the Database sheet, select rows to validate, and run the macro again.", vbExclamation
        Exit Sub
    End If

    If TypeName(Selection) <> "Range" Then
        MsgBox "Select one or more rows in Database before validation.", vbExclamation
        Exit Sub
    End If

    Dim targetRows As Collection
    Set targetRows = SelectedProductionRows(wsDatabase, Selection)

    If targetRows.Count = 0 Then
        MsgBox "The selection does not contain production-order rows with order numbers.", vbExclamation
        Exit Sub
    End If

    Dim validationErrors As Collection
    Set validationErrors = New Collection

    Dim checkedOrderCount As Long
    checkedOrderCount = targetRows.Count

    If ValidateRows(wsDatabase, wsPrintingCatalog, wsExtrusionCatalog, targetRows, validationErrors) Then
        MsgBox ValidationPassedMessage(checkedOrderCount), vbInformation
    Else
        MsgBox ValidationFailedMessage(checkedOrderCount, validationErrors), vbExclamation
    End If
End Sub

Public Sub ValidateConfiguredExportRows()
    Dim workbook As Workbook
    Set workbook = ActiveWorkbook

    Dim shapeErrors As Collection
    Set shapeErrors = New Collection

    Dim wsDatabase As Worksheet
    Dim wsConfig As Worksheet
    Dim wsPrintingCatalog As Worksheet
    Dim wsExtrusionCatalog As Worksheet

    If Not RequiredWorkbookShapeIsValid(workbook, wsDatabase, wsConfig, wsPrintingCatalog, wsExtrusionCatalog, shapeErrors) Then
        MsgBox "Validation could not start:" & vbCrLf & JoinCollection(shapeErrors, vbCrLf), vbCritical
        Exit Sub
    End If

    Dim firstRow As Long
    Dim firstRowError As String
    firstRow = FirstValidationRow(wsConfig, firstRowError)
    If firstRow = 0 Then
        MsgBox firstRowError, vbCritical
        Exit Sub
    End If

    Dim targetRows As Collection
    Set targetRows = ConfiguredProductionRows(wsDatabase, firstRow)

    If targetRows.Count = 0 Then
        MsgBox "No production-order rows found from row " & firstRow & " onward.", vbExclamation
        Exit Sub
    End If

    Dim validationErrors As Collection
    Set validationErrors = New Collection

    Dim checkedOrderCount As Long
    checkedOrderCount = targetRows.Count

    If ValidateRows(wsDatabase, wsPrintingCatalog, wsExtrusionCatalog, targetRows, validationErrors) Then
        MsgBox ValidationPassedMessage(checkedOrderCount), vbInformation
    Else
        MsgBox ValidationFailedMessage(checkedOrderCount, validationErrors), vbExclamation
    End If
End Sub

Public Sub ExportSelectedExtrusionOrdersCsv()
    Dim workbook As Workbook
    Set workbook = ActiveWorkbook

    Dim shapeErrors As Collection
    Set shapeErrors = New Collection

    Dim wsDatabase As Worksheet
    Dim wsConfig As Worksheet
    Dim wsPrintingCatalog As Worksheet
    Dim wsExtrusionCatalog As Worksheet

    If Not RequiredWorkbookShapeIsValid(workbook, wsDatabase, wsConfig, wsPrintingCatalog, wsExtrusionCatalog, shapeErrors) Then
        MsgBox "Export could not start:" & vbCrLf & JoinCollection(shapeErrors, vbCrLf), vbCritical
        Exit Sub
    End If

    If ActiveSheet.Name <> DATABASE_SHEET_NAME Then
        MsgBox "Open the Database sheet, select rows to export, and run the macro again.", vbExclamation
        Exit Sub
    End If

    If TypeName(Selection) <> "Range" Then
        MsgBox "Select one or more rows in Database before export.", vbExclamation
        Exit Sub
    End If

    Dim exportRows As Collection
    Set exportRows = SelectedProductionRows(wsDatabase, Selection)

    If exportRows.Count = 0 Then
        MsgBox "The selection does not contain production-order rows with order numbers.", vbExclamation
        Exit Sub
    End If

    Dim validationErrors As Collection
    Set validationErrors = New Collection

    If Not ValidateRows(wsDatabase, wsPrintingCatalog, wsExtrusionCatalog, exportRows, validationErrors) Then
        MsgBox ValidationFailedMessage(exportRows.Count, validationErrors), vbExclamation
        Exit Sub
    End If

    Dim csvText As String
    csvText = BuildCsv(wsDatabase, exportRows)

    Dim exportPath As String
    exportPath = ExportFolderPath(workbook.Path)
    EnsureFolderExists exportPath

    Dim filename As String
    filename = exportPath & "\extrusion_orders_" & Format(Now, "yyyymmdd_hhnnss") & ".csv"
    WriteUtf8TextFile filename, csvText

    MsgBox "Exported production-order rows: " & exportRows.Count & vbCrLf & filename, vbInformation
End Sub

Private Sub EnsureExportConfigSheet(ByVal workbook As Workbook, ByVal errors As Collection)
    Dim ws As Worksheet
    Set ws = EnsureSheet(workbook, CONFIG_SHEET_NAME)

    Dim configHeaderRow As Variant
    configHeaderRow = Array("Setting", "Value", "Notes")

    If HeaderMatches(ws, configHeaderRow) Then
        ' Header already matches.
    ElseIf SheetHasOnlyBlankHeader(ws, UBound(configHeaderRow) - LBound(configHeaderRow) + 1) Then
        WriteHeaders ws, configHeaderRow
    Else
        errors.Add "Sheet " & CONFIG_SHEET_NAME & " has unexpected headers in row 1."
        Exit Sub
    End If

    EnsureConfigSettingRow ws, CONFIG_FIRST_VALIDATION_ROW, vbNullString, "First Database row validated by ValidateConfiguredExportRows."
    ws.Visible = xlSheetHidden
End Sub

Private Sub EnsureCatalogSheet(ByVal workbook As Workbook, ByVal sheetName As String, ByVal headers As Variant, ByVal errors As Collection)
    Dim ws As Worksheet
    Set ws = EnsureSheet(workbook, sheetName)

    If HeaderMatches(ws, headers) Then
        Exit Sub
    End If

    If SheetHasOnlyBlankHeader(ws, UBound(headers) - LBound(headers) + 1) Then
        WriteHeaders ws, headers
        Exit Sub
    End If

    errors.Add "Sheet " & sheetName & " has unexpected headers in row 1."
End Sub

Private Function EnsureSheet(ByVal workbook As Workbook, ByVal sheetName As String) As Worksheet
    If SheetExists(workbook, sheetName) Then
        Set EnsureSheet = workbook.Worksheets(sheetName)
    Else
        Dim newSheet As Worksheet
        Set newSheet = workbook.Worksheets.Add(After:=workbook.Worksheets(workbook.Worksheets.Count))
        newSheet.Name = sheetName
        Set EnsureSheet = newSheet
    End If
End Function

Private Function HeaderMatches(ByVal ws As Worksheet, ByVal expectedHeaders As Variant) As Boolean
    Dim expectedCount As Long
    expectedCount = UBound(expectedHeaders) - LBound(expectedHeaders) + 1

    Dim lastColumn As Long
    lastColumn = ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column
    If lastColumn < expectedCount Then
        lastColumn = expectedCount
    End If

    Dim i As Long
    For i = 1 To expectedCount
        If CStr(ws.Cells(1, i).Value) <> CStr(expectedHeaders(LBound(expectedHeaders) + i - 1)) Then
            Exit Function
        End If
    Next i

    For i = expectedCount + 1 To lastColumn
        If Not IsBlankText(CStr(ws.Cells(1, i).Value)) Then
            Exit Function
        End If
    Next i

    HeaderMatches = True
End Function

Private Function SheetHasOnlyBlankHeader(ByVal ws As Worksheet, ByVal expectedHeaderCount As Long) As Boolean
    Dim lastColumn As Long
    lastColumn = ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column
    If lastColumn < expectedHeaderCount Then
        lastColumn = expectedHeaderCount
    End If

    Dim i As Long
    For i = 1 To lastColumn
        If Not IsBlankText(CStr(ws.Cells(1, i).Value)) Then
            Exit Function
        End If
    Next i

    SheetHasOnlyBlankHeader = True
End Function

Private Sub WriteHeaders(ByVal ws As Worksheet, ByVal headers As Variant)
    Dim i As Long
    For i = LBound(headers) To UBound(headers)
        ws.Cells(1, i - LBound(headers) + 1).Value = CStr(headers(i))
    Next i
End Sub

Private Sub EnsureConfigSettingRow(ByVal ws As Worksheet, ByVal settingName As String, ByVal defaultValue As String, ByVal notesText As String)
    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    If lastRow < 2 Then
        lastRow = 1
    End If

    Dim rowNumber As Long
    For rowNumber = 2 To lastRow
        If CStr(ws.Cells(rowNumber, 1).Value) = settingName Then
            Exit Sub
        End If
    Next rowNumber

    rowNumber = lastRow + 1
    ws.Cells(rowNumber, 1).Value = settingName
    ws.Cells(rowNumber, 2).Value = defaultValue
    ws.Cells(rowNumber, 3).Value = notesText
End Sub

Private Sub AddValidationError(ByVal errors As Collection, ByVal rowNumber As Long, ByVal orderNumber As String, ByVal columnRef As String, ByVal offendingValue As String, ByVal reason As String)
    Dim message As String
    message = RowContext(rowNumber, orderNumber) & ", column " & columnRef

    If Len(offendingValue) > 0 Then
        message = message & ", value """ & offendingValue & """"
    End If

    message = message & ": " & reason
    errors.Add message
End Sub

Private Function ValidationFailedMessage(ByVal checkedOrderCount As Long, ByVal errors As Collection) As String
    Dim lines As Collection
    Set lines = New Collection

    lines.Add "Validation failed. Checked production-order rows: " & checkedOrderCount & "."
    lines.Add "Showing the first " & MAX_DISPLAYED_VALIDATION_ERRORS & " errors:"

    Dim i As Long
    For i = 1 To errors.Count
        If i > MAX_DISPLAYED_VALIDATION_ERRORS Then
            Exit For
        End If
        lines.Add CStr(errors(i))
    Next i

    If errors.Count > MAX_DISPLAYED_VALIDATION_ERRORS Then
        lines.Add "Total errors: " & errors.Count & "."
    End If

    ValidationFailedMessage = JoinCollection(lines, vbCrLf)
End Function

Private Function ValidationPassedMessage(ByVal checkedOrderCount As Long) As String
    ValidationPassedMessage = "Validation passed. Checked production-order rows: " & checkedOrderCount & "."
End Function

Private Function RowContext(ByVal rowNumber As Long, ByVal orderNumber As String) As String
    RowContext = "Row " & rowNumber & " (order " & orderNumber & ")"
End Function

Private Function TrimmedCellText(ByVal cell As Range) As String
    TrimmedCellText = Trim$(DisplayCellText(cell))
End Function

Private Function IsBlankText(ByVal value As String) As Boolean
    IsBlankText = Len(Trim$(value)) = 0
End Function

Private Function CountOccurrences(ByVal text As String, ByVal token As String) As Long
    If Len(token) = 0 Then
        Exit Function
    End If

    CountOccurrences = (Len(text) - Len(Replace(text, token, vbNullString))) \ Len(token)
End Function

Private Function TextBeforeFinalDelimiter(ByVal text As String, ByVal delimiter As String) As String
    Dim position As Long
    position = InStrRev(text, delimiter, -1, vbBinaryCompare)

    If position = 0 Then
        TextBeforeFinalDelimiter = vbNullString
    Else
        TextBeforeFinalDelimiter = Left$(text, position - 1)
    End If
End Function

Private Function TextAfterFinalDelimiter(ByVal text As String, ByVal delimiter As String) As String
    Dim position As Long
    position = InStrRev(text, delimiter, -1, vbBinaryCompare)

    If position = 0 Then
        TextAfterFinalDelimiter = vbNullString
    Else
        TextAfterFinalDelimiter = Mid$(text, position + Len(delimiter))
    End If
End Function

Private Function NormalizeSpacesForBuilderOutput(ByVal text As String) As String
    NormalizeSpacesForBuilderOutput = Trim$(text)
End Function

Private Function FirstIdentityToken(ByVal identityValue As String) As String
    Dim i As Long

    For i = 1 To Len(identityValue)
        Select Case Mid$(identityValue, i, 1)
            Case " ", vbTab
                If i = 1 Then
                    FirstIdentityToken = vbNullString
                Else
                    FirstIdentityToken = Left$(identityValue, i - 1)
                End If
                Exit Function
        End Select
    Next i

    FirstIdentityToken = identityValue
End Function

Private Function TryParsePositiveNumber(ByVal value As Variant, ByRef parsedNumber As Double) As Boolean
    If IsNumeric(value) Then
        parsedNumber = CDbl(value)
        TryParsePositiveNumber = (parsedNumber > 0)
        Exit Function
    End If

    Dim textValue As String
    textValue = Trim$(CStr(value))
    If Len(textValue) = 0 Then
        Exit Function
    End If

    Dim decimalSeparator As String
    decimalSeparator = Application.International(xlDecimalSeparator)

    textValue = Replace(textValue, ".", decimalSeparator)
    textValue = Replace(textValue, ",", decimalSeparator)

    If Not IsNumeric(textValue) Then
        Exit Function
    End If

    parsedNumber = CDbl(textValue)
    TryParsePositiveNumber = (parsedNumber > 0)
End Function

Private Function TryParseRecipePercent(ByVal value As String, ByRef parsedPercent As Double) As Boolean
    Dim textValue As String
    textValue = Trim$(value)

    If Right$(textValue, 1) <> "%" Then
        Exit Function
    End If

    textValue = Trim$(Left$(textValue, Len(textValue) - 1))
    If Len(textValue) = 0 Then
        Exit Function
    End If

    If Not TryParsePositiveNumber(textValue, parsedPercent) Then
        Exit Function
    End If

    TryParseRecipePercent = True
End Function

Private Function RequiredWorkbookShapeIsValid(ByVal workbook As Workbook, ByRef wsDatabase As Worksheet, ByRef wsConfig As Worksheet, ByRef wsPrintingCatalog As Worksheet, ByRef wsExtrusionCatalog As Worksheet, ByVal errors As Collection) As Boolean
    If Not SheetExists(workbook, DATABASE_SHEET_NAME) Then
        errors.Add "Required sheet " & DATABASE_SHEET_NAME & " is missing."
    Else
        Set wsDatabase = workbook.Worksheets(DATABASE_SHEET_NAME)
    End If

    If Not SheetExists(workbook, CONFIG_SHEET_NAME) Then
        errors.Add "Sheet " & CONFIG_SHEET_NAME & " is missing. Run InstallExportValidation."
    Else
        Set wsConfig = workbook.Worksheets(CONFIG_SHEET_NAME)
        If Not HeaderMatches(wsConfig, Array("Setting", "Value", "Notes")) Then
            errors.Add "Sheet " & CONFIG_SHEET_NAME & " does not have the expected headers."
        End If
    End If

    If Not SheetExists(workbook, PRINTING_CATALOG_SHEET_NAME) Then
        errors.Add "Sheet " & PRINTING_CATALOG_SHEET_NAME & " is missing. Run InstallExportValidation."
    Else
        Set wsPrintingCatalog = workbook.Worksheets(PRINTING_CATALOG_SHEET_NAME)
        If Not HeaderMatches(wsPrintingCatalog, Array("Type", "Value", "Notes")) Then
            errors.Add "Sheet " & PRINTING_CATALOG_SHEET_NAME & " does not have the expected headers."
        End If
    End If

    If Not SheetExists(workbook, EXTRUSION_CATALOG_SHEET_NAME) Then
        errors.Add "Sheet " & EXTRUSION_CATALOG_SHEET_NAME & " is missing. Run InstallExportValidation."
    Else
        Set wsExtrusionCatalog = workbook.Worksheets(EXTRUSION_CATALOG_SHEET_NAME)
        If Not HeaderMatches(wsExtrusionCatalog, Array("Category", "Producer", "GradeCode", "Notes")) Then
            errors.Add "Sheet " & EXTRUSION_CATALOG_SHEET_NAME & " does not have the expected headers."
        End If
    End If

    RequiredWorkbookShapeIsValid = (errors.Count = 0)
End Function

Private Function SheetExists(ByVal workbook As Workbook, ByVal sheetName As String) As Boolean
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = workbook.Worksheets(sheetName)
    SheetExists = Not ws Is Nothing
    On Error GoTo 0
End Function

Private Function LoadPrintingCatalogValues(ByVal ws As Worksheet, ByRef inkValues As Object, ByRef aniloxValues As Object, ByVal errors As Collection) As Boolean
    Set inkValues = CreateObject("Scripting.Dictionary")
    Set aniloxValues = CreateObject("Scripting.Dictionary")

    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    If lastRow < 2 Then
        LoadPrintingCatalogValues = True
        Exit Function
    End If

    Dim rowNumber As Long
    For rowNumber = 2 To lastRow
        Dim typeValue As String
        Dim catalogValue As String

        typeValue = TrimmedCellText(ws.Cells(rowNumber, 1))
        catalogValue = TrimmedCellText(ws.Cells(rowNumber, 2))

        If IsBlankText(typeValue) And IsBlankText(catalogValue) Then
            ' Ignore blank rows.
        ElseIf IsBlankText(typeValue) Then
            errors.Add PRINTING_CATALOG_SHEET_NAME & " row " & rowNumber & ": missing Type."
        ElseIf IsBlankText(catalogValue) Then
            errors.Add PRINTING_CATALOG_SHEET_NAME & " row " & rowNumber & ": missing Value."
        ElseIf typeValue = "Ink" Then
            If Not inkValues.Exists(catalogValue) Then
                inkValues.Add catalogValue, True
            End If
        ElseIf typeValue = "Anilox" Then
            If Not aniloxValues.Exists(catalogValue) Then
                aniloxValues.Add catalogValue, True
            End If
        Else
            errors.Add PRINTING_CATALOG_SHEET_NAME & " row " & rowNumber & ": invalid Type """ & typeValue & """."
        End If
    Next rowNumber

    LoadPrintingCatalogValues = (errors.Count = 0)
End Function

Private Function LoadExtrusionMaterialIdentities(ByVal ws As Worksheet, ByRef identities As Object, ByVal errors As Collection) As Boolean
    Set identities = CreateObject("Scripting.Dictionary")

    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    If lastRow < 2 Then
        LoadExtrusionMaterialIdentities = True
        Exit Function
    End If

    Dim rowNumber As Long
    For rowNumber = 2 To lastRow
        Dim categoryValue As String
        Dim producerValue As String
        Dim gradeValue As String

        categoryValue = CStr(ws.Cells(rowNumber, 1).Value)
        producerValue = CStr(ws.Cells(rowNumber, 2).Value)
        gradeValue = CStr(ws.Cells(rowNumber, 3).Value)

        If IsBlankText(categoryValue) And IsBlankText(producerValue) And IsBlankText(gradeValue) Then
            ' Ignore blank rows.
        Else
            Dim trimmedCategory As String
            Dim trimmedProducer As String
            Dim trimmedGrade As String

            trimmedCategory = Trim$(categoryValue)
            trimmedProducer = Trim$(producerValue)
            trimmedGrade = Trim$(gradeValue)

            If Len(trimmedCategory) = 0 Then
                errors.Add EXTRUSION_CATALOG_SHEET_NAME & " row " & rowNumber & ": missing Category."
            ElseIf Len(trimmedProducer) = 0 Then
                errors.Add EXTRUSION_CATALOG_SHEET_NAME & " row " & rowNumber & ": missing Producer. Use N/A for intentional omission."
            ElseIf Len(trimmedGrade) = 0 Then
                errors.Add EXTRUSION_CATALOG_SHEET_NAME & " row " & rowNumber & ": missing GradeCode. Use N/A for intentional omission."
            ElseIf Not IsApprovedExtrusionCategory(trimmedCategory) Then
                errors.Add EXTRUSION_CATALOG_SHEET_NAME & " row " & rowNumber & ": invalid category """ & categoryValue & """."
            Else
                Dim builtIdentity As String
                builtIdentity = BuildExtrusionIdentity(trimmedCategory, trimmedProducer, trimmedGrade)
                If Len(builtIdentity) = 0 Then
                    errors.Add EXTRUSION_CATALOG_SHEET_NAME & " row " & rowNumber & ": missing valid identity."
                ElseIf Not identities.Exists(builtIdentity) Then
                    identities.Add builtIdentity, True
                End If
            End If
        End If
    Next rowNumber

    LoadExtrusionMaterialIdentities = (errors.Count = 0)
End Function

Private Function BuildExtrusionIdentity(ByVal categoryValue As String, ByVal producerValue As String, ByVal gradeValue As String) As String
    Dim parts As Collection
    Set parts = New Collection

    Dim normalizedCategory As String
    normalizedCategory = NormalizeSpacesForBuilderOutput(categoryValue)
    If Len(normalizedCategory) > 0 Then
        parts.Add normalizedCategory
    End If

    Dim normalizedProducer As String
    normalizedProducer = NormalizeSpacesForBuilderOutput(producerValue)
    If Len(normalizedProducer) > 0 Then
        If normalizedProducer <> "N/A" Then
            parts.Add normalizedProducer
        End If
    End If

    Dim normalizedGrade As String
    normalizedGrade = NormalizeSpacesForBuilderOutput(gradeValue)
    If Len(normalizedGrade) > 0 Then
        If normalizedGrade <> "N/A" Then
            parts.Add normalizedGrade
        End If
    End If

    BuildExtrusionIdentity = JoinCollection(parts, " ")
End Function

Private Function IsApprovedExtrusionCategory(ByVal categoryValue As String) As Boolean
    Select Case categoryValue
        Case "LDPE", "LLDPE", "MDPE", "reLDPE", "Antistatic", "Masterbatch", "Filler", "UV", "Antislip"
            IsApprovedExtrusionCategory = True
    End Select
End Function

Private Function SelectedProductionRows(ByVal ws As Worksheet, ByVal selectedRange As Range) As Collection
    Dim rows As New Collection
    Dim seen As Object
    Set seen = CreateObject("Scripting.Dictionary")

    Dim area As Range
    Dim rowRange As Range
    Dim rowNumber As Long
    Dim orderNumber As String

    For Each area In selectedRange.Areas
        For Each rowRange In area.Rows
            rowNumber = rowRange.Row
            If rowNumber >= FIRST_PRODUCTION_ROW Then
                If Not seen.Exists(CStr(rowNumber)) Then
                    seen.Add CStr(rowNumber), True
                    orderNumber = TrimmedCellText(ws.Cells(rowNumber, 1))
                    If Not IsBlankText(orderNumber) Then
                        rows.Add rowNumber
                    End If
                End If
            End If
        Next rowRange
    Next area

    Set SelectedProductionRows = rows
End Function

Private Function ConfiguredProductionRows(ByVal ws As Worksheet, ByVal firstRow As Long) As Collection
    Dim rows As New Collection

    Dim startRow As Long
    startRow = firstRow

    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    If lastRow < startRow Then
        Set ConfiguredProductionRows = rows
        Exit Function
    End If

    Dim rowNumber As Long
    For rowNumber = startRow To lastRow
        If Not IsBlankText(TrimmedCellText(ws.Cells(rowNumber, 1))) Then
            rows.Add rowNumber
        End If
    Next rowNumber

    Set ConfiguredProductionRows = rows
End Function

Private Function FirstValidationRow(ByVal wsConfig As Worksheet, ByRef errorMessage As String) As Long
    Dim lastRow As Long
    lastRow = wsConfig.Cells(wsConfig.Rows.Count, 1).End(xlUp).Row
    If lastRow < 2 Then
        errorMessage = "The FirstValidationRow setting is missing in ExportConfig."
        Exit Function
    End If

    Dim rowNumber As Long
    For rowNumber = 2 To lastRow
        If CStr(wsConfig.Cells(rowNumber, 1).Value) = CONFIG_FIRST_VALIDATION_ROW Then
            Dim configuredValue As String
            configuredValue = CStr(wsConfig.Cells(rowNumber, 2).Value)

            If IsBlankText(configuredValue) Then
                errorMessage = "The FirstValidationRow setting in ExportConfig is blank."
                Exit Function
            End If

            Dim parsedValue As Double
            If Not TryParsePositiveNumber(configuredValue, parsedValue) Then
                errorMessage = "The FirstValidationRow setting in ExportConfig must be a whole number."
                Exit Function
            End If

            If parsedValue <> Fix(parsedValue) Then
                errorMessage = "The FirstValidationRow setting in ExportConfig must be a whole number."
                Exit Function
            End If

            If parsedValue < FIRST_PRODUCTION_ROW Then
                errorMessage = "The FirstValidationRow setting in ExportConfig must be row " & FIRST_PRODUCTION_ROW & " or greater."
                Exit Function
            End If

            FirstValidationRow = CLng(parsedValue)
            Exit Function
        End If
    Next rowNumber

    errorMessage = "The FirstValidationRow setting is missing in ExportConfig."
End Function

Private Function ValidateRows(ByVal wsDatabase As Worksheet, ByVal wsPrintingCatalog As Worksheet, ByVal wsExtrusionCatalog As Worksheet, ByVal targetRows As Collection, ByVal errors As Collection) As Boolean
    Dim printingInkValues As Object
    Dim printingAniloxValues As Object
    Dim extrusionIdentities As Object

    If Not LoadPrintingCatalogValues(wsPrintingCatalog, printingInkValues, printingAniloxValues, errors) Then
        Exit Function
    End If

    If Not LoadExtrusionMaterialIdentities(wsExtrusionCatalog, extrusionIdentities, errors) Then
        Exit Function
    End If

    Dim item As Variant
    For Each item In targetRows
        Dim rowNumber As Long
        rowNumber = CLng(item)

        ValidateTargetGross wsDatabase, rowNumber, errors
        ValidatePrintingCells wsDatabase, rowNumber, printingInkValues, printingAniloxValues, errors
        ValidateExtrusionCells wsDatabase, rowNumber, extrusionIdentities, errors
    Next item

    ValidateRows = (errors.Count = 0)
End Function

Private Sub ValidateTargetGross(ByVal ws As Worksheet, ByVal rowNumber As Long, ByVal errors As Collection)
    Dim orderNumber As String
    orderNumber = TrimmedCellText(ws.Cells(rowNumber, 1))

    Dim grossCell As Range
    Set grossCell = ws.Range("G" & rowNumber)

    Dim parsedGross As Double
    If Not TryParsePositiveNumber(grossCell.Value, parsedGross) Then
        AddValidationError errors, rowNumber, orderNumber, "G", DisplayCellText(grossCell), "target gross kilograms must be a positive number."
    End If
End Sub

Private Sub ValidatePrintingCells(ByVal ws As Worksheet, ByVal rowNumber As Long, ByVal inkValues As Object, ByVal aniloxValues As Object, ByVal errors As Collection)
    Dim orderNumber As String
    orderNumber = TrimmedCellText(ws.Cells(rowNumber, 1))

    Dim cell As Range
    For Each cell In ws.Range(PRINTING_FIRST_COLUMN & rowNumber & ":" & PRINTING_LAST_COLUMN & rowNumber).Cells
        Dim rawValue As String
        rawValue = DisplayCellText(cell)

        If Not IsBlankText(rawValue) Then
            Dim slashCount As Long
            slashCount = CountOccurrences(rawValue, "/")

            If slashCount > 1 Then
                AddValidationError errors, rowNumber, orderNumber, ColumnName(cell), rawValue, "at most one / delimiter is allowed."
            Else
                Dim inkPart As String
                Dim aniloxPart As String

                If slashCount = 1 Then
                    inkPart = Trim$(Left$(rawValue, InStr(1, rawValue, "/", vbBinaryCompare) - 1))
                    aniloxPart = Trim$(Mid$(rawValue, InStr(1, rawValue, "/", vbBinaryCompare) + 1))
                Else
                    inkPart = Trim$(rawValue)
                    aniloxPart = vbNullString
                End If

                If IsBlankText(inkPart) Then
                    AddValidationError errors, rowNumber, orderNumber, ColumnName(cell), rawValue, "missing Ink value."
                ElseIf Not inkValues.Exists(inkPart) Then
                    AddValidationError errors, rowNumber, orderNumber, ColumnName(cell), rawValue, "Ink does not match RecipeCatalogPrinting."
                ElseIf slashCount = 1 Then
                    If IsBlankText(aniloxPart) Then
                        AddValidationError errors, rowNumber, orderNumber, ColumnName(cell), rawValue, "Anilox value is required after /."
                    ElseIf Not aniloxValues.Exists(aniloxPart) Then
                        AddValidationError errors, rowNumber, orderNumber, ColumnName(cell), rawValue, "Anilox does not match RecipeCatalogPrinting."
                    End If
                End If
            End If
        End If
    Next cell
End Sub

Private Sub ValidateExtrusionCells(ByVal ws As Worksheet, ByVal rowNumber As Long, ByVal extrusionIdentities As Object, ByVal errors As Collection)
    Dim orderNumber As String
    orderNumber = TrimmedCellText(ws.Cells(rowNumber, 1))

    Dim totalPercent As Double
    Dim filledCount As Long
    Dim cell As Range

    For Each cell In ws.Range(EXTRUSION_FIRST_COLUMN & rowNumber & ":" & EXTRUSION_LAST_COLUMN & rowNumber).Cells
        Dim rawValue As String
        rawValue = DisplayCellText(cell)

        If Not IsBlankText(rawValue) Then
            filledCount = filledCount + 1

            If CountOccurrences(rawValue, "|") = 0 Then
                AddValidationError errors, rowNumber, orderNumber, ColumnName(cell), rawValue, "missing | delimiter between identity and percent."
            Else
                Dim identityValue As String
                Dim percentText As String
                identityValue = Trim$(TextBeforeFinalDelimiter(rawValue, "|"))
                percentText = Trim$(TextAfterFinalDelimiter(rawValue, "|"))

                ValidateExtrusionIdentity ws, rowNumber, ColumnName(cell), rawValue, identityValue, extrusionIdentities, errors

                Dim parsedPercent As Double
                If Not TryParseRecipePercent(percentText, parsedPercent) Then
                    AddValidationError errors, rowNumber, orderNumber, ColumnName(cell), rawValue, "percent must be a positive number with a % symbol."
                Else
                    totalPercent = totalPercent + parsedPercent
                End If
            End If
        End If
    Next cell

    If filledCount > 0 Then
        If Abs(totalPercent - 100#) > 0.000001 Then
            AddValidationError errors, rowNumber, orderNumber, EXTRUSION_FIRST_COLUMN & ":" & EXTRUSION_LAST_COLUMN, CStr(totalPercent) & "%", "filled extrusion percentages must total exactly 100%."
        End If
    End If
End Sub

Private Sub ValidateExtrusionIdentity(ByVal ws As Worksheet, ByVal rowNumber As Long, ByVal columnRef As String, ByVal rawValue As String, ByVal identityValue As String, ByVal extrusionIdentities As Object, ByVal errors As Collection)
    Dim orderNumber As String
    orderNumber = TrimmedCellText(ws.Cells(rowNumber, 1))

    Dim trimmedIdentity As String
    trimmedIdentity = Trim$(identityValue)

    If Len(trimmedIdentity) = 0 Then
        AddValidationError errors, rowNumber, orderNumber, columnRef, rawValue, "missing identity before |."
        Exit Sub
    End If

    Dim firstToken As String
    firstToken = FirstIdentityToken(trimmedIdentity)

    If Not IsApprovedExtrusionCategory(firstToken) Then
        AddValidationError errors, rowNumber, orderNumber, columnRef, rawValue, "first token is not an approved category."
        Exit Sub
    End If

    If Not extrusionIdentities.Exists(trimmedIdentity) Then
        AddValidationError errors, rowNumber, orderNumber, columnRef, rawValue, "identity does not match RecipeCatalogExtrusion."
    End If
End Sub

Private Function BuildCsv(ByVal ws As Worksheet, ByVal exportRows As Collection) As String
    Dim headers As Variant
    headers = Array( _
        "order_number", "order_date", "delivery_date", "customer", "city", "product_type", _
        "quantity_1", "unit_1", "quantity_2", "unit_2", "product_form", "material", _
        "size_thickness", "notes", "extrusion_flag", "extrusion_folding", _
        "extrusion_next_operation", "extrusion_treatment", "raw_material_a", "raw_material_b", _
        "raw_material_c", "linear_pe", "antistatic", "masterbatch", "chalk", "packaging_method" _
    )

    Dim sourceColumns As Variant
    sourceColumns = Array( _
        "A", "B", "C", "D", "E", "F", _
        "G", "H", "I", "J", "K", "L", _
        "M", "N", "W", "AJ", _
        "AK", "AL", "AM", "AN", _
        "AO", "AP", "AQ", "AR", "AS", "AT" _
    )

    Dim lines As Collection
    Set lines = New Collection
    lines.Add JoinCsvFields(headers)

    Dim item As Variant
    Dim rowNumber As Long
    Dim values() As String
    Dim i As Long

    For Each item In exportRows
        rowNumber = CLng(item)
        ReDim values(LBound(sourceColumns) To UBound(sourceColumns))

        For i = LBound(sourceColumns) To UBound(sourceColumns)
            values(i) = DisplayCellText(ws.Range(CStr(sourceColumns(i)) & rowNumber))
        Next i

        lines.Add JoinCsvFields(values)
    Next item

    BuildCsv = JoinCollection(lines, vbCrLf) & vbCrLf
End Function

Private Function DisplayCellText(ByVal cell As Range) As String
    Dim textValue As String
    textValue = CStr(cell.Text)

    If Len(textValue) > 0 And Left$(textValue, 1) <> "#" Then
        DisplayCellText = textValue
    ElseIf IsError(cell.Value) Or IsEmpty(cell.Value) Then
        DisplayCellText = vbNullString
    Else
        DisplayCellText = CStr(cell.Value)
    End If
End Function

Private Function JoinCsvFields(ByVal fields As Variant) As String
    Dim escaped() As String
    Dim i As Long

    ReDim escaped(LBound(fields) To UBound(fields))
    For i = LBound(fields) To UBound(fields)
        escaped(i) = CsvEscape(CStr(fields(i)))
    Next i

    JoinCsvFields = Join(escaped, ",")
End Function

Private Function CsvEscape(ByVal value As String) As String
    Dim needsQuotes As Boolean
    needsQuotes = InStr(1, value, ",", vbBinaryCompare) > 0 _
        Or InStr(1, value, """", vbBinaryCompare) > 0 _
        Or InStr(1, value, vbCr, vbBinaryCompare) > 0 _
        Or InStr(1, value, vbLf, vbBinaryCompare) > 0

    value = Replace(value, """", """""")

    If needsQuotes Then
        CsvEscape = """" & value & """"
    Else
        CsvEscape = value
    End If
End Function

Private Function JoinCollection(ByVal values As Collection, ByVal delimiter As String) As String
    If values.Count = 0 Then
        JoinCollection = vbNullString
        Exit Function
    End If

    Dim parts() As String
    Dim i As Long

    ReDim parts(1 To values.Count)
    For i = 1 To values.Count
        parts(i) = CStr(values(i))
    Next i

    JoinCollection = Join(parts, delimiter)
End Function

Private Function ColumnName(ByVal cell As Range) As String
    ColumnName = Replace(cell.Address(False, False), CStr(cell.Row), vbNullString)
End Function

Private Function ExportFolderPath(ByVal workbookPath As String) As String
    If Len(workbookPath) = 0 Then
        Err.Raise vbObjectError + 1000, , "Save the workbook before exporting."
    End If

    ExportFolderPath = workbookPath & "\" & EXPORT_FOLDER_NAME
End Function

Private Sub EnsureFolderExists(ByVal folderPath As String)
    Dim fso As Object
    Set fso = CreateObject("Scripting.FileSystemObject")

    If Not fso.FolderExists(folderPath) Then
        fso.CreateFolder folderPath
    End If
End Sub

Private Sub WriteUtf8TextFile(ByVal filename As String, ByVal text As String)
    Dim stream As Object
    Set stream = CreateObject("ADODB.Stream")

    With stream
        .Type = 2
        .Charset = "utf-8"
        .Open
        .WriteText text
        .SaveToFile filename, 2
        .Close
    End With
End Sub
