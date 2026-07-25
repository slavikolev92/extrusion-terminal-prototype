from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


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


TERMINAL_CONFIGURATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS terminal_configuration (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    shift_count INTEGER NOT NULL DEFAULT 4
        CHECK (typeof(shift_count) = 'integer' AND shift_count >= 1),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

SHIFT_OCCURRENCES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS shift_occurrences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_number INTEGER NOT NULL
        CHECK (typeof(shift_number) = 'integer' AND shift_number >= 1),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (ended_at IS NULL OR ended_at >= started_at)
)
"""

SHIFT_ONE_ACTIVE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_shift_occurrences_one_active
ON shift_occurrences((1))
WHERE ended_at IS NULL
"""

SHIFT_COMPLETED_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_shift_occurrences_completed
ON shift_occurrences(ended_at DESC, id DESC)
WHERE ended_at IS NOT NULL
"""

ROLL_SHIFT_CARD_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_roll_entries_shift_card
ON roll_entries(shift_occurrence_id, card_id)
WHERE shift_occurrence_id IS NOT NULL
"""


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str] | None:
    table_row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if table_row is None:
        return None
    return {
        str(row[1])
        for row in connection.execute(
            f"PRAGMA table_info({_quote_identifier(table_name)})"
        ).fetchall()
    }


def _add_final_import_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str] | None:
    columns = _table_columns(connection, table_name)
    if columns is None:
        return None
    quoted_table = _quote_identifier(table_name)
    for column_name in FINAL_IMPORT_COLUMNS:
        if column_name in columns:
            continue
        connection.execute(
            f"ALTER TABLE {quoted_table} "
            f"ADD COLUMN {_quote_identifier(column_name)} TEXT"
        )
        columns.add(column_name)
    return columns


def _apply_shift_manager_import_fields(connection: sqlite3.Connection) -> None:
    for table_name in ("cards", "card_import_sources"):
        _add_final_import_columns(connection, table_name)


def _apply_shift_management(connection: sqlite3.Connection) -> None:
    connection.execute(TERMINAL_CONFIGURATION_TABLE_SQL)
    connection.execute(SHIFT_OCCURRENCES_TABLE_SQL)
    connection.execute(
        "INSERT OR IGNORE INTO terminal_configuration (id, shift_count) VALUES (1, 4)"
    )

    roll_columns = _table_columns(connection, "roll_entries")
    if roll_columns is not None and "shift_occurrence_id" not in roll_columns:
        connection.execute(
            "ALTER TABLE roll_entries "
            "ADD COLUMN shift_occurrence_id INTEGER "
            "REFERENCES shift_occurrences(id) ON DELETE RESTRICT"
        )
        roll_columns.add("shift_occurrence_id")

    connection.execute(SHIFT_ONE_ACTIVE_INDEX_SQL)
    connection.execute(SHIFT_COMPLETED_INDEX_SQL)
    if roll_columns is not None:
        connection.execute(ROLL_SHIFT_CARD_INDEX_SQL)


MIGRATIONS = (
    Migration(1, "shift_manager_import_fields", _apply_shift_manager_import_fields),
    Migration(2, "shift_management", _apply_shift_management),
)


def _validate_registry(registry: tuple[Migration, ...]) -> None:
    versions = tuple(migration.version for migration in registry)
    if any(version <= 0 for version in versions):
        raise ValueError("migration versions must be positive")
    if versions != tuple(sorted(set(versions))):
        raise ValueError("migration versions must be strictly increasing")
    if any(not migration.name.strip() for migration in registry):
        raise ValueError("migration names must not be blank")


def apply_pending_migrations(
    connection: sqlite3.Connection,
) -> tuple[int, ...]:
    """Apply and record pending migrations in version order.

    Transaction ownership stays with the caller so initialization can commit or
    roll back the migration changes and their records together.
    """
    registry = MIGRATIONS
    _validate_registry(registry)
    if not connection.in_transaction:
        raise RuntimeError("migrations require an active caller transaction")
    savepoint_name = "apply_pending_migrations"
    connection.execute(f"SAVEPOINT {savepoint_name}")
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        recorded_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        registry_by_version = {
            migration.version: migration
            for migration in registry
        }
        for version, recorded_name in recorded_rows:
            registered = registry_by_version.get(int(version))
            if registered is None:
                raise RuntimeError(
                    f"database contains unknown migration version {version}"
                )
            if registered.name != recorded_name:
                raise RuntimeError(
                    f"migration {version} name mismatch: "
                    f"database={recorded_name!r}, code={registered.name!r}"
                )

        recorded_version_sequence = tuple(int(row[0]) for row in recorded_rows)
        registered_prefix = tuple(
            migration.version
            for migration in registry[: len(recorded_version_sequence)]
        )
        if recorded_version_sequence != registered_prefix:
            raise RuntimeError(
                "recorded migrations must be a contiguous prefix of the registry"
            )

        recorded_versions = set(recorded_version_sequence)
        applied_versions: list[int] = []
        for migration in registry:
            if migration.version in recorded_versions:
                continue
            migration.apply(connection)
            connection.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (migration.version, migration.name),
            )
            applied_versions.append(migration.version)
    except BaseException:
        connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
        connection.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        raise
    else:
        connection.execute(f"RELEASE SAVEPOINT {savepoint_name}")

    return tuple(applied_versions)
