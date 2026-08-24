from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlencode

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.datastructures import FormData
from starlette.requests import Request

from app import db
from app.db import STALE_CARD_MESSAGE
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import (
    TERMINAL_CARD_UNAVAILABLE_MESSAGE,
    add_roll_weight,
    app,
    delete_roll_weight,
    delete_selected_roll_weight,
    finish_terminal_card,
    progress_percent,
    remaining_gross_display,
    save_current_pallet_number,
    save_roll_weight,
    save_terminal_roll_corrections,
    save_tare_weight,
    target_gross_decimal,
    terminal_card,
    terminal_context,
    terminal_roll_corrections_from_form,
)
from app.presentation import next_operation_display
from app.rules import RuleResult


pytestmark = pytest.mark.usefixtures("active_test_shift")


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
        "ordered_gross_kg": "500",
        "ordered_rolls": "5",
        "product_form": "плоско",
        "material": "LDPE",
        "size_thickness": "890 / 0.082",
        "notes": "Важна бележка за оператор.",
        "extrusion_sequence": "1",
        "extrusion_folding": "single",
        "extrusion_next_operation": "rewind",
        "extrusion_treatment": "corona",
        "raw_material_a": "LDPE; A | 50%",
        "raw_material_b": "LLDPE; B | 30%",
        "raw_material_c": "MDPE; HDPE C | 5%",
        "linear_pe": "LLDPE; Линеен PE | 8%",
        "antistatic": "Antistatic; Антистатик 1% | 1%",
        "masterbatch": "Masterbatch; Бял мастербач | 4%",
        "chalk": "Filler; Креда 5% | 2%",
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
    ).ok
    return card_id


def card_version(card_id: int) -> int:
    return int(db.fetch_terminal_card_detail(card_id)["version"])


def end_active_test_shift() -> dict[str, object]:
    active_shift = db.fetch_active_shift()
    assert active_shift is not None
    assert db.end_shift(int(active_shift["id"]), int(active_shift["version"])).ok
    summary = db.fetch_shift_summary(int(active_shift["id"]))
    assert summary is not None
    return summary


def complete_card(card_id: int) -> None:
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.25").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.35").ok
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


def html_between_ids(html: str, start_id: str, end_id: str) -> str:
    start = html.find(f'id="{start_id}"')
    assert start != -1
    end = html.find(f'id="{end_id}"', start)
    assert end != -1
    return html[start:end]


def shift_window_block(html: str) -> str:
    start = html.find('<div class="shift-window-overlay"')
    assert start != -1
    end_marker = "<!-- terminal-shift-window:end -->"
    end = html.find(end_marker, start)
    assert end != -1
    return html[start:end]


def form_block(html: str, action: str) -> str:
    match = re.search(
        rf'<form[^>]* action="{re.escape(action)}"[^>]*>.*?</form>',
        html,
        flags=re.S,
    )
    assert match is not None
    return match.group(0)


def normalized_markup(markup: str) -> str:
    return re.sub(r"\s+", " ", markup).strip()


def terminal_timing_model_from_html(html: str) -> dict[str, object]:
    match = re.search(
        r'<script type="application/json" data-terminal-timing-model>\s*'
        r'(?P<payload>.*?)\s*</script>',
        html,
        flags=re.S,
    )
    assert match is not None
    return json.loads(match.group("payload"))


def accepted_lifecycle_form_snapshot(
    *,
    action: str,
    slot: str,
    version: int,
    icon: str,
    label: str,
    button_class: str,
    finish_message: str | None = None,
) -> str:
    finish_hook = (
        ' data-finish-confirm-form="true"'
        f' data-finish-confirm-message="{finish_message}"'
        if finish_message is not None
        else ""
    )
    return normalized_markup(
        f"""
        <form action="{action}" method="post" data-lifecycle-slot="{slot}"{finish_hook}>
          <input type="hidden" name="loaded_version" value="{version}">
          <button class="{button_class}" type="submit"><span class="button-icon button-icon-asset"
                data-icon-asset="{icon}"
                style="--button-icon-source: url('/static/images/terminal-ui/{icon}.svg')"
                aria-hidden="true"></span><span>{label}</span></button>
        </form>
        """
    )


def route_endpoint(path: str):
    route = next(
        (
            route
            for route in app.routes
            if getattr(route, "path", None) == path
        ),
        None,
    )
    assert route is not None, f"route must be registered: {path}"
    return route.endpoint


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
    start_match = re.search(
        rf'<(?:div|form) class="roll-row[^\"]*"[^>]*data-roll-id="{roll_id}"[^>]*>',
        html,
    )
    assert start_match is not None
    start = start_match.start()
    next_match = re.search(
        r'<(?:div|form) class="roll-row[^\"]*"[^>]*data-roll-id="',
        html[start_match.end() :],
    )
    next_start = start_match.end() + next_match.start() if next_match else -1
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


def new_roll_input_tag(html: str) -> str:
    match = re.search(
        r'<input[^>]+name="gross_weight"[^>]*>',
        roll_entry_block(html),
        flags=re.S,
    )
    assert match is not None
    return match.group(0)


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


class TerminalFormRequest:
    def __init__(self, path: str, form: FormData) -> None:
        self._request = make_test_request(path)
        self._form = form

    async def form(self) -> FormData:
        return self._form

    def __getattr__(self, name: str):
        return getattr(self._request, name)


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
    assert 'href="/terminal/cards/' in html
    assert 'href="/terminal?machine_id=2"' in html
    assert "Машина 1" in html
    assert "Машина 2" in html
    assert "Машина 3" in html
    assert "Машина 4" in html
    assert "Машина 2" in empty_machine_html
    assert "Няма активна поръчка за Машина 2." in empty_machine_html
    assert re.search(
        r'<a class="machine-tab idle selected"[^>]*href="/terminal\?machine_id=2"',
        empty_machine_html,
    )


def test_terminal_v8_machine_navigation_renders_roll_change_timer_hosts(connection):
    running_id = release_ready_card("26101", machine_id=1, sequence=1)
    paused_id = release_ready_card("26102", machine_id=2, sequence=1)
    pending_id = release_ready_card("26104", machine_id=3, sequence=1)
    assert db.start_production_timing(running_id, card_version(running_id)).ok
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok

    html = render_terminal()

    assert len(re.findall(r'data-roll-change-machine(?:\s|=)', html)) == 4
    for machine_tab_top in re.findall(
        r'<span class="machine-tab-top">.*?</span>\s*<span class="machine-tab-meta">',
        html,
        re.S,
    ):
        assert 'class="status ' not in machine_tab_top
    assert re.search(r'class="machine-state-dot running".*>.*Машина 1: работи', html, re.S)
    assert re.search(r'class="machine-state-dot paused".*>.*Машина 2: пауза', html, re.S)
    assert re.search(r'class="machine-state-dot idle".*>.*Машина 3: чака старт', html, re.S)
    assert re.search(r'class="machine-state-dot idle".*>.*Машина 4: свободна', html, re.S)
    assert len(re.findall(r'data-roll-change-machine-timer', html)) == 4
    for card_id in (running_id, paused_id, pending_id):
        assert re.search(
            rf'data-card-id="{card_id}"\s+data-card-version="{card_version(card_id)}"',
            html,
        )
    assert re.search(r'data-card-id=""\s+data-card-version=""\s+data-card-status="free"', html)
    assert re.search(
        rf'data-roll-change-controls\s+data-machine-id="1"\s+'
        rf'data-card-id="{running_id}"\s+data-card-version="{card_version(running_id)}"\s+'
        r'data-card-status="running"',
        html,
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


def test_terminal_v8_details_grid_uses_fixed_five_column_rows(connection):
    release_ready_card("26104", machine_id=1, sequence=1)

    html = render_terminal()

    assert ".info-row-primary" in html
    assert ".info-row-secondary" in html
    assert html.count("grid-template-columns: repeat(5, minmax(0, 1fr));") >= 2


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
        r'<a class="machine-tab running selected"[^>]*>.*?</a>',
        html,
        flags=re.S,
    )
    assert machine_tab_match is not None
    machine_tab = machine_tab_match.group(0)
    assert f'href="/terminal/cards/{running_id}"' in machine_tab
    assert "Машина 2: работи" in machine_tab
    assert "V8 Customer 26147" in machine_tab


def test_terminal_v8_non_focus_paused_card_cannot_own_machine_countdown(
    connection,
):
    paused_id = release_ready_card("26148", machine_id=2, sequence=1)
    running_id = release_ready_card("26149", machine_id=2, sequence=2)
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    paused_html = render_terminal(paused_id)
    running_html = render_terminal(running_id)

    assert "Машина 2: №26148" in paused_html
    assert 'data-roll-change-controls' not in paused_html
    assert 'data-roll-change-overlay' not in paused_html
    assert 'data-roll-change-controls' in running_html
    assert 'data-roll-change-overlay' in running_html


def test_terminal_disables_start_when_another_card_occupies_selected_machine(connection):
    pending_id = release_ready_card("26148-pending", machine_id=1, sequence=1)
    running_id = release_ready_card("26148-running", machine_id=1, sequence=2)
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    context = terminal_context(pending_id)
    html = render_terminal(pending_id)
    start_button = re.search(
        r'<button[^>]+data-lifecycle-slot="start"[^>]*>.*?<span>Старт</span></button>',
        html,
        flags=re.S,
    )

    assert context["selected_machine_occupying_card"]["id"] == running_id
    assert f'action="/terminal/cards/{pending_id}/timing/start"' not in html
    assert start_button is not None
    assert "disabled" in start_button.group(0)
    assert 'aria-describedby="machine-occupied-reason"' in start_button.group(0)
    assert (
        '<p class="action-disabled-reason" id="machine-occupied-reason" role="note">'
        'Машина 1 е заета от поръчка 26148-running.</p>'
    ) in html


def test_terminal_disables_resume_when_another_card_occupies_selected_machine(connection):
    paused_id = release_ready_card("26148-paused", machine_id=2, sequence=1)
    running_id = release_ready_card("26148-occupant", machine_id=2, sequence=2)
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    context = terminal_context(paused_id)
    html = render_terminal(paused_id)
    continue_button = re.search(
        r'<button[^>]+data-lifecycle-slot="pause"[^>]*>.*?<span>Продължи</span></button>',
        html,
        flags=re.S,
    )

    assert context["selected_machine_occupying_card"]["id"] == running_id
    assert f'action="/terminal/cards/{paused_id}/timing/resume"' not in html
    assert continue_button is not None
    assert "disabled" in continue_button.group(0)
    assert 'aria-describedby="machine-occupied-reason"' in continue_button.group(0)
    assert f'action="/terminal/cards/{paused_id}/finish"' in html


def test_terminal_keeps_start_enabled_when_other_card_is_only_paused(connection):
    paused_id = release_ready_card("26148-only-paused", machine_id=3, sequence=1)
    pending_id = release_ready_card("26148-free-pending", machine_id=3, sequence=2)
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok

    context = terminal_context(pending_id)
    html = render_terminal(pending_id)

    assert context["selected_machine_occupying_card"] is None
    start_form = form_block(html, f"/terminal/cards/{pending_id}/timing/start")
    assert ">Старт</span>" in start_form
    assert "machine-occupied-reason" not in html


def test_terminal_v8_renders_only_accepted_selected_card_details(connection):
    card_id = release_ready_card("26101", machine_id=1, sequence=1)

    html = render_terminal(card_id)

    assert "Машина 1: №26101" in html
    assert "ТСФ 890/0.082" in html
    assert "V8 Customer 26101" in html
    assert "Поръчано бруто, кг" in html
    assert "500" in html
    assert "890 / 0.082" in html
    assert "плоско" in html
    assert "Важна бележка за оператор." in html
    details_html = html.split('<section class="panel details-panel">', 1)[1].split(
        '<div class="recipe-section">', 1
    )[0]
    assert "Поръчани ролки" not in details_html
    assert "Поръчани метри" not in details_html
    assert "Поръчани бройки" not in details_html
    assert "Дата доставка" not in details_html
    assert "Материал" not in details_html
    assert "Макс. тегло ролка, кг" not in details_html
    first_row = details_html.split(
        '<div class="info-row info-row-primary">', 1
    )[1].split('<div class="info-row info-row-secondary">', 1)[0]
    assert [
        "Фирма",
        "Поръчано бруто, кг",
        "Вид изделие",
        "Размер / дебелина",
        "Фалдиране",
    ] == re.findall(r'<span class="field-label">([^<]+)</span>', first_row)
    second_row = details_html.split(
        '<div class="info-row info-row-secondary">', 1
    )[1].split('<section class="notes-section">', 1)[0]
    assert [
        "Вид заготовка",
        "Следваща операция",
        "Третиране",
        "Опаковка",
    ] == re.findall(r'<span class="field-label">([^<]+)</span>', second_row)


def test_terminal_roll_correction_controls_have_unique_accessible_names(connection):
    card_id = release_ready_card("26101-accessible-roll", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.25").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "25.00").ok

    html = render_terminal(card_id)
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    roll = card["roll_entries"][0]
    row = form_block(html, f"/terminal/cards/{card_id}/rolls/{roll['id']}")

    for name, label in (
        ("gross_weight", "Ролка 1, бруто"),
        ("tare_weight", "Ролка 1, шпула"),
        ("pallet_number", "Ролка 1, палет"),
    ):
        tag = re.search(rf'<input[^>]+name="{name}"[^>]*>', row)
        assert tag is not None
        assert f'aria-label="{label}"' in tag.group(0)


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

    assert "row-gap: 26px;" in html
    assert "padding: 18px 18px;" in html
    assert "gap: 26px;" in html


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


def test_terminal_v8_recipe_table_follows_scrollable_details_with_matching_recipe_title(
    connection,
):
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

    assert "display: flex;" in details_body_rules
    assert "flex-direction: column;" in details_body_rules
    assert "gap: 22px;" in details_body_rules
    assert "overflow-y: auto;" in details_body_rules
    assert "overscroll-behavior: contain;" in details_body_rules
    assert "scrollbar-gutter: stable;" in details_body_rules
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
    assert any("padding: 8px 0 2px;" in rules for rules in roll_entry_rules)
    assert any("margin: 0;" in rules for rules in css_rules_all(html, r"(?m)^    \.roll-entry label\.roll-floating-field > \.field-label"))
    assert "min-height: 40px;" in roll_entry_input_rules
    assert any("min-height: 40px;" in rules for rules in css_rules_all(html, r"(?m)^    \.roll-entry > \.roll-add-button"))
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


def test_terminal_v8_renders_semicolon_reusable_recipe_without_na_control_value(connection):
    card_id = release_ready_card(
        "26241",
        machine_id=1,
        sequence=1,
        raw_material_a="reLDPE; Recycled LDPE | 80%",
        linear_pe="LLDPE; SABIC 119ZJ | 20%",
        raw_material_b="",
        raw_material_c="",
        antistatic="",
        masterbatch="",
        chalk="",
    )

    html = render_terminal(card_id)
    recipe_html = form_block(html, f"/terminal/cards/{card_id}/materials")

    assert "reLDPE" in recipe_html
    assert "Recycled LDPE" in recipe_html
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
        ordered_gross_kg="1250",
        raw_material_a="LDPE; A | 37.5%",
        raw_material_b="LLDPE; B | 23.5%",
        raw_material_c="MDPE; C | 12%",
        linear_pe="reLDPE; D | 10%",
        antistatic="Antistatic; E | 2.5%",
        masterbatch="Masterbatch; F | 9%",
        chalk="Filler; G | 5.5%",
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


def test_terminal_v8_shows_accepted_extrusion_details_only(connection):
    card_id = release_ready_card(
        "26244",
        machine_id=1,
        sequence=1,
        delivery_date="01/08/2026",
        ordered_gross_kg="500",
        ordered_rolls="20",
        ordered_meters="15000",
        ordered_units="40000",
        extrusion_folding="folding detail",
        extrusion_next_operation="Printing",
        extrusion_treatment="corona",
        packaging_method="1 big pallet",
    )

    html = render_terminal(card_id)

    assert "Поръчано бруто, кг" in html
    assert "500" in html
    assert "Фалдиране" in html
    assert "folding detail" in html
    assert "Следваща операция" in html
    assert "Печат" in html
    assert "Третиране" in html
    assert "corona" in html
    assert "Опаковка" in html
    assert "1 big pallet" in html


@pytest.mark.parametrize(
    ("stored_value", "display_value"),
    [
        ("Printing", "Печат"),
        ("Rewinding / Slitting", "Разролване"),
        ("Confection", "Конфекция"),
    ],
)
def test_terminal_v8_translates_next_operation_to_bulgarian(
    connection,
    stored_value,
    display_value,
):
    card_id = release_ready_card(
        "26245",
        machine_id=1,
        sequence=1,
        extrusion_next_operation=stored_value,
    )

    html = render_terminal(card_id)
    match = re.search(
        r'<span class="field-label">Следваща операция</span>\s*'
        r'<div class="value">([^<]*)</div>',
        html,
    )

    assert match is not None
    assert match.group(1) == display_value
    with db.connect() as stored_connection:
        stored = stored_connection.execute(
            "SELECT extrusion_next_operation FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()
    assert stored["extrusion_next_operation"] == stored_value


@pytest.mark.parametrize("value", ["  Unknown operation  ", "  Печат  "])
def test_next_operation_display_preserves_unmapped_values_exactly(value):
    assert next_operation_display(value) == value


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
        "grid-template-columns: 120px minmax(146px, 1fr) 86px 86px "
        "minmax(112px, .58fr) minmax(110px, .52fr);"
    ) in html
    assert (
        "grid-template-columns: 88px minmax(116px, 1fr) 68px 68px "
        "minmax(104px, .52fr) minmax(84px, .42fr);"
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


def test_terminal_drawers_show_only_semantic_gross_weights(connection):
    queued_id = release_ready_card(
        "26160",
        machine_id=1,
        sequence=1,
        ordered_gross_kg="500",
        ordered_rolls="20",
        ordered_meters="15000",
        ordered_units="40000",
    )
    blank_target_id = release_ready_card(
        "26161",
        machine_id=2,
        sequence=1,
        ordered_rolls="21",
        ordered_meters="16000",
        ordered_units="41000",
    )
    blank_target_card = db.fetch_admin_card_detail(blank_target_id)
    blank_target_fields = {
        field: str(blank_target_card[field] or "") for field in IMPORT_FIELDS
    }
    blank_target_fields["ordered_gross_kg"] = ""
    assert db.update_admin_imported_fields(
        blank_target_id,
        card_version(blank_target_id),
        blank_target_fields,
    ).ok
    completed_id = release_ready_card(
        "26162",
        machine_id=3,
        sequence=1,
        ordered_gross_kg="700",
        ordered_rolls="22",
        ordered_meters="17000",
        ordered_units="42000",
    )
    complete_card(completed_id)

    html = render_terminal(queued_id)
    queued_row = re.search(
        rf'<a class="queue-card[^>]+href="/terminal/cards/{queued_id}">.*?</a>',
        html,
        flags=re.S,
    ).group(0)
    blank_target_row = re.search(
        rf'<a class="queue-card[^>]+href="/terminal/cards/{blank_target_id}">.*?</a>',
        html,
        flags=re.S,
    ).group(0)
    produced_row = re.search(
        rf'<a class="history-row[^>]+href="/terminal/cards/{completed_id}".*?</a>',
        html,
        flags=re.S,
    ).group(0)

    assert "500.00 кг" in queued_row
    assert "20 ролки" not in queued_row
    assert "15000 м" not in queued_row
    assert "40000 бр." not in queued_row
    assert '<span>-</span>' in blank_target_row
    assert "- кг" not in blank_target_row
    assert "21 ролки" not in blank_target_row
    assert "60 кг" in produced_row
    assert "22 ролки" not in produced_row
    assert "17000 м" not in produced_row
    assert "42000 бр." not in produced_row


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


def test_terminal_v8_sorts_produced_lookup_by_finished_at_descending(connection):
    older_id = release_ready_card(
        "26185",
        machine_id=1,
        sequence=1,
        customer="Older Produced",
    )
    newer_id = release_ready_card(
        "26186",
        machine_id=4,
        sequence=1,
        customer="Newer Produced",
    )
    complete_card(older_id)
    complete_card(newer_id)
    connection.execute(
        "UPDATE cards SET finished_at = ? WHERE id = ?",
        ("2026-07-24 09:00:00", older_id),
    )
    connection.execute(
        "UPDATE cards SET finished_at = ? WHERE id = ?",
        ("2026-07-24 15:00:00", newer_id),
    )
    connection.commit()

    html = render_terminal(newer_id)

    assert html.index("Newer Produced") < html.index("Older Produced")
    assert '<time datetime="2026-07-24T15:00:00Z">24.07.2026 18:00:00</time>' in html


def test_terminal_v8_renders_waiting_rewinding_header_badge_and_separate_rows(
    connection,
):
    queued_id = release_ready_card(
        "26187",
        machine_id=1,
        sequence=1,
        customer="Queued Customer",
    )
    older_waiting_id = release_ready_card(
        "26188",
        machine_id=2,
        sequence=1,
        customer="Older Waiting",
    )
    newer_waiting_id = release_ready_card(
        "26189",
        machine_id=3,
        sequence=1,
        customer="Newer Waiting",
    )
    completed_id = release_ready_card(
        "26190",
        machine_id=4,
        sequence=1,
        customer="Completed Customer",
    )
    for card_id, count in ((older_waiting_id, 4), (newer_waiting_id, 12)):
        assert db.start_production_timing(card_id, card_version(card_id)).ok
        assert db.update_rewinding_roll_count(card_id, card_version(card_id), count).ok
        assert db.finish_card(card_id, card_version(card_id)).ok
    complete_card(completed_id)
    connection.execute(
        "UPDATE cards SET finished_at = ? WHERE id = ?",
        ("2026-07-24 09:00:00", older_waiting_id),
    )
    connection.execute(
        "UPDATE cards SET finished_at = ? WHERE id = ?",
        ("2026-07-24 10:00:00", newer_waiting_id),
    )
    connection.commit()

    html = render_terminal(newer_waiting_id)

    queue_button = re.search(r'<button[^>]+id="queue-open".*?</button>', html, re.S)
    waiting_button = re.search(r'<button[^>]+id="waiting-open".*?</button>', html, re.S)
    history_button = re.search(r'<button[^>]+id="history-open".*?</button>', html, re.S)
    assert queue_button and waiting_button and history_button
    assert queue_button.start() < waiting_button.start() < history_button.start()
    assert "/static/images/terminal-ui/waiting-orders.svg" in queue_button.group(0)
    assert "/static/images/terminal-ui/awaiting-rewinding.png" in waiting_button.group(0)
    assert "/static/images/terminal-ui/produced-orders.svg" in history_button.group(0)
    assert 'aria-label="Изчакващи пренавиване"' in waiting_button.group(0)
    assert 'data-waiting-count="2"' in waiting_button.group(0)
    assert re.search(r'<span class="waiting-badge"[^>]*>2</span>', waiting_button.group(0))

    waiting_pane = html_between_ids(html, "waiting-overlay", "history-overlay")
    assert 'role="dialog"' in waiting_pane
    assert 'aria-modal="true"' in waiting_pane
    assert 'aria-labelledby="waiting-title"' in waiting_pane
    assert '<h2 id="waiting-title">Изчакващи пренавиване</h2>' in waiting_pane
    assert 'aria-label="Затвори изчакващите пренавиване"' in waiting_pane
    assert waiting_pane.index("Newer Waiting") < waiting_pane.index("Older Waiting")
    assert '<time datetime="2026-07-24T10:00:00Z">24.07.2026 13:00:00</time>' in waiting_pane
    assert f'href="/terminal/cards/{newer_waiting_id}"' in waiting_pane
    assert f'href="/terminal/cards/{older_waiting_id}"' in waiting_pane
    assert "12 ролки" in waiting_pane
    assert "4 ролки" in waiting_pane

    assert not re.search(
        rf'class="queue-card[^"]*"[^>]+href="/terminal/cards/{older_waiting_id}"',
        html,
    )
    history_start = html.index('id="history-overlay"')
    history_end = html.index('<section class="main">', history_start)
    history_pane = html[history_start:history_end]
    assert f'href="/terminal/cards/{older_waiting_id}"' not in history_pane
    assert re.search(
        rf'class="queue-card[^"]*"[^>]+href="/terminal/cards/{queued_id}"',
        html,
    )
    assert re.search(
        rf'class="history-row[^"]*"[^>]+href="/terminal/cards/{completed_id}"',
        html,
    )
    assert f'href="/terminal/cards/{completed_id}"' not in waiting_pane


@pytest.mark.parametrize(
    "terminal_notice",
    ["rewinding_saved", "card_awaiting_rewinding", "card_finished"],
)
def test_terminal_v8_hides_zero_waiting_badge_and_never_opens_pane_from_notice(
    connection,
    terminal_notice,
):
    card_id = release_ready_card("26191", machine_id=1, sequence=1)

    html = render_terminal(card_id, terminal_notice=terminal_notice)

    waiting_button = re.search(r'<button[^>]+id="waiting-open".*?</button>', html, re.S)
    assert waiting_button
    assert 'data-waiting-count="0"' in waiting_button.group(0)
    assert 'class="waiting-badge"' not in waiting_button.group(0)
    waiting_overlay = re.search(r'<div[^>]+id="waiting-overlay"[^>]*>', html)
    assert waiting_overlay
    assert "hidden" in waiting_overlay.group(0)
    assert 'aria-hidden="true"' in waiting_overlay.group(0)


def test_terminal_v8_renders_rewinding_and_roll_change_hosts_in_separate_action_areas(connection):
    running_id = release_ready_card("26192", machine_id=1, sequence=1)
    paused_id = release_ready_card("26193", machine_id=2, sequence=1)
    pending_id = release_ready_card("26194", machine_id=3, sequence=1)
    waiting_id = release_ready_card("26195", machine_id=4, sequence=1)
    assert db.start_production_timing(running_id, card_version(running_id)).ok
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok
    assert db.start_production_timing(waiting_id, card_version(waiting_id)).ok
    assert db.update_rewinding_roll_count(waiting_id, card_version(waiting_id), 1).ok
    assert db.finish_card(waiting_id, card_version(waiting_id)).ok
    completed_id = release_ready_card("26196", machine_id=4, sequence=1)
    assert db.start_production_timing(completed_id, card_version(completed_id)).ok
    assert db.update_tare_weight(completed_id, card_version(completed_id), "1.25").ok
    assert db.add_roll_gross_weight(completed_id, card_version(completed_id), "60.35").ok
    assert db.finish_card(completed_id, card_version(completed_id)).ok

    running_html = render_terminal(running_id)
    clear_button = re.search(
        r'<button[^>]+data-rewinding-open[^>]*>.*?</button>',
        running_html,
        re.S,
    )
    assert clear_button
    assert "/static/images/terminal-ui/awaiting-rewinding.png" in clear_button.group(0)
    assert "Пренавиване" in clear_button.group(0)
    assert "Пренавиване:" not in clear_button.group(0)
    assert "is-marked" not in clear_button.group(0)
    assert 'data-rewinding-open' in running_html
    secondary_actions = re.search(
        r'<div class="roll-secondary-actions"[^>]*>.*?</div>',
        running_html,
        re.S,
    )
    assert secondary_actions
    assert "data-roll-change-open" not in secondary_actions.group(0)
    assert re.search(
        rf'<div class="roll-change-controls"[^>]+data-machine-id="1"'
        rf'[^>]+data-card-id="{running_id}"[^>]+data-card-status="running"',
        running_html,
    )
    assert 'data-roll-change-open' in running_html
    roll_change_button = re.search(
        r'<button[^>]+data-roll-change-open[^>]*>.*?</button>',
        running_html,
        re.S,
    )
    assert roll_change_button
    assert 'roll-change-control-icon' in roll_change_button.group(0)
    assert "/static/images/terminal-ui/rewinding-circular.svg" in roll_change_button.group(0)
    assert 'data-roll-change-advance' in running_html
    assert 'aria-label="Потвърди смяна на ролките"' in running_html
    assert 'data-roll-change-overlay' in running_html
    assert 'src="/static/js/roll_change_countdown.mjs"' in running_html

    editor = html_between_ids(
        running_html,
        "roll-change-overlay",
        "finish-confirm-modal",
    )
    assert 'role="dialog"' in editor
    assert 'aria-modal="true"' in editor
    assert 'aria-labelledby="roll-change-title"' in editor
    assert 'data-roll-change-dialog' in editor
    assert 'data-roll-change-form novalidate' in editor
    assert 'class="roll-change-dialog-intro"' in editor
    assert editor.count('class="roll-change-editor-section') == 3
    assert '<h3>Начало врътка</h3>' in editor
    assert '<h3>Интервал</h3>' in editor
    assert '<h3>Очаквана смяна на ролките</h3>' in editor
    assert editor.count('class="roll-change-step"') == 3
    assert '<input type="hidden" data-roll-change-previous>' in editor
    assert re.search(r'<input[^>]+type="date"[^>]+data-roll-change-previous-date>', editor)
    for input_name in (
        "previous-hour",
        "previous-minute",
        "hours",
        "minutes",
        "next-hour",
        "next-minute",
    ):
        assert re.search(
            rf'<input[^>]+type="text"[^>]+inputmode="numeric"[^>]+'
            rf'data-roll-change-{input_name}',
            editor,
        )
        assert f'<select data-roll-change-{input_name}>' not in editor
    assert editor.count('class="roll-change-clock-separator" aria-hidden="true">:</span>') == 3
    assert '<input type="hidden" data-roll-change-next>' in editor
    assert re.search(r'<input[^>]+type="date"[^>]+data-roll-change-next-date>', editor)
    assert 'type="datetime-local"' not in editor
    assert 'type="number"' not in editor
    assert "Следваща смяна" not in editor
    assert not re.search(r">\s*Коригирай\s*</button>", editor)
    assert "Очаквана смяна на ролките" in editor
    assert 'class="roll-change-interval-note">Напомняне на всеки' in editor
    assert 'data-roll-change-interval-summary' in editor
    for error_name in ("previous", "hours", "minutes", "next", "form"):
        assert f'data-roll-change-error-for="{error_name}"' in editor
        assert f'id="roll-change-error-{error_name}"' in editor
    assert editor.count('aria-describedby="roll-change-error-previous"') == 3
    assert editor.count('aria-describedby="roll-change-error-next"') == 3
    assert 'aria-describedby="roll-change-error-hours roll-change-error-form"' in editor
    assert 'aria-describedby="roll-change-error-minutes roll-change-error-form"' in editor
    assert 'data-roll-change-error-for="form" role="alert"' in editor
    assert 'class="roll-change-start-action"' in editor
    assert 'data-roll-change-restart' in editor
    assert 'Използвай текущия час</button>' in editor
    assert 'class="roll-change-editor-footer"' in editor
    assert 'data-roll-change-clear>Изключи брояча</button>' in editor
    assert 'class="roll-change-confirm-actions"' in editor
    assert 'data-roll-change-cancel>Отказ</button>' in editor
    assert '<button type="submit" class="roll-change-save">Запиши</button>' in editor

    paused_tone_rules = css_rules(
        running_html,
        r"\.roll-change-open\.warning,\s*"
        r"\.roll-change-open\.paused,\s*"
        r"\.roll-change-open\.resync",
    )
    urgent_tone_rules = css_rules(
        running_html,
        r"\.roll-change-open\.urgent",
    )
    assert "color: #704100;" in paused_tone_rules
    assert "background: #fff2bd;" in paused_tone_rules
    assert "border-color: #d7a13f;" in paused_tone_rules
    assert "color: #fff;" in urgent_tone_rules
    assert "background: var(--red);" in urgent_tone_rules
    assert "border-color: var(--red);" in urgent_tone_rules

    machine_links = re.findall(
        r'<a class="machine-tab .*?</a>',
        running_html,
        re.S,
    )
    assert len(machine_links) == 4
    assert all("<button" not in machine_link for machine_link in machine_links)

    assert db.update_rewinding_roll_count(running_id, card_version(running_id), 8).ok
    marked_html = render_terminal(running_id)
    marked_button = re.search(
        r'<button[^>]+data-rewinding-open[^>]*>.*?</button>',
        marked_html,
        re.S,
    )
    assert marked_button
    assert "Пренавиване: 8" in marked_button.group(0)
    assert "is-marked" in marked_button.group(0)

    paused_html = render_terminal(paused_id)
    assert 'data-card-status="paused"' in paused_html
    assert 'data-roll-change-controls' in paused_html
    assert re.search(r'<button[^>]+data-rewinding-open', paused_html)

    for unavailable_id in (pending_id, waiting_id, completed_id):
        unavailable_html = render_terminal(unavailable_id)
        assert 'data-roll-change-controls' not in unavailable_html
        assert 'data-roll-change-overlay' not in unavailable_html


def test_terminal_v8_rewinding_dialog_posts_version_and_reopens_only_for_errors(
    connection,
):
    card_id = release_ready_card("26193", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok

    html = render_terminal(
        card_id,
        rewinding_result=RuleResult(
            False,
            ("Броят за пренавиване трябва да бъде цяло число от 1 до 999.",),
        ),
        rewinding_result_value=" 12x ",
        rewinding_dialog_open=True,
    )

    dialog = html_between_ids(html, "rewinding-overlay", "finish-confirm-modal")
    assert 'role="dialog"' in dialog
    assert 'aria-modal="true"' in dialog
    assert 'aria-labelledby="rewinding-title"' in dialog
    assert '<h2 class="rewinding-title" id="rewinding-title">Ролки за пренавиване</h2>' in dialog
    form = form_block(html, f"/terminal/cards/{card_id}/rewinding-count")
    assert f'name="loaded_version" value="{card_version(card_id)}"' in form
    assert 'type="text"' in form
    assert 'inputmode="numeric"' in form
    assert 'pattern="[0-9]{0,3}"' in form
    assert 'maxlength="3"' in form
    assert 'name="rewinding_roll_count"' in form
    assert 'value=" 12x "' in form
    assert "Оставете празно или въведете 0, за да изчистите." in form
    assert ">Запиши</button>" in form
    assert ">Отказ</button>" in dialog
    assert 'data-feedback-target="rewinding"' in form
    assert 'role="alert"' in form
    assert "Броят за пренавиване трябва да бъде цяло число от 1 до 999." in form
    assert 'id="rewinding-overlay"' in html
    rewinding_overlay = re.search(r'<div[^>]+id="rewinding-overlay"[^>]*>', html)
    assert rewinding_overlay
    assert not re.search(r"\shidden(?:\s|>)", rewinding_overlay.group(0))
    assert re.search(r'<div[^>]+id="waiting-overlay"[^>]*hidden', html)


def test_terminal_v8_waiting_and_rewinding_scripts_coordinate_modal_lifecycle(connection):
    card_id = release_ready_card("26194", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok

    html = render_terminal(card_id)

    assert "const openWaiting = () =>" in html
    assert "const closeWaiting = (restoreFocus = true) =>" in html
    assert "const openRewinding = () =>" in html
    assert "const closeRewinding = (restoreFocus = true) =>" in html
    assert "closeQueue(false);" in html
    assert "closeHistory(false);" in html
    assert "closeWaiting(false);" in html
    assert "closeRewinding(false);" in html
    assert 'event.key === "Escape"' in html
    assert "event.target === waitingOverlay" in html
    assert "event.target === rewindingOverlay" in html
    assert "(waitingReturnFocus || waitingOpenButton)?.focus" in html
    assert "(rewindingReturnFocus || rewindingOpenButton)?.focus" in html
    assert "focusableModalElements" in html
    assert "trapModalFocus" in html
    trap_start = html.index("const trapModalFocus")
    trap_end = html.index("const setCorrectionControlLock", trap_start)
    trap_script = html[trap_start:trap_end]
    assert "!dialog?.contains(document.activeElement)" in trap_script
    shift_start = html.index("const shiftWindow")
    shift_end = html.index("const finishConfirmModal", shift_start)
    assert "!dialog?.contains(document.activeElement)" not in html[shift_start:shift_end]
    assert 'if (overlay.classList.contains("open")) {' in html
    assert 'if (historyOverlay.classList.contains("open")) {' in html
    assert "waitingRows.forEach" in html
    assert "correctionModeOpen" in html
    assert "#waiting-open" in html
    assert "[data-rewinding-open]" in html
    assert "[data-waiting-row]" in html


def test_terminal_queue_produced_and_finish_overlays_render_modal_semantics(connection):
    card_id = release_ready_card("26194-modal-semantics", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok

    html = render_terminal(card_id)
    queue = html_between_ids(html, "queue-overlay", "waiting-overlay")
    produced = html_between_ids(html, "history-overlay", "finish-confirm-modal")
    finish_start = html.find('id="finish-confirm-modal"')
    finish_end = html.find("<script>", finish_start)
    assert finish_start != -1 and finish_end != -1
    finish = html[finish_start:finish_end]

    assert 'role="dialog"' in queue
    assert 'aria-modal="true"' in queue
    assert 'aria-labelledby="queue-title"' in queue
    assert 'tabindex="-1"' in queue
    assert '<h2 id="queue-title">Опашка по машини</h2>' in queue
    assert 'role="dialog"' in produced
    assert 'aria-modal="true"' in produced
    assert 'aria-labelledby="history-title"' in produced
    assert 'tabindex="-1"' in produced
    assert '<h2 id="history-title">Произведени поръчки</h2>' in produced
    assert 'role="dialog"' in finish
    assert 'aria-modal="true"' in finish


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


def test_terminal_v8_waiting_recipe_actual_inputs_remain_enabled(connection):
    card_id = release_ready_card("26145", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_rewinding_roll_count(card_id, card_version(card_id), 2).ok
    assert db.finish_card(card_id, card_version(card_id)).ok

    recipe_form = form_block(
        render_terminal(card_id),
        f"/terminal/cards/{card_id}/materials",
    )

    for field_name in ("actual_material__raw_material_a", "batch_lot__raw_material_a"):
        input_tag = re.search(
            rf'<input[^>]+name="{field_name}"[^>]*>',
            recipe_form,
        )
        assert input_tag is not None
        assert "disabled" not in input_tag.group(0)


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


def test_target_gross_uses_ordered_gross_kg_and_ignores_other_ordered_amounts(
    connection,
):
    card_id = release_ready_card(
        "26141",
        machine_id=1,
        sequence=1,
        ordered_gross_kg="100",
        ordered_rolls="9999",
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


def test_terminal_v8_rounds_machine_progress_but_shows_bottom_totals_with_one_decimal(
    connection,
):
    card_id = release_ready_card(
        "26145",
        machine_id=1,
        sequence=1,
        ordered_gross_kg="1000",
    )
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "0.25").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "100.55").ok

    html = render_terminal(card_id)

    assert '<span class="machine-tab-qty">101 / 1000 кг</span>' in html
    assert re.search(
        r'<span class="field-label">Бруто</span>\s*<div class="big">100\.6</div>',
        html,
    )
    assert re.search(
        r'<span class="field-label">Оставащи</span>\s*<div class="big">899\.5</div>',
        html,
    )
    assert re.search(
        r'<span class="field-label">Нето</span>\s*<div class="big">100\.3</div>',
        html,
    )
    assert re.search(r'value="100\.55"', html)
    assert 'data-roll-display="net">100.3</span>' in html
    assert "100.50 / 1000.00 кг" not in html


def test_terminal_v8_keeps_totals_visible_if_server_context_lacks_new_display_fields(
    connection,
):
    card_id = release_ready_card(
        "26146",
        machine_id=1,
        sequence=1,
        ordered_gross_kg="1000",
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


def test_terminal_v8_does_not_show_fake_zero_target_when_ordered_gross_kg_is_invalid(
    connection,
):
    card_id = release_ready_card(
        "26142",
        machine_id=1,
        sequence=1,
    )
    card = db.fetch_admin_card_detail(card_id)
    fields = {field: str(card[field] or "") for field in IMPORT_FIELDS}
    fields["ordered_gross_kg"] = ""
    fields["ordered_rolls"] = "20"
    fields["ordered_meters"] = "20"
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
    assert 'aria-label="Редактирай ролка 1"' in completed_html


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
    assert 'data-icon-asset="start"' in start_form
    assert 'aria-hidden="true"' in start_form
    assert "Старт" in start_form
    assert 'data-icon-asset="pause"' in pending_html
    assert 'data-icon-asset="end"' in pending_html
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
    assert 'data-icon-asset="pause"' in pause_form
    assert "Пауза" in pause_form
    assert 'data-icon-asset="end"' in finish_form
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
    assert 'data-icon-asset="start"' in resume_form
    assert "Продължи" in resume_form


def test_terminal_timing_context_models_running_and_paused_ledgers(connection):
    running_id = release_ready_card("26182-timing-running", machine_id=1, sequence=1)
    assert db.start_production_timing(running_id, card_version(running_id)).ok
    with db.connect() as timing_connection:
        running_segment_id = int(
            timing_connection.execute(
                "SELECT id FROM production_time_segments WHERE card_id = ?",
                (running_id,),
            ).fetchone()["id"]
        )
        timing_connection.execute(
            """
            UPDATE production_time_segments
            SET started_at = '2026-01-15 08:00:37'
            WHERE id = ?
            """,
            (running_segment_id,),
        )

    running_context = terminal_context(running_id)
    running_model = running_context["terminal_timing"]
    assert running_model["card_id"] == running_id
    assert running_model["status"] == "running"
    assert running_model["loaded_version"] == card_version(running_id)
    assert running_model["server_now_utc"]
    assert running_model["server_now_display"]
    assert running_model["draft"] == [
        {
            "segment_id": running_segment_id,
            "start_date": "2026-01-15",
            "start_time": "10:00",
            "stop_date": "",
            "stop_time": "",
            "deleted": False,
        }
    ]
    assert running_model["display"]["production_seconds"] >= 0

    paused_id = release_ready_card("26182-timing-paused", machine_id=2, sequence=1)
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok
    paused_context = terminal_context(paused_id)
    paused_model = paused_context["terminal_timing"]
    assert paused_model["status"] == "paused"
    assert paused_model["draft"][0]["stop_date"]
    assert paused_model["draft"][0]["stop_time"]


def test_terminal_timing_context_blocks_missing_shift_and_other_statuses(connection):
    pending_id = release_ready_card("26182-timing-pending", machine_id=1, sequence=1)
    assert terminal_context(pending_id)["terminal_timing"] is None

    completed_id = release_ready_card(
        "26182-timing-completed",
        machine_id=2,
        sequence=1,
    )
    complete_card(completed_id)
    assert terminal_context(completed_id)["terminal_timing"] is None

    waiting_id = release_ready_card("26182-timing-waiting", machine_id=3, sequence=1)
    assert db.start_production_timing(waiting_id, card_version(waiting_id)).ok
    assert db.update_rewinding_roll_count(
        waiting_id,
        card_version(waiting_id),
        1,
    ).ok
    assert db.finish_card(waiting_id, card_version(waiting_id)).ok
    assert terminal_context(waiting_id)["terminal_timing"] is None

    running_id = release_ready_card(
        "26182-timing-no-shift",
        machine_id=4,
        sequence=1,
    )
    assert db.start_production_timing(running_id, card_version(running_id)).ok
    end_active_test_shift()
    assert terminal_context(running_id)["terminal_timing"] is None


def test_terminal_timing_context_retains_invalid_and_locks_stale_drafts(connection):
    card_id = release_ready_card("26182-timing-retained", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    segment_id = int(card["timing_segments"][0]["id"])
    submitted = db.TimingDraftRow(
        segment_id,
        "2026-01-15",
        "10:00",
        "2026-01-15",
        "10:00",
    )
    loaded_version = str(card_version(card_id))

    invalid_context = terminal_context(
        card_id,
        terminal_timing_draft=[submitted],
        terminal_timing_loaded_version=loaded_version,
        terminal_timing_stale=False,
    )
    assert invalid_context["terminal_timing"]["draft"] == [
        {
            "segment_id": segment_id,
            "start_date": "2026-01-15",
            "start_time": "10:00",
            "stop_date": "2026-01-15",
            "stop_time": "10:00",
            "deleted": False,
        }
    ]
    assert invalid_context["terminal_timing"]["locked"] is False

    stale_context = terminal_context(
        card_id,
        terminal_timing_draft=[submitted],
        terminal_timing_loaded_version=loaded_version,
        terminal_timing_stale=True,
    )
    assert stale_context["terminal_timing"]["draft"] == invalid_context[
        "terminal_timing"
    ]["draft"]
    assert stale_context["terminal_timing"]["locked"] is True


def test_terminal_timing_menu_visibility_icon_and_lifecycle_markup(connection):
    card_id = release_ready_card("26182-timing-menu", machine_id=1, sequence=1)

    pending_version = card_version(card_id)
    pending_html = render_terminal(card_id)
    pending_start = form_block(
        pending_html,
        f"/terminal/cards/{card_id}/timing/start",
    )
    assert normalized_markup(pending_start) == accepted_lifecycle_form_snapshot(
        action=f"/terminal/cards/{card_id}/timing/start",
        slot="start",
        version=pending_version,
        icon="start",
        label="Старт",
        button_class="action-button action-primary",
    )
    assert '<div class="timing-menu" data-timing-menu>' not in pending_html

    assert db.start_production_timing(card_id, pending_version).ok
    running_version = card_version(card_id)
    running_card = terminal_context(card_id)["selected_card"]
    running_html = render_terminal(card_id)
    running_pause = form_block(
        running_html,
        f"/terminal/cards/{card_id}/timing/pause",
    )
    running_finish = form_block(
        running_html,
        f"/terminal/cards/{card_id}/finish",
    )
    assert normalized_markup(running_pause) == accepted_lifecycle_form_snapshot(
        action=f"/terminal/cards/{card_id}/timing/pause",
        slot="pause",
        version=running_version,
        icon="pause",
        label="Пауза",
        button_class="action-button action-secondary",
    )
    assert 'data-timing-finish-review="true"' in running_finish
    assert 'data-finish-confirm-form="true"' not in running_finish
    accepted_running_finish = running_finish.replace(
        'data-timing-finish-review="true"',
        'data-finish-confirm-form="true"',
    )
    assert normalized_markup(
        accepted_running_finish
    ) == accepted_lifecycle_form_snapshot(
        action=f"/terminal/cards/{card_id}/finish",
        slot="finish",
        version=running_version,
        icon="end",
        label="Приключи",
        button_class="action-button action-primary",
        finish_message=running_card["finish_confirmation_message"],
    )
    assert running_html.count('data-lifecycle-slot=') == 3
    assert running_html.index('data-lifecycle-slot="finish"') < running_html.index(
        "data-timing-menu"
    )
    assert running_html.count("Производствено време") >= 1
    assert 'aria-label="Още действия"' in running_html
    assert 'aria-haspopup="menu"' in running_html
    assert 'aria-expanded="false"' in running_html
    assert 'role="menu"' in running_html
    assert 'role="menuitem"' in running_html
    assert re.search(
        r'<img[^>]+src="/static/images/terminal-ui/clock-icon\.png"'
        r'[^>]+width="17"[^>]+height="17"[^>]+alt=""',
        running_html,
    )
    assert Path(
        "app/static/images/terminal-ui/clock-icon.png"
    ).read_bytes() == Path("ui-prototypes/clock-icon.png").read_bytes()

    assert db.pause_production_timing(card_id, running_version).ok
    paused_version = card_version(card_id)
    paused_card = terminal_context(card_id)["selected_card"]
    paused_html = render_terminal(card_id)
    paused_resume = form_block(
        paused_html,
        f"/terminal/cards/{card_id}/timing/resume",
    )
    paused_finish = form_block(
        paused_html,
        f"/terminal/cards/{card_id}/finish",
    )
    assert normalized_markup(paused_resume) == accepted_lifecycle_form_snapshot(
        action=f"/terminal/cards/{card_id}/timing/resume",
        slot="pause",
        version=paused_version,
        icon="start",
        label="Продължи",
        button_class="action-button action-primary",
    )
    accepted_paused_finish = paused_finish.replace(
        'data-timing-finish-review="true"',
        'data-finish-confirm-form="true"',
    )
    assert normalized_markup(
        accepted_paused_finish
    ) == accepted_lifecycle_form_snapshot(
        action=f"/terminal/cards/{card_id}/finish",
        slot="finish",
        version=paused_version,
        icon="end",
        label="Приключи",
        button_class="action-button action-secondary",
        finish_message=paused_card["finish_confirmation_message"],
    )
    assert paused_html.count("data-timing-menu") >= 1

    assert db.update_rewinding_roll_count(card_id, paused_version, 2).ok
    assert db.finish_card(card_id, card_version(card_id)).ok
    waiting_version = card_version(card_id)
    waiting_card = terminal_context(card_id)["selected_card"]
    waiting_html = render_terminal(card_id)
    waiting_finish = form_block(
        waiting_html,
        f"/terminal/cards/{card_id}/finish",
    )
    assert normalized_markup(waiting_finish) == accepted_lifecycle_form_snapshot(
        action=f"/terminal/cards/{card_id}/finish",
        slot="finish",
        version=waiting_version,
        icon="end",
        label="Приключи",
        button_class="action-button action-primary",
        finish_message=waiting_card["finish_confirmation_message"],
    )
    assert '<div class="timing-menu" data-timing-menu>' not in waiting_html


def test_terminal_timing_dialog_matches_approved_v2_contract(connection):
    card_id = release_ready_card("26182-timing-dialog", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok

    html = render_terminal(card_id)
    controller_path = Path("app/static/js/timing_interval_editor.mjs")
    assert controller_path.exists()
    controller_source = controller_path.read_text(encoding="utf-8")

    assert html.count('data-timing-editor-overlay') == 1
    assert re.search(
        r'<div[^>]+data-timing-editor-overlay[^>]+hidden[^>]+aria-hidden="true"',
        html,
    )
    assert re.search(
        r'<section[^>]+class="timing-dialog"[^>]+role="dialog"'
        r'[^>]+aria-modal="true"[^>]+aria-labelledby="timing-dialog-title"'
        r'[^>]+aria-describedby="timing-dialog-context"[^>]+tabindex="-1"',
        html,
    )
    assert '<h2 id="timing-dialog-title">Корекция на производствено време</h2>' in html
    assert 'id="timing-dialog-context"' in html
    assert html.count("Производствено време") >= 2
    assert "Общо паузирано време" in html
    assert [
        html.index(">№</div>", html.index('data-timing-column-headings')),
        html.index(">Начало</span>", html.index('data-timing-column-headings')),
        html.index(">Край</span>", html.index('data-timing-column-headings')),
        html.index(">Продължителност</div>", html.index('data-timing-column-headings')),
        html.index(">Действие</div>", html.index('data-timing-column-headings')),
    ] == sorted(
        [
            html.index(">№</div>", html.index('data-timing-column-headings')),
            html.index(">Начало</span>", html.index('data-timing-column-headings')),
            html.index(">Край</span>", html.index('data-timing-column-headings')),
            html.index(">Продължителност</div>", html.index('data-timing-column-headings')),
            html.index(">Действие</div>", html.index('data-timing-column-headings')),
        ]
    )
    assert 'class="interval-scroll" data-timing-interval-list tabindex="-1"' in html
    assert 'role="alert" tabindex="-1" data-timing-alert hidden' in html
    assert 'data-timing-add-interval>Добави интервал</button>' in html
    assert 'data-timing-reload hidden>Презареди</a>' in html
    assert 'data-timing-cancel>Отказ</button>' in html
    assert 'data-timing-save>Запиши</button>' in html
    assert 'name="loaded_version"' in html
    assert 'name="timing_draft"' in html
    assert 'type="application/json" data-terminal-timing-model' in html
    assert '/static/js/timing_interval_editor.mjs' in html

    dialog_rules = css_rules(html, r"(?m)^    \.timing-dialog")
    assert "width: min(1040px, calc(100vw - 40px));" in dialog_rules
    assert re.search(
        r"(?m)^\s*height: min\(728px, calc\(100vh - 40px\)\);$",
        dialog_rules,
    ) is None
    assert "max-height: min(728px, calc(100vh - 40px));" in dialog_rules
    assert "grid-template-rows: auto auto auto minmax(0, 1fr) auto;" in dialog_rules
    overlay_rules = css_rules(html, r"(?m)^    \.timing-modal-overlay")
    assert "padding: 20px;" in overlay_rules
    menu_button_rules = css_rules(html, r"(?m)^    \.timing-menu-button")
    assert "color: var(--primary-text);" in menu_button_rules
    scroll_rules = css_rules(html, r"(?m)^    \.interval-scroll")
    assert "overflow-y: auto;" in scroll_rules
    assert "max-height: min(430px, calc(100vh - 338px));" in scroll_rules
    columns_rules = css_rules(
        html,
        r"(?m)^    \.interval-columns,\s*\.interval-row",
    )
    assert "48px minmax(0, 1fr) minmax(0, 1fr) 150px 96px" in columns_rules
    row_rule_sets = css_rules_all(html, r"(?m)^    \.interval-row")
    assert any("min-height: 72px;" in rules for rules in row_rule_sets)
    assert any("padding: 8px 24px;" in rules for rules in row_rule_sets)
    delete_rules = css_rules(html, r"(?m)^    \.interval-delete")
    assert "border-color: var(--line);" in delete_rules
    assert "background: var(--surface);" in delete_rules
    assert "color: var(--text);" in delete_rules
    assert "min-width: 72px;" in delete_rules
    assert "min-height: 40px;" in delete_rules
    segmented_date_rules = css_rules(html, r"(?m)^    \.segmented-date-input")
    assert "grid-template-columns: 22px 5px 22px 5px 44px;" in segmented_date_rules
    assert "justify-content: center;" in segmented_date_rules
    separator_rules = css_rules(
        html,
        r"(?m)^    \.interval-columns > div:not\(:first-child\),\s*\.interval-row > div:not\(:first-child\)",
    )
    assert "border-left: 1px solid #dfe5eb;" in separator_rules

    assert 'from "./timing_interval_editor_core.mjs"' in controller_source
    for reused_export in (
        "addIntervalDraft",
        "canDeleteTimingRow",
        "dateSegmentsFromValue",
        "dateValueFromSegments",
        "incompleteDraftFields",
        "mapServerPreview",
        "markIntervalDeleted",
        "maskTimeInput",
        "maskedCaretPosition",
        "serializeTimingDraft",
        "visibleTimingRows",
    ):
        assert reused_export in controller_source
    assert 'input.type = "date"' not in controller_source
    assert 'group.className = "segmented-date-input"' in controller_source
    assert 'input.dataset.dateSegment = definition.key' in controller_source
    assert '{ key: "day", label: "ден", maxLength: 2, placeholder: "дд" }' in controller_source
    assert '{ key: "month", label: "месец", maxLength: 2, placeholder: "мм" }' in controller_source
    assert '{ key: "year", label: "година", maxLength: 4, placeholder: "гггг" }' in controller_source
    assert 'inputMode = "numeric"' in controller_source
    assert 'maxLength = 5' in controller_source
    assert 'stopCell.replaceChildren()' in controller_source
    assert 'button.textContent = "Изтрий"' in controller_source
    assert (
        "Сигурни ли сте, че искате да изтриете интервал "
        "№${row.display_number}?"
    ) in controller_source
    assert "undoIntervalDelete" not in controller_source
    assert "pending-delete" not in controller_source
    assert "openEditor({ opener: menuButton });" in controller_source
    assert "new Date(" not in controller_source
    assert "Date.parse(" not in controller_source
    assert "Добави пауза" not in html
    assert "ongoing" not in html


def test_terminal_timing_delete_confirmation_and_presentation_contract(connection):
    card_id = release_ready_card(
        "26182-timing-final-correction",
        machine_id=1,
        sequence=1,
    )
    assert db.start_production_timing(card_id, card_version(card_id)).ok

    html = render_terminal(card_id)
    controller_source = Path(
        "app/static/js/timing_interval_editor.mjs"
    ).read_text(encoding="utf-8")

    assert 'data-timing-delete-confirm-overlay hidden aria-hidden="true"' in html
    assert 'role="dialog" aria-modal="true"' in html
    assert 'aria-labelledby="timing-delete-confirm-title"' in html
    assert 'aria-describedby="timing-delete-confirm-prompt"' in html
    assert (
        '<h2 class="finish-confirm-title" id="timing-delete-confirm-title">'
        'Изтриване на интервал</h2>'
    ) in html
    assert 'data-timing-delete-confirm-prompt' in html
    assert 'data-timing-delete-confirm-cancel>Отказ</button>' in html
    assert 'data-timing-delete-confirm-submit>Изтрий</button>' in html
    assert "window.confirm" not in controller_source
    assert (
        "Сигурни ли сте, че искате да изтриете интервал "
        "№${row.display_number}?"
    ) in controller_source

    delete_overlay_rules = css_rules(
        html,
        r"(?m)^    \.timing-delete-confirm-modal",
    )
    assert "z-index: 120;" in delete_overlay_rules
    delete_submit_rules = css_rules(
        html,
        r"(?m)^    \.timing-delete-confirm-submit",
    )
    assert "background: var(--surface);" in delete_submit_rules
    assert "color: var(--primary-text);" in delete_submit_rules
    assert "var(--red)" not in delete_submit_rules

    assert '<span class="timing-column-heading--timestamp">Начало</span>' in html
    assert '<span class="timing-column-heading--timestamp">Край</span>' in html
    timestamp_heading_rules = css_rules(
        html,
        r"(?m)^    \.timing-column-heading--timestamp",
    )
    assert "width: 206px;" in timestamp_heading_rules
    duration_axis_rules = css_rules(
        html,
        r"(?m)^    \.interval-columns > div:nth-child\(4\),\s*"
        r"\.interval-row > div:nth-child\(4\)",
    )
    assert "justify-content: center;" in duration_axis_rules

    assert 'separator.textContent = "/"' in controller_source
    assert 'separator.textContent = "."' not in controller_source
    assert "min-width: 46rem;" not in html
    assert html.count("0 ч 00 м") == 2
    assert "0 ч 00 мин" not in html
    assert 'padStart(2, "0")} м`' in controller_source
    assert 'padStart(2, "0")} мин`' not in controller_source


def test_terminal_timing_errors_use_stable_summary_and_boundary_highlights(connection):
    card_id = release_ready_card(
        "26182-timing-error-slots",
        machine_id=1,
        sequence=1,
    )
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    html = render_terminal(card_id)
    controller = Path(
        "app/static/js/timing_interval_editor.mjs"
    ).read_text(encoding="utf-8")

    assert 'id="timing-dialog-alert"' in html
    assert 'wrapper.dataset.timingFieldWrapper = "true"' in controller
    assert "wrapper.append(input)" in controller
    assert "timingFieldError" not in controller
    assert 'input.setAttribute("aria-describedby", "timing-dialog-alert")' in controller
    assert 'input.setAttribute("aria-invalid", "true")' in controller
    assert "showAlert(formMessages" in controller


def test_terminal_v8_finish_form_uses_app_native_confirmation_modal(connection):
    card_id = release_ready_card("26183", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok

    running_html = render_terminal(card_id)
    pause_form = form_block(running_html, f"/terminal/cards/{card_id}/timing/pause")
    assert db.update_rewinding_roll_count(card_id, card_version(card_id), 1).ok
    assert db.finish_card(card_id, card_version(card_id)).ok
    html = render_terminal(card_id)
    finish_form = form_block(html, f"/terminal/cards/{card_id}/finish")

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
    assert ">Да</button>" in html
    assert 'data-finish-confirm-cancel' in html
    assert ">Не</button>" in html


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


def test_active_finish_uses_review_while_waiting_finish_keeps_simple_confirmation(
    connection,
):
    active_id = release_ready_card(
        "26184-reviewed-active",
        machine_id=1,
        sequence=1,
    )
    assert db.start_production_timing(active_id, card_version(active_id)).ok
    assert db.update_tare_weight(active_id, card_version(active_id), "1.00").ok
    assert db.add_roll_gross_weight(active_id, card_version(active_id), "25.00").ok
    active_card = db.fetch_terminal_card_detail(active_id)
    assert active_card is not None
    active_segment_id = int(active_card["timing_segments"][0]["id"])
    with db.connect() as setup_connection:
        setup_connection.execute(
            """
            UPDATE production_time_segments
            SET started_at = '2026-01-15 08:00:37'
            WHERE id = ?
            """,
            (active_segment_id,),
        )
        setup_connection.execute(
            """
            UPDATE cards
            SET first_started_at = '2026-01-15 08:00:37'
            WHERE id = ?
            """,
            (active_id,),
        )
    loaded_version = card_version(active_id)
    active_html = render_terminal(active_id)
    active_finish_markup = form_block(
        active_html,
        f"/terminal/cards/{active_id}/finish",
    )
    finish_review_start = active_html.index("data-finish-review-overlay")
    finish_review_end = active_html.index(
        'class="finish-confirm-modal"',
        finish_review_start,
    )
    finish_review_markup = active_html[finish_review_start:finish_review_end]
    controller_source = Path(
        "app/static/js/timing_interval_editor.mjs"
    ).read_text(encoding="utf-8")

    assert 'data-timing-finish-review="true"' in active_finish_markup
    assert 'data-finish-confirm-form="true"' not in active_finish_markup
    assert active_html.count("data-finish-review-overlay") == 1
    assert 'aria-labelledby="finish-review-title"' in active_html
    assert 'role="alert" tabindex="-1" data-finish-review-alert hidden' in active_html
    assert '<h2 id="finish-review-title">Преглед преди приключване</h2>' in active_html
    assert "Проверете производствените интервали" not in finish_review_markup
    assert "Първо начало" not in finish_review_markup
    assert "Предложен край" not in finish_review_markup
    assert "Начало" in finish_review_markup
    assert "Край" in finish_review_markup
    assert 'data-finish-timing-summary' in finish_review_markup
    assert 'data-finish-production-summary' in finish_review_markup
    for heading in (
        "Палет №",
        "Брой ролки",
        "Бруто, кг",
        "Тегло на палета, кг",
        "Нето, кг",
    ):
        assert heading in finish_review_markup
    assert 'data-finish-pallet-weight>—</td>' in finish_review_markup
    assert 'data-finish-pallet-weight-total>—</td>' in finish_review_markup
    assert "Без палет" in finish_review_markup
    assert "25.0" in finish_review_markup
    assert "24.0" in finish_review_markup
    assert 'data-finish-review-edit>Редактирай времето</button>' in active_html
    assert 'data-finish-review-cancel>Отказ</button>' in active_html
    assert (
        'class="finish-confirm-primary" type="button" '
        'data-finish-review-confirm>Потвърди приключване</button>'
    ) in active_html
    assert 'form[data-timing-finish-review="true"]' in controller_source
    assert "`${activeFinishForm.action}-review`" in controller_source
    assert "`${activeFinishForm.action}-review/preview`" in controller_source
    assert "responsePayload.preview.draft" in controller_source
    assert 'name = "review_token"' in controller_source
    assert 'name = "timing_draft"' in controller_source
    assert 'overlay.addEventListener("click"' not in controller_source
    assert 'cancelButton.addEventListener("click", cancelEditor)' in controller_source
    finish_submit_start = controller_source.index(
        'activeFinishForm.addEventListener("submit", (event) => {'
    )
    finish_submit_end = controller_source.index("});", finish_submit_start)
    finish_submit_handler = controller_source[finish_submit_start:finish_submit_end]
    assert "if (finishNativeSubmit)" in finish_submit_handler
    assert finish_submit_handler.index("event.preventDefault();") < finish_submit_handler.index(
        "if (finishSubmitting)"
    )
    assert "finishNativeSubmit = true;" in controller_source
    assert "activeFinishForm.requestSubmit();\n    } finally {\n      finishNativeSubmit = false;" in controller_source

    missing_review = asyncio.run(
        finish_terminal_card(
            make_test_request(f"/terminal/cards/{active_id}/finish"),
            active_id,
            str(loaded_version),
        )
    )

    assert missing_review.status_code == 200
    assert missing_review.context["workflow_result"].messages == (
        "Прегледът за приключване е невалиден. Отворете го отново.",
    )
    assert db.fetch_terminal_card_detail(active_id)["status"] == "running"

    review_response = asyncio.run(
        route_endpoint("/terminal/cards/{card_id}/finish-review")(
            make_test_request(f"/terminal/cards/{active_id}/finish-review"),
            active_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)
    active_finish = asyncio.run(
        finish_terminal_card(
            make_test_request(f"/terminal/cards/{active_id}/finish"),
            active_id,
            str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=json.dumps(review_payload["preview"]["draft"]),
        )
    )

    assert active_finish.status_code == 303
    assert active_finish.headers["location"] == (
        f"/terminal/cards/{active_id}?notice=card_finished"
    )
    assert db.fetch_terminal_card_detail(active_id)["status"] == "completed"

    waiting_id = release_ready_card(
        "26184-reviewed-waiting",
        machine_id=2,
        sequence=1,
    )
    assert db.start_production_timing(waiting_id, card_version(waiting_id)).ok
    assert db.update_rewinding_roll_count(
        waiting_id,
        card_version(waiting_id),
        2,
    ).ok
    assert db.finish_card(waiting_id, card_version(waiting_id)).ok
    assert db.update_tare_weight(waiting_id, card_version(waiting_id), "1.00").ok
    assert db.add_roll_gross_weight(waiting_id, card_version(waiting_id), "25.00").ok
    waiting_before = db.fetch_terminal_card_detail(waiting_id)
    assert waiting_before is not None
    timing_before = [dict(row) for row in waiting_before["timing_segments"]]
    waiting_html = render_terminal(waiting_id)
    waiting_finish_markup = form_block(
        waiting_html,
        f"/terminal/cards/{waiting_id}/finish",
    )
    assert 'data-finish-confirm-form="true"' in waiting_finish_markup
    assert 'data-timing-finish-review="true"' not in waiting_finish_markup
    waiting_finish = asyncio.run(
        finish_terminal_card(
            make_test_request(f"/terminal/cards/{waiting_id}/finish"),
            waiting_id,
            str(waiting_before["version"]),
            review_token="malformed-review-token",
            timing_draft="{",
        )
    )

    waiting_after = db.fetch_terminal_card_detail(waiting_id)
    assert waiting_finish.status_code == 303
    assert waiting_after["status"] == "completed"
    assert waiting_after["finished_at"] == waiting_before["finished_at"]
    assert waiting_after["timing_segments"] == timing_before


def test_terminal_timing_errors_reopen_or_lock_the_submitted_draft(connection):
    card_id = release_ready_card("26184-timing-errors", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.pause_production_timing(card_id, card_version(card_id)).ok
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    segment_id = int(card["timing_segments"][0]["id"])
    loaded_version = card_version(card_id)
    submitted = db.TimingDraftRow(
        segment_id,
        "2026-01-15",
        "10:00",
        "2026-01-15",
        "10:00",
    )
    hostile_message = 'Краят е невалиден. </script><script>alert("x")</script>'
    issue = db.TimingValidationIssue(0, "stop_time", hostile_message)
    retained_preview = db.TimingLedgerPreview(
        draft_rows=(submitted,),
        intervals=({"source_index": 0, "duration_seconds": 3600},),
        first_started_at="2026-01-15 08:00:37",
        proposed_finished_at="2026-01-15 09:00:29",
        production_seconds=3600,
        paused_seconds=600,
        reviewed_at="2026-01-15 09:00:29",
    )

    ordinary_html = render_terminal(
        card_id,
        terminal_timing_dialog_open=True,
        terminal_timing_draft=[submitted],
        terminal_timing_loaded_version=str(loaded_version),
        terminal_timing_issues=(issue,),
        terminal_timing_stale=False,
        timing_result=RuleResult(False, (hostile_message,)),
    )
    ordinary_model = terminal_timing_model_from_html(ordinary_html)
    assert ordinary_model["editor_open"] is True
    assert ordinary_model["timing"]["loaded_version"] == loaded_version
    assert ordinary_model["timing"]["draft"] == [
        {
            "segment_id": segment_id,
            "start_date": "2026-01-15",
            "start_time": "10:00",
            "stop_date": "2026-01-15",
            "stop_time": "10:00",
            "deleted": False,
        }
    ]
    assert ordinary_model["issues"] == [
        {
            "source_index": 0,
            "field": "stop_time",
            "message": hostile_message,
        }
    ]
    assert hostile_message not in ordinary_html
    assert "\\u003c/script\\u003e" in ordinary_html

    finish_html = render_terminal(
        card_id,
        finish_review_open=True,
        finish_review_token="opaque-review-token",
        finish_review_draft=[submitted],
        finish_review_loaded_version=str(loaded_version),
        finish_review_issues=(issue,),
        finish_review_preview=retained_preview,
        finish_review_stale=True,
        workflow_result=RuleResult(False, (hostile_message,)),
    )
    finish_model = terminal_timing_model_from_html(finish_html)
    assert finish_model["finish_review"] == {
        "open": True,
        "review_token": "opaque-review-token",
        "loaded_version": loaded_version,
        "draft": ordinary_model["timing"]["draft"],
        "issues": ordinary_model["issues"],
        "messages": [hostile_message],
        "locked": True,
        "preview": {
            "first_start_display": "15.01.2026 10:00",
            "proposed_stop_display": "15.01.2026 11:00",
            "production_seconds": 3600,
            "paused_seconds": 600,
            "intervals": [{"source_index": 0, "duration_seconds": 3600}],
        },
    }

    controller_source = Path(
        "app/static/js/timing_interval_editor.mjs"
    ).read_text(encoding="utf-8")
    assert "if (model.finish_review?.open)" in controller_source
    assert "initialFinishReviewHydration(" in controller_source
    assert "finishReview.draft.length > 0" in controller_source
    assert "retainedFinishPreview(model.finish_review, retainedDraft)" in controller_source
    assert "renderServerErrors" in controller_source
    assert 'const prefix = issue.field.startsWith("start_") ? "start" : "stop"' in controller_source
    assert "targetFields.forEach((field)" in controller_source
    assert "lockTimingDraft" in controller_source
    assert "reloadLink.hidden = false" in controller_source
    assert "finishConfirmButton.disabled = true" in controller_source

    begin_review_start = controller_source.index("async function beginFinishReview()")
    begin_review_end = controller_source.index(
        "async function applyFinishDraft()", begin_review_start
    )
    begin_review = controller_source[begin_review_start:begin_review_end]
    assert "const hasRowErrors = (responsePayload.field_errors || []).some" in begin_review
    stale_branch = begin_review.index("if (response.status === 409)")
    assert begin_review.index("openEditor({", stale_branch) < begin_review.index(
        "lockTimingDraft(responsePayload.messages)", stale_branch
    )
    row_error_branch = begin_review.index("if (hasRowErrors)")
    row_error_end = begin_review.index("openFinishSummary", row_error_branch)
    row_error_recovery = begin_review[row_error_branch:row_error_end]
    assert 'mode: "ordinary"' in row_error_recovery
    assert "запишете промените" in row_error_recovery
    assert "renderServerErrors" in row_error_recovery
    assert "finishConfirmButton.disabled = true" in begin_review
    assert "finishEditButton.disabled = true" in begin_review
    assert begin_review.count("focusFinishAlert();") == 2
    assert "showFinishAlert(retainedMessages);" in controller_source
    assert "finishEditButton.disabled = retainedMessages.length > 0" in controller_source
    assert "finishConfirmButton.disabled = retainedMessages.length > 0" in controller_source


def test_terminal_finish_no_roll_failure_retains_message_in_review_model(connection):
    card_id = release_ready_card(
        "26184-reviewed-no-roll",
        machine_id=1,
        sequence=1,
    )
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    with db.connect() as setup_connection:
        setup_connection.execute(
            """
            UPDATE production_time_segments
            SET started_at = '2026-01-15 08:00:37'
            WHERE card_id = ?
            """,
            (card_id,),
        )
        setup_connection.execute(
            """
            UPDATE cards
            SET first_started_at = '2026-01-15 08:00:37'
            WHERE id = ?
            """,
            (card_id,),
        )
    loaded_version = card_version(card_id)
    review_response = asyncio.run(
        route_endpoint("/terminal/cards/{card_id}/finish-review")(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)

    response = asyncio.run(
        finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=json.dumps(review_payload["preview"]["draft"]),
            finish_review_preview=json.dumps(review_payload["preview"]),
        )
    )

    message = "Поне едно бруто тегло на ролка е задължително преди приключване."
    html = response.body.decode("utf-8")
    model = terminal_timing_model_from_html(html)
    assert response.status_code == 200
    assert response.context["workflow_result"].messages == (message,)
    assert model["finish_review"]["open"] is True
    assert model["finish_review"]["issues"] == []
    assert model["finish_review"]["messages"] == [message]

    controller_source = Path(
        "app/static/js/timing_interval_editor.mjs"
    ).read_text(encoding="utf-8")
    assert "retainedFinishReviewMessages(finishReview)" in controller_source
    assert "finishEditButton.disabled = retainedMessages.length > 0" in controller_source
    assert "finishConfirmButton.disabled = retainedMessages.length > 0" in controller_source
    assert "focusFinishAlert();" in controller_source


def test_terminal_initial_stale_finish_hydration_preserves_exact_locked_draft(
    connection,
):
    card_id = release_ready_card(
        "26184-reviewed-stale-hydration-order",
        machine_id=1,
        sequence=1,
    )
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.pause_production_timing(card_id, card_version(card_id)).ok
    loaded_version = card_version(card_id)
    retained_rows = [
        db.TimingDraftRow(
            202,
            "2026-08-20",
            "10:00",
            "2026-08-20",
            "12:00",
        ),
        db.TimingDraftRow(
            101,
            "2026-08-20",
            "08:00",
            "2026-08-20",
            "09:00",
        ),
    ]
    retained_preview = db.TimingLedgerPreview(
        draft_rows=tuple(retained_rows),
        intervals=(
            {"source_index": 1, "duration_seconds": 3_600},
            {"source_index": 0, "duration_seconds": 7_200},
        ),
        first_started_at="2026-08-20 05:00:00",
        proposed_finished_at="2026-08-20 09:00:00",
        production_seconds=10_800,
        paused_seconds=3_600,
        reviewed_at="2026-08-20 09:00:00",
    )

    html = render_terminal(
        card_id,
        finish_review_open=True,
        finish_review_token="opaque-stale-review-token",
        finish_review_draft=retained_rows,
        finish_review_loaded_version=str(loaded_version),
        finish_review_issues=(),
        finish_review_preview=retained_preview,
        finish_review_stale=True,
        workflow_result=RuleResult(False, (STALE_CARD_MESSAGE,)),
    )
    model = terminal_timing_model_from_html(html)
    controller_path = Path("app/static/js/timing_interval_editor.mjs")
    core_path = Path("app/static/js/timing_interval_editor_core.mjs")
    execution = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            f"""
globalThis.document = {{
  querySelector: () => null,
  querySelectorAll: () => [],
}};
const controller = await import({json.dumps(controller_path.resolve().as_uri())});
const core = await import({json.dumps(core_path.resolve().as_uri())});
const model = {json.dumps(model)};
const finishModel = model.finish_review;
const hydration = typeof controller.initialFinishReviewHydration === "function"
  ? controller.initialFinishReviewHydration(
      finishModel,
      model.timing.draft,
      model.timing.display,
    )
  : {{
      draft: finishModel.draft,
      preview: finishModel.preview,
      locked: false,
      lockedMessages: [],
    }};
const mapped = core.mapServerPreview(
  core.normalizeDraftDateInputs(hydration.draft),
  hydration.preview,
  {{ normalizeOrder: !hydration.locked }},
);
console.log(JSON.stringify({{
  rows: mapped.rows.map((row) => ({{
    segment_id: row.segment_id,
    start_date: row.start_date,
    start_time: row.start_time,
    stop_date: row.stop_date,
    stop_time: row.stop_time,
    duration_seconds: row.duration_seconds,
    display_number: row.display_number,
  }})),
  raw_draft: core.serializeTimingDraft(mapped.rows),
  actions_disabled: hydration.locked,
  stale_messages: hydration.lockedMessages,
  summary: {{
    first_start_display: hydration.preview.first_start_display,
    proposed_stop_display: hydration.preview.proposed_stop_display,
    production_seconds: hydration.preview.production_seconds,
    paused_seconds: hydration.preview.paused_seconds,
  }},
}}));
""",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    hydrated = json.loads(execution.stdout)
    assert hydrated == {
        "rows": [
            {
                "segment_id": 202,
                "start_date": "20.08.2026",
                "start_time": "10:00",
                "stop_date": "20.08.2026",
                "stop_time": "12:00",
                "duration_seconds": 7_200,
                "display_number": 1,
            },
            {
                "segment_id": 101,
                "start_date": "20.08.2026",
                "start_time": "08:00",
                "stop_date": "20.08.2026",
                "stop_time": "09:00",
                "duration_seconds": 3_600,
                "display_number": 2,
            },
        ],
        "raw_draft": [
            {
                "segment_id": 202,
                "start_date": "2026-08-20",
                "start_time": "10:00",
                "stop_date": "2026-08-20",
                "stop_time": "12:00",
                "deleted": False,
            },
            {
                "segment_id": 101,
                "start_date": "2026-08-20",
                "start_time": "08:00",
                "stop_date": "2026-08-20",
                "stop_time": "09:00",
                "deleted": False,
            },
        ],
        "actions_disabled": True,
        "stale_messages": [STALE_CARD_MESSAGE],
        "summary": {
            "first_start_display": "20.08.2026 08:00",
            "proposed_stop_display": "20.08.2026 12:00",
            "production_seconds": 10_800,
            "paused_seconds": 3_600,
        },
    }


def test_terminal_stale_confirmed_finish_retains_locked_alert_and_reload_focus(connection):
    card_id = release_ready_card(
        "26184-reviewed-stale",
        machine_id=1,
        sequence=1,
    )
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "25.00").ok
    with db.connect() as setup_connection:
        setup_connection.execute(
            """
            UPDATE production_time_segments
            SET started_at = '2026-01-15 08:00:37'
            WHERE card_id = ?
            """,
            (card_id,),
        )
        setup_connection.execute(
            """
            UPDATE cards
            SET first_started_at = '2026-01-15 08:00:37'
            WHERE id = ?
            """,
            (card_id,),
        )
    loaded_version = card_version(card_id)
    review_response = asyncio.run(
        route_endpoint("/terminal/cards/{card_id}/finish-review")(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)
    assert db.update_tare_weight(card_id, loaded_version, "1.25").ok

    response = asyncio.run(
        finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=json.dumps(review_payload["preview"]["draft"]),
            finish_review_preview=json.dumps(review_payload["preview"]),
        )
    )

    model = terminal_timing_model_from_html(response.body.decode("utf-8"))
    assert response.status_code == 200
    assert response.context["workflow_result"].messages == (STALE_CARD_MESSAGE,)
    assert db.fetch_terminal_card_detail(card_id)["status"] == "running"
    assert model["finish_review"]["open"] is True
    assert model["finish_review"]["locked"] is True
    assert model["finish_review"]["issues"] == []
    assert model["finish_review"]["messages"] == [STALE_CARD_MESSAGE]
    assert model["finish_review"]["preview"] == {
        "first_start_display": review_payload["preview"]["first_start_display"],
        "proposed_stop_display": review_payload["preview"]["proposed_stop_display"],
        "production_seconds": review_payload["preview"]["production_seconds"],
        "paused_seconds": review_payload["preview"]["paused_seconds"],
        "intervals": review_payload["preview"]["intervals"],
    }

    controller_path = Path("app/static/js/timing_interval_editor.mjs")
    controller_source = controller_path.read_text(encoding="utf-8")
    execution = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            f"""
globalThis.document = {{
  querySelector: () => null,
  querySelectorAll: () => [],
}};
const controller = await import({json.dumps(controller_path.resolve().as_uri())});
const retained = typeof controller.retainedFinishReviewMessages === "function"
  ? controller.retainedFinishReviewMessages({json.dumps(model["finish_review"])})
  : null;
console.log(JSON.stringify(retained));
""",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(execution.stdout) == [STALE_CARD_MESSAGE]

    hydration_start = controller_source.index("if (model.finish_review?.open)")
    hydration = controller_source[hydration_start:]
    finish_hydration_index = hydration.index(
        "const finishHydration = initialFinishReviewHydration("
    )
    retained_index = hydration.index(
        "const retainedMessages = finishHydration.lockedMessages;"
    )
    branch_index = hydration.index("const mustShowEditor")
    open_index = hydration.index("openEditor({", branch_index)
    locked_index = hydration.index("locked: finishHydration.locked", open_index)
    messages_index = hydration.index(
        "lockedMessages: retainedMessages", locked_index
    )
    row_errors_index = hydration.index(
        "renderServerErrors(model.finish_review.issues, {\n"
        "        focus: true,\n"
        "        preserveAlert: model.finish_review.locked,\n"
        "      });",
        messages_index,
    )
    assert (
        finish_hydration_index
        < retained_index
        < branch_index
        < open_index
        < locked_index
        < messages_index
        < row_errors_index
    )

    render_errors_start = controller_source.index("function renderServerErrors")
    render_errors_end = controller_source.index(
        "function lockTimingDraft", render_errors_start
    )
    render_errors = controller_source[render_errors_start:render_errors_end]
    assert "preserveAlert = false" in render_errors
    assert "if (!preserveAlert)" in render_errors
    assert "firstEditableTarget.focus()" in render_errors
    assert "reloadLink.focus();" in controller_source

    stale_listener_start = controller_source.index(
        'window.addEventListener("terminal:card-stale"'
    )
    stale_listener_end = controller_source.index(
        'window.addEventListener("terminal:shift-stale"',
        stale_listener_start,
    )
    stale_listener = controller_source[stale_listener_start:stale_listener_end]
    assert "locked: true" in stale_listener
    assert "lockedMessages: staleMessages" in stale_listener


def test_terminal_finish_confirmation_warns_only_for_mixed_saved_gross_roll_pallets(
    connection,
):
    def running_card_with_roll_pallets(
        order_number: str,
        machine_id: int,
        pallets: tuple[str | None, ...],
    ) -> int:
        card_id = release_ready_card(order_number, machine_id=machine_id, sequence=1)
        assert db.start_production_timing(card_id, card_version(card_id)).ok
        assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
        for pallet_number in pallets:
            assert db.add_roll_gross_weight(
                card_id,
                card_version(card_id),
                "50.00",
                pallet_number=pallet_number,
            ).ok
        return card_id

    all_blank_id = running_card_with_roll_pallets(
        "FINISH-PALLET-BLANK", 1, (None, None)
    )
    all_assigned_id = running_card_with_roll_pallets(
        "FINISH-PALLET-ASSIGNED", 2, ("7", "7")
    )
    mixed_singular_id = running_card_with_roll_pallets(
        "FINISH-PALLET-SINGULAR", 3, (None, "8")
    )
    mixed_plural_id = running_card_with_roll_pallets(
        "FINISH-PALLET-PLURAL", 4, (None, None, None, "9")
    )

    # An unsaved row must not count as a roll without a pallet.
    with db.connect() as db_connection:
        db_connection.execute(
            """
            INSERT INTO roll_entries (card_id, order_number, roll_number)
            VALUES (?, ?, ?)
            """,
            (mixed_singular_id, "FINISH-PALLET-SINGULAR", 3),
        )

    standard_question = "Сигурни ли сте, че искате да приключите тази поръчка?"
    expected_questions = {
        all_blank_id: standard_question,
        all_assigned_id: standard_question,
        mixed_singular_id: "В поръчката има 1 ролка без палет. Искате ли да приключите поръчката?",
        mixed_plural_id: "В поръчката има 3 ролки без палет. Искате ли да приключите поръчката?",
    }

    for card_id, expected_question in expected_questions.items():
        finish_form = form_block(
            render_terminal(card_id),
            f"/terminal/cards/{card_id}/finish",
        )
        assert f'data-finish-confirm-message="{expected_question}"' in finish_form


def test_terminal_finish_confirmation_keeps_mixed_pallet_warning_in_all_finish_contexts(
    connection,
):
    direct_completion_id = release_ready_card(
        "FINISH-CONTEXT-DIRECT",
        machine_id=1,
        sequence=1,
    )
    entering_wait_id = release_ready_card(
        "FINISH-CONTEXT-ENTER-WAIT",
        machine_id=2,
        sequence=1,
    )
    completing_wait_id = release_ready_card(
        "FINISH-CONTEXT-COMPLETE-WAIT",
        machine_id=3,
        sequence=1,
    )
    with db.connect() as db_connection:
        db_connection.execute(
            "UPDATE cards SET status = 'running' WHERE id = ?",
            (direct_completion_id,),
        )
        db_connection.execute(
            """
            UPDATE cards
            SET status = 'paused', rewinding_roll_count = 4
            WHERE id = ?
            """,
            (entering_wait_id,),
        )
        db_connection.execute(
            """
            UPDATE cards
            SET status = 'awaiting_rewinding', rewinding_roll_count = 4,
                finished_at = '2026-07-26 10:00:00'
            WHERE id = ?
            """,
            (completing_wait_id,),
        )
        for card_id, order_number in (
            (direct_completion_id, "FINISH-CONTEXT-DIRECT"),
            (entering_wait_id, "FINISH-CONTEXT-ENTER-WAIT"),
            (completing_wait_id, "FINISH-CONTEXT-COMPLETE-WAIT"),
        ):
            db_connection.executemany(
                """
                INSERT INTO roll_entries (
                    card_id, order_number, roll_number, gross_weight, pallet_number
                )
                VALUES (?, ?, ?, '50.00', ?)
                """,
                (
                    (card_id, order_number, 1, None),
                    (card_id, order_number, 2, 7),
                ),
            )

    expected = (
        "В поръчката има 1 ролка без палет. "
        "Искате ли да приключите поръчката?"
    )
    contexts = {
        "direct completion": terminal_context(direct_completion_id),
        "enter rewinding wait": terminal_context(entering_wait_id),
        "complete rewinding wait": terminal_context(completing_wait_id),
    }

    assert {
        name: context["selected_card"]["finish_confirmation_message"]
        for name, context in contexts.items()
    } == {name: expected for name in contexts}


def test_terminal_finish_confirmation_is_generic_for_no_all_blank_or_all_assigned_rolls(
    connection,
):
    card_id = release_ready_card(
        "FINISH-CONTEXT-GENERIC",
        machine_id=1,
        sequence=1,
    )
    with db.connect() as db_connection:
        db_connection.execute(
            "UPDATE cards SET status = 'paused' WHERE id = ?",
            (card_id,),
        )
    no_rolls = terminal_context(card_id)["selected_card"]["finish_confirmation_message"]

    with db.connect() as db_connection:
        db_connection.executemany(
            """
            INSERT INTO roll_entries (
                card_id, order_number, roll_number, gross_weight, pallet_number
            )
            VALUES (?, 'FINISH-CONTEXT-GENERIC', ?, '50.00', NULL)
            """,
            ((card_id, 1), (card_id, 2)),
        )
    all_blank = terminal_context(card_id)["selected_card"]["finish_confirmation_message"]

    with db.connect() as db_connection:
        db_connection.execute(
            "UPDATE roll_entries SET pallet_number = 7 WHERE card_id = ?",
            (card_id,),
        )
    all_assigned = terminal_context(card_id)["selected_card"]["finish_confirmation_message"]

    expected = "Сигурни ли сте, че искате да приключите тази поръчка?"
    assert (no_rolls, all_blank, all_assigned) == (expected, expected, expected)


def test_terminal_finish_pallet_confirmation_script_uses_selected_message_and_simple_actions(
    connection,
):
    card_id = release_ready_card("FINISH-PALLET-SCRIPT", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok

    html = render_terminal(card_id)
    script_start = html.find('const finishConfirmModal =')
    script_end = html.find("    })();", script_start)
    assert script_start != -1
    assert script_end != -1
    script = html[script_start:script_end]

    assert ">Не</button>" in html
    assert ">Да</button>" in html
    assert "Не, назад" not in html
    assert "Да, приключи" not in html
    assert 'finishConfirmModal?.querySelector("#finish-confirm-body")' in script
    assert "finishConfirmBody.textContent = form.dataset.finishConfirmMessage;" in script
    assert "finishConfirmBack?.addEventListener(\"click\", closeFinishConfirm);" in script
    assert "finishConfirmSubmitting = true;" in script
    assert "pendingFinishForm.requestSubmit();" in script
    assert "openRollCorrection" not in script
    assert "fetch(" not in script


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


def test_terminal_v8_roll_ledger_centers_headers_and_display_values(connection):
    card_id = release_ready_card("26112-CENTERED", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.50").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok

    html = render_terminal(card_id)
    row = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]
    row_html = roll_row_block(html, int(row["id"]))

    roll_head_rules = css_rules_all(html, r"(?m)^    \.roll-head > div")
    roll_body_rules = css_rules_all(html, r"(?m)^    \.roll-row > div")
    roll_list_rules = css_rules(html, r"(?m)^    \.roll-list")
    assert ".roll-head {\n      overflow-y: auto;" in html
    roll_head_scroll_rules = css_rules_all(html, r"(?m)^    \.roll-head")
    assert ".roll-row > .roll-weight-cell {" in html
    roll_weight_rules = css_rules(html, r"(?m)^    \.roll-row > \.roll-weight-cell")
    display_value_rules = css_rules(html, r"(?m)^    \.roll-display-value")

    assert any(
        "justify-content: center;" in rules and "text-align: center;" in rules
        for rules in roll_head_rules
    )
    assert any(
        "justify-content: center;" in rules and "text-align: center;" in rules
        for rules in roll_body_rules
    )
    assert "display: grid;" in roll_weight_rules
    assert "justify-content: stretch;" in roll_weight_rules
    assert "scrollbar-gutter: stable;" in roll_list_rules
    assert any(
        "overflow-y: auto;" in rules and "scrollbar-gutter: stable;" in rules
        for rules in roll_head_scroll_rules
    )
    assert "width: 100%;" in display_value_rules
    assert "justify-content: center;" in display_value_rules
    assert re.search(
        r'<div class="roll-row-error-slot field-error-slot"[^>]*hidden>',
        row_html,
    )


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

    assert 'Корекция на ролки' not in html
    assert 'aria-label="Редактирай ролка 1"' in row_html
    assert row_html.count('class="roll-edit-button"') == 1
    assert 'data-roll-display="gross"' in row_html
    assert 'data-roll-display="tare"' in row_html
    assert 'data-roll-correction-input' in row_html
    assert 'name="gross_weight"' in row_html
    assert 'name="tare_weight"' in row_html
    assert 'name="pallet_number"' in row_html
    assert f'action="/terminal/cards/{card_id}/rolls/{first_roll["id"]}"' in row_html
    assert "disabled" in row_html
    assert 'data-dirty-autosave="true"' not in row_html
    assert 'data-roll-actions-for' in html


def test_terminal_roll_row_error_reopens_only_affected_row_and_preserves_values(connection):
    card_id = release_ready_card("26231", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok

    roll = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]
    html = render_terminal(
        card_id,
        roll_result=RuleResult(
            False,
            ("Палетът трябва да бъде цяло число от 1 до 999.",),
        ),
        roll_result_target="roll_row",
        roll_result_roll_id=roll["id"],
        roll_result_values={
            "gross_weight": "51.23",
            "tare_weight": "2.34",
            "pallet_number": "9",
        },
    )

    row_html = roll_row_block(html, int(roll["id"]))
    assert 'data-roll-edit-open="true"' in row_html
    assert 'name="gross_weight"' in row_html and 'value="51.23"' in row_html
    assert 'name="tare_weight"' in row_html and 'value="2.34"' in row_html
    assert 'name="pallet_number"' in row_html and 'value="9"' in row_html
    assert "Палетът трябва да бъде цяло число от 1 до 999." in row_html
    assert f'data-roll-actions-for="{roll["id"]}"' in html
    gross_tag = re.search(r'<input[^>]+name="gross_weight"[^>]*>', row_html)
    pallet_tag = re.search(r'<input[^>]+name="pallet_number"[^>]*>', row_html)
    assert gross_tag and pallet_tag
    assert 'data-roll-error-focus="true"' not in gross_tag.group(0)
    assert 'data-roll-error-focus="true"' in pallet_tag.group(0)
    assert "openRowEdit(initialOpenRow, true);" in html


def test_terminal_roll_table_scrolls_without_obsolete_batch_editor_css(connection):
    card_id = release_ready_card("26233", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    for gross_weight in ("50.00", "51.00", "52.00"):
        assert db.add_roll_gross_weight(card_id, card_version(card_id), gross_weight).ok

    html = render_terminal(card_id)

    roll_table_rules = css_rules(html, r"(?m)^    \.roll-table")
    roll_list_rules = css_rules(html, r"(?m)^    \.roll-list")

    assert ".roll-correction-form {" not in html
    assert ".roll-delete-panel {" not in html
    assert "height: 100%;" in roll_table_rules
    assert "min-height: 0;" in roll_table_rules
    assert "overflow: auto;" in roll_list_rules


def test_terminal_row_editor_exposes_one_save_cancel_delete_action_set(connection):
    card_id = release_ready_card("26234", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok

    card = db.fetch_terminal_card_detail(card_id)
    roll = card["roll_entries"][0]
    html = render_terminal(card_id)
    assert f'Редакция на ролка №{roll["roll_number"]}' in html
    assert len(re.findall(r'<button[^>]+data-roll-row-save', html)) == 1
    assert len(re.findall(r'<button[^>]+data-roll-row-cancel', html)) == 1
    assert len(re.findall(r'<button[^>]+data-roll-row-delete', html)) == 1
    assert "const openRowEdit = (row, focusError = false) =>" in html
    assert "closeRowEdit();" in html
    assert "activeRow = row;" in html
    message_rules = css_rules(html, r"(?m)^    \.roll-correction-message")
    button_group_rules = css_rules(
        html,
        r"(?m)^    \.roll-correction-delete,\n    \.roll-correction-save,\n    \.roll-correction-cancel",
    )
    button_row_rules = css_rules(html, r"(?m)^    \.roll-correction-buttons")
    save_rules = css_rules(html, r"(?m)^    \.roll-correction-save")
    assert "font-size: 14px;" in message_rules
    assert "font-size: 13px;" in button_group_rules
    assert "padding: 0 10px;" in button_group_rules
    assert "gap: 8px;" in button_row_rules
    assert "border-color: #0b355f;" in save_rules
    assert "background: #0b355f;" in save_rules
    assert "color: #fff;" in save_rules
    assert "display: none;" in css_rules(
        html,
        r"(?m)^    \.roll-body\.roll-correction-mode \.totals",
    )
    assert "grid-template-columns: minmax(0, 1fr) auto;" in css_rules(
        html,
        r"(?m)^    \.roll-correction-actions",
    )


def test_terminal_roll_entry_controls_follow_roll_table_weight_and_pallet_order(connection):
    card_id = release_ready_card("26197", machine_id=1, sequence=1)

    html = render_terminal(card_id)
    entry_html = roll_entry_block(html)
    pallet_form = form_block(html, f"/terminal/cards/{card_id}/tare")
    add_roll_form = form_block(html, f"/terminal/cards/{card_id}/rolls")

    assert entry_html.find('class="add-roll-form"') < entry_html.find('class="tare-form')
    assert entry_html.find('class="tare-form') < entry_html.find('class="pallet-form')
    assert entry_html.find('class="field-label">Ролка</span>') < entry_html.find('class="field-label">Шпула</span>')
    assert entry_html.find('class="field-label">Шпула</span>') < entry_html.find('class="field-label">Палет</span>')
    assert entry_html.find("Палет") < entry_html.find('class="roll-add-button"')
    assert entry_html.count('class="roll-floating-field"') == 3
    entry_rules = css_rules_all(html, r"(?m)^    \.roll-entry")
    accepted_entry_rules = next(
        rules for rules in entry_rules
        if "grid-template-columns: minmax(132px, 1.35fr)" in rules
    )
    assert "grid-template-columns: minmax(132px, 1.35fr) repeat(2, minmax(92px, .72fr)) 126px;" in accepted_entry_rules
    assert "align-items: end;" in accepted_entry_rules
    assert "border: 0;" in accepted_entry_rules
    assert "background: transparent;" in accepted_entry_rules
    add_rules = css_rules_all(html, r"(?m)^    \.roll-entry > \.roll-add-button")
    assert any("width: 100%;" in rules and "height: 40px;" in rules for rules in add_rules)
    assert ">Добави</span>" in entry_html
    compact_roll_match = re.search(
        r"@media \(max-height: 820px\) \{(?P<rules>.*?)\n    \}",
        html,
        re.S,
    )
    assert compact_roll_match is not None
    assert "grid-template-columns: minmax(118px, 1.25fr) repeat(2, minmax(84px, .7fr)) 126px;" in compact_roll_match.group("rules")
    assert 'data-dirty-autosave="true"' in pallet_form
    assert 'data-dirty-autosave-group="roll-entry"' in pallet_form
    current_pallet_match = re.search(
        r'<input[^>]+name="pallet_number"[^>]*>',
        pallet_form,
    )
    assert current_pallet_match is not None
    current_pallet_tag = current_pallet_match.group(0)
    assert 'type="text"' in current_pallet_tag
    assert 'inputmode="numeric"' in current_pallet_tag
    for forbidden_attribute in ('min="', 'max="', 'step="', 'pattern="', 'maxlength="'):
        assert forbidden_attribute not in current_pallet_tag
    assert 'data-current-pallet-input="true"' in pallet_form
    assert 'data-new-roll-pallet-copy="true"' in add_roll_form
    assert 'name="pallet_number"' in add_roll_form
    assert "syncNewRollPallet" in html
    assert "currentPalletInput?.addEventListener(\"input\", syncNewRollPallet);" in html
    assert "currentPalletInput?.addEventListener(\"change\", syncNewRollPallet);" in html
    assert "newRollPalletCopy?.form?.addEventListener(\"submit\", syncNewRollPallet);" in html
    workspace_rules = css_rules_all(html, r"\.workspace")
    assert any(
        "grid-template-columns: minmax(0, 1fr) 510px;" in rules
        for rules in workspace_rules
    )
    assert any(
        "grid-template-columns: minmax(0, 1fr) 460px;" in rules
        for rules in workspace_rules
    )


def test_terminal_tare_and_pallet_render_as_one_coordinated_autosave_form(connection):
    card_id = release_ready_card("PALLET-COORDINATED-FORM", machine_id=1, sequence=1)

    html = render_terminal(card_id)
    entry_html = roll_entry_block(html)
    defaults_form = form_block(html, f"/terminal/cards/{card_id}/tare")
    add_roll_form = form_block(html, f"/terminal/cards/{card_id}/rolls")

    assert 'name="tare_weight"' in defaults_form
    assert 'name="pallet_number"' in defaults_form
    assert defaults_form.count('data-dirty-autosave="true"') == 1
    assert 'data-dirty-autosave-group="roll-entry"' in defaults_form
    assert f'action="/terminal/cards/{card_id}/pallet"' not in entry_html
    assert 'data-persist-dirty-autosave-group="roll-entry"' in add_roll_form


def test_terminal_roll_defaults_remain_editable_in_supported_card_states(connection):
    card_id = release_ready_card("ROLL-DEFAULT-STATES", machine_id=1, sequence=1)

    def assert_defaults_enabled() -> None:
        html = render_terminal(card_id)
        tare_tag = re.search(r'<input[^>]+data-current-tare-input="true"[^>]*>', html)
        pallet_tag = re.search(r'<input[^>]+data-current-pallet-input="true"[^>]*>', html)
        assert tare_tag and pallet_tag
        assert "disabled" not in tare_tag.group(0)
        assert "disabled" not in pallet_tag.group(0)

    assert_defaults_enabled()
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.25").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "20.00").ok
    assert db.pause_production_timing(card_id, card_version(card_id)).ok
    assert_defaults_enabled()
    assert db.update_rewinding_roll_count(card_id, card_version(card_id), 1).ok
    assert db.finish_card(card_id, card_version(card_id)).ok
    assert_defaults_enabled()


def test_terminal_active_lifecycle_slots_are_equal_and_waiting_has_only_finish(connection):
    card_id = release_ready_card("LIFECYCLE-SLOTS", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok

    running_html = render_terminal(card_id)
    running_actions = re.search(r'<div class="actions">(?P<body>.*?)</div>\s*</div>', running_html, re.S)
    assert running_actions is not None
    running_body = running_actions.group("body")
    assert running_body.count('data-lifecycle-slot') == 3
    assert len(re.findall(r'data-lifecycle-slot=', running_html)) == 3
    assert '<div class="roll-change-controls"' in running_body
    assert (
        running_body.index('data-roll-change-open')
        < running_body.index('data-roll-change-advance')
        < running_body.index('data-lifecycle-slot="start"')
        < running_body.index('data-lifecycle-slot="pause"')
        < running_body.index('data-lifecycle-slot="finish"')
    )
    timer_rules = css_rules(running_html, r"(?m)^    \.roll-change-controls")
    assert "margin-right: 12px;" in timer_rules
    assert "padding-right: 12px;" in timer_rules
    assert "border-right:" not in timer_rules
    assert "border-left:" not in timer_rules
    assert "transform: translateX(-44px);" in timer_rules
    action_area_rules = css_rules(running_html, r"(?m)^    \.action-area")
    assert "padding-right: 44px;" not in action_area_rules
    lifecycle_rules = css_rules(running_html, r"(?m)^    \.actions > \.action-button,\s*\.actions > form")
    assert "width: 150px;" in lifecycle_rules
    assert "flex: 0 0 150px;" in lifecycle_rules

    assert db.update_rewinding_roll_count(card_id, card_version(card_id), 3).ok
    assert db.finish_card(card_id, card_version(card_id)).ok
    waiting_html = render_terminal(card_id)
    waiting_actions = re.search(r'<div class="actions">(?P<body>.*?)</div>\s*</div>', waiting_html, re.S)
    assert waiting_actions is not None
    waiting_body = waiting_actions.group("body")
    assert "Старт" not in waiting_body
    assert "Пауза" not in waiting_body
    assert f'action="/terminal/cards/{card_id}/finish"' in waiting_body
    assert "Приключи" in waiting_body
    assert "disabled" not in waiting_body
    assert 'class="menu"' not in waiting_html


def test_terminal_roll_ledger_renders_blank_pallet_and_editable_pallet_correction(
    connection,
):
    card_id = release_ready_card("PALLET-TERMINAL-RENDER", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.25").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.35").ok
    roll = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]

    html = render_terminal(card_id)
    ledger_head = html.split('<div class="roll-head">', 1)[1].split(
        '<div class="roll-list"', 1
    )[0]
    row_html = roll_row_block(html, int(roll["id"]))

    assert [ledger_head.find(label) for label in ("№", "Бруто", "Шпула", "Нето", "Палет")] == sorted(
        ledger_head.find(label)
        for label in ("№", "Бруто", "Шпула", "Нето", "Палет")
    )
    assert "Бруто кг" not in ledger_head
    assert "Шпула кг" not in ledger_head
    assert "Нето кг" not in ledger_head
    assert '<div class="roll-edit-heading" aria-label="Редакция"></div>' in ledger_head
    assert 'data-roll-display="pallet">-</span>' in row_html
    assert 'data-roll-display="gross">60.4</span>' in row_html
    assert 'data-roll-display="tare">1.3</span>' in row_html
    assert 'data-roll-display="net">59.1</span>' in row_html
    assert re.search(r'name="gross_weight"[^>]+value="60\.35"', row_html)
    assert re.search(r'name="tare_weight"[^>]+value="1\.25"', row_html)
    pallet_input_match = re.search(
        r'<input[^>]+name="pallet_number"[^>]*>',
        row_html,
    )
    assert pallet_input_match is not None
    pallet_input_tag = pallet_input_match.group(0)
    assert 'type="text"' in pallet_input_tag
    assert 'inputmode="numeric"' in pallet_input_tag
    for forbidden_attribute in ('min="', 'max="', 'step="', 'pattern="', 'maxlength="'):
        assert forbidden_attribute not in pallet_input_tag
    assert "grid-template-columns: repeat(5, minmax(0, 1fr)) 38px;" in html


def test_terminal_pallet_errors_render_under_current_pallet_control(connection):
    card_id = release_ready_card("PALLET-TERMINAL-FEEDBACK", machine_id=1, sequence=1)

    html = render_terminal(
        card_id,
        roll_result=RuleResult(False, ("pallet validation failure",)),
        roll_result_target="pallet",
    )

    pallet_feedback = data_block(html, "data-feedback-target", "pallet")
    assert "pallet validation failure" in pallet_feedback


def test_terminal_new_roll_autofocus_marker_renders_only_for_running_card(connection):
    running_id = release_ready_card("26301", machine_id=1, sequence=1)
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    running_html = render_terminal(running_id)
    running_input = new_roll_input_tag(running_html)
    assert 'data-new-roll-autofocus="true"' in running_input
    assert "disabled" not in running_input

    pending_id = release_ready_card("26302", machine_id=2, sequence=1)
    pending_input = new_roll_input_tag(render_terminal(pending_id))
    assert 'data-new-roll-autofocus="true"' not in pending_input
    assert "disabled" in pending_input

    paused_id = release_ready_card("26303", machine_id=3, sequence=1)
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok
    paused_input = new_roll_input_tag(render_terminal(paused_id))
    assert 'data-new-roll-autofocus="true"' not in paused_input
    assert "disabled" in paused_input

    completed_id = release_ready_card("26304", machine_id=4, sequence=1)
    complete_card(completed_id)
    completed_input = new_roll_input_tag(render_terminal(completed_id))
    assert 'data-new-roll-autofocus="true"' not in completed_input
    assert "disabled" not in completed_input


def test_terminal_new_roll_autofocus_marker_is_absent_without_selected_card(connection):
    html = render_terminal(machine_id=4)

    assert 'data-new-roll-autofocus="true"' not in html
    assert "Няма активна поръчка за Машина 4." in html


def test_terminal_new_roll_autofocus_validation_error_keeps_marker(connection):
    card_id = release_ready_card("26305", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok

    html = render_terminal(
        card_id,
        roll_result=RuleResult(False, ("new roll failure",)),
        roll_result_target="new_roll",
    )

    new_roll_block = data_block(html, "data-feedback-target", "new_roll")
    assert "new roll failure" in new_roll_block
    assert 'id="terminal-refresh-alert"' not in html
    assert 'data-new-roll-autofocus="true"' in new_roll_input_tag(html)


def test_terminal_new_roll_autofocus_script_guards_reload_and_open_row_editor(connection):
    card_id = release_ready_card("26306", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok

    html = render_terminal(card_id)

    assert "focusNewRollInput" in html
    assert "input[data-new-roll-autofocus='true']" in html
    assert 'document.getElementById("terminal-refresh-alert")' in html
    assert ".roll-row[data-roll-edit-open='true']" in html
    assert "newRollInput.focus();" in html

    roll = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]
    correction_html = render_terminal(
        card_id,
        roll_result=RuleResult(False, ("correction failure",)),
        roll_result_target="roll_row",
        roll_result_roll_id=roll["id"],
    )
    assert 'data-roll-edit-open="true"' in correction_html
    assert 'data-new-roll-autofocus="true"' in new_roll_input_tag(correction_html)


def test_terminal_coordinated_defaults_and_row_forms_use_dirty_autosave_without_new_roll_autosave(connection):
    card_id = release_ready_card("26198", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    roll = card["roll_entries"][0]

    html = render_terminal(card_id)
    tare_form = form_block(html, f"/terminal/cards/{card_id}/tare")
    add_roll_form = form_block(html, f"/terminal/cards/{card_id}/rolls")
    row_form = form_block(html, f"/terminal/cards/{card_id}/rolls/{roll['id']}")
    row_html = roll_row_block(html, roll["id"])

    assert 'data-dirty-autosave="true"' in tare_form
    assert tare_form.count('data-dirty-autosave="true"') == 1
    assert 'data-dirty-autosave="true"' not in add_roll_form
    assert 'data-dirty-autosave="true"' not in row_form
    assert 'data-dirty-autosave="true"' not in row_html
    assert 'data-dirty-autosave-group="roll-entry"' in tare_form
    assert 'data-dirty-autosave-group="roll-entry"' not in add_roll_form
    assert 'data-dirty-autosave-group="roll-entry"' not in row_form
    assert 'data-new-roll-tare-copy="true"' in add_roll_form
    assert 'data-new-roll-pallet-copy="true"' in add_roll_form
    assert 'data-persist-dirty-autosave-group="roll-entry"' in add_roll_form
    assert 'data-current-tare-input="true"' in tare_form
    assert 'data-current-pallet-input="true"' in tare_form
    assert 'form[data-recipe-autosave="true"], form[data-dirty-autosave="true"]' in html
    assert "syncNewRollTare" in html
    assert "syncNewRollPallet" in html
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

    assert "setCorrectionControlLock" in html
    assert "if (!row || row === activeRow) return;" in html
    assert "data-roll-edit-open" in html
    assert "data-roll-row-cancel" in html
    assert "data-roll-correction-input" in html
    assert "correctionBlockedControls" in html
    assert 'class="menu"' not in html
    assert ".roll-add-button" in html
    assert ".tare-form input" in html
    assert ".pallet-form input" in html
    assert ".recipe-table input" in html
    assert "#queue-open" in html
    assert "#history-open" in html
    assert "[data-rewinding-open], [data-roll-change-open], [data-roll-change-advance]" in html
    assert "initialCorrectionValues" in html
    assert "hasDirtyRollCorrections" in html
    assert "skipCorrectionBeforeUnload" in html


def test_terminal_roll_correction_locks_and_closes_timing_menu(connection):
    card_id = release_ready_card("26232-timing-lock", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok
    html = render_terminal(card_id)
    controller = Path(
        "app/static/js/timing_interval_editor.mjs"
    ).read_text(encoding="utf-8")

    blocked_start = html.index("const correctionBlockedControls")
    blocked_end = html.index("const correctionBlockedLinks", blocked_start)
    assert "[data-timing-menu-button]" in html[blocked_start:blocked_end]

    lock_start = html.index("const setCorrectionControlLock = (open) => {")
    lock_end = html.index("const closeRollDeleteModal", lock_start)
    lock_handler = html[lock_start:lock_end]
    coordination = (
        'document.dispatchEvent(new CustomEvent("terminal:roll-correction-open"));'
    )
    assert coordination in lock_handler
    assert lock_handler.index(coordination) < lock_handler.index(
        "correctionBlockedControls.forEach"
    )

    assert (
        'document.addEventListener("terminal:roll-correction-open", () => {'
        in controller
    )
    assert "closeMenu({ restoreFocus: menuPanel.contains(document.activeElement) });" in controller
    assert "if (menuButton.disabled)" in controller


def test_terminal_roll_correction_save_suppresses_dirty_exit_warning(connection):
    card_id = release_ready_card("26235", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok

    html = render_terminal(card_id)

    submit_handler_start = html.index('row.addEventListener("submit", (event) => {')
    submit_handler_end = html.index("rollActionPanels.forEach", submit_handler_start)
    submit_handler = html[submit_handler_start:submit_handler_end]
    assert 'document.getElementById("terminal-refresh-alert")' in submit_handler
    assert "event.preventDefault();" in submit_handler
    assert "skipCorrectionBeforeUnload = true;" in submit_handler


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


def test_terminal_v8_roll_defaults_notice_uses_generic_saved_message(connection):
    card_id = release_ready_card("26191-defaults", machine_id=1, sequence=1)

    html = render_terminal(card_id, terminal_notice="roll_defaults_saved")

    assert html.count('class="terminal-toast"') == 1
    assert "Данните са записани." in html
    assert "Шпула е записана." not in html


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
    assert 'class="field-label">Шпула</span>' in html
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
    assert 'class="field-label">Ролка</span>' in html
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


def test_terminal_stale_roll_row_requires_reload_before_another_row_write(connection):
    card_id = release_ready_card("STALE-ROLL-ROW", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok
    stale_card = db.fetch_terminal_card_detail(card_id)
    roll = stale_card["roll_entries"][0]
    assert db.update_tare_weight(card_id, stale_card["version"], "1.25").ok

    response = asyncio.run(
        save_roll_weight(
            make_test_request(f"/terminal/cards/{card_id}/rolls/{roll['id']}"),
            card_id,
            roll["id"],
            str(stale_card["version"]),
            "61.23",
            "1.21",
            "8",
        )
    )
    html = response.body.decode("utf-8")

    row_html = roll_row_block(html, int(roll["id"]))
    unchanged_roll = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]
    assert response.status_code == 200
    assert (
        unchanged_roll["gross_weight"],
        unchanged_roll["tare_weight"],
        unchanged_roll["pallet_number"],
    ) == (60, 1.2, None)
    assert 'id="terminal-refresh-alert"' in html
    assert 'data-roll-edit-open="true"' in row_html
    assert 'value="61.23"' in row_html
    assert re.search(
        rf'name="loaded_version" value="{stale_card["version"]}"',
        row_html,
    )
    actions = re.search(
        rf'<div class="roll-correction-actions" data-roll-actions-for="{roll["id"]}".*?</div>\s*</div>',
        html,
        re.S,
    )
    assert actions is not None
    assert len(re.findall(r'<button[^>]+disabled', actions.group(0))) == 3
    assert 'event.target.closest?.("#terminal-refresh-alert-button")' in html
    assert "skipCorrectionBeforeUnload = true;" in html
    assert 'activeRow && !document.getElementById("terminal-refresh-alert")' in html
    assert 'if (document.getElementById("terminal-refresh-alert")) {' in html
    assert "event.preventDefault();" in html


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


def test_terminal_roll_weight_route_updates_one_row_gross_tare_and_pallet_atomically(connection):
    card_id = release_ready_card("26176", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok
    assert db.add_roll_gross_weight(
        card_id,
        card_version(card_id),
        "60.00",
        pallet_number="4",
    ).ok
    card = db.fetch_terminal_card_detail(card_id)
    roll = card["roll_entries"][0]
    untouched_roll = card["roll_entries"][1]

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls/{roll['id']}",
            {
                "loaded_version": str(card["version"]),
                "gross_weight": "51.23",
                "tare_weight": "3.21",
                "pallet_number": "7",
            },
        )
    )

    updated = db.fetch_terminal_card_detail(card_id)
    updated_roll = updated["roll_entries"][0]
    assert status_code == 303
    assert headers["location"] == (
        f"/terminal/cards/{card_id}?notice=roll_updated"
    )
    assert (
        updated_roll["gross_weight"],
        updated_roll["tare_weight"],
        updated_roll["pallet_number"],
        updated_roll["net_weight"],
    ) == (51.23, 3.21, 7, 48.02)
    assert updated["roll_entries"][1] == untouched_roll
    assert updated["tare_weight"] == card["tare_weight"] == 2
    assert updated["current_pallet_number"] == card["current_pallet_number"] == 4
    assert updated["version"] == card["version"] + 1


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


def test_terminal_stale_roll_delete_reopens_locked_row_and_requires_reload(connection):
    card_id = release_ready_card("STALE-ROLL-DELETE", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok
    stale_card = db.fetch_terminal_card_detail(card_id)
    roll = stale_card["roll_entries"][0]
    assert db.update_tare_weight(card_id, stale_card["version"], "1.25").ok

    response = asyncio.run(
        delete_roll_weight(
            make_test_request(f"/terminal/cards/{card_id}/rolls/{roll['id']}/delete"),
            card_id,
            roll["id"],
            str(stale_card["version"]),
            str(roll["roll_number"]),
        )
    )
    html = response.body.decode("utf-8")
    row_html = roll_row_block(html, int(roll["id"]))

    assert response.status_code == 200
    assert db.fetch_terminal_card_detail(card_id)["roll_entries"][0]["id"] == roll["id"]
    assert 'id="terminal-refresh-alert"' in html
    assert 'data-roll-edit-open="true"' in row_html
    assert re.search(
        rf'<input type="hidden" name="loaded_version" value="{stale_card["version"]}">',
        row_html,
    )
    actions = re.search(
        rf'<div class="roll-correction-actions" data-roll-actions-for="{roll["id"]}".*?</div>\s*</div>',
        html,
        re.S,
    )
    assert actions is not None
    assert len(re.findall(r'<button[^>]+disabled', actions.group(0))) == 3


def test_terminal_v8_roll_delete_confirmation_names_selected_roll(connection):
    card_id = release_ready_card("26172", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok

    html = render_terminal(card_id)
    roll_id = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]["id"]
    row_html = roll_row_block(html, roll_id)

    assert 'data-roll-edit-open' in row_html
    assert f'data-roll-actions-for="{roll_id}"' in html
    assert f'data-roll-number="1"' in html
    assert f'action="/terminal/cards/{card_id}/rolls/{roll_id}/delete"' in html
    assert "Сигурни ли сте, че искате да изтриете ролка №1?" in html
    assert 'name="confirm_roll_number"' in html
    assert "Потвърдете номера на ролката" in html


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
    middle_modal = re.search(
        rf'<div class="finish-confirm-modal roll-delete-modal" id="roll-delete-modal-{middle_roll["id"]}"(?P<tag>[^>]*)>',
        page,
    )
    first_modal = re.search(
        rf'<div class="finish-confirm-modal roll-delete-modal" id="roll-delete-modal-{first_roll["id"]}"(?P<tag>[^>]*)>',
        page,
    )
    assert middle_modal and first_modal
    assert re.search(r"\shidden(?:\s|$)", middle_modal.group("tag")) is None
    assert re.search(r"\shidden(?:\s|$)", first_modal.group("tag"))
    assert f'ролка №{middle_roll["roll_number"]}?' in page
    assert f'action="/terminal/cards/{card_id}/rolls/{middle_roll["id"]}/delete"' in page


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
    with db.connect() as setup_connection:
        setup_connection.execute(
            """
            UPDATE production_time_segments
            SET started_at = '2026-01-15 08:00:37'
            WHERE card_id = ?
            """,
            (card_id,),
        )
        setup_connection.execute(
            """
            UPDATE cards
            SET first_started_at = '2026-01-15 08:00:37'
            WHERE id = ?
            """,
            (card_id,),
        )
    loaded_version = card_version(card_id)
    review_response = asyncio.run(
        route_endpoint("/terminal/cards/{card_id}/finish-review")(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)

    response = asyncio.run(
        finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=json.dumps(review_payload["preview"]["draft"]),
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


def test_terminal_roll_correction_parser_includes_pallet_values():
    updates = terminal_roll_corrections_from_form(
        FormData(
            [
                ("gross_weight__17", "55.50"),
                ("pallet_number__17", "6"),
                ("pallet_number__18", "7"),
            ]
        )
    )

    assert updates == {
        17: {"gross_weight": "55.50", "pallet_number": "6"},
        18: {"pallet_number": "7"},
    }


def test_terminal_current_pallet_route_trims_saves_and_uses_prg(connection):
    card_id = release_ready_card("PALLET-TERMINAL-SAVE", machine_id=1, sequence=1)
    loaded_version = card_version(card_id)

    response = asyncio.run(
        save_current_pallet_number(
            make_test_request(f"/terminal/cards/{card_id}/pallet"),
            card_id,
            str(loaded_version),
            " 7 ",
        )
    )
    saved = db.fetch_terminal_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=pallet_saved"
    )
    assert saved["current_pallet_number"] == 7


def test_terminal_current_pallet_route_clears_existing_value(connection):
    card_id = release_ready_card("PALLET-TERMINAL-CLEAR", machine_id=1, sequence=1)
    assert db.update_current_pallet_number(card_id, card_version(card_id), "4").ok

    response = asyncio.run(
        save_current_pallet_number(
            make_test_request(f"/terminal/cards/{card_id}/pallet"),
            card_id,
            str(card_version(card_id)),
            " ",
        )
    )

    assert response.status_code == 303
    assert db.fetch_terminal_card_detail(card_id)["current_pallet_number"] is None


def test_terminal_current_pallet_route_targets_validation_error_to_pallet(connection):
    card_id = release_ready_card("PALLET-TERMINAL-ERROR", machine_id=1, sequence=1)

    response = asyncio.run(
        save_current_pallet_number(
            make_test_request(f"/terminal/cards/{card_id}/pallet"),
            card_id,
            str(card_version(card_id)),
            "1000",
        )
    )

    assert response.status_code == 200
    assert response.context["terminal_feedback"]["errors"]["pallet"] == (
        "Палетът трябва да бъде цяло число от 1 до 999.",
    )


def test_terminal_add_roll_saves_submitted_pallet_with_roll_atomically(connection):
    card_id = release_ready_card("PALLET-TERMINAL-ROLL", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok

    response = asyncio.run(
        add_roll_weight(
            make_test_request(f"/terminal/cards/{card_id}/rolls"),
            card_id,
            str(card_version(card_id)),
            "60.00",
            None,
            " 8 ",
        )
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert response.status_code == 303
    assert card["current_pallet_number"] == 8
    assert card["roll_entries"][-1]["pallet_number"] == 8


def test_terminal_tare_route_saves_dirty_tare_and_pallet_atomically(connection):
    card_id = release_ready_card("PALLET-TERMINAL-DEFAULTS", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    loaded_version = card_version(card_id)

    response = asyncio.run(
        save_tare_weight(
            make_test_request(f"/terminal/cards/{card_id}/tare"),
            card_id,
            str(loaded_version),
            "2.50",
            "9",
        )
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=roll_defaults_saved"
    )
    assert card["tare_weight"] == 2.5
    assert card["current_pallet_number"] == 9
    assert card["version"] == loaded_version + 1


def test_terminal_defaults_http_route_clears_explicitly_blank_pallet(connection):
    card_id = release_ready_card("PALLET-HTTP-DEFAULT-CLEAR", machine_id=1, sequence=1)
    assert db.update_roll_defaults(
        card_id,
        card_version(card_id),
        tare_weight="1.25",
        pallet_number="7",
        require_active_shift=True,
    ).ok
    loaded_version = card_version(card_id)

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/tare",
            {
                "loaded_version": str(loaded_version),
                "tare_weight": "1.25",
                "pallet_number": "",
            },
        )
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert status_code == 303
    assert headers["location"] == (
        f"/terminal/cards/{card_id}?notice=roll_defaults_saved"
    )
    assert card["tare_weight"] == 1.25
    assert card["current_pallet_number"] is None
    assert card["version"] == loaded_version + 1


def test_terminal_defaults_http_route_preserves_omitted_tare_when_clearing_pallet(
    connection,
):
    card_id = release_ready_card("PALLET-HTTP-DEFAULT-OMIT", machine_id=1, sequence=1)
    assert db.update_roll_defaults(
        card_id,
        card_version(card_id),
        tare_weight="1.25",
        pallet_number="7",
        require_active_shift=True,
    ).ok
    loaded_version = card_version(card_id)

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/tare",
            {
                "loaded_version": str(loaded_version),
                "pallet_number": "",
            },
        )
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert status_code == 303
    assert headers["location"] == (
        f"/terminal/cards/{card_id}?notice=roll_defaults_saved"
    )
    assert card["tare_weight"] == 1.25
    assert card["current_pallet_number"] is None
    assert card["version"] == loaded_version + 1


def test_terminal_add_roll_http_route_clears_blank_pallet_atomically(connection):
    card_id = release_ready_card("PALLET-HTTP-ROLL-CLEAR", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_roll_defaults(
        card_id,
        card_version(card_id),
        tare_weight="1.25",
        pallet_number="7",
        require_active_shift=True,
    ).ok
    loaded_version = card_version(card_id)

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls",
            {
                "loaded_version": str(loaded_version),
                "gross_weight": "60.00",
                "tare_weight": "1.25",
                "pallet_number": "",
            },
        )
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert status_code == 303
    assert headers["location"] == f"/terminal/cards/{card_id}?notice=roll_saved"
    assert card["tare_weight"] == 1.25
    assert card["current_pallet_number"] is None
    assert card["roll_entries"][0]["pallet_number"] is None
    assert card["roll_entries"][0]["tare_weight"] == 1.25
    assert card["roll_entries"][0]["net_weight"] == 58.75
    assert card["version"] == loaded_version + 1


def test_terminal_add_roll_http_route_preserves_omitted_defaults(connection):
    card_id = release_ready_card("ROLL-HTTP-DEFAULTS-OMIT", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_roll_defaults(
        card_id,
        card_version(card_id),
        tare_weight="1.25",
        pallet_number="7",
        require_active_shift=True,
    ).ok
    loaded_version = card_version(card_id)

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls",
            {
                "loaded_version": str(loaded_version),
                "gross_weight": "60.00",
            },
        )
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert status_code == 303
    assert headers["location"] == f"/terminal/cards/{card_id}?notice=roll_saved"
    assert card["tare_weight"] == 1.25
    assert card["current_pallet_number"] == 7
    assert card["roll_entries"][0]["tare_weight"] == 1.25
    assert card["roll_entries"][0]["pallet_number"] == 7
    assert card["roll_entries"][0]["net_weight"] == 58.75
    assert card["version"] == loaded_version + 1


def test_terminal_add_roll_http_route_does_not_reuse_explicitly_blank_tare(connection):
    card_id = release_ready_card("TARE-HTTP-ROLL-CLEAR", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_roll_defaults(
        card_id,
        card_version(card_id),
        tare_weight="1.25",
        pallet_number="7",
        require_active_shift=True,
    ).ok
    before = db.fetch_terminal_card_detail(card_id)

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls",
            {
                "loaded_version": str(before["version"]),
                "gross_weight": "60.00",
                "tare_weight": "",
                "pallet_number": "",
            },
        )
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert status_code == 200
    assert "location" not in headers
    assert card["tare_weight"] == before["tare_weight"] == 1.25
    assert card["current_pallet_number"] == before["current_pallet_number"] == 7
    assert card["roll_entries"] == []
    assert card["version"] == before["version"]


def test_terminal_pencil_http_route_clears_only_selected_roll_defaults(connection):
    card_id = release_ready_card("PALLET-HTTP-PENCIL-CLEAR", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_roll_defaults(
        card_id,
        card_version(card_id),
        tare_weight="1.25",
        pallet_number="7",
        require_active_shift=True,
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        card_version(card_id),
        "60.00",
        require_active_shift=True,
    ).ok
    before = db.fetch_terminal_card_detail(card_id)
    roll = before["roll_entries"][0]

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls/{roll['id']}",
            {
                "loaded_version": str(before["version"]),
                "gross_weight": "60.00",
                "tare_weight": "",
                "pallet_number": "",
            },
        )
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert status_code == 303
    assert headers["location"] == (
        f"/terminal/cards/{card_id}?notice=roll_updated"
    )
    assert card["roll_entries"][0]["tare_weight"] is None
    assert card["roll_entries"][0]["net_weight"] is None
    assert card["roll_entries"][0]["pallet_number"] is None
    assert card["tare_weight"] == 1.25
    assert card["current_pallet_number"] == 7
    assert card["version"] == before["version"] + 1


@pytest.mark.parametrize(
    ("submitted_pallet", "expected_pallet"),
    (("", None), ("9", 9)),
)
def test_terminal_pencil_http_route_updates_pallet_when_tare_is_omitted(
    connection,
    submitted_pallet,
    expected_pallet,
):
    card_id = release_ready_card(
        f"PALLET-HTTP-PENCIL-OMIT-{submitted_pallet or 'BLANK'}",
        machine_id=1,
        sequence=1,
    )
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_roll_defaults(
        card_id,
        card_version(card_id),
        tare_weight="1.25",
        pallet_number="7",
        require_active_shift=True,
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        card_version(card_id),
        "60.00",
        require_active_shift=True,
    ).ok
    before = db.fetch_terminal_card_detail(card_id)
    roll = before["roll_entries"][0]

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls/{roll['id']}",
            {
                "loaded_version": str(before["version"]),
                "gross_weight": "61.00",
                "pallet_number": submitted_pallet,
            },
        )
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert status_code == 303
    assert headers["location"] == (
        f"/terminal/cards/{card_id}?notice=roll_updated"
    )
    assert card["roll_entries"][0]["gross_weight"] == 61
    assert card["roll_entries"][0]["tare_weight"] == 1.25
    assert card["roll_entries"][0]["pallet_number"] == expected_pallet
    assert card["roll_entries"][0]["net_weight"] == 59.75
    assert card["tare_weight"] == 1.25
    assert card["current_pallet_number"] == 7
    assert card["version"] == before["version"] + 1


@pytest.mark.parametrize(
    "invalid_pallet",
    ("1000", "15+1", pytest.param("9" * 5000, id="5000-digits")),
)
def test_terminal_tare_route_targets_invalid_pallet_and_saves_neither_default(
    connection,
    invalid_pallet,
):
    card_id = release_ready_card("PALLET-TERMINAL-DEFAULTS-ERROR", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.25").ok
    assert db.update_current_pallet_number(card_id, card_version(card_id), "7").ok
    before = db.fetch_terminal_card_detail(card_id)

    response = asyncio.run(
        save_tare_weight(
            make_test_request(f"/terminal/cards/{card_id}/tare"),
            card_id,
            str(before["version"]),
            "2.50",
            invalid_pallet,
        )
    )
    after = db.fetch_terminal_card_detail(card_id)

    assert response.status_code == 200
    assert response.context["terminal_feedback"]["errors"]["pallet"] == (
        "Палетът трябва да бъде цяло число от 1 до 999.",
    )
    assert after["tare_weight"] == before["tare_weight"] == 1.25
    assert after["current_pallet_number"] == before["current_pallet_number"] == 7
    assert after["version"] == before["version"]


def test_terminal_tare_route_blocks_stale_coordinated_defaults_without_partial_write(connection):
    card_id = release_ready_card("PALLET-TERMINAL-DEFAULTS-STALE", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.25").ok
    current = db.fetch_terminal_card_detail(card_id)

    response = asyncio.run(
        save_tare_weight(
            make_test_request(f"/terminal/cards/{card_id}/tare"),
            card_id,
            str(loaded_version),
            "2.50",
            "9",
        )
    )
    after = db.fetch_terminal_card_detail(card_id)

    assert response.status_code == 200
    assert response.context["terminal_feedback"]["refresh_required"] is True
    assert after["tare_weight"] == current["tare_weight"] == 1.25
    assert after["current_pallet_number"] is None
    assert after["version"] == current["version"]


@pytest.mark.parametrize("invalid_pallet", ("1000", "15+1"))
def test_terminal_add_roll_targets_invalid_pallet_to_current_pallet_control(
    connection,
    invalid_pallet,
):
    card_id = release_ready_card("PALLET-TERMINAL-ROLL-ERROR", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok

    response = asyncio.run(
        add_roll_weight(
            make_test_request(f"/terminal/cards/{card_id}/rolls"),
            card_id,
            str(card_version(card_id)),
            "60.00",
            None,
            invalid_pallet,
        )
    )

    assert response.status_code == 200
    assert response.context["terminal_feedback"]["errors"]["pallet"] == (
        "Палетът трябва да бъде цяло число от 1 до 999.",
    )
    assert db.fetch_terminal_card_detail(card_id)["roll_entries"] == []


def test_terminal_roll_corrections_route_saves_per_row_pallet(connection):
    card_id = release_ready_card("PALLET-TERMINAL-CORRECTION", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok
    roll_id = int(db.fetch_terminal_card_detail(card_id)["roll_entries"][0]["id"])

    response = asyncio.run(
        save_terminal_roll_corrections(
            TerminalFormRequest(
                f"/terminal/cards/{card_id}/rolls/corrections",
                FormData(
                    [
                        ("loaded_version", str(card_version(card_id))),
                        (f"pallet_number__{roll_id}", "3"),
                    ]
                )
            ),
            card_id,
        )
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=rolls_saved"
    )
    assert db.fetch_terminal_card_detail(card_id)["roll_entries"][0]["pallet_number"] == 3


def test_terminal_roll_corrections_route_rejects_malformed_pallet_atomically(connection):
    card_id = release_ready_card("PALLET-TERMINAL-CORRECTION-INVALID", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(
        card_id,
        card_version(card_id),
        "60.00",
        pallet_number="3",
    ).ok
    before = db.fetch_terminal_card_detail(card_id)
    roll_id = int(before["roll_entries"][0]["id"])

    response = asyncio.run(
        save_terminal_roll_corrections(
            TerminalFormRequest(
                f"/terminal/cards/{card_id}/rolls/corrections",
                FormData(
                    [
                        ("loaded_version", str(before["version"])),
                        (f"pallet_number__{roll_id}", "15+1"),
                        (f"gross_weight__{roll_id}", "75.00"),
                    ]
                ),
            ),
            card_id,
        )
    )
    after = db.fetch_terminal_card_detail(card_id)

    assert response.status_code == 200
    assert "Палетът трябва да бъде цяло число от 1 до 999." in response.body.decode("utf-8")
    assert after["version"] == before["version"]
    assert after["current_pallet_number"] == before["current_pallet_number"]
    assert [
        (roll["pallet_number"], roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
        for roll in after["roll_entries"]
    ] == [
        (roll["pallet_number"], roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
        for roll in before["roll_entries"]
    ]


def test_terminal_roll_corrections_route_reports_malformed_pallet_roll_id(connection):
    card_id = release_ready_card("PALLET-TERMINAL-MALFORMED", machine_id=1, sequence=1)

    response = asyncio.run(
        save_terminal_roll_corrections(
            TerminalFormRequest(
                f"/terminal/cards/{card_id}/rolls/corrections",
                FormData(
                    [
                        ("loaded_version", str(card_version(card_id))),
                        ("pallet_number__bad-id", "3"),
                    ]
                )
            ),
            card_id,
        )
    )

    assert response.status_code == 200
    assert "Формата съдържа невалидна ролка." in response.body.decode("utf-8")


def test_terminal_current_pallet_route_blocks_stale_post(connection):
    card_id = release_ready_card("PALLET-TERMINAL-STALE", machine_id=1, sequence=1)
    loaded_version = card_version(card_id)
    assert db.update_current_pallet_number(card_id, loaded_version, "2").ok

    response = asyncio.run(
        save_current_pallet_number(
            make_test_request(f"/terminal/cards/{card_id}/pallet"),
            card_id,
            str(loaded_version),
            "3",
        )
    )

    assert response.status_code == 200
    assert db.fetch_terminal_card_detail(card_id)["current_pallet_number"] == 2
    assert response.context["terminal_feedback"]["refresh_required"] is True


@pytest.mark.parametrize("terminal_state", ("cancelled", "archived"))
def test_terminal_current_pallet_route_blocks_nonterminal_cards(connection, terminal_state):
    card_id = release_ready_card(f"PALLET-TERMINAL-{terminal_state}", machine_id=1, sequence=1)
    if terminal_state == "cancelled":
        assert db.cancel_card(card_id, card_version(card_id)).ok
    else:
        complete_card(card_id)
        assert db.archive_completed_card(card_id, card_version(card_id)).ok
    card = db.fetch_admin_card_detail(card_id)

    response = asyncio.run(
        save_current_pallet_number(
            make_test_request(f"/terminal/cards/{card_id}/pallet"),
            card_id,
            str(card["version"]),
            "3",
        )
    )

    assert response.status_code == 200
    assert db.fetch_admin_card_detail(card_id)["current_pallet_number"] is None
    assert response.context["terminal_feedback"]["refresh_required"] is True


def test_terminal_current_pallet_route_requires_active_shift(connection):
    card_id = release_ready_card("PALLET-TERMINAL-NO-SHIFT", machine_id=1, sequence=1)
    end_active_test_shift()

    response = asyncio.run(
        save_current_pallet_number(
            make_test_request(f"/terminal/cards/{card_id}/pallet"),
            card_id,
            str(card_version(card_id)),
            "3",
        )
    )

    assert response.status_code == 200
    assert db.fetch_terminal_card_detail(card_id)["current_pallet_number"] is None
    assert response.context["terminal_feedback"]["errors"]["topbar"] == (
        "Отворете смяна, преди да продължите.",
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


def test_terminal_tokenless_nonwaiting_finish_requires_reload_without_redirect(connection):
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
    assert response.context["workflow_result"].messages == (STALE_CARD_MESSAGE,)
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


def test_terminal_header_has_centered_global_actions_and_shift_identity(connection):
    active_shift = db.fetch_active_shift()
    assert active_shift is not None

    html = render_terminal()
    header = re.search(r'<header class="terminal-header".*?</header>', html, re.S)

    assert header is not None
    header_html = header.group(0)
    assert "/static/images/kolev-logo.png" in header_html
    assert header_html.count('class="terminal-header-action') == 4
    assert "/static/images/terminal-ui/waiting-orders.svg" in header_html
    assert "/static/images/terminal-ui/awaiting-rewinding.png" in header_html
    assert "/static/images/terminal-ui/produced-orders.svg" in header_html
    assert "/static/images/terminal-ui/worker_3537.webp" in header_html
    assert Path("app/static/images/terminal-ui/worker_3537.webp").is_file()
    assert ">Чакащи поръчки<" in header_html
    assert "Изчакващи пренавиване" in header_html
    assert ">Произведени поръчки<" in header_html
    assert 'id="shift-open"' in header_html
    assert "shift-status-dot" not in header_html
    assert f'>Смяна {active_shift["shift_number"]}<' in header_html
    assert str(active_shift["started_at"]) not in header_html
    assert 'class="machine-nav-actions"' not in html
    assert "--terminal-header-action-width: 260px;" in html
    assert "--terminal-side-action-width: 186px;" in html
    assert re.search(
        r"@media \(max-width: 1360px\).*?"
        r"--terminal-header-action-width: 244px;.*?"
        r"--terminal-side-action-width: 175px;",
        html,
        re.S,
    )


def test_terminal_header_shows_nonwrapping_no_active_shift_label(connection):
    end_active_test_shift()

    html = render_terminal()
    header = re.search(r'<header class="terminal-header".*?</header>', html, re.S)

    assert header is not None
    header_html = header.group(0)
    assert "shift-status-dot" not in header_html
    assert ">Няма активна смяна<" in header_html
    assert 'data-terminal-action="shift"' in header_html


def test_no_active_shift_gate_uses_reference_start_screen_without_generic_header(
    connection,
):
    end_active_test_shift()

    html = render_terminal()
    shift_window = shift_window_block(html)

    assert 'data-shift-state="gate"' in shift_window
    assert 'data-shift-blocking="true"' in shift_window
    assert 'data-shift-pane="gate"' in shift_window
    assert 'data-shift-pane="start-confirm" hidden' in shift_window
    assert 'class="shift-window-header"' not in shift_window
    assert 'class="shift-start-icon shift-start-icon--selection"' in shift_window
    assert '/static/images/shift-ui/shift-switch.svg' in shift_window
    assert '/static/images/shift-ui/calendar-clock.svg' in shift_window
    assert "Начало на смяна" in shift_window
    assert "Изберете номера на смяната, за да започнете работа." in shift_window
    assert "Номер на смяна" in shift_window
    assert "Започни смяна" in shift_window
    assert shift_window.count("data-shift-live-clock") == 2
    assert "data-shift-close" not in shift_window
    assert "Отказ" not in shift_window
    assert ">Back<" not in shift_window
    assert ">Yes<" not in shift_window
    assert "updateShiftClocks" in html
    assert "window.setInterval(updateShiftClocks, 1000)" in html


def test_start_confirmation_replaces_gate_content_and_names_selected_shift(connection):
    ended_shift = end_active_test_shift()

    html = render_terminal()
    shift_window = shift_window_block(html)

    assert html.count('role="dialog" aria-modal="true" data-shift-dialog') == 1
    assert 'data-shift-pane="gate"' in shift_window
    assert 'data-shift-pane="start-confirm" hidden' in shift_window
    assert 'data-shift-confirm-open="start"' in shift_window
    assert 'class="shift-start-icon shift-start-icon--confirmation"' in shift_window
    assert '/static/images/shift-ui/check-circle.svg' in shift_window
    assert '/static/images/shift-ui/calendar.svg' in shift_window
    assert '/static/images/shift-ui/clock.svg' in shift_window
    assert 'data-shift-start-selection' in shift_window
    assert 'data-shift-start-question-number' in shift_window
    assert "Сигурни ли сте, че искате да започнете смяна" in shift_window
    assert f'>{int(ended_shift["shift_number"]) + 1}<' in shift_window
    assert 'data-shift-confirm-submit="start"' in shift_window


def test_start_and_end_confirmations_share_the_same_bulgarian_structure(connection):
    overview_window = shift_window_block(render_terminal(shift_view="overview"))
    end_active_test_shift()
    start_window = shift_window_block(render_terminal())

    assert 'class="shift-window-pane shift-confirmation-pane shift-start-confirmation-pane"' in start_window
    assert 'class="shift-window-pane shift-confirmation-pane shift-end-confirmation-pane"' in overview_window
    assert "Потвърждение за начало" in start_window
    assert "Потвърждение за приключване" in overview_window
    for shift_window in (start_window, overview_window):
        assert "shift-start-icon shift-start-icon--confirmation" in shift_window
        assert "shift-details-card shift-start-details-card" in shift_window
        assert "shift-start-confirmation-question" in shift_window
        assert ">Назад<" in shift_window
        assert ">Потвърди<" in shift_window
        assert ">Back<" not in shift_window
        assert ">Yes<" not in shift_window
        assert "data-shift-nested-modal" not in shift_window
    assert "/static/images/shift-ui/stop-square.svg" in overview_window


def test_targeted_shift_spacing_uses_equal_summary_columns_and_blue_start_icons(
    connection,
):
    html = render_terminal(shift_view="overview")

    summary_rules = css_rules(html, r"(?m)^    \.shift-summary-metadata")
    question_rules = css_rules(html, r"(?m)^    \.shift-start-confirmation-question")
    end_question_rules = css_rules(
        html,
        r"(?m)^    \.shift-end-confirmation-pane \.shift-start-confirmation-question",
    )
    play_icon = Path("app/static/images/shift-ui/play-circle.svg").read_text()

    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in summary_rules
    assert "margin: 6px 0 18px;" in question_rules
    assert "margin: 10px 0 14px;" in end_question_rules
    assert 'stroke="#2865d8"' in play_icon


def test_targeted_terminal_density_compacts_chrome_without_shrinking_recipe_rows(
    connection,
):
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

    compact_rules = compact_height_match.group("rules")
    assert ".machine-nav {\n        padding: 5px 24px;" in compact_rules
    assert ".machine-tab {\n        min-height: 70px;" in compact_rules
    assert ".topbar {\n        min-height: 46px;" in compact_rules
    assert ".details-body {\n        gap: 6px;" in compact_rules
    assert ".order-section {\n        padding: 10px 14px;\n        gap: 14px;" in compact_rules
    assert ".info-grid {\n        row-gap: 14px;" in compact_rules
    assert ".recipe-row {\n        min-height: 36px;" in compact_rules

    short_rules = short_height_match.group("rules")
    assert ".machine-nav {\n        padding: 5px 18px;" in short_rules
    assert ".machine-tab {\n        min-height: 68px;" in short_rules
    assert ".topbar {\n        min-height: 44px;" in short_rules
    assert ".details-body {\n        gap: 5px;" in short_rules
    assert ".order-section {\n        padding: 9px 12px;\n        gap: 12px;" in short_rules
    assert ".info-grid {\n        row-gap: 14px;" in short_rules
    assert ".recipe-row {\n        min-height: 32px;" in short_rules


def test_active_window_uses_current_number_as_the_only_correction_dropdown(connection):
    active_shift = db.fetch_active_shift()
    assert active_shift is not None
    assert db.update_active_shift_number(
        int(active_shift["id"]),
        int(active_shift["version"]),
        "4",
    ).ok
    configuration = db.fetch_terminal_configuration()
    assert db.update_shift_count(int(configuration["version"]), "3").ok

    html = render_terminal(shift_view="overview")
    shift_window = shift_window_block(html)

    assert shift_window.count("<select") == 1
    assert 'name="shift_number" data-shift-number-select' in shift_window
    assert re.search(r'<option value="4" selected disabled>4</option>', shift_window)
    for valid_shift_number in (1, 2, 3):
        valid_option = re.search(
            rf'<option value="{valid_shift_number}"([^>]*)>{valid_shift_number}</option>',
            shift_window,
        )
        assert valid_option is not None
        assert "disabled" not in valid_option.group(1)
    assert 'addEventListener("change"' in html
    assert "shiftNumberForm.requestSubmit()" in html


def test_active_window_shows_start_time_separate_end_action_and_newest_history(
    connection,
):
    end_active_test_shift()
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("2", int(configuration["version"])).ok
    end_active_test_shift()
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("3", int(configuration["version"])).ok
    end_active_test_shift()
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("4", int(configuration["version"])).ok
    end_active_test_shift()
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("1", int(configuration["version"])).ok
    end_active_test_shift()
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("2", int(configuration["version"])).ok
    context = terminal_context(shift_view="overview")
    active_shift = context["active_shift"]
    assert active_shift is not None

    html = render_terminal(shift_view="overview")
    shift_window = shift_window_block(html)

    title_match = re.search(
        r'<h2 id="shift-window-title"[^>]*>\s*([^<]+?)\s*</h2>',
        shift_window,
    )
    assert title_match is not None
    assert title_match.group(1).strip() == "Управление на смяната"
    assert "Текуща смяна" in shift_window
    assert 'name="shift_number" data-shift-number-select' in shift_window
    assert active_shift["started_at_display"] in shift_window
    assert "Приключи смяната" in shift_window
    assert "shift-current-status" not in shift_window
    assert "/static/images/shift-ui/play-circle.svg" in shift_window
    assert "/static/images/shift-ui/stop-square.svg" in shift_window
    assert "/static/images/shift-ui/eye.svg" in shift_window
    assert "Продължителност" not in shift_window
    assert "Виж всички" in shift_window
    assert 'shift_view=history' in shift_window
    assert shift_window.count("data-shift-history-preview-id=") == 5


def test_full_shift_history_replaces_contents_and_uses_bulgarian_columns(connection):
    completed = end_active_test_shift()
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("2", int(configuration["version"])).ok

    html = render_terminal(shift_view="history")
    shift_window = shift_window_block(html)

    assert html.count('role="dialog" aria-modal="true" data-shift-dialog') == 1
    assert 'data-shift-state="history"' in shift_window
    assert 'data-shift-pane="history"' in shift_window
    for heading in (
        "Смяна",
        "Начало",
        "Край",
        "Различни изделия",
        "Ролки",
        "Бруто, кг",
        "Преглед",
    ):
        assert heading in shift_window
    assert f'data-shift-history-id="{completed["id"]}"' in shift_window
    assert 'aria-label="Страници на историята"' in shift_window
    assert 'data-shift-history-page="1"' in shift_window
    assert ">Shift<" not in shift_window
    assert ">Start<" not in shift_window
    assert ">End<" not in shift_window
    assert ">View<" not in shift_window


def test_end_confirmation_replaces_window_content_without_nested_modal(connection):
    active_shift = db.fetch_active_shift()
    assert active_shift is not None

    html = render_terminal(shift_view="overview")
    shift_window = shift_window_block(html)

    assert html.count('role="dialog" aria-modal="true" data-shift-dialog') == 1
    assert 'data-shift-pane="overview"' in shift_window
    assert 'data-shift-pane="end-confirm" hidden' in shift_window
    assert 'data-shift-confirm-open="end"' in shift_window
    assert "Потвърждение за приключване" in shift_window
    assert f'Смяна {active_shift["shift_number"]}' in shift_window
    assert "/static/images/shift-ui/check-circle.svg" in shift_window
    assert "/static/images/shift-ui/calendar.svg" in shift_window
    assert "/static/images/shift-ui/clock.svg" in shift_window
    assert "/static/images/shift-ui/stop-square.svg" in shift_window
    assert "Сигурни ли сте, че искате да приключите смяна" in shift_window
    assert 'data-shift-confirm-submit="end"' in shift_window
    assert "data-shift-nested-modal" not in shift_window


def test_end_summary_renders_header_and_required_order_columns(connection):
    card_id = release_ready_card("SHIFT-SUMMARY", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.50").ok
    summary = end_active_test_shift()

    summary_context = terminal_context(
        card_id,
        shift_view="summary",
        shift_id=str(summary["id"]),
        handoff="1",
    )
    display_summary = summary_context["selected_shift_summary"]
    html = render_terminal(
        card_id,
        shift_view="summary",
        shift_id=str(summary["id"]),
        handoff="1",
    )
    shift_window = shift_window_block(html)

    assert "Произведени количества" in shift_window
    assert f'Смяна {summary["shift_number"]}' in shift_window
    assert display_summary["started_at_display"] in shift_window
    assert display_summary["ended_at_display"] in shift_window
    assert "артикула" not in shift_window
    for heading in (
        "Производствена поръчка",
        "Клиент",
        "Вид изделие",
        "Брой ролки",
        "Бруто, кг",
    ):
        assert heading in shift_window
    assert "SHIFT-SUMMARY" in shift_window
    assert "V8 Customer SHIFT-SUMMARY" in shift_window
    assert "ТСФ 890/0.082" in shift_window
    assert "60.5" in shift_window
    assert "60.50" not in shift_window


def test_empty_shift_summary_renders_empty_table_without_item_counter(connection):
    summary = end_active_test_shift()

    html = render_terminal(
        shift_view="summary",
        shift_id=str(summary["id"]),
        handoff="1",
    )
    shift_window = shift_window_block(html)
    table_body = re.search(r'<tbody data-shift-summary-orders>(.*?)</tbody>', shift_window, re.S)

    assert "0 артикула" not in shift_window
    assert table_body is not None
    assert "data-shift-summary-order" not in table_body.group(1)
    assert "Няма произведени артикули в тази смяна." in shift_window


def test_history_view_and_back_replace_contents_in_one_modal(connection):
    card_id = release_ready_card("SHIFT-HISTORY", machine_id=1, sequence=1)
    completed = end_active_test_shift()
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("2", int(configuration["version"])).ok

    overview_html = render_terminal(card_id, shift_view="overview")
    summary_html = render_terminal(
        card_id,
        shift_view="summary",
        shift_id=str(completed["id"]),
    )

    assert overview_html.count('<div class="shift-window-overlay"') == 1
    assert summary_html.count('<div class="shift-window-overlay"') == 1
    assert (
        f'href="/terminal/cards/{card_id}?shift_view=summary&shift_id={completed["id"]}"'
        in overview_html
    )
    assert f'href="/terminal/cards/{card_id}?shift_view=history"' in summary_html
    assert 'data-shift-pane="summary"' in summary_html
    assert ">Назад<" in summary_html


def test_blocking_shift_state_makes_terminal_content_inert(connection):
    summary = end_active_test_shift()

    gate_html = render_terminal()
    handoff_html = render_terminal(
        shift_view="summary",
        shift_id=str(summary["id"]),
        handoff="1",
    )

    for html in (gate_html, handoff_html):
        app_element = re.search(r'<div class="app"[^>]*>', html)
        assert app_element is not None
        assert " inert" in app_element.group(0)
        assert 'aria-hidden="true"' in app_element.group(0)
        assert 'data-shift-blocking="true"' in html


def test_shift_snapshot_change_renders_blocking_reload_state_without_discarding_dirty_forms(
    connection,
):
    card_id = release_ready_card("SHIFT-STALE", machine_id=1, sequence=1)

    html = render_terminal(card_id)

    assert 'data-shift-pane="reload" hidden' in html
    assert "Смяната е променена" in html
    assert "let currentShiftSignature = initialSnapshot.shift_signature;" in html
    assert "snapshot.shift_signature !== currentShiftSignature" in html
    assert 'new CustomEvent("terminal:shift-stale")' in html
    assert 'shiftApp.setAttribute("inert", "")' in html
    assert 'shiftApp.setAttribute("aria-hidden", "true")' in html
    assert 'form[data-recipe-autosave="true"], form[data-dirty-autosave="true"]' in html
    assert "window.location.reload()" not in html
    assert ".reset()" not in html
