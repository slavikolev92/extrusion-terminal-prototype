from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app import db
from app.constants import STATUS_COMPLETED


DEFAULT_DB_PATH = Path(".test-runtime/print-template-tuning/extrusion_terminal.sqlite3")
DEFAULT_OUTPUT_PATH = Path(".test-runtime/print-template-tuning/fixture.json")
SCENARIOS = (
    ("no_weight", 2, False, 2, "page2"),
    ("page2_boundary", 7, True, 2, "page2"),
    ("first_overflow", 8, True, 3, "overflow:1"),
    ("overflow_boundary", 46, True, 3, "overflow:1"),
    ("orphan_total", 47, True, 4, "overflow:2"),
)


def decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def require_single_link(path: Path, *, label: str) -> None:
    if path.exists() and path.stat().st_nlink != 1:
        raise ValueError(f"{label} must not have multiple hard links")


def resolve_under_test_runtime(raw_path: str, *, label: str) -> Path:
    runtime_path = ROOT_DIR / ".test-runtime"
    if runtime_path.is_symlink():
        raise ValueError(".test-runtime guard root must not be a symlink")
    if runtime_path.exists() and not runtime_path.is_dir():
        raise ValueError(".test-runtime guard root must be a directory")

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    lexical_candidate = candidate.absolute()
    lexical_runtime = runtime_path.absolute()
    try:
        lexical_relative = lexical_candidate.relative_to(lexical_runtime)
    except ValueError as exc:
        raise ValueError(f"{label} must be under .test-runtime") from exc
    if not lexical_relative.parts:
        raise ValueError(f"{label} must be under .test-runtime")

    current = lexical_runtime
    for component in lexical_relative.parts:
        current = current / component
        if (current.exists() or current.is_symlink()) and current.is_symlink():
            raise ValueError(f"{label} must not be a symlink")

    resolved = candidate.resolve()
    test_runtime_dir = runtime_path.resolve()
    try:
        relative = resolved.relative_to(test_runtime_dir)
    except ValueError as exc:
        raise ValueError(f"{label} must be under .test-runtime") from exc
    if not relative.parts:
        raise ValueError(f"{label} must be under .test-runtime")
    if resolved.exists() and not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    require_single_link(resolved, label=label)
    return resolved


def resolve_fixture_db_path(raw_path: str) -> Path:
    """Backward-compatible database-path guard for existing UI checks."""
    return resolve_under_test_runtime(raw_path, label="fixture DB path")


def reset_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    require_single_link(database_path, label="fixture DB path")
    database_path.unlink(missing_ok=True)
    db.DATA_DIR = database_path.parent
    db.DB_PATH = database_path
    db.init_db()


def atomic_write_text(path: Path, contents: str, *, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(contents)
            temporary.flush()
            os.fsync(temporary.fileno())
        require_single_link(path, label=label)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def create_completed_scenario_card(
    order_number: str,
    *,
    pallet_count: int,
    include_physical_weights: bool,
) -> int:
    with db.connect() as connection:
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
                printing_sequence,
                extrusion_sequence,
                rewinding_slitting_sequence,
                confection_sequence,
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
                ?,
                ?,
                '15000',
                '40000',
                'Ръкав',
                'LDPE / LLDPE',
                '620 / 0.050',
                'Проверка на ширина, дебелина и равномерност. Текстът е нарочно по-дълъг за контрол на пренасянето.',
                '2',
                '1',
                '3',
                '4',
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
                '2026-06-18 21:35:00',
                '2026-06-19 04:15:00'
            )
            """,
            (
                order_number,
                STATUS_COMPLETED,
                decimal_text(
                    sum(
                        (
                            Decimal("20.00")
                            + Decimal(roll_number) / Decimal("100")
                            for roll_number in range(1, pallet_count + 1)
                        ),
                        Decimal("0"),
                    )
                ),
                str(pallet_count),
            ),
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
                (card_id, "2026-06-18 21:35:00", "2026-06-18 23:40:00", "pause"),
                (card_id, "2026-06-19 00:00:00", "2026-06-19 01:50:00", "pause"),
                (card_id, "2026-06-19 02:20:00", "2026-06-19 04:15:00", "finish"),
            ),
        )

        tare = Decimal("1.25")
        roll_rows = []
        for roll_number in range(1, pallet_count + 1):
            gross = Decimal("20.00") + Decimal(roll_number) / Decimal("100")
            net = gross - tare
            roll_rows.append(
                (
                    card_id,
                    order_number,
                    roll_number,
                    decimal_text(gross),
                    decimal_text(tare),
                    decimal_text(net),
                    roll_number,
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
                net_weight,
                pallet_number
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            roll_rows,
        )
        if include_physical_weights:
            connection.executemany(
                """
                INSERT INTO card_pallet_weights (
                    card_id, pallet_number, weight_hundredths
                )
                VALUES (?, ?, ?)
                """,
                (
                    (card_id, pallet_number, (100 + pallet_number) * 10)
                    for pallet_number in range(1, pallet_count + 1)
                ),
            )
        connection.commit()

    return card_id


def create_dense_completed_card(order_number: str = "PRINT-TEMPLATE-001") -> int:
    """Create the legacy dense card used by the time-handling UI verifier."""
    with db.connect() as connection:
        existing = connection.execute(
            "SELECT id FROM cards WHERE order_number = ?",
            (order_number,),
        ).fetchone()
        if existing:
            return int(existing["id"])

    card_id = create_completed_scenario_card(
        order_number,
        pallet_count=83,
        include_physical_weights=False,
    )
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO shift_occurrences (shift_number, started_at, ended_at)
            VALUES (1, '2026-06-19 04:00:00', NULL)
            """
        )
        connection.commit()
    return card_id


def create_fixture(database_path: Path, order_prefix: str) -> dict[str, object]:
    reset_database(database_path)
    scenarios: dict[str, dict[str, object]] = {}
    for (
        scenario_name,
        pallet_count,
        include_physical_weights,
        expected_page_count,
        expected_total_placement,
    ) in SCENARIOS:
        order_number = f"{order_prefix}-{scenario_name.upper().replace('_', '-')}"
        card_id = create_completed_scenario_card(
            order_number,
            pallet_count=pallet_count,
            include_physical_weights=include_physical_weights,
        )
        scenarios[scenario_name] = {
            "scenario": scenario_name,
            "card_id": card_id,
            "order_number": order_number,
            "print_path": f"/cards/{card_id}/print",
            "expected_page_count": expected_page_count,
            "expected_total_placement": expected_total_placement,
            "expected_pallet_row_count": pallet_count,
        }
    return {
        "db_path": str(database_path),
        "scenario_order": [scenario[0] for scenario in SCENARIOS],
        "scenarios": scenarios,
    }


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
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Temporary JSON manifest path to create.",
    )
    parser.add_argument(
        "--order-prefix",
        default="PRINT-TEMPLATE",
        help="Fixture order-number prefix.",
    )
    args = parser.parse_args()

    try:
        database_path = resolve_under_test_runtime(args.db_path, label="fixture DB path")
        output_path = resolve_under_test_runtime(args.output, label="fixture output path")
        if database_path == output_path:
            raise ValueError("fixture DB path and fixture output path must differ")
        if database_path.suffix not in {".sqlite3", ".sqlite", ".db"}:
            raise ValueError("fixture DB path must name a SQLite file")
        if output_path.suffix != ".json":
            raise ValueError("fixture output path must name a JSON file")
    except ValueError as exc:
        parser.error(str(exc))
    payload = create_fixture(database_path, args.order_prefix)
    serialized = f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
    atomic_write_text(
        output_path,
        serialized,
        label="fixture output path",
    )
    print(serialized, end="")


if __name__ == "__main__":
    main()
