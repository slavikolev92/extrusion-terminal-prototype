# Admin Global Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the admin shell so `/admin/import`, `/admin/planning`, `/admin/cards`, and `/admin/cards/{id}` share one sticky global navigation bar, while card-specific actions live in a separate toolbar and the operational card internals remain unchanged.

**Architecture:** Keep the existing FastAPI/Jinja/server-rendered structure. Replace the repeated page-header navigation with a single reusable `_admin_nav.html` shell that receives an `admin_section` context value. On card detail pages, replace only the top header/action cluster with a compact card context header plus a separate action toolbar; do not restructure the order/materials/rolls/timing sections.

**Tech Stack:** FastAPI, Jinja2 templates, direct Python route context helpers, CSS in `app/static/css/app.css`, pytest route/template assertions, Playwright for live UI screenshot verification.

---

## Approved Scope

Implement these changes:

- Add one consistent sticky admin global navigation bar across all admin pages.
- Equalize the three main admin navigation tabs: `Импорт`, `Планиране`, `Технологични карти`.
- Move `Терминал` out of per-page/per-card action clusters and rename it to `Към терминала` in the global nav.
- Remove the `Началник смяна` eyebrow/tag from admin pages.
- Remove oversized repeated page title treatment from admin pages.
- Separate card-specific workflow actions from global navigation.
- Remove duplicate `Технологични карти` navigation on card detail pages.
- Remove sticky behavior from the `Общо произведено` summary panel so global navigation owns the sticky top position.
- Preserve all internal operational card body sections and field layouts.

Do not implement these changes:

- Do not redesign `Данни по поръчката`, `Материали`, `Ролки`, `Време`, or `Системни данни`.
- Do not change backend workflow rules or status transitions.
- Do not change print eligibility.
- Do not change terminal/workstation layout.
- Do not stage or commit unless the user explicitly asks. This overrides the generic Superpowers "frequent commits" recommendation for this repository.

## Files And Responsibilities

- Modify: `app/main.py`
  - Add `admin_section` to admin template contexts.
  - Keep route behavior unchanged.

- Modify: `app/templates/_admin_nav.html`
  - Convert the current simple link row into the sticky global admin navigation.
  - Include the right-side `Към терминала` app-switch link.
  - Use `admin_section` to mark the active tab.

- Modify: `app/templates/admin_import.html`
  - Remove the old page header and terminal link.
  - Include the new global nav at the top of the admin page.
  - Add an accessible hidden `h1` or compact title treatment without restoring the old oversized header.

- Modify: `app/templates/admin_planning.html`
  - Same shell treatment as import.
  - Preserve planning table and machine queue markup.

- Modify: `app/templates/admin_cards.html`
  - Same shell treatment as import.
  - Preserve filters and cards table.

- Modify: `app/templates/admin_card_detail.html`
  - Replace only the top `page-header admin-card-header` area.
  - Add compact card context and separate `admin-card-actions` toolbar.
  - Preserve the operational card body starting with `admin-summary-panel` and all sections below it, except class behavior needed to remove sticky summary.

- Modify: `app/static/css/app.css`
  - Add sticky global admin nav styles.
  - Add equal-width tab styles.
  - Add compact page/card context styles.
  - Add separate card action toolbar styles.
  - Remove or neutralize sticky behavior from `.admin-summary-panel`.

- Modify: `tests/test_admin_routes.py`
  - Add focused route-rendering tests for shared admin global nav and removal of old header duplication.

- Modify: `tests/test_admin_card_detail_redesign.py`
  - Update existing assertions that currently expect print links to use `class="nav-link"`.
  - Add card detail assertions for separated action toolbar and no duplicate navigation.

- Modify: `IMPLEMENTATION_PLAN.md`
  - Add this as the next milestone once the implementation starts, keeping the next intended step obvious.

---

## Task 1: Add Failing Tests For Global Admin Navigation

**Files:**
- Modify: `tests/test_admin_routes.py`

- [ ] **Step 1: Add helper assertions near `assert_html_order`**

Add this code after `assert_html_order`:

```python
def assert_admin_global_nav(html: str, active_label: str) -> None:
    assert 'class="admin-topbar"' in html
    assert 'aria-label="Админ навигация"' in html
    assert 'href="/admin/import"' in html
    assert 'href="/admin/planning"' in html
    assert 'href="/admin/cards"' in html
    assert 'href="/terminal"' in html
    assert "Към терминала" in html
    assert f'aria-current="page">{active_label}</a>' in html
    assert "Началник смяна" not in html
    assert '<a class="nav-link" href="/terminal">Терминал</a>' not in html
```

- [ ] **Step 2: Add route tests for import, planning, and card list pages**

Add this code after `test_admin_import_explains_overwrite_scope`:

```python
def test_admin_import_uses_shared_global_navigation(connection):
    response = asyncio.run(admin_import(make_request("/admin/import", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert_admin_global_nav(html, "Импорт")
    assert "Импорт от CSV" in html


def test_admin_planning_uses_shared_global_navigation(connection):
    response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert_admin_global_nav(html, "Планиране")
    assert "Неизпратени технологични карти" in html


def test_admin_cards_list_uses_shared_global_navigation(connection):
    response = asyncio.run(
        admin_cards(
            make_request("/admin/cards", method="GET"),
            order_number="",
            customer="",
            product="",
            status="",
        )
    )
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert_admin_global_nav(html, "Технологични карти")
    assert "Търсене на технологични карти" in html
```

- [ ] **Step 3: Import `admin_cards` in the existing import list**

Change the import from `app.main` so it includes `admin_cards`:

```python
from app.main import (
    admin,
    admin_card_detail,
    admin_cards,
    admin_import,
    admin_planning,
    app,
    import_csv as post_admin_import,
    release_card_to_terminal,
    sorted_draft_cards,
    unrelease_admin_card,
    update_admin_card_planning,
)
```

- [ ] **Step 4: Run the focused tests and confirm they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_import_uses_shared_global_navigation tests/test_admin_routes.py::test_admin_planning_uses_shared_global_navigation tests/test_admin_routes.py::test_admin_cards_list_uses_shared_global_navigation -q
```

Expected result before implementation:

```text
FAILED ... assert 'class="admin-topbar"' in html
```

---

## Task 2: Add Failing Tests For Card Detail Action Separation

**Files:**
- Modify: `tests/test_admin_card_detail_redesign.py`

- [ ] **Step 1: Add a card-detail navigation test**

Add this test after `test_admin_detail_print_link_is_available_only_for_completed_cards`:

```python
def test_admin_detail_separates_global_navigation_from_card_actions(connection):
    card_id = prepare_dense_completed_card("27042", roll_count=1)

    html = render_admin_detail(card_id)

    assert 'class="admin-topbar"' in html
    assert 'aria-current="page">Технологични карти</a>' in html
    assert "Към терминала" in html
    assert 'class="admin-card-context"' in html
    assert f"Технологични карти / Поръчка № 27042" in html
    assert 'class="admin-card-actions"' in html
    assert f'href="/cards/{card_id}/print"' in html
    assert f'action="/admin/cards/{card_id}/archive"' in html

    header_before_actions = html.split('class="admin-card-actions"', 1)[0]
    assert 'href="/cards/' not in header_before_actions
    assert "Маркирай като завършена" not in header_before_actions
    assert "Началник смяна" not in html
    assert '<a class="nav-link" href="/admin/cards">Технологични карти</a>' not in html
    assert '<a class="nav-link" href="/terminal">Терминал</a>' not in html
```

- [ ] **Step 2: Update print-link class expectations in existing tests**

Replace the three exact assertions that currently expect:

```python
f'<a class="nav-link" href="/cards/{completed_id}/print" '
'target="_blank" rel="noopener">Печат / препечат</a>'
```

or:

```python
f'<a class="nav-link" href="/cards/{card_id}/print" '
'target="_blank" rel="noopener">Печат / препечат</a>'
```

with less brittle assertions:

```python
assert f'href="/cards/{completed_id}/print"' in completed_html
assert 'target="_blank" rel="noopener">Печат / препечат</a>' in completed_html
```

and:

```python
assert f'href="/cards/{card_id}/print"' in html
assert 'target="_blank" rel="noopener">Печат / препечат</a>' in html
```

Keep the existing negative assertions for cancelled cards and archived cards.

- [ ] **Step 3: Run the focused card detail tests and confirm the new test fails**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py::test_admin_detail_separates_global_navigation_from_card_actions tests/test_admin_card_detail_redesign.py::test_admin_detail_print_link_is_available_only_for_completed_cards tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_archive_action_for_produced_cards tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_print_but_no_archive_action_for_archived_cards -q
```

Expected result before implementation:

```text
FAILED ... assert 'class="admin-topbar"' in html
```

---

## Task 3: Pass Admin Section Context To Templates

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add `admin_section` to import context**

Change `admin_import_context` to include:

```python
def admin_import_context(**extra: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "admin_section": "import",
        "recent_imports": fetch_recent_import_batches(),
        "summary": database_summary(),
    }
    context.update(extra)
    return context
```

- [ ] **Step 2: Add `admin_section` to planning context**

In `admin_planning_context`, add `"admin_section": "planning"` to the context dictionary:

```python
    context: dict[str, Any] = {
        "admin_section": "planning",
        "draft_cards": draft_cards,
        "draft_sort": normalized_sort,
        "draft_dir": normalized_dir,
        "draft_sort_links": build_draft_sort_links(normalized_sort, normalized_dir),
        "machine_queues": machine_queues,
        "machines": [queue["machine"] for queue in machine_queues],
        "summary": database_summary(),
        "status_labels": STATUS_LABELS,
    }
```

- [ ] **Step 3: Add `admin_section` to card detail context**

In `admin_card_detail_context`, add `"admin_section": "cards"` to the context dictionary:

```python
    context: dict[str, Any] = {
        "admin_section": "cards",
        "card": card,
        "import_fields": IMPORT_FIELDS,
        "import_field_labels": IMPORT_FIELD_LABELS,
        "status_labels": STATUS_LABELS,
        "timing_reason_labels": TIMING_REASON_LABELS,
        "quantity_lines": build_quantity_lines(card),
        "recipe_rows": build_recipe_rows(card),
    }
```

- [ ] **Step 4: Add `admin_section` to the card list route**

In `admin_cards`, add `"admin_section": "cards"` to the `TemplateResponse` context:

```python
        {
            "admin_section": "cards",
            "cards": fetch_admin_cards(filters),
            "filters": filters,
            "card_statuses": CARD_STATUSES,
            "status_labels": STATUS_LABELS,
            "summary": database_summary(),
        },
```

- [ ] **Step 5: Run current tests to confirm no route behavior changed**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_redirects_to_import tests/test_admin_routes.py::test_admin_import_explains_overwrite_scope -q
```

Expected result:

```text
2 passed
```

---

## Task 4: Build The Shared Sticky Admin Navigation Template

**Files:**
- Modify: `app/templates/_admin_nav.html`

- [ ] **Step 1: Replace `_admin_nav.html` with the global topbar**

Replace the file contents with:

```html
<nav class="admin-topbar" aria-label="Админ навигация">
  <div class="admin-topbar-inner">
    <a class="admin-brand" href="/admin/cards">Екструдиране</a>
    <div class="admin-tabs" role="list">
      <a class="admin-tab {% if admin_section == 'import' %}active{% endif %}" href="/admin/import" {% if admin_section == 'import' %}aria-current="page"{% endif %}>Импорт</a>
      <a class="admin-tab {% if admin_section == 'planning' %}active{% endif %}" href="/admin/planning" {% if admin_section == 'planning' %}aria-current="page"{% endif %}>Планиране</a>
      <a class="admin-tab {% if admin_section == 'cards' %}active{% endif %}" href="/admin/cards" {% if admin_section == 'cards' %}aria-current="page"{% endif %}>Технологични карти</a>
    </div>
    <a class="admin-terminal-link" href="/terminal">Към терминала</a>
  </div>
</nav>
```

- [ ] **Step 2: Run the admin nav tests and confirm they still fail because templates still render old headers**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_import_uses_shared_global_navigation tests/test_admin_routes.py::test_admin_planning_uses_shared_global_navigation tests/test_admin_routes.py::test_admin_cards_list_uses_shared_global_navigation -q
```

Expected result:

```text
FAILED ... assert '<a class="nav-link" href="/terminal">Терминал</a>' not in html
```

---

## Task 5: Apply The Global Shell To Import, Planning, And Card List Pages

**Files:**
- Modify: `app/templates/admin_import.html`
- Modify: `app/templates/admin_planning.html`
- Modify: `app/templates/admin_cards.html`

- [ ] **Step 1: Replace the top of `admin_import.html` body**

Replace this block:

```html
<main class="page">
  <header class="page-header">
    <div>
      <p class="eyebrow">Началник смяна</p>
      <h1>Импорт</h1>
    </div>
    <a class="nav-link" href="/terminal">Терминал</a>
  </header>

  {% include "_admin_nav.html" %}
```

with:

```html
<main class="page admin-page">
  {% include "_admin_nav.html" %}
  <h1 class="visually-hidden">Импорт</h1>
```

- [ ] **Step 2: Replace the top of `admin_planning.html` body**

Replace this block:

```html
<main class="page">
  <header class="page-header">
    <div>
      <p class="eyebrow">Началник смяна</p>
      <h1>Планиране</h1>
    </div>
    <a class="nav-link" href="/terminal">Терминал</a>
  </header>

  {% include "_admin_nav.html" %}
```

with:

```html
<main class="page admin-page">
  {% include "_admin_nav.html" %}
  <h1 class="visually-hidden">Планиране</h1>
```

- [ ] **Step 3: Replace the top of `admin_cards.html` body**

Replace this block:

```html
<main class="page">
  <header class="page-header">
    <div>
      <p class="eyebrow">Началник смяна</p>
      <h1>Технологични карти</h1>
    </div>
    <a class="nav-link" href="/terminal">Терминал</a>
  </header>

  {% include "_admin_nav.html" %}
```

with:

```html
<main class="page admin-page">
  {% include "_admin_nav.html" %}
  <h1 class="visually-hidden">Технологични карти</h1>
```

- [ ] **Step 4: Run focused global nav tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_import_uses_shared_global_navigation tests/test_admin_routes.py::test_admin_planning_uses_shared_global_navigation tests/test_admin_routes.py::test_admin_cards_list_uses_shared_global_navigation -q
```

Expected result:

```text
3 passed
```

---

## Task 6: Separate Card Detail Context From Card Actions

**Files:**
- Modify: `app/templates/admin_card_detail.html`

- [ ] **Step 1: Replace only the card detail header and old nav include**

Replace the block from:

```html
<main class="page wide-page admin-review-page">
  <header class="page-header admin-card-header">
```

through the existing:

```html
  {% include "_admin_nav.html" %}
```

with this block:

```html
<main class="page wide-page admin-page admin-review-page">
  {% include "_admin_nav.html" %}

  <header class="admin-card-context">
    <div class="admin-card-title-block">
      <p class="admin-breadcrumb">Технологични карти / Поръчка № {{ card.order_number }}</p>
      <h1>Поръчка № {{ card.order_number }}</h1>
      <div class="admin-card-meta">
        <span class="pill status-{{ card.status }}">{{ status_labels.get(card.status, card.status) }}</span>
        <span>
          {% if card.machine_id %}
            Машина {{ card.machine_id }}{% if card.machine_sequence %} / ред {{ card.machine_sequence }}{% endif %}
          {% else %}
            Без машина
          {% endif %}
        </span>
        <span>Версия {{ card.version }}</span>
        <span>Обновена {{ card.updated_at }}</span>
      </div>
    </div>
    <div class="admin-card-actions" aria-label="Действия за технологична карта">
      {% if card.status in ["completed", "archived"] %}
        <a class="admin-action-button primary" href="/cards/{{ card.id }}/print" target="_blank" rel="noopener">Печат / препечат</a>
      {% endif %}
      {% if card.status == "completed" %}
        <form action="/admin/cards/{{ card.id }}/archive" method="post">
          <input type="hidden" name="loaded_version" value="{{ card.version }}">
          <button class="admin-action-button" type="submit">Маркирай като завършена</button>
        </form>
      {% endif %}
      {% if card.status == "pending" %}
        <form action="/admin/cards/{{ card.id }}/unrelease" method="post">
          <input type="hidden" name="loaded_version" value="{{ card.version }}">
          <input type="hidden" name="return_to" value="detail">
          <button class="admin-action-button" type="submit">Върни в планиране</button>
        </form>
      {% endif %}
      {% if card.status in ["pending", "running", "paused"] %}
        <form action="/admin/cards/{{ card.id }}/cancel" method="post">
          <input type="hidden" name="loaded_version" value="{{ card.version }}">
          <button class="admin-action-button danger" type="submit">Анулирай</button>
        </form>
      {% elif card.status == "cancelled" %}
        <form action="/admin/cards/{{ card.id }}/restore" method="post">
          <input type="hidden" name="loaded_version" value="{{ card.version }}">
          <button class="admin-action-button" type="submit">Възстанови</button>
        </form>
      {% endif %}
    </div>
  </header>
```

- [ ] **Step 2: Confirm the operational card body remains present**

In `app/templates/admin_card_detail.html`, verify these existing markers are still present after the new header:

```html
<section class="section admin-summary-panel">
<form class="admin-operational-form" action="/admin/cards/{{ card.id }}/imported-fields" method="post">
<section class="section operational-panel" id="materials">
<section class="section operational-panel" id="rolls">
<section class="section operational-panel" id="timing">
<section class="section admin-system-section">
```

- [ ] **Step 3: Run the focused card detail tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py::test_admin_detail_separates_global_navigation_from_card_actions tests/test_admin_card_detail_redesign.py::test_admin_detail_print_link_is_available_only_for_completed_cards tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_archive_action_for_produced_cards tests/test_admin_card_detail_redesign.py::test_admin_detail_shows_print_but_no_archive_action_for_archived_cards -q
```

Expected result:

```text
4 passed
```

---

## Task 7: Style The Admin Shell And Remove Sticky Summary Behavior

**Files:**
- Modify: `app/static/css/app.css`

- [ ] **Step 1: Add global admin shell styles after the `.page` and `.wide-page` rules**

Add:

```css
.admin-page {
  padding-top: 14px;
}

.admin-topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  margin-bottom: 16px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 2px 10px rgba(31, 35, 40, 0.08);
  backdrop-filter: blur(8px);
}

.admin-topbar-inner {
  display: grid;
  grid-template-columns: minmax(150px, auto) minmax(0, 540px) auto;
  gap: 12px;
  align-items: center;
  min-height: 58px;
  padding: 8px;
}

.admin-brand {
  color: var(--text);
  font-size: 15px;
  font-weight: 850;
  text-decoration: none;
  white-space: nowrap;
}

.admin-tabs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.admin-tab,
.admin-terminal-link,
.admin-action-button {
  min-height: 40px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
  color: var(--text);
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 750;
  text-align: center;
  text-decoration: none;
  white-space: nowrap;
}

.admin-tab.active {
  border-color: var(--blue);
  background: var(--blue-soft);
  color: var(--blue);
}

.admin-terminal-link {
  justify-self: end;
}
```

- [ ] **Step 2: Add compact card context and action toolbar styles after `.admin-card-meta`**

Add:

```css
.admin-card-context {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: start;
  margin-bottom: 16px;
}

.admin-card-title-block h1 {
  margin-bottom: 0;
  font-size: 26px;
  line-height: 1.1;
}

.admin-breadcrumb {
  margin-bottom: 5px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 800;
}

.admin-card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.admin-card-actions form {
  margin: 0;
}

.admin-action-button.primary {
  border-color: var(--blue);
  background: var(--blue);
  color: white;
}

.admin-action-button.danger {
  border-color: #f0a3a8;
  background: var(--red-soft);
  color: var(--red);
}
```

- [ ] **Step 3: Remove sticky behavior from `.admin-summary-panel`**

Replace:

```css
.admin-summary-panel {
  position: sticky;
  top: 0;
  z-index: 2;
}
```

with:

```css
.admin-summary-panel {
  position: static;
}
```

- [ ] **Step 4: Make mobile/smaller viewport behavior stable**

Add this near the existing media queries if present, or near the end of `app/static/css/app.css`:

```css
@media (max-width: 820px) {
  .admin-topbar-inner {
    grid-template-columns: 1fr;
  }

  .admin-tabs {
    grid-template-columns: 1fr;
  }

  .admin-terminal-link {
    justify-self: stretch;
  }

  .admin-card-context {
    grid-template-columns: 1fr;
  }

  .admin-card-actions {
    justify-content: flex-start;
  }

  .admin-action-button {
    width: 100%;
  }
}
```

- [ ] **Step 5: Run CSS-adjacent template tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_import_uses_shared_global_navigation tests/test_admin_routes.py::test_admin_planning_uses_shared_global_navigation tests/test_admin_routes.py::test_admin_cards_list_uses_shared_global_navigation tests/test_admin_card_detail_redesign.py::test_admin_detail_separates_global_navigation_from_card_actions -q
```

Expected result:

```text
4 passed
```

---

## Task 8: Update Milestone Tracker

**Files:**
- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Add the new milestone near the current active/next milestone section**

Add a milestone entry:

```markdown
## Milestone 10 - Admin Global Navigation Rework

Status: in progress

Scope:

- replace repeated admin page headers with one sticky global admin navigation bar.
- keep equal-width navigation tabs for Import, Planning, and Technology Cards.
- move terminal app switching into the global navigation bar as `Към терминала`.
- remove the `Началник смяна` eyebrow and oversized repeated page title treatment.
- separate card-specific actions from global navigation on operational card detail pages.
- remove duplicate navigation buttons on card detail pages.
- remove sticky behavior from the produced-summary panel so global navigation remains the sticky orientation element.
- preserve operational card internal section structure and styling.

Review checkpoint:

- admin import, planning, card list, and card detail pages render the same global navigation.
- card detail actions vary by status but remain separate from global navigation.
- operational card body sections are visually unchanged except for the removed sticky summary behavior.
- focused tests pass.
- Playwright screenshot verification covers import, planning, cards list, and card detail pages.
```

- [ ] **Step 2: Run a quick grep to confirm milestone appears**

Run:

```bash
rg -n "Milestone 10 - Admin Global Navigation Rework|sticky global admin navigation" IMPLEMENTATION_PLAN.md
```

Expected result:

```text
IMPLEMENTATION_PLAN.md:<line>:## Milestone 10 - Admin Global Navigation Rework
```

---

## Task 9: Run Automated Verification

**Files:**
- No file changes.

- [ ] **Step 1: Run focused admin tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py tests/test_admin_card_detail_redesign.py -q
```

Expected result:

```text
all selected tests pass
```

- [ ] **Step 2: Run the full test suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected result:

```text
all tests pass
```

- [ ] **Step 3: Run whitespace check**

Run:

```bash
git diff --check
```

Expected result:

```text
no output
```

---

## Task 10: Run Live UI Verification With Playwright

**Files:**
- Create screenshots under: `artifacts/ui-checks/admin-global-navigation/`
- Do not track generated artifacts.

- [ ] **Step 1: Start the local app on an available port**

Run:

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Expected result:

```text
Uvicorn running on http://127.0.0.1:8001
```

If port `8001` is busy, use `8002` and update the Playwright command URLs in the next step.

- [ ] **Step 2: Capture screenshots of admin pages**

Run this from another shell while the server is running:

```bash
mkdir -p artifacts/ui-checks/admin-global-navigation
node -e "const { chromium } = require('@playwright/test'); const path = require('path'); (async () => { const out = 'artifacts/ui-checks/admin-global-navigation'; const browser = await chromium.launch({ headless: true }); const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 }); const targets = [['import','/admin/import'], ['planning','/admin/planning'], ['cards','/admin/cards'], ['card-completed','/admin/cards/3'], ['card-pending','/admin/cards/10']]; for (const [name, url] of targets) { await page.goto('http://127.0.0.1:8001' + url, { waitUntil: 'networkidle' }); await page.screenshot({ path: path.join(out, name + '-viewport.png'), fullPage: false }); await page.screenshot({ path: path.join(out, name + '-full.png'), fullPage: true }); } await browser.close(); })().catch(err => { console.error(err); process.exit(1); });"
```

Expected result:

```text
artifacts/ui-checks/admin-global-navigation/import-viewport.png
artifacts/ui-checks/admin-global-navigation/planning-viewport.png
artifacts/ui-checks/admin-global-navigation/cards-viewport.png
artifacts/ui-checks/admin-global-navigation/card-completed-viewport.png
artifacts/ui-checks/admin-global-navigation/card-pending-viewport.png
```

- [ ] **Step 3: Verify sticky nav while scrolled**

Run:

```bash
node -e "const { chromium } = require('@playwright/test'); const path = require('path'); (async () => { const out = 'artifacts/ui-checks/admin-global-navigation'; const browser = await chromium.launch({ headless: true }); const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 }); await page.goto('http://127.0.0.1:8001/admin/cards/3', { waitUntil: 'networkidle' }); await page.evaluate(() => window.scrollTo(0, 900)); await page.screenshot({ path: path.join(out, 'card-completed-scrolled-nav.png'), fullPage: false }); const navBox = await page.locator('.admin-topbar').boundingBox(); const summaryPosition = await page.locator('.admin-summary-panel').evaluate(el => getComputedStyle(el).position); console.log(JSON.stringify({ navTop: navBox && Math.round(navBox.y), summaryPosition }, null, 2)); await browser.close(); })().catch(err => { console.error(err); process.exit(1); });"
```

Expected output:

```json
{
  "navTop": 0,
  "summaryPosition": "static"
}
```

- [ ] **Step 4: Manually inspect the screenshots**

Verify:

- `Импорт`, `Планиране`, and `Технологични карти` are equal-width tabs.
- Active tab is visually obvious.
- `Към терминала` is on the right and not duplicated elsewhere.
- Card detail pages have card actions in a separate toolbar.
- No visible `Началник смяна` tag remains.
- Operational card internals still look like the prior implementation.
- `Общо произведено` does not stick over lower card sections while scrolling.

- [ ] **Step 5: Stop the local server**

Press `Ctrl+C` in the uvicorn shell.

---

## Task 11: Final Review

**Files:**
- Review all modified files.

- [ ] **Step 1: Review changed files**

Run:

```bash
git diff -- app/main.py app/templates/_admin_nav.html app/templates/admin_import.html app/templates/admin_planning.html app/templates/admin_cards.html app/templates/admin_card_detail.html app/static/css/app.css tests/test_admin_routes.py tests/test_admin_card_detail_redesign.py IMPLEMENTATION_PLAN.md
```

Expected review findings:

- No backend workflow logic changed.
- No operational-card internal section markup was restructured.
- Card actions are status-gated exactly as before.
- Print link remains available only for `completed` and `archived`.
- Archive action remains available only for `completed`.
- Cancel remains available only for `pending`, `running`, and `paused`.
- Restore remains available only for `cancelled`.

- [ ] **Step 2: Check worktree status**

Run:

```bash
git status --short
```

Expected result:

```text
modified files for this milestone are listed
existing unrelated user changes may still be listed
artifacts/ screenshots are untracked or ignored
```

- [ ] **Step 3: Prepare handoff summary**

Report:

- Files changed.
- Tests run and pass/fail result.
- Screenshot directory.
- Any known residual risk.
- Whether a commit was skipped because the user did not explicitly ask for one.

Do not stage or commit unless the user explicitly asks.

