from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .constants import (
    ACTIVE_TERMINAL_STATUSES,
    CARD_STATUSES,
    STATUS_LABELS,
    STATUS_IMPORTED,
    STATUS_PENDING,
    TERMINAL_ARCHIVE_STATUSES,
    TIMING_REASON_LABELS,
)
from .db import (
    MAX_SHIFT_COUNT,
    NO_ACTIVE_SHIFT_MESSAGE,
    STALE_CARD_MESSAGE,
    STALE_CONFIGURATION_MESSAGE,
    STALE_SHIFT_MESSAGE,
    add_timing_segment,
    add_roll_gross_weight,
    archive_completed_card,
    cancel_card,
    connect,
    database_summary,
    delete_timing_segment,
    delete_roll_entry,
    delete_admin_imported_card,
    end_shift,
    fetch_active_shift,
    fetch_cards_by_status,
    fetch_admin_card_detail,
    fetch_admin_cards,
    fetch_import_batch_result,
    fetch_terminal_configuration,
    fetch_terminal_shift_page_state,
    fetch_terminal_card_detail,
    fetch_machine_queues,
    fetch_machines,
    fetch_recent_import_batches,
    fetch_shift_summary,
    fetch_shift_window_state,
    finish_card,
    init_db,
    pause_production_timing,
    release_card,
    resume_production_timing,
    restore_cancelled_card,
    start_shift,
    start_production_timing,
    terminal_snapshot as fetch_terminal_snapshot,
    update_timing_segment,
    update_admin_imported_fields,
    update_admin_material_ledger,
    update_admin_roll_ledger,
    update_admin_timing_ledger,
    update_card_planning,
    update_roll_gross_weight,
    update_roll_weight,
    update_tare_weight,
    update_terminal_recipe_actual_entries,
    update_terminal_roll_corrections,
    update_shift_count,
    update_active_shift_number,
    unrelease_pending_card,
)
from .deployment import deployment_metadata
from .importer import IMPORT_FIELDS, csv_template, import_cards_from_csv
from .printing import build_print_readiness
from .recipe_parser import RECIPE_SOURCE_FIELDS
from .recipe_parser import parse_recipe_source_fields
from .rules import RECIPE_RELEASE_FIELD_LABELS, RuleResult, target_gross_weight_from_card

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

CARD_NOT_FOUND_MESSAGE = "Картата не е намерена."
INVALID_LOADED_VERSION_MESSAGE = "Версията на заредената карта е невалидна. Презаредете картата."
TERMINAL_CARD_UNAVAILABLE_MESSAGE = "Картата не е налична на терминала."
DEFAULT_PLANNING_ANCHOR = "unreleased-queue"
DRAFT_SORT_DEFAULT = "order_number"
DRAFT_SORT_DIRECTIONS = {"asc", "desc"}
DRAFT_SORT_LABELS = {
    "order_number": "Поръчка",
    "delivery_date": "Доставка",
    "customer": "Клиент",
    "product_type": "Изделие",
}
SAFE_ANCHOR_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

TERMINAL_NOTICE_MESSAGES = {
    "materials_saved": ("Материалите са записани.",),
    "tare_saved": ("Шпула е записана.",),
    "roll_saved": ("Ролката е записана.",),
    "rolls_saved": ("Ролките са записани.",),
    "roll_updated": ("Ролката е коригирана.",),
    "roll_deleted": ("Ролката е изтрита.",),
    "timing_started": ("Времето е стартирано.",),
    "timing_paused": ("Времето е паузирано.",),
    "timing_resumed": ("Времето е продължено.",),
    "card_finished": ("Картата е приключена.",),
    "shift_changed": ("Номерът на смяната е коригиран.",),
}

SHIFT_HISTORY_PREVIEW_SIZE = 5
SHIFT_HISTORY_PAGE_SIZE = 10
SHIFT_HISTORY_PAGE_WINDOW = 5

ADMIN_SETTINGS_NOTICE_MESSAGES = {
    "shift_count_saved": ("Броят смени е записан.",),
}

IMPORT_ACTION_LABELS = {
    "blocked": "блокиран",
    "created": "създаден",
    "skipped": "пропуснат",
    "updated": "обновен",
}

IMPORT_FIELD_LABELS = {
    "order_number": "№ поръчка",
    "order_date": "Дата",
    "delivery_date": "Дата доставка",
    "customer": "Клиент",
    "city": "Град",
    "product_type": "Вид изделие",
    "ordered_gross_kg": "Поръчано бруто, кг",
    "ordered_rolls": "Поръчани ролки",
    "ordered_meters": "Поръчани метри",
    "ordered_units": "Поръчани бройки",
    "product_form": "Вид заготовка",
    "material": "Материал",
    "size_thickness": "Размер/дебелина",
    "notes": "Забележки",
    "printing_sequence": "Печат - ред",
    "extrusion_sequence": "Екструзия - ред",
    "rewinding_slitting_sequence": "Пренавиване/рязане - ред",
    "confection_sequence": "Конфекция - ред",
    "extrusion_folding": "Фалдиране",
    "extrusion_next_operation": "Следваща операция",
    "extrusion_treatment": "Третиране",
    "raw_material_a": "A",
    "raw_material_b": "B",
    "raw_material_c": "C",
    "linear_pe": "Линеен",
    "antistatic": "Антистатик",
    "masterbatch": "Мастербач",
    "chalk": "Креда",
    "packaging_method": "Опаковка",
}

RECIPE_FIELD_ROWS = (
    ("A", "raw_material_a"),
    ("B", "raw_material_b"),
    ("C", "raw_material_c"),
    ("Линеен", "linear_pe"),
    ("Антистатик", "antistatic"),
    ("Мастербач", "masterbatch"),
    ("Креда", "chalk"),
)

ORDERED_AMOUNT_FIELDS = (
    ("ordered_gross_kg", "Поръчано бруто", "кг"),
    ("ordered_rolls", "Поръчани ролки", "ролки"),
    ("ordered_meters", "Поръчани метри", "м"),
    ("ordered_units", "Поръчани бройки", "бр."),
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Терминал Екструдиране", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


def admin_import_context(**extra: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "admin_section": "import",
        "recent_imports": fetch_recent_import_batches(),
        "summary": database_summary(),
    }
    context.update(extra)
    return context


def admin_settings_context(**extra: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "admin_section": "settings",
        "configuration": fetch_terminal_configuration(),
        "maximum_shift_count": MAX_SHIFT_COUNT,
    }
    context.update(extra)
    return context


def admin_planning_context(
    draft_sort: str = DRAFT_SORT_DEFAULT,
    draft_dir: str = "asc",
    **extra: Any,
) -> dict[str, Any]:
    machine_queues = fetch_machine_queues()
    normalized_sort, normalized_dir = normalize_draft_sort(draft_sort, draft_dir)
    draft_cards = sorted_draft_cards(
        fetch_cards_by_status((STATUS_IMPORTED,)),
        normalized_sort,
        normalized_dir,
    )
    context: dict[str, Any] = {
        "admin_section": "planning",
        "draft_cards": draft_cards,
        "draft_sort": normalized_sort,
        "draft_dir": normalized_dir,
        "draft_sort_links": build_draft_sort_links(normalized_sort, normalized_dir),
        "machine_queues": machine_queues,
        "machines": [queue["machine"] for queue in machine_queues],
        "summary": database_summary(),
        "status_labels": STATUS_LABELS,
    }
    context.update(extra)
    return context


def admin_card_detail_context(card_id: int, **extra: Any) -> dict[str, Any] | None:
    card = fetch_admin_card_detail(card_id)
    if not card:
        return None
    card["total_production_duration"] = format_duration(
        card["total_production_seconds"],
    )
    recipe_rows = build_recipe_rows(card)
    context: dict[str, Any] = {
        "admin_section": "cards",
        "card": card,
        "import_fields": IMPORT_FIELDS,
        "import_field_labels": IMPORT_FIELD_LABELS,
        "status_labels": STATUS_LABELS,
        "timing_reason_labels": TIMING_REASON_LABELS,
        "quantity_lines": build_ordered_amount_lines(card),
        "recipe_rows": recipe_rows,
    }
    context.update(extra)
    return context


def admin_card_post_response(
    request: Request,
    card_id: int,
    result_name: str,
    result: RuleResult,
    anchor: str | None = None,
):
    if result.ok:
        suffix = f"#{anchor}" if anchor else ""
        return RedirectResponse(url=f"/admin/cards/{card_id}{suffix}", status_code=303)

    context = admin_card_detail_context(card_id, **{result_name: result})
    if context is None:
        return PlainTextResponse(CARD_NOT_FOUND_MESSAGE, status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


def safe_planning_anchor(anchor: str) -> str:
    candidate = anchor.strip()
    if SAFE_ANCHOR_PATTERN.fullmatch(candidate):
        return candidate
    return DEFAULT_PLANNING_ANCHOR


def normalize_draft_sort(sort_key: str, sort_dir: str) -> tuple[str, str]:
    normalized_sort = sort_key if sort_key in DRAFT_SORT_LABELS else DRAFT_SORT_DEFAULT
    normalized_dir = sort_dir if sort_dir in DRAFT_SORT_DIRECTIONS else "asc"
    return normalized_sort, normalized_dir


def draft_date_sort_value(value: Any) -> tuple[int, str]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return (1, "")
    for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return (0, datetime.strptime(raw_value, date_format).date().isoformat())
        except ValueError:
            continue
    return (0, raw_value)


def draft_sort_value(card: dict[str, Any], sort_key: str) -> tuple[int, str]:
    if sort_key == "delivery_date":
        return draft_date_sort_value(card.get("delivery_date"))
    return (0, str(card.get(sort_key) or "").casefold())


def sorted_draft_cards(
    cards: list[dict[str, Any]],
    sort_key: str,
    sort_dir: str,
) -> list[dict[str, Any]]:
    reverse = sort_dir == "desc"
    ordered_cards = sorted(
        cards,
        key=lambda card: (
            str(card.get("order_number") or "").casefold(),
            int(card.get("id") or 0),
        ),
    )
    if sort_key == "delivery_date" and reverse:
        # Keep missing dates last; reversing the full key would move blanks first.
        dated_cards = []
        missing_date_cards = []
        for card in ordered_cards:
            missing_date, _ = draft_date_sort_value(card.get("delivery_date"))
            if missing_date:
                missing_date_cards.append(card)
            else:
                dated_cards.append(card)
        return sorted(
            dated_cards,
            key=lambda card: draft_date_sort_value(card.get("delivery_date")),
            reverse=True,
        ) + missing_date_cards
    return sorted(
        ordered_cards,
        key=lambda card: draft_sort_value(card, sort_key),
        reverse=reverse,
    )


def build_draft_sort_links(active_sort: str, active_dir: str) -> dict[str, dict[str, str]]:
    links: dict[str, dict[str, str]] = {}
    for sort_key, label in DRAFT_SORT_LABELS.items():
        next_dir = "desc" if active_sort == sort_key and active_dir == "asc" else "asc"
        query = urlencode({"draft_sort": sort_key, "draft_dir": next_dir})
        aria_sort = "none"
        if active_sort == sort_key:
            aria_sort = "ascending" if active_dir == "asc" else "descending"
        links[sort_key] = {
            "label": label,
            "href": f"/admin/planning?{query}#{DEFAULT_PLANNING_ANCHOR}",
            "aria_sort": aria_sort,
        }
    return links


def build_ordered_amount_lines(card: dict[str, Any]) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for field, label, unit in ORDERED_AMOUNT_FIELDS:
        value = str(card.get(field) or "").strip()
        if value:
            lines.append(
                {
                    "field": field,
                    "label": label,
                    "value": value,
                    "unit": unit,
                    "display": f"{label}: {value} {unit}",
                }
            )
    return lines


def decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def whole_decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP), "f")


def recipe_percent_display(value: Any, *, rounded: bool = False) -> str:
    percent = decimal_from_display(value)
    if percent is not None and rounded:
        return f"{whole_decimal_text(percent)}%"
    return f"{decimal_text(percent)}%" if percent is not None else ""


def recipe_components_by_key(card: dict[str, Any]) -> dict[str, dict[str, Any]]:
    components = card.get("recipe_components") or []
    if not isinstance(components, list):
        return {}
    return {str(component["component_key"]): component for component in components}


def planned_kg_display(
    card: dict[str, Any],
    recipe_percent: Any,
    *,
    rounded: bool = False,
) -> str:
    target = target_gross_weight_from_card(card)
    percent = decimal_from_display(recipe_percent)
    if target is None or percent is None:
        return ""
    planned_kg = target * percent / Decimal("100")
    if rounded:
        return whole_decimal_text(planned_kg)
    return decimal_weight_display(planned_kg)


def build_recipe_rows(
    card: dict[str, Any],
    *,
    include_all_source_fields: bool = True,
    rounded_operator_values: bool = False,
) -> list[dict[str, Any]]:
    actual_entries = card.get("recipe_actual_entries") or {}
    if not isinstance(actual_entries, dict):
        actual_entries = {}
    components = recipe_components_by_key(card)
    source_labels = {field: label for label, field in RECIPE_FIELD_ROWS}

    fields: list[str] = []
    for field in RECIPE_SOURCE_FIELDS:
        source_text = str(card.get(field) or "")
        has_component = field in components
        entry = actual_entries.get(field, {}) if isinstance(actual_entries, dict) else {}
        has_actual_entry = bool(
            isinstance(entry, dict)
            and (entry.get("actual_material_used") or entry.get("batch_lot"))
        )
        if include_all_source_fields or has_component or source_text.strip() or has_actual_entry:
            fields.append(field)

    rows: list[dict[str, Any]] = []
    for field in fields:
        source_text = str(card.get(field) or "")
        component = components.get(field)
        entry = actual_entries.get(field, {}) if isinstance(actual_entries, dict) else {}
        actual_material = str(entry.get("actual_material_used") or "")
        batch = str(entry.get("batch_lot") or "")
        if field == "raw_material_a" and field not in actual_entries:
            actual_material = str(card.get("actual_raw_material_used") or "")
            batch = str(card.get("raw_material_batch_lot") or "")

        if component:
            material_category = str(component.get("material_category") or "")
            normalized_planned_material = str(component.get("planned_material") or "")
            planned_material = normalized_planned_material or material_category
            planned_material_edit = normalized_planned_material
            recipe_percent = recipe_percent_display(
                component.get("recipe_percent"),
                rounded=rounded_operator_values,
            )
            recipe_percent_edit = recipe_percent.rstrip("%")
            planned_kg = planned_kg_display(
                card,
                component.get("recipe_percent"),
                rounded=rounded_operator_values,
            )
            is_structured = True
        else:
            planned_material = source_text
            planned_material_edit = source_text
            material_category = ""
            recipe_percent = ""
            recipe_percent_edit = ""
            planned_kg = ""
            is_structured = False

        source_label = source_labels.get(field, field)
        rows.append(
            {
                "field": field,
                "source_label": source_label,
                "label": source_label,
                "material_category": material_category,
                "planned_material": planned_material,
                "planned_material_edit": planned_material_edit,
                "recipe_percent": recipe_percent,
                "recipe_percent_edit": recipe_percent_edit,
                "planned_kg": planned_kg,
                "source_text": source_text,
                "planned": source_text,
                "actual_material": actual_material,
                "batch": batch,
                "has_actual": bool(actual_material or batch),
                "is_structured": is_structured,
            }
        )
    return rows


def build_terminal_recipe_rows(card: dict[str, Any]) -> list[dict[str, Any]]:
    return build_recipe_rows(
        card,
        include_all_source_fields=False,
        rounded_operator_values=True,
    )


def recipe_actual_entries_from_form(form: Any) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for key, value in form.multi_items():
        text_value = str(value or "")
        if key.startswith("actual_material__"):
            field = key.removeprefix("actual_material__")
            entry = entries.setdefault(
                field,
                {"actual_material_used": "", "batch_lot": ""},
            )
            entry["actual_material_used"] = text_value
        elif key.startswith("batch_lot__"):
            field = key.removeprefix("batch_lot__")
            entry = entries.setdefault(
                field,
                {"actual_material_used": "", "batch_lot": ""},
            )
            entry["batch_lot"] = text_value
    return entries


def material_ledger_from_form(
    form: Any,
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    planned_materials: dict[str, str] = {}
    actual_entries: dict[str, dict[str, str]] = {}
    for _, field in RECIPE_FIELD_ROWS:
        planned_materials[field] = compose_recipe_source_text(
            category=str(form.get(f"material_category__{field}") or ""),
            planned_material=str(form.get(f"planned_material__{field}") or ""),
            recipe_percent=str(form.get(f"recipe_percent__{field}") or ""),
        )
        actual_entries[field] = {
            "actual_material_used": str(form.get(f"actual_material__{field}") or ""),
            "batch_lot": str(form.get(f"batch_lot__{field}") or ""),
        }
    return planned_materials, actual_entries


def validate_recipe_structured_delimiters(form: Any) -> RuleResult:
    for label, field in RECIPE_FIELD_ROWS:
        category = str(form.get(f"material_category__{field}") or "")
        planned_material = str(form.get(f"planned_material__{field}") or "")
        if ";" in category or ";" in planned_material:
            return RuleResult(
                False,
                (
                    "Рецептата не може да бъде записана: "
                    f"Суровина {label}: категорията и материалът не могат да съдържат ;. "
                    "Коригирайте рецептата и опитайте отново.",
                ),
            )
    return RuleResult(True)


def normalize_recipe_percent_input(recipe_percent: str) -> str:
    percent = recipe_percent.strip()
    if not percent:
        return ""
    if percent.endswith("%"):
        percent = percent[:-1].strip()
    return f"{percent}%"


def compose_recipe_source_text(
    *,
    category: str,
    planned_material: str,
    recipe_percent: str,
) -> str:
    category = category.strip()
    planned_material = planned_material.strip()
    recipe_percent = normalize_recipe_percent_input(recipe_percent)
    if category and planned_material:
        identity = f"{category}; {planned_material}"
    else:
        identity = " ".join(part for part in (category, planned_material) if part)
    if not identity and not recipe_percent:
        return ""
    if recipe_percent:
        return f"{identity} | {recipe_percent}"
    return identity


def validate_admin_recipe_source_fields(source_fields: dict[str, str]) -> RuleResult:
    result = parse_recipe_source_fields(
        source_fields,
        require_semicolon_delimiter=True,
        reject_embedded_semicolon=True,
    )
    messages: list[str] = []
    for error in result.errors:
        if error.component_key == "__total__":
            reason = error.message
        else:
            label = RECIPE_RELEASE_FIELD_LABELS.get(error.component_key, error.component_key)
            reason = f"{label}: {error.message}"
        messages.append(
            f"Рецептата не може да бъде записана: {reason}. "
            "Коригирайте рецептата и опитайте отново."
        )
    return RuleResult(not messages, tuple(messages))


def roll_ledger_from_form(
    form: Any,
) -> tuple[str, dict[int, dict[str, str]], set[int], list[str]]:
    roll_updates: dict[int, dict[str, str]] = {}
    delete_roll_ids: set[int] = set()
    new_gross_weights: list[str] = []

    for key, value in form.multi_items():
        text_value = str(value or "")
        if key.startswith("gross_weight__"):
            roll_id = int(key.removeprefix("gross_weight__"))
            roll_updates.setdefault(roll_id, {})["gross_weight"] = text_value
        elif key.startswith("tare_weight__"):
            roll_id = int(key.removeprefix("tare_weight__"))
            roll_updates.setdefault(roll_id, {})["tare_weight"] = text_value
        elif key == "delete_roll_id":
            delete_roll_ids.add(int(text_value))
        elif key == "new_gross_weight":
            new_gross_weights.append(text_value)

    return (
        str(form.get("tare_weight") or ""),
        roll_updates,
        delete_roll_ids,
        new_gross_weights,
    )


def terminal_roll_corrections_from_form(form: Any) -> dict[int, dict[str, str]]:
    roll_updates: dict[int, dict[str, str]] = {}
    for key, value in form.multi_items():
        text_value = str(value or "")
        if key.startswith("gross_weight__"):
            roll_id = int(key.removeprefix("gross_weight__"))
            roll_updates.setdefault(roll_id, {})["gross_weight"] = text_value
        elif key.startswith("tare_weight__"):
            roll_id = int(key.removeprefix("tare_weight__"))
            roll_updates.setdefault(roll_id, {})["tare_weight"] = text_value
    return roll_updates


def timing_ledger_from_form(
    form: Any,
) -> tuple[dict[int, dict[str, str]], set[int], list[dict[str, str]]]:
    segment_updates: dict[int, dict[str, str]] = {}
    delete_segment_ids: set[int] = set()
    new_segment = {
        "started_at": str(form.get("new_started_at") or ""),
        "ended_at": str(form.get("new_ended_at") or ""),
        "end_reason": str(form.get("new_end_reason") or ""),
    }

    for key, value in form.multi_items():
        text_value = str(value or "")
        if key == "delete_segment_id":
            delete_segment_ids.add(int(text_value))
        elif "__" in key:
            field_name, segment_id_text = key.split("__", 1)
            if field_name in {"started_at", "ended_at", "end_reason"}:
                segment_id = int(segment_id_text)
                segment_updates.setdefault(segment_id, {})[field_name] = text_value

    return segment_updates, delete_segment_ids, [new_segment]


@app.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse(url="/terminal", status_code=303)


@app.get("/health")
async def health() -> dict:
    summary = database_summary()
    return {
        "status": "ok",
        **deployment_metadata(),
        **summary,
    }


@app.get("/cards/{card_id}/print")
async def print_card(
    request: Request,
    card_id: int,
    auto: str | None = None,
    source: str | None = None,
):
    readiness = build_print_readiness(card_id)
    terminal_source = source == "terminal"
    return templates.TemplateResponse(
        request,
        "print_card.html",
        {
            "card_id": card_id,
            "readiness": readiness,
            "print_data": readiness.data,
            "auto_print": auto == "1",
            "preview_url": (
                f"/cards/{card_id}/print?source=terminal"
                if terminal_source
                else f"/cards/{card_id}/print"
            ),
            "return_url": "/terminal" if terminal_source else f"/admin/cards/{card_id}",
            "return_label": "Към терминала" if terminal_source else "Към картата",
        },
    )


@app.get("/admin")
async def admin() -> RedirectResponse:
    return RedirectResponse(url="/admin/import", status_code=303)


@app.get("/admin/import")
async def admin_import(request: Request, batch_id: int | None = None):
    import_result = fetch_import_batch_result(batch_id)
    return templates.TemplateResponse(
        request,
        "admin_import.html",
        admin_import_context(
            import_result=import_result,
            import_action_labels=IMPORT_ACTION_LABELS,
        ),
    )


@app.get("/admin/settings")
async def admin_settings(request: Request, notice: str | None = None):
    return templates.TemplateResponse(
        request,
        "admin_settings.html",
        admin_settings_context(notice_messages=ADMIN_SETTINGS_NOTICE_MESSAGES.get(notice, ())),
    )


@app.post("/admin/settings/shifts")
async def save_admin_shift_settings(
    request: Request,
    shift_count: str = Form(...),
    loaded_version: int = Form(...),
):
    result = update_shift_count(loaded_version, shift_count)
    if result.ok:
        return RedirectResponse(
            url="/admin/settings?notice=shift_count_saved",
            status_code=303,
        )
    return templates.TemplateResponse(
        request,
        "admin_settings.html",
        admin_settings_context(
            settings_result=result,
            submitted_shift_count=shift_count,
            submitted_version=loaded_version,
            reload_required=result.messages == (STALE_CONFIGURATION_MESSAGE,),
        ),
    )


@app.get("/admin/import-template.csv")
async def import_template() -> PlainTextResponse:
    return PlainTextResponse(
        csv_template(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="extrusion_import_template.csv"'},
    )


@app.post("/admin/import")
async def import_csv(
    request: Request,
    csv_file: UploadFile = File(...),
    overwrite_existing: bool = Form(False),
):
    content = await csv_file.read()
    result = import_cards_from_csv(
        filename=csv_file.filename or "uploaded.csv",
        content=content,
        overwrite_existing=overwrite_existing,
    )

    if result.batch_id is not None:
        return RedirectResponse(
            url=f"/admin/import?batch_id={result.batch_id}",
            status_code=303,
        )

    return templates.TemplateResponse(
        request,
        "admin_import.html",
        admin_import_context(import_result=result, import_action_labels=IMPORT_ACTION_LABELS),
    )


@app.get("/admin/planning")
async def admin_planning(
    request: Request,
    draft_sort: str = DRAFT_SORT_DEFAULT,
    draft_dir: str = "asc",
):
    return templates.TemplateResponse(
        request,
        "admin_planning.html",
        admin_planning_context(draft_sort=draft_sort, draft_dir=draft_dir),
    )


@app.get("/admin/cards")
async def admin_cards(
    request: Request,
    order_number: str = "",
    customer: str = "",
    product: str = "",
    status: str = "",
):
    filters = {
        "order_number": order_number,
        "customer": customer,
        "product": product,
        "status": status,
    }
    return templates.TemplateResponse(
        request,
        "admin_cards.html",
        {
            "admin_section": "cards",
            "cards": fetch_admin_cards(filters),
            "filters": filters,
            "card_statuses": CARD_STATUSES,
            "status_labels": STATUS_LABELS,
            "summary": database_summary(),
        },
    )


@app.get("/admin/cards/{card_id}")
async def admin_card_detail(request: Request, card_id: int):
    context = admin_card_detail_context(card_id)
    if context is None:
        return PlainTextResponse(CARD_NOT_FOUND_MESSAGE, status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


@app.post("/admin/cards/{card_id}/imported-fields")
async def save_admin_imported_fields(request: Request, card_id: int):
    form = await request.form()
    parsed_version, imported_field_result = parse_loaded_version(
        str(form.get("loaded_version", ""))
    )
    if parsed_version is not None:
        preserved_fields, imported_field_result = imported_fields_from_form(card_id, form)
        if preserved_fields is not None:
            imported_field_result = validate_admin_recipe_source_fields(
                {field: preserved_fields.get(field, "") for field in RECIPE_SOURCE_FIELDS}
            )
            if imported_field_result.ok:
                imported_field_result = update_admin_imported_fields(
                    card_id=card_id,
                    loaded_version=parsed_version,
                    fields=preserved_fields,
                )

    return admin_card_post_response(
        request,
        card_id,
        "imported_field_result",
        imported_field_result,
        anchor="order",
    )


@app.post("/admin/cards/{card_id}/save-all")
async def save_admin_card_changes(request: Request, card_id: int):
    form = await request.form()
    parsed_version, save_all_result = parse_loaded_version(
        str(form.get("loaded_version", ""))
    )
    if parsed_version is not None:
        save_all_result = save_all_admin_card_changes(card_id, parsed_version, form)

    return admin_card_post_response(
        request,
        card_id,
        "save_all_result",
        save_all_result,
    )


def imported_fields_from_form(
    card_id: int,
    form: Any,
) -> tuple[dict[str, str] | None, RuleResult]:
    delimiter_result = validate_recipe_structured_delimiters(form)
    if not delimiter_result.ok:
        return None, delimiter_result

    submitted_fields = {key: str(value) for key, value in form.multi_items()}
    current_card = fetch_admin_card_detail(card_id)
    if current_card is None:
        return None, RuleResult(False, (CARD_NOT_FOUND_MESSAGE,))

    preserved_fields = {
        field: str(current_card[field] or "")
        for field in IMPORT_FIELDS
    }
    preserved_fields.update(
        {
            field: submitted_fields[field]
            for field in IMPORT_FIELDS
            if field in submitted_fields
        }
    )
    for field in RECIPE_SOURCE_FIELDS:
        structured_keys = (
            f"material_category__{field}",
            f"planned_material__{field}",
            f"recipe_percent__{field}",
        )
        if any(key in submitted_fields for key in structured_keys):
            preserved_fields[field] = compose_recipe_source_text(
                category=submitted_fields.get(f"material_category__{field}", ""),
                planned_material=submitted_fields.get(f"planned_material__{field}", ""),
                recipe_percent=submitted_fields.get(f"recipe_percent__{field}", ""),
            )
    return preserved_fields, RuleResult(True)


def current_card_version_and_status(
    card_id: int,
    connection: Any | None = None,
) -> tuple[int | None, str | None, RuleResult]:
    if connection is None:
        card = fetch_admin_card_detail(card_id)
    else:
        card = connection.execute(
            """
            SELECT version, status
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
    if card is None:
        return None, None, RuleResult(False, (CARD_NOT_FOUND_MESSAGE,))
    return int(card["version"]), str(card["status"]), RuleResult(True)


def save_all_admin_card_changes(
    card_id: int,
    loaded_version: int,
    form: Any,
) -> RuleResult:
    preserved_fields, result = imported_fields_from_form(card_id, form)
    if preserved_fields is None:
        return result
    recipe_result = validate_admin_recipe_source_fields(
        {field: preserved_fields.get(field, "") for field in RECIPE_SOURCE_FIELDS}
    )
    if not recipe_result.ok:
        return recipe_result

    with connect() as connection:
        result = update_admin_imported_fields(
            card_id=card_id,
            loaded_version=loaded_version,
            fields=preserved_fields,
            connection=connection,
        )
        if not result.ok:
            connection.rollback()
            return result

        current_version, current_status, result = current_card_version_and_status(
            card_id,
            connection,
        )
        if not result.ok:
            connection.rollback()
            return result
        if current_status == STATUS_IMPORTED:
            return RuleResult(True, ("Промените са записани.",))
        assert current_version is not None

        planned_materials, actual_entries = material_ledger_from_form(form)
        result = validate_admin_recipe_source_fields(planned_materials)
        if not result.ok:
            connection.rollback()
            return result
        result = update_admin_material_ledger(
            card_id=card_id,
            loaded_version=current_version,
            planned_materials=planned_materials,
            actual_entries=actual_entries,
            connection=connection,
        )
        if not result.ok:
            connection.rollback()
            return result

        current_version, _, result = current_card_version_and_status(card_id, connection)
        if not result.ok:
            connection.rollback()
            return result
        assert current_version is not None

        try:
            tare_weight, roll_updates, delete_roll_ids, new_gross_weights = (
                roll_ledger_from_form(form)
            )
        except ValueError:
            connection.rollback()
            return RuleResult(False, ("Формата съдържа невалидна ролка.",))
        result = update_admin_roll_ledger(
            card_id=card_id,
            loaded_version=current_version,
            tare_weight=tare_weight,
            roll_updates=roll_updates,
            delete_roll_ids=delete_roll_ids,
            new_gross_weights=new_gross_weights,
            connection=connection,
        )
        if not result.ok:
            connection.rollback()
            return result

        current_version, _, result = current_card_version_and_status(card_id, connection)
        if not result.ok:
            connection.rollback()
            return result
        assert current_version is not None

        try:
            segment_updates, delete_segment_ids, new_segments = timing_ledger_from_form(form)
        except ValueError:
            connection.rollback()
            return RuleResult(False, ("Формата съдържа невалиден времеви сегмент.",))
        result = update_admin_timing_ledger(
            card_id=card_id,
            loaded_version=current_version,
            segment_updates=segment_updates,
            delete_segment_ids=delete_segment_ids,
            new_segments=new_segments,
            connection=connection,
        )
        if not result.ok:
            connection.rollback()
            return result

    return RuleResult(True, ("Промените са записани.",))


@app.post("/admin/cards/{card_id}/delete")
async def delete_admin_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, delete_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        delete_result = delete_admin_imported_card(card_id, parsed_version)

    if delete_result.ok:
        return RedirectResponse(url="/admin/cards", status_code=303)

    context = admin_card_detail_context(card_id, delete_result=delete_result)
    if context is None:
        return PlainTextResponse(CARD_NOT_FOUND_MESSAGE, status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


@app.post("/admin/cards/{card_id}/release")
async def release_card_to_terminal(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    machine_id: str = Form(...),
    machine_sequence: str = Form(...),
    return_anchor: str = Form(DEFAULT_PLANNING_ANCHOR),
):
    parsed_version, release_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        parsed_planning, release_result = parse_planning_form(machine_id, machine_sequence)
        if parsed_planning is not None:
            release_result = release_card(
                card_id,
                parsed_planning["machine_id"],
                parsed_planning["machine_sequence"],
                loaded_version=parsed_version,
            )

    if release_result.ok:
        anchor = safe_planning_anchor(return_anchor)
        return RedirectResponse(url=f"/admin/planning#{anchor}", status_code=303)

    return templates.TemplateResponse(
        request,
        "admin_planning.html",
        admin_planning_context(release_result=release_result),
    )


@app.post("/admin/cards/{card_id}/planning")
async def update_admin_card_planning(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    machine_id: str = Form(...),
    machine_sequence: str = Form(...),
):
    parsed_version, planning_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        parsed_planning, planning_result = parse_planning_form(machine_id, machine_sequence)
        if parsed_planning is not None:
            planning_result = update_card_planning(
                card_id=card_id,
                loaded_version=parsed_version,
                machine_id=parsed_planning["machine_id"],
                machine_sequence=parsed_planning["machine_sequence"],
            )

    if planning_result.ok:
        return RedirectResponse(url="/admin/planning", status_code=303)

    return templates.TemplateResponse(
        request,
        "admin_planning.html",
        admin_planning_context(planning_result=planning_result),
    )


@app.post("/admin/cards/{card_id}/unrelease")
async def unrelease_admin_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    return_to: str = Form("planning"),
):
    parsed_version, workflow_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        workflow_result = unrelease_pending_card(card_id, parsed_version)

    if return_to == "detail":
        return admin_card_post_response(
            request,
            card_id,
            "workflow_result",
            workflow_result,
        )

    if workflow_result.ok:
        return RedirectResponse(url="/admin/planning", status_code=303)

    return templates.TemplateResponse(
        request,
        "admin_planning.html",
        admin_planning_context(planning_result=workflow_result),
    )


@app.post("/admin/cards/{card_id}/cancel")
async def cancel_admin_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, workflow_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        workflow_result = cancel_card(card_id, parsed_version)

    return admin_card_post_response(
        request,
        card_id,
        "workflow_result",
        workflow_result,
    )


@app.post("/admin/cards/{card_id}/restore")
async def restore_admin_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, workflow_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        workflow_result = restore_cancelled_card(card_id, parsed_version)

    return admin_card_post_response(
        request,
        card_id,
        "workflow_result",
        workflow_result,
    )


@app.post("/admin/cards/{card_id}/archive")
async def archive_admin_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, workflow_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        workflow_result = archive_completed_card(card_id, parsed_version)

    return admin_card_post_response(
        request,
        card_id,
        "workflow_result",
        workflow_result,
    )


@app.post("/admin/cards/{card_id}/production-materials")
async def save_admin_production_materials(
    request: Request,
    card_id: int,
):
    form = await request.form()
    loaded_version = str(form.get("loaded_version") or "")
    parsed_version, material_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        raw_material_brand_grade = (
            str(form.get("raw_material_brand_grade") or "")
            if "raw_material_brand_grade" in form
            else None
        )
        material_result = update_terminal_recipe_actual_entries(
            card_id=card_id,
            loaded_version=parsed_version,
            entries=recipe_actual_entries_from_form(form),
            raw_material_brand_grade=raw_material_brand_grade,
        )

    return admin_card_post_response(
        request,
        card_id,
        "material_result",
        material_result,
        anchor="materials",
    )


@app.post("/admin/cards/{card_id}/materials-ledger")
async def save_admin_materials_ledger(request: Request, card_id: int):
    form = await request.form()
    parsed_version, material_result = parse_loaded_version(
        str(form.get("loaded_version") or "")
    )
    if parsed_version is not None:
        material_result = validate_recipe_structured_delimiters(form)
        if material_result.ok:
            planned_materials, actual_entries = material_ledger_from_form(form)
            material_result = validate_admin_recipe_source_fields(planned_materials)
        if material_result.ok:
            material_result = update_admin_material_ledger(
                card_id=card_id,
                loaded_version=parsed_version,
                planned_materials=planned_materials,
                actual_entries=actual_entries,
            )

    return admin_card_post_response(
        request,
        card_id,
        "material_result",
        material_result,
        anchor="materials",
    )


@app.post("/admin/cards/{card_id}/tare")
async def save_admin_tare_weight(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    tare_weight: str = Form(""),
):
    parsed_version, roll_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        roll_result = update_tare_weight(card_id, parsed_version, tare_weight)

    return admin_card_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        anchor="rolls",
    )


@app.post("/admin/cards/{card_id}/rolls")
async def add_admin_roll_weight(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    gross_weight: str = Form(""),
):
    parsed_version, roll_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        roll_result = add_roll_gross_weight(card_id, parsed_version, gross_weight)

    return admin_card_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        anchor="rolls",
    )


@app.post("/admin/cards/{card_id}/roll-ledger")
async def save_admin_roll_ledger(request: Request, card_id: int):
    form = await request.form()
    parsed_version, roll_result = parse_loaded_version(
        str(form.get("loaded_version") or "")
    )
    if parsed_version is not None:
        try:
            tare_weight, roll_updates, delete_roll_ids, new_gross_weights = (
                roll_ledger_from_form(form)
            )
        except ValueError:
            roll_result = RuleResult(False, ("Формата съдържа невалидна ролка.",))
        else:
            roll_result = update_admin_roll_ledger(
                card_id=card_id,
                loaded_version=parsed_version,
                tare_weight=tare_weight,
                roll_updates=roll_updates,
                delete_roll_ids=delete_roll_ids,
                new_gross_weights=new_gross_weights,
            )

    return admin_card_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        anchor="rolls",
    )


@app.post("/admin/cards/{card_id}/rolls/{roll_id}")
async def save_admin_roll_weight(
    request: Request,
    card_id: int,
    roll_id: int,
    loaded_version: str = Form(...),
    gross_weight: str = Form(""),
    tare_weight: str | None = Form(None),
):
    parsed_version, roll_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        if tare_weight is None or not isinstance(tare_weight, str):
            roll_result = update_roll_gross_weight(
                card_id=card_id,
                roll_id=roll_id,
                loaded_version=parsed_version,
                gross_weight=gross_weight,
            )
        else:
            roll_result = update_roll_weight(
                card_id=card_id,
                roll_id=roll_id,
                loaded_version=parsed_version,
                gross_weight=gross_weight,
                tare_weight=tare_weight,
            )

    return admin_card_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        anchor="rolls",
    )


@app.post("/admin/cards/{card_id}/rolls/{roll_id}/delete")
async def delete_admin_roll_weight(
    request: Request,
    card_id: int,
    roll_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, roll_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        roll_result = delete_roll_entry(
            card_id=card_id,
            roll_id=roll_id,
            loaded_version=parsed_version,
        )

    return admin_card_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        anchor="rolls",
    )


@app.post("/admin/cards/{card_id}/timing-segments")
async def add_admin_timing_segment(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    started_at: str = Form(""),
    ended_at: str = Form(""),
    end_reason: str = Form(""),
):
    parsed_version, timing_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        timing_result = add_timing_segment(
            card_id=card_id,
            loaded_version=parsed_version,
            started_at=started_at,
            ended_at=ended_at,
            end_reason=end_reason,
        )

    return admin_card_post_response(
        request,
        card_id,
        "timing_result",
        timing_result,
        anchor="timing",
    )


@app.post("/admin/cards/{card_id}/timing-ledger")
async def save_admin_timing_ledger(request: Request, card_id: int):
    form = await request.form()
    parsed_version, timing_result = parse_loaded_version(
        str(form.get("loaded_version") or "")
    )
    if parsed_version is not None:
        try:
            segment_updates, delete_segment_ids, new_segments = (
                timing_ledger_from_form(form)
            )
        except ValueError:
            timing_result = RuleResult(False, ("Формата съдържа невалиден времеви сегмент.",))
        else:
            timing_result = update_admin_timing_ledger(
                card_id=card_id,
                loaded_version=parsed_version,
                segment_updates=segment_updates,
                delete_segment_ids=delete_segment_ids,
                new_segments=new_segments,
            )

    return admin_card_post_response(
        request,
        card_id,
        "timing_result",
        timing_result,
        anchor="timing",
    )


@app.post("/admin/cards/{card_id}/timing-segments/{segment_id}")
async def save_admin_timing_segment(
    request: Request,
    card_id: int,
    segment_id: int,
    loaded_version: str = Form(...),
    started_at: str = Form(""),
    ended_at: str = Form(""),
    end_reason: str = Form(""),
):
    parsed_version, timing_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        timing_result = update_timing_segment(
            card_id=card_id,
            segment_id=segment_id,
            loaded_version=parsed_version,
            started_at=started_at,
            ended_at=ended_at,
            end_reason=end_reason,
        )

    return admin_card_post_response(
        request,
        card_id,
        "timing_result",
        timing_result,
        anchor="timing",
    )


@app.post("/admin/cards/{card_id}/timing-segments/{segment_id}/delete")
async def delete_admin_timing_segment(
    request: Request,
    card_id: int,
    segment_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, timing_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        timing_result = delete_timing_segment(
            card_id=card_id,
            segment_id=segment_id,
            loaded_version=parsed_version,
        )

    return admin_card_post_response(
        request,
        card_id,
        "timing_result",
        timing_result,
        anchor="timing",
    )


def parse_planning_form(
    machine_id: str,
    machine_sequence: str,
) -> tuple[dict[str, int] | None, RuleResult]:
    messages: list[str] = []

    try:
        parsed_machine_id = int(machine_id)
    except ValueError:
        parsed_machine_id = 0
        messages.append("Машината трябва да е число от 1 до 4.")

    try:
        parsed_sequence = int(machine_sequence)
    except ValueError:
        parsed_sequence = 0
        messages.append("Редът трябва да е цяло число.")

    if parsed_machine_id not in (1, 2, 3, 4):
        messages.append("Машината трябва да е 1, 2, 3 или 4.")

    if parsed_sequence < 1:
        messages.append("Редът трябва да е 1 или по-голям.")

    result = RuleResult(not messages, tuple(messages))
    if not result.ok:
        return None, result

    return {
        "machine_id": parsed_machine_id,
        "machine_sequence": parsed_sequence,
    }, result


@app.get("/terminal")
async def terminal(
    request: Request,
    machine_id: int | None = None,
    notice: str | None = None,
    shift_view: str | None = None,
    shift_id: str | None = None,
    handoff: str | None = None,
    shift_page: str | None = None,
):
    return terminal_response(
        request,
        selected_machine_id=machine_id,
        terminal_notice=notice,
        shift_view=shift_view,
        shift_id=shift_id,
        handoff=handoff,
        shift_page=shift_page,
    )


@app.get("/terminal/snapshot")
async def terminal_snapshot_route(selected_card_id: int | None = None):
    return fetch_terminal_snapshot(selected_card_id)


@app.get("/terminal/cards/{card_id}")
async def terminal_card(
    request: Request,
    card_id: int,
    notice: str | None = None,
    shift_view: str | None = None,
    shift_id: str | None = None,
    handoff: str | None = None,
    shift_page: str | None = None,
):
    return terminal_response(
        request,
        selected_card_id=card_id,
        terminal_notice=notice,
        shift_view=shift_view,
        shift_id=shift_id,
        handoff=handoff,
        shift_page=shift_page,
    )


@app.post("/terminal/shifts/start")
async def start_terminal_shift(
    request: Request,
    shift_number: str = Form(...),
    configuration_version: str = Form(...),
    selected_card_id: str | None = Form(None),
):
    parsed_version, shift_result = parse_shift_form_integer(
        configuration_version,
        "Версията на настройките е невалидна. Презаредете терминала.",
    )
    if parsed_version is not None:
        shift_result = start_shift(shift_number, parsed_version)

    validated_card_id = validated_terminal_selected_card_id(selected_card_id)
    if shift_result.ok:
        return RedirectResponse(
            url=terminal_shift_redirect_url(validated_card_id),
            status_code=303,
        )
    return terminal_response(
        request,
        selected_card_id=validated_card_id,
        shift_result=shift_result,
        shift_view="overview" if fetch_active_shift() is not None else None,
        shift_reload_required=shift_lifecycle_reload_required(shift_result),
    )


@app.post("/terminal/shifts/current/number")
async def change_terminal_shift_number(
    request: Request,
    shift_occurrence_id: str = Form(...),
    loaded_version: str = Form(...),
    shift_number: str = Form(...),
    selected_card_id: str | None = Form(None),
):
    parsed_occurrence_id, shift_result = parse_shift_form_integer(
        shift_occurrence_id,
        "Активната смяна е невалидна. Презаредете терминала.",
    )
    parsed_version, version_result = parse_shift_form_integer(
        loaded_version,
        "Версията на смяната е невалидна. Презаредете терминала.",
    )
    if not version_result.ok:
        shift_result = version_result
    if parsed_occurrence_id is not None and parsed_version is not None:
        shift_result = update_active_shift_number(
            parsed_occurrence_id,
            parsed_version,
            shift_number,
        )

    validated_card_id = validated_terminal_selected_card_id(selected_card_id)
    if shift_result.ok:
        return RedirectResponse(
            url=terminal_shift_redirect_url(
                validated_card_id,
                shift_view="overview",
                notice="shift_changed",
            ),
            status_code=303,
        )
    return terminal_response(
        request,
        selected_card_id=validated_card_id,
        shift_result=shift_result,
        shift_view="overview",
        shift_reload_required=shift_lifecycle_reload_required(shift_result),
    )


@app.post("/terminal/shifts/current/end")
async def end_terminal_shift(
    request: Request,
    shift_occurrence_id: str = Form(...),
    loaded_version: str = Form(...),
    selected_card_id: str | None = Form(None),
):
    parsed_occurrence_id, shift_result = parse_shift_form_integer(
        shift_occurrence_id,
        "Активната смяна е невалидна. Презаредете терминала.",
    )
    parsed_version, version_result = parse_shift_form_integer(
        loaded_version,
        "Версията на смяната е невалидна. Презаредете терминала.",
    )
    if not version_result.ok:
        shift_result = version_result
    if parsed_occurrence_id is not None and parsed_version is not None:
        shift_result = end_shift(parsed_occurrence_id, parsed_version)

    validated_card_id = validated_terminal_selected_card_id(selected_card_id)
    if shift_result.ok:
        return RedirectResponse(
            url=terminal_shift_redirect_url(
                validated_card_id,
                shift_view="summary",
                shift_id=parsed_occurrence_id,
                handoff="1",
            ),
            status_code=303,
        )
    return terminal_response(
        request,
        selected_card_id=validated_card_id,
        shift_result=shift_result,
        shift_view="overview",
        shift_reload_required=shift_lifecycle_reload_required(shift_result),
    )


@app.post("/terminal/cards/{card_id}/materials")
async def save_terminal_materials(
    request: Request,
    card_id: int,
):
    form = await request.form()
    loaded_version = str(form.get("loaded_version") or "")
    try:
        parsed_version = int(loaded_version)
    except ValueError:
        material_result = RuleResult(False, (INVALID_LOADED_VERSION_MESSAGE,))
    else:
        material_result = validate_terminal_card_available_for_post(card_id)
        if material_result.ok:
            material_result = update_terminal_recipe_actual_entries(
                card_id=card_id,
                loaded_version=parsed_version,
                entries=recipe_actual_entries_from_form(form),
                require_active_shift=True,
            )

    return terminal_post_response(
        request,
        card_id,
        "material_result",
        material_result,
        notice_code="materials_saved",
    )


@app.post("/terminal/cards/{card_id}/tare")
async def save_tare_weight(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    tare_weight: str = Form(""),
):
    parsed_version, roll_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        roll_result = validate_terminal_card_available_for_post(card_id)
        if roll_result.ok:
            roll_result = update_tare_weight(
                card_id,
                parsed_version,
                tare_weight,
                require_active_shift=True,
            )

    return terminal_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        notice_code="tare_saved",
        roll_result_target="tare",
    )


@app.post("/terminal/cards/{card_id}/rolls")
async def add_roll_weight(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    gross_weight: str = Form(""),
    tare_weight: str | None = Form(None),
):
    parsed_version, roll_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        roll_result = validate_terminal_card_available_for_post(card_id)
        if roll_result.ok:
            roll_result = add_roll_gross_weight(
                card_id,
                parsed_version,
                gross_weight,
                tare_weight=tare_weight,
                require_active_shift=True,
            )

    return terminal_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        notice_code="roll_saved",
        roll_result_target="new_roll",
    )


@app.post("/terminal/cards/{card_id}/rolls/corrections")
async def save_terminal_roll_corrections(
    request: Request,
    card_id: int,
):
    form = await request.form()
    parsed_version, roll_result = parse_loaded_version(
        str(form.get("loaded_version") or "")
    )
    if parsed_version is not None:
        roll_result = validate_terminal_card_available_for_post(card_id)
        if roll_result.ok:
            try:
                roll_updates = terminal_roll_corrections_from_form(form)
            except ValueError:
                roll_result = RuleResult(False, ("Формата съдържа невалидна ролка.",))
            else:
                roll_result = update_terminal_roll_corrections(
                    card_id,
                    parsed_version,
                    roll_updates,
                    require_active_shift=True,
                )

    return terminal_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        notice_code="rolls_saved",
        roll_result_target="roll_corrections",
    )


@app.post("/terminal/cards/{card_id}/rolls/{roll_id}")
async def save_roll_weight(
    request: Request,
    card_id: int,
    roll_id: int,
    loaded_version: str = Form(...),
    gross_weight: str = Form(""),
    tare_weight: str | None = Form(None),
):
    parsed_version, roll_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        roll_result = validate_terminal_card_available_for_post(card_id)
        if roll_result.ok:
            if tare_weight is None or not isinstance(tare_weight, str):
                roll_result = update_roll_gross_weight(
                    card_id=card_id,
                    roll_id=roll_id,
                    loaded_version=parsed_version,
                    gross_weight=gross_weight,
                    require_active_shift=True,
                )
            else:
                roll_result = update_roll_weight(
                    card_id=card_id,
                    roll_id=roll_id,
                    loaded_version=parsed_version,
                    gross_weight=gross_weight,
                    tare_weight=tare_weight,
                    require_active_shift=True,
                )

    return terminal_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        notice_code="roll_updated",
        roll_result_target="roll_row",
        roll_result_roll_id=roll_id,
    )


@app.post("/terminal/cards/{card_id}/rolls/{roll_id}/delete")
async def delete_roll_weight(
    request: Request,
    card_id: int,
    roll_id: int,
    loaded_version: str = Form(...),
    confirm_roll_number: str = Form(""),
):
    parsed_version, roll_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        roll_result = validate_terminal_card_available_for_post(card_id)
        if roll_result.ok:
            roll_result = delete_terminal_roll_with_confirmation(
                card_id,
                roll_id,
                parsed_version,
                confirm_roll_number,
            )

    return terminal_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        notice_code="roll_deleted",
        roll_result_target="roll_delete",
        roll_delete_selected_roll_id=roll_id,
    )


@app.post("/terminal/cards/{card_id}/rolls/actions/delete-selected")
async def delete_selected_roll_weight(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    roll_id: str = Form(""),
    confirm_roll_number: str = Form(""),
):
    parsed_version, roll_result = parse_loaded_version(loaded_version)
    parsed_roll_id: int | None = None
    if parsed_version is not None:
        roll_result = validate_terminal_card_available_for_post(card_id)
        if roll_result.ok:
            try:
                parsed_roll_id = int(roll_id)
            except ValueError:
                roll_result = RuleResult(False, ("Изберете валидна ролка за изтриване.",))
            else:
                roll_result = delete_terminal_roll_with_confirmation(
                    card_id,
                    parsed_roll_id,
                    parsed_version,
                    confirm_roll_number,
                )

    return terminal_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        notice_code="roll_deleted",
        roll_result_target="roll_delete",
        roll_delete_selected_roll_id=parsed_roll_id,
    )


@app.post("/terminal/cards/{card_id}/timing/start")
async def start_timing(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, timing_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        timing_result = validate_terminal_card_available_for_post(card_id)
        if timing_result.ok:
            timing_result = start_production_timing(
                card_id,
                parsed_version,
                require_active_shift=True,
            )

    return terminal_post_response(
        request,
        card_id,
        "timing_result",
        timing_result,
        notice_code="timing_started",
    )


@app.post("/terminal/cards/{card_id}/timing/pause")
async def pause_timing(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, timing_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        timing_result = validate_terminal_card_available_for_post(card_id)
        if timing_result.ok:
            timing_result = pause_production_timing(
                card_id,
                parsed_version,
                require_active_shift=True,
            )

    return terminal_post_response(
        request,
        card_id,
        "timing_result",
        timing_result,
        notice_code="timing_paused",
    )


@app.post("/terminal/cards/{card_id}/timing/resume")
async def resume_timing(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, timing_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        timing_result = validate_terminal_card_available_for_post(card_id)
        if timing_result.ok:
            timing_result = resume_production_timing(
                card_id,
                parsed_version,
                require_active_shift=True,
            )

    return terminal_post_response(
        request,
        card_id,
        "timing_result",
        timing_result,
        notice_code="timing_resumed",
    )


@app.post("/terminal/cards/{card_id}/finish")
async def finish_terminal_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, workflow_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        workflow_result = validate_terminal_card_available_for_post(card_id)
        if workflow_result.ok:
            workflow_result = finish_card(
                card_id,
                parsed_version,
                require_active_shift=True,
            )

    return terminal_post_response(
        request,
        card_id,
        "workflow_result",
        workflow_result,
        notice_code="card_finished",
    )


def parse_loaded_version(loaded_version: str) -> tuple[int | None, RuleResult]:
    try:
        return int(loaded_version), RuleResult(True)
    except ValueError:
        return None, RuleResult(False, (INVALID_LOADED_VERSION_MESSAGE,))


def parse_shift_form_integer(
    value: str,
    invalid_message: str,
) -> tuple[int | None, RuleResult]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, RuleResult(False, (invalid_message,))
    if parsed < 1:
        return None, RuleResult(False, (invalid_message,))
    return parsed, RuleResult(True)


def shift_lifecycle_reload_required(result: RuleResult) -> bool:
    stale_messages = {STALE_CONFIGURATION_MESSAGE, STALE_SHIFT_MESSAGE}
    return not result.ok and any(
        message in stale_messages for message in result.messages
    )


def validate_terminal_card_available_for_post(card_id: int) -> RuleResult:
    if fetch_active_shift() is None:
        return RuleResult(False, (NO_ACTIVE_SHIFT_MESSAGE,))
    if fetch_terminal_card_detail(card_id) is None:
        return RuleResult(False, (TERMINAL_CARD_UNAVAILABLE_MESSAGE,))
    return RuleResult(True)


def delete_terminal_roll_with_confirmation(
    card_id: int,
    roll_id: int,
    loaded_version: int,
    confirm_roll_number: str,
) -> RuleResult:
    card = fetch_terminal_card_detail(card_id)
    if not card:
        return RuleResult(False, (CARD_NOT_FOUND_MESSAGE,))

    roll = next(
        (
            roll_entry
            for roll_entry in card["roll_entries"]
            if int(roll_entry["id"]) == roll_id
        ),
        None,
    )
    if not roll:
        return RuleResult(False, ("Ролката не е намерена.",))

    expected_roll_number = str(roll["roll_number"])
    if confirm_roll_number.strip() != expected_roll_number:
        return RuleResult(False, ("Потвърдете изтриването с номера на ролката.",))

    return delete_roll_entry(
        card_id,
        roll_id,
        loaded_version,
        require_active_shift=True,
    )


def terminal_response(
    request: Request,
    selected_card_id: int | None = None,
    selected_machine_id: int | None = None,
    **extra: Any,
):
    return templates.TemplateResponse(
        request,
        "terminal.html",
        terminal_context(selected_card_id, selected_machine_id, **extra),
    )


def terminal_post_response(
    request: Request,
    card_id: int,
    result_name: str,
    result: RuleResult,
    notice_code: str | None = None,
    **extra: Any,
):
    if result.ok:
        return RedirectResponse(
            url=terminal_redirect_url(card_id, notice_code),
            status_code=303,
        )
    return terminal_response(
        request,
        selected_card_id=card_id,
        **{result_name: result},
        **extra,
    )


def terminal_redirect_url(card_id: int, notice_code: str | None = None) -> str:
    base_url = f"/terminal/cards/{card_id}"
    if not notice_code:
        return base_url
    return f"{base_url}?{urlencode({'notice': notice_code})}"


def validated_terminal_selected_card_id(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        card_id = int(value)
    except (TypeError, ValueError):
        return None
    if card_id < 1 or fetch_terminal_card_detail(card_id) is None:
        return None
    return card_id


def terminal_shift_redirect_url(
    selected_card_id: int | None,
    **query: str | int | None,
) -> str:
    base_url = (
        f"/terminal/cards/{selected_card_id}"
        if selected_card_id is not None
        else "/terminal"
    )
    normalized_query = {
        key: value for key, value in query.items() if value is not None
    }
    if not normalized_query:
        return base_url
    return f"{base_url}?{urlencode(normalized_query)}"


def terminal_notice_result(notice_code: str | None) -> RuleResult | None:
    messages = TERMINAL_NOTICE_MESSAGES.get(str(notice_code or ""))
    if not messages:
        return None
    return RuleResult(True, messages)


def terminal_context(
    selected_card_id: int | None = None,
    selected_machine_id: int | None = None,
    shift_view: str | None = None,
    shift_id: str | int | None = None,
    handoff: str | None = None,
    shift_page: str | int | None = None,
    shift_reload_required: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    machine_queues = fetch_machine_queues()
    machines = fetch_machines()
    valid_machine_ids = {int(machine["id"]) for machine in machines}
    if selected_machine_id not in valid_machine_ids:
        selected_machine_id = None

    if selected_card_id is None:
        if selected_machine_id is not None:
            selected_card_id = next(
                (
                    int(queue["focus_card"]["id"])
                    for queue in machine_queues
                    if int(queue["machine"]["id"]) == selected_machine_id
                    and queue["focus_card"]
                ),
                None,
            )
        else:
            selected_card_id = next(
                (
                    int(queue["focus_card"]["id"])
                    for queue in machine_queues
                    if queue["focus_card"]
                ),
                None,
            )

    selected_card = fetch_terminal_card_detail(selected_card_id) if selected_card_id else None
    if selected_card:
        selected_card["total_production_duration"] = format_duration(
            selected_card["total_production_seconds"],
        )
        enrich_terminal_card_display(selected_card)
        selected_machine_id = selected_card["machine_id"]

    enriched_queues = enrich_machine_queues(machine_queues, selected_card, selected_machine_id)
    active_cards = [
        card
        for queue in enriched_queues
        for card in queue["cards"]
    ]
    archive_cards = [
        enrich_terminal_list_card(card, selected_card)
        for card in sorted_terminal_archive_cards(
            fetch_cards_by_status(TERMINAL_ARCHIVE_STATUSES),
        )
    ]
    try:
        requested_shift_page = int(shift_page or 1)
    except (TypeError, ValueError):
        requested_shift_page = 1
    shift_state = fetch_terminal_shift_page_state(
        requested_page=requested_shift_page,
        page_size=SHIFT_HISTORY_PAGE_SIZE,
        preview_size=SHIFT_HISTORY_PREVIEW_SIZE,
    )
    shift_context = build_terminal_shift_context(
        shift_view,
        shift_id,
        handoff,
        shift_page,
        state=shift_state,
        reload_required=shift_reload_required,
    )
    terminal_snapshot = fetch_terminal_snapshot(
        selected_card_id,
        known_shift_signature=str(shift_state["shift_signature"]),
    )

    context: dict[str, Any] = {
        "machines": fetch_machines(),
        "machine_queues": enriched_queues,
        "active_cards": active_cards,
        "archive_cards": archive_cards,
        "selected_card": selected_card,
        "selected_machine_id": selected_machine_id,
        "terminal_snapshot": terminal_snapshot,
        "status_labels": STATUS_LABELS,
        "recipe_rows": build_terminal_recipe_rows(selected_card) if selected_card else [],
        **shift_context,
        **extra,
        "terminal_feedback": build_terminal_feedback(extra),
    }
    return context


def build_terminal_shift_context(
    shift_view: str | None,
    shift_id: str | int | None,
    handoff: str | None,
    shift_page: str | int | None = None,
    *,
    state: dict[str, Any] | None = None,
    reload_required: bool = False,
) -> dict[str, Any]:
    if state is None:
        state = fetch_shift_window_state()
    configuration = state["configuration"]
    raw_active_shift = state["active_shift"]
    active_shift = (
        build_shift_display(raw_active_shift) if raw_active_shift is not None else None
    )
    if "completed_shifts" in state:
        completed_shifts = [
            build_shift_display(shift) for shift in state["completed_shifts"]
        ]
        try:
            requested_history_page = int(shift_page or 1)
        except (TypeError, ValueError):
            requested_history_page = 1
        completed_shift_count = len(completed_shifts)
        history_page_count = max(
            1,
            (completed_shift_count + SHIFT_HISTORY_PAGE_SIZE - 1)
            // SHIFT_HISTORY_PAGE_SIZE,
        )
        history_page = min(max(1, requested_history_page), history_page_count)
        history_page_start = (history_page - 1) * SHIFT_HISTORY_PAGE_SIZE
        history_shifts = completed_shifts[
            history_page_start : history_page_start + SHIFT_HISTORY_PAGE_SIZE
        ]
        recent_completed_shifts = completed_shifts[:SHIFT_HISTORY_PREVIEW_SIZE]
    else:
        completed_shift_count = int(state["completed_shift_count"])
        history_page_count = int(state["history_page_count"])
        history_page = int(state["history_page"])
        recent_completed_shifts = [
            build_shift_display(shift)
            for shift in state["recent_completed_shifts"]
        ]
        history_shifts = [
            build_shift_display(shift) for shift in state["history_shifts"]
        ]
        completed_shifts = recent_completed_shifts
    history_page_window_start = max(
        1,
        min(
            history_page - (SHIFT_HISTORY_PAGE_WINDOW // 2),
            history_page_count - SHIFT_HISTORY_PAGE_WINDOW + 1,
        ),
    )
    history_page_numbers = list(
        range(
            history_page_window_start,
            min(
                history_page_count,
                history_page_window_start + SHIFT_HISTORY_PAGE_WINDOW - 1,
            )
            + 1,
        )
    )
    normalized_view = (
        shift_view if shift_view in {"overview", "history", "summary"} else None
    )

    parsed_shift_id: int | None = None
    if shift_id is not None:
        try:
            candidate_shift_id = int(shift_id)
        except (TypeError, ValueError):
            candidate_shift_id = 0
        if candidate_shift_id > 0:
            parsed_shift_id = candidate_shift_id

    selected_shift_summary = None
    if normalized_view == "summary" and parsed_shift_id is not None:
        raw_selected_shift_summary = fetch_shift_summary(parsed_shift_id)
        if (
            raw_selected_shift_summary is not None
            and raw_selected_shift_summary["ended_at"] is not None
        ):
            selected_shift_summary = build_shift_display(raw_selected_shift_summary)

    just_ended_handoff = selected_shift_summary is not None and handoff == "1"
    if reload_required:
        shift_window_state = "reload"
        shift_blocking = True
    elif just_ended_handoff:
        shift_window_state = "summary"
        shift_blocking = True
    elif active_shift is None:
        shift_window_state = "gate"
        shift_blocking = True
    elif normalized_view == "summary" and selected_shift_summary is not None:
        shift_window_state = "summary"
        shift_blocking = False
    elif normalized_view == "history":
        shift_window_state = "history"
        shift_blocking = False
    elif normalized_view in {"overview", "summary"}:
        shift_window_state = "overview"
        shift_blocking = False
    else:
        shift_window_state = "closed"
        shift_blocking = False

    shift_count = int(configuration["shift_count"])
    shift_options = list(range(1, shift_count + 1))
    if active_shift is not None:
        active_shift_number = int(active_shift["shift_number"])
        if active_shift_number not in shift_options:
            shift_options.append(active_shift_number)

    return {
        "shift_configuration": {
            "shift_count": shift_count,
            "version": int(configuration["version"]),
        },
        "active_shift": active_shift,
        "shift_options": shift_options,
        "suggested_shift_number": int(state["suggested_shift_number"]),
        "completed_shifts": completed_shifts,
        "completed_shift_count": completed_shift_count,
        "recent_completed_shifts": recent_completed_shifts,
        "history_shifts": history_shifts,
        "shift_history_page": history_page,
        "shift_history_page_count": history_page_count,
        "shift_history_page_numbers": history_page_numbers,
        "shift_history_has_previous": history_page > 1,
        "shift_history_has_next": history_page < history_page_count,
        "selected_shift_summary": selected_shift_summary,
        "shift_window_state": shift_window_state,
        "shift_blocking": shift_blocking,
    }


def build_terminal_feedback(results: dict[str, Any]) -> dict[str, Any]:
    feedback: dict[str, Any] = {
        "toast": None,
        "scroll_rolls_to_bottom": False,
        "open_roll_corrections": False,
        "refresh_required": False,
        "roll_delete_selected_roll_id": results.get("roll_delete_selected_roll_id"),
        "errors": {
            "tare": (),
            "new_roll": (),
            "roll_corrections": (),
            "roll_delete": (),
            "roll_rows": {},
            "material": (),
            "topbar": (),
        },
    }

    notice_result = terminal_notice_result(results.get("terminal_notice"))
    if notice_result is not None:
        feedback["toast"] = {"messages": notice_result.messages}
        if results.get("terminal_notice") == "roll_saved":
            feedback["scroll_rolls_to_bottom"] = True

    for result_name, target in (
        ("workflow_result", "topbar"),
        ("timing_result", "topbar"),
        ("material_result", "material"),
        ("roll_result", terminal_roll_feedback_target(results)),
    ):
        result = results.get(result_name)
        if not isinstance(result, RuleResult):
            continue

        messages = tuple(message for message in result.messages if message)
        if not messages:
            continue

        if result.ok:
            feedback["toast"] = {"messages": messages}
            if result_name == "roll_result" and target == "new_roll":
                feedback["scroll_rolls_to_bottom"] = True
            continue

        if is_terminal_card_state_error(messages):
            feedback["refresh_required"] = True
            continue

        if NO_ACTIVE_SHIFT_MESSAGE in messages:
            feedback["errors"]["topbar"] = messages
            continue

        if target == "roll_corrections":
            feedback["open_roll_corrections"] = True

        if target == "roll_row":
            roll_id = results.get("roll_result_roll_id")
            if roll_id is not None:
                feedback["errors"]["roll_rows"][roll_id] = messages
            else:
                feedback["errors"]["new_roll"] = messages
        else:
            feedback["errors"][target] = messages

    return feedback


def is_terminal_card_state_error(messages: tuple[str, ...]) -> bool:
    state_messages = {
        STALE_CARD_MESSAGE,
        INVALID_LOADED_VERSION_MESSAGE,
        TERMINAL_CARD_UNAVAILABLE_MESSAGE,
    }
    return any(message in state_messages for message in messages)


def terminal_roll_feedback_target(results: dict[str, Any]) -> str:
    target = str(results.get("roll_result_target") or "new_roll")
    if target in {"tare", "new_roll", "roll_row", "roll_delete", "roll_corrections"}:
        return target
    return "new_roll"


def enrich_machine_queues(
    machine_queues: list[dict[str, Any]],
    selected_card: dict[str, Any] | None,
    selected_machine_id: int | None,
) -> list[dict[str, Any]]:
    enriched_queues: list[dict[str, Any]] = []
    for queue in machine_queues:
        machine_id = int(queue["machine"]["id"])
        enriched_cards = [
            enrich_terminal_list_card(card, selected_card)
            for card in queue["cards"]
        ]
        focus_card = queue["focus_card"]
        if focus_card:
            focus_card = next(
                (card for card in enriched_cards if card["id"] == focus_card["id"]),
                enrich_terminal_list_card(focus_card, selected_card),
            )
        enriched_queue = {
            **queue,
            "cards": enriched_cards,
            "focus_card": focus_card,
            "is_selected": selected_machine_id == machine_id,
        }
        enriched_queues.append(enriched_queue)
    return enriched_queues


def enrich_terminal_card_display(card: dict[str, Any]) -> dict[str, Any]:
    enrich_terminal_list_card(card, card)
    card["quantity_display"] = build_quantity_display(card)
    card["recipe_rows"] = build_terminal_recipe_rows(card)
    card["target_gross_weight"] = target_gross_display(card)
    card["remaining_gross_weight"] = remaining_gross_display(card)
    card["total_gross_weight_display"] = one_decimal_weight_display(
        card.get("total_gross_weight"),
        blank="0.0",
    )
    card["remaining_gross_weight_display"] = one_decimal_weight_display(
        card.get("remaining_gross_weight"),
    )
    card["total_net_weight_display"] = one_decimal_weight_display(
        card.get("total_net_weight"),
    )
    return card


def enrich_terminal_list_card(
    card: dict[str, Any],
    selected_card: dict[str, Any] | None,
) -> dict[str, Any]:
    card["status_label"] = STATUS_LABELS.get(card.get("status"), str(card.get("status") or ""))
    card["status_display_class"] = (
        "idle" if card.get("status") == STATUS_PENDING else str(card.get("status") or "")
    )
    card["quantity_display"] = build_quantity_display(card)
    card["target_gross_weight"] = target_gross_display(card)
    card["produced_gross_weight"] = rounded_weight_display(card.get("total_gross_weight"))
    card["remaining_gross_weight"] = remaining_gross_display(card)
    card["progress_percent"] = progress_percent(card)
    card["is_selected"] = bool(selected_card and selected_card["id"] == card["id"])
    return card


def build_quantity_display(card: dict[str, Any]) -> str:
    lines = [line["display"] for line in build_ordered_amount_lines(card)]
    return " / ".join(lines) if lines else "-"


def target_gross_decimal(card: dict[str, Any]) -> Decimal | None:
    return target_gross_weight_from_card(card)


def target_gross_display(card: dict[str, Any]) -> str | None:
    target = target_gross_decimal(card)
    return decimal_weight_display(target) if target is not None else None


def remaining_gross_display(card: dict[str, Any]) -> str | None:
    target = target_gross_decimal(card)
    produced = decimal_from_display(card.get("total_gross_weight")) or Decimal("0")
    if target is None:
        return None
    return decimal_weight_display(max(target - produced, Decimal("0")))


def sorted_terminal_archive_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dated_cards = []
    missing_finished_cards = []
    for card in cards:
        if str(card.get("finished_at") or "").strip():
            dated_cards.append(card)
        else:
            missing_finished_cards.append(card)

    return sorted(
        dated_cards,
        key=lambda card: (
            str(card.get("finished_at") or ""),
            str(card.get("order_number") or "").casefold(),
            int(card.get("id") or 0),
        ),
        reverse=True,
    ) + sorted(
        missing_finished_cards,
        key=lambda card: (
            str(card.get("order_number") or "").casefold(),
            int(card.get("id") or 0),
        ),
    )


def progress_percent(card: dict[str, Any]) -> int:
    target = target_gross_decimal(card)
    produced = decimal_from_display(card.get("total_gross_weight")) or Decimal("0")
    if target is None or target <= 0:
        return 0
    percentage = int((produced / target) * Decimal("100"))
    return max(0, min(100, percentage))


def decimal_from_display(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def decimal_weight_display(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value.quantize(Decimal('0.01'))}"


def one_decimal_weight_display(value: Any, blank: str = "-") -> str:
    decimal_value = decimal_from_display(value)
    if decimal_value is None:
        return blank
    return format(decimal_value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f")


BULGARIAN_MONTH_NAMES = (
    "",
    "януари",
    "февруари",
    "март",
    "април",
    "май",
    "юни",
    "юли",
    "август",
    "септември",
    "октомври",
    "ноември",
    "декември",
)
SHIFT_DISPLAY_TIME_ZONE = ZoneInfo("Europe/Sofia")


def format_shift_datetime(value: Any) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return "-"
    try:
        parsed_utc = datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return "-"
    parsed = parsed_utc.astimezone(SHIFT_DISPLAY_TIME_ZONE)
    return (
        f"{parsed.day} {BULGARIAN_MONTH_NAMES[parsed.month]} "
        f"{parsed.year}, {parsed:%H:%M}"
    )


def build_shift_display(shift: dict[str, Any]) -> dict[str, Any]:
    display = dict(shift)
    display["started_at_display"] = format_shift_datetime(shift.get("started_at"))
    display["ended_at_display"] = format_shift_datetime(shift.get("ended_at"))
    if "total_gross_weight" in shift:
        display["total_gross_weight_display"] = one_decimal_weight_display(
            shift.get("total_gross_weight"),
            "0.0",
        )
    if "orders" in shift:
        display["orders"] = [
            {
                **order,
                "gross_weight_display": one_decimal_weight_display(
                    order.get("gross_weight"),
                    "0.0",
                ),
            }
            for order in shift["orders"]
        ]
    return display


def rounded_weight_display(value: Any) -> str:
    decimal_value = decimal_from_display(value)
    if decimal_value is None:
        return "0"
    return whole_decimal_text(decimal_value)


def format_duration(total_seconds: int) -> str:
    hours, remainder = divmod(max(total_seconds, 0), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
