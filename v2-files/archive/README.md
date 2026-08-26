# V2 Archive

This directory contains completed specifications and point-in-time evidence.
Nothing here is an open task or a current deployment decision.

Use `v2-files/PLAN.md` for current production status, active design work, and
the deferred backlog. Use
`docs/implementation-notes/sqlite-migration-and-deployment-playbook.md` for the
active reusable migration and deployment procedure.

## Retained Records

- `MIGRATION-REPORT-2026-07-28.md` — successful production migration and
  deployment evidence for M001-M006 through production revision `95093c0`.
- `TASK-01-SHIFT-MANAGEMENT.md` — completed and deployed shift-management
  behavior specification.
- `TASK-10-ROLL-CHANGE-COUNTDOWN.md` — completed countdown specification,
  including later source follow-ups whose production status is kept in the
  master tracker.
- `TASK-11-REWINDING.md` — completed and deployed bounded rewinding-return
  behavior specification.
- `TASK-22-TERMINAL-TIMING-CORRECTION.md` — source-complete, reviewed, and
  merged terminal production-time correction; it has not yet been deployed.
- `TASK-02-ADMIN-DESIGN.md` — accepted design record for the completed Admin
  planning cleanup.
- `TASK-02-ADMIN-PLAN.md` — historical implementation plan for that cleanup.
- `TASK-02-STRUCTURE-CLEANUP.md` — historical completion and release-gate
  tracker; its old unchecked boxes are not current work.

Superseded release-candidate audit/verdict files and the former Markdown
migration register were deliberately pruned after their reusable lessons were
captured. Git history remains the recovery path for those deleted records.
