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


MIGRATIONS = (
    Migration(1, "shift_manager_import_fields", _apply_shift_manager_import_fields),
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
