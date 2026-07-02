from __future__ import annotations

import asyncio
import csv
import io
import re
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.requests import Request

from app import db
from app.db import STALE_CARD_MESSAGE
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import (
    TERMINAL_CARD_UNAVAILABLE_MESSAGE,
    app,
    delete_selected_roll_weight,
    finish_terminal_card,
    progress_percent,
    remaining_gross_display,
    save_roll_weight,
    save_terminal_roll_corrections,
    save_tare_weight,
    target_gross_decimal,
    terminal_card,
    terminal_context,
)
from app.rules import RuleResult


def csv_bytes(*rows: dict[str, str]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")


def extrusion_row(order_number: str, **overrides: str) -> dict[str, str]:
    row = {
        "order_number": order_number,
        "customer": f"V8 Customer {order_number}",
        "product_type": "ТСФ 890/0.082",
        "quantity_1": "500",
        "unit_1": "kg",
        "quantity_2": "5",
        "unit_2": "ролки",
        "product_form": "плоско",
        "material": "LDPE",
        "size_thickness": "890 / 0.082",
        "notes": "Важна бележка за оператор.",
        "extrusion_flag": "da",
        "extrusion_folding": "single",
        "extrusion_next_operation": "rewind",
        "extrusion_treatment": "corona",
        "raw_material_a": "LDPE A | 50%",
        "raw_material_b": "LLDPE B | 30%",
        "raw_material_c": "MDPE HDPE C | 5%",
        "linear_pe": "LLDPE Линеен PE | 8%",
        "antistatic": "Antistatic Антистатик 1% | 1%",
        "masterbatch": "Masterbatch Бял мастербач | 4%",
        "chalk": "Filler Креда 5% | 2%",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def import_ready_card(order_number: str, **overrides: str) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number, **overrides)),
        overwrite_existing=False,
    )
    assert result.rows_imported == 1
    with db.connect() as connection:
        return int(
            connection.execute(
                "SELECT id FROM cards WHERE order_number = ?",
                (order_number,),
            ).fetchone()["id"]
        )


def release_ready_card(
    order_number: str,
    machine_id: int,
    sequence: int,
    **overrides: str,
) -> int:
    card_id = import_ready_card(order_number, **overrides)
    assert db.release_card(
        card_id,
        machine_id,
        sequence,
        db.fetch_admin_card_detail(card_id)["version"],
        max_roll_weight="62.5",
    ).ok
    return card_id


def card_version(card_id: int) -> int:
    return int(db.fetch_terminal_card_detail(card_id)["version"])


def complete_card(card_id: int) -> None:
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok
    assert db.finish_card(card_id, card_version(card_id)).ok


def render_terminal(
    card_id: int | None = None,
    machine_id: int | None = None,
    **extra: object,
) -> str:
    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["url_for"] = lambda name, **kwargs: f"/static{kwargs.get('path', '')}"
    return env.get_template("terminal.html").render(**terminal_context(card_id, machine_id, **extra))


def data_block(html: str, attribute: str, value: str) -> str:
    match = re.search(
        rf'<[^>]+{attribute}="{re.escape(value)}"[^>]*>.*?</[^>]+>',
        html,
        flags=re.S,
    )
    assert match
    return match.group(0)


def form_block(html: str, action: str) -> str:
    match = re.search(
        rf'<form[^>]* action="{re.escape(action)}"[^>]*>.*?</form>',
        html,
        flags=re.S,
    )
    assert match is not None
    return match.group(0)


def form_blocks(html: str, action: str) -> list[str]:
    forms = [
        match.group(0)
        for match in re.finditer(
            rf'<form[^>]* action="{re.escape(action)}"[^>]*>.*?</form>',
            html,
            flags=re.S,
        )
    ]
    assert forms
    return forms


def roll_row_block(html: str, roll_id: int) -> str:
    start_marker = f'<div class="roll-row" data-roll-id="{roll_id}">'
    start = html.find(start_marker)
    assert start != -1
    next_start = html.find('<div class="roll-row" data-roll-id="', start + len(start_marker))
    correction_form_end = html.find("</form>", start)
    table_end = html.find('<div class="totals">', start)
    end_candidates = [
        position for position in (next_start, correction_form_end, table_end) if position != -1
    ]
    assert end_candidates
    return html[start : min(end_candidates)]


def roll_entry_block(html: str) -> str:
    start = html.find('<div class="roll-entry">')
    assert start != -1
    end = html.find('<div class="roll-table">', start)
    assert end != -1
    return html[start:end]


def css_rules(html: str, selector_pattern: str) -> str:
    match = re.search(rf"{selector_pattern}\s*\{{(?P<rules>.*?)\}}", html, flags=re.S)
    assert match is not None
    return match.group("rules")


def css_rules_all(html: str, selector_pattern: str) -> list[str]:
    rules = [
        match.group("rules")
        for match in re.finditer(rf"{selector_pattern}\s*\{{(?P<rules>.*?)\}}", html, flags=re.S)
    ]
    assert rules
    return rules


def make_test_request(path: str, method: str = "POST") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
            "app": app,
        }
    )


async def post_form_to_app(path: str, data: dict[str, str]) -> tuple[int, dict[str, str]]:
    body = urlencode(data).encode("utf-8")
    messages = []

    async def receive():
        return {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }

    async def send(message):
        messages.append(message)

    await app(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [
                (b"content-type", b"application/x-www-form-urlencoded"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        },
        receive,
        send,
    )
    response_start = next(message for message in messages if message["type"] == "http.response.start")
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in response_start["headers"]
    }
    return int(response_start["status"]), headers


def test_terminal_v8_route_is_registered_and_cancel_restore_routes_are_absent():
    route_paths = {route.path for route in app.routes}

    assert "/terminal" in route_paths
    assert "/terminal/cards/{card_id}/cancel" not in route_paths
    assert "/terminal/cards/{card_id}/restore" not in route_paths


def test_terminal_v8_renders_four_machine_navigation_controls(connection):
    release_ready_card("26100", machine_id=1, sequence=1)

    html = render_terminal()
    empty_machine_html = render_terminal(machine_id=2)

    assert len(re.findall(r'<a class="machine-tab', html)) == 4
    assert "/static/assets/machine-icon.png" in html
    assert 'href="/terminal/cards/' in html
    assert 'href="/terminal?machine_id=2"' in html
    assert "Машина 1" in html
    assert "Машина 2" in html
    assert "Машина 3" in html
    assert "Машина 4" in html
    assert "Машина 2" in empty_machine_html
    assert "Няма активна поръчка за Машина 2." in empty_machine_html
    assert re.search(
        r'<a class="machine-tab idle selected" href="/terminal\?machine_id=2">',
        empty_machine_html,
    )


def test_terminal_v8_selected_machine_navigation_does_not_use_heavy_focus_ring(connection):
    release_ready_card("26103", machine_id=1, sequence=1)

    html = render_terminal()

    selected_style_match = re.search(
        r"\.machine-tab\.selected\s*\{(?P<rules>.*?)\}",
        html,
        flags=re.S,
    )
    assert selected_style_match is not None
    selected_style = selected_style_match.group("rules")
    assert "outline:" not in selected_style
    assert "box-shadow:" not in selected_style
    assert "border-color: #0b355f;" in selected_style
    assert "border-width: 10px 3px 3px;" in selected_style


def test_terminal_v8_action_buttons_are_vertically_aligned(connection):
    release_ready_card("26124", machine_id=1, sequence=1)

    html = render_terminal()

    actions_rules = css_rules(html, r"(?m)^    \.actions")
    action_form_rules = css_rules(html, r"(?m)^    \.actions form")
    action_button_rules = css_rules(html, r"(?m)^    \.actions \.action-button")

    assert "align-items: center;" in actions_rules
    assert "display: flex;" in action_form_rules
    assert "align-items: center;" in action_form_rules
    assert "height: 38px;" in action_button_rules
    assert "min-height: 38px;" in action_button_rules
    assert "align-items: center;" in action_button_rules
    assert "line-height: 1;" in action_button_rules


def test_terminal_v8_machine_card_kpi_text_is_semibold(connection):
    release_ready_card("26113", machine_id=1, sequence=1)

    html = render_terminal()

    machine_name_style = re.search(
        r"\.machine-tab-name\s*\{(?P<rules>.*?)\}",
        html,
        flags=re.S,
    )
    assert machine_name_style is not None
    assert "font-weight: 900;" in machine_name_style.group("rules")

    for selector in (
        r"\.machine-tab-meta",
        r"\.machine-tab-customer",
        r"\.machine-tab-product",
        r"\.machine-tab-progress",
    ):
        style_match = re.search(rf"{selector}\s*\{{(?P<rules>.*?)\}}", html, flags=re.S)
        assert style_match is not None
        assert "font-weight: 600;" in style_match.group("rules")


def test_terminal_v8_uses_defined_primary_and_secondary_text_tokens(connection):
    release_ready_card("26117", machine_id=1, sequence=1)

    html = render_terminal()

    root_rules = css_rules(html, r":root")
    assert "--primary-text: #222222;" in root_rules
    assert "--secondary-text: #565656;" in root_rules


def test_terminal_v8_machine_cards_apply_primary_and_secondary_text_colors(connection):
    release_ready_card("26118", machine_id=1, sequence=1)

    html = render_terminal()

    assert "color: var(--primary-text);" in css_rules(html, r"(?m)^    \.machine-tab-name")
    assert "color: var(--primary-text);" in css_rules(html, r"(?m)^    \.machine-tab-customer")
    assert any(
        "color: var(--secondary-text);" in rules
        for rules in css_rules_all(html, r"(?m)^    \.machine-tab-product")
    )


def test_terminal_v8_details_and_rolls_apply_primary_and_secondary_text_colors(
    connection,
):
    card_id = release_ready_card("26119", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "100").ok

    html = render_terminal(card_id)

    assert "color: var(--primary-text);" in css_rules(html, r"(?m)^    \.title h2")
    assert any(
        "color: var(--primary-text);" in rules
        for rules in css_rules_all(html, r"(?m)^    \.panel-head,\s*\.recipe-panel-head")
    )
    assert "color: var(--secondary-text);" in css_rules(
        html,
        r"\.details-panel \.field-label,\s*"
        r"\.details-panel \.section-title,\s*"
        r"\.roll-entry \.field-label",
    )
    assert "color: var(--primary-text);" in css_rules(html, r"\.details-panel \.value")
    assert "color: var(--primary-text);" in css_rules(html, r"\.notes")

    roll_entry_label_rules = css_rules_all(html, r"(?m)^    \.roll-entry \.field-label")
    assert any("color: var(--secondary-text);" in rules for rules in roll_entry_label_rules)
    assert any("font-size: 17px;" in rules for rules in roll_entry_label_rules)
    assert any("font-weight: 400;" in rules for rules in roll_entry_label_rules)
    assert any("line-height: 1.2;" in rules for rules in roll_entry_label_rules)
    assert "color: var(--secondary-text);" in css_rules(html, r"(?m)^    \.roll-head")
    roll_row_rules = css_rules_all(html, r"(?m)^    \.roll-row")
    roll_row_input_rules = css_rules(html, r"(?m)^    \.roll-row input")
    assert any(
        "color: var(--primary-text);" in rules
        for rules in roll_row_rules
    )
    assert any("font-weight: 600;" in rules for rules in roll_row_rules)
    assert "font-weight: 600;" in roll_row_input_rules
    assert "color: var(--secondary-text);" in css_rules(html, r"(?m)^    \.totals \.field-label")
    assert "color: var(--primary-text);" in css_rules(html, r"(?m)^    \.metric \.big")


def test_terminal_v8_recipe_table_uses_secondary_text_color(connection):
    release_ready_card("26120", machine_id=1, sequence=1)

    html = render_terminal()

    assert "color: var(--secondary-text);" in css_rules(
        html,
        r"(?m)^    \.recipe-head,\s*\.roll-head",
    )
    for selector in (
        r"\.component",
        r"\.material-planned",
        r"\.recipe-percent",
        r"\.recipe-kg",
        r"\.recipe-row input",
    ):
        assert "color: var(--secondary-text);" in css_rules(html, rf"(?m)^    {selector}")


def test_terminal_v8_details_grid_wraps_by_available_panel_width(connection):
    release_ready_card("26104", machine_id=1, sequence=1)

    html = render_terminal()

    assert "grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));" in html


def test_terminal_v8_selects_requested_machine_focus_card(connection):
    release_ready_card("26115", machine_id=1, sequence=1)
    focused_id = release_ready_card("26116", machine_id=2, sequence=1)

    context = terminal_context(selected_machine_id=2)
    html = render_terminal(machine_id=2)

    assert context["selected_card"]["id"] == focused_id
    assert context["selected_machine_id"] == 2
    assert "Машина 2: №26116" in html
    assert "Няма активна поръчка за Машина 2." not in html


def test_terminal_v8_machine_card_and_machine_default_prefer_running_over_paused(
    connection,
):
    paused_id = release_ready_card("26145", machine_id=2, sequence=1)
    release_ready_card("26146", machine_id=2, sequence=2)
    running_id = release_ready_card("26147", machine_id=2, sequence=3)
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    context = terminal_context(selected_machine_id=2)
    html = render_terminal(machine_id=2)

    assert context["selected_card"]["id"] == running_id
    assert context["selected_card"]["order_number"] == "26147"
    assert f'href="/terminal/cards/{running_id}"' in html
    assert "Машина 2: №26147" in html
    machine_tab_match = re.search(
        rf'<a class="machine-tab running selected" href="/terminal/cards/{running_id}">.*?</a>',
        html,
        flags=re.S,
    )
    assert machine_tab_match is not None
    machine_tab = machine_tab_match.group(0)
    assert "Изработване" in machine_tab
    assert "V8 Customer 26147" in machine_tab


def test_terminal_v8_renders_selected_card_details_and_max_roll_weight(connection):
    card_id = release_ready_card("26101", machine_id=1, sequence=1)

    html = render_terminal(card_id)
    card = terminal_context(card_id)["selected_card"]

    assert "Машина 1: №26101" in html
    assert "ТСФ 890/0.082" in html
    assert "V8 Customer 26101" in html
    assert "500 kg / 5 ролки" in html
    assert "890 / 0.082" in html
    assert "плоско" in html
    assert "LDPE" in html
    assert "Макс. тегло ролка, кг" in html
    assert card["max_roll_weight_display"] == "63"
    assert "62.5" not in html
    assert re.search(r"Макс\. тегло ролка, кг\s*</span>\s*<div class=\"value\">63</div>", html)
    assert "Важна бележка за оператор." in html


def test_terminal_v8_details_panel_labels_and_values_are_deemphasized(connection):
    release_ready_card("26114", machine_id=1, sequence=1)

    html = render_terminal()

    label_style = re.search(
        r"\.details-panel \.field-label,\s*"
        r"\.details-panel \.section-title,\s*"
        r"\.roll-entry \.field-label\s*\{(?P<rules>.*?)\}",
        html,
        flags=re.S,
    )
    value_style = re.search(r"\.details-panel \.value\s*\{(?P<rules>.*?)\}", html, flags=re.S)
    assert label_style is not None
    assert value_style is not None

    label_rules = label_style.group("rules")
    assert "display: block;" in label_rules
    assert "margin-bottom: var(--details-value-gap);" in label_rules
    assert "color: var(--secondary-text);" in label_rules
    assert "font-size: 17px;" in label_rules
    assert "font-weight: 400;" in label_rules
    assert "line-height: 1.2;" in label_rules

    value_rules = value_style.group("rules")
    assert "color: var(--primary-text);" in value_rules
    assert "font-weight: 600;" in value_rules

    assert "row-gap: 22px;" in html
    assert "gap: 20px;" in html


def test_terminal_v8_details_values_and_notes_share_value_rhythm(connection):
    release_ready_card("26123", machine_id=1, sequence=1)

    html = render_terminal()

    root_rules = css_rules(html, r":root")
    label_rules = css_rules(
        html,
        r"\.details-panel \.field-label,\s*"
        r"\.details-panel \.section-title,\s*"
        r"\.roll-entry \.field-label",
    )
    notes_section_rules = css_rules(html, r"(?m)^    \.notes-section")
    notes_rules = css_rules(html, r"(?m)^    \.notes")

    assert "--details-value-gap: 4px;" in root_rules
    assert "margin-bottom: var(--details-value-gap);" in label_rules
    assert "gap: 0;" in notes_section_rules
    assert "font-weight: 600;" in notes_rules

    compact_height_match = re.search(
        r"@media \(max-height: 980px\) \{(?P<rules>.*?)@media \(max-height: 760px\)",
        html,
        flags=re.S,
    )
    short_height_match = re.search(
        r"@media \(max-height: 760px\) \{(?P<rules>.*?)a\.machine-tab,",
        html,
        flags=re.S,
    )
    assert compact_height_match is not None
    assert short_height_match is not None

    for rules in (compact_height_match.group("rules"), short_height_match.group("rules")):
        assert "margin-bottom: 2px;" not in rules
        assert "margin-bottom: 3px;" not in rules
        assert ".notes-section" not in rules


def test_terminal_v8_notes_title_tracks_details_label_style_in_compact_viewports(
    connection,
):
    release_ready_card("26121", machine_id=1, sequence=1)

    html = render_terminal()

    compact_height_match = re.search(
        r"@media \(max-height: 980px\) \{(?P<rules>.*?)@media \(max-height: 760px\)",
        html,
        flags=re.S,
    )
    short_height_match = re.search(
        r"@media \(max-height: 760px\) \{(?P<rules>.*?)a\.machine-tab,",
        html,
        flags=re.S,
    )
    assert compact_height_match is not None
    assert short_height_match is not None

    compact_height_rules = compact_height_match.group("rules")
    assert ".order-section .field-label,\n      .order-section .section-title" in compact_height_rules
    assert "font-size: 13px;" in compact_height_rules
    assert "margin-bottom: 3px;" not in compact_height_rules

    short_height_rules = short_height_match.group("rules")
    assert ".order-section .field-label,\n      .order-section .section-title" in short_height_rules
    assert "font-size: 12px;" in short_height_rules
    assert "margin-bottom: 2px;" not in short_height_rules


def test_terminal_v8_roll_entry_labels_track_details_label_style_in_compact_viewports(
    connection,
):
    release_ready_card("26122", machine_id=1, sequence=1)

    html = render_terminal()

    compact_height_match = re.search(
        r"@media \(max-height: 980px\) \{(?P<rules>.*?)@media \(max-height: 760px\)",
        html,
        flags=re.S,
    )
    short_height_match = re.search(
        r"@media \(max-height: 760px\) \{(?P<rules>.*?)a\.machine-tab,",
        html,
        flags=re.S,
    )
    assert compact_height_match is not None
    assert short_height_match is not None

    compact_height_rules = compact_height_match.group("rules")
    assert ".order-section .field-label,\n      .order-section .section-title,\n      .roll-entry .field-label" in compact_height_rules
    assert "font-size: 13px;" in compact_height_rules
    assert "margin-bottom: 3px;" not in compact_height_rules

    short_height_rules = short_height_match.group("rules")
    assert ".order-section .field-label,\n      .order-section .section-title,\n      .roll-entry .field-label" in short_height_rules
    assert "font-size: 12px;" in short_height_rules
    assert "margin-bottom: 2px;" not in short_height_rules


def test_terminal_v8_recipe_table_follows_details_with_matching_recipe_title(connection):
    card_id = release_ready_card("26240", machine_id=1, sequence=1)

    html = render_terminal(card_id)

    assert '<span>Детайли</span>' in html
    assert re.search(
        r'<div class="panel-head recipe-panel-head">\s*<span>Рецепта</span>\s*</div>',
        html,
    )
    assert '<span>Ролки</span>' in html
    assert 'class="recipe-table"' in html
    assert "Категория" in html
    assert "Планирани материали" in html
    assert ">%<" in html
    assert ">КГ<" in html
    assert "Вложени материали" in html
    assert "Партида" in html
    recipe_html = form_block(html, f"/terminal/cards/{card_id}/materials")
    assert "LDPE" in recipe_html
    assert "A" in recipe_html
    assert "50%" in recipe_html
    assert "250.00" not in recipe_html
    assert re.search(r'<div class="recipe-number recipe-percent">50%</div>', recipe_html)
    assert re.search(r'<div class="recipe-number recipe-kg">250</div>', recipe_html)
    assert 'data-recipe-autosave="true"' in html
    assert f'action="/terminal/cards/{card_id}/materials"' in html
    assert 'name="actual_material__raw_material_a"' in html
    assert 'name="batch_lot__raw_material_a"' in html

    details_body_rules = css_rules(html, r"(?m)^    \.details-body")
    recipe_section_rules = css_rules(html, r"(?m)^    \.recipe-section")
    shared_head_rules = css_rules_all(html, r"(?m)^    \.panel-head,\s*\.recipe-panel-head")

    assert "grid-template-rows: auto auto;" in details_body_rules
    assert "align-content: start;" in details_body_rules
    assert "gap: 22px;" in details_body_rules
    assert "align-content: start;" in recipe_section_rules
    assert any("color: var(--primary-text);" in rules for rules in shared_head_rules)
    assert any("font-size: 21px;" in rules for rules in shared_head_rules)
    assert any("font-weight: 800;" in rules for rules in shared_head_rules)


def test_terminal_v8_recipe_table_aligns_all_values_left(connection):
    release_ready_card("26239", machine_id=1, sequence=1)

    html = render_terminal()

    recipe_head_cell_rules = css_rules(html, r"(?m)^    \.recipe-head div,\s*\.roll-head > div")
    recipe_body_cell_rules = css_rules(html, r"(?m)^    \.recipe-row > div")
    recipe_number_rules = css_rules(html, r"\.recipe-number")

    assert "justify-content: flex-start;" in recipe_head_cell_rules
    assert "text-align: left;" in recipe_head_cell_rules
    assert "justify-content: flex-start;" in recipe_body_cell_rules
    assert "text-align: left;" in recipe_body_cell_rules
    assert "justify-content: flex-start;" in recipe_number_rules
    assert "text-align: left;" in recipe_number_rules
    assert "justify-content: flex-end;" not in recipe_number_rules
    assert "text-align: right;" not in recipe_number_rules


def test_terminal_v8_recipe_and_roll_spacing_is_balanced_for_compact_workstations(
    connection,
):
    release_ready_card("26238", machine_id=1, sequence=1)

    html = render_terminal()

    recipe_row_rules = css_rules_all(html, r"(?m)^    \.recipe-row")
    recipe_cell_rules = css_rules(html, r"(?m)^    \.recipe-row > div")
    roll_entry_rules = css_rules_all(html, r"(?m)^    \.roll-entry")
    roll_entry_label_rules = css_rules_all(html, r"(?m)^    \.roll-entry \.field-label")
    roll_entry_input_rules = css_rules(html, r"(?m)^    \.roll-entry input")
    roll_entry_button_rules = css_rules_all(html, r"(?m)^    \.roll-entry button")
    roll_entry_feedback_rules = css_rules(html, r"(?m)^    \.roll-entry \.field-error-slot")
    roll_head_rules = css_rules_all(html, r"(?m)^    \.roll-head")

    assert any("min-height: 52px;" in rules for rules in recipe_row_rules)
    assert "align-items: center;" in recipe_cell_rules
    assert "padding: 6px 9px;" in recipe_cell_rules
    assert any("padding: 6px 8px;" in rules for rules in roll_entry_rules)
    assert any("margin-bottom: 6px;" in rules for rules in roll_entry_label_rules)
    assert "min-height: 36px;" in roll_entry_input_rules
    assert any("min-height: 36px;" in rules for rules in roll_entry_button_rules)
    assert "min-height: 0;" in roll_entry_feedback_rules
    assert any("min-height: 36px;" in rules for rules in roll_head_rules)

    compact_height_match = re.search(
        r"@media \(max-height: 980px\) \{(?P<rules>.*?)@media \(max-height: 760px\)",
        html,
        flags=re.S,
    )
    short_height_match = re.search(
        r"@media \(max-height: 760px\) \{(?P<rules>.*?)a\.machine-tab,",
        html,
        flags=re.S,
    )
    assert compact_height_match is not None
    assert short_height_match is not None

    compact_height_rules = compact_height_match.group("rules")
    assert ".recipe-row {\n        min-height: 36px;" in compact_height_rules
    assert ".recipe-row > div {\n        padding: 4px 7px;" in compact_height_rules
    assert ".roll-entry .field-label {\n        margin-bottom: 5px;" in compact_height_rules

    short_height_rules = short_height_match.group("rules")
    assert ".recipe-row {\n        min-height: 32px;" in short_height_rules
    assert ".recipe-row > div {\n        padding: 3px 6px;" in short_height_rules
    assert ".roll-entry .field-label {\n        margin-bottom: 5px;" in short_height_rules


def test_terminal_v8_recipe_and_roll_table_headers_share_style(connection):
    release_ready_card("26237", machine_id=1, sequence=1)

    html = render_terminal()

    shared_head_rules = css_rules(html, r"(?m)^    \.recipe-head,\s*\.roll-head")
    shared_head_cell_rules = css_rules(html, r"(?m)^    \.recipe-head div,\s*\.roll-head > div")
    recipe_body_cell_rules = css_rules(html, r"(?m)^    \.recipe-row > div")
    roll_body_cell_rules = css_rules(html, r"(?m)^    \.roll-row > div")

    assert "min-height: 36px;" in shared_head_rules
    assert "background: #f1f4f7;" in shared_head_rules
    assert "color: var(--secondary-text);" in shared_head_rules
    assert "font-size: 13px;" in shared_head_rules
    assert "font-weight: 700;" in shared_head_rules
    assert "line-height: 1.15;" in shared_head_rules
    assert "text-transform:" not in shared_head_rules

    assert "padding: 6px 9px;" in shared_head_cell_rules
    assert "align-items: center;" in shared_head_cell_rules
    assert "justify-content: flex-start;" in shared_head_cell_rules
    assert "text-align: left;" in shared_head_cell_rules
    assert "padding: 6px 9px;" in recipe_body_cell_rules
    assert "padding: 4px 7px;" in roll_body_cell_rules

    compact_height_match = re.search(
        r"@media \(max-height: 980px\) \{(?P<rules>.*?)@media \(max-height: 760px\)",
        html,
        flags=re.S,
    )
    short_height_match = re.search(
        r"@media \(max-height: 760px\) \{(?P<rules>.*?)a\.machine-tab,",
        html,
        flags=re.S,
    )
    assert compact_height_match is not None
    assert short_height_match is not None

    compact_height_rules = compact_height_match.group("rules")
    assert ".recipe-head,\n      .roll-head {\n        min-height: 32px;" in compact_height_rules
    assert ".recipe-head div,\n      .roll-head > div {\n        padding: 5px 7px;" in compact_height_rules

    short_height_rules = short_height_match.group("rules")
    assert ".recipe-head,\n      .roll-head {\n        min-height: 30px;" in short_height_rules
    assert ".recipe-head div,\n      .roll-head > div {\n        padding: 4px 6px;" in short_height_rules


def test_terminal_v8_renders_category_only_recipe_without_na_control_value(connection):
    card_id = release_ready_card(
        "26241",
        machine_id=1,
        sequence=1,
        raw_material_a="reLDPE | 80%",
        linear_pe="LLDPE SABIC 119ZJ | 20%",
        raw_material_b="",
        raw_material_c="",
        antistatic="",
        masterbatch="",
        chalk="",
    )

    html = render_terminal(card_id)
    recipe_html = form_block(html, f"/terminal/cards/{card_id}/materials")

    assert "reLDPE" in recipe_html
    assert "80%" in recipe_html
    assert "400.00" not in recipe_html
    assert "400" in recipe_html
    assert "SABIC 119ZJ" in recipe_html
    assert 'name="actual_material__raw_material_b"' not in recipe_html
    assert 'name="actual_material__raw_material_c"' not in recipe_html
    assert 'name="actual_material__antistatic"' not in recipe_html
    assert 'name="actual_material__masterbatch"' not in recipe_html
    assert 'name="actual_material__chalk"' not in recipe_html
    assert "N/A" not in recipe_html
    assert 'name="actual_material__raw_material_a"' in recipe_html
    assert 'name="batch_lot__raw_material_a"' in recipe_html


def test_terminal_v8_recipe_display_rounds_operator_percent_and_kg_values(connection):
    card_id = release_ready_card(
        "26242",
        machine_id=1,
        sequence=1,
        quantity_1="1250",
        raw_material_a="LDPE A | 37.5%",
        raw_material_b="LLDPE B | 23.5%",
        raw_material_c="MDPE C | 12%",
        linear_pe="reLDPE D | 10%",
        antistatic="Antistatic E | 2.5%",
        masterbatch="Masterbatch F | 9%",
        chalk="Filler G | 5.5%",
    )

    rows = {row["field"]: row for row in terminal_context(card_id)["recipe_rows"]}

    assert rows["raw_material_a"]["recipe_percent"] == "38%"
    assert rows["raw_material_a"]["planned_kg"] == "469"
    assert rows["raw_material_b"]["recipe_percent"] == "24%"
    assert rows["raw_material_b"]["planned_kg"] == "294"
    assert rows["antistatic"]["recipe_percent"] == "3%"
    assert rows["antistatic"]["planned_kg"] == "31"
    assert rows["chalk"]["recipe_percent"] == "6%"
    assert rows["chalk"]["planned_kg"] == "69"


def test_terminal_v8_recipe_body_values_use_homogeneous_regular_style(connection):
    release_ready_card("26243", machine_id=1, sequence=1)

    html = render_terminal()

    component_style = re.search(r"\.component\s*\{(?P<rules>.*?)\}", html, flags=re.S)
    planned_style = re.search(r"\.material-planned\s*\{(?P<rules>.*?)\}", html, flags=re.S)
    percent_style = re.search(r"\.recipe-percent\s*\{(?P<rules>.*?)\}", html, flags=re.S)
    kg_style = re.search(r"\.recipe-kg\s*\{(?P<rules>.*?)\}", html, flags=re.S)
    input_style = re.search(r"\.recipe-row input\s*\{(?P<rules>.*?)\}", html, flags=re.S)
    assert component_style is not None
    assert planned_style is not None
    assert percent_style is not None
    assert kg_style is not None
    assert input_style is not None

    assert "font-weight: 400;" in component_style.group("rules")
    assert "font-weight: 400;" in planned_style.group("rules")
    assert "font-weight: 400;" in percent_style.group("rules")
    assert "font-weight: 400;" in kg_style.group("rules")
    assert "font-weight: 400;" in input_style.group("rules")

    assert "font-size: 17px;" in component_style.group("rules")
    assert "font-size: 17px;" in planned_style.group("rules")
    assert "font-size: 16px;" in percent_style.group("rules")
    assert "font-size: 16px;" in kg_style.group("rules")
    assert "font-size: 17px;" in input_style.group("rules")

    assert "color: var(--secondary-text);" in component_style.group("rules")
    assert "color: var(--secondary-text);" in planned_style.group("rules")
    assert "color: var(--secondary-text);" in percent_style.group("rules")
    assert "color: var(--secondary-text);" in kg_style.group("rules")
    assert "color: var(--secondary-text);" in input_style.group("rules")

    assert (
        "grid-template-columns: 132px minmax(152px, 1fr) 86px 86px "
        "minmax(140px, .72fr) minmax(110px, .52fr);"
    ) in html
    assert (
        "grid-template-columns: 96px minmax(124px, 1fr) 76px 76px "
        "minmax(118px, .62fr) minmax(92px, .48fr);"
    ) in html
    assert "padding: 0 14px;" in html


def test_terminal_v8_renders_recipe_queue_and_completed_lookup(connection):
    selected_id = release_ready_card("26102", machine_id=1, sequence=1)
    release_ready_card("26103", machine_id=1, sequence=2, customer="Queued Customer")
    completed_id = release_ready_card("26104", machine_id=2, sequence=1, customer="Done Customer")
    complete_card(completed_id)
    cancelled_id = release_ready_card("26105", machine_id=3, sequence=1, customer="Hidden Customer")
    assert db.cancel_card(cancelled_id, card_version(cancelled_id)).ok

    html = render_terminal(selected_id)

    recipe_html = form_block(html, f"/terminal/cards/{selected_id}/materials")
    assert "A" in recipe_html
    assert "B" in recipe_html
    assert "HDPE C" in recipe_html
    assert "Линеен PE" in recipe_html
    assert "Антистатик 1%" in recipe_html
    assert "Бял мастербач" in recipe_html
    assert "Креда 5%" in recipe_html
    assert "50%" in recipe_html
    assert "30%" in recipe_html
    assert "250.00" not in recipe_html
    assert "150.00" not in recipe_html
    assert "250" in recipe_html
    assert "150" in recipe_html
    assert "Марка" not in html
    assert "v8-recipe-actions" not in html
    assert "Queued Customer" in html
    assert "№26103" in html
    assert "Done Customer" in html
    assert "№26104" in html
    assert "Hidden Customer" not in html
    assert "№26105" not in html


def test_terminal_v8_labels_completed_lookup_as_produced_orders(connection):
    completed_id = release_ready_card(
        "26184",
        machine_id=1,
        sequence=1,
        customer="Produced Customer",
    )
    complete_card(completed_id)

    html = render_terminal(completed_id)

    assert "Произведени поръчки" in html
    assert "Завършени поръчки" not in html
    assert "Филтри за произведени поръчки" in html
    assert "Затвори произведените поръчки" in html
    assert "Няма намерени произведени поръчки." in html


def test_terminal_v8_recipe_inputs_are_named_for_all_rows(connection):
    card_id = release_ready_card("26140", machine_id=1, sequence=1)
    entries = {
        "raw_material_a": {
            "actual_material_used": "Actual A",
            "batch_lot": "Batch A",
        },
        "raw_material_b": {
            "actual_material_used": "Actual B",
            "batch_lot": "Batch B",
        },
        "raw_material_c": {
            "actual_material_used": "Actual C",
            "batch_lot": "Batch C",
        },
        "linear_pe": {
            "actual_material_used": "Actual Linear",
            "batch_lot": "Batch Linear",
        },
        "antistatic": {
            "actual_material_used": "Actual Antistatic",
            "batch_lot": "Batch Antistatic",
        },
        "masterbatch": {
            "actual_material_used": "Actual Masterbatch",
            "batch_lot": "Batch Masterbatch",
        },
        "chalk": {
            "actual_material_used": "Actual Chalk",
            "batch_lot": "Batch Chalk",
        },
    }
    assert db.update_terminal_recipe_actual_entries(card_id, card_version(card_id), entries).ok

    html = render_terminal(card_id)

    for field, entry in entries.items():
        assert f'name="actual_material__{field}"' in html
        assert f'name="batch_lot__{field}"' in html
        assert f'value="{entry["actual_material_used"]}"' in html
        assert f'value="{entry["batch_lot"]}"' in html
    assert 'name="actual_raw_material_used"' not in html
    assert 'name="raw_material_batch_lot"' not in html


def test_terminal_v8_recipe_form_marks_exit_autosave_contract(connection):
    card_id = release_ready_card("26143", machine_id=1, sequence=1)

    html = render_terminal(card_id)

    recipe_form = form_block(
        html,
        f"/terminal/cards/{card_id}/materials",
    )
    assert 'data-recipe-autosave="true"' in recipe_form
    assert 'name="actual_material__raw_material_a"' in recipe_form
    assert 'name="batch_lot__raw_material_a"' in recipe_form
    assert '<button type="submit" hidden>Запази материал</button>' in recipe_form


def test_terminal_v8_recipe_autosave_script_tracks_dirty_exit_and_beforeunload(
    connection,
):
    card_id = release_ready_card("26144", machine_id=1, sequence=1)

    html = render_terminal(card_id)

    assert 'form[data-recipe-autosave="true"]' in html
    assert 'form[data-recipe-autosave="true"], form[data-dirty-autosave="true"]' in html
    assert "bindDirtyAutosaveForm" in html
    assert "const isDirty" in html
    assert "submitDirtyForm" in html
    assert 'event.key === "Enter"' in html
    assert "group.contains(nextTarget)" in html
    assert 'document.addEventListener("click"' in html
    assert "event.stopPropagation()" in html
    assert re.search(
        r"const submittingState = autosaveStates\.find\(\(state\) => state\.isSubmitting\(\)\);\s*"
        r"if \(submittingState\) {\s*"
        r"event\.preventDefault\(\);\s*"
        r"event\.stopPropagation\(\);\s*"
        r"return;\s*"
        r"}",
        html,
    )
    assert 'window.addEventListener("beforeunload"' in html


def test_target_gross_uses_quantity_1_and_ignores_quantity_units_and_secondary_quantity(
    connection,
):
    card_id = release_ready_card(
        "26141",
        machine_id=1,
        sequence=1,
        quantity_1="100",
        unit_1="ролки",
        quantity_2="9999",
        unit_2="kg",
    )
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "140.25").ok

    card = terminal_context(card_id)["selected_card"]

    assert target_gross_decimal(card) == 100
    assert card["target_gross_weight"] == "100.00"
    assert remaining_gross_display(card) == "0.00"
    assert progress_percent(card) == 100
    assert card["remaining_gross_weight"] == "0.00"


def test_terminal_v8_rounds_machine_progress_and_totals_but_preserves_roll_decimals(
    connection,
):
    card_id = release_ready_card(
        "26145",
        machine_id=1,
        sequence=1,
        quantity_1="1000",
    )
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "0.25").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "100.50").ok

    html = render_terminal(card_id)

    assert '<span class="machine-tab-qty">101 / 1000 кг</span>' in html
    assert re.search(
        r'<span class="field-label">Бруто</span>\s*<div class="big">101</div>',
        html,
    )
    assert re.search(
        r'<span class="field-label">Оставащи</span>\s*<div class="big">900</div>',
        html,
    )
    assert re.search(
        r'<span class="field-label">Нето</span>\s*<div class="big">100</div>',
        html,
    )
    assert re.search(r'value="100\.50?"', html)
    assert "<div>100.25</div>" in html
    assert "100.50 / 1000.00 кг" not in html


def test_terminal_v8_keeps_totals_visible_if_server_context_lacks_new_display_fields(
    connection,
):
    card_id = release_ready_card(
        "26146",
        machine_id=1,
        sequence=1,
        quantity_1="1000",
    )
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "0.25").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "100.50").ok

    context = terminal_context(card_id)
    context["selected_card"].pop("total_gross_weight_display", None)
    context["selected_card"].pop("remaining_gross_weight_display", None)
    context["selected_card"].pop("total_net_weight_display", None)
    for queue in context["machine_queues"]:
        focus_card = queue.get("focus_card")
        if focus_card:
            focus_card.pop("target_gross_weight_display", None)

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["url_for"] = lambda name, **kwargs: f"/static{kwargs.get('path', '')}"
    html = env.get_template("terminal.html").render(**context)

    assert re.search(r'<span class="machine-tab-qty">101 / [^<]+ кг</span>', html)
    assert re.search(
        r'<span class="field-label">Бруто</span>\s*<div class="big">\S+</div>',
        html,
    )
    assert re.search(
        r'<span class="field-label">Оставащи</span>\s*<div class="big">\S+</div>',
        html,
    )
    assert re.search(
        r'<span class="field-label">Нето</span>\s*<div class="big">\S+</div>',
        html,
    )


def test_terminal_v8_does_not_show_fake_zero_target_when_quantity_1_is_invalid(
    connection,
):
    card_id = release_ready_card(
        "26142",
        machine_id=1,
        sequence=1,
    )
    card = db.fetch_admin_card_detail(card_id)
    fields = {field: str(card[field] or "") for field in IMPORT_FIELDS}
    fields["quantity_1"] = ""
    fields["unit_1"] = "kg"
    fields["quantity_2"] = "20"
    fields["unit_2"] = "kg"
    assert db.update_admin_imported_fields(card_id, card_version(card_id), fields).ok

    html = render_terminal(card_id)
    card = terminal_context(card_id)["selected_card"]

    assert target_gross_decimal(card) is None
    assert card["target_gross_weight"] is None
    assert card["remaining_gross_weight"] is None
    assert '<span class="machine-tab-qty">0 / - кг</span>' in html
    assert re.search(
        r'<span class="field-label">Оставащи</span>\s*<div class="big">-</div>',
        html,
    )


def test_terminal_v8_write_forms_include_loaded_version_and_no_operator_cancel_restore(
    connection,
):
    card_id = release_ready_card("26106", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok

    html = render_terminal(card_id)
    forms = re.findall(r"<form\b.*?</form>", html, flags=re.S)
    terminal_write_forms = [form for form in forms if 'action="/terminal/cards/' in form]

    assert terminal_write_forms
    assert all('name="loaded_version"' in form for form in terminal_write_forms)
    assert "Анулирай" not in html
    assert "Възстанови" not in html
    assert "Cancel" not in html
    assert "Restore" not in html
    assert f"/terminal/cards/{card_id}/cancel" not in html
    assert f"/terminal/cards/{card_id}/restore" not in html
    assert f"/admin/cards/{card_id}/cancel" not in html
    assert f"/admin/cards/{card_id}/restore" not in html


def test_terminal_v8_does_not_render_print_action_for_produced_cards(connection):
    completed_id = release_ready_card("26180", machine_id=1, sequence=1)
    complete_card(completed_id)

    completed_html = render_terminal(completed_id)

    assert f"/cards/{completed_id}/print" not in completed_html
    assert "Печат / препечат" not in completed_html
    assert "Корекция на ролки" in completed_html


def test_terminal_v8_hides_archived_cards_from_produced_lookup(connection):
    completed_id = release_ready_card(
        "26185",
        machine_id=1,
        sequence=1,
        customer="Produced Customer",
    )
    complete_card(completed_id)
    archived_id = release_ready_card(
        "26186",
        machine_id=2,
        sequence=1,
        customer="Archived Customer",
    )
    complete_card(archived_id)
    assert db.archive_completed_card(archived_id, card_version(archived_id)).ok

    html = render_terminal(completed_id)

    assert "Produced Customer" in html
    assert "Archived Customer" not in html


def test_terminal_v8_action_and_roll_add_buttons_render_decorative_icons(connection):
    card_id = release_ready_card("26182", machine_id=1, sequence=1)

    def form_block(html: str, action: str) -> str:
        match = re.search(
            rf'<form action="{re.escape(action)}".*?</form>',
            html,
            flags=re.S,
        )
        assert match is not None
        return match.group(0)

    pending_html = render_terminal(card_id)
    start_form = form_block(
        pending_html,
        f"/terminal/cards/{card_id}/timing/start",
    )
    assert 'data-icon="play"' in start_form
    assert 'aria-hidden="true"' in start_form
    assert "Старт" in start_form
    assert 'data-icon="pause"' in pending_html
    assert 'data-icon="check-circle"' in pending_html
    assert 'data-icon="plus"' in pending_html

    assert db.start_production_timing(card_id, card_version(card_id)).ok
    running_html = render_terminal(card_id)
    pause_form = form_block(
        running_html,
        f"/terminal/cards/{card_id}/timing/pause",
    )
    finish_form = form_block(running_html, f"/terminal/cards/{card_id}/finish")
    roll_form = form_block(running_html, f"/terminal/cards/{card_id}/rolls")
    roll_entry = roll_entry_block(running_html)
    assert 'data-icon="pause"' in pause_form
    assert "Пауза" in pause_form
    assert 'data-icon="check-circle"' in finish_form
    assert "Приключи" in finish_form
    assert f'id="add-roll-form-{card_id}"' in roll_form
    assert 'data-icon="plus"' in roll_entry
    assert f'form="add-roll-form-{card_id}"' in roll_entry
    assert "Добави" in roll_entry

    assert db.pause_production_timing(card_id, card_version(card_id)).ok
    paused_html = render_terminal(card_id)
    resume_form = form_block(
        paused_html,
        f"/terminal/cards/{card_id}/timing/resume",
    )
    assert 'data-icon="play"' in resume_form
    assert "Продължи" in resume_form


def test_terminal_v8_finish_form_uses_app_native_confirmation_modal(connection):
    card_id = release_ready_card("26183", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok

    html = render_terminal(card_id)
    finish_form = form_block(html, f"/terminal/cards/{card_id}/finish")
    pause_form = form_block(html, f"/terminal/cards/{card_id}/timing/pause")

    assert "confirm(" not in html
    assert "onsubmit=" not in finish_form
    assert 'data-finish-confirm-form="true"' in finish_form
    assert 'name="loaded_version"' in finish_form
    assert "Приключи" in finish_form
    assert 'data-finish-confirm-form="true"' not in pause_form

    assert 'id="finish-confirm-modal"' in html
    assert 'data-finish-confirm-modal' in html
    assert "Приключване на поръчка" in html
    assert "Сигурни ли сте, че искате да приключите тази поръчка?" in html
    assert 'data-finish-confirm-submit' in html
    assert "Да, приключи" in html
    assert 'data-finish-confirm-cancel' in html
    assert "Не, назад" in html


def test_terminal_v8_finish_confirmation_script_handles_modal_lifecycle(connection):
    card_id = release_ready_card("26184", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok

    html = render_terminal(card_id)

    assert 'form[data-finish-confirm-form="true"]' in html
    assert 'event.preventDefault();' in html
    assert 'finishConfirmModal.hidden = false;' in html
    assert 'finishConfirmModal.hidden = true;' in html
    assert 'data-finish-confirm-cancel' in html
    assert 'data-finish-confirm-submit' in html
    assert 'event.key === "Escape"' in html
    assert "finishConfirmSubmitting || !pendingFinishForm" in html
    assert "finishConfirmSubmit.disabled = true;" in html
    assert "pendingFinishForm.requestSubmit();" in html


def test_terminal_v8_success_result_renders_one_dismissible_toast(connection):
    card_id = release_ready_card("26107", machine_id=1, sequence=1)

    html = render_terminal(
        card_id,
        roll_result=RuleResult(True, ("Ролка 1 е записана.",)),
        roll_result_target="new_roll",
    )

    assert html.count('class="terminal-toast"') == 1
    assert "Ролка 1 е записана." in html
    assert 'class="terminal-toast-close"' in html
    assert html.count('role="alert"') == 0
    assert 'class="roll-list" data-scroll-bottom="true"' in html


def test_terminal_v8_roll_rows_are_compact_and_vertically_centered(connection):
    card_id = release_ready_card("26112", machine_id=1, sequence=1)

    html = render_terminal(card_id)

    assert ".roll-row {\n      min-height: 46px;" in html
    roll_body_cell_rules = css_rules(html, r"(?m)^    \.roll-row > div")
    assert "padding: 4px 7px;" in roll_body_cell_rules
    assert "align-items: center;" in roll_body_cell_rules
    assert "align-content: center;" in html
    assert ".roll-row-error-slot:empty {\n      display: none;" in html


def test_terminal_roll_rows_are_readonly_by_default_with_correction_action(connection):
    card_id = release_ready_card("26230", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    first_roll = card["roll_entries"][0]

    html = render_terminal(card_id)
    row_html = roll_row_block(html, first_roll["id"])

    assert "Корекция на ролки" in html
    assert "Изтриване на ролки" in html
    assert 'data-roll-correction-open' in html
    assert 'data-roll-delete-open' in html
    assert 'data-roll-display="gross"' in row_html
    assert 'data-roll-display="tare"' in row_html
    assert 'data-roll-correction-input' in row_html
    assert f'name="gross_weight__{first_roll["id"]}"' in row_html
    assert f'name="tare_weight__{first_roll["id"]}"' in row_html
    assert "disabled" in row_html
    assert 'data-dirty-autosave="true"' not in row_html
    assert 'data-roll-correction-actions hidden' in html


def test_terminal_roll_correction_error_opens_correction_mode(connection):
    card_id = release_ready_card("26231", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok

    html = render_terminal(
        card_id,
        roll_result=RuleResult(False, ("correction failure",)),
        roll_result_target="roll_corrections",
    )

    assert 'data-roll-correction-root data-correction-open="true"' in html
    assert "correction failure" in data_block(html, "data-feedback-target", "roll_corrections")
    assert "Запази данните" in html
    assert "Отказ" in html


def test_terminal_roll_table_scrolls_above_footer_actions(connection):
    card_id = release_ready_card("26233", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    for gross_weight in ("50.00", "51.00", "52.00"):
        assert db.add_roll_gross_weight(card_id, card_version(card_id), gross_weight).ok

    html = render_terminal(card_id)

    correction_form_rules = css_rules(html, r"(?m)^    \.roll-correction-form")
    roll_table_rules = css_rules(html, r"(?m)^    \.roll-table")
    roll_list_rules = css_rules(html, r"(?m)^    \.roll-list")

    assert "min-height: 0;" in correction_form_rules
    assert "display: grid;" in correction_form_rules
    assert "grid-template-rows: minmax(0, 1fr);" in correction_form_rules
    assert "height: 100%;" in roll_table_rules
    assert "min-height: 0;" in roll_table_rules
    assert "overflow: auto;" in roll_list_rules


def test_terminal_roll_correction_actions_replace_totals_footer(connection):
    card_id = release_ready_card("26234", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok

    html = render_terminal(
        card_id,
        roll_result=RuleResult(False, ("correction failure",)),
        roll_result_target="roll_corrections",
    )

    assert 'class="panel-body roll-body roll-correction-mode"' in html
    assert "data-roll-body" in html
    assert "rollBody.classList.toggle(\"roll-correction-mode\", open);" in html
    assert "display: none;" in css_rules(
        html,
        r"(?m)^    \.roll-body\.roll-correction-mode \.totals",
    )
    assert "grid-template-columns: minmax(0, 1fr) auto;" in css_rules(
        html,
        r"(?m)^    \.roll-correction-actions",
    )


def test_terminal_roll_entry_controls_follow_roll_table_weight_order(connection):
    card_id = release_ready_card("26197", machine_id=1, sequence=1)

    html = render_terminal(card_id)
    entry_html = roll_entry_block(html)

    assert entry_html.find('class="add-roll-form"') < entry_html.find('class="tare-form')
    assert entry_html.find("Нова ролка, кг") < entry_html.find("Шпула, кг")
    assert entry_html.find("Шпула, кг") < entry_html.find('class="roll-add-button"')


def test_terminal_tare_and_correction_forms_use_dirty_autosave_without_new_roll_autosave(connection):
    card_id = release_ready_card("26198", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    roll = card["roll_entries"][0]

    html = render_terminal(card_id)
    tare_form = form_block(html, f"/terminal/cards/{card_id}/tare")
    add_roll_form = form_block(html, f"/terminal/cards/{card_id}/rolls")
    correction_form = form_block(html, f"/terminal/cards/{card_id}/rolls/corrections")
    row_html = roll_row_block(html, roll["id"])

    assert 'data-dirty-autosave="true"' in tare_form
    assert 'data-dirty-autosave="true"' not in add_roll_form
    assert 'data-dirty-autosave="true"' not in correction_form
    assert 'data-dirty-autosave="true"' not in row_html
    assert 'data-dirty-autosave-group="roll-entry"' in tare_form
    assert 'data-dirty-autosave-group="roll-entry"' not in add_roll_form
    assert 'data-dirty-autosave-group="roll-entry"' not in correction_form
    assert 'data-new-roll-tare-copy="true"' in add_roll_form
    assert 'data-current-tare-input="true"' in tare_form
    assert 'form[data-recipe-autosave="true"], form[data-dirty-autosave="true"]' in html
    assert "syncNewRollTare" in html
    assert "dirtyAutosaveGroup" in html
    assert "bindDirtyAutosaveForm" in html
    assert "submitDirtyForm" in html
    assert 'window.addEventListener("beforeunload"' in html


def test_terminal_roll_correction_script_blocks_other_actions_while_open(connection):
    card_id = release_ready_card("26232", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok

    html = render_terminal(card_id)

    assert "setCorrectionMode" in html
    assert "data-roll-correction-open" in html
    assert "data-roll-correction-cancel" in html
    assert "data-roll-correction-input" in html
    assert "correctionBlockedControls" in html
    assert ".menu-btn" in html
    assert "[data-roll-correction-open]" in html
    assert ".roll-add-button" in html
    assert ".tare-form input" in html
    assert ".recipe-table input" in html
    assert "#queue-open" in html
    assert "#history-open" in html
    assert "initialCorrectionValues" in html
    assert "hasDirtyRollCorrections" in html
    assert "skipCorrectionBeforeUnload" in html


def test_terminal_roll_correction_save_suppresses_dirty_exit_warning(connection):
    card_id = release_ready_card("26235", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok

    html = render_terminal(card_id)

    assert re.search(
        r"rollCorrectionRoot\.addEventListener\(\"submit\", \(\) => \{\s*"
        r"skipCorrectionBeforeUnload = true;\s*"
        r"\}\);",
        html,
    )


def test_terminal_v8_roll_saved_notice_scrolls_roll_list_to_bottom(connection):
    card_id = release_ready_card("26192", machine_id=1, sequence=1)

    html = render_terminal(card_id, terminal_notice="roll_saved")

    assert "Ролката е записана." in html
    assert 'class="roll-list" data-scroll-bottom="true"' in html


def test_terminal_v8_notice_code_renders_one_dismissible_toast(connection):
    card_id = release_ready_card("26191", machine_id=1, sequence=1)

    html = render_terminal(card_id, terminal_notice="tare_saved")

    assert html.count('class="terminal-toast"') == 1
    assert "Шпула е записана." in html
    assert 'class="terminal-toast-close"' in html
    assert html.count('role="alert"') == 0


def test_terminal_card_notice_query_renders_one_dismissible_toast(connection):
    card_id = release_ready_card("26193", machine_id=1, sequence=1)

    response = asyncio.run(
        terminal_card(
            make_test_request(
                f"/terminal/cards/{card_id}?notice=tare_saved",
                method="GET",
            ),
            card_id,
            notice="tare_saved",
        )
    )
    html = response.body.decode("utf-8")

    assert html.count('class="terminal-toast"') == 1
    assert "Шпула е записана." in html


def test_terminal_v8_unknown_notice_code_is_ignored(connection):
    card_id = release_ready_card("26192", machine_id=1, sequence=1)

    html = render_terminal(card_id, terminal_notice="not_a_real_notice")

    assert 'class="terminal-toast"' not in html
    assert "not_a_real_notice" not in html

    response = asyncio.run(
        terminal_card(
            make_test_request(
                f"/terminal/cards/{card_id}?notice=not_a_real_notice",
                method="GET",
            ),
            card_id,
            notice="not_a_real_notice",
        )
    )
    route_html = response.body.decode("utf-8")

    assert 'class="terminal-toast"' not in route_html
    assert "not_a_real_notice" not in route_html


def test_terminal_v8_failed_tare_result_renders_under_tare_field(connection):
    card_id = release_ready_card("26108", machine_id=1, sequence=1)

    html = render_terminal(
        card_id,
        roll_result=RuleResult(False, ("tare failure",)),
        roll_result_target="tare",
    )

    tare_block = data_block(html, "data-feedback-target", "tare")
    new_roll_block = data_block(html, "data-feedback-target", "new_roll")
    assert "Шпула, кг" in html
    assert "tare failure" in tare_block
    assert "tare failure" not in new_roll_block


def test_terminal_v8_failed_new_roll_result_renders_under_new_roll_field(connection):
    card_id = release_ready_card("26109", machine_id=1, sequence=1)

    html = render_terminal(
        card_id,
        roll_result=RuleResult(False, ("new roll failure",)),
        roll_result_target="new_roll",
    )

    tare_block = data_block(html, "data-feedback-target", "tare")
    new_roll_block = data_block(html, "data-feedback-target", "new_roll")
    assert "Нова ролка, кг" in html
    assert "new roll failure" in new_roll_block
    assert "new roll failure" not in tare_block
    assert 'class="roll-list" data-scroll-bottom="false"' in html


def test_terminal_v8_stale_new_roll_result_renders_refresh_alert_not_chip_or_error_text(connection):
    card_id = release_ready_card("26114", machine_id=1, sequence=1)

    html = render_terminal(
        card_id,
        roll_result=RuleResult(False, (STALE_CARD_MESSAGE,)),
        roll_result_target="new_roll",
    )

    new_roll_block = data_block(html, "data-feedback-target", "new_roll")
    assert STALE_CARD_MESSAGE not in html
    assert 'id="terminal-refresh-alert"' in html
    assert "Данните са променени" in html
    assert "Презаредете картата, преди да продължите." in html
    assert 'id="terminal-refresh-alert-button"' in html
    assert f'href="/terminal/cards/{card_id}"' in html
    assert "window.location.reload()" not in html
    assert "sync-chip" not in html
    assert "action-error-chip" not in html
    assert STALE_CARD_MESSAGE not in new_roll_block


def test_terminal_v8_failed_roll_edit_result_renders_in_affected_row_only(connection):
    card_id = release_ready_card("26110", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "61.00").ok
    with db.connect() as connection:
        roll_ids = [
            int(row["id"])
            for row in connection.execute(
                "SELECT id FROM roll_entries WHERE card_id = ? ORDER BY roll_number",
                (card_id,),
            ).fetchall()
        ]

    html = render_terminal(
        card_id,
        roll_result=RuleResult(False, ("row edit failure",)),
        roll_result_target="roll_row",
        roll_result_roll_id=roll_ids[1],
    )

    first_row = roll_row_block(html, roll_ids[0])
    second_row = roll_row_block(html, roll_ids[1])
    assert "row edit failure" not in first_row
    assert "row edit failure" in second_row


def test_terminal_roll_weight_route_preserves_row_tare_when_tare_field_omitted(connection):
    card_id = release_ready_card("26175", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    roll = card["roll_entries"][0]
    assert roll["tare_weight"] == 1.2

    response = asyncio.run(
        save_roll_weight(
            make_test_request(f"/terminal/cards/{card_id}/rolls/{roll['id']}"),
            card_id,
            roll["id"],
            str(card["version"]),
            "61.00",
            None,
        )
    )

    updated_roll = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]
    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=roll_updated"
    )
    assert updated_roll["gross_weight"] == 61
    assert updated_roll["tare_weight"] == 1.2
    assert updated_roll["net_weight"] == 59.8


def test_terminal_roll_weight_route_updates_row_tare_with_hidden_gross(connection):
    card_id = release_ready_card("26176", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    roll = card["roll_entries"][0]

    response = asyncio.run(
        save_roll_weight(
            make_test_request(f"/terminal/cards/{card_id}/rolls/{roll['id']}"),
            card_id,
            roll["id"],
            str(card["version"]),
            "50.00",
            "3.00",
        )
    )

    updated_roll = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]
    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=roll_updated"
    )
    assert updated_roll["gross_weight"] == 50
    assert updated_roll["tare_weight"] == 3
    assert updated_roll["net_weight"] == 47


def test_terminal_new_roll_route_can_save_current_tare_before_adding_roll(connection):
    card_id = release_ready_card("26201", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    loaded_version = card_version(card_id)

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls",
            {
                "loaded_version": str(loaded_version),
                "gross_weight": "50.00",
                "tare_weight": "2.50",
            },
        )
    )

    card = db.fetch_terminal_card_detail(card_id)
    roll = card["roll_entries"][0]
    assert status_code == 303
    assert headers["location"] == (
        f"/terminal/cards/{card_id}?notice=roll_saved"
    )
    assert card["tare_weight"] == 2.5
    assert roll["gross_weight"] == 50
    assert roll["tare_weight"] == 2.5
    assert roll["net_weight"] == 47.5


def test_terminal_roll_corrections_route_saves_multiple_rows_together(connection):
    card_id = release_ready_card("26220", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    first_id = int(card["roll_entries"][0]["id"])
    second_id = int(card["roll_entries"][1]["id"])

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls/corrections",
            {
                "loaded_version": str(card["version"]),
                f"gross_weight__{first_id}": "51.00",
                f"tare_weight__{first_id}": "2.50",
                f"gross_weight__{second_id}": "62.00",
                f"tare_weight__{second_id}": "3.00",
            },
        )
    )
    updated = db.fetch_terminal_card_detail(card_id)

    assert status_code == 303
    assert headers["location"] == f"/terminal/cards/{card_id}?notice=rolls_saved"
    assert [
        (roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
        for roll in updated["roll_entries"]
    ] == [(51, 2.5, 48.5), (62, 3, 59)]


def test_terminal_roll_corrections_route_blocks_stale_post_without_partial_update(connection):
    card_id = release_ready_card("26221", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])
    assert db.update_tare_weight(card_id, card["version"], "2.25").ok

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls/corrections",
            {
                "loaded_version": str(card["version"]),
                f"gross_weight__{roll_id}": "51.00",
                f"tare_weight__{roll_id}": "2.50",
            },
        )
    )
    updated = db.fetch_terminal_card_detail(card_id)

    assert status_code == 200
    assert "location" not in headers
    assert updated["roll_entries"][0]["gross_weight"] == 50
    assert updated["roll_entries"][0]["tare_weight"] == 2


def test_terminal_roll_corrections_route_blocks_archived_card_direct_post(connection):
    card_id = release_ready_card("26222", machine_id=2, sequence=1)
    complete_card(card_id)
    assert db.archive_completed_card(card_id, card_version(card_id)).ok
    card = db.fetch_admin_card_detail(card_id)
    roll = card["roll_entries"][0]

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls/corrections",
            {
                "loaded_version": str(card["version"]),
                f"gross_weight__{roll['id']}": "99.00",
                f"tare_weight__{roll['id']}": "1.00",
            },
        )
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert status_code == 200
    assert "location" not in headers
    assert updated["roll_entries"][0]["gross_weight"] == roll["gross_weight"]
    assert updated["version"] == card["version"]


def test_terminal_roll_corrections_route_blocks_cancelled_card_direct_post(connection):
    card_id = release_ready_card("26223", machine_id=2, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "40.00").ok
    assert db.cancel_card(card_id, card_version(card_id)).ok
    card = db.fetch_admin_card_detail(card_id)
    roll = card["roll_entries"][0]

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls/corrections",
            {
                "loaded_version": str(card["version"]),
                f"gross_weight__{roll['id']}": "99.00",
                f"tare_weight__{roll['id']}": "1.00",
            },
        )
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert status_code == 200
    assert "location" not in headers
    assert updated["roll_entries"][0]["gross_weight"] == roll["gross_weight"]
    assert updated["version"] == card["version"]


def test_terminal_v8_roll_delete_is_separate_from_roll_correction(connection):
    card_id = release_ready_card("26172", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok

    html = render_terminal(card_id)
    roll_id = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]["id"]
    row_html = roll_row_block(html, roll_id)

    assert "Корекция на ролки" in html
    assert "Изтриване на ролки" in html
    assert 'data-roll-correction-open' in html
    assert 'data-roll-delete-open' in html
    assert f'action="/terminal/cards/{card_id}/rolls/corrections"' in html
    assert f'action="/terminal/cards/{card_id}/rolls/actions/delete-selected"' in html
    assert "/delete" not in row_html
    assert "Изтрий" not in row_html


def test_terminal_roll_delete_requires_matching_roll_number_confirmation(connection):
    card_id = release_ready_card("26173", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
    for gross_weight in ("10.00", "20.00", "30.00"):
        assert db.add_roll_gross_weight(card_id, card_version(card_id), gross_weight).ok
    card = db.fetch_terminal_card_detail(card_id)
    middle_roll = card["roll_entries"][1]

    blocked = asyncio.run(
        delete_selected_roll_weight(
            make_test_request(f"/terminal/cards/{card_id}/rolls/actions/delete-selected"),
            card_id,
            str(card["version"]),
            str(middle_roll["id"]),
            "1",
        )
    )
    after_blocked = db.fetch_terminal_card_detail(card_id)

    assert blocked.status_code == 200
    assert blocked.context["roll_result"].messages == (
        "Потвърдете изтриването с номера на ролката.",
    )
    assert after_blocked["roll_count"] == 3

    deleted = asyncio.run(
        delete_selected_roll_weight(
            make_test_request(f"/terminal/cards/{card_id}/rolls/actions/delete-selected"),
            card_id,
            str(after_blocked["version"]),
            str(middle_roll["id"]),
            "2",
        )
    )
    after_deleted = db.fetch_terminal_card_detail(card_id)

    assert deleted.status_code == 303
    assert deleted.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=roll_deleted"
    )
    assert after_deleted["roll_count"] == 2
    assert [
        (roll["roll_number"], roll["gross_weight"])
        for roll in after_deleted["roll_entries"]
    ] == [(1, 10), (2, 30)]


def test_terminal_failed_selected_roll_delete_preserves_selected_roll(connection):
    card_id = release_ready_card("26174", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
    for gross_weight in ("10.00", "20.00", "30.00"):
        assert db.add_roll_gross_weight(card_id, card_version(card_id), gross_weight).ok
    card = db.fetch_terminal_card_detail(card_id)
    first_roll = card["roll_entries"][0]
    middle_roll = card["roll_entries"][1]

    response = asyncio.run(
        delete_selected_roll_weight(
            make_test_request(f"/terminal/cards/{card_id}/rolls/actions/delete-selected"),
            card_id,
            str(card["version"]),
            str(middle_roll["id"]),
            "1",
        )
    )
    page = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "Потвърдете изтриването с номера на ролката." in page
    assert 'class="roll-delete-panel" id="roll-delete-panel" hidden' not in page
    assert re.search(
        rf'<option value="{middle_roll["id"]}" selected>№{middle_roll["roll_number"]}',
        page,
    )
    assert not re.search(
        rf'<option value="{first_roll["id"]}" selected>№{first_roll["roll_number"]}',
        page,
    )


def test_terminal_v8_material_error_renders_under_recipe_table(connection):
    card_id = release_ready_card("26111", machine_id=1, sequence=1)

    html = render_terminal(
        card_id,
        material_result=RuleResult(False, ("material failure",)),
    )

    material_block = data_block(html, "data-feedback-target", "material")
    assert "recipe-table" in html
    assert "material failure" in material_block


def test_terminal_v8_timing_and_finish_errors_render_near_topbar_actions(connection):
    card_id = release_ready_card("26112", machine_id=1, sequence=1)

    timing_html = render_terminal(
        card_id,
        timing_result=RuleResult(False, ("timing failure",)),
    )
    finish_html = render_terminal(
        card_id,
        workflow_result=RuleResult(False, ("finish failure",)),
    )

    assert 'data-feedback-target="topbar"' in timing_html
    assert 'data-feedback-target="topbar"' in finish_html
    assert "timing failure" in timing_html
    assert "finish failure" in finish_html


def test_terminal_finish_success_redirects_to_canonical_get(connection):
    card_id = release_ready_card("26170", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok
    loaded_version = card_version(card_id)

    response = asyncio.run(
        finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            str(loaded_version),
        )
    )
    refresh_html = render_terminal(card_id)

    card = db.fetch_terminal_card_detail(card_id)
    assert card["status"] == "completed"
    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=card_finished"
    )
    assert "Действието не беше записано" not in refresh_html
    assert "Картата не е намерена." not in refresh_html
    assert f"№{card['order_number']}" in refresh_html


def test_terminal_success_post_redirects_with_notice_query(connection):
    card_id = release_ready_card("26190", machine_id=1, sequence=1)
    loaded_version = card_version(card_id)

    response = asyncio.run(
        save_tare_weight(
            make_test_request(f"/terminal/cards/{card_id}/tare"),
            card_id,
            str(loaded_version),
            "1.20",
        )
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=tare_saved"
    )


def test_terminal_stale_tare_submit_renders_refresh_alert_without_overwrite(connection):
    card_id = release_ready_card("26195", machine_id=1, sequence=1)
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.20").ok

    response = asyncio.run(
        save_tare_weight(
            make_test_request(f"/terminal/cards/{card_id}/tare"),
            card_id,
            str(loaded_version),
            "1.50",
        )
    )
    card = db.fetch_terminal_card_detail(card_id)
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "location" not in response.headers
    assert card["tare_weight"] == 1.2
    assert 'id="terminal-refresh-alert"' in html
    assert "Данните са променени" in html
    assert "Презаредете картата, преди да продължите." in html
    assert STALE_CARD_MESSAGE not in html
    assert 'class="terminal-toast"' not in html


def test_terminal_tare_route_blocks_cancelled_card_direct_post(connection):
    card_id = release_ready_card("26210", machine_id=1, sequence=1)
    assert db.cancel_card(card_id, card_version(card_id)).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]

    response = asyncio.run(
        save_tare_weight(
            make_test_request(f"/terminal/cards/{card_id}/tare"),
            card_id,
            str(loaded_version),
            "9.99",
        )
    )
    card = db.fetch_admin_card_detail(card_id)
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert card["status"] == "cancelled"
    assert card["tare_weight"] is None
    assert card["version"] == loaded_version
    assert 'id="terminal-refresh-alert"' in html
    assert "Данните са променени" in html
    assert "Презаредете картата, преди да продължите." in html
    assert TERMINAL_CARD_UNAVAILABLE_MESSAGE not in html


def test_terminal_material_route_blocks_archived_card_direct_post(connection):
    card_id = release_ready_card("26211", machine_id=2, sequence=1)
    complete_card(card_id)
    assert db.archive_completed_card(card_id, card_version(card_id)).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]

    response_status, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/materials",
            {
                "loaded_version": str(loaded_version),
                "actual_material__raw_material_a": "Terminal overwrite",
                "batch_lot__raw_material_a": "Bad batch",
            },
        )
    )
    card = db.fetch_admin_card_detail(card_id)

    assert response_status == 200
    assert "location" not in headers
    assert card["status"] == "archived"
    assert (
        card["recipe_actual_entries"]
        .get("raw_material_a", {})
        .get("actual_material_used")
        != "Terminal overwrite"
    )
    assert card["version"] == loaded_version


def test_terminal_roll_route_blocks_archived_card_direct_post(connection):
    card_id = release_ready_card("26212", machine_id=3, sequence=1)
    complete_card(card_id)
    assert db.archive_completed_card(card_id, card_version(card_id)).ok
    card = db.fetch_admin_card_detail(card_id)
    loaded_version = card["version"]
    roll = card["roll_entries"][0]

    response = asyncio.run(
        save_roll_weight(
            make_test_request(f"/terminal/cards/{card_id}/rolls/{roll['id']}"),
            card_id,
            roll["id"],
            str(loaded_version),
            "99.99",
            None,
        )
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 200
    assert updated["status"] == "archived"
    assert updated["roll_entries"][0]["gross_weight"] == roll["gross_weight"]
    assert updated["version"] == loaded_version


def test_terminal_finish_failure_renders_inline_without_redirect(connection):
    card_id = release_ready_card("26171", machine_id=1, sequence=1)

    response = asyncio.run(
        finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            str(card_version(card_id)),
        )
    )

    assert response.status_code == 200
    assert "location" not in response.headers
    assert "workflow_result" in response.context
    assert response.context["workflow_result"].messages == (
        "Времето трябва да бъде стартирано преди приключване.",
    )
    assert 'class="terminal-toast"' not in response.body.decode("utf-8")


def test_terminal_v8_refresh_alert_hook_exists_and_old_sync_ui_is_absent(connection):
    card_id = release_ready_card("26113", machine_id=1, sequence=1)

    html = render_terminal(card_id)

    assert 'id="terminal-refresh-alert"' not in html
    assert "terminal-refresh-alert-button" in html
    assert 'const selectedMachineId = 1;' in html
    assert '`/terminal?machine_id=${selectedMachineId}`' in html
    assert '`/terminal/cards/${selectedCardId}`' in html
    assert "window.location.reload()" not in html
    assert "terminal-sync-banner" not in html
    assert "sync-banner" not in html
    assert "sync-chip" not in html
    assert "Довършете текущото въвеждане" not in html
