# Repository Consolidation And Release-Candidate Audit Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to execute this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce one authoritative, verified `main` containing the completed
terminal timing-correction work and machine-production dashboard, while
accounting for every branch, worktree, and outstanding local file.

**Architecture:** Build the consolidated release in an isolated worktree based
on `origin/main`. Apply the two reviewed dashboard commits, reconcile only
evidence-backed outstanding records and tools, and keep the original dirty
checkout unchanged until every local path has a documented disposition. Promote
the result only after full automated, browser, database-safety, and independent
review gates pass.

**Tech Stack:** Git worktrees, FastAPI, direct `sqlite3`, Jinja templates,
pytest, Node.js, repository-local Playwright, and Markdown operational records.

**Spec:** User-approved repository-resolution design in the 2026-08-26 session;
the binding repository scope remains `README.md` and `AGENTS.md`.

## Global Constraints

- Do not mutate the production runtime database during tests or browser checks.
- Do not overwrite, delete, reset, clean, or stash the original dirty checkout.
- Do not silently discard unique commits or untracked files.
- Preserve the completed terminal timing-correction behavior from `origin/main`.
- Preserve the approved dashboard behavior from commits `8d4978f` and `2890685`.
- Treat `README.md` as authoritative when documentation conflicts.
- Every conflict resolution must be reviewed semantically, not selected as a
  whole-file “ours” or “theirs” shortcut.
- New behavior fixes require a failing regression test before production code.
- No Critical or Important review finding may remain unresolved.
- The final source endpoint is one clean local `main` synchronized with
  `origin/main`; production deployment is outside this plan.

---

### Task 1: Establish Evidence And Baseline

**Files:**
- Create: ignored audit reports under `artifacts/repository-consolidation/`
- Create: ignored SDD ledger under `.superpowers/sdd/`
- Modify: none

**Interfaces:**
- Consumes: local/remote refs, registered worktrees, original checkout status.
- Produces: complete branch/ref and dirty-file inventories used by Tasks 3–4.

- [ ] Record the exact local `main`, `origin/main`, merge base, ahead/behind
      counts, worktree registrations, and dirty paths.
- [ ] Audit every branch/ref for commits not reachable from `origin/main`.
- [ ] Audit every dirty path against `origin/main` and the dashboard commits.
- [ ] Run the complete Python suite on untouched `origin/main` in the isolated
      worktree using
      `/home/sk/projects/extrusion-terminal/.venv/bin/python -m pytest -q`.
- [ ] Require exit code `0`; investigate any failure before integration.

### Task 2: Integrate Dashboard And Timing Correction

**Files:**
- Modify only files changed by commits `8d4978f` and `2890685` where their
  changes remain applicable on `origin/main`.
- Test: existing dashboard, terminal timing, admin-route, and verifier tests.

**Interfaces:**
- Consumes: clean `origin/main` baseline and commits `8d4978f`, `2890685`.
- Produces: one branch containing Task 22 plus the approved dashboard.

- [ ] Cherry-pick `8d4978f` and inspect every conflict.
- [ ] Preserve both dashboard routing/layout and timing-correction lifecycle,
      transaction, and UI behavior when resolving overlaps.
- [ ] Run focused dashboard, admin-route, terminal-timing, render, and lifecycle
      tests after the first cherry-pick.
- [ ] Cherry-pick `2890685` and run the roll/pallet verifier safety tests.
- [ ] Run `git diff --check`, Python compile checks, and Node syntax checks.
- [ ] Request a task-scoped integration review and fix every Critical or
      Important finding before Task 3.

### Task 3: Reconcile Outstanding Local Work

**Files:**
- Modify: `v2-files/PLAN.md`, relevant active/archive task records,
  `AGENTS.md`, `README.md`, and evidence-backed operational documentation.
- Add only complete, reviewed source bundles and records whose provenance and
  status are confirmed by the Task 1 audit.

**Interfaces:**
- Consumes: dirty-file audit and consolidated feature history.
- Produces: an accurate tracker and a documented disposition for every original
  dirty path.

- [ ] Classify each dirty path as already integrated, legitimate completed
      work, approved future record, generated/ignored artifact, or obsolete
      duplicate.
- [ ] Compare files that now exist on the integration branch byte-for-byte or
      semantically; do not re-add duplicate timing-correction files.
- [ ] Review and verify the maintenance-display bundle before including it.
- [ ] Consolidate Tasks 6/14 into Task 20 and record Tasks 18–22 and 69 without
      claiming unimplemented work is complete.
- [ ] Update `PLAN.md` through 2026-08-26 with the dashboard and Task 22 marked
      complete in source but not deployed.
- [ ] Record every original dirty path and its final disposition in the audit
      report.
- [ ] Commit coherent documentation/tooling slices separately and review each
      slice before proceeding.

### Task 4: Close Branch And Worktree Ambiguity

**Files:**
- Create/modify: ignored branch-provenance report only.

**Interfaces:**
- Consumes: Task 1 branch audit plus the consolidated branch history.
- Produces: proof that no remaining branch/worktree hides unintegrated required
  application work.

- [ ] Recalculate unique commits for every local and remote-tracking branch
      against the consolidated head.
- [ ] Prove whether each unique commit is integrated, superseded, intentionally
      deferred, or unrelated historical tooling.
- [ ] Preserve refs with unresolved unique work; do not delete them silently.
- [ ] Remove only temporary integration refs/worktrees created by this plan
      after promotion and after verifying they are clean.
- [ ] Report any historical branch that remains and why it is not hidden release
      work.

### Task 5: Comprehensive Combined Verification

**Files:**
- Create: screenshots, traces, logs, and summaries under
  `artifacts/ui-checks/` and `artifacts/repository-consolidation/`.
- Modify: tests and production code only when a reproduced failure requires a
  test-first fix.

**Interfaces:**
- Consumes: complete consolidated source candidate.
- Produces: fresh evidence that the combined candidate is safe and coherent.

- [ ] Run Python compile/import checks and all applicable Node syntax/tests.
- [ ] Run the complete Python suite with exit code `0` and record the exact
      passing count.
- [ ] Run the dashboard date-entry, duration-proportion, productivity-tooltip,
      layout, and responsive-browser checks.
- [ ] Run Task 22's full timing-correction Playwright workflow.
- [ ] Run terminal pallet-summary and roll/pallet browser verifiers at supported
      workstation dimensions.
- [ ] Run a production-backup read-only compatibility audit, with pre/post hash,
      `PRAGMA integrity_check`, and `PRAGMA foreign_key_check` evidence.
- [ ] Confirm browser checks use temporary databases except explicitly
      read-only compatibility checks.
- [ ] Reproduce, diagnose, test-first fix, and re-verify every failure.
- [ ] Run `git diff --check` and confirm no unexpected tracked artifacts.

### Task 6: Independent Review And Promotion

**Files:**
- Modify only files required to resolve final-review findings.

**Interfaces:**
- Consumes: verified consolidated candidate and complete audit reports.
- Produces: one authoritative local and remote `main` and a clean handoff for
  Task 20.

- [ ] Request an independent whole-branch review covering data integrity,
      lifecycle/timing correctness, dashboard read-only behavior, documentation
      truthfulness, and branch/file accounting.
- [ ] Resolve every Critical and Important finding and run one scoped re-review.
- [ ] Repeat the complete verification gates after the final code state.
- [ ] Promote the verified integration head to local `main` without rewriting
      `origin/main` history.
- [ ] Push the resulting fast-forward `main` to `origin/main`.
- [ ] Verify local `main` and `origin/main` resolve to the same commit and report
      zero ahead/behind counts.
- [ ] Remove the temporary integration worktree and branch only after proving
      they contain no uncommitted or unique work.
- [ ] Report the final commit, test/browser/database evidence, remaining
      deferred tasks, retained historical refs, and every integration ruling.
