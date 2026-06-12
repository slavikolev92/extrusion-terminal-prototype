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
    database_summary,
    fetch_cards_by_status,
    fetch_machine_queues,
    fetch_machines,
    fetch_recent_import_batches,
    init_db,
    release_card,
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


def admin_context(**extra: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "draft_cards": fetch_cards_by_status((STATUS_DRAFT, STATUS_IMPORTED)),
        "machine_queues": fetch_machine_queues(),
        "machines": fetch_machines(),
        "recent_imports": fetch_recent_import_batches(),
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
async def admin(request: Request):
    return templates.TemplateResponse(
        request,
        "admin.html",
        admin_context(),
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
        "admin.html",
        admin_context(import_result=result),
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
        "admin.html",
        admin_context(release_result=release_result),
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
    return templates.TemplateResponse(
        request,
        "terminal.html",
        {
            "machines": fetch_machines(),
            "machine_queues": fetch_machine_queues(),
            "active_cards": fetch_cards_by_status(ACTIVE_TERMINAL_STATUSES),
            "archive_cards": fetch_cards_by_status(ARCHIVE_STATUSES),
        },
    )
