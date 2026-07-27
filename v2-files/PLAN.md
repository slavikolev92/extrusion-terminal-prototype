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
2. Bounded per-roll pallet attribution and operational-card summary.

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
- Per-roll pallet attribution is separate from shift tracking. A shift produces
  rolls; each roll may snapshot an optional pallet number scoped to its card.
- The operational card summarizes roll count, gross weight, and net weight by
  pallet. Separate package entities, labels, shipping, and pallet lifecycle are
  outside the implemented workstream.

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

## Workstream 2: Roll Pallet Assignment And Operational-Card Summary

Completed locally after shift management on July 26, 2026, following
feature-wide verification and independent review.

### Goal

Record an optional pallet number on each produced roll and show calculated
pallet aggregates on the completed operational card.

### Current Status And Boundary

The bounded feature is complete in the local worktree. It provides a card-level current
pallet value for future rolls, independent per-roll snapshots that remain
correctable, a mixed-assignment finish warning, and current-data operational-
card aggregates with measured page-2/overflow geometry. The final verification
passed 469 focused and 686 full-suite tests plus guarded live browser/PDF
acceptance at both supported viewports.

It deliberately does not create a package/pallet entity or a selection
workflow. Package creation, roll selection across a package, label routes,
label void/reprint history, package/pallet lifecycle, shipping state, and
cross-card packaging are deferred and outside this implemented workstream.

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

- Any future package, label, shipping, or pallet-lifecycle workflow requires a
  separate approved design; no such workflow is implied by the implemented
  per-roll pallet number.

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
   - Surface: `/terminal` machine navigation cards, active-card lifecycle bar,
     and versioned browser local storage.
   - Complexity: large.
   - Status: complete locally on July 27, 2026. The optional synchronized
     winding-set pace clock, editor, anchored one-touch acknowledgement,
     pause/resume state model, machine-card attention states, same-origin tab
     synchronization, lifecycle cleanup, and guarded verification are
     implemented.
   - Implemented boundary: one optional schedule belongs to the current
     running/paused machine-card pair. It is a reminder, not a physical
     roll-change timestamp or production record. Version-1 records live only
     in browser `localStorage`; there is no SQLite schema, migration, backup,
     card-version, re-import, shift, roll, pallet, recipe, print, timing, or
     historical-report coupling, and the next order never inherits a schedule.
   - Verification: compileall and all three Node syntax checks exited zero;
     18 Node schedule tests passed in 70.304575 ms; the focused Python matrix
     passed 182 tests in 27.55 s; the final full-suite rerun passed 844 tests
     in 67.48 s; `git diff --check` passed; and the guarded Playwright 1.61.0
     workflow passed at `1920x768` and `1366x768` with no console errors, page errors,
     horizontal overflow, timer-only database mutation, or schedule transfer
     to the next order.
   - Durable references: `v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md`,
     `docs/implementation-notes/roll-change-countdown.md`, and browser evidence
     under `artifacts/ui-checks/roll-change-countdown/`.

11. **Track cards awaiting ripped rolls returned from rewinding/setting**
   - Surface: `/terminal`, `/admin`, database, production timing, and finalization/print eligibility.
   - Complexity: medium to large.
   - Status: complete locally on July 27, 2026. The approved lifecycle,
     schema-only M004, terminal/Admin integration, roll-control prototype,
     migration/adversarial review, durable documentation, and guarded browser
     workflow are implemented and verified. The exact focused matrix passed
     611 tests, the migration suite passed 42, the full suite passed 814, and
     the unchanged prototype plus live `1920x768`/`1366x768` verifiers exited
     zero without overflow, console errors, or page errors.
   - Current process: ripped rolls are sent to an additional rewinding/setting operation and are not entered on the extrusion terminal until they return. Extrusion has already ended, so operators record the stop time, note the number of outstanding rolls on the paper operational card, and keep the card visible near the machine until those rolls return.
   - Implemented behavior: `awaiting_rewinding` records the real extrusion stop
     and final extrusion shift, frees and normalizes the machine queue, remains
     separate from active and Produced Orders, accepts actual returned-roll and
     permitted correction work, and requires deliberate terminal finalization.
     The informational `1..999` marker is editable but never count-matched;
     pallet remains optional; waiting is not printable, cancellable, deletable,
     archivable, startable, pausable, resumable, or resequencable.
   - Durable references: `v2-files/TASK-11-REWINDING.md` and
     `docs/implementation-notes/rewinding-return-workflow.md`.

### Packaging / Pallets

12. **Per-roll pallet attribution and operational-card summary**
   - Surface: `/terminal`, `/admin`, database, operational-card print route.
   - Complexity: medium to large.
   - Status: complete in the local worktree after feature-wide verification and independent review. M003, terminal/admin current and per-roll correction, overwrite-import preservation, mixed finish warning, derived print aggregates, measured renderer capacities, 469 focused tests, 686 full-suite tests, and guarded live browser/PDF acceptance pass.
   - Implemented behavior: each roll optionally snapshots a `1..999` pallet number scoped to its card; corrections preserve current-versus-snapshot semantics; print output groups current saved rolls by numeric pallet with gross/net totals and conditional `Без палет`.
   - Explicitly deferred/out of scope: package/pallet entities, roll-selection workflow, label routes, label void/reprint history, package/pallet lifecycle, shipping state, and cross-card packaging.

## Suggested Implementation Order

1. Before deployment, complete the production legacy-data profile and
   release-candidate rehearsal after an immutable backup is supplied.
2. Design the remaining admin import workflow changes before implementation.
3. Design terminal workflow additions before calculator or roll-change timing
   work.
4. Implement the remaining larger production-data workstreams in the order the
   user confirms. Worker recipe editing, roll-change timing, and any future
   package/label/shipping lifecycle remain separate future work. Task 11's
   waiting-for-rewound-rolls workflow and Task 12's bounded per-roll pallet
   attribution/operational-card summary are complete locally. Production
   deployment remains a separate, explicitly gated operation.

This order is only a first cut. The larger items need short design passes before implementation because they change workflow, database shape, and future ERP/costing assumptions.
