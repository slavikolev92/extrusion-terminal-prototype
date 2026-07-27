from __future__ import annotations

import asyncio
import csv
import io
import re

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import db
from app.constants import (
    CARD_STATUSES,
    STATUS_ARCHIVED,
    STATUS_AWAITING_REWINDING,
    STATUS_LABELS,
)
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import (
    admin_card_detail_context,
    roll_ledger_from_form,
    save_admin_card_changes,
    save_admin_imported_fields,
    save_admin_roll_ledger,
)


pytestmark = pytest.mark.usefixtures("active_test_shift")


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
        "ordered_gross_kg": "3250.50",
        "ordered_rolls": "60",
        "ordered_meters": "15000",
        "ordered_units": "40000",
        "product_form": "flat film",
        "material": "LDPE / LLDPE",
        "size_thickness": "890 / 0.082",
        "notes": "Dense admin detail redesign fixture.",
        "printing_sequence": "2",
        "extrusion_sequence": "1",
        "rewinding_slitting_sequence": "3",
        "confection_sequence": "4",
        "extrusion_folding": "single fold",
        "extrusion_next_operation": "rewind",
        "extrusion_treatment": "corona",
        "raw_material_a": "LDPE; Planned A | 50%",
        "raw_material_b": "LLDPE; Planned B | 30%",
        "raw_material_c": "MDPE; Planned C | 5%",
        "linear_pe": "LLDPE; Planned mLLDPE | 8%",
        "antistatic": "Antistatic; Planned antistatic | 1%",
        "masterbatch": "Masterbatch; Planned masterbatch | 4%",
        "chalk": "Filler; Planned chalk | 2%",
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


def admin_material_form_items(
    card_id: int,
    *,
    overrides: dict[str, dict[str, str]] | None = None,
) -> list[tuple[str, str]]:
    overrides = overrides or {}
    context = admin_card_detail_context(card_id)
    assert context is not None
    items: list[tuple[str, str]] = []
    for row in context["recipe_rows"]:
        field = row["field"]
        row_overrides = overrides.get(field, {})
        percent = str(row["recipe_percent"] or "")
        if percent.endswith("%"):
            percent = percent[:-1]
        items.extend(
            [
                (
                    f"material_category__{field}",
                    row_overrides.get("material_category", str(row["material_category"] or "")),
                ),
                (
                    f"planned_material__{field}",
                    row_overrides.get(
                        "planned_material",
                        str(row["planned_material_edit"] or ""),
                    ),
                ),
                (
                    f"recipe_percent__{field}",
                    row_overrides.get("recipe_percent", percent),
                ),
                (
                    f"actual_material__{field}",
                    row_overrides.get("actual_material", str(row["actual_material"] or "")),
                ),
                (
                    f"batch_lot__{field}",
                    row_overrides.get("batch_lot", str(row["batch"] or "")),
                ),
            ]
        )
    return items


def test_admin_detail_combines_recipe_and_machine_materials(connection):
    card_id = prepare_dense_completed_card("27001")
    context = admin_card_detail_context(card_id)

    html = render_admin_detail(card_id)

    assert context is not None
    assert "recipe_categories" not in context
    assert "Материали" in html
    assert "Категория" in html
    assert "Планирани материали" in html
    assert ">%<" in html
    assert ">КГ<" in html
    assert "Вложени материали" in html
    assert "Рецепта" not in html
    assert "Материал на машината" not in html
    assert '<input name="material_category__raw_material_a"' in html
    assert '<select name="material_category__raw_material_a"' not in html
    assert html.count('name="material_category__raw_material_a"') == 1
    assert html.count('name="planned_material__raw_material_a"') == 1
    assert html.count('name="recipe_percent__raw_material_a"') == 1
    assert 'value="Planned A"' in html
    assert 'value="50"' in html
    assert 'value="50%"' not in html
    assert 'value="LDPE Planned A | 50%"' not in html
    assert "Planned A" in html
    assert "1625.25" in html
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


def test_waiting_rewinding_card_is_visible_to_admins_without_lifecycle_shortcuts(
    connection,
):
    card_id = prepare_dense_completed_card("27041-waiting", roll_count=1)
    with db.connect() as update_connection:
        update_connection.execute(
            """
            UPDATE cards
            SET status = ?, rewinding_roll_count = 4
            WHERE id = ?
            """,
            (STATUS_AWAITING_REWINDING, card_id),
        )
        update_connection.commit()

    detail_html = render_admin_detail(card_id)
    list_html = render_admin_cards_list(
        cards=db.fetch_admin_cards({"status": STATUS_AWAITING_REWINDING}),
        filters={
            "order_number": "",
            "customer": "",
            "product": "",
            "status": STATUS_AWAITING_REWINDING,
        },
    )

    assert "Изчаква пренавиване" in detail_html
    assert "Изчаква пренавиване" in list_html
    assert detail_html.count("Пренавиване: 4") == 1
    assert list_html.count("Пренавиване: 4") == 1
    assert 'value="awaiting_rewinding" selected' in list_html
    assert "Actual LDPE A" in detail_html
    assert "LOT-A" in detail_html
    assert "51.00" in detail_html
    assert "Машина" in detail_html
    assert "Време" in detail_html
    assert f'action="/admin/cards/{card_id}/cancel"' not in detail_html
    assert f'action="/admin/cards/{card_id}/delete"' not in detail_html
    assert f'action="/admin/cards/{card_id}/archive"' not in detail_html
    assert f'href="/cards/{card_id}/print"' not in detail_html


def test_admin_rewinding_count_is_hidden_after_waiting_status(connection):
    completed_id = prepare_dense_completed_card("27041-completed", roll_count=1)
    archived_id = prepare_dense_completed_card("27041-archived", roll_count=1)
    with db.connect() as update_connection:
        update_connection.execute(
            "UPDATE cards SET rewinding_roll_count = 6 WHERE id = ?",
            (completed_id,),
        )
        update_connection.execute(
            "UPDATE cards SET status = ?, rewinding_roll_count = 9 WHERE id = ?",
            (STATUS_ARCHIVED, archived_id),
        )
        update_connection.commit()

    detail_html = render_admin_detail(completed_id)
    archived_detail_html = render_admin_detail(archived_id)
    list_html = render_admin_cards_list()

    assert "Пренавиване: 6" not in detail_html
    assert "Пренавиване: 9" not in archived_detail_html
    assert "Пренавиване: 6" not in list_html
    assert "Пренавиване: 9" not in list_html


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
    ).ok
    cancelled_id = import_ready_card("27044")
    assert db.release_card(
        cancelled_id,
        machine_id=2,
        machine_sequence=1,
        loaded_version=card_version(cancelled_id),
    ).ok
    assert db.cancel_card(cancelled_id, card_version(cancelled_id)).ok

    html = render_admin_cards_list()

    assert f'<a href="/admin/cards/{completed_id}">Отвори</a>' in html
    assert f'<a href="/admin/cards/{pending_id}">Отвори</a>' in html
    assert f'<a href="/admin/cards/{cancelled_id}">Отвори</a>' in html
    assert "/print" not in html
    assert ">Печат<" not in html


def test_admin_cards_list_shows_delivery_and_ordered_gross(connection):
    import_ready_card(
        "27049",
        delivery_date="2026-06-29",
        ordered_gross_kg="875.50",
    )

    html = render_admin_cards_list()

    assert "<th>Доставка</th>" in html
    assert "<th>Поръчано бруто, кг</th>" in html
    assert "2026-06-29" in html
    assert "875.50" in html
    assert "875.50 кг" not in html

    import_ready_card("27050", delivery_date="", ordered_gross_kg="")
    html = render_admin_cards_list()
    blank_row = html.split("<td>27050</td>", 1)[1].split("</tr>", 1)[0]
    assert blank_row.count("<td>-</td>") >= 2
    assert "- кг" not in html


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


def test_admin_detail_renders_accepted_order_groups_without_route_inputs(connection):
    card_id = import_ready_card("27122")
    html = render_admin_detail(card_id)

    expected_inputs = {
        "ordered_gross_kg": "3250.50",
        "ordered_rolls": "60",
        "ordered_meters": "15000",
        "ordered_units": "40000",
    }
    for name, value in expected_inputs.items():
        assert f'name="{name}" value="{value}"' in html

    for old_name in (
        "quantity_1",
        "unit_1",
        "quantity_2",
        "unit_2",
        "extrusion_flag",
        "max_roll_weight",
        "printing_sequence",
        "extrusion_sequence",
        "rewinding_slitting_sequence",
        "confection_sequence",
    ):
        assert f'name="{old_name}"' not in html

    assert "Фалдиране" in html
    assert "Фалцоване" not in html


def test_admin_roll_ledger_renders_current_and_per_roll_pallets(connection):
    card_id = prepare_dense_completed_card("27120", roll_count=1)
    card = db.fetch_admin_card_detail(card_id)
    roll = card["roll_entries"][0]
    roll_id = int(roll["id"])

    html = render_admin_detail(card_id)
    roll_ledger_html = html.split('<div class="admin-ledger-table roll-ledger">', 1)[1]
    header_html = roll_ledger_html.split('<div class="admin-ledger-head">', 1)[1].split(
        '<div class="admin-ledger-row admin-roll-ledger-row">',
        1,
    )[0]

    toolbar_html = html.split('<div class="admin-roll-toolbar">', 1)[1].split("</div>", 1)[0]

    assert toolbar_html.find("Шпула, кг") < toolbar_html.find("Палет")
    assert toolbar_html.find("Палет") < toolbar_html.find("Нова ролка, кг")
    assert 'name="current_pallet_number"' in toolbar_html
    current_pallet_match = re.search(
        r'<input[^>]+name="current_pallet_number"[^>]*>',
        toolbar_html,
    )
    assert current_pallet_match is not None
    current_pallet_tag = current_pallet_match.group(0)
    assert 'type="text"' in current_pallet_tag
    assert 'inputmode="numeric"' in current_pallet_tag
    for forbidden_attribute in ('min="', 'max="', 'step="', 'pattern="', 'maxlength="'):
        assert forbidden_attribute not in current_pallet_tag
    assert ">Палет<" in header_html
    assert ">Бруто, кг<" in header_html
    assert ">Шпула, кг<" in header_html
    assert ">Нето, кг<" in header_html
    assert f'name="gross_weight__{roll_id}"' in roll_ledger_html
    pallet_input_match = re.search(
        rf'<input[^>]+name="pallet_number__{roll_id}"[^>]*>',
        roll_ledger_html,
    )
    assert pallet_input_match is not None
    pallet_input_tag = pallet_input_match.group(0)
    assert 'type="text"' in pallet_input_tag
    assert 'inputmode="numeric"' in pallet_input_tag
    assert 'placeholder="-"' in pallet_input_tag
    for forbidden_attribute in ('min="', 'max="', 'step="', 'pattern="', 'maxlength="'):
        assert forbidden_attribute not in pallet_input_tag
    assert f'name="tare_weight__{roll_id}"' in roll_ledger_html
    assert str(roll["net_weight"]) in roll_ledger_html
    assert f'form="roll-delete-{roll_id}"' in roll_ledger_html
    assert 'name="new_gross_weight"' in html
    assert 'name="new_tare_weight"' not in html
    assert "Без палет" not in roll_ledger_html


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
    assert "Екструзия" in html
    assert "Забележки" in html
    assert html.find("Поръчка") < html.find("Клиент") < html.find("Изделие")
    assert html.find("Изделие") < html.find("Екструзия") < html.find("Забележки")
    extrusion_group = html.split("<legend>Екструзия</legend>", 1)[1].split("</fieldset>", 1)[0]
    assert extrusion_group.count('<input name="') == 3
    assert "Фалдиране" in extrusion_group
    assert "Следваща операция" in extrusion_group
    assert "Третиране" in extrusion_group
    order_group = html.split("<legend>Поръчка</legend>", 1)[1].split("</fieldset>", 1)[0]
    assert 'name="packaging_method"' in order_group
    assert 'class="admin-order-groups"' in html


def test_admin_materials_ledger_omits_brand_class_field(connection):
    card_id = prepare_dense_completed_card("27102", roll_count=2)

    html = render_admin_detail(card_id)

    assert 'id="materials"' in html
    assert "Категория" in html
    assert "Планирани материали" in html
    assert ">%<" in html
    assert ">КГ<" in html
    assert "Вложени материали" in html
    assert "Марка / клас" not in html
    assert 'name="raw_material_brand_grade"' not in html
    assert html.count('name="material_category__raw_material_a"') == 1
    assert html.count('name="planned_material__raw_material_a"') == 1
    assert html.count('name="recipe_percent__raw_material_a"') == 1
    assert html.count('name="actual_material__raw_material_a"') == 1
    assert html.count('name="batch_lot__raw_material_a"') == 1


def test_admin_materials_ledger_renders_structured_planned_inputs(connection):
    card_id = prepare_dense_completed_card("27120", roll_count=1)

    html = render_admin_detail(card_id)

    assert 'name="material_category__raw_material_a"' in html
    assert '<input name="material_category__raw_material_a"' in html
    assert '<select name="material_category__raw_material_a"' not in html
    assert 'name="planned_material__raw_material_a" value="Planned A"' in html
    assert 'name="recipe_percent__raw_material_a" value="50"' in html
    assert 'name="recipe_percent__raw_material_a" value="50%"' not in html
    assert 'aria-label="A категория"' in html
    assert 'aria-label="A планиран материал"' in html
    assert 'aria-label="A процент"' in html
    assert 'aria-label="A източник по карта"' not in html
    assert 'value="LDPE Planned A | 50%"' not in html


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
    connection.execute(
        "UPDATE cards SET max_roll_weight = ? WHERE id = ?",
        ("70.5", card_id),
    )
    connection.commit()

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
                        ("ordered_gross_kg", "4250"),
                        ("ordered_rolls", "80"),
                        ("ordered_meters", "21000"),
                        ("ordered_units", "51000"),
                        ("size_thickness", "900 / 0.090"),
                        ("product_form", "sleeve"),
                        ("material", "LDPE"),
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
    assert updated["ordered_gross_kg"] == "4250"
    assert updated["ordered_rolls"] == "80"
    assert updated["ordered_meters"] == "21000"
    assert updated["ordered_units"] == "51000"
    assert updated["printing_sequence"] == "2"
    assert updated["extrusion_sequence"] == "1"
    assert updated["rewinding_slitting_sequence"] == "3"
    assert updated["confection_sequence"] == "4"
    legacy_max_roll_weight = connection.execute(
        "SELECT max_roll_weight FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()["max_roll_weight"]
    assert legacy_max_roll_weight == "70.5"
    assert updated["raw_material_a"] == "LDPE; Planned A | 50%"
    assert updated["raw_material_b"] == "LLDPE; Planned B | 30%"
    assert updated["raw_material_c"] == "MDPE; Planned C | 5%"
    assert updated["linear_pe"] == "LLDPE; Planned mLLDPE | 8%"
    assert updated["antistatic"] == "Antistatic; Planned antistatic | 1%"
    assert updated["masterbatch"] == "Masterbatch; Planned masterbatch | 4%"
    assert updated["chalk"] == "Filler; Planned chalk | 2%"


def test_admin_imported_fields_route_rejects_raw_old_recipe_format(connection):
    card_id = import_ready_card("27107")
    before = db.fetch_admin_card_detail(card_id)

    response = asyncio.run(
        save_admin_imported_fields(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(before["version"])),
                        ("order_number", "27107"),
                        ("raw_material_a", "LDPE Updated | 100%"),
                    ]
                )
            ),
            card_id,
        )
    )
    after = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 200
    assert after["raw_material_a"] == before["raw_material_a"]
    assert after["version"] == before["version"]
    assert "липсва разделител ;" in response.body.decode()


def test_admin_imported_fields_route_rejects_raw_extra_semicolon(connection):
    card_id = import_ready_card("27108")
    before = db.fetch_admin_card_detail(card_id)

    response = asyncio.run(
        save_admin_imported_fields(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(before["version"])),
                        ("order_number", "27108"),
                        (
                            "raw_material_a",
                            "UV Protection; Additech; Shield | 100%",
                        ),
                    ]
                )
            ),
            card_id,
        )
    )
    after = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 200
    assert after["raw_material_a"] == before["raw_material_a"]
    assert after["version"] == before["version"]
    assert "неподдържан разделител ; в материала" in response.body.decode()


def test_admin_global_save_updates_structured_materials_on_imported_card(connection):
    card_id = import_ready_card(
        "27121",
        raw_material_a="LDPE; Initial A | 80%",
        raw_material_b="",
        raw_material_c="",
        linear_pe="LLDPE; Initial L | 20%",
        antistatic="",
        masterbatch="",
        chalk="",
    )
    card = db.fetch_admin_card_detail(card_id)

    response = asyncio.run(
        save_admin_card_changes(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(card["version"])),
                        ("material_category__raw_material_a", "reLDPE"),
                        ("planned_material__raw_material_a", "Recycled LDPE"),
                        ("recipe_percent__raw_material_a", "80"),
                        ("material_category__linear_pe", "LLDPE"),
                        ("planned_material__linear_pe", "SABIC 119ZJ"),
                        ("recipe_percent__linear_pe", "20"),
                    ]
                )
            ),
            card_id,
        )
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert updated["raw_material_a"] == "reLDPE; Recycled LDPE | 80%"
    assert updated["linear_pe"] == "LLDPE; SABIC 119ZJ | 20%"
    components = {
        component_key: (source_text, category, planned_material, percent)
        for component_key, source_text, category, planned_material, percent in recipe_component_snapshot(card_id)
    }
    assert components["raw_material_a"] == (
        "reLDPE; Recycled LDPE | 80%",
        "reLDPE",
        "Recycled LDPE",
        "80",
    )
    assert components["linear_pe"] == (
        "LLDPE; SABIC 119ZJ | 20%",
        "LLDPE",
        "SABIC 119ZJ",
        "20",
    )


def test_admin_global_save_accepts_multi_word_category_as_free_text(connection):
    card_id = import_ready_card(
        "27124",
        raw_material_a="LDPE; Initial A | 80%",
        raw_material_b="",
        raw_material_c="",
        linear_pe="LLDPE; Initial L | 20%",
        antistatic="",
        masterbatch="",
        chalk="",
    )
    card = db.fetch_admin_card_detail(card_id)

    response = asyncio.run(
        save_admin_card_changes(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(card["version"])),
                        ("material_category__raw_material_a", "UV Protection"),
                        ("planned_material__raw_material_a", "Additech UV Shield XZ-204"),
                        ("recipe_percent__raw_material_a", "2"),
                        ("material_category__linear_pe", "LLDPE"),
                        ("planned_material__linear_pe", "SABIC 119ZJ"),
                        ("recipe_percent__linear_pe", "98"),
                    ]
                )
            ),
            card_id,
        )
    )
    updated = db.fetch_admin_card_detail(card_id)
    components = {
        component_key: (source_text, category, planned_material, percent)
        for component_key, source_text, category, planned_material, percent in recipe_component_snapshot(card_id)
    }

    assert response.status_code == 303
    assert updated["raw_material_a"] == "UV Protection; Additech UV Shield XZ-204 | 2%"
    assert components["raw_material_a"] == (
        "UV Protection; Additech UV Shield XZ-204 | 2%",
        "UV Protection",
        "Additech UV Shield XZ-204",
        "2",
    )


@pytest.mark.parametrize(
    ("category", "planned_material"),
    [
        ("UV; Protection", "Additech"),
        ("UV Protection", "Additech; Shield"),
    ],
)
def test_admin_global_save_rejects_semicolon_in_structured_recipe_fields(
    connection,
    category,
    planned_material,
):
    card_id = import_ready_card(
        f"27125-{category.count(';')}{planned_material.count(';')}",
        raw_material_a="LDPE; Initial A | 80%",
        raw_material_b="",
        raw_material_c="",
        linear_pe="LLDPE; Initial L | 20%",
        antistatic="",
        masterbatch="",
        chalk="",
    )
    before = db.fetch_admin_card_detail(card_id)

    response = asyncio.run(
        save_admin_card_changes(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(before["version"])),
                        ("material_category__raw_material_a", category),
                        ("planned_material__raw_material_a", planned_material),
                        ("recipe_percent__raw_material_a", "2"),
                        ("material_category__linear_pe", "LLDPE"),
                        ("planned_material__linear_pe", "SABIC 119ZJ"),
                        ("recipe_percent__linear_pe", "98"),
                    ]
                )
            ),
            card_id,
        )
    )
    body = response.body.decode("utf-8")
    after = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 200
    assert "Рецептата не може да бъде записана" in body
    assert ";" in body
    assert after["version"] == before["version"]
    assert after["raw_material_a"] == before["raw_material_a"]


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
                        *admin_material_form_items(
                            card_id,
                            overrides={
                                "raw_material_a": {
                                    "material_category": "LLDPE",
                                    "planned_material": "Global planned A",
                                    "recipe_percent": "50",
                                    "actual_material": "Global actual A",
                                    "batch_lot": "Global batch A",
                                }
                            },
                        ),
                        ("tare_weight", "2.00"),
                        ("current_pallet_number", "4"),
                        (f"gross_weight__{roll_id}", "60.00"),
                        (f"tare_weight__{roll_id}", "3.00"),
                        (f"pallet_number__{roll_id}", "2"),
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
    assert updated["raw_material_a"] == "LLDPE; Global planned A | 50%"
    assert (
        updated["recipe_actual_entries"]["raw_material_a"]["actual_material_used"]
        == "Global actual A"
    )
    assert updated["recipe_actual_entries"]["raw_material_a"]["batch_lot"] == "Global batch A"
    assert updated["tare_weight"] == 2
    assert updated["current_pallet_number"] == 4
    assert updated["roll_entries"][0]["gross_weight"] == 60
    assert updated["roll_entries"][0]["tare_weight"] == 3
    assert updated["roll_entries"][0]["pallet_number"] == 2
    assert updated["roll_entries"][0]["net_weight"] == 57


def test_admin_global_save_blocks_material_percent_total_over_100(connection):
    card_id = prepare_dense_completed_card("27122", roll_count=1)
    before = db.fetch_admin_card_detail(card_id)
    roll_id = int(before["roll_entries"][0]["id"])

    response = asyncio.run(
        save_admin_card_changes(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(before["version"])),
                        *admin_material_form_items(
                            card_id,
                            overrides={
                                "raw_material_a": {
                                    "recipe_percent": "350",
                                }
                            },
                        ),
                        ("tare_weight", "2.00"),
                        (f"gross_weight__{roll_id}", "60.00"),
                    ]
                )
            ),
            card_id,
        )
    )
    body = response.body.decode("utf-8")
    after = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 200
    assert "сборът на процентите трябва да е точно 100%" in body
    assert after["version"] == before["version"]
    assert after["raw_material_a"] == before["raw_material_a"]
    assert after["tare_weight"] == before["tare_weight"]
    assert after["roll_entries"][0]["gross_weight"] == before["roll_entries"][0]["gross_weight"]


def test_admin_global_save_blocks_invalid_material_percent_number(connection):
    card_id = prepare_dense_completed_card("27123", roll_count=1)
    before = db.fetch_admin_card_detail(card_id)

    response = asyncio.run(
        save_admin_card_changes(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(before["version"])),
                        *admin_material_form_items(
                            card_id,
                            overrides={
                                "raw_material_a": {
                                    "recipe_percent": "abc",
                                }
                            },
                        ),
                    ]
                )
            ),
            card_id,
        )
    )
    body = response.body.decode("utf-8")
    after = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 200
    assert "Суровина A: невалиден процент" in body
    assert after["version"] == before["version"]
    assert after["raw_material_a"] == before["raw_material_a"]


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
                        *admin_material_form_items(
                            card_id,
                            overrides={
                                "raw_material_a": {
                                    "planned_material": "Should Not Persist",
                                    "actual_material": "Should Not Persist",
                                    "batch_lot": "Should Not Persist",
                                }
                            },
                        ),
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


@pytest.mark.parametrize("failure", ("invalid_pallet", "foreign_roll", "stale_version"))
def test_admin_ledger_failure_rolls_back_prior_global_save_sections_in_caller_transaction(
    connection,
    failure,
):
    card_id = prepare_dense_completed_card(f"27110-{failure}", roll_count=1)
    before = db.fetch_admin_card_detail(card_id)
    roll_id = int(before["roll_entries"][0]["id"])
    foreign_card_id: int | None = None
    foreign_before: dict[str, object] | None = None
    foreign_roll_id: int | None = None
    if failure == "foreign_roll":
        foreign_card_id = prepare_dense_completed_card("27111-foreign-roll", roll_count=1)
        foreign_before = db.fetch_admin_card_detail(foreign_card_id)
        foreign_roll_id = int(foreign_before["roll_entries"][0]["id"])
    before_segments = [
        (segment["started_at"], segment["ended_at"], segment["end_reason"])
        for segment in before["timing_segments"]
    ]
    imported_fields = current_import_fields(card_id)
    imported_fields["customer"] = "Transaction customer"
    planned_materials = {
        field: str(before[field] or "")
        for field in (
            "raw_material_a",
            "raw_material_b",
            "raw_material_c",
            "linear_pe",
            "antistatic",
            "masterbatch",
            "chalk",
        )
    }
    planned_materials["raw_material_a"] = "LDPE; Transaction planned A | 50%"
    actual_entries = {
        "raw_material_a": {
            "actual_material_used": "Transaction actual A",
            "batch_lot": "Transaction batch A",
        }
    }

    with db.connect() as caller_connection:
        caller_connection.execute("BEGIN IMMEDIATE")
        imported_result = db.update_admin_imported_fields(
            card_id,
            before["version"],
            imported_fields,
            connection=caller_connection,
        )
        assert imported_result.ok
        material_version = int(
            caller_connection.execute(
                "SELECT version FROM cards WHERE id = ?", (card_id,)
            ).fetchone()["version"]
        )
        material_result = db.update_admin_material_ledger(
            card_id,
            material_version,
            planned_materials,
            actual_entries,
            connection=caller_connection,
        )
        assert material_result.ok
        ledger_version = int(
            caller_connection.execute(
                "SELECT version FROM cards WHERE id = ?", (card_id,)
            ).fetchone()["version"]
        )

        if failure == "invalid_pallet":
            result = db.update_admin_roll_ledger(
                card_id,
                ledger_version,
                tare_weight="2.00",
                current_pallet_number="1000",
                roll_updates={roll_id: {"pallet_number": "2", "gross_weight": "60.00"}},
                delete_roll_ids=set(),
                new_gross_weights=[],
                connection=caller_connection,
            )
        elif failure == "foreign_roll":
            assert foreign_roll_id is not None
            result = db.update_admin_roll_ledger(
                card_id,
                ledger_version,
                tare_weight="2.00",
                current_pallet_number="2",
                roll_updates={foreign_roll_id: {"pallet_number": "2", "gross_weight": "60.00"}},
                delete_roll_ids=set(),
                new_gross_weights=[],
                connection=caller_connection,
            )
        else:
            result = db.update_admin_roll_ledger(
                card_id,
                before["version"],
                tare_weight="2.00",
                current_pallet_number="2",
                roll_updates={roll_id: {"pallet_number": "2", "gross_weight": "60.00"}},
                delete_roll_ids=set(),
                new_gross_weights=[],
                connection=caller_connection,
            )

        assert not result.ok
        caller_connection.rollback()

    after = db.fetch_admin_card_detail(card_id)

    assert after["version"] == before["version"]
    assert after["customer"] == before["customer"]
    assert after["raw_material_a"] == before["raw_material_a"]
    assert after["recipe_actual_entries"]["raw_material_a"] == (
        before["recipe_actual_entries"]["raw_material_a"]
    )
    assert after["tare_weight"] == before["tare_weight"]
    assert after["current_pallet_number"] == before["current_pallet_number"]
    assert [
        (roll["gross_weight"], roll["tare_weight"], roll["net_weight"], roll["pallet_number"])
        for roll in after["roll_entries"]
    ] == [
        (roll["gross_weight"], roll["tare_weight"], roll["net_weight"], roll["pallet_number"])
        for roll in before["roll_entries"]
    ]
    assert [
        (segment["started_at"], segment["ended_at"], segment["end_reason"])
        for segment in after["timing_segments"]
    ] == before_segments
    if foreign_card_id is not None:
        assert foreign_before is not None
        foreign_after = db.fetch_admin_card_detail(foreign_card_id)
        assert foreign_after["version"] == foreign_before["version"]
        assert [
            (roll["gross_weight"], roll["tare_weight"], roll["net_weight"], roll["pallet_number"])
            for roll in foreign_after["roll_entries"]
        ] == [
            (roll["gross_weight"], roll["tare_weight"], roll["net_weight"], roll["pallet_number"])
            for roll in foreign_before["roll_entries"]
        ]


def test_admin_global_save_rolls_back_recipe_components_when_timing_is_invalid(connection):
    card_id = prepare_dense_completed_card("27109", roll_count=1)
    seed_fields = current_import_fields(card_id)
    seed_fields["raw_material_a"] = "LDPE; Before Rollback | 80%"
    seed_fields["raw_material_b"] = ""
    seed_fields["raw_material_c"] = ""
    seed_fields["linear_pe"] = "LLDPE; Before Rollback | 20%"
    seed_fields["antistatic"] = ""
    seed_fields["masterbatch"] = ""
    seed_fields["chalk"] = ""
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
                        ("raw_material_a", "LDPE; After Rollback | 70%"),
                        ("linear_pe", "LLDPE; After Rollback | 30%"),
                        *admin_material_form_items(
                            card_id,
                            overrides={
                                "raw_material_a": {
                                    "planned_material": "Should Not Persist",
                                }
                            },
                        ),
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
        ("raw_material_a", "LDPE; Before Rollback | 80%", "LDPE", "Before Rollback", "80"),
        ("linear_pe", "LLDPE; Before Rollback | 20%", "LLDPE", "Before Rollback", "20"),
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
            "raw_material_a": "LDPE; Corrected planned A | 50%",
            "raw_material_b": "LLDPE; Corrected planned B | 30%",
            "raw_material_c": "MDPE; Corrected planned C | 5%",
            "linear_pe": "LLDPE; Corrected linear | 8%",
            "antistatic": "Antistatic; Corrected antistatic | 1%",
            "masterbatch": "Masterbatch; Corrected masterbatch | 4%",
            "chalk": "Filler; Corrected chalk | 2%",
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
    assert card["raw_material_a"] == "LDPE; Corrected planned A | 50%"
    assert card["raw_material_b"] == "LLDPE; Corrected planned B | 30%"
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
        planned_materials={
            "raw_material_a": "LDPE; Corrected planned A | 50%",
            "raw_material_b": "LLDPE; Corrected planned B | 30%",
            "raw_material_c": "MDPE; Corrected planned C | 5%",
            "linear_pe": "LLDPE; Corrected linear | 8%",
            "antistatic": "Antistatic; Corrected antistatic | 1%",
            "masterbatch": "Masterbatch; Corrected masterbatch | 4%",
            "chalk": "Filler; Corrected chalk | 2%",
        },
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
        roll_updates={
            int(first_roll["id"]): {"gross_weight": "55.00", "tare_weight": "2.00"}
        },
        delete_roll_ids={int(second_roll["id"])},
        new_gross_weights=["56.25"],
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert updated["tare_weight"] == 1.5
    assert updated["roll_count"] == 3
    assert [roll["roll_number"] for roll in updated["roll_entries"]] == [1, 2, 3]
    assert updated["roll_entries"][0]["gross_weight"] == 55
    assert updated["roll_entries"][0]["tare_weight"] == 2
    assert updated["roll_entries"][0]["net_weight"] == 53
    assert updated["roll_entries"][2]["gross_weight"] == 56.25
    assert updated["roll_entries"][2]["tare_weight"] == 1.5
    assert updated["roll_entries"][2]["net_weight"] == 54.75
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


def test_admin_roll_ledger_current_pallet_and_roll_snapshots_are_atomic(connection):
    card_id = prepare_dense_completed_card("27025", roll_count=3)
    card = db.fetch_admin_card_detail(card_id)
    first_id = int(card["roll_entries"][0]["id"])
    middle_id = int(card["roll_entries"][1]["id"])
    last_id = int(card["roll_entries"][2]["id"])

    result = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=card["version"],
        tare_weight="1.50",
        current_pallet_number="7",
        roll_updates={
            first_id: {"pallet_number": "1", "gross_weight": "55.00"},
            last_id: {"pallet_number": "3"},
        },
        delete_roll_ids={middle_id},
        new_gross_weights=["56.25"],
    )
    updated = db.fetch_admin_card_detail(card_id)

    changed = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=updated["version"],
        tare_weight="1.50",
        roll_updates={first_id: {"pallet_number": "2"}},
        delete_roll_ids=set(),
        new_gross_weights=[],
    )
    changed_card = db.fetch_admin_card_detail(card_id)
    cleared = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=changed_card["version"],
        tare_weight="1.50",
        roll_updates={first_id: {"pallet_number": ""}},
        delete_roll_ids=set(),
        new_gross_weights=[],
    )
    final_card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert changed.ok
    assert cleared.ok
    assert updated["current_pallet_number"] == 7
    assert final_card["current_pallet_number"] == 7
    assert [(roll["roll_number"], roll["pallet_number"], roll["gross_weight"], roll["tare_weight"])
            for roll in final_card["roll_entries"]] == [
        (1, None, 55, 1.25),
        (2, 3, 51.2, 1.25),
        (3, 7, 56.25, 1.5),
    ]


def test_admin_roll_ledger_current_pallet_only_save_is_allowed_while_paused(connection):
    card_id = import_ready_card("27026")
    assert db.release_card(card_id, machine_id=1, machine_sequence=1, loaded_version=card_version(card_id)).ok
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.pause_production_timing(card_id, card_version(card_id)).ok
    before = db.fetch_admin_card_detail(card_id)

    saved = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=before["version"],
        tare_weight="",
        current_pallet_number="4",
        roll_updates={},
        delete_roll_ids=set(),
        new_gross_weights=[],
    )
    after = db.fetch_admin_card_detail(card_id)

    cleared = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=after["version"],
        tare_weight="",
        current_pallet_number="",
        roll_updates={},
        delete_roll_ids=set(),
        new_gross_weights=[],
    )
    final_card = db.fetch_admin_card_detail(card_id)

    assert saved.ok
    assert cleared.ok
    assert after["current_pallet_number"] == 4
    assert after["version"] == before["version"] + 1
    assert final_card["current_pallet_number"] is None


def test_admin_roll_ledger_blocks_pallet_snapshot_mutation_while_paused(connection):
    card_id = import_ready_card("27027")
    assert db.release_card(card_id, machine_id=1, machine_sequence=1, loaded_version=card_version(card_id)).ok
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "25.00").ok
    assert db.pause_production_timing(card_id, card_version(card_id)).ok
    before = db.fetch_admin_card_detail(card_id)
    roll_id = int(before["roll_entries"][0]["id"])

    blocked = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=before["version"],
        tare_weight="1.00",
        current_pallet_number=None,
        roll_updates={roll_id: {"pallet_number": "4"}},
        delete_roll_ids=set(),
        new_gross_weights=[],
    )
    after = db.fetch_admin_card_detail(card_id)

    assert not blocked.ok
    assert after["version"] == before["version"]
    assert after["roll_entries"][0]["pallet_number"] is None


@pytest.mark.parametrize("invalid_pallet", ("1000", "15+1"))
def test_admin_roll_ledger_rejects_invalid_pallet_before_writing_tare_or_rolls(
    connection,
    invalid_pallet,
):
    card_id = prepare_dense_completed_card("27028", roll_count=1)
    before = db.fetch_admin_card_detail(card_id)
    roll_id = int(before["roll_entries"][0]["id"])

    result = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=before["version"],
        tare_weight="2.00",
        current_pallet_number=invalid_pallet,
        roll_updates={roll_id: {"pallet_number": "2", "gross_weight": "60.00"}},
        delete_roll_ids=set(),
        new_gross_weights=[],
    )
    after = db.fetch_admin_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Палетът трябва да бъде цяло число от 1 до 999.",)
    assert after["version"] == before["version"]
    assert after["tare_weight"] == before["tare_weight"]
    assert after["current_pallet_number"] == before["current_pallet_number"]
    assert after["roll_entries"][0]["gross_weight"] == before["roll_entries"][0]["gross_weight"]
    assert after["roll_entries"][0]["pallet_number"] == before["roll_entries"][0]["pallet_number"]


def test_admin_roll_ledger_rejects_malformed_roll_pallet_before_any_write(connection):
    card_id = prepare_dense_completed_card("PALLET-ADMIN-ROW-INVALID", roll_count=1)
    assert db.update_current_pallet_number(card_id, card_version(card_id), "7").ok
    before = db.fetch_admin_card_detail(card_id)
    roll_id = int(before["roll_entries"][0]["id"])

    result = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=before["version"],
        tare_weight="2.00",
        current_pallet_number="8",
        roll_updates={
            roll_id: {"pallet_number": "15+1", "gross_weight": "60.00"}
        },
        delete_roll_ids=set(),
        new_gross_weights=[],
    )
    after = db.fetch_admin_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Палетът трябва да бъде цяло число от 1 до 999.",)
    assert after["version"] == before["version"]
    assert after["tare_weight"] == before["tare_weight"]
    assert after["current_pallet_number"] == before["current_pallet_number"]
    assert [
        (roll["pallet_number"], roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
        for roll in after["roll_entries"]
    ] == [
        (roll["pallet_number"], roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
        for roll in before["roll_entries"]
    ]


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
        [
            ("loaded_version", str(loaded_version)),
            ("tare_weight", "1.50"),
            ("pallet_number__bad-id", "2"),
        ],
    ]

    for items in malformed_forms:
        response = asyncio.run(
            save_admin_roll_ledger(FormRequest(MultiItemForm(items)), card_id)
        )
        body = response.body.decode("utf-8")

        assert response.status_code == 200
        assert "Формата съдържа невалидна ролка." in body


def test_admin_roll_ledger_parser_returns_current_and_per_roll_pallets():
    parsed = roll_ledger_from_form(
        MultiItemForm(
            [
                ("tare_weight", "1.50"),
                ("current_pallet_number", "5"),
                ("gross_weight__17", "55.00"),
                ("pallet_number__17", "3"),
                ("pallet_number__18", "4"),
            ]
        )
    )

    assert parsed == (
        "1.50",
        "5",
        {
            17: {"gross_weight": "55.00", "pallet_number": "3"},
            18: {"pallet_number": "4"},
        },
        set(),
        [],
    )


def test_admin_roll_ledger_parser_distinguishes_omitted_current_pallet_from_blank():
    omitted = roll_ledger_from_form(MultiItemForm([("tare_weight", "1.50")]))
    explicit_blank = roll_ledger_from_form(
        MultiItemForm(
            [
                ("tare_weight", "1.50"),
                ("current_pallet_number", ""),
            ]
        )
    )

    assert omitted[1] is None
    assert explicit_blank[1] == ""


def test_admin_roll_ledger_older_client_omission_preserves_and_explicit_blank_clears_pallet(
    connection,
):
    card_id = prepare_dense_completed_card("PALLET-ADMIN-OMITTED", roll_count=1)
    assert db.update_current_pallet_number(card_id, card_version(card_id), "7").ok
    before = db.fetch_admin_card_detail(card_id)

    omitted_response = asyncio.run(
        save_admin_roll_ledger(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(before["version"])),
                        ("tare_weight", str(before["tare_weight"])),
                    ]
                )
            ),
            card_id,
        )
    )
    preserved = db.fetch_admin_card_detail(card_id)
    blank_response = asyncio.run(
        save_admin_roll_ledger(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(preserved["version"])),
                        ("tare_weight", str(preserved["tare_weight"])),
                        ("current_pallet_number", ""),
                    ]
                )
            ),
            card_id,
        )
    )
    cleared = db.fetch_admin_card_detail(card_id)

    assert omitted_response.status_code == 303
    assert preserved["current_pallet_number"] == 7
    assert blank_response.status_code == 303
    assert cleared["current_pallet_number"] is None


def test_admin_roll_ledger_route_saves_current_and_per_roll_pallets(connection):
    card_id = prepare_dense_completed_card("PALLET-ADMIN-LEDGER", roll_count=1)
    card = db.fetch_admin_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])

    response = asyncio.run(
        save_admin_roll_ledger(
            FormRequest(
                MultiItemForm(
                    [
                        ("loaded_version", str(card["version"])),
                        ("tare_weight", str(card["tare_weight"])),
                        ("current_pallet_number", "6"),
                        (f"pallet_number__{roll_id}", "2"),
                    ]
                )
            ),
            card_id,
        )
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/cards/{card_id}#rolls"
    assert updated["current_pallet_number"] == 6
    assert updated["roll_entries"][0]["pallet_number"] == 2


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
