# Open Issues

## Purpose

This file records issues that occur as part of audits and reviews of the extrusion terminal app. Keep entries concise, actionable, and linked to the report or evidence where the issue was found.

## Issues

### OI-001 - Active machine queue is not normalized after finish/archive

- Status: open
- Severity: important
- Found in: Fast Software Audit, 2026-06-24
- Evidence:
  - `reports/fast-audit-20260624.md`
  - `artifacts/ui-checks/fast-audit-20260624/21-admin-planning-after-finish-gap.png`
  - `artifacts/ui-checks/fast-audit-20260624/24-terminal-queue-drawer-after-finish.png`

After order `3118` was completed/archived from Machine 1 sequence `1`, the remaining active order `3117` stayed at sequence `2`. Active machine queues must remain contiguous from `1`.

Recommended fix:

- Add regression tests for queue normalization after finish and cancel.
- Normalize the affected machine queue when a card leaves the active queue through finish, archive, or cancellation paths as appropriate.

### OI-002 - Admin save-all correction has weak visible confirmation

- Status: open
- Severity: minor
- Found in: Fast Software Audit, 2026-06-24
- Evidence:
  - `reports/fast-audit-20260624.md`
  - `artifacts/ui-checks/fast-audit-20260624/18-admin-card-corrections-saved.png`

Admin completed-card corrections persisted correctly, but the captured post-save page did not show an obvious success confirmation near the top of the page.

Recommended follow-up:

- Confirm during the full readiness audit whether a success notice is missing or only displaced by redirect/anchor behavior.
- If missing, add a clear success message for the admin save-all correction flow.
