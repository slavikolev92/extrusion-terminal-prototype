from __future__ import annotations

import asyncio
import csv
import io
from datetime import datetime, timedelta

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import db
from app.constants import STATUS_CANCELLED, STATUS_COMPLETED, STATUS_PENDING, STATUS_RUNNING
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import (
    add_admin_roll_weight,
    add_admin_timing_segment,
    admin_card_detail,
    admin_card_detail_context,
    app,
    cancel_admin_card,
    delete_admin_roll_weight,
    delete_admin_timing_segment,
    restore_admin_card,
    save_admin_imported_fields,
    save_admin_production_materials,
    save_admin_roll_weight,
    save_admin_tare_weight,
    save_admin_timing_segment,
)


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


def recipe_actual_entries(**overrides: dict[str, str]) -> dict[str, dict[str, str]]:
    entries = {
        "raw_material_a": {
            "actual_material_used": "Terminal A",
            "batch_lot": "Terminal Batch A",
        },
        "raw_material_b": {
            "actual_material_used": "Terminal B",
            "batch_lot": "Terminal Batch B",
        },
        "raw_material_c": {
            "actual_material_used": "",
            "batch_lot": "",
        },
        "linear_pe": {
            "actual_material_used": "",
            "batch_lot": "",
        },
        "antistatic": {
            "actual_material_used": "",
            "batch_lot": "",
        },
        "masterbatch": {
            "actual_material_used": "",
            "batch_lot": "",
        },
        "chalk": {
            "actual_material_used": "",
            "batch_lot": "",
        },
    }
    entries.update(overrides)
    return entries


def card_version(card_id: int) -> int:
    return int(db.fetch_admin_card_detail(card_id)["version"])


def current_imported_fields(card_id: int) -> dict[str, str]:
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    return {field: str(card[field] or "") for field in IMPORT_FIELDS}


def start_card(card_id: int) -> None:
    assert db.start_production_timing(card_id, card_version(card_id)).ok


def add_tare(card_id: int, tare_weight: str = "1.00") -> None:
    assert db.update_tare_weight(card_id, card_version(card_id), tare_weight).ok


def add_roll(card_id: int, gross_weight: str = "25.00") -> None:
    assert db.add_roll_gross_weight(card_id, card_version(card_id), gross_weight).ok


class FormData(dict):
    def multi_items(self) -> list[tuple[str, str]]:
        return list(self.items())


class FormRequest:
    def __init__(self, data: dict[str, str]) -> None:
        self.data = FormData(data)

    async def form(self) -> FormData:
        return self.data

    def url_for(self, name: str, **path_params: str) -> str:
        if name == "static":
            return f"/static{path_params.get('path', '')}"
        return f"/{name}"


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
    assert card["recipe_actual_entries"]["raw_material_a"]["actual_material_used"] == "Actual LDPE"
    assert card["recipe_actual_entries"]["raw_material_a"]["batch_lot"] == "Batch 42"
    assert not stale_result.ok


def test_admin_material_correction_route_updates_recipe_actual_entries(connection):
    card_id = import_ready_card("26015", raw_material_b="LDPE B")
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        card_version(card_id),
        recipe_actual_entries(),
    ).ok

    response = asyncio.run(
        save_admin_production_materials(
            FormRequest(
                {
                    "loaded_version": str(card_version(card_id)),
                    "raw_material_brand_grade": "Admin Grade A",
                    "actual_material__raw_material_a": "Admin A",
                    "batch_lot__raw_material_a": "Admin Batch A",
                    "actual_material__raw_material_b": "Terminal B",
                    "batch_lot__raw_material_b": "Terminal Batch B",
                    "actual_material__raw_material_c": "",
                    "batch_lot__raw_material_c": "",
                    "actual_material__linear_pe": "",
                    "batch_lot__linear_pe": "",
                    "actual_material__antistatic": "",
                    "batch_lot__antistatic": "",
                    "actual_material__masterbatch": "",
                    "batch_lot__masterbatch": "",
                    "actual_material__chalk": "",
                    "batch_lot__chalk": "",
                }
            ),
            card_id,
        )
    )
    card = db.fetch_admin_card_detail(card_id)
    context = admin_card_detail_context(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/cards/{card_id}#materials"
    assert card["recipe_actual_entries"]["raw_material_a"]["actual_material_used"] == "Admin A"
    assert card["recipe_actual_entries"]["raw_material_a"]["batch_lot"] == "Admin Batch A"
    assert card["recipe_actual_entries"]["raw_material_b"]["actual_material_used"] == "Terminal B"
    assert card["actual_raw_material_used"] == "Admin A"
    assert card["raw_material_brand_grade"] == "Admin Grade A"
    assert card["raw_material_batch_lot"] == "Admin Batch A"
    assert context["recipe_rows"][0]["actual_material"] == "Admin A"
    assert context["recipe_rows"][0]["batch"] == "Admin Batch A"
    assert context["recipe_rows"][1]["actual_material"] == "Terminal B"


def test_admin_material_correction_route_preserves_legacy_brand_when_omitted(connection):
    card_id = import_ready_card("26016", raw_material_b="LDPE B")
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        card_version(card_id),
        recipe_actual_entries(),
        raw_material_brand_grade="Legacy Grade A",
    ).ok

    response = asyncio.run(
        save_admin_production_materials(
            FormRequest(
                {
                    "loaded_version": str(card_version(card_id)),
                    "actual_material__raw_material_a": "Admin A",
                    "batch_lot__raw_material_a": "Admin Batch A",
                    "actual_material__raw_material_b": "Terminal B",
                    "batch_lot__raw_material_b": "Terminal Batch B",
                    "actual_material__raw_material_c": "",
                    "batch_lot__raw_material_c": "",
                    "actual_material__linear_pe": "",
                    "batch_lot__linear_pe": "",
                    "actual_material__antistatic": "",
                    "batch_lot__antistatic": "",
                    "actual_material__masterbatch": "",
                    "batch_lot__masterbatch": "",
                    "actual_material__chalk": "",
                    "batch_lot__chalk": "",
                }
            ),
            card_id,
        )
    )
    card = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert card["actual_raw_material_used"] == "Admin A"
    assert card["raw_material_brand_grade"] == "Legacy Grade A"
    assert card["raw_material_batch_lot"] == "Admin Batch A"


def test_admin_successful_detail_correction_routes_redirect_to_canonical_get(connection):
    card_id = prepare_completed_card("26021")
    card = db.fetch_admin_card_detail(card_id)
    fields = current_imported_fields(card_id)
    fields["loaded_version"] = str(card["version"])
    fields["customer"] = "PRG Customer"

    imported_response = asyncio.run(
        save_admin_imported_fields(FormRequest(fields), card_id)
    )
    tare_response = asyncio.run(
        save_admin_tare_weight(
            FormRequest({}),
            card_id,
            str(card_version(card_id)),
            "2.00",
        )
    )
    card = db.fetch_admin_card_detail(card_id)
    roll_response = asyncio.run(
        save_admin_roll_weight(
            FormRequest({}),
            card_id,
            card["roll_entries"][0]["id"],
            str(card["version"]),
            "27.00",
        )
    )
    card = db.fetch_admin_card_detail(card_id)
    timing_response = asyncio.run(
        save_admin_timing_segment(
            FormRequest({}),
            card_id,
            card["timing_segments"][0]["id"],
            str(card["version"]),
            card["timing_segments"][0]["started_at"],
            card["timing_segments"][0]["ended_at"],
            "correction",
        )
    )
    after = db.fetch_admin_card_detail(card_id)

    expected_locations = (
        (imported_response, f"/admin/cards/{card_id}#order"),
        (tare_response, f"/admin/cards/{card_id}#rolls"),
        (roll_response, f"/admin/cards/{card_id}#rolls"),
        (timing_response, f"/admin/cards/{card_id}#timing"),
    )
    for response, expected_location in expected_locations:
        assert response.status_code == 303
        assert response.headers["location"] == expected_location
    assert after["customer"] == "PRG Customer"
    assert after["tare_weight"] == 2
    assert after["roll_entries"][0]["gross_weight"] == 27
    assert after["timing_segments"][0]["end_reason"] == "correction"


def test_admin_successful_roll_add_redirects_and_get_refresh_does_not_repeat(connection):
    card_id = prepare_completed_card("26016")
    loaded_version = card_version(card_id)

    response = asyncio.run(
        add_admin_roll_weight(
            FormRequest({}),
            card_id,
            str(loaded_version),
            "30.00",
        )
    )
    refresh = asyncio.run(admin_card_detail(FormRequest({}), card_id))
    card = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/cards/{card_id}#rolls"
    assert refresh.status_code == 200
    assert card["roll_count"] == 2
    assert [roll["gross_weight"] for roll in card["roll_entries"]] == [25, 30]


def test_admin_successful_roll_delete_redirects_and_get_refresh_does_not_repeat(connection):
    card_id = prepare_completed_card("26017")
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "30.00").ok
    card = db.fetch_admin_card_detail(card_id)
    roll_id = card["roll_entries"][1]["id"]

    response = asyncio.run(
        delete_admin_roll_weight(
            FormRequest({}),
            card_id,
            roll_id,
            str(card["version"]),
        )
    )
    refresh = asyncio.run(admin_card_detail(FormRequest({}), card_id))
    after = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/cards/{card_id}#rolls"
    assert refresh.status_code == 200
    assert after["roll_count"] == 1
    assert [roll["gross_weight"] for roll in after["roll_entries"]] == [25]


def test_admin_successful_timing_segment_add_delete_redirect_and_get_refresh_is_safe(connection):
    card_id = release_ready_card("26018")

    add_response = asyncio.run(
        add_admin_timing_segment(
            FormRequest({}),
            card_id,
            str(card_version(card_id)),
            "2026-06-14 08:00:00",
            "2026-06-14 09:00:00",
            "pause",
        )
    )
    add_refresh = asyncio.run(admin_card_detail(FormRequest({}), card_id))
    card = db.fetch_admin_card_detail(card_id)
    segment_id = card["timing_segments"][0]["id"]

    delete_response = asyncio.run(
        delete_admin_timing_segment(
            FormRequest({}),
            card_id,
            segment_id,
            str(card["version"]),
        )
    )
    delete_refresh = asyncio.run(admin_card_detail(FormRequest({}), card_id))
    after = db.fetch_admin_card_detail(card_id)

    assert add_response.status_code == 303
    assert add_response.headers["location"] == f"/admin/cards/{card_id}#timing"
    assert add_refresh.status_code == 200
    assert len(card["timing_segments"]) == 1
    assert delete_response.status_code == 303
    assert delete_response.headers["location"] == f"/admin/cards/{card_id}#timing"
    assert delete_refresh.status_code == 200
    assert after["timing_segments"] == []


def test_admin_successful_cancel_restore_redirect_and_get_refresh_does_not_toggle(connection):
    card_id = release_ready_card("26019")

    cancel_response = asyncio.run(
        cancel_admin_card(FormRequest({}), card_id, str(card_version(card_id)))
    )
    cancel_refresh = asyncio.run(admin_card_detail(FormRequest({}), card_id))
    cancelled = db.fetch_admin_card_detail(card_id)

    restore_response = asyncio.run(
        restore_admin_card(FormRequest({}), card_id, str(cancelled["version"]))
    )
    restore_refresh = asyncio.run(admin_card_detail(FormRequest({}), card_id))
    restored = db.fetch_admin_card_detail(card_id)

    assert cancel_response.status_code == 303
    assert cancel_response.headers["location"] == f"/admin/cards/{card_id}"
    assert cancel_refresh.status_code == 200
    assert cancelled["status"] == STATUS_CANCELLED
    assert restore_response.status_code == 303
    assert restore_response.headers["location"] == f"/admin/cards/{card_id}"
    assert restore_refresh.status_code == 200
    assert restored["status"] == STATUS_PENDING


def test_admin_stale_roll_add_still_renders_inline_without_redirect(connection):
    card_id = prepare_completed_card("26020")
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "2.00").ok

    response = asyncio.run(
        add_admin_roll_weight(
            FormRequest({}),
            card_id,
            str(loaded_version),
            "30.00",
        )
    )

    assert response.status_code == 200
    assert "location" not in response.headers
    assert "roll_result" in response.context
    assert response.context["roll_result"].messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )


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


def test_completed_admin_detail_uses_explicit_delete_controls(connection):
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

    assert f"/admin/cards/{card_id}/rolls/{roll_id}/delete" in html
    assert f"/admin/cards/{card_id}/timing-segments/{segment_id}/delete" in html
    assert html.count('name="loaded_version"') >= 2
    assert "admin-row-delete-button" in html


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
