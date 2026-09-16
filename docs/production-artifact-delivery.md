# Production Artifact Delivery And Backup Runbook

This is the operational authority for Task 25. Merging or deploying its source
does not install units, enable schedules, contact Hetzner or Discord, or touch
the production database. Each production action below requires its own approval.

## Fixed Production Contract

```text
Application checkout: /opt/extrusion-terminal/app
Production database:  /opt/extrusion-terminal/data/extrusion_terminal.sqlite3
Local backups:        /opt/extrusion-terminal/backups
Protected base:       /opt/extrusion-terminal
Maintenance lock:     /opt/extrusion-terminal/maintenance.lock
Runtime anchor:       /opt/extrusion-terminal/artifact-delivery
Pending outbox:       /opt/extrusion-terminal/artifact-delivery/outbox
Notification state:  /opt/extrusion-terminal/artifact-delivery/state
Operation lock:       /opt/extrusion-terminal/artifact-delivery/operation.lock
WebDAV curl config:   /etc/extrusion-terminal/hetzner-webdav.conf
Discord curl config:  /etc/extrusion-terminal/discord-webhook.conf
Summary schedule:     /etc/extrusion-terminal/backup-summary.conf (optional)
```

The fixed WebDAV base is:

```text
https://nx106226.your-storageshare.de/remote.php/dav/files/extrusion-backup
```

The application writes only below this existing remote hierarchy:

```text
system-backups/extrusion-terminal/
├── database-backups/YYYY-MM-DD/
├── shift-reports/
└── completed-order-pdfs/
```

Only `database-backups/` has a producer in this slice. Create that category
folder manually before acceptance. For each database backup, the worker issues
one bounded `MKCOL` for the queue item's Sofia-calendar `YYYY-MM-DD` child and accepts only
`201` (created) or `405` (already exists or cannot be created); the following
conditional upload is still the decisive success check. The application never
manages Hetzner users, shares, permissions, or remote retention, and it creates
no other remote directory.

## Protected Local Paths And Configuration

The base is a root-controlled anchor. The application user owns only the
children it must write:

```bash
sudo chown root:root /opt/extrusion-terminal
sudo chmod 0755 /opt/extrusion-terminal
sudo chown -R sk:sk \
  /opt/extrusion-terminal/app \
  /opt/extrusion-terminal/data \
  /opt/extrusion-terminal/backups
```

Do not recursively give `sk` ownership of `/opt/extrusion-terminal` after this.
The installer creates the root-controlled maintenance/runtime anchors and the
`sk`-writable outbox/state children with their exact permissions.

The existing Hetzner device credentials remain in:

```text
/etc/extrusion-terminal/hetzner-webdav.conf
```

Its only effective curl directive must be `user`. Create the Discord webhook
config without putting the URL in shell history:

```bash
sudo install -o sk -g sk -m 0600 /dev/null \
  /etc/extrusion-terminal/discord-webhook.conf
sudoedit /etc/extrusion-terminal/discord-webhook.conf
```

Enter this single directive in the editor, with the real values substituted:

```text
url = "https://discord.com/api/webhooks/WEBHOOK_ID/WEBHOOK_TOKEN?wait=true"
```

Verify metadata without displaying either secret:

```bash
sudo stat -c 'owner=%U group=%G mode=%a type=%F' \
  /etc/extrusion-terminal/hetzner-webdav.conf \
  /etc/extrusion-terminal/discord-webhook.conf
```

Both must be regular, non-symlink files owned by `sk:sk`, readable by `sk`, and
not accessible to group/other users (normally mode `600`). The installer also
parses both configs: WebDAV permits only `user`; Discord permits only one valid
`https://discord.com/api/webhooks/...?...wait=true` URL. It never prints values.

The optional summary schedule defaults to one daily message at `09:00`. Times
are always interpreted in Sofia; neither the file nor Discord messages repeat
the timezone label. To disable summaries or select one or two daily times,
create this non-secret configuration:

```bash
sudo install -o root -g sk -m 0640 /dev/null \
  /etc/extrusion-terminal/backup-summary.conf
sudoedit /etc/extrusion-terminal/backup-summary.conf
```

Enter exactly one of these forms:

```text
summary_times=off
summary_times=09:00
summary_times=09:00,21:00
```

Validate it without reading credentials or contacting Hetzner or Discord:

```bash
cd /opt/extrusion-terminal/app
sudo -u sk .venv/bin/python -m app.backup_summary validate-config
```

The command prints the normalized value and exits nonzero for any other form.
The installer performs the same parse automatically when this optional file
exists and also requires it to be a direct `root:sk` mode-`640` regular file.
Changing the schedule arms the next future slot; it does not send a historical
summary immediately. It preserves the last confirmed summary counters, while a
pending message belonging to the old schedule is discarded. During the
repeated autumn hour, one configured civil-time slot is sent at most once and
belongs to that hour's first occurrence.

## Install Units Disabled

Deploy the accepted source revision first. Set `ACCEPTED_REVISION` to the exact
40-character commit ID that was reviewed and approved; do not derive it from an
unreviewed checkout. Define this launcher in the operator shell:

```bash
ACCEPTED_REVISION=REPLACE_WITH_EXACT_REVIEWED_COMMIT_ID

run_accepted_task25_installer() {
  /usr/bin/sudo /bin/bash -c '
set -Eeuo pipefail
revision="$1"
shift
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || {
  printf "ERROR: accepted revision must be an exact lowercase commit ID.\n" >&2
  exit 1
}
app=/opt/extrusion-terminal/app
trusted_installer="$(/usr/bin/mktemp /run/extrusion-task25-installer.XXXXXX)"
cleanup() {
  /bin/rm -f -- "$trusted_installer"
}
trap cleanup EXIT
/usr/bin/env -i HOME=/root PATH=/usr/bin:/bin GIT_NO_REPLACE_OBJECTS=1 \
  /usr/bin/git --no-replace-objects -c safe.directory="$app" -C "$app" \
  show "$revision:scripts/install_artifact_delivery.sh" > "$trusted_installer"
/bin/chown root:root "$trusted_installer"
/bin/chmod 0700 "$trusted_installer"
/bin/bash "$trusted_installer" \
  --app-dir "$app" --accepted-revision "$revision" "$@"
' task25-installer "$ACCEPTED_REVISION" "$@"
}
```

This extracts the installer itself from the accepted Git object into a
root-owned temporary file. It disables Git replacement objects and ignores
repository-selection environment overrides, so root never executes the
`sk`-writable working-tree copy. Keep this shell open through acceptance, or
redefine the function and the same accepted revision before enablement.

Before first enablement, audit every pre-existing matching final-name backup.
The current backup code publishes a final name only after SQLite validation,
but retention deliberately does not repeat up to 144 integrity checks every ten
minutes. This one-time gate prevents a corrupt file left by older code or a
manual copy from occupying a retention slot:

```bash
cd /opt/extrusion-terminal/app
.venv/bin/python - <<'PY'
from pathlib import Path

from app.backups import (
    BACKUP_FILENAME_PREFIX,
    BACKUP_FILENAME_SUFFIX,
    validate_sqlite_database,
)

backup_dir = Path("/opt/extrusion-terminal/backups")
if not backup_dir.is_dir() or backup_dir.is_symlink():
    raise RuntimeError(f"Backup directory is missing or unsafe: {backup_dir}")
paths = sorted(
    backup_dir.glob(f"{BACKUP_FILENAME_PREFIX}*{BACKUP_FILENAME_SUFFIX}")
)
unsafe_paths = [path for path in paths if path.is_symlink() or not path.is_file()]
if unsafe_paths:
    names = ", ".join(path.name for path in unsafe_paths)
    raise RuntimeError(f"Matching backup entries are not direct regular files: {names}")
for path in paths:
    validate_sqlite_database(path)
print(f"Validated existing final-name backups: {len(paths)}")
PY
```

Any failure blocks enablement. Review and relocate the invalid file outside the
matching final-name set; do not silently delete it.

Run the read-only preflight:

```bash
run_accepted_task25_installer --dry-run
```

After explicit installation approval, install without enabling either timer:

```bash
run_accepted_task25_installer
```

The installer requires a clean deployed checkout, stages and verifies exactly
four tracked units, preserves the previous installation until daemon reload
succeeds, and holds both the maintenance and operation locks throughout.
Failure restores the
previous units and leaves both timers disabled. Success also leaves both timers
disabled. Confirm that state before any external acceptance:

```bash
systemctl is-enabled extrusion-terminal-backup.timer || true
systemctl is-enabled extrusion-terminal-delivery.timer || true
systemctl is-active extrusion-terminal-backup.timer || true
systemctl is-active extrusion-terminal-delivery.timer || true
```

All four results should be `disabled` or `inactive`, as appropriate.

## Base Endpoint Acceptance Before Enablement

These checks deliberately contact the real services. Run them only after the
user separately authorizes acceptance. They use a temporary local outbox and a
harmless disposable SQLite file, never the production database.

Create the disposable file and enqueue it:

```bash
cd /opt/extrusion-terminal/app
TASK25_ACCEPTANCE_DIR="$(mktemp -d /tmp/extrusion-task25-acceptance.XXXXXX)"
export TASK25_ACCEPTANCE_DIR
export EXTRUSION_ARTIFACT_OUTBOX_DIR="$TASK25_ACCEPTANCE_DIR/outbox"
export EXTRUSION_ARTIFACT_STATE_DIR="$TASK25_ACCEPTANCE_DIR/state"
export EXTRUSION_WEBDAV_CURL_CONFIG=/etc/extrusion-terminal/hetzner-webdav.conf
export EXTRUSION_DISCORD_CURL_CONFIG=/etc/extrusion-terminal/discord-webhook.conf
ACCEPTANCE_DAY="$(TZ=Europe/Sofia date +%F)"

.venv/bin/python - <<'PY'
import os
import sqlite3
from pathlib import Path
from app.artifact_outbox import enqueue_artifact

root = Path(os.environ["TASK25_ACCEPTANCE_DIR"])
source = root / "task25-acceptance.sqlite3"
with sqlite3.connect(source) as connection:
    connection.execute("CREATE TABLE acceptance (value TEXT NOT NULL)")
    connection.execute("INSERT INTO acceptance VALUES ('harmless disposable check')")
enqueue_artifact(source, "database-backups")
PY

.venv/bin/python -m app.artifact_delivery deliver
```

The first delivery must report `created=1`, `failed=0`, and `pending=0`, proving
the conditional create received HTTP `201`. Enqueue the identical file again:

```bash
.venv/bin/python - <<'PY'
import os
from pathlib import Path
from app.artifact_outbox import enqueue_artifact

source = Path(os.environ["TASK25_ACCEPTANCE_DIR"]) / "task25-acceptance.sqlite3"
enqueue_artifact(source, "database-backups")
PY

.venv/bin/python -m app.artifact_delivery deliver
```

That run must report `already_present=1`, `failed=0`, and `pending=0`, proving
the checksum-identical HTTP `412` retry is handled idempotently. Any HTTP `200`,
`204`, other result, remaining queue item, or nonzero exit blocks activation.

Also test that an interrupted conditional PUT does not reserve a partial remote
object. This is a production-activation gate, not application behavior:

```bash
.venv/bin/python - <<'PY'
import os
import sqlite3
from pathlib import Path

root = Path(os.environ["TASK25_ACCEPTANCE_DIR"])
source = root / "task25-interrupted.sqlite3"
with sqlite3.connect(source) as connection:
    connection.execute("CREATE TABLE payload (value BLOB NOT NULL)")
    connection.execute("INSERT INTO payload VALUES (zeroblob(1048576))")
PY

INTERRUPTED_SOURCE="$TASK25_ACCEPTANCE_DIR/task25-interrupted.sqlite3"
INTERRUPTED_SHA="$(sha256sum "$INTERRUPTED_SOURCE" | awk '{print $1}')"
INTERRUPTED_NAME="task25-interrupted-$(date -u +%Y%m%dT%H%M%SZ)__sha256-${INTERRUPTED_SHA}.sqlite3"
INTERRUPTED_URL="https://nx106226.your-storageshare.de/remote.php/dav/files/extrusion-backup/system-backups/extrusion-terminal/database-backups/${ACCEPTANCE_DAY}/${INTERRUPTED_NAME}"

curl --disable --config /etc/extrusion-terminal/hetzner-webdav.conf \
  --silent --show-error --output /dev/null --write-out '%{http_code}\n' \
  --connect-timeout 10 --limit-rate 1024 --max-time 2 \
  --request PUT --upload-file "$INTERRUPTED_SOURCE" \
  --header 'If-None-Match: *' "$INTERRUPTED_URL"

curl --disable --config /etc/extrusion-terminal/hetzner-webdav.conf \
  --silent --show-error --output /dev/null --write-out '%{http_code}\n' \
  --connect-timeout 10 --max-time 120 \
  --request PUT --upload-file "$INTERRUPTED_SOURCE" \
  --header 'If-None-Match: *' "$INTERRUPTED_URL"
```

The deliberately limited first command must time out before completing. The
second must return `201`. If it returns `412`, stop: the provider retained a
partial path, so the current idempotency design must be revised before timers
are enabled.

Finally send one explicit harmless Discord acceptance message:

```bash
.venv/bin/python - <<'PY'
from app.pipeline_notifications import DiscordWebhookSender

DiscordWebhookSender().send(
    "Extrusion Terminal Task 25 acceptance: Discord delivery confirmed"
)
PY
```

Success requires Discord HTTP `200` plus a bounded JSON response containing the
saved message ID. Confirm the message appears in the intended channel. Preserve
the command outputs in the maintenance record; do not preserve or print secret
config contents.

## Refinement Acceptance Before Enablement

The September 15 development endpoint exercise accepted the original transport
slice only. It did not accept upload-on-change, producer handoff coordination,
Sofia routing, delayed cloud alerts, full-drain recovery, freshness, or
summaries. Before production enablement, run these refinement checks from the
exact accepted checkout while the production timers remain disabled.

First execute the disposable integration cases. They use temporary SQLite and
filesystem paths plus fake transports; they do not contact Hetzner or Discord:

```bash
cd /opt/extrusion-terminal/app
source .venv/bin/activate
python -m pytest -q \
  tests/test_backup_job.py::test_unchanged_database_is_validated_but_not_queued_twice \
  tests/test_artifact_delivery.py::test_delivery_waits_for_active_backup_handoff_before_uploading \
  tests/test_artifact_delivery.py::test_recovery_waits_for_the_entire_multibatch_backlog \
  tests/test_artifact_delivery.py::test_cleanup_retry_does_not_double_count_a_confirmed_upload \
  tests/test_pipeline_notifications.py::test_webdav_failure_alerts_once_after_ten_minute_grace \
  tests/test_backup_summary.py::test_daily_summary_sends_once_at_first_invocation_after_slot \
  tests/test_backup_summary.py::test_never_run_freshness_waits_thirty_minutes_then_alerts
```

All seven must pass. This proves the accepted source's multi-check deduplication,
unfinished-handoff gate, one-count confirmation checkpoint, full-backlog
recovery, ten-minute grace, scheduled summary, and same-server freshness paths.

Then exercise the grace/recovery path against the real disposable endpoints.
Use a syntactically valid curl config containing deliberately wrong credentials;
an invalid config is a local configuration failure and correctly bypasses the
cloud grace period.

Make exactly two bad-credential requests: the initial failure and one controlled
request when the grace expires. If this check is driven by real elapsed time,
stop the disposable delivery timer immediately after the first failure, wait
ten minutes, then run the second failure manually. Do not leave the one-minute
timer retrying a wrong password: repeated bad authentication can trigger
Nextcloud's temporary brute-force protection and delay the valid recovery.

```bash
BAD_WEBDAV_CONFIG="$TASK25_ACCEPTANCE_DIR/bad-webdav.conf"
SUMMARY_OFF_CONFIG="$TASK25_ACCEPTANCE_DIR/summary-off.conf"
install -m 0600 /dev/null "$BAD_WEBDAV_CONFIG"
printf '%s\n' 'user = "extrusion-backup:deliberately-wrong-acceptance-password"' \
  > "$BAD_WEBDAV_CONFIG"
printf '%s\n' 'summary_times=off' > "$SUMMARY_OFF_CONFIG"

.venv/bin/python - <<'PY'
import os
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.artifact_delivery import default_delivery_config, deliver_pending
from app.backup_job import run_backup_job

root = Path(os.environ["TASK25_ACCEPTANCE_DIR"])
source = root / "task25-acceptance.sqlite3"
with sqlite3.connect(source) as connection:
    connection.execute(
        "INSERT INTO acceptance VALUES ('refinement grace and recovery check')"
    )
started = datetime.now(timezone.utc).replace(microsecond=0)
produced = run_backup_job(
    source_db_path=source,
    backup_dir=root / "backups",
    outbox_dir=root / "outbox",
    state_dir=root / "state",
    now=started,
)
assert produced.queued_artifact is not None
assert produced.queued_artifact.remote_filename.startswith(
    "extrusion-terminal_"
    f"{started.astimezone(ZoneInfo('Europe/Sofia')):%Y-%m-%d_%H-%M-%S}_"
)

base = replace(
    default_delivery_config(),
    outbox_dir=root / "outbox",
    state_dir=root / "state",
    discord_curl_config=Path(
        "/etc/extrusion-terminal/discord-webhook.conf"
    ),
    summary_config_path=root / "summary-off.conf",
)
bad = replace(base, webdav_curl_config=root / "bad-webdav.conf")
first = deliver_pending(bad, now=started)
warned = deliver_pending(bad, now=started + timedelta(minutes=10))
recovered = deliver_pending(
    replace(
        base,
        webdav_curl_config=Path(
            "/etc/extrusion-terminal/hetzner-webdav.conf"
        ),
    ),
    now=started + timedelta(minutes=11),
)
assert first.failed_count == 1 and first.notification_pending
assert warned.failed_count == 1 and not warned.notification_pending
assert recovered.failed_count == 0 and recovered.pending_count == 0
print("Refinement grace/full-drain recovery acceptance passed.")
PY
```

Confirm exactly one readable delayed-cloud warning and one recovery message in
Discord, and confirm the final readable Sofia-named object exists in the
correct Sofia-date folder. Any early cloud warning, missing recovery, remaining
queue item, duplicate recovery, or unreadable/incorrectly routed object blocks
enablement. Remove only the disposable acceptance directory after recording
and approving the results.

## Enable Timers And Check The First Production Backup

Only after both endpoint and refinement acceptance pass and the user approves
activation:

```bash
run_accepted_task25_installer --enable --dry-run
run_accepted_task25_installer --enable
```

The enable command refuses installed units that differ from the accepted source.
Then perform one observed production cycle:

```bash
sudo systemctl start extrusion-terminal-backup.service
sudo systemctl start extrusion-terminal-delivery.service
journalctl -u extrusion-terminal-backup.service -n 100 --no-pager
journalctl -u extrusion-terminal-delivery.service -n 100 --no-pager
systemctl list-timers \
  extrusion-terminal-backup.timer \
  extrusion-terminal-delivery.timer
```

Verify one validated `extrusion_terminal_*.sqlite3` remains locally, its
short-identity queue copy drains, the remote object appears under
`database-backups/<Sofia YYYY-MM-DD>/`, and both timers remain scheduled. Then
observe at least one automatic ten-minute backup and one delivery retry
interval. Do not automate remote inspection or restoration.

## Runtime Behavior And Failure Meaning

- The backup timer runs every ten minutes. Every run creates and validates a
  SQLite-safe local image; only content whose complete SHA-256 differs from the
  previous validated check is enqueued. The newest 144 validated local images
  remain (approximately 24 hours), including unchanged checks. The activation
  audit covers pre-existing matching files; retention does not revalidate the
  entire historical set on every run.
- The independent delivery timer runs approximately once per minute.
- One run considers at most 25 active queue entries, starts no new upload at or
  after 180 seconds, rechecks that cutoff immediately before curl, and defers a
  new Discord request at or after 410 seconds. Deferred notification state is
  retried by the next run. Reaching the upload cutoff with zero upload progress
  is a reported delivery failure; reaching it after at least one confirmed
  upload safely defers the remaining queue.
- WebDAV uses 10-second connect, 120-second transfer, and 180-second subprocess
  bounds; Discord uses 10-second connect and 30-second transfer bounds.
- Backup and delivery services have five- and ten-minute ceilings respectively.

For database backups, each delivery first ensures the exact Sofia-calendar daily child
with bounded `MKCOL`, once per child per batch, then sends a conditional `PUT`
with `If-None-Match: *`. HTTP `201` is a new object. A matching 16-character
content identity—or a legacy matching full checksum—makes `412` an accepted
idempotent retry under the tested sole-writer contract. There is no
remote read, listing, file overwrite, rename, move, copy, deletion, or retention
operation.

Backup or enqueue failure fails the producer job. WebDAV transport,
authentication, permission, unexpected response, local cleanup, or queue-health
failure fails delivery and preserves evidence. Malformed entries are moved
intact to local quarantine so they cannot starve later valid work, including
malformed post-delivery cleanup tombstones. Quarantine collisions use a bounded
opaque name so a maximum-length source name cannot block the move. Quarantined
evidence blocks a green recovery until an operator inspects and resolves it;
empty quarantine directories do not.

The producer writes a durable handoff before publishing a changed backup to the
queue. Delivery skips that exact database item until the producer has committed
activity/retention and cleared the handoff. If the handoff state is unreadable,
delivery leaves database items untouched and reports a local failure; unrelated
artifact categories may still proceed.

For remotely confirmed uploads, the worker first records the queue-item ID and
upload counters durably, then moves the active item to local cleanup, records
the invocation's final success/failure outcome exactly once, and acknowledges
the recorded ID. This ordering makes a retry after a crash or cleanup failure
idempotent: a matching conditional `412` can finish cleanup but cannot increment
the confirmed-upload total twice or count one failed invocation twice.

Routine successful checks do not send Discord messages. A backup-producer
failure alerts immediately. A remote WebDAV incident is silent if it recovers
within ten minutes; otherwise it sends one warning and no repeats. Local
configuration, queue, quarantine, activity-state, and cleanup failures alert
immediately. Recovery is sent
only after a failure-free delivery run leaves the exact queue empty, and says
how many waiting database backups were uploaded. If the warning itself never
reached Discord, one combined interruption-and-recovery message preserves the
incident.

While delivery still runs, it also warns if the producer has not recorded a
validated check for 30 minutes. This same-server check cannot report a dead VM
or total connectivity loss. The scheduled summary reports validated checks,
failed checks, changed database versions, confirmed Hetzner uploads, the latest
check/upload times, and exact waiting count. Incident notices take priority,
and one delivery invocation sends at most one Discord message. Notification
errors and pending status remain in bounded local state/journal output; pending
outbox and quarantine evidence have no automatic retention.

A summary counter that regresses below its last confirmed baseline is shown as
unknown and does not lower that baseline. This avoids presenting restored or
manually reset state as a healthy negative/zero interval.

## Deployment Coordination

The installer and deployment script take the root-protected maintenance lock.
Scheduled jobs take the operation lock shared/non-blocking; deployment takes it
exclusively. Once Task 25 is installed, deployment records which timers were
enabled, disables both, mutates and verifies the checkout, then restores only
the previously enabled timers after final health/revision checks. A failed
deployment leaves both timers disabled and prints that recovery requirement.

The upgraded deploy script requires the protected base and maintenance lock
even before Task 25 units exist. Therefore, after first deploying this source,
complete the disabled installer step before attempting the next deployment.
Never bypass a lock/ownership refusal by manually restarting production.

## Safe Disablement And Discord Revocation

Disable future scheduled work without deleting any data or configuration:

```bash
sudo systemctl disable --now \
  extrusion-terminal-backup.timer \
  extrusion-terminal-delivery.timer
sudo systemctl stop \
  extrusion-terminal-backup.service \
  extrusion-terminal-delivery.service
```

To retire Discord, first disable/stop the jobs, revoke the webhook in Discord,
then remove only `/etc/extrusion-terminal/discord-webhook.conf`. Create a new
mode-`600` config and repeat preflight/acceptance before re-enabling. Never paste
the URL into chat, tickets, logs, or command arguments.

## Manual Restore Remains Human-Controlled

Task 25 never downloads or restores a database. An authorized person selects
and downloads a remote backup. Rehearse into a scratch target first:

```bash
cd /opt/extrusion-terminal/app
.venv/bin/python -m app.backups restore \
  --backup /opt/extrusion-terminal/backups/CHOSEN_BACKUP.sqlite3 \
  --target /tmp/extrusion-terminal-restore-check.sqlite3
```

For an actual restore, use one operator shell for the entire procedure. Acquire
the maintenance lock followed by the operation lock, then record timer state
under those locks. This is the same lock order used by installation and
deployment:

```bash
exec {MAINTENANCE_LOCK_FD}</opt/extrusion-terminal/maintenance.lock
/usr/bin/flock --exclusive --timeout 60 "$MAINTENANCE_LOCK_FD"
exec {OPERATION_LOCK_FD}</opt/extrusion-terminal/artifact-delivery/operation.lock
/usr/bin/flock --exclusive --timeout 600 "$OPERATION_LOCK_FD"

PREVIOUSLY_ENABLED_TASK25_TIMERS=()
for timer in \
  extrusion-terminal-backup.timer \
  extrusion-terminal-delivery.timer
do
  if test "$(systemctl is-enabled "$timer" 2>/dev/null || true)" = enabled; then
    PREVIOUSLY_ENABLED_TASK25_TIMERS+=("$timer")
  fi
done
```

Keep that shell open. Under both locks, quiesce every writer and prove all three
services are inactive before changing the database:

```bash
sudo systemctl disable --now \
  extrusion-terminal-backup.timer \
  extrusion-terminal-delivery.timer
sudo systemctl stop \
  extrusion-terminal-backup.service \
  extrusion-terminal-delivery.service
test "$(systemctl show extrusion-terminal-backup.service -p ActiveState --value)" = inactive
test "$(systemctl show extrusion-terminal-delivery.service -p ActiveState --value)" = inactive
sudo systemctl stop extrusion-terminal.service
test "$(systemctl show extrusion-terminal.service -p ActiveState --value)" = inactive
```

Still in the same shell and holding both locks, run the restore and its built-in
SQLite integrity/foreign-key validation:

```bash
cd /opt/extrusion-terminal/app
sudo -u sk .venv/bin/python -m app.backups restore \
  --backup /opt/extrusion-terminal/backups/CHOSEN_BACKUP.sqlite3 \
  --target /opt/extrusion-terminal/data/extrusion_terminal.sqlite3
```

Restart the application while both locks remain held. Verify `/health`,
`/admin`, and `/terminal` against the restored data. If any step fails, stop and
leave the timers disabled; do not run the unlock steps:

```bash
sudo systemctl start extrusion-terminal.service
test "$(systemctl show extrusion-terminal.service -p ActiveState --value)" = active
curl --fail --silent --show-error http://127.0.0.1:8000/health
```

After the app and restored workflow are healthy, release the operation lock,
restore only the timers that were enabled before maintenance, confirm they are
active, and finally release the maintenance lock:

```bash
/usr/bin/flock --unlock "$OPERATION_LOCK_FD"
exec {OPERATION_LOCK_FD}<&-

if test "${#PREVIOUSLY_ENABLED_TASK25_TIMERS[@]}" -gt 0; then
  sudo systemctl enable --now "${PREVIOUSLY_ENABLED_TASK25_TIMERS[@]}"
  for timer in "${PREVIOUSLY_ENABLED_TASK25_TIMERS[@]}"; do
    test "$(systemctl is-enabled "$timer")" = enabled
    test "$(systemctl is-active "$timer")" = active
  done
fi

/usr/bin/flock --unlock "$MAINTENANCE_LOCK_FD"
exec {MAINTENANCE_LOCK_FD}<&-
```

Never overwrite the live database while the app or either one-shot job is
active, never change the lock order, and never use a normal file copy while
SQLite may be writing.

## Monitoring Boundary

Task 25 can warn only while the production VM is alive and can reach Discord. A
dead VM, site power loss, or total network outage cannot be reported by software
on that VM. External heartbeat/availability monitoring remains a separate task.
