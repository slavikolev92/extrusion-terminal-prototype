from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEPLOY_DIR = BASE_DIR / ".deploy"
REVISION_FILE = DEPLOY_DIR / "current_revision"


def deployment_metadata(revision_file: Path = REVISION_FILE) -> dict[str, str | None]:
    try:
        revision = revision_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        revision = ""

    return {"app_revision": revision or None}
