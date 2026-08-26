# V2 Records Archive And Prune Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `v2-files/` an accurate current backlog, archive useful completed records, delete superseded migration/release trackers, and preserve a concise reusable SQLite migration and deployment procedure.

**Architecture:** Separate live status, historical evidence, and reusable operational guidance into `v2-files/`, `v2-files/archive/`, and `docs/implementation-notes/` respectively. Repair repository references so future work follows the playbook and no deleted document remains an apparent current authority.

**Tech Stack:** Markdown, Git, repository-local shell checks.

## Global Constraints

- Preserve the user's existing `v2-files/PLAN.md` and Task 18 work.
- Preserve the unrelated deletion of `design-qa.md`.
- Do not mutate application code, tests, artifacts, or any SQLite database.
- Do not stage or commit.
- Use `apply_patch` for content edits and record moves/deletions.

---

### Task 1: Create The Durable Procedure And Archive Boundary

**Files:**
- Create: `docs/implementation-notes/sqlite-migration-and-deployment-playbook.md`
- Create: `v2-files/archive/README.md`

**Interfaces:**
- Consumes: the proven July 28 migration report, repository backup/deployment documentation, and migration implementation.
- Produces: the active future migration procedure and the archive interpretation rule.

- [x] **Step 1: Write the reusable playbook**

Record the decision classification, safe production-evidence rules, exact successful rehearsal/deployment sequence, preservation checks, rollback rule, and assessment output. State that `app/migrations.py` plus the database's `schema_migrations` table replace the deleted Markdown register as authoritative state.

- [x] **Step 2: Write the archive index**

List each archived record, its completion date/status, why it is retained, and state that `v2-files/PLAN.md` is the only current V2 status source.

- [x] **Step 3: Review both files for stale release-specific instructions**

Run:

```bash
rg -n "NO-GO|Task 8 is pending|Task 9 is pending|M001-M006.*Not run" \
  docs/implementation-notes/sqlite-migration-and-deployment-playbook.md \
  v2-files/archive/README.md
```

Expected: no matches.

### Task 2: Archive Completed Evidence And Specifications

**Files:**
- Archive: `v2-files/archive/MIGRATION-REPORT-2026-07-28.md`
- Archive and update: `v2-files/archive/TASK-01-SHIFT-MANAGEMENT.md`
- Archive and update: `v2-files/archive/TASK-10-ROLL-CHANGE-COUNTDOWN.md`
- Archive and update: `v2-files/archive/TASK-11-REWINDING.md`

**Interfaces:**
- Consumes: completed status and production evidence from the master tracker.
- Produces: clearly labelled historical specifications and an unchanged successful migration report.

- [x] **Step 1: Move the four retained records**

Use `apply_patch` moves so Git records renames rather than unrelated replacement files.

- [x] **Step 2: Correct completed task status headers**

Mark Task 01 and Task 11 completed and deployed. Mark Task 10's core feature completed/deployed while distinguishing its later source-verified threshold follow-up from production deployment.

- [x] **Step 3: Verify the migration evidence survived the move**

Run:

```bash
rg -n "Final decision: GO|95093c080|M001 through|rollback" \
  v2-files/archive/MIGRATION-REPORT-2026-07-28.md
```

Expected: the successful result, deployed revision, migration range, and rollback material remain present.

### Task 3: Prune Superseded Migration And Release Records

**Files:**
- Delete: the former V2 migration instructions/register
- Delete: the superseded release-candidate audit
- Delete: the obsolete release-candidate `NO-GO` verdict

**Interfaces:**
- Consumes: the completed durable playbook and archived final report.
- Produces: removal of contradictory registers, unchecked audit steps, and the obsolete `NO-GO` verdict.

- [x] **Step 1: Confirm their unique durable content is represented**

Compare the files against the playbook and archived report for migration safety, production evidence, and rollback guidance.

- [x] **Step 2: Delete the three superseded records**

Use `apply_patch` deletion. Recovery remains available through Git history.

- [x] **Step 3: Confirm the paths no longer exist**

Run:

```bash
find v2-files -maxdepth 1 -type f -printf '%f\n' | sort
```

Expected: none of the three deleted filenames appears.

### Task 4: Reconcile Current Status And References

**Files:**
- Modify: `v2-files/PLAN.md`
- Modify: `v2-files/TASK-14-RECIPE-CATALOG-PROTOTYPE.md`
- Modify: `v2-files/TASK-15-TERMINAL-ACTION-HEADER.md`
- Modify: `v2-files/TASK-18-SALES-REPORTING-DASHBOARD.md`
- Modify: affected durable notes and historical plans containing moved/deleted paths

**Interfaces:**
- Consumes: the new archive paths, playbook path, current Git revision, and existing user-authored Task 18 text.
- Produces: accurate current status and valid documentation references.

- [x] **Step 1: Update the master tracker**

Preserve Task 18 additions. Record the terminal pallet summary as completed in source with its required compatibility gate, keep `95093c0` as the last confirmed production revision, redirect archived specification/report links, and replace former manual-register references with the playbook.

- [x] **Step 2: Correct deferred and active task references**

Point migration assessments at the playbook. Replace Task 14's obsolete proposed M005 with the rule to use the next version after the then-current code registry.

- [x] **Step 3: Repair repository-wide direct path references**

Redirect completed Task 01/10/11 and migration-report paths to `v2-files/archive/`. Rewrite instructions that name deleted files so they are historical descriptions or point to the playbook; do not make an old implementation plan look current.

- [x] **Step 4: Search for dangling references**

Run:

```bash
rg -n "v2-files/(AGENTS|MIGRATION-REPORT-2026-07-28|RELEASE-CANDIDATE-AUDIT|RELEASE-CANDIDATE-VERDICT|TASK-01-SHIFT-MANAGEMENT|TASK-10-ROLL-CHANGE-COUNTDOWN|TASK-11-REWINDING)\.md"
```

Expected: no references to deleted paths; retained records appear only through `v2-files/archive/...`.

### Task 5: Verify The Documentation Boundary

**Files:**
- Verify: all changed documentation

**Interfaces:**
- Consumes: the complete documentation diff.
- Produces: evidence that the active folder, archive, playbook, and references are consistent.

- [x] **Step 1: List the final V2 root and archive**

Run:

```bash
find v2-files -maxdepth 2 -type f -printf '%P\n' | sort
```

Expected: `PLAN.md` plus Tasks 13/14/15/18 at the root; completed Tasks 01/02/10/11 and the migration report under `archive/`.

- [x] **Step 2: Search active records for superseded status**

Run:

```bash
rg -n "NO-GO|Task 8 is pending|Task 9 is pending|Production.*Not run|Approve the exact M005" \
  v2-files/PLAN.md v2-files/TASK-*.md
```

Expected: no matches.

- [x] **Step 3: Review working-tree scope and formatting**

Run:

```bash
git status --short
git diff --stat
git diff --check
```

Expected: only the approved documentation cleanup plus the user's pre-existing changes; formatting check exits zero.

- [x] **Step 4: Confirm no application verification is required**

Review `git diff --name-only`. If no application, test, script, template, configuration, or database file changed, do not run Python or browser tests.

- [x] **Step 5: Report the result**

List archived, deleted, created, and corrected files; report reference-search and formatting results; explicitly state that no database was touched and nothing was staged or committed.
