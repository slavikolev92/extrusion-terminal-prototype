# Unified Time Handling Design

Date: 2026-07-31

## Goal

Establish one explicit time contract for production timestamps across the
database, backend, admin interface, terminal interface, and printed operational
card:

1. the server and SQLite provide the authoritative current time;
2. production instants are stored and calculated in UTC; and
3. user-facing timestamps are displayed and edited in the Bulgarian civil time
   zone, `Europe/Sofia`.

This corrects the current print discrepancy without rewriting existing
production records. It also removes the accidental mixture of raw UTC,
Bulgarian local time, and browser-device time from user-visible surfaces.

## Current Behavior And Root Cause

Production actions already obtain their timestamps from SQLite through
`CURRENT_TIMESTAMP`. SQLite returns UTC, and the application stores those
values as `TEXT` in the canonical form `YYYY-MM-DD HH:MM:SS`. Timing durations,
ordering, overlap validation, optimistic versions, and terminal snapshot
signatures operate on those raw values.

The time source and persisted values are therefore already suitable. The
problem is inconsistent presentation:

- shift screens interpret stored timestamps as UTC and convert them to
  `Europe/Sofia`;
- print formatting reparses the same raw text but does not convert it, so the
  UTC wall-clock value is printed as though it were Bulgarian local time;
- several admin and terminal templates expose raw stored values;
- admin timing-correction forms currently treat their visible values as the
  same representation sent to the database; and
- the terminal's live shift clock is initialized from the browser device
  clock, even though persisted production actions use server/SQLite time.

The visible app can consequently appear correct while a paper export is two or
three hours behind, depending on daylight-saving time. This is a presentation
and input-boundary defect, not evidence that the stored instants are generally
wrong.

## Canonical Time Contract

### Authoritative current time

SQLite remains the authoritative source for timestamps that change production
state. Start, pause, resume, finish, shift start, shift end, and related actions
continue to call the existing database time helper inside their transaction.
Application-host and browser clocks must not determine persisted production
times.

The terminal may render a continuously moving clock in JavaScript, but it must
calculate that clock from a server-provided UTC sample and a measured offset.
The browser clock is only the local oscillator between server synchronizations.

### Storage and calculation

Persist instants as UTC text in the existing form:

```text
YYYY-MM-DD HH:MM:SS
```

The absence of a suffix is an existing schema convention, not an indication
that the value is local time. Code at storage boundaries must treat these
values as UTC. Existing SQL ordering, duration calculations, overlap checks,
status rules, optimistic versions, and snapshot signatures continue to use the
raw canonical values.

No timezone conversion may be applied inside duration or ordering logic.
Conversion happens only when a value crosses a user presentation or user input
boundary.

### User timezone

All production timestamps shown to operators and shift managers use the IANA
zone `Europe/Sofia`. This is an application rule and must not depend on the
Linux host timezone, browser timezone, locale, or daylight-saving offset in
effect when the software is deployed.

The IANA rules determine whether the display offset is UTC+02:00 or UTC+03:00
for the instant being shown. A fixed numeric offset is not acceptable.

## Shared Timekeeping Module

Add `app/timekeeping.py` as the single application-level conversion and
formatting boundary. It uses the Python standard library (`datetime` and
`zoneinfo`) and introduces no third-party dependency.

The module owns these responsibilities:

- strictly parse a canonical stored UTC timestamp;
- convert a UTC instant to `Europe/Sofia`;
- format ordinary admin and terminal displays;
- format the numeric date/time required by the print card;
- format the existing Bulgarian shift-screen date/time style;
- emit an unambiguous UTC value ending in `Z` for HTML `<time datetime>`;
- format an existing instant for an editable Bulgarian-local admin input; and
- parse a Bulgarian-local admin input back to canonical UTC.

Callers choose a named presentation formatter suitable for their surface. They
must not independently attach `tzinfo`, call `astimezone`, or duplicate string
formats in route, printing, or template helper code.

The accepted output forms are explicit:

- ordinary admin and terminal display: `DD.MM.YYYY HH:MM:SS`;
- printed operational card: `DD.MM.YYYY HH:MM`;
- shift interface: `D <Bulgarian month name> YYYY, HH:MM`;
- editable correction input: `YYYY-MM-DD HH:MM:SS`, with `+HH:MM` appended
  only when needed to disambiguate a repeated local hour; and
- HTML machine-readable value: `YYYY-MM-DDTHH:MM:SSZ`.

An absent optional display uses the surface's existing blank marker (`-` in
ordinary screens and the accepted empty placeholder in print). An editable
optional value uses an empty string.

Malformed nonempty stored timestamps are data-integrity errors. Shared helpers
must distinguish an absent optional value from an invalid present value. They
must not silently interpret malformed text as local time, substitute the
current time, or return the original raw string as if formatting succeeded.

## Presentation Boundaries

Route and print view models retain canonical fields and add distinct derived
values such as:

- `*_display` for visible Bulgarian-local text;
- `*_input` for editable correction-form values; and
- `*_iso_utc` for machine-readable HTML attributes.

Raw values must not be overwritten in dictionaries used for database
operations, ordering, terminal synchronization, or signatures. This separation
prevents presentation conversions from leaking into production logic.

The shared boundary applies to every user-visible production instant found in
the current application, including:

- operational-card start and stop times in print output;
- admin card-detail first-started, finished, created, and updated times;
- admin timing-ledger values and deletion confirmations;
- admin card-list updated times and import-list created times;
- terminal waiting and produced-history finish times; and
- shift start/end/current-time displays.

Existing shift formatting is folded into the shared module without changing
its accepted Bulgarian display style.

HTML `<time>` elements display Bulgarian-local text while their `datetime`
attributes contain the corresponding unambiguous UTC instant with a trailing
`Z`.

## Print Behavior And Failure Handling

The printed operational card converts the canonical UTC start and stop
instants to `Europe/Sofia` before applying its accepted numeric print format.
This directly fixes the reported paper-export discrepancy and handles both
standard and daylight-saving time.

If a timestamp required for an eligible print is present but malformed, print
generation must fail with an explicit user-visible validation error. Printing
an unconverted or fabricated time would create a misleading production record.
An absent optional timestamp may retain the print layout's accepted placeholder
where the domain permits the value to be absent.

Print eligibility does not change: only completed and archived cards may be
printed.

## Admin Timing Corrections

Timing corrections are the only current path where a person edits a production
instant, so they require a reversible boundary in both directions.

The normal input format remains familiar and second-precise:

```text
YYYY-MM-DD HH:MM:SS
```

Without an explicit offset, this means Bulgarian local time in
`Europe/Sofia`. The FastAPI form boundary validates and converts it to canonical
UTC before calling database-layer correction functions. Database functions
continue to accept UTC values; they do not become timezone-aware presentation
APIs.

An existing canonical UTC value must survive the complete operation unchanged:

```text
stored UTC -> Bulgarian correction input -> submitted form -> stored UTC
```

This is especially important because the global admin save path resubmits the
complete timing ledger, including unchanged rows.

### Daylight-saving transitions

A local time skipped during the spring transition does not identify an instant
and must be rejected with a clear validation message.

A local time repeated during the autumn transition identifies two possible
instants. A newly entered ambiguous value without an offset must be rejected
and the user instructed to add either `+02:00` or `+03:00`. The accepted
explicit form is:

```text
YYYY-MM-DD HH:MM:SS+HH:MM
```

The offset must be one that `Europe/Sofia` actually used for that local wall
time. An inconsistent offset is rejected rather than being treated as an
arbitrary fixed-offset timestamp.

When an existing UTC instant falls in a repeated local hour, its correction
input is rendered with the applicable explicit offset. This makes an unchanged
save lossless and unambiguous.

All validation occurs before the correction transaction mutates production
data. One invalid ledger value must reject the complete form and preserve every
existing segment.

## Server-Synchronized Terminal Clock

Add a `server_now_utc` field to the terminal snapshot. Its value is sampled
from SQLite in the same existing read transaction as the snapshot data. The
client computes the difference between that sample and its own clock, then
renders `Europe/Sofia` time from the adjusted instant.

The current ten-second polling cycle refreshes the offset. Offset refresh must
happen before the snapshot signature early-return so the clock is corrected
even when no production data changed.

`server_now_utc` is deliberately excluded from the snapshot signature. A
constantly changing current-time value must not force a full terminal render on
every poll or create false state-change notifications.

If polling temporarily fails, the clock continues from the last valid offset.
It is a display aid only; persisted actions remain server-authoritative.

## Explicit Exceptions

The following values are not production instants and are not converted by this
change:

- imported order and delivery dates, which are date-only business fields;
- the roll-change countdown, which is a browser-only workstation reminder and
  does not persist or print an event timestamp; and
- backup filename timestamps, which are operational identifiers rather than
  production-card fields.

These exceptions must be documented so they are not mistaken for gaps in the
time contract.

## Production Data And Migration Assessment

The latest available production snapshot was inspected read-only:

```text
production-db/extrusion_terminal_20260728_075318_093595.sqlite3
SHA-256: f3786bb80fa4bf6e99a50e1f0c918f8db766450af42e1d3d90ccb08b53e3f481
```

It passed SQLite integrity checking and contained migrations `M001` through
`M006`, 35 production cards, and 35 timing segments. The timing relationships
matched normal automatic capture: no correction indicators were found, every
segment start matched its creation time, and every closed segment end matched
its update time. No timing-marker or lifecycle inconsistency was found. The
snapshot hash was unchanged after inspection.

Those observations are consistent with the existing code path that obtains
automatic production timestamps from SQLite UTC. There is no evidence that the
snapshot contains Bulgarian-local values requiring reinterpretation.

Therefore:

- no schema migration is required;
- no data migration or timestamp rewrite is required;
- no new migration identifier is added;
- `app/schema.py`, `app/migrations.py`, and the runtime production database are
  not changed for this feature; and
- existing timestamps retain their instant and gain correct local
  presentation at output boundaries.

Rewriting existing timestamps would be riskier than the approved change
because it would shift already-canonical instants and could corrupt durations,
ordering, and audit history.

Before production deployment, take the normal SQLite-safe backup and verify at
least one known completed card in both the on-screen detail and printed output.
That is a deployment safeguard, not a prerequisite data transformation.

## Testing And Verification

Automated coverage must include:

- shared parsing and formatting in winter and summer offsets;
- a conversion that crosses Bulgarian midnight;
- leap-date handling;
- empty optional values and malformed required values;
- Bulgarian-local correction input converted to UTC;
- nonexistent spring-transition input rejection;
- ambiguous autumn-transition input rejection without an offset;
- valid and invalid explicit-offset input;
- exact UTC-to-input-to-UTC round trips, including the repeated hour;
- print start/stop conversion and explicit malformed-value failure;
- ordinary admin detail, list, import, timing-ledger, and confirmation displays;
- individual and global timing-correction conversion;
- atomic rejection of an invalid global correction form;
- terminal waiting and produced-history displays;
- reuse of shared formatting by shift screens;
- terminal snapshots containing `server_now_utc`;
- snapshot signatures remaining stable when only current time changes;
- JavaScript offset refresh before an unchanged-snapshot early return; and
- unchanged raw UTC ordering, timing duration, overlap, and concurrency rules.

The existing print fixture contains UTC-looking test timestamps whose current
expected output accidentally encodes the defect. Update the fixture or expected
values so assertions clearly state the canonical UTC input and expected
Bulgarian-local print time.

Run focused Python tests first, followed by the complete Python suite, Python
syntax/import checks, JavaScript syntax checking for changed scripts, and
`git diff --check`.

Because this changes visible admin, terminal, and print output, also run a
task-specific Playwright workflow against a temporary SQLite database. It must
cover at least one timestamp whose Bulgarian date differs from its UTC date,
exercise a normal correction round trip, and capture relevant screen and print
evidence under `artifacts/ui-checks/`. Browser verification must not open or
modify `data/extrusion_terminal.sqlite3` or a production snapshot.

## Documentation

Update these durable sources during implementation:

- `README.md` with the authoritative storage, display, input, and server-clock
  contract;
- `docs/implementation-notes/print-output-reference.md` with the print timezone
  rule and malformed-required-time behavior;
- `docs/implementation-notes/shift-management.md` with the shared formatter and
  server-synchronized clock rule; and
- a new `docs/implementation-notes/time-handling.md` with the conversion API,
  daylight-saving correction rules, explicit exceptions, and no-migration
  decision.

## Out Of Scope

- Changing the database timestamp representation or adding timezone columns.
- Rewriting or reinterpreting existing production records.
- Adding user-selectable timezones or locale preferences.
- Using browser time for persisted production events.
- Changing imported date-only fields into timestamps.
- Persisting the roll-change countdown.
- Renaming backups or changing backup scheduling.
- Redesigning the print card, admin workflow, terminal workflow, or timing
  ledger beyond the required time boundary and validation messages.
