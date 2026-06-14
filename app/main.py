from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .constants import (
    ACTIVE_TERMINAL_STATUSES,
    ARCHIVE_STATUSES,
    CARD_STATUSES,
    STATUS_IMPORTED,
)
from .db import (
    add_timing_segment,
    add_roll_gross_weight,
    cancel_card,
    database_summary,
    delete_timing_segment,
    delete_roll_entry,
    delete_admin_imported_card,
    fetch_cards_by_status,
    fetch_admin_card_detail,
    fetch_admin_cards,
    fetch_terminal_card_detail,
    fetch_machine_queues,
    fetch_machines,
    fetch_recent_import_batches,
    finish_card,
    init_db,
    pause_production_timing,
    release_card,
    resume_production_timing,
    restore_cancelled_card,
    start_production_timing,
    terminal_snapshot as fetch_terminal_snapshot,
    update_timing_segment,
    update_admin_imported_fields,
    update_card_planning,
    update_roll_gross_weight,
    update_tare_weight,
    update_terminal_material_fields,
    update_terminal_recipe_material,
)
from .importer import IMPORT_FIELDS, csv_template, import_cards_from_csv
from .rules import RuleResult

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

STATUS_LABELS = {
    "imported": "Импортирана",
    "pending": "Чакаща",
    "running": "В производство",
    "paused": "Пауза",
    "completed": "Приключена",
    "cancelled": "Анулирана",
}

IMPORT_FIELD_LABELS = {
    "order_number": "№ поръчка",
    "order_date": "Дата",
    "delivery_date": "Дата доставка",
    "customer": "Фирма",
    "city": "Град",
    "product_type": "Вид изделие",
    "quantity_1": "Количество",
    "unit_1": "Мярка",
    "quantity_2": "Допълнително количество",
    "unit_2": "Мярка",
    "product_form": "Вид заготовка",
    "material": "Материал",
    "size_thickness": "Размер/дебелина",
    "notes": "Забележки",
    "extrusion_flag": "Екструзия",
    "extrusion_folding": "Фалцоване",
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Extrusion Terminal Prototype", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


def admin_import_context(**extra: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "recent_imports": fetch_recent_import_batches(),
        "summary": database_summary(),
    }
    context.update(extra)
    return context


def admin_planning_context(**extra: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "draft_cards": fetch_cards_by_status((STATUS_IMPORTED,)),
        "machine_queues": fetch_machine_queues(),
        "machines": fetch_machines(),
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
    context: dict[str, Any] = {
        "card": card,
        "import_fields": IMPORT_FIELDS,
        "import_field_labels": IMPORT_FIELD_LABELS,
        "status_labels": STATUS_LABELS,
        "quantity_lines": build_quantity_lines(card),
        "recipe_rows": build_recipe_rows(card),
    }
    context.update(extra)
    return context


def build_quantity_lines(card: dict[str, Any]) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for index in (1, 2):
        quantity = str(card.get(f"quantity_{index}") or "").strip()
        unit = str(card.get(f"unit_{index}") or "").strip()
        if quantity or unit:
            lines.append(
                {
                    "quantity_field": f"quantity_{index}",
                    "unit_field": f"unit_{index}",
                    "quantity": quantity,
                    "unit": unit,
                    "display": " ".join(part for part in (quantity, unit) if part),
                }
            )
    return lines


def build_recipe_rows(card: dict[str, Any]) -> list[dict[str, str | bool]]:
    rows: list[dict[str, str | bool]] = []
    key_by_field = {
        "raw_material_a": "a",
        "raw_material_b": "b",
        "raw_material_c": "c",
        "linear_pe": "linear_pe",
        "antistatic": "antistatic",
        "masterbatch": "masterbatch",
        "chalk": "chalk",
    }
    recipe_entries = card.get("recipe_entries") or {}
    for label, field in RECIPE_FIELD_ROWS:
        key = key_by_field[field]
        entry = recipe_entries.get(key) or {}
        has_entry = key in recipe_entries
        imported_material = str(card.get(field) or "")
        old_single_material = key == "a" and (
            card.get("actual_raw_material_used")
            or card.get("raw_material_brand_grade")
            or card.get("raw_material_batch_lot")
        )
        material = str(entry.get("material") or "") if has_entry else imported_material
        brand = str(entry.get("brand") or "") if has_entry else ""
        batch = str(entry.get("batch") or "") if has_entry else ""
        if old_single_material and not has_entry:
            material = str(card.get("actual_raw_material_used") or imported_material)
            brand = str(card.get("raw_material_brand_grade") or "")
            batch = str(card.get("raw_material_batch_lot") or "")
        rows.append(
            {
                "label": label,
                "key": key,
                "field": field,
                "planned": imported_material,
                "material": material,
                "actual_material": material if has_entry or old_single_material else "",
                "brand": brand,
                "batch": batch,
                "has_actual": has_entry or bool(old_single_material),
            }
        )
    return rows


def parse_quantity_for_progress(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", ".")
    number_chars: list[str] = []
    decimal_seen = False
    for char in text:
        if char.isdigit():
            number_chars.append(char)
        elif char == "." and number_chars and not decimal_seen:
            number_chars.append(char)
            decimal_seen = True
        elif number_chars:
            break
    if not number_chars:
        return None
    try:
        return float("".join(number_chars))
    except ValueError:
        return None


def decorate_terminal_card_summary(card: dict[str, Any]) -> dict[str, Any]:
    detail = fetch_terminal_card_detail(int(card["id"]))
    gross = 0.0
    if detail:
        try:
            gross = float(str(detail["total_gross_weight"]).replace(",", "."))
        except ValueError:
            gross = 0.0
    target = parse_quantity_for_progress(card.get("quantity_1"))
    progress = 0
    if target and target > 0:
        progress = max(0, min(100, round((gross / target) * 100)))
    decorated = dict(card)
    decorated["total_gross_display"] = f"{gross:g}"
    decorated["target_quantity"] = target
    decorated["progress_percent"] = progress
    return decorated


def decorate_terminal_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [decorate_terminal_card_summary(card) for card in cards]


@app.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse(url="/terminal", status_code=303)


@app.get("/health")
async def health() -> dict:
    summary = database_summary()
    return {
        "status": "ok",
        **summary,
    }


@app.get("/admin")
async def admin() -> RedirectResponse:
    return RedirectResponse(url="/admin/import", status_code=303)


@app.get("/admin/import")
async def admin_import(request: Request):
    return templates.TemplateResponse(
        request,
        "admin_import.html",
        admin_import_context(),
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

    return templates.TemplateResponse(
        request,
        "admin_import.html",
        admin_import_context(import_result=result),
    )


@app.get("/admin/planning")
async def admin_planning(request: Request):
    return templates.TemplateResponse(
        request,
        "admin_planning.html",
        admin_planning_context(),
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
            "cards": fetch_admin_cards(filters),
            "filters": filters,
            "card_statuses": CARD_STATUSES,
            "summary": database_summary(),
        },
    )


@app.get("/admin/cards/{card_id}")
async def admin_card_detail(request: Request, card_id: int):
    context = admin_card_detail_context(card_id)
    if context is None:
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


@app.post("/admin/cards/{card_id}/imported-fields")
async def save_admin_imported_fields(request: Request, card_id: int):
    form = await request.form()
    parsed_version, imported_field_result = parse_loaded_version(
        str(form.get("loaded_version", ""))
    )
    if parsed_version is not None:
        imported_field_result = update_admin_imported_fields(
            card_id=card_id,
            loaded_version=parsed_version,
            fields={field: str(form.get(field, "")) for field in IMPORT_FIELDS},
        )

    context = admin_card_detail_context(card_id, imported_field_result=imported_field_result)
    if context is None:
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


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
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


@app.post("/admin/cards/{card_id}/release")
async def release_card_to_terminal(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    machine_id: str = Form(...),
    machine_sequence: str = Form(...),
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

    return templates.TemplateResponse(
        request,
        "admin_planning.html",
        admin_planning_context(planning_result=planning_result),
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

    context = admin_card_detail_context(card_id, workflow_result=workflow_result)
    if context is None:
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


@app.post("/admin/cards/{card_id}/restore")
async def restore_admin_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, workflow_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        workflow_result = restore_cancelled_card(card_id, parsed_version)

    context = admin_card_detail_context(card_id, workflow_result=workflow_result)
    if context is None:
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


@app.post("/admin/cards/{card_id}/production-materials")
async def save_admin_production_materials(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    actual_raw_material_used: str = Form(""),
    raw_material_brand_grade: str = Form(""),
    raw_material_batch_lot: str = Form(""),
):
    parsed_version, material_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        material_result = update_terminal_material_fields(
            card_id=card_id,
            loaded_version=parsed_version,
            actual_raw_material_used=actual_raw_material_used,
            raw_material_brand_grade=raw_material_brand_grade,
            raw_material_batch_lot=raw_material_batch_lot,
        )

    context = admin_card_detail_context(card_id, material_result=material_result)
    if context is None:
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


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

    context = admin_card_detail_context(card_id, roll_result=roll_result)
    if context is None:
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


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

    context = admin_card_detail_context(card_id, roll_result=roll_result)
    if context is None:
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


@app.post("/admin/cards/{card_id}/rolls/{roll_id}")
async def save_admin_roll_weight(
    request: Request,
    card_id: int,
    roll_id: int,
    loaded_version: str = Form(...),
    gross_weight: str = Form(""),
):
    parsed_version, roll_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        roll_result = update_roll_gross_weight(
            card_id=card_id,
            roll_id=roll_id,
            loaded_version=parsed_version,
            gross_weight=gross_weight,
        )

    context = admin_card_detail_context(card_id, roll_result=roll_result)
    if context is None:
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


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

    context = admin_card_detail_context(card_id, roll_result=roll_result)
    if context is None:
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


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

    context = admin_card_detail_context(card_id, timing_result=timing_result)
    if context is None:
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


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

    context = admin_card_detail_context(card_id, timing_result=timing_result)
    if context is None:
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


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

    context = admin_card_detail_context(card_id, timing_result=timing_result)
    if context is None:
        return PlainTextResponse("Card was not found.", status_code=404)
    return templates.TemplateResponse(request, "admin_card_detail.html", context)


def parse_planning_form(
    machine_id: str,
    machine_sequence: str,
) -> tuple[dict[str, int] | None, RuleResult]:
    messages: list[str] = []

    try:
        parsed_machine_id = int(machine_id)
    except ValueError:
        parsed_machine_id = 0
        messages.append("Machine must be a number from 1 to 4.")

    try:
        parsed_sequence = int(machine_sequence)
    except ValueError:
        parsed_sequence = 0
        messages.append("Sequence must be a whole number.")

    if parsed_machine_id not in (1, 2, 3, 4):
        messages.append("Machine must be 1, 2, 3, or 4.")

    if parsed_sequence < 1:
        messages.append("Sequence must be 1 or higher.")

    result = RuleResult(not messages, tuple(messages))
    if not result.ok:
        return None, result

    return {
        "machine_id": parsed_machine_id,
        "machine_sequence": parsed_sequence,
    }, result


@app.get("/terminal")
async def terminal(request: Request):
    return terminal_response(request)


@app.get("/terminal/snapshot")
async def terminal_snapshot_route(selected_card_id: int | None = None):
    return fetch_terminal_snapshot(selected_card_id)


@app.get("/terminal/cards/{card_id}")
async def terminal_card(request: Request, card_id: int):
    return terminal_response(request, selected_card_id=card_id)


@app.post("/terminal/cards/{card_id}/materials")
async def save_terminal_materials(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    actual_raw_material_used: str = Form(""),
    raw_material_brand_grade: str = Form(""),
    raw_material_batch_lot: str = Form(""),
):
    try:
        parsed_version = int(loaded_version)
    except ValueError:
        material_result = RuleResult(False, ("Loaded card version is invalid. Reload the card.",))
    else:
        material_result = update_terminal_material_fields(
            card_id=card_id,
            loaded_version=parsed_version,
            actual_raw_material_used=actual_raw_material_used,
            raw_material_brand_grade=raw_material_brand_grade,
            raw_material_batch_lot=raw_material_batch_lot,
        )

    return terminal_response(
        request,
        selected_card_id=card_id,
        material_result=material_result,
    )


@app.post("/terminal/cards/{card_id}/recipe/{component_key}")
async def save_terminal_recipe_material(
    request: Request,
    card_id: int,
    component_key: str,
    loaded_version: str = Form(...),
    material: str = Form(""),
    brand: str = Form(""),
    batch: str = Form(""),
):
    parsed_version, material_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        material_result = update_terminal_recipe_material(
            card_id=card_id,
            loaded_version=parsed_version,
            component_key=component_key,
            material=material,
            brand=brand,
            batch=batch,
        )

    return terminal_response(
        request,
        selected_card_id=card_id,
        material_result=material_result,
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
        roll_result = update_tare_weight(card_id, parsed_version, tare_weight)

    return terminal_response(
        request,
        selected_card_id=card_id,
        roll_result=roll_result,
    )


@app.post("/terminal/cards/{card_id}/rolls")
async def add_roll_weight(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    gross_weight: str = Form(""),
):
    parsed_version, roll_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        roll_result = add_roll_gross_weight(card_id, parsed_version, gross_weight)

    return terminal_response(
        request,
        selected_card_id=card_id,
        roll_result=roll_result,
    )


@app.post("/terminal/cards/{card_id}/rolls/{roll_id}")
async def save_roll_weight(
    request: Request,
    card_id: int,
    roll_id: int,
    loaded_version: str = Form(...),
    gross_weight: str = Form(""),
):
    parsed_version, roll_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        roll_result = update_roll_gross_weight(
            card_id=card_id,
            roll_id=roll_id,
            loaded_version=parsed_version,
            gross_weight=gross_weight,
        )

    return terminal_response(
        request,
        selected_card_id=card_id,
        roll_result=roll_result,
    )


@app.post("/terminal/cards/{card_id}/rolls/{roll_id}/delete")
async def delete_roll_weight(
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

    return terminal_response(
        request,
        selected_card_id=card_id,
        roll_result=roll_result,
    )


@app.post("/terminal/cards/{card_id}/timing/start")
async def start_timing(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, timing_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        timing_result = start_production_timing(card_id, parsed_version)

    return terminal_response(
        request,
        selected_card_id=card_id,
        timing_result=timing_result,
    )


@app.post("/terminal/cards/{card_id}/timing/pause")
async def pause_timing(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, timing_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        timing_result = pause_production_timing(card_id, parsed_version)

    return terminal_response(
        request,
        selected_card_id=card_id,
        timing_result=timing_result,
    )


@app.post("/terminal/cards/{card_id}/timing/resume")
async def resume_timing(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, timing_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        timing_result = resume_production_timing(card_id, parsed_version)

    return terminal_response(
        request,
        selected_card_id=card_id,
        timing_result=timing_result,
    )


@app.post("/terminal/cards/{card_id}/finish")
async def finish_terminal_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, workflow_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        workflow_result = finish_card(card_id, parsed_version)

    return terminal_response(
        request,
        selected_card_id=card_id,
        workflow_result=workflow_result,
    )


@app.post("/terminal/cards/{card_id}/cancel")
async def cancel_terminal_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, workflow_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        workflow_result = cancel_card(card_id, parsed_version)

    return terminal_response(
        request,
        selected_card_id=card_id,
        workflow_result=workflow_result,
    )


@app.post("/terminal/cards/{card_id}/restore")
async def restore_terminal_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, workflow_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        workflow_result = restore_cancelled_card(card_id, parsed_version)

    return terminal_response(
        request,
        selected_card_id=card_id,
        workflow_result=workflow_result,
    )


def parse_loaded_version(loaded_version: str) -> tuple[int | None, RuleResult]:
    try:
        return int(loaded_version), RuleResult(True)
    except ValueError:
        return None, RuleResult(False, ("Loaded card version is invalid. Reload the card.",))


def terminal_response(
    request: Request,
    selected_card_id: int | None = None,
    **extra: Any,
):
    selected_card = fetch_terminal_card_detail(selected_card_id) if selected_card_id else None
    if selected_card:
        selected_card["total_production_duration"] = format_duration(
            selected_card["total_production_seconds"],
        )
        selected_target = parse_quantity_for_progress(selected_card.get("quantity_1"))
        selected_gross = float(str(selected_card["total_gross_weight"]).replace(",", "."))
        selected_card["progress_percent"] = (
            max(0, min(100, round((selected_gross / selected_target) * 100)))
            if selected_target
            else 0
        )
    return templates.TemplateResponse(
        request,
        "terminal.html",
        {
            "active_cards": decorate_terminal_cards(fetch_cards_by_status(ACTIVE_TERMINAL_STATUSES)),
            "archive_cards": decorate_terminal_cards(fetch_cards_by_status(ARCHIVE_STATUSES)),
            "selected_card": selected_card,
            "recipe_rows": build_recipe_rows(selected_card) if selected_card else [],
            "status_labels": STATUS_LABELS,
            "terminal_snapshot": fetch_terminal_snapshot(selected_card_id),
            **extra,
        },
    )


def format_duration(total_seconds: int) -> str:
    hours, remainder = divmod(max(total_seconds, 0), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
