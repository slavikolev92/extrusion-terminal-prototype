# Task 69: MES Software

Status: high-level scope discovery closed on August 14, 2026. This document is
the durable record for the centralized production-planning and manufacturing-
execution successor. The project is ready for formal system design and slice-
by-slice implementation planning. A revised AI-only delivery estimate is
recorded below. This record does not by itself authorize implementation,
deployment, production-data migration, inventory posting, or changes to the
existing extrusion-terminal pilot.

The proposed system is a possible successor to the two Shift Manager workbooks
and the operation-specific terminal prototypes. It must be designed as a
separate product decision. It must not silently expand the current bounded
extrusion pilot, whose authoritative scope remains in `README.md`.

## Desired Business Outcome

Provide one reliable place to:

- create and maintain production orders and their shared planning data;
- define which operations each order requires and in what order;
- hold the operation-specific instructions currently stored in Excel;
- plan, assign, sequence, release, and execute operational cards;
- send each operation only the information its workers need;
- capture actual quantities, time, materials, and corrections at the source;
- show the current state of orders and operational cards;
- use current material/item records when planning recipes and inputs;
- expose clean production facts to separate costing and reporting processes;
  and
- remove repeated CSV export, import, and manual transcription once the new
  system is proven.

The intended product is custom data-capture software with production planning
and execution functionality, not an ERP and not an attempt to automate every
possible manufacturing outcome.

## Confirmed End State: No Excel Dependency

The final system replaces the Shift Manager workbooks as operating systems of
record. Excel is not part of the target-state workflow.

The MES becomes the canonical holder of:

- production orders and shared planning fields;
- required operation routes and operation-specific planned specifications;
- released and completed operational cards;
- terminal-entered execution data;
- actual quantities, time, materials, batches, waste, and corrections; and
- any make-to-stock relationship or balance that remains a real business need.

The current `Actuals Entry`, `ActualsData`, `ActualsMaterials`, and
`MTS Balances` worksheets are therefore migration evidence, not end-state
components to preserve as Excel processes. Their useful business facts and
rules should move into the appropriate MES or inventory records. Workbook-only
helpers, positional dependencies, refresh macros, and duplicate repositories
should disappear.

Paper remains necessary as an operational contingency, not as a parallel
system of record. The final application must still be able to print the
required operational card with the same usable content as Excel. If workers
complete a card on paper because the digital process is unavailable, the
system must provide a deliberate after-the-fact entry workflow for recording
that completed card when service is restored.

That contingency workflow should eventually define:

- how the printed card carries an unambiguous production-order and operational-
  card identity;
- which planned revision was printed;
- who may transcribe completed paper actuals;
- how the record is identified as paper-origin/recovery entry;
- how it is reviewed for completeness; and
- how a duplicate digital completion is prevented.

The exact controls are still to be designed. The confirmed boundary is that
paper provides redundancy while the MES remains canonical after recovery.

## Confirmed Production-Order Ownership

The two current Shift Manager workbooks are not cleanly divided by operation.
The practical starting split is material-based:

- Shift Manager 1 generally owns polyethylene orders and has primary knowledge
  and responsibility for extrusion.
- Shift Manager 2 generally owns polypropylene orders and has primary knowledge
  and responsibility for printing.
- Printing can appear on orders created by Shift Manager 1.
- Rewinding/slitting and confection are shared across both managers.

This material split describes who normally creates an order. It should not be
implemented as a rigid rule that polyethylene orders can only contain one set
of operations or that printing orders belong automatically to one manager.

The durable ownership rule is simpler:

1. The Shift Manager who creates a production order owns and remains accountable
   for the complete production order.
2. Ownership covers the entire ordered route and all of its operational cards,
   including operations usually understood or conducted by the other manager.
3. Sending or discussing an operational card with the other Shift Manager does
   not transfer ownership of the order.
4. The managers may collaborate informally, including working together at one
   manager's computer when specialist knowledge is needed.
5. The application does not need delegation, transfer, task-assignment, or
   per-operation acceptance workflows between Shift Managers.

The system should therefore store one production-order owner/creator for
accountability, while treating operation knowledge and execution as separate
from order ownership.

Ownership is an enforced Shift Manager data boundary. A non-owning Shift
Manager has no visibility into and no editing access to the other manager's
production orders or private planning records outside the deliberately shared
operation-dispatch surface described below. The manager must not see the other
owner's order lists, order details, unreleased operational-card plans, or
private planning status. Informal collaboration does not create delegated
access; if the other manager's knowledge is needed, the owner remains
responsible for entering or approving the plan through the owner's own
workspace.

The application may use one central deployment and database, but each Shift
Manager's planning workspace must be logically partitioned by owner. Enforcing
that isolation requires the future system to distinguish the two managers
reliably; the current extrusion pilot's unauthenticated route separation is not
sufficient for this requirement.

This decision concerns Shift Manager planning/edit access. Terminal operators'
ability to execute a released operational card and any exceptional
administrator recovery authority are separate permission questions.

## Confirmed Numbering And Migration Boundary

The two current workbooks cannot produce conflicting historical production-
order numbers. Their numbering ranges were deliberately separated when the
managers began working independently: one manager uses the lower range and is
currently around `15,000`, while the other uses the higher range and is
currently around `25,000`.

Historical and future numbering have different rules:

- A migrated production order keeps its existing business order number exactly
  as recorded.
- Historical orders are not renumbered merely to fit the future sequence.
- Each production order also receives a stable internal system identity.
- After cutover, both Shift Managers use one shared centrally controlled
  sequence for new business order numbers.
- A manager can see the latest/highest allocated number or the next number
  available for creation without seeing the other manager's order that consumed
  the preceding number.
- The server allocates the number centrally when the new order is created, so
  simultaneous creation cannot issue the same number twice.
- The exact first number in the new shared sequence is a cutover configuration
  decision, not a new numbering domain per manager.

Migration is deliberately limited:

- The system will not migrate the entire workbook history.
- July 1, 2026 is the confirmed source-data cutoff because the workbooks and
  process were reshaped into their current more-normalized form on that date.
- Data before July 1, 2026 is considered unreliable for migration and remains
  outside the new operational database.
- Only the useful normalized orders and related records created on or after the
  cutoff are candidates for import.
- Included records may be cleaned or normalized during a controlled migration;
  this is considered manageable because the migration population is small and
  recent.
- Existing numbers from both ranges are preserved, and the new shared sequence
  begins only for future orders after cutover.

Legacy route flags inside the limited migration population should be corrected
to the new ordered-route representation during migration preparation. The MES
should not guess operation sequence from ambiguous `да` flags at runtime.

### Confirmed Cutover And Legacy-Reference Boundary

Rollout uses one explicit cutover date; October 1, 2026 is an illustrative
target rather than a committed date. Before cutover, the business continues
collecting normalized workbook data that may be migrated. At cutover:

- all new production orders, operational cards, planning changes, execution,
  and actuals are entered only in the MES;
- the migration transfers as much reliable, useful structured information as
  practical from the post-July 1 workbook population;
- Excel becomes a read-only legacy information source and is not kept current;
- there is no dual writing, field-level source ownership, synchronization, or
  conflict resolution between Excel and the MES;
- legacy orders omitted from the bulk migration may be recreated in the MES by
  a Shift Manager when they become operationally useful; and
- an old Excel order may supply the static information for a new MES order or
  duplication template, but production may proceed only from the MES record.

The simplest post-cutover mechanism is ordinary MES order creation or
duplication using the legacy workbook as reference. A narrow migration import
may be retained if it saves real manual entry, but the product does not require
a permanent general-purpose Excel synchronization layer or complete historical
conversion.

## Confirmed Shared-Operation Dispatch Boundary

Printing, rewinding/slitting, and confection can receive operational cards from
both Shift Manager ownership domains. Their dispatch planning is shared even
though the underlying production orders are private.

The confirmed working model is:

1. Only the owning Shift Manager creates, edits, and releases an operational
   card from the private production-order workspace.
2. Once released to a shared operation, the card appears in that operation's
   shared queue together with released cards from both owners.
3. Both Shift Managers can see the minimum card summary needed to understand
   and plan that shared queue.
4. Both Shift Managers can reorder the shared queue, including changing the
   relative priority of a card owned by the other manager.
5. Reordering is dispatch metadata; it does not grant access to edit the other
   manager's production order, recipe/specification, quantities, notes, or
   operational-card content.
6. The originating Shift Manager retains ownership of the card and is the only
   Shift Manager who may change or withdraw its content.
7. Operators at the shared operation terminal can execute any card released to
   their operation, regardless of which Shift Manager owns it.
8. The two Shift Managers resolve shared priorities through direct
   communication. The MES does not need a separate dispatcher, delegation
   workflow, or inter-manager approval process.

This is a narrow capability-based exception to planner isolation: shared queue
visibility and queue ordering are shared; every other production-order,
operational-card, and scheduling action remains owner-only. The non-owner
cannot assign or change a machine/resource, edit the plan, change card content,
release, withdraw, cancel, or correct the other manager's card. Queue changes
still require concurrency protection so one manager cannot silently overwrite
a reorder made by the other.

There are no cross-manager change requests, permission requests, approval
notifications, ownership transfers, or temporary edit grants. If a change is
needed, the managers communicate directly and the owner makes it.

## Confirmed Simplification Direction

The following direction came from the initial August 14 discussion and should
be retained unless the user later changes it:

- Do not build costing into the MES. The MES records facts; a separate process
  calculates costs.
- Do not make accounting, invoicing, sales, or a full ERP prerequisites for
  production execution.
- Do not automatically decide which finished item was produced from every
  production event.
- Do not require a fully automated material-transformation or product-lineage
  engine.
- Prefer a deliberate Shift Manager confirmation when an operation's output or
  final stock item is ambiguous.
- Keep make-to-order and make-to-stock behavior simple and explicit.
- Use planned recipe quantities for material-demand visibility.
- If completed production is connected to raw-material inventory, theoretical
  consumption is based on the effective recipe and actual produced quantity;
  exact costing and physical-stock reconciliation remain separate concerns.
- Preserve human correction paths instead of attempting to predict every
  interruption, short run, split, substitution, rework, or changed output.

These simplifications remove much of the failed ERP design's combinatorial
business logic. They do not remove the need for stable identities, explicit
states, safe corrections, concurrent-edit protection, or recoverable data.

## Confirmed Completion Review And Material Posting

Raw-material inventory is updated at the end of an operational card, not
continuously during execution. Finishing machine work and confirming its
inventory effect are two explicit states:

1. The operator finishes the operational card and records the operation's
   execution actuals.
2. The card enters `awaiting_shift_manager_review` and has not yet affected
   inventory.
3. The owning Shift Manager reviews the output and the proposed or entered
   consumption lines.
4. Submitting the review marks the card reviewed and creates the linked
   inventory issue in one atomic action.

For extrusion, the system may prefill theoretical consumption from the actual
produced net kilograms and the effective recipe:

```text
suggested consumption = actual produced net kg × effective recipe percentage
```

This is a convenience calculation, not a claim of measured physical usage. The
Shift Manager can change the selected material and quantity before submission
when the recipe was not followed exactly or a material was substituted.

For printing, rewinding/slitting, confection, and any other case where
consumption is not unambiguously derivable, the MES does not invent allocation
logic. The Shift Manager selects the material and enters the consumed quantity.
The review must also support an explicit confirmation that no tracked material
was consumed, so an empty form cannot be mistaken for an unfinished review.

The submitted rows become the declared consumption facts used by inventory and
later costing. The MES does not require real-time backflushing, reservations,
work-in-progress movements, automatic variance allocation, or automatic
costing. One card can post no consumption or multiple material lines, each with
a stable material identity, quantity, unit of measure, and reference to the
card and review.

Submitting the same review twice must not deduct stock twice. A later correction
must preserve the original posting and create a linked reversal/replacement or
adjustment rather than silently rewriting inventory history. This can remain a
single simple `Correct posting` action in the Shift Manager interface; the
integrity behavior belongs behind that action.

Review-time checks should remain small and advisory. The system may warn when:

- an operation or product that normally consumes an input film/material has no
  declared input;
- declared material does not match the planned recipe or expected input
  category;
- a theoretical extrusion quantity differs materially from the manager's
  declaration; or
- the posting will take an inventory balance below zero.

These warnings help the Shift Manager spot an incorrect material, missing input,
or suspicious quantity before submission. They do not require the MES to infer
what physically happened and do not block a deliberate confirmation. Only
structurally invalid data—such as an unknown material, invalid unit, non-positive
quantity, incomplete material row, or duplicate posting—is rejected.

Inventory balances are allowed to become negative. Production that already
happened must still be recordable even when the current inventory ledger is
wrong. A negative balance is visibly flagged for investigation. If the cause is
an incorrect operational-card posting, the Shift Manager corrects that posting;
if no source error can be identified, an authorized reconciliation adjustment
brings the balance back to the verified physical quantity. Reconciliation does
not rewrite the original production or inventory entries.

## Confirmed Make-To-Stock And Output Boundary

The MES must not create a work-in-progress inventory item after every completed
operational card. Doing so would turn every route step, partial card, and
correction into an unnecessary receipt-and-consumption chain.

The initial scope therefore distinguishes three cases:

1. **Ordinary make-to-order route:** operational cards record their output
   actuals, but intermediate cards do not create inventory items. Initial scope
   also does not require a finished-goods inventory, dispatch, sales, or
   invoicing process for the final customer item.
2. **Make-to-stock source order:** the order deliberately produces a reusable
   base item, such as an unprinted film roll that will feed more than one later
   customer order. Its reviewed production output creates or increases a
   make-to-stock source lot linked to that production order.
3. **Deliberate early-finalization exception:** if the remaining route is
   stopped and the current intermediate output is intentionally treated as a
   standalone item, the owning Shift Manager may explicitly declare that
   outcome, its reason, item identity, and quantity. No such item is inferred
   merely because a card stopped. If general output inventory is deferred, this
   exception can remain a production-output declaration rather than a stock
   receipt.

The required make-to-stock model is a small source-lot ledger, not a general
work-in-progress or finished-goods warehouse:

- the source production order identifies the make-to-stock lot and produced
  item;
- reviewed output quantities from that source increase its produced quantity;
- a later consuming card explicitly selects the source make-to-stock order and
  declares the quantity consumed;
- more than one production order may consume from the same source;
- the remaining balance is derived as `reviewed produced quantity - linked
  declared consumption`; and
- corrections and reconciliations preserve the same ledger history rules as
  other inventory postings.

This directly replaces the useful business role of the workbook's
`MTS Balances` and `Source MTS production order` fields. It supports costing and
shared-base production without introducing automatic WIP transformation,
dispatch, sales, invoicing, or full finished-goods inventory.

### Confirmed Production-Order-Specific MTS Identity

The initial system does not need a governed code that pools technically
interchangeable make-to-stock outputs. Every make-to-stock source production
order is its own selectable output identity and balance. The small number of
simultaneously open items makes this deliberate duplication operationally
acceptable.

A consuming card can use one or more source production orders. For example, if
two source orders each have `100 kg` and a later order consumes all `200 kg`,
the ledger records two consumption lines:

```text
source order A: -100 kg
source order B: -100 kg
```

The consuming order's material value is later the sum of the values taken from
both sources. Each source is costed separately before the consuming order:

```text
consumed input value = Σ(quantity from source order × source-order unit cost)
```

No MES weighted-average layer, common-item pool, FIFO allocation, or shared
interchangeability code is required. A future costing or inventory module can
introduce pooling later without changing the existing source-order ledger
facts.

Source valuation remains anchored to the source production event rather than
the later consumption month. In the example provided, output produced in July
uses the applicable fixed input and operation prices from June even when a
customer order consumes it in September. The MES records the source order,
completion date/production period, declared material inputs, operation actuals,
output quantity, and downstream consumption links. The separate costing process
may calculate the monetary value later from those durable facts.

The workbook's `±5 kg` hiding rule is not needed in the app. Exact nonzero
balances remain visible until corrected or reconciled. During the monthly
costing/reconciliation cycle, small residuals can be adjusted to the verified
balance so the normal open list clears through actual ledger entries rather
than a display tolerance.

## Confirmed Order Creation, Duplication, And Manual Release

Operational-card creation and dispatch remain under direct Shift Manager
control. The system does not infer route progression or automatically release
work after another card completes.

There are two normal ways to establish a production order:

1. **Create new:** the owning Shift Manager enters the order and explicitly
   chooses which operations are present.
2. **Duplicate existing:** the system copies the existing order's recurring
   planned route and operation-specific planned recipe/instructions as the
   starting point for the new order.

Duplication is a planning convenience, not a copy of production history. It
must not copy card status, terminal release, resource assignment, queue
position, execution timing, output actuals, declared consumption, review,
corrections, or other completed-production facts.

An owning Shift Manager may add an operation after order creation, including
during production. Each added operation is deliberately classified as either:

- **recurring route operation:** part of the normal planned route and therefore
  eligible to be copied when this order is later duplicated; or
- **supplementary operation:** a one-off response to an exceptional event, such
  as additional rewinding/slitting after a problem. It remains recorded on that
  order but is excluded from later duplication.

For every planned or supplementary card, the owning Shift Manager explicitly
chooses when to release it to a terminal queue or when to print and issue a
paper card. Card completion, Shift Manager review, inventory posting, and
completion of an earlier route step never release another card automatically.
Operation ordering and readiness remain human planning decisions because the
correct sequence depends on the product and current production circumstances.

Terminal workers may finish the execution portion of a released card. Where
required actuals are outside their knowledge—such as printing material
consumption—the result enters Shift Manager review. The owner supplies or
verifies the missing information and approves the card, without that approval
triggering the next operation.

The core Shift Manager planning surface therefore needs to show the order's
route and card states and provide deliberate actions to add, edit, print,
release, withdraw, and prioritize work. It does not need a rules engine for
automatic route release.

## Confirmed LAN Deployment And Outage Boundary

The MES is one centrally served factory-LAN web application. Shift Manager
computers and terminal kiosks are clients of the same application and database;
the terms `online` and `offline` do not refer to public internet access here.
Normal operation requires the central LAN service to be available.

There is no terminal-local production database, disconnected write queue, or
later data synchronization/merge process. If a terminal cannot reach the
server, it does not continue writing to a separate copy.

The intended operational stack follows the proven extrusion-terminal pattern:

- the physical server automatically boots after power returns;
- the Proxmox host starts the application VM;
- the VM starts the MES service;
- terminal hardware automatically boots and opens its assigned page in kiosk
  mode; and
- previously persisted production state remains available after restart.

A factory-wide power loss stops the server, terminals, and production machinery,
so no concurrent digital production activity exists that would later need to be
synchronized. The important technical requirements are automatic restart,
immediate persistence of completed actions, backups, restore procedures, and
clear recovery checks after service resumes.

If production equipment remains usable while the server, network path, or an
individual terminal is unavailable, printed operational cards are the bounded
fallback. Work completed on paper is entered through a deliberate recovery form
after the MES becomes available. The recovery entry carries the existing order
and card identity where available, records that it originated from paper, and
checks for duplicate digital completion. No automatic reconciliation engine or
offline conflict merge is required.

Operational documentation must cover server/app restart, VM and service health,
terminal kiosk restart, backup/restore, temporary paper operation, and later
paper-card entry. These are recovery procedures for one central system, not an
offline architecture.

If the primary server is unavailable but an alternate powered computer and
printer can be used, an administrator may manually start the recoverable app on
that computer to access and print cards. This is a documented low-tech recovery
option, not automatic failover or a second live database. Paper operation and
later entry remain sufficient if that recovery is not immediately possible.

## Confirmed Accounts, Kiosks, And Shift Attribution

The initial access model is intentionally small:

- each Shift Manager has one named account;
- one administrator/recovery account can access and correct everything across
  owner workspaces;
- each operation kiosk has one fixed account that remains signed in and is
  restricted to that operation's terminal workflow; and
- terminal operators do not have individual accounts.

Kiosks are operation-specific rather than cross-functional. The kiosk identity
determines which operation queue and card interface it displays—for example,
extrusion, printing, rewinding/slitting, or confection. One kiosk is expected
for each operation in initial scope; exact machine selection within that
operation remains part of its terminal workflow where needed.

Shift attribution does not require worker authentication. The operation records
the active production shift using the same simple direction proven by the
extrusion terminal: a shift is explicitly started/changed, and kiosk production
actions are linked to that active shift. A separately maintained shift-roster
CSV can identify which workers belonged to each shift when reporting requires
names.

Manager actions are attributable to the named manager account. Kiosk actions
are attributable to the fixed operation kiosk and active shift, not to a
specific operator. The MES does not need employee accounts, per-worker
passwords, badge scanning, operator permission matrices, or operator-level audit
history.

## Confirmed Modular Application Boundary

The MES is one deployed application and one database with several internally
separated business modules. Inventory is one of those modules; it is not a
separate application, service, database, or synchronization domain.

“Separate module” means operational and permission isolation:

- inventory has its own screens, navigation, application code, transaction
  rules, and role checks;
- inventory visibility and inventory modification are separate account
  capabilities rather than consequences of a fixed job title;
- an account with visibility only can observe the inventory dashboard, active
  material catalogue, balances, and other published stock information but
  cannot open inventory transaction-entry actions;
- an account with inventory-modification capability may receive stock, record
  consumption, remove disposed/sold stock, and reconcile balances, subject to
  normal validation and attribution;
- a named inventory user can be restricted to those inventory capabilities and
  cannot open or modify Shift Manager planning, operational-card content, or
  terminal execution screens;
- Shift Managers receive the visibility needed for planning and may also be
  granted inventory-modification capability when the business wants them to
  perform that separate process;
- a Shift Manager's reviewed operational card may invoke the narrow inventory
  consumption-posting function without granting that manager the general
  inventory-maintenance workflow;
- the administrator/recovery account retains access to every module; and
- internal module boundaries prevent unrelated inventory changes from mutating
  production records, while explicit linked actions retain their production-
  card references.

Keeping the module in the same application and database allows reviewed card
completion and its inventory issue to be committed atomically. It also avoids a
network API, duplicated authentication, synchronization, and partial failure
between two applications. Inventory can still be designed, tested, navigated,
and operated as a separate business process.

## Confirmed Minimal Raw-Material Inventory Ledger

The initial raw-material inventory is a quantity ledger with exactly four
business transaction types:

1. **Receipt:** add a declared material quantity to stock.
2. **Operational-card consumption:** subtract the material quantity confirmed
   during Shift Manager review and link it to the operational card.
3. **Disposal or sale removal:** subtract material that is scrapped, discarded,
   or sold off instead of used in production.
4. **Reconciliation adjustment:** add or subtract the quantity needed to align
   the ledger with verified physical stock.

A disposal/sale removal is an inventory disposition, not a sales workflow. It
needs the material, quantity, date, reason/type, responsible account, and an
optional note or external reference. The MES does not need a customer order,
dispatch, invoice, payment, revenue-recognition, or profit calculation merely
because unwanted stock was sold. Any monetary proceeds can be captured by the
separate invoice/cost-tracking process if required.

Every transaction is retained as a dated ledger entry. Corrections use a linked
reversal/replacement or adjustment instead of editing historical balance
directly. Current stock is derived from all receipts and positive adjustments
minus production consumption, disposal/sale removals, and negative adjustments.
As already confirmed, this balance may become negative and remains visible for
investigation and reconciliation.

The dashboard shows two deliberately separate quantity views:

- **current recorded balance:** the quantity derived only from posted inventory
  ledger entries; and
- **projected balance:** the current recorded balance minus the theoretical
  material requirements of the planned/released operational cards included in
  the planning view.

Projection is informational. It does not reserve, allocate, or deduct material,
and it creates no inventory transaction. When reviewed actual consumption is
posted, the ledger balance changes and that card no longer contributes the same
unposted demand to the projection. Catalogue-active status remains a separate
fact from both quantities. This is a small derived query and dashboard display,
not a separate planning engine or material-requirements module.

The initial inventory does not include reservations, purchase-order workflow,
warehouse transfers, automated allocations, automatic replenishment, or MRP.
These are excluded rather than deferred requirements; they should be added only
if a future real process independently justifies them.

## Confirmed Generic Non-Extrusion Execution Flow

For printing, rewinding/slitting, and confection, the terminal execution flow is
the same small set of actions:

1. The owning Shift Manager manually releases the card to the operation queue.
2. The operation starts the card.
3. The operation may pause and resume it.
4. The operation finishes the execution work and records the terminal-known
   output facts.
5. Where additional information is required, the owning Shift Manager reviews
   the result, supplies missing actuals such as consumed materials, and approves
   the completed card.

There are no further operation-lifecycle states or automatic downstream actions
for these departments. They may display different planned instructions and ask
for different output/material fields, but those are bounded form differences,
not separate workflow engines.

Extrusion retains its already-proven operation-specific extensions—recipe,
roll/tare/net, pallets, and bounded rewinding-return handling—without imposing
those extensions on the three simpler operation terminals.

## Confirmed Summary And Terminal Actuals Contract

Excel parity requires every operation to support Shift Manager entry of the
summary facts from a completed paper operational card before its digital
terminal exists. This is also the permanent recovery path when a terminal or
central service was unavailable.

The system must not make a Shift Manager reproduce terminal-level detail. For
example, a paper confection card may be entered as total gross weight, total
tare, total net weight, and the other required summary quantities. The manager
does not enter every box, container, or unit event merely so the software can
recalculate the known total.

There is one canonical operational-card actuals contract with several attributed
capture sources:

- **manual summary:** normal Shift Manager entry while an operation has no live
  terminal;
- **terminal detail:** detailed rolls, boxes, containers, units, or other events
  recorded at the machine, from which the same summary is calculated;
- **paper recovery:** exceptional post-outage transcription after a digital
  terminal has become the normal source; and
- **migrated legacy:** normalized actuals imported from the limited workbook
  population with their source recorded; and
- **admin correction:** an attributed correction to summary or detailed facts
  with the previous value/history preserved.

All sources produce the same normalized summary used by Shift Manager review,
inventory posting, costing export, order status, and reporting. Manual gross,
tare, and net totals are validated for consistency. Terminal summaries are
recalculated atomically when their detailed rows change. Detail remains
available where it was actually captured, but it is optional for a legitimate
manual or paper-recovery record.

Each operation has an effective-dated normal capture mode. Before its terminal
go-live date, routine actuals entry uses manual summary. From the agreed cutoff
date—preferably a clean month boundary—routine actuals come from terminal detail.
Historical records retain their original source. The manual form is removed
from ordinary entry after cutoff but remains available through controlled paper-
recovery and admin-correction actions.

This is not duplicated business logic. Source-specific forms call one actuals
service that validates the normalized summary, preserves provenance, applies
optimistic conflict checks, and updates the card transactionally. Operation-
specific detail collectors are adapters around that contract.

## Design Principle: Structured Repository With Soft Rails

The successor sits deliberately between Excel and ERP rigidity:

- stable relational identities, lifecycles, ownership, queue rules,
  permissions, source provenance, and audit history provide the rails;
- Shift Managers can edit order-specific recipes and instructions, choose
  routes, add supplementary cards, release work manually, correct mistakes, and
  handle real exceptions without changing a global process model; and
- the MES does not contain a universal workflow engine, automatic production-
  transformation model, or administrative approval framework.

The system has low algorithmic complexity. Its main engineering complexity is
transactional: several kiosks and managers can read and write related records,
so backend transactions, database constraints, idempotency, and stale-write
protection must keep those records coherent.

## Confirmed Machine Assignment And Kiosk Topology

Operational cards are assigned to named machines/resources. More than one card
may run within the same operation at the same time when different machines are
used, while one machine may have at most one running card.

The initial resource direction includes:

- extrusion machines `1` through `4`, with one currently inactive/offline and
  one extrusion kiosk able to serve all four machine queues;
- printing machines `1` and `2`, with separate nearby kiosks because the
  machines are approximately `30–50 m` apart; and
- confection machines `1` through `4`, with approximately two or three kiosks
  anticipated so the physical work areas can access their queues.

The resource catalogue must allow a machine to be active or inactive without
deleting its identity or history. Exact future kiosk count is configuration,
not a new workflow design.

A kiosk is fixed to one operation but may be configured for one machine or a
small set of machines in that operation. It shows only the configured machine
queues and cards. Multiple kiosks may therefore serve one operation, while no
kiosk needs to switch between operations.

The owning Shift Manager explicitly selects the target machine and queue
position when releasing or reassigning a card. There is no automatic machine
selection or load balancing. Each machine queue follows the proven extrusion
rule: deliberate ordering and no more than one running card per machine.

## Scope-Decision Heuristic

Future scope questions should start with a concrete lowest-complexity
recommendation rather than presenting every technically possible workflow as a
candidate requirement.

Use these rules during discovery:

1. Prefer one clear owner and one clear authority boundary.
2. Do not add delegation, transfer, notification, approval, or merge workflows
   unless a current real process cannot work without them.
3. Prefer direct human communication for rare coordination between two Shift
   Managers.
4. Share only the smallest capability required by a genuinely shared resource.
5. Do not model hypothetical edge cases merely because software could support
   them.
6. When asking for a decision, recommend the simplest safe option and explain
   the material trade-off; ask the user only about a real remaining constraint.
7. Do not turn normal centralized-system mechanics—such as generating unique
   identifiers—into business questions unless the current process supplies a
   conflicting requirement.

For Shift Manager access, this heuristic is now fixed: creator-only control is
the default, and shared queue reordering is the only confirmed exception.

## Evidence Inspected So Far

### Existing Extrusion Terminal

The current FastAPI/SQLite pilot already proves several useful MES concepts:

- persistent import before release;
- machine assignment and ordered queues;
- pending, running, paused, awaiting-return, completed, archived, and cancelled
  states;
- one running card per machine;
- segmented start/pause/resume/finish timing;
- roll-level gross, tare, net, pallet, and shift attribution;
- separate planned recipe and production-entered material data;
- a bounded extrusion-to-rewinding return workflow;
- admin and terminal correction paths;
- optimistic conflict detection and database-enforced invariants;
- non-destructive re-import of planned data;
- print eligibility independent of production completion; and
- SQLite-safe migration, backup, and recovery discipline.

The reusable result is the behavior learned from the pilot, not necessarily its
current database or code structure. In particular, the pilot's single `cards`
record combines production-order, operation-card, dispatch, execution, and
review concerns that a multi-operation system should separate.

### Confirmed Successor-Build Boundary

The production MES will be a new application built from the ground up. The
extrusion terminal remains a bounded discovery pilot and will not be expanded,
converted, or treated as the codebase that the successor must preserve.

This is a clean production implementation, not a second round of discovery:

- the validated terminal workflow, business rules, print behavior, hardware
  deployment lessons, and operator feedback become requirements and acceptance
  references for the new extrusion slice;
- the successor starts with a coherent model separating production orders,
  operational cards, dispatch, execution actuals, review, machines, ownership,
  and inventory-ledger entries;
- existing code may be copied only selectively after review when it is already
  the simplest correct implementation;
- no schema compatibility, in-place upgrade path, or preservation of pilot
  implementation choices is required; and
- delivery proceeds through small vertical slices, with each relevant
  extrusion behavior checked against the proven pilot before cutover.

The successor is a custom factory-LAN application. ERPNext and other rigid ERP
process frameworks are out of scope: adapting the deliberately simple workflow
to their administrative models would recreate the complexity this project is
intended to remove. The current pilot remains the successor's executable
workflow reference rather than its technical foundation.

### Shift Manager Workbook V14.22

Inspected source:

`source-files/Production Orders (Marco) V14.22.xlsm`

The workbook has ten worksheets:

1. `Database`
2. `Actuals Entry`
3. `Technology Cards`
4. `MTS Balances`
5. `ActualsConfig`
6. `RecipeCatalogExtrusion`
7. `ActualsData`
8. `Working Calendar`
9. `MaterialCatalog`
10. `ActualsMaterials`

`Database` contains 46 columns (`A:AT`) and 5,463 populated production-order
rows in the inspected file. Its planning fields are grouped as follows:

| Columns | Meaning |
| --- | --- |
| `A:Q` | Shared order, customer, requested quantity, product, notes, price, make-to-stock reference, and operation-route context |
| `Q:T` | Printing, extrusion, rewinding/slitting, and confection route flags or sequence values |
| `V:AD` | Printing cylinder and up to eight ink/color positions |
| `AE:AO` | Extrusion folding, treatment, recipe check, seven recipe positions, and packaging |
| `AP:AQ` | Rewinding/slitting size and cuttings/waste instruction |
| `AR:AT` | Confection folding, packaging, and ventilation-hole instruction |

The workbook is more than a planning database. V14.22 also contains a small
multi-operation actuals-capture system:

- `ActualsData` stores one row per saved physical operational card and currently
  contains extrusion, printing, rewinding/slitting, and confection records.
- One production order and operation may have more than one operational card.
- Operational cards have stable IDs such as `PO25441-CON-1`.
- Actuals include start/stop, pause and additional time, calculated/overridden
  minutes, gross/tare/net, waste, meters, units, timestamps, and correction
  metadata.
- Additional rewinding/slitting work may be linked to a primary operational
  card.
- `ActualsMaterials` stores material, quantity, unit, and optional source
  make-to-stock production order per operational card.
- `MTS Balances` derives produced, consumed, and remaining make-to-stock
  quantities.
- `Working Calendar` contains operation-specific schedules and holidays for
  calculating working minutes.
- `Technology Cards` renders the four operation card types from the selected
  `Database` order.
- The VBA project includes validation, route analysis, order duplication,
  recipe building, printing, actual-card entry/editing, duplicate warnings,
  working-time calculations, material entry, and make-to-stock balance logic.

The inspected `ActualsData` contains 181 unique cards over 149 production
orders: 128 extrusion, 17 printing, 7 rewinding/slitting, and 29 confection.
Seven are additional cards linked to a primary card. The workbook permits an
additional card after a duplicate warning, but it updates saved cards in place
and has no revision/history ledger.

Additional scope-relevant workbook findings:

- Route data is transitional: 4,931 orders use legacy `да` flags, 530 use
  ordered numeric routes, and two inspected rows mix incompatible forms. A
  centralized model cannot infer route sequence from every legacy row without
  an explicit migration rule.
- `Actuals Entry` scans from a hard-coded worksheet row and stores the mutable
  `Database` row number in `ActualsData`. A centralized system should replace
  this positional link with stable identities.
- Operation time is not uniformly raw elapsed machine time. The workbook can
  calculate scheduled working overlap against operation-specific weekly hours
  and holidays, then subtract pause and add separately entered time.
- The printed common card back contains 120 handwritten roll slots but is not
  populated from `ActualsData`; the paper-detail and aggregate-actuals sources
  are currently separate.
- `RecipeCatalogExtrusion` and `MaterialCatalog` are different catalogues with
  different purposes. The latter currently covers BOPP/CPP film, boxes, and
  cores used by actuals entry.
- MTS balances are refreshed by a macro from final-operation net output minus
  material rows linked to a source MTS order. Balances within plus or minus
  5 kg are hidden, while larger negative balances remain possible.
- Three actual cards have a positive calculated duration but a stored total of
  zero. This is evidence that historical migration will need exception
  reporting rather than blind copying.
- The unplanned-rewinding print macro temporarily changes the selected order's
  route value, prints, and restores it. A centralized system should represent
  the business exception directly rather than mutate the plan as a print trick.

This evidence does not require reproducing every workbook helper or historical
implementation detail. The end state does replace both planning and actuals
capture. The remaining discovery work is to identify which business facts and
rules are genuinely required, which become derived system behavior, and which
were only Excel implementation machinery.

### Remaining Evidence And Later Mapping

- The user confirmed on August 14, 2026 that the second Shift Manager workbook
  follows the same planning, operational-card, actuals, duplication, and shared-
  operation patterns as the inspected workbook. It is a simpler subset without
  extrusion and contains only printing, rewinding/slitting, and confection.
  Inspecting it is therefore not a prerequisite for the architecture or
  complexity assessment. Its eventual import is a source-mapping and validation
  task.
- The existing physical raw-material inventory source and its data quality have
  not been inspected. This affects later migration/import mechanics, not the
  confirmed four-transaction inventory-ledger scope.
- Exact operation-specific fields, output units, print layouts, and export
  columns are later implementation mappings. They do not introduce another
  workflow or lifecycle class.

## Provisional System Decomposition

This is an investigation model, not an approved schema.

### 1. Production-Order Planning

Own the shared commercial and manufacturing request:

- production order number;
- order and delivery dates;
- customer and location;
- requested product and dimensions;
- ordered quantities in applicable units;
- notes;
- make-to-order or make-to-stock intent; and
- the ordered route through required operations.

The production order should not itself be the execution record for every
operation.

### 2. Operation Requirements And Planned Specifications

For each required route step, store an operation requirement with its sequence
and operation-specific plan:

- extrusion recipe and extrusion instructions;
- printing cylinder and ink/color plan;
- rewinding/slitting size and related instruction; or
- confection folding, packaging, ventilation, and related instruction.

Planned specifications remain distinct from what workers actually execute.

### 3. Operational Cards And Dispatch

An operational card is the executable unit sent to a department or terminal.
It needs its own identity, lifecycle, planned specification snapshot or
reference, resource assignment, queue position, execution records, and review
state.

The current workbook demonstrates that one production-order operation may need
multiple physical operational cards for split work, partial production, reruns,
or corrections. Whether the future MES preserves that behavior is an explicit
scope decision; it should not be hidden behind a one-card-per-order assumption.

### 4. Execution Actuals

Each operation should record only the facts needed for operations and later
costing, such as:

- actual start/pause/resume/finish segments or approved summarized time;
- output quantity in the operation's relevant units;
- waste where required;
- actual materials and batches where required;
- rolls, tare, net weight, pallets, or other operation-specific outputs where
  required;
- shift and resource attribution; and
- review, correction, void, or supersession information.

The common lifecycle can be shared, while operation-specific actuals remain
small bounded extensions. Printing and confection should not inherit extrusion
recipe, roll-return, or pallet logic merely because they share one application.

### 5. Material And Item Availability

The minimum inventory-facing capability described so far is:

- one canonical material/item record;
- active/inactive status;
- category, such as LDPE;
- the available items in each category;
- current stock quantity where the planning workflow needs it; and
- stable identity usable by planned and executed recipe snapshots.

The Shift Manager should be able to select a category and see the active,
available materials in that category. This replaces the workbook recipe
catalogue as the normal selection source without making the recipe editor
responsible for stock accounting.

### 6. Planning Demand And Projected Availability

For planned orders, the system can calculate simple theoretical demand:

```text
planned output quantity × planned recipe percentage
```

For execution or completed cards, the already-recorded future direction is:

```text
actual produced net quantity × effective recipe percentage
```

where the effective recipe is the complete executed snapshot when one exists,
otherwise the planned recipe.

This supports views of planned demand and projected remaining material without
claiming that the calculated number is exact physical consumption. Physical
stock differences, loss, waste, and month-end reconciliation remain a separate
explicit process.

### 7. Completion Review And Inventory Posting

Raw-material consumption is now confirmed scope. The owning Shift Manager
reviews every completed operational card before it affects inventory:

1. Finish execution and record the card's actual output.
2. For extrusion, show editable consumption suggestions derived from actual net
   kilograms and the effective recipe.
3. For other operations, accept manager-declared material and quantity rows
   without attempting automatic inference.
4. Let the owning Shift Manager confirm the review and post the material issue
   once with a durable card reference.
5. Correct through a linked reversal/replacement or adjustment, not silent
   overwrite.

This deliberately transfers exceptional production knowledge to the Shift
Manager instead of encoding it as a transformation engine. It does not create
automatic intermediate or ordinary make-to-order finished-goods receipts.

### 8. Make-To-Stock Source-Lot Ledger

Make-to-stock is the one initially required production-output balance:

1. A source production order is deliberately designated make-to-stock and
   identifies the reusable base item.
2. Its reviewed production output increases the source lot's produced
   quantity.
3. A consuming operational card selects that source production order and
   declares how much it used.
4. The system derives the remaining quantity from source output minus all
   linked consumption.

No item is created after every intermediate card. Ordinary make-to-order final
output can remain an execution fact in the first release rather than a
warehouse item.

The confirmed initial representation is one distinct selectable MTS output per
source production order. A consuming card can select multiple source orders and
declare the quantity used from each. No shared item pool or weighted-average
inventory valuation is required.

### 9. Costing And Reporting Boundary

The MES should expose raw, structured production facts. It should not calculate
material prices, operation rates, allocations, invoice cost, margin, or monthly
costing results.

For make-to-stock costing, the production period of the source—not the later
consumption period—determines which external fixed-price schedule applies. The
MES stores the dates and production facts; the costing process maps them to the
appropriate price period and may perform or repeat that calculation later.

Likely downstream facts include:

- production order and operational-card identities;
- operation type and completion period;
- resource and shift;
- actual time;
- actual output quantities;
- theoretical or declared material quantities with stable material identity;
- waste where recorded; and
- corrections/voids needed to interpret the current record.

The exact export columns will be specified after the MES data ownership is
settled. The costing process itself is not needed to estimate the MES except for
defining the raw fields it must receive.

### 10. Confirmed One-Way Costing Export

The only initial connection to costing is a repeatable CSV/Excel extract with a
stable documented structure. An authorized user selects the relevant period and
exports the raw production and inventory facts required by the external costing
file, including:

- production-order and operational-card identities;
- operation and completion period;
- timing and output actuals;
- declared material-consumption rows;
- make-to-stock producing/consuming source links and quantities; and
- relevant inventory corrections or adjustments needed to interpret balances.

The export contract uses stable column names, identifiers, units, date formats,
and a schema version so the costing file can import the same structure every
time. The exact column mapping is an implementation specification, not a
complexity decision.

There is no live API integration, two-way synchronization, costing-file
writeback, automatic valuation, price import, or costing calculation inside the
MES. The export can be regenerated later after production corrections because
the MES preserves the underlying facts and history.

## Scope That Should Remain Excluded Unless Deliberately Added

- general ledger, invoicing, payments, or accounting;
- a costing engine, cost allocation, or margin calculation;
- sales-order and dispatch workflow;
- automated purchasing or full MRP;
- automatic finished-item inference in ambiguous cases;
- automatic transformation/genealogy for every intermediate product;
- finite-capacity optimization or automatic schedule generation;
- machine telemetry, OEE, detailed downtime, or predictive maintenance;
- quality-management workflows beyond fields explicitly required on a card;
- formula-driven automatic release of every next operation;
- exact real-time material consumption when it is not actually measured; and
- arbitrary workflow automation added only to imitate a full ERP.

## Complexity That Cannot Be Removed Safely

Even a deliberately simple MES needs the following:

- stable production-order, operation, operational-card, material, and output
  identities;
- explicit state transitions and clear ownership of each state change;
- preservation of planned data separately from executed facts;
- non-destructive correction, void, or reversal behavior;
- protection against two Shift Managers or a manager and terminal silently
  overwriting each other;
- deterministic queue/resource rules wherever machine assignment exists;
- durable links between completion records and any inventory posting;
- idempotency if completion or correction is communicated to another module;
- clear treatment of split work and multiple operational cards;
- backup, restore, migration, and cutover procedures; and
- enough user/role/audit information to determine who may plan, execute,
  approve, correct, or post stock in a multi-department system.

These are data-integrity requirements, not ERP automation.

## Lessons To Carry Forward From The Extrusion Pilot

- Build and validate one real workflow slice at a time.
- Keep planned/imported data separate from terminal-entered production data.
- Snapshot mutable reference data when it becomes a production fact.
- Use backend and database constraints for important invariants.
- Treat queue positions as insertion targets and keep active queues contiguous.
- Store segmented timing when pause/resume matters.
- Make exceptional waiting states explicit instead of overloading "running" or
  "completed."
- Persist every production mutation immediately.
- Reject stale writes and require reload instead of silently merging production
  changes.
- Preserve history during correction and migration; do not guess missing
  historical meaning.
- Keep operation-specific logic bounded rather than forcing all departments
  into the extrusion model.
- Validate the workflow on real hardware and with real users before broadening
  it.

## Prototype Choices Not Inherited Automatically

The following current-pilot choices must not become future-system requirements
without evaluation:

- one FastAPI process;
- SQLite;
- four fixed machine IDs;
- one global active extrusion shift;
- one terminal and one Shift Manager;
- no authentication or named actors;
- CSV as the normal planning handoff;
- ten-second browser polling;
- one coarse version number for the whole card;
- mutable completed records without a formal close; and
- the current `cards` table as the central model.

## Closed Scope Decisions And Later Specification Mappings

The high-level questions are closed. Items described as later mappings belong
in the relevant operation design or migration plan and do not reopen product
discovery.

### A. Product Boundary

1. **Resolved on August 14, 2026:** the MES replaces the workbook's planning,
   operational-card, actuals, materials, and make-to-stock repository roles.
   Excel has no end-state operating role. Paper printing and deliberate
   recovery entry remain required for redundancy.
2. **Resolved on August 14, 2026:** Task 69 is a greenfield successor
   application. The existing FastAPI extrusion terminal is not expanded or
   rewritten in place; its validated behavior is carried forward as requirements
   and acceptance evidence. The successor is a custom LAN application; ERPNext
   and general ERP process frameworks are explicitly out of scope.
3. **Resolved on August 14, 2026:** inventory is a separate internal module in
   the same custom application, deployment, and database. It has isolated
   screens, code, rules, and role-scoped access, but communicates with planning
   and reviewed-card consumption through narrow internal functions. It is not a
   separate application or synchronization boundary.

### B. Two-Workbook Ownership

4. **Resolved on August 14, 2026:** the current work is generally divided by
   material—polyethylene with Shift Manager 1 and polypropylene with Shift
   Manager 2—but operation coverage overlaps and this is not a rigid system
   rule.
5. **Resolved on August 14, 2026:** ownership is a Shift Manager data boundary
   with one narrow exception. A non-owner cannot access another manager's
   private production-order workspace or edit that manager's card. Once an
   owner releases a card to a shared operation, both managers may see its
   minimal queue summary and reorder it within the shared dispatch queue.
6. **Resolved on August 14, 2026:** historical workbook ranges are disjoint and
   migrated orders retain their existing numbers. Every order also receives a
   stable internal identity. Future orders use one centrally allocated shared
   sequence; both managers may see the global sequence state without seeing
   each other's orders.
7. **Resolved direction on August 14, 2026:** migrate only the useful normalized
   production data created on or after July 1, 2026. Earlier history is
   unreliable and remains outside the new operational database. Exact included
   tables and fields will be determined from the available normalized source
   data as a technical migration mapping. The second workbook is confirmed to
   use the same, simpler business model and adds no discovery dependency.
8. **Migration default closed on August 14, 2026:** included legacy `да` route
   flags are corrected into the new ordered-route representation during
   migration preparation. The MES does not infer ambiguous sequence at runtime.

### C. Operation Scope

9. **Resolved on August 14, 2026:** extrusion, printing, rewinding/slitting, and
   confection each receive an operation-specific kiosk/terminal. The three non-
   extrusion operations share the generic start, pause/resume, finish, and
   optional Shift Manager review flow.
10. **Resolved direction on August 14, 2026:** every card uses named machine
    assignment and each machine has its own queue. Known examples are printing
    `1–2`, confection `1–4`, and extrusion `1–4` with one currently inactive.
    Rewinding/slitting resource names and exact kiosk count are configuration
    details. Shared authority over another owner's released card is limited to
    queue reordering; machine/resource assignment remains owner-only.
11. **Resolved direction on August 15, 2026:** the data model permits multiple
    cards for the same operation within one production order when the owning
    Shift Manager deliberately adds split, rerun, recurring, or supplementary
    work. The MES does not create those cards automatically.
12. **Resolved on August 14, 2026:** there are no automatic releases. The owning
    Shift Manager explicitly releases or prints each planned or supplementary
    card. Execution completion, review, inventory posting, and prior-operation
    completion never release the next card.
13. **Resolved default on August 15, 2026:** every operation has a printable
    operational card sufficient for paper execution and recovery entry. Exact
    card content is an operation mapping. Separate labels are out of scope unless
    a specific operation brief demonstrates a real requirement.
14. **Resolved direction on August 15, 2026:** unplanned rewinding is a
    deliberately added supplementary operational card owned by the production-
    order creator. It is one-off by default and is not copied during duplication
    unless the manager explicitly classifies the operation as recurring.

### D. Actuals And Corrections

15. **Later mapping, not discovery:** identify the V14.22 actual fields genuinely
    used for operations and the stable costing export. This does not change the
    confirmed one-way CSV/Excel integration boundary.
16. **Resolved default on August 15, 2026:** store raw start/pause/resume/finish
    timestamps and derive active elapsed time from their segments. Preserve
    manually entered paper-summary time with its source. Any scheduled-calendar
    overlap or costing interpretation is derived outside the MES from exported
    facts unless an operation brief proves it needs a different live rule.
17. **Resolved live-terminal direction on August 14, 2026:** every operation
    terminal supports start, pause/resume, and finish, so those events provide
    its normal timing record. Before terminal go-live and during exceptional
    recovery, Shift Managers enter the paper card's required summary actuals;
    exact fields remain an operation-level mapping.
18. **Resolved direction on August 14, 2026:** completed actuals remain
    correctable through attributed admin actions that preserve the prior value
    or linked correction history. The MES does not make an erroneous production
    fact unfixable merely because it was completed or exported.
19. **Resolved default on August 15, 2026:** an unstarted card with no production,
    review, inventory, or other dependent facts may be deleted safely. Once a
    card has production facts or dependencies, it is voided/cancelled and
    retained with correction history instead of being erased.
20. **Resolved on August 14, 2026:** source authority depends on capture mode.
    Detailed terminal rows are authoritative when a terminal captured them and
    the normalized card summary is derived from those rows. A valid manual or
    paper-recovery card stores an authoritative summary without fabricated
    detail. Both expose the same summary contract to review and export.

### E. Inventory

21. **Resolved initial transaction scope on August 14, 2026:** raw-material
    inventory is a ledger with receipt, reviewed operational-card consumption,
    disposal/sale removal, and reconciliation adjustment. Disposal/sale only
    removes quantity with a reason/reference; it does not add sales, dispatch,
    invoicing, or profit logic. Reservations, purchase-order workflow, warehouse
    transfers, automated allocations, replenishment, and MRP are excluded.
22. **Resolved on August 14, 2026:** the dashboard shows current recorded ledger
    balance and projected balance after the planned/released operational cards
    included in the view. They are separate figures. Projection is informational
    and creates no reservation, allocation, deduction, or inventory transaction;
    active catalogue status is also separate.
23. **Resolved on August 14, 2026:** every completed operational card receives
    an owning-Shift-Manager review. Submitting that review posts its declared
    raw-material consumption to inventory. Extrusion may prefill editable
    theoretical quantities from actual net output and recipe percentages;
    non-obvious consumption is entered explicitly by the manager.
24. **Resolved initial direction on August 14, 2026:** do not create general
    work-in-progress or finished-goods inventory after normal cards. If a route
    is deliberately stopped early and its current output must be treated as a
    standalone item, the owning Shift Manager explicitly declares the reason,
    item, and quantity; this may remain an output record if finished-goods
    inventory is deferred.
25. **Resolved on August 14, 2026:** a make-to-stock source order owns a reusable
    source lot. Its reviewed output increases produced quantity; later consuming
    cards select that source production order and declare their consumed
    quantity. The remaining balance is derived from all linked production and
    consumption records. Each source production order remains a distinct MTS
    output identity; a consuming card can use multiple source orders through
    separate consumption lines. No common-item pool or MES weighted-average
    valuation is required.
26. **Resolved on August 15, 2026:** any named account with inventory-
    modification capability may perform monthly physical reconciliation. The
    adjustment is dated and attributed, retains the original transactions, and
    includes small residuals previously hidden within `±5 kg`. No special
    reconciliation role or approval workflow is required.
27. **Resolved for initial make-to-stock scope on August 14, 2026:** no stable
    interchangeability code or pooled MTS item master is required. Each source
    production order is its own MTS output identity. Broader governance of raw-
    material and operation-specific catalogues remains part of inventory design.

### F. Users, Infrastructure, And Cutover

28. **Resolved initial identity boundary on August 14, 2026:** each Shift Manager
    has a named login; one administrator/recovery account can do everything; and
    every operation kiosk has one permanently signed-in fixed account. Operators
    have no individual accounts. Kiosk actions are attributed to the operation
    kiosk and active shift, while manager actions are attributed to the manager.
    Inventory visibility and modification are separate capabilities assigned to
    named accounts. An inventory-only user may be restricted to that module; a
    Shift Manager may receive dashboard visibility alone or may additionally be
    granted full inventory-modification capability.
29. **Resolved initial production-user scale on August 14, 2026:** two named
    Shift Managers, one administrator/recovery account, and one or more fixed
    kiosks per included operation/machine area—approximately seven terminals in
    total. Kiosks are not cross-functional; one kiosk may show one or several
    configured machines within its operation. A small number of named inventory-
    only users may be added without changing the architecture.
30. **Resolved on August 14, 2026:** one central factory-LAN server, application,
    and database serve all Shift Manager computers and terminal kiosks. No
    terminal-local database, disconnected writes, or later synchronization is
    required. Automatic restart follows the current Proxmox/VM/app/kiosk model;
    paper cards plus deliberate recovery entry cover exceptional server,
    network, or terminal unavailability.
31. **Resolved on August 14, 2026:** rollout uses one declared cutover date.
    From that date forward, the MES is the sole writable operational system and
    Excel is read-only reference material. Reliable structured data is bulk-
    migrated where practical; omitted legacy orders are recreated in the MES
    only when useful. There is no dual write, synchronization, or field-level
    coexistence model.

## Durable Terminal Contract

Most terminal behavior belongs to one reusable execution contract. Every
operation terminal must provide:

- a fixed kiosk identity and configured operation/machine scope;
- released queues for its configured machines;
- deliberate card selection and display of the operation's planned
  instructions;
- start, pause, resume, and finish actions linked to the active shift;
- immediate persistence, stale-action rejection, and one-running-card-per-
  machine enforcement;
- operation-specific actual-entry fields and validation;
- completion handoff to owning-Shift-Manager review where additional actuals or
  consumption are required; and
- no automatic release of downstream cards.

An operation-specific terminal implementation supplies only:

- planned fields and presentation groups;
- actual fields, quantities, units, and validation;
- operation-specific print content; and
- deliberately approved extensions beyond the common lifecycle.

Printing, rewinding/slitting, and confection should therefore be thin
implementations of this contract rather than separate terminal applications or
copied state machines. Extrusion uses the same contract but adds its proven
recipe, roll/tare/net, pallet, countdown, and rewinding-return extensions.

## Recommended Phased Delivery Design

Three rollout shapes were considered:

1. **Build the entire foundation before any terminal.** This appears orderly but
   risks designing too much untested infrastructure before an end-to-end flow
   proves it.
2. **Build each terminal independently.** This gives visible screens quickly but
   duplicates lifecycle, queue, permission, and persistence behavior.
3. **Build a thin common foundation through one real terminal, then extend it.**
   This is the recommended approach. It proves the shared model early and makes
   later simple terminals small field/UI adapters.

The recommended slices are:

1. **Contracts and core model:** production orders, ordered operation
   requirements, operational cards, lifecycle, ownership, machines, queues,
   review, inventory links, corrections, and terminal adapter boundaries.
2. **MES planning repository and paper continuity:** accounts, order creation and
   duplication, shared numbering, route planning, release, printable cards,
   summary actuals entry for every operation, recovery entry, migration shape,
   and the minimum inventory catalogue/ledger needed by planning and review.
3. **First end-to-end production terminal:** connect one operation from order
   creation through release, kiosk execution, review, inventory posting, output,
   printing, export, and correction. The recommended first rollout terminal is
   extrusion because its behavior and worker UI already have an accepted
   executable reference; this avoids rediscovery and operator retraining.
4. **Printing as the generic terminal reference:** finalize the shared simple-
   operation layout and adapter contract using printing's planned colors/inks,
   machine assignment, timing, output, and review fields.
5. **Rewinding/slitting and confection adapters:** supply their bounded fields,
   units, layouts, and tests on the already-proven generic lifecycle.
6. **Migration, deployment, and cutover hardening:** validate normalized source
   import, backup/restore, paper recovery, costing export, kiosk configuration,
   and factory acceptance.

The MES can replace Excel before every operation has a digital kiosk. Operations
whose terminals are not yet implemented receive MES-printed cards and use the
confirmed paper/recovery-entry path. Excel still becomes read-only at the
declared cutover; phased terminal delivery does not reintroduce dual system-of-
record operation.

The user's `80/20` intuition is directionally correct: approximately `70–80%` of
the work is the shared production model, planning surfaces, permissions,
persistence, reviews, inventory links, migration, and verification. Roughly
`20–30%` is operation-specific field mapping, layout, validation, and testing.
Extrusion is the deliberate exception because its richer extensions make it
larger than the other three terminal adapters combined.

This delivery shape does not eliminate end-state functionality already counted
in the revised estimate. It reduces rework, allows safe parallel adapter work,
and moves the likely result toward the lower half of the one-month envelope.

## Discovery Closure And AI-Only Delivery Model

High-level discovery is complete. The remaining later-mapping entries above are
operation-field mappings, print-layout details, resource configuration, and
form-level correction rules. They can change individual slice effort and test
cases, but they do not change the product boundary, module count, lifecycle
class, integration architecture, or overall complexity assessment.

There is no conventional human development team or human code-review estimate.
Codex and other AI agents perform design drafting, implementation, tests,
reviews, documentation, and verification. The user supplies business decisions,
source information, and real-factory acceptance feedback, but is not expected
to inspect source-code diffs.

Delivery follows the Superpowers workflow:

1. consolidate the confirmed scope into a coherent system design;
2. self-review the design for ambiguity, contradictions, and accidental ERP
   scope;
3. write a dependency-ordered implementation plan divided into small vertical
   slices;
4. implement each slice with backend/database invariants first and tests before
   or alongside behavior;
5. run focused automated, browser, migration, and deployment verification;
6. use independent AI-agent review for data integrity and workflow gaps; and
7. integrate only a verified slice before starting the next dependent slice.

The user still confirms business behavior at design and factory-acceptance
boundaries. That is product acceptance, not manual code review.

## Remaining Work Before Coding

No further general business discovery is required. The next work is to turn the
confirmed scope into implementation artifacts:

1. **System design:** module boundaries, relational data model, lifecycle
   transitions, permissions, transaction boundaries, concurrency invariants,
   correction semantics, and deployment architecture.
2. **Operation contracts:** one concise matrix per operation covering planned
   fields, manual-summary actuals, terminal-detail actuals, units, validations,
   machine configuration, review requirements, and printable-card content.
3. **Shared terminal contract:** reusable queue, timing, shift, persistence,
   conflict, completion, and recovery behavior, with extrusion extensions kept
   separate.
4. **Data contracts:** source-to-MES migration mapping and the versioned costing
   export structure.
5. **Implementation plan:** dependency-ordered vertical slices with acceptance
   tests, browser checks, migration rehearsals, agent-review gates, and cutover
   criteria.

Technology and code-organization choices are engineering decisions for the
design agents unless they would change the confirmed LAN deployment or business
workflow. Per-operation mappings may require inspecting source fields or asking
a targeted factual question, but they are specifications—not renewed discovery
of the product.

## Complexity Assessment

This is a **moderate custom business application**, not a complex ERP. Its
interactive scale—approximately seven fixed kiosks, two Shift Managers, a small
number of inventory users, and one recovery administrator—is technically small.
It requires a normal central transactional web application, not distributed or
high-scale infrastructure.

Complexity is concentrated in a few bounded areas:

- **moderate:** the shared production-order/operational-card model, creator-only
  ownership, shared queue ordering, corrections, and concurrency invariants;
- **moderate:** faithful extrusion behavior, including recipes, rolls, timing,
  pallets, rewinding return, manager review, and print output;
- **moderate:** immutable inventory and make-to-stock ledgers with source-order
  provenance and atomic reviewed-card posting;
- **low:** printing, rewinding/slitting, and confection terminal workflows once
  their fields and print layouts are mapped;
- **low:** current/projected inventory display and stable costing export; and
- **bounded but verification-heavy:** workbook migration, paper recovery,
  deployment, backups, and factory cutover.

The application logic itself is not unusually difficult. The work is primarily
the disciplined assembly, testing, and rollout of several simple workflows
around one reliable data model.

## Revised AI-Only Estimate

The estimate assumes sustained Codex/agent sessions, no ERP or new automation
scope, prompt access to source fields and factory feedback, and the confirmed
single-LAN deployment. Ranges include ordinary agent review and rework but not
long calendar pauses between sessions.

The earlier estimate used "focused AI delivery days" as though each slice were
a sequential human work package. That was the wrong unit: it double-counted
testing and hardening already performed inside each slice and failed to account
properly for parallel agents and AI implementation speed. That estimate is
withdrawn.

An **active Codex build day** below is not five or eight hours of human labor. It
means one calendar day in which the project is actively advanced through
multiple implementation, review, test, and correction turns, potentially using
several agents. It is a scheduling unit, not an AI-hours conversion.

| Delivery area | Active Codex build days if performed serially |
| --- | ---: |
| Consolidated architecture, data model, and master slice plan | 1–2 days |
| Application foundation, migrations, accounts, permissions, and core references | 1–2 days |
| Production orders, routes, duplication, ownership, machines, and shared planning | 2–3 days |
| Generic terminal execution plus printing, rewinding/slitting, and confection | 1–2 days |
| Inventory, completion review, make-to-stock ledger, and projection | 2–3 days |
| Extrusion workflow recreated to proven pilot parity | 3–5 days |
| Printing, exports, migration, paper recovery, deployment, and backup tooling | 2–3 days |
| Integrated verification, factory trial, corrections, and cutover hardening | 2–4 days |

The deliberately conservative serial sum is **14–24 active Codex build days**.
It is not the expected elapsed duration because field mapping, UI work, isolated
modules, tests, and independent reviews can overlap after the core model is
stable. Shared-schema and end-to-end integration work still remains sequential.

Reasonable elapsed targets are:

- **first usable end-to-end vertical slice:** 2–4 active build days;
- **feature-complete internal release candidate:** 8–12 active build days; and
- **cutover-ready initial MES:** 12–18 active build days, normally about 2½–4
  calendar weeks if the project is advanced on most working days.

An October 1 cutover from an August 14 start leaves meaningful schedule margin
under this revised estimate. The main causes for exceeding it would be renewed
product discovery, significant scope additions, unavailable hardware/source
data, or factory validation revealing a genuinely new workflow class—not the
known coding volume.

## Durable Decisions So Far

1. High-level scope boundaries were closed before estimation; the initial
   AI-only range was recorded on August 14, 2026.
2. Task 69 now governs system design and planning for a greenfield successor; it
   does not change the current extrusion-pilot scope or itself authorize coding.
3. The MES captures planning and execution facts; costing and analytics remain
   separate.
4. Ambiguous output/item decisions should use deliberate human confirmation
   rather than automatic inference.
5. Planned data and executed production facts must remain separate.
6. Extrusion-specific behavior must not be imposed on simpler operations.
7. Inventory catalogue/availability lookup and human-confirmed consumption
   posting are in scope; automatic unreviewed stock posting is not.
8. The second Shift Manager workbook is not required discovery evidence. It is
   confirmed to be a simpler instance of the same model without extrusion; its
   eventual migration is a field-mapping and validation task.
9. Excel will not remain an end-state system of record or routine workflow
   dependency.
10. Planned orders, operational cards, and completed-card actuals will be held
    in the centralized digital system.
11. Required operational cards must remain printable for redundancy, and the
    system must accept deliberate after-the-fact entry from a completed paper
    card.
12. Paper fallback must reconcile back into the MES; it must not create a
    permanent second source of truth.
13. The production order—not the operation—is the unit of Shift Manager
    accountability.
14. The manager who creates an order owns its complete route and all related
    operational cards.
15. Material type is a practical guide to who normally creates an order, not a
    rigid ownership or operation-routing rule.
16. Shared or specialist operation work does not transfer order ownership.
17. The MES does not need delegation, task transfer, or per-operation acceptance
    between Shift Managers.
18. A non-owning Shift Manager cannot access another manager's private
    production-order workspace or edit that manager's operational-card
    content. Minimal released-card context in a shared dispatch queue is the
    sole confirmed visibility exception.
19. Shift Manager planning workspaces must be logically partitioned by owner,
    even if they run in one central application and database.
20. Shared operations use a combined released-card queue across both owner
    workspaces.
21. Both Shift Managers may view the minimum shared-queue summary and reorder
    every released entry, including cards owned by the other manager.
22. Only the originating manager may edit or withdraw that manager's card;
    shared reordering does not grant card-content access.
23. Shared operation priorities are coordinated by the managers themselves;
    no separate dispatcher, delegation, or approval workflow is required.
24. Shared queue reordering is the only cross-owner modification. Machine or
    resource assignment, card editing, release, withdrawal, cancellation, and
    correction remain owner-only.
25. The MES will not include cross-manager change requests, approval
    notifications, ownership transfers, or temporary edit grants.
26. Remaining scope decisions should default to the simplest safe owner and
    workflow boundary unless a real current process requires more.
27. The centralized system owns production-order identity and generates one
    globally unique order-number sequence across both Shift Manager ownership
    domains.
28. Existing migrated orders retain their original disjoint-range business
    numbers and also receive stable internal system identities.
29. Future orders use one central shared number sequence across both managers;
    the shared latest/next number is visible without revealing another owner's
    order.
30. Migration is limited to useful normalized production data created on or
    after July 1, 2026; earlier unreliable history is not migrated into the new
    operational database.
31. Ambiguous legacy route flags in the included migration population are
    corrected before import rather than interpreted dynamically by the MES.
32. Raw-material inventory changes occur only when the owning Shift Manager
    submits the review of a completed operational card.
33. Completing execution first places the card in a distinct pending-review
    state; it does not itself change inventory.
34. Extrusion consumption suggestions use actual produced net kilograms times
    the effective recipe percentages and remain editable before confirmation.
35. When consumption is not obvious, the Shift Manager declares the material
    and quantity instead of the MES attempting to infer it.
36. A review may deliberately confirm that no tracked material was consumed;
    an empty unreviewed form is not treated as that confirmation.
37. Review submission is idempotent and atomic with the inventory issue. Later
    corrections preserve history through a linked reversal/replacement or
    adjustment rather than a second deduction or silent overwrite.
38. Insufficient recorded stock does not block a declared-consumption posting;
    inventory balances may become negative.
39. Negative balances and suspicious or missing material inputs are visible
    review/reconciliation warnings, not attempts to infer production outcomes.
40. Review warnings are advisory. The Shift Manager may deliberately confirm
    the posting despite them.
41. Only structurally invalid material rows and duplicate posting attempts are
    hard-blocked.
42. A known source error is corrected through the linked card posting. An
    unexplained discrepancy is resolved with a dated, attributed inventory
    reconciliation adjustment that preserves the original ledger history.
43. The MES does not create a work-in-progress inventory item after every
    operational card.
44. General finished-goods inventory, dispatch, sales, and invoicing are not
    required in the initial MES scope.
45. Ordinary make-to-order card outputs remain production actuals rather than
    automatic inventory receipts.
46. A deliberately stopped route creates a standalone output only through an
    explicit owning-Shift-Manager declaration of reason, item, and quantity;
    stopping a card alone never infers an item.
47. Make-to-stock is the required exception: a designated source production
    order owns a reusable source lot whose produced quantity comes from its
    reviewed output.
48. Consuming cards explicitly select the source make-to-stock production order
    and declare the quantity used; multiple later orders may consume the same
    source.
49. A make-to-stock balance is derived from reviewed source output minus linked
    declared consumption. It is a bounded source-lot ledger, not a general WIP
    warehouse.
50. The make-to-stock tracker is a quantity ledger: reviewed production posts
    positive quantities and linked consumption posts negative quantities.
51. Every make-to-stock receipt retains its producing production order, and
    every consuming order retains the source order or orders and quantity used
    from each.
52. The app does not reproduce the workbook's `±5 kg` hiding tolerance. Exact
    nonzero MTS balances remain visible until an actual correction or monthly
    reconciliation adjustment clears them.
53. The MES preserves the dependency needed for costing—source order, consuming
    order, source quantity, dates, material inputs, and operation actuals—but
    does not assign source costs or calculate weighted-average valuation.
54. Each make-to-stock source production order is its own initial selectable
    output identity; no shared interchangeability code or pooled item balance is
    required.
55. One consuming card may contain multiple MTS consumption lines referencing
    different source production orders.
56. The consuming order's input value is the sum of the consumed values from
    its individually costed MTS source orders.
57. An MTS source keeps the valuation basis of its own production period even
    when consumed in a later month. The MES records the production date and
    facts; the costing process applies the appropriate fixed-price schedule.
58. Source-order costing can occur or be recalculated later because the MES
    retains its inputs, output quantity, dates, and downstream relationships.
59. A new production order explicitly identifies every initially planned
    operation.
60. Duplicating an order copies its recurring planned route and operation-
    specific planned recipe/instructions as a starting point, not its production
    history.
61. Duplication does not copy release state, assignment, queue position, timing,
    output actuals, consumption, review, or corrections.
62. An added operation is classified as recurring or supplementary. Recurring
    operations are eligible for later duplication; supplementary one-off
    operations are not.
63. A supplementary card remains part of the source order's record even though
    it is excluded from later duplication.
64. Only the owning Shift Manager chooses when to release a card to a terminal
    or print and issue it for production.
65. No card completion, review, inventory posting, or preceding-route event
    automatically releases another operational card.
66. Terminal workers can finish execution, while the owning Shift Manager may
    subsequently supply missing actuals and approve the completed card.
67. Shift Manager approval does not trigger automatic downstream work.
68. The MES runs as one central factory-LAN application and database shared by
    all Shift Manager workstations and terminal kiosks.
69. The system is not publicly internet-dependent and does not need terminal-
    local production databases, disconnected write queues, or later data merge.
70. Server, VM, MES service, and terminal kiosks automatically restart after
    power restoration, following the proven extrusion-terminal deployment
    pattern.
71. Factory-wide power loss creates no synchronization problem because the
    production machinery and digital system stop together.
72. When machinery can operate but the central service or a terminal is
    unavailable, printed cards provide the bounded production fallback.
73. Completed paper cards are deliberately entered after service recovery with
    source identity, paper-origin attribution, and duplicate-completion checks.
74. Deployment scope includes immediate persistence, backup/restore, automatic
    restart, health checks, and documented recovery—not offline synchronization.
75. A documented manual alternate-host procedure may allow the administrator to
    start the recoverable app on another PC or laptop for card access/printing;
    this is not automatic failover or a second live database.
76. Each Shift Manager has one named account, and manager actions are attributed
    to that account.
77. One administrator/recovery account has full cross-owner access and recovery
    authority.
78. Each physical kiosk has one fixed, permanently signed-in account restricted
    to its configured operation and machine queue or queues.
79. Kiosks are operation-specific and are not required to switch between
    functional departments.
80. Terminal operators have no individual MES accounts, passwords, badges, or
    operator-level permission model.
81. Production actions at a kiosk are attributed to its operation identity and
    the active shift, not to a named operator.
82. Shift start/change tracking follows the existing extrusion-terminal model;
    a separate roster CSV may map each shift to its workers for reporting.
83. Initial raw-material inventory supports exactly four business transaction
    types: receipt, reviewed operational-card consumption, disposal/sale removal,
    and reconciliation adjustment.
84. Disposal, scrapping, or sale of unwanted material is a quantity-removal
    transaction with reason and reference, not a customer-order, dispatch,
    invoicing, payment, or revenue workflow.
85. Inventory balances are derived from immutable dated ledger entries rather
    than directly overwritten totals.
86. Inventory corrections use linked reversal/replacement or reconciliation
    adjustments and preserve the original transaction history.
87. Reservations, purchase-order workflow, warehouse transfers, automatic
    allocation, replenishment, and MRP are excluded from initial scope.
88. Any money recovered from selling unwanted material belongs to a separate
    invoice/cost-tracking process; the MES inventory action only removes the
    declared quantity.
89. Extrusion, printing, rewinding/slitting, and confection each have operation-
    specific kiosk/terminal coverage in initial production scope; an operation
    may have multiple physical kiosks.
90. Printing, rewinding/slitting, and confection share one generic execution
    flow: released queue, start, pause/resume, and finish.
91. Terminal workers record the execution facts they know; the owning Shift
    Manager can later supply missing actuals and approve the card.
92. The three simpler departments do not need separate lifecycle engines or
    additional workflow states.
93. Operation-specific differences are planned/actual field sets and display
    content, not different dispatch or execution state machines.
94. Finishing or approving a non-extrusion card never releases downstream work
    automatically.
95. Extrusion-specific recipe, roll, tare/net, pallet, and rewinding-return
    behavior remains isolated to extrusion.
96. Every executable card is assigned to a named machine/resource and machine
    queue before release.
97. Multiple cards may run concurrently within an operation on different
    machines, but one machine has at most one running card.
98. Extrusion has machines `1–4`, with one currently inactive, and one kiosk may
    serve all extrusion machine queues.
99. Printing has at least machines `1–2` with separate nearby kiosks; confection
    anticipates machines `1–4` served by approximately two or three kiosks.
100. A machine may be marked inactive without deleting its identity, queue
     history, or completed cards.
101. Machine selection and reassignment are deliberate owning-Shift-Manager
     actions; the MES performs no automatic assignment or load balancing.
102. The initial costing connection is a one-way CSV/Excel export with a stable,
     documented, versioned structure.
103. The export includes production/card identity, period, operation, timing,
     output, declared consumption, MTS source links, and relevant inventory
     adjustments.
104. The export can be regenerated for a selected period after corrections from
     the preserved MES facts.
105. The MES has no live costing API, two-way synchronization, costing-file
     writeback, price import, or automatic valuation.
106. Cost calculation and monetary values remain entirely outside the MES.
107. Exact export columns and field mappings are implementation specification
     details and do not affect the current complexity assessment.
108. The second Shift Manager workbook uses the same core order planning,
     operational-card, actuals, duplication, and shared-operation behavior as
     the inspected workbook.
109. Its printing, rewinding/slitting, and confection content is already covered
     by the confirmed generic non-extrusion operation model; it introduces no
     additional lifecycle or application-logic class.
110. Inspection of the second workbook is not a prerequisite for architecture
     selection or complexity estimation. Eventual import requires only source-
     field mapping, data validation, and migration testing.
111. July 1, 2026 is the source-data cutoff for the normalized workbook
     population considered for migration.
112. MES rollout uses one explicit operational cutover date; October 1, 2026 is
     currently an illustrative target, not a committed date.
113. From the cutover date onward, all new planning and production execution are
     recorded only in the MES. Excel is no longer a writable operating system.
114. There is no parallel Excel/MES write period, field-level coexistence,
     synchronization, or conflict-resolution requirement.
115. Cutover migrates as much reliable, useful structured information from the
     post-July 1 population as is practical; complete historical conversion is
     not required.
116. Unmigrated legacy records remain available in read-only workbook files and
     are recreated in the MES only if they later become operationally useful.
117. Shift Managers may use an old workbook order as reference when manually
     creating or duplicating a MES order, but the resulting MES record is the
     only record used for post-cutover production.
118. A narrow one-way migration importer may be retained if it materially saves
     entry effort, but a permanent generalized Excel integration is not part of
     the product scope.
119. The production MES is a new greenfield application; the existing extrusion
     terminal pilot will not be expanded or rewritten into the successor.
120. The pilot remains a bounded discovery artifact and executable workflow
     reference until the successor's extrusion slice has been validated.
121. Proven pilot behavior, business rules, print results, deployment lessons,
     and operator feedback are reusable requirements and acceptance evidence.
122. The successor begins with a coherent production-order and multi-operation
     domain model rather than preserving the pilot's combined card-centric
     database structure.
123. There is no requirement for schema compatibility, an in-place database
     upgrade, or preservation of the pilot's implementation choices.
124. Existing pilot code may be reused selectively only after review; code reuse
     is not an objective and creates no compatibility obligation.
125. The successor is delivered in small vertical slices, and the relevant
     extrusion slice must reproduce the proven workflow before pilot retirement
     and operational cutover.
126. The successor is custom factory-LAN software. ERPNext and general-purpose
     ERP process frameworks are explicitly out of scope.
127. The reason for excluding ERPNext is functional, not merely technical: its
     rigid administrative process model would add steps, constrain exceptions,
     and undermine the intended workflow simplification.
128. The initial expected interactive load is approximately seven fixed
     operation terminals, two named Shift Managers, and one administrator/
     recovery account on the factory LAN.
129. This is a small centralized multi-user workload. It does not require cloud
     scaling, distributed services, message queues, terminal synchronization,
     or other high-scale infrastructure.
130. Concurrent use still requires ordinary transactional correctness: each
     action persists immediately, stale edits are rejected, one machine cannot
     run conflicting cards, and shared queue changes remain consistent.
131. The product's core is structured production data capture plus manual
     planning, dispatch, execution, review, and bounded inventory recording.
132. Inventory is a separate internal business module within the same MES
     application, deployment, and database.
133. Inventory is not a separate service, application, database, API
     integration, or synchronization domain.
134. The inventory module has its own screens, navigation, code boundary,
     transaction rules, and role checks so it can be operated as a separate
     business process.
135. One or more named inventory accounts may be granted access only to the
     inventory module and denied access to production planning and terminal
     execution workflows.
136. Shift Managers can view active material choices and the stock information
     required for planning, and can trigger card-linked consumption through
     their reviewed-card workflow.
137. Card-linked consumption does not grant a Shift Manager general inventory-
     maintenance authority; broader permissions require the inventory-
     modification capability.
138. The administrator/recovery account retains full cross-module authority.
139. The shared application and database allow card review and its linked
     inventory posting to succeed or fail as one atomic transaction.
140. Inventory changes cannot silently mutate production facts. Every permitted
     cross-module effect is explicit and retains its source-card or other
     business reference.
141. Inventory access is capability-based rather than hard-coded to a particular
     job title or account type.
142. Inventory visibility permits read-only use of the dashboard, active
     catalogue, balances, and other published stock information.
143. An account without inventory-modification capability cannot open or submit
     general inventory transaction-entry actions.
144. Inventory modification permits receipts, consumption, disposal/sale
     removals, and reconciliation adjustments, with normal validation and actor
     attribution.
145. A named inventory user can be confined to the inventory module, while a
     Shift Manager may optionally be granted the same modification capability
     in addition to that manager's production permissions.
146. Granting inventory modification does not change production-order ownership
     or grant access to another Shift Manager's private planning records.
147. Reviewed-card consumption remains a narrow production workflow capability;
     it does not by itself grant access to general inventory maintenance.
148. The inventory dashboard shows current recorded balance derived from posted
     ledger transactions.
149. It separately shows projected balance after the theoretical requirements
     of planned/released operational cards included in the planning view.
150. Projected demand does not reserve, allocate, deduct, or otherwise mutate
     inventory and creates no ledger transaction.
151. Once reviewed actual consumption is posted, the current ledger balance
     changes and the same card's unposted theoretical demand is no longer
     counted in projection.
152. Catalogue-active status, current recorded balance, and projected balance
     are three distinct facts.
153. Current-versus-projected inventory display is a small derived query and UI
     feature, not a material-requirements engine or meaningful complexity driver.
154. High-level discovery is closed. Remaining field, print-layout, resource-
     configuration, and correction-form details are slice specifications rather
     than architecture or estimate blockers.
155. Development is performed entirely by Codex and other AI agents; no
     conventional human-development estimate applies.
156. The user is not expected to review code diffs. AI agents and automated
     checks perform engineering review, while the user supplies business
     decisions and factory-acceptance feedback.
157. Delivery follows the Superpowers design, planning, test, independent review,
     verification, and slice-integration gates.
158. The product is a moderate custom business application, not a complex ERP or
     high-scale distributed system.
159. The prior 43–66 day serial estimate used a human-like unit, double-counted
     slice verification, and underweighted parallel AI execution; it is
     withdrawn.
160. The revised conservative serial range is 14–24 active Codex build days. An
     active build day is a calendar day with sustained multi-turn agent
     implementation and verification, not a fixed number of human labor hours.
161. Expected elapsed targets are 2–4 active build days for the first complete
     slice, 8–12 for a feature-complete internal candidate, and 12–18 for a
     cutover-ready MES—normally about 2½–4 calendar weeks of sustained work.
162. The next project phase is a consolidated system design followed by a
     dependency-ordered vertical-slice implementation plan; coding begins only
     after those gates are completed.
163. One month is a comfortable planning envelope rather than a required coding
     duration; fixed specifications and sustained agent execution should place
     delivery toward the lower half of that window.
164. All operation terminals share one durable queue, lifecycle, timing, shift,
     persistence, conflict, completion-review, and permission contract.
165. Printing, rewinding/slitting, and confection are thin operation-specific
     field, layout, validation, print, and test adapters on that common contract.
166. Extrusion shares the common contract but retains its proven specialist
     recipe, roll/tare/net, pallet, countdown, and rewinding-return extensions.
167. Delivery proceeds through a thin common foundation connected immediately
     to one real end-to-end terminal, not a large untested foundation or four
     independently implemented terminal state machines.
168. The recommended first rollout terminal is extrusion because the accepted
     pilot provides an exact behavior and worker-UI reference; printing then
     becomes the reference implementation for the generic simple-operation
     adapter.
169. Rewinding/slitting and confection follow as bounded adapters after the
     printing contract is verified.
170. The MES may replace Excel before every digital terminal exists. Remaining
     operations use MES-printed cards and deliberate recovery entry until their
     kiosks are added; Excel remains read-only after cutover.
171. Approximately 70–80% of implementation effort belongs to the shared model,
     planning, permissions, persistence, review, inventory links, migration, and
     verification, with roughly 20–30% in operation-specific terminal adapters.
172. Excel parity includes Shift Manager entry of required summary actuals for
     every operation before that operation's digital terminal exists.
173. Manual summary entry does not require fabricated roll, box, container,
     unit, or other machine-level detail.
174. All execution sources expose one canonical operational-card actuals
     summary to review, inventory posting, costing export, status, and reporting.
175. Actuals retain capture provenance: manual summary, terminal detail, paper
     recovery, migration where applicable, or admin correction.
176. Terminal detail is authoritative when captured and the normalized summary
     is calculated from it; valid manual/recovery actuals may consist only of an
     authoritative summary.
177. Manual gross, tare, net, and other internally related totals are validated;
     terminal summaries are recalculated atomically when detail changes.
178. Each operation has an effective-dated normal capture mode. Manual summary
     is normal before terminal go-live and terminal detail is normal after its
     selected cutoff, preferably at a month boundary.
179. A capture-mode cutoff does not rewrite history. Existing actuals keep their
     original values and source provenance.
180. After terminal go-live, ordinary manual total entry is hidden, not deleted.
     Controlled paper-recovery and admin-correction paths remain permanently.
181. Admin correction is the catch-all repair path for mistakes in either
     summary or detailed facts and preserves prior values/history.
182. Source-specific forms and terminal collectors call one transactional
     actuals service; they do not duplicate lifecycle, validation, review, or
     export business logic.
183. The MES provides soft rails: stable core identities, lifecycle, ownership,
     permissions, constraints, and audit history with flexible order-specific
     recipes, routes, supplementary cards, manual release, and correction.
184. The system has low algorithmic complexity; its main engineering challenge
     is coherent concurrent writes from managers and kiosks.
185. Concurrency is handled with database transactions and constraints,
     idempotent commands, immediate persistence, and optimistic stale-write
     rejection—not with a complex distributed architecture.
186. No high-level business-scope or architecture question remains before formal
     system design and implementation planning.
187. Remaining work consists of system design, per-operation field/print
     contracts, migration/export mappings, and a dependency-ordered slice plan.
188. Multiple cards for the same operation are permitted only through deliberate
     Shift Manager creation for split, rerun, recurring, or supplementary work;
     the MES does not split work automatically.
189. Every operation has a printable paper-execution card by default; separate
     labels remain out of scope unless a real operation brief requires them.
190. Live terminal time is derived from persisted execution segments, while
     manual paper time retains its declared value and provenance. Costing-
     calendar interpretation stays outside the MES.
191. Unstarted dependency-free cards may be deleted; cards with production or
     dependent facts are voided/cancelled and retained.
192. Any account with inventory-modification capability may post an attributed
     physical-reconciliation adjustment without a separate approval workflow.
193. Technology and code-organization choices are owned by the engineering
     design process unless they alter the confirmed deployment or business
     behavior.

## Change Log

- **2026-08-14:** Opened discovery from the user's centralized MES discussion;
  inspected the extrusion pilot and Shift Manager workbook V14.22; recorded the
  provisional decomposition, simplification direction, missing evidence, and
  dependency-ordered questions. No estimate made.
- **2026-08-14:** Confirmed that Excel has no role in the end state. The MES
  replaces workbook planning and actuals repositories while preserving
  operational-card printing and after-the-fact paper recovery entry for
  redundancy.
- **2026-08-14:** Confirmed creator-owned production-order accountability. The
  current material-based division is a practical convention, operation work
  overlaps, and no delegation or operation-level ownership-transfer workflow
  is required.
- **2026-08-14:** Confirmed that production-order ownership is a Shift Manager
  data boundary: the non-owner has neither visibility nor editing access to the
  private production-order workspace. A central deployment must preserve
  logically isolated owner workspaces.
- **2026-08-14:** Refined the isolation rule for shared operations. Released
  cards from both owners enter one shared operation queue; both managers may
  see minimal queue context and reorder all entries, while only the originating
  manager may edit or withdraw the card itself.
- **2026-08-14:** Fixed queue reordering as the sole cross-owner modification.
  All other scheduling and card actions remain owner-only, with no change-
  request, notification, approval, transfer, or temporary-access workflows.
  Future questions will lead with the simplest safe recommendation.
- **2026-08-14:** Closed production-order numbering as a standard centralized-
  system decision rather than a business question: one global identity and
  display-number sequence, with ownership stored separately.
- **2026-08-14:** Corrected the numbering and migration record. The historical
  workbook ranges are intentionally disjoint, migrated records preserve their
  existing numbers, and future records use one shared central sequence visible
  only as sequence state across isolated manager workspaces. Migration is
  limited to useful normalized data from July 1, 2026 onward; older unreliable
  history is excluded.
- **2026-08-14:** Confirmed end-of-card material posting. Execution completion
  enters Shift Manager review; review submission records declared consumption
  and posts the linked inventory issue. Extrusion receives editable theoretical
  suggestions from actual net output and recipe percentages, while non-obvious
  consumption is entered manually. Duplicate posting and silent correction are
  prevented without adding automatic backflush or costing logic.
- **2026-08-14:** Confirmed non-blocking inventory verification. Missing or
  suspicious inputs and negative projected balances produce review warnings,
  but declared consumption may drive stock below zero. Known entry errors are
  corrected at their linked posting; otherwise a preserved reconciliation
  adjustment aligns the ledger to physical stock.
- **2026-08-14:** Removed automatic card-output receipts from the proposed
  initial scope. Ordinary intermediate and make-to-order output remains in
  production actuals; general finished inventory, dispatch, sales, and invoicing
  are deferred. Make-to-stock remains as a bounded source-order lot whose
  reviewed output is consumed explicitly by later cards, matching the workbook's
  useful MTS balance relationship. Early route termination never creates an item
  without a deliberate manager declaration.
- **2026-08-14:** Refined the make-to-stock ledger and costing boundary. Positive
  reviewed output and negative source-linked consumption retain exact producing-
  and consuming-order provenance. Each source production order remains its own
  MTS output identity, and a consuming card may reference several sources. No
  pooled item code or MES weighted-average valuation is required. Source cost is
  based on its production period, not its later consumption month. The app does
  not hide `±5 kg` balances; monthly reconciliation clears residuals through
  actual adjustment entries.
- **2026-08-14:** Confirmed manual operational-card release and duplication
  boundaries. New orders explicitly choose their operations; duplication copies
  recurring planned route/specification data but no execution history. Added
  operations are marked recurring or one-off supplementary, and supplementary
  cards are not reproduced by later duplication. Only the owning Shift Manager
  releases or prints work; no completion or review event advances the route
  automatically.
- **2026-08-14:** Confirmed one central LAN deployment. Shift Manager computers
  and kiosk terminals use the same server application and database; there are no
  terminal-local databases, disconnected writes, or synchronization workflows.
  The service stack and kiosks restart automatically after power restoration.
  Printed cards and later attributed recovery entry cover the bounded case where
  machinery can run but the server, network, or terminal cannot.
- **2026-08-14:** Confirmed the minimum account model. Shift Managers have named
  accounts, one administrator/recovery account has full authority, and each
  operation has one permanently signed-in fixed kiosk. Operators do not log in;
  kiosk execution is attributed to the operation and active shift, with worker
  names available separately through the shift-roster CSV. Manual alternate-host
  printing may be documented as a low-tech recovery option without adding
  automatic failover.
- **2026-08-14:** Closed initial raw-material inventory to four ledger actions:
  receipt, reviewed card consumption, disposal/sale removal, and reconciliation.
  Disposal or sale reduces quantity with a reason/reference but adds no sales,
  dispatch, invoicing, or profit workflow. Reservations, purchasing workflow,
  transfers, allocation, replenishment, and MRP are excluded.
- **2026-08-14:** Confirmed a shared minimal execution flow for printing,
  rewinding/slitting, and confection: release, start, pause/resume, finish, and
  optional owning-Shift-Manager review for missing actuals. Their differences
  are limited to displayed instructions and captured fields. Extrusion keeps its
  bounded specialist extensions without creating separate lifecycle engines for
  the simpler operations.
- **2026-08-14:** Confirmed named machine assignment and multiple kiosks per
  operation where physical distance requires them. Printing has machines `1–2`,
  confection anticipates `1–4`, and one extrusion kiosk continues to cover four
  machines with one currently inactive. Kiosks remain operation-specific and
  may show one or several configured machine queues. Machine selection is manual
  and each machine permits at most one running card.
- **2026-08-14:** Closed costing integration to a stable one-way CSV/Excel
  extract of raw production, consumption, MTS-link, and relevant adjustment
  facts for a selected period. The MES performs no costing, valuation, price
  import, live API synchronization, or writeback. Exact export columns are a
  later field-mapping task, not a scope-complexity question.
- **2026-08-14:** Removed second-workbook inspection as a discovery dependency.
  The user confirmed that it implements the same business behavior as the
  inspected workbook and is a simpler subset without extrusion. Its printing,
  rewinding/slitting, and confection records require later source mapping and
  migration validation, not a new workflow or architecture investigation.
- **2026-08-14:** Closed migration coexistence with a one-way cutover. July 1,
  2026 defines the normalized source population; a later declared rollout date
  makes the MES the sole writable operating system. Reliable records are bulk-
  migrated where practical, while omitted history remains read-only reference
  and is recreated in the MES only when useful. No dual writing, synchronization,
  or complete historical conversion is required.
- **2026-08-14:** Confirmed a greenfield successor rather than expansion of the
  extrusion pilot. The pilot's validated behavior and deployment experience
  become requirements and acceptance evidence, but its schema, code structure,
  and incremental implementation history create no compatibility obligation.
  The successor starts from a coherent multi-operation model and is delivered
  in tested vertical slices.
- **2026-08-14:** Excluded ERPNext and general ERP process frameworks. The
  successor is custom factory-LAN data-capture, planning, and execution software
  whose purpose is to simplify rather than reproduce administrative ERP rails.
  Its expected interactive scale is approximately seven fixed terminals, two
  Shift Managers, and one recovery administrator; this needs reliable ordinary
  transactions, not distributed or high-scale infrastructure.
- **2026-08-14:** Placed inventory inside the same application and database as a
  permission-isolated business module. Named inventory users can operate only
  its screens, Shift Managers receive narrow lookup and card-consumption
  capabilities, and the recovery administrator can access everything. Explicit
  internal contracts and atomic card-review posting provide separation without
  a second service, API, authentication system, or synchronization path.
- **2026-08-14:** Refined inventory authorization into two reusable capabilities.
  Read-only access exposes the dashboard, catalogue, and balances; modification
  access permits the four confirmed ledger transaction types. Either capability
  can be granted to a named inventory user or a Shift Manager without changing
  production-order ownership. Card-review consumption remains independently
  available through the owning manager's production workflow.
- **2026-08-14:** Defined inventory availability as two displayed figures:
  current posted ledger balance and projected balance after included planned/
  released cards. Projection is an informational calculation only; it makes no
  reservation, allocation, deduction, or ledger entry and is not treated as a
  meaningful scope-complexity driver.
- **2026-08-14:** Closed high-level discovery and fixed the delivery model as
  entirely Codex/AI-agent implementation under Superpowers design, planning,
  testing, review, and verification gates. The user provides business decisions
  and factory acceptance rather than source-code review. Assessed the system as
  moderate custom factory software.
- **2026-08-14:** Corrected the AI-only estimate after the user challenged its
  human-like effort unit. The previous serial range double-counted verification
  and underweighted agent parallelism and is withdrawn. The revised range is
  14–24 active Codex build days if work were serialized, with expected elapsed
  targets of 8–12 active days for a feature-complete candidate and 12–18 active
  days—normally about 2½–4 calendar weeks—for cutover readiness.
- **2026-08-14:** Adopted a contract-first, vertical-slice delivery design. A
  shared terminal contract owns queue, lifecycle, timing, shift, persistence,
  conflict, and review behavior; operation implementations supply bounded
  fields, layout, validation, printing, and approved extensions. Recommended
  building the MES planning/paper foundation through extrusion parity first,
  using printing to finalize the generic terminal adapter, and then adding
  rewinding/slitting and confection. MES-printed cards preserve phased operation
  without restoring Excel as a writable system of record.
- **2026-08-14:** Unified manual paper actuals and terminal detail behind one
  canonical summary contract. Shift Managers enter only paper-level totals;
  terminals capture useful detail and derive the same summary. Each operation
  switches its normal capture source on an effective date while recovery and
  attributed admin correction remain permanent. Recorded the design goal as a
  structured repository with flexible order-level behavior and identified
  transactional concurrency—not algorithms—as the principal engineering risk.
- **2026-08-15:** Completed the final scope-gap audit. Closed deliberate multi-
  card handling, printable-card defaults, supplementary unplanned rewinding,
  time semantics, delete-versus-void behavior, and reconciliation authority
  using the established simplicity rules. Confirmed that no general discovery
  question remains; the next artifacts are system design, operation contracts,
  migration/export mappings, and the vertical-slice implementation plan.
