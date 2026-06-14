from __future__ import annotations

import csv
import io
import asyncio

from starlette.requests import Request

from app import db
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import app, terminal_card


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
        "customer": "Render Customer",
        "product_type": "PE film",
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "da",
        "raw_material_a": "LDPE A",
        "raw_material_b": "LDPE B",
        "linear_pe": "20%",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def import_and_release_card(
    order_number: str,
    machine_id: int = 1,
    machine_sequence: int = 1,
) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number)),
        overwrite_existing=False,
    )
    assert result.rows_imported == 1
    with db.connect() as connection:
        card_id = int(
            connection.execute(
                "SELECT id FROM cards WHERE order_number = ?",
                (order_number,),
            ).fetchone()["id"]
        )
    assert db.release_card(card_id, machine_id, machine_sequence).ok
    return card_id


def make_running(card_id: int) -> None:
    assert db.start_production_timing(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
    ).ok


def make_finishable(card_id: int) -> None:
    make_running(card_id)
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.00",
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
    ).ok


def request_for(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "app": app,
        }
    )


def render_terminal_card(card_id: int) -> str:
    response = asyncio.run(terminal_card(request_for(f"/terminal/cards/{card_id}"), card_id))
    return response.body.decode("utf-8")


def test_terminal_renders_v4_shell_with_live_selected_card(connection):
    card_id = import_and_release_card("26000", machine_id=1, machine_sequence=1)
    card = db.fetch_terminal_card_detail(card_id)

    html = render_terminal_card(card_id)

    assert "data-terminal-v4-shell" in html
    assert "data-terminal-active-panel" in html
    assert "data-terminal-archive-panel" in html
    assert "No. 26000" in html
    assert "Render Customer" in html
    assert "LDPE A" in html
    assert f'action="/terminal/cards/{card_id}/timing/start"' in html
    assert f'name="loaded_version" value="{card["version"]}"' in html
    assert "const orders" not in html
    assert "selectedId" not in html


def test_terminal_v4_archive_tab_renders_completed_and_cancelled_cards(connection):
    completed_id = import_and_release_card("26001", machine_id=1, machine_sequence=1)
    make_finishable(completed_id)
    assert db.finish_card(
        completed_id,
        db.fetch_terminal_card_detail(completed_id)["version"],
    ).ok
    cancelled_id = import_and_release_card("26002", machine_id=2, machine_sequence=1)
    assert db.cancel_card(
        cancelled_id,
        db.fetch_terminal_card_detail(cancelled_id)["version"],
    ).ok

    html = render_terminal_card(completed_id)

    assert "No. 26001" in html
    assert "completed" in html
    assert "No. 26002" in html
    assert "cancelled" in html
    archive_tag = 'id="terminal-archive-panel" data-terminal-archive-panel'
    assert archive_tag in html


def test_terminal_v4_status_controls_use_live_forms_and_loaded_versions(connection):
    running_id = import_and_release_card("26003", machine_id=3, machine_sequence=1)
    make_running(running_id)
    running = db.fetch_terminal_card_detail(running_id)
    paused_id = import_and_release_card("26004", machine_id=4, machine_sequence=1)
    make_running(paused_id)
    assert db.pause_production_timing(
        paused_id,
        db.fetch_terminal_card_detail(paused_id)["version"],
    ).ok
    paused = db.fetch_terminal_card_detail(paused_id)

    running_html = render_terminal_card(running_id)
    paused_html = render_terminal_card(paused_id)

    assert f'action="/terminal/cards/{running_id}/timing/pause"' in running_html
    assert f'action="/terminal/cards/{running_id}/rolls"' in running_html
    assert f'name="loaded_version" value="{running["version"]}"' in running_html
    assert "data-terminal-pause-form" in running_html

    assert f'action="/terminal/cards/{paused_id}/timing/resume"' in paused_html
    assert f'name="loaded_version" value="{paused["version"]}"' in paused_html
    assert "data-terminal-resume-form" in paused_html
    assert 'name="gross_weight" min="0" step="0.01" inputmode="decimal" autocomplete="off" disabled' in paused_html
