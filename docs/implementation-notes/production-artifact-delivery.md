# Production Artifact Delivery — Implementation Note

Status: the September 14 base slice is merged into the current source. The
September 15 observability and deduplication refinement is source-complete,
verified, independently reviewed, integrated, and accepted with a disposable
copy of production data against the real test endpoints. Neither version has
been installed, enabled, accepted, or deployed in production.

## Implemented Boundary

Task 25 is an operational subsystem in this repository; it does not add UI or
database schema. Two one-shot jobs are launched by the existing four tracked
systemd units: a ten-minute SQLite backup producer and an approximately
one-minute delivery worker. Installing those units is a separate,
disabled-by-default operation after source deployment.

The shared pipeline consists of:

- `app.backups`: SQLite backup/validation, durable publication, local retention,
  and manual restore primitives;
- `app.backup_job`: producer handoff, upload-on-change decision, local image
  retention, and outbox publication;
- `app.artifact_outbox`: fixed-category durable queue, quarantine, and
  crash-safe cleanup;
- `app.artifact_delivery`: fixed-destination, create-only WebDAV delivery and
  delivery/freshness/summary orchestration;
- `app.backup_activity` and `app.backup_summary`: bounded atomic operational
  evidence and schedule state;
- `app.pipeline_notifications`: bounded incident state and confirmed Discord
  delivery; and
- `app.curl_transport` and `app.bounded_files`: no-shell subprocess and
  no-follow bounded-file boundaries.

The only artifact categories are `database-backups`, `shift-reports`, and
`completed-order-pdfs`. Only database backups have a producer in this slice.
Task 24 and the future completed-order feature own their PDF triggers, content,
and edition rules.

## Backup Producer And Local Durability

Every ten-minute producer run creates and validates a SQLite-safe local image.
The newest 144 final images remain under `/opt/extrusion-terminal/backups`,
including unchanged checks. Publication and retention directory mutations are
fsynced. Retention does not reopen all retained databases on every run, so the
first-enable runbook audits pre-existing matching files once.

Only a complete SHA-256 change from the last committed observation is queued.
A bounded `database-backup-handoff.json` binds an in-progress observation to
its local filename, human remote basename, stable queue item ID, digest, and
changed decision. A retry completes that exact handoff before observing newer
database state. Delivery will not consume the handoff's queue item while the
handoff remains active, closing the producer/delivery crash race.

The local producer image remains after enqueue. The outbox owns a separate
retry copy. Queue publication and state replacement use same-filesystem atomic
renames plus file/directory fsync. Pending, staging, cleanup, and quarantine
evidence is never silently expired.

## Remote Contract

The destination is fixed below:

```text
system-backups/extrusion-terminal/database-backups/<Sofia YYYY-MM-DD>/
system-backups/extrusion-terminal/shift-reports/
system-backups/extrusion-terminal/completed-order-pdfs/
```

New database objects use a readable Sofia timestamp and a 16-character content
identity, for example:

```text
extrusion-terminal_2026-09-15_14-20-00_8a363dadd2680c91.sqlite3
```

The UTC offset is added during Sofia's repeated autumn hour so two real instants
cannot receive the same readable basename. Legacy pending names containing the
complete SHA-256 remain readable and retryable.

Delivery issues only a bounded `MKCOL` for the exact daily child and a
conditional `PUT` with `If-None-Match: *`. HTTP `201` means created. HTTP `412`
is accepted only when the immutable filename matches the queued content
identity, under Task 25's tested sole-writer contract. There is no remote read,
listing, download, overwrite, rename, move, copy, deletion, or retention path.

Remote confirmation is durably checkpointed before local cleanup. The
invocation's final success/failure outcome is then recorded exactly once.
Queue-item IDs prevent a cleanup retry or matching `412` from incrementing
confirmed-upload counters twice. A recovery is green only after a failure-free
run leaves no pending or quarantined work.

## Alerts And Summaries

Routine successful checks are silent. Producer failures alert immediately.
Genuine WebDAV/transport incidents have a ten-minute grace period; local
configuration, queue, quarantine, state, and cleanup failures alert
immediately. Quarantine messages state that manual review is required and do
not claim automatic retry. Recovery reports only after the complete backlog
drains and includes the number of database uploads confirmed during the
incident.

The delivery worker also warns when the same server has recorded no validated
backup check for 30 minutes. This cannot detect a dead VM or total site outage;
external heartbeat monitoring remains outside Task 25.

A Sofia civil-time summary defaults to `09:00` and may be set to `off`, one
daily time, or two daily times through
`/etc/extrusion-terminal/backup-summary.conf`. It reports check/change/failure
counters, confirmed uploads, latest activity, and waiting work. Incident
messages take priority, and a delivery invocation sends at most one Discord
message. Ambiguous autumn slots belong to the first real occurrence; a skipped
spring slot becomes due at the first valid local instant after the gap.

## Bounds And Coordination

- delivery snapshot: at most 25 active entries, oldest first;
- latest WebDAV start: before 180 seconds;
- latest Discord start: before 410 seconds, otherwise persisted for retry;
- WebDAV: 10-second connect and 30-second folder/120-second upload bounds;
- Discord: 10-second connect and 30-second transfer bounds;
- backup service: five-minute ceiling; delivery service: ten-minute ceiling;
- backup schedule: every ten minutes; delivery schedule: approximately every
  minute.

Scheduled jobs share the operation lock non-blockingly. Installation,
deployment, and restore acquire the maintenance lock and then the operation
lock exclusively. The installer validates the exact clean accepted revision,
both protected curl configs, and the optional summary config before installing
the four units; success leaves both timers disabled. Deployment restores only
timers that were previously enabled, and failure leaves both disabled.

## Recovery And Deployment Status

Task 25 never downloads or restores a database. An authorized operator selects
a backup and uses the existing guarded manual restore procedure while the jobs
and application are quiescent under both locks.

The September 15 development endpoint exercise proved the historical base
slice's WebDAV create/idempotent-retry path, Discord failure/recovery messages,
and one automatic disposable backup/delivery cycle. That evidence predates the
upload-on-change, Sofia naming/routing, freshness, summary, grace, and handoff
refinement and therefore does not accept the refined behavior.

Final refinement source verification on 2026-09-16 completed without external
contacts or production mutation:

```text
Focused Task 25 suite:                 304 passed in 5.92 seconds
Full repository suite:                 1,819 passed in 263.69 seconds
Python compile/import checks:          passed
Installer/deployment shell syntax:     passed
systemd-analyze verify (four units):   passed
git diff --check:                      passed
Independent scoped re-review:          no Critical or Important findings
```

The final refinement review covered security/credential boundaries,
producer/delivery crash recovery, notification and summary state, operational
installation, and code/test quality. Its last five Important findings were
resolved before source acceptance: exact pending recount after confirmation
checkpoint failure, immediate alerting for mixed quarantine and remote
failures, complete durable incident evidence, bytecode-free installer
validation, and a runbook acceptance example that exercises the real backup-job
entry point and checks the Sofia timestamp prefix. Focused regressions cover
each correction. No Critical or Important finding remains open.

Two boundaries remain deliberate rather than source defects: Discord delivery
is at-least-once across an interruption after the remote service accepts a
message but before local confirmation is durable, and production installation,
acceptance, and enablement remain separate authorized operations.

Disposable refinement acceptance on September 16, 2026 used the protected test
Discord/WebDAV configuration and a copy of the September 14 database, never the
runtime application database:

```text
Focused refinement integration cases:      7 passed
Automatic validated database checks:       3 observed
Unchanged-content duplicate uploads:       0
Changed versions / initial uploads:         2 / 2
Accelerated scheduled summaries:           3 confirmed by the user
Delayed cloud warning:                     1 after the ten-minute grace
Queued files during the incident:          1 preserved
Recovery messages:                         1 after the queue drained
Total confirmed test uploads:              3
Remote objects confirmed by the user:      3 readable Sofia-named files
Downloaded SHA-256:                        05e00e4f636a625a29ab956fa1ffbf62b0afb094d8020608dfcaa892d9c639ab
Filename identity / local image match:      passed / passed
Downloaded SQLite integrity / FK check:    ok / zero violations
Scratch restore:                           passed, two test-event rows present
Production database/services:              untouched
```

The deliberately wrong-password timer test also established a test-procedure
constraint: do not leave the one-minute delivery timer running with bad
credentials. Repeated bad authentication triggered Nextcloud's temporary
brute-force protection and delayed the otherwise successful recovery. Future
acceptance must make one initial bad-credential attempt, pause delivery for the
grace period, make one controlled due attempt, then restore the valid config.

Migration: **none**. This work changes no application SQLite schema or stored
production meaning.

Deployment: **not deployed**. Production source deployment, protected
configuration, root-staged disabled installation, production acceptance, timer
enablement, and the first observed production cycle remain separate gates. The
operational authority is
`docs/production-artifact-delivery.md`; this note authorizes none of them.
