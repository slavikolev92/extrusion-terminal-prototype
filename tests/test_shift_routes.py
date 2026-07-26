from __future__ import annotations

import asyncio
import csv
import io
from urllib.parse import urlencode

from app import db
import app.main as main_module
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import app, terminal_context


def csv_bytes(*rows: dict[str, str]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")


def extrusion_row(order_number: str) -> dict[str, str]:
    return {
        "order_number": order_number,
        "customer": "Shift Route Customer",
        "product_type": "PE film",
        "ordered_gross_kg": "500",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_sequence": "1",
        "raw_material_a": "LDPE; A | 100%",
        "packaging_method": "rolls",
    }


def release_ready_card(order_number: str) -> int:
    imported = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number)),
        overwrite_existing=False,
    )
    assert imported.rows_imported == 1
    with db.connect() as connection:
        card_id = int(
            connection.execute(
                "SELECT id FROM cards WHERE order_number = ?",
                (order_number,),
            ).fetchone()["id"]
        )
    version = int(db.fetch_admin_card_detail(card_id)["version"])
    assert db.release_card(card_id, 1, 1, version).ok
    return card_id


async def post_form(path: str, data: dict[str, str]) -> tuple[int, dict[str, str], str]:
    body = urlencode(data).encode("utf-8")
    messages: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, object]) -> None:
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
            "app": app,
        },
        receive,
        send,
    )
    response_start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in response_start["headers"]
    }
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    ).decode("utf-8")
    return int(response_start["status"]), headers, response_body


async def get_page(path: str, query_string: str = "") -> tuple[int, str]:
    messages: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": query_string.encode("ascii"),
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
            "app": app,
        },
        receive,
        send,
    )
    response_start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    ).decode("utf-8")
    return int(response_start["status"]), response_body


def assert_blocking_shift_reload(body: str) -> None:
    assert 'data-shift-state="reload"' in body
    assert 'data-shift-blocking="true"' in body
    assert 'data-shift-pane="reload"' in body
    assert 'data-shift-pane="reload" hidden' not in body
    assert 'data-shift-reload' in body
    assert 'action="/terminal/shifts/' not in body
    assert '<div class="app" inert aria-hidden="true">' in body


def terminal_shift_routes() -> dict[str, object]:
    return {
        route.path: route
        for route in app.routes
        if route.path.startswith("/terminal/shifts")
    }


def test_terminal_shift_routes_are_registered(connection):
    routes = terminal_shift_routes()

    assert set(routes) == {
        "/terminal/shifts/start",
        "/terminal/shifts/current/number",
        "/terminal/shifts/current/end",
    }
    assert routes["/terminal/shifts/start"].endpoint.__name__ == "start_terminal_shift"
    assert (
        routes["/terminal/shifts/current/number"].endpoint.__name__
        == "change_terminal_shift_number"
    )
    assert routes["/terminal/shifts/current/end"].endpoint.__name__ == "end_terminal_shift"
    assert all(route.methods == {"POST"} for route in routes.values())


def test_no_active_shift_context_is_blocking_gate(connection):
    context = terminal_context()

    assert context["shift_configuration"] == {"shift_count": 4, "version": 1}
    assert context["active_shift"] is None
    assert context["shift_options"] == [1, 2, 3, 4]
    assert context["suggested_shift_number"] == 1
    assert context["completed_shifts"] == []
    assert context["selected_shift_summary"] is None
    assert context["shift_window_state"] == "gate"
    assert context["shift_blocking"] is True


def test_shift_display_helpers_convert_utc_to_sofia_without_raw_seconds():
    assert main_module.format_shift_datetime("2026-07-26 18:30:59") == (
        "26 юли 2026, 21:30"
    )
    assert main_module.format_shift_datetime("2026-01-26 19:30:59") == (
        "26 януари 2026, 21:30"
    )
    assert main_module.format_shift_datetime(None) == "-"
    assert main_module.format_shift_datetime("not-a-timestamp") == "-"

    display = main_module.build_shift_display(
        {
            "id": 8,
            "shift_number": 2,
            "started_at": "2026-07-26 18:30:59",
            "ended_at": "2026-07-27 03:05:02",
            "total_gross_weight": "550.00",
            "orders": [
                {
                    "card_id": 11,
                    "order_number": "26001",
                    "customer": "Клиент",
                    "product_type": "Фолио",
                    "roll_count": 2,
                    "gross_weight": "550.00",
                }
            ],
        }
    )

    assert display["started_at_display"] == "26 юли 2026, 21:30"
    assert display["ended_at_display"] == "27 юли 2026, 06:05"
    assert display["total_gross_weight_display"] == "550.0"
    assert display["orders"][0]["gross_weight_display"] == "550.0"


def test_shift_context_exposes_five_recent_rows_and_ten_row_history_pages():
    completed = [
        {
            "id": shift_id,
            "shift_number": ((shift_id - 1) % 4) + 1,
            "started_at": f"2026-07-{shift_id:02d} 06:00:00",
            "ended_at": f"2026-07-{shift_id:02d} 14:00:00",
            "distinct_item_count": 0,
            "roll_count": 0,
            "total_gross_weight": "0.00",
        }
        for shift_id in range(12, 0, -1)
    ]
    state = {
        "configuration": {"shift_count": 4, "version": 1},
        "active_shift": {
            "id": 5,
            "shift_number": 1,
            "started_at": "2026-07-26 18:30:59",
            "ended_at": None,
            "version": 1,
        },
        "suggested_shift_number": 2,
        "completed_shifts": completed,
    }

    context = main_module.build_terminal_shift_context(
        "history",
        None,
        None,
        "2",
        state=state,
    )

    assert context["shift_window_state"] == "history"
    assert context["shift_blocking"] is False
    assert [row["id"] for row in context["recent_completed_shifts"]] == [12, 11, 10, 9, 8]
    assert [row["id"] for row in context["history_shifts"]] == [2, 1]
    assert context["shift_history_page"] == 2
    assert context["shift_history_page_count"] == 2
    assert context["shift_history_page_numbers"] == [1, 2]
    assert context["shift_history_has_previous"] is True
    assert context["shift_history_has_next"] is False
    assert context["active_shift"]["started_at_display"] == (
        "26 юли 2026, 21:30"
    )


def test_shift_history_page_is_clamped_to_available_pages():
    completed = [
        {
            "id": shift_id,
            "shift_number": 1,
            "started_at": "2026-07-25 06:00:00",
            "ended_at": "2026-07-25 14:00:00",
            "distinct_item_count": 0,
            "roll_count": 0,
            "total_gross_weight": "0.00",
        }
        for shift_id in range(11, 0, -1)
    ]
    state = {
        "configuration": {"shift_count": 4, "version": 1},
        "active_shift": {
            "id": 12,
            "shift_number": 2,
            "started_at": "2026-07-26 18:30:59",
            "ended_at": None,
            "version": 1,
        },
        "suggested_shift_number": 3,
        "completed_shifts": completed,
    }

    context = main_module.build_terminal_shift_context(
        "history",
        None,
        None,
        "999",
        state=state,
    )

    assert context["shift_history_page"] == 2
    assert [row["id"] for row in context["history_shifts"]] == [1]


def test_start_uses_configured_choice_and_explicit_confirmation(connection):
    configuration = db.fetch_terminal_configuration()
    assert db.update_shift_count(int(configuration["version"]), "3").ok
    context_before_confirmation = terminal_context()

    assert context_before_confirmation["active_shift"] is None
    assert context_before_confirmation["shift_options"] == [1, 2, 3]

    status, headers, _ = asyncio.run(
        post_form(
            "/terminal/shifts/start",
            {
                "shift_number": "3",
                "configuration_version": str(
                    context_before_confirmation["shift_configuration"]["version"]
                ),
                "selected_card_id": "not-a-card-id",
            },
        )
    )

    assert status == 303
    assert headers["location"] == "/terminal"
    active_shift = db.fetch_active_shift()
    assert active_shift is not None
    assert active_shift["shift_number"] == 3


def test_number_change_updates_same_occurrence_and_preserves_selected_card(connection):
    card_id = release_ready_card("SR-002")
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("4", int(configuration["version"])).ok
    active_before = db.fetch_active_shift()
    assert active_before is not None
    assert db.update_shift_count(int(configuration["version"]), "3").ok

    reduced_context = terminal_context(selected_card_id=card_id, shift_view="overview")
    assert reduced_context["shift_options"] == [1, 2, 3, 4]
    card_before = db.fetch_terminal_card_detail(card_id)

    status, headers, _ = asyncio.run(
        post_form(
            "/terminal/shifts/current/number",
            {
                "shift_occurrence_id": str(active_before["id"]),
                "loaded_version": str(active_before["version"]),
                "shift_number": "2",
                "selected_card_id": str(card_id),
            },
        )
    )

    active_after = db.fetch_active_shift()
    card_after = db.fetch_terminal_card_detail(card_id)
    assert status == 303
    assert headers["location"] == (
        f"/terminal/cards/{card_id}?shift_view=overview&notice=shift_changed"
    )
    assert active_after is not None
    assert active_after["id"] == active_before["id"]
    assert active_after["shift_number"] == 2
    assert active_after["version"] == int(active_before["version"]) + 1
    assert card_after["status"] == card_before["status"]
    assert card_after["version"] == card_before["version"]


def test_rendered_shift_state_and_initial_signature_share_one_snapshot(
    connection,
    monkeypatch,
):
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("1", int(configuration["version"])).ok
    rendered_shift = db.fetch_active_shift()
    assert rendered_shift is not None
    expected_signature = (
        f"configuration:{configuration['version']}:{configuration['shift_count']}"
        f"||active:{rendered_shift['id']}:1:1:{rendered_shift['started_at']}"
    )
    original_snapshot = db.terminal_snapshot
    writer_ran = False

    def interleaving_snapshot(selected_card_id=None, **kwargs):
        nonlocal writer_ran
        assert writer_ran is False
        writer_ran = True
        changed = db.update_active_shift_number(
            int(rendered_shift["id"]),
            int(rendered_shift["version"]),
            "2",
        )
        assert changed.ok
        return original_snapshot(selected_card_id, **kwargs)

    monkeypatch.setattr(main_module, "fetch_terminal_snapshot", interleaving_snapshot)

    context = main_module.terminal_context(shift_view="overview")

    assert writer_ran is True
    assert context["active_shift"]["shift_number"] == 1
    assert context["terminal_snapshot"]["shift_signature"] == expected_signature
    assert db.fetch_active_shift()["shift_number"] == 2


def test_end_redirects_to_just_completed_blocking_summary(connection):
    card_id = release_ready_card("SR-003")
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("1", int(configuration["version"])).ok
    active_shift = db.fetch_active_shift()
    assert active_shift is not None
    card_before = db.fetch_terminal_card_detail(card_id)

    status, headers, _ = asyncio.run(
        post_form(
            "/terminal/shifts/current/end",
            {
                "shift_occurrence_id": str(active_shift["id"]),
                "loaded_version": str(active_shift["version"]),
                "selected_card_id": str(card_id),
            },
        )
    )

    assert status == 303
    assert headers["location"] == (
        f"/terminal/cards/{card_id}?shift_view=summary"
        f"&shift_id={active_shift['id']}&handoff=1"
    )
    assert db.fetch_active_shift() is None
    ended = db.fetch_shift_summary(int(active_shift["id"]))
    assert ended is not None
    assert ended["ended_at"] is not None
    summary_context = terminal_context(
        selected_card_id=card_id,
        shift_view="summary",
        shift_id=str(active_shift["id"]),
        handoff="1",
    )
    assert summary_context["selected_shift_summary"]["id"] == active_shift["id"]
    assert summary_context["shift_window_state"] == "summary"
    assert summary_context["shift_blocking"] is True
    card_after = db.fetch_terminal_card_detail(card_id)
    assert card_after["status"] == card_before["status"]
    assert card_after["version"] == card_before["version"]
    assert card_after["timing_segments"] == card_before["timing_segments"]
    assert card_after["roll_entries"] == card_before["roll_entries"]


def test_terminal_timing_start_rechecks_shift_inside_write_transaction(
    connection,
    monkeypatch,
):
    card_id = release_ready_card("SR-RACE")
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("1", int(configuration["version"])).ok
    loaded_version = int(db.fetch_terminal_card_detail(card_id)["version"])
    original_validation = main_module.validate_terminal_card_available_for_post

    def end_shift_after_route_validation(validated_card_id: int):
        result = original_validation(validated_card_id)
        assert result.ok
        active = db.fetch_active_shift()
        assert active is not None
        assert db.end_shift(int(active["id"]), int(active["version"])).ok
        return result

    monkeypatch.setattr(
        main_module,
        "validate_terminal_card_available_for_post",
        end_shift_after_route_validation,
    )

    status, _, body = asyncio.run(
        post_form(
            f"/terminal/cards/{card_id}/timing/start",
            {"loaded_version": str(loaded_version)},
        )
    )

    card = db.fetch_terminal_card_detail(card_id)
    assert status == 200
    assert db.NO_ACTIVE_SHIFT_MESSAGE in body
    assert card["status"] == "pending"
    assert card["version"] == loaded_version
    assert card["timing_segments"] == []
    assert db.fetch_active_shift() is None


def test_summary_acknowledgment_returns_to_no_active_gate(connection):
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("1", int(configuration["version"])).ok
    active_shift = db.fetch_active_shift()
    assert active_shift is not None
    assert db.end_shift(int(active_shift["id"]), int(active_shift["version"])).ok

    handoff = terminal_context(
        shift_view="summary",
        shift_id=str(active_shift["id"]),
        handoff="1",
    )
    acknowledged = terminal_context()
    summary_without_handoff = terminal_context(
        shift_view="summary",
        shift_id=str(active_shift["id"]),
    )

    assert handoff["shift_window_state"] == "summary"
    assert handoff["shift_blocking"] is True
    assert acknowledged["shift_window_state"] == "gate"
    assert acknowledged["shift_blocking"] is True
    assert summary_without_handoff["shift_window_state"] == "gate"
    assert summary_without_handoff["shift_blocking"] is True


def test_history_summary_and_back_use_the_same_window_state(connection):
    configuration = db.fetch_terminal_configuration()
    assert db.start_shift("1", int(configuration["version"])).ok
    completed = db.fetch_active_shift()
    assert completed is not None
    assert db.end_shift(int(completed["id"]), int(completed["version"])).ok
    current_configuration = db.fetch_terminal_configuration()
    assert db.start_shift("2", int(current_configuration["version"])).ok

    overview = terminal_context(shift_view="overview")
    history = terminal_context(shift_view="history")
    summary = terminal_context(shift_view="summary", shift_id=str(completed["id"]))
    back = terminal_context(shift_view="overview")
    closed = terminal_context()
    normalized_invalid_request = terminal_context(
        shift_view="not-a-window",
        shift_id="not-a-shift-id",
        handoff="1",
    )

    assert overview["shift_window_state"] == "overview"
    assert overview["shift_blocking"] is False
    assert history["shift_window_state"] == "history"
    assert history["shift_blocking"] is False
    assert history["recent_completed_shifts"] == history["completed_shifts"][:5]
    assert summary["shift_window_state"] == "summary"
    assert summary["shift_blocking"] is False
    assert summary["selected_shift_summary"]["id"] == completed["id"]
    assert back["shift_window_state"] == "overview"
    assert back["active_shift"]["id"] == overview["active_shift"]["id"]
    assert back["completed_shifts"] == overview["completed_shifts"]
    assert closed["shift_window_state"] == "closed"
    assert closed["shift_blocking"] is False
    assert normalized_invalid_request["shift_window_state"] == "closed"
    assert normalized_invalid_request["selected_shift_summary"] is None


def test_stale_shift_lifecycle_posts_block_controls_until_canonical_get(connection):
    initial_configuration = db.fetch_terminal_configuration()
    assert db.update_shift_count(int(initial_configuration["version"]), "3").ok

    stale_start_status, _, stale_start_body = asyncio.run(
        post_form(
            "/terminal/shifts/start",
            {
                "shift_number": "1",
                "configuration_version": str(initial_configuration["version"]),
            },
        )
    )

    assert stale_start_status == 200
    assert_blocking_shift_reload(stale_start_body)
    assert db.fetch_active_shift() is None
    gate_status, gate_body = asyncio.run(get_page("/terminal"))
    assert gate_status == 200
    assert 'data-shift-state="gate"' in gate_body
    assert 'action="/terminal/shifts/start"' in gate_body

    current_configuration = db.fetch_terminal_configuration()
    assert db.start_shift("1", int(current_configuration["version"])).ok
    first_version = db.fetch_active_shift()
    assert first_version is not None
    assert db.update_active_shift_number(
        int(first_version["id"]),
        int(first_version["version"]),
        "2",
    ).ok

    stale_change_status, _, stale_change_body = asyncio.run(
        post_form(
            "/terminal/shifts/current/number",
            {
                "shift_occurrence_id": str(first_version["id"]),
                "loaded_version": str(first_version["version"]),
                "shift_number": "3",
            },
        )
    )

    assert stale_change_status == 200
    assert_blocking_shift_reload(stale_change_body)
    current_shift = db.fetch_active_shift()
    assert current_shift is not None
    assert current_shift["shift_number"] == 2
    overview_status, overview_body = asyncio.run(
        get_page("/terminal", "shift_view=overview")
    )
    assert overview_status == 200
    assert 'data-shift-state="overview"' in overview_body
    assert 'action="/terminal/shifts/current/number"' in overview_body
    assert 'action="/terminal/shifts/current/end"' in overview_body

    assert db.update_active_shift_number(
        int(current_shift["id"]),
        int(current_shift["version"]),
        "3",
    ).ok
    stale_end_status, _, stale_end_body = asyncio.run(
        post_form(
            "/terminal/shifts/current/end",
            {
                "shift_occurrence_id": str(current_shift["id"]),
                "loaded_version": str(current_shift["version"]),
            },
        )
    )

    assert stale_end_status == 200
    assert_blocking_shift_reload(stale_end_body)
    latest_shift = db.fetch_active_shift()
    assert latest_shift is not None
    assert latest_shift["shift_number"] == 3
    canonical_status, canonical_body = asyncio.run(
        get_page("/terminal", "shift_view=overview")
    )
    assert canonical_status == 200
    assert 'data-shift-state="overview"' in canonical_body
    assert 'action="/terminal/shifts/current/end"' in canonical_body


def test_terminal_normal_posts_are_blocked_without_active_shift(connection):
    card_id = release_ready_card("SR-004")
    version = int(db.fetch_terminal_card_detail(card_id)["version"])
    mutations = [
        (f"/terminal/cards/{card_id}/materials", {"loaded_version": str(version)}),
        (
            f"/terminal/cards/{card_id}/tare",
            {"loaded_version": str(version), "tare_weight": "1.25"},
        ),
        (
            f"/terminal/cards/{card_id}/rolls",
            {"loaded_version": str(version), "gross_weight": "50"},
        ),
        (
            f"/terminal/cards/{card_id}/rolls/corrections",
            {"loaded_version": str(version)},
        ),
        (
            f"/terminal/cards/{card_id}/rolls/999",
            {"loaded_version": str(version), "gross_weight": "50"},
        ),
        (
            f"/terminal/cards/{card_id}/rolls/999/delete",
            {"loaded_version": str(version), "confirm_roll_number": "1"},
        ),
        (
            f"/terminal/cards/{card_id}/rolls/actions/delete-selected",
            {
                "loaded_version": str(version),
                "roll_id": "999",
                "confirm_roll_number": "1",
            },
        ),
        (f"/terminal/cards/{card_id}/timing/start", {"loaded_version": str(version)}),
        (f"/terminal/cards/{card_id}/timing/pause", {"loaded_version": str(version)}),
        (f"/terminal/cards/{card_id}/timing/resume", {"loaded_version": str(version)}),
        (f"/terminal/cards/{card_id}/finish", {"loaded_version": str(version)}),
    ]
    before = db.fetch_terminal_card_detail(card_id)

    responses = [asyncio.run(post_form(path, data)) for path, data in mutations]

    assert all(status == 200 for status, _, _ in responses)
    responses_missing_gate_message = [
        path
        for (path, _), (_, _, body) in zip(mutations, responses, strict=True)
        if db.NO_ACTIVE_SHIFT_MESSAGE not in body
    ]
    assert responses_missing_gate_message == []
    after = db.fetch_terminal_card_detail(card_id)
    assert after["status"] == before["status"]
    assert after["version"] == before["version"]
    assert after["tare_weight"] == before["tare_weight"]
    assert after["timing_segments"] == before["timing_segments"]
    assert after["roll_entries"] == before["roll_entries"]


def test_shift_routes_do_not_expose_time_edit_cancel_admin_review_or_report_actions(
    connection,
):
    routes = terminal_shift_routes()
    forbidden_action_words = (
        "time",
        "edit",
        "cancel",
        "admin",
        "review",
        "report",
    )

    assert set(routes) == {
        "/terminal/shifts/start",
        "/terminal/shifts/current/number",
        "/terminal/shifts/current/end",
    }
    assert all(
        forbidden not in route_path
        for route_path in routes
        for forbidden in forbidden_action_words
    )
