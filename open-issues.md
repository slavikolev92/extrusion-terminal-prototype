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

### OI-003 - Structured extrusion recipe display and export validation

- Status: open
- Severity: important
- Found in: Structured recipe redesign discussion, 2026-06-24

The shift-manager workbook will keep its current structure, but extrusion recipe
source cells `AM:AS` will use a structured text convention:

`[Material category] [Producer] [Grade/Brand] | [% of total layer]`

Example:

`LDPE Rompetrol B20/03 | 80%`

The app should keep storing and printing the imported source text as-is. In
parallel, the app should parse and normalize the recipe rows into clean internal
recipe-component records so the terminal/admin display and future app-side
exports can work from structured data. The print output remains unchanged and
continues to show the original imported source text.

Accepted implementation roadmap:

1. Lock the recipe contract.
   - Confirm approved material categories.
   - Confirm accepted text format, percent decimal rules, total-percent tolerance,
     target-gross behavior, and Bulgarian UI labels.
   - Record the contract before implementation plans are written.

2. Build the app parser.
   - Add a central Python parser for non-empty `AM:AS` recipe source cells.
   - Normalize extra spaces and parse category, planned raw material, and percent.
   - Return clear validation errors for malformed rows.
   - Add focused parser tests before downstream changes.

3. Add normalized recipe storage.
   - Keep original imported source fields on `cards`.
   - Add thin recipe-component storage derived from those fields.
   - Store source field, source text, material category, planned material, and
     recipe percent.
   - Do not add material pricing, inventory, costing, or ERP functionality.

4. Sync normalized rows from source fields.
   - Refresh normalized recipe rows on CSV import, overwrite re-import, and admin
     source recipe correction.
   - Ensure empty source cells remove derived rows and changed source cells update
     derived rows.
   - Preserve existing actual material and batch/lot production data.

5. Add the app release gate.
   - Block release when non-empty recipe rows are malformed.
   - Block release when parsed recipe percentages do not total `100%` within the
     accepted tolerance.
   - Keep imported draft storage permissive enough for admin correction before
     release.

6. Redesign terminal/admin recipe display.
   - Replace the rigid recipe grid with parsed columns:
     material category, planned raw material, percent, planned kg, actual material
     used, and batch/lot.
   - Calculate planned kilograms as recipe percent multiplied by target gross
     weight.
   - Keep existing actual material and batch/lot save behavior and loaded-version
     conflict checks.

7. Verify with structured sample CSV data.
   - Create several sample orders using the new convention.
   - Verify import, admin review/correction, release, terminal display, actual
     material/batch save, completion behavior, and unchanged print output.
   - Add automated tests and at least one focused Playwright screenshot for the
     changed UI.

8. Add Excel export macro validation.
   - Update the read-only CSV export macro so it validates selected rows before
     writing a CSV.
   - Validate non-empty `AM:AS` cells against the same recipe contract used by
     the app.
   - Block export with a clear row/order/column/value/reason message when
     validation fails.
   - Keep the macro read-only with respect to existing workbook cells.
