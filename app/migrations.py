from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

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


def terminal_configuration_table_sql(
    table_name: str = "terminal_configuration",
    *,
    bounded: bool = True,
    if_not_exists: bool = True,
) -> str:
    existence_clause = " IF NOT EXISTS" if if_not_exists else ""
    range_clause = "shift_count BETWEEN 1 AND 99" if bounded else "shift_count >= 1"
    return f"""
CREATE TABLE{existence_clause} {table_name} (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    shift_count INTEGER NOT NULL DEFAULT 4
        CHECK (typeof(shift_count) = 'integer' AND {range_clause}),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


TERMINAL_CONFIGURATION_TABLE_SQL = terminal_configuration_table_sql()
LEGACY_TERMINAL_CONFIGURATION_TABLE_SQL = terminal_configuration_table_sql(
    bounded=False,
)

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


def _normalized_contract_sql(sql: str) -> str:
    normalized = "".join(_strip_sql_comments(sql).lower().split())
    return normalized.replace("ifnotexists", "").rstrip(";")


def _schema_object_sql(
    connection: sqlite3.Connection,
    object_type: str,
    object_name: str,
) -> str | None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?",
        (object_type, object_name),
    ).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def _validate_exact_table_contract(
    connection: sqlite3.Connection,
    table_name: str,
    accepted_definitions: tuple[str, ...],
) -> str:
    actual_sql = _schema_object_sql(connection, "table", table_name)
    if actual_sql is None:
        raise RuntimeError(f"{table_name} is missing")
    normalized_actual = _normalized_contract_sql(actual_sql)
    normalized_definitions = {
        _normalized_contract_sql(definition): definition
        for definition in accepted_definitions
    }
    matched_definition = normalized_definitions.get(normalized_actual)
    if matched_definition is None:
        raise RuntimeError(f"{table_name} does not match the required schema contract")
    return matched_definition


def _validate_terminal_configuration_values(
    connection: sqlite3.Connection,
) -> None:
    rows = connection.execute(
        """
        SELECT id, shift_count, typeof(shift_count),
               version, typeof(version),
               updated_at, typeof(updated_at)
        FROM terminal_configuration
        """
    ).fetchall()
    if len(rows) != 1 or rows[0][0] != 1:
        raise RuntimeError(
            "terminal_configuration must contain exactly the singleton row id=1"
        )
    row = rows[0]
    if row[2] != "integer" or not 1 <= row[1] <= 99:
        raise RuntimeError(
            "terminal_configuration.shift_count must be a SQLite integer from 1 to 99"
        )
    if row[4] != "integer" or row[3] < 1:
        raise RuntimeError(
            "terminal_configuration.version must be a positive SQLite integer"
        )
    if row[6] != "text" or not str(row[5]):
        raise RuntimeError(
            "terminal_configuration.updated_at must be non-empty text"
        )


def _validate_shift_occurrence_values(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT shift_number, typeof(shift_number),
               started_at, typeof(started_at),
               ended_at, typeof(ended_at),
               version, typeof(version),
               created_at, typeof(created_at),
               updated_at, typeof(updated_at)
        FROM shift_occurrences
        """
    ).fetchall()
    for row in rows:
        if row[1] != "integer" or row[0] < 1:
            raise RuntimeError(
                "shift_occurrences.shift_number must be a positive SQLite integer"
            )
        if row[3] != "text" or not str(row[2]):
            raise RuntimeError("shift_occurrences.started_at must be non-empty text")
        if row[4] is not None and (
            row[5] != "text" or not str(row[4]) or str(row[4]) < str(row[2])
        ):
            raise RuntimeError("shift_occurrences.ended_at contains an invalid value")
        if row[7] != "integer" or row[6] < 1:
            raise RuntimeError(
                "shift_occurrences.version must be a positive SQLite integer"
            )
        if row[9] != "text" or not str(row[8]):
            raise RuntimeError("shift_occurrences.created_at must be non-empty text")
        if row[11] != "text" or not str(row[10]):
            raise RuntimeError("shift_occurrences.updated_at must be non-empty text")


def _required_shift_index_contracts() -> tuple[tuple[str, str], ...]:
    return (
        ("idx_shift_occurrences_one_active", SHIFT_ONE_ACTIVE_INDEX_SQL),
        ("idx_shift_occurrences_completed", SHIFT_COMPLETED_INDEX_SQL),
        ("idx_roll_entries_shift_card", ROLL_SHIFT_CARD_INDEX_SQL),
    )


def _ensure_required_shift_indexes(connection: sqlite3.Connection) -> None:
    for index_name, required_sql in _required_shift_index_contracts():
        actual_sql = _schema_object_sql(connection, "index", index_name)
        if actual_sql is None:
            connection.execute(required_sql)
            actual_sql = _schema_object_sql(connection, "index", index_name)
        if (
            actual_sql is None
            or _normalized_contract_sql(actual_sql)
            != _normalized_contract_sql(required_sql)
        ):
            raise RuntimeError(
                f"{index_name} does not match the required index contract"
            )


def _validate_shift_management_tables(
    connection: sqlite3.Connection,
    *,
    allow_legacy_configuration: bool,
) -> str:
    accepted_configuration_definitions = (TERMINAL_CONFIGURATION_TABLE_SQL,)
    if allow_legacy_configuration:
        accepted_configuration_definitions += (
            LEGACY_TERMINAL_CONFIGURATION_TABLE_SQL,
        )
    matched_configuration = _validate_exact_table_contract(
        connection,
        "terminal_configuration",
        accepted_configuration_definitions,
    )
    _validate_exact_table_contract(
        connection,
        "shift_occurrences",
        (SHIFT_OCCURRENCES_TABLE_SQL,),
    )
    _validate_terminal_configuration_values(connection)
    _validate_shift_occurrence_values(connection)

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
    return (
        "legacy"
        if _normalized_contract_sql(matched_configuration)
        == _normalized_contract_sql(LEGACY_TERMINAL_CONFIGURATION_TABLE_SQL)
        else "current"
    )


def _reject_m005_temporary_table(connection: sqlite3.Connection) -> None:
    temporary_table = "terminal_configuration_m005"
    if _table_columns(connection, temporary_table) is not None:
        raise RuntimeError(
            f"{temporary_table} already exists; repair the partial M005 schema "
            "before retrying"
        )


def validate_shift_management_schema(connection: sqlite3.Connection) -> None:
    _reject_m005_temporary_table(connection)
    _validate_shift_management_tables(
        connection,
        allow_legacy_configuration=False,
    )
    _ensure_required_shift_indexes(connection)


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
        shift_id = connection.execute(
            """
            INSERT INTO shift_occurrences (shift_number, started_at, ended_at)
            VALUES (1, '2000-01-01 00:00:00', '2000-01-01 00:00:00')
            """
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
                "UPDATE cards SET final_extrusion_shift_occurrence_id = ? "
                "WHERE id = ?",
                (shift_id, card_id),
            )
        except sqlite3.IntegrityError as error:
            raise RuntimeError(
                "cards.final_extrusion_shift_occurrence_id lacks the required "
                "constraint"
            ) from error
        stored_shift_id = connection.execute(
            "SELECT final_extrusion_shift_occurrence_id FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()[0]
        if stored_shift_id != shift_id:
            raise RuntimeError(
                "cards.final_extrusion_shift_occurrence_id lacks the required "
                "constraint"
            )

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
    connection.execute(SHIFT_ONE_ACTIVE_INDEX_SQL)
    connection.execute(SHIFT_COMPLETED_INDEX_SQL)
    if roll_columns is not None:
        connection.execute(ROLL_SHIFT_CARD_INDEX_SQL)
        _validate_shift_management_tables(
            connection,
            allow_legacy_configuration=True,
        )
        _ensure_required_shift_indexes(connection)


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


def apply_m005_shift_schema_contract(connection: sqlite3.Connection) -> None:
    _reject_m005_temporary_table(connection)
    configuration_contract = _validate_shift_management_tables(
        connection,
        allow_legacy_configuration=True,
    )
    _ensure_required_shift_indexes(connection)
    if configuration_contract == "legacy":
        temporary_table = "terminal_configuration_m005"
        connection.execute(
            terminal_configuration_table_sql(
                temporary_table,
                if_not_exists=False,
            )
        )
        connection.execute(
            f"""
            INSERT INTO {temporary_table} (
                id, shift_count, version, updated_at
            )
            SELECT id, shift_count, version, updated_at
            FROM terminal_configuration
            """
        )
        connection.execute("DROP TABLE terminal_configuration")
        connection.execute(TERMINAL_CONFIGURATION_TABLE_SQL)
        connection.execute(
            f"""
            INSERT INTO terminal_configuration (
                id, shift_count, version, updated_at
            )
            SELECT id, shift_count, version, updated_at
            FROM {temporary_table}
            """
        )
        connection.execute(f"DROP TABLE {temporary_table}")

    validate_shift_management_schema(connection)


LEGACY_AMOUNT_MAPPING = (
    ("quantity_1", "ordered_gross_kg"),
    ("unit_1", "ordered_rolls"),
    ("quantity_2", "ordered_meters"),
    ("unit_2", "ordered_units"),
)

LEGACY_ROUTE_COLUMNS = (
    "printing_sequence",
    "extrusion_sequence",
    "rewinding_slitting_sequence",
    "confection_sequence",
)


def _blank_text(value: object) -> bool:
    return value is None or not str(value).strip()


def _legacy_amount_is_numeric(value: object) -> bool:
    if _blank_text(value):
        return True
    normalized = "".join(str(value).split())
    if "," in normalized and "." in normalized:
        return False
    try:
        parsed = Decimal(normalized.replace(",", "."))
    except InvalidOperation:
        return False
    return parsed.is_finite() and parsed >= 0


def _legacy_row_matches_profiled_amount_contract(
    card_values: tuple[object, ...],
    source_values: tuple[object, ...],
) -> bool:
    combined_values = card_values + source_values
    if any(
        any(character.isalpha() for character in str(value))
        for value in combined_values
        if not _blank_text(value)
    ):
        return False
    if card_values != source_values:
        raise RuntimeError(
            "legacy ordered amount values disagree between card and import source"
        )
    if not all(_legacy_amount_is_numeric(value) for value in card_values):
        raise RuntimeError("unsupported legacy ordered amount format")
    return True


def _legacy_route_values(flag: object, next_operation: object) -> tuple[object, ...] | None:
    normalized_flag = str(flag or "").strip().casefold()
    if normalized_flag not in {"yes", "да"}:
        return None
    normalized_next = str(next_operation or "").strip().casefold()
    if not normalized_next:
        return (None, "1", None, None)
    if normalized_next == "confection":
        return (None, "1", None, "2")
    if normalized_next == "printing":
        return ("2", "1", None, "3")
    raise RuntimeError(
        f"unsupported legacy extrusion route: {str(next_operation).strip()!r}"
    )


def _update_blank_destination(
    connection: sqlite3.Connection,
    table_name: str,
    key_name: str,
    row_id: int,
    destination: str,
    value: object,
) -> None:
    if _blank_text(value):
        return
    connection.execute(
        f"""
        UPDATE {_quote_identifier(table_name)}
        SET {_quote_identifier(destination)} = ?
        WHERE {_quote_identifier(key_name)} = ?
          AND trim(COALESCE({_quote_identifier(destination)}, '')) = ''
        """,
        (value, row_id),
    )


def apply_m006_legacy_import_normalization(
    connection: sqlite3.Connection,
) -> None:
    required_legacy_columns = {
        *(source for source, _destination in LEGACY_AMOUNT_MAPPING),
        "extrusion_flag",
        "extrusion_next_operation",
    }
    required_final_columns = {
        *(destination for _source, destination in LEGACY_AMOUNT_MAPPING),
        *LEGACY_ROUTE_COLUMNS,
    }
    for table_name in ("cards", "card_import_sources"):
        columns = _table_columns(connection, table_name)
        if columns is None or not required_legacy_columns.issubset(columns):
            return
        if not required_final_columns.issubset(columns):
            raise RuntimeError(
                f"{table_name} is missing required normalized import columns"
            )

    rows = connection.execute(
        """
        SELECT c.id,
               c.quantity_1, c.unit_1, c.quantity_2, c.unit_2,
               s.quantity_1, s.unit_1, s.quantity_2, s.unit_2,
               c.extrusion_flag, c.extrusion_next_operation,
               s.extrusion_flag, s.extrusion_next_operation,
               c.printing_sequence, c.extrusion_sequence,
               c.rewinding_slitting_sequence, c.confection_sequence,
               s.printing_sequence, s.extrusion_sequence,
               s.rewinding_slitting_sequence, s.confection_sequence
        FROM cards AS c
        JOIN card_import_sources AS s ON s.card_id = c.id
        ORDER BY c.id
        """
    ).fetchall()
    for row in rows:
        card_id = int(row[0])
        card_amounts = tuple(row[1:5])
        source_amounts = tuple(row[5:9])
        if not _legacy_row_matches_profiled_amount_contract(
            card_amounts,
            source_amounts,
        ):
            continue

        for (source_column, destination), value in zip(
            LEGACY_AMOUNT_MAPPING,
            card_amounts,
            strict=True,
        ):
            _update_blank_destination(
                connection,
                "cards",
                "id",
                card_id,
                destination,
                value,
            )
            _update_blank_destination(
                connection,
                "card_import_sources",
                "card_id",
                card_id,
                destination,
                value,
            )

        card_route_source = (row[9], row[10])
        import_route_source = (row[11], row[12])
        normalized_card_route_source = tuple(
            str(value or "").strip().casefold() for value in card_route_source
        )
        normalized_import_route_source = tuple(
            str(value or "").strip().casefold() for value in import_route_source
        )
        if normalized_card_route_source != normalized_import_route_source:
            raise RuntimeError(
                "legacy extrusion route values disagree between card and import source"
            )
        route_values = _legacy_route_values(*card_route_source)
        if route_values is None:
            continue
        for table_name, key_name, existing_values in (
            ("cards", "id", tuple(row[13:17])),
            ("card_import_sources", "card_id", tuple(row[17:21])),
        ):
            if not all(_blank_text(value) for value in existing_values):
                continue
            for destination, value in zip(
                LEGACY_ROUTE_COLUMNS,
                route_values,
                strict=True,
            ):
                _update_blank_destination(
                    connection,
                    table_name,
                    key_name,
                    card_id,
                    destination,
                    value,
                )


MIGRATIONS = (
    Migration(1, "shift_manager_import_fields", _apply_shift_manager_import_fields),
    Migration(2, "shift_management", _apply_shift_management),
    Migration(3, "roll_pallet_assignment", _apply_roll_pallet_assignment),
    Migration(4, "rewinding_return_workflow", apply_m004_rewinding_return_workflow),
    Migration(5, "shift_schema_contract", apply_m005_shift_schema_contract),
    Migration(6, "legacy_import_normalization", apply_m006_legacy_import_normalization),
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
