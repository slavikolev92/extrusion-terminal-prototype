# Unified Order-Finish Review

This note records the implemented Task 21 workstation review that now opens
from every eligible `Приключи` action. It extends the existing Task 22 finish
orchestration; it does not add another completion transaction, timing ledger,
or pallet calculation.

## Mode selection and exact operator actions

Lifecycle status selects the mode. Imported route-sequence text does not.

| Mode | Selection rule | Timing control | Footer outcome | Primary action |
| --- | --- | --- | --- | --- |
| Normal initial completion | `running` or `paused`, and `rewinding_roll_count` is blank or not positive | `Редактирай` opens the existing interval editor | none | `Потвърди приключване` |
| End extrusion into rewinding wait | `running` or `paused`, and `rewinding_roll_count` is positive | `Редактирай` opens the existing interval editor | `След потвърждение: Изчаква пренавиване · {count label}` | `Потвърди край на екструдирането` |
| Finalize returned rewinding rolls | status is `awaiting_rewinding`, regardless of whether the current marker remains positive | no edit control is rendered | `Изчаква пренавиване`, with ` · {count label}` only while the marker is positive | `Потвърди приключване` |

The count label is `1 ролка` for one and `{N} ролки` otherwise. The common
modal shows `Детайли на поръчката`, `Производствено време`, and
`Произведена продукция` for all three modes. The pallet record area scrolls
inside the production card while the card headings, time/order cards, total,
and full-width footer remain fixed.

The final visual tuning keeps the normal desktop dialog contained rather than
nearly edge-to-edge: it targets 94% viewport width, is capped at 1360×840 px,
and keeps a safe height margin while retaining the existing compact fallback
for constrained screens. Section headings are 21 px at the taller desktop
state (20 px at the shorter desktop state), values are 17 px, and table/body
actions are 16 px. The confirmation action uses the terminal's established
dark-blue primary treatment; red remains reserved for destructive actions.

## Timing authority and Task 22 reuse

Active timing is editable because a running or paused card has not yet applied
its final extrusion transition. `POST /terminal/cards/{card_id}/finish-review`
uses the existing Task 22 preview to freeze the stop and bind card ID, loaded
version, frozen database time, and finish mode in the existing authenticated
non-persistent review token. `Редактирай` uses the existing interval editor and
`POST /terminal/cards/{card_id}/finish-review/preview`; Apply returns to the
same summary without writing. Final confirmation submits the reviewed draft to
the existing `finish_card_with_timing_ledger()` path, which applies the timing
ledger and lifecycle transition atomically.

Waiting timing is immutable because extrusion already ended before the card
entered `awaiting_rewinding`. The review displays stored first start, stored
`finished_at`, productive duration, and paused duration. It creates no frozen
stop or token and offers no timing editor. Its tokenless
`POST /terminal/cards/{card_id}/finish` submission still calls the dedicated
`finalize_awaiting_rewinding_card()` transaction. That operation re-reads the
loaded version, status, active shift, timing closure, rolls, tare/net values,
and roll sequence, then changes only lifecycle/version/update metadata. It
does not change a timing segment or `finished_at`.

Both branches reuse the existing Task 22 optimistic-conflict rules, active
shift gate, `attach_terminal_pallet_summary()` boundary, mixed numbered/
unassigned pallet warning, final-shift attribution, queue normalization, and
backend finish validation. The common screen changes presentation and
orchestration only.

## Physical pallet placeholder seam

`Тегло палет, кг` is the weight of the physical pallet under the rolls. It is
not the card's roll-core tare field (`Шпула, кг`). Physical pallet weight is not
captured in this pilot revision.

The pallet-summary view model now exposes `pallet_weight = Decimal("0")` and
`pallet_weight_display = "0.0"` for every ready row and for the total. The
empty state also has an explicit zero total with those fields. The template
renders only those view-model values; there is no literal dash and no use of a
tare value in the physical-pallet column. This Task 21 contract supersedes the
earlier visual-dash placeholder described by the Task 22 timing-review note.

The seam is presentation-only. There is no pallet-weight input, database
column, migration, history, correction rule, or SQLite write. Gross remains
the sum of saved roll gross weights and net remains the sum of each saved
`gross_weight - tare_weight`; the `0.0` placeholder participates in neither
calculation. A separately specified future task must define physical pallet
weight ownership, persistence, and calculation semantics before replacing the
placeholder.

## Empty and error summaries

When no gross roll exists, the five-column shell remains visible, the record
area says `Няма въведени ролки.`, and the aligned total is
`Общо / 0 / 0.0 / 0.0 / 0.0`. This can be a valid review state for an active
card entering rewinding wait; the backend still decides which lifecycle
outcome requires returned gross rolls.

If saved roll data cannot be summarized safely, the record area says
`Обобщението по палети не може да бъде показано. Проверете данните за ролките.`
No plausible-looking total is rendered and confirmation is unavailable. The
exception boundary logs only the numeric card ID, exception type, and stack;
it does not log order/customer text or roll contents.

## Failure, concurrency, and focus behavior

- `×`, `Отказ`, and Escape dismiss an unlocked review without a write and
  restore focus to the initiating `Приключи` button. A backdrop click does not
  dismiss it. Focus starts on the safe cancel control, remains trapped in the
  modal, and has visible focus styling; the terminal behind it is inert and
  hidden from assistive technology while the review is open.
- Active review and preview failures retain the draft and Bulgarian message.
  Correctable timing issues reopen the editor; summary-level failures keep or
  reopen the common summary. A stale card locks Apply/Confirm, preserves the
  operator's review, exposes reload, and never overwrites the newer card.
- Waiting confirmation failures re-render the same review with the backend
  message. Correctable roll/tare/sequence failures allow Cancel so the operator
  can repair the card and reopen the review. A stale or unavailable waiting
  card locks the action or routes the message through the existing terminal
  reload behavior.
- A shift-stale event suspends either review and yields to the existing
  blocking shift-reload surface. It cannot submit after the shift disappears.
- Starting either confirmation marks the dialog busy and disables its actions.
  A second click or activation while the first request is pending is ignored,
  so only one finish request is issued.

## Verification record

The final live fixture was created only under
`.test-runtime/order-finish-review-adversarial/fixture.sqlite3`, and `/health` resolved to
that exact path before any browser opened. Chromium came only from the
repository-local Playwright 1.61.0 installation. The verifier used six
deterministic cards covering normal active, marked empty, marked mixed,
many-pallet waiting, marker-cleared waiting, and invalid zero-roll waiting
states.

Fixture, server, and live verifier commands:

```bash
mkdir -p .test-runtime/order-finish-review-adversarial artifacts/ui-checks/order-finish-review-adversarial
EXTRUSION_DATA_DIR=.test-runtime/order-finish-review-adversarial \
EXTRUSION_DB_PATH=.test-runtime/order-finish-review-adversarial/fixture.sqlite3 \
.venv/bin/python scripts/create_order_finish_review_fixture.py \
  --db-path .test-runtime/order-finish-review-adversarial/fixture.sqlite3 \
  --output .test-runtime/order-finish-review-adversarial/fixture.json

EXTRUSION_DATA_DIR=.test-runtime/order-finish-review-adversarial \
EXTRUSION_DB_PATH=.test-runtime/order-finish-review-adversarial/fixture.sqlite3 \
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8021

./node_modules/.bin/playwright --version
BASE_URL=http://127.0.0.1:8021 \
FIXTURE_JSON=.test-runtime/order-finish-review-adversarial/fixture.json \
ARTIFACT_DIR=artifacts/ui-checks/order-finish-review-adversarial \
node scripts/verify_order_finish_review_ui.mjs
```

The original acceptance run passed 33 assertion groups. After the bounded
adversarial and frontend re-review repairs, the latest live run passes 62
assertion groups at 1440×900, 1366×768, and compact 1093×614. It creates
exactly five screenshots with their required viewport dimensions and leaves
the unexpected console-error, page-error, failed-request, and cross-origin
arrays empty. The deliberate active-stale HTTP 409 and deliberately aborted
waiting-review controller request are retained separately as expected evidence.
The generated JSON and screenshot evidence was inspected during acceptance and
then removed as disposable output. The guarded verifier itself retains the
responsive long-value, focus-recovery, and final shift-gate checks.

Final automated commands:

```bash
.venv/bin/python -m compileall -q app tests scripts
node --check app/static/js/timing_interval_editor.mjs
node --check app/static/js/waiting_finish_review.mjs
node --check scripts/verify_order_finish_review_ui.mjs
node --test tests/js/*.test.mjs
.venv/bin/python -m pytest \
  tests/test_terminal_pallet_summary.py \
  tests/test_terminal_timing_correction.py \
  tests/test_finish_cancel_history.py \
  tests/test_rewinding_workflow.py \
  tests/test_terminal_v8_render.py \
  tests/test_terminal_sync.py \
  tests/test_order_finish_review_ui_script_safety.py -q
git diff --check
.venv/bin/python -m pytest -q
```

Latest observed results: 45 JavaScript tests passed; the final focused render
and verifier-safety group passed 209 Python tests in 33.74 seconds; and the
live verifier passed 62 assertion groups after the bounded scale and primary-
action color correction. The September 9 checkpoint rerun passed all 1342
Python tests in 244.21 seconds and all 45 JavaScript tests. Final syntax and
`git diff --check` commands exited zero.

## Mocked and temporary boundaries

- Automated route/unit tests use temporary SQLite databases and monkeypatch
  database time or narrow collaborators where a deterministic boundary is
  required. They do not mutate the runtime database.
- The live fixture uses fixed card/timing/roll data, while the active proposed
  stop is the live isolated server's database time. It is verification data,
  not a production snapshot and not a historical backfill.
- Browser evidence covers repository-local Chromium at the two required
  desktop viewports plus the effective compact 1093×614 viewport. It is not a
  multi-browser, printer, full screen-reader, or full WCAG certification.
- The approved source and live fixture intentionally use different sample
  order and pallet values. Design QA compares the same active completion mode,
  native viewport/density, layout, typography, and interaction surfaces.
- No application was deployed, shared, or pointed at the real runtime
  database. Generated fixtures and screenshots are disposable review evidence;
  they remain untracked and are removed after acceptance.

Migration assessment
- Decision: No migration
- Why: The change adds presentation fields, markup, controller behavior, and tests without changing schema or stored-value meaning.
- Existing production data affected: None.
- Proposed migration: None.
- Transformation: No values changed.
- Unknowns or ambiguous rows: None known; physical pallet weight is intentionally not inferred historically.
- Required tests: Temporary-database render, lifecycle, timing-preservation, and browser interaction checks.
- Production snapshot needed now: No.
- Deployment constraint: Deploy the verified application revision normally; do not add a pallet-weight schema until the separately specified follow-up task.
