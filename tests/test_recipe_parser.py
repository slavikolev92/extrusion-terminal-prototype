from __future__ import annotations

from decimal import Decimal

from app.recipe_parser import (
    ParsedRecipeComponent,
    parse_recipe_cell,
    parse_recipe_source_fields,
)


def error_messages(result):
    return tuple(error.message for error in result.errors)


def test_parse_structured_recipe_fields_returns_components_and_exact_total():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "LDPE; Rompetrol Midilena B20/03 | 77%",
            "linear_pe": "LLDPE; SABIC 119ZJ | 18%",
            "antistatic": "Antistatic Additive; Novachem AT 04673 LD | 2%",
            "masterbatch": "White Masterbatch; Polibach White 8000 ET | 3%",
        }
    )

    assert result.ok
    assert result.errors == ()
    assert result.total_percent == Decimal("100")
    assert result.components == (
        ParsedRecipeComponent(
            component_key="raw_material_a",
            source_text="LDPE; Rompetrol Midilena B20/03 | 77%",
            material_category="LDPE",
            planned_material="Rompetrol Midilena B20/03",
            recipe_percent=Decimal("77"),
        ),
        ParsedRecipeComponent(
            component_key="linear_pe",
            source_text="LLDPE; SABIC 119ZJ | 18%",
            material_category="LLDPE",
            planned_material="SABIC 119ZJ",
            recipe_percent=Decimal("18"),
        ),
        ParsedRecipeComponent(
            component_key="antistatic",
            source_text="Antistatic Additive; Novachem AT 04673 LD | 2%",
            material_category="Antistatic Additive",
            planned_material="Novachem AT 04673 LD",
            recipe_percent=Decimal("2"),
        ),
        ParsedRecipeComponent(
            component_key="masterbatch",
            source_text="White Masterbatch; Polibach White 8000 ET | 3%",
            material_category="White Masterbatch",
            planned_material="Polibach White 8000 ET",
            recipe_percent=Decimal("3"),
        ),
    )


def test_parse_ignores_empty_cells_when_non_empty_rows_total_100():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "LDPE; Rompetrol B20/03 | 80%",
            "raw_material_b": "",
            "raw_material_c": None,
            "linear_pe": "LLDPE; SABIC 119ZJ | 20%",
            "antistatic": "",
            "masterbatch": "",
            "chalk": "",
        }
    )

    assert result.ok
    assert result.total_percent == Decimal("100")
    assert [component.component_key for component in result.components] == [
        "raw_material_a",
        "linear_pe",
    ]


def test_parse_cell_splits_on_final_pipe():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE; Producer | Internal grade note B20/03 | 100%",
    )

    assert errors == ()
    assert component == ParsedRecipeComponent(
        component_key="raw_material_a",
        source_text="LDPE; Producer | Internal grade note B20/03 | 100%",
        material_category="LDPE",
        planned_material="Producer | Internal grade note B20/03",
        recipe_percent=Decimal("100"),
    )


def test_parse_semicolon_cell_with_multi_word_category():
    component, errors = parse_recipe_cell(
        "masterbatch",
        "UV Protection; Additech UV Shield XZ-204 | 2%",
    )

    assert errors == ()
    assert component == ParsedRecipeComponent(
        component_key="masterbatch",
        source_text="UV Protection; Additech UV Shield XZ-204 | 2%",
        material_category="UV Protection",
        planned_material="Additech UV Shield XZ-204",
        recipe_percent=Decimal("2"),
    )


def test_parse_normalizes_spacing_decimal_comma_and_preserves_category_case():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "  ldpe  ;  Rompetrol   B20/03  |  97,5 %  ",
            "masterbatch": "uv; Stabilizer 123 | 2.5%",
        }
    )

    assert result.ok
    assert result.total_percent == Decimal("100.0")
    assert result.components[0] == ParsedRecipeComponent(
        component_key="raw_material_a",
        source_text="  ldpe  ;  Rompetrol   B20/03  |  97,5 %  ",
        material_category="ldpe",
        planned_material="Rompetrol B20/03",
        recipe_percent=Decimal("97.5"),
    )
    assert result.components[1] == ParsedRecipeComponent(
        component_key="masterbatch",
        source_text="uv; Stabilizer 123 | 2.5%",
        material_category="uv",
        planned_material="Stabilizer 123",
        recipe_percent=Decimal("2.5"),
    )


def test_parse_legacy_fallback_splits_first_token_as_category():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Rompetrol Midilena B20/03 | 38%",
    )

    assert errors == ()
    assert component == ParsedRecipeComponent(
        component_key="raw_material_a",
        source_text="LDPE Rompetrol Midilena B20/03 | 38%",
        material_category="LDPE",
        planned_material="Rompetrol Midilena B20/03",
        recipe_percent=Decimal("38"),
    )


def test_parse_legacy_fallback_preserves_category_spelling():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "reldpe Natural Regranulate | 100%",
        }
    )

    assert result.ok
    assert result.components[0].material_category == "reldpe"


def test_parse_requires_material_for_legacy_fallback():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "reLDPE | 80%",
            "linear_pe": "LLDPE; 119ZJ | 20%",
        }
    )

    assert not result.ok
    assert result.total_percent == Decimal("20")
    assert error_messages(result) == ("липсва материал след категория",)


def test_parse_reports_missing_final_pipe():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Rompetrol B20/03 100%",
    )

    assert component is None
    assert errors[0].component_key == "raw_material_a"
    assert errors[0].source_text == "LDPE Rompetrol B20/03 100%"
    assert errors[0].message == "липсва разделител |"


def test_parse_requires_percent_symbol():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Rompetrol B20/03 | 100",
    )

    assert component is None
    assert errors[0].message == "липсва процент"


def test_parse_reports_missing_category():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "; Rompetrol B20/03 | 38%",
    )

    assert component is None
    assert errors[0].message == "липсва категория"


def test_parse_reports_missing_material_after_semicolon_category():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE; | 38%",
    )

    assert component is None
    assert errors[0].message == "липсва материал след категория"


def test_parse_rejects_missing_identity_before_percent_delimiter():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        " | 100%",
    )

    assert component is None
    assert errors[0].message == "липсва категория"


def test_parse_rejects_invalid_percent_text():
    component, errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Rompetrol B20/03 | one hundred%",
    )

    assert component is None
    assert errors[0].message == "невалиден процент"


def test_parse_rejects_zero_and_negative_percentages():
    zero_component, zero_errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Rompetrol B20/03 | 0%",
    )
    negative_component, negative_errors = parse_recipe_cell(
        "raw_material_a",
        "LDPE Rompetrol B20/03 | -1%",
    )

    assert zero_component is None
    assert zero_errors[0].message == "процентът трябва да е по-голям от 0%"
    assert negative_component is None
    assert negative_errors[0].message == "невалиден процент"


def test_parse_requires_total_percent_to_be_exactly_100():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "LDPE Rompetrol B20/03 | 80%",
            "linear_pe": "LLDPE SABIC 119ZJ | 19%",
        }
    )

    assert not result.ok
    assert result.total_percent == Decimal("99")
    assert error_messages(result) == ("сборът на процентите трябва да е точно 100%",)
    assert result.errors[0].component_key == "__total__"


def test_parse_returns_cell_errors_without_adding_total_error():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "LDPE Rompetrol B20/03 | 80%",
            "linear_pe": "LLDPE SABIC 119ZJ | 20",
        }
    )

    assert not result.ok
    assert result.total_percent == Decimal("80")
    assert error_messages(result) == ("липсва процент",)


def test_parser_source_fields_match_workbook_recipe_field_order():
    from app.recipe_parser import RECIPE_SOURCE_FIELDS

    assert RECIPE_SOURCE_FIELDS == (
        "raw_material_a",
        "raw_material_b",
        "raw_material_c",
        "linear_pe",
        "antistatic",
        "masterbatch",
        "chalk",
    )


def test_parser_does_not_require_all_mapping_keys_to_be_present():
    result = parse_recipe_source_fields(
        {
            "raw_material_a": "LDPE Rompetrol B20/03 | 100%",
            "unrelated_field": "ignored",
        }
    )

    assert result.ok
    assert len(result.components) == 1
    assert result.components[0].component_key == "raw_material_a"
