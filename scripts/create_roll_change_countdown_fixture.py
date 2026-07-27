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
    "machine_1_running",
    "machine_1_follow_up",
    "machine_2_running",
    "machine_3_running",
    "machine_4_paused",
    "completed",
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
        "order_date": "27.07.2026",
        "delivery_date": "31.07.2026",
        "customer": customer,
        "city": "София",
        "product_type": "Фолио за проверка на брояч",
        "ordered_gross_kg": "500",
        "ordered_rolls": "20",
        "ordered_meters": "12000",
        "ordered_units": "24000",
        "product_form": "Ръкав",
        "material": "LDPE",
        "size_thickness": "600 / 0.050",
        "notes": "Временна карта само за проверка на смяната на ролките.",
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
                    f"ROLL-CHANGE-UI-{index:02d}",
                    f"Клиент {index} за брояч на ролки",
                ).get(field, "")
                for field in IMPORT_FIELDS
            }
        )
    result = import_cards_from_csv(
        "roll-change-countdown-ui-fixture.csv",
        buffer.getvalue().encode("utf-8"),
        overwrite_existing=False,
    )
    if result.rows_imported != len(SCENARIOS):
        raise RuntimeError(f"Fixture import failed: {result.messages}")

    with db.connect() as connection:
        ids = [
            int(row["id"])
            for row in connection.execute("SELECT id FROM cards ORDER BY id").fetchall()
        ]
    if len(ids) != len(SCENARIOS):
        raise RuntimeError("Fixture import did not create exactly six cards.")
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

    release(cards["completed"], 3, 1)
    start(cards["completed"])
    set_defaults(cards["completed"], tare="1.0")
    add_roll(cards["completed"], "20.0")
    finish(cards["completed"])

    release(cards["machine_1_running"], 1, 1)
    release(cards["machine_1_follow_up"], 1, 2)
    release(cards["machine_2_running"], 2, 1)
    release(cards["machine_3_running"], 3, 1)
    release(cards["machine_4_paused"], 4, 1)

    for scenario in (
        "machine_1_running",
        "machine_2_running",
        "machine_3_running",
        "machine_4_paused",
    ):
        start(cards[scenario])
    set_defaults(cards["machine_1_running"], tare="1.0")
    add_roll(cards["machine_1_running"], "25.0")
    pause(cards["machine_4_paused"])

    active_shift_id = int(db.fetch_active_shift()["id"])
    return {
        "db_path": str(database_path),
        "active_shift_id": active_shift_id,
        "cards": cards,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the guarded roll-change-countdown browser fixture."
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
