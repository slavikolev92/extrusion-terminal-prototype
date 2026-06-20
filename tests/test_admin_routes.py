from __future__ import annotations

import asyncio
from tempfile import SpooledTemporaryFile

from starlette.datastructures import UploadFile
from starlette.requests import Request

from app import db
from app.importer import import_cards_from_csv
from app.main import (
    admin,
    admin_card_detail,
    admin_import,
    admin_planning,
    app,
    import_csv as post_admin_import,
    release_card_to_terminal,
    sorted_draft_cards,
    unrelease_admin_card,
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
    assert "/admin/cards/{card_id}/unrelease" in route_paths
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


def assert_html_order(html: str, *needles: str) -> None:
    positions = [html.index(needle) for needle in needles]
    assert positions == sorted(positions)


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


def test_admin_planning_renders_compact_unreleased_release_table(connection):
    result = import_cards_from_csv(
        "planning-compact-route.csv",
        csv_bytes(
            extrusion_row(
                "25902",
                delivery_date="2026-06-25",
                customer="Compact Customer",
                product_type="Long product type that should stay in the product column",
            ),
            extrusion_row(
                "25903",
                delivery_date="2026-06-26",
                customer="Second Compact Customer",
                product_type="Second product",
            ),
        ),
        overwrite_existing=False,
    )
    assert result.rows_imported == 2

    response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert '<section class="section" id="unreleased-queue">' in html
    assert '<th class="col-order" aria-sort="ascending">' in html
    assert 'href="/admin/planning?draft_sort=order_number&amp;draft_dir=desc#unreleased-queue"' in html
    assert 'href="/admin/planning?draft_sort=delivery_date&amp;draft_dir=asc#unreleased-queue"' in html
    assert 'href="/admin/planning?draft_sort=customer&amp;draft_dir=asc#unreleased-queue"' in html
    assert 'href="/admin/planning?draft_sort=product_type&amp;draft_dir=asc#unreleased-queue"' in html
    assert ">Поръчка" in html
    assert ">Доставка" in html
    assert ">Клиент" in html
    assert ">Изделие" in html
    assert '<th class="col-max-roll">Макс. кг/ролка</th>' in html
    assert '<th class="col-sequence">Ред</th>' in html
    assert '<th class="col-machine">Машина</th>' in html
    assert '<th class="col-action">Действие</th>' in html
    assert "2026-06-25" in html
    assert "2026-06-26" in html
    assert 'id="draft-card-' in html
    assert 'class="unreleased-table compact-table"' in html
    assert 'class="release-control release-control-max-roll"' in html
    assert 'class="release-control release-control-sequence"' in html
    assert 'class="release-control release-control-machine"' in html
    assert 'class="release-submit-button"' in html
    assert 'name="return_anchor" value="draft-card-' in html
    assert 'name="return_anchor" value="unreleased-queue"' in html
    assert '<span>Макс. тегло ролка, кг</span>' not in html
    assert '<span>Ред <span class="required-marker">*</span></span>' not in html
    assert '<span>Машина <span class="required-marker">*</span></span>' not in html


def test_admin_planning_sorts_unreleased_cards_with_header_links(connection):
    result = import_cards_from_csv(
        "planning-sort-route.csv",
        csv_bytes(
            extrusion_row(
                "25941",
                delivery_date="2026-06-22",
                customer="Beta Customer",
                product_type="Zeta Product",
            ),
            extrusion_row(
                "25940",
                delivery_date="2026-06-21",
                customer="Alpha Customer",
                product_type="Omega Product",
            ),
            extrusion_row(
                "25942",
                delivery_date="2026-06-20",
                customer="Gamma Customer",
                product_type="Alpha Product",
            ),
        ),
        overwrite_existing=False,
    )
    assert result.rows_imported == 3

    customer_response = asyncio.run(
        admin_planning(
            make_request("/admin/planning", method="GET"),
            draft_sort="customer",
            draft_dir="asc",
        )
    )
    customer_html = customer_response.body.decode("utf-8")

    assert customer_response.status_code == 200
    assert_html_order(customer_html, "25940", "25941", "25942")
    assert 'href="/admin/planning?draft_sort=customer&amp;draft_dir=desc#unreleased-queue"' in customer_html
    assert 'aria-sort="ascending"' in customer_html

    delivery_response = asyncio.run(
        admin_planning(
            make_request("/admin/planning", method="GET"),
            draft_sort="delivery_date",
            draft_dir="desc",
        )
    )
    delivery_html = delivery_response.body.decode("utf-8")

    assert delivery_response.status_code == 200
    assert_html_order(delivery_html, "25941", "25940", "25942")
    assert 'href="/admin/planning?draft_sort=delivery_date&amp;draft_dir=asc#unreleased-queue"' in delivery_html
    assert 'aria-sort="descending"' in delivery_html


def test_admin_planning_delivery_date_sort_keeps_missing_dates_last():
    cards = [
        {"id": 1, "order_number": "25961", "delivery_date": "2026-06-21"},
        {"id": 2, "order_number": "25962", "delivery_date": ""},
        {"id": 3, "order_number": "25963", "delivery_date": "2026-06-20"},
        {"id": 4, "order_number": "25964", "delivery_date": None},
        {"id": 5, "order_number": "25965", "delivery_date": "22/06/2026"},
    ]

    ascending = sorted_draft_cards(cards, "delivery_date", "asc")
    descending = sorted_draft_cards(cards, "delivery_date", "desc")

    assert [card["order_number"] for card in ascending] == [
        "25963",
        "25961",
        "25965",
        "25962",
        "25964",
    ]
    assert [card["order_number"] for card in descending] == [
        "25965",
        "25961",
        "25963",
        "25962",
        "25964",
    ]


def test_admin_planning_ignores_invalid_unreleased_sort_values(connection):
    result = import_cards_from_csv(
        "planning-invalid-sort-route.csv",
        csv_bytes(
            extrusion_row("25951", customer="First Customer"),
            extrusion_row("25950", customer="Second Customer"),
        ),
        overwrite_existing=False,
    )
    assert result.rows_imported == 2

    response = asyncio.run(
        admin_planning(
            make_request("/admin/planning", method="GET"),
            draft_sort='customer" onclick="alert(1)',
            draft_dir="sideways",
        )
    )
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert_html_order(html, "25950", "25951")
    assert 'onclick="alert(1)' not in html
    assert 'draft_dir=sideways' not in html


def test_successful_release_redirects_to_planning_anchor_and_refresh_does_not_resubmit(connection):
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
            return_anchor="draft-card-999",
        )
    )
    after_release = db.fetch_admin_card_detail(card_id)
    refresh_response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    after_refresh = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/planning#draft-card-999"
    assert refresh_response.status_code == 200
    assert after_release["status"] == "pending"
    assert after_release["machine_id"] == 1
    assert after_release["machine_sequence"] == 1
    assert after_refresh["version"] == after_release["version"]
    assert after_refresh["machine_id"] == 1
    assert after_refresh["machine_sequence"] == 1


def test_successful_release_ignores_unsafe_return_anchor(connection):
    card_id = import_route_card("25913")
    loaded_version = card_version(card_id)

    response = asyncio.run(
        release_card_to_terminal(
            make_request(f"/admin/cards/{card_id}/release"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            max_roll_weight="60.0",
            machine_id="1",
            machine_sequence="1",
            return_anchor='draft-card-1" onclick="alert(1)',
        )
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/planning#unreleased-queue"


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


def test_successful_unrelease_from_planning_redirects_to_planning_get_and_refresh_does_not_resubmit(connection):
    card_id = import_route_card("25920")
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    loaded_version = card_version(card_id)

    response = asyncio.run(
        unrelease_admin_card(
            make_request(f"/admin/cards/{card_id}/unrelease"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            return_to="planning",
        )
    )
    after_unrelease = db.fetch_admin_card_detail(card_id)
    refresh_response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    after_refresh = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/planning"
    assert refresh_response.status_code == 200
    assert after_unrelease["status"] == "imported"
    assert after_unrelease["machine_id"] is None
    assert after_unrelease["machine_sequence"] is None
    assert after_refresh["version"] == after_unrelease["version"]
    assert after_refresh["status"] == "imported"


def test_successful_unrelease_from_detail_redirects_to_card_detail(connection):
    card_id = import_route_card("25921")
    assert db.release_card(
        card_id,
        machine_id=2,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    loaded_version = card_version(card_id)

    response = asyncio.run(
        unrelease_admin_card(
            make_request(f"/admin/cards/{card_id}/unrelease"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            return_to="detail",
        )
    )
    card = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/cards/{card_id}"
    assert card["status"] == "imported"
    assert card["machine_id"] is None
    assert card["machine_sequence"] is None


def test_failed_unrelease_from_planning_renders_planning_inline(connection):
    card_id = import_route_card("25922")
    assert db.release_card(
        card_id,
        machine_id=3,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.25").ok

    response = asyncio.run(
        unrelease_admin_card(
            make_request(f"/admin/cards/{card_id}/unrelease"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            return_to="planning",
        )
    )
    card = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 200
    assert "location" not in response.headers
    assert "planning_result" in response.context
    assert response.context["planning_result"].messages == (db.STALE_CARD_MESSAGE,)
    assert card["status"] == "pending"
    assert card["machine_id"] == 3
    assert card["machine_sequence"] == 1


def test_failed_unrelease_from_detail_renders_detail_inline(connection):
    card_id = import_route_card("25923")
    assert db.release_card(
        card_id,
        machine_id=4,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    loaded_version = card_version(card_id)
    assert db.start_production_timing(card_id, loaded_version).ok

    response = asyncio.run(
        unrelease_admin_card(
            make_request(f"/admin/cards/{card_id}/unrelease"),
            card_id=card_id,
            loaded_version=str(card_version(card_id)),
            return_to="detail",
        )
    )
    card = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 200
    assert "location" not in response.headers
    assert "workflow_result" in response.context
    assert response.context["workflow_result"].messages == (
        "Само изчакващи технологични карти могат да се връщат за планиране.",
    )
    assert card["status"] == "running"
    assert card["machine_id"] == 4
    assert card["machine_sequence"] == 1


def test_admin_planning_renders_unrelease_form_for_pending_queue_cards_only(connection):
    pending_id = import_route_card("25924")
    running_id = import_route_card("25925")
    assert db.release_card(
        pending_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(pending_id),
        max_roll_weight="60.0",
    ).ok
    assert db.release_card(
        running_id,
        machine_id=1,
        machine_sequence=2,
        loaded_version=card_version(running_id),
        max_roll_weight="60.0",
    ).ok
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert f'action="/admin/cards/{pending_id}/unrelease"' in html
    assert f'action="/admin/cards/{running_id}/unrelease"' not in html
    assert '<input type="hidden" name="return_to" value="planning">' in html
    assert 'class="queue-card-header"' in html
    assert 'class="queue-return-form"' in html
    assert 'class="queue-return-button"' in html
    assert 'aria-label="Върни поръчка 25924 в неизпратени"' in html
    assert ">↩ Върни</button>" in html
    assert "Върни в неизпратени" not in html
    assert "4 машини в системата" not in html
    assert '<span class="planning-field-label">Машина</span>' in html
    assert '<span class="planning-field-label">Ред</span>' in html


def test_admin_detail_renders_unrelease_form_for_pending_card_only(connection):
    pending_id = import_route_card("25926")
    running_id = import_route_card("25927")
    imported_id = import_route_card("25928")
    assert db.release_card(
        pending_id,
        machine_id=2,
        machine_sequence=1,
        loaded_version=card_version(pending_id),
        max_roll_weight="60.0",
    ).ok
    assert db.release_card(
        running_id,
        machine_id=2,
        machine_sequence=2,
        loaded_version=card_version(running_id),
        max_roll_weight="60.0",
    ).ok
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    pending_response = asyncio.run(
        admin_card_detail(make_request(f"/admin/cards/{pending_id}", method="GET"), pending_id)
    )
    running_response = asyncio.run(
        admin_card_detail(make_request(f"/admin/cards/{running_id}", method="GET"), running_id)
    )
    imported_response = asyncio.run(
        admin_card_detail(make_request(f"/admin/cards/{imported_id}", method="GET"), imported_id)
    )

    pending_html = pending_response.body.decode("utf-8")
    running_html = running_response.body.decode("utf-8")
    imported_html = imported_response.body.decode("utf-8")

    assert f'action="/admin/cards/{pending_id}/unrelease"' in pending_html
    assert '<input type="hidden" name="return_to" value="detail">' in pending_html
    assert "Върни в планиране" in pending_html
    assert f'action="/admin/cards/{running_id}/unrelease"' not in running_html
    assert f'action="/admin/cards/{imported_id}/unrelease"' not in imported_html
