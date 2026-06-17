from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import db
from app.constants import STATUS_CANCELLED, STATUS_COMPLETED, STATUS_PENDING, STATUS_RUNNING
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import admin_card_detail_context, app


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
        "customer": "Admin Correction Customer",
        "product_type": "PE film",
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "da",
        "raw_material_a": "LDPE A",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def import_ready_card(order_number: str) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number)),
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


def release_ready_card(order_number: str, machine_id: int = 1, sequence: int = 1) -> int:
    card_id = import_ready_card(order_number)
    assert db.release_card(
        card_id,
        machine_id,
        sequence,
        card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    return card_id


def card_version(card_id: int) -> int:
    return int(db.fetch_admin_card_detail(card_id)["version"])


def start_card(card_id: int) -> None:
    assert db.start_production_timing(card_id, card_version(card_id)).ok


def add_tare(card_id: int, tare_weight: str = "1.00") -> None:
    assert db.update_tare_weight(card_id, card_version(card_id), tare_weight).ok


def add_roll(card_id: int, gross_weight: str = "25.00") -> None:
    assert db.add_roll_gross_weight(card_id, card_version(card_id), gross_weight).ok


def prepare_completed_card(order_number: str) -> int:
    card_id = release_ready_card(order_number)
    start_card(card_id)
    add_tare(card_id)
    add_roll(card_id)
    assert db.finish_card(card_id, card_version(card_id)).ok
    return card_id


def test_admin_cancel_closes_running_segment_and_blocks_stale_version(connection):
    card_id = release_ready_card("26000")
    start_card(card_id)
    loaded_version = card_version(card_id)

    result = db.cancel_card(card_id, loaded_version)
    card = db.fetch_admin_card_detail(card_id)
    segment = card["timing_segments"][0]

    stale_card_id = release_ready_card("26010", machine_id=2, sequence=1)
    stale_version = card_version(stale_card_id)
    add_tare(stale_card_id)
    stale_result = db.cancel_card(stale_card_id, stale_version)

    assert result.ok
    assert card["status"] == STATUS_CANCELLED
    assert card["version"] == loaded_version + 1
    assert segment["ended_at"] is not None
    assert segment["end_reason"] == "correction"
    assert not stale_result.ok
    assert stale_result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )


def test_admin_restore_returns_cancelled_card_to_pending_and_blocks_duplicate_sequence(connection):
    cancelled_id = release_ready_card("26001", machine_id=2, sequence=1)
    assert db.cancel_card(cancelled_id, card_version(cancelled_id)).ok
    restore_version = card_version(cancelled_id)

    result = db.restore_cancelled_card(cancelled_id, restore_version)
    restored = db.fetch_admin_card_detail(cancelled_id)

    assert result.ok
    assert restored["status"] == STATUS_PENDING
    assert restored["version"] == restore_version + 1

    assert db.cancel_card(cancelled_id, card_version(cancelled_id)).ok
    release_ready_card("26002", machine_id=2, sequence=1)
    blocked = db.restore_cancelled_card(cancelled_id, card_version(cancelled_id))

    assert not blocked.ok
    assert blocked.messages == ("Машина 2 вече има активен ред 1 за поръчка 26002.",)


def test_admin_material_correction_updates_terminal_fields_and_blocks_stale_version(connection):
    card_id = release_ready_card("26003")
    loaded_version = card_version(card_id)

    result = db.update_terminal_material_fields(
        card_id,
        loaded_version,
        "Actual LDPE",
        "Grade A",
        "Batch 42",
    )
    stale_result = db.update_terminal_material_fields(
        card_id,
        loaded_version,
        "Stale",
        "Grade B",
        "Batch 99",
    )
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["actual_raw_material_used"] == "Actual LDPE"
    assert card["raw_material_brand_grade"] == "Grade A"
    assert card["raw_material_batch_lot"] == "Batch 42"
    assert not stale_result.ok


def test_admin_tare_correction_recalculates_net_weights_and_blocks_invalid_tare(connection):
    card_id = release_ready_card("26004")
    start_card(card_id)
    add_tare(card_id, "1.00")
    add_roll(card_id, "10.00")
    loaded_version = card_version(card_id)

    result = db.update_tare_weight(card_id, loaded_version, "2.50")
    invalid_result = db.update_tare_weight(card_id, card_version(card_id), "11.00")
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["tare_weight"] == 2.5
    assert card["roll_entries"][0]["net_weight"] == 7.5
    assert card["total_net_weight"] == "7.50"
    assert not invalid_result.ok
    assert invalid_result.messages == (
        "Шпулата не може да бъде по-голяма от съществуващо бруто тегло на ролка.",
    )


def test_admin_roll_add_update_delete_preserves_numbering_and_completed_final_roll(connection):
    card_id = prepare_completed_card("26005")
    add_result = db.add_roll_gross_weight(card_id, card_version(card_id), "30.00")
    card = db.fetch_admin_card_detail(card_id)
    first_roll_id = card["roll_entries"][0]["id"]

    update_result = db.update_roll_gross_weight(
        card_id,
        first_roll_id,
        card["version"],
        "26.00",
    )
    updated_card = db.fetch_admin_card_detail(card_id)
    second_roll_id = updated_card["roll_entries"][1]["id"]
    delete_result = db.delete_roll_entry(card_id, second_roll_id, updated_card["version"])
    final_card = db.fetch_admin_card_detail(card_id)
    blocked_delete = db.delete_roll_entry(
        card_id,
        final_card["roll_entries"][0]["id"],
        final_card["version"],
    )

    assert add_result.ok
    assert update_result.ok
    assert delete_result.ok
    assert final_card["status"] == STATUS_COMPLETED
    assert final_card["roll_count"] == 1
    assert final_card["roll_entries"][0]["roll_number"] == 1
    assert final_card["roll_entries"][0]["gross_weight"] == 26
    assert not blocked_delete.ok
    assert blocked_delete.messages == ("Завършените карти трябва да запазят поне едно бруто тегло на ролка.",)


def test_admin_timing_segment_edit_recalculates_total_time(connection):
    card_id = release_ready_card("26006")
    add_result = db.add_timing_segment(
        card_id,
        card_version(card_id),
        "2026-06-14 08:00:00",
        "2026-06-14 09:00:00",
        "pause",
    )
    segment_id = db.fetch_admin_card_detail(card_id)["timing_segments"][0]["id"]
    update_result = db.update_timing_segment(
        card_id,
        segment_id,
        card_version(card_id),
        "2026-06-14 08:00:00",
        "2026-06-14 10:00:00",
        "correction",
    )
    card = db.fetch_admin_card_detail(card_id)

    assert add_result.ok
    assert update_result.ok
    assert card["total_production_seconds"] == 7200
    assert card["timing_segments"][0]["end_reason"] == "correction"
    assert card["first_started_at"] == "2026-06-14 08:00:00"


def test_admin_timing_correction_rejects_invalid_intervals_and_multiple_open_segments(connection):
    card_id = release_ready_card("26007")

    invalid_interval = db.add_timing_segment(
        card_id,
        card_version(card_id),
        "2026-06-14 10:00:00",
        "2026-06-14 09:00:00",
        "pause",
    )
    running_card_id = release_ready_card("26014", machine_id=2, sequence=1)
    start_card(running_card_id)
    open_result = db.add_timing_segment(
        running_card_id,
        card_version(running_card_id),
        "2026-06-14 10:00:00",
        "",
        "",
    )
    non_running_open_result = db.add_timing_segment(
        card_id,
        card_version(card_id),
        "2026-06-14 10:00:00",
        "",
        "",
    )
    assert not invalid_interval.ok
    assert invalid_interval.messages == ("Краят не може да бъде преди началото.",)
    assert not open_result.ok
    assert open_result.messages == ("Картата вече има отворен времеви сегмент.",)
    assert not non_running_open_result.ok
    assert non_running_open_result.messages == ("Само карти в изработване могат да имат отворен времеви сегмент.",)


def test_admin_timing_correction_blocks_deleting_all_timing_from_completed_card(connection):
    card_id = prepare_completed_card("26008")
    card = db.fetch_admin_card_detail(card_id)
    segment_id = card["timing_segments"][0]["id"]

    delete_result = db.delete_timing_segment(card_id, segment_id, card["version"])
    open_update_result = db.update_timing_segment(
        card_id,
        segment_id,
        card["version"],
        card["timing_segments"][0]["started_at"],
        "",
        "",
    )

    assert not delete_result.ok
    assert delete_result.messages == ("Завършените карти трябва да запазят поне един времеви сегмент.",)
    assert not open_update_result.ok
    assert open_update_result.messages == ("Само карти в изработване могат да имат отворен времеви сегмент.",)


def test_admin_timing_correction_preserves_running_open_segment(connection):
    card_id = release_ready_card("26012")
    start_card(card_id)
    card = db.fetch_admin_card_detail(card_id)
    segment_id = card["timing_segments"][0]["id"]
    started_at = card["timing_segments"][0]["started_at"]
    ended_at = (
        datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=5)
    ).strftime("%Y-%m-%d %H:%M:%S")

    close_result = db.update_timing_segment(
        card_id,
        segment_id,
        card["version"],
        started_at,
        ended_at,
        "correction",
    )
    delete_result = db.delete_timing_segment(card_id, segment_id, card["version"])

    assert not close_result.ok
    assert close_result.messages == ("Картите в изработване трябва да запазят отворен времеви сегмент.",)
    assert not delete_result.ok
    assert delete_result.messages == ("Картите в изработване трябва да запазят отворен времеви сегмент.",)


def test_admin_timing_correction_blocks_open_segment_on_non_running_card(connection):
    card_id = release_ready_card("26013")

    result = db.add_timing_segment(
        card_id,
        card_version(card_id),
        "2026-06-14 08:00:00",
        "",
        "",
    )

    assert not result.ok
    assert result.messages == ("Само карти в изработване могат да имат отворен времеви сегмент.",)


def test_admin_timing_correction_blocks_stale_loaded_version(connection):
    card_id = release_ready_card("26009")
    loaded_version = card_version(card_id)
    assert db.add_timing_segment(
        card_id,
        loaded_version,
        "2026-06-14 08:00:00",
        "2026-06-14 09:00:00",
        "pause",
    ).ok

    stale_result = db.add_timing_segment(
        card_id,
        loaded_version,
        "2026-06-14 09:30:00",
        "2026-06-14 10:00:00",
        "pause",
    )

    assert not stale_result.ok
    assert stale_result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )


def test_completed_admin_detail_hides_unsafe_delete_controls(connection):
    card_id = prepare_completed_card("26011")
    card = db.fetch_admin_card_detail(card_id)
    roll_id = card["roll_entries"][0]["id"]
    segment_id = card["timing_segments"][0]["id"]

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["url_for"] = lambda name, **kwargs: "/static/css/app.css"
    context = admin_card_detail_context(card_id)
    html = env.get_template("admin_card_detail.html").render(**context)

    assert f"/admin/cards/{card_id}/rolls/{roll_id}/delete" not in html
    assert f"/admin/cards/{card_id}/timing-segments/{segment_id}/delete" not in html


def test_admin_production_correction_routes_are_registered():
    route_paths = {route.path for route in app.routes}

    assert "/admin/cards/{card_id}/cancel" in route_paths
    assert "/admin/cards/{card_id}/restore" in route_paths
    assert "/admin/cards/{card_id}/production-materials" in route_paths
    assert "/admin/cards/{card_id}/tare" in route_paths
    assert "/admin/cards/{card_id}/rolls" in route_paths
    assert "/admin/cards/{card_id}/rolls/{roll_id}" in route_paths
    assert "/admin/cards/{card_id}/rolls/{roll_id}/delete" in route_paths
    assert "/admin/cards/{card_id}/timing-segments" in route_paths
    assert "/admin/cards/{card_id}/timing-segments/{segment_id}" in route_paths
    assert "/admin/cards/{card_id}/timing-segments/{segment_id}/delete" in route_paths
