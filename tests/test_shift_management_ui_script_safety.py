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
VERIFICATION_SCRIPT = REPO_ROOT / "scripts" / "verify_shift_management_ui.mjs"


def verifier_environment(**overrides: str) -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "ARTIFACT_DIR",
        "BASE_URL",
        "EXTRUSION_DATA_DIR",
        "EXTRUSION_DB_PATH",
        "RUNTIME_DIR",
    ):
        environment.pop(name, None)
    environment.update(overrides)
    return environment


def run_verifier(
    environment: dict[str, str],
    *,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(VERIFICATION_SCRIPT)],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def initialize_database(database_path: Path) -> None:
    environment = verifier_environment(
        EXTRUSION_DATA_DIR=str(database_path.parent),
        EXTRUSION_DB_PATH=str(database_path),
    )
    result = subprocess.run(
        [sys.executable, "-c", "from app.db import init_db; init_db()"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def database_counts(database_path: Path) -> tuple[int, int, int, int, int]:
    with sqlite3.connect(database_path) as connection:
        card_count = int(connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0])
        import_count = int(
            connection.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
        )
        occurrence_count = int(
            connection.execute("SELECT COUNT(*) FROM shift_occurrences").fetchone()[0]
        )
        shift_count, version = connection.execute(
            "SELECT shift_count, version FROM terminal_configuration WHERE id = 1"
        ).fetchone()
    return card_count, import_count, occurrence_count, int(shift_count), int(version)


def unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@contextmanager
def temporary_server(database_path: Path):
    port = unused_local_port()
    environment = verifier_environment(
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
                with urllib.request.urlopen(f"{base_url}/health", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.05)
        else:
            process.terminate()
            process.wait(timeout=5)
            pytest.fail("temporary server did not start")
        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize(
    ("missing_name", "provided"),
    [
        (
            "BASE_URL",
            {
                "RUNTIME_DIR": ".test-runtime/unused-shift-ui-runtime",
                "ARTIFACT_DIR": "artifacts/ui-checks/unused-shift-ui-artifacts",
            },
        ),
        (
            "RUNTIME_DIR",
            {
                "BASE_URL": "http://127.0.0.1:9",
                "ARTIFACT_DIR": "artifacts/ui-checks/unused-shift-ui-artifacts",
            },
        ),
        (
            "ARTIFACT_DIR",
            {
                "BASE_URL": "http://127.0.0.1:9",
                "RUNTIME_DIR": ".test-runtime/unused-shift-ui-runtime",
            },
        ),
    ],
)
def test_verifier_requires_explicit_environment_before_browser_mutation(
    missing_name: str,
    provided: dict[str, str],
):
    result = run_verifier(verifier_environment(**provided))

    assert result.returncode != 0
    assert f"Required environment variable {missing_name} is missing." in result.stderr


@pytest.mark.parametrize(
    ("input_name", "input_value", "expected_error"),
    [
        (
            "RUNTIME_DIR",
            "outside-runtime",
            "RUNTIME_DIR must be below .test-runtime.",
        ),
        (
            "ARTIFACT_DIR",
            "outside-artifacts",
            "ARTIFACT_DIR must be below artifacts/ui-checks.",
        ),
    ],
)
def test_verifier_rejects_paths_outside_guard_roots_before_mutation(
    tmp_path: Path,
    input_name: str,
    input_value: str,
    expected_error: str,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"shift-path-{tmp_path.name}"
    artifact_dir = (
        REPO_ROOT / "artifacts" / "ui-checks" / f"shift-path-{tmp_path.name}"
    )
    outside_path = tmp_path / input_value
    outside_path.mkdir()
    environment = verifier_environment(
        BASE_URL="http://127.0.0.1:9",
        RUNTIME_DIR=str(runtime_dir),
        ARTIFACT_DIR=str(artifact_dir),
    )
    environment[input_name] = str(outside_path)

    try:
        result = run_verifier(environment)
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert list(outside_path.iterdir()) == []


@pytest.mark.parametrize(
    ("input_name", "expected_error"),
    [
        ("RUNTIME_DIR", "RUNTIME_DIR guard path must not contain symlinks."),
        ("ARTIFACT_DIR", "ARTIFACT_DIR guard path must not contain symlinks."),
    ],
)
def test_verifier_rejects_guard_path_symlink_escape_before_mutation(
    tmp_path: Path,
    input_name: str,
    expected_error: str,
):
    outside_dir = tmp_path / f"outside-{input_name.lower()}"
    outside_dir.mkdir()
    runtime_dir = REPO_ROOT / ".test-runtime" / f"shift-symlink-{tmp_path.name}"
    artifact_dir = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / f"shift-symlink-{tmp_path.name}"
    )
    guarded_path = runtime_dir if input_name == "RUNTIME_DIR" else artifact_dir
    guarded_path.parent.mkdir(parents=True, exist_ok=True)
    guarded_path.symlink_to(outside_dir, target_is_directory=True)

    try:
        result = run_verifier(
            verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                RUNTIME_DIR=str(runtime_dir),
                ARTIFACT_DIR=str(artifact_dir),
            )
        )
    finally:
        guarded_path.unlink(missing_ok=True)
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert list(outside_dir.iterdir()) == []


def test_verifier_rejects_summary_leaf_symlink_and_preserves_sentinel_before_health(
    tmp_path: Path,
):
    case_root = (
        REPO_ROOT
        / ".test-runtime"
        / "release-candidate-audit"
        / "final-verifier-fix-round-1"
        / f"shift-summary-leaf-{tmp_path.name}"
    )
    runtime_dir = case_root / "runtime"
    database_path = runtime_dir / "shift-ui.sqlite3"
    sentinel_path = case_root / "outside-summary-sentinel.json"
    artifact_dir = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / "release-candidate-audit"
        / "final-verifier-fix-round-1"
        / f"shift-summary-leaf-{tmp_path.name}"
    )
    sentinel = "sentinel: must remain unchanged\n"

    try:
        initialize_database(database_path)
        artifact_dir.mkdir(parents=True)
        sentinel_path.write_text(sentinel, encoding="utf-8")
        (artifact_dir / "shift-management-ui-summary.json").symlink_to(sentinel_path)
        before = database_counts(database_path)

        result = run_verifier(
            verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                RUNTIME_DIR=str(runtime_dir),
                ARTIFACT_DIR=str(artifact_dir),
            )
        )
        sentinel_after = sentinel_path.read_text(encoding="utf-8")
        after = database_counts(database_path)
    finally:
        shutil.rmtree(case_root, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "Evidence output path must not be a symlink" in result.stderr
    assert sentinel_after == sentinel
    assert after == before


def test_verifier_rejects_non_regular_screenshot_leaf_before_health(
    tmp_path: Path,
):
    case_root = (
        REPO_ROOT
        / ".test-runtime"
        / "release-candidate-audit"
        / "final-verifier-fix-round-1"
        / f"shift-screenshot-leaf-{tmp_path.name}"
    )
    runtime_dir = case_root / "runtime"
    database_path = runtime_dir / "shift-ui.sqlite3"
    artifact_dir = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / "release-candidate-audit"
        / "final-verifier-fix-round-1"
        / f"shift-screenshot-leaf-{tmp_path.name}"
    )

    try:
        initialize_database(database_path)
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "admin-shift-count.png").mkdir()
        before = database_counts(database_path)

        result = run_verifier(
            verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                RUNTIME_DIR=str(runtime_dir),
                ARTIFACT_DIR=str(artifact_dir),
            )
        )
        after = database_counts(database_path)
    finally:
        shutil.rmtree(case_root, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "Evidence output path must be absent or a regular file" in result.stderr
    assert after == before


def test_verifier_rejects_runtime_database_symlink_before_mutation(tmp_path: Path):
    outside_database = tmp_path / "outside.sqlite3"
    initialize_database(outside_database)
    before = database_counts(outside_database)
    runtime_dir = REPO_ROOT / ".test-runtime" / f"shift-db-link-{tmp_path.name}"
    artifact_dir = (
        REPO_ROOT / "artifacts" / "ui-checks" / f"shift-db-link-{tmp_path.name}"
    )
    runtime_dir.mkdir(parents=True)
    artifact_dir.mkdir(parents=True)
    (runtime_dir / "shift-ui.sqlite3").symlink_to(outside_database)

    try:
        result = run_verifier(
            verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                RUNTIME_DIR=str(runtime_dir),
                ARTIFACT_DIR=str(artifact_dir),
            )
        )
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "Temporary database must resolve inside RUNTIME_DIR." in result.stderr
    assert database_counts(outside_database) == before


def test_verifier_rejects_runtime_csv_symlink_before_mutation(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"shift-csv-link-{tmp_path.name}"
    artifact_dir = (
        REPO_ROOT / "artifacts" / "ui-checks" / f"shift-csv-link-{tmp_path.name}"
    )
    database_path = runtime_dir / "shift-ui.sqlite3"
    initialize_database(database_path)
    artifact_dir.mkdir(parents=True)
    outside_csv = tmp_path / "outside.csv"
    outside_csv.write_text("sentinel\n", encoding="utf-8")
    (runtime_dir / "shift-management-orders.csv").symlink_to(outside_csv)

    try:
        result = run_verifier(
            verifier_environment(
                BASE_URL="http://127.0.0.1:9",
                RUNTIME_DIR=str(runtime_dir),
                ARTIFACT_DIR=str(artifact_dir),
            )
        )
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "CSV fixture path must not be a symlink." in result.stderr
    assert outside_csv.read_text(encoding="utf-8") == "sentinel\n"


def test_verifier_rejects_server_backed_by_different_database_before_mutation(tmp_path):
    runtime_root = REPO_ROOT / ".test-runtime" / f"shift-identity-{tmp_path.name}"
    server_dir = runtime_root / "different-server"
    server_dir.mkdir(parents=True)
    server_database = server_dir / "server.sqlite3"
    initialize_database(server_database)
    verifier_runtime_dir = runtime_root / "verifier"
    verifier_runtime_dir.mkdir()
    verifier_database = verifier_runtime_dir / "shift-ui.sqlite3"
    initialize_database(verifier_database)
    artifact_root = REPO_ROOT / "artifacts" / "ui-checks"
    artifact_root.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(
            prefix="shift-safety-",
            dir=artifact_root,
        ) as artifact_dir_value:
            artifact_dir = Path(artifact_dir_value)

            with temporary_server(server_database) as base_url:
                result = run_verifier(
                    verifier_environment(
                        BASE_URL=base_url,
                        RUNTIME_DIR=str(verifier_runtime_dir),
                        ARTIFACT_DIR=str(artifact_dir),
                    )
                )
            server_counts_after = database_counts(server_database)
            verifier_counts_after = database_counts(verifier_database)
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)

    assert result.returncode != 0
    assert "server database identity" in result.stderr
    assert server_counts_after == (0, 0, 0, 4, 1)
    assert verifier_counts_after == (0, 0, 0, 4, 1)


def test_verifier_repeats_post_correction_history_transition(tmp_path: Path):
    runtime_root = (
        REPO_ROOT
        / ".test-runtime"
        / "release-candidate-audit"
        / "final-verifier-fix-round-1"
    )
    runtime_root.mkdir(parents=True, exist_ok=True)
    runtime_dir = Path(
        tempfile.mkdtemp(
            prefix=f"shift-history-regression-{tmp_path.name}-",
            dir=runtime_root,
        )
    )
    database_path = runtime_dir / "shift-ui.sqlite3"
    artifact_root = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / "release-candidate-audit"
        / "final-verifier-fix-round-1"
    )
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_dir = Path(
        tempfile.mkdtemp(
            prefix=f"shift-history-regression-{tmp_path.name}-",
            dir=artifact_root,
        )
    )

    try:
        initialize_database(database_path)
        with temporary_server(database_path) as base_url:
            result = run_verifier(
                verifier_environment(
                    BASE_URL=base_url,
                    RUNTIME_DIR=str(runtime_dir),
                    ARTIFACT_DIR=str(artifact_dir),
                ),
                timeout=300,
            )

        assert result.returncode == 0, result.stderr
        summary = json.loads(
            (artifact_dir / "shift-management-ui-summary.json").read_text(
                encoding="utf-8"
            )
        )
        assert summary["postCorrectionHistoryTransitions"] == 3
        assert summary["integrityCheck"] == "ok"
        assert summary["foreignKeyErrors"] == 0
        assert len(summary["screenshots"]) == 11
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)
