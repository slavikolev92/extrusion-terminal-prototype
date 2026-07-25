# Open Issues

## Purpose

This file records issues that occur as part of audits and reviews of the extrusion terminal app. Keep entries concise, actionable, and linked to the report or evidence where the issue was found.

## Issues

### OI-001 - Active machine queue is not normalized after finish/archive

- Status: complete
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

Resolution:

- Fixed during the Full Readiness Audit, 2026-07-02.
- `finish_card()` and `cancel_card()` now normalize the affected active machine queue.
- Restoring a cancelled card now treats the stored sequence as a target insertion position and shifts active cards as needed.
- Regression tests cover finish, cancel, and restore queue normalization.

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

- Status: complete
- Severity: important
- Found in: Structured recipe redesign discussion, 2026-06-24

The shift-manager workbook will keep its current cleaned structure, but
extrusion recipe source cells `AH:AN` will use a structured text convention:

`[Material category]; [Full material name] | [% of total layer]`

Example:

`UV Protection; Additech UV Shield XZ-204 | 2%`

Excel owns category validity. The terminal app validates structure only:
category is required, material name is required, percent is required, percent
must be positive, recipe rows must total exactly `100%`, and `;` is reserved as
the category/material delimiter. The app keeps storing the imported source text,
syncs normalized recipe-component records from that text, and displays category
and material separately in admin/terminal views. Print output intentionally shows
only compact `Material name Percent`, with no category, semicolon, or pipe.

Durable current contract:

- `docs/implementation-notes/structured-recipe-contract.md`

Accepted implementation roadmap:

1. Lock the recipe contract.
   - Confirm accepted text format, delimiter rules, percent decimal rules,
     exact total-percent behavior, target-gross behavior, and Bulgarian UI labels.
   - Record the contract before implementation plans are written.

2. Build the app parser.
   - Add a central Python parser for non-empty `AH:AN` recipe source cells.
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
   - Block release when parsed recipe percentages do not total exactly `100%`.
   - Keep legacy parser fallback only for existing/development stored rows; new
     import/admin source saves must use the semicolon contract.

6. Redesign terminal/admin recipe display.
   - Replace the rigid recipe grid with parsed columns:
     material category, planned raw material, percent, planned kg, actual material
     used, and batch/lot.
   - Calculate planned kilograms as recipe percent multiplied by target gross
     weight.
   - Keep existing actual material and batch/lot save behavior and loaded-version
     conflict checks.

6.5. Align app parser with Excel recipe-builder `N/A` omissions.
   - Superseded by the semicolon contract. Even reusable material rows require
     both category and non-empty material name, for example
     `reLDPE; reLDPE | 80%`.
   - Keep app-side validation limited to the final source-cell structure because
     the app does not import `RecipeCatalog`.
   - Preserve original source text for storage/admin correction, but print
     compact material-plus-percent text.
   - Keep malformed rows, invalid percentages, non-100 totals, and missing target
     gross blocked.

7. Verify with structured sample CSV data.
   - Create several sample orders using the new convention.
   - Verify import, admin review/correction, release, terminal display, actual
     material/batch save, completion behavior, and compact print output.
   - Add automated tests and at least one focused Playwright screenshot for the
     changed UI.

8. Add Excel export macro validation.
   - Update the read-only CSV export macro so it validates selected production
     rows before writing a CSV.
   - Add standalone selected-row validation and configured-range validation from
     `ExportConfig!FirstValidationRow`.
   - Validate `Database!G` as positive gross kilograms for every validated
     production-order row.
   - Validate printing `W:AD` cells against `RecipeCatalogPrinting`; do not add
     printing fields to the extrusion-terminal CSV.
   - Validate extrusion `AH:AN` cells against the structured recipe contract and
     `RecipeCatalogExtrusion`.
   - Validate sales price in `Database!O` as a positive number.
   - Block CSV writing with a clear English row/order/column/value/reason
     message when validation fails.
   - Keep the macro read-only with respect to existing workbook production-order
     cells.

Immediate follow-up after Step 8:

- Address `OI-004` so the app release gate aligns with the workbook/export
  contract that `Database!G` is the only canonical target gross kilograms source.

Resolution:

- Completed across OI-003 Steps 2 through 8, then updated for the final
  semicolon contract.
- The app now parses and stores normalized recipe components, syncs them from
  import/re-import/admin source corrections, gates import/admin saves/release on
  valid structured recipes, and displays structured recipe rows in
  terminal/admin views.
- Category validity is no longer hard-coded in the terminal app; Excel owns
  category validity.
- Print output now shows compact material-plus-percent text.
- Structured sample CSV verification and Playwright screenshots were completed.
- The Excel export validation work was completed before workbook tooling was
  moved out of this repository.
- OI-004 completed the required canonical target-gross follow-up.

### OI-004 - App target gross validation should align to canonical Database column G

- Status: complete
- Severity: important
- Found in: OI-003 Step 8 export-validation design discussion, 2026-06-26
- Must follow: immediately after OI-003 Step 8 Excel export validation
- Evidence:
  - `docs/implementation-notes/oi-003-step-8-export-validation-interim.md`

The OI-003 Step 8 workbook/export validation design now treats `Database!G` as
the canonical target manufacturing weight for every future validated production
order. Column `G` must contain positive gross kilograms. Columns `H`, `I`, and
`J` are not authoritative for this purpose and should be ignored by the export
validator.

The current app release gate still accepts target gross from either `G/H` or
`I/J` when the unit looks kg-like. That broader app behavior was useful earlier,
but it no longer matches the workbook contract needed for controlled export and
future costing.

Recommended fix:

- After OI-003 Step 8 is complete, update app-side release validation and
  planned-kilogram calculations to use only imported `quantity_1`
  (`Database!G`) as positive gross kilograms.
- Stop using `unit_1`, `quantity_2`, or `unit_2` as alternate target gross
  sources.
- Update focused release-validation tests that currently accept `I/J` kg-like
  values.
- Preserve the app's role as a structural/operational safety backstop; do not
  add app-side workbook catalog validation.

Resolution:

- Implemented in OI-004. App release validation, planned kilograms, terminal
  target kilograms, remaining kilograms, and progress percentage now use
  canonical `quantity_1` (`Database!G`) only. `unit_1`, `quantity_2`, and
  `unit_2` remain imported/displayed workbook fields and are ignored for
  target-gross calculations.

### OI-005 - Consolidate workbook helper macro installation

- Status: transferred
- Severity: important
- Found in: workbook macro validation discussion, 2026-06-26
- Must consider after: OI-003 Step 8 Excel export validation
- Evidence:
  - `production-workbook-tooling/interim-costing-process/excel-tools/export-validation/export-validation.bas`
  - `production-workbook-tooling/interim-costing-process/excel-tools/recipe-builder/recipe-builder-installer.bas`

The workbook helper macro workflow currently requires separate installation
paths for the recipe builder and export validation. In practice this is fragile:
the shift-manager should not have to know which helper module installs which
piece of workbook infrastructure, nor remember to run multiple setup macros in
the correct order.

The target workflow should have one installation command for all workbook helper
functionality needed by the pilot workbook. The underlying implementation may
still keep separate VBA modules for recipe-builder behavior, export validation,
and CSV export, but installation should be a single explicit operation that
ensures all required helper sheets, forms, event handlers, and export validation
prerequisites are present.

Recommended fix:

- Design a single workbook-helper installation entry point that installs or
  verifies both recipe-builder support and export-validation support.
- Keep catalog data preservation as a hard requirement; installation must not
  clear, seed, or rewrite reviewed catalog rows.
- Preserve the existing public export macro `ExportSelectedExtrusionOrdersCsv`.
- Avoid duplicate or competing `Database` worksheet event handlers.
- Make installation messages ASCII/English so VBA import/display remains
  reliable across workstations.
- Document one installation workflow for the shift-manager workbook.

Current disposition:

- This is no longer tracked as app work in this repository.
- Production workbook tooling has been moved to a separate repository, so this item should be handled there if still needed.

### OI-006 - Restore Bulgarian workbook runtime messages safely

- Status: transferred
- Severity: important
- Found in: workbook macro validation discussion, 2026-06-26
- Must consider after: OI-005 workbook helper installation consolidation
- Evidence:
  - `production-workbook-tooling/interim-costing-process/excel-tools/export-validation/export-validation.bas`
  - `production-workbook-tooling/tests/test_excel_export_macro_contract.py`

The export-validation macro was temporarily converted to English-only messages
because raw Cyrillic string literals in imported `.bas` files displayed as
mojibake in Excel/VBE. This made validation messages unreadable on the target
workstation even though the validation behavior worked.

Installation/setup messages should remain English/ASCII for reliability and
supportability. Runtime messages that operators or shift managers use during
validation and export should be translated back to Bulgarian, but only with an
encoding-safe implementation that survives `.bas` import.

Recommended fix:

- Keep installation/setup messages in English/ASCII.
- Translate non-installation runtime messages to Bulgarian, including selected
  validation, configured validation, export validation failure, and row-level
  validation errors.
- Do not store raw Cyrillic literals directly in `.bas` source files unless the
  workbook import path is proven to preserve them.
- Use an encoding-safe approach such as `ChrW$`/Unicode helper functions, or a
  generated installer path that writes Unicode text inside Excel reliably.
- Keep static tests that prevent accidental raw Cyrillic in imported `.bas`
  source files until the safe message strategy is implemented and verified.
- Verify messages manually in a copied workbook on the target Excel
  workstation.

Current disposition:

- This is no longer tracked as app work in this repository.
- Production workbook tooling has been moved to a separate repository, so this item should be handled there if still needed.

### OI-007 - Harden optimistic version checks atomically

- Status: open
- Severity: important
- Found in: Full Readiness Audit, 2026-07-02

Most card mutations currently read the card, compare `version`, and then update
by `id`. Normal stale pages are blocked, and SQLite write locking lowers the
practical risk, but the tighter pattern is to make the first state-changing
write atomic with `WHERE id = ? AND version = ?` and check `rowcount`.

Recommended fix:

- Convert the highest-risk mutations first: release, planning/resequence,
  cancel, restore, archive, terminal tare, terminal roll, and terminal material
  writes.
- Use the existing `unrelease_pending_card()` pattern as the model.
- Add stale-write regression tests for each converted flow.

### OI-008 - Resolve remaining multi-form dirty autosave edge case

- Status: open
- Severity: important
- Found in: Full Readiness Audit, 2026-07-02

The new-roll autosave issue and existing-roll correction autosave issue are
fixed. The remaining terminal risk is when recipe fields and the tare field are
both dirty before the operator clicks away; the current client behavior can save
only the first dirty form it sees.

Recommended fix:

- Either block navigation/action with a clear unsaved-changes warning when more
  than one terminal form is dirty, or batch/save all dirty forms before reload.
- Verify with Playwright using dirty recipe plus dirty tare, then attempted
  machine navigation, queue navigation, produced-card navigation, and finish.

### OI-009 - Build unattended production backup system

- Status: open
- Severity: important
- Found in: Full Readiness Audit, 2026-07-02

The app has a SQLite-safe backup/restore helper, but it does not yet have the
production backup system needed for pilot use or future ERP rehearsal. Backups
must not depend on shift-manager/admin clicks. They need to run unattended on a
fixed schedule, be validated, be retained according to an explicit policy, and
support tested recovery drills.

Recommended fix:

- Create an unattended scheduler-owned backup job for the app server.
- Keep using SQLite-safe backup behavior rather than raw file copy.
- Run `PRAGMA integrity_check` on each newly created backup immediately after
  the SQLite backup copy completes.
- Write backup metadata, including status, timestamp, source path, backup path,
  file size, checksum, and validation result.
- Apply an explicit retention policy suitable for pilot use, such as frequent
  short-term backups plus daily longer-term backups.
- Support at least one off-machine/off-disk copy target, or document the chosen
  deployment constraint if off-machine storage is not available yet.
- Provide a no-shift-manager recovery procedure and a tested restore drill using
  scratch databases, including intentional bad-backup/corruption tests.
- Expose backup health in developer/admin diagnostics without requiring anyone
  to manually trigger routine backups.

### OI-010 - Terminal/admin UX and accessibility hardening pass

- Status: open
- Severity: medium/minor
- Found in: Full Readiness Audit, 2026-07-02

The remaining audit UX items are about operator confidence and keyboard/screen
reader behavior rather than core data integrity.

Recommended fix:

- Move focus into queue and produced drawers when they open, trap focus while
  open if appropriate, and restore focus when they close.
- Change the finish confirmation modal so the non-destructive back/cancel action
  receives initial focus, and restore focus after close.
- Improve admin planning validation so row/action errors appear near the affected
  card instead of only as global notices.
- Check admin correction ledgers for per-row accessible labels and keyboard flow.
- Decide whether terminal sync should auto-refresh when no operator input is
  dirty/focused, or keep the manual refresh banner as an accepted limitation and
  document it.
- Verify with focused Playwright keyboard checks and screenshots.

### OI-011 - Build a repeatable Playwright UI test suite

- Status: open
- Severity: medium
- Found in: root tooling review, 2026-07-25

The repository uses Playwright for task-specific browser checks and screenshots,
but it does not have a Playwright configuration or committed browser test files.
As a result, there is no valid repository-wide Playwright test command today.

Recommended follow-up:

- Add a small Playwright configuration and focused browser test suite for the
  highest-value admin and terminal workflows.
- Start and stop the local FastAPI test server deterministically.
- Use only temporary SQLite databases and never the real runtime database.
- Keep screenshots, videos, traces, reports, and browser binaries untracked.
- Run through the repo-local Playwright installation without implicit downloads.
- Update `AGENTS.md` with the suite command only after the suite exists and has
  been verified.
