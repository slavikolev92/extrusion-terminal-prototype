# Shift Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one global extrusion-shift workflow that attributes new roll production to a durable shift occurrence, blocks normal terminal use while no shift is open, and provides configurable shift choices plus live end/history summaries.

**Architecture:** Add schema-only migration M002 with a singleton terminal-configuration row, durable shift-occurrence rows, and a nullable foreign key from each roll to its occurrence. Keep lifecycle rules and live summary queries in the existing direct-`sqlite3` data layer, expose them through small FastAPI routes, and render one server-driven terminal modal with minimal JavaScript for confirmations and modal state. Preserve the existing card, machine, timing, roll-correction, and archive workflows; shift handoff changes attribution only.

**Tech Stack:** FastAPI, Jinja templates, direct `sqlite3`, SQLite migrations, pytest with temporary databases, vanilla JavaScript, repository-local Playwright.

## Global Constraints

- Read `AGENTS.md`, `v2-files/AGENTS.md`, and `v2-files/TASK-01-SHIFT-MANAGEMENT.md` before implementation. Do not use `README.md` as a source for this V2 feature.
- Do not mutate `data/extrusion_terminal.sqlite3` or any production/runtime database during implementation or tests.
- Do not infer historical shift assignments. Every pre-M002 roll remains unattributed unless a later explicit roll-creation rule applies.
- Do not add people count, notes, workers, crews, rosters, packaging, pallet tracking, shift cancellation, time editing, admin shift operation/review, printable shift reports, or shift fields on the operational-card printout.
- Keep the existing timestamp convention: use SQLite `CURRENT_TIMESTAMP` through `current_database_timestamp()` and display stored timestamps the same way existing screens do. Timezone conversion is not part of this feature.
- Important invariants must be enforced in the database or data layer, not only by the terminal modal.
- Use explicit optimistic versions for the singleton configuration and each shift occurrence. Stale writes must require reload.
- Ending or relabelling a shift must never update cards, machines, queue positions, card statuses, or `production_time_segments`.
- Do not stage or commit unless the user explicitly asks.

## Final Data Contract

```sql
CREATE TABLE terminal_configuration (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    shift_count INTEGER NOT NULL DEFAULT 4
        CHECK (typeof(shift_count) = 'integer' AND shift_count >= 1),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE shift_occurrences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_number INTEGER NOT NULL
        CHECK (typeof(shift_number) = 'integer' AND shift_number >= 1),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

-- Nullable for all historical/pre-feature rolls.
ALTER TABLE roll_entries
ADD COLUMN shift_occurrence_id INTEGER
    REFERENCES shift_occurrences(id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX idx_shift_occurrences_one_active
ON shift_occurrences((1))
WHERE ended_at IS NULL;

CREATE INDEX idx_shift_occurrences_completed
ON shift_occurrences(ended_at DESC, id DESC)
WHERE ended_at IS NOT NULL;

CREATE INDEX idx_roll_entries_shift_card
ON roll_entries(shift_occurrence_id, card_id)
WHERE shift_occurrence_id IS NOT NULL;
```

The configuration upper bound is dynamic and cannot be expressed as a cross-table SQLite `CHECK`. `start_shift()` and `update_active_shift_number()` must validate `1 <= shift_number <= current shift_count` inside their write transactions. The unique partial index is the final authority for the one-open-shift invariant.

## File Map

- Modify `app/migrations.py`: register and apply schema-only M002.
- Modify `app/db.py`: fresh-schema roll FK, configuration/lifecycle/read-model functions, shift-aware snapshot, roll attribution, live summaries.
- Modify `app/main.py`: admin settings routes/context, terminal shift routes/state, safe redirect helpers, terminal gate validation.
- Create `app/templates/admin_settings.html`: shift-count configuration page.
- Modify `app/templates/_admin_nav.html`: fourth `Настройки` navigation item.
- Modify `app/static/css/app.css`: four-column admin navigation and settings form styles.
- Create `app/templates/_terminal_shift_window.html`: gate, overview, confirmations, summaries, and history.
- Modify `app/templates/terminal.html`: global `Shift` action, modal include, blocking/inert behavior, snapshot response handling.
- Modify `tests/test_migrations.py`: M002 preservation, idempotence, rollback, and integrity coverage.
- Create `tests/test_shift_management.py`: configuration, lifecycle, summaries, and production-isolation coverage.
- Modify `tests/test_roll_entry.py`: normal running-roll attribution and late-roll rules.
- Modify `tests/test_admin_production_corrections.py`: admin-ledger late-roll attribution.
- Modify `tests/test_admin_routes.py`: settings routes, shared navigation, validation, and PRG.
- Create `tests/test_shift_routes.py`: terminal shift route and rendered-state coverage.
- Modify `tests/test_terminal_sync.py`: shift/configuration snapshot signatures.
- Modify `tests/test_terminal_v8_render.py`: global button, modal states, confirmation behavior, and blocking refresh rendering.
- Create `scripts/verify_shift_management_ui.mjs`: focused browser workflow and screenshots against a temporary database.
- Modify `v2-files/AGENTS.md`: M002 migration register/assessment evidence after tests pass.
- Modify `v2-files/PLAN.md` and `v2-files/TASK-01-SHIFT-MANAGEMENT.md`: mark implementation/verification status only after the feature is actually complete.
- Create `docs/implementation-notes/shift-management.md`: durable invariants, attribution rules, and recovery notes.

---

### Task 0: Preflight And Worktree Preservation

**Files:**
- Inspect only: current worktree and baseline suite

**Consumes:** User-owned uncommitted documentation changes and current passing baseline.

**Produces:** Recorded starting state; no source mutation.

- [ ] **Step 1: Confirm the worktree before editing**

```bash
git status --short
git diff -- v2-files/PLAN.md v2-files/TASK-01-SHIFT-MANAGEMENT.md
```

Expected: preserve the existing approved-spec/tracker changes and this plan. Do not overwrite or revert them.

- [ ] **Step 2: Reconfirm the baseline**

```bash
.venv/bin/python -m pytest -q
```

Expected at plan-writing time: `485 passed`. If the baseline has changed, record the exact result before feature edits and investigate failures before continuing.

---

### Task 1: M002 Schema And Existing-Data Preservation

**Files:**
- Modify: `tests/test_migrations.py`
- Modify: `app/migrations.py`
- Modify: `app/db.py:193-204`
- Modify after passing tests: `v2-files/AGENTS.md`

**Consumes:** Existing migration runner `apply_pending_migrations()`, caller-owned transaction in `init_db()`, legacy database fixture in `tests/test_migrations.py`.

**Produces:** Recorded M002, default configuration count `4`, durable occurrence storage, one-open DB invariant, nullable roll relationship, no historical backfill.

- [ ] **Step 1: Add failing migration-preservation tests**

Add these exact test functions:

- `test_m002_adds_shift_schema_without_attributing_legacy_rolls`
- `test_m002_preserves_existing_attribution_in_partially_upgraded_schema`
- `test_fresh_database_records_m001_and_m002_once_with_schema_parity`
- `test_m002_enforces_single_active_shift_and_roll_foreign_key`
- `test_m002_failure_rolls_back_schema_and_migration_record`

The first test must initialize the current legacy fixture, then assert:

```python
assert [(row["version"], row["name"]) for row in migration_rows] == [
    (1, "shift_manager_import_fields"),
    (2, "shift_management"),
]
assert configuration == {"id": 1, "shift_count": 4, "version": 1}
assert legacy_roll["shift_occurrence_id"] is None
assert integrity == "ok"
assert foreign_key_violations == []
```

Preservation snapshots must cover cards, import sources, rolls, recipe actuals/components, timing segments, machine queues, versions, and timestamps. Run initialization twice and assert the second run changes neither data nor migration rows.

- [ ] **Step 2: Prove the new tests fail for the missing schema**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_migrations.py::test_m002_adds_shift_schema_without_attributing_legacy_rolls \
  tests/test_migrations.py::test_fresh_database_records_m001_and_m002_once_with_schema_parity \
  -q
```

Expected: FAIL because M002, the two tables, and `roll_entries.shift_occurrence_id` do not exist.

- [ ] **Step 3: Add the nullable FK to the fresh `roll_entries` declaration**

In `SCHEMA_SQL`'s `roll_entries` table, add:

```sql
shift_occurrence_id INTEGER
    REFERENCES shift_occurrences(id) ON DELETE RESTRICT,
```

Do not add the shift indexes to `SCHEMA_SQL`. On a legacy database, `init_db()` executes `SCHEMA_SQL` before M002 adds the missing roll column; an early index on that column would fail. M002 owns table creation, legacy `ALTER TABLE`, seeding, and all new indexes.

- [ ] **Step 4: Implement `_apply_shift_management()` and register M002**

In `app/migrations.py`, add table/column existence checks using the existing `_table_columns()` helper. Execute each DDL statement through `connection.execute()`; do not call `executescript()` or `commit()` inside the migration. Define SQL constants from **Final Data Contract** and apply them in this order:

```python
def _apply_shift_management(connection: sqlite3.Connection) -> None:
    connection.execute(TERMINAL_CONFIGURATION_TABLE_SQL)
    connection.execute(SHIFT_OCCURRENCES_TABLE_SQL)
    connection.execute(
        "INSERT OR IGNORE INTO terminal_configuration (id, shift_count) VALUES (1, 4)"
    )

    roll_columns = _table_columns(connection, "roll_entries")
    if roll_columns is not None and "shift_occurrence_id" not in roll_columns:
        connection.execute(
            "ALTER TABLE roll_entries "
            "ADD COLUMN shift_occurrence_id INTEGER "
            "REFERENCES shift_occurrences(id) ON DELETE RESTRICT"
        )
        roll_columns.add("shift_occurrence_id")

    connection.execute(SHIFT_ONE_ACTIVE_INDEX_SQL)
    connection.execute(SHIFT_COMPLETED_INDEX_SQL)
    if roll_columns is not None:
        connection.execute(ROLL_SHIFT_CARD_INDEX_SQL)


MIGRATIONS = (
    Migration(1, "shift_manager_import_fields", _apply_shift_manager_import_fields),
    Migration(2, "shift_management", _apply_shift_management),
)
```

M002 must tolerate an absent `roll_entries` table and a partially upgraded schema. It must preserve any valid non-null attribution already present in a partially upgraded test database.

- [ ] **Step 5: Run focused migration checks**

```bash
.venv/bin/python -m pytest tests/test_migrations.py -q
```

Expected: all migration tests PASS, including second-run idempotence, injected rollback, `PRAGMA integrity_check`, and `PRAGMA foreign_key_check`.

- [ ] **Step 6: Record the completed migration evidence**

Only after the focused tests pass, append M002 `shift_management` to the migration register and assessment log in `v2-files/AGENTS.md`:

- Decision: schema-only.
- Transformation: no existing values changed; legacy rolls remain `NULL`.
- Production snapshot needed now: no for M002 attribution. The unresolved M001 legacy-data production profile and the later release-candidate rehearsal both remain deployment gates.
- Deployment constraint: migration chain and app must deploy together after SQLite-safe backup/rehearsal.

- [ ] **Step 7: Stop for slice review**

Review only the migration/schema diff and test evidence. Do not stage or commit without explicit user approval.

---

### Task 2: Configuration And Shift Lifecycle Domain

**Files:**
- Create: `tests/test_shift_management.py`
- Modify: `app/db.py`

**Consumes:** M002 tables, `RuleResult`, `connect()`, `current_database_timestamp()`.

**Produces:** Validated configuration reads/writes, persistent start/correct/end lifecycle, next-number suggestion, stale-write messages.

- [ ] **Step 1: Write failing lifecycle tests**

Add these exact test functions:

- `test_shift_count_defaults_to_four_and_rejects_non_positive_values`
- `test_shift_count_update_checks_loaded_version_and_preserves_history`
- `test_only_one_shift_occurrence_can_be_open_globally`
- `test_next_shift_suggestion_wraps_and_operator_may_override_it`
- `test_active_shift_number_correction_preserves_identity_and_start_time`
- `test_reduced_shift_count_keeps_removed_open_number_until_normal_end`
- `test_shift_lifecycle_blocks_stale_writes`
- `test_init_db_restores_open_shift_and_latest_selected_number`
- `test_empty_shift_can_end_without_touching_production_state`
- `test_reused_shift_number_creates_distinct_occurrence_identity`

For the isolation test, snapshot `cards`, `machines`, and `production_time_segments` before correction/end and assert byte-for-byte row equality afterward.

- [ ] **Step 2: Run the lifecycle tests and verify the intended failure**

```bash
.venv/bin/python -m pytest tests/test_shift_management.py -q
```

Expected: FAIL because the public lifecycle functions do not exist.

- [ ] **Step 3: Add stable messages and parsing helpers**

In `app/db.py`, define:

```python
STALE_SHIFT_MESSAGE = "Данните за смяната са променени. Презаредете терминала."
STALE_CONFIGURATION_MESSAGE = (
    "Настройките са променени след зареждането. Презаредете и опитайте отново."
)
NO_ACTIVE_SHIFT_MESSAGE = "Отворете смяна, преди да продължите."


def parse_positive_integer(value: str, field_name: str) -> tuple[int | None, str | None]:
    cleaned = value.strip()
    if not cleaned or any(character not in "0123456789" for character in cleaned):
        return None, f"{field_name} трябва да е положително цяло число."
    parsed = int(cleaned)
    if parsed < 1:
        return None, f"{field_name} трябва да е положително цяло число."
    return parsed, None
```

Do not invent a maximum shift count.

- [ ] **Step 4: Implement the public lifecycle interface**

Implement these exact interfaces:

- `fetch_active_shift_row(connection: sqlite3.Connection) -> sqlite3.Row | None` (internal transaction-aware helper)
- `fetch_terminal_configuration() -> dict[str, Any]`
- `update_shift_count(loaded_version: int, shift_count: str) -> RuleResult`
- `fetch_active_shift() -> dict[str, Any] | None`
- `suggest_next_shift_number() -> int`
- `start_shift(shift_number: str, loaded_configuration_version: int) -> RuleResult`
- `update_active_shift_number(shift_occurrence_id: int, loaded_version: int, shift_number: str) -> RuleResult`
- `end_shift(shift_occurrence_id: int, loaded_version: int) -> RuleResult`

Implementation rules:

- Re-read configuration inside start/correction transactions.
- `start_shift()` validates the submitted configuration version and selected number, records one database timestamp, and lets `idx_shift_occurrences_one_active` resolve concurrent starts. Catch only that expected integrity conflict and return a reload message.
- Correction uses a conditional update constrained by occurrence ID, loaded version, and `ended_at IS NULL`; it increments only occurrence version/`updated_at` and retains `started_at` and occurrence ID.
- End uses the same conditional-write pattern, sets one database timestamp, increments the version, and permits zero rolls.
- Configuration reduction updates only the singleton row. It never edits open or historical occurrences.
- Suggestion is `1` when there is no completed shift. Otherwise increment the latest completed shift's final number and wrap from `N` to `1`. If that historical number is now outside `1..N` after a count reduction, suggest `1`.

- [ ] **Step 5: Run the lifecycle suite**

```bash
.venv/bin/python -m pytest tests/test_shift_management.py -q
```

Expected: all lifecycle/configuration tests PASS.

- [ ] **Step 6: Stop for slice review**

Review transaction boundaries, conditional updates, and zero production-table changes. Do not stage or commit without explicit user approval.

---

### Task 3: Live Shift Summaries And Completed History

**Files:**
- Modify: `tests/test_shift_management.py`
- Modify: `app/db.py`

**Consumes:** `shift_occurrences`, linked current `roll_entries`, current `cards` customer/product/order fields.

**Produces:** Live per-occurrence summary and newest-first completed history; no frozen summary storage.

- [ ] **Step 1: Add failing read-model tests**

Add these exact test functions:

- `test_shift_summary_groups_distinct_orders_roll_count_and_gross_weight`
- `test_shift_summary_counts_all_linked_rolls_and_sums_available_gross_weight`
- `test_shift_summary_reflects_current_card_details_roll_corrections_and_deletions`
- `test_empty_shift_summary_has_zero_totals_and_no_order_rows`
- `test_completed_shift_history_is_newest_first_and_uses_live_totals`

The grouping fixture must include rolls from at least two cards in one occurrence, more than one roll on one card, a roll on another occurrence, and an unattributed legacy roll. Assert the latter two are excluded.

- [ ] **Step 2: Run the new tests and verify failure**

```bash
.venv/bin/python -m pytest tests/test_shift_management.py -q
```

Expected: FAIL because summary/history queries are not implemented.

- [ ] **Step 3: Implement the read-model interface**

Implement these exact interfaces:

- `fetch_completed_shifts() -> list[dict[str, Any]]`
- `fetch_shift_summary(shift_occurrence_id: int) -> dict[str, Any] | None`
- `fetch_shift_window_state() -> dict[str, Any]`

`fetch_shift_summary()` returns:

```python
{
    "id": int,
    "shift_number": int,
    "started_at": str,
    "ended_at": str | None,
    "distinct_item_count": int,
    "roll_count": int,
    "total_gross_weight": str,
    "orders": [
        {
            "card_id": int,
            "order_number": str,
            "customer": str | None,
            "product_type": str | None,
            "roll_count": int,
            "gross_weight": str,
        }
    ],
}
```

Query rules:

- Count every currently existing roll row linked to the occurrence, even when a later valid correction leaves its gross weight blank.
- Group by `card_id`; an item is one production order/card with at least one linked roll row.
- Sum current non-`NULL` gross values and format with the existing weight helpers; an all-blank group has gross total zero.
- Join current card fields so later valid card-detail corrections also render current values.
- Order summary rows deterministically by `order_number`, then `card_id`.
- Completed history is `ended_at DESC, id DESC` and carries the same distinct-item, roll, and gross aggregates.
- Store no snapshot table or copied totals.

- [ ] **Step 4: Run summary and lifecycle tests**

```bash
.venv/bin/python -m pytest tests/test_shift_management.py -q
```

Expected: PASS.

- [ ] **Step 5: Stop for slice review**

Confirm live values change after corrections/deletions and no history snapshot was introduced.

---

### Task 4: Roll Attribution And No-Shift Data Integrity

**Files:**
- Modify: `tests/test_roll_entry.py`
- Modify: `tests/test_admin_production_corrections.py`
- Modify: existing roll-producing helpers in affected tests
- Modify: `app/db.py:2393-2499`
- Modify: `app/db.py:2872-3123`
- Modify: `app/db.py:3126-3152`

**Consumes:** Active occurrence, card status, existing linked rolls on the same card, existing optimistic card version.

**Produces:** Atomic running-roll attribution, deterministic completed/archived inheritance, legacy `NULL` fallback, preserved links through corrections.

- [ ] **Step 1: Add focused failing attribution tests**

Add these exact test functions:

- `test_running_roll_requires_active_shift_and_links_occurrence`
- `test_active_shift_number_correction_does_not_rewrite_roll_link`
- `test_roll_correction_preserves_shift_occurrence`
- `test_completed_roll_inherits_latest_linked_occurrence_not_active_shift`
- `test_late_roll_without_known_order_shift_remains_unattributed`

Add these exact test functions:

- `test_admin_archived_roll_inherits_latest_linked_occurrence`
- `test_admin_legacy_archived_roll_remains_unattributed`
- `test_admin_roll_ledger_resolves_shift_before_deleting_source_roll`
- `test_admin_roll_correction_preserves_attribution_and_stale_save_is_atomic`

- [ ] **Step 2: Verify the intended failures**

```bash
.venv/bin/python -m pytest \
  tests/test_roll_entry.py \
  tests/test_admin_production_corrections.py \
  -q
```

Expected: new tests FAIL because inserts neither require nor store an occurrence.

- [ ] **Step 3: Add one attribution resolver used by both insertion paths**

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

    if card["status"] in PRODUCTION_COMPLETE_STATUSES:
        inherited = connection.execute(
            """
            SELECT shift_occurrences.id
            FROM roll_entries
            JOIN shift_occurrences
              ON shift_occurrences.id = roll_entries.shift_occurrence_id
            WHERE roll_entries.card_id = ?
            ORDER BY shift_occurrences.started_at DESC,
                     shift_occurrences.id DESC
            LIMIT 1
            """,
            (int(card["id"]),),
        ).fetchone()
        inherited_id = int(inherited["id"]) if inherited is not None else None
        return inherited_id, RuleResult(True)

    return None, RuleResult(
        False,
        ("Картата не позволява добавяне на ролка.",),
    )
```

Rules:

- `running`: fetch the one active occurrence and return its ID; if absent, return a blocking result before inserting.
- `completed`/`archived`: select the occurrence already linked to another roll on the same `card_id`, ordered by `shift_occurrences.started_at DESC, shift_occurrences.id DESC`, and return its ID.
- Completed/archived with no known linked occurrence: return `None`, ignoring any globally active shift.
- Resolve completed/archived inheritance before an admin ledger deletes rows, so delete-and-add in one save cannot erase the only known source attribution.
- Resolve once for an admin batch; every new row in that save receives the same ID.

- [ ] **Step 4: Modify both roll insertion paths**

Add `shift_occurrence_id` to the `INSERT INTO roll_entries` columns and values in:

- `add_roll_gross_weight()`;
- `_update_admin_roll_ledger()`.

Keep resolution, validation, insert, and card-version update in the same database transaction. Do not alter `shift_occurrence_id` in weight corrections, tare corrections, renumbering, or unrelated roll updates. Include the relationship in `fetch_roll_entries_and_totals()` for test/debug visibility only; no per-roll shift UI is required.

- [ ] **Step 5: Make existing test setup explicit**

Existing tests that create normal running-card rolls must explicitly open a shift before the first roll. Add a reusable non-autouse test helper/fixture and opt the relevant tests into it. Do not auto-seed an active shift in `init_db()` or an autouse fixture; that would conceal the required initial no-shift state.

Use:

```bash
rg -n "add_roll_gross_weight|new_gross_weights|/rolls" tests
```

to audit every roll-creation fixture and route test.

- [ ] **Step 6: Run attribution and regression tests**

```bash
.venv/bin/python -m pytest \
  tests/test_roll_entry.py \
  tests/test_admin_production_corrections.py \
  tests/test_finish_cancel_history.py \
  tests/test_production_timing.py \
  -q
```

Expected: PASS.

- [ ] **Step 7: Audit every application roll insert**

```bash
rg -n "INSERT INTO roll_entries" app
```

Expected: exactly the known normal insert and admin-ledger insert, and both provide `shift_occurrence_id`.

- [ ] **Step 8: Stop for slice review**

Review running versus completed/archived semantics, inherited-ID timing, stale atomicity, and correction preservation.

---

### Task 5: Admin Terminal-Configuration Page

**Files:**
- Modify: `tests/test_admin_routes.py`
- Modify: `app/main.py`
- Create: `app/templates/admin_settings.html`
- Modify: `app/templates/_admin_nav.html`
- Modify: `app/static/css/app.css`

**Consumes:** `fetch_terminal_configuration()`, `update_shift_count()`, shared admin template/navigation patterns.

**Produces:** Admin-only count configuration with default/current value, positive-integer validation, stale protection, and PRG success.

- [ ] **Step 1: Write failing settings-route tests**

Add these exact test functions:

- `test_admin_settings_routes_are_registered_without_admin_shift_operations`
- `test_admin_settings_page_uses_shared_nav_and_renders_current_count`
- `test_admin_settings_post_redirects_after_valid_update`
- `test_admin_settings_invalid_or_stale_post_renders_error_without_write`

Extend `assert_admin_global_nav()` to require links for Import, Planning, Cards, Settings, and Terminal on every admin page.

- [ ] **Step 2: Run focused admin tests**

```bash
.venv/bin/python -m pytest tests/test_admin_routes.py -q
```

Expected: FAIL because `/admin/settings` and its navigation item do not exist.

- [ ] **Step 3: Add settings context and routes**

In `app/main.py` add these exact interfaces:

- `admin_settings_context(**extra: Any) -> dict[str, Any]`
- `GET /admin/settings` handled by `admin_settings(request, notice)`
- `POST /admin/settings/shifts` handled by `save_admin_shift_settings(request, shift_count, loaded_version)`

Use PRG on success to `/admin/settings?notice=shift_count_saved`; render inline errors on failure. Do not add start/end/history/correction routes under `/admin`.

- [ ] **Step 4: Create the minimal page**

`admin_settings.html` contains one section titled `Настройки на терминала`, one input `Брой смени`, hidden configuration version, a save button, and success/error notice. Use `inputmode="numeric"`, but rely on backend validation.

Add `Настройки` as the fourth centered admin-nav item and change the desktop/tablet/mobile grids from three to four columns without altering unrelated admin pages.

- [ ] **Step 5: Run admin tests**

```bash
.venv/bin/python -m pytest tests/test_admin_routes.py -q
```

Expected: PASS.

- [ ] **Step 6: Stop for slice review**

Confirm workers cannot change the count from `/terminal` and the admin page cannot operate or edit occurrences.

---

### Task 6: Terminal Routes, State Model, Gate, And Synchronization

**Files:**
- Create: `tests/test_shift_routes.py`
- Modify: `tests/test_terminal_sync.py`
- Modify: `app/main.py`
- Modify: `app/db.py:652-725`

**Consumes:** Lifecycle/read-model functions, current terminal GET/POST helpers, current snapshot polling contract.

**Produces:** Safe terminal lifecycle endpoints, deterministic server-rendered modal state, backend terminal-action gate, shift-aware concurrency signal.

- [ ] **Step 1: Write failing route/state tests**

Add these exact test functions:

- `test_terminal_shift_routes_are_registered`
- `test_no_active_shift_context_is_blocking_gate`
- `test_start_uses_configured_choice_and_explicit_confirmation`
- `test_number_change_updates_same_occurrence_and_preserves_selected_card`
- `test_end_redirects_to_just_completed_blocking_summary`
- `test_summary_acknowledgment_returns_to_no_active_gate`
- `test_history_summary_and_back_use_the_same_window_state`
- `test_terminal_normal_posts_are_blocked_without_active_shift`
- `test_shift_routes_do_not_expose_time_edit_cancel_admin_review_or_report_actions`

Add these exact test functions:

- `test_terminal_snapshot_shift_signature_changes_on_start_change_end_and_count_update`
- `test_terminal_snapshot_exposes_only_current_shift_state_needed_for_reload`

- [ ] **Step 2: Verify failures**

```bash
.venv/bin/python -m pytest tests/test_shift_routes.py tests/test_terminal_sync.py -q
```

Expected: FAIL because routes, context state, and snapshot signature are absent.

- [ ] **Step 3: Add terminal lifecycle routes**

Add these POST handlers:

- `/terminal/shifts/start` → `start_terminal_shift`
- `/terminal/shifts/current/number` → `change_terminal_shift_number`
- `/terminal/shifts/current/end` → `end_terminal_shift`

Form fields:

- start: `shift_number`, `configuration_version`, optional numeric `selected_card_id`;
- correction: `shift_occurrence_id`, `loaded_version`, `shift_number`, optional `selected_card_id`;
- end: `shift_occurrence_id`, `loaded_version`, optional `selected_card_id`.

Build redirect destinations from the server-validated optional card ID, never a client-supplied return URL. On success:

- start → clean current terminal/card GET;
- correction → same GET with `shift_view=overview&notice=shift_changed`;
- end → same GET with `shift_view=summary&shift_id=<ended id>&handoff=1`.

- [ ] **Step 4: Extend terminal GET/context state**

Allow both `/terminal` and `/terminal/cards/{card_id}` to accept normalized `shift_view` and `shift_id` query parameters. Add this context contract:

```python
{
    "shift_configuration": {"shift_count": int, "version": int},
    "active_shift": dict[str, Any] | None,
    "shift_options": list[int],
    "suggested_shift_number": int,
    "completed_shifts": list[dict[str, Any]],
    "selected_shift_summary": dict[str, Any] | None,
    "shift_window_state": "closed" | "overview" | "gate" | "summary",
    "shift_blocking": bool,
}
```

State precedence:

1. A valid just-ended summary request with `handoff=1` → blocking `summary`.
2. No active shift → blocking `gate`.
3. Active shift plus overview/history request → dismissible `overview` or read-only `summary`.
4. Active shift with no request → `closed`.

When a reduced count excludes the open shift number, include that number as a selected disabled display option plus the valid correction choices `1..N`.

- [ ] **Step 5: Enforce the terminal gate on normal mutation routes**

Extend `validate_terminal_card_available_for_post()` so material, tare, roll correction/delete, timing start/pause/resume, and finish routes return `NO_ACTIVE_SHIFT_MESSAGE` when there is no active shift. Shift-start is the only terminal mutation available through the gate.

This central check protects normal HTTP flow. `add_roll_gross_weight()` remains the atomic data-layer authority that prevents an unattributed running-card roll during concurrent handoff.

Update existing route tests that intentionally perform normal terminal mutations so they explicitly start a shift first. Keep no-shift tests unseeded. Audit with:

```bash
rg -n "save_terminal_materials|save_tare_weight|add_roll_weight|save_terminal_roll_corrections|save_roll_weight|delete_roll_weight|delete_selected_roll_weight|start_timing|pause_timing|resume_timing|finish_terminal_card" tests
```

- [ ] **Step 6: Extend terminal snapshot state**

Add separate `shift_signature` data containing:

- configuration version/count;
- active occurrence ID, final/current number, version, and start timestamp, or `none`.

Include it in the overall signature but also return it separately. A different tab's start, correction, end, or settings update must change it. Do not expose history or summary rows in the polling payload.

- [ ] **Step 7: Run route and synchronization tests**

```bash
.venv/bin/python -m pytest \
  tests/test_shift_routes.py \
  tests/test_terminal_sync.py \
  tests/test_terminal_detail.py \
  tests/test_terminal_v8_render.py \
  -q
```

Expected: PASS.

- [ ] **Step 8: Stop for slice review**

Confirm routes preserve selected-card context, direct posts are gated, and no shift action mutates production execution.

---

### Task 7: Terminal Shift Window And History UI

**Files:**
- Modify: `tests/test_terminal_v8_render.py`
- Create: `app/templates/_terminal_shift_window.html`
- Modify: `app/templates/terminal.html`

**Consumes:** Task 6 context, current terminal global-action bar, existing confirmation/focus/polling JavaScript patterns.

**Produces:** One accessible modal surface for gate, start/end confirmations, active correction, end summary, completed history, and history details.

- [ ] **Step 1: Add failing render tests**

Add these exact test functions:

- `test_terminal_header_has_one_global_shift_button_without_inline_shift_details`
- `test_no_active_shift_gate_has_no_close_or_escape_dismissal`
- `test_start_confirmation_replaces_gate_content_and_names_selected_shift`
- `test_active_window_uses_current_number_as_the_only_correction_dropdown`
- `test_active_window_shows_start_time_separate_end_action_and_newest_history`
- `test_end_confirmation_replaces_window_content_without_nested_modal`
- `test_end_summary_renders_header_and_required_order_columns`
- `test_empty_shift_summary_renders_zero_items_and_empty_table`
- `test_history_view_and_back_replace_contents_in_one_modal`
- `test_blocking_shift_state_makes_terminal_content_inert`
- `test_shift_snapshot_change_renders_blocking_reload_state_without_discarding_dirty_forms`

- [ ] **Step 2: Run render tests and verify failure**

```bash
.venv/bin/python -m pytest tests/test_terminal_v8_render.py -q
```

Expected: new shift render tests FAIL.

- [ ] **Step 3: Add the global action and modal include**

Add exactly one global action labelled `Shift` beside Produced Orders and Queue. Do not show the shift number or start time in the main header.

Create `_terminal_shift_window.html` and include it once near the existing terminal overlays. Use one fixed centered dialog; do not add another drawer or stack a second modal.

- [ ] **Step 4: Render the four window modes**

- `gate`: `Няма активна смяна`, configured dropdown `1..N`, start action, no close control.
- `overview`: current number as the only correction dropdown, stored start time, visually separated `End shift`, scrollable newest-first history with Shift, start, end, distinct items, rolls, gross kg, and `View`.
- start/end confirmation: replace the current modal body and name the selected/current shift. Back returns to the prior modal body; Yes submits the relevant form.
- `summary`: header with shift number/start/end/distinct-item count; one row per order with production order ID, customer, product type, roll count, and gross kg. The just-ended summary has an acknowledgment link that leads to the gate. Historical summary has `Back` to overview.

Do not add search, filters, print, download, timestamp editing, cancellation, or worker fields.

- [ ] **Step 5: Add interaction and accessibility behavior**

- Auto-submit active-number correction on dropdown change.
- Start/end buttons first switch the same dialog to an internal confirmation pane; only Yes submits.
- Apply `inert` and `aria-hidden` to the underlying terminal app during gate, handoff summary, or stale-shift refresh state.
- Focus the first actionable dialog control.
- Escape/backdrop may close only ordinary active overview/history; it cannot dismiss gate or handoff summary.
- History `View` uses the server-normalized current terminal URL and replaces modal content; `Back` returns to overview.
- If snapshot `shift_signature` changes, preserve the existing dirty-form protection and display a blocking reload panel instead of auto-reloading or silently discarding input.

- [ ] **Step 6: Run terminal render/route tests**

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py \
  tests/test_shift_routes.py \
  tests/test_terminal_sync.py \
  -q
```

Expected: PASS.

- [ ] **Step 7: Stop for slice review**

Review terminal compact-height layouts, keyboard/focus behavior, one-modal rule, and the lack of any main-screen shift details.

---

### Task 8: End-To-End Verification And Durable Records

**Files:**
- Create: `scripts/verify_shift_management_ui.mjs`
- Create: `docs/implementation-notes/shift-management.md`
- Modify after verification: `v2-files/PLAN.md`
- Modify after verification: `v2-files/TASK-01-SHIFT-MANAGEMENT.md`
- Artifacts: `artifacts/ui-checks/shift-management/`

**Consumes:** Completed Tasks 1-7.

**Produces:** Focused browser evidence, full regression evidence, durable implementation notes, accurate V2 status.

- [ ] **Step 1: Run focused backend suites**

```bash
.venv/bin/python -m pytest tests/test_migrations.py -q
.venv/bin/python -m pytest tests/test_shift_management.py -q
.venv/bin/python -m pytest tests/test_roll_entry.py tests/test_admin_production_corrections.py -q
.venv/bin/python -m pytest tests/test_shift_routes.py tests/test_terminal_sync.py tests/test_terminal_v8_render.py -q
```

Expected: all PASS.

- [ ] **Step 2: Run syntax and full regression checks**

```bash
.venv/bin/python -m compileall app tests
.venv/bin/python -m pytest -q
git diff --check
```

Expected: no syntax errors, full suite PASS, no whitespace errors.

- [ ] **Step 3: Create the focused Playwright workflow**

`scripts/verify_shift_management_ui.mjs` must use the repository-local Playwright and a temporary `EXTRUSION_DB_PATH` under `artifacts/ui-checks/shift-management/`. It must not touch the real runtime database.

Browser sequence:

1. Write a two-order CSV fixture under the ignored artifact directory, upload it through `/admin/import`, and release the two orders from `/admin/planning` to different machines with sequence 1.
2. Open `/admin/settings`, change count to `3`, and verify the saved value.
3. Open `/terminal`; verify the dimmed, non-dismissible no-active gate offers exactly shifts `1..3`.
4. Confirm start of Shift 1; verify the main screen has only the global `Shift` label.
5. On both released cards, start production timing and enter a valid tare; add one roll to the first card so a running timer and attributed production both exist.
6. Open Shift, change the current number to 2, and verify occurrence ID/start time, card status, open timing segment, and existing roll link remain unchanged.
7. Add a second roll to the first order and at least one roll to the second order.
8. End the shift; verify confirmation, required summary columns, distinct items, roll totals, and gross totals.
9. Acknowledge the summary; verify the blocking start gate and suggested next number.
10. Start the next shift, reopen history, use `View` and `Back`, and verify the same summary appears in the same modal.
11. Correct/delete a linked roll through an allowed workflow and verify reopened history uses the latest roll count/gross values.
12. In a second browser page, change/end a shift and verify the first page shows the blocking reload state rather than accepting stale writes.

Capture:

```text
artifacts/ui-checks/shift-management/admin-shift-count.png
artifacts/ui-checks/shift-management/no-active-shift-gate.png
artifacts/ui-checks/shift-management/active-shift-window.png
artifacts/ui-checks/shift-management/ended-shift-summary.png
artifacts/ui-checks/shift-management/historical-shift-summary.png
```

- [ ] **Step 4: Run the UI verification**

Terminal 1:

```bash
mkdir -p artifacts/ui-checks/shift-management
EXTRUSION_DATA_DIR="$PWD/artifacts/ui-checks/shift-management" \
EXTRUSION_DB_PATH="$PWD/artifacts/ui-checks/shift-management/shift-ui.sqlite3" \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

Terminal 2:

```bash
./node_modules/.bin/playwright --version
BASE_URL=http://127.0.0.1:8011 \
ARTIFACT_DIR="$PWD/artifacts/ui-checks/shift-management" \
  node scripts/verify_shift_management_ui.mjs
```

Expected: script exits `0` and all five screenshots exist. Stop the local server afterward.

- [ ] **Step 5: Inspect the final diff and persistent-data safety**

```bash
git diff --stat
git diff -- app/migrations.py app/db.py app/main.py app/templates app/static/css/app.css tests scripts v2-files docs/implementation-notes
git status --short
```

Confirm:

- no unrelated refactor or packaging/pallet work;
- no production/runtime database or UI artifact is tracked;
- no roll history backfill;
- no frozen shift-summary storage;
- no start/end timestamp editing;
- every app roll insert follows the approved attribution rule.

- [ ] **Step 6: Write durable implementation notes and update status**

In `docs/implementation-notes/shift-management.md`, record:

- one global occurrence and one-open DB invariant;
- reusable business number versus unique occurrence ID;
- configuration count behavior and default;
- running versus completed/archived roll attribution;
- intentional `NULL` legacy attribution;
- live-summary behavior after correction/deletion;
- migration M002 and backup/rehearsal requirement;
- the still-unresolved M001 production legacy-data profile gate as well as the release-candidate rehearsal gate;
- terminal gate and concurrency/reload behavior.

Only now update `v2-files/PLAN.md` and the `Next technical work`/status text in `v2-files/TASK-01-SHIFT-MANAGEMENT.md` to say implementation and verification are complete. Preserve unrelated existing user changes in those files.

- [ ] **Step 7: Final review checkpoint**

Report focused/full test counts, exact UI verification command, screenshot paths, migration decision, the unresolved M001 production-profile gate, and the release-candidate rehearsal requirement. Do not stage or commit unless the user explicitly asks.

---

## Self-Review Checklist

- [x] Every approved behavior in `v2-files/TASK-01-SHIFT-MANAGEMENT.md` maps to a task and an automated or browser check.
- [x] Schema uses a permanent unique occurrence ID, not copied shift numbers or timestamp inference.
- [x] The database enforces at most one open occurrence.
- [x] Existing rolls remain unattributed; no guessed backfill exists.
- [x] Running rolls require and atomically capture the active occurrence.
- [x] Completed/archived late rolls inherit the latest known occurrence on the same card or remain `NULL`.
- [x] Corrections preserve attribution; deletion/live values change summaries.
- [x] Shift relabelling retains occurrence ID/start time and changes no production execution state.
- [x] Count reduction changes future choices only and does not invalidate an open historical number.
- [x] No-open gate is non-dismissible and normal terminal POSTs are blocked.
- [x] End summary and historical summary share one format and one modal surface.
- [x] History is newest first, compact, scrollable, and has no filters.
- [x] No worker, roster, notes, packaging, print, download, time correction, cancellation, or admin shift-operation scope was added.
- [x] Migration, focused tests, full tests, Playwright, integrity, foreign keys, diff check, and status records are all covered.
