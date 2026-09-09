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
FIXTURE_SCRIPT = REPO_ROOT / "scripts" / "create_order_finish_review_fixture.py"
VERIFIER_SCRIPT = REPO_ROOT / "scripts" / "verify_order_finish_review_ui.mjs"
VERIFIER_CONTRACT = REPO_ROOT / "scripts" / "order_finish_review_ui_contract.mjs"
OUTPUT_GUARD = REPO_ROOT / "scripts" / "order_finish_review_output_guard.mjs"
SCENARIOS = {
    "active_normal",
    "active_marked_empty",
    "active_marked_mixed",
    "waiting_many_pallets",
    "waiting_marker_cleared",
    "waiting_zero_rolls",
}


def run_fixture(
    database_path: Path | str,
    output_path: Path | str,
    *,
    cwd: Path = REPO_ROOT,
    script: Path = FIXTURE_SCRIPT,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("EXTRUSION_DB_PATH", None)
    environment.pop("EXTRUSION_DATA_DIR", None)
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


def run_contract_probe(expression: str) -> subprocess.CompletedProcess[str]:
    contract_url = VERIFIER_CONTRACT.resolve().as_uri()
    program = (
        f'import {{ VERIFICATION_CONTRACT }} from {json.dumps(contract_url)}; '
        f"console.log(JSON.stringify({expression}));"
    )
    return subprocess.run(
        ["node", "--input-type=module", "--eval", program],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def run_output_guard_probe(program: str, *arguments: Path) -> subprocess.CompletedProcess[str]:
    guard_url = OUTPUT_GUARD.resolve().as_uri()
    source = (
        f'import {{ assertSafeGeneratedFileTarget, writeGeneratedFileAtomic }} '
        f'from {json.dumps(guard_url)}; '
        f"{program}"
    )
    return subprocess.run(
        [
            "node",
            "--input-type=module",
            "--eval",
            source,
            *(str(argument) for argument in arguments),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def copy_fixture_repository(tmp_path: Path) -> tuple[Path, Path]:
    copied_root = tmp_path / "isolated-repository"
    copied_scripts = copied_root / "scripts"
    copied_scripts.mkdir(parents=True)
    copied_script = copied_scripts / FIXTURE_SCRIPT.name
    shutil.copy2(FIXTURE_SCRIPT, copied_script)
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
        (
            "data/extrusion_terminal.sqlite3",
            ".test-runtime/order-finish-review/output.json",
        ),
        ("{outside}/fixture.sqlite3", "{outside}/fixture.json"),
        (
            ".test-runtime/order-finish-review/fixture.sqlite3",
            "{outside}/fixture.json",
        ),
    ],
)
def test_fixture_rejects_runtime_and_external_paths(
    tmp_path: Path,
    database_path: str,
    output_path: str,
):
    database_path = database_path.format(outside=tmp_path)
    output_path = output_path.format(outside=tmp_path)

    result = run_fixture(database_path, output_path)

    assert result.returncode != 0
    assert "must be under .test-runtime" in result.stderr
    if Path(database_path).is_absolute():
        assert not Path(database_path).exists()
    if Path(output_path).is_absolute():
        assert not Path(output_path).exists()


@pytest.mark.parametrize("escaped_target", ["database", "output"])
def test_fixture_rejects_symlink_escape_without_mutation(
    tmp_path: Path,
    escaped_target: str,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"finish-link-{tmp_path.name}"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    runtime_dir.mkdir(parents=True)
    escape = runtime_dir / "escape"
    escape.symlink_to(outside_dir, target_is_directory=True)
    safe_database = runtime_dir / "fixture.sqlite3"
    safe_output = runtime_dir / "fixture.json"
    database_path = (
        escape / "fixture.sqlite3"
        if escaped_target == "database"
        else safe_database
    )
    output_path = escape / "fixture.json" if escaped_target == "output" else safe_output
    escaped_path = database_path if escaped_target == "database" else output_path
    escaped_path.write_bytes(b"outside sentinel")

    try:
        result = run_fixture(database_path, output_path)
        escaped_bytes = escaped_path.read_bytes()
        safe_database_created = safe_database.exists()
        safe_output_created = safe_output.exists()
    finally:
        escape.unlink(missing_ok=True)
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "must be under .test-runtime" in result.stderr
    assert escaped_bytes == b"outside sentinel"
    if escaped_target == "database":
        assert not safe_output_created
    else:
        assert not safe_database_created


def test_fixture_rejects_symlinked_runtime_root_without_mutation(tmp_path: Path):
    copied_root, copied_script = copy_fixture_repository(tmp_path)
    outside_dir = tmp_path / "outside-runtime"
    outside_dir.mkdir()
    database_path = outside_dir / "fixture.sqlite3"
    database_path.write_bytes(b"runtime database sentinel")
    (copied_root / ".test-runtime").symlink_to(
        outside_dir,
        target_is_directory=True,
    )

    result = run_fixture(
        ".test-runtime/fixture.sqlite3",
        ".test-runtime/fixture.json",
        cwd=copied_root,
        script=copied_script,
    )

    assert result.returncode != 0
    assert ".test-runtime guard root must not be a symlink" in result.stderr
    assert database_path.read_bytes() == b"runtime database sentinel"
    assert not (outside_dir / "fixture.json").exists()


@pytest.mark.parametrize("linked_target", ["database", "output"])
def test_fixture_rejects_hard_linked_generated_target_without_mutating_sentinel(
    tmp_path: Path,
    linked_target: str,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"finish-hardlink-{tmp_path.name}"
    runtime_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    output_path = runtime_dir / "fixture.json"
    sentinel = tmp_path / f"{linked_target}-sentinel"
    sentinel.write_bytes(b"repository-external sentinel")
    target = database_path if linked_target == "database" else output_path
    os.link(sentinel, target)

    try:
        result = run_fixture(database_path, output_path)
        sentinel_bytes = sentinel.read_bytes()
        target_bytes = target.read_bytes()
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "must not have multiple hard links" in result.stderr
    assert sentinel_bytes == b"repository-external sentinel"
    assert target_bytes == b"repository-external sentinel"


@pytest.mark.parametrize("directory_target", ["database", "output"])
def test_fixture_rejects_directory_where_regular_file_is_required(
    tmp_path: Path,
    directory_target: str,
):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"finish-directory-{tmp_path.name}"
    database_path = runtime_dir / "fixture.sqlite3"
    output_path = runtime_dir / "fixture.json"
    runtime_dir.mkdir(parents=True)
    target = database_path if directory_target == "database" else output_path
    target.mkdir()

    try:
        result = run_fixture(database_path, output_path)
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "must be a regular file" in result.stderr


def test_fixture_emits_all_deterministic_review_states(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"finish-fixture-{tmp_path.name}"
    database_path = runtime_dir / "fixture.sqlite3"
    output_path = runtime_dir / "fixture.json"

    try:
        first = run_fixture(database_path, output_path)
        assert first.returncode == 0, first.stderr
        first_payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert Path(first_payload["db_path"]) == database_path.resolve()
        assert set(first_payload["cards"]) == SCENARIOS
        assert set(first_payload["orders"]) == SCENARIOS
        assert set(first_payload["snapshot"]["cards"]) == SCENARIOS
        assert len(set(first_payload["cards"].values())) == len(SCENARIOS)

        with sqlite3.connect(database_path) as connection:
            connection.row_factory = sqlite3.Row
            cards = {
                row["id"]: dict(row)
                for row in connection.execute(
                    """
                    SELECT id, order_number, customer, product_type,
                           size_thickness, status, machine_id,
                           rewinding_roll_count
                    FROM cards
                    ORDER BY id
                    """
                )
            }
            roll_counts = {
                scenario: connection.execute(
                    "SELECT COUNT(*) FROM roll_entries WHERE card_id = ?",
                    (first_payload["cards"][scenario],),
                ).fetchone()[0]
                for scenario in SCENARIOS
            }
            pallet_groups = connection.execute(
                """
                SELECT COUNT(DISTINCT pallet_number)
                FROM roll_entries
                WHERE card_id = ? AND pallet_number IS NOT NULL
                """,
                (first_payload["cards"]["waiting_many_pallets"],),
            ).fetchone()[0]
            mixed_pallets = [
                row[0]
                for row in connection.execute(
                    """
                    SELECT pallet_number
                    FROM roll_entries
                    WHERE card_id = ?
                    ORDER BY roll_number
                    """,
                    (first_payload["cards"]["active_marked_mixed"],),
                ).fetchall()
            ]
            running_by_machine = connection.execute(
                """
                SELECT machine_id, COUNT(*)
                FROM cards
                WHERE status = 'running'
                GROUP BY machine_id
                """
            ).fetchall()
            machine_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT id FROM machines ORDER BY id"
                ).fetchall()
            ]

        ids = first_payload["cards"]
        assert cards[ids["active_normal"]]["status"] == "running"
        assert cards[ids["active_normal"]]["rewinding_roll_count"] is None
        assert len(cards[ids["active_normal"]]["customer"]) >= 45
        assert len(cards[ids["active_normal"]]["product_type"]) >= 60
        assert cards[ids["active_normal"]]["size_thickness"].endswith("0.060 мм")
        assert roll_counts["active_normal"] >= 12
        assert cards[ids["active_marked_empty"]]["status"] == "running"
        assert cards[ids["active_marked_empty"]]["rewinding_roll_count"] > 0
        assert roll_counts["active_marked_empty"] == 0
        assert cards[ids["active_marked_mixed"]]["status"] == "running"
        assert cards[ids["active_marked_mixed"]]["rewinding_roll_count"] > 0
        assert roll_counts["active_marked_mixed"] >= 2
        assert mixed_pallets == [7, None]
        assert cards[ids["waiting_many_pallets"]]["status"] == "awaiting_rewinding"
        assert pallet_groups >= 12
        assert cards[ids["waiting_marker_cleared"]]["status"] == "awaiting_rewinding"
        assert cards[ids["waiting_marker_cleared"]]["rewinding_roll_count"] is None
        assert roll_counts["waiting_marker_cleared"] > 0
        assert cards[ids["waiting_zero_rolls"]]["status"] == "awaiting_rewinding"
        assert roll_counts["waiting_zero_rolls"] == 0
        assert machine_ids == [1, 2, 3, 4]
        assert all(count == 1 for _machine, count in running_by_machine)

        second = run_fixture(database_path, output_path)
        assert second.returncode == 0, second.stderr
        second_payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert second_payload == first_payload
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)


def test_verifier_rejects_mismatched_health_database_before_writes(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"finish-health-{tmp_path.name}"
    artifact_dir = (
        REPO_ROOT / "artifacts" / "ui-checks" / f"finish-health-{tmp_path.name}"
    )
    runtime_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    database_path.write_bytes(b"fixture database sentinel")
    fixture_path = runtime_dir / "fixture.json"
    fixture_text = json.dumps({"db_path": str(database_path), "cards": {}}) + "\n"
    fixture_path.write_text(fixture_text, encoding="utf-8")
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
        artifact_created = artifact_dir.exists()
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "server database identity" in result.stderr
    assert requests == [("GET", "/health")]
    assert observed_database == b"fixture database sentinel"
    assert observed_fixture == fixture_text
    assert not artifact_created


def test_verifier_rejects_artifact_output_outside_guard(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"finish-artifact-{tmp_path.name}"
    runtime_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    database_path.write_bytes(b"fixture database sentinel")
    fixture_path = runtime_dir / "fixture.json"
    fixture_path.write_text(
        json.dumps({"db_path": str(database_path), "cards": {}}) + "\n",
        encoding="utf-8",
    )
    outside_artifact_dir = tmp_path / "outside-artifacts"

    try:
        with health_server(database_path) as (_base_url, requests):
            result = subprocess.run(
                ["node", str(VERIFIER_SCRIPT)],
                cwd=REPO_ROOT,
                env=verifier_environment(
                    BASE_URL=_base_url,
                    FIXTURE_JSON=str(fixture_path),
                    ARTIFACT_DIR=str(outside_artifact_dir),
                ),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "ARTIFACT_DIR must be below artifacts/ui-checks" in result.stderr
    assert requests == []
    assert not outside_artifact_dir.exists()


def test_verifier_rejects_artifact_symlink_escape(tmp_path: Path):
    runtime_dir = REPO_ROOT / ".test-runtime" / f"finish-art-link-{tmp_path.name}"
    runtime_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    database_path.write_bytes(b"fixture database sentinel")
    fixture_path = runtime_dir / "fixture.json"
    fixture_path.write_text(
        json.dumps({"db_path": str(database_path), "cards": {}}) + "\n",
        encoding="utf-8",
    )
    outside_artifact_dir = tmp_path / "outside-artifacts"
    outside_artifact_dir.mkdir()
    artifact_link = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / f"finish-art-link-{tmp_path.name}"
    )
    artifact_link.parent.mkdir(parents=True, exist_ok=True)
    artifact_link.symlink_to(outside_artifact_dir, target_is_directory=True)

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
            timeout=30,
            check=False,
        )
    finally:
        artifact_link.unlink(missing_ok=True)
        shutil.rmtree(runtime_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "ARTIFACT_DIR guard path must not contain symlinks" in result.stderr
    assert list(outside_artifact_dir.iterdir()) == []


@pytest.mark.parametrize(
    "name",
    [
        "verification-summary.json",
        "active-normal-1440x900.png",
    ],
)
def test_generated_output_guard_rejects_hard_links_without_mutating_sentinel(
    tmp_path: Path,
    name: str,
):
    artifact_dir = (
        REPO_ROOT
        / "artifacts"
        / "ui-checks"
        / f"finish-output-hardlink-{tmp_path.name}-{Path(name).stem}"
    )
    artifact_dir.mkdir(parents=True)
    sentinel = tmp_path / f"{Path(name).stem}-sentinel"
    sentinel.write_bytes(b"repository-external sentinel")
    target = artifact_dir / name
    os.link(sentinel, target)

    try:
        result = run_output_guard_probe(
            "assertSafeGeneratedFileTarget(process.argv[1], 'generated target');",
            target,
        )
        sentinel_bytes = sentinel.read_bytes()
        target_bytes = target.read_bytes()
    finally:
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode != 0
    assert "must not have multiple hard links" in result.stderr
    assert sentinel_bytes == b"repository-external sentinel"
    assert target_bytes == b"repository-external sentinel"


def test_generated_output_guard_writes_ordinary_file_atomically(tmp_path: Path):
    artifact_dir = (
        REPO_ROOT / "artifacts" / "ui-checks" / f"finish-atomic-{tmp_path.name}"
    )
    artifact_dir.mkdir(parents=True)
    target = artifact_dir / "verification-summary.json"

    try:
        result = run_output_guard_probe(
            "writeGeneratedFileAtomic(process.argv[1], Buffer.from('safe output'));",
            target,
        )
        contents = target.read_bytes() if target.exists() else b""
        leftovers = sorted(path.name for path in artifact_dir.iterdir())
    finally:
        shutil.rmtree(artifact_dir, ignore_errors=True)

    assert result.returncode == 0, result.stderr
    assert contents == b"safe output"
    assert leftovers == ["verification-summary.json"]


def test_verifier_contract_requires_exact_product_unit():
    result = run_contract_probe("VERIFICATION_CONTRACT.expectedLongProduct")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == (
        "Термоусадъчно полиетиленово фолио за групова транспортна опаковка "
        "850 / 0.060 мм"
    )


def test_verifier_contract_checks_long_values_and_sticky_scroll_at_both_viewports():
    result = run_contract_probe("VERIFICATION_CONTRACT.viewportCoverage")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        {
            "width": 1440,
            "height": 900,
            "checkLongOrderValues": True,
            "checkStableTableScroll": True,
        },
        {
            "width": 1366,
            "height": 768,
            "checkLongOrderValues": True,
            "checkStableTableScroll": True,
        },
    ]


def test_verifier_contract_preserves_exact_required_evidence_set():
    result = run_contract_probe("VERIFICATION_CONTRACT.screenshots")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        "active-normal-1440x900.png",
        "active-marked-empty-1366x768.png",
        "waiting-read-only-1440x900.png",
        "waiting-scrolled-1366x768.png",
        "waiting-validation-error-1366x768.png",
    ]


def test_exact_screenshot_postcondition_rejects_missing_reordered_or_wrong_dimensions():
    contract_url = VERIFIER_CONTRACT.resolve().as_uri()
    program = f"""
import {{
  VERIFICATION_CONTRACT,
  assertExactScreenshotEvidence,
}} from {json.dumps(contract_url)};
const prefix = "artifacts/ui-checks/order-finish-review";
const expectedDimensions = [
  [1440, 900],
  [1366, 768],
  [1440, 900],
  [1366, 768],
  [1366, 768],
];
const valid = {{
  screenshots: VERIFICATION_CONTRACT.screenshots.map((name) => `${{prefix}}/${{name}}`),
  screenshotDimensions: VERIFICATION_CONTRACT.screenshots.map((name, index) => ({{
    path: `${{prefix}}/${{name}}`,
    width: expectedDimensions[index][0],
    height: expectedDimensions[index][1],
  }})),
}};
assertExactScreenshotEvidence(valid);
const invalid = [
  {{ ...valid, screenshots: valid.screenshots.slice(0, 4) }},
  {{ ...valid, screenshots: [valid.screenshots[1], valid.screenshots[0], ...valid.screenshots.slice(2)] }},
  {{ ...valid, screenshotDimensions: valid.screenshotDimensions.map((entry, index) => (
    index === 0 ? {{ ...entry, width: 1439 }} : entry
  )) }},
];
let rejected = 0;
for (const candidate of invalid) {{
  try {{
    assertExactScreenshotEvidence(candidate);
  }} catch {{
    rejected += 1;
  }}
}}
console.log(JSON.stringify({{ rejected }}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", program],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"rejected": 3}
