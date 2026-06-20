# Pending Card Unrelease Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix audit issue #7 by allowing shift managers to return a released-but-not-started `pending` card from the terminal queue back to the unreleased planning pool, without using cancellation.

**Architecture:** Add one backend transition from `pending` to `imported` that clears machine assignment and queue sequence, preserves all card data, and normalizes the old machine queue. Expose that transition through admin planning and admin card detail with the same loaded-version conflict checks and PRG behavior used by existing admin mutations.

**Tech Stack:** Python 3.12, FastAPI, Jinja templates, direct `sqlite3`, SQLite partial indexes, pytest, repo-local `.venv`, Playwright for final UI verification when templates change.

---

## Mandatory Session Instructions

- Start by reading `/home/sk/projects/extrusion-terminal/AGENTS.md` and follow it.
- Use `superpowers:subagent-driven-development` to execute this plan: dispatch a fresh subagent per task, then run spec-compliance review and code-quality review after each task.
- Do not commit unless the user explicitly asks. This repository's `AGENTS.md` overrides the generic SuperPowers frequent-commit guidance.
- Do not implement audit issue #8 planning UI cleanup in this branch.
- Do not change print output behavior.
- Do not add users, roles, sessions, flash-message frameworks, background jobs, or client-side state.
- Do not mutate `data/extrusion_terminal.sqlite3` in tests. Automated tests must use temporary SQLite database paths.
- Use the repo-local Python virtualenv:

```bash
source .venv/bin/activate
```

- Use TDD for each code task: add the focused failing tests first, run them to verify they fail for the expected reason, then implement the minimal production change.
- Preserve existing stale-write behavior. Every unrelease form must include `loaded_version`; stale writes must warn and require reload.
- Preserve existing queue invariants:
  - active machine queues normalize to contiguous sequence positions starting at `1`;
  - duplicate active sequence numbers for one machine remain impossible;
  - terminal-visible active cards remain `pending`, `running`, or `paused`.

## Branch Preflight

Before editing code, run:

```bash
git status --short --branch
git log --oneline --decorate -n 8
```

Expected:

- The working tree has no unrelated modified files that would be overwritten by this work.
- If there are unrelated local changes, leave them alone.
- Create a focused branch from the current accepted integration branch:

```bash
git switch -c audit-fix-pending-card-unrelease
```

If `git switch -c` fails because the branch already exists, stop and inspect:

```bash
git status --short --branch
git branch --list audit-fix-pending-card-unrelease
```

Continue on the existing branch only if it is clearly the branch for this exact issue.

## Background

Audit report: `reports/full-workflow-audit-20260618.md`, issue #7, "High - Released Cards Cannot Be Returned To The Unreleased Planning Pool."

Observed problem:

1. A shift manager imports a card.
2. The shift manager releases it to a machine queue.
3. The card becomes `pending` and appears on `/terminal`.
4. If the shift manager decides the card should not be produced yet, the only current admin state-change option is cancellation.
5. Cancellation is semantically wrong for "do this later"; it marks the card as cancelled instead of returning it to the unreleased planning pool.

Confirmed desired behavior from the user on 2026-06-19:

- Only `pending` cards can be returned to the unreleased planning pool.
- If a card is started in any way, including `running` or `paused`, it stays in execution and cannot be returned to the pool.
- `completed`, `cancelled`, and already-`imported` cards cannot use this transition.

Current relevant behavior:

- `app/constants.py` defines:

```python
STATUS_IMPORTED = "imported"
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
```

- `app/db.py::release_card()` moves `imported` to `pending`, assigns `machine_id`, assigns a target `machine_sequence`, and normalizes the queue.
- `app/db.py::update_card_planning()` moves active cards between machine queues and normalizes queues.
- `app/db.py::normalize_machine_queue()` already rewrites active machine sequences safely.
- `app/db.py` has a partial unique index:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_active_machine_sequence
ON cards(machine_id, machine_sequence)
WHERE status IN ('pending', 'running', 'paused')
  AND machine_id IS NOT NULL
  AND machine_sequence IS NOT NULL;
```

- `app/main.py` has admin routes for release, planning, cancel, and restore, but no unrelease route.
- `app/templates/admin_planning.html` shows active machine queue cards but no "return to pool" control.
- `app/templates/admin_card_detail.html` shows cancel/restore controls but no "return to pool" control.

## Required Behavior

Backend transition:

- Add `db.unrelease_pending_card(card_id: int, loaded_version: int) -> RuleResult`.
- It must load the card by `id` and validate `loaded_version` using `validate_loaded_card_version()`.
- It must allow only `status == STATUS_PENDING`.
- On success it must:
  - set `status = STATUS_IMPORTED`;
  - set `machine_id = NULL`;
  - set `machine_sequence = NULL`;
  - increment `version`;
  - update `updated_at`;
  - preserve imported/front-card fields;
  - preserve `max_roll_weight`;
  - preserve any existing production-side fields if present;
  - normalize the old machine queue after removing the card.
- It must not delete rolls, timing segments, recipe actual entries, import source rows, or import batch history.
- It must return a Bulgarian success message naming the order number.
- It must return a Bulgarian validation message for non-pending statuses.

Admin route and UI:

- Add POST route `/admin/cards/{card_id}/unrelease`.
- The route must parse `loaded_version` using the existing `parse_loaded_version()` helper.
- The route must accept a hidden `return_to` field:
  - `return_to=planning` means success redirects to `/admin/planning`; failures render `admin_planning.html` inline with `planning_result`.
  - `return_to=detail` means success redirects to `/admin/cards/{card_id}`; failures render `admin_card_detail.html` inline with `workflow_result`.
  - any other value is treated as `planning`.
- Add an unrelease control on `/admin/planning` for active queue cards with `status == "pending"` only.
- Add an unrelease control on `/admin/cards/{card_id}` for `status == "pending"` only.
- Keep cancel available as a separate admin action; returning to pool is not cancellation.

Terminal behavior:

- After unrelease, the card must disappear from terminal active queues and `/terminal/snapshot`.
- If the terminal had that card selected, the snapshot should mark it as missing using existing snapshot behavior.
- No new terminal route or terminal action should be added.

Documentation:

- Update `README.md` lifecycle/admin behavior to describe pending-only return-to-pool behavior.
- Update `IMPLEMENTATION_PLAN.md` to record this audit follow-up after implementation and verification.

## Files And Responsibilities

- Modify `app/db.py`
  - Add `unrelease_pending_card()`.
  - Reuse `validate_loaded_card_version()` and `normalize_machine_queue()`.
  - Do not change `release_card()`, `update_card_planning()`, cancellation, or restore semantics except where imports are needed.

- Modify `app/main.py`
  - Import `unrelease_pending_card`.
  - Register `POST /admin/cards/{card_id}/unrelease`.
  - Keep PRG for successful unrelease actions.
  - Render inline errors on the correct admin page based on `return_to`.

- Modify `app/templates/admin_planning.html`
  - Add a `pending`-only return-to-pool form to each queue card.
  - Include hidden `loaded_version` and `return_to=planning`.

- Modify `app/templates/admin_card_detail.html`
  - Add a `pending`-only return-to-pool form in the header actions.
  - Include hidden `loaded_version` and `return_to=detail`.
  - Leave cancel/restore behavior intact.

- Modify `tests/test_admin_planning.py`
  - Add backend tests for successful unrelease, queue normalization, stale write blocking, and non-pending blocking.

- Modify `tests/test_admin_routes.py`
  - Add route registration and route-level PRG/error tests.
  - Add render tests for the planning and detail forms.

- Modify `tests/test_terminal_sync.py`
  - Add snapshot coverage proving unrelease removes a selected card from terminal visibility through the existing missing-card behavior.

- Modify `README.md`
  - Document the pending-only return-to-pool behavior.

- Modify `IMPLEMENTATION_PLAN.md`
  - Record the implemented audit follow-up and verification results.

---

## Task 1: Backend Unrelease Rule

**Files:**

- Modify: `tests/test_admin_planning.py`
- Modify: `app/db.py`

- [ ] **Step 1: Read focused backend context**

Run:

```bash
cat AGENTS.md
sed -n '368,410p' reports/full-workflow-audit-20260618.md
sed -n '1,80p' app/constants.py
sed -n '886,980p;2719,2898p;2900,2982p' app/db.py
sed -n '1,280p' tests/test_admin_planning.py
```

Expected:

- Audit issue #7 confirms no unrelease route exists.
- `restore_cancelled_card()` is not the right semantic model because it returns cancelled cards to `pending`.
- `release_card()` is the inverse reference: `imported` to `pending` with machine assignment.
- `normalize_machine_queue()` can close gaps after the pending card is removed.

- [ ] **Step 2: Import required statuses in planning tests**

In `tests/test_admin_planning.py`, change the constants import from:

```python
from app.constants import STATUS_PENDING, STATUS_RUNNING
```

to:

```python
from app.constants import STATUS_IMPORTED, STATUS_PAUSED, STATUS_PENDING, STATUS_RUNNING
```

- [ ] **Step 3: Add failing backend tests**

Append these tests to `tests/test_admin_planning.py`:

```python
def test_unrelease_pending_card_returns_it_to_unreleased_pool_and_preserves_data(connection):
    card_id = release_ready_card("25820", machine_id=2, machine_sequence=1)
    before = db.fetch_admin_card_detail(card_id)
    assert before["status"] == STATUS_PENDING
    assert before["machine_id"] == 2
    assert before["machine_sequence"] == 1
    assert before["max_roll_weight"] == "60.0"

    result = db.unrelease_pending_card(card_id, card_version(card_id))
    after = db.fetch_admin_card_detail(card_id)
    draft_cards = db.fetch_cards_by_status((STATUS_IMPORTED,))
    queues = db.fetch_machine_queues()

    assert result.ok
    assert result.messages == ("Поръчка 25820 е върната в неизпратени технологични карти.",)
    assert after["status"] == STATUS_IMPORTED
    assert after["machine_id"] is None
    assert after["machine_sequence"] is None
    assert after["max_roll_weight"] == "60.0"
    assert after["customer"] == before["customer"]
    assert after["raw_material_a"] == before["raw_material_a"]
    assert after["version"] == before["version"] + 1
    assert card_id in {card["id"] for card in draft_cards}
    assert all(
        card["id"] != card_id
        for queue in queues
        for card in queue["cards"]
    )


def test_unrelease_pending_card_normalizes_old_machine_queue(connection):
    first_id = release_ready_card("25821", machine_id=1, machine_sequence=1)
    removed_id = release_ready_card("25822", machine_id=1, machine_sequence=2)
    third_id = release_ready_card("25823", machine_id=1, machine_sequence=3)

    result = db.unrelease_pending_card(removed_id, card_version(removed_id))

    first = db.fetch_admin_card_detail(first_id)
    removed = db.fetch_admin_card_detail(removed_id)
    third = db.fetch_admin_card_detail(third_id)
    machine_1_cards = [
        (card["order_number"], card["machine_sequence"])
        for queue in db.fetch_machine_queues()
        if queue["machine"]["id"] == 1
        for card in queue["cards"]
    ]

    assert result.ok
    assert first["status"] == STATUS_PENDING
    assert first["machine_sequence"] == 1
    assert removed["status"] == STATUS_IMPORTED
    assert removed["machine_id"] is None
    assert removed["machine_sequence"] is None
    assert third["status"] == STATUS_PENDING
    assert third["machine_sequence"] == 2
    assert machine_1_cards == [("25821", 1), ("25823", 2)]


def test_unrelease_pending_card_blocks_stale_loaded_version(connection):
    card_id = release_ready_card("25824", machine_id=3, machine_sequence=1)
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.25").ok

    result = db.unrelease_pending_card(card_id, loaded_version)
    card = db.fetch_admin_card_detail(card_id)

    assert not result.ok
    assert result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert card["status"] == STATUS_PENDING
    assert card["machine_id"] == 3
    assert card["machine_sequence"] == 1


def test_unrelease_blocks_running_and_paused_cards(connection):
    running_id = release_ready_card("25825", machine_id=4, machine_sequence=1)
    paused_id = release_ready_card("25826", machine_id=4, machine_sequence=2)
    assert db.start_production_timing(paused_id, card_version(paused_id)).ok
    assert db.pause_production_timing(paused_id, card_version(paused_id)).ok
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    running_result = db.unrelease_pending_card(running_id, card_version(running_id))
    paused_result = db.unrelease_pending_card(paused_id, card_version(paused_id))
    running = db.fetch_admin_card_detail(running_id)
    paused = db.fetch_admin_card_detail(paused_id)

    assert not running_result.ok
    assert running_result.messages == (
        "Само изчакващи технологични карти могат да се връщат за планиране.",
    )
    assert not paused_result.ok
    assert paused_result.messages == (
        "Само изчакващи технологични карти могат да се връщат за планиране.",
    )
    assert running["status"] == STATUS_RUNNING
    assert running["machine_id"] == 4
    assert running["machine_sequence"] == 1
    assert paused["status"] == STATUS_PAUSED
    assert paused["machine_id"] == 4
    assert paused["machine_sequence"] == 2


def test_unrelease_blocks_imported_completed_and_cancelled_cards(connection):
    imported_id = import_ready_card("25827")
    completed_id = release_ready_card("25828", machine_id=2, machine_sequence=1)
    cancelled_id = release_ready_card("25829", machine_id=2, machine_sequence=2)
    assert db.start_production_timing(completed_id, card_version(completed_id)).ok
    assert db.update_tare_weight(completed_id, card_version(completed_id), "1.00").ok
    assert db.add_roll_gross_weight(completed_id, card_version(completed_id), "20.00").ok
    assert db.finish_card(completed_id, card_version(completed_id)).ok
    assert db.cancel_card(cancelled_id, card_version(cancelled_id)).ok

    imported_result = db.unrelease_pending_card(imported_id, card_version(imported_id))
    completed_result = db.unrelease_pending_card(completed_id, card_version(completed_id))
    cancelled_result = db.unrelease_pending_card(cancelled_id, card_version(cancelled_id))

    assert not imported_result.ok
    assert imported_result.messages == (
        "Само изчакващи технологични карти могат да се връщат за планиране.",
    )
    assert not completed_result.ok
    assert completed_result.messages == (
        "Само изчакващи технологични карти могат да се връщат за планиране.",
    )
    assert not cancelled_result.ok
    assert cancelled_result.messages == (
        "Само изчакващи технологични карти могат да се връщат за планиране.",
    )
    assert db.fetch_admin_card_detail(imported_id)["status"] == STATUS_IMPORTED
    assert db.fetch_admin_card_detail(completed_id)["status"] == "completed"
    assert db.fetch_admin_card_detail(cancelled_id)["status"] == "cancelled"
```

- [ ] **Step 4: Run the new backend tests and verify the expected failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_planning.py -k unrelease -q
```

Expected before implementation:

- Tests fail with `AttributeError: module 'app.db' has no attribute 'unrelease_pending_card'`.

- [ ] **Step 5: Implement `unrelease_pending_card()` in `app/db.py`**

Add this function immediately after `restore_cancelled_card()`:

```python
def unrelease_pending_card(card_id: int, loaded_version: int) -> RuleResult:
    with connect() as connection:
        card = connection.execute(
            """
            SELECT id, order_number, status, machine_id, machine_sequence, version
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        if card["status"] != STATUS_PENDING:
            return RuleResult(
                False,
                ("Само изчакващи технологични карти могат да се връщат за планиране.",),
            )

        old_machine_id = int(card["machine_id"]) if card["machine_id"] is not None else None
        connection.execute(
            """
            UPDATE cards
            SET status = ?,
                machine_id = NULL,
                machine_sequence = NULL,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (STATUS_IMPORTED, card_id),
        )
        if old_machine_id is not None:
            normalize_machine_queue(connection, machine_id=old_machine_id)

    return RuleResult(
        True,
        (f"Поръчка {card['order_number']} е върната в неизпратени технологични карти.",),
    )
```

Do not add roll/timing/material deletion.

- [ ] **Step 6: Run the backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_planning.py -k unrelease -q
```

Expected:

- All new `unrelease` tests pass.

- [ ] **Step 7: Run the broader planning and timing tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_planning.py tests/test_production_timing.py -q
```

Expected:

- All selected tests pass.

## Task 2: Admin Route And Route-Level Tests

**Files:**

- Modify: `tests/test_admin_routes.py`
- Modify: `app/main.py`

- [ ] **Step 1: Read focused route context**

Run:

```bash
sed -n '1,80p;140,190p;500,610p;880,930p;1160,1185p' app/main.py
sed -n '1,340p' tests/test_admin_routes.py
```

Expected:

- `app/main.py` imports DB helpers individually.
- Successful release and planning POSTs already redirect to `/admin/planning`.
- `admin_card_post_response()` redirects successful detail actions to `/admin/cards/{card_id}`.
- `parse_loaded_version()` already returns a `RuleResult` for invalid loaded versions.

- [ ] **Step 2: Update route test imports**

In `tests/test_admin_routes.py`, add `unrelease_admin_card` to the `from app.main import (...)` import list:

```python
from app.main import (
    admin,
    admin_card_detail,
    admin_import,
    admin_planning,
    app,
    import_csv as post_admin_import,
    release_card_to_terminal,
    unrelease_admin_card,
    update_admin_card_planning,
)
```

- [ ] **Step 3: Add route registration assertion**

In `test_admin_routes_are_registered()`, add:

```python
    assert "/admin/cards/{card_id}/unrelease" in route_paths
```

Place it near the existing release/planning/cancel/restore route assertions.

- [ ] **Step 4: Add failing route tests**

Append these tests to `tests/test_admin_routes.py`:

```python
def test_successful_unrelease_from_planning_redirects_to_planning_get_and_refresh_does_not_resubmit(connection):
    card_id = import_route_card("25920")
    assert db.release_card(
        card_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    loaded_version = card_version(card_id)

    response = asyncio.run(
        unrelease_admin_card(
            make_request(f"/admin/cards/{card_id}/unrelease"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            return_to="planning",
        )
    )
    after_unrelease = db.fetch_admin_card_detail(card_id)
    refresh_response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    after_refresh = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/planning"
    assert refresh_response.status_code == 200
    assert after_unrelease["status"] == "imported"
    assert after_unrelease["machine_id"] is None
    assert after_unrelease["machine_sequence"] is None
    assert after_refresh["version"] == after_unrelease["version"]
    assert after_refresh["status"] == "imported"


def test_successful_unrelease_from_detail_redirects_to_card_detail(connection):
    card_id = import_route_card("25921")
    assert db.release_card(
        card_id,
        machine_id=2,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    loaded_version = card_version(card_id)

    response = asyncio.run(
        unrelease_admin_card(
            make_request(f"/admin/cards/{card_id}/unrelease"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            return_to="detail",
        )
    )
    card = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/cards/{card_id}"
    assert card["status"] == "imported"
    assert card["machine_id"] is None
    assert card["machine_sequence"] is None


def test_failed_unrelease_from_planning_renders_planning_inline(connection):
    card_id = import_route_card("25922")
    assert db.release_card(
        card_id,
        machine_id=3,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    loaded_version = card_version(card_id)
    assert db.update_tare_weight(card_id, loaded_version, "1.25").ok

    response = asyncio.run(
        unrelease_admin_card(
            make_request(f"/admin/cards/{card_id}/unrelease"),
            card_id=card_id,
            loaded_version=str(loaded_version),
            return_to="planning",
        )
    )
    card = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 200
    assert "location" not in response.headers
    assert "planning_result" in response.context
    assert response.context["planning_result"].messages == (db.STALE_CARD_MESSAGE,)
    assert card["status"] == "pending"
    assert card["machine_id"] == 3
    assert card["machine_sequence"] == 1


def test_failed_unrelease_from_detail_renders_detail_inline(connection):
    card_id = import_route_card("25923")
    assert db.release_card(
        card_id,
        machine_id=4,
        machine_sequence=1,
        loaded_version=card_version(card_id),
        max_roll_weight="60.0",
    ).ok
    loaded_version = card_version(card_id)
    assert db.start_production_timing(card_id, loaded_version).ok

    response = asyncio.run(
        unrelease_admin_card(
            make_request(f"/admin/cards/{card_id}/unrelease"),
            card_id=card_id,
            loaded_version=str(card_version(card_id)),
            return_to="detail",
        )
    )
    card = db.fetch_admin_card_detail(card_id)

    assert response.status_code == 200
    assert "location" not in response.headers
    assert "workflow_result" in response.context
    assert response.context["workflow_result"].messages == (
        "Само изчакващи технологични карти могат да се връщат за планиране.",
    )
    assert card["status"] == "running"
    assert card["machine_id"] == 4
    assert card["machine_sequence"] == 1
```

- [ ] **Step 5: Run route tests and verify expected failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -k "unrelease or routes_are_registered" -q
```

Expected before implementation:

- Import fails or tests fail because `unrelease_admin_card` and `/admin/cards/{card_id}/unrelease` do not exist.

- [ ] **Step 6: Import the DB helper in `app/main.py`**

In the `from .db import (...)` block in `app/main.py`, add:

```python
    unrelease_pending_card,
```

Place it near `restore_cancelled_card` and other workflow helpers.

- [ ] **Step 7: Add the route in `app/main.py`**

Add this route immediately after `update_admin_card_planning()` and before `cancel_admin_card()`:

```python
@app.post("/admin/cards/{card_id}/unrelease")
async def unrelease_admin_card(
    request: Request,
    card_id: int,
    loaded_version: str = Form(...),
    return_to: str = Form("planning"),
):
    parsed_version, workflow_result = parse_loaded_version(loaded_version)
    if parsed_version is not None:
        workflow_result = unrelease_pending_card(card_id, parsed_version)

    if return_to == "detail":
        return admin_card_post_response(
            request,
            card_id,
            "workflow_result",
            workflow_result,
        )

    if workflow_result.ok:
        return RedirectResponse(url="/admin/planning", status_code=303)

    return templates.TemplateResponse(
        request,
        "admin_planning.html",
        admin_planning_context(planning_result=workflow_result),
    )
```

- [ ] **Step 8: Run route tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -k "unrelease or routes_are_registered" -q
```

Expected:

- The selected route tests pass.

- [ ] **Step 9: Run broader admin route/planning tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py tests/test_admin_planning.py -q
```

Expected:

- All selected tests pass.

## Task 3: Admin Planning And Detail UI

**Files:**

- Modify: `tests/test_admin_routes.py`
- Modify: `app/templates/admin_planning.html`
- Modify: `app/templates/admin_card_detail.html`

- [ ] **Step 1: Read focused template context**

Run:

```bash
sed -n '1,150p' app/templates/admin_planning.html
sed -n '1,70p' app/templates/admin_card_detail.html
sed -n '170,260p' tests/test_admin_routes.py
```

Expected:

- Admin planning queue cards render one planning form per active card.
- Admin detail header renders cancel for `pending`, `running`, and `paused`.
- There is no unrelease form in either template.

- [ ] **Step 2: Add failing render tests**

Append these tests to `tests/test_admin_routes.py`:

```python
def test_admin_planning_renders_unrelease_form_for_pending_queue_cards_only(connection):
    pending_id = import_route_card("25924")
    running_id = import_route_card("25925")
    assert db.release_card(
        pending_id,
        machine_id=1,
        machine_sequence=1,
        loaded_version=card_version(pending_id),
        max_roll_weight="60.0",
    ).ok
    assert db.release_card(
        running_id,
        machine_id=1,
        machine_sequence=2,
        loaded_version=card_version(running_id),
        max_roll_weight="60.0",
    ).ok
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    response = asyncio.run(admin_planning(make_request("/admin/planning", method="GET")))
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert f'action="/admin/cards/{pending_id}/unrelease"' in html
    assert f'action="/admin/cards/{running_id}/unrelease"' not in html
    assert '<input type="hidden" name="return_to" value="planning">' in html
    assert "Върни в неизпратени" in html


def test_admin_detail_renders_unrelease_form_for_pending_card_only(connection):
    pending_id = import_route_card("25926")
    running_id = import_route_card("25927")
    imported_id = import_route_card("25928")
    assert db.release_card(
        pending_id,
        machine_id=2,
        machine_sequence=1,
        loaded_version=card_version(pending_id),
        max_roll_weight="60.0",
    ).ok
    assert db.release_card(
        running_id,
        machine_id=2,
        machine_sequence=2,
        loaded_version=card_version(running_id),
        max_roll_weight="60.0",
    ).ok
    assert db.start_production_timing(running_id, card_version(running_id)).ok

    pending_response = asyncio.run(
        admin_card_detail(make_request(f"/admin/cards/{pending_id}", method="GET"), pending_id)
    )
    running_response = asyncio.run(
        admin_card_detail(make_request(f"/admin/cards/{running_id}", method="GET"), running_id)
    )
    imported_response = asyncio.run(
        admin_card_detail(make_request(f"/admin/cards/{imported_id}", method="GET"), imported_id)
    )

    pending_html = pending_response.body.decode("utf-8")
    running_html = running_response.body.decode("utf-8")
    imported_html = imported_response.body.decode("utf-8")

    assert f'action="/admin/cards/{pending_id}/unrelease"' in pending_html
    assert '<input type="hidden" name="return_to" value="detail">' in pending_html
    assert "Върни в планиране" in pending_html
    assert f'action="/admin/cards/{running_id}/unrelease"' not in running_html
    assert f'action="/admin/cards/{imported_id}/unrelease"' not in imported_html
```

- [ ] **Step 3: Run render tests and verify expected failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -k "renders_unrelease" -q
```

Expected before template changes:

- Tests fail because the unrelease forms are absent.

- [ ] **Step 4: Add the planning-page unrelease form**

In `app/templates/admin_planning.html`, inside each `queue-card`, after the existing `<form class="planning-form" ...>` block and before `</div>` for the queue card, add:

```html
                {% if card.status == "pending" %}
                  <form class="planning-form" action="/admin/cards/{{ card.id }}/unrelease" method="post">
                    <input type="hidden" name="loaded_version" value="{{ card.version }}">
                    <input type="hidden" name="return_to" value="planning">
                    <button type="submit">Върни в неизпратени</button>
                  </form>
                {% endif %}
```

Do not nest this form inside the existing planning form.

- [ ] **Step 5: Add the detail-page unrelease form**

In `app/templates/admin_card_detail.html`, inside `<div class="actions">`, after the print link block and before the existing cancel/restore conditional, add:

```html
      {% if card.status == "pending" %}
        <form action="/admin/cards/{{ card.id }}/unrelease" method="post">
          <input type="hidden" name="loaded_version" value="{{ card.version }}">
          <input type="hidden" name="return_to" value="detail">
          <button type="submit">Върни в планиране</button>
        </form>
      {% endif %}
```

Leave the existing cancellation form in place for `pending`, `running`, and `paused`.

- [ ] **Step 6: Run render and route tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_routes.py -q
```

Expected:

- All admin route tests pass.

## Task 4: Terminal Snapshot Visibility

**Files:**

- Modify: `tests/test_terminal_sync.py`

- [ ] **Step 1: Read terminal snapshot context**

Run:

```bash
sed -n '1,180p' tests/test_terminal_sync.py
sed -n '420,470p;1660,1710p' app/db.py
```

Expected:

- Existing snapshot behavior marks selected cards missing when they are no longer terminal-visible.
- Existing tests manually update a card to `imported`; this task replaces that implicit scenario with the real unrelease helper.

- [ ] **Step 2: Add terminal snapshot regression test**

Append this test to `tests/test_terminal_sync.py`:

```python
def test_terminal_snapshot_marks_unreleased_selected_card_missing(connection):
    card_id = release_ready_card("25908", machine_id=2, machine_sequence=1)
    before = db.terminal_snapshot(selected_card_id=card_id)

    result = db.unrelease_pending_card(card_id, card_version(card_id))
    after = db.terminal_snapshot(selected_card_id=card_id)

    assert result.ok
    assert before["selected_card"]["id"] == card_id
    assert before["selected_card"]["status"] == "pending"
    assert after["selected_card"] is None
    assert after["selected_card_missing"] is True
    assert card_id not in {card["id"] for card in after["active_cards"]}
    assert f"missing:{card_id}" in after["signature"]
```

- [ ] **Step 3: Run terminal sync tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_sync.py -q
```

Expected:

- All terminal sync tests pass.

## Task 5: Documentation And Milestone Tracker

**Files:**

- Modify: `README.md`
- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Read current docs context**

Run:

```bash
sed -n '84,112p;288,314p;900,922p' README.md
sed -n '326,420p' IMPLEMENTATION_PLAN.md
```

Expected:

- README lifecycle describes `imported`, `pending`, `running`, `paused`, `completed`, and `cancelled`.
- Admin behavior does not yet mention pending-only return to planning.
- Implementation plan currently records Milestone 10 print output and Milestone 11 pilot rehearsal.

- [ ] **Step 2: Update README lifecycle**

In `README.md`, replace the `pending` lifecycle row:

```markdown
| `pending` | Order/card has been released by the shift manager and is visible in the terminal queue, but production timing is not currently running. |
```

with:

```markdown
| `pending` | Order/card has been released by the shift manager and is visible in the terminal queue, but production timing has not started. A pending card can be returned to the unreleased planning pool by the shift manager. |
```

- [ ] **Step 3: Update README admin behavior**

In the "Admin page behavior" list, after:

```markdown
- The shift manager can cancel and restore terminal-visible cards from the admin card detail page.
```

add:

```markdown
- The shift manager can return a `pending` card to the unreleased planning pool. This clears machine assignment and queue position, removes the card from the terminal queue, and is only allowed before production has started. `running`, `paused`, `completed`, and `cancelled` cards cannot be returned to the pool.
```

- [ ] **Step 4: Update README planning rules**

In the planning rules list, after:

```markdown
- Release/submit can be one draft at a time. Do not add bulk release unless it becomes clearly necessary.
```

add:

```markdown
- Returning a pending card to the unreleased pool is the inverse of release for scheduling mistakes or deferment. It must not be used after timing starts; cancellation remains the separate action for truly cancelled work.
```

- [ ] **Step 5: Update IMPLEMENTATION_PLAN.md**

In `IMPLEMENTATION_PLAN.md`, add this bullet under `## Milestone 11 - Pilot Rehearsal`, before `Scope:`:

```markdown
Audit follow-up before rehearsal:

- Add pending-card return-to-planning behavior from full workflow audit issue #7: pending cards can be returned to the unreleased planning pool with version checks, queue normalization, terminal removal, and admin planning/detail controls. Started cards (`running` or `paused`) remain in execution and cannot be returned to the pool.
```

After implementation and verification, update the same section with the verification commands actually run and whether they passed.

- [ ] **Step 6: Run documentation diff review**

Run:

```bash
git diff -- README.md IMPLEMENTATION_PLAN.md
```

Expected:

- Docs mention only pending-only return-to-planning behavior.
- Docs do not claim issue #8 planning UI cleanup or physical printer rehearsal is complete.

## Task 6: Final Verification And UI Check

**Files:**

- No required source edits unless verification finds a defect.
- Create ignored artifacts only under `artifacts/ui-checks/`.

- [ ] **Step 1: Run focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_planning.py tests/test_admin_routes.py tests/test_terminal_sync.py -q
```

Expected:

- All selected tests pass.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected:

- Full suite passes.

- [ ] **Step 3: Run syntax/import check**

Run:

```bash
source .venv/bin/activate
python -m compileall app
```

Expected:

- Compile check passes.

- [ ] **Step 4: Run whitespace diff check**

Run:

```bash
git diff --check
```

Expected:

- No whitespace errors.

- [ ] **Step 5: Perform focused manual browser check with a temporary DB**

Use a temporary DB path. Do not use `data/extrusion_terminal.sqlite3`.

Run the server:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/unrelease-ui/extrusion_terminal.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

In a separate shell, use the existing app routes and/or a minimal fixture script approach consistent with this repo's previous UI checks to:

1. Import at least two ready cards.
2. Release both to the same machine queue.
3. Verify `/terminal` shows both released cards.
4. Open `/admin/planning` and use "Върни в неизпратени" on the first pending card.
5. Verify the returned card appears in the unreleased card pool.
6. Verify the remaining machine queue is normalized to sequence `1`.
7. Verify `/terminal` no longer shows the returned card.
8. Start another pending card, verify admin detail does not show "Върни в планиране" for the `running` card.
9. Capture at least one relevant screenshot under `artifacts/ui-checks/`.

Expected:

- Pending-only return-to-planning works in the live app.
- Started cards do not expose the return control.
- Terminal visibility updates after refresh/snapshot polling.

- [ ] **Step 6: Stop the temporary server**

Stop uvicorn with `Ctrl+C`. Verify no needed server session remains running before finishing.

- [ ] **Step 7: Review final diff**

Run:

```bash
git status --short --branch
git diff -- app/db.py app/main.py app/templates/admin_planning.html app/templates/admin_card_detail.html tests/test_admin_planning.py tests/test_admin_routes.py tests/test_terminal_sync.py README.md IMPLEMENTATION_PLAN.md
```

Expected:

- Diff is scoped to pending-card unrelease behavior, tests, and docs.
- No unrelated print-output or issue #8 planning UI cleanup is included.
- No ignored runtime DBs or screenshots are staged.

## Self-Review Checklist For The Implementing Session

Before reporting completion:

- Confirm `unrelease_pending_card()` rejects every non-`pending` status.
- Confirm successful unrelease clears only `machine_id`, `machine_sequence`, and `status`; it does not clear imported/front-card data, `max_roll_weight`, roll data, timing data, or material data.
- Confirm old machine queues normalize after removing a pending card from the middle.
- Confirm successful route actions use PRG redirects and browser refresh cannot repeat the mutation.
- Confirm stale loaded versions are blocked both in backend tests and route tests.
- Confirm `/terminal` does not expose unrelease.
- Confirm `/admin/planning` and `/admin/cards/{id}` expose unrelease only for `pending`.
- Confirm docs describe pending-only behavior and do not claim unrelated audit issues are fixed.
- Confirm all verification commands and the manual screenshot path are reported in the final response.
