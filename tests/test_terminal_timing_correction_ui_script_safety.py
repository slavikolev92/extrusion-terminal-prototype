from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "create_terminal_timing_correction_fixture.py"
VERIFIER_SCRIPT = REPO_ROOT / "scripts" / "verify_terminal_timing_correction_ui.mjs"


def run_fixture(
    database_path: Path | str,
    output_path: Path | str,
    *,
    cwd: Path = REPO_ROOT,
    script: Path = FIXTURE_SCRIPT,
    extrusion_db_path: Path | str | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if extrusion_db_path is None:
        environment.pop("EXTRUSION_DB_PATH", None)
    else:
        environment["EXTRUSION_DB_PATH"] = str(extrusion_db_path)
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--db-path",
            str(database_path),
            "--output",
            str(output_path),
        ],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def verifier_environment(**overrides: str) -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("BASE_URL", "FIXTURE_JSON", "ARTIFACT_DIR"):
        environment.pop(name, None)
    environment.update(overrides)
    return environment


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


def test_timing_fixture_only_replaces_requested_temp_database(tmp_path: Path):
    copied_root = tmp_path / "isolated-repository"
    copied_scripts = copied_root / "scripts"
    copied_scripts.mkdir(parents=True)
    copied_script = copied_scripts / FIXTURE_SCRIPT.name
    shutil.copy2(FIXTURE_SCRIPT, copied_script)
    (copied_root / "app").symlink_to(REPO_ROOT / "app", target_is_directory=True)

    fake_runtime_dir = copied_root / "data"
    fake_runtime_dir.mkdir()
    fake_runtime_database = fake_runtime_dir / "extrusion_terminal.sqlite3"
    fake_runtime_database.write_bytes(b"synthetic runtime sentinel")
    temporary_dir = copied_root / ".test-runtime" / "timing"
    temporary_database = temporary_dir / "fixture.sqlite3"
    temporary_output = temporary_dir / "fixture.json"

    runtime_result = run_fixture(
        fake_runtime_database,
        temporary_output,
        cwd=copied_root,
        script=copied_script,
    )
    assert runtime_result.returncode != 0
    assert "must be under .test-runtime" in runtime_result.stderr
    assert fake_runtime_database.read_bytes() == b"synthetic runtime sentinel"
    assert not temporary_output.exists()

    temporary_result = run_fixture(
        temporary_database,
        temporary_output,
        cwd=copied_root,
        script=copied_script,
        extrusion_db_path=temporary_database,
    )
    assert temporary_result.returncode == 0, temporary_result.stderr
    fixture = json.loads(temporary_output.read_text(encoding="utf-8"))
    assert Path(fixture["db_path"]) == temporary_database
    assert set(fixture["cards"]) == {
        "running",
        "paused",
        "completed",
        "awaiting_rewinding",
        "many_rows",
    }
    assert temporary_database.is_file()
    assert fake_runtime_database.read_bytes() == b"synthetic runtime sentinel"


def test_timing_verifier_requires_matching_health_database_identity(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"timing-health-{tmp_path.name}"
    artifact_dir = (
        REPO_ROOT / "artifacts" / "ui-checks" / f"timing-health-{tmp_path.name}"
    )
    runtime_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    database_path.write_bytes(b"synthetic fixture database")
    fixture_path = runtime_dir / "fixture.json"
    fixture_text = json.dumps({"db_path": str(database_path), "cards": {}}) + "\n"
    fixture_path.write_text(fixture_text, encoding="utf-8")
    mismatched_database = tmp_path / "different.sqlite3"
    mismatched_database.write_bytes(b"different synthetic database")

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
        database_bytes = database_path.read_bytes()
        observed_fixture = fixture_path.read_text(encoding="utf-8")
        artifact_directory_was_created = artifact_dir.exists()
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "server database identity" in result.stderr
    assert requests == [("GET", "/health")]
    assert database_bytes == b"synthetic fixture database"
    assert observed_fixture == fixture_text
    assert not artifact_directory_was_created


def test_timing_verifier_rejects_artifacts_outside_repository(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"timing-artifact-{tmp_path.name}"
    runtime_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    database_path.write_bytes(b"synthetic fixture database")
    fixture_path = runtime_dir / "fixture.json"
    fixture_path.write_text(
        json.dumps({"db_path": str(database_path), "cards": {}}) + "\n",
        encoding="utf-8",
    )
    outside_artifact_dir = tmp_path / "outside-artifacts"

    try:
        with health_server(database_path) as (base_url, outside_requests):
            outside_result = subprocess.run(
                ["node", str(VERIFIER_SCRIPT)],
                cwd=REPO_ROOT,
                env=verifier_environment(
                    BASE_URL=base_url,
                    FIXTURE_JSON=str(fixture_path),
                    ARTIFACT_DIR=str(outside_artifact_dir),
                ),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

        database_bytes = database_path.read_bytes()
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert outside_result.returncode != 0
    assert "ARTIFACT_DIR must be below artifacts/ui-checks" in outside_result.stderr
    assert outside_requests == []
    assert not outside_artifact_dir.exists()
    assert database_bytes == b"synthetic fixture database"
