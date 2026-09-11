# Physical Pallet Weight

Date: 2026-09-10

Status: source-complete, verified, and accepted on 2026-09-11; production
deployment remains separately gated

This note records the implemented physical transport-pallet-weight slice. A
physical pallet weight is distinct from roll-core tare (`Шпула, кг`): roll
gross weight includes the roll core and excludes the transport pallet. This
feature remains scoped to one numbered pallet within one extrusion operational
card. It does not create warehouse pallet identity, capacity, shipping,
barcode, label, inventory, or cross-card behavior.

M007/M008 are source-complete but undeployed pending a separately approved
production maintenance window. No production database or production backup was
opened, migrated, or changed during implementation or acceptance verification.

## Persistent Schema And Ownership

The ordered migration registry now ends with M008,
`physical_pallet_weight_hundredths`. Startup applies this canonical table through the
migration runner rather than adding it to the base schema outside the runner:

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

The composite primary key permits one latest value per card and numbered
pallet while isolating the same pallet number on different cards. Deleting a
card cascades to its weights. `weight_hundredths` stores exact hundredths of a
kilogram: `1250` means `12.50 kg`; valid stored values are `1..10000`. Absence is represented
only by absence of a row. Zero is neither a stored weight nor a missing-value
sentinel. SQLite may normalize numeric text such as `"10"` through INTEGER
affinity before the `typeof` check; strict submitted-text syntax is enforced by
the application parser.

A weight belongs only to a numbered pallet currently used by at least one
saved gross roll on the same card. `Без палет` and
`cards.current_pallet_number` never own weights. The current/default pallet
number for future rolls does not create a summary row or weight record.
Re-import does not touch `card_pallet_weights`; the values are production data,
not imported order data.

M007 creates and validates the final hundredths table for production, where
this feature has not been deployed. M008 upgrades an exact earlier unshipped
tenths-based M007 development table by multiplying each stored value by ten,
preserving keys and timestamps. It validates and makes no data change when
M007 already created the final schema. The caller-owned transaction and
migration savepoint commit each migration and its record together. A malformed
look-alike is rejected rather than accepted or replaced.

## Input, Form, And Validation Contract

Each numbered-pallet field accepts leading/trailing whitespace around:

- blank, which clears the target weight;
- ASCII digits, such as `12`, normalized after save to `12.00`;
- ASCII digits with exactly one `.` or `,` fractional separator and one or two
  fractional digits, such as `12.5`, `12,5`, or `12.55`; and
- positive values from `0.01 kg` through `100.00 kg` inclusive.

The Python and JavaScript parsers implement the same grammar:
`-?[0-9]+(?:[.,][0-9]{1,2})?`. A leading minus is reported as below the
minimum; other signed forms remain invalid syntax. They reject zero, `.5`,
scientific notation, non-finite/text values, embedded whitespace, multiple
separators, more than two fractional digits, and raw values above `100.00`.
Accepted values are stored exactly as integer hundredths; for example,
`10.35` remains `10.35` and `12.5` normalizes to `12.50`. The backend does not call `float()`; the client uses only
bounded integers for immediate validation and performs no gross or total
arithmetic. Oversized digit strings are rejected as over-maximum without
passing an unbounded integer string to `int()`.

The two save routes accept exactly one `loaded_version` field and exactly one
`pallet_weight` field; duplicate, missing, or unexpected fields are rejected.
The path pallet must be an integer from `1` through `999` and must still have a
gross roll on that card when the write transaction checks it.

Errors preserve the submitted text and identify the pallet where applicable.
Ordinary validation or permission failures return HTTP 422 with `ok: false`,
`messages`, `field_errors`, `submitted_weight`, and
`reload_required: false`. A stale loaded version returns HTTP 409 and
`reload_required: true`. A successful JSON response returns the new card
version, path pallet, normalized string (or `""` for clear), authoritative
affected row, authoritative total, weight state, messages, and
`reload_required: false`. Because one successful field save increments the
parent card exactly once, the client accepts a success response only when its
version is exactly the submitted version plus one; a larger or otherwise
malformed jump fails closed. Display values remain strings; no `Decimal` is
serialized through a float.

## Shared Summary And Calculations

`app/pallet_summary.py:build_pallet_summary()` is the common calculation and
validation owner used by terminal, Admin, Finish Review, and print. It consumes
all current roll rows plus the per-card integer-hundredths mapping. Only rolls with
a saved gross weight participate. It validates pallet numbers, finite
nonnegative gross/core/net values, and the exact stored invariant
`net_weight = gross_weight - tare_weight`. A saved weight for a numbered pallet
with no participating gross roll is an orphan and raises
`PalletSummaryDataError`; adapters fail soft for display, but finish and print
remain blocked.

The former terminal-only `build_terminal_pallet_summary()` compatibility
adapter and its fabricated `Decimal("0")` / `"0.0"` physical-weight fields have
been removed. Selected-card context and pre-route structural validation call
the shared builder with both the fetched roll rows and authoritative
`pallet_weights` mapping. Their narrow fail-soft fallback retains the shared
summary shape while marking the state as an error, so the terminal remains
usable without creating a second calculation contract.

For each numbered pallet:

- `Брой ролки` = count of participating gross rolls assigned to that number;
- `Бруто без палет, кг` = sum of their saved roll gross weights;
- `Тегло палет, кг` = `weight_hundredths / 100`, when saved;
- `Бруто с палет, кг` = gross without pallet + physical pallet weight, only
  when that row has a saved pallet weight; and
- `Нето, кг` = sum of the rolls' existing validated net weights. Physical
  pallet weight never changes film net weight.

The common six-column order is:

1. `Палет №`
2. `Брой ролки`
3. `Бруто без палет, кг`
4. `Тегло палет, кг`
5. `Бруто с палет, кг`
6. `Нето, кг`

Numbered pallets sort numerically. A participating `Без палет` group follows
all numbered rows. Gross-without-pallet and net values retain one decimal;
physical pallet weights and gross-with-pallet values use exactly two decimals.
All use a decimal point. A missing row weight displays `-` for both `Тегло палет, кг`
and that row's `Бруто с палет, кг`; no physical weight is invented as `0.0`.

The `Общо` row always totals roll count, gross without pallet, and net across
the complete underlying record set. It shows total pallet weight and total
gross with pallet only in the complete state. Those two cells are `-` in the
none and partial states. When present, total pallet weight is the sum of all
used numbered-pallet weights and total gross with pallet is total roll gross
plus total pallet weight.

The presentation state is `empty` when no saved gross roll participates and
`ready` otherwise. Physical-weight state is independent:

- `none`: no physical pallet-weight row exists for the card;
- `complete`: every participating gross roll has a numbered pallet and every
  used numbered pallet has one weight; and
- `partial`: at least one weight exists, but a used numbered pallet is missing
  its weight and/or one or more gross rolls remain in `Без палет`.

## State And Completion Rules

No weights is a valid opt-out state. Once any physical weight is saved, final
completion requires the complete state; operators may instead clear all
weights to return to the valid none state. There is no bypass for a partial
state. Missing numbered pallets are reported in numeric order and the number
of unassigned gross rolls is reported separately.

| Transition or boundary | `none` | `partial` | `complete` | orphan/inconsistent |
| --- | --- | --- | --- | --- |
| `running`/`paused` to `completed` | allowed, subject to existing finish rules | blocked | allowed | blocked for repair/reload |
| `running`/`paused` to `awaiting_rewinding` | allowed | allowed with nonblocking warning | allowed | blocked for repair/reload |
| `awaiting_rewinding` to `completed` | allowed, subject to existing finalization rules | blocked | allowed | blocked for repair/reload |
| completed/archived print | allowed | blocked | allowed | blocked for repair/reload |

Every finish transaction constructs and structurally validates the shared
summary inside the same `BEGIN IMMEDIATE` transaction as the lifecycle change.
Entry into waiting skips only final completeness; it never skips structural
validation. Normal completion and waiting finalization still require existing
timing, roll-core tare/net, at-least-one-gross-roll, and gap-free roll-sequence
rules. Entry into waiting may still occur without tare or rolls when the
existing rewinding marker permits it. Every finish variant retains the active
shift gate. That gate is enforced inside the shared finish transaction for
both public database services, including direct waiting-card finalization when
the caller did not perform the route-level precheck.

When no weights exist, the established mixed numbered/unassigned pallet
warning remains nonblocking. When any weight exists, partial completeness is
the stronger rule. Completed and archived cards can temporarily become partial
while one-at-a-time corrections are in progress; print remains blocked until
the set is complete or all weights are cleared.

## Persistence, Atomicity, And Cleanup

Each pallet field save is independent and starts `BEGIN IMMEDIATE`. In one
transaction it checks the active shift when required, loaded card version,
permitted status, path pallet range, continued pallet use, and submitted text;
then it upserts or deletes only the target row, increments the parent card
version and `updated_at` exactly once, and builds the authoritative response
summary before commit. Upsert preserves `created_at` and updates only
`weight_hundredths` plus the weight row's `updated_at`. A failed validation, stale
update, or summary-integrity check leaves both the weight rows and parent card
version unchanged.

If a roll mutation leaves no gross roll assigned to a weighted numbered
pallet, that weight is deleted in the same transaction. Cleanup runs after the
final roll mutations in all paths that can orphan a value:

- `update_roll_weight()` (including the gross-only wrapper and per-roll gross,
  tare, or pallet correction);
- `update_terminal_roll_corrections()`;
- `delete_roll_entry()`; and
- `_update_admin_roll_ledger()` after its complete multi-row mutation.

Deleting one of several participating rolls retains the weight while another
gross roll still uses that pallet. Clearing the last gross value, deleting the
last gross roll, or reassigning it removes the old weight. Removed pallet
numbers are sorted and included in the successful mutation message. Cleanup
does not add another card-version increment. The primary Admin save-all path
preserves this cleanup notice from the lower-level roll-ledger result while
suppressing only the redundant generic roll-save message; the notice is
returned only after the complete Admin transaction succeeds.

## Routes And Editable Surfaces

The relevant existing page and read routes are:

- `GET /terminal` and `GET /terminal/cards/{card_id}` for the workstation;
- `GET /terminal/snapshot` for polling and post-autosave reconciliation;
- `GET /admin/cards/{card_id}` for shift-manager correction; and
- `GET /cards/{card_id}/print` for the existing completed/archived operational
  card print.

The new field-save routes are:

- `POST /terminal/cards/{card_id}/pallet-weights/{pallet_number}`; and
- `POST /admin/cards/{card_id}/pallet-weights/{pallet_number}`.

The terminal route permits `pending`, `running`, `paused`,
`awaiting_rewinding`, and `completed` cards and requires an active shift. The
Admin route permits only `completed` and `archived` cards and does not require
an active shift. Both use the same strict form and response adapter but
separate database-service permission sets.

The shared `Обобщение по палети` modal is available through `Палети`. Each
numbered row always has one restrained `inputmode="decimal"` input; blank
means no saved weight. `Без палет` never has an input. Empty cards show `Няма
въведени ролки.`; all-unassigned cards retain the read-only row and explain
that numbered assignment is required before entering a physical weight.

The modal has a semantic six-column table, narrow pallet-number column, five
equal remaining columns, tabular numerals, a vertically scrolling body, sticky
heading and total, and a reachable fixed footer. The ordinary footer action is
only `Затвори`; the icon close, footer close, Escape, and backdrop all use the
same save-aware dismissal. Focus is trapped, the background is inert, and
ordinary close returns focus to its trigger. The hidden in-modal `Презареди`
action becomes keyboard reachable only after fatal stale or uncertain-commit
recovery.

On Admin, the modal is rendered outside the outer card form. It does not open
while that form has unsaved changes; the manager must first save the form or
reload to discard it. This prevents the summary from targeting a pallet set
that exists only in unsaved roll edits. Pallet correction remains separate
from the Admin roll-ledger submission.

## Autosave And Stale-State Contract

A changed input saves on Enter or blur, including a blur directly into another
weight field. The client state machine is `clean -> dirty -> queued -> active
-> clean|failed`. It freezes the raw queued value, protects a queued/active
field from duplicate submission, keeps an Enter-submitted focused field
read-only rather than disabled, and serializes all fields through one queue.
Each task reads the newest successfully returned card version only when it
reaches the queue head.

A successful response normalizes the input and replaces the affected
gross-with-pallet value, total values, and weight state without moving or
closing the modal. It updates loaded-version inputs only for forms belonging to
the same card and publishes the exact old/new version event. The response is
accepted only for an exact `old_version + 1` increment. A client-side parse
error or HTTP 422 validation error is nonfatal: the typed text remains visible,
the failing field is refocused while the modal remains open, and later queued
fields may continue against the unchanged version. A stale HTTP 409, network
failure, or malformed response creates one controller-wide fatal lock: typed
values remain visible, fields freeze, the reload action receives focus, and no
later queued pallet POST is sent against uncertain state.

Dismissal first freezes and queues any focused valid dirty draft, then waits for
the relevant queue generation and terminal reconciliation. It closes
automatically after success. Explicit X/footer/Escape/backdrop dismissal
discards an invalid unsaved draft and restores the last authoritative value.
Stale, network, or malformed-response failures remain clearly marked and
reload-protected, but explicit dismissal is still allowed so the modal cannot
trap the operator.

On `/terminal`, polling is deferred while the autosave queue is active. The
controller captures the complete pre-queue structured snapshot and performs
one fresh `GET /terminal/snapshot` when the queue becomes idle. Silent
`accept-local` is allowed only when every difference is the selected card's
exact final returned version and its consistent `updated_at` occurrences.
Changes to shift signature, active/waiting membership or order, any other card,
selected-card lifecycle/queue data, selected-card version beyond the returned
version, or malformed/missing snapshot data trigger the existing stale/reload
treatment. Only after `accept-local` does the terminal adopt the new snapshot
and derived signatures. A clean polling takeover may close the modal; a dirty,
queued, active, or failed draft prevents silent dismissal and remains frozen
for reload.

## Finish Review Freshness And Reconciliation

The feature uses these existing completion routes:

- `POST /terminal/cards/{card_id}/finish-review` for every fresh open;
- `POST /terminal/cards/{card_id}/finish-review/preview` after active timing
  edits; and
- `POST /terminal/cards/{card_id}/finish` for the final confirmed transition.

Every Finish Review open posts the current loaded version and obtains a new
server-authoritative snapshot before the dialog becomes visible. One
`BEGIN IMMEDIATE` read transaction validates version and active shift, derives
mode, loads all roll and weight rows, validates their structure, and combines
the full six-column summary, totals, lifecycle messages, timing display, and
`can_confirm`. The client validates the complete payload and replaces rows,
totals, messages, warning, version, timing display, and confirmation state as
one review update. It never reuses page-load pallet values as confirmation
authority and never calculates pallet totals in JavaScript.

The modes are `complete`, `enter_rewinding`, and `finalize_rewinding`. Active
running/paused modes retain the authenticated, process-local timing-review
token and editable timing draft. Applying a timing edit obtains another
same-version authoritative review; final confirmation applies the reviewed
ledger and lifecycle change atomically. Waiting finalization is tokenless,
uses stored closed timing read-only, and exposes no timing edit action. Its
successful transaction changes lifecycle/version/update metadata only; it does
not mutate timing or overwrite `finished_at`.

Partial weights disable confirmation in `complete` and
`finalize_rewinding`. They remain a visible yellow warning with confirmation
enabled in `enter_rewinding`. The final database transaction re-runs structural
and, where applicable, completeness validation; the browser's `can_confirm`
value is never trusted as the enforcement boundary.

Waiting-card refresh failures remain visible rather than leaving a disabled,
hidden dead end. A structural HTTP 422 opens the review in a visible,
nonconfirming repair state with the server's actionable messages and without a
reload requirement. Stale HTTP 409, malformed JSON or payload, and network
failures open a visible fatal locked state, keep the background inert, disable
ordinary dismissal, and expose keyboard access to `Презареди`. These recovery
paths never mutate the waiting card or its read-only timing record.

## Operational-Card Print Contract

The existing print route remains Admin/shift-manager-only in workflow and
continues to accept only `completed` and `archived` cards. A partial or orphaned
weight set blocks print with an actionable correction message. A no-weight set
prints valid numbered pallet rows with `-` for pallet weight and gross with
pallet. An all-unassigned card omits the transport-pallet table because it has
no numbered transport pallet. Mixed rows retain numeric order followed by
`Без палет` when print is otherwise ready.

The back page now uses one six-column table across the 109 mm middle/right
summary area while the existing six-row production summary remains in the
63 mm left area. Page 2 has eight measured body-row slots including `Общо`, so
its maximum is seven pallet rows plus the total. If eight or more pallet rows
exist, page 2 omits the pallet table completely and the full list begins on an
overflow page.

Each overflow page has 47 measured body-row slots, again including `Общо` on
the final page. Thus one overflow page can hold 46 pallet rows plus the total.
Overflow pages repeat the six headings and order context. The `Общо` row is
printed exactly once, after the final pallet row, and consumes one slot. If
ordinary chunking would put `Общо` alone on a new page, the last pallet row is
moved with it. The 47-row data case therefore prints 46 pallet rows on the
first overflow page and one pallet row plus `Общо` on the second.

Browser/PDF measurement rejected the proposed 48-slot overflow capacity: the
table bottom exceeded the page bottom by about 9.86 px. At 47 slots, the
46-row-plus-total boundary ended at 3358.515625 px against a 3367.546875 px
page bottom, leaving 9.03125 px. The renderer retained readable headings and
one-decimal cells rather than shrinking type to keep 48 slots.

The deterministic rendered matrix was:

| Scenario | Pallet rows | PDF pages | `Общо` placement |
| --- | ---: | ---: | --- |
| `no_weight` | 2 | 2 | page 2 |
| `page2_boundary` | 7 | 2 | page 2 |
| `first_overflow` | 8 | 3 | overflow 1 |
| `overflow_boundary` | 46 | 3 | overflow 1 |
| `orphan_total` | 47 | 4 | overflow 2 |

All 14 rasterized PDF pages were inspected at 1192x1686. They reported A4
595.92x842.88 points, one `Общо`, repeated readable headings, correct
page-2/overflow placement, and no clipped row or total-only page. This digital
render evidence does not replace a physical-printer test. A physical-printer
rehearsal remains a pre-production `GO` gate.

## Verification Record

Before adversarial review, Task 9 ran this focused baseline on 2026-09-10:

```bash
source .venv/bin/activate
python -m compileall -q app tests
python -m pytest tests/test_migrations.py tests/test_physical_pallet_weights.py tests/test_terminal_pallet_summary.py tests/test_roll_entry.py tests/test_admin_card_detail_redesign.py tests/test_rewinding_workflow.py tests/test_terminal_timing_correction.py tests/test_order_finish_review_ui_script_safety.py tests/test_print_output.py tests/test_print_template_fixture_script.py tests/test_terminal_pallet_summary_scripts.py -vv
node --test tests/js/*.test.mjs
git diff --check
```

Result at that pre-review checkpoint: compile exited 0; 721/721 focused Python
tests passed; 64/64 JavaScript tests passed; `git diff --check` exited 0.

It then ran this complete pre-review baseline:

```bash
source .venv/bin/activate
python -m pytest
node --test tests/js/*.test.mjs
git diff --check
```

Result at that pre-review checkpoint: 1501/1501 Python tests passed in 256.82
seconds; 64/64 JavaScript tests passed; `git diff --check` exited 0.

Three independent reviewers then completed the bounded Task 9 adversarial
review. Across their reports there were 0 Critical, 5 distinct Important, and
3 Minor findings. The Important findings covered the Admin cleanup notice,
direct waiting-finalization shift enforcement, visible waiting-review failure
recovery, removal of the legacy `0.0` adapter, and invalid-input refocus. The
Minor findings covered direct M007 constraint tests, authoritative-only fixture
eligibility metadata, and exact `+1` success-version validation. All findings
were fixed and independently scoped re-reviewed. The integrated suite then
exposed one stale source-shape assertion for the refactored waiting request
helper; that test-only mismatch was fixed and re-reviewed. Final inspection of
the retained `1093x614` screenshot also exposed overlap between the
`Паузирано време` label and its value. The narrow label column was corrected,
the live verifier now measures rendered label/value separation at every
required viewport, and the visual fix passed scoped re-review. No scoped
re-review found new Critical or Important breakage.

After all review fixes, the controller ran the integrated source-complete
verification:

```bash
source .venv/bin/activate
python -m compileall -q app scripts tests
python -m pytest
node --test tests/js/*.test.mjs
git diff --check
```

Final result: compile exited 0; 1511/1511 Python tests passed in 255.94 seconds;
64/64 JavaScript tests passed; and `git diff --check` exited 0. The automated
tests use temporary SQLite database paths. Neither the pre-review nor final
commands targeted `data/extrusion_terminal.sqlite3`, `production-db/`, or
backups.

The final guarded browser evidence was produced from a deterministic database
under `.test-runtime/physical-pallet-weight/` with these commands:

```bash
source .venv/bin/activate
python scripts/create_terminal_pallet_summary_fixture.py --db-path .test-runtime/physical-pallet-weight/extrusion.sqlite3 --output .test-runtime/physical-pallet-weight/fixture.json

EXTRUSION_DB_PATH=.test-runtime/physical-pallet-weight/extrusion.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

BASE_URL=http://127.0.0.1:8000 FIXTURE_JSON=.test-runtime/physical-pallet-weight/fixture.json ARTIFACT_DIR=artifacts/ui-checks/physical-pallet-weight node scripts/verify_terminal_pallet_summary_ui.mjs
```

Result: `Terminal pallet-summary UI verification passed.` The guarded run
recorded 132 assertions, 86 database mutation audits, 50 exact-path POSTs, and
21 screenshots across 1440x900, 1366x768, and 1093x614. It exactly consumed 10
expected console errors, three expected failed requests, and seven expected
HTTP error responses from deliberate recovery checks. There were zero
unexpected console errors, page errors, failed requests, HTTP error responses,
or dialogs. The final canonical database audit command and result were:

```bash
.venv/bin/python scripts/audit_terminal_pallet_summary_db.py \
  --db-path .test-runtime/physical-pallet-weight/extrusion.sqlite3 \
  --fixture-json .test-runtime/physical-pallet-weight/fixture.json
```

```text
{"database":".test-runtime/physical-pallet-weight/extrusion.sqlite3","integrity":"ok","foreign_key_violations":0,"visible_cards":9,"ready":8,"empty":1,"error":0,"weight_none":3,"weight_partial":3,"weight_complete":3,"mutation_audit":"passed","audited_fields":1260,"expected_saves":0,"unexpected_mutations":0,"hash_algorithm":"sha256"}
```

Its SHA-256 pre/post hashes were identical across all eight audited tables and
it reported zero unexpected mutations.

The final print evidence used:

```bash
source .venv/bin/activate
python scripts/create_print_template_fixture.py --db-path .test-runtime/physical-pallet-weight/print.sqlite3 --output .test-runtime/physical-pallet-weight/print-fixture.json

EXTRUSION_DB_PATH=.test-runtime/physical-pallet-weight/print.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8010

BASE_URL=http://127.0.0.1:8010 node scripts/render_print_template.mjs --fixture-json .test-runtime/physical-pallet-weight/print-fixture.json --output-dir artifacts/ui-checks/physical-pallet-weight/print
```

Result: every manifest DOM/PDF page count and total placement matched the five
scenario table above, and all 14 pages passed the recorded visual inspection.

The fixture databases, JSON summaries, PDFs, and screenshots were disposable
review evidence, not durable project records or production data. They were
deleted after acceptance and are not the authority for this contract.

## Migration Assessment And Deployment Boundary

Migration assessment

- Decision: Deterministic compatibility migration; schema-only on production.
- Why: the application needs one new persistent value for each `(card_id,
  pallet_number)` pair, with exact type/range, uniqueness, timestamp, and
  cascade constraints.
- Existing production data affected: none. No existing field has physical
  transport-pallet-weight meaning, and M007 changes no card, roll, tare, net,
  timing, shift, pallet assignment, recipe, import, status, version, or
  timestamp value.
- Proposed migrations: M007 `physical_pallet_weights` creates the final
  integer-hundredths table; M008 `physical_pallet_weight_hundredths` converts
  only an exact earlier M007 development table or validates/no-ops on the final
  table. Neither is applied to production.
- Transformation: `weight_hundredths = weight_tenths * 10` for the earlier
  unshipped M007 developer schema, preserving keys and timestamps. Production
  receives an empty final table with no backfill or inference.
- Unknowns or ambiguous rows: none require transformation. Any malformed
  pre-existing look-alike table is rejected rather than guessed.
- Required tests: fresh schema, exact constraints and cascade, accepted
  version-6 upgrade, no backfill, exact prior card/roll preservation,
  idempotence, malformed table rejection, injected rollback, integrity `ok`,
  and empty foreign-key check. These cases passed in the fresh Task 9 focused
  and complete suites, plus focused M008 conversion coverage.
- Production snapshot needed now: No for source acceptance. A final
  SQLite-safe backup and immutable clone are mandatory before deployment.
- Deployment constraint: schedule and separately approve a production
  maintenance window; freeze the exact candidate revision; stop worker access
  and the service; take, verify, fingerprint, and copy off-host the final
  SQLite-safe backup; rehearse the exact candidate and migration chain on
  disposable clones; compare every pre-existing logical value; deploy code and
  M007/M008 together through `bash scripts/deploy_production.sh`; verify migration
  history, idempotence, integrity, foreign keys, health revision, Admin,
  Terminal, correction, and print; take and compare a post-migration safe
  backup; complete the physical-printer rehearsal; then issue an explicit
  `GO`. Rollback is restoration of the verified final pre-migration backup plus
  the matching prior application revision, not reverse SQL.

Task 20 remains the next unimplemented workstream after this feature. Nothing
in this implementation changes its Item Master reconciliation gate or current
material/recipe boundary.

## Acceptance Corrections — 2026-09-11

The accepted follow-up originally used integer-tenths storage. The later
approved precision correction supersedes that part only: pallet-weight inputs
accept up to two fractional digits and preserve exact integer hundredths, so
`10.35` remains `10.35` and `12.5` displays as `12.50`. Negative input reports
the minimum-weight rule instead of a decimal-format error. Finish, print,
concurrency, dismissal, banner, and icon behavior remains unchanged.

Pallet and Finish Review feedback now share pale green, red, and amber status
banners with check-circle, circle-X, and warning-triangle icons. The terminal
`Палети` action uses a bounded transport-truck icon that remains clear at
`20px`; unrelated application icons were not redesigned. Validation appears
once in the modal footer while the input retains
its accessible invalid state, so errors no longer insert a second row-level
message or change table height.

Explicit X/footer/Escape/backdrop dismissal restores an invalid unsaved draft
to its last authoritative value and closes without a write. Valid dirty input
still saves before close. Stale, network, and malformed responses remain
reload-protected and are never represented as successful saves, but they do not
trap the operator inside the modal. The Finish Review footer can grow for a
two-line warning plus its outcome text without clipping the latter.

A successful pallet-weight notice is transient to the current modal visit.
Successful dismissal clears that notice, so reopening shows a neutral footer
without changing the saved value. Finish Review error and warning banners now
fill the complete status area up to the fixed gap before the action buttons,
matching the pallet-summary footer rule.

Final verification used only temporary databases and disposable UI evidence:

```bash
.venv/bin/python -m compileall -q app scripts tests
.venv/bin/python -m pytest
node --test tests/js/*.test.mjs
git diff --check

BASE_URL=http://127.0.0.1:8013 \
FIXTURE_JSON=.test-runtime/physical-pallet-weight-acceptance/fixture.json \
ARTIFACT_DIR=artifacts/ui-checks/physical-pallet-weight-acceptance-corrections \
node scripts/verify_terminal_pallet_summary_ui.mjs
```

Results: compile and diff checks exited `0`; 1521/1521 Python tests and 66/66
JavaScript tests passed; and the guarded live Playwright workflow passed across
1440x900, 1366x768, and the short-width layout with no unexpected console,
page, network, response, or dialog errors. Representative red, green, amber,
neutral, fatal-recovery, admin, and finish-review screenshots were visually
reviewed and then deleted as disposable acceptance evidence.

The two-decimal precision correction was reverified separately against a fresh
temporary database. The live workflow saved and reopened `10.35` without
rounding it to one decimal, displayed whole pallet values with two decimals,
and passed the same three-viewport guarded Playwright matrix. The final checks
passed with 1521 Python tests, 66 JavaScript tests, SQLite integrity `ok`, no
foreign-key violations, no unexpected database mutations, and a clean
`git diff --check`. The representative `autosave-complete.png` screenshot was
visually reviewed and then deleted with the other disposable acceptance
evidence.
