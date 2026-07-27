# Task 13: Production Backup And Recovery Resilience

Status: discussion paused on July 26, 2026. This document preserves the
decisions, recommended direction, failure scenarios, and open questions so the
backup design can resume later without repeating the full conversation.

## Purpose

Build production-ready backup and recovery infrastructure for the extrusion
terminal pilot. The goal is not only to create backup files, but to make the
business able to recover production data and continue work if the app, VM,
Proxmox host, physical server, storage, network, cloud sync, or power fails.

The accepted operating model is:

- maximum acceptable data loss: `0-10 minutes`;
- target recovery time: roughly `1-4 hours`;
- paper fallback is acceptable while recovery is underway;
- no full high-availability requirement for now;
- recovery should be simple enough to execute from a written runbook.

## Current Application State

The app already has a repo-local SQLite-safe backup primitive:

- `app.backups` creates timestamped SQLite backups using SQLite's backup API.
- Restore copies from a backup into a target database path and validates the
  restored database before replacing the target.
- Tests exist for backup creation, restore, retention, open source connection,
  missing backup refusal, failed restore safety, and avoiding mutation of the
  runtime database.

The remaining work is operational hardening:

- unattended scheduling;
- backup validation immediately after creation;
- metadata and checksums;
- redundant destinations outside the app VM;
- cloud copy;
- backup health visibility;
- failure alerts;
- restore drills;
- scenario-specific recovery procedures.

## Decisions Reached

### Backup Frequency

Backups should run every 10 minutes. Anything older than 10 minutes without an
expected reason should be treated as a failed backup condition, not merely as a
minor warning.

### Backup Destinations

Use multiple places:

1. **Inside the app VM** for quick local restores.
2. **USB drive attached to the Proxmox server** for recovery if the VM or its
   virtual disk is damaged.
3. **Cloud storage** for off-site recovery if the physical server or building is
   unavailable.
4. **Optional standby server over Tailscale** if later approved.

The cloud provider is not yet chosen. It may be Dropbox, Google Drive, OneDrive,
or similar. The design should treat cloud storage as a replaceable sync target
instead of baking one vendor into the application.

### Recovery Speed

The business can tolerate paper fallback during an outage. Recovery does not
need to be automatic or near-zero downtime. A practical target of one to four
hours is acceptable as long as data is safe and the procedure is clear.

### Emergency Server

There is currently no dedicated spare server. If the main server fails, another
LAN PC may be temporarily repurposed as the app server. The user can provide
access to both Linux and Windows machines for emergency recovery testing.

The recovery design should therefore support portable recovery:

- install or already have Python and the approved app release available;
- restore the latest valid backup;
- start the FastAPI server locally;
- point terminal/admin browsers to the temporary machine;
- prevent the old primary from later accepting writes until the situation is
  reconciled.

### Warm Standby Possibility

An external standby server is possible. It could run a VM, Proxmox, and
Tailscale on a different network but in the same Tailscale tailnet.

The safer model is warm standby:

- backup copies are already pushed to the standby while the primary is healthy;
- the standby has the approved app release already installed;
- the standby app service normally remains stopped;
- on primary failure, a manager activates the standby;
- the standby restores the newest valid backup and starts the app;
- operators switch to the standby URL or a stable DNS/proxy target is repointed.

Emergency recovery should not depend on running `git pull` after failure.
Production recovery should use the currently approved release, not whatever is
newest in a branch.

Fully automatic failover is not currently approved because it adds split-brain
risk: two servers could accept production writes at the same time. The preferred
future direction is manager-approved failover with clear checks.

## Recommended Architecture

### Normal Production Path

```text
Terminal/Admin browsers
        |
        v
App VM on Proxmox
        |
        v
SQLite database
```

### Backup Path

```text
SQLite-safe backup every 10 minutes
        |
        +--> App VM local backup directory
        +--> USB drive mounted by Proxmox or exposed safely to the app VM
        +--> Cloud sync target chosen later
        +--> Optional Tailscale standby server
```

Each backup should have:

- timestamp;
- source database path;
- backup path;
- file size;
- SHA-256 checksum;
- SQLite `PRAGMA integrity_check` result;
- SQLite `PRAGMA foreign_key_check` result if applicable;
- copy status for each destination;
- retained/pruned status;
- final health state.

### Scheduling

Use systemd timers on the app VM for the first implementation:

- app backup service every 10 minutes;
- copy/sync service after successful local backup;
- health check service that marks backup status unhealthy if the latest valid
  backup is older than 10 minutes plus a small grace period.

The existing app backup command should remain the core safe snapshot mechanism.
Raw file copying of a live SQLite database must not be used.

### Retention Direction

The exact retention policy remains open, but the likely pilot policy is:

- frequent 10-minute backups for recent days;
- daily snapshots for older history;
- keep enough local and USB history to recover from accidental deletion or data
  corruption discovered late;
- cloud retention should not be shorter than USB retention.

Retention must delete only known backup files in known backup directories and
must not remove unrelated files.

## Failure Scenarios To Cover

### App Process Fails

Expected response:

1. systemd restarts the app automatically;
2. operator refreshes `/terminal`;
3. manager verifies `/health`;
4. no restore is needed unless database corruption is detected.

### VM Fails But Proxmox Host Works

Expected response:

1. stop or isolate the failed VM;
2. create or repair the app VM;
3. restore the latest valid backup from USB or local Proxmox storage;
4. start app service;
5. verify `/health`, `/admin`, `/terminal`, representative cards, and printing.

### Proxmox Host Fails Temporarily

Expected response:

1. determine if host is rebootable;
2. if host returns quickly, verify VM and latest backup health;
3. if host does not return, use emergency PC or standby server restore.

### Physical Server Or Internal SSD Fails

Expected response:

1. switch production to paper;
2. recover from USB, cloud, or standby copy;
3. start temporary app server on another LAN PC or activate standby server;
4. point terminal/admin browsers to temporary server;
5. keep the old server offline until it can no longer accept writes.

### USB Drive Fails

Expected response:

1. local VM and cloud backups continue;
2. backup health must report USB copy failure;
3. replace USB drive and run a fresh backup/copy test;
4. do not continue pilot indefinitely without a working off-VM target.

### Cloud Sync Fails

Expected response:

1. local VM and USB backups continue;
2. backup health reports cloud copy failure;
3. fix account/tool/network issue;
4. verify cloud receives a new validated backup.

### Network Or Tailscale Fails

Expected response:

1. local app may continue on LAN if LAN works;
2. cloud or standby sync may pause;
3. local and USB backups remain mandatory;
4. recovery runbook must describe whether admin/terminal URLs change.

### Power Outage

Expected response:

1. paper fallback if the terminal and server lose power;
2. strongly consider a UPS for Proxmox server, network switch/router, and
   possibly terminal workstation;
3. if UPS is used, configure graceful shutdown before battery exhaustion;
4. after power returns, verify app service, database integrity, and latest
   backup health.

### SQLite Corruption Or Accidental Data Damage

Expected response:

1. stop app or prevent new writes;
2. identify last known good backup before corruption or mistake;
3. restore to a scratch database first;
4. inspect expected cards/totals;
5. only then restore production or recover manually from the scratch copy.

## Open Questions

- Which cloud provider and sync tool will be used?
- Will the USB drive be mounted on Proxmox and passed through to the VM, or
  mounted directly inside the app VM?
- What USB drive model/capacity should be purchased?
- Should a second USB drive be rotated off-site?
- What exact retention schedule is acceptable?
- Should backup health be visible only in developer diagnostics or also in the
  admin panel?
- What alerting method is acceptable: admin banner, local file/log, email,
  Telegram, or another channel?
- Should a warm standby server over Tailscale be included in the first
  production backup task or left as a later enhancement?
- If standby is included, should activation be manual or manager-approved
  semi-automatic?
- How should terminal/admin browsers switch during failover: manually entered
  URL, local DNS name, reverse proxy, or kiosk launcher config?
- What is the exact procedure to prevent split-brain when a failed primary
  comes back online after standby activation?
- Which Windows/Linux emergency PC should be used for restore drills?
- Should the repository include OS-specific emergency server scripts for Linux
  and Windows?
- What UPS hardware is available or should be purchased?

## Future Design Work

When this task resumes, the next design pass should decide:

1. concrete backup destinations and mount paths;
2. cloud sync tool and account model;
3. metadata/checksum file format;
4. retention policy;
5. health reporting surface;
6. restore rehearsal schedule;
7. emergency PC procedure;
8. optional Tailscale standby procedure;
9. exact runbook for every failure scenario above.

No app implementation should begin until those choices are approved.
