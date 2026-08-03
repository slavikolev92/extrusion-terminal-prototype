# V2 Production Status And Backlog

This is the single master tracker for the extrusion-terminal V2 work that began
on July 25-26, 2026. The user can ask an agent to read this file and recommend
the next task. Keep it at workstream/status level rather than turning it into a
detailed implementation plan.

When a workstream starts, explore it with the user and create a temporary task
tracker only if needed. Delete that temporary tracker after the workstream is
complete. Persist the completed status and any remaining work here.

## Current Production Status — August 3, 2026

- The production VM remains on the last confirmed deployed revision,
  `95093c0`. No later production deployment is recorded or authorized by this
  tracker update.
- The production profile, deterministic M006 normalization, production-clone
  migration/rollback rehearsal, final production migration, and deployment
  through that revision were completed. The app was confirmed running in
  production on July 28, 2026. The durable deployment evidence is recorded in
  `v2-files/MIGRATION-REPORT-2026-07-28.md`.
- The current source release candidate contains three later verified
  follow-ups: fixed-height sparse pallet print tables (`1203d25`), unified
  UTC/`Europe/Sofia` time handling (`f77ac6c`), and 15-minute-yellow/
  5-minute-red roll-change indicators (`f1d276f`). These changes require no
  schema or production-data migration. Publishing this source does not deploy
  it; production deployment remains a separate user-scheduled action.
- Fresh verification of the current source checkout on August 3 passed 975
  Python tests and 20 JavaScript tests. The implementation sessions also
  completed the applicable guarded Playwright and print/PDF checks, with
  evidence retained under `artifacts/ui-checks/`.
- There is no known application blocker. The only current operational problem
  is in the upstream Excel workbook/export process, not in this application.
  The inspected V14.07 workbook still embeds the obsolete 26-column exporter,
  while the production app correctly accepts the approved exact 29-column CSV
  contract. Fix the workbook exporter rather than weakening the app importer.
  Evidence and debugging instructions are recorded in
  `docs/implementation-notes/excel-csv-import-contract-debug-handoff.md`.
- The previously discussed fixed-height pallet rows on the bottom print
  summary are implemented and verified in the current source release. They are
  no longer an open task.
- Tasks 4, 6, 7, 13, 14, 15, and 17 below are deferred or optional future work.
  They are not missing requirements for the current production release.

The Shift Manager downstream application cleanup caused by the V14.04
export/import contract change is complete, including Task 6 verification and
the later production normalization/deployment work.

Shift management is functionally implemented and its automated and browser
workflow checks pass against the approved behavior in
`v2-files/TASK-01-SHIFT-MANAGEMENT.md`. The approved replacement terminal
header and shift-interface design is implemented, visually accepted, and has
passed the final adversarial correction gate. Task 01 is complete and deployed.
The follow-up kiosk URL cleanup, compact shift overview, shift-date formatting,
seven-component recipe reachability, transaction-bound active-shift checks,
bounded history queries, safe shift-count validation, and migration validation
are implemented and verified. The production profile, rehearsal, migration,
and deployment gates have all been completed.

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

Completed project.

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

Task 01 is complete and deployed in production. Its M002 migration and the later
M005 shift-schema validation were included in the completed production
migration chain.

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

Completed after shift management on July 26, 2026, following feature-wide
verification and independent review; it is now deployed in production.

### Goal

Record an optional pallet number on each produced roll and show calculated
pallet aggregates on the completed operational card.

### Current Status And Boundary

The bounded feature is complete and deployed. It provides a card-level current
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

- The production M001-M006 migration and deployment are complete. They are no
  longer open gates in this tracker.
- The completed migration preserved production rolls, weights, timing,
  assignments, queues, and imported-source history except for the explicitly
  approved deterministic M006 destination-field normalization.
- Future schema or stored-meaning changes must still follow
  `v2-files/AGENTS.md`: SQLite-safe backup, immutable clone rehearsal,
  temporary-database automated tests, integrity/foreign-key checks,
  idempotence, and rollback preparation before production deployment.
- Unknown historical shift assignment remains better than guessed historical
  assignment. Any approximate backfill would require a separate explicit
  decision and clearly labelled workflow.

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
8. The production profile, M006 implementation, migration/rollback rehearsal,
   final safe backup, production migration, and deployment were completed. The
   application is running in production.

## Deferred Scope

- Any future package, label, shipping, or pallet-lifecycle workflow requires a
  separate approved design; no such workflow is implied by the implemented
  per-roll pallet number.

## Production Workstreams And Deferred Backlog

This list preserves the numbered workstreams and their final production or
deferred status. It is grouped by affected surface and rough complexity.

### Admin / Shift-Manager Panel

1. **Shift management for extrusion production**
   - Surface: `/terminal`, `/admin`, database.
   - Complexity: large.
   - Status: complete and deployed in production. The approved replacement header/shift UI design,
     adversarial review corrections, automated checks, and isolated browser
     verification pass. The production migration and deployment gates have
     been completed.
   - Goal: create one active extrusion shift at a time, require/open shift context for new production roll entry, and attach every new roll to the shift that produced it.
   - Approved behavior: `v2-files/TASK-01-SHIFT-MANAGEMENT.md`.

2. **Fix technology-card quantity fields to match the new Shift Manager export**
   - Surface: CSV/export import, database fields, admin technology-card edit screen, terminal details.
   - Complexity: medium.
   - Status: complete and deployed. The strict V14.04 import/storage correction, schema-only
     M001, admin/terminal cleanup, documentation, print contract, and Task 6
     verification are complete. M001-M006 have been applied through the
     completed production migration.
   - Goal: remove the old ambiguous unit/unit-of-measure display model from the app screens and align the imported/displayed fields one-to-one with the current structured export.
   - Final structured quantity fields: `ordered_gross_kg`, `ordered_rolls`, `ordered_meters`, and `ordered_units`.
   - First visible behavior: show the gross amount clearly as gross kilograms instead of a generic `amount` field.
   - Data behavior: still import/store the other structured ordered amounts even if only gross kilograms are shown to workers initially.
   - Fixed rule: old CSV headers are dead; do not restore compatibility or copy old quantity/unit pairs positionally into the final fields.

3. **Import and display missing Shift Manager production-detail fields**
   - Surface: Shift Manager export file, import parser, database, admin technology-card edit screen, terminal details.
   - Complexity: medium.
   - Status: complete and deployed. The final V14.04 import/storage fields, accepted
     admin/terminal displays, documentation, print contract, and Task 6
     verification are complete. English route values are translated only for
     application display as `Печат`, `Разролване`, and `Конфекция`; stored and
     imported source values remain unchanged.
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
   - Status: deferred future usability improvement; not a current production
     requirement or known application defect. The existing strict CSV import
     works. The current operational problem belongs to the upstream Excel
     workbook/export process.
   - Goal: make import simple enough that the Shift Manager export lands in a known folder and the app can import from that predictable location with minimal clicking.
   - Desired direction: remove or replace the low-value `last imports` section, improve validation review, and make conflict handling happen after import analysis rather than through a pre-selected overwrite checkbox.
   - Data rule direction: the Shift Manager workbook/export is the canonical source for imported/front-card fields, while app-entered production data must still be preserved.
   - Needs design: exact folder handoff, file selection rules, conflict categories, automatic overwrite rules, skip rules, and how production-data-preserving overwrite is explained to the user.

5. **Redesign admin planning and machine sequencing**
   - Surface: `/admin` planning/release screen.
   - Complexity: large.
   - Status: complete and deployed in production. The approved dense table design, shared
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
   - Status: deferred future functionality; it is not part of the current
     production release and its absence is not a current application defect.
   - Goal: allow workers to record the actual recipe/materials used when ad hoc material changes happen during production.
   - Desired behavior: workers can choose materials from inventory-like dropdowns, edit non-calculated recipe fields such as material selection and percentages, and use a free-form material entry only when the material cannot be found.
   - Admin visibility: changed recipe/materials must be clearly brought to Shift Manager attention. Free-form material names must be especially visible because they may not match costing/inventory items.
   - Needs design: inventory source, dropdown grouping to mimic the inventory worksheet, which recipe fields are editable, whether new material categories can be added, audit/history behavior, and how the Shift Manager acknowledges reviewed changes without pretending to approve or reject already-used material.

7. **Add calculator access from the workstation**
   - Surface: `/terminal`, workstation VM/browser environment.
   - Complexity: small to medium.
   - Status: deferred optional convenience; not part of the current production
     release and not a production blocker.
   - Goal: provide quick calculator access for operators.
   - Possible approaches: link/button to a browser-based calculator inside the app, open the Linux desktop calculator from the kiosk environment, or rely on an existing OS shortcut if available.
   - Needs validation: whether the kiosk browser is allowed to launch a native Linux calculator. If not, an in-app calculator is likely simpler and more reliable.

8. **Show one decimal place in weight totals**
   - Surface: `/terminal` totals display, possibly admin card details/print if the same formatter is reused.
   - Complexity: small.
   - Status: complete and deployed in production (original implementation commit
     `97c6ce5`).
   - Goal: display gross total, remaining gross amount, and net total with one decimal place using standard rounding.
   - Verified behavior: only the bottom-right workstation totals changed; underlying stored values, machine KPI quantities, roll rows, admin totals, and print output were left unchanged.

9. **Sort produced cards by produced/finished date descending**
   - Surface: `/terminal` produced-cards popup/drawer.
   - Complexity: small.
   - Status: complete and deployed in production (original implementation commit
     `97c6ce5`).
   - Goal: show the latest produced cards first.
   - Sort key: finished/completed timestamp descending.
   - Verified behavior: produced cards with a finish timestamp sort newest first; cards without a finish timestamp fall after dated cards with deterministic fallback ordering.

10. **Roll change pace / countdown timer**
   - Surface: `/terminal` machine navigation cards, active-card lifecycle bar,
     and versioned browser local storage.
   - Complexity: large.
   - Status: complete and deployed in production. The optional synchronized
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
     19 Node schedule tests passed in 123.953662 ms; the focused Python matrix
     passed 182 tests in 28.07 s; the final full-suite rerun passed 844 tests
     in 67.51 s; `git diff --check` passed; and the guarded Playwright 1.61.0
     workflow passed at `1920x768` and `1366x768`, including adversarial drags
     from every time control over the backdrop, with no console errors, page
     errors, horizontal overflow, timer-only database mutation, accidental
     editor dismissal, or schedule transfer to the next order.
   - July 28 correction: quick acknowledgement preserves the saved scheduled
     cadence, advances at least once, and catches up through whole intervals to
     the first strictly future expected time. The machine-state indicator is a
     solid borderless `16px` circle. This correction remains browser-local and
     makes no production-data or schema change. Fresh verification passed 20
     Node schedule tests, 253 focused Python tests including all 61 migration
     tests, 912 complete Python tests, and the guarded live browser workflow at
     both supported viewports with zero console/page errors.
   - August 1 threshold follow-up: resolved running countdowns now use normal
     styling above `15:00`, yellow from exactly `15:00` through more than
     `05:00`, and red from exactly `05:00` through the due/overdue hold. Both
     the machine card and selected-card indicator use the same pure-model
     result. The follow-up is complete in source through `f1d276f`, requires no
     migration, and passed 975 Python tests, 20 JavaScript tests, and guarded
     browser checks at both supported viewports.
   - Moving the quick acknowledgement/reset action into the machine boxes was
     deliberately excluded from the threshold follow-up. It remains the
     separate deferred Task 17 below.
   - Durable references: `v2-files/TASK-10-ROLL-CHANGE-COUNTDOWN.md`,
     `docs/implementation-notes/roll-change-countdown.md`, and browser evidence
     under `artifacts/ui-checks/roll-change-countdown/`.

11. **Track cards awaiting ripped rolls returned from rewinding/setting**
   - Surface: `/terminal`, `/admin`, database, production timing, and finalization/print eligibility.
   - Complexity: medium to large.
   - Status: complete and deployed in production. The approved lifecycle,
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
   - Status: complete and deployed in production after feature-wide verification
     and independent review. M003, terminal/admin current and per-roll
     correction, overwrite-import preservation, mixed finish warning, derived
     print aggregates, measured renderer capacities, 469 focused tests, 686
     full-suite tests, and guarded live browser/PDF acceptance pass.
   - Implemented behavior: each roll optionally snapshots a `1..999` pallet number scoped to its card; corrections preserve current-versus-snapshot semantics; print output groups current saved rolls by numeric pallet with gross/net totals and conditional `Без палет`.
   - July 31 print-layout follow-up: sparse one- and two-pallet tables and sparse
     final overflow pages retain fixed row heights and leave blank space below
     instead of stretching to fill their neighboring grid area. The CSS-only
     correction is complete in source at `1203d25`, requires no migration, and
     passed the full automated and guarded print/PDF verification used for the
     change.
   - Explicitly deferred/out of scope: package/pallet entities, roll-selection workflow, label routes, label void/reprint history, package/pallet lifecycle, shipping state, and cross-card packaging.

### Operations / Infrastructure

13. **Production backup and recovery resilience**
   - Surface: app VM, Proxmox host, USB backup storage, cloud backup target, optional Tailscale standby server, emergency recovery workstation.
   - Complexity: large.
   - Status: deferred operational-resilience work persisted in
     `v2-files/TASK-13-BACKUP-RESILIENCE.md`. It is not an unresolved
     application-functionality defect, although future backup/restore hardening
     remains operationally valuable.
   - Goal: make the terminal production data recoverable if the app, VM, Proxmox host, physical server, disk, USB drive, cloud sync, network, or power fails.
   - Decided direction: target `0-10 minutes` maximum data loss, tolerate roughly `1-4 hours` recovery time with paper fallback during outage, use two backup destinations beyond the VM (`USB attached to the Proxmox server` plus `cloud storage chosen later`), and keep recovery portable enough that another LAN PC or Linux/Windows machine can temporarily run the app if the main server is unavailable.
   - Possible extension: a warm standby server over Tailscale may receive validated backup copies and remain ready for manager-approved failover. It should run the approved app release rather than emergency `git pull` from the latest branch.
   - Needs design: exact cloud provider/tool, USB mount and monitoring approach, retention policy, checksum/metadata format, backup-health visibility, operator/admin alerting, restore drills, standby activation rules, terminal URL/failover behavior, UPS behavior, and scenario-specific runbooks.

### Deferred Prototype / Recipe Catalogue

14. **CSV-managed extrusion recipe catalogue and filterable material entry**
   - Surface: `/admin/settings`, `/terminal`, `/admin` card detail, database.
   - Complexity: medium; the visible behavior is simple, but safe import,
     persistence, search, concurrent-entry behavior, and verification require
     care. Current estimate: 6-10 engineering hours after the task is resumed.
   - Status: discussion concluded and deferred in
     `v2-files/TASK-14-RECIPE-CATALOG-PROTOTYPE.md`; no implementation is
     authorized. The production-data migration is complete; resume this task
     only if the user explicitly reopens the prototype.
   - Goal: atomically replace a SQLite-backed reference catalogue from the exact
     seven-column CSV represented by the V14.07 `RecipeCatalogExtrusion`
     worksheet, then offer category-filtered, searchable suggestions in the
     existing actual-material text fields while retaining free-form entry.
   - Safety boundary: the catalogue needs a schema-only migration, but existing
     cards and historical actual-material text are not migrated or linked to
     mutable catalogue entries. Invalid imports leave the current catalogue
     active, and successful replacements affect future suggestions only.
   - Prototype purpose: test catalogue ownership, update frequency, search and
     naming quality, and operator exception behavior before considering one
     recipe-prefilled editable material field or strict allowed-list enforcement.
   - Relationship: this is a bounded first prototype slice of Task 6, not the
     full worker recipe edit and inventory workflow.

### Terminal / Workstation UI Follow-Up

15. **State-based lifecycle buttons and split terminal action header**
   - Surface: `/terminal` selected-card header and existing roll-change
     countdown controls.
   - Complexity: small; presentation, render expectations, and browser geometry
     only. No backend lifecycle, database, migration, or stored-data change is
     expected.
   - Status: deferred outside the current release by explicit user decision on
     July 28, 2026. Nothing in this task is approved for implementation, work
     has not started, and it is not a pilot-production prerequisite. The task
     file preserves discussion context only.
   - Goal: stop rendering obsolete disabled lifecycle controls after production
     begins, make the Start/Pause/Continue control morph with card state, keep
     exactly one visually primary action in each active state, and align the two
     header control groups with the Details and Rolls panes below.
   - Preserved proposal only: pending shows primary `Старт` plus disabled
     `Приключи` and no Pause; running shows secondary `Пауза` plus primary
     `Приключи` and no Start; paused shows primary `Продължи` plus secondary
     enabled `Приключи` and no Start.
   - Preserved proposed color rule: retain the existing dark primary and white active
     secondary treatments. Gray is reserved for disabled controls; green/red
     action colors are not introduced because finishing is the normal successful
     path rather than a destructive or emergency action.
   - Preserved proposed layout: keep one header row, align the roll-change group to the
     right edge above Details, and align the lifecycle group to the right edge
     above Rolls by sharing the workspace column geometry at both supported
     workstation widths.

### Cross-Cutting Release Follow-Ups

16. **Unified UTC and Sofia-local time handling**
   - Surface: persistence boundaries, `/terminal`, `/admin`, operational-card
     print output, and admin timing corrections.
   - Complexity: medium to large.
   - Status: complete and verified in the current source release through
     `f77ac6c`; production deployment remains a separate user decision.
   - Implemented contract: production instants remain canonical UTC in SQLite;
     visible operator/admin/print timestamps use `Europe/Sofia`; admin timing
     corrections accept Sofia-local civil time and convert it to UTC with
     explicit handling for repeated and skipped DST hours; the terminal clock
     interpolates from SQLite server time rather than trusting the workstation
     wall clock.
   - Data safety: the inspected production snapshot contained automatic UTC
     timing records and no admin-correction signatures. No schema migration,
     timestamp rewrite, or production-data transformation is required.
   - Durable reference: `docs/implementation-notes/time-handling.md`.

17. **Move roll-change quick acknowledgement into machine boxes**
   - Surface: `/terminal` machine navigation and roll-change controls.
   - Complexity: medium interaction change despite its small visual footprint.
   - Status: deferred separate future task. It was explicitly excluded from
     the completed August 1 indicator-threshold change; no implementation has
     started.
   - Needs design: per-machine targeting, machine-card navigation markup,
     prevention of accidental acknowledgement on the wrong machine, stale-tab
     behavior, keyboard/focus handling, event propagation, and supported
     viewport geometry.

## Current Next Step And Future Order

1. Keep production on the last confirmed deployed revision until the user
   chooses a maintenance window and explicitly authorizes the documented
   production procedure. Source publication is not deployment.
2. Resolve the upstream Excel workbook/export problem. This is the only active
   operational issue identified by the user and is outside the production app.
   Relevant export-side design context is preserved in
   `docs/implementation-notes/oi-003-step-8-export-validation-interim.md`.
3. Treat Task 17's machine-box acknowledgement relocation as a separate future
   interaction task; do not bundle it into the completed threshold release.
4. Do not reopen application development merely because Tasks 4, 6, 7, 13, 14,
   15, or 17 remain documented. They are optional/deferred work and require
   fresh explicit user authorization.
5. If future application functionality is approved, run a short design pass,
   write a scoped implementation plan, assess migration impact under
   `v2-files/AGENTS.md`, test against temporary databases, and deploy through a
   new safe release process.
6. Keep package/label/shipping lifecycle, worker recipe editing, calculator,
   recipe catalogue, backup-resilience expansion, and Task 15 separate from the
   completed production release unless the user explicitly reopens them.
