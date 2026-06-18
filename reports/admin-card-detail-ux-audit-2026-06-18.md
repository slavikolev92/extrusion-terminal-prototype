# Admin Card Detail UX Audit - 2026-06-18

## Audit Scope

Surface audited: shift-manager/admin card list and card detail page for a completed extrusion card.

Primary page: `/admin/cards/{card_id}`.

Audit mode: combined UX, visual structure, and accessibility-risk review. This was an exploratory pass only; no application code was changed.

Evidence was captured with Playwright against the live FastAPI app on a temporary SQLite database:

- Server: `http://127.0.0.1:8017`
- Temporary DB: `.test-runtime/admin-ux-audit/admin_ux_audit_v2.sqlite3`
- Test card: `UX-AUDIT-60`, completed, machine `2`, sequence `1`
- Test data density: all import fields populated, all recipe actual-material rows populated, tare populated, `60` roll rows, `6` timing segments

Screenshots:

- [01-admin-card-list-completed.png](admin-card-detail-ux-audit-assets/01-admin-card-list-completed.png)
- [02-admin-detail-top.png](admin-card-detail-ux-audit-assets/02-admin-detail-top.png)
- [03-imported-recipe-section.png](admin-card-detail-ux-audit-assets/03-imported-recipe-section.png)
- [04-production-materials-section.png](admin-card-detail-ux-audit-assets/04-production-materials-section.png)
- [05-roll-section-start.png](admin-card-detail-ux-audit-assets/05-roll-section-start.png)
- [06-roll-section-mid.png](admin-card-detail-ux-audit-assets/06-roll-section-mid.png)
- [07-timing-section.png](admin-card-detail-ux-audit-assets/07-timing-section.png)
- [08-system-section.png](admin-card-detail-ux-audit-assets/08-system-section.png)
- [09-mobile-roll-section.png](admin-card-detail-ux-audit-assets/09-mobile-roll-section.png)

Captured DOM metrics:

- Desktop page height: `9506px`
- Mobile page height: `17648px`
- Forms on detail page: `137`
- Buttons on detail page: `137`
- Inputs on detail page: `254`
- Roll correction rows: `60`
- Timing correction rows: `6`
- Repeated `Запази` buttons: `66`
- Repeated `Изтрий` buttons: `66`

## Flow Steps Reviewed

1. Admin completed-card list: usable, but sparse and not a major issue in this pass.
2. Open completed card detail: page loads with status, machine, version, and import fields.
3. Review imported card fields and recipe: editable import fields appear before production corrections.
4. Review machine material corrections: separate editable table for actual materials.
5. Review produced quantity and roll area: summary, tare editing, roll adding, read-only roll table, and per-roll correction forms.
6. Review long roll correction list: 60 repeated rows with individual save/delete controls.
7. Review timing corrections: similar duplicated read-only table plus editable row forms.
8. Review mobile/narrow layout: content stacks, but the detail page becomes very long and some material-table content is clipped.

## Executive Summary

The admin card detail page is functionally powerful but operationally hostile. It exposes every correction mechanism at once, gives all actions similar visual weight, and duplicates the same production data in read-only and editable forms without explaining which representation the shift manager should trust or use.

The roll section is the worst part. A completed card with 60 rolls renders a compact read-only roll table, then immediately renders 60 separate correction rows. Each row has its own `Запази` and `Изтрий` button. This creates a page that looks like an implementation dump rather than a shift-manager correction screen. It is technically editable, but not practically usable.

The current working tree no longer shows the exact stale label reported by the prior audit (`Само преглед в този пакет`) in the screenshot I captured; the current label reads `Корекции на шпула и ролки`. That copy is better, but the underlying UX problem remains: the section is still mixing review, add, edit, delete, summary, and correction workflows in one dense block.

## Strengths

- The page preserves important production data and exposes correction workflows without requiring direct database access.
- The card header gives useful operational anchors: order number, status, machine/sequence, version, and updated timestamp.
- Conflict-safe editing is represented by loaded-version form posts, which fits the pilot's safety model.
- Totals are visible near the roll section: gross total, net total, and roll count.
- The admin card list is simple and gets the user into the card detail page quickly.

## High-Priority Findings

### 1. Roll review and roll correction are duplicated instead of integrated

Evidence: [05-roll-section-start.png](admin-card-detail-ux-audit-assets/05-roll-section-start.png), [06-roll-section-mid.png](admin-card-detail-ux-audit-assets/06-roll-section-mid.png)

The roll section first shows a read-only table with roll number, gross weight, and net weight. Immediately below it, the page shows a second list of the same rolls as editable correction rows. This forces the shift manager to reconcile two representations of the same production data.

Why this is a problem:

- The read-only table is useful for scanning, but the editable list is where action happens.
- The editable list omits net weight, so editing context is worse than the read-only table.
- With many rolls, the shift manager must scroll through duplicate data before reaching later sections.
- It is unclear whether the read-only table is the official record and the correction rows are secondary, or whether the correction rows are the real working surface.

Recommendation:

Replace the two roll representations with one table that supports both review and correction. Columns should be:

- Roll number
- Gross weight editable field
- Net weight read-only calculated field
- Row status or validation message
- Row actions only when the row is actively being edited

Use one section-level `Save roll corrections` action or an explicit `Edit` mode instead of permanent save/delete buttons on every row.

### 2. The page renders 120 roll action buttons for a 60-roll order

Evidence: [06-roll-section-mid.png](admin-card-detail-ux-audit-assets/06-roll-section-mid.png)

The audit card rendered 60 `Запази` buttons and 60 `Изтрий` buttons just for roll rows. These buttons dominate the visual field and make the page feel unsafe.

Why this is a problem:

- A shift manager scanning for one bad roll has to visually parse a wall of identical buttons.
- Delete actions look routine because they repeat on every row with the same weight as save.
- The row number, weight, save, and delete pattern becomes noise after the first few rows.
- Keyboard tab order is likely very poor: every roll adds multiple stops.

Recommendation:

Use progressive disclosure:

- Default state: compact read-only rows.
- Row selected state: show one inline editor for that row.
- Bulk correction mode: allow multiple gross fields to be edited and saved once.
- Destructive delete should be visually secondary and require either a confirmation or a clearly separated danger affordance.

### 3. The roll section mixes five separate jobs in one panel

Evidence: [05-roll-section-start.png](admin-card-detail-ux-audit-assets/05-roll-section-start.png)

The `Ролки` panel currently contains:

- Tare display
- Tare edit
- Add next roll
- Read-only roll table
- Existing roll correction forms
- Existing roll deletion forms

Why this is a problem:

- The shift manager has no clear starting point.
- Routine review and risky correction are visually equivalent.
- Add-roll workflow sits next to completed-roll correction even on a completed card.
- Tare is displayed twice: once as a detail-grid value and once as an editable field.

Recommendation:

Split this into clear subareas:

- `Production totals`: gross, tare, net, roll count, max roll weight comparison.
- `Tare correction`: one compact control, ideally collapsed unless correction is needed.
- `Roll ledger`: one integrated table for review and edits.
- `Add missing roll`: separate secondary action, hidden behind `Add missing roll` for completed cards.

### 4. Completed-card correction mode is always on

Evidence: [02-admin-detail-top.png](admin-card-detail-ux-audit-assets/02-admin-detail-top.png), [05-roll-section-start.png](admin-card-detail-ux-audit-assets/05-roll-section-start.png), [07-timing-section.png](admin-card-detail-ux-audit-assets/07-timing-section.png)

When a shift manager opens a completed card, nearly everything is already editable: import fields, recipe fields, actual material fields, tare, rolls, and timing segments.

Why this is a problem:

- Review and correction are different mental modes.
- A completed card should feel stable by default.
- The page currently increases risk of accidental edits because every field is live.
- The shift manager cannot quickly distinguish imported workbook data from terminal-entered production data and admin correction data.

Recommendation:

Make completed-card detail read-first:

- Default mode: review-only summary with clear sections.
- Section action: `Correct imported fields`, `Correct materials`, `Correct rolls`, `Correct timing`.
- Correction mode: show editable fields only for the chosen section.
- After saving, return to review mode with a visible success/error message.

### 5. The page has no local navigation or section index for a long completed card

Evidence: desktop page height `9506px`, mobile page height `17648px`

A dense completed card is too long for a single uninterrupted document. The user must scroll through import fields, recipe, material corrections, roll rows, timing rows, and system data.

Why this is a problem:

- The shift manager cannot jump directly to rolls or timing.
- The important production sections are buried after imported card fields.
- On mobile or narrow windows, the page becomes effectively unscannable.

Recommendation:

Add a sticky section rail or compact anchor bar:

- Summary
- Imported card
- Materials
- Rolls
- Timing
- System

For completed cards, put production summary and correction history before imported-field editing. Imported data is still important, but it should not dominate the first screen when the task is completed-card review/correction.

## Medium-Priority Findings

### 6. Material information is split across two tables with overlapping meaning

Evidence: [03-imported-recipe-section.png](admin-card-detail-ux-audit-assets/03-imported-recipe-section.png), [04-production-materials-section.png](admin-card-detail-ux-audit-assets/04-production-materials-section.png)

The `Рецепта` section shows planned material fields and read-only actual material hints. The `Материал на машината` section below shows planned material again and editable actual material fields.

Why this is a problem:

- Planned and actual materials are a comparison task, but the page splits comparison and correction into two separate tables.
- `Марка / клас за ред A` appears as a full-width field below the material table, which feels bolted on and visually broken.
- The first recipe table uses editable planned fields and read-only actual fields, while the second uses read-only planned fields and editable actual fields. That pattern is logical to the implementation, but hard to parse quickly.

Recommendation:

Use one material comparison table in review mode:

- Row
- Planned material
- Actual material
- Brand/class where applicable
- Batch/lot

Then provide `Edit planned recipe` and `Edit actual materials` as separate correction actions, not simultaneous always-on tables.

### 7. Timing section repeats the same duplication pattern as rolls

Evidence: [07-timing-section.png](admin-card-detail-ux-audit-assets/07-timing-section.png), [08-system-section.png](admin-card-detail-ux-audit-assets/08-system-section.png)

Timing shows a read-only segment table, then editable segment rows. This is less severe than rolls because there are usually fewer segments, but the structure is the same flawed pattern.

Why this is a problem:

- The user sees each timing segment twice.
- The editable rows lack a clear correction mode.
- Repeated `Запази` / `Изтрий` controls make timing deletion look too casual.

Recommendation:

Use one timing ledger table with inline edit-on-row-selection or a modal/panel editor. Keep `Add segment` as a separate correction action, not an always-visible blank row.

### 8. Primary page ordering is not aligned to completed-card review

Evidence: [02-admin-detail-top.png](admin-card-detail-ux-audit-assets/02-admin-detail-top.png)

The first screen is dominated by imported operational-card fields and a global `Запази корекциите` button. For a completed card, the shift manager likely needs to answer:

- What was produced?
- Was tare entered?
- Are roll totals sane?
- What materials were actually used?
- What timing was recorded?
- Does anything need correction?

The current page starts with workbook/import fields instead.

Recommendation:

For completed cards, reorder the page:

1. Header and status
2. Production summary: gross, net, tare, roll count, timing total, machine, finish timestamp
3. Warnings/anomalies: missing values, over max roll weight, unusual roll count, stale/conflict message
4. Roll ledger
5. Materials planned vs actual
6. Timing ledger
7. Imported card details
8. System data

### 9. Action labels are too generic in repeated contexts

Evidence: repeated buttons in [06-roll-section-mid.png](admin-card-detail-ux-audit-assets/06-roll-section-mid.png) and [07-timing-section.png](admin-card-detail-ux-audit-assets/07-timing-section.png)

`Запази` and `Изтрий` appear dozens of times. The buttons are visually identical across roll and timing contexts.

Recommendation:

Use context-aware accessible labels and/or visible text where space allows:

- `Save roll 17`
- `Delete roll 17`
- `Save segment 2`
- `Delete segment 2`

Visible Bulgarian copy can stay compact, but accessible names should include the row context.

### 10. The admin detail page does not show correction risk clearly

The page allows destructive or audit-sensitive actions: deleting rolls, deleting timing segments, changing imported fields, changing actual materials. These actions are all normal white buttons.

Recommendation:

Introduce action hierarchy:

- Primary: section-level save
- Secondary: edit/cancel
- Destructive: delete, visually distinct and confirmed
- Dangerous workflow actions: cancel/restore card, visually separated from normal navigation

## Lower-Priority Findings

### 11. Header navigation is adequate but does not indicate current admin section

The admin nav repeats `Импорт`, `Планиране`, `Технологични карти`, but the current item is not visually active.

Recommendation:

Add selected styling for the current admin tab.

### 12. The card list is usable but wraps important values awkwardly

Evidence: [01-admin-card-list-completed.png](admin-card-detail-ux-audit-assets/01-admin-card-list-completed.png)

The order number wraps at the hyphen and customer/product values wrap into short lines. This is acceptable for now, but it reduces scan speed.

Recommendation:

Make order number non-wrapping and consider denser table column sizing for the list page.

### 13. Mobile/narrow layout is technically responsive but not usable for this detail page

Evidence: [09-mobile-roll-section.png](admin-card-detail-ux-audit-assets/09-mobile-roll-section.png)

The page stacks, but the material table is horizontally clipped and the page becomes `17648px` tall with the audit data. This may be acceptable if the admin terminal is desktop-only, but the page should still degrade safely.

Recommendation:

Confirm target device for shift-manager/admin use. If desktop-only, optimize for desktop and avoid spending much on mobile polish. If tablet/narrow laptop is possible, the material and roll sections need dedicated responsive layouts.

### 14. System data is useful but too prominent for normal correction work

Evidence: [08-system-section.png](admin-card-detail-ux-audit-assets/08-system-section.png)

System data belongs at the bottom, which is correct, but it could be collapsed by default once the page gains better production summary and correction history.

## Accessibility Risks Visible From Screenshots And DOM

This was not a full WCAG audit. The following are risks visible from screenshots and DOM metrics:

- Excessive keyboard tab stops: `254` inputs/selects/textareas and `137` buttons on one page.
- Repeated button text creates poor screen-reader context unless accessible names include row identity.
- Always-visible destructive actions increase accidental activation risk.
- Mobile/narrow material tables clip content horizontally.
- Page structure is long but lacks local navigation landmarks for major correction areas.
- The page relies heavily on visual grouping; if a user navigates by form controls, the repeated row forms will be hard to understand.

## Recommended Redesign Direction

The right fix is not only changing the stale label. The admin card detail page should become a completed-card review surface with targeted correction tools.

Recommended model:

### Default Completed-Card View

- Read-only by default.
- Top summary: status, machine, version, completed timestamp, gross/net/tare/roll count, timing total.
- Show warnings first: missing tare, missing rolls, unusual totals, roll over max, stale version.
- Use compact ledgers for rolls and timing.
- Show planned vs actual material comparison in one table.

### Correction Mode

- Each section has one correction entry point.
- Only the active correction section becomes editable.
- Save/cancel happens at section level.
- Delete is visually dangerous and confirmed.
- Roll and timing corrections should use one integrated ledger, not duplicate read-only and editable lists.

### Roll Section Candidate Structure

1. Header: `Ролки`
2. Summary strip: roll count, gross total, tare, net total, max roll weight
3. Actions: `Edit rolls`, `Correct tare`, `Add missing roll`
4. Ledger table:
   - `№`
   - `Gross kg`
   - `Tare kg`
   - `Net kg`
   - `Max check`
   - `Updated`
5. In edit mode:
   - Gross fields become editable in the table
   - Net stays calculated/read-only
   - One `Save roll corrections` button
   - One `Cancel` button
   - Row delete appears only from a row action menu or explicit row edit state

## Suggested Fix Backlog

1. Rename stale/misleading roll-section copy wherever it still exists, but treat that as a quick copy fix only.
2. Move completed-card production summary above imported workbook fields.
3. Replace duplicated roll read-only table plus correction rows with one integrated roll ledger.
4. Hide roll correction controls behind `Edit rolls` or section edit mode.
5. Make delete actions visually dangerous and require confirmation.
6. Apply the same pattern to timing segments.
7. Consolidate planned vs actual material display into one comparison table.
8. Add a sticky local section nav for long admin detail pages.
9. Add active state to admin nav tabs.
10. Add accessible names for repeated row actions.
11. Decide whether admin detail must support tablet/mobile; if yes, redesign material/roll tables for narrow widths.
12. Add Playwright coverage for the completed-card admin detail with many rolls, checking page structure and absence of duplicated edit/read-only roll ledgers after redesign.

## Evidence Limits

- The audit used the current working tree, which already contains uncommitted changes in admin/terminal files. Findings describe what rendered from that checkout on 2026-06-18.
- I did not test real operator hardware, printer output, or a production database.
- I did not perform a full keyboard-only pass or screen-reader pass.
- The test data was seeded through backend workflow functions into a temporary database, then visually reviewed through the live rendered app.

