# V2 Records Archive And Prune Design

## Goal

Make `v2-files/` an unambiguous current-status and backlog area while retaining
the minimum historical and operational knowledge needed for future database
migrations and deployments.

## Record Lifecycle

- The root of `v2-files/` contains only the master tracker and work that is
  active, paused, deferred, or awaiting an explicit future decision.
- `v2-files/archive/` contains completed specifications and point-in-time
  evidence that remains useful for explaining shipped behavior or a past
  production event. Archived records are not current status sources.
- `docs/implementation-notes/` contains reusable instructions that future work
  should actively follow.
- Superseded execution trackers and verdicts are deleted when their only useful
  lessons have been preserved elsewhere. Git history remains the recovery path.

## Archive And Deletion Decisions

Move these records to `v2-files/archive/`:

- `MIGRATION-REPORT-2026-07-28.md`, preserved unchanged as the evidence for the
  successful M001-M006 production migration and deployment;
- `TASK-01-SHIFT-MANAGEMENT.md`, after its status is corrected to completed and
  deployed;
- `TASK-10-ROLL-CHANGE-COUNTDOWN.md`, after its status distinguishes the
  deployed feature from the later source-only threshold follow-up; and
- `TASK-11-REWINDING.md`, after its status is corrected to completed and
  deployed.

Delete the superseded release-candidate audit, obsolete `NO-GO` verdict, and
former V2 migration instructions/register after extracting their durable
lessons.

Add `v2-files/archive/README.md` so archived documents cannot be mistaken for
open work.

## Durable Migration Guidance

Create `docs/implementation-notes/sqlite-migration-and-deployment-playbook.md`.
It will describe:

- how to classify persistent schema and stored-meaning changes;
- why the live database must never be profiled or migrated during development;
- the backup, fingerprint, off-host-copy, clone, rehearsal, preservation,
  idempotence, rollback, deployment, and post-deployment sequence that worked;
- the rule that the migration registry in code and the database's
  `schema_migrations` table are authoritative, not a manually maintained
  Markdown register;
- the evidence required for schema-only, deterministic data, and ambiguous
  production-data cases; and
- the final migration-assessment format future feature work should record.

The July 28 report remains historical proof, while the playbook becomes the
active procedure.

## Current Tracker Corrections

Update `v2-files/PLAN.md` without discarding its existing uncommitted Task 18
changes. The tracker will:

- identify the last confirmed production revision separately from current
  source;
- include the completed terminal pallet-summary source work and its mandatory
  pre-rollout compatibility gate;
- link completed specifications through the archive;
- link future migration work to the durable playbook;
- keep Tasks 4, 6, 7, 13, 14, 15, and 17 explicitly deferred/optional;
- keep Task 18 as the only active application design work; and
- avoid treating old release-candidate gates as current work.

Correct active/deferred task files so they refer to the new playbook. Task 14
must not reserve the already-used M005 number; a future migration number is
selected from the code registry when implementation begins.

## Reference Safety

Update meaningful current and durable references to the archived paths or the
new playbook. Historical implementation plans may retain descriptions of what
they changed at the time, but they must not direct future agents to a deleted
file as the current procedure. Explicit references to the deleted release
audit and verdict will be removed or labelled as Git-history-only records.

## Verification

- List `v2-files/` and confirm only current/deferred records remain at its root.
- Search the repository for references to the deleted paths.
- Search active records for stale `NO-GO`, pending M001-M006 production gates,
  and the obsolete future `M005` recipe-catalogue wording.
- Confirm the archived migration report still records the successful `GO`,
  deployed revision, M001-M006 result, and rollback evidence.
- Review the complete documentation diff and run `git diff --check`.
- Do not run application tests because no executable code or runtime data is
  changed.

## Working-Tree Safety

Preserve the pre-existing deletion of `design-qa.md`, the user's uncommitted
Task 18 additions to `v2-files/PLAN.md`, and the untracked
`v2-files/TASK-18-SALES-REPORTING-DASHBOARD.md`. Do not stage or commit.
