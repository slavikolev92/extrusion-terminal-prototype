from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from .constants import (
    ACTIVE_TERMINAL_STATUSES,
    ARCHIVE_STATUSES,
    CARD_STATUSES,
    STATUS_DRAFT,
    STATUS_IMPORTED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_RUNNING,
    VALIDATION_READY,
    VALIDATION_STATUSES,
)
from .rules import RuleResult

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
    validation_status TEXT NOT NULL DEFAULT 'ready' CHECK (validation_status IN ({_sql_list(VALIDATION_STATUSES)})),
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
            SELECT id, order_number, status, validation_status, machine_id,
                   machine_sequence, customer, product_type, quantity_1,
                   unit_1, tare_weight, updated_at
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
            SELECT id, order_number, status, validation_status, machine_id,
                   machine_sequence, customer, product_type
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        return dict(row) if row else None


def fetch_terminal_card_detail(card_id: int) -> dict[str, Any] | None:
    terminal_statuses = (*ACTIVE_TERMINAL_STATUSES, *ARCHIVE_STATUSES)
    placeholders = ", ".join("?" for _ in terminal_statuses)
    with connect() as connection:
        row = connection.execute(
            f"""
            SELECT id, order_number, status, validation_status, machine_id,
                   machine_sequence, order_date, delivery_date, customer, city,
                   product_type, quantity_1, unit_1, quantity_2, unit_2,
                   product_form, material, size_thickness, notes,
                   extrusion_folding, extrusion_next_operation,
                   extrusion_treatment, raw_material_a, raw_material_b,
                   raw_material_c, linear_pe, antistatic, masterbatch, chalk,
                   packaging_method, actual_raw_material_used,
                   raw_material_brand_grade, raw_material_batch_lot,
                   tare_weight, version, updated_at
            FROM cards
            WHERE id = ?
              AND status IN ({placeholders})
            """,
            (card_id, *terminal_statuses),
        ).fetchone()
        return dict(row) if row else None


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
                ("Card changed after this page was loaded. Reload the card and try again.",),
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


def release_card(card_id: int, machine_id: int, machine_sequence: int) -> RuleResult:
    messages: list[str] = []

    with connect() as connection:
        card = connection.execute(
            """
            SELECT id, order_number, status, validation_status
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()

        if not card:
            return RuleResult(False, ("Card was not found.",))

        if card["status"] not in (STATUS_DRAFT, STATUS_IMPORTED):
            messages.append("Only draft/imported cards can be released.")

        if card["validation_status"] != VALIDATION_READY:
            messages.append("Only ready cards can be released.")

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
