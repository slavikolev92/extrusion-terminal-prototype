# Admin Planning Unreleased Queue Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up only the unreleased-card queue on `/admin/planning` so draft cards scan as compact single table rows with shared column headers, delivery date visibility, tighter input/action sizing, and non-AJAX scroll-preserving release redirects.

**Architecture:** Keep the app server-rendered and preserve existing release semantics. Make a small data-query addition for `delivery_date`, restructure only the unreleased table markup, add unreleased-table-specific CSS, and extend the release POST to redirect to a safe fragment anchor after successful PRG.

**Tech Stack:** Python 3.12, FastAPI, Jinja2 templates, direct `sqlite3`, pytest, repo-local `.venv`, Playwright CLI for UI screenshot verification.

---

## Mandatory Session Instructions

- Start by reading `/home/sk/projects/extrusion-terminal/AGENTS.md` and follow it.
- Use `superpowers:subagent-driven-development` to execute this plan: dispatch a fresh subagent per task, then run spec-compliance review and code-quality review after each task.
- Use `superpowers:using-git-worktrees` before implementation if starting feature work in an isolated workspace is needed by the active Superpowers workflow.
- Do not commit, stage, or revert files unless the user explicitly asks. This repository's `AGENTS.md` overrides generic Superpowers frequent-commit guidance.
- Keep scope limited to the unreleased-card queue section headed `Неизпратени технологични карти`.
- Do not change the `Опашки по машини` section behavior or layout in this plan.
- Do not add AJAX, frontend state management, new frameworks, sessions, flash-message systems, or client-side persistence.
- Do not mutate `data/extrusion_terminal.sqlite3` in tests or manual checks. Use temporary SQLite database paths.
- Use the repo-local Python virtualenv:

```bash
source .venv/bin/activate
```

- Use TDD for behavior changes: write focused tests first, run them to verify they fail for the expected reason, implement the minimal change, then re-run.
- Preserve existing release behavior:
  - release validates loaded card version;
  - release validates machine and sequence;
  - release converts `imported` cards to `pending`;
  - release inserts at target sequence and normalizes queues;
  - successful release uses PRG;
  - failed release renders `admin_planning.html` inline with `release_result`.

## Superpowers Execution Workflow Checked

The recommended Superpowers execution path for this plan is:

1. Read this plan once and extract every task with full task text.
2. Create a task checklist for the controller session.
3. For each task, dispatch a fresh implementer subagent with the full task text and only the context it needs.
4. If the implementer asks for context, answer the question with exact file paths, command output, or product constraints, then continue only after the implementer confirms it can proceed.
5. After implementation, dispatch a spec-compliance reviewer subagent.
6. If spec review finds gaps, send the implementer back to fix them, then repeat spec review.
7. After spec review passes, dispatch a code-quality reviewer subagent.
8. If code-quality review finds issues, send the implementer back to fix them, then repeat code-quality review.
9. Mark the task complete only after both review stages pass.
10. After all tasks, run a final review and verification pass.

Important adaptation for this repository: subagents must not commit even though generic Superpowers examples mention commits. The repo instruction says to stage or commit only when the user explicitly asks.

## Background

Audit report: `reports/full-workflow-audit-20260618.md`, issue #8, "Medium - Admin Planning UI Repeats Per-Row Field Labels And Looks Cluttered."

Observed current problem:

- In `app/templates/admin_planning.html`, draft release rows render a nested form inside one table cell.
- The labels `Макс. тегло ролка, кг`, `Ред`, and `Машина` repeat visibly for every unreleased card.
- The product/type field is too narrow relative to low-information fields.
- Max-roll-weight, sequence, machine, and send button consume too much width.
- After successful release, PRG redirects to `/admin/planning`, which returns the browser to the top of the page.

User-confirmed scope on 2026-06-19:

- Work only on the unreleased queue.
- Do not modify the machine queue section for now.
- Aim for each unreleased card to fit on one table row.
- Keep the no-AJAX recommendation and preserve simple server-rendered behavior.

Current relevant files:

- `app/templates/admin_planning.html`
  - unreleased queue table starts around line 47.
  - current draft release form starts around line 70.
  - machine queue section starts around line 101 and must remain functionally unchanged.
- `app/static/css/app.css`
  - current `.release-form`, `.release-field`, `.planning-form`, `.machine-grid`, and `.queue-card` styles are shared.
  - add new unreleased-table-specific classes instead of broadly changing machine queue styles.
- `app/db.py`
  - `fetch_cards_by_status()` currently does not select `delivery_date`.
  - `delivery_date` exists in the card schema and is selected by admin detail queries elsewhere.
- `app/main.py`
  - `release_card_to_terminal()` currently redirects successful releases to `/admin/planning`.
  - failed release still renders inline and must keep that behavior.
- `tests/test_admin_routes.py`
  - existing route tests cover planning render and release PRG.

## Required Behavior

Unreleased table layout:

- Replace the current nested labeled release form with table columns:
  - `Поръчка`
  - `Доставка`
  - `Клиент`
  - `Изделие`
  - `Макс. кг/ролка`
  - `Ред`
  - `Машина`
  - `Действие`
- Show one shared header row only.
- Do not show repeated visible labels for max roll weight, sequence, or machine in each row.
- Keep per-input `aria-label` values so controls remain understandable to assistive technology.
- Keep one release submission per card.
- Keep `loaded_version` for stale-write protection.
- Add a hidden `return_anchor` value so successful release can return near the user's current place.

Column sizing:

- `Изделие` gets the most horizontal space.
- `Макс. кг/ролка`, `Ред`, `Машина`, and `Действие` are compact.
- The send button is narrower than the current 180px button and right-aligned.
- The row should prefer a single line on normal desktop planning screens.
- Long customer/product text may truncate with ellipsis in the unreleased table to protect row height.

Delivery date:

- Add `delivery_date` to `fetch_cards_by_status()`.
- Render `card.delivery_date or "-"` immediately after the order number column.

Scroll-preserving PRG:

- Keep successful release as a `303` redirect.
- Add an optional `return_anchor` form field to the release route.
- Sanitize the anchor to allow only simple HTML id characters.
- On successful release, redirect to `/admin/planning#<safe-anchor>`.
- If no safe anchor is submitted, redirect to `/admin/planning#unreleased-queue`.
- Failed release must not redirect and must continue rendering inline with `release_result`.
- Use anchors in the unreleased table:
  - section id: `unreleased-queue`;
  - row id: `draft-card-{{ card.id }}`;
  - each row should submit `return_anchor` for the next draft row when one exists, otherwise `unreleased-queue`.

Out of scope:

- No machine queue redesign.
- No AJAX release.
- No bulk release.
- No sorting/filtering changes.
- No backend release semantics changes beyond redirect fragment support and selecting `delivery_date`.

## Files And Responsibilities

- Modify `tests/test_admin_routes.py`
  - Add render tests for the unreleased table columns and absence of repeated visible per-row labels.
  - Update release PRG test to pass and assert a safe return anchor.
  - Add a malicious-anchor test proving unsafe fragments are ignored.

- Modify `app/db.py`
  - Add `delivery_date` to `fetch_cards_by_status()` SELECT list.

- Modify `app/main.py`
  - Add a small anchor sanitizer helper.
  - Accept optional `return_anchor` in `release_card_to_terminal()`.
  - Redirect successful releases to `/admin/planning#<safe-anchor>`.

- Modify `app/templates/admin_planning.html`
  - Restructure only the unreleased table.
  - Add section/row ids and compact release controls.
  - Do not alter the machine queue loop other than incidental line movement caused by the unreleased section edit.

- Modify `app/static/css/app.css`
  - Add unreleased-table-specific classes.
  - Avoid changing `.planning-form`, `.machine-grid`, `.machine-column`, or `.queue-card` behavior.

- Optionally modify `IMPLEMENTATION_PLAN.md`
  - Only if implementation is completed in the same execution session, record this audit cleanup and verification under the current milestone/follow-up notes.

---

## Task 1: Add Failing Route/Render Tests For The Unreleased Queue

**Files:**

- Modify: `tests/test_admin_routes.py`

- [ ] **Step 1: Read focused test and template context**

Run:

```bash
sed -n '1,120p' tests/test_admin_routes.py
sed -n '180,330p' tests/test_admin_routes.py
sed -n '45,100p' app/templates/admin_planning.html
sed -n '330,372p' app/db.py
sed -n '510,538p' app/main.py
```

Expected:

- `import_route_card()`, `card_version()`, `admin_planning()`, and `release_card_to_terminal()` are already imported or available.
- The current unreleased table does not have a delivery column.
- The current route redirects to `/admin/planning` without an anchor.

- [ ] **Step 2: Add tests for compact unreleased table rendering**

In `tests/test_admin_routes.py`, after `test_admin_planning_renders_unreleased_cards_and_machine_options`, add:

```python
def test_admin_planning_renders_compact_unreleased_release_table(connection):
    result = import_cards_from_csv(
        "planning-compact-route.csv",
        csv_bytes(
            extrusion_row(
                "25902",
                delivery_date="2026-06-25",
                customer="Compact Customer",
                product_type="Long product type that should stay in the product column",
            ),
            extrusion_row(
                "25903",
                delivery_date="2026-06-26",
                customer="Second Compact Customer",
                product_type="Second product",
            ),
        ),
        overwrite_existing=False,
    )
    assert result.rows_imported == 2

    response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert '<section class="section" id="unreleased-queue">' in html
    assert "<th>Поръчка</th>" in html
    assert "<th>Доставка</th>" in html
    assert "<th>Клиент</th>" in html
    assert "<th>Изделие</th>" in html
    assert "<th>Макс. кг/ролка</th>" in html
    assert "<th>Ред</th>" in html
    assert "<th>Машина</th>" in html
    assert "<th>Действие</th>" in html
    assert "2026-06-25" in html
    assert "2026-06-26" in html
    assert 'id="draft-card-' in html
    assert 'class="unreleased-table compact-table"' in html
    assert 'class="release-control release-control-max-roll"' in html
    assert 'class="release-control release-control-sequence"' in html
    assert 'class="release-control release-control-machine"' in html
    assert 'class="release-submit-button"' in html
    assert '<span>Макс. тегло ролка, кг</span>' not in html
    assert '<span>Ред <span class="required-marker">*</span></span>' not in html
    assert '<span>Машина <span class="required-marker">*</span></span>' not in html
```

- [ ] **Step 3: Add release redirect anchor tests**

In `tests/test_admin_routes.py`, replace `test_successful_release_redirects_to_planning_get_and_refresh_does_not_resubmit` with this version:

```python
def test_successful_release_redirects_to_planning_anchor_and_refresh_does_not_resubmit(connection):
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
            return_anchor="draft-card-999",
        )
    )
    after_release = db.fetch_admin_card_detail(card_id)
    refresh_response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    after_refresh = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/planning#draft-card-999"
    assert refresh_response.status_code == 200
    assert after_release["status"] == "pending"
    assert after_release["machine_id"] == 1
    assert after_release["machine_sequence"] == 1
    assert after_refresh["version"] == after_release["version"]
    assert after_refresh["machine_id"] == 1
    assert after_refresh["machine_sequence"] == 1
```

Then add this test immediately after it:

```python
def test_successful_release_ignores_unsafe_return_anchor(connection):
    card_id = import_route_card("25913")
    loaded_version = card_version(card_id)

    response = asyncio.run(
        release_card_to_terminal(
            make_request(f"/admin/cards/{card_id}/release"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            max_roll_weight="60.0",
            machine_id="1",
            machine_sequence="1",
            return_anchor='draft-card-1" onclick="alert(1)',
        )
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/planning#unreleased-queue"
```

- [ ] **Step 4: Run the focused tests and verify expected failures**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_planning_renders_compact_unreleased_release_table tests/test_admin_routes.py::test_successful_release_redirects_to_planning_anchor_and_refresh_does_not_resubmit tests/test_admin_routes.py::test_successful_release_ignores_unsafe_return_anchor -q
```

Expected before implementation:

- The compact table test fails because `delivery_date`, `unreleased-table`, and compact control classes are not rendered yet.
- The release redirect tests fail because `release_card_to_terminal()` does not yet accept `return_anchor`.

Do not modify production code in this task.

---

## Task 2: Add Delivery Date Data And Scroll-Preserving Release Redirect

**Files:**

- Modify: `app/db.py`
- Modify: `app/main.py`
- Test: `tests/test_admin_routes.py`

- [ ] **Step 1: Add `delivery_date` to planning card rows**

In `app/db.py`, update `fetch_cards_by_status()` so the SELECT list includes `delivery_date` after `order_number`.

Change this fragment:

```python
            SELECT id, order_number, status, machine_id, machine_sequence,
                   customer, product_type, quantity_1, unit_1, quantity_2, unit_2,
```

to:

```python
            SELECT id, order_number, delivery_date, status, machine_id, machine_sequence,
                   customer, product_type, quantity_1, unit_1, quantity_2, unit_2,
```

- [ ] **Step 2: Add a safe fragment helper**

In `app/main.py`, near `INVALID_LOADED_VERSION_MESSAGE`, add:

```python
DEFAULT_PLANNING_ANCHOR = "unreleased-queue"
SAFE_ANCHOR_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
```

Near `admin_card_post_response()`, add:

```python
def safe_planning_anchor(anchor: str) -> str:
    candidate = anchor.strip()
    if SAFE_ANCHOR_PATTERN.fullmatch(candidate):
        return candidate
    return DEFAULT_PLANNING_ANCHOR
```

This uses the existing `re` import already present at the top of `app/main.py`.

- [ ] **Step 3: Accept `return_anchor` in release route**

In `app/main.py`, change the release route signature from:

```python
async def release_card_to_terminal(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    max_roll_weight: str = Form(""),
    machine_id: str = Form(...),
    machine_sequence: str = Form(...),
):
```

to:

```python
async def release_card_to_terminal(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    max_roll_weight: str = Form(""),
    machine_id: str = Form(...),
    machine_sequence: str = Form(...),
    return_anchor: str = Form(DEFAULT_PLANNING_ANCHOR),
):
```

Then change the success redirect from:

```python
    if release_result.ok:
        return RedirectResponse(url="/admin/planning", status_code=303)
```

to:

```python
    if release_result.ok:
        anchor = safe_planning_anchor(return_anchor)
        return RedirectResponse(url=f"/admin/planning#{anchor}", status_code=303)
```

- [ ] **Step 4: Run redirect/data tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_successful_release_redirects_to_planning_anchor_and_refresh_does_not_resubmit tests/test_admin_routes.py::test_successful_release_ignores_unsafe_return_anchor -q
```

Expected after this task:

- Both redirect tests pass.

The compact table render test can still fail until Task 3 updates the template and CSS.

---

## Task 3: Restructure Only The Unreleased Queue Template

**Files:**

- Modify: `app/templates/admin_planning.html`
- Test: `tests/test_admin_routes.py`

- [ ] **Step 1: Replace the unreleased section markup**

In `app/templates/admin_planning.html`, replace the current unreleased-card section from:

```jinja2
  <section class="section">
    <div class="section-head">
      <h2>Неизпратени технологични карти</h2>
      <span>{{ draft_cards|length }} карти</span>
    </div>

    {% if draft_cards %}
      <table>
        <thead>
          <tr>
            <th>Поръчка</th>
            <th>Клиент</th>
            <th>Изделие</th>
            <th>Изпрати</th>
          </tr>
        </thead>
        <tbody>
          {% for card in draft_cards %}
            <tr>
              <td><a href="/admin/cards/{{ card.id }}">{{ card.order_number }}</a></td>
              <td>{{ card.customer or "-" }}</td>
              <td>{{ card.product_type or "-" }}</td>
              <td>
                <form class="release-form" action="/admin/cards/{{ card.id }}/release" method="post">
                  <input type="hidden" name="loaded_version" value="{{ card.version }}">
                  <label class="release-field">
                    <span>Макс. тегло ролка, кг</span>
                    <input name="max_roll_weight" inputmode="decimal" value="{{ card.max_roll_weight or '' }}" aria-label="Максимално тегло ролка за поръчка {{ card.order_number }}">
                  </label>
                  <label class="release-field required-field">
                    <span>Ред <span class="required-marker">*</span></span>
                    <input name="machine_sequence" inputmode="numeric" pattern="[0-9]*" value="{{ card.machine_sequence or '' }}" aria-label="Ред за поръчка {{ card.order_number }}" required>
                  </label>
                  <label class="release-field required-field">
                    <span>Машина <span class="required-marker">*</span></span>
                    <select name="machine_id" aria-label="Машина за поръчка {{ card.order_number }}" required>
                      <option value="">Машина</option>
                      {% for machine in machines %}
                        <option value="{{ machine.id }}" {% if card.machine_id == machine.id %}selected{% endif %}>{{ machine.id }}</option>
                      {% endfor %}
                    </select>
                  </label>
                  <button type="submit">Изпрати</button>
                </form>
              </td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    {% else %}
      <p class="empty">Няма неизпратени технологични карти.</p>
    {% endif %}
  </section>
```

with:

```jinja2
  <section class="section" id="unreleased-queue">
    <div class="section-head">
      <h2>Неизпратени технологични карти</h2>
      <span>{{ draft_cards|length }} карти</span>
    </div>

    {% if draft_cards %}
      <table class="unreleased-table compact-table">
        <thead>
          <tr>
            <th class="col-order">Поръчка</th>
            <th class="col-delivery">Доставка</th>
            <th class="col-customer">Клиент</th>
            <th class="col-product">Изделие</th>
            <th class="col-max-roll">Макс. кг/ролка</th>
            <th class="col-sequence">Ред</th>
            <th class="col-machine">Машина</th>
            <th class="col-action">Действие</th>
          </tr>
        </thead>
        <tbody>
          {% for card in draft_cards %}
            {% set next_card = draft_cards[loop.index] if not loop.last else none %}
            {% set return_anchor = 'draft-card-' ~ next_card.id if next_card else 'unreleased-queue' %}
            <tr id="draft-card-{{ card.id }}">
              <td class="col-order"><a href="/admin/cards/{{ card.id }}">{{ card.order_number }}</a></td>
              <td class="col-delivery">{{ card.delivery_date or "-" }}</td>
              <td class="col-customer truncate-cell" title="{{ card.customer or '' }}">{{ card.customer or "-" }}</td>
              <td class="col-product truncate-cell" title="{{ card.product_type or '' }}">{{ card.product_type or "-" }}</td>
              <td class="col-max-roll">
                <form id="release-card-{{ card.id }}" action="/admin/cards/{{ card.id }}/release" method="post">
                  <input type="hidden" name="loaded_version" value="{{ card.version }}">
                  <input type="hidden" name="return_anchor" value="{{ return_anchor }}">
                </form>
                <input class="release-control release-control-max-roll" form="release-card-{{ card.id }}" name="max_roll_weight" inputmode="decimal" value="{{ card.max_roll_weight or '' }}" aria-label="Максимално тегло ролка за поръчка {{ card.order_number }}">
              </td>
              <td class="col-sequence">
                <input class="release-control release-control-sequence" form="release-card-{{ card.id }}" name="machine_sequence" inputmode="numeric" pattern="[0-9]*" value="{{ card.machine_sequence or '' }}" aria-label="Ред за поръчка {{ card.order_number }}" required>
              </td>
              <td class="col-machine">
                <select class="release-control release-control-machine" form="release-card-{{ card.id }}" name="machine_id" aria-label="Машина за поръчка {{ card.order_number }}" required>
                  <option value="">-</option>
                  {% for machine in machines %}
                    <option value="{{ machine.id }}" {% if card.machine_id == machine.id %}selected{% endif %}>{{ machine.id }}</option>
                  {% endfor %}
                </select>
              </td>
              <td class="col-action">
                <button class="release-submit-button" type="submit" form="release-card-{{ card.id }}">Изпрати</button>
              </td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    {% else %}
      <p class="empty">Няма неизпратени технологични карти.</p>
    {% endif %}
  </section>
```

Notes:

- This creates one form per draft card without nesting all controls inside one wide table cell.
- The hidden form intentionally lives in the max-roll cell. The visible controls submit to it via the HTML `form` attribute.
- `loop.index` is one-based in Jinja and can access the next item because Python lists are zero-based; for the first rendered card, `draft_cards[1]` is the second card.
- The machine queue section below this block must remain unchanged.

- [ ] **Step 2: Run the compact render test**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py::test_admin_planning_renders_compact_unreleased_release_table -q
```

Expected:

- The test passes after the template and Task 2 data change are present.

If Jinja rejects the inline `none` expression, replace:

```jinja2
{% set next_card = draft_cards[loop.index] if not loop.last else none %}
```

with:

```jinja2
{% if not loop.last %}
  {% set next_card = draft_cards[loop.index] %}
  {% set return_anchor = 'draft-card-' ~ next_card.id %}
{% else %}
  {% set return_anchor = 'unreleased-queue' %}
{% endif %}
```

and keep the rest of the row unchanged.

---

## Task 4: Add Scoped CSS For A Single-Line Unreleased Table

**Files:**

- Modify: `app/static/css/app.css`
- Test: Playwright screenshot in Task 5

- [ ] **Step 1: Add unreleased-table styles without changing machine queue styles**

In `app/static/css/app.css`, after the existing `select` rule and before `.release-form`, add:

```css
.unreleased-table {
  table-layout: fixed;
}

.unreleased-table th {
  white-space: nowrap;
}

.unreleased-table td {
  vertical-align: middle;
}

.unreleased-table .col-order {
  width: 86px;
}

.unreleased-table .col-delivery {
  width: 104px;
}

.unreleased-table .col-customer {
  width: 18%;
}

.unreleased-table .col-product {
  width: auto;
}

.unreleased-table .col-max-roll {
  width: 112px;
}

.unreleased-table .col-sequence {
  width: 66px;
}

.unreleased-table .col-machine {
  width: 78px;
}

.unreleased-table .col-action {
  width: 92px;
  text-align: right;
}

.truncate-cell {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.release-control {
  width: 100%;
  min-height: 34px;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  background: var(--surface);
  padding: 0 8px;
  font: inherit;
}

.release-control-sequence,
.release-control-machine {
  text-align: center;
}

.release-submit-button {
  min-height: 34px;
  width: auto;
  padding: 0 10px;
  white-space: nowrap;
}
```

- [ ] **Step 2: Add narrow-screen protection for the unreleased table**

Inside the existing `@media (max-width: 760px)` block, before the closing brace, add:

```css
  .unreleased-table {
    min-width: 880px;
  }

  #unreleased-queue {
    overflow-x: auto;
  }
```

Expected:

- On desktop, the table uses compact fixed columns.
- On narrow screens, the section scrolls horizontally instead of crushing controls into multi-line rows.

- [ ] **Step 3: Run CSS syntax/diff whitespace check**

Run:

```bash
git diff -- app/static/css/app.css
git diff --check
```

Expected:

- CSS changes are scoped to `.unreleased-table`, `.release-control`, `.release-submit-button`, `#unreleased-queue`.
- No whitespace errors.

---

## Task 5: Focused Verification And Playwright UI Evidence

**Files:**

- Generated artifacts only under `artifacts/ui-checks/admin-planning-unreleased-queue/`
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

Run this from the repo root:

```bash
mkdir -p .test-runtime/admin-planning-unreleased-queue artifacts/ui-checks/admin-planning-unreleased-queue
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/admin-planning-unreleased-queue/planning.sqlite3 python -c '
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
    "planning-ui.csv",
    csv_bytes(
        row("32501", "2026-06-25", "Пелети Пирин PELLITO", "ТСФ 890/0.082 - long product name for single-line check"),
        row("32502", "2026-06-26", "Балкан Фуудс", "Ръкав 600/0.050"),
        row("32503", "2026-06-27", "Тест Клиент София", "Плик 300/0.030"),
        row("32504", "2026-06-28", "Драфт Клиент", "Фолио 500/0.040"),
    ),
    overwrite_existing=False,
)
assert result.rows_imported == 4, result
print("seeded", result.rows_imported)
'
```

Expected:

- Output includes `seeded 4`.
- Database is under `.test-runtime/`, not under `data/`.

- [ ] **Step 4: Start the app against the temporary DB**

Run:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/admin-planning-unreleased-queue/planning.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8766
```

Expected:

- Uvicorn reports it is running on `http://127.0.0.1:8766`.

Keep this process running until screenshots are captured. Stop it with `Ctrl+C` after Step 6.

- [ ] **Step 5: Capture Playwright screenshot**

In a second shell, run:

```bash
npx playwright screenshot --viewport-size=1440,950 http://127.0.0.1:8766/admin/planning artifacts/ui-checks/admin-planning-unreleased-queue/unreleased-queue-cleanup.png
```

Expected:

- Screenshot is created.
- The unreleased table has one shared header row.
- Each draft card is visually one compact table row at 1440px width.
- `Доставка` appears after the order column.
- Product/type has more room than max roll weight, sequence, and machine.
- The send button is compact and right-aligned.
- The machine queue section remains in its existing card/column style.

- [ ] **Step 6: Manually verify scroll-preserving anchor**

With the temp app still running:

1. Open `http://127.0.0.1:8766/admin/planning`.
2. Enter:
   - max roll weight `60`;
   - sequence `1`;
   - machine `1`;
   - click `Изпрати` for the first unreleased row.
3. Confirm the browser URL has this form:

```text
http://127.0.0.1:8766/admin/planning#draft-card-2
```

or, when releasing the last draft row:

```text
http://127.0.0.1:8766/admin/planning#unreleased-queue
```

Expected:

- The page uses a GET after release.
- Browser refresh does not resubmit the release.
- The viewport returns near the unreleased queue instead of the top of the page.

Stop the Uvicorn server with `Ctrl+C`.

- [ ] **Step 7: Run final diff checks**

Run:

```bash
git diff --check
git status --short
```

Expected:

- `git diff --check` exits 0.
- `git status --short` shows only intentional tracked modifications and ignored/untracked artifacts under `artifacts/` or `.test-runtime/`.
- No files are staged.

---

## Task 6: Optional Milestone Note After Verified Implementation

**Files:**

- Modify: `IMPLEMENTATION_PLAN.md`

Only execute this task after Tasks 1 through 5 have passed. If the user wants code changes but no milestone note, skip this task and state that it was skipped by user preference.

- [ ] **Step 1: Add a concise audit-follow-up note**

In `IMPLEMENTATION_PLAN.md`, add a short completed bullet in the current milestone/follow-up area:

```markdown
- admin planning unreleased-queue cleanup: compact single-row release table, delivery-date column, scoped control sizing, and PRG anchor return after release.
```

- [ ] **Step 2: Verify plan note is scoped**

Run:

```bash
git diff -- IMPLEMENTATION_PLAN.md
```

Expected:

- The note mentions only the unreleased queue cleanup.
- It does not claim machine queue redesign.
- It does not claim AJAX behavior.

---

## Final Verification Checklist

Before reporting completion, run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py tests/test_admin_planning.py
python -m pytest
git diff --check
```

Also confirm one Playwright screenshot exists:

```bash
ls -l artifacts/ui-checks/admin-planning-unreleased-queue/unreleased-queue-cleanup.png
```

Report:

- tests run and pass/fail status;
- screenshot path;
- whether the temp server was stopped;
- whether `IMPLEMENTATION_PLAN.md` was updated or intentionally skipped;
- any pre-existing dirty worktree files that were not part of this task.

## Copy/Paste Execution Prompt

Use this prompt in a new session or later turn:

```text
Execute the plan at /home/sk/projects/extrusion-terminal/docs/superpowers/plans/2026-06-19-admin-planning-unreleased-queue-cleanup.md using the Superpowers plugin's subagent-driven development workflow.

Requirements:
- First read AGENTS.md and the plan file.
- Use superpowers:subagent-driven-development exactly as recommended: fresh implementer subagent per task, then spec-compliance review and code-quality review after each task, with fixes and re-review before moving on.
- Do not commit, stage, or revert files unless I explicitly ask.
- Keep scope limited to the unreleased queue on /admin/planning; do not redesign or change the machine queue section.
- Keep the implementation server-rendered and avoid AJAX.
- Run the verification commands from the plan, capture the Playwright screenshot, stop any temp server you start, and report results.
```
