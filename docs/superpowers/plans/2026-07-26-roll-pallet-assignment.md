# Roll Pallet Assignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Use superpowers:test-driven-development for every behavior change and superpowers:verification-before-completion before making any completion claim. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let terminal and admin users record an optional pallet number (`1`–`999`) on every roll, retain a card-level current pallet for rapid entry, warn—without blocking—when a finish contains mixed assigned/unassigned rolls, and print derived per-pallet roll, gross, and net totals on the operational card.

**Architecture:** Extend the existing tare-weight pattern with two nullable constrained integers: `cards.current_pallet_number` is the current workflow selection and `roll_entries.pallet_number` is the permanent roll snapshot. Keep parsing, optimistic-version enforcement, ownership checks, atomic correction, and derived aggregation in the direct-`sqlite3` data layer. Add only the minimal FastAPI forms and server-rendered UI required by the existing terminal/admin roll ledgers. Build pallet print rows from saved gross rolls at request time and split them with empirically verified A4 capacities; do not add package records, pallet lifecycle, shipping state, or label printing.

**Tech Stack:** FastAPI, Jinja2 templates, direct `sqlite3`, ordered SQLite migrations, pytest with temporary databases, vanilla JavaScript, HTML/CSS A4 printing, repository-local Playwright.

## Global Constraints

- Read `README.md`, the repository `AGENTS.md` instructions supplied for the task, `v2-files/AGENTS.md`, and the approved design at `docs/superpowers/specs/2026-07-26-roll-pallet-assignment-design.md` before implementation.
- Do not mutate `data/extrusion_terminal.sqlite3`, any production database, or any production backup. All automated and browser checks use temporary paths under `.test-runtime/` or `artifacts/ui-checks/`.
- Preserve the unrelated in-progress `v2-files/PLAN.md` and `v2-files/TASK-13-BACKUP-RESILIENCE.md` work. Re-read their diffs before any V2 recordkeeping edit and never overwrite concurrent Task 13 changes.
- Do not stage or commit unless the user explicitly asks. Every task ends at a review checkpoint, not a commit.
- Use `Палет` in Bulgarian UI text. Blank ledger values display `-`; the mixed printed aggregate is `Без палет`.
- Pallet assignment is optional. Valid nonblank input is an ASCII whole number from `1` through `999`, after trimming surrounding whitespace.
- Do not add a pallet capacity, full/closed state, auto-numbering, next-pallet action, pallet entity/table, shipping tracking, interim label printing, barcode, physical pallet/tare weight, or cross-card pallet assignment.
- `cards.current_pallet_number` changes only the default for future rolls. It never rewrites existing rolls.
- `roll_entries.pallet_number` changes only when that roll is created or explicitly corrected. Roll deletion/renumbering must retain the surviving rows' assignments.
- Pallet gross/net values are derived sums of roll gross/net values. The wooden pallet and wrapping are excluded. Do not persist aggregate rows or totals.
- Blank and mixed pallet assignments remain valid production data. The finish change is a client-side confirmation message only; do not add a backend blocker or override flag.
- Keep all existing status, active-shift, timing, tare/net, final-roll, 120-roll print, ownership, and optimistic-conflict invariants unchanged.
- The front print page, back-page order header, 120-roll grid, and blank `Дата / смяна` cells must remain unchanged.
- A normal or all-blank print remains exactly two A4 pages. An overflow pallet summary starts on page 3 and may continue to later pages.

## Final Data Contract

```sql
-- Nullable workflow state; new and migrated cards start blank.
ALTER TABLE cards
ADD COLUMN current_pallet_number INTEGER
    CHECK (
        current_pallet_number IS NULL
        OR (
            typeof(current_pallet_number) = 'integer'
            AND current_pallet_number BETWEEN 1 AND 999
        )
    );

-- Nullable immutable-at-entry snapshot; historical rolls stay blank.
ALTER TABLE roll_entries
ADD COLUMN pallet_number INTEGER
    CHECK (
        pallet_number IS NULL
        OR (
            typeof(pallet_number) = 'integer'
            AND pallet_number BETWEEN 1 AND 999
        )
    );
```

The same declarations belong in the fresh-schema definitions in `app/db.py`. Migration M003 is schema-only: it does not update existing values. If a partial schema already contains either column without the required integer declaration, range constraint, or valid stored values, M003 must fail atomically and must not record itself.

## Final Backend Interfaces

Add these focused interfaces rather than a pallet service or object model:

```python
PALLET_NUMBER_ERROR = "Палетът трябва да бъде цяло число от 1 до 999."

def parse_pallet_number(value: str, *, allow_blank: bool = True) -> tuple[int | None, str | None]: ...

def update_current_pallet_number(
    card_id: int,
    loaded_version: int,
    pallet_number: str,
    *,
    require_active_shift: bool = False,
) -> RuleResult: ...

def add_roll_gross_weight(
    card_id: int,
    loaded_version: int,
    gross_weight: str,
    tare_weight: str | None = None,
    pallet_number: str | None = None,
    *,
    require_active_shift: bool = False,
) -> RuleResult: ...

def update_admin_roll_ledger(
    card_id: int,
    loaded_version: int,
    tare_weight: str,
    roll_updates: dict[int, dict[str, str]],
    delete_roll_ids: set[int],
    new_gross_weights: list[str],
    *,
    current_pallet_number: str | None = None,
    connection: sqlite3.Connection | None = None,
) -> RuleResult: ...
```

`None` for the optional submitted current pallet means “the caller omitted this control; preserve the stored current value.” An explicit string—including `""`—means “validate, persist this current value, and copy it to any new roll created by the same transaction.” Existing row correction dictionaries gain `pallet_number`; an omitted key preserves the existing row value while an explicit blank clears it.

## Final Print Interfaces

Keep the print code as pure, inspectable functions:

```python
def build_pallet_summary(gross_rolls: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

def split_pallet_summary(
    rows: list[dict[str, Any]],
    *,
    back_column_capacity: int,
    overflow_page_capacity: int,
) -> dict[str, Any]: ...
```

`build_pallet_summary()` returns numeric pallets in numeric order and appends `Без палет` only when numbered and blank assignments are mixed. If every roll is blank, it returns an empty list. Each row contains `pallet_label`, `roll_count`, `gross_display`, and `net_display` with one-decimal display values.

`split_pallet_summary()` is independently unit-tested with injected capacities. Production capacities are named positive-integer constants set only after measuring the completed fixed-height CSS with Playwright/PDF. If all rows fit across the two page-2 columns, split middle then right. If not, page 2 gets no pallet rows and the entire list is chunked into page-3-and-later groups.

## File Map

- Modify `app/migrations.py`: add and validate schema-only M003 `roll_pallet_assignment`.
- Modify `app/db.py`: fresh constraints, initialization validation, reads, pallet parsing/current state, roll snapshot writes, atomic corrections, and admin ledger behavior.
- Modify `app/main.py`: parse pallet form fields, add the terminal current-pallet route, pass pallet values through roll routes, expose targeted feedback, and derive mixed-finish presentation state.
- Modify `app/templates/terminal.html`: pallet entry/current control, pallet ledger/correction column, finish question, and minimal autosave/synchronization JavaScript.
- Modify `app/templates/admin_card_detail.html`: current pallet control and per-roll pallet correction column in the existing global production form.
- Modify `app/static/css/app.css`: admin roll-toolbar/ledger sizing for the added column.
- Modify `app/printing.py`: pallet aggregation, numeric sorting, blank grouping, and print-page splitting.
- Modify `app/templates/print_card.html`: three-block back summary and identifiable overflow pages.
- Modify `app/static/css/print.css`: fixed-height pallet rows, three-block back layout, and overflow-page geometry.
- Modify `tests/test_migrations.py`: M003 fresh/legacy/partial/idempotence/rollback/constraint/preservation coverage.
- Modify `tests/test_roll_entry.py`: parser, current state, new-roll copy, stale/shift/status, correction, deletion, and atomicity coverage.
- Modify `tests/test_baseline.py`: overwrite-import preservation of both pallet fields.
- Modify `tests/test_terminal_v8_render.py`: terminal routes, markup, layout, autosave, correction, errors, finish modal, and JavaScript behavior.
- Modify `tests/test_admin_card_detail_redesign.py`: admin markup, form parsing, current state, new rows, and atomic ledger behavior.
- Modify `tests/test_admin_production_corrections.py`: completed/archived correction and pallet-preservation behavior.
- Modify `tests/test_print_output.py`: aggregation, page splitting, conditional rendering, overflow identification, and unchanged print-grid coverage.
- Create `tests/test_roll_pallet_ui_script_safety.py`: temporary-path enforcement and static browser-verifier safety checks.
- Create `scripts/create_roll_pallet_fixture.py`: safe temporary-DB browser fixture with terminal, normal-print, mixed-print, and overflow-print cards.
- Create `scripts/verify_roll_pallet_ui.mjs`: live terminal/admin/print geometry, interaction, screenshot, and PDF verification.
- Modify `README.md`: add the user-approved pallet attribution and operational-card summary to the authoritative pilot contract.
- Modify `docs/implementation-notes/print-output-reference.md`: replace the obsolete exactly-two-pages rule with the approved conditional overflow contract and field mapping.
- Create `docs/implementation-notes/roll-pallet-assignment.md`: durable data, migration, validation, correction, and recovery notes.
- Modify `v2-files/AGENTS.md`: record M003 only after implementation and verified evidence exist.
- Modify only Task 12/status text in `v2-files/PLAN.md`: replace the superseded package/label lifecycle with the approved bounded feature, while preserving concurrent Task 13 edits.

---

### Task 0: Preflight, Shared-Worktree Safety, And Baseline

**Files:**
- Inspect only: repository status, approved spec, current tests

**Consumes:** The approved design and other agents' current uncommitted V2 documentation.

**Produces:** A recorded clean baseline for source files and a list of user/concurrent changes to preserve.

- [ ] **Step 1: Re-read instructions and the approved design**

```bash
sed -n '1,360p' README.md
sed -n '1,360p' v2-files/AGENTS.md
sed -n '1,320p' docs/superpowers/specs/2026-07-26-roll-pallet-assignment-design.md
```

Expected: the design matches this plan. Stop and reconcile any later user-approved difference before code changes.

- [ ] **Step 2: Record and protect the shared worktree**

```bash
git status --short
git diff -- v2-files/PLAN.md v2-files/TASK-13-BACKUP-RESILIENCE.md
```

Expected at plan-writing time: `v2-files/PLAN.md` is modified and `v2-files/TASK-13-BACKUP-RESILIENCE.md` is untracked by another agent; the approved spec and this plan are also untracked. Do not revert, rename, stage, or absorb unrelated changes.

- [ ] **Step 3: Run the unmodified baseline**

```bash
.venv/bin/python -m pytest -q
```

Expected: all existing tests pass. Record the exact count because concurrent work may have changed it; investigate any pre-existing failure before implementing the feature.

**Review checkpoint:** No files changed and no staging/commit.

---

### Task 1: M003 Schema, Validation, And Historical Preservation

**Files:**
- Modify: `tests/test_migrations.py`
- Modify: `app/migrations.py`
- Modify: `app/db.py:98-212,728-756`

**Consumes:** `Migration`, `_table_columns()`, `apply_pending_migrations()`, `cards_table_sql()`, `SCHEMA_SQL`, and caller-owned `init_db()` transaction.

**Produces:** Nullable, constrained card/roll pallet columns on fresh and accepted legacy databases, recorded once as M003 with no backfill.

- [ ] **Step 1: Add failing M003 migration tests**

Add these exact tests in `tests/test_migrations.py`:

```python
def test_m003_adds_nullable_pallet_columns_without_backfilling_legacy_data(...): ...
def test_m003_accepts_a_valid_partially_upgraded_schema_and_preserves_values(...): ...
def test_m003_rejects_partial_pallet_columns_without_required_constraints(...): ...
def test_init_rejects_recorded_m003_with_malformed_pallet_schema(...): ...
def test_fresh_database_records_m001_m002_and_m003_once_with_schema_parity(...): ...
def test_m003_enforces_integer_pallet_range_on_cards_and_rolls(...): ...
def test_m003_failure_rolls_back_columns_and_migration_record(...): ...
```

The legacy-preservation snapshot must compare cards, import sources, rolls, recipe actuals/components, timing, machines/queues, versions, timestamps, shift attribution/configuration, and the prior migration records before/after. Assert:

```python
assert legacy_card["current_pallet_number"] is None
assert legacy_roll["pallet_number"] is None
assert migration_rows[-1] == {"version": 3, "name": "roll_pallet_assignment"}
assert integrity == "ok"
assert foreign_key_violations == []
```

The constraint test must reject direct SQL writes of non-coercible text such as `abc`, `0`, negative integers, and `1000` in both tables, while accepting `NULL`, `1`, and `999`. SQLite may coerce numeric text to integer affinity before evaluating `typeof()`, so assert the stored type rather than incorrectly expecting bound text `"1"` to fail. Run `init_db()` twice and prove the second run changes neither data nor migration history.

- [ ] **Step 2: Prove the focused tests fail for the intended missing schema**

```bash
.venv/bin/python -m pytest \
  tests/test_migrations.py::test_m003_adds_nullable_pallet_columns_without_backfilling_legacy_data \
  tests/test_migrations.py::test_fresh_database_records_m001_m002_and_m003_once_with_schema_parity \
  -q
```

Expected: FAIL because M003 and both columns do not exist.

- [ ] **Step 3: Add the exact fresh-schema declarations**

Add `current_pallet_number` after `cards.tare_weight` and `pallet_number` after `roll_entries.net_weight` using the **Final Data Contract** checks. Do not add defaults and do not derive either value from `packaging_method`, order number, roll number, or any historical field.

- [ ] **Step 4: Implement and register M003**

In `app/migrations.py`:

- add each missing column with one `ALTER TABLE ... ADD COLUMN`;
- validate existing partial columns as declared `INTEGER`, carrying the `NULL OR (typeof(...) = 'integer' AND ... BETWEEN 1 AND 999)` constraint;
- query and reject any stored non-null row whose type/range is invalid;
- expose `validate_roll_pallet_schema(connection)` and call it inside M003;
- append `Migration(3, "roll_pallet_assignment", _apply_roll_pallet_assignment)`;
- never call `commit()` or `executescript()` inside M003.

Import and call `validate_roll_pallet_schema()` immediately after `apply_pending_migrations()` in `app/db.init_db()`, next to `validate_shift_management_schema()`. A database claiming M003 with a malformed schema must fail startup rather than continue unprotected.

- [ ] **Step 5: Run the full migration test module**

```bash
.venv/bin/python -m pytest tests/test_migrations.py -q
```

Expected: PASS, including previous M001/M002 runner behavior.

**Review checkpoint:** Inspect only the schema/migration diff; confirm no production values, runtime database, or migration records outside temporary fixtures changed. Do not stage or commit.

---

### Task 2: Pallet Parsing, Current State, And New-Roll Snapshot

**Files:**
- Modify: `tests/test_roll_entry.py`
- Modify: `app/db.py:1217-1455,2791-3019,3695-3710`

**Consumes:** Current tare parsing/persistence, `fetch_roll_action_card()`, `add_roll_gross_weight()`, active-shift gate, and card-version validation.

**Produces:** Robust pallet parsing, persisted current selection, and atomic snapshot copying on every new roll.

- [ ] **Step 1: Add failing parser and current-state tests**

Cover these inputs exactly:

```python
valid = {"": None, "   ": None, "1": 1, " 1 ": 1, "999": 999, "001": 1}
invalid = ("0", "-1", "1000", "1.0", "1,0", "+1", "A", "1A", "١")
```

Assert every invalid input returns only:

```text
Палетът трябва да бъде цяло число от 1 до 999.
```

Add tests that current pallet save/clear:

- increments the card version and persists `int`/`NULL`;
- trims whitespace before storage;
- leaves the old value/version unchanged on invalid or stale input;
- respects the existing card-status and terminal active-shift gates;
- never creates a roll and never rewrites existing rolls.

- [ ] **Step 2: Add failing new-roll snapshot tests**

Verify:

- omitted `pallet_number` copies stored `cards.current_pallet_number`;
- explicit `" 2 "` updates current pallet to integer `2` and inserts roll pallet `2` in the same transaction;
- explicit blank clears current pallet and inserts a blank roll pallet;
- changing current from `1` to `2` leaves prior roll `1` on pallet `1`;
- invalid or stale submitted pallet creates no roll, changes no current value, and does not advance the card version;
- gross/tare/net/shift attribution remains identical to baseline behavior.

- [ ] **Step 3: Run the focused tests and observe the missing behavior**

```bash
.venv/bin/python -m pytest tests/test_roll_entry.py -k "pallet or current_pallet" -q
```

Expected: FAIL because the parser, current update, and roll snapshot do not exist.

- [ ] **Step 4: Implement the parser and current update**

Use ASCII digits only; do not rely on `int()` accepting signs or Unicode numerals:

```python
def parse_pallet_number(value: str, *, allow_blank: bool = True) -> tuple[int | None, str | None]:
    cleaned = value.strip()
    if not cleaned:
        return (None, None) if allow_blank else (None, PALLET_NUMBER_ERROR)
    if not cleaned.isascii() or not all("0" <= char <= "9" for char in cleaned):
        return None, PALLET_NUMBER_ERROR
    parsed = int(cleaned)
    if not 1 <= parsed <= 999:
        return None, PALLET_NUMBER_ERROR
    return parsed, None
```

Implement `update_current_pallet_number()` by mirroring `update_tare_weight()` exactly for transaction ownership, active-shift validation, accepted statuses, stale versions, timestamps, and one version increment. Use messages `Палетът е изчистен.` and `Палетът е записан.`.

- [ ] **Step 5: Extend reads and new-roll writes**

- Select `current_pallet_number` in admin detail, terminal detail, and `fetch_roll_action_card()`.
- Select `pallet_number` in `fetch_roll_entries_and_totals()`.
- Extend `add_roll_gross_weight()` with the optional submitted pallet contract from **Final Backend Interfaces**.
- Parse all submitted gross/tare/pallet values before opening or mutating the transaction.
- Resolve the snapshot as submitted pallet when present, otherwise stored current pallet.
- Insert `roll_entries.pallet_number` with gross/tare/net/shift in the same `INSERT`.
- If submitted pallet is present, update `cards.current_pallet_number` and version in the same card update that currently persists a submitted tare; do not increment twice when both tare and pallet are submitted.

- [ ] **Step 6: Run roll-entry regression tests**

```bash
.venv/bin/python -m pytest tests/test_roll_entry.py -q
```

Expected: PASS, including all existing tare, totals, shift-attribution, stale-write, deletion, and completed-card invariants.

**Review checkpoint:** Query only the temporary test database to confirm `typeof()` is `integer` for assigned pallets and `null` for blanks. Do not stage or commit.

---

### Task 3: Atomic Terminal And Admin Roll Corrections

**Files:**
- Modify: `tests/test_roll_entry.py`
- Modify: `tests/test_admin_card_detail_redesign.py`
- Modify: `tests/test_admin_production_corrections.py`
- Modify: `app/db.py:3021-3270,3395-3688`

**Consumes:** Terminal bulk correction, admin atomic ledger, per-roll tare recalculation, roll deletion/renumbering, completed/archived edit rules, and stale checks.

**Produces:** Per-roll pallet correction and admin current-pallet/new-roll behavior without partial saves or unintended reassignment.

- [ ] **Step 1: Add failing terminal correction tests**

Assert that one bulk correction can set, change, and clear `pallet_number` while updating gross/tare/net as usual. Cover:

- all rows validate before any write;
- one invalid pallet rolls back every pallet/gross/tare change;
- a foreign roll ID is rejected;
- a stale version changes nothing;
- correcting a roll does not change `cards.current_pallet_number`;
- a no-op correction does not increment the card version;
- completed-card final-gross-roll protection is unchanged.

- [ ] **Step 2: Add failing admin ledger tests**

Cover in one atomic save:

- current pallet save/clear;
- existing row pallet set/change/clear;
- admin-added rows copy the submitted current pallet;
- deleting a middle roll and renumbering survivors preserves their pallet values;
- paused-card current-pallet-only save follows the existing tare-only allowance;
- paused-card roll mutation remains blocked;
- completed and archived corrections remain allowed;
- invalid pallet, malformed/foreign roll ID, or stale version rolls back order/material/timing sections too when invoked through the global save transaction.

- [ ] **Step 3: Run focused correction tests and observe failure**

```bash
.venv/bin/python -m pytest \
  tests/test_roll_entry.py \
  tests/test_admin_card_detail_redesign.py \
  tests/test_admin_production_corrections.py \
  -k "pallet" -q
```

Expected: FAIL because correction dictionaries and admin ledger do not process pallet values.

- [ ] **Step 4: Extend terminal bulk correction atomically**

Select existing `pallet_number`, use omitted-key-preserves/blank-clears semantics, parse every row before updates, and include pallet equality in `changed_updates`. Update each changed row with:

```sql
SET pallet_number = ?,
    gross_weight = ?,
    tare_weight = ?,
    net_weight = ?,
    updated_at = CURRENT_TIMESTAMP
```

Keep the ownership set comparison and one card-version increment only when at least one row changed.

- [ ] **Step 5: Extend the admin ledger without breaking callers**

Add keyword-only `current_pallet_number: str | None = None` so existing callers that omit the new field preserve stored current state. In `_update_admin_roll_ledger()`:

- select card current pallet and row pallet values;
- parse explicit current pallet and all row pallets before any write;
- treat per-roll pallet differences as roll mutation for status validation, while a card-level current-pallet-only change remains allowed anywhere the existing tare-only card update is allowed;
- update card tare/current pallet/version once;
- update existing rows with pallet/gross/tare/net;
- copy the resolved current pallet to every new roll;
- retain pallet values during delete/renumber passes.

- [ ] **Step 6: Run all roll/admin correction tests**

```bash
.venv/bin/python -m pytest \
  tests/test_roll_entry.py \
  tests/test_admin_card_detail_redesign.py \
  tests/test_admin_production_corrections.py \
  -q
```

Expected: PASS.

**Review checkpoint:** Inspect transaction boundaries and every early return; no validated subset may be written before a later invalid pallet is discovered. Do not stage or commit.

---

### Task 4: Import/Re-import And Production-Data Preservation

**Files:**
- Modify: `tests/test_baseline.py`
- Inspect, normally no change: `app/importer.py`

**Consumes:** Existing explicit imported-field update and overwrite-import preservation behavior.

**Produces:** Regression proof that both pallet fields are production data and never overwritten by CSV import.

- [ ] **Step 1: Extend the overwrite-import preservation fixture**

In `test_overwrite_import_updates_imported_fields_and_preserves_production_data`, set:

```python
cards.current_pallet_number = 7
roll_entries.pallet_number = 6
```

Run overwrite import, then assert both still have exactly those integer values alongside existing status, machine, sequence, tare, roll, timing, shift, materials, versions, and timestamps.

- [ ] **Step 2: Run the test before importer changes**

```bash
.venv/bin/python -m pytest \
  tests/test_baseline.py::test_overwrite_import_updates_imported_fields_and_preserves_production_data \
  -q
```

Expected after Tasks 1–3: PASS because importer updates an explicit imported-field list. If it fails, make the smallest importer query correction; do not add pallet columns to import headers or source tables.

- [ ] **Step 3: Run baseline import coverage**

```bash
.venv/bin/python -m pytest tests/test_baseline.py -q
```

Expected: PASS.

**Review checkpoint:** Confirm no CSV field, workbook mapping, `card_import_sources` column, or import contract was added. Do not stage or commit.

---

### Task 5: FastAPI Form Plumbing And Targeted Feedback

**Files:**
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_admin_card_detail_redesign.py`
- Modify: `app/main.py:675-718,1022-1085,1377-1465,1826-1935,2510-2600`

**Consumes:** Existing form parsers, POST/redirect/get responses, terminal active-card validation, notice codes, and feedback targets.

**Produces:** Pallet values reach the data layer through current terminal/admin routes with correct inline errors and no duplicate mutation paths.

- [ ] **Step 1: Add failing route/parser tests**

Cover:

- `roll_ledger_from_form()` returns current pallet plus per-row pallet values;
- `terminal_roll_corrections_from_form()` parses `pallet_number__<roll_id>`;
- malformed pallet field suffixes return the existing invalid-roll-form message;
- terminal `/pallet` saves, clears, trims, blocks stale/cancelled/archived/no-active-shift posts, and redirects with `pallet_saved` on success;
- terminal add-roll passes explicit current pallet so click-before-blur is atomic;
- terminal correction route passes per-row pallet values;
- admin global save and `/roll-ledger` pass current/per-row pallet values;
- success uses PRG and failure renders near the correct pallet/roll control.

- [ ] **Step 2: Run focused tests and observe failure**

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py \
  tests/test_admin_card_detail_redesign.py \
  -k "pallet" -q
```

Expected: FAIL because routes/form parsers do not know pallet fields.

- [ ] **Step 3: Extend the form parsers**

Change the admin tuple to include current pallet explicitly:

```python
tuple[str, str, dict[int, dict[str, str]], set[int], list[str]]
# tare_weight, current_pallet_number, roll_updates, delete_ids, new_gross
```

Recognize `pallet_number__<roll_id>` in both admin and terminal parsers. Keep `int()` conversion inside the existing `try/except ValueError` route boundary so malformed IDs never reach SQL.

- [ ] **Step 4: Add the terminal current-pallet route**

Add:

```python
@app.post("/terminal/cards/{card_id}/pallet")
async def save_current_pallet_number(...):
    ...
```

Follow `/tare` exactly: parse loaded version, validate terminal availability, require active shift, call `update_current_pallet_number()`, then use `terminal_post_response(... notice_code="pallet_saved", roll_result_target="pallet")`.

Add `pallet` to `terminal_roll_feedback_target()` and to the feedback error dictionary. Extend `terminal_notice_result()` with the corresponding success message. Do not introduce an admin-only pallet route when the existing global roll ledger already saves that control.

- [ ] **Step 5: Pass pallet values through add/correction/admin routes**

- Add optional `pallet_number: str | None = Form(None)` to terminal add-roll.
- When terminal add-roll fails specifically with `PALLET_NUMBER_ERROR`, target the error to `pallet`; gross/tare failures remain targeted to `new_roll`. This keeps click-before-blur validation beside the field that caused it.
- Pass the parser's current pallet to both admin ledger invocation sites.
- Keep legacy individual gross/tare routes pallet-preserving by leaving the pallet column out of their SQL update unless a pallet field is actually accepted by that route.
- Do not change `finish_card()` or finish route parameters.

- [ ] **Step 6: Run route regressions**

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py \
  tests/test_admin_card_detail_redesign.py \
  tests/test_admin_production_corrections.py \
  -q
```

Expected: PASS.

**Review checkpoint:** Confirm every mutating route still validates loaded version and terminal state before the write, and successful posts remain refresh-safe. Do not stage or commit.

---

### Task 6: Terminal And Admin Roll-Entry UI

**Files:**
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_admin_card_detail_redesign.py`
- Modify: `app/templates/terminal.html:685-1225,1690-1740,1981-2010,3359-3465,3926-3970,4180-4225`
- Modify: `app/templates/admin_card_detail.html:290-335`
- Modify: `app/static/css/app.css:1180-1270,1800-1825`

**Consumes:** Current tare dirty-autosave group, hidden new-roll tare copy, terminal correction mode, single admin global form, and responsive ledger styling.

**Produces:** Clear pallet entry and correction on both surfaces, without adding buttons or a separate pallet workflow.

- [ ] **Step 1: Add failing terminal render/layout tests**

Assert the exact entry order:

```text
Нова ролка, кг | Шпула, кг | Палет | Добави
```

Also assert:

- pallet input is `type="number" min="1" max="999" step="1"` and blank by default;
- it has `data-dirty-autosave="true"` in the `roll-entry` group;
- add-roll contains a hidden `data-new-roll-pallet-copy` value;
- JavaScript syncs current pallet to the hidden copy on input/change just like tare;
- the terminal ledger is `№ | Палет | Бруто кг | Шпула кг | Нето кг`;
- blank pallet display is `-`;
- correction mode exposes `pallet_number__<id>` with the same min/max/step;
- pallet autosave errors render under the current pallet control;
- correction-mode action blocking includes the pallet form;
- gross/core controls are narrower, the roll panel gains bounded width, and recipe values remain present/scroll-safe at the supported compact viewport.

- [ ] **Step 2: Add failing admin render tests**

Assert the existing roll toolbar contains current `Шпула, кг`, current `Палет`, then new gross-roll input, and that the ledger contains an editable pallet column per existing roll. Blank values use empty inputs, not the literal `Без палет`.

- [ ] **Step 3: Run render tests and observe failure**

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py \
  tests/test_admin_card_detail_redesign.py \
  -k "pallet or roll_entry_controls" -q
```

Expected: FAIL because markup and styles are absent.

- [ ] **Step 4: Implement terminal markup and autosave**

In the roll-entry block:

- keep new gross as the first form/control;
- keep current tare second;
- add a separate current-pallet autosave form third, posting to `/terminal/cards/<id>/pallet`;
- add the hidden pallet copy to the add-roll form;
- keep the existing Add button last;
- keep current pallet unchanged after successful add.

Use `.value` synchronization only; backend trimming/range validation remains authoritative. Do not auto-increment or infer the next pallet after add.

- [ ] **Step 5: Rebalance terminal geometry minimally**

- Shorten gross and core field widths enough to fit the pallet control.
- Increase the right roll-panel track modestly from its current fixed width.
- Recover that space by narrowing the oversized planned-material recipe track and shifting the column boundary left.
- Preserve every recipe label/value/input and horizontal scrolling fallback at compact widths.
- Change roll head/rows from four to five columns, making the pallet column narrower than gross/core/net.

Do not redesign the recipe or overall page.

- [ ] **Step 6: Implement admin toolbar/ledger markup and CSS**

Add the current pallet input to the existing production form and `pallet_number__<roll.id>` to each row. Expand the admin roll ledger to six grid columns (`№`, pallet, gross, tare, net, delete) and the toolbar to three responsive controls. Retain the existing single Save action and delete forms.

- [ ] **Step 7: Run all terminal/admin render tests**

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py \
  tests/test_admin_card_detail_redesign.py \
  -q
```

Expected: PASS.

**Review checkpoint:** Inspect at 1536×1024 and 1366×768 during Task 10 before accepting the width values. Do not stage or commit.

---

### Task 7: Mixed-Pallet Finish Confirmation

**Files:**
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `app/main.py:2617-2635`
- Modify: `app/templates/terminal.html:3213-3220,3550-3565,3843-3905`

**Consumes:** Saved gross roll data and the existing app-native finish confirmation modal.

**Produces:** Correct Bulgarian warning for mixed assignments, with simple `Да`/`Не`, and no backend finish rule.

- [ ] **Step 1: Add failing display and JavaScript tests**

Create all-blank, all-assigned, mixed-singular, and mixed-plural cards. Assert:

- all blank and all assigned use `Сигурни ли сте, че искате да приключите тази поръчка?`;
- mixed with one blank uses `В поръчката има 1 ролка без палет. Искате ли да приключите поръчката?`;
- mixed with three blanks uses `В поръчката има 3 ролки без палет. Искате ли да приключите поръчката?`;
- only saved rolls with non-null gross weights count;
- buttons render exactly `Да` and `Не`;
- opening the modal copies the selected form's message into `#finish-confirm-body` with `textContent`;
- `Не` closes the modal, makes no request, and does not open correction mode;
- `Да` submits the unchanged finish form once.

- [ ] **Step 2: Prove the tests fail**

```bash
.venv/bin/python -m pytest tests/test_terminal_v8_render.py -k "finish and pallet" -q
```

Expected: FAIL because all finish forms currently use one static question and verbose button labels.

- [ ] **Step 3: Derive presentation-only state**

In `enrich_terminal_card_display()`, derive counts from `card["roll_entries"]` after fetch:

```python
gross_rolls = [roll for roll in card["roll_entries"] if roll["gross_weight"] is not None]
missing = sum(roll["pallet_number"] is None for roll in gross_rolls)
assigned = len(gross_rolls) - missing
is_mixed = missing > 0 and assigned > 0
```

Set a single escaped data attribute on the active finish form containing either the standard question or exact singular/plural mixed question. Do not add a field to the finish POST and do not call this a validation result.

- [ ] **Step 4: Simplify and update modal JavaScript**

Change button text to `Не` and `Да`. On open, set the modal body's `textContent` from the pending form. On close, restore only modal state/focus; leave the normal card screen untouched.

- [ ] **Step 5: Run finish and lifecycle regressions**

```bash
.venv/bin/python -m pytest \
  tests/test_terminal_v8_render.py \
  tests/test_finish_cancel_history.py \
  tests/test_production_timing.py \
  -q
```

Expected: PASS. Backend finish tests remain unchanged because pallet completeness is not an invariant.

**Review checkpoint:** Search for new pallet checks in `finish_card()`/`validate_card_ready_to_finish()` and remove any if present. Do not stage or commit.

---

### Task 8: Derived Pallet Print Data And Deterministic Splitting

**Files:**
- Modify: `tests/test_print_output.py`
- Modify: `app/printing.py:1-245`

**Consumes:** `gross_roll_entries()`, decimal parsing, half-up one-decimal formatting, and current print readiness.

**Produces:** Correct, current per-pallet summary data and an independently tested whole-row page split.

- [ ] **Step 1: Add failing aggregation tests**

Add exact tests for:

- all blank rolls produce `[]`;
- pallets `10`, `2`, and `7` sort as `2, 7, 10`, without rows for gaps;
- per-pallet roll counts and Decimal gross/net sums are correct;
- `51.25` displays `51.3` through the existing half-up formatter;
- mixed blanks produce one final `Без палет` row;
- blank-only rolls with no gross are ignored;
- changing a completed roll pallet/gross/tare is reflected by the next `build_print_readiness()` call, proving no aggregate is persisted.

- [ ] **Step 2: Add failing split tests with injected small capacities**

Use `back_column_capacity=2` and `overflow_page_capacity=3` to assert:

```python
0 rows -> no back columns, no overflow pages
1..2 rows -> middle only
3..4 rows -> middle then right
5 rows -> page 2 empty, overflow chunks [3, 2]
7 rows -> page 2 empty, overflow chunks [3, 3, 1]
```

Assert input order and every row are preserved exactly once; never split a row.

- [ ] **Step 3: Run tests and observe failure**

```bash
.venv/bin/python -m pytest tests/test_print_output.py -k "pallet_summary or split_pallet" -q
```

Expected: FAIL because the print builder has no pallet summary.

- [ ] **Step 4: Implement aggregation**

Use `dict[int | None, ...]` and `Decimal("0")`. Include the `None` bucket only if at least one numbered bucket exists. Sort numbered keys with normal integer ordering, append the blank bucket last, and format both weights through `format_weight()`.

- [ ] **Step 5: Implement the pure split function**

Reject non-positive capacities with `ValueError`. Return two back-column lists only when the full summary fits `2 * back_column_capacity`; otherwise return both back columns empty and chunk the full list by `overflow_page_capacity`.

Wire both outputs into `assemble_print_data()` while leaving `roll_slots`, front data, readiness, and 120-roll limit unchanged.

- [ ] **Step 6: Run all print-data tests**

```bash
.venv/bin/python -m pytest tests/test_print_output.py -q
```

Expected before markup work: aggregation/splitting tests pass; existing rendered-summary assertions may remain intentionally red until Task 9 if they assert the old two-table structure. Keep the focused pure tests green.

**Review checkpoint:** Confirm there is no pallet aggregate table, insert, update, cache, or stored total. Do not stage or commit.

---

### Task 9: Operational-Card Back Layout And Overflow Pages

**Files:**
- Modify: `tests/test_print_output.py`
- Modify: `app/templates/print_card.html:276-370`
- Modify: `app/static/css/print.css:40-65,400-565`
- Modify: `app/printing.py` (production capacity constants only after measurement)

**Consumes:** Fixed A4 print geometry, unchanged 120-roll grid, page split view model, and current order header fields.

**Produces:** Three-block page-2 summary, conditional omission, and complete identifiable page-3+ overflow.

- [ ] **Step 1: Add failing rendered-output tests**

Cover:

- all-blank cards render exactly two `.print-page` elements and no pallet-summary table/text;
- fitting summaries render page 2 with one left combined production table and middle/right pallet blocks;
- pallet headings are exactly `Палет`, `Ролки`, `Бруто, кг`, `Нето, кг`;
- page-2 pallet rows preserve numeric order and display both one-decimal weights;
- there is no redundant pallet grand-total row;
- overflow renders no page-2 pallet rows, starts the complete list on page 3, and repeats order number/customer/product on every overflow page;
- every source summary row appears exactly once across overflow pages;
- the front page, back header, roll slots `1..120`, blank `Дата / смяна`, and gross-only roll grid remain unchanged.

- [ ] **Step 2: Replace the two-table lower summary with three blocks**

The left block contains six rows in this order:

1. `Старт производство`
2. `Стоп производство`
3. `Време за изработка`
4. `Шпула /кг/`
5. `Произведено кол. бруто /кг/`
6. `Произведено кол. нето /кг/`

Render middle/right pallet tables only when `print_data` supplies fitting rows. Do not render empty pallet frames for an all-blank card or an overflow case.

- [ ] **Step 3: Add explicit overflow page markup**

For each overflow chunk, render one `.print-page.print-page-pallet-overflow` with the same three-field order header values and one full-width pallet table. Use `thead` and whole fixed-height `tr` rows; no row may cross a page boundary.

Make page breaking positional:

- front always breaks;
- back breaks when overflow pages follow;
- the final page does not emit an extra blank page.

- [ ] **Step 4: Define fixed physical geometry, then measure rather than guess**

Use `mm` dimensions and fixed row heights in `print.css`. The page-2 summary must stay within the existing `210mm × 297mm` page and the back page's established `14mm 18mm 10mm` padding. Start with readable compact typography consistent with the current `7.6pt` summary, then use Task 10's browser measurement to determine:

- greatest whole pallet rows fitting in one page-2 pallet block;
- greatest whole pallet rows fitting on one overflow page.

Only after the PDF/bounding-box check passes, store those measured integers as named constants in `app/printing.py` and use them in `assemble_print_data()`. They are renderer capacities, not user-visible limits. Add assertions/tests that both are positive and that the boundary case fits while boundary+1 takes the required path.

- [ ] **Step 5: Run print render tests**

```bash
.venv/bin/python -m pytest tests/test_print_output.py -q
```

Expected: PASS after measured constants are finalized in Task 10; do not accept a guessed value merely to make string tests pass.

**Review checkpoint:** Compare the unchanged front/roll-grid selectors and existing tests before accepting the layout diff. Do not stage or commit.

---

### Task 10: Live Browser/PDF Calibration And UI Acceptance

**Files:**
- Create: `scripts/create_roll_pallet_fixture.py`
- Create: `scripts/verify_roll_pallet_ui.mjs`
- Modify if measurement requires: `app/static/css/print.css`, `app/printing.py`, terminal/admin CSS
- Create: `tests/test_roll_pallet_ui_script_safety.py`
- Output only: `artifacts/ui-checks/roll-pallet-assignment/`

**Consumes:** Completed backend/UI/print work and repo-local Playwright/browser installation.

**Produces:** Reproducible temporary data, terminal/admin screenshots, normal and overflow PDFs, and geometry evidence.

- [ ] **Step 1: Create a safe fixture generator**

Require its DB path to resolve under `.test-runtime/`. Generate:

- one running card with an active shift, current pallet, assigned and blank rolls for terminal interaction;
- one completed mixed card whose pallet summary fits on page 2;
- one completed all-blank sample card;
- one completed card with enough distinct numbered pallets to force page 3 and at least one further overflow boundary if the measured capacity requires it.

Return card IDs as JSON. Never open or delete the real runtime database.

Add focused tests proving the fixture rejects paths outside `.test-runtime/`, the verifier requires explicit fixture/artifact inputs, and neither script contains the real `data/extrusion_terminal.sqlite3` path or downloads/installs browser tooling.

- [ ] **Step 2: Create the Playwright verifier**

At `1536×1024` and `1366×768`, assert:

- terminal entry controls appear in approved order and do not overlap;
- the recipe remains readable/reachable;
- pallet autosave survives reload;
- adding a roll copies the visible current pallet and leaves the input unchanged;
- correction can change/clear pallet and blank display becomes `-`;
- mixed finish modal uses exact Bulgarian text and `Не` makes no request/does not open correction;
- admin current and row pallet inputs render without ledger clipping.

For print pages, assert with `getBoundingClientRect()`:

- every fitting page-2 pallet row is wholly inside its block and above the safe bottom boundary;
- the middle block fills before the right block;
- overflow leaves page 2 pallet blocks empty;
- every overflow row is wholly within its A4 page;
- row text does not horizontally overflow its cell;
- source and rendered pallet-row counts match.

Save at minimum:

```text
terminal-pallet-entry-1536x1024.png
terminal-pallet-correction-1366x768.png
admin-pallet-ledger.png
print-pallet-back-page.png
print-pallet-overflow-page-3.png
normal-pallet-print.pdf
overflow-pallet-print.pdf
verification-summary.json
```

- [ ] **Step 3: Verify local browser tooling**

```bash
./node_modules/.bin/playwright --version
```

Expected: repository-local Playwright responds; do not download tools implicitly.

- [ ] **Step 4: Build the temporary fixture and start the app**

```bash
.venv/bin/python scripts/create_roll_pallet_fixture.py \
  --db-path .test-runtime/roll-pallet-assignment/extrusion_terminal.sqlite3 \
  --output .test-runtime/roll-pallet-assignment/fixture.json
```

```bash
EXTRUSION_DB_PATH=.test-runtime/roll-pallet-assignment/extrusion_terminal.sqlite3 \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8012
```

Run the server in a reusable PTY/session and stop it cleanly after verification.

- [ ] **Step 5: Run the live verifier**

```bash
BASE_URL=http://127.0.0.1:8012 \
FIXTURE_JSON=.test-runtime/roll-pallet-assignment/fixture.json \
ARTIFACT_DIR=artifacts/ui-checks/roll-pallet-assignment \
  node scripts/verify_roll_pallet_ui.mjs
```

Expected: exit `0`; screenshots/PDF/JSON appear only under ignored `artifacts/ui-checks/`.

- [ ] **Step 6: Finalize measured capacities and repeat**

Set the production constants to the greatest verified whole-row counts reported by the geometry run. Repeat the focused print tests and Playwright verifier. A passing result requires the boundary row to fit and the next row to trigger the next column or whole-summary overflow exactly as designed.

**Review checkpoint:** Inspect the generated back-page and first overflow-page PNGs, not only script exit status. Confirm no clipping, overlap, tiny text, or missing row. Do not stage or commit artifacts.

---

### Task 11: Authoritative Documentation And Migration Recordkeeping

**Files:**
- Modify: `README.md`
- Modify: `docs/implementation-notes/print-output-reference.md`
- Create: `docs/implementation-notes/roll-pallet-assignment.md`
- Modify: `v2-files/AGENTS.md`
- Modify carefully: `v2-files/PLAN.md`

**Consumes:** Actual finished behavior, measured print capacities, test evidence, and final diff.

**Produces:** Durable source-of-truth requirements and truthful M003/development records.

- [ ] **Step 1: Update the authoritative project contract**

Add concise confirmed facts to `README.md`: optional per-roll pallet number, card-level current value for future rolls, correction support, mixed finish warning, and operational-card pallet aggregates. Add label printing, shipping tracking, and pallet lifecycle to explicit exclusions for this feature.

- [ ] **Step 2: Update print documentation**

In `print-output-reference.md`:

- replace “always exactly two pages” with two pages normally and page 3+ only for pallet-summary overflow;
- document the left production block, two page-2 pallet blocks, headings, one-decimal totals, numeric order, conditional `Без палет`, all-blank omission, and repeated overflow identification;
- retain the 120-roll grid/readiness limit and blank `Дата / смяна` contract;
- record the measured renderer capacities as implementation facts, not business limits.

Create `roll-pallet-assignment.md` with M003 fields/constraints, no-backfill rule, parser error, current-versus-snapshot semantics, transaction/conflict rules, import preservation, finish warning boundary, and recovery/rollback note.

- [ ] **Step 3: Re-inspect concurrent V2 changes before editing**

```bash
git status --short
git diff -- v2-files/PLAN.md v2-files/TASK-13-BACKUP-RESILIENCE.md
```

If another agent still owns overlapping `PLAN.md` lines, do not overwrite them. Wait for integration or make only a narrowly non-overlapping Task 12 patch after re-reading the current file.

- [ ] **Step 4: Replace the superseded Task 12 description**

Record that the implemented feature is per-roll pallet attribution plus operational-card summary. Explicitly defer the former package table, package selection workflow, label route, void/reprint lifecycle, shipping state, and cross-card packaging. Mark complete only after all verification in Task 12 passes.

- [ ] **Step 5: Maintain the migration register from evidence**

Append M003 `roll_pallet_assignment` to `v2-files/AGENTS.md` only after tests pass. Record schema-only/no-value-change behavior, focused/full test counts, integrity/foreign-key results, browser/PDF evidence, and that no production snapshot is needed for M003 itself. Preserve the separate M001 profiling and final release-candidate rehearsal deployment gates.

Use this final user-facing structure:

```text
Migration assessment
- Decision: Schema-only
- Why: cards.current_pallet_number and roll_entries.pallet_number are new constrained persisted columns
- Existing production data affected: no existing values; both new columns remain NULL on historical rows
- Proposed migration: M003 roll_pallet_assignment
- Transformation: no values changed
- Unknowns or ambiguous rows: none known; historical pallet assignment is deliberately not inferred
- Required tests: fresh, legacy, partial, malformed, repeat-run, rollback, constraints, preservation, integrity, and foreign-key checks on temporary databases
- Production snapshot needed now: No
- Deployment constraint: deploy M003 and consuming application code together after a SQLite-safe backup; M001 profiling and final release-candidate rehearsal remain separate gates
```

**Review checkpoint:** Documentation must describe actual verified behavior and measured values only. Do not stage or commit.

---

### Task 12: Full Verification, Review, And Handoff

**Files:**
- Review: every changed source/test/documentation file
- Do not include: `.test-runtime/`, `artifacts/`, databases, screenshots, PDFs, Playwright reports, `node_modules/`

**Consumes:** All completed tasks.

**Produces:** Evidence-backed implementation ready for user review, with no unauthorized commit.

- [ ] **Step 1: Run syntax/import checks**

```bash
.venv/bin/python -m compileall app tests scripts
```

Expected: PASS.

- [ ] **Step 2: Run the focused affected suite**

```bash
.venv/bin/python -m pytest \
  tests/test_migrations.py \
  tests/test_baseline.py \
  tests/test_roll_entry.py \
  tests/test_terminal_v8_render.py \
  tests/test_admin_card_detail_redesign.py \
  tests/test_admin_production_corrections.py \
  tests/test_finish_cancel_history.py \
  tests/test_production_timing.py \
  tests/test_print_output.py \
  tests/test_print_template_fixture_script.py \
  tests/test_roll_pallet_ui_script_safety.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run the full suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: PASS with the exact count recorded in implementation notes/V2 migration evidence.

- [ ] **Step 4: Run repository checks**

```bash
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors; only intended feature/docs changes plus clearly identified concurrent user/agent files; no database/artifact paths tracked.

- [ ] **Step 5: Inspect schema integrity on a temporary migrated fixture**

Run `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, and query `schema_migrations` on the Task 10 temporary database. Expected: `ok`, no FK rows, M001/M002/M003 recorded once.

- [ ] **Step 6: Re-run the live Playwright/PDF acceptance command from Task 10**

Expected: exit `0` and fresh artifacts matching the finalized capacity constants.

- [ ] **Step 7: Review against the approved design**

Use `superpowers:requesting-code-review`. Check specifically:

- no current-to-historical roll propagation;
- no correction-to-current propagation;
- no partial write on invalid/stale forms;
- no import overwrite;
- no pallet finish blocker;
- no guessed/persisted aggregates;
- no page-2 partial summary on overflow;
- no omitted pallet rows;
- no pallet-management/label/shipping scope creep;
- unchanged recipe visibility, 120-roll grid, shift/tare/net/timing behavior.

- [ ] **Step 8: Provide the user handoff**

Report:

- implemented behavior and explicit exclusions;
- M003 migration assessment using the exact structure in Task 11;
- focused/full test commands and counts;
- Playwright command and artifact paths;
- measured page-2 and overflow capacities as renderer facts;
- any remaining printer-only calibration risk;
- current worktree status and that nothing was staged or committed.

Do not stage, commit, push, deploy, or touch the production database unless the user separately authorizes it.
