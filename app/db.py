from __future__ import annotations

import os
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .constants import (
    ACTIVE_TERMINAL_STATUSES,
    ARCHIVE_STATUSES,
    CARD_STATUSES,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_IMPORTED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_RUNNING,
)
from .rules import RuleResult

STALE_CARD_MESSAGE = "Card changed after this page was loaded. Reload the card and try again."

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("EXTRUSION_DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.getenv("EXTRUSION_DB_PATH", DATA_DIR / "extrusion_terminal.sqlite3"))


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


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

CREATE TABLE IF NOT EXISTS cards (
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

CREATE TABLE IF NOT EXISTS roll_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    order_number TEXT NOT NULL,
    roll_number INTEGER NOT NULL CHECK (roll_number >= 1),
    gross_weight NUMERIC CHECK (gross_weight IS NULL OR gross_weight >= 0),
    net_weight NUMERIC CHECK (net_weight IS NULL OR net_weight >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (card_id, roll_number)
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

CREATE INDEX IF NOT EXISTS idx_roll_entries_card_roll
ON roll_entries(card_id, roll_number);

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


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with connect() as connection:
        connection.executescript(SCHEMA_SQL)
        # Existing pilot databases may still have legacy cards.validation_status;
        # current code ignores it and validates current card fields directly.
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
            SELECT id, order_number, status, machine_id, machine_sequence,
                   customer, product_type, quantity_1, unit_1, tare_weight,
                   version, updated_at
            FROM cards
            WHERE status IN ({placeholders})
            ORDER BY machine_id IS NULL, machine_id, machine_sequence IS NULL,
                     machine_sequence, order_number
            """,
            statuses,
        ).fetchall()
        return rows_to_dicts(rows)


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
                   size_thickness, notes, extrusion_flag, extrusion_folding,
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
        roll_data = fetch_roll_entries_and_totals(connection, card_id, card["tare_weight"])
        card.update(roll_data)
        return card


def fetch_terminal_card_detail(card_id: int) -> dict[str, Any] | None:
    terminal_statuses = (*ACTIVE_TERMINAL_STATUSES, *ARCHIVE_STATUSES)
    placeholders = ", ".join("?" for _ in terminal_statuses)
    with connect() as connection:
        row = connection.execute(
            f"""
            SELECT id, order_number, status, machine_id, machine_sequence,
                   order_date, delivery_date, customer, city,
                   product_type, quantity_1, unit_1, quantity_2, unit_2,
                   product_form, material, size_thickness, notes,
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
            (card_id, *terminal_statuses),
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
        roll_data = fetch_roll_entries_and_totals(connection, card_id, card["tare_weight"])
        card.update(roll_data)
        return card


def fetch_roll_entries_and_totals(
    connection: sqlite3.Connection,
    card_id: int,
    tare_weight: Any,
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT id, roll_number, gross_weight, net_weight, updated_at
        FROM roll_entries
        WHERE card_id = ?
        ORDER BY roll_number
        """,
        (card_id,),
    ).fetchall()
    roll_entries = rows_to_dicts(rows)
    tare = decimal_from_database(tare_weight)
    gross_values = [
        decimal_from_database(entry["gross_weight"])
        for entry in roll_entries
        if entry["gross_weight"] is not None
    ]
    gross_values = [gross for gross in gross_values if gross is not None]
    roll_count = len(gross_values)
    total_gross = sum(gross_values, Decimal("0"))
    total_net = None if tare is None else total_gross - (tare * roll_count)
    next_roll_number = (
        max((int(entry["roll_number"]) for entry in roll_entries), default=0) + 1
    )

    return {
        "roll_entries": roll_entries,
        "roll_count": roll_count,
        "next_roll_number": next_roll_number,
        "total_gross_weight": decimal_to_display(total_gross),
        "total_net_weight": decimal_to_display(total_net) if total_net is not None else None,
    }


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
            expected_status_message="Only pending cards can be started.",
        )
        if not result.ok:
            return result

        occupied_card = fetch_occupied_machine_card(connection, card_id, int(card["machine_id"]))
        if occupied_card:
            return RuleResult(
                False,
                (
                    f"Machine {card['machine_id']} is occupied by order "
                    f"{occupied_card['order_number']}.",
                ),
            )

        if has_open_timing_segment(connection, card_id):
            return RuleResult(False, ("Card already has an active timing segment.",))

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
                (f"Machine {card['machine_id']} already has a running card.",),
            )

    return RuleResult(True, (f"Production timing started for order {card['order_number']}.",))


def pause_production_timing(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = fetch_timing_action_card(connection, card_id)
        result = validate_timing_action_card(
            card=card,
            loaded_version=loaded_version,
            expected_status=STATUS_RUNNING,
            expected_status_message="Only running cards can be paused.",
        )
        if not result.ok:
            return result

        open_segment = fetch_open_timing_segment(connection, card_id)
        if not open_segment:
            return RuleResult(False, ("Card has no active timing segment to pause.",))

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

    return RuleResult(True, (f"Production timing paused for order {card['order_number']}.",))


def resume_production_timing(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = fetch_timing_action_card(connection, card_id)
        result = validate_timing_action_card(
            card=card,
            loaded_version=loaded_version,
            expected_status=STATUS_PAUSED,
            expected_status_message="Only paused cards can be resumed.",
        )
        if not result.ok:
            return result

        occupied_card = fetch_occupied_machine_card(connection, card_id, int(card["machine_id"]))
        if occupied_card:
            return RuleResult(
                False,
                (
                    f"Machine {card['machine_id']} is occupied by order "
                    f"{occupied_card['order_number']}.",
                ),
            )

        if has_open_timing_segment(connection, card_id):
            return RuleResult(False, ("Card already has an active timing segment.",))

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
                (f"Machine {card['machine_id']} already has a running card.",),
            )

    return RuleResult(True, (f"Production timing resumed for order {card['order_number']}.",))


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
                    ("Paused cards should not have an active timing segment. Reload the card.",),
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

    return RuleResult(True, (f"Order {card['order_number']} finished.",))


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

    return RuleResult(True, (f"Order {card['order_number']} cancelled.",))


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

        if card["machine_id"] is not None and card["machine_sequence"] is not None:
            duplicate = connection.execute(
                f"""
                SELECT order_number
                FROM cards
                WHERE id <> ?
                  AND machine_id = ?
                  AND machine_sequence = ?
                  AND status IN ({", ".join("?" for _ in ACTIVE_TERMINAL_STATUSES)})
                LIMIT 1
                """,
                (
                    card_id,
                    card["machine_id"],
                    card["machine_sequence"],
                    *ACTIVE_TERMINAL_STATUSES,
                ),
            ).fetchone()
            if duplicate:
                return RuleResult(
                    False,
                    (
                        f"Machine {card['machine_id']} already has active sequence "
                        f"{card['machine_sequence']} on order {duplicate['order_number']}.",
                    ),
                )

        try:
            connection.execute(
                """
                UPDATE cards
                SET status = ?,
                    cancelled_at = NULL,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (STATUS_PENDING, card_id),
            )
        except sqlite3.IntegrityError:
            connection.rollback()
            return RuleResult(
                False,
                ("Restore failed because the machine/sequence is already active.",),
            )

    return RuleResult(True, (f"Order {card['order_number']} restored to pending.",))


def fetch_active_terminal_action_card(
    connection: sqlite3.Connection,
    card_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        f"""
        SELECT id, order_number, status, tare_weight, version
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
        return RuleResult(False, ("Card was not found in the active terminal queue.",))

    if card["tare_weight"] is None:
        return RuleResult(False, ("Tare weight is required before finishing.",))

    segment_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM production_time_segments
        WHERE card_id = ?
        """,
        (card_id,),
    ).fetchone()[0]
    if int(segment_count or 0) == 0:
        return RuleResult(False, ("Production timing must be started before finishing.",))

    roll_rows = connection.execute(
        """
        SELECT roll_number, gross_weight
        FROM roll_entries
        WHERE card_id = ?
        ORDER BY roll_number
        """,
        (card_id,),
    ).fetchall()
    gross_rolls = [roll for roll in roll_rows if roll["gross_weight"] is not None]
    if not gross_rolls:
        return RuleResult(False, ("At least one gross roll weight is required before finishing.",))

    found_empty_roll = False
    for roll in roll_rows:
        if roll["gross_weight"] is None:
            found_empty_roll = True
        elif found_empty_roll:
            return RuleResult(
                False,
                ("Empty roll gaps must be corrected before finishing.",),
            )

    return RuleResult(True)


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
        return RuleResult(False, ("Card was not found in the active terminal queue.",))

    if int(card["version"]) != loaded_version:
        return RuleResult(
            False,
            (STALE_CARD_MESSAGE,),
        )

    if not card["machine_id"]:
        return RuleResult(False, ("Card must be assigned to a machine before timing starts.",))

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
          AND status IN (?, ?)
        ORDER BY machine_sequence IS NULL, machine_sequence, id
        LIMIT 1
        """,
        (card_id, machine_id, STATUS_RUNNING, STATUS_PAUSED),
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
        return None, f"{field_name} is required."

    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        return None, f"{field_name} must be a number."

    if not parsed.is_finite():
        return None, f"{field_name} must be a number."

    if parsed < 0:
        return None, f"{field_name} must be 0 or higher."

    if parsed.as_tuple().exponent < -2:
        return None, f"{field_name} supports at most two decimal places."

    return parsed, None


def validate_loaded_card_version(card: sqlite3.Row | None, loaded_version: int) -> RuleResult:
    if not card:
        return RuleResult(False, ("Card was not found.",))

    if int(card["version"]) != loaded_version:
        return RuleResult(False, (STALE_CARD_MESSAGE,))

    return RuleResult(True)


def net_weight_for_gross(gross_weight: Decimal, tare_weight: Decimal | None) -> Decimal | None:
    if tare_weight is None:
        return None

    net_weight = gross_weight - tare_weight
    if net_weight < 0:
        return None
    return net_weight


def update_tare_weight(card_id: int, loaded_version: int, tare_weight: str) -> RuleResult:
    parsed_tare, parse_error = parse_weight(
        tare_weight,
        "Tare weight",
        allow_blank=True,
    )
    if parse_error:
        return RuleResult(False, (parse_error,))

    with connect() as connection:
        card = connection.execute(
            """
            SELECT id, order_number, version
            FROM cards
            WHERE id = ?
              AND status IN (?, ?, ?, ?, ?)
            """,
            (card_id, *ACTIVE_TERMINAL_STATUSES, *ARCHIVE_STATUSES),
        ).fetchone()

        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        rolls = connection.execute(
            """
            SELECT id, gross_weight
            FROM roll_entries
            WHERE card_id = ?
              AND gross_weight IS NOT NULL
            ORDER BY roll_number
            """,
            (card_id,),
        ).fetchall()
        recalculated_rolls: list[tuple[str | None, int]] = []
        for roll in rolls:
            gross = decimal_from_database(roll["gross_weight"])
            if gross is None:
                continue
            net = net_weight_for_gross(gross, parsed_tare)
            if parsed_tare is not None and net is None:
                return RuleResult(
                    False,
                    ("Tare weight cannot be greater than an existing gross roll weight.",),
                )
            recalculated_rolls.append(
                (decimal_to_storage(net) if net is not None else None, int(roll["id"]))
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
        connection.executemany(
            """
            UPDATE roll_entries
            SET net_weight = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            recalculated_rolls,
        )

    message = "Tare weight cleared." if parsed_tare is None else "Tare weight saved."
    return RuleResult(True, (message,))


def add_roll_gross_weight(card_id: int, loaded_version: int, gross_weight: str) -> RuleResult:
    parsed_gross, parse_error = parse_weight(
        gross_weight,
        "Gross weight",
        allow_blank=False,
    )
    if parse_error:
        return RuleResult(False, (parse_error,))
    assert parsed_gross is not None

    with connect() as connection:
        card = fetch_roll_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        roll_entry_result = validate_card_allows_roll_entry(card)
        if not roll_entry_result.ok:
            return roll_entry_result

        tare = decimal_from_database(card["tare_weight"])
        net = net_weight_for_gross(parsed_gross, tare)
        if tare is not None and net is None:
            return RuleResult(
                False,
                ("Gross weight cannot be lower than the tare weight.",),
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
                net_weight
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                card_id,
                card["order_number"],
                next_roll_number,
                decimal_to_storage(parsed_gross),
                decimal_to_storage(net) if net is not None else None,
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

    return RuleResult(True, (f"Roll {next_roll_number} saved.",))


def update_roll_gross_weight(
    card_id: int,
    roll_id: int,
    loaded_version: int,
    gross_weight: str,
) -> RuleResult:
    parsed_gross, parse_error = parse_weight(
        gross_weight,
        "Gross weight",
        allow_blank=True,
    )
    if parse_error:
        return RuleResult(False, (parse_error,))

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
            return RuleResult(False, ("Roll entry was not found.",))

        if (
            card["status"] == STATUS_COMPLETED
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
                    ("Completed cards must keep at least one gross roll weight.",),
                )

        tare = decimal_from_database(card["tare_weight"])
        net = net_weight_for_gross(parsed_gross, tare) if parsed_gross is not None else None
        if tare is not None and parsed_gross is not None and net is None:
            return RuleResult(
                False,
                ("Gross weight cannot be lower than the tare weight.",),
            )

        connection.execute(
            """
            UPDATE roll_entries
            SET gross_weight = ?,
                net_weight = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                decimal_to_storage(parsed_gross) if parsed_gross is not None else None,
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

    return RuleResult(True, (f"Roll {roll['roll_number']} saved.",))


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
            return RuleResult(False, ("Roll entry was not found.",))

        if card["status"] == STATUS_COMPLETED and roll["gross_weight"] is not None:
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
                    ("Completed cards must keep at least one gross roll weight.",),
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

    return RuleResult(True, (f"Roll {deleted_roll_number} deleted. Remaining rolls renumbered.",))


def fetch_roll_action_card(
    connection: sqlite3.Connection,
    card_id: int,
) -> sqlite3.Row | None:
    roll_edit_statuses = (*ACTIVE_TERMINAL_STATUSES, STATUS_COMPLETED)
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
        return RuleResult(False, ("Card was not found for roll entry.",))

    if card["status"] not in (STATUS_RUNNING, STATUS_COMPLETED):
        return RuleResult(
            False,
            ("Roll weights can only be changed while the card is running or completed.",),
        )

    return RuleResult(True)


def update_admin_imported_fields(
    card_id: int,
    loaded_version: int,
    fields: dict[str, str],
) -> RuleResult:
    from .importer import IMPORT_FIELDS, card_has_usable_extrusion_step

    cleaned_fields = {field: str(fields.get(field, "")).strip() for field in IMPORT_FIELDS}
    if not cleaned_fields["order_number"]:
        return RuleResult(False, ("Order number is required.",))

    if not card_has_usable_extrusion_step(cleaned_fields):
        return RuleResult(
            False,
            ("Imported fields must keep a usable extrusion step before saving.",),
        )

    with connect() as connection:
        card = connection.execute(
            """
            SELECT id, order_number, version
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
            return RuleResult(False, ("Order number already exists on another card.",))

        assignments = [
            *(f"{field} = ?" for field in IMPORT_FIELDS),
            "version = version + 1",
            "updated_at = CURRENT_TIMESTAMP",
        ]
        values: list[Any] = [
            *(cleaned_fields[field] for field in IMPORT_FIELDS),
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
        except sqlite3.IntegrityError:
            connection.rollback()
            return RuleResult(False, ("Order number already exists on another card.",))

    return RuleResult(True, ("Imported card fields saved.",))


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
            return RuleResult(False, ("Only unreleased imported cards can be deleted.",))

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
            return RuleResult(False, ("Cards with production data cannot be deleted.",))

        connection.execute("DELETE FROM cards WHERE id = ?", (card_id,))

    return RuleResult(True, (f"Order {card['order_number']} deleted.",))


def update_terminal_material_fields(
    card_id: int,
    loaded_version: int,
    actual_raw_material_used: str,
    raw_material_brand_grade: str,
    raw_material_batch_lot: str,
) -> RuleResult:
    with connect() as connection:
        card = connection.execute(
            """
            SELECT id, version
            FROM cards
            WHERE id = ?
              AND status IN (?, ?, ?, ?, ?)
            """,
            (card_id, *ACTIVE_TERMINAL_STATUSES, *ARCHIVE_STATUSES),
        ).fetchone()

        if not card:
            return RuleResult(False, ("Card was not found.",))

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

    return RuleResult(True, ("Material fields saved.",))


def release_card(
    card_id: int,
    machine_id: int,
    machine_sequence: int,
    loaded_version: int | None = None,
) -> RuleResult:
    from .importer import IMPORT_FIELDS, card_has_usable_extrusion_step

    messages: list[str] = []
    import_columns = ", ".join(IMPORT_FIELDS)

    with connect() as connection:
        card = connection.execute(
            f"""
            SELECT id, order_number, status, version, {import_columns}
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()

        if not card:
            return RuleResult(False, ("Card was not found.",))

        if loaded_version is not None:
            version_result = validate_loaded_card_version(card, loaded_version)
            if not version_result.ok:
                return version_result

        if card["status"] != STATUS_IMPORTED:
            messages.append("Only imported cards can be released.")

        card_fields = {field: str(card[field] or "") for field in IMPORT_FIELDS}
        if not card_has_usable_extrusion_step(card_fields):
            messages.append("Card must have a usable extrusion step before release.")

        machine_exists = connection.execute(
            "SELECT 1 FROM machines WHERE id = ?",
            (machine_id,),
        ).fetchone()
        if not machine_exists:
            messages.append("Select a valid machine.")

        if machine_sequence < 1:
            messages.append("Sequence must be 1 or higher.")

        duplicate = connection.execute(
            f"""
            SELECT order_number
            FROM cards
            WHERE id <> ?
              AND machine_id = ?
              AND machine_sequence = ?
              AND status IN ({", ".join("?" for _ in ACTIVE_TERMINAL_STATUSES)})
            LIMIT 1
            """,
            (card_id, machine_id, machine_sequence, *ACTIVE_TERMINAL_STATUSES),
        ).fetchone()
        if duplicate:
            messages.append(
                f"Machine {machine_id} already has active sequence {machine_sequence} "
                f"on order {duplicate['order_number']}."
            )

        if messages:
            return RuleResult(False, tuple(messages))

        try:
            connection.execute(
                """
                UPDATE cards
                SET status = ?,
                    machine_id = ?,
                    machine_sequence = ?,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (STATUS_PENDING, machine_id, machine_sequence, card_id),
            )
        except sqlite3.IntegrityError:
            return RuleResult(
                False,
                ("Release failed because the machine/sequence is already active.",),
            )

    return RuleResult(True, (f"Order {card['order_number']} released to machine {machine_id}.",))


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
                ("Only active terminal cards can be reassigned or resequenced.",),
            )

        messages: list[str] = []
        machine_exists = connection.execute(
            "SELECT 1 FROM machines WHERE id = ?",
            (machine_id,),
        ).fetchone()
        if not machine_exists:
            messages.append("Select a valid machine.")

        if machine_sequence < 1:
            messages.append("Sequence must be 1 or higher.")

        duplicate = fetch_duplicate_active_sequence_card(
            connection,
            card_id=card_id,
            machine_id=machine_id,
            machine_sequence=machine_sequence,
        )
        if duplicate:
            messages.append(
                f"Machine {machine_id} already has active sequence {machine_sequence} "
                f"on order {duplicate['order_number']}."
            )

        if card["status"] in (STATUS_RUNNING, STATUS_PAUSED):
            occupied_card = fetch_occupied_machine_card(connection, card_id, machine_id)
            if occupied_card:
                messages.append(
                    f"Machine {machine_id} is occupied by order "
                    f"{occupied_card['order_number']}."
                )

        if messages:
            return RuleResult(False, tuple(messages))

        try:
            connection.execute(
                """
                UPDATE cards
                SET machine_id = ?,
                    machine_sequence = ?,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (machine_id, machine_sequence, card_id),
            )
        except sqlite3.IntegrityError:
            connection.rollback()
            return RuleResult(
                False,
                ("Planning update failed because the machine/sequence is already active.",),
            )

    return RuleResult(
        True,
        (f"Order {card['order_number']} moved to machine {machine_id}, sequence {machine_sequence}.",),
    )


def fetch_duplicate_active_sequence_card(
    connection: sqlite3.Connection,
    card_id: int,
    machine_id: int,
    machine_sequence: int,
) -> sqlite3.Row | None:
    return connection.execute(
        f"""
        SELECT order_number
        FROM cards
        WHERE id <> ?
          AND machine_id = ?
          AND machine_sequence = ?
          AND status IN ({", ".join("?" for _ in ACTIVE_TERMINAL_STATUSES)})
        LIMIT 1
        """,
        (card_id, machine_id, machine_sequence, *ACTIVE_TERMINAL_STATUSES),
    ).fetchone()


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
    for card in cards:
        if card["status"] in (STATUS_RUNNING, STATUS_PAUSED):
            return card
    return cards[0] if cards else None


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
