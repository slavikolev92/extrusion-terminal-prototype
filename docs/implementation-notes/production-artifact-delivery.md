# Production Artifact Delivery — Implementation Note

Status: implemented and source-verified on branch
`task-25-production-artifact-delivery` on 2026-09-14. Not installed, enabled,
merged, externally accepted, or deployed in production.

## Implemented Boundary

- `app/bounded_files.py` owns no-follow, direct-regular-file, cap-plus-one
  reads for curl configuration, queue metadata, and notification state. It
  rejects oversized files before content allocation, rejects FIFOs/symlinks
  and devices, and completes legal short reads only through EOF or the bound.
- `app.backups` now creates each SQLite image under a non-retention staging
  name, validates and fsyncs it, atomically publishes the final name, fsyncs the
  directory, and only then applies local retention. Abrupt-process staging
  residue is reported and never counted in the final-name set.
- `app/artifact_outbox.py` owns fixed-category durable queue publication,
  bounded discovery, metadata/checksum validation, malformed-evidence
  quarantine, and crash-safe delivered-item cleanup.
- `app/curl_transport.py` owns the no-shell bounded subprocess boundary and the
  allowlisted curl-config parser.
- `app/pipeline_notifications.py` owns bounded atomic per-component incident
  state, pending-notification retry, and confirmed Discord webhook delivery.
- `app/artifact_delivery.py` owns fixed URL construction, conditional WebDAV
  creation, finite queue draining, internal network-start budgets, and separate
  artifact/notification outcomes.
- `app/backup_job.py` wraps the SQLite-safe backup primitive and enqueues the
  validated result without calling WebDAV.
- Four tracked systemd units schedule the backup producer and independent
  delivery worker. Installation is a disabled-by-default transaction, while
  normal deployment and actual restore coordinate through root-controlled
  maintenance and operation locks.

The only categories are:

```text
database-backups
shift-reports
completed-order-pdfs
```

Only `database-backups` has a producer in this slice. Task 24 and the future
completed-order producer retain ownership of their PDF triggers, contents, and
edition rules.

## Ownership, Persistence, And Recovery

The production database remains
`/opt/extrusion-terminal/data/extrusion_terminal.sqlite3`. Validated images are
published under `/opt/extrusion-terminal/backups`; the newest 144 matching
final names are retained. The current producer creates a final name only after
validation and durability. Steady-state retention treats that publication as
evidence instead of reopening all 144 databases every ten minutes, so the
first-enable runbook audits every pre-existing matching file.

The producer-owned backup remains after enqueue. The outbox payload is a retry
copy and is removed only after confirmed delivery. Queue publication copies to
same-filesystem staging, fsyncs payload and bounded schema-version-1 metadata,
and atomically renames the complete item into its allowlisted pending category.
Confirmed deliveries move atomically to cleanup before idempotent reaping.
Malformed or structurally unexpected evidence moves intact to quarantine so it
cannot starve valid work. The same rule covers malformed cleanup tombstones;
inspection stops after a third child and quarantine-name collisions fall back
to a bounded opaque ID. Pending, quarantine, and stale staging have no silent
automatic retention.

Actual database replacement remains manual. The production runbook acquires
the maintenance lock and then the operation lock before recording timer state
or quiescing anything; it proves both jobs and the app inactive and holds both
locks through restore validation and application restart checks.

## Remote Operation Contract

The destination is fixed at the `extrusion-backup` WebDAV base and:

```text
system-backups/extrusion-terminal/production-data/<category>/
```

Remote filenames carry the full lowercase SHA-256 digest. Delivery performs
one `PUT` with `If-None-Match: *`. HTTP `201` means created. A checksum-named
`412` means an idempotent prior delivery only under the approved sole-writer
contract and the required real interrupted-PUT acceptance result. HTTP `200`,
`204`, and all other statuses fail and retain the queue item.

There is no source path for remote discovery, read, download, overwrite,
directory creation, rename, move, copy, deletion, or retention.

## Bounds And Coordination

- delivery snapshot: at most 25 active queue entries, oldest first;
- WebDAV curl: 10-second connect and 120-second transfer bounds;
- Discord curl: 10-second connect and 30-second transfer bounds;
- shared curl subprocess: 180-second outer bound;
- latest WebDAV start: before 180 seconds, rechecked immediately before curl;
- latest Discord start: before 410 seconds, otherwise persisted for retry;
- backup service: five-minute bound;
- delivery service: ten-minute bound; and
- schedules: backup every ten minutes, delivery approximately every minute.

A cutoff after confirmed upload progress defers only the remainder. A cutoff
with zero upload progress records a delivery failure, preventing an expensive
oldest item from silently starving every later item.

Scheduled services take the operation lock shared/non-blocking. Installation,
deployment, and restore take the maintenance lock and then the operation lock
exclusively. The installer validates an exact clean accepted revision again
under the lock, stages the four unit blobs from that commit with Git replacement
objects disabled, installs transactionally, and leaves timers disabled.
Privileged execution uses a root-owned temporary installer extracted from that
same commit rather than the `sk`-writable working-tree script.

Deployment suppresses Git replacement/repository-selection overrides, disables
both schedules during mutation, checks installed units against the deployed
checkout, and restores only previously enabled timers. It confirms each
restored timer is both enabled and active; failure leaves both disabled.

## Notification State

The allowlisted components are `database-backup` and `webdav-delivery`.
Discord success requires HTTP `200` and a bounded JSON saved-message response
with a valid message ID. Redirects, malformed/empty responses, `204`, nonzero
curl, and oversized output remain pending failures.

One incident preserves its first and latest bounded errors. A sent failure is
suppressed while the incident remains open. If the failure warning could not be
sent before recovery, one `FAILED AND RECOVERED` message carries the evidence.
If that combined message also fails and the component fails again, the original
incident evidence remains open rather than being overwritten. A run that
reaches its work budget without an upload does not claim recovery. Notification
errors remain in bounded state and journal output without exposing URLs or
credentials. Discord-owned transport/confirmation failures retain a safe
actionable reason; arbitrary notifier exceptions remain class-only diagnostics.

The server cannot report its own complete absence. External heartbeat
monitoring remains outside Task 25.

## Verification

All automated work used temporary SQLite/filesystem paths, fake transports,
and fake systemd commands. No test contacted Hetzner or Discord, installed a
unit, changed a service, or mutated the runtime database.

Fresh source verification on 2026-09-14:

```text
Focused Task 25 and backup/recovery tests: 161 passed in 3.55 seconds
Python compile/import checks:             passed
Bash syntax checks:                       passed
systemd ten-minute calendar parse:        passed
systemd-analyze verify (four units):       passed
Forbidden WebDAV operation source scan:   passed, no matches
git diff --check:                         passed
Full repository test suite:               1,671 passed in 264.89 seconds
```

Independent post-hardening security, logic/data-integrity, and
quality/operations reports are stored under
`artifacts/task-25-post-hardening-review/`; their aggregate is the final review
record for this branch state.

## Migration And Deployment Assessment

Migration: **No migration.** This slice changes no production SQLite schema,
stored-data meaning, or application UI.

Deployment: **Not deployed.** Source review, commit/merge, app deployment,
protected Discord configuration, root-staged installer execution, disposable
real-service acceptance, timer enablement, and the first observed production
cycle are distinct approval gates. The operational authority is
`docs/production-artifact-delivery.md`; this note authorizes none of those
actions.
