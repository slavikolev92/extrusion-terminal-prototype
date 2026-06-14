from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .constants import ACTIVE_TERMINAL_STATUSES, ARCHIVE_STATUSES, STATUS_DRAFT, STATUS_IMPORTED
from .db import (
    add_roll_gross_weight,
    cancel_card,
    database_summary,
    delete_roll_entry,
    fetch_cards_by_status,
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
    update_roll_gross_weight,
    update_tare_weight,
    update_terminal_material_fields,
)
from .importer import csv_template, import_cards_from_csv
from .rules import RuleResult

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


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
        "draft_cards": fetch_cards_by_status((STATUS_DRAFT, STATUS_IMPORTED)),
        "machine_queues": fetch_machine_queues(),
        "machines": fetch_machines(),
        "summary": database_summary(),
    }
    context.update(extra)
    return context


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


@app.post("/admin/cards/{card_id}/release")
async def release_card_to_terminal(
    request: Request,
    card_id: int,
    machine_id: str = Form(...),
    machine_sequence: str = Form(...),
):
    release_result = parse_release_form(machine_id, machine_sequence)
    if release_result.ok:
        release_result = release_card(card_id, int(machine_id), int(machine_sequence))

    return templates.TemplateResponse(
        request,
        "admin_planning.html",
        admin_planning_context(release_result=release_result),
    )


def parse_release_form(machine_id: str, machine_sequence: str) -> RuleResult:
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

    return RuleResult(not messages, tuple(messages))


@app.get("/terminal")
async def terminal(request: Request):
    return terminal_response(request)


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
    return templates.TemplateResponse(
        request,
        "terminal.html",
        {
            "machines": fetch_machines(),
            "machine_queues": fetch_machine_queues(),
            "active_cards": fetch_cards_by_status(ACTIVE_TERMINAL_STATUSES),
            "archive_cards": fetch_cards_by_status(ARCHIVE_STATUSES),
            "selected_card": selected_card,
            **extra,
        },
    )


def format_duration(total_seconds: int) -> str:
    hours, remainder = divmod(max(total_seconds, 0), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
