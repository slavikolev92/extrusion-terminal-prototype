# Task 21: Order-Finish Review Extension

Status: residual future Terminal UI scope. Task 22 already implements the
timing-aware Finish Review in source and it is locally verified, but it is not
deployed. Task 21 is not a second, unstarted finish-review feature. Its only
remaining work is the contextual production-summary extension described below.
This record does not authorize application changes, production deployment, or
mutation of the runtime database.

## Relationship To Task 22

Task 22 already provides two deliberately different finish paths.

For a `running` or `paused` card, including both normal completion and entry
into `awaiting_rewinding`, Task 22 provides the timing-aware Finish Review:

- the review opens from the existing Terminal finish action;
- it binds the loaded version and frozen proposed stop to a review token;
- it permits the approved editable timing draft;
- it renders the existing pallet-production table; and
- it applies the reviewed timing and finish mutation atomically.

Residual Task 21 work for these active-card outcomes must extend that existing
tokenized review and reuse its pallet aggregation and mutation path. It must
not create another review dialog, finish route, confirmation token, timing
editor, pallet calculation, or completion transaction.

Finalization of an `awaiting_rewinding` card is a separate, timing-neutral
path. Task 22 deliberately preserves its simple confirmation and dedicated
backend finalization operation. Residual read-only order and outcome context
may be added to that confirmation, but it must never adopt a frozen proposed
stop, timing editor, finish-review token, editable timing draft, or timing-ledger
mutation. Finalization must continue to leave timing and `finished_at`
unchanged.

The shipped Task 22 behavior is recorded in
`docs/implementation-notes/terminal-timing-correction.md` and its final
design remains the source of truth for both branches.

## Existing Review Content To Preserve And Reuse

Task 22 already renders:

- the order number and machine number in the Finish Review header; and
- the existing pallet-production table, whose total row includes submitted
  roll count, total produced gross, and total produced net.

These are existing content, not wholly missing Task 21 behavior. Any future
Task 21 implementation must preserve and reuse them. It may deliberately make
those existing values more prominent when that improves scanability, but must
not create a competing order header, roll count, weight-total calculation, or
pallet aggregation.

## Purpose Of The Remaining Extension

Give the operator fuller order identity, target-versus-produced context, and
clear branch-specific outcome wording before confirming the applicable finish
action. The extension remains read-only: corrections stay on the normal
Terminal order screen, and each existing branch retains its own authoritative
confirmation and backend mutation path.

## Remaining Required Information

The residual extension is limited to:

- customer;
- product/type;
- size/thickness;
- primary material;
- imported target gross kilograms;
- a clearly labelled gross-weight delta: `remaining` below target and
  `over target` above target;
- the current informational sent-roll marker when rewinding is relevant;
- explicit outcome wording for normal completion, ending active extrusion into
  `awaiting_rewinding`, and later timing-neutral waiting-card finalization;
  and
- any deliberately more-prominent reuse of the already-rendered order/machine
  header and pallet total row.

The delta must use the existing total produced gross from saved roll entries.
The existing pallet-production table remains the source for submitted roll
count and produced gross/net totals. Do not compare the rewinding marker with
returned rolls, create roll placeholders, or add a validation rule.

Pallet assignment remains optional, and target variance remains non-blocking
unless an existing backend rule independently blocks the finish.

## Preserved Boundaries And Backend Invariants

- Running/paused normal completion and entry into waiting reuse Task 22's
  existing modal, frozen review state, token, editable timing behavior,
  pallet-production table, and atomic timing/finish mutation path.
- Awaiting-rewinding finalization retains its separate simple confirmation and
  dedicated timing-preserving backend path; it never receives Task 22 timing
  controls or tokenized timing semantics.
- Finalization from `awaiting_rewinding` must not mutate timing or
  `finished_at`.
- Do not duplicate, replace, or reopen Task 22's timing controls.
- Do not add fields, migrations, tables, status transitions, routes, audit
  records, or another completion workflow.
- Do not alter existing finish validation, timing closure, final-shift
  attribution, queue normalization, machine reuse, rewinding rules, stale-write
  protection, or pallet optionality.
- Each final submission must continue through its existing backend operation,
  which re-reads current data and enforces all lifecycle invariants.
- Do not add editable production controls inside either confirmation.
- Do not imply that the residual customer/product/dimension/material context,
  target, clear delta, marker/outcome wording, or more-prominent summary reuse
  is already implemented.

## Expected Implementation And Verification

When separately scheduled, make the smallest presentation/view-model extension
to the existing branch-specific confirmations.

For `running` and `paused` cards, add the residual context to Task 22's
tokenized review and verify continued reuse of its token, timing draft,
pallet-production aggregation, and atomic timing/finish operation.

For `awaiting_rewinding` cards, add only the applicable residual read-only
context to the simple confirmation and verify that the submission remains
tokenless and timing-neutral through the dedicated waiting-finalization
operation. Tests must prove timing rows and `finished_at` are unchanged.

Focused render and interaction coverage must distinguish normal completion,
active-card entry into waiting, and waiting-card finalization. It must also
cover customer/product/dimension/material context, target, the correctly
labelled remaining or over-target delta, marker/outcome wording, and preserved
reuse of the existing order/machine header and pallet totals.

Use temporary SQLite databases and the repository-local Playwright installation
for any browser verification. Do not use the production runtime database.
Before implementation, perform the migration assessment required by
`docs/implementation-notes/sqlite-migration-and-deployment-playbook.md`; this
residual read-only presentation scope expects no migration.

## Completion Criteria

Task 21 is complete only when:

- the active-card Task 22 Finish Review adds the residual read-only context
  without duplicating its tokenized timing, pallet, or atomic mutation path;
- the awaiting-rewinding simple confirmation adds the applicable residual
  context without gaining frozen timing, an editor, a review token, or any
  timing-ledger mutation;
- existing order/machine and roll/gross/net totals are preserved and reused,
  with any new prominence deliberate rather than recalculated;
- customer/product/dimension/material, target, clear delta, marker, and
  branch-specific outcome wording are focused-tested and browser-verified; and
- review confirms every existing finish, timing, rewinding, stale-write, shift,
  queue, and pallet-optional invariant remains enforced.
