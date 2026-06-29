from __future__ import annotations

import re
from pathlib import Path


MACRO_PATH = Path(
    "interim-costing-process/excel-tools/export-validation/ExportExtrusionOrders.bas"
)
README_PATH = Path("interim-costing-process/excel-tools/export-validation/README.md")


def macro_text() -> str:
    return MACRO_PATH.read_text(encoding="utf-8")


def readme_text() -> str:
    return README_PATH.read_text(encoding="utf-8")


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
        'PRINTING_FIRST_COLUMN As String = "AB"',
        'PRINTING_LAST_COLUMN As String = "AI"',
        'EXTRUSION_FIRST_COLUMN As String = "AM"',
        'EXTRUSION_LAST_COLUMN As String = "AS"',
    ):
        assert expected in text

    assert 'EXPORT_FOLDER_NAME As String = "extracts"' not in text


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
        "W",
        "AJ",
        "AK",
        "AL",
        "AM",
        "AN",
        "AO",
        "AP",
        "AQ",
        "AR",
        "AS",
        "AT",
    ]
    assert "AB" not in source_columns
    assert "AI" not in source_columns


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
    text = readme_text()

    assert "InstallExportValidation" in text
    assert "ValidateSelectedExportRows" in text
    assert "ValidateConfiguredExportRows" in text
    assert "ExportSelectedExtrusionOrdersCsv" in text
    assert "exports" in text
    assert "RecipeCatalogPrinting" in text
    assert "RecipeCatalogExtrusion" in text
    assert "ExportConfig" in text
    assert "extracts" not in text
