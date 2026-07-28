from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "create_roll_pallet_fixture.py"
VERIFIER_SCRIPT = REPO_ROOT / "scripts" / "verify_roll_pallet_ui.mjs"


def verifier_environment(**overrides: str) -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("BASE_URL", "FIXTURE_JSON", "ARTIFACT_DIR"):
        environment.pop(name, None)
    environment.update(overrides)
    return environment


def unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@contextmanager
def temporary_server(database_path: Path):
    port = unused_local_port()
    environment = os.environ.copy()
    environment.update(
        EXTRUSION_DATA_DIR=str(database_path.parent),
        EXTRUSION_DB_PATH=str(database_path),
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=REPO_ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"{base_url}/health", timeout=0.5
                ) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.05)
        else:
            pytest.fail("temporary roll/pallet server did not start")
        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def create_roll_pallet_fixture(database_path: Path, fixture_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(FIXTURE_SCRIPT),
            "--db-path",
            str(database_path),
            "--output",
            str(fixture_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_roll_pallet_fixture_rejects_database_path_outside_test_runtime(tmp_path):
    unsafe_database = tmp_path / "unsafe.sqlite3"
    unsafe_output = tmp_path / "fixture.json"

    result = subprocess.run(
        [
            sys.executable,
            str(FIXTURE_SCRIPT),
            "--db-path",
            str(unsafe_database),
            "--output",
            str(unsafe_output),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "must be under .test-runtime" in result.stderr
    assert not unsafe_database.exists()
    assert not unsafe_output.exists()


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
def test_roll_pallet_verifier_requires_every_explicit_input_before_browser_use(
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


def test_roll_pallet_verifier_rejects_summary_leaf_symlink_and_preserves_sentinel(
    tmp_path: Path,
):
    case_root = (
        REPO_ROOT
        / ".test-runtime"
        / "release-candidate-audit"
        / "final-verifier-fix-round-1"
        / f"roll-summary-leaf-{tmp_path.name}"
    )
    runtime_dir = case_root / "runtime"
    database_path = runtime_dir / "fixture.sqlite3"
    fixture_path = runtime_dir / "fixture.json"
    sentinel_path = case_root / "outside-summary-sentinel.json"
    artifact_dir = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / "release-candidate-audit"
        / "final-verifier-fix-round-1"
        / f"roll-summary-leaf-{tmp_path.name}"
    )
    sentinel = "sentinel: must remain unchanged\n"

    try:
        create_roll_pallet_fixture(database_path, fixture_path)
        artifact_dir.mkdir(parents=True)
        sentinel_path.write_text(sentinel, encoding="utf-8")
        (artifact_dir / "verification-summary.json").symlink_to(sentinel_path)

        result = subprocess.run(
            ["node", str(VERIFIER_SCRIPT)],
            cwd=REPO_ROOT,
            env=verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                FIXTURE_JSON=str(fixture_path),
                ARTIFACT_DIR=str(artifact_dir),
            ),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        sentinel_after = sentinel_path.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(case_root, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert sentinel_after == sentinel
    assert "Evidence output path must not be a symlink" in result.stderr


def test_roll_pallet_verifier_rejects_non_regular_screenshot_leaf_before_health(
    tmp_path: Path,
):
    case_root = (
        REPO_ROOT
        / ".test-runtime"
        / "release-candidate-audit"
        / "final-verifier-fix-round-1"
        / f"roll-screenshot-leaf-{tmp_path.name}"
    )
    runtime_dir = case_root / "runtime"
    database_path = runtime_dir / "fixture.sqlite3"
    fixture_path = runtime_dir / "fixture.json"
    artifact_dir = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / "release-candidate-audit"
        / "final-verifier-fix-round-1"
        / f"roll-screenshot-leaf-{tmp_path.name}"
    )

    try:
        create_roll_pallet_fixture(database_path, fixture_path)
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "terminal-pallet-entry-1536x1024.png").mkdir()
        database_before = database_path.read_bytes()

        result = subprocess.run(
            ["node", str(VERIFIER_SCRIPT)],
            cwd=REPO_ROOT,
            env=verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                FIXTURE_JSON=str(fixture_path),
                ARTIFACT_DIR=str(artifact_dir),
            ),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        database_after = database_path.read_bytes()
        summary_exists = (artifact_dir / "verification-summary.json").exists()
    finally:
        shutil.rmtree(case_root, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert database_after == database_before
    assert not summary_exists
    assert "Evidence output path must be absent or a regular file" in result.stderr


def test_roll_pallet_fixture_creates_only_the_four_required_card_kinds(tmp_path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"roll-pallet-safety-{tmp_path.name}"
    database_path = runtime_dir / "fixture.sqlite3"
    output_path = runtime_dir / "fixture.json"

    result = subprocess.run(
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

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert set(payload["cards"]) == {
        "running",
        "completed_mixed",
        "completed_all_blank",
        "completed_overflow",
    }
    assert len(set(payload["cards"].values())) == 4

    with sqlite3.connect(database_path) as connection:
        statuses = dict(
            connection.execute(
                "SELECT id, status FROM cards ORDER BY id"
            ).fetchall()
        )
        active_shift_count = connection.execute(
            "SELECT COUNT(*) FROM shift_occurrences WHERE ended_at IS NULL"
        ).fetchone()[0]
        overflow_pallet_count = connection.execute(
            """
            SELECT COUNT(DISTINCT pallet_number)
            FROM roll_entries
            WHERE card_id = ? AND pallet_number IS NOT NULL
            """,
            (payload["cards"]["completed_overflow"],),
        ).fetchone()[0]
        clear_candidate_pallet = connection.execute(
            "SELECT pallet_number FROM roll_entries WHERE id = ?",
            (payload["clear_candidate_roll_id"],),
        ).fetchone()[0]
        mixed_blank_pallet = connection.execute(
            "SELECT pallet_number FROM roll_entries WHERE id = ?",
            (payload["mixed_blank_roll_id"],),
        ).fetchone()[0]
        running_defaults = connection.execute(
            "SELECT tare_weight, current_pallet_number, version FROM cards WHERE id = ?",
            (payload["cards"]["running"],),
        ).fetchone()
        recipe_components_by_card = {
            card_id: connection.execute(
                """
                SELECT component_key, source_text, material_category,
                       planned_material, recipe_percent
                FROM recipe_components
                WHERE card_id = ?
                ORDER BY id
                """,
                (card_id,),
            ).fetchall()
            for card_id in payload["cards"].values()
        }

    assert statuses[payload["cards"]["running"]] == "running"
    assert statuses[payload["cards"]["completed_mixed"]] == "completed"
    assert statuses[payload["cards"]["completed_all_blank"]] == "completed"
    assert statuses[payload["cards"]["completed_overflow"]] == "completed"
    assert active_shift_count == 1
    assert overflow_pallet_count == payload["expected_summary_rows"]["completed_overflow"]
    assert overflow_pallet_count > payload["measured_capacities"]["overflow_page"] * 2
    assert clear_candidate_pallet is not None
    assert mixed_blank_pallet is None
    assert running_defaults == (1.25, 7, 1)
    expected_recipe_components = [
        ("raw_material_a", "LDPE; Alpha 2420H | 55%", "LDPE", "Alpha 2420H", 55),
        ("raw_material_b", "LDPE; Beta B20 | 20%", "LDPE", "Beta B20", 20),
        ("raw_material_c", "MDPE; Gamma 3802 | 10%", "MDPE", "Gamma 3802", 10),
        ("linear_pe", "LLDPE; Linear 118W | 10%", "LLDPE", "Linear 118W", 10),
        ("antistatic", "Antistatic; AS-1 | 1%", "Antistatic", "AS-1", 1),
        ("masterbatch", "Masterbatch; Blue MB | 3%", "Masterbatch", "Blue MB", 3),
        ("chalk", "Filler; Chalk C | 1%", "Filler", "Chalk C", 1),
    ]
    for card_id, components in recipe_components_by_card.items():
        assert components == expected_recipe_components, card_id
        assert sum(component[4] for component in components) == 100


def test_roll_pallet_verifier_completes_current_pencil_editor_workflow(tmp_path):
    runtime_dir = (
        REPO_ROOT
        / ".test-runtime"
        / f"roll-pallet-verifier-safety-{tmp_path.name}"
    )
    database_path = runtime_dir / "fixture.sqlite3"
    fixture_path = runtime_dir / "fixture.json"
    artifact_root = REPO_ROOT / "artifacts" / "ui-checks"
    artifact_root.mkdir(parents=True, exist_ok=True)

    try:
        fixture_result = subprocess.run(
            [
                sys.executable,
                str(FIXTURE_SCRIPT),
                "--db-path",
                str(database_path),
                "--output",
                str(fixture_path),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert fixture_result.returncode == 0, fixture_result.stderr

        with tempfile.TemporaryDirectory(
            prefix="roll-pallet-verifier-safety-",
            dir=artifact_root,
        ) as artifact_dir_value:
            artifact_dir = Path(artifact_dir_value)
            with temporary_server(database_path) as base_url:
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
                    timeout=240,
                    check=False,
                )

            assert result.returncode == 0, result.stderr
            summary = json.loads(
                (artifact_dir / "verification-summary.json").read_text(
                    encoding="utf-8"
                )
            )
            assert summary["status"] == "passed"
            assert summary["consoleErrors"] == []
            assert summary["browserErrors"] == []
            assert len(summary["interactions"]) == 2
            assert all(
                interaction["pencilEditorUsed"]
                and interaction["oneEditorAtATime"]
                for interaction in summary["interactions"]
            )
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)


def test_roll_pallet_verifier_rejects_fixture_symlink_resolving_outside_test_runtime(
    tmp_path,
):
    outside_fixture = tmp_path / "fixture.json"
    outside_fixture.write_text("{}\n", encoding="utf-8")
    runtime_dir = (
        REPO_ROOT
        / ".test-runtime"
        / f"roll-pallet-symlink-safety-{tmp_path.name}"
    )
    runtime_dir.mkdir(parents=True, exist_ok=True)
    fixture_symlink = runtime_dir / "fixture.json"
    fixture_symlink.symlink_to(outside_fixture)
    artifact_dir = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / f"roll-pallet-symlink-safety-{tmp_path.name}"
    )

    try:
        result = subprocess.run(
            ["node", str(VERIFIER_SCRIPT)],
            cwd=REPO_ROOT,
            env=verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                FIXTURE_JSON=str(fixture_symlink),
                ARTIFACT_DIR=str(artifact_dir),
            ),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    finally:
        fixture_symlink.unlink(missing_ok=True)
        runtime_dir.rmdir()
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "FIXTURE_JSON must resolve below .test-runtime." in result.stderr


def test_roll_pallet_scripts_do_not_embed_runtime_database_or_tool_installers():
    production_database_fragment = "/".join(
        ("data", "extrusion" + "_terminal.sqlite3")
    )
    forbidden_install_fragments = (
        "playwright install",
        "npm install",
        "npm ci",
        "npx playwright",
    )

    for script_path in (FIXTURE_SCRIPT, VERIFIER_SCRIPT):
        source = script_path.read_text(encoding="utf-8").lower()
        assert production_database_fragment not in source
        assert all(fragment not in source for fragment in forbidden_install_fragments)
