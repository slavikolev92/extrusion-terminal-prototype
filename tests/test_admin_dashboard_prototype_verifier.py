from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER_SCRIPT = REPO_ROOT / "ui-prototypes" / "verify-admin-machine-time-dashboard.mjs"


def test_dashboard_prototype_verifier_skips_optional_visual_comparison():
    environment = os.environ.copy()
    environment.pop("DASHBOARD_SOURCE_VISUAL", None)

    result = subprocess.run(
        ["node", str(VERIFIER_SCRIPT)],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (
        "Skipped visual comparison: DASHBOARD_SOURCE_VISUAL is not set."
        in result.stdout
    )
