# Task 25 Backup Observability And Deduplication Design

Date: 2026-09-15

Status: Approved by the user on September 15, 2026

Supersedes the database-backup naming, notification wording, recovery timing,
daily-folder timezone, and enqueue-every-run parts of
`2026-09-14-production-artifact-delivery-design.md`. All other boundaries from
that design remain in force.

## Goal

Keep the thirty-minute SQLite recovery-point check without uploading byte-for-byte
duplicate database images. Replace machine-oriented Discord output with quiet,
human-readable incident transitions and a configurable Sofia-time summary.

## Backup Check And Deduplication

The backup timer runs every thirty minutes. Each run:

1. creates a new SQLite-safe local image through `app.backups.create_backup()`;
2. validates SQLite integrity and foreign keys through the existing primitive;
3. calculates the complete SHA-256 of the validated image;
4. records the successful check even when the image is unchanged;
5. compares the digest with the immediately previous validated image;
6. enqueues the new image only when the digest changed; and
7. commits the completed observation before applying the existing newest-144
   retention policy.

Missing activity state is treated as the first changed image and is queued.
Invalid activity state is a visible producer failure; the newly validated local
image remains available and no prior image or pending item is removed.

The comparison is with the immediately previous validated image, not the most
recent remote object. If content changes from A to B and later back to A, the
second A is queued because it represents a new observed production state.

The producer records a separate durable handoff before creating the local
image. That record binds one observation to its backup filename, immutable
remote basename, stable queue-item ID, and—after validation—its complete
digest and changed/unchanged decision. A retry finishes that handoff before
observing newer database state. This prevents a crash between enqueue and
activity-state replacement from either duplicating a queue item or silently
skipping an A-to-B-to-A transition. The handoff is cleared only after activity
state and retention are durable. Retention cannot remove the prior comparison
image while a malformed or incomplete handoff is unresolved.

## Human-Readable Immutable Names

New database backup objects use one Sofia timestamp followed by the first 16
lowercase hexadecimal characters of their full content SHA-256:

```text
extrusion-terminal_2026-09-15_14-20-00_8a363dadd2680c91.sqlite3
```

The full SHA-256 remains in immutable queue metadata and is checked against the
queued payload before upload. The 16-character content identity keeps the
create-only retry name stable and is materially shorter than the previous
full-digest name.

Ordinary names use the form above. During only the repeated autumn Sofia hour,
the name also includes the local UTC offset so two distinct instants cannot
collide:

```text
extrusion-terminal_2026-10-25_03-30-00_utc+03-00_8a363dadd2680c91.sqlite3
extrusion-terminal_2026-10-25_03-30-00_utc+02-00_8a363dadd2680c91.sqlite3
```

Existing pending queue items whose names contain
`__sha256-<complete SHA-256>` remain readable and deliverable. New enqueue
operations create only the short-identity form. HTTP `412` is accepted only
when the immutable name contains either the matching legacy full digest or the
matching new 16-character prefix. Every other `412` remains a failure.

Remote database folders use the Sofia calendar date derived from the immutable
UTC queue timestamp:

```text
system-backups/extrusion-terminal/database-backups/YYYY-MM-DD/
```

Internal timestamps and persisted state remain UTC. Human-visible folders,
filenames, and Discord timestamps use `Europe/Sofia`; messages do not print a
timezone label or UTC offset.

## Operational Activity State

Activity and summary state are operational files under the existing Task 25
state directory. They do not change the application database schema.

Separate single-writer files prevent the backup and delivery one-shot services
from racing on one shared JSON document:

- `database-backup-activity.json` is written only by the backup producer;
- `database-backup-handoff.json` is the backup producer's bounded in-progress
  transaction record;
- `database-delivery-activity.json` is written only by the delivery worker; and
- `database-backup-summary.json` is written only by the delivery worker.

All four use bounded regular-file reads, exact schemas, atomic replacement,
directory durability, aware UTC timestamps, and monotonically increasing
counters. They record enough evidence to distinguish:

- a recent successful check with no database change;
- a changed image successfully queued;
- a producer failure;
- a confirmed database-backup upload;
- an active delivery interruption and the number uploaded while draining it;
- missing, never-run, invalid, or stale state; and
- summary counters since the last confirmed summary.

An empty outbox is not evidence that the backup producer is healthy.

The delivery activity includes a bounded set of remotely confirmed queue-item
IDs whose local cleanup has not yet been acknowledged. The worker durably
records a remote confirmation before removing the corresponding active queue
item, and acknowledges it after cleanup. Retrying a conditional `412` after a
crash therefore cannot double-count the same upload, while a cleanup failure
cannot produce a false recovery.

## Incident Notifications

Routine per-check success messages are disabled. Technical diagnostics remain
in the local system journal. Discord uses separate human headings for:

- `Database backup failed`;
- `Database backup recovered`;
- `Cloud backups delayed`;
- `Cloud backups recovered`; and
- `Database backup summary`.

Database creation or validation failure opens one incident and alerts on the
first failed run. Repeated failures update local evidence without repeating the
warning. Its first later successful validated check sends one recovery.

Remote WebDAV transport or response failure opens an incident immediately in
local state but has a ten-minute notification grace. Recovery within the grace
is silent. If the incident lasts at least ten minutes, send one warning and
suppress repetitions. If Discord was unreachable, keep the notification
pending. Local configuration, queue-integrity, quarantine, activity-state, and
cleanup failures are immediately alertable because waiting ten minutes cannot
make those local faults safe.

Successful upload of one delivery batch does not close a WebDAV incident while
any queue item remains. Recovery is recorded only when:

- the current delivery run has no delivery or queue-health failure; and
- the exact final pending count is zero.

The recovery message states that all waiting backups were uploaded and nothing
remains waiting. If no failure warning reached Discord, a qualifying incident
instead sends one combined interruption-and-recovery message. The delivery
activity file supplies the count uploaded while the incident drained.

Quarantined evidence is unresolved pending work for health purposes even
though it is kept outside active queue ordering. It blocks a green recovery
until an operator inspects and resolves it. Empty quarantine directories do
not count as evidence.

Messages use Sofia civil time formatted like `15 Sep 2026 at 05:42`. They omit
host names, raw component identifiers, ISO `Z` timestamps, key/value dumps, and
claims that a restore was performed. A bounded non-secret reason may appear in
a failure message; URLs and control characters remain sanitized.

## Producer Freshness

The delivery worker checks the producer activity after its normal upload work.
If an otherwise healthy producer has not recorded a successful validated check,
or its last success is at least 90 minutes old, the delivery worker owns a
separate `database-backup-freshness` incident. A known last success becomes
alertable when that 90-minute inactivity threshold is reached. Missing,
never-run, or unreadable activity begins a 90-minute observation grace on the
first delivery-worker observation. The delivery worker also
closes that incident after it observes a recent successful check. The backup
producer never writes the freshness incident file, avoiding a two-process state
race. An explicit producer failure remains covered immediately by the existing
`database-backup` incident and does not generate a second freshness warning.

This same-server freshness check detects a stopped backup timer or producer
while the delivery worker still runs. It cannot detect complete server, power,
or outbound-network failure. External dead-server monitoring remains outside
Task 25.

## Scheduled Summary

The existing minute delivery worker evaluates summary scheduling after urgent
failure/recovery notification work. No new daemon, service, or timer is added.

The optional bounded configuration file defaults to:

```text
summary_times=09:00
```

The only accepted values are `off`, one strict `HH:MM`, or two distinct strict
`HH:MM` values separated by one comma. The timezone is fixed internally to
`Europe/Sofia` and is not configurable. Invalid configuration is reported and
causes the delivery invocation to exit nonzero after preserving completed
upload work; it never prevents backup creation or corrupts incident state.

A summary is due on the first worker invocation at or after each configured
Sofia civil-time slot. Slot identity is the Sofia calendar date plus `HH:MM`,
which prevents duplicate sends in the repeated DST hour; the slot belongs to
the first occurrence of that civil time. A missed multi-day
schedule produces only the newest due summary after restart. Enabling or
changing the schedule preserves the last confirmed counter baselines, clears
any pending message for the old schedule, and arms the next future slot instead
of sending an unexpected historical summary immediately.

The summary reports:

- successful backup checks since the previous confirmed summary;
- changed database versions queued;
- confirmed Hetzner database-backup uploads;
- the latest successful check;
- the latest confirmed changed upload;
- the current exact pending count; and
- a clear warning when producer state is missing, failed, or older than 30
  minutes, or delivery is failing or still has pending work.

It never infers health from an empty delivery poll and never says data was
restored or is universally recoverable. A summary due during an active incident
is a warning summary. Pending incident notifications take priority over routine
summaries.

If an activity counter is lower than the last confirmed summary baseline, the
summary reports that count as unknown and keeps the higher baseline. It never
turns a state reset or rollback into a falsely healthy negative or zero delta.

Before sending, the worker atomically records the pending summary slot and its
counter snapshot. It marks the slot delivered and advances counter baselines
only after Discord confirms HTTP 200 with a saved message ID. A process crash
after Discord accepts but before the state replacement can cause one duplicate;
this at-least-once boundary is accepted, and the visible slot timestamp makes
the duplicate recognizable.

Pending counter fields preserve the evidence represented by the pending
message separately from the last confirmed-summary baselines. Activity that
occurs while Discord retries an older pending summary therefore remains
available to the next summary instead of being silently absorbed.

Summary-send failure remains summary state and local journal evidence. It must
not call incident success/failure functions or change backup/WebDAV health.

## Remote Mutation And Retention

The existing create-only boundary remains unchanged:

- exact allowlisted `MKCOL` for the Sofia database day folder;
- conditional `PUT` with `If-None-Match: *`;
- no remote `GET`, `HEAD`, `PROPFIND`, `DELETE`, `MOVE`, or `COPY`;
- no unconditional PUT; and
- no automatic remote cleanup.

Local retention remains the newest 144 validated images. Unchanged local images
may be retained inside that bounded set even though they are not enqueued.

## Verification And Development Acceptance

Automated checks must cover:

- unchanged content produces a validated check but no second queue item;
- changed content queues a new immutable object;
- A-to-B-to-A queues all three observed changes;
- missing and malformed activity state;
- producer crashes before validation, after enqueue, after activity commit, and
  during retention, with stable handoff replay and exact counters;
- new short names, legacy full names, conditional `412`, Sofia day folders,
  and the repeated DST hour;
- immediate producer failure, ten-minute WebDAV grace, silent brief recovery,
  failure suppression, undelivered combined recovery, and recovery only at
  exact queue zero;
- multi-batch backlog counting;
- remote confirmation before local cleanup, idempotent retry counting, and
  unresolved quarantine blocking recovery;
- recent, stale, never-run, failed, pending, and healthy summary rendering;
- `off`, one-time, two-time, invalid, schedule-change, missed-slot, DST fold,
  DST gap, summary retry, and urgent-notification precedence; and
- all existing WebDAV method and secret-redaction restrictions.

Development acceptance uses disposable units, state, outbox, database copy,
and test-labelled messages. It observes three real automatic backup checks,
three accelerated Discord summaries by reconfiguring the supported one- or
two-slot schedule between observations, one controlled WebDAV failure, local
backlog retention, full backlog recovery, remote file creation, and a manual
scratch restore. The disposable services remain in place until the user
confirms the results. Production installation and activation remain separately
unauthorized.

## Explicitly Out Of Scope

- per-backup Discord success messages;
- automatic remote deletion or quota management;
- remote reads or automated restore;
- external dead-server monitoring;
- email;
- Task 24 shift-report contents;
- completed-order PDF generation; and
- changes to the production application database schema.
