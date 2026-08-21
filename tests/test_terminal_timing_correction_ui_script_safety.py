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


def test_timing_fixture_refuses_runtime_and_paths_outside_test_runtime(
    tmp_path: Path,
):
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
    runtime_output = copied_root / ".test-runtime" / "timing" / "fixture.json"

    runtime_result = run_fixture(
        fake_runtime_database,
        runtime_output,
        cwd=copied_root,
        script=copied_script,
    )
    assert runtime_result.returncode != 0
    assert "must be under .test-runtime" in runtime_result.stderr
    assert fake_runtime_database.read_bytes() == b"synthetic runtime sentinel"
    assert not runtime_output.exists()

    outside_database = tmp_path / "outside.sqlite3"
    outside_output = tmp_path / "outside.json"
    safe_database = copied_root / ".test-runtime" / "timing" / "fixture.sqlite3"
    safe_output = copied_root / ".test-runtime" / "timing" / "fixture.json"
    for database_path, output_path in (
        (outside_database, safe_output),
        (safe_database, outside_output),
    ):
        result = run_fixture(
            database_path,
            output_path,
            cwd=copied_root,
            script=copied_script,
        )
        assert result.returncode != 0
        assert "must be under .test-runtime" in result.stderr
    assert not outside_database.exists()
    assert not outside_output.exists()
    assert not safe_database.exists()
    assert not safe_output.exists()

    runtime_root = copied_root / ".test-runtime"
    runtime_root.mkdir()
    alias = runtime_root / "runtime-alias"
    alias.symlink_to(fake_runtime_dir, target_is_directory=True)
    alias_result = run_fixture(
        alias / "extrusion_terminal.sqlite3",
        runtime_root / "timing" / "alias.json",
        cwd=copied_root,
        script=copied_script,
    )
    assert alias_result.returncode != 0
    assert "must be under .test-runtime" in alias_result.stderr
    assert fake_runtime_database.read_bytes() == b"synthetic runtime sentinel"

    runtime_output_dir = runtime_root / "hard-link"
    runtime_output_dir.mkdir()
    outside_sentinel = tmp_path / "outside-sentinel.json"
    outside_sentinel.write_bytes(b"outside artifact sentinel")
    hard_link_output = runtime_output_dir / "fixture.json"
    os.link(outside_sentinel, hard_link_output)
    hard_link_result = run_fixture(
        runtime_output_dir / "fixture.sqlite3",
        hard_link_output,
        cwd=copied_root,
        script=copied_script,
    )
    assert hard_link_result.returncode != 0
    assert "must not be hard-linked" in hard_link_result.stderr
    assert outside_sentinel.read_bytes() == b"outside artifact sentinel"

    mismatch_database = runtime_root / "mismatch" / "fixture.sqlite3"
    mismatch_output = runtime_root / "mismatch" / "fixture.json"
    explicit_other_database = runtime_root / "other" / "fixture.sqlite3"
    mismatch_result = run_fixture(
        mismatch_database,
        mismatch_output,
        cwd=copied_root,
        script=copied_script,
        extrusion_db_path=explicit_other_database,
    )
    assert mismatch_result.returncode != 0
    assert "EXTRUSION_DB_PATH must match --db-path" in mismatch_result.stderr
    assert not mismatch_database.exists()
    assert not mismatch_output.exists()
    assert not explicit_other_database.exists()


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


def test_timing_verifier_writes_only_to_supplied_artifact_directory(tmp_path: Path):
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

        artifact_dir = (
            REPO_ROOT
            / "artifacts"
            / "ui-checks"
            / f"timing-artifact-{tmp_path.name}"
        )
        artifact_dir.mkdir(parents=True)
        outside_sentinel = tmp_path / "outside-summary.json"
        outside_sentinel.write_bytes(b"outside summary sentinel")
        summary_alias = artifact_dir / "verification-summary.json"
        os.link(outside_sentinel, summary_alias)
        with health_server(database_path) as (base_url, guarded_requests):
            guarded_result = subprocess.run(
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
        outside_bytes = outside_sentinel.read_bytes()
        database_bytes = database_path.read_bytes()
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(
            REPO_ROOT
            / "artifacts"
            / "ui-checks"
            / f"timing-artifact-{tmp_path.name}",
            ignore_errors=True,
        )

    assert outside_result.returncode != 0
    assert "ARTIFACT_DIR must be below artifacts/ui-checks" in outside_result.stderr
    assert outside_requests == []
    assert not outside_artifact_dir.exists()
    assert guarded_result.returncode != 0
    assert "Existing artifact target must not be hard-linked" in guarded_result.stderr
    assert guarded_requests == [("GET", "/health")]
    assert outside_bytes == b"outside summary sentinel"
    assert database_bytes == b"synthetic fixture database"
