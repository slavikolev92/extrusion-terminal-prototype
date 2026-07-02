# Require Tare Before Roll Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent operators from creating a gross roll unless the roll can immediately receive a tare weight and calculated net weight.

**Architecture:** Enforce the rule in `app/db.py` inside `add_roll_gross_weight()`, because this is the shared backend path used by terminal and admin roll-add routes. Keep `finish_card()` validation as a defensive backstop for legacy/manual DB corruption, but normal app flow should block tare-less roll creation earlier.

**Tech Stack:** FastAPI route handlers call direct `sqlite3` helper functions in `app/db.py`; tests are Python `pytest` tests using temporary SQLite databases.

---

### Task 1: Add Roll-Entry Tare Validation

**Files:**
- Modify: `tests/test_roll_entry.py`
- Modify: `app/db.py`

- [ ] **Step 1: Write failing backend tests**

Add these tests to `tests/test_roll_entry.py` near the existing roll-add tests:

```python
def test_add_roll_requires_default_tare(connection):
    card_id = import_and_release_card("25546")
    start_card(card_id)
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.add_roll_gross_weight(card_id, loaded_version, "25.00")
    card = db.fetch_terminal_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Въведете шпула преди да добавите ролка.",)
    assert card["roll_entries"] == []
    assert card["version"] == loaded_version


def test_add_roll_allows_submitted_tare_without_existing_default(connection):
    card_id = import_and_release_card("25547")
    start_card(card_id)

    result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
        tare_weight="1.50",
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert card["tare_weight"] == 1.5
    assert [
        (roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
        for roll in card["roll_entries"]
    ] == [(25, 1.5, 23.5)]
```

- [ ] **Step 2: Run the new failing test**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_roll_entry.py::test_add_roll_requires_default_tare -v
```

Expected: the first test fails because `add_roll_gross_weight()` currently inserts a roll with `tare_weight` and `net_weight` set to `NULL`.

- [ ] **Step 3: Implement the minimal backend validation**

In `app/db.py`, inside `add_roll_gross_weight()`, after `default_tare` is computed and before `net = net_weight_for_roll(...)`, add:

```python
        if default_tare is None:
            return RuleResult(False, ("Въведете шпула преди да добавите ролка.",))
```

The resulting block should be:

```python
        default_tare = (
            parsed_submitted_tare
            if tare_weight is not None
            else decimal_from_database(card["tare_weight"])
        )
        if default_tare is None:
            return RuleResult(False, ("Въведете шпула преди да добавите ролка.",))
        net = net_weight_for_roll(parsed_gross, default_tare)
```

- [ ] **Step 4: Run the focused roll-entry tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_roll_entry.py -v
```

Expected: all `tests/test_roll_entry.py` tests pass.

- [ ] **Step 5: Update finish test that encoded the old late-failure path**

Modify `tests/test_finish_cancel_history.py::test_finish_blocks_roll_added_before_default_tare_was_set` so it asserts the new earlier failure instead of adding a bad roll and expecting finish to fail:

```python
def test_roll_entry_blocks_roll_added_before_default_tare_was_set(connection):
    card_id = import_and_release_card("25641")
    start_card(card_id)

    result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
    )

    assert not result.ok
    assert result.messages == ("Въведете шпула преди да добавите ролка.",)
    assert db.fetch_terminal_card_detail(card_id)["roll_entries"] == []
```

- [ ] **Step 6: Run focused finish/roll suites**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_roll_entry.py tests/test_finish_cancel_history.py -v
```

Expected: both focused suites pass.

- [ ] **Step 7: Run full verification**

Run:

```bash
source .venv/bin/activate
python -m compileall app
python -m pytest
git diff --check
```

Expected: compile succeeds, all tests pass, and `git diff --check` exits 0.

---

## Self-Review

- Spec coverage: the plan enforces default/submitted tare before new roll creation, preserves submitted-tare behavior, leaves finish validation as a defensive backstop, and does not change print routing.
- Placeholder scan: no placeholder steps or unspecified tests remain.
- Type consistency: all referenced functions already exist: `db.add_roll_gross_weight()`, `db.fetch_terminal_card_detail()`, `import_and_release_card()`, and `start_card()`.
