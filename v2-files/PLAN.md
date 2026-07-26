# Weekend Update Plan

This is the single master tracker for the extrusion-terminal work planned for
July 25-26, 2026. The user can ask an agent to read this file and recommend the
next task. Keep it at workstream/status level rather than turning it into a
detailed implementation plan.

When a workstream starts, explore it with the user and create a temporary task
tracker only if needed. Delete that temporary tracker after the workstream is
complete. Persist the completed status and any remaining work here.

The Shift Manager downstream application cleanup caused by the V14.04
export/import contract change is complete, including Task 6 verification.
The remaining production legacy-data profile and release-candidate rehearsal
are deployment gates only; both require an immutable SQLite-safe backup.

Shift management is functionally implemented and its automated and browser
workflow checks pass against the approved behavior in
`v2-files/TASK-01-SHIFT-MANAGEMENT.md`. The approved replacement terminal
header and shift-interface design is implemented, visually accepted, and has
passed the final adversarial correction gate. Task 01 is complete locally. The
follow-up kiosk URL cleanup, compact shift overview, shift-date formatting,
seven-component recipe reachability, transaction-bound active-shift checks,
bounded history queries, safe shift-count validation, and migration validation
are implemented and verified. The separate M001 production legacy-data profile
and final release-candidate rehearsal remain deployment gates.

The original production-tracking workstreams are:

1. Shift management for extrusion production.
2. Roll packaging / pallet tracking with label printing.

For this V2 workstream, `v2-files/TASK-01-SHIFT-MANAGEMENT.md` is the approved
shift-management functionality source. Do not reintroduce older shift details
from the repository-root `README.md` or this tracker's historical notes.

## Confirmed Direction

- There is one active extrusion shift at a time across all four machines.
- The terminal should not allow production roll entry unless an active shift is selected/open.
- Shift tracking contains a unique occurrence identity, shift number, start
  timestamp, and end timestamp. People count, notes, and named worker assignment
  are not part of this workstream.
- Each normal new roll should persist the active shift occurrence that produced
  it. A roll added later to a completed or archived order inherits the latest
  known shift occurrence already linked to a roll on that order.
- The relationship should permit future crew data to reference a shift
  occurrence without rewriting roll production history, but crew functionality
  is not currently planned.
- Existing roll data must be migrated safely. Old rolls should not receive guessed shift assignments unless the user explicitly approves an approximate backfill.
- Packaging/pallet tracking is separate from shift tracking. A shift produces rolls; a package/pallet groups rolls for transport and label printing.
- Pallet labels should summarize the rolls included, including roll count, gross weight, and net weight.

## Workstream 1: Shift Management

Recommended first project.

### Goal

Persist shift occurrences and attach rolls to them so the app can report
production by numbered shift and time period.

### Current Status

The shift-management backend behavior, M002 schema foundation, terminal
workflow, approved terminal header and shift-interface redesign, and automated
checks are implemented. The follow-up dismissible-window URL cleanup, compact
overview, year-suffix removal, and full-recipe scrolling are also implemented.
M002 performs no historical backfill; 118 focused route/render/script-safety,
14 focused migration, and 560 full automated tests pass, and the
temporary-database Playwright workflow is
recorded in `docs/implementation-notes/shift-management.md`.

Task 01 is complete locally. Production use remains blocked only by the M001
production profile and final release-candidate rehearsal described in
`v2-files/AGENTS.md`.

### Confirmed Data Relationships

- Every shift occurrence has a permanent unique internal identity plus its
  reusable business shift number and automatic start/end timestamps.
- New roll production links to the applicable shift occurrence.
- Historical shift summaries are calculated from the latest corrected linked
  roll data rather than frozen summary copies.
- M002 provides the occurrence/configuration tables, the one-open database
  invariant, and nullable roll attribution without guessing legacy history.

### Future Extension Placeholder

Future worker or crew data could reference the permanent shift-occurrence
identity without changing existing roll history. No worker, roster, or crew
interface or import is included in the current workstream.

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

## Shift-Management Sequence

1. Full shift-management behavior and the focused specification are approved.
2. Post-blocker app/database exploration is complete.
3. The practical implementation plan was written and reviewed.
4. The reviewed slices and schema-only M002 migration are implemented.
5. Existing-data preservation, shift lifecycle, roll attribution, terminal
   gating, summaries, history, configuration, and stale-page behavior are
   verified.
6. The replacement terminal header and shift-interface design are approved and
   their implementation plan is written.
7. Implement the redesign and complete live-browser UI acceptance.
8. Production deployment still requires the M001 legacy-data profile and final
   release-candidate rehearsal on SQLite-safe backup copies.

## Open Questions

- Packaging remains separate: should eventual pallet/package creation happen
  from `/terminal`, `/admin`, or both?

## Near-Term Backlog For Sunday Review

Target completion/review date: Sunday, July 26, 2026.

This list combines the two existing production-tracking workstreams with the newly observed admin and terminal tasks. It is intentionally grouped by affected surface and rough complexity so implementation can be sequenced without mixing small UI fixes with larger workflow redesigns.

### Admin / Shift-Manager Panel

1. **Shift management for extrusion production**
   - Surface: `/terminal`, `/admin`, database.
   - Complexity: large.
   - Status: complete locally. The approved replacement header/shift UI design,
     adversarial review corrections, automated checks, and isolated browser
     verification pass. M001 production profiling and the final
     release-candidate rehearsal remain separate deployment gates.
   - Goal: create one active extrusion shift at a time, require/open shift context for new production roll entry, and attach every new roll to the shift that produced it.
   - Approved behavior: `v2-files/TASK-01-SHIFT-MANAGEMENT.md`.

2. **Fix technology-card quantity fields to match the new Shift Manager export**
   - Surface: CSV/export import, database fields, admin technology-card edit screen, terminal details.
   - Complexity: medium.
   - Status: complete. The strict V14.04 import/storage correction, schema-only
     M001, admin/terminal cleanup, documentation, print contract, and Task 6
     verification are complete.
   - Goal: remove the old ambiguous unit/unit-of-measure display model from the app screens and align the imported/displayed fields one-to-one with the current structured export.
   - Final structured quantity fields: `ordered_gross_kg`, `ordered_rolls`, `ordered_meters`, and `ordered_units`.
   - First visible behavior: show the gross amount clearly as gross kilograms instead of a generic `amount` field.
   - Data behavior: still import/store the other structured ordered amounts even if only gross kilograms are shown to workers initially.
   - Fixed rule: old CSV headers are dead; do not restore compatibility or copy old quantity/unit pairs positionally into the final fields.

3. **Import and display missing Shift Manager production-detail fields**
   - Surface: Shift Manager export file, import parser, database, admin technology-card edit screen, terminal details.
   - Complexity: medium.
   - Status: complete. The final V14.04 import/storage fields, accepted
     admin/terminal displays, documentation, print contract, and Task 6
     verification are complete.
   - Goal: make the app carry all important production-card information from
     the Shift Manager file while showing only the approved fields on each
     admin/terminal surface.
   - Current stored fields include delivery, four route sequence values, next
     operation, folding/gusseting, treatment, recipe materials, and packaging
     method. Route sequences remain stored but are not actionable display inputs.
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
   - Status: complete locally. The approved dense table design, shared
     release/replan modal, row overflow actions, sortable unreleased headers,
     guarded delete behavior, transaction-bound release/replan writes,
     documentation, code review, adversarial fixes, automated tests, and
     Playwright browser verification are complete.
   - Goal: make machine assignment and sequencing manageable when one machine has many orders.
   - Implemented behavior: unreleased cards and each machine queue are shown as
     compact homogeneous tables. Machine queues keep their sequence order.
     Unreleased cards can be sorted by supported headers. Planning/replanning
     happens through one modal. Rare actions such as returning to the unreleased
     queue and deleting unstarted cards live in row overflow menus.
   - Data-safety behavior: deletion is allowed only before production data
     exists, blocks running/paused/started/data-bearing cards, and normalizes
     pending machine queues after deletion. Release and replanning serialize
     their validation/write transaction to avoid delete/replan races.
   - Migration decision: no migration required; the feature uses existing
     planning, roll, timing, tare, and material-actual fields only.

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

11. **Track cards awaiting ripped rolls returned from rewinding/setting**
   - Surface: `/terminal`, `/admin`, database, production timing, and finalization/print eligibility.
   - Complexity: medium to large.
   - Status: newly identified; discussion/design pending.
   - Current process: ripped rolls are sent to an additional rewinding/setting operation and are not entered on the extrusion terminal until they return. Extrusion has already ended, so operators record the stop time, note the number of outstanding rolls on the paper operational card, and keep the card visible near the machine until those rolls return.
   - Goal: make cards waiting for returned rolls easy to identify without treating extrusion as still running, then allow operators to enter the returned roll weights and finalize the card.
   - Desired direction: introduce an explicit waiting-for-rewound-rolls workflow/status, preserve the actual extrusion stop time, record the number of outstanding rolls, and make these cards easy to find from the produced-card area or another focused terminal view.
   - Needs design: the exact status and Bulgarian label; whether the card immediately releases its machine; how outstanding and returned roll counts are stored and corrected; where waiting cards appear; which roll edits are allowed while waiting; the transition to produced/completed; admin correction and visibility; print eligibility; and safe migration behavior.

### Packaging / Pallets

12. **Roll packaging / pallet tracking with label printing**
   - Surface: `/terminal` and/or `/admin`, database, print route.
   - Complexity: large.
   - Goal: group produced rolls into packages/pallets and generate printable transport labels.
   - Desired behavior: select produced rolls, create a package/pallet, prevent one roll from being assigned to more than one active package, show package totals, print labels, and allow voiding/replacing bad labels without deleting production roll history.
   - Needs design: whether packaging happens from `/terminal`, `/admin`, or both; package numbering; package type names; correction workflow; and label format.

## Suggested Implementation Order

1. Before deployment, complete the production legacy-data profile and
   release-candidate rehearsal after an immutable backup is supplied.
2. Design the remaining admin import workflow changes before implementation.
3. Design terminal workflow additions before calculator or roll-change timing
   work.
4. Finish and visually accept the approved shift-management UI redesign, then
   implement the remaining larger production-data workstreams in the order the
   user confirms. Worker recipe editing and packaging/pallet tracking remain
   separate future work.

This order is only a first cut. The larger items need short design passes before implementation because they change workflow, database shape, and future ERP/costing assumptions.
