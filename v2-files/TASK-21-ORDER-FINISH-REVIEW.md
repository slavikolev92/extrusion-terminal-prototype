# Task 21: Order-Finish Review Extension

Status: residual future Terminal UI scope. Task 22 already implements the
timing-aware Finish Review in source and it is locally verified, but it is not
deployed. Task 21 is not a second, unstarted finish-review feature. Its only
remaining work is the contextual production-summary extension described below.
This record does not authorize application changes, production deployment, or
mutation of the runtime database.

## Relationship To Task 22

Task 22 already supplies the timing-aware Finish Review and the authoritative
finish path:

- the review opens from the existing Terminal finish action;
- it uses a frozen proposed finish and review token;
- it permits the approved editable timing draft;
- it presents the existing pallet-production table; and
- it applies the reviewed timing and finish mutation atomically.

The residual Task 21 work must extend that existing modal, aggregation, review
token, and atomic mutation path. It must not create another review dialog,
finish route, confirmation token, timing editor, timing control, pallet
calculation, or completion transaction. It must not restate completed Task 22
work as a remaining requirement.

The shipped Task 22 behavior is recorded in
`docs/implementation-notes/terminal-timing-correction.md` and its final
design remains the source of truth for the existing timing-aware review.

## Purpose Of The Remaining Extension

Give the operator clearer order identity and production-total context while
reviewing the already-implemented finish action. The extension remains
read-only: corrections stay on the normal Terminal order screen, and the
existing review confirmation is the only mutation path.

## Remaining Required Information

The existing review must be extended to show:

- order number, machine number, customer, product/type, size/thickness, and
  primary material;
- imported target gross kilograms;
- total produced gross from saved gross roll entries;
- total produced net from saved per-roll net values;
- a clearly labelled delta: `remaining` below target and `over target`
  above target; and
- explicit outcome wording that distinguishes normal completion from ending
  extrusion into `awaiting_rewinding`, and distinguishes later
  `awaiting_rewinding` finalization after returned-roll entry.

Where a rewinding marker is relevant, show its informational sent-roll count
without comparing it to returned rolls or creating a new validation rule.

The extension must use the existing saved roll data and established
aggregations. It must not invent a second totals or pallet-summary calculation.
Pallet assignment remains optional, and target variance remains non-blocking
unless an existing backend rule independently blocks the finish.

## Preserved Boundaries

- Reuse Task 22's existing modal, frozen review state, token, editable timing
  behavior, pallet-production table, and atomic finish mutation path.
- Do not duplicate, replace, or reopen Task 22's timing controls.
- Do not add fields, migrations, tables, status transitions, routes, audit
  records, or a separate completion workflow.
- Do not alter existing finish validation, timing closure, `finished_at`,
  final-shift attribution, queue normalization, machine reuse, rewinding
  rules, or pallet optionality.
- Do not add editable controls inside the review.
- Do not imply that the residual identity, target/produced totals, delta, or
  explicit normal-versus-rewinding outcome wording is already implemented.

## Expected Implementation And Verification

When separately scheduled, make the smallest presentation/view-model extension
to the existing Task 22 review. Add focused render and interaction coverage
for the identity context, target/produced gross and net totals, remaining or
over-target label, and each lifecycle outcome wording. Verify that the existing
Task 22 review token, timing edit behavior, pallet-production aggregation, and
atomic finish path continue to be reused.

Use temporary SQLite databases and the repository-local Playwright installation
for any browser verification. Do not use the production runtime database.
Before implementation, perform the migration assessment required by
`docs/implementation-notes/sqlite-migration-and-deployment-playbook.md`; this
residual read-only presentation scope expects no migration.

## Completion Criteria

Task 21 is complete only when the existing Task 22 finish review visibly adds
the remaining identity/context, target and produced totals, clear delta, and
outcome wording; the extension has been focused-tested and browser-verified;
and review confirms that it reused rather than duplicated the existing Task 22
modal, aggregation, token, timing, and atomic mutation path.
