# Admin Planning Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish `/admin/planning` by adding server-rendered sorting to the unreleased table and making machine queue cards clearer without changing planning/release semantics.

**Architecture:** Keep the app server-rendered with normal GET and POST/303/GET flows. Sort only the unreleased draft list in the planning route using validated query parameters, and keep machine queue behavior unchanged while improving labels and return-button placement in the existing template/CSS.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, direct `sqlite3`, pytest, repo-local `.venv`, Playwright CLI for UI screenshot verification.

---

## Mandatory Session Instructions

- Start by reading `/home/sk/projects/extrusion-terminal/AGENTS.md` and follow it.
- Use `superpowers:subagent-driven-development` to execute this plan: fresh implementer per task, then spec-compliance review and code-quality review after each task.
- Do not commit, stage, or revert files unless the user explicitly asks. This repository's `AGENTS.md` overrides generic Superpowers commit guidance.
- Keep scope limited to `/admin/planning`.
- Keep the implementation server-rendered. Do not add AJAX, frontend state management, sessions, or client-side persistence.
- Do not change release, unrelease, or resequence data semantics.
- Do not mutate `data/extrusion_terminal.sqlite3` in automated tests or manual checks. Use temporary SQLite database paths.
- Use the repo-local Python virtualenv:

```bash
source .venv/bin/activate
```

## Approved Scope

Implement these approved changes:

- Move the pending-card return action in machine queue cards from the bottom of the card to a compact top-right action next to the order ID.
- Use `Върни` or `↩ Върни`, not `X`.
- Add small visible labels above machine queue reassignment controls: `Машина` and `Ред`.
- Remove the `{{ summary.machine_count }} машини в системата` text from the machine queue section header.
- Make unreleased table headers clickable for server-rendered sorting:
  - `Поръчка`
  - `Доставка`
  - `Клиент`
  - `Изделие`
- Clicking the active header toggles ascending/descending.
- Suggested URL shape:

```text
/admin/planning?draft_sort=delivery_date&draft_dir=asc#unreleased-queue
```

Explicitly out of scope:

- No mobile-specific redesign.
- No AJAX.
- No broad page redesign.
- No changes to machine queue release/resequence/unrelease behavior.
- No sorting/filtering changes for the machine queue section.

Note: Bulgarian UI text already uses non-ASCII characters in this repository. The arrow glyphs in this plan (`↩`, `↑`, `↓`) are intentional visible UI affordances, not placeholder notation.

## Files And Responsibilities

- Modify `tests/test_admin_routes.py`
  - Add route/template tests for unreleased sorting links and sorted draft order.
  - Add route/template tests for the machine queue card return action, labels, and removed machine-count text.

- Modify `app/main.py`
  - Accept validated `draft_sort` and `draft_dir` query parameters in `admin_planning()`.
  - Add small helper functions/constants for draft sorting and header link state.
  - Keep invalid sort/direction values safe by falling back to defaults.

- Modify `app/templates/admin_planning.html`
  - Render clickable unreleased table headers using context-provided sort links.
  - Move the unrelease form to the top-right of each pending machine queue card.
  - Add visible labels to machine queue planning controls.
  - Remove the machine-count text from the machine queue section header.

- Modify `app/static/css/app.css`
  - Add scoped CSS for sortable unreleased headers.
  - Add scoped CSS for queue-card header/action layout and compact planning field labels.
  - Avoid changing terminal queue card styles or unrelated admin detail styles.

- Generated artifacts only under `artifacts/ui-checks/admin-planning-polish/`.

---

## Task 1: Add Failing Route Tests For Sorting And Machine Card Polish

**Files:**

- Modify: `tests/test_admin_routes.py`

- [ ] **Step 1: Read focused context**

Run:

```bash
sed -n '180,570p' tests/test_admin_routes.py
sed -n '40,150p' app/templates/admin_planning.html
sed -n '420,610p' app/main.py
```

Expected:

- `admin_planning()`, `update_admin_card_planning()`, and `unrelease_admin_card()` are imported in `tests/test_admin_routes.py`.
- `test_admin_planning_renders_compact_unreleased_release_table()` already covers the current unreleased table.
- `test_admin_planning_renders_unrelease_form_for_pending_queue_cards_only()` currently expects `Върни в неизпратени`.
- `admin_planning()` currently accepts only `request`.

- [ ] **Step 2: Add a small order assertion helper**

In `tests/test_admin_routes.py`, after `card_version()`, add:

```python
def assert_html_order(html: str, *needles: str) -> None:
    positions = [html.index(needle) for needle in needles]
    assert positions == sorted(positions)
```

- [ ] **Step 3: Add a failing test for unreleased table sort links and sorted order**

In `tests/test_admin_routes.py`, after `test_admin_planning_renders_compact_unreleased_release_table`, add:

```python
def test_admin_planning_sorts_unreleased_cards_with_header_links(connection):
    result = import_cards_from_csv(
        "planning-sort-route.csv",
        csv_bytes(
            extrusion_row(
                "25941",
                delivery_date="2026-06-22",
                customer="Beta Customer",
                product_type="Zeta Product",
            ),
            extrusion_row(
                "25940",
                delivery_date="2026-06-21",
                customer="Alpha Customer",
                product_type="Omega Product",
            ),
            extrusion_row(
                "25942",
                delivery_date="2026-06-20",
                customer="Gamma Customer",
                product_type="Alpha Product",
            ),
        ),
        overwrite_existing=False,
    )
    assert result.rows_imported == 3

    customer_response = asyncio.run(
        admin_planning(
            make_request("/admin/planning", method="GET"),
            draft_sort="customer",
            draft_dir="asc",
        )
    )
    customer_html = customer_response.body.decode("utf-8")

    assert customer_response.status_code == 200
    assert_html_order(customer_html, "25940", "25941", "25942")
    assert 'href="/admin/planning?draft_sort=customer&amp;draft_dir=desc#unreleased-queue"' in customer_html
    assert 'aria-sort="ascending"' in customer_html

    delivery_response = asyncio.run(
        admin_planning(
            make_request("/admin/planning", method="GET"),
            draft_sort="delivery_date",
            draft_dir="desc",
        )
    )
    delivery_html = delivery_response.body.decode("utf-8")

    assert delivery_response.status_code == 200
    assert_html_order(delivery_html, "25941", "25940", "25942")
    assert 'href="/admin/planning?draft_sort=delivery_date&amp;draft_dir=asc#unreleased-queue"' in delivery_html
    assert 'aria-sort="descending"' in delivery_html
```

- [ ] **Step 4: Add a failing test for invalid sort fallback**

In `tests/test_admin_routes.py`, immediately after the sorting test, add:

```python
def test_admin_planning_ignores_invalid_unreleased_sort_values(connection):
    result = import_cards_from_csv(
        "planning-invalid-sort-route.csv",
        csv_bytes(
            extrusion_row("25951", customer="Second Customer"),
            extrusion_row("25950", customer="First Customer"),
        ),
        overwrite_existing=False,
    )
    assert result.rows_imported == 2

    response = asyncio.run(
        admin_planning(
            make_request("/admin/planning", method="GET"),
            draft_sort='customer" onclick="alert(1)',
            draft_dir="sideways",
        )
    )
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert_html_order(html, "25950", "25951")
    assert 'onclick="alert(1)' not in html
    assert 'draft_dir=sideways' not in html
```

- [ ] **Step 5: Replace the machine card unrelease render expectations**

In `test_admin_planning_renders_unrelease_form_for_pending_queue_cards_only`, replace the final assertions:

```python
    assert f'action="/admin/cards/{pending_id}/unrelease"' in html
    assert f'action="/admin/cards/{running_id}/unrelease"' not in html
    assert '<input type="hidden" name="return_to" value="planning">' in html
    assert "Върни в неизпратени" in html
```

with:

```python
    assert f'action="/admin/cards/{pending_id}/unrelease"' in html
    assert f'action="/admin/cards/{running_id}/unrelease"' not in html
    assert '<input type="hidden" name="return_to" value="planning">' in html
    assert 'class="queue-card-header"' in html
    assert 'class="queue-return-form"' in html
    assert 'class="queue-return-button"' in html
    assert 'aria-label="Върни поръчка 25924 в неизпратени"' in html
    assert ">↩ Върни</button>" in html
    assert "Върни в неизпратени" not in html
    assert "4 машини в системата" not in html
    assert '<span class="planning-field-label">Машина</span>' in html
    assert '<span class="planning-field-label">Ред</span>' in html
```

- [ ] **Step 6: Run focused tests and verify expected failures**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_planning_sorts_unreleased_cards_with_header_links tests/test_admin_routes.py::test_admin_planning_ignores_invalid_unreleased_sort_values tests/test_admin_routes.py::test_admin_planning_renders_unrelease_form_for_pending_queue_cards_only -q
```

Expected before implementation:

- Sorting tests fail because `admin_planning()` does not yet accept `draft_sort` and `draft_dir`.
- Machine card render test fails because the template still renders the old bottom `Върни в неизпратени` button and the machine-count text.

Do not modify production code in this task.

---

## Task 2: Add Safe Server-Side Sorting Context For Unreleased Cards

**Files:**

- Modify: `app/main.py`
- Test: `tests/test_admin_routes.py`

- [ ] **Step 1: Add imports and constants**

In `app/main.py`, update the datetime import near the top from:

```python
from datetime import date, datetime, timezone
```

to:

```python
from datetime import date, datetime, timezone
from urllib.parse import urlencode
```

Then add these constants near `DEFAULT_PLANNING_ANCHOR`:

```python
DRAFT_SORT_DEFAULT = "order_number"
DRAFT_SORT_DIRECTIONS = {"asc", "desc"}
DRAFT_SORT_LABELS = {
    "order_number": "Поръчка",
    "delivery_date": "Доставка",
    "customer": "Клиент",
    "product_type": "Изделие",
}
```

- [ ] **Step 2: Add sorting helper functions**

In `app/main.py`, after `safe_planning_anchor()`, add:

```python
def normalize_draft_sort(sort_key: str, sort_dir: str) -> tuple[str, str]:
    normalized_sort = sort_key if sort_key in DRAFT_SORT_LABELS else DRAFT_SORT_DEFAULT
    normalized_dir = sort_dir if sort_dir in DRAFT_SORT_DIRECTIONS else "asc"
    return normalized_sort, normalized_dir


def draft_date_sort_value(value: Any) -> tuple[int, str]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return (1, "")
    for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return (0, datetime.strptime(raw_value, date_format).date().isoformat())
        except ValueError:
            continue
    return (0, raw_value)


def draft_sort_value(card: dict[str, Any], sort_key: str) -> tuple[int, str]:
    if sort_key == "delivery_date":
        return draft_date_sort_value(card.get("delivery_date"))
    return (0, str(card.get(sort_key) or "").casefold())


def sorted_draft_cards(
    cards: list[dict[str, Any]],
    sort_key: str,
    sort_dir: str,
) -> list[dict[str, Any]]:
    reverse = sort_dir == "desc"
    return sorted(
        cards,
        key=lambda card: (
            draft_sort_value(card, sort_key),
            str(card.get("order_number") or "").casefold(),
            int(card.get("id") or 0),
        ),
        reverse=reverse,
    )


def build_draft_sort_links(active_sort: str, active_dir: str) -> dict[str, dict[str, str]]:
    links: dict[str, dict[str, str]] = {}
    for sort_key, label in DRAFT_SORT_LABELS.items():
        next_dir = "desc" if active_sort == sort_key and active_dir == "asc" else "asc"
        query = urlencode({"draft_sort": sort_key, "draft_dir": next_dir})
        aria_sort = "none"
        if active_sort == sort_key:
            aria_sort = "ascending" if active_dir == "asc" else "descending"
        links[sort_key] = {
            "label": label,
            "href": f"/admin/planning?{query}#unreleased-queue",
            "aria_sort": aria_sort,
        }
    return links
```

- [ ] **Step 3: Update planning context to accept sort inputs**

Change `admin_planning_context()` from:

```python
def admin_planning_context(**extra: Any) -> dict[str, Any]:
    machines = fetch_machines()
    active_cards = fetch_cards_by_status(ACTIVE_TERMINAL_STATUSES)
    context: dict[str, Any] = {
        "machines": machines,
        "draft_cards": fetch_cards_by_status((STATUS_IMPORTED,)),
        "machine_queues": group_cards_by_machine(machines, active_cards),
        "status_labels": STATUS_LABELS,
        "summary": database_summary(),
    }
    context.update(extra)
    return context
```

to:

```python
def admin_planning_context(
    draft_sort: str = DRAFT_SORT_DEFAULT,
    draft_dir: str = "asc",
    **extra: Any,
) -> dict[str, Any]:
    machines = fetch_machines()
    active_cards = fetch_cards_by_status(ACTIVE_TERMINAL_STATUSES)
    normalized_sort, normalized_dir = normalize_draft_sort(draft_sort, draft_dir)
    draft_cards = sorted_draft_cards(
        fetch_cards_by_status((STATUS_IMPORTED,)),
        normalized_sort,
        normalized_dir,
    )
    context: dict[str, Any] = {
        "machines": machines,
        "draft_cards": draft_cards,
        "draft_sort": normalized_sort,
        "draft_dir": normalized_dir,
        "draft_sort_links": build_draft_sort_links(normalized_sort, normalized_dir),
        "machine_queues": group_cards_by_machine(machines, active_cards),
        "status_labels": STATUS_LABELS,
        "summary": database_summary(),
    }
    context.update(extra)
    return context
```

- [ ] **Step 4: Update the planning route signature**

Change:

```python
@app.get("/admin/planning")
async def admin_planning(request: Request):
    return templates.TemplateResponse(
        request,
        "admin_planning.html",
        admin_planning_context(),
    )
```

to:

```python
@app.get("/admin/planning")
async def admin_planning(
    request: Request,
    draft_sort: str = DRAFT_SORT_DEFAULT,
    draft_dir: str = "asc",
):
    return templates.TemplateResponse(
        request,
        "admin_planning.html",
        admin_planning_context(draft_sort=draft_sort, draft_dir=draft_dir),
    )
```

- [ ] **Step 5: Run sorting tests and verify backend behavior**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_planning_sorts_unreleased_cards_with_header_links tests/test_admin_routes.py::test_admin_planning_ignores_invalid_unreleased_sort_values -q
```

Expected after this task:

- These tests may still fail on missing header links until Task 3 updates the template.
- They should no longer fail with `TypeError` for unexpected `draft_sort` or `draft_dir`.

---

## Task 3: Render Sortable Unreleased Table Headers

**Files:**

- Modify: `app/templates/admin_planning.html`
- Modify: `app/static/css/app.css`
- Test: `tests/test_admin_routes.py`

- [ ] **Step 1: Replace sortable header cells**

In `app/templates/admin_planning.html`, replace the first four unreleased table headers:

```jinja2
            <th class="col-order">Поръчка</th>
            <th class="col-delivery">Доставка</th>
            <th class="col-customer">Клиент</th>
            <th class="col-product">Изделие</th>
```

with:

```jinja2
            <th class="col-order" aria-sort="{{ draft_sort_links.order_number.aria_sort }}">
              <a class="sort-link {% if draft_sort == 'order_number' %}active{% endif %}" href="{{ draft_sort_links.order_number.href }}">{{ draft_sort_links.order_number.label }}{% if draft_sort == 'order_number' %}<span aria-hidden="true">{% if draft_dir == 'asc' %} ↑{% else %} ↓{% endif %}</span>{% endif %}</a>
            </th>
            <th class="col-delivery" aria-sort="{{ draft_sort_links.delivery_date.aria_sort }}">
              <a class="sort-link {% if draft_sort == 'delivery_date' %}active{% endif %}" href="{{ draft_sort_links.delivery_date.href }}">{{ draft_sort_links.delivery_date.label }}{% if draft_sort == 'delivery_date' %}<span aria-hidden="true">{% if draft_dir == 'asc' %} ↑{% else %} ↓{% endif %}</span>{% endif %}</a>
            </th>
            <th class="col-customer" aria-sort="{{ draft_sort_links.customer.aria_sort }}">
              <a class="sort-link {% if draft_sort == 'customer' %}active{% endif %}" href="{{ draft_sort_links.customer.href }}">{{ draft_sort_links.customer.label }}{% if draft_sort == 'customer' %}<span aria-hidden="true">{% if draft_dir == 'asc' %} ↑{% else %} ↓{% endif %}</span>{% endif %}</a>
            </th>
            <th class="col-product" aria-sort="{{ draft_sort_links.product_type.aria_sort }}">
              <a class="sort-link {% if draft_sort == 'product_type' %}active{% endif %}" href="{{ draft_sort_links.product_type.href }}">{{ draft_sort_links.product_type.label }}{% if draft_sort == 'product_type' %}<span aria-hidden="true">{% if draft_dir == 'asc' %} ↑{% else %} ↓{% endif %}</span>{% endif %}</a>
            </th>
```

Keep `Макс. кг/ролка`, `Ред`, `Машина`, and `Действие` as non-sortable plain headers.

- [ ] **Step 2: Add scoped sort-link styles**

In `app/static/css/app.css`, after `.unreleased-table th`, add:

```css
.unreleased-table .sort-link {
  color: inherit;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  text-decoration: none;
}

.unreleased-table .sort-link:hover,
.unreleased-table .sort-link:focus {
  color: var(--blue);
  text-decoration: underline;
}

.unreleased-table .sort-link.active {
  color: var(--text);
}
```

- [ ] **Step 3: Update the compact table test header assertions**

In `test_admin_planning_renders_compact_unreleased_release_table`, replace these four assertions:

```python
    assert '<th class="col-order">Поръчка</th>' in html
    assert '<th class="col-delivery">Доставка</th>' in html
    assert '<th class="col-customer">Клиент</th>' in html
    assert '<th class="col-product">Изделие</th>' in html
```

with:

```python
    assert '<th class="col-order" aria-sort="ascending">' in html
    assert 'href="/admin/planning?draft_sort=order_number&amp;draft_dir=desc#unreleased-queue"' in html
    assert 'href="/admin/planning?draft_sort=delivery_date&amp;draft_dir=asc#unreleased-queue"' in html
    assert 'href="/admin/planning?draft_sort=customer&amp;draft_dir=asc#unreleased-queue"' in html
    assert 'href="/admin/planning?draft_sort=product_type&amp;draft_dir=asc#unreleased-queue"' in html
    assert ">Поръчка" in html
    assert ">Доставка" in html
    assert ">Клиент" in html
    assert ">Изделие" in html
```

- [ ] **Step 4: Run unreleased table tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_planning_renders_compact_unreleased_release_table tests/test_admin_routes.py::test_admin_planning_sorts_unreleased_cards_with_header_links tests/test_admin_routes.py::test_admin_planning_ignores_invalid_unreleased_sort_values -q
```

Expected:

- All three tests pass.

---

## Task 4: Polish Machine Queue Card Markup

**Files:**

- Modify: `app/templates/admin_planning.html`
- Test: `tests/test_admin_routes.py`

- [ ] **Step 1: Remove machine-count text from machine queue header**

In `app/templates/admin_planning.html`, replace:

```jinja2
    <div class="section-head">
      <h2>Опашки по машини</h2>
      <span>{{ summary.machine_count }} машини в системата</span>
    </div>
```

with:

```jinja2
    <div class="section-head">
      <h2>Опашки по машини</h2>
    </div>
```

- [ ] **Step 2: Replace the queue-card main block and move the pending return form**

Inside the machine queue card loop, replace:

```jinja2
                <div class="queue-card-main">
                  <strong>{{ card.machine_sequence }}. <a href="/admin/cards/{{ card.id }}">№ {{ card.order_number }}</a></strong>
                  <span>{{ card.customer or "Без клиент" }}</span>
                  <small>{{ card.product_type or "Без изделие" }}</small>
                  <span class="pill status-{{ card.status }}">{{ status_labels.get(card.status, card.status) }}</span>
                </div>
                <form class="planning-form" action="/admin/cards/{{ card.id }}/planning" method="post">
                  <input type="hidden" name="loaded_version" value="{{ card.version }}">
                  <select name="machine_id" aria-label="Нова машина за поръчка {{ card.order_number }}">
                    {% for machine in machines %}
                      <option value="{{ machine.id }}" {% if card.machine_id == machine.id %}selected{% endif %}>{{ machine.id }}</option>
                    {% endfor %}
                  </select>
                  <input name="machine_sequence" inputmode="numeric" pattern="[0-9]*" value="{{ card.machine_sequence or '' }}" aria-label="Нов ред за поръчка {{ card.order_number }}">
                  <button type="submit">Запази</button>
                </form>
                {% if card.status == "pending" %}
                  <form class="planning-form" action="/admin/cards/{{ card.id }}/unrelease" method="post">
                    <input type="hidden" name="loaded_version" value="{{ card.version }}">
                    <input type="hidden" name="return_to" value="planning">
                    <button type="submit">Върни в неизпратени</button>
                  </form>
                {% endif %}
```

with:

```jinja2
                <div class="queue-card-header">
                  <strong>{{ card.machine_sequence }}. <a href="/admin/cards/{{ card.id }}">№ {{ card.order_number }}</a></strong>
                  {% if card.status == "pending" %}
                    <form class="queue-return-form" action="/admin/cards/{{ card.id }}/unrelease" method="post">
                      <input type="hidden" name="loaded_version" value="{{ card.version }}">
                      <input type="hidden" name="return_to" value="planning">
                      <button class="queue-return-button" type="submit" aria-label="Върни поръчка {{ card.order_number }} в неизпратени">↩ Върни</button>
                    </form>
                  {% endif %}
                </div>
                <div class="queue-card-main">
                  <span>{{ card.customer or "Без клиент" }}</span>
                  <small>{{ card.product_type or "Без изделие" }}</small>
                  <span class="pill status-{{ card.status }}">{{ status_labels.get(card.status, card.status) }}</span>
                </div>
                <form class="planning-form" action="/admin/cards/{{ card.id }}/planning" method="post">
                  <input type="hidden" name="loaded_version" value="{{ card.version }}">
                  <label class="planning-field">
                    <span class="planning-field-label">Машина</span>
                    <select name="machine_id" aria-label="Нова машина за поръчка {{ card.order_number }}">
                      {% for machine in machines %}
                        <option value="{{ machine.id }}" {% if card.machine_id == machine.id %}selected{% endif %}>{{ machine.id }}</option>
                      {% endfor %}
                    </select>
                  </label>
                  <label class="planning-field">
                    <span class="planning-field-label">Ред</span>
                    <input name="machine_sequence" inputmode="numeric" pattern="[0-9]*" value="{{ card.machine_sequence or '' }}" aria-label="Нов ред за поръчка {{ card.order_number }}">
                  </label>
                  <button type="submit">Запази</button>
                </form>
```

- [ ] **Step 3: Run the machine card render test**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_planning_renders_unrelease_form_for_pending_queue_cards_only -q
```

Expected:

- The test passes.

---

## Task 5: Add Scoped CSS For Machine Queue Card Polish

**Files:**

- Modify: `app/static/css/app.css`
- Test: Playwright screenshot in Task 6

- [ ] **Step 1: Update planning form layout for labeled fields**

In `app/static/css/app.css`, replace:

```css
.planning-form {
  display: grid;
  grid-template-columns: 72px minmax(72px, 1fr) auto;
  gap: 7px;
  align-items: center;
  margin-top: 8px;
}
```

with:

```css
.planning-form {
  display: grid;
  grid-template-columns: minmax(72px, 0.8fr) minmax(72px, 1fr) auto;
  gap: 7px;
  align-items: end;
  margin-top: 8px;
}
```

- [ ] **Step 2: Add label and header styles**

In `app/static/css/app.css`, after `.planning-form { ... }`, add:

```css
.planning-field {
  display: grid;
  gap: 3px;
}

.planning-field-label {
  color: var(--muted);
  font-size: 10px;
  font-weight: 850;
  line-height: 1;
  text-transform: uppercase;
}
```

Then replace:

```css
.queue-card-main {
  display: grid;
  gap: 4px;
}
```

with:

```css
.queue-card-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  justify-content: space-between;
}

.queue-return-form {
  margin: 0;
}

.queue-return-button {
  min-height: 28px;
  padding: 0 7px;
  white-space: nowrap;
}

.queue-card-main {
  display: grid;
  gap: 4px;
  margin-top: 4px;
}
```

- [ ] **Step 3: Keep input styling working under labels**

Replace:

```css
.planning-form input {
  width: 100%;
  min-height: 38px;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  padding: 0 9px;
}
```

with:

```css
.planning-form select,
.planning-form input {
  width: 100%;
  min-height: 38px;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  padding: 0 9px;
}
```

- [ ] **Step 4: Run CSS whitespace check**

Run:

```bash
git diff -- app/static/css/app.css
git diff --check
```

Expected:

- CSS changes are scoped to planning form labels, queue-card header/action, and existing planning form control styling.
- No whitespace errors.

---

## Task 6: Focused Verification And Playwright UI Evidence

**Files:**

- Generated artifacts only under `artifacts/ui-checks/admin-planning-polish/`
- No production DB mutation

- [ ] **Step 1: Run focused automated tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py tests/test_admin_planning.py
```

Expected:

- Both test modules pass.

- [ ] **Step 2: Run full Python test suite if focused tests pass**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected:

- Full suite passes.

- [ ] **Step 3: Create a temporary manual-check database**

Run:

```bash
mkdir -p .test-runtime/admin-planning-polish artifacts/ui-checks/admin-planning-polish
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/admin-planning-polish/planning.sqlite3 python -c '
import csv
import io
from app import db
from app.importer import IMPORT_FIELDS, import_cards_from_csv

db.init_db()

def csv_bytes(*rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")

def row(order_number, delivery_date, customer, product_type):
    return {
        "order_number": order_number,
        "delivery_date": delivery_date,
        "customer": customer,
        "product_type": product_type,
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "da",
        "raw_material_a": "LDPE A",
        "packaging_method": "rolls",
    }

result = import_cards_from_csv(
    "planning-polish-ui.csv",
    csv_bytes(
        row("32601", "2026-06-22", "Beta Foods", "Zeta tube 350/400/0.045"),
        row("32602", "2026-06-21", "Alpha Pack", "Omega sleeve 530/0.075"),
        row("32603", "2026-06-20", "Gamma Print", "Alpha film 400/0.070"),
        row("32604", "2026-06-23", "Delta Client", "Carrier bag 300/0.030"),
    ),
    overwrite_existing=False,
)
assert result.rows_imported == 4, result

card_ids = [row["id"] for row in db.fetch_cards_by_status((db.STATUS_IMPORTED,))]
assert db.release_card(card_ids[0], machine_id=1, machine_sequence=1, loaded_version=db.fetch_admin_card_detail(card_ids[0])["version"], max_roll_weight="60").ok
assert db.release_card(card_ids[1], machine_id=1, machine_sequence=2, loaded_version=db.fetch_admin_card_detail(card_ids[1])["version"], max_roll_weight="60").ok
assert db.release_card(card_ids[2], machine_id=2, machine_sequence=1, loaded_version=db.fetch_admin_card_detail(card_ids[2])["version"], max_roll_weight="60").ok
assert db.start_production_timing(card_ids[1], db.fetch_admin_card_detail(card_ids[1])["version"]).ok
print("seeded planning polish database")
'
```

Expected:

- Output includes `seeded planning polish database`.
- Database is under `.test-runtime/`, not under `data/`.

- [ ] **Step 4: Start the app against the temporary DB**

Run:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/admin-planning-polish/planning.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8767
```

Expected:

- Uvicorn reports it is running on `http://127.0.0.1:8767`.

Keep this process running until screenshots are captured. Stop it with `Ctrl+C` after Step 7.

- [ ] **Step 5: Capture Playwright screenshots**

In a second shell, run:

```bash
npx playwright screenshot --viewport-size=1440,950 http://127.0.0.1:8767/admin/planning artifacts/ui-checks/admin-planning-polish/admin-planning-polish-desktop.png
npx playwright screenshot --viewport-size=1440,950 'http://127.0.0.1:8767/admin/planning?draft_sort=customer&draft_dir=asc#unreleased-queue' artifacts/ui-checks/admin-planning-polish/admin-planning-polish-sorted.png
```

Expected:

- Screenshots are created.
- Unreleased headers for order, delivery, customer, and product are visibly clickable.
- Machine queue section no longer shows `4 машини в системата`.
- Pending machine cards show a compact top-right `↩ Върни` action.
- Machine queue controls show `Машина` and `Ред` labels above the controls.
- Running cards do not show the return action.

- [ ] **Step 6: Verify sorting and button placement with Playwright assertions**

Run:

```bash
node - <<'NODE'
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
  await page.goto('http://127.0.0.1:8767/admin/planning?draft_sort=customer&draft_dir=asc#unreleased-queue');

  const machineCountText = await page.getByText('машини в системата').count();
  if (machineCountText !== 0) throw new Error('machine count text still visible');

  const returnButtons = await page.locator('.queue-return-button').allTextContents();
  if (!returnButtons.every((text) => text.trim() === '↩ Върни')) {
    throw new Error(`unexpected return button labels: ${returnButtons.join(', ')}`);
  }

  const machineLabels = await page.locator('.planning-field-label').allTextContents();
  if (!machineLabels.includes('Машина') || !machineLabels.includes('Ред')) {
    throw new Error(`missing planning labels: ${machineLabels.join(', ')}`);
  }

  const orders = await page.locator('#unreleased-queue tbody .col-order').allTextContents();
  console.log(JSON.stringify({ orders, returnButtons, machineLabels }, null, 2));
  await browser.close();
})();
NODE
```

Expected:

- Script exits 0.
- Output lists sorted unreleased order numbers and visible machine-card labels/actions.

- [ ] **Step 7: Stop the temporary server**

Stop Uvicorn with `Ctrl+C`.

Expected:

- Uvicorn logs clean shutdown.
- No listener remains on port `8767`.

- [ ] **Step 8: Run final checks**

Run:

```bash
git diff --check
git diff --cached --name-only
git status --short
```

Expected:

- `git diff --check` exits 0.
- `git diff --cached --name-only` prints nothing.
- `git status --short` shows only intentional unstaged changes plus any pre-existing dirty files.

---

## Final Verification Checklist

Before reporting completion, run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py tests/test_admin_planning.py
python -m pytest
git diff --check
ls -l artifacts/ui-checks/admin-planning-polish/admin-planning-polish-desktop.png
ls -l artifacts/ui-checks/admin-planning-polish/admin-planning-polish-sorted.png
git diff --cached --name-only
```

Report:

- tests run and pass/fail status;
- screenshot paths;
- whether the temp server was stopped;
- whether any unrelated pre-existing dirty files remain;
- confirmation that no files were staged or committed.
