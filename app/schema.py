from __future__ import annotations

import sqlite3
from typing import Any

from .constants import ACTIVE_TERMINAL_STATUSES, CARD_STATUSES


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


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
    ordered_gross_kg TEXT,
    ordered_rolls TEXT,
    ordered_meters TEXT,
    ordered_units TEXT,
    product_form TEXT,
    material TEXT,
    max_roll_weight TEXT,
    size_thickness TEXT,
    notes TEXT,

    printing_sequence TEXT,
    extrusion_sequence TEXT,
    rewinding_slitting_sequence TEXT,
    confection_sequence TEXT,
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
    current_pallet_number INTEGER CHECK (
        current_pallet_number IS NULL OR (
            typeof(current_pallet_number) = 'integer'
            AND current_pallet_number BETWEEN 1 AND 999
        )
    ),
    rewinding_roll_count INTEGER CHECK (
        rewinding_roll_count IS NULL OR (
            typeof(rewinding_roll_count) = 'integer'
            AND rewinding_roll_count BETWEEN 1 AND 999
        )
    ),
    final_extrusion_shift_occurrence_id INTEGER
        REFERENCES shift_occurrences(id) ON DELETE RESTRICT,

    first_started_at TEXT,
    finished_at TEXT,
    cancelled_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


CARD_INDEX_SQL = (
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_one_running_per_machine
    ON cards(machine_id)
    WHERE status = 'running' AND machine_id IS NOT NULL;
    """,
    f"""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_active_machine_sequence
    ON cards(machine_id, machine_sequence)
    WHERE status IN ({_sql_list(ACTIVE_TERMINAL_STATUSES)})
      AND machine_id IS NOT NULL
      AND machine_sequence IS NOT NULL;
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cards_status_machine_sequence
    ON cards(status, machine_id, machine_sequence);
    """,
)


def extend_cards_rebuild_target(
    connection: sqlite3.Connection,
    source_table: str,
    target_table: str,
) -> tuple[str, ...]:
    source_column_info = connection.execute(
        f"PRAGMA table_info({_quote_identifier(source_table)})"
    ).fetchall()
    source_columns = {str(row[1]): row for row in source_column_info}
    target_columns = {
        str(row[1])
        for row in connection.execute(
            f"PRAGMA table_info({_quote_identifier(target_table)})"
        ).fetchall()
    }

    for column_name, column_info in source_columns.items():
        if column_name in target_columns:
            continue
        connection.execute(
            f"ALTER TABLE {_quote_identifier(target_table)} "
            f"ADD COLUMN {_quote_identifier(column_name)} "
            f"{_legacy_column_type_sql(column_info[2])}"
        )
        target_columns.add(column_name)

    return tuple(
        str(row[1])
        for row in connection.execute(
            f"PRAGMA table_info({_quote_identifier(target_table)})"
        ).fetchall()
        if str(row[1]) in source_columns
    )
