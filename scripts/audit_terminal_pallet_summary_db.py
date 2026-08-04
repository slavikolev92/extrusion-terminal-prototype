from __future__ import annotations

import argparse
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
from app.pallet_summary import build_terminal_pallet_summary


def resolve_database_path(raw_path: str) -> Path:
    """Accept only an existing ordinary file below this checkout's test runtime."""
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
        raise ValueError("database must be under .test-runtime") from exc
    if not relative.parts:
        raise ValueError("database must be under .test-runtime")

    current = lexical_runtime
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError("database must not be a symlink")

    if not candidate.exists():
        raise ValueError("database must be an existing regular file")
    candidate_stat = candidate.stat()
    if not stat.S_ISREG(candidate_stat.st_mode):
        raise ValueError("database must be an existing regular file")
    if candidate_stat.st_nlink != 1:
        raise ValueError("database must not be hard-linked")

    resolved_runtime = runtime_path.resolve()
    resolved_database = candidate.resolve(strict=True)
    try:
        resolved_database.relative_to(resolved_runtime)
    except ValueError as exc:
        raise ValueError("database must be under .test-runtime") from exc
    return resolved_database


def empty_result(database_path: Path) -> dict[str, str | int]:
    return {
        "database": database_path.relative_to(ROOT_DIR).as_posix(),
        "integrity": "unreadable",
        "foreign_key_violations": 0,
        "visible_cards": 0,
        "ready": 0,
        "empty": 0,
        "error": 0,
    }


def audit_database(database_path: Path) -> tuple[dict[str, str | int], bool]:
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
        except sqlite3.Error:
            result["error"] = 1
            return result, False

        result["visible_cards"] = len(cards)
        rolls_by_card: dict[object, list[dict[str, object]]] = defaultdict(list)
        for roll in roll_rows:
            rolls_by_card[roll["card_id"]].append(dict(roll))

        for card in cards:
            try:
                card_id = card["id"]
                if type(card_id) is not int:
                    raise ValueError("invalid card id")
                summary = build_terminal_pallet_summary(
                    rolls_by_card[card_id]
                )
            except Exception:
                result["error"] = int(result["error"]) + 1
                continue
            state = summary.get("state")
            if state in ("ready", "empty"):
                result[state] = int(result[state]) + 1
            else:
                result["error"] = int(result["error"]) + 1
    finally:
        connection.close()

    return result, int(result["error"]) == 0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only terminal pallet-summary compatibility audit."
    )
    parser.add_argument("--db-path", required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        database_path = resolve_database_path(arguments.db_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    result, ok = audit_database(database_path)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
