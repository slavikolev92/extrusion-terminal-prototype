# Task 11: Rewinding Return Workflow Specification

Status: implemented and verified locally on July 27, 2026. This document remains
the approved functional design record. The executed implementation plan is at
`docs/superpowers/plans/2026-07-26-rewinding-return-workflow.md`; the durable
shipped-behavior, migration, recovery, and verification record is at
`docs/implementation-notes/rewinding-return-workflow.md`.

## Purpose

Support extrusion rolls that rip during production and must pass through an
additional rewinding/setting operation before they can be weighed, placed on a
pallet, and included in the finished production order.

The workflow separates two real events without inventing a second business
timestamp:

1. extrusion ends, `finished_at` records the real stop, and the machine becomes
   free; and
2. the returned rolls are later entered and the card is deliberately moved to
   the existing produced/completed state.

This is the functionality specification that governed implementation. It
records the approved business behavior, UI, existing roll semantics, data
contract, safeguards, accepted visual design, and scope boundary. It does not
authorize deployment or mutation of a runtime/production database.

## Existing Physical Process

- A roll may rip during extrusion because of material, machine, or another
  production problem.
- A ripped roll is physically produced, but it is not weighed or entered at the
  extrusion terminal before it leaves for rewinding/setting.
- Extrusion may therefore produce, for example, 20 physical rolls while only 18
  rolls are initially entered on the operational card.
- Operators currently write the outstanding number, such as `2`, on the paper
  card and leave it on the noticeboard beside the machine.
- Extrusion has already ended when the final roll leaves the machine. Rewinding,
  later weighing, and pallet assembly do not occupy or block the extrusion
  machine.
- When the rewound rolls return, terminal operators weigh them, enter them,
  assemble the transportation pallet, and deliberately finish the card.
- Rewinding may merge or split film. Two sent rolls may return as one, and one
  sent roll may return as two.

## Chosen Design

Use one explicit waiting status plus two persistent card values:

- an informational count of rolls sent for rewinding; and
- a reference to the shift active when extrusion ended.

The internal waiting status is `awaiting_rewinding`.

The alternatives were rejected:

- A completed card plus a separate waiting flag would make the card appear
  simultaneously completed and unfinished.
- A separate rewinding-event ledger would add batch history and identity that
  the pilot neither needs nor uses.
- A mandatory rewinding question on every End action would complicate every
  normal order to protect against an occasional operator mistake.

## Bulgarian Terminology

- Header navigation button: `Изчакващи пренавиване`.
- Individual card status: `Изчаква пренавиване`.
- Selected-card secondary action: `Пренавиване`.
- Marked secondary action: `Пренавиване: N`.
- Rewinding dialog title: `Ролки за пренавиване`.
- Existing lifecycle action used for both transitions: `Приключи`.

## Approved Lifecycle

### Normal path

```text
running or paused --Приключи without a rewinding count--> completed --> archived
```

The existing normal End confirmation and completed-card behavior remain
unchanged.

### Rewinding path

```text
running or paused + positive rewinding count
        --Приключи / extrusion stops--> awaiting_rewinding
        --add, correct, or delete actual returned rolls--> awaiting_rewinding
        --Приключи / deliberate finalization--> completed --> archived
```

### Recording rewinding before End

- `Пренавиване` is available while the card is running or paused.
- It opens one small dialog for the informational sent-roll count.
- A positive whole number from `1` through `999` saves the marker.
- Blank or `0` clears the marker.
- Negative values, decimals, non-numeric values, and values above `999` are
  rejected without changing the saved value.
- Cancel closes the dialog without saving.
- A saved positive value changes the secondary action to the amber
  `Пренавиване: N` state.
- If the value is cleared before End, the existing normal End path applies.
- The count creates no roll placeholders or roll identities.

### Ending extrusion into the waiting state

When a running or paused card has a positive saved count, the existing
`Приключи` action and existing confirmation are used. This preserves the
current app rule that a paused card may be deliberately finished without being
resumed first. Confirming performs one complete operation:

- record `finished_at` as the real extrusion stop time;
- record the shift that is active at that stop as the final extrusion shift;
- close the active production timing segment when the card is running, or
  preserve the already closed timing ledger when the card is paused;
- remove the card from active machine work;
- preserve its machine assignment as production history;
- normalize the remaining active machine queue;
- change the status to `awaiting_rewinding`; and
- retain the informational count.

The transition requires production timing to have been started and the normal
terminal active-shift gate to be satisfied. It does **not** require:

- a current/default `Шпула` value;
- an existing roll entry;
- a gross weight;
- a net weight; or
- a pallet number.

This explicitly supports the edge case where every physical roll was ripped
and all roll weighing happens after rewinding.

The waiting card does not count as the machine's running card, does not block
the next queued card, and has no open production timing segment. Rewinding time
is not extrusion runtime.

After success, the terminal follows the current successful-finish navigation:
the same card remains selected, now in the waiting state, and a short success
message is shown. It does not automatically open the waiting pane.

### Working on a waiting card

- Operators open the card from `Изчакващи пренавиване`.
- `Пренавиване` remains editable while the card is waiting.
- Correcting the count changes only the informational value.
- Clearing it to blank or `0` does not remove the card from the waiting state.
- Once a card is waiting, only deliberate `Приключи` can move it to Produced
  Orders.
- Operators use the normal roll controls to add the actual returned rolls.
- The existing terminal material/batch and current roll-default corrections
  remain available while waiting, just as correction remains available on a
  produced card.
- Normal per-card sequential numbering continues.
- Operators may correct and delete individual rolls through the approved pencil
  interaction.
- The waiting card may temporarily contain zero rolls.
- Adding, editing, or deleting a roll never finalizes the card automatically.
- The sent count never decreases automatically and is never compared with the
  number of returned rolls.

### Deliberate finalization

When a waiting card is opened:

- Start and Pause are not shown because extrusion has ended.
- The familiar primary `Приключи` action remains.
- Selecting it opens the existing short End confirmation.
- No additional long explanation or separate finalization workflow is added.

On confirmation, the server requires:

- at least one roll with a gross weight;
- a valid saved `Шпула` value on every roll with gross weight;
- a correctly calculated net weight on every such roll; and
- no invalid gaps in the roll sequence.

Pallet assignment remains optional, as it is in the current completed-card
workflow. The sent count is informational and does not participate in
validation. A card marked with `2` may validly finish with one returned roll; a
card marked with `1` may validly finish with two returned rolls.

The current mixed-pallet confirmation is used consistently for every
`Приключи` action. When some entered gross rolls have pallet numbers and others
do not, the confirmation warns how many rolls lack a pallet for normal
completion, entry into the waiting state, and finalization from the waiting
state. If the current mixed-pallet rule does not apply, the standard short
confirmation is shown. Pallet assignment remains non-blocking in every case.

If validation fails, the card stays in `awaiting_rewinding` and the terminal
shows what is missing or invalid. If validation succeeds:

- status changes to the existing completed/produced state;
- production timing is not reopened or changed;
- `finished_at` remains the original extrusion stop;
- no finalization timestamp is recorded;
- the existing completed-card correction, print, and later archive behavior
  becomes available; and
- the terminal returns to its normal view without automatically opening
  Produced Orders.

## Timestamp And Sorting Rules

- `finished_at` always means the real extrusion stop time.
- Finalization does not create or overwrite a timestamp.
- The printed operational-card stop time uses `finished_at`.
- Produced Orders continue to sort newest `finished_at` first.
- `Изчакващи пренавиване` uses the same newest-first `finished_at` ordering.
- `updated_at` is not a substitute for a business timestamp.

## Shift Attribution

- Every card that reaches End after this feature records the shift active when
  extrusion ends, whether it follows the normal or rewinding path.
- That shift is the final extrusion shift—the shift that produced the final
  roll—even if earlier shifts performed most of the order.
- Every roll added after End is attributed to that final extrusion shift,
  including:
  - returned rolls added to a waiting card; and
  - a missing roll added directly to a produced card after the operator forgot
    to record rewinding.
- The later shift that weighs or types the roll does not receive production
  credit for it.
- A current shift must still be open to perform terminal production mutations;
  that operational gate does not change historical attribution.
- Older cards have no recorded final extrusion shift. A later roll on such a
  card inherits the chronologically latest shift already attached to one of the
  card's rolls. If none exists, attribution remains unknown rather than guessed.
- Shift summaries remain live calculations from the rolls currently attached to
  the shift. Adding a returned roll later increases the original final shift's
  roll and weight totals.

## Forgotten Marker Behavior

No special recovery workflow is added.

If an operator forgets to record rewinding and finishes normally:

- the card remains in Produced Orders;
- the operator opens it through the existing produced-card workflow;
- the missing rolls are added through the existing completed-card roll-entry
  capability;
- the card is not moved backward into `awaiting_rewinding`;
- its extrusion stop time is not rewritten; and
- the added rolls use the recorded final extrusion shift.

This is the accepted pilot recovery method. The app will not add a produced-to-
waiting reversal, special warning, or Admin recovery control.

## Rewinding Count Lifecycle

- Store one current informational sent-roll count per card.
- Do not create a rewinding batch/event table.
- The value may be corrected while running, paused, or waiting.
- Correcting or clearing it never changes status by itself.
- The value remains stored after finalization so entered production data is not
  silently discarded.
- After finalization it is not shown on the terminal, Admin, Produced Orders, or
  printed operational card and has no continuing workflow role.

## Waiting-Card Navigation

- Use three central header buttons in lifecycle order: `Чакащи поръчки`,
  `Изчакващи пренавиване`, and `Произведени поръчки`.
- Show a small badge at the button's bottom-right containing the number of cards
  in `awaiting_rewinding`.
- The badge counts cards, not sent or returned rolls.
- Hide the badge when the count is zero.
- The button opens a centered pane/modal rather than a side drawer.
- The pane shows cards across the terminal using the existing Produced Orders
  row presentation.
- Each row adds the informational sent-roll count, such as `2 ролки`.
- A cleared count is shown as `0 ролки` while the card remains waiting.
- Rows use the same newest-first order as Produced Orders.
- Selecting a row opens the normal card detail and approved roll panel.
- Waiting cards never appear in Produced Orders and are never printable.
- Empty, loading, and stale-refresh behavior should follow the existing terminal
  navigation patterns.

## Terminal And Admin Permissions

- Terminal operators record and correct the rewinding count.
- Terminal operators add/correct/delete returned rolls and perform finalization.
- Admin displays the individual status `Изчаква пренавиване` and the current
  count while the card is waiting.
- Admin retains its existing permitted production-data correction capabilities.
- Admin does not receive a finalization action for waiting cards.
- The waiting card itself cannot be cancelled, deleted, or archived.
  Cancellation means abandoning the entire production card and is not a way to
  clear a waiting state; this does not restrict the approved deletion of an
  individual roll while the card waits.
- After terminal finalization, the normal completed-card Admin behavior resumes.

## Approved Selected-Card UI

The selected-card roll area must follow the accepted design described below.

### Action hierarchy

1. Start, Pause, and End are the primary lifecycle actions at the top.
2. `Пренавиване` and `Смяна на ролка` are compact secondary controls beside the
   `Ролки` heading.
3. `Добави` is the primary local action for the new-roll fields.
4. Every saved roll has one compact pencil action at the right of its row.
5. Save, Cancel, and Delete appear only after a particular roll is selected.
6. The previous order-level roll-edit/delete overflow menu is removed.

Start, Pause, and End have equal visual width with enough internal padding for
`Приключи`; equal sizing must not clip or crowd the label.

### Rewinding dialog

- Selecting `Пренавиване` opens `Ролки за пренавиване`.
- The dialog contains one whole-number count field and Save/Cancel actions.
- Save uses the normal navy action treatment, not red destructive styling.
- Reopening shows the latest saved value.
- The input is labelled, keyboard operable, and constrained in both browser and
  backend validation.
- Escape/Cancel leaves the saved value unchanged and restores focus to the
  trigger.

### New-roll input presentation

These accepted changes are not unique to rewinding but are included in Task 11:

- Remove the border surrounding the complete new-roll input group.
- Use individual border-embedded labels:
  - `Ролка`
  - `Шпула`
  - `Палет`
- Keep the `Шпула` and pallet input boxes equal in size.
- Align the bottom of `Добави` with the input bottoms.
- Center the plus icon and text as one visual group.
- Preserve the existing terminal typography. `Ролка` and `Шпула` use the same
  font, size, weight, and line height.

### Roll table and per-roll correction

Show columns in this exact order:

1. `№`
2. `Бруто`
3. `Шпула`
4. `Нето`
5. `Палет`
6. compact pencil action

Additional rules:

- Do not show `кг` in weight headings.
- The first five information columns use equal tracks; the pencil remains a
  compact action column.
- Center the roll number within its full-width track.
- Gross, spool, and net values use one decimal place in the read-only table.
- Roll and pallet numbers remain whole integers.
- Only one roll editor is open at a time.
- The selected row exposes that roll's gross, `Шпула`, and pallet values.
- Net remains calculated and read-only.
- Changing a selected roll's `Шпула` recalculates only that roll's net.
- It does not change the current default or any other saved roll.
- Changing the current `Шпула` above the table affects only rolls added after
  the change; it never rewrites existing roll snapshots.
- Delete is inside the selected-roll interaction and requires explicit
  confirmation.
- The read-only table uses one decimal without destroying precision. Correction
  inputs load and preserve the exact stored value of up to two decimal places;
  opening and saving `1.25` unchanged must not turn it into `1.3`.

## Task 10 Roll-Change Placeholder

Task 11 must render the `Смяна на ролка` button in the exact approved secondary
position beside `Пренавиване`, even though its functionality belongs to Task 10.

For Task 11:

- the button is visually present and follows the approved hierarchy;
- it has no countdown, modal, persistence, machine-card indicator, reminder,
  multiple-track behavior, or click logic; and
- tests must prove that Task 11 did not accidentally include partial Task 10
  behavior.

Task 10 will attach the real behavior to this existing control in a later
session. Task 11 must not redesign or move it.

## Existing Roll Semantics To Preserve

The current app behavior was verified directly against `app/db.py`, the
terminal template, and focused tests:

- `cards.tare_weight` is the current/default `Шпула` for a future roll.
- `cards.current_pallet_number` is the current/default pallet for a future roll.
- Every `roll_entries` row stores its own `tare_weight` snapshot.
- Every `roll_entries` row stores its own `pallet_number` snapshot.
- The current `Шпула` and pallet inputs are one coordinated autosave unit: when
  either changes, the server validates and saves the submitted pair atomically.
- Adding a roll copies the submitted/current `Шпула` and pallet defaults into
  the new roll in the same transaction as gross weight, roll number, shift
  attribution, net calculation, and the card-version update.
- Changing the default later does not mutate existing roll snapshots or nets.
- Per-roll correction changes only the selected roll's gross, `Шпула`, pallet,
  and calculated net.

Task 11 must preserve this behavior exactly. It must not reinterpret `Шпула` as
one order-wide historical value.

## Backend And Data Invariants

- `awaiting_rewinding` is one explicit lifecycle status, not a derived
  combination of completed status and a flag.
- The rewinding count is `NULL` when absent and otherwise a whole integer from
  `1` through `999`; user input `0` or blank maps to `NULL`.
- The waiting status may coexist with a `NULL` count after the operator clears
  it. Status changes only through `Приключи`.
- Only running, paused, and waiting cards may change the count.
- End-to-wait is allowed from running or paused with a saved positive count.
- The End transition, final-shift capture, timing closure, status change, and
  queue normalization are one transaction.
- A waiting card is excluded from active-machine, produced, archived, cancelled,
  and printable status groups.
- A waiting card is terminal-visible, roll-editable, and extrusion-ended. It is
  not added to the active or production-complete status groups merely to reuse
  existing queries.
- No open timing segment may exist while waiting.
- Admin timing corrections treat a waiting card as extrusion-ended: it must
  retain at least one closed timing segment, cannot acquire an open segment,
  and keeps `finished_at` synchronized with its corrected closed timing ledger.
- Waiting roll changes use actual per-roll snapshots, normal numbering, and
  existing optimistic conflict checks.
- No rule compares the informational count with returned roll entries.
- Finalization is explicit, validates the complete roll ledger on the server,
  and changes only the status/version/update metadata.
- All rewinding-count, roll, status, and finalization writes use the existing
  card version. A stale page must require reload rather than overwrite newer
  production data.
- Repeated or stale End/finalization submissions cannot close timing twice,
  duplicate state transitions, or overwrite the original stop.
- Re-import updates imported/front-card fields only. It preserves waiting
  status, count, final extrusion shift, timing, rolls, per-roll spool snapshots,
  pallet data, recipe data, versions, and all other production data.
- Existing cards retain their statuses and history during migration. No old
  rewinding state, count, or final extrusion shift is inferred.
- The terminal polling signature includes waiting-card identity, status,
  version, count, and ordering data so waiting-pane and badge changes trigger
  the established reload-required behavior rather than silently remaining
  stale.

## Failure And Feedback Behavior

- Invalid count input leaves the previous value unchanged and displays a short
  Bulgarian message in the rewinding dialog.
- A failed End-to-wait operation leaves status, timing, final shift, machine
  queue, and count unchanged as one consistent state.
- A failed finalization leaves the card waiting and identifies missing or
  invalid roll data.
- A roll-entry or correction failure preserves all other roll values and keeps
  the relevant input/editor visible.
- Stale writes use the established reload-required conflict message.
- Successful mutations persist immediately and update the terminal polling
  signature/badge without requiring an unsafe partial client-side state.

## Accepted Visual Design

The user visually approved the standalone prototype on July 26, 2026 with the statement
`Excellent! This is the design.`

The standalone prototype was an implementation-time reference. Its disposable
source was removed after acceptance; the accepted design is now embodied in the
terminal template and Task 11 automated/live verification. This specification
defines the selected-card visual treatment and supersedes earlier reference-only
interactions where later business decisions differ:

- the centered waiting pane and header button were approved after the prototype;
- waiting-card finalization reuses `Приключи`;
- `Смяна на ролка` is present but inert in Task 11; and
- persistence, validation, state transitions, conflicts, and migration are
  server responsibilities.

Implementation preserved intervening terminal work while applying the accepted
design. The shipped Jinja/CSS embodies that treatment; the server owns
persistence, validation, conflicts, and state transitions. Do not recreate a
standalone companion as a current verification dependency.

## Acceptance Scenarios For The Implementation Plan

### Marker and count

- Saving `2` on a running, paused, or waiting card persists immediately,
  increments the card version, and renders `Пренавиване: 2` after reload.
- Cancel after typing another value preserves `2`.
- Blank or `0` clears the count.
- Clearing a waiting card leaves it waiting and its row shows `0 ролки`.
- Invalid and stale submissions preserve the previous value.

### End extrusion into waiting

- A running or paused card with a positive count enters `awaiting_rewinding`
  through the existing End confirmation.
- A running or paused card without a count follows the existing completed path.
- A card with no tare/default and no roll entries can enter waiting.
- A running card's timing segment closes exactly once at `finished_at`; a paused
  card remains closed and is not resumed or given artificial runtime.
- Its active shift is recorded as the final extrusion shift.
- Its machine becomes available and the remaining active queue is normalized.
- No pane opens automatically.
- The same waiting card remains selected after the successful redirect.
- The current mixed-pallet warning appears on End-to-wait when its existing
  assigned/unassigned-roll condition applies.

### Waiting work and finalization

- The centered pane badge counts cards, not rolls.
- Rows show the sent count and sort newest extrusion stop first.
- A card marked `2` may finish with one returned roll.
- A card marked `1` may finish with two returned rolls.
- Adding, editing, or deleting rolls never finalizes automatically.
- Waiting cards may temporarily have zero rolls.
- Finalization rejects zero rolls and incomplete/invalid per-roll spool/net data.
- Pallet remains optional.
- The current mixed-pallet warning also appears on waiting-card finalization
  when its existing condition applies.
- Successful finalization enables existing completed-card review and printing
  without changing `finished_at` or recording another timestamp.
- The rewinding count is hidden after completion.

### Shift behavior and forgotten marker

- Returned rolls are assigned to the recorded final extrusion shift rather than
  the later data-entry shift.
- A completed card that receives a forgotten missing roll uses the same recorded
  final shift and remains completed.
- Older cards fall back to their latest linked roll shift or unknown.
- Historical shift totals update from the added roll.

### Existing roll UI and precision

- The approved field labels, sizing, Add alignment, equal columns, header order,
  pencil interaction, and one-decimal read display match the accepted design.
- The coordinated `Шпула`/pallet defaults save and new-roll snapshot remain
  atomic after the visual refactor.
- Editing one roll's `Шпула` changes only that roll and its net.
- Changing the default affects only future rolls.
- Exact two-decimal stored values survive an unchanged correction save.
- `Смяна на ролка` is present in the approved position and performs no action.

### Safety and compatibility

- Waiting cards are not active, produced, archived, cancelled, or printable.
- Admin can view waiting information and correct permitted production data but
  cannot finalize, cancel, delete, or archive the waiting card.
- Re-import preserves all rewinding and production data.
- Migration preserves every accepted older database without guessed rewinding
  or final-shift values.
- The migration rebuilds or otherwise upgrades the existing `cards.status`
  constraint; adding only the Python constant is insufficient for an existing
  SQLite database.
- `README.md` and repository scope documentation describe this narrowly as
  extrusion-card return tracking, not management of the rewinding/slitting
  department or a shipping/pallet lifecycle.
- Stale/repeated submissions cannot partially mutate timing, queues, shifts,
  statuses, counts, or rolls.

## Verification Requirements

The implementation plan must provide backend/database tests, route/template
checks, migration fixtures, re-import preservation tests, and a live Playwright
workflow against a temporary SQLite database.

Browser verification must cover:

- the approved selected-card layout at 1920 by 768 and 1366 by 768;
- equal primary buttons and aligned new-roll controls;
- centered waiting pane, count badge, sorting, and row count;
- marker save/change/clear and waiting-state persistence;
- the all-rolls-away End transition;
- roll entry/correction/deletion and finalization;
- one-decimal display without stored-precision loss;
- the present but inert Task 10 button; and
- console/page errors, clipping, overlap, and horizontal overflow.

Testing must not mutate the runtime database. The focused checks, full Python
suite, `git diff --check`, migration assessment, and manual browser workflow
must pass before completion can be claimed.

## Migration Direction

Persistent structure and status meaning changed. The implemented feature was
therefore assessed under `v2-files/AGENTS.md` and uses schema-only M004,
`rewinding_return_workflow`.

The approved data rule for existing rows is deterministic:

- keep every existing status and production value unchanged;
- add no historical rewinding status or count;
- leave historical final extrusion shift unknown; and
- use the existing latest-linked-roll fallback only when a future late roll is
  actually added to an older card.

M004 rebuilds `cards` to add the accepted status constraint and nullable
rewinding/final-shift columns with their constraints and foreign key. Startup
validation, rollback guarantees, and the synthetic fixture matrix are recorded
in `v2-files/AGENTS.md` and the implementation note. No runtime or production
database was opened or changed during implementation or verification.

## Out Of Scope

- Tracking the identity, lineage, dimensions, defect, or physical location of a
  ripped roll while it is away.
- Requiring sent and returned quantities to match.
- Managing the rewinding/setting department's timing or work queue.
- Multiple rewinding batches or event history per card.
- A produced-to-waiting recovery transition for a forgotten marker.
- Displaying or printing the rewinding count after finalization.
- A finalization timestamp.
- Waiting-card cancellation, deletion, archive, or Admin finalization.
- Inventory consumption, costing, waste, or quality-control expansion.
- Customer shipping or package/pallet lifecycle beyond existing pallet entry.
- Users, roles, login, or permission expansion.
- Task 10 countdown, reminder, multiple-track, persistence, or machine-card
  behavior. Only its approved button is rendered by Task 11.

## Implementation Plan

The business workflow, lifecycle, terminology, navigation, UI hierarchy,
validation, shift attribution, forgotten-marker behavior, roll semantics,
permissions, timestamps, sorting, print eligibility, migration direction, and
Task 10 boundary are decided.

The completed backend-first implementation plan is:

- `docs/superpowers/plans/2026-07-26-rewinding-return-workflow.md`

Implementation followed that reviewed plan; any later behavior change requires
a separately approved specification update rather than silent drift here.
