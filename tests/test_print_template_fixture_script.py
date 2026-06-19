from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app import db
from app.printing import build_print_readiness


ROOT_DIR = Path(__file__).resolve().parent.parent

def test_print_template_fixture_rejects_db_path_outside_test_runtime(tmp_path):
    unsafe_db_path = tmp_path / "extrusion_terminal.sqlite3"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/create_print_template_fixture.py",
            "--db-path",
            str(unsafe_db_path),
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "must be under .test-runtime" in result.stderr
    assert not unsafe_db_path.exists()


def test_print_template_fixture_creates_completed_printable_temp_card(
    monkeypatch,
    tmp_path,
):
    runtime_name = tmp_path.name
    fixture_db_path = (
        ROOT_DIR
        / ".test-runtime"
        / f"print-template-fixture-test-{runtime_name}"
        / "extrusion_terminal.sqlite3"
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/create_print_template_fixture.py",
            "--db-path",
            str(fixture_db_path),
            "--order-number",
            "PRINT-FIXTURE-TEST",
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert fixture_db_path.exists()

    monkeypatch.setattr(db, "DATA_DIR", fixture_db_path.parent)
    monkeypatch.setattr(db, "DB_PATH", fixture_db_path)
    with db.connect() as connection:
        card_id = int(
            connection.execute(
                "SELECT id FROM cards WHERE order_number = ?",
                ("PRINT-FIXTURE-TEST",),
            ).fetchone()["id"]
        )
    readiness = build_print_readiness(card_id)

    assert readiness.ok
    assert readiness.data is not None
    assert readiness.data["front"]["order_number"] == "PRINT-FIXTURE-TEST"
    assert len(readiness.data["roll_slots"]) == 120
    for row in readiness.data["front"]["recipe_rows"]:
        assert row["planned_material"]
        assert row["actual_material_used"]
        assert row["batch_lot"]


def test_print_template_renderer_rejects_output_dir_outside_ui_artifacts(tmp_path):
    unsafe_output_dir = tmp_path / "render-output"

    result = subprocess.run(
        [
            "node",
            "scripts/render_print_template.mjs",
            "--card-id",
            "1",
            "--output-dir",
            str(unsafe_output_dir),
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "render output dir must be under artifacts/ui-checks" in result.stderr
    assert not unsafe_output_dir.exists()


def test_print_template_renderer_rejects_output_dir_without_creating_outside_parent(
    tmp_path,
):
    unsafe_parent = tmp_path / "outside-parent"
    unsafe_output_dir = unsafe_parent / "render-output"

    result = subprocess.run(
        [
            "node",
            "scripts/render_print_template.mjs",
            "--card-id",
            "1",
            "--output-dir",
            str(unsafe_output_dir),
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "render output dir must be under artifacts/ui-checks" in result.stderr
    assert not unsafe_parent.exists()
