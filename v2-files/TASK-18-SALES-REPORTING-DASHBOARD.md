# Task 18: Read-Only Sales And Logistics Reporting Dashboard

Status: functional discovery opened on August 4, 2026. The user wants this
prototype functionality developed, but the detailed product design is not yet
complete and implementation has not started. This document records the full
discussion, the recommended direction, the deliberately deferred security
work, and the decisions still required before an implementation plan is
approved.

This task is a scoped expansion of the extrusion-terminal pilot. Recording it
does not authorize implementation, production deployment, authentication,
network reconfiguration, firewall changes, or mutation of the runtime
database.

## Executive Summary

Aparkey, who is responsible for sales and logistics work, needs practical
access to the actual output recorded by the extrusion terminal. In particular,
he needs to see the rolls produced for an order, their gross and net weights,
the total production output, and other relevant operational-card information.
He also needs to print specific business documents from that data. His current
printing process is inefficient.

The current application has only `/terminal` and `/admin` working surfaces and
has no authentication or permission system. Any computer that can reach the
application on the LAN can type either route and use the available actions.
Removing links or creating an unlinked URL does not prevent this. That fact was
confirmed by the user through direct LAN testing.

The eventual secure architecture may restrict the routes by approved LAN
workstation IP address, introduce a reverse proxy, run reporting as a separate
read-only process, or add authentication and roles. The user has explicitly
deferred all of that work. The current phase is intended to prove the sales and
logistics functionality, information, workflow, and print templates before
investing in security infrastructure.

The recommended prototype is therefore a new, isolated `/sales` section in the
existing FastAPI deployment. It should be functionally read-only: it exposes
only pages that read and present current saved data, contains no editing or
production actions, and provides only approved searches and print views. It
should use the existing live SQLite database and reuse the application's
validated roll, weight-total, pallet-summary, timing, and print-assembly logic
where applicable. It should not create a second database, copy production
records, or introduce a synchronization process.

For later security to remain inexpensive, every sales page and sales print
route should live under the `/sales` namespace, use dedicated query and
presentation boundaries, and remain independent of Admin and Terminal mutation
functions. The prototype must be described honestly as functionally read-only,
not securely access-restricted: until the deferred security work is completed,
a LAN user can still manually visit the existing `/admin` or `/terminal`
routes.

## Business Problem And Intended User

The primary intended user is Aparkey in the sales and logistics function. The
business need is downstream visibility into completed extrusion output, not
participation in extrusion planning or execution.

The sales/logistics user needs a purpose-built surface because the two existing
interfaces have different responsibilities:

- `/terminal` is the production workstation. It starts, pauses, resumes, and
  finishes cards; records rolls; and changes other production information.
- `/admin` is the Shift Manager interface. It imports and edits cards, plans
  machine queues, corrects production data, archives/cancels/restores cards,
  and prints operational cards.
- The proposed `/sales` area should find, monitor, inspect, and print selected
  finished-card information without exposing any sales-side edit control.

The requested dashboard is not a new sales-order system, shipping module,
inventory module, or ERP. It is a read-only reporting surface over the output
already captured by this bounded extrusion pilot.

## Current Application Facts Relevant To This Task

Repository inspection during the discussion confirmed these facts:

- The application is one FastAPI service backed by SQLite.
- `/admin`, `/terminal`, and the existing completed-card print route are served
  by the same application and LAN endpoint.
- There are no users, passwords, roles, sessions, or route permissions.
- The current separation between Admin and Terminal is practical UI
  segregation, not strong security.
- Any LAN computer that can reach the app can manually enter either route. The
  user has tested and confirmed this behavior.
- The database already stores structured imported operational-card data,
  terminal-entered roll data, per-roll gross/tare/net values, total weights,
  timing, shift attribution, optional pallet numbers, and lifecycle status.
- Existing Admin detail queries already assemble broad card information and
  current roll/timing totals.
- The existing print subsystem validates printable card state and assembles the
  operational-card front, roll grid, totals, and pallet summary.
- Existing operational-card printing is currently allowed only for
  `completed` and `archived` cards.
- `awaiting_rewinding` cards are deliberately not yet completed and are not
  printable under the current operational-card rules.
- Cancelled, imported, pending, running, and paused cards are not printable.
- There is no Tailscale installation or Tailscale access requirement for this
  task. The environment under discussion is LAN-only.

These facts mean the data and much of the reporting calculation logic already
exist. The primary new work is deciding the sales-facing information model,
list/detail workflow, and document templates, then presenting them through a
separate read-only surface.

## Meaning Of “Read-Only” In The Prototype

Two meanings must remain separate.

### Functional read-only behavior now

The `/sales` surface should:

- expose only HTTP `GET` pages;
- contain no forms or controls that update cards, rolls, timing, shifts,
  planning, imports, materials, tare, pallets, or statuses;
- never call Admin or Terminal database mutation functions;
- never silently mark a card as viewed, printed, approved, dispatched, or
  otherwise processed;
- calculate and present current saved values without changing them; and
- have its own navigation with no links into `/admin` or `/terminal`.

This is achievable immediately and is the approved direction for functional
discovery.

### Enforced access restriction later

During the prototype phase, “read-only dashboard” does not mean that Aparkey or
another LAN user is technically prevented from typing `/admin` or `/terminal`.
That restriction requires the separately deferred security work.

The prototype must not claim that hiding links, using a different route, or
removing edit buttons secures the existing application. These measures reduce
accidental navigation only. They do not provide authorization.

## Recommended Prototype Architecture

### Overall structure

Use one repository, one deployed FastAPI application, and the existing live
SQLite database:

```text
LAN browser
    |
    v
/sales GET routes
    |
    v
sales-specific read queries and presentation assembly
    |
    v
existing live SQLite card, roll, timing, shift, and pallet data
```

The browser must never connect directly to SQLite. FastAPI reads the approved
fields, creates a bounded view model, and renders HTML or a print view.

### Proposed route namespace

The exact URLs can be adjusted during design, but all sales behavior should
remain under one prefix. A likely route shape is:

```text
GET /sales
GET /sales/cards/{card_id}
GET /sales/cards/{card_id}/print/{template_name}
```

Search and filter values should normally be query parameters on `/sales`
rather than POST forms because searches do not mutate state.

Sales print routes should not rely on the existing public
`/cards/{card_id}/print` URL as their user-facing entry point. They may reuse
the renderer and assembly functions internally, but keeping the routes under
`/sales` creates one future access-control boundary.

### Recommended component boundaries

The implementation should keep four responsibilities distinct:

1. **Sales routes**
   - Accept bounded search/filter parameters.
   - Select the sales list, detail, or print response.
   - Contain no mutation endpoints.

2. **Sales read queries**
   - Fetch only visible card statuses and approved fields.
   - Fetch roll-level data and calculated current totals.
   - Use parameterized SQL and bounded pagination.
   - Remain separate from Admin save/update/delete functions.

3. **Sales presentation models**
   - Translate stored values into clear Bulgarian labels and display formats.
   - Reuse established production calculations instead of recalculating totals
     with a second set of business rules.
   - Provide stable data shapes to both screen and print templates.

4. **Sales templates and print templates**
   - Use a dedicated sales layout and navigation.
   - Contain no Admin or Terminal actions.
   - Present the approved fields and documents only.

This separation is intentionally small. It does not require a general report
framework, plugin system, API layer, background service, or second database.

## Why The Same-App `/sales` Approach Is Recommended Now

Three approaches were considered during the discussion.

### Approach A: Dedicated `/sales` section in the existing app

This is the recommendation for the prototype.

Advantages:

- quickest route to testing real workflow and print needs;
- reuses the current database, calculations, time formatting, and print logic;
- avoids database copies, synchronization, and a second deployment service;
- keeps backup and recovery behavior unchanged if no new data is persisted;
- can later be protected as one route namespace; and
- can later be extracted into a separate process if stronger isolation is
  justified.

Limitations:

- it is behaviorally read-only, not technically isolated from database writes
  at the operating-system/process level;
- the rest of the application remains reachable on the LAN until security is
  added; and
- careless future code could introduce a write route, so route and regression
  tests must enforce the intended boundary.

### Approach B: Separate reporting FastAPI process now

A second process could open SQLite through URI read-only mode and
`PRAGMA query_only`, then expose a separate LAN port.

Advantages:

- stronger technical database-write protection;
- clean deployment and network boundary; and
- direct fit for later IP-based port restrictions.

Limitations:

- adds a second service, health check, deployment configuration, port, and
  operational troubleshooting surface before the reporting workflow is proven;
- requires careful sharing of query/presentation code to prevent duplication;
  and
- spends effort on isolation that the user explicitly wants to defer.

This remains a viable later extraction path, not the recommended first
prototype step.

### Approach C: Generate static PDF/CSV exports

The production app could generate files into a folder that sales/logistics can
read.

Advantages:

- strong separation from the live application when the shared folder is
  properly configured; and
- simple access to already-generated documents.

Limitations:

- stale copies after Admin corrections;
- duplicated/exported production data;
- weak search and monitoring behavior;
- file naming, retention, replacement, and synchronization rules; and
- poor support for interactive choice among multiple print templates.

This does not match the requested live dashboard as well as Approach A.

## Known Functional Requirements

The discussion established the following requirements:

- Aparkey needs access to actual output saved by the extrusion terminal.
- The dashboard is for sales and logistics work.
- It must focus on finished operational cards rather than active production
  execution.
- It must show the rolls produced for an order.
- It must show gross and net weights.
- It must show order/card totals derived from the saved rolls.
- It should expose the relevant information otherwise available to the Shift
  Manager without exposing editing actions in the sales interface.
- It must support printing specific templates based on the saved card/output
  data.
- It should use current live application data rather than requiring the Shift
  Manager to export or re-enter the results.
- Security enforcement is not part of the first functional prototype.
- The architecture must keep later security feasible without rebuilding the
  dashboard.

“The same information as the Shift Manager” should not yet be interpreted as
every Admin field. The sales-facing field set must be chosen deliberately so
the page is useful and not simply a non-editable clone of a dense operational
administration screen.

## Candidate Dashboard Workflow

This workflow is recommended for the next design discussion but is not yet
approved in detail.

1. Aparkey opens `/sales` from a LAN browser.
2. The page initially shows the newest visible finished cards first.
3. He searches or filters to find an order, customer, product, or production
   period.
4. He opens one card without changing its status or version.
5. The detail page shows the approved order information, timing/output summary,
   roll ledger, and aggregate totals.
6. He selects one of the approved document templates.
7. The app renders current saved data in a print-oriented view.
8. Browser printing or an approved downloadable format produces the document.
9. Viewing or printing does not archive, approve, dispatch, correct, or
   otherwise mutate the operational card.

## Card Visibility And Review State

The most important unresolved functional decision is when a card becomes
visible to sales/logistics.

The current lifecycle distinguishes:

- `completed`: production is finished, but the card remains available for
  review and correction;
- `archived`: the Shift Manager has finished review/paper handling; and
- `awaiting_rewinding`: extrusion has ended, but returned rolls still need to
  be entered and the card deliberately finalized.

The recommended option presented in discussion is to show both `completed` and
`archived`, with visibly different meanings:

- Completed: produced, possibly awaiting Shift Manager review/correction.
- Archived: reviewed/final under the current operational workflow.

This would provide timely information while warning sales/logistics when values
are still provisional. The user has not yet approved this option.

Other possibilities are:

- show only `archived` cards, giving sales only reviewed/final results but
  delaying visibility; or
- show only `completed` cards, which would omit retained archived history and
  is therefore not recommended.

Unless explicitly changed, imported, pending, running, paused,
`awaiting_rewinding`, and cancelled cards should remain excluded from sales
results and sales printing.

## Candidate Information Set

The final field list is open. The following candidates should be reviewed with
the actual sales/logistics workflow rather than accepted automatically.

### Order and customer context

- order number;
- order date and delivery date;
- customer and city;
- product/type;
- product form;
- material and size/thickness;
- packaging method;
- ordered gross kilograms, rolls, metres, and units where useful; and
- relevant operational notes, if they are appropriate for sales visibility.

### Production summary

- card status and whether the values are provisional or reviewed;
- machine;
- first production start and extrusion finish time in `Europe/Sofia`;
- total production duration, if useful to sales/logistics;
- final extrusion shift, if useful;
- count of produced gross rolls;
- total gross weight;
- total net weight;
- tare summary; and
- pallet summary, including unassigned rolls where applicable.

### Roll detail

- roll number;
- gross weight;
- snapshotted tare weight;
- calculated net weight;
- optional pallet number; and
- shift attribution only if sales/logistics has a concrete use for it.

Recipe details, actual materials, timing-segment corrections, import metadata,
card version values, internal IDs, queue sequence, and other operational data
should not be exposed merely because Admin can see them. Their inclusion must
have a stated business reason.

## Search, Filtering, And Ordering Decisions

The dashboard will need a bounded list rather than loading unlimited history.
Candidate controls include:

- order number search;
- customer search;
- product search;
- produced/finished date range;
- delivery date range;
- completed versus archived status;
- machine, only if useful; and
- newest finished cards first by default.

The exact filters, default period, pagination size, and empty-search behavior
remain open. Searches should be server-side, parameterized, and bounded so the
page remains fast as completed-card history grows.

## Printing And Document Templates

Printing is a core requirement, but the required sales/logistics templates have
not yet been described. Each template needs its own explicit contract.

For every requested template, decide:

- business name and purpose;
- whether it covers one card, multiple selected cards, or a date/customer
  group;
- exact fields and labels;
- roll-level detail versus totals only;
- grouping and sort order;
- whether pallet summaries appear;
- paper size, portrait/landscape orientation, margins, and page-break rules;
- whether the output is browser print HTML, downloadable PDF, CSV, or another
  format;
- whether the existing two-page operational-card format is reused, adapted, or
  completely separate;
- how blank or unavailable values render;
- whether completed/provisional cards may be printed; and
- whether a document needs a visible generated-at time or review-state label.

The existing operational-card print renderer may provide trusted calculations
and layout utilities, but Task 18 must not turn it into an unrestricted generic
report framework. Sales-specific documents should have explicit templates and
tests.

Opening or printing a sales document should not change card state. If the
business later requires recording who printed what and when, that becomes a
separate write/audit feature and cannot be called strictly database read-only.

## Current-Data And Correction Behavior

The recommended prototype reads the current saved data on every request.
Therefore:

- a later permitted Admin correction to a completed or archived card appears
  on the next sales page load;
- totals and print output are derived from the current corrected roll ledger;
- no stale reporting snapshot needs to be synchronized; and
- browser refresh is sufficient to see new production results or corrections.

Whether sales needs a visible warning that previously printed information may
have changed remains open. Solving that with durable document versions or print
history would add persistence and audit scope, so it should not be implied by
the first prototype.

## Deliberately Deferred Security Work

The security discussion produced a viable later architecture, but the user
explicitly asked not to implement or further develop it during this prototype
phase.

The proposed later workstation access matrix was:

| LAN client | Admin | Terminal | Sales reports |
| --- | ---: | ---: | ---: |
| Two Shift Manager PCs | Allowed | Optional | Allowed |
| Extrusion workstation | Blocked | Allowed | Optional |
| Aparkey sales/logistics PC | Blocked | Blocked | Allowed |
| Other LAN computers | To be decided | To be decided | To be decided |

This matrix was illustrative and was not fully confirmed, particularly for
other LAN computers and whether Shift Manager PCs should also use Terminal.

The recommended later network design is:

1. Give approved workstations stable LAN addresses through DHCP reservations.
2. Bind the underlying FastAPI/Uvicorn service to loopback so LAN clients
   cannot bypass the gateway and connect directly to port `8000`.
3. Put Nginx or another small reverse proxy in front of the app.
4. Apply allow/deny rules independently to `/admin`, `/terminal`, and `/sales`.
5. Deny unmatched access by default.
6. Include every mutation and print route in the correct protected namespace;
   protecting only menu pages is insufficient.

If stronger database isolation is later desired, the sales router/query layer
can be mounted in a separate FastAPI process that opens SQLite with URI
read-only mode plus `PRAGMA query_only`. The current `/sales` namespace and
component separation are intended to make that extraction practical.

IP restrictions identify a computer, not a person. Anyone using an approved
Shift Manager PC would have that PC's access. Stable DHCP reservations are
required, and IP/MAC controls are not equivalent to user authentication. A
future named-user login and role model would be more robust and auditable but
would be a larger scope than the current LAN pilot requires.

None of the following is part of the current functional prototype:

- Nginx or another reverse proxy;
- firewall changes;
- DHCP reservations or static client addressing;
- IP allowlists;
- a second reporting service or port;
- SQLite operating-system read-only permissions;
- usernames, passwords, sessions, roles, or permissions;
- Tailscale;
- security audit logging; or
- claims that an unlinked or hidden route is secure.

## Security-Ready Decisions To Preserve Now

Although enforcement is deferred, these low-cost boundaries should be part of
the functional implementation:

- Keep all sales pages and sales printing below `/sales`.
- Do not link sales pages to Admin or Terminal.
- Do not place sales actions in Admin or Terminal templates.
- Use only GET routes for view, search, and print behavior.
- Keep visibility rules in one explicit sales-status allowlist.
- Keep sales SQL/read functions separate from mutation functions.
- Reuse calculation functions, not editable Admin page contexts containing
  unrelated internal data and actions.
- Use a dedicated sales template base so later access/login presentation can be
  added at one boundary.
- Do not scatter client-IP checks through route handlers.
- Do not add user/role fields to production tables for this prototype.
- Keep future authorization outside the report calculation and template logic.
- Add sales print routes under `/sales` even if they call existing internal
  print assembly.

These are maintainability and future-isolation decisions, not substitutes for
security.

## Validation And Error Behavior

The detailed wording is still to be designed, but the implementation should
handle at least:

- unknown card ID with a clear not-found response;
- card exists but is not sales-visible with no leakage of its hidden details;
- invalid or excessive filter values with bounded user-visible validation;
- a card that changes status between list and detail requests;
- no matching results;
- malformed historical weight/timestamp data without generating a misleading
  print document;
- a card that does not satisfy the selected template's print requirements;
- more roll or pallet-summary rows than fit a template page; and
- later Admin corrections appearing consistently in screen totals and print
  totals.

The dashboard must not recover from malformed production data by silently
changing it, inventing values, or bypassing existing print-readiness rules.

## Testing And Verification Expectations

When implementation is approved, automated tests should prove at least:

1. Only the approved statuses appear in sales list queries.
2. A hidden-status card cannot be retrieved through a guessed sales detail or
   print URL.
3. Search, filters, ordering, and pagination follow the approved contract.
4. The detail page shows the approved fields and no edit forms/actions.
5. Roll numbers, gross weights, tare weights, net weights, totals, and pallet
   summaries match the current canonical calculation behavior.
6. Admin corrections are reflected on later sales reads without a duplicate
   data store.
7. Sales routes do not mutate card versions, timestamps, statuses, roll rows,
   timing, or any other database content.
8. No sales POST route exists.
9. Sales print eligibility and output match the contract of each template.
10. Invalid or non-visible card IDs fail safely without disclosing hidden card
    details.
11. Existing `/admin`, `/terminal`, and operational-card print behavior remain
    unchanged.
12. The functional dashboard does not require or mutate the real runtime
    database during tests.

Because this is UI work, verification must also use the live FastAPI app with a
temporary SQLite database and the repository-local Playwright installation.
At least one relevant screenshot must be saved under a dedicated directory such
as:

```text
artifacts/ui-checks/sales-reporting-dashboard/
```

Browser verification should cover the agreed sales desktop viewport, list and
detail navigation, at least one populated roll ledger, empty results, and every
approved print template. Print/PDF page geometry should be measured when the
template contract requires fixed pages.

## Data And Migration Assessment

The expected first-prototype migration decision is **No migration** if Task 18
only reads existing card/roll/timing/shift/pallet fields and renders pages or
documents.

No existing production value needs to be converted, backfilled, copied, or
reinterpreted merely to provide a read-only dashboard. A new reporting database
or cached summary table is not recommended.

This expectation changes if later decisions add any persisted concept, such as:

- print/view audit records;
- saved report presets;
- document revisions or immutable generated-document history;
- sales approval/review state;
- dispatch/shipping state; or
- user/role/session records in SQLite.

Implementation must inspect the final diff and complete the formal migration
assessment required by
`docs/implementation-notes/sqlite-migration-and-deployment-playbook.md`.
Documentation alone does not trigger a migration assessment or create a
migration record.

## Authoritative Specification Alignment

The repository-root `README.md` currently describes the confirmed pilot as
having only `/terminal` and `/admin`, says printing/reprinting is a Shift
Manager/Admin action, and excludes users, roles, login, and permissions. Task
18 changes the first two functional boundaries but deliberately leaves the
authentication exclusion in place for the prototype.

Before Task 18 implementation begins, the approved functional design should be
reflected in the authoritative `README.md` and then reconciled with the
repository-root `AGENTS.md`. The narrow intended update is:

- add the `/sales` read-only reporting surface;
- allow its approved finished-card document templates to be printed by the
  sales/logistics user;
- retain Admin-only editing, operational-card administration, and production
  correction;
- state that prototype read-only behavior is not enforced authorization; and
- keep authentication, roles, IP restrictions, reverse-proxy rules, and other
  security infrastructure deferred until separately approved.

This Task 18 record preserves the discussion but does not itself silently
rewrite those authoritative project contracts.

## Explicitly Out Of Scope For The First Prototype

- changing or correcting production data from `/sales`;
- importing cards or editing imported order fields;
- machine assignment, release, resequencing, cancellation, restoration,
  archive actions, shift control, or terminal timing actions;
- entering, correcting, or deleting rolls;
- tare, pallet, material, recipe, or timing correction;
- active production control or detailed machine monitoring;
- authentication, authorization, user accounts, roles, sessions, passwords,
  IP restrictions, reverse proxy, firewall, or DHCP configuration;
- Tailscale or public internet exposure;
- direct browser/database access;
- a duplicate reporting database or background synchronization;
- write-back to the Shift Manager Excel workbook;
- shipping, dispatch, delivery, inventory, costing, or ERPNext workflows;
- package/pallet lifecycle or cross-card packages;
- automatically treating a print as approval, archive, dispatch, or another
  business event; and
- a generic user-configurable report builder.

## Open Decisions Before Design Approval

Resolve these decisions in order, one question at a time:

1. **Visibility point:** show both `completed` and `archived` with a clear
   provisional/final distinction, or show only archived/reviewed cards.
2. **Exact fields:** approve the list-page summary fields and the detail-page
   fields; reject Admin-only operational/internal fields that sales does not
   need.
3. **Search and filters:** choose required fields, default ordering, default
   date range, pagination, and empty-filter behavior.
4. **Roll presentation:** choose the visible roll columns, totals, pallet
   grouping, and whether shift attribution has a sales use.
5. **Print-template inventory:** list every required document and provide or
   describe the current inefficient output/reference that each replaces.
6. **Template contracts:** decide paper format, grouping, fields, page breaks,
   labels, browser/PDF/CSV output, and provisional-card eligibility for each
   document.
7. **Corrections:** decide whether a visible provisional label is sufficient
   when completed-card values may later be corrected, and whether archived
   cards are considered final for sales purposes.
8. **Downloads:** decide whether browser printing is sufficient or whether PDF
   and/or CSV download is required.
9. **Dashboard device:** identify the expected sales PC display size and
   browser so the responsive verification target is concrete.
10. **Language and naming:** confirm the Bulgarian user-facing name for the
    dashboard and its navigation/actions.
11. **Audit behavior:** confirm that the prototype should record nothing when a
    card is viewed or printed, as currently recommended.
12. **Future access matrix:** defer implementation, but later confirm which LAN
    computers may reach Admin, Terminal, and Sales when security work resumes.

## Recommended Next Design Sequence

1. Decide the visible lifecycle statuses and provisional/final semantics.
2. Review one representative finished card and select the exact sales fields.
3. Sketch and approve the list/search workflow.
4. Sketch and approve the read-only detail workflow.
5. Inventory the required print templates and design them one at a time.
6. Present the complete architecture, data flow, error behavior, and test
   contract for approval.
7. Write a scoped implementation plan only after the functional design is
   approved.
8. Implement and verify using temporary databases and live Playwright evidence.
9. Run the migration assessment on the actual completed diff.
10. Leave network security deferred until the user explicitly reopens it.

## Prototype Success Criteria

The functional prototype is successful when:

- Aparkey can find the required finished card without using `/admin`;
- the page shows the agreed sales/order context and current production output;
- roll-level and total gross/net information matches the canonical saved data;
- every agreed business document can be printed efficiently and correctly;
- the sales UI provides no production editing action;
- viewing and printing do not mutate production data;
- later Admin corrections appear consistently on refresh;
- the feature remains bounded to extrusion-card reporting;
- focused tests and live browser/print verification pass against temporary
  SQLite data; and
- the route/query/template boundaries leave a clear insertion point for later
  LAN restrictions or authentication.

## Resume Condition

Resume the Task 18 design with the first open decision: whether sales should
see both completed and archived cards with a provisional/final distinction, or
only archived cards after Shift Manager review. Continue through the remaining
questions one at a time before preparing an implementation plan.
