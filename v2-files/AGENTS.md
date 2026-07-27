# Database Migration System Instructions

This file is the complete, standalone agent procedure for maintaining database
migrations during the July 25-26, 2026 extrusion-terminal update. It also
contains the migration register and assessment history. The user is not
expected to operate or remember the technical process.

## User Trigger

Treat the exact phrase **“maintain the database migration system”** as a user
command. Minor grammatical variations such as **“do whatever is needed to
maintain the database migration system”** mean the same thing.

After this command, complete the entire applicable workflow in this file:

1. inspect the finished feature and actual working-tree diff;
2. classify its migration impact;
3. implement and test a schema-only or deterministic migration when its rules
   are proven;
4. refuse to guess when real production values must be profiled;
5. update the migration register and assessment log in this file; and
6. give the user the required plain-language recommendation.

This command authorizes local migration code, tests, and updates to this file.
It does not authorize mutation of the runtime or production database,
customer-data extraction, deployment, staging, or committing.

## What The Migration System Is

`app/migrations.py` contains an ordered tuple of `Migration` objects:

```python
@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]
```

`app.db.init_db()` creates the normal tables, starts a caller-owned transaction,
and calls:

```python
apply_pending_migrations(connection) -> tuple[int, ...]
```

The runner creates `schema_migrations(version, name, applied_at)`, validates the
registry and recorded history, then applies only unrecorded versions in order.
Each invocation uses a savepoint. Schema changes, data changes, and the version
record roll back together on failure. Re-running initialization skips recorded
versions.

The runner rejects:

- non-positive, duplicate, or out-of-order registry versions;
- unknown versions already recorded by the database;
- recorded names that do not match code; and
- recorded histories that are not a prefix of the code registry.

This mechanism upgrades an existing database. It does not replace SQLite-safe
backups, snapshot profiling, release rehearsal, or rollback preparation.

## Required Reading For A Migration Assessment

When migration impact is asked about or potentially present, read:

1. `app/migrations.py`;
2. `app/db.py`, especially schema definitions and `init_db()` ordering;
3. `tests/test_migrations.py`; and
4. the task's importer, database queries, models, routes, templates, scripts, and
   tests that read or write the affected data.

Inspect the actual working-tree diff. Do not base a recommendation only on the
user's description or a filename.

## Migration Decision Procedure

For every completed feature, ask these questions in order.

### 1. Did persistent structure change?

Migration required when the change adds, removes, renames, or changes:

- SQLite tables or columns;
- indexes, unique rules, checks, defaults, or foreign keys;
- persisted relationships or ownership;
- the type/shape expected from an existing stored value.

### 2. Did the meaning of existing data change?

Migration or production profiling may be required even without obvious DDL when:

- one field is split into several fields or several fields are merged;
- a field is renamed but existing rows must remain readable;
- a status, unit, route, identifier, default, or null value gets a new meaning;
- new code requires a value that old production rows do not contain;
- importer changes make old stored source values incompatible with current code;
- old data must be normalized, recomputed, reassigned, or backfilled.

### 3. Is the change display-only?

Normally no migration is required for:

- HTML/CSS/layout changes;
- wording or labels;
- changing which already-stored field a query displays;
- test-only fixture updates; or
- documentation.

Confirm that the required columns already exist in every production schema the
new code must accept. A UI change that starts reading a new column is not
display-only if production does not yet have that column.

### 4. Can existing values be transformed deterministically?

Classify the result:

| Decision | Meaning | Required action |
| --- | --- | --- |
| No migration | No persistent structure or meaning changes | Record why in the assessment log below |
| Schema-only | DDL is needed; existing values remain valid and untouched | Add a numbered migration and synthetic legacy tests |
| Deterministic data migration | Every affected old value has one provably correct target | Add a numbered migration, literal mapping tests, and preservation checks |
| Production profile required | Real values, units, conflicts, or ambiguities determine the rules | Do not guess or number a data migration; profile an immutable snapshot copy first |

When uncertain, choose “production profile required.” Unknown historical data is
better than confidently corrupted data.

## Required Recommendation To The User

After the assessment, answer in plain language using this exact structure:

```text
Migration assessment
- Decision: No migration | Schema-only | Data migration | Production profile required
- Why: <specific schema or stored-data reason>
- Existing production data affected: <what is affected, or “none”>
- Proposed migration: <next version and short name, or “none/not yet”>
- Transformation: <exact rule, or “no values changed”>
- Unknowns or ambiguous rows: <specific unknowns, or “none known”>
- Required tests: <temporary-database cases>
- Production snapshot needed now: Yes | No
- Deployment constraint: <what must happen before this code can be deployed>
```

Do not merely say “update the migration plan.” State the technical decision and
what, if anything, the user must provide or approve.

## Adding A Migration

Use the next positive integer after the last registered version. Names must be
short snake_case descriptions of the completed transformation.

1. Write failing tests in `tests/test_migrations.py` using temporary SQLite
   files that reproduce every accepted old schema/data shape.
2. Verify each new test fails for the intended missing behavior.
3. Add a focused apply function and append one `Migration` to `MIGRATIONS` in
   `app/migrations.py`.
4. Never call `commit()` inside a migration. The runner requires the caller's
   transaction and provides the savepoint.
5. Add columns/constraints only when absent or migrate tables using an atomic
   replacement pattern already established in `app/db.py`.
6. Change existing values only with an approved deterministic mapping. Preserve
   nonblank current values unless the approved rule explicitly replaces them.
7. Never infer missing route order, shift ownership, units, status, or business
   meaning from a weak proxy.
8. Keep the migration safe when its legacy source columns do not exist.
9. Run the focused migration tests and the affected baseline/workflow tests.
10. Append the version, rules, tests, and rehearsal status to the register below.
11. Append the feature decision and evidence to the assessment log below.

Every migration test set must cover, where applicable:

- fresh database initialization;
- the oldest accepted production schema;
- partially upgraded schema;
- existing destination values;
- null, empty, malformed, and ambiguous source values;
- imported and active/completed cards;
- preservation of status, assignment, queues, versions, timestamps, tare, rolls,
  timing, recipe/material actuals, and import-source values;
- migration record insertion exactly once;
- second-run idempotence;
- DDL/data/record rollback after an injected failure;
- `PRAGMA integrity_check` and `PRAGMA foreign_key_check`.

## Migration Register

| Version | Name | Purpose | Development | Snapshot rehearsal | Production |
| --- | --- | --- | --- | --- | --- |
| M001 | `shift_manager_import_fields` | Add the eight final ordered/route columns without guessing legacy values | 9 focused tests passed | Not run | Not run |
| M002 | `shift_management` | Add shift configuration, durable occurrences, and nullable roll attribution without historical backfill | 14 focused migration tests and 560 full-suite tests passed | Not run | Not run |
| M003 | `roll_pallet_assignment` | Add nullable constrained current-card and per-roll pallet numbers without historical backfill | 28 focused migration, 78 focused print/verifier-safety, and 686 full-suite tests passed | Not needed for M003 itself; final release rehearsal still required | Not run |
| M004 | `rewinding_return_workflow` | Rebuild `cards` for the waiting status, constrained nullable marker, and nullable final-shift foreign key without historical inference | 42 migration, 611 focused affected-workflow, and 814 full-suite tests passed | Not needed for M004 itself; final release rehearsal still required | Not run |

### M001: Shift Manager Import Fields

Accepted legacy state may include `quantity_1`, `unit_1`, `quantity_2`,
`unit_2`, and `extrusion_flag` in `cards` and `card_import_sources` alongside
production status, assignment, roll, tare, timing, and material data.

M001 ensures both import-field tables contain:

```text
ordered_gross_kg
ordered_rolls
ordered_meters
ordered_units
printing_sequence
extrusion_sequence
rewinding_slitting_sequence
confection_sequence
```

It performs no legacy value transformation. Known old fixtures contain
quantity/unit pairs such as `1000` plus `kg`; positional copying would place unit
labels in numeric-meaning destination fields. M001 therefore:

- leaves all legacy columns and values unchanged;
- adds missing final fields with blank/null values;
- preserves existing nonblank final values;
- does not translate `extrusion_flag` into any route sequence; and
- does not touch card versions, timestamps, production tables, or actuals.

Development evidence from July 25, 2026:

```bash
.venv/bin/python -m pytest tests/test_migrations.py -q
# 9 passed

.venv/bin/python -m pytest tests/test_migrations.py tests/test_baseline.py -q
# 57 passed

.venv/bin/python -m compileall app tests
git diff --check
# passed
```

No production snapshot has been profiled or rehearsed. Do not deploy M001 alone:
current views expect final fields while historical production rows retain legacy
quantity/unit pairs.

### M002: Shift Management

M002 adds `terminal_configuration`, `shift_occurrences`, the nullable
`roll_entries.shift_occurrence_id` foreign key, and the indexes that enforce one
active shift and support completed-shift and attributed-roll queries. It seeds
only the singleton configuration row with `id = 1` and `shift_count = 4`.

M002 is schema-only: it does not update cards, import sources, rolls, recipe
actuals/components, timing segments, machine queues, versions, or timestamps.
Every historical roll remains `NULL` for `shift_occurrence_id`; no historical
shift attribution is inferred. A partially upgraded database retains valid
non-null attribution and its existing configuration values. If the attribution
column already exists, M002 verifies that it has the required `ON DELETE
RESTRICT` foreign key to `shift_occurrences(id)`. A malformed partial schema is
rejected atomically rather than recorded as migrated.

Development evidence from July 25, 2026:

```bash
.venv/bin/python -m pytest tests/test_migrations.py -q
# 14 passed

.venv/bin/python -m pytest -q
# 560 passed

.venv/bin/python -m pytest tests/test_migrations.py tests/test_baseline.py \
  tests/test_shift_management.py tests/test_roll_entry.py \
  tests/test_admin_production_corrections.py -q
# 149 passed
```

The unresolved M001 legacy-data production profile and the later
release-candidate rehearsal remain deployment gates. M002 and the application
code that consumes it must deploy together after a SQLite-safe backup and
rehearsal.

### M003: Roll Pallet Assignment

M003 adds nullable `cards.current_pallet_number` and
`roll_entries.pallet_number` columns. Each column is a defaultless SQLite
`INTEGER` constrained to `NULL` or a whole integer from `1` through `999`.
Startup validation rejects missing, malformed, non-null/defaulted, or
constraint-spoofed partial definitions and validates persisted non-null values.

M003 is schema-only. It updates no existing row: historical cards and rolls
retain `NULL` in the new columns, and no pallet assignment is inferred.
Statuses, assignments, queues, versions, timestamps, tare, gross/net roll data,
shift attribution, timing, recipe/material actuals, and import-source values are
preserved. A valid partially upgraded schema keeps its existing pallet values.
The migration and record share the existing caller-owned transaction/savepoint,
and injected validation failure rolls both columns and the M003 record back.

Development evidence from July 26, 2026:

```bash
.venv/bin/python -m pytest tests/test_migrations.py -q
# 28 passed in 2.02s

.venv/bin/python -m pytest \
  tests/test_roll_pallet_ui_script_safety.py tests/test_print_output.py -q
# 78 passed in 3.52s

.venv/bin/python -m pytest -q
# 686 passed in 50.00s
```

The focused migration suite covers fresh, oldest accepted legacy, valid and
malformed partial, recorded-malformed, repeat-run, rollback, direct constraints,
full production-data preservation, `PRAGMA integrity_check == 'ok'`, and empty
`PRAGMA foreign_key_check` results on temporary databases. No production or
runtime database was opened or changed.

The independent live Playwright 1.61.0 verifier exited `0` at `1536x1024` and
`1366x768`. It exercised current-pallet autosave/reload, roll snapshotting,
correction/clear, mixed finish confirmation, terminal/admin geometry, and
browser/PDF print boundaries. The measured renderer capacities are 8 whole
rows per page-2 pallet block and 48 whole rows per overflow page. Evidence is
under `artifacts/ui-checks/roll-pallet-assignment/`; the normal PDF is 2 A4
pages and the overflow fixture PDF is 5 A4 pages.

No production snapshot is needed for M003 itself because its approved rule is
to leave historical values `NULL`. M003 and the consuming application code must
deploy together after a SQLite-safe backup. The unresolved M001 legacy-data
production profile and the final release-candidate rehearsal remain separate
deployment gates.

### M004: Rewinding Return Workflow

M004, `rewinding_return_workflow`, is implemented in `app/migrations.py` using
the canonical `cards` definition and rebuild helpers in `app/schema.py`; status
membership is defined in `app/constants.py`. It rebuilds `cards` so the status
constraint accepts `awaiting_rewinding`, then adds these nullable, defaultless
fields:

```text
cards.rewinding_roll_count INTEGER
    CHECK NULL or SQLite integer from 1 through 999
cards.final_extrusion_shift_occurrence_id INTEGER
    REFERENCES shift_occurrences(id) ON DELETE RESTRICT
```

M004 is schema-only. It transforms no existing value and infers no historical
waiting status, rewinding count, or final extrusion shift. A recorded-M003
upgrade preserves status, assignment, queue, versions, timestamps, tare,
current/per-roll pallets, roll gross/tare/net and shift links, timing,
recipe/material actuals, import-source data, legacy extension columns, and the
`cards` autoincrement high-water mark. Existing rows receive `NULL` only when a
new field was absent. A valid partial schema preserves valid non-null marker and
final-shift values.

Fresh-schema and direct-constraint tests prove every canonical status is
accepted, unknown status is rejected, the marker accepts only its exact
nullable integer range, and dangling final-shift references are rejected.
Upgrade fixtures cover recorded M003 and a sparse oldest accepted `cards`
shape. Partial fixtures cover valid values and preservation. Malformed fixtures
cover invalid partial counts, dangling shifts, a recorded M004 missing a field,
missing count constraint, missing foreign key, and a status constraint missing
either waiting or other canonical statuses. Integrity is `ok`, foreign-key
checks are empty, and repeat initialization records M004 once.

The table rebuild, copied data, recreated indexes, and migration record share
the migration runner's caller-owned transaction/savepoint. An injected failure
after the card copy proves the original schema, data, legacy extension, and M003
record are restored, the temporary rebuild table is absent, and foreign-key
enforcement is re-enabled. No runtime or production database was opened or
changed; all migration fixtures used temporary SQLite files.

Development evidence from July 27, 2026:

```bash
source .venv/bin/activate
python -m compileall -q app scripts tests
# exited 0

python -m pytest tests/test_migrations.py -q
# 42 passed in 3.18s

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
# 611 passed in 48.39s

python -m pytest -q
# 814 passed in 61.92s
```

The unchanged prototype verifier and guarded live Playwright verifier both
exited `0`. The live verifier used only
`.test-runtime/rewinding-ui.sqlite3`, passed at `1920x768` and `1366x768`,
reported no overflow, console errors, or page errors, and recorded evidence
under `artifacts/ui-checks/rewinding-return-workflow/`.

Migration assessment
- Decision: Schema-only
- Why: `cards.status` must accept `awaiting_rewinding`, and `cards` needs the
  constrained nullable marker plus nullable final-shift foreign key.
- Existing production data affected: none; every existing stored value is
  copied unchanged and absent new fields remain `NULL`.
- Proposed migration: M004 `rewinding_return_workflow` (implemented).
- Transformation: no values changed.
- Unknowns or ambiguous rows: none known; historical rewinding state, count,
  and final shift are deliberately not inferred.
- Required tests: fresh, recorded-M003/oldest upgrade, valid partial, malformed
  partial/recorded, direct constraints, preservation, idempotence, integrity,
  foreign keys, and injected rollback on temporary databases; all pass.
- Production snapshot needed now: No.
- Deployment constraint: deploy the application and M004 together only after a
  SQLite-safe backup; retain the unresolved M001 production profile and final
  release-candidate rehearsal as independent release gates.

## Migration Assessment Log

| Date | Feature/change | Decision | Result |
| --- | --- | --- | --- |
| 2026-07-25 | Shift Manager V14.04 import-field correction | Schema-only plus later production profile | M001 implemented; legacy values deliberately unchanged; 9 focused and 57 combined tests passed |
| 2026-07-25 | V2 documentation consolidation and trigger command | No migration | Documentation and agent instructions only; no stored data or schema changed |
| 2026-07-25 | Shift management M002 schema foundation | Schema-only | Added configuration, occurrences, nullable roll FK, and indexes; no existing values changed and legacy rolls remain `NULL`; M001 production profile and release-candidate rehearsal remain deployment gates |
| 2026-07-25 | New-roll shift occurrence attribution and correction preservation | No migration | M002 already provides the nullable roll FK; only new roll writes resolve attribution, while historical `NULL` values and existing linked rolls remain unchanged |
| 2026-07-25 | Admin terminal-configuration page | No migration | Routes, templates, navigation, and CSS now expose the existing M002 singleton configuration row; no schema, stored values, or data meaning changed |
| 2026-07-25 | Terminal shift routes, state gate, and polling signature | No migration | Routes and read context use the existing M002 configuration/occurrence data; the mutation gate and polling signature change runtime behavior only, with no schema or stored-value transformation |
| 2026-07-25 | Completed shift-management functionality and final migration maintenance | Schema-only M002; no additional migration | Final feature diff confirmed M002 covers every persistent change; legacy rolls remain `NULL`, no values are transformed, 145 focused affected tests and 547 full-suite tests passed; M001 production profiling and release-candidate rehearsal remain deployment gates |
| 2026-07-26 | Shift-management UI homogenization and bounded history pagination | No migration | Templates, CSS, supplied SVG assets, GET query pagination, display context, tests, and browser verification only; no schema, stored value, timestamp, roll attribution, or data meaning changed |
| 2026-07-26 | Shift UI redesign | No migration | Actual diff changes only presentation helpers, templates/CSS/JavaScript, browser verification, tests, and documentation. M002 schema and stored meanings are unchanged; 198 focused and 552 full-suite tests passed. M001 production profiling and the final release-candidate rehearsal remain deployment gates. |
| 2026-07-26 | Shift UI kiosk URL, compact overview, date display, and full-recipe reachability fixes | No migration | JavaScript history cleanup, conditional close rendering, CSS sizing/scrolling, display formatting, browser fixtures, tests, and documentation only. No schema or stored-data meaning changed; runtime sample cards use the existing import/release workflow. |
| 2026-07-26 | Task 01 adversarial review corrections and final migration maintenance | Schema-only M002; no additional migration | M002 and startup validation now reject a partial attribution column without its required foreign key, including a database that already records M002; terminal write gates are transaction-bound; shift-count input is bounded; history reads are paged; UI state and verification were hardened. No existing values are transformed. 14 migration and 560 full-suite tests pass; M001 profiling and release-candidate rehearsal remain deployment gates. |
| 2026-07-26 | Completed Task 01 post-merge migration maintenance | Schema-only M002; no additional migration | The merged feature and migration chain were reassessed after final integration. M002 remains the only required persistent change, performs no historical attribution or other value transformation, and fails safely on a malformed partial roll foreign key. 14 migration, 149 affected-workflow, and 560 full-suite tests pass. No production snapshot is needed now; M001 profiling and the release-candidate rehearsal remain deployment gates. |
| 2026-07-26 | Admin planning page redesign and guarded planning writes | No migration | The merged diff changes planning display, templates/CSS/JavaScript, sorting/display helpers, delete/release/replan transaction boundaries, and tests/documentation only. It reuses existing `cards`, `roll_entries`, `production_time_segments`, and `recipe_actual_entries` columns/tables; no schema, constraints, migration registry entry, status meaning, units, assignments, queues, versions, timestamps, tare, rolls, timing, or material actual values are transformed. 573 full-suite tests passed after merge; M001 profiling and release-candidate rehearsal remain deployment gates. |
| 2026-07-26 | Repeated admin planning migration maintenance check | No migration | Re-read the migration procedure and re-inspected the merged admin-planning diff, `app/migrations.py`, `app/db.py` schema/init ordering, and migration tests. The feature still only changes UI/planning behavior and guarded writes over existing columns/tables; no new migration version or production data profile is required for this feature. |
| 2026-07-26 | Per-roll pallet attribution and operational-card summary | Schema-only M003 | Added constrained nullable current-card and per-roll pallet columns; historical values deliberately remain `NULL` and no values are transformed. 28 migration, 78 print/verifier-safety, and 686 full-suite tests pass; integrity is `ok`, foreign-key checks are empty, and live browser/PDF acceptance passed at both supported viewports. No M003 snapshot is needed now; M001 profiling and the final release-candidate rehearsal remain deployment gates. |
| 2026-07-26 | Repeated pallet-assignment migration maintenance after user acceptance | Schema-only M003; no additional migration | Re-inspected the accepted feature diff, schema/init ordering, M003 registry entry, startup validation, and synthetic legacy/partial-schema tests. M003 remains the only required persistent change; historical card and roll pallet values remain `NULL`, no stored values are transformed, and no production snapshot is needed for M003. The M001 production profile and final release-candidate rehearsal remain deployment gates. |
| 2026-07-27 | Rewinding return workflow and final Task 11 migration assessment | Schema-only M004 | Rebuilt `cards` for `awaiting_rewinding`, constrained nullable marker, and nullable final-shift foreign key; no existing value or historical state was inferred. Fresh, recorded-M003/oldest upgrade, valid partial, malformed partial/recorded, idempotence, integrity/foreign-key, preservation, and injected rollback cases pass on temporary databases. 42 migration, 611 focused affected-workflow, and 814 full-suite tests pass; guarded live browser verification passed at both viewports. No M004 production snapshot is needed now; deploy app+M004 together after SQLite-safe backup while retaining the M001 profile and final release rehearsal gates. |
| 2026-07-27 | Task 10 roll-change countdown pace clock | No migration | Actual feature diff adds terminal HTML/CSS/JavaScript, browser-local versioned schedule records, guarded test scripts, tests, and documentation only. No SQLite structure, stored production-data meaning, card version, or production value changes; browser-local countdowns are not restored from SQLite backups. |

Append one row after every use of the trigger command, including when no
migration is required.

## After Each Feature

Before closing any task:

1. inspect the diff and run the decision procedure above;
2. record one of the four decisions in the assessment log above;
3. if a migration is needed, implement/test it in the same feature slice unless
   real production values must be profiled first;
4. if profiling is required, leave data unchanged, explain the deployment block,
   and add the exact profile questions to this file;
5. do not reset the disposable development database merely to simulate
   production migration—use synthetic legacy fixtures;
6. do not ask the user for a production database until the planned application
   changes are stable, unless earlier profiling is explicitly approved.

## Production Legacy-Data Profile

After application data shapes are stable, request a SQLite-safe production
backup. The received file is immutable evidence.

1. Record source timestamp, deployed revision, file size, SHA-256, SQLite
   version, `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, recorded
   migrations, and high-level row counts.
2. Clone it to an ignored temporary directory and query only the copy.
3. Record counts—not customer-level tracked rows—for statuses, assignments,
   queues, rolls, gross/net/tare, timing, material actuals, and import sources.
4. For both `cards` and `card_import_sources`, count each trimmed legacy unit
   spelling, quantity-less unit, unitless quantity, existing final destination,
   and card/source disagreement.
5. List ambiguous mapping categories and their counts. Do not change them.
6. Produce the required recommendation. If conversion is deterministic, write a
   new exact migration task and obtain approval before implementation.
7. Record the profile and decision in this file without customer names, order
   details, or the database itself.

## Release-Candidate Rehearsal

When code and the migration chain are final, obtain a fresh SQLite-safe backup.

1. Fingerprint the immutable backup and clone it.
2. Capture pre-migration invariants.
3. Run the full application initialization/migration chain on the clone.
4. Record applied versions, duration, logs, exit status, integrity, and foreign
   key results.
5. Compare all production invariants and require exactly the approved value
   transformations.
6. Run health, admin, terminal, and completed-card print smoke checks against the
   migrated copy.
7. Repeat initialization and prove no migration/data change occurs.
8. Write the final maintenance and rollback commands using the observed timing.

## Backup, Deployment, And Rollback

Never use a raw file copy as the backup method while the app may be writing.
Create a SQLite-safe backup using the deployed environment and `app.backups`:

```bash
.venv/bin/python -m app.backups backup \
  --source /opt/extrusion-terminal/data/extrusion_terminal.sqlite3 \
  --backup-dir /opt/extrusion-terminal/backups \
  --keep 144
```

For production deployment:

1. approve a maintenance window;
2. stop the app;
3. create and fingerprint the final SQLite-safe backup;
4. preserve the previous application revision;
5. deploy code and run initialization/migrations;
6. run integrity, foreign-key, invariant, health, admin, terminal, and print
   checks;
7. reopen use only after validation passes.

Rollback is recovery from the full pre-migration backup, not improvised reverse
SQL:

1. keep the app stopped;
2. restore the final backup using `app.backups restore` and the documented
   production paths;
3. restore the previous application revision;
4. start the app;
5. verify `/health`, `/admin`, `/terminal`, representative production cards, and
   completed-card printing before reopening use.

Production paths:

- database: `/opt/extrusion-terminal/data/extrusion_terminal.sqlite3`;
- backups: `/opt/extrusion-terminal/backups`.

Never store a production database, backup, customer-level extract, or migration
working copy in git or in this directory.
