# Task 23: Physical Pallet-Weight Entry

Status: implemented, verified, and accepted in source on 2026-09-11; not yet
deployed. The authoritative design is
`docs/superpowers/specs/2026-09-09-physical-pallet-weight-design.md`, and the
durable implementation record is
`docs/implementation-notes/physical-pallet-weight.md`.

## Delivered behavior

- Operators can enter or clear an optional physical transport-pallet weight for
  each numbered pallet directly in `Обобщение по палети`; Enter and blur save
  immediately. Shift managers can correct the same values from Admin.
- Values are positive, capped at `100.00 kg`, stored exactly as integer
  hundredths, and displayed with two decimal places. Blank means missing.
- Once any physical pallet weight exists for a card, completion requires a
  weight for every numbered pallet and a pallet assignment for every roll.
- Removing the last roll from a pallet removes its orphaned pallet-weight row.
- Pallet summaries, Finish Review, and print output distinguish roll gross,
  physical pallet weight, gross including pallet, and film net weight.
- Optimistic conflict checks, dismissal behavior, immediate persistence,
  rewinding lifecycle rules, and completed-card correction remain enforced.

## Data and deployment boundary

M007 creates the final `card_pallet_weights` table using integer hundredths.
M008 safely upgrades the earlier unshipped integer-tenths development schema;
fresh databases simply validate the final table. No historical weight is
inferred or backfilled. Production deployment requires the repository's
SQLite-safe backup, rehearsal, maintenance-window, verification, and rollback
procedure and remains separately authorized work.

## Acceptance evidence

The accepted source passed 1,521 Python tests, 66 JavaScript tests, syntax and
diff checks, SQLite integrity and foreign-key checks, and the guarded live
Playwright workflow at 1440×900, 1366×768, and 1093×614. That workflow included
exact `10.35` autosave/reopen behavior, finish enforcement, terminal/admin
correction, error recovery, accessibility, and mutation auditing. Generated
screenshots, databases, PDFs, and browser summaries were deleted after review;
they remain recoverable only through regeneration.
