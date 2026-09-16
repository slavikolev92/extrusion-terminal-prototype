# Task 25 Backup Observability And Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep ten-minute SQLite-safe checks, upload only changed database images, and provide quiet human-readable Discord incident and scheduled-summary behavior.

**Architecture:** Preserve the existing filesystem outbox, one-shot backup producer, one-shot delivery worker, protected curl transports, and create-only WebDAV boundary. Add separate single-writer operational activity files, a summary scheduler evaluated by the existing minute delivery worker, and backward-compatible short content identities for new remote names.

**Tech Stack:** Python 3.12, direct filesystem JSON state with atomic replacement, SQLite backup API, `zoneinfo`, systemd one-shot timers, curl WebDAV/Discord transports, pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-backup-observability-and-deduplication-design.md`

## Global Constraints

- Keep the backup timer at ten minutes and the delivery timer at approximately one minute.
- Keep the existing newest-144 local SQLite backup retention.
- Enqueue only a database image whose complete SHA-256 differs from the immediately previous validated image.
- Keep complete SHA-256 in queue metadata; new remote names expose exactly the first 16 lowercase hex characters.
- Accept and deliver both legacy full-checksum pending names and new short-identity names.
- Use `Europe/Sofia` for visible folder, filename, and message times; persist aware UTC timestamps internally.
- Send no per-backup success message.
- Alert a database producer failure immediately and a WebDAV failure only after a ten-minute grace.
- Declare WebDAV recovery only after a failure-free run leaves the exact pending count at zero.
- Default the summary to `09:00`; accept only `off`, one strict `HH:MM`, or two distinct strict `HH:MM` values.
- Add no daemon, broker, application database migration, remote read, remote overwrite, or automatic remote deletion.
- Never issue WebDAV `GET`, `HEAD`, `PROPFIND`, `DELETE`, `MOVE`, `COPY`, or unconditional `PUT`.
- Never expose credentials, webhook URLs, application-device passwords, or authenticated URLs.
- Tests use temporary SQLite databases and directories; they never mutate `data/extrusion_terminal.sqlite3`.
- Production installation, timer activation, and real production endpoint acceptance remain unauthorized.
- Do not stage or commit this refinement until the user explicitly asks; the existing untracked `TEMP - Task 20 requirements-spec.md` is never touched.

---

### Task 1: Backward-Compatible Human Remote Names And Sofia Day Folders

**Files:**
- Modify: `app/artifact_outbox.py`
- Modify: `app/artifact_delivery.py`
- Test: `tests/test_artifact_outbox.py`
- Test: `tests/test_artifact_delivery.py`

**Interfaces:**
- Consumes: metadata schema version 1 with complete `sha256` and `queued_at_utc`.
- Produces: `content_identity_filename(basename: str, suffix: str, digest: str) -> str`, `has_matching_content_identity(artifact: QueuedArtifact) -> bool`, and Sofia-derived database day routing.

- [x] **Step 1: Write failing naming and compatibility tests**

Add literal expectations proving that new enqueue produces:

```python
assert queued.remote_filename == (
    "extrusion-terminal_2026-09-15_14-20-00_"
    f"{digest[:16]}.sqlite3"
)
```

Add a fixture that rewrites one pending item's metadata and immutable name to
the legacy `__sha256-<64 hex>` form, then prove `load_queued_artifact()` still
loads it. Add rejections for a wrong 16-character prefix, an incomplete legacy
digest, uppercase hex, and an arbitrary same-length suffix.

- [x] **Step 2: Run the focused tests and confirm RED**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_artifact_outbox.py -q
```

Expected: failures show that enqueue still creates the full digest form and the
loader does not yet recognize the new short form.

- [x] **Step 3: Implement new-name creation with legacy reading**

In `app/artifact_outbox.py`, add:

```python
CONTENT_ID_HEX_LENGTH = 16

def content_identity_filename(basename: str, suffix: str, digest: str) -> str:
    stem = basename[: -len(suffix)]
    remote_filename = f"{stem}_{digest[:CONTENT_ID_HEX_LENGTH]}{suffix}"
    if len(remote_filename.encode("utf-8")) > MAX_REMOTE_FILENAME_BYTES:
        raise ValueError("Content-identity artifact name is too long for the remote store.")
    return remote_filename

def has_matching_content_identity(artifact: QueuedArtifact) -> bool:
    suffix = CATEGORY_SUFFIXES.get(artifact.category)
    if not suffix or len(artifact.sha256) != 64:
        return False
    return artifact.remote_filename.endswith(
        f"_{artifact.sha256[:CONTENT_ID_HEX_LENGTH]}{suffix}"
    ) or artifact.remote_filename.endswith(
        f"__sha256-{artifact.sha256}{suffix}"
    )
```

Use the new builder for enqueue. Use the shared matcher in metadata loading and
export it to delivery instead of maintaining a second filename rule.

- [x] **Step 4: Write failing Sofia folder and retry tests**

Add literal cases proving:

```python
# 21:30 UTC is already the next Sofia calendar day in September.
queued_at = datetime(2026, 9, 15, 21, 30, tzinfo=timezone.utc)
expected_child = "2026-09-16"
```

Add a fall-DST pair whose UTC instants render the repeated Sofia hour but whose
short content identities remain different. Prove `412` succeeds for matching
new and legacy identities, while mismatched identities never start curl.

- [x] **Step 5: Run the folder/retry tests and confirm RED**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_artifact_delivery.py -q
```

Expected: the day-boundary test still receives the UTC date and short-identity
retry is not yet accepted.

- [x] **Step 6: Implement Sofia routing and shared identity validation**

Parse `artifact.queued_at_utc` as aware UTC and convert it through:

```python
SOFIA = ZoneInfo("Europe/Sofia")
day = parsed.astimezone(SOFIA).date().isoformat()
```

Use `has_matching_content_identity()` both before upload and before accepting
HTTP `412`. Do not add any remote request method.

- [x] **Step 7: Verify Task 1**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_artifact_outbox.py tests/test_artifact_delivery.py -q
git diff --check
```

Expected: focused tests pass and no whitespace errors are reported.

---

### Task 2: Single-Writer Backup Activity And Upload Deduplication

**Files:**
- Create: `app/backup_activity.py`
- Modify: `app/backup_job.py`
- Modify: `app/backups.py`
- Test: `tests/test_backup_activity.py`
- Test: `tests/test_backup_job.py`

**Interfaces:**
- Consumes: `create_backup()`, `enqueue_artifact()`, and the Task 1 short-name contract.
- Produces:
  - `BackupActivity` with status, UTC attempt/success/change timestamps, last complete digest, and monotonic check/failure/change counters.
  - `load_backup_activity(state_dir: Path | str | None = None) -> BackupActivity`.
  - `record_backup_success(digest: str, *, changed: bool, state_dir=None, now=None) -> BackupActivity`.
  - `record_backup_failure(*, state_dir=None, now=None) -> BackupActivity`.
  - `sha256_file(path: Path) -> str`.
  - `remote_backup_basename(now: datetime) -> str`.
  - `run_backup_job(..., now: datetime | None = None) -> BackupJobResult`.
  - `BackupJobResult.queued_artifact: QueuedArtifact | None` and `BackupJobResult.database_changed: bool`.

**Implemented hardening:** activity schema version 2 adds an observation ID,
and a separate bounded `database-backup-handoff.json` binds a run to its local
filename, remote basename, stable queue-item ID, digest, and changed decision.
Retries finish that exact handoff before observing newer database state.
Retention is deferred until activity is durable. Schema version 1 activity
remains readable.

- [x] **Step 1: Write failing activity-state tests**

Create `tests/test_backup_activity.py` with hand-derived schema and transition
cases. The dataclass fields are:

```python
@dataclass(frozen=True)
class BackupActivity:
    status: Literal["never", "healthy", "failing"]
    last_attempt_at_utc: str | None
    last_successful_check_at_utc: str | None
    last_change_at_utc: str | None
    last_validated_sha256: str | None
    successful_checks_total: int
    failed_checks_total: int
    changed_versions_total: int
```

Prove missing state returns `never` with zero counters, success increments one
check, unchanged success preserves `last_change_at_utc`, failure increments only
the failed counter, later success restores healthy, malformed/oversized/symlink
state is rejected, and atomic replacement preserves the old file on failure.

- [x] **Step 2: Run activity tests and confirm RED**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_backup_activity.py -q
```

Expected: collection/import fails because `app.backup_activity` does not exist.

- [x] **Step 3: Implement bounded atomic backup activity**

Use schema version 2 with backward-compatible version 1 reading, exact key
validation, `_MAX_ACTIVITY_BYTES = 16 * 1024`,
`read_bounded_regular_file()`, a same-directory temporary file, `os.replace()`,
file `fsync`, and directory `fsync`. Require aware timestamps and complete
lowercase SHA-256. Do not share this writable file with the delivery worker.

Implement `remote_backup_basename()` as:

```python
local = now.astimezone(ZoneInfo("Europe/Sofia"))
return f"extrusion-terminal_{local:%Y-%m-%d_%H-%M-%S}.sqlite3"
```

- [x] **Step 4: Verify activity tests GREEN**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_backup_activity.py -q
```

Expected: all activity-state tests pass.

- [x] **Step 5: Write failing backup-job deduplication tests**

Add three real temporary-SQLite scenarios:

```python
first = run_backup_job(..., now=t0)
second = run_backup_job(..., now=t1)
assert first.database_changed is True
assert first.queued_artifact is not None
assert second.database_changed is False
assert second.queued_artifact is None
```

Then mutate committed SQLite content and prove a third run queues. Add A-to-B-to-A
using real SQL transactions and literal queue counts. Prove unchanged runs still
retain local images and advance successful-check activity. Prove malformed state
preserves the newly validated local image, does not publish a queue item, records
a producer incident when possible, and exits nonzero through `BackupJobError`.

- [x] **Step 6: Run backup-job tests and confirm RED**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_backup_job.py -q
```

Expected: the second unchanged run still queues and the result has no
`database_changed` behavior.

- [x] **Step 7: Implement deduplication after validation and before enqueue**

Capture one aware UTC `run_time` at job start and pass it to
`create_backup(timestamp=run_time)`. Begin or resume the durable handoff,
create or validate its exact local backup, hash it, and compare only with the
previously committed `last_validated_sha256` when the handoff has no recorded
decision.

When changed, call:

```python
queued = enqueue_artifact(
    backup_result.backup_path,
    "database-backups",
    outbox_dir=outbox_dir,
    remote_basename=remote_backup_basename(run_time),
    now=run_time,
)
```

When unchanged, set `queued = None`. Record successful activity only after a
required enqueue succeeds or an unchanged result is known. Preserve the local
backup in both cases. Keep component notification success/failure semantics.
Update CLI output to say either `Queued changed database backup` or
`Database backup validated; content unchanged and not queued`.

- [x] **Step 8: Verify Task 2**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_backup_activity.py tests/test_backup_job.py tests/test_backup_recovery.py -q
git diff --check
```

Expected: focused producer and existing recovery tests pass.

---

### Task 3: Human Incident Messages, Delivery Grace, And Full-Drain Recovery

**Files:**
- Modify: `app/backup_activity.py`
- Modify: `app/pipeline_notifications.py`
- Modify: `app/artifact_delivery.py`
- Test: `tests/test_backup_activity.py`
- Test: `tests/test_pipeline_notifications.py`
- Test: `tests/test_artifact_delivery.py`

**Interfaces:**
- Consumes: existing notification schema version 2 without adding keys.
- Produces:
  - `DeliveryActivity` in the delivery-worker-owned `database-delivery-activity.json`.
  - `record_delivery_run(*, confirmed_uploads, confirmed_item_ids, latest_backup_queued_at_utc, failed, pending_count, state_dir=None, now=None) -> DeliveryRunTransition`.
  - `acknowledge_confirmed_delivery_items(item_ids, *, state_dir=None) -> DeliveryActivity`.
  - `notification_grace: timedelta = timedelta(0)` keyword parameters on incident failure and success transitions.
  - delivery-worker-owned notification component `database-backup-freshness`.
  - human message rendering in Sofia time.

**Implemented hardening:** delivery activity schema version 2 keeps a bounded
set of remotely confirmed queue-item IDs until local cleanup is acknowledged.
This makes upload counters idempotent across crash/`412` retries. Unresolved
quarantine evidence blocks recovery. The ten-minute grace applies only to
remote WebDAV faults; local configuration, queue, state, quarantine, and
cleanup faults are immediately alertable.

- [x] **Step 1: Write failing delivery-activity tests**

Use these result fields:

```python
@dataclass(frozen=True)
class DeliveryRunTransition:
    activity: DeliveryActivity
    recovered: bool
    recovered_upload_count: int
```

Prove a first failed run opens an incident and counts any earlier uploads in the
same batch; later successful partial batches add to the incident count without
recovering; only a failure-free zero-pending run recovers and returns the full
count; normal healthy empty polls do not invent uploads. Prove exact schema,
bounded reads, atomic writes, and single-writer file location.

- [x] **Step 2: Run delivery-activity tests and confirm RED**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_backup_activity.py -q
```

Expected: delivery activity interfaces are absent.

- [x] **Step 3: Implement delivery activity**

Persist UTC timestamps, `status`, `last_successful_run_at_utc`,
`last_confirmed_upload_at_utc`, `last_confirmed_backup_queued_at_utc`,
`confirmed_uploads_total`, `failed_runs_total`, and
`active_incident_upload_count`, plus a bounded collection of confirmed but not
yet locally removed queue-item IDs. Only the delivery worker writes this file.
Validate all counters as non-negative integers and all timestamps as aware UTC.

- [x] **Step 4: Write failing grace and human-message tests**

Cover:

- WebDAV first failure at `00:00Z`, repeated failure at `00:09Z`, and recovery
  before ten minutes produce no Discord message.
- Failure still present at `00:10Z` produces exactly one warning.
- Repeated failures after warning produce no duplicates.
- A failed Discord attempt followed by recovery produces one combined message.
- Database producer failure uses zero grace and alerts immediately.
- Messages contain friendly headings and Sofia-rendered dates, and omit
  `host=`, `pending_count=`, component codes, ISO `T`/`Z` timestamps, webhook
  values, and URLs.
- `database-backup-freshness` renders as a human database-backup-process
  warning rather than exposing its component code.

Pass the same grace to failure and recovery:

```python
WEBDAV_FAILURE_GRACE = timedelta(minutes=10)
```

- [x] **Step 5: Run notification tests and confirm RED**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_pipeline_notifications.py -q
```

Expected: first WebDAV failure still sends immediately and messages remain
machine-oriented.

- [x] **Step 6: Implement grace without changing the version-2 state schema**

Determine incident age from `first_failed_at_utc`. Before grace expiry, persist
failure evidence but do not set `notification_attempted_at_utc`. On recovery:

- close silently when the incident ended before grace and no send was attempted;
- send normal recovery when the warning was confirmed;
- send combined interruption-and-recovery when the incident met grace but no
  warning reached Discord.

Render component-specific multiline messages. Use bounded sanitized error text
only in failures; keep raw diagnostics in journal output.

- [x] **Step 7: Write failing full-drain delivery tests**

Queue more than `MAX_DELIVERY_ITEMS_PER_RUN`, start from a persisted failing
incident, and prove the first successful batch leaves the incident failing and
sends no recovery while `pending_count > 0`. Prove the final batch sends exactly
one recovery with the accumulated upload count. Add a failure-during-drain case
and an empty healthy poll that sends nothing.

- [x] **Step 8: Run delivery tests and confirm RED**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_artifact_delivery.py -q
```

Expected: current `created_count` logic closes the incident after the first
successful partial batch.

- [x] **Step 9: Integrate delivery state and corrected transitions**

After the exact final queue snapshot, call `record_delivery_run()` once. Then:

```python
if failed_count:
    record_component_failure(..., notification_grace=WEBDAV_FAILURE_GRACE)
elif pending_count > 0:
    retry_pending_notification(...)
else:
    record_component_success(
        ...,
        notification_grace=WEBDAV_FAILURE_GRACE,
        context={"recovered_upload_count": transition.recovered_upload_count},
    )
```

Include both `created` and idempotent `already-present` database objects in
confirmed upload totals. Do not count PDFs as database uploads. Preserve the
existing network time budgets and return nonzero on state failure.

- [x] **Step 10: Verify Task 3**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_backup_activity.py tests/test_pipeline_notifications.py tests/test_artifact_delivery.py -q
git diff --check
```

Expected: incident, delivery, and security-boundary tests pass.

---

### Task 4: Configurable Sofia Summary And Producer Freshness

**Files:**
- Create: `app/backup_summary.py`
- Modify: `app/artifact_delivery.py`
- Test: `tests/test_backup_summary.py`
- Test: `tests/test_artifact_delivery.py`

**Interfaces:**
- Consumes: backup and delivery activity readers from `app.backup_activity`, exact pending count, and `NotificationSender`.
- Produces:
  - `load_summary_times(path: Path | str | None = None) -> tuple[time, ...]`.
  - `maybe_send_backup_summary(*, state_dir, pending_count, notifier, now=None, config_path=None, urgent_notification_pending=False) -> BackupSummaryResult`.
  - `check_backup_freshness(*, state_dir, notifier, now=None) -> NotificationResult | None`, which is called and persisted only by the delivery worker.

**Implemented hardening:** schedule changes preserve confirmed counter
baselines while discarding an old pending slot; counter regression renders an
explicit unknown value without lowering the baseline. The repeated Sofia hour
maps to one slot at its first occurrence. An active explicit producer incident
suppresses a duplicate freshness incident.

- [x] **Step 1: Write failing strict-configuration tests**

Test missing configuration defaults to `(time(9, 0),)`. Accept literals:

```text
summary_times=off
summary_times=09:00
summary_times=09:00,21:00
```

Reject empty values, extra keys/lines, duplicates, whitespace ambiguity,
seconds, invalid hours/minutes, more than two times, oversized files, symlinks,
FIFOs, and invalid UTF-8. Read from the fixed default
`/etc/extrusion-terminal/backup-summary.conf`, with an environment override only
for test/disposable operation.

- [x] **Step 2: Run configuration tests and confirm RED**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_backup_summary.py -q
```

Expected: import fails because `app.backup_summary` does not exist.

- [x] **Step 3: Implement strict bounded configuration and slot selection**

Use `read_bounded_regular_file()` with a 1 KiB cap and strict ASCII parsing.
Represent slot IDs as `YYYY-MM-DD/HH:MM` in Sofia civil time. On missing or
changed schedule, atomically arm the next future slot and send nothing. Once
initialized, choose only the newest due slot; never replay multiple missed
slots. The repeated DST hour has one slot ID, while a skipped wall time becomes
due at the first later worker invocation.

- [x] **Step 4: Write failing summary-state and rendering tests**

Cover:

- `off`, one daily slot, and two independent daily slots;
- same-slot rerun sends exactly once;
- schedule change arms the future rather than sending history;
- multi-day downtime sends only the newest due slot;
- Sofia winter/summer conversion plus DST fold/gap behavior;
- missing/never-run activity renders warning/unknown, not healthy;
- malformed or unreadable activity renders a warning with unknown counters and
  preserves the invalid evidence rather than producing a green summary;
- failed or 30-minute-stale producer renders warning;
- active delivery incident or nonzero queue renders warning;
- recent healthy check plus zero queue renders success;
- counter deltas advance only after confirmed Discord delivery;
- failed Discord send retries the same pending slot and baseline;
- a simulated crash window may duplicate but never marks an unsent summary done;
- all message times omit timezone labels and machine-oriented keys.

The healthy message must include literal human labels for checks, changed
versions, confirmed uploads, latest check, latest uploaded change, and waiting
items. It must not claim a restore or universal recoverability.

- [x] **Step 5: Run summary tests and confirm RED**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_backup_summary.py -q
```

Expected: scheduling, persistence, and rendering behavior is absent.

- [x] **Step 6: Implement separate atomic summary state**

Persist exactly one delivery-worker-owned `database-backup-summary.json` with:

```python
schema_version
schedule_signature
initialized_at_utc
last_delivered_slot
pending_slot
pending_message
baseline_successful_checks_total
baseline_failed_checks_total
baseline_changed_versions_total
baseline_confirmed_uploads_total
pending_successful_checks_total
pending_failed_checks_total
pending_changed_versions_total
pending_confirmed_uploads_total
```

Write pending slot/message and its evidence snapshot before invoking Discord.
After confirmed send, clear pending and advance baselines. Summary send failure
must never call `record_component_failure()` or `record_component_success()`.

- [x] **Step 7: Implement producer freshness check**

Use `PRODUCER_STALE_AFTER = timedelta(minutes=30)`. Known healthy activity
alerts when its last success reaches that threshold; the inactivity interval
itself is the grace. Missing, never-run, or unreadable activity starts a
30-minute observation grace on first observation. Recent healthy activity
closes the delivery-worker-owned `database-backup-freshness` incident. Explicit
`last_status == "failing"` remains owned by the producer's immediate
`database-backup` incident and must not create a second freshness warning.
Never-run activity starts the freshness grace on first observation rather than
alerting immediately. Only the delivery worker writes freshness state, so the
two one-shot services never race on that component file.

- [x] **Step 8: Integrate summary after urgent delivery notification work**

Pass one captured aware UTC `now` through delivery, incident, freshness, and
summary calls. Attempt at most one Discord message from a delivery invocation,
with priority `WebDAV incident -> producer freshness -> routine summary`.
Defer lower-priority work whenever a higher-priority failure/recovery notice is
pending or was attempted in the current run. Evaluate the summary only after
upload work and exact pending-count collection. Preserve completed uploads if
configuration or summary state fails, surface the bounded error in
`DeliveryBatchResult`, and return nonzero from the CLI.

- [x] **Step 9: Verify Task 4**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_backup_summary.py tests/test_artifact_delivery.py tests/test_pipeline_notifications.py tests/test_backup_job.py -q
git diff --check
```

Expected: summary, freshness, integration, and prior incident behavior all pass.

---

### Task 5: Operations, Durable Documentation, And Complete Verification

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `v2-files/TASK-25-PRODUCTION-ARTIFACT-DELIVERY.md`
- Modify: `docs/superpowers/specs/2026-09-14-production-artifact-delivery-design.md`
- Modify: `docs/production-artifact-delivery.md`
- Modify: `docs/implementation-notes/production-artifact-delivery.md`
- Modify: `docs/superpowers/plans/2026-09-14-production-artifact-delivery-and-backup.md`
- Modify: `tests/test_artifact_delivery_operations.py`

**Interfaces:**
- Consumes: completed Tasks 1-4 behavior and unchanged systemd service/timer count.
- Produces: one consistent source/operations contract and reproducible development-acceptance instructions.

- [x] **Step 1: Write failing operations-contract tests**

Extend behavioral operations tests to validate the summary configuration through
the application parser and prove the tracked systemd topology remains exactly
the existing backup service/timer plus delivery service/timer. Test commands
must use disposable config/state paths and must not contact Discord or Hetzner.

- [x] **Step 2: Run operations tests and confirm RED**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_artifact_delivery_operations.py -q
```

Expected: new config-validation behavior/documented invocation is absent.

- [x] **Step 3: Add a no-network summary-config validation command**

Expose:

```bash
python -m app.backup_summary validate-config
```

It prints only the normalized setting (`off`, `09:00`, or `09:00,21:00`) and
never reads curl credential files or starts a network request. Invalid config
prints a bounded error and exits nonzero.

- [x] **Step 4: Update durable documentation consistently**

Record:

- ten-minute validated checks and upload-on-change behavior;
- newest-144 local retention;
- Sofia day/name/message rendering with UTC internal state;
- short content identity plus legacy pending-item compatibility;
- immediate producer failure, ten-minute cloud grace, full-drain recovery;
- default daily `09:00` summary and strict optional config file;
- 30-minute same-server producer freshness check and external-monitor limit;
- no extra daemon or systemd unit;
- unchanged create-only/no-read/no-delete boundary;
- development acceptance passed only after Task 5's live checks; and
- production remains uninstalled/unaccepted until separately authorized.

Mark the original design/plan naming and notification sections as superseded by
the September 15 refinement rather than silently rewriting historical evidence.

- [x] **Step 5: Run all automated verification**

Run:

```bash
source .venv/bin/activate
python -m compileall -q app tests
python -m pytest
git diff --check
git status --short
```

Expected: the complete suite passes; only this plan's tracked files plus the
pre-existing untracked Task 20 file appear.

- [x] **Step 6: Perform disposable development acceptance**

Using only the previously authorized test WebDAV/Discord configuration, a copy
of the September 14 production database, disposable user units, disposable
state/outbox, and `TEST`-labelled summaries:

1. configure one or two future summary slots, then reconfigure after an
   observation to produce three accelerated summaries within the supported
   contract;
2. observe three automatic safe backup checks;
3. confirm unchanged checks do not create duplicate remote objects;
4. make one controlled database change in the disposable copy and confirm one
   readable Sofia-named object uploads;
5. use a syntactically valid disposable WebDAV config with deliberately wrong
   credentials for at least the grace period, and confirm exactly one readable
   warning while local pending data remains (an invalid config is an immediate
   local failure and does not test remote grace);
6. restore the valid config and confirm all pending items drain before exactly
   one recovery message;
7. download the newest test object manually, verify its 16-character digest
   prefix plus SQLite integrity/foreign keys, and restore only to a scratch
   database; and
8. keep the disposable units/config/state installed until the user confirms the
   three summaries, warning/recovery messages, and remote files.

Do not access or modify the production application database, production units,
or production timer state.

Completed on September 16, 2026. The user confirmed all three summaries, the
single delayed warning, the single full-drain recovery, and all three readable
remote files. The newest remote object was downloaded, matched its full local
SHA-256 and 16-character filename identity, passed SQLite integrity and foreign
key checks, and restored successfully into a scratch database. The one-minute
bad-password retries triggered Nextcloud's temporary brute-force protection;
the runbook now requires exactly two controlled bad-credential requests so the
production acceptance does not repeat that avoidable test lockout.

- [x] **Step 7: Prepare for user review without staging or committing**

Report the changed files, exact automated results, exact disposable acceptance
results, remaining production-only steps, and any rare at-least-once Discord
duplicate boundary. Wait for explicit user direction before staging, committing,
pushing, merging, enabling production timers, or deleting accepted test evidence.

Completed on September 16, 2026: the final source review and independent scoped
re-review found no remaining Critical or Important findings. Automated evidence
is recorded in `docs/implementation-notes/production-artifact-delivery.md`.
The user later approved and confirmed Step 6 without authorizing production
installation, endpoint activation, or timer enablement.
