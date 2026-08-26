# Repository Consolidation — 2026-08-26

This note records the repository-reconciliation decisions made on 2026-08-26.
Retaining a specification or research record is not proof that its behavior is
implemented or deployed. Task 20 is separately approved as the next pilot
implementation, but its initial phase remains unimplemented. This note is
durable status evidence, not deployment authorization. `README.md` remains the
authoritative pilot specification.

## Resulting Source And Production Boundary

- The last confirmed production revision remains `95093c0`.
- Dashboard and Task 22 source were reconciled into the source candidate, but
  neither is deployed. Publishing or merging source is not a production
  deployment.
- The dashboard is read-only: it defaults to the rolling latest 24 hours and
  may show a selectable completed `Europe/Sofia` calendar day. Its approved
  admin navigation order is Импорт → Планиране → Технологични карти → Табло →
  Настройки; older dashboard-first instructions are superseded.
- Task 22 is source-complete and not deployed. Running/paused active-card
  outcomes use its tokenized timing-aware Finish Review; later
  `awaiting_rewinding` finalization keeps a separate tokenless, timing-neutral
  confirmation and leaves the timing ledger and `finished_at` unchanged.
- Task 20 is the next approved pilot feature, but its initial forward-looking
  phase is unimplemented. Historical normalization, notifications,
  inventory/material ownership, and successor-MES work remain later separate
  work.

No cleanup of the original checkout, refs, stash, or other worktrees occurred.
The candidate did intentionally prune the source documents recorded in the
ledger below. No production deployment, workstation copy, installation, reboot,
or live acceptance occurred as part of this reconciliation.

## Original Dirty-Path Ledger

The original checkout had 31 tracked changes and 34 untracked leaf files: 65
paths total. The following grouped lists account for every path and state its
disposition.

### Integrated archive and migration-playbook records

These 32 paths were retained as the archive/playbook reconciliation. They
preserve completed evidence, repair durable references, and replace the former
manual migration register with the active playbook:

- `docs/implementation-notes/excel-csv-import-contract-debug-handoff.md`
- `docs/implementation-notes/rewinding-return-workflow.md`
- `docs/implementation-notes/roll-pallet-assignment.md`
- `docs/implementation-notes/shift-management.md`
- `docs/implementation-notes/sqlite-migration-and-deployment-playbook.md`
- `docs/superpowers/plans/2026-07-25-shift-management.md`
- `docs/superpowers/plans/2026-07-26-rewinding-return-workflow.md`
- `docs/superpowers/plans/2026-07-26-roll-pallet-assignment.md`
- `docs/superpowers/plans/2026-07-26-shift-management-ui-redesign.md`
- `docs/superpowers/plans/2026-07-27-roll-change-countdown.md`
- `docs/superpowers/plans/2026-07-28-scheduled-countdown-and-machine-dot.md`
- `docs/superpowers/plans/2026-07-31-fixed-pallet-print-table.md`
- `docs/superpowers/plans/2026-08-01-roll-change-indicator-thresholds.md`
- `docs/superpowers/plans/2026-08-06-v2-records-archive-prune.md`
- `docs/superpowers/specs/2026-08-01-roll-change-indicator-thresholds-design.md`
- `docs/superpowers/specs/2026-08-06-v2-records-archive-prune-design.md`
- `v2-files/TASK-15-TERMINAL-ACTION-HEADER.md`
- `v2-files/archive/MIGRATION-REPORT-2026-07-28.md`
- `v2-files/archive/README.md`
- `v2-files/archive/TASK-01-SHIFT-MANAGEMENT.md`
- `v2-files/archive/TASK-10-ROLL-CHANGE-COUNTDOWN.md`
- `v2-files/archive/TASK-11-REWINDING.md`
- `v2-files/archive/TASK-02-ADMIN-PLAN.md`
- `v2-files/archive/TASK-02-STRUCTURE-CLEANUP.md`
- deleted `v2-files/AGENTS.md`
- deleted `v2-files/MIGRATION-REPORT-2026-07-28.md`
- deleted `v2-files/RELEASE-CANDIDATE-AUDIT.md`
- deleted `v2-files/RELEASE-CANDIDATE-VERDICT.md`
- deleted `v2-files/TASK-01-SHIFT-MANAGEMENT.md`
- deleted `v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md`
- deleted `v2-files/TASK-11-REWINDING.md`
- deleted `v2-files/TASK-14-RECIPE-CATALOG-PROTOTYPE.md`

Future schema or stored-data-meaning changes use
`docs/implementation-notes/sqlite-migration-and-deployment-playbook.md`.
The code registry and the target database's `schema_migrations` table—not a
Markdown register—are the applied-state evidence. The deleted Task 14
prototype is consolidated into Task 20 and must not be revived as a separate
feature.

### Source-only physical-workstation maintenance bundle

These 16 paths form one source-complete maintenance bundle. They were retained
as source and locally verified only; they were not copied to, installed on,
rebooted, or live-accepted at the physical kiosk:

- `docs/DEPLOYMENT.md`
- `docs/INFRASTRUCTURE_IMPLEMENTATION_PLAN.md`
- `docs/superpowers/plans/2026-08-07-workstation-maintenance-display.md`
- `docs/superpowers/specs/2026-08-07-workstation-maintenance-display-design.md`
- `pyproject.toml`
- `ui-prototypes/gears.png`
- `ui-prototypes/thumb_u.min.webp`
- `v2-files/TASK-19-WORKSTATION-MAINTENANCE-DISPLAY.md`
- `workstation-maintenance/README.md`
- `workstation-maintenance/extrusion-kiosk-maintenance`
- `workstation-maintenance/extrusion-kiosk-session`
- `workstation-maintenance/gears.png`
- `workstation-maintenance/install.sh`
- `workstation-maintenance/maintenance.html`
- `workstation-maintenance/test_workstation_maintenance.py`
- `workstation-maintenance/verify-ui.mjs`

Task 19's August 26 source-integration safety follow-up passed 85 focused
maintenance tests after regular-file and browser-process hardening; Bash,
POSIX-shell, Node, and local-page checks also passed. The repository-wide suite
remains a consolidation final-gate check. The launcher records its active PID,
process start time, and selected browser; before signalling, the controller
verifies current start time, kiosk ownership, command, and executable identity.
Its physical-workstation actions require a separately authorized quiet window
because they replace the launcher, restart Chromium, and require a reboot.

### Retained specifications and non-pilot research

These eight paths were retained as durable context. Their presence is not proof
of implementation or deployment. Task 20 is the exception only in the narrow
sense that its initial forward-looking phase is separately implementation-
approved and next; it is still unimplemented and grants no deployment
authority:

- `v2-files/TASK-18-SALES-REPORTING-DASHBOARD.md` — paused discovery.
- `v2-files/TASK-20-EDITABLE-EXECUTED-RECIPES.md` — next approved feature,
  initial phase unimplemented.
- `v2-files/TASK-21-ORDER-FINISH-REVIEW.md` — residual contextual extension
  only; active running/paused outcomes reuse Task 22's tokenized review, while
  waiting-card finalization remains a separate tokenless, timing-neutral path.
- `docs/superpowers/plans/2026-08-12-editable-executed-recipes.md` — Task 20
  implementation plan.
- `v2-files/TASK-69-MES-SOFTWARE.md` — successor-product research, not pilot
  scope.
- `v2-files/inventory-and-materials/ITEM-MASTER-SKU-DESIGN.md`
- `v2-files/inventory-and-materials/MATERIAL-IDENTITY-AND-CATALOGUE-RESEARCH.md`
- `v2-files/inventory-and-materials/material-identification-research.md`

Task 69 and the material/item records must not authorize pilot implementation,
production-data changes, inventory posting, or deployment.

### Upstream/current timing duplicates

These four original untracked paths were not copied as new work. The current
source already holds the final Task 22 material; the plan and specification
copies were older drafts, while the two prototype assets were byte-identical:

- `docs/superpowers/plans/2026-08-21-terminal-timing-correction.md`
- `docs/superpowers/specs/2026-08-21-terminal-timing-correction-design.md`
- `ui-prototypes/clock-icon.png`
- `ui-prototypes/terminal-timing-correction.html`

### Manual root governance

These three original tracked paths required manual reconciliation rather than
whole-file replacement because the upstream timing/dashboard wording was newer:

- `AGENTS.md`
- `README.md`
- `v2-files/PLAN.md`

The resulting rule is that README is authoritative; AGENTS directs future
stored-data changes to the migration playbook; and the tracker retains Task 22,
the dashboard, Task 19, Tasks 18–21, and Task 69 with their actual source and
deployment status.

### Separate script guidance and design-QA deletion

- `script-instructions.md` is retained by explicit user ruling as root
  operator/agent guidance. It is non-executable and is not deployment or
  migration authority.
- deleted `design-qa.md` remains an intentional deletion: it was point-in-time
  visual-QA material whose screenshot paths are ignored artifacts, not live
  project requirements.

## Provenance And Preservation Evidence

The ignored session audits under `artifacts/repository-consolidation/` recorded
the original branch, dirty-file, and integration-preflight evidence. This note
contains the durable conclusions so those ignored reports are not required to
understand the disposition.

- The original local `main` was ahead of `origin/main` only by the intended
  dashboard/verifier commits. Other named local and remote-tracking feature
  refs had no unique commits relative to `origin/main`.
- The one stash held no unreproduced payload: its tracked/index trees were
  empty and its two untracked-parent files were byte-identical to reachable
  source.
- The detached release-candidate commit `1e138ed` was patch-identical to
  reachable `75e027c`; its worktree's `v2-files/AGENTS.md` edit was a less
  complete duplicate. The admin-planning dirty prototype and its handoff note
  were superseded by the implemented planning work and remain cleanup decisions,
  not integration work.
- The rollback-rehearsal worktree had no unique project commit. The active
  repository-consolidation worktree and its plan were preserved. No branch,
  stash, or non-root worktree was removed or cleaned.
- During the initial Task 3C1 path incident, the original checkout was
  accidentally targeted for nine untracked source documents. All nine were
  restored byte-for-byte to their captured pre-write hashes and independently
  reproduced before work continued; after that point, only absolute worktree
  paths were used.

## Follow-up

Before any later production deployment, follow the migration/deployment
playbook and the documented production procedure in a separately authorized
maintenance window. Before any cleanup, re-audit current refs, worktrees, and
the original checkout; the classifications above are not authorization to
delete them.
