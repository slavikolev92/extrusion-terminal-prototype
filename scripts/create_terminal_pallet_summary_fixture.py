from __future__ import annotations

import argparse
import csv
import hashlib
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


SCENARIO_ORDER = (
    "empty",
    "all_unassigned",
    "no_weights",
    "partial_weights",
    "complete_weights",
    "mixed_unassigned",
    "awaiting_partial",
    "completed_complete",
    "archived_complete",
    "many_pallets",
)

AUDITED_TABLES = (
    "cards",
    "roll_entries",
    "production_time_segments",
    "recipe_actual_entries",
    "recipe_components",
    "shift_occurrences",
    "terminal_configuration",
)


def require_single_link(path: Path, *, label: str) -> None:
    if path.exists() and path.stat().st_nlink != 1:
        raise ValueError(f"{label} must not be hard-linked")


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
    require_single_link(resolved, label=label)
    return resolved


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
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


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
        raise RuntimeError(
            f"Fixture import did not create exactly {len(SCENARIO_ORDER)} cards."
        )
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


def save_weight(card_id: int, pallet_number: int, weight: str) -> None:
    require_ok(
        db.update_terminal_pallet_weight(
            card_id,
            pallet_number,
            card_version(card_id),
            weight,
        ).result,
        f"save pallet {pallet_number} weight for card {card_id}",
    )


def expected_many_rows() -> list[list[str]]:
    return [
        [
            str(pallet),
            "1",
            f"{10 + pallet}.0",
            f"{pallet}.00",
            f"{10 + (2 * pallet)}.00",
            f"{9 + pallet}.0",
        ]
        for pallet in range(1, 25)
    ]


def stabilize_fixture_times() -> None:
    with db.connect() as connection:
        connection.execute(
            "UPDATE cards SET created_at = '2026-09-10 06:00:00', "
            "updated_at = '2026-09-10 06:30:00', "
            "first_started_at = CASE WHEN first_started_at IS NULL THEN NULL "
            "ELSE '2026-09-10 06:05:00' END, "
            "finished_at = CASE WHEN finished_at IS NULL THEN NULL "
            "ELSE '2026-09-10 06:25:00' END"
        )
        connection.execute(
            "UPDATE roll_entries SET created_at = '2026-09-10 06:10:00', "
            "updated_at = '2026-09-10 06:10:00'"
        )
        connection.execute(
            "UPDATE production_time_segments "
            "SET started_at = '2026-09-10 06:05:00', "
            "ended_at = CASE WHEN ended_at IS NULL THEN NULL "
            "ELSE '2026-09-10 06:25:00' END, "
            "created_at = '2026-09-10 06:05:00', "
            "updated_at = '2026-09-10 06:25:00'"
        )
        connection.execute(
            "UPDATE shift_occurrences SET started_at = '2026-09-10 06:00:00', "
            "created_at = '2026-09-10 06:00:00', "
            "updated_at = '2026-09-10 06:00:00'"
        )
        connection.execute(
            "UPDATE terminal_configuration SET updated_at = '2026-09-10 06:00:00'"
        )
        connection.execute(
            "UPDATE recipe_actual_entries SET created_at = '2026-09-10 06:00:00', "
            "updated_at = '2026-09-10 06:00:00'"
        )
        connection.execute(
            "UPDATE recipe_components SET created_at = '2026-09-10 06:00:00', "
            "updated_at = '2026-09-10 06:00:00'"
        )
        connection.execute(
            "UPDATE card_pallet_weights SET created_at = '2026-09-10 06:15:00', "
            "updated_at = '2026-09-10 06:15:00'"
        )


def audited_table_snapshot() -> dict[str, object]:
    tables: dict[str, object] = {}
    with db.connect() as connection:
        for table in AUDITED_TABLES:
            info = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            columns = [str(row["name"]) for row in info]
            primary = [
                (int(row["pk"]), str(row["name"]))
                for row in info
                if int(row["pk"]) > 0
            ]
            order_columns = [name for _, name in sorted(primary)] or columns
            order_sql = ", ".join(f'"{name}"' for name in order_columns)
            rows = [
                [row[column] for column in columns]
                for row in connection.execute(
                    f'SELECT * FROM "{table}" ORDER BY {order_sql}'
                ).fetchall()
            ]
            row_json = [
                json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                for row in rows
            ]
            tables[table] = {
                "columns": columns,
                "rows": rows,
                "row_hashes": [
                    hashlib.sha256(value.encode("utf-8")).hexdigest()
                    for value in row_json
                ],
                "table_hash": hashlib.sha256(
                    "\n".join(row_json).encode("utf-8")
                ).hexdigest(),
            }
        pallet_rows = [
            list(row)
            for row in connection.execute(
                "SELECT card_id, pallet_number, weight_hundredths, created_at, updated_at "
                "FROM card_pallet_weights ORDER BY card_id, pallet_number"
            ).fetchall()
        ]
    return {
        "algorithm": "sha256",
        "tables": tables,
        "pallet_weight_columns": [
            "card_id",
            "pallet_number",
            "weight_hundredths",
            "created_at",
            "updated_at",
        ],
        "pallet_weight_rows": pallet_rows,
    }


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

    # Build completed/waiting cards first so their machines are reusable by the
    # active scenarios in the final canonical state.
    completed_id = cards["completed_complete"]
    release(completed_id, 2, 1)
    start(completed_id)
    set_tare(completed_id)
    add_roll(completed_id, "60.0", "3")
    add_roll(completed_id, "40.5", "12")
    save_weight(completed_id, 3, "12.0")
    save_weight(completed_id, 12, "15.0")
    finish(completed_id)

    archived_id = cards["archived_complete"]
    release(archived_id, 3, 1)
    start(archived_id)
    set_tare(archived_id)
    add_roll(archived_id, "45.0", "6")
    add_roll(archived_id, "55.5", "9")
    save_weight(archived_id, 6, "11.5")
    save_weight(archived_id, 9, "16.0")
    finish(archived_id)
    require_ok(
        db.archive_completed_card(archived_id, card_version(archived_id)),
        f"archive card {archived_id}",
    )

    waiting_id = cards["awaiting_partial"]
    release(waiting_id, 1, 1)
    start(waiting_id)
    set_tare(waiting_id)
    add_roll(waiting_id, "70.0", "4")
    add_roll(waiting_id, "30.5", "5")
    save_weight(waiting_id, 4, "15.5")
    mark_rewinding(waiting_id, 1)
    finish(waiting_id)

    many_id = cards["many_pallets"]
    release(many_id, 4, 1)
    start(many_id)
    set_tare(many_id)
    mark_rewinding(many_id, 24)
    finish(many_id)
    for pallet in range(1, 25):
        add_roll(many_id, f"{10 + pallet}.0", str(pallet))
        save_weight(many_id, pallet, f"{pallet}.0")

    empty_id = cards["empty"]
    release(empty_id, 1, 1)

    unassigned_id = cards["all_unassigned"]
    release(unassigned_id, 1, 2)
    start(unassigned_id)
    set_tare(unassigned_id)
    add_roll(unassigned_id, "50.0", "")
    add_roll(unassigned_id, "75.5", "")
    finish(unassigned_id)

    no_weights_id = cards["no_weights"]
    release(no_weights_id, 1, 3)
    start(no_weights_id)
    set_tare(no_weights_id)
    for gross, pallet in (
        ("120.0", "10"),
        ("100.0", "2"),
        ("100.1", "2"),
    ):
        add_roll(no_weights_id, gross, pallet)

    partial_id = cards["partial_weights"]
    release(partial_id, 2, 1)
    start(partial_id)
    set_tare(partial_id)
    add_roll(partial_id, "60.0", "2")
    add_roll(partial_id, "40.5", "7")
    save_weight(partial_id, 2, "10.35")

    complete_id = cards["complete_weights"]
    release(complete_id, 3, 1)
    start(complete_id)
    set_tare(complete_id)
    add_roll(complete_id, "60.0", "2")
    add_roll(complete_id, "40.5", "7")
    save_weight(complete_id, 2, "12.5")
    save_weight(complete_id, 7, "10.0")
    pause(complete_id)

    mixed_id = cards["mixed_unassigned"]
    release(mixed_id, 4, 1)
    start(mixed_id)
    set_tare(mixed_id)
    add_roll(mixed_id, "60.0", "3")
    add_roll(mixed_id, "40.5", "")
    save_weight(mixed_id, 3, "10.0")
    mark_rewinding(mixed_id, 1)

    stabilize_fixture_times()

    active_shift = db.fetch_active_shift()
    if active_shift is None:
        raise RuntimeError("Fixture active shift is missing.")

    scenario_payload = {
        "empty": {
            "card_id": empty_id,
            "machine_id": 1,
            "order_number": "PALLET-UI-01",
            "status": "pending",
            "summary_state": "empty",
            "weight_state": "none",
            "expected_rows": [],
            "expected_total": None,
            "expected_inputs": {},
            "editable": {"terminal": True, "admin": False},
            "finish_eligibility": {
                "normal": None,
                "waiting_entry": None,
                "waiting_final": None,
            },
        },
        "all_unassigned": {
            "card_id": unassigned_id,
            "machine_id": 1,
            "order_number": "PALLET-UI-02",
            "status": "completed",
            "summary_state": "ready",
            "weight_state": "none",
            "expected_rows": [["Без палет", "2", "125.5", "-", "-", "123.5"]],
            "expected_total": ["Общо", "2", "125.5", "-", "-", "123.5"],
            "expected_inputs": {},
            "editable": {"terminal": True, "admin": True},
            "finish_eligibility": {
                "normal": None,
                "waiting_entry": None,
                "waiting_final": None,
            },
        },
        "no_weights": {
            "card_id": no_weights_id,
            "machine_id": 1,
            "order_number": "PALLET-UI-03",
            "status": "running",
            "summary_state": "ready",
            "weight_state": "none",
            "expected_rows": [
                ["2", "2", "200.1", "", "-", "198.1"],
                ["10", "1", "120.0", "", "-", "119.0"],
            ],
            "expected_total": ["Общо", "3", "320.1", "-", "-", "317.1"],
            "expected_inputs": {"2": "", "10": ""},
            "editable": {"terminal": True, "admin": False},
            "finish_eligibility": {
                "normal": True,
                "waiting_entry": None,
                "waiting_final": None,
            },
        },
        "partial_weights": {
            "card_id": partial_id,
            "machine_id": 2,
            "order_number": "PALLET-UI-04",
            "status": "running",
            "summary_state": "ready",
            "weight_state": "partial",
            "expected_rows": [
                ["2", "1", "60.0", "10.35", "70.35", "59.0"],
                ["7", "1", "40.5", "", "-", "39.5"],
            ],
            "expected_total": ["Общо", "2", "100.5", "-", "-", "98.5"],
            "expected_inputs": {"2": "10.35", "7": ""},
            "editable": {"terminal": True, "admin": False},
            "finish_eligibility": {
                "normal": False,
                "waiting_entry": None,
                "waiting_final": None,
            },
        },
        "complete_weights": {
            "card_id": complete_id,
            "machine_id": 3,
            "order_number": "PALLET-UI-05",
            "status": "paused",
            "summary_state": "ready",
            "weight_state": "complete",
            "expected_rows": [
                ["2", "1", "60.0", "12.50", "72.50", "59.0"],
                ["7", "1", "40.5", "10.00", "50.50", "39.5"],
            ],
            "expected_total": ["Общо", "2", "100.5", "22.50", "123.00", "98.5"],
            "expected_inputs": {"2": "12.50", "7": "10.00"},
            "editable": {"terminal": True, "admin": False},
            "finish_eligibility": {
                "normal": True,
                "waiting_entry": None,
                "waiting_final": None,
            },
        },
        "mixed_unassigned": {
            "card_id": mixed_id,
            "machine_id": 4,
            "order_number": "PALLET-UI-06",
            "status": "running",
            "summary_state": "ready",
            "weight_state": "partial",
            "expected_rows": [
                ["3", "1", "60.0", "10.00", "70.00", "59.0"],
                ["Без палет", "1", "40.5", "-", "-", "39.5"],
            ],
            "expected_total": ["Общо", "2", "100.5", "-", "-", "98.5"],
            "expected_inputs": {"3": "10.00"},
            "editable": {"terminal": True, "admin": False},
            "finish_eligibility": {
                "normal": None,
                "waiting_entry": True,
                "waiting_final": None,
            },
        },
        "awaiting_partial": {
            "card_id": waiting_id,
            "machine_id": 1,
            "order_number": "PALLET-UI-07",
            "status": "awaiting_rewinding",
            "summary_state": "ready",
            "weight_state": "partial",
            "expected_rows": [
                ["4", "1", "70.0", "15.50", "85.50", "69.0"],
                ["5", "1", "30.5", "", "-", "29.5"],
            ],
            "expected_total": ["Общо", "2", "100.5", "-", "-", "98.5"],
            "expected_inputs": {"4": "15.50", "5": ""},
            "editable": {"terminal": True, "admin": False},
            "finish_eligibility": {
                "normal": None,
                "waiting_entry": None,
                "waiting_final": False,
            },
        },
        "completed_complete": {
            "card_id": completed_id,
            "machine_id": 2,
            "order_number": "PALLET-UI-08",
            "status": "completed",
            "summary_state": "ready",
            "weight_state": "complete",
            "expected_rows": [
                ["3", "1", "60.0", "12.00", "72.00", "59.0"],
                ["12", "1", "40.5", "15.00", "55.50", "39.5"],
            ],
            "expected_total": ["Общо", "2", "100.5", "27.00", "127.50", "98.5"],
            "expected_inputs": {"3": "12.00", "12": "15.00"},
            "editable": {"terminal": True, "admin": True},
            "finish_eligibility": {
                "normal": None,
                "waiting_entry": None,
                "waiting_final": None,
            },
        },
        "archived_complete": {
            "card_id": archived_id,
            "machine_id": 3,
            "order_number": "PALLET-UI-09",
            "status": "archived",
            "summary_state": "ready",
            "weight_state": "complete",
            "expected_rows": [
                ["6", "1", "45.0", "11.50", "56.50", "44.0"],
                ["9", "1", "55.5", "16.00", "71.50", "54.5"],
            ],
            "expected_total": ["Общо", "2", "100.5", "27.50", "128.00", "98.5"],
            "expected_inputs": {"6": "11.50", "9": "16.00"},
            "editable": {"terminal": False, "admin": True},
            "finish_eligibility": {
                "normal": None,
                "waiting_entry": None,
                "waiting_final": None,
            },
        },
        "many_pallets": {
            "card_id": many_id,
            "machine_id": 4,
            "order_number": "PALLET-UI-10",
            "status": "awaiting_rewinding",
            "summary_state": "ready",
            "weight_state": "complete",
            "expected_rows": expected_many_rows(),
            "expected_total": ["Общо", "24", "540.0", "300.00", "840.00", "516.0"],
            "expected_inputs": {str(pallet): f"{pallet}.00" for pallet in range(1, 25)},
            "editable": {"terminal": True, "admin": False},
            "finish_eligibility": {
                "normal": None,
                "waiting_entry": None,
                "waiting_final": True,
            },
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
        "audit_baseline": audited_table_snapshot(),
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
    atomic_write_text(
        output_path,
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
        label="fixture output path",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
