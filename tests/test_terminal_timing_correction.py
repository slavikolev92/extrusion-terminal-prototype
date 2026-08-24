from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import hmac
import io
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from itertools import permutations
from threading import Event, local
from typing import Callable

import pytest
from starlette.requests import Request

from app import db
from app import main
from app.constants import (
    STATUS_ARCHIVED,
    STATUS_AWAITING_REWINDING,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_IMPORTED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_RUNNING,
)
from app.importer import IMPORT_FIELDS, import_cards_from_csv


pytestmark = pytest.mark.usefixtures("active_test_shift")


def csv_bytes(*rows: dict[str, str]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")


def extrusion_row(order_number: str) -> dict[str, str]:
    return {
        "order_number": order_number,
        "customer": "Terminal Timing Customer",
        "product_type": "PE film",
        "ordered_gross_kg": "500",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_sequence": "1",
        "raw_material_a": "LDPE; A | 100%",
        "packaging_method": "rolls",
    }


def release_ready_card(order_number: str, machine_id: int) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number)),
        overwrite_existing=False,
    )
    assert result.rows_imported == 1
    with db.connect() as connection:
        card_id = int(
            connection.execute(
                "SELECT id FROM cards WHERE order_number = ?",
                (order_number,),
            ).fetchone()["id"]
        )
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    assert db.release_card(card_id, machine_id, 1, int(card["version"])).ok
    return card_id


def card_version(card_id: int) -> int:
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    return int(card["version"])


def start_card(card_id: int) -> None:
    assert db.start_production_timing(card_id, card_version(card_id)).ok


def end_active_test_shift() -> None:
    active_shift = db.fetch_active_shift()
    assert active_shift is not None
    assert db.end_shift(int(active_shift["id"]), int(active_shift["version"])).ok


def set_single_segment(
    card_id: int,
    *,
    started_at: str,
    ended_at: str | None,
    end_reason: str | None,
    status: str,
) -> int:
    with db.connect() as connection:
        segment_id = int(
            connection.execute(
                "SELECT id FROM production_time_segments WHERE card_id = ?",
                (card_id,),
            ).fetchone()["id"]
        )
        connection.execute(
            """
            UPDATE production_time_segments
            SET started_at = ?, ended_at = ?, end_reason = ?
            WHERE id = ?
            """,
            (started_at, ended_at, end_reason, segment_id),
        )
        connection.execute(
            "UPDATE cards SET status = ?, first_started_at = ? WHERE id = ?",
            (status, started_at, card_id),
        )
    return segment_id


def insert_segment(
    card_id: int,
    *,
    started_at: str,
    ended_at: str | None,
    end_reason: str | None,
) -> int:
    with db.connect() as connection:
        return int(
            connection.execute(
                """
                INSERT INTO production_time_segments (
                    card_id, started_at, ended_at, end_reason
                )
                VALUES (?, ?, ?, ?)
                RETURNING id
                """,
                (card_id, started_at, ended_at, end_reason),
            ).fetchone()["id"]
        )


def timing_snapshot(card_id: int) -> tuple[int, list[dict[str, object]]]:
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    return int(card["version"]), card["timing_segments"]


def unrelated_production_snapshot(card_id: int) -> dict[str, object]:
    with db.connect() as connection:
        card = dict(
            connection.execute(
                """
                SELECT status, machine_id, machine_sequence, tare_weight,
                       current_pallet_number, rewinding_roll_count,
                       final_extrusion_shift_occurrence_id,
                       actual_raw_material_used, raw_material_brand_grade,
                       raw_material_batch_lot
                FROM cards
                WHERE id = ?
                """,
                (card_id,),
            ).fetchone()
        )
        rolls = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM roll_entries WHERE card_id = ? ORDER BY id",
                (card_id,),
            ).fetchall()
        ]
        recipe_entries = [
            dict(row)
            for row in connection.execute(
                """
                SELECT *
                FROM recipe_actual_entries
                WHERE card_id = ?
                ORDER BY component_key
                """,
                (card_id,),
            ).fetchall()
        ]
    return {"card": card, "rolls": rolls, "recipe_entries": recipe_entries}


def make_test_request(path: str, method: str = "POST") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "root_path": "",
            "app": main.app,
        }
    )


def finish_review_endpoint():
    route = next(
        (
            route
            for route in main.app.routes
            if getattr(route, "path", None)
            == "/terminal/cards/{card_id}/finish-review"
        ),
        None,
    )
    assert route is not None, "finish-review route must be registered"
    return route.endpoint


def finish_review_preview_endpoint():
    route = next(
        (
            route
            for route in main.app.routes
            if getattr(route, "path", None)
            == "/terminal/cards/{card_id}/finish-review/preview"
        ),
        None,
    )
    assert route is not None, "finish-review preview route must be registered"
    return route.endpoint


def terminal_timing_model_from_response(response) -> dict[str, object]:
    match = re.search(
        rb'<script type="application/json" data-terminal-timing-model>\s*'
        rb'(?P<payload>.*?)\s*</script>',
        response.body,
        flags=re.S,
    )
    assert match is not None
    return json.loads(match.group("payload"))


def stored_finish_snapshot(card_id: int) -> dict[str, object]:
    with db.connect() as connection:
        card = dict(
            connection.execute(
                "SELECT * FROM cards WHERE id = ?",
                (card_id,),
            ).fetchone()
        )
        timing_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT *
                FROM production_time_segments
                WHERE card_id = ?
                ORDER BY started_at, id
                """,
                (card_id,),
            ).fetchall()
        ]
        roll_rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM roll_entries WHERE card_id = ? ORDER BY id",
                (card_id,),
            ).fetchall()
        ]
        recipe_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT *
                FROM recipe_actual_entries
                WHERE card_id = ?
                ORDER BY component_key
                """,
                (card_id,),
            ).fetchall()
        ]
    return {
        "card": card,
        "timing_rows": timing_rows,
        "roll_rows": roll_rows,
        "recipe_rows": recipe_rows,
    }


def preserved_snapshot(
    snapshot: dict[str, object],
    *,
    allowed_card_changes: set[str],
) -> dict[str, object]:
    card = snapshot["card"]
    assert isinstance(card, dict)
    return {
        "card": {
            key: value
            for key, value in card.items()
            if key not in allowed_card_changes
        },
        "roll_rows": snapshot["roll_rows"],
        "recipe_rows": snapshot["recipe_rows"],
    }


def seed_timing_audit_unrelated_data(card_id: int) -> None:
    assert db.update_tare_weight(card_id, card_version(card_id), "1.25").ok
    assert db.update_current_pallet_number(card_id, card_version(card_id), "7").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "25.50").ok
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        card_version(card_id),
        {
            "raw_material_a": {
                "actual_material_used": "Audit material",
                "batch_lot": "AUDIT-LOT",
            }
        },
    ).ok
    with db.connect() as setup_connection:
        setup_connection.execute(
            """
            UPDATE cards
            SET actual_raw_material_used = 'Retain card material',
                raw_material_brand_grade = 'Retain audit grade',
                raw_material_batch_lot = 'Retain audit batch'
            WHERE id = ?
            """,
            (card_id,),
        )


def run_serialized_timing_writers(
    monkeypatch: pytest.MonkeyPatch,
    winner_action: Callable[[], db.TimingLedgerOutcome],
    stale_action: Callable[[], db.TimingLedgerOutcome],
) -> tuple[db.TimingLedgerOutcome, db.TimingLedgerOutcome, bool]:
    """Prove writer two hits SQLite's lock before writer one commits."""

    real_connect = db.connect
    real_current_database_timestamp = db.current_database_timestamp
    writer_role = local()
    winner_has_lock = Event()
    release_winner = Event()
    retry_stale_writer = Event()
    contention_proved = Event()

    class LockProvingConnection:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return self.connection.__exit__(exc_type, exc_value, traceback)

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def execute(self, statement, parameters=()):
            if statement.strip().upper() != "BEGIN IMMEDIATE":
                return self.connection.execute(statement, parameters)
            try:
                return self.connection.execute(statement, parameters)
            except sqlite3.OperationalError as error:
                assert str(error) in {
                    "database is locked",
                    "database table is locked",
                }
                contention_proved.set()
                assert retry_stale_writer.wait(timeout=3)
                return self.connection.execute(statement, parameters)

    def synchronized_connect():
        connection = real_connect()
        if getattr(writer_role, "name", None) == "stale":
            connection.execute("PRAGMA busy_timeout = 0")
            return LockProvingConnection(connection)
        return connection

    def synchronized_transaction_time(connection):
        if getattr(writer_role, "name", None) == "winner":
            winner_has_lock.set()
            assert release_winner.wait(timeout=3)
        return real_current_database_timestamp(connection)

    def invoke(role: str, action: Callable[[], db.TimingLedgerOutcome]):
        writer_role.name = role
        try:
            return action()
        finally:
            del writer_role.name

    monkeypatch.setattr(db, "connect", synchronized_connect)
    monkeypatch.setattr(
        db,
        "current_database_timestamp",
        synchronized_transaction_time,
    )

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        winner_future = executor.submit(invoke, "winner", winner_action)
        assert winner_has_lock.wait(timeout=3)
        stale_future = executor.submit(invoke, "stale", stale_action)
        assert contention_proved.wait(timeout=3)
        assert not stale_future.done()
        release_winner.set()
        winner = winner_future.result(timeout=3)
        retry_stale_writer.set()
        stale = stale_future.result(timeout=3)
        return winner, stale, contention_proved.is_set()
    finally:
        release_winner.set()
        retry_stale_writer.set()
        executor.shutdown(wait=True, cancel_futures=True)


def timing_draft_json(*rows: db.TimingDraftRow) -> str:
    return json.dumps(
        [
            {
                "segment_id": row.segment_id,
                "start_date": row.start_date,
                "start_time": row.start_time,
                "stop_date": row.stop_date,
                "stop_time": row.stop_time,
                "deleted": row.deleted,
            }
            for row in rows
        ]
    )


def prepare_status_transition_race(
    order_number: str,
    target_status: str,
) -> tuple[int, int, int]:
    card_id = release_ready_card(order_number, 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    if target_status == STATUS_COMPLETED:
        assert db.update_tare_weight(card_id, card_version(card_id), "1.25").ok
        assert db.add_roll_gross_weight(
            card_id,
            card_version(card_id),
            "25.50",
        ).ok
    elif target_status == STATUS_AWAITING_REWINDING:
        assert db.update_rewinding_roll_count(
            card_id,
            card_version(card_id),
            1,
        ).ok
    with db.connect() as setup_connection:
        setup_connection.execute(
            """
            UPDATE cards
            SET actual_raw_material_used = 'Retain material',
                raw_material_brand_grade = 'Retain grade',
                raw_material_batch_lot = 'Retain batch'
            WHERE id = ?
            """,
            (card_id,),
        )
    return card_id, segment_id, card_version(card_id)


def commit_competing_status_transition(
    card_id: int,
    loaded_version: int,
    target_status: str,
) -> None:
    if target_status == STATUS_CANCELLED:
        result = db.cancel_card(card_id, loaded_version)
    else:
        result = db.finish_card(
            card_id,
            loaded_version,
            require_active_shift=True,
        )
    assert result.ok
    stored = db.fetch_admin_card_detail(card_id)
    assert stored is not None
    assert stored["status"] == target_status


def test_terminal_timing_save_allows_running_and_paused_with_active_shift(connection):
    running_id = release_ready_card("27001", 1)
    start_card(running_id)
    running_segment_id = set_single_segment(
        running_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    running_version = card_version(running_id)

    running_result = db.update_terminal_timing_ledger(
        running_id,
        running_version,
        [
            db.TimingDraftRow(
                segment_id=running_segment_id,
                start_date="2026-01-15",
                start_time="10:05",
                stop_date="",
                stop_time="",
            )
        ],
    )

    assert running_result.result.ok
    running_card = db.fetch_admin_card_detail(running_id)
    assert running_card is not None
    assert running_card["timing_segments"][0]["ended_at"] is None
    assert running_card["version"] == running_version + 1

    paused_id = release_ready_card("27002", 2)
    start_card(paused_id)
    paused_segment_id = set_single_segment(
        paused_id,
        started_at="2026-01-15 09:00:29",
        ended_at="2026-01-15 10:00:41",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    paused_version = card_version(paused_id)

    paused_result = db.update_terminal_timing_ledger(
        paused_id,
        paused_version,
        [
            db.TimingDraftRow(
                segment_id=paused_segment_id,
                start_date="2026-01-15",
                start_time="11:00",
                stop_date="2026-01-15",
                stop_time="12:05",
            )
        ],
    )

    assert paused_result.result.ok
    paused_card = db.fetch_admin_card_detail(paused_id)
    assert paused_card is not None
    assert paused_card["timing_segments"][0]["end_reason"] == "pause"
    assert paused_card["version"] == paused_version + 1


def test_terminal_timing_save_rejects_other_statuses_and_missing_shift(connection):
    card_id = release_ready_card("27003", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    draft = [
        db.TimingDraftRow(
            segment_id=segment_id,
            start_date="2026-01-15",
            start_time="10:00",
            stop_date="",
            stop_time="",
        )
    ]
    rejected_statuses = (
        STATUS_IMPORTED,
        STATUS_PENDING,
        STATUS_AWAITING_REWINDING,
        STATUS_COMPLETED,
        STATUS_ARCHIVED,
        STATUS_CANCELLED,
    )

    for status in rejected_statuses:
        with db.connect() as status_connection:
            status_connection.execute(
                "UPDATE cards SET status = ? WHERE id = ?",
                (status, card_id),
            )
        before = db.fetch_admin_card_detail(card_id)
        assert before is not None

        result = db.update_terminal_timing_ledger(
            card_id,
            int(before["version"]),
            draft,
        )

        after = db.fetch_admin_card_detail(card_id)
        assert after is not None
        assert not result.result.ok
        assert result.result.messages == (
            "Производственото време може да се коригира само за карта "
            "в изработване или на пауза.",
        )
        assert after["version"] == before["version"]
        assert after["timing_segments"] == before["timing_segments"]

    with db.connect() as status_connection:
        status_connection.execute(
            "UPDATE cards SET status = ? WHERE id = ?",
            (STATUS_RUNNING, card_id),
        )
    end_active_test_shift()
    before_missing_shift = db.fetch_admin_card_detail(card_id)
    assert before_missing_shift is not None

    missing_shift = db.update_terminal_timing_ledger(
        card_id,
        int(before_missing_shift["version"]),
        draft,
    )

    after_missing_shift = db.fetch_admin_card_detail(card_id)
    assert after_missing_shift is not None
    assert not missing_shift.result.ok
    assert missing_shift.result.messages == (db.NO_ACTIVE_SHIFT_MESSAGE,)
    assert after_missing_shift["version"] == before_missing_shift["version"]
    assert after_missing_shift["timing_segments"] == before_missing_shift["timing_segments"]


def test_terminal_timing_draft_rejects_duplicate_missing_unknown_and_foreign_ids(connection):
    card_id = release_ready_card("27004", 1)
    start_card(card_id)
    open_segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 10:00:17",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    closed_segment_id = insert_segment(
        card_id,
        started_at="2026-01-15 08:00:11",
        ended_at="2026-01-15 09:00:23",
        end_reason="pause",
    )
    foreign_card_id = release_ready_card("27005", 2)
    start_card(foreign_card_id)
    foreign_segment_id = set_single_segment(
        foreign_card_id,
        started_at="2026-01-15 11:00:00",
        ended_at="2026-01-15 12:00:00",
        end_reason="pause",
        status=STATUS_PAUSED,
    )

    closed_row = db.TimingDraftRow(
        segment_id=closed_segment_id,
        start_date="2026-01-15",
        start_time="10:00",
        stop_date="2026-01-15",
        stop_time="11:00",
    )
    open_row = db.TimingDraftRow(
        segment_id=open_segment_id,
        start_date="2026-01-15",
        start_time="12:00",
        stop_date="",
        stop_time="",
    )
    invalid_drafts = (
        [closed_row, open_row, open_row],
        [open_row],
        [closed_row, open_row, db.TimingDraftRow(999_999, "2026-01-15", "14:00", "", "")],
        [closed_row, open_row, db.TimingDraftRow(foreign_segment_id, "2026-01-15", "14:00", "", "")],
    )

    for draft in invalid_drafts:
        before = timing_snapshot(card_id)

        result = db.update_terminal_timing_ledger(
            card_id,
            before[0],
            draft,
        )

        assert not result.result.ok
        assert result.issues
        assert result.issues[0].field == "form"
        assert timing_snapshot(card_id) == before


def test_terminal_timing_failure_rolls_back_card_and_complete_ledger(connection):
    card_id = release_ready_card("27006", 1)
    start_card(card_id)
    open_segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    before = timing_snapshot(card_id)
    connection.execute(
        f"""
        CREATE TRIGGER fail_terminal_timing_insert
        BEFORE INSERT ON production_time_segments
        WHEN NEW.card_id = {card_id}
        BEGIN
            SELECT RAISE(ABORT, 'forced terminal timing failure');
        END
        """
    )
    connection.commit()

    result = db.update_terminal_timing_ledger(
        card_id,
        before[0],
        [
            db.TimingDraftRow(
                open_segment_id,
                "2026-01-15",
                "10:00",
                "2026-01-15",
                "11:00",
            ),
            db.TimingDraftRow(None, "2026-01-15", "12:00", "", ""),
        ],
    )

    assert not result.result.ok
    assert timing_snapshot(card_id) == before


def test_terminal_timing_enforces_running_and_paused_ledger_shapes(connection):
    running_id = release_ready_card("27007", 1)
    start_card(running_id)
    running_segment_id = set_single_segment(
        running_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    running_closed = db.TimingDraftRow(
        running_segment_id,
        "2026-01-15",
        "10:00",
        "2026-01-15",
        "11:00",
    )
    running_open = db.TimingDraftRow(
        running_segment_id,
        "2026-01-15",
        "10:00",
        "",
        "",
    )

    before_no_open = timing_snapshot(running_id)
    no_open = db.update_terminal_timing_ledger(
        running_id,
        before_no_open[0],
        [running_closed],
    )
    assert not no_open.result.ok
    assert timing_snapshot(running_id) == before_no_open

    before_two_open = timing_snapshot(running_id)
    two_open = db.update_terminal_timing_ledger(
        running_id,
        before_two_open[0],
        [running_open, db.TimingDraftRow(None, "2026-01-15", "12:00", "", "")],
    )
    assert not two_open.result.ok
    assert timing_snapshot(running_id) == before_two_open

    valid_running = db.update_terminal_timing_ledger(
        running_id,
        before_two_open[0],
        [running_closed, db.TimingDraftRow(None, "2026-01-15", "12:00", "", "")],
    )
    assert valid_running.result.ok
    running_after = db.fetch_admin_card_detail(running_id)
    assert running_after is not None
    assert [row["end_reason"] for row in running_after["timing_segments"]] == [
        "pause",
        None,
    ]

    paused_id = release_ready_card("27008", 2)
    start_card(paused_id)
    paused_segment_id = set_single_segment(
        paused_id,
        started_at="2026-01-15 08:00:37",
        ended_at="2026-01-15 09:00:41",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    paused_row = db.TimingDraftRow(
        paused_segment_id,
        "2026-01-15",
        "10:00",
        "2026-01-15",
        "11:00",
    )

    before_empty = timing_snapshot(paused_id)
    empty = db.update_terminal_timing_ledger(
        paused_id,
        before_empty[0],
        [db.TimingDraftRow(**{**paused_row.__dict__, "deleted": True})],
    )
    assert not empty.result.ok
    assert timing_snapshot(paused_id) == before_empty

    before_paused_open = timing_snapshot(paused_id)
    paused_open = db.update_terminal_timing_ledger(
        paused_id,
        before_paused_open[0],
        [
            db.TimingDraftRow(
                paused_segment_id,
                "2026-01-15",
                "10:00",
                "",
                "",
            )
        ],
    )
    assert not paused_open.result.ok
    assert timing_snapshot(paused_id) == before_paused_open


def test_terminal_timing_preserves_legacy_null_reason_on_existing_closed_edit(
    connection,
):
    card_id = release_ready_card("27008-legacy-null-reason", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 09:00:29",
        end_reason=None,
        status=STATUS_PAUSED,
    )
    before_version = card_version(card_id)

    outcome = db.update_terminal_timing_ledger(
        card_id,
        before_version,
        [
            db.TimingDraftRow(
                segment_id,
                "2026-01-15",
                "10:05",
                "2026-01-15",
                "11:05",
            )
        ],
    )

    assert outcome.result.ok
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    assert card["version"] == before_version + 1
    assert card["timing_segments"] == [
        {
            "id": segment_id,
            "started_at": "2026-01-15 08:05:00",
            "ended_at": "2026-01-15 09:05:00",
            "end_reason": None,
        }
    ]


def test_terminal_timing_rejects_equal_reversed_overlapping_and_future_rows(connection):
    card_id = release_ready_card("27009", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 09:00:29",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    invalid_cases = (
        (
            [
                db.TimingDraftRow(
                    segment_id,
                    "2026-01-15",
                    "10:00",
                    "2026-01-15",
                    "10:00",
                )
            ],
            "Краят трябва да бъде след началото.",
        ),
        (
            [
                db.TimingDraftRow(
                    segment_id,
                    "2026-01-15",
                    "11:00",
                    "2026-01-15",
                    "10:00",
                )
            ],
            "Краят трябва да бъде след началото.",
        ),
        (
            [
                db.TimingDraftRow(
                    segment_id,
                    "2026-01-15",
                    "10:00",
                    "2026-01-15",
                    "11:00",
                ),
                db.TimingDraftRow(
                    None,
                    "2026-01-15",
                    "10:30",
                    "2026-01-15",
                    "11:30",
                ),
            ],
            "Времевите сегменти не могат да се застъпват.",
        ),
        (
            [
                db.TimingDraftRow(
                    segment_id,
                    "2999-01-15",
                    "10:00",
                    "2999-01-15",
                    "11:00",
                )
            ],
            "Времето не може да бъде в бъдещето.",
        ),
    )

    for draft, expected_message in invalid_cases:
        before = timing_snapshot(card_id)

        result = db.update_terminal_timing_ledger(card_id, before[0], draft)

        assert not result.result.ok
        assert expected_message in result.result.messages
        assert timing_snapshot(card_id) == before


def test_terminal_timing_rejects_unchanged_zero_length_existing_segment(connection):
    card_id = release_ready_card("27009-legacy-zero", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:00",
        ended_at="2026-01-15 08:00:00",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    before = timing_snapshot(card_id)

    outcome = db.update_terminal_timing_ledger(
        card_id,
        before[0],
        [
            db.TimingDraftRow(
                segment_id,
                "2026-01-15",
                "10:00",
                "2026-01-15",
                "10:00",
            )
        ],
    )

    assert not outcome.result.ok
    assert outcome.result.messages == ("Краят трябва да бъде след началото.",)
    assert timing_snapshot(card_id) == before


def test_terminal_timing_allows_adjacent_rows(connection):
    card_id = release_ready_card("27010", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 09:00:00",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    before_version = card_version(card_id)

    result = db.update_terminal_timing_ledger(
        card_id,
        before_version,
        [
            db.TimingDraftRow(
                segment_id,
                "2026-01-15",
                "10:00",
                "2026-01-15",
                "11:00",
            ),
            db.TimingDraftRow(
                None,
                "2026-01-15",
                "11:00",
                "2026-01-15",
                "12:00",
            ),
        ],
    )

    assert result.result.ok
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    assert card["version"] == before_version + 1
    assert [
        (row["started_at"], row["ended_at"], row["end_reason"])
        for row in card["timing_segments"]
    ] == [
        ("2026-01-15 08:00:17", "2026-01-15 09:00:00", "pause"),
        ("2026-01-15 09:00:00", "2026-01-15 10:00:00", "correction"),
    ]


def test_terminal_timing_preserves_unchanged_seconds_and_zeroes_changed_minutes(connection):
    card_id = release_ready_card("27011", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at="2026-01-15 09:00:41",
        end_reason="pause",
        status=STATUS_PAUSED,
    )

    result = db.update_terminal_timing_ledger(
        card_id,
        card_version(card_id),
        [
            db.TimingDraftRow(
                segment_id,
                "2026-01-15",
                "10:00",
                "2026-01-15",
                "11:05",
            )
        ],
    )

    assert result.result.ok
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    assert card["timing_segments"][0]["started_at"] == "2026-01-15 08:00:37"
    assert card["timing_segments"][0]["ended_at"] == "2026-01-15 09:05:00"


def test_terminal_timing_handles_skipped_repeated_and_unchanged_ambiguous_minutes(connection):
    card_id = release_ready_card("27012", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at="2026-01-15 09:00:41",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    before_skipped = timing_snapshot(card_id)

    skipped = db.update_terminal_timing_ledger(
        card_id,
        before_skipped[0],
        [
            db.TimingDraftRow(
                segment_id,
                "2026-03-29",
                "03:30",
                "2026-03-29",
                "04:30",
            )
        ],
    )

    assert not skipped.result.ok
    assert skipped.issues[0].field == "start_time"
    assert timing_snapshot(card_id) == before_skipped

    before_repeated = timing_snapshot(card_id)
    repeated = db.update_terminal_timing_ledger(
        card_id,
        before_repeated[0],
        [
            db.TimingDraftRow(
                segment_id,
                "2026-10-25",
                "03:30",
                "2026-10-25",
                "04:30",
            )
        ],
    )

    assert not repeated.result.ok
    assert repeated.issues[0].field == "start_time"
    assert timing_snapshot(card_id) == before_repeated

    set_single_segment(
        card_id,
        started_at="2026-10-25 00:30:37",
        ended_at="2026-10-25 02:30:41",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    unchanged_ambiguous = db.update_terminal_timing_ledger(
        card_id,
        card_version(card_id),
        [
            db.TimingDraftRow(
                segment_id,
                "2026-10-25",
                "03:30",
                "2026-10-25",
                "04:30",
            )
        ],
    )

    assert unchanged_ambiguous.result.ok
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    assert card["timing_segments"][0]["started_at"] == "2026-10-25 00:30:37"
    assert card["timing_segments"][0]["ended_at"] == "2026-10-25 02:30:41"


def test_terminal_timing_rejects_unrepresentable_sofia_value_without_mutation(
    connection,
):
    card_id = release_ready_card("27012-timezone-overflow", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 09:00:29",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    before = timing_snapshot(card_id)
    submitted = db.TimingDraftRow(
        segment_id,
        "0001-01-01",
        "00:00",
        "0001-01-01",
        "01:00",
    )
    draft_json = timing_draft_json(submitted)

    preview_response = asyncio.run(
        main.preview_terminal_timing_ledger_route(
            make_test_request(
                f"/terminal/cards/{card_id}/timing-ledger/preview"
            ),
            card_id,
            loaded_version=str(before[0]),
            timing_draft=draft_json,
        )
    )
    save_response = asyncio.run(
        main.save_terminal_timing_ledger(
            make_test_request(f"/terminal/cards/{card_id}/timing-ledger"),
            card_id,
            loaded_version=str(before[0]),
            timing_draft=draft_json,
        )
    )

    expected_issues = [
        {
            "source_index": 0,
            "field": "start_time",
            "message": "Начало съдържа невалидна дата или час.",
        },
        {
            "source_index": 0,
            "field": "stop_time",
            "message": "Край съдържа невалидна дата или час.",
        },
    ]
    assert preview_response.status_code == 422
    assert json.loads(preview_response.body) == {
        "ok": False,
        "messages": [
            "Начало съдържа невалидна дата или час.",
            "Край съдържа невалидна дата или час.",
        ],
        "field_errors": expected_issues,
    }
    assert save_response.status_code == 200
    assert save_response.context["timing_result"].messages == (
        "Начало съдържа невалидна дата или час.",
        "Край съдържа невалидна дата или час.",
    )
    assert save_response.context["terminal_timing_issues"] == (
        db.TimingValidationIssue(
            source_index=0,
            field="start_time",
            message="Начало съдържа невалидна дата или час.",
        ),
        db.TimingValidationIssue(
            source_index=0,
            field="stop_time",
            message="Край съдържа невалидна дата или час.",
        ),
    )
    assert timing_snapshot(card_id) == before


def test_terminal_timing_save_preserves_unrelated_production_data_and_versions_once(connection):
    card_id = release_ready_card("27013", 1)
    start_card(card_id)
    assert db.update_tare_weight(card_id, card_version(card_id), "1.25").ok
    assert db.update_current_pallet_number(card_id, card_version(card_id), "7").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "25.50").ok
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        card_version(card_id),
        {
            "raw_material_a": {
                "actual_material_used": "Terminal Material",
                "batch_lot": "LOT-27013",
            }
        },
    ).ok
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 09:00:29",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    before_version = card_version(card_id)
    before_unrelated = unrelated_production_snapshot(card_id)

    result = db.update_terminal_timing_ledger(
        card_id,
        before_version,
        [
            db.TimingDraftRow(
                segment_id,
                "2026-01-15",
                "10:05",
                "2026-01-15",
                "11:05",
            ),
            db.TimingDraftRow(
                None,
                "2026-01-15",
                "12:00",
                "2026-01-15",
                "13:00",
            ),
        ],
    )

    assert result.result.ok
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    assert card["version"] == before_version + 1
    assert card["first_started_at"] == "2026-01-15 08:05:00"
    assert unrelated_production_snapshot(card_id) == before_unrelated


def test_terminal_timing_json_parser_rejects_oversize_extra_and_wrong_types(connection):
    valid_row = {
        "segment_id": None,
        "start_date": "2026-01-15",
        "start_time": "10:00",
        "stop_date": "",
        "stop_time": "",
        "deleted": False,
    }
    parsed = main.parse_terminal_timing_draft(
        json.dumps([valid_row, valid_row], ensure_ascii=False)
    )
    assert parsed == [
        db.TimingDraftRow(None, "2026-01-15", "10:00", "", ""),
        db.TimingDraftRow(None, "2026-01-15", "10:00", "", ""),
    ]

    invalid_values = [
        "я" * 32_769,
        "\ud800",
        "{",
        "[" * 1_100 + "]" * 1_100,
        (
            '[{"segment_id":null,"start_date":"","start_time":"",'
            '"stop_date":"","stop_time":"","deleted":false,'
            '"deleted":false}]'
        ),
        json.dumps(valid_row),
        json.dumps([valid_row] * 201),
        json.dumps(["row"]),
        json.dumps([{key: value for key, value in valid_row.items() if key != "deleted"}]),
        json.dumps([{**valid_row, "extra": "value"}]),
        json.dumps([{**valid_row, "segment_id": True}]),
        json.dumps([{**valid_row, "segment_id": 0}]),
        json.dumps([{**valid_row, "segment_id": 1.0}]),
        json.dumps([{**valid_row, "segment_id": "1"}]),
        json.dumps([{**valid_row, "deleted": 0}]),
        json.dumps([{**valid_row, "start_date": 20260115}]),
        json.dumps([{**valid_row, "start_date": "2026-02-30"}]),
        json.dumps([{**valid_row, "start_time": "24:00"}]),
        json.dumps([{**valid_row, "stop_date": "2026-01-15", "stop_time": ""}]),
        json.dumps([{**valid_row, "start_date": "", "start_time": "10:00"}]),
    ]

    for value in invalid_values:
        with pytest.raises(ValueError) as error:
            main.parse_terminal_timing_draft(value)
        assert str(error.value) == db.INVALID_TERMINAL_TIMING_DRAFT_MESSAGE


def test_terminal_timing_parser_ignores_timestamp_semantics_for_deleted_rows():
    parsed = main.parse_terminal_timing_draft(
        json.dumps(
            [
                {
                    "segment_id": 41,
                    "start_date": "",
                    "start_time": "13:",
                    "stop_date": "not-a-date",
                    "stop_time": "25:99",
                    "deleted": True,
                }
            ]
        )
    )

    assert parsed == [db.TimingDraftRow(41, "", "13:", "not-a-date", "25:99", True)]


def test_terminal_timing_future_boundary_does_not_emit_cascading_order_errors(
    connection,
):
    card_id = release_ready_card("27013-future-only", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 09:00:29",
        end_reason="pause",
        status=STATUS_PAUSED,
    )

    outcome = db.preview_terminal_timing_ledger(
        card_id,
        card_version(card_id),
        [
            db.TimingDraftRow(
                segment_id,
                "2099-01-15",
                "10:00",
                "2026-01-15",
                "11:00",
            )
        ],
        preview_at="2026-01-16 00:00:00",
    )

    assert outcome.result.messages == ("Времето не може да бъде в бъдещето.",)
    assert outcome.issues == (
        db.TimingValidationIssue(
            source_index=0,
            field="start_time",
            message="Времето не може да бъде в бъдещето.",
        ),
    )


def test_terminal_timing_preview_is_authoritative_nonpersistent_and_dst_correct(connection):
    paused_id = release_ready_card("27014", 1)
    start_card(paused_id)
    paused_segment_id = set_single_segment(
        paused_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 09:00:29",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    paused_before = timing_snapshot(paused_id)

    paused_outcome = db.preview_terminal_timing_ledger(
        paused_id,
        paused_before[0],
        [
            db.TimingDraftRow(
                paused_segment_id,
                "2026-03-29",
                "02:30",
                "2026-03-29",
                "04:30",
            )
        ],
        preview_at="2026-03-30 00:00:00",
    )

    assert paused_outcome.result.ok
    assert paused_outcome.preview is not None
    assert paused_outcome.preview.reviewed_at == "2026-03-30 00:00:00"
    assert paused_outcome.preview.first_started_at == "2026-03-29 00:30:00"
    assert paused_outcome.preview.proposed_finished_at == "2026-03-29 01:30:00"
    assert paused_outcome.preview.production_seconds == 3600
    assert paused_outcome.preview.paused_seconds == 0
    assert paused_outcome.preview.intervals == (
        {"source_index": 0, "duration_seconds": 3600},
    )
    assert timing_snapshot(paused_id) == paused_before

    running_id = release_ready_card("27015", 2)
    start_card(running_id)
    running_segment_id = set_single_segment(
        running_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    running_before = timing_snapshot(running_id)

    running_outcome = db.preview_terminal_timing_ledger(
        running_id,
        running_before[0],
        [
            db.TimingDraftRow(
                running_segment_id,
                "2026-01-15",
                "10:00",
                "",
                "",
            )
        ],
        preview_at="2026-01-15 09:00:45",
    )

    assert running_outcome.result.ok
    assert running_outcome.preview is not None
    assert running_outcome.preview.production_seconds == 3608
    assert running_outcome.preview.proposed_finished_at == "2026-01-15 09:00:45"
    assert running_outcome.preview.draft_rows[0].stop_date == ""
    assert running_outcome.preview.draft_rows[0].stop_time == ""
    assert timing_snapshot(running_id) == running_before


def test_terminal_timing_preview_targets_the_first_server_invalid_field(connection):
    card_id = release_ready_card("27016", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 09:00:29",
        end_reason="pause",
        status=STATUS_PAUSED,
    )

    outcome = db.preview_terminal_timing_ledger(
        card_id,
        card_version(card_id),
        [
            db.TimingDraftRow(
                None,
                "2026-01-15",
                "10:30",
                "2026-01-15",
                "11:30",
            ),
            db.TimingDraftRow(
                segment_id,
                "2026-01-15",
                "10:00",
                "2026-01-15",
                "11:00",
            ),
        ],
        preview_at="2026-01-16 00:00:00",
    )

    assert not outcome.result.ok
    assert outcome.issues[0] == db.TimingValidationIssue(
        source_index=0,
        field="start_time",
        message="Времевите сегменти не могат да се застъпват.",
    )


def test_terminal_timing_save_route_uses_successful_prg(connection):
    card_id = release_ready_card("27017", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )

    response = asyncio.run(
        main.save_terminal_timing_ledger(
            make_test_request(f"/terminal/cards/{card_id}/timing-ledger"),
            card_id,
            loaded_version=str(card_version(card_id)),
            timing_draft=timing_draft_json(
                db.TimingDraftRow(segment_id, "2026-01-15", "10:05", "", "")
            ),
        )
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=timing_saved"
    )
    notice_context = main.terminal_context(
        card_id,
        terminal_notice="timing_saved",
    )
    assert notice_context["terminal_feedback"]["toast"] == {
        "messages": ("Производственото време е записано.",)
    }


def test_terminal_timing_save_route_retains_invalid_draft(connection):
    card_id = release_ready_card("27018", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 09:00:29",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    loaded_version = str(card_version(card_id))
    submitted = db.TimingDraftRow(
        segment_id,
        "2026-01-15",
        "10:00",
        "2026-01-15",
        "10:00",
    )

    response = asyncio.run(
        main.save_terminal_timing_ledger(
            make_test_request(f"/terminal/cards/{card_id}/timing-ledger"),
            card_id,
            loaded_version=loaded_version,
            timing_draft=timing_draft_json(submitted),
        )
    )

    assert response.status_code == 200
    assert response.context["timing_result"].messages == (
        "Краят трябва да бъде след началото.",
    )
    assert response.context["terminal_timing_dialog_open"] is True
    assert response.context["terminal_timing_draft"] == [submitted]
    assert response.context["terminal_timing_loaded_version"] == loaded_version
    assert response.context["terminal_timing_stale"] is False


@pytest.mark.parametrize(
    ("invalid_values", "expected_field"),
    (
        (
            {
                "start_date": "2026-02-30",
                "start_time": "10:00",
                "stop_date": "",
                "stop_time": "",
            },
            "start_date",
        ),
        (
            {
                "start_date": "2026-01-15",
                "start_time": "10:00",
                "stop_date": "2026-01-15",
                "stop_time": "",
            },
            "stop_time",
        ),
    ),
)
def test_terminal_timing_parser_invalid_save_retains_safe_rows_in_render_model(
    connection,
    monkeypatch,
    invalid_values,
    expected_field,
):
    card_id = release_ready_card("27018-parser-retained", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    before = timing_snapshot(card_id)
    adapter_calls: list[int] = []

    def save_adapter(*args, **kwargs):
        adapter_calls.append(card_id)
        return None

    monkeypatch.setattr(main, "update_terminal_timing_ledger", save_adapter)
    submitted_row = {
        "segment_id": segment_id,
        **invalid_values,
        "deleted": False,
    }
    submitted_json = json.dumps([submitted_row])

    response = asyncio.run(
        main.save_terminal_timing_ledger(
            make_test_request(f"/terminal/cards/{card_id}/timing-ledger"),
            card_id,
            loaded_version=str(before[0]),
            timing_draft=submitted_json,
        )
    )

    assert response.status_code == 200
    assert response.context["timing_result"].messages == (
        db.INVALID_TERMINAL_TIMING_DRAFT_MESSAGE,
    )
    assert response.context["terminal_timing_issues"] == (
        db.TimingValidationIssue(
            source_index=0,
            field=expected_field,
            message=db.INVALID_TERMINAL_TIMING_DRAFT_MESSAGE,
        ),
    )
    assert response.context["terminal_timing_draft"] == [
        db.TimingDraftRow(segment_id=segment_id, **invalid_values)
    ]
    assert response.context["terminal_timing"]["draft"] == [submitted_row]
    assert response.context["terminal_timing_draft_json"] == submitted_json
    assert adapter_calls == []
    assert timing_snapshot(card_id) == before


def test_terminal_timing_save_route_locks_retained_stale_draft(connection):
    card_id = release_ready_card("27019", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 09:00:29",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    loaded_version = str(card_version(card_id))
    submitted = db.TimingDraftRow(
        segment_id,
        "2026-01-15",
        "10:05",
        "2026-01-15",
        "11:05",
    )
    with db.connect() as stale_connection:
        stale_connection.execute(
            """
            UPDATE cards
            SET customer = 'Concurrent manager change',
                version = version + 1
            WHERE id = ?
            """,
            (card_id,),
        )
    before = timing_snapshot(card_id)

    response = asyncio.run(
        main.save_terminal_timing_ledger(
            make_test_request(f"/terminal/cards/{card_id}/timing-ledger"),
            card_id,
            loaded_version=loaded_version,
            timing_draft=timing_draft_json(submitted),
        )
    )

    assert response.status_code == 200
    assert response.context["timing_result"].messages == (db.STALE_CARD_MESSAGE,)
    assert response.context["terminal_timing_dialog_open"] is True
    assert response.context["terminal_timing_draft"] == [submitted]
    assert response.context["terminal_timing_stale"] is True
    assert timing_snapshot(card_id) == before


@pytest.mark.parametrize(
    "target_status",
    (STATUS_COMPLETED, STATUS_CANCELLED, STATUS_AWAITING_REWINDING),
)
def test_terminal_timing_status_transition_retained_exact_locked_save_draft(
    connection,
    target_status,
):
    card_id, segment_id, loaded_version = prepare_status_transition_race(
        f"27019-save-status-transition-retained-{target_status}",
        target_status,
    )
    submitted_payload = [
        {
            "segment_id": segment_id,
            "start_date": "2026-01-15",
            "start_time": "10:05",
            "stop_date": "",
            "stop_time": "",
            "deleted": False,
        }
    ]
    submitted_json = json.dumps(submitted_payload, separators=(",", ":"))
    commit_competing_status_transition(card_id, loaded_version, target_status)
    after_competing_write = stored_finish_snapshot(card_id)

    response = asyncio.run(
        main.save_terminal_timing_ledger(
            make_test_request(f"/terminal/cards/{card_id}/timing-ledger"),
            card_id,
            loaded_version=str(loaded_version),
            timing_draft=submitted_json,
        )
    )

    assert response.status_code == 200
    assert response.context["timing_result"].messages == (db.STALE_CARD_MESSAGE,)
    assert response.context["terminal_timing_dialog_open"] is True
    assert response.context["terminal_timing_draft_json"] == submitted_json
    assert response.context["terminal_timing"]["draft"] == submitted_payload
    assert response.context["terminal_timing"]["locked"] is True
    assert response.context["terminal_timing"]["loaded_version"] == loaded_version
    assert response.context["terminal_timing"]["status"] == target_status
    assert b"data-terminal-timing-model" in response.body
    assert stored_finish_snapshot(card_id) == after_competing_write


@pytest.mark.parametrize(
    "target_status",
    (STATUS_COMPLETED, STATUS_CANCELLED, STATUS_AWAITING_REWINDING),
)
def test_terminal_finish_status_transition_retained_authenticated_locked_review(
    connection,
    target_status,
):
    card_id, _, loaded_version = prepare_status_transition_race(
        f"27019-finish-status-transition-retained-{target_status}",
        target_status,
    )
    review_response = asyncio.run(
        finish_review_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)
    submitted_json = json.dumps(
        review_payload["preview"]["draft"],
        separators=(",", ":"),
    )
    submitted_draft = main.parse_terminal_timing_draft(submitted_json)
    commit_competing_status_transition(card_id, loaded_version, target_status)
    after_competing_write = stored_finish_snapshot(card_id)

    response = asyncio.run(
        main.finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=submitted_json,
        )
    )

    assert response.status_code == 200
    assert response.context["workflow_result"].messages == (db.STALE_CARD_MESSAGE,)
    assert response.context["finish_review_open"] is True
    assert response.context["finish_review_stale"] is True
    assert response.context["finish_review_token"] == review_payload["review_token"]
    assert response.context["finish_review_draft"] == submitted_draft
    assert response.context["finish_review_draft_json"] == submitted_json
    assert response.context["terminal_timing"]["locked"] is True
    assert response.context["terminal_timing"]["status"] == target_status
    assert b"data-terminal-timing-model" in response.body
    assert b"data-finish-review-overlay" in response.body
    assert stored_finish_snapshot(card_id) == after_competing_write


@pytest.mark.parametrize(
    "target_status",
    (STATUS_COMPLETED, STATUS_CANCELLED),
)
def test_terminal_finish_status_transition_interleaving_retained_locked_review(
    connection,
    monkeypatch,
    target_status,
):
    card_id, _, loaded_version = prepare_status_transition_race(
        f"27019-finish-interleaving-retained-{target_status}",
        target_status,
    )
    review_response = asyncio.run(
        finish_review_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)
    submitted_json = json.dumps(
        review_payload["preview"]["draft"],
        separators=(",", ":"),
    )
    submitted_draft = main.parse_terminal_timing_draft(submitted_json)
    real_finish = main.finish_card_with_timing_ledger
    competing_snapshot: dict[str, object] = {}
    interleaving_calls = 0

    def finish_after_competing_transition(*args, **kwargs):
        nonlocal interleaving_calls
        interleaving_calls += 1
        commit_competing_status_transition(card_id, loaded_version, target_status)
        competing_snapshot.update(stored_finish_snapshot(card_id))
        return real_finish(*args, **kwargs)

    monkeypatch.setattr(
        main,
        "finish_card_with_timing_ledger",
        finish_after_competing_transition,
    )

    response = asyncio.run(
        main.finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=submitted_json,
        )
    )

    assert interleaving_calls == 1
    assert response.status_code == 200
    assert response.context["workflow_result"].messages == (db.STALE_CARD_MESSAGE,)
    assert response.context["finish_review_open"] is True
    assert response.context["finish_review_stale"] is True
    assert response.context["finish_review_token"] == review_payload["review_token"]
    assert response.context["finish_review_draft"] == submitted_draft
    assert response.context["finish_review_draft_json"] == submitted_json
    assert response.context["terminal_timing"]["draft"] == [
        main.terminal_timing_draft_row_payload(row) for row in submitted_draft
    ]
    assert response.context["terminal_timing"]["locked"] is True
    assert response.context["terminal_timing"]["status"] == target_status
    assert b"data-terminal-timing-model" in response.body
    assert b"data-finish-review-overlay" in response.body
    assert stored_finish_snapshot(card_id) == competing_snapshot


@pytest.mark.parametrize("current_status", (STATUS_COMPLETED, STATUS_CANCELLED))
def test_finish_review_transaction_same_version_ineligible_status_is_not_stale(
    connection,
    current_status,
):
    card_id, segment_id, loaded_version = prepare_status_transition_race(
        f"27019-finish-same-version-{current_status}",
        current_status,
    )
    with db.connect() as status_connection:
        status_connection.execute(
            "UPDATE cards SET status = ? WHERE id = ?",
            (current_status, card_id),
        )
    before = stored_finish_snapshot(card_id)

    outcome = db.finish_card_with_timing_ledger(
        card_id,
        loaded_version,
        [
            db.TimingDraftRow(
                segment_id,
                "2026-01-15",
                "10:00",
                "2026-01-15",
                "11:00",
            )
        ],
        "2026-01-15 12:34:56",
    )

    assert not outcome.result.ok
    assert outcome.result.messages == (
        "Производственото време може да се коригира само за карта "
        "в изработване или на пауза.",
    )
    assert db.STALE_CARD_MESSAGE not in outcome.result.messages
    assert stored_finish_snapshot(card_id) == before


def test_terminal_timing_preview_route_returns_authoritative_json(connection):
    card_id = release_ready_card("27020", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    submitted = db.TimingDraftRow(
        segment_id,
        "2026-01-15",
        "10:00",
        "",
        "",
    )

    response = asyncio.run(
        main.preview_terminal_timing_ledger_route(
            make_test_request(
                f"/terminal/cards/{card_id}/timing-ledger/preview"
            ),
            card_id,
            loaded_version=str(card_version(card_id)),
            timing_draft=timing_draft_json(submitted),
        )
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["ok"] is True
    assert payload["review_token"] is None
    assert payload["preview"]["first_start_display"] == "15.01.2026 10:00"
    assert payload["preview"]["draft"] == [
        {
            "segment_id": segment_id,
            "start_date": "2026-01-15",
            "start_time": "10:00",
            "stop_date": "",
            "stop_time": "",
            "deleted": False,
        }
    ]
    assert payload["preview"]["production_seconds"] >= 0
    assert payload["preview"]["paused_seconds"] == 0
    assert payload["preview"]["intervals"][0]["source_index"] == 0


def test_terminal_timing_reordered_intervals_preview_save_and_reload_chronologically(
    connection,
):
    card_id = release_ready_card("27020-reordered-save", 1)
    start_card(card_id)
    later_segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 09:00:23",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    earlier_segment_id = insert_segment(
        card_id,
        started_at="2026-01-15 10:00:31",
        ended_at="2026-01-15 11:00:41",
        end_reason="correction",
    )
    loaded_version = card_version(card_id)
    submitted_rows = [
        db.TimingDraftRow(
            later_segment_id,
            "2026-01-15",
            "11:00",
            "2026-01-15",
            "13:00",
        ),
        db.TimingDraftRow(
            earlier_segment_id,
            "2026-01-15",
            "08:00",
            "2026-01-15",
            "09:00",
        ),
    ]
    submitted_json = timing_draft_json(*submitted_rows)

    preview_response = asyncio.run(
        main.preview_terminal_timing_ledger_route(
            make_test_request(
                f"/terminal/cards/{card_id}/timing-ledger/preview"
            ),
            card_id,
            loaded_version=str(loaded_version),
            timing_draft=submitted_json,
        )
    )

    assert preview_response.status_code == 200
    preview = json.loads(preview_response.body)["preview"]
    assert [row["source_index"] for row in preview["intervals"]] == [1, 0]
    assert [row["duration_seconds"] for row in preview["intervals"]] == [3_600, 7_200]
    assert preview["first_start_display"] == "15.01.2026 08:00"
    assert preview["proposed_stop_display"] == "15.01.2026 13:00"
    assert preview["production_seconds"] == 10_800
    assert preview["paused_seconds"] == 7_200

    save_response = asyncio.run(
        main.save_terminal_timing_ledger(
            make_test_request(f"/terminal/cards/{card_id}/timing-ledger"),
            card_id,
            loaded_version=str(loaded_version),
            timing_draft=submitted_json,
        )
    )

    assert save_response.status_code == 303
    reloaded = db.fetch_terminal_card_detail(card_id)
    assert reloaded is not None
    assert [
        row["id"] for row in reloaded["timing_segments"]
    ] == [earlier_segment_id, later_segment_id]
    assert [
        row["started_at"] for row in reloaded["timing_segments"]
    ] == ["2026-01-15 06:00:00", "2026-01-15 09:00:00"]


def test_terminal_finish_reordered_preview_and_rejected_confirmation_retain_chronology(
    connection,
    monkeypatch,
):
    card_id = release_ready_card("27020-reordered-finish", 1)
    start_card(card_id)
    later_segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 07:00:17",
        ended_at="2026-01-15 08:00:23",
        end_reason="pause",
        status=STATUS_RUNNING,
    )
    earlier_segment_id = insert_segment(
        card_id,
        started_at="2026-01-15 09:00:31",
        ended_at=None,
        end_reason=None,
    )
    loaded_version = card_version(card_id)
    before = stored_finish_snapshot(card_id)
    monkeypatch.setattr(
        db,
        "current_database_timestamp",
        lambda connection: "2026-01-15 12:00:00",
    )
    review_response = asyncio.run(
        finish_review_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)
    submitted_rows = [
        db.TimingDraftRow(
            later_segment_id,
            "2026-01-15",
            "11:00",
            "2026-01-15",
            "13:00",
        ),
        db.TimingDraftRow(
            earlier_segment_id,
            "2026-01-15",
            "08:00",
            "2026-01-15",
            "09:00",
        ),
    ]
    submitted_json = timing_draft_json(*submitted_rows)

    preview_response = asyncio.run(
        finish_review_preview_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review/preview"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=submitted_json,
        )
    )

    assert preview_response.status_code == 200
    preview = json.loads(preview_response.body)["preview"]
    assert [row["source_index"] for row in preview["intervals"]] == [1, 0]
    assert [row["duration_seconds"] for row in preview["intervals"]] == [3_600, 7_200]
    assert preview["first_start_display"] == "15.01.2026 08:00"
    assert preview["proposed_stop_display"] == "15.01.2026 13:00"
    assert preview["production_seconds"] == 10_800
    assert preview["paused_seconds"] == 7_200

    rejected_response = asyncio.run(
        main.finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=submitted_json,
        )
    )

    expected_message = "Поне едно бруто тегло на ролка е задължително преди приключване."
    assert rejected_response.context["workflow_result"].messages == (expected_message,)
    retained_model = terminal_timing_model_from_response(rejected_response)
    assert [
        row["segment_id"] for row in retained_model["finish_review"]["draft"]
    ] == [later_segment_id, earlier_segment_id]
    assert retained_model["finish_review"]["preview"] == {
        "first_start_display": "15.01.2026 08:00",
        "proposed_stop_display": "15.01.2026 13:00",
        "production_seconds": 10_800,
        "paused_seconds": 7_200,
        "intervals": [
            {"source_index": 1, "duration_seconds": 3_600},
            {"source_index": 0, "duration_seconds": 7_200},
        ],
    }
    assert stored_finish_snapshot(card_id) == before


def test_terminal_timing_routes_parse_before_database_adapter(connection, monkeypatch):
    card_id = release_ready_card("27021", 1)
    start_card(card_id)
    adapter_calls: list[str] = []

    def preview_adapter(*args, **kwargs):
        adapter_calls.append("preview")
        return None

    def save_adapter(*args, **kwargs):
        adapter_calls.append("save")
        return None

    monkeypatch.setattr(main, "preview_terminal_timing_ledger_data", preview_adapter)
    monkeypatch.setattr(main, "update_terminal_timing_ledger", save_adapter)

    preview_response = asyncio.run(
        main.preview_terminal_timing_ledger_route(
            make_test_request(
                f"/terminal/cards/{card_id}/timing-ledger/preview"
            ),
            card_id,
            loaded_version=str(card_version(card_id)),
            timing_draft="{",
        )
    )
    save_response = asyncio.run(
        main.save_terminal_timing_ledger(
            make_test_request(f"/terminal/cards/{card_id}/timing-ledger"),
            card_id,
            loaded_version=str(card_version(card_id)),
            timing_draft="{",
        )
    )

    assert preview_response.status_code == 422
    assert json.loads(preview_response.body) == {
        "ok": False,
        "messages": [db.INVALID_TERMINAL_TIMING_DRAFT_MESSAGE],
        "field_errors": [
            {
                "source_index": None,
                "field": "form",
                "message": db.INVALID_TERMINAL_TIMING_DRAFT_MESSAGE,
            }
        ],
    }
    assert save_response.status_code == 200
    assert save_response.context["timing_result"].messages == (
        db.INVALID_TERMINAL_TIMING_DRAFT_MESSAGE,
    )
    assert save_response.context["terminal_timing_draft_json"] == "{"
    assert adapter_calls == []


def test_terminal_timing_decoder_depth_failure_returns_malformed_before_adapter(
    connection,
    monkeypatch,
):
    card_id = release_ready_card("27021-decoder-depth", 1)
    start_card(card_id)
    before = timing_snapshot(card_id)
    adapter_calls: list[str] = []

    def preview_adapter(*args, **kwargs):
        adapter_calls.append("preview")
        return None

    def save_adapter(*args, **kwargs):
        adapter_calls.append("save")
        return None

    monkeypatch.setattr(main, "preview_terminal_timing_ledger_data", preview_adapter)
    monkeypatch.setattr(main, "update_terminal_timing_ledger", save_adapter)
    deeply_nested_json = "[" * 30_000 + "]" * 30_000

    preview_response = asyncio.run(
        main.preview_terminal_timing_ledger_route(
            make_test_request(
                f"/terminal/cards/{card_id}/timing-ledger/preview"
            ),
            card_id,
            loaded_version=str(card_version(card_id)),
            timing_draft=deeply_nested_json,
        )
    )
    save_response = asyncio.run(
        main.save_terminal_timing_ledger(
            make_test_request(f"/terminal/cards/{card_id}/timing-ledger"),
            card_id,
            loaded_version=str(card_version(card_id)),
            timing_draft=deeply_nested_json,
        )
    )

    expected_error = {
        "ok": False,
        "messages": [db.INVALID_TERMINAL_TIMING_DRAFT_MESSAGE],
        "field_errors": [
            {
                "source_index": None,
                "field": "form",
                "message": db.INVALID_TERMINAL_TIMING_DRAFT_MESSAGE,
            }
        ],
    }
    assert preview_response.status_code == 422
    assert json.loads(preview_response.body) == expected_error
    assert save_response.status_code == 200
    assert save_response.context["timing_result"].messages == (
        db.INVALID_TERMINAL_TIMING_DRAFT_MESSAGE,
    )
    assert adapter_calls == []
    assert timing_snapshot(card_id) == before


def test_terminal_timing_preview_parser_targets_row_and_field(connection):
    card_id = release_ready_card("27021-parser-target", 1)
    malformed_row = {
        "segment_id": None,
        "start_date": "2026-02-30",
        "start_time": "10:00",
        "stop_date": "",
        "stop_time": "",
        "deleted": False,
    }

    response = asyncio.run(
        main.preview_terminal_timing_ledger_route(
            make_test_request(
                f"/terminal/cards/{card_id}/timing-ledger/preview"
            ),
            card_id,
            loaded_version=str(card_version(card_id)),
            timing_draft=json.dumps([malformed_row]),
        )
    )

    assert response.status_code == 422
    assert json.loads(response.body)["field_errors"] == [
        {
            "source_index": 0,
            "field": "start_date",
            "message": db.INVALID_TERMINAL_TIMING_DRAFT_MESSAGE,
        }
    ]


def test_terminal_timing_preview_and_save_do_not_mutate_when_stale_or_shift_missing(connection):
    card_id = release_ready_card("27022", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 09:00:29",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    current_version = card_version(card_id)
    submitted = timing_draft_json(
        db.TimingDraftRow(
            segment_id,
            "2026-01-15",
            "10:05",
            "2026-01-15",
            "11:05",
        )
    )
    before = timing_snapshot(card_id)

    stale_preview = asyncio.run(
        main.preview_terminal_timing_ledger_route(
            make_test_request(
                f"/terminal/cards/{card_id}/timing-ledger/preview"
            ),
            card_id,
            loaded_version=str(current_version - 1),
            timing_draft=submitted,
        )
    )
    stale_save = asyncio.run(
        main.save_terminal_timing_ledger(
            make_test_request(f"/terminal/cards/{card_id}/timing-ledger"),
            card_id,
            loaded_version=str(current_version - 1),
            timing_draft=submitted,
        )
    )

    assert stale_preview.status_code == 409
    assert json.loads(stale_preview.body)["messages"] == [db.STALE_CARD_MESSAGE]
    assert stale_save.context["timing_result"].messages == (db.STALE_CARD_MESSAGE,)
    assert timing_snapshot(card_id) == before

    end_active_test_shift()
    missing_shift_preview = asyncio.run(
        main.preview_terminal_timing_ledger_route(
            make_test_request(
                f"/terminal/cards/{card_id}/timing-ledger/preview"
            ),
            card_id,
            loaded_version=str(current_version),
            timing_draft=submitted,
        )
    )
    missing_shift_save = asyncio.run(
        main.save_terminal_timing_ledger(
            make_test_request(f"/terminal/cards/{card_id}/timing-ledger"),
            card_id,
            loaded_version=str(current_version),
            timing_draft=submitted,
        )
    )

    assert missing_shift_preview.status_code == 422
    assert json.loads(missing_shift_preview.body)["messages"] == [
        db.NO_ACTIVE_SHIFT_MESSAGE
    ]
    assert missing_shift_save.context["timing_result"].messages == (
        db.NO_ACTIVE_SHIFT_MESSAGE,
    )
    assert timing_snapshot(card_id) == before


def test_terminal_timing_preview_and_save_routes_reject_non_active_status(connection):
    card_id = release_ready_card("27023", 1)
    before = timing_snapshot(card_id)

    preview_response = asyncio.run(
        main.preview_terminal_timing_ledger_route(
            make_test_request(
                f"/terminal/cards/{card_id}/timing-ledger/preview"
            ),
            card_id,
            loaded_version=str(before[0]),
            timing_draft="[]",
        )
    )
    save_response = asyncio.run(
        main.save_terminal_timing_ledger(
            make_test_request(f"/terminal/cards/{card_id}/timing-ledger"),
            card_id,
            loaded_version=str(before[0]),
            timing_draft="[]",
        )
    )

    expected_message = (
        "Производственото време може да се коригира само за карта "
        "в изработване или на пауза."
    )
    assert preview_response.status_code == 422
    assert json.loads(preview_response.body)["messages"] == [expected_message]
    assert save_response.context["timing_result"].messages == (expected_message,)
    assert timing_snapshot(card_id) == before


def test_finish_review_freezes_time_and_writes_nothing(connection, monkeypatch):
    card_id = release_ready_card("27024", 1)
    start_card(card_id)
    set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    loaded_version = card_version(card_id)
    before = stored_finish_snapshot(card_id)
    monkeypatch.setattr(
        db,
        "current_database_timestamp",
        lambda connection: "2026-01-15 12:34:56",
    )

    response = asyncio.run(
        finish_review_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["ok"] is True
    assert payload["preview"]["reviewed_at_utc"] == "2026-01-15 12:34:56"
    assert payload["preview"]["proposed_stop_display"] == "15.01.2026 14:34"
    assert stored_finish_snapshot(card_id) == before


def test_running_finish_initial_review_rejects_closed_only_stored_ledger_without_mutation(
    connection,
    monkeypatch,
):
    card_id = release_ready_card("27024-closed-only-review", 1)
    start_card(card_id)
    set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at="2026-01-15 09:00:29",
        end_reason="correction",
        status=STATUS_RUNNING,
    )
    loaded_version = card_version(card_id)
    before = stored_finish_snapshot(card_id)
    monkeypatch.setattr(
        db,
        "current_database_timestamp",
        lambda connection: "2026-01-15 12:34:56",
    )

    response = asyncio.run(
        finish_review_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )

    assert response.status_code == 422
    assert json.loads(response.body) == {
        "ok": False,
        "messages": [
            "Картите в изработване трябва да имат активен времеви сегмент. "
            "Презаредете картата."
        ],
        "field_errors": [
            {
                "source_index": None,
                "field": "form",
                "message": (
                    "Картите в изработване трябва да имат активен времеви "
                    "сегмент. Презаредете картата."
                ),
            }
        ],
    }
    assert stored_finish_snapshot(card_id) == before


def test_finish_review_returns_server_normalized_editable_stop(connection, monkeypatch):
    card_id = release_ready_card("27025", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    monkeypatch.setattr(
        db,
        "current_database_timestamp",
        lambda connection: "2026-01-15 12:34:56",
    )

    response = asyncio.run(
        finish_review_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(card_version(card_id)),
        )
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["preview"]["draft"] == [
        {
            "segment_id": segment_id,
            "start_date": "2026-01-15",
            "start_time": "10:00",
            "stop_date": "2026-01-15",
            "stop_time": "14:34",
            "deleted": False,
        }
    ]


def test_finish_review_token_rejects_tampering_substitution_and_new_process_key(
    connection,
    monkeypatch,
):
    card_id = release_ready_card("27026", 1)
    start_card(card_id)
    set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    loaded_version = card_version(card_id)
    key = b"a" * 32
    monkeypatch.setattr(main, "FINISH_REVIEW_TOKEN_KEY", key)

    review_response = asyncio.run(
        finish_review_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)
    token = review_payload["review_token"]
    assert isinstance(token, str) and token.count(".") == 1
    decoded = main.decode_finish_review_token(token, key=key)
    assert decoded == {
        "card_id": card_id,
        "loaded_version": loaded_version,
        "reviewed_at": review_payload["preview"]["reviewed_at_utc"],
    }
    draft_json = json.dumps(review_payload["preview"]["draft"])
    before = stored_finish_snapshot(card_id)
    payload_part, signature_part = token.split(".")
    replacement = "A" if signature_part[0] != "A" else "B"
    tampered = f"{payload_part}.{replacement}{signature_part[1:]}"
    substituted_card = main.encode_finish_review_token(
        card_id + 1,
        loaded_version,
        review_payload["preview"]["reviewed_at_utc"],
        key=key,
    )
    substituted_version = main.encode_finish_review_token(
        card_id,
        loaded_version + 1,
        review_payload["preview"]["reviewed_at_utc"],
        key=key,
    )

    rejected_responses = []
    for rejected_token in (tampered, substituted_card, substituted_version):
        rejected_responses.append(
            asyncio.run(
                finish_review_preview_endpoint()(
                    make_test_request(
                        f"/terminal/cards/{card_id}/finish-review/preview"
                    ),
                    card_id,
                    loaded_version=str(loaded_version),
                    review_token=rejected_token,
                    timing_draft=draft_json,
                )
            )
        )

    monkeypatch.setattr(main, "FINISH_REVIEW_TOKEN_KEY", b"b" * 32)
    rejected_responses.append(
        asyncio.run(
            finish_review_preview_endpoint()(
                make_test_request(
                    f"/terminal/cards/{card_id}/finish-review/preview"
                ),
                card_id,
                loaded_version=str(loaded_version),
                review_token=token,
                timing_draft=draft_json,
            )
        )
    )

    for response in rejected_responses:
        assert response.status_code == 422
        assert json.loads(response.body) == {
            "ok": False,
            "messages": [
                "Прегледът за приключване е невалиден. Отворете го отново."
            ],
            "field_errors": [
                {
                    "source_index": None,
                    "field": "form",
                    "message": (
                        "Прегледът за приключване е невалиден. "
                        "Отворете го отново."
                    ),
                }
            ],
        }
    assert stored_finish_snapshot(card_id) == before


def test_finish_review_token_rejects_malformed_and_noncanonical_signed_payloads():
    key = b"canonical-review-key" * 2

    def signed_token(payload: bytes) -> str:
        payload_text = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        signature = hmac.new(key, payload, hashlib.sha256).digest()
        signature_text = (
            base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        )
        return f"{payload_text}.{signature_text}"

    invalid_tokens = [
        "",
        "not-a-token",
        signed_token(b"{"),
        signed_token(
            b'{"card_id":1,"loaded_version":2,"reviewed_at":"2026-1-1 00:00:00"}'
        ),
        signed_token(
            b'{"reviewed_at":"2026-01-01 00:00:00", "loaded_version":2, "card_id":1}'
        ),
        signed_token(
            b'{"card_id":1,"loaded_version":2,"reviewed_at":"2026-01-01 00:00:00","extra":true}'
        ),
    ]

    for token in invalid_tokens:
        with pytest.raises(ValueError) as error:
            main.decode_finish_review_token(token, key=key)
        assert str(error.value) == (
            "Прегледът за приключване е невалиден. Отворете го отново."
        )
    with pytest.raises(ValueError):
        main.encode_finish_review_token(
            1,
            2,
            "2026-1-1 00:00:00",
            key=key,
        )


def test_finish_preview_rejects_stale_or_missing_shift_and_retains_draft(
    connection,
    monkeypatch,
):
    card_id = release_ready_card("27027", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    loaded_version = card_version(card_id)
    review_response = asyncio.run(
        finish_review_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)
    reviewed_at = review_payload["preview"]["reviewed_at_utc"]
    submitted = db.TimingDraftRow(
        segment_id,
        "2026-01-15",
        "09:30",
        review_payload["preview"]["draft"][0]["stop_date"],
        review_payload["preview"]["draft"][0]["stop_time"],
    )
    submitted_json = timing_draft_json(submitted)
    before = stored_finish_snapshot(card_id)
    captured_drafts: list[list[db.TimingDraftRow]] = []
    real_preview = main.preview_terminal_timing_ledger_data

    def capture_preview(*args, **kwargs):
        captured_drafts.append(list(args[2]))
        return real_preview(*args, **kwargs)

    monkeypatch.setattr(main, "preview_terminal_timing_ledger_data", capture_preview)
    stale_version = loaded_version - 1
    stale_token = main.encode_finish_review_token(
        card_id,
        stale_version,
        reviewed_at,
        key=main.FINISH_REVIEW_TOKEN_KEY,
    )
    stale_response = asyncio.run(
        finish_review_preview_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review/preview"),
            card_id,
            loaded_version=str(stale_version),
            review_token=stale_token,
            timing_draft=submitted_json,
        )
    )

    end_active_test_shift()
    missing_shift_response = asyncio.run(
        finish_review_preview_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review/preview"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=submitted_json,
        )
    )

    assert stale_response.status_code == 409
    assert json.loads(stale_response.body)["messages"] == [db.STALE_CARD_MESSAGE]
    assert missing_shift_response.status_code == 422
    assert json.loads(missing_shift_response.body)["messages"] == [
        db.NO_ACTIVE_SHIFT_MESSAGE
    ]
    assert captured_drafts == [[submitted], [submitted]]
    assert stored_finish_snapshot(card_id) == before


def test_finish_preview_recalculates_without_mutation(connection, monkeypatch):
    card_id = release_ready_card("27028", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    loaded_version = card_version(card_id)
    monkeypatch.setattr(
        db,
        "current_database_timestamp",
        lambda connection: "2026-01-15 12:34:56",
    )
    review_response = asyncio.run(
        finish_review_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)
    before = stored_finish_snapshot(card_id)
    corrected = db.TimingDraftRow(
        segment_id,
        "2026-01-15",
        "10:00",
        "2026-01-15",
        "12:00",
    )

    response = asyncio.run(
        finish_review_preview_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review/preview"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=timing_draft_json(corrected),
        )
    )

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["review_token"] == review_payload["review_token"]
    assert payload["preview"]["reviewed_at_utc"] == "2026-01-15 12:34:56"
    assert payload["preview"]["proposed_stop_display"] == "15.01.2026 12:00"
    assert payload["preview"]["production_seconds"] == 7_163
    assert payload["preview"]["paused_seconds"] == 0
    assert stored_finish_snapshot(card_id) == before


def test_running_finish_review_preview_rejects_closed_only_stored_ledger_without_mutation(
    connection,
):
    card_id = release_ready_card("27028-closed-only-preview", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at="2026-01-15 09:00:29",
        end_reason="correction",
        status=STATUS_RUNNING,
    )
    loaded_version = card_version(card_id)
    reviewed_at = "2026-01-15 12:34:56"
    review_token = main.encode_finish_review_token(
        card_id,
        loaded_version,
        reviewed_at,
        key=main.FINISH_REVIEW_TOKEN_KEY,
    )
    submitted = db.TimingDraftRow(
        segment_id,
        "2026-01-15",
        "10:00",
        "2026-01-15",
        "11:00",
    )
    before = stored_finish_snapshot(card_id)

    response = asyncio.run(
        finish_review_preview_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review/preview"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=review_token,
            timing_draft=timing_draft_json(submitted),
        )
    )

    expected_message = (
        "Картите в изработване трябва да имат активен времеви сегмент. "
        "Презаредете картата."
    )
    assert response.status_code == 422
    assert json.loads(response.body) == {
        "ok": False,
        "messages": [expected_message],
        "field_errors": [
            {
                "source_index": None,
                "field": "form",
                "message": expected_message,
            }
        ],
    }
    assert stored_finish_snapshot(card_id) == before


@pytest.mark.parametrize(
    ("failure_kind", "expected_message"),
    [
        ("stale", db.STALE_CARD_MESSAGE),
        ("missing_shift", db.NO_ACTIVE_SHIFT_MESSAGE),
        ("future", "Времето не може да бъде в бъдещето."),
        (
            "rolls",
            "Поне едно бруто тегло на ролка е задължително преди приключване.",
        ),
    ],
)
def test_finish_with_timing_rolls_back_every_validation_failure(
    connection,
    failure_kind,
    expected_message,
):
    card_id = release_ready_card(f"27029-{failure_kind}", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    if failure_kind != "rolls":
        assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
        assert db.add_roll_gross_weight(card_id, card_version(card_id), "25.00").ok
    loaded_version = card_version(card_id)
    submitted_stop = "15:00" if failure_kind == "future" else "14:00"
    draft_rows = [
        db.TimingDraftRow(
            segment_id,
            "2026-01-15",
            "10:00",
            "2026-01-15",
            submitted_stop,
        )
    ]
    if failure_kind == "stale":
        loaded_version -= 1
    elif failure_kind == "missing_shift":
        end_active_test_shift()
    before = stored_finish_snapshot(card_id)

    outcome = db.finish_card_with_timing_ledger(
        card_id,
        loaded_version,
        draft_rows,
        "2026-01-15 12:34:56",
    )

    assert not outcome.result.ok
    assert expected_message in outcome.result.messages
    assert stored_finish_snapshot(card_id) == before


def test_running_reviewed_confirmation_rejects_closed_only_stored_ledger_without_mutation(
    connection,
):
    card_id = release_ready_card("27029-closed-only-confirm", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at="2026-01-15 09:00:29",
        end_reason="correction",
        status=STATUS_RUNNING,
    )
    assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "25.00").ok
    loaded_version = card_version(card_id)
    before = stored_finish_snapshot(card_id)

    outcome = db.finish_card_with_timing_ledger(
        card_id,
        loaded_version,
        [
            db.TimingDraftRow(
                segment_id,
                "2026-01-15",
                "10:00",
                "2026-01-15",
                "11:00",
            )
        ],
        "2026-01-15 12:34:56",
    )

    assert not outcome.result.ok
    assert outcome.result.messages == (
        "Картите в изработване трябва да имат активен времеви сегмент. "
        "Презаредете картата.",
    )
    assert stored_finish_snapshot(card_id) == before


def test_finish_with_timing_uses_one_lifecycle_version_increment(
    connection,
    monkeypatch,
):
    card_id = release_ready_card("27030", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "25.00").ok
    loaded_version = card_version(card_id)

    def forbidden_touch(*args, **kwargs):
        raise AssertionError("reviewed finish must not call touch_card")

    monkeypatch.setattr(db, "touch_card", forbidden_touch)
    outcome = db.finish_card_with_timing_ledger(
        card_id,
        loaded_version,
        [
            db.TimingDraftRow(
                segment_id,
                "2026-01-15",
                "10:00",
                "2026-01-15",
                "14:00",
            )
        ],
        "2026-01-15 12:34:56",
    )

    after = stored_finish_snapshot(card_id)
    assert outcome.result.ok
    assert after["card"]["status"] == STATUS_COMPLETED
    assert after["card"]["version"] == loaded_version + 1
    assert after["card"]["finished_at"] == "2026-01-15 12:00:00"
    assert after["timing_rows"][0]["ended_at"] == "2026-01-15 12:00:00"
    assert after["timing_rows"][0]["end_reason"] == "finish"


def test_failed_active_finish_confirmation_reopens_retained_review_draft(
    connection,
    monkeypatch,
):
    card_id = release_ready_card("27031", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    loaded_version = card_version(card_id)
    monkeypatch.setattr(
        db,
        "current_database_timestamp",
        lambda connection: "2026-01-15 12:34:56",
    )
    review_response = asyncio.run(
        finish_review_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)
    retained_row = db.TimingDraftRow(
        segment_id,
        "2026-01-15",
        "10:00",
        "2026-01-15",
        "14:00",
    )
    retained_json = timing_draft_json(retained_row)
    before = stored_finish_snapshot(card_id)

    response = asyncio.run(
        main.finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=retained_json,
        )
    )

    assert response.status_code == 200
    assert response.context["workflow_result"].messages == (
        "Поне едно бруто тегло на ролка е задължително преди приключване.",
    )
    assert response.context["finish_review_open"] is True
    assert response.context["finish_review_token"] == review_payload["review_token"]
    assert response.context["finish_review_draft"] == [retained_row]
    assert response.context["finish_review_draft_json"] == retained_json
    assert response.context["finish_review_loaded_version"] == str(loaded_version)
    assert response.context["finish_review_preview"] is not None
    assert stored_finish_snapshot(card_id) == before


def test_finish_preview_rejects_authenticated_review_time_after_transaction_time(
    connection,
):
    card_id = release_ready_card("27032", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:37",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    loaded_version = card_version(card_id)
    future_reviewed_at = "2099-01-15 12:34:56"
    token = main.encode_finish_review_token(
        card_id,
        loaded_version,
        future_reviewed_at,
        key=main.FINISH_REVIEW_TOKEN_KEY,
    )
    submitted = db.TimingDraftRow(
        segment_id,
        "2026-01-15",
        "10:00",
        "2026-01-15",
        "14:00",
    )
    before = stored_finish_snapshot(card_id)

    response = asyncio.run(
        finish_review_preview_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review/preview"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=token,
            timing_draft=timing_draft_json(submitted),
        )
    )

    assert response.status_code == 422
    assert json.loads(response.body)["messages"] == [
        "Времето не може да бъде в бъдещето."
    ]
    assert stored_finish_snapshot(card_id) == before


def test_finish_preview_rejects_unchanged_submitted_time_after_frozen_review(
    connection,
):
    card_id = release_ready_card("27033", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 13:00:37",
        ended_at="2026-01-15 14:00:29",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    loaded_version = card_version(card_id)
    reviewed_at = "2026-01-15 12:34:56"
    token = main.encode_finish_review_token(
        card_id,
        loaded_version,
        reviewed_at,
        key=main.FINISH_REVIEW_TOKEN_KEY,
    )
    submitted = db.TimingDraftRow(
        segment_id,
        "2026-01-15",
        "15:00",
        "2026-01-15",
        "16:00",
    )
    before = stored_finish_snapshot(card_id)

    response = asyncio.run(
        finish_review_preview_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review/preview"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=token,
            timing_draft=timing_draft_json(submitted),
        )
    )

    assert response.status_code == 422
    assert json.loads(response.body)["messages"] == [
        "Времето не може да бъде в бъдещето."
    ]
    assert stored_finish_snapshot(card_id) == before


_AUDIT_INTERVALS = (
    (10 * 60, 10 * 60 + 10),
    (10 * 60 + 10, 10 * 60 + 25),
    (10 * 60 + 35, 11 * 60),
    (11 * 60 + 20, 11 * 60 + 25),
)


def audit_interval_draft(
    interval: tuple[int, int],
    *,
    segment_id: int | None,
) -> db.TimingDraftRow:
    start_minute, stop_minute = interval
    return db.TimingDraftRow(
        segment_id,
        "2026-01-15",
        f"{start_minute // 60:02d}:{start_minute % 60:02d}",
        "2026-01-15",
        f"{stop_minute // 60:02d}:{stop_minute % 60:02d}",
    )


def audit_interval_totals(
    intervals: tuple[tuple[int, int], ...],
) -> tuple[int, int]:
    ordered = sorted(intervals)
    production_seconds = sum((stop - start) * 60 for start, stop in ordered)
    paused_seconds = sum(
        (current[0] - previous[1]) * 60
        for previous, current in zip(ordered, ordered[1:])
    )
    return production_seconds, paused_seconds


def test_terminal_timing_interval_oracle_normalizes_all_bounded_valid_permutations(
    connection,
):
    """Catches input-order totals or source indices replacing chronology."""

    card_id = release_ready_card("27034-oracle-valid", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:00",
        ended_at="2026-01-15 08:10:00",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    loaded_version = card_version(card_id)
    before = stored_finish_snapshot(card_id)
    checked_ledgers = 0

    for interval_count in range(1, 5):
        canonical = _AUDIT_INTERVALS[:interval_count]
        expected_production, expected_paused = audit_interval_totals(canonical)
        for source_order in permutations(range(interval_count)):
            draft_rows = [
                audit_interval_draft(
                    canonical[canonical_index],
                    segment_id=(segment_id if source_index == 0 else None),
                )
                for source_index, canonical_index in enumerate(source_order)
            ]

            outcome = db.preview_terminal_timing_ledger(
                card_id,
                loaded_version,
                draft_rows,
                preview_at="2026-01-15 22:00:00",
            )

            assert outcome.result.ok
            assert outcome.preview is not None
            assert outcome.preview.production_seconds == expected_production
            assert outcome.preview.paused_seconds == expected_paused
            assert [
                row["source_index"] for row in outcome.preview.intervals
            ] == [source_order.index(index) for index in range(interval_count)]
            checked_ledgers += 1

    assert checked_ledgers == 33
    assert stored_finish_snapshot(card_id) == before


@pytest.mark.parametrize(
    ("case_name", "intervals", "expected_issues"),
    [
        (
            "equality",
            ((10 * 60, 10 * 60),),
            (
                db.TimingValidationIssue(
                    0,
                    "stop_time",
                    "Краят трябва да бъде след началото.",
                ),
            ),
        ),
        (
            "reversal",
            ((10 * 60 + 10, 10 * 60),),
            (
                db.TimingValidationIssue(
                    0,
                    "stop_time",
                    "Краят трябва да бъде след началото.",
                ),
            ),
        ),
        (
            "overlap",
            ((10 * 60 + 20, 10 * 60 + 40), (10 * 60, 10 * 60 + 30)),
            (
                db.TimingValidationIssue(
                    0,
                    "start_time",
                    "Времевите сегменти не могат да се застъпват.",
                ),
            ),
        ),
    ],
    ids=("equality", "reversal", "overlap"),
)
def test_terminal_timing_interval_oracle_targets_invalid_boundaries_without_mutation(
    connection,
    case_name,
    intervals,
    expected_issues,
):
    """Catches equal/reversed/overlapping ledgers reaching persistence."""

    card_id = release_ready_card(f"27035-oracle-{case_name}", 1)
    start_card(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 08:10:23",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    draft_rows = [
        audit_interval_draft(
            interval,
            segment_id=(segment_id if source_index == 0 else None),
        )
        for source_index, interval in enumerate(intervals)
    ]
    loaded_version = card_version(card_id)
    before = stored_finish_snapshot(card_id)

    preview = db.preview_terminal_timing_ledger(
        card_id,
        loaded_version,
        draft_rows,
        preview_at="2026-01-15 22:00:00",
    )
    save = db.update_terminal_timing_ledger(
        card_id,
        loaded_version,
        draft_rows,
    )

    assert not preview.result.ok
    assert preview.issues == expected_issues
    assert not save.result.ok
    assert save.issues == expected_issues
    assert stored_finish_snapshot(card_id) == before


def test_terminal_timing_save_serializes_two_committed_writers_without_mixing(
    connection,
    monkeypatch,
):
    """Catches a stale timing writer overwriting the committed winner."""

    card_id = release_ready_card("27036-save-serialized", 1)
    start_card(card_id)
    seed_timing_audit_unrelated_data(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    loaded_version = card_version(card_id)
    before = stored_finish_snapshot(card_id)
    winner_draft = [
        db.TimingDraftRow(segment_id, "2026-01-15", "10:05", "", "")
    ]
    stale_draft = [
        db.TimingDraftRow(segment_id, "2026-01-15", "10:10", "", "")
    ]

    winner, stale, contention_proved = run_serialized_timing_writers(
        monkeypatch,
        lambda: db.update_terminal_timing_ledger(
            card_id,
            loaded_version,
            winner_draft,
        ),
        lambda: db.update_terminal_timing_ledger(
            card_id,
            loaded_version,
            stale_draft,
        ),
    )

    after = stored_finish_snapshot(card_id)
    assert contention_proved
    assert sorted(outcome.result.ok for outcome in (winner, stale)) == [False, True]
    assert winner.result.ok
    assert stale.result.messages == (db.STALE_CARD_MESSAGE,)
    assert after["card"]["version"] == loaded_version + 1
    assert after["card"]["status"] == STATUS_RUNNING
    assert after["card"]["first_started_at"] == "2026-01-15 08:05:00"
    assert [
        (
            row["id"],
            row["started_at"],
            row["ended_at"],
            row["end_reason"],
        )
        for row in after["timing_rows"]
    ] == [(segment_id, "2026-01-15 08:05:00", None, None)]
    assert preserved_snapshot(
        after,
        allowed_card_changes={"first_started_at", "updated_at", "version"},
    ) == preserved_snapshot(
        before,
        allowed_card_changes={"first_started_at", "updated_at", "version"},
    )


def test_reviewed_finish_serializes_two_committed_writers_without_mixing(
    connection,
    monkeypatch,
):
    """Catches a stale reviewed Finish partially replacing winner lifecycle."""

    card_id = release_ready_card("27037-finish-serialized", 1)
    start_card(card_id)
    seed_timing_audit_unrelated_data(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    loaded_version = card_version(card_id)
    before = stored_finish_snapshot(card_id)
    active_shift = db.fetch_active_shift()
    assert active_shift is not None
    active_shift_occurrence_id = int(active_shift["id"])
    reviewed_at = "2026-01-15 12:34:56"
    winner_draft = [
        db.TimingDraftRow(
            segment_id,
            "2026-01-15",
            "10:00",
            "2026-01-15",
            "14:00",
        )
    ]
    stale_draft = [
        db.TimingDraftRow(
            segment_id,
            "2026-01-15",
            "10:00",
            "2026-01-15",
            "14:15",
        )
    ]

    winner, stale, contention_proved = run_serialized_timing_writers(
        monkeypatch,
        lambda: db.finish_card_with_timing_ledger(
            card_id,
            loaded_version,
            winner_draft,
            reviewed_at,
        ),
        lambda: db.finish_card_with_timing_ledger(
            card_id,
            loaded_version,
            stale_draft,
            reviewed_at,
        ),
    )

    after = stored_finish_snapshot(card_id)
    assert contention_proved
    assert sorted(outcome.result.ok for outcome in (winner, stale)) == [False, True]
    assert winner.result.ok
    assert stale.result.messages == (db.STALE_CARD_MESSAGE,)
    assert after["card"]["version"] == loaded_version + 1
    assert after["card"]["status"] == STATUS_COMPLETED
    assert after["card"]["machine_sequence"] == 1
    assert (
        after["card"]["final_extrusion_shift_occurrence_id"]
        == active_shift_occurrence_id
    )
    assert after["card"]["first_started_at"] == "2026-01-15 08:00:17"
    assert after["card"]["finished_at"] == "2026-01-15 12:00:00"
    assert [
        (
            row["id"],
            row["started_at"],
            row["ended_at"],
            row["end_reason"],
        )
        for row in after["timing_rows"]
    ] == [
        (
            segment_id,
            "2026-01-15 08:00:17",
            "2026-01-15 12:00:00",
            "finish",
        )
    ]
    allowed_finish_changes = {
        "final_extrusion_shift_occurrence_id",
        "finished_at",
        "first_started_at",
        "status",
        "updated_at",
        "version",
    }
    assert preserved_snapshot(
        after,
        allowed_card_changes=allowed_finish_changes,
    ) == preserved_snapshot(
        before,
        allowed_card_changes=allowed_finish_changes,
    )


def test_terminal_timing_save_applies_multirow_add_delete_as_one_structure(
    connection,
):
    """Catches partial delete/add writes or wrong IDs/reasons/totals."""

    card_id = release_ready_card("27038-save-structure", 1)
    start_card(card_id)
    seed_timing_audit_unrelated_data(card_id)
    first_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 08:30:23",
        end_reason="pause",
        status=STATUS_PAUSED,
    )
    deleted_id = insert_segment(
        card_id,
        started_at="2026-01-15 09:30:00",
        ended_at="2026-01-15 09:45:00",
        end_reason="pause",
    )
    last_id = insert_segment(
        card_id,
        started_at="2026-01-15 10:00:31",
        ended_at="2026-01-15 10:30:41",
        end_reason="pause",
    )
    loaded_version = card_version(card_id)
    before = stored_finish_snapshot(card_id)
    with db.connect() as id_connection:
        next_id = int(
            id_connection.execute(
                "SELECT seq + 1 FROM sqlite_sequence WHERE name = ?",
                ("production_time_segments",),
            ).fetchone()[0]
        )
    draft_rows = [
        db.TimingDraftRow(
            last_id,
            "2026-01-15",
            "12:00",
            "2026-01-15",
            "12:30",
        ),
        db.TimingDraftRow(
            None,
            "2026-01-15",
            "11:00",
            "2026-01-15",
            "11:20",
        ),
        db.TimingDraftRow(deleted_id, "", "", "", "", deleted=True),
        db.TimingDraftRow(
            first_id,
            "2026-01-15",
            "10:00",
            "2026-01-15",
            "10:30",
        ),
        db.TimingDraftRow(
            None,
            "2026-01-15",
            "10:35",
            "2026-01-15",
            "10:50",
        ),
    ]

    preview = db.preview_terminal_timing_ledger(
        card_id,
        loaded_version,
        draft_rows,
        preview_at="2026-01-15 22:00:00",
    )
    outcome = db.update_terminal_timing_ledger(
        card_id,
        loaded_version,
        draft_rows,
    )

    after = stored_finish_snapshot(card_id)
    assert preview.result.ok
    assert preview.preview is not None
    assert preview.preview.production_seconds == 5_716
    assert preview.preview.paused_seconds == 3_308
    assert outcome.result.ok
    assert after["card"]["version"] == loaded_version + 1
    assert after["card"]["first_started_at"] == "2026-01-15 08:00:17"
    assert after["card"]["finished_at"] is None
    detail = db.fetch_admin_card_detail(card_id)
    assert detail is not None
    assert detail["total_production_seconds"] == 5_716
    assert [
        (
            row["id"],
            row["started_at"],
            row["ended_at"],
            row["end_reason"],
        )
        for row in after["timing_rows"]
    ] == [
        (
            first_id,
            "2026-01-15 08:00:17",
            "2026-01-15 08:30:23",
            "pause",
        ),
        (
            next_id + 1,
            "2026-01-15 08:35:00",
            "2026-01-15 08:50:00",
            "correction",
        ),
        (
            next_id,
            "2026-01-15 09:00:00",
            "2026-01-15 09:20:00",
            "correction",
        ),
        (
            last_id,
            "2026-01-15 10:00:31",
            "2026-01-15 10:30:41",
            "pause",
        ),
    ]
    assert deleted_id not in {row["id"] for row in after["timing_rows"]}
    assert preserved_snapshot(
        after,
        allowed_card_changes={"first_started_at", "updated_at", "version"},
    ) == preserved_snapshot(
        before,
        allowed_card_changes={"first_started_at", "updated_at", "version"},
    )


def test_reviewed_finish_applies_multirow_add_delete_and_lifecycle_once(
    connection,
):
    """Catches structural timing edits committing separately from Finish."""

    card_id = release_ready_card("27039-finish-structure", 1)
    start_card(card_id)
    open_id = set_single_segment(
        card_id,
        started_at="2026-01-15 10:00:41",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    first_id = insert_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at="2026-01-15 08:30:23",
        end_reason="pause",
    )
    deleted_id = insert_segment(
        card_id,
        started_at="2026-01-15 09:30:00",
        ended_at="2026-01-15 09:45:00",
        end_reason="pause",
    )
    seed_timing_audit_unrelated_data(card_id)
    loaded_version = card_version(card_id)
    before = stored_finish_snapshot(card_id)
    active_shift = db.fetch_active_shift()
    assert active_shift is not None
    active_shift_occurrence_id = int(active_shift["id"])
    with db.connect() as id_connection:
        next_id = int(
            id_connection.execute(
                "SELECT seq + 1 FROM sqlite_sequence WHERE name = ?",
                ("production_time_segments",),
            ).fetchone()[0]
        )
    draft_rows = [
        db.TimingDraftRow(
            open_id,
            "2026-01-15",
            "12:00",
            "2026-01-15",
            "14:00",
        ),
        db.TimingDraftRow(deleted_id, "", "", "", "", deleted=True),
        db.TimingDraftRow(
            None,
            "2026-01-15",
            "11:00",
            "2026-01-15",
            "11:20",
        ),
        db.TimingDraftRow(
            first_id,
            "2026-01-15",
            "10:00",
            "2026-01-15",
            "10:30",
        ),
    ]

    outcome = db.finish_card_with_timing_ledger(
        card_id,
        loaded_version,
        draft_rows,
        "2026-01-15 12:34:56",
    )

    after = stored_finish_snapshot(card_id)
    assert outcome.result.ok
    assert outcome.preview is not None
    assert outcome.preview.production_seconds == 10_165
    assert outcome.preview.paused_seconds == 4_218
    assert after["card"]["version"] == loaded_version + 1
    assert after["card"]["status"] == STATUS_COMPLETED
    assert (
        after["card"]["final_extrusion_shift_occurrence_id"]
        == active_shift_occurrence_id
    )
    assert after["card"]["first_started_at"] == "2026-01-15 08:00:17"
    assert after["card"]["finished_at"] == "2026-01-15 12:00:00"
    detail = db.fetch_admin_card_detail(card_id)
    assert detail is not None
    assert detail["total_production_seconds"] == 10_165
    assert [
        (
            row["id"],
            row["started_at"],
            row["ended_at"],
            row["end_reason"],
        )
        for row in after["timing_rows"]
    ] == [
        (
            first_id,
            "2026-01-15 08:00:17",
            "2026-01-15 08:30:23",
            "pause",
        ),
        (
            next_id,
            "2026-01-15 09:00:00",
            "2026-01-15 09:20:00",
            "correction",
        ),
        (
            open_id,
            "2026-01-15 10:00:41",
            "2026-01-15 12:00:00",
            "finish",
        ),
    ]
    assert deleted_id not in {row["id"] for row in after["timing_rows"]}
    allowed_finish_changes = {
        "final_extrusion_shift_occurrence_id",
        "finished_at",
        "first_started_at",
        "status",
        "updated_at",
        "version",
    }
    assert preserved_snapshot(
        after,
        allowed_card_changes=allowed_finish_changes,
    ) == preserved_snapshot(
        before,
        allowed_card_changes=allowed_finish_changes,
    )


@pytest.mark.parametrize("token_kind", ("missing", "tampered", "restart"))
def test_actual_finish_endpoint_rejects_invalid_review_tokens_without_any_write(
    connection,
    monkeypatch,
    token_kind,
):
    """Catches Finish submission bypassing authenticated review boundaries."""

    monkeypatch.setattr(main, "FINISH_REVIEW_TOKEN_KEY", b"a" * 32)
    monkeypatch.setattr(
        db,
        "current_database_timestamp",
        lambda connection: "2026-01-15 12:34:56",
    )
    card_id = release_ready_card(f"27040-token-{token_kind}", 1)
    start_card(card_id)
    seed_timing_audit_unrelated_data(card_id)
    set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    loaded_version = card_version(card_id)
    review_response = asyncio.run(
        finish_review_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)
    submitted_json = json.dumps(review_payload["preview"]["draft"])
    submitted_token = review_payload["review_token"]
    if token_kind == "missing":
        submitted_token = ""
    elif token_kind == "tampered":
        payload_part, signature_part = submitted_token.split(".")
        replacement = "A" if signature_part[0] != "A" else "B"
        submitted_token = (
            f"{payload_part}.{replacement}{signature_part[1:]}"
        )
    else:
        monkeypatch.setattr(main, "FINISH_REVIEW_TOKEN_KEY", b"b" * 32)
    before = stored_finish_snapshot(card_id)

    response = asyncio.run(
        main.finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=submitted_token,
            timing_draft=submitted_json,
        )
    )

    after = stored_finish_snapshot(card_id)
    assert response.status_code == 200
    assert response.context["workflow_result"].messages == (
        main.INVALID_FINISH_REVIEW_MESSAGE,
    )
    assert response.context["finish_review_open"] is True
    assert after == before


def test_tokenless_finish_cannot_use_pending_preread_to_finish_newly_running_card(
    connection,
    monkeypatch,
):
    """Catches route dispatch authorizing active Finish from an unlocked pre-read."""

    card_id = release_ready_card("27040-tokenless-dispatch-race", 1)
    with db.connect() as setup_connection:
        setup_connection.execute(
            "UPDATE cards SET rewinding_roll_count = 1 WHERE id = ?",
            (card_id,),
        )
    pending_version = card_version(card_id)
    submitted_version = pending_version + 1
    real_fetch = main.fetch_terminal_card_detail
    started_snapshot: dict[str, object] = {}
    pre_read_count = 0

    def pending_preread_then_start(selected_card_id):
        nonlocal pre_read_count
        card = real_fetch(selected_card_id)
        pre_read_count += 1
        if pre_read_count == 1:
            assert card is not None
            assert card["status"] == STATUS_PENDING
            start_card(card_id)
            started_snapshot.update(stored_finish_snapshot(card_id))
        return card

    monkeypatch.setattr(
        main,
        "fetch_terminal_card_detail",
        pending_preread_then_start,
    )

    response = asyncio.run(
        main.finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            loaded_version=str(submitted_version),
        )
    )

    after = stored_finish_snapshot(card_id)
    assert pre_read_count >= 1
    assert response.status_code == 200
    assert response.context["workflow_result"].messages == (db.STALE_CARD_MESSAGE,)
    assert response.context["finish_review_open"] is False
    assert after == started_snapshot
    assert after["card"]["status"] == STATUS_RUNNING
    assert after["card"]["version"] == submitted_version
    assert after["card"]["finished_at"] is None
    assert after["card"]["final_extrusion_shift_occurrence_id"] is None
    assert len(after["timing_rows"]) == 1
    assert after["timing_rows"][0]["ended_at"] is None
    assert after["timing_rows"][0]["end_reason"] is None


def test_tokenless_finish_route_still_finalizes_awaiting_rewinding_card(connection):
    """Catches route-safe waiting finalization being lost while closing the race."""

    card_id = release_ready_card("27040-tokenless-waiting", 1)
    start_card(card_id)
    assert db.update_rewinding_roll_count(card_id, card_version(card_id), 1).ok
    assert db.finish_card(
        card_id,
        card_version(card_id),
        require_active_shift=True,
    ).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "25.00").ok
    waiting = stored_finish_snapshot(card_id)
    assert waiting["card"]["status"] == STATUS_AWAITING_REWINDING

    response = asyncio.run(
        main.finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            loaded_version=str(waiting["card"]["version"]),
        )
    )

    after = stored_finish_snapshot(card_id)
    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/terminal/cards/{card_id}?notice=card_finished"
    )
    assert after["card"]["status"] == STATUS_COMPLETED
    assert after["card"]["version"] == waiting["card"]["version"] + 1
    assert after["card"]["finished_at"] == waiting["card"]["finished_at"]
    assert after["card"]["final_extrusion_shift_occurrence_id"] == (
        waiting["card"]["final_extrusion_shift_occurrence_id"]
    )
    assert after["timing_rows"] == waiting["timing_rows"]


def test_actual_finish_endpoint_rejects_replayed_authenticated_review_token(
    connection,
    monkeypatch,
):
    """Catches an authenticated Finish review being accepted twice."""

    monkeypatch.setattr(main, "FINISH_REVIEW_TOKEN_KEY", b"a" * 32)
    monkeypatch.setattr(
        db,
        "current_database_timestamp",
        lambda connection: "2026-01-15 12:34:56",
    )
    card_id = release_ready_card("27041-token-replay", 1)
    start_card(card_id)
    seed_timing_audit_unrelated_data(card_id)
    segment_id = set_single_segment(
        card_id,
        started_at="2026-01-15 08:00:17",
        ended_at=None,
        end_reason=None,
        status=STATUS_RUNNING,
    )
    loaded_version = card_version(card_id)
    review_response = asyncio.run(
        finish_review_endpoint()(
            make_test_request(f"/terminal/cards/{card_id}/finish-review"),
            card_id,
            loaded_version=str(loaded_version),
        )
    )
    review_payload = json.loads(review_response.body)
    submitted_json = json.dumps(review_payload["preview"]["draft"])
    before = stored_finish_snapshot(card_id)

    first_response = asyncio.run(
        main.finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=submitted_json,
        )
    )
    after_first = stored_finish_snapshot(card_id)
    replay_response = asyncio.run(
        main.finish_terminal_card(
            make_test_request(f"/terminal/cards/{card_id}/finish"),
            card_id,
            loaded_version=str(loaded_version),
            review_token=review_payload["review_token"],
            timing_draft=submitted_json,
        )
    )
    after_replay = stored_finish_snapshot(card_id)

    assert first_response.status_code == 303
    assert after_first["card"]["status"] == STATUS_COMPLETED
    assert after_first["card"]["version"] == loaded_version + 1
    assert after_first["card"]["finished_at"] == "2026-01-15 12:34:56"
    assert [
        (
            row["id"],
            row["started_at"],
            row["ended_at"],
            row["end_reason"],
        )
        for row in after_first["timing_rows"]
    ] == [
        (
            segment_id,
            "2026-01-15 08:00:17",
            "2026-01-15 12:34:56",
            "finish",
        )
    ]
    assert after_first != before
    assert replay_response.context["workflow_result"].messages == (
        db.STALE_CARD_MESSAGE,
    )
    assert replay_response.context["finish_review_open"] is True
    assert replay_response.context["finish_review_stale"] is True
    assert after_replay == after_first
