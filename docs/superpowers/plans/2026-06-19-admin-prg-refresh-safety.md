# Admin PRG Refresh Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix audit findings #3 and #4 so successful admin import, release, and planning POSTs redirect to canonical GET pages and browser refresh cannot repeat those mutations.

**Architecture:** Use Post/Redirect/Get for successful admin mutations while preserving inline rendering for validation and stale-write failures. Persist import row-level results in SQLite so `/admin/import?batch_id=<id>` can reconstruct the post-import result after redirect without relying on in-memory POST state. Keep planning success feedback simple: redirect to `/admin/planning`; failed release/replanning continues to render `admin_planning.html` with the relevant `RuleResult`.

**Tech Stack:** Python 3.12, FastAPI, Jinja templates, direct `sqlite3`, SQLite schema migration via `CREATE TABLE IF NOT EXISTS`, pytest, repo-local `.venv`.

---

## Mandatory Session Instructions

- Start by reading `/home/sk/projects/extrusion-terminal/AGENTS.md` and follow it.
- Do not commit unless the user explicitly asks. This overrides generic Superpowers guidance about frequent commits.
- Do not use the existing `print-output` branch.
- Execute this plan with `superpowers:subagent-driven-development`: dispatch a fresh subagent per task, then perform spec-compliance review and code-quality review after each implementation task.
- Use TDD: write or update the focused failing tests first, run them and observe the expected failures, then edit production code.
- Do not implement audit bug #1, #5, #7, or #8 in this branch.
- Do not redesign planning UI labels or layout while fixing PRG.
- Do not add authentication, sessions, flash-message frameworks, background services, or client-side state mechanisms.
- Preserve existing stale-write behavior: stale or invalid admin writes should warn inline and require reload; only successful mutations should redirect.
- Preserve import overwrite conflict behavior from completed audit finding #2.
- Preserve paused-machine behavior from completed audit finding #6.

## Required Branch Preflight

This plan should be executed from the integrated base branch:

- `audit-fixes-integrated`

That branch was created from local `main` and contains both completed audit fixes:

- `eb8b574` (`Block stale import overwrites`)
- `a5e94ba` (`Fix paused machine occupancy`)

It also contains the integration merge commits:

- `7cdc936` (`Merge branch 'audit-fix-import-overwrite-conflicts' into audit-fixes-integrated`)
- `5cb3394` (`Merge branch 'audit-fix-paused-machine-occupancy' into audit-fixes-integrated`)

Before changing code, run:

```bash
git status --short --branch
git log --oneline --decorate -n 12
git branch --contains eb8b574
git branch --contains a5e94ba
```

Expected:

- Current branch is `audit-fixes-integrated`.
- Current branch contains both `eb8b574` and `a5e94ba`.
- Current branch contains merge commits `7cdc936` and `5cb3394`, unless the user has explicitly rebased or rebuilt the integration branch.
- Any unrelated untracked files remain untouched.

If the current branch is not `audit-fixes-integrated`, or if either completed fix commit is missing, stop and ask the user before making code changes. Do not silently build the PRG work on a branch that lacks the completed import-overwrite or paused-machine fixes.

## Background

Report: `reports/full-workflow-audit-20260618.md`

Completed findings already marked in the report:

- `#2 High - Import Overwrite Silently Replaces Admin-Corrected Front-Card Fields`
- `#6 High - Paused Card Blocks Starting Another Card On The Same Machine`

Findings this plan addresses:

- `#3 Important - /admin/import POST Is Repeatable By Browser Refresh`
- `#4 Medium - Planning Release/Replanning POSTs Do Not Use PRG`

Observed route behavior before this plan:

```text
/admin/import                 -> 200 TemplateResponse, no Location
/admin/cards/{id}/release     -> 200 TemplateResponse, no Location
/admin/cards/{id}/planning    -> 200 TemplateResponse, no Location
```

Working patterns already present:

- `app/main.py::admin_card_post_response()` redirects successful admin detail POSTs to `/admin/cards/{card_id}` or an anchored section.
- `app/main.py::terminal_post_response()` redirects successful terminal POSTs to `/terminal/cards/{card_id}`.
- Failed admin and terminal actions render inline with the error `RuleResult`.

Important import-specific context:

- `app/templates/admin_import.html` currently displays detailed `import_result.row_results`.
- `import_batches` persists only import summary data before this plan.
- To redirect after successful import without losing row-level feedback, this plan adds persisted import batch rows and reconstructs `import_result` on GET.

## Files And Responsibilities

- Modify `app/db.py`
  - Add `import_batch_rows` schema.
  - Add helpers to insert import row results.
  - Add helper to reconstruct an import result for a selected import batch.

- Modify `app/importer.py`
  - Record each per-row import result in memory and, when a batch exists, in SQLite.
  - Preserve existing conflict-blocking behavior from `STALE_IMPORT_MESSAGE`.
  - Preserve no-batch inline failure behavior for missing header / missing required-column uploads.

- Modify `app/main.py`
  - Load selected import batch result on GET `/admin/import?batch_id=<id>`.
  - Redirect successful import POSTs to `/admin/import?batch_id={result.batch_id}`.
  - Keep non-persisted import failures inline.
  - Redirect successful release and planning POSTs to `/admin/planning`.
  - Keep failed release and planning POSTs inline.

- Modify `tests/test_baseline.py`
  - Add backend coverage for persisted import batch row results.

- Modify `tests/test_admin_routes.py`
  - Add route-level PRG tests for import, release, and planning.
  - Add failure-path tests proving invalid/stale routes still render inline.

- Modify `reports/full-workflow-audit-20260618.md`
  - After implementation and verification, mark findings #3 and #4 completed with the final commit hash if the user approves a commit, or with the branch name if no commit is requested.

- Do not modify templates or CSS unless a failing test proves a direct template change is necessary.
- Do not modify print files.

---

## Task 1: Confirm Context And Add Persisted Import Result Tests

**Files:**

- Modify: `tests/test_baseline.py`
- Read-only context: `app/db.py`, `app/importer.py`, `app/templates/admin_import.html`, `reports/full-workflow-audit-20260618.md`

- [ ] **Step 1: Read required context**

Run:

```bash
cat AGENTS.md
sed -n '180,208p;208,239p' reports/full-workflow-audit-20260618.md
sed -n '40,75p;2850,2945p' app/db.py
sed -n '90,310p' app/importer.py
sed -n '1,120p' app/templates/admin_import.html
sed -n '1,390p' tests/test_baseline.py
```

Expected:

- `AGENTS.md` confirms no commit unless asked.
- Report findings #3 and #4 describe repeatable successful POSTs.
- `app/importer.py` contains `ImportRowResult`, `ImportResult`, `STALE_IMPORT_MESSAGE`, `block_import_row()`, and import overwrite conflict logic.
- `app/templates/admin_import.html` expects `import_result.row_results`.
- No persisted import row result table exists yet.

- [ ] **Step 2: Add failing backend test for persisted import batch rows**

In `tests/test_baseline.py`, add this test after `test_overwrite_import_blocks_stale_row_without_blocking_other_rows` if that test exists; otherwise add it after the existing overwrite-import tests:

```python
def test_import_batch_result_reconstructs_processed_rows_after_redirect(connection):
    result = import_cards_from_csv(
        "route-result.csv",
        csv_bytes(
            extrusion_row("25296"),
            extrusion_row(
                "32999",
                extrusion_flag="не",
                raw_material_a="",
                packaging_method="",
            ),
        ),
        overwrite_existing=False,
    )

    detail = db.fetch_import_batch_result(result.batch_id)

    assert result.batch_id is not None
    assert detail is not None
    assert detail["batch_id"] == result.batch_id
    assert detail["filename"] == "route-result.csv"
    assert detail["rows_seen"] == 2
    assert detail["rows_imported"] == 1
    assert detail["created"] == 1
    assert detail["updated"] == 0
    assert detail["skipped"] == 1
    assert [row["row_number"] for row in detail["row_results"]] == [2, 3]
    assert [row["order_number"] for row in detail["row_results"]] == ["25296", "32999"]
    assert [row["action"] for row in detail["row_results"]] == ["created", "skipped"]
    assert detail["row_results"][0]["message"] == (
        "Създадена нова технологична карта; готова за планиране."
    )
    assert detail["row_results"][1]["message"] == "Пропуснат ред: няма екструдиране."
    assert "Ред 3: Пропуснат ред: няма екструдиране." in detail["row_errors"]
```

- [ ] **Step 3: Add failing backend test for persisted blocked import rows**

In `tests/test_baseline.py`, add this test immediately after the previous new test:

```python
def test_import_batch_result_persists_blocked_stale_overwrite_rows(connection):
    card_id = import_one_ready_card("25297")
    fields = current_import_fields(connection, card_id)
    fields["city"] = "Corrected City"
    card = db.fetch_admin_card_detail(card_id)
    assert db.update_admin_imported_fields(card_id, card["version"], fields).ok

    result = import_cards_from_csv(
        "blocked-result.csv",
        csv_bytes(extrusion_row("25297")),
        overwrite_existing=True,
    )

    detail = db.fetch_import_batch_result(result.batch_id)

    assert result.batch_id is not None
    assert detail is not None
    assert detail["rows_seen"] == 1
    assert detail["rows_imported"] == 0
    assert detail["created"] == 0
    assert detail["updated"] == 0
    assert detail["skipped"] == 1
    assert len(detail["row_results"]) == 1
    assert detail["row_results"][0]["row_number"] == 2
    assert detail["row_results"][0]["order_number"] == "25297"
    assert detail["row_results"][0]["action"] == "blocked"
    assert "администратор" in detail["row_results"][0]["message"].casefold()
    assert "Ред 2:" in detail["row_errors"][0]
```

- [ ] **Step 4: Run tests and verify red**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py -k "import_batch_result_reconstructs_processed_rows_after_redirect or import_batch_result_persists_blocked_stale_overwrite_rows"
```

Expected before implementation:

- Both tests fail because `app.db.fetch_import_batch_result` does not exist.

Do not edit production code until this red state is observed.

---

## Task 2: Persist Import Row Results And Reconstruct Import Batch Detail

**Files:**

- Modify: `app/db.py`
- Modify: `app/importer.py`
- Test: `tests/test_baseline.py`

- [ ] **Step 1: Add import batch row schema**

In `app/db.py`, add this table immediately after `CREATE TABLE IF NOT EXISTS import_batches`:

```python
CREATE TABLE IF NOT EXISTS import_batch_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL CHECK (display_order >= 1),
    row_number INTEGER,
    order_number TEXT,
    action TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Add this index near the other import-related indexes:

```python
CREATE INDEX IF NOT EXISTS idx_import_batch_rows_batch_order
ON import_batch_rows(import_batch_id, display_order, id);
```

- [ ] **Step 2: Add import row persistence helpers**

In `app/db.py`, add these helpers near `fetch_recent_import_batches()`:

```python
def insert_import_batch_row(
    connection: sqlite3.Connection,
    import_batch_id: int,
    display_order: int,
    row_number: int | None,
    order_number: str,
    action: str,
    message: str,
) -> None:
    connection.execute(
        """
        INSERT INTO import_batch_rows (
            import_batch_id,
            display_order,
            row_number,
            order_number,
            action,
            message
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            import_batch_id,
            display_order,
            row_number,
            order_number,
            action,
            message,
        ),
    )


def fetch_import_batch_result(batch_id: int | None) -> dict[str, Any] | None:
    if batch_id is None:
        return None

    with connect() as connection:
        batch = connection.execute(
            """
            SELECT id, source_filename, rows_seen, rows_imported
            FROM import_batches
            WHERE id = ?
            """,
            (batch_id,),
        ).fetchone()
        if batch is None:
            return None

        rows = rows_to_dicts(
            connection.execute(
                """
                SELECT row_number, order_number, action, message
                FROM import_batch_rows
                WHERE import_batch_id = ?
                ORDER BY display_order, id
                """,
                (batch_id,),
            ).fetchall()
        )

    created = sum(1 for row in rows if row["action"] == "created")
    updated = sum(1 for row in rows if row["action"] == "updated")
    skipped = sum(1 for row in rows if row["action"] in ("skipped", "blocked"))
    duplicate_rows = [
        str(row["order_number"] or "")
        for row in rows
        if row["action"] == "skipped" and str(row["order_number"] or "")
    ]
    row_errors = [
        format_import_row_error(row)
        for row in rows
        if row["action"] in ("skipped", "blocked")
    ]

    return {
        "batch_id": int(batch["id"]),
        "filename": str(batch["source_filename"] or ""),
        "rows_seen": int(batch["rows_seen"] or 0),
        "rows_imported": int(batch["rows_imported"] or 0),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "duplicate_rows": duplicate_rows,
        "row_errors": row_errors,
        "row_results": rows,
    }


def format_import_row_error(row: dict[str, Any]) -> str:
    row_number = row.get("row_number")
    message = str(row.get("message") or "")
    prefix = f"Ред {row_number}: " if row_number is not None else ""
    return f"{prefix}{message}".strip()
```

- [ ] **Step 3: Wire importer row recording through one helper**

In `app/importer.py`, change the import from `app.db` so it includes `insert_import_batch_row`:

```python
from .db import connect, insert_import_batch_row
```

Add this helper after the `ImportResult` dataclass:

```python
def record_import_row_result(
    result: ImportResult,
    row_number: int | None,
    order_number: str,
    action: str,
    message: str,
    connection: Any | None = None,
) -> None:
    row_result = ImportRowResult(
        row_number=row_number,
        order_number=order_number,
        action=action,
        message=message,
    )
    result.row_results.append(row_result)
    if connection is not None and result.batch_id is not None:
        insert_import_batch_row(
            connection,
            int(result.batch_id),
            len(result.row_results),
            row_number,
            order_number,
            action,
            message,
        )
```

Replace each direct append of an `ImportRowResult` object in `import_cards_from_csv()` with the `record_import_row_result` calls shown below.

Use these exact calls:

```python
record_import_row_result(result, None, "", "blocked", message)
```

```python
record_import_row_result(result, row_number, "", "skipped", message, connection)
```

```python
record_import_row_result(result, row_number, order_number, "skipped", message, connection)
```

```python
record_import_row_result(result, row_number, order_number, action, message, connection)
```

Then update `block_import_row()` to accept the optional connection and use the same helper:

```python
def block_import_row(
    result: ImportResult,
    row_number: int,
    order_number: str,
    message: str,
    connection: Any | None = None,
) -> None:
    result.skipped += 1
    result.row_errors.append(f"Ред {row_number}: {message} {order_number}.")
    record_import_row_result(
        result,
        row_number,
        order_number,
        "blocked",
        message,
        connection,
    )
```

Update both stale-overwrite call sites to pass `connection`:

```python
block_import_row(result, row_number, order_number, STALE_IMPORT_MESSAGE, connection)
```

- [ ] **Step 4: Run focused backend tests and verify green**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py -k "import_batch_result_reconstructs_processed_rows_after_redirect or import_batch_result_persists_blocked_stale_overwrite_rows"
```

Expected:

- Both selected tests pass.

- [ ] **Step 5: Run import baseline tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py -k "import or overwrite"
```

Expected:

- Existing import and overwrite tests still pass.
- Completed audit finding #2 behavior remains intact.

---

## Task 3: Add `/admin/import` PRG While Preserving Result Review

**Files:**

- Modify: `tests/test_admin_routes.py`
- Modify: `app/main.py`
- Test: `tests/test_admin_routes.py`

- [ ] **Step 1: Add route-test helpers**

In `tests/test_admin_routes.py`, update imports:

```python
import asyncio
from tempfile import SpooledTemporaryFile

from starlette.datastructures import UploadFile
from starlette.requests import Request

from app import db
from app.importer import import_cards_from_csv
from app.main import (
    admin,
    admin_import,
    admin_planning,
    app,
    import_csv as post_admin_import,
)
from tests.test_admin_planning import csv_bytes, extrusion_row
```

Add these helpers after `test_admin_redirects_to_import()`:

```python
def make_request(path: str, method: str = "POST") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
            "app": app,
        }
    )


def upload_file(filename: str, content: bytes) -> UploadFile:
    file = SpooledTemporaryFile()
    file.write(content)
    file.seek(0)
    return UploadFile(file=file, filename=filename)
```

- [ ] **Step 2: Add failing import PRG test**

In `tests/test_admin_routes.py`, add:

```python
def test_successful_admin_import_redirects_to_batch_result_get(connection):
    content = csv_bytes(
        extrusion_row("25901"),
        extrusion_row(
            "31999",
            extrusion_flag="не",
            raw_material_a="",
            packaging_method="",
        ),
    )

    response = asyncio.run(
        post_admin_import(
            make_request("/admin/import"),
            csv_file=upload_file("route-import.csv", content),
            overwrite_existing=False,
        )
    )

    batches_after_post = connection.execute(
        "SELECT COUNT(*) FROM import_batches"
    ).fetchone()[0]
    location = response.headers.get("location", "")
    batch_id = int(location.rsplit("=", 1)[1])

    get_response = asyncio.run(
        admin_import(
            make_request("/admin/import", method="GET"),
            batch_id=batch_id,
        )
    )
    refresh_response = asyncio.run(
        admin_import(
            make_request("/admin/import", method="GET"),
            batch_id=batch_id,
        )
    )
    batches_after_get_refresh = connection.execute(
        "SELECT COUNT(*) FROM import_batches"
    ).fetchone()[0]
    html = get_response.body.decode("utf-8")

    assert response.status_code == 303
    assert location == f"/admin/import?batch_id={batch_id}"
    assert get_response.status_code == 200
    assert refresh_response.status_code == 200
    assert batches_after_post == 1
    assert batches_after_get_refresh == 1
    assert "Резултат от импорта:" in html
    assert "route-import.csv" in html
    assert "25901" in html
    assert "31999" in html
    assert "Пропуснат ред: няма екструдиране." in html
```

- [ ] **Step 3: Add failing inline invalid import test**

In `tests/test_admin_routes.py`, add:

```python
def test_admin_import_without_persisted_batch_still_renders_inline(connection):
    response = asyncio.run(
        post_admin_import(
            make_request("/admin/import"),
            csv_file=upload_file("missing-required.csv", b"order_number\n25902\n"),
            overwrite_existing=False,
        )
    )
    batch_count = connection.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "location" not in response.headers
    assert batch_count == 0
    assert "Липсват задължителни CSV колони" in html
```

- [ ] **Step 4: Run route tests and verify red**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -k "successful_admin_import_redirects_to_batch_result_get or admin_import_without_persisted_batch_still_renders_inline"
```

Expected before implementation:

- The successful import PRG test fails because the POST returns `200` with no `Location`.
- The inline invalid import test may already pass; if it passes, keep it as regression coverage.

- [ ] **Step 5: Implement import GET reconstruction and POST redirect**

In `app/main.py`, add `fetch_import_batch_result` to the `.db` import list.

Change the GET route signature and context:

```python
@app.get("/admin/import")
async def admin_import(request: Request, batch_id: int | None = None):
    import_result = fetch_import_batch_result(batch_id)
    return templates.TemplateResponse(
        request,
        "admin_import.html",
        admin_import_context(
            import_result=import_result,
            import_action_labels=IMPORT_ACTION_LABELS,
        ),
    )
```

Change the POST route return:

```python
    if result.batch_id is not None:
        return RedirectResponse(
            url=f"/admin/import?batch_id={result.batch_id}",
            status_code=303,
        )

    return templates.TemplateResponse(
        request,
        "admin_import.html",
        admin_import_context(import_result=result, import_action_labels=IMPORT_ACTION_LABELS),
    )
```

- [ ] **Step 6: Run focused import route tests and verify green**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -k "successful_admin_import_redirects_to_batch_result_get or admin_import_without_persisted_batch_still_renders_inline"
```

Expected:

- Both selected tests pass.

- [ ] **Step 7: Run import and route tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py tests/test_baseline.py
```

Expected:

- All selected tests pass.

---

## Task 4: Add Release And Planning PRG

**Files:**

- Modify: `tests/test_admin_routes.py`
- Modify: `app/main.py`
- Test: `tests/test_admin_routes.py`, `tests/test_admin_planning.py`

- [ ] **Step 1: Add route imports for planning handlers**

In `tests/test_admin_routes.py`, extend the `app.main` import block so it includes:

```python
    release_card_to_terminal,
    update_admin_card_planning,
```

- [ ] **Step 2: Add helper for route card setup**

In `tests/test_admin_routes.py`, add:

```python
def import_route_card(order_number: str) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number)),
        overwrite_existing=False,
    )
    assert result.rows_imported == 1
    with db.connect() as connection:
        return int(
            connection.execute(
                "SELECT id FROM cards WHERE order_number = ?",
                (order_number,),
            ).fetchone()["id"]
        )


def card_version(card_id: int) -> int:
    return int(db.fetch_admin_card_detail(card_id)["version"])
```

- [ ] **Step 3: Add failing release PRG test**

In `tests/test_admin_routes.py`, add:

```python
def test_successful_release_redirects_to_planning_get_and_refresh_does_not_resubmit(connection):
    card_id = import_route_card("25910")
    loaded_version = card_version(card_id)

    response = asyncio.run(
        release_card_to_terminal(
            make_request(f"/admin/cards/{card_id}/release"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            max_roll_weight="60.0",
            machine_id="1",
            machine_sequence="1",
        )
    )
    after_release = db.fetch_admin_card_detail(card_id)
    refresh_response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    after_refresh = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/planning"
    assert refresh_response.status_code == 200
    assert after_release["status"] == "pending"
    assert after_release["machine_id"] == 1
    assert after_release["machine_sequence"] == 1
    assert after_refresh["version"] == after_release["version"]
    assert after_refresh["machine_id"] == 1
    assert after_refresh["machine_sequence"] == 1
```

- [ ] **Step 4: Add failing planning PRG test**

In `tests/test_admin_routes.py`, add:

```python
def test_successful_replanning_redirects_to_planning_get_and_refresh_does_not_resubmit(connection):
    card_id = import_route_card("25911")
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    loaded_version = card_version(card_id)

    response = asyncio.run(
        update_admin_card_planning(
            make_request(f"/admin/cards/{card_id}/planning"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            machine_id="2",
            machine_sequence="1",
        )
    )
    after_planning = db.fetch_admin_card_detail(card_id)
    refresh_response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    after_refresh = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/planning"
    assert refresh_response.status_code == 200
    assert after_planning["machine_id"] == 2
    assert after_planning["machine_sequence"] == 1
    assert after_refresh["version"] == after_planning["version"]
    assert after_refresh["machine_id"] == 2
    assert after_refresh["machine_sequence"] == 1
```

- [ ] **Step 5: Add failure-path route tests**

In `tests/test_admin_routes.py`, add:

```python
def test_failed_release_and_planning_still_render_inline_without_redirect(connection):
    card_id = import_route_card("25912")
    stale_version = card_version(card_id)
    fields = {
        field: str(db.fetch_admin_card_detail(card_id)[field] or "")
        for field in db.CARD_IMPORT_SOURCE_FIELDS
    }
    fields["customer"] = "Changed Before Release"
    assert db.update_admin_imported_fields(card_id, stale_version, fields).ok

    stale_release = asyncio.run(
        release_card_to_terminal(
            make_request(f"/admin/cards/{card_id}/release"),
            card_id=card_id,
            loaded_version=str(stale_version),
            max_roll_weight="60.0",
            machine_id="1",
            machine_sequence="1",
        )
    )
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    invalid_planning = asyncio.run(
        update_admin_card_planning(
            make_request(f"/admin/cards/{card_id}/planning"),
            card_id=card_id,
            loaded_version=str(card_version(card_id)),
            machine_id="1",
            machine_sequence="0",
        )
    )

    assert stale_release.status_code == 200
    assert "location" not in stale_release.headers
    assert "release_result" in stale_release.context
    assert stale_release.context["release_result"].messages == (db.STALE_CARD_MESSAGE,)
    assert invalid_planning.status_code == 200
    assert "location" not in invalid_planning.headers
    assert "planning_result" in invalid_planning.context
    assert invalid_planning.context["planning_result"].messages == (
        "Редът трябва да е 1 или по-голям.",
    )
```

- [ ] **Step 6: Run route tests and verify red**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -k "successful_release_redirects_to_planning_get_and_refresh_does_not_resubmit or successful_replanning_redirects_to_planning_get_and_refresh_does_not_resubmit or failed_release_and_planning_still_render_inline_without_redirect"
```

Expected before implementation:

- Success tests fail because release and planning return `200` with no `Location`.
- Failure-path test should pass before implementation; keep it as guard coverage.

- [ ] **Step 7: Implement release/planning redirects on success only**

In `app/main.py`, update `release_card_to_terminal()` after calculating `release_result`:

```python
    if release_result.ok:
        return RedirectResponse(url="/admin/planning", status_code=303)

    return templates.TemplateResponse(
        request,
        "admin_planning.html",
        admin_planning_context(release_result=release_result),
    )
```

Update `update_admin_card_planning()` after calculating `planning_result`:

```python
    if planning_result.ok:
        return RedirectResponse(url="/admin/planning", status_code=303)

    return templates.TemplateResponse(
        request,
        "admin_planning.html",
        admin_planning_context(planning_result=planning_result),
    )
```

- [ ] **Step 8: Run focused route tests and verify green**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -k "successful_release_redirects_to_planning_get_and_refresh_does_not_resubmit or successful_replanning_redirects_to_planning_get_and_refresh_does_not_resubmit or failed_release_and_planning_still_render_inline_without_redirect"
```

Expected:

- All selected tests pass.

- [ ] **Step 9: Run planning tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py tests/test_admin_planning.py
```

Expected:

- Route tests pass.
- Existing planning backend tests pass.

---

## Task 5: Update Audit Report Status And Run Required Verification

**Files:**

- Modify: `reports/full-workflow-audit-20260618.md`
- Verify: `tests/test_admin_routes.py`
- Verify: `tests/test_admin_planning.py`
- Verify: `tests/test_baseline.py`
- Verify: full suite
- Verify: `app`

- [ ] **Step 1: Mark findings #3 and #4 complete in the report**

In `reports/full-workflow-audit-20260618.md`, add a status line below each heading:

For finding #3:

```markdown
Status: **completed** in the admin PRG refresh-safety branch. Successful import POSTs redirect to `/admin/import?batch_id=<id>`; refreshing the GET result does not repeat the upload.
```

For finding #4:

```markdown
Status: **completed** in the admin PRG refresh-safety branch. Successful release and replanning POSTs redirect to `/admin/planning`; failed writes still render inline.
```

If the user later approves a commit, update these lines with the final commit hash before committing.

- [ ] **Step 2: Run focused route/import/planning tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py tests/test_admin_planning.py tests/test_baseline.py
```

Expected:

- All selected tests pass.

- [ ] **Step 3: Run related workflow tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py tests/test_admin_production_corrections.py tests/test_terminal_v8_render.py
```

Expected:

- Existing PRG and stale-write behavior still passes.

- [ ] **Step 4: Run full test suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected:

- Full suite passes.

- [ ] **Step 5: Run syntax/import checks**

Run:

```bash
source .venv/bin/activate
python -m compileall app
```

Expected:

- Command exits 0.

- [ ] **Step 6: Run whitespace diff check**

Run:

```bash
git diff --check
```

Expected:

- Command exits 0 with no output.

- [ ] **Step 7: Inspect final diff for scope**

Run:

```bash
git diff --stat
git diff -- app/db.py app/importer.py app/main.py tests/test_baseline.py tests/test_admin_routes.py reports/full-workflow-audit-20260618.md
git status --short --branch
```

Expected:

- Tracked implementation changes are limited to:
  - `app/db.py`
  - `app/importer.py`
  - `app/main.py`
  - `tests/test_baseline.py`
  - `tests/test_admin_routes.py`
  - `reports/full-workflow-audit-20260618.md`
- No print, cancellation, unrelease, planning UI redesign, template/CSS, or unrelated audit bug changes are present.
- Any pre-existing unrelated untracked files remain untracked and untouched.

- [ ] **Step 8: Decide whether Playwright is required**

Playwright is not required if the change remains backend route behavior, database persistence, tests, and report status only.

If templates, CSS, or visible UI layout changed unexpectedly, stop and either revert those unrelated UI changes or run the live FastAPI app and capture a focused Playwright screenshot under `artifacts/ui-checks/`.

---

## Expected Final Behavior Checklist

Verify each item against tests or code before final response:

- [ ] Successful `/admin/import` POST returns `303`.
- [ ] Successful `/admin/import` POST redirects to `/admin/import?batch_id=<id>`.
- [ ] GET `/admin/import?batch_id=<id>` shows the import summary and processed row table.
- [ ] Refreshing GET `/admin/import?batch_id=<id>` does not insert another `import_batches` row.
- [ ] Missing-header or missing-required-column import failures still render inline without redirect because no import batch was persisted.
- [ ] Import overwrite conflict rows from finding #2 still block stale source overwrites.
- [ ] Blocked/skipped import rows appear in reconstructed batch result.
- [ ] Successful `/admin/cards/{id}/release` POST returns `303` to `/admin/planning`.
- [ ] Refreshing `/admin/planning` after release does not resubmit release.
- [ ] Successful `/admin/cards/{id}/planning` POST returns `303` to `/admin/planning`.
- [ ] Refreshing `/admin/planning` after replanning does not resubmit replanning.
- [ ] Failed release writes still render inline with `release_result`.
- [ ] Failed planning writes still render inline with `planning_result`.
- [ ] Existing admin detail POST PRG behavior remains unchanged.
- [ ] No unrelated audit bug is included.

## Final Response Guidance

In the final response:

- State the branch name.
- State that no commit was made unless the user explicitly asked for one.
- Summarize changed files in one short list.
- Include exact verification commands and pass/fail status.
- Mention that Playwright was not run if no UI/template/CSS files changed.
- Mention any pre-existing untracked files that remain untouched.

Do not say “done” or “fixed” unless the verification commands above have passed in the current execution session.

## Self-Review Of This Plan

Spec coverage:

- Audit finding #3 is covered by persisted import row result tests, import POST redirect, GET reconstruction, and refresh-safe batch count assertions.
- Audit finding #4 is covered by release/replanning route tests that require `303` redirects on success and inline render on failure.
- Existing successful PRG patterns are preserved by reusing `RedirectResponse(status_code=303)` rather than introducing a new framework.
- Existing stale-write behavior is protected by explicit failure-path tests.
- Import overwrite conflict behavior from finding #2 is protected by a blocked-row reconstruction test.

Undefined-marker scan:

- No undefined implementation markers are present.
- Each code-changing task includes concrete code snippets and exact commands.
- No task asks the implementer to design an unspecified mechanism.

Type/signature consistency:

- `fetch_import_batch_result(batch_id: int | None) -> dict[str, Any] | None` is used by `admin_import()`.
- `insert_import_batch_row()` accepts primitive row result values and avoids importing `ImportRowResult` into `app/db.py`.
- `record_import_row_result()` keeps `ImportResult.row_results` in memory while persisting rows when `result.batch_id` exists.
- Route tests use direct route-function calls because this repo does not currently have `httpx2` installed for `fastapi.testclient`.
