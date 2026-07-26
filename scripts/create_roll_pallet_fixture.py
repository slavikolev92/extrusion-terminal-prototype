from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app import db
from app.constants import STATUS_COMPLETED, STATUS_RUNNING
from app.printing import (
    MAX_PRINT_ROLLS,
    PALLET_BACK_COLUMN_CAPACITY,
    PALLET_OVERFLOW_PAGE_CAPACITY,
)


FIXTURE_RECIPE_SOURCE_FIELDS = {
    "raw_material_a": "LDPE; Alpha 2420H | 55%",
    "raw_material_b": "LDPE; Beta B20 | 20%",
    "raw_material_c": "MDPE; Gamma 3802 | 10%",
    "linear_pe": "LLDPE; Linear 118W | 10%",
    "antistatic": "Antistatic; AS-1 | 1%",
    "masterbatch": "Masterbatch; Blue MB | 3%",
    "chalk": "Filler; Chalk C | 1%",
}


def resolve_under_test_runtime(raw_path: str, *, label: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    resolved = candidate.resolve()
    runtime_root = (ROOT_DIR / ".test-runtime").resolve()
    try:
        resolved.relative_to(runtime_root)
    except ValueError as exc:
        raise ValueError(f"{label} must be under .test-runtime") from exc
    return resolved


def reset_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_path.unlink(missing_ok=True)
    db.DATA_DIR = database_path.parent
    db.DB_PATH = database_path
    db.init_db()


def insert_card(
    connection,
    *,
    order_number: str,
    status: str,
    machine_id: int | None,
    machine_sequence: int | None,
    current_pallet_number: int | None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO cards (
            order_number,
            status,
            machine_id,
            machine_sequence,
            order_date,
            delivery_date,
            customer,
            city,
            product_type,
            ordered_gross_kg,
            ordered_rolls,
            ordered_meters,
            ordered_units,
            product_form,
            material,
            size_thickness,
            notes,
            extrusion_sequence,
            extrusion_folding,
            extrusion_next_operation,
            extrusion_treatment,
            raw_material_a,
            raw_material_b,
            raw_material_c,
            linear_pe,
            antistatic,
            masterbatch,
            chalk,
            packaging_method,
            tare_weight,
            current_pallet_number,
            first_started_at,
            finished_at
        )
        VALUES (
            ?, ?, ?, ?,
            '26.07.2026', '30.07.2026',
            'Калибрация Палети ООД', 'София',
            'Полиетиленово фолио за UI проверка',
            '3600', '120', '24000', '48000',
            'Ръкав', 'LDPE / LLDPE', '650 / 0.050',
            'Временна карта само за браузърна проверка.',
            '1', 'C-фалда', 'Печат', 'Двустранно',
            ?, ?, ?, ?, ?, ?, ?,
            'Ролки върху транспортни палети',
            1.25, ?, '2026-07-26 06:05:00', ?
        )
        """,
        (
            order_number,
            status,
            machine_id,
            machine_sequence,
            *FIXTURE_RECIPE_SOURCE_FIELDS.values(),
            current_pallet_number,
            None if status == STATUS_RUNNING else "2026-07-26 14:35:00",
        ),
    )
    card_id = int(cursor.lastrowid)
    recipe_result = db.parse_and_replace_recipe_components_for_card(
        connection,
        card_id,
        FIXTURE_RECIPE_SOURCE_FIELDS,
    )
    if not recipe_result.ok:
        details = "; ".join(
            f"{error.component_key}: {error.message}"
            for error in recipe_result.errors
        )
        raise RuntimeError(f"Fixture recipe failed production parsing: {details}")
    connection.executemany(
        """
        INSERT INTO recipe_actual_entries (
            card_id, component_key, component_label,
            planned_material, actual_material_used, batch_lot
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (card_id, "raw_material_a", "Вид суровина A", "Alpha 2420H", "Alpha 2420H", "LOT-A-26"),
            (card_id, "raw_material_b", "Вид суровина B", "Beta B20", "Beta B20", "LOT-B-26"),
            (card_id, "raw_material_c", "Вид суровина C", "Gamma 3802", "Gamma 3802", "LOT-C-26"),
            (card_id, "linear_pe", "Линеен /mLLDPE/", "Linear 118W", "Linear 118W", "LOT-L-26"),
            (card_id, "antistatic", "Антистатик", "AS-1", "AS-1", "LOT-AS-26"),
            (card_id, "masterbatch", "Мастербач", "Blue MB", "Blue MB", "LOT-MB-26"),
            (card_id, "chalk", "Креда", "Chalk C", "Chalk C", "LOT-CH-26"),
        ),
    )
    return card_id


def add_rolls(
    connection,
    *,
    card_id: int,
    order_number: str,
    pallet_numbers: list[int | None],
    shift_occurrence_id: int | None,
) -> list[int]:
    roll_ids: list[int] = []
    tare = Decimal("1.25")
    for roll_number, pallet_number in enumerate(pallet_numbers, start=1):
        gross = Decimal("20.00") + Decimal(roll_number % 17) / Decimal("10")
        cursor = connection.execute(
            """
            INSERT INTO roll_entries (
                card_id, shift_occurrence_id, order_number, roll_number,
                gross_weight, tare_weight, net_weight, pallet_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                shift_occurrence_id,
                order_number,
                roll_number,
                str(gross),
                str(tare),
                str(gross - tare),
                pallet_number,
            ),
        )
        roll_ids.append(int(cursor.lastrowid))
    return roll_ids


def add_timing(connection, card_id: int, *, running: bool) -> None:
    connection.execute(
        """
        INSERT INTO production_time_segments (card_id, started_at, ended_at, end_reason)
        VALUES (?, '2026-07-26 06:05:00', ?, ?)
        """,
        (
            card_id,
            None if running else "2026-07-26 14:35:00",
            None if running else "finish",
        ),
    )


def create_fixture(database_path: Path) -> dict[str, object]:
    reset_database(database_path)
    with db.connect() as connection:
        shift_cursor = connection.execute(
            """
            INSERT INTO shift_occurrences (shift_number, started_at)
            VALUES (1, '2026-07-26 06:00:00')
            """
        )
        active_shift_id = int(shift_cursor.lastrowid)

        running_id = insert_card(
            connection,
            order_number="PALLET-UI-RUNNING",
            status=STATUS_RUNNING,
            machine_id=1,
            machine_sequence=1,
            current_pallet_number=7,
        )
        running_roll_ids = add_rolls(
            connection,
            card_id=running_id,
            order_number="PALLET-UI-RUNNING",
            pallet_numbers=[7, 6, None],
            shift_occurrence_id=active_shift_id,
        )
        add_timing(connection, running_id, running=True)

        fitting_summary_count = 2 * PALLET_BACK_COLUMN_CAPACITY
        completed_mixed_id = insert_card(
            connection,
            order_number="PALLET-UI-NORMAL",
            status=STATUS_COMPLETED,
            machine_id=2,
            machine_sequence=None,
            current_pallet_number=4,
        )
        add_rolls(
            connection,
            card_id=completed_mixed_id,
            order_number="PALLET-UI-NORMAL",
            pallet_numbers=[
                *range(1, fitting_summary_count),
                None,
            ],
            shift_occurrence_id=None,
        )
        add_timing(connection, completed_mixed_id, running=False)

        completed_all_blank_id = insert_card(
            connection,
            order_number="PALLET-UI-BLANK",
            status=STATUS_COMPLETED,
            machine_id=3,
            machine_sequence=None,
            current_pallet_number=None,
        )
        overflow_summary_count = max(
            2 * PALLET_BACK_COLUMN_CAPACITY + 1,
            2 * PALLET_OVERFLOW_PAGE_CAPACITY + 1,
        )
        if overflow_summary_count > MAX_PRINT_ROLLS:
            raise RuntimeError(
                "Measured pallet capacities cannot be exercised within the 120-roll print grid."
            )
        add_rolls(
            connection,
            card_id=completed_all_blank_id,
            order_number="PALLET-UI-BLANK",
            pallet_numbers=[None, None],
            shift_occurrence_id=None,
        )
        add_timing(connection, completed_all_blank_id, running=False)

        completed_overflow_id = insert_card(
            connection,
            order_number="PALLET-UI-OVERFLOW",
            status=STATUS_COMPLETED,
            machine_id=4,
            machine_sequence=None,
            current_pallet_number=120,
        )
        add_rolls(
            connection,
            card_id=completed_overflow_id,
            order_number="PALLET-UI-OVERFLOW",
            pallet_numbers=list(range(1, overflow_summary_count + 1)),
            shift_occurrence_id=None,
        )
        add_timing(connection, completed_overflow_id, running=False)
        connection.commit()

    return {
        "db_path": str(database_path),
        "active_shift_id": active_shift_id,
        "cards": {
            "running": running_id,
            "completed_mixed": completed_mixed_id,
            "completed_all_blank": completed_all_blank_id,
            "completed_overflow": completed_overflow_id,
        },
        "running_roll_ids": running_roll_ids,
        "clear_candidate_roll_id": running_roll_ids[1],
        "mixed_blank_roll_id": running_roll_ids[2],
        "expected_summary_rows": {
            "completed_mixed": fitting_summary_count,
            "completed_all_blank": 0,
            "completed_overflow": overflow_summary_count,
        },
        "measured_capacities": {
            "back_column": PALLET_BACK_COLUMN_CAPACITY,
            "overflow_page": PALLET_OVERFLOW_PAGE_CAPACITY,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the temporary roll/pallet browser and print fixture."
    )
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        database_path = resolve_under_test_runtime(args.db_path, label="fixture DB path")
        output_path = resolve_under_test_runtime(args.output, label="fixture output path")
    except ValueError as exc:
        parser.error(str(exc))

    payload = create_fixture(database_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
