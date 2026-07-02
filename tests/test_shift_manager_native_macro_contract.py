from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "interim-costing-process/excel-tools/native/shift-manager-native-macros.bas"


def macro_text() -> str:
    return NATIVE.read_text(encoding="utf-8")


def test_native_macro_uses_marko_filter_range_as_standard():
    assert 'A4:AX30000' in macro_text()


def test_native_macro_uses_marko_back_side_print_range_as_standard():
    text = macro_text()
    assert "AS55:BC105" in text
    assert "AS56:BC106" not in text


def test_native_macro_installs_database_change_handler():
    text = macro_text()
    assert "InstallDatabaseNativeSheetCode" in text
    assert "Worksheet_Change" in text
    assert "ApplyDatabaseFilters" in text
    assert 'Me.Range("C2,D2,F2")' in text


def test_native_macro_installs_technology_card_print_entry_points():
    text = macro_text()
    for procedure in [
        "PrintFlexprinting",
        "PrintExtrusion",
        "PrintRerolling",
        "PrintConfection",
    ]:
        assert procedure in text
