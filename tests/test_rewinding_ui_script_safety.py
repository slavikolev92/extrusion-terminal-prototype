from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
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
        }
        assert len(set(first_payload["cards"].values())) == 7

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
        assert rows[cards["waiting_newest"]]["finished_at"] > rows[cards["waiting_older"]]["finished_at"]
        assert rows[cards["waiting_newest"]]["rewinding_roll_count"] != rows[cards["waiting_older"]]["rewinding_roll_count"]
        assert [row[0] for row in running_pallets] == [7, None]
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
    assert "ARTIFACT_DIR resolves outside artifacts/ui-checks." in result.stderr


def test_rewinding_verifier_preflights_database_before_mutating_scenarios():
    source = VERIFIER_SCRIPT.read_text(encoding="utf-8")

    assert '`${baseURL}/health`' in source
    assert source.index("await preflightDatabase(page);") < source.index(
        "await verifyMutatingScenarios(page, viewport);"
    )


def test_rewinding_scripts_use_local_playwright_without_installers_or_runtime_db():
    production_database_fragment = "/".join(("data", "extrusion" + "_terminal.sqlite3"))
    forbidden_fragments = (
        "playwright install",
        "npm install",
        "npm ci",
        "npx playwright",
    )

    verifier_source = VERIFIER_SCRIPT.read_text(encoding="utf-8")
    assert "createRequire(import.meta.url)" in verifier_source
    assert 'require("@playwright/test")' in verifier_source

    for script_path in (FIXTURE_SCRIPT, VERIFIER_SCRIPT):
        source = script_path.read_text(encoding="utf-8").lower()
        assert production_database_fragment not in source
        assert all(fragment not in source for fragment in forbidden_fragments)
