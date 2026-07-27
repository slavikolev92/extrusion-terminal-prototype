# Rewinding Return Workflow

This note records the shipped Task 11 behavior for extrusion rolls that leave
for rewinding/setting before they can be weighed. It is intentionally narrower
than a rewinding-department workflow: the pilot records an extrusion-card
marker, waits for the physical rolls to return, accepts their actual weights,
and then completes the existing extrusion card.

## Business Reason And Lifecycle

A ripped physical roll may leave extrusion before it is weighed. Extrusion has
still ended, and the machine must become available, but the operational card is
not ready for Produced Orders or printing. The explicit waiting state prevents
the card from being misleadingly active or prematurely complete.

```text
imported -> pending -> running <-> paused
                            |          |
                            +----------+
                                 |
             Приключи without marker -> completed -> archived
                                 |
             Приключи with marker -> awaiting_rewinding
                                      | add/correct/delete returned rolls
                                      +-> awaiting_rewinding
                                      |
                         deliberate Приключи -> completed -> archived

pending/running/paused -> cancelled -> pending remains the separate Admin path;
awaiting_rewinding cannot enter cancellation, archive, planning, or timing paths.
```

`awaiting_rewinding` is neither active nor completed. It is excluded from the
machine queue and running-card constraint, so the machine can start its next
card immediately. It is also excluded from Produced Orders, print, archive,
cancel, delete, start, pause, resume, and queue sequencing. The historical
machine assignment remains on the card.

## Marker And Returned-Roll Semantics

`cards.rewinding_roll_count` is one current informational count. While a card is
running, paused, or waiting, `Пренавиване` accepts a whole integer from `1`
through `999`; blank or any all-zero value clears it to `NULL`. Invalid text,
negative values, decimals, and values over `999` leave the prior value
unchanged. Every save uses the card version and the active-shift terminal gate.

The marker creates no roll placeholders, IDs, batches, or lineage. It is never
decremented automatically and is never compared with the number of returned
rolls: one sent roll may become two, or two may become one. Clearing a marker
after extrusion ends does not leave the waiting state. Only the explicit
`Приключи` action finalizes a waiting card. The stored marker is preserved after
completion but hidden from terminal, Admin, Produced Orders, and print.

## Timing, Queue, And Finalization

Ending marked extrusion is one `BEGIN IMMEDIATE` transaction. It validates the
loaded version and active shift, records the real extrusion stop in
`finished_at`, records the final extrusion shift, closes the one open timing
segment when the card is running, changes status, and normalizes the remaining
active queue. A paused card already has a closed timing ledger, so End preserves
its segments exactly. Entry into waiting requires timing to have started but
does not require a default spool/tare, a roll, gross/net weight, or a pallet.

Waiting-card finalization requires at least one gross roll, a valid saved tare
and exactly recalculated net for every gross roll, and no filled roll after an
empty roll gap. It changes only status, card version, and update metadata.
`finished_at`, `first_started_at`, all timing segments, the marker, final shift,
machine history, and roll data remain unchanged. Admin timing correction treats
waiting as extrusion-ended: at least one closed segment must remain, no open
segment is allowed, and `finished_at` is recalculated from the corrected closed
ledger.

## Shift Attribution

Every normal or rewinding-path End records
`cards.final_extrusion_shift_occurrence_id` from the shift active when extrusion
stopped. Any later roll added to an awaiting, completed, or archived card uses
that final extrusion shift, not the shift whose operator later weighs or types
the roll. Shift summaries are live roll queries, so returned rolls increase the
original final shift's counts and weights.

Legacy cards deliberately have no inferred final shift. A late roll on such a
card falls back to the chronologically latest shift already linked to one of
that card's rolls. If no linked shift exists, attribution remains `NULL` rather
than being guessed. The terminal still requires a currently open shift as an
operational gate for the write; that gate does not change historical ownership.

## Roll, Default, Material, And Correction Rules

The established roll snapshot model remains intact:

- `cards.tare_weight` and `cards.current_pallet_number` are current defaults for
  future rolls. Their coordinated terminal form validates and saves the pair
  atomically when both are submitted.
- Each new roll snapshots its own tare and optional pallet in the same
  transaction as gross, net, sequential roll number, shift attribution, and
  card version.
- Changing a default never rewrites existing roll snapshots. Per-roll pencil
  correction changes only that roll's gross, tare, calculated net, and pallet;
  exact stored precision of up to two decimal places is preserved even though
  the read-only table displays one decimal.
- Roll deletion is explicit and renumbers later rows contiguously. A waiting
  card may temporarily have zero rolls; completed/archived cards must preserve
  at least one gross roll.
- Existing terminal material and batch corrections and Admin's permitted roll,
  material, default, and closed-timing corrections remain available while the
  card waits. Every mutation uses optimistic version checks; stale marker,
  finish, default, roll, and correction submissions require reload and cannot
  partially overwrite data.
- Re-import changes imported/front-card fields only. It preserves waiting
  status, marker, final shift, timing, rolls and shift links, tare/pallet
  defaults and snapshots, recipe/material actuals, assignment, version, and all
  other production data.

Pallet assignment remains optional. The existing mixed-pallet confirmation is
used consistently for normal completion, entry into waiting, and waiting
finalization when saved gross rolls mix numbered and blank pallets. The warning
states how many gross rolls have no pallet but never blocks the server action.

## Recovery When The Marker Was Forgotten

No produced-to-waiting reversal exists. If an operator finishes normally and
later discovers a missing returned roll, they open the card through
`Произведени поръчки` and use the existing completed-card roll entry. The card
remains completed, `finished_at` remains the original extrusion stop, and the
new roll uses the recorded final extrusion shift or the legacy fallback above.

## Operator And Admin UI

The three centered header actions are `Чакащи поръчки`, `Изчакващи
пренавиване`, and `Произведени поръчки`. The waiting button's bottom-right badge
counts cards, not rolls, and disappears at zero. Its centered pane sorts by
newest `finished_at`, uses the Produced Orders row presentation, and adds the
current marker label such as `2 ролки` or `0 ролки`.

On running, paused, and waiting cards, the compact secondary control reads
`Пренавиване` or `Пренавиване: N` and opens `Ролки за пренавиване`. Waiting cards
show only the primary lifecycle action `Приключи`; Start and Pause are absent.
`Смяна на ролка` remains visibly present beside the marker but intentionally has
no persistence, modal, countdown, reminder, or click behavior in Task 11.

The selected roll area follows the fixed approved prototype: equal lifecycle
controls; border-embedded `Ролка`, `Шпула`, and `Палет` inputs; aligned `Добави`;
columns `№`, `Бруто`, `Шпула`, `Нето`, `Палет`, then one pencil action; one open
row editor; and Save/Cancel/Delete only for the selected row. Admin displays
`Изчаква пренавиване` and the marker only while waiting, retains permitted
production corrections, and exposes no waiting-card finalization, cancel,
delete, archive, or print shortcut.

The visually accepted immutable reference is
`v2-files/prototypes/rewinding-roll-controls/`. It was approved on July 26, 2026
as “Excellent! This is the design.” The shipped implementation preserves the
prototype's hierarchy and roll-table treatment while applying the later
approved centered waiting pane and server-owned workflow rules. The prototype
was not regenerated or modified during implementation.

## M004 Schema And Recovery

Schema-only migration M004, `rewinding_return_workflow`, rebuilds `cards` so
the canonical status constraint accepts `awaiting_rewinding` and adds:

```text
cards.rewinding_roll_count INTEGER NULL
    CHECK integer storage and value between 1 and 999
cards.final_extrusion_shift_occurrence_id INTEGER NULL
    REFERENCES shift_occurrences(id) ON DELETE RESTRICT
```

Both columns are nullable and defaultless. The rebuild copies every shared
source column, preserves legacy extension columns with safe declared types,
preserves valid partial values and the `cards` autoincrement high-water mark,
and recreates the card indexes. Existing rows receive no inferred status,
marker, or final shift, and no existing value is transformed. Startup validates
column metadata, accepted/rejected count and status values, the exact foreign
key, persisted counts and references, canonical statuses, integrity, and
foreign-key consistency. Missing or malformed recorded/partial schemas fail
instead of being recorded as migrated.

The migration runner temporarily disables foreign-key enforcement for the
SQLite table rebuild, owns one transaction around apply plus validation, and
uses its migration savepoint. Schema, copied data, recreated indexes, and the
M004 record commit together; any apply or validation failure rolls all of them
back, and foreign-key enforcement is restored. An injected failure after the
copy proved the original schema/data and M003 history remain intact. A separate
finish-path trace injected failure after timing close but before status update
and proved the open segment, card, final shift, and queue all rolled back.

No runtime or production database was opened or mutated. M004 itself does not
need a production snapshot because its rule is schema-only and changes no
existing value. The application and M004 must deploy together after a
SQLite-safe backup. Production rollback is restoration of that verified backup
plus the matching prior application revision, not reverse SQL. The unresolved
M001 legacy-data profile and final release-candidate rehearsal remain separate
deployment gates.

## Verification Record

All verification on July 27, 2026 used temporary databases. Syntax/import and
the exact focused matrix ran as follows:

```bash
source .venv/bin/activate
python -m compileall -q app scripts tests
python -m pytest \
  tests/test_migrations.py \
  tests/test_rewinding_workflow.py \
  tests/test_finish_cancel_history.py \
  tests/test_roll_entry.py \
  tests/test_terminal_sync.py \
  tests/test_terminal_v8_render.py \
  tests/test_admin_production_corrections.py \
  tests/test_admin_card_detail_redesign.py \
  tests/test_print_output.py \
  tests/test_baseline.py \
  tests/test_shift_routes.py \
  tests/test_production_timing.py \
  tests/test_rewinding_ui_script_safety.py \
  -q
# compileall exited 0; 611 passed in 48.39s

python -m pytest tests/test_migrations.py -q
# 42 passed in 3.18s

python -m pytest -q
# 814 passed in 61.92s
```

The unchanged accepted prototype verifier ran against a local static server:

```bash
PROTOTYPE_URL=http://127.0.0.1:8765/prototype.html \
node v2-files/prototypes/rewinding-roll-controls/verify-prototype.mjs
# rewinding prototype checks passed
```

The guarded live fixture and app used only the required ignored database:

```bash
source .venv/bin/activate
python scripts/create_rewinding_fixture.py \
  --db-path .test-runtime/rewinding-ui.sqlite3 \
  --output .test-runtime/rewinding-ui.json

EXTRUSION_DB_PATH=.test-runtime/rewinding-ui.sqlite3 \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011

BASE_URL=http://127.0.0.1:8011 \
FIXTURE_JSON=.test-runtime/rewinding-ui.json \
ARTIFACT_DIR=artifacts/ui-checks/rewinding-return-workflow \
node scripts/verify_rewinding_ui.mjs
# Rewinding return workflow verification passed.
```

The guarded verifier passed at `1920x768` and `1366x768`, reported no document
or roll-panel overflow, and recorded empty console-error and page-error lists.
It exercised the centered pane and badge, marker save/clear/invalid/cancel/stale
paths, running and paused End-to-wait, mixed-pallet confirmations, immediate
machine reuse at both viewports, zero-roll finalization failure, returned-roll
entry and correction, timing/stop preservation, Produced Orders transition,
precision display, per-row editing, dirty-navigation guards, and the inert
roll-change control.

The adversarial workflow selection passed 53 tests in 7.01s, covering every
approved/forbidden transition; stale marker, finish, default, roll, and
correction writes; queue normalization; final-shift and legacy attribution;
re-import preservation; print/archive/cancel exclusion; all mixed-pallet finish
contexts; and pallet/print regression checks. The injected transaction trace at
`.test-runtime/task10-adversarial.sqlite3` reported card, open timing, and queue
state unchanged after `injected status failure`.

Ignored browser evidence is under:

- `artifacts/ui-checks/rewinding-ui-prototype/`
- `artifacts/ui-checks/rewinding-return-workflow/verification-summary.json`
- `artifacts/ui-checks/rewinding-return-workflow/rewinding-1920x768-full.png`
- `artifacts/ui-checks/rewinding-return-workflow/rewinding-1366x768-full.png`
- `artifacts/ui-checks/rewinding-return-workflow/waiting-pane.png`
- `artifacts/ui-checks/rewinding-return-workflow/marker-dialog.png`
- `artifacts/ui-checks/rewinding-return-workflow/waiting-detail.png`
- `artifacts/ui-checks/rewinding-return-workflow/row-edit.png`
- `artifacts/ui-checks/rewinding-return-workflow/final-produced-row.png`

All seven live screenshots were re-opened at original resolution. Both full
layouts have readable unclipped controls and even roll columns; the waiting
pane is centered and ordered; the validation dialog, empty waiting card,
selected-row editor, and Produced Orders transition are visually coherent. No
prototype, runtime database, customer data, or production artifact is tracked
by this documentation change.
