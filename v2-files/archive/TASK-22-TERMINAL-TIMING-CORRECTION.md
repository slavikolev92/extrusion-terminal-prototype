# Task 22 — Terminal Production-Time Correction

## Status

Complete in source as of August 25, 2026. The reviewed implementation is
pushed on branch `terminal-timing-correction` through commit `4635a3d`. It has
not yet been merged or deployed.

No schema migration or new dependency is required.

## Delivered Scope

- Operators can open `Производствено време` for running and paused cards and
  edit the productive interval ledger.
- Each interval has a start, optional/required end according to card state,
  calculated duration, and guarded in-app deletion.
- Pauses are implied by gaps between consecutive intervals. The UI calculates
  production time and total paused time; it does not store separate pause rows.
- A running card retains one final open interval. Paused cards contain only
  closed intervals. Adding an interval preserves the final open interval.
- Date and time controls use segmented, bounded numeric entry with
  `DD/MM/YYYY` and `HH:MM` behavior.
- Clicking Finish freezes the proposed stop instant before showing a review.
  Operators can review or edit timing, inspect the pallet-production summary,
  and then confirm.
- Confirm Finish applies the reviewed timing and the lifecycle transition in
  one transaction. Time spent reviewing does not extend production.
- Completed-card timing remains read-only on the terminal. Existing Admin
  historical correction remains separate.
- Awaiting-rewinding finalization retains its existing timing-preserving path.

## Validation And Data Safety

Backend rules reject malformed, impossible, future, ambiguous, overlapping,
non-positive, stale, foreign, or state-incompatible interval ledgers. An active
shift is required. Timing replacement is atomic, card-version checked, and
preserves rolls, shift links, materials, machine/queue data, pallet data,
rewinding data, imported fields, and unrelated card values.

The final review also fixed two independently identified lifecycle edges:

- a tokenless Finish race that could otherwise select the waiting-card branch
  before a concurrent status change; and
- stale cancelled-card recovery that needed to navigate back to the terminal
  rather than retain unavailable card details.

## Verification Record

- Full Python suite: 1,161 passed.
- Focused Python matrix: 317 passed.
- JavaScript tests: 21 passed.
- Python compile/import, JavaScript syntax, and `git diff --check`: passed.
- Fresh live Chromium verification: 56 assertion groups passed with no
  unexpected console errors, page errors, or failed requests.
- Temporary SQLite databases were used; the real runtime database was not
  mutated.

Detailed behavior, commands, audit findings, and browser evidence are recorded
in `docs/implementation-notes/terminal-timing-correction.md`.

## Completion Boundary

The feature implementation and review are complete. Remaining release work is
only repository integration and a separately authorized deployment. This task
does not close or expand any broader future order-finish review task.
