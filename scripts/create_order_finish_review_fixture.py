from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app import db
from app.importer import IMPORT_FIELDS, import_cards_from_csv


SCENARIOS = (
    "active_normal",
    "active_marked_empty",
    "active_marked_mixed",
    "waiting_many_pallets",
    "waiting_marker_cleared",
    "waiting_zero_rolls",
)


def assert_safe_generated_file_target(path: Path, *, label: str) -> None:
    if not path.exists():
        return
    if not path.is_file():
        raise ValueError(f"{label} must be a regular file")
    if path.stat().st_nlink != 1:
        raise ValueError(f"{label} must not have multiple hard links")


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    assert_safe_generated_file_target(path, label="fixture output path")
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
            temporary.write(value)
            temporary.flush()
            os.fsync(temporary.fileno())
        assert_safe_generated_file_target(path, label="fixture output path")
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def resolve_under_test_runtime(raw_path: str, *, label: str) -> Path:
    runtime_path = ROOT_DIR / ".test-runtime"
    if runtime_path.is_symlink():
        raise ValueError(".test-runtime guard root must not be a symlink")
    if runtime_path.exists() and not runtime_path.is_dir():
        raise ValueError(".test-runtime guard root must be a directory")
    runtime_root = runtime_path.resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(runtime_root)
    except ValueError as exc:
        raise ValueError(f"{label} must be under .test-runtime") from exc
    if not relative.parts:
        raise ValueError(f"{label} must be under .test-runtime")
    if resolved.exists() and not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    assert_safe_generated_file_target(resolved, label=label)
    return resolved


def reset_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    assert_safe_generated_file_target(database_path, label="fixture DB path")
    database_path.unlink(missing_ok=True)
    db.DATA_DIR = database_path.parent
    db.DB_PATH = database_path
    db.init_db()


def fixture_row(scenario: str, index: int) -> dict[str, str]:
    common = {
        "order_number": f"FINISH-UI-{index:02d}",
        "order_date": "06.09.2026",
        "delivery_date": "10.09.2026",
        "customer": f"Клиент за преглед на приключване {index}",
        "city": "София",
        "product_type": "Полиетиленово фолио за визуална проверка",
        "ordered_gross_kg": "720",
        "ordered_rolls": "24",
        "ordered_meters": "18000",
        "ordered_units": "36000",
        "product_form": "Ръкав",
        "material": "LDPE",
        "size_thickness": "850 / 0.060 мм",
        "notes": "Детерминирана временна карта само за браузърна проверка.",
        "extrusion_sequence": "1",
        "extrusion_next_operation": "Пренавиване",
        "raw_material_a": "LDPE; Alpha 2420H | 100%",
        "packaging_method": "Ролки върху палет",
    }
    if scenario == "active_normal":
        common["customer"] = (
            "Дългосрочен индустриален клиент Балкан Пак България АД"
        )
        common["product_type"] = (
            "Термоусадъчно полиетиленово фолио за групова транспортна опаковка"
        )
    return common


def import_scenarios() -> dict[str, int]:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for index, scenario in enumerate(SCENARIOS, start=1):
        row = fixture_row(scenario, index)
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    result = import_cards_from_csv(
        "order-finish-review-fixture.csv",
        buffer.getvalue().encode("utf-8"),
        overwrite_existing=False,
    )
    if result.rows_imported != len(SCENARIOS):
        raise RuntimeError(f"Fixture import failed: {result.messages}")
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT id, order_number FROM cards ORDER BY id"
        ).fetchall()
    if len(rows) != len(SCENARIOS):
        raise RuntimeError(
            f"Fixture import did not create exactly {len(SCENARIOS)} cards."
        )
    return dict(
        zip(SCENARIOS, (int(row["id"]) for row in rows), strict=True)
    )


def require_ok(result: db.RuleResult, action: str) -> None:
    if not result.ok:
        raise RuntimeError(f"{action} failed: {'; '.join(result.messages)}")


def card_version(card_id: int) -> int:
    card = db.fetch_terminal_card_detail(card_id)
    if card is None:
        card = db.fetch_admin_card_detail(card_id)
    if card is None:
        raise RuntimeError(f"Fixture card {card_id} is missing.")
    return int(card["version"])


def release(card_id: int, machine_id: int, sequence: int) -> None:
    require_ok(
        db.release_card(card_id, machine_id, sequence, card_version(card_id)),
        f"release card {card_id}",
    )


def start(card_id: int) -> None:
    require_ok(
        db.start_production_timing(card_id, card_version(card_id)),
        f"start card {card_id}",
    )


def set_roll_defaults(
    card_id: int,
    *,
    tare: str = "1.0",
    pallet: str = "",
) -> None:
    require_ok(
        db.update_roll_defaults(
            card_id,
            card_version(card_id),
            tare_weight=tare,
            pallet_number=pallet,
        ),
        f"set roll defaults for card {card_id}",
    )


def add_roll(card_id: int, gross: str, *, pallet: str | None = None) -> None:
    require_ok(
        db.add_roll_gross_weight(
            card_id,
            card_version(card_id),
            gross,
            pallet_number=pallet,
        ),
        f"add roll for card {card_id}",
    )


def mark_rewinding(card_id: int, count: int | None) -> None:
    require_ok(
        db.update_rewinding_roll_count(card_id, card_version(card_id), count),
        f"set rewinding marker for card {card_id}",
    )


def finish(card_id: int) -> None:
    require_ok(
        db.finish_card(card_id, card_version(card_id)),
        f"finish card {card_id}",
    )


def replace_timing(
    card_id: int,
    *,
    started_at: str,
    ended_at: str | None,
) -> None:
    with db.connect() as connection:
        segment = connection.execute(
            """
            SELECT id
            FROM production_time_segments
            WHERE card_id = ?
            ORDER BY id
            LIMIT 1
            """,
            (card_id,),
        ).fetchone()
        if segment is None:
            raise RuntimeError(f"Fixture card {card_id} has no timing segment.")
        connection.execute(
            """
            UPDATE production_time_segments
            SET started_at = ?, ended_at = ?,
                end_reason = CASE WHEN ? IS NULL THEN NULL ELSE 'finish' END,
                created_at = '2026-09-06 00:00:00',
                updated_at = '2026-09-06 00:00:00'
            WHERE id = ?
            """,
            (started_at, ended_at, ended_at, int(segment["id"])),
        )
        connection.execute(
            """
            UPDATE cards
            SET first_started_at = ?, finished_at = ?,
                updated_at = '2026-09-06 00:00:00'
            WHERE id = ?
            """,
            (started_at, ended_at, card_id),
        )


def fixture_snapshot(cards: dict[str, int]) -> dict[str, object]:
    scenario_by_id = {card_id: scenario for scenario, card_id in cards.items()}
    with db.connect() as connection:
        card_rows = connection.execute(
            """
            SELECT id, order_number, status, version, machine_id,
                   machine_sequence, tare_weight, current_pallet_number,
                   rewinding_roll_count, first_started_at, finished_at,
                   final_extrusion_shift_occurrence_id
            FROM cards
            ORDER BY id
            """
        ).fetchall()
        timing_rows = connection.execute(
            """
            SELECT card_id, started_at, ended_at, end_reason
            FROM production_time_segments
            ORDER BY card_id, started_at, id
            """
        ).fetchall()
        roll_rows = connection.execute(
            """
            SELECT card_id, roll_number, gross_weight, tare_weight,
                   net_weight, pallet_number, shift_occurrence_id
            FROM roll_entries
            ORDER BY card_id, roll_number
            """
        ).fetchall()
    return {
        "cards": {
            scenario_by_id[int(row["id"])]: {
                key: row[key] for key in row.keys() if key != "id"
            }
            for row in card_rows
        },
        "timing": [list(row) for row in timing_rows],
        "rolls": [list(row) for row in roll_rows],
    }


def create_fixture(database_path: Path) -> dict[str, object]:
    reset_database(database_path)
    configuration = db.fetch_terminal_configuration()
    require_ok(
        db.start_shift("1", int(configuration["version"])),
        "start active shift",
    )
    cards = import_scenarios()

    release(cards["active_normal"], 1, 1)
    release(cards["active_marked_empty"], 2, 1)
    release(cards["active_marked_mixed"], 3, 1)
    release(cards["waiting_many_pallets"], 4, 1)
    release(cards["waiting_marker_cleared"], 4, 2)
    release(cards["waiting_zero_rolls"], 4, 3)

    start(cards["active_normal"])
    set_roll_defaults(cards["active_normal"], tare="1.2")
    for pallet_number in range(1, 14):
        add_roll(
            cards["active_normal"],
            f"{40 + pallet_number}.0",
            pallet=str(pallet_number),
        )

    start(cards["active_marked_empty"])
    set_roll_defaults(cards["active_marked_empty"], tare="1.0")
    mark_rewinding(cards["active_marked_empty"], 4)

    start(cards["active_marked_mixed"])
    set_roll_defaults(cards["active_marked_mixed"], tare="1.0", pallet="7")
    add_roll(cards["active_marked_mixed"], "42.0", pallet="7")
    add_roll(cards["active_marked_mixed"], "43.0", pallet="")
    mark_rewinding(cards["active_marked_mixed"], 2)

    waiting_many = cards["waiting_many_pallets"]
    start(waiting_many)
    set_roll_defaults(waiting_many, tare="1.0")
    mark_rewinding(waiting_many, 12)
    finish(waiting_many)
    for pallet_number in range(101, 113):
        add_roll(waiting_many, f"{30 + pallet_number - 100}.0", pallet=str(pallet_number))

    waiting_cleared = cards["waiting_marker_cleared"]
    start(waiting_cleared)
    set_roll_defaults(waiting_cleared, tare="1.0")
    mark_rewinding(waiting_cleared, 2)
    finish(waiting_cleared)
    add_roll(waiting_cleared, "37.0", pallet="201")
    mark_rewinding(waiting_cleared, None)

    waiting_zero = cards["waiting_zero_rolls"]
    start(waiting_zero)
    set_roll_defaults(waiting_zero, tare="1.0")
    mark_rewinding(waiting_zero, 1)
    finish(waiting_zero)

    timestamps = {
        "active_normal": ("2026-09-06 06:05:00", None),
        "active_marked_empty": ("2026-09-06 06:10:00", None),
        "active_marked_mixed": ("2026-09-06 06:15:00", None),
        "waiting_many_pallets": (
            "2026-09-06 06:20:00",
            "2026-09-06 08:20:00",
        ),
        "waiting_marker_cleared": (
            "2026-09-06 06:25:00",
            "2026-09-06 08:25:00",
        ),
        "waiting_zero_rolls": (
            "2026-09-06 06:30:00",
            "2026-09-06 08:30:00",
        ),
    }
    for scenario, (started_at, ended_at) in timestamps.items():
        replace_timing(
            cards[scenario],
            started_at=started_at,
            ended_at=ended_at,
        )

    with db.connect() as connection:
        connection.execute(
            """
            UPDATE shift_occurrences
            SET started_at = '2026-09-06 06:00:00',
                updated_at = '2026-09-06 06:00:00'
            WHERE ended_at IS NULL
            """
        )

    payload = {
        "db_path": str(database_path),
        "scenario_order": list(SCENARIOS),
        "cards": cards,
        "orders": {
            scenario: f"FINISH-UI-{index:02d}"
            for index, scenario in enumerate(SCENARIOS, start=1)
        },
        "snapshot": fixture_snapshot(cards),
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the guarded order-finish review browser fixture."
    )
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        database_path = resolve_under_test_runtime(
            args.db_path,
            label="fixture DB path",
        )
        output_path = resolve_under_test_runtime(
            args.output,
            label="fixture output path",
        )
        if database_path == output_path:
            raise ValueError("fixture DB path and fixture output path must differ")
        if database_path.suffix not in {".sqlite3", ".sqlite", ".db"}:
            raise ValueError("fixture DB path must name a SQLite file")
        if output_path.suffix != ".json":
            raise ValueError("fixture output path must name a JSON file")
        explicit_database = os.environ.get("EXTRUSION_DB_PATH", "").strip()
        if explicit_database:
            environment_path = Path(explicit_database)
            if not environment_path.is_absolute():
                environment_path = ROOT_DIR / environment_path
            if environment_path.resolve() != database_path:
                raise ValueError("EXTRUSION_DB_PATH must match --db-path")
        explicit_data_dir = os.environ.get("EXTRUSION_DATA_DIR", "").strip()
        if explicit_data_dir:
            environment_dir = Path(explicit_data_dir)
            if not environment_dir.is_absolute():
                environment_dir = ROOT_DIR / environment_dir
            if environment_dir.resolve() != database_path.parent:
                raise ValueError("EXTRUSION_DATA_DIR must match --db-path parent")
    except ValueError as exc:
        parser.error(str(exc))

    payload = create_fixture(database_path)
    write_text_atomic(
        output_path,
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
