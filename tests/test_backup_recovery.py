from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app import db
from app.backups import (
    BACKUP_FILENAME_PREFIX,
    BACKUP_FILENAME_SUFFIX,
    apply_retention,
    create_backup,
    restore_backup,
)
from app.importer import IMPORT_FIELDS, import_cards_from_csv


def csv_bytes(*rows: dict[str, str]) -> bytes:
    import csv
    import io

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")


def extrusion_row(order_number: str, **overrides: str) -> dict[str, str]:
    row = {
        "order_number": order_number,
        "customer": "Backup Customer",
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


def import_sample_card(order_number: str = "25700") -> int:
    result = import_cards_from_csv(
        "backup-sample.csv",
        csv_bytes(extrusion_row(order_number, customer="Backup Customer")),
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


def test_backup_creates_timestamped_sqlite_file(temp_db_path: Path):
    backup_dir = temp_db_path.parent / "backups"
    import_sample_card("25701")

    result = create_backup(source_db_path=temp_db_path, backup_dir=backup_dir, keep_count=10)

    assert result.source_path == temp_db_path.resolve()
    assert result.backup_path.parent == backup_dir.resolve()
    assert result.backup_path.exists()
    assert re.match(
        rf"{BACKUP_FILENAME_PREFIX}\d{{8}}_\d{{6}}_\d{{6}}{re.escape(BACKUP_FILENAME_SUFFIX)}$",
        result.backup_path.name,
    )


def test_backup_does_not_overwrite_existing_backup_with_same_timestamp(temp_db_path: Path):
    backup_dir = temp_db_path.parent / "backups"
    timestamp = datetime(2026, 6, 13, 8, 0, 0, 123456)

    first = create_backup(temp_db_path, backup_dir, keep_count=10, timestamp=timestamp)
    second = create_backup(temp_db_path, backup_dir, keep_count=10, timestamp=timestamp)

    assert first.backup_path.exists()
    assert second.backup_path.exists()
    assert first.backup_path != second.backup_path
    assert second.backup_path.name.endswith(f"_001{BACKUP_FILENAME_SUFFIX}")


def test_backup_restores_database_contents_to_separate_temp_database(temp_db_path: Path):
    backup_dir = temp_db_path.parent / "backups"
    card_id = import_sample_card("25702")
    assert db.release_card(
        card_id,
        machine_id=2,
        machine_sequence=1,
        max_roll_weight="60.0",
    ).ok

    backup_result = create_backup(temp_db_path, backup_dir, keep_count=10)
    restore_path = temp_db_path.parent / "restored" / "restored.sqlite3"
    restored_path = restore_backup(backup_result.backup_path, restore_path)

    with sqlite3.connect(restored_path) as restored:
        restored.row_factory = sqlite3.Row
        card = restored.execute(
            """
            SELECT order_number, customer, status, machine_id, machine_sequence
            FROM cards
            WHERE order_number = '25702'
            """
        ).fetchone()

    assert restored_path == restore_path.resolve()
    assert card["order_number"] == "25702"
    assert card["customer"] == "Backup Customer"
    assert card["status"] == "pending"
    assert card["machine_id"] == 2
    assert card["machine_sequence"] == 1


def test_backup_runs_while_source_database_connection_is_open(
    connection: sqlite3.Connection,
    temp_db_path: Path,
):
    backup_dir = temp_db_path.parent / "backups"
    import_sample_card("25703")
    open_connection_count = connection.execute("SELECT COUNT(*) FROM machines").fetchone()[0]

    backup_result = create_backup(temp_db_path, backup_dir, keep_count=10)
    restore_path = temp_db_path.parent / "open-connection-restore.sqlite3"
    restore_backup(backup_result.backup_path, restore_path)

    with sqlite3.connect(restore_path) as restored:
        restored_count = restored.execute("SELECT COUNT(*) FROM machines").fetchone()[0]
        restored_card_count = restored.execute(
            "SELECT COUNT(*) FROM cards WHERE order_number = '25703'"
        ).fetchone()[0]

    assert open_connection_count == 4
    assert restored_count == 4
    assert restored_card_count == 1


def test_restore_refuses_missing_backup_path(temp_db_path: Path):
    missing_backup = temp_db_path.parent / "missing.sqlite3"
    restore_path = temp_db_path.parent / "restore.sqlite3"

    with pytest.raises(FileNotFoundError):
        restore_backup(missing_backup, restore_path)

    assert not restore_path.exists()


def test_restore_refuses_same_backup_and_target_path(temp_db_path: Path):
    backup_dir = temp_db_path.parent / "backups"
    backup_result = create_backup(temp_db_path, backup_dir, keep_count=10)

    with pytest.raises(ValueError):
        restore_backup(backup_result.backup_path, backup_result.backup_path)


def test_failed_restore_leaves_existing_target_database_untouched(temp_db_path: Path):
    bad_backup = temp_db_path.parent / "bad-backup.sqlite3"
    bad_backup.write_text("not a sqlite database", encoding="utf-8")
    target_path = temp_db_path.parent / "existing-target.sqlite3"
    with sqlite3.connect(target_path) as target:
        target.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        target.execute("INSERT INTO sentinel (value) VALUES ('keep')")

    with pytest.raises(sqlite3.DatabaseError):
        restore_backup(bad_backup, target_path)

    with sqlite3.connect(target_path) as target:
        value = target.execute("SELECT value FROM sentinel").fetchone()[0]

    assert value == "keep"


def test_retention_keeps_newest_matching_backups_only(temp_db_path: Path):
    backup_dir = temp_db_path.parent / "backups"
    backup_dir.mkdir()
    base_time = datetime(2026, 6, 13, 12, 0, 0).timestamp()
    backup_paths = []
    for index in range(5):
        path = backup_dir / f"{BACKUP_FILENAME_PREFIX}20260613_12000{index}_000000{BACKUP_FILENAME_SUFFIX}"
        path.write_text(f"backup {index}", encoding="utf-8")
        os.utime(path, (base_time + index, base_time + index))
        backup_paths.append(path)
    unrelated = backup_dir / "operator-note.txt"
    unrelated.write_text("keep me", encoding="utf-8")

    retained, removed = apply_retention(backup_dir, keep_count=2)

    assert {path.name for path in retained} == {backup_paths[4].name, backup_paths[3].name}
    assert {path.name for path in removed} == {
        backup_paths[0].name,
        backup_paths[1].name,
        backup_paths[2].name,
    }
    assert backup_paths[4].exists()
    assert backup_paths[3].exists()
    assert not backup_paths[2].exists()
    assert unrelated.exists()


def test_backup_restore_tests_use_temp_database_not_runtime_database(temp_db_path: Path):
    runtime_db_path = (db.BASE_DIR / "data" / "extrusion_terminal.sqlite3").resolve()
    backup_dir = temp_db_path.parent / "backups"
    restore_path = temp_db_path.parent / "restored.sqlite3"

    assert temp_db_path.resolve() != runtime_db_path
    backup_result = create_backup(temp_db_path, backup_dir, keep_count=10)
    restore_backup(backup_result.backup_path, restore_path)

    assert backup_result.source_path == temp_db_path.resolve()
    assert restore_path.resolve() != runtime_db_path
