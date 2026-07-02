# Roll-Level Tare Weights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change roll entry so each roll stores and edits its own tare/core weight, while the card-level tare field becomes only the default tare copied onto newly added rolls.

**Architecture:** Keep the existing `cards.tare_weight` column as the workstation/admin default tare for future rolls. Add `roll_entries.tare_weight`, calculate `roll_entries.net_weight` from each roll's own gross and tare, and derive order total net by summing per-roll net values. Update terminal/admin roll ledgers to edit gross and per-roll tare while keeping net read-only, and show mixed tare summaries as a lowest-to-highest range.

**Tech Stack:** FastAPI, direct `sqlite3`, Jinja templates, existing CSS, pytest, local Playwright for UI verification.

---

## Scope And Confirmed Behavior

- The top/current `Шпула, кг` field remains on the workstation roll panel.
- `cards.tare_weight` is the current/default tare only.
- Adding a new roll copies `cards.tare_weight` into the new `roll_entries.tare_weight`.
- If `cards.tare_weight` is blank when a roll is added, the roll is still added with blank tare and blank net so it can be corrected in the table; finish and print remain blocked until each gross roll has a valid tare/net.
- Changing `cards.tare_weight` never changes existing roll rows.
- Workstation operators can edit each roll's gross and tare in the roll table.
- Admin/shift-manager can edit each roll's gross and tare in the admin roll ledger.
- Editing a roll's gross or tare recalculates only that roll's net and the card totals.
- Net is read-only in both terminal and admin UI.
- `total_net_weight` is the sum of per-roll net weights. If any gross roll lacks a valid per-roll tare/net, total net is unknown and should render blank/`-` through the existing display helpers.
- Mixed tare summary displays as `lowest-highest`, for example `2.0-2.5`.
- Single tare summary displays as one value, for example `2.0`.
- Existing pilot databases migrate by copying `cards.tare_weight` into existing roll rows and recalculating stored net values.
- Re-import behavior remains unchanged: imported/front-card fields update only; roll production data, including per-roll tare, is preserved.
- No commit should be made unless the user explicitly asks. This plan intentionally uses review checkpoints instead of mandatory commit steps.

## Files To Modify

- `app/db.py`: schema migration, roll fetching/totals, default tare update, roll add/update/admin ledger logic, finish validation.
- `app/main.py`: roll form parsing and route parameters for per-roll tare.
- `app/printing.py`: print readiness checks and derived tare summary display.
- `app/templates/terminal.html`: workstation roll table adds editable per-roll tare column.
- `app/templates/admin_card_detail.html`: admin roll ledger adds editable per-roll tare column.
- `app/static/css/app.css`: admin roll ledger grid updates for the added tare column.
- `README.md`: replace order-level tare invariant with default-plus-per-roll tare behavior.
- `IMPLEMENTATION_PLAN.md`: add this behavior as the next completed/in-progress milestone note when implemented.
- `tests/test_baseline.py`: migration/backfill coverage.
- `tests/test_roll_entry.py`: default copy, per-roll edit, totals, validation.
- `tests/test_finish_cancel_history.py`: finish blocking and completed-card correction behavior.
- `tests/test_admin_production_corrections.py`: admin per-roll tare corrections.
- `tests/test_admin_card_detail_redesign.py`: admin roll ledger markup/parser/global save behavior.
- `tests/test_print_output.py`: print readiness and mixed tare range summary.
- `tests/test_terminal_v8_render.py`: terminal markup, route behavior, and per-row error rendering for roll gross/tare edits.

## Task 1: Add Failing Data-Model Tests

**Files:**
- Modify: `tests/test_baseline.py`
- Modify: `tests/test_roll_entry.py`

- [ ] **Step 1: Add schema migration tests**

In `tests/test_baseline.py`, add tests near the existing database initialization/migration tests:

```python
def test_database_initialization_adds_roll_entry_tare_weight_to_existing_table(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "legacy.sqlite3"
    monkeypatch.setattr(db, "DB_PATH", database_path)
    with db.connect() as connection:
        connection.executescript(
            """
            CREATE TABLE cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'imported',
                machine_id INTEGER,
                machine_sequence INTEGER,
                import_batch_id INTEGER,
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
                tare_weight NUMERIC,
                first_started_at TEXT,
                finished_at TEXT,
                cancelled_at TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE roll_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL,
                order_number TEXT NOT NULL,
                roll_number INTEGER NOT NULL,
                gross_weight NUMERIC,
                net_weight NUMERIC,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (card_id, roll_number)
            );
            INSERT INTO cards (id, order_number, status, tare_weight)
            VALUES (1, '29001', 'running', 1.25);
            INSERT INTO roll_entries (card_id, order_number, roll_number, gross_weight, net_weight)
            VALUES (1, '29001', 1, 51.25, 50.00);
            """
        )

    db.init_db()

    with db.connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(roll_entries)").fetchall()
        }
        roll = connection.execute(
            "SELECT tare_weight, net_weight FROM roll_entries WHERE card_id = 1"
        ).fetchone()

    assert "tare_weight" in columns
    assert roll["tare_weight"] == 1.25
    assert roll["net_weight"] == 50


def test_database_initialization_recalculates_legacy_roll_net_from_roll_tare(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "legacy-net.sqlite3"
    monkeypatch.setattr(db, "DB_PATH", database_path)
    with db.connect() as connection:
        connection.executescript(
            """
            CREATE TABLE cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'imported',
                machine_id INTEGER,
                machine_sequence INTEGER,
                import_batch_id INTEGER,
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
                tare_weight NUMERIC,
                first_started_at TEXT,
                finished_at TEXT,
                cancelled_at TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE roll_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL,
                order_number TEXT NOT NULL,
                roll_number INTEGER NOT NULL,
                gross_weight NUMERIC,
                net_weight NUMERIC,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (card_id, roll_number)
            );
            INSERT INTO cards (id, order_number, status, tare_weight)
            VALUES (1, '29002', 'running', 2.50);
            INSERT INTO roll_entries (card_id, order_number, roll_number, gross_weight, net_weight)
            VALUES (1, '29002', 1, 60.00, 60.00);
            """
        )

    db.init_db()

    with db.connect() as connection:
        roll = connection.execute(
            "SELECT tare_weight, net_weight FROM roll_entries WHERE card_id = 1"
        ).fetchone()

    assert roll["tare_weight"] == 2.5
    assert roll["net_weight"] == 57.5
```

- [ ] **Step 2: Add failing roll behavior tests**

In `tests/test_roll_entry.py`, add these tests after `test_gross_and_net_totals_calculate_with_tare`:

```python
def test_new_roll_copies_current_default_tare_without_mutating_existing_rolls(connection):
    card_id = import_and_release_card("25540")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.50").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "60.00").ok

    card = db.fetch_terminal_card_detail(card_id)

    assert card["tare_weight"] == 2.5
    assert [(roll["gross_weight"], roll["tare_weight"], roll["net_weight"]) for roll in card["roll_entries"]] == [
        (50, 2, 48),
        (60, 2.5, 57.5),
    ]
    assert card["total_gross_weight"] == "110.00"
    assert card["total_net_weight"] == "105.50"


def test_editing_roll_tare_recalculates_only_that_roll_and_not_default_tare(connection):
    card_id = import_and_release_card("25541")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "60.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    first_roll_id = int(card["roll_entries"][0]["id"])

    result = db.update_roll_weight(
        card_id=card_id,
        roll_id=first_roll_id,
        loaded_version=card["version"],
        gross_weight="50.00",
        tare_weight="3.00",
    )
    updated = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert updated["tare_weight"] == 2
    assert [(roll["tare_weight"], roll["net_weight"]) for roll in updated["roll_entries"]] == [
        (3, 47),
        (2, 58),
    ]
    assert updated["total_net_weight"] == "105.00"


def test_roll_tare_rejects_more_than_two_decimal_places_and_tare_above_gross(connection):
    card_id = import_and_release_card("25542")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])

    too_precise = db.update_roll_weight(card_id, roll_id, card["version"], "50.00", "1.234")
    unchanged = db.fetch_terminal_card_detail(card_id)
    too_large = db.update_roll_weight(card_id, roll_id, unchanged["version"], "50.00", "60.00")

    assert not too_precise.ok
    assert too_precise.messages == ("Шпула поддържа най-много два знака след десетичната запетая.",)
    assert not too_large.ok
    assert too_large.messages == ("Бруто теглото не може да бъде по-малко от шпулата.",)
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py::test_database_initialization_adds_roll_entry_tare_weight_to_existing_table tests/test_baseline.py::test_database_initialization_recalculates_legacy_roll_net_from_roll_tare tests/test_roll_entry.py::test_new_roll_copies_current_default_tare_without_mutating_existing_rolls tests/test_roll_entry.py::test_editing_roll_tare_recalculates_only_that_roll_and_not_default_tare tests/test_roll_entry.py::test_roll_tare_rejects_more_than_two_decimal_places_and_tare_above_gross -q
```

Expected before implementation: failures mention missing `tare_weight` on `roll_entries` and missing `db.update_roll_weight`.

## Task 2: Add Roll Tare Schema And Migration

**Files:**
- Modify: `app/db.py`

- [ ] **Step 1: Add the column to new databases**

In the `CREATE TABLE IF NOT EXISTS roll_entries` block in `app/db.py`, insert `tare_weight` between `gross_weight` and `net_weight`:

```python
CREATE TABLE IF NOT EXISTS roll_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    order_number TEXT NOT NULL,
    roll_number INTEGER NOT NULL CHECK (roll_number >= 1),
    gross_weight NUMERIC CHECK (gross_weight IS NULL OR gross_weight >= 0),
    tare_weight NUMERIC CHECK (tare_weight IS NULL OR tare_weight >= 0),
    net_weight NUMERIC CHECK (net_weight IS NULL OR net_weight >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (card_id, roll_number)
);
```

- [ ] **Step 2: Add migration helper**

After `ensure_column(...)`, add:

```python
def ensure_roll_entry_tare_weight(connection: sqlite3.Connection) -> None:
    ensure_column(
        connection,
        "roll_entries",
        "tare_weight",
        "NUMERIC CHECK (tare_weight IS NULL OR tare_weight >= 0)",
    )
    connection.execute(
        """
        UPDATE roll_entries
        SET tare_weight = (
            SELECT cards.tare_weight
            FROM cards
            WHERE cards.id = roll_entries.card_id
        )
        WHERE tare_weight IS NULL
          AND EXISTS (
              SELECT 1
              FROM cards
              WHERE cards.id = roll_entries.card_id
                AND cards.tare_weight IS NOT NULL
          )
        """
    )
    connection.execute(
        """
        UPDATE roll_entries
        SET net_weight = CASE
            WHEN gross_weight IS NOT NULL
             AND tare_weight IS NOT NULL
             AND CAST(gross_weight AS NUMERIC) >= CAST(tare_weight AS NUMERIC)
                THEN CAST(gross_weight AS NUMERIC) - CAST(tare_weight AS NUMERIC)
            ELSE NULL
        END
        WHERE gross_weight IS NOT NULL
        """
    )
```

- [ ] **Step 3: Call migration from `init_db()`**

In `init_db()`, after `connection.executescript(SCHEMA_SQL)` and before `backfill_card_import_sources(connection)`, add:

```python
        ensure_roll_entry_tare_weight(connection)
```

Keep the existing `ensure_column(connection, "cards", "max_roll_weight", "TEXT")` call.

- [ ] **Step 4: Run migration tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py::test_database_initialization_adds_roll_entry_tare_weight_to_existing_table tests/test_baseline.py::test_database_initialization_recalculates_legacy_roll_net_from_roll_tare -q
```

Expected: both tests pass.

## Task 3: Change Roll Fetching, Totals, And Tare Summary Helpers

**Files:**
- Modify: `app/db.py`

- [ ] **Step 1: Replace `fetch_roll_entries_and_totals` signature and implementation**

Replace:

```python
def fetch_roll_entries_and_totals(
    connection: sqlite3.Connection,
    card_id: int,
    tare_weight: Any,
) -> dict[str, Any]:
```

with:

```python
def fetch_roll_entries_and_totals(
    connection: sqlite3.Connection,
    card_id: int,
) -> dict[str, Any]:
```

Inside the function, select `tare_weight` and calculate totals from stored per-roll values:

```python
    rows = connection.execute(
        """
        SELECT id, roll_number, gross_weight, tare_weight, net_weight, updated_at
        FROM roll_entries
        WHERE card_id = ?
        ORDER BY roll_number
        """,
        (card_id,),
    ).fetchall()
    roll_entries = rows_to_dicts(rows)
    gross_rolls = [entry for entry in roll_entries if entry["gross_weight"] is not None]
    gross_values = [
        decimal_from_database(entry["gross_weight"])
        for entry in gross_rolls
    ]
    gross_values = [gross for gross in gross_values if gross is not None]
    net_values = [
        decimal_from_database(entry["net_weight"])
        for entry in gross_rolls
        if entry["net_weight"] is not None
    ]
    net_values = [net for net in net_values if net is not None]
    roll_count = len(gross_values)
    total_gross = sum(gross_values, Decimal("0"))
    total_net = (
        sum(net_values, Decimal("0"))
        if roll_count == len(net_values)
        else None
    )
    next_roll_number = (
        max((int(entry["roll_number"]) for entry in roll_entries), default=0) + 1
    )

    return {
        "roll_entries": roll_entries,
        "roll_count": roll_count,
        "next_roll_number": next_roll_number,
        "total_gross_weight": decimal_to_display(total_gross),
        "total_net_weight": decimal_to_display(total_net) if total_net is not None else None,
        "tare_summary_display": roll_tare_summary_display(roll_entries),
    }
```

- [ ] **Step 2: Add derived tare summary helper**

Near `fetch_roll_entries_and_totals`, add:

```python
def decimal_to_tare_summary_display(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.1")), "f")


def roll_tare_summary_display(roll_entries: list[dict[str, Any]]) -> str | None:
    tare_values = [
        decimal_from_database(entry.get("tare_weight"))
        for entry in roll_entries
        if entry.get("gross_weight") is not None and entry.get("tare_weight") is not None
    ]
    tare_values = [tare for tare in tare_values if tare is not None]
    if not tare_values:
        return None

    lowest = min(tare_values)
    highest = max(tare_values)
    if lowest == highest:
        return decimal_to_tare_summary_display(lowest)
    return f"{decimal_to_tare_summary_display(lowest)}-{decimal_to_tare_summary_display(highest)}"
```

- [ ] **Step 3: Update callers**

In both `fetch_admin_card_detail()` and `fetch_terminal_card_detail()`, replace:

```python
        roll_data = fetch_roll_entries_and_totals(connection, card_id, card["tare_weight"])
```

with:

```python
        roll_data = fetch_roll_entries_and_totals(connection, card_id)
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_roll_entry.py::test_gross_and_net_totals_calculate_with_tare tests/test_roll_entry.py::test_new_roll_copies_current_default_tare_without_mutating_existing_rolls -q
```

Expected at this point: existing total test may still fail until roll insert/update logic is changed in the next task.

## Task 4: Change Default Tare And Roll Mutation Logic

**Files:**
- Modify: `app/db.py`

- [ ] **Step 1: Replace net helper**

Rename or replace `net_weight_for_gross` with this more explicit helper:

```python
def net_weight_for_roll(
    gross_weight: Decimal | None,
    tare_weight: Decimal | None,
) -> Decimal | None:
    if gross_weight is None or tare_weight is None:
        return None

    net_weight = gross_weight - tare_weight
    if net_weight < 0:
        return None
    return net_weight
```

Update all call sites from `net_weight_for_gross(...)` to `net_weight_for_roll(...)`.

- [ ] **Step 2: Simplify `update_tare_weight()` so it updates only the default**

In `update_tare_weight()`, remove the existing query over `roll_entries`, the recalculation loop, and the `executemany` update. The function should parse and version-check, then only run:

```python
        connection.execute(
            """
            UPDATE cards
            SET tare_weight = ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                decimal_to_storage(parsed_tare) if parsed_tare is not None else None,
                card_id,
            ),
        )
```

Keep the existing success messages.

- [ ] **Step 3: Change `add_roll_gross_weight()` to copy default tare**

Inside `add_roll_gross_weight()`, keep gross parsing and version/status validation. Replace the current net calculation with:

```python
        default_tare = decimal_from_database(card["tare_weight"])
        net = net_weight_for_roll(parsed_gross, default_tare)
        if default_tare is not None and net is None:
            return RuleResult(
                False,
                ("Бруто теглото не може да бъде по-малко от шпулата.",),
            )
```

Update the insert statement to include `tare_weight`:

```python
            INSERT INTO roll_entries (
                card_id,
                order_number,
                roll_number,
                gross_weight,
                tare_weight,
                net_weight
            )
            VALUES (?, ?, ?, ?, ?, ?)
```

and values:

```python
                decimal_to_storage(parsed_gross),
                decimal_to_storage(default_tare) if default_tare is not None else None,
                decimal_to_storage(net) if net is not None else None,
```

- [ ] **Step 4: Add `update_roll_weight()`**

Add this function before `delete_roll_entry()`:

```python
def update_roll_weight(
    card_id: int,
    roll_id: int,
    loaded_version: int,
    gross_weight: str,
    tare_weight: str,
) -> RuleResult:
    parsed_gross, gross_parse_error = parse_weight(
        gross_weight,
        "Бруто тегло",
        allow_blank=True,
    )
    if gross_parse_error:
        return RuleResult(False, (gross_parse_error,))

    parsed_tare, tare_parse_error = parse_weight(
        tare_weight,
        "Шпула",
        allow_blank=True,
    )
    if tare_parse_error:
        return RuleResult(False, (tare_parse_error,))

    with connect() as connection:
        card = fetch_roll_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        roll_entry_result = validate_card_allows_roll_entry(card)
        if not roll_entry_result.ok:
            return roll_entry_result

        roll = connection.execute(
            """
            SELECT id, roll_number, gross_weight, tare_weight
            FROM roll_entries
            WHERE id = ?
              AND card_id = ?
            """,
            (roll_id, card_id),
        ).fetchone()
        if not roll:
            return RuleResult(False, ("Ролката не е намерена.",))

        if (
            card["status"] in PRODUCTION_COMPLETE_STATUSES
            and parsed_gross is None
            and roll["gross_weight"] is not None
        ):
            gross_roll_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM roll_entries
                    WHERE card_id = ?
                      AND gross_weight IS NOT NULL
                    """,
                    (card_id,),
                ).fetchone()[0]
            )
            if gross_roll_count <= 1:
                return RuleResult(
                    False,
                    ("Завършените карти трябва да запазят поне едно бруто тегло на ролка.",),
                )

        net = net_weight_for_roll(parsed_gross, parsed_tare)
        if parsed_gross is not None and parsed_tare is not None and net is None:
            return RuleResult(
                False,
                ("Бруто теглото не може да бъде по-малко от шпулата.",),
            )

        connection.execute(
            """
            UPDATE roll_entries
            SET gross_weight = ?,
                tare_weight = ?,
                net_weight = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                decimal_to_storage(parsed_gross) if parsed_gross is not None else None,
                decimal_to_storage(parsed_tare) if parsed_tare is not None else None,
                decimal_to_storage(net) if net is not None else None,
                roll_id,
            ),
        )
        connection.execute(
            """
            UPDATE cards
            SET version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (card_id,),
        )

    return RuleResult(True, (f"Ролка {roll['roll_number']} е записана.",))
```

- [ ] **Step 5: Keep a compatibility wrapper for older direct callers**

Replace the old body of `update_roll_gross_weight(...)` with:

```python
def update_roll_gross_weight(
    card_id: int,
    roll_id: int,
    loaded_version: int,
    gross_weight: str,
) -> RuleResult:
    with connect() as connection:
        roll = connection.execute(
            """
            SELECT tare_weight
            FROM roll_entries
            WHERE id = ?
              AND card_id = ?
            """,
            (roll_id, card_id),
        ).fetchone()
    if not roll:
        return RuleResult(False, ("Ролката не е намерена.",))
    existing_tare = decimal_from_database(roll["tare_weight"])
    return update_roll_weight(
        card_id=card_id,
        roll_id=roll_id,
        loaded_version=loaded_version,
        gross_weight=gross_weight,
        tare_weight=decimal_to_storage(existing_tare) if existing_tare is not None else "",
    )
```

This keeps existing tests and call sites working until they are updated.

- [ ] **Step 6: Run roll behavior tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_roll_entry.py::test_gross_and_net_totals_calculate_with_tare tests/test_roll_entry.py::test_new_roll_copies_current_default_tare_without_mutating_existing_rolls tests/test_roll_entry.py::test_editing_roll_tare_recalculates_only_that_roll_and_not_default_tare tests/test_roll_entry.py::test_roll_tare_rejects_more_than_two_decimal_places_and_tare_above_gross -q
```

Expected: all listed tests pass.

## Task 5: Update Finish Validation For Per-Roll Tare

**Files:**
- Modify: `app/db.py`
- Modify: `tests/test_finish_cancel_history.py`

- [ ] **Step 1: Add failing finish validation test**

In `tests/test_finish_cancel_history.py`, add after the existing finish validation tests:

```python
def test_finish_blocks_gross_roll_without_roll_tare(connection):
    card_id = import_and_release_card("25640")
    start_card(card_id)
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO roll_entries (card_id, order_number, roll_number, gross_weight, tare_weight, net_weight)
            VALUES (?, '25640', 1, 25.00, NULL, NULL)
            """,
            (card_id,),
        )

    result = db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"])

    assert not result.ok
    assert result.messages == ("Всяка ролка с бруто тегло трябва да има шпула преди приключване.",)
```

- [ ] **Step 2: Update `validate_card_ready_to_finish()`**

Remove the existing card-level tare requirement:

```python
    if card["tare_weight"] is None:
        return RuleResult(False, ("Шпула е задължителна преди приключване.",))
```

Update the roll query to include tare and net:

```python
        SELECT roll_number, gross_weight, tare_weight, net_weight
```

After the `gross_rolls` check, add:

```python
    if any(roll["tare_weight"] is None or roll["net_weight"] is None for roll in gross_rolls):
        return RuleResult(
            False,
            ("Всяка ролка с бруто тегло трябва да има шпула преди приключване.",),
        )
```

Keep the existing empty-row gap validation.

- [ ] **Step 3: Run finish tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_finish_cancel_history.py::test_finish_blocks_gross_roll_without_roll_tare tests/test_finish_cancel_history.py -q
```

Expected: the new test and existing finish/cancel/history tests pass.

## Task 6: Update Routes And Form Parsing

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Import `update_roll_weight`**

At the import list from `app.db`, add:

```python
    update_roll_weight,
```

Keep `update_roll_gross_weight` only if other routes/tests still import it directly.

- [ ] **Step 2: Change roll ledger form parsing**

Replace `roll_ledger_from_form` with:

```python
def roll_ledger_from_form(
    form: Any,
) -> tuple[str, dict[int, dict[str, str]], set[int], list[str]]:
    roll_updates: dict[int, dict[str, str]] = {}
    delete_roll_ids: set[int] = set()
    new_gross_weights: list[str] = []

    for key, value in form.multi_items():
        text_value = str(value or "")
        if key.startswith("gross_weight__"):
            roll_id = int(key.removeprefix("gross_weight__"))
            roll_updates.setdefault(roll_id, {})["gross_weight"] = text_value
        elif key.startswith("tare_weight__"):
            roll_id = int(key.removeprefix("tare_weight__"))
            roll_updates.setdefault(roll_id, {})["tare_weight"] = text_value
        elif key == "delete_roll_id":
            delete_roll_ids.add(int(text_value))
        elif key == "new_gross_weight":
            new_gross_weights.append(text_value)

    return (
        str(form.get("tare_weight") or ""),
        roll_updates,
        delete_roll_ids,
        new_gross_weights,
    )
```

Malformed IDs still raise `ValueError`, preserving existing route error behavior.

- [ ] **Step 3: Update terminal/admin single-row routes**

In `save_admin_roll_weight()` and `save_roll_weight()`, add:

```python
    tare_weight: str = Form(""),
```

and replace calls to `update_roll_gross_weight(...)` with:

```python
        roll_result = update_roll_weight(
            card_id=card_id,
            roll_id=roll_id,
            loaded_version=parsed_version,
            gross_weight=gross_weight,
            tare_weight=tare_weight,
        )
```

- [ ] **Step 4: Run route-level tests that touch roll forms**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_stale_tare_submit_renders_refresh_alert_without_overwrite tests/test_admin_card_detail_redesign.py::test_admin_roll_ledger_route_blocks_malformed_roll_ids -q
```

Expected: pass after the admin ledger update in the next task; malformed ID behavior should remain unchanged.

## Task 7: Update Admin Roll Ledger Backend

**Files:**
- Modify: `app/db.py`
- Modify: `tests/test_admin_card_detail_redesign.py`
- Modify: `tests/test_admin_production_corrections.py`

- [ ] **Step 1: Change `update_admin_roll_ledger` type signatures**

Change both public and private signatures from:

```python
    roll_updates: dict[int, str],
```

to:

```python
    roll_updates: dict[int, dict[str, str]],
```

- [ ] **Step 2: Parse existing roll gross and tare updates**

Inside `_update_admin_roll_ledger`, change the existing roll query to:

```python
        SELECT id, roll_number, gross_weight, tare_weight
```

Replace `existing_gross_by_id` with:

```python
    existing_values_by_id = {
        int(row["id"]): {
            "gross_weight": decimal_from_database(row["gross_weight"]),
            "tare_weight": decimal_from_database(row["tare_weight"]),
        }
        for row in existing_rolls
    }
```

Replace parsed update loop with:

```python
    parsed_updates: dict[int, dict[str, Decimal | None]] = {}
    for roll_id, values in roll_updates.items():
        if roll_id in delete_roll_ids:
            continue
        current = existing_values_by_id[roll_id]
        gross_text = values.get(
            "gross_weight",
            decimal_to_storage(current["gross_weight"]) if current["gross_weight"] is not None else "",
        )
        tare_text = values.get(
            "tare_weight",
            decimal_to_storage(current["tare_weight"]) if current["tare_weight"] is not None else "",
        )
        parsed_gross, parse_error = parse_weight(
            gross_text,
            "Бруто тегло",
            allow_blank=True,
        )
        if parse_error:
            return RuleResult(False, (parse_error,))
        parsed_tare, parse_error = parse_weight(
            tare_text,
            "Шпула",
            allow_blank=True,
        )
        if parse_error:
            return RuleResult(False, (parse_error,))
        parsed_updates[roll_id] = {
            "gross_weight": parsed_gross,
            "tare_weight": parsed_tare,
        }
```

- [ ] **Step 3: Update mutation detection**

Replace the existing `roll_mutation_requested` comparison with:

```python
    if not roll_mutation_requested:
        roll_mutation_requested = any(
            parsed_values["gross_weight"] != existing_values_by_id[roll_id]["gross_weight"]
            or parsed_values["tare_weight"] != existing_values_by_id[roll_id]["tare_weight"]
            for roll_id, parsed_values in parsed_updates.items()
        )
```

- [ ] **Step 4: Recalculate remaining and new roll net values**

In the loop over existing rolls, use parsed per-roll tare:

```python
        parsed_values = parsed_updates.get(roll_id)
        if parsed_values is None:
            gross = decimal_from_database(roll["gross_weight"])
            row_tare = decimal_from_database(roll["tare_weight"])
        else:
            gross = parsed_values["gross_weight"]
            row_tare = parsed_values["tare_weight"]
        if gross is not None:
            gross_roll_count += 1
        net = net_weight_for_roll(gross, row_tare)
        if gross is not None and row_tare is not None and net is None:
            return RuleResult(
                False,
                ("Бруто теглото не може да бъде по-малко от шпулата.",),
            )
        remaining_updates[roll_id] = (gross, row_tare, net)
```

For new rolls, continue using the parsed card default tare:

```python
    for gross in parsed_new:
        net = net_weight_for_roll(gross, parsed_tare)
        if parsed_tare is not None and net is None:
            return RuleResult(
                False,
                ("Бруто теглото не може да бъде по-малко от шпулата.",),
            )
```

- [ ] **Step 5: Persist per-roll tare**

Update existing roll update SQL:

```python
            UPDATE roll_entries
            SET gross_weight = ?,
                tare_weight = ?,
                net_weight = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND card_id = ?
```

with values:

```python
                decimal_to_storage(gross) if gross is not None else None,
                decimal_to_storage(row_tare) if row_tare is not None else None,
                decimal_to_storage(net) if net is not None else None,
```

Update new roll insert SQL to include `tare_weight`, using `parsed_tare`.

- [ ] **Step 6: Update tests that call `update_admin_roll_ledger`**

For existing direct calls with one gross update, change:

```python
roll_updates={int(first_roll["id"]): "55.00"},
```

to:

```python
roll_updates={int(first_roll["id"]): {"gross_weight": "55.00", "tare_weight": "1.50"}},
```

For calls with no row updates, keep `roll_updates={}`.

Add this focused test to `tests/test_admin_production_corrections.py`:

```python
def test_admin_roll_ledger_updates_per_roll_tare_without_changing_default_tare(connection):
    card_id = release_ready_card("26040")
    start_card(card_id)
    add_tare(card_id, "2.00")
    add_roll(card_id, "50.00")
    card = db.fetch_admin_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])

    result = db.update_admin_roll_ledger(
        card_id,
        card["version"],
        tare_weight="2.00",
        roll_updates={roll_id: {"gross_weight": "50.00", "tare_weight": "3.00"}},
        delete_roll_ids=set(),
        new_gross_weights=[],
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert updated["tare_weight"] == 2
    assert updated["roll_entries"][0]["tare_weight"] == 3
    assert updated["roll_entries"][0]["net_weight"] == 47
```

- [ ] **Step 7: Run admin roll tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_production_corrections.py::test_admin_roll_ledger_updates_per_roll_tare_without_changing_default_tare tests/test_admin_card_detail_redesign.py::test_admin_roll_ledger_updates_tare_rolls_deletes_and_adds tests/test_admin_card_detail_redesign.py::test_admin_global_save_updates_order_materials_and_roll_data -q
```

Expected: all listed tests pass.

## Task 8: Update Workstation Roll Table UI

**Files:**
- Modify: `app/templates/terminal.html`
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Update terminal roll table markup**

In `app/templates/terminal.html`, change the roll head from:

```html
<div class="roll-head">
  <div>№</div>
  <div>Бруто кг</div>
  <div>Нето</div>
</div>
```

to:

```html
<div class="roll-head">
  <div>№</div>
  <div>Бруто кг</div>
  <div>Шпула кг</div>
  <div>Нето кг</div>
</div>
```

Change each roll row form to include one editable gross cell, one editable tare cell, and one read-only net cell:

```html
<div class="roll-row" data-roll-id="{{ roll.id }}">
  <div>{{ roll.roll_number }}</div>
  <div class="roll-weight-cell">
    <form action="/terminal/cards/{{ selected_card.id }}/rolls/{{ roll.id }}" method="post">
      <input type="hidden" name="loaded_version" value="{{ selected_card.version }}">
      <input type="hidden" name="tare_weight" value="{{ roll.tare_weight if roll.tare_weight is not none else '' }}">
      <input type="number" name="gross_weight" min="0" step="0.01" value="{{ roll.gross_weight if roll.gross_weight is not none else '' }}" {% if not can_edit_rolls %}disabled{% endif %}>
    </form>
    <div class="roll-row-error-slot field-error-slot" data-feedback-roll-id="{{ roll.id }}">
      {% set roll_errors = terminal_feedback.errors.roll_rows.get(roll.id) %}
      {% if roll_errors %}
        <div class="inline-error" role="alert">
          {% for message in roll_errors %}
            <p>{{ message }}</p>
          {% endfor %}
        </div>
      {% endif %}
    </div>
  </div>
  <div class="roll-weight-cell">
    <form action="/terminal/cards/{{ selected_card.id }}/rolls/{{ roll.id }}" method="post">
      <input type="hidden" name="loaded_version" value="{{ selected_card.version }}">
      <input type="hidden" name="gross_weight" value="{{ roll.gross_weight if roll.gross_weight is not none else '' }}">
      <input type="number" name="tare_weight" min="0" step="0.01" value="{{ roll.tare_weight if roll.tare_weight is not none else '' }}" {% if not can_edit_rolls %}disabled{% endif %}>
    </form>
  </div>
  <div>{{ roll.net_weight if roll.net_weight is not none else "-" }}</div>
</div>
```

The gross and tare inputs submit to the same route. Each form carries the other current value as a hidden field so editing one value does not clear the other. Keep the submitted field names exactly as `loaded_version`, `gross_weight`, and `tare_weight`.

For the empty state, use four cells:

```html
<div class="roll-row"><div>-</div><div>Няма въведени ролки.</div><div>-</div><div>-</div></div>
```

- [ ] **Step 2: Update terminal CSS inside the template**

In the `.roll-head, .roll-row` rule, change:

```css
grid-template-columns: 48px minmax(0, 1fr) minmax(0, 1fr);
```

to:

```css
grid-template-columns: 44px minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
```

Run this search and update every `.roll-head` or `.roll-row` grid-template found in compact viewport blocks to the same four-column structure:

```bash
rg -n "\\.roll-head|\\.roll-row|grid-template-columns" app/templates/terminal.html
```

- [ ] **Step 3: Add terminal render tests**

In `tests/test_terminal_v8_render.py`, add:

```python
def test_terminal_roll_table_renders_editable_gross_and_tare_with_readonly_net(connection):
    card_id = release_ready_card("26196", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    roll = card["roll_entries"][0]

    html = render_terminal(card_id)
    row_html = roll_row_block(html, int(roll["id"]))

    assert "Бруто кг" in html
    assert "Шпула кг" in html
    assert "Нето кг" in html
    assert 'name="gross_weight"' in row_html
    assert 'name="tare_weight"' in row_html
    assert 'value="50"' in row_html
    assert 'value="2"' in row_html
    assert ">48<" in row_html
```

- [ ] **Step 4: Run terminal render tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_roll_table_renders_editable_gross_and_tare_with_readonly_net tests/test_terminal_v8_render.py::test_terminal_v8_roll_rows_are_compact_and_vertically_centered -q
```

Expected: both tests pass after CSS/markup updates.

## Task 9: Update Admin Roll Ledger UI

**Files:**
- Modify: `app/templates/admin_card_detail.html`
- Modify: `app/static/css/app.css`
- Modify: `tests/test_admin_card_detail_redesign.py`

- [ ] **Step 1: Update admin ledger header and rows**

In `app/templates/admin_card_detail.html`, change the roll ledger header to:

```html
<div class="admin-ledger-head">
  <div>№</div>
  <div>Бруто, кг</div>
  <div>Шпула, кг</div>
  <div>Нето, кг</div>
  <div><span class="visually-hidden">Изтриване</span></div>
</div>
```

Change each row to include an editable tare input:

```html
<div class="admin-ledger-row admin-roll-ledger-row">
  <div>{{ roll.roll_number }}</div>
  <div>
    <input type="number" name="gross_weight__{{ roll.id }}" min="0" step="0.01" value="{{ roll.gross_weight if roll.gross_weight is not none else '' }}">
  </div>
  <div>
    <input type="number" name="tare_weight__{{ roll.id }}" min="0" step="0.01" value="{{ roll.tare_weight if roll.tare_weight is not none else '' }}">
  </div>
  <div class="readonly-cell">{{ roll.net_weight if roll.net_weight is not none else "-" }}</div>
  <div class="ledger-row-actions">
    <button class="admin-row-delete-button" type="submit" form="roll-delete-{{ roll.id }}" aria-label="Изтрий ролка {{ roll.roll_number }}">×</button>
  </div>
</div>
```

- [ ] **Step 2: Update admin CSS grid**

In `app/static/css/app.css`, update:

```css
.roll-ledger .admin-ledger-head,
.roll-ledger .admin-ledger-row {
  grid-template-columns: 70px minmax(140px, 0.6fr) minmax(140px, 0.6fr) 110px;
}
```

to:

```css
.roll-ledger .admin-ledger-head,
.roll-ledger .admin-ledger-row {
  grid-template-columns: 70px minmax(120px, 0.6fr) minmax(120px, 0.6fr) minmax(120px, 0.6fr) 110px;
}
```

Update any mobile/compact duplicate `.roll-ledger` grid rules to the same five-column shape where present.

- [ ] **Step 3: Add admin markup test**

In `tests/test_admin_card_detail_redesign.py`, add:

```python
def test_admin_roll_ledger_renders_editable_per_roll_tare(connection):
    card_id = prepare_dense_completed_card("27120", roll_count=1)
    card = db.fetch_admin_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])

    html = render_admin_detail(card_id)

    assert "Шпула, кг" in html
    assert f'name="gross_weight__{roll_id}"' in html
    assert f'name="tare_weight__{roll_id}"' in html
```

- [ ] **Step 4: Run admin UI tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py::test_admin_roll_ledger_renders_editable_per_roll_tare tests/test_admin_card_detail_redesign.py::test_admin_detail_uses_single_roll_ledger_without_repeated_save_buttons -q
```

Expected: both tests pass.

## Task 10: Update Print Readiness And Summary Tare Display

**Files:**
- Modify: `app/printing.py`
- Modify: `tests/test_print_output.py`

- [ ] **Step 1: Add print tests**

In `tests/test_print_output.py`, update `make_completed_printable_card()` insert SQL to include `tare_weight` on each roll:

```python
                INSERT INTO roll_entries (
                    card_id, order_number, roll_number, gross_weight, tare_weight, net_weight
                )
                VALUES (?, ?, ?, ?, ?, ?)
```

with values:

```python
                (card_id, order_number, roll_number, gross_weight, "1.25", net_weight),
```

Add:

```python
def test_print_summary_tare_uses_range_for_mixed_roll_tares(connection):
    card_id = make_completed_printable_card("27060", roll_count=2)
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE roll_entries
            SET tare_weight = 2.00,
                net_weight = CAST(gross_weight AS NUMERIC) - 2.00
            WHERE card_id = ?
              AND roll_number = 1
            """,
            (card_id,),
        )
        connection.execute(
            """
            UPDATE roll_entries
            SET tare_weight = 2.50,
                net_weight = CAST(gross_weight AS NUMERIC) - 2.50
            WHERE card_id = ?
              AND roll_number = 2
            """,
            (card_id,),
        )

    response = get_print_page(card_id)

    assert response.status_code == 200
    assert rendered_text(data_block(response.text, "data-summary-field", "tare")) == "2.0-2.5"


def test_print_readiness_blocks_gross_roll_without_tare(connection):
    card_id = make_completed_printable_card("27061", roll_count=1)
    with db.connect() as connection:
        connection.execute(
            "UPDATE roll_entries SET tare_weight = NULL, net_weight = NULL WHERE card_id = ?",
            (card_id,),
        )

    readiness = build_print_readiness(card_id)

    assert not readiness.ok
    assert "Всяка ролка с бруто тегло трябва да има шпула преди печат." in readiness.messages
```

- [ ] **Step 2: Update `validate_print_readiness()`**

Remove the card-level tare required message:

```python
    if card.get("tare_weight") is None:
        messages.append("Шпула е задължителна преди печат.")
```

Update `validate_print_weight_values()` values to include per-roll tare and net:

```python
    values = [
        card.get("total_gross_weight"),
        card.get("total_net_weight"),
        *(roll.get("gross_weight") for roll in gross_rolls),
        *(roll.get("tare_weight") for roll in gross_rolls),
        *(roll.get("net_weight") for roll in gross_rolls),
    ]
```

Add before numeric negativity checks:

```python
    if any(roll.get("tare_weight") is None or roll.get("net_weight") is None for roll in gross_rolls):
        return ["Всяка ролка с бруто тегло трябва да има шпула преди печат."]
```

Replace old gross-versus-card-tare negative check with:

```python
    net_values = [decimal_from_value(roll.get("net_weight")) for roll in gross_rolls]
    total_net = decimal_from_value(card.get("total_net_weight"))
    if total_net is not None and (total_net < 0 or any(net is not None and net < 0 for net in net_values)):
        return ["Нето теглото за печат не може да бъде отрицателно."]
```

- [ ] **Step 3: Add print tare summary helper**

In `app/printing.py`, add:

```python
def tare_summary_display(card: dict[str, Any]) -> str:
    tare_values = [
        decimal_from_value(roll.get("tare_weight"))
        for roll in gross_roll_entries(card)
        if roll.get("tare_weight") is not None
    ]
    tare_values = [tare for tare in tare_values if tare is not None]
    if not tare_values:
        return format_weight(card.get("tare_weight"))

    lowest = min(tare_values)
    highest = max(tare_values)
    if lowest == highest:
        return format_weight(lowest)
    return f"{format_weight(lowest)}-{format_weight(highest)}"
```

In `assemble_print_data()`, replace:

```python
        "tare_display": format_weight(card.get("tare_weight")),
```

with:

```python
        "tare_display": tare_summary_display(card),
```

- [ ] **Step 4: Run print tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_print_output.py::test_print_summary_tare_uses_range_for_mixed_roll_tares tests/test_print_output.py::test_print_readiness_blocks_gross_roll_without_tare tests/test_print_output.py::test_print_route_back_page_summary_weights_use_one_decimal -q
```

Expected: all listed tests pass.

## Task 11: Update Documentation And Milestone Notes

**Files:**
- Modify: `README.md`
- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update README product rules**

Replace the order-level tare language in the terminal workflow section:

```markdown
- The app needs one tare-weight field for the order.
- Tare weight means the actual weight of the roll core.
- The tare weight is the same for the whole order.
- Operators input gross weight for each roll.
- The app calculates net weight per roll from gross roll weight and order-level tare weight.
- The app calculates total net weight for the order from the roll net weights.
```

with:

```markdown
- The app keeps one current/default tare-weight field for the next roll.
- Tare weight means the actual weight of the roll core.
- Each saved roll stores its own tare weight.
- Changing the current/default tare affects only future rolls.
- Operators input gross weight for each roll and can correct that roll's tare weight.
- The app calculates net weight per roll from that roll's gross weight and that roll's tare weight.
- The app calculates total net weight for the order from the saved roll net weights.
```

In the data model section, replace:

```markdown
- Net weight is calculated as `gross weight - order tare weight`.
- Per-roll net weight formula: `roll_net_weight = roll_gross_weight - tare_weight`.
- Total net weight formula: `total_net_weight = total_gross_weight - (number_of_rolls * tare_weight)`.
- Tare weight is stored once on the order/card.
- The same tare weight applies to every roll in the order.
```

with:

```markdown
- Net weight is calculated as `roll gross weight - roll tare weight`.
- Per-roll net weight formula: `roll_net_weight = roll_gross_weight - roll_tare_weight`.
- Total net weight formula: `total_net_weight = sum(roll_net_weight)`.
- The card stores a current/default tare weight used only for newly added rolls.
- Each roll stores the tare value copied from the default at creation time, and that per-roll tare can be corrected later.
- If an order uses multiple tare values, summary display shows the lowest-to-highest tare range.
```

- [ ] **Step 2: Update implementation plan**

Add a new note under the current milestone state or next milestone section:

```markdown
- Roll-level tare redesign planned/implemented: card-level `tare_weight` is now the default for newly added rolls, each roll stores editable `tare_weight`, net totals sum per-roll net values, and mixed tare summaries display as a lowest-to-highest range.
```

Use `planned` if writing this note before implementation completes, and `implemented` only after tests and UI verification pass.

- [ ] **Step 3: Run docs-related grep check**

Run:

```bash
rg -n "same tare|order-level tare|order tare|tare_weight = total_gross|number_of_rolls \\* tare|same for the whole order" README.md IMPLEMENTATION_PLAN.md app tests
```

Expected: no remaining authoritative statements that the same tare applies to every roll. Historical plan files under `docs/superpowers/plans/` may still contain old context and do not need edits.

## Task 12: Full Focused Verification

**Files:**
- No code changes unless verification exposes defects.

- [ ] **Step 1: Run focused Python tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py tests/test_roll_entry.py tests/test_finish_cancel_history.py tests/test_admin_production_corrections.py tests/test_admin_card_detail_redesign.py tests/test_print_output.py tests/test_terminal_v8_render.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full pytest suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected: full test suite passes.

- [ ] **Step 3: Run syntax/import check**

Run:

```bash
source .venv/bin/activate
python -m compileall app tests
```

Expected: no syntax errors.

- [ ] **Step 4: Run diff whitespace check**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

## Task 13: Manual UI Verification With Playwright Screenshot

**Files:**
- No tracked source changes unless defects are found.
- Artifacts: `artifacts/ui-checks/roll-level-tare/`

- [ ] **Step 1: Start app against a temporary database**

Use a temporary runtime database, not `data/extrusion_terminal.sqlite3`.

Run:

```bash
mkdir -p .test-runtime/roll-level-tare artifacts/ui-checks/roll-level-tare
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/roll-level-tare/extrusion_terminal.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 18080
```

Expected: server starts on `127.0.0.1:18080`.

- [ ] **Step 2: Seed a card through app helpers**

In a separate shell:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/roll-level-tare/extrusion_terminal.sqlite3 python - <<'PY'
import csv
import io
from app import db
from app.importer import IMPORT_FIELDS, import_cards_from_csv

db.init_db()
row = {
    "order_number": "29901",
    "customer": "Tare Range Customer",
    "product_type": "PE film",
    "quantity_1": "200",
    "unit_1": "kg",
    "material": "LDPE",
    "size_thickness": "600/0.050",
    "extrusion_flag": "da",
    "raw_material_a": "LDPE A | 100%",
    "packaging_method": "rolls",
}
output = io.StringIO()
writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
writer.writeheader()
writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
result = import_cards_from_csv("roll-level-tare.csv", output.getvalue().encode("utf-8"))
assert result.rows_imported == 1, result
with db.connect() as connection:
    card_id = int(connection.execute("SELECT id FROM cards WHERE order_number = '29901'").fetchone()["id"])
assert db.release_card(card_id, 1, 1, max_roll_weight="60").ok
assert db.start_production_timing(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok
assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.50").ok
assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "60.00").ok
print(card_id)
PY
```

Expected: command prints the seeded card id.

- [ ] **Step 3: Capture workstation screenshot**

Run:

```bash
npx playwright screenshot --viewport-size=1366,768 http://127.0.0.1:18080/terminal/cards/1 artifacts/ui-checks/roll-level-tare/workstation-roll-tare-table.png
```

Expected: screenshot shows the roll table with editable gross/tare columns and read-only net values.

- [ ] **Step 4: Capture admin screenshot**

Run:

```bash
npx playwright screenshot --viewport-size=1440,900 http://127.0.0.1:18080/admin/cards/1 artifacts/ui-checks/roll-level-tare/admin-roll-tare-ledger.png
```

Expected: screenshot shows the admin roll ledger with editable gross/tare columns and read-only net values.

- [ ] **Step 5: Check visible values manually**

Open or inspect the screenshots and verify:

- Roll 1 displays gross `50`, tare `2`, net `48`.
- Roll 2 displays gross `60`, tare `2.5`, net `57.5`.
- The default tare input displays the latest default `2.5`.
- Net total displays `105.5` or rounded equivalent according to existing `whole_kg` display behavior.
- Inputs do not overlap or clip at workstation viewport size.

## Self-Review Checklist

- Spec coverage: data model, migration, default copy behavior, per-roll edit behavior, admin correction, finish validation, print readiness, mixed tare summary, documentation, automated tests, and UI verification are covered.
- Placeholder scan: this plan intentionally contains no `TBD`, `TODO`, or unspecified edge-case steps.
- Type consistency: the new public roll update function is consistently named `update_roll_weight`; admin ledger roll updates are consistently shaped as `dict[int, dict[str, str]]`.
- Scope check: this is one cohesive workflow slice; it does not add users, roles, non-extrusion workflows, Excel writeback, or ERP expansion.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-roll-level-tare-weights.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Do not stage or commit unless the user explicitly asks.
