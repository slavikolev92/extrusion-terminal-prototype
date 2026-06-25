from __future__ import annotations

import csv
import io

from app import db
from app.constants import STATUS_PAUSED, STATUS_PENDING, STATUS_RUNNING
from app.importer import IMPORT_FIELDS, import_cards_from_csv


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
        "customer": "Timing Customer",
        "product_type": "PE film",
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "da",
        "raw_material_a": "LDPE A | 100%",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def import_and_release_card(
    order_number: str,
    machine_id: int = 1,
    machine_sequence: int = 1,
) -> int:
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
    assert db.release_card(
        card_id,
        machine_id,
        machine_sequence,
        max_roll_weight="60.0",
    ).ok
    return card_id


def test_start_creates_open_timing_segment_and_running_status(connection):
    card_id = import_and_release_card("25400", machine_id=1, machine_sequence=1)
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.start_production_timing(card_id, loaded_version)

    card = connection.execute(
        "SELECT status, first_started_at, version FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()
    segments = connection.execute(
        """
        SELECT started_at, ended_at, end_reason
        FROM production_time_segments
        WHERE card_id = ?
        """,
        (card_id,),
    ).fetchall()

    assert result.ok
    assert card["status"] == STATUS_RUNNING
    assert card["first_started_at"] is not None
    assert card["version"] == loaded_version + 1
    assert len(segments) == 1
    assert segments[0]["started_at"] is not None
    assert segments[0]["ended_at"] is None
    assert segments[0]["end_reason"] is None


def test_pause_closes_open_segment_and_sets_paused_status(connection):
    card_id = import_and_release_card("25401", machine_id=2, machine_sequence=1)
    assert db.start_production_timing(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
    ).ok
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.pause_production_timing(card_id, loaded_version)

    card = connection.execute(
        "SELECT status, version FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()
    segment = connection.execute(
        """
        SELECT ended_at, end_reason
        FROM production_time_segments
        WHERE card_id = ?
        """,
        (card_id,),
    ).fetchone()

    assert result.ok
    assert card["status"] == STATUS_PAUSED
    assert card["version"] == loaded_version + 1
    assert segment["ended_at"] is not None
    assert segment["end_reason"] == "pause"


def test_resume_creates_new_open_segment(connection):
    card_id = import_and_release_card("25402", machine_id=3, machine_sequence=1)
    assert db.start_production_timing(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
    ).ok
    assert db.pause_production_timing(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
    ).ok
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.resume_production_timing(card_id, loaded_version)

    card = connection.execute(
        "SELECT status, version FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()
    segments = connection.execute(
        """
        SELECT ended_at, end_reason
        FROM production_time_segments
        WHERE card_id = ?
        ORDER BY id
        """,
        (card_id,),
    ).fetchall()

    assert result.ok
    assert card["status"] == STATUS_RUNNING
    assert card["version"] == loaded_version + 1
    assert len(segments) == 2
    assert segments[0]["ended_at"] is not None
    assert segments[0]["end_reason"] == "pause"
    assert segments[1]["ended_at"] is None
    assert segments[1]["end_reason"] is None


def test_timing_actions_block_stale_loaded_versions(connection):
    card_id = import_and_release_card("25403", machine_id=4, machine_sequence=1)
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]
    assert db.start_production_timing(card_id, loaded_version).ok

    stale_result = db.pause_production_timing(card_id, loaded_version)

    card = connection.execute(
        "SELECT status FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()

    assert not stale_result.ok
    assert stale_result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert card["status"] == STATUS_RUNNING


def open_segment_count(connection, card_id: int) -> int:
    return int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM production_time_segments
            WHERE card_id = ?
              AND ended_at IS NULL
            """,
            (card_id,),
        ).fetchone()[0]
    )


def test_start_blocks_when_machine_has_running_card(connection):
    running_card_id = import_and_release_card("25404", machine_id=1, machine_sequence=1)
    blocked_card_id = import_and_release_card("25405", machine_id=1, machine_sequence=2)
    assert db.start_production_timing(
        running_card_id,
        db.fetch_terminal_card_detail(running_card_id)["version"],
    ).ok

    blocked_result = db.start_production_timing(
        blocked_card_id,
        db.fetch_terminal_card_detail(blocked_card_id)["version"],
    )

    blocked_card = connection.execute(
        "SELECT status FROM cards WHERE id = ?",
        (blocked_card_id,),
    ).fetchone()

    assert not blocked_result.ok
    assert blocked_result.messages == ("Машина 1 е заета от поръчка 25404.",)
    assert blocked_card["status"] == STATUS_PENDING
    assert open_segment_count(connection, blocked_card_id) == 0


def test_start_allows_another_card_when_existing_card_is_paused(connection):
    paused_card_id = import_and_release_card("25406", machine_id=1, machine_sequence=1)
    next_card_id = import_and_release_card("25407", machine_id=1, machine_sequence=2)
    assert db.start_production_timing(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
    ).ok
    assert db.pause_production_timing(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
    ).ok

    start_result = db.start_production_timing(
        next_card_id,
        db.fetch_terminal_card_detail(next_card_id)["version"],
    )

    paused_card = connection.execute(
        "SELECT status FROM cards WHERE id = ?",
        (paused_card_id,),
    ).fetchone()
    next_card = connection.execute(
        "SELECT status FROM cards WHERE id = ?",
        (next_card_id,),
    ).fetchone()

    assert start_result.ok
    assert paused_card["status"] == STATUS_PAUSED
    assert next_card["status"] == STATUS_RUNNING
    assert open_segment_count(connection, paused_card_id) == 0
    assert open_segment_count(connection, next_card_id) == 1


def test_resume_paused_card_blocks_when_another_card_is_running_on_machine(connection):
    paused_card_id = import_and_release_card("25408", machine_id=1, machine_sequence=1)
    running_card_id = import_and_release_card("25409", machine_id=1, machine_sequence=2)
    assert db.start_production_timing(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
    ).ok
    assert db.pause_production_timing(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
    ).ok
    assert db.start_production_timing(
        running_card_id,
        db.fetch_terminal_card_detail(running_card_id)["version"],
    ).ok

    resume_result = db.resume_production_timing(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
    )

    paused_card = connection.execute(
        "SELECT status FROM cards WHERE id = ?",
        (paused_card_id,),
    ).fetchone()
    running_card = connection.execute(
        "SELECT status FROM cards WHERE id = ?",
        (running_card_id,),
    ).fetchone()

    assert not resume_result.ok
    assert resume_result.messages == ("Машина 1 е заета от поръчка 25409.",)
    assert paused_card["status"] == STATUS_PAUSED
    assert running_card["status"] == STATUS_RUNNING
    assert open_segment_count(connection, paused_card_id) == 0
    assert open_segment_count(connection, running_card_id) == 1


def test_total_production_seconds_sums_segments_without_pauses(connection):
    card_id = import_and_release_card("25406", machine_id=2, machine_sequence=1)
    connection.execute(
        """
        INSERT INTO production_time_segments (card_id, started_at, ended_at, end_reason)
        VALUES
            (?, '2026-06-12 08:00:00', '2026-06-12 09:00:00', 'pause'),
            (?, '2026-06-12 09:30:00', '2026-06-12 10:00:00', 'pause')
        """,
        (card_id, card_id),
    )
    connection.commit()

    assert db.fetch_total_production_seconds(card_id) == 5400
    assert db.fetch_terminal_card_detail(card_id)["total_production_seconds"] == 5400
