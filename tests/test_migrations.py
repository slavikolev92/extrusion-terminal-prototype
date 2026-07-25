from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import db, migrations


FINAL_IMPORT_COLUMNS = (
    "ordered_gross_kg",
    "ordered_rolls",
    "ordered_meters",
    "ordered_units",
    "printing_sequence",
    "extrusion_sequence",
    "rewinding_slitting_sequence",
    "confection_sequence",
)


def create_legacy_database(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE machines (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                is_operational INTEGER NOT NULL,
                display_order INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE import_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_filename TEXT,
                rows_seen INTEGER NOT NULL DEFAULT 0,
                rows_imported INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'imported'
                    CHECK (status IN (
                        'imported', 'pending', 'running', 'paused',
                        'completed', 'archived', 'cancelled'
                    )),
                import_batch_id INTEGER REFERENCES import_batches(id),
                machine_id INTEGER REFERENCES machines(id),
                machine_sequence INTEGER,
                order_date TEXT,
                delivery_date TEXT,
                customer TEXT,
                city TEXT,
                product_type TEXT,
                quantity_1 TEXT,
                unit_1 TEXT,
                quantity_2 TEXT,
                unit_2 TEXT,
                product_form TEXT,
                material TEXT,
                max_roll_weight TEXT,
                size_thickness TEXT,
                notes TEXT,
                extrusion_flag TEXT,
                extrusion_folding TEXT,
                extrusion_next_operation TEXT,
                extrusion_treatment TEXT,
                raw_material_a TEXT,
                raw_material_b TEXT,
                raw_material_c TEXT,
                linear_pe TEXT,
                antistatic TEXT,
                masterbatch TEXT,
                chalk TEXT,
                packaging_method TEXT,
                actual_raw_material_used TEXT,
                raw_material_brand_grade TEXT,
                raw_material_batch_lot TEXT,
                tare_weight NUMERIC,
                first_started_at TEXT,
                finished_at TEXT,
                cancelled_at TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE card_import_sources (
                card_id INTEGER PRIMARY KEY REFERENCES cards(id),
                import_batch_id INTEGER REFERENCES import_batches(id),
                order_number TEXT,
                order_date TEXT,
                delivery_date TEXT,
                customer TEXT,
                city TEXT,
                product_type TEXT,
                quantity_1 TEXT,
                unit_1 TEXT,
                quantity_2 TEXT,
                unit_2 TEXT,
                product_form TEXT,
                material TEXT,
                size_thickness TEXT,
                notes TEXT,
                extrusion_flag TEXT,
                extrusion_folding TEXT,
                extrusion_next_operation TEXT,
                extrusion_treatment TEXT,
                raw_material_a TEXT,
                raw_material_b TEXT,
                raw_material_c TEXT,
                linear_pe TEXT,
                antistatic TEXT,
                masterbatch TEXT,
                chalk TEXT,
                packaging_method TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE roll_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL REFERENCES cards(id),
                order_number TEXT NOT NULL,
                roll_number INTEGER NOT NULL,
                gross_weight NUMERIC,
                tare_weight NUMERIC,
                net_weight NUMERIC,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (card_id, roll_number)
            );

            CREATE TABLE recipe_actual_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL REFERENCES cards(id),
                component_key TEXT NOT NULL,
                component_label TEXT NOT NULL,
                planned_material TEXT,
                actual_material_used TEXT,
                batch_lot TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (card_id, component_key)
            );

            CREATE TABLE recipe_components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL REFERENCES cards(id),
                component_key TEXT NOT NULL,
                source_text TEXT NOT NULL,
                material_category TEXT NOT NULL,
                planned_material TEXT NOT NULL,
                recipe_percent NUMERIC NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (card_id, component_key)
            );

            CREATE TABLE production_time_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL REFERENCES cards(id),
                started_at TEXT NOT NULL,
                ended_at TEXT,
                end_reason TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            INSERT INTO machines (
                id, name, is_operational, display_order, created_at, updated_at
            ) VALUES (
                1, 'Legacy machine 1', 1, 1,
                '2026-07-20 06:00:00', '2026-07-20 06:00:00'
            );

            INSERT INTO import_batches (
                id, source_filename, rows_seen, rows_imported, notes, created_at
            ) VALUES (
                1, 'legacy.csv', 1, 1, 'legacy batch', '2026-07-20 06:05:00'
            );

            INSERT INTO cards (
                id, order_number, status, import_batch_id, machine_id,
                machine_sequence, order_date, delivery_date, customer, city,
                product_type, quantity_1, unit_1, quantity_2, unit_2,
                product_form, material, max_roll_weight, size_thickness, notes,
                extrusion_flag, extrusion_folding, extrusion_next_operation,
                extrusion_treatment, raw_material_a, packaging_method,
                actual_raw_material_used, raw_material_brand_grade,
                raw_material_batch_lot, tare_weight, first_started_at, version,
                created_at, updated_at
            ) VALUES (
                1, 'LEGACY-25450', 'running', 1, 1,
                1, '2026-07-20', '2026-07-26', 'Legacy customer', 'Sofia',
                'Film', '500', 'kg', '20', 'rolls',
                'Roll', 'LDPE', '50', '600/0.050', 'Preserve me',
                'yes', 'Center', 'Printing', 'Corona', 'LDPE; A | 100%', 'Pallet',
                'LDPE actual', 'Brand X', 'LOT-7', 1.25,
                '2026-07-20 07:00:00', 7,
                '2026-07-20 06:10:00', '2026-07-20 08:00:00'
            );

            INSERT INTO cards (
                id, order_number, status, import_batch_id,
                quantity_1, unit_1, quantity_2, unit_2,
                extrusion_flag, version, created_at, updated_at
            ) VALUES (
                2, 'LEGACY-25451', 'imported', 1,
                '600', 'kg', '30', 'rolls',
                'yes', 3, '2026-07-20 06:20:00', '2026-07-20 06:20:00'
            );

            INSERT INTO card_import_sources (
                card_id, import_batch_id, order_number, order_date,
                delivery_date, customer, city, product_type,
                quantity_1, unit_1, quantity_2, unit_2,
                product_form, material, size_thickness, notes,
                extrusion_flag, extrusion_folding, extrusion_next_operation,
                extrusion_treatment, raw_material_a, packaging_method,
                created_at, updated_at
            ) VALUES (
                1, 1, 'LEGACY-25450', '2026-07-20',
                '2026-07-26', 'Legacy source customer', 'Sofia', 'Film',
                '510', 'kg', '21', 'rolls',
                'Roll', 'LDPE', '600/0.050', 'Original import',
                'yes', 'Center', 'Printing',
                'Corona', 'LDPE; A | 100%', 'Pallet',
                '2026-07-20 06:10:00', '2026-07-20 06:10:00'
            );

            INSERT INTO card_import_sources (
                card_id, import_batch_id, order_number,
                quantity_1, unit_1, quantity_2, unit_2,
                extrusion_flag, created_at, updated_at
            ) VALUES (
                2, 1, 'LEGACY-25451',
                '610', 'kg', '31', 'rolls',
                'yes', '2026-07-20 06:20:00', '2026-07-20 06:20:00'
            );

            INSERT INTO roll_entries (
                id, card_id, order_number, roll_number, gross_weight,
                tare_weight, net_weight, created_at, updated_at
            ) VALUES (
                1, 1, 'LEGACY-25450', 1, 50.25,
                1.25, 49.0, '2026-07-20 07:30:00', '2026-07-20 07:30:00'
            );

            INSERT INTO recipe_actual_entries (
                id, card_id, component_key, component_label, planned_material,
                actual_material_used, batch_lot, created_at, updated_at
            ) VALUES (
                1, 1, 'raw_material_a', 'Raw material A', 'LDPE',
                'LDPE actual', 'LOT-7',
                '2026-07-20 07:10:00', '2026-07-20 07:10:00'
            );

            INSERT INTO recipe_components (
                id, card_id, component_key, source_text, material_category,
                planned_material, recipe_percent, created_at, updated_at
            ) VALUES (
                1, 1, 'raw_material_a', 'LDPE; A | 100%', 'raw_material',
                'LDPE', 100, '2026-07-20 07:10:00', '2026-07-20 07:10:00'
            );

            INSERT INTO production_time_segments (
                id, card_id, started_at, ended_at, end_reason,
                created_at, updated_at
            ) VALUES (
                1, 1, '2026-07-20 07:00:00', NULL, NULL,
                '2026-07-20 07:00:00', '2026-07-20 07:00:00'
            );
            """
        )


def add_existing_final_values(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        for table_name in ("cards", "card_import_sources"):
            for column_name in FINAL_IMPORT_COLUMNS:
                connection.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} TEXT"
                )
        connection.execute(
            """
            UPDATE cards
            SET ordered_gross_kg = '900',
                ordered_rolls = '90',
                ordered_meters = '19000',
                ordered_units = '49000',
                printing_sequence = '2',
                extrusion_sequence = '1',
                rewinding_slitting_sequence = '3',
                confection_sequence = '4'
            WHERE id = 1
            """
        )
        connection.execute(
            """
            UPDATE card_import_sources
            SET ordered_gross_kg = '910',
                ordered_rolls = '91',
                ordered_meters = '19100',
                ordered_units = '49100',
                printing_sequence = '2',
                extrusion_sequence = '1',
                rewinding_slitting_sequence = '3',
                confection_sequence = '4'
            WHERE card_id = 1
            """
        )


def add_partially_upgraded_shift_schema(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE terminal_configuration (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                shift_count INTEGER NOT NULL DEFAULT 4
                    CHECK (typeof(shift_count) = 'integer' AND shift_count >= 1),
                version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE shift_occurrences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_number INTEGER NOT NULL
                    CHECK (typeof(shift_number) = 'integer' AND shift_number >= 1),
                started_at TEXT NOT NULL,
                ended_at TEXT,
                version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK (ended_at IS NULL OR ended_at >= started_at)
            );

            INSERT INTO terminal_configuration (id, shift_count, version, updated_at)
            VALUES (1, 6, 3, '2026-07-20 06:00:00');
            INSERT INTO shift_occurrences (
                id, shift_number, started_at, ended_at, version, created_at, updated_at
            ) VALUES (
                1, 2, '2026-07-20 06:00:00', '2026-07-20 14:00:00', 4,
                '2026-07-20 06:00:00', '2026-07-20 14:00:00'
            );
            ALTER TABLE roll_entries
            ADD COLUMN shift_occurrence_id INTEGER
                REFERENCES shift_occurrences(id) ON DELETE RESTRICT;
            UPDATE roll_entries SET shift_occurrence_id = 1 WHERE id = 1;
            """
        )


def configure_database(
    monkeypatch: pytest.MonkeyPatch,
    database_path: Path,
) -> None:
    monkeypatch.setattr(db, "DATA_DIR", database_path.parent)
    monkeypatch.setattr(db, "DB_PATH", database_path)


def read_row(
    connection: sqlite3.Connection,
    table_name: str,
    key_column: str,
    key_value: int,
) -> dict[str, object]:
    row = connection.execute(
        f"SELECT * FROM {table_name} WHERE {key_column} = ?",
        (key_value,),
    ).fetchone()
    assert row is not None
    return dict(row)


def test_m002_adds_shift_schema_without_attributing_legacy_rolls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    create_legacy_database(database_path)
    configure_database(monkeypatch, database_path)

    db.init_db()

    with db.connect() as connection:
        migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        card = read_row(connection, "cards", "id", 1)
        source = read_row(connection, "card_import_sources", "card_id", 1)
        roll = read_row(connection, "roll_entries", "id", 1)
        actual = read_row(connection, "recipe_actual_entries", "id", 1)
        segment = read_row(connection, "production_time_segments", "id", 1)
        imported_card = read_row(connection, "cards", "id", 2)
        imported_source = read_row(
            connection,
            "card_import_sources",
            "card_id",
            2,
        )
        first_snapshot = {
            table_name: [tuple(row) for row in connection.execute(query).fetchall()]
            for table_name, query in {
                "cards": "SELECT * FROM cards ORDER BY id",
                "card_import_sources": (
                    "SELECT * FROM card_import_sources ORDER BY card_id"
                ),
                "roll_entries": "SELECT * FROM roll_entries ORDER BY id",
                "recipe_actual_entries": (
                    "SELECT * FROM recipe_actual_entries ORDER BY id"
                ),
                "recipe_components": (
                    "SELECT * FROM recipe_components ORDER BY id"
                ),
                "production_time_segments": (
                    "SELECT * FROM production_time_segments ORDER BY id"
                ),
                "machines": "SELECT * FROM machines ORDER BY id",
            }.items()
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        configuration = dict(
            connection.execute(
                "SELECT id, shift_count, version "
                "FROM terminal_configuration WHERE id = 1"
            ).fetchone()
        )

    db.init_db()
    with db.connect() as connection:
        second_snapshot = {
            table_name: [tuple(row) for row in connection.execute(query).fetchall()]
            for table_name, query in {
                "cards": "SELECT * FROM cards ORDER BY id",
                "card_import_sources": (
                    "SELECT * FROM card_import_sources ORDER BY card_id"
                ),
                "roll_entries": "SELECT * FROM roll_entries ORDER BY id",
                "recipe_actual_entries": (
                    "SELECT * FROM recipe_actual_entries ORDER BY id"
                ),
                "recipe_components": (
                    "SELECT * FROM recipe_components ORDER BY id"
                ),
                "production_time_segments": (
                    "SELECT * FROM production_time_segments ORDER BY id"
                ),
                "machines": "SELECT * FROM machines ORDER BY id",
            }.items()
        }
        second_migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert [(row["version"], row["name"]) for row in migration_rows] == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
    ]
    assert configuration == {"id": 1, "shift_count": 4, "version": 1}
    assert roll["shift_occurrence_id"] is None
    assert [card[column] for column in FINAL_IMPORT_COLUMNS] == [None] * 8
    assert [source[column] for column in FINAL_IMPORT_COLUMNS] == [None] * 8
    assert [imported_card[column] for column in FINAL_IMPORT_COLUMNS] == [None] * 8
    assert [imported_source[column] for column in FINAL_IMPORT_COLUMNS] == [None] * 8
    assert [card[column] for column in (
        "quantity_1",
        "unit_1",
        "quantity_2",
        "unit_2",
    )] == [
        "500",
        "kg",
        "20",
        "rolls",
    ]
    assert [source[column] for column in (
        "quantity_1",
        "unit_1",
        "quantity_2",
        "unit_2",
    )] == [
        "510",
        "kg",
        "21",
        "rolls",
    ]
    assert [imported_card[column] for column in (
        "quantity_1",
        "unit_1",
        "quantity_2",
        "unit_2",
    )] == [
        "600",
        "kg",
        "30",
        "rolls",
    ]
    assert [imported_source[column] for column in (
        "quantity_1",
        "unit_1",
        "quantity_2",
        "unit_2",
    )] == [
        "610",
        "kg",
        "31",
        "rolls",
    ]
    assert imported_card["status"] == "imported"
    assert imported_card["version"] == 3
    assert card["extrusion_flag"] == "yes"
    assert source["extrusion_flag"] == "yes"
    assert {
        "status": card["status"],
        "machine_id": card["machine_id"],
        "machine_sequence": card["machine_sequence"],
        "tare_weight": card["tare_weight"],
        "actual_raw_material_used": card["actual_raw_material_used"],
        "raw_material_brand_grade": card["raw_material_brand_grade"],
        "raw_material_batch_lot": card["raw_material_batch_lot"],
        "version": card["version"],
        "created_at": card["created_at"],
        "updated_at": card["updated_at"],
    } == {
        "status": "running",
        "machine_id": 1,
        "machine_sequence": 1,
        "tare_weight": 1.25,
        "actual_raw_material_used": "LDPE actual",
        "raw_material_brand_grade": "Brand X",
        "raw_material_batch_lot": "LOT-7",
        "version": 7,
        "created_at": "2026-07-20 06:10:00",
        "updated_at": "2026-07-20 08:00:00",
    }
    assert {
        "gross_weight": roll["gross_weight"],
        "tare_weight": roll["tare_weight"],
        "net_weight": roll["net_weight"],
        "updated_at": roll["updated_at"],
    } == {
        "gross_weight": 50.25,
        "tare_weight": 1.25,
        "net_weight": 49,
        "updated_at": "2026-07-20 07:30:00",
    }
    assert actual["actual_material_used"] == "LDPE actual"
    assert actual["batch_lot"] == "LOT-7"
    assert segment["started_at"] == "2026-07-20 07:00:00"
    assert segment["ended_at"] is None
    assert integrity == "ok"
    assert foreign_key_violations == []
    assert second_snapshot == first_snapshot
    assert second_migration_rows == migration_rows


def test_m001_keeps_existing_final_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "partly-migrated.sqlite3"
    create_legacy_database(database_path)
    add_existing_final_values(database_path)
    configure_database(monkeypatch, database_path)

    db.init_db()

    with db.connect() as connection:
        card = read_row(connection, "cards", "id", 1)
        source = read_row(connection, "card_import_sources", "card_id", 1)

    assert [card[column] for column in FINAL_IMPORT_COLUMNS] == [
        "900",
        "90",
        "19000",
        "49000",
        "2",
        "1",
        "3",
        "4",
    ]
    assert [source[column] for column in FINAL_IMPORT_COLUMNS] == [
        "910",
        "91",
        "19100",
        "49100",
        "2",
        "1",
        "3",
        "4",
    ]


def test_m002_preserves_existing_attribution_in_partially_upgraded_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "partly-upgraded.sqlite3"
    create_legacy_database(database_path)
    add_existing_final_values(database_path)
    add_partially_upgraded_shift_schema(database_path)
    configure_database(monkeypatch, database_path)

    db.init_db()

    with db.connect() as connection:
        configuration = dict(
            connection.execute("SELECT * FROM terminal_configuration WHERE id = 1").fetchone()
        )
        roll = read_row(connection, "roll_entries", "id", 1)
        occurrence = read_row(connection, "shift_occurrences", "id", 1)
        migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    assert configuration["shift_count"] == 6
    assert configuration["version"] == 3
    assert configuration["updated_at"] == "2026-07-20 06:00:00"
    assert roll["shift_occurrence_id"] == 1
    assert occurrence["shift_number"] == 2
    assert occurrence["version"] == 4
    assert [(row["version"], row["name"]) for row in migration_rows] == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
    ]
    assert integrity == "ok"
    assert foreign_key_violations == []


def test_fresh_database_records_m001_and_m002_once_with_schema_parity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "fresh.sqlite3"
    configure_database(monkeypatch, database_path)

    db.init_db()
    with db.connect() as connection:
        first_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        configuration = dict(
            connection.execute(
                "SELECT id, shift_count, version "
                "FROM terminal_configuration WHERE id = 1"
            ).fetchone()
        )
        connection.execute("BEGIN")
        assert migrations.apply_pending_migrations(connection) == ()
        card_id = connection.execute(
            """
            INSERT INTO cards (
                order_number, ordered_gross_kg, ordered_rolls,
                ordered_meters, ordered_units, printing_sequence,
                extrusion_sequence, rewinding_slitting_sequence,
                confection_sequence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("FINAL-25452", "700", "40", "17000", "60000", "2", "1", "3", "4"),
        ).lastrowid
        connection.execute(
            """
            INSERT INTO card_import_sources (
                card_id, order_number, ordered_gross_kg, ordered_rolls,
                ordered_meters, ordered_units, printing_sequence,
                extrusion_sequence, rewinding_slitting_sequence,
                confection_sequence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                "FINAL-25452",
                "710",
                "41",
                "17100",
                "60100",
                "2",
                "1",
                "3",
                "4",
            ),
        )
    db.init_db()

    with db.connect() as connection:
        second_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        card_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(cards)").fetchall()
        }
        source_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(card_import_sources)"
            ).fetchall()
        }
        roll_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(roll_entries)").fetchall()
        }
        shift_tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        card = read_row(connection, "cards", "id", int(card_id))
        source = read_row(
            connection,
            "card_import_sources",
            "card_id",
            int(card_id),
        )

    assert [(row["version"], row["name"]) for row in first_rows] == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
    ]
    assert [(row["version"], row["name"]) for row in second_rows] == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
    ]
    assert configuration == {"id": 1, "shift_count": 4, "version": 1}
    assert set(FINAL_IMPORT_COLUMNS).issubset(card_columns)
    assert set(FINAL_IMPORT_COLUMNS).issubset(source_columns)
    assert "shift_occurrence_id" in roll_columns
    assert {"terminal_configuration", "shift_occurrences"}.issubset(shift_tables)
    assert [card[column] for column in FINAL_IMPORT_COLUMNS] == [
        "700",
        "40",
        "17000",
        "60000",
        "2",
        "1",
        "3",
        "4",
    ]
    assert [source[column] for column in FINAL_IMPORT_COLUMNS] == [
        "710",
        "41",
        "17100",
        "60100",
        "2",
        "1",
        "3",
        "4",
    ]


def test_m002_enforces_single_active_shift_and_roll_foreign_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "constraints.sqlite3"
    configure_database(monkeypatch, database_path)
    db.init_db()

    with db.connect() as connection:
        card_id = connection.execute(
            "INSERT INTO cards (order_number) VALUES ('SHIFT-25452')"
        ).lastrowid
        connection.execute(
            "INSERT INTO shift_occurrences (shift_number, started_at) "
            "VALUES (1, '2026-07-25 06:00:00')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO shift_occurrences (shift_number, started_at) "
                "VALUES (2, '2026-07-25 14:00:00')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO roll_entries ("
                "card_id, order_number, roll_number, shift_occurrence_id"
                ") VALUES (?, 'SHIFT-25452', 1, 999)",
                (card_id,),
            )
        connection.execute(
            "INSERT INTO roll_entries ("
            "card_id, order_number, roll_number, shift_occurrence_id"
            ") VALUES (?, 'SHIFT-25452', 1, 1)",
            (card_id,),
        )


def test_m002_failure_rolls_back_schema_and_migration_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m002-failure.sqlite3"
    create_legacy_database(database_path)
    configure_database(monkeypatch, database_path)
    monkeypatch.setattr(migrations, "SHIFT_COMPLETED_INDEX_SQL", "CREATE INDEX")

    with pytest.raises(sqlite3.OperationalError):
        db.init_db()

    with db.connect() as connection:
        table_names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        roll_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(roll_entries)"
            ).fetchall()
        }

    assert "terminal_configuration" not in table_names
    assert "shift_occurrences" not in table_names
    assert "schema_migrations" not in table_names
    assert "shift_occurrence_id" not in roll_columns


@pytest.mark.parametrize(
    "registry",
    [
        (
            migrations.Migration(1, "one", lambda connection: None),
            migrations.Migration(1, "duplicate", lambda connection: None),
        ),
        (
            migrations.Migration(2, "two", lambda connection: None),
            migrations.Migration(1, "one", lambda connection: None),
        ),
    ],
)
def test_runner_rejects_invalid_registry_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    registry: tuple[migrations.Migration, ...],
) -> None:
    database_path = tmp_path / "invalid-registry.sqlite3"
    monkeypatch.setattr(migrations, "MIGRATIONS", registry)

    with sqlite3.connect(database_path) as connection:
        with pytest.raises(ValueError, match="strictly increasing"):
            migrations.apply_pending_migrations(connection)


def test_runner_rejects_recorded_migrations_that_are_not_a_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "migration-gap.sqlite3"
    registry = (
        migrations.Migration(1, "one", lambda connection: None),
        migrations.Migration(2, "two", lambda connection: None),
    )
    monkeypatch.setattr(migrations, "MIGRATIONS", registry)

    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO schema_migrations (version, name) VALUES (2, 'two');
            """
        )
        connection.execute("BEGIN")

        with pytest.raises(RuntimeError, match="contiguous prefix"):
            migrations.apply_pending_migrations(connection)

        rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert rows == [(2, "two")]


def test_runner_requires_a_caller_owned_transaction(tmp_path: Path) -> None:
    database_path = tmp_path / "no-transaction.sqlite3"

    with sqlite3.connect(database_path) as connection:
        assert connection.in_transaction is False
        with pytest.raises(RuntimeError, match="active caller transaction"):
            migrations.apply_pending_migrations(connection)


def test_successful_runner_changes_remain_rollbackable_by_caller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "caller-rollback.sqlite3"

    def create_probe(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE migrated_probe (value TEXT NOT NULL)")
        connection.execute("INSERT INTO migrated_probe VALUES ('applied')")

    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        (migrations.Migration(1, "create_probe", create_probe),),
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute("BEGIN")
        assert migrations.apply_pending_migrations(connection) == (1,)
        assert connection.in_transaction is True
        connection.rollback()

        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert "migrated_probe" not in table_names
    assert "schema_migrations" not in table_names


def test_runner_failure_rolls_back_data_and_migration_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "failed.sqlite3"

    def fail_after_write(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE partial_migration (value TEXT NOT NULL)")
        connection.execute("INSERT INTO migration_probe (value) VALUES ('partial')")
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(
        migrations,
        "MIGRATIONS",
        (migrations.Migration(1, "failing_migration", fail_after_write),),
    )

    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE migration_probe (value TEXT NOT NULL);
            """
        )

        connection.execute("BEGIN")
        with pytest.raises(RuntimeError, match="injected migration failure"):
            with connection:
                migrations.apply_pending_migrations(connection)

        assert connection.execute(
            "SELECT COUNT(*) FROM migration_probe"
        ).fetchone()[0] == 0
        remaining_migration_tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name IN ('schema_migrations', 'partial_migration')
                """
            ).fetchall()
        }
        assert remaining_migration_tables == set()
    finally:
        connection.close()
