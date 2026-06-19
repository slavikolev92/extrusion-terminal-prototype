from __future__ import annotations

import asyncio
import csv
import io
import re

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.requests import Request

from app import db
from app.db import STALE_CARD_MESSAGE
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import (
    app,
    delete_selected_roll_weight,
    finish_terminal_card,
    progress_percent,
    remaining_gross_display,
    target_gross_decimal,
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
        "raw_material_a": "LDPE A",
        "raw_material_b": "LLDPE B",
        "raw_material_c": "HDPE C",
        "linear_pe": "Линеен PE",
        "antistatic": "Антистатик 1%",
        "masterbatch": "Бял мастербач",
        "chalk": "Креда 5%",
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


def roll_row_block(html: str, roll_id: int) -> str:
    start_marker = f'<div class="roll-row" data-roll-id="{roll_id}">'
    start = html.find(start_marker)
    assert start != -1
    next_start = html.find('<div class="roll-row" data-roll-id="', start + len(start_marker))
    table_end = html.find('<div class="totals">', start)
    end_candidates = [position for position in (next_start, table_end) if position != -1]
    assert end_candidates
    return html[start : min(end_candidates)]


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


def test_terminal_v8_selects_requested_machine_focus_card(connection):
    release_ready_card("26115", machine_id=1, sequence=1)
    focused_id = release_ready_card("26116", machine_id=2, sequence=1)

    context = terminal_context(selected_machine_id=2)
    html = render_terminal(machine_id=2)

    assert context["selected_card"]["id"] == focused_id
    assert context["selected_machine_id"] == 2
    assert "Машина 2: №26116" in html
    assert "Няма активна поръчка за Машина 2." not in html


def test_terminal_v8_renders_selected_card_details_and_max_roll_weight(connection):
    card_id = release_ready_card("26101", machine_id=1, sequence=1)

    html = render_terminal(card_id)

    assert "Машина 1: №26101" in html
    assert "ТСФ 890/0.082" in html
    assert "V8 Customer 26101" in html
    assert "500 kg / 5 ролки" in html
    assert "890 / 0.082" in html
    assert "плоско" in html
    assert "LDPE" in html
    assert "Макс. тегло ролка, кг" in html
    assert "62.5" in html
    assert "Важна бележка за оператор." in html


def test_terminal_v8_renders_recipe_queue_and_completed_lookup(connection):
    selected_id = release_ready_card("26102", machine_id=1, sequence=1)
    release_ready_card("26103", machine_id=1, sequence=2, customer="Queued Customer")
    completed_id = release_ready_card("26104", machine_id=2, sequence=1, customer="Done Customer")
    complete_card(completed_id)
    cancelled_id = release_ready_card("26105", machine_id=3, sequence=1, customer="Hidden Customer")
    assert db.cancel_card(cancelled_id, card_version(cancelled_id)).ok

    html = render_terminal(selected_id)

    assert "LDPE A" in html
    assert "LLDPE B" in html
    assert "HDPE C" in html
    assert "Линеен PE" in html
    assert "Вид суровина A" in html
    assert "Вид суровина B" in html
    assert "Вид суровина C" in html
    assert "Линеен /mLLDPE/" in html
    assert "Антистатик 1%" in html
    assert "Бял мастербач" in html
    assert "Креда 5%" in html
    assert "Марка" not in html
    assert "v8-recipe-actions" not in html
    assert "Queued Customer" in html
    assert "№26103" in html
    assert "Done Customer" in html
    assert "№26104" in html
    assert "Hidden Customer" not in html
    assert "№26105" not in html


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


def test_target_gross_resolves_from_quantity_2_and_remaining_clamps(connection):
    card_id = release_ready_card(
        "26141",
        machine_id=1,
        sequence=1,
        quantity_1="7",
        unit_1="ролки",
        quantity_2="100",
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


def test_terminal_v8_does_not_show_fake_zero_target_when_no_kg_quantity(connection):
    card_id = release_ready_card(
        "26142",
        machine_id=1,
        sequence=1,
        quantity_1="7",
        unit_1="ролки",
        quantity_2="20",
        unit_2="бр",
    )

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


def test_terminal_v8_print_link_is_available_only_for_completed_cards(connection):
    completed_id = release_ready_card("26180", machine_id=1, sequence=1)
    complete_card(completed_id)
    pending_id = release_ready_card("26181", machine_id=2, sequence=1)

    completed_html = render_terminal(completed_id)
    pending_html = render_terminal(pending_id)

    assert (
        f'<a href="/cards/{completed_id}/print?auto=1&amp;source=terminal" '
        'target="_blank" rel="noopener">Печат / препечат</a>'
    ) in completed_html
    assert "Печат / препечат" in completed_html
    assert f"/cards/{pending_id}/print" not in pending_html
    assert "Печат / препечат" not in pending_html


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
    assert 'data-icon="pause"' in pause_form
    assert "Пауза" in pause_form
    assert 'data-icon="check-circle"' in finish_form
    assert "Приключи" in finish_form
    assert 'data-icon="plus"' in roll_form
    assert "Добави" in roll_form

    assert db.pause_production_timing(card_id, card_version(card_id)).ok
    paused_html = render_terminal(card_id)
    resume_form = form_block(
        paused_html,
        f"/terminal/cards/{card_id}/timing/resume",
    )
    assert 'data-icon="play"' in resume_form
    assert "Продължи" in resume_form


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


def test_terminal_v8_roll_delete_is_hidden_behind_menu_correction_action(connection):
    card_id = release_ready_card("26172", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "61.00").ok

    html = render_terminal(card_id)
    roll_id = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]["id"]
    row_html = roll_row_block(html, roll_id)

    assert 'id="roll-correction-open"' in html
    assert "Корекции на ролки" in html
    assert 'class="roll-delete-panel" id="roll-delete-panel" hidden' in html
    assert 'id="roll-delete-close"' in html
    assert f'action="/terminal/cards/{card_id}/rolls/actions/delete-selected"' in html
    assert 'name="confirm_roll_number"' in html
    assert 'name="roll_id"' in html
    assert "Изтриване на ролка" in html
    assert "/delete" not in row_html
    assert "Изтрий" not in row_html

    error_html = render_terminal(
        card_id,
        roll_result=RuleResult(False, ("delete failure",)),
        roll_result_target="roll_delete",
    )
    delete_block = data_block(error_html, "data-feedback-target", "roll_delete")
    assert 'class="roll-delete-panel" id="roll-delete-panel" hidden' not in error_html
    assert "delete failure" in delete_block


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
    assert deleted.headers["location"] == f"/terminal/cards/{card_id}"
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
    assert response.headers["location"] == f"/terminal/cards/{card_id}"
    assert "Действието не беше записано" not in refresh_html
    assert "Картата не е намерена." not in refresh_html
    assert f"№{card['order_number']}" in refresh_html


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
        "Шпула е задължителна преди приключване.",
    )


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
