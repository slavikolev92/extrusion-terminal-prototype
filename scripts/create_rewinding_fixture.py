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


SCENARIOS = (
    "running_mixed",
    "paused_marked",
    "waiting_newest",
    "waiting_older",
    "waiting_zero",
    "completed_editable",
    "follow_up",
    "paused_follow_up",
)


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


def fixture_row(order_number: str, customer: str) -> dict[str, str]:
    return {
        "order_number": order_number,
        "order_date": "26.07.2026",
        "delivery_date": "30.07.2026",
        "customer": customer,
        "city": "София",
        "product_type": "Полиетиленово фолио",
        "ordered_gross_kg": "500",
        "ordered_rolls": "20",
        "ordered_meters": "12000",
        "ordered_units": "24000",
        "product_form": "Ръкав",
        "material": "LDPE",
        "size_thickness": "600 / 0.050",
        "notes": "Временна карта само за браузърна проверка.",
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
        writer.writerow(
            {
                field: fixture_row(
                    f"REW-UI-{index:02d}",
                    f"Клиент {index} за пренавиване",
                ).get(field, "")
                for field in IMPORT_FIELDS
            }
        )
    result = import_cards_from_csv(
        "rewinding-ui-fixture.csv",
        buffer.getvalue().encode("utf-8"),
        overwrite_existing=False,
    )
    if result.rows_imported != len(SCENARIOS):
        raise RuntimeError(f"Fixture import failed: {result.messages}")

    with db.connect() as connection:
        ids = [
            int(row["id"])
            for row in connection.execute(
                "SELECT id FROM cards ORDER BY id"
            ).fetchall()
        ]
    if len(ids) != len(SCENARIOS):
        raise RuntimeError("Fixture import did not create exactly seven cards.")
    return dict(zip(SCENARIOS, ids, strict=True))


def card_version(card_id: int) -> int:
    card = db.fetch_terminal_card_detail(card_id)
    if card is None:
        card = db.fetch_admin_card_detail(card_id)
    if card is None:
        raise RuntimeError(f"Fixture card {card_id} is missing.")
    return int(card["version"])


def require_ok(result: db.RuleResult, action: str) -> None:
    if not result.ok:
        raise RuntimeError(f"{action} failed: {'; '.join(result.messages)}")


def release(card_id: int, machine_id: int, sequence: int) -> None:
    require_ok(
        db.release_card(card_id, machine_id, sequence, card_version(card_id)),
        f"release card {card_id}",
    )


def set_defaults(card_id: int, *, tare: str = "1.0", pallet: str = "") -> None:
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
        f"add roll to card {card_id}",
    )


def mark_rewinding(card_id: int, count: int) -> None:
    require_ok(
        db.update_rewinding_roll_count(card_id, card_version(card_id), count),
        f"mark card {card_id} for rewinding",
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


def finish(card_id: int) -> None:
    require_ok(
        db.finish_card(card_id, card_version(card_id)),
        f"finish card {card_id}",
    )


def create_fixture(database_path: Path) -> dict[str, object]:
    reset_database(database_path)
    configuration = db.fetch_terminal_configuration()
    require_ok(
        db.start_shift("1", int(configuration["version"])),
        "start active shift",
    )
    cards = import_scenarios()

    release(cards["running_mixed"], 1, 1)
    release(cards["follow_up"], 1, 2)
    release(cards["paused_marked"], 2, 1)
    release(cards["waiting_newest"], 2, 2)
    release(cards["waiting_older"], 3, 1)
    release(cards["waiting_zero"], 4, 1)
    release(cards["completed_editable"], 3, 2)
    release(cards["paused_follow_up"], 2, 3)

    running_id = cards["running_mixed"]
    start(running_id)
    set_defaults(running_id, pallet="7")
    add_roll(running_id, "20.0")
    add_roll(running_id, "21.0", pallet="")
    mark_rewinding(running_id, 3)

    paused_id = cards["paused_marked"]
    start(paused_id)
    set_defaults(paused_id, pallet="8")
    add_roll(paused_id, "22.0")
    add_roll(paused_id, "23.0", pallet="")
    mark_rewinding(paused_id, 4)
    pause(paused_id)

    for scenario, count, pallet_values in (
        ("waiting_newest", 6, ("11", "")),
        ("waiting_older", 2, ("12",)),
        ("waiting_zero", 5, ()),
    ):
        card_id = cards[scenario]
        start(card_id)
        set_defaults(card_id, pallet="")
        mark_rewinding(card_id, count)
        finish(card_id)
        for offset, pallet in enumerate(pallet_values, start=1):
            add_roll(card_id, f"{24 + offset}.0", pallet=pallet)

    completed_id = cards["completed_editable"]
    start(completed_id)
    set_defaults(completed_id, pallet="15")
    add_roll(completed_id, "31.0")
    add_roll(completed_id, "32.0", pallet="")
    finish(completed_id)

    # Fixed timestamps make ordering and timing-preservation assertions repeatable.
    with db.connect() as connection:
        connection.execute(
            "UPDATE shift_occurrences SET started_at = '2026-07-26 06:00:00' WHERE ended_at IS NULL"
        )
        timestamp_by_scenario = {
            "running_mixed": ("2026-07-26 06:05:00", None, None),
            "paused_marked": ("2026-07-26 06:10:00", None, "2026-07-26 06:40:00"),
            "waiting_newest": ("2026-07-26 07:00:00", "2026-07-26 09:30:00", "2026-07-26 09:30:00"),
            "waiting_older": ("2026-07-26 06:30:00", "2026-07-26 08:45:00", "2026-07-26 08:45:00"),
            "waiting_zero": ("2026-07-26 06:20:00", "2026-07-26 08:15:00", "2026-07-26 08:15:00"),
            "completed_editable": ("2026-07-26 05:30:00", "2026-07-26 07:30:00", "2026-07-26 07:30:00"),
        }
        for scenario, (started_at, finished_at, segment_end) in timestamp_by_scenario.items():
            card_id = cards[scenario]
            connection.execute(
                "UPDATE cards SET first_started_at = ?, finished_at = ? WHERE id = ?",
                (started_at, finished_at, card_id),
            )
            segment = connection.execute(
                "SELECT id, ended_at FROM production_time_segments WHERE card_id = ? ORDER BY id LIMIT 1",
                (card_id,),
            ).fetchone()
            if segment is not None:
                connection.execute(
                    """
                    UPDATE production_time_segments
                    SET started_at = ?,
                        ended_at = ?
                    WHERE id = ?
                    """,
                    (started_at, segment_end, int(segment["id"])),
                )

        roll_rows = connection.execute(
            "SELECT id, card_id, roll_number FROM roll_entries ORDER BY id"
        ).fetchall()
        active_shift_id = int(
            connection.execute(
                "SELECT id FROM shift_occurrences WHERE ended_at IS NULL"
            ).fetchone()["id"]
        )
        connection.commit()

    rolls = {
        f"{scenario}_{int(row['roll_number'])}": int(row["id"])
        for scenario, card_id in cards.items()
        for row in roll_rows
        if int(row["card_id"]) == card_id
    }
    return {
        "db_path": str(database_path),
        "active_shift_id": active_shift_id,
        "cards": cards,
        "rolls": rolls,
        "waiting_order": [
            cards["waiting_newest"],
            cards["waiting_older"],
            cards["waiting_zero"],
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the guarded rewinding-return browser fixture."
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
