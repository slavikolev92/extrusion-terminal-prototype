from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import stat
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.constants import TERMINAL_VISIBLE_STATUSES
from app.pallet_summary import build_pallet_summary


def resolve_guarded_input(raw_path: str, *, label: str) -> Path:
    """Accept only an existing ordinary single-link file below test runtime."""
    runtime_path = ROOT_DIR / ".test-runtime"
    if runtime_path.is_symlink():
        raise ValueError(".test-runtime guard root must not be a symlink")

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    lexical_candidate = candidate.absolute()
    lexical_runtime = runtime_path.absolute()
    try:
        relative = lexical_candidate.relative_to(lexical_runtime)
    except ValueError as exc:
        raise ValueError(f"{label} must be under .test-runtime") from exc
    if not relative.parts:
        raise ValueError(f"{label} must be under .test-runtime")

    current = lexical_runtime
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"{label} must not be a symlink")

    if not candidate.exists():
        raise ValueError(f"{label} must be an existing regular file")
    candidate_stat = candidate.stat()
    if not stat.S_ISREG(candidate_stat.st_mode):
        raise ValueError(f"{label} must be an existing regular file")
    if candidate_stat.st_nlink != 1:
        raise ValueError(f"{label} must not be hard-linked")

    resolved_runtime = runtime_path.resolve()
    resolved_database = candidate.resolve(strict=True)
    try:
        resolved_database.relative_to(resolved_runtime)
    except ValueError as exc:
        raise ValueError(f"{label} must be under .test-runtime") from exc
    return resolved_database


def resolve_database_path(raw_path: str) -> Path:
    return resolve_guarded_input(raw_path, label="database")


def empty_result(database_path: Path) -> dict[str, object]:
    return {
        "database": database_path.relative_to(ROOT_DIR).as_posix(),
        "integrity": "unreadable",
        "foreign_key_violations": 0,
        "visible_cards": 0,
        "ready": 0,
        "empty": 0,
        "error": 0,
        "weight_none": 0,
        "weight_partial": 0,
        "weight_complete": 0,
        "mutation_audit": "not_requested",
        "audited_fields": 0,
        "expected_saves": 0,
        "unexpected_mutations": 0,
        "hash_algorithm": "sha256",
        "pre_hashes": {},
        "post_hashes": {},
    }


def parse_expected_saves(raw_values: list[str]) -> list[tuple[int, int, int | None]]:
    parsed: list[tuple[int, int, int | None]] = []
    for raw in raw_values:
        parts = raw.split(":")
        if len(parts) != 3:
            raise ValueError("expected save must use CARD:PALLET:HUNDREDTHS_OR_CLEAR")
        try:
            card_id = int(parts[0])
            pallet_number = int(parts[1])
            weight_hundredths = None if parts[2] == "clear" else int(parts[2])
        except ValueError as exc:
            raise ValueError(
                "expected save must use CARD:PALLET:HUNDREDTHS_OR_CLEAR"
            ) from exc
        if card_id <= 0 or not 1 <= pallet_number <= 999:
            raise ValueError("expected save identifiers are outside their allowed range")
        if weight_hundredths is not None and not 1 <= weight_hundredths <= 10000:
            raise ValueError("expected save weight is outside 1..10000 hundredths")
        parsed.append((card_id, pallet_number, weight_hundredths))
    return parsed


def current_table_rows(
    connection: sqlite3.Connection,
    table: str,
    columns: list[str],
) -> list[list[object]]:
    quoted = ", ".join(f'"{column}"' for column in columns)
    info = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    primary = [
        (int(row["pk"]), str(row["name"]))
        for row in info
        if int(row["pk"]) > 0
    ]
    order_columns = [name for _, name in sorted(primary)] or columns
    order_sql = ", ".join(f'"{column}"' for column in order_columns)
    return [
        list(row)
        for row in connection.execute(
            f'SELECT {quoted} FROM "{table}" ORDER BY {order_sql}'
        ).fetchall()
    ]


def hash_rows(rows: list[list[object]]) -> dict[str, object]:
    serialized = [
        json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        for row in rows
    ]
    return {
        "row_hashes": [
            hashlib.sha256(row.encode("utf-8")).hexdigest()
            for row in serialized
        ],
        "table_hash": hashlib.sha256(
            "\n".join(serialized).encode("utf-8")
        ).hexdigest(),
    }


def audit_expected_mutations(
    connection: sqlite3.Connection,
    baseline: dict[str, object],
    expected_saves: list[tuple[int, int, int | None]],
) -> tuple[int, int, dict[str, object], dict[str, object]]:
    unexpected = 0
    audited_fields = 0
    pre_hashes: dict[str, object] = {}
    post_hashes: dict[str, object] = {}
    expected_by_card: dict[int, int] = defaultdict(int)
    targeted_weights: dict[tuple[int, int], int | None] = {}
    for card_id, pallet_number, weight_hundredths in expected_saves:
        expected_by_card[card_id] += 1
        targeted_weights[(card_id, pallet_number)] = weight_hundredths

    tables = baseline.get("tables")
    if not isinstance(tables, dict):
        return 1, 0, pre_hashes, post_hashes
    for table in sorted(tables):
        raw_snapshot = tables[table]
        if not isinstance(table, str) or not isinstance(raw_snapshot, dict):
            unexpected += 1
            continue
        columns = raw_snapshot.get("columns")
        before_rows = raw_snapshot.get("rows")
        if not isinstance(columns, list) or not isinstance(before_rows, list):
            unexpected += 1
            continue
        try:
            after_rows = current_table_rows(connection, table, columns)
        except sqlite3.Error:
            unexpected += 1
            continue
        pre_hashes[table] = hash_rows(before_rows)
        post_hashes[table] = hash_rows(after_rows)
        if (
            raw_snapshot.get("row_hashes") != pre_hashes[table]["row_hashes"]
            or raw_snapshot.get("table_hash") != pre_hashes[table]["table_hash"]
        ):
            unexpected += 1
        audited_fields += sum(len(row) for row in before_rows)
        if table != "cards":
            if after_rows != before_rows:
                unexpected += 1
            continue

        if not columns or columns[0] != "id":
            unexpected += 1
            continue
        before_by_id = {int(row[0]): row for row in before_rows}
        after_by_id = {int(row[0]): row for row in after_rows}
        if set(before_by_id) != set(after_by_id):
            unexpected += 1
            continue
        version_index = columns.index("version")
        updated_index = columns.index("updated_at")
        for card_id, before in before_by_id.items():
            after = after_by_id[card_id]
            increment = expected_by_card.get(card_id, 0)
            for index, (old_value, new_value) in enumerate(zip(before, after, strict=True)):
                if index == version_index:
                    if new_value != old_value + increment:
                        unexpected += 1
                elif index == updated_index and increment:
                    if not isinstance(new_value, str) or not new_value or new_value == old_value:
                        unexpected += 1
                elif new_value != old_value:
                    unexpected += 1

    weight_columns = baseline.get("pallet_weight_columns")
    weight_rows = baseline.get("pallet_weight_rows")
    if not isinstance(weight_columns, list) or not isinstance(weight_rows, list):
        return unexpected + 1, audited_fields, pre_hashes, post_hashes
    after_weights = current_table_rows(
        connection,
        "card_pallet_weights",
        weight_columns,
    )
    pre_hashes["card_pallet_weights"] = hash_rows(weight_rows)
    post_hashes["card_pallet_weights"] = hash_rows(after_weights)
    audited_fields += sum(len(row) for row in weight_rows)
    before_by_key = {(int(row[0]), int(row[1])): row for row in weight_rows}
    after_by_key = {(int(row[0]), int(row[1])): row for row in after_weights}
    expected_values = {key: int(row[2]) for key, row in before_by_key.items()}
    for key, value in targeted_weights.items():
        if value is None:
            expected_values.pop(key, None)
        else:
            expected_values[key] = value
    if set(after_by_key) != set(expected_values):
        unexpected += 1
    for key, expected_weight in expected_values.items():
        row = after_by_key.get(key)
        if row is None:
            continue
        if int(row[2]) != expected_weight:
            unexpected += 1
        before = before_by_key.get(key)
        if key not in targeted_weights:
            if before != row:
                unexpected += 1
        elif before is not None and row[3] != before[3]:
            unexpected += 1
        if not isinstance(row[3], str) or not row[3]:
            unexpected += 1
        if not isinstance(row[4], str) or not row[4]:
            unexpected += 1
    return unexpected, audited_fields, pre_hashes, post_hashes


def audit_database(
    database_path: Path,
    *,
    fixture: dict[str, object] | None = None,
    expected_saves: list[tuple[int, int, int | None]] | None = None,
) -> tuple[dict[str, object], bool]:
    result = empty_result(database_path)
    database_uri = f"file:{quote(str(database_path))}?mode=ro&immutable=1"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(database_uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
    except sqlite3.Error:
        if connection is not None:
            connection.close()
        return result, False

    try:
        try:
            integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
        except sqlite3.Error:
            return result, False
        if len(integrity_rows) == 1 and integrity_rows[0][0] == "ok":
            result["integrity"] = "ok"
        else:
            result["integrity"] = "failed"
            return result, False

        try:
            foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        except sqlite3.Error:
            result["integrity"] = "failed"
            return result, False
        result["foreign_key_violations"] = len(foreign_key_rows)
        if foreign_key_rows:
            return result, False

        status_placeholders = ", ".join("?" for _ in TERMINAL_VISIBLE_STATUSES)
        try:
            cards = connection.execute(
                "SELECT id, status FROM cards "
                f"WHERE status IN ({status_placeholders}) ORDER BY id",
                TERMINAL_VISIBLE_STATUSES,
            ).fetchall()
            roll_rows = connection.execute(
                "SELECT card_id, gross_weight, tare_weight, net_weight, pallet_number "
                "FROM roll_entries "
                f"WHERE card_id IN ({', '.join('?' for _ in cards)}) "
                "ORDER BY card_id, id",
                tuple(row["id"] for row in cards),
            ).fetchall() if cards else []
            weight_rows = connection.execute(
                "SELECT card_id, pallet_number, weight_hundredths "
                "FROM card_pallet_weights "
                f"WHERE card_id IN ({', '.join('?' for _ in cards)}) "
                "ORDER BY card_id, pallet_number",
                tuple(row["id"] for row in cards),
            ).fetchall() if cards else []
        except sqlite3.Error:
            result["error"] = 1
            return result, False

        result["visible_cards"] = len(cards)
        rolls_by_card: dict[object, list[dict[str, object]]] = defaultdict(list)
        weights_by_card: dict[object, dict[int, int]] = defaultdict(dict)
        for roll in roll_rows:
            rolls_by_card[roll["card_id"]].append(dict(roll))
        for weight in weight_rows:
            weights_by_card[weight["card_id"]][int(weight["pallet_number"])] = int(
                weight["weight_hundredths"]
            )

        for card in cards:
            try:
                card_id = card["id"]
                if type(card_id) is not int:
                    raise ValueError("invalid card id")
                summary = build_pallet_summary(
                    rolls_by_card[card_id],
                    weights_by_card[card_id],
                )
            except Exception:
                result["error"] = int(result["error"]) + 1
                continue
            state = summary.get("state")
            if state in ("ready", "empty"):
                result[state] = int(result[state]) + 1
            else:
                result["error"] = int(result["error"]) + 1
            weight_state = summary.get("weight_state")
            weight_key = f"weight_{weight_state}"
            if weight_key in result:
                result[weight_key] = int(result[weight_key]) + 1
            else:
                result["error"] = int(result["error"]) + 1

        if fixture is not None:
            result["mutation_audit"] = "failed"
            saves = expected_saves or []
            result["expected_saves"] = len(saves)
            unexpected, audited_fields, pre_hashes, post_hashes = audit_expected_mutations(
                connection,
                fixture.get("audit_baseline", {}),
                saves,
            )
            result["unexpected_mutations"] = unexpected
            result["audited_fields"] = audited_fields
            result["pre_hashes"] = pre_hashes
            result["post_hashes"] = post_hashes
            if unexpected == 0:
                result["mutation_audit"] = "passed"
    finally:
        connection.close()

    audit_ok = result["mutation_audit"] in {"not_requested", "passed"}
    return result, int(result["error"]) == 0 and audit_ok


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only terminal pallet-summary compatibility audit."
    )
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--fixture-json")
    parser.add_argument("--expect-save", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        database_path = resolve_database_path(arguments.db_path)
        fixture_path = (
            resolve_guarded_input(arguments.fixture_json, label="fixture JSON")
            if arguments.fixture_json
            else None
        )
        if arguments.expect_save and fixture_path is None:
            raise ValueError("--expect-save requires --fixture-json")
        expected_saves = parse_expected_saves(arguments.expect_save)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    fixture = None
    if fixture_path is not None:
        try:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            print("fixture JSON must contain valid JSON", file=sys.stderr)
            return 2
        if not isinstance(fixture, dict):
            print("fixture JSON must contain a JSON object", file=sys.stderr)
            return 2

    result, ok = audit_database(
        database_path,
        fixture=fixture,
        expected_saves=expected_saves,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
