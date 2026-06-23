# Admin Archive Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the shift-manager finalization step where workstation-finished cards are labeled `Произведена`, admin-finalized cards are labeled `Завършена`, and printing/finalization actions live only on the admin card detail page.

**Architecture:** Keep the existing `completed` database status as the workstation finish state, relabel it to `Произведена`, and add a new `archived` status for the admin final state shown as `Завършена`. Use small shared status tuples for printable and production-complete behavior so print/correction rules include both `completed` and `archived`, while the workstation archive drawer continues to show only `completed` cards. Add a narrow SQLite schema migration because existing pilot databases have a `cards.status` CHECK constraint that will reject the new status until the table is rebuilt.

**Tech Stack:** FastAPI, Jinja2 templates, direct `sqlite3`, SQLite CHECK constraints, pytest, repo-local Playwright for UI verification.

---

## Repository Rules For Execution

- Work in `/home/sk/projects/extrusion-terminal`.
- Follow `AGENTS.md`.
- Use the repo-local virtualenv: `source .venv/bin/activate`.
- Do not mutate `data/extrusion_terminal.sqlite3` in tests or UI checks.
- Use temporary SQLite paths under `.test-runtime/`.
- Save UI screenshots under `artifacts/ui-checks/`.
- Do not stage or commit unless the user explicitly asks.
- This plan changes workflow status behavior only. Do not change print template layout, workbook import behavior, timing math, roll calculations, or workstation machine-state colors.

## Confirmed Behavior

- Workstation finish still sets internal status `completed`.
- Internal `completed` is shown as `Произведена`.
- Add internal status `archived`, shown as `Завършена`.
- Admin card detail shows `Печат / препечат` for `completed` and `archived`.
- Admin card detail shows `Маркирай като завършена` only for `completed`.
- Clicking print never changes status.
- Clicking `Маркирай като завършена` changes `completed` to `archived`.
- `archived` cards stay visible in admin, editable, correctable, and reprintable.
- No return/reopen workflow is added.
- The admin card table remains search/navigation only; remove the table print shortcut.
- Remove the print action from the workstation terminal entirely.
- Workstation completed-card drawer is renamed to `Произведени поръчки` and still shows only `completed` cards.
- Workstation colors stay unchanged. Admin/global status colors change so `completed` is blue and `archived` is green.

## Files

- Modify: `app/constants.py`
  - Add `STATUS_ARCHIVED`.
  - Relabel `STATUS_COMPLETED` to `Произведена`.
  - Add `STATUS_ARCHIVED: "Завършена"`.
  - Add shared tuples for printable and production-complete statuses.
  - Keep `TERMINAL_ARCHIVE_STATUSES` as completed-only.
- Modify: `app/db.py`
  - Import `STATUS_ARCHIVED` and new tuples.
  - Split the cards table DDL so it can be reused for schema migration.
  - Add a migration helper that rebuilds `cards` when the existing CHECK constraint lacks `archived`.
  - Add `archive_completed_card(card_id, loaded_version)`.
  - Update production-complete checks from completed-only to completed-or-archived where preserving print/correction invariants matters.
  - Keep finish behavior writing `STATUS_COMPLETED`.
- Modify: `app/printing.py`
  - Allow print readiness for both `completed` and `archived`.
  - Update blocked-print message to mention produced or finalized cards.
- Modify: `app/main.py`
  - Import and route `archive_completed_card`.
  - Add `POST /admin/cards/{card_id}/archive`.
  - Keep print route as read-only status-wise.
- Modify: `app/templates/admin_card_detail.html`
  - Show admin print link for `completed` and `archived`.
  - Add `Маркирай като завършена` form for `completed`.
  - Do not add any return/reopen control.
- Modify: `app/templates/admin_cards.html`
  - Remove the table-level print shortcut.
- Modify: `app/templates/terminal.html`
  - Rename workstation history UI from `Завършени поръчки` to `Произведени поръчки`.
  - Remove terminal print/reprint action and link.
  - Keep roll correction menu behavior for produced cards.
  - Keep workstation status colors unchanged.
- Modify: `app/static/css/app.css`
  - Change admin/global `completed` pill color variables to blue.
  - Add `archived` pill variables/rules in green.
- Modify: `README.md`
  - Update status table and print/finalization workflow text.
- Modify: `IMPLEMENTATION_PLAN.md`
  - Add concise milestone note and verification results after implementation.
- Modify: focused tests listed in the tasks below.

---

### Task 1: Add Status And Schema Tests

**Files:**
- Modify: `tests/test_baseline.py`

- [ ] **Step 1: Extend the status imports**

Replace the current constants import in `tests/test_baseline.py`:

```python
from app.constants import (
    STATUS_IMPORTED,
    STATUS_PENDING,
)
```

with:

```python
from app.constants import (
    CARD_STATUSES,
    STATUS_ARCHIVED,
    STATUS_COMPLETED,
    STATUS_IMPORTED,
    STATUS_LABELS,
    STATUS_PENDING,
)
```

- [ ] **Step 2: Add status label and new-schema CHECK coverage**

Add these tests after `test_database_initialization_seeds_four_machines`:

```python
def test_status_constants_label_completed_as_produced_and_archived_as_finished():
    assert STATUS_COMPLETED in CARD_STATUSES
    assert STATUS_ARCHIVED in CARD_STATUSES
    assert STATUS_LABELS[STATUS_COMPLETED] == "Произведена"
    assert STATUS_LABELS[STATUS_ARCHIVED] == "Завършена"


def test_new_cards_schema_allows_archived_status(connection):
    schema_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
    ).fetchone()["sql"]

    assert "'archived'" in schema_sql

    connection.execute(
        """
        INSERT INTO cards (order_number, status)
        VALUES (?, ?)
        """,
        ("ARCHIVED-SCHEMA-1", STATUS_ARCHIVED),
    )

    status = connection.execute(
        "SELECT status FROM cards WHERE order_number = ?",
        ("ARCHIVED-SCHEMA-1",),
    ).fetchone()["status"]
    assert status == STATUS_ARCHIVED
```

- [ ] **Step 3: Add old CHECK-constraint migration coverage**

Add this test after `test_database_initialization_adds_max_roll_weight_to_existing_cards_table`:

```python
def test_database_initialization_updates_existing_status_check_to_allow_archived(
    monkeypatch,
):
    legacy_data_dir = Path.cwd() / ".test-runtime" / uuid4().hex
    legacy_data_dir.mkdir(parents=True)
    legacy_db_path = legacy_data_dir / "legacy-status-check.sqlite3"
    try:
        with sqlite3.connect(legacy_db_path) as legacy_connection:
            legacy_connection.execute(
                """
                CREATE TABLE cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'imported'
                        CHECK (status IN ('imported', 'pending', 'running', 'paused', 'completed', 'cancelled')),
                    machine_id INTEGER,
                    machine_sequence INTEGER,
                    max_roll_weight TEXT
                )
                """
            )
            legacy_connection.execute(
                "INSERT INTO cards (order_number, status) VALUES (?, ?)",
                ("LEGACY-ARCHIVE-1", STATUS_COMPLETED),
            )

        monkeypatch.setattr(db, "DATA_DIR", legacy_data_dir)
        monkeypatch.setattr(db, "DB_PATH", legacy_db_path)

        db.init_db()
        db.init_db()

        with db.connect() as migrated_connection:
            migrated_connection.execute(
                "UPDATE cards SET status = ? WHERE order_number = ?",
                (STATUS_ARCHIVED, "LEGACY-ARCHIVE-1"),
            )
            migrated_connection.commit()
            schema_sql = migrated_connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
            ).fetchone()["sql"]
            status = migrated_connection.execute(
                "SELECT status FROM cards WHERE order_number = ?",
                ("LEGACY-ARCHIVE-1",),
            ).fetchone()["status"]
    finally:
        shutil.rmtree(legacy_data_dir, ignore_errors=True)

    assert "'archived'" in schema_sql
    assert status == STATUS_ARCHIVED
```

- [ ] **Step 4: Run focused baseline tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py::test_status_constants_label_completed_as_produced_and_archived_as_finished tests/test_baseline.py::test_new_cards_schema_allows_archived_status tests/test_baseline.py::test_database_initialization_updates_existing_status_check_to_allow_archived -q
```

Expected before implementation:

```text
FAILED tests/test_baseline.py::test_status_constants_label_completed_as_produced_and_archived_as_finished
FAILED tests/test_baseline.py::test_new_cards_schema_allows_archived_status
FAILED tests/test_baseline.py::test_database_initialization_updates_existing_status_check_to_allow_archived
```

---

### Task 2: Implement Status Constants And SQLite Status Migration

**Files:**
- Modify: `app/constants.py`
- Modify: `app/db.py`

- [ ] **Step 1: Add archived status constants**

In `app/constants.py`, replace the status block with:

```python
STATUS_IMPORTED = "imported"
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_COMPLETED = "completed"
STATUS_ARCHIVED = "archived"
STATUS_CANCELLED = "cancelled"

CARD_STATUSES = (
    STATUS_IMPORTED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_PAUSED,
    STATUS_COMPLETED,
    STATUS_ARCHIVED,
    STATUS_CANCELLED,
)

STATUS_LABELS = {
    STATUS_IMPORTED: "Импортирана",
    STATUS_PENDING: "Изчакване",
    STATUS_RUNNING: "Изработване",
    STATUS_PAUSED: "Паузирана",
    STATUS_COMPLETED: "Произведена",
    STATUS_ARCHIVED: "Завършена",
    STATUS_CANCELLED: "Анулирана",
}
```

Below `ACTIVE_TERMINAL_STATUSES`, replace the archive tuples with:

```python
PRODUCTION_COMPLETE_STATUSES = (
    STATUS_COMPLETED,
    STATUS_ARCHIVED,
)

PRINTABLE_STATUSES = PRODUCTION_COMPLETE_STATUSES

ARCHIVE_STATUSES = (
    *PRODUCTION_COMPLETE_STATUSES,
    STATUS_CANCELLED,
)

TERMINAL_ARCHIVE_STATUSES = (
    STATUS_COMPLETED,
)
```

- [ ] **Step 2: Update `app/db.py` imports**

Update the constants import in `app/db.py` to include:

```python
    PRODUCTION_COMPLETE_STATUSES,
    STATUS_ARCHIVED,
```

- [ ] **Step 3: Split the cards table SQL into a reusable helper**

Above `SCHEMA_SQL`, add:

```python
def cards_table_sql(table_name: str = "cards", if_not_exists: bool = True) -> str:
    create_clause = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE TABLE"
    return f"""
{create_clause} {table_name} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'imported' CHECK (status IN ({_sql_list(CARD_STATUSES)})),
    import_batch_id INTEGER REFERENCES import_batches(id) ON DELETE SET NULL,
    machine_id INTEGER REFERENCES machines(id) ON DELETE RESTRICT,
    machine_sequence INTEGER,

    order_date TEXT,
    delivery_date TEXT,
    customer TEXT,
    city TEXT,
    product_type TEXT,
    quantity_1 TEXT,
    unit_1 TEXT,
    quantity_2 TEXT,
    unit_2 TEXT,
    product_form TEXT,
    material TEXT,
    max_roll_weight TEXT,
    size_thickness TEXT,
    notes TEXT,

    extrusion_flag TEXT,
    extrusion_folding TEXT,
    extrusion_next_operation TEXT,
    extrusion_treatment TEXT,
    raw_material_a TEXT,
    raw_material_b TEXT,
    raw_material_c TEXT,
    linear_pe TEXT,
    antistatic TEXT,
    masterbatch TEXT,
    chalk TEXT,
    packaging_method TEXT,

    actual_raw_material_used TEXT,
    raw_material_brand_grade TEXT,
    raw_material_batch_lot TEXT,
    tare_weight NUMERIC CHECK (tare_weight IS NULL OR tare_weight >= 0),

    first_started_at TEXT,
    finished_at TEXT,
    cancelled_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
```

Then replace the inline `CREATE TABLE IF NOT EXISTS cards (...)` block inside `SCHEMA_SQL` with:

```python
{cards_table_sql().strip()}
```

- [ ] **Step 4: Add the CHECK-constraint migration helper**

Below `ensure_column`, add:

```python
def ensure_cards_status_constraint(connection: sqlite3.Connection) -> None:
    schema_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cards'"
    ).fetchone()
    schema_sql = str(schema_row["sql"] or "") if schema_row else ""
    if f"'{STATUS_ARCHIVED}'" in schema_sql:
        return

    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("DROP TABLE IF EXISTS cards_status_migration")
        connection.execute(cards_table_sql("cards_status_migration", if_not_exists=False))

        legacy_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(cards)").fetchall()
        }
        target_columns = [
            row["name"]
            for row in connection.execute("PRAGMA table_info(cards_status_migration)").fetchall()
        ]
        copy_columns = [column for column in target_columns if column in legacy_columns]
        column_sql = ", ".join(copy_columns)
        connection.execute(
            f"""
            INSERT INTO cards_status_migration ({column_sql})
            SELECT {column_sql}
            FROM cards
            """
        )
        connection.execute("DROP TABLE cards")
        connection.execute("ALTER TABLE cards_status_migration RENAME TO cards")
        connection.commit()
    finally:
        connection.execute("PRAGMA foreign_keys = ON")

    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise sqlite3.IntegrityError("cards status migration failed foreign key check")
```

- [ ] **Step 5: Run the migration during initialization**

In `init_db()`, immediately after the first `connection.executescript(SCHEMA_SQL)`, add:

```python
        ensure_cards_status_constraint(connection)
        connection.executescript(SCHEMA_SQL)
```

The second `executescript(SCHEMA_SQL)` recreates indexes dropped when the `cards` table is rebuilt.

- [ ] **Step 6: Run focused baseline tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py::test_status_constants_label_completed_as_produced_and_archived_as_finished tests/test_baseline.py::test_new_cards_schema_allows_archived_status tests/test_baseline.py::test_database_initialization_updates_existing_status_check_to_allow_archived tests/test_baseline.py::test_database_initialization_adds_max_roll_weight_to_existing_cards_table -q
```

Expected:

```text
4 passed
```

---

### Task 3: Add Admin Archive Action Tests

**Files:**
- Modify: `tests/test_finish_cancel_history.py`
- Modify: `tests/test_admin_card_detail_redesign.py`

- [ ] **Step 1: Import `STATUS_ARCHIVED` in finish/history tests**

In `tests/test_finish_cancel_history.py`, add `STATUS_ARCHIVED` to the constants import.

- [ ] **Step 2: Add backend archive transition tests**

Add these tests after `test_finish_from_paused_succeeds_without_open_segment`:

```python
def test_admin_can_mark_completed_card_as_archived(connection):
    card_id = prepare_running_finishable_card("25630")
    assert db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]

    result = db.archive_completed_card(card_id, loaded_version)

    card = db.fetch_admin_card_detail(card_id)
    assert result.ok
    assert result.messages == ("Поръчка 25630 е маркирана като завършена.",)
    assert card["status"] == STATUS_ARCHIVED
    assert card["version"] == loaded_version + 1


def test_archive_action_blocks_non_completed_cards(connection):
    card_id = import_and_release_card("25631", machine_id=1, machine_sequence=1)
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]

    result = db.archive_completed_card(card_id, loaded_version)

    assert not result.ok
    assert result.messages == ("Само произведени карти могат да се маркират като завършени.",)
    assert db.fetch_admin_card_detail(card_id)["status"] == STATUS_PENDING


def test_archive_action_blocks_stale_version(connection):
    card_id = prepare_running_finishable_card("25632")
    assert db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok
    loaded_version = db.fetch_admin_card_detail(card_id)["version"]
    assert db.update_tare_weight(card_id, loaded_version, "1.10").ok

    result = db.archive_completed_card(card_id, loaded_version)

    assert not result.ok
    assert result.messages == (db.STALE_CARD_MESSAGE,)
    assert db.fetch_admin_card_detail(card_id)["status"] == STATUS_COMPLETED
```

- [ ] **Step 3: Add admin detail action rendering tests**

Add these tests near `test_admin_detail_print_link_is_available_only_for_completed_cards`:

```python
def test_admin_detail_shows_archive_action_for_produced_cards(connection):
    card_id = prepare_dense_completed_card("27045", roll_count=1)

    html = render_admin_detail(card_id)

    assert "Произведена" in html
    assert (
        f'<a class="nav-link" href="/cards/{card_id}/print" '
        'target="_blank" rel="noopener">Печат / препечат</a>'
    ) in html
    assert f'action="/admin/cards/{card_id}/archive"' in html
    assert "Маркирай като завършена" in html


def test_admin_detail_shows_print_but_no_archive_action_for_archived_cards(connection):
    card_id = prepare_dense_completed_card("27046", roll_count=1)
    assert db.archive_completed_card(card_id, card_version(card_id)).ok

    html = render_admin_detail(card_id)

    assert "Завършена" in html
    assert 'class="pill status-archived"' in html
    assert (
        f'<a class="nav-link" href="/cards/{card_id}/print" '
        'target="_blank" rel="noopener">Печат / препечат</a>'
    ) in html
    assert f'action="/admin/cards/{card_id}/archive"' not in html
    assert "Маркирай като завършена" not in html
```

- [ ] **Step 4: Add admin list navigation-only coverage**

Replace `test_admin_cards_list_print_link_is_completed_only` with:

```python
def test_admin_cards_list_does_not_show_print_shortcuts(connection):
    completed_id = prepare_dense_completed_card("27042", roll_count=1)
    pending_id = import_ready_card("27043")
    assert db.release_card(
        pending_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(pending_id),
        max_roll_weight="62.50",
    ).ok
    cancelled_id = import_ready_card("27044")
    assert db.release_card(
        cancelled_id,
        machine_id=2,
        machine_sequence=1,
        loaded_version=card_version(cancelled_id),
        max_roll_weight="62.50",
    ).ok
    assert db.cancel_card(cancelled_id, card_version(cancelled_id)).ok

    html = render_admin_cards_list()

    assert f'<a href="/admin/cards/{completed_id}">Отвори</a>' in html
    assert f'<a href="/admin/cards/{pending_id}">Отвори</a>' in html
    assert f'<a href="/admin/cards/{cancelled_id}">Отвори</a>' in html
    assert "/print" not in html
    assert ">Печат<" not in html
```

- [ ] **Step 5: Run focused tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_finish_cancel_history.py::test_admin_can_mark_completed_card_as_archived tests/test_finish_cancel_history.py::test_archive_action_blocks_non_completed_cards tests/test_finish_cancel_history.py::test_archive_action_blocks_stale_version tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_archive_action_for_produced_cards tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_print_but_no_archive_action_for_archived_cards tests/test_admin_card_detail_redesign.py::test_admin_cards_list_does_not_show_print_shortcuts -q
```

Expected before implementation:

```text
FAILED tests/test_finish_cancel_history.py::test_admin_can_mark_completed_card_as_archived
FAILED tests/test_finish_cancel_history.py::test_archive_action_blocks_non_completed_cards
FAILED tests/test_finish_cancel_history.py::test_archive_action_blocks_stale_version
FAILED tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_archive_action_for_produced_cards
FAILED tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_print_but_no_archive_action_for_archived_cards
FAILED tests/test_admin_card_detail_redesign.py::test_admin_cards_list_does_not_show_print_shortcuts
```

---

### Task 4: Implement Admin Archive Action

**Files:**
- Modify: `app/db.py`
- Modify: `app/main.py`
- Modify: `app/templates/admin_card_detail.html`
- Modify: `app/templates/admin_cards.html`

- [ ] **Step 1: Add `archive_completed_card()` to `app/db.py`**

Add this function after `finish_card()` and before `cancel_card()`:

```python
def archive_completed_card(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = connection.execute(
            """
            SELECT id, order_number, status, version
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        if card["status"] != STATUS_COMPLETED:
            return RuleResult(
                False,
                ("Само произведени карти могат да се маркират като завършени.",),
            )

        connection.execute(
            """
            UPDATE cards
            SET status = ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (STATUS_ARCHIVED, card_id),
        )

    return RuleResult(True, (f"Поръчка {card['order_number']} е маркирана като завършена.",))
```

- [ ] **Step 2: Wire the admin route in `app/main.py`**

Add `archive_completed_card` to the `.db` imports.

After `restore_admin_card`, add:

```python
@app.post("/admin/cards/{card_id}/archive")
async def archive_admin_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
):
    parsed_version, workflow_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        workflow_result = archive_completed_card(card_id, parsed_version)

    return admin_card_post_response(
        request,
        card_id,
        "workflow_result",
        workflow_result,
    )
```

- [ ] **Step 3: Update admin card detail actions**

In `app/templates/admin_card_detail.html`, replace:

```jinja2
{% if card.status == "completed" %}
  <a class="nav-link" href="/cards/{{ card.id }}/print" target="_blank" rel="noopener">Печат / препечат</a>
{% endif %}
```

with:

```jinja2
{% if card.status in ["completed", "archived"] %}
  <a class="nav-link" href="/cards/{{ card.id }}/print" target="_blank" rel="noopener">Печат / препечат</a>
{% endif %}
{% if card.status == "completed" %}
  <form action="/admin/cards/{{ card.id }}/archive" method="post">
    <input type="hidden" name="loaded_version" value="{{ card.version }}">
    <button type="submit">Маркирай като завършена</button>
  </form>
{% endif %}
```

- [ ] **Step 4: Remove table print shortcut**

In `app/templates/admin_cards.html`, replace:

```jinja2
<a href="/admin/cards/{{ card.id }}">Отвори</a>
{% if card.status == "completed" %}
  <a href="/cards/{{ card.id }}/print" target="_blank" rel="noopener">Печат</a>
{% endif %}
```

with:

```jinja2
<a href="/admin/cards/{{ card.id }}">Отвори</a>
```

- [ ] **Step 5: Run archive/admin focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_finish_cancel_history.py::test_admin_can_mark_completed_card_as_archived tests/test_finish_cancel_history.py::test_archive_action_blocks_non_completed_cards tests/test_finish_cancel_history.py::test_archive_action_blocks_stale_version tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_archive_action_for_produced_cards tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_print_but_no_archive_action_for_archived_cards tests/test_admin_card_detail_redesign.py::test_admin_cards_list_does_not_show_print_shortcuts -q
```

Expected:

```text
6 passed
```

---

### Task 5: Add Print And Correction Eligibility Tests For Archived Cards

**Files:**
- Modify: `tests/test_print_output.py`
- Modify: `tests/test_admin_production_corrections.py`

- [ ] **Step 1: Import `STATUS_ARCHIVED` in print tests**

In `tests/test_print_output.py`, add `STATUS_ARCHIVED` to the constants import.

- [ ] **Step 2: Add archived print readiness coverage**

Add this test after `test_completed_card_with_required_production_data_is_printable`:

```python
def test_archived_card_with_required_production_data_is_printable(connection):
    card_id = make_completed_printable_card("27035")
    set_card_status(card_id, STATUS_ARCHIVED)

    result = build_print_readiness(card_id)

    assert result.ok
    assert result.data is not None
```

- [ ] **Step 3: Update non-printable status coverage**

Rename `test_only_completed_cards_are_printable` to:

```python
@pytest.mark.parametrize(
    "status",
    [
        STATUS_PENDING,
        STATUS_RUNNING,
        STATUS_PAUSED,
        STATUS_IMPORTED,
        STATUS_CANCELLED,
    ],
)
def test_only_produced_or_archived_cards_are_printable(connection, status):
    card_id = make_completed_printable_card(f"27001-{status}")
    set_card_status(card_id, status)

    result = build_print_readiness(card_id)

    assert not result.ok
    assert result.data is None
    assert "Печатът е разрешен само за произведени или завършени карти." in result.messages
```

- [ ] **Step 4: Import `STATUS_ARCHIVED` in admin correction tests**

In `tests/test_admin_production_corrections.py`, add `STATUS_ARCHIVED` to the constants import.

- [ ] **Step 5: Add archived correction coverage**

Add these tests near the existing completed-card correction tests:

```python
def test_archived_card_roll_weights_remain_editable(connection):
    card_id = prepare_completed_card("26030")
    assert db.archive_completed_card(card_id, card_version(card_id)).ok

    result = db.update_admin_roll_ledger(
        card_id,
        card_version(card_id),
        tare_weight="1.10",
        roll_updates={},
        delete_roll_ids=set(),
        new_gross_weights=["35.00"],
    )

    card = db.fetch_admin_card_detail(card_id)
    assert result.ok
    assert card["status"] == STATUS_ARCHIVED
    assert card["roll_entries"][-1]["gross_weight"] == 35


def test_archived_card_materials_remain_editable(connection):
    card_id = prepare_completed_card("26031")
    assert db.archive_completed_card(card_id, card_version(card_id)).ok

    result = db.update_terminal_recipe_actual_entries(
        card_id,
        card_version(card_id),
        {
            "raw_material_a": {
                "actual_material_used": "Archived Actual A",
                "batch_lot": "ARCH-A",
            }
        },
    )

    card = db.fetch_admin_card_detail(card_id)
    assert result.ok
    assert card["status"] == STATUS_ARCHIVED
    assert card["recipe_actual_entries"]["raw_material_a"]["actual_material_used"] == "Archived Actual A"
    assert card["recipe_actual_entries"]["raw_material_a"]["batch_lot"] == "ARCH-A"
```

- [ ] **Step 6: Run focused tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_print_output.py::test_archived_card_with_required_production_data_is_printable tests/test_print_output.py::test_only_produced_or_archived_cards_are_printable tests/test_admin_production_corrections.py::test_archived_card_roll_weights_remain_editable tests/test_admin_production_corrections.py::test_archived_card_materials_remain_editable -q
```

Expected before implementation:

```text
FAILED tests/test_print_output.py::test_archived_card_with_required_production_data_is_printable
FAILED tests/test_print_output.py::test_only_produced_or_archived_cards_are_printable
FAILED tests/test_admin_production_corrections.py::test_archived_card_roll_weights_remain_editable
FAILED tests/test_admin_production_corrections.py::test_archived_card_materials_remain_editable
```

---

### Task 6: Implement Printable And Correctable Archived Behavior

**Files:**
- Modify: `app/printing.py`
- Modify: `app/db.py`

- [ ] **Step 1: Update print readiness**

In `app/printing.py`, replace:

```python
from .constants import STATUS_COMPLETED
```

with:

```python
from .constants import PRINTABLE_STATUSES
```

Replace:

```python
if card["status"] != STATUS_COMPLETED:
    messages.append("Печатът е разрешен само за завършени карти.")
```

with:

```python
if card["status"] not in PRINTABLE_STATUSES:
    messages.append("Печатът е разрешен само за произведени или завършени карти.")
```

- [ ] **Step 2: Update completed-like invariant checks in `app/db.py`**

Replace each completed-only invariant check that protects final production data with `PRODUCTION_COMPLETE_STATUSES`:

```python
if card["status"] == STATUS_COMPLETED:
```

becomes:

```python
if card["status"] in PRODUCTION_COMPLETE_STATUSES:
```

Apply that replacement in:

- `delete_timing_segment()`
- `update_timing_ledger()` for the final segment count check
- `update_roll_gross_weight()` for the final gross roll clearing check
- `delete_roll_entry()` for the final gross roll deletion check
- `update_admin_roll_ledger()` for the final gross roll count check

Replace:

```python
WHEN status = ?
```

inside `update_timing_ledger()` with:

```python
WHEN status IN (?, ?)
```

and update the parameters from:

```python
(STATUS_COMPLETED, card_id, card_id),
```

to:

```python
(*PRODUCTION_COMPLETE_STATUSES, card_id, card_id),
```

- [ ] **Step 3: Update roll action eligibility**

In `fetch_roll_action_card()`, replace:

```python
roll_edit_statuses = (*ACTIVE_TERMINAL_STATUSES, STATUS_COMPLETED)
```

with:

```python
roll_edit_statuses = (*ACTIVE_TERMINAL_STATUSES, *PRODUCTION_COMPLETE_STATUSES)
```

In `validate_card_allows_roll_entry()`, replace:

```python
if card["status"] not in (STATUS_RUNNING, STATUS_COMPLETED):
```

with:

```python
if card["status"] not in (STATUS_RUNNING, *PRODUCTION_COMPLETE_STATUSES):
```

Replace the message:

```python
"Теглата на ролките могат да се променят само когато картата е в изработване или завършена."
```

with:

```python
"Теглата на ролките могат да се променят само когато картата е в изработване, произведена или завършена."
```

- [ ] **Step 4: Confirm admin production action status coverage**

Do not change `fetch_admin_production_action_card()` if `ARCHIVE_STATUSES` now contains `completed`, `archived`, and `cancelled`; that keeps existing correction functions able to find archived cards.

- [ ] **Step 5: Run focused print/correction tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_print_output.py::test_archived_card_with_required_production_data_is_printable tests/test_print_output.py::test_only_produced_or_archived_cards_are_printable tests/test_admin_production_corrections.py::test_archived_card_roll_weights_remain_editable tests/test_admin_production_corrections.py::test_archived_card_materials_remain_editable -q
```

Expected:

```text
4 passed
```

---

### Task 7: Add Terminal And Admin UI Tests

**Files:**
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_admin_card_detail_redesign.py`

- [ ] **Step 1: Replace terminal print-link test**

Replace `test_terminal_v8_print_link_is_available_only_for_completed_cards` in `tests/test_terminal_v8_render.py` with:

```python
def test_terminal_v8_does_not_render_print_action_for_produced_cards(connection):
    completed_id = release_ready_card("26180", machine_id=1, sequence=1)
    complete_card(completed_id)

    completed_html = render_terminal(completed_id)

    assert f"/cards/{completed_id}/print" not in completed_html
    assert "Печат / препечат" not in completed_html
    assert "Корекции на ролки" in completed_html
```

- [ ] **Step 2: Add produced-history label coverage**

Add this test near `test_terminal_v8_renders_recipe_queue_and_completed_lookup`:

```python
def test_terminal_v8_labels_completed_lookup_as_produced_orders(connection):
    completed_id = release_ready_card("26184", machine_id=1, sequence=1, customer="Produced Customer")
    complete_card(completed_id)

    html = render_terminal(completed_id)

    assert "Произведени поръчки" in html
    assert "Завършени поръчки" not in html
    assert "Филтри за произведени поръчки" in html
    assert "Затвори произведените поръчки" in html
    assert "Няма намерени произведени поръчки." in html
```

- [ ] **Step 3: Add archived cards stay out of terminal lookup**

Add this test near the produced-history test:

```python
def test_terminal_v8_hides_archived_cards_from_produced_lookup(connection):
    completed_id = release_ready_card("26185", machine_id=1, sequence=1, customer="Produced Customer")
    complete_card(completed_id)
    archived_id = release_ready_card("26186", machine_id=2, sequence=1, customer="Archived Customer")
    complete_card(archived_id)
    assert db.archive_completed_card(archived_id, card_version(archived_id)).ok

    html = render_terminal(completed_id)

    assert "Produced Customer" in html
    assert "Archived Customer" not in html
```

- [ ] **Step 4: Add admin status color render assertions**

Extend `test_admin_detail_shows_archive_action_for_produced_cards` with:

```python
assert 'class="pill status-completed"' in html
```

Extend `test_admin_detail_shows_print_but_no_archive_action_for_archived_cards` with:

```python
assert 'class="pill status-archived"' in html
```

- [ ] **Step 5: Run focused render tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_v8_does_not_render_print_action_for_produced_cards tests/test_terminal_v8_render.py::test_terminal_v8_labels_completed_lookup_as_produced_orders tests/test_terminal_v8_render.py::test_terminal_v8_hides_archived_cards_from_produced_lookup tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_archive_action_for_produced_cards tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_print_but_no_archive_action_for_archived_cards -q
```

Expected before implementation:

```text
FAILED tests/test_terminal_v8_render.py::test_terminal_v8_does_not_render_print_action_for_produced_cards
FAILED tests/test_terminal_v8_render.py::test_terminal_v8_labels_completed_lookup_as_produced_orders
FAILED tests/test_terminal_v8_render.py::test_terminal_v8_hides_archived_cards_from_produced_lookup
```

The admin tests may already pass for class names once earlier tasks are implemented; the terminal tests should fail until the template is changed.

---

### Task 8: Implement Template And Admin Color Changes

**Files:**
- Modify: `app/templates/terminal.html`
- Modify: `app/templates/admin_card_detail.html`
- Modify: `app/templates/admin_cards.html`
- Modify: `app/static/css/app.css`

- [ ] **Step 1: Remove terminal print action**

In `app/templates/terminal.html`, replace:

```jinja2
{% set show_roll_correction = selected_card and selected_card.roll_entries and selected_card.status in ["running", "completed"] %}
{% set show_print_action = selected_card and selected_card.status == "completed" %}
{% if show_print_action or show_roll_correction %}
  <div class="menu">
    <button class="menu-btn" type="button" aria-label="Още действия">⋯</button>
    <div class="menu-panel">
      {% if show_print_action %}
        <a href="/cards/{{ selected_card.id }}/print?auto=1&amp;source=terminal" target="_blank" rel="noopener">Печат / препечат</a>
      {% endif %}
      {% if show_roll_correction %}
        <button class="roll-correction-open" id="roll-correction-open" type="button">Корекции на ролки</button>
      {% endif %}
    </div>
  </div>
{% endif %}
```

with:

```jinja2
{% set show_roll_correction = selected_card and selected_card.roll_entries and selected_card.status in ["running", "completed"] %}
{% if show_roll_correction %}
  <div class="menu">
    <button class="menu-btn" type="button" aria-label="Още действия">⋯</button>
    <div class="menu-panel">
      <button class="roll-correction-open" id="roll-correction-open" type="button">Корекции на ролки</button>
    </div>
  </div>
{% endif %}
```

- [ ] **Step 2: Rename terminal produced-history strings**

In `app/templates/terminal.html`, replace:

```text
Завършени поръчки
Затвори завършените поръчки
Филтри за завършени поръчки
Няма намерени завършени поръчки.
завършените поръчки
```

with:

```text
Произведени поръчки
Затвори произведените поръчки
Филтри за произведени поръчки
Няма намерени произведени поръчки.
произведените поръчки
```

Do not change the JavaScript variable names such as `historyOverlay`; they are internal UI code and not user-facing.

- [ ] **Step 3: Update admin/global status colors**

In `app/static/css/app.css`, replace:

```css
--status-completed-bg: #dcfce7;
--status-completed-border: #22c55e;
--status-completed-text: #166534;
```

with:

```css
--status-completed-bg: #ddf4ff;
--status-completed-border: #8bb8e8;
--status-completed-text: #0969da;
--status-archived-bg: #dcfce7;
--status-archived-border: #22c55e;
--status-archived-text: #166534;
```

After the completed pill rule, add:

```css
.pill.archived,
.pill.status-archived {
  border-color: var(--status-archived-border);
  background: var(--status-archived-bg);
  color: var(--status-archived-text);
}
```

Do not change `.status.running` or `.status.completed` inside `app/templates/terminal.html`; those workstation colors have a separate machine-state meaning.

- [ ] **Step 4: Run focused UI render tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_v8_does_not_render_print_action_for_produced_cards tests/test_terminal_v8_render.py::test_terminal_v8_labels_completed_lookup_as_produced_orders tests/test_terminal_v8_render.py::test_terminal_v8_hides_archived_cards_from_produced_lookup tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_archive_action_for_produced_cards tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_print_but_no_archive_action_for_archived_cards tests/test_admin_card_detail_redesign.py::test_admin_cards_list_does_not_show_print_shortcuts -q
```

Expected:

```text
6 passed
```

---

### Task 9: Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update README status table**

In `README.md`, update the workflow status section so it includes:

```markdown
| `completed` / produced | Operators have manufactured the order/card. It moves from the active terminal queue to the terminal produced section and remains available to workstation operators for review/correction, but print/final archive approval is handled by shift-manager/admin. |
| `archived` / finished | Shift-manager/admin has reviewed the produced card, printed/reprinted as needed, and marked the paper operational card as filed/done. It remains visible, editable, correctable, and reprintable in admin. |
```

Update the Bulgarian label table so it includes:

```markdown
| `completed` | Произведена |
| `archived` | Завършена |
```

- [ ] **Step 2: Update print workflow text**

In `README.md`, update the print requirements so they state:

```markdown
- Printing/reprinting is an admin/shift-manager action from the operational card detail.
- Workstation operators do not print from `/terminal`.
- Printing is allowed for produced (`completed`) and finished/archived (`archived`) cards.
- Opening or executing print does not change card status.
- Shift-manager/admin manually marks a produced card as finished/archived after review and paper handling.
```

- [ ] **Step 3: Update implementation tracker**

In `IMPLEMENTATION_PLAN.md`, add a short follow-up under the current print/workflow milestone:

```markdown
Follow-up: Admin finalization status

- `completed` is now the workstation-produced state and is labeled `Произведена`.
- `archived` is the shift-manager finalized state and is labeled `Завършена`.
- Admin card detail owns print/reprint and manual finalization actions.
- The workstation no longer exposes print/reprint; its produced-card drawer is labeled `Произведени поръчки`.
- Produced and archived cards remain editable/correctable, and both are printable from admin.
```

- [ ] **Step 4: Run documentation grep checks**

Run:

```bash
rg -n "Завършени поръчки|Only completed cards can be printed|Printing must be possible from the workstation|Печат / препечат" README.md IMPLEMENTATION_PLAN.md app/templates/terminal.html app/templates/admin_cards.html
```

Expected:

- No `Завършени поръчки` remains in `app/templates/terminal.html`.
- No README statement remains saying printing must be possible from the workstation.
- `Печат / препечат` remains in `app/templates/admin_card_detail.html` and may remain in docs.
- `Печат / препечат` does not remain in `app/templates/terminal.html`.

---

### Task 10: Full Verification And Manual UI Check

**Files:**
- Test only unless a failure reveals a bug.

- [ ] **Step 1: Run focused Python tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py tests/test_finish_cancel_history.py tests/test_admin_card_detail_redesign.py tests/test_admin_production_corrections.py tests/test_print_output.py tests/test_terminal_v8_render.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run the full test suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected:

```text
passed
```

- [ ] **Step 3: Run syntax/import check**

Run:

```bash
source .venv/bin/activate
python -m compileall app tests
```

Expected:

```text
0 failures
```

- [ ] **Step 4: Run whitespace diff check**

Run:

```bash
git diff --check
```

Expected:

```text
no output
```

- [ ] **Step 5: Start the app against a temporary database**

Run:

```bash
mkdir -p .test-runtime/archive-status-ui
EXTRUSION_DB_PATH=.test-runtime/archive-status-ui/extrusion_terminal.sqlite3 source .venv/bin/activate
```

Then run:

```bash
EXTRUSION_DB_PATH=.test-runtime/archive-status-ui/extrusion_terminal.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected:

```text
Uvicorn running on http://127.0.0.1:8000
```

- [ ] **Step 6: Capture Playwright UI evidence**

Use the existing repo-local Playwright setup to exercise:

- `/terminal` shows `Произведени поръчки`.
- `/terminal` does not show `Печат / препечат`.
- `/admin/cards/{card_id}` for a produced card shows blue `Произведена`, `Печат / препечат`, and `Маркирай като завършена`.
- After marking the card finalized, `/admin/cards/{card_id}` shows green `Завършена`, still shows `Печат / препечат`, and no longer shows `Маркирай като завършена`.

Save at least one relevant screenshot under:

```text
artifacts/ui-checks/archive-status-admin-detail.png
```

- [ ] **Step 7: Stop the dev server**

Stop the uvicorn process before ending the implementation session.

- [ ] **Step 8: Review changed code**

Run:

```bash
git diff -- app/constants.py app/db.py app/printing.py app/main.py app/templates/admin_card_detail.html app/templates/admin_cards.html app/templates/terminal.html app/static/css/app.css README.md IMPLEMENTATION_PLAN.md tests
```

Review specifically for:

- No terminal print link remains.
- No admin table print shortcut remains.
- No return/reopen workflow was added.
- `finish_card()` still writes `STATUS_COMPLETED`.
- `archive_completed_card()` is admin-only through route/template exposure.
- Print readiness allows `completed` and `archived`, but rejects cancelled.
- Existing production data corrections work for archived cards.
- The SQLite migration preserves existing card rows.

- [ ] **Step 9: Report verification**

In the final implementation report, include:

- Tests run and pass/fail status.
- Screenshot path.
- Any skipped UI or Playwright verification with reason.
- Reminder that no files were staged or committed unless the user explicitly asked.

---

## Plan Self-Review

- Spec coverage: The plan covers the new `archived` status, Bulgarian labels, manual admin-only finalization, admin-only print action, removal of terminal/table print shortcuts, admin color semantics, workstation label change, print/correction eligibility, SQLite CHECK migration, docs, and UI verification.
- Placeholder scan: No `TBD`, `TODO`, or unspecified implementation step remains.
- Type consistency: The plan uses `STATUS_ARCHIVED`, `PRODUCTION_COMPLETE_STATUSES`, `PRINTABLE_STATUSES`, and `archive_completed_card()` consistently across tests and implementation steps.
- Scope check: This is one focused workflow/status slice. It does not change print layout, import behavior, timing calculations, role/login behavior, or workstation machine-state colors.
