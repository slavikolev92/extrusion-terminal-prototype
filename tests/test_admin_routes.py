from __future__ import annotations

import asyncio
from tempfile import SpooledTemporaryFile

from starlette.datastructures import UploadFile
from starlette.requests import Request

from app import db
from app.importer import import_cards_from_csv
from app.main import (
    admin,
    admin_import,
    admin_planning,
    app,
    import_csv as post_admin_import,
    release_card_to_terminal,
    update_admin_card_planning,
)
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


def make_request(path: str, method: str = "POST") -> Request:
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


def upload_file(filename: str, content: bytes) -> UploadFile:
    file = SpooledTemporaryFile()
    file.write(content)
    file.seek(0)
    return UploadFile(file=file, filename=filename)


def import_route_card(order_number: str) -> int:
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


def card_version(card_id: int) -> int:
    return int(db.fetch_admin_card_detail(card_id)["version"])


def test_successful_admin_import_redirects_to_batch_result_get(connection):
    content = csv_bytes(
        extrusion_row("25901"),
        extrusion_row(
            "31999",
            extrusion_flag="не",
            raw_material_a="",
            packaging_method="",
        ),
    )

    response = asyncio.run(
        post_admin_import(
            make_request("/admin/import"),
            csv_file=upload_file("route-import.csv", content),
            overwrite_existing=False,
        )
    )

    batches_after_post = connection.execute(
        "SELECT COUNT(*) FROM import_batches"
    ).fetchone()[0]
    location = response.headers.get("location", "")
    batch_id = int(location.rsplit("=", 1)[1])
    persisted_result = db.fetch_import_batch_result(batch_id)

    get_response = asyncio.run(
        admin_import(
            make_request("/admin/import", method="GET"),
            batch_id=batch_id,
        )
    )
    refresh_response = asyncio.run(
        admin_import(
            make_request("/admin/import", method="GET"),
            batch_id=batch_id,
        )
    )
    batches_after_get_refresh = connection.execute(
        "SELECT COUNT(*) FROM import_batches"
    ).fetchone()[0]
    html = get_response.body.decode("utf-8")

    assert response.status_code == 303
    assert location == f"/admin/import?batch_id={batch_id}"
    assert persisted_result is not None
    assert persisted_result["filename"] == "route-import.csv"
    assert get_response.status_code == 200
    assert refresh_response.status_code == 200
    assert batches_after_post == 1
    assert batches_after_get_refresh == 1
    assert "Резултат от импорта:" in html
    assert "route-import.csv" in html
    assert "25901" in html
    assert "31999" in html
    assert "Пропуснат ред: няма екструдиране." in html


def test_admin_import_without_persisted_batch_still_renders_inline(connection):
    response = asyncio.run(
        post_admin_import(
            make_request("/admin/import"),
            csv_file=upload_file("missing-required.csv", b"order_number\n25902\n"),
            overwrite_existing=False,
        )
    )
    batch_count = connection.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "location" not in response.headers
    assert batch_count == 0
    assert "Липсват задължителни CSV колони" in html


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


def test_successful_release_redirects_to_planning_get_and_refresh_does_not_resubmit(connection):
    card_id = import_route_card("25910")
    loaded_version = card_version(card_id)

    response = asyncio.run(
        release_card_to_terminal(
            make_request(f"/admin/cards/{card_id}/release"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            max_roll_weight="60.0",
            machine_id="1",
            machine_sequence="1",
        )
    )
    after_release = db.fetch_admin_card_detail(card_id)
    refresh_response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    after_refresh = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/planning"
    assert refresh_response.status_code == 200
    assert after_release["status"] == "pending"
    assert after_release["machine_id"] == 1
    assert after_release["machine_sequence"] == 1
    assert after_refresh["version"] == after_release["version"]
    assert after_refresh["machine_id"] == 1
    assert after_refresh["machine_sequence"] == 1


def test_successful_replanning_redirects_to_planning_get_and_refresh_does_not_resubmit(connection):
    card_id = import_route_card("25911")
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    loaded_version = card_version(card_id)

    response = asyncio.run(
        update_admin_card_planning(
            make_request(f"/admin/cards/{card_id}/planning"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            machine_id="2",
            machine_sequence="1",
        )
    )
    after_planning = db.fetch_admin_card_detail(card_id)
    refresh_response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    after_refresh = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/planning"
    assert refresh_response.status_code == 200
    assert after_planning["machine_id"] == 2
    assert after_planning["machine_sequence"] == 1
    assert after_refresh["version"] == after_planning["version"]
    assert after_refresh["machine_id"] == 2
    assert after_refresh["machine_sequence"] == 1


def test_failed_release_and_planning_still_render_inline_without_redirect(connection):
    card_id = import_route_card("25912")
    stale_version = card_version(card_id)
    fields = {
        field: str(db.fetch_admin_card_detail(card_id)[field] or "")
        for field in db.CARD_IMPORT_SOURCE_FIELDS
    }
    fields["customer"] = "Changed Before Release"
    assert db.update_admin_imported_fields(card_id, stale_version, fields).ok

    stale_release = asyncio.run(
        release_card_to_terminal(
            make_request(f"/admin/cards/{card_id}/release"),
            card_id=card_id,
            loaded_version=str(stale_version),
            max_roll_weight="60.0",
            machine_id="1",
            machine_sequence="1",
        )
    )
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    invalid_planning = asyncio.run(
        update_admin_card_planning(
            make_request(f"/admin/cards/{card_id}/planning"),
            card_id=card_id,
            loaded_version=str(card_version(card_id)),
            machine_id="1",
            machine_sequence="0",
        )
    )

    assert stale_release.status_code == 200
    assert "location" not in stale_release.headers
    assert "release_result" in stale_release.context
    assert stale_release.context["release_result"].messages == (db.STALE_CARD_MESSAGE,)
    assert invalid_planning.status_code == 200
    assert "location" not in invalid_planning.headers
    assert "planning_result" in invalid_planning.context
    assert invalid_planning.context["planning_result"].messages == (
        "Редът трябва да е 1 или по-голям.",
    )
