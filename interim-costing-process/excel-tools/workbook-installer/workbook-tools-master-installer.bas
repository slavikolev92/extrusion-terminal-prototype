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

    Dim previousScreenUpdating As Boolean
    previousScreenUpdating = Application.ScreenUpdating

    On Error GoTo InstallFailed
    Application.ScreenUpdating = False

    RemoveManagedWorkbookToolComponents
    ImportBundleFile folderPath, FILE_NATIVE
    ImportBundleFile folderPath, FILE_RECIPE
    ImportBundleFile folderPath, FILE_EXPORT
    ImportBundleFile folderPath, FILE_ACTUALS

    RunWorkbookInstaller "InstallShiftManagerNativeMacros"
    RunWorkbookInstaller "InstallRecipeBuilder"
    RunWorkbookInstaller "InstallExportValidation"
    RunWorkbookInstaller "InstallActualsCapture"
    InstallWorkbookOpenProtectionReset

    Application.ScreenUpdating = previousScreenUpdating
    MsgBox "Workbook tools installed successfully.", vbInformation, "Workbook Tools"
    Exit Sub

InstallFailed:
    Application.ScreenUpdating = previousScreenUpdating
    MsgBox "Workbook tools installation failed: " & Err.Description, vbCritical, "Workbook Tools"
End Sub

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

    Dim invalid As Collection
    Set invalid = New Collection

    AddInvalidBundleFileIfNeeded invalid, folderPath, FILE_NATIVE, "ShiftManagerNativeMacros", "InstallShiftManagerNativeMacros"
    AddInvalidBundleFileIfNeeded invalid, folderPath, FILE_RECIPE, "RecipeBuilderInstaller", "InstallRecipeBuilder"
    AddInvalidBundleFileIfNeeded invalid, folderPath, FILE_EXPORT, "ExportValidation", "InstallExportValidation"
    AddInvalidBundleFileIfNeeded invalid, folderPath, FILE_ACTUALS, "ActualsCaptureInstaller", "InstallActualsCapture"

    If invalid.Count > 0 Then
        MsgBox "Invalid workbook tool file:" & vbCrLf & JoinCollection(invalid, vbCrLf), vbCritical, "Workbook Tools"
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

Private Sub AddInvalidBundleFileIfNeeded(ByVal invalid As Collection, ByVal folderPath As String, ByVal filename As String, ByVal moduleName As String, ByVal installerName As String)
    Dim fileText As String
    fileText = ReadTextFile(folderPath & Application.PathSeparator & filename)

    If InStr(1, fileText, "Attribute VB_Name = """ & moduleName & """", vbTextCompare) = 0 Then
        invalid.Add filename & " is missing Attribute VB_Name = """ & moduleName & """."
        Exit Sub
    End If

    If InStr(1, fileText, "Public Sub " & installerName, vbTextCompare) = 0 Then
        invalid.Add filename & " is missing public installer entry point " & installerName & "."
        Exit Sub
    End If
End Sub

Private Function ReadTextFile(ByVal filePath As String) As String
    Dim fileNumber As Integer
    fileNumber = FreeFile

    Open filePath For Binary Access Read As #fileNumber
    If LOF(fileNumber) > 0 Then
        ReadTextFile = Space$(LOF(fileNumber))
        Get #fileNumber, , ReadTextFile
    Else
        ReadTextFile = vbNullString
    End If
    Close #fileNumber
End Function

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

Private Sub RunWorkbookInstaller(ByVal installerName As String)
    Application.Run "'" & Replace(ThisWorkbook.Name, "'", "''") & "'!" & installerName
End Sub

Private Sub InstallWorkbookOpenProtectionReset()
    Dim codeModule As Object
    Set codeModule = ThisWorkbook.VBProject.VBComponents("ThisWorkbook").CodeModule

    If WorkbookOpenProcedureExists(codeModule) Then
        If Not WorkbookOpenProcedureIsManaged(codeModule) Then
            Err.Raise vbObjectError + 3000, , "Installation stopped because an unmanaged ThisWorkbook.Workbook_Open already exists. Preserve or merge that code manually before installing the Actuals protection reset."
        End If

        RemoveCodeProcedureIfExists codeModule, "Workbook_Open"
    End If

    codeModule.AddFromString WorkbookOpenProtectionResetCode()
End Sub

Private Function WorkbookOpenProcedureExists(ByVal codeModule As Object) As Boolean
    Dim startLine As Long

    On Error Resume Next
    startLine = codeModule.ProcStartLine("Workbook_Open", 0)
    WorkbookOpenProcedureExists = (Err.Number = 0 And startLine > 0)
    Err.Clear
    On Error GoTo 0
End Function

Private Function WorkbookOpenProcedureIsManaged(ByVal codeModule As Object) As Boolean
    WorkbookOpenProcedureIsManaged = NormalizeWorkbookOpenCode(WorkbookOpenProcedureText(codeModule)) = NormalizeWorkbookOpenCode(WorkbookOpenProtectionResetCode())
End Function

Private Function WorkbookOpenProcedureText(ByVal codeModule As Object) As String
    Dim startLine As Long
    Dim lineCount As Long

    On Error GoTo NoWorkbookOpenProcedure
    startLine = codeModule.ProcStartLine("Workbook_Open", 0)
    lineCount = codeModule.ProcCountLines("Workbook_Open", 0)
    WorkbookOpenProcedureText = codeModule.Lines(startLine, lineCount)
    Exit Function

NoWorkbookOpenProcedure:
    WorkbookOpenProcedureText = vbNullString
End Function

Private Function NormalizeWorkbookOpenCode(ByVal procedureCode As String) As String
    Dim normalized As String
    normalized = LCase$(procedureCode)
    normalized = Replace(normalized, vbCrLf, vbNullString)
    normalized = Replace(normalized, vbCr, vbNullString)
    normalized = Replace(normalized, vbLf, vbNullString)
    normalized = Replace(normalized, vbTab, vbNullString)
    normalized = Replace(normalized, " ", vbNullString)

    NormalizeWorkbookOpenCode = normalized
End Function

Private Sub RemoveCodeProcedureIfExists(ByVal codeModule As Object, ByVal procedureName As String)
    Dim startLine As Long
    Dim lineCount As Long

    On Error Resume Next
    startLine = codeModule.ProcStartLine(procedureName, 0)
    If Err.Number = 0 Then
        lineCount = codeModule.ProcCountLines(procedureName, 0)
        codeModule.DeleteLines startLine, lineCount
    End If
    On Error GoTo 0
End Sub

Private Function WorkbookOpenProtectionResetCode() As String
    WorkbookOpenProtectionResetCode = _
        "Private Sub Workbook_Open()" & vbCrLf & _
        "    On Error Resume Next" & vbCrLf & _
        "    ApplyActualsProtection" & vbCrLf & _
        "    On Error GoTo 0" & vbCrLf & _
        "End Sub" & vbCrLf
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
