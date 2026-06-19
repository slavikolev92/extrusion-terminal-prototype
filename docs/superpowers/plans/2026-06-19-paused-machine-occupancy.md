# Paused Machine Occupancy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix audit bug #6 so a paused card no longer blocks starting another card on the same machine, while resuming a paused card is still blocked when another card is running on that machine.

**Architecture:** Keep `paused` as an active/visible workflow status, but narrow physical machine occupancy to `running` cards only. The existing timing actions should continue to use one shared occupancy helper so start, resume, and admin replanning agree on what physically occupies a machine.

**Tech Stack:** Python 3.12, FastAPI, direct `sqlite3`, SQLite partial indexes, pytest, server-rendered HTML/CSS. Use the repo-local `.venv`.

---

## Mandatory Session Instructions

- Start by reading `/home/sk/projects/extrusion-terminal/AGENTS.md` and follow it.
- Do not commit unless the user explicitly asks. This overrides any generic Superpowers instruction about frequent commits.
- Do not use the existing `print-output` branch.
- Create a focused branch from `main`:

```bash
git switch main
git status --short --branch
git switch -c audit-fix-paused-machine-occupancy
```

- If `git status` shows unrelated untracked or modified files, leave them alone.
- Do not implement audit bug #1, #3, #4, #5, #7, or #8 in this branch.
- Do not remove `STATUS_PAUSED` from `ACTIVE_TERMINAL_STATUSES`; paused cards must remain visible/active in admin and terminal queues.
- Use TDD: write/update the regression tests first and watch the paused-machine tests fail before editing production code.
- Because the next execution should use `superpowers:subagent-driven-development`, dispatch fresh subagents per task and perform spec-compliance review and code-quality review after each implementation task.

## Background

Audit report: `reports/full-workflow-audit-20260618.md`, bug #6, “High - Paused Card Blocks Starting Another Card On The Same Machine.”

Observed behavior:

1. Import two cards, `PAUSE1` and `PAUSE2`.
2. Release both to machine 1.
3. Start `PAUSE1`.
4. Pause `PAUSE1`.
5. Try to start `PAUSE2`.
6. The app blocks `PAUSE2` with `Машина 1 е заета от поръчка PAUSE1.`

Required behavior:

- A `running` card occupies its machine.
- A `paused` card does not occupy the physical machine.
- Starting a pending card must be blocked when another card on the same machine is `running`.
- Starting a pending card must be allowed when another card on the same machine is only `paused`.
- Resuming a paused card must be blocked when another card on the same machine is currently `running`.
- The existing SQLite one-running-card-per-machine invariant must remain intact.
- Timing segments must remain correct: paused cards have no open segment; running cards have one open segment.

Current likely root cause:

- `app/db.py::fetch_occupied_machine_card()` currently checks both `STATUS_RUNNING` and `STATUS_PAUSED`:

```python
def fetch_occupied_machine_card(
    connection: sqlite3.Connection,
    card_id: int,
    machine_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT id, order_number, status
        FROM cards
        WHERE id <> ?
          AND machine_id = ?
          AND status IN (?, ?)
        ORDER BY machine_sequence IS NULL, machine_sequence, id
        LIMIT 1
        """,
        (card_id, machine_id, STATUS_RUNNING, STATUS_PAUSED),
    ).fetchone()
```

- `start_production_timing()` and `resume_production_timing()` both call this helper.
- `tests/test_production_timing.py::test_start_blocks_when_machine_has_running_or_paused_card` currently encodes the old behavior and needs to be replaced or split.

## Files And Responsibilities

- Modify `tests/test_production_timing.py`
  - Replace the old paused-occupancy expectation.
  - Add focused tests for running occupancy, paused non-occupancy, and resume blocking.

- Modify `app/db.py`
  - Update `fetch_occupied_machine_card()` so only `STATUS_RUNNING` occupies a machine.
  - Keep existing call sites in `start_production_timing()` and `resume_production_timing()`.
  - Do not change timing status transitions unless a test proves a real issue.

- Modify `README.md`
  - Update the terminal machine behavior section that still says paused cards occupy machines.
  - Clarify that paused cards remain visible/active but do not block starting another pending card.

- Do not modify templates or CSS unless a failing test proves it is required.

---

## Task 1: Confirm Current Context And Write Failing Timing Tests

**Files:**

- Modify: `tests/test_production_timing.py`
- Read-only context: `app/db.py`, `app/constants.py`, `reports/full-workflow-audit-20260618.md`, `README.md`

- [ ] **Step 1: Read required repository instructions and context**

Run:

```bash
cat AGENTS.md
sed -n '319,360p' reports/full-workflow-audit-20260618.md
sed -n '1,120p' app/constants.py
sed -n '660,790p;1638,1672p' app/db.py
sed -n '1,230p' tests/test_production_timing.py
sed -n '55,80p;590,610p' README.md
```

Expected:

- `AGENTS.md` confirms no commit unless asked.
- Audit bug #6 confirms paused cards should not occupy a machine.
- `ACTIVE_TERMINAL_STATUSES` includes `pending`, `running`, `paused`.
- `fetch_occupied_machine_card()` checks `running` and `paused`.
- `test_start_blocks_when_machine_has_running_or_paused_card` expects old blocked behavior.

- [ ] **Step 2: Replace the old occupancy test with three focused tests**

In `tests/test_production_timing.py`, replace the existing function:

```python
def test_start_blocks_when_machine_has_running_or_paused_card(connection):
    ...
```

with this exact test block:

```python
def open_segment_count(connection, card_id: int) -> int:
    return int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM production_time_segments
            WHERE card_id = ?
              AND ended_at IS NULL
            """,
            (card_id,),
        ).fetchone()[0]
    )


def test_start_blocks_when_machine_has_running_card(connection):
    running_card_id = import_and_release_card("25404", machine_id=1, machine_sequence=1)
    blocked_card_id = import_and_release_card("25405", machine_id=1, machine_sequence=2)
    assert db.start_production_timing(
        running_card_id,
        db.fetch_terminal_card_detail(running_card_id)["version"],
    ).ok

    blocked_result = db.start_production_timing(
        blocked_card_id,
        db.fetch_terminal_card_detail(blocked_card_id)["version"],
    )

    blocked_card = connection.execute(
        "SELECT status FROM cards WHERE id = ?",
        (blocked_card_id,),
    ).fetchone()

    assert not blocked_result.ok
    assert blocked_result.messages == ("Машина 1 е заета от поръчка 25404.",)
    assert blocked_card["status"] == STATUS_PENDING
    assert open_segment_count(connection, blocked_card_id) == 0


def test_start_allows_another_card_when_existing_card_is_paused(connection):
    paused_card_id = import_and_release_card("25406", machine_id=1, machine_sequence=1)
    next_card_id = import_and_release_card("25407", machine_id=1, machine_sequence=2)
    assert db.start_production_timing(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
    ).ok
    assert db.pause_production_timing(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
    ).ok

    start_result = db.start_production_timing(
        next_card_id,
        db.fetch_terminal_card_detail(next_card_id)["version"],
    )

    paused_card = connection.execute(
        "SELECT status FROM cards WHERE id = ?",
        (paused_card_id,),
    ).fetchone()
    next_card = connection.execute(
        "SELECT status FROM cards WHERE id = ?",
        (next_card_id,),
    ).fetchone()

    assert start_result.ok
    assert paused_card["status"] == STATUS_PAUSED
    assert next_card["status"] == STATUS_RUNNING
    assert open_segment_count(connection, paused_card_id) == 0
    assert open_segment_count(connection, next_card_id) == 1


def test_resume_paused_card_blocks_when_another_card_is_running_on_machine(connection):
    paused_card_id = import_and_release_card("25408", machine_id=1, machine_sequence=1)
    running_card_id = import_and_release_card("25409", machine_id=1, machine_sequence=2)
    assert db.start_production_timing(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
    ).ok
    assert db.pause_production_timing(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
    ).ok
    assert db.start_production_timing(
        running_card_id,
        db.fetch_terminal_card_detail(running_card_id)["version"],
    ).ok

    resume_result = db.resume_production_timing(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
    )

    paused_card = connection.execute(
        "SELECT status FROM cards WHERE id = ?",
        (paused_card_id,),
    ).fetchone()
    running_card = connection.execute(
        "SELECT status FROM cards WHERE id = ?",
        (running_card_id,),
    ).fetchone()

    assert not resume_result.ok
    assert resume_result.messages == ("Машина 1 е заета от поръчка 25409.",)
    assert paused_card["status"] == STATUS_PAUSED
    assert running_card["status"] == STATUS_RUNNING
    assert open_segment_count(connection, paused_card_id) == 0
    assert open_segment_count(connection, running_card_id) == 1
```

- [ ] **Step 3: Run the focused timing tests and verify the new behavior is red**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_production_timing.py -k "start_blocks_when_machine_has_running_card or start_allows_another_card_when_existing_card_is_paused or resume_paused_card_blocks_when_another_card_is_running_on_machine"
```

Expected before implementation:

- `test_start_blocks_when_machine_has_running_card` passes.
- `test_start_allows_another_card_when_existing_card_is_paused` fails because `start_result.ok` is false.
- `test_resume_paused_card_blocks_when_another_card_is_running_on_machine` may fail before reaching the resume assertion because starting the second card is currently blocked by the paused first card.

Do not edit production code until this red state is observed.

---

## Task 2: Implement Minimal Running-Only Occupancy

**Files:**

- Modify: `app/db.py`
- Test: `tests/test_production_timing.py`

- [ ] **Step 1: Change `fetch_occupied_machine_card()` to only return running cards**

In `app/db.py`, replace the helper implementation with:

```python
def fetch_occupied_machine_card(
    connection: sqlite3.Connection,
    card_id: int,
    machine_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT id, order_number, status
        FROM cards
        WHERE id <> ?
          AND machine_id = ?
          AND status = ?
        ORDER BY machine_sequence IS NULL, machine_sequence, id
        LIMIT 1
        """,
        (card_id, machine_id, STATUS_RUNNING),
    ).fetchone()
```

Do not change:

- `ACTIVE_TERMINAL_STATUSES`
- `idx_cards_one_running_per_machine`
- `start_production_timing()`
- `resume_production_timing()`
- `pause_production_timing()`

unless a test failure proves a necessary direct change.

- [ ] **Step 2: Run the focused timing tests and verify green**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_production_timing.py -k "start_blocks_when_machine_has_running_card or start_allows_another_card_when_existing_card_is_paused or resume_paused_card_blocks_when_another_card_is_running_on_machine"
```

Expected:

- All selected tests pass.
- The occupied-machine message for resume names the running second card, e.g. `25409`.

- [ ] **Step 3: Run all production timing tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_production_timing.py
```

Expected:

- All tests in `tests/test_production_timing.py` pass.

- [ ] **Step 4: Check admin planning implications**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_planning.py
```

Expected:

- Existing planning tests pass.
- `test_planning_blocks_running_card_into_occupied_machine` still passes because running cards still occupy machines.
- `test_planning_allows_pending_card_into_occupied_machine_when_sequence_is_unique` still passes.

If a planning test fails because it expected paused cards to occupy machines, update that test only if the new clarified audit behavior applies. Do not add a broad planning redesign.

---

## Task 3: Update README For Clarified Paused-Machine Behavior

**Files:**

- Modify: `README.md`

- [ ] **Step 1: Update the terminal machine behavior bullets**

Find this current text near the top of `README.md`:

```markdown
- Clicking a machine tile should open the running/paused card for that machine if one exists; otherwise it should open the next pending card for that machine by sequence.
...
- If a card is paused, treat that machine as occupied until the card is completed, cancelled by the shift manager, or reassigned.
```

Replace those bullets with wording that preserves visibility but changes occupancy:

```markdown
- Clicking a machine tile should open the running card for that machine if one exists; otherwise it should open the next active card for that machine by sequence, including paused cards that remain in the queue.
...
- A running card occupies its machine.
- A paused card remains active and visible, but it does not occupy the physical machine for starting another pending card.
- Resuming a paused card must be blocked if another card is currently running on that machine.
```

Keep the surrounding status table and terminal workflow text intact.

- [ ] **Step 2: Search for contradictory paused-occupancy wording**

Run:

```bash
rg -n "paused.*occup|paused.*machine|Пауз" README.md AGENTS.md app tests
```

Expected:

- No remaining README text says paused cards occupy machines.
- Do not edit `AGENTS.md` unless the user explicitly asks.
- Existing app labels for `paused` / `Паузирана` should remain unchanged.

---

## Task 4: Required Verification And Review

**Files:**

- Verify: `tests/test_production_timing.py`
- Verify: `tests/test_terminal_detail.py`
- Verify: `tests/test_terminal_v8_render.py`
- Verify: `tests/test_admin_planning.py`
- Verify: all tests
- Verify: `app`

- [ ] **Step 1: Run the required focused test set**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_production_timing.py tests/test_terminal_detail.py tests/test_terminal_v8_render.py tests/test_admin_planning.py
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

- [ ] **Step 3: Run syntax/import checks**

Run:

```bash
source .venv/bin/activate
python -m compileall app
```

Expected:

- Command exits 0.

- [ ] **Step 4: Run whitespace diff check**

Run:

```bash
git diff --check
```

Expected:

- Command exits 0 with no output.

- [ ] **Step 5: Inspect the diff for scope**

Run:

```bash
git diff --stat
git diff -- README.md app/db.py tests/test_production_timing.py
git status --short --branch
```

Expected:

- Only `README.md`, `app/db.py`, and `tests/test_production_timing.py` are modified for this task.
- No print, import, cancellation, unrelease, PRG, template, or CSS changes are present.
- Any pre-existing unrelated untracked files remain untracked and untouched.

- [ ] **Step 6: Decide whether Playwright is required**

Playwright is not required if the change remains backend/docs/test-only.

If templates or visible UI layout were changed unexpectedly, stop and either revert those unrelated UI changes or run the live FastAPI app and capture a focused Playwright screenshot under `artifacts/ui-checks/`.

---

## Expected Final Behavior Checklist

Verify each item against tests or code before final response:

- [ ] Starting a second pending card on machine 1 is blocked while the first card is `running`.
- [ ] Starting a second pending card on machine 1 succeeds after the first card is paused.
- [ ] The paused first card remains `paused`.
- [ ] The second card becomes `running`.
- [ ] The paused first card has no open timing segment.
- [ ] The running second card has one open timing segment.
- [ ] Resuming the paused first card is blocked while the second card is running.
- [ ] The occupied-machine message names the currently running second order.
- [ ] `STATUS_PAUSED` remains in `ACTIVE_TERMINAL_STATUSES`.
- [ ] The SQLite unique index allowing only one `running` card per machine remains unchanged.
- [ ] README no longer says paused cards occupy machines.
- [ ] No unrelated audit bug is included.

## Final Response Guidance

In the final response:

- State the branch name.
- State that no commit was made unless the user explicitly asked for one.
- Summarize changed files in one short list.
- Include the exact verification commands and pass/fail status.
- Mention that Playwright was not run if no UI/template files changed.
- Mention any pre-existing untracked files that remain untouched.

Do not say “done” or “fixed” unless the verification commands above have passed in the current execution session.

## Self-Review Of This Plan

Spec coverage:

- Audit bug #6 reproduction and desired behavior are covered by Task 1 tests.
- Root cause is addressed by Task 2.
- README contradiction is addressed by Task 3.
- Existing terminal/admin queue visibility is protected by keeping `ACTIVE_TERMINAL_STATUSES` unchanged and running existing terminal/admin tests.
- Verification commands match the repository’s `.venv` and pytest expectations.

Placeholder scan:

- No placeholder markers are present.
- Test code and implementation code are included explicitly.

Type/signature consistency:

- `open_segment_count(connection, card_id: int) -> int` uses existing sqlite connection fixture.
- Existing helper names match current code: `import_and_release_card`, `db.start_production_timing`, `db.pause_production_timing`, `db.resume_production_timing`, `db.fetch_terminal_card_detail`.
- Status constants match current imports in `tests/test_production_timing.py`: `STATUS_PAUSED`, `STATUS_PENDING`, `STATUS_RUNNING`.
