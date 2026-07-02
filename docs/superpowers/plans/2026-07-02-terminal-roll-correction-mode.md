# Terminal Roll Correction Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make existing terminal roll-row corrections deliberate and atomic: roll rows are read-only by default, a menu action opens correction mode, gross/tare edits save together, and delete remains a separate explicit action.

**Architecture:** Keep normal material/batch recipe entry and new-roll entry unchanged. Add a terminal-only bulk roll-correction backend helper and route that update existing roll gross/tare values in one version-checked transaction. Update the terminal template so existing roll rows display as read-only text until `Корекция на ролки` is opened from the overflow menu; correction mode enables gross/tare inputs, shows a large `Запази данните` action between the roll table and totals, and blocks other terminal actions until save/cancel.

**Tech Stack:** FastAPI server-rendered Jinja template, direct `sqlite3` helpers in `app/db.py`, Python `pytest`, local Playwright via Node for browser verification.

---

## File Map

- `app/db.py`: add `update_terminal_roll_corrections()` for existing terminal roll gross/tare edits only.
- `app/main.py`: add terminal roll-correction form parser, route, feedback target, and response context flag.
- `app/templates/terminal.html`: split roll delete from correction mode, make existing roll rows read-only by default, add correction form/actions, add JS mode toggling and action blocking.
- `tests/test_roll_entry.py`: backend transaction and validation coverage.
- `tests/test_terminal_v8_render.py`: route/render/JS contract coverage.
- `reports/full-readiness-audit-20260702.md`: after implementation, mark multiple dirty roll correction risk fixed.
- `artifacts/ui-checks/roll-correction-mode/`: ignored Playwright script/screenshots for manual browser verification.

Out of scope:

- Recipe actual material and batch-number autosave behavior.
- New roll entry flow, except it must be blocked/inert while roll-correction mode is open in the browser.
- Admin roll ledger behavior.
- Atomic optimistic write refactor beyond this new correction route.

---

### Task 1: Backend Bulk Roll Correction Helper

**Files:**
- Modify: `app/db.py`
- Modify: `tests/test_roll_entry.py`

- [ ] **Step 1: Write failing backend tests**

Add these tests near the existing roll edit tests in `tests/test_roll_entry.py`:

```python
def roll_values(card_id: int) -> list[tuple[float | None, float | None, float | None]]:
    return [
        (roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
        for roll in db.fetch_terminal_card_detail(card_id)["roll_entries"]
    ]


def test_terminal_roll_corrections_update_multiple_rolls_in_one_version(connection):
    card_id = import_and_release_card("25560")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "60.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    first_id = int(card["roll_entries"][0]["id"])
    second_id = int(card["roll_entries"][1]["id"])

    result = db.update_terminal_roll_corrections(
        card_id,
        card["version"],
        {
            first_id: {"gross_weight": "51.00", "tare_weight": "2.50"},
            second_id: {"gross_weight": "62.00", "tare_weight": "3.00"},
        },
    )
    updated = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert result.messages == ("Ролките са записани.",)
    assert updated["version"] == card["version"] + 1
    assert roll_values(card_id) == [(51, 2.5, 48.5), (62, 3, 59)]
    assert updated["total_gross_weight"] == "113.00"
    assert updated["total_net_weight"] == "107.50"


def test_terminal_roll_corrections_block_stale_version_without_partial_update(connection):
    card_id = import_and_release_card("25561")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])
    assert db.update_tare_weight(card_id, card["version"], "2.25").ok

    result = db.update_terminal_roll_corrections(
        card_id,
        card["version"],
        {roll_id: {"gross_weight": "51.00", "tare_weight": "2.50"}},
    )

    assert not result.ok
    assert result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert roll_values(card_id) == [(50, 2, 48)]


def test_terminal_roll_corrections_validate_all_rows_before_saving(connection):
    card_id = import_and_release_card("25562")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "60.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    first_id = int(card["roll_entries"][0]["id"])
    second_id = int(card["roll_entries"][1]["id"])

    result = db.update_terminal_roll_corrections(
        card_id,
        card["version"],
        {
            first_id: {"gross_weight": "55.00", "tare_weight": "2.00"},
            second_id: {"gross_weight": "1.00", "tare_weight": "3.00"},
        },
    )

    assert not result.ok
    assert result.messages == ("Бруто теглото не може да бъде по-малко от шпулата.",)
    assert roll_values(card_id) == [(50, 2, 48), (60, 2, 58)]


def test_terminal_roll_corrections_reject_unknown_roll_id(connection):
    card_id = import_and_release_card("25563")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    card = db.fetch_terminal_card_detail(card_id)

    result = db.update_terminal_roll_corrections(
        card_id,
        card["version"],
        {999999: {"gross_weight": "55.00", "tare_weight": "2.00"}},
    )

    assert not result.ok
    assert result.messages == ("Избрана ролка не принадлежи към тази карта.",)
    assert roll_values(card_id) == [(50, 2, 48)]


def test_terminal_roll_corrections_completed_card_keeps_final_gross_roll(connection):
    card_id = import_and_release_card("25564")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    assert db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok
    card = db.fetch_terminal_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])

    result = db.update_terminal_roll_corrections(
        card_id,
        card["version"],
        {roll_id: {"gross_weight": "", "tare_weight": "2.00"}},
    )

    assert not result.ok
    assert result.messages == ("Завършените карти трябва да запазят поне едно бруто тегло на ролка.",)
    assert roll_values(card_id) == [(50, 2, 48)]
```

- [ ] **Step 2: Run the failing backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_roll_entry.py::test_terminal_roll_corrections_update_multiple_rolls_in_one_version -v
```

Expected: fail with `AttributeError: module 'app.db' has no attribute 'update_terminal_roll_corrections'`.

- [ ] **Step 3: Add the backend helper**

In `app/db.py`, add this function near `update_roll_weight()`:

```python
def update_terminal_roll_corrections(
    card_id: int,
    loaded_version: int,
    roll_updates: dict[int, dict[str, str]],
) -> RuleResult:
    with connect() as connection:
        card = fetch_roll_action_card(connection, card_id)
        version_result = validate_loaded_card_version(card, loaded_version)
        if not version_result.ok:
            return version_result

        roll_entry_result = validate_card_allows_roll_entry(card)
        if not roll_entry_result.ok:
            return roll_entry_result

        existing_rolls = connection.execute(
            """
            SELECT id, roll_number, gross_weight, tare_weight
            FROM roll_entries
            WHERE card_id = ?
            ORDER BY roll_number
            """,
            (card_id,),
        ).fetchall()
        existing_ids = {int(row["id"]) for row in existing_rolls}
        unknown_ids = set(roll_updates) - existing_ids
        if unknown_ids:
            return RuleResult(False, ("Избрана ролка не принадлежи към тази карта.",))

        parsed_updates: dict[int, tuple[Decimal | None, Decimal | None, Decimal | None]] = {}
        changed = False
        gross_roll_count = 0
        for roll in existing_rolls:
            roll_id = int(roll["id"])
            submitted = roll_updates.get(roll_id, {})
            gross_text = submitted.get(
                "gross_weight",
                decimal_to_storage(decimal_from_database(roll["gross_weight"]))
                if roll["gross_weight"] is not None
                else "",
            )
            tare_text = submitted.get(
                "tare_weight",
                decimal_to_storage(decimal_from_database(roll["tare_weight"]))
                if roll["tare_weight"] is not None
                else "",
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
            net = net_weight_for_roll(parsed_gross, parsed_tare)
            if parsed_gross is not None and parsed_tare is not None and net is None:
                return RuleResult(
                    False,
                    ("Бруто теглото не може да бъде по-малко от шпулата.",),
                )
            if parsed_gross is not None:
                gross_roll_count += 1
            existing_gross = decimal_from_database(roll["gross_weight"])
            existing_tare = decimal_from_database(roll["tare_weight"])
            if parsed_gross != existing_gross or parsed_tare != existing_tare:
                changed = True
            parsed_updates[roll_id] = (parsed_gross, parsed_tare, net)

        if str(card["status"]) in PRODUCTION_COMPLETE_STATUSES and gross_roll_count < 1:
            return RuleResult(
                False,
                ("Завършените карти трябва да запазят поне едно бруто тегло на ролка.",),
            )

        if not changed:
            return RuleResult(True, ("Ролките са записани.",))

        for roll_id, (gross, tare, net) in parsed_updates.items():
            connection.execute(
                """
                UPDATE roll_entries
                SET gross_weight = ?,
                    tare_weight = ?,
                    net_weight = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND card_id = ?
                """,
                (
                    decimal_to_storage(gross) if gross is not None else None,
                    decimal_to_storage(tare) if tare is not None else None,
                    decimal_to_storage(net) if net is not None else None,
                    roll_id,
                    card_id,
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

    return RuleResult(True, ("Ролките са записани.",))
```

`Decimal` is already imported in `app/db.py`; do not add a duplicate import.

- [ ] **Step 4: Run backend roll tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_roll_entry.py -v
```

Expected: all roll-entry tests pass.

---

### Task 2: Terminal Route, Form Parser, And Feedback

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Write failing route tests**

Update imports in `tests/test_terminal_v8_render.py` to include `save_terminal_roll_corrections`.

Add these route tests near the existing terminal roll route tests:

```python
def test_terminal_roll_corrections_route_saves_multiple_rows_together(connection):
    card_id = release_ready_card("26220", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    first_id = int(card["roll_entries"][0]["id"])
    second_id = int(card["roll_entries"][1]["id"])

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls/corrections",
            {
                "loaded_version": str(card["version"]),
                f"gross_weight__{first_id}": "51.00",
                f"tare_weight__{first_id}": "2.50",
                f"gross_weight__{second_id}": "62.00",
                f"tare_weight__{second_id}": "3.00",
            },
        )
    )
    updated = db.fetch_terminal_card_detail(card_id)

    assert status_code == 303
    assert headers["location"] == f"/terminal/cards/{card_id}?notice=rolls_saved"
    assert [
        (roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
        for roll in updated["roll_entries"]
    ] == [(51, 2.5, 48.5), (62, 3, 59)]


def test_terminal_roll_corrections_route_blocks_stale_post_without_partial_update(connection):
    card_id = release_ready_card("26221", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])
    assert db.update_tare_weight(card_id, card["version"], "2.25").ok

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls/corrections",
            {
                "loaded_version": str(card["version"]),
                f"gross_weight__{roll_id}": "51.00",
                f"tare_weight__{roll_id}": "2.50",
            },
        )
    )
    updated = db.fetch_terminal_card_detail(card_id)

    assert status_code == 200
    assert "location" not in headers
    assert updated["roll_entries"][0]["gross_weight"] == 50
    assert updated["roll_entries"][0]["tare_weight"] == 2
```

Add this unavailable-card direct post test:

```python
def test_terminal_roll_corrections_route_blocks_archived_card_direct_post(connection):
    card_id = release_ready_card("26222", machine_id=2, sequence=1)
    complete_card(card_id)
    assert db.archive_completed_card(card_id, card_version(card_id)).ok
    card = db.fetch_admin_card_detail(card_id)
    roll = card["roll_entries"][0]

    status_code, headers = asyncio.run(
        post_form_to_app(
            f"/terminal/cards/{card_id}/rolls/corrections",
            {
                "loaded_version": str(card["version"]),
                f"gross_weight__{roll['id']}": "99.00",
                f"tare_weight__{roll['id']}": "1.00",
            },
        )
    )
    updated = db.fetch_admin_card_detail(card_id)

    assert status_code == 200
    assert "location" not in headers
    assert updated["roll_entries"][0]["gross_weight"] == roll["gross_weight"]
    assert updated["version"] == card["version"]
```

- [ ] **Step 2: Run failing route tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_roll_corrections_route_saves_multiple_rows_together -v
```

Expected: fail because the route/function does not exist yet.

- [ ] **Step 3: Add imports and notice text**

In `app/main.py`, add `update_terminal_roll_corrections` to the `.db` import list.

Add this entry to `TERMINAL_NOTICE_MESSAGES` immediately after the existing `"roll_saved"` entry:

```python
"rolls_saved": ("Ролките са записани.",),
```

- [ ] **Step 4: Add terminal roll-correction form parser**

In `app/main.py`, near `roll_ledger_from_form()`, add:

```python
def terminal_roll_corrections_from_form(form: Any) -> dict[int, dict[str, str]]:
    roll_updates: dict[int, dict[str, str]] = {}
    for key, value in form.multi_items():
        text_value = str(value or "")
        if key.startswith("gross_weight__"):
            roll_id = int(key.removeprefix("gross_weight__"))
            roll_updates.setdefault(roll_id, {})["gross_weight"] = text_value
        elif key.startswith("tare_weight__"):
            roll_id = int(key.removeprefix("tare_weight__"))
            roll_updates.setdefault(roll_id, {})["tare_weight"] = text_value
    return roll_updates
```

- [ ] **Step 5: Add route**

In `app/main.py`, place this route after `save_roll_weight()` and before delete routes:

```python
@app.post("/terminal/cards/{card_id}/rolls/corrections")
async def save_terminal_roll_corrections(
    request: Request,
    card_id: int,
):
    form = await request.form()
    parsed_version, roll_result = parse_loaded_version(
        str(form.get("loaded_version") or "")
    )
    if parsed_version is not None:
        roll_result = validate_terminal_card_available_for_post(card_id)
        if roll_result.ok:
            try:
                roll_updates = terminal_roll_corrections_from_form(form)
            except ValueError:
                roll_result = RuleResult(False, ("Формата съдържа невалидна ролка.",))
            else:
                roll_result = update_terminal_roll_corrections(
                    card_id,
                    parsed_version,
                    roll_updates,
                )

    return terminal_post_response(
        request,
        card_id,
        "roll_result",
        roll_result,
        notice_code="rolls_saved",
        roll_result_target="roll_corrections",
    )
```

- [ ] **Step 6: Extend terminal feedback**

In `build_terminal_feedback()` add an error bucket:

```python
"roll_corrections": (),
```

In `terminal_roll_feedback_target()` accept the new target:

```python
if target in {"tare", "new_roll", "roll_row", "roll_delete", "roll_corrections"}:
    return target
```

In `build_terminal_feedback()`, after state-error handling and before normal target assignment, mark correction mode open:

```python
if target == "roll_corrections":
    feedback["open_roll_corrections"] = True
```

Initialize the flag in the feedback object:

```python
"open_roll_corrections": False,
```

- [ ] **Step 7: Run route tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_roll_corrections_route_saves_multiple_rows_together tests/test_terminal_v8_render.py::test_terminal_roll_corrections_route_blocks_archived_card_direct_post -v
```

Expected: route tests pass.

---

### Task 3: Template Roll Correction Mode

**Files:**
- Modify: `app/templates/terminal.html`
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Write failing render tests**

Replace `test_terminal_roll_table_renders_editable_gross_and_tare_with_readonly_net`, update `test_terminal_tare_and_correction_forms_use_dirty_autosave_without_new_roll_autosave`, and replace `test_terminal_v8_roll_delete_is_hidden_behind_menu_correction_action` with these render tests.

```python
def test_terminal_roll_rows_are_readonly_by_default_with_correction_action(connection):
    card_id = release_ready_card("26230", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    first_roll = card["roll_entries"][0]

    html = render_terminal(card_id)
    row_html = roll_row_block(html, first_roll["id"])

    assert "Корекция на ролки" in html
    assert "Изтриване на ролки" in html
    assert 'data-roll-correction-open' in html
    assert 'data-roll-delete-open' in html
    assert 'data-roll-display="gross"' in row_html
    assert 'data-roll-display="tare"' in row_html
    assert 'data-roll-correction-input' in row_html
    assert 'name="gross_weight__' in row_html
    assert 'name="tare_weight__' in row_html
    assert "disabled" in row_html
    assert 'data-dirty-autosave="true"' not in row_html
    assert 'data-roll-correction-actions hidden' in html
```

Add correction error/open-mode test:

```python
def test_terminal_roll_correction_error_opens_correction_mode(connection):
    card_id = release_ready_card("26231", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok

    html = render_terminal(
        card_id,
        roll_result=RuleResult(False, ("correction failure",)),
        roll_result_target="roll_corrections",
    )

    assert 'data-roll-correction-root data-correction-open="true"' in html
    assert "correction failure" in data_block(html, "data-feedback-target", "roll_corrections")
    assert "Запази данните" in html
    assert "Отказ" in html
```

Add delete separation test update:

```python
def test_terminal_v8_roll_delete_is_separate_from_roll_correction(connection):
    card_id = release_ready_card("26172", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "60.00").ok

    html = render_terminal(card_id)
    roll_id = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]["id"]
    row_html = roll_row_block(html, roll_id)

    assert "Корекция на ролки" in html
    assert "Изтриване на ролки" in html
    assert 'data-roll-correction-open' in html
    assert 'data-roll-delete-open' in html
    assert f'action="/terminal/cards/{card_id}/rolls/corrections"' in html
    assert f'action="/terminal/cards/{card_id}/rolls/actions/delete-selected"' in html
    assert "/delete" not in row_html
    assert "Изтрий" not in row_html
```

- [ ] **Step 2: Run failing render tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_roll_rows_are_readonly_by_default_with_correction_action -v
```

Expected: fail because rows are editable and the correction/delete controls are not separated.

- [ ] **Step 3: Split menu buttons**

In `app/templates/terminal.html`, replace the current one-button menu:

```html
<button class="roll-correction-open" id="roll-correction-open" type="button">Корекции на ролки</button>
```

with:

```html
<button class="roll-correction-open" id="roll-correction-open" type="button" data-roll-correction-open>Корекция на ролки</button>
<button class="roll-delete-open" id="roll-delete-open" type="button" data-roll-delete-open>Изтриване на ролки</button>
```

Keep the existing `show_roll_correction` condition.

- [ ] **Step 4: Wrap roll table in one correction form**

Around the roll table, add a single correction form:

```html
<form
  class="roll-correction-form"
  id="roll-correction-form-{{ selected_card.id }}"
  action="/terminal/cards/{{ selected_card.id }}/rolls/corrections"
  method="post"
  data-roll-correction-root
  data-correction-open="{% if terminal_feedback.open_roll_corrections %}true{% else %}false{% endif %}"
>
  <input type="hidden" name="loaded_version" value="{{ selected_card.version }}">
</form>
```

Move the existing roll-table block, starting at `<div class="roll-table">` and ending at that block's matching closing `</div>`, so it sits inside this form after the hidden `loaded_version` input. Do not move the new-roll form, default-tare form, delete panel, or totals into this correction form.

Inside each roll row, replace the two per-row autosave forms with read-only spans plus correction inputs:

```html
<div class="roll-weight-cell">
  <span class="roll-display-value" data-roll-display="gross">{{ roll.gross_weight if roll.gross_weight is not none else "-" }}</span>
  <input
    class="roll-correction-input"
    data-roll-correction-input
    type="number"
    name="gross_weight__{{ roll.id }}"
    min="0"
    step="0.01"
    value="{{ roll.gross_weight if roll.gross_weight is not none else '' }}"
    {% if not terminal_feedback.open_roll_corrections %}disabled hidden{% endif %}
    {% if not can_edit_rolls %}disabled{% endif %}
  >
</div>
<div class="roll-weight-cell">
  <span class="roll-display-value" data-roll-display="tare">{{ roll.tare_weight if roll.tare_weight is not none else "-" }}</span>
  <input
    class="roll-correction-input"
    data-roll-correction-input
    type="number"
    name="tare_weight__{{ roll.id }}"
    min="0"
    step="0.01"
    value="{{ roll.tare_weight if roll.tare_weight is not none else '' }}"
    {% if not terminal_feedback.open_roll_corrections %}disabled hidden{% endif %}
    {% if not can_edit_rolls %}disabled{% endif %}
  >
</div>
```

Do not include `data-dirty-autosave="true"` on roll-row correction inputs/forms.

- [ ] **Step 5: Add correction save/cancel bar between roll table and totals**

Place this after the roll table and before the delete panel/totals:

```html
<div class="roll-correction-actions" data-roll-correction-actions {% if not terminal_feedback.open_roll_corrections %}hidden{% endif %}>
  <div class="roll-correction-message">
    Коригирайте бруто/шпула за съществуващите ролки и запазете наведнъж.
  </div>
  <div class="roll-correction-buttons">
    <button class="roll-correction-save" type="submit" form="roll-correction-form-{{ selected_card.id }}">Запази данните</button>
    <button class="roll-correction-cancel" type="button" data-roll-correction-cancel>Отказ</button>
  </div>
  <div class="roll-correction-error-slot field-error-slot" data-feedback-target="roll_corrections">
    {% if terminal_feedback.errors.roll_corrections %}
      <div class="inline-error" role="alert">
        {% for message in terminal_feedback.errors.roll_corrections %}
          <p>{{ message }}</p>
        {% endfor %}
      </div>
    {% endif %}
  </div>
</div>
```

- [ ] **Step 6: Rename delete panel**

Change delete heading from:

```html
<span>Изтриване на ролка</span>
```

to:

```html
<span>Изтриване на ролки</span>
```

- [ ] **Step 7: Add correction mode JavaScript**

In the final terminal UI script block, replace `rollCorrectionOpen` delete-panel behavior with correction/delete separation:

```javascript
const rollCorrectionRoot = document.querySelector("[data-roll-correction-root]");
const rollCorrectionOpen = document.querySelector("[data-roll-correction-open]");
const rollCorrectionCancel = document.querySelector("[data-roll-correction-cancel]");
const rollCorrectionActions = document.querySelector("[data-roll-correction-actions]");
const rollCorrectionInputs = Array.from(document.querySelectorAll("[data-roll-correction-input]"));
const rollDisplayValues = Array.from(document.querySelectorAll("[data-roll-display]"));
const rollDeleteOpen = document.querySelector("[data-roll-delete-open]");
const rollDeletePanel = document.getElementById("roll-delete-panel");
const rollDeleteClose = document.getElementById("roll-delete-close");

const correctionBlockedControls = Array.from(document.querySelectorAll(
  ".machine-tab, .queue-card, .history-row, #queue-open, #history-open, .actions form button, .roll-add-button, .tare-form input, .recipe-table input",
));
const originalDisabled = new WeakMap();

const setCorrectionMode = (open) => {
  if (!rollCorrectionRoot) {
    return;
  }
  rollCorrectionRoot.dataset.correctionOpen = open ? "true" : "false";
  rollCorrectionActions.hidden = !open;
  rollCorrectionInputs.forEach((input) => {
    input.hidden = !open;
    input.disabled = !open;
  });
  rollDisplayValues.forEach((value) => {
    value.hidden = open;
  });
  correctionBlockedControls.forEach((control) => {
    if (!originalDisabled.has(control)) {
      originalDisabled.set(control, control.disabled === true);
    }
    control.disabled = open || originalDisabled.get(control);
    control.setAttribute("aria-disabled", open ? "true" : "false");
  });
  if (open) {
    rollCorrectionInputs[0]?.focus();
  }
};

if (rollCorrectionRoot?.dataset.correctionOpen === "true") {
  setCorrectionMode(true);
}
rollCorrectionOpen?.addEventListener("click", () => {
  setCorrectionMode(true);
});
rollCorrectionCancel?.addEventListener("click", () => {
  window.location.href = "{{ '/terminal/cards/' ~ selected_card.id if selected_card else '/terminal' }}";
});
rollDeleteOpen?.addEventListener("click", () => {
  if (rollDeletePanel) {
    rollDeletePanel.hidden = false;
  }
});
rollDeleteClose?.addEventListener("click", () => {
  if (rollDeletePanel) {
    rollDeletePanel.hidden = true;
  }
});
```

For anchor-like elements such as `.machine-tab`, `.queue-card`, and `.history-row`, do not assign `disabled`. Store them in `correctionBlockedLinks`, add `aria-disabled="true"` and class `correction-blocked-link` while correction mode is open, and add a capture-phase click handler that prevents default when correction mode is open and the clicked target is inside a blocked link.

- [ ] **Step 8: Add/adjust CSS**

In the inline CSS of `app/templates/terminal.html`, add:

```css
.roll-correction-actions {
  border: 2px solid #2563eb;
  border-radius: 8px;
  padding: 12px;
  background: #eff6ff;
  display: grid;
  gap: 10px;
}

.roll-correction-actions[hidden] {
  display: none;
}

.roll-correction-buttons {
  display: flex;
  gap: 10px;
  align-items: center;
}

.roll-correction-save {
  min-height: 48px;
  padding: 0 20px;
  font-weight: 800;
}

.roll-correction-cancel {
  min-height: 44px;
}

.roll-display-value {
  display: inline-flex;
  min-height: 36px;
  align-items: center;
}
```

Set `.roll-body` to `grid-template-rows: auto minmax(0, 1fr) auto auto auto;` so the vertical order is roll entry, roll table, correction actions, delete panel, totals.

- [ ] **Step 9: Run render tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py::test_terminal_roll_rows_are_readonly_by_default_with_correction_action tests/test_terminal_v8_render.py::test_terminal_roll_correction_error_opens_correction_mode tests/test_terminal_v8_render.py::test_terminal_v8_roll_delete_is_separate_from_roll_correction -v
```

Expected: render tests pass.

---

### Task 4: Correction Mode Blocking And Legacy Test Cleanup

**Files:**
- Modify: `app/templates/terminal.html`
- Modify: `tests/test_terminal_v8_render.py`

- [ ] **Step 1: Update existing tests that assumed row autosave**

Find these tests:

```bash
rg -n "editable_gross|dirty_autosave|Корекции на ролки|Изтриване на ролка|roll_delete_is_hidden" tests/test_terminal_v8_render.py
```

Update expectations:

- `test_terminal_roll_table_renders_editable_gross_and_tare_with_readonly_net` becomes `test_terminal_roll_table_renders_readonly_existing_rolls_with_readonly_net`.
- Existing row blocks should not contain active per-row `data-dirty-autosave="true"` forms.
- New-roll form still does not autosave.
- Tare form may keep dirty autosave outside correction mode.
- Recipe form remains unchanged.
- Button text `Корекции на ролки` is removed. Correction assertions use `Корекция на ролки`; delete assertions use `Изтриване на ролки`.
- Delete heading becomes `Изтриване на ролки`.

- [ ] **Step 2: Add blocking contract test**

Add:

```python
def test_terminal_roll_correction_script_blocks_other_actions_while_open(connection):
    card_id = release_ready_card("26232", machine_id=1, sequence=1)
    assert db.start_production_timing(card_id, card_version(card_id)).ok
    assert db.update_tare_weight(card_id, card_version(card_id), "2.00").ok
    assert db.add_roll_gross_weight(card_id, card_version(card_id), "50.00").ok

    html = render_terminal(card_id)

    assert "setCorrectionMode" in html
    assert "data-roll-correction-open" in html
    assert "data-roll-correction-cancel" in html
    assert "data-roll-correction-input" in html
    assert "correctionBlockedControls" in html
    assert ".roll-add-button" in html
    assert ".tare-form input" in html
    assert ".recipe-table input" in html
    assert "#queue-open" in html
    assert "#history-open" in html
```

- [ ] **Step 3: Add beforeunload guard for dirty correction edits**

Capture initial values and warn on tab close when correction mode is open and any correction input changed:

```javascript
const initialCorrectionValues = new Map(
  rollCorrectionInputs.map((input) => [input.name, input.value]),
);
const hasDirtyRollCorrections = () => rollCorrectionInputs.some(
  (input) => input.value !== initialCorrectionValues.get(input.name),
);
window.addEventListener("beforeunload", (event) => {
  if (!rollCorrectionRoot || rollCorrectionRoot.dataset.correctionOpen !== "true") {
    return;
  }
  if (!hasDirtyRollCorrections()) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
});
```

Do not reuse the generic dirty autosave submit-on-click behavior for roll correction inputs.

- [ ] **Step 4: Run terminal render suite**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py -v
```

Expected: all terminal render tests pass.

---

### Task 5: Playwright Browser Verification

**Files:**
- Create ignored artifact script: `artifacts/ui-checks/roll-correction-mode/playwright_roll_correction.mjs`
- Create ignored seed helper: `artifacts/ui-checks/roll-correction-mode/seed_roll_correction_db.py`
- Do not commit artifacts.

- [ ] **Step 1: Create a focused temporary DB seed script**

Create a temporary script under `artifacts/ui-checks/roll-correction-mode/seed_roll_correction_db.py` that:

- uses `.test-runtime/roll-correction-mode/extrusion_terminal.sqlite3`
- imports one released card
- starts timing
- saves tare
- adds two rolls

Use the same temp-database pattern as `artifacts/ui-checks/audit-2026-07-02/seed_audit_db.py`, but keep this script focused on one running card with two rolls.

- [ ] **Step 2: Create a Playwright script**

Create `artifacts/ui-checks/roll-correction-mode/playwright_roll_correction.mjs` that:

- opens `/terminal`
- captures `01-default-readonly-rolls.png`
- asserts existing roll gross/tare row inputs are not focusable/editable by default
- clicks `Корекция на ролки`
- captures `02-correction-mode-open.png`
- edits first roll gross and tare
- clicks `Запази данните`
- waits for redirect/reload
- asserts both gross/tare/net changed
- opens `Корекция на ролки` again
- checks `Изтриване на ролки` is a separate control/panel
- captures `03-delete-separate.png`

- [ ] **Step 3: Start local app against temp DB**

Run:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/roll-correction-mode/extrusion_terminal.sqlite3 \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

Use a background session and stop it before final response.

- [ ] **Step 4: Run Playwright**

Run:

```bash
node artifacts/ui-checks/roll-correction-mode/playwright_roll_correction.mjs
```

Expected: script exits 0 and screenshots are saved under `artifacts/ui-checks/roll-correction-mode/`.

---

### Task 6: Audit Report And Final Verification

**Files:**
- Modify: `reports/full-readiness-audit-20260702.md`

- [ ] **Step 1: Update audit report**

Remove “Multiple Dirty Autosave Forms” from “Remaining Hardening Recommendations” and add this fixed-after-audit item:

```markdown
### 7. Existing Roll Corrections Were Always Editable And Autosaved Separately

Severity: Important.

Problem: Existing roll gross/tare fields were editable by default and used separate autosave forms. Editing multiple rows or both gross/tare on the same row could save only part of the operator's intended correction.

Fix:

- Existing roll rows are read-only by default.
- `Корекция на ролки` opens a deliberate correction mode.
- Existing roll gross/tare values save together through one version-checked route.
- `Изтриване на ролки` remains a separate explicit delete flow.
- Other terminal actions are blocked while correction mode is open.
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_roll_entry.py tests/test_terminal_v8_render.py -v
```

Expected: both suites pass.

- [ ] **Step 3: Run full verification**

Run:

```bash
source .venv/bin/activate
python -m compileall app
python -m pytest
git diff --check
```

Expected: compile succeeds, all tests pass, and diff check exits 0.

- [ ] **Step 4: Review changed code**

Inspect:

```bash
git diff -- app/db.py app/main.py app/templates/terminal.html tests/test_roll_entry.py tests/test_terminal_v8_render.py reports/full-readiness-audit-20260702.md
```

Confirm:

- recipe actual material and batch-number behavior is unchanged
- new roll entry remains explicit
- existing roll rows are not editable by default
- correction save route updates gross/tare together
- delete route remains separate
- stale/unavailable cards mutate nothing

---

## Self-Review

- Spec coverage: covers the requested roll-pane-only scope, correction and delete separation, read-only default rows, correction mode, large save button, backend atomicity, stale handling, tests, Playwright, and audit update.
- Placeholder scan: no `TBD`, `TODO`, “add tests”, or unspecified behavior remains. Artifact scripts are described by behavior because they are ignored verification tooling, not production code.
- Type consistency: planned functions and routes are consistent: `update_terminal_roll_corrections()`, `terminal_roll_corrections_from_form()`, `save_terminal_roll_corrections()`, and `/terminal/cards/{card_id}/rolls/corrections`.
- Scope check: this is one coherent feature slice. It should be implemented before the broader atomic optimistic-version refactor.
