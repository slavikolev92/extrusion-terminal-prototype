from __future__ import annotations

import asyncio

from app.main import admin, app


def test_admin_routes_are_registered():
    route_paths = {route.path for route in app.routes}

    assert "/admin" in route_paths
    assert "/admin/import" in route_paths
    assert "/admin/planning" in route_paths


def test_admin_redirects_to_import():
    response = asyncio.run(admin())

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/import"
