from __future__ import annotations

import asyncio
import re
from pathlib import Path
from tempfile import SpooledTemporaryFile

from starlette.datastructures import UploadFile
from starlette.requests import Request

from app import db
from app.importer import import_cards_from_csv
from app.main import (
    admin,
    admin_cards,
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
    assert "/admin/cards/{card_id}/save-all" in route_paths
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


def test_admin_settings_routes_are_registered_without_admin_shift_operations():
    route_paths = {route.path for route in app.routes}

    assert "/admin/settings" in route_paths
    assert "/admin/settings/shifts" in route_paths
    assert "/admin/shifts/start" not in route_paths
    assert "/admin/shifts/end" not in route_paths
    assert "/admin/shifts/history" not in route_paths
    assert "/admin/shifts/corrections" not in route_paths


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


def test_admin_import_explains_overwrite_scope(connection):
    response = asyncio.run(admin_import(make_request("/admin/import", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "Обнови импортните/лицеви полета за съществуващи поръчки със същия номер" in html
    assert "Запазва ролки, шпула, времена и операторски данни." in html
    assert "По-стари CSV редове, които биха заменили админ корекции, се блокират за преглед." in html


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


def admin_route_endpoint(path: str):
    return next(route.endpoint for route in app.routes if route.path == path)


def upload_file(filename: str, content: bytes) -> UploadFile:
    file = SpooledTemporaryFile()
    file.write(content)
    file.seek(0)
    return UploadFile(file=file, filename=filename)


def import_route_card(order_number: str, **overrides: str) -> int:
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


def card_version(card_id: int) -> int:
    return int(db.fetch_admin_card_detail(card_id)["version"])


def assert_html_order(html: str, *needles: str) -> None:
    positions = [html.index(needle) for needle in needles]
    assert positions == sorted(positions)


def assert_admin_global_nav(html: str, active_label: str) -> None:
    assert "/static/css/app.css?v=admin-nav-underline" in html
    assert 'class="admin-header"' in html
    assert 'aria-label="Admin navigation"' in html
    assert "/static/images/kolev-logo.png" in html
    assert 'href="/admin/import"' in html
    assert 'href="/admin/planning"' in html
    assert 'href="/admin/cards"' in html
    assert 'href="/admin/settings"' in html
    assert 'href="/terminal"' in html
    assert "Терминал" in html
    assert f'aria-current="page">{active_label}</a>' in html
    assert "Началник смяна" not in html
    assert '<a class="nav-link" href="/terminal">Терминал</a>' not in html
    assert "Terminal" not in html
    assert "Към терминала" not in html


def test_admin_nav_active_underline_is_direct_border_style():
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")

    assert "border-bottom: 3px solid transparent;" in css
    assert ".admin-nav-link.is-active {" in css
    assert "border-bottom-color: var(--admin-nav-accent);" in css


def test_admin_import_uses_shared_global_navigation(connection):
    response = asyncio.run(admin_import(make_request("/admin/import", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert_admin_global_nav(html, "Импорт")
    assert "Импорт от CSV" in html


def test_admin_planning_uses_shared_global_navigation(connection):
    response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert_admin_global_nav(html, "Планиране")
    assert "Неизпратени технологични карти" in html


def test_admin_cards_list_uses_shared_global_navigation(connection):
    response = asyncio.run(
        admin_cards(
            make_request("/admin/cards", method="GET"),
            order_number="",
            customer="",
            product="",
            status="",
        )
    )
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert_admin_global_nav(html, "Технологични карти")
    assert "Търсене на технологични карти" in html


def test_admin_settings_page_uses_shared_nav_and_renders_current_count(connection):
    route_paths = {route.path for route in app.routes}
    assert "/admin/settings" in route_paths
    response = asyncio.run(
        admin_route_endpoint("/admin/settings")(make_request("/admin/settings", method="GET"))
    )
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert_admin_global_nav(html, "Настройки")
    assert "Настройки на терминала" in html
    assert 'name="shift_count"' in html
    assert 'value="4"' in html
    assert 'name="loaded_version"' in html
    assert 'value="1"' in html
    assert 'inputmode="numeric"' in html


def test_admin_settings_post_redirects_after_valid_update(connection):
    configuration = db.fetch_terminal_configuration()
    route_paths = {route.path for route in app.routes}
    assert "/admin/settings/shifts" in route_paths

    response = asyncio.run(
        admin_route_endpoint("/admin/settings/shifts")(
            make_request("/admin/settings/shifts"),
            shift_count="3",
            loaded_version=int(configuration["version"]),
        )
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/settings?notice=shift_count_saved"
    assert db.fetch_terminal_configuration()["shift_count"] == 3


def test_admin_settings_invalid_or_stale_post_renders_error_without_write(connection):
    initial = db.fetch_terminal_configuration()
    route_paths = {route.path for route in app.routes}
    assert "/admin/settings/shifts" in route_paths

    invalid_response = asyncio.run(
        admin_route_endpoint("/admin/settings/shifts")(
            make_request("/admin/settings/shifts"),
            shift_count="0",
            loaded_version=int(initial["version"]),
        )
    )
    after_invalid = db.fetch_terminal_configuration()
    assert invalid_response.status_code == 200
    assert "Брой смени трябва да е положително цяло число." in invalid_response.body.decode(
        "utf-8"
    )
    assert after_invalid == initial

    assert db.update_shift_count(int(initial["version"]), "3").ok
    stale_response = asyncio.run(
        admin_route_endpoint("/admin/settings/shifts")(
            make_request("/admin/settings/shifts"),
            shift_count="2",
            loaded_version=int(initial["version"]),
        )
    )
    after_stale = db.fetch_terminal_configuration()

    assert stale_response.status_code == 200
    assert db.STALE_CONFIGURATION_MESSAGE in stale_response.body.decode("utf-8")
    assert after_stale["shift_count"] == 3
    assert after_stale["version"] == int(initial["version"]) + 1


def test_admin_settings_stale_response_requires_reload_before_another_write(connection):
    initial = db.fetch_terminal_configuration()
    assert db.update_shift_count(int(initial["version"]), "3").ok

    stale_response = asyncio.run(
        admin_route_endpoint("/admin/settings/shifts")(
            make_request("/admin/settings/shifts"),
            shift_count="2",
            loaded_version=int(initial["version"]),
        )
    )
    stale_html = stale_response.body.decode("utf-8")
    rendered_version = re.search(
        r'name="loaded_version" value="(\d+)"',
        stale_html,
    )

    assert stale_response.status_code == 200
    assert db.STALE_CONFIGURATION_MESSAGE in stale_html
    assert rendered_version is not None
    assert int(rendered_version.group(1)) == int(initial["version"])
    assert '<button type="submit" disabled>Запази</button>' in stale_html
    assert 'href="/admin/settings">Презареди</a>' in stale_html

    repeated_response = asyncio.run(
        admin_route_endpoint("/admin/settings/shifts")(
            make_request("/admin/settings/shifts"),
            shift_count="2",
            loaded_version=int(rendered_version.group(1)),
        )
    )

    assert repeated_response.status_code == 200
    assert db.STALE_CONFIGURATION_MESSAGE in repeated_response.body.decode("utf-8")
    assert db.fetch_terminal_configuration()["shift_count"] == 3


def test_successful_admin_import_redirects_to_batch_result_get(connection):
    content = csv_bytes(
        extrusion_row("25901"),
        extrusion_row(
            "31999",
            extrusion_sequence="2",
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
    created_card_id = int(
        connection.execute(
            "SELECT id FROM cards WHERE order_number = ?",
            ("25901",),
        ).fetchone()["id"]
    )
    created_row = next(
        row
        for row in persisted_result["row_results"]
        if row["order_number"] == "25901"
    )
    skipped_row = next(
        row
        for row in persisted_result["row_results"]
        if row["order_number"] == "31999"
    )

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
    assert created_row["card_id"] == created_card_id
    assert skipped_row["card_id"] is None
    assert f'<a href="/admin/cards/{created_card_id}">25901</a>' in html
    skipped_cell = html.split(">31999<", 1)[0].rsplit("<td", 1)[-1]
    assert "/admin/cards/" not in skipped_cell


def test_admin_import_result_keeps_deleted_successful_card_as_plain_text(connection):
    result = import_cards_from_csv(
        "deleted-result-card.csv",
        csv_bytes(extrusion_row("25904")),
        overwrite_existing=False,
    )
    assert result.batch_id is not None
    card_id = int(
        connection.execute(
            "SELECT id FROM cards WHERE order_number = ?",
            ("25904",),
        ).fetchone()["id"]
    )
    connection.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    connection.commit()

    persisted = db.fetch_import_batch_result(int(result.batch_id))
    response = asyncio.run(
        admin_import(
            make_request("/admin/import", method="GET"),
            batch_id=int(result.batch_id),
        )
    )
    html = response.body.decode("utf-8")

    assert persisted is not None
    assert persisted["row_results"][0]["card_id"] is None
    assert "25904" in html
    assert f'href="/admin/cards/{card_id}"' not in html


def test_admin_import_result_links_updated_row_to_existing_card(connection):
    first = import_cards_from_csv(
        "updated-row-first.csv",
        csv_bytes(extrusion_row("25905", customer="Before Update")),
        overwrite_existing=False,
    )
    assert first.rows_imported == 1
    card_id = int(
        connection.execute(
            "SELECT id FROM cards WHERE order_number = ?",
            ("25905",),
        ).fetchone()["id"]
    )

    updated = import_cards_from_csv(
        "updated-row-second.csv",
        csv_bytes(extrusion_row("25905", customer="After Update")),
        overwrite_existing=True,
    )
    assert updated.batch_id is not None
    persisted = db.fetch_import_batch_result(int(updated.batch_id))
    response = asyncio.run(
        admin_import(
            make_request("/admin/import", method="GET"),
            batch_id=int(updated.batch_id),
        )
    )
    html = response.body.decode("utf-8")

    assert persisted is not None
    assert persisted["row_results"][0]["action"] == "updated"
    assert persisted["row_results"][0]["card_id"] == card_id
    assert f'<a href="/admin/cards/{card_id}">25905</a>' in html


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
                ordered_gross_kg="725.50",
            ),
            extrusion_row(
                "25903",
                delivery_date="2026-06-26",
                customer="Second Compact Customer",
                product_type="Second product",
                ordered_gross_kg="",
            ),
        ),
        overwrite_existing=False,
    )
    assert result.rows_imported == 2

    response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert '<main class="page wide-page admin-page">' in html
    assert '<table class="planning-table">' in html
    assert ">Ред" in html
    assert ">Поръчка" in html
    assert ">Доставка" in html
    assert ">Клиент" in html
    assert ">Изделие" in html
    assert ">Размер" in html
    assert ">Бруто кг" in html
    assert ">Действие" in html
    assert "25.06.2026" in html
    assert "26.06.2026" in html
    assert '<td class="col-sequence">-</td>' in html
    assert 'class="planning-open-button"' in html
    assert 'data-planning-action="/admin/cards/' in html
    assert 'class="planning-overflow"' in html
    assert "Изтрий карта" in html
    assert ">2 карти<" not in html
    assert 'class="release-control release-control-sequence"' not in html
    assert 'class="release-control release-control-machine"' not in html
    assert 'class="release-submit-button"' not in html
    assert '<span>Макс. тегло ролка, кг</span>' not in html
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")
    assert ".planning-table {" in css
    assert ".planning-table .col-size {" in css
    assert ".planning-open-button {" in css
    assert ".planning-overflow-menu {" in css
    assert ".planning-modal {" in css
    assert 'class="machine-grid"' not in html


def test_admin_planning_renders_machine_queues_as_shared_tables_with_menus(connection):
    pending_id = import_route_card(
        "25971",
        delivery_date="2026-07-30",
        customer="Machine Customer",
        product_type="Machine Product",
        size_thickness="800/0.045",
        ordered_gross_kg="650",
    )
    assert db.release_card(pending_id, 1, 1, card_version(pending_id)).ok

    response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "Машина 1" in html
    assert "30.07.2026" in html
    assert "800/0.045" in html
    assert "650" in html
    assert 'action="/admin/cards/' in html
    assert 'name="return_to" value="planning"' in html
    assert "Върни в неизпратени" in html
    assert "Изтрий карта" in html
    assert 'id="planning-modal"' in html
    assert ">Планирай карта<" in html
    assert 'id="planning-modal-form"' in html
    assert 'class="queue-card' not in html
    assert 'class="planning-form"' not in html
    assert 'class="queue-return-button"' not in html


def test_admin_planning_escapes_delete_confirmation_order_number(connection):
    order_number = "25973' + confirm('unsafe') + '"
    import_route_card(order_number)

    response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert 'onsubmit="return confirm(' not in html
    assert 'data-delete-order="25973&#39; + confirm(&#39;unsafe&#39;) + &#39;"' in html
    assert "deleteForm.dataset.deleteOrder" in html
    assert "innerHTML" not in html


def test_admin_delete_redirects_back_to_planning_when_requested(connection):
    card_id = import_route_card("25972")

    response = asyncio.run(
        admin_route_endpoint("/admin/cards/{card_id}/delete")(
            make_request(f"/admin/cards/{card_id}/delete"),
            card_id=card_id,
            loaded_version=str(card_version(card_id)),
            return_to="planning",
        )
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/planning"
    assert db.fetch_admin_card_detail(card_id) is None


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


def test_admin_planning_sorts_unreleased_cards_by_size_and_gross(connection):
    result = import_cards_from_csv(
        "planning-sort-size-gross-route.csv",
        csv_bytes(
            extrusion_row("25951", size_thickness="900/0.050", ordered_gross_kg="700"),
            extrusion_row("25950", size_thickness="600/0.040", ordered_gross_kg="1200"),
            extrusion_row("25952", size_thickness="700/0.030", ordered_gross_kg=""),
            extrusion_row("25953", size_thickness="800/0.040", ordered_gross_kg="NaN"),
        ),
        overwrite_existing=False,
    )
    assert result.rows_imported == 4

    size_response = asyncio.run(
        admin_planning(
            make_request("/admin/planning", method="GET"),
            draft_sort="size_thickness",
            draft_dir="asc",
        )
    )
    gross_response = asyncio.run(
        admin_planning(
            make_request("/admin/planning", method="GET"),
            draft_sort="ordered_gross_kg",
            draft_dir="desc",
        )
    )

    assert size_response.status_code == 200
    assert_html_order(size_response.body.decode("utf-8"), "25950", "25952", "25953", "25951")
    assert gross_response.status_code == 200
    assert_html_order(gross_response.body.decode("utf-8"), "25950", "25951", "25952", "25953")


def test_admin_planning_sort_does_not_reorder_machine_queues(connection):
    first_id = import_route_card("25961", customer="Zulu Machine")
    second_id = import_route_card("25962", customer="Alpha Machine")
    assert db.release_card(first_id, 1, 1, card_version(first_id)).ok
    assert db.release_card(second_id, 1, 2, card_version(second_id)).ok

    response = asyncio.run(
        admin_planning(
            make_request("/admin/planning", method="GET"),
            draft_sort="customer",
            draft_dir="desc",
        )
    )
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert_html_order(html, "25961", "25962")


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
            machine_id="1",
            machine_sequence="1",
        )
    )
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
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
    pending_id = import_route_card("25924", ordered_gross_kg="640.25")
    running_id = import_route_card("25925", ordered_gross_kg="")
    release_import = import_cards_from_csv(
        "25925-release.csv",
        csv_bytes(extrusion_row("25925", ordered_gross_kg="1")),
        overwrite_existing=True,
    )
    assert release_import.updated == 1
    assert db.release_card(
        pending_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(pending_id),
    ).ok
    assert db.release_card(
        running_id,
        machine_id=1,
        machine_sequence=2,
        loaded_version=card_version(running_id),
    ).ok
    assert db.start_production_timing(running_id, card_version(running_id)).ok
    connection.execute(
        "UPDATE cards SET ordered_gross_kg = '' WHERE id = ?",
        (running_id,),
    )
    connection.commit()

    response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert f'action="/admin/cards/{pending_id}/unrelease"' in html
    assert f'action="/admin/cards/{running_id}/unrelease"' not in html
    assert '<input type="hidden" name="return_to" value="planning">' in html
    assert '<table class="planning-table">' in html
    assert 'class="planning-overflow"' in html
    assert 'aria-label="Още действия за поръчка 25924"' in html
    assert ">Върни в неизпратени</button>" in html
    assert "4 машини в системата" not in html
    assert '<td class="col-gross">640.25</td>' in html
    assert '<td class="col-gross">-</td>' in html
    assert 'class="queue-card' not in html
    assert 'class="planning-form"' not in html


def test_admin_detail_renders_unrelease_form_for_pending_card_only(connection):
    pending_id = import_route_card("25926")
    running_id = import_route_card("25927")
    imported_id = import_route_card("25928")
    assert db.release_card(
        pending_id,
        machine_id=2,
        machine_sequence=1,
        loaded_version=card_version(pending_id),
    ).ok
    assert db.release_card(
        running_id,
        machine_id=2,
        machine_sequence=2,
        loaded_version=card_version(running_id),
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
