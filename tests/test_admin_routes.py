from __future__ import annotations

import asyncio

from app.main import admin, app


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
