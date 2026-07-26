# Rewinding Return Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task. If the user explicitly chooses delegated execution, use `superpowers:subagent-driven-development` instead.

**Goal:** Add a safe terminal workflow for extrusion cards whose production has ended but whose damaged rolls must return from rewinding/slitting before the operator deliberately completes the card.

**Architecture:** Introduce one explicit `awaiting_rewinding` card state and two persisted facts: the informational rewinding-roll count and the final extrusion shift. The existing `Приключи` operation branches transactionally: an active card with a positive marker ends extrusion and enters the waiting state, while a waiting card runs the existing roll-ledger completion checks and becomes completed without changing production time. Keep waiting separate from active production and completed/printable states, expose it through a third centered terminal pane, and preserve the accepted Task 11 roll-panel design without adding a rewinding-department workflow.

**Tech Stack:** Python 3, FastAPI, direct `sqlite3`, Jinja2 server-rendered HTML, vanilla JavaScript/CSS, pytest, repo-local Node Playwright.

## Global Constraints

- Treat [README.md](/home/sk/projects/extrusion-terminal/README.md) as authoritative and expand its extrusion-only lifecycle narrowly: this feature tracks an extrusion card awaiting returned rolls; it does not manage rewinding/slitting work.
- Follow [AGENTS.md](/home/sk/projects/extrusion-terminal/AGENTS.md) and [v2-files/AGENTS.md](/home/sk/projects/extrusion-terminal/v2-files/AGENTS.md). Do not touch `data/extrusion_terminal.sqlite3`; tests and browser checks must use temporary databases.
- Preserve the one-app, SQLite, server-rendered pilot architecture. Add no dependency, client framework, background service, user/permission system, Task 10 roll-change/countdown behavior, or Task 12 pallet/transportation lifecycle expansion.
- Use [v2-files/TASK-11-REWINDING.md](/home/sk/projects/extrusion-terminal/v2-files/TASK-11-REWINDING.md) as the approved behavioral specification and [v2-files/prototypes/rewinding-roll-controls/prototype.html](/home/sk/projects/extrusion-terminal/v2-files/prototypes/rewinding-roll-controls/prototype.html) as the fixed visual reference. Do not regenerate or replace the prototype.
- Keep the rewinding count informational. It is either `NULL` or an integer from `1` through `999`; blank or zero clears it. It never has to match the number of rolls later returned.
- A positive rewinding count permits `Приключи` from either `running` or `paused` without tare, pallet, or roll entries. Running closes its open timing segment; paused remains paused in timing history and gains no artificial segment.
- Waiting cards are extrusion-ended and terminal-visible, but are not active, completed, archived, or printable. Their machine is free because status excludes them from active work; remaining active queue positions are normalized while the card's saved machine/sequence history remains unchanged, matching current completion behavior.
- Deliberate completion from waiting reuses the current roll-ledger validation: at least one gross roll, valid tare/net for every gross roll, and no incomplete roll gaps. Pallet remains optional.
- Every successful normal completion and transition into waiting stores the active shift occurrence as `final_extrusion_shift_occurrence_id`. Late rolls use that stored shift; legacy rows fall back to the latest shift already linked to a roll, or remain unattributed when no defensible shift exists.
- Preserve the current mixed-pallet warning condition and wording for all three finish contexts: normal completion, ending extrusion into waiting, and finalizing a waiting card. If its condition does not apply, show the ordinary confirmation.
- Preserve exact stored decimal input semantics (up to two decimal places). Display gross, tare/core, and net with one decimal place in the terminal roll table.
- Every production-data mutation persists immediately and uses optimistic version checking. Multi-field default changes and roll insertion remain atomic.
- Do not stage or commit unless the user explicitly asks. Each task ends with a review checkpoint and an optional, user-authorized commit command.

## Current Baseline and Fixed Decisions

- Baseline before implementation: `686` pytest tests pass.
- The current app already permits finishing a paused card without creating an open timing segment; Task 11 preserves that behavior.
- The accepted third header action is `Изчакващи пренавиване`, with a bottom-right badge hidden at zero. It opens a centered pane and never opens automatically.
- The selected-card marker action is `Пренавиване`; its marked state reads `Пренавиване: N`. The neighboring `Смяна на ролка` control is visual only in this task and must have no handler, dialog, timer, or backend route.
- The waiting-card action remains `Приключи`; no new “finalize” verb is introduced.
- Completed-card recovery remains the existing Produced Orders route: if the marker was forgotten, the card stays completed and operators may add the missing rolls there.
- Waiting cards cannot be cancelled, deleted, archived, or printed.

## File and Responsibility Map

### New files

- `app/schema.py`: canonical cards-table DDL and card-index definitions shared by fresh initialization and migrations.
- `tests/test_rewinding_workflow.py`: focused domain, persistence, lifecycle, shift-attribution, and route coverage for Task 11.
- `tests/test_rewinding_ui_script_safety.py`: fixture/verifier path, preflight, and no-install safety coverage.
- `scripts/create_rewinding_fixture.py`: guarded temporary browser-test fixture builder.
- `scripts/verify_rewinding_ui.mjs`: task-specific Playwright workflow and visual assertions.
- `docs/implementation-notes/rewinding-return-workflow.md`: durable rationale, lifecycle, recovery, and migration notes.

### Existing files to modify

- `app/constants.py`: new status and semantic status groups.
- `app/db.py`: schema import, marker persistence, finish branching, final-shift attribution, waiting-card queries, roll/default rules, admin timing rules, and polling signature.
- `app/migrations.py`: M004 rebuild, validation, and atomic startup migration runner.
- `app/main.py`: marker route, terminal context, finish feedback, waiting-pane data, per-row roll save data, and display formatting.
- `app/templates/terminal.html`: third header button/pane, marker dialog, selected-card action hierarchy, accepted roll table, per-row editor, and dirty-state interactions.
- `app/templates/admin_card_detail.html`: waiting status/count presentation.
- `app/templates/admin_cards.html`: waiting status label/filter presentation through shared status labels.
- `app/static/css/app.css`: admin waiting-status pill.
- `tests/test_migrations.py`: M004 matrix and startup transaction guarantees.
- `tests/test_finish_cancel_history.py`: paused-finish regression across both finish branches.
- `tests/test_roll_entry.py`: waiting/completed late-roll attribution and row-edit invariants.
- `tests/test_terminal_sync.py`: waiting-pane polling invalidation.
- `tests/test_terminal_v8_render.py`: server-rendered Task 11 structure and accessible labels.
- `tests/test_shift_routes.py`: active-shift gating for the new terminal mutation route.
- `tests/test_admin_production_corrections.py`: timing edits on waiting cards.
- `tests/test_admin_card_detail_redesign.py`: waiting admin detail rendering/actions.
- `tests/test_print_output.py`: waiting remains non-printable.
- `tests/test_baseline.py`: overwrite re-import preservation for both new card fields.
- `v2-files/prototypes/rewinding-roll-controls/`: accepted, read-only Task 11 visual reference and verifier.
- `README.md`, `AGENTS.md`, `v2-files/PLAN.md`, and `v2-files/AGENTS.md`: confirmed scope, current behavior, task status, and migration register.

## Task 1: Make the Cards Schema Migration-Safe and Add M004

**Interfaces produced:**

- `app.schema.cards_table_sql(table_name: str = "cards", if_not_exists: bool = True) -> str`
- `app.schema.CARD_INDEX_SQL: tuple[str, ...]`
- `app.schema.extend_cards_rebuild_target(connection: sqlite3.Connection, source_table: str, target_table: str) -> tuple[str, ...]`
- `app.migrations.validate_rewinding_schema(connection: sqlite3.Connection) -> None`
- `app.migrations.ensure_foreign_keys_valid(connection: sqlite3.Connection, message: str) -> None`
- `app.migrations.apply_startup_migrations(connection: sqlite3.Connection) -> tuple[int, ...]`
- Migration registry entry `004 / rewinding_return_workflow`

**Interfaces consumed:** Existing `cards_table_sql()` and card indexes from `app/db.py`; the migration registry and schema validators in `app/migrations.py`.

**Files:**

- Create: `app/schema.py`
- Modify: `app/constants.py`
- Modify: `app/db.py`
- Modify: `app/migrations.py`
- Test: `tests/test_migrations.py`

- [ ] **Step 1: Add failing fresh-schema and constraint tests**

Add these assertions to the existing fresh-database migration test, using the literal `"awaiting_rewinding"` until the production constant is added in Step 3:

```python
columns = {
    row["name"]: row
    for row in connection.execute("PRAGMA table_info(cards)").fetchall()
}
assert "rewinding_roll_count" in columns
assert "final_extrusion_shift_occurrence_id" in columns

migrations = connection.execute(
    "SELECT version, name FROM schema_migrations ORDER BY version"
).fetchall()
assert [(row["version"], row["name"]) for row in migrations] == [
    (1, "shift_manager_import_fields"),
    (2, "shift_management"),
    (3, "roll_pallet_assignment"),
    (4, "rewinding_return_workflow"),
]
```

Add direct constraint cases in a temporary database:

```python
connection.execute(
    "UPDATE cards SET rewinding_roll_count = 1 WHERE id = ?",
    (card_id,),
)
connection.execute(
    "UPDATE cards SET status = ? WHERE id = ?",
    ("awaiting_rewinding", card_id),
)

for invalid_count in (0, -1, 1000, 1.5, "invalid"):
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE cards SET rewinding_roll_count = ? WHERE id = ?",
            (invalid_count, card_id),
        )
```

Verify the new foreign key points to `shift_occurrences(id)` with `ON DELETE RESTRICT` using `PRAGMA foreign_key_list(cards)`.

- [ ] **Step 2: Run the focused tests and confirm the expected failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_migrations.py -q
```

Expected: failure because M004 and both columns do not exist.

- [ ] **Step 3: Centralize cards DDL without changing existing columns**

Move the current cards-table SQL from `app/db.py` into `app/schema.py` verbatim, parameterize only the table name and `IF NOT EXISTS`, and add these exact columns:

```sql
rewinding_roll_count INTEGER CHECK (
    rewinding_roll_count IS NULL OR (
        typeof(rewinding_roll_count) = 'integer'
        AND rewinding_roll_count BETWEEN 1 AND 999
    )
),
final_extrusion_shift_occurrence_id INTEGER
    REFERENCES shift_occurrences(id) ON DELETE RESTRICT,
```

Move the existing card-index SQL into `CARD_INDEX_SQL`. Update `app/db.py` to import and execute those definitions. Do not duplicate the canonical cards DDL in migrations.

Move the current identifier quoting and safe legacy declared-type handling into `app/schema.py`. Implement `extend_cards_rebuild_target()` by adding every source-only legacy column to the target with that safe declared type, then returning the target-ordered tuple of columns present in both tables. M004 uses this helper; the obsolete archived-status compatibility rebuild is removed in Step 5.

Define the semantic status groups explicitly in `app/constants.py`:

```python
STATUS_AWAITING_REWINDING = "awaiting_rewinding"

STATUS_LABELS = {
    STATUS_IMPORTED: "Импортирана",
    STATUS_PENDING: "Изчакване",
    STATUS_RUNNING: "Изработване",
    STATUS_PAUSED: "Паузирана",
    STATUS_COMPLETED: "Произведена",
    STATUS_ARCHIVED: "Завършена",
    STATUS_CANCELLED: "Анулирана",
    STATUS_AWAITING_REWINDING: "Изчаква пренавиване",
}

WAITING_REWINDING_STATUSES = (STATUS_AWAITING_REWINDING,)
EXTRUSION_ENDED_STATUSES = (
    STATUS_AWAITING_REWINDING,
    STATUS_COMPLETED,
    STATUS_ARCHIVED,
)
TERMINAL_VISIBLE_STATUSES = (
    *ACTIVE_TERMINAL_STATUSES,
    STATUS_AWAITING_REWINDING,
    *TERMINAL_ARCHIVE_STATUSES,
)
```

Add the new value to `CARD_STATUSES`, but do not add it to active, production-complete, printable, archive-eligible, or queue status groups.

- [ ] **Step 4: Add the M004 rebuild**

Register:

```python
Migration(
    version=4,
    name="rewinding_return_workflow",
    apply=apply_m004_rewinding_return_workflow,
)
```

Implement `apply_m004_rewinding_return_workflow()` as a deterministic cards-table rebuild:

1. Create `cards_m004` with `cards_table_sql("cards_m004", if_not_exists=False)`.
2. Read source and target columns with `PRAGMA table_info`.
3. Call `extend_cards_rebuild_target()` so every source-only legacy extension column is recreated safely and returned in target order alongside the canonical common columns.
4. Copy that returned column tuple exactly. The two new canonical columns naturally remain at their `NULL` defaults when absent from the source, while valid partially deployed values are preserved and validated.
5. Drop the old `cards`, rename `cards_m004` to `cards`, and recreate every entry in `CARD_INDEX_SQL`.
6. Do not infer a final shift from timing or roll history during migration; runtime fallback owns legacy attribution.

The migration must preserve imported fields, machine assignment/sequence, production status, version/timestamps, roll/timing child rows, Task 10 pallet data, and unknown legacy extension columns that the current compatibility policy already retains.

- [ ] **Step 5: Make startup migration application atomic for a parent-table rebuild**

Move the existing `ensure_foreign_keys_valid()` helper from `app/db.py` to `app/migrations.py` so the migration runner can use it without a circular import. Replace the pre-migration cards-status repair path with one caller-owned startup transaction. Foreign keys must be disabled before `BEGIN`, not during it:

```python
def apply_startup_migrations(connection: sqlite3.Connection) -> tuple[int, ...]:
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN")
        applied_versions = apply_pending_migrations(connection)
        validate_shift_management_schema(connection)
        validate_roll_pallet_schema(connection)
        validate_rewinding_schema(connection)
        ensure_foreign_keys_valid(
            connection,
            "migration foreign key check failed",
        )
        connection.commit()
        return applied_versions
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
```

Call this from `init_db()`. Migration `apply` functions must not commit. Remove the obsolete `ensure_cards_status_constraint()` startup call and helper after its behavior is covered by M004.

- [ ] **Step 6: Validate both metadata and stored data**

`validate_rewinding_schema()` must verify:

- both columns exist with the expected SQLite metadata;
- the final-shift foreign key targets `shift_occurrences(id)` with `RESTRICT` delete behavior;
- no stored count is non-integer, below `1`, or above `999`;
- every stored final-shift ID resolves;
- a savepoint probe accepts `awaiting_rewinding` and rejects an unknown card status;
- the full `PRAGMA foreign_key_check` remains empty.

The probes must always roll back to and release their savepoint.

- [ ] **Step 7: Complete the migration matrix**

Add tests for:

- a fresh database;
- the oldest accepted legacy schema;
- a database recorded through M003;
- a partially deployed schema containing valid new columns/data;
- a partial schema with invalid count or dangling final-shift data;
- a database claiming M004 while missing/misdefining either column or constraint;
- preservation of all card data and roll/timing/pallet child rows;
- idempotent repeated startup;
- an injected failure after the cards copy proving DDL, data, and `schema_migrations` all roll back;
- `PRAGMA foreign_keys` is restored to `1` after success and failure.

- [ ] **Step 8: Run focused and full migration checks**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_migrations.py -q
python -m pytest tests/test_baseline.py tests/test_migrations.py -q
```

Expected: all selected tests pass and no test opens the real runtime database.

- [ ] **Step 9: Review checkpoint**

Run:

```bash
git diff -- app/schema.py app/constants.py app/db.py app/migrations.py tests/test_migrations.py
git diff --check
```

Confirm there is one canonical cards DDL, M004 has no historical inference, and startup rollback is proven. If and only if the user explicitly authorizes a commit:

```bash
git add app/schema.py app/constants.py app/db.py app/migrations.py tests/test_migrations.py
git commit -m "Add rewinding workflow schema migration"
```

## Task 2: Persist and Expose the Rewinding Marker

**Interfaces produced:**

- `app.db.parse_rewinding_roll_count(value: str) -> tuple[int | None, str | None]`
- `app.db.update_rewinding_roll_count(card_id: int, loaded_version: int, count: int | None, require_active_shift: bool = False) -> RuleResult`
- `rewinding_roll_count` in terminal/admin card mappings

**Interfaces consumed:** `RuleResult`, version-conflict helpers, active-shift gate, terminal mutation transaction pattern.

**Files:**

- Modify: `app/db.py`
- Create: `tests/test_rewinding_workflow.py`
- Modify: `tests/test_terminal_sync.py`

- [ ] **Step 1: Write parser and mutation tests first**

Parameterize the parser contract:

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", None),
        ("   ", None),
        ("0", None),
        ("000", None),
        ("1", 1),
        ("002", 2),
        ("999", 999),
    ],
)
def test_parse_rewinding_roll_count_accepts_supported_values(raw, expected):
    assert db.parse_rewinding_roll_count(raw) == (expected, None)
```

Reject `-1`, `1.5`, `1,5`, whitespace-separated digits, non-digits, and `1000` with one stable Bulgarian message:

```python
REWINDING_COUNT_ERROR = (
    "Броят за пренавиване трябва да бъде цяло число от 1 до 999."
)
```

Test that an update:

- succeeds for running, paused, and waiting cards;
- clears with `None` while leaving waiting status unchanged;
- rejects pending, completed, archived, and cancelled cards;
- requires a current active shift when called from terminal workflow;
- increments `version` exactly once and updates `updated_at`;
- rejects stale `loaded_version` without changing the stored count.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_rewinding_workflow.py -q
```

Expected: failure because the parser and mutation do not exist.

- [ ] **Step 3: Implement parsing and transactional mutation**

Accept ASCII decimal digits only. Normalize all-zero text to `None`; normalize leading zeros on a positive value to the corresponding integer. Keep parsing separate from persistence so the route can return field-level feedback.

Implement the mutation with `BEGIN IMMEDIATE`, fetch the card with its current version/status, enforce the permitted statuses and optional active-shift gate, then update with the optimistic predicate:

```sql
UPDATE cards
SET rewinding_roll_count = ?,
    version = version + 1,
    updated_at = ?
WHERE id = ? AND version = ?
```

Return the repository’s existing stale-write result if `rowcount != 1`.

- [ ] **Step 4: Expose the value consistently**

Add both new columns to:

- terminal selected-card detail;
- terminal active/waiting/completed list rows where relevant;
- admin list and detail queries;
- the admin production-action fetch;
- re-import preservation assertions.

Do not expose the count in completed/archived UI even though the historical value remains stored.

- [ ] **Step 5: Add waiting identity to terminal polling**

Extend `terminal_snapshot()` with a stable, ordered waiting-card signature. Each element must contain:

```python
{
    "id": row["id"],
    "status": row["status"],
    "version": row["version"],
    "updated_at": row["updated_at"],
    "finished_at": row["finished_at"],
    "rewinding_roll_count": row["rewinding_roll_count"],
}
```

Order it the same way the pane will render: `finished_at DESC, id DESC`. Add sync tests showing that entering waiting, editing/clearing the count, adding/editing/deleting a roll, and completing the card all change the snapshot token.

- [ ] **Step 6: Run focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_rewinding_workflow.py tests/test_terminal_sync.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Review checkpoint**

Run:

```bash
git diff -- app/db.py tests/test_rewinding_workflow.py tests/test_terminal_sync.py
git diff --check
```

Confirm blank/zero clearing is not represented as stored `0`, waiting status is not cleared by marker edits, and stale writes are side-effect free. If explicitly authorized:

```bash
git add app/db.py tests/test_rewinding_workflow.py tests/test_terminal_sync.py
git commit -m "Persist rewinding roll markers"
```

## Task 3: Branch `Приключи` Across the Approved Lifecycle

**Interfaces produced:** One `finish_card()` operation supporting normal completion, active-to-waiting, and waiting-to-completed transitions.

**Interfaces consumed:** Existing timing integrity checks, roll-ledger completion validation, active-shift lookup, queue normalization, optimistic version rules.

**Files:**

- Modify: `app/db.py`
- Modify: `tests/test_rewinding_workflow.py`
- Modify: `tests/test_finish_cancel_history.py`

- [ ] **Step 1: Write the lifecycle tests before changing `finish_card()`**

Cover this state table:

| Starting state | Marker | Required data | Result |
|---|---:|---|---|
| running | absent | current finish requirements | completed |
| paused | absent | current finish requirements | completed; no new segment |
| running | positive | timer started only | awaiting; open segment closed |
| paused | positive | timer started only | awaiting; no new segment |
| awaiting | any/cleared | current finish requirements | completed; production times unchanged |

For active-to-waiting, assert in one committed outcome:

```python
assert card["status"] == STATUS_AWAITING_REWINDING
assert card["finished_at"] is not None
assert card["final_extrusion_shift_occurrence_id"] == active_shift_id
assert card["machine_id"] == original_machine_id
assert card["machine_sequence"] == original_machine_sequence
assert fetch_open_timing_segment(connection, card_id) is None
```

Also assert the remaining active machine queue is contiguous from `1`, a completely roll-less card can enter waiting, and the machine can immediately start its next card.

For waiting-to-completed, snapshot `started_at`, every timing segment, `finished_at`, final shift, machine assignment, and version before the action. Assert only status/version/update metadata change.

- [ ] **Step 2: Add failure and concurrency tests**

Test that:

- active-to-waiting fails if the timer never started;
- waiting-to-completed fails with no gross rolls, missing tare/net, or an incomplete roll gap;
- pallet absence does not block any branch;
- a stale finish fails without closing a segment, normalizing a queue, or changing status;
- repeated finish submission cannot re-close timing or change final shift;
- finishing a waiting card while a malformed open timing segment exists is rejected as lifecycle corruption;
- an active card cannot enter waiting without an active shift occurrence.

- [ ] **Step 3: Run the tests and observe the branch failures**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_rewinding_workflow.py tests/test_finish_cancel_history.py -q
```

Expected: new cases fail against the current completed-only implementation.

- [ ] **Step 4: Refactor `finish_card()` around an explicit transition decision**

Keep the public signature stable. Inside one `BEGIN IMMEDIATE` transaction:

1. Fetch a finish-action row in active or waiting status, including version, marker, timing fields, and final shift.
2. Enforce the active-shift gate before any write.
3. If already waiting, run the existing completed-card ledger validation, require no open segment, update status to completed, and do not change `finished_at` or final shift.
4. If active with a positive marker, require that timing started. Close the open segment only when running; require no open segment when paused. Store `finished_at`, the active shift, and waiting status while preserving machine/sequence history.
5. If active with no marker, run the existing complete ledger validation, close timing as today, store `finished_at` and the active final shift, and set completed status while preserving current machine/sequence behavior.
6. Normalize the former machine’s active queue only for transitions out of an active state.
7. Perform exactly one version-checked cards update for the chosen branch and commit only after every invariant succeeds.

Use explicit predicates rather than broadening `ACTIVE_TERMINAL_STATUSES` or `PRODUCTION_COMPLETE_STATUSES`.

- [ ] **Step 5: Preserve current paused behavior**

Update the existing paused-finish regression to test both marker absent and marker positive. Confirm neither creates a zero-duration timing segment or moves a prior segment’s end.

- [ ] **Step 6: Run focused lifecycle tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_rewinding_workflow.py tests/test_finish_cancel_history.py tests/test_production_timing.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Review checkpoint**

Run:

```bash
git diff -- app/db.py tests/test_rewinding_workflow.py tests/test_finish_cancel_history.py
git diff --check
```

Trace all three successful branches and every rollback path. If explicitly authorized:

```bash
git add app/db.py tests/test_rewinding_workflow.py tests/test_finish_cancel_history.py
git commit -m "Add rewinding waiting lifecycle"
```

## Task 4: Attribute Returned Rolls and Permit Waiting-Card Corrections

**Interfaces produced:** Stable final-extrusion-shift attribution and explicitly scoped waiting-card edit rules.

**Interfaces consumed:** `final_extrusion_shift_occurrence_id`, roll entry/update/delete functions, card default/material corrections, admin timing corrections.

**Files:**

- Modify: `app/db.py`
- Modify: `tests/test_rewinding_workflow.py`
- Modify: `tests/test_roll_entry.py`
- Modify: `tests/test_admin_production_corrections.py`

- [ ] **Step 1: Add late-roll attribution tests**

Test these exact precedence rules:

1. A running card’s new roll belongs to the current active shift.
2. A waiting, completed, or archived card with `final_extrusion_shift_occurrence_id` uses that stored shift, even if a different shift is currently active.
3. A legacy completed/archived card without the stored field uses the most recent non-null shift linked to an existing roll on that card.
4. A legacy card with neither source stores `NULL`; it does not guess from timing timestamps or the current shift.
5. The terminal route still requires some current active shift before allowing the mutation, even when attribution resolves to a historical shift.

Add a two-shift scenario where shift one starts the card, shift two ends it, and every returned roll is entered under shift three. Assert every returned roll counts toward shift two.

- [ ] **Step 2: Add waiting-card roll/default/correction tests**

Assert waiting cards can:

- add a roll with gross, snapshot tare, snapshot pallet, net, next per-card roll number, final shift, and version bump in one transaction;
- edit gross, roll tare, and pallet atomically;
- delete any roll, including the final roll, because waiting is not production-complete;
- change order-level current tare and current pallet defaults without retroactively changing existing rolls;
- correct material and batch fields under the same rules currently available after production;
- edit or clear the rewinding marker without leaving waiting.

Assert they cannot start, pause, resume, cancel, archive, or be resequenced.

- [ ] **Step 3: Add waiting-card admin timing tests**

Use `EXTRUSION_ENDED_STATUSES` only where timing corrections need it. Assert:

- at least one valid timing segment must remain for a waiting card;
- open segments cannot be added to waiting cards;
- adding/editing/deleting closed segments recomputes total duration and `finished_at` using the same extrusion-ended rule as completed/archived cards;
- these corrections do not change waiting status, final shift, rewinding count, roll data, or queue state.

- [ ] **Step 4: Run the focused tests and confirm current failures**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_rewinding_workflow.py tests/test_roll_entry.py tests/test_admin_production_corrections.py -q
```

- [ ] **Step 5: Implement a single attribution resolver**

Extend the existing helper without changing its return convention:

```python
def resolve_new_roll_shift_occurrence_id(
    connection: sqlite3.Connection,
    card: sqlite3.Row,
) -> tuple[int | None, RuleResult]:
    if card["status"] == STATUS_RUNNING:
        active_shift = fetch_active_shift_row(connection)
        if active_shift is None:
            return None, RuleResult(
                False,
                ("Отворете смяна, преди да добавите ролка.",),
            )
        return int(active_shift["id"]), RuleResult(True)
    if card["status"] in (
        STATUS_AWAITING_REWINDING,
        STATUS_COMPLETED,
        STATUS_ARCHIVED,
    ):
        if card["final_extrusion_shift_occurrence_id"] is not None:
            return (
                int(card["final_extrusion_shift_occurrence_id"]),
                RuleResult(True),
            )
        inherited_id = fetch_latest_linked_roll_shift_occurrence_id(
            connection,
            int(card["id"]),
        )
        return inherited_id, RuleResult(True)
    return None, RuleResult(
        False,
        ("Картата не позволява добавяне на ролка.",),
    )
```

Extract the current latest-linked-roll query into `fetch_latest_linked_roll_shift_occurrence_id()` and select `final_extrusion_shift_occurrence_id` in `fetch_roll_action_card()`.

- [ ] **Step 6: Extend permitted action scopes narrowly**

- Include waiting in the roll-action fetch and card default/material correction scopes.
- Keep waiting out of `PRODUCTION_COMPLETE_STATUSES` so existing “cannot delete final roll” protections continue only for completed/archived cards.
- Add waiting to `EXTRUSION_ENDED_STATUSES` for timing correction rules without adding it to print/archive eligibility.
- Extend `save_roll_weight()`/`update_roll_weight()` so a row edit can submit `pallet_number` alongside gross and tare; preserve the existing value when that form field is deliberately omitted by non-terminal callers.
- Keep the add-roll transaction atomic: gross, tare snapshot, pallet snapshot, net, shift attribution, roll number, and card version either all commit or all roll back.

- [ ] **Step 7: Run roll, timing, and shift-summary regressions**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_rewinding_workflow.py tests/test_roll_entry.py tests/test_admin_production_corrections.py tests/test_shift_management.py -q
```

Expected: returned rolls appear in the final extrusion shift summary, and all selected tests pass.

- [ ] **Step 8: Review checkpoint**

Run:

```bash
git diff -- app/db.py tests/test_rewinding_workflow.py tests/test_roll_entry.py tests/test_admin_production_corrections.py
git diff --check
```

Confirm no current shift is substituted for a known historical final shift. If explicitly authorized:

```bash
git add app/db.py tests/test_rewinding_workflow.py tests/test_roll_entry.py tests/test_admin_production_corrections.py
git commit -m "Attribute returned rolls to the final extrusion shift"
```

## Task 5: Add Terminal Routes, Context, and Feedback

**Interfaces produced:**

- `POST /terminal/cards/{card_id}/rewinding-count`
- Waiting cards/count in `/terminal` context
- Branch-specific successful finish notice while preserving the current selected card

**Interfaces consumed:** marker parser/mutation, branched `finish_card()`, terminal availability/active-shift guard, feedback redirect helpers.

**Files:**

- Modify: `app/main.py`
- Modify: `app/db.py`
- Modify: `tests/test_rewinding_workflow.py`
- Modify: `tests/test_terminal_sync.py`
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_shift_routes.py`

- [ ] **Step 1: Write route tests first**

For `POST /terminal/cards/{id}/rewinding-count`, test:

- positive marker set and redirect back to the same selected card;
- blank/zero clear;
- invalid input preserves the submitted value and targets feedback to the rewinding dialog;
- missing/invalid `loaded_version`;
- stale version;
- no active shift;
- terminal unavailable;
- forbidden card status;
- successful mutation emits a concise Bulgarian notice.

For the existing finish route, assert:

- active-to-waiting redirects with `card_id` still selected and an “extrusion ended; waiting for rewinding” notice;
- waiting-to-completed redirects with the normal completion notice and the same card selected in Produced Orders behavior;
- neither success auto-opens the waiting pane;
- validation errors remain attached to the selected card and relevant control.

- [ ] **Step 2: Run the focused route tests and confirm failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_rewinding_workflow.py tests/test_terminal_sync.py -q
```

- [ ] **Step 3: Implement the marker route**

Follow the current terminal mutation sequence exactly:

1. Parse `loaded_version`.
2. Enforce terminal availability and active shift.
3. Parse the marker text.
4. Call `update_rewinding_roll_count(..., require_active_shift=True)`.
5. On success, use PRG back to `/terminal/cards/{id}?notice=rewinding_saved`.
6. On failure, render the selected card with `rewinding_result`, `rewinding_result_value` containing the raw submitted text, and `rewinding_dialog_open=True`.

Do not add JSON state or a client-only save path.

Add these exact entries to `TERMINAL_NOTICE_MESSAGES`:

```python
"rewinding_saved": ("Ролките за пренавиване са записани.",),
"card_awaiting_rewinding": (
    "Екструдирането е приключено. Картата изчаква пренавиване.",
),
```

Extend `build_terminal_feedback()` with a `rewinding` error target, `open_rewinding_dialog`, and the raw `rewinding_result_value`. Process `rewinding_result` through the same stale-card and no-active-shift branches as every other card write; stale feedback opens the existing refresh-required alert, while ordinary validation feedback reopens only the marker dialog.

- [ ] **Step 4: Build waiting context deterministically**

Add a dedicated DB query for waiting cards ordered by `finished_at DESC, id DESC`. In `terminal_context()`, provide:

```python
{
    "waiting_rewinding_cards": waiting_cards,
    "waiting_rewinding_count": len(waiting_cards),
}
```

Enrich each row with the same order/card display identity used by Produced Orders and the exact count label `"{rewinding_roll_count or 0} ролки"`.

- [ ] **Step 5: Select the finish notice after the transaction**

After a successful `finish_card()`, refetch the selected card. If its status is `awaiting_rewinding`, use notice code `card_awaiting_rewinding`, whose message is:

```text
Екструдирането е приключено. Картата изчаква пренавиване.
```

Otherwise use the current completed-card notice. Keep the same route and confirmation dialog; do not auto-open any pane.

- [ ] **Step 6: Centralize finish confirmation text**

Continue using the current mixed-pallet warning whenever its existing predicate is true, regardless of the finish branch. Do not create a separate rewinding-specific pallet predicate. Otherwise show the existing generic `Are you sure` equivalent in Bulgarian.

Add route/render tests for the warning in all three contexts and for the generic confirmation when every roll has a pallet, every gross roll lacks a pallet, or no rolls exist.

- [ ] **Step 7: Run route and terminal-service tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_rewinding_workflow.py tests/test_terminal_sync.py tests/test_terminal_v8_render.py tests/test_shift_routes.py -q
```

- [ ] **Step 8: Review checkpoint**

Run:

```bash
git diff -- app/main.py app/db.py tests/test_rewinding_workflow.py tests/test_terminal_sync.py tests/test_terminal_v8_render.py tests/test_shift_routes.py
git diff --check
```

Confirm every terminal write has both the active-shift gate and version predicate. If explicitly authorized:

```bash
git add app/main.py app/db.py tests/test_rewinding_workflow.py tests/test_terminal_sync.py tests/test_terminal_v8_render.py tests/test_shift_routes.py
git commit -m "Expose rewinding workflow terminal actions"
```

## Task 6: Build the Waiting Pane and Marker Interaction

**Interfaces produced:** Accepted third header button, badge, centered waiting pane, and accessible marker dialog.

**Interfaces consumed:** terminal context from Task 5; existing selected-card and drawer JavaScript.

**Files:**

- Modify: `app/templates/terminal.html`
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_rewinding_workflow.py`

- [ ] **Step 1: Add failing render-structure tests**

Parse the returned HTML and assert:

- one header button named `Изчакващи пренавиване`;
- `data-waiting-count` contains the number of cards;
- the badge is absent/hidden at zero and reads the exact number above zero;
- the waiting pane has dialog semantics, a heading, close control, and rows in newest-finished order;
- each waiting row contains the card identity, `N ролки`, and a link selecting that card;
- waiting cards do not appear in Queue or Produced Orders, while completed cards remain absent from the waiting pane;
- the pane is not open in initial HTML after a finish redirect;
- the marker button reads `Пренавиване` when clear and `Пренавиване: N` when set;
- the marked button uses the accepted amber state;
- the marker dialog contains a numeric text/input control, Save, Clear through blank/zero semantics, and Cancel.

- [ ] **Step 2: Run the render tests and confirm failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py tests/test_rewinding_workflow.py -q
```

- [ ] **Step 3: Add the third header control**

Change the central header-actions layout from two columns to three equal columns in the approved lifecycle order: `Чакащи поръчки`, `Изчакващи пренавиване`, `Произведени поръчки`. Position the badge at the waiting button’s bottom-right, keep it readable at `1366×768`, and hide it completely when the count is zero.

- [ ] **Step 4: Add a centered waiting pane**

Implement the pane as a centered modal layer, not a side drawer. Reuse the existing Produced row visual language and ordering. Render the established empty-state treatment when there are no rows. It must:

- open only from its header button;
- close from its close button, Escape, or backdrop;
- restore focus to the trigger;
- not auto-open after marker save or either finish branch;
- be mutually exclusive with Queue, Produced, marker, and row-editor modal states;
- respect existing unsaved/dirty edit navigation protection.

Selecting a row closes the pane and navigates to that card’s normal terminal detail.

- [ ] **Step 5: Add the marker dialog**

Place `Пренавиване` in the secondary roll-panel action row only for running, paused, and waiting cards. Submit to the server route from Task 5 with `loaded_version`. Use `type="text"`, `inputmode="numeric"`, `pattern="[0-9]{0,3}"`, and `maxlength="3"`, while retaining backend validation as authoritative.

Use the normal navy treatment for Save and a non-destructive Cancel. On invalid submission, reopen only this dialog, display the returned message adjacent to the field, preserve the raw submitted value, and focus the field. Cancel/Escape must make no mutation and restore focus.

- [ ] **Step 6: Add the inert roll-change control**

Add `Смяна на ролка` beside the marker control with `type="button"`. Give it the accepted secondary styling but no click listener, form action, route, modal, tooltip promise, or production-data effect.

- [ ] **Step 7: Run render tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py tests/test_rewinding_workflow.py tests/test_terminal_sync.py -q
```

- [ ] **Step 8: Review checkpoint**

Run:

```bash
git diff -- app/templates/terminal.html tests/test_terminal_v8_render.py tests/test_rewinding_workflow.py
git diff --check
```

Confirm there is no roll-change behavior and no automatic pane opening. If explicitly authorized:

```bash
git add app/templates/terminal.html tests/test_terminal_v8_render.py tests/test_rewinding_workflow.py
git commit -m "Add terminal rewinding queue controls"
```

## Task 7: Transfer the Accepted Roll-Panel Design to the Real Terminal

**Interfaces produced:** Accepted selected-card control hierarchy, aligned roll inputs, one-decimal read table, and one-row-at-a-time editor.

**Interfaces consumed:** existing add/update/delete roll routes, Task 4 row-level pallet support, accepted prototype.

**Files:**

- Modify: `app/main.py`
- Modify: `app/templates/terminal.html`
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_roll_entry.py`

- [ ] **Step 1: Add failing render and route tests for the accepted structure**

Assert:

- Start, Pause, and End occupy equal primary-button slots for active cards;
- waiting cards show active `Приключи` but no Start/Pause action;
- the old order-level overflow menu is absent;
- roll inputs are labeled exactly `Ролка`, `Шпула`, `Палет` with border-embedded labels and no outer group border;
- Add Roll aligns to the input row and retains its existing Bulgarian name;
- table columns are exactly `№`, `Бруто`, `Шпула`, `Нето`, `Палет`, then the unlabeled row-action column;
- the first five data columns use equal layout widths;
- weight headings contain no `кг`;
- read values render with one decimal while edit inputs retain exact stored values up to two decimals;
- every row has one pencil control and only one row may be editing at a time;
- an editing row exposes Save, Cancel, and Delete, with the delete confirmation naming the roll number.

Add route tests proving a row save changes gross, that roll’s tare, and pallet in one version-checked request and leaves other rolls unchanged.

- [ ] **Step 2: Run focused tests and confirm failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py tests/test_roll_entry.py -q
```

- [ ] **Step 3: Reuse the established one-decimal display formatter**

Use the existing `app.main.one_decimal_weight_display()` helper, which already applies `Decimal("0.1")` with `ROUND_HALF_UP`, for the roll table’s gross, tare, and net read values. Add those display values during terminal-card enrichment rather than formatting inside Jinja.

Keep form values sourced from the exact stored representation rather than the one-decimal helper, so editing `12.34` never silently becomes `12.3`.

- [ ] **Step 4: Rebuild only the real roll-panel hierarchy**

Match the approved prototype within the real terminal card:

1. primary lifecycle controls at the top;
2. secondary `Пренавиване` and inert `Смяна на ролка` controls beneath;
3. `Ролка`, `Шпула`, and `Палет` default/input fields and the centered/aligned Add Roll primary action;
4. equally distributed roll table beneath.

Remove the roll-input group border and remove the order-level overflow menu. Preserve all unrelated real terminal header, material, timing, feedback, and navigation structure.

- [ ] **Step 5: Replace batch row correction UI with per-row editing**

Use one form per row and the existing roll update/delete endpoints. A pencil selects exactly one row in JavaScript. The selected row replaces read spans with gross/tare/pallet inputs and exposes:

- Save: server submit with card and roll versions;
- Cancel: restore the read row without a request;
- Delete: existing delete form after an explicit confirmation naming `Ролка N`.

If a server validation or stale-write failure occurs, return `roll_result_roll_id` in terminal feedback, reopen that row only, preserve submitted values, and focus the first invalid field. Remove the old global/batch editor from the terminal UI; retaining a backend compatibility endpoint is allowed only if existing non-UI tests or callers require it.

- [ ] **Step 6: Preserve coordinated default autosave and atomic Add Roll**

The current order-level `current_tare_weight` and `current_pallet_number` remain coordinated defaults. When either changes, their autosave request must submit both current values in one version-checked mutation. Add Roll must snapshot both saved defaults with gross/net/shift/roll number in one transaction.

Update dirty-state logic so navigating to Queue, Produced, Waiting, or another card never silently discards an open row edit or unsaved defaults.

- [ ] **Step 7: Run the focused UI/service suite**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_v8_render.py tests/test_roll_entry.py tests/test_rewinding_workflow.py -q
```

- [ ] **Step 8: Compare against the fixed prototype**

Run the existing prototype verifier unchanged:

```bash
PROTOTYPE_URL=http://127.0.0.1:8765/prototype.html \
node v2-files/prototypes/rewinding-roll-controls/verify-prototype.mjs
```

Expected: `rewinding prototype checks passed`. This verifies the reference remains intact; it is not evidence that the live app is complete.

- [ ] **Step 9: Review checkpoint**

Run:

```bash
git diff -- app/main.py app/templates/terminal.html tests/test_terminal_v8_render.py tests/test_roll_entry.py
git diff --check
```

Compare the real roll panel side-by-side with the fixed prototype and confirm no unrelated terminal layout was replaced. If explicitly authorized:

```bash
git add app/main.py app/templates/terminal.html tests/test_terminal_v8_render.py tests/test_roll_entry.py
git commit -m "Apply accepted terminal roll controls"
```

## Task 8: Integrate Admin, Import, and Print Boundaries

**Interfaces produced:** Waiting status visibility for administrators without adding invalid admin lifecycle actions.

**Interfaces consumed:** shared status labels, admin detail/list rendering, overwrite import field whitelist, print eligibility.

**Files:**

- Modify: `app/main.py`
- Modify: `app/templates/admin_card_detail.html`
- Modify: `app/templates/admin_cards.html`
- Modify: `app/static/css/app.css`
- Modify: `tests/test_admin_card_detail_redesign.py`
- Modify: `tests/test_admin_production_corrections.py`
- Modify: `tests/test_print_output.py`
- Modify: `tests/test_baseline.py`

- [ ] **Step 1: Add admin rendering tests**

Assert a waiting card:

- shows Bulgarian status `Изчаква пренавиване` in admin list/detail;
- shows `Пренавиване: N` only while waiting;
- retains the existing admin imported fields, material corrections, timing history, rolls, and machine history;
- exposes no Cancel, Delete, Archive, or Print action;
- can be filtered by its exact status in the existing admin list filter.

Assert completed/archived cards with a stored historical count do not render the count.

- [ ] **Step 2: Add print-boundary tests**

Call every print route/service with a waiting card and assert the same non-printable rejection used for active cards. Then complete it and assert printing succeeds under the existing completed-card rules, uses the original extrusion `finished_at` as its stop time, and never renders the stored rewinding count. After the normal admin review/archive action, assert reprinting still works. Do not alter print templates or output mapping.

- [ ] **Step 3: Add overwrite-import preservation tests**

Re-import a waiting card in overwrite mode and assert it preserves:

- `status`;
- `rewinding_roll_count`;
- `final_extrusion_shift_occurrence_id`;
- `finished_at` and all timing segments;
- rolls, per-roll tare/net/pallet, current defaults, machine assignment/history, and versioned production data.

Only the existing imported/front-card whitelist may change.

- [ ] **Step 4: Run the tests and confirm missing presentation coverage**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py tests/test_admin_production_corrections.py tests/test_print_output.py tests/test_rewinding_workflow.py -q
```

- [ ] **Step 5: Implement labels and status pill only**

Use the shared waiting Bulgarian label added in Task 1 and add a visually distinct but secondary admin pill in `app/static/css/app.css`. Render the count conditionally on waiting status. Keep existing action predicates so no cancellation/archive/print action appears.

Do not create an admin “remove from waiting” operation; the only state-clearing operation is terminal `Приключи` after valid returned-roll entry.

- [ ] **Step 6: Run admin, import, and print regressions**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_admin_card_detail_redesign.py tests/test_admin_production_corrections.py tests/test_print_output.py tests/test_baseline.py tests/test_rewinding_workflow.py -q
```

- [ ] **Step 7: Review checkpoint**

Run:

```bash
git diff -- app/main.py app/templates/admin_card_detail.html app/templates/admin_cards.html app/static/css/app.css tests/test_admin_card_detail_redesign.py tests/test_admin_production_corrections.py tests/test_print_output.py tests/test_baseline.py tests/test_rewinding_workflow.py
git diff --check
```

Confirm waiting has administrative visibility but no administrative lifecycle shortcut. If explicitly authorized:

```bash
git add app/main.py app/templates/admin_card_detail.html app/templates/admin_cards.html app/static/css/app.css tests/test_admin_card_detail_redesign.py tests/test_admin_production_corrections.py tests/test_print_output.py tests/test_baseline.py tests/test_rewinding_workflow.py
git commit -m "Integrate rewinding status with admin and print rules"
```

## Task 9: Add a Guarded Live Browser Verification

**Interfaces produced:** Repeatable Task 11 fixture and Playwright evidence under ignored artifact paths.

**Interfaces consumed:** repo-local `.venv`, repo-local Playwright, temporary database startup convention.

**Files:**

- Create: `scripts/create_rewinding_fixture.py`
- Create: `scripts/verify_rewinding_ui.mjs`
- Create: `tests/test_rewinding_ui_script_safety.py`
- Create at runtime only: `.test-runtime/rewinding-ui.sqlite3`
- Create at runtime only: `.test-runtime/rewinding-ui.json`
- Create at runtime only: `artifacts/ui-checks/rewinding-return-workflow/`

- [ ] **Step 1: Add failing script-safety tests**

Model `tests/test_roll_pallet_ui_script_safety.py` and assert:

- the fixture rejects `data/extrusion_terminal.sqlite3` and any DB/output path outside `.test-runtime/`;
- a successful fixture run emits valid JSON whose resolved `db_path` is below `.test-runtime/` and whose card IDs cover every named scenario;
- fixture recreation is deterministic for the IDs referenced by the verifier;
- the verifier requires `BASE_URL`, `FIXTURE_JSON`, and `ARTIFACT_DIR`;
- the verifier rejects fixture/artifact paths that resolve outside their guarded roots;
- the verifier source contains the `/health` database-identity preflight before its first mutation;
- neither script invokes npm, npx, Playwright installation, or the runtime database.

- [ ] **Step 2: Run the safety tests and confirm failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_rewinding_ui_script_safety.py -q
```

Expected: failure because both scripts are absent.

- [ ] **Step 3: Build a deterministic fixture script**

Follow the existing roll/pallet fixture convention: require `--db-path` and `--output`, emit the fixture metadata JSON to the requested output path, and reject:

- the repository runtime DB path;
- either requested path outside `.test-runtime/`.

Initialize through normal `init_db()` and create:

- an active running card with rolls and mixed pallet assignment;
- an active paused card with a positive rewinding marker;
- at least two waiting cards with distinct `finished_at` values/counts;
- a waiting card with zero returned rolls;
- a completed Produced Orders card with editable rolls;
- an active shift and released follow-up queue card.

Use production DB functions where available; use direct SQL only for fixture timestamps/state combinations that cannot be reached deterministically without wall-clock waits.

- [ ] **Step 4: Build the Playwright verifier without installing anything**

Use the already installed `@playwright/test` module through `createRequire`, matching `scripts/verify_roll_pallet_ui.mjs`; do not install anything. Require `BASE_URL`, `FIXTURE_JSON`, and `ARTIFACT_DIR`. Resolve the database identity from the guarded fixture JSON, then call `/health` and assert the reported database path is exactly that file before any mutation. Abort if identity differs.

At `1920×768` and `1366×768`, verify:

1. the three header actions fit and the waiting badge count is correct;
2. waiting opens centered, rows are newest-first, Escape/backdrop/close work, and it does not auto-open;
3. selecting a waiting card renders its marker count and only the valid lifecycle action;
4. marker save, clear, invalid input, cancel, and stale-version feedback work;
5. a running/paused positive-marker finish shows the mixed-pallet warning when its existing predicate applies and ends in waiting;
6. the newly freed machine can start its next queue card;
7. a waiting card with no returned rolls cannot complete;
8. returned rolls can be added with changed count/cardinality and optional pallet;
9. final `Приключи` completes without changing timing/`finished_at` and moves the card to Produced Orders;
10. Start/Pause/End sizing, secondary actions, aligned fieldset labels, equal table columns, one-decimal display, pencil row editor, Cancel, Save, and Delete confirmation match the accepted design;
11. `Смяна на ролка` has no effect;
12. dirty edits prevent silent navigation to all three panes.

Collect `pageerror` and error-level console messages and fail if either collection is non-empty. At both viewports, assert the document and roll panel have no horizontal overflow and no relevant controls overlap or clip. Recreate the guarded fixture between mutating scenarios by spawning `scripts/create_rewinding_fixture.py` with the same `--db-path` and `--output`, matching the established roll/pallet verifier pattern.

Save screenshots at both viewport sizes, plus focused states for the waiting pane, marker dialog, waiting detail, row edit, and final Produced row. Save a JSON summary containing URL, database identity, viewport, assertions, console/page errors, and screenshot paths.

- [ ] **Step 5: Run syntax/import and safety checks for the verification assets**

Run:

```bash
source .venv/bin/activate
python -m py_compile scripts/create_rewinding_fixture.py
node --check scripts/verify_rewinding_ui.mjs
./node_modules/.bin/playwright --version
python -m pytest tests/test_rewinding_ui_script_safety.py -q
```

- [ ] **Step 6: Start the app against the guarded fixture**

Run in one terminal:

```bash
source .venv/bin/activate
python scripts/create_rewinding_fixture.py \
  --db-path .test-runtime/rewinding-ui.sqlite3 \
  --output .test-runtime/rewinding-ui.json
EXTRUSION_DB_PATH=.test-runtime/rewinding-ui.sqlite3 \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

- [ ] **Step 7: Run the live browser verification**

Run in a second terminal:

```bash
BASE_URL=http://127.0.0.1:8011 \
FIXTURE_JSON=.test-runtime/rewinding-ui.json \
ARTIFACT_DIR=artifacts/ui-checks/rewinding-return-workflow \
node scripts/verify_rewinding_ui.mjs
```

Expected: a zero exit status, JSON summary with every assertion passed, and the required screenshots under the artifact directory.

- [ ] **Step 8: Inspect the two full-page screenshots**

Open the `1920×768` and `1366×768` full-page images and confirm visually:

- no control overlap or clipping;
- equal primary sizes with usable left/right spacing around End;
- aligned `+ Добави ролка` content;
- evenly distributed table columns and unclumped roll number;
- centered waiting pane;
- Bulgarian strings and one-decimal weights.

- [ ] **Step 9: Review checkpoint**

Run:

```bash
git status --short
git diff -- scripts/create_rewinding_fixture.py scripts/verify_rewinding_ui.mjs tests/test_rewinding_ui_script_safety.py
git diff --check
```

Confirm `.test-runtime/` and `artifacts/` remain untracked/ignored. If explicitly authorized:

```bash
git add scripts/create_rewinding_fixture.py scripts/verify_rewinding_ui.mjs tests/test_rewinding_ui_script_safety.py
git commit -m "Add rewinding workflow browser verification"
```

## Task 10: Reconcile Durable Documentation and Run Final Verification

**Interfaces produced:** Repository documentation that matches the implemented workflow and migration state.

**Interfaces consumed:** completed implementation, test evidence, M004 schema facts, approved Task 11 spec.

**Files:**

- Create: `docs/implementation-notes/rewinding-return-workflow.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `v2-files/PLAN.md`
- Modify: `v2-files/AGENTS.md`
- Verify: `v2-files/TASK-11-REWINDING.md`

- [ ] **Step 1: Write the implementation note from verified behavior**

Record:

- the business reason and exact lifecycle state diagram;
- why waiting is neither active nor completed;
- marker range/clearing semantics and lack of count matching;
- timing behavior from running versus paused;
- final shift attribution and legacy fallback;
- roll/default/material/timing correction rules;
- pallet optionality and consistent warning behavior;
- recovery through Produced Orders when the marker was forgotten;
- UI strings and fixed prototype reference;
- M004 rebuild, transaction, rollback, and operational DB safety;
- exact automated and Playwright verification commands and artifact directory.

- [ ] **Step 2: Update repository scope and operating truth**

In `README.md` and root `AGENTS.md`, replace the broad rewinding exclusion with this bounded inclusion and explicitly retain rewinding-department scheduling/processing as out of scope. Update status/finish/print rules to include the waiting state and final-shift attribution.

In `v2-files/PLAN.md`, mark Task 11 implemented only after every verification below passes; retain any independent task statuses unchanged.

In `v2-files/AGENTS.md`, append M004 to the migration register with:

- migration name and files;
- schema fields/constraints/foreign key;
- fresh/upgrade/partial/malformed/rollback coverage;
- no runtime database mutation;
- exact verification result.

- [ ] **Step 3: Reconcile the approved Task 11 spec**

Read `v2-files/TASK-11-REWINDING.md` against the implementation. Correct only factual drift discovered during implementation; do not silently alter approved product behavior. Preserve its reference to the accepted prototype and all previously approved unrelated roll-panel visual changes.

- [ ] **Step 4: Run syntax/import checks and focused tests**

Run:

```bash
source .venv/bin/activate
python -m compileall -q app scripts tests
python -m pytest \
  tests/test_migrations.py \
  tests/test_rewinding_workflow.py \
  tests/test_finish_cancel_history.py \
  tests/test_roll_entry.py \
  tests/test_terminal_sync.py \
  tests/test_terminal_v8_render.py \
  tests/test_admin_production_corrections.py \
  tests/test_admin_card_detail_redesign.py \
  tests/test_print_output.py \
  tests/test_baseline.py \
  tests/test_shift_routes.py \
  tests/test_production_timing.py \
  tests/test_rewinding_ui_script_safety.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Run the complete automated suite**

Run:

```bash
source .venv/bin/activate
python -m pytest -q
```

Expected: every test passes; the result must exceed the pre-feature baseline of `686` tests because Task 11 adds coverage.

- [ ] **Step 6: Re-run the accepted reference and live-app browser checks**

Run:

```bash
PROTOTYPE_URL=http://127.0.0.1:8765/prototype.html \
node v2-files/prototypes/rewinding-roll-controls/verify-prototype.mjs

BASE_URL=http://127.0.0.1:8011 \
FIXTURE_JSON=.test-runtime/rewinding-ui.json \
ARTIFACT_DIR=artifacts/ui-checks/rewinding-return-workflow \
node scripts/verify_rewinding_ui.mjs
```

Expected: both commands exit zero. Capture the live-app output and inspect the latest screenshots before making a completion claim.

- [ ] **Step 7: Perform an adversarial data-integrity review**

Trace and document evidence for:

- every status transition and forbidden transition;
- stale marker, finish, roll, default, and correction submissions;
- transaction rollback after timing close but before status update;
- queue normalization and immediate machine reuse;
- no timing mutation during waiting finalization;
- exact late-roll shift attribution across shift changes;
- re-import preservation;
- print/archive/cancel exclusion;
- mixed-pallet warnings in all finish contexts;
- no runtime database access;
- no regression to Task 10 pallet persistence or print summaries.

- [ ] **Step 8: Scan the implementation and plan for unfinished shortcuts**

Run:

```bash
rg -n 'TB[D]|TO[DO]|implement lat[e]r|appropriate error handl[ing]|handle edge cas[es]|Write tests for the abov[e]|Similar to Tas[k]' \
  app tests scripts docs v2-files/TASK-11-REWINDING.md \
  docs/superpowers/plans/2026-07-26-rewinding-return-workflow.md
git diff --check
git status --short
```

Expected: no unfinished implementation shortcut, no whitespace error, and only intentional task/user changes present.

- [ ] **Step 9: Final review checkpoint**

Review the complete diff by file and ensure unrelated user changes remain untouched:

```bash
git diff --stat
git diff -- README.md AGENTS.md app docs scripts tests v2-files/PLAN.md v2-files/AGENTS.md v2-files/TASK-11-REWINDING.md
```

If and only if the user explicitly authorizes the final commit, stage the exact reviewed Task 11 paths and commit:

```bash
git add \
  README.md AGENTS.md \
  app/schema.py app/constants.py app/db.py app/migrations.py app/main.py \
  app/templates/terminal.html app/templates/admin_card_detail.html app/templates/admin_cards.html \
  app/static/css/app.css \
  docs/superpowers/plans/2026-07-26-rewinding-return-workflow.md \
  docs/implementation-notes/rewinding-return-workflow.md \
  scripts/create_rewinding_fixture.py scripts/verify_rewinding_ui.mjs \
  tests/test_migrations.py tests/test_rewinding_workflow.py tests/test_finish_cancel_history.py \
  tests/test_roll_entry.py tests/test_terminal_sync.py tests/test_terminal_v8_render.py \
  tests/test_admin_production_corrections.py tests/test_admin_card_detail_redesign.py tests/test_print_output.py \
  tests/test_baseline.py tests/test_shift_routes.py \
  tests/test_rewinding_ui_script_safety.py \
  v2-files/PLAN.md v2-files/AGENTS.md v2-files/TASK-11-REWINDING.md \
  v2-files/prototypes/rewinding-roll-controls/README.md \
  v2-files/prototypes/rewinding-roll-controls/design-qa.md \
  v2-files/prototypes/rewinding-roll-controls/example.JPG \
  v2-files/prototypes/rewinding-roll-controls/generate-prototype.mjs \
  v2-files/prototypes/rewinding-roll-controls/prototype.css \
  v2-files/prototypes/rewinding-roll-controls/prototype.html \
  v2-files/prototypes/rewinding-roll-controls/prototype.js \
  v2-files/prototypes/rewinding-roll-controls/verify-prototype.mjs
git commit -m "Implement rewinding return workflow"
```

The accepted prototype directory is currently part of the uncommitted Task 11 design record. Include those exact files only in the final user-authorized Task 11 commit, after verifying they remain unchanged during implementation.

## Completion Criteria

Task 11 is complete only when all of the following are true:

- M004 upgrades every supported schema atomically, validates itself, preserves child data, and is recorded in V2 migration documentation.
- Operators can mark running/paused cards, end extrusion into waiting, find them through the third centered pane, enter returned rolls, and deliberately complete them.
- A waiting card frees the machine and no longer occupies the active queue.
- Timing stops exactly once at extrusion end and never changes during ordinary returned-roll entry/finalization.
- Returned rolls count toward the final extrusion shift under the approved fallback rules.
- Pallet remains optional, and the existing mixed-pallet warning is consistent in all finish contexts.
- Waiting cards remain excluded from print, archive, cancel, delete, start, pause, resume, and queue sequencing.
- The real terminal matches the accepted control hierarchy and roll-table design at both required viewport sizes.
- Focused tests, the complete pytest suite, prototype verification, live Playwright verification, syntax checks, and `git diff --check` all pass with recorded evidence.
- README, both AGENTS files, V2 plan/spec, and the implementation note agree with the shipped behavior.
