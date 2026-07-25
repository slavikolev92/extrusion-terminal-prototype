# Task 02 — Admin Visibility Implementation Plan

This is the archived implementation plan for the admin-visibility slice of
completed Task 02. Do not execute it as current work.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the final Shift Manager ordered and route fields visible and correct across the four admin surfaces.

**Architecture:** Keep the existing FastAPI routes, direct SQLite queries, and server-rendered Jinja templates. Extend only the current admin view models and templates; resolve import links dynamically from the unique order number and reuse M001 columns without adding schema or compatibility code.

**Tech Stack:** Python 3, FastAPI, Jinja2, direct `sqlite3`, pytest with temporary databases, repo-local Playwright, HTML/CSS.

## Global Constraints

- Read repository-root `AGENTS.md` and
  `v2-files/archive/TASK-02-ADMIN-DESIGN.md` before starting.
- Accept only the exact final 29-column Shift Manager CSV header in exact order.
- Do not restore legacy CSV aliases or old-field compatibility.
- Do not add `micro_perforation`.
- `ordered_gross_kg` is the only target gross source.
- `extrusion_sequence == "1"` is the only extrusion eligibility signal.
- Use the workbook label `Фалдиране`.
- Do not change terminal or print behavior in this plan.
- Do not add or modify a database migration; Task 2 reads M001 columns only.
- Automated and live UI checks must use temporary SQLite databases, never `data/extrusion_terminal.sqlite3`.
- Preserve loaded-version conflict checks and all production data.
- Do not stage or commit. Replace commit steps with explicit review checkpoints.
- Stop after each task for the two-stage review required by subagent-driven development.

---

## File Map

- `app/db.py`: admin list queries and persisted import-result view model.
- `app/main.py`: shared imported-field labels only; no new route is required.
- `app/templates/admin_import.html`: successful import-row links.
- `app/templates/admin_planning.html`: ordered gross in drafts and active queues.
- `app/templates/admin_cards.html`: delivery date and ordered gross list columns.
- `app/templates/admin_card_detail.html`: accepted folding label; existing eight inputs remain.
- `app/static/css/app.css`: planning gross-column width and responsive table width.
- `tests/test_admin_routes.py`: import-result and planning route rendering.
- `tests/test_admin_planning.py`: existing planning workflow regression coverage.
- `tests/test_admin_card_review.py`: admin list query and imported-field persistence.
- `tests/test_admin_card_detail_redesign.py`: cards-list/detail rendering and save coverage.
- `tests/test_baseline.py`: import/persistence regression suite; verification only.
- `v2-files/archive/TASK-02-STRUCTURE-CLEANUP.md`: result and next-task
  checkpoint after verification.
- `artifacts/ui-checks/v2/admin/`: untracked browser screenshots.

No new production source file or database column is required.

---

### Task 1: Link Successful Import Results To Current Cards

**Files:**

- Modify: `tests/test_admin_routes.py:187-243`
- Modify: `app/db.py:3972-4036`
- Modify: `app/templates/admin_import.html:48-68`

**Interfaces:**

- Consumes: persisted `import_batch_rows.order_number`, `import_batch_rows.action`, and unique `cards.order_number`.
- Produces: each dictionary in `fetch_import_batch_result(batch_id)["row_results"]` includes `card_id: int | None`.
- Produces: successful `created` and `updated` rows link to `/admin/cards/{card_id}`; all other rows remain plain text.

- [ ] **Step 1: Extend the persisted import-result test with the missing link contract**

In `test_successful_admin_import_redirects_to_batch_result_get`, read the created
card and assert both the view-model relationship and rendered link:

```python
    created_card_id = int(
        connection.execute(
            "SELECT id FROM cards WHERE order_number = ?",
            ("25901",),
        ).fetchone()["id"]
    )
    created_row = next(
        row
        for row in persisted_result["row_results"]
        if row["order_number"] == "25901"
    )
    skipped_row = next(
        row
        for row in persisted_result["row_results"]
        if row["order_number"] == "31999"
    )

    assert created_row["card_id"] == created_card_id
    assert skipped_row["card_id"] is None
    assert f'<a href="/admin/cards/{created_card_id}">25901</a>' in html
```

Also assert that the skipped row does not receive that link:

```python
    skipped_cell = html.split(">31999<", 1)[0].rsplit("<td", 1)[-1]
    assert "/admin/cards/" not in skipped_cell
```

- [ ] **Step 2: Add the missing-current-card fallback test**

Add this focused test to `tests/test_admin_routes.py`:

```python
def test_admin_import_result_keeps_deleted_successful_card_as_plain_text(connection):
    result = import_cards_from_csv(
        "deleted-result-card.csv",
        csv_bytes(extrusion_row("25904")),
        overwrite_existing=False,
    )
    assert result.batch_id is not None
    card_id = int(
        connection.execute(
            "SELECT id FROM cards WHERE order_number = ?",
            ("25904",),
        ).fetchone()["id"]
    )
    connection.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    connection.commit()

    persisted = db.fetch_import_batch_result(int(result.batch_id))
    response = asyncio.run(
        admin_import(
            make_request("/admin/import", method="GET"),
            batch_id=int(result.batch_id),
        )
    )
    html = response.body.decode("utf-8")

    assert persisted is not None
    assert persisted["row_results"][0]["card_id"] is None
    assert "25904" in html
    assert f'href="/admin/cards/{card_id}"' not in html
```

- [ ] **Step 3: Add updated-row link coverage**

Add this focused test to `tests/test_admin_routes.py`:

```python
def test_admin_import_result_links_updated_row_to_existing_card(connection):
    first = import_cards_from_csv(
        "updated-row-first.csv",
        csv_bytes(extrusion_row("25905", customer="Before Update")),
        overwrite_existing=False,
    )
    assert first.rows_imported == 1
    card_id = int(
        connection.execute(
            "SELECT id FROM cards WHERE order_number = ?",
            ("25905",),
        ).fetchone()["id"]
    )

    updated = import_cards_from_csv(
        "updated-row-second.csv",
        csv_bytes(extrusion_row("25905", customer="After Update")),
        overwrite_existing=True,
    )
    assert updated.batch_id is not None
    persisted = db.fetch_import_batch_result(int(updated.batch_id))
    response = asyncio.run(
        admin_import(
            make_request("/admin/import", method="GET"),
            batch_id=int(updated.batch_id),
        )
    )
    html = response.body.decode("utf-8")

    assert persisted is not None
    assert persisted["row_results"][0]["action"] == "updated"
    assert persisted["row_results"][0]["card_id"] == card_id
    assert f'<a href="/admin/cards/{card_id}">25905</a>' in html
```

- [ ] **Step 4: Run the three tests and verify the red state**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_admin_routes.py::test_successful_admin_import_redirects_to_batch_result_get \
  tests/test_admin_routes.py::test_admin_import_result_keeps_deleted_successful_card_as_plain_text \
  tests/test_admin_routes.py::test_admin_import_result_links_updated_row_to_existing_card -q
```

Expected: FAIL because persisted row results do not contain `card_id` and the
created order number is not rendered as a link.

- [ ] **Step 5: Extend the persisted import-result query**

In `fetch_import_batch_result()`, qualify the import-row columns and join the
current card:

```sql
SELECT
    import_batch_rows.row_number,
    import_batch_rows.order_number,
    import_batch_rows.action,
    import_batch_rows.message,
    import_batch_rows.is_duplicate_row,
    import_batch_rows.row_error,
    cards.id AS current_card_id
FROM import_batch_rows
LEFT JOIN cards
  ON cards.order_number = import_batch_rows.order_number
WHERE import_batch_rows.import_batch_id = ?
ORDER BY import_batch_rows.display_order, import_batch_rows.id
```

Add the optional relationship to each returned row dictionary:

```python
            "card_id": (
                int(row["current_card_id"])
                if row["action"] in ("created", "updated")
                and row["current_card_id"] is not None
                else None
            ),
```

Do not change `import_batch_rows`, `ImportRowResult`, or the migration registry.

- [ ] **Step 6: Render links only when `card_id` is present**

Replace the plain order cell in `admin_import.html` with:

```jinja2
<td>
  {% if row.card_id %}
    <a href="/admin/cards/{{ row.card_id }}">{{ row.order_number }}</a>
  {% else %}
    {{ row.order_number or "-" }}
  {% endif %}
</td>
```

The inline invalid-header result still renders safely because it has no
successful row and a missing Jinja attribute is false.

- [ ] **Step 7: Run the focused import-result tests and verify green**

Run the command from Step 4.

Expected: all three tests PASS.

- [ ] **Step 8: Run the full admin-route file**

Run:

```bash
.venv/bin/python -m pytest tests/test_admin_routes.py -q
```

Expected: all tests PASS with import counts, PRG behavior, and skipped-row
messages unchanged.

- [ ] **Step 9: Review checkpoint**

Inspect:

```bash
git diff -- app/db.py app/templates/admin_import.html tests/test_admin_routes.py
git diff --check
```

Confirm no schema, importer-contract, or non-admin change. Do not stage or
commit. Stop for specification-compliance and code-quality review.

---

### Task 2: Show Ordered Gross In Planning

**Files:**

- Modify: `tests/test_admin_routes.py:108-116,293-345,715-745`
- Modify: `app/templates/admin_planning.html:47-114,123-148`
- Modify: `app/static/css/app.css:397-460,1768-1776`
- Test: `tests/test_admin_planning.py`

**Interfaces:**

- Consumes: `fetch_cards_by_status()` dictionaries, which already include `ordered_gross_kg`.
- Produces: draft table column `col-gross` and active queue line `queue-card-gross`.
- Produces: populated values as `<stored text> кг`; blank values as `-` without `кг`.

- [ ] **Step 1: Allow the admin-route import helper to set a gross value**

Change the helper signature without breaking existing callers:

```python
def import_route_card(order_number: str, **overrides: str) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number, **overrides)),
        overwrite_existing=False,
    )
```

- [ ] **Step 2: Add draft-table gross assertions**

In `test_admin_planning_renders_compact_unreleased_release_table`, give the
first row `ordered_gross_kg="725.50"` and the second row
`ordered_gross_kg=""`. Add:

```python
    assert '<th class="col-gross">Поръчано бруто, кг</th>' in html
    assert '<td class="col-gross">725.50 кг</td>' in html
    assert '<td class="col-gross">-</td>' in html
```

- [ ] **Step 3: Add active-queue gross assertions**

In `test_admin_planning_renders_unrelease_form_for_pending_queue_cards_only`,
create the two cards with explicit values:

```python
    pending_id = import_route_card("25924", ordered_gross_kg="640.25")
    running_id = import_route_card("25925", ordered_gross_kg="")
```

Then add:

```python
    assert '<small class="queue-card-gross">Поръчано бруто: 640.25 кг</small>' in html
    assert '<small class="queue-card-gross">Поръчано бруто: -</small>' in html
    assert "Поръчано бруто: - кг" not in html
```

- [ ] **Step 4: Add a CSS contract assertion**

Within the compact-table test, read the existing stylesheet using the already
imported `Path` and assert the new fixed-width rules:

```python
    css = Path("app/static/css/app.css").read_text(encoding="utf-8")
    assert ".unreleased-table .col-gross {" in css
    assert "width: 118px;" in css
    assert "min-width: 1000px;" in css
```

- [ ] **Step 5: Run the planning rendering tests and verify the red state**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_admin_routes.py::test_admin_planning_renders_compact_unreleased_release_table \
  tests/test_admin_routes.py::test_admin_planning_renders_unrelease_form_for_pending_queue_cards_only -q
```

Expected: FAIL because the draft gross column, active-queue line, and CSS width
do not exist.

- [ ] **Step 6: Add the draft gross column**

In `admin_planning.html`, place the new header after `Изделие` and before
`Макс. кг/ролка`:

```jinja2
<th class="col-gross">Поръчано бруто, кг</th>
```

Add the matching cell after the product cell:

```jinja2
<td class="col-gross">{% if card.ordered_gross_kg %}{{ card.ordered_gross_kg }} кг{% else %}-{% endif %}</td>
```

- [ ] **Step 7: Add the active-queue gross line**

Inside `queue-card-main`, after the product type and before the status pill,
add:

```jinja2
<small class="queue-card-gross">Поръчано бруто: {% if card.ordered_gross_kg %}{{ card.ordered_gross_kg }} кг{% else %}-{% endif %}</small>
```

- [ ] **Step 8: Extend the planning table CSS**

Add next to the other `.unreleased-table` column widths:

```css
.unreleased-table .col-gross {
  width: 118px;
}
```

Change the narrow-screen table minimum from `880px` to:

```css
.unreleased-table {
  min-width: 1000px;
}
```

Do not redesign queue cards or other admin tables.

- [ ] **Step 9: Run the focused tests and verify green**

Run the command from Step 5.

Expected: both tests PASS.

- [ ] **Step 10: Run planning regressions**

Run:

```bash
.venv/bin/python -m pytest tests/test_admin_routes.py tests/test_admin_planning.py -q
```

Expected: all tests PASS; sorting, release, resequencing, unrelease, and
conflict behavior remain unchanged.

- [ ] **Step 11: Review checkpoint**

Inspect:

```bash
git diff -- app/templates/admin_planning.html app/static/css/app.css tests/test_admin_routes.py
git diff --check
```

Confirm there is no new query, write path, or terminal markup. Do not stage or
commit. Stop for specification-compliance and code-quality review.

---

### Task 3: Add Delivery And Ordered Gross To The Cards List

**Files:**

- Modify: `tests/test_admin_card_review.py:60-93`
- Modify: `tests/test_admin_card_detail_redesign.py:168-182,421-447`
- Modify: `app/db.py:742-780`
- Modify: `app/templates/admin_cards.html:48-75`

**Interfaces:**

- Produces: every `fetch_admin_cards()` row includes `delivery_date` and `ordered_gross_kg`.
- Produces: cards-list columns `Доставка` and `Поръчано бруто, кг`.
- Preserves: filters, ordering, 100-row limit, status pills, and `Отвори` actions.

- [ ] **Step 1: Add a query-contract test**

Add to `tests/test_admin_card_review.py`:

```python
def test_admin_card_index_includes_delivery_and_ordered_gross(connection):
    import_ready_card(
        "25715",
        delivery_date="2026-06-29",
        ordered_gross_kg="875.50",
    )

    card = next(
        card
        for card in db.fetch_admin_cards({"order_number": "25715"})
        if card["order_number"] == "25715"
    )

    assert card["delivery_date"] == "2026-06-29"
    assert card["ordered_gross_kg"] == "875.50"
```

- [ ] **Step 2: Add cards-list rendering coverage**

Add to `tests/test_admin_card_detail_redesign.py`:

```python
def test_admin_cards_list_shows_delivery_and_ordered_gross(connection):
    import_ready_card(
        "27049",
        delivery_date="2026-06-29",
        ordered_gross_kg="875.50",
    )

    html = render_admin_cards_list()

    assert "<th>Доставка</th>" in html
    assert "<th>Поръчано бруто, кг</th>" in html
    assert "2026-06-29" in html
    assert "875.50 кг" in html
```

Add a second imported card with blank values and assert no dangling unit:

```python
    import_ready_card("27050", delivery_date="", ordered_gross_kg="")
    html = render_admin_cards_list()
    blank_row = html.split("<td>27050</td>", 1)[1].split("</tr>", 1)[0]
    assert blank_row.count("<td>-</td>") >= 2
    assert "- кг" not in html
```

- [ ] **Step 3: Run the new tests and verify the red state**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_admin_card_review.py::test_admin_card_index_includes_delivery_and_ordered_gross \
  tests/test_admin_card_detail_redesign.py::test_admin_cards_list_shows_delivery_and_ordered_gross -q
```

Expected: FAIL because `fetch_admin_cards()` omits both fields and the list has
neither column.

- [ ] **Step 4: Extend the cards-list query**

Change the `fetch_admin_cards()` projection to:

```sql
SELECT id, order_number, delivery_date, status, customer, product_type,
       ordered_gross_kg, machine_id, machine_sequence, updated_at
FROM cards
```

Do not add new filters or change ordering.

- [ ] **Step 5: Add the two cards-list columns**

In `admin_cards.html`, add headers after `Поръчка`:

```jinja2
<th>Доставка</th>
<th>Поръчано бруто, кг</th>
```

Add matching cells after the order number:

```jinja2
<td>{{ card.delivery_date or "-" }}</td>
<td>{% if card.ordered_gross_kg %}{{ card.ordered_gross_kg }} кг{% else %}-{% endif %}</td>
```

- [ ] **Step 6: Run the new tests and verify green**

Run the command from Step 3.

Expected: both tests PASS.

- [ ] **Step 7: Run cards-list and review regressions**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_admin_card_review.py \
  tests/test_admin_card_detail_redesign.py -q
```

Expected: all tests PASS, including filter behavior and absence of list print
shortcuts.

- [ ] **Step 8: Review checkpoint**

Inspect:

```bash
git diff -- app/db.py app/templates/admin_cards.html tests/test_admin_card_review.py tests/test_admin_card_detail_redesign.py
git diff --check
```

Confirm the query projection is the only database-layer change. Do not stage or
commit. Stop for specification-compliance and code-quality review.

---

### Task 4: Lock Down The Final Card-Detail Contract

**Files:**

- Modify: `tests/test_admin_card_detail_redesign.py:30-58,501-515,609-655`
- Modify: `tests/test_admin_card_review.py:135-184`
- Modify: `app/main.py:109-135`
- Modify: `app/templates/admin_card_detail.html:180-250`

**Interfaces:**

- Consumes: the existing eight M001 fields returned by `fetch_admin_card_detail()`.
- Consumes: the existing generic `IMPORT_FIELDS` form parsing and save path.
- Produces: regression proof that all eight fields render and save.
- Produces: `Фалдиране` as the visible and shared label for `extrusion_folding`.

- [ ] **Step 1: Complete the dense final-contract fixture**

Add the remaining ordered and route fields to `extrusion_row()` in
`tests/test_admin_card_detail_redesign.py`:

```python
        "ordered_meters": "15000",
        "ordered_units": "40000",
        "printing_sequence": "2",
        "rewinding_slitting_sequence": "3",
        "confection_sequence": "4",
```

Keep `extrusion_sequence="1"`.

- [ ] **Step 2: Add final field rendering and legacy-name rejection coverage**

Add this test:

```python
def test_admin_detail_renders_only_final_ordered_and_route_inputs(connection):
    card_id = import_ready_card("27122")
    html = render_admin_detail(card_id)

    expected_inputs = {
        "ordered_gross_kg": "3250.50",
        "ordered_rolls": "60",
        "ordered_meters": "15000",
        "ordered_units": "40000",
        "printing_sequence": "2",
        "extrusion_sequence": "1",
        "rewinding_slitting_sequence": "3",
        "confection_sequence": "4",
    }
    for name, value in expected_inputs.items():
        assert f'name="{name}" value="{value}"' in html

    for old_name in (
        "quantity_1",
        "unit_1",
        "quantity_2",
        "unit_2",
        "extrusion_flag",
    ):
        assert f'name="{old_name}"' not in html

    assert "Фалдиране" in html
    assert "Фалцоване" not in html
```

- [ ] **Step 3: Extend the ordered-amount context expectation**

In `test_admin_card_detail_context_groups_quantities_and_recipe_rows`, update
the expected `quantity_lines` to all four populated final fields:

```python
    assert [line["display"] for line in context["quantity_lines"]] == [
        "Поръчано бруто: 500 кг",
        "Поръчани ролки: 1200 ролки",
        "Поръчани метри: 15000 м",
        "Поръчани бройки: 40000 бр.",
    ]
```

- [ ] **Step 4: Extend the save test to all eight fields**

In `test_admin_order_form_save_preserves_omitted_recipe_fields`, add these
submitted pairs:

```python
                        ("ordered_meters", "21000"),
                        ("ordered_units", "51000"),
                        ("printing_sequence", "2"),
                        ("rewinding_slitting_sequence", "3"),
                        ("confection_sequence", "4"),
```

Keep `ordered_gross_kg`, `ordered_rolls`, and `extrusion_sequence`. Add:

```python
    assert updated["ordered_gross_kg"] == "4250"
    assert updated["ordered_rolls"] == "80"
    assert updated["ordered_meters"] == "21000"
    assert updated["ordered_units"] == "51000"
    assert updated["printing_sequence"] == "2"
    assert updated["extrusion_sequence"] == "1"
    assert updated["rewinding_slitting_sequence"] == "3"
    assert updated["confection_sequence"] == "4"
```

- [ ] **Step 5: Run the detail tests and verify the red/characterization state**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_admin_card_detail_redesign.py::test_admin_detail_renders_only_final_ordered_and_route_inputs \
  tests/test_admin_card_detail_redesign.py::test_admin_order_form_save_preserves_omitted_recipe_fields \
  tests/test_admin_card_review.py::test_admin_card_detail_context_groups_quantities_and_recipe_rows -q
```

Expected: the final-field render/save assertions characterize already-connected
behavior; the render test FAILS because the current label is `Фалцоване`.

- [ ] **Step 6: Correct both admin folding labels**

In `IMPORT_FIELD_LABELS` in `app/main.py`, change:

```python
    "extrusion_folding": "Фалдиране",
```

In `admin_card_detail.html`, change the visible input label to:

```jinja2
<span>Фалдиране</span>
```

Do not rename the persisted field `extrusion_folding`.

- [ ] **Step 7: Run the focused detail tests and verify green**

Run the command from Step 5.

Expected: all three tests PASS.

- [ ] **Step 8: Run both detail suites**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_admin_card_review.py \
  tests/test_admin_card_detail_redesign.py -q
```

Expected: all tests PASS; stale-write, duplicate-order, recipe, roll, timing,
and production-data preservation behavior remain unchanged.

- [ ] **Step 9: Review checkpoint**

Inspect:

```bash
git diff -- app/main.py app/templates/admin_card_detail.html tests/test_admin_card_review.py tests/test_admin_card_detail_redesign.py
git diff --check
```

Confirm only copy and test coverage changed in production code. Do not stage or
commit. Stop for specification-compliance and code-quality review.

---

### Task 5: Verify The Complete Admin Slice And Record The Checkpoint

**Files:**

- Modify after verification: `v2-files/archive/TASK-02-STRUCTURE-CLEANUP.md`
- Create untracked evidence: `artifacts/ui-checks/v2/admin/*.png`
- Do not modify: `v2-files/AGENTS.md` unless the user separately invokes the phrase `maintain the database migration system`.

**Interfaces:**

- Consumes: all Task 1-4 admin query, view-model, template, label, CSS, and test changes.
- Produces: fresh automated counts, four live screenshots, scope review, and the exact next task in the temporary cleanup tracker.

- [ ] **Step 1: Run Python compilation**

Run:

```bash
.venv/bin/python -m compileall app tests
```

Expected: exit 0 with no syntax/import compilation errors.

- [ ] **Step 2: Run the complete focused admin suite**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_admin_routes.py \
  tests/test_admin_planning.py \
  tests/test_admin_card_review.py \
  tests/test_admin_card_detail_redesign.py -q
```

Expected: all tests PASS. Record the observed pass count; do not copy the
pre-change count of 94.

- [ ] **Step 3: Run the import/persistence regression suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_baseline.py -q
```

Expected: all tests PASS using pytest temporary database paths.

- [ ] **Step 4: Review formatting and scope**

Run:

```bash
git diff --check
git diff -- app/db.py app/main.py app/templates/admin_import.html app/templates/admin_planning.html app/templates/admin_cards.html app/templates/admin_card_detail.html app/static/css/app.css tests/test_admin_routes.py tests/test_admin_planning.py tests/test_admin_card_review.py tests/test_admin_card_detail_redesign.py
```

Expected: no whitespace errors and no terminal, printing, importer-contract,
migration, or unrelated refactor changes.

- [ ] **Step 5: Create a fresh temporary live-check database**

In one shell, run:

```bash
mkdir -p .test-runtime artifacts/ui-checks/v2/admin
V2_ADMIN_RUNTIME=$(mktemp -d "$PWD/.test-runtime/v2-admin.XXXXXX")
export V2_ADMIN_RUNTIME
export EXTRUSION_DB_PATH="$V2_ADMIN_RUNTIME/extrusion_terminal.sqlite3"
.venv/bin/python - <<'PY'
from pathlib import Path

from app import db
from app.importer import import_cards_from_csv

db.init_db()
result = import_cards_from_csv(
    "extrusion_orders_20260725_110012.csv",
    Path("source-files/extrusion_orders_20260725_110012.csv").read_bytes(),
    overwrite_existing=False,
)
assert result.batch_id == 1
assert (result.rows_seen, result.rows_imported, result.created, result.skipped) == (
    3,
    3,
    3,
    0,
)
with db.connect() as connection:
    rows = connection.execute(
        "SELECT id, order_number, version FROM cards ORDER BY id"
    ).fetchall()
assert [(row["id"], row["order_number"]) for row in rows] == [
    (1, "25450"),
    (2, "25451"),
    (3, "25452"),
]
assert db.release_card(
    card_id=1,
    machine_id=1,
    machine_sequence=1,
    loaded_version=int(rows[0]["version"]),
    max_roll_weight="60",
).ok
print(f"temporary database: {db.DB_PATH}")
print("batch_id=1; detail_card_id=1")
PY
```

Expected: the assertions pass, order `25450` becomes the active queue card,
and orders `25451`-`25452` remain drafts. The real runtime DB is not opened.

- [ ] **Step 6: Start the live app against only that temporary database**

In the same shell, run:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8768
```

Expected: the app starts on `http://127.0.0.1:8768` using the exported
`EXTRUSION_DB_PATH`.

- [ ] **Step 7: Check all four admin routes and required text**

In a second shell, run:

```bash
curl -fsS 'http://127.0.0.1:8768/admin/import?batch_id=1' | rg 'href="/admin/cards/1">25450</a>'
curl -fsS 'http://127.0.0.1:8768/admin/planning' | rg 'Поръчано бруто|25450|25451|25452'
curl -fsS 'http://127.0.0.1:8768/admin/cards' | rg 'Доставка|Поръчано бруто, кг|500 кг'
curl -fsS 'http://127.0.0.1:8768/admin/cards/1' | rg 'ordered_gross_kg|ordered_rolls|ordered_meters|ordered_units|printing_sequence|extrusion_sequence|rewinding_slitting_sequence|confection_sequence|Фалдиране'
```

Expected: every command exits 0. Also check status directly:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8768/admin/import?batch_id=1'
curl -sS -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8768/admin/planning'
curl -sS -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8768/admin/cards'
curl -sS -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8768/admin/cards/1'
```

Expected: four `200` responses.

- [ ] **Step 8: Capture one full-page screenshot per admin surface**

Run:

```bash
npx playwright screenshot --full-page --viewport-size=1440,1000 'http://127.0.0.1:8768/admin/import?batch_id=1' artifacts/ui-checks/v2/admin/import-result.png
npx playwright screenshot --full-page --viewport-size=1440,1000 'http://127.0.0.1:8768/admin/planning' artifacts/ui-checks/v2/admin/planning.png
npx playwright screenshot --full-page --viewport-size=1440,1000 'http://127.0.0.1:8768/admin/cards' artifacts/ui-checks/v2/admin/cards.png
npx playwright screenshot --full-page --viewport-size=1440,1000 'http://127.0.0.1:8768/admin/cards/1' artifacts/ui-checks/v2/admin/card-detail.png
```

Expected: four PNG files under the ignored artifacts directory.

- [ ] **Step 9: Inspect the screenshots**

Open all four images with the local image-viewing tool. Confirm:

- the successful import order number is visibly linked;
- draft and active planning values are readable and release controls are not crushed;
- the cards table shows delivery and gross values without unusable wrapping;
- detail shows all eight inputs and `Фалдиране`;
- no terminal print/cancel/restore controls or print changes were introduced.

If the planning table is cramped, adjust only `.col-gross` and the table minimum
width, rerun the Task 2 tests, and recapture `planning.png`.

- [ ] **Step 10: Stop the temporary server**

Return to the uvicorn shell and press `Ctrl-C`.

Expected: port `8768` is no longer serving. Leave the ignored temporary DB only
as local evidence; do not copy it into tracked files.

- [ ] **Step 11: Update the temporary cleanup tracker with observed evidence**

In `v2-files/archive/TASK-02-STRUCTURE-CLEANUP.md`:

- mark Task 2 complete;
- set Task 3, terminal semantics/layout, as the exact next action;
- record the actual focused and baseline pass counts;
- record the four screenshot paths;
- state that live checks used a temporary SQLite database;
- state that no new migration was introduced; and
- leave Tasks 3-8 otherwise unchanged.

Do not update `v2-files/AGENTS.md` unless the user explicitly invokes
`maintain the database migration system`.

- [ ] **Step 12: Final review checkpoint**

Run:

```bash
git status --short
git diff --check
git diff --stat
```

Confirm:

- runtime DB `data/extrusion_terminal.sqlite3` was not changed by Task 2;
- screenshots and `.test-runtime` remain untracked/ignored;
- no files are staged;
- no commit was created;
- the plan's complete scope is present and nothing from Tasks 3-5 was pulled in.

The historical completion gate required keeping `TASK-02-ADMIN-DESIGN.md` and
`TASK-02-ADMIN-PLAN.md` until the user approved the admin slice. That approval
was received, and both files are now retained in the Task 02 archive.

---

### Task 6: Remove Redundant Table Units And Verify Fully Populated Order 26000

**Files:**

- Modify: `tests/test_admin_routes.py`
- Modify: `tests/test_admin_card_detail_redesign.py`
- Modify: `app/templates/admin_planning.html`
- Modify: `app/templates/admin_cards.html`
- Create ignored local evidence: `source-files/extrusion_order_26000_full.csv`
- Create ignored UI evidence: `artifacts/ui-checks/v2/admin/order-26000-*.png`

**Interfaces:**

- Planning and cards-list headers retain `Поръчано бруто, кг`; populated table
  cells render the stored number with no repeated `кг` suffix.
- The active machine-queue line remains `Поръчано бруто: <value> кг`.
- Order `26000` uses the exact `IMPORT_FIELDS` order and all values are nonblank.

- [ ] **Step 1: Write the failing table-format assertions**

Change the planning expectation to:

```python
assert '<td class="col-gross">725.50</td>' in html
assert '<td class="col-gross">725.50 кг</td>' not in html
```

Change the technology-cards list expectation to:

```python
assert "875.50" in html
assert "875.50 кг" not in html
```

Keep the existing blank-cell and active-queue unit assertions.

- [ ] **Step 2: Run the two tests and verify red**

```bash
.venv/bin/python -m pytest \
  tests/test_admin_routes.py::test_admin_planning_renders_compact_unreleased_release_table \
  tests/test_admin_card_detail_redesign.py::test_admin_cards_list_shows_delivery_and_ordered_gross -q
```

Expected: both fail because populated table cells still append `кг`.

- [ ] **Step 3: Remove only the redundant table suffixes**

In `admin_planning.html`, render the populated draft cell as
`{{ card.ordered_gross_kg }}`. In `admin_cards.html`, render the populated list
cell the same way. Preserve `-` for blanks and preserve the active queue line.

- [ ] **Step 4: Run focused and complete admin checks**

Run the Step 2 command, then:

```bash
.venv/bin/python -m pytest \
  tests/test_admin_routes.py \
  tests/test_admin_planning.py \
  tests/test_admin_card_review.py \
  tests/test_admin_card_detail_redesign.py -q
.venv/bin/python -m pytest tests/test_baseline.py -q
```

- [ ] **Step 5: Create the exact fully populated test export**

Create `source-files/extrusion_order_26000_full.csv` with this exact header and
single row:

```csv
order_number,order_date,delivery_date,customer,city,product_type,ordered_gross_kg,ordered_rolls,ordered_meters,ordered_units,product_form,material,size_thickness,notes,printing_sequence,extrusion_sequence,rewinding_slitting_sequence,confection_sequence,extrusion_next_operation,extrusion_folding,extrusion_treatment,raw_material_a,raw_material_b,raw_material_c,linear_pe,antistatic,masterbatch,chalk,packaging_method
26000,25/07/2026,31/07/2026,ТЕСТ 26000 - Каменица,Хасково - ТЕСТ 26000,ТСФ 600/0.060 ++ / ТЕСТ 26000 /,2600.01,26,26000,260000,плоско,LDPE,600/0.060,ТЕСТ 26000 - всички 29 експортни полета са попълнени,2,1,3,4,Printing,ТЕСТ 26000 - Фалдиране,ТЕСТ 26000 - Двустранно,LDPE; Rompetrol B20/03 | 25%,LDPE; ExxonMobil LD 3529 | 20%,HDPE; HIP Petrohemija TR-130 | 15%,LLDPE; ExxonMobil C4LL1018 BT | 15%,Antistatic; LyondellBasell VLA 66 NAT | 5%,Masterbatch; LyondellBasell AG L 4535 BLUE | 10%,Filler; Noviz FM80-41 | 10%,ТЕСТ 26000 - 1 голям палет
```

- [ ] **Step 6: Validate and import into the served temporary database**

Before import, assert the CSV header equals `IMPORT_FIELDS`, it has exactly one
row, all 29 values are nonblank, route values are `2,1,3,4`, and recipe
percentages total 100. Import without overwrite into
`.test-runtime/v2-admin.IInXK2/extrusion_terminal.sqlite3` and assert one row
seen/imported/created with zero skipped.

- [ ] **Step 7: Prove all 29 persisted values**

Read the imported card from the same temporary database and compare every
field in `IMPORT_FIELDS` to the CSV dictionary. Record a field-by-field manifest
under `artifacts/ui-checks/v2/admin/order-26000-field-check.md`.

- [ ] **Step 8: Verify the four admin surfaces live**

Against the existing LAN server on port 8768, verify:

- import result links order `26000` to its card;
- planning shows order `26000` and gross value `2600.01` without repeated unit;
- cards list shows order `26000`, delivery date, and `2600.01` without repeated unit;
- card detail exposes all 29 imported values in their appropriate order,
  quantity, route, extrusion, recipe, and packaging regions.

Capture and inspect:

- `order-26000-import.png`
- `order-26000-planning.png`
- `order-26000-cards.png`
- `order-26000-detail.png`

- [ ] **Step 9: Final checkpoint**

Run `git diff --check`, confirm the runtime database remains unchanged, confirm
no migration/staging/commit, and append the observed evidence to the Task 5
report and SDD ledger before task review.
