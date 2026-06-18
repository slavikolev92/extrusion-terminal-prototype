# Admin Card Detail Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `/admin/cards/{card_id}` into a compact, section-based admin correction page that removes duplicated materials, rolls, and timing displays while preserving backend conflict checks and production-data safety.

**Architecture:** Keep the current FastAPI/Jinja/server-rendered architecture. Add small bulk admin correction helpers in `app/db.py` for materials, rolls, and timing so the UI can use one form and one save action per section instead of one form per row. Restructure `admin_card_detail.html` into summary, compact order details, unified materials, unified roll ledger, unified timing ledger, and collapsed system data.

**Tech Stack:** FastAPI, direct `sqlite3`, Jinja2 templates, existing CSS in `app/static/css/app.css`, pytest, Playwright.

---

## File Structure

- Modify `app/db.py`
  - Add `update_admin_material_ledger`.
  - Add `update_admin_roll_ledger`.
  - Add `update_admin_timing_ledger`.
  - Keep existing single-row helpers in place for compatibility unless tests prove they are unused.

- Modify `app/main.py`
  - Add parsers for material, roll, and timing ledger forms.
  - Add section-level POST routes:
    - `/admin/cards/{card_id}/materials-ledger`
    - `/admin/cards/{card_id}/roll-ledger`
    - `/admin/cards/{card_id}/timing-ledger`
  - Keep existing route names unless removing them is covered by tests.

- Replace major structure in `app/templates/admin_card_detail.html`
  - Header + production summary.
  - Compact order details.
  - One unified materials table.
  - One roll ledger table.
  - One timing ledger table.
  - Collapsed/low-emphasis system data.

- Modify `app/static/css/app.css`
  - Add dense admin detail grid classes.
  - Add ledger-table styles.
  - Add compact field-width utilities.
  - Add danger/secondary row-action styling.

- Add `tests/test_admin_card_detail_redesign.py`
  - Render-focused tests proving duplication is gone.
  - Route/helper tests for bulk material, roll, and timing saves.
  - Stale-version tests for new bulk endpoints.

- Update `IMPLEMENTATION_PLAN.md`
  - Add this as the active next milestone once implementation begins.

---

## Design Targets

The final admin detail page should follow this order:

1. Header and production summary
2. Compact order details
3. Unified materials ledger
4. Unified roll ledger
5. Unified timing ledger
6. System data

Use the rule: one logical section, one table where repeated data exists, one save button.

Do not introduce users, roles, permissions, JavaScript-heavy editing, modals, or a frontend framework.

---

### Task 1: Add Render Regression Tests For The New Page Shape

**Files:**
- Create: `tests/test_admin_card_detail_redesign.py`
- Read: `tests/test_admin_production_corrections.py`
- Read: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Create fixture helpers for a dense completed admin card**

Create `tests/test_admin_card_detail_redesign.py` with helper functions copied/adapted from existing tests. Keep helpers local to avoid broad test refactors.

```python
from __future__ import annotations

import csv
import io

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import db
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import admin_card_detail_context


def csv_bytes(*rows: dict[str, str]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")


def extrusion_row(order_number: str, **overrides: str) -> dict[str, str]:
    row = {
        "order_number": order_number,
        "order_date": "2026-06-18",
        "delivery_date": "2026-06-20",
        "customer": "Admin Detail Redesign Customer",
        "city": "Plovdiv",
        "product_type": "TSF 890/0.082",
        "quantity_1": "3250.50",
        "unit_1": "kg",
        "quantity_2": "60",
        "unit_2": "rolls",
        "product_form": "flat film",
        "material": "LDPE / LLDPE",
        "size_thickness": "890 / 0.082",
        "notes": "Dense admin detail redesign fixture.",
        "extrusion_flag": "da",
        "extrusion_folding": "single fold",
        "extrusion_next_operation": "rewind",
        "extrusion_treatment": "corona",
        "raw_material_a": "Planned LDPE A",
        "raw_material_b": "Planned LLDPE B",
        "raw_material_c": "Planned HDPE C",
        "linear_pe": "Planned mLLDPE",
        "antistatic": "Planned antistatic",
        "masterbatch": "Planned masterbatch",
        "chalk": "Planned chalk",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def card_version(card_id: int) -> int:
    return int(db.fetch_admin_card_detail(card_id)["version"])


def import_ready_card(order_number: str, **overrides: str) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number, **overrides)),
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


def prepare_dense_completed_card(order_number: str = "27000", roll_count: int = 12) -> int:
    card_id = import_ready_card(order_number)
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="62.50",
    ).ok
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_terminal_recipe_actual_entries(
        card_id,
        card_version(card_id),
        {
            "raw_material_a": {"actual_material_used": "Actual LDPE A", "batch_lot": "LOT-A"},
            "raw_material_b": {"actual_material_used": "Actual LLDPE B", "batch_lot": "LOT-B"},
            "raw_material_c": {"actual_material_used": "Actual HDPE C", "batch_lot": "LOT-C"},
            "linear_pe": {"actual_material_used": "Actual mLLDPE", "batch_lot": "LOT-L"},
            "antistatic": {"actual_material_used": "Actual antistatic", "batch_lot": "LOT-AS"},
            "masterbatch": {"actual_material_used": "Actual masterbatch", "batch_lot": "LOT-MB"},
            "chalk": {"actual_material_used": "Actual chalk", "batch_lot": "LOT-CH"},
        },
        raw_material_brand_grade="Grade A",
    ).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.25").ok
    for index in range(roll_count):
        assert db.add_roll_gross_weight(card_id, card_version(card_id), f"{51 + index / 10:.2f}").ok
    assert db.finish_card(card_id, card_version(card_id)).ok
    return card_id


def render_admin_detail(card_id: int, **extra: object) -> str:
    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["url_for"] = lambda name, **kwargs: f"/static{kwargs.get('path', '')}"
    context = admin_card_detail_context(card_id, **extra)
    assert context is not None
    return env.get_template("admin_card_detail.html").render(**context)
```

- [ ] **Step 2: Add tests for section structure and removed duplicated material sections**

```python
def test_admin_detail_combines_recipe_and_machine_materials(connection):
    card_id = prepare_dense_completed_card("27001")

    html = render_admin_detail(card_id)

    assert "Материали" in html
    assert "Рецепта" not in html
    assert "Материал на машината" not in html
    assert html.count('name="planned_material__raw_material_a"') == 1
    assert html.count('name="actual_material__raw_material_a"') == 1
    assert html.count('name="batch_lot__raw_material_a"') == 1
    assert "Марка / клас за ред A" not in html
```

- [ ] **Step 3: Add tests for one roll ledger and one save action**

```python
def test_admin_detail_uses_single_roll_ledger_without_repeated_save_buttons(connection):
    card_id = prepare_dense_completed_card("27002", roll_count=12)

    html = render_admin_detail(card_id)

    assert html.count('class="admin-roll-ledger-row"') == 12
    assert html.count("Запази ролките") == 1
    assert "admin-roll-correction-row" not in html
    assert html.count(">Запази<") < 10
    assert html.count(">Изтрий<") < 10
    assert "Произведено количество" not in html
    assert "Общо произведено" in html
```

- [ ] **Step 4: Add tests for one timing ledger and one save action**

```python
def test_admin_detail_uses_single_timing_ledger_without_duplicate_segment_forms(connection):
    card_id = prepare_dense_completed_card("27003", roll_count=2)

    html = render_admin_detail(card_id)

    assert "Време" in html
    assert html.count("Запази времето") == 1
    assert "admin-timing-correction-row" not in html
    assert "timing-correction-form" not in html
```

- [ ] **Step 5: Run the new tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py -v
```

Expected: failures because the template still has separate `Рецепта`, `Материал на машината`, duplicated roll correction rows, and duplicated timing correction forms.

---

### Task 2: Add Bulk Material Ledger Backend Behavior

**Files:**
- Modify: `app/db.py`
- Modify: `app/main.py`
- Test: `tests/test_admin_card_detail_redesign.py`

- [ ] **Step 1: Add backend tests for material ledger updates**

Append:

```python
def test_admin_material_ledger_updates_planned_and_actual_fields(connection):
    card_id = prepare_dense_completed_card("27010", roll_count=1)
    loaded_version = card_version(card_id)

    result = db.update_admin_material_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        planned_materials={
            "raw_material_a": "Corrected planned A",
            "raw_material_b": "Corrected planned B",
            "raw_material_c": "Corrected planned C",
            "linear_pe": "Corrected linear",
            "antistatic": "Corrected antistatic",
            "masterbatch": "Corrected masterbatch",
            "chalk": "Corrected chalk",
        },
        actual_entries={
            "raw_material_a": {
                "actual_material_used": "Corrected actual A",
                "batch_lot": "Corrected batch A",
            },
            "raw_material_b": {
                "actual_material_used": "Corrected actual B",
                "batch_lot": "Corrected batch B",
            },
            "raw_material_c": {"actual_material_used": "", "batch_lot": ""},
            "linear_pe": {"actual_material_used": "", "batch_lot": ""},
            "antistatic": {"actual_material_used": "", "batch_lot": ""},
            "masterbatch": {"actual_material_used": "", "batch_lot": ""},
            "chalk": {"actual_material_used": "", "batch_lot": ""},
        },
        raw_material_brand_grade="Corrected Grade",
    )
    card = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert card["raw_material_a"] == "Corrected planned A"
    assert card["raw_material_b"] == "Corrected planned B"
    assert card["recipe_actual_entries"]["raw_material_a"]["actual_material_used"] == "Corrected actual A"
    assert card["recipe_actual_entries"]["raw_material_a"]["batch_lot"] == "Corrected batch A"
    assert card["actual_raw_material_used"] == "Corrected actual A"
    assert card["raw_material_batch_lot"] == "Corrected batch A"
    assert card["raw_material_brand_grade"] == "Corrected Grade"
    assert card["version"] == loaded_version + 1


def test_admin_material_ledger_blocks_stale_version(connection):
    card_id = prepare_dense_completed_card("27011", roll_count=1)
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.30").ok

    result = db.update_admin_material_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        planned_materials={"raw_material_a": "Stale"},
        actual_entries={},
        raw_material_brand_grade="Stale",
    )

    assert not result.ok
    assert result.messages == (db.STALE_CARD_MESSAGE,)
```

- [ ] **Step 2: Run tests and verify missing function failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py::test_admin_material_ledger_updates_planned_and_actual_fields -v
```

Expected: FAIL with `AttributeError: module 'app.db' has no attribute 'update_admin_material_ledger'`.

- [ ] **Step 3: Implement `update_admin_material_ledger` in `app/db.py`**

Add near existing material update helpers:

```python
ADMIN_MATERIAL_FIELDS = (
    "raw_material_a",
    "raw_material_b",
    "raw_material_c",
    "linear_pe",
    "antistatic",
    "masterbatch",
    "chalk",
)


def update_admin_material_ledger(
    card_id: int,
    loaded_version: int,
    planned_materials: dict[str, str],
    actual_entries: dict[str, dict[str, str]],
    raw_material_brand_grade: str,
) -> RuleResult:
    component_labels = dict(RECIPE_COMPONENT_FIELDS)
    unknown_keys = sorted((set(planned_materials) | set(actual_entries)) - set(component_labels))
    if unknown_keys:
        return RuleResult(False, ("Формата съдържа непознат ред от рецептата.",))

    import_columns = ", ".join(ADMIN_MATERIAL_FIELDS)
    with connect() as connection:
        card = connection.execute(
            f"""
            SELECT id, version, raw_material_brand_grade, {import_columns}
            FROM cards
            WHERE id = ?
              AND status IN (?, ?, ?, ?, ?)
            """,
            (card_id, *ACTIVE_TERMINAL_STATUSES, *ARCHIVE_STATUSES),
        ).fetchone()
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        cleaned_planned = {
            field: str(planned_materials.get(field) or "").strip()
            for field in ADMIN_MATERIAL_FIELDS
        }
        connection.execute(
            """
            UPDATE cards
            SET raw_material_a = ?,
                raw_material_b = ?,
                raw_material_c = ?,
                linear_pe = ?,
                antistatic = ?,
                masterbatch = ?,
                chalk = ?,
                actual_raw_material_used = ?,
                raw_material_brand_grade = ?,
                raw_material_batch_lot = ?,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                cleaned_planned["raw_material_a"],
                cleaned_planned["raw_material_b"],
                cleaned_planned["raw_material_c"],
                cleaned_planned["linear_pe"],
                cleaned_planned["antistatic"],
                cleaned_planned["masterbatch"],
                cleaned_planned["chalk"],
                str(actual_entries.get("raw_material_a", {}).get("actual_material_used") or "").strip(),
                raw_material_brand_grade.strip(),
                str(actual_entries.get("raw_material_a", {}).get("batch_lot") or "").strip(),
                card_id,
            ),
        )

        for component_key, component_label in RECIPE_COMPONENT_FIELDS:
            entry = actual_entries.get(component_key, {})
            connection.execute(
                """
                INSERT INTO recipe_actual_entries (
                    card_id, component_key, component_label, planned_material,
                    actual_material_used, batch_lot, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(card_id, component_key) DO UPDATE SET
                    component_label = excluded.component_label,
                    planned_material = excluded.planned_material,
                    actual_material_used = excluded.actual_material_used,
                    batch_lot = excluded.batch_lot,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    card_id,
                    component_key,
                    component_label,
                    cleaned_planned.get(component_key, ""),
                    str(entry.get("actual_material_used") or "").strip(),
                    str(entry.get("batch_lot") or "").strip(),
                ),
            )

    return RuleResult(True, ("Материалите са записани.",))
```

- [ ] **Step 4: Add route parser and POST route in `app/main.py`**

Add parser:

```python
def material_ledger_from_form(form: Any) -> tuple[dict[str, str], dict[str, dict[str, str]], str]:
    planned_materials: dict[str, str] = {}
    actual_entries: dict[str, dict[str, str]] = {}
    for _, field in RECIPE_FIELD_ROWS:
        planned_materials[field] = str(form.get(f"planned_material__{field}") or "")
        actual_entries[field] = {
            "actual_material_used": str(form.get(f"actual_material__{field}") or ""),
            "batch_lot": str(form.get(f"batch_lot__{field}") or ""),
        }
    return (
        planned_materials,
        actual_entries,
        str(form.get("raw_material_brand_grade") or ""),
    )
```

Add route:

```python
@app.post("/admin/cards/{card_id}/materials-ledger")
async def save_admin_materials_ledger(request: Request, card_id: int):
    form = await request.form()
    parsed_version, material_result = parse_loaded_version(
        str(form.get("loaded_version") or "")
    )
    if parsed_version is not None:
        planned_materials, actual_entries, raw_material_brand_grade = material_ledger_from_form(form)
        material_result = update_admin_material_ledger(
            card_id=card_id,
            loaded_version=parsed_version,
            planned_materials=planned_materials,
            actual_entries=actual_entries,
            raw_material_brand_grade=raw_material_brand_grade,
        )

    return admin_card_post_response(
        request,
        card_id,
        "material_result",
        material_result,
    )
```

Import `update_admin_material_ledger` from `.db`.

- [ ] **Step 5: Run focused material tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py::test_admin_material_ledger_updates_planned_and_actual_fields tests/test_admin_card_detail_redesign.py::test_admin_material_ledger_blocks_stale_version -v
```

Expected: PASS.

---

### Task 3: Add Bulk Roll Ledger Backend Behavior

**Files:**
- Modify: `app/db.py`
- Modify: `app/main.py`
- Test: `tests/test_admin_card_detail_redesign.py`

- [ ] **Step 1: Add roll ledger tests**

Append:

```python
def test_admin_roll_ledger_updates_tare_rolls_deletes_and_adds(connection):
    card_id = prepare_dense_completed_card("27020", roll_count=3)
    card = db.fetch_admin_card_detail(card_id)
    loaded_version = int(card["version"])
    first_roll = card["roll_entries"][0]
    second_roll = card["roll_entries"][1]

    result = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        tare_weight="1.50",
        roll_updates={int(first_roll["id"]): "55.00"},
        delete_roll_ids={int(second_roll["id"])},
        new_gross_weights=["56.25"],
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert updated["tare_weight"] == "1.5"
    assert updated["roll_count"] == 3
    assert [roll["roll_number"] for roll in updated["roll_entries"]] == [1, 2, 3]
    assert updated["roll_entries"][0]["gross_weight"] == "55"
    assert updated["version"] == loaded_version + 1


def test_admin_roll_ledger_blocks_stale_version(connection):
    card_id = prepare_dense_completed_card("27021", roll_count=2)
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.40").ok

    result = db.update_admin_roll_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        tare_weight="1.50",
        roll_updates={},
        delete_roll_ids=set(),
        new_gross_weights=[],
    )

    assert not result.ok
    assert result.messages == (db.STALE_CARD_MESSAGE,)
```

- [ ] **Step 2: Run tests and verify missing function failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py::test_admin_roll_ledger_updates_tare_rolls_deletes_and_adds -v
```

Expected: FAIL with missing `update_admin_roll_ledger`.

- [ ] **Step 3: Implement `update_admin_roll_ledger` in `app/db.py`**

Use the existing roll helpers directly: `fetch_roll_action_card`, `validate_loaded_card_version`, `validate_card_allows_roll_entry`, `parse_weight`, `decimal_to_storage`, and `net_weight_for_gross`.

Add:

```python
def update_admin_roll_ledger(
    card_id: int,
    loaded_version: int,
    tare_weight: str,
    roll_updates: dict[int, str],
    delete_roll_ids: set[int],
    new_gross_weights: list[str],
) -> RuleResult:
    with connect() as connection:
        card = fetch_roll_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        roll_entry_result = validate_card_allows_roll_entry(card)
        if not roll_entry_result.ok:
            return roll_entry_result

        parsed_tare, parse_error = parse_weight(tare_weight, "Шпула", allow_blank=True)
        if parse_error:
            return RuleResult(False, (parse_error,))

        existing_rolls = connection.execute(
            """
            SELECT id, roll_number
            FROM roll_entries
            WHERE card_id = ?
            ORDER BY roll_number
            """,
            (card_id,),
        ).fetchall()
        existing_ids = {int(row["id"]) for row in existing_rolls}
        unknown_ids = (set(roll_updates) | delete_roll_ids) - existing_ids
        if unknown_ids:
            return RuleResult(False, ("Избрана ролка не принадлежи към тази карта.",))

        remaining_count = len(existing_ids - delete_roll_ids) + len(
            [value for value in new_gross_weights if str(value).strip()]
        )
        if str(card["status"]) == STATUS_COMPLETED and remaining_count < 1:
            return RuleResult(False, ("Завършена карта трябва да има поне една ролка.",))

        parsed_updates: dict[int, Decimal] = {}
        for roll_id, gross_weight in roll_updates.items():
            if roll_id in delete_roll_ids:
                continue
            parsed_gross, parse_error = parse_weight(gross_weight, "Бруто тегло", allow_blank=True)
            if parse_error:
                return RuleResult(False, (parse_error,))
            if parsed_gross is None:
                continue
            parsed_updates[roll_id] = parsed_gross

        parsed_new: list[Decimal] = []
        for gross_weight in new_gross_weights:
            if not str(gross_weight).strip():
                continue
            parsed_gross, parse_error = parse_weight(gross_weight, "Бруто тегло", allow_blank=False)
            if parse_error:
                return RuleResult(False, (parse_error,))
            assert parsed_gross is not None
            parsed_new.append(parsed_gross)

        connection.execute(
            """
            UPDATE cards
            SET tare_weight = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (decimal_to_storage(parsed_tare) if parsed_tare is not None else None, card_id),
        )

        for roll_id in delete_roll_ids:
            connection.execute(
                "DELETE FROM roll_entries WHERE id = ? AND card_id = ?",
                (roll_id, card_id),
            )

        for roll_id, parsed_gross in parsed_updates.items():
            net_weight = net_weight_for_gross(parsed_gross, parsed_tare)
            if parsed_tare is not None and net_weight is None:
                return RuleResult(False, ("Бруто теглото не може да бъде по-малко от шпулата.",))
            connection.execute(
                """
                UPDATE roll_entries
                SET gross_weight = ?, net_weight = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND card_id = ?
                """,
                (
                    decimal_to_storage(parsed_gross),
                    decimal_to_storage(net_weight) if net_weight is not None else None,
                    roll_id,
                    card_id,
                ),
            )

        next_roll_number = int(
            connection.execute(
                "SELECT COALESCE(MAX(roll_number), 0) + 1 AS next_roll_number FROM roll_entries WHERE card_id = ?",
                (card_id,),
            ).fetchone()["next_roll_number"]
        )
        order_number = str(card["order_number"])
        for parsed_gross in parsed_new:
            net_weight = net_weight_for_gross(parsed_gross, parsed_tare)
            if parsed_tare is not None and net_weight is None:
                return RuleResult(False, ("Бруто теглото не може да бъде по-малко от шпулата.",))
            connection.execute(
                """
                INSERT INTO roll_entries (
                    card_id, order_number, roll_number, gross_weight, net_weight
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    card_id,
                    order_number,
                    next_roll_number,
                    decimal_to_storage(parsed_gross),
                    decimal_to_storage(net_weight) if net_weight is not None else None,
                ),
            )
            next_roll_number += 1

        remaining_rolls = connection.execute(
            """
            SELECT id
            FROM roll_entries
            WHERE card_id = ?
            ORDER BY roll_number, id
            """,
            (card_id,),
        ).fetchall()
        for roll_number, roll in enumerate(remaining_rolls, start=1):
            connection.execute(
                """
                UPDATE roll_entries
                SET roll_number = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (roll_number, int(roll["id"])),
            )

    return RuleResult(True, ("Ролките са записани.",))
```

- [ ] **Step 4: Add route parser in `app/main.py`**

```python
def roll_ledger_from_form(form: Any) -> tuple[str, dict[int, str], set[int], list[str]]:
    roll_updates: dict[int, str] = {}
    delete_roll_ids: set[int] = set()
    new_gross_weights: list[str] = []

    for key, value in form.multi_items():
        text_value = str(value or "")
        if key.startswith("gross_weight__"):
            roll_updates[int(key.removeprefix("gross_weight__"))] = text_value
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

Add route:

```python
@app.post("/admin/cards/{card_id}/roll-ledger")
async def save_admin_roll_ledger(request: Request, card_id: int):
    form = await request.form()
    parsed_version, roll_result = parse_loaded_version(
        str(form.get("loaded_version") or "")
    )
    if parsed_version is not None:
        tare_weight, roll_updates, delete_roll_ids, new_gross_weights = roll_ledger_from_form(form)
        roll_result = update_admin_roll_ledger(
            card_id=card_id,
            loaded_version=parsed_version,
            tare_weight=tare_weight,
            roll_updates=roll_updates,
            delete_roll_ids=delete_roll_ids,
            new_gross_weights=new_gross_weights,
        )

    return admin_card_post_response(request, card_id, "roll_result", roll_result)
```

Import `update_admin_roll_ledger`.

- [ ] **Step 5: Run focused roll tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py::test_admin_roll_ledger_updates_tare_rolls_deletes_and_adds tests/test_admin_card_detail_redesign.py::test_admin_roll_ledger_blocks_stale_version -v
```

Expected: PASS.

---

### Task 4: Add Bulk Timing Ledger Backend Behavior

**Files:**
- Modify: `app/db.py`
- Modify: `app/main.py`
- Test: `tests/test_admin_card_detail_redesign.py`

- [ ] **Step 1: Add timing ledger tests**

Append:

```python
def test_admin_timing_ledger_updates_deletes_and_adds_segments(connection):
    card_id = prepare_dense_completed_card("27030", roll_count=1)
    assert db.add_timing_segment(
        card_id,
        card_version(card_id),
        "2026-06-18 08:00:00",
        "2026-06-18 09:00:00",
        "correction",
    ).ok
    card = db.fetch_admin_card_detail(card_id)
    loaded_version = int(card["version"])
    first_segment = card["timing_segments"][0]

    result = db.update_admin_timing_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        segment_updates={
            int(first_segment["id"]): {
                "started_at": "2026-06-18 06:10:00",
                "ended_at": "2026-06-18 07:00:00",
                "end_reason": "pause",
            }
        },
        delete_segment_ids=set(),
        new_segments=[
            {
                "started_at": "2026-06-18 10:00:00",
                "ended_at": "2026-06-18 10:30:00",
                "end_reason": "correction",
            }
        ],
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert updated["timing_segments"][0]["started_at"] == "2026-06-18 06:10:00"
    assert any(segment["started_at"] == "2026-06-18 10:00:00" for segment in updated["timing_segments"])
    assert updated["version"] == loaded_version + 1


def test_admin_timing_ledger_blocks_stale_version(connection):
    card_id = prepare_dense_completed_card("27031", roll_count=1)
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.40").ok

    result = db.update_admin_timing_ledger(
        card_id=card_id,
        loaded_version=loaded_version,
        segment_updates={},
        delete_segment_ids=set(),
        new_segments=[],
    )

    assert not result.ok
    assert result.messages == (db.STALE_CARD_MESSAGE,)
```

- [ ] **Step 2: Run tests and verify missing function failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py::test_admin_timing_ledger_updates_deletes_and_adds_segments -v
```

Expected: FAIL with missing `update_admin_timing_ledger`.

- [ ] **Step 3: Implement `update_admin_timing_ledger` in `app/db.py`**

Add a transaction-based helper near current timing helpers:

```python
def update_admin_timing_ledger(
    card_id: int,
    loaded_version: int,
    segment_updates: dict[int, dict[str, str]],
    delete_segment_ids: set[int],
    new_segments: list[dict[str, str]],
) -> RuleResult:
    with connect() as connection:
        card = fetch_admin_production_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        existing_segments = connection.execute(
            """
            SELECT id
            FROM production_time_segments
            WHERE card_id = ?
            ORDER BY started_at, id
            """,
            (card_id,),
        ).fetchall()
        existing_ids = {int(row["id"]) for row in existing_segments}
        unknown_ids = (set(segment_updates) | delete_segment_ids) - existing_ids
        if unknown_ids:
            return RuleResult(False, ("Избран времеви сегмент не принадлежи към тази карта.",))

        remaining_count = len(existing_ids - delete_segment_ids) + len(
            [
                segment
                for segment in new_segments
                if str(segment.get("started_at") or "").strip()
                or str(segment.get("ended_at") or "").strip()
            ]
        )
        if str(card["status"]) == STATUS_COMPLETED and remaining_count < 1:
            return RuleResult(False, ("Завършена карта трябва да има поне един времеви сегмент.",))

        for segment_id in delete_segment_ids:
            connection.execute(
                "DELETE FROM production_time_segments WHERE id = ? AND card_id = ?",
                (segment_id, card_id),
            )

        for segment_id, values in segment_updates.items():
            if segment_id in delete_segment_ids:
                continue
            parsed, result = parse_timing_segment_values(
                values.get("started_at", ""),
                values.get("ended_at", ""),
                values.get("end_reason", ""),
            )
            if not result.ok:
                return result
            connection.execute(
                """
                UPDATE production_time_segments
                SET started_at = ?, ended_at = ?, end_reason = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND card_id = ?
                """,
                (
                    parsed["started_at"],
                    parsed["ended_at"],
                    parsed["end_reason"],
                    segment_id,
                    card_id,
                ),
            )

        for segment in new_segments:
            if not str(segment.get("started_at") or "").strip():
                continue
            parsed, result = parse_timing_segment_values(
                segment.get("started_at", ""),
                segment.get("ended_at", ""),
                segment.get("end_reason", ""),
            )
            if not result.ok:
                return result
            connection.execute(
                """
                INSERT INTO production_time_segments (card_id, started_at, ended_at, end_reason)
                VALUES (?, ?, ?, ?)
                """,
                (
                    card_id,
                    parsed["started_at"],
                    parsed["ended_at"],
                    parsed["end_reason"],
                ),
            )

        connection.execute(
            """
            UPDATE cards
            SET finished_at = CASE
                    WHEN status = ?
                    THEN (
                        SELECT MAX(ended_at)
                        FROM production_time_segments
                        WHERE card_id = ? AND ended_at IS NOT NULL
                    )
                    ELSE finished_at
                END
            WHERE id = ?
            """,
            (STATUS_COMPLETED, card_id, card_id),
        )
        refresh_card_timing_markers(connection, card_id)
        touch_card(connection, card_id)

    return RuleResult(True, ("Времето е записано.",))
```

- [ ] **Step 4: Add route parser and route in `app/main.py`**

```python
def timing_ledger_from_form(
    form: Any,
) -> tuple[dict[int, dict[str, str]], set[int], list[dict[str, str]]]:
    segment_updates: dict[int, dict[str, str]] = {}
    delete_segment_ids: set[int] = set()
    new_segment = {
        "started_at": str(form.get("new_started_at") or ""),
        "ended_at": str(form.get("new_ended_at") or ""),
        "end_reason": str(form.get("new_end_reason") or ""),
    }

    for key, value in form.multi_items():
        text_value = str(value or "")
        if key == "delete_segment_id":
            delete_segment_ids.add(int(text_value))
        elif "__" in key:
            field_name, segment_id_text = key.split("__", 1)
            if field_name in {"started_at", "ended_at", "end_reason"}:
                segment_id = int(segment_id_text)
                segment_updates.setdefault(segment_id, {})[field_name] = text_value

    return segment_updates, delete_segment_ids, [new_segment]
```

Route:

```python
@app.post("/admin/cards/{card_id}/timing-ledger")
async def save_admin_timing_ledger(request: Request, card_id: int):
    form = await request.form()
    parsed_version, timing_result = parse_loaded_version(
        str(form.get("loaded_version") or "")
    )
    if parsed_version is not None:
        segment_updates, delete_segment_ids, new_segments = timing_ledger_from_form(form)
        timing_result = update_admin_timing_ledger(
            card_id=card_id,
            loaded_version=parsed_version,
            segment_updates=segment_updates,
            delete_segment_ids=delete_segment_ids,
            new_segments=new_segments,
        )

    return admin_card_post_response(request, card_id, "timing_result", timing_result)
```

Import `update_admin_timing_ledger`.

- [ ] **Step 5: Run focused timing tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py::test_admin_timing_ledger_updates_deletes_and_adds_segments tests/test_admin_card_detail_redesign.py::test_admin_timing_ledger_blocks_stale_version -v
```

Expected: PASS.

---

### Task 5: Restructure `admin_card_detail.html`

**Files:**
- Modify: `app/templates/admin_card_detail.html`
- Test: `tests/test_admin_card_detail_redesign.py`

- [ ] **Step 1: Replace top imported-field-first layout with summary-first layout**

In `admin_card_detail.html`, keep the existing header, notice blocks, and admin nav. Immediately after notices, add:

```html
<section class="section admin-summary-panel">
  <div class="section-head">
    <h2>Общо произведено</h2>
    <span>{{ card.finished_at or card.updated_at }}</span>
  </div>
  <dl class="admin-summary-grid">
    <div>
      <dt>Бруто</dt>
      <dd>{{ card.total_gross_weight }} кг</dd>
    </div>
    <div>
      <dt>Нето</dt>
      <dd>
        {% if card.total_net_weight is not none %}
          {{ card.total_net_weight }} кг
        {% else %}
          -
        {% endif %}
      </dd>
    </div>
    <div>
      <dt>Шпула</dt>
      <dd>{{ card.tare_weight if card.tare_weight is not none else "-" }} кг</dd>
    </div>
    <div>
      <dt>Ролки</dt>
      <dd>{{ card.roll_count }}</dd>
    </div>
    <div>
      <dt>Време</dt>
      <dd>{{ card.total_production_duration }}</dd>
    </div>
    <div>
      <dt>Машина</dt>
      <dd>
        {% if card.machine_id %}
          {{ card.machine_id }}{% if card.machine_sequence %} / ред {{ card.machine_sequence }}{% endif %}
        {% else %}
          -
        {% endif %}
      </dd>
    </div>
  </dl>
</section>
```

- [ ] **Step 2: Keep order details as one compact form**

Retain the `/imported-fields` form but remove material recipe fields from this section. It should contain only:

- order number
- order date
- delivery date
- customer
- city
- product type
- quantity/unit pairs
- size/thickness
- product form
- material
- max roll weight
- notes
- extrusion fields
- packaging method

Use compact classes:

```html
<section class="section operational-panel admin-compact-card">
  <div class="section-head">
    <h2>Данни по поръчката</h2>
    <button type="submit">Запази данните</button>
  </div>
  <div class="admin-compact-grid">
    <label class="field-short">
      <span>№ поръчка</span>
      <input name="order_number" value="{{ card.order_number or '' }}" required>
    </label>
    <label class="field-short">
      <span>Дата</span>
      <input name="order_date" value="{{ card.order_date or '' }}">
    </label>
    <label class="field-short">
      <span>Дата доставка</span>
      <input name="delivery_date" value="{{ card.delivery_date or '' }}">
    </label>
    <label class="field-wide">
      <span>Клиент</span>
      <input name="customer" value="{{ card.customer or '' }}">
    </label>
    <label class="field-medium">
      <span>Град</span>
      <input name="city" value="{{ card.city or '' }}">
    </label>
    <label class="field-wide">
      <span>Вид изделие</span>
      <input name="product_type" value="{{ card.product_type or '' }}">
    </label>
    <label class="field-short">
      <span>Количество</span>
      <input name="quantity_1" value="{{ card.quantity_1 or '' }}">
    </label>
    <label class="field-short">
      <span>Мярка</span>
      <input name="unit_1" value="{{ card.unit_1 or '' }}">
    </label>
    <label class="field-short">
      <span>Допълнително</span>
      <input name="quantity_2" value="{{ card.quantity_2 or '' }}">
    </label>
    <label class="field-short">
      <span>Мярка</span>
      <input name="unit_2" value="{{ card.unit_2 or '' }}">
    </label>
    <label class="field-medium">
      <span>Размер/дебелина</span>
      <input name="size_thickness" value="{{ card.size_thickness or '' }}">
    </label>
    <label class="field-medium">
      <span>Вид заготовка</span>
      <input name="product_form" value="{{ card.product_form or '' }}">
    </label>
    <label class="field-medium">
      <span>Материал</span>
      <input name="material" value="{{ card.material or '' }}">
    </label>
    <label class="field-short">
      <span>Макс. тегло ролка, кг</span>
      <input name="max_roll_weight" value="{{ card.max_roll_weight or '' }}">
    </label>
    <label class="field-short">
      <span>Екструзия</span>
      <input name="extrusion_flag" value="{{ card.extrusion_flag or '' }}">
    </label>
    <label class="field-medium">
      <span>Фалцоване</span>
      <input name="extrusion_folding" value="{{ card.extrusion_folding or '' }}">
    </label>
    <label class="field-medium">
      <span>Следваща операция</span>
      <input name="extrusion_next_operation" value="{{ card.extrusion_next_operation or '' }}">
    </label>
    <label class="field-medium">
      <span>Третиране</span>
      <input name="extrusion_treatment" value="{{ card.extrusion_treatment or '' }}">
    </label>
    <label class="field-medium">
      <span>Опаковка</span>
      <input name="packaging_method" value="{{ card.packaging_method or '' }}">
    </label>
    <label class="field-full">
      <span>Забележки</span>
      <textarea name="notes" rows="3">{{ card.notes or "" }}</textarea>
    </label>
  </div>
</section>
```

Do not leave `raw_material_a`, `raw_material_b`, `raw_material_c`, `linear_pe`, `antistatic`, `masterbatch`, or `chalk` inputs in this order-details form.

- [ ] **Step 3: Add unified materials ledger**

Replace both old `Рецепта` and `Материал на машината` sections with:

```html
<section class="section operational-panel">
  <form class="admin-ledger-form" action="/admin/cards/{{ card.id }}/materials-ledger" method="post">
    <input type="hidden" name="loaded_version" value="{{ card.version }}">
    <div class="section-head">
      <h2>Материали</h2>
      <button type="submit">Запази материалите</button>
    </div>
    <div class="admin-ledger-table material-ledger">
      <div class="admin-ledger-head">
        <div>Позиция</div>
        <div>По карта</div>
        <div>Реално използвано</div>
        <div>Марка / клас</div>
        <div>Партида</div>
      </div>
      {% for row in recipe_rows %}
        <div class="admin-ledger-row material-ledger-row">
          <div class="component">{{ row.label }}</div>
          <div>
            <input name="planned_material__{{ row.field }}" value="{{ row.planned }}">
          </div>
          <div>
            <input name="actual_material__{{ row.field }}" value="{{ row.actual_material or '' }}">
          </div>
          <div>
            {% if row.field == "raw_material_a" %}
              <input name="raw_material_brand_grade" value="{{ card.raw_material_brand_grade or '' }}">
            {% else %}
              <span class="readonly-cell">-</span>
            {% endif %}
          </div>
          <div>
            <input name="batch_lot__{{ row.field }}" value="{{ row.batch or '' }}">
          </div>
        </div>
      {% endfor %}
    </div>
  </form>
</section>
```

- [ ] **Step 4: Replace produced quantity plus duplicated roll corrections with one roll ledger**

```html
<section class="section operational-panel">
  <form class="admin-ledger-form" action="/admin/cards/{{ card.id }}/roll-ledger" method="post">
    <input type="hidden" name="loaded_version" value="{{ card.version }}">
    <div class="section-head">
      <h2>Ролки</h2>
      <button type="submit">Запази ролките</button>
    </div>

    <div class="admin-roll-toolbar">
      <label>
        <span>Шпула, кг</span>
        <input type="number" name="tare_weight" min="0" step="0.01" value="{{ card.tare_weight if card.tare_weight is not none else '' }}">
      </label>
      <label>
        <span>Нова ролка, кг</span>
        <input type="number" name="new_gross_weight" min="0" step="0.01" placeholder="Бруто">
      </label>
    </div>

    {% if card.roll_entries %}
      <div class="admin-ledger-table roll-ledger">
        <div class="admin-ledger-head">
          <div>№</div>
          <div>Бруто, кг</div>
          <div>Нето, кг</div>
          <div>Изтрий</div>
        </div>
        {% for roll in card.roll_entries %}
          <div class="admin-ledger-row admin-roll-ledger-row">
            <div>{{ roll.roll_number }}</div>
            <div>
              <input type="number" name="gross_weight__{{ roll.id }}" min="0" step="0.01" value="{{ roll.gross_weight if roll.gross_weight is not none else '' }}">
            </div>
            <div class="readonly-cell">{{ roll.net_weight if roll.net_weight is not none else "-" }}</div>
            <label class="delete-check">
              <input type="checkbox" name="delete_roll_id" value="{{ roll.id }}">
              <span>Изтрий</span>
            </label>
          </div>
        {% endfor %}
      </div>
    {% else %}
      <p class="empty">Няма въведени ролки.</p>
    {% endif %}
  </form>
</section>
```

Remove:

- `.admin-review-grid`
- `Произведено количество` section
- old read-only roll `<table class="compact-table">`
- `.admin-roll-corrections`
- per-roll `inline-roll-form`
- per-roll `roll-delete-form`

- [ ] **Step 5: Replace duplicated timing view with one timing ledger**

```html
<section class="section operational-panel">
  <form class="admin-ledger-form" action="/admin/cards/{{ card.id }}/timing-ledger" method="post">
    <input type="hidden" name="loaded_version" value="{{ card.version }}">
    <div class="section-head">
      <h2>Време</h2>
      <button type="submit">Запази времето</button>
    </div>

    <dl class="detail-grid timing-summary">
      <div>
        <dt>Общо време</dt>
        <dd>{{ card.total_production_duration }}</dd>
      </div>
      <div>
        <dt>Първи старт</dt>
        <dd>{{ card.first_started_at or "-" }}</dd>
      </div>
      <div>
        <dt>{{ status_labels.completed }}</dt>
        <dd>{{ card.finished_at or "-" }}</dd>
      </div>
    </dl>

    <div class="admin-ledger-table timing-ledger">
      <div class="admin-ledger-head">
        <div>Начало</div>
        <div>Край</div>
        <div>Причина</div>
        <div>Изтрий</div>
      </div>
      {% for segment in card.timing_segments %}
        <div class="admin-ledger-row admin-timing-ledger-row">
          <div><input name="started_at__{{ segment.id }}" value="{{ segment.started_at }}"></div>
          <div><input name="ended_at__{{ segment.id }}" value="{{ segment.ended_at or '' }}"></div>
          <div>
            <select name="end_reason__{{ segment.id }}">
              <option value="" {% if not segment.end_reason %}selected{% endif %}>В ход</option>
              <option value="pause" {% if segment.end_reason == "pause" %}selected{% endif %}>пауза</option>
              <option value="finish" {% if segment.end_reason == "finish" %}selected{% endif %}>приключване</option>
              <option value="correction" {% if segment.end_reason == "correction" %}selected{% endif %}>корекция</option>
            </select>
          </div>
          <label class="delete-check">
            <input type="checkbox" name="delete_segment_id" value="{{ segment.id }}">
            <span>Изтрий</span>
          </label>
        </div>
      {% endfor %}
      <div class="admin-ledger-row admin-timing-ledger-row new-row">
        <div><input name="new_started_at" placeholder="YYYY-MM-DD HH:MM:SS"></div>
        <div><input name="new_ended_at" placeholder="YYYY-MM-DD HH:MM:SS"></div>
        <div>
          <select name="new_end_reason">
            <option value="">В ход</option>
            <option value="pause">пауза</option>
            <option value="finish">приключване</option>
            <option value="correction">корекция</option>
          </select>
        </div>
        <div class="readonly-cell">Нов</div>
      </div>
    </div>
  </form>
</section>
```

Remove old read-only timing segment table and `.admin-timing-corrections`.

- [ ] **Step 6: Collapse system data**

Replace the system section body with native `<details>`:

```html
<section class="section admin-system-section">
  <details>
    <summary>Системни данни</summary>
    <dl class="detail-grid">
      <div>
        <dt>Статус</dt>
        <dd>{{ status_labels.get(card.status, card.status) }}</dd>
      </div>
      <div>
        <dt>Импорт</dt>
        <dd>{{ card.import_batch_id or "-" }}</dd>
      </div>
      <div>
        <dt>Версия</dt>
        <dd>{{ card.version }}</dd>
      </div>
      <div>
        <dt>Създадена</dt>
        <dd>{{ card.created_at }}</dd>
      </div>
      <div>
        <dt>Обновена</dt>
        <dd>{{ card.updated_at }}</dd>
      </div>
    </dl>
  </details>
</section>
```

- [ ] **Step 7: Run render regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py::test_admin_detail_combines_recipe_and_machine_materials tests/test_admin_card_detail_redesign.py::test_admin_detail_uses_single_roll_ledger_without_repeated_save_buttons tests/test_admin_card_detail_redesign.py::test_admin_detail_uses_single_timing_ledger_without_duplicate_segment_forms -v
```

Expected: PASS.

---

### Task 6: Add Compact Admin Detail CSS

**Files:**
- Modify: `app/static/css/app.css`
- Test: Playwright screenshot in Task 8

- [ ] **Step 1: Add summary and compact field styles**

Append near existing admin detail styles:

```css
.admin-summary-panel {
  position: sticky;
  top: 0;
  z-index: 2;
}

.admin-summary-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.admin-summary-grid div {
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--surface-soft);
  padding: 10px;
}

.admin-summary-grid dt,
.admin-compact-grid span,
.admin-ledger-form label span {
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}

.admin-summary-grid dd {
  margin: 3px 0 0;
  font-size: 20px;
  font-weight: 850;
}

.admin-compact-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 10px;
}

.admin-compact-grid label {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.admin-compact-grid input,
.admin-compact-grid textarea {
  width: 100%;
  min-height: 36px;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  padding: 7px 9px;
  color: var(--text);
  font: inherit;
}

.admin-compact-grid .field-short {
  grid-column: span 2;
}

.admin-compact-grid .field-medium {
  grid-column: span 3;
}

.admin-compact-grid .field-wide {
  grid-column: span 6;
}

.admin-compact-grid .field-full {
  grid-column: 1 / -1;
}
```

- [ ] **Step 2: Add ledger styles**

```css
.admin-ledger-form {
  display: grid;
  gap: 12px;
}

.admin-ledger-table {
  border: 1px solid var(--line);
  border-radius: 7px;
  overflow: hidden;
  background: var(--surface);
}

.admin-ledger-head,
.admin-ledger-row {
  display: grid;
  align-items: stretch;
}

.material-ledger .admin-ledger-head,
.material-ledger .admin-ledger-row {
  grid-template-columns: 90px minmax(180px, 1fr) minmax(180px, 1fr) minmax(130px, 0.7fr) minmax(140px, 0.7fr);
}

.roll-ledger .admin-ledger-head,
.roll-ledger .admin-ledger-row {
  grid-template-columns: 70px minmax(140px, 0.6fr) minmax(140px, 0.6fr) 110px;
}

.timing-ledger .admin-ledger-head,
.timing-ledger .admin-ledger-row {
  grid-template-columns: minmax(190px, 1fr) minmax(190px, 1fr) minmax(140px, 0.7fr) 110px;
}

.admin-ledger-head {
  min-height: 34px;
  background: var(--surface-soft);
  color: var(--muted);
  font-size: 12px;
  font-weight: 850;
  text-transform: uppercase;
}

.admin-ledger-row {
  min-height: 44px;
  border-top: 1px solid var(--line);
}

.admin-ledger-head > div,
.admin-ledger-row > div,
.admin-ledger-row > label {
  min-width: 0;
  border-right: 1px solid var(--line);
  padding: 7px;
}

.admin-ledger-head > div:last-child,
.admin-ledger-row > div:last-child,
.admin-ledger-row > label:last-child {
  border-right: 0;
}

.admin-ledger-row input,
.admin-ledger-row select,
.admin-roll-toolbar input {
  width: 100%;
  min-height: 34px;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  padding: 0 8px;
  color: var(--text);
  font: inherit;
}

.admin-roll-toolbar {
  display: grid;
  grid-template-columns: minmax(160px, 220px) minmax(180px, 240px);
  gap: 10px;
}

.admin-roll-toolbar label,
.delete-check {
  display: grid;
  gap: 5px;
}

.delete-check {
  grid-template-columns: auto 1fr;
  align-items: center;
  color: var(--red);
  font-weight: 750;
}

.new-row {
  background: var(--surface-soft);
}

.admin-system-section summary {
  cursor: pointer;
  font-weight: 850;
}
```

- [ ] **Step 3: Add responsive rules**

In the existing media query, include:

```css
@media (max-width: 1080px) {
  .admin-summary-grid,
  .admin-roll-toolbar {
    grid-template-columns: 1fr 1fr;
  }

  .admin-compact-grid {
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .admin-summary-panel {
    position: static;
  }

  .admin-summary-grid,
  .admin-roll-toolbar {
    grid-template-columns: 1fr;
  }

  .admin-compact-grid {
    grid-template-columns: 1fr;
  }

  .admin-compact-grid .field-short,
  .admin-compact-grid .field-medium,
  .admin-compact-grid .field-wide,
  .admin-compact-grid .field-full {
    grid-column: 1 / -1;
  }

  .admin-ledger-table {
    overflow-x: auto;
  }

  .material-ledger .admin-ledger-head,
  .material-ledger .admin-ledger-row {
    min-width: 760px;
  }

  .roll-ledger .admin-ledger-head,
  .roll-ledger .admin-ledger-row {
    min-width: 520px;
  }

  .timing-ledger .admin-ledger-head,
  .timing-ledger .admin-ledger-row {
    min-width: 720px;
  }
}
```

- [ ] **Step 4: Run render tests again**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py -v
```

Expected: PASS.

---

### Task 7: Preserve Existing Behavior Tests And Remove Dead UI Assumptions

**Files:**
- Modify only tests that fail because they asserted old markup, not behavior.
- Run existing relevant suites.

- [ ] **Step 1: Run admin and production correction tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_production_corrections.py tests/test_admin_card_review.py tests/test_finish_cancel_history.py tests/test_roll_entry.py tests/test_production_timing.py -v
```

Expected: PASS or failures only where tests assert old template strings/classes.

- [ ] **Step 2: Update old markup assertions if needed**

If existing tests assert old section names like `Материал на машината`, update them to assert behavior:

```python
assert "Материали" in html
assert "Запази материалите" in html
assert 'name="actual_material__raw_material_a"' in html
assert 'name="planned_material__raw_material_a"' in html
```

If tests assert old roll correction classes, update them:

```python
assert "admin-roll-ledger-row" in html
assert "admin-roll-correction-row" not in html
assert "Запази ролките" in html
```

- [ ] **Step 3: Run full Python suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected: all tests pass.

---

### Task 8: Playwright Visual Verification With Dense Completed Card

**Files:**
- Create screenshots under: `artifacts/ui-checks/admin-card-detail-redesign/`
- Do not mutate real runtime database.

- [ ] **Step 1: Start app against a temporary DB**

Use a temporary DB path:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=/home/sk/projects/extrusion-terminal/.test-runtime/admin-card-detail-redesign/redesign.sqlite3 \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8018
```

Expected: Uvicorn starts on `127.0.0.1:8018`.

- [ ] **Step 2: Seed a dense completed card**

Use a short local script based on the helper in `tests/test_admin_card_detail_redesign.py` to create:

- completed card
- all material rows populated
- tare populated
- `60` roll rows
- at least `6` timing segments

Expected: card is available at `/admin/cards/1`.

- [ ] **Step 3: Capture Playwright screenshots**

Run:

```bash
mkdir -p artifacts/ui-checks/admin-card-detail-redesign
npx playwright test --project=chromium --headed=false
```

If there is no existing Playwright spec for this exact flow, use a one-off Node script:

```javascript
const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.goto('http://127.0.0.1:8018/admin/cards/1', { waitUntil: 'networkidle' });
  await page.screenshot({
    path: 'artifacts/ui-checks/admin-card-detail-redesign/desktop-detail.png',
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto('http://127.0.0.1:8018/admin/cards/1', { waitUntil: 'networkidle' });
  await page.screenshot({
    path: 'artifacts/ui-checks/admin-card-detail-redesign/mobile-detail.png',
    fullPage: true,
  });
  const metrics = await page.evaluate(() => ({
    buttons: document.querySelectorAll('button').length,
    forms: document.querySelectorAll('form').length,
    inputs: document.querySelectorAll('input, textarea, select').length,
    height: document.documentElement.scrollHeight,
    rollRows: document.querySelectorAll('.admin-roll-ledger-row').length,
    timingRows: document.querySelectorAll('.admin-timing-ledger-row').length,
  }));
  console.log(JSON.stringify(metrics, null, 2));
  await browser.close();
})();
```

Expected:

- No duplicated material sections.
- One roll ledger.
- One timing ledger.
- Button count is dramatically lower than the audit baseline of `137`.
- The 60-roll page is still long, but shorter and visually scannable.

- [ ] **Step 4: Stop the temporary server**

Send Ctrl-C to the Uvicorn session.

Expected: server exits cleanly.

---

### Task 9: Update Milestone Tracker And Run Final Checks

**Files:**
- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update milestone tracker**

Add an active/completed entry describing:

```markdown
- admin completed-card detail redesign: compact summary-first layout, unified materials ledger, unified roll ledger, unified timing ledger, and section-level admin corrections.
```

Ensure the next recommended milestone remains obvious.

- [ ] **Step 2: Run final checks**

Run:

```bash
source .venv/bin/activate
python -m pytest
git diff --check
```

Expected:

- pytest passes.
- `git diff --check` reports no whitespace errors.

- [ ] **Step 3: Review changed code**

Manually inspect:

```bash
git diff -- app/db.py app/main.py app/templates/admin_card_detail.html app/static/css/app.css tests/test_admin_card_detail_redesign.py IMPLEMENTATION_PLAN.md
```

Review for:

- no real runtime DB mutation in tests
- stale-version checks on bulk routes
- roll numbering remains contiguous
- completed cards cannot lose all rolls/timing segments
- no duplicated material/roll/timing sections in the template
- UI remains in confirmed pilot scope

- [ ] **Step 4: Do not stage or commit unless the user explicitly asks**

Expected: working tree contains implementation changes only. No `git add`, no commit.

---

## Execution Notes

- Keep the existing single-row correction endpoints until the new bulk endpoints are fully tested. Remove old endpoints only as a later cleanup if they become unused and tests cover route absence.
- The trusted-user prototype context allows simpler destructive controls, but destructive actions should still be visually low-noise and not repeated as large buttons.
- Avoid JavaScript unless a later pass needs richer edit interactions. This plan should work with plain HTML forms.
- The implementation should preserve optimistic conflict behavior by using the loaded card version once per section-level save.
