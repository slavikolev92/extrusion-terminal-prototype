from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "create_terminal_pallet_summary_fixture.py"
VERIFIER_SCRIPT = REPO_ROOT / "scripts" / "verify_terminal_pallet_summary_ui.mjs"
AUDITOR_SCRIPT = REPO_ROOT / "scripts" / "audit_terminal_pallet_summary_db.py"
AUDIT_RESULT_KEYS = {
    "database",
    "integrity",
    "foreign_key_violations",
    "visible_cards",
    "ready",
    "empty",
    "error",
}
SCENARIOS = {
    "pending_empty",
    "running_mixed",
    "paused_all_unassigned",
    "awaiting_many_pallets",
    "completed_numbered",
}


def verifier_environment(**overrides: str) -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("BASE_URL", "FIXTURE_JSON", "ARTIFACT_DIR"):
        environment.pop(name, None)
    environment.update(overrides)
    return environment


def tree_snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def file_snapshot(path: Path) -> tuple[bytes, tuple[int, ...]]:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOATIME", 0))
    with os.fdopen(descriptor, "rb") as file:
        contents = file.read()
    metadata = path.stat()
    return contents, (
        metadata.st_mode,
        metadata.st_ino,
        metadata.st_dev,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_atime_ns,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def run_fixture(database_path: Path, output_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(FIXTURE_SCRIPT),
            "--db-path",
            str(database_path),
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def run_auditor(database_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AUDITOR_SCRIPT), "--db-path", str(database_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def create_audit_fixture(tmp_path: Path) -> tuple[Path, Path]:
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-audit-{tmp_path.name}"
    database_path = runtime_dir / "copied-safe-backup.sqlite3"
    result = run_fixture(database_path, runtime_dir / "fixture.json")
    assert result.returncode == 0, result.stderr
    return runtime_dir, database_path


def sqlite_side_file_snapshot(database_path: Path) -> dict[str, tuple[str, int] | None]:
    snapshot: dict[str, tuple[str, int] | None] = {}
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = Path(f"{database_path}{suffix}")
        if path.exists():
            snapshot[suffix] = (
                hashlib.sha256(path.read_bytes()).hexdigest(),
                path.stat().st_mtime_ns,
            )
        else:
            snapshot[suffix] = None
    return snapshot


def create_id_incompatible_audit_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE cards (id TEXT PRIMARY KEY, status TEXT NOT NULL);
            CREATE TABLE roll_entries (
                id INTEGER PRIMARY KEY,
                card_id TEXT NOT NULL,
                gross_weight NUMERIC,
                tare_weight NUMERIC,
                net_weight NUMERIC,
                pallet_number INTEGER
            );
            INSERT INTO cards (id, status) VALUES ('CARD-ID-SENTINEL', 'running');
            INSERT INTO roll_entries (
                card_id, gross_weight, tare_weight, net_weight, pallet_number
            ) VALUES ('CARD-ID-SENTINEL', 10, 1, 9, 1);
            """
        )


def test_audit_requires_an_explicit_database_path():
    result = subprocess.run(
        [sys.executable, str(AUDITOR_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "the following arguments are required: --db-path" in result.stderr


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "data/extrusion_terminal.sqlite3",
        "production-db/copied-safe-backup.sqlite3",
        "{outside}/copied-safe-backup.sqlite3",
    ],
)
def test_audit_rejects_protected_and_outside_database_paths(
    tmp_path: Path,
    unsafe_path: str,
):
    selected_path = Path(unsafe_path.format(outside=tmp_path))
    result = run_auditor(selected_path)

    assert result.returncode != 0
    assert "must be under .test-runtime" in result.stderr


def test_audit_rejects_missing_nonfile_and_symlink_inputs(tmp_path: Path):
    runtime_dir, database_path = create_audit_fixture(tmp_path)
    directory_path = runtime_dir / "not-a-database"
    directory_path.mkdir()
    symlink_path = runtime_dir / "linked-backup.sqlite3"
    symlink_path.symlink_to(database_path)

    try:
        missing = run_auditor(runtime_dir / "missing.sqlite3")
        directory = run_auditor(directory_path)
        symlink = run_auditor(symlink_path)
    finally:
        symlink_path.unlink(missing_ok=True)
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert missing.returncode != 0
    assert "must be an existing regular file" in missing.stderr
    assert directory.returncode != 0
    assert "must be an existing regular file" in directory.stderr
    assert symlink.returncode != 0
    assert "must not be a symlink" in symlink.stderr


def test_audit_reports_only_redacted_counts_and_never_mutates_backup(tmp_path: Path):
    runtime_dir, database_path = create_audit_fixture(tmp_path)
    before_hash = hashlib.sha256(database_path.read_bytes()).hexdigest()
    before_mtime_ns = database_path.stat().st_mtime_ns

    try:
        result = run_auditor(database_path)
        after_hash = hashlib.sha256(database_path.read_bytes()).hexdigest()
        after_mtime_ns = database_path.stat().st_mtime_ns
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload) == AUDIT_RESULT_KEYS
    assert payload == {
        "database": ".test-runtime/" + runtime_dir.name + "/copied-safe-backup.sqlite3",
        "integrity": "ok",
        "foreign_key_violations": 0,
        "visible_cards": 5,
        "ready": 4,
        "empty": 1,
        "error": 0,
    }
    assert after_hash == before_hash
    assert after_mtime_ns == before_mtime_ns
    assert result.stderr == ""


def test_audit_malformed_roll_data_fails_without_disclosing_saved_values(tmp_path: Path):
    runtime_dir, database_path = create_audit_fixture(tmp_path)
    secrets = {
        "order_number": "ORDER-DO-NOT-DISCLOSE",
        "customer": "CUSTOMER-DO-NOT-DISCLOSE",
        "material": "MATERIAL-DO-NOT-DISCLOSE",
        "notes": "NOTES-DO-NOT-DISCLOSE",
        "gross_weight": "9876.54",
        "tare_weight": "TARE-DO-NOT-DISCLOSE",
    }
    with sqlite3.connect(database_path) as connection:
        card_id = connection.execute(
            "SELECT id FROM cards WHERE status = 'running'"
        ).fetchone()[0]
        connection.execute(
            "UPDATE cards SET order_number = ?, customer = ?, material = ?, notes = ? "
            "WHERE id = ?",
            (
                secrets["order_number"],
                secrets["customer"],
                secrets["material"],
                secrets["notes"],
                card_id,
            ),
        )
        connection.execute(
            "UPDATE roll_entries SET gross_weight = ?, tare_weight = ? "
            "WHERE card_id = ? AND roll_number = 1",
            (secrets["gross_weight"], secrets["tare_weight"], card_id),
        )

    try:
        result = run_auditor(database_path)
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    payload = json.loads(result.stdout)
    emitted = result.stdout + result.stderr
    assert result.returncode != 0
    assert set(payload) == AUDIT_RESULT_KEYS
    assert payload["error"] == 1
    for secret in secrets.values():
        assert secret not in emitted
    assert "invalid tare_weight" not in emitted


def test_audit_integrity_and_foreign_key_failures_short_circuit_summaries(
    tmp_path: Path,
):
    runtime_dir, database_path = create_audit_fixture(tmp_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO roll_entries (card_id, order_number, roll_number, gross_weight, tare_weight, net_weight) "
            "VALUES (999999, 'FOREIGN-KEY-SECRET', 1, 'not-a-number', 1, 1)"
        )

    try:
        foreign_key_result = run_auditor(database_path)
        corrupted_path = runtime_dir / "corrupted-backup.sqlite3"
        corrupted_path.write_bytes(database_path.read_bytes()[:100])
        integrity_result = run_auditor(corrupted_path)
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    foreign_key_payload = json.loads(foreign_key_result.stdout)
    assert foreign_key_result.returncode != 0
    assert foreign_key_payload["integrity"] == "ok"
    assert foreign_key_payload["foreign_key_violations"] == 1
    assert foreign_key_payload["visible_cards"] == 0
    assert foreign_key_payload["error"] == 0
    assert "FOREIGN-KEY-SECRET" not in foreign_key_result.stdout + foreign_key_result.stderr

    integrity_payload = json.loads(integrity_result.stdout)
    assert integrity_result.returncode != 0
    assert integrity_payload["integrity"] != "ok"
    assert integrity_payload["visible_cards"] == 0
    assert integrity_payload["error"] == 0


def test_audit_id_incompatibility_is_a_redacted_json_failure(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-id-incompatible-{tmp_path.name}"
    database_path = runtime_dir / "copied-safe-backup.sqlite3"
    create_id_incompatible_audit_database(database_path)

    try:
        result = run_auditor(database_path)
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "CARD-ID-SENTINEL" not in result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert set(payload) == AUDIT_RESULT_KEYS
    assert payload["visible_cards"] == 1
    assert payload["ready"] == 0
    assert payload["empty"] == 0
    assert payload["error"] == 1


def test_audit_preserves_main_and_adjacent_wal_side_files(tmp_path: Path):
    runtime_dir, database_path = create_audit_fixture(tmp_path)
    writer = sqlite3.connect(database_path)
    try:
        assert writer.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
        writer.execute("UPDATE cards SET version = version + 1 WHERE id = 1")
        writer.commit()
        before = sqlite_side_file_snapshot(database_path)
        assert before[""] is not None
        assert before["-wal"] is not None
        assert before["-shm"] is not None
        assert before["-journal"] is None

        result = run_auditor(database_path)
        after = sqlite_side_file_snapshot(database_path)
    finally:
        writer.close()
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode == 0, result.stderr
    assert after == before


def test_audit_rejects_symlink_directory_component_without_touching_target(
    tmp_path: Path,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-component-link-{tmp_path.name}"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    target = outside_dir / "copied-safe-backup.sqlite3"
    target.write_bytes(b"outside sentinel")
    component_link = runtime_dir / "escaped-directory"
    runtime_dir.mkdir(parents=True)
    component_link.symlink_to(outside_dir, target_is_directory=True)
    before = hashlib.sha256(target.read_bytes()).hexdigest()

    try:
        result = run_auditor(component_link / target.name)
    finally:
        component_link.unlink(missing_ok=True)
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "must not be a symlink" in result.stderr
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before


def test_audit_rejects_resolved_dotdot_escape_without_touching_target(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-dotdot-{tmp_path.name}"
    runtime_dir.mkdir(parents=True)
    target = tmp_path / "outside-backup.sqlite3"
    target.write_bytes(b"outside sentinel")
    relative_escape = os.path.relpath(target, runtime_dir)
    raw_path = Path(".test-runtime") / runtime_dir.name / relative_escape
    before = hashlib.sha256(target.read_bytes()).hexdigest()

    try:
        result = run_auditor(raw_path)
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "must be under .test-runtime" in result.stderr
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before


def test_audit_rejects_hard_link_input_without_touching_outside_sentinel(
    tmp_path: Path,
):
    source_dir, source_database = create_audit_fixture(tmp_path)
    outside_sentinel = tmp_path / "outside-safe-backup.sqlite3"
    shutil.copy2(source_database, outside_sentinel)
    alias_dir = REPO_ROOT / ".test-runtime" / f"pallet-audit-hardlink-{tmp_path.name}"
    alias_dir.mkdir(parents=True)
    database_alias = alias_dir / "copied-safe-backup.sqlite3"
    os.link(outside_sentinel, database_alias)
    before = file_snapshot(outside_sentinel)

    try:
        result = run_auditor(database_alias)
        after = file_snapshot(outside_sentinel)
    finally:
        shutil.rmtree(source_dir, ignore_errors=True)
        shutil.rmtree(alias_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "must not be hard-linked" in result.stderr
    assert after == before


@contextmanager
def health_server(database_path: Path):
    requests: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
            requests.append(("GET", self.path))
            payload = json.dumps(
                {"status": "ok", "database_path": str(database_path)}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
            requests.append(("POST", self.path))
            self.send_response(204)
            self.end_headers()

        def log_message(self, format, *args):  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.parametrize("missing_option", ["--db-path", "--output"])
def test_fixture_requires_both_explicit_paths(missing_option: str):
    arguments = [sys.executable, str(FIXTURE_SCRIPT)]
    if missing_option != "--db-path":
        arguments.extend(["--db-path", ".test-runtime/pallet-summary/missing.sqlite3"])
    if missing_option != "--output":
        arguments.extend(["--output", ".test-runtime/pallet-summary/missing.json"])

    result = subprocess.run(
        arguments,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert f"the following arguments are required: {missing_option}" in result.stderr


@pytest.mark.parametrize(
    ("database_path", "output_path"),
    [
        ("data/extrusion_terminal.sqlite3", ".test-runtime/pallet-summary/out.json"),
        ("production-db/extrusion.sqlite3", ".test-runtime/pallet-summary/out.json"),
        ("{outside}/fixture.sqlite3", ".test-runtime/pallet-summary/out.json"),
        (".test-runtime/pallet-summary/fixture.sqlite3", "{outside}/out.json"),
    ],
)
def test_fixture_rejects_every_path_outside_test_runtime(
    tmp_path: Path,
    database_path: str,
    output_path: str,
):
    database_path = database_path.format(outside=tmp_path)
    output_path = output_path.format(outside=tmp_path)

    result = run_fixture(Path(database_path), Path(output_path))

    assert result.returncode != 0
    assert "must be under .test-runtime" in result.stderr
    if Path(database_path).is_absolute():
        assert not Path(database_path).exists()
    if Path(output_path).is_absolute():
        assert not Path(output_path).exists()


def test_fixture_rejects_symlink_escape_without_touching_target(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-summary-link-{tmp_path.name}"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    runtime_dir.parent.mkdir(parents=True, exist_ok=True)
    runtime_dir.symlink_to(outside_dir, target_is_directory=True)

    try:
        result = run_fixture(runtime_dir / "fixture.sqlite3", runtime_dir / "fixture.json")
    finally:
        runtime_dir.unlink(missing_ok=True)

    assert result.returncode != 0
    assert "must be under .test-runtime" in result.stderr
    assert list(outside_dir.iterdir()) == []


def test_fixture_rejects_symlinked_test_runtime_root_without_mutation(tmp_path: Path):
    copied_root = tmp_path / "copied-repo"
    copied_scripts = copied_root / "scripts"
    copied_scripts.mkdir(parents=True)
    copied_script = copied_scripts / FIXTURE_SCRIPT.name
    shutil.copy2(FIXTURE_SCRIPT, copied_script)
    (copied_root / "app").symlink_to(REPO_ROOT / "app", target_is_directory=True)
    outside_dir = tmp_path / "outside-runtime"
    outside_dir.mkdir()
    sentinel = outside_dir / "fixture.sqlite3"
    sentinel.write_bytes(b"must survive")
    (copied_root / ".test-runtime").symlink_to(outside_dir, target_is_directory=True)

    result = subprocess.run(
        [
            sys.executable,
            str(copied_script),
            "--db-path",
            ".test-runtime/fixture.sqlite3",
            "--output",
            ".test-runtime/fixture.json",
        ],
        cwd=copied_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert ".test-runtime guard root must not be a symlink" in result.stderr
    assert sentinel.read_bytes() == b"must survive"
    assert not (outside_dir / "fixture.json").exists()


def test_fixture_rejects_hard_link_database_without_touching_outside_sentinel(
    tmp_path: Path,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-db-hardlink-{tmp_path.name}"
    runtime_dir.mkdir(parents=True)
    outside_sentinel = tmp_path / "outside-database-sentinel.sqlite3"
    outside_sentinel.write_bytes(b"outside database sentinel")
    database_alias = runtime_dir / "fixture.sqlite3"
    os.link(outside_sentinel, database_alias)
    before = file_snapshot(outside_sentinel)

    try:
        result = run_fixture(database_alias, runtime_dir / "fixture.json")
        after = file_snapshot(outside_sentinel)
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "fixture DB path must not be hard-linked" in result.stderr
    assert after == before


def test_fixture_rejects_hard_link_json_output_without_touching_outside_sentinel(
    tmp_path: Path,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-json-hardlink-{tmp_path.name}"
    runtime_dir.mkdir(parents=True)
    outside_sentinel = tmp_path / "outside-json-sentinel.json"
    outside_sentinel.write_bytes(b"outside JSON sentinel\n")
    output_alias = runtime_dir / "fixture.json"
    os.link(outside_sentinel, output_alias)
    before = file_snapshot(outside_sentinel)

    try:
        result = run_fixture(runtime_dir / "fixture.sqlite3", output_alias)
        after = file_snapshot(outside_sentinel)
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "fixture output path must not be hard-linked" in result.stderr
    assert after == before


def test_fixture_recreates_exact_deterministic_scenarios_and_preserves_runtime_data(
    tmp_path: Path,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-summary-{tmp_path.name}"
    database_path = runtime_dir / "fixture.sqlite3"
    output_path = runtime_dir / "fixture.json"
    protected_before = {
        "data": tree_snapshot(REPO_ROOT / "data"),
        "production-db": tree_snapshot(REPO_ROOT / "production-db"),
    }

    try:
        first = run_fixture(database_path, output_path)
        assert first.returncode == 0, first.stderr
        first_payload = json.loads(output_path.read_text(encoding="utf-8"))

        assert Path(first_payload["db_path"]).resolve() == database_path.resolve()
        assert set(first_payload["scenarios"]) == SCENARIOS
        assert [first_payload["scenarios"][name]["order_number"] for name in (
            "pending_empty",
            "running_mixed",
            "paused_all_unassigned",
            "awaiting_many_pallets",
            "completed_numbered",
        )] == [
            "PALLET-UI-01",
            "PALLET-UI-02",
            "PALLET-UI-03",
            "PALLET-UI-04",
            "PALLET-UI-05",
        ]
        assert first_payload["scenarios"]["running_mixed"]["expected_rows"] == [
            ["2", "2", "200.1", "198.1"],
            ["10", "1", "120.0", "119.0"],
            ["Без палет", "1", "80.0", "79.0"],
        ]
        assert first_payload["scenarios"]["running_mixed"]["expected_total"] == [
            "Общо", "4", "400.1", "396.1"
        ]
        assert first_payload["scenarios"]["paused_all_unassigned"]["expected_rows"] == [
            ["Без палет", "2", "125.5", "123.5"]
        ]
        assert len(
            first_payload["scenarios"]["awaiting_many_pallets"]["expected_rows"]
        ) == 24
        assert first_payload["scenarios"]["completed_numbered"]["expected_rows"] == [
            ["3", "1", "60.0", "59.0"],
            ["12", "1", "40.5", "39.5"],
        ]
        assert first_payload["active_shift"]["shift_number"] == 1
        assert first_payload["active_shift"]["alternate_number"] == 2

        with sqlite3.connect(database_path) as connection:
            cards = {
                row[0]: row[1:]
                for row in connection.execute(
                    "SELECT order_number, status, machine_id, current_pallet_number "
                    "FROM cards ORDER BY order_number"
                )
            }
            running_rolls = connection.execute(
                "SELECT pallet_number, gross_weight, tare_weight, net_weight "
                "FROM roll_entries WHERE card_id = ? ORDER BY roll_number",
                (first_payload["scenarios"]["running_mixed"]["card_id"],),
            ).fetchall()
            counts = {
                "cards": connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0],
                "rolls": connection.execute("SELECT COUNT(*) FROM roll_entries").fetchone()[0],
                "timing_rows": connection.execute(
                    "SELECT COUNT(*) FROM production_time_segments"
                ).fetchone()[0],
                "pallet_assignments": connection.execute(
                    "SELECT COUNT(*) FROM roll_entries WHERE pallet_number IS NOT NULL"
                ).fetchone()[0],
            }
            shift_count = connection.execute(
                "SELECT shift_count FROM terminal_configuration WHERE id = 1"
            ).fetchone()[0]

        assert cards == {
            "PALLET-UI-01": ("pending", 1, None),
            "PALLET-UI-02": ("running", 1, 2),
            "PALLET-UI-03": ("paused", 2, None),
            "PALLET-UI-04": ("awaiting_rewinding", 3, 24),
            "PALLET-UI-05": ("completed", 4, 12),
        }
        assert running_rolls == [
            (10, 120, 1, 119),
            (None, 80, 1, 79),
            (2, 100, 1, 99),
            (2, 100.1, 1, 99.1),
        ]
        assert counts == {
            "cards": 5,
            "rolls": 32,
            "timing_rows": 4,
            "pallet_assignments": 29,
        }
        assert shift_count == 2
        assert first_payload["production_snapshot"]["counts"] == counts

        second = run_fixture(database_path, output_path)
        assert second.returncode == 0, second.stderr
        second_payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert second_payload == first_payload
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert tree_snapshot(REPO_ROOT / "data") == protected_before["data"]
    assert tree_snapshot(REPO_ROOT / "production-db") == protected_before["production-db"]


@pytest.mark.parametrize(
    ("missing_name", "provided"),
    [
        ("BASE_URL", {"FIXTURE_JSON": ".test-runtime/x/f.json", "ARTIFACT_DIR": "artifacts/ui-checks/x"}),
        ("FIXTURE_JSON", {"BASE_URL": "http://127.0.0.1:9", "ARTIFACT_DIR": "artifacts/ui-checks/x"}),
        ("ARTIFACT_DIR", {"BASE_URL": "http://127.0.0.1:9", "FIXTURE_JSON": ".test-runtime/x/f.json"}),
    ],
)
def test_verifier_requires_every_nonblank_input(
    missing_name: str,
    provided: dict[str, str],
):
    result = subprocess.run(
        ["node", str(VERIFIER_SCRIPT)],
        cwd=REPO_ROOT,
        env=verifier_environment(**provided),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert f"Required environment variable {missing_name} is missing." in result.stderr


def test_verifier_rejects_fixture_and_artifact_symlink_escapes(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-verifier-{tmp_path.name}"
    runtime_dir.mkdir(parents=True)
    outside_fixture = tmp_path / "fixture.json"
    outside_fixture.write_text("{}\n", encoding="utf-8")
    fixture_link = runtime_dir / "fixture.json"
    fixture_link.symlink_to(outside_fixture)
    outside_artifacts = tmp_path / "outside-artifacts"
    outside_artifacts.mkdir()
    artifact_link = REPO_ROOT / "artifacts" / "ui-checks" / f"pallet-link-{tmp_path.name}"
    artifact_link.parent.mkdir(parents=True, exist_ok=True)
    artifact_link.symlink_to(outside_artifacts, target_is_directory=True)

    try:
        fixture_result = subprocess.run(
            ["node", str(VERIFIER_SCRIPT)],
            cwd=REPO_ROOT,
            env=verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                FIXTURE_JSON=str(fixture_link),
                ARTIFACT_DIR="artifacts/ui-checks/safe-leaf",
            ),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        artifact_result = subprocess.run(
            ["node", str(VERIFIER_SCRIPT)],
            cwd=REPO_ROOT,
            env=verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                FIXTURE_JSON=str(runtime_dir / "missing.json"),
                ARTIFACT_DIR=str(artifact_link),
            ),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    finally:
        fixture_link.unlink(missing_ok=True)
        artifact_link.unlink(missing_ok=True)
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert fixture_result.returncode != 0
    assert "FIXTURE_JSON must resolve below .test-runtime." in fixture_result.stderr
    assert artifact_result.returncode != 0
    assert "ARTIFACT_DIR guard path must not contain symlinks" in artifact_result.stderr
    assert list(outside_artifacts.iterdir()) == []


@pytest.mark.parametrize("unsafe_input", ["fixture", "artifacts"])
def test_verifier_rejects_direct_paths_outside_guard(
    tmp_path: Path,
    unsafe_input: str,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-direct-{tmp_path.name}"
    runtime_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    database_path.write_bytes(b"fixture sentinel")
    fixture_path = runtime_dir / "fixture.json"
    fixture_path.write_text(
        json.dumps({"db_path": str(database_path)}) + "\n",
        encoding="utf-8",
    )
    selected_fixture = tmp_path / "outside.json" if unsafe_input == "fixture" else fixture_path
    if unsafe_input == "fixture":
        selected_fixture.write_text("{}\n", encoding="utf-8")
    selected_artifacts = (
        tmp_path / "outside-artifacts"
        if unsafe_input == "artifacts"
        else REPO_ROOT / "artifacts" / "ui-checks" / f"pallet-direct-{tmp_path.name}"
    )

    try:
        result = subprocess.run(
            ["node", str(VERIFIER_SCRIPT)],
            cwd=REPO_ROOT,
            env=verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                FIXTURE_JSON=str(selected_fixture),
                ARTIFACT_DIR=str(selected_artifacts),
            ),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        if unsafe_input != "artifacts":
            shutil.rmtree(selected_artifacts, ignore_errors=True)

    assert result.returncode != 0
    expected = (
        "FIXTURE_JSON must be under .test-runtime."
        if unsafe_input == "fixture"
        else "ARTIFACT_DIR must be below artifacts/ui-checks."
    )
    assert expected in result.stderr
    if unsafe_input == "artifacts":
        assert not selected_artifacts.exists()


def test_verifier_rejects_hard_link_fixture_without_touching_outside_sentinel(
    tmp_path: Path,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-fixture-hardlink-{tmp_path.name}"
    artifact_dir = REPO_ROOT / "artifacts" / "ui-checks" / f"pallet-fixture-hardlink-{tmp_path.name}"
    runtime_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    database_path.write_bytes(b"fixture database sentinel")
    outside_sentinel = tmp_path / "outside-fixture.json"
    outside_sentinel.write_text(
        json.dumps({"db_path": str(database_path), "scenarios": {}}) + "\n",
        encoding="utf-8",
    )
    fixture_alias = runtime_dir / "fixture.json"
    os.link(outside_sentinel, fixture_alias)
    before = file_snapshot(outside_sentinel)

    try:
        with health_server(database_path) as (base_url, requests):
            result = subprocess.run(
                ["node", str(VERIFIER_SCRIPT)],
                cwd=REPO_ROOT,
                env=verifier_environment(
                    BASE_URL=base_url,
                    FIXTURE_JSON=str(fixture_alias),
                    ARTIFACT_DIR=str(artifact_dir),
                    PLAYWRIGHT_BROWSERS_PATH=str(tmp_path / "missing-browsers"),
                ),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        after = file_snapshot(outside_sentinel)
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "FIXTURE_JSON must not be hard-linked" in result.stderr
    assert requests == []
    assert after == before


@pytest.mark.parametrize(
    "relative_artifact",
    [
        Path("verification-summary.json"),
        Path("desktop-1366") / "running-mixed-open.png",
    ],
)
def test_verifier_rejects_hard_link_artifact_without_touching_outside_sentinel(
    tmp_path: Path,
    relative_artifact: Path,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-artifact-hardlink-{tmp_path.name}"
    artifact_dir = REPO_ROOT / "artifacts" / "ui-checks" / f"pallet-artifact-hardlink-{tmp_path.name}"
    runtime_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    database_path.write_bytes(b"fixture database sentinel")
    fixture_path = runtime_dir / "fixture.json"
    fixture_path.write_text(
        json.dumps({"db_path": str(database_path), "scenarios": {}}) + "\n",
        encoding="utf-8",
    )
    outside_sentinel = tmp_path / f"outside-{relative_artifact.name}"
    outside_sentinel.write_bytes(b"outside artifact sentinel\n")
    artifact_alias = artifact_dir / relative_artifact
    artifact_alias.parent.mkdir(parents=True)
    os.link(outside_sentinel, artifact_alias)
    before = file_snapshot(outside_sentinel)

    try:
        with health_server(database_path) as (base_url, requests):
            result = subprocess.run(
                ["node", str(VERIFIER_SCRIPT)],
                cwd=REPO_ROOT,
                env=verifier_environment(
                    BASE_URL=base_url,
                    FIXTURE_JSON=str(fixture_path),
                    ARTIFACT_DIR=str(artifact_dir),
                    PLAYWRIGHT_BROWSERS_PATH=str(tmp_path / "missing-browsers"),
                ),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        after = file_snapshot(outside_sentinel)
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "Existing artifact target must not be hard-linked" in result.stderr
    assert requests == [("GET", "/health")]
    assert after == before


def test_verifier_health_mismatch_is_the_only_request_and_preserves_fixture(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"pallet-preflight-{tmp_path.name}"
    artifact_dir = REPO_ROOT / "artifacts" / "ui-checks" / f"pallet-preflight-{tmp_path.name}"
    database_path = runtime_dir / "fixture.sqlite3"
    fixture_path = runtime_dir / "fixture.json"
    runtime_dir.mkdir(parents=True)
    database_path.write_bytes(b"fixture sentinel")
    fixture_text = json.dumps({"db_path": str(database_path), "scenarios": {}}) + "\n"
    fixture_path.write_text(fixture_text, encoding="utf-8")
    mismatch_path = tmp_path / "other.sqlite3"
    mismatch_path.write_bytes(b"different")

    try:
        with health_server(mismatch_path) as (base_url, requests):
            result = subprocess.run(
                ["node", str(VERIFIER_SCRIPT)],
                cwd=REPO_ROOT,
                env=verifier_environment(
                    BASE_URL=base_url,
                    FIXTURE_JSON=str(fixture_path),
                    ARTIFACT_DIR=str(artifact_dir),
                ),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        observed_database = database_path.read_bytes()
        observed_fixture = fixture_path.read_text(encoding="utf-8")
        artifact_directory_was_created = artifact_dir.exists()
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "server database identity" in result.stderr
    assert requests == [("GET", "/health")]
    assert observed_database == b"fixture sentinel"
    assert observed_fixture == fixture_text
    assert not artifact_directory_was_created


def test_verifier_has_complete_guarded_browser_contract_and_valid_node_syntax():
    syntax = subprocess.run(
        ["node", "--check", str(VERIFIER_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    source = VERIFIER_SCRIPT.read_text(encoding="utf-8")
    required_contract_markers = (
        'createRequire(import.meta.url)',
        'require("@playwright/test")',
        '{ name: "desktop-1366", width: 1366, height: 768 }',
        '{ name: "desktop-1920", width: 1920, height: 1080 }',
        '"Пренавиване"',
        '"Палети"',
        '"Обобщение по палети"',
        '"Палет"',
        '"Брой ролки"',
        '"Бруто, кг"',
        '"Нето, кг"',
        '"Няма въведени ролки."',
        '"Обобщението по палети не може да бъде показано. Проверете данните за ролките."',
        'data-pallet-summary-open',
        'data-pallet-summary-overlay',
        'data-pallet-summary-dialog',
        'data-pallet-summary-close',
        'data-pallet-summary-scroll',
        'terminal-refresh-alert-button',
        'data-shift-reload',
        'fetch_active_shift()',
        'update_active_shift_number(',
        'scrollHeight > clientHeight',
        'running-mixed-open.png',
        'pending-empty-open.png',
        'awaiting-many-scrolled.png',
        'verification-summary.json',
    )
    for marker in required_contract_markers:
        assert marker in source

    assert "npm install" not in source
    assert "npx" not in source
    assert "window.setInterval" not in source
    assert source.index('`${baseURL}/health`') < source.index('require("@playwright/test")')


def test_verifier_modal_network_contract_requires_base_url_origin_and_summary_evidence():
    """An external /terminal/snapshot request must not satisfy modal-only checks."""
    source = VERIFIER_SCRIPT.read_text(encoding="utf-8")

    assert "const baseOrigin = new URL(baseURL).origin;" in source
    assert "requestURL.origin, baseOrigin" in source
    assert 'request.method, "GET"' in source
    assert "allowedOrigin: baseOrigin" in source
    assert "observedOrigins" in source
