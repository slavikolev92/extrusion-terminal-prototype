from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app import db
from app.importer import IMPORT_FIELDS, import_cards_from_csv


SCENARIO_ORDER = (
    "pending_empty",
    "running_mixed",
    "paused_all_unassigned",
    "awaiting_many_pallets",
    "completed_numbered",
)


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
        if current.exists() or current.is_symlink():
            if current.is_symlink():
                raise ValueError(f"{label} must be under .test-runtime")

    runtime_root = runtime_path.resolve()
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(runtime_root)
    except ValueError as exc:
        raise ValueError(f"{label} must be under .test-runtime") from exc
    if not relative.parts:
        raise ValueError(f"{label} must be under .test-runtime")
    if resolved.exists() and not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    return resolved


def reset_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_path.unlink(missing_ok=True)
    db.DATA_DIR = database_path.parent
    db.DB_PATH = database_path
    db.init_db()


def fixture_row(order_number: str) -> dict[str, str]:
    return {
        "order_number": order_number,
        "order_date": "04.08.2026",
        "delivery_date": "05.08.2026",
        "customer": "Браузърна проверка",
        "city": "София",
        "product_type": "Полиетиленово фолио",
        "ordered_gross_kg": "800",
        "ordered_rolls": "120",
        "ordered_meters": "12000",
        "ordered_units": "24000",
        "product_form": "Ръкав",
        "material": "LDPE",
        "size_thickness": "600 / 0.050",
        "extrusion_sequence": "1",
        "extrusion_next_operation": "Пренавиване",
        "raw_material_a": "LDPE; Alpha 2420H | 100%",
        "packaging_method": "Ролки",
    }


def import_scenarios() -> dict[str, int]:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for index, _scenario in enumerate(SCENARIO_ORDER, start=1):
        row = fixture_row(f"PALLET-UI-{index:02d}")
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})

    result = import_cards_from_csv(
        "terminal-pallet-summary-fixture.csv",
        buffer.getvalue().encode("utf-8"),
        overwrite_existing=False,
    )
    if result.rows_imported != len(SCENARIO_ORDER):
        raise RuntimeError(f"Fixture import failed: {result.messages}")

    with db.connect() as connection:
        rows = connection.execute(
            "SELECT id, order_number FROM cards ORDER BY order_number"
        ).fetchall()
    if len(rows) != len(SCENARIO_ORDER):
        raise RuntimeError("Fixture import did not create exactly five cards.")
    return {
        scenario: int(row["id"])
        for scenario, row in zip(SCENARIO_ORDER, rows, strict=True)
    }


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


def pause(card_id: int) -> None:
    require_ok(
        db.pause_production_timing(card_id, card_version(card_id)),
        f"pause card {card_id}",
    )


def set_tare(card_id: int, tare: str = "1.0") -> None:
    require_ok(
        db.update_roll_defaults(card_id, card_version(card_id), tare_weight=tare),
        f"set tare for card {card_id}",
    )


def add_roll(card_id: int, gross: str, pallet: str) -> None:
    require_ok(
        db.add_roll_gross_weight(
            card_id,
            card_version(card_id),
            gross,
            pallet_number=pallet,
        ),
        f"add roll to card {card_id}",
    )


def mark_rewinding(card_id: int, count: int) -> None:
    require_ok(
        db.update_rewinding_roll_count(card_id, card_version(card_id), count),
        f"mark card {card_id} for rewinding",
    )


def finish(card_id: int) -> None:
    require_ok(
        db.finish_card(card_id, card_version(card_id)),
        f"finish card {card_id}",
    )


def expected_many_rows() -> list[list[str]]:
    return [
        [str(pallet), "1", f"{10 + pallet}.0", f"{9 + pallet}.0"]
        for pallet in range(1, 25)
    ]


def production_snapshot(cards: dict[str, int]) -> dict[str, object]:
    with db.connect() as connection:
        card_rows = connection.execute(
            "SELECT id, version, current_pallet_number FROM cards ORDER BY id"
        ).fetchall()
        counts = {
            "cards": int(connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0]),
            "rolls": int(
                connection.execute("SELECT COUNT(*) FROM roll_entries").fetchone()[0]
            ),
            "timing_rows": int(
                connection.execute(
                    "SELECT COUNT(*) FROM production_time_segments"
                ).fetchone()[0]
            ),
            "pallet_assignments": int(
                connection.execute(
                    "SELECT COUNT(*) FROM roll_entries WHERE pallet_number IS NOT NULL"
                ).fetchone()[0]
            ),
        }
    scenario_by_id = {card_id: scenario for scenario, card_id in cards.items()}
    return {
        "cards": {
            scenario_by_id[int(row["id"])]: {
                "version": int(row["version"]),
                "current_pallet_number": row["current_pallet_number"],
            }
            for row in card_rows
        },
        "counts": counts,
    }


def create_fixture(database_path: Path) -> dict[str, object]:
    reset_database(database_path)
    configuration = db.fetch_terminal_configuration()
    require_ok(
        db.update_shift_count(int(configuration["version"]), "2"),
        "configure two shifts",
    )
    configuration = db.fetch_terminal_configuration()
    require_ok(
        db.start_shift("1", int(configuration["version"])),
        "start active shift",
    )
    cards = import_scenarios()

    release(cards["pending_empty"], 1, 1)
    release(cards["running_mixed"], 1, 1)
    release(cards["paused_all_unassigned"], 2, 1)
    release(cards["awaiting_many_pallets"], 3, 1)
    release(cards["completed_numbered"], 4, 1)

    running_id = cards["running_mixed"]
    start(running_id)
    set_tare(running_id)
    for gross, pallet in (
        ("120.0", "10"),
        ("80.0", ""),
        ("100.0", "2"),
        ("100.1", "2"),
    ):
        add_roll(running_id, gross, pallet)
    mark_rewinding(running_id, 1)

    paused_id = cards["paused_all_unassigned"]
    start(paused_id)
    set_tare(paused_id)
    add_roll(paused_id, "50.0", "")
    add_roll(paused_id, "75.5", "")
    mark_rewinding(paused_id, 1)
    pause(paused_id)

    waiting_id = cards["awaiting_many_pallets"]
    start(waiting_id)
    set_tare(waiting_id)
    mark_rewinding(waiting_id, 24)
    finish(waiting_id)
    for pallet in range(1, 25):
        add_roll(waiting_id, f"{10 + pallet}.0", str(pallet))

    completed_id = cards["completed_numbered"]
    start(completed_id)
    set_tare(completed_id)
    add_roll(completed_id, "60.0", "3")
    add_roll(completed_id, "40.5", "12")
    finish(completed_id)

    active_shift = db.fetch_active_shift()
    if active_shift is None:
        raise RuntimeError("Fixture active shift is missing.")

    scenario_payload = {
        "pending_empty": {
            "card_id": cards["pending_empty"],
            "machine_id": 1,
            "order_number": "PALLET-UI-01",
            "status": "pending",
            "summary_state": "empty",
            "expected_rows": [],
            "expected_total": None,
        },
        "running_mixed": {
            "card_id": running_id,
            "machine_id": 1,
            "order_number": "PALLET-UI-02",
            "status": "running",
            "summary_state": "ready",
            "expected_rows": [
                ["2", "2", "200.1", "198.1"],
                ["10", "1", "120.0", "119.0"],
                ["Без палет", "1", "80.0", "79.0"],
            ],
            "expected_total": ["Общо", "4", "400.1", "396.1"],
        },
        "paused_all_unassigned": {
            "card_id": paused_id,
            "machine_id": 2,
            "order_number": "PALLET-UI-03",
            "status": "paused",
            "summary_state": "ready",
            "expected_rows": [["Без палет", "2", "125.5", "123.5"]],
            "expected_total": ["Общо", "2", "125.5", "123.5"],
        },
        "awaiting_many_pallets": {
            "card_id": waiting_id,
            "machine_id": 3,
            "order_number": "PALLET-UI-04",
            "status": "awaiting_rewinding",
            "summary_state": "ready",
            "expected_rows": expected_many_rows(),
            "expected_total": ["Общо", "24", "540.0", "516.0"],
        },
        "completed_numbered": {
            "card_id": completed_id,
            "machine_id": 4,
            "order_number": "PALLET-UI-05",
            "status": "completed",
            "summary_state": "ready",
            "expected_rows": [
                ["3", "1", "60.0", "59.0"],
                ["12", "1", "40.5", "39.5"],
            ],
            "expected_total": ["Общо", "2", "100.5", "98.5"],
        },
    }
    return {
        "db_path": str(database_path),
        "active_shift": {
            "id": int(active_shift["id"]),
            "version": int(active_shift["version"]),
            "shift_number": int(active_shift["shift_number"]),
            "alternate_number": 2,
        },
        "scenario_order": list(SCENARIO_ORDER),
        "scenarios": scenario_payload,
        "production_snapshot": production_snapshot(cards),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the guarded terminal pallet-summary browser fixture."
    )
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--output", required=True)
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

    payload = create_fixture(database_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
