# Terminal Timing Correction And Finish Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to execute this plan in the current
> session, `superpowers:test-driven-development` for every behavior change,
> `superpowers:requesting-code-review` after each backend/UI slice, and
> `superpowers:verification-before-completion` before reporting completion.

**Goal:** Let terminal operators correct productive-time intervals while a card
is running or paused, then review and correct the proposed finish time before
the card is completed.

**Architecture:** Keep `production_time_segments` as the authoritative ledger.
Refactor the existing Admin implementation into one connection-scoped ledger
builder, validator, and mutator with explicit Admin and Terminal policy
wrappers. A finish review is non-persistent; confirmation applies its complete
ledger and the existing finish lifecycle in one `BEGIN IMMEDIATE` transaction.

**Tech Stack:** FastAPI, Jinja, direct `sqlite3`, `app/timekeeping.py`, plain
JavaScript ES modules, pytest, and repository-local Playwright.

**Approved specification:**
`docs/superpowers/specs/2026-08-21-terminal-timing-correction-design.md`

**Approved UI reference:** `ui-prototypes/terminal-timing-correction.html`

## Accepted Design Gate

The V2 static prototype is approved. Production implementation must reproduce
its timing menu and dialogs; no further design approval is required before
starting the backend slices.

## Global Constraints

- Do not change the appearance, order, enabled state, or behavior of Start,
  Pause/Resume, or Finish. Only active-card Finish submission gains the approved
  review step.
- Add only `Производствено време` to the new terminal overflow menu.
  Do not copy the prototype's illustrative Print/Reprint item.
- Terminal timing correction is limited to `running` and `paused` cards with an
  active shift. Completed timing remains Admin-only.
- Pauses are derived gaps between productive intervals. Do not add pause rows,
  cross-card checks, or machine-conflict checks.
- Preserve existing Admin correction permissions and every Start/Pause/Resume,
  roll/tare, rewinding, pallet-warning, final-shift, and queue rule.
- Important validation is backend-authoritative. Browser calculations and
  validation are only immediate operator feedback.
- Use optimistic version checks and atomic writes. Never partially save a
  draft. Ordinary Terminal timing Save and reviewed Finish each increment the
  card version exactly once; existing Admin Save All version behavior remains
  unchanged.
- Do not alter schema files or migrations. No migration is required.
- Never use `data/extrusion_terminal.sqlite3` for tests or browser checks.
- Preserve unrelated dirty-worktree changes. Do not stage or commit without
  explicit user permission.

## File Map

**Create:**

- `tests/test_terminal_timing_correction.py` — shared-core, Terminal policy,
  parsing, route, and atomic-finish behavior.
- `app/static/images/terminal-ui/clock-icon.png` — exact copy of the approved
  `ui-prototypes/clock-icon.png` asset.
- `app/static/js/timing_interval_editor_core.mjs` — pure draft transformations,
  mask/shape checks, serialization, and authoritative-preview mapping.
- `app/static/js/timing_interval_editor.mjs` — menu, modal, preview, submit,
  focus, and stale-state controller.
- `tests/js/timing_interval_editor_core.test.mjs` — browser-independent JS
  behavior checks.
- `scripts/create_terminal_timing_correction_fixture.py` — deterministic
  temporary database fixture for UI verification.
- `scripts/verify_terminal_timing_correction_ui.mjs` — focused live-app
  Playwright workflow.
- `tests/test_terminal_timing_correction_ui_script_safety.py` — fixture and
  verifier guards against runtime-database use.
- `docs/implementation-notes/terminal-timing-correction.md` — durable behavior,
  transaction, and deployment notes.

**Modify:**

- `app/db.py` — shared ledger core, preview totals, Terminal wrapper, and atomic
  finish-with-ledger operation.
- `app/main.py` — strict Terminal draft parsing, render model, save/review/
  preview/confirm routes, and retained feedback state.
- `app/templates/terminal.html` — accepted overflow menu, timing editor, finish
  review, and module bootstrap.
- `tests/test_admin_production_corrections.py` — prove all Admin timing entry
  points retain policy while sharing strict/future validation.
- `tests/test_admin_card_detail_redesign.py` — preserve existing Admin Save All
  and bulk-ledger transaction/version behavior through the refactor.
- `tests/test_finish_cancel_history.py` — frozen running/paused completion and
  rollback coverage.
- `tests/test_rewinding_workflow.py` — preserve active-to-waiting and
  timing-immutable waiting finalization.
- `tests/test_terminal_v8_render.py` — route, menu, form, dialog, and finish-flow
  render contracts.
- `tests/test_terminal_sync.py` — lock and retain an open timing draft on the
  existing `terminal:card-stale` event.
- `README.md` — record the implemented operator workflow and distinguish atomic
  correction Save from immediate lifecycle actions.

## Data And Request Contract

Add these small immutable types in `app/db.py`:

```python
@dataclass(frozen=True)
class TimingDraftRow:
    segment_id: int | None
    start_date: str
    start_time: str
    stop_date: str
    stop_time: str
    deleted: bool = False


@dataclass(frozen=True)
class TimingLedgerPreview:
    draft_rows: tuple[TimingDraftRow, ...]
    intervals: tuple[dict[str, Any], ...]
    first_started_at: str | None
    proposed_finished_at: str | None
    production_seconds: int
    paused_seconds: int
    reviewed_at: str


@dataclass(frozen=True)
class TimingValidationIssue:
    source_index: int | None
    field: str
    message: str


@dataclass(frozen=True)
class TimingLedgerOutcome:
    result: RuleResult
    preview: TimingLedgerPreview | None = None
    issues: tuple[TimingValidationIssue, ...] = ()
```

The browser submits one `timing_draft` form field containing a JSON array:

```json
[
  {
    "segment_id": 17,
    "start_date": "2026-08-21",
    "start_time": "10:00",
    "stop_date": "2026-08-21",
    "stop_time": "12:30",
    "deleted": false
  },
  {
    "segment_id": null,
    "start_date": "2026-08-21",
    "start_time": "13:30",
    "stop_date": "",
    "stop_time": "",
    "deleted": false
  }
]
```

Each existing segment must appear exactly once; deletion must be explicit.
Reject duplicate, missing, unknown, and foreign IDs. New rows use
`segment_id: null`; deleted unsaved rows may be omitted. Never accept
`end_reason`, totals, an “unchanged” flag, or canonical UTC values from the
browser.

The server compares submitted local date/minute fields with the transaction's
stored segment values. A matching existing minute preserves the exact stored
UTC seconds and repeated-hour offset. A changed or new value is parsed as
Sofia-local `:00` through `app/timekeeping.py`; a skipped or ambiguous local
minute is rejected.

In running finish mode, the server-issued frozen close is also an original
baseline: if the submitted final stop still matches its Sofia-local minute,
preserve the frozen timestamp's exact seconds; if the operator changes that
minute, parse it with seconds `00`. The same preservation rule applies when a
finish-review preview is reopened without editing.

Use these routes:

```text
POST /terminal/cards/{card_id}/timing-ledger/preview
POST /terminal/cards/{card_id}/timing-ledger
POST /terminal/cards/{card_id}/finish-review
POST /terminal/cards/{card_id}/finish-review/preview
POST /terminal/cards/{card_id}/finish
```

- `timing-ledger/preview` accepts `loaded_version` and `timing_draft`, samples
  SQLite current time, and returns authoritative non-persistent interval and
  total calculations. The ordinary editor calls it after Add/Delete/Undo and
  on date/time blur so Sofia DST transitions are never calculated as naive
  browser-local elapsed minutes.
- `timing-ledger` persists an ordinary complete draft and uses the existing PRG
  success pattern. A failure rerenders and reopens the retained draft.
- `finish-review` accepts `loaded_version`, samples SQLite current time, and
  returns a non-persistent JSON `TimingLedgerPreview` for the current ledger.
- `finish-review` also returns an opaque `review_token` that authenticates the
  card ID, loaded version, and frozen time with standard-library HMAC-SHA256 and
  a process-local random key.
- `finish-review/preview` accepts `loaded_version`, `review_token`, and
  `timing_draft`, validates without writing, and returns recalculated JSON.
- Active-card `finish` accepts those same three fields and performs the atomic
  ledger/lifecycle write. It extracts `reviewed_at` only from the verified
  token and never trusts a browser timestamp. Awaiting-rewinding finalization
  retains its existing loaded-version-only request and current confirmation
  modal.

Implement token helpers in `app/main.py` as
`encode_finish_review_token(card_id, loaded_version, reviewed_at, *, key)` and
`decode_finish_review_token(token, *, key)`. Encode a canonical, key-sorted
compact JSON payload with URL-safe base64 (no padding), append a URL-safe
base64 HMAC-SHA256 signature separated by `.`, and verify with
`hmac.compare_digest()`. Production calls use one `secrets.token_bytes(32)` key
created when the process imports the app; tests pass explicit keys. Any decode,
field, card/version, signature, or canonical-time failure returns the single
documented invalid-review message.

All three JSON preview routes return this exact success envelope with HTTP 200:

```json
{
  "ok": true,
  "review_token": "opaque-or-null",
  "preview": {
    "reviewed_at_utc": "2026-08-21 11:15:00",
    "first_start_display": "21.08.2026 10:00",
    "proposed_stop_display": "21.08.2026 14:15",
    "production_seconds": 11700,
    "paused_seconds": 3600,
    "draft": [
      {
        "segment_id": 17,
        "start_date": "2026-08-21",
        "start_time": "10:00",
        "stop_date": "2026-08-21",
        "stop_time": "14:15",
        "deleted": false
      }
    ],
    "intervals": [{"source_index": 0, "duration_seconds": 9000}]
  }
}
```

`review_token` is `null` for ordinary preview. UTC values use canonical
`YYYY-MM-DD HH:MM:SS`; display values are server-formatted Sofia
`DD.MM.YYYY HH:MM`; durations are non-negative integers. The server-normalized
`draft` is authoritative for opening finish edit mode, including the generated
Sofia final-stop date/minute; the browser performs no timezone conversion.

Stale responses use HTTP 409 and validation responses use HTTP 422 with this
exact envelope:

```json
{
  "ok": false,
  "messages": ["Краят трябва да бъде след началото."],
  "field_errors": [
    {"source_index": 0, "field": "stop_time", "message": "Краят трябва да бъде след началото."}
  ]
}
```

Allowed fields are `start_date`, `start_time`, `stop_date`, `stop_time`, and
`form`; global lifecycle/token/stale errors use `source_index: null` and
`field: "form"`. Issues are returned in display/focus order. The controller
focuses the first issue when its row is editable; a locked stale draft keeps
focus inside the modal and exposes Reload/Cancel. None of these routes
redirects or mutates data.

For finish review, no submitted timestamp may exceed the token's frozen
`reviewed_at`; `reviewed_at` itself must not exceed SQLite transaction time.
This prevents time spent in the modal from extending production. A tampered or
post-restart token fails without mutation and requires the operator to reopen
the review. The operator may move the last stop earlier through the editor.

## TDD Sequencing And Named Checks

Treat every named check below as its own red/green micro-step: add one failing
test, run only that test, implement the minimum behavior, rerun it, then move to
the next name. Do not batch an entire task's failures before implementation.

Add these tests beside the existing timing-ledger block in
`tests/test_admin_production_corrections.py` and the bulk Save All block in
`tests/test_admin_card_detail_redesign.py`:

- `test_admin_timing_rejects_equal_and_future_changed_values`
- `test_admin_individual_and_bulk_timing_share_final_ledger_validation`
- `test_admin_standalone_timing_correction_increments_version_once`
- `test_admin_save_all_timing_keeps_outer_transaction_and_version_behavior`

Create `tests/test_terminal_timing_correction.py` with these groups:

- `test_terminal_timing_save_allows_running_and_paused_with_active_shift`
- `test_terminal_timing_save_rejects_other_statuses_and_missing_shift`
- `test_terminal_timing_draft_rejects_duplicate_missing_unknown_and_foreign_ids`
- `test_terminal_timing_failure_rolls_back_card_and_complete_ledger`
- `test_terminal_timing_enforces_running_and_paused_ledger_shapes`
- `test_terminal_timing_rejects_equal_reversed_overlapping_and_future_rows`
- `test_terminal_timing_allows_adjacent_rows`
- `test_terminal_timing_preserves_unchanged_seconds_and_zeroes_changed_minutes`
- `test_terminal_timing_handles_skipped_repeated_and_unchanged_ambiguous_minutes`
- `test_terminal_timing_save_preserves_unrelated_production_data_and_versions_once`
- `test_terminal_timing_json_parser_rejects_oversize_extra_and_wrong_types`
- `test_terminal_timing_preview_is_authoritative_nonpersistent_and_dst_correct`
- `test_terminal_timing_preview_targets_the_first_server_invalid_field`
- `test_finish_review_freezes_time_and_writes_nothing`
- `test_finish_review_returns_server_normalized_editable_stop`
- `test_finish_review_token_rejects_tampering_substitution_and_new_process_key`
- `test_finish_preview_rejects_stale_or_missing_shift_and_retains_draft`
- `test_finish_preview_recalculates_without_mutation`
- `test_finish_with_timing_rolls_back_every_validation_failure`
- `test_finish_with_timing_uses_one_lifecycle_version_increment`

Add finish tests immediately after the existing running/paused finish cases in
`tests/test_finish_cancel_history.py` and after the active-to-waiting cases in
`tests/test_rewinding_workflow.py`:

- `test_reviewed_running_finish_uses_frozen_or_earlier_corrected_stop`
- `test_reviewed_paused_finish_applies_only_submitted_timing_edits`
- `test_reviewed_finish_sets_markers_shift_and_normalizes_queue_once`
- `test_reviewed_finish_to_waiting_is_atomic_for_running_and_paused`
- `test_waiting_finalization_remains_timing_immutable_without_review_payload`

Add render/sync checks beside the existing lifecycle and finish-confirmation
blocks in `tests/test_terminal_v8_render.py` and stale-event block in
`tests/test_terminal_sync.py`:

- `test_terminal_timing_menu_visibility_icon_and_lifecycle_markup`
- `test_terminal_timing_dialog_matches_approved_v2_contract`
- `test_active_finish_uses_review_while_waiting_finish_keeps_simple_confirmation`
- `test_terminal_timing_errors_reopen_or_lock_the_submitted_draft`
- `test_terminal_card_stale_locks_timing_without_topbar_focus_takeover`
- `test_terminal_shift_stale_leaves_only_shift_reload_modal_active`
- `test_terminal_timing_preview_ignores_superseded_and_post_stale_responses`

New Node subtests use these exact names:

- `time mask inserts one colon and rejects incomplete or impossible values`
- `running add interval creates blank operator-entered boundaries`
- `paused add interval creates a blank closed-row draft`
- `pending delete retains its displayed number and undo restores it`
- `server preview maps interval productive and paused seconds without Date parsing`

New safety tests are:

- `test_timing_fixture_refuses_runtime_and_paths_outside_test_runtime`
- `test_timing_verifier_requires_matching_health_database_identity`
- `test_timing_verifier_writes_only_to_supplied_artifact_directory`

Assert these exact new Bulgarian messages while retaining the existing
`STALE_CARD_MESSAGE` and `NO_ACTIVE_SHIFT_MESSAGE` constants:

- malformed draft: `Данните за производственото време са невалидни.`
- equal/reversed interval: `Краят трябва да бъде след началото.`
- future value: `Времето не може да бъде в бъдещето.`
- invalid review token: `Прегледът за приключване е невалиден. Отворете го отново.`

---

### Task 1: Extract The Shared Timing-Ledger Engine

**Files:**

- Modify: `app/db.py`
- Modify: `tests/test_admin_production_corrections.py`
- Modify: `tests/test_admin_card_detail_redesign.py`

- [ ] Red/green the four named Admin checks one at a time. Begin with the strict
  interval test, confirm its expected assertion failure, implement only that
  rule, rerun it green, then repeat for shared entry points, dedicated version,
  and Save All outer-transaction behavior:

  ```bash
  .venv/bin/python -m pytest \
    tests/test_admin_production_corrections.py::test_admin_timing_rejects_equal_and_future_changed_values -q
  ```

- [ ] Refactor `_update_admin_timing_ledger()` into connection-scoped private
  stages: build the complete proposed ledger, validate it against an explicit
  status policy and transaction time, and apply ordered delete/update/insert
  mutations. The apply stage must not call `touch_card()` itself.
- [ ] Have the shared validator retain each proposal row's `source_index` and
  emit ordered `TimingValidationIssue` values. Existing Admin wrappers flatten
  those issues back to their current `RuleResult.messages`; Terminal wrappers
  preserve the structured targets.
- [ ] Make all Admin ledger and individual segment operations delegate to those
  stages. Keep their public signatures and success/error messages compatible.
- [ ] A standalone timing operation starts `BEGIN IMMEDIATE`. When the shared
  stages receive the existing Admin Save All connection, they must not start,
  commit, roll back, or change that outer transaction's version semantics.
- [ ] Tighten closed intervals to `ended_at > started_at`; allow adjacency;
  reject only changed/new future timestamps; validate open-row count and
  chronological final position after the complete proposal is built.
- [ ] Preserve existing end reasons on existing closed rows and keep Admin's
  explicit valid reason handling. Apply all changes only after full validation,
  refresh timing markers, then touch the card exactly once.
- [ ] Add a pure connection-scoped totals helper that sorts canonical rows,
  sums closed productive seconds, and sums non-negative gaps as paused seconds.
  An optional preview end may close only the final open row for calculation.
- [ ] Rerun both focused files after all four micro-steps; inspect the diff for
  any changed Admin access or historical-card behavior:

  ```bash
  .venv/bin/python -m pytest \
    tests/test_admin_production_corrections.py \
    tests/test_admin_card_detail_redesign.py -q
  ```

**Checkpoint:** Request a code review focused on data integrity and Admin
regressions before continuing.

---

### Task 2: Add Ordinary Terminal Ledger Correction

**Files:**

- Modify: `app/db.py`
- Modify: `app/main.py`
- Create: `tests/test_terminal_timing_correction.py`
- Modify: `tests/test_terminal_v8_render.py`

**Public interfaces:**

```python
def preview_terminal_timing_ledger(
    card_id: int,
    loaded_version: int,
    draft_rows: list[TimingDraftRow],
    *,
    preview_at: str | None = None,
    finish_mode: bool = False,
    require_active_shift: bool = True,
) -> TimingLedgerOutcome: ...


def update_terminal_timing_ledger(
    card_id: int,
    loaded_version: int,
    draft_rows: list[TimingDraftRow],
    *,
    require_active_shift: bool = True,
) -> TimingLedgerOutcome: ...
```

- [ ] Red/green the first thirteen named Terminal checks one at a time, in their
  listed order. Each test must first fail on its intended assertion, receive
  the smallest supporting database/parser change, and pass before the next
  test is added. Run each by full node ID, for example:

  ```bash
  .venv/bin/python -m pytest \
    tests/test_terminal_timing_correction.py::test_terminal_timing_save_allows_running_and_paused_with_active_shift -q
  ```

- [ ] Implement the strict JSON parser in `app/main.py`: reject a form value
  over 65,536 UTF-8 bytes; require a top-level list of at most 200 objects;
  require exactly the six documented keys; accept only a positive Python `int`
  (not Boolean) or `null` for `segment_id`; require a real Boolean for
  `deleted`; and require string date/time fields using exact `YYYY-MM-DD` and
  `HH:MM` or paired blanks. Multiple `null` IDs are valid new rows. Reject all
  extra keys, floats, numeric strings, unpaired date/time blanks, and malformed
  JSON before calling the database layer.
- [ ] Implement the Terminal adapter inside the same `BEGIN IMMEDIATE`
  transaction as validation and mutation. Require active shift and status
  `running`/`paused`; derive end reasons server-side (`pause` for a formerly
  open row closed before a new open row, `correction` for new closed rows, and
  `None` for the final open row).
- [ ] Add `POST .../timing-ledger`, using `terminal_response()`/
  `terminal_post_response()` conventions. On invalid/stale input, retain the
  submitted rows; stale state is locked and requires reload or Cancel.
- [ ] Add `POST .../timing-ledger/preview` using the same parser, ownership,
  status, shift, version, and transaction-time validation without mutation.
  Return server-derived interval durations/totals and Sofia display strings in
  the documented JSON envelope. Return row/field targets for parser, DST,
  future, order, and overlap failures.
- [ ] Add a server-rendered timing model to `terminal_context()` containing only
  running/paused rows, their local date/minute display values, exact IDs,
  status, version, server time, and display context. Do not expose the action
  for other statuses.
- [ ] For an ordinary running preview, keep the stop cell blank but calculate
  its provisional duration and production total through current server time;
  do not persist that preview end.
- [ ] Red/green route/render checks for successful PRG, retained invalid draft,
  stale locked draft, active-shift/status blocking, and absence from completed/
  waiting cards. Cover missing shift and stale version on both the ordinary
  preview and save routes with no mutation.
- [ ] Rerun the complete new test file and focused render file:

  ```bash
  .venv/bin/python -m pytest \
    tests/test_terminal_timing_correction.py tests/test_terminal_v8_render.py -q
  ```

**Checkpoint:** Request a code review focused on policy separation, transaction
boundaries, local-time parsing, and unrelated-data preservation.

---

### Task 3: Make Finish Review And Confirmation Atomic

**Files:**

- Modify: `app/db.py`
- Modify: `app/main.py`
- Modify: `tests/test_terminal_timing_correction.py`
- Modify: `tests/test_finish_cancel_history.py`
- Modify: `tests/test_rewinding_workflow.py`
- Modify: `tests/test_terminal_v8_render.py`

**Public interface:**

```python
def finish_card_with_timing_ledger(
    card_id: int,
    loaded_version: int,
    draft_rows: list[TimingDraftRow],
    reviewed_at: str,
    *,
    require_active_shift: bool = True,
) -> TimingLedgerOutcome: ...
```

- [ ] Red/green the seven named finish checks in
  `tests/test_terminal_timing_correction.py` one at a time, starting with the
  non-persistent frozen preview, then token integrity, preview recalculation,
  rollback, and the sole lifecycle version increment.
- [ ] Red/green the five named normal/rewinding regression checks one at a time.
  Each failure snapshot must include the card row and ordered timing rows before
  and after the rejected operation.
- [ ] After the micro-steps, run the focused finish set:

  ```bash
  .venv/bin/python -m pytest \
    tests/test_terminal_timing_correction.py \
    tests/test_finish_cancel_history.py \
    tests/test_rewinding_workflow.py -q
  ```

- [ ] Extract the current active-card body of `finish_card()` into a
  connection-scoped lifecycle operation. Reuse it from the reviewed workflow;
  keep the legacy function behavior for non-reviewed internal callers.
- [ ] In reviewed finish, begin once, load/check version and active shift once,
  validate the complete draft against `reviewed_at`, apply without touching the
  version, then execute the existing lifecycle `UPDATE cards ... version =
  version + 1` exactly once. That lifecycle update is the sole version
  increment; reviewed finish must not call `touch_card()`.
- [ ] Add minimal standard-library HMAC helpers in `app/main.py`. Sign the
  server-sampled card ID, loaded version, and `reviewed_at`; verify with
  `hmac.compare_digest()` before preview or confirmation. Do not add sessions,
  storage, dependencies, or deployment secrets.
- [ ] Add the two non-persistent review routes and change only the active-card
  branch of `POST .../finish` to verify the token, parse the draft, and call the
  reviewed workflow. Return JSON for review/preview; retain a failed confirm
  draft in the server-rendered modal. Keep awaiting-rewinding finalization
  backward-compatible.
- [ ] Carry the existing `finish_confirmation_message` into the new active-card
  summary so the mixed-pallet warning remains visible in every finish branch.
- [ ] Rerun focused tests and review each lifecycle branch for accidental timing
  mutation or double version increments.

**Checkpoint:** Request a code review focused on transaction atomicity and all
three finish branches.

---

### Task 4: Build The Pure Interval-Editor Module

**Files:**

- Create: `app/static/js/timing_interval_editor_core.mjs`
- Create: `tests/js/timing_interval_editor_core.test.mjs`

- [ ] Red/green the five named Node subtests one at a time in listed order. Use
  this command with the current subtest name until it passes before adding the
  next:

  ```bash
  node --test --test-name-pattern="time mask inserts one colon" \
    tests/js/timing_interval_editor_core.test.mjs
  ```

- [ ] Implement only pure exported functions; do not access DOM or submit
  forms. Render duration/totals from the latest server preview; local checks may
  identify incomplete fields but never become persistence authority.
- [ ] Rerun the JS tests and inspect the module for deterministic timezone-free
  behavior. Do not parse local date/time fields with browser `Date`.

**Checkpoint:** Request a focused review of input masking and interval-state
transitions.

---

### Task 5: Implement The Approved Terminal UI

**Files:**

- Create: `app/static/images/terminal-ui/clock-icon.png`
- Create: `app/static/js/timing_interval_editor.mjs`
- Modify: `app/templates/terminal.html`
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_terminal_sync.py`

- [ ] Red/green the seven named render/sync checks one at a time. The lifecycle
  markup test must snapshot the Start/Pause/Resume/Finish form blocks before the
  UI edit and assert that only the active Finish data hook changes.
- [ ] After the six micro-steps, run the focused render/sync set:

  ```bash
  .venv/bin/python -m pytest \
    tests/test_terminal_v8_render.py tests/test_terminal_sync.py -q
  ```

- [ ] Copy the approved PNG into `app/static/images/terminal-ui/clock-icon.png`,
  verify exact bytes/checksum, and give the rendered image explicit visible
  dimensions and an empty decorative alt.
- [ ] Add an accessible ellipsis button/menu after the existing three lifecycle
  slots without modifying those slots. Support click, keyboard activation,
  outside-click close, Escape, and focus return.
- [ ] Render one reusable editor matching the V2 prototype: fixed header,
  totals, column header, and footer; scrollable row body; separate native date
  and masked text time inputs; subtle vertical dividers; neutral Delete/Undo;
  and completely blank final running stop cell.
- [ ] Implement the controller module: hydrate from the safe JSON model, update
  the hidden `timing_draft`, call review/preview endpoints, render server errors,
  and prevent double submission. Call ordinary preview on modal open, after
  Delete/Undo when the remaining draft is complete, every complete date/time
  field blur, and each `terminal:server-time` event while a complete running
  editor is open. Add Interval creates/focuses blank fields and does not call
  preview until the new required fields are complete. Keep the last valid
  totals visible with a loading state until the new preview returns.
- [ ] In finish mode, replace the local draft with the server-normalized
  `preview.draft` before opening the editor. Map `field_errors` to exact row
  controls and focus the first target; show `field: "form"` messages in the
  modal alert without guessing a field.
- [ ] Give preview calls one `AbortController` plus a monotonically increasing
  generation number. Every draft mutation first aborts any request and advances
  the generation, even when the draft is incomplete and no replacement request
  will start. Apply a response only when its generation is current and the
  draft is not stale; abort all preview work when either stale event locks or
  suspends the modal.
- [ ] Implement accessible modal behavior: background inertness, focus trap,
  focus first invalid field, direct Escape/Cancel discard, and focus
  restoration. In finish mode, Apply returns to summary without saving; Cancel
  discards all review changes.
- [ ] Replace only the active-card generic confirmation path. Keep the Finish
  button itself unchanged and leave awaiting-rewinding on the existing simple
  modal/script.
- [ ] Subscribe the controller to `terminal:server-time` for open-row preview
  calculations. On `terminal:card-stale`, retain and lock the visible timing
  modal and suppress the generic topbar focus takeover. On
  `terminal:shift-stale`, suspend/hide the timing modal and let the existing
  blocking shift-reload dialog be the sole `aria-modal` and focus trap.
- [ ] Rerun JS, render, and sync tests. Compare the implementation against the
  accepted prototype at the source level before browser verification.

**Checkpoint:** Request a code review focused on approved visual fidelity,
accessibility, stale handling, and lifecycle-control preservation.

---

### Task 6: Browser Verification And Durable Documentation

**Files:**

- Create: `scripts/create_terminal_timing_correction_fixture.py`
- Create: `scripts/verify_terminal_timing_correction_ui.mjs`
- Create: `tests/test_terminal_timing_correction_ui_script_safety.py`
- Create: `docs/implementation-notes/terminal-timing-correction.md`
- Modify: `README.md`

- [ ] Red/green the three named fixture/verifier safety tests one at a time.
  Begin with runtime-path refusal:

  ```bash
  .venv/bin/python -m pytest \
    tests/test_terminal_timing_correction_ui_script_safety.py::test_timing_fixture_refuses_runtime_and_paths_outside_test_runtime -q
  ```

- [ ] Create deterministic running, paused, completed, awaiting-rewinding, and
  many-interval cards plus an active shift in a temporary SQLite database.
- [ ] Implement one Playwright verifier covering: menu/icon loading; unchanged
  lifecycle controls; ordinary running and paused saves; Add Interval;
  Delete/Undo; blank open stop; `1350` → `13:50`; incomplete, invalid, and
  future rejection; Cancel; many-row internal scrolling; finish freeze;
  Edit/Apply/Cancel/Confirm; mixed-pallet warning; completed/waiting absence;
  stale takeover; focus trap/restoration; Escape; and double-submit blocking.
- [ ] Save screenshots at `1366×768` and `1920×1080` beneath
  `artifacts/ui-checks/terminal-timing-correction/` and record exact commands.
- [ ] Document interval/pause semantics, Terminal/Admin access, local-time and
  minute precision, frozen finish, transaction boundaries, end reasons, stale
  response, preserved data, and “no migration” in the implementation note.
- [ ] Update README's production-timing section with the implemented workflow.
  Change the existing “no save all for timing actions” sentence only enough to
  distinguish immediate Start/Pause/Resume lifecycle actions from the atomic
  Save inside the timing-correction draft.
- [ ] Run the safety test, create a fresh fixture, start FastAPI with
  `EXTRUSION_DB_PATH` pointing to it, run the verifier, and inspect both
  screenshots. Do not use or copy the runtime database.

  Prepare the fixture and artifact directories:

  ```bash
  mkdir -p /home/sk/projects/extrusion-terminal/.test-runtime/terminal-timing-correction
  mkdir -p /home/sk/projects/extrusion-terminal/artifacts/ui-checks/terminal-timing-correction
  EXTRUSION_DB_PATH=/home/sk/projects/extrusion-terminal/.test-runtime/terminal-timing-correction/fixture.sqlite3 \
    .venv/bin/python scripts/create_terminal_timing_correction_fixture.py \
    --db-path /home/sk/projects/extrusion-terminal/.test-runtime/terminal-timing-correction/fixture.sqlite3 \
    --output /home/sk/projects/extrusion-terminal/.test-runtime/terminal-timing-correction/fixture.json
  ```

  Start the app in one terminal:

  ```bash
  EXTRUSION_DB_PATH=/home/sk/projects/extrusion-terminal/.test-runtime/terminal-timing-correction/fixture.sqlite3 \
    .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8014
  ```

  Run the verifier from a second terminal, then stop the server with `Ctrl-C`:

  ```bash
  BASE_URL=http://127.0.0.1:8014 \
  FIXTURE_JSON=/home/sk/projects/extrusion-terminal/.test-runtime/terminal-timing-correction/fixture.json \
  ARTIFACT_DIR=/home/sk/projects/extrusion-terminal/artifacts/ui-checks/terminal-timing-correction \
    node scripts/verify_terminal_timing_correction_ui.mjs
  ```

**Checkpoint:** Request final code review before the completion suite.

---

### Task 7: Final Verification And Handoff

- [ ] Run Python syntax/import checks:

  ```bash
  .venv/bin/python -m compileall app scripts
  ```

- [ ] Run focused backend and UI tests:

  ```bash
  .venv/bin/python -m pytest \
    tests/test_terminal_timing_correction.py \
    tests/test_admin_production_corrections.py \
    tests/test_finish_cancel_history.py \
    tests/test_rewinding_workflow.py \
    tests/test_terminal_v8_render.py \
    tests/test_terminal_sync.py \
    tests/test_terminal_timing_correction_ui_script_safety.py -q
  node --test tests/js/timing_interval_editor_core.test.mjs
  ```

- [ ] Run the complete Python suite and whitespace check:

  ```bash
  .venv/bin/python -m pytest
  git diff --check
  git status --short
  ```

- [ ] Rerun the focused live-app Playwright verifier against a newly created
  temporary database and inspect the final screenshots.
- [ ] Use `git status --short` to enumerate every tracked and untracked feature
  file. Review tracked changes with `git diff -- <path>`, each new text file
  with `git diff --no-index /dev/null <path>`, and the copied PNG with
  `sha256sum` against `ui-prototypes/clock-icon.png`. Check schema/migration
  absence, one-version Terminal writes, retained Admin behavior, unchanged
  lifecycle controls, existing finish/rewinding branches, user-visible
  Bulgarian errors, and unrelated dirty files.
- [ ] Report implementation and verification results with links to the main
  changed files and artifacts. Do not stage or commit unless the user separately
  authorizes it.

## Completion Criteria

- Operators can correct only running/paused timing from the approved overflow
  menu; completed timing is Terminal read-only and remains Admin-correctable.
- The ledger contains productive intervals only; pauses and both totals are
  calculated correctly.
- Time input, dialog layout, blank open stop, neutral delete, scrolling, and
  labels match the approved V2 prototype.
- Finish captures a server time immediately, permits retrospective correction,
  and applies timing plus the existing lifecycle atomically only on Confirm.
- Backend validation covers local-time validity, future/frozen limits, strict
  interval order, overlap, ledger shape, ownership, shift, and stale version.
- Existing production data, lifecycle controls, Admin correction, and all
  normal/rewinding finish branches remain intact.
- Focused tests, full pytest, JS tests, live Playwright checks, screenshot
  inspection, and `git diff --check` pass against temporary data only.
- No database migration, unrelated refactor, stage, or commit is introduced.
