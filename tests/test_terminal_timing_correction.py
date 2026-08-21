from __future__ import annotations

import asyncio
import csv
import io
import json

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
