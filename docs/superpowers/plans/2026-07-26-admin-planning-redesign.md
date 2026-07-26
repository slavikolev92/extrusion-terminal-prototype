# Admin Planning Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/admin/planning` with the approved dense table design, modal-based planning controls, hidden rare actions, safe pre-production deletion, and sortable unsent-card headers.

**Architecture:** Keep the existing server-rendered FastAPI/Jinja flow and SQLite rule enforcement. Reuse the current release, replanning, unrelease, stale-version, and queue-normalization behavior; change the page markup/CSS and add the smallest backend rule expansion needed for deleting pending cards that have not started production.

**Tech Stack:** FastAPI, Jinja2 templates, direct `sqlite3`, SQLite, pytest, repo-local Playwright, CSS in `app/static/css/app.css`, no new frontend package.

## Global Constraints

- README.md is the authoritative project specification.
- Do not stage or commit unless the user explicitly asks.
- Use the repo-local Python virtualenv `.venv`.
- Tests must use temporary SQLite database paths and must not mutate `data/extrusion_terminal.sqlite3`.
- For UI changes, verify against the live FastAPI app with repo-local Playwright before claiming completion.
- Save screenshots/videos/traces under `artifacts/ui-checks/`.
- Keep `/admin/planning` machine queues ordered by `machine_sequence`; sortable headers apply only to the unsent/imported card table.
- Do not add drag-and-drop, search controls, helper text, card-count pills, inline machine/order controls, visible return buttons, or visible delete buttons.
- Do not show material or maximum roll weight on the redesigned planning page.
- Keep important invariants enforced in backend code, not only in the UI.

---

## File Structure

- Modify `app/db.py`
  - Expand admin delete behavior to allow imported cards and pending cards that have not started production.
  - Keep stale-version checks and production-data guards.
  - Normalize the old machine queue after deleting a pending card.
- Modify `app/main.py`
  - Extend unsent-card sort keys to include `size_thickness` and `ordered_gross_kg`.
  - Add display helpers for planning rows, including `DD.MM.YYYY` delivery-date formatting.
  - Route planning-page delete success back to `/admin/planning` when requested by the form.
- Modify `app/templates/admin_planning.html`
  - Replace the old compact release table and machine cards with the approved stacked full-width tables.
  - Add a single shared `Планирай карта` dialog for imported and assigned cards.
  - Move `Върни в неизпратени` and `Изтрий карта` into per-row overflow menus.
- Modify `app/static/css/app.css`
  - Replace old planning-card styles with dense planning table, quiet row action button, overflow menu, and dialog styles.
  - Preserve unrelated terminal `.queue-card` styling because terminal uses that class.
- Modify `tests/test_admin_planning.py`
  - Add backend deletion tests for pending/unstarted cards and production-data blocks.
- Modify `tests/test_admin_routes.py`
  - Update planning-page route/render tests to assert the accepted table structure, modal controls, menu actions, and sortable unsent headers.
- Modify `tests/test_admin_card_review.py`
  - Update existing delete expectations so the broadened backend delete rule is intentional and covered.
- Modify `README.md`
  - Replace the obsolete “four machine columns” description with the accepted stacked-table behavior and delete guard.
- Create/update `artifacts/ui-checks/admin-planning-redesign/`
  - Store Playwright evidence from the live app with a temporary database.

---

### Task 1: Backend Delete Rule

**Files:**
- Modify: `app/db.py`
- Test: `tests/test_admin_planning.py`
- Test: `tests/test_admin_card_review.py`

**Interfaces:**
- Consumes: `validate_loaded_card_version(card, loaded_version)`, `normalize_machine_queue(connection, machine_id=...)`, `STATUS_IMPORTED`, `STATUS_PENDING`, `STATUS_RUNNING`, `STATUS_PAUSED`
- Produces: `delete_admin_planning_card(card_id: int, loaded_version: int) -> RuleResult`
- Preserves: `delete_admin_imported_card(card_id: int, loaded_version: int) -> RuleResult` as a compatibility wrapper for existing imports/tests until callers are moved.

- [ ] **Step 1: Add backend tests for deleting a pending card that has not started**

Add this test to `tests/test_admin_planning.py` after the unrelease tests:

```python
def test_delete_pending_unstarted_card_removes_it_and_normalizes_queue(connection):
    first_id = release_ready_card("25830", machine_id=1, machine_sequence=1)
    deleted_id = release_ready_card("25831", machine_id=1, machine_sequence=2)
    third_id = release_ready_card("25832", machine_id=1, machine_sequence=3)

    result = db.delete_admin_planning_card(deleted_id, card_version(deleted_id))
    machine_1_cards = [
        (card["order_number"], card["machine_sequence"])
        for queue in db.fetch_machine_queues()
        if queue["machine"]["id"] == 1
        for card in queue["cards"]
    ]

    assert result.ok
    assert result.messages == ("Поръчка 25831 е изтрита.",)
    assert db.fetch_admin_card_detail(deleted_id) is None
    assert db.fetch_admin_card_detail(first_id)["machine_sequence"] == 1
    assert db.fetch_admin_card_detail(third_id)["machine_sequence"] == 2
    assert machine_1_cards == [("25830", 1), ("25832", 2)]
```

- [ ] **Step 2: Add backend tests for blocking started or active production cards**

Add this test to `tests/test_admin_planning.py`:

```python
def test_delete_blocks_started_running_and_paused_cards(connection, active_test_shift):
    started_pending_id = release_ready_card("25833", machine_id=2, machine_sequence=1)
    running_id = release_ready_card("25834", machine_id=2, machine_sequence=2)
    paused_id = release_ready_card("25835", machine_id=2, machine_sequence=3)

    connection.execute(
        "UPDATE cards SET first_started_at = CURRENT_TIMESTAMP WHERE id = ?",
        (started_pending_id,),
    )
    connection.commit()
    assert db.start_production_timing(running_id, card_version(running_id)).ok
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok

    started_result = db.delete_admin_planning_card(started_pending_id, card_version(started_pending_id))
    running_result = db.delete_admin_planning_card(running_id, card_version(running_id))
    paused_result = db.delete_admin_planning_card(paused_id, card_version(paused_id))

    assert not started_result.ok
    assert started_result.messages == ("Технологични карти с производствени данни не могат да се изтриват.",)
    assert not running_result.ok
    assert running_result.messages == ("Картата може да се изтрие само преди започване на производство.",)
    assert not paused_result.ok
    assert paused_result.messages == ("Картата може да се изтрие само преди започване на производство.",)
    assert db.fetch_admin_card_detail(started_pending_id) is not None
    assert db.fetch_admin_card_detail(running_id) is not None
    assert db.fetch_admin_card_detail(paused_id) is not None
```

- [ ] **Step 3: Update the existing released-card delete test**

In `tests/test_admin_card_review.py`, change `test_admin_delete_blocks_released_card` into a test that proves a released-but-unstarted pending card is now deletable:

```python
def test_admin_delete_removes_pending_unstarted_card(connection):
    card_id = import_ready_card("25712")
    assert db.release_card(
        card_id,
        machine_id=4,
        machine_sequence=9,
    ).ok
    card = db.fetch_admin_card_detail(card_id)

    result = db.delete_admin_planning_card(card_id, card["version"])
    deleted = db.fetch_admin_card_detail(card_id)

    assert result.ok
    assert deleted is None
```

Also update `test_admin_delete_removes_unreleased_card` to call `db.delete_admin_planning_card(...)`.

- [ ] **Step 4: Run the focused delete tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_planning.py -k "delete_pending_unstarted or delete_blocks_started_running_and_paused" -q
python -m pytest tests/test_admin_card_review.py -k "admin_delete" -q
```

Expected: failures because `delete_admin_planning_card` does not exist yet and the old delete helper blocks pending cards.

- [ ] **Step 5: Implement `delete_admin_planning_card`**

In `app/db.py`, replace the current `delete_admin_imported_card` implementation with a new function plus wrapper:

```python
def delete_admin_planning_card(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = connection.execute(
            """
            SELECT id, order_number, status, version, machine_id, first_started_at
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        if card["status"] not in (STATUS_IMPORTED, STATUS_PENDING):
            return RuleResult(False, ("Картата може да се изтрие само преди започване на производство.",))

        roll_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM roll_entries WHERE card_id = ?",
                (card_id,),
            ).fetchone()[0]
        )
        segment_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM production_time_segments WHERE card_id = ?",
                (card_id,),
            ).fetchone()[0]
        )
        if roll_count or segment_count or card["first_started_at"]:
            return RuleResult(False, ("Технологични карти с производствени данни не могат да се изтриват.",))

        old_machine_id = int(card["machine_id"]) if card["machine_id"] is not None else None
        connection.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        if old_machine_id is not None:
            normalize_machine_queue(connection, machine_id=old_machine_id)

    return RuleResult(True, (f"Поръчка {card['order_number']} е изтрита.",))


def delete_admin_imported_card(card_id: int, loaded_version: int) -> RuleResult:
    return delete_admin_planning_card(card_id, loaded_version)
```

- [ ] **Step 6: Run the focused delete tests and verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_planning.py -k "delete_pending_unstarted or delete_blocks_started_running_and_paused" -q
python -m pytest tests/test_admin_card_review.py -k "admin_delete" -q
```

Expected: all selected tests pass.

---

### Task 2: Planning Context And Unsent Sorting

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: `fetch_cards_by_status((STATUS_IMPORTED,))`, `fetch_machine_queues()`
- Produces: `format_planning_delivery_date(value: Any) -> str`, `prepare_planning_card_rows(cards: list[dict[str, Any]]) -> list[dict[str, Any]]`
- Extends: `DRAFT_SORT_LABELS` with `size_thickness` and `ordered_gross_kg`

- [ ] **Step 1: Update the sort/render tests for the accepted columns**

In `tests/test_admin_routes.py`, update `test_admin_planning_renders_compact_unreleased_release_table` so it asserts these strings instead of the old inline release controls:

```python
assert '<main class="page wide-page admin-page">' in html
assert '<table class="planning-table">' in html
assert ">Ред" in html
assert ">Поръчка" in html
assert ">Доставка" in html
assert ">Клиент" in html
assert ">Изделие" in html
assert ">Размер" in html
assert ">Бруто кг" in html
assert ">Действие" in html
assert "25.06.2026" in html
assert "26.06.2026" in html
assert '<td class="col-sequence">-</td>' in html
assert 'class="planning-open-button"' in html
assert 'data-planning-action="/admin/cards/' in html
assert 'class="planning-overflow"' in html
assert "Изтрий карта" in html
assert 'class="release-control release-control-sequence"' not in html
assert 'class="release-control release-control-machine"' not in html
assert 'class="release-submit-button"' not in html
assert '<span>Макс. тегло ролка, кг</span>' not in html
```

- [ ] **Step 2: Add route tests for size and gross sort links**

Extend `test_admin_planning_sorts_unreleased_cards_with_header_links` or add a nearby test:

```python
def test_admin_planning_sorts_unreleased_cards_by_size_and_gross(connection):
    result = import_cards_from_csv(
        "planning-sort-size-gross-route.csv",
        csv_bytes(
            extrusion_row("25951", size_thickness="900/0.050", ordered_gross_kg="700"),
            extrusion_row("25950", size_thickness="600/0.040", ordered_gross_kg="1200"),
            extrusion_row("25952", size_thickness="700/0.030", ordered_gross_kg=""),
        ),
        overwrite_existing=False,
    )
    assert result.rows_imported == 3

    size_response = asyncio.run(
        admin_planning(
            make_request("/admin/planning", method="GET"),
            draft_sort="size_thickness",
            draft_dir="asc",
        )
    )
    gross_response = asyncio.run(
        admin_planning(
            make_request("/admin/planning", method="GET"),
            draft_sort="ordered_gross_kg",
            draft_dir="desc",
        )
    )

    assert size_response.status_code == 200
    assert_html_order(size_response.body.decode("utf-8"), "25950", "25952", "25951")
    assert gross_response.status_code == 200
    assert_html_order(gross_response.body.decode("utf-8"), "25950", "25951", "25952")
```

- [ ] **Step 3: Add a route test proving machine queues keep sequence order while the unsent queue is sorted**

Add this test to `tests/test_admin_routes.py`:

```python
def test_admin_planning_sort_does_not_reorder_machine_queues(connection):
    first_id = import_route_card("25961", customer="Zulu Machine")
    second_id = import_route_card("25962", customer="Alpha Machine")
    assert db.release_card(first_id, 1, 1, card_version(first_id)).ok
    assert db.release_card(second_id, 1, 2, card_version(second_id)).ok

    response = asyncio.run(
        admin_planning(
            make_request("/admin/planning", method="GET"),
            draft_sort="customer",
            draft_dir="desc",
        )
    )
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert_html_order(html, "25961", "25962")
```

- [ ] **Step 4: Run the focused planning render tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -k "planning_renders_compact or sorts_unreleased_cards or sort_does_not_reorder_machine_queues" -q
```

Expected: failures because the current context lacks the new sort keys and the template still uses old markup/date display.

- [ ] **Step 5: Extend sort keys and display helpers**

In `app/main.py`, update `DRAFT_SORT_LABELS`:

```python
DRAFT_SORT_LABELS = {
    "order_number": "Поръчка",
    "delivery_date": "Доставка",
    "customer": "Клиент",
    "product_type": "Изделие",
    "size_thickness": "Размер",
    "ordered_gross_kg": "Бруто кг",
}
```

Add helpers near the existing draft sort helpers:

```python
def draft_decimal_sort_value(value: Any) -> tuple[int, Decimal]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return (1, Decimal("0"))
    try:
        return (0, Decimal(raw_value.replace(",", ".")))
    except InvalidOperation:
        return (1, Decimal("0"))


def format_planning_delivery_date(value: Any) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return "-"
    for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw_value, date_format).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return raw_value


def prepare_planning_card_rows(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for card in cards:
        row = dict(card)
        row["planning_delivery_date"] = format_planning_delivery_date(card.get("delivery_date"))
        row["planning_gross_kg"] = str(card.get("ordered_gross_kg") or "").strip() or "-"
        row["planning_size"] = str(card.get("size_thickness") or "").strip() or "-"
        rows.append(row)
    return rows
```

Update `draft_sort_value`:

```python
def draft_sort_value(card: dict[str, Any], sort_key: str) -> tuple[int, Any]:
    if sort_key == "delivery_date":
        return draft_date_sort_value(card.get("delivery_date"))
    if sort_key == "ordered_gross_kg":
        return draft_decimal_sort_value(card.get("ordered_gross_kg"))
    return (0, str(card.get(sort_key) or "").casefold())
```

Update `sorted_draft_cards` so missing gross values stay last on descending sorts, matching the existing missing-date behavior. Use the same split pattern as delivery dates:

```python
    if sort_key == "ordered_gross_kg" and reverse:
        numeric_cards = []
        missing_gross_cards = []
        for card in ordered_cards:
            missing_gross, _ = draft_decimal_sort_value(card.get("ordered_gross_kg"))
            if missing_gross:
                missing_gross_cards.append(card)
            else:
                numeric_cards.append(card)
        return sorted(
            numeric_cards,
            key=lambda card: draft_decimal_sort_value(card.get("ordered_gross_kg")),
            reverse=True,
        ) + missing_gross_cards
```

- [ ] **Step 6: Prepare display rows in `admin_planning_context`**

Change the beginning of `admin_planning_context` to prepare both draft and machine card rows:

```python
    raw_machine_queues = fetch_machine_queues()
    machine_queues = [
        {
            **queue,
            "cards": prepare_planning_card_rows(queue["cards"]),
        }
        for queue in raw_machine_queues
    ]
    normalized_sort, normalized_dir = normalize_draft_sort(draft_sort, draft_dir)
    draft_cards = prepare_planning_card_rows(
        sorted_draft_cards(
            fetch_cards_by_status((STATUS_IMPORTED,)),
            normalized_sort,
            normalized_dir,
        )
    )
```

Keep the existing context keys so the rest of the app is unaffected.

- [ ] **Step 7: Run the focused sorting tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -k "sorts_unreleased_cards or sort_does_not_reorder_machine_queues" -q
```

Expected: sorting tests pass after the helper changes. The full render test may still fail until the template is replaced in Task 3.

---

### Task 3: Planning Template Redesign

**Files:**
- Modify: `app/templates/admin_planning.html`
- Modify: `app/main.py`
- Test: `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: `draft_cards`, `draft_sort_links`, `machine_queues`, `machines`, `status_labels`, `planning_delivery_date`, `planning_gross_kg`, `planning_size`
- Produces: shared table markup, `planning-modal`, `planning-open-button`, overflow forms for delete and unrelease

- [ ] **Step 1: Update route tests for machine table/menu/modal markup**

Add this test to `tests/test_admin_routes.py`:

```python
def test_admin_planning_renders_machine_queues_as_shared_tables_with_menus(connection):
    pending_id = import_route_card(
        "25971",
        delivery_date="2026-07-30",
        customer="Machine Customer",
        product_type="Machine Product",
        size_thickness="800/0.045",
        ordered_gross_kg="650",
    )
    assert db.release_card(pending_id, 1, 1, card_version(pending_id)).ok

    response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert "Машина 1" in html
    assert "30.07.2026" in html
    assert "800/0.045" in html
    assert "650" in html
    assert 'action="/admin/cards/' in html
    assert 'name="return_to" value="planning"' in html
    assert "Върни в неизпратени" in html
    assert "Изтрий карта" in html
    assert 'id="planning-modal"' in html
    assert ">Планирай карта<" in html
    assert 'id="planning-modal-form"' in html
    assert 'class="queue-card' not in html
    assert 'class="planning-form"' not in html
    assert 'class="queue-return-button"' not in html
```

- [ ] **Step 2: Update planning delete route test expectations**

Add this test to `tests/test_admin_routes.py`:

```python
def test_admin_delete_redirects_back_to_planning_when_requested(connection):
    card_id = import_route_card("25972")

    response = asyncio.run(
        admin_route_endpoint("/admin/cards/{card_id}/delete")(
            make_request(f"/admin/cards/{card_id}/delete"),
            card_id=card_id,
            loaded_version=str(card_version(card_id)),
            return_to="planning",
        )
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/planning"
    assert db.fetch_admin_card_detail(card_id) is None
```

- [ ] **Step 3: Run focused route tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -k "machine_queues_as_shared_tables or delete_redirects_back_to_planning" -q
```

Expected: failures because the template is still old and the delete route does not accept `return_to`.

- [ ] **Step 4: Update the delete route for planning-page redirects**

In `app/main.py`, import `delete_admin_planning_card` from `app.db`.

Change the delete route signature:

```python
async def delete_admin_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    return_to: str = Form("detail"),
):
```

Call `delete_admin_planning_card(card_id, parsed_version)`.

After a successful delete:

```python
    if delete_result.ok:
        if return_to == "planning":
            return RedirectResponse(url="/admin/planning", status_code=303)
        return RedirectResponse(url="/admin/cards", status_code=303)
```

For failed planning deletes, render `admin_planning.html` with `planning_result=delete_result`; for detail deletes, keep the existing detail response:

```python
    if return_to == "planning":
        return templates.TemplateResponse(
            request,
            "admin_planning.html",
            admin_planning_context(planning_result=delete_result),
        )
```

- [ ] **Step 5: Replace `admin_planning.html` with the shared table layout**

Rewrite the body of `app/templates/admin_planning.html` so the top-level main tag is:

```jinja2
<main class="page wide-page admin-page">
```

Use a helper macro for sortable unsent headers:

```jinja2
{% macro sortable_header(key, class_name) -%}
  <th class="{{ class_name }}" aria-sort="{{ draft_sort_links[key].aria_sort }}">
    <a class="sort-link {% if draft_sort == key %}active{% endif %}" href="{{ draft_sort_links[key].href }}">{{ draft_sort_links[key].label }}{% if draft_sort == key %}<span aria-hidden="true">{% if draft_dir == "asc" %}↑{% else %}↓{% endif %}</span>{% endif %}</a>
  </th>
{%- endmacro %}
```

Use the same column order everywhere:

```jinja2
<th class="col-sequence">Ред</th>
<th class="col-order">Поръчка</th>
<th class="col-delivery">Доставка</th>
<th class="col-customer">Клиент</th>
<th class="col-product">Изделие</th>
<th class="col-size">Размер</th>
<th class="col-gross">Бруто кг</th>
<th class="col-action">Действие</th>
<th class="col-menu"><span class="visually-hidden">Още</span></th>
```

For unsent rows, render:

```jinja2
<tr id="draft-card-{{ card.id }}">
  <td class="col-sequence">-</td>
  <td class="col-order"><a href="/admin/cards/{{ card.id }}">№ {{ card.order_number }}</a></td>
  <td class="col-delivery">{{ card.planning_delivery_date }}</td>
  <td class="col-customer truncate-cell" title="{{ card.customer or '' }}">{{ card.customer or "-" }}</td>
  <td class="col-product truncate-cell" title="{{ card.product_type or '' }}">{{ card.product_type or "-" }}</td>
  <td class="col-size truncate-cell" title="{{ card.planning_size }}">{{ card.planning_size }}</td>
  <td class="col-gross">{{ card.planning_gross_kg }}</td>
  <td class="col-action">
    <button class="planning-open-button" type="button"
            data-planning-action="/admin/cards/{{ card.id }}/release"
            data-loaded-version="{{ card.version }}"
            data-order-number="{{ card.order_number }}"
            data-customer="{{ card.customer or '-' }}"
            data-machine-id="{{ card.machine_id or '' }}"
            data-machine-sequence="{{ card.machine_sequence or '' }}">
      Планирай
    </button>
  </td>
  <td class="col-menu">
    <details class="planning-overflow">
      <summary aria-label="Още действия за поръчка {{ card.order_number }}">⋮</summary>
      <div class="planning-overflow-menu">
        <form action="/admin/cards/{{ card.id }}/delete" method="post" onsubmit="return confirm('Изтриване на поръчка {{ card.order_number }}?');">
          <input type="hidden" name="loaded_version" value="{{ card.version }}">
          <input type="hidden" name="return_to" value="planning">
          <button type="submit">Изтрий карта</button>
        </form>
      </div>
    </details>
  </td>
</tr>
```

For machine rows, use the same cells, with `{{ card.machine_sequence or "-" }}` in the `Ред` cell, `/admin/cards/{{ card.id }}/planning` as the planning action, and two overflow forms:

```jinja2
{% if card.status == "pending" %}
  <form action="/admin/cards/{{ card.id }}/unrelease" method="post">
    <input type="hidden" name="loaded_version" value="{{ card.version }}">
    <input type="hidden" name="return_to" value="planning">
    <button type="submit">Върни в неизпратени</button>
  </form>
{% endif %}
<form action="/admin/cards/{{ card.id }}/delete" method="post" onsubmit="return confirm('Изтриване на поръчка {{ card.order_number }}?');">
  <input type="hidden" name="loaded_version" value="{{ card.version }}">
  <input type="hidden" name="return_to" value="planning">
  <button type="submit">Изтрий карта</button>
</form>
```

Do not render status pills in the table. The backend will reject invalid delete/unrelease actions.

- [ ] **Step 6: Add the shared planning dialog markup and safe JavaScript**

At the bottom of `admin_planning.html`, before `</main>`, add:

```jinja2
<dialog class="planning-modal" id="planning-modal">
  <form id="planning-modal-form" method="post">
    <div class="planning-modal-head">
      <h2>Планирай карта</h2>
      <button class="planning-modal-close" type="button" aria-label="Затвори">×</button>
    </div>
    <dl class="planning-modal-context">
      <div><dt>Поръчка</dt><dd id="planning-modal-order">-</dd></div>
      <div><dt>Клиент</dt><dd id="planning-modal-customer">-</dd></div>
    </dl>
    <input id="planning-modal-version" type="hidden" name="loaded_version" value="">
    <div class="planning-modal-fields">
      <label>
        <span>Машина</span>
        <select id="planning-modal-machine" name="machine_id" required>
          {% for machine in machines %}
            <option value="{{ machine.id }}">{{ machine.id }}</option>
          {% endfor %}
        </select>
      </label>
      <label>
        <span>Ред</span>
        <input id="planning-modal-sequence" name="machine_sequence" inputmode="numeric" pattern="[0-9]*" required>
      </label>
    </div>
    <div class="planning-modal-actions">
      <button class="secondary-button" type="button" data-planning-cancel>Отказ</button>
      <button class="primary-button" type="submit">Запази</button>
    </div>
  </form>
</dialog>
```

Add a short script that uses `textContent`, `value`, and `setAttribute`; do not use `innerHTML`:

```html
<script>
  (() => {
    const modal = document.getElementById("planning-modal");
    const form = document.getElementById("planning-modal-form");
    const order = document.getElementById("planning-modal-order");
    const customer = document.getElementById("planning-modal-customer");
    const version = document.getElementById("planning-modal-version");
    const machine = document.getElementById("planning-modal-machine");
    const sequence = document.getElementById("planning-modal-sequence");
    if (!modal || !form || !order || !customer || !version || !machine || !sequence) return;

    document.querySelectorAll(".planning-open-button").forEach((button) => {
      button.addEventListener("click", () => {
        form.setAttribute("action", button.dataset.planningAction || "");
        version.value = button.dataset.loadedVersion || "";
        order.textContent = button.dataset.orderNumber || "-";
        customer.textContent = button.dataset.customer || "-";
        machine.value = button.dataset.machineId || "";
        sequence.value = button.dataset.machineSequence || "";
        modal.showModal();
      });
    });

    document.querySelectorAll(".planning-modal-close, [data-planning-cancel]").forEach((button) => {
      button.addEventListener("click", () => modal.close());
    });
  })();
</script>
```

- [ ] **Step 7: Run focused route tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -k "planning_renders_compact or machine_queues_as_shared_tables or delete_redirects_back_to_planning or sorts_unreleased_cards or sort_does_not_reorder_machine_queues" -q
```

Expected: selected route tests pass.

---

### Task 4: Planning CSS

**Files:**
- Modify: `app/static/css/app.css`
- Test: `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: classes from Task 3 markup
- Produces: accepted visual treatment for stacked tables, quiet `Планирай` buttons, overflow menus, and dialog

- [ ] **Step 1: Replace old planning CSS assertions**

In `tests/test_admin_routes.py`, replace CSS assertions for `.unreleased-table` widths with assertions for the new planning classes:

```python
css = Path("app/static/css/app.css").read_text(encoding="utf-8")
assert ".planning-table {" in css
assert ".planning-table .col-size {" in css
assert ".planning-open-button {" in css
assert ".planning-overflow-menu {" in css
assert ".planning-modal {" in css
assert 'class="machine-grid"' not in html
```

- [ ] **Step 2: Run the updated render test and verify it fails on CSS**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_planning_renders_compact_unreleased_release_table -q
```

Expected: failure until CSS is updated.

- [ ] **Step 3: Add planning table styles without touching terminal queue-card styles**

In `app/static/css/app.css`, remove or stop relying on planning-only rules for `.unreleased-table`, `.release-control`, `.release-submit-button`, `.planning-form`, `.machine-grid`, `.machine-column`, `.queue-card-header`, `.queue-return-form`, and `.queue-return-button` where they are only used by `admin_planning.html`.

Add:

```css
.planning-section {
  overflow: visible;
}

.planning-section-head {
  align-items: center;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  padding: 14px 16px;
}

.planning-section-head h2 {
  font-size: 18px;
  margin: 0;
}

.planning-table {
  table-layout: fixed;
  width: 100%;
}

.planning-table th {
  background: var(--surface-soft);
  border-top: 0;
  border-bottom: 2px solid var(--line-strong);
  color: var(--muted);
  font-size: 11px;
  font-weight: 850;
  line-height: 1.2;
  text-transform: uppercase;
  white-space: nowrap;
}

.planning-table td {
  vertical-align: middle;
}

.planning-table .col-sequence {
  width: 56px;
  text-align: center;
}

.planning-table .col-order {
  width: 105px;
}

.planning-table .col-delivery {
  width: 116px;
}

.planning-table .col-customer {
  width: 19%;
}

.planning-table .col-product {
  width: 20%;
}

.planning-table .col-size {
  width: 135px;
}

.planning-table .col-gross {
  width: 96px;
  text-align: right;
}

.planning-table .col-action {
  width: 106px;
  text-align: right;
}

.planning-table .col-menu {
  width: 48px;
  text-align: right;
}

.planning-table .truncate-cell {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.planning-open-button,
.planning-overflow summary {
  min-height: 34px;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  background: var(--surface);
  color: var(--text);
  font: inherit;
}

.planning-open-button {
  padding: 0 12px;
  white-space: nowrap;
}

.planning-overflow {
  position: relative;
}

.planning-overflow summary {
  align-items: center;
  cursor: pointer;
  display: inline-flex;
  justify-content: center;
  list-style: none;
  width: 34px;
}

.planning-overflow summary::-webkit-details-marker {
  display: none;
}

.planning-overflow-menu {
  background: var(--surface);
  border: 1px solid var(--line-strong);
  border-radius: 7px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.16);
  display: grid;
  min-width: 190px;
  padding: 6px;
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  z-index: 20;
}

.planning-overflow-menu form {
  margin: 0;
}

.planning-overflow-menu button {
  background: transparent;
  border: 0;
  border-radius: 5px;
  color: var(--text);
  font: inherit;
  min-height: 34px;
  padding: 0 10px;
  text-align: left;
  white-space: nowrap;
  width: 100%;
}

.planning-overflow-menu button:hover,
.planning-overflow-menu button:focus {
  background: var(--surface-soft);
}
```

Add dialog styles:

```css
.planning-modal {
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.25);
  max-width: 440px;
  padding: 0;
  width: min(440px, calc(100vw - 32px));
}

.planning-modal::backdrop {
  background: rgba(15, 23, 42, 0.38);
}

.planning-modal form {
  display: grid;
  gap: 14px;
  margin: 0;
  padding: 16px;
}

.planning-modal-head {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

.planning-modal-head h2 {
  font-size: 18px;
  margin: 0;
}

.planning-modal-close {
  min-height: 32px;
  width: 32px;
}

.planning-modal-context {
  display: grid;
  gap: 8px;
  margin: 0;
}

.planning-modal-context div {
  display: grid;
  gap: 2px;
}

.planning-modal-context dt,
.planning-modal-fields span {
  color: var(--muted);
  font-size: 11px;
  font-weight: 850;
  text-transform: uppercase;
}

.planning-modal-context dd {
  margin: 0;
}

.planning-modal-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.planning-modal-fields label {
  display: grid;
  gap: 4px;
}

.planning-modal-fields input,
.planning-modal-fields select {
  width: 100%;
}

.planning-modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
```

- [ ] **Step 4: Add a responsive fallback without adding desktop inner scrollbars**

Add:

```css
@media (max-width: 900px) {
  .planning-section {
    overflow-x: auto;
  }

  .planning-table {
    min-width: 920px;
  }
}
```

Desktop should show the full table without inner scrollbars. Narrow/mobile viewports may horizontally scroll the table because the approved dense table has fixed operational columns.

- [ ] **Step 5: Run route tests that inspect markup and CSS**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -k "planning_renders_compact or machine_queues_as_shared_tables" -q
```

Expected: selected tests pass.

---

### Task 5: Documentation And Verification

**Files:**
- Modify: `README.md`
- Test: focused pytest commands
- Verify: Playwright screenshot under `artifacts/ui-checks/admin-planning-redesign/`

**Interfaces:**
- Consumes: completed Tasks 1-4
- Produces: updated project documentation and browser evidence

- [ ] **Step 1: Update README planning description**

In `README.md`, replace:

```markdown
- The admin page should provide a simple machine planning view split into four machine columns.
- Each machine column should show active queued cards for that machine sorted by numeric queue position.
```

with:

```markdown
- The admin planning page should show one stacked table for unreleased technology cards and one stacked table per machine.
- Machine tables must show active queued cards sorted by numeric queue position; sortable headers are limited to the unreleased-card table so machine execution order remains visible.
- Planning and replanning use a shared modal for machine and sequence. Rare actions such as returning a pending card to unreleased planning and deleting an unstarted card live in each row's overflow menu.
```

Near the delete/admin correction rules, add:

```markdown
- Admin deletion is allowed only before production starts: imported cards and pending cards with no timing segments, no roll entries, and no first-start timestamp may be deleted. Running, paused, completed, cancelled, or production-data-bearing cards cannot be deleted.
```

- [ ] **Step 2: Run the focused automated tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_planning.py tests/test_admin_routes.py tests/test_admin_card_review.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run syntax/import and diff hygiene checks**

Run:

```bash
source .venv/bin/activate
python -m compileall app tests
git diff --check
```

Expected: compileall passes and `git diff --check` reports no whitespace errors.

- [ ] **Step 4: Run a Playwright visual check against a temporary database**

Start the app on an unused local port with a temporary database. Use the repo-local `.venv`; do not use the real runtime database:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/admin-planning-redesign.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

In another shell, seed enough planning data and capture screenshots. Use an app route or direct test helper only against `.test-runtime/admin-planning-redesign.sqlite3`. Save evidence under:

```text
artifacts/ui-checks/admin-planning-redesign/
```

Use repo-local Playwright:

```bash
./node_modules/.bin/playwright --version
```

Capture at least:

```text
artifacts/ui-checks/admin-planning-redesign/planning-desktop.png
artifacts/ui-checks/admin-planning-redesign/planning-modal.png
artifacts/ui-checks/admin-planning-redesign/planning-menu.png
```

Manual browser checks:

- `/admin/planning` has no visible helper text, counts, pills, material, max-roll-weight, or old card layout.
- The unsent table can sort by `Поръчка`, `Доставка`, `Клиент`, `Изделие`, `Размер`, and `Бруто кг`.
- Machine tables remain sorted by `Ред` even after using unsent sort links.
- `Планирай` opens the same modal from unsent and machine rows.
- The modal posts to release for unsent rows and planning for assigned rows.
- Overflow menu labels stay on one line.
- Delete confirmation includes the order number.
- Delete succeeds for imported and pending/unstarted cards.
- Delete is blocked for running/paused/started cards.

- [ ] **Step 5: Run the full baseline pytest suite if the focused tests pass**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected: all tests pass. If unrelated failures appear, record the failing test names, check whether they reproduce on clean `main`, and do not hide planning regressions behind unrelated failures.

- [ ] **Step 6: Review the final diff before reporting completion**

Run:

```bash
git diff -- app/db.py app/main.py app/templates/admin_planning.html app/static/css/app.css tests/test_admin_planning.py tests/test_admin_routes.py tests/test_admin_card_review.py README.md docs/superpowers/plans/2026-07-26-admin-planning-redesign.md
```

Confirm:

- no terminal data-sync work is included;
- no migration files were added;
- no dependency files were changed;
- no real runtime database file was changed;
- no old visible `Върни`, inline machine/sequence forms, status pills, material field, max-roll-weight field, helper text, or count pills remain on `/admin/planning`;
- backend deletion remains guarded by stale-version and production-data checks.

---

## Self-Review

- Spec coverage: the plan covers the accepted stacked-table visual design, quiet table-row `Планирай` button, shared modal, overflow menus, deletion confirmation, backend delete guards, unsent sortable headers, machine sequence ordering, tests, docs, and Playwright verification.
- Placeholder scan: the plan contains no unresolved placeholders and no instruction to invent validation later.
- Type consistency: produced helpers and route/function names are defined before later tasks consume them.
- Scope check: the plan does not include terminal data-sync, calculator launch, worker recipe editing, import redesign, or countdown timers.

---

## Post-Implementation Verification Log

Recorded after implementation on branch `admin-planning-redesign-implementation`.

Automated checks run from `/home/sk/projects/extrusion-terminal/.worktrees/admin-planning-redesign-implementation`:

```bash
/home/sk/projects/extrusion-terminal/.venv/bin/python -m pytest tests/test_admin_planning.py -q
```

Result: `23 passed in 2.08s`.

```bash
/home/sk/projects/extrusion-terminal/.venv/bin/python -m pytest tests/test_admin_planning.py tests/test_admin_routes.py tests/test_admin_card_review.py tests/test_terminal_detail.py tests/test_recipe_sync.py -q
```

Result: `100 passed in 6.02s`.

```bash
/home/sk/projects/extrusion-terminal/.venv/bin/python -m pytest -q
```

Result: `573 passed in 40.74s`.

```bash
/home/sk/projects/extrusion-terminal/.venv/bin/python -m compileall app tests
git diff --check
```

Result: both passed; `git diff --check` produced no output.

Playwright check:

```bash
./node_modules/.bin/playwright --version
```

Result: `Version 1.61.0`.

Temporary browser verification database:

```text
/home/sk/projects/extrusion-terminal/.worktrees/admin-planning-redesign-implementation/.test-runtime/manual-planning-review/review2.sqlite3
```

Temporary server command:

```bash
EXTRUSION_DB_PATH=/home/sk/projects/extrusion-terminal/.worktrees/admin-planning-redesign-implementation/.test-runtime/manual-planning-review/review2.sqlite3 /home/sk/projects/extrusion-terminal/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8017
```

Browser verification result: live `/admin/planning` workflow passed through repo-local Playwright. The scripted check exercised unreleased sorting, release modal, machine replan modal, hostile order-number delete confirmation dismissal, successful imported-card deletion, blocked running-card deletion, desktop layout, mobile layout, modal-open screenshot, and overflow-menu-open screenshot.

Local ignored screenshot evidence:

```text
artifacts/ui-checks/admin-planning-review-desktop.png
artifacts/ui-checks/admin-planning-review-after-workflow.png
artifacts/ui-checks/admin-planning-review-mobile.png
artifacts/ui-checks/admin-planning-redesign/planning-desktop.png
artifacts/ui-checks/admin-planning-redesign/planning-modal.png
artifacts/ui-checks/admin-planning-redesign/planning-menu.png
artifacts/ui-checks/admin-planning-redesign/planning-mobile.png
```

Final temporary database state after the browser workflow:

```text
[('UI-001', 'pending', 4, 1), ('UI-003', 'imported', None, None), ('UI-PEND', 'pending', 2, 1), ('UI-RUN', 'running', 1, 1), ('UI-XSS-"\';alert(1)//', 'imported', None, None)]
```

This confirms `UI-002` was deleted, `UI-001` was released to machine 4, `UI-PEND` was replanned to machine 2, `UI-RUN` remained protected from deletion, and the hostile order number remained after dismissed confirmation.
