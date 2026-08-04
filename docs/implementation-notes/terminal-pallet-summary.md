# Terminal Pallet Summary

## Purpose and scope

`/terminal` provides a read-only `Палети` summary for the selected card. It is
an aid for checking pallet transport information from saved roll entries; it
does not edit rolls or create pallet records.

The button is present for the five terminal-visible statuses: `pending`,
`running`, `paused`, `awaiting_rewinding`, and `completed`. It appears in the
right-aligned actions of the `Ролки` panel. When the rewinding action exists,
the order is `Пренавиване` followed by `Палети`; otherwise `Палети` appears in
the same place on its own.

The feature does not add or change a database schema, migration, route, write
handler, card lifecycle rule, roll entry/correction workflow, admin screen, or
print calculation/output. Opening and closing the dialog uses the selected
card's already-rendered `roll_entries` and does not issue a pallet-summary
request or write production data.

## Operator states and copy

The centered dialog is titled `Обобщение по палети` and retains order context
as `Поръчка №{order number}`.

- `ready`: a semantic four-column table: `Палет`, `Брой ролки`, `Бруто, кг`,
  and `Нето, кг`. It has a separate `Общо` footer row.
- `empty`: no saved entered rolls exist, so the dialog shows `Няма въведени
  ролки.` instead of a table.
- `error`: saved roll data cannot safely be summarized, so the dialog shows
  `Обобщението по палети не може да бъде показано. Проверете данните за
  ролките.` The selected terminal card remains otherwise usable.

## Saved-data calculation contract

A participating roll is a saved roll whose `gross_weight` is not `NULL`.
Only that roll's saved pallet snapshot participates; the card's current pallet
default for future rolls never creates a summary row.

For every participating roll, saved gross, tare, and net weights must be
finite, non-negative `Decimal` values. The saved net must exactly equal saved
gross minus saved tare. Its pallet must be `NULL` or an actual integer from 1
through 999 (not a numeric string or boolean). Numbered pallet rows sort by
ascending numeric pallet number. `Без палет` is appended last whenever any
participating roll has a blank pallet, including all-unassigned cards.

Totals are exact decimal sums of saved values. Each pallet total and the
overall total is rounded only once for display to one decimal place using
`ROUND_HALF_UP`; no float arithmetic, pre-rounded display values, inferred
weights, or recomputation is used.

Invalid or inconsistent participating rolls produce the `error` state rather
than a partial result, a repaired net weight, an omitted roll, or a zero value.
Those alternatives can look plausible while giving incorrect transportation
information.

## Failure containment and modal coordination

The pure calculator deliberately does not catch unexpected programming errors.
The sole broad exception boundary is `attach_terminal_pallet_summary()` in the
terminal page-context preparation. This narrowly contains malformed saved data
or an optional-summary defect without hiding failures elsewhere in the
terminal. It logs the exception stack and numeric card ID only; it must not log
order, customer, material, notes, weights, or roll contents.

The dialog is owned by the existing inline terminal drawer/modal coordinator.
Opening it closes queue, waiting, produced-history, and rewinding surfaces;
roll correction disables its trigger. Finish, shift, and roll-change overlays
block underlying terminal controls and do not stack with the summary.

The dialog supports its explicit `Затвори` button, Escape, and backdrop close.
Focus is trapped while open and normally returns to the `Палети` trigger on
close. The terminal background becomes inert and `aria-hidden` while the
dialog is active, and its prior state is restored on every close path. A long
table scrolls inside the dialog so its title and close action stay reachable.
If the selected card becomes stale, the summary closes without restoring focus
to stale controls and focus moves to the existing reload action. A shift-stale
takeover closes the summary before the existing shift reload surface appears.

## Temporary browser verification

Use only a freshly generated fixture under this worktree's `.test-runtime/`
directory and a loopback-only server. From the repository worktree, run:

```bash
mkdir -p .test-runtime/terminal-pallet-summary
mkdir -p artifacts/ui-checks/terminal-pallet-summary

.venv/bin/python scripts/create_terminal_pallet_summary_fixture.py \
  --db-path .test-runtime/terminal-pallet-summary/fixture.sqlite3 \
  --output .test-runtime/terminal-pallet-summary/fixture.json

EXTRUSION_DB_PATH="$PWD/.test-runtime/terminal-pallet-summary/fixture.sqlite3" \
  .venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8012

BASE_URL="http://127.0.0.1:8012" \
FIXTURE_JSON="$PWD/.test-runtime/terminal-pallet-summary/fixture.json" \
ARTIFACT_DIR="$PWD/artifacts/ui-checks/terminal-pallet-summary" \
  node scripts/verify_terminal_pallet_summary_ui.mjs
```

Run the server in a separate terminal, record its PID, and stop that exact
process with an ordinary interrupt after verification. The verifier checks both
`1366x768` and `1920x1080`, captures screenshots, verifies stale-card and
shift-stale takeover, limits browser requests to the configured loopback
origin, and compares before/after database snapshots for modal-only actions.

## Mandatory pre-rollout compatibility gate (deferred here)

This task did not inspect or audit a real backup. Immediately before a
production rollout, first create the normal SQLite-safe backup with the
repository's documented backup procedure. Never copy a live SQLite database
while the app might be writing. Copy the completed backup, once, to the narrow
temporary guard path and run the read-only auditor:

```bash
mkdir -p .test-runtime/terminal-pallet-summary-rollout
cp --no-clobber \
  /absolute/path/to/newest/sqlite-safe-backup.sqlite3 \
  .test-runtime/terminal-pallet-summary-rollout/production-backup.sqlite3
.venv/bin/python scripts/audit_terminal_pallet_summary_db.py \
  --db-path .test-runtime/terminal-pallet-summary-rollout/production-backup.sqlite3
```

The gate is acceptable only when integrity is `ok`, foreign-key violations are
zero, `visible_cards == ready + empty + error`, and `error == 0`. Its output is
counts only. Any nonzero `error` blocks rollout: investigate the affected
saved-roll invariant and use an approved production-data procedure before
trying again. Do not waive this requirement because the terminal summary fails
softly. The auditor accepts only an existing regular, non-symlink file below
this checkout's `.test-runtime/`, opens it read-only and immutable, and must
never be pointed at `data/`, `production-db/`, or a live database.
