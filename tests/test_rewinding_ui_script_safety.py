from __future__ import annotations

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
FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "create_rewinding_fixture.py"
VERIFIER_SCRIPT = REPO_ROOT / "scripts" / "verify_rewinding_ui.mjs"


def verifier_environment(**overrides: str) -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("BASE_URL", "FIXTURE_JSON", "ARTIFACT_DIR"):
        environment.pop(name, None)
    environment.update(overrides)
    return environment


def copy_script_repository(tmp_path: Path, script_path: Path) -> tuple[Path, Path]:
    copied_root = tmp_path / f"copied-{script_path.stem}"
    copied_scripts = copied_root / "scripts"
    copied_scripts.mkdir(parents=True)
    copied_script = copied_scripts / script_path.name
    shutil.copy2(script_path, copied_script)
    if script_path == FIXTURE_SCRIPT:
        (copied_root / "app").symlink_to(REPO_ROOT / "app", target_is_directory=True)
    return copied_root, copied_script


@contextmanager
def mismatched_health_server(database_path: Path):
    requests: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(("GET", self.path))
            payload = json.dumps(
                {"status": "ok", "database_path": str(database_path)}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            requests.append(("POST", self.path))
            self.send_response(204)
            self.end_headers()

        def log_message(self, format, *args):
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


@pytest.mark.parametrize(
    ("database_path", "output_path"),
    [
        ("data/extrusion_terminal.sqlite3", ".test-runtime/rewinding-safety/output.json"),
        ("{outside}/fixture.sqlite3", "{outside}/fixture.json"),
        (".test-runtime/rewinding-safety/fixture.sqlite3", "{outside}/fixture.json"),
    ],
)
def test_rewinding_fixture_rejects_runtime_and_external_paths(
    tmp_path: Path,
    database_path: str,
    output_path: str,
):
    database_path = database_path.format(outside=tmp_path)
    output_path = output_path.format(outside=tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(FIXTURE_SCRIPT),
            "--db-path",
            database_path,
            "--output",
            output_path,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "must be under .test-runtime" in result.stderr
    if Path(database_path).is_absolute():
        assert not Path(database_path).exists()
    if Path(output_path).is_absolute():
        assert not Path(output_path).exists()


def test_rewinding_fixture_rejects_symlinked_runtime_root_without_mutation(
    tmp_path: Path,
):
    copied_root, copied_script = copy_script_repository(tmp_path, FIXTURE_SCRIPT)
    runtime_data = copied_root / "data"
    runtime_data.mkdir()
    runtime_database = runtime_data / "extrusion_terminal.sqlite3"
    original_bytes = b"production sentinel must survive"
    runtime_database.write_bytes(original_bytes)
    (copied_root / ".test-runtime").symlink_to(runtime_data, target_is_directory=True)

    result = subprocess.run(
        [
            sys.executable,
            str(copied_script),
            "--db-path",
            ".test-runtime/extrusion_terminal.sqlite3",
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
    assert runtime_database.read_bytes() == original_bytes
    assert not (runtime_data / "fixture.json").exists()


def test_rewinding_fixture_emits_all_deterministic_scenarios(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"rewinding-safety-{tmp_path.name}"
    database_path = runtime_dir / "fixture.sqlite3"
    output_path = runtime_dir / "fixture.json"

    try:
        first = subprocess.run(
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
            check=False,
        )
        assert first.returncode == 0, first.stderr
        first_payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert Path(first_payload["db_path"]).resolve().is_relative_to(
            (REPO_ROOT / ".test-runtime").resolve()
        )
        assert set(first_payload["cards"]) == {
            "running_mixed",
            "paused_marked",
            "waiting_newest",
            "waiting_older",
            "waiting_zero",
            "completed_editable",
            "follow_up",
            "paused_follow_up",
        }
        assert len(set(first_payload["cards"].values())) == 8

        with sqlite3.connect(database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = {
                row["id"]: dict(row)
                for row in connection.execute(
                    """
                    SELECT id, status, machine_id, machine_sequence,
                           rewinding_roll_count, finished_at
                    FROM cards
                    ORDER BY id
                    """
                )
            }
            active_shift_count = connection.execute(
                "SELECT COUNT(*) FROM shift_occurrences WHERE ended_at IS NULL"
            ).fetchone()[0]
            running_pallets = connection.execute(
                "SELECT pallet_number FROM roll_entries WHERE card_id = ? ORDER BY roll_number",
                (first_payload["cards"]["running_mixed"],),
            ).fetchall()
            completed_rolls = connection.execute(
                """
                SELECT gross_weight, tare_weight, net_weight, pallet_number
                FROM roll_entries
                WHERE card_id = ?
                ORDER BY roll_number
                """,
                (first_payload["cards"]["completed_editable"],),
            ).fetchall()
            waiting_roll_counts = {
                name: connection.execute(
                    "SELECT COUNT(*) FROM roll_entries WHERE card_id = ?",
                    (first_payload["cards"][name],),
                ).fetchone()[0]
                for name in ("waiting_newest", "waiting_older", "waiting_zero")
            }
            open_timing_counts = {
                name: connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM production_time_segments
                    WHERE card_id = ? AND ended_at IS NULL
                    """,
                    (first_payload["cards"][name],),
                ).fetchone()[0]
                for name in ("running_mixed", "paused_marked")
            }

        cards = first_payload["cards"]
        assert rows[cards["running_mixed"]]["status"] == "running"
        assert rows[cards["paused_marked"]]["status"] == "paused"
        assert rows[cards["paused_marked"]]["rewinding_roll_count"] > 0
        assert rows[cards["waiting_newest"]]["status"] == "awaiting_rewinding"
        assert rows[cards["waiting_older"]]["status"] == "awaiting_rewinding"
        assert rows[cards["waiting_zero"]]["status"] == "awaiting_rewinding"
        assert rows[cards["completed_editable"]]["status"] == "completed"
        assert rows[cards["follow_up"]]["status"] == "pending"
        assert rows[cards["follow_up"]]["machine_id"] == 1
        assert rows[cards["paused_follow_up"]]["status"] == "pending"
        assert rows[cards["paused_follow_up"]]["machine_id"] == 2
        assert rows[cards["waiting_newest"]]["finished_at"] > rows[cards["waiting_older"]]["finished_at"]
        assert rows[cards["waiting_newest"]]["rewinding_roll_count"] != rows[cards["waiting_older"]]["rewinding_roll_count"]
        assert [row[0] for row in running_pallets] == [7, None]
        assert [tuple(row) for row in completed_rolls] == [
            (31.25, 1.25, 30.0, 15),
            (32.0, 1.25, 30.75, None),
        ]
        assert waiting_roll_counts == {
            "waiting_newest": 2,
            "waiting_older": 1,
            "waiting_zero": 0,
        }
        assert open_timing_counts == {
            "running_mixed": 1,
            "paused_marked": 0,
        }
        assert active_shift_count == 1

        second = subprocess.run(
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
            check=False,
        )
        assert second.returncode == 0, second.stderr
        second_payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert second_payload["cards"] == first_payload["cards"]
        assert second_payload["rolls"] == first_payload["rolls"]
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)


@pytest.mark.parametrize(
    ("missing_name", "provided"),
    [
        (
            "BASE_URL",
            {
                "FIXTURE_JSON": ".test-runtime/unused/fixture.json",
                "ARTIFACT_DIR": "artifacts/ui-checks/unused",
            },
        ),
        (
            "FIXTURE_JSON",
            {
                "BASE_URL": "http://127.0.0.1:9",
                "ARTIFACT_DIR": "artifacts/ui-checks/unused",
            },
        ),
        (
            "ARTIFACT_DIR",
            {
                "BASE_URL": "http://127.0.0.1:9",
                "FIXTURE_JSON": ".test-runtime/unused/fixture.json",
            },
        ),
    ],
)
def test_rewinding_verifier_requires_every_explicit_input_before_browser_use(
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


def test_rewinding_verifier_rejects_fixture_symlink_outside_guard(tmp_path: Path):
    outside_fixture = tmp_path / "fixture.json"
    outside_fixture.write_text("{}\n", encoding="utf-8")
    runtime_dir = REPO_ROOT / ".test-runtime" / f"rewinding-link-{tmp_path.name}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    fixture_link = runtime_dir / "fixture.json"
    fixture_link.symlink_to(outside_fixture)

    try:
        result = subprocess.run(
            ["node", str(VERIFIER_SCRIPT)],
            cwd=REPO_ROOT,
            env=verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                FIXTURE_JSON=str(fixture_link),
                ARTIFACT_DIR="artifacts/ui-checks/rewinding-link-safety",
            ),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    finally:
        fixture_link.unlink(missing_ok=True)
        runtime_dir.rmdir()

    assert result.returncode != 0
    assert "FIXTURE_JSON must resolve below .test-runtime." in result.stderr


def test_rewinding_verifier_rejects_symlinked_runtime_guard_root(tmp_path: Path):
    copied_root, copied_script = copy_script_repository(tmp_path, VERIFIER_SCRIPT)
    runtime_data = copied_root / "data"
    runtime_data.mkdir()
    database_path = runtime_data / "extrusion_terminal.sqlite3"
    original_bytes = b"runtime database sentinel"
    database_path.write_bytes(original_bytes)
    fixture_path = runtime_data / "fixture.json"
    fixture_path.write_text(
        json.dumps({"db_path": str(database_path)}) + "\n",
        encoding="utf-8",
    )
    (copied_root / ".test-runtime").symlink_to(runtime_data, target_is_directory=True)

    result = subprocess.run(
        ["node", str(copied_script)],
        cwd=copied_root,
        env=verifier_environment(
            BASE_URL="http://127.0.0.1:9",
            FIXTURE_JSON=".test-runtime/fixture.json",
            ARTIFACT_DIR="artifacts/ui-checks/run",
        ),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert ".test-runtime guard root must not be a symlink" in result.stderr
    assert database_path.read_bytes() == original_bytes


def test_rewinding_verifier_rejects_artifact_path_outside_guard(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"rewinding-artifact-{tmp_path.name}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = runtime_dir / "fixture.json"
    fixture_path.write_text("{}\n", encoding="utf-8")

    try:
        result = subprocess.run(
            ["node", str(VERIFIER_SCRIPT)],
            cwd=REPO_ROOT,
            env=verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                FIXTURE_JSON=str(fixture_path),
                ARTIFACT_DIR=str(tmp_path / "artifacts"),
            ),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "ARTIFACT_DIR must be below artifacts/ui-checks." in result.stderr
    assert not (tmp_path / "artifacts").exists()


def test_rewinding_verifier_rejects_artifact_symlink_outside_guard(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"rewinding-artifact-link-{tmp_path.name}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = runtime_dir / "fixture.json"
    fixture_path.write_text("{}\n", encoding="utf-8")
    outside_artifacts = tmp_path / "outside-artifacts"
    outside_artifacts.mkdir()
    artifact_link = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / f"rewinding-artifact-link-{tmp_path.name}"
    )
    artifact_link.parent.mkdir(parents=True, exist_ok=True)
    artifact_link.symlink_to(outside_artifacts, target_is_directory=True)

    try:
        result = subprocess.run(
            ["node", str(VERIFIER_SCRIPT)],
            cwd=REPO_ROOT,
            env=verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                FIXTURE_JSON=str(fixture_path),
                ARTIFACT_DIR=str(artifact_link),
            ),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    finally:
        artifact_link.unlink(missing_ok=True)
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "ARTIFACT_DIR guard path must not contain symlinks" in result.stderr


@pytest.mark.parametrize("symlinked_ancestor", ["artifacts", "ui-checks"])
def test_rewinding_verifier_rejects_symlinked_artifact_ancestors_before_writing(
    tmp_path: Path,
    symlinked_ancestor: str,
):
    copied_root, copied_script = copy_script_repository(tmp_path, VERIFIER_SCRIPT)
    runtime_root = copied_root / ".test-runtime"
    runtime_root.mkdir()
    database_path = runtime_root / "fixture.sqlite3"
    database_path.write_bytes(b"guarded fixture")
    (runtime_root / "fixture.json").write_text(
        json.dumps({"db_path": str(database_path)}) + "\n",
        encoding="utf-8",
    )
    outside_artifacts = tmp_path / f"outside-{symlinked_ancestor}"
    outside_artifacts.mkdir()
    if symlinked_ancestor == "artifacts":
        (copied_root / "artifacts").symlink_to(
            outside_artifacts,
            target_is_directory=True,
        )
    else:
        (copied_root / "artifacts").mkdir()
        (copied_root / "artifacts" / "ui-checks").symlink_to(
            outside_artifacts,
            target_is_directory=True,
        )

    result = subprocess.run(
        ["node", str(copied_script)],
        cwd=copied_root,
        env=verifier_environment(
            BASE_URL="http://127.0.0.1:9",
            FIXTURE_JSON=".test-runtime/fixture.json",
            ARTIFACT_DIR="artifacts/ui-checks/run",
        ),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode != 0
    assert "ARTIFACT_DIR guard path must not contain symlinks" in result.stderr
    assert list(outside_artifacts.iterdir()) == []


def test_rewinding_verifier_health_mismatch_prevents_mutation_requests_and_resets(
    tmp_path: Path,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"rewinding-preflight-{tmp_path.name}"
    artifact_dir = (
        REPO_ROOT / "artifacts" / "ui-checks" / f"rewinding-preflight-{tmp_path.name}"
    )
    runtime_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    original_database = b"guarded fixture must not be reset"
    database_path.write_bytes(original_database)
    fixture_path = runtime_dir / "fixture.json"
    original_fixture = (
        json.dumps({"db_path": str(database_path), "cards": {}, "rolls": {}}) + "\n"
    )
    fixture_path.write_text(original_fixture, encoding="utf-8")
    mismatched_database = tmp_path / "different.sqlite3"
    mismatched_database.write_bytes(b"different database")

    try:
        with mismatched_health_server(mismatched_database) as (base_url, requests):
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
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "server database identity" in result.stderr
    assert requests == [("GET", "/health")]
    assert observed_database == original_database
    assert observed_fixture == original_fixture


def test_rewinding_scripts_do_not_invoke_installers_during_real_execution(
    tmp_path: Path,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"rewinding-command-{tmp_path.name}"
    artifact_dir = (
        REPO_ROOT / "artifacts" / "ui-checks" / f"rewinding-command-{tmp_path.name}"
    )
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"
    wrapper = "#!/bin/sh\nprintf '%s\\n' \"$0 $*\" >> \"$COMMAND_LOG\"\nexit 97\n"
    for command in ("npm", "npx", "playwright"):
        target = fake_bin / command
        target.write_text(wrapper, encoding="utf-8")
        target.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
    environment["COMMAND_LOG"] = str(command_log)

    try:
        fixture_result = subprocess.run(
            [
                sys.executable,
                str(FIXTURE_SCRIPT),
                "--db-path",
                str(runtime_dir / "fixture.sqlite3"),
                "--output",
                str(runtime_dir / "fixture.json"),
            ],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert fixture_result.returncode == 0, fixture_result.stderr
        mismatch = tmp_path / "mismatch.sqlite3"
        mismatch.write_bytes(b"mismatch")
        verifier_environment_values = environment.copy()
        with mismatched_health_server(mismatch) as (base_url, _requests):
            verifier_environment_values.update(
                {
                    "BASE_URL": base_url,
                    "FIXTURE_JSON": str(runtime_dir / "fixture.json"),
                    "ARTIFACT_DIR": str(artifact_dir),
                }
            )
            verifier_result = subprocess.run(
                ["node", str(VERIFIER_SCRIPT)],
                cwd=REPO_ROOT,
                env=verifier_environment_values,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        assert verifier_result.returncode != 0
        assert "server database identity" in verifier_result.stderr
        assert not command_log.exists()
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)
