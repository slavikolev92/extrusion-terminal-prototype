from __future__ import annotations

import csv
import io

from app import db
from app.constants import (
    STATUS_IMPORTED,
    STATUS_PENDING,
    VALIDATION_NO_EXTRUSION_STEP,
    VALIDATION_READY,
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
        "customer": "Test Customer",
        "product_type": "PE film",
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "da",
        "raw_material_a": "LDPE A",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def import_one_ready_card(order_number: str = "25278") -> int:
    result = import_cards_from_csv(
        "ready.csv",
        csv_bytes(extrusion_row(order_number)),
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


def test_database_initialization_seeds_machines_1_through_4(temp_db_path):
    assert temp_db_path.exists()

    machines = db.fetch_machines()

    assert [machine["id"] for machine in machines] == [1, 2, 3, 4]
    assert [machine["display_order"] for machine in machines] == [1, 2, 3, 4]


def test_csv_import_creates_imported_ready_cards(connection):
    result = import_cards_from_csv(
        "orders.csv",
        csv_bytes(extrusion_row("25278")),
        overwrite_existing=False,
    )

    card = connection.execute(
        "SELECT order_number, status, validation_status, customer FROM cards"
    ).fetchone()

    assert result.rows_seen == 1
    assert result.rows_imported == 1
    assert result.created == 1
    assert len(result.row_results) == 1
    assert result.row_results[0].row_number == 2
    assert result.row_results[0].order_number == "25278"
    assert result.row_results[0].action == "created"
    assert result.row_results[0].validation_status == VALIDATION_READY
    assert card["order_number"] == "25278"
    assert card["status"] == STATUS_IMPORTED
    assert card["validation_status"] == VALIDATION_READY
    assert card["customer"] == "Test Customer"


def test_csv_import_skips_rows_without_extrusion_step(connection):
    result = import_cards_from_csv(
        "no-extrusion.csv",
        csv_bytes(
            extrusion_row(
                "25279",
                extrusion_flag="",
                raw_material_a="",
                packaging_method="",
            )
        ),
        overwrite_existing=False,
    )

    card = connection.execute(
        "SELECT order_number, status, validation_status FROM cards WHERE order_number = '25279'"
    ).fetchone()

    assert result.rows_imported == 0
    assert result.skipped == 1
    assert result.row_results[0].action == "skipped"
    assert result.row_results[0].validation_status == VALIDATION_NO_EXTRUSION_STEP
    assert "no extrusion step" in result.row_results[0].message
    assert card is None


def test_duplicate_import_is_skipped_by_default(connection):
    first = import_cards_from_csv(
        "first.csv",
        csv_bytes(extrusion_row("25280", customer="Original Customer")),
        overwrite_existing=False,
    )
    duplicate = import_cards_from_csv(
        "duplicate.csv",
        csv_bytes(extrusion_row("25280", customer="Changed Customer")),
        overwrite_existing=False,
    )

    card = connection.execute(
        "SELECT customer FROM cards WHERE order_number = '25280'"
    ).fetchone()

    assert first.created == 1
    assert duplicate.rows_seen == 1
    assert duplicate.rows_imported == 0
    assert duplicate.skipped == 1
    assert duplicate.duplicate_rows == ["25280"]
    assert duplicate.row_results[0].row_number == 2
    assert duplicate.row_results[0].order_number == "25280"
    assert duplicate.row_results[0].action == "skipped"
    assert "overwrite" in duplicate.row_results[0].message
    assert card["customer"] == "Original Customer"


def test_duplicate_row_inside_same_csv_is_reported_and_skipped(connection):
    result = import_cards_from_csv(
        "duplicate-in-file.csv",
        csv_bytes(
            extrusion_row("25288", customer="First Customer"),
            extrusion_row("25288", customer="Second Customer"),
        ),
        overwrite_existing=False,
    )

    card = connection.execute(
        "SELECT customer FROM cards WHERE order_number = '25288'"
    ).fetchone()

    assert result.rows_seen == 2
    assert result.rows_imported == 1
    assert result.created == 1
    assert result.skipped == 1
    assert result.duplicate_rows == ["25288"]
    assert [row.action for row in result.row_results] == ["created", "skipped"]
    assert result.row_results[1].row_number == 3
    assert result.row_results[1].validation_status == VALIDATION_READY
    assert "inside this CSV" in result.row_results[1].message
    assert card["customer"] == "First Customer"


def test_missing_order_number_row_is_reported_and_skipped(connection):
    result = import_cards_from_csv(
        "missing-order.csv",
        csv_bytes(extrusion_row("")),
        overwrite_existing=False,
    )

    card_count = connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0]

    assert result.rows_seen == 1
    assert result.rows_imported == 0
    assert result.skipped == 1
    assert result.row_results[0].row_number == 2
    assert result.row_results[0].order_number == ""
    assert result.row_results[0].action == "skipped"
    assert result.row_results[0].message == "Missing order_number."
    assert card_count == 0


def test_missing_required_columns_are_reported_as_file_level_blocker(connection):
    result = import_cards_from_csv(
        "missing-columns.csv",
        b"order_number,customer\n25289,Customer\n",
        overwrite_existing=False,
    )

    card_count = connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0]

    assert result.rows_seen == 0
    assert result.rows_imported == 0
    assert result.row_results[0].row_number is None
    assert result.row_results[0].action == "blocked"
    assert "Missing required CSV columns" in result.row_results[0].message
    assert card_count == 0


def test_overwrite_import_updates_imported_fields_and_preserves_production_data(connection):
    card_id = import_one_ready_card("25281")
    db.release_card(card_id, machine_id=2, machine_sequence=7)

    connection.execute(
        """
        UPDATE cards
        SET tare_weight = 1.25,
            actual_raw_material_used = 'Actual LDPE',
            raw_material_brand_grade = 'Grade A',
            raw_material_batch_lot = 'Batch 42',
            first_started_at = '2026-06-12T08:00:00',
            version = version + 1
        WHERE id = ?
        """,
        (card_id,),
    )
    connection.execute(
        """
        INSERT INTO roll_entries (card_id, order_number, roll_number, gross_weight, net_weight)
        VALUES (?, '25281', 1, 25.50, 24.25)
        """,
        (card_id,),
    )
    connection.execute(
        """
        INSERT INTO production_time_segments (card_id, started_at, ended_at, end_reason)
        VALUES (?, '2026-06-12T08:00:00', '2026-06-12T09:00:00', 'pause')
        """,
        (card_id,),
    )
    connection.commit()

    result = import_cards_from_csv(
        "overwrite.csv",
        csv_bytes(
            extrusion_row(
                "25281",
                customer="Updated Customer",
                raw_material_a="Updated LDPE",
            )
        ),
        overwrite_existing=True,
    )

    card = connection.execute(
        """
        SELECT status, machine_id, machine_sequence, customer, raw_material_a,
               tare_weight, actual_raw_material_used, raw_material_brand_grade,
               raw_material_batch_lot, first_started_at
        FROM cards
        WHERE id = ?
        """,
        (card_id,),
    ).fetchone()
    roll_count = connection.execute(
        "SELECT COUNT(*) FROM roll_entries WHERE card_id = ?",
        (card_id,),
    ).fetchone()[0]
    segment_count = connection.execute(
        "SELECT COUNT(*) FROM production_time_segments WHERE card_id = ?",
        (card_id,),
    ).fetchone()[0]

    assert result.updated == 1
    assert result.row_results[0].action == "updated"
    assert result.row_results[0].order_number == "25281"
    assert card["status"] == STATUS_PENDING
    assert card["machine_id"] == 2
    assert card["machine_sequence"] == 7
    assert card["customer"] == "Updated Customer"
    assert card["raw_material_a"] == "Updated LDPE"
    assert card["tare_weight"] == 1.25
    assert card["actual_raw_material_used"] == "Actual LDPE"
    assert card["raw_material_brand_grade"] == "Grade A"
    assert card["raw_material_batch_lot"] == "Batch 42"
    assert card["first_started_at"] == "2026-06-12T08:00:00"
    assert roll_count == 1
    assert segment_count == 1


def test_release_succeeds_for_ready_cards(connection):
    card_id = import_one_ready_card("25282")

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)

    card = connection.execute(
        "SELECT status, machine_id, machine_sequence FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()

    assert result.ok
    assert card["status"] == STATUS_PENDING
    assert card["machine_id"] == 1
    assert card["machine_sequence"] == 1


def test_release_blocks_invalid_non_ready_cards(connection):
    cursor = connection.execute(
        """
        INSERT INTO cards (
            order_number,
            status,
            validation_status,
            customer,
            product_type
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "25283",
            STATUS_IMPORTED,
            VALIDATION_NO_EXTRUSION_STEP,
            "Invalid Customer",
            "PE film",
        ),
    )
    connection.commit()
    card_id = int(cursor.lastrowid)

    release_result = db.release_card(card_id, machine_id=1, machine_sequence=1)

    card = connection.execute(
        "SELECT status, machine_id, machine_sequence FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()

    assert not release_result.ok
    assert "Only ready cards can be released." in release_result.messages
    assert card["status"] == STATUS_IMPORTED
    assert card["machine_id"] is None
    assert card["machine_sequence"] is None


def test_release_blocks_duplicate_active_machine_sequence(connection):
    first_card_id = import_one_ready_card("25284")
    second_card_id = import_one_ready_card("25285")
    assert db.release_card(first_card_id, machine_id=3, machine_sequence=4).ok

    duplicate_result = db.release_card(second_card_id, machine_id=3, machine_sequence=4)

    second_card = connection.execute(
        "SELECT status, machine_id, machine_sequence FROM cards WHERE id = ?",
        (second_card_id,),
    ).fetchone()

    assert not duplicate_result.ok
    assert duplicate_result.messages == (
        "Machine 3 already has active sequence 4 on order 25284.",
    )
    assert second_card["status"] == STATUS_IMPORTED
    assert second_card["machine_id"] is None
    assert second_card["machine_sequence"] is None


def test_released_cards_appear_in_machine_queues(connection):
    first_card_id = import_one_ready_card("25286")
    second_card_id = import_one_ready_card("25287")
    assert db.release_card(first_card_id, machine_id=4, machine_sequence=2).ok
    assert db.release_card(second_card_id, machine_id=4, machine_sequence=1).ok

    queues = db.fetch_machine_queues()
    machine_4_cards = [
        card["order_number"]
        for queue in queues
        if queue["machine"]["id"] == 4
        for card in queue["cards"]
    ]

    assert machine_4_cards == ["25287", "25286"]
