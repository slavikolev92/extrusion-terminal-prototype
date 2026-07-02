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


def procedure_body(text: str, declaration: str) -> str:
    start = text.index(declaration)
    end = text.index("End Sub", start)
    return text[start:end]


def test_master_installer_declares_required_bundle_files():
    text = macro_text()
    for filename in REQUIRED_FILES:
        assert filename in text


def test_master_installer_stops_before_import_when_required_file_missing():
    text = macro_text()
    assert "ValidateRequiredBundleFiles" in text
    assert "Exit Sub" in text
    assert "Missing required workbook tool file" in text


def test_master_installer_validates_required_files_before_workbook_mutation():
    body = procedure_body(macro_text(), "Public Sub InstallWorkbookTools")
    validation = body.index("ValidateRequiredBundleFiles(folderPath)")
    cleanup = body.index("RemoveManagedWorkbookToolComponents")
    first_import = body.index("ImportBundleFile")
    assert validation < cleanup
    assert validation < first_import


def test_master_installer_restores_screen_updating_on_success_and_failure_paths():
    body = procedure_body(macro_text(), "Public Sub InstallWorkbookTools")
    assert body.count("Application.ScreenUpdating = previousScreenUpdating") >= 2
    assert (
        body.index("Application.ScreenUpdating = previousScreenUpdating")
        < body.index('MsgBox "Workbook tools installed successfully.')
    )
    assert (
        body.rindex("Application.ScreenUpdating = previousScreenUpdating")
        > body.index("InstallFailed:")
    )


def test_master_installer_runs_installers_in_fixed_order():
    text = macro_text()
    body = procedure_body(text, "Public Sub InstallWorkbookTools")
    native = body.index('"InstallShiftManagerNativeMacros"')
    recipe = body.index('"InstallRecipeBuilder"')
    export = body.index('"InstallExportValidation"')
    actuals = body.index('"InstallActualsCapture"')
    assert native < recipe < export < actuals


def test_master_installer_late_binds_imported_installers_to_compile_standalone():
    text = macro_text()
    body = procedure_body(text, "Public Sub InstallWorkbookTools")
    assert "RunWorkbookInstaller" in body
    for installer_name in [
        "InstallShiftManagerNativeMacros",
        "InstallRecipeBuilder",
        "InstallExportValidation",
        "InstallActualsCapture",
    ]:
        assert f'RunWorkbookInstaller "{installer_name}"' in body
        assert f"\n    {installer_name}\n" not in body
        assert f"\n    {installer_name}\r\n" not in body


def test_master_installer_preserves_itself():
    text = macro_text()
    assert "WORKBOOK_TOOLS_MASTER_INSTALLER_MODULE" in text
    assert "Skip managed cleanup for the running master installer" in text


def test_master_installer_installs_workbook_open_protection_reset_only():
    text = macro_text()
    body = procedure_body(text, "Public Sub InstallWorkbookTools")
    assert "InstallWorkbookOpenProtectionReset" in text
    assert body.index("InstallActualsCapture") < body.index("InstallWorkbookOpenProtectionReset")
    assert "Private Sub Workbook_Open()" in text
    assert "ApplyActualsProtection" in text
    assert "On Error Resume Next" in text
    assert "On Error GoTo 0" in text
    assert "Worksheet_BeforeDoubleClick" not in text
    assert "Workbook_SheetBeforeDoubleClick" not in text


def test_workbook_open_installer_replaces_only_empty_or_managed_open_handler():
    text = macro_text()
    body = procedure_body(text, "Private Sub InstallWorkbookOpenProtectionReset")
    assert "WorkbookOpenProcedureExists" in body
    assert "WorkbookOpenProcedureIsManaged" in body
    assert "Err.Raise" in body
    assert "unmanaged ThisWorkbook.Workbook_Open" in text
    assert body.index("WorkbookOpenProcedureIsManaged") < body.index("RemoveCodeProcedureIfExists")
    assert "NormalizeWorkbookOpenCode" in text
    assert "WorkbookOpenProtectionResetCode()" in text
