# Task 24: Shift Crew Attribution And End-Of-Shift Production Reports

Status: discussion captured on September 13, 2026. This is a deferred task and
the durable continuation record for the discussion summarized below. It has no
approved implementation plan, no code or schema work has started, and it is not
deployed. Recording it does not authorize application changes, a production
database profile, historical attribution, migration, report scheduling, or
deployment.

Physical pallet-weight entry is source-complete but not deployed. Task 25's
separately approved operational pipeline/database-backup slice is current, and
Task 20 remains the next application-feature workstream after its required Item
Master contract decisions and design/plan reconciliation. Resume Task 24's
product design only when the user deliberately returns to it; its eventual PDF
delivery must consume Task 25 rather than adding another uploader.

## Executive Summary

The desired outcome is a simple, repeatable end-of-shift production document
that identifies the people working the extrusion shift and shows what that
shift produced. The business can provide the names of the people on each day
and night shift from the beginning of July 2026 onward. The fixed business
windows are:

- day shift: `08:00` inclusive through `20:00` exclusive on the same Sofia
  calendar date; and
- night shift: `20:00` inclusive on its start date through `08:00` exclusive
  on the following Sofia calendar date.

The application already has the correct production-ownership foundation.
`shift_occurrences.id` is the permanent identity of one actual extrusion shift,
and new rolls record the occurrence that produced them. The completed Task 01
shift model should therefore be retained. Named workers and scheduled day/night
meaning should be added beside it, not encoded into the reusable numeric shift
number and not used to rewrite existing roll history.

The current terminal summary is a live query that groups rolls by shift and
production order and reports roll counts and gross kilograms. The requested
document extends that concept with crew names, individual roll rows, per-roll
weights, per-order subtotals, and shift totals. The default direction is one PDF
per completed shift occurrence, generated after the shift-end transaction,
retained as a revisioned business document, and available to the Shift Manager
for review, download, and regeneration.

## Why This Is A Separate Task

Task 01 deliberately implemented shift occurrences, roll attribution, history,
and a live summary without people count, worker names, roster import, or PDF
report generation. It left a permanent occurrence identity specifically suited
to a later crew relationship.

Task 24 is not a small label addition because it must reconcile four different
facts safely:

1. scheduled day/night roster windows;
2. the actual manually opened and ended shift occurrence;
3. per-roll production ownership and later corrections; and
4. an immutable PDF revision whose contents may later become stale.

It also has a hard historical boundary: M002 did not invent occurrences or
shift links for legacy production. Crew names can be stored for old dates, but
names alone cannot prove which legacy rolls belonged to those crews.

## Existing Application Contract To Preserve

Any future design and implementation must begin from the source and database
contract that exists at that time. The present contract includes:

- one global active extrusion shift across all four machines;
- one permanent `shift_occurrences.id` per actual shift opening;
- a reusable, editable numeric `shift_number` that is not a day/night identity;
- authoritative application/database start and end timestamps stored in UTC
  and displayed in `Europe/Sofia`;
- one nullable `roll_entries.shift_occurrence_id` per roll;
- normal new rolls linked atomically to the active shift occurrence;
- later rolls on waiting, completed, or archived cards attributed according to
  the bounded final-extrusion-shift and legacy fallback rules;
- live completed-shift summaries derived from the latest corrected linked roll
  rows rather than frozen summary data;
- shift ending that does not pause, finish, reassign, or otherwise mutate cards
  or production timing; and
- no individual operator identity, user account, role, login, or permission
  model in the pilot.

The current shift summary groups linked rolls by card and shows production
order, customer, product type, roll count, and gross weight. It does not show
worker names, individual roll weights, net totals, or create a durable PDF.

Task 23 physical pallet-weight entry is source-complete and may be deployed
before this task is resumed. At Task 24 design time, the implementation must
inspect the then-current source and production revision. A physical pallet
weight is pallet-level information and must never be reinterpreted as roll-core
tare or divided into invented per-roll pallet weights.

## Desired Business Outcome

For every completed extrusion shift, the Shift Manager should be able to obtain
one document that answers:

- which dated day or night shift this was;
- when the scheduled shift window began and ended;
- when the actual app shift began and ended;
- which people were recorded as working that shift;
- which machines and production orders contributed rolls;
- which roll numbers belonged to each production order;
- the gross, roll-core tare, and film-net amount for each roll;
- the amount contributed by each production order during this shift; and
- the total roll count, gross kilograms, and net kilograms for the shift.

The initial definition of “produced by the shift” remains roll-based: a
production order participates when at least one roll is linked to that shift
occurrence. A card that was worked on during the time window but produced no
linked roll is not silently treated as produced. If the business later needs a
second section for every order worked on, including zero-roll work, that section
must be designed explicitly from production-timing overlap and labelled
separately.

## Default Roster Input

The recommended source is a UTF-8 CSV with one row per worker per scheduled
shift. Do not place multiple people in one delimited name cell.

```csv
shift_date,shift_type,worker_name,worker_code,machine_number,notes
2026-07-01,day,Иван Иванов,EMP001,1,
2026-07-01,day,Петър Петров,EMP002,2,
2026-07-01,night,Георги Георгиев,EMP003,,
2026-07-01,night,Николай Николов,EMP004,,
2026-07-02,day,Иван Иванов,EMP001,1,
```

### Column Meaning

| Column | Current default meaning |
| --- | --- |
| `shift_date` | Required ISO date `YYYY-MM-DD`; always the date on which the shift begins. |
| `shift_type` | Required controlled value `day` or `night`. |
| `worker_name` | Required full display name, preserved as the historical roster snapshot. |
| `worker_code` | Optional stable personnel code; recommended for duplicate names and spelling changes. |
| `machine_number` | Optional machine `1` through `4`; blank means the person is recorded only as part of the shift-wide crew. |
| `notes` | Optional source note; not production data and not automatically printed. |

The night shift that starts at 20:00 on July 1 is identified by
`shift_date=2026-07-01` and `shift_type=night`, even though it ends on July 2.
The user should not need to provide UTC offsets. The application should derive
the scheduled boundaries with `Europe/Sofia`, including daylight-saving
transitions.

Names should use consistent spelling. A worker code should identify a person
when available, but the report must retain the name snapshot supplied for the
particular shift so a later personnel-name edit cannot silently rewrite an old
report. A general employee directory, attendance system, payroll integration,
or user-account relationship is not required by the current discussion.

Machine assignment is optional input. The confirmed business request is to
show the people on the shift, not to make an automatic worker-performance
judgment or prove individual responsibility for a particular machine or roll.
Before implementation, confirm whether the optional machine value should be
stored and printed in the initial slice or deferred.

## Scheduled Roster And Actual Occurrence

A scheduled roster slot and an actual shift occurrence are related but not the
same record:

- the roster slot carries the business date, `day`/`night` type, scheduled
  Sofia boundaries, and crew;
- the occurrence carries the actual app start/end timestamps and the permanent
  identity already referenced by production rolls; and
- the report is owned by the actual occurrence after that occurrence is linked
  to the applicable roster slot.

Never derive day/night meaning from `shift_number`. That number is a reusable
business label, can be corrected while a shift is open, and may describe a
rotating crew rather than one of the two daily time windows.

The default future direction is to resolve the unique scheduled slot applicable
to a newly opened occurrence and persist the occurrence relationship. Normal
early or late starts must not change the scheduled business window. Historical
matching should be previewed and confirmed from the actual occurrence interval.
An ambiguous, abnormally long, missing, or overlapping occurrence must remain
unmatched until reviewed; the application must not choose a crew silently from
a weak timestamp heuristic.

A missing roster must not block workers from starting or ending production.
Production continuity is more important than report completeness. The report
state should make the missing crew visible and permit a later roster correction
and report revision.

## Default Data Direction

The following conceptual records are the current recommendation. Exact table
and column names must be finalized only during the later approved design and
implementation plan.

### Scheduled Shift Roster

One record per `(shift_date, shift_type)` should hold:

- the Sofia business date and controlled day/night type;
- canonical scheduled start and end instants;
- an optional unique link to the actual `shift_occurrences.id`;
- source/import metadata;
- optimistic version and update timestamps; and
- a visible unmatched, matched, or attention-required state derived without
  changing production history.

### Roster Workers

One child row per person should hold:

- the owning roster;
- the supplied display-name snapshot;
- optional stable worker code;
- optional machine number if that part of the input is retained;
- deterministic display order; and
- optional source note if approved.

Do not store a comma-separated worker list on `shift_occurrences`. A separate
child relationship supports variable crew size, validation, duplicate
detection, and exact report rendering without changing the completed Task 01
row meaning.

The current default does not require a separate mutable worker-master table.
That would add naming, lifecycle, alias, and personnel-management decisions not
needed merely to print a historical name snapshot. Reconsider it only if real
worker codes or another authoritative personnel source make it useful.

### Report Metadata

A small report record may hold:

- owning `shift_occurrence_id`;
- revision number;
- generation state and failure message;
- generation timestamp;
- durable relative filename or storage identity;
- content checksum; and
- whether a newer production or roster change has made the revision stale.

The SQLite database should continue to own structured production and roster
facts. The PDF is a generated business document, not a replacement database.
Generated business PDFs must use an approved durable report location with a
retention and backup decision; they must not be stored under disposable
`artifacts/`.

## Default PDF Contents

One report should represent one completed `shift_occurrences.id`. Its default
presentation is:

### Header

- report title and revision;
- shift business date and `Дневна` or `Нощна`;
- scheduled start and end in Sofia time;
- actual app start and end in Sofia time;
- reusable shift number as supporting information, not identity;
- generation timestamp and provisional/stale/final status where applicable;
- worker names, with optional machine labels only if machine-level roster data
  is confirmed; and
- an explicit missing-roster warning instead of guessed names.

### Roll Detail

- machine number from the current saved card assignment;
- production order number;
- customer and product type;
- roll number;
- optional saved pallet number;
- gross kilograms;
- saved roll-core tare kilograms; and
- calculated film-net kilograms.

Each stored amount should be rendered from the existing exact decimal value
using an explicitly approved report format. The current default is to retain
the existing gross measure and add tare and net rather than use an ambiguous
single “amount” column.

If physical pallet weight is included after Task 23 deployment, show it only in
a separate pallet-level summary using the existing physical-pallet semantics.
Do not allocate it across roll rows or subtract it from film net.

### Subtotals And Grand Total

For each production order, show the contribution of rolls linked to this shift:

- linked roll count;
- gross total;
- roll-core tare total; and
- film-net total.

The subtotal is not automatically the complete lifetime total of the order. If
one production order has rolls in two occurrences, it should appear in both
reports, with each report containing only its own linked rolls.

The final shift total should show:

- distinct production-order count;
- roll count;
- gross kilograms;
- roll-core tare kilograms; and
- film-net kilograms.

## Generation And Revision Lifecycle

The explicit successful `Приключи смяната` action is the natural report-
generation trigger. The report producer does not require its own generation
timer or general background-service framework. After it creates a complete PDF,
the separately approved Task 25 outbox and delivery timer own Hetzner upload,
retry, and Discord pipeline notification.

The safe order is:

1. validate and commit the existing shift end exactly as today;
2. build a report from one consistent post-commit database snapshot;
3. resolve the linked roster or record that it is missing;
4. generate and atomically publish a new PDF revision; and
5. expose the result and any retryable generation error to the Shift Manager.

PDF generation failure must never reopen or roll back a successfully ended
production shift. A missing roster or unavailable renderer should create a
visible retryable report state, not corrupt production data and not prevent the
next shift from starting.

The report renderer is not yet selected. The existing application uses
server-rendered HTML/CSS and browser print for operational cards. The later
design should compare extending that pattern with a production-supported PDF
renderer. It must account for Bulgarian fonts, deterministic A4 pagination,
the deployed server environment, dependency installation, process failure,
atomic file publication, and recovery. Development-only Playwright tooling
must not silently become an undeclared production dependency.

## Why The First PDF May Not Be Final

Completed-shift summaries are live. Permitted roll correction or deletion can
change an ended shift's next summary. The rewinding workflow is especially
important: a returned roll entered after extrusion ended is assigned back to
the final extrusion shift, not to the later shift whose worker typed the
weight. The original shift's totals can therefore increase after its shift-end
PDF was created.

The current default is:

- create revision 1 after shift end using the data currently available;
- label it provisional when the linked final-extrusion shift still has a card
  awaiting returned rewinding rolls or when its roster is missing;
- never silently overwrite an existing PDF revision;
- mark the latest report stale when a linked roll or roster is later added,
  corrected, or removed; and
- let the Shift Manager deliberately generate the next numbered revision.

Whether the application should also create a final revision automatically when
the last relevant waiting card is finalized remains a later product decision.
The design must cover completed-card corrections as well as rewinding returns;
solving only the waiting state would leave another stale-report path.

## Historical July Boundary

The production M002 migration deployed on July 28, 2026. It deliberately:

- left all 653 then-existing roll rows with `NULL` shift attribution;
- created no guessed historical shift occurrence; and
- preserved every prior production value.

A roster containing the names for July 1 onward does not establish which of
those legacy rolls each crew produced. Neither roll creation timestamps, card
start/finish timestamps, reusable shift numbers, nor scheduled day/night windows
are sufficient authority for an automatic backfill.

If exact pre-M002 reports are required, the recommended additional evidence is
one UTF-8 CSV row per existing roll:

```csv
shift_date,shift_type,order_number,roll_number,gross_weight_check
2026-07-01,day,ORD-1042,1,52.40
2026-07-01,day,ORD-1042,2,51.85
2026-07-01,night,ORD-1042,3,53.10
2026-07-01,night,ORD-1077,1,48.20
```

`gross_weight_check` is validation evidence only. It must never overwrite the
saved roll weight. The intended match is the unique existing card/order and
roll number, verified against the supplied amount. Conflicts, missing rolls,
duplicate rows, or changed weights must be reported for review.

Any historical attribution is a separate production-data migration decision.
It requires explicit user approval, a SQLite-safe production backup, immutable
clone profiling, exact accepted mapping rules, preservation comparisons,
integrity and foreign-key checks, idempotence, rollback preparation, and the
active migration/deployment playbook. The first forward-looking roster/report
slice should remain schema-only and empty unless the historical mapping is
separately approved.

If roll-level historical evidence is unavailable, the application may retain
the historical worker rosters, but the corresponding pre-M002 production must
remain explicitly unattributed. It must not publish apparently exact shift
totals from guessed data.

## Access And Privacy Boundary

Worker names are personal data. The current pilot has practical route
segregation but no authentication or strong authorization. The default report
surface should therefore be Shift Manager/Admin only, must not add PDF controls
to the workstation, and must not expose a public report URL.

This task does not authorize users, roles, login, permissions, payroll,
attendance, biometric data, individual productivity scoring, or automatic
worker-performance verdicts. If stronger access control or a wider audience is
required, that is a separate scope decision and must be reconciled with the
pilot boundary before implementation.

## Relationship To Other Tasks

- **Task 01:** preserve its occurrence identity, roll relationship, lifecycle,
  and live-summary semantics. Task 24 extends rather than replaces it.
- **Task 11:** preserve returned-roll ownership by final extrusion shift and
  design report revision behavior around that fact.
- **Task 18:** keep the broader sales/logistics reporting discovery separate.
  Task 24 is an operational end-of-shift crew and production report, not a
  general external reporting portal.
- **Task 20:** no recipe/catalogue dependency belongs in Task 24. Task 20 remains
  the next application-feature workstream.
- **Task 23:** inspect its deployed state when Task 24 resumes; never confuse
  physical pallet weight with roll-core tare or per-roll film net.
- **Task 25:** reuse its approved `shift-reports` outbox category, immutable
  delivery, retry, and Discord notification. Task 24 continues to own roster,
  report content, revision, renderer, and generation-event rules.
- **Task 69:** do not pull successor-MES personnel, authorization, or general
  reporting architecture into this bounded pilot task.

## Explicitly Outside The Current Default

- replacing the existing shift occurrence or roll-attribution model;
- inferring day/night from the numeric shift number;
- guessing historical shift ownership;
- blocking shift start or end because roster/report data is missing;
- users, authentication, permissions, attendance, time clocks, or payroll;
- worker productivity rankings, OEE, anomaly judgments, or disciplinary data;
- assigning individual responsibility for a roll without confirmed source data;
- rewinding-department scheduling, processing, or worker tracking;
- writing terminal production or roster data back into the Shift Manager Excel
  workbook;
- a general report scheduler or background-service framework;
- public internet exposure;
- inventory posting, costing, Task 20 recipe work, or permanent ERP/MES
  expansion; and
- treating generated PDFs as the authoritative structured production database.

## Default Future Execution Sequence

This is a planning baseline for the next discussion, not an executable
implementation plan.

1. Re-read `README.md`, the then-current `AGENTS.md`, Task 01, shift-management,
   rewinding, time-handling, printing, physical-pallet, migration, and
   production-deployment contracts.
2. Confirm the roster sample and the remaining product decisions listed below.
3. Inspect only an explicitly authorized SQLite-safe production backup to
   profile actual post-M002 occurrences, timing boundaries, linked/unlinked
   rolls, waiting cards, and correction cases. Never inspect or mutate the live
   runtime database for design convenience.
4. Write and approve a focused design covering roster import, occurrence
   matching, Admin workflow, report presentation, generation failure, revision,
   access, retention, and backup behavior.
5. Write and review a separate implementation plan. Derive the next migration
   version from `app/migrations.py` at that time; this document reserves none.
6. Implement one schema/data-contract slice first with temporary-database
   migration tests and no historical backfill.
7. Add the minimal Admin roster import/review and occurrence-link workflow with
   optimistic conflict handling.
8. Add one pure report view model and a server-rendered preview from a
   consistent read snapshot.
9. Add the approved PDF renderer, durable versioned publication, retry/stale
   handling, and shift-end trigger without coupling report failure to the shift
   transaction.
10. Verify focused backend and route behavior, migration preservation,
    printing/PDF output, Bulgarian text, supported viewports where applicable,
    filesystem safety, and the full automated suite using only temporary
    databases and disposable verification artifacts.
11. Treat any pre-M002 roll attribution as a separate explicitly approved data
    migration after the forward-looking behavior is accepted.
12. Update durable implementation notes and tracker status only after verified
    source completion. Production deployment remains a separate maintenance-
    window decision.

## Decisions To Confirm When Discussion Resumes

The current recommendation above is sufficient to retain the task, but these
questions must be answered before approving an implementation plan:

1. Is a shift-wide list of names sufficient, or must the first version record
   each worker's machine assignment?
2. Are stable worker/personnel codes available, and are they authoritative?
3. Will the normal roster arrive as CSV upload, one initial historical file
   followed by manual Admin entry, or another maintained source?
4. What early/late-start tolerance and manual confirmation flow should link an
   actual occurrence to a scheduled day/night slot?
5. Should a missing roster create a PDF with a warning or leave generation
   pending until the roster is added?
6. Should the report show both gross and film-net as recommended, and should it
   include pallet-level values after Task 23 deployment?
7. Is roll-based production sufficient, or is a separate list of zero-roll
   orders worked on during the shift also required?
8. Which production-supported PDF renderer, producer-owned durable local
   directory, filename/edition contract, retention period, and download
   workflow should be used? Hetzner delivery must use Task 25.
9. Should later changes only mark a report stale for deliberate regeneration,
   or should some events generate a new revision automatically?
10. Is exact per-roll evidence available for any desired pre-M002 historical
    attribution, and which date range must the first report set cover?
11. Who may access worker-name PDFs on the current unauthenticated LAN app, and
    is practical Admin-only route separation sufficient for the pilot?

## Discussion Checkpoint

The discussion ended with the following default recommendation:

- keep the current shift occurrence and per-roll production relationships;
- accept a long-form UTF-8 roster CSV with one person per row;
- define day/night by the shift's Sofia start date and fixed `08:00`/`20:00`
  boundaries;
- store scheduled rosters and worker snapshots separately from actual shift
  occurrences;
- link each report to the permanent occurrence ID, never only to a date or
  reusable shift number;
- generate one detailed, versioned, retryable PDF after each successful shift
  end;
- include crew names, individual rolls, gross/tare/net amounts, per-order
  shift contributions, and shift totals;
- preserve later rewinding and correction effects through visible stale/report-
  revision behavior;
- require explicit roll-level evidence for any pre-M002 historical production
  mapping; and
- postpone design approval and implementation until the user deliberately
  resumes Task 24; reuse Task 25 delivery rather than redesigning upload.

When that happens, start by obtaining a representative roster sample and
answering Decisions 1, 5, 6, 8, 9, and 10. Do not begin with schema or route
implementation from this discussion record alone.
