from __future__ import annotations

import argparse
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from . import db

BACKUP_FILENAME_PREFIX = "extrusion_terminal_"
BACKUP_FILENAME_SUFFIX = ".sqlite3"
DEFAULT_BACKUP_DIR = Path(os.getenv("EXTRUSION_BACKUP_DIR", db.BASE_DIR / "backups"))
DEFAULT_BACKUP_KEEP_COUNT = int(os.getenv("EXTRUSION_BACKUP_KEEP_COUNT", "144"))


@dataclass(frozen=True)
class BackupResult:
    source_path: Path
    backup_path: Path
    retained_paths: tuple[Path, ...]
    removed_paths: tuple[Path, ...]


def create_backup(
    source_db_path: Path | str | None = None,
    backup_dir: Path | str | None = None,
    keep_count: int = DEFAULT_BACKUP_KEEP_COUNT,
    timestamp: datetime | None = None,
) -> BackupResult:
    source_path = Path(source_db_path) if source_db_path is not None else db.DB_PATH
    source_path = source_path.resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Source database does not exist: {source_path}")

    resolved_backup_dir = resolve_backup_dir(backup_dir)
    resolved_backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = next_backup_path(resolved_backup_dir, timestamp)

    backup_sqlite_database(source_path, backup_path)
    retained_paths, removed_paths = apply_retention(resolved_backup_dir, keep_count)
    return BackupResult(
        source_path=source_path,
        backup_path=backup_path,
        retained_paths=retained_paths,
        removed_paths=removed_paths,
    )


def restore_backup(
    backup_path: Path | str,
    target_db_path: Path | str,
) -> Path:
    source_path = Path(backup_path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Backup database does not exist: {source_path}")

    target_path = Path(target_db_path).resolve()
    if source_path == target_path:
        raise ValueError("Backup path and target database path must be different.")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_restore_path = target_path.with_name(
        f".{target_path.name}.restore-{uuid4().hex}.sqlite3"
    )
    try:
        backup_sqlite_database(source_path, temporary_restore_path)
        validate_sqlite_database(temporary_restore_path)
        os.replace(temporary_restore_path, target_path)
    finally:
        if temporary_restore_path.exists():
            temporary_restore_path.unlink()
    return target_path


def apply_retention(
    backup_dir: Path | str | None = None,
    keep_count: int = DEFAULT_BACKUP_KEEP_COUNT,
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    if keep_count < 1:
        raise ValueError("keep_count must be 1 or higher.")

    resolved_backup_dir = resolve_backup_dir(backup_dir)
    if not resolved_backup_dir.exists():
        return (), ()

    backup_files = [
        path
        for path in resolved_backup_dir.glob(f"{BACKUP_FILENAME_PREFIX}*{BACKUP_FILENAME_SUFFIX}")
        if path.is_file()
    ]
    backup_files.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)

    retained = tuple(backup_files[:keep_count])
    removed: list[Path] = []
    for backup_file in backup_files[keep_count:]:
        assert_path_inside_directory(backup_file, resolved_backup_dir)
        backup_file.unlink()
        removed.append(backup_file)

    return retained, tuple(removed)


def backup_sqlite_database(source_path: Path, target_path: Path) -> None:
    source_uri = source_path.as_uri() + "?mode=ro"
    target_connection: sqlite3.Connection | None = None
    source_connection: sqlite3.Connection | None = None
    try:
        source_connection = sqlite3.connect(source_uri, uri=True)
        target_connection = sqlite3.connect(target_path)
        source_connection.backup(target_connection)
    except Exception:
        if target_connection is not None:
            target_connection.close()
            target_connection = None
        if target_path.exists():
            target_path.unlink()
        raise
    finally:
        if target_connection is not None:
            target_connection.close()
        if source_connection is not None:
            source_connection.close()


def validate_sqlite_database(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        connection.close()
    if not result or result[0] != "ok":
        raise sqlite3.DatabaseError(f"SQLite integrity check failed for {database_path}")


def next_backup_path(
    backup_dir: Path,
    timestamp: datetime | None = None,
) -> Path:
    timestamp_text = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{BACKUP_FILENAME_PREFIX}{timestamp_text}{BACKUP_FILENAME_SUFFIX}"
    counter = 1
    while backup_path.exists():
        backup_path = backup_dir / (
            f"{BACKUP_FILENAME_PREFIX}{timestamp_text}_{counter:03d}{BACKUP_FILENAME_SUFFIX}"
        )
        counter += 1
    return backup_path


def resolve_backup_dir(backup_dir: Path | str | None = None) -> Path:
    return (Path(backup_dir) if backup_dir is not None else DEFAULT_BACKUP_DIR).resolve()


def assert_path_inside_directory(path: Path, directory: Path) -> None:
    resolved_path = path.resolve()
    resolved_directory = directory.resolve()
    if resolved_path.parent != resolved_directory:
        raise ValueError(f"Refusing to remove backup outside {resolved_directory}: {resolved_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SQLite-safe backup and restore utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Create a timestamped database backup.")
    backup_parser.add_argument("--source", type=Path, default=None, help="Source SQLite database path.")
    backup_parser.add_argument("--backup-dir", type=Path, default=None, help="Directory for backup files.")
    backup_parser.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_BACKUP_KEEP_COUNT,
        help="Number of newest backup files to keep.",
    )

    restore_parser = subparsers.add_parser("restore", help="Restore a backup into a target database path.")
    restore_parser.add_argument("--backup", type=Path, required=True, help="Backup SQLite file to restore.")
    restore_parser.add_argument("--target", type=Path, required=True, help="Target database path to replace.")

    prune_parser = subparsers.add_parser("prune", help="Apply backup retention without creating a backup.")
    prune_parser.add_argument("--backup-dir", type=Path, default=None, help="Directory containing backup files.")
    prune_parser.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_BACKUP_KEEP_COUNT,
        help="Number of newest backup files to keep.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "backup":
            result = create_backup(
                source_db_path=args.source,
                backup_dir=args.backup_dir,
                keep_count=args.keep,
            )
            print(f"Created backup: {result.backup_path}")
            if result.removed_paths:
                print(f"Removed old backups: {len(result.removed_paths)}")
            return 0

        if args.command == "restore":
            restored_path = restore_backup(args.backup, args.target)
            print(f"Restored backup to: {restored_path}")
            return 0

        if args.command == "prune":
            retained_paths, removed_paths = apply_retention(args.backup_dir, args.keep)
            print(f"Retained backups: {len(retained_paths)}")
            print(f"Removed old backups: {len(removed_paths)}")
            return 0
    except (FileNotFoundError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Error: {error}\n")

    parser.error("Unknown command.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
