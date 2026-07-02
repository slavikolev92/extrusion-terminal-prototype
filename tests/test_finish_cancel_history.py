from __future__ import annotations

import csv
import io

from app import db
from app.constants import (
    STATUS_ARCHIVED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_PENDING,
    STATUS_RUNNING,
)
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
        "customer": "Finish Customer",
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


def start_card(card_id: int) -> None:
    assert db.start_production_timing(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
    ).ok


def add_tare(card_id: int, tare_weight: str = "1.00") -> None:
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        tare_weight,
    ).ok


def add_roll(card_id: int, gross_weight: str = "25.00") -> None:
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        gross_weight,
    ).ok


def prepare_running_finishable_card(order_number: str, **release_kwargs: int) -> int:
    card_id = import_and_release_card(order_number, **release_kwargs)
    start_card(card_id)
    add_tare(card_id)
    add_roll(card_id)
    return card_id


def test_finish_blocks_roll_added_without_row_tare(connection):
    card_id = import_and_release_card("25600")
    start_card(card_id)
    add_tare(card_id)
    add_roll(card_id)
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE roll_entries
            SET tare_weight = NULL,
                net_weight = NULL
            WHERE card_id = ?
            """,
            (card_id,),
        )

    result = db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"])

    card = db.fetch_terminal_card_detail(card_id)
    assert not result.ok
    assert result.messages == ("Всяка ролка с бруто тегло трябва да има шпула преди приключване.",)
    assert card["status"] == STATUS_RUNNING


def test_finish_blocks_without_timing_started(connection):
    card_id = import_and_release_card("25601")
    add_tare(card_id)
    connection.execute(
        """
        INSERT INTO roll_entries (card_id, order_number, roll_number, gross_weight, net_weight)
        VALUES (?, '25601', 1, 25.00, 24.00)
        """,
        (card_id,),
    )
    connection.commit()

    result = db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"])

    assert not result.ok
    assert result.messages == ("Времето трябва да бъде стартирано преди приключване.",)
    assert db.fetch_terminal_card_detail(card_id)["status"] == STATUS_PENDING


def test_finish_blocks_without_gross_roll(connection):
    card_id = import_and_release_card("25602")
    start_card(card_id)
    add_tare(card_id)

    result = db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"])

    assert not result.ok
    assert result.messages == ("Поне едно бруто тегло на ролка е задължително преди приключване.",)
    assert db.fetch_terminal_card_detail(card_id)["status"] == STATUS_RUNNING


def test_finish_blocks_empty_roll_gaps(connection):
    card_id = prepare_running_finishable_card("25603")
    add_roll(card_id, "30.00")
    card = db.fetch_terminal_card_detail(card_id)
    first_roll_id = card["roll_entries"][0]["id"]
    assert db.update_roll_gross_weight(
        card_id,
        first_roll_id,
        card["version"],
        "",
    ).ok

    result = db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"])

    assert not result.ok
    assert result.messages == ("Празните редове между ролките трябва да бъдат коригирани преди приключване.",)
    assert db.fetch_terminal_card_detail(card_id)["status"] == STATUS_RUNNING


def test_finish_blocks_gross_roll_without_roll_tare(connection):
    card_id = import_and_release_card("25640")
    start_card(card_id)
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO roll_entries (card_id, order_number, roll_number, gross_weight, tare_weight, net_weight)
            VALUES (?, '25640', 1, 25.00, NULL, NULL)
            """,
            (card_id,),
        )

    result = db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"])

    assert not result.ok
    assert result.messages == ("Всяка ролка с бруто тегло трябва да има шпула преди приключване.",)


def test_finish_blocks_gross_roll_with_stale_net(connection):
    card_id = import_and_release_card("25642")
    start_card(card_id)
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO roll_entries (card_id, order_number, roll_number, gross_weight, tare_weight, net_weight)
            VALUES (?, '25642', 1, 25.00, 1.00, 99.00)
            """,
            (card_id,),
        )

    result = db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"])

    assert not result.ok
    assert result.messages == ("Всяка ролка с бруто тегло трябва да има шпула преди приключване.",)


def test_finish_blocks_gross_roll_with_invalid_stored_weight(connection):
    card_id = import_and_release_card("25643")
    start_card(card_id)
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO roll_entries (card_id, order_number, roll_number, gross_weight, tare_weight, net_weight)
            VALUES (?, '25643', 1, 'bad', 1.00, 24.00)
            """,
            (card_id,),
        )

    result = db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"])

    assert not result.ok
    assert result.messages == ("Всяка ролка с бруто тегло трябва да има шпула преди приключване.",)


def test_roll_entry_blocks_roll_added_before_default_tare_was_set(connection):
    card_id = import_and_release_card("25641")
    start_card(card_id)

    result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
    )

    assert not result.ok
    assert result.messages == ("Въведете шпула преди да добавите ролка.",)
    assert db.fetch_terminal_card_detail(card_id)["roll_entries"] == []


def test_finish_from_running_closes_active_segment_and_archives_card(connection):
    card_id = prepare_running_finishable_card("25604")
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.finish_card(card_id, loaded_version)

    card = db.fetch_terminal_card_detail(card_id)
    segment = connection.execute(
        """
        SELECT ended_at, end_reason
        FROM production_time_segments
        WHERE card_id = ?
        """,
        (card_id,),
    ).fetchone()
    active_ids = {card["id"] for card in db.fetch_cards_by_status(("pending", "running", "paused"))}
    archive_ids = {card["id"] for card in db.fetch_cards_by_status(("completed", "cancelled"))}

    assert result.ok
    assert card["status"] == STATUS_COMPLETED
    assert card["finished_at"] is not None
    assert card["version"] == loaded_version + 1
    assert segment["ended_at"] is not None
    assert segment["end_reason"] == "finish"
    assert card_id not in active_ids
    assert card_id in archive_ids


def test_finish_normalizes_active_machine_queue_after_removed_card(connection):
    first_id = prepare_running_finishable_card("25650", machine_id=1, machine_sequence=1)
    second_id = import_and_release_card("25651", machine_id=1, machine_sequence=2)
    third_id = import_and_release_card("25652", machine_id=1, machine_sequence=3)

    result = db.finish_card(first_id, db.fetch_terminal_card_detail(first_id)["version"])
    active_rows = connection.execute(
        """
        SELECT id, machine_sequence
        FROM cards
        WHERE machine_id = 1 AND status IN ('pending', 'running', 'paused')
        ORDER BY machine_sequence
        """
    ).fetchall()

    assert result.ok
    assert [(row["id"], row["machine_sequence"]) for row in active_rows] == [
        (second_id, 1),
        (third_id, 2),
    ]


def test_finish_from_paused_succeeds_without_open_segment(connection):
    card_id = prepare_running_finishable_card("25605")
    assert db.pause_production_timing(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
    ).ok
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.finish_card(card_id, loaded_version)

    open_segments = connection.execute(
        """
        SELECT COUNT(*)
        FROM production_time_segments
        WHERE card_id = ?
          AND ended_at IS NULL
        """,
        (card_id,),
    ).fetchone()[0]
    card = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert card["status"] == STATUS_COMPLETED
    assert card["finished_at"] is not None
    assert open_segments == 0


def test_admin_can_mark_completed_card_as_archived(connection):
    card_id = prepare_running_finishable_card("25630")
    assert db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]

    result = db.archive_completed_card(card_id, loaded_version)

    card = db.fetch_admin_card_detail(card_id)
    assert result.ok
    assert result.messages == ("Поръчка 25630 е маркирана като завършена.",)
    assert card["status"] == STATUS_ARCHIVED
    assert card["version"] == loaded_version + 1


def test_archive_action_blocks_non_completed_cards(connection):
    card_id = import_and_release_card("25631", machine_id=1, machine_sequence=1)
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]

    result = db.archive_completed_card(card_id, loaded_version)

    assert not result.ok
    assert result.messages == ("Само произведени карти могат да се маркират като завършени.",)
    assert db.fetch_admin_card_detail(card_id)["status"] == STATUS_PENDING


def test_archive_action_blocks_stale_version(connection):
    card_id = prepare_running_finishable_card("25632")
    assert db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]
    assert db.update_tare_weight(card_id, loaded_version, "1.10").ok

    result = db.archive_completed_card(card_id, loaded_version)

    assert not result.ok
    assert result.messages == (db.STALE_CARD_MESSAGE,)
    assert db.fetch_admin_card_detail(card_id)["status"] == STATUS_COMPLETED


def test_completed_card_roll_weights_remain_editable(connection):
    card_id = prepare_running_finishable_card("25614")
    assert db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok

    add_result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "30.00",
    )
    card = db.fetch_terminal_card_detail(card_id)
    first_roll_id = card["roll_entries"][0]["id"]
    update_result = db.update_roll_gross_weight(
        card_id,
        first_roll_id,
        card["version"],
        "26.00",
    )
    updated_card = db.fetch_terminal_card_detail(card_id)

    assert add_result.ok
    assert update_result.ok
    assert updated_card["status"] == STATUS_COMPLETED
    assert updated_card["roll_count"] == 2
    assert updated_card["total_gross_weight"] == "56.00"
    assert updated_card["total_net_weight"] == "54.00"


def test_cancel_pending_card_moves_it_out_of_workstation_visibility(connection):
    card_id = import_and_release_card("25606")
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.cancel_card(card_id, loaded_version)

    card = db.fetch_admin_card_detail(card_id)
    active_ids = {card["id"] for card in db.fetch_cards_by_status(("pending", "running", "paused"))}
    archive_ids = {card["id"] for card in db.fetch_cards_by_status(("completed", "cancelled"))}

    assert result.ok
    assert card["status"] == STATUS_CANCELLED
    assert card["cancelled_at"] is not None
    assert card["version"] == loaded_version + 1
    assert card_id not in active_ids
    assert card_id in archive_ids
    assert db.fetch_terminal_card_detail(card_id) is None


def test_cancel_normalizes_active_machine_queue_after_removed_card(connection):
    first_id = import_and_release_card("25653", machine_id=2, machine_sequence=1)
    second_id = import_and_release_card("25654", machine_id=2, machine_sequence=2)
    third_id = import_and_release_card("25655", machine_id=2, machine_sequence=3)

    result = db.cancel_card(second_id, db.fetch_terminal_card_detail(second_id)["version"])
    active_rows = connection.execute(
        """
        SELECT id, machine_sequence
        FROM cards
        WHERE machine_id = 2 AND status IN ('pending', 'running', 'paused')
        ORDER BY machine_sequence
        """
    ).fetchall()

    assert result.ok
    assert [(row["id"], row["machine_sequence"]) for row in active_rows] == [
        (first_id, 1),
        (third_id, 2),
    ]


def test_cancel_running_card_closes_open_segment(connection):
    card_id = import_and_release_card("25607")
    start_card(card_id)
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.cancel_card(card_id, loaded_version)

    card = db.fetch_admin_card_detail(card_id)
    segment = connection.execute(
        """
        SELECT ended_at, end_reason
        FROM production_time_segments
        WHERE card_id = ?
        """,
        (card_id,),
    ).fetchone()

    assert result.ok
    assert card["status"] == STATUS_CANCELLED
    assert segment["ended_at"] is not None
    assert segment["end_reason"] == "correction"


def test_restore_cancelled_card_returns_to_pending(connection):
    card_id = import_and_release_card("25608")
    assert db.cancel_card(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]

    result = db.restore_cancelled_card(card_id, loaded_version)

    card = db.fetch_terminal_card_detail(card_id)
    active_ids = {card["id"] for card in db.fetch_cards_by_status(("pending", "running", "paused"))}

    assert result.ok
    assert card["status"] == STATUS_PENDING
    assert card["cancelled_at"] is None
    assert card["version"] == loaded_version + 1
    assert card_id in active_ids


def test_restore_inserts_at_original_sequence_and_shifts_active_queue(connection):
    cancelled_card_id = import_and_release_card("25609", machine_id=2, machine_sequence=1)
    assert db.cancel_card(
        cancelled_card_id,
        db.fetch_terminal_card_detail(cancelled_card_id)["version"],
    ).ok
    other_card_id = import_and_release_card("25610", machine_id=2, machine_sequence=1)

    result = db.restore_cancelled_card(
        cancelled_card_id,
        db.fetch_admin_card_detail(cancelled_card_id)["version"],
    )
    active_rows = connection.execute(
        """
        SELECT id, machine_sequence
        FROM cards
        WHERE machine_id = 2 AND status IN ('pending', 'running', 'paused')
        ORDER BY machine_sequence
        """
    ).fetchall()

    assert result.ok
    assert [(row["id"], row["machine_sequence"]) for row in active_rows] == [
        (cancelled_card_id, 1),
        (other_card_id, 2),
    ]
    assert db.fetch_terminal_card_detail(cancelled_card_id)["status"] == STATUS_PENDING


def test_stale_finish_cancel_and_restore_edits_are_blocked(connection):
    finish_card_id = prepare_running_finishable_card("25611", machine_id=3, machine_sequence=1)
    finish_version = db.fetch_terminal_card_detail(finish_card_id)["version"]
    add_roll(finish_card_id, "26.00")
    stale_finish = db.finish_card(finish_card_id, finish_version)

    cancel_card_id = import_and_release_card("25612", machine_id=3, machine_sequence=2)
    cancel_version = db.fetch_terminal_card_detail(cancel_card_id)["version"]
    add_tare(cancel_card_id)
    stale_cancel = db.cancel_card(cancel_card_id, cancel_version)

    restore_card_id = import_and_release_card("25613", machine_id=3, machine_sequence=3)
    restore_version = db.fetch_terminal_card_detail(restore_card_id)["version"]
    assert db.cancel_card(restore_card_id, restore_version).ok
    stale_restore = db.restore_cancelled_card(restore_card_id, restore_version)

    assert not stale_finish.ok
    assert stale_finish.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert not stale_cancel.ok
    assert stale_cancel.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert not stale_restore.ok
    assert stale_restore.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
