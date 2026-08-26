# SQLite Migration And Deployment Playbook

This is the active reusable procedure for future extrusion-terminal schema or
stored-data changes. It distils the July 28, 2026 M001-M006 production migration
that completed successfully. The exact historical evidence remains in
`v2-files/archive/MIGRATION-REPORT-2026-07-28.md`.

This playbook does not authorize access to, copying of, or mutation of a live
production database. Every production action still requires explicit user
approval and a scheduled maintenance window.

## Sources Of Truth

- `app/migrations.py` is the ordered migration registry implemented by the
  current application revision.
- A database's `schema_migrations` table is the record of migrations applied to
  that database.
- `app/db.py` and `app/schema.py` define the schema contract consumed by the
  current application.
- `tests/test_migrations.py` is the executable migration-safety contract.
- `docs/production-deployment.md` and `scripts/deploy_production.sh` define the
  current deployment procedure.

Do not maintain a second migration-status register in Markdown. Determine the
next migration version from the code registry at implementation time, then
verify the target database's recorded prefix on an immutable clone. A dated
production report may record what happened during a particular deployment, but
it is historical evidence rather than live state.

## Decide Whether A Migration Is Needed

Inspect the completed feature diff, not only its task description.

1. **No migration** — HTML, CSS, wording, tests, or code changes that neither
   change persistent structure nor reinterpret stored values.
2. **Schema-only migration** — tables, columns, indexes, constraints, defaults,
   or foreign keys change, while every existing stored value remains valid and
   untouched.
3. **Deterministic data migration** — every affected old value has one proven
   target and the exact transformation can be tested literally.
4. **Production profile required** — real values, units, conflicts, missing
   fields, or business meaning determine the transformation. Stop rather than
   guessing. Profile an immutable SQLite-safe backup copy and obtain approval
   for every ambiguous mapping before implementing the data migration.

New code that begins reading a column is not display-only if an accepted
production schema may lack that column. A new status, route meaning, required
value, unit, or interpretation can require a migration even without obvious
DDL.

Never infer historical shift ownership, pallet assignment, rewinding state,
route order, units, or other business facts from a weak proxy.

## Development Requirements

1. Reproduce every accepted legacy or partial schema in temporary databases.
2. Write focused migration tests before implementing the migration.
3. Add one positive, unique, ordered migration version to `app/migrations.py`.
4. Keep the migration inside the runner's caller-owned transaction and
   savepoint; do not call `commit()` from migration code.
5. Preserve valid existing destination values unless the approved rule
   explicitly replaces them.
6. Fail atomically on malformed schema, unsupported values, or ambiguity.
7. Prove a second initialization applies nothing and changes nothing.
8. Require `PRAGMA integrity_check` to return `ok` and
   `PRAGMA foreign_key_check` to return no rows.
9. Run the focused migration tests, affected workflow tests, full Python suite,
   syntax/import checks, and `git diff --check` against temporary databases.
10. Inspect the final diff again and record the assessment after implementation
    and verification—not from the proposed design alone.

Tests should cover, where applicable: the oldest accepted schema, fresh schema,
valid and malformed partial upgrades, existing destination values, null/blank/
malformed/ambiguous sources, active and completed cards, migration history,
idempotence, injected-failure rollback, autoincrement preservation, and every
production table/value that the feature must not change.

## Production Evidence Rules

- Never profile, initialize, or rehearse against the live runtime database.
- Do not use an ordinary filesystem copy while SQLite may be writing.
- Stop workers and the service before taking the final pre-migration evidence.
- Create the backup with the repository's SQLite backup command/API so it runs
  integrity and foreign-key checks before retaining the image.
- Record the deployed application revision, SQLite version, backup byte size,
  SHA-256, relevant row/status counts, migration history, and integrity results.
- Copy the completed backup off-host and make the evidence immutable.
- Perform all profiling and rehearsal on disposable copies of that backup.
- Keep customer data, database files, backup copies, and reports containing
  business data out of Git.

On the current production layout, the explicit final backup command is:

```bash
.venv/bin/python -m app.backups backup \
  --source /opt/extrusion-terminal/data/extrusion_terminal.sqlite3 \
  --backup-dir /opt/extrusion-terminal/backups \
  --keep 144
```

Record the exact output filename, size, and SHA-256. Download that completed
file and verify the same checksum on the receiving computer before treating it
as immutable evidence.

A preliminary snapshot can guide development, but it never replaces the final
backup taken after workers stop. The final backup is the rollback boundary and
must reflect the exact state immediately before deployment.

## Rehearsal That Worked

On disposable clones of the immutable final backup:

1. Record complete pre-migration invariants. Prefer ordered exports or logical
   hashes of every pre-existing column and row over headline counts alone.
2. Run the exact candidate application's normal initialization so it applies
   the complete ordered migration chain.
3. Record duration, applied versions/names, schema, counts, statuses, queues,
   rolls, gross/tare/net values, timing, shifts, pallets, recipe/material
   actuals, import sources, versions, timestamps, and autoincrement state.
4. Compare every original column and value before and after. Accept only the
   specifically approved new schema and deterministic transformed values.
5. Require integrity `ok`, no foreign-key violations, and the exact expected
   migration-history prefix.
6. Run health, Admin, Terminal, representative-card, correction, and eligible/
   ineligible print smokes against the migrated clone.
7. Initialize the same clone a second time. Require no new migration record and
   an identical logical database state.
8. Restore the pre-migration backup into a separate path with the backup CLI's
   `restore --backup <verified-backup> --target <disposable-database>` form,
   run the previous exact application revision, and repeat its
   health/Admin/Terminal/representative print smokes.

The successful July 28 rehearsal also showed why file hashes are insufficient:
SQLite file size and SHA-256 naturally change after schema work. Exact logical
preservation is the deciding evidence.

## Maintenance Window And Deployment

1. Freeze the exact candidate revision; do not add feature changes during the
   rehearsal/deployment sequence.
2. Schedule the maintenance window and keep workers out.
3. Stop the application service and confirm no worker writes can occur.
4. Take, verify, fingerprint, and copy off-host the final SQLite-safe backup.
5. Rehearse the exact candidate and full migration chain on clones of that
   final backup. Do not proceed if the final evidence differs from the approved
   profile or produces ambiguous rows.
6. Deploy schema-consuming code and its migrations together using
   `bash scripts/deploy_production.sh`. Do not replace the scripted deployment
   with ad hoc Git or service commands.
7. Require the script to report `DEPLOYMENT OK`, verify process/port ownership,
   and confirm `/health` reports the exact deployed Git revision.
8. Keep workers out even after the service restarts.
9. Create a new post-migration SQLite-safe backup, fingerprint it off-host, and
   compare it with the frozen pre-migration evidence using the same invariants.
10. Repeat integrity, foreign-key, migration-history, idempotence, health,
    Admin, Terminal, representative-card, correction, and print checks.
11. Issue an explicit `GO` and reopen production only after every post-deploy
    comparison passes.

Use `--skip-tests` only when the exact deployed commit already has fresh full-
suite evidence and the operator intentionally chooses that documented option.
The deployment script must still perform its syntax/import, backup, revision,
service, port, and health checks.

## Rollback Rule

Do not attempt reverse SQL during a failed migration deployment.

1. Keep the application service stopped.
2. Preserve the failed post-migration database for diagnosis.
3. Restore the verified final pre-migration SQLite-safe backup with the backup
   CLI's `restore --backup <verified-backup> --target <runtime-database>` form.
4. Restore the exact previous application revision that matches that database.
5. Start the service and verify process identity, port ownership, health
   revision, Admin, Terminal, representative cards, and printing.
6. Account explicitly for any production writes made after the backup. If such
   writes exist, do not overwrite them without a separately approved recovery
   procedure.
7. Reopen worker access only after rollback verification passes.

## Required Migration Assessment

Record this concise assessment in the feature's durable implementation note or
deployment record; do not recreate a global Markdown register:

```text
Migration assessment
- Decision: No migration | Schema-only | Data migration | Production profile required
- Why: <specific schema or stored-data reason>
- Existing production data affected: <affected values, or none>
- Proposed migration: <version/name derived from current code, or none/not yet>
- Transformation: <exact mapping, or no values changed>
- Unknowns or ambiguous rows: <specific unknowns, or none known>
- Required tests: <temporary-database cases and preservation checks>
- Production snapshot needed now: Yes | No
- Deployment constraint: <what must happen before deployment>
```

For a deployed migration, add a dated report containing the exact candidate and
production revisions, backup fingerprints, applied migration history, approved
transformations, invariant comparisons, smoke results, rollback assets, and the
final `GO`/rollback decision. Place completed reports under `v2-files/archive/`
or the later repository archive chosen for release evidence.

## Lessons From July 28, 2026

- The successful sequence was: safe backup → fingerprint → off-host copy →
  clone-only profile/rehearsal → exact preservation comparison → rollback
  rehearsal → scripted deployment → post-backup → independent comparison →
  explicit `GO`.
- Schema migrations and their consuming code must deploy together because
  startup applies the ordered registry.
- Exact old-column comparisons are stronger evidence than row counts.
- A successful service restart is necessary but not sufficient.
- Unknown historical values are safer than plausible invented values.
- The final frozen backup, not an earlier snapshot, is the recovery boundary.
