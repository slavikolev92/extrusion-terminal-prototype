# Physical Pallet Weight Implementation Plan

> **Precision amendment (2026-09-11):** The persisted/displayed physical-pallet
> precision in this original execution plan is superseded by
> `docs/superpowers/plans/2026-09-11-physical-pallet-weight-two-decimal-precision.md`.
> Do not reintroduce integer-tenths storage or one-decimal pallet values.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans (recommended because these tasks share schema and
> interface state) or, if the user explicitly authorizes delegated execution,
> superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax
> for tracking.

**Plan status:** Execution-ready after final review corrections and consistency
check on 2026-09-10. The design and interactive prototype are approved;
production implementation has not started. Execution begins with the
authority-status checkpoint in Task 0.

**Acceptance correction:** The feature implementation is now present on its
feature branch. The approved post-implementation corrections to numeric input,
dismissal, semantic feedback, and the terminal pallet-action icon are specified
and executed separately in
`docs/superpowers/plans/2026-09-11-physical-pallet-weight-acceptance-corrections.md`.
That later plan supersedes conflicting validation and dismissal details below.

**Goal:** Add optional, separately editable physical transport-pallet weights per numbered card pallet, enforce complete data once weight entry is activated, display correct six-column pallet calculations, and carry the values into the existing operational-card print.

**Architecture:** Add a schema-only per-card/per-pallet table that stores exact tenths of a kilogram, extend `app/pallet_summary.py` into the single pure owner of pallet calculations and completeness, and keep persistence and finish enforcement in `app/db.py`. Reuse one server-rendered modal with always-visible per-pallet inputs on terminal and admin surfaces. A small vanilla-JavaScript controller serializes immediate field saves; the terminal monitor accepts only an allowlisted selected-card version change after local saves; every Finish Review refreshes one version-consistent server payload before opening; and print pagination carries one explicit totals row.

**Tech Stack:** Python 3, FastAPI, Jinja2, direct `sqlite3`, `Decimal`, pytest with temporary SQLite databases, vanilla JavaScript ES modules, Node test runner, repository-local Playwright, HTML/CSS print.

**Spec:** `docs/superpowers/specs/2026-09-09-physical-pallet-weight-design.md`

## Global Constraints

- Read `README.md`, the supplied `AGENTS.md`, the specification above, `docs/implementation-notes/sqlite-migration-and-deployment-playbook.md`, and the user-approved `ui-prototypes/physical-pallet-weight-summary.html` before implementation.
- The user approved `ui-prototypes/physical-pallet-weight-summary.html` on
  2026-09-10. If that accepted wording, structure, or interaction changes,
  update the specification and this plan before writing application code.
- Preserve the unrelated untracked `TEMP - Task 20 requirements-spec.md`; do not edit, remove, stage, or commit it.
- Do not stage or commit unless the user explicitly asks. Each task ends at a review checkpoint; a later user-approved checkpoint may group those reviewed files into a commit.
- Use the next version from `app/migrations.py` at execution time. It is M007 in the current source, but stop and reconcile if that registry changes before implementation.
- The migration is schema-only. Never infer or backfill physical pallet weights from roll-core tare, roll gross, product data, or pallet number.
- Store physical pallet weight as integer tenths of a kilogram from `1` through `1000`; no row means missing. Never store zero as a missing-value sentinel.
- Accept blank or an unsigned integer with up to two fractional digits using
  `.` or `,`; normalize accepted values with exact half-up rounding and display
  one decimal place. Reject zero, negative values, raw values above `100.0 kg`,
  and positive values whose rounded result would be below `0.1 kg`.
- A pallet-weight value is owned by `(card_id, pallet_number)`. `Без палет` and `cards.current_pallet_number` never own a value.
- If a roll mutation leaves no gross roll assigned to a numbered pallet, delete that pallet's physical weight in the same transaction.
- Structurally validate the shared pallet summary inside every finish
  transaction. A valid partial set may enter `awaiting_rewinding`; orphaned or
  inconsistent saved data may not.
- No weights is valid. Once any weight exists, normal completion and waiting-card finalization require every gross roll to have a numbered pallet and every used numbered pallet to have a weight. Entry into `awaiting_rewinding` remains allowed with a warning because it is not final completion.
- Completed and archived corrections use the same one-field-at-a-time persistence. Partial post-completion state may exist temporarily, but printing remains blocked until the set is complete or fully cleared.
- `Нето, кг` remains the sum of existing roll net weights. Physical pallet weight changes only `Тегло палет, кг` and `Бруто с палет, кг`.
- Missing pallet weight and gross-with-pallet display as `-`, never `0.0`. The two corresponding total cells remain `-` until the weight set is complete.
- Every pallet table uses this exact order and Bulgarian copy: `Палет №`, `Брой ролки`, `Бруто без палет, кг`, `Тегло палет, кг`, `Бруто с палет, кг`, `Нето, кг`.
- Preserve existing finish-review timing behavior, token safety, `awaiting_rewinding` timing neutrality, mixed-pallet warning behavior when no physical weights exist, and existing print eligibility.
- Refresh the complete, server-authoritative Finish Review payload every time
  any finish variant opens. Never use page-load pallet rows as confirmation
  data after an inline save.
- After a local autosave queue, silently reconcile only the expected selected-
  card version/timestamp delta. Other-card, queue, lifecycle, or shift changes
  must retain the normal stale-data warning.
- Print `Общо` exactly once after the final pallet row. It consumes page
  capacity and must remain with at least one preceding pallet row.
- The shipping/transport pallet-label workflow, archive removal, pallet lifecycle, inventory, barcode, scanning, and Task 20 work are out of scope.
- Automated and browser tests use only temporary databases. Never mutate `data/extrusion_terminal.sqlite3`, `production-db/`, or a production backup.
- Browser evidence belongs under `artifacts/ui-checks/physical-pallet-weight/` and is deleted after user acceptance unless retention is explicitly requested.

## File Structure

**Approved inputs (read; do not redesign during implementation):**

- `docs/superpowers/specs/2026-09-09-physical-pallet-weight-design.md`
- `docs/superpowers/plans/2026-09-09-physical-pallet-weight.md`
- `ui-prototypes/physical-pallet-weight-summary.html`

**Create:**

- `app/templates/_pallet_summary_modal.html` — shared terminal/admin modal markup.
- `app/static/css/pallet_summary.css` — modal/table styling shared by terminal and admin.
- `app/static/js/pallet_weight_autosave_core.mjs` — pure input parsing and serialized-task-queue helpers.
- `app/static/js/pallet_weight_autosave.mjs` — field autosave, validation feedback, authoritative row/total refresh, save-aware dismissal, and focus behavior.
- `app/static/js/pallet_weight_terminal_sync_core.mjs` — pure validation and
  allowlisted comparison of pre-save and post-save terminal snapshots.
- `app/static/js/finish_review_pallet_state.mjs` — validate and atomically
  apply authoritative pallet rows, totals, messages, and eligibility to the
  shared Finish Review dialog.
- `tests/test_physical_pallet_weights.py` — focused persistence, permissions, validation, cleanup, and conflict tests.
- `tests/js/pallet_weight_autosave_core.test.mjs` — pure JavaScript parser and queue tests.
- `tests/js/pallet_weight_terminal_sync_core.test.mjs` — local-only versus
  external terminal-snapshot change classification.
- `tests/js/finish_review_pallet_state.test.mjs` — authoritative Finish Review
  payload validation and replacement behavior.
- `docs/implementation-notes/physical-pallet-weight.md` — final implementation and migration assessment.

**Modify:**

- `app/schema.py` — canonical `card_pallet_weights` table definition.
- `app/migrations.py` — ordered M007 schema migration and schema validator.
- `app/db.py` — weight loading, atomic terminal/admin saves, cleanup after roll mutations, and final-completion validation.
- `app/pallet_summary.py` — shared six-column aggregation, completeness, exact calculation, and presentation.
- `app/main.py` — terminal/admin single-field save routes, JSON feedback, modal context, and finish-review model integration.
- `app/templates/base.html` — optional page-head block for shared modal stylesheet.
- `app/templates/terminal.html` — modal trigger/include, accepted six-column finish-review table, host modal coordination, and shared scripts.
- `app/templates/admin_card_detail.html` — admin summary trigger/include and result feedback.
- `app/static/js/timing_interval_editor.mjs` — replace active Finish Review from
  its authoritative open response.
- `app/static/js/waiting_finish_review.mjs` — refresh the read-only waiting
  Finish Review before every open.
- `app/static/js/waiting_finish_review_core.mjs` — validate the refreshed
  waiting-review contract.
- `app/static/js/roll_change_countdown.mjs` — adopt the expected local
  selected-card version without resetting lifecycle timing.
- `app/static/js/roll_change_countdown_core.mjs` — pure local-version adoption
  helper.
- `app/printing.py` — use shared pallet summary, validate completeness, and revise page-2/overflow layout model.
- `app/templates/print_card.html` — six-column pallet tables.
- `app/static/css/print.css` — one wide page-2 pallet table and readable six-column widths.
- `tests/test_migrations.py` — M007 upgrade and safety coverage.
- `tests/test_terminal_pallet_summary.py` — new view-model and rendering contract.
- `tests/test_terminal_pallet_summary_scripts.py` — fixture/verifier contract updates.
- `tests/test_roll_entry.py` — orphan-weight cleanup through terminal mutations.
- `tests/test_admin_card_detail_redesign.py` — admin modal, correction route, and cleanup behavior.
- `tests/test_rewinding_workflow.py` — final-completion blockers and waiting-entry warning.
- `tests/test_terminal_timing_correction.py` — preserve timing-preview and
  finish-recovery behavior while the shared summary signature changes.
- `tests/test_order_finish_review_ui_script_safety.py` — six-column finish-review contract and recovery state.
- `tests/test_print_output.py` — six-column print calculations/readiness/layout.
- `scripts/create_terminal_pallet_summary_fixture.py` — none, partial, complete, mixed, and many-pallet browser fixtures.
- `scripts/verify_terminal_pallet_summary_ui.mjs` — terminal and admin interaction/geometry verification.
- `scripts/audit_terminal_pallet_summary_db.py` — verify expected writes and absence of unrelated mutations.
- `scripts/create_print_template_fixture.py` — deterministic no-weight,
  complete-boundary, first-overflow, and overflow-boundary print fixtures.
- `scripts/render_print_template.mjs` — variable expected page counts and
  capture of every rendered PDF page.
- `tests/test_print_template_fixture_script.py` — print fixture/render contract
  and output-path guards.

**Modify in the pre-implementation authority checkpoint and again after user acceptance:**

- `README.md` — first record approved-but-unimplemented status; after acceptance,
  replace it with the implemented contract.
- `AGENTS.md` — first replace the obsolete open-design gate with the approved
  implementation boundary; after acceptance, remove the unimplemented-slice
  instruction.
- `v2-files/PLAN.md` — first record that Task 23 design is approved and in
  implementation; after acceptance, mark Task 23 complete and preserve Task 20
  as next.

**Modify only after implementation acceptance:**

- `docs/implementation-notes/print-output-reference.md` — replace the obsolete
  two-block pallet-print contract with the measured six-column layout and
  cross-link the feature implementation note.

---

### Task 0: Record The Approved Implementation Gate

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `v2-files/PLAN.md`

**Interfaces:**
- Produces: one consistent repository-wide statement that the physical
  pallet-weight design is approved, the implementation is authorized as the
  current slice, and the feature remains unimplemented and undeployed
- Preserves: Task 20 as later work and Task 23 as incomplete until post-build
  user acceptance

- [ ] **Step 1: Assert the recorded approval and current source state**

Read the three authority files beside the approved specification and this plan.
Confirm that the current source still contains only the presentation-only
`0.0` seam and no physical pallet-weight persistence. Stop if application code
already implements any part of the slice or if the migration registry no longer
ends at M006; reconcile the plan before continuing.

- [ ] **Step 2: Update status language only**

Replace the obsolete instruction to brainstorm undecided ownership and
validation semantics. State that the approved design is
`docs/superpowers/specs/2026-09-09-physical-pallet-weight-design.md`, this is the
current authorized implementation slice, and production implementation and
deployment have not started. Do not describe the feature as available, remove
the existing placeholder code, mark Task 23 complete, or change Task 20.

- [ ] **Step 3: Verify the authority files agree**

Run:

```bash
rg -n "physical pallet|Physical pallet|физическ.*палет|Task 23|Task 20" README.md AGENTS.md v2-files/PLAN.md
git diff --check
```

Expected: all three documents identify the same approved specification and
unimplemented status, Task 23 remains open/in progress, and Task 20 remains
later and unimplemented.

---

### Task 1: Add The M007 Physical-Pallet-Weight Schema

**Files:**
- Modify: `app/schema.py`
- Modify: `app/migrations.py`
- Test: `tests/test_migrations.py`

**Interfaces:**
- Produces: `CARD_PALLET_WEIGHTS_TABLE_SQL: str`
- Produces: `apply_m007_physical_pallet_weights(connection: sqlite3.Connection) -> None`
- Produces: `validate_card_pallet_weights_schema(connection: sqlite3.Connection) -> None`
- Consumes later: table `card_pallet_weights(card_id, pallet_number, weight_tenths, created_at, updated_at)`

- [ ] **Step 1: Write failing fresh-schema and constraint tests**

Add tests that initialize a temporary database, inspect `sqlite_master`, and
prove the composite key and range/type constraints:

```python
def test_fresh_schema_has_exact_card_pallet_weights_contract(connection):
    sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'card_pallet_weights'"
    ).fetchone()[0]
    assert "PRIMARY KEY (card_id, pallet_number)" in sql
    assert "weight_tenths BETWEEN 1 AND 1000" in sql
    assert connection.execute(
        "PRAGMA foreign_key_list(card_pallet_weights)"
    ).fetchone()[2:7] == ("cards", "card_id", "id", "NO ACTION", "CASCADE")


@pytest.mark.parametrize("weight_tenths", (0, 1001, 1.5, "not-an-integer"))
def test_card_pallet_weight_rejects_invalid_storage(connection, weight_tenths):
    card_id = insert_card(connection, order_number=f"PW-{weight_tenths}")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO card_pallet_weights (card_id, pallet_number, weight_tenths) VALUES (?, 1, ?)",
            (card_id, weight_tenths),
        )
```

Add a separate SQLite-affinity test showing that direct numeric text such as
`"10"` is normalized by the `INTEGER` column to integer storage. Do not expect
the DDL to reject a representation that SQLite converts before evaluating the
`typeof(...)` constraint. Strict submitted-text syntax remains an application-
parser and route responsibility.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_migrations.py -k card_pallet_weight -vv
```

Expected: failure because `card_pallet_weights` and M007 do not exist.

- [ ] **Step 3: Add the canonical table SQL and M007**

Define `CARD_PALLET_WEIGHTS_TABLE_SQL` once in `app/schema.py` and import it in
`app/migrations.py`. M007 executes that `CREATE TABLE IF NOT EXISTS` SQL and
then validates the exact column, constraint, composite-primary-key, and
cascade-foreign-key contract. Do not interpolate this new table into
`app/db.py:SCHEMA_SQL`: `init_db()` runs the ordered migration chain after the
base schema, so keeping creation in M007 preserves transactional rollback for
both fresh databases and upgrades. Extend `MIGRATIONS` only after checking its
current final version:

```python
MIGRATIONS = (
    Migration(1, "shift_manager_import_fields", _apply_shift_manager_import_fields),
    Migration(2, "shift_management", _apply_shift_management),
    Migration(3, "roll_pallet_assignment", _apply_roll_pallet_assignment),
    Migration(4, "rewinding_return_workflow", apply_m004_rewinding_return_workflow),
    Migration(5, "shift_schema_contract", apply_m005_shift_schema_contract),
    Migration(6, "legacy_import_normalization", apply_m006_legacy_import_normalization),
    Migration(7, "physical_pallet_weights", apply_m007_physical_pallet_weights),
)
```

Call `validate_card_pallet_weights_schema()` from startup migration validation
after pending migrations have applied. M007 uses `IF NOT EXISTS` only so it can
validate and accept an exact pre-existing table; it must reject a malformed
look-alike rather than recording version 7 over it.

- [ ] **Step 4: Add upgrade, no-backfill, idempotence, and rollback tests**

Build accepted version-6 temporary schemas and assert:

```python
assert before_roll_rows == after_roll_rows
assert before_card_rows == after_card_rows
assert connection.execute("SELECT COUNT(*) FROM card_pallet_weights").fetchone()[0] == 0
assert applied_versions == (7,)
assert second_applied_versions == ()
assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
```

Inject a failure after table creation and prove the table and migration-history
row both roll back. Add malformed pre-existing `card_pallet_weights` cases for
wrong columns, constraints, primary key, and foreign-key action; initialization
must fail instead of accepting a look-alike table.

- [ ] **Step 5: Run migration and baseline checks**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_migrations.py -vv
python -m compileall -q app tests
git diff --check
```

Expected: all pass. Stop at a review checkpoint; do not commit without explicit
authorization.

---

### Task 2: Make Pallet Summary The Single Calculation Owner

**Files:**
- Modify: `app/pallet_summary.py`
- Modify: `app/db.py`
- Test: `tests/test_terminal_pallet_summary.py`
- Test: `tests/test_physical_pallet_weights.py`

**Interfaces:**
- Produces: `parse_physical_pallet_weight(raw: str, pallet_number: int) -> tuple[int | None, str | None]`
- Produces: `build_pallet_summary(roll_entries: Iterable[Mapping[str, Any]], pallet_weights: Mapping[int, int]) -> dict[str, Any]`
- Produces: `fetch_card_pallet_weights(connection: sqlite3.Connection, card_id: int) -> dict[int, int]`
- Produces: `load_card_pallet_summary(connection: sqlite3.Connection, card_id: int) -> dict[str, Any]`
- Produces result fields: `state`, `weight_state`, `rows`, `total`, `used_pallet_numbers`, `missing_weight_pallet_numbers`, `unassigned_roll_count`

- [ ] **Step 1: Write failing parser tests**

Use table-driven cases with exact results:

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    (("", None), ("   ", None), ("12", 120), ("12.0", 120),
     ("12,5", 125), ("0.1", 1), ("100", 1000)),
)
def test_parse_physical_pallet_weight_accepts_approved_values(raw, expected):
    assert parse_physical_pallet_weight(raw, 3) == (expected, None)


@pytest.mark.parametrize("raw", ("0", "0.0", "-1", "12.55", ".5", "1e1", "NaN", "12 5", "101"))
def test_parse_physical_pallet_weight_rejects_invalid_values(raw):
    value, message = parse_physical_pallet_weight(raw, 3)
    assert value is None
    assert message is not None
    assert "палет №3" in message
```

Assert the special maximum message exactly for `100.1` and `330`:
`Теглото за палет №3 не може да бъде повече от 100.0 кг.`

- [ ] **Step 2: Write failing six-column summary tests**

Cover no weights, complete weights, partial weights, mixed assignment,
all-unassigned, empty, exact decimal addition, and an orphan weight. A complete
row contract is:

```python
{
    "pallet_number": 2,
    "pallet_label": "2",
    "roll_count": 2,
    "gross_without_pallet": Decimal("230.00"),
    "pallet_weight": Decimal("18.5"),
    "gross_with_pallet": Decimal("248.50"),
    "net_weight": Decimal("226.00"),
    "gross_without_pallet_display": "230.0",
    "pallet_weight_display": "18.5",
    "gross_with_pallet_display": "248.5",
    "net_display": "226.0",
    "pallet_weight_input": "18.5",
}
```

For missing weights, assert both dependent displays are `-`. For a partial or
mixed set, assert the two dependent total displays are `-` even though complete
individual rows may show their own gross-with-pallet value. Assert an orphan
saved weight raises `PalletSummaryDataError`.

The total object uses the same calculation names as rows plus
`pallet_weight_display` and `gross_with_pallet_display`. It has no editable
input value. `state` remains the presentation state (`empty` or `ready`), while
`weight_state` is independently `none`, `partial`, or `complete`; an empty or
all-unassigned summary has `weight_state == "none"`.

- [ ] **Step 3: Run the tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_pallet_summary.py tests/test_physical_pallet_weights.py -vv
```

Expected: imports or assertions fail because the parser and six-column model do
not exist.

- [ ] **Step 4: Implement exact parsing and shared aggregation**

Use a full-match expression equivalent to `[0-9]+(?:[.,][0-9])?`. Strip leading
zeroes and reject an overlong/significantly-greater-than-100 whole part before
calling `int()`, so even hostile oversized input receives the normal maximum
error instead of hitting Python's integer-string limit. Convert only the
bounded digit parts to integer tenths and branch separately for the specific
over-maximum error. Do not call `float()`.

Replace the terminal-only zero placeholder with a shared summary builder. Sum
saved roll values as exact `Decimal`, validate the existing gross/tare/net
invariant, validate every weight key/value, raise `PalletSummaryDataError` when
a stored weight does not belong to a currently used numbered pallet, merge the
remaining integer-tenths values, and derive:

```python
weight_state = (
    "none" if not pallet_weights
    else "complete" if not missing_numbers and unassigned_roll_count == 0
    else "partial"
)
```

Keep `build_terminal_pallet_summary()` as a narrow compatibility wrapper only
if existing callers need a staged transition; by the end of the task all new
semantics must come from `build_pallet_summary()`.

- [ ] **Step 5: Load weights with every detailed card snapshot**

Add `fetch_card_pallet_weights()` and include its mapping in
`fetch_roll_entries_and_totals()`. Return integer tenths without converting
through binary floating point:

```python
return {
    int(row["pallet_number"]): int(row["weight_tenths"])
    for row in rows
}
```

This automatically supplies terminal detail, admin detail, finish review, and
print readiness through their existing card fetches.

Add `load_card_pallet_summary()` as the connection-owning adapter used inside
write/finish transactions. It loads the roll entries and physical weights once
through the supplied connection and calls the pure builder. It intentionally
allows `PalletSummaryDataError` to propagate to the narrow service boundary;
it must not catch arbitrary exceptions or open a second connection.

- [ ] **Step 6: Run focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_pallet_summary.py tests/test_physical_pallet_weights.py -vv
git diff --check
```

Expected: all pass. Review the view-model keys for consistent naming before the
next task.

---

### Task 3: Add Atomic Per-Pallet Save Rules And Orphan Cleanup

**Files:**
- Modify: `app/db.py`
- Test: `tests/test_physical_pallet_weights.py`
- Test: `tests/test_roll_entry.py`
- Test: `tests/test_admin_card_detail_redesign.py`

**Interfaces:**
- Produces: `PalletWeightIssue(pallet_number: int | None, field: str, message: str)`
- Produces: `PalletWeightSaveOutcome(result: RuleResult, issues: tuple[PalletWeightIssue, ...], card_version: int | None, saved_weight_tenths: int | None, summary: dict[str, Any] | None)`
- Produces: `update_terminal_pallet_weight(card_id: int, pallet_number: int, loaded_version: int, raw_weight: str, *, require_active_shift: bool = True) -> PalletWeightSaveOutcome`
- Produces: `update_admin_pallet_weight(card_id: int, pallet_number: int, loaded_version: int, raw_weight: str) -> PalletWeightSaveOutcome`
- Produces: `delete_unused_card_pallet_weights(connection: sqlite3.Connection, card_id: int) -> tuple[int, ...]`

Use one explicit outcome shape for both services:

```python
@dataclass(frozen=True)
class PalletWeightIssue:
    pallet_number: int | None
    field: str
    message: str


@dataclass(frozen=True)
class PalletWeightSaveOutcome:
    result: RuleResult
    issues: tuple[PalletWeightIssue, ...] = ()
    card_version: int | None = None
    saved_weight_tenths: int | None = None
    summary: dict[str, Any] | None = None
```

- [ ] **Step 1: Write failing persistence and permission tests**

Create two cards that both use pallet `1`; save different values and prove
isolation. Cover terminal saves for pending/running/paused/waiting/completed,
active-shift enforcement, admin saves only for completed/archived, one parent
version increment, and unchanged rows/version on every failure.

After saving a weight, run the existing overwrite-import path for the same
order and assert the `card_pallet_weights` row, roll assignments, card status,
and card version semantics are preserved exactly as production data.

Assert every allowed status can save pallet `1` without requiring pallet `2`
in the same request. Then save pallet `2` separately and prove each successful
request increments the version once. Assert a blank value clears only the
target pallet in every allowed status.

- [ ] **Step 2: Write failing submission-shape and conflict tests**

For a card whose gross rolls use pallets `1` and `3`, accept target `1` or `3`
and reject an unused target such as `2`, an out-of-range pallet number, or a
stale `loaded_version`. Use `interleave_committed_card_version` to prove a
concurrent card/roll write wins and the stale pallet-weight save writes
nothing.

- [ ] **Step 3: Write failing lifecycle-cleanup tests**

Prove all of these transaction outcomes:

- deleting the last gross roll on pallet `4` removes weight `4`;
- moving that roll to pallet `5` removes weight `4`;
- clearing its gross weight removes weight `4`;
- deleting one of two gross rolls on pallet `4` preserves weight `4`;
- a multi-row terminal correction and the admin roll-ledger save run cleanup
  once after all row mutations, so an old pallet still used by a remaining row
  is retained; and
- the cleanup message lists removed pallet numbers in numeric order.

- [ ] **Step 4: Run focused tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_physical_pallet_weights.py tests/test_roll_entry.py tests/test_admin_card_detail_redesign.py -k "pallet_weight or unused_pallet" -vv
```

Expected: failure because save services and cleanup do not exist.

- [ ] **Step 5: Implement the atomic save services**

Both public services start `BEGIN IMMEDIATE`, validate the card version and
allowed status, enforce terminal shift rules when requested, prove the target
number is still a used pallet, and validate the one raw value with the shared
parser before writing.

Keep the public surface explicit:

```python
def update_terminal_pallet_weight(
    card_id: int,
    pallet_number: int,
    loaded_version: int,
    raw_weight: str,
    *,
    require_active_shift: bool = True,
) -> PalletWeightSaveOutcome:
    return _update_card_pallet_weight(
        card_id,
        pallet_number,
        loaded_version,
        raw_weight,
        allowed_statuses=TERMINAL_VISIBLE_STATUSES,
        require_active_shift=require_active_shift,
    )


def update_admin_pallet_weight(
    card_id: int,
    pallet_number: int,
    loaded_version: int,
    raw_weight: str,
) -> PalletWeightSaveOutcome:
    return _update_card_pallet_weight(
        card_id,
        pallet_number,
        loaded_version,
        raw_weight,
        allowed_statuses=PRODUCTION_COMPLETE_STATUSES,
        require_active_shift=False,
    )
```

On success, upsert only the targeted nonblank value or delete only the targeted
row for a blank value:

```sql
DELETE FROM card_pallet_weights WHERE card_id = ? AND pallet_number = ?;
```

For a valid nonblank value, use an SQLite upsert that preserves `created_at`
and refreshes only `weight_tenths` and `updated_at` on conflict. Update the parent card exactly
once with `version = version + 1, updated_at = CURRENT_TIMESTAMP`. Before the
transaction exits, re-read rolls and pallet weights and build the authoritative
summary that belongs to that new version. Return the normalized stored tenths,
new card version, summary, and an issue list suitable for field-level feedback.
Do not re-query after commit to assemble the response, because a concurrent
write could otherwise make the returned summary disagree with its version.
Do not reject partial state during field entry, regardless of allowed card
status; completion and print boundaries enforce completeness separately.

If `load_card_pallet_summary()` raises the defined
`PalletSummaryDataError`, convert it to a structured non-success outcome inside
the transaction so the attempted weight mutation and card-version increment
roll back. Catch only that data exception; unexpected programming errors must
remain visible to tests and application logging. Add a corrupted-state service
test proving the row and parent version remain unchanged.

- [ ] **Step 6: Add cleanup to every roll mutation path**

Call `delete_unused_card_pallet_weights()` after final roll changes and before
the transaction exits in:

- `update_roll_weight()`;
- `update_terminal_roll_corrections()`;
- `delete_roll_entry()`; and
- `_update_admin_roll_ledger()`.

The helper selects currently weighted pallet numbers no longer referenced by
any row satisfying `gross_weight IS NOT NULL AND pallet_number IS NOT NULL`,
deletes only those rows, and returns their ordered numbers. Append a concise
message such as `Премахнато е теглото за неизползвания палет №4.` without an
extra card-version increment.

Use one helper call at the end of each mutation, after all updates/deletes:

```python
removed_pallets = delete_unused_card_pallet_weights(connection, card_id)
messages = ["Ролките са записани."]
if removed_pallets:
    labels = ", ".join(f"№{number}" for number in removed_pallets)
    messages.append(f"Премахнати са теглата за неизползваните палети {labels}.")
return RuleResult(True, tuple(messages))
```

- [ ] **Step 7: Run focused and regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_physical_pallet_weights.py tests/test_roll_entry.py tests/test_admin_card_detail_redesign.py -vv
git diff --check
```

Expected: all pass and existing roll-number renumbering, gross/net calculation,
and optimistic conflicts remain unchanged.

---

### Task 4: Add Terminal And Admin Field-Save Routes With Recoverable Feedback

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_physical_pallet_weights.py`
- Test: `tests/test_terminal_pallet_summary.py`
- Test: `tests/test_admin_card_detail_redesign.py`

**Interfaces:**
- Produces: `POST /terminal/cards/{card_id}/pallet-weights/{pallet_number}`
- Produces: `POST /admin/cards/{card_id}/pallet-weights/{pallet_number}`
- Produces: `pallet_weight_json_response(outcome: PalletWeightSaveOutcome, *, pallet_number: int, submitted_weight: str) -> JSONResponse`
- Produces: `pallet_summary_display_payload(summary: Mapping[str, Any]) -> dict[str, Any]`
- Consumes form fields: `loaded_version`, `pallet_weight`
- Produces success JSON: `ok`, `card_version`, `pallet_number`, `normalized_weight`, `row`, `total`, `weight_state`, `messages`, `reload_required`
- Produces error JSON: `ok`, `submitted_weight`, `messages`, `field_errors`, `reload_required`

- [ ] **Step 1: Write failing request-shape tests**

Accept exactly one `pallet_weight` value and one valid `loaded_version` for the
path pallet. Reject duplicate, missing, or unexpected fields, out-of-range path
values, and an unused pallet. Preserve the raw value exactly for validation
feedback.

- [ ] **Step 2: Write failing route tests**

For both routes assert:

- successful saves return the authoritative new value and incremented version;
- terminal save without an active shift is blocked;
- invalid input returns structured feedback identifying the path pallet while
  preserving the submitted text and writing nothing;
- stale saves return the existing reload-required message and no write;
- success returns the new version plus authoritative affected-row and total
  display values as JSON strings/integers, with no raw `Decimal` or float
  conversion, without redirecting or closing the modal; and
- neither route accepts a pallet number absent from current gross rolls.

- [ ] **Step 3: Run route tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_physical_pallet_weights.py tests/test_terminal_pallet_summary.py tests/test_admin_card_detail_redesign.py -k "pallet_weight_route or pallet_weight_form" -vv
```

- [ ] **Step 4: Implement strict field routes and response adapters**

Parse `await request.form()` with `multi_items()` so duplicate values cannot be
collapsed silently. Pass the path pallet and the one raw value to the correct
database service. Build the response from the transaction-consistent outcome;
do not calculate, persist, or re-fetch pallet values in `app/main.py`.

Use one adapter for the terminal and admin JSON contract. A successful clear
returns `normalized_weight: ""`; a saved value returns one decimal place.
Project the calculation result into a JSON-safe display payload: include pallet
number/label, roll count, and the four weight display strings for rows, plus
roll count and the four display strings for totals. Do not place raw `Decimal`
objects in `JSONResponse`, and do not serialize them through binary floats. The
response's `row` is the affected projected row and `total` is the projected
authoritative total. Set `reload_required` to `false` on success.

Return validation/permission errors as HTTP 422 with the raw
`submitted_weight`; return stale-card errors as HTTP 409 with
`reload_required: true`. Each `field_errors` entry has
`pallet_number`, `field`, and `message`; use `field: "pallet_weight"` for a
targeted input and `field: "form"` for cross-cutting failures such as an
inactive shift. Follow the existing timing-editor JSON error pattern. Never
redirect, reload, or close the modal after a successful field save.

The success adapter should be equivalent to:

```python
assert outcome.card_version is not None
assert outcome.summary is not None
display = pallet_summary_display_payload(outcome.summary)
row = next(
    row
    for row in display["rows"]
    if row["pallet_number"] == pallet_number
)
return JSONResponse({
    "ok": True,
    "card_version": outcome.card_version,
    "pallet_number": pallet_number,
    "normalized_weight": (
        "" if outcome.saved_weight_tenths is None
        else f"{outcome.saved_weight_tenths // 10}.{outcome.saved_weight_tenths % 10}"
    ),
    "row": row,
    "total": display["total"],
    "weight_state": outcome.summary["weight_state"],
    "messages": list(outcome.result.messages),
    "reload_required": False,
})
```

- [ ] **Step 5: Run focused route tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_physical_pallet_weights.py tests/test_terminal_pallet_summary.py tests/test_admin_card_detail_redesign.py -vv
git diff --check
```

Expected: all pass.

---

### Task 5: Build The Shared Inline-Entry Pallet Modal

**Prerequisite satisfied:** The user approved
`ui-prototypes/physical-pallet-weight-summary.html` on 2026-09-10.

**Files:**
- Create: `app/templates/_pallet_summary_modal.html`
- Create: `app/static/css/pallet_summary.css`
- Create: `app/static/js/pallet_weight_autosave_core.mjs`
- Create: `app/static/js/pallet_weight_autosave.mjs`
- Create: `app/static/js/pallet_weight_terminal_sync_core.mjs`
- Modify: `app/templates/base.html`
- Modify: `app/templates/terminal.html`
- Modify: `app/templates/admin_card_detail.html`
- Modify: `app/static/js/roll_change_countdown.mjs`
- Modify: `app/static/js/roll_change_countdown_core.mjs`
- Test: `tests/js/pallet_weight_autosave_core.test.mjs`
- Test: `tests/js/pallet_weight_terminal_sync_core.test.mjs`
- Test: `tests/js/roll_change_countdown_core.test.mjs`
- Test: `tests/test_terminal_pallet_summary.py`
- Test: `tests/test_admin_card_detail_redesign.py`

**Interfaces:**
- Consumes: the server summary and JSON contracts from Tasks 2–4
- Produces DOM hooks: `data-pallet-summary-overlay`, `data-pallet-summary-dialog`, `data-pallet-summary-open`, `data-pallet-summary-close="icon|footer"`, `data-pallet-weight-form`, `data-pallet-weight-input`, `data-pallet-weight-error`, `data-pallet-gross-with`, `data-pallet-weight-total`, `data-pallet-gross-with-total`, `data-pallet-weight-status`, `data-pallet-weight-reload`
- Produces JS: `parsePalletWeightDraft(raw: string) -> {kind: "blank" | "valid" | "invalid", tenths?: number, reason?: string}`
- Produces JS: `createSerializedTaskQueue() -> {enqueue(task), whenIdle(), pendingCount()}`
- Produces JS: `classifyPalletWeightSnapshotReconciliation(before, after, {cardId, expectedVersion}) -> {kind: "accept-local" | "stale", reason: string}`
- Produces JS controller behavior: serialize dirty field saves, use the newest returned version at dequeue time, apply authoritative row/total responses without modal movement or reload, and coordinate save-aware dismissal

- [ ] **Step 1: Write failing JavaScript unit tests**

Mirror backend acceptance exactly for blank, dot/comma, integer normalization,
one/two decimals with half-up rounding, zero, negative, over-100, text,
exponent, and more than two decimals. Test field dirty
state, one-pending-save protection, queue continuation after a rejected task,
strict execution order, and `whenIdle()` resolution only after the queue has
settled. Response-to-DOM behavior remains an integration concern because the
server, not a client calculation, supplies every derived value.

Exercise the controller state machine in browser verification: the same field
cannot enqueue twice while queued/active; HTTP 422 permits the next queued
field; stale/network/malformed response trips the fatal lock and no later task
issues a POST; Enter does not lose focus merely because its field becomes
read-only; and dismissal waits for the exact generation containing the focused
dirty draft.

In `pallet_weight_terminal_sync_core.test.mjs`, construct literal terminal
snapshots and assert `accept-local` only when all differences are the selected
card's exact expected version and its accompanying `updated_at` in every place
that card occurs. Assert `stale` for a changed shift signature, active/waiting
membership or order, any other-card field/version change, a selected-card
lifecycle/queue change, a missing selected card, or a selected version that is
older or newer than the exact returned version. Ignore only
`server_now_utc` and derived signature strings.

Run:

```bash
node --test tests/js/pallet_weight_autosave_core.test.mjs
node --test tests/js/pallet_weight_terminal_sync_core.test.mjs
```

Expected: module-not-found failure.

- [ ] **Step 2: Write failing server-rendered markup tests**

Assert the shared modal renders:

- exact title `Обобщение по палети` and `Клиент (№ поръчка)` context;
- the accepted clipboard/list icon asset, accessible upper-right close control,
  and footer `Затвори`, both routed through the same dismissal behavior;
- exactly six headings in approved order;
- `-` for both missing dependent values;
- only one footer action, `Затвори`;
- a hidden status-area `Презареди` recovery link that becomes reachable only
  after stale or commit-ambiguous failure and does not become a second ordinary
  footer action;
- no `Добави тегла`, `Отказ`, or `Запази` action;
- one always-visible text/inputmode-decimal input for each numbered row;
- no input for `Без палет`;
- no roll-number, count, gross, or net editing controls; and
- a read-only `Без палет` row plus explanatory copy when gross rolls exist but
  no numbered pallet exists, and the existing empty state when no gross rolls
  exist.

On admin detail, add a `Палети` trigger in the rolls-section header only for
`completed` and `archived` cards. A cancelable before-open hook must block the
modal and tell the manager to save or discard the outer admin form first when
`#admin-card-save-form` is dirty; otherwise the displayed pallet set could
disagree with unsaved roll assignments.

Place the admin overlay after `</main>` so it cannot be inside either the outer
form or an element made inert while the dialog is open. Because the existing
admin page has no discard button, the dirty-state message must name the actions
that actually exist: save the form or reload the page to discard its changes.

- [ ] **Step 3: Implement the pure client core**

Keep the client parser aligned with backend validation so obvious invalid input
can be rejected immediately. Submitted raw strings remain authoritative to the
backend; displayed derived values are replaced only with authoritative values
from a successful response. Do not use binary floating point for any client
fallback calculation.

Export only parser and queue primitives from the core module. Do not add client
gross or total arithmetic:

```javascript
export function parsePalletWeightDraft(rawValue) {
  const trimmed = String(rawValue ?? "").trim();
  if (!trimmed) return { kind: "blank" };
  if (!/^[0-9]+(?:[.,][0-9])?$/.test(trimmed)) {
    return { kind: "invalid", reason: "format" };
  }
  const [whole, fraction = "0"] = trimmed.replace(",", ".").split(".");
  const significantWhole = whole.replace(/^0+/, "") || "0";
  if (significantWhole.length > 3) {
    return { kind: "invalid", reason: "maximum" };
  }
  const wholeNumber = Number(significantWhole);
  const tenths = wholeNumber * 10 + Number(fraction);
  if (tenths < 1) return { kind: "invalid", reason: "minimum" };
  if (tenths > 1000) return { kind: "invalid", reason: "maximum" };
  return { kind: "valid", tenths };
}

export function createSerializedTaskQueue() {
  let tail = Promise.resolve();
  let pending = 0;
  return {
    enqueue(task) {
      pending += 1;
      const current = tail.catch(() => undefined).then(task);
      tail = current.finally(() => { pending -= 1; });
      return current;
    },
    whenIdle() {
      return tail.catch(() => undefined);
    },
    pendingCount() {
      return pending;
    },
  };
}
```

Implement `classifyPalletWeightSnapshotReconciliation()` in the separate
terminal-sync core. Validate the required snapshot arrays/selected-card shape,
compare ordered cards by identity and every field, and allow `version` plus
`updated_at` to differ only for `cardId` when the final version equals
`expectedVersion`. Return `stale` for malformed snapshots rather than guessing.

- [ ] **Step 4: Implement the shared modal markup and styling**

Match the approved prototype: accepted finish-review visual language, modest
top close area, pale-blue icon tile, readable six-column table, sticky header
and total, vertically scrollable body, and full-width footer with actions
grouped on the right. The first column is narrow and the remaining five are
equal width. Use `Segoe UI`, Arial, sans-serif consistently and
tabular numerals for numeric cells.

Use one semantic table and a six-entry `<colgroup>` so header, body, inputs, and
totals share boundaries even when the body scrolls. Give the first column a
fixed narrow share and each other column the same calculated share. Keep one
font stack, line-height, vertical centering, and numeric alignment across all
cells; the pallet identifier is the only left-aligned body/total value. Cap the
dialog/table height so the footer remains visible and allow vertical—not
horizontal—scrolling at the three acceptance viewports.

Add a `{% block head %}` to `base.html` and load the shared stylesheet on admin
detail. Load it directly from `terminal.html` because that template is
standalone. Reuse the accepted
`/static/images/terminal-ui/finish-review-clipboard-list.svg` and
`finish-review-close.svg`; do not add an unrelated icon style.

The shared partial receives one complete view model and action-URL prefix:

```jinja2
{% include "_pallet_summary_modal.html" %}
```

```html
<form method="post"
      action="{{ pallet_modal.action_url }}/{{ row.pallet_number }}"
      data-pallet-weight-form="{{ row.pallet_number }}">
  <input type="hidden" name="loaded_version" value="{{ pallet_modal.loaded_version }}">
  <input type="text" inputmode="decimal"
         name="pallet_weight"
         value="{{ row.pallet_weight_input }}"
         aria-label="Тегло за палет №{{ row.pallet_number }}, кг"
         data-pallet-weight-input="{{ row.pallet_number }}">
</form>
```

Render each pallet-weight form outside any unrelated parent form. In
`admin_card_detail.html`, the existing `#admin-card-save-form` wraps the roll
ledger, so the summary trigger may be a `type="button"` inside that section but
the modal partial and its per-row forms must be included only after the outer
form closes. Never produce nested HTML forms.

- [ ] **Step 5: Implement immediate serialized field saving**

Every changed field saves on Enter or blur. Model each input explicitly as
`clean -> dirty -> queued -> active -> clean|failed`, with a controller-wide
fatal lock for stale or commit-ambiguous failures. Freeze the exact raw value at
enqueue time, treat queued and active as duplicate-protected, and use
`readOnly` plus `aria-busy` rather than disabling a focused Enter-submitted
field. Save only that pallet. The modal owns one current
`cardVersion`; when a task reaches the head of the serialized queue, it builds
its `FormData` using that current value—not the version that existed when blur
first fired. After success, update `cardVersion` and every hidden
`loaded_version` field before the next queued task starts. Moving to another
field must not move the table, close the modal, or discard the new focus. A
successful response normalizes the input (`20` → `20.0`) and replaces the
affected row, totals, and weight-state displays with server values. Blank
deletes the saved value.

Track the last successfully saved string per input and suppress unchanged blur
or repeated Enter submissions. A failed request must not advance the shared
version or replace any derived display. Ordinary HTTP 422 field validation
writes nothing, so later queued fields may continue against the unchanged
version. A stale conflict, network failure, or malformed response makes the
server commit state uncertain: lock further requests, preserve all typed
values, skip every not-yet-started queued request, and require reload rather
than blindly sending the remaining queue.

After success, update `loaded_version` only in forms whose action targets the
same terminal/admin card ID; do not rewrite shift/configuration tokens or forms
for another card. Dispatch a `pallet-summary:card-version-updated` event with
the card ID and old/new versions so other page controllers can reconcile their
state. The roll-change countdown controller and same-card DOM version hooks
must adopt that exact local version without resetting the schedule; no other
lifecycle field may change. Also dispatch autosave-started and queue-idle
events.

When the first task enters an empty queue, the terminal monitor retains the
complete current structured snapshot as its pre-queue baseline and defers
normal polling comparisons. At queue idle, fetch one fresh snapshot and pass
the baseline, response, selected card ID, and queue's final returned version to
`classifyPalletWeightSnapshotReconciliation()`. Adopt the new structured
snapshot/signature only for `accept-local`. For `stale`, preserve the existing
baseline, show the normal reload warning, and dispatch the normal stale event.
Selected-version equality alone is never sufficient. This prevents the local
save from producing a false alert without hiding a concurrent queue, other-card,
selected-card lifecycle, or shift change.

Invalid client or server input sets `aria-invalid`, shows the single linked
footer status message, and leaves the raw text available for correction while
the modal remains open. A network or malformed-JSON
failure does the same, never claims success, and invokes the reload-required
treatment because commit status is unknown. A stale response invokes the same
lock and must not be retried against a guessed version. In a fatal lock, reveal
and focus the in-modal `Презареди` link because the background refresh control
is inert; no further pallet POST may be issued.

The upper close control, backdrop, Escape, and footer `Затвори` have no
independent save semantics and all call one `prepareDismiss()` path. It
synchronously freezes edits, validates and enqueues the currently focused valid
dirty draft even when Escape/backdrop did not naturally blur it, captures that
queue generation, and closes automatically only after that generation succeeds;
do not require a second click. An explicit dismissal discards an invalid
unsaved draft and restores the last authoritative value. A stale, network, or
malformed response stays clearly marked and reload-protected but does not trap
the operator inside the modal. With no dirty or pending work, close immediately
without a request.

Keep open/close/background isolation in the existing terminal coordinator.
The shared controller must not create a second modal stack owner. On admin,
provide the same Escape, close, background, focus-trap, and focus-return
behavior without affecting other pages. Use a small explicit bridge rather than
duplicating save logic: the autosave controller handles a
`pallet-summary:prepare-dismiss` event by placing a `Promise<boolean>` in the
event detail; the terminal/admin modal host awaits it and performs the actual
DOM close only when it resolves `true`. Define the detail as
`{decision: null}`; exactly one autosave controller must replace `decision`
with the promise synchronously. A missing or duplicate responder fails closed.

For polling-detected `terminal:card-stale`, close a clean pallet modal and use
the existing outer reload treatment. If any field is dirty, queued, active, or
failed, keep the modal open, freeze it under the controller-wide lock, preserve
the typed values, and reveal/focus its reload action. Never discard an
unconfirmed draft during stale takeover.

- [ ] **Step 6: Run JS and rendering tests**

Run:

```bash
node --test tests/js/pallet_weight_autosave_core.test.mjs
node --test tests/js/pallet_weight_terminal_sync_core.test.mjs
node --test tests/js/roll_change_countdown_core.test.mjs
source .venv/bin/activate
python -m pytest tests/test_terminal_pallet_summary.py tests/test_admin_card_detail_redesign.py -vv
git diff --check
```

Expected: all pass.

---

### Task 6: Enforce Completeness In Finish And Extend The Review Table

**Files:**
- Modify: `app/db.py`
- Modify: `app/main.py`
- Modify: `app/templates/terminal.html`
- Create: `app/static/js/finish_review_pallet_state.mjs`
- Create: `tests/js/finish_review_pallet_state.test.mjs`
- Modify: `app/static/js/timing_interval_editor.mjs`
- Modify: `app/static/js/waiting_finish_review.mjs`
- Modify: `app/static/js/waiting_finish_review_core.mjs`
- Test: `tests/test_rewinding_workflow.py`
- Test: `tests/test_terminal_pallet_summary.py`
- Test: `tests/test_terminal_timing_correction.py`
- Test: `tests/test_order_finish_review_ui_script_safety.py`

**Interfaces:**
- Produces: `validate_final_pallet_weight_completeness(summary: Mapping[str, Any]) -> RuleResult`
- Produces: `pallet_weight_completion_messages(summary: Mapping[str, Any]) -> tuple[str, ...]`
- Produces: `FinishReviewSnapshot(card: dict[str, Any], pallet_summary: dict[str, Any], timing_preview: TimingLedgerPreview | None, reviewed_at: str, mode: str)`
- Produces: `FinishReviewOutcome(result: RuleResult, snapshot: FinishReviewSnapshot | None, issues: tuple[TimingValidationIssue, ...])`
- Produces: `preview_terminal_finish_review_snapshot(card_id: int, loaded_version: int, *, timing_draft: list[TimingDraftRow] | None = None, reviewed_at: str | None = None, require_active_shift: bool = True) -> FinishReviewOutcome`
- Produces JSON field: `finish_review` containing `mode`, `card_version`,
  `pallet_summary`, `messages`, `warning_message`, `can_confirm`, and current
  timing display; active modes additionally retain `review_token` and timing
  draft/preview data
- Produces JS: `validateFinishReviewPalletState(payload) -> object | null` and
  `applyFinishReviewPalletState(dialog, payload) -> boolean`
- Consumes: `load_card_pallet_summary()` and its completeness fields
- Preserves: existing timing-review tokens and `finish_card_with_timing_ledger()` atomic transaction

- [ ] **Step 1: Write failing backend lifecycle tests**

Cover these exact decisions:

| Target transition | No weights | Valid partial | Complete | Invalid/orphaned |
| --- | --- | --- | --- | --- |
| running/paused → completed | allow | block | allow | block |
| running/paused → awaiting_rewinding | allow | allow with warning | allow | block |
| awaiting_rewinding → completed | allow | block | allow | block |

For partial state, separately test missing weight numbers, gross rolls in
`Без палет`, and both together. Assert messages identify missing pallet numbers
in numeric order and the unassigned roll count. Create an orphaned weight by
direct SQL and call both `finish_card()` and `finish_card_with_timing_ledger()`
directly for the applicable active/waiting modes. Assert status, timing,
version, and weights remain unchanged. HTTP tests remain additional protection;
they are not the proof of the database invariant.

- [ ] **Step 2: Write failing finish-review rendering tests**

Assert the table has the approved six headings and no five-column placeholder,
uses non-equal column classes, displays `-` correctly, and preserves sticky
header/total hooks. Assert `can_confirm` is false for a final partial state and
true for partial entry into waiting. The latter must expose a yellow warning,
not a red blocker.

Add route/JavaScript tests proving every open obtains a new authoritative
payload. Render a page, save or clear a weight without reloading, and then open
normal completion, entry into waiting, and waiting finalization. Assert the
dialog replaces all rows, totals, messages, warning, `card_version`, and
`can_confirm` before becoming visible. Waiting refresh must return no timing
token and must not change timing data.

- [ ] **Step 3: Run focused tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_rewinding_workflow.py tests/test_terminal_pallet_summary.py tests/test_order_finish_review_ui_script_safety.py -k "pallet or finish_review" -vv
```

- [ ] **Step 4: Separate structural integrity from final completeness**

At the start of `_finish_card_with_connection()`, after timing/status checks but
before choosing the lifecycle branch, call `load_card_pallet_summary()` once
inside the existing `BEGIN IMMEDIATE` transaction. Catch only
`PalletSummaryDataError` and return a blocking repair/reload message. This
structural check applies to normal completion, entry into waiting, and waiting
finalization.

For the two final transitions, pass the already-built summary into the explicit
completeness rule:

```python
def validate_final_pallet_weight_completeness(
    summary: Mapping[str, Any],
) -> RuleResult:
    if summary["weight_state"] in {"none", "complete"}:
        return RuleResult(True)
    return RuleResult(False, pallet_weight_completion_messages(summary))
```

Keep the existing roll/tare/net/gap validation in
`validate_card_ready_to_finish()` and pass or reuse the transaction's summary
instead of opening another connection. The `needs_rewinding` branch skips only
final completeness; it never skips structural summary construction. Use the
same message builder in review and print readiness. Do not rely on browser
`can_confirm` or the pre-route `validate_terminal_pallet_summary()` check.

- [ ] **Step 5: Build one version-consistent Finish Review snapshot**

Refactor the existing initial and edited timing-preview preparation behind
`preview_terminal_finish_review_snapshot()`. Under one database transaction it
must validate the submitted card version and active shift, derive the lifecycle
mode, load the complete pallet summary, and build the active timing preview or
the waiting card's stored read-only timing state. A defined structural summary
error returns a non-success outcome; unrelated exceptions are not relabeled as
production-data errors.

Use explicit immutable outcomes rather than an untyped tuple:

```python
@dataclass(frozen=True)
class FinishReviewSnapshot:
    card: dict[str, Any]
    pallet_summary: dict[str, Any]
    timing_preview: TimingLedgerPreview | None
    reviewed_at: str
    mode: str  # complete | enter_rewinding | finalize_rewinding


@dataclass(frozen=True)
class FinishReviewOutcome:
    result: RuleResult
    snapshot: FinishReviewSnapshot | None = None
    issues: tuple[TimingValidationIssue, ...] = ()
```

For active `running`/`paused` cards, retain the reviewed timestamp, timing
draft, and signed recovery-mode token. For `awaiting_rewinding`, return mode
`finalize_rewinding`, `timing_preview=None`, the stored timing values, and no
token. The read-only path must not write, open a timing segment, alter
`finished_at`, or make timing editable.

Adapt the result once in `app/main.py` into the common `finish_review` JSON
object. For `complete` and `finalize_rewinding`, partial data supplies blockers
and `can_confirm=false`. For `enter_rewinding`, the same facts are a yellow
warning and confirmation remains enabled. Keep the mixed-pallet warning
nonblocking only when `weight_state == "none"`.

- [ ] **Step 6: Refresh and replace the complete review before opening**

Make `POST /terminal/cards/{card_id}/finish-review` the fresh-open boundary for
all three modes. The active timing controller and waiting-review controller
both submit their current `loaded_version`, await the response, validate the
mode/version/payload, and call the shared `applyFinishReviewPalletState()` before
showing the dialog. The shared function replaces all six-column rows and totals,
blocking messages, warning text, and confirmation state as one operation; it
does not calculate weights.

The waiting trigger no longer opens its page-load model directly. It calls the
same refresh route, requires mode `finalize_rewinding`, and receives no timing
token. Timing-editor previews made after the active review opens retain or
refresh the same-version pallet review state; any intervening write changes the
card version and follows the existing stale lock instead of mixing versions.
Leave the accepted order/time cards, edit availability, close/cancel behavior,
and blue completion button unchanged.

- [ ] **Step 7: Run finish and timing regression tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_rewinding_workflow.py tests/test_terminal_timing_correction.py tests/test_order_finish_review_ui_script_safety.py tests/test_terminal_pallet_summary.py -vv
node --test tests/js/finish_review_pallet_state.test.mjs
git diff --check
```

Expected: all pass, including cancelled review writes-nothing and waiting
finalization timing-neutral tests.

---

### Task 7: Carry Physical Pallet Weights Into Operational-Card Printing

**Files:**
- Modify: `app/printing.py`
- Modify: `app/templates/print_card.html`
- Modify: `app/static/css/print.css`
- Modify: `scripts/create_print_template_fixture.py`
- Modify: `scripts/render_print_template.mjs`
- Test: `tests/test_print_output.py`
- Test: `tests/test_print_template_fixture_script.py`

**Interfaces:**
- Consumes: `build_pallet_summary()` from `app/pallet_summary.py`
- Produces print layout: `{"page2_table": {"rows": list[dict], "total": dict} | None, "overflow_tables": list[{"rows": list[dict], "total": dict | None}]}`
- Interprets `PALLET_BACK_TABLE_CAPACITY` and
  `PALLET_OVERFLOW_PAGE_CAPACITY` as total printable body-row slots, including
  the one `Общо` row on the page where it appears
- Keeps the current values `8` and `48` only if browser/PDF measurement proves
  the six-column table remains readable with the total included

- [ ] **Step 1: Write failing print calculation and readiness tests**

Assert printed row dictionaries include all six approved display values. Cover
no weights, complete weights, mixed assignment, all-unassigned omission, and
corrected values on reprint. A partial or orphaned weight set must produce a
print-readiness message and no `print_data`.

Assert the print total is derived from the complete shared summary and appears
exactly once. For no weights, its pallet-weight and gross-with-pallet cells are
`-`; for complete weights they contain exact one-decimal totals. Partial data
does not reach layout generation because readiness is blocked.

- [ ] **Step 2: Write failing layout and template tests**

Replace middle/right-half expectations with one page-2 table whose capacity
includes the total:

```python
assert split_pallet_summary(rows[:7], total, back_table_capacity=8, overflow_page_capacity=48) == {
    "page2_table": {"rows": rows[:7], "total": total},
    "overflow_tables": [],
}
assert split_pallet_summary(rows[:8], total, back_table_capacity=8, overflow_page_capacity=48) == {
    "page2_table": None,
    "overflow_tables": [{"rows": rows[:8], "total": total}],
}
```

With a deliberately small overflow capacity, assert that a total which would
otherwise be alone causes the last data row to move with it. Assert every data
row appears once, in order, and only the final table contains `total`.

Assert page 2 and overflow templates have exactly six headers in approved order,
never render the former generic `Бруто, кг`, and never print `0.0` for absent
physical weight.

- [ ] **Step 3: Run focused print tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_print_output.py -k pallet -vv
```

- [ ] **Step 4: Reuse the shared summary and enforce print readiness**

Remove the independent print pallet arithmetic. Adapt the shared exact result
to print behavior: omit the table for all-unassigned cards, append `Без палет`
last only for mixed cards, and block partial/orphaned stored weight data.

Replace `middle_rows`/`right_rows` with `page2_table`. Preserve the rule that if
all data rows plus the total do not fit page 2, none are split there and the
complete list begins on an overflow page.

Catch `PalletSummaryDataError` at `build_print_readiness()` and convert it into
an actionable print blocker, alongside the existing invalid-number handling;
do not allow inconsistent stored summary data to become a server error.

The splitter remains deterministic. Capacities must be at least two because a
final page needs space for one pallet row and its total:

```python
def split_pallet_summary(
    rows, total, *, back_table_capacity, overflow_page_capacity
):
    if back_table_capacity < 2 or overflow_page_capacity < 2:
        raise ValueError("Pallet summary capacities must be at least two.")
    if not rows:
        return {"page2_table": None, "overflow_tables": []}
    if len(rows) + 1 <= back_table_capacity:
        return {
            "page2_table": {"rows": list(rows), "total": total},
            "overflow_tables": [],
        }

    items = [("row", row) for row in rows] + [("total", total)]
    pages = [
        items[index:index + overflow_page_capacity]
        for index in range(0, len(items), overflow_page_capacity)
    ]
    if len(pages) > 1 and pages[-1] == [("total", total)]:
        pages[-1].insert(0, pages[-2].pop())
    return {
        "page2_table": None,
        "overflow_tables": [
            {
                "rows": [value for kind, value in page if kind == "row"],
                "total": next(
                    (value for kind, value in page if kind == "total"), None
                ),
            }
            for page in pages
        ],
    }
```

- [ ] **Step 5: Render one readable six-column table across the two pallet columns**

Keep the production summary in the left 63 mm grid column. Make the pallet
table span grid columns 2 through 4 (the combined 109 mm area), use explicit
narrow identifier/count widths and wider weight widths, allow heading wrapping,
and keep every body row whole. Render `Общо` as a visually distinct final table
row on page 2 or only the final overflow page. Apply the same ordered columns
and numeric alignment on every page.

- [ ] **Step 6: Run all print tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_print_output.py tests/test_print_template_fixture_script.py -vv
git diff --check
```

Expected: all pass before visual PDF measurement.

- [ ] **Step 7: Extend the guarded print fixture and renderer**

Create all deterministic scenarios in one guarded database: numbered pallets
with no physical weights, the largest table that fits page 2 including `Общо`,
the first overflow case, a full overflow boundary, and the case that would
orphan `Общо` without row rebalancing. Add `--output` for a guarded JSON manifest
containing each card ID, scenario name, expected page count, and expected total
placement. Keep all databases and output under guarded `.test-runtime/` and
`artifacts/` paths.

Give `render_print_template.mjs` `--fixture-json`; loop over the manifest,
enforce every expected page count/total placement, capture every PDF page rather
than only front/back, and fail on missing or extra pages. Contract tests must
reject runtime/production paths, symlinks, and hard links using the existing
guards.

---

### Task 8: Extend Guarded Browser And Database Verification

**Files:**
- Modify: `scripts/create_terminal_pallet_summary_fixture.py`
- Modify: `scripts/verify_terminal_pallet_summary_ui.mjs`
- Modify: `scripts/audit_terminal_pallet_summary_db.py`
- Modify: `tests/test_terminal_pallet_summary_scripts.py`
- Test: `tests/test_terminal_pallet_summary_scripts.py`

**Interfaces:**
- Produces fixture scenarios: `empty`, `all_unassigned`, `no_weights`, `partial_weights`, `complete_weights`, `mixed_unassigned`, `awaiting_partial`, `completed_complete`, `archived_complete`, `many_pallets`
- Produces screenshots under: `artifacts/ui-checks/physical-pallet-weight/`
- Produces a JSON/database audit that permits only the expected card-version and `card_pallet_weights` mutations

- [ ] **Step 1: Write failing fixture/verifier contract tests**

Assert every scenario exists in one guarded task database, has internally
consistent gross/core/net values, and declares expected weights, six-column
rows, totals, editable state, and finish eligibility. The verifier must restore
or recreate the canonical task database before each mutation group and each
viewport so scenarios cannot contaminate one another. Reject real runtime
paths, symlinks, hard links, and paths outside `.test-runtime/` or `artifacts/`
using the existing guard patterns.

- [ ] **Step 2: Extend the fixture and audit tools**

Create only deterministic non-customer sample data. Record pre/post hashes of
all existing cards, rolls, timing, recipe, and shift fields. Allow the expected
new table rows and one parent version/update change per successful save; report
any unrelated mutation as failure.

- [ ] **Step 3: Extend the browser verifier**

Against the live temporary FastAPI app, verify:

- upper-close/footer-close/Escape/backdrop/background isolation/focus return;
- blank-by-default, always-visible inputs with no mode-switch or save button;
- Enter and blur each persist the changed pallet independently while the modal
  stays open and the table does not move;
- moving directly to another input preserves focus while queued saves use the
  latest returned card version;
- successful rapid saves refresh card-scoped version tokens and reconcile the
  terminal snapshot once at queue idle without creating a false stale alert;
- a genuinely newer selected-card version, any other active/waiting-card
  change, queue reorder/membership change, or shift change still raises the
  normal stale-data warning and is never adopted as part of the local save;
- integer, comma, and two-decimal entry normalize to one decimal after save;
- invalid and over-100 field feedback;
- duplicate-submit prevention and serialized rapid saves;
- same-field queued/active protection, 422 continuation, and zero later POSTs
  after the fatal stale/network/malformed-response fuse;
- independent single-value clears, including clearing the last remaining
  weight back to the valid no-weights state;
- close/backdrop/Escape during a dirty blur save: automatic close after success,
  invalid draft restoration on explicit dismissal, and explicit dismissal from
  reload-protected network or stale failure states;
- a keyboard-reachable in-modal `Презареди` recovery action while the
  background remains inert after stale or commit-ambiguous failure;
- `Без палет` has no input;
- sticky heading/total and footer while scrolling;
- stale-card conflict and inactive/stale-shift handling;
- non-stacking with terminal drawers and finish/timing overlays;
- admin completed and archived correction;
- admin refuses to open the summary over unsaved outer-form changes, then opens
  normally after those changes are saved or discarded;
- hard-blocked normal/final waiting completion versus warning-only waiting entry;
- after a save or clear, opening normal completion, waiting entry, and waiting
  finalization without reloading replaces the complete six-column review,
  totals, warnings/blockers, and confirmation state from the server response;
- no unexpected console, page, response, or request errors; and
- no horizontal overflow or clipped actions at `1440x900`, `1366x768`, and
  `1093x614`.

- [ ] **Step 4: Run script safety tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_terminal_pallet_summary_scripts.py -vv
```

Expected: all pass.

- [ ] **Step 5: Run the guarded live browser workflow**

Create the guarded fixture first:

```bash
source .venv/bin/activate
python scripts/create_terminal_pallet_summary_fixture.py --db-path .test-runtime/physical-pallet-weight/extrusion.sqlite3 --output .test-runtime/physical-pallet-weight/fixture.json
```

Start FastAPI in a separate terminal with:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/physical-pallet-weight/extrusion.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the repo-local verifier against that process:

```bash
BASE_URL=http://127.0.0.1:8000 FIXTURE_JSON=.test-runtime/physical-pallet-weight/fixture.json ARTIFACT_DIR=artifacts/ui-checks/physical-pallet-weight node scripts/verify_terminal_pallet_summary_ui.mjs
```

Save evidence only to `artifacts/ui-checks/physical-pallet-weight/` and record
these exact final commands in the implementation note.

- [ ] **Step 6: Render and inspect representative print PDFs**

Create one guarded print database and manifest containing no-weight,
complete-page-2-boundary, first-overflow, full-overflow-boundary, and
total-rebalancing cards:

```bash
source .venv/bin/activate
python scripts/create_print_template_fixture.py --db-path .test-runtime/physical-pallet-weight/print.sqlite3 --output .test-runtime/physical-pallet-weight/print-fixture.json
```

Start FastAPI in a separate terminal:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/physical-pallet-weight/print.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Render every declared card and require its manifest page count:

```bash
BASE_URL=http://127.0.0.1:8010 node scripts/render_print_template.mjs --fixture-json .test-runtime/physical-pallet-weight/print-fixture.json --output-dir artifacts/ui-checks/physical-pallet-weight/print
```

Inspect every captured page at 100% scale. Verify the one-time `Общо` row,
page-2 and first-overflow behavior, no total-only page, repeated six-column
headings, one-decimal formatting, and absence of clipping. Treat the capacity
constants as body-row slots including the total. If the current values are not
readable, reduce them to the highest measured whole-row capacities and update
the constants, paginator tests, manifest page counts, and durable print note
together; do not shrink below readable type solely to preserve row count. A
physical-printer rehearsal remains a required pre-production GO check, not a
source-acceptance blocker.

---

### Task 9: Final Review, Documentation, And Backlog Closure

**Files:**
- Create: `docs/implementation-notes/physical-pallet-weight.md`
- Modify after user acceptance: `README.md`
- Modify after user acceptance: `AGENTS.md`
- Modify after user acceptance: `v2-files/PLAN.md`
- Modify after user acceptance: `docs/implementation-notes/print-output-reference.md`
- Review: every file changed in Tasks 0–8

**Interfaces:**
- Produces: durable implementation/migration/deployment record
- Produces: an evidence-backed source-complete handoff, followed by coordinated
  authoritative status updates only after user acceptance
- Preserves: Task 20 as the next unimplemented workstream

- [ ] **Step 1: Run syntax/import and focused suites**

Run:

```bash
source .venv/bin/activate
python -m compileall -q app tests
python -m pytest tests/test_migrations.py tests/test_physical_pallet_weights.py tests/test_terminal_pallet_summary.py tests/test_roll_entry.py tests/test_admin_card_detail_redesign.py tests/test_rewinding_workflow.py tests/test_terminal_timing_correction.py tests/test_order_finish_review_ui_script_safety.py tests/test_print_output.py tests/test_print_template_fixture_script.py tests/test_terminal_pallet_summary_scripts.py -vv
node --test tests/js/*.test.mjs
git diff --check
```

- [ ] **Step 2: Run the complete automated suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
node --test tests/js/*.test.mjs
git diff --check
```

Expected: all tests pass with no mutation of real runtime/production data.

- [ ] **Step 3: Conduct the bounded adversarial code review**

Review only this feature's diff and directly affected contracts for:

- database constraints and migration atomicity;
- decimal/input parser parity between Python and JavaScript;
- transactional cleanup coverage across every roll mutation path;
- stale-write and duplicate-submit races;
- structural snapshot reconciliation that rejects unrelated card, queue, and
  shift changes;
- final completion and print bypasses;
- freshness and version consistency of every Finish Review open path;
- none/partial/complete state consistency across terminal, admin, finish review,
  and print;
- accessibility and focus behavior;
- table alignment, overflow, short-height behavior, and consistent typography;
- exactly-once print totals, total-aware page capacity, and prevention of a
  total-only overflow page;
- accidental changes to timing, rewinding, roll net, import preservation, or
  unrelated application behavior; and
- dead compatibility fields left from the former `0.0` placeholder.

Fix every confirmed issue with a failing regression test first, then rerun its
focused suite.

- [ ] **Step 4: Record the durable implementation note**

Document exact final schema, formulas, state/validation rules, routes, UI
surfaces, Finish Review refresh and snapshot-reconciliation contracts, print
layout/total pagination, cleanup semantics, verification commands/results, and
the migration assessment required by the playbook. State clearly that M007 has
not been deployed until a production maintenance window is separately approved.

- [ ] **Step 5: Present the source-complete feature and stop for acceptance**

Report the implemented functionality, exact automated/browser/print evidence,
migration and deployment status, and a short severity-calibrated summary of the
bounded adversarial review. Preserve the UI evidence and do not change the
authoritative accepted-task status yet. Stop and wait for the user to review
and explicitly accept or request changes.

- [ ] **Step 6: Update authoritative status after explicit acceptance**

After acceptance, update `README.md`, `AGENTS.md`, and `v2-files/PLAN.md`
together: document the accepted behavior, remove the obsolete physical-pallet
placeholder/unimplemented instructions, mark Task 23 complete, and preserve
Task 20 as the next workstream. Update
`docs/implementation-notes/print-output-reference.md` from the former
two-block/four-column contract to the measured six-column table, one-time
`Общо` placement, final capacities, missing-value/readiness rules, and PDF plus
pre-production physical-printer obligations; cross-link the new implementation
note. Archive any temporary Task 23 tracker if one was created. Do not modify
the separate Task 20 requirements file.

- [ ] **Step 7: Remove disposable evidence after acceptance**

Delete only task-created files under
`artifacts/ui-checks/physical-pallet-weight/` and task-owned temporary runtime
directories after their results have been reviewed. Preserve source, tests,
fixtures required by the suite, databases, backups, and unrelated untracked
files.

- [ ] **Step 8: Present the clean checkpoint for an explicit Git decision**

Run `git status --short` and `git diff --check`, report the retained source and
documentation changes plus the fact that production M007 remains undeployed,
and ask for the next explicit checkpoint action. Do not stage, commit, push, or
deploy until the user authorizes that specific action.
