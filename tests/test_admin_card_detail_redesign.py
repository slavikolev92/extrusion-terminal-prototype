from __future__ import annotations

import asyncio
import csv
import io

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import db
from app.constants import CARD_STATUSES, STATUS_LABELS
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import (
    admin_card_detail_context,
    save_admin_card_changes,
    save_admin_imported_fields,
    save_admin_roll_ledger,
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
        "order_date": "2026-06-18",
        "delivery_date": "2026-06-20",
        "customer": "Admin Detail Redesign Customer",
        "city": "Plovdiv",
        "product_type": "TSF 890/0.082",
        "quantity_1": "3250.50",
        "unit_1": "kg",
        "quantity_2": "60",
        "unit_2": "rolls",
        "product_form": "flat film",
        "material": "LDPE / LLDPE",
        "size_thickness": "890 / 0.082",
        "notes": "Dense admin detail redesign fixture.",
        "extrusion_flag": "da",
        "extrusion_folding": "single fold",
        "extrusion_next_operation": "rewind",
        "extrusion_treatment": "corona",
        "raw_material_a": "Planned LDPE A",
        "raw_material_b": "Planned LLDPE B",
        "raw_material_c": "Planned HDPE C",
        "linear_pe": "Planned mLLDPE",
        "antistatic": "Planned antistatic",
        "masterbatch": "Planned masterbatch",
        "chalk": "Planned chalk",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def card_version(card_id: int) -> int:
    return int(db.fetch_admin_card_detail(card_id)["version"])


def current_import_fields(card_id: int) -> dict[str, str]:
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    return {field: str(card[field] or "") for field in IMPORT_FIELDS}


def recipe_component_snapshot(card_id: int) -> list[tuple[str, str, str, str, str]]:
    with db.connect() as connection:
        return [
            (
                str(row["component_key"]),
                str(row["source_text"]),
                str(row["material_category"]),
                str(row["planned_material"]),
                str(row["recipe_percent"]),
            )
            for row in db.fetch_recipe_components(connection, card_id)
        ]


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


def prepare_dense_completed_card(order_number: str = "27000", roll_count: int = 12) -> int:
    card_id = import_ready_card(order_number)
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="62.50",
    ).ok
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        card_version(card_id),
        {
            "raw_material_a": {
                "actual_material_used": "Actual LDPE A",
                "batch_lot": "LOT-A",
            },
            "raw_material_b": {
                "actual_material_used": "Actual LLDPE B",
                "batch_lot": "LOT-B",
            },
            "raw_material_c": {
                "actual_material_used": "Actual HDPE C",
                "batch_lot": "LOT-C",
            },
            "linear_pe": {
                "actual_material_used": "Actual mLLDPE",
                "batch_lot": "LOT-L",
            },
            "antistatic": {
                "actual_material_used": "Actual antistatic",
                "batch_lot": "LOT-AS",
            },
            "masterbatch": {
                "actual_material_used": "Actual masterbatch",
                "batch_lot": "LOT-MB",
            },
            "chalk": {
                "actual_material_used": "Actual chalk",
                "batch_lot": "LOT-CH",
            },
        },
        raw_material_brand_grade="Grade A",
    ).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.25").ok
    for index in range(roll_count):
        assert db.add_roll_gross_weight(
            card_id,
            card_version(card_id),
            f"{51 + index / 10:.2f}",
        ).ok
    assert db.finish_card(card_id, card_version(card_id)).ok
    return card_id


def render_admin_detail(card_id: int, **extra: object) -> str:
    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["url_for"] = lambda name, **kwargs: f"/static{kwargs.get('path', '')}"
    context = admin_card_detail_context(card_id, **extra)
    assert context is not None
    return env.get_template("admin_card_detail.html").render(**context)


def render_admin_cards_list(**extra: object) -> str:
    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["url_for"] = lambda name, **kwargs: f"/static{kwargs.get('path', '')}"
    context = {
        "cards": db.fetch_admin_cards({}),
        "filters": {"order_number": "", "customer": "", "product": "", "status": ""},
        "card_statuses": CARD_STATUSES,
        "status_labels": STATUS_LABELS,
        "summary": db.database_summary(),
    }
    context.update(extra)
    return env.get_template("admin_cards.html").render(**context)


class MultiItemForm:
    def __init__(self, items: list[tuple[str, str]]) -> None:
        self.items = items

    def get(self, key: str, default: str | None = None) -> str | None:
        for item_key, value in reversed(self.items):
            if item_key == key:
                return value
        return default

    def multi_items(self) -> list[tuple[str, str]]:
        return self.items


class FormRequest:
    def __init__(self, form: MultiItemForm) -> None:
        self._form = form

    async def form(self) -> MultiItemForm:
        return self._form

    def url_for(self, name: str, **path_params: str) -> str:
        if name == "static":
            return f"/static{path_params.get('path', '')}"
        return f"/{name}"


def test_admin_detail_combines_recipe_and_machine_materials(connection):
    card_id = prepare_dense_completed_card("27001")

    html = render_admin_detail(card_id)

    assert "Материали" in html
    assert "Рецепта" not in html
    assert "Материал на машината" not in html
    assert html.count('name="planned_material__raw_material_a"') == 1
    assert html.count('name="actual_material__raw_material_a"') == 1
    assert html.count('name="batch_lot__raw_material_a"') == 1
    assert 'name="raw_material_brand_grade"' not in html


def test_admin_detail_print_link_is_available_only_for_completed_cards(connection):
    completed_id = prepare_dense_completed_card("27040", roll_count=1)
    cancelled_id = import_ready_card("27041")
    assert db.release_card(
        cancelled_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(cancelled_id),
        max_roll_weight="62.50",
    ).ok
    assert db.cancel_card(cancelled_id, card_version(cancelled_id)).ok

    completed_html = render_admin_detail(completed_id)
    cancelled_html = render_admin_detail(cancelled_id)

    assert f'href="/cards/{completed_id}/print"' in completed_html
    assert 'class="admin-action-button admin-print-button"' in completed_html
    assert 'target="_blank" rel="noopener">Принтирай</a>' in completed_html
    assert "Печат / препечат" not in completed_html
    assert f"/cards/{cancelled_id}/print" not in cancelled_html
    assert "Принтирай" not in cancelled_html


def test_admin_detail_separates_global_navigation_from_card_actions(connection):
    card_id = prepare_dense_completed_card("27042", roll_count=1)

    html = render_admin_detail(card_id)

    assert 'class="admin-header"' in html
    assert 'src="/static/images/kolev-logo.png"' in html
    assert 'aria-current="page">Технологични карти</a>' in html
    assert "Терминал" in html
    assert 'class="admin-card-context admin-action-bar"' in html
    assert 'class="admin-card-title-line"' in html
    assert "Поръчка № 27042" in html
    assert 'class="pill status-completed"' in html
    assert 'class="admin-card-actions"' in html
    assert f'href="/cards/{card_id}/print"' in html
    assert f'action="/admin/cards/{card_id}/archive"' in html

    header_before_actions = html.split('class="admin-card-actions"', 1)[0]
    assert 'href="/cards/' not in header_before_actions
    assert "Технологични карти / Поръчка" not in header_before_actions
    assert "Машина 1 / ред 1" not in header_before_actions
    assert "Версия" not in header_before_actions
    assert "Обновена" not in header_before_actions
    assert "Маркирай като завършена" not in header_before_actions
    assert "Началник смяна" not in html
    assert '<a class="nav-link" href="/admin/cards">Технологични карти</a>' not in html
    assert '<a class="nav-link" href="/terminal">Терминал</a>' not in html
    assert "Terminal" not in html
    assert "Към терминала" not in html


def test_admin_detail_shows_archive_action_for_produced_cards(connection):
    card_id = prepare_dense_completed_card("27045", roll_count=1)

    html = render_admin_detail(card_id)

    assert "Произведена" in html
    assert 'class="pill status-completed"' in html
    assert f'href="/cards/{card_id}/print"' in html
    assert 'target="_blank" rel="noopener">Принтирай</a>' in html
    assert f'action="/admin/cards/{card_id}/archive"' in html
    assert 'class="admin-action-button admin-finish-button"' in html
    assert ">Маркирай завършена</button>" in html
    assert "<span>Маркирай</span>" not in html
    assert "<span>завършена</span>" not in html
    assert "Маркирай като завършена" not in html


def test_admin_detail_shows_print_but_no_archive_action_for_archived_cards(connection):
    card_id = prepare_dense_completed_card("27046", roll_count=1)
    assert db.archive_completed_card(card_id, card_version(card_id)).ok

    html = render_admin_detail(card_id)

    assert "Завършена" in html
    assert 'class="pill status-archived"' in html
    assert f'href="/cards/{card_id}/print"' in html
    assert 'target="_blank" rel="noopener">Принтирай</a>' in html
    assert f'action="/admin/cards/{card_id}/archive"' not in html
    assert 'class="admin-action-button admin-finish-button disabled"' in html
    assert 'type="button" disabled' in html
    assert ">Маркирай завършена</button>" in html
    assert "<span>Маркирай</span>" not in html
    assert "<span>завършена</span>" not in html
    assert "Маркирай като завършена" not in html


def test_admin_detail_header_and_summary_remove_nonessential_metadata(connection):
    card_id = prepare_dense_completed_card("27047", roll_count=1)

    html = render_admin_detail(card_id)

    assert '<main class="page admin-page admin-review-page">' in html
    assert "wide-page admin-page admin-review-page" not in html
    assert '<h1 class="admin-card-title-line">' in html
    assert 'Поръчка № 27047' in html
    assert 'class="pill status-completed"' in html

    header_html = html.split('<section class="section admin-summary-panel"', 1)[0]
    assert "Технологични карти / Поръчка" not in header_html
    assert "Машина 1 / ред 1" not in header_html
    assert "Версия" not in header_html
    assert "Обновена" not in header_html

    summary_html = html.split('<section class="section admin-summary-panel"', 1)[1].split("</section>", 1)[0]
    assert "<span>" not in summary_html
    assert "/ ред" not in summary_html
    assert "<dt>Машина</dt>" in summary_html
    machine_value = summary_html.split("<dt>Машина</dt>", 1)[1].split("</dd>", 1)[0]
    assert ">1" in "".join(machine_value.split())


def test_admin_detail_uses_sticky_action_bar_and_single_save_button(connection):
    card_id = prepare_dense_completed_card("27048", roll_count=1)

    html = render_admin_detail(card_id)

    assert 'class="admin-card-context admin-action-bar"' in html
    assert 'id="admin-card-save-form"' in html
    assert f'action="/admin/cards/{card_id}/save-all"' in html
    assert 'class="admin-action-button primary admin-save-button"' in html
    assert 'form="admin-card-save-form">Запази Промените</button>' in html
    assert html.count("Запази Промените") == 1
    assert "Запази данните" not in html
    assert "Запази материалите" not in html
    assert "Запази ролките" not in html
    assert "Запази времето" not in html


def test_admin_cards_list_does_not_show_print_shortcuts(connection):
    completed_id = prepare_dense_completed_card("27042", roll_count=1)
    pending_id = import_ready_card("27043")
    assert db.release_card(
        pending_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(pending_id),
        max_roll_weight="62.50",
    ).ok
    cancelled_id = import_ready_card("27044")
    assert db.release_card(
        cancelled_id,
        machine_id=2,
        machine_sequence=1,
        loaded_version=card_version(cancelled_id),
        max_roll_weight="62.50",
    ).ok
    assert db.cancel_card(cancelled_id, card_version(cancelled_id)).ok

    html = render_admin_cards_list()

    assert f'<a href="/admin/cards/{completed_id}">Отвори</a>' in html
    assert f'<a href="/admin/cards/{pending_id}">Отвори</a>' in html
    assert f'<a href="/admin/cards/{cancelled_id}">Отвори</a>' in html
    assert "/print" not in html
    assert ">Печат<" not in html


def test_admin_detail_uses_single_roll_ledger_without_repeated_save_buttons(connection):
    card_id = prepare_dense_completed_card("27002", roll_count=12)

    html = render_admin_detail(card_id)

    assert html.count("admin-roll-ledger-row") == 12
    assert "Запази ролките" not in html
    assert html.count("Запази Промените") == 1
    assert "admin-roll-correction-row" not in html
    assert html.count(">Запази<") < 10
    assert html.count(">Изтрий<") < 10
    assert "Произведено количество" not in html
    assert "Общо произведено" in html


def test_admin_detail_uses_single_timing_ledger_without_duplicate_segment_forms(connection):
    card_id = prepare_dense_completed_card("27003", roll_count=2)

    html = render_admin_detail(card_id)

    assert "Време" in html
    assert "Запази времето" not in html
    assert html.count("Запази Промените") == 1
    assert "admin-timing-correction-row" not in html
    assert "timing-correction-form" not in html


def test_admin_order_details_are_grouped_into_logical_sections(connection):
    card_id = prepare_dense_completed_card("27101", roll_count=2)

    html = render_admin_detail(card_id)

    assert 'id="order"' in html
    assert 'class="admin-order-group"' in html
    assert html.count("admin-order-group") >= 5
    assert "Поръчка" in html
    assert "Клиент" in html
    assert "Изделие" in html
    assert "Операции" in html
    assert "Забележки" in html
    assert html.find("Поръчка") < html.find("Клиент") < html.find("Изделие")
    assert html.find("Изделие") < html.find("Операции") < html.find("Забележки")


def test_admin_materials_ledger_omits_brand_class_field(connection):
    card_id = prepare_dense_completed_card("27102", roll_count=2)

    html = render_admin_detail(card_id)

    assert 'id="materials"' in html
    assert "Марка / клас" not in html
    assert 'name="raw_material_brand_grade"' not in html
    assert html.count('name="planned_material__raw_material_a"') == 1
    assert html.count('name="actual_material__raw_material_a"') == 1
    assert html.count('name="batch_lot__raw_material_a"') == 1


def test_admin_roll_and_timing_ledgers_use_explicit_x_delete_actions(connection):
    card_id = prepare_dense_completed_card("27103", roll_count=3)

    html = render_admin_detail(card_id)

    assert 'id="rolls"' in html
    assert 'id="timing"' in html
    assert 'name="delete_roll_id"' not in html
    assert 'name="delete_segment_id"' not in html
    assert ">Да</span>" not in html
    assert html.count("admin-row-delete-button") >= 2
    assert f'/admin/cards/{card_id}/rolls/' in html
    assert f'/admin/cards/{card_id}/timing-segments/' in html
    assert "/rolls/" in html
    assert "/delete" in html
    assert "/timing-segments/" in html
    assert html.count("/delete") >= 2
    assert "return confirm(" in html


def test_admin_card_post_response_redirects_to_section_anchor_on_success(connection):
    from app.main import admin_card_post_response
    from app.rules import RuleResult

    card_id = prepare_dense_completed_card("27104", roll_count=1)
    response = admin_card_post_response(
        FormRequest(MultiItemForm([])),
        card_id,
        "roll_result",
        RuleResult(True, ("ok",)),
        anchor="rolls",
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/cards/{card_id}#rolls"


def test_admin_card_post_response_without_anchor_keeps_existing_redirect(connection):
    from app.main import admin_card_post_response
    from app.rules import RuleResult

    card_id = prepare_dense_completed_card("27105", roll_count=1)
    response = admin_card_post_response(
        FormRequest(MultiItemForm([])),
        card_id,
        "workflow_result",
        RuleResult(True, ("ok",)),
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/cards/{card_id}"


def test_admin_order_form_save_preserves_omitted_recipe_fields(connection):
    card_id = import_ready_card("27106")
    card = db.fetch_admin_card_detail(card_id)

    response = asyncio.run(
        save_admin_imported_fields(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(card["version"])),
                        ("order_number", "27106"),
                        ("order_date", "2026-06-19"),
                        ("delivery_date", "2026-06-21"),
                        ("customer", "Grouped Order Customer"),
                        ("city", "Varna"),
                        ("product_type", "Updated film"),
                        ("quantity_1", "4250"),
                        ("unit_1", "kg"),
                        ("quantity_2", "80"),
                        ("unit_2", "rolls"),
                        ("size_thickness", "900 / 0.090"),
                        ("product_form", "sleeve"),
                        ("material", "LDPE"),
                        ("max_roll_weight", "70.5"),
                        ("extrusion_flag", "da"),
                        ("extrusion_folding", "double fold"),
                        ("extrusion_next_operation", "print"),
                        ("extrusion_treatment", "corona"),
                        ("packaging_method", "pallet"),
                        ("notes", "Grouped order save."),
                    ]
                )
            ),
            card_id,
        )
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert updated["customer"] == "Grouped Order Customer"
    assert updated["max_roll_weight"] == "70.5"
    assert updated["raw_material_a"] == "Planned LDPE A"
    assert updated["raw_material_b"] == "Planned LLDPE B"
    assert updated["raw_material_c"] == "Planned HDPE C"
    assert updated["linear_pe"] == "Planned mLLDPE"
    assert updated["antistatic"] == "Planned antistatic"
    assert updated["masterbatch"] == "Planned masterbatch"
    assert updated["chalk"] == "Planned chalk"


def test_admin_global_save_updates_order_materials_and_roll_data(connection):
    card_id = prepare_dense_completed_card("27107", roll_count=1)
    card = db.fetch_admin_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])

    response = asyncio.run(
        save_admin_card_changes(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(card["version"])),
                        ("customer", "Global Save Customer"),
                        ("planned_material__raw_material_a", "Global planned A"),
                        ("actual_material__raw_material_a", "Global actual A"),
                        ("batch_lot__raw_material_a", "Global batch A"),
                        ("tare_weight", "2.00"),
                        (f"gross_weight__{roll_id}", "60.00"),
                    ]
                )
            ),
            card_id,
        )
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/cards/{card_id}"
    assert updated["customer"] == "Global Save Customer"
    assert updated["raw_material_a"] == "Global planned A"
    assert (
        updated["recipe_actual_entries"]["raw_material_a"]["actual_material_used"]
        == "Global actual A"
    )
    assert updated["recipe_actual_entries"]["raw_material_a"]["batch_lot"] == "Global batch A"
    assert updated["tare_weight"] == 2
    assert updated["roll_entries"][0]["gross_weight"] == 60
    assert updated["roll_entries"][0]["net_weight"] == 58


def test_admin_global_save_rolls_back_all_sections_when_timing_is_invalid(connection):
    card_id = prepare_dense_completed_card("27108", roll_count=1)
    before = db.fetch_admin_card_detail(card_id)
    roll_id = int(before["roll_entries"][0]["id"])
    segment_id = int(before["timing_segments"][0]["id"])
    before_segments = [
        (
            int(segment["id"]),
            segment["started_at"],
            segment["ended_at"],
            segment["end_reason"],
        )
        for segment in before["timing_segments"]
    ]

    response = asyncio.run(
        save_admin_card_changes(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(before["version"])),
                        ("customer", "Should Not Persist"),
                        ("planned_material__raw_material_a", "Should Not Persist"),
                        ("actual_material__raw_material_a", "Should Not Persist"),
                        ("batch_lot__raw_material_a", "Should Not Persist"),
                        ("tare_weight", "2.00"),
                        (f"gross_weight__{roll_id}", "60.00"),
                        ("delete_segment_id", str(segment_id)),
                    ]
                )
            ),
            card_id,
        )
    )
    body = response.body.decode("utf-8")
    after = db.fetch_admin_card_detail(card_id)
    after_segments = [
        (
            int(segment["id"]),
            segment["started_at"],
            segment["ended_at"],
            segment["end_reason"],
        )
        for segment in after["timing_segments"]
    ]

    assert response.status_code == 200
    assert "Завършена карта трябва да има поне един времеви сегмент." in body
    assert after["version"] == before["version"]
    assert after["customer"] == before["customer"]
    assert after["raw_material_a"] == before["raw_material_a"]
    assert (
        after["recipe_actual_entries"]["raw_material_a"]["actual_material_used"]
        == before["recipe_actual_entries"]["raw_material_a"]["actual_material_used"]
    )
    assert after["recipe_actual_entries"]["raw_material_a"]["batch_lot"] == (
        before["recipe_actual_entries"]["raw_material_a"]["batch_lot"]
    )
    assert after["tare_weight"] == before["tare_weight"]
    assert after["roll_entries"][0]["gross_weight"] == before["roll_entries"][0]["gross_weight"]
    assert after["roll_entries"][0]["net_weight"] == before["roll_entries"][0]["net_weight"]
    assert after_segments == before_segments


def test_admin_global_save_rolls_back_recipe_components_when_timing_is_invalid(connection):
    card_id = prepare_dense_completed_card("27109", roll_count=1)
    seed_fields = current_import_fields(card_id)
    seed_fields["raw_material_a"] = "LDPE Before Rollback | 80%"
    seed_fields["linear_pe"] = "LLDPE Before Rollback | 20%"
    assert db.update_admin_imported_fields(card_id, card_version(card_id), seed_fields).ok

    before = db.fetch_admin_card_detail(card_id)
    roll_id = int(before["roll_entries"][0]["id"])
    segment_id = int(before["timing_segments"][0]["id"])
    before_components = recipe_component_snapshot(card_id)

    response = asyncio.run(
        save_admin_card_changes(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(before["version"])),
                        ("raw_material_a", "LDPE After Rollback | 70%"),
                        ("linear_pe", "LLDPE After Rollback | 30%"),
                        ("planned_material__raw_material_a", "Should Not Persist"),
                        ("tare_weight", "2.00"),
                        (f"gross_weight__{roll_id}", "60.00"),
                        ("delete_segment_id", str(segment_id)),
                    ]
                )
            ),
            card_id,
        )
    )
    body = response.body.decode("utf-8")
    after = db.fetch_admin_card_detail(card_id)

    assert before_components == [
        ("raw_material_a", "LDPE Before Rollback | 80%", "LDPE", "Before Rollback", "80"),
        ("linear_pe", "LLDPE Before Rollback | 20%", "LLDPE", "Before Rollback", "20"),
    ]
    assert response.status_code == 200
    assert "Завършена карта трябва да има поне един времеви сегмент." in body
    assert after["version"] == before["version"]
    assert after["raw_material_a"] == before["raw_material_a"]
    assert after["linear_pe"] == before["linear_pe"]
    assert recipe_component_snapshot(card_id) == before_components


def test_admin_material_ledger_updates_planned_and_actual_fields(connection):
    card_id = prepare_dense_completed_card("27010", roll_count=1)
    loaded_version = card_version(card_id)

    result = db.update_admin_material_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        planned_materials={
            "raw_material_a": "Corrected planned A",
            "raw_material_b": "Corrected planned B",
            "raw_material_c": "Corrected planned C",
            "linear_pe": "Corrected linear",
            "antistatic": "Corrected antistatic",
            "masterbatch": "Corrected masterbatch",
            "chalk": "Corrected chalk",
        },
        actual_entries={
            "raw_material_a": {
                "actual_material_used": "Corrected actual A",
                "batch_lot": "Corrected batch A",
            },
            "raw_material_b": {
                "actual_material_used": "Corrected actual B",
                "batch_lot": "Corrected batch B",
            },
            "raw_material_c": {"actual_material_used": "", "batch_lot": ""},
            "linear_pe": {"actual_material_used": "", "batch_lot": ""},
            "antistatic": {"actual_material_used": "", "batch_lot": ""},
            "masterbatch": {"actual_material_used": "", "batch_lot": ""},
            "chalk": {"actual_material_used": "", "batch_lot": ""},
        },
    )
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["raw_material_a"] == "Corrected planned A"
    assert card["raw_material_b"] == "Corrected planned B"
    assert (
        card["recipe_actual_entries"]["raw_material_a"]["actual_material_used"]
        == "Corrected actual A"
    )
    assert card["recipe_actual_entries"]["raw_material_a"]["batch_lot"] == "Corrected batch A"
    assert card["actual_raw_material_used"] == "Corrected actual A"
    assert card["raw_material_batch_lot"] == "Corrected batch A"
    assert card["raw_material_brand_grade"] == "Grade A"
    assert card["version"] == loaded_version + 1


def test_admin_material_ledger_preserves_legacy_brand_class_when_omitted(connection):
    card_id = prepare_dense_completed_card("27012", roll_count=1)
    loaded_version = card_version(card_id)

    result = db.update_admin_material_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        planned_materials={"raw_material_a": "Corrected planned A"},
        actual_entries={
            "raw_material_a": {
                "actual_material_used": "Corrected actual A",
                "batch_lot": "Corrected batch A",
            },
        },
        raw_material_brand_grade=None,
    )
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["raw_material_brand_grade"] == "Grade A"


def test_admin_material_ledger_blocks_stale_version(connection):
    card_id = prepare_dense_completed_card("27011", roll_count=1)
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.30").ok

    result = db.update_admin_material_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        planned_materials={"raw_material_a": "Stale"},
        actual_entries={},
        raw_material_brand_grade="Stale",
    )

    assert not result.ok
    assert result.messages == (db.STALE_CARD_MESSAGE,)


def test_admin_roll_ledger_updates_tare_rolls_deletes_and_adds(connection):
    card_id = prepare_dense_completed_card("27020", roll_count=3)
    card = db.fetch_admin_card_detail(card_id)
    loaded_version = int(card["version"])
    first_roll = card["roll_entries"][0]
    second_roll = card["roll_entries"][1]

    result = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        tare_weight="1.50",
        roll_updates={int(first_roll["id"]): "55.00"},
        delete_roll_ids={int(second_roll["id"])},
        new_gross_weights=["56.25"],
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert updated["tare_weight"] == 1.5
    assert updated["roll_count"] == 3
    assert [roll["roll_number"] for roll in updated["roll_entries"]] == [1, 2, 3]
    assert updated["roll_entries"][0]["gross_weight"] == 55
    assert updated["version"] == loaded_version + 1


def test_admin_roll_ledger_blocks_stale_version(connection):
    card_id = prepare_dense_completed_card("27021", roll_count=2)
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.40").ok

    result = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        tare_weight="1.50",
        roll_updates={},
        delete_roll_ids=set(),
        new_gross_weights=[],
    )

    assert not result.ok
    assert result.messages == (db.STALE_CARD_MESSAGE,)


def test_admin_roll_ledger_allows_tare_only_save_on_paused_card(connection):
    card_id = import_ready_card("27023")
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="62.50",
    ).ok
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.pause_production_timing(card_id, card_version(card_id)).ok
    loaded_version = card_version(card_id)

    result = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        tare_weight="1.75",
        roll_updates={},
        delete_roll_ids=set(),
        new_gross_weights=[],
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert updated["tare_weight"] == 1.75
    assert updated["version"] == loaded_version + 1


def test_admin_roll_ledger_blocks_roll_add_on_paused_card(connection):
    card_id = import_ready_card("27024")
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="62.50",
    ).ok
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.pause_production_timing(card_id, card_version(card_id)).ok

    result = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=card_version(card_id),
        tare_weight="1.75",
        roll_updates={},
        delete_roll_ids=set(),
        new_gross_weights=["55.00"],
    )

    assert not result.ok
    assert result.messages == (
        "Теглата на ролките могат да се променят само когато картата е в изработване, произведена или завършена.",
    )


def test_admin_roll_ledger_route_blocks_malformed_roll_ids(connection):
    card_id = prepare_dense_completed_card("27022", roll_count=2)
    loaded_version = card_version(card_id)
    malformed_forms = [
        [
            ("loaded_version", str(loaded_version)),
            ("tare_weight", "1.50"),
            ("gross_weight__bad-id", "55.00"),
        ],
        [
            ("loaded_version", str(loaded_version)),
            ("tare_weight", "1.50"),
            ("delete_roll_id", "bad-id"),
        ],
    ]

    for items in malformed_forms:
        response = asyncio.run(
            save_admin_roll_ledger(FormRequest(MultiItemForm(items)), card_id)
        )
        body = response.body.decode("utf-8")

        assert response.status_code == 200
        assert "Формата съдържа невалидна ролка." in body


def test_admin_timing_ledger_updates_deletes_and_adds_segments(connection):
    card_id = prepare_dense_completed_card("27030", roll_count=1)
    assert db.add_timing_segment(
        card_id,
        card_version(card_id),
        "2026-06-18 08:00:00",
        "2026-06-18 09:00:00",
        "correction",
    ).ok
    card = db.fetch_admin_card_detail(card_id)
    loaded_version = int(card["version"])
    first_segment = card["timing_segments"][0]
    deleted_segment = card["timing_segments"][1]

    result = db.update_admin_timing_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        segment_updates={
            int(first_segment["id"]): {
                "started_at": "2026-06-18 06:10:00",
                "ended_at": "2026-06-18 07:00:00",
                "end_reason": "pause",
            }
        },
        delete_segment_ids={int(deleted_segment["id"])},
        new_segments=[
            {
                "started_at": "2026-06-18 10:00:00",
                "ended_at": "2026-06-18 10:30:00",
                "end_reason": "correction",
            }
        ],
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert updated["timing_segments"][0]["started_at"] == "2026-06-18 06:10:00"
    assert all(
        int(segment["id"]) != int(deleted_segment["id"])
        for segment in updated["timing_segments"]
    )
    assert any(
        segment["started_at"] == "2026-06-18 10:00:00"
        for segment in updated["timing_segments"]
    )
    assert updated["version"] == loaded_version + 1


def test_admin_timing_ledger_blocks_open_segment_on_completed_card(connection):
    card_id = prepare_dense_completed_card("27032", roll_count=1)
    before = db.fetch_admin_card_detail(card_id)
    loaded_version = int(before["version"])
    before_segments = [
        (
            int(segment["id"]),
            segment["started_at"],
            segment["ended_at"],
            segment["end_reason"],
        )
        for segment in before["timing_segments"]
    ]

    result = db.update_admin_timing_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        segment_updates={},
        delete_segment_ids=set(),
        new_segments=[
            {
                "started_at": "2026-06-18 11:00:00",
                "ended_at": "",
                "end_reason": "",
            }
        ],
    )
    after = db.fetch_admin_card_detail(card_id)
    after_segments = [
        (
            int(segment["id"]),
            segment["started_at"],
            segment["ended_at"],
            segment["end_reason"],
        )
        for segment in after["timing_segments"]
    ]

    assert not result.ok
    assert result.messages == ("Само карти в изработване могат да имат отворен времеви сегмент.",)
    assert after_segments == before_segments
    assert after["version"] == loaded_version


def test_admin_timing_ledger_blocks_open_segment_on_paused_card(connection):
    card_id = import_ready_card("27033")
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="62.50",
    ).ok
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.pause_production_timing(card_id, card_version(card_id)).ok
    before = db.fetch_admin_card_detail(card_id)
    loaded_version = int(before["version"])

    result = db.update_admin_timing_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        segment_updates={},
        delete_segment_ids=set(),
        new_segments=[
            {
                "started_at": "2026-06-18 12:00:00",
                "ended_at": "",
                "end_reason": "",
            }
        ],
    )
    after = db.fetch_admin_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Само карти в изработване могат да имат отворен времеви сегмент.",)
    assert len(after["timing_segments"]) == len(before["timing_segments"])
    assert after["version"] == loaded_version


def test_admin_timing_ledger_allows_swapping_open_segment_order_independently(connection):
    card_id = import_ready_card("27034")
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="62.50",
    ).ok
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.add_timing_segment(
        card_id,
        card_version(card_id),
        "2026-06-18 07:00:00",
        "2026-06-18 07:30:00",
        "correction",
    ).ok
    card = db.fetch_admin_card_detail(card_id)
    loaded_version = int(card["version"])
    open_segment = next(segment for segment in card["timing_segments"] if segment["ended_at"] is None)
    closed_segment = next(segment for segment in card["timing_segments"] if segment["ended_at"] is not None)

    result = db.update_admin_timing_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        segment_updates={
            int(closed_segment["id"]): {
                "started_at": closed_segment["started_at"],
                "ended_at": "",
                "end_reason": "",
            },
            int(open_segment["id"]): {
                "started_at": "2026-06-18 07:31:00",
                "ended_at": "2026-06-18 08:00:00",
                "end_reason": "pause",
            },
        },
        delete_segment_ids=set(),
        new_segments=[],
    )
    updated = db.fetch_admin_card_detail(card_id)
    updated_open_segments = [
        segment for segment in updated["timing_segments"] if segment["ended_at"] is None
    ]
    updated_closed_segment = next(
        segment
        for segment in updated["timing_segments"]
        if int(segment["id"]) == int(open_segment["id"])
    )

    assert result.ok
    assert len(updated_open_segments) == 1
    assert int(updated_open_segments[0]["id"]) == int(closed_segment["id"])
    assert updated_closed_segment["ended_at"] == "2026-06-18 08:00:00"
    assert updated_closed_segment["end_reason"] == "pause"


def test_admin_timing_ledger_blocks_stale_version(connection):
    card_id = prepare_dense_completed_card("27031", roll_count=1)
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.40").ok

    result = db.update_admin_timing_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        segment_updates={},
        delete_segment_ids=set(),
        new_segments=[],
    )

    assert not result.ok
    assert result.messages == (db.STALE_CARD_MESSAGE,)
