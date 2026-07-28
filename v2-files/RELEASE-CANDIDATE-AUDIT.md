# Release Candidate Integration Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that the completed extrusion-terminal features work safely together, profile the real production database without changing it, and rehearse the exact migration, deployment, validation, and rollback procedure before production use.

**Architecture:** Verification has two stages. Stage A audits the frozen application candidate against temporary SQLite databases, the complete real-order CSV export, automated tests, live FastAPI/Playwright workflows, print output, restart, re-import, backup, and restore. Stage B profiles an immutable SQLite-safe production backup and runs the entire migration chain on disposable clones, with before/after invariants and a second-run idempotence proof.

**Tech Stack:** Python 3.12, FastAPI, direct `sqlite3`, Pytest, Node.js, Playwright 1.61.0, HTML/CSS print output, SQLite-safe `app.backups` commands.

## Execution Status — 2026-07-28

- Tasks 1-7 and the final verifier-maintenance closure are complete. Stage A
  is `PASS WITH DOCUMENTED NON-BLOCKING LIMITATIONS` on application candidate
  `48fc57b7fd111707b65fa42be07baadb2d48b3c9`.
- Task 8 is pending. It requires a user-supplied immutable SQLite-safe
  production backup and the exact deployed application revision; neither was
  supplied during this audit.
- Task 9 is pending and cannot begin until Task 8 produces the approved M001
  treatment and a fresh production-backup clone.
- Task 10 issued `NO-GO` in `v2-files/RELEASE-CANDIDATE-VERDICT.md`. This does
  not mark Tasks 8-9 complete and does not authorize deployment.

## Global Constraints

- Treat the candidate as frozen during the audit; any functional fix creates a new candidate and requires rerunning the affected checks plus the complete suite.
- Do not mutate `data/extrusion_terminal.sqlite3` or any production/runtime database.
- All writable databases must live under `.test-runtime/release-candidate-audit/`.
- All screenshots, traces, summaries, manifests, and logs must live under `artifacts/ui-checks/release-candidate-audit/`.
- Both runtime directories must remain ignored by Git.
- Use the repo-local `.venv` and `node_modules`; do not install or upgrade dependencies during the audit.
- Use `/home/sk/projects/extrusion-terminal/source-files/extrusion_orders_all_new_after_row_5342_20260727.csv` as the complete current real-order CSV input.
- Preserve exact two-decimal stored weight values even where the UI displays one decimal.
- A production database, backup, customer-level extract, or migration working copy must never be committed.
- The existing M001 production profile remains a deployment gate. M002, M003, and M004 must not infer historical shift, pallet, rewinding, or final-shift values.
- Pallets remain optional; mixed pallet assignment warns consistently but does not block approved completion paths.
- The roll-change countdown remains browser-local and must not alter SQLite, timing, shift, roll, pallet, rewinding, print, or re-import data.
- No push, deployment, production mutation, or release decision is implied by completing Stage A.

---

### Task 1: Freeze And Fingerprint The Candidate

**Files:**
- Read: `README.md`
- Read: `AGENTS.md`
- Read: `v2-files/AGENTS.md`
- Read: `v2-files/PLAN.md`
- Create: `artifacts/ui-checks/release-candidate-audit/candidate-manifest.txt`
- Create: `artifacts/ui-checks/release-candidate-audit/candidate-status.txt`

**Interfaces:**
- Consumes: the completed application tree and all intentional documentation changes.
- Produces: one immutable Git revision when authorized, or a precisely fingerprinted dirty-tree candidate clearly marked non-deployable.

- [ ] **Step 1: Record repository identity and dirty state**

  Run:

  ```bash
  git rev-parse HEAD
  git branch --show-current
  git status --short
  git diff --stat
  git diff --check
  ```

  Expected: branch `main`; `git diff --check` exits `0`; every uncommitted path is intentional and named in the evidence.

- [ ] **Step 2: Record a candidate content fingerprint**

  Record the HEAD, tracked diff hash, untracked source/document hashes, Python version, SQLite version, Node version, and Playwright version in `candidate-manifest.txt`.

  Expected: the manifest distinguishes the complete candidate from commit `c6b68ff` while the roll-change countdown remains uncommitted.

- [ ] **Step 3: Enforce the release-freeze gate**

  Do not commit without explicit user authorization. Stage A may audit a fingerprinted dirty tree, but Stage B and production deployment require a committed candidate revision and a clean code worktree.

---

### Task 2: Run Static, Automated, And Migration Baselines

**Files:**
- Read: `tests/`
- Read: `tests/js/roll_change_countdown_core.test.mjs`
- Read: `app/migrations.py`
- Test: complete Python and Node test collections
- Create: `artifacts/ui-checks/release-candidate-audit/automated-verification.txt`

**Interfaces:**
- Consumes: Task 1 candidate fingerprint.
- Produces: exact syntax, test, migration, and diff-check results for that fingerprint.

- [ ] **Step 1: Verify Python syntax and imports**

  ```bash
  source .venv/bin/activate
  python -m compileall -q app scripts tests
  ```

  Expected: exit `0` with no output.

- [ ] **Step 2: Verify JavaScript syntax and countdown logic**

  ```bash
  node --check app/static/js/roll_change_countdown.mjs
  node --check app/static/js/roll_change_countdown_core.mjs
  node --check scripts/verify_roll_change_countdown_ui.mjs
  node --test tests/js/roll_change_countdown_core.test.mjs
  ```

  Expected: every syntax check exits `0`; all Node tests pass.

- [ ] **Step 3: Run the migration matrix**

  ```bash
  source .venv/bin/activate
  python -m pytest tests/test_migrations.py -q
  ```

  Expected: all fresh, legacy, partial, malformed, idempotence, integrity, foreign-key, preservation, and rollback cases pass on temporary databases.

- [ ] **Step 4: Run the complete Python suite**

  ```bash
  source .venv/bin/activate
  python -m pytest -q
  ```

  Expected: zero failures or errors.

- [ ] **Step 5: Verify tracked formatting**

  ```bash
  git diff --check
  ```

  Expected: exit `0`.

---

### Task 3: Audit Cross-Feature Coverage Adversarially

**Files:**
- Read: all files under `tests/`
- Read: all verification scripts under `scripts/`
- Read: `docs/implementation-notes/`
- Create: `artifacts/ui-checks/release-candidate-audit/coverage-matrix.md`

**Interfaces:**
- Consumes: completed feature specifications and automated test inventory.
- Produces: a requirement-to-test matrix and an explicit list of interaction gaps that require live rehearsal or new regression tests.

- [ ] **Step 1: Map every completed feature to tests**

  The matrix must include import/re-import, Admin planning, shift lifecycle, timing, roll entry/correction/deletion, tare, pallets, rewinding, produced orders, print, countdown isolation, backup/restore, restart, stale writes, and queue normalization.

- [ ] **Step 2: Map cross-feature interactions**

  Require evidence for at least these combinations:

  ```text
  active shift + start/pause/resume + one-running-card-per-machine
  roll defaults + exact weights + pallet snapshots + per-row correction
  running/paused finish + rewinding marker + queue normalization
  waiting finalization + late rolls + stored final shift
  mixed pallets + normal completion + end-to-wait + waiting finalization
  re-import + rolls + timing + shifts + pallets + rewinding fields
  countdown + pause/resume + card replacement + zero SQLite mutation
  completed correction + produced-order sorting + print eligibility/output
  backup + restore + restart + all persisted production fields
  stale versions + every mutating Admin/Terminal route used in rehearsal
  ```

- [ ] **Step 3: Classify gaps**

  Each gap must be classified as `automated test required`, `live-browser evidence required`, `production-snapshot evidence required`, or `accepted out of scope`. No unexplained gap may reach the release verdict.

---

### Task 4: Import And Inspect The Complete Real-Order CSV

**Files:**
- Read: `source-files/extrusion_orders_all_new_after_row_5342_20260727.csv`
- Read: `app/importer.py`
- Create: `.test-runtime/release-candidate-audit/real-orders.sqlite3`
- Create: `artifacts/ui-checks/release-candidate-audit/real-order-import.json`

**Interfaces:**
- Consumes: the exact current Shift Manager CSV export and a fresh M001-M005 schema.
- Produces: complete import counts, skipped/error categories, order/card invariants, and a reusable disposable database for lifecycle rehearsal.

- [ ] **Step 1: Fingerprint the CSV**

  Record byte size, SHA-256, header names, data-row count, and duplicate order-number count.

- [ ] **Step 2: Initialize a fresh temporary database**

  Set both `EXTRUSION_DB_PATH` and `EXTRUSION_DATA_DIR` under `.test-runtime/release-candidate-audit/`, run `app.db.init_db()`, and confirm migrations `(1, 2, 3, 4, 5)` are recorded once.

- [ ] **Step 3: Import every CSV row**

  Use the production importer rather than direct card inserts. Record imported, skipped, duplicate, no-extrusion, and error counts.

- [ ] **Step 4: Sweep every imported card**

  Verify unique order numbers, recognized statuses, import-source presence, recipe parsing reachability, nullable production fields, and successful Admin/Terminal detail-context construction without customer-level data in tracked evidence.

- [ ] **Step 5: Repeat safe re-import**

  Prove skip-by-default leaves the database unchanged. Later, after lifecycle data exists, prove overwrite re-import changes imported fields only and preserves every production field.

---

### Task 5: Run The Combined Lifecycle Rehearsal

**Files:**
- Use: `.test-runtime/release-candidate-audit/real-orders.sqlite3`
- Create: `.test-runtime/release-candidate-audit/combined-workflow.mjs`
- Create: `artifacts/ui-checks/release-candidate-audit/combined-workflow-summary.json`
- Create: `artifacts/ui-checks/release-candidate-audit/screenshots/`

**Interfaces:**
- Consumes: Task 4 real-order database and the isolated live FastAPI app on `127.0.0.1:8011`. Port `8000` belongs to an external in-progress development session and must not be interrupted or reused by this audit.
- Produces: one end-to-end browser/database proof that the completed features interact correctly.

- [ ] **Step 1: Select representative real cards**

  Select at least eight distinct imported cards without recording customer/order details in tracked evidence. Cover all four machines, two shift occurrences, normal completion, running end-to-wait, paused end-to-wait, every-roll-rewinding, waiting finalization, and completed-card late roll correction.

- [ ] **Step 2: Exercise Admin planning**

  Release, insert, resequence, replan, and return only eligible unstarted cards. Verify contiguous queues, one running card per machine, protected data-bearing cards, and stale-version rejection.

- [ ] **Step 3: Exercise shifts and timing**

  Open shift 1; start/pause/resume cards; prove terminal mutations require an active shift; finish shift 1; open shift 2; verify roll attribution and final-shift rules across the boundary.

- [ ] **Step 4: Exercise roll, tare, and pallet interactions**

  Enter exact two-decimal gross/tare values, clear and replace defaults, add pallet and no-pallet rolls, edit one row at a time, confirm deletion, and verify displayed one-decimal formatting never changes stored precision.

- [ ] **Step 5: Exercise all completion paths**

  Complete normally, end running and paused cards into `awaiting_rewinding`, verify mixed-pallet warnings consistently, add split/merged returned rolls without count matching, and deliberately finalize waiting cards through `Приключи`.

- [ ] **Step 6: Exercise produced-order recovery and print rules**

  Add a forgotten late roll to a completed card, verify stored/fallback shift attribution, newest-first produced ordering, print eligibility only for completed/archived cards, and grouped pallet totals including `Без палет`.

- [ ] **Step 7: Exercise countdown isolation**

  Create and edit a countdown on a running card, pause/resume it, acknowledge a change, verify cross-tab synchronization, finish/replace the card, and prove the schedule does not transfer. Compare SQLite before/after countdown-only operations byte-for-byte or through a complete logical dump.

- [ ] **Step 8: Verify both supported viewports**

  At `1920x768` and `1366x768`, capture the Admin plan, active Terminal card, countdown editor, rewinding pane, waiting-card detail, produced-orders pane, row editor, mixed warning, and print output. Require zero console errors, page errors, horizontal overflow, clipping, or actionable-control overlap.

---

### Task 6: Re-import, Restart, Backup, Restore, And Print

**Files:**
- Use: `.test-runtime/release-candidate-audit/real-orders.sqlite3`
- Create: `.test-runtime/release-candidate-audit/backups/`
- Create: `artifacts/ui-checks/release-candidate-audit/persistence-summary.json`

**Interfaces:**
- Consumes: the mutated Task 5 rehearsal database.
- Produces: persistence and recoverability evidence for the complete workflow state.

- [ ] **Step 1: Capture production-data invariants**

  Record aggregate counts/hashes for cards by status/machine, queues, shifts, rolls and weights, pallets, rewinding fields, timing segments, recipe actuals/components, import sources, and schema migrations.

- [ ] **Step 2: Overwrite re-import the complete CSV**

  Prove imported/front-card fields follow the current CSV while all terminal-entered production invariants remain unchanged.

- [ ] **Step 3: Restart the application**

  Stop and restart FastAPI against the same temporary database. Verify `/health`, `/admin`, `/terminal`, waiting cards, produced cards, shifts, and completed-card print output.

- [ ] **Step 4: Create a SQLite-safe backup**

  ```bash
  source .venv/bin/activate
  python -m app.backups backup \
    --source .test-runtime/release-candidate-audit/real-orders.sqlite3 \
    --backup-dir .test-runtime/release-candidate-audit/backups \
    --keep 10
  ```

  Expected: backup and metadata are created successfully without a raw live-file copy.

- [ ] **Step 5: Restore into a new path**

  Restore to `.test-runtime/release-candidate-audit/restored.sqlite3`, never over the source rehearsal database.

- [ ] **Step 6: Compare restored invariants**

  Require matching logical invariants, `PRAGMA integrity_check == 'ok'`, empty `PRAGMA foreign_key_check`, identical migration history, successful repeated `init_db()`, and passing health/Admin/Terminal/print smoke checks.

---

### Task 7: Whole-Candidate Adversarial Review And Fix Gate

**Files:**
- Read: candidate diff from the last deployed/accepted base through the Task 1 fingerprint.
- Create: `artifacts/ui-checks/release-candidate-audit/adversarial-review.md`
- Modify only if defects are confirmed: affected app/test/documentation files

**Interfaces:**
- Consumes: Tasks 1-6 evidence and complete candidate code.
- Produces: severity-ranked findings, rulings, fixes, regression tests, and a Stage A verdict.

- [ ] **Step 1: Review data integrity and transaction boundaries**

  Inspect every cross-feature write for active-shift gating, optimistic version checks, `BEGIN IMMEDIATE` placement, queue normalization, all-or-nothing roll/default writes, and migration/import preservation.

- [ ] **Step 2: Review lifecycle reachability**

  Prove each status has only approved incoming/outgoing transitions and that waiting cards cannot accidentally start, pause, resume, cancel, archive, delete, print, or re-enter an active queue.

- [ ] **Step 3: Review UI and client-only state isolation**

  Inspect form omission/blank semantics, one-row editor behavior, warnings, disabled/hidden controls, countdown local-storage keys, card-version boundaries, and tab synchronization.

- [ ] **Step 4: Apply the defect gate**

  Any confirmed defect requires a failing regression test, minimal fix, focused checks, complete suite, live-browser recheck where applicable, migration reassessment, and a new candidate fingerprint. Do not waive major or data-integrity findings.

- [ ] **Step 5: Issue the Stage A verdict**

  Verdict must be exactly `PASS`, `PASS WITH DOCUMENTED NON-BLOCKING LIMITATIONS`, or `FAIL`. A pass is required before requesting the final production backup for migration rehearsal.

---

### Task 8: Profile The Immutable Production Backup

**Files:**
- Read only: user-supplied SQLite-safe production backup
- Create: ignored clone under `.test-runtime/release-candidate-audit/production-profile/`
- Modify: `v2-files/AGENTS.md`
- Create: `artifacts/ui-checks/release-candidate-audit/production-profile-summary.json`

**Interfaces:**
- Consumes: a SQLite-safe immutable production backup and its deployed application revision.
- Produces: the M001 legacy-data decision without customer-level tracked output.

- [ ] **Step 1: Stop if no safe backup is supplied**

  A live runtime database or raw copy made while the app could write is not acceptable evidence.

- [ ] **Step 2: Fingerprint immutable evidence**

  Record source timestamp, deployed revision, file size, SHA-256, SQLite version, integrity, foreign keys, recorded migrations, and high-level row counts.

- [ ] **Step 3: Clone and profile only the clone**

  Count statuses, assignments, queues, rolls, weights, timing, actuals, import sources, legacy unit spellings, quantity-less units, unitless quantities, existing final destinations, and card/source disagreements.

- [ ] **Step 4: Decide the M001 data treatment**

  If every category maps provably and a data migration is required, specify the
  next available migration (currently M006) with a literal deterministic
  mapping and obtain user approval before implementation. If no data migration
  is required, record that decision explicitly. If any category is ambiguous,
  leave values unchanged and define counted manual-remediation categories.

- [ ] **Step 5: Append migration maintenance evidence**

  Update the migration register and assessment log in `v2-files/AGENTS.md` without customer names, order details, or the database itself.

---

### Task 9: Rehearse The Full Production Migration And Rollback

**Files:**
- Use: a fresh clone of the immutable production backup
- Create: `artifacts/ui-checks/release-candidate-audit/migration-rehearsal-summary.json`
- Create: `v2-files/PRODUCTION-DEPLOYMENT-RUNBOOK.md`

**Interfaces:**
- Consumes: frozen committed executable candidate, the approved M001 treatment
  decision (no new migration or an approved next migration, currently M006),
  and a fresh production backup clone.
- Produces: observed migration timing, invariant comparison, smoke results, repeat-run proof, and exact deployment/rollback commands.

- [ ] **Step 1: Capture pre-migration invariants**

  Record the same aggregate schema/data invariants used in Tasks 6 and 8.

- [ ] **Step 2: Run the complete initialization/migration chain**

  Run M001-M005 when Task 8 approves no new migration, or run through M006 if
  Task 8 approves and implements that next migration. Record applied versions,
  duration, logs, exit status, integrity, and foreign-key results. Require only
  approved schema/value transformations.

- [ ] **Step 3: Run production-clone smoke workflows**

  Verify `/health`, `/admin`, `/terminal`, representative active/completed cards, shifts, rewinding visibility, countdown isolation, corrections, and completed-card printing.

- [ ] **Step 4: Prove second-run idempotence**

  Run initialization again and require no new migration record or data/schema change.

- [ ] **Step 5: Rehearse rollback**

  Restore the pre-migration backup into a separate path, start the previous application revision, and verify health/Admin/Terminal/representative cards/print before documenting observed recovery time.

- [ ] **Step 6: Write the deployment runbook**

  Include maintenance-window approval, stop, SQLite-safe backup/fingerprint, deploy exact commit, migrate, validate, reopen, and rollback commands using the observed paths and timings.

---

### Task 10: Final Go/No-Go Review

**Files:**
- Read: all Task 1-9 evidence
- Create: `v2-files/RELEASE-CANDIDATE-VERDICT.md`

**Interfaces:**
- Consumes: complete Stage A and Stage B evidence.
- Produces: one explicit production deployment recommendation.

- [ ] **Step 1: Verify every gate**

  Require a committed candidate, clean code tree, complete green suites, Stage A pass, production profile decision, migration rehearsal pass, idempotence, integrity, foreign keys, live smoke checks, backup/restore proof, and rollback proof.

- [ ] **Step 2: List all limitations and rulings**

  Every deferred or non-blocking finding must have a named owner, operational consequence, and explicit deployment ruling. No unresolved data-integrity finding may be accepted.

- [ ] **Step 3: Issue the verdict**

  Verdict must be exactly `GO` or `NO-GO`. Deployment remains a separate user-authorized operation even after `GO`.
