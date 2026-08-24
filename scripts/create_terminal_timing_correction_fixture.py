from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app import db
from app.importer import IMPORT_FIELDS, import_cards_from_csv


SCENARIOS = (
    "running",
    "paused",
    "completed",
    "awaiting_rewinding",
    "many_rows",
)


def resolve_under_test_runtime(raw_path: str, *, label: str) -> Path:
    runtime_path = (ROOT_DIR / ".test-runtime").resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    try:
        candidate = candidate.resolve()
        relative = candidate.relative_to(runtime_path)
    except ValueError as exc:
        raise ValueError(f"{label} must be under .test-runtime") from exc
    if not relative.parts:
        raise ValueError(f"{label} must be under .test-runtime")
    if candidate.exists() and not candidate.is_file():
        raise ValueError(f"{label} must be a regular file")
    return candidate


def reset_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_path.unlink(missing_ok=True)
    db.DATA_DIR = database_path.parent
    db.DB_PATH = database_path
    db.init_db()


def write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def fixture_row(order_number: str, customer: str) -> dict[str, str]:
    return {
        "order_number": order_number,
        "order_date": "20.08.2026",
        "delivery_date": "24.08.2026",
        "customer": customer,
        "city": "София",
        "product_type": "Фолио за проверка на производствено време",
        "ordered_gross_kg": "500",
        "ordered_rolls": "20",
        "ordered_meters": "12000",
        "ordered_units": "24000",
        "product_form": "Ръкав",
        "material": "LDPE",
        "size_thickness": "600 / 0.050",
        "notes": "Детерминирана временна карта само за браузърна проверка.",
        "extrusion_sequence": "1",
        "extrusion_next_operation": "Пренавиване",
        "raw_material_a": "LDPE; Alpha 2420H | 100%",
        "packaging_method": "Ролки",
    }


def import_scenarios() -> dict[str, int]:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for index, scenario in enumerate(SCENARIOS, start=1):
        row = fixture_row(
            f"TIMING-UI-{index:02d}",
            f"Клиент за време {scenario}",
        )
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    result = import_cards_from_csv(
        "terminal-timing-correction-fixture.csv",
        buffer.getvalue().encode("utf-8"),
        overwrite_existing=False,
    )
    if result.rows_imported != len(SCENARIOS):
        raise RuntimeError(f"Fixture import failed: {result.messages}")
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT id, order_number FROM cards ORDER BY order_number"
        ).fetchall()
    if len(rows) != len(SCENARIOS):
        raise RuntimeError("Fixture import did not create exactly five cards.")
    return {
        scenario: int(row["id"])
        for scenario, row in zip(SCENARIOS, rows, strict=True)
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


def set_roll_defaults(card_id: int, *, pallet: str = "") -> None:
    require_ok(
        db.update_roll_defaults(
            card_id,
            card_version(card_id),
            tare_weight="1.25",
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


def mark_rewinding(card_id: int, count: int) -> None:
    require_ok(
        db.update_rewinding_roll_count(card_id, card_version(card_id), count),
        f"mark rewinding for card {card_id}",
    )


def finish(card_id: int) -> None:
    require_ok(
        db.finish_card(card_id, card_version(card_id)),
        f"finish card {card_id}",
    )


def many_timing_rows() -> list[tuple[str, str | None, str | None]]:
    rows: list[tuple[str, str | None, str | None]] = []
    start_minutes = 4 * 60
    for index in range(18):
        start_total = start_minutes + index * 7
        start_hour, start_minute = divmod(start_total, 60)
        started_at = f"2026-08-20 {start_hour:02d}:{start_minute:02d}:{(index + 11) % 60:02d}"
        if index == 17:
            rows.append((started_at, None, None))
            continue
        stop_total = start_total + 5
        stop_hour, stop_minute = divmod(stop_total, 60)
        ended_at = f"2026-08-20 {stop_hour:02d}:{stop_minute:02d}:{(index + 23) % 60:02d}"
        rows.append((started_at, ended_at, "pause"))
    return rows


def replace_timing(
    card_id: int,
    rows: list[tuple[str, str | None, str | None]],
    *,
    finished_at: str | None = None,
) -> None:
    with db.connect() as connection:
        connection.execute(
            "DELETE FROM production_time_segments WHERE card_id = ?",
            (card_id,),
        )
        connection.executemany(
            """
            INSERT INTO production_time_segments (
                card_id, started_at, ended_at, end_reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, '2026-08-20 00:00:00', '2026-08-20 00:00:00')
            """,
            [(card_id, started_at, ended_at, end_reason) for started_at, ended_at, end_reason in rows],
        )
        connection.execute(
            """
            UPDATE cards
            SET first_started_at = ?, finished_at = ?, updated_at = '2026-08-20 00:00:00'
            WHERE id = ?
            """,
            (rows[0][0], finished_at, card_id),
        )


def fixture_snapshot(cards: dict[str, int]) -> dict[str, object]:
    with db.connect() as connection:
        card_rows = connection.execute(
            """
            SELECT id, status, machine_id, machine_sequence, version,
                   tare_weight, current_pallet_number, rewinding_roll_count,
                   first_started_at, finished_at
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
    scenario_by_id = {card_id: scenario for scenario, card_id in cards.items()}
    return {
        "cards": {
            scenario_by_id[int(row["id"])]: {
                key: row[key]
                for key in row.keys()
                if key != "id"
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
        db.update_shift_count(int(configuration["version"]), "2"),
        "configure two shifts",
    )
    configuration = db.fetch_terminal_configuration()
    require_ok(
        db.start_shift("1", int(configuration["version"])),
        "start active shift",
    )
    cards = import_scenarios()

    release(cards["running"], 1, 1)
    release(cards["paused"], 2, 1)
    release(cards["completed"], 3, 1)
    release(cards["awaiting_rewinding"], 3, 1)
    release(cards["many_rows"], 4, 1)

    start(cards["running"])
    set_roll_defaults(cards["running"], pallet="7")
    add_roll(cards["running"], "41.50", pallet="7")
    set_roll_defaults(cards["running"], pallet="")
    add_roll(cards["running"], "42.75", pallet="")

    start(cards["paused"])
    set_roll_defaults(cards["paused"], pallet="3")
    add_roll(cards["paused"], "38.00", pallet="3")
    pause(cards["paused"])

    start(cards["completed"])
    set_roll_defaults(cards["completed"], pallet="2")
    add_roll(cards["completed"], "30.00", pallet="2")
    finish(cards["completed"])

    start(cards["awaiting_rewinding"])
    set_roll_defaults(cards["awaiting_rewinding"], pallet="5")
    add_roll(cards["awaiting_rewinding"], "33.00", pallet="5")
    mark_rewinding(cards["awaiting_rewinding"], 1)
    finish(cards["awaiting_rewinding"])

    start(cards["many_rows"])
    set_roll_defaults(cards["many_rows"], pallet="9")
    add_roll(cards["many_rows"], "50.00", pallet="9")

    replace_timing(
        cards["running"],
        [
            ("2026-08-20 07:00:17", "2026-08-20 08:00:29", "pause"),
            ("2026-08-20 08:15:31", "2026-08-20 09:00:41", "pause"),
            ("2026-08-20 09:10:43", None, None),
        ],
    )
    replace_timing(
        cards["paused"],
        [
            ("2026-08-20 07:30:17", "2026-08-20 08:30:29", "pause"),
            ("2026-08-20 08:45:31", "2026-08-20 09:15:41", "pause"),
        ],
    )
    replace_timing(
        cards["completed"],
        [("2026-08-20 07:00:17", "2026-08-20 08:00:29", "finish")],
        finished_at="2026-08-20 08:00:29",
    )
    replace_timing(
        cards["awaiting_rewinding"],
        [("2026-08-20 07:15:17", "2026-08-20 08:05:29", "finish")],
        finished_at="2026-08-20 08:05:29",
    )
    replace_timing(cards["many_rows"], many_timing_rows())

    active_shift = db.fetch_active_shift()
    if active_shift is None:
        raise RuntimeError("Fixture active shift is missing.")
    payload = {
        "db_path": str(database_path),
        "active_shift": {
            "id": int(active_shift["id"]),
            "shift_number": int(active_shift["shift_number"]),
        },
        "scenario_order": list(SCENARIOS),
        "cards": cards,
        "orders": {
            scenario: f"TIMING-UI-{index:02d}"
            for index, scenario in enumerate(SCENARIOS, start=1)
        },
        "snapshot": fixture_snapshot(cards),
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the temporary terminal timing-correction browser fixture."
    )
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        database_path = resolve_under_test_runtime(args.db_path, label="fixture DB path")
        output_path = resolve_under_test_runtime(args.output, label="fixture output path")
        if database_path == output_path:
            raise ValueError("fixture DB path and fixture output path must differ")
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
        if database_path.suffix not in {".sqlite3", ".sqlite", ".db"}:
            raise ValueError("fixture DB path must name a SQLite file")
        if output_path.suffix != ".json":
            raise ValueError("fixture output path must name a JSON file")
    except ValueError as exc:
        parser.error(str(exc))

    payload = create_fixture(database_path)
    write_text(
        output_path,
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
