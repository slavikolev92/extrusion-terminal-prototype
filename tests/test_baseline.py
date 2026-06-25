from __future__ import annotations

import csv
import io
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

from app import db
from app.constants import (
    CARD_STATUSES,
    STATUS_ARCHIVED,
    STATUS_COMPLETED,
    STATUS_IMPORTED,
    STATUS_LABELS,
    STATUS_PENDING,
)
from app.importer import IMPORT_FIELDS, csv_template, import_cards_from_csv


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
        "raw_material_a": "LDPE A | 100%",
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


def current_import_fields(connection, card_id: int) -> dict[str, str]:
    row = connection.execute(
        f"""
        SELECT {", ".join(IMPORT_FIELDS)}
        FROM cards
        WHERE id = ?
        """,
        (card_id,),
    ).fetchone()
    assert row is not None
    return {field: str(row[field] or "") for field in IMPORT_FIELDS}


def test_csv_template_uses_valid_structured_recipe_sample():
    content = csv_template()

    assert "raw_material_a" in content
    assert "reLDPE | 100%" in content
    assert "N/A" not in content


def test_database_initialization_seeds_machines_1_through_4(temp_db_path):
    assert temp_db_path.exists()

    machines = db.fetch_machines()

    assert [machine["id"] for machine in machines] == [1, 2, 3, 4]
    assert [machine["display_order"] for machine in machines] == [1, 2, 3, 4]


def test_status_constants_label_completed_as_produced_and_archived_as_finished():
    assert STATUS_COMPLETED in CARD_STATUSES
    assert STATUS_ARCHIVED in CARD_STATUSES
    assert STATUS_LABELS[STATUS_COMPLETED] == "Произведена"
    assert STATUS_LABELS[STATUS_ARCHIVED] == "Завършена"


def test_new_cards_schema_allows_archived_status(connection):
    schema_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
    ).fetchone()["sql"]

    assert "'archived'" in schema_sql

    connection.execute(
        """
        INSERT INTO cards (order_number, status)
        VALUES (?, ?)
        """,
        ("ARCHIVED-SCHEMA-1", STATUS_ARCHIVED),
    )

    status = connection.execute(
        "SELECT status FROM cards WHERE order_number = ?",
        ("ARCHIVED-SCHEMA-1",),
    ).fetchone()["status"]
    assert status == STATUS_ARCHIVED


def test_csv_import_creates_imported_ready_cards(connection):
    result = import_cards_from_csv(
        "orders.csv",
        csv_bytes(extrusion_row("25278")),
        overwrite_existing=False,
    )

    card = connection.execute(
        "SELECT order_number, status, customer, max_roll_weight FROM cards"
    ).fetchone()

    assert result.rows_seen == 1
    assert result.rows_imported == 1
    assert result.created == 1
    assert len(result.row_results) == 1
    assert result.row_results[0].row_number == 2
    assert result.row_results[0].order_number == "25278"
    assert result.row_results[0].action == "created"
    assert result.row_results[0].message == "Създадена нова технологична карта; готова за планиране."
    assert card["order_number"] == "25278"
    assert card["status"] == STATUS_IMPORTED
    assert card["customer"] == "Test Customer"
    assert card["max_roll_weight"] is None


def test_database_initialization_adds_max_roll_weight_to_existing_cards_table(
    monkeypatch,
):
    legacy_data_dir = Path.cwd() / ".test-runtime" / uuid4().hex
    legacy_data_dir.mkdir(parents=True)
    legacy_db_path = legacy_data_dir / "legacy.sqlite3"
    try:
        with sqlite3.connect(legacy_db_path) as legacy_connection:
            legacy_connection.execute(
                """
                CREATE TABLE cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'imported',
                    machine_id INTEGER,
                    machine_sequence INTEGER
                )
                """
            )

        monkeypatch.setattr(db, "DATA_DIR", legacy_data_dir)
        monkeypatch.setattr(db, "DB_PATH", legacy_db_path)

        db.init_db()
        db.init_db()

        with db.connect() as migrated_connection:
            columns = {
                row["name"]
                for row in migrated_connection.execute("PRAGMA table_info(cards)").fetchall()
            }
    finally:
        shutil.rmtree(legacy_data_dir, ignore_errors=True)

    assert "max_roll_weight" in columns


def test_database_initialization_updates_existing_status_check_to_allow_archived(
    monkeypatch,
):
    legacy_data_dir = Path.cwd() / ".test-runtime" / uuid4().hex
    legacy_data_dir.mkdir(parents=True)
    legacy_db_path = legacy_data_dir / "legacy-status-check.sqlite3"
    try:
        with sqlite3.connect(legacy_db_path) as legacy_connection:
            legacy_connection.execute(
                """
                CREATE TABLE cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'imported'
                        CHECK (status IN ('imported', 'pending', 'running', 'paused', 'completed', 'cancelled')),
                    machine_id INTEGER,
                    machine_sequence INTEGER,
                    max_roll_weight TEXT
                )
                """
            )
            legacy_connection.execute(
                "INSERT INTO cards (order_number, status) VALUES (?, ?)",
                ("LEGACY-ARCHIVE-1", STATUS_COMPLETED),
            )

        monkeypatch.setattr(db, "DATA_DIR", legacy_data_dir)
        monkeypatch.setattr(db, "DB_PATH", legacy_db_path)

        db.init_db()
        db.init_db()

        with db.connect() as migrated_connection:
            migrated_connection.execute(
                "UPDATE cards SET status = ? WHERE order_number = ?",
                (STATUS_ARCHIVED, "LEGACY-ARCHIVE-1"),
            )
            migrated_connection.commit()
            schema_sql = migrated_connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
            ).fetchone()["sql"]
            status = migrated_connection.execute(
                "SELECT status FROM cards WHERE order_number = ?",
                ("LEGACY-ARCHIVE-1",),
            ).fetchone()["status"]
    finally:
        shutil.rmtree(legacy_data_dir, ignore_errors=True)

    assert "'archived'" in schema_sql
    assert status == STATUS_ARCHIVED


def test_database_initialization_preserves_legacy_only_cards_columns_during_status_check_migration(
    monkeypatch,
):
    legacy_data_dir = Path.cwd() / ".test-runtime" / uuid4().hex
    legacy_data_dir.mkdir(parents=True)
    legacy_db_path = legacy_data_dir / "legacy-status-check-extra-column.sqlite3"
    try:
        with sqlite3.connect(legacy_db_path) as legacy_connection:
            legacy_connection.execute(
                """
                CREATE TABLE cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'imported'
                        CHECK (status IN ('imported', 'pending', 'running', 'paused', 'completed', 'cancelled')),
                    machine_id INTEGER,
                    machine_sequence INTEGER,
                    max_roll_weight TEXT,
                    validation_status TEXT
                )
                """
            )
            legacy_connection.execute(
                """
                INSERT INTO cards (order_number, status, validation_status)
                VALUES (?, ?, ?)
                """,
                ("LEGACY-EXTRA-COLUMN-1", STATUS_COMPLETED, "legacy-ready"),
            )

        monkeypatch.setattr(db, "DATA_DIR", legacy_data_dir)
        monkeypatch.setattr(db, "DB_PATH", legacy_db_path)

        db.init_db()
        db.init_db()

        with db.connect() as migrated_connection:
            migrated_connection.execute(
                "UPDATE cards SET status = ? WHERE order_number = ?",
                (STATUS_ARCHIVED, "LEGACY-EXTRA-COLUMN-1"),
            )
            migrated_connection.commit()
            columns = {
                row["name"]
                for row in migrated_connection.execute("PRAGMA table_info(cards)").fetchall()
            }
            schema_sql = migrated_connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
            ).fetchone()["sql"]
            card = migrated_connection.execute(
                """
                SELECT status, validation_status
                FROM cards
                WHERE order_number = ?
                """,
                ("LEGACY-EXTRA-COLUMN-1",),
            ).fetchone()
    finally:
        shutil.rmtree(legacy_data_dir, ignore_errors=True)

    assert "validation_status" in columns
    assert "'archived'" in schema_sql
    assert dict(card) == {
        "status": STATUS_ARCHIVED,
        "validation_status": "legacy-ready",
    }


def test_database_initialization_seeds_machines_before_status_check_fk_validation(
    monkeypatch,
):
    legacy_data_dir = Path.cwd() / ".test-runtime" / uuid4().hex
    legacy_data_dir.mkdir(parents=True)
    legacy_db_path = legacy_data_dir / "legacy-status-check-machine-fk.sqlite3"
    try:
        with sqlite3.connect(legacy_db_path) as legacy_connection:
            legacy_connection.execute(
                """
                CREATE TABLE machines (
                    id INTEGER PRIMARY KEY CHECK (id BETWEEN 1 AND 4),
                    name TEXT NOT NULL,
                    is_operational INTEGER NOT NULL DEFAULT 1 CHECK (is_operational IN (0, 1)),
                    display_order INTEGER NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            legacy_connection.execute(
                """
                CREATE TABLE cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'imported'
                        CHECK (status IN ('imported', 'pending', 'running', 'paused', 'completed', 'cancelled')),
                    machine_id INTEGER REFERENCES machines(id) ON DELETE RESTRICT,
                    machine_sequence INTEGER,
                    max_roll_weight TEXT
                )
                """
            )
            legacy_connection.execute(
                """
                INSERT INTO cards (order_number, status, machine_id, machine_sequence)
                VALUES (?, ?, ?, ?)
                """,
                ("LEGACY-MACHINE-FK-1", STATUS_PENDING, 1, 1),
            )

        monkeypatch.setattr(db, "DATA_DIR", legacy_data_dir)
        monkeypatch.setattr(db, "DB_PATH", legacy_db_path)

        db.init_db()

        with db.connect() as migrated_connection:
            migrated_connection.execute(
                "UPDATE cards SET status = ? WHERE order_number = ?",
                (STATUS_ARCHIVED, "LEGACY-MACHINE-FK-1"),
            )
            migrated_connection.commit()
            machines = migrated_connection.execute(
                "SELECT id, display_order FROM machines ORDER BY id"
            ).fetchall()
            card = migrated_connection.execute(
                """
                SELECT order_number, status, machine_id, machine_sequence
                FROM cards
                WHERE order_number = ?
                """,
                ("LEGACY-MACHINE-FK-1",),
            ).fetchone()
            violations = migrated_connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        shutil.rmtree(legacy_data_dir, ignore_errors=True)

    assert [(machine["id"], machine["display_order"]) for machine in machines] == [
        (1, 1),
        (2, 2),
        (3, 3),
        (4, 4),
    ]
    assert dict(card) == {
        "order_number": "LEGACY-MACHINE-FK-1",
        "status": STATUS_ARCHIVED,
        "machine_id": 1,
        "machine_sequence": 1,
    }
    assert violations == []


def test_csv_import_ignores_max_roll_weight_alias(connection):
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "order_number",
            "customer",
            "product_type",
            "quantity_1",
            "unit_1",
            "material",
            "max_roll_weight_kg",
            "size_thickness",
            "extrusion_flag",
            "raw_material_a",
            "packaging_method",
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerow(
        {
            "order_number": "25290",
            "customer": "Alias Customer",
            "product_type": "PE film",
            "quantity_1": "500",
            "unit_1": "kg",
            "material": "LDPE",
            "max_roll_weight_kg": "75",
            "size_thickness": "600/0.050",
            "extrusion_flag": "da",
            "raw_material_a": "LDPE A | 100%",
            "packaging_method": "rolls",
        }
    )

    result = import_cards_from_csv(
        "alias.csv",
        output.getvalue().encode("utf-8"),
        overwrite_existing=False,
    )
    card = connection.execute(
        "SELECT max_roll_weight FROM cards WHERE order_number = '25290'"
    ).fetchone()

    assert result.rows_imported == 1
    assert card["max_roll_weight"] is None


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
        "SELECT order_number, status FROM cards WHERE order_number = '25279'"
    ).fetchone()

    assert result.rows_imported == 0
    assert result.skipped == 1
    assert result.row_results[0].action == "skipped"
    assert "няма екструдиране" in result.row_results[0].message
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
    assert "обновяване" in duplicate.row_results[0].message
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
    assert "Дублиран номер на поръчка" in result.row_results[1].message
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
    assert result.row_results[0].message == "Липсва номер на поръчка."
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
    assert "Липсват задължителни CSV колони" in result.row_results[0].message
    assert card_count == 0


def test_overwrite_import_updates_imported_fields_and_preserves_production_data(connection):
    card_id = import_one_ready_card("25281")
    db.release_card(
        card_id,
        machine_id=2,
        machine_sequence=1,
        max_roll_weight="60.0",
    )

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
        SELECT status, machine_id, machine_sequence, customer, max_roll_weight, raw_material_a,
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
    assert card["machine_sequence"] == 1
    assert card["customer"] == "Updated Customer"
    assert card["max_roll_weight"] == "60.0"
    assert card["raw_material_a"] == "Updated LDPE"
    assert card["tare_weight"] == 1.25
    assert card["actual_raw_material_used"] == "Actual LDPE"
    assert card["raw_material_brand_grade"] == "Grade A"
    assert card["raw_material_batch_lot"] == "Batch 42"
    assert card["first_started_at"] == "2026-06-12T08:00:00"
    assert roll_count == 1
    assert segment_count == 1


def test_overwrite_import_blocks_stale_source_after_admin_imported_field_correction(connection):
    card_id = import_one_ready_card("25291")
    fields = current_import_fields(connection, card_id)
    fields["city"] = "Corrected City"
    fields["product_type"] = "Corrected Product"
    fields["raw_material_a"] = "Corrected LDPE"
    card = db.fetch_admin_card_detail(card_id)
    assert db.update_admin_imported_fields(card_id, card["version"], fields).ok
    corrected = db.fetch_admin_card_detail(card_id)

    result = import_cards_from_csv(
        "stale-overwrite.csv",
        csv_bytes(extrusion_row("25291")),
        overwrite_existing=True,
    )

    unchanged = db.fetch_admin_card_detail(card_id)
    assert result.rows_imported == 0
    assert result.updated == 0
    assert result.skipped == 1
    assert result.row_results[0].action == "blocked"
    assert "администратор" in result.row_results[0].message.casefold()
    assert "преглед" in result.row_results[0].message.casefold()
    assert unchanged["city"] == "Corrected City"
    assert unchanged["product_type"] == "Corrected Product"
    assert unchanged["raw_material_a"] == "Corrected LDPE"
    assert unchanged["version"] == corrected["version"]
    assert unchanged["import_batch_id"] == corrected["import_batch_id"]


def test_overwrite_import_allows_when_current_fields_match_incoming_after_admin_correction(connection):
    card_id = import_one_ready_card("25292")
    fields = current_import_fields(connection, card_id)
    fields["product_type"] = "Corrected Product"
    card = db.fetch_admin_card_detail(card_id)
    assert db.update_admin_imported_fields(card_id, card["version"], fields).ok

    matching_result = import_cards_from_csv(
        "matching-correction.csv",
        csv_bytes(extrusion_row("25292", product_type="Corrected Product")),
        overwrite_existing=True,
    )
    assert matching_result.rows_imported == 1
    assert matching_result.updated == 1
    assert matching_result.row_results[0].action == "updated"

    source = connection.execute(
        """
        SELECT product_type
        FROM card_import_sources
        WHERE card_id = ?
        """,
        (card_id,),
    ).fetchone()

    assert source["product_type"] == "Corrected Product"


def test_overwrite_import_blocks_old_order_number_after_admin_order_number_correction(connection):
    card_id = import_one_ready_card("25293")
    fields = current_import_fields(connection, card_id)
    fields["order_number"] = "25293A"
    card = db.fetch_admin_card_detail(card_id)
    assert db.update_admin_imported_fields(card_id, card["version"], fields).ok
    corrected = db.fetch_admin_card_detail(card_id)

    result = import_cards_from_csv(
        "old-order.csv",
        csv_bytes(extrusion_row("25293")),
        overwrite_existing=True,
    )
    cards = connection.execute(
        "SELECT id, order_number, version, import_batch_id FROM cards ORDER BY id"
    ).fetchall()

    assert result.rows_imported == 0
    assert result.updated == 0
    assert result.skipped == 1
    assert result.row_results[0].action == "blocked"
    assert "администратор" in result.row_results[0].message.casefold()
    assert len(cards) == 1
    assert cards[0]["id"] == card_id
    assert cards[0]["order_number"] == "25293A"
    assert cards[0]["version"] == corrected["version"]
    assert cards[0]["import_batch_id"] == corrected["import_batch_id"]


def test_overwrite_import_blocks_stale_row_without_blocking_other_rows(connection):
    card_id = import_one_ready_card("25294")
    fields = current_import_fields(connection, card_id)
    fields["city"] = "Corrected City"
    card = db.fetch_admin_card_detail(card_id)
    assert db.update_admin_imported_fields(card_id, card["version"], fields).ok

    result = import_cards_from_csv(
        "mixed-overwrite.csv",
        csv_bytes(
            extrusion_row("25294"),
            extrusion_row("25295", customer="Second Customer"),
        ),
        overwrite_existing=True,
    )
    unchanged = db.fetch_admin_card_detail(card_id)
    created = connection.execute(
        "SELECT customer FROM cards WHERE order_number = '25295'"
    ).fetchone()

    assert result.rows_seen == 2
    assert result.rows_imported == 1
    assert result.created == 1
    assert result.updated == 0
    assert result.skipped == 1
    assert [row.action for row in result.row_results] == ["blocked", "created"]
    assert unchanged["city"] == "Corrected City"
    assert created["customer"] == "Second Customer"


def test_import_batch_result_reconstructs_processed_rows_after_redirect(connection):
    result = import_cards_from_csv(
        "route-result.csv",
        csv_bytes(
            extrusion_row("25296"),
            extrusion_row(
                "32999",
                extrusion_flag="не",
                raw_material_a="",
                packaging_method="",
            ),
        ),
        overwrite_existing=False,
    )

    detail = db.fetch_import_batch_result(result.batch_id)

    assert result.batch_id is not None
    assert detail is not None
    assert detail["batch_id"] == result.batch_id
    assert detail["filename"] == "route-result.csv"
    assert detail["rows_seen"] == 2
    assert detail["rows_imported"] == 1
    assert detail["created"] == 1
    assert detail["updated"] == 0
    assert detail["skipped"] == 1
    assert [row["row_number"] for row in detail["row_results"]] == [2, 3]
    assert [row["order_number"] for row in detail["row_results"]] == ["25296", "32999"]
    assert [row["action"] for row in detail["row_results"]] == ["created", "skipped"]
    assert detail["row_results"][0]["message"] == (
        "Създадена нова технологична карта; готова за планиране."
    )
    assert detail["row_results"][1]["message"] == "Пропуснат ред: няма екструдиране."
    assert "Ред 3: Пропуснат ред: няма екструдиране." in detail["row_errors"]


def test_import_batch_result_persists_blocked_stale_overwrite_rows(connection):
    card_id = import_one_ready_card("25297")
    fields = current_import_fields(connection, card_id)
    fields["city"] = "Corrected City"
    card = db.fetch_admin_card_detail(card_id)
    assert db.update_admin_imported_fields(card_id, card["version"], fields).ok

    result = import_cards_from_csv(
        "blocked-result.csv",
        csv_bytes(extrusion_row("25297")),
        overwrite_existing=True,
    )

    detail = db.fetch_import_batch_result(result.batch_id)

    assert result.batch_id is not None
    assert detail is not None
    assert detail["rows_seen"] == 1
    assert detail["rows_imported"] == 0
    assert detail["created"] == 0
    assert detail["updated"] == 0
    assert detail["skipped"] == 1
    assert len(detail["row_results"]) == 1
    assert detail["row_results"][0]["row_number"] == 2
    assert detail["row_results"][0]["order_number"] == "25297"
    assert detail["row_results"][0]["action"] == "blocked"
    assert "администратор" in detail["row_results"][0]["message"].casefold()
    assert "Ред 2:" in detail["row_errors"][0]


def test_import_batch_result_preserves_duplicate_and_error_summaries(connection):
    import_one_ready_card("25310")

    result = import_cards_from_csv(
        "mixed-summary-result.csv",
        csv_bytes(
            extrusion_row("25310"),
            extrusion_row("25311"),
            extrusion_row(
                "33010",
                extrusion_flag="не",
                raw_material_a="",
                packaging_method="",
            ),
            extrusion_row("25311"),
        ),
        overwrite_existing=False,
    )

    detail = db.fetch_import_batch_result(result.batch_id)

    assert result.duplicate_rows == ["25310", "25311"]
    assert result.row_errors == [
        "Ред 4: Пропуснат ред: няма екструдиране.",
        "Ред 5: Дублиран номер на поръчка в този CSV файл. 25311.",
    ]
    assert detail is not None
    assert detail["duplicate_rows"] == result.duplicate_rows
    assert detail["row_errors"] == result.row_errors
    assert [row["order_number"] for row in detail["row_results"]] == [
        "25310",
        "25311",
        "33010",
        "25311",
    ]


def test_release_succeeds_for_ready_cards(connection):
    card_id = import_one_ready_card("25282")

    result = db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        max_roll_weight="60.0",
    )

    card = connection.execute(
        "SELECT status, machine_id, machine_sequence, max_roll_weight FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()

    assert result.ok
    assert card["status"] == STATUS_PENDING
    assert card["machine_id"] == 1
    assert card["machine_sequence"] == 1
    assert card["max_roll_weight"] == "60.0"


def test_release_allows_blank_shift_manager_max_roll_weight(connection):
    card_id = import_one_ready_card("25291")

    result = db.release_card(card_id, machine_id=1, machine_sequence=1)
    card = connection.execute(
        "SELECT status, machine_id, machine_sequence, max_roll_weight FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()

    assert result.ok
    assert card["status"] == STATUS_PENDING
    assert card["machine_id"] == 1
    assert card["machine_sequence"] == 1
    assert card["max_roll_weight"] in (None, "")


def test_release_blocks_cards_without_usable_extrusion_fields(connection):
    cursor = connection.execute(
        """
        INSERT INTO cards (
            order_number,
            status,
            customer,
            product_type
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            "25283",
            STATUS_IMPORTED,
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
    assert "Картата трябва да има валидна стъпка за екструдиране преди изпращане." in release_result.messages
    assert card["status"] == STATUS_IMPORTED
    assert card["machine_id"] is None
    assert card["machine_sequence"] is None


def test_release_inserts_at_existing_position_and_normalizes_machine_sequence(connection):
    first_card_id = import_one_ready_card("25284")
    second_card_id = import_one_ready_card("25285")
    assert db.release_card(
        first_card_id,
        machine_id=3,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok

    insert_result = db.release_card(
        second_card_id,
        machine_id=3,
        machine_sequence=1,
        max_roll_weight="60.0",
    )

    cards = connection.execute(
        """
        SELECT order_number, status, machine_id, machine_sequence
        FROM cards
        WHERE id IN (?, ?)
        ORDER BY machine_sequence
        """,
        (first_card_id, second_card_id),
    ).fetchall()

    assert insert_result.ok
    assert [(card["order_number"], card["status"], card["machine_id"], card["machine_sequence"]) for card in cards] == [
        ("25285", STATUS_PENDING, 3, 1),
        ("25284", STATUS_PENDING, 3, 2),
    ]


def test_released_cards_appear_in_machine_queues(connection):
    first_card_id = import_one_ready_card("25286")
    second_card_id = import_one_ready_card("25287")
    assert db.release_card(
        first_card_id,
        machine_id=4,
        machine_sequence=2,
        max_roll_weight="60.0",
    ).ok
    assert db.release_card(
        second_card_id,
        machine_id=4,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok

    queues = db.fetch_machine_queues()
    machine_4_cards = [
        card["order_number"]
        for queue in queues
        if queue["machine"]["id"] == 4
        for card in queue["cards"]
    ]

    assert machine_4_cards == ["25287", "25286"]
