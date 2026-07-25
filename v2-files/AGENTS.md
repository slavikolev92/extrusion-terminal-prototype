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

## Migration Assessment Log

| Date | Feature/change | Decision | Result |
| --- | --- | --- | --- |
| 2026-07-25 | Shift Manager V14.04 import-field correction | Schema-only plus later production profile | M001 implemented; legacy values deliberately unchanged; 9 focused and 57 combined tests passed |
| 2026-07-25 | V2 documentation consolidation and trigger command | No migration | Documentation and agent instructions only; no stored data or schema changed |

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
