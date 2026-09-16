# Task 25: Production Artifact Delivery And Cloud Backup

Status: the first source slice was implemented, verified, and merged into the
current source on September 14, 2026. It covers only the shared delivery
pipeline, Discord pipeline alerts, automatic database backups, tracked one-shot
units, transactional disabled-by-default installer, and deployment/restore
locks. The September 15 source refinement implements and automatically verifies
upload-on-change behavior, Sofia-readable names and folders, quiet human
alerts, scheduled summaries, same-server producer freshness checks, and
crash-safe producer/delivery handoffs. Its separate disposable external
acceptance passed against the real test endpoints on September 16, 2026.
Neither slice has been installed, enabled, accepted, or deployed in production.

Authoritative design:
`docs/superpowers/specs/2026-09-14-production-artifact-delivery-design.md`

Current refinement design:
`docs/superpowers/specs/2026-09-15-backup-observability-and-deduplication-design.md`

First executable plan:
`docs/superpowers/plans/2026-09-14-production-artifact-delivery-and-backup.md`

Current refinement plan:
`docs/superpowers/plans/2026-09-15-backup-observability-and-deduplication.md`

## Purpose

Create one small, reusable way for the extrusion-terminal system to deliver
generated files to the configured Hetzner Storage Share. Database backups,
shift reports, and completed-order PDFs have different business rules and
triggers, but they must not duplicate credentials, remote-path handling,
failure retry, or notification behavior.

In this task, an artifact simply means a completed file that one producer wants
to preserve outside the production server.

## Approved Umbrella Boundary

Task 25 owns the shared infrastructure for:

- copying a completed source file atomically into a local pending outbox;
- routing only approved file categories to fixed Hetzner subfolders;
- uploading a new remote file without overwriting an existing remote path;
- retaining failed deliveries locally and retrying them later;
- recording pipeline failures and recoveries without notification spam;
- sending the first external notification through a Discord webhook; and
- providing source-controlled one-shot systemd services and timers for the
  current backup and delivery jobs.

Task 25 does not own the business logic or presentation rules used to create
future shift-report or completed-order PDF files. Each producer receives its
own detailed design and implementation plan when that producer is implemented.

## Shared Delivery Contract

Every producer supplies:

- one complete, closed source file;
- one allowlisted category;
- one unique immutable remote filename; and
- enough producer-owned identity in that filename to distinguish later
  editions where applicable.

The shared pipeline then:

1. copies the complete file into a staging directory;
2. records bounded metadata including category, size, checksum, filename, and
   queued time;
3. atomically publishes the queue item into the pending outbox;
4. ensures the exact Sofia-calendar daily child for database backups and issues a
   conditional create upload to the fixed remote category/day path;
5. removes only the disposable local outbox copy after confirmed delivery; and
6. leaves the producer's original local-retention policy unchanged.

The delivery code must not contain remote download, delete, rename, move, copy,
sync, or retention operations. Its only directory mutation is bounded `MKCOL`
for `database-backups/<Sofia YYYY-MM-DD>/`. A conditional create accepts only
HTTP `201` as a new object; `200` or `204` is a failure because it does not
prove creation.
A matching short-identity or legacy full-checksum `412` is accepted only as an
idempotent retry under the explicit assumption that Task 25 is the sole
automated writer of those names.
A conditional create must reject a pre-existing remote path, and every producer
filename therefore remains immutable.

The credentials may technically have broader capabilities at the storage
provider. The enforceable application boundary is that Task 25 source code and
its service commands expose only the approved create-only upload operation.

## Approved Remote Layout

The existing WebDAV account is `extrusion-backup`. Its tested base URL is:

```text
https://nx106226.your-storageshare.de/remote.php/dav/files/extrusion-backup
```

Task 25 uses this approved root:

```text
system-backups/extrusion-terminal/
```

The fixed child folders are:

```text
database-backups/YYYY-MM-DD/
shift-reports/
completed-order-pdfs/
```

The three category roots are provisioned manually. The worker creates only the
database backup Sofia-calendar daily child and never lists or deletes remote
content. The
separation is a business requirement. Hetzner sharing and permissions may
be configured independently for each folder. The application does not manage
Nextcloud users, groups, shares, or permissions.

Remote files are retained until an authorized person deliberately removes them
through Hetzner. The production application and Task 25 jobs perform no remote
cleanup.

## Local Outbox And Retention

The outbox is retry storage, not the authoritative production database and not
a replacement for producer-specific local retention.

- A failed delivery remains pending and is retried automatically.
- Pending files are never silently pruned by successful-backup retention.
- A successfully delivered outbox copy may be removed because the producer's
  source copy and the new remote object are separate from the queue copy.
- Malformed or structurally unexpected queue evidence is atomically quarantined
  outside active ordering, retained for inspection, and reported without
  starving later valid work. The same bounded quarantine rule applies to
  malformed delivered-cleanup tombstones and maximum-length name collisions.
- A prolonged remote outage may grow the pending directory. Task 25 reports
  the failure rather than deleting undelivered files to hide the condition.

Database backups retain their newest 144 final-name local images, approximately
three days at thirty-minute intervals. Every run creates and validates a local
SQLite-safe image, then compares its complete SHA-256 with the immediately
previous validated image. Only changed content is copied into the outbox and
uploaded. The first-enable runbook audits any pre-existing matching files
because steady-state retention does not reopen all 144 on every run. Remote
database-backup daily folders are append-only from the pipeline's perspective
and have no automatic retention.

A bounded durable producer handoff makes the create/validate/enqueue/activity
sequence resumable. A retry completes that exact observation, using the same
queue-item ID and remote name, before inspecting newer database state. Local
retention is applied only after the observation is committed. Delivery likewise
records each remote confirmation before local cleanup, preventing crash retries
from double-counting an upload.

## Subtasks And Ownership

### 25.1 Shared outbox and create-only delivery

Build the fixed-category filesystem outbox and one common WebDAV worker. Use
one-shot invocations rather than a continuously running daemon. A frequent
delivery timer drains a finite batch of pending work, while producers remain
independently triggered. A shared operation lock prevents scheduled jobs from
running against the checkout during a normal production deployment.

Status: implemented and source-verified in the first slice; production
installation and acceptance remain pending.

### 25.2 Discord pipeline notifications

Send human-readable Discord incident messages without routine per-check
success spam. Producer failures alert immediately. WebDAV incidents are silent
if they recover within ten minutes, alert once if they persist, and recover
only after a failure-free run drains the exact queue to zero. A separate
delivery-worker freshness check warns when validated producer checks stop for
90 minutes. A Sofia-time summary defaults to `09:00`, and can be disabled or
configured for one or two daily times. Keep local journal/state evidence and
retry pending notifications when Discord itself is unavailable.

The ten-minute grace applies only to remote WebDAV failures. Local
configuration, queue-health, quarantine, activity-state, and cleanup failures
are alertable immediately. Quarantined evidence blocks recovery until an
operator resolves it.

Email is a provisional later notification option. It is not part of the first
implementation plan.

Status: implemented and source-verified in the first slice; the real Discord
webhook is not configured or activated by source work.

### 25.3 Automatic production database backups

Run the existing SQLite backup API every thirty minutes and retain the newest 144
final-name local backups published after validation. Enqueue only when the
complete validated SHA-256 differs from the prior check, then let the common
delivery worker upload it under `database-backups/<Sofia YYYY-MM-DD>/`. New
remote names expose a readable Sofia timestamp and only the first 16 checksum
characters; queue metadata retains the full checksum and legacy pending
full-checksum names remain deliverable. During only the repeated autumn Sofia
hour, the readable name adds its UTC offset to prevent two distinct instants
from colliding. Unsafe raw copying of the live SQLite file remains forbidden.

The manual restore command and human-selected restore procedure remain the
recovery model. Task 25 does not automatically download or restore a database.

Status: implemented and source-verified as the first producer; its production
timer is not installed or enabled.

### 25.4 End-of-shift PDF producer

The PDF generated from the shift-end workflow will use the shared outbox and
the `shift-reports/` destination. Its roster, report contents, revision,
correction, and PDF-rendering behavior remain owned by the separate detailed
Task 24 discovery record. Task 25 does not reinterpret that feature or make its
current defaults implementation-ready.

Status: future producer; no implementation in the first Task 25 plan.

### 25.5 Completed-order PDF producer

The accepted existing operational-card print output is the source presentation
for the future completed-order PDF. The first printable completion creates
edition 1 automatically. A later successful save from Admin or Terminal that
actually changes PDF-visible data on a completed or archived card creates a
new corrected edition automatically. An unchanged save creates no edition.

The filename and the PDF itself must show the stable card/order identity,
edition number, and generation time. Earlier editions are preserved. No manual
"generate corrected report" action is permitted because it would be forgotten
operationally. Occasional deletion of unwanted intermediate editions, if ever
needed, is a manual Hetzner maintenance action outside the uploader.

Status: future producer; exact event detection, PDF renderer, edition metadata,
and correction coverage require a separate design and implementation plan.

## Failure Boundary

Task 25 can notify externally only while the production server can execute the
job and reach Discord. It covers failures such as:

- SQLite-safe backup creation or validation failure;
- failure to enqueue a completed file;
- Hetzner authentication, permission, HTTP, or connection failure; and
- a future producer explicitly reporting its own generation failure through
  the shared notifier.

If the complete server, site power, or all outbound connectivity is down, this
server cannot report its own absence. Whole-server heartbeat and availability
monitoring require an external system and are explicitly outside Task 25.

## Security And Secret Handling

- Keep all credentials and webhook URLs outside Git.
- Reuse the protected production WebDAV curl configuration at
  `/etc/extrusion-terminal/hetzner-webdav.conf` without printing its contents.
- Store the Discord webhook in a separate protected configuration file.
- Run the jobs as the existing production service user `sk`.
- Keep `/opt/extrusion-terminal` and the maintenance/runtime lock anchors
  root-controlled; give `sk` ownership only to the outbox/state children it
  must write.
- Execute privileged installation only from a root-owned temporary installer
  extracted from the exact reviewed commit. Suppress Git replacement objects
  and repository/object-selection environment overrides, recheck the clean
  exact checkout under the maintenance lock, and stage unit bytes from that
  same commit.
- Start curl with ambient configuration disabled and give every external call
  fixed connection, transfer, subprocess, and systemd runtime bounds.
- Never place passwords, application-device passwords, webhook tokens, or full
  authenticated URLs in logs, filenames, test fixtures, unit files, task
  records, or command-line output.
- Automated tests use fake transports and temporary filesystem paths. They do
  not contact Hetzner or Discord.

## Existing Functionality Reused

`app.backups.create_backup()` already:

- opens the source SQLite database read-only;
- uses SQLite's backup API while the application may be running;
- validates `PRAGMA integrity_check` and `PRAGMA foreign_key_check`;
- refuses unsafe or invalid restore cases; and
- keeps a bounded number of timestamped local backup files.

Task 25 wraps this primitive; it must not replace it with live-file copying or
change manual restore safety.

Production installation leaves both timers disabled. Separately authorized
disposable `201`, idempotent `412`, interrupted-PUT, and Discord acceptance must
pass before the verified units are enabled. An actual restore requires both
the maintenance and operation locks acquired in that order before timer-state
capture, both timers disabled, both one-shot services stopped/inactive, the app
stopped/inactive, and both locks held through restore validation and application
restart checks.

The WebDAV application-device connection, conditional create/idempotent retry,
the original Discord failure/recovery messages, UTC daily-folder creation, and one automatic
backup/delivery cycle were accepted on September 15 with disposable
development paths and timers. The development units were then removed.
That historical acceptance predates the observability, deduplication,
Sofia-routing, and summary refinement. A separate disposable exercise accepted
the refined behavior on September 16, 2026.
Production protected-config placement, unit installation, timer enablement,
and end-to-end production acceptance remain separately authorized operational
work.

## Explicitly Out Of Scope

- Task 18's independent sales/logistics dashboard;
- the detailed Task 24 roster and shift-report product design;
- detailed completed-order PDF generation logic in the first slice;
- email notifications in the first slice;
- whole-server or site heartbeat monitoring;
- automatic database download, restore, or failover;
- bidirectional synchronization;
- remote overwrite or automated remote deletion;
- USB backup destinations, warm standby servers, UPS work, and disaster-site
  recovery from the archived Task 13 discussion;
- public internet exposure of the FastAPI application; and
- any production installation or service activation without a separately
  authorized maintenance operation.

## First-Slice Success Criteria

The first slice is ready for source acceptance when:

- a temporary SQLite database produces a validated backup through the existing
  API;
- the original backup remains under the configured local 144-file retention;
- an immutable copy is queued under `database-backups`;
- the fake WebDAV integration proves create-only requests, overwrite refusal,
  `204` rejection, matching-content `412` retry handling, successful removal of
  only the disposable queue copy, and retry preservation on failure;
- notification tests prove one failure message, suppression while still
  failing, retry after notification-send failure, and one recovery message;
- source-controlled one-shot service/timer definitions schedule backups every
  thirty minutes and delivery independently, with finite runtimes and deployment
  coordination;
- tests never contact real external services or mutate the runtime database;
- the production runbook documents configuration, installation, observation,
  manual testing, disablement, and the unchanged manual restore path; and
- production remains unchanged until the user explicitly authorizes
  installation and enablement.

## Relationship To Earlier And Parallel Tasks

- Task 13 is closed and archived. Only its SQLite-safe periodic cloud-backup
  need is absorbed here; its broader resilience program is not.
- Task 18 remains completely independent.
- Task 24 remains the detailed shift-crew/report producer record and later
  consumes this delivery infrastructure.
- Task 20 remains a separate application feature. Task 25 is an explicitly
  approved operational prerequisite/workstream and does not authorize Task 20
  implementation.
- Task 69's successor MES is not a source of requirements for this bounded
  pipeline.
