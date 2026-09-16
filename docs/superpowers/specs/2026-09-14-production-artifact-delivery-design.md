# Production Artifact Delivery And Cloud Backup Design

Date: 2026-09-14

Status: Approved and adversarially hardened on September 14, 2026

The filename, calendar-folder, upload frequency, Discord wording/grace,
activity-state, producer-freshness, and scheduled-summary parts of this design
are superseded by
`docs/superpowers/specs/2026-09-15-backup-observability-and-deduplication-design.md`.
The create-only transport, fixed-category outbox, retention, restore, and
production-authority boundaries remain in force.

## Goal

Build one bounded file-delivery pipeline that current database backups and
future PDF producers can reuse. Implement its first production use as a
ten-minute SQLite-safe backup copied to the Hetzner Storage Share, with local
retry and Discord failure/recovery notification.

The design deliberately separates producer logic from delivery logic. A
producer decides when and how to create a complete file. The pipeline accepts
that finished file and owns only safe local queuing, category routing,
create-only delivery, retry, and notification state.

## Approved Scope And Sequence

The umbrella contains three file producers:

1. production database backups;
2. end-of-shift PDFs; and
3. completed-order operational-card PDFs.

Only the database-backup producer is part of the first implementation plan.
The shift-report feature remains specified separately by Task 24. The
completed-order producer requires its own later detailed design. Their
existence influences the shared category and interface boundaries but does not
authorize speculative implementation of their business logic.

Task 18's interactive sales/logistics reporting work is independent and has no
relationship to this umbrella.

## Chosen Architecture

Use a filesystem outbox and a common one-shot delivery worker:

```text
producer-owned complete file
            |
            v
atomic local enqueue under an allowlisted category
            |
            v
periodic one-shot delivery worker
       |                   |
       v                   v
bounded daily-folder    Discord state notification
ensure + conditional PUT
       |
       v
fixed Hetzner category/day path
```

This was selected over two alternatives:

- Direct upload in every producer would minimize the first backup wrapper but
  duplicate credentials, remote paths, retries, and alerts in later features.
- A SQLite-backed general artifact registry would offer richer audit queries
  but introduce a migration and couple an operational file queue to production
  application data before that complexity is justified.

The filesystem outbox is sufficient because queue ownership is local to one
server, payloads are immutable, delivery is single-purpose, and a systemd
one-shot unit serializes normal worker execution.

## Component Boundaries

### Producer

A producer must finish and close its source file before enqueueing it. It owns:

- business trigger and validation;
- content generation;
- its stable business identity and edition rules;
- its authoritative local copy and retention; and
- reporting its own generation success or failure to the shared notifier.

The database producer calls `app.backups.create_backup()` and keeps its output
under `/opt/extrusion-terminal/backups`. The existing default keep count of 144
is retained.

### Outbox

The outbox copies a source file into a queue-item staging directory, calculates
SHA-256 and byte size, writes bounded metadata, and atomically renames the
complete directory into:

```text
/opt/extrusion-terminal/artifact-delivery/outbox/pending/<category>/<item-id>/
```

Each item contains exactly:

```text
payload
metadata.json
```

Metadata schema version 1 contains:

```json
{
  "schema_version": 1,
  "category": "database-backups",
  "remote_filename": "unique-immutable-name.sqlite3",
  "sha256": "64-lowercase-hex-characters",
  "size_bytes": 12345,
  "queued_at_utc": "2026-09-14T12:34:56Z"
}
```

Category and filename validation rejects path separators, dot segments,
control characters, unknown categories, and ambiguous names. The queue item ID
is generated locally and is not a business identifier. Staging and pending must
be on the same filesystem so publication is an atomic rename.

If enqueue fails, the incomplete staging directory is removed and no pending
item is published. The source file is never moved or deleted by the outbox.

### Category Routing

The exact category allowlist is:

| Category | Remote child folder |
| --- | --- |
| `database-backups` | `database-backups/<UTC YYYY-MM-DD>/` |
| `shift-reports` | `shift-reports/` |
| `completed-order-pdfs` | `completed-order-pdfs/` |

The remote base is the tested `extrusion-backup` WebDAV endpoint. All category
folders live beneath:

```text
system-backups/extrusion-terminal/
```

The three category roots are provisioned manually. For database backups only,
the worker derives one UTC `YYYY-MM-DD` child from immutable queue metadata and
issues bounded WebDAV `MKCOL` before upload. It accepts `201` or `405`, ensuring
the same child only once per delivery batch. The worker does not discover,
list, rename, move, share, or delete remote directories and cannot create an
arbitrary path.

### Immutable Naming And Idempotence

Every remote filename includes producer identity plus a full content SHA-256.
For the first database producer, preserve the existing timestamped backup stem
and append the checksum before `.sqlite3`:

```text
extrusion_terminal_20260914_123456_123456__sha256-<64 hex>.sqlite3
```

After ensuring the database backup's daily child, the worker sends one WebDAV
`PUT` with `If-None-Match: *`. It accepts only HTTP
`201 Created` as a newly created remote object. HTTP `200` or `204` is treated
as a failure because it does not prove that the server honored the create-only
contract; the queue item remains pending and the condition is reported.

HTTP `412 Precondition Failed` for the same deterministic queue item is treated
as an idempotent prior delivery because the remote filename contains the
complete source checksum. This relies on an explicit operational assumption:
Task 25 is the only automated writer of its checksum-bearing names. It supports
safe recovery when the original `201` response was lost without adding a remote
read. If another writer is ever allowed to create those names, this assumption
and the `412` handling must be redesigned. The worker never falls back to an
unconditional upload.

No Task 25 code path may issue WebDAV `GET`, `PROPFIND`, `DELETE`, `MOVE`,
`COPY`, or an unconditional overwrite. `MKCOL` is restricted to the exact
allowlisted database category and UTC day child. The server never pulls a
remote payload or restores one automatically.

### Delivery Completion

After confirmed create or idempotent prior delivery, the worker removes only
that queue item's `payload`, `metadata.json`, and now-empty item directory. It
does not remove the producer's source file.

On authentication, permission, HTTP, timeout, DNS, TLS, connection, malformed
metadata, size, or checksum failure, the item remains pending. Corrupt or
malformed local queue state is reported and retained for human inspection; it
is not uploaded or silently discarded.

The worker processes at most 25 items from one oldest-first snapshot. A file
queued while a run is active is safely left for that run or the next. It may
retain one malformed local item and continue with other snapshot items, but it
stops further upload attempts after the first WebDAV transport,
authentication, permission, or unexpected-response failure. Retrying every
queued item cannot make a shared remote outage recover faster.

The source-controlled systemd unit provides normal single-worker execution;
the outbox's atomic publication prevents the worker from seeing partial items.
Malformed active entries and malformed post-delivery cleanup tombstones move
intact to durable quarantine after bounded inspection. A quarantine collision
uses a bounded opaque destination name rather than extending an already
maximum-length source name. This preserves evidence without letting the same 25
malformed entries permanently starve later valid work.

## Transport Choice

Use the production VM's existing `curl` command through Python
`subprocess.run()` with an argument list and no shell. Every invocation places
`--disable` first so curl cannot load an ambient user `curlrc`, then loads only
the validated task-specific configuration. Each command has a fixed connection
timeout and total-transfer timeout, and the subprocess plus systemd service have
outer runtime bounds. This reuses the already tested protected curl
configuration at:

```text
/etc/extrusion-terminal/hetzner-webdav.conf
```

The WebDAV base URL and fixed remote root are non-secret source-controlled
configuration. The credential file remains outside Git and must not be printed
or copied into test fixtures. Automated tests inject a fake command runner and
assert the exact operation and status handling; they never call the real
service.

Because curl configuration files can contain options beyond credentials, the
code reads each configuration through a no-follow, direct-regular-file,
cap-plus-one descriptor boundary, then validates directive names before
invoking curl without logging directive values. The same bounded reader owns
queue-metadata and notification-state input. FIFOs, symlinks, devices, files
over the declared cap, and files that grow past the cap while being read are
rejected. The WebDAV file may contain only its required `user` directive. The
Discord file may contain only its required `url` directive, using the Discord
webhook HTTPS endpoint with confirmed-response `wait=true`. Options that could
change the URL, method, payload, output, redirect behavior, or transfer count
are rejected. This keeps the operation boundary in source rather than trusting
an arbitrary curl configuration.

## Discord Notification State

Discord is the first external notification channel. Email is a provisional
later extension, not part of this slice.

The webhook URL is stored in a separate mode-`0600` curl configuration outside
Git. The worker posts a bounded JSON message with `allowed_mentions.parse` set
to an empty list. Use Discord's confirmed-response mode so the command can
distinguish a saved notification from a failed request. Discord documents that
executing an incoming webhook can post content without a bot account and that
confirmed execution returns the saved result rather than fire-and-forget
behavior: <https://docs.discord.com/developers/resources/webhook>.

Notification state is persisted atomically per component under:

```text
/opt/extrusion-terminal/artifact-delivery/state/
```

The first slice has these components:

- `database-backup`; and
- `webdav-delivery`.

State transitions are:

```text
healthy -> failing: send one failure notification
failing -> failing: update local evidence; do not repeat a sent warning
failing -> healthy: send one recovery notification
healthy -> healthy: no notification
```

If Discord is unavailable, the pending notification remains recorded and is
retried on a later applicable run. Messages contain the component, category if
applicable, first-failure time, latest attempt time, bounded non-secret error,
pending item count, and production host name. They never contain credentials,
webhook URLs, application-device passwords, or authenticated URLs.

Local journal output and state remain required even when notification cannot be
sent. This system cannot report a dead server or complete site/internet outage
while it has no outbound path. External heartbeat monitoring is outside scope.

## Scheduling

Use source-controlled systemd definitions with `Type=oneshot`:

- a database-backup timer invokes the backup producer every ten minutes; and
- an independent delivery timer invokes the common worker every minute.

No continuously running delivery daemon is added. The minute worker makes
future event-produced PDFs deliver promptly without giving each future
producer its own upload service. A failed pending file is naturally retried by
later worker invocations.

Both services have finite `TimeoutStartSec` values. Their commands take a shared
filesystem operation lock while the normal deployment script takes the same
lock exclusively. Installer and deployment also serialize through a stable
root-protected maintenance lock. Deployment disables the schedules during its
mutable phase and restores only those previously enabled after final health and
revision checks; failure leaves them disabled. This prevents either service
from importing an unverified checkout. A timer run that cannot obtain the
operation lock exits without changing queued or source files and tries again on
its next normal interval.

The delivery worker starts no WebDAV request at or after 180 seconds, rechecks
that cutoff immediately before invoking curl, and starts no Discord request at
or after 410 seconds. Since the curl subprocess ceiling is 180 seconds, these
cutoffs leave a bounded margin inside the delivery service's 600-second limit;
a deferred notification remains pending for the next run. A cutoff reached
after confirmed upload progress defers the remainder normally; a cutoff with
zero upload progress is a component failure so a permanently expensive oldest
item cannot starve the queue silently.

The production user remains `sk`. Runtime paths are outside the Git checkout so
pending files cannot dirty the production worktree or be rejected by the
deployment script. Their anchor and lock files are root-controlled; `sk` owns
only writable outbox/state children. Installation leaves schedules disabled.
Timer enablement is a later authorized action after disposable acceptance.
Privileged installation executes a root-owned temporary installer extracted
from the exact reviewed 40-character Git commit. Both the launcher and
installer suppress Git replacement objects and repository-selection
environment overrides. The installer rechecks that the deployed checkout is
clean and exactly that revision after acquiring the maintenance lock, stages
unit bytes from the same accepted commit, and never executes the `sk`-writable
working-tree script as root.

## Database Backup Job

One backup run performs this order:

1. call `create_backup()` against the configured production database;
2. require its existing SQLite integrity and foreign-key validation;
3. retain the newest 144 matching final-name local images through existing
   behavior;
4. enqueue an immutable copy under `database-backups`;
5. record producer success or failure through the shared notification state;
6. exit nonzero on backup or enqueue failure so systemd also records failure.

Delivery remains a separate worker. A successfully queued database backup is a
successful producer run even if Hetzner is temporarily unavailable; delivery
owns that later failure and retry state.

The current backup primitive publishes a matching final name only after SQLite
validation and directory durability. Retention treats those final names as
publication evidence instead of reopening up to 144 databases every ten
minutes. Before first enablement, the runbook therefore performs a one-time
integrity/foreign-key audit of every pre-existing matching file; an invalid
legacy/manual file must be reviewed and moved outside the matching set rather
than silently deleted.

Backup creation and local retention must never prune the separate pending
outbox. The manual restore command remains unchanged and always uses a
human-selected local or manually downloaded backup. An actual production
replacement requires the maintenance lock followed by the exclusive operation
lock before timer-state capture or quiescence, both timers disabled, both
one-shot services and the app stopped/proven inactive, and both locks held
through restore validation and application restart checks.

## Future Producer Contracts

### Shift reports

Task 24 owns the shift/crew data, PDF contents, revision semantics, and
generation trigger. When implemented, its producer will enqueue a completed
PDF under `shift-reports`. Task 25 supplies no roster, report schema, or PDF
renderer.

### Completed-order operational-card PDFs

The future producer converts the accepted existing print output to PDF. It
creates edition 1 on printable completion, and creates a new corrected edition
after every successful Admin or Terminal save that actually changes data
visible in that PDF for a completed or archived card. No-op saves and changes
that cannot affect the PDF create no edition. Earlier editions remain visible,
with stable card/order identity, edition, and generation time in both filename
and document.

These rules ensure the outbox interface supports immutable revisions. Their
event detection, renderer, and edition persistence are not implemented by the
first plan.

## Failure And Recovery Behavior

- Backup validation failure: do not enqueue; retain any prior valid local and
  remote backups; record `database-backup` failure.
- Enqueue failure: leave the validated source backup intact; record
  `database-backup` failure.
- WebDAV failure: retain the complete queue item; stop further remote attempts
  for that run; record `webdav-delivery` failure; retry on the next minute
  worker.
- Lost acknowledgement after remote creation: retry the same checksum-bearing
  conditional name and accept the precondition response as prior delivery.
- Discord failure: retain notification state and local logs; retry without
  exposing the webhook URL.
- Recovery: send one recovery message for the affected component after its next
  success, then return it to healthy state.
- Local disk pressure during a long outage: keep pending payloads; expose the
  backlog count and failure. Do not silently discard undelivered production
  files.

## Data And Migration Assessment

The first slice adds no SQLite table and changes no stored production meaning.
Its state is operational filesystem state outside the runtime database. No
application database migration is expected.

Future shift-report or completed-order edition metadata may justify migrations,
but those decisions belong to their own approved designs and must use the
repository migration playbook at implementation time.

## Testing Strategy

Automated tests use temporary directories and temporary SQLite databases. They
cover:

- atomic enqueue and cleanup after injected failures;
- bounded regular-file reads at the exact cap and rejection of oversized,
  FIFO, symlink/device, and forced-short-read cases;
- category, filename, metadata, size, and checksum validation;
- source-file preservation;
- bounded daily-folder command construction, conditional create command
  construction, and the absence of every forbidden WebDAV method;
- suppression of ambient curl configuration, finite command/service timeouts,
  `201` creation, checksum-named `412` idempotence, `204` rejection, HTTP
  failure, and transport failure;
- pending retention and later retry;
- one Discord failure notification, duplicate suppression, notification retry,
  and one recovery notification;
- backup creation, 144-file local retention, enqueue, and failure exit status;
- systemd timer cadence and one-shot unit wiring;
- deployment-lock coordination between scheduled jobs and the production
  deployment script; and
- installer/runbook safety without contacting production services.

One bounded manual acceptance uses a disposable temporary database and a
disposable remote test name in `database-backups`. It confirms `201` on the real
conditional create, checksum-named `412` on its identical retry, and Discord
notification. A deliberately interrupted disposable PUT must then prove its
full retry receives `201`, rather than a `412` for a retained partial path.
Unexpected `200`/`204`, failed confirmation, or partial-path `412` blocks
activation. Timers are enabled only afterward. Tests and manual rehearsals must
never mutate the live runtime database.

## Operational And Authorization Boundary

Source implementation does not authorize production installation. After code
acceptance, an explicit maintenance operation must:

1. create the fixed remote category folder if absent (daily database children
   are created by the worker);
2. create and protect the Discord webhook configuration;
3. validate the already-protected WebDAV curl configuration without displaying
   its secret;
4. install and verify the source-controlled unit files with timers disabled;
5. run the disposable `201`/idempotent-`412`, interrupted-PUT, and notification
   acceptance checks;
6. separately enable the verified timers;
7. run one safe production backup job;
8. confirm the local file, pending/drained state, remote object, timer schedule,
   and journal output; and
9. rehearse manual restore only to a separate scratch database.

Disabling the timers stops new automatic work without deleting local backups,
pending queue items, remote objects, or production data.

## Explicitly Out Of Scope

- automatic remote cleanup or retention;
- remote download, restore, or failover;
- a general job framework, broker, worker daemon, or plugin system;
- a production-data schema migration in the first slice;
- Task 18;
- Task 24's detailed report functionality;
- completed-order PDF implementation in the first slice;
- email in the first slice;
- external heartbeat monitoring;
- USB/standby/UPS/disaster-recovery work preserved in archived Task 13; and
- public exposure of the FastAPI application.
