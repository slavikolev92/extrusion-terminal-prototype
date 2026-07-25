# Shift Manager Import Field Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the app import, storage, validation, admin display, and terminal display with the final Shift Manager CSV export structure.

**Architecture:** Treat the corrected Shift Manager CSV header as the only supported import contract. Add the new source fields to `cards` and `card_import_sources`, route all target-gross math through `ordered_gross_kg`, and route extrusion eligibility through `extrusion_sequence == 1`. Leave old physical SQLite columns in place as harmless migration remnants if they already exist, but remove them from active import/edit/display logic.

**Tech Stack:** FastAPI, Jinja templates, direct `sqlite3`, pytest with temporary SQLite databases, local Playwright for UI verification.

---

## Source Of Truth

Read these before implementation:

- `AGENTS.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `docs/implementation-notes/shift-manager-export-import-field-correctness.md`

Final canonical CSV header:

```csv
order_number,order_date,delivery_date,customer,city,product_type,ordered_gross_kg,ordered_rolls,ordered_meters,ordered_units,product_form,material,size_thickness,notes,printing_sequence,extrusion_sequence,rewinding_slitting_sequence,confection_sequence,extrusion_next_operation,extrusion_folding,extrusion_treatment,raw_material_a,raw_material_b,raw_material_c,linear_pe,antistatic,masterbatch,chalk,packaging_method
```

Firm scope boundaries:

- Do not support old `quantity_1`, `unit_1`, `quantity_2`, `unit_2`, or `extrusion_flag` CSV input.
- Do not add `micro_perforation`.
- Do not touch print output in this slice. Leave `app/printing.py` and `app/templates/print_card.html` stale until the separate print update task.
- Do not mutate `data/extrusion_terminal.sqlite3`.
- Do not stage or commit unless the user explicitly asks.

## File Map

- Modify `app/importer.py`: canonical import fields, CSV template, required header validation, no-extrusion skip rule based on `extrusion_sequence`.
- Modify `app/db.py`: schema columns, migration columns, `CARD_IMPORT_SOURCE_FIELDS`, card fetch SQL, import source backfill, admin save validation.
- Modify `app/rules.py`: target gross source and release message wording.
- Modify `app/main.py`: labels, structured ordered amount display helpers, terminal/admin context display fields.
- Modify `app/templates/admin_card_detail.html`: admin edit fields for structured quantities and route sequences.
- Modify `app/templates/terminal.html`: terminal details for ordered quantities and missing production-detail fields.
- Modify tests under `tests/`: fixtures/helpers and focused regressions for new contract.
- Modify `README.md`: failed import troubleshooting text that still mentions `extrusion_flag`.
- Modify `IMPLEMENTATION_PLAN.md`: add a new current milestone note for this slice.
- Keep deleted `EXCEL_EXPORT_CONTRACT.md` deleted.
- Do not modify `app/printing.py`.
- Do not modify `app/templates/print_card.html`.

---

### Task 1: Import Contract Tests

**Files:**
- Modify: `tests/test_baseline.py`
- Modify: `tests/test_recipe_release_validation.py`
- Modify: `tests/fixtures/structured_recipe_sample.csv`

- [ ] **Step 1: Update the shared baseline CSV fixture helper**

In `tests/test_baseline.py`, replace `extrusion_row()` with:

```python
def extrusion_row(order_number: str, **overrides: str) -> dict[str, str]:
    row = {
        "order_number": order_number,
        "customer": "Test Customer",
        "product_type": "PE film",
        "ordered_gross_kg": "500",
        "ordered_rolls": "20",
        "ordered_meters": "15000",
        "ordered_units": "40000",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "printing_sequence": "2",
        "extrusion_sequence": "1",
        "rewinding_slitting_sequence": "3",
        "confection_sequence": "4",
        "extrusion_next_operation": "Printing",
        "raw_material_a": "LDPE; A | 100%",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row
```

- [ ] **Step 2: Add a test that the template uses the final header**

Add this test in `tests/test_baseline.py` near `test_csv_template_uses_valid_structured_recipe_sample`:

```python
def test_csv_template_uses_final_shift_manager_header():
    header = csv_template().splitlines()[0]

    assert header == ",".join(IMPORT_FIELDS)
    assert "ordered_gross_kg" in header
    assert "ordered_rolls" in header
    assert "ordered_meters" in header
    assert "ordered_units" in header
    assert "extrusion_sequence" in header
    assert "quantity_1" not in header
    assert "unit_1" not in header
    assert "quantity_2" not in header
    assert "unit_2" not in header
    assert "extrusion_flag" not in header
```

- [ ] **Step 3: Add a test that old headers are rejected**

Add this test in `tests/test_baseline.py`:

```python
def test_import_rejects_old_quantity_and_extrusion_flag_contract():
    old_header = (
        "order_number,order_date,delivery_date,customer,city,product_type,"
        "quantity_1,unit_1,quantity_2,unit_2,product_form,material,"
        "size_thickness,notes,extrusion_flag,raw_material_a,packaging_method\n"
    )
    old_row = (
        "OLD-1,,,,Old Customer,Film,500,kg,20,rolls,,LDPE,"
        "600/0.050,,da,LDPE; A | 100%,rolls\n"
    )

    result = import_cards_from_csv(
        "old-contract.csv",
        (old_header + old_row).encode("utf-8"),
        overwrite_existing=False,
    )

    assert result.rows_imported == 0
    assert result.row_results[0].action == "blocked"
    assert "ordered_gross_kg" in result.row_results[0].message
    assert "extrusion_sequence" in result.row_results[0].message
```

- [ ] **Step 4: Add a test that structured fields persist**

Add this test in `tests/test_baseline.py`:

```python
def test_import_persists_structured_ordered_amounts_and_route_sequences(temp_db_path):
    result = import_cards_from_csv(
        "final-contract.csv",
        csv_bytes(
            extrusion_row(
                "NEW-STRUCT-1",
                ordered_gross_kg="750.5",
                ordered_rolls="33",
                ordered_meters="18000",
                ordered_units="42000",
                printing_sequence="",
                extrusion_sequence="1",
                rewinding_slitting_sequence="2",
                confection_sequence="3",
            )
        ),
        overwrite_existing=False,
    )

    assert result.rows_imported == 1
    with db.connect() as connection:
        row = connection.execute(
            """
            SELECT ordered_gross_kg, ordered_rolls, ordered_meters, ordered_units,
                   printing_sequence, extrusion_sequence,
                   rewinding_slitting_sequence, confection_sequence
            FROM cards
            WHERE order_number = ?
            """,
            ("NEW-STRUCT-1",),
        ).fetchone()

    assert dict(row) == {
        "ordered_gross_kg": "750.5",
        "ordered_rolls": "33",
        "ordered_meters": "18000",
        "ordered_units": "42000",
        "printing_sequence": "",
        "extrusion_sequence": "1",
        "rewinding_slitting_sequence": "2",
        "confection_sequence": "3",
    }
```

- [ ] **Step 5: Add a test that `extrusion_sequence != 1` is skipped**

Add this test in `tests/test_baseline.py`:

```python
def test_import_skips_rows_where_extrusion_sequence_is_not_first(temp_db_path):
    result = import_cards_from_csv(
        "not-first.csv",
        csv_bytes(extrusion_row("NOT-FIRST-1", extrusion_sequence="2")),
        overwrite_existing=False,
    )

    assert result.rows_imported == 0
    assert result.skipped == 1
    assert result.row_results[0].action == "skipped"
    assert "няма екструдиране" in result.row_results[0].message
```

- [ ] **Step 6: Run the focused tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py::test_csv_template_uses_final_shift_manager_header tests/test_baseline.py::test_import_rejects_old_quantity_and_extrusion_flag_contract tests/test_baseline.py::test_import_persists_structured_ordered_amounts_and_route_sequences tests/test_baseline.py::test_import_skips_rows_where_extrusion_sequence_is_not_first -q
```

Expected: FAIL because app code still uses old import fields and schema.

---

### Task 2: Importer Contract Implementation

**Files:**
- Modify: `app/importer.py`
- Test: `tests/test_baseline.py`

- [ ] **Step 1: Replace `IMPORT_FIELDS`**

In `app/importer.py`, replace `IMPORT_FIELDS` with:

```python
IMPORT_FIELDS = (
    "order_number",
    "order_date",
    "delivery_date",
    "customer",
    "city",
    "product_type",
    "ordered_gross_kg",
    "ordered_rolls",
    "ordered_meters",
    "ordered_units",
    "product_form",
    "material",
    "size_thickness",
    "notes",
    "printing_sequence",
    "extrusion_sequence",
    "rewinding_slitting_sequence",
    "confection_sequence",
    "extrusion_next_operation",
    "extrusion_folding",
    "extrusion_treatment",
    "raw_material_a",
    "raw_material_b",
    "raw_material_c",
    "linear_pe",
    "antistatic",
    "masterbatch",
    "chalk",
    "packaging_method",
)
```

- [ ] **Step 2: Remove old aliases that accept stale quantity or flag headers**

In `app/importer.py`, keep only aliases that do not reintroduce the old contract:

```python
FIELD_ALIASES = {
    "order_no": "order_number",
    "order": "order_number",
    "date": "order_date",
    "company": "customer",
    "firm": "customer",
    "blank_type": "product_form",
    "form": "product_form",
    "size": "size_thickness",
    "thickness": "size_thickness",
    "folding": "extrusion_folding",
    "next_operation": "extrusion_next_operation",
    "treatment": "extrusion_treatment",
    "material_a": "raw_material_a",
    "material_b": "raw_material_b",
    "material_c": "raw_material_c",
    "linear": "linear_pe",
    "linear_pe_percent": "linear_pe",
    "packaging": "packaging_method",
}
```

Delete `TRUE_EXTRUSION_FLAGS`.

- [ ] **Step 3: Update `csv_template()` sample values**

Use this `sample_values` block:

```python
sample_values = {
    "order_number": "25278",
    "customer": "Примерен клиент",
    "product_type": "PE фолио",
    "ordered_gross_kg": "500",
    "ordered_rolls": "20",
    "ordered_meters": "15000",
    "ordered_units": "40000",
    "material": "LDPE",
    "size_thickness": "600/0.050",
    "printing_sequence": "2",
    "extrusion_sequence": "1",
    "rewinding_slitting_sequence": "3",
    "confection_sequence": "4",
    "extrusion_next_operation": "Printing",
    "raw_material_a": "reLDPE; recycled LDPE | 100%",
    "packaging_method": "ролки",
}
```

- [ ] **Step 4: Require the new contract fields**

In `import_cards_from_csv()`, replace the required-field calculation with:

```python
required_fields = ("order_number", "ordered_gross_kg", "extrusion_sequence")
missing_required = [field for field in required_fields if field not in header_map.values()]
```

- [ ] **Step 5: Replace `card_has_usable_extrusion_step()`**

Replace the function and delete `normalize_flag()`:

```python
def card_has_usable_extrusion_step(card: dict[str, str]) -> bool:
    has_extrusion_details = any(card[field] for field in EXTRUSION_DETAIL_FIELDS)
    return card.get("extrusion_sequence", "").strip() == "1" and has_extrusion_details
```

- [ ] **Step 6: Run focused importer tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py::test_csv_template_uses_final_shift_manager_header tests/test_baseline.py::test_import_rejects_old_quantity_and_extrusion_flag_contract tests/test_baseline.py::test_import_skips_rows_where_extrusion_sequence_is_not_first -q
```

Expected: importer header tests pass; persistence may still fail until schema migration is implemented.

---

### Task 3: Schema And DB Field Migration

**Files:**
- Modify: `app/db.py`
- Test: `tests/test_baseline.py`

- [ ] **Step 1: Replace `CARD_IMPORT_SOURCE_FIELDS`**

In `app/db.py`, replace `CARD_IMPORT_SOURCE_FIELDS` with the same tuple as `app.importer.IMPORT_FIELDS`:

```python
CARD_IMPORT_SOURCE_FIELDS = (
    "order_number",
    "order_date",
    "delivery_date",
    "customer",
    "city",
    "product_type",
    "ordered_gross_kg",
    "ordered_rolls",
    "ordered_meters",
    "ordered_units",
    "product_form",
    "material",
    "size_thickness",
    "notes",
    "printing_sequence",
    "extrusion_sequence",
    "rewinding_slitting_sequence",
    "confection_sequence",
    "extrusion_next_operation",
    "extrusion_folding",
    "extrusion_treatment",
    "raw_material_a",
    "raw_material_b",
    "raw_material_c",
    "linear_pe",
    "antistatic",
    "masterbatch",
    "chalk",
    "packaging_method",
)
```

- [ ] **Step 2: Add new columns to `cards_table_sql()`**

Replace the old quantity columns with the new columns in the create-table SQL:

```sql
    product_type TEXT,
    ordered_gross_kg TEXT,
    ordered_rolls TEXT,
    ordered_meters TEXT,
    ordered_units TEXT,
    product_form TEXT,
    material TEXT,
    max_roll_weight TEXT,
    size_thickness TEXT,
    notes TEXT,

    printing_sequence TEXT,
    extrusion_sequence TEXT,
    rewinding_slitting_sequence TEXT,
    confection_sequence TEXT,
    extrusion_folding TEXT,
```

Do not add `extrusion_flag` to the new create-table definition.

- [ ] **Step 3: Add migration columns in `init_db()`**

After `ensure_column(connection, "cards", "max_roll_weight", "TEXT")`, add:

```python
        for column_name in (
            "ordered_gross_kg",
            "ordered_rolls",
            "ordered_meters",
            "ordered_units",
            "printing_sequence",
            "extrusion_sequence",
            "rewinding_slitting_sequence",
            "confection_sequence",
        ):
            ensure_column(connection, "cards", column_name, "TEXT")
            ensure_column(connection, "card_import_sources", column_name, "TEXT")
```

This preserves existing pilot DBs without destructive column removal.

- [ ] **Step 4: Update fetch SQL for active/planning cards**

In `fetch_cards_by_status()`, replace old selected fields:

```sql
                   customer, product_type, ordered_gross_kg, ordered_rolls,
                   ordered_meters, ordered_units,
                   product_form, material, size_thickness, max_roll_weight,
```

- [ ] **Step 5: Update admin detail fetch SQL**

In `fetch_admin_card_detail()`, replace old selected fields with:

```sql
                   customer, city, product_type, ordered_gross_kg,
                   ordered_rolls, ordered_meters, ordered_units,
                   product_form, material, max_roll_weight,
                   size_thickness, notes, printing_sequence,
                   extrusion_sequence, rewinding_slitting_sequence,
                   confection_sequence, extrusion_folding,
```

- [ ] **Step 6: Update terminal detail fetch SQL**

In `fetch_terminal_card_detail()`, replace old selected fields with:

```sql
                   product_type, ordered_gross_kg, ordered_rolls,
                   ordered_meters, ordered_units,
                   product_form, material, max_roll_weight, size_thickness, notes,
                   extrusion_folding, extrusion_next_operation,
```

- [ ] **Step 7: Update any remaining active SQL references**

Run:

```bash
rg -n "quantity_1|unit_1|quantity_2|unit_2|extrusion_flag" app/db.py
```

Expected after this task: any remaining matches are comments about harmless old physical columns or tests intentionally creating old schemas. No active SELECT/INSERT/UPDATE statement should depend on old fields.

- [ ] **Step 8: Run schema/import persistence tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py::test_database_initialization_seeds_machines_1_through_4 tests/test_baseline.py::test_import_persists_structured_ordered_amounts_and_route_sequences -q
```

Expected: PASS.

---

### Task 4: Target Gross And Release Rules

**Files:**
- Modify: `app/rules.py`
- Modify: `tests/test_recipe_release_validation.py`
- Modify: `tests/test_recipe_sync.py`
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Change target gross source**

In `app/rules.py`, replace `target_gross_weight_from_card()` with:

```python
def target_gross_weight_from_card(card: dict[str, Any]) -> Decimal | None:
    quantity = decimal_from_quantity_text(card.get("ordered_gross_kg"))
    if quantity is not None and quantity > Decimal("0"):
        return quantity
    return None
```

- [ ] **Step 2: Update release reason wording**

Replace `TARGET_GROSS_RELEASE_REASON` with:

```python
TARGET_GROSS_RELEASE_REASON = "липсват поръчани бруто кг"
```

- [ ] **Step 3: Update invalid target-gross tests**

In `tests/test_recipe_release_validation.py`, replace old `quantity_1` invalid overrides with `ordered_gross_kg`:

```python
@pytest.mark.parametrize(
    ("order_number", "overrides"),
    [
        ("RS-REL-008", {"ordered_gross_kg": ""}),
        ("RS-REL-009", {"ordered_gross_kg": "0"}),
        ("RS-REL-010", {"ordered_gross_kg": "-10"}),
        ("RS-REL-011", {"ordered_gross_kg": "not a number"}),
        ("RS-REL-017", {"ordered_gross_kg": "-10 kg"}),
        ("RS-REL-018", {"ordered_gross_kg": "abc10"}),
        ("RS-REL-019", {"ordered_gross_kg": "10 kg"}),
        ("RS-REL-020", {"ordered_gross_kg": "Infinity"}),
        ("RS-REL-021", {"ordered_gross_kg": "NaN"}),
    ],
)
```

- [ ] **Step 4: Replace target gross regression names and fields**

In `tests/test_terminal_v8_render.py`, replace the old `quantity_1` target test with:

```python
def test_target_gross_uses_ordered_gross_kg_and_ignores_other_ordered_amounts(temp_db_path):
    card_id = import_ready_card(
        "V8-GROSS-1",
        ordered_gross_kg="100",
        ordered_rolls="9999",
        ordered_meters="8888",
        ordered_units="7777",
    )
    release_ready_card("V8-GROSS-1", machine_id=1, sequence=1)

    with db.connect() as connection:
        card = dict(
            connection.execute(
                "SELECT *, 0 AS total_gross_weight FROM cards WHERE id = ?",
                (card_id,),
            ).fetchone()
        )

    assert target_gross_decimal(card) == Decimal("100")
    assert remaining_gross_display(card) == "100"
    assert progress_percent(card) == 0
```

- [ ] **Step 5: Run focused release and target tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_recipe_release_validation.py tests/test_terminal_v8_render.py::test_target_gross_uses_ordered_gross_kg_and_ignores_other_ordered_amounts -q
```

Expected: PASS after helper fixtures are updated across these files.

---

### Task 5: Admin Display And Save

**Files:**
- Modify: `app/main.py`
- Modify: `app/templates/admin_card_detail.html`
- Modify: `app/db.py`
- Modify: `tests/test_admin_card_detail_redesign.py`
- Modify: `tests/test_admin_card_review.py`

- [ ] **Step 1: Update import field labels**

In `app/main.py`, replace old labels with:

```python
    "ordered_gross_kg": "Поръчано бруто, кг",
    "ordered_rolls": "Поръчани ролки",
    "ordered_meters": "Поръчани метри",
    "ordered_units": "Поръчани бройки",
    "printing_sequence": "Печат - ред",
    "extrusion_sequence": "Екструзия - ред",
    "rewinding_slitting_sequence": "Пренавиване/рязане - ред",
    "confection_sequence": "Конфекция - ред",
```

Remove labels for `quantity_1`, `unit_1`, `quantity_2`, `unit_2`, and `extrusion_flag`.

- [ ] **Step 2: Replace `build_quantity_lines()` with structured ordered amounts**

In `app/main.py`, replace `build_quantity_lines()` with:

```python
ORDERED_AMOUNT_FIELDS = (
    ("ordered_gross_kg", "Поръчано бруто", "кг"),
    ("ordered_rolls", "Поръчани ролки", "ролки"),
    ("ordered_meters", "Поръчани метри", "м"),
    ("ordered_units", "Поръчани бройки", "бр."),
)


def build_ordered_amount_lines(card: dict[str, Any]) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for field, label, unit in ORDERED_AMOUNT_FIELDS:
        value = str(card.get(field) or "").strip()
        if value:
            lines.append(
                {
                    "field": field,
                    "label": label,
                    "value": value,
                    "unit": unit,
                    "display": f"{label}: {value} {unit}",
                }
            )
    return lines
```

Update callers from `build_quantity_lines(card)` to `build_ordered_amount_lines(card)`.

- [ ] **Step 3: Update `build_quantity_display()`**

Replace the function with:

```python
def build_quantity_display(card: dict[str, Any]) -> str:
    lines = [line["display"] for line in build_ordered_amount_lines(card)]
    return " / ".join(lines) if lines else "-"
```

- [ ] **Step 4: Update admin card detail quantity fields**

In `app/templates/admin_card_detail.html`, replace the old `Количество/Мярка/Допълнително/Мярка` inputs with:

```html
            <label class="field-short">
              <span>Поръчано бруто, кг</span>
              <input name="ordered_gross_kg" value="{{ card.ordered_gross_kg or '' }}">
            </label>
            <label class="field-short">
              <span>Поръчани ролки</span>
              <input name="ordered_rolls" value="{{ card.ordered_rolls or '' }}">
            </label>
            <label class="field-short">
              <span>Поръчани метри</span>
              <input name="ordered_meters" value="{{ card.ordered_meters or '' }}">
            </label>
            <label class="field-short">
              <span>Поръчани бройки</span>
              <input name="ordered_units" value="{{ card.ordered_units or '' }}">
            </label>
```

- [ ] **Step 5: Update admin operation fields**

In `app/templates/admin_card_detail.html`, replace the `Екструзия` input with route sequence inputs:

```html
            <label class="field-short">
              <span>Печат - ред</span>
              <input name="printing_sequence" value="{{ card.printing_sequence or '' }}">
            </label>
            <label class="field-short">
              <span>Екструзия - ред</span>
              <input name="extrusion_sequence" value="{{ card.extrusion_sequence or '' }}">
            </label>
            <label class="field-short">
              <span>Пренавиване/рязане - ред</span>
              <input name="rewinding_slitting_sequence" value="{{ card.rewinding_slitting_sequence or '' }}">
            </label>
            <label class="field-short">
              <span>Конфекция - ред</span>
              <input name="confection_sequence" value="{{ card.confection_sequence or '' }}">
            </label>
```

Keep `extrusion_folding`, `extrusion_next_operation`, `extrusion_treatment`, and `packaging_method`.

- [ ] **Step 6: Run admin focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py tests/test_admin_card_review.py -q
```

Expected: PASS after fixtures and assertions are updated to the new fields.

---

### Task 6: Terminal Display

**Files:**
- Modify: `app/main.py`
- Modify: `app/templates/terminal.html`
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_terminal_detail.py`

- [ ] **Step 1: Add terminal display fields in the detail block**

In `app/templates/terminal.html`, replace the generic `Количество` field with:

```html
                    <div class="field">
                      <span class="field-label">Поръчано бруто, кг</span>
                      <div class="value">{{ selected_card.ordered_gross_kg or "-" }}</div>
                    </div>
                    <div class="field">
                      <span class="field-label">Поръчани ролки</span>
                      <div class="value">{{ selected_card.ordered_rolls or "-" }}</div>
                    </div>
                    <div class="field">
                      <span class="field-label">Поръчани метри</span>
                      <div class="value">{{ selected_card.ordered_meters or "-" }}</div>
                    </div>
                    <div class="field">
                      <span class="field-label">Поръчани бройки</span>
                      <div class="value">{{ selected_card.ordered_units or "-" }}</div>
                    </div>
```

- [ ] **Step 2: Add missing production-detail fields**

In the same `info-grid`, add:

```html
                    <div class="field">
                      <span class="field-label">Дата доставка</span>
                      <div class="value">{{ selected_card.delivery_date or "-" }}</div>
                    </div>
                    <div class="field">
                      <span class="field-label">Фалцоване</span>
                      <div class="value">{{ selected_card.extrusion_folding or "-" }}</div>
                    </div>
                    <div class="field">
                      <span class="field-label">Следваща операция</span>
                      <div class="value">{{ selected_card.extrusion_next_operation or "-" }}</div>
                    </div>
                    <div class="field">
                      <span class="field-label">Третиране</span>
                      <div class="value">{{ selected_card.extrusion_treatment or "-" }}</div>
                    </div>
                    <div class="field">
                      <span class="field-label">Опаковка</span>
                      <div class="value">{{ selected_card.packaging_method or "-" }}</div>
                    </div>
```

- [ ] **Step 3: Update queue row expectations**

Queue and produced rows can keep using `card.quantity_display`; after Task 5 it will render structured ordered amounts. Do not add new controls.

- [ ] **Step 4: Add terminal render assertion**

In `tests/test_terminal_v8_render.py`, add:

```python
def test_terminal_v8_shows_structured_ordered_amounts_and_extrusion_details(temp_db_path):
    card_id = import_ready_card(
        "V8-STRUCT-1",
        delivery_date="01/08/2026",
        ordered_gross_kg="500",
        ordered_rolls="20",
        ordered_meters="15000",
        ordered_units="40000",
        extrusion_folding="folding detail",
        extrusion_next_operation="Printing",
        extrusion_treatment="corona",
        packaging_method="1 big pallet",
    )
    release_ready_card("V8-STRUCT-1", machine_id=1, sequence=1)

    context = terminal_context(selected_card_id=card_id)
    html = render_terminal_template(context)

    assert "Поръчано бруто, кг" in html
    assert "500" in html
    assert "Поръчани ролки" in html
    assert "20" in html
    assert "Поръчани метри" in html
    assert "15000" in html
    assert "Поръчани бройки" in html
    assert "40000" in html
    assert "Дата доставка" in html
    assert "01/08/2026" in html
    assert "Фалцоване" in html
    assert "folding detail" in html
    assert "Следваща операция" in html
    assert "Printing" in html
    assert "Третиране" in html
    assert "corona" in html
    assert "Опаковка" in html
    assert "1 big pallet" in html
```

- [ ] **Step 5: Run terminal focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_v8_shows_structured_ordered_amounts_and_extrusion_details tests/test_terminal_detail.py -q
```

Expected: PASS.

---

### Task 7: Update Remaining Test Fixtures

**Files:**
- Modify: `tests/test_terminal_sync.py`
- Modify: `tests/test_production_timing.py`
- Modify: `tests/test_recipe_storage.py`
- Modify: `tests/test_admin_production_corrections.py`
- Modify: `tests/test_finish_cancel_history.py`
- Modify: `tests/test_admin_routes.py`
- Modify: `tests/test_admin_planning.py`
- Modify: `tests/test_roll_entry.py`
- Modify: `tests/test_recipe_sync.py`
- Modify: `tests/test_backup_recovery.py`
- Do not modify: `tests/test_print_output.py` unless it fails during broad import collection for reasons unrelated to print semantics.

- [ ] **Step 1: Replace fixture field names**

In each non-print test fixture, replace:

```python
"quantity_1": "500",
"unit_1": "kg",
"quantity_2": "5",
"unit_2": "ролки",
"extrusion_flag": "da",
```

with:

```python
"ordered_gross_kg": "500",
"ordered_rolls": "5",
"ordered_meters": "",
"ordered_units": "",
"printing_sequence": "",
"extrusion_sequence": "1",
"rewinding_slitting_sequence": "",
"confection_sequence": "",
```

Preserve existing test-specific values by mapping:

- old gross target from `quantity_1` to `ordered_gross_kg`;
- old roll count from `quantity_2` to `ordered_rolls` only when `quantity_2` represented rolls;
- route marker from `extrusion_flag` to `extrusion_sequence="1"`.

- [ ] **Step 2: Update direct SQL fixture schemas in tests**

Where tests create ad hoc `cards` tables, replace old field columns with:

```sql
ordered_gross_kg TEXT,
ordered_rolls TEXT,
ordered_meters TEXT,
ordered_units TEXT,
printing_sequence TEXT,
extrusion_sequence TEXT,
rewinding_slitting_sequence TEXT,
confection_sequence TEXT,
```

- [ ] **Step 3: Update assertions that old fields are preserved**

Replace assertions such as:

```python
assert unchanged["extrusion_flag"] == "da"
assert fields["quantity_1"] == "500"
```

with:

```python
assert unchanged["extrusion_sequence"] == "1"
assert fields["ordered_gross_kg"] == "500"
```

- [ ] **Step 4: Search for remaining active old fields**

Run:

```bash
rg -n "quantity_1|unit_1|quantity_2|unit_2|extrusion_flag" app tests README.md IMPLEMENTATION_PLAN.md docs/implementation-notes
```

Expected: matches may remain only in:

- `app/printing.py`
- `app/templates/print_card.html`
- `tests/test_print_output.py`
- historical docs under `docs/superpowers/plans/`
- the new implementation note if it is explaining the old mismatch

No active importer, DB, rules, admin, terminal, or non-print test fixture should use the old fields.

- [ ] **Step 5: Run broad non-print tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_baseline.py tests/test_terminal_detail.py tests/test_terminal_sync.py tests/test_production_timing.py tests/test_recipe_storage.py tests/test_admin_card_detail_redesign.py tests/test_admin_production_corrections.py tests/test_finish_cancel_history.py tests/test_admin_routes.py tests/test_admin_card_review.py tests/test_admin_planning.py tests/test_roll_entry.py tests/test_recipe_release_validation.py tests/test_terminal_v8_render.py tests/test_recipe_sync.py tests/test_backup_recovery.py -q
```

Expected: PASS.

---

### Task 8: Documentation And Milestone Tracking

**Files:**
- Modify: `README.md`
- Modify: `IMPLEMENTATION_PLAN.md`
- Verify deleted: `EXCEL_EXPORT_CONTRACT.md`

- [ ] **Step 1: Update README failed-import troubleshooting**

In `README.md`, replace the stale failed-import bullet with:

```markdown
- Failed imports: confirm the uploaded file is CSV, uses the current Shift Manager export headers including `order_number`, `ordered_gross_kg`, and `extrusion_sequence`, and includes extrusion detail data. Rows where `extrusion_sequence` is not `1` are reported in the import result and skipped.
```

- [ ] **Step 2: Add milestone note**

In `IMPLEMENTATION_PLAN.md`, add a new current milestone section after the latest completed milestone:

```markdown
## Milestone 10 - Shift Manager Export/Import Field Correctness

Status: in progress

Scope:

- align app CSV import with the current Shift Manager export structure;
- replace generic quantity/unit import fields with structured ordered amount fields;
- store numeric route sequence fields from the workbook export;
- use `extrusion_sequence == 1` as the extrusion import eligibility signal;
- use `ordered_gross_kg` as the only target gross source;
- update admin and terminal displays for structured ordered amounts and approved production-detail fields;
- leave print output unchanged for the separate print update task.

Review checkpoint:

- focused import/release tests pass with temporary SQLite databases;
- overwrite import still preserves production data;
- admin detail shows and saves structured ordered amount fields;
- terminal details show ordered gross kg clearly plus rolls, meters, units, delivery, folding, next operation, treatment, and packaging;
- Playwright screenshot captured for the updated terminal detail display;
- no real runtime database was mutated.
```

- [ ] **Step 3: Verify stale contract file is gone**

Run:

```bash
test ! -e EXCEL_EXPORT_CONTRACT.md
```

Expected: command exits with status `0`.

---

### Task 9: Verification

**Files:**
- No planned source edits.
- Artifacts: `artifacts/ui-checks/`

- [ ] **Step 1: Run syntax/import check**

Run:

```bash
source .venv/bin/activate
python -m compileall app tests
```

Expected: no syntax errors.

- [ ] **Step 2: Run full pytest suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected: all non-print tests pass. If `tests/test_print_output.py` fails only because print remains intentionally stale, report that explicitly instead of changing print files.

- [ ] **Step 3: Start local server for UI verification**

Run:

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected: server starts and listens on `127.0.0.1:8000`.

- [ ] **Step 4: Capture focused terminal screenshot**

Use local Playwright to import/release a temporary-database card or use the existing Playwright helpers if present. Save the screenshot under:

```text
artifacts/ui-checks/shift-manager-import-field-correctness-terminal.png
```

Expected screenshot evidence:

- terminal details show `Поръчано бруто, кг`;
- terminal details show ordered rolls/meters/units;
- terminal details show delivery, folding, next operation, treatment, and packaging;
- no terminal cancel/restore/calculator controls were added.

- [ ] **Step 5: Check whitespace and unintended print edits**

Run:

```bash
git diff --check
git diff -- app/printing.py app/templates/print_card.html
```

Expected:

- `git diff --check` reports no whitespace errors;
- no diff appears for `app/printing.py` or `app/templates/print_card.html`.

- [ ] **Step 6: Review final diff**

Run:

```bash
git diff --stat
git diff -- app/importer.py app/db.py app/rules.py app/main.py app/templates/admin_card_detail.html app/templates/terminal.html README.md IMPLEMENTATION_PLAN.md
```

Expected: changes are limited to the approved import/storage/admin/terminal/docs scope.

Do not stage or commit unless the user explicitly asks.

---

## Self-Review Notes

- Spec coverage: covered import header, structured ordered amounts, route sequence storage, extrusion eligibility, target gross, admin display/edit, terminal display, docs, and verification.
- Explicitly out of scope: print output/template, micro perforation, workbook macro edits, calculator access, terminal cancellation/restore.
- Migration stance: non-destructive SQLite migration; old columns may remain physically present but are not part of active app logic.
- User approval needed before implementation starts: choose subagent-driven or inline execution.
