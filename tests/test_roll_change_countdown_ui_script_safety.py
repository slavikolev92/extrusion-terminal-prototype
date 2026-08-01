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
FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "create_roll_change_countdown_fixture.py"
VERIFIER_SCRIPT = REPO_ROOT / "scripts" / "verify_roll_change_countdown_ui.mjs"


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
def health_server(database_path: Path):
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
        ("data/extrusion_terminal.sqlite3", ".test-runtime/roll-change-safety/output.json"),
        ("{outside}/fixture.sqlite3", "{outside}/fixture.json"),
        (".test-runtime/roll-change-safety/fixture.sqlite3", "{outside}/fixture.json"),
    ],
)
def test_roll_change_fixture_rejects_runtime_and_external_paths(
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


def test_roll_change_fixture_rejects_symlinked_runtime_root_without_mutation(
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


def test_roll_change_fixture_emits_all_deterministic_scenarios(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"roll-change-safety-{tmp_path.name}"
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
            "machine_1_running",
            "machine_1_follow_up",
            "machine_2_running",
            "machine_3_running",
            "machine_4_paused",
            "completed",
            "machine_2_paused",
            "imported",
            "restored_started",
        }
        assert len(set(first_payload["cards"].values())) == 9

        with sqlite3.connect(database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = {
                row["id"]: dict(row)
                for row in connection.execute(
                    """
                    SELECT id, status, machine_id, machine_sequence,
                           tare_weight, first_started_at, version
                    FROM cards
                    ORDER BY id
                    """
                )
            }
            active_shift_count = connection.execute(
                "SELECT COUNT(*) FROM shift_occurrences WHERE ended_at IS NULL"
            ).fetchone()[0]
            open_timing_counts = {
                name: connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM production_time_segments
                    WHERE card_id = ? AND ended_at IS NULL
                    """,
                    (first_payload["cards"][name],),
                ).fetchone()[0]
                for name in (
                    "machine_1_running",
                    "machine_2_running",
                    "machine_3_running",
                    "machine_4_paused",
                    "completed",
                    "machine_2_paused",
                    "restored_started",
                )
            }
            running_rolls = connection.execute(
                """
                SELECT gross_weight, tare_weight, net_weight
                FROM roll_entries
                WHERE card_id = ?
                ORDER BY roll_number
                """,
                (first_payload["cards"]["machine_1_running"],),
            ).fetchall()

        cards = first_payload["cards"]
        assert rows[cards["machine_1_running"]]["status"] == "running"
        assert rows[cards["machine_1_running"]]["machine_sequence"] == 1
        assert rows[cards["machine_1_follow_up"]]["status"] == "pending"
        assert rows[cards["machine_1_follow_up"]]["machine_sequence"] == 2
        assert rows[cards["machine_2_running"]]["status"] == "running"
        assert rows[cards["machine_3_running"]]["status"] == "running"
        assert rows[cards["machine_4_paused"]]["status"] == "paused"
        assert rows[cards["machine_2_paused"]]["status"] == "paused"
        assert rows[cards["machine_2_paused"]]["machine_id"] == 2
        assert rows[cards["imported"]]["status"] == "imported"
        assert rows[cards["imported"]]["machine_id"] is None
        assert rows[cards["restored_started"]]["status"] == "pending"
        assert rows[cards["restored_started"]]["machine_id"] == 2
        assert rows[cards["restored_started"]]["first_started_at"] is not None
        assert rows[cards["completed"]]["status"] == "completed"
        assert rows[cards["completed"]]["machine_id"] == 3
        assert open_timing_counts == {
            "machine_1_running": 1,
            "machine_2_running": 1,
            "machine_3_running": 1,
            "machine_4_paused": 0,
            "completed": 0,
            "machine_2_paused": 0,
            "restored_started": 0,
        }
        assert [tuple(row) for row in running_rolls] == [(25.0, 1.0, 24.0)]
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
        assert second_payload == first_payload
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
def test_roll_change_verifier_requires_every_explicit_input_before_browser_use(
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


def test_roll_change_verifier_rejects_fixture_symlink_outside_guard(tmp_path: Path):
    outside_fixture = tmp_path / "fixture.json"
    outside_fixture.write_text("{}\n", encoding="utf-8")
    runtime_dir = REPO_ROOT / ".test-runtime" / f"roll-change-link-{tmp_path.name}"
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
                ARTIFACT_DIR="artifacts/ui-checks/roll-change-link-safety",
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


def test_roll_change_verifier_rejects_symlinked_runtime_guard_root(tmp_path: Path):
    copied_root, copied_script = copy_script_repository(tmp_path, VERIFIER_SCRIPT)
    runtime_data = copied_root / "data"
    runtime_data.mkdir()
    database_path = runtime_data / "extrusion_terminal.sqlite3"
    original_bytes = b"runtime database sentinel"
    database_path.write_bytes(original_bytes)
    (runtime_data / "fixture.json").write_text(
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


def test_roll_change_verifier_rejects_artifact_path_outside_guard(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"roll-change-artifact-{tmp_path.name}"
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


def test_roll_change_verifier_rejects_artifact_symlink_outside_guard(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"roll-change-artifact-link-{tmp_path.name}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = runtime_dir / "fixture.json"
    fixture_path.write_text("{}\n", encoding="utf-8")
    outside_artifacts = tmp_path / "outside-artifacts"
    outside_artifacts.mkdir()
    artifact_link = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / f"roll-change-artifact-link-{tmp_path.name}"
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
def test_roll_change_verifier_rejects_symlinked_artifact_ancestors_before_writing(
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


def test_roll_change_verifier_health_mismatch_prevents_requests_and_reset(
    tmp_path: Path,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"roll-change-preflight-{tmp_path.name}"
    artifact_dir = (
        REPO_ROOT / "artifacts" / "ui-checks" / f"roll-change-preflight-{tmp_path.name}"
    )
    runtime_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    original_database = b"guarded fixture must not be reset"
    database_path.write_bytes(original_database)
    fixture_path = runtime_dir / "fixture.json"
    original_fixture = (
        json.dumps({"db_path": str(database_path), "cards": {}}) + "\n"
    )
    fixture_path.write_text(original_fixture, encoding="utf-8")
    mismatched_database = tmp_path / "different.sqlite3"
    mismatched_database.write_bytes(b"different database")

    try:
        with health_server(mismatched_database) as (base_url, requests):
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


def test_roll_change_verifier_preflights_before_loading_browser_dependency(
    tmp_path: Path,
):
    copied_root, copied_script = copy_script_repository(tmp_path, VERIFIER_SCRIPT)
    runtime_dir = copied_root / ".test-runtime"
    runtime_dir.mkdir()
    database_path = runtime_dir / "fixture.sqlite3"
    database_path.write_bytes(b"guarded fixture")
    fixture_path = runtime_dir / "fixture.json"
    fixture_path.write_text(
        json.dumps({"db_path": str(database_path), "cards": {}}) + "\n",
        encoding="utf-8",
    )
    mismatched_database = tmp_path / "different.sqlite3"
    mismatched_database.write_bytes(b"different database")

    with health_server(mismatched_database) as (base_url, requests):
        result = subprocess.run(
            ["node", str(copied_script)],
            cwd=copied_root,
            env=verifier_environment(
                BASE_URL=base_url,
                FIXTURE_JSON=str(fixture_path),
                ARTIFACT_DIR="artifacts/ui-checks/run",
            ),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    assert result.returncode != 0
    assert "server database identity" in result.stderr
    assert requests == [("GET", "/health")]
    assert database_path.read_bytes() == b"guarded fixture"


def test_roll_change_verifier_resolves_repo_playwright_without_install_commands():
    source = VERIFIER_SCRIPT.read_text(encoding="utf-8")
    lowered = source.lower()

    assert 'createRequire(path.join(repoRoot, "package.json"))' in source
    assert 'require("@playwright/test")' in source
    for forbidden in (
        "playwright install",
        "npm install",
        "npm ci",
        "npx playwright",
        "download",
    ):
        assert forbidden not in lowered


def test_roll_change_verifier_uses_directional_spacing_and_accepted_geometry_checks():
    source = VERIFIER_SCRIPT.read_text(encoding="utf-8")

    assert "return start.left - rollChange.right;" in source
    assert "Math.abs(whitespace.shift.left - whitespace.queue.left) <= 1" in source
    assert "Math.abs(whitespace.shift.right - whitespace.queue.right) <= 1" in source
    assert "Math.abs(ledger.headerGutter - ledger.bodyGutter) <= 1" in source
    assert "Math.abs(headerCell.left - bodyCell.left) <= 1" in source
    assert "Math.abs(headerCell.right - bodyCell.right) <= 1" in source
    assert "const spread = Math.max(...centers) - Math.min(...centers);" in source
    assert 'initialErrorSlot.display === "none" && initialErrorSlot.height === 0' in source
    assert 'row.locator("[data-roll-edit-open]").click()' in source
    assert '[data-roll-row-cancel]' in source


def test_roll_change_verifier_covers_approved_indicator_thresholds_on_both_surfaces():
    source = VERIFIER_SCRIPT.read_text(encoding="utf-8")

    assert "async function assertThresholdTones(page, viewport)" in source
    assert 'tone: "normal"' in source
    assert 'tone: "warning"' in source
    assert 'tone: "urgent"' in source
    assert 'tone: "paused"' in source
    assert 'host.querySelector("[data-roll-change-machine-timer]")' in source
    assert 'page.locator("[data-roll-change-open]")' in source
    assert "await assertThresholdTones(page, viewport);" in source


def test_roll_change_verifier_covers_round4_and_round5_guarded_workflows_at_both_viewports():
    source = VERIFIER_SCRIPT.read_text(encoding="utf-8")

    assert '"correction-close-pending"' in source
    assert '"correction-close-reload-latched"' in source
    assert '"round4-modal-containment"' in source
    assert '"round4-admin-and-affordances"' in source
    assert '"round5-toast-modal-isolation"' in source
    assert '"round5-admin-new-timing-names"' in source
    assert "assertRound4AdminAndAffordances" in source
    assert "assertRound5ToastModalIsolation" in source
    assert "assertRound5AdminNewTimingNames" in source
    assert "beforeunload" in source
    assert "restored-started unrelease" in source
    assert "imported operational rejection" in source
    assert "occupied pending Start" in source
    assert "occupied paused Continue" in source
    assert "terminal roll accessible name" in source
    assert "admin timing accessible name" in source
    assert "toast accessibility-tree isolation" in source
    assert "Нов сегмент, начало" in source
    assert "Нов сегмент, край" in source
    assert "Нов сегмент, причина" in source


def test_due_selected_countdown_accessible_name_includes_expected_time():
    source = (REPO_ROOT / "app/static/js/roll_change_countdown.mjs").read_text(
        encoding="utf-8"
    )

    assert (
        "смяната е дължима; следваща ${view.nextExpectedLabel}" in source
    )


def test_roll_change_scripts_do_not_invoke_installers_during_real_execution(
    tmp_path: Path,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"roll-change-command-{tmp_path.name}"
    artifact_dir = (
        REPO_ROOT / "artifacts" / "ui-checks" / f"roll-change-command-{tmp_path.name}"
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
        with health_server(mismatch) as (base_url, _requests):
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
