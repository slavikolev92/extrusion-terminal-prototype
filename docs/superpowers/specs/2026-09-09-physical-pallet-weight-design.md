# Physical Pallet Weight Design

Date: 2026-09-09

Status: Approved; final review corrections incorporated on 2026-09-10

Approved interactive reference:
`ui-prototypes/physical-pallet-weight-summary.html`

## Goal

Add optional physical transport-pallet weights to the existing per-card pallet
summary. Operators and shift managers must be able to enter one weight for each
numbered pallet, review trustworthy gross/net pallet totals, complete cards only
when an activated set of pallet weights is complete, and print the same values
on the existing operational card.

This is a bounded extension of the extrusion-card pallet attribution already in
the application. It does not create a warehouse pallet entity, shipping state,
capacity workflow, pallet label, barcode, or cross-card pallet.

## Terminology And Calculations

The feature distinguishes the physical wooden transport pallet from the roll
core (`Шпула`). The gross weight entered for a roll does not include the
transport pallet.

For each numbered pallet:

- `Брой ролки` is the count of saved rolls with a gross weight assigned to that
  pallet number.
- `Бруто без палет, кг` is the sum of those rolls' gross weights. It includes
  their roll cores and excludes the transport pallet.
- `Тегло палет, кг` is the separately entered physical transport-pallet weight.
- `Бруто с палет, кг` is `Бруто без палет + Тегло палет`. It is unavailable
  when the physical pallet weight is missing.
- `Нето, кг` is the sum of the rolls' existing net weights, meaning the pure
  film weight after roll-core tare has already been removed. Physical pallet
  weight does not change this value.

The table uses exactly these six columns in this order:

1. `Палет №`
2. `Брой ролки`
3. `Бруто без палет, кг`
4. `Тегло палет, кг`
5. `Бруто с палет, кг`
6. `Нето, кг`

The pallet-number column is narrower than the others. The remaining five
columns have equal width. Gross-without-pallet and net values retain the
existing one-decimal presentation. Physical pallet weights and the
gross-with-pallet values derived from them use exactly two decimal places and
a decimal point.

When a pallet weight is absent, `Тегло палет, кг` and `Бруто с палет, кг` show
a plain `-`. They never show an invented `0.0`. `Бруто без палет, кг` and
`Нето, кг` remain available.

The `Общо` row always shows total roll count, gross without pallet, and net.
Total pallet weight and total gross with pallet appear only when every used
numbered pallet has a valid physical weight and there are no gross rolls in
`Без палет`. Otherwise both cells show `-`. Totals are calculated from the
complete underlying record set, not only visible rows.

## Ownership And Persistent Data

A physical pallet weight belongs to one numbered pallet within one operational
card. It does not belong to the card globally and is not copied onto individual
rolls.

Add a `card_pallet_weights` table with this contract:

```sql
CREATE TABLE IF NOT EXISTS card_pallet_weights (
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    pallet_number INTEGER NOT NULL CHECK (
        typeof(pallet_number) = 'integer'
        AND pallet_number BETWEEN 1 AND 999
    ),
    weight_hundredths INTEGER NOT NULL CHECK (
        typeof(weight_hundredths) = 'integer'
        AND weight_hundredths BETWEEN 1 AND 10000
    ),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (card_id, pallet_number)
);
```

`weight_hundredths` stores hundredths of a kilogram exactly: `12.50 kg` is
stored as `1250`, and `100.00 kg` as `10000`. A missing row means no physical pallet weight
has been supplied. Zero is neither a valid stored value nor a missing-value
sentinel.

The change uses the ordered schema migrations derived from `app/migrations.py`.
M007 creates the final hundredths table for production databases, where this
unshipped feature has never existed. M008 is a deterministic compatibility
migration for development databases that recorded the earlier tenths-based
M007: each valid value becomes `weight_hundredths = weight_tenths * 10` while
card, pallet, and timestamp fields are preserved. It is a validated no-op when
M007 already created the final schema.
Existing cards begin with no physical pallet-weight rows. Re-import preserves
the table because pallet weights are terminal-entered production data.

The application keeps only the latest value. No separate pallet-weight edit
history or audit-log subsystem is added. Every save increments the parent
card's version and update timestamp, so existing optimistic conflict detection
prevents silent overwrites.

## Pallet Lifecycle

The application continues deriving used pallets from the current saved roll
assignments. It does not create independently managed pallet objects.

A numbered pallet is used only while at least one roll with a saved gross
weight is assigned to it. If a roll deletion, pallet reassignment, or gross-
weight clearing removes the last gross roll from a numbered pallet, its saved
physical pallet weight is deleted in the same database transaction. Reusing
that number later starts without a weight. The successful mutation message
identifies any pallet weights removed by this cleanup.

The `Без палет` group never accepts or stores a physical pallet weight. A
future-roll default pallet number does not create a summary row or a weight
record.

The summary treats a weight record for a pallet with no participating gross
roll as invalid stored data rather than silently omitting it. Normal write
paths prevent this state; the defensive read boundary reports it so the data
can be repaired.

Structural integrity and completion completeness are separate invariants.
Every finish transition, including entry into `awaiting_rewinding`, must build
and structurally validate the pallet summary inside the same database
transaction as the lifecycle change. Entry into `awaiting_rewinding` may
accept a structurally valid partial set, but it must reject orphaned or otherwise
inconsistent saved pallet data. Normal completion and finalization after
rewinding additionally enforce the completeness rule below.

## Input And Validation

The input is optional until at least one physical pallet weight is saved for
the card. Each editable numbered-pallet row accepts:

- an integer such as `12`, displayed after save as `12.00`;
- one or two fractional digits such as `12.5` or `12.55`;
- either `.` or `,` as the submitted decimal separator; and
- a positive value from `0.01 kg` through `100.00 kg` inclusive.

Leading and trailing whitespace is ignored. Blank or whitespace-only input
clears that pallet's weight. The parser rejects zero, negative values, text,
scientific notation, non-finite values, embedded whitespace, more than one
decimal separator, and more than two fractional digits. Accepted values are
stored exactly as integer hundredths and normalized to two displayed decimals;
for example, `10.35` remains `10.35` and `12.5` displays as `12.50`. The raw
submitted value must not exceed `100.00 kg`. The parser never clamps, rounds
away an accepted hundredth, or reinterprets invalid input.

The backend is authoritative. Client-side input restrictions and live errors
exist only to give faster feedback. An over-limit error identifies the pallet,
for example: `Теглото за палет №3 не може да бъде повече от 100.00 кг.` Invalid
precision or syntax and below-minimum values also identify the affected pallet.

Each field is saved independently. A save targets exactly one currently used
numbered pallet and either adds/updates its value or clears it. Unknown pallet
numbers, duplicate fields, malformed values, or a pallet that ceased to be
used after page load are rejected without a write. Each individual operation
is atomic.

## Conditional Completeness Rule

The feature has two valid completion states:

1. **No physical weights:** no numbered pallet has a saved physical weight.
   Pallet weights remain optional and existing pallet-assignment behavior is
   unchanged.
2. **Complete physical weights:** every gross roll has a numbered pallet and
   every used numbered pallet has one valid physical weight.

Any other state is partial. Partial values may be saved while a card is
`pending`, `running`, `paused`, or `awaiting_rewinding`, because operators may
enter them progressively. Once one weight exists, normal completion and final
completion from `awaiting_rewinding` are hard-blocked until either all used
pallets are weighted and all gross rolls are assigned, or every physical
pallet weight is cleared.

Ending extrusion into `awaiting_rewinding` is not final completion and remains
allowed with partial values because additional rolls may not have returned.
The review shows a nonblocking warning that pallet weights must be completed
before finalization.

Completed and archived cards may be corrected one pallet at a time. A partial
state may therefore exist temporarily after completion, but print readiness is
blocked until the weights are either complete or all cleared. This preserves
the same immediate-save interaction without allowing a misleading printout.

The hard blocker has no `Продължи въпреки това` bypass. It identifies both
unassigned gross-roll count and missing numbered pallets as applicable. The
database finish transaction re-evaluates the rule; disabling a button in the
browser is never the only enforcement.

The existing mixed assigned/unassigned warning remains nonblocking only while
the card has no physical pallet weights. Once one weight exists, the stricter
completeness rule takes precedence.

## `Обобщение по палети` Modal

The existing terminal `Палети` action and exact modal title
`Обобщение по палети` remain. The modal is restyled to the same restrained
industrial visual language as the accepted order-finish review: white surface,
pale blue-gray borders, modest radius, dark readable text, a pale-blue icon
tile, and a visually separate full-width footer. It must remain comfortably
readable at the supported terminal viewports rather than shrinking into a
dense office table.

The terminal `Палети` action includes a compact outlined transport-truck icon
that remains recognizable at the button's `20px` rendering size. This bounded
change does not redesign unrelated application icons.

The header contains a matching outlined clipboard/list icon tile, the title,
the current customer and order in the format `Клиент (№ 25000)`, and the
existing upper-right close control. Reusing the accepted finish-review icon
family is preferable to inventing a different style.

The table has the six approved columns, centered headings and numeric data,
left-aligned pallet identifiers, tabular numerals, a vertically scrollable body,
and sticky headings and totals. The footer remains visible while rows scroll.

There is no separate view/edit mode and no `Добави тегла`, `Отказ`, or
`Запази` action. Every numbered-pallet row always contains a restrained input
in `Тегло палет, кг`; missing values appear as blank inputs. The only footer
action is the neutral `Затвори`. `Без палет` never gains an input. When there
are saved gross rolls but no used numbered pallets, the read-only `Без палет`
row remains visible and the modal explains that rolls must first be assigned to
a numbered pallet. When there are no saved gross rolls, the modal shows its
existing empty-state explanation instead of editable rows.

A changed field saves when the operator presses Enter or moves focus out of
that field, including directly into another pallet-weight field. Whole numbers
normalize after successful save (`20` becomes `20.0`). Blank clears the stored
value. There is no modal-level save step, and closing the modal is not a
completion or validation boundary: successfully entered values have already
persisted independently.

The client serializes saves so two rapid field changes cannot race on the
card-version token. Each successful response returns the authoritative
normalized value, updated card version, affected row calculation, and totals;
the controller applies them without moving the table or closing the modal.
While a field is pending it cannot submit a duplicate request. A validation or
stale-version failure preserves the typed value while the modal remains open,
marks and focuses the field, and shows the existing reload-required treatment
where applicable. Validation
feedback appears once in the fixed footer status region; the input keeps a red
invalid-state border and an accessible relationship to that status message,
but no visible per-row error sentence is inserted under the field. The server
remains authoritative.

The pallet-summary footer and Finish Review footer use the same restrained
semantic-banner language on the surfaces touched by this feature: pale green
with a check-circle for successful saves, pale red with a circle-X for errors
and hard blockers, and pale amber with a warning triangle for nonblocking
warnings. Icons are decorative, use the same outlined family, render at `20px`,
and do not replace the message text. The existing pallet-summary section icon
tile remains `24px`.

Queued and active are explicit per-field states. The raw value is frozen when
queued, a focused Enter-submitted input remains focusable/read-only rather than
being disabled, and a stale, network, or malformed-response failure trips one
controller-wide fatal lock so no later queued request is sent against uncertain
state. In that lock state, a keyboard-reachable `Презареди` action appears in
the modal status area; the ordinary footer still contains only `Затвори`.

After a successful field save, that row's gross-with-pallet value refreshes.
Total pallet weight and total gross-with-pallet appear only when every used
numbered pallet has a saved weight and no gross rolls are unassigned;
otherwise those total cells show `-`. Saving one value does not require the
operator to enter the remaining values in the same visit.

The existing modal coordination remains authoritative on `/terminal`: only one
drawer/modal may be active, focus is trapped, Escape and the close control work,
the background is inert, and focus returns to the opener after ordinary close.
A polling-detected stale-card takeover closes a clean modal safely. If the
modal has dirty, queued, active, or failed input, it instead freezes the fields,
preserves the draft, and exposes the in-modal reload action; it never discards
uncertain operator input merely to show the outer stale alert. Closing the modal performs
no separate write and does not validate final-completion eligibility. If close,
backdrop, or Escape moves focus out of a dirty field, that normal blur save is
allowed to finish first. The modal then closes automatically after success.
An invalid unsaved draft is discarded on explicit dismissal and its field is
restored to the last authoritative saved value. A stale, network, or malformed-
response failure is clearly reported and never presented as saved, but it must
not trap the operator inside the modal; explicit dismissal remains available
while the existing optimistic-concurrency and reload protections continue to
guard later writes. With no dirty or pending field, dismissal is immediate and
never sends a request. A successful-save message is transient to that modal
visit: successful dismissal clears it so reopening starts with a neutral status
area while the saved value remains visible.

## Terminal And Admin Availability

Terminal operators may add, correct, or clear pallet weights for terminal-
visible `pending`, `running`, `paused`, `awaiting_rewinding`, and `completed`
cards. A terminal save requires an active shift, following existing operator
write rules.

The admin card detail exposes the same pallet summary and inline-entry modal for
`completed` and `archived` cards. It uses a separate save route and does not
require an active shift. Admin pallet-weight correction is separate from the
large roll-ledger save so changing roll assignments and changing physical
pallet weights cannot ambiguously target two different pallet sets in one
form submission. The admin must first save roll changes, then edit the freshly
derived pallet summary. If the outer admin card form has unsaved changes, the
pallet summary does not open and directs the manager to save those changes or
reload the page to discard them first.

After an inline save, the page updates optimistic-version tokens only for forms
belonging to the same card. On `/terminal`, the polling monitor defers while the
serialized save queue is active and reconciles once against the final returned
card version. The application must neither report its own pallet save as an
external edit nor hide a genuinely newer concurrent version.

That reconciliation is structural rather than selected-version-only. Before
the queue starts, the monitor retains the active-card list, waiting-card list,
selected-card snapshot, and shift signature. At queue idle it may silently
accept only the exact selected-card version and update-timestamp changes
reported by the successful local saves. Any queue membership, ordering,
lifecycle, other-card, selected-card-beyond-the-returned-version, or shift
change follows the existing stale-data/reload treatment. The monitor must not
adopt the complete new signature merely because the selected card has the
expected version.

Admin archive removal remains outside this task.

## Unified Finish Review

The accepted finish-review structure, proportions, typography, timing editor,
footer actions, and lifecycle behavior stay unchanged. Only its production
table and pallet-weight validation are extended.

The production table adopts the same six columns and calculations as the
pallet-summary modal. Its former presentation-only `0.0` pallet-weight seam is
removed. Missing physical weights display `-` and do not change net film
weight.

Every attempt to open a Finish Review obtains a fresh, server-authoritative
review payload for the submitted card version before showing the dialog. The
payload contains the complete pallet rows and totals, lifecycle-specific
warnings and blockers, and `can_confirm`, all derived from one internally
consistent database snapshot. It replaces the previously rendered pallet
table and eligibility state instead of assuming that page-load markup is still
current.

The same review-state assembler serves normal completion, entry into
`awaiting_rewinding`, and waiting-card finalization. Initial completion keeps
the existing signed timing-review token and editable timing draft. Waiting-card
finalization uses a tokenless, read-only refresh and must not reopen or mutate
timing. Pallet autosave does not directly maintain a second hidden copy of the
Finish Review; refreshing at the review boundary keeps the two UI components
independent. The final database transaction still rechecks structural integrity
and final completeness rather than trusting the payload or `can_confirm`.

For normal completion and `awaiting_rewinding` finalization, a partial weight
set produces a visible hard-blocking message and disables confirmation. The
server repeats the same check in the final transaction. For the initial
transition into `awaiting_rewinding`, partial weights produce only the
nonblocking warning described above. Timing remains editable only during the
initial extrusion completion, exactly as already implemented.

## Operational-Card Print

The existing completed/archived print route remains the only printing surface.
The separate transport/shipping label is a follow-on task and is not designed
or implemented here.

The back-page pallet summary uses the same six columns and current saved data.
Because the approved labels cannot remain legible in either existing 53.5 mm
half-width pallet block, page 2 uses one pallet table spanning the combined
middle and right summary columns while the six-row production summary remains
on the left. Up to the measured page-2 row capacity is printed there. When the
complete pallet list does not fit, page 2 omits the partial table and the full
list starts on the existing overflow pages, which repeat the order context.

Numbered pallets remain sorted numerically and `Без палет` remains last when
numbered and unassigned rolls are mixed. All-unassigned cards continue to omit
the print pallet-summary table because there is no numbered transport pallet
to report.

The printed pallet table contains one `Общо` row exactly once. If every
numbered pallet row plus the total fits in the measured page-2 capacity, the
total follows the final pallet row on page 2. Otherwise page 2 omits the pallet
table, the complete row set starts on overflow pages, and the total follows the
last pallet row on the final overflow page. The total consumes one measured row
slot. Pagination must keep it with at least one preceding pallet row; it may
not appear alone on a new page. Repeated overflow tables repeat their column
headings but not the total.

If no physical weights exist, numbered rows print gross without pallet and net
while pallet weight and gross with pallet print `-`. If a printable card has a
partial or orphaned weight set, print readiness is blocked with an actionable
message rather than printing misleading partial totals. Correcting values and
reprinting uses the latest saved weights.

## Architecture And Boundaries

`app/pallet_summary.py` becomes the single pure calculation and validation
owner for pallet rows, physical weights, formulas, completeness state, and
the column-specific one-/two-decimal presentation. Terminal, finish-review, admin, and print adapters
consume that common result instead of independently recomputing pallet
semantics.

One backend Finish Review assembler owns the version-consistent combination of
the shared pallet summary, lifecycle-specific messages, and confirmation
eligibility. The active timing-review and read-only waiting-review routes adapt
that common state to their existing lifecycle-specific contracts.

`app/db.py` owns persistence, optimistic version checks, state permissions,
atomic per-pallet saves, and orphan cleanup after roll mutations.
`app/main.py` owns strict single-field request parsing and the common
terminal/admin JSON response contract. Server-rendered Jinja owns initial
presentation; small vanilla-JavaScript behavior owns modal state, serialized
autosave, focus, and immediate validation feedback without becoming the data
or calculation authority.

Important stored-data rules are protected in SQLite where practical and always
rechecked in backend code. No new framework, background service, client-side
store, or API architecture is introduced.

## Error And Recovery Behavior

- Invalid input keeps the typed value visible, identifies the affected pallet, and
  writes nothing.
- A stale card version blocks that field save and requires reload.
- A concurrent roll mutation changes the parent card version and therefore
  prevents a weight form based on an old pallet set from saving.
- A local save is reconciled against the complete structured terminal snapshot;
  unrelated card, queue, or shift changes retain the normal reload warning.
- Network or malformed-response failures never claim that a value was saved;
  because the client cannot know whether the server committed before the
  response was lost, the controller requires a reload before retry. The modal
  remains open by default to show that recovery state, but explicit dismissal
  is still allowed and does not mark the draft as saved.
- Unexpected or inconsistent saved roll/weight data uses the existing narrow
  fail-soft summary boundary so the rest of the terminal remains usable, but
  completion and print remain blocked.
- A failed completion keeps the review open and preserves the reviewed timing
  draft under the existing finish-review contract.
- A failed print remains on the existing print-blocked page with a concrete
  correction message.

## Testing And Verification

Automated tests must cover:

- M007/M008 fresh-schema and version-6/tenths-schema upgrade behavior, exact
  constraints, deterministic conversion, idempotence, rollback, foreign keys,
  and preservation of all prior data;
- integer-hundredths conversion, comma/dot acceptance, blanks, bounds, precision,
  malformed values, duplicate/unknown/missing single-field request values, and
  atomic failure;
- one value per card/pallet and isolation of identical pallet numbers on
  different cards;
- derived rows and all six calculations for none, complete, partial, mixed,
  all-unassigned, empty, and orphaned data;
- total visibility rules and exact column-specific one-/two-decimal formatting;
- terminal and admin state permissions, active-shift enforcement, successful
  independent saves and clears, partial active/completed/archived states, final
  completion and print enforcement, and stale-write conflicts;
- cleanup when the last gross roll is deleted, reassigned, or cleared, with no
  cleanup while another gross roll still uses the pallet;
- normal completion and waiting finalization blockers plus the nonblocking
  transition into `awaiting_rewinding`;
- direct database-service rejection of orphaned/inconsistent pallet state for
  every finish transition, without rejecting a structurally valid partial set
  entering `awaiting_rewinding`;
- preservation of the accepted timing-review behavior;
- save-then-open and clear-then-open Finish Reviews without a page reload for
  normal completion, waiting entry, and waiting finalization;
- print readiness, six-column output, missing-value hyphens, corrected reprint,
  one-time `Общо` placement, page-2 capacity, and overflow boundaries including
  the no-orphan-total rule; and
- accessibility, focus, keyboard operation, serialized rapid saves,
  save-aware dismissal, validation/network recovery, sticky/scroll geometry,
  and modal non-stacking.

Browser checks use a temporary SQLite database and the repository-local
Playwright installation. They cover `/terminal` and `/admin` at `1440x900`,
`1366x768`, and the existing short-height acceptance viewport `1093x614`.
Relevant screenshots go under `artifacts/ui-checks/physical-pallet-weight/` and
are deleted after acceptance unless the user requests retention. Print checks
render PDFs from temporary data and verify both page count and readable column
geometry.

Before completion, run focused tests, all JavaScript tests, the complete Python
suite, syntax/import checks, `git diff --check`, and the guarded live browser
workflow. No test may mutate `data/extrusion_terminal.sqlite3` or any file under
`production-db/`.

## Migration And Deployment Assessment

- Decision: deterministic compatibility migration; schema-only on production.
- Why: one new persistent per-card/per-pallet value requires a new table, and
  developer databases may contain the earlier unshipped integer-tenths draft.
- Existing production data affected: none; no current value has this meaning.
- Proposed migrations: M007 `physical_pallet_weights` creates the final
  hundredths table; M008 `physical_pallet_weight_hundredths` upgrades only an
  exact earlier M007 table or validates/no-ops on the final table.
- Transformation: exact prior draft values use
  `weight_hundredths = weight_tenths * 10`; production has no such rows and no
  production backfill.
- Unknown or ambiguous rows: none need transformation.
- Required tests: accepted version-6 schemas, fresh schema, malformed partial
  table, idempotence, injected rollback, exact prior-value preservation,
  integrity check, and foreign-key check.
- Production snapshot needed now: no. A final SQLite-safe backup and clone-only
  rehearsal are required before deployment.
- Deployment constraint: deploy migration and consuming code together during an
  explicitly approved maintenance window, using the documented playbook and
  existing deployment script.

## Out Of Scope

- Transport/shipping pallet-label design or printing.
- Pallet barcodes, scanning, capacity, full/closed state, dispatch, delivery,
  or warehouse inventory.
- Independent empty-pallet records or cross-card pallets.
- Editing pallet number, roll count, roll gross, roll-core tare, or roll net in
  the pallet-summary modal.
- Automatic assignment of unassigned rolls.
- Per-customer rules that automatically require physical pallet weights.
- Historical pallet-weight audit logs.
- Removing the admin archive feature.
- Task 20 Item Master, material, and recipe-catalogue work.
