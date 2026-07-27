from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import db, migrations
from app.schema import cards_table_sql


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


def add_partially_upgraded_shift_schema(
    database_path: Path,
    *,
    include_roll_shift_foreign_key: bool = True,
) -> None:
    roll_shift_definition = (
        "INTEGER REFERENCES shift_occurrences(id) ON DELETE RESTRICT"
        if include_roll_shift_foreign_key
        else "INTEGER"
    )
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            f"""
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
            ADD COLUMN shift_occurrence_id {roll_shift_definition};
            UPDATE roll_entries SET shift_occurrence_id = 1 WHERE id = 1;
            """
        )


PALLET_VALUE_CHECK = (
    "CHECK ({column} IS NULL OR "
    "(typeof({column}) = 'integer' AND {column} BETWEEN 1 AND 999))"
)


def add_recorded_m001_and_m002(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO schema_migrations (version, name)
            VALUES (1, 'shift_manager_import_fields');
            INSERT INTO schema_migrations (version, name)
            VALUES (2, 'shift_management');
            """
        )


def add_recorded_m003(database_path: Path) -> None:
    add_recorded_m001_and_m002(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO schema_migrations (version, name) "
            "VALUES (3, 'roll_pallet_assignment')"
        )


def add_partially_upgraded_rewinding_schema(
    database_path: Path,
    *,
    count_definition: str = (
        "INTEGER CHECK (rewinding_roll_count IS NULL OR "
        "(typeof(rewinding_roll_count) = 'integer' "
        "AND rewinding_roll_count BETWEEN 1 AND 999))"
    ),
    final_shift_definition: str = (
        "INTEGER REFERENCES shift_occurrences(id) ON DELETE RESTRICT"
    ),
) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "ALTER TABLE cards ADD COLUMN rewinding_roll_count "
            f"{count_definition}"
        )
        connection.execute(
            "ALTER TABLE cards ADD COLUMN final_extrusion_shift_occurrence_id "
            f"{final_shift_definition}"
        )


def add_recorded_m004(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO schema_migrations (version, name) "
            "VALUES (4, 'rewinding_return_workflow')"
        )


def add_partially_upgraded_pallet_schema(
    database_path: Path,
    *,
    card_definition: str,
    roll_definition: str,
) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "ALTER TABLE cards ADD COLUMN current_pallet_number "
            f"{card_definition}"
        )
        connection.execute(
            "ALTER TABLE roll_entries ADD COLUMN pallet_number "
            f"{roll_definition}"
        )


def create_recorded_m003_database(database_path: Path) -> None:
    create_legacy_database(database_path)
    add_existing_final_values(database_path)
    add_partially_upgraded_shift_schema(database_path)
    add_partially_upgraded_pallet_schema(
        database_path,
        card_definition=(
            "INTEGER " + PALLET_VALUE_CHECK.format(column="current_pallet_number")
        ),
        roll_definition=(
            "INTEGER " + PALLET_VALUE_CHECK.format(column="pallet_number")
        ),
    )
    add_recorded_m003(database_path)


def clear_legacy_production_rows(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        for table_name in (
            "production_time_segments",
            "recipe_actual_entries",
            "recipe_components",
            "roll_entries",
            "card_import_sources",
            "cards",
        ):
            connection.execute(f"DELETE FROM {table_name}")


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


PRESERVATION_TABLES = (
    "cards",
    "card_import_sources",
    "roll_entries",
    "recipe_actual_entries",
    "recipe_components",
    "production_time_segments",
    "machines",
)
PRESERVATION_ORDER_COLUMNS = {
    "card_import_sources": "card_id",
}


def capture_preservation_snapshot(
    connection: sqlite3.Connection,
    columns_by_table: dict[str, tuple[str, ...]] | None = None,
    legacy_machine_ids: tuple[int, ...] | None = None,
) -> tuple[dict[str, list[tuple[object, ...]]], dict[str, tuple[str, ...]]]:
    if columns_by_table is None:
        columns_by_table = {
            table_name: tuple(
                row["name"]
                for row in connection.execute(
                    f"PRAGMA table_info({table_name})"
                ).fetchall()
            )
            for table_name in PRESERVATION_TABLES
        }

    snapshot: dict[str, list[tuple[object, ...]]] = {}
    for table_name, columns in columns_by_table.items():
        order_column = PRESERVATION_ORDER_COLUMNS.get(table_name, "id")
        query = "SELECT " + ", ".join(columns) + f" FROM {table_name}"
        parameters: tuple[int, ...] = ()
        if table_name == "machines" and legacy_machine_ids is not None:
            placeholders = ", ".join("?" for _ in legacy_machine_ids)
            query += f" WHERE id IN ({placeholders})"
            parameters = legacy_machine_ids
        snapshot[table_name] = [
            tuple(row)
            for row in connection.execute(
                f"{query} ORDER BY {order_column}",
                parameters,
            ).fetchall()
        ]
    return snapshot, columns_by_table


def capture_m003_preservation_snapshot(
    connection: sqlite3.Connection,
    *,
    legacy_machine_ids: tuple[int, ...] | None = None,
) -> dict[str, list[tuple[object, ...]]]:
    table_names = (
        "cards",
        "card_import_sources",
        "roll_entries",
        "recipe_actual_entries",
        "recipe_components",
        "production_time_segments",
        "machines",
        "terminal_configuration",
        "shift_occurrences",
        "schema_migrations",
    )
    order_columns = {
        "card_import_sources": "card_id",
        "schema_migrations": "version",
    }
    snapshot: dict[str, list[tuple[object, ...]]] = {}
    for table_name in table_names:
        column_names = [
            row["name"]
            for row in connection.execute(
                f"PRAGMA table_info({table_name})"
            ).fetchall()
            if row["name"] not in {
                "current_pallet_number",
                "pallet_number",
                "rewinding_roll_count",
                "final_extrusion_shift_occurrence_id",
            }
        ]
        columns = tuple(sorted(column_names) if table_name == "cards" else column_names)
        query = (
            "SELECT " + ", ".join(columns) + f" FROM {table_name} "
        )
        parameters: tuple[int, ...] = ()
        if table_name == "machines" and legacy_machine_ids is not None:
            query += "WHERE id IN (" + ", ".join("?" for _ in legacy_machine_ids) + ") "
            parameters = legacy_machine_ids
        query += f"ORDER BY {order_columns.get(table_name, 'id')}"
        snapshot[table_name] = [
            tuple(row)
            for row in connection.execute(
                query,
                parameters,
            ).fetchall()
        ]
    return snapshot


def capture_m004_preservation_snapshot(
    connection: sqlite3.Connection,
    *,
    legacy_machine_ids: tuple[int, ...] | None = None,
) -> dict[str, list[tuple[object, ...]]]:
    table_names = (
        "cards",
        "card_import_sources",
        "roll_entries",
        "recipe_actual_entries",
        "recipe_components",
        "production_time_segments",
        "machines",
        "terminal_configuration",
        "shift_occurrences",
        "schema_migrations",
    )
    order_columns = {
        "card_import_sources": "card_id",
        "schema_migrations": "version",
    }
    snapshot: dict[str, list[tuple[object, ...]]] = {}
    for table_name in table_names:
        column_names = [
            row["name"]
            for row in connection.execute(
                f"PRAGMA table_info({table_name})"
            ).fetchall()
            if row["name"] not in {
                "rewinding_roll_count",
                "final_extrusion_shift_occurrence_id",
            }
        ]
        columns = tuple(sorted(column_names) if table_name == "cards" else column_names)
        query = "SELECT " + ", ".join(columns) + f" FROM {table_name} "
        parameters: tuple[int, ...] = ()
        if table_name == "machines" and legacy_machine_ids is not None:
            query += "WHERE id IN (" + ", ".join("?" for _ in legacy_machine_ids) + ") "
            parameters = legacy_machine_ids
        query += f"ORDER BY {order_columns.get(table_name, 'id')}"
        snapshot[table_name] = [
            tuple(row)
            for row in connection.execute(
                query,
                parameters,
            ).fetchall()
        ]
    return snapshot


def test_m002_adds_shift_schema_without_attributing_legacy_rolls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    create_legacy_database(database_path)
    configure_database(monkeypatch, database_path)

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        pre_migration_snapshot, legacy_columns = capture_preservation_snapshot(
            connection
        )
        legacy_machine_ids = tuple(
            int(row[0]) for row in pre_migration_snapshot["machines"]
        )

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
        first_snapshot, _ = capture_preservation_snapshot(
            connection,
            legacy_columns,
            legacy_machine_ids,
        )
        machines = connection.execute(
            "SELECT id, name, is_operational, display_order FROM machines ORDER BY id"
        ).fetchall()
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
        second_snapshot, _ = capture_preservation_snapshot(
            connection,
            legacy_columns,
            legacy_machine_ids,
        )
        second_migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert [(row["version"], row["name"]) for row in migration_rows] == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
        (3, "roll_pallet_assignment"),
        (4, "rewinding_return_workflow"),
    ]
    assert configuration == {"id": 1, "shift_count": 4, "version": 1}
    assert roll["shift_occurrence_id"] is None
    assert card["rewinding_roll_count"] is None
    assert card["final_extrusion_shift_occurrence_id"] is None
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
    assert first_snapshot == pre_migration_snapshot
    assert [tuple(machine) for machine in machines] == [
        (1, "Legacy machine 1", 1, 1),
        (2, "Machine 2", 1, 2),
        (3, "Machine 3", 1, 3),
        (4, "Machine 4", 1, 4),
    ]
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
        (3, "roll_pallet_assignment"),
        (4, "rewinding_return_workflow"),
    ]
    assert integrity == "ok"
    assert foreign_key_violations == []


def test_m002_rejects_partial_roll_shift_column_without_foreign_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "partly-upgraded-without-roll-fk.sqlite3"
    create_legacy_database(database_path)
    add_partially_upgraded_shift_schema(
        database_path,
        include_roll_shift_foreign_key=False,
    )
    configure_database(monkeypatch, database_path)

    with pytest.raises(
        RuntimeError,
        match="roll_entries.shift_occurrence_id.*foreign key",
    ):
        db.init_db()

    with sqlite3.connect(database_path) as connection:
        attribution = connection.execute(
            "SELECT shift_occurrence_id FROM roll_entries WHERE id = 1"
        ).fetchone()[0]
        roll_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(roll_entries)"
        ).fetchall()
        migration_table = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'schema_migrations'
            """
        ).fetchone()

    assert attribution == 1
    assert all(row[2] != "shift_occurrences" for row in roll_foreign_keys)
    assert migration_table is None


def test_init_rejects_recorded_m002_without_roll_shift_foreign_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "recorded-m002-without-roll-fk.sqlite3"
    create_legacy_database(database_path)
    add_existing_final_values(database_path)
    add_partially_upgraded_shift_schema(
        database_path,
        include_roll_shift_foreign_key=False,
    )
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO schema_migrations (version, name)
            VALUES (1, 'shift_manager_import_fields');
            INSERT INTO schema_migrations (version, name)
            VALUES (2, 'shift_management');
            """
        )
    configure_database(monkeypatch, database_path)

    with pytest.raises(
        RuntimeError,
        match="roll_entries.shift_occurrence_id.*foreign key",
    ):
        db.init_db()


def test_m003_adds_nullable_pallet_columns_without_backfilling_legacy_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m003-legacy.sqlite3"
    create_legacy_database(database_path)
    add_existing_final_values(database_path)
    add_partially_upgraded_shift_schema(database_path)
    add_recorded_m001_and_m002(database_path)
    configure_database(monkeypatch, database_path)

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        before_snapshot = capture_m003_preservation_snapshot(connection)
    legacy_machine_ids = tuple(
        int(row[0]) for row in before_snapshot["machines"]
    )
    prior_migration_rows = before_snapshot.pop("schema_migrations")

    db.init_db()

    with db.connect() as connection:
        migration_rows = [
            dict(row)
            for row in connection.execute(
                "SELECT version, name FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]
        legacy_card = read_row(connection, "cards", "id", 1)
        legacy_roll = read_row(connection, "roll_entries", "id", 1)
        first_snapshot = capture_m003_preservation_snapshot(
            connection,
            legacy_machine_ids=legacy_machine_ids,
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    db.init_db()

    with db.connect() as connection:
        second_snapshot = capture_m003_preservation_snapshot(
            connection,
            legacy_machine_ids=legacy_machine_ids,
        )

    first_migration_rows = first_snapshot.pop("schema_migrations")
    second_migration_rows = second_snapshot.pop("schema_migrations")
    assert first_snapshot == before_snapshot
    assert second_snapshot == first_snapshot
    assert first_migration_rows[:-2] == prior_migration_rows
    assert second_migration_rows == first_migration_rows
    assert legacy_card["current_pallet_number"] is None
    assert legacy_roll["pallet_number"] is None
    assert migration_rows[-2:] == [
        {"version": 3, "name": "roll_pallet_assignment"},
        {"version": 4, "name": "rewinding_return_workflow"},
    ]
    assert integrity == "ok"
    assert foreign_key_violations == []


def test_m003_accepts_a_valid_partially_upgraded_schema_and_preserves_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m003-partially-upgraded.sqlite3"
    create_legacy_database(database_path)
    add_existing_final_values(database_path)
    add_partially_upgraded_shift_schema(database_path)
    add_recorded_m001_and_m002(database_path)
    add_partially_upgraded_pallet_schema(
        database_path,
        card_definition=(
            "INTEGER " + PALLET_VALUE_CHECK.format(column="current_pallet_number")
        ),
        roll_definition=(
            "INTEGER " + PALLET_VALUE_CHECK.format(column="pallet_number")
        ),
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE cards SET current_pallet_number = 17 WHERE id = 1")
        connection.execute("UPDATE roll_entries SET pallet_number = 18 WHERE id = 1")
    configure_database(monkeypatch, database_path)

    db.init_db()

    with db.connect() as connection:
        first_card = read_row(connection, "cards", "id", 1)
        first_roll = read_row(connection, "roll_entries", "id", 1)
        first_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        first_snapshot = capture_m003_preservation_snapshot(connection)

    db.init_db()

    with db.connect() as connection:
        second_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        second_snapshot = capture_m003_preservation_snapshot(connection)

    assert first_card["current_pallet_number"] == 17
    assert first_roll["pallet_number"] == 18
    assert [(row["version"], row["name"]) for row in first_rows] == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
        (3, "roll_pallet_assignment"),
        (4, "rewinding_return_workflow"),
    ]
    assert second_rows == first_rows
    assert second_snapshot == first_snapshot


def test_m003_rejects_partial_pallet_columns_without_required_constraints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m003-partial-constraints.sqlite3"
    create_legacy_database(database_path)
    add_existing_final_values(database_path)
    add_partially_upgraded_shift_schema(database_path)
    add_recorded_m001_and_m002(database_path)
    add_partially_upgraded_pallet_schema(
        database_path,
        card_definition="INTEGER",
        roll_definition="INTEGER",
    )
    configure_database(monkeypatch, database_path)

    with pytest.raises(RuntimeError, match="required pallet constraint"):
        db.init_db()

    with sqlite3.connect(database_path) as connection:
        migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert migration_rows == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
    ]


def test_init_rejects_recorded_m003_with_malformed_pallet_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "recorded-m003-malformed.sqlite3"
    create_legacy_database(database_path)
    add_existing_final_values(database_path)
    add_partially_upgraded_shift_schema(database_path)
    add_recorded_m001_and_m002(database_path)
    add_partially_upgraded_pallet_schema(
        database_path,
        card_definition="INTEGER",
        roll_definition="INTEGER",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO schema_migrations (version, name) "
            "VALUES (3, 'roll_pallet_assignment')"
        )
    configure_database(monkeypatch, database_path)

    with pytest.raises(RuntimeError, match="required pallet constraint"):
        db.init_db()


@pytest.mark.parametrize(
    (
        "card_definition",
        "roll_definition",
        "clear_rows",
    ),
    [
        (
            "INTEGER NOT NULL "
            + PALLET_VALUE_CHECK.format(column="current_pallet_number"),
            "INTEGER NOT NULL " + PALLET_VALUE_CHECK.format(column="pallet_number"),
            True,
        ),
        (
            "INTEGER DEFAULT 1 "
            + PALLET_VALUE_CHECK.format(column="current_pallet_number"),
            "INTEGER DEFAULT 1 " + PALLET_VALUE_CHECK.format(column="pallet_number"),
            False,
        ),
        (
            "INTEGER /* CHECK (current_pallet_number IS NULL OR "
            "(typeof(current_pallet_number) = 'integer' AND "
            "current_pallet_number BETWEEN 1 AND 999)) */",
            "INTEGER /* CHECK (pallet_number IS NULL OR "
            "(typeof(pallet_number) = 'integer' AND pallet_number BETWEEN 1 "
            "AND 999)) */",
            False,
        ),
    ],
    ids=("not-null", "default", "comment-spoofed"),
)
def test_m003_rejects_partial_pallet_columns_that_violate_nullable_defaultless_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    card_definition: str,
    roll_definition: str,
    clear_rows: bool,
) -> None:
    database_path = tmp_path / "m003-invalid-column-contract.sqlite3"
    create_legacy_database(database_path)
    add_existing_final_values(database_path)
    add_partially_upgraded_shift_schema(database_path)
    if clear_rows:
        clear_legacy_production_rows(database_path)
    add_recorded_m001_and_m002(database_path)
    add_partially_upgraded_pallet_schema(
        database_path,
        card_definition=card_definition,
        roll_definition=roll_definition,
    )
    configure_database(monkeypatch, database_path)

    with pytest.raises(RuntimeError, match="pallet"):
        db.init_db()

    with sqlite3.connect(database_path) as connection:
        migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert migration_rows == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
    ]


def test_m003_accepts_equivalent_nullable_pallet_constraints_and_preserves_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m003-equivalent-constraint.sqlite3"
    create_legacy_database(database_path)
    add_existing_final_values(database_path)
    add_partially_upgraded_shift_schema(database_path)
    add_recorded_m001_and_m002(database_path)
    add_partially_upgraded_pallet_schema(
        database_path,
        card_definition=(
            "INTEGER CHECK ((typeof(current_pallet_number) = 'integer' "
            "AND current_pallet_number BETWEEN 1 AND 999) OR "
            "current_pallet_number IS NULL)"
        ),
        roll_definition=(
            "INTEGER CHECK ((typeof(pallet_number) = 'integer' "
            "AND pallet_number BETWEEN 1 AND 999) OR pallet_number IS NULL)"
        ),
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE cards SET current_pallet_number = 17 WHERE id = 1")
        connection.execute("UPDATE roll_entries SET pallet_number = 18 WHERE id = 1")
    configure_database(monkeypatch, database_path)

    db.init_db()

    with db.connect() as connection:
        card = read_row(connection, "cards", "id", 1)
        roll = read_row(connection, "roll_entries", "id", 1)
        migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert card["current_pallet_number"] == 17
    assert roll["pallet_number"] == 18
    assert [(row["version"], row["name"]) for row in migration_rows] == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
        (3, "roll_pallet_assignment"),
        (4, "rewinding_return_workflow"),
    ]


@pytest.mark.parametrize(
    ("card_definition", "roll_definition"),
    [
        (
            "INTEGER CHECK (current_pallet_number IS NULL OR "
            "(typeof(current_pallet_number) = 'integer' AND "
            "current_pallet_number BETWEEN 1 AND 999 AND "
            "current_pallet_number <> 42))",
            "INTEGER CHECK (pallet_number IS NULL OR "
            "(typeof(pallet_number) = 'integer' AND pallet_number BETWEEN 1 "
            "AND 999 AND pallet_number <> 42))",
        ),
        (
            "INTEGER CHECK (current_pallet_number IS NULL OR "
            "(typeof(current_pallet_number) = 'integer' AND "
            "current_pallet_number BETWEEN 1 AND 999) OR "
            "current_pallet_number = 1001)",
            "INTEGER CHECK (pallet_number IS NULL OR "
            "(typeof(pallet_number) = 'integer' AND pallet_number BETWEEN 1 "
            "AND 999) OR pallet_number = 1001)",
        ),
        (
            "INTEGER CHECK (current_pallet_number IS NULL OR "
            "(typeof(current_pallet_number) = 'integer' AND "
            "current_pallet_number BETWEEN 1 AND 999)) "
            "CHECK (current_pallet_number <> 42)",
            "INTEGER CHECK (pallet_number IS NULL OR "
            "(typeof(pallet_number) = 'integer' AND pallet_number BETWEEN 1 "
            "AND 999)) CHECK (pallet_number <> 42)",
        ),
        (
            "INTEGER CHECK (current_pallet_number IS NULL OR "
            "(typeof(current_pallet_number) = 'integer' AND "
            "current_pallet_number BETWEEN 1 AND 999)) "
            "CHECK (\"current_pallet_number\" <> 42)",
            "INTEGER CHECK (pallet_number IS NULL OR "
            "(typeof(pallet_number) = 'integer' AND pallet_number BETWEEN 1 "
            "AND 999)) CHECK ([pallet_number] <> 42)",
        ),
    ],
    ids=(
        "excludes-valid-42",
        "permits-invalid-1001",
        "extra-target-column-check",
        "quoted-extra-target-column-check",
    ),
)
def test_m003_rejects_semantically_non_equivalent_pallet_constraints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    card_definition: str,
    roll_definition: str,
) -> None:
    database_path = tmp_path / "m003-non-equivalent-constraint.sqlite3"
    create_legacy_database(database_path)
    add_existing_final_values(database_path)
    add_partially_upgraded_shift_schema(database_path)
    add_recorded_m001_and_m002(database_path)
    add_partially_upgraded_pallet_schema(
        database_path,
        card_definition=card_definition,
        roll_definition=roll_definition,
    )
    configure_database(monkeypatch, database_path)

    with pytest.raises(RuntimeError, match="required pallet constraint"):
        db.init_db()

    with sqlite3.connect(database_path) as connection:
        migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert migration_rows == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
    ]


def test_fresh_database_records_migrations_once_with_schema_parity(
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
        card_column_rows = connection.execute("PRAGMA table_info(cards)").fetchall()
        card_columns = [row["name"] for row in card_column_rows]
        columns = {row["name"]: row for row in card_column_rows}
        source_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(card_import_sources)"
            ).fetchall()
        }
        roll_columns = [
            row["name"]
            for row in connection.execute("PRAGMA table_info(roll_entries)").fetchall()
        ]
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
        card_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(cards)"
        ).fetchall()
        foreign_keys_enabled = connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

    assert [(row["version"], row["name"]) for row in first_rows] == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
        (3, "roll_pallet_assignment"),
        (4, "rewinding_return_workflow"),
    ]
    assert [(row["version"], row["name"]) for row in second_rows] == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
        (3, "roll_pallet_assignment"),
        (4, "rewinding_return_workflow"),
    ]
    assert configuration == {"id": 1, "shift_count": 4, "version": 1}
    assert set(FINAL_IMPORT_COLUMNS).issubset(card_columns)
    assert columns["rewinding_roll_count"]["type"] == "INTEGER"
    assert columns["rewinding_roll_count"]["notnull"] == 0
    assert columns["rewinding_roll_count"]["dflt_value"] is None
    assert columns["final_extrusion_shift_occurrence_id"]["type"] == "INTEGER"
    assert columns["final_extrusion_shift_occurrence_id"]["notnull"] == 0
    assert columns["final_extrusion_shift_occurrence_id"]["dflt_value"] is None
    assert set(FINAL_IMPORT_COLUMNS).issubset(source_columns)
    assert "shift_occurrence_id" in roll_columns
    assert card_columns.index("current_pallet_number") == card_columns.index("tare_weight") + 1
    assert roll_columns.index("pallet_number") == roll_columns.index("net_weight") + 1
    assert {"terminal_configuration", "shift_occurrences"}.issubset(shift_tables)
    assert any(
        row["table"] == "shift_occurrences"
        and row["from"] == "final_extrusion_shift_occurrence_id"
        and row["to"] == "id"
        and row["on_delete"] == "RESTRICT"
        for row in card_foreign_keys
    )
    assert foreign_keys_enabled == 1
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


def test_m004_enforces_rewinding_count_status_and_final_shift_foreign_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m004-constraints.sqlite3"
    configure_database(monkeypatch, database_path)
    db.init_db()

    with db.connect() as connection:
        shift_id = connection.execute(
            "INSERT INTO shift_occurrences (shift_number, started_at) "
            "VALUES (1, '2026-07-26 06:00:00')"
        ).lastrowid
        card_id = connection.execute(
            "INSERT INTO cards (order_number) VALUES ('REWIND-VALID')"
        ).lastrowid
        connection.execute(
            "UPDATE cards SET rewinding_roll_count = 1 WHERE id = ?",
            (card_id,),
        )
        connection.execute(
            "UPDATE cards SET status = ? WHERE id = ?",
            ("awaiting_rewinding", card_id),
        )
        connection.execute(
            "UPDATE cards SET final_extrusion_shift_occurrence_id = ? WHERE id = ?",
            (shift_id, card_id),
        )

        for invalid_count in (0, -1, 1000, 1.5, "invalid"):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE cards SET rewinding_roll_count = ? WHERE id = ?",
                    (invalid_count, card_id),
                )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE cards SET status = 'unknown' WHERE id = ?",
                (card_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE cards SET final_extrusion_shift_occurrence_id = 999 "
                "WHERE id = ?",
                (card_id,),
            )

        stored = connection.execute(
            "SELECT status, rewinding_roll_count, "
            "final_extrusion_shift_occurrence_id FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()

    assert tuple(stored) == ("awaiting_rewinding", 1, shift_id)


def test_m004_upgrades_recorded_m003_without_inference_and_preserves_all_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m004-recorded-m003.sqlite3"
    create_recorded_m003_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            "ALTER TABLE cards ADD COLUMN legacy_extension VARCHAR(32)"
        )
        connection.execute(
            'ALTER TABLE cards ADD COLUMN legacy_unsafe "WEIRD; TYPE"'
        )
        connection.execute(
            "UPDATE cards SET current_pallet_number = 17, "
            "legacy_extension = 'preserved', legacy_unsafe = 'safe fallback' "
            "WHERE id = 1"
        )
        connection.execute("UPDATE roll_entries SET pallet_number = 18 WHERE id = 1")
        legacy_machine_ids = tuple(
            int(row[0])
            for row in connection.execute("SELECT id FROM machines ORDER BY id")
        )
        before = capture_m004_preservation_snapshot(
            connection,
            legacy_machine_ids=legacy_machine_ids,
        )
    prior_migrations = before.pop("schema_migrations")
    configure_database(monkeypatch, database_path)

    db.init_db()

    with db.connect() as connection:
        after = capture_m004_preservation_snapshot(
            connection,
            legacy_machine_ids=legacy_machine_ids,
        )
        card = read_row(connection, "cards", "id", 1)
        column_types = {
            row["name"]: row["type"]
            for row in connection.execute("PRAGMA table_info(cards)").fetchall()
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    migration_rows = after.pop("schema_migrations")
    assert after == before
    assert migration_rows[:-1] == prior_migrations
    assert migration_rows[-1][:2] == (4, "rewinding_return_workflow")
    assert card["rewinding_roll_count"] is None
    assert card["final_extrusion_shift_occurrence_id"] is None
    assert card["current_pallet_number"] == 17
    assert card["legacy_extension"] == "preserved"
    assert card["legacy_unsafe"] == "safe fallback"
    assert column_types["legacy_extension"] == "VARCHAR(32)"
    assert column_types["legacy_unsafe"] == "TEXT"
    assert integrity == "ok"
    assert foreign_key_violations == []


def test_m004_upgrades_sparse_legacy_cards_before_creating_card_indexes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m004-sparse-legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'imported',
                raw_material_a TEXT
            );
            INSERT INTO cards (order_number, raw_material_a)
            VALUES ('SPARSE-LEGACY-1', 'LDPE Legacy A | 100%');
            """
        )
    configure_database(monkeypatch, database_path)

    db.init_db()

    with db.connect() as connection:
        card = read_row(connection, "cards", "id", 1)
        card_indexes = {
            row["name"]
            for row in connection.execute("PRAGMA index_list(cards)").fetchall()
        }
        migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert card["order_number"] == "SPARSE-LEGACY-1"
    assert card["raw_material_a"] == "LDPE Legacy A | 100%"
    assert card["rewinding_roll_count"] is None
    assert {
        "idx_cards_one_running_per_machine",
        "idx_cards_active_machine_sequence",
        "idx_cards_status_machine_sequence",
    }.issubset(card_indexes)
    assert tuple(migration_rows[-1]) == (4, "rewinding_return_workflow")


def test_m004_preserves_valid_partially_deployed_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m004-valid-partial.sqlite3"
    create_recorded_m003_database(database_path)
    add_partially_upgraded_rewinding_schema(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE cards SET rewinding_roll_count = 12, "
            "final_extrusion_shift_occurrence_id = 1 WHERE id = 1"
        )
    configure_database(monkeypatch, database_path)

    db.init_db()

    with db.connect() as connection:
        card = read_row(connection, "cards", "id", 1)
        migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert card["rewinding_roll_count"] == 12
    assert card["final_extrusion_shift_occurrence_id"] == 1
    assert tuple(migration_rows[-1]) == (4, "rewinding_return_workflow")


def test_m004_preserves_cards_autoincrement_high_water_mark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m004-autoincrement.sqlite3"
    create_recorded_m003_database(database_path)
    with sqlite3.connect(database_path) as connection:
        deleted_id = connection.execute(
            "INSERT INTO cards (order_number) VALUES ('DELETED-HIGH-WATER')"
        ).lastrowid
        connection.execute("DELETE FROM cards WHERE id = ?", (deleted_id,))
        sequence_before = connection.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'cards'"
        ).fetchone()[0]
    configure_database(monkeypatch, database_path)

    db.init_db()

    with db.connect() as connection:
        inserted_id = connection.execute(
            "INSERT INTO cards (order_number) VALUES ('AFTER-M004')"
        ).lastrowid

    assert sequence_before == deleted_id
    assert inserted_id > deleted_id


def test_recorded_m004_rejects_status_constraint_missing_canonical_statuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "recorded-m004-narrow-statuses.sqlite3"
    configure_database(monkeypatch, database_path)
    db.init_db()

    canonical_status_sql = (
        "status TEXT NOT NULL DEFAULT 'imported' CHECK (status IN "
        "('imported', 'pending', 'running', 'paused', 'completed', 'archived', "
        "'cancelled', 'awaiting_rewinding'))"
    )
    narrow_status_sql = (
        "status TEXT NOT NULL DEFAULT 'imported' CHECK (status IN "
        "('imported', 'awaiting_rewinding'))"
    )
    narrow_table_sql = cards_table_sql(
        "cards_narrow_status",
        if_not_exists=False,
    ).replace(canonical_status_sql, narrow_status_sql)
    assert narrow_table_sql != cards_table_sql(
        "cards_narrow_status",
        if_not_exists=False,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(narrow_table_sql)
        connection.execute("DROP TABLE cards")
        connection.execute("ALTER TABLE cards_narrow_status RENAME TO cards")

    with pytest.raises(RuntimeError, match="status.*canonical"):
        db.init_db()


@pytest.mark.parametrize(
    "invalid_kind",
    ("count", "dangling-final-shift"),
)
def test_m004_rejects_invalid_partially_deployed_data_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_kind: str,
) -> None:
    database_path = tmp_path / f"m004-invalid-partial-{invalid_kind}.sqlite3"
    create_recorded_m003_database(database_path)
    add_partially_upgraded_rewinding_schema(
        database_path,
        count_definition="INTEGER",
    )
    with sqlite3.connect(database_path) as connection:
        if invalid_kind == "count":
            connection.execute(
                "UPDATE cards SET rewinding_roll_count = 0 WHERE id = 1"
            )
        else:
            connection.execute(
                "UPDATE cards SET final_extrusion_shift_occurrence_id = 999 "
                "WHERE id = 1"
            )
    configure_database(monkeypatch, database_path)

    with pytest.raises((RuntimeError, sqlite3.IntegrityError)):
        db.init_db()

    with sqlite3.connect(database_path) as connection:
        card = connection.execute(
            "SELECT rewinding_roll_count, final_extrusion_shift_occurrence_id "
            "FROM cards WHERE id = 1"
        ).fetchone()
        migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

    expected = (0, None) if invalid_kind == "count" else (None, 999)
    assert card == expected
    assert migration_rows[-1] == (3, "roll_pallet_assignment")


@pytest.mark.parametrize(
    ("malformation", "error_match"),
    (
        ("missing-final-column", "final_extrusion_shift_occurrence_id.*missing"),
        ("count-without-constraint", "rewinding_roll_count.*constraint"),
        ("final-shift-without-foreign-key", "final_extrusion.*foreign key"),
        ("status-without-awaiting", "status.*awaiting_rewinding"),
    ),
)
def test_init_rejects_recorded_m004_with_malformed_cards_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    malformation: str,
    error_match: str,
) -> None:
    database_path = tmp_path / f"recorded-m004-{malformation}.sqlite3"
    create_recorded_m003_database(database_path)
    if malformation == "missing-final-column":
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "ALTER TABLE cards ADD COLUMN rewinding_roll_count "
                + "INTEGER "
                + PALLET_VALUE_CHECK.format(column="rewinding_roll_count")
            )
    else:
        add_partially_upgraded_rewinding_schema(
            database_path,
            count_definition=(
                "INTEGER"
                if malformation == "count-without-constraint"
                else "INTEGER "
                + PALLET_VALUE_CHECK.format(column="rewinding_roll_count")
            ),
            final_shift_definition=(
                "INTEGER"
                if malformation == "final-shift-without-foreign-key"
                else "INTEGER REFERENCES shift_occurrences(id) ON DELETE RESTRICT"
            ),
        )
    add_recorded_m004(database_path)
    configure_database(monkeypatch, database_path)

    with pytest.raises(RuntimeError, match=error_match):
        db.init_db()


def test_recorded_m004_rejects_final_shift_constraint_that_forces_null(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "recorded-m004-final-shift-forced-null.sqlite3"
    configure_database(monkeypatch, database_path)
    db.init_db()
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM shift_occurrences"
        ).fetchone()[0] == 0

    canonical_definition = (
        "final_extrusion_shift_occurrence_id INTEGER\n"
        "        REFERENCES shift_occurrences(id) ON DELETE RESTRICT,"
    )
    malformed_definition = (
        "final_extrusion_shift_occurrence_id INTEGER\n"
        "        REFERENCES shift_occurrences(id) ON DELETE RESTRICT\n"
        "        CHECK (final_extrusion_shift_occurrence_id IS NULL),"
    )
    malformed_table_sql = cards_table_sql(
        "cards_final_shift_forced_null",
        if_not_exists=False,
    ).replace(canonical_definition, malformed_definition)
    assert malformed_table_sql != cards_table_sql(
        "cards_final_shift_forced_null",
        if_not_exists=False,
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(malformed_table_sql)
        connection.execute("DROP TABLE cards")
        connection.execute(
            "ALTER TABLE cards_final_shift_forced_null RENAME TO cards"
        )

    with pytest.raises(RuntimeError, match="final_extrusion.*constraint"):
        db.init_db()

    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM shift_occurrences"
        ).fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 4"
        ).fetchone()[0] == 1


def test_recorded_m004_rejects_final_shift_write_that_does_not_persist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "recorded-m004-final-shift-discarded.sqlite3"
    configure_database(monkeypatch, database_path)
    db.init_db()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER cards_discard_final_shift
            AFTER UPDATE OF final_extrusion_shift_occurrence_id ON cards
            WHEN NEW.final_extrusion_shift_occurrence_id IS NOT NULL
            BEGIN
                UPDATE cards
                SET final_extrusion_shift_occurrence_id = NULL
                WHERE id = NEW.id;
            END
            """
        )

    with pytest.raises(RuntimeError, match="final_extrusion.*constraint"):
        db.init_db()

    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM shift_occurrences"
        ).fetchone()[0] == 0


def test_m004_failure_after_cards_copy_rolls_back_schema_data_and_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m004-failure-after-copy.sqlite3"
    create_recorded_m003_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("ALTER TABLE cards ADD COLUMN legacy_extension TEXT")
        connection.execute(
            "UPDATE cards SET legacy_extension = 'still here' WHERE id = 1"
        )
        original_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
        ).fetchone()[0]
    configure_database(monkeypatch, database_path)
    startup_connection = sqlite3.connect(database_path)
    startup_connection.row_factory = sqlite3.Row
    startup_connection.execute("PRAGMA foreign_keys = ON")
    monkeypatch.setattr(db, "connect", lambda: startup_connection)
    monkeypatch.setattr(
        migrations,
        "CARD_INDEX_SQL",
        (*migrations.CARD_INDEX_SQL, "CREATE INDEX"),
    )

    with pytest.raises(sqlite3.OperationalError):
        db.init_db()

    with sqlite3.connect(database_path) as connection:
        restored_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
        ).fetchone()[0]
        card = connection.execute(
            "SELECT status, machine_id, machine_sequence, version, "
            "legacy_extension FROM cards WHERE id = 1"
        ).fetchone()
        migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        temporary_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cards_m004'"
        ).fetchone()
    foreign_keys_enabled = startup_connection.execute(
        "PRAGMA foreign_keys"
    ).fetchone()[0]
    startup_connection.close()

    assert restored_schema == original_schema
    assert card == ("running", 1, 1, 7, "still here")
    assert migration_rows[-1] == (3, "roll_pallet_assignment")
    assert temporary_table is None
    assert foreign_keys_enabled == 1


def test_apply_startup_migrations_restores_foreign_keys_after_success_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "startup-foreign-keys.sqlite3"
    configure_database(monkeypatch, database_path)
    db.init_db()

    with db.connect() as connection:
        assert migrations.apply_startup_migrations(connection) == ()
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1

        def fail_validation(_connection: sqlite3.Connection) -> None:
            raise RuntimeError("injected startup validation failure")

        monkeypatch.setattr(
            migrations,
            "validate_rewinding_schema",
            fail_validation,
        )
        with pytest.raises(
            RuntimeError,
            match="injected startup validation failure",
        ):
            migrations.apply_startup_migrations(connection)

        assert connection.in_transaction is False
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_m003_enforces_integer_pallet_range_on_cards_and_rolls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m003-constraints.sqlite3"
    configure_database(monkeypatch, database_path)
    db.init_db()

    valid_values: tuple[object, ...] = (None, 1, 999, "1")
    with db.connect() as connection:
        for index, value in enumerate(valid_values, start=1):
            order_number = f"PALLET-VALID-{index}"
            card_id = connection.execute(
                "INSERT INTO cards (order_number, current_pallet_number) VALUES (?, ?)",
                (order_number, value),
            ).lastrowid
            connection.execute(
                "INSERT INTO roll_entries ("
                "card_id, order_number, roll_number, pallet_number"
                ") VALUES (?, ?, 1, ?)",
                (card_id, order_number, value),
            )

        for index, value in enumerate(("abc", 0, -1, 1000), start=1):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO cards (order_number, current_pallet_number) "
                    "VALUES (?, ?)",
                    (f"PALLET-CARD-INVALID-{index}", value),
                )
            card_id = connection.execute(
                "INSERT INTO cards (order_number) VALUES (?)",
                (f"PALLET-ROLL-INVALID-{index}",),
            ).lastrowid
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO roll_entries ("
                    "card_id, order_number, roll_number, pallet_number"
                    ") VALUES (?, ?, 1, ?)",
                    (card_id, f"PALLET-ROLL-INVALID-{index}", value),
                )

        stored_card_types = [
            tuple(row)
            for row in connection.execute(
                "SELECT current_pallet_number, typeof(current_pallet_number) "
                "FROM cards WHERE order_number LIKE 'PALLET-VALID-%' ORDER BY id"
            ).fetchall()
        ]
        stored_roll_types = [
            tuple(row)
            for row in connection.execute(
                "SELECT pallet_number, typeof(pallet_number) FROM roll_entries "
                "WHERE order_number LIKE 'PALLET-VALID-%' ORDER BY id"
            ).fetchall()
        ]

    assert stored_card_types == [
        (None, "null"),
        (1, "integer"),
        (999, "integer"),
        (1, "integer"),
    ]
    assert stored_roll_types == stored_card_types


def test_m003_failure_rolls_back_columns_and_migration_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "m003-failure.sqlite3"
    create_legacy_database(database_path)
    add_existing_final_values(database_path)
    add_partially_upgraded_shift_schema(database_path)
    add_recorded_m001_and_m002(database_path)
    configure_database(monkeypatch, database_path)

    def fail_validation(connection: sqlite3.Connection) -> None:
        raise RuntimeError("injected M003 validation failure")

    monkeypatch.setattr(migrations, "validate_roll_pallet_schema", fail_validation)

    with pytest.raises(RuntimeError, match="injected M003 validation failure"):
        db.init_db()

    with sqlite3.connect(database_path) as connection:
        card_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(cards)").fetchall()
        }
        roll_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(roll_entries)").fetchall()
        }
        migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert "current_pallet_number" not in card_columns
    assert "pallet_number" not in roll_columns
    assert migration_rows == [
        (1, "shift_manager_import_fields"),
        (2, "shift_management"),
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
