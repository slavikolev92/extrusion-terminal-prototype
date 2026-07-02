from __future__ import annotations

import os
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path
from datetime import datetime
from typing import Any

from .constants import (
    ACTIVE_TERMINAL_STATUSES,
    ARCHIVE_STATUSES,
    CARD_STATUSES,
    PRODUCTION_COMPLETE_STATUSES,
    STATUS_ARCHIVED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_IMPORTED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_RUNNING,
    TERMINAL_VISIBLE_STATUSES,
)
from .recipe_parser import (
    APPROVED_RECIPE_CATEGORIES,
    RECIPE_SOURCE_FIELDS,
    ParsedRecipeComponent,
    RecipeParseResult,
    parse_recipe_source_fields,
)
from .rules import RuleResult, validate_structured_recipe_release

STALE_CARD_MESSAGE = "Картата е променена след зареждането на страницата. Презаредете и опитайте отново."
TIMING_END_REASONS = ("pause", "finish", "correction")
TIMING_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("EXTRUSION_DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.getenv("EXTRUSION_DB_PATH", DATA_DIR / "extrusion_terminal.sqlite3"))
TERMINAL_ACTION_STATUSES = (*ACTIVE_TERMINAL_STATUSES, *ARCHIVE_STATUSES)
TERMINAL_ACTION_STATUS_PLACEHOLDERS = ", ".join("?" for _ in TERMINAL_ACTION_STATUSES)


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


RECIPE_COMPONENT_KEY_PLACEHOLDERS = _sql_list(RECIPE_SOURCE_FIELDS)
RECIPE_CATEGORY_PLACEHOLDERS = _sql_list(APPROVED_RECIPE_CATEGORIES)
RECIPE_COMPONENT_ORDER_SQL = " ".join(
    f"WHEN '{component_key}' THEN {index}"
    for index, component_key in enumerate(RECIPE_SOURCE_FIELDS, start=1)
)


CARD_IMPORT_SOURCE_FIELDS = (
    "order_number",
    "order_date",
    "delivery_date",
    "customer",
    "city",
    "product_type",
    "quantity_1",
    "unit_1",
    "quantity_2",
    "unit_2",
    "product_form",
    "material",
    "size_thickness",
    "notes",
    "extrusion_flag",
    "extrusion_folding",
    "extrusion_next_operation",
    "extrusion_treatment",
    "raw_material_a",
    "raw_material_b",
    "raw_material_c",
    "linear_pe",
    "antistatic",
    "masterbatch",
    "chalk",
    "packaging_method",
)


def _sql_text_columns(values: tuple[str, ...]) -> str:
    return ",\n    ".join(f"{value} TEXT" for value in values)


def cards_table_sql(table_name: str = "cards", if_not_exists: bool = True) -> str:
    create_clause = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE TABLE"
    return f"""
{create_clause} {table_name} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'imported' CHECK (status IN ({_sql_list(CARD_STATUSES)})),
    import_batch_id INTEGER REFERENCES import_batches(id) ON DELETE SET NULL,
    machine_id INTEGER REFERENCES machines(id) ON DELETE RESTRICT,
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
    tare_weight NUMERIC CHECK (tare_weight IS NULL OR tare_weight >= 0),

    first_started_at TEXT,
    finished_at TEXT,
    cancelled_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


SCHEMA_SQL = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS machines (
    id INTEGER PRIMARY KEY CHECK (id BETWEEN 1 AND 4),
    name TEXT NOT NULL,
    is_operational INTEGER NOT NULL DEFAULT 1 CHECK (is_operational IN (0, 1)),
    display_order INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_filename TEXT,
    rows_seen INTEGER NOT NULL DEFAULT 0 CHECK (rows_seen >= 0),
    rows_imported INTEGER NOT NULL DEFAULT 0 CHECK (rows_imported >= 0),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_batch_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL CHECK (display_order >= 1),
    row_number INTEGER,
    order_number TEXT,
    action TEXT NOT NULL,
    message TEXT NOT NULL,
    is_duplicate_row INTEGER NOT NULL DEFAULT 0 CHECK (is_duplicate_row IN (0, 1)),
    row_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

{cards_table_sql().strip()}

CREATE TABLE IF NOT EXISTS card_import_sources (
    card_id INTEGER PRIMARY KEY REFERENCES cards(id) ON DELETE CASCADE,
    import_batch_id INTEGER REFERENCES import_batches(id) ON DELETE SET NULL,
    {_sql_text_columns(CARD_IMPORT_SOURCE_FIELDS)},
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS roll_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    order_number TEXT NOT NULL,
    roll_number INTEGER NOT NULL CHECK (roll_number >= 1),
    gross_weight NUMERIC CHECK (gross_weight IS NULL OR gross_weight >= 0),
    tare_weight NUMERIC CHECK (tare_weight IS NULL OR tare_weight >= 0),
    net_weight NUMERIC CHECK (net_weight IS NULL OR net_weight >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (card_id, roll_number)
);

CREATE TABLE IF NOT EXISTS recipe_actual_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    component_key TEXT NOT NULL,
    component_label TEXT NOT NULL,
    planned_material TEXT,
    actual_material_used TEXT,
    batch_lot TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (card_id, component_key)
);

CREATE TABLE IF NOT EXISTS recipe_components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    component_key TEXT NOT NULL CHECK (component_key IN ({RECIPE_COMPONENT_KEY_PLACEHOLDERS})),
    source_text TEXT NOT NULL,
    material_category TEXT NOT NULL CHECK (material_category IN ({RECIPE_CATEGORY_PLACEHOLDERS})),
    planned_material TEXT NOT NULL,
    recipe_percent NUMERIC NOT NULL CHECK (recipe_percent > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (card_id, component_key)
);

CREATE TABLE IF NOT EXISTS production_time_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    end_reason TEXT CHECK (end_reason IS NULL OR end_reason IN ('pause', 'finish', 'correction')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_one_running_per_machine
ON cards(machine_id)
WHERE status = 'running' AND machine_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_active_machine_sequence
ON cards(machine_id, machine_sequence)
WHERE status IN ({_sql_list(ACTIVE_TERMINAL_STATUSES)})
  AND machine_id IS NOT NULL
  AND machine_sequence IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cards_status_machine_sequence
ON cards(status, machine_id, machine_sequence);

CREATE INDEX IF NOT EXISTS idx_card_import_sources_order_number
ON card_import_sources(order_number);

CREATE INDEX IF NOT EXISTS idx_import_batch_rows_batch_order
ON import_batch_rows(import_batch_id, display_order, id);

CREATE INDEX IF NOT EXISTS idx_roll_entries_card_roll
ON roll_entries(card_id, roll_number);

CREATE INDEX IF NOT EXISTS idx_recipe_actual_entries_card
ON recipe_actual_entries(card_id);

CREATE INDEX IF NOT EXISTS idx_recipe_components_card
ON recipe_components(card_id);

CREATE INDEX IF NOT EXISTS idx_time_segments_card_started
ON production_time_segments(card_id, started_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_time_segments_one_open_per_card
ON production_time_segments(card_id)
WHERE ended_at IS NULL;
"""


MACHINE_SEED = (
    (1, "Machine 1", 1, 1),
    (2, "Machine 2", 1, 2),
    (3, "Machine 3", 1, 3),
    (4, "Machine 4", 1, 4),
)

RECIPE_COMPONENT_FIELDS = (
    ("raw_material_a", "Вид суровина A"),
    ("raw_material_b", "Вид суровина B"),
    ("raw_material_c", "Вид суровина C"),
    ("linear_pe", "Линеен /mLLDPE/"),
    ("antistatic", "Антистатик"),
    ("masterbatch", "Мастербач"),
    ("chalk", "Креда"),
)

ADMIN_MATERIAL_FIELDS = tuple(field for field, _ in RECIPE_COMPONENT_FIELDS)


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with connect() as connection:
        existing_cards_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
        ).fetchone()
        cards_status_migrated_before_schema = False
        if existing_cards_table:
            cards_status_migrated_before_schema = ensure_cards_status_constraint(
                connection,
                validate_foreign_keys=False,
            )
        connection.executescript(SCHEMA_SQL)
        seed_fixed_machines(connection)
        ensure_cards_status_constraint(connection)
        if cards_status_migrated_before_schema:
            ensure_foreign_keys_valid(
                connection,
                "cards status migration failed foreign key check",
            )
        connection.executescript(SCHEMA_SQL)
        # Existing pilot databases may still have legacy cards.validation_status;
        # current code ignores it and validates current card fields directly.
        ensure_column(connection, "cards", "max_roll_weight", "TEXT")
        ensure_roll_entry_tare_weight(connection)
        backfill_card_import_sources(connection)
        ensure_column(
            connection,
            "import_batch_rows",
            "is_duplicate_row",
            "INTEGER NOT NULL DEFAULT 0 CHECK (is_duplicate_row IN (0, 1))",
        )
        ensure_column(connection, "import_batch_rows", "row_error", "TEXT")


def seed_fixed_machines(connection: sqlite3.Connection) -> None:
    connection.executemany(
        """
        INSERT INTO machines (id, name, is_operational, display_order)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            display_order = excluded.display_order,
            updated_at = CURRENT_TIMESTAMP
        """,
        MACHINE_SEED,
    )


def ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> bool:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )
        return True
    return False


def ensure_roll_entry_tare_weight(connection: sqlite3.Connection) -> None:
    added_tare_weight = ensure_column(
        connection,
        "roll_entries",
        "tare_weight",
        "NUMERIC CHECK (tare_weight IS NULL OR tare_weight >= 0)",
    )
    if not added_tare_weight:
        return

    connection.execute(
        """
        UPDATE roll_entries
        SET tare_weight = (
            SELECT cards.tare_weight
            FROM cards
            WHERE cards.id = roll_entries.card_id
        )
        WHERE tare_weight IS NULL
          AND EXISTS (
              SELECT 1
              FROM cards
              WHERE cards.id = roll_entries.card_id
                AND cards.tare_weight IS NOT NULL
          )
        """
    )
    connection.execute(
        """
        UPDATE roll_entries
        SET net_weight = CASE
            WHEN gross_weight IS NOT NULL
             AND tare_weight IS NOT NULL
             AND CAST(gross_weight AS NUMERIC) >= CAST(tare_weight AS NUMERIC)
                THEN CAST(gross_weight AS NUMERIC) - CAST(tare_weight AS NUMERIC)
            ELSE NULL
        END
        WHERE gross_weight IS NOT NULL
        """
    )


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _legacy_column_type_sql(declared_type: Any) -> str:
    column_type = str(declared_type or "").strip()
    if not column_type:
        return "TEXT"
    safe_type_characters = (
        character.isascii() and (character.isalnum() or character in " _()")
        for character in column_type
    )
    if not all(safe_type_characters):
        return "TEXT"
    return column_type


def ensure_cards_status_constraint(
    connection: sqlite3.Connection,
    *,
    validate_foreign_keys: bool = True,
) -> bool:
    schema_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
    ).fetchone()
    schema_sql = str(schema_row["sql"] or "") if schema_row else ""
    if f"'{STATUS_ARCHIVED}'" in schema_sql:
        return False

    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("DROP TABLE IF EXISTS cards_status_migration")
        connection.execute(cards_table_sql("cards_status_migration", if_not_exists=False))

        legacy_column_info = connection.execute("PRAGMA table_info(cards)").fetchall()
        legacy_columns = {row["name"]: row for row in legacy_column_info}
        target_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(cards_status_migration)"
            ).fetchall()
        }
        for column_name, column_info in legacy_columns.items():
            if column_name in target_columns:
                continue
            connection.execute(
                f"""
                ALTER TABLE cards_status_migration
                ADD COLUMN {_quote_identifier(column_name)} {_legacy_column_type_sql(column_info["type"])}
                """
            )
            target_columns.add(column_name)

        copy_columns = [
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(cards_status_migration)"
            ).fetchall()
            if row["name"] in legacy_columns
        ]
        column_sql = ", ".join(_quote_identifier(column) for column in copy_columns)
        connection.execute(
            f"""
            INSERT INTO cards_status_migration ({column_sql})
            SELECT {column_sql}
            FROM cards
            """
        )
        connection.execute("DROP TABLE cards")
        connection.execute("ALTER TABLE cards_status_migration RENAME TO cards")
        connection.commit()
    finally:
        connection.execute("PRAGMA foreign_keys = ON")

    if validate_foreign_keys:
        ensure_foreign_keys_valid(
            connection,
            "cards status migration failed foreign key check",
        )
    return True


def ensure_foreign_keys_valid(
    connection: sqlite3.Connection,
    message: str,
) -> None:
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise sqlite3.IntegrityError(message)


def backfill_card_import_sources(connection: sqlite3.Connection) -> None:
    card_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(cards)").fetchall()
    }
    required_columns = {"id", "import_batch_id", *CARD_IMPORT_SOURCE_FIELDS}
    if not required_columns.issubset(card_columns):
        return

    columns = ("card_id", "import_batch_id", *CARD_IMPORT_SOURCE_FIELDS)
    select_values = (
        "id",
        "import_batch_id",
        *(f"COALESCE({field}, '')" for field in CARD_IMPORT_SOURCE_FIELDS),
    )
    # Older databases did not store source values separately, so their first
    # baseline can only be the current card values at migration time.
    connection.execute(
        f"""
        INSERT INTO card_import_sources ({", ".join(columns)})
        SELECT {", ".join(select_values)}
        FROM cards
        WHERE NOT EXISTS (
            SELECT 1
            FROM card_import_sources
            WHERE card_import_sources.card_id = cards.id
        )
        """
    )


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def fetch_machines() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, name, is_operational, display_order
            FROM machines
            ORDER BY display_order
            """
        ).fetchall()
        return rows_to_dicts(rows)


def fetch_cards_by_status(statuses: tuple[str, ...]) -> list[dict[str, Any]]:
    placeholders = ", ".join("?" for _ in statuses)
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT id, order_number, delivery_date, status, machine_id, machine_sequence,
                   customer, product_type, quantity_1, unit_1, quantity_2, unit_2,
                   product_form, material, size_thickness, max_roll_weight,
                   tare_weight, finished_at, version, updated_at,
                   COALESCE((
                       SELECT SUM(CAST(gross_weight AS NUMERIC))
                       FROM roll_entries
                       WHERE roll_entries.card_id = cards.id
                         AND gross_weight IS NOT NULL
                   ), 0) AS total_gross_weight
            FROM cards
            WHERE status IN ({placeholders})
            ORDER BY machine_id IS NULL, machine_id, machine_sequence IS NULL,
                     machine_sequence, order_number
            """,
            statuses,
        ).fetchall()
        return rows_to_dicts(rows)


def terminal_snapshot(selected_card_id: int | None = None) -> dict[str, Any]:
    active_placeholders = ", ".join("?" for _ in ACTIVE_TERMINAL_STATUSES)
    visible_placeholders = ", ".join("?" for _ in TERMINAL_VISIBLE_STATUSES)

    with connect() as connection:
        active_rows = connection.execute(
            f"""
            SELECT id, order_number, status, machine_id, machine_sequence,
                   version, updated_at
            FROM cards
            WHERE status IN ({active_placeholders})
            ORDER BY machine_id IS NULL, machine_id, machine_sequence IS NULL,
                     machine_sequence, order_number, id
            """,
            ACTIVE_TERMINAL_STATUSES,
        ).fetchall()
        active_cards = rows_to_dicts(active_rows)

        selected_card = None
        selected_card_missing = False
        if selected_card_id is not None:
            selected_row = connection.execute(
                f"""
                SELECT id, order_number, status, machine_id, machine_sequence,
                       version, updated_at
                FROM cards
                WHERE id = ?
                  AND status IN ({visible_placeholders})
                """,
                (selected_card_id, *TERMINAL_VISIBLE_STATUSES),
            ).fetchone()
            if selected_row:
                selected_card = dict(selected_row)
            else:
                selected_card_missing = True

    active_signature = "|".join(
        ":".join(
            str(card[field] if card[field] is not None else "")
            for field in (
                "id",
                "order_number",
                "status",
                "machine_id",
                "machine_sequence",
                "version",
                "updated_at",
            )
        )
        for card in active_cards
    )
    selected_signature = "none"
    if selected_card is not None:
        selected_signature = ":".join(
            str(selected_card[field] if selected_card[field] is not None else "")
            for field in (
                "id",
                "status",
                "machine_id",
                "machine_sequence",
                "version",
                "updated_at",
            )
        )
    elif selected_card_missing:
        selected_signature = f"missing:{selected_card_id}"

    return {
        "active_signature": active_signature,
        "signature": f"{active_signature}||{selected_signature}",
        "selected_card": selected_card,
        "selected_card_missing": selected_card_missing,
        "active_cards": active_cards,
    }


def fetch_card_by_id(card_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, order_number, status, machine_id, machine_sequence,
                   customer, product_type
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        return dict(row) if row else None


def fetch_admin_cards(filters: dict[str, str] | None = None, limit: int = 100) -> list[dict[str, Any]]:
    filters = filters or {}
    clauses: list[str] = []
    values: list[Any] = []

    text_filters = {
        "order_number": "order_number",
        "customer": "customer",
        "product": "product_type",
    }
    for filter_name, column_name in text_filters.items():
        value = filters.get(filter_name, "").strip()
        if value:
            clauses.append(f"LOWER({column_name}) LIKE LOWER(?)")
            values.append(f"%{value}%")

    exact_filters = {"status": "status"}
    for filter_name, column_name in exact_filters.items():
        value = filters.get(filter_name, "").strip()
        if value:
            clauses.append(f"{column_name} = ?")
            values.append(value)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    values.append(limit)

    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT id, order_number, status, customer, product_type,
                   machine_id, machine_sequence, updated_at
            FROM cards
            {where_sql}
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
        return rows_to_dicts(rows)


def fetch_admin_card_detail(card_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, order_number, status, import_batch_id, machine_id,
                   machine_sequence, order_date, delivery_date,
                   customer, city, product_type, quantity_1, unit_1,
                   quantity_2, unit_2, product_form, material,
                   max_roll_weight, size_thickness, notes, extrusion_flag, extrusion_folding,
                   extrusion_next_operation, extrusion_treatment,
                   raw_material_a, raw_material_b, raw_material_c,
                   linear_pe, antistatic, masterbatch, chalk,
                   packaging_method, actual_raw_material_used,
                   raw_material_brand_grade, raw_material_batch_lot,
                   tare_weight, first_started_at, finished_at, cancelled_at,
                   version, created_at, updated_at
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        if not row:
            return None

        card = dict(row)
        card["timing_segments"] = fetch_timing_segments_for_card(connection, card_id)
        card["total_production_seconds"] = calculate_total_production_seconds(
            connection,
            card_id,
        )
        card["active_segment_started_at"] = next(
            (
                segment["started_at"]
                for segment in card["timing_segments"]
                if segment["ended_at"] is None
            ),
            None,
        )
        roll_data = fetch_roll_entries_and_totals(connection, card_id)
        card.update(roll_data)
        card["recipe_actual_entries"] = fetch_recipe_actual_entries(connection, card_id)
        card["recipe_components"] = fetch_recipe_components(connection, card_id)
        return card


def fetch_terminal_card_detail(card_id: int) -> dict[str, Any] | None:
    placeholders = ", ".join("?" for _ in TERMINAL_VISIBLE_STATUSES)
    with connect() as connection:
        row = connection.execute(
            f"""
            SELECT id, order_number, status, machine_id, machine_sequence,
                   order_date, delivery_date, customer, city,
                   product_type, quantity_1, unit_1, quantity_2, unit_2,
                   product_form, material, max_roll_weight, size_thickness, notes,
                   extrusion_folding, extrusion_next_operation,
                   extrusion_treatment, raw_material_a, raw_material_b,
                   raw_material_c, linear_pe, antistatic, masterbatch, chalk,
                   packaging_method, actual_raw_material_used,
                   raw_material_brand_grade, raw_material_batch_lot,
                   tare_weight, first_started_at, finished_at, cancelled_at, version,
                   updated_at
            FROM cards
            WHERE id = ?
              AND status IN ({placeholders})
            """,
            (card_id, *TERMINAL_VISIBLE_STATUSES),
        ).fetchone()
        if not row:
            return None

        card = dict(row)
        card["timing_segments"] = fetch_timing_segments_for_card(connection, card_id)
        card["total_production_seconds"] = calculate_total_production_seconds(
            connection,
            card_id,
        )
        card["active_segment_started_at"] = next(
            (
                segment["started_at"]
                for segment in card["timing_segments"]
                if segment["ended_at"] is None
            ),
            None,
        )
        roll_data = fetch_roll_entries_and_totals(connection, card_id)
        card.update(roll_data)
        card["recipe_actual_entries"] = fetch_recipe_actual_entries(connection, card_id)
        card["recipe_components"] = fetch_recipe_components(connection, card_id)
        return card


def fetch_recipe_actual_entries(
    connection: sqlite3.Connection,
    card_id: int,
) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, component_key, component_label, planned_material,
               actual_material_used, batch_lot, created_at, updated_at
        FROM recipe_actual_entries
        WHERE card_id = ?
        """,
        (card_id,),
    ).fetchall()
    return {str(row["component_key"]): dict(row) for row in rows}


def replace_recipe_components_for_card(
    connection: sqlite3.Connection,
    card_id: int,
    components: tuple[ParsedRecipeComponent, ...] | list[ParsedRecipeComponent],
) -> None:
    component_order = {
        component_key: index for index, component_key in enumerate(RECIPE_SOURCE_FIELDS)
    }
    ordered_components = sorted(
        components,
        key=lambda component: component_order.get(component.component_key, 999),
    )

    connection.execute(
        """
        DELETE FROM recipe_components
        WHERE card_id = ?
        """,
        (card_id,),
    )
    connection.executemany(
        """
        INSERT INTO recipe_components (
            card_id,
            component_key,
            source_text,
            material_category,
            planned_material,
            recipe_percent
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (
                card_id,
                component.component_key,
                component.source_text,
                component.material_category,
                component.planned_material,
                decimal_to_storage(component.recipe_percent),
            )
            for component in ordered_components
        ),
    )


def parse_and_replace_recipe_components_for_card(
    connection: sqlite3.Connection,
    card_id: int,
    source_fields: dict[str, str | None],
) -> RecipeParseResult:
    result = parse_recipe_source_fields(source_fields)
    if result.ok:
        replace_recipe_components_for_card(connection, card_id, result.components)
    return result


def recipe_source_fields_from_mapping(source: dict[str, Any]) -> dict[str, str | None]:
    return {field: source.get(field) for field in RECIPE_SOURCE_FIELDS}


def sync_recipe_components_for_card(
    connection: sqlite3.Connection,
    card_id: int,
    source_fields: dict[str, Any],
) -> RecipeParseResult:
    result = parse_recipe_source_fields(recipe_source_fields_from_mapping(source_fields))
    replace_recipe_components_for_card(connection, card_id, result.components)
    return result


def fetch_recipe_components(
    connection: sqlite3.Connection,
    card_id: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"""
        SELECT id, card_id, component_key, source_text, material_category,
               planned_material, recipe_percent, created_at, updated_at
        FROM recipe_components
        WHERE card_id = ?
        ORDER BY CASE component_key {RECIPE_COMPONENT_ORDER_SQL} ELSE 999 END, id
        """,
        (card_id,),
    ).fetchall()
    components = rows_to_dicts(rows)
    for component in components:
        component["recipe_percent"] = decimal_from_database(component["recipe_percent"])
    return components


def fetch_roll_entries_and_totals(
    connection: sqlite3.Connection,
    card_id: int,
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT id, roll_number, gross_weight, tare_weight, net_weight, updated_at
        FROM roll_entries
        WHERE card_id = ?
        ORDER BY roll_number
        """,
        (card_id,),
    ).fetchall()
    roll_entries = rows_to_dicts(rows)
    gross_rolls = [entry for entry in roll_entries if entry["gross_weight"] is not None]
    gross_values = [
        decimal_from_roll_value(entry["gross_weight"])
        for entry in gross_rolls
    ]
    gross_values = [gross for gross in gross_values if gross is not None]
    gross_total_is_complete = len(gross_rolls) == len(gross_values)
    net_values = []
    for entry in gross_rolls:
        gross = decimal_from_roll_value(entry["gross_weight"])
        tare = decimal_from_roll_value(entry["tare_weight"])
        net = decimal_from_roll_value(entry["net_weight"])
        expected_net = net_weight_for_roll(gross, tare)
        if expected_net is not None and net == expected_net:
            net_values.append(net)
    roll_count = len(gross_rolls)
    total_gross = sum(gross_values, Decimal("0")) if gross_total_is_complete else None
    total_net = (
        sum(net_values, Decimal("0"))
        if gross_total_is_complete and len(gross_rolls) == len(net_values)
        else None
    )
    next_roll_number = (
        max((int(entry["roll_number"]) for entry in roll_entries), default=0) + 1
    )

    return {
        "roll_entries": roll_entries,
        "roll_count": roll_count,
        "next_roll_number": next_roll_number,
        "total_gross_weight": decimal_to_display(total_gross) if total_gross is not None else None,
        "total_net_weight": decimal_to_display(total_net) if total_net is not None else None,
        "tare_summary_display": roll_tare_summary_display(roll_entries),
    }


def decimal_from_roll_value(value: Any) -> Decimal | None:
    try:
        parsed = decimal_from_database(value)
    except (InvalidOperation, ValueError):
        return None
    if parsed is None or not parsed.is_finite():
        return None
    return parsed


def decimal_to_tare_summary_display(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.1")), "f")


def roll_tare_summary_display(roll_entries: list[dict[str, Any]]) -> str | None:
    tare_values = [
        decimal_from_roll_value(entry.get("tare_weight"))
        for entry in roll_entries
        if entry.get("gross_weight") is not None and entry.get("tare_weight") is not None
    ]
    tare_values = [tare for tare in tare_values if tare is not None]
    if not tare_values:
        return None

    lowest = min(tare_values)
    highest = max(tare_values)
    lowest_display = decimal_to_tare_summary_display(lowest)
    highest_display = decimal_to_tare_summary_display(highest)
    if lowest_display == highest_display:
        return lowest_display
    return f"{lowest_display}-{highest_display}"


def fetch_timing_segments_for_card(
    connection: sqlite3.Connection,
    card_id: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, started_at, ended_at, end_reason
        FROM production_time_segments
        WHERE card_id = ?
        ORDER BY started_at, id
        """,
        (card_id,),
    ).fetchall()
    return rows_to_dicts(rows)


def calculate_total_production_seconds(
    connection: sqlite3.Connection,
    card_id: int,
) -> int:
    total = connection.execute(
        """
        SELECT COALESCE(
            SUM(
                CAST(strftime('%s', COALESCE(ended_at, CURRENT_TIMESTAMP)) AS INTEGER)
                - CAST(strftime('%s', started_at) AS INTEGER)
            ),
            0
        )
        FROM production_time_segments
        WHERE card_id = ?
        """,
        (card_id,),
    ).fetchone()[0]
    return int(total or 0)


def fetch_total_production_seconds(card_id: int) -> int:
    with connect() as connection:
        return calculate_total_production_seconds(connection, card_id)


def start_production_timing(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = fetch_timing_action_card(connection, card_id)
        result = validate_timing_action_card(
            card=card,
            loaded_version=loaded_version,
            expected_status=STATUS_PENDING,
            expected_status_message="Само карти със статус Изчакване могат да бъдат стартирани.",
        )
        if not result.ok:
            return result

        occupied_card = fetch_occupied_machine_card(connection, card_id, int(card["machine_id"]))
        if occupied_card:
            return RuleResult(
                False,
                (
                    f"Машина {card['machine_id']} е заета от поръчка "
                    f"{occupied_card['order_number']}.",
                ),
            )

        if has_open_timing_segment(connection, card_id):
            return RuleResult(False, ("Картата вече има активен времеви сегмент.",))

        now = current_database_timestamp(connection)
        try:
            connection.execute(
                """
                UPDATE cards
                SET status = ?,
                    first_started_at = COALESCE(first_started_at, ?),
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (STATUS_RUNNING, now, card_id),
            )
            connection.execute(
                """
                INSERT INTO production_time_segments (card_id, started_at)
                VALUES (?, ?)
                """,
                (card_id, now),
            )
        except sqlite3.IntegrityError:
            connection.rollback()
            return RuleResult(
                False,
                (f"Машина {card['machine_id']} вече има карта в изработване.",),
            )

    return RuleResult(True, (f"Времето за поръчка {card['order_number']} е стартирано.",))


def pause_production_timing(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = fetch_timing_action_card(connection, card_id)
        result = validate_timing_action_card(
            card=card,
            loaded_version=loaded_version,
            expected_status=STATUS_RUNNING,
            expected_status_message="Само карти в изработване могат да бъдат паузирани.",
        )
        if not result.ok:
            return result

        open_segment = fetch_open_timing_segment(connection, card_id)
        if not open_segment:
            return RuleResult(False, ("Картата няма активен времеви сегмент за пауза.",))

        now = current_database_timestamp(connection)
        connection.execute(
            """
            UPDATE production_time_segments
            SET ended_at = ?,
                end_reason = 'pause',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (now, open_segment["id"]),
        )
        connection.execute(
            """
            UPDATE cards
            SET status = ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (STATUS_PAUSED, card_id),
        )

    return RuleResult(True, (f"Времето за поръчка {card['order_number']} е паузирано.",))


def resume_production_timing(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = fetch_timing_action_card(connection, card_id)
        result = validate_timing_action_card(
            card=card,
            loaded_version=loaded_version,
            expected_status=STATUS_PAUSED,
            expected_status_message="Само паузирани карти могат да бъдат продължени.",
        )
        if not result.ok:
            return result

        occupied_card = fetch_occupied_machine_card(connection, card_id, int(card["machine_id"]))
        if occupied_card:
            return RuleResult(
                False,
                (
                    f"Машина {card['machine_id']} е заета от поръчка "
                    f"{occupied_card['order_number']}.",
                ),
            )

        if has_open_timing_segment(connection, card_id):
            return RuleResult(False, ("Картата вече има активен времеви сегмент.",))

        now = current_database_timestamp(connection)
        try:
            connection.execute(
                """
                UPDATE cards
                SET status = ?,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (STATUS_RUNNING, card_id),
            )
            connection.execute(
                """
                INSERT INTO production_time_segments (card_id, started_at)
                VALUES (?, ?)
                """,
                (card_id, now),
            )
        except sqlite3.IntegrityError:
            connection.rollback()
            return RuleResult(
                False,
                (f"Машина {card['machine_id']} вече има карта в изработване.",),
            )

    return RuleResult(True, (f"Времето за поръчка {card['order_number']} е продължено.",))


def finish_card(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = fetch_active_terminal_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        finish_result = validate_card_ready_to_finish(connection, card_id, card)
        if not finish_result.ok:
            return finish_result

        now = current_database_timestamp(connection)
        open_segment = fetch_open_timing_segment(connection, card_id)
        if open_segment:
            if card["status"] != STATUS_RUNNING:
                return RuleResult(
                    False,
                    ("Паузирани карти не трябва да имат активен времеви сегмент. Презаредете картата.",),
                )
            connection.execute(
                """
                UPDATE production_time_segments
                SET ended_at = ?,
                    end_reason = 'finish',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (now, open_segment["id"]),
            )

        connection.execute(
            """
            UPDATE cards
            SET status = ?,
                finished_at = ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (STATUS_COMPLETED, now, card_id),
        )
        if card["machine_id"] is not None:
            normalize_machine_queue(connection, int(card["machine_id"]))

    return RuleResult(True, (f"Поръчка {card['order_number']} е приключена.",))


def archive_completed_card(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = connection.execute(
            """
            SELECT id, order_number, status, version
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        if card["status"] != STATUS_COMPLETED:
            return RuleResult(
                False,
                ("Само произведени карти могат да се маркират като завършени.",),
            )

        connection.execute(
            """
            UPDATE cards
            SET status = ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (STATUS_ARCHIVED, card_id),
        )

    return RuleResult(True, (f"Поръчка {card['order_number']} е маркирана като завършена.",))


def cancel_card(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = fetch_active_terminal_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        now = current_database_timestamp(connection)
        open_segment = fetch_open_timing_segment(connection, card_id)
        if open_segment:
            connection.execute(
                """
                UPDATE production_time_segments
                SET ended_at = ?,
                    end_reason = 'correction',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (now, open_segment["id"]),
            )

        connection.execute(
            """
            UPDATE cards
            SET status = ?,
                cancelled_at = ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (STATUS_CANCELLED, now, card_id),
        )
        if card["machine_id"] is not None:
            normalize_machine_queue(connection, int(card["machine_id"]))

    return RuleResult(True, (f"Поръчка {card['order_number']} е анулирана.",))


def restore_cancelled_card(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = connection.execute(
            """
            SELECT id, order_number, status, machine_id, machine_sequence, version
            FROM cards
            WHERE id = ?
              AND status = ?
            """,
            (card_id, STATUS_CANCELLED),
        ).fetchone()
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        try:
            temporary_sequence = -int(card["id"])
            connection.execute(
                """
                UPDATE cards
                SET status = ?,
                    machine_sequence = ?,
                    cancelled_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (STATUS_PENDING, temporary_sequence, card_id),
            )
            if card["machine_id"] is not None and card["machine_sequence"] is not None:
                normalize_machine_queue(
                    connection,
                    machine_id=int(card["machine_id"]),
                    moving_card_id=card_id,
                    target_position=int(card["machine_sequence"]),
                )
            else:
                touch_card(connection, card_id)
        except sqlite3.IntegrityError:
            connection.rollback()
            return RuleResult(
                False,
                ("Възстановяването не бе записано, защото тази машина и ред вече са заети.",),
            )

    return RuleResult(True, (f"Поръчка {card['order_number']} е възстановена със статус Изчакване.",))


def unrelease_pending_card(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = connection.execute(
            """
            SELECT id, order_number, status, machine_id, machine_sequence, version
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        if card["status"] != STATUS_PENDING:
            return RuleResult(
                False,
                ("Само изчакващи технологични карти могат да се връщат за планиране.",),
            )

        old_machine_id = int(card["machine_id"]) if card["machine_id"] is not None else None
        cursor = connection.execute(
            """
            UPDATE cards
            SET status = ?,
                machine_id = NULL,
                machine_sequence = NULL,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = ?
              AND version = ?
            """,
            (STATUS_IMPORTED, card_id, STATUS_PENDING, loaded_version),
        )
        if cursor.rowcount == 0:
            return RuleResult(False, (STALE_CARD_MESSAGE,))

        if old_machine_id is not None:
            normalize_machine_queue(connection, machine_id=old_machine_id)

    return RuleResult(
        True,
        (f"Поръчка {card['order_number']} е върната в неизпратени технологични карти.",),
    )


def add_timing_segment(
    card_id: int,
    loaded_version: int,
    started_at: str,
    ended_at: str,
    end_reason: str,
) -> RuleResult:
    parsed, parse_result = parse_timing_segment_values(started_at, ended_at, end_reason)
    if not parse_result.ok:
        return parse_result

    with connect() as connection:
        card = fetch_admin_production_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        invariant_result = validate_timing_segment_change(
            connection=connection,
            card=card,
            started_at=parsed["started_at"],
            ended_at=parsed["ended_at"],
        )
        if not invariant_result.ok:
            return invariant_result

        try:
            connection.execute(
                """
                INSERT INTO production_time_segments (card_id, started_at, ended_at, end_reason)
                VALUES (?, ?, ?, ?)
                """,
                (
                    card_id,
                    parsed["started_at"],
                    parsed["ended_at"],
                    parsed["end_reason"],
                ),
            )
            refresh_card_timing_markers(connection, card_id)
            touch_card(connection, card_id)
        except sqlite3.IntegrityError:
            connection.rollback()
            return RuleResult(False, ("Картата вече има отворен времеви сегмент.",))

    return RuleResult(True, (f"Времеви сегмент е добавен за поръчка {card['order_number']}.",))


def update_timing_segment(
    card_id: int,
    segment_id: int,
    loaded_version: int,
    started_at: str,
    ended_at: str,
    end_reason: str,
) -> RuleResult:
    parsed, parse_result = parse_timing_segment_values(started_at, ended_at, end_reason)
    if not parse_result.ok:
        return parse_result

    with connect() as connection:
        card = fetch_admin_production_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        segment = connection.execute(
            """
            SELECT id
            FROM production_time_segments
            WHERE id = ?
              AND card_id = ?
            """,
            (segment_id, card_id),
        ).fetchone()
        if not segment:
            return RuleResult(False, ("Времевият сегмент не е намерен.",))

        invariant_result = validate_timing_segment_change(
            connection=connection,
            card=card,
            started_at=parsed["started_at"],
            ended_at=parsed["ended_at"],
            segment_id=segment_id,
        )
        if not invariant_result.ok:
            return invariant_result

        try:
            connection.execute(
                """
                UPDATE production_time_segments
                SET started_at = ?,
                    ended_at = ?,
                    end_reason = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND card_id = ?
                """,
                (
                    parsed["started_at"],
                    parsed["ended_at"],
                    parsed["end_reason"],
                    segment_id,
                    card_id,
                ),
            )
            refresh_card_timing_markers(connection, card_id)
            touch_card(connection, card_id)
        except sqlite3.IntegrityError:
            connection.rollback()
            return RuleResult(False, ("Картата вече има отворен времеви сегмент.",))

    return RuleResult(True, ("Времевият сегмент е записан.",))


def delete_timing_segment(card_id: int, segment_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = fetch_admin_production_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        segment = connection.execute(
            """
            SELECT id
            FROM production_time_segments
            WHERE id = ?
              AND card_id = ?
            """,
            (segment_id, card_id),
        ).fetchone()
        if not segment:
            return RuleResult(False, ("Времевият сегмент не е намерен.",))

        delete_result = validate_timing_segment_delete(connection, card, segment_id)
        if not delete_result.ok:
            return delete_result

        if card["status"] in PRODUCTION_COMPLETE_STATUSES:
            segment_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM production_time_segments
                    WHERE card_id = ?
                    """,
                    (card_id,),
                ).fetchone()[0]
            )
            if segment_count <= 1:
                return RuleResult(
                    False,
                    ("Завършените карти трябва да запазят поне един времеви сегмент.",),
                )

        connection.execute(
            """
            DELETE FROM production_time_segments
            WHERE id = ?
              AND card_id = ?
            """,
            (segment_id, card_id),
        )
        refresh_card_timing_markers(connection, card_id)
        touch_card(connection, card_id)

    return RuleResult(True, ("Времевият сегмент е изтрит.",))


def update_admin_timing_ledger(
    card_id: int,
    loaded_version: int,
    segment_updates: dict[int, dict[str, str]],
    delete_segment_ids: set[int],
    new_segments: list[dict[str, str]],
    *,
    connection: sqlite3.Connection | None = None,
) -> RuleResult:
    if connection is not None:
        return _update_admin_timing_ledger(
            connection,
            card_id,
            loaded_version,
            segment_updates,
            delete_segment_ids,
            new_segments,
        )

    with connect() as owned_connection:
        return _update_admin_timing_ledger(
            owned_connection,
            card_id,
            loaded_version,
            segment_updates,
            delete_segment_ids,
            new_segments,
        )


def _update_admin_timing_ledger(
    connection: sqlite3.Connection,
    card_id: int,
    loaded_version: int,
    segment_updates: dict[int, dict[str, str]],
    delete_segment_ids: set[int],
    new_segments: list[dict[str, str]],
) -> RuleResult:
    card = fetch_admin_production_action_card(connection, card_id)
    version_result = validate_loaded_card_version(card, loaded_version)
    if not version_result.ok:
        return version_result

    existing_segments = connection.execute(
        """
        SELECT id, started_at, ended_at, end_reason
        FROM production_time_segments
        WHERE card_id = ?
        ORDER BY started_at, id
        """,
        (card_id,),
    ).fetchall()
    existing_ids = {int(row["id"]) for row in existing_segments}
    unknown_ids = (set(segment_updates) | delete_segment_ids) - existing_ids
    if unknown_ids:
        return RuleResult(False, ("Избран времеви сегмент не принадлежи към тази карта.",))

    parsed_updates: dict[int, dict[str, str | None]] = {}
    for segment_id, values in segment_updates.items():
        if segment_id in delete_segment_ids:
            continue
        parsed, result = parse_timing_segment_values(
            values.get("started_at", ""),
            values.get("ended_at", ""),
            values.get("end_reason", ""),
        )
        if not result.ok:
            return result
        parsed_updates[segment_id] = parsed

    parsed_new: list[dict[str, str | None]] = []
    for segment in new_segments:
        if not (
            str(segment.get("started_at") or "").strip()
            or str(segment.get("ended_at") or "").strip()
        ):
            continue
        parsed, result = parse_timing_segment_values(
            segment.get("started_at", ""),
            segment.get("ended_at", ""),
            segment.get("end_reason", ""),
        )
        if not result.ok:
            return result
        parsed_new.append(parsed)

    final_open_count = 0
    final_segment_count = len(parsed_new)
    for row in existing_segments:
        segment_id = int(row["id"])
        if segment_id in delete_segment_ids:
            continue
        values = parsed_updates.get(
            segment_id,
            {
                "started_at": str(row["started_at"]),
                "ended_at": row["ended_at"],
                "end_reason": row["end_reason"],
            },
        )
        final_segment_count += 1
        if values["ended_at"] is None:
            final_open_count += 1
    final_open_count += sum(1 for segment in parsed_new if segment["ended_at"] is None)

    if str(card["status"]) in PRODUCTION_COMPLETE_STATUSES and final_segment_count < 1:
        return RuleResult(False, ("Завършена карта трябва да има поне един времеви сегмент.",))

    if str(card["status"]) != STATUS_RUNNING and final_open_count > 0:
        return RuleResult(False, ("Само карти в изработване могат да имат отворен времеви сегмент.",))

    if str(card["status"]) == STATUS_RUNNING and final_open_count != 1:
        return RuleResult(
            False,
            ("Картите в изработване трябва да запазят един отворен времеви сегмент.",),
        )

    final_segments: list[dict[str, str | None]] = []
    for row in existing_segments:
        segment_id = int(row["id"])
        if segment_id in delete_segment_ids:
            continue
        final_segments.append(
            parsed_updates.get(
                segment_id,
                {
                    "started_at": str(row["started_at"]),
                    "ended_at": row["ended_at"],
                    "end_reason": row["end_reason"],
                },
            )
        )
    final_segments.extend(parsed_new)
    overlap_result = validate_no_overlapping_closed_segments(final_segments)
    if not overlap_result.ok:
        return overlap_result

    try:
        for segment_id in delete_segment_ids:
            connection.execute(
                """
                DELETE FROM production_time_segments
                WHERE id = ?
                  AND card_id = ?
                """,
                (segment_id, card_id),
            )

        closing_updates = [
            (segment_id, parsed)
            for segment_id, parsed in parsed_updates.items()
            if parsed["ended_at"] is not None
        ]
        opening_updates = [
            (segment_id, parsed)
            for segment_id, parsed in parsed_updates.items()
            if parsed["ended_at"] is None
        ]
        closing_new_segments = [
            parsed for parsed in parsed_new if parsed["ended_at"] is not None
        ]
        opening_new_segments = [
            parsed for parsed in parsed_new if parsed["ended_at"] is None
        ]

        for segment_id, parsed in closing_updates:
            connection.execute(
                """
                UPDATE production_time_segments
                SET started_at = ?,
                    ended_at = ?,
                    end_reason = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND card_id = ?
                """,
                (
                    parsed["started_at"],
                    parsed["ended_at"],
                    parsed["end_reason"],
                    segment_id,
                    card_id,
                ),
            )

        for parsed in closing_new_segments:
            connection.execute(
                """
                INSERT INTO production_time_segments (
                    card_id,
                    started_at,
                    ended_at,
                    end_reason
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    card_id,
                    parsed["started_at"],
                    parsed["ended_at"],
                    parsed["end_reason"],
                ),
            )

        for segment_id, parsed in opening_updates:
            connection.execute(
                """
                UPDATE production_time_segments
                SET started_at = ?,
                    ended_at = ?,
                    end_reason = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND card_id = ?
                """,
                (
                    parsed["started_at"],
                    parsed["ended_at"],
                    parsed["end_reason"],
                    segment_id,
                    card_id,
                ),
            )

        for parsed in opening_new_segments:
            connection.execute(
                """
                INSERT INTO production_time_segments (
                    card_id,
                    started_at,
                    ended_at,
                    end_reason
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    card_id,
                    parsed["started_at"],
                    parsed["ended_at"],
                    parsed["end_reason"],
                ),
            )

        connection.execute(
            """
            UPDATE cards
            SET finished_at = CASE
                    WHEN status IN (?, ?)
                    THEN (
                        SELECT MAX(ended_at)
                        FROM production_time_segments
                        WHERE card_id = ? AND ended_at IS NOT NULL
                    )
                    ELSE finished_at
                END
            WHERE id = ?
            """,
            (*PRODUCTION_COMPLETE_STATUSES, card_id, card_id),
        )
        refresh_card_timing_markers(connection, card_id)
        touch_card(connection, card_id)
    except sqlite3.IntegrityError:
        connection.rollback()
        return RuleResult(False, ("Картата вече има отворен времеви сегмент.",))

    return RuleResult(True, ("Времето е записано.",))


def validate_no_overlapping_closed_segments(
    segments: list[dict[str, str | None]],
) -> RuleResult:
    closed_segments = sorted(
        (
            segment
            for segment in segments
            if segment.get("ended_at") is not None
        ),
        key=lambda segment: (str(segment["started_at"]), str(segment["ended_at"])),
    )
    previous_end: str | None = None
    for segment in closed_segments:
        started_at = str(segment["started_at"])
        ended_at = str(segment["ended_at"])
        if previous_end is not None and started_at < previous_end:
            return RuleResult(False, ("Времевите сегменти не могат да се застъпват.",))
        previous_end = ended_at
    return RuleResult(True)


def parse_timing_segment_values(
    started_at: str,
    ended_at: str,
    end_reason: str,
) -> tuple[dict[str, str | None], RuleResult]:
    messages: list[str] = []
    cleaned_start = started_at.strip()
    cleaned_end = ended_at.strip()
    cleaned_reason = end_reason.strip()

    parsed_start = parse_timing_timestamp(cleaned_start, "Начало", messages)
    parsed_end = None
    if cleaned_end:
        parsed_end = parse_timing_timestamp(cleaned_end, "Край", messages)

    if parsed_start and parsed_end and parsed_end < parsed_start:
        messages.append("Краят не може да бъде преди началото.")

    if cleaned_end:
        if not cleaned_reason:
            messages.append("Причина е задължителна, когато е въведен край.")
        elif cleaned_reason not in TIMING_END_REASONS:
            messages.append("Причината трябва да бъде пауза, приключване или корекция.")
    elif cleaned_reason:
        messages.append("Причината трябва да е празна за отворен сегмент.")

    result = RuleResult(not messages, tuple(messages))
    if not result.ok:
        return {}, result

    assert parsed_start is not None
    return {
        "started_at": parsed_start.strftime(TIMING_TIMESTAMP_FORMAT),
        "ended_at": parsed_end.strftime(TIMING_TIMESTAMP_FORMAT) if parsed_end else None,
        "end_reason": cleaned_reason if cleaned_end else None,
    }, result


def parse_timing_timestamp(
    value: str,
    label: str,
    messages: list[str],
) -> datetime | None:
    if not value:
        messages.append(f"{label} е задължително поле.")
        return None

    try:
        return datetime.strptime(value, TIMING_TIMESTAMP_FORMAT)
    except ValueError:
        messages.append(f"{label} трябва да използва формат YYYY-MM-DD HH:MM:SS.")
        return None


def validate_timing_segment_change(
    connection: sqlite3.Connection,
    card: sqlite3.Row,
    started_at: str,
    ended_at: str | None,
    segment_id: int | None = None,
) -> RuleResult:
    if ended_at is None and card["status"] != STATUS_RUNNING:
        return RuleResult(False, ("Само карти в изработване могат да имат отворен времеви сегмент.",))

    if ended_at is None:
        query = """
            SELECT id
            FROM production_time_segments
            WHERE card_id = ?
              AND ended_at IS NULL
        """
        values: list[Any] = [card["id"]]
        if segment_id is not None:
            query += " AND id <> ?"
            values.append(segment_id)
        existing_open = connection.execute(query, values).fetchone()
        if existing_open:
            return RuleResult(False, ("Картата вече има отворен времеви сегмент.",))
    elif card["status"] == STATUS_RUNNING:
        open_segment_count = count_open_timing_segments(
            connection,
            int(card["id"]),
            exclude_segment_id=segment_id,
        )
        if open_segment_count == 0:
            return RuleResult(False, ("Картите в изработване трябва да запазят отворен времеви сегмент.",))

    if ended_at is not None:
        overlap = connection.execute(
            """
            SELECT id
            FROM production_time_segments
            WHERE card_id = ?
              AND ended_at IS NOT NULL
              AND started_at < ?
              AND ended_at > ?
              AND (? IS NULL OR id <> ?)
            LIMIT 1
            """,
            (card["id"], ended_at, started_at, segment_id, segment_id),
        ).fetchone()
        if overlap:
            return RuleResult(False, ("Времевите сегменти не могат да се застъпват.",))

    return RuleResult(True)


def validate_timing_segment_delete(
    connection: sqlite3.Connection,
    card: sqlite3.Row,
    segment_id: int,
) -> RuleResult:
    if card["status"] == STATUS_RUNNING:
        segment = connection.execute(
            """
            SELECT ended_at
            FROM production_time_segments
            WHERE id = ?
              AND card_id = ?
            """,
            (segment_id, card["id"]),
        ).fetchone()
        if segment and segment["ended_at"] is None:
            open_segment_count = count_open_timing_segments(
                connection,
                int(card["id"]),
                exclude_segment_id=segment_id,
            )
            if open_segment_count == 0:
                return RuleResult(False, ("Картите в изработване трябва да запазят отворен времеви сегмент.",))

    return RuleResult(True)


def count_open_timing_segments(
    connection: sqlite3.Connection,
    card_id: int,
    exclude_segment_id: int | None = None,
) -> int:
    query = """
        SELECT COUNT(*)
        FROM production_time_segments
        WHERE card_id = ?
          AND ended_at IS NULL
    """
    values: list[Any] = [card_id]
    if exclude_segment_id is not None:
        query += " AND id <> ?"
        values.append(exclude_segment_id)
    return int(connection.execute(query, values).fetchone()[0] or 0)


def fetch_admin_production_action_card(
    connection: sqlite3.Connection,
    card_id: int,
) -> sqlite3.Row | None:
    terminal_visible_statuses = (*ACTIVE_TERMINAL_STATUSES, *ARCHIVE_STATUSES)
    return connection.execute(
        f"""
        SELECT id, order_number, status, version
        FROM cards
        WHERE id = ?
          AND status IN ({", ".join("?" for _ in terminal_visible_statuses)})
        """,
        (card_id, *terminal_visible_statuses),
    ).fetchone()


def refresh_card_timing_markers(connection: sqlite3.Connection, card_id: int) -> None:
    first_started_at = connection.execute(
        """
        SELECT MIN(started_at)
        FROM production_time_segments
        WHERE card_id = ?
        """,
        (card_id,),
    ).fetchone()[0]
    connection.execute(
        """
        UPDATE cards
        SET first_started_at = ?
        WHERE id = ?
        """,
        (first_started_at, card_id),
    )


def touch_card(connection: sqlite3.Connection, card_id: int) -> None:
    connection.execute(
        """
        UPDATE cards
        SET version = version + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (card_id,),
    )


def fetch_active_terminal_action_card(
    connection: sqlite3.Connection,
    card_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        f"""
        SELECT id, order_number, status, machine_id, tare_weight, version
        FROM cards
        WHERE id = ?
          AND status IN ({", ".join("?" for _ in ACTIVE_TERMINAL_STATUSES)})
        """,
        (card_id, *ACTIVE_TERMINAL_STATUSES),
    ).fetchone()


def validate_card_ready_to_finish(
    connection: sqlite3.Connection,
    card_id: int,
    card: sqlite3.Row | None,
) -> RuleResult:
    if not card:
        return RuleResult(False, ("Картата не е намерена в активната опашка на терминала.",))

    segment_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM production_time_segments
        WHERE card_id = ?
        """,
        (card_id,),
    ).fetchone()[0]
    if int(segment_count or 0) == 0:
        return RuleResult(False, ("Времето трябва да бъде стартирано преди приключване.",))

    roll_rows = connection.execute(
        """
        SELECT roll_number, gross_weight, tare_weight, net_weight
        FROM roll_entries
        WHERE card_id = ?
        ORDER BY roll_number
        """,
        (card_id,),
    ).fetchall()
    gross_rolls = [roll for roll in roll_rows if roll["gross_weight"] is not None]
    if not gross_rolls:
        return RuleResult(False, ("Поне едно бруто тегло на ролка е задължително преди приключване.",))

    if any(not gross_roll_is_ready_to_finish(roll) for roll in gross_rolls):
        return RuleResult(
            False,
            ("Всяка ролка с бруто тегло трябва да има шпула преди приключване.",),
        )

    found_empty_roll = False
    for roll in roll_rows:
        if roll["gross_weight"] is None:
            found_empty_roll = True
        elif found_empty_roll:
            return RuleResult(
                False,
                ("Празните редове между ролките трябва да бъдат коригирани преди приключване.",),
            )

    return RuleResult(True)


def gross_roll_is_ready_to_finish(roll: sqlite3.Row) -> bool:
    gross = decimal_from_roll_value(roll["gross_weight"])
    tare = decimal_from_roll_value(roll["tare_weight"])
    net = decimal_from_roll_value(roll["net_weight"])
    if gross is None or tare is None or net is None:
        return False

    expected_net = net_weight_for_roll(gross, tare)
    return expected_net is not None and net == expected_net


def fetch_timing_action_card(
    connection: sqlite3.Connection,
    card_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        f"""
        SELECT id, order_number, status, machine_id, version
        FROM cards
        WHERE id = ?
          AND status IN ({", ".join("?" for _ in ACTIVE_TERMINAL_STATUSES)})
        """,
        (card_id, *ACTIVE_TERMINAL_STATUSES),
    ).fetchone()


def validate_timing_action_card(
    card: sqlite3.Row | None,
    loaded_version: int,
    expected_status: str,
    expected_status_message: str,
) -> RuleResult:
    if not card:
        return RuleResult(False, ("Картата не е намерена в активната опашка на терминала.",))

    if int(card["version"]) != loaded_version:
        return RuleResult(
            False,
            (STALE_CARD_MESSAGE,),
        )

    if not card["machine_id"]:
        return RuleResult(False, ("Картата трябва да бъде назначена към машина преди старт на времето.",))

    if card["status"] != expected_status:
        return RuleResult(False, (expected_status_message,))

    return RuleResult(True)


def fetch_open_timing_segment(
    connection: sqlite3.Connection,
    card_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT id, started_at
        FROM production_time_segments
        WHERE card_id = ?
          AND ended_at IS NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        (card_id,),
    ).fetchone()


def fetch_occupied_machine_card(
    connection: sqlite3.Connection,
    card_id: int,
    machine_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT id, order_number, status
        FROM cards
        WHERE id <> ?
          AND machine_id = ?
          AND status = ?
        ORDER BY machine_sequence IS NULL, machine_sequence, id
        LIMIT 1
        """,
        (card_id, machine_id, STATUS_RUNNING),
    ).fetchone()


def has_open_timing_segment(connection: sqlite3.Connection, card_id: int) -> bool:
    return fetch_open_timing_segment(connection, card_id) is not None


def current_database_timestamp(connection: sqlite3.Connection) -> str:
    return str(connection.execute("SELECT CURRENT_TIMESTAMP").fetchone()[0])


def decimal_from_database(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def decimal_to_storage(value: Decimal) -> str:
    return format(value, "f")


def decimal_to_display(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def parse_weight(value: str, field_name: str, *, allow_blank: bool) -> tuple[Decimal | None, str | None]:
    cleaned = value.strip()
    if not cleaned:
        if allow_blank:
            return None, None
        return None, f"{field_name} е задължително поле."

    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        return None, f"{field_name} трябва да е число."

    if not parsed.is_finite():
        return None, f"{field_name} трябва да е число."

    if parsed < 0:
        return None, f"{field_name} трябва да е 0 или по-голямо."

    if parsed.as_tuple().exponent < -2:
        return None, f"{field_name} поддържа най-много два знака след десетичната запетая."

    return parsed, None


def validate_loaded_card_version(card: sqlite3.Row | None, loaded_version: int) -> RuleResult:
    if not card:
        return RuleResult(False, ("Картата не е намерена.",))

    if int(card["version"]) != loaded_version:
        return RuleResult(False, (STALE_CARD_MESSAGE,))

    return RuleResult(True)


def net_weight_for_roll(
    gross_weight: Decimal | None,
    tare_weight: Decimal | None,
) -> Decimal | None:
    if gross_weight is None or tare_weight is None:
        return None

    net_weight = gross_weight - tare_weight
    if net_weight < 0:
        return None
    return net_weight


def update_tare_weight(card_id: int, loaded_version: int, tare_weight: str) -> RuleResult:
    parsed_tare, parse_error = parse_weight(
        tare_weight,
        "Шпула",
        allow_blank=True,
    )
    if parse_error:
        return RuleResult(False, (parse_error,))

    with connect() as connection:
        card = connection.execute(
            f"""
            SELECT id, order_number, version
            FROM cards
            WHERE id = ?
              AND status IN ({TERMINAL_ACTION_STATUS_PLACEHOLDERS})
            """,
            (card_id, *TERMINAL_ACTION_STATUSES),
        ).fetchone()

        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        connection.execute(
            """
            UPDATE cards
            SET tare_weight = ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                decimal_to_storage(parsed_tare) if parsed_tare is not None else None,
                card_id,
            ),
        )

    message = "Шпулата е изчистена." if parsed_tare is None else "Шпулата е записана."
    return RuleResult(True, (message,))


def add_roll_gross_weight(
    card_id: int,
    loaded_version: int,
    gross_weight: str,
    tare_weight: str | None = None,
) -> RuleResult:
    parsed_gross, parse_error = parse_weight(
        gross_weight,
        "Бруто тегло",
        allow_blank=False,
    )
    if parse_error:
        return RuleResult(False, (parse_error,))
    assert parsed_gross is not None

    parsed_submitted_tare: Decimal | None = None
    if tare_weight is not None:
        parsed_submitted_tare, tare_parse_error = parse_weight(
            tare_weight,
            "Шпула",
            allow_blank=True,
        )
        if tare_parse_error:
            return RuleResult(False, (tare_parse_error,))

    with connect() as connection:
        card = fetch_roll_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        roll_entry_result = validate_card_allows_roll_entry(card)
        if not roll_entry_result.ok:
            return roll_entry_result

        default_tare = (
            parsed_submitted_tare
            if tare_weight is not None
            else decimal_from_database(card["tare_weight"])
        )
        if default_tare is None:
            return RuleResult(False, ("Въведете шпула преди да добавите ролка.",))

        net = net_weight_for_roll(parsed_gross, default_tare)
        if default_tare is not None and net is None:
            return RuleResult(
                False,
                ("Бруто теглото не може да бъде по-малко от шпулата.",),
            )

        next_roll_number = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(roll_number), 0) + 1
                FROM roll_entries
                WHERE card_id = ?
                """,
                (card_id,),
            ).fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO roll_entries (
                card_id,
                order_number,
                roll_number,
                gross_weight,
                tare_weight,
                net_weight
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                card["order_number"],
                next_roll_number,
                decimal_to_storage(parsed_gross),
                decimal_to_storage(default_tare) if default_tare is not None else None,
                decimal_to_storage(net) if net is not None else None,
            ),
        )
        if tare_weight is not None:
            connection.execute(
                """
                UPDATE cards
                SET tare_weight = ?,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    decimal_to_storage(default_tare) if default_tare is not None else None,
                    card_id,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE cards
                SET version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (card_id,),
            )

    return RuleResult(True, (f"Ролка {next_roll_number} е записана.",))


def update_roll_weight(
    card_id: int,
    roll_id: int,
    loaded_version: int,
    gross_weight: str,
    tare_weight: str,
) -> RuleResult:
    parsed_gross, parse_error = parse_weight(
        gross_weight,
        "Бруто тегло",
        allow_blank=True,
    )
    if parse_error:
        return RuleResult(False, (parse_error,))

    parsed_tare, tare_parse_error = parse_weight(
        tare_weight,
        "Шпула",
        allow_blank=True,
    )
    if tare_parse_error:
        return RuleResult(False, (tare_parse_error,))

    with connect() as connection:
        card = fetch_roll_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        roll_entry_result = validate_card_allows_roll_entry(card)
        if not roll_entry_result.ok:
            return roll_entry_result

        roll = connection.execute(
            """
            SELECT id, roll_number, gross_weight, tare_weight
            FROM roll_entries
            WHERE id = ?
              AND card_id = ?
            """,
            (roll_id, card_id),
        ).fetchone()
        if not roll:
            return RuleResult(False, ("Ролката не е намерена.",))

        if (
            card["status"] in PRODUCTION_COMPLETE_STATUSES
            and parsed_gross is None
            and roll["gross_weight"] is not None
        ):
            gross_roll_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM roll_entries
                    WHERE card_id = ?
                      AND gross_weight IS NOT NULL
                    """,
                    (card_id,),
                ).fetchone()[0]
            )
            if gross_roll_count <= 1:
                return RuleResult(
                    False,
                    ("Завършените карти трябва да запазят поне едно бруто тегло на ролка.",),
                )

        net = net_weight_for_roll(parsed_gross, parsed_tare)
        if parsed_gross is not None and parsed_tare is not None and net is None:
            return RuleResult(
                False,
                ("Бруто теглото не може да бъде по-малко от шпулата.",),
            )

        connection.execute(
            """
            UPDATE roll_entries
            SET gross_weight = ?,
                tare_weight = ?,
                net_weight = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                decimal_to_storage(parsed_gross) if parsed_gross is not None else None,
                decimal_to_storage(parsed_tare) if parsed_tare is not None else None,
                decimal_to_storage(net) if net is not None else None,
                roll_id,
            ),
        )
        connection.execute(
            """
            UPDATE cards
            SET version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (card_id,),
        )

    return RuleResult(True, (f"Ролка {roll['roll_number']} е записана.",))


def update_terminal_roll_corrections(
    card_id: int,
    loaded_version: int,
    roll_updates: dict[int, dict[str, str]],
) -> RuleResult:
    with connect() as connection:
        card = fetch_roll_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        roll_entry_result = validate_card_allows_roll_entry(card)
        if not roll_entry_result.ok:
            return roll_entry_result

        existing_rolls = connection.execute(
            """
            SELECT id, gross_weight, tare_weight
            FROM roll_entries
            WHERE card_id = ?
            ORDER BY roll_number, id
            """,
            (card_id,),
        ).fetchall()
        existing_ids = {int(roll["id"]) for roll in existing_rolls}
        unknown_ids = set(roll_updates) - existing_ids
        if unknown_ids:
            return RuleResult(False, ("Избрана ролка не принадлежи към тази карта.",))

        changed_updates: dict[int, tuple[Decimal | None, Decimal | None, Decimal | None]] = {}
        gross_roll_count = 0
        for roll in existing_rolls:
            roll_id = int(roll["id"])
            existing_gross = decimal_from_database(roll["gross_weight"])
            existing_tare = decimal_from_database(roll["tare_weight"])
            submitted = roll_updates.get(roll_id, {})
            gross_text = submitted.get(
                "gross_weight",
                decimal_to_storage(existing_gross) if existing_gross is not None else "",
            )
            tare_text = submitted.get(
                "tare_weight",
                decimal_to_storage(existing_tare) if existing_tare is not None else "",
            )

            parsed_gross, parse_error = parse_weight(
                gross_text,
                "Бруто тегло",
                allow_blank=True,
            )
            if parse_error:
                return RuleResult(False, (parse_error,))
            parsed_tare, parse_error = parse_weight(
                tare_text,
                "Шпула",
                allow_blank=True,
            )
            if parse_error:
                return RuleResult(False, (parse_error,))

            net = net_weight_for_roll(parsed_gross, parsed_tare)
            if parsed_gross is not None:
                gross_roll_count += 1
            if parsed_gross is not None and parsed_tare is not None and net is None:
                return RuleResult(
                    False,
                    ("Бруто теглото не може да бъде по-малко от шпулата.",),
                )

            if parsed_gross != existing_gross or parsed_tare != existing_tare:
                changed_updates[roll_id] = (parsed_gross, parsed_tare, net)

        if str(card["status"]) in PRODUCTION_COMPLETE_STATUSES and gross_roll_count < 1:
            return RuleResult(
                False,
                ("Завършените карти трябва да запазят поне едно бруто тегло на ролка.",),
            )

        if changed_updates:
            for roll_id, (gross, tare, net) in changed_updates.items():
                connection.execute(
                    """
                    UPDATE roll_entries
                    SET gross_weight = ?,
                        tare_weight = ?,
                        net_weight = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                      AND card_id = ?
                    """,
                    (
                        decimal_to_storage(gross) if gross is not None else None,
                        decimal_to_storage(tare) if tare is not None else None,
                        decimal_to_storage(net) if net is not None else None,
                        roll_id,
                        card_id,
                    ),
                )
            connection.execute(
                """
                UPDATE cards
                SET version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (card_id,),
            )

    return RuleResult(True, ("Ролките са записани.",))


def update_roll_gross_weight(
    card_id: int,
    roll_id: int,
    loaded_version: int,
    gross_weight: str,
) -> RuleResult:
    with connect() as connection:
        roll = connection.execute(
            """
            SELECT tare_weight
            FROM roll_entries
            WHERE id = ?
              AND card_id = ?
            """,
            (roll_id, card_id),
        ).fetchone()
    if not roll:
        return RuleResult(False, ("Ролката не е намерена.",))
    existing_tare = decimal_from_database(roll["tare_weight"])
    return update_roll_weight(
        card_id=card_id,
        roll_id=roll_id,
        loaded_version=loaded_version,
        gross_weight=gross_weight,
        tare_weight=decimal_to_storage(existing_tare) if existing_tare is not None else "",
    )


def delete_roll_entry(card_id: int, roll_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = fetch_roll_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        roll_entry_result = validate_card_allows_roll_entry(card)
        if not roll_entry_result.ok:
            return roll_entry_result

        roll = connection.execute(
            """
            SELECT id, roll_number, gross_weight
            FROM roll_entries
            WHERE id = ?
              AND card_id = ?
            """,
            (roll_id, card_id),
        ).fetchone()
        if not roll:
            return RuleResult(False, ("Ролката не е намерена.",))

        if card["status"] in PRODUCTION_COMPLETE_STATUSES and roll["gross_weight"] is not None:
            gross_roll_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM roll_entries
                    WHERE card_id = ?
                      AND gross_weight IS NOT NULL
                    """,
                    (card_id,),
                ).fetchone()[0]
            )
            if gross_roll_count <= 1:
                return RuleResult(
                    False,
                    ("Завършените карти трябва да запазят поне едно бруто тегло на ролка.",),
                )

        deleted_roll_number = int(roll["roll_number"])
        max_roll_number = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(roll_number), 0)
                FROM roll_entries
                WHERE card_id = ?
                """,
                (card_id,),
            ).fetchone()[0]
        )
        renumber_offset = max_roll_number + 1

        connection.execute(
            """
            DELETE FROM roll_entries
            WHERE id = ?
              AND card_id = ?
            """,
            (roll_id, card_id),
        )
        connection.execute(
            """
            UPDATE roll_entries
            SET roll_number = roll_number + ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE card_id = ?
              AND roll_number > ?
            """,
            (renumber_offset, card_id, deleted_roll_number),
        )
        connection.execute(
            """
            UPDATE roll_entries
            SET roll_number = roll_number - ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE card_id = ?
              AND roll_number > ?
            """,
            (renumber_offset + 1, card_id, renumber_offset),
        )
        connection.execute(
            """
            UPDATE cards
            SET version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (card_id,),
        )

    return RuleResult(True, (f"Ролка {deleted_roll_number} е изтрита. Оставащите ролки са преномерирани.",))


def update_admin_roll_ledger(
    card_id: int,
    loaded_version: int,
    tare_weight: str,
    roll_updates: dict[int, dict[str, str]],
    delete_roll_ids: set[int],
    new_gross_weights: list[str],
    *,
    connection: sqlite3.Connection | None = None,
) -> RuleResult:
    if connection is not None:
        return _update_admin_roll_ledger(
            connection,
            card_id,
            loaded_version,
            tare_weight,
            roll_updates,
            delete_roll_ids,
            new_gross_weights,
        )

    with connect() as owned_connection:
        return _update_admin_roll_ledger(
            owned_connection,
            card_id,
            loaded_version,
            tare_weight,
            roll_updates,
            delete_roll_ids,
            new_gross_weights,
        )


def _update_admin_roll_ledger(
    connection: sqlite3.Connection,
    card_id: int,
    loaded_version: int,
    tare_weight: str,
    roll_updates: dict[int, dict[str, str]],
    delete_roll_ids: set[int],
    new_gross_weights: list[str],
) -> RuleResult:
    parsed_tare, parse_error = parse_weight(tare_weight, "Шпула", allow_blank=True)
    if parse_error:
        return RuleResult(False, (parse_error,))

    card = connection.execute(
        f"""
        SELECT id, order_number, status, tare_weight, version
        FROM cards
        WHERE id = ?
          AND status IN ({TERMINAL_ACTION_STATUS_PLACEHOLDERS})
        """,
        (card_id, *TERMINAL_ACTION_STATUSES),
    ).fetchone()
    version_result = validate_loaded_card_version(card, loaded_version)
    if not version_result.ok:
        return version_result

    existing_rolls = connection.execute(
        """
        SELECT id, roll_number, gross_weight, tare_weight
        FROM roll_entries
        WHERE card_id = ?
        ORDER BY roll_number
        """,
        (card_id,),
    ).fetchall()
    existing_ids = {int(row["id"]) for row in existing_rolls}
    unknown_ids = (set(roll_updates) | delete_roll_ids) - existing_ids
    if unknown_ids:
        return RuleResult(False, ("Избрана ролка не принадлежи към тази карта.",))
    existing_values_by_id = {
        int(row["id"]): {
            "gross_weight": decimal_from_database(row["gross_weight"]),
            "tare_weight": decimal_from_database(row["tare_weight"]),
        }
        for row in existing_rolls
    }

    parsed_updates: dict[int, dict[str, Decimal | None]] = {}
    for roll_id, values in roll_updates.items():
        if roll_id in delete_roll_ids:
            continue
        current = existing_values_by_id[roll_id]
        gross_text = values.get(
            "gross_weight",
            decimal_to_storage(current["gross_weight"])
            if current["gross_weight"] is not None
            else "",
        )
        tare_text = values.get(
            "tare_weight",
            decimal_to_storage(current["tare_weight"])
            if current["tare_weight"] is not None
            else "",
        )
        parsed_gross, parse_error = parse_weight(
            gross_text,
            "Бруто тегло",
            allow_blank=True,
        )
        if parse_error:
            return RuleResult(False, (parse_error,))
        parsed_row_tare, parse_error = parse_weight(
            tare_text,
            "Шпула",
            allow_blank=True,
        )
        if parse_error:
            return RuleResult(False, (parse_error,))
        parsed_updates[roll_id] = {
            "gross_weight": parsed_gross,
            "tare_weight": parsed_row_tare,
        }

    parsed_new: list[Decimal] = []
    for gross_weight in new_gross_weights:
        if not str(gross_weight).strip():
            continue
        parsed_gross, parse_error = parse_weight(
            gross_weight,
            "Бруто тегло",
            allow_blank=False,
        )
        if parse_error:
            return RuleResult(False, (parse_error,))
        assert parsed_gross is not None
        parsed_new.append(parsed_gross)

    roll_mutation_requested = bool(delete_roll_ids or parsed_new)
    if not roll_mutation_requested:
        roll_mutation_requested = any(
            parsed_values["gross_weight"]
            != existing_values_by_id[roll_id]["gross_weight"]
            or parsed_values["tare_weight"]
            != existing_values_by_id[roll_id]["tare_weight"]
            for roll_id, parsed_values in parsed_updates.items()
        )

    if roll_mutation_requested:
        roll_entry_result = validate_card_allows_roll_entry(card)
        if not roll_entry_result.ok:
            return roll_entry_result

    remaining_updates: dict[
        int,
        tuple[Decimal | None, Decimal | None, Decimal | None],
    ] = {}
    gross_roll_count = len(parsed_new)
    for roll in existing_rolls:
        roll_id = int(roll["id"])
        if roll_id in delete_roll_ids:
            continue
        parsed_values = parsed_updates.get(roll_id)
        if parsed_values is None:
            gross = decimal_from_database(roll["gross_weight"])
            row_tare = decimal_from_database(roll["tare_weight"])
        else:
            gross = parsed_values["gross_weight"]
            row_tare = parsed_values["tare_weight"]
        if gross is not None:
            gross_roll_count += 1
        net = net_weight_for_roll(gross, row_tare)
        if gross is not None and row_tare is not None and net is None:
            return RuleResult(
                False,
                ("Бруто теглото не може да бъде по-малко от шпулата.",),
            )
        remaining_updates[roll_id] = (gross, row_tare, net)

    for gross in parsed_new:
        net = net_weight_for_roll(gross, parsed_tare)
        if parsed_tare is not None and net is None:
            return RuleResult(
                False,
                ("Бруто теглото не може да бъде по-малко от шпулата.",),
            )

    if str(card["status"]) in PRODUCTION_COMPLETE_STATUSES and gross_roll_count < 1:
        return RuleResult(
            False,
            ("Завършените карти трябва да запазят поне едно бруто тегло на ролка.",),
        )

    connection.execute(
        """
        UPDATE cards
        SET tare_weight = ?,
            version = version + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            decimal_to_storage(parsed_tare) if parsed_tare is not None else None,
            card_id,
        ),
    )

    for roll_id in delete_roll_ids:
        connection.execute(
            """
            DELETE FROM roll_entries
            WHERE id = ?
              AND card_id = ?
            """,
            (roll_id, card_id),
        )

    for roll_id, (gross, row_tare, net) in remaining_updates.items():
        connection.execute(
            """
            UPDATE roll_entries
            SET gross_weight = ?,
                tare_weight = ?,
                net_weight = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND card_id = ?
            """,
            (
                decimal_to_storage(gross) if gross is not None else None,
                decimal_to_storage(row_tare) if row_tare is not None else None,
                decimal_to_storage(net) if net is not None else None,
                roll_id,
                card_id,
            ),
        )

    next_roll_number = int(
        connection.execute(
            """
            SELECT COALESCE(MAX(roll_number), 0) + 1 AS next_roll_number
            FROM roll_entries
            WHERE card_id = ?
            """,
            (card_id,),
        ).fetchone()["next_roll_number"]
    )
    for gross in parsed_new:
        net = net_weight_for_roll(gross, parsed_tare)
        connection.execute(
            """
            INSERT INTO roll_entries (
                card_id,
                order_number,
                roll_number,
                gross_weight,
                tare_weight,
                net_weight
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                str(card["order_number"]),
                next_roll_number,
                decimal_to_storage(gross),
                decimal_to_storage(parsed_tare) if parsed_tare is not None else None,
                decimal_to_storage(net) if net is not None else None,
            ),
        )
        next_roll_number += 1

    remaining_rolls = connection.execute(
        """
        SELECT id
        FROM roll_entries
        WHERE card_id = ?
        ORDER BY roll_number, id
        """,
        (card_id,),
    ).fetchall()
    for roll_number, roll in enumerate(remaining_rolls, start=1):
        connection.execute(
            """
            UPDATE roll_entries
            SET roll_number = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (roll_number, int(roll["id"])),
        )

    return RuleResult(True, ("Ролките са записани.",))


def fetch_roll_action_card(
    connection: sqlite3.Connection,
    card_id: int,
) -> sqlite3.Row | None:
    roll_edit_statuses = (*ACTIVE_TERMINAL_STATUSES, *PRODUCTION_COMPLETE_STATUSES)
    return connection.execute(
        f"""
        SELECT id, order_number, status, tare_weight, version
        FROM cards
        WHERE id = ?
          AND status IN ({", ".join("?" for _ in roll_edit_statuses)})
        """,
        (card_id, *roll_edit_statuses),
    ).fetchone()


def validate_card_allows_roll_entry(card: sqlite3.Row | None) -> RuleResult:
    if not card:
        return RuleResult(False, ("Картата не е намерена за въвеждане на ролка.",))

    if card["status"] not in (STATUS_RUNNING, *PRODUCTION_COMPLETE_STATUSES):
        return RuleResult(
            False,
            ("Теглата на ролките могат да се променят само когато картата е в изработване, произведена или завършена.",),
        )

    return RuleResult(True)


def update_admin_imported_fields(
    card_id: int,
    loaded_version: int,
    fields: dict[str, str],
    *,
    connection: sqlite3.Connection | None = None,
) -> RuleResult:
    if connection is not None:
        return _update_admin_imported_fields(connection, card_id, loaded_version, fields)

    with connect() as owned_connection:
        return _update_admin_imported_fields(owned_connection, card_id, loaded_version, fields)


def _update_admin_imported_fields(
    connection: sqlite3.Connection,
    card_id: int,
    loaded_version: int,
    fields: dict[str, str],
) -> RuleResult:
    from .importer import IMPORT_FIELDS, card_has_usable_extrusion_step

    cleaned_fields = {field: str(fields.get(field, "")).strip() for field in IMPORT_FIELDS}
    submitted_max_roll_weight = (
        str(fields["max_roll_weight"]).strip() if "max_roll_weight" in fields else None
    )
    if not cleaned_fields["order_number"]:
        return RuleResult(False, ("Номерът на поръчката е задължителен.",))

    if not card_has_usable_extrusion_step(cleaned_fields):
        return RuleResult(
            False,
            ("Импортираните полета трябва да запазят валидна стъпка за екструдиране преди запис.",),
        )

    card = connection.execute(
        """
        SELECT id, order_number, max_roll_weight, version
        FROM cards
        WHERE id = ?
        """,
        (card_id,),
    ).fetchone()
    version_result = validate_loaded_card_version(card, loaded_version)
    if not version_result.ok:
        return version_result

    duplicate = connection.execute(
        """
        SELECT id
        FROM cards
        WHERE order_number = ?
          AND id <> ?
        """,
        (cleaned_fields["order_number"], card_id),
    ).fetchone()
    if duplicate:
        return RuleResult(False, ("Номерът на поръчката вече съществува в друга карта.",))

    assignments = [
        *(f"{field} = ?" for field in IMPORT_FIELDS),
        "max_roll_weight = ?",
        "version = version + 1",
        "updated_at = CURRENT_TIMESTAMP",
    ]
    max_roll_weight = (
        submitted_max_roll_weight
        if submitted_max_roll_weight is not None
        else str(card["max_roll_weight"] or "").strip()
    )
    values: list[Any] = [
        *(cleaned_fields[field] for field in IMPORT_FIELDS),
        max_roll_weight,
        card_id,
    ]

    try:
        connection.execute(
            f"""
            UPDATE cards
            SET {", ".join(assignments)}
            WHERE id = ?
            """,
            values,
        )
        if cleaned_fields["order_number"] != card["order_number"]:
            connection.execute(
                """
                UPDATE roll_entries
                SET order_number = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE card_id = ?
                """,
                (cleaned_fields["order_number"], card_id),
            )
        sync_recipe_components_for_card(connection, card_id, cleaned_fields)
    except sqlite3.IntegrityError:
        connection.rollback()
        return RuleResult(False, ("Номерът на поръчката вече съществува в друга карта.",))

    return RuleResult(True, ("Данните на технологичната карта са записани.",))


def delete_admin_imported_card(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = connection.execute(
            """
            SELECT id, order_number, status, version
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        if card["status"] != STATUS_IMPORTED:
            return RuleResult(False, ("Само неизпратени импортирани технологични карти могат да се изтриват.",))

        roll_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM roll_entries WHERE card_id = ?",
                (card_id,),
            ).fetchone()[0]
        )
        segment_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM production_time_segments WHERE card_id = ?",
                (card_id,),
            ).fetchone()[0]
        )
        if roll_count or segment_count:
            return RuleResult(False, ("Технологични карти с производствени данни не могат да се изтриват.",))

        connection.execute("DELETE FROM cards WHERE id = ?", (card_id,))

    return RuleResult(True, (f"Поръчка {card['order_number']} е изтрита.",))


def update_terminal_material_fields(
    card_id: int,
    loaded_version: int,
    actual_raw_material_used: str,
    raw_material_brand_grade: str,
    raw_material_batch_lot: str,
) -> RuleResult:
    with connect() as connection:
        card = connection.execute(
            f"""
            SELECT id, version, raw_material_a
            FROM cards
            WHERE id = ?
              AND status IN ({TERMINAL_ACTION_STATUS_PLACEHOLDERS})
            """,
            (card_id, *TERMINAL_ACTION_STATUSES),
        ).fetchone()

        if not card:
            return RuleResult(False, ("Картата не е намерена.",))

        if int(card["version"]) != loaded_version:
            return RuleResult(
                False,
                (STALE_CARD_MESSAGE,),
            )

        connection.execute(
            """
            UPDATE cards
            SET actual_raw_material_used = ?,
                raw_material_brand_grade = ?,
                raw_material_batch_lot = ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                actual_raw_material_used.strip(),
                raw_material_brand_grade.strip(),
                raw_material_batch_lot.strip(),
                card_id,
            ),
        )
        _upsert_recipe_actual_entry(
            connection,
            card,
            "raw_material_a",
            dict(RECIPE_COMPONENT_FIELDS)["raw_material_a"],
            actual_raw_material_used,
            raw_material_batch_lot,
        )

    return RuleResult(True, ("Материалите са записани.",))


def _upsert_recipe_actual_entry(
    connection: sqlite3.Connection,
    card: sqlite3.Row,
    component_key: str,
    component_label: str,
    actual_material: str,
    batch_lot: str,
) -> None:
    planned_material = str(card[component_key] or "")
    connection.execute(
        """
        INSERT INTO recipe_actual_entries (
            card_id, component_key, component_label, planned_material,
            actual_material_used, batch_lot
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(card_id, component_key) DO UPDATE SET
            component_label = excluded.component_label,
            planned_material = excluded.planned_material,
            actual_material_used = excluded.actual_material_used,
            batch_lot = excluded.batch_lot,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            int(card["id"]),
            component_key,
            component_label,
            planned_material,
            actual_material.strip(),
            batch_lot.strip(),
        ),
    )


def update_terminal_recipe_actual_entries(
    card_id: int,
    loaded_version: int,
    entries: dict[str, dict[str, str]],
    raw_material_brand_grade: str | None = None,
) -> RuleResult:
    component_labels = dict(RECIPE_COMPONENT_FIELDS)
    unknown_keys = sorted(set(entries) - set(component_labels))
    if unknown_keys:
        return RuleResult(False, ("Формата съдържа непознат ред от рецептата.",))

    import_columns = ", ".join(component_labels)
    with connect() as connection:
        card = connection.execute(
            f"""
            SELECT id,
                   version,
                   actual_raw_material_used,
                   raw_material_brand_grade,
                   raw_material_batch_lot,
                   {import_columns}
            FROM cards
            WHERE id = ?
              AND status IN ({TERMINAL_ACTION_STATUS_PLACEHOLDERS})
            """,
            (card_id, *TERMINAL_ACTION_STATUSES),
        ).fetchone()

        if not card:
            return RuleResult(False, ("Картата не е намерена.",))

        if int(card["version"]) != loaded_version:
            return RuleResult(False, (STALE_CARD_MESSAGE,))

        for component_key, entry in entries.items():
            component_label = component_labels[component_key]
            actual_material = str(entry.get("actual_material_used") or "").strip()
            batch_lot = str(entry.get("batch_lot") or "").strip()
            _upsert_recipe_actual_entry(
                connection,
                card,
                component_key,
                component_label,
                actual_material,
                batch_lot,
            )

        if "raw_material_a" in entries:
            raw_material_entry = entries["raw_material_a"]
            raw_material_used = str(
                raw_material_entry.get("actual_material_used") or ""
            ).strip()
            raw_material_batch_lot = str(raw_material_entry.get("batch_lot") or "").strip()
        else:
            raw_material_used = str(card["actual_raw_material_used"] or "")
            raw_material_batch_lot = str(card["raw_material_batch_lot"] or "")
        if raw_material_brand_grade is None:
            raw_material_brand_grade = str(card["raw_material_brand_grade"] or "")

        connection.execute(
            """
            UPDATE cards
            SET actual_raw_material_used = ?,
                raw_material_brand_grade = ?,
                raw_material_batch_lot = ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                raw_material_used,
                raw_material_brand_grade.strip(),
                raw_material_batch_lot,
                card_id,
            ),
        )

    return RuleResult(True, ("Материалите са записани.",))


def update_admin_material_ledger(
    card_id: int,
    loaded_version: int,
    planned_materials: dict[str, str],
    actual_entries: dict[str, dict[str, str]],
    raw_material_brand_grade: str | None = None,
    *,
    connection: sqlite3.Connection | None = None,
) -> RuleResult:
    if connection is not None:
        return _update_admin_material_ledger(
            connection,
            card_id,
            loaded_version,
            planned_materials,
            actual_entries,
            raw_material_brand_grade,
        )

    with connect() as owned_connection:
        return _update_admin_material_ledger(
            owned_connection,
            card_id,
            loaded_version,
            planned_materials,
            actual_entries,
            raw_material_brand_grade,
        )


def _update_admin_material_ledger(
    connection: sqlite3.Connection,
    card_id: int,
    loaded_version: int,
    planned_materials: dict[str, str],
    actual_entries: dict[str, dict[str, str]],
    raw_material_brand_grade: str | None = None,
) -> RuleResult:
    component_labels = dict(RECIPE_COMPONENT_FIELDS)
    unknown_keys = sorted((set(planned_materials) | set(actual_entries)) - set(component_labels))
    if unknown_keys:
        return RuleResult(False, ("Формата съдържа непознат ред от рецептата.",))

    import_columns = ", ".join(ADMIN_MATERIAL_FIELDS)
    card = connection.execute(
        f"""
        SELECT id, version, raw_material_brand_grade, {import_columns}
        FROM cards
        WHERE id = ?
          AND status IN ({TERMINAL_ACTION_STATUS_PLACEHOLDERS})
        """,
        (card_id, *TERMINAL_ACTION_STATUSES),
    ).fetchone()
    version_result = validate_loaded_card_version(card, loaded_version)
    if not version_result.ok:
        return version_result

    cleaned_planned = {
        field: str(planned_materials.get(field) or "").strip()
        for field in ADMIN_MATERIAL_FIELDS
    }
    raw_material_entry = actual_entries.get("raw_material_a", {})
    raw_material_used = str(
        raw_material_entry.get("actual_material_used") or ""
    ).strip()
    raw_material_batch_lot = str(raw_material_entry.get("batch_lot") or "").strip()
    if raw_material_brand_grade is None:
        raw_material_brand_grade = str(card["raw_material_brand_grade"] or "")

    connection.execute(
        """
        UPDATE cards
        SET raw_material_a = ?,
            raw_material_b = ?,
            raw_material_c = ?,
            linear_pe = ?,
            antistatic = ?,
            masterbatch = ?,
            chalk = ?,
            actual_raw_material_used = ?,
            raw_material_brand_grade = ?,
            raw_material_batch_lot = ?,
            version = version + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            cleaned_planned["raw_material_a"],
            cleaned_planned["raw_material_b"],
            cleaned_planned["raw_material_c"],
            cleaned_planned["linear_pe"],
            cleaned_planned["antistatic"],
            cleaned_planned["masterbatch"],
            cleaned_planned["chalk"],
            raw_material_used,
            raw_material_brand_grade.strip(),
            raw_material_batch_lot,
            card_id,
        ),
    )

    sync_recipe_components_for_card(connection, card_id, cleaned_planned)

    for component_key, component_label in RECIPE_COMPONENT_FIELDS:
        entry = actual_entries.get(component_key, {})
        connection.execute(
            """
            INSERT INTO recipe_actual_entries (
                card_id, component_key, component_label, planned_material,
                actual_material_used, batch_lot
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(card_id, component_key) DO UPDATE SET
                component_label = excluded.component_label,
                planned_material = excluded.planned_material,
                actual_material_used = excluded.actual_material_used,
                batch_lot = excluded.batch_lot,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                card_id,
                component_key,
                component_label,
                cleaned_planned.get(component_key, ""),
                str(entry.get("actual_material_used") or "").strip(),
                str(entry.get("batch_lot") or "").strip(),
            ),
        )

    return RuleResult(True, ("Материалите са записани.",))


def release_card(
    card_id: int,
    machine_id: int,
    machine_sequence: int,
    loaded_version: int | None = None,
    max_roll_weight: str | None = None,
) -> RuleResult:
    from .importer import IMPORT_FIELDS, card_has_usable_extrusion_step

    messages: list[str] = []
    import_columns = ", ".join(IMPORT_FIELDS)

    with connect() as connection:
        card = connection.execute(
            f"""
            SELECT id, order_number, status, version, max_roll_weight, {import_columns}
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()

        if not card:
            return RuleResult(False, ("Картата не е намерена.",))

        if loaded_version is not None:
            version_result = validate_loaded_card_version(card, loaded_version)
            if not version_result.ok:
                return version_result

        if card["status"] != STATUS_IMPORTED:
            messages.append("Само импортирани технологични карти могат да се изпращат.")

        card_fields = {field: str(card[field] or "") for field in IMPORT_FIELDS}
        if not card_has_usable_extrusion_step(card_fields):
            messages.append("Картата трябва да има валидна стъпка за екструдиране преди изпращане.")
        recipe_release_result = validate_structured_recipe_release(card_fields)
        messages.extend(recipe_release_result.messages)

        release_max_roll_weight = (
            str(max_roll_weight).strip()
            if max_roll_weight is not None
            else str(card["max_roll_weight"] or "").strip()
        )

        machine_exists = connection.execute(
            "SELECT 1 FROM machines WHERE id = ?",
            (machine_id,),
        ).fetchone()
        if not machine_exists:
            messages.append("Изберете валидна машина.")

        if machine_sequence < 1:
            messages.append("Редът трябва да е 1 или по-голям.")

        if messages:
            return RuleResult(False, tuple(messages))

        try:
            temporary_sequence = -int(card["id"])
            connection.execute(
                """
                UPDATE cards
                SET status = ?,
                    machine_id = ?,
                    machine_sequence = ?,
                    max_roll_weight = ?
                WHERE id = ?
                """,
                (
                    STATUS_PENDING,
                    machine_id,
                    temporary_sequence,
                    release_max_roll_weight,
                    card_id,
                ),
            )
            final_sequence = normalize_machine_queue(
                connection,
                machine_id=machine_id,
                moving_card_id=card_id,
                target_position=machine_sequence,
            )
        except sqlite3.IntegrityError:
            connection.rollback()
            return RuleResult(
                False,
                ("Изпращането не бе записано, защото тази машина и ред вече са заети.",),
            )

    return RuleResult(
        True,
        (f"Поръчка {card['order_number']} е изпратена към машина {machine_id}, ред {final_sequence}.",),
    )


def update_card_planning(
    card_id: int,
    loaded_version: int,
    machine_id: int,
    machine_sequence: int,
) -> RuleResult:
    with connect() as connection:
        card = connection.execute(
            """
            SELECT id, order_number, status, machine_id, machine_sequence, version,
                   tare_weight, actual_raw_material_used, raw_material_brand_grade,
                   raw_material_batch_lot, first_started_at, finished_at, cancelled_at
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        if card["status"] not in ACTIVE_TERMINAL_STATUSES:
            return RuleResult(
                False,
                ("Само активни технологични карти могат да се преместват.",),
            )

        messages: list[str] = []
        if card["machine_id"] is None:
            messages.append("Картата трябва вече да е назначена към машина преди препланиране.")

        machine_exists = connection.execute(
            "SELECT 1 FROM machines WHERE id = ?",
            (machine_id,),
        ).fetchone()
        if not machine_exists:
            messages.append("Изберете валидна машина.")

        if machine_sequence < 1:
            messages.append("Редът трябва да е 1 или по-голям.")

        if (
            card["status"] in (STATUS_RUNNING, STATUS_PAUSED)
            and card["machine_id"] is not None
            and int(card["machine_id"]) != machine_id
        ):
            occupied_card = fetch_occupied_machine_card(connection, card_id, machine_id)
            if occupied_card:
                messages.append(
                    f"Машина {machine_id} е заета от поръчка "
                    f"{occupied_card['order_number']}."
                )

        if messages:
            return RuleResult(False, tuple(messages))

        try:
            assert card["machine_id"] is not None
            old_machine_id = int(card["machine_id"])
            temporary_sequence = -int(card["id"])
            connection.execute(
                """
                UPDATE cards
                SET machine_id = ?,
                    machine_sequence = ?
                WHERE id = ?
                """,
                (machine_id, temporary_sequence, card_id),
            )
            if old_machine_id != machine_id:
                normalize_machine_queue(connection, machine_id=old_machine_id)
            final_sequence = normalize_machine_queue(
                connection,
                machine_id=machine_id,
                moving_card_id=card_id,
                target_position=machine_sequence,
            )
        except sqlite3.IntegrityError:
            connection.rollback()
            return RuleResult(
                False,
                ("Планирането не бе записано, защото тази машина и ред вече са заети.",),
            )

    return RuleResult(
        True,
        (f"Поръчка {card['order_number']} е преместена към машина {machine_id}, ред {final_sequence}.",),
    )


def normalize_machine_queue(
    connection: sqlite3.Connection,
    machine_id: int,
    moving_card_id: int | None = None,
    target_position: int | None = None,
) -> int | None:
    rows = connection.execute(
        f"""
        SELECT id, machine_sequence
        FROM cards
        WHERE machine_id = ?
          AND status IN ({", ".join("?" for _ in ACTIVE_TERMINAL_STATUSES)})
        ORDER BY machine_sequence IS NULL, machine_sequence, id
        """,
        (machine_id, *ACTIVE_TERMINAL_STATUSES),
    ).fetchall()

    moving_row = None
    queue_rows = []
    for row in rows:
        if moving_card_id is not None and int(row["id"]) == moving_card_id:
            moving_row = row
        else:
            queue_rows.append(row)

    if moving_card_id is not None and moving_row is not None:
        assert target_position is not None
        insert_position = min(max(target_position, 1), len(queue_rows) + 1)
        queue_rows.insert(insert_position - 1, moving_row)
    else:
        insert_position = None

    rewrite_machine_queue_sequences(connection, machine_id, queue_rows)
    return insert_position


def rewrite_machine_queue_sequences(
    connection: sqlite3.Connection,
    machine_id: int,
    queue_rows: list[sqlite3.Row],
) -> None:
    for row in queue_rows:
        connection.execute(
            """
            UPDATE cards
            SET machine_sequence = ?
            WHERE id = ?
              AND machine_id = ?
            """,
            (-int(row["id"]), row["id"], machine_id),
        )

    for index, row in enumerate(queue_rows, start=1):
        original_sequence = row["machine_sequence"]
        sequence_changed = original_sequence is None or int(original_sequence) != index
        if sequence_changed:
            connection.execute(
                """
                UPDATE cards
                SET machine_sequence = ?,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND machine_id = ?
                """,
                (index, row["id"], machine_id),
            )
        else:
            connection.execute(
                """
                UPDATE cards
                SET machine_sequence = ?
                WHERE id = ?
                  AND machine_id = ?
                """,
                (index, row["id"], machine_id),
            )


def fetch_machine_queues() -> list[dict[str, Any]]:
    machines = fetch_machines()
    active_cards = fetch_cards_by_status(ACTIVE_TERMINAL_STATUSES)
    by_machine: dict[int, list[dict[str, Any]]] = {machine["id"]: [] for machine in machines}

    for card in active_cards:
        machine_id = card["machine_id"]
        if machine_id in by_machine:
            by_machine[machine_id].append(card)

    return [
        {
            "machine": machine,
            "cards": by_machine[machine["id"]],
            "focus_card": select_machine_focus_card(by_machine[machine["id"]]),
        }
        for machine in machines
    ]


def select_machine_focus_card(cards: list[dict[str, Any]]) -> dict[str, Any] | None:
    for status in (STATUS_RUNNING, STATUS_PAUSED, STATUS_PENDING):
        for card in cards:
            if card["status"] == status:
                return card
    return None


def fetch_recent_import_batches(limit: int = 8) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, source_filename, rows_seen, rows_imported, created_at
            FROM import_batches
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return rows_to_dicts(rows)


def insert_import_batch_row(
    connection: sqlite3.Connection,
    import_batch_id: int,
    display_order: int,
    row_number: int | None,
    order_number: str,
    action: str,
    message: str,
    is_duplicate_row: bool = False,
    row_error: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO import_batch_rows (
            import_batch_id,
            display_order,
            row_number,
            order_number,
            action,
            message,
            is_duplicate_row,
            row_error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_batch_id,
            display_order,
            row_number,
            order_number,
            action,
            message,
            1 if is_duplicate_row else 0,
            row_error,
        ),
    )


def fetch_import_batch_result(batch_id: int | None) -> dict[str, Any] | None:
    if batch_id is None:
        return None

    with connect() as connection:
        batch = connection.execute(
            """
            SELECT id, source_filename, rows_seen, rows_imported
            FROM import_batches
            WHERE id = ?
            """,
            (batch_id,),
        ).fetchone()
        if batch is None:
            return None

        rows = rows_to_dicts(
            connection.execute(
                """
                SELECT
                    row_number,
                    order_number,
                    action,
                    message,
                    is_duplicate_row,
                    row_error
                FROM import_batch_rows
                WHERE import_batch_id = ?
                ORDER BY display_order, id
                """,
                (batch_id,),
            ).fetchall()
        )

    created = sum(1 for row in rows if row["action"] == "created")
    updated = sum(1 for row in rows if row["action"] == "updated")
    skipped = sum(1 for row in rows if row["action"] in ("skipped", "blocked"))
    duplicate_rows = [
        str(row["order_number"] or "")
        for row in rows
        if row["is_duplicate_row"] and str(row["order_number"] or "")
    ]
    row_errors = [str(row["row_error"]) for row in rows if row["row_error"]]
    row_results = [
        {
            "row_number": row["row_number"],
            "order_number": row["order_number"],
            "action": row["action"],
            "message": row["message"],
        }
        for row in rows
    ]

    return {
        "batch_id": int(batch["id"]),
        "filename": str(batch["source_filename"] or ""),
        "rows_seen": int(batch["rows_seen"] or 0),
        "rows_imported": int(batch["rows_imported"] or 0),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "duplicate_rows": duplicate_rows,
        "row_errors": row_errors,
        "row_results": row_results,
    }


def database_summary() -> dict[str, Any]:
    with connect() as connection:
        card_counts = rows_to_dicts(
            connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM cards
                GROUP BY status
                ORDER BY status
                """
            ).fetchall()
        )
        machine_count = connection.execute("SELECT COUNT(*) FROM machines").fetchone()[0]
        return {
            "database_path": str(DB_PATH),
            "machine_count": machine_count,
            "card_counts": card_counts,
        }
