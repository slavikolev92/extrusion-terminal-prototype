from __future__ import annotations

import re
from pathlib import Path


EXPORT_MACRO_PATH = Path(
    "interim-costing-process/excel-tools/export-validation/export-validation.bas"
)
EXPORT_README_PATH = Path("interim-costing-process/excel-tools/export-validation/README.md")
RECIPE_BUILDER_PATH = Path(
    "interim-costing-process/excel-tools/recipe-builder/recipe-builder-installer.bas"
)
RECIPE_BUILDER_README_PATH = Path(
    "interim-costing-process/excel-tools/recipe-builder/README.md"
)


def macro_text() -> str:
    return EXPORT_MACRO_PATH.read_text(encoding="utf-8")


def recipe_builder_text() -> str:
    return RECIPE_BUILDER_PATH.read_text(encoding="utf-8")


def export_readme_text() -> str:
    return EXPORT_README_PATH.read_text(encoding="utf-8")


def recipe_builder_readme_text() -> str:
    return RECIPE_BUILDER_README_PATH.read_text(encoding="utf-8")


def array_body(text: str, assignment_name: str) -> str:
    pattern = rf"{assignment_name}\s*=\s*Array\((.*?)\)"
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    assert match, f"{assignment_name} array not found"
    return match.group(1)


def quoted_values(body: str) -> list[str]:
    return re.findall(r'"([^"]*)"', body)


def procedure_body(text: str, procedure_name: str) -> str:
    pattern = rf"Public Sub {procedure_name}\(\)(.*?)(?:\nPublic Sub |\Z)"
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    assert match, f"{procedure_name} procedure not found"
    return match.group(1)


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
        'PRINTING_FIRST_COLUMN As String = "W"',
        'PRINTING_LAST_COLUMN As String = "AD"',
        'EXTRUSION_FIRST_COLUMN As String = "AH"',
        'EXTRUSION_LAST_COLUMN As String = "AN"',
    ):
        assert expected in text

    assert 'EXPORT_FOLDER_NAME As String = "extracts"' not in text
    assert 'PRINTING_FIRST_COLUMN As String = "AB"' not in text
    assert 'EXTRUSION_FIRST_COLUMN As String = "AM"' not in text


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
        "R",
        "AE",
        "AF",
        "AG",
        "AH",
        "AI",
        "AJ",
        "AK",
        "AL",
        "AM",
        "AN",
        "AO",
    ]
    assert "O" not in source_columns
    assert "AT" not in source_columns


def test_export_macro_requires_positive_sales_price_without_exporting_it():
    text = macro_text()

    assert "ValidateSalesPrice wsDatabase, rowNumber, errors" in text
    assert 'ws.Range("O" & rowNumber)' in text
    assert "sales price must be a positive number." in text
    assert '"sales_price"' not in text


def test_selected_row_macros_require_active_sheet_to_be_thisworkbook_database():
    selected_validation = procedure_body(macro_text(), "ValidateSelectedExportRows")
    selected_export = procedure_body(macro_text(), "ExportSelectedExtrusionOrdersCsv")
    configured_validation = procedure_body(macro_text(), "ValidateConfiguredExportRows")

    for body in (selected_validation, selected_export):
        assert "If Not ActiveSheet Is wsDatabase Then" in body
        assert "ActiveSheet.Name <> DATABASE_SHEET_NAME" not in body

    assert "ActiveSheet" not in configured_validation
    assert "Selection" not in configured_validation


def test_export_macro_keeps_catalog_omission_control_case_sensitive():
    text = macro_text()

    assert 'normalizedProducer <> "N/A"' in text
    assert 'normalizedGrade <> "N/A"' in text
    assert 'UCase$(normalizedProducer) <> "N/A"' not in text
    assert 'UCase$(normalizedGrade) <> "N/A"' not in text


def test_install_macro_messages_remain_english_ascii():
    body = procedure_body(macro_text(), "InstallExportValidation")

    assert "Export validation setup" in body
    assert not re.search(r"[\u0400-\u04ff]", body)


def test_export_macro_source_is_ascii_only_for_vba_import_safety():
    text = macro_text()

    assert text.isascii()


def test_export_macro_documents_validation_and_exports_folder():
    text = export_readme_text()

    assert "InstallExportValidation" in text
    assert "ValidateSelectedExportRows" in text
    assert "ValidateConfiguredExportRows" in text
    assert "ExportSelectedExtrusionOrdersCsv" in text
    assert "export-validation.bas" in text
    assert "exports" in text
    assert "RecipeCatalogPrinting" in text
    assert "RecipeCatalogExtrusion" in text
    assert "ExportConfig" in text
    assert "Database!W:AD" in text
    assert "Database!AH:AN" in text
    assert "extracts" not in text


def test_recipe_builder_installer_uses_plain_names_and_cleaned_ranges():
    text = recipe_builder_text()

    assert 'Attribute VB_Name = "RecipeBuilderInstaller"' in text
    assert "Public Sub InstallRecipeBuilder()" in text
    assert "Public Function IsExtrusionRecipeBuilderCell(" in text
    assert "Public Function IsPrintingRecipeBuilderCell(" in text
    assert "Public Sub OpenExtrusionRecipeBuilder(" in text
    assert "Public Sub OpenPrintingRecipeBuilder(" in text
    assert "V2" not in text
    assert "InstallRecipeBuilderV2" not in text

    for expected in (
        'PRINTING_FIRST_COLUMN As String = "W"',
        'PRINTING_LAST_COLUMN As String = "AD"',
        'EXTRUSION_FIRST_COLUMN As String = "AH"',
        'EXTRUSION_LAST_COLUMN As String = "AN"',
    ):
        assert expected in text


def test_recipe_builder_readme_uses_plain_installer_name_and_cleaned_ranges():
    text = recipe_builder_readme_text()

    assert "recipe-builder-installer.bas" in text
    assert "InstallRecipeBuilder" in text
    assert "InstallRecipeBuilderV2" not in text
    assert "modRecipeBuilderCascadingInstaller" not in text
    assert "Database!W:AD" in text
    assert "Database!AH:AN" in text
