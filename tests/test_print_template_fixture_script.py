from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app import db
from app.printing import build_print_readiness


ROOT_DIR = Path(__file__).resolve().parent.parent


def run_fixture(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/create_print_template_fixture.py", *arguments],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def run_renderer(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "scripts/render_print_template.mjs", *arguments],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def test_print_template_fixture_rejects_db_path_outside_test_runtime(tmp_path):
    unsafe_db_path = tmp_path / "extrusion_terminal.sqlite3"
    unsafe_output_path = tmp_path / "fixture.json"

    result = run_fixture(
        "--db-path",
        str(unsafe_db_path),
        "--output",
        str(unsafe_output_path),
    )

    assert result.returncode != 0
    assert "must be under .test-runtime" in result.stderr
    assert not unsafe_db_path.exists()


def test_print_template_fixture_rejects_output_path_outside_test_runtime(tmp_path):
    runtime_dir = ROOT_DIR / ".test-runtime" / f"print-output-guard-{tmp_path.name}"
    fixture_db_path = runtime_dir / "fixture.sqlite3"
    unsafe_output_path = tmp_path / "fixture.json"

    try:
        result = run_fixture(
            "--db-path",
            str(fixture_db_path),
            "--output",
            str(unsafe_output_path),
        )

        assert result.returncode != 0
        assert "fixture output path must be under .test-runtime" in result.stderr
        assert not fixture_db_path.exists()
        assert not unsafe_output_path.exists()
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)


@pytest.mark.parametrize("target_name", ["fixture.sqlite3", "fixture.json"])
@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_print_template_fixture_rejects_linked_targets_without_touching_source(
    tmp_path,
    target_name,
    link_kind,
):
    runtime_dir = ROOT_DIR / ".test-runtime" / f"print-link-guard-{tmp_path.name}-{target_name}-{link_kind}"
    runtime_dir.mkdir(parents=True)
    source_path = tmp_path / target_name
    source_path.write_text("sentinel", encoding="utf-8")
    target_path = runtime_dir / target_name
    if link_kind == "symlink":
        target_path.symlink_to(source_path)
    else:
        os.link(source_path, target_path)
    database_path = runtime_dir / "fixture.sqlite3"
    output_path = runtime_dir / "fixture.json"

    try:
        result = run_fixture(
            "--db-path",
            str(database_path),
            "--output",
            str(output_path),
        )

        assert result.returncode != 0
        expected_error = (
            "must not be a symlink"
            if link_kind == "symlink"
            else "must not have multiple hard links"
        )
        assert expected_error in result.stderr
        assert source_path.read_text(encoding="utf-8") == "sentinel"
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)


def test_print_template_fixture_creates_all_print_boundary_scenarios(
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
    fixture_json_path = fixture_db_path.with_name("fixture.json")

    result = run_fixture(
        "--db-path",
        str(fixture_db_path),
        "--output",
        str(fixture_json_path),
        "--order-prefix",
        "PRINT-FIXTURE-TEST",
    )

    assert result.returncode == 0
    assert fixture_db_path.exists()
    assert fixture_json_path.exists()
    payload = json.loads(fixture_json_path.read_text(encoding="utf-8"))
    assert payload["scenario_order"] == [
        "no_weight",
        "page2_boundary",
        "first_overflow",
        "overflow_boundary",
        "orphan_total",
    ]
    expected_contract = {
        "no_weight": (2, "page2", 2, "40.03 кг"),
        "page2_boundary": (2, "page2", 7, "140.28 кг"),
        "first_overflow": (3, "overflow:1", 8, "160.36 кг"),
        "overflow_boundary": (3, "overflow:1", 46, "930.81 кг"),
        "orphan_total": (4, "overflow:2", 47, "951.28 кг"),
    }

    monkeypatch.setattr(db, "DATA_DIR", fixture_db_path.parent)
    monkeypatch.setattr(db, "DB_PATH", fixture_db_path)
    for scenario_name in payload["scenario_order"]:
        scenario = payload["scenarios"][scenario_name]
        expected_pages, expected_total, expected_rows, expected_gross = expected_contract[scenario_name]
        assert scenario == {
            "scenario": scenario_name,
            "card_id": scenario["card_id"],
            "order_number": f"PRINT-FIXTURE-TEST-{scenario_name.upper().replace('_', '-')}",
            "print_path": f"/cards/{scenario['card_id']}/print",
            "expected_page_count": expected_pages,
            "expected_total_placement": expected_total,
            "expected_pallet_row_count": expected_rows,
        }
        readiness = build_print_readiness(int(scenario["card_id"]))
        assert readiness.ok
        assert readiness.data is not None
        assert readiness.data["front"]["ordered_gross_display"] == expected_gross
        assert readiness.data["front"]["ordered_rolls_display"] == f"{expected_rows} ролки"
        assert len(readiness.data["roll_slots"]) == 120
        summary = readiness.data["pallet_summary"]
        assert summary is not None
        assert len(summary["rows"]) == expected_rows
        layout = readiness.data["pallet_summary_layout"]
        assert 2 + len(layout["overflow_tables"]) == expected_pages
        actual_total = (
            "page2"
            if layout["page2_table"] is not None
            else next(
                f"overflow:{index}"
                for index, table in enumerate(layout["overflow_tables"], start=1)
                if table["total"] is not None
            )
        )
        assert actual_total == expected_total

    no_weight = build_print_readiness(
        int(payload["scenarios"]["no_weight"]["card_id"])
    )
    assert no_weight.data is not None
    assert all(
        row["pallet_weight_display"] == "-"
        and row["gross_with_pallet_display"] == "-"
        for row in no_weight.data["pallet_summary"]["rows"]
    )


def test_print_template_renderer_rejects_output_dir_outside_ui_artifacts(tmp_path):
    unsafe_output_dir = tmp_path / "render-output"
    fixture_path = ROOT_DIR / ".test-runtime" / "missing-print-fixture.json"

    result = run_renderer(
        "--fixture-json",
        str(fixture_path),
        "--output-dir",
        str(unsafe_output_dir),
    )

    assert result.returncode != 0
    assert "render output dir must be under artifacts/ui-checks" in result.stderr
    assert not unsafe_output_dir.exists()


def test_print_template_renderer_rejects_output_dir_without_creating_outside_parent(
    tmp_path,
):
    unsafe_parent = tmp_path / "outside-parent"
    unsafe_output_dir = unsafe_parent / "render-output"
    fixture_path = ROOT_DIR / ".test-runtime" / "missing-print-fixture.json"

    result = run_renderer(
        "--fixture-json",
        str(fixture_path),
        "--output-dir",
        str(unsafe_output_dir),
    )

    assert result.returncode != 0
    assert "render output dir must be under artifacts/ui-checks" in result.stderr
    assert not unsafe_parent.exists()


def test_print_template_renderer_rejects_fixture_outside_test_runtime(tmp_path):
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text("{}", encoding="utf-8")
    output_dir = ROOT_DIR / "artifacts/ui-checks/print-fixture-outside"

    result = run_renderer(
        "--fixture-json",
        str(fixture_path),
        "--output-dir",
        str(output_dir),
    )

    assert result.returncode != 0
    assert "fixture JSON must be under .test-runtime" in result.stderr


def test_print_template_renderer_rejects_symlinked_output_directory(tmp_path):
    artifact_link = ROOT_DIR / "artifacts/ui-checks" / f"print-render-link-{tmp_path.name}"
    artifact_link.parent.mkdir(parents=True, exist_ok=True)
    artifact_link.symlink_to(tmp_path, target_is_directory=True)
    fixture_path = ROOT_DIR / ".test-runtime" / "missing-print-fixture.json"

    try:
        result = run_renderer(
            "--fixture-json",
            str(fixture_path),
            "--output-dir",
            str(artifact_link / "nested"),
        )

        assert result.returncode != 0
        assert "render output dir must be under artifacts/ui-checks" in result.stderr
        assert not (tmp_path / "nested").exists()
    finally:
        artifact_link.unlink(missing_ok=True)


@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_print_template_renderer_rejects_linked_fixture_json(tmp_path, link_kind):
    runtime_dir = ROOT_DIR / ".test-runtime" / f"print-render-fixture-link-{tmp_path.name}-{link_kind}"
    runtime_dir.mkdir(parents=True)
    source_path = tmp_path / "fixture.json"
    source_path.write_text("{}", encoding="utf-8")
    fixture_path = runtime_dir / "fixture.json"
    if link_kind == "symlink":
        fixture_path.symlink_to(source_path)
    else:
        os.link(source_path, fixture_path)
    output_dir = ROOT_DIR / "artifacts/ui-checks" / runtime_dir.name

    try:
        result = run_renderer(
            "--fixture-json",
            str(fixture_path),
            "--output-dir",
            str(output_dir),
        )

        assert result.returncode != 0
        assert "fixture JSON" in result.stderr
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)


@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_print_template_renderer_rejects_linked_summary_target(tmp_path, link_kind):
    runtime_dir = ROOT_DIR / ".test-runtime" / f"print-render-target-link-{tmp_path.name}-{link_kind}"
    artifact_dir = ROOT_DIR / "artifacts/ui-checks" / runtime_dir.name
    runtime_dir.mkdir(parents=True)
    artifact_dir.mkdir(parents=True)
    database_path = runtime_dir / "fixture.sqlite3"
    database_path.write_bytes(b"fixture")
    fixture_path = runtime_dir / "fixture.json"
    fixture_path.write_text(
        json.dumps({
            "db_path": str(database_path),
            "scenario_order": ["guard"],
            "scenarios": {
                "guard": {
                    "scenario": "guard",
                    "card_id": 1,
                    "expected_page_count": 2,
                    "expected_pallet_row_count": 1,
                    "expected_total_placement": "page2",
                }
            },
        }),
        encoding="utf-8",
    )
    source_path = tmp_path / "render-summary.json"
    source_path.write_text("sentinel", encoding="utf-8")
    target_path = artifact_dir / "render-summary.json"
    if link_kind == "symlink":
        target_path.symlink_to(source_path)
    else:
        os.link(source_path, target_path)

    try:
        result = run_renderer(
            "--fixture-json",
            str(fixture_path),
            "--output-dir",
            str(artifact_dir),
        )

        assert result.returncode != 0
        assert "render summary target" in result.stderr
        assert source_path.read_text(encoding="utf-8") == "sentinel"
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
        shutil.rmtree(artifact_dir, ignore_errors=True)
