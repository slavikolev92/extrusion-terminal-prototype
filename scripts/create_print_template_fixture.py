from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app import db
from app.constants import STATUS_COMPLETED


DEFAULT_DB_PATH = Path(".test-runtime/print-template-tuning/extrusion_terminal.sqlite3")


def decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def resolve_fixture_db_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    resolved = candidate.resolve()
    test_runtime_dir = (ROOT_DIR / ".test-runtime").resolve()
    try:
        resolved.relative_to(test_runtime_dir)
    except ValueError as exc:
        raise ValueError("fixture DB path must be under .test-runtime") from exc
    return resolved


def reset_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_path.unlink(missing_ok=True)
    db.DATA_DIR = database_path.parent
    db.DB_PATH = database_path
    db.init_db()


def create_dense_completed_card(order_number: str = "PRINT-TEMPLATE-001") -> int:
    with db.connect() as connection:
        existing = connection.execute(
            "SELECT id FROM cards WHERE order_number = ?",
            (order_number,),
        ).fetchone()
        if existing:
            return int(existing["id"])

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
                quantity_1,
                unit_1,
                quantity_2,
                unit_2,
                product_form,
                material,
                size_thickness,
                notes,
                extrusion_flag,
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
                first_started_at,
                finished_at
            )
            VALUES (
                ?, ?, 1, 1,
                '18.06.2026',
                '25.06.2026',
                'Дълго име на клиент ООД',
                'Пловдив',
                'Полиетиленово фолио ръкав с печатна подготовка',
                '1250',
                'kg',
                '83',
                'ролки',
                'Ръкав',
                'LDPE / LLDPE',
                '620 / 0.050',
                'Проверка на ширина, дебелина и равномерност. Текстът е нарочно по-дълъг за контрол на пренасянето.',
                'да',
                'C-фалда',
                'Печат',
                'Двустранно',
                'LDPE 2420H Exxon',
                'LLDPE 118W Rompetrol',
                'mLLDPE C6 Metallocene',
                '12%',
                '1%',
                'Син мастербач 3%',
                '0%',
                'Палетизиране и стреч фолио',
                1.25,
                '2026-06-18 08:05:00',
                '2026-06-18 14:45:00'
            )
            """,
            (order_number, STATUS_COMPLETED),
        )
        card_id = int(cursor.lastrowid)

        recipe_rows = (
            ("raw_material_a", "Вид суровина A", "LDPE 2420H Exxon", "LDPE Exxon Mobil 2420H", "LOT-A-25279-BG"),
            ("raw_material_b", "Вид суровина B", "LLDPE 118W Rompetrol", "LLDPE Rompetrol 118W", "LOT-B-25279-BG"),
            ("raw_material_c", "Вид суровина C", "mLLDPE C6 Metallocene", "mLLDPE C6 Metallocene", "LOT-C-25279-BG"),
            ("linear_pe", "Линеен /mLLDPE/", "12% без добавки", "mLLDPE C6 добавка", "LOT-LIN-25279"),
            ("antistatic", "Антистатик", "1%", "Antistatic B80", "LOT-AS-25279"),
            ("masterbatch", "Мастербач", "Син мастербач 3%", "Masterbatch Blue 3000", "LOT-MB-25279"),
            ("chalk", "Креда", "0%", "Chalk concentrate full", "LOT-CH-25279"),
        )
        connection.executemany(
            """
            INSERT INTO recipe_actual_entries (
                card_id,
                component_key,
                component_label,
                planned_material,
                actual_material_used,
                batch_lot
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(card_id, *row) for row in recipe_rows],
        )

        connection.executemany(
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
                (card_id, "2026-06-18 08:05:00", "2026-06-18 10:10:00", "pause"),
                (card_id, "2026-06-18 10:30:00", "2026-06-18 12:20:00", "pause"),
                (card_id, "2026-06-18 12:50:00", "2026-06-18 14:45:00", "finish"),
            ),
        )

        tare = Decimal("1.25")
        roll_rows = []
        for roll_number in range(1, 84):
            gross = Decimal("28.40") + (Decimal(roll_number % 9) * Decimal("0.35"))
            net = gross - tare
            roll_rows.append(
                (
                    card_id,
                    order_number,
                    roll_number,
                    decimal_text(gross),
                    decimal_text(tare),
                    decimal_text(net),
                )
            )
        connection.executemany(
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
            roll_rows,
        )
        connection.commit()

    return card_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a dense completed print fixture in a temporary SQLite DB."
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help="Temporary SQLite DB path to create.",
    )
    parser.add_argument(
        "--order-number",
        default="PRINT-TEMPLATE-001",
        help="Fixture order number.",
    )
    args = parser.parse_args()

    try:
        database_path = resolve_fixture_db_path(args.db_path)
    except ValueError as exc:
        parser.error(str(exc))
    reset_database(database_path)
    card_id = create_dense_completed_card(args.order_number)
    print(
        json.dumps(
            {
                "db_path": str(database_path),
                "card_id": card_id,
                "order_number": args.order_number,
                "print_path": f"/cards/{card_id}/print",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
