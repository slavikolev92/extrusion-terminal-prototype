from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
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


def unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@contextmanager
def timing_app_server(database_path: Path):
    port = unused_local_port()
    environment = os.environ.copy()
    environment.update(
        EXTRUSION_DB_PATH=str(database_path),
        EXTRUSION_DATA_DIR=str(database_path.parent),
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
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"{base_url}/health",
                    timeout=0.5,
                ) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("temporary timing-correction server did not start")
        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


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
    dedicated_root = (
        copied_root / ".test-runtime" / "terminal-timing-correction"
    )
    runtime_output = dedicated_root / "timing" / "fixture.json"

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
    safe_database = dedicated_root / "timing" / "fixture.sqlite3"
    safe_output = dedicated_root / "timing" / "fixture.json"
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

    runtime_root = dedicated_root
    runtime_root.mkdir(parents=True)
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

    database_link_dir = runtime_root / "hard-link-db"
    database_link_dir.mkdir()
    outside_database_sentinel = tmp_path / "outside-database-sentinel.sqlite3"
    outside_database_sentinel.write_bytes(b"outside database sentinel")
    hard_link_database = database_link_dir / "fixture.sqlite3"
    os.link(outside_database_sentinel, hard_link_database)
    hard_link_database_result = run_fixture(
        hard_link_database,
        database_link_dir / "fixture.json",
        cwd=copied_root,
        script=copied_script,
    )
    assert hard_link_database_result.returncode != 0
    assert "must not be hard-linked" in hard_link_database_result.stderr
    assert outside_database_sentinel.read_bytes() == b"outside database sentinel"

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


def test_timing_fixture_owns_only_dedicated_paths_and_refuses_unowned_targets(
    tmp_path: Path,
):
    copied_root = tmp_path / "isolated-repository"
    copied_scripts = copied_root / "scripts"
    copied_scripts.mkdir(parents=True)
    copied_script = copied_scripts / FIXTURE_SCRIPT.name
    shutil.copy2(FIXTURE_SCRIPT, copied_script)
    (copied_root / "app").symlink_to(REPO_ROOT / "app", target_is_directory=True)

    dedicated_root = (
        copied_root / ".test-runtime" / "terminal-timing-correction"
    )
    sibling_root = copied_root / ".test-runtime" / "other-verifier"
    sibling_result = run_fixture(
        sibling_root / "fixture.sqlite3",
        sibling_root / "fixture.json",
        cwd=copied_root,
        script=copied_script,
    )
    assert sibling_result.returncode != 0
    assert "must be under .test-runtime/terminal-timing-correction" in (
        sibling_result.stderr
    )
    assert not sibling_root.exists()

    outside_runtime_root = tmp_path / "outside-runtime-alias"
    outside_runtime_root.mkdir()
    runtime_alias = copied_root / ".test-runtime"
    runtime_alias.symlink_to(outside_runtime_root, target_is_directory=True)
    parent_alias_result = run_fixture(
        dedicated_root / "fixture.sqlite3",
        dedicated_root / "fixture.json",
        cwd=copied_root,
        script=copied_script,
    )
    assert parent_alias_result.returncode != 0
    assert "guard root must not contain symlinks" in parent_alias_result.stderr
    assert list(outside_runtime_root.iterdir()) == []
    runtime_alias.unlink()

    dedicated_root.mkdir(parents=True)
    database_path = dedicated_root / "fixture.sqlite3"
    output_path = dedicated_root / "fixture.json"
    database_sentinel = b"unowned single-link database sentinel"
    database_path.write_bytes(database_sentinel)
    unowned_database_result = run_fixture(
        database_path,
        output_path,
        cwd=copied_root,
        script=copied_script,
    )
    assert unowned_database_result.returncode != 0
    assert "existing fixture targets are not owned by this fixture" in (
        unowned_database_result.stderr
    )
    assert database_path.read_bytes() == database_sentinel
    assert not output_path.exists()

    database_path.unlink()
    output_sentinel = b"unowned single-link JSON sentinel"
    output_path.write_bytes(output_sentinel)
    unowned_output_result = run_fixture(
        database_path,
        output_path,
        cwd=copied_root,
        script=copied_script,
    )
    assert unowned_output_result.returncode != 0
    assert "existing fixture targets are not owned by this fixture" in (
        unowned_output_result.stderr
    )
    assert output_path.read_bytes() == output_sentinel
    assert not database_path.exists()

    output_path.unlink()
    first_result = run_fixture(
        database_path,
        output_path,
        cwd=copied_root,
        script=copied_script,
    )
    assert first_result.returncode == 0, first_result.stderr
    first_payload = json.loads(output_path.read_text(encoding="utf-8"))
    first_database_stat = database_path.stat()

    second_result = run_fixture(
        database_path,
        output_path,
        cwd=copied_root,
        script=copied_script,
    )
    assert second_result.returncode == 0, second_result.stderr
    second_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert second_payload["fixture_kind"] == "terminal-timing-correction-v1"
    assert second_payload["ownership_token"] == first_payload["ownership_token"]
    assert second_payload["snapshot"] == first_payload["snapshot"]
    assert database_path.stat().st_ino != first_database_stat.st_ino


def test_timing_verifier_requires_matching_health_database_identity(tmp_path: Path):
    runtime_dir = (
        REPO_ROOT
        / ".test-runtime"
        / "terminal-timing-correction"
        / f"timing-health-{tmp_path.name}"
    )
    artifact_dir = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / "terminal-timing-correction"
        / f"timing-health-{tmp_path.name}"
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
    runtime_dir = (
        REPO_ROOT
        / ".test-runtime"
        / "terminal-timing-correction"
        / f"timing-artifact-{tmp_path.name}"
    )
    runtime_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    database_path.write_bytes(b"synthetic fixture database")
    fixture_path = runtime_dir / "fixture.json"
    fixture_path.write_text(
        json.dumps({"db_path": str(database_path), "cards": {}}) + "\n",
        encoding="utf-8",
    )
    sibling_artifact_dir = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / f"other-verifier-{tmp_path.name}"
    )

    try:
        with health_server(database_path) as (base_url, outside_requests):
            outside_result = subprocess.run(
                ["node", str(VERIFIER_SCRIPT)],
                cwd=REPO_ROOT,
                env=verifier_environment(
                    BASE_URL=base_url,
                    FIXTURE_JSON=str(fixture_path),
                    ARTIFACT_DIR=str(sibling_artifact_dir),
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
            / "terminal-timing-correction"
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

        sentinel_artifact_dir = (
            REPO_ROOT
            / "artifacts"
            / "ui-checks"
            / "terminal-timing-correction"
            / f"timing-sentinel-{tmp_path.name}"
        )
        sentinel_artifact_dir.mkdir(parents=True)
        sentinel_path = sentinel_artifact_dir / "timing-editor-1366x768.png"
        sentinel_bytes = b"unowned single-link screenshot sentinel"
        sentinel_path.write_bytes(sentinel_bytes)
        with health_server(database_path) as (base_url, sentinel_requests):
            sentinel_result = subprocess.run(
                ["node", str(VERIFIER_SCRIPT)],
                cwd=REPO_ROOT,
                env=verifier_environment(
                    BASE_URL=base_url,
                    FIXTURE_JSON=str(fixture_path),
                    ARTIFACT_DIR=str(sentinel_artifact_dir),
                ),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        observed_sentinel = sentinel_path.read_bytes()

        outside_alias_target = tmp_path / "outside-artifact-alias"
        outside_alias_target.mkdir()
        alias_artifact_dir = (
            REPO_ROOT
            / "artifacts"
            / "ui-checks"
            / "terminal-timing-correction"
            / f"timing-alias-{tmp_path.name}"
        )
        alias_artifact_dir.symlink_to(outside_alias_target, target_is_directory=True)
        with health_server(database_path) as (base_url, alias_requests):
            alias_result = subprocess.run(
                ["node", str(VERIFIER_SCRIPT)],
                cwd=REPO_ROOT,
                env=verifier_environment(
                    BASE_URL=base_url,
                    FIXTURE_JSON=str(fixture_path),
                    ARTIFACT_DIR=str(alias_artifact_dir),
                ),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(
            REPO_ROOT
            / "artifacts"
            / "ui-checks"
            / "terminal-timing-correction"
            / f"timing-artifact-{tmp_path.name}",
            ignore_errors=True,
        )
        shutil.rmtree(
            REPO_ROOT
            / "artifacts"
            / "ui-checks"
            / "terminal-timing-correction"
            / f"timing-sentinel-{tmp_path.name}",
            ignore_errors=True,
        )
        alias_path = (
            REPO_ROOT
            / "artifacts"
            / "ui-checks"
            / "terminal-timing-correction"
            / f"timing-alias-{tmp_path.name}"
        )
        alias_path.unlink(missing_ok=True)
        shutil.rmtree(sibling_artifact_dir, ignore_errors=True)

    assert outside_result.returncode != 0
    assert (
        "ARTIFACT_DIR must be at or below "
        "artifacts/ui-checks/terminal-timing-correction"
    ) in outside_result.stderr
    assert outside_requests == []
    assert not sibling_artifact_dir.exists()
    assert guarded_result.returncode != 0
    assert "ARTIFACT_DIR must be an empty, dedicated run directory" in (
        guarded_result.stderr
    )
    assert guarded_requests == [("GET", "/health")]
    assert outside_bytes == b"outside summary sentinel"
    assert database_bytes == b"synthetic fixture database"
    assert sentinel_result.returncode != 0
    assert "ARTIFACT_DIR must be an empty, dedicated run directory" in (
        sentinel_result.stderr
    )
    assert sentinel_requests == [("GET", "/health")]
    assert observed_sentinel == sentinel_bytes
    assert alias_result.returncode != 0
    assert "ARTIFACT_DIR guard path must not contain symlinks" in alias_result.stderr
    assert alias_requests == []
    assert list(outside_alias_target.iterdir()) == []


def test_timing_verifier_accounts_for_requests_after_bounded_quiescence(
    tmp_path: Path,
):
    runtime_dir = (
        REPO_ROOT
        / ".test-runtime"
        / "terminal-timing-correction"
        / f"request-accounting-{tmp_path.name}"
    )
    database_path = runtime_dir / "fixture.sqlite3"
    fixture_path = runtime_dir / "fixture.json"
    artifact_root = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / "terminal-timing-correction"
    )
    artifact_root.mkdir(parents=True, exist_ok=True)

    try:
        fixture_result = run_fixture(database_path, fixture_path)
        assert fixture_result.returncode == 0, fixture_result.stderr
        with tempfile.TemporaryDirectory(
            prefix="request-accounting-",
            dir=artifact_root,
        ) as artifact_dir_value:
            artifact_dir = Path(artifact_dir_value)
            with timing_app_server(database_path) as base_url:
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
                    timeout=180,
                    check=False,
                )
            assert result.returncode == 0, result.stderr
            summary = json.loads(
                (artifact_dir / "verification-summary.json").read_text(
                    encoding="utf-8"
                )
            )

        assert summary["status"] == "passed"
        assert summary["requestCounts"] == {
            "finishReviewDoubleClick": 1,
            "confirmFinishDoubleClick": 1,
        }
        assert summary["requestQuiescenceWindowMs"] >= 200
        assert summary["routeGateTimeouts"] == []
        assert summary["unexpectedHttpResponses"] == []
        assert summary["unmatchedAbortedPreviewRequests"] == []
        assert summary["expectedHttpResponses"]
        assert {
            "phase": "validation-failures",
            "method": "POST",
            "pathname": "/terminal/cards/2/timing-ledger/preview",
            "status": 422,
        } in summary["expectedHttpResponses"]
        assert summary["expectedConsoleErrors"] == [{
            "phase": "validation-failures",
            "text": (
                "Failed to load resource: the server responded with a status of "
                "422 (Unprocessable Entity)"
            ),
        }]
        assert all(
            aborted["correlation"]
            for aborted in summary["abortedPreviewRequests"]
        )
        assert summary["consoleErrors"] == []
        assert summary["pageErrors"] == []
        assert summary["failedRequests"] == []
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
