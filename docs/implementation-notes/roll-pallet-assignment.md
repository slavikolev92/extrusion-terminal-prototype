# Roll Pallet Assignment

This note records the implemented, bounded pallet-attribution behavior for the
extrusion terminal pilot. It is not a pallet-management, label, or shipping
system.

## Persisted Model And M003

Migration M003, `roll_pallet_assignment`, adds two nullable columns:

```text
cards.current_pallet_number
roll_entries.pallet_number
```

Both columns are declared `INTEGER`, have no default, and permit only `NULL` or
a SQLite integer from `1` through `999`. The fresh schema has the same contract.
Startup validates declared type, null/default metadata, the exact constraint
semantics, and any persisted non-null values. A malformed partial or recorded
M003 schema fails initialization instead of being accepted as migrated.

M003 is schema-only. In legacy schemas where M003 adds the missing columns,
existing cards and rolls retain `NULL`; it does not infer or backfill historical
pallet assignments. A conforming valid partial M003 schema preserves any
existing valid pallet values, so the migration changes no existing value.
Existing status, assignment, queue position, version, timestamps, tare, gross,
net, shift attribution, timing, recipe/material actuals, and import-source data
remain unchanged. M003 runs within the migration runner's caller-owned
transaction/savepoint, so added columns and the migration record roll back
together on failure.

## Input And Snapshot Semantics

Pallet assignment is optional and scoped to one operational card. Pallet
numbers may contain gaps and are not normalized, incremented, or renumbered.

- `cards.current_pallet_number` is the current workflow value for future rolls.
- `roll_entries.pallet_number` is the snapshot copied when a roll is created.
- Changing the current value does not rewrite existing rolls.
- Correcting an individual roll does not change the current value.
- Deleting a roll and renumbering its surviving neighbors preserves each
  survivor's pallet snapshot.

The backend parser trims whitespace, accepts blank as `NULL`, and accepts only a
whole number from `1` through `999`. Invalid input returns the exact Bulgarian
message:

```text
Палетът трябва да бъде цяло число от 1 до 999.
```

Editable pallet fields use raw-preserving text controls with
`inputmode="numeric"`. This keeps the numeric keyboard hint without allowing an
HTML number control to normalize malformed text such as `15+1` before the
backend sees it. The backend parser and SQLite constraints are authoritative.

## Writes, Atomicity, And Conflicts

The terminal tare and current-pallet inputs form one coordinated autosave unit.
Submitting either dirty field sends both values with one loaded version and
saves them with one version increment. Both values are validated before the
write, so invalid pallet input or a stale version saves neither field. The
standalone tare and pallet routes remain compatible with older one-field
clients: an omitted field is preserved, while an explicitly blank submitted
field is cleared. The same card-status, active-shift, optimistic-conflict, and
post/redirect/get boundaries apply to every path.

A new roll copies the resolved current pallet in the same transaction as gross,
tare, net, shift occurrence, and card-version changes. Failed validation or a
stale version creates no roll and changes no pallet data.

Terminal and admin correction forms validate all submitted pallet and weight
values before their first roll write. Invalid pallet/weight input, a foreign
roll ID, or a stale card version saves none of that form. The admin global save
uses its caller-owned transaction, so failures also roll back imported-field,
recipe/material, tare, pallet, roll, timing, and version changes made by that
save attempt. Successful production edits increment the card version; stale
pages warn and require reload rather than silently overwriting newer data.

## Import Preservation

Current and per-roll pallet fields are terminal/admin production data. CSV
import and overwrite re-import continue to update only imported/front-card
fields. They do not add a pallet CSV field and preserve both pallet columns,
along with the established roll, tare, timing, status, assignment, and material
actual data.

## Finish Warning Boundary

Only saved rolls with a gross weight participate in the terminal finish-time
check.

- All blank pallet snapshots use the normal finish confirmation.
- All numbered pallet snapshots use the normal finish confirmation.
- Mixed numbered and blank snapshots use a Bulgarian confirmation that states
  the count of gross rolls without a pallet, with correct singular/plural text.

Choosing `Не` closes the dialog and makes no request or data change. Choosing
`Да` submits the unchanged finish operation. The warning is presentation-only:
blank or mixed pallet assignment is valid data and is not a backend finish or
print blocker.

## Operational-Card Summary

The print renderer derives pallet summaries from current saved gross roll rows
on every request. Numbered pallets sort numerically. Each row contains roll
count and gross/net sums with one-decimal formatting. A final `Без палет` row is
included only when numbered and blank assignments are mixed; an all-blank card
omits the pallet section entirely.

Page 2 retains the fixed 120-roll grid and blank `Дата / смяна` cells. Its lower
area contains the left production-summary block and two pallet blocks. The
measured current renderer capacities are 8 whole rows per page-2 pallet block
and 48 whole rows per overflow page. If more than 16 summary rows exist, page 2
shows no partial pallet summary and the complete summary starts on page 3.
Every overflow page repeats order number, customer, product, and the pallet
headings. See [Print Output Reference](print-output-reference.md) for the full
geometry and validation contract.

## Recovery, Deployment, And Rollback

M003 and the application code that reads/writes these columns must deploy
together after a SQLite-safe backup. M003 itself needs no production snapshot:
historical values deliberately remain `NULL`. The separate unresolved M001
legacy-data profile and final release-candidate rehearsal remain deployment
gates.

Do not hand-edit or drop M003 columns to roll back. If deployment must be
reversed, stop the application and restore the verified pre-deployment
SQLite-safe backup using the documented backup/restore procedure, then deploy
the matching prior application release. Account for any production data entered
after that backup before authorizing a restore.

## Explicit Boundary

This implementation does not provide package/pallet entities, cross-card roll
selection, capacity or closed state, automatic numbering, label routes,
barcodes, label void/reprint history, shipping/dispatch tracking, or a pallet
lifecycle. Those workflows require a separate approved design and data model.
