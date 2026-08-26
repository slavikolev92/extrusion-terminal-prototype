from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
from zoneinfo import ZoneInfo

import pytest
from starlette.requests import Request

from app import db, main
from app.constants import STATUS_AWAITING_REWINDING, STATUS_COMPLETED
from app.main import app
from app.production_dashboard import (
    build_machine_time_dashboard,
    normalize_dimensions,
    parse_dashboard_day,
)


REFERENCE_TIME = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
DAY_SELECTION_REFERENCE_TIME = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)


def insert_card(
    connection: sqlite3.Connection,
    *,
    order_number: str,
    machine_id: int,
    status: str,
    first_started_at: str,
    finished_at: str | None = None,
    customer: str = "Клиент",
    size_thickness: str = "400/0.050",
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO cards (
            order_number, status, machine_id, customer, size_thickness,
            first_started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_number,
            status,
            machine_id,
            customer,
            size_thickness,
            first_started_at,
            finished_at,
        ),
    )
    return int(cursor.lastrowid)


def insert_segment(
    connection: sqlite3.Connection,
    *,
    card_id: int,
    started_at: str,
    ended_at: str | None,
    end_reason: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO production_time_segments (
            card_id, started_at, ended_at, end_reason
        )
        VALUES (?, ?, ?, ?)
        """,
        (card_id, started_at, ended_at, end_reason),
    )


def insert_roll(
    connection: sqlite3.Connection,
    *,
    card_id: int,
    order_number: str,
    roll_number: int,
    net_weight: str,
) -> None:
    connection.execute(
        """
        INSERT INTO roll_entries (
            card_id, order_number, roll_number, gross_weight, tare_weight,
            net_weight
        )
        VALUES (?, ?, ?, ?, 0, ?)
        """,
        (card_id, order_number, roll_number, net_weight, net_weight),
    )


def machine(dashboard: dict[str, object], machine_id: int) -> dict[str, object]:
    return next(
        row
        for row in dashboard["machines"]
        if row["id"] == machine_id
    )


def make_request(path: str, method: str = "GET") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
            "app": app,
        }
    )


def stored(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def test_dashboard_day_parser_accepts_only_completed_iso_dates():
    assert parse_dashboard_day(None, DAY_SELECTION_REFERENCE_TIME) is None
    assert parse_dashboard_day("", DAY_SELECTION_REFERENCE_TIME) is None
    assert parse_dashboard_day("2026-08-24", DAY_SELECTION_REFERENCE_TIME) == date(
        2026, 8, 24
    )

    for value in ("24-08-2026", "20260824", "not-a-date", "2026-08-25", "2026-08-26"):
        with pytest.raises(ValueError):
            parse_dashboard_day(value, DAY_SELECTION_REFERENCE_TIME)


def test_admin_dashboard_redirects_unrepresentable_lower_bound_day(connection, monkeypatch):
    monkeypatch.setattr("app.main.datetime", FixedDateTime)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/admin/dashboard")

    with pytest.raises(ValueError):
        parse_dashboard_day("0001-01-01", DAY_SELECTION_REFERENCE_TIME)
    response = asyncio.run(
        endpoint(make_request("/admin/dashboard?day=0001-01-01"), day="0001-01-01")
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/dashboard"


def test_selected_sofia_day_has_local_midnight_bounds(connection):
    dashboard = build_machine_time_dashboard(
        DAY_SELECTION_REFERENCE_TIME,
        selected_day=date(2026, 8, 24),
    )

    assert dashboard["window"] == {
        "mode": "calendar_day",
        "selected_day": "2026-08-24",
        "max_selectable_day": "2026-08-24",
        "start_utc": "2026-08-23T21:00:00Z",
        "end_utc": "2026-08-24T21:00:00Z",
        "seconds": 86_400,
        "range_display": "24 авг. 00:00 – 25 авг. 00:00",
    }
    assert dashboard["axis"][0]["display"] == "00:00"
    assert dashboard["axis"][-1]["display"] == "00:00"
    assert dashboard["axis"][0]["position"] == 0
    assert dashboard["axis"][-1]["position"] == 100


@pytest.mark.parametrize(
    (
        "selected_day",
        "expected_start",
        "expected_end",
        "expected_seconds",
        "activity_start",
        "activity_end",
        "internal_axis_position",
        "active_percent",
    ),
    [
        (
            date(2026, 3, 29),
            "2026-03-28T22:00:00Z",
            "2026-03-29T21:00:00Z",
            23 * 3600,
            "2026-03-29 03:00:00",
            "2026-03-29 06:00:00",
            47.82608695652174,
            13,
        ),
        (
            date(2026, 10, 25),
            "2026-10-24T21:00:00Z",
            "2026-10-25T22:00:00Z",
            25 * 3600,
            "2026-10-25 03:00:00",
            "2026-10-25 06:00:00",
            52.0,
            12,
        ),
    ],
)
def test_selected_day_uses_real_dst_duration(
    connection,
    selected_day,
    expected_start,
    expected_end,
    expected_seconds,
    activity_start,
    activity_end,
    internal_axis_position,
    active_percent,
):
    reference = datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc)
    card_id = insert_card(
        connection,
        order_number="DST-ACTIVITY",
        machine_id=1,
        status="completed",
        first_started_at=activity_start,
        finished_at=activity_end,
    )
    insert_segment(
        connection,
        card_id=card_id,
        started_at=activity_start,
        ended_at=activity_end,
        end_reason="finish",
    )
    connection.commit()

    dashboard = build_machine_time_dashboard(reference, selected_day=selected_day)

    assert dashboard["window"]["start_utc"] == expected_start
    assert dashboard["window"]["end_utc"] == expected_end
    assert dashboard["window"]["seconds"] == expected_seconds
    assert dashboard["axis"][0]["position"] == 0
    assert dashboard["axis"][-1]["position"] == 100
    assert dashboard["axis"][4]["position"] == pytest.approx(internal_axis_position)
    machine_one = machine(dashboard, 1)
    assert sum(interval["duration_seconds"] for interval in machine_one["timeline"]) == expected_seconds
    assert machine_one["active_seconds"] == 3 * 3600
    assert machine_one["active_percent"] == active_percent


def test_fall_back_interval_tooltip_times_include_distinct_utc_offsets(connection):
    card_id = insert_card(
        connection,
        order_number="DST-FOLD",
        machine_id=1,
        status="completed",
        first_started_at="2026-10-25 00:30:00",
        finished_at="2026-10-25 01:30:00",
    )
    insert_segment(
        connection,
        card_id=card_id,
        started_at="2026-10-25 00:30:00",
        ended_at="2026-10-25 01:30:00",
        end_reason="finish",
    )
    connection.commit()

    dashboard = build_machine_time_dashboard(
        datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc),
        selected_day=date(2026, 10, 25),
    )

    order_interval = next(
        interval
        for interval in machine(dashboard, 1)["timeline"]
        if interval["kind"] == "order"
    )
    assert order_interval["start_display"] == "03:30 (UTC+03:00)"
    assert order_interval["end_display"] == "03:30 (UTC+02:00)"


def test_selected_day_clips_timeline_but_keeps_complete_order_productivity(connection):
    card_id = insert_card(
        connection,
        order_number="BOUNDARY-100",
        machine_id=1,
        status="completed",
        first_started_at="2026-08-24 20:00:00",
        finished_at="2026-08-24 22:00:00",
    )
    insert_segment(
        connection,
        card_id=card_id,
        started_at="2026-08-24 20:00:00",
        ended_at="2026-08-24 22:00:00",
        end_reason="finish",
    )
    insert_roll(
        connection,
        card_id=card_id,
        order_number="BOUNDARY-100",
        roll_number=1,
        net_weight="200",
    )
    connection.commit()

    dashboard = build_machine_time_dashboard(
        DAY_SELECTION_REFERENCE_TIME,
        selected_day=date(2026, 8, 24),
    )

    machine_one = machine(dashboard, 1)
    order_interval = next(
        interval
        for interval in machine_one["timeline"]
        if interval["kind"] == "order"
    )
    productivity = next(
        row
        for row in machine_one["orders"]
        if row["order_number"] == "BOUNDARY-100"
    )
    assert order_interval["start_utc"] == "2026-08-24T20:00:00Z"
    assert order_interval["end_utc"] == "2026-08-24T21:00:00Z"
    assert order_interval["duration_seconds"] == 60 * 60
    assert productivity["active_seconds"] == 2 * 60 * 60
    assert productivity["produced"] == 200
    assert productivity["productivity"] == 100


def test_dashboard_builds_clipped_order_pause_and_idle_intervals(connection):
    card_id = insert_card(
        connection,
        order_number="M1-ORDER",
        machine_id=1,
        status="completed",
        first_started_at="2026-08-23 11:00:00",
        finished_at="2026-08-23 16:00:00",
        customer="Дълъг клиент",
    )
    insert_segment(
        connection,
        card_id=card_id,
        started_at="2026-08-23 11:00:00",
        ended_at="2026-08-23 12:00:00",
        end_reason="pause",
    )
    insert_segment(
        connection,
        card_id=card_id,
        started_at="2026-08-23 13:00:00",
        ended_at="2026-08-23 16:00:00",
        end_reason="finish",
    )
    connection.commit()

    dashboard = build_machine_time_dashboard(REFERENCE_TIME)

    assert dashboard["window"]["seconds"] == 24 * 60 * 60
    assert [row["id"] for row in dashboard["machines"]] == [1, 2, 3, 4]
    machine_one = machine(dashboard, 1)
    assert [interval["kind"] for interval in machine_one["timeline"]] == [
        "idle",
        "order",
        "pause",
        "order",
        "idle",
    ]
    assert [interval["duration_seconds"] for interval in machine_one["timeline"]] == [
        60 * 60,
        60 * 60,
        60 * 60,
        3 * 60 * 60,
        18 * 60 * 60,
    ]
    assert machine_one["active_seconds"] == 4 * 60 * 60
    assert machine_one["active_percent"] == 17
    assert machine_one["timeline"][1]["order_number"] == "M1-ORDER"
    assert machine_one["timeline"][1]["customer"] == "Дълъг клиент"


def test_dashboard_clips_open_running_and_paused_cards_at_reference_time(connection):
    running_id = insert_card(
        connection,
        order_number="M2-RUNNING",
        machine_id=2,
        status="running",
        first_started_at="2026-08-24 09:00:00",
    )
    insert_segment(
        connection,
        card_id=running_id,
        started_at="2026-08-24 09:00:00",
        ended_at=None,
    )
    paused_id = insert_card(
        connection,
        order_number="M3-PAUSED",
        machine_id=3,
        status="paused",
        first_started_at="2026-08-24 07:00:00",
    )
    insert_segment(
        connection,
        card_id=paused_id,
        started_at="2026-08-24 07:00:00",
        ended_at="2026-08-24 08:00:00",
        end_reason="pause",
    )
    connection.commit()

    dashboard = build_machine_time_dashboard(REFERENCE_TIME)

    machine_two = machine(dashboard, 2)
    assert [part["kind"] for part in machine_two["timeline"]] == ["idle", "order"]
    assert machine_two["timeline"][-1]["duration_seconds"] == 60 * 60
    assert machine_two["timeline"][-1]["end_display"] == "13:00"

    machine_three = machine(dashboard, 3)
    assert [part["kind"] for part in machine_three["timeline"]] == [
        "idle",
        "order",
        "pause",
    ]
    assert machine_three["timeline"][-1]["duration_seconds"] == 2 * 60 * 60
    assert machine_three["timeline"][-1]["start_display"] == "11:00"
    assert machine_three["timeline"][-1]["end_display"] == "13:00"


def test_running_order_takes_precedence_over_another_cards_overlapping_pause(connection):
    paused_card_id = insert_card(
        connection,
        order_number="PAUSED-ORDER",
        machine_id=1,
        status="completed",
        first_started_at="2026-08-24 04:00:00",
        finished_at="2026-08-24 09:00:00",
    )
    insert_segment(
        connection,
        card_id=paused_card_id,
        started_at="2026-08-24 04:00:00",
        ended_at="2026-08-24 05:00:00",
        end_reason="pause",
    )
    insert_segment(
        connection,
        card_id=paused_card_id,
        started_at="2026-08-24 08:00:00",
        ended_at="2026-08-24 09:00:00",
        end_reason="finish",
    )
    running_card_id = insert_card(
        connection,
        order_number="ORDER-DURING-PAUSE",
        machine_id=1,
        status="completed",
        first_started_at="2026-08-24 06:00:00",
        finished_at="2026-08-24 07:00:00",
    )
    insert_segment(
        connection,
        card_id=running_card_id,
        started_at="2026-08-24 06:00:00",
        ended_at="2026-08-24 07:00:00",
        end_reason="finish",
    )
    connection.commit()

    dashboard = build_machine_time_dashboard(REFERENCE_TIME)

    timeline = machine(dashboard, 1)["timeline"]
    assert [part["kind"] for part in timeline] == [
        "idle",
        "order",
        "pause",
        "order",
        "pause",
        "order",
        "idle",
    ]
    assert [
        part.get("order_number")
        for part in timeline
        if part["kind"] == "order"
    ] == ["PAUSED-ORDER", "ORDER-DURING-PAUSE", "PAUSED-ORDER"]
    assert sum(
        part["duration_seconds"]
        for part in timeline
        if part["kind"] == "order"
    ) == 3 * 60 * 60


def test_dashboard_uses_sofia_axis_and_full_idle_machine(connection):
    dashboard = build_machine_time_dashboard(REFERENCE_TIME)

    assert [tick["display"] for tick in dashboard["axis"]] == [
        "13:00",
        "16:00",
        "19:00",
        "22:00",
        "01:00",
        "04:00",
        "07:00",
        "10:00",
        "13:00",
    ]
    assert dashboard["window"]["range_display"] == (
        "23 авг. 13:00 – 24 авг. 13:00"
    )
    machine_four = machine(dashboard, 4)
    assert machine_four["active_seconds"] == 0
    assert machine_four["active_percent"] == 0
    assert len(machine_four["timeline"]) == 1
    assert machine_four["timeline"][0]["kind"] == "idle"
    assert machine_four["timeline"][0]["duration_seconds"] == 24 * 60 * 60


def test_dimension_matching_is_numeric_exact_and_rejects_malformed_values():
    assert normalize_dimensions("400/0.050") == normalize_dimensions("400 / 0,05")
    assert normalize_dimensions("400/0.050") != normalize_dimensions("401/0.050")
    assert normalize_dimensions("not-a-size") is None
    assert normalize_dimensions("") is None


def test_productivity_uses_complete_order_and_prior_exact_machine_history(connection):
    historical_values = [
        ("HIST-50", 1, "400/0.050", "2026-08-20 08:00:00", "2026-08-20 10:00:00", "100"),
        ("HIST-60", 1, "400 / 0,05", "2026-08-21 08:00:00", "2026-08-21 10:00:00", "120"),
        ("OTHER-MACHINE", 2, "400/0.050", "2026-08-21 08:00:00", "2026-08-21 10:00:00", "140"),
        ("OTHER-SIZE", 1, "401/0.050", "2026-08-21 08:00:00", "2026-08-21 10:00:00", "160"),
    ]
    for order, machine_id, dimensions, started, finished, net_weight in historical_values:
        card_id = insert_card(
            connection,
            order_number=order,
            machine_id=machine_id,
            status="completed",
            first_started_at=started,
            finished_at=finished,
            size_thickness=dimensions,
        )
        insert_segment(
            connection,
            card_id=card_id,
            started_at=started,
            ended_at=finished,
            end_reason="finish",
        )
        insert_roll(
            connection,
            card_id=card_id,
            order_number=order,
            roll_number=1,
            net_weight=net_weight,
        )

    current_id = insert_card(
        connection,
        order_number="CURRENT-100",
        machine_id=1,
        status="completed",
        first_started_at="2026-08-24 08:00:00",
        finished_at="2026-08-24 09:00:00",
        customer="Текущ клиент",
        size_thickness="400/0,050",
    )
    insert_segment(
        connection,
        card_id=current_id,
        started_at="2026-08-24 08:00:00",
        ended_at="2026-08-24 09:00:00",
        end_reason="finish",
    )
    insert_roll(
        connection,
        card_id=current_id,
        order_number="CURRENT-100",
        roll_number=1,
        net_weight="100",
    )

    later_id = insert_card(
        connection,
        order_number="LATER-80",
        machine_id=1,
        status="completed",
        first_started_at="2026-08-24 09:15:00",
        finished_at="2026-08-24 09:45:00",
        size_thickness="400/0.050",
    )
    insert_segment(
        connection,
        card_id=later_id,
        started_at="2026-08-24 09:15:00",
        ended_at="2026-08-24 09:45:00",
        end_reason="finish",
    )
    insert_roll(
        connection,
        card_id=later_id,
        order_number="LATER-80",
        roll_number=1,
        net_weight="40",
    )
    connection.commit()

    dashboard = build_machine_time_dashboard(REFERENCE_TIME)

    rows = machine(dashboard, 1)["orders"]
    current = next(row for row in rows if row["order_number"] == "CURRENT-100")
    assert current["dimensions"] == "400 × 0.050"
    assert current["produced"] == 100
    assert current["active_seconds"] == 60 * 60
    assert current["productivity"] == 100
    assert current["baseline"]["sample_count"] == 2
    assert current["baseline"]["minimum"] == 50
    assert current["baseline"]["maximum"] == 60
    assert [sample["order_number"] for sample in current["baseline"]["samples"]] == [
        "HIST-60",
        "HIST-50",
    ]
    assert current["baseline"]["marker_position"] > current["baseline"]["range_end"]


def test_zero_net_order_keeps_produced_amount_but_has_no_productivity(connection):
    card_id = insert_card(
        connection,
        order_number="ZERO-NET-CURRENT",
        machine_id=1,
        status="completed",
        first_started_at="2026-08-24 08:00:00",
        finished_at="2026-08-24 09:00:00",
    )
    insert_segment(
        connection,
        card_id=card_id,
        started_at="2026-08-24 08:00:00",
        ended_at="2026-08-24 09:00:00",
        end_reason="finish",
    )
    insert_roll(
        connection,
        card_id=card_id,
        order_number="ZERO-NET-CURRENT",
        roll_number=1,
        net_weight="0",
    )
    connection.commit()

    dashboard = build_machine_time_dashboard(REFERENCE_TIME)

    current = machine(dashboard, 1)["orders"][0]
    assert current["produced"] == 0
    assert current["productivity"] is None
    assert current["baseline"] is None


def test_zero_net_history_is_excluded_from_productivity_baseline(connection):
    historical_values = [
        ("POSITIVE-HISTORY", "2026-08-20 08:00:00", "2026-08-20 09:00:00", "50"),
        ("ZERO-NET-HISTORY", "2026-08-21 08:00:00", "2026-08-21 09:00:00", "0"),
    ]
    for order_number, started_at, finished_at, net_weight in historical_values:
        card_id = insert_card(
            connection,
            order_number=order_number,
            machine_id=1,
            status="completed",
            first_started_at=started_at,
            finished_at=finished_at,
        )
        insert_segment(
            connection,
            card_id=card_id,
            started_at=started_at,
            ended_at=finished_at,
            end_reason="finish",
        )
        insert_roll(
            connection,
            card_id=card_id,
            order_number=order_number,
            roll_number=1,
            net_weight=net_weight,
        )

    current_id = insert_card(
        connection,
        order_number="CURRENT-WITH-HISTORY",
        machine_id=1,
        status="completed",
        first_started_at="2026-08-24 08:00:00",
        finished_at="2026-08-24 09:00:00",
    )
    insert_segment(
        connection,
        card_id=current_id,
        started_at="2026-08-24 08:00:00",
        ended_at="2026-08-24 09:00:00",
        end_reason="finish",
    )
    insert_roll(
        connection,
        card_id=current_id,
        order_number="CURRENT-WITH-HISTORY",
        roll_number=1,
        net_weight="100",
    )
    connection.commit()

    dashboard = build_machine_time_dashboard(REFERENCE_TIME)

    current = next(
        row
        for row in machine(dashboard, 1)["orders"]
        if row["order_number"] == "CURRENT-WITH-HISTORY"
    )
    assert current["baseline"]["sample_count"] == 1
    assert current["baseline"]["minimum"] == 50
    assert current["baseline"]["maximum"] == 50
    assert [sample["order_number"] for sample in current["baseline"]["samples"]] == [
        "POSITIVE-HISTORY"
    ]


def test_productivity_baseline_handles_zero_one_and_latest_seven_samples(connection):
    for index in range(1, 10):
        order = f"HIST-{index}"
        day = index
        started = f"2026-08-{day:02d} 08:00:00"
        finished = f"2026-08-{day:02d} 09:00:00"
        card_id = insert_card(
            connection,
            order_number=order,
            machine_id=1,
            status="completed",
            first_started_at=started,
            finished_at=finished,
            size_thickness="450/0.060",
        )
        insert_segment(
            connection,
            card_id=card_id,
            started_at=started,
            ended_at=finished,
            end_reason="finish",
        )
        insert_roll(
            connection,
            card_id=card_id,
            order_number=order,
            roll_number=1,
            net_weight=str(40 + index),
        )

    one_history_id = insert_card(
        connection,
        order_number="ONE-HISTORY",
        machine_id=2,
        status="completed",
        first_started_at="2026-08-20 08:00:00",
        finished_at="2026-08-20 09:00:00",
        size_thickness="420/0.060",
    )
    insert_segment(
        connection,
        card_id=one_history_id,
        started_at="2026-08-20 08:00:00",
        ended_at="2026-08-20 09:00:00",
        end_reason="finish",
    )
    insert_roll(
        connection,
        card_id=one_history_id,
        order_number="ONE-HISTORY",
        roll_number=1,
        net_weight="36",
    )

    recent_specs = [
        ("NINE-CURRENT", 1, "450/0.060", "90"),
        ("ONE-CURRENT", 2, "420/0.060", "76"),
        ("ZERO-CURRENT", 3, "590/0.150", "64"),
    ]
    for order, machine_id, dimensions, net_weight in recent_specs:
        card_id = insert_card(
            connection,
            order_number=order,
            machine_id=machine_id,
            status="completed",
            first_started_at="2026-08-24 08:00:00",
            finished_at="2026-08-24 09:00:00",
            size_thickness=dimensions,
        )
        insert_segment(
            connection,
            card_id=card_id,
            started_at="2026-08-24 08:00:00",
            ended_at="2026-08-24 09:00:00",
            end_reason="finish",
        )
        insert_roll(
            connection,
            card_id=card_id,
            order_number=order,
            roll_number=1,
            net_weight=net_weight,
        )
    connection.commit()

    dashboard = build_machine_time_dashboard(REFERENCE_TIME)

    nine = machine(dashboard, 1)["orders"][0]
    assert nine["baseline"]["sample_count"] == 9
    assert len(nine["baseline"]["samples"]) == 7
    assert [sample["order_number"] for sample in nine["baseline"]["samples"]] == [
        "HIST-9",
        "HIST-8",
        "HIST-7",
        "HIST-6",
        "HIST-5",
        "HIST-4",
        "HIST-3",
    ]

    one = machine(dashboard, 2)["orders"][0]
    assert one["baseline"]["sample_count"] == 1
    assert one["baseline"]["minimum"] == 36
    assert one["baseline"]["maximum"] == 36
    assert one["baseline"]["is_single_sample"] is True

    zero = machine(dashboard, 3)["orders"][0]
    assert zero["baseline"] is None


def test_productivity_baseline_keeps_archived_completed_history(connection):
    archived_id = insert_card(
        connection,
        order_number="ARCHIVED-HISTORY",
        machine_id=1,
        status="archived",
        first_started_at="2026-08-20 08:00:00",
        finished_at="2026-08-20 09:00:00",
        size_thickness="400/0.050",
    )
    insert_segment(
        connection,
        card_id=archived_id,
        started_at="2026-08-20 08:00:00",
        ended_at="2026-08-20 09:00:00",
        end_reason="finish",
    )
    insert_roll(
        connection,
        card_id=archived_id,
        order_number="ARCHIVED-HISTORY",
        roll_number=1,
        net_weight="50",
    )
    current_id = insert_card(
        connection,
        order_number="CURRENT-AFTER-ARCHIVE",
        machine_id=1,
        status="completed",
        first_started_at="2026-08-24 08:00:00",
        finished_at="2026-08-24 09:00:00",
        size_thickness="400/0.050",
    )
    insert_segment(
        connection,
        card_id=current_id,
        started_at="2026-08-24 08:00:00",
        ended_at="2026-08-24 09:00:00",
        end_reason="finish",
    )
    insert_roll(
        connection,
        card_id=current_id,
        order_number="CURRENT-AFTER-ARCHIVE",
        roll_number=1,
        net_weight="75",
    )
    connection.commit()

    dashboard = build_machine_time_dashboard(REFERENCE_TIME)

    current = machine(dashboard, 1)["orders"][0]
    assert current["baseline"]["sample_count"] == 1
    assert current["baseline"]["samples"][0]["order_number"] == "ARCHIVED-HISTORY"


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = DAY_SELECTION_REFERENCE_TIME
        return value if tz is None else value.astimezone(tz)


class IntegrationReferenceDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = REFERENCE_TIME
        return value if tz is None else value.astimezone(tz)


def test_dashboard_route_observes_running_terminal_timing_correction(
    connection,
    active_test_shift,
    monkeypatch,
):
    """Catches the dashboard reading stale card markers instead of the corrected ledger."""

    card_id = insert_card(
        connection,
        order_number="CORRECTED-RUNNING",
        machine_id=1,
        status="running",
        first_started_at="2026-08-24 06:00:00",
    )
    insert_segment(
        connection,
        card_id=card_id,
        started_at="2026-08-24 06:00:00",
        ended_at=None,
    )
    insert_roll(
        connection,
        card_id=card_id,
        order_number="CORRECTED-RUNNING",
        roll_number=1,
        net_weight="90",
    )
    connection.commit()
    segment_id = int(
        connection.execute(
            "SELECT id FROM production_time_segments WHERE card_id = ?",
            (card_id,),
        ).fetchone()["id"]
    )
    loaded_version = int(
        connection.execute(
            "SELECT version FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()["version"]
    )
    draft = json.dumps(
        [
            {
                "segment_id": segment_id,
                "start_date": "2026-08-24",
                "start_time": "11:00",
                "stop_date": "",
                "stop_time": "",
                "deleted": False,
            }
        ]
    )

    correction_response = asyncio.run(
        main.save_terminal_timing_ledger(
            make_request(
                f"/terminal/cards/{card_id}/timing-ledger",
                method="POST",
            ),
            card_id,
            loaded_version=str(loaded_version),
            timing_draft=draft,
        )
    )

    assert correction_response.status_code == 303
    assert correction_response.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=timing_saved"
    )
    corrected_card = db.fetch_admin_card_detail(card_id)
    assert corrected_card is not None
    assert corrected_card["first_started_at"] == "2026-08-24 08:00:00"
    assert corrected_card["timing_segments"] == [
        {
            "id": segment_id,
            "started_at": "2026-08-24 08:00:00",
            "ended_at": None,
            "end_reason": None,
        }
    ]

    monkeypatch.setattr(main, "datetime", IntegrationReferenceDateTime)
    endpoint = next(
        route.endpoint
        for route in app.routes
        if route.path == "/admin/dashboard"
    )
    dashboard_response = asyncio.run(endpoint(make_request("/admin/dashboard")))
    dashboard = dashboard_response.context["dashboard"]
    machine_one = machine(dashboard, 1)
    order_interval = next(
        interval
        for interval in machine_one["timeline"]
        if interval.get("order_number") == "CORRECTED-RUNNING"
    )
    productivity = next(
        row
        for row in machine_one["orders"]
        if row["order_number"] == "CORRECTED-RUNNING"
    )

    assert dashboard_response.status_code == 200
    assert order_interval["start_utc"] == "2026-08-24T08:00:00Z"
    assert order_interval["end_utc"] == "2026-08-24T10:00:00Z"
    assert order_interval["duration_seconds"] == 2 * 60 * 60
    assert productivity["active_seconds"] == 2 * 60 * 60
    assert productivity["produced"] == 90
    assert productivity["productivity"] == 45


def test_dashboard_is_timing_neutral_when_corrected_paused_finish_is_finalized(
    connection,
    active_test_shift,
    monkeypatch,
):
    """Catches waiting finalization moving the corrected extrusion ledger or finish time."""

    card_id = insert_card(
        connection,
        order_number="CORRECTED-WAITING",
        machine_id=2,
        status="paused",
        first_started_at="2026-08-24 06:00:00",
    )
    connection.execute(
        "UPDATE cards SET rewinding_roll_count = 1 WHERE id = ?",
        (card_id,),
    )
    insert_segment(
        connection,
        card_id=card_id,
        started_at="2026-08-24 06:00:00",
        ended_at="2026-08-24 06:30:00",
        end_reason="pause",
    )
    connection.commit()
    segment_id = int(
        connection.execute(
            "SELECT id FROM production_time_segments WHERE card_id = ?",
            (card_id,),
        ).fetchone()["id"]
    )
    loaded_version = int(
        connection.execute(
            "SELECT version FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()["version"]
    )

    finish_outcome = db.finish_card_with_timing_ledger(
        card_id,
        loaded_version,
        [
            db.TimingDraftRow(
                segment_id,
                "2026-08-24",
                "10:00",
                "2026-08-24",
                "11:30",
            )
        ],
        "2026-08-24 09:00:00",
    )

    assert finish_outcome.result.ok
    waiting_card = db.fetch_admin_card_detail(card_id)
    assert waiting_card is not None
    assert waiting_card["status"] == STATUS_AWAITING_REWINDING
    assert waiting_card["first_started_at"] == "2026-08-24 07:00:00"
    assert waiting_card["finished_at"] == "2026-08-24 08:30:00"
    assert waiting_card["timing_segments"] == [
        {
            "id": segment_id,
            "started_at": "2026-08-24 07:00:00",
            "ended_at": "2026-08-24 08:30:00",
            "end_reason": "pause",
        }
    ]
    assert db.update_tare_weight(card_id, int(waiting_card["version"]), "1.00").ok
    waiting_card = db.fetch_admin_card_detail(card_id)
    assert waiting_card is not None
    assert db.add_roll_gross_weight(card_id, int(waiting_card["version"]), "101.00").ok
    waiting_card = db.fetch_admin_card_detail(card_id)
    assert waiting_card is not None

    monkeypatch.setattr(main, "datetime", IntegrationReferenceDateTime)
    endpoint = next(
        route.endpoint
        for route in app.routes
        if route.path == "/admin/dashboard"
    )
    before_response = asyncio.run(endpoint(make_request("/admin/dashboard")))
    before_machine = machine(before_response.context["dashboard"], 2)
    before_interval = next(
        interval
        for interval in before_machine["timeline"]
        if interval.get("order_number") == "CORRECTED-WAITING"
    )
    before_productivity = next(
        row
        for row in before_machine["orders"]
        if row["order_number"] == "CORRECTED-WAITING"
    )
    before_timing = waiting_card["timing_segments"]
    before_finished_at = waiting_card["finished_at"]

    finalization_response = asyncio.run(
        main.finish_terminal_card(
            make_request(f"/terminal/cards/{card_id}/finish", method="POST"),
            card_id,
            loaded_version=str(waiting_card["version"]),
        )
    )
    completed_card = db.fetch_admin_card_detail(card_id)
    assert completed_card is not None
    after_response = asyncio.run(endpoint(make_request("/admin/dashboard")))
    after_machine = machine(after_response.context["dashboard"], 2)
    after_interval = next(
        interval
        for interval in after_machine["timeline"]
        if interval.get("order_number") == "CORRECTED-WAITING"
    )
    after_productivity = next(
        row
        for row in after_machine["orders"]
        if row["order_number"] == "CORRECTED-WAITING"
    )

    assert finalization_response.status_code == 303
    assert completed_card["status"] == STATUS_COMPLETED
    assert completed_card["finished_at"] == before_finished_at
    assert completed_card["timing_segments"] == before_timing
    assert before_interval == after_interval
    assert before_productivity == after_productivity
    assert after_interval["start_utc"] == "2026-08-24T07:00:00Z"
    assert after_interval["end_utc"] == "2026-08-24T08:30:00Z"
    assert after_productivity["active_seconds"] == 90 * 60
    assert after_productivity["produced"] == 100
    assert after_productivity["productivity"] == 67


def test_admin_dashboard_renders_selected_day_control(connection, monkeypatch):
    monkeypatch.setattr("app.main.datetime", FixedDateTime)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/admin/dashboard")

    response = asyncio.run(
        endpoint(make_request("/admin/dashboard?day=2026-08-24"), day="2026-08-24")
    )
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert 'action="/admin/dashboard"' in html
    assert 'method="get"' in html
    assert 'type="date"' in html
    assert 'name="day"' in html
    assert 'value="2026-08-24"' in html
    assert 'max="2026-08-24"' in html
    assert "Избран ден" in html
    assert 'data-dashboard-window-reset' in html


def test_admin_dashboard_date_control_requires_explicit_submit(connection, monkeypatch):
    monkeypatch.setattr("app.main.datetime", FixedDateTime)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/admin/dashboard")

    response = asyncio.run(endpoint(make_request("/admin/dashboard")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert 'class="dashboard-day-submit"' in html
    assert 'type="submit"' in html
    assert 'data-dashboard-day-submit' in html
    assert ">Покажи</button>" in html
    assert 'dayInput.addEventListener("change"' not in html


def test_admin_dashboard_prefills_latest_complete_day_in_rolling_mode(
    connection,
    monkeypatch,
):
    monkeypatch.setattr("app.main.datetime", FixedDateTime)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/admin/dashboard")

    response = asyncio.run(endpoint(make_request("/admin/dashboard")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "Последни 24 часа" in html
    assert 'value="2026-08-24"' in html
    assert 'data-dashboard-window-reset' not in html


@pytest.mark.parametrize("day", ["bad", "2026-08-25", "2026-08-26"])
def test_admin_dashboard_rejects_invalid_or_incomplete_day(connection, monkeypatch, day):
    monkeypatch.setattr("app.main.datetime", FixedDateTime)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/admin/dashboard")

    response = asyncio.run(endpoint(make_request("/admin/dashboard"), day=day))

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/dashboard"


def test_admin_dashboard_route_renders_approved_read_only_surface(connection):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    historical_start = now - timedelta(days=3, hours=1)
    historical_end = now - timedelta(days=3)
    historical_id = insert_card(
        connection,
        order_number="HIST-ROUTE",
        machine_id=1,
        status="completed",
        first_started_at=stored(historical_start),
        finished_at=stored(historical_end),
        customer="Исторически клиент",
        size_thickness="400/0.050",
    )
    insert_segment(
        connection,
        card_id=historical_id,
        started_at=stored(historical_start),
        ended_at=stored(historical_end),
        end_reason="finish",
    )
    insert_roll(
        connection,
        card_id=historical_id,
        order_number="HIST-ROUTE",
        roll_number=1,
        net_weight="50",
    )

    current_start = now - timedelta(hours=2)
    current_end = now - timedelta(hours=1)
    current_id = insert_card(
        connection,
        order_number="CURRENT-ROUTE",
        machine_id=1,
        status="completed",
        first_started_at=stored(current_start),
        finished_at=stored(current_end),
        customer="Много дълго име на клиент за проверка на съкращаването",
        size_thickness="400/0,050",
    )
    insert_segment(
        connection,
        card_id=current_id,
        started_at=stored(current_start),
        ended_at=stored(current_end),
        end_reason="finish",
    )
    insert_roll(
        connection,
        card_id=current_id,
        order_number="CURRENT-ROUTE",
        roll_number=1,
        net_weight="100",
    )
    connection.commit()

    endpoint = next(route.endpoint for route in app.routes if route.path == "/admin/dashboard")
    response = asyncio.run(endpoint(make_request("/admin/dashboard")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "Производствено време по машини" in html
    assert html.count('data-machine-row="') == 4
    assert html.count('class="productivity-machine-group"') == 4
    assert 'data-kind="order"' in html
    assert 'data-kind="idle"' in html
    assert "CURRENT-ROUTE" in html
    assert "400 × 0.050" in html
    assert 'class="productivity-gauge is-single-sample"' in html
    assert 'data-sample-count="1"' in html
    assert 'href="/admin/dashboard"' in html
    latest_complete_day = (
        now.astimezone(ZoneInfo("Europe/Sofia")).date() - timedelta(days=1)
    )
    assert f'value="{latest_complete_day.isoformat()}"' in html
    assert "Последни 24 часа" in html
    assert 'data-dashboard-window-reset' not in html
    assert 'class="refresh-button" type="button">Обнови</button>' in html
    assert "Размер" in html and "(мм)" in html
    assert "Произведено" in html and "(кг)" in html
    assert "Производителност" in html and "(кг/ч)" in html
    assert "Обновено" not in html
    assert "Нетна производителност" not in html
    assert "Какво е стандарт" not in html
    assert "<dialog" not in html
