# Time Handling

## Canonical Storage And Source Of Truth

SQLite/server `CURRENT_TIMESTAMP` is authoritative for production and shift
actions. Start, pause, resume, finish, shift start, and shift end persist UTC
text in the existing canonical `YYYY-MM-DD HH:MM:SS` form. The missing suffix
is an existing storage convention; these values are UTC, not local wall time.
Ordering, duration calculations, overlap checks, optimistic versions, and
terminal signatures continue to use the raw canonical values without timezone
conversion. Host and browser clocks never determine persisted production time.

## Shared `app/timekeeping.py` API

`app/timekeeping.py` is the only application conversion and formatting
boundary and uses the standard-library `zoneinfo` database for
`Europe/Sofia`:

- `parse_stored_utc(value, required=False)` strictly parses canonical UTC and
  distinguishes an absent optional value from malformed stored data.
- `format_display_datetime(value, blank="-")` renders ordinary admin and
  terminal values as `DD.MM.YYYY HH:MM:SS`.
- `format_print_datetime(value)` renders printed values as
  `DD.MM.YYYY HH:MM`.
- `format_shift_datetime(value, blank="-")` renders the established Bulgarian
  shift style, `D <Bulgarian month> YYYY, HH:MM`.
- `format_utc_datetime_attribute(value)` emits an unambiguous
  `YYYY-MM-DDTHH:MM:SSZ` value for HTML `<time datetime>`.
- `format_sofia_input(value)` renders an existing instant for the editable
  Sofia-local correction field, adding an offset during a repeated hour.
- `parse_sofia_input(value, label=..., required=...)` validates Sofia-local
  input and returns canonical UTC text.

Malformed nonempty stored timestamps are data-integrity errors. Callers do not
fall back to raw text, reinterpret malformed text as local time, or substitute
the current time.

## Presentation Field Convention

View models preserve canonical fields and add separate presentation fields:
`*_display` for Sofia-local visible text, `*_input` for editable Sofia-local
correction values, and `*_iso_utc` for machine-readable UTC attributes. Raw
fields remain available to database writes, ordering, terminal synchronization,
and signatures and are never overwritten by a presentation conversion.

This convention covers print start/stop values; admin card detail, timing
ledger, deletion confirmation, card-list, and import timestamps; terminal
waiting and produced-history finish times; and shift start, end, and current
time displays. Printed and visible timestamps use `Europe/Sofia` regardless of
host or browser timezone.

## Admin Correction And DST Rules

Admin timing corrections are entered as Sofia local
`YYYY-MM-DD HH:MM:SS` and converted to canonical UTC before database correction
functions run. A skipped spring-transition value is rejected because it does
not identify an instant. A repeated autumn-hour value is rejected unless the
operator appends the applicable `+02:00` or `+03:00`; an offset inconsistent
with `Europe/Sofia` for that wall time is also rejected.

Existing UTC values in a repeated hour render with their applicable offset, so
`stored UTC -> Sofia correction input -> submitted form -> stored UTC` is exact.
All form values are validated before the correction transaction mutates any
segment, making a global timing-ledger rejection atomic.

## Terminal Server-Clock Synchronization

Every terminal snapshot contains `server_now_utc`, sampled from SQLite in the
snapshot read transaction. The browser measures an offset from that sample and
uses its clock only as an oscillator while rendering `Europe/Sofia` civil time.
The ten-second snapshot poll refreshes the offset before the unchanged-signature
early return. If a poll fails, the display continues from the last valid
offset; production writes remain server-authoritative.

`server_now_utc` is deliberately excluded from every snapshot signature. It
therefore causes neither a full rerender nor a state-change notification, and
it never participates in a production write.

## Explicit Date/Countdown/Backup Exceptions

Imported order and delivery dates are date-only business fields and are not
timezone converted. The roll-change countdown is a non-persisted browser-only
workstation reminder, not a production event timestamp. Backup filename
timestamps are operational identifiers, not production-card fields; this
feature does not rename backups or change backup scheduling.

## Production Snapshot Assessment

The latest available production snapshot was inspected read-only at
`production-db/extrusion_terminal_20260728_075318_093595.sqlite3`, with SHA-256
`f3786bb80fa4bf6e99a50e1f0c918f8db766450af42e1d3d90ccb08b53e3f481`.
SQLite `integrity_check` returned `ok`, `foreign_key_check` returned no rows,
and the snapshot contained migrations M001 through M006, 35 production cards,
and 35 production timing segments.

No correction indicators were found: every segment start matched its creation
time and every closed segment end matched its update time, with no timing-marker
or lifecycle inconsistency. The inspection hash remained exactly
`f3786bb80fa4bf6e99a50e1f0c918f8db766450af42e1d3d90ccb08b53e3f481`.
No snapshot value was modified during inspection.

## No-Migration Decision

The inspected values and existing SQLite timestamp path are consistent with
canonical UTC storage. This feature changes presentation and input boundaries
only: it requires no schema migration, production-data migration, or timestamp
rewrite. There is no M007 for this feature. `app/schema.py`,
`app/migrations.py`, `production-db`, and `data/extrusion_terminal.sqlite3`
remain unchanged. Existing stored timestamps retain their instant; shifting
them would corrupt durations, ordering, and audit history.

## Deployment Verification

Before rollout, take the normal SQLite-safe backup. Then choose one known
completed card and compare its admin detail with its print output, confirming
that both show the same `Europe/Sofia` civil time for the stored UTC instants.
This is a deployment-only safeguard, not a migration or data-transformation
step.
