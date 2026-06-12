Attribute VB_Name = "ExportExtrusionOrders"
Option Explicit

' Exports selected rows from the Database worksheet into the CSV format expected by
' the extrusion terminal prototype. The macro reads workbook cells only; it does
' not edit worksheet data.

Private Const EXPORT_FOLDER_NAME As String = "extracts"
Private Const DATABASE_SHEET_NAME As String = "Database"

Public Sub ExportSelectedExtrusionOrdersCsv()
    Dim ws As Worksheet
    Set ws = ActiveWorkbook.Worksheets(DATABASE_SHEET_NAME)

    If ActiveSheet.Name <> DATABASE_SHEET_NAME Then
        MsgBox "Open the Database sheet, select the order rows to export, then run this macro.", vbExclamation
        Exit Sub
    End If

    If TypeName(Selection) <> "Range" Then
        MsgBox "Select one or more Database rows before running the export.", vbExclamation
        Exit Sub
    End If

    Dim exportRows As Collection
    Set exportRows = SelectedDataRows(Selection)

    If exportRows.Count = 0 Then
        MsgBox "No valid production-order rows selected. Select rows 5 or below in Database.", vbExclamation
        Exit Sub
    End If

    Dim csvText As String
    csvText = BuildCsv(ws, exportRows)

    Dim exportPath As String
    exportPath = ExportFolderPath(ActiveWorkbook.Path)
    EnsureFolderExists exportPath

    Dim filename As String
    filename = exportPath & "\extrusion_orders_" & Format(Now, "yyyymmdd_hhnnss") & ".csv"
    WriteUtf8TextFile filename, csvText

    MsgBox "Exported " & exportRows.Count & " row(s) to:" & vbCrLf & filename, vbInformation
End Sub

Private Function SelectedDataRows(ByVal selectedRange As Range) As Collection
    Dim rows As New Collection
    Dim seen As Object
    Set seen = CreateObject("Scripting.Dictionary")

    Dim area As Range
    Dim rowRange As Range
    Dim rowNumber As Long

    For Each area In selectedRange.Areas
        For Each rowRange In area.Rows
            rowNumber = rowRange.Row
            If rowNumber >= 5 Then
                If Not seen.Exists(CStr(rowNumber)) Then
                    seen.Add CStr(rowNumber), True
                    rows.Add rowNumber
                End If
            End If
        Next rowRange
    Next area

    Set SelectedDataRows = rows
End Function

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
    Dim parts() As String
    Dim i As Long

    ReDim parts(1 To values.Count)
    For i = 1 To values.Count
        parts(i) = CStr(values(i))
    Next i

    JoinCollection = Join(parts, delimiter)
End Function

Private Function ExportFolderPath(ByVal workbookPath As String) As String
    If Len(workbookPath) = 0 Then
        Err.Raise vbObjectError + 1000, , "Save the workbook before exporting CSV files."
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
