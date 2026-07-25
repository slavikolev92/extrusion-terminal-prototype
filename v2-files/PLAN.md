# Weekend Update Plan

This is the single master tracker for the extrusion-terminal work planned for
July 25-26, 2026. The user can ask an agent to read this file and recommend the
next task. Keep it at workstream/status level rather than turning it into a
detailed implementation plan.

When a workstream starts, explore it with the user and create a temporary task
tracker only if needed. Delete that temporary tracker after the workstream is
complete. Persist the completed status and any remaining work here.

Current priority: finish the Shift Manager downstream cleanup caused by the
V14.04 export/import contract change. The strict import/storage correction and
schema-only M001 are complete; admin, terminal, documentation, print, final
verification, and production migration preparation remain.

Next recommended task: make the admin import results, planning queues, cards
list, and card detail consistently show the final imported fields.

The original production-tracking workstreams are:

1. Shift management for extrusion production.
2. Roll packaging / pallet tracking with label printing.

Repository-root `README.md` remains the authoritative project specification
until confirmed behavior is merged into it.

## Confirmed Direction

- There is one active extrusion shift at a time across all four machines.
- The terminal should not allow production roll entry unless an active shift is selected/open.
- Shift tracking starts simple: shift number, people count, timestamps, and optional notes.
- Named worker assignment is future functionality, not required for the first shift-management slice.
- The data model should allow future worker/crew import, for example from an Excel roster, without rewriting roll production history.
- Each new roll should persist the shift that produced it.
- Existing roll data must be migrated safely. Old rolls should not receive guessed shift assignments unless the user explicitly approves an approximate backfill.
- Packaging/pallet tracking is separate from shift tracking. A shift produces rolls; a package/pallet groups rolls for transport and label printing.
- Pallet labels should summarize the rolls included, including roll count, gross weight, and net weight.

## Workstream 1: Shift Management

Recommended first project.

### Goal

Persist shift sessions and attach newly entered rolls to the active shift so the app can report production by shift number and later connect shifts to people.

### Current Planning Stage

Shift management is still being defined. Do not treat the implementation sequence as final until the shift workflow, validation rules, reporting expectations, and migration rules are confirmed.

The next work is discussion/design, not coding:

- define the full terminal shift workflow.
- define what is blocked when no shift is open.
- define how shift start/end reminders should behave.
- define what shift summary/reporting should show.
- define what admin correction should allow.
- define how existing roll data should be represented after the feature exists.

Only after that should implementation be split into slices. Migration is not a standalone business project and should not run before the shift-management feature is designed. It is a safety part of the eventual implementation because the database must be upgraded without damaging existing rolls.

### Initial Data Shape

```text
production_shifts
- id
- operation
- shift_number
- started_at
- ended_at
- people_count
- crew_note
- source
- status
- created_at
- updated_at
```

```text
roll_entries additions
- shift_id
- produced_at
```

### Future Extension Placeholder

Named workers can be added later without changing how rolls attach to shifts:

```text
workers
shift_workers
```

Potential future import path:

- Import a roster/crew Excel or CSV file.
- Match roster rows to shift sessions by operation, shift number, and date/time.
- Populate shift worker assignments after production has already been recorded.

## Workstream 2: Roll Packaging / Pallet Tracking

Recommended second project, after shift management is stable.

### Goal

Group produced rolls into packages or pallets and generate printable labels for transport and handling.

### Suggested Feature Slices

1. Packaging data foundation
   - Add packages/pallets.
   - Add package-to-roll assignment.
   - Prevent one roll from being assigned to more than one active package.

2. Packaging workflow
   - Let users select produced rolls and create a pallet/package.
   - Show totals for selected rolls before saving.
   - Allow package correction before label printing.

3. Label printing
   - Add a package label print route.
   - Label should show package number, roll count, gross total, net total, order/product details, and included roll numbers.
   - Keep this separate from the operational-card print route.

4. Packaging history and correction
   - Add package index and package detail.
   - Allow voiding/replacing bad package labels without deleting production roll history.

### Initial Data Shape

```text
packages
- id
- package_number
- package_type
- operation
- status
- created_at
- updated_at
```

```text
package_rolls
- package_id
- roll_entry_id
```

## Migration Safety Notes

- Migration belongs to the shift-management implementation after the shift feature is designed.
- Do not migrate the real runtime database before the shift-management behavior is confirmed and tested.
- Before any schema migration against a real runtime database, create a SQLite-safe backup.
- Automated tests should use temporary SQLite databases only.
- Existing production roll data should remain valid after migration.
- Existing roll rows should keep their gross, tare, net, card, order number, and roll number values unchanged.
- Unknown historical shift assignment is better than guessed historical shift assignment.
- If approximate historical assignment is later desired, it should be a separate explicit admin/backfill action with clear labeling.

## Original Production-Tracking Sequence

This sequence applied when the only recorded workstreams were shift management and packaging. The Sunday review backlog below may reprioritize smaller correctness and usability fixes ahead of these larger workstreams.

1. Focus only on shift management.
2. Discuss and confirm the full shift-management behavior.
3. Decide the implementation split after the behavior is known.
4. Write a focused shift-management spec.
5. Implement shift management with a safe database upgrade as part of that work.
6. Verify old data preservation, new roll shift assignment, terminal behavior, reminders, and admin review/correction.
7. Only after shift management is accepted, return to packaging/pallet tracking.

## Open Questions

- What are the exact expected shift windows for shift numbers 1 through 4?
- Should starting a shift allow manual start time entry, or always use the current server time with admin correction later?
- Should ending a shift allow manual end time entry, or always use the current server time with admin correction later?
- Should roll entry be blocked entirely when no shift is open, or should admin be able to add/correct rolls without an active shift?
- Should pallet/package creation happen from `/terminal`, `/admin`, or both?

## Near-Term Backlog For Sunday Review

Target completion/review date: Sunday, July 26, 2026.

This list combines the two existing production-tracking workstreams with the newly observed admin and terminal tasks. It is intentionally grouped by affected surface and rough complexity so implementation can be sequenced without mixing small UI fixes with larger workflow redesigns.

### Admin / Shift-Manager Panel

1. **Shift management for extrusion production**
   - Surface: `/terminal`, `/admin`, database.
   - Complexity: large.
   - Goal: create one active extrusion shift at a time, require/open shift context for new production roll entry, and attach every new roll to the shift that produced it.
   - Needs design: shift start/end workflow, no-open-shift blocking rules, reminders, summary reporting, admin correction, and safe handling of existing rolls with unknown historical shift.

2. **Fix technology-card quantity fields to match the new Shift Manager export**
   - Surface: CSV/export import, database fields, admin technology-card edit screen, terminal details.
   - Complexity: medium.
   - Status: strict V14.04 import/storage correction and schema-only M001 are
     complete; downstream admin, terminal, documentation, and print cleanup
     remain in progress.
   - Goal: remove the old ambiguous unit/unit-of-measure display model from the app screens and align the imported/displayed fields one-to-one with the current structured export.
   - Final structured quantity fields: `ordered_gross_kg`, `ordered_rolls`, `ordered_meters`, and `ordered_units`.
   - First visible behavior: show the gross amount clearly as gross kilograms instead of a generic `amount` field.
   - Data behavior: still import/store the other structured ordered amounts even if only gross kilograms are shown to workers initially.
   - Fixed rule: old CSV headers are dead; do not restore compatibility or copy old quantity/unit pairs positionally into the final fields.

3. **Import and display missing Shift Manager production-detail fields**
   - Surface: Shift Manager export file, import parser, database, admin technology-card edit screen, terminal details.
   - Complexity: medium.
   - Status: final V14.04 import/storage fields are implemented; downstream
     display cleanup remains in progress.
   - Goal: make the app carry and show all important production-card information from the Shift Manager file, not only the fields currently visible.
   - Current fields include delivery, four route sequence values, next operation, folding/gusseting, treatment, recipe materials, and packaging method.
   - Fixed rule: do not add `micro_perforation`; it is not part of the final contract.
   - Display behavior: these fields should appear in the relevant details section of the main app and technology-card editing screen.

4. **Redesign Shift Manager import workflow**
   - Surface: `/admin` import area, export/import file process, validation UX.
   - Complexity: large.
   - Goal: make import simple enough that the Shift Manager export lands in a known folder and the app can import from that predictable location with minimal clicking.
   - Desired direction: remove or replace the low-value `last imports` section, improve validation review, and make conflict handling happen after import analysis rather than through a pre-selected overwrite checkbox.
   - Data rule direction: the Shift Manager workbook/export is the canonical source for imported/front-card fields, while app-entered production data must still be preserved.
   - Needs design: exact folder handoff, file selection rules, conflict categories, automatic overwrite rules, skip rules, and how production-data-preserving overwrite is explained to the user.

5. **Redesign admin planning and machine sequencing**
   - Surface: `/admin` planning/release screen.
   - Complexity: large.
   - Goal: make machine assignment and sequencing manageable when one machine has many orders.
   - Problem: current cards are too large and the planning page becomes difficult to use when machine queues are long, especially for machine 1.
   - Needs design: compact rows vs cards, drag/resequence or explicit sequence editing, machine grouping, filtering, conflict handling, and fast review/release actions.

### Terminal / Workstation

6. **Worker recipe edit functionality**
   - Surface: `/terminal`, `/admin`, database, possible inventory import/reference data.
   - Complexity: large.
   - Goal: allow workers to record the actual recipe/materials used when ad hoc material changes happen during production.
   - Desired behavior: workers can choose materials from inventory-like dropdowns, edit non-calculated recipe fields such as material selection and percentages, and use a free-form material entry only when the material cannot be found.
   - Admin visibility: changed recipe/materials must be clearly brought to Shift Manager attention. Free-form material names must be especially visible because they may not match costing/inventory items.
   - Needs design: inventory source, dropdown grouping to mimic the inventory worksheet, which recipe fields are editable, whether new material categories can be added, audit/history behavior, and how the Shift Manager acknowledges reviewed changes without pretending to approve or reject already-used material.

7. **Add calculator access from the workstation**
   - Surface: `/terminal`, workstation VM/browser environment.
   - Complexity: small to medium.
   - Status: deferred / pending; not part of the current quick-fix slice.
   - Goal: provide quick calculator access for operators.
   - Possible approaches: link/button to a browser-based calculator inside the app, open the Linux desktop calculator from the kiosk environment, or rely on an existing OS shortcut if available.
   - Needs validation: whether the kiosk browser is allowed to launch a native Linux calculator. If not, an in-app calculator is likely simpler and more reliable.

8. **Show one decimal place in weight totals**
   - Surface: `/terminal` totals display, possibly admin card details/print if the same formatter is reused.
   - Complexity: small.
   - Status: done in local commit `97c6ce5`.
   - Goal: display gross total, remaining gross amount, and net total with one decimal place using standard rounding.
   - Verified behavior: only the bottom-right workstation totals changed; underlying stored values, machine KPI quantities, roll rows, admin totals, and print output were left unchanged.

9. **Sort produced cards by produced/finished date descending**
   - Surface: `/terminal` produced-cards popup/drawer.
   - Complexity: small.
   - Status: done in local commit `97c6ce5`.
   - Goal: show the latest produced cards first.
   - Sort key: finished/completed timestamp descending.
   - Verified behavior: produced cards with a finish timestamp sort newest first; cards without a finish timestamp fall after dated cards with deterministic fallback ordering.

10. **Roll change pace / countdown timer**
   - Surface: `/terminal` machine KPI cards, active card detail, database.
   - Complexity: large.
   - Goal: help workers track when wound rolls should be changed during active production, including cases where one machine runs multiple roll tracks from slitting/sleeve/flat-sheet setups.
   - Desired behavior: workers set a roll-change pace such as 2 hours 30 minutes and click when a roll starts winding or has just been changed. The app then shows a countdown and a visual cue when the next change is due.
   - Display direction: countdown status should be visible on the machine KPI/navigation cards so workers can see which machine needs attention.
   - Needs design: whether the timer is per card, machine, roll track, or multiple tracks; how many simultaneous tracks are supported; what happens on pause/resume/finish; how reminders appear; whether missed changes are recorded; and how this interacts with actual roll gross-weight entry.

### Packaging / Pallets

11. **Roll packaging / pallet tracking with label printing**
   - Surface: `/terminal` and/or `/admin`, database, print route.
   - Complexity: large.
   - Goal: group produced rolls into packages/pallets and generate printable transport labels.
   - Desired behavior: select produced rolls, create a package/pallet, prevent one roll from being assigned to more than one active package, show package totals, print labels, and allow voiding/replacing bad labels without deleting production roll history.
   - Needs design: whether packaging happens from `/terminal`, `/admin`, or both; package numbering; package type names; correction workflow; and label format.

## Suggested Implementation Order

1. Complete the active Shift Manager downstream cleanup and release-safety work.
2. Re-evaluate this backlog after the V2 cleanup and production migration are
   accepted.
3. Design admin workflow changes before implementing import and planning
   redesigns.
4. Design terminal workflow additions before calculator or roll-change timing
   work.
5. Implement the larger production-data workstreams in this order unless the
   user reprioritizes them: shift management, worker recipe editing, then
   packaging/pallet tracking.

This order is only a first cut. The larger items need short design passes before implementation because they change workflow, database shape, and future ERP/costing assumptions.
