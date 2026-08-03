# Production Migration Report — 2026-07-28

## Outcome

**Final decision: GO.** The production application was upgraded from revision
`f6123c8669c1b0ab11698ba5ecf7ee8e4f7ce32d` to revision
`95093c080cf76867a32b785cf4686cf391e5cdc3`. Database migrations M001 through
M006 ran successfully. The post-deployment database preserved every value in
every pre-existing production column and added only the approved schema and
deterministic normalized values.

The `extrusion-terminal.service` service restarted successfully, owned port
`8000`, and reported the exact deployed revision from `/health`. Final checks
against the downloaded post-deployment backup passed integrity, foreign-key,
migration-history, preservation, idempotence, Admin, Terminal, card-detail,
and print-output verification.

## Environment And Revisions

| Item | Value |
| --- | --- |
| Production host | `extrusion-app` |
| Application checkout | `/opt/extrusion-terminal/app` |
| Runtime database | `/opt/extrusion-terminal/data/extrusion_terminal.sqlite3` |
| Backup directory | `/opt/extrusion-terminal/backups` |
| Service | `extrusion-terminal.service` |
| Previous revision | `f6123c8669c1b0ab11698ba5ecf7ee8e4f7ce32d` |
| Deployed revision | `95093c080cf76867a32b785cf4686cf391e5cdc3` |
| Deployment log | `/opt/extrusion-terminal/app/.deploy/logs/deploy_20260728T075151Z.log` |
| SQLite version observed | `3.45.1` |

The final revision included the Bulgarian presentation of known next-operation
values. This last change was display-only: stored English source values were
not rewritten.

## Database Evidence

### Preliminary rehearsal backup

The first production-safe backup used to develop and rehearse M006 was:

```text
/opt/extrusion-terminal/backups/extrusion_terminal_20260728_060830_855736.sqlite3
Size:   282624 bytes
SHA-256: de409738df588db73a769b71ad545865d05e055a45a015eee7eaccfca1bb80bc
```

This backup was useful for migration development, but it was not used as the
final cutover baseline.

### Frozen pre-migration backup

Workers stopped using the terminal, the application service was stopped, and
`systemctl is-active extrusion-terminal.service` returned `inactive`. A final
SQLite-safe backup was then created, fingerprinted, downloaded, and verified:

```text
/opt/extrusion-terminal/backups/extrusion_terminal_20260728_073114_160413.sqlite3
Size:   282624 bytes
SHA-256: e7a8b7ac193433e1f132bce799915f423d2ca98137d710883c0efed078d83e1d
```

An additional pre-activation backup was created automatically by the deployment
script:

```text
/opt/extrusion-terminal/backups/extrusion_terminal_20260728_075152_385438.sqlite3
```

Creating multiple SQLite-safe backups was harmless and increased rollback
coverage.

### Post-migration backup

After deployment and service restart, a new SQLite-safe backup was created,
downloaded, and independently fingerprinted:

```text
/opt/extrusion-terminal/backups/extrusion_terminal_20260728_075318_093595.sqlite3
Size:   339968 bytes
SHA-256: f3786bb80fa4bf6e99a50e1f0c918f8db766450af42e1d3d90ccb08b53e3f481
```

The larger file is expected because the migration added tables, columns,
indexes, constraints, and migration-history records.

Downloaded evidence copies were retained under the ignored local
`production-db/` directory. They must remain untracked.

## Why A Fresh Final Backup Was Necessary

The frozen pre-migration backup differed from the earlier rehearsal backup.
Between those snapshots:

- three card versions and `updated_at` values changed;
- three roll rows were added; and
- four recipe-actual rows were added.

No legacy amount or route source value changed, but the production activity
proved that an earlier backup cannot be assumed to represent the cutover state.
Always obtain and verify a fresh backup after workers stop.

## Frozen Baseline

The final pre-migration database contained:

| Invariant | Value |
| --- | ---: |
| Cards | 35 |
| Card import-source rows | 35 |
| Completed cards | 28 |
| Imported cards | 1 |
| Pending cards | 3 |
| Running cards | 3 |
| Machines | 4 |
| Roll rows | 653 |
| Gross roll total | 18586.70 kg |
| Tare total | 788.50 kg |
| Net roll total | 17798.20 kg |
| Production timing segments | 35 |
| Open timing segments | 3 |
| Recipe components | 126 |
| Recipe actual entries | 117 |
| Import batches | 24 |
| Import batch rows | 49 |

The three running cards and three open timing segments were intentional. The
maintenance interval remained part of their open elapsed time.

## Applied Migrations

The deployed database records the following exact history, once each and in
order:

| Version | Name | Result |
| --- | --- | --- |
| M001 | `shift_manager_import_fields` | Added final ordered-amount and route columns without guessing values |
| M002 | `shift_management` | Added shift configuration, occurrences, indexes, and nullable roll attribution |
| M003 | `roll_pallet_assignment` | Added nullable constrained card and roll pallet numbers |
| M004 | `rewinding_return_workflow` | Added the waiting status, rewinding marker, and final-shift relationship |
| M005 | `shift_schema_contract` | Added and validated the bounded shift configuration contract |
| M006 | `legacy_import_normalization` | Deterministically populated approved legacy amount and route destinations |

### M006 amount mapping

M006 copied exact stored text only when card and import-source values agreed,
the legacy values matched the proven numeric production shape, and the final
destination was blank:

```text
quantity_1 -> ordered_gross_kg
unit_1     -> ordered_rolls
quantity_2 -> ordered_meters
unit_2     -> ordered_units
```

The misleading legacy `unit_1` and `unit_2` names came from the former workbook
contract; production profiling and the corrected Shift Manager contract proved
that their stored values represented roll and unit counts for this database.

### M006 route mapping

For rows marked for extrusion, the approved route rules were:

```text
blank next operation -> extrusion 1
Confection           -> extrusion 1, confection 2
Printing             -> extrusion 1, printing 2, confection 3
```

The resulting production distribution was:

- 29 extrusion-only routes;
- 5 extrusion-then-confection routes; and
- 1 extrusion-then-printing-then-confection route.

All 35 card/import-source pairs agreed. Final verification reported zero amount
mapping errors and zero route disagreements.

## Historical Values Deliberately Not Inferred

The migration did not invent historical production information:

- all 653 historical rolls retained `NULL` shift attribution;
- historical card and roll pallet values remained `NULL`;
- no historical card was assigned a rewinding marker or waiting status; and
- no historical final extrusion shift was guessed.

Completed historical cards remain valid, editable, printable, and correctly
weighted. The limitation is only that their historical rolls cannot be assigned
to a particular shift for shift reporting. This is preferable to false data.

The new shift configuration was seeded as singleton `id = 1`, `shift_count = 4`,
`version = 1`. No shift occurrence was invented. A real current shift must be
opened before workers add new rolls or finish running cards.

## Rehearsal And Preservation Evidence

Before production deployment, the exact release candidate was run against a
writable clone of the frozen backup. M001 through M006 completed in `0.07`
seconds. The rehearsal proved:

- `PRAGMA integrity_check` returned `ok`;
- `PRAGMA foreign_key_check` returned no rows;
- all original table rows and original columns matched exactly;
- all approved amount and route mappings were exact;
- no historical shift, pallet, rewinding, status, or final-shift value was
  inferred;
- the second initialization produced the same logical database hash; and
- health, Admin, Terminal, completed-card detail, and print routes rendered
  successfully.

The optional Starlette test-client dependency was not installed in the local
virtual environment. Instead of installing new tooling during cutover, live
smoke checks were run through a temporary real Uvicorn server and normal HTTP
requests. This exercised the actual application startup path.

## Production Deployment

The production checkout was clean and still at the previous revision. The
service was already stopped. Deployment used:

```bash
cd /opt/extrusion-terminal/app
bash scripts/deploy_production.sh --skip-tests
```

`--skip-tests` was chosen because the final feature agent had already run the
full suite against the final code. The deployment script still performed all
of the following:

1. verified paths, branch, database presence, and clean Git state;
2. fetched `origin/main` and resolved the exact target revision;
3. created a SQLite-safe backup before activating new code;
4. fast-forwarded the checkout;
5. verified runtime dependencies;
6. ran Python compilation and import checks;
7. wrote the exact deployed revision marker;
8. restarted `extrusion-terminal.service`;
9. verified the new process command and working directory;
10. verified that the service process owned port `8000`;
11. verified `/health` and its reported revision; and
12. verified that the checkout still matched the fetched target.

The successful deployment reported:

```text
DEPLOYMENT OK
deployed_commit=95093c080cf76867a32b785cf4686cf391e5cdc3
service=extrusion-terminal.service
pid=26494
health_url=http://127.0.0.1:8000/health
```

The service started at `2026-07-28 07:51:57 UTC`.

## Final Post-Deployment Verification

The downloaded post-migration backup was compared to the frozen pre-migration
backup by selecting every original column from every original table and
comparing the complete row multisets. The following all had zero removed,
changed, or unexpected rows:

- `cards`;
- `card_import_sources`;
- `import_batches`;
- `import_batch_rows`;
- `machines`;
- `production_time_segments`;
- `recipe_components`;
- `recipe_actual_entries`; and
- `roll_entries`.

Therefore every pre-existing production value was preserved exactly. The
headline counts, status distribution, roll totals, timing counts, and open
segments also matched the frozen baseline.

Running initialization again against a disposable copy of the actual
post-deployment backup produced identical logical hashes:

```text
before: 61c00f3c7c10218650e42fb6f9e80aa99155f1048c1c5939c3c254e44b62feef
after:  61c00f3c7c10218650e42fb6f9e80aa99155f1048c1c5939c3c254e44b62feef
```

Final HTTP checks returned `200` for health, Admin import, Terminal, Admin card
detail, Terminal card detail, and completed-card print output. An actual
migrated card with stored next operation `Printing` rendered the approved
Bulgarian `Печат` value on both Terminal and print output.

## Rollback Assets And Rule

No rollback was required. If a future deployment fails validation:

1. keep or place the application service in the stopped state;
2. restore the final pre-migration SQLite-safe backup with
   `.venv/bin/python -m app.backups restore` rather than reverse SQL;
3. restore the previous exact application revision;
4. start the service;
5. verify process identity, port ownership, health revision, Admin, Terminal,
   representative cards, and print output; and
6. do not reopen worker access until all rollback checks pass.

For this cutover, the off-host rollback evidence is the verified
`extrusion_terminal_20260728_073114_160413.sqlite3` backup and previous revision
`f6123c8669c1b0ab11698ba5ecf7ee8e4f7ce32d`.

## Reusable Future Migration Checklist

### 1. Freeze the candidate

- Commit and push the exact candidate.
- Record its full Git SHA.
- Require successful relevant and full automated tests against that SHA.
- Review the final diff and migration impact.
- Do not duplicate a full suite if fresh evidence already covers the exact
  unchanged commit; run only missing verification.

### 2. Begin the maintenance window

- Tell workers to stop using the terminal.
- Decide explicitly whether currently running timing segments should remain
  open during maintenance or be paused first.
- Stop `extrusion-terminal.service`.
- Confirm `systemctl is-active` returns `inactive`.
- Confirm the production checkout is clean and record its current SHA.

### 3. Create and verify the final pre-migration backup

Use the deployed environment's SQLite backup helper, never a raw copy of a live
database:

```bash
.venv/bin/python -m app.backups backup \
  --source /opt/extrusion-terminal/data/extrusion_terminal.sqlite3 \
  --backup-dir /opt/extrusion-terminal/backups \
  --keep 144
```

Record the exact filename, byte size, and SHA-256. Download that exact file and
verify the checksum again on the receiving computer.

For Windows Command Prompt, use `%USERPROFILE%` and `certutil`; `$HOME`,
`Get-Item`, and `Get-FileHash` are not Command Prompt syntax:

```bat
cd %USERPROFILE%\Downloads
scp sk@extrusion-app:/exact/backup/path.sqlite3 .
certutil -hashfile backup-file.sqlite3 SHA256
```

An SSH host-alias prompt may add the alias to `known_hosts`. Accept it only after
the displayed fingerprint is verified against the already trusted host/IP key.
A rejected password attempt has no database effect; successful SCP plus a
matching checksum proves the resulting transfer.

### 4. Profile and rehearse only on copies

- Treat the downloaded backup as immutable evidence.
- Clone it into an ignored temporary directory.
- Capture integrity, foreign keys, migration history, table counts, statuses,
  queues, rolls, weights, timing, recipes, and importer invariants.
- Apply the full migration chain only to the clone.
- Compare every original column and value.
- Require exactly the approved transformations and no inferred historical data.
- Prove second-run idempotence.
- Run health, Admin, Terminal, representative card, and print smokes.

### 5. Deploy

- Use `scripts/deploy_production.sh` rather than ad hoc Git and service commands.
- Use the default test behavior unless a fresh full-suite result already covers
  the exact deployed commit; only then consider `--skip-tests`.
- Require `DEPLOYMENT OK` and the expected full deployed SHA.
- Keep workers out even though the service has restarted.

### 6. Verify the deployed database

- Create a new SQLite-safe post-migration backup.
- Record and verify its size and SHA-256 off-host.
- Compare it against the frozen pre-migration backup.
- Require integrity `ok`, no foreign-key violations, exact migration history,
  exact preservation of all original values, approved new values only,
  idempotence, and successful application smokes.
- Retain both the before and after evidence files outside production.

### 7. Reopen production

- Issue an explicit `GO` only after the post-deployment comparison passes.
- Open the current shift before any new roll entry or card completion when
  shift management is newly introduced.
- Explain new operator behavior before workers resume.
- Keep rollback artifacts until the deployment is operationally accepted.

## Actionable Conclusions

1. The backup → fingerprint → off-host download → clone rehearsal → scripted
   deployment → post-backup → exact comparison sequence worked and should be
   reused.
2. A preliminary production snapshot is useful for development, but it never
   replaces the final snapshot taken after workers stop.
3. Schema migration and application code must deploy together because startup
   applies the ordered migration registry.
4. Exact old-column comparison provides stronger preservation evidence than
   row counts or file hashes alone.
5. File size and SHA-256 are expected to change after schema migration; logical
   invariants determine correctness.
6. Unknown historical shifts, pallets, and rewinding state must remain unknown
   unless reliable evidence exists.
7. A successful service restart is not the final gate. Worker access reopens
   only after the migrated database has been downloaded and independently
   verified.
8. The Ubuntu `System restart required` banner was unrelated to the application
   migration. A VM reboot should be scheduled separately and followed by a
   service/health check.
