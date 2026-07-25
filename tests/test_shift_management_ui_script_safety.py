from __future__ import annotations

import os
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
    ):
        environment.pop(name, None)
    environment.update(overrides)
    return environment


def run_verifier(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(VERIFICATION_SCRIPT)],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
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
        stdout=subprocess.PIPE,
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
            output, _ = process.communicate(timeout=5)
            pytest.fail(f"temporary server did not start:\n{output}")
        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


@pytest.mark.parametrize(
    ("missing_name", "provided"),
    [
        ("BASE_URL", {"ARTIFACT_DIR": "/tmp/unused-shift-ui-artifacts"}),
        ("ARTIFACT_DIR", {"BASE_URL": "http://127.0.0.1:9"}),
    ],
)
def test_verifier_requires_explicit_environment_before_browser_mutation(
    missing_name: str,
    provided: dict[str, str],
):
    result = run_verifier(verifier_environment(**provided))

    assert result.returncode != 0
    assert f"Required environment variable {missing_name} is missing." in result.stderr


def test_verifier_rejects_server_backed_by_different_database_before_mutation(tmp_path):
    server_dir = tmp_path / "different-server"
    server_dir.mkdir()
    server_database = server_dir / "server.sqlite3"
    initialize_database(server_database)
    artifact_root = REPO_ROOT / "artifacts" / "ui-checks"
    artifact_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="shift-safety-",
        dir=artifact_root,
    ) as artifact_dir_value:
        artifact_dir = Path(artifact_dir_value)
        artifact_database = artifact_dir / "shift-ui.sqlite3"
        initialize_database(artifact_database)

        with temporary_server(server_database) as base_url:
            result = run_verifier(
                verifier_environment(
                    BASE_URL=base_url,
                    ARTIFACT_DIR=str(artifact_dir),
                )
            )

        assert result.returncode != 0
        assert "Selected HTTP server is not backed by the required artifact database." in result.stderr
        assert database_counts(server_database) == (0, 0, 0, 4, 1)
        assert database_counts(artifact_database) == (0, 0, 0, 4, 1)
