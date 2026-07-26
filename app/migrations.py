from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from .constants import CARD_STATUSES, STATUS_AWAITING_REWINDING
from .schema import (
    CARD_INDEX_SQL,
    _quote_identifier,
    cards_table_sql,
    extend_cards_rebuild_target,
)


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

PALLET_COLUMNS = (
    ("cards", "current_pallet_number"),
    ("roll_entries", "pallet_number"),
)


def _pallet_column_definition(column_name: str) -> str:
    return (
        "INTEGER CHECK ("
        f"{column_name} IS NULL OR "
        f"(typeof({column_name}) = 'integer' AND {column_name} BETWEEN 1 AND 999)"
        ")"
    )


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


def _roll_shift_foreign_key_is_valid(connection: sqlite3.Connection) -> bool:
    return any(
        str(row[2]) == "shift_occurrences"
        and str(row[3]) == "shift_occurrence_id"
        and str(row[4]) == "id"
        and str(row[6]).upper() == "RESTRICT"
        for row in connection.execute(
            "PRAGMA foreign_key_list(roll_entries)"
        ).fetchall()
    )


def validate_shift_management_schema(connection: sqlite3.Connection) -> None:
    roll_columns = _table_columns(connection, "roll_entries")
    if roll_columns is None or "shift_occurrence_id" not in roll_columns:
        raise RuntimeError(
            "roll_entries.shift_occurrence_id is missing after M002"
        )
    if not _roll_shift_foreign_key_is_valid(connection):
        raise RuntimeError(
            "roll_entries.shift_occurrence_id exists without the required "
            "foreign key to shift_occurrences(id); restore a known-good backup "
            "or repair the partial schema before retrying M002"
        )


def _pallet_column_has_required_metadata(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    column = next(
        (
            row
            for row in connection.execute(
                f"PRAGMA table_info({_quote_identifier(table_name)})"
            ).fetchall()
            if str(row[1]) == column_name
        ),
        None,
    )
    return (
        column is not None
        and str(column[2]).strip().upper() == "INTEGER"
        and int(column[3]) == 0
        and column[4] is None
    )


def _is_sql_identifier_character(character: str) -> bool:
    return character.isalnum() or character == "_"


def _skip_sql_quoted_text(sql: str, start: int, quote: str) -> int:
    index = start + 1
    while index < len(sql):
        if sql[index] != quote:
            index += 1
            continue
        if index + 1 < len(sql) and sql[index + 1] == quote:
            index += 2
            continue
        return index + 1
    return index


def _strip_sql_comments(sql: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(sql):
        character = sql[index]
        if character in "'\"`":
            end = _skip_sql_quoted_text(sql, index, character)
            result.append(sql[index:end])
            index = end
            continue
        if character == "[":
            end = sql.find("]", index + 1)
            end = len(sql) if end == -1 else end + 1
            result.append(sql[index:end])
            index = end
            continue
        if sql.startswith("--", index):
            line_end = sql.find("\n", index + 2)
            result.append(" ")
            index = len(sql) if line_end == -1 else line_end
            continue
        if sql.startswith("/*", index):
            comment_end = sql.find("*/", index + 2)
            result.append(" ")
            index = len(sql) if comment_end == -1 else comment_end + 2
            continue
        result.append(character)
        index += 1
    return "".join(result)


def _extract_parenthesized_sql(sql: str, start: int) -> tuple[str, int] | None:
    depth = 0
    index = start
    while index < len(sql):
        character = sql[index]
        if character in "'\"`":
            index = _skip_sql_quoted_text(sql, index, character)
            continue
        if character == "[":
            end = sql.find("]", index + 1)
            index = len(sql) if end == -1 else end + 1
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return sql[start + 1:index], index + 1
        index += 1
    return None


def _normalized_check_expressions(schema_sql: str) -> tuple[str, ...]:
    sql = _strip_sql_comments(schema_sql)
    expressions: list[str] = []
    index = 0
    while index < len(sql):
        character = sql[index]
        if character in "'\"`":
            index = _skip_sql_quoted_text(sql, index, character)
            continue
        if character == "[":
            end = sql.find("]", index + 1)
            index = len(sql) if end == -1 else end + 1
            continue
        if (
            sql[index:index + 5].lower() == "check"
            and (index == 0 or not _is_sql_identifier_character(sql[index - 1]))
            and (
                index + 5 == len(sql)
                or not _is_sql_identifier_character(sql[index + 5])
            )
        ):
            opening_parenthesis = index + 5
            while (
                opening_parenthesis < len(sql)
                and sql[opening_parenthesis].isspace()
            ):
                opening_parenthesis += 1
            if (
                opening_parenthesis < len(sql)
                and sql[opening_parenthesis] == "("
            ):
                extracted = _extract_parenthesized_sql(sql, opening_parenthesis)
                if extracted is not None:
                    expression, index = extracted
                    expressions.append(
                        "check(" + "".join(expression.lower().split()) + ")"
                    )
                    continue
        index += 1
    return tuple(expressions)


def _sql_contains_identifier(sql: str, identifier: str) -> bool:
    index = 0
    lowered_identifier = identifier.lower()
    while index < len(sql):
        character = sql[index]
        if character == "'":
            index = _skip_sql_quoted_text(sql, index, character)
            continue
        if character in "\"`":
            end = _skip_sql_quoted_text(sql, index, character)
            quoted_identifier = sql[index + 1:end - 1].replace(
                character * 2,
                character,
            )
            if quoted_identifier.lower() == lowered_identifier:
                return True
            index = end
            continue
        if character == "[":
            end = sql.find("]", index + 1)
            if end != -1 and sql[index + 1:end].lower() == lowered_identifier:
                return True
            index = len(sql) if end == -1 else end + 1
            continue
        if (
            sql[index:index + len(identifier)].lower() == lowered_identifier
            and (index == 0 or not _is_sql_identifier_character(sql[index - 1]))
            and (
                index + len(identifier) == len(sql)
                or not _is_sql_identifier_character(sql[index + len(identifier)])
            )
        ):
            return True
        index += 1
    return False


def _pallet_constraint_forms(column_name: str) -> frozenset[str]:
    null_clause = f"{column_name}isnull"
    integer_clause = f"typeof({column_name})='integer'"
    range_clause = f"{column_name}between1and999"
    return frozenset(
        (
            f"check({null_clause}or({integer_clause}and{range_clause}))",
            f"check({null_clause}or({range_clause}and{integer_clause}))",
            f"check(({integer_clause}and{range_clause})or{null_clause})",
            f"check(({range_clause}and{integer_clause})or{null_clause})",
        )
    )


def _pallet_column_has_required_constraint(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    schema_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if schema_row is None:
        return False
    allowed_forms = _pallet_constraint_forms(column_name)
    target_expressions = tuple(
        expression
        for expression in _normalized_check_expressions(str(schema_row[0] or ""))
        if _sql_contains_identifier(expression, column_name)
    )
    return len(target_expressions) == 1 and target_expressions[0] in allowed_forms


def _insert_pallet_constraint_probe(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    order_number: str,
    probe_number: int,
    value: object,
) -> None:
    quoted_column = _quote_identifier(column_name)
    if table_name == "cards":
        connection.execute(
            f"INSERT INTO cards (order_number, {quoted_column}) VALUES (?, ?)",
            (order_number, value),
        )
        return

    card_id = connection.execute(
        "INSERT INTO cards (order_number) VALUES (?)",
        (order_number,),
    ).lastrowid
    connection.execute(
        f"""
        INSERT INTO roll_entries (
            card_id, order_number, roll_number, {quoted_column}
        ) VALUES (?, ?, ?, ?)
        """,
        (card_id, order_number, probe_number, value),
    )


def _pallet_column_enforces_contract(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    savepoint_name = "validate_roll_pallet_constraint"
    connection.execute(f"SAVEPOINT {savepoint_name}")
    try:
        probe_suffix = connection.execute(
            "SELECT lower(hex(randomblob(16)))"
        ).fetchone()[0]
        valid_values = (None, 1, 999, "1")
        invalid_values = ("abc", 0, -1, 1000, 1.5, b"1")
        for probe_number, value in enumerate(valid_values, start=1):
            _insert_pallet_constraint_probe(
                connection,
                table_name,
                column_name,
                f"__m003_pallet_probe_{probe_suffix}_{probe_number}",
                probe_number,
                value,
            )
        for probe_number, value in enumerate(
            invalid_values,
            start=len(valid_values) + 1,
        ):
            try:
                _insert_pallet_constraint_probe(
                    connection,
                    table_name,
                    column_name,
                    f"__m003_pallet_probe_{probe_suffix}_{probe_number}",
                    probe_number,
                    value,
                )
            except sqlite3.IntegrityError:
                continue
            return False
    finally:
        connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
        connection.execute(f"RELEASE SAVEPOINT {savepoint_name}")
    return True


def validate_roll_pallet_schema(connection: sqlite3.Connection) -> None:
    for table_name, column_name in PALLET_COLUMNS:
        columns = _table_columns(connection, table_name)
        if columns is None or column_name not in columns:
            raise RuntimeError(
                f"{table_name}.{column_name} is missing after M003"
            )
        if not _pallet_column_has_required_metadata(
            connection,
            table_name,
            column_name,
        ):
            raise RuntimeError(
                f"{table_name}.{column_name} must be nullable, defaultless INTEGER"
            )
        if not _pallet_column_has_required_constraint(
            connection,
            table_name,
            column_name,
        ):
            raise RuntimeError(
                f"{table_name}.{column_name} lacks the required pallet constraint"
            )
        if not _pallet_column_enforces_contract(
            connection,
            table_name,
            column_name,
        ):
            raise RuntimeError(
                f"{table_name}.{column_name} lacks the required pallet constraint"
            )
        quoted_table = _quote_identifier(table_name)
        quoted_column = _quote_identifier(column_name)
        invalid_row = connection.execute(
            f"""
            SELECT 1
            FROM {quoted_table}
            WHERE {quoted_column} IS NOT NULL
              AND (
                  typeof({quoted_column}) != 'integer'
                  OR {quoted_column} NOT BETWEEN 1 AND 999
              )
            LIMIT 1
            """
        ).fetchone()
        if invalid_row is not None:
            raise RuntimeError(
                f"{table_name}.{column_name} contains an invalid pallet value"
            )


def _rewinding_column_has_required_metadata(
    connection: sqlite3.Connection,
    column_name: str,
) -> bool:
    column = next(
        (
            row
            for row in connection.execute("PRAGMA table_info(cards)").fetchall()
            if str(row[1]) == column_name
        ),
        None,
    )
    return (
        column is not None
        and str(column[2]).strip().upper() == "INTEGER"
        and int(column[3]) == 0
        and column[4] is None
    )


def _final_extrusion_shift_foreign_key_is_valid(
    connection: sqlite3.Connection,
) -> bool:
    return any(
        str(row[2]) == "shift_occurrences"
        and str(row[3]) == "final_extrusion_shift_occurrence_id"
        and str(row[4]) == "id"
        and str(row[6]).upper() == "RESTRICT"
        for row in connection.execute("PRAGMA foreign_key_list(cards)").fetchall()
    )


def _validate_rewinding_constraints(connection: sqlite3.Connection) -> None:
    savepoint_name = "validate_rewinding_constraints"
    connection.execute(f"SAVEPOINT {savepoint_name}")
    try:
        probe_suffix = connection.execute(
            "SELECT lower(hex(randomblob(16)))"
        ).fetchone()[0]
        card_id = connection.execute(
            "INSERT INTO cards (order_number) VALUES (?)",
            (f"__m004_rewinding_probe_{probe_suffix}",),
        ).lastrowid

        for value in (None, 1, 42, 999, "1"):
            try:
                connection.execute(
                    "UPDATE cards SET rewinding_roll_count = ? WHERE id = ?",
                    (value, card_id),
                )
            except sqlite3.IntegrityError as error:
                raise RuntimeError(
                    "cards.rewinding_roll_count lacks the required constraint"
                ) from error

        for value in (0, -1, 1000, 1.5, "invalid", b"1"):
            try:
                connection.execute(
                    "UPDATE cards SET rewinding_roll_count = ? WHERE id = ?",
                    (value, card_id),
                )
            except sqlite3.IntegrityError:
                continue
            raise RuntimeError(
                "cards.rewinding_roll_count lacks the required constraint"
            )

        for status in CARD_STATUSES:
            try:
                connection.execute(
                    "UPDATE cards SET status = ? WHERE id = ?",
                    (status, card_id),
                )
            except sqlite3.IntegrityError as error:
                if status == STATUS_AWAITING_REWINDING:
                    message = (
                        "cards status constraint must accept awaiting_rewinding"
                    )
                else:
                    message = (
                        "cards status constraint must accept canonical status "
                        f"{status!r}"
                    )
                raise RuntimeError(message) from error

        try:
            connection.execute(
                "UPDATE cards SET status = 'unknown' WHERE id = ?",
                (card_id,),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise RuntimeError(
                "cards status constraint must reject unknown and accept "
                "awaiting_rewinding"
            )
    finally:
        connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
        connection.execute(f"RELEASE SAVEPOINT {savepoint_name}")


def ensure_foreign_keys_valid(
    connection: sqlite3.Connection,
    message: str,
) -> None:
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise sqlite3.IntegrityError(message)


def validate_rewinding_schema(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "cards")
    for column_name in (
        "rewinding_roll_count",
        "final_extrusion_shift_occurrence_id",
    ):
        if columns is None or column_name not in columns:
            raise RuntimeError(f"cards.{column_name} is missing after M004")
        if not _rewinding_column_has_required_metadata(connection, column_name):
            raise RuntimeError(
                f"cards.{column_name} must be nullable, defaultless INTEGER"
            )

    if not _final_extrusion_shift_foreign_key_is_valid(connection):
        raise RuntimeError(
            "cards.final_extrusion_shift_occurrence_id exists without the required "
            "foreign key to shift_occurrences(id)"
        )

    invalid_count = connection.execute(
        """
        SELECT 1
        FROM cards
        WHERE rewinding_roll_count IS NOT NULL
          AND (
              typeof(rewinding_roll_count) != 'integer'
              OR rewinding_roll_count NOT BETWEEN 1 AND 999
          )
        LIMIT 1
        """
    ).fetchone()
    if invalid_count is not None:
        raise RuntimeError("cards.rewinding_roll_count contains an invalid value")

    dangling_shift = connection.execute(
        """
        SELECT 1
        FROM cards
        LEFT JOIN shift_occurrences
          ON shift_occurrences.id = cards.final_extrusion_shift_occurrence_id
        WHERE cards.final_extrusion_shift_occurrence_id IS NOT NULL
          AND shift_occurrences.id IS NULL
        LIMIT 1
        """
    ).fetchone()
    if dangling_shift is not None:
        raise RuntimeError(
            "cards.final_extrusion_shift_occurrence_id contains a dangling value"
        )

    _validate_rewinding_constraints(connection)
    ensure_foreign_keys_valid(
        connection,
        "rewinding schema foreign key check failed",
    )


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
    if roll_columns is not None:
        validate_shift_management_schema(connection)

    connection.execute(SHIFT_ONE_ACTIVE_INDEX_SQL)
    connection.execute(SHIFT_COMPLETED_INDEX_SQL)
    if roll_columns is not None:
        connection.execute(ROLL_SHIFT_CARD_INDEX_SQL)


def _apply_roll_pallet_assignment(connection: sqlite3.Connection) -> None:
    for table_name, column_name in PALLET_COLUMNS:
        columns = _table_columns(connection, table_name)
        if columns is None:
            continue
        if column_name not in columns:
            connection.execute(
                f"ALTER TABLE {_quote_identifier(table_name)} "
                f"ADD COLUMN {_quote_identifier(column_name)} "
                f"{_pallet_column_definition(column_name)}"
            )
    validate_roll_pallet_schema(connection)


def apply_m004_rewinding_return_workflow(
    connection: sqlite3.Connection,
) -> None:
    source_sequence_row = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'cards'"
    ).fetchone()
    source_sequence = (
        int(source_sequence_row[0]) if source_sequence_row is not None else None
    )
    connection.execute(cards_table_sql("cards_m004", if_not_exists=False))
    copy_columns = extend_cards_rebuild_target(
        connection,
        "cards",
        "cards_m004",
    )
    column_sql = ", ".join(
        _quote_identifier(column_name) for column_name in copy_columns
    )
    connection.execute(
        f"INSERT INTO cards_m004 ({column_sql}) "
        f"SELECT {column_sql} FROM cards"
    )
    connection.execute("DROP TABLE cards")
    connection.execute("ALTER TABLE cards_m004 RENAME TO cards")
    replacement_sequence_row = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'cards'"
    ).fetchone()
    replacement_sequence = (
        int(replacement_sequence_row[0])
        if replacement_sequence_row is not None
        else None
    )
    if source_sequence is not None and (
        replacement_sequence is None or source_sequence > replacement_sequence
    ):
        if replacement_sequence_row is None:
            connection.execute(
                "INSERT INTO sqlite_sequence (name, seq) VALUES ('cards', ?)",
                (source_sequence,),
            )
        else:
            connection.execute(
                "UPDATE sqlite_sequence SET seq = ? WHERE name = 'cards'",
                (source_sequence,),
            )
    for index_sql in CARD_INDEX_SQL:
        connection.execute(index_sql)


MIGRATIONS = (
    Migration(1, "shift_manager_import_fields", _apply_shift_manager_import_fields),
    Migration(2, "shift_management", _apply_shift_management),
    Migration(3, "roll_pallet_assignment", _apply_roll_pallet_assignment),
    Migration(4, "rewinding_return_workflow", apply_m004_rewinding_return_workflow),
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


def apply_startup_migrations(
    connection: sqlite3.Connection,
) -> tuple[int, ...]:
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN")
        applied_versions = apply_pending_migrations(connection)
        validate_shift_management_schema(connection)
        validate_roll_pallet_schema(connection)
        validate_rewinding_schema(connection)
        ensure_foreign_keys_valid(
            connection,
            "migration foreign key check failed",
        )
        connection.commit()
        return applied_versions
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
