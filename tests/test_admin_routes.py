from __future__ import annotations

import asyncio

from starlette.requests import Request

from app.importer import import_cards_from_csv
from app.main import admin, admin_planning, app
from tests.test_admin_planning import csv_bytes, extrusion_row


def test_admin_routes_are_registered():
    route_paths = {route.path for route in app.routes}

    assert "/admin" in route_paths
    assert "/admin/import" in route_paths
    assert "/admin/planning" in route_paths
    assert "/admin/cards" in route_paths
    assert "/admin/cards/{card_id}" in route_paths
    assert "/admin/cards/{card_id}/imported-fields" in route_paths
    assert "/admin/cards/{card_id}/planning" in route_paths
    assert "/admin/cards/{card_id}/delete" in route_paths
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


def test_workstation_cancel_restore_routes_are_not_registered():
    route_paths = {route.path for route in app.routes}

    assert "/admin/cards/{card_id}/cancel" in route_paths
    assert "/admin/cards/{card_id}/restore" in route_paths
    assert "/terminal/cards/{card_id}/cancel" not in route_paths
    assert "/terminal/cards/{card_id}/restore" not in route_paths


def test_admin_redirects_to_import():
    response = asyncio.run(admin())

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/import"


def test_admin_planning_renders_unreleased_cards_and_machine_options(connection):
    result = import_cards_from_csv(
        "planning-route.csv",
        csv_bytes(extrusion_row("25900")),
        overwrite_existing=False,
    )
    assert result.rows_imported == 1

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/admin/planning",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
            "app": app,
        }
    )
    response = asyncio.run(admin_planning(request))

    assert response.status_code == 200
    page = response.body.decode("utf-8")
    assert "25900" in page
    for machine_id in range(1, 5):
        assert f'<option value="{machine_id}"' in page
        assert f"Машина {machine_id}" in page
