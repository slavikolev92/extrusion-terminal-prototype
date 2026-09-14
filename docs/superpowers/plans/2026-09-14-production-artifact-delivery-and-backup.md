# Production Artifact Delivery And Database Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. Use
> superpowers:subagent-driven-development only if the user explicitly
> authorizes delegated execution. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Add one reusable append-only file-delivery outbox, Discord
failure/recovery notifications, and a ten-minute job that sends validated
SQLite backups to the configured Hetzner Storage Share while retaining the
newest 144 local backups.

**Architecture:** Producers atomically copy finished immutable files into a
fixed-category filesystem outbox outside the Git checkout. A one-shot delivery
worker validates each queue item and uses the existing protected curl
configuration to issue only conditional WebDAV `PUT` requests. Separate
filesystem notification state suppresses Discord warning spam and records one
recovery; the first producer wraps the existing `app.backups.create_backup()`
primitive and is scheduled independently from the common delivery worker.

**Tech Stack:** Python 3 standard library, existing `app.backups`, curl,
systemd one-shot services/timers, pytest with temporary SQLite/filesystem
paths, Discord incoming webhook.

**Spec:**
`docs/superpowers/specs/2026-09-14-production-artifact-delivery-design.md`

**Plan status:** Initial source implementation and verification completed on
the dedicated branch on 2026-09-14. The approved post-review hardening tasks
below are now in progress. This plan does not authorize production
installation, external test uploads, Discord webhook creation, timer
enablement, or deployment.

## Branch Boundary

- Execute this plan on `task-25-production-artifact-delivery`, created from the
  current local `main` on 2026-09-14 with the accepted planning work intact.
- Keep the Task 25 planning documents and all implementation slices on this one
  branch so they can be reviewed together before a later merge to `main`.
- Do not implement Task 25 directly on `main`. Branch creation and source edits
  do not authorize staging, commits, deployment, or the eventual merge; those
  remain explicit user decisions.

## Global Constraints

- Implement only the shared outbox, WebDAV delivery, Discord notification, and
  database-backup producer. Do not implement Task 24 reports or completed-order
  PDF generation.
- Reuse `app.backups.create_backup()`; never copy the live SQLite database as
  the backup method.
- Add no SQLite schema, migration, production-data field, or application UI.
- Use exactly these categories: `database-backups`, `shift-reports`, and
  `completed-order-pdfs`.
- Use remote root
  `system-backups/extrusion-terminal/production-data/` and never expose a
  configurable arbitrary remote destination to a producer.
- The WebDAV worker may issue only conditional create `PUT`. It must not issue
  `GET`, `PROPFIND`, `DELETE`, `MOVE`, `COPY`, unconditional overwrite, remote
  directory creation, or remote retention operations.
- Accept only HTTP `201` as a new remote object. Treat `200` and `204` as
  failures. Accept checksum-named `412` only as an idempotent retry under the
  explicit sole-automated-writer assumption recorded in the design.
- Remote filenames include the complete lowercase SHA-256 digest before the
  final file suffix.
- Preserve source files. Remove only a fully delivered disposable queue copy.
- Never silently delete an undelivered or malformed queue item.
- Retain 144 local database backups through existing retention behavior.
- Use `/etc/extrusion-terminal/hetzner-webdav.conf` without reading its secret
  into logs or command-line arguments.
- Store the Discord webhook outside Git in a separate protected curl config.
- Put curl's `--disable` option first, use finite connect/transfer/subprocess
  timeouts, and give both systemd services finite runtime bounds.
- Process no more than 25 pending items per worker run and stop further remote
  attempts after the first shared WebDAV/transport failure.
- Automated tests use injected fake command runners and temporary directories;
  they never contact Hetzner or Discord and never mutate
  `data/extrusion_terminal.sqlite3`.
- Runtime outbox/state paths remain outside `/opt/extrusion-terminal/app` so
  they cannot dirty the production checkout.
- Run services as the existing production user `sk`.
- Coordinate the scheduled jobs and normal production deployment through one
  shared/exclusive operation lock outside the Git checkout.
- Do not stage or commit any file unless the user explicitly requests it.
- Do not modify `TEMP - Task 20 requirements-spec.md`, Task 24's detailed
  producer record, or unrelated tracker work while executing this slice.

---

## File Structure

### Create

- `app/bounded_files.py` — no-follow, regular-file-only, cap-plus-one reads for
  bounded local control files.
- `app/artifact_outbox.py` — category contract, immutable remote naming,
  atomic queue publication, queue validation, and delivered-item cleanup.
- `app/curl_transport.py` — one injectable no-shell subprocess runner shared
  by WebDAV and Discord.
- `app/pipeline_notifications.py` — atomic per-component state and bounded
  Discord webhook delivery.
- `app/artifact_delivery.py` — fixed WebDAV URL construction, conditional curl
  upload, pending-queue drain, notification integration, and delivery CLI.
- `app/backup_job.py` — one backup/validate/retain/enqueue operation and CLI.
- `tests/test_bounded_files.py` — exact-limit, oversize, FIFO, symlink, and
  forced-short-read coverage for the shared bounded reader.
- `tests/test_artifact_outbox.py` — atomicity, validation, checksum, ordering,
  source preservation, and cleanup tests.
- `tests/test_pipeline_notifications.py` — failure/recovery state-machine and
  Discord command tests.
- `tests/test_artifact_delivery.py` — create-only curl contract, status
  handling, retry, queue preservation, and CLI tests.
- `tests/test_backup_job.py` — backup-wrapper success/failure, keep-count, and
  runtime-database isolation tests.
- `tests/test_artifact_delivery_operations.py` — source-controlled unit,
  timer, installer, path, and secret-boundary tests.
- `deployment/systemd/extrusion-terminal-backup.service` — one backup producer
  run.
- `deployment/systemd/extrusion-terminal-backup.timer` — ten-minute calendar
  schedule.
- `deployment/systemd/extrusion-terminal-delivery.service` — one common outbox
  drain.
- `deployment/systemd/extrusion-terminal-delivery.timer` — one-minute retry
  cadence.
- `scripts/install_artifact_delivery.sh` — explicit dry-run and authorized
  installation/enablement path.
- `docs/production-artifact-delivery.md` — configuration, operation,
  troubleshooting, disablement, and manual acceptance runbook.
- `docs/implementation-notes/production-artifact-delivery.md` — final source
  behavior, verification result, migration assessment, and deployment status.

### Modify

- `.gitignore` — ignore repo-local developer defaults for artifact-delivery
  runtime state if the modules are run without production path overrides.
- `README.md` — replace scheduler-not-installed wording only after source
  implementation is accepted, while distinguishing source readiness from
  production enablement.
- `docs/production-deployment.md` — link the separately authorized timer
  installation and verification procedure and document the operation lock.
- `docs/INFRASTRUCTURE_IMPLEMENTATION_PLAN.md` — supersede its old standalone
  local-only Phase 7 timer sketch with the Task 25 runbook.
- `scripts/deploy_production.sh` — hold the Task 25 operation lock exclusively
  while backing up, updating, verifying, and restarting the production app.

### Reuse Without Redesign

- `app/backups.py`
- `tests/test_backup_recovery.py`
- `/etc/extrusion-terminal/hetzner-webdav.conf`
- `/opt/extrusion-terminal/data/extrusion_terminal.sqlite3`
- `/opt/extrusion-terminal/backups`

---

### Task 1: Atomic Fixed-Category Outbox

**Files:**

- Create: `app/artifact_outbox.py`
- Create: `tests/test_artifact_outbox.py`
- Modify: `.gitignore`

**Interfaces:**

- Produces:
  `enqueue_artifact(source_path: Path | str, category: str, *, outbox_dir: Path | str | None = None, remote_basename: str | None = None, now: datetime | None = None, item_id: str | None = None) -> QueuedArtifact`
- Produces:
  `snapshot_queue_entries(outbox_dir: Path | str | None = None, *, max_entries: int) -> QueueSnapshot`
- Produces:
  `load_queued_artifact(item_dir: Path | str, *, outbox_dir: Path | str | None = None) -> QueuedArtifact`
- Produces:
  `remove_delivered_artifact(artifact: QueuedArtifact) -> None`
- Produces bounded malformed-evidence quarantine and delivered-cleanup reaping
  through `quarantine_queue_entry()` and `reap_delivered_cleanup()`.
- Produces:
  `CATEGORY_REMOTE_FOLDERS: Mapping[str, str]`
- Produces immutable `QueuedArtifact` fields: `item_dir`, `payload_path`,
  `metadata_path`, `category`, `remote_filename`, `sha256`, `size_bytes`, and
  `queued_at_utc`.
- Consumes only complete producer-owned source files; it never moves or deletes
  them.

- [x] **Step 1: Write the fixed-category and immutable-name tests**

Create `tests/test_artifact_outbox.py` with focused cases equivalent to:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.artifact_outbox import (
    CATEGORY_REMOTE_FOLDERS,
    enqueue_artifact,
    load_queued_artifact,
    remove_delivered_artifact,
    snapshot_queue_entries,
)


def test_enqueue_copies_source_and_uses_checksum_name(tmp_path: Path):
    source = tmp_path / "extrusion_terminal_20260914_120000_000001.sqlite3"
    source.write_bytes(b"sqlite-safe-image")
    outbox = tmp_path / "outbox"

    queued = enqueue_artifact(
        source,
        "database-backups",
        outbox_dir=outbox,
        now=datetime(2026, 9, 14, 12, 1, tzinfo=timezone.utc),
        item_id="item-001",
    )

    assert source.read_bytes() == b"sqlite-safe-image"
    assert queued.payload_path.read_bytes() == b"sqlite-safe-image"
    assert queued.remote_filename.startswith(
        "extrusion_terminal_20260914_120000_000001__sha256-"
    )
    assert queued.remote_filename.endswith(".sqlite3")
    assert len(queued.sha256) == 64
    assert queued.item_dir.parent == outbox / "pending" / "database-backups"
    assert tuple((outbox / "staging").iterdir()) == ()


@pytest.mark.parametrize(
    ("category", "name"),
    [
        ("unknown", "report.pdf"),
        ("database-backups", "../escape.sqlite3"),
        ("database-backups", "wrong.pdf"),
        ("shift-reports", "wrong.sqlite3"),
        ("completed-order-pdfs", "bad/name.pdf"),
    ],
)
def test_enqueue_rejects_unknown_category_path_or_suffix(
    tmp_path: Path, category: str, name: str
):
    source = tmp_path / "source.bin"
    source.write_bytes(b"payload")
    with pytest.raises(ValueError):
        enqueue_artifact(
            source,
            category,
            outbox_dir=tmp_path / "outbox",
            remote_basename=name,
        )


def test_category_mapping_is_exact():
    assert CATEGORY_REMOTE_FOLDERS == {
        "database-backups": "database-backups",
        "shift-reports": "shift-reports",
        "completed-order-pdfs": "completed-order-pdfs",
    }
```

Add tests proving missing/non-file sources fail, metadata contains exactly the
approved schema, pending items load oldest-first, a corrupt payload or metadata
is rejected without deletion, and delivered cleanup refuses paths outside the
specific item directory.

- [x] **Step 2: Run the outbox tests and confirm the missing-module failure**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_artifact_outbox.py -q
```

Expected: collection fails because `app.artifact_outbox` does not exist.

- [x] **Step 3: Implement the minimal outbox contract**

Create `app/artifact_outbox.py` with these concrete foundations:

```python
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

from . import db


OUTBOX_SCHEMA_VERSION = 1
CATEGORY_REMOTE_FOLDERS = MappingProxyType({
    "database-backups": "database-backups",
    "shift-reports": "shift-reports",
    "completed-order-pdfs": "completed-order-pdfs",
})
CATEGORY_SUFFIXES = MappingProxyType({
    "database-backups": ".sqlite3",
    "shift-reports": ".pdf",
    "completed-order-pdfs": ".pdf",
})
DEFAULT_OUTBOX_DIR = Path(
    os.getenv(
        "EXTRUSION_ARTIFACT_OUTBOX_DIR",
        db.BASE_DIR / "artifact-delivery" / "outbox",
    )
)


@dataclass(frozen=True)
class QueuedArtifact:
    item_dir: Path
    payload_path: Path
    metadata_path: Path
    category: str
    remote_filename: str
    sha256: str
    size_bytes: int
    queued_at_utc: str
```

Implement helpers that:

- validate a plain basename with no `/`, `\\`, dot segment, control character,
  or wrong category suffix;
- copy to `<outbox>/staging/<item-id>/payload`;
- hash the copied payload with SHA-256;
- derive `<stem>__sha256-<full digest><suffix>`;
- write canonical UTF-8 JSON to `metadata.json` through a temporary file;
- fsync the payload, metadata, and staging directory before `os.replace()`;
- atomically rename the complete item to
  `<outbox>/pending/<category>/<item-id>`; and
- remove incomplete staging on an exception without touching the source.

`snapshot_queue_entries()` must maintain a bounded oldest-first selection while
counting active pending and stale staging entries, including structural
problems at the immediate roots. `load_queued_artifact()` must validate that a
candidate is inside the configured pending/category root, then validate schema
version, exact metadata keys, parent category, suffix, digest syntax, recorded
size, and actual payload hash. Do not delete invalid evidence. Quarantine it
durably outside active ordering so later valid items cannot be starved.

`remove_delivered_artifact()` must resolve and validate that both files are
direct children of the resolved item directory, unlink only those two files,
and remove only the now-empty item directory.

Add this repo-local default state path to `.gitignore`:

```gitignore
artifact-delivery/
```

- [x] **Step 4: Run the outbox tests**

Run:

```bash
python -m pytest tests/test_artifact_outbox.py tests/test_backup_recovery.py -q
```

Expected: all tests pass and existing SQLite backup behavior is unchanged.

- [x] **Step 5: Review the Task 1 diff**

Run:

```bash
git diff --check
git diff -- app/artifact_outbox.py tests/test_artifact_outbox.py .gitignore
```

Confirm no queue path can escape its configured root and no source-file unlink
exists. Do not stage or commit. If the user explicitly requests a Task 1
commit, use only these files and message `Add atomic artifact outbox`.

---

### Task 2: Discord Failure And Recovery State

**Files:**

- Create: `app/curl_transport.py`
- Create: `app/pipeline_notifications.py`
- Create: `tests/test_pipeline_notifications.py`

**Interfaces:**

- Produces:
  `record_component_failure(component: str, error: str, *, state_dir: Path | str | None = None, notifier: NotificationSender | None = None, now: datetime | None = None, context: Mapping[str, object] | None = None) -> NotificationResult`
- Produces:
  `record_component_success(component: str, *, state_dir: Path | str | None = None, notifier: NotificationSender | None = None, now: datetime | None = None, context: Mapping[str, object] | None = None) -> NotificationResult`
- Produces `DiscordWebhookSender(curl_config_path: Path | str, runner: CurlRunner
  = run_curl)` with `send(message: str) -> None`.
- Produces shared `CurlResult`, `CurlRunner`, and
  `run_curl(command: Sequence[str], *, input_bytes: bytes | None = None) -> CurlResult`;
  the real runner applies a fixed outer subprocess timeout.
- Produces
  `validate_curl_config(path: Path | str, *, required_options: frozenset[str], allowed_options: frozenset[str]) -> Mapping[str, str]`, which never includes
  secret values in an exception.
- Produces `NotificationSender` protocol and immutable `NotificationResult`
  fields: `component`, `health`, `state_path`, `notification_attempted`,
  `notification_sent`, and `notification_pending`.
- Consumed later by the delivery worker and backup producer.

- [x] **Step 1: Write the notification state-machine tests**

Create tests with an injected in-memory sender:

```python
class RecordingSender:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)
        if self.fail:
            raise RuntimeError("discord unavailable")


def test_failure_is_sent_once_and_recovery_is_sent_once(tmp_path):
    sender = RecordingSender()

    first = record_component_failure(
        "webdav-delivery",
        "HTTP 503",
        state_dir=tmp_path,
        notifier=sender,
    )
    repeated = record_component_failure(
        "webdav-delivery",
        "HTTP 503 again",
        state_dir=tmp_path,
        notifier=sender,
    )
    recovered = record_component_success(
        "webdav-delivery",
        state_dir=tmp_path,
        notifier=sender,
    )
    healthy = record_component_success(
        "webdav-delivery",
        state_dir=tmp_path,
        notifier=sender,
    )

    assert first.notification_sent is True
    assert repeated.notification_sent is False
    assert recovered.notification_sent is True
    assert healthy.notification_sent is False
    assert len(sender.messages) == 2
    assert "FAILED" in sender.messages[0]
    assert "RECOVERED" in sender.messages[1]
```

Add cases proving a failed Discord send remains pending and retries, state
writes are atomic, component names are allowlisted, error/context text is
bounded and excludes newlines/control characters, and `allowed_mentions` is
disabled in the outgoing JSON. Add curl-config tests proving comments and one
quoted directive parse, a Discord file must contain exactly one `url`, the URL
must use `https://discord.com/api/webhooks/` with `wait=true`, and rejected
configuration errors never contain the fake token value. Assert `--disable` is
the first curl option, fixed connection/transfer bounds are present, and an
injected subprocess timeout leaves notification state pending without exposing
the command or token.

- [x] **Step 2: Run the tests and confirm failure**

Run:

```bash
python -m pytest tests/test_pipeline_notifications.py -q
```

Expected: collection fails because `app.pipeline_notifications` does not exist.

- [x] **Step 3: Implement atomic state and the Discord sender**

Create `app/curl_transport.py` with one injectable, no-shell subprocess
boundary:

```python
from dataclasses import dataclass
import subprocess
from typing import Protocol, Sequence


CURL_PROCESS_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class CurlResult:
    returncode: int
    stdout: str
    stderr: str


class CurlRunner(Protocol):
    def __call__(
        self,
        command: Sequence[str],
        *,
        input_bytes: bytes | None = None,
    ) -> CurlResult: ...


def run_curl(
    command: Sequence[str],
    *,
    input_bytes: bytes | None = None,
) -> CurlResult:
    completed = subprocess.run(
        list(command),
        input=input_bytes,
        capture_output=True,
        check=False,
        timeout=CURL_PROCESS_TIMEOUT_SECONDS,
    )
    return CurlResult(
        completed.returncode,
        completed.stdout.decode("utf-8", errors="replace"),
        completed.stderr.decode("utf-8", errors="replace"),
    )
```

Do not accept a shell string or expose `shell=True`. Let
`subprocess.TimeoutExpired` reach the bounded caller error path; callers must
not discard pending queue or notification state when it occurs.

In the same module, implement `validate_curl_config()` as a bounded parser for
blank lines, `#` comments, and `name = value` directives. Reject duplicate,
missing, malformed, or non-allowlisted directive names. Return parsed values
only to the immediate caller and never interpolate them into an error. The
WebDAV caller requires/allows only `user`; the Discord caller requires/allows
only `url`.

Use these exact component names and state location:

```python
ALLOWED_COMPONENTS = frozenset({"database-backup", "webdav-delivery"})
DEFAULT_STATE_DIR = Path(
    os.getenv(
        "EXTRUSION_ARTIFACT_STATE_DIR",
        db.BASE_DIR / "artifact-delivery" / "state",
    )
)
DEFAULT_DISCORD_CURL_CONFIG = Path(
    os.getenv(
        "EXTRUSION_DISCORD_CURL_CONFIG",
        "/etc/extrusion-terminal/discord-webhook.conf",
    )
)
```

Store one schema-versioned JSON file per component through write/fsync/replace.
Retain `health`, `first_failed_at_utc`, `last_attempt_at_utc`, bounded
`last_error`, whether the failure notice was sent, and whether recovery notice
delivery remains pending.

Define the notification interface and immutable result explicitly:

```python
class NotificationSender(Protocol):
    def send(self, message: str) -> None: ...


@dataclass(frozen=True)
class NotificationResult:
    component: str
    health: str
    state_path: Path
    notification_attempted: bool
    notification_sent: bool
    notification_pending: bool
```

Implement the sender with `subprocess.run()` using an argument list, no shell,
JSON on standard input, and the protected curl config as the URL source:

```python
payload = json.dumps(
    {
        "content": message,
        "allowed_mentions": {"parse": []},
    },
    ensure_ascii=False,
).encode("utf-8")
command = [
    "curl",
    "--disable",
    "--config", str(self.curl_config_path),
    "--silent",
    "--show-error",
    "--fail",
    "--connect-timeout", "10",
    "--max-time", "30",
    "--request", "POST",
    "--header", "Content-Type: application/json",
    "--data-binary", "@-",
]
```

Require exit code zero; bound captured stderr before raising. Never include the
curl-config contents or command URL in the error. The external curl config must
contain the Discord webhook URL with `wait=true` so success confirms message
creation. Validate that secret URL before invoking curl, but continue to let
curl read it from the config so it never appears in the process argument list.

- [x] **Step 4: Run the notification tests**

Run:

```bash
python -m pytest tests/test_pipeline_notifications.py -q
```

Expected: all tests pass.

- [x] **Step 5: Review the Task 2 diff**

Run `git diff --check` and inspect the two Task 2 files. Confirm message
construction cannot create mentions, webhook secrets never enter logs/state,
and a failed notification does not erase prior failure state. Do not stage or
commit unless explicitly requested; the conditional commit message is
`Add pipeline failure notifications`.

---

### Task 3: Conditional Create-Only WebDAV Delivery

**Files:**

- Create: `app/artifact_delivery.py`
- Create: `tests/test_artifact_delivery.py`

**Interfaces:**

- Consumes `QueuedArtifact`, `CATEGORY_REMOTE_FOLDERS`,
  `snapshot_queue_entries()`, `load_queued_artifact()`, malformed-evidence
  quarantine, and delivered-cleanup reaping from Task 1.
- Consumes `DiscordWebhookSender`, `record_component_failure()`, and
  `record_component_success()` from Task 2.
- Produces:
  `upload_create_only(artifact: QueuedArtifact, config: DeliveryConfig, *, runner: CurlRunner = run_curl) -> UploadResult`
- Produces:
  `deliver_pending(config: DeliveryConfig, *, runner: CurlRunner = run_curl, notifier: NotificationSender | None = None) -> DeliveryBatchResult`
- Produces immutable `UploadResult` fields `state`, `http_status`, and
  `remote_url`, where state is `created` or `already-present`.
- Produces immutable `DeliveryBatchResult` fields `created_count`,
  `already_present_count`, `failed_count`, and `pending_count`.
- Produces CLI: `python -m app.artifact_delivery deliver`.

- [x] **Step 1: Write transport tests before implementation**

Use a fake subprocess runner that records the argument list and returns
controlled stdout/status:

```python
class RecordingCurlRunner:
    def __init__(self, *, returncode: int, stdout: str, stderr: str = ""):
        self.result = CurlResult(returncode, stdout, stderr)
        self.calls: list[tuple[list[str], bytes | None]] = []

    def __call__(self, command, *, input_bytes=None):
        self.calls.append((list(command), input_bytes))
        return self.result


def test_upload_is_conditional_create_only(queued_artifact, delivery_config):
    runner = RecordingCurlRunner(returncode=0, stdout="201")

    result = upload_create_only(
        queued_artifact,
        delivery_config,
        runner=runner,
    )

    assert result.state == "created"
    command, input_bytes = runner.calls[0]
    assert input_bytes is None
    assert command[command.index("--request") + 1] == "PUT"
    assert command[command.index("--header") + 1] == "If-None-Match: *"
    assert str(queued_artifact.payload_path) in command
    assert queued_artifact.remote_filename in command[-1]
    assert not any(
        method in command
        for method in ("GET", "PROPFIND", "DELETE", "MOVE", "COPY")
    )
```

Add cases for:

- URL quoting each fixed path segment and filename without accepting an
  arbitrary remote root;
- HTTP `201` as the only confirmed creation response;
- HTTP `412` as idempotent prior delivery only for the checksum-bearing name;
- HTTP `200`, `204`, and every other status as failure with the queue item
  retained;
- nonzero curl exit as a bounded transport failure;
- `--disable` as the first curl option plus fixed connection/transfer bounds;
- `--config /etc/extrusion-terminal/hetzner-webdav.conf` with no credential in
  arguments;
- rejection when that config contains anything other than exactly one `user`
  directive, without reproducing its value in the error;
- queue-item removal after success or idempotent delivery;
- payload retention after HTTP/transport failure;
- a 25-item maximum oldest-first batch;
- malformed queue items retained while later valid items are still attempted;
  and
- the first WebDAV transport/authentication/permission/unexpected-response
  failure stops further remote attempts for that run.

- [x] **Step 2: Run the delivery tests and confirm failure**

Run:

```bash
python -m pytest tests/test_artifact_delivery.py -q
```

Expected: collection fails because `app.artifact_delivery` does not exist.

- [x] **Step 3: Implement fixed configuration and URL construction**

Use this dataclass and production defaults:

```python
@dataclass(frozen=True)
class DeliveryConfig:
    outbox_dir: Path
    state_dir: Path
    webdav_base_url: str
    webdav_root: tuple[str, ...]
    webdav_curl_config: Path
    discord_curl_config: Path


DEFAULT_WEBDAV_BASE_URL = (
    "https://nx106226.your-storageshare.de/remote.php/dav/files/"
    "extrusion-backup"
)
DEFAULT_WEBDAV_ROOT = (
    "system-backups",
    "extrusion-terminal",
    "production-data",
)
DEFAULT_WEBDAV_CURL_CONFIG = Path(
    os.getenv(
        "EXTRUSION_WEBDAV_CURL_CONFIG",
        "/etc/extrusion-terminal/hetzner-webdav.conf",
    )
)
MAX_DELIVERY_ITEMS_PER_RUN = 25
```

Define the result dataclasses beside `DeliveryConfig`:

```python
@dataclass(frozen=True)
class UploadResult:
    state: Literal["created", "already-present"]
    http_status: int
    remote_url: str


@dataclass(frozen=True)
class DeliveryBatchResult:
    created_count: int
    already_present_count: int
    failed_count: int
    pending_count: int
```

Permit environment overrides for local outbox/state paths and protected config
file paths only. Keep the approved host/base/root and category routing fixed in
source for this bounded task. Build the URL with `urllib.parse.quote(segment,
safe="")` for every category/filename segment.

- [x] **Step 4: Implement the curl upload and batch worker**

Construct only this operation shape:

```python
command = [
    "curl",
    "--disable",
    "--config", str(config.webdav_curl_config),
    "--silent",
    "--show-error",
    "--output", "/dev/null",
    "--write-out", "%{http_code}",
    "--connect-timeout", "10",
    "--max-time", "120",
    "--request", "PUT",
    "--upload-file", str(artifact.payload_path),
    "--header", "If-None-Match: *",
    remote_url,
]
```

Run without a shell. Accept only `201` or checksum-name `412` according to the
test contract. Treat `200`, `204`, or any other response as failure. Before
upload, validate payload size/hash against metadata. After success, atomically
move the item to cleanup and reap it idempotently; on failure leave the complete
pending item untouched.

`deliver_pending()` must obtain one oldest-first snapshot from
`snapshot_queue_entries()` and process no more than
`MAX_DELIVERY_ITEMS_PER_RUN`. Load each item independently and retain/continue
past malformed local items after durable quarantine. After the first WebDAV
transport, authentication,
permission, or unexpected-response failure, retain that item and stop further
remote attempts for the run. Report the first bounded error plus total pending
count through component `webdav-delivery`, and return nonzero from the CLI when
any processed item is invalid or undelivered. After at least one real or
idempotent upload succeeds and no processed item fails, record component
success/recovery.

- [x] **Step 5: Run Tasks 1-3 tests**

Run:

```bash
python -m pytest \
  tests/test_artifact_outbox.py \
  tests/test_pipeline_notifications.py \
  tests/test_artifact_delivery.py \
  -q
```

Expected: all tests pass.

- [x] **Step 6: Perform the forbidden-operation source check**

Run:

```bash
rg -n 'PROPFIND|DELETE|MOVE|COPY|--request.*GET|--request.*HEAD' \
  app/artifact_delivery.py app/artifact_outbox.py
```

Expected: no matches. The tests may name forbidden methods as assertions; the
implementation may not contain them.

- [x] **Step 7: Review the Task 3 diff**

Confirm `412` cannot be accepted for a name lacking the complete recorded
digest, source files remain untouched, credentials stay outside arguments, and
the CLI communicates failures through exit status. Do not stage or commit
unless explicitly requested; the conditional commit message is
`Add create-only WebDAV delivery`.

---

### Task 4: SQLite Backup Producer

**Files:**

- Create: `app/backup_job.py`
- Create: `tests/test_backup_job.py`

**Interfaces:**

- Consumes `app.backups.create_backup()` and its `BackupResult`.
- Consumes `enqueue_artifact()` from Task 1.
- Consumes Task 2 notification functions for component `database-backup`.
- Produces:
  `run_backup_job(*, source_db_path: Path | str | None = None, backup_dir: Path | str | None = None, outbox_dir: Path | str | None = None, keep_count: int = 144, notifier: NotificationSender | None = None, state_dir: Path | str | None = None) -> BackupJobResult`
- Produces CLI: `python -m app.backup_job`.

- [x] **Step 1: Write the backup-job tests**

Create a temporary SQLite database and assert the complete producer boundary:

```python
class RecordingSender:
    def __init__(self):
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)


def test_backup_job_creates_retains_and_queues_safe_image(tmp_path):
    source = tmp_path / "source.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample VALUES ('preserved')")

    result = run_backup_job(
        source_db_path=source,
        backup_dir=tmp_path / "backups",
        outbox_dir=tmp_path / "outbox",
        state_dir=tmp_path / "state",
        notifier=RecordingSender(),
    )

    assert result.backup_path.exists()
    assert result.queued_artifact.category == "database-backups"
    assert result.queued_artifact.payload_path.exists()
    with sqlite3.connect(result.backup_path) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "preserved"
```

Add tests proving:

- the wrapper passes keep count `144` by default;
- a backup/validation failure enqueues nothing, reports
  `database-backup` failure, and exits nonzero;
- an enqueue failure leaves the validated local backup intact, reports failure,
  and exits nonzero;
- the next success reports one recovery;
- no raw `shutil.copy*` of the live source exists in `app/backup_job.py`; and
- the test's resolved source path differs from the real runtime database.

- [x] **Step 2: Run the backup-job tests and confirm failure**

Run:

```bash
python -m pytest tests/test_backup_job.py -q
```

Expected: collection fails because `app.backup_job` does not exist.

- [x] **Step 3: Implement the orchestration wrapper**

Build `BackupJobResult` from the existing backup and outbox results:

```python
@dataclass(frozen=True)
class BackupJobResult:
    backup_path: Path
    queued_artifact: QueuedArtifact
    retained_paths: tuple[Path, ...]
    removed_paths: tuple[Path, ...]
```

The operation order must be exactly:

```python
backup_result = create_backup(
    source_db_path=source_db_path,
    backup_dir=backup_dir,
    keep_count=keep_count,
)
queued = enqueue_artifact(
    backup_result.backup_path,
    "database-backups",
    outbox_dir=outbox_dir,
)
record_component_success(
    "database-backup",
    state_dir=state_dir,
    notifier=notifier,
    context={"backup": backup_result.backup_path.name},
)
```

Catch and locally report a bounded exception from backup creation or enqueue,
call `record_component_failure()`, print no secret configuration, and exit the
CLI with status 1. Do not call the WebDAV worker from this module; delivery is
independently scheduled.

- [x] **Step 4: Run backup and regression tests**

Run:

```bash
python -m pytest \
  tests/test_backup_job.py \
  tests/test_backup_recovery.py \
  -q
```

Expected: all tests pass.

- [x] **Step 5: Review the Task 4 diff**

Confirm the source database is passed only into `create_backup()`, local
retention cannot see the separate outbox, and a delivery outage cannot undo or
mark a successfully queued backup creation as failed. Do not stage or commit
unless explicitly requested; the conditional commit message is
`Queue validated production backups`.

---

### Task 5: Source-Controlled Systemd Scheduling And Installer

**Files:**

- Create: `deployment/systemd/extrusion-terminal-backup.service`
- Create: `deployment/systemd/extrusion-terminal-backup.timer`
- Create: `deployment/systemd/extrusion-terminal-delivery.service`
- Create: `deployment/systemd/extrusion-terminal-delivery.timer`
- Create: `scripts/install_artifact_delivery.sh`
- Create: `tests/test_artifact_delivery_operations.py`
- Modify: `scripts/deploy_production.sh`

**Interfaces:**

- Backup service invokes `/opt/extrusion-terminal/app/.venv/bin/python -m
  app.backup_job` as `sk` under a non-blocking shared operation lock.
- Delivery service invokes `/opt/extrusion-terminal/app/.venv/bin/python -m
  app.artifact_delivery deliver` as `sk` under the same shared lock.
- Backup timer runs on `*:0/10`; delivery timer runs one minute after boot and
  one minute after each inactive transition.
- Backup and delivery services have five- and ten-minute runtime ceilings,
  respectively.
- Installer creates runtime directories, installs only the four tracked units,
  reloads systemd, and enables both timers only during an explicitly authorized
  normal invocation.
- The production deploy script takes the same operation lock exclusively before
  its backup/update/verification/restart sequence when Task 25 is installed.

- [x] **Step 1: Write static operational-contract tests**

Create tests that parse the tracked files as text and assert:

```python
def test_backup_timer_is_ten_minutes_and_persistent():
    timer = Path(
        "deployment/systemd/extrusion-terminal-backup.timer"
    ).read_text(encoding="utf-8")
    assert "OnCalendar=*:0/10" in timer
    assert "Persistent=true" in timer
    assert "Unit=extrusion-terminal-backup.service" in timer


def test_services_are_one_shot_and_use_paths_outside_checkout():
    backup = Path(
        "deployment/systemd/extrusion-terminal-backup.service"
    ).read_text(encoding="utf-8")
    delivery = Path(
        "deployment/systemd/extrusion-terminal-delivery.service"
    ).read_text(encoding="utf-8")
    assert "Type=oneshot" in backup
    assert "Type=oneshot" in delivery
    assert "User=sk" in backup and "User=sk" in delivery
    assert "/opt/extrusion-terminal/artifact-delivery" in backup
    assert "/opt/extrusion-terminal/artifact-delivery" in delivery
    assert "flock --shared --nonblock" in backup
    assert "flock --shared --nonblock" in delivery
    assert "TimeoutStartSec=5min" in backup
    assert "TimeoutStartSec=10min" in delivery
    assert "EnvironmentFile=" not in backup
    assert "EnvironmentFile=" not in delivery
```

Also assert the installer has `set -Eeuo pipefail`, a `--dry-run` path that
does not invoke `install` or `systemctl`, mode/owner checks for both protected
curl configs, explicit directory targets, no creation or reading of secret
files, and only the four allowlisted unit names. Assert that it creates the
non-secret operation-lock file with owner/group `sk` and mode `0640`. Assert the
normal deploy script acquires that file exclusively before its production
backup, does not create Task 25 runtime state before Task 25 is installed, and
fails if Task 25 units exist but their required lock file is missing.

- [x] **Step 2: Run the operational tests and confirm missing-file failures**

Run:

```bash
python -m pytest tests/test_artifact_delivery_operations.py -q
```

Expected: failures report the absent unit and installer files.

- [x] **Step 3: Create the systemd units**

Use this backup unit:

```ini
[Unit]
Description=Create and queue an Extrusion Terminal SQLite backup
After=local-fs.target

[Service]
Type=oneshot
User=sk
Group=sk
TimeoutStartSec=5min
WorkingDirectory=/opt/extrusion-terminal/app
Environment=EXTRUSION_DB_PATH=/opt/extrusion-terminal/data/extrusion_terminal.sqlite3
Environment=EXTRUSION_BACKUP_DIR=/opt/extrusion-terminal/backups
Environment=EXTRUSION_BACKUP_KEEP_COUNT=144
Environment=EXTRUSION_ARTIFACT_OUTBOX_DIR=/opt/extrusion-terminal/artifact-delivery/outbox
Environment=EXTRUSION_ARTIFACT_STATE_DIR=/opt/extrusion-terminal/artifact-delivery/state
Environment=EXTRUSION_DISCORD_CURL_CONFIG=/etc/extrusion-terminal/discord-webhook.conf
ExecStart=/usr/bin/flock --shared --nonblock /opt/extrusion-terminal/artifact-delivery/operation.lock /opt/extrusion-terminal/app/.venv/bin/python -m app.backup_job
```

Use a calendar timer with:

```ini
[Timer]
OnCalendar=*:0/10
Persistent=true
AccuracySec=1s
Unit=extrusion-terminal-backup.service
```

The delivery unit uses the same user, working directory, outbox/state/Discord
variables, adds
`EXTRUSION_WEBDAV_CURL_CONFIG=/etc/extrusion-terminal/hetzner-webdav.conf`, and
invokes `python -m app.artifact_delivery deliver` through the same shared,
non-blocking lock. Give it `TimeoutStartSec=10min`. Its timer uses:

```ini
[Timer]
OnBootSec=1min
OnUnitInactiveSec=1min
AccuracySec=10s
Unit=extrusion-terminal-delivery.service
```

Both timers use `WantedBy=timers.target`. Do not add restart loops or a
long-running service.

- [x] **Step 4: Implement the installer and deployment lock**

`scripts/install_artifact_delivery.sh` must:

1. resolve `/opt/extrusion-terminal/app` and confirm its `.venv` and new Python
   modules exist;
2. verify user/group `sk`;
3. verify both `/etc/extrusion-terminal/*.conf` files are regular, owned by
   `sk`, not group/world accessible, and never print their contents;
4. create `/opt/extrusion-terminal/artifact-delivery`, `outbox`, and `state`
   with owner/group `sk` and mode `0750`, then create the non-secret
   `operation.lock` if absent with owner/group `sk` and mode `0640`;
5. confirm `/usr/bin/flock` is available;
6. install exactly the four tracked files to `/etc/systemd/system` with mode
   `0644`;
7. run `systemd-analyze verify` on the installed units;
8. run `systemctl daemon-reload`; and
9. run `systemctl enable --now` for the two timers only after every prior step
   succeeds.

`--dry-run` prints resolved non-secret paths and intended unit names, performs
read-only preflight checks, and exits before directory creation, file install,
daemon reload, or timer enablement.

Modify `scripts/deploy_production.sh` so a normal deploy checks whether either
Task 25 service unit is installed. If neither is installed, continue exactly as
before so source can be deployed before Task 25 activation. If either exists,
require the operation-lock file, open it without truncating it, and acquire an
exclusive lock with a bounded wait before the script's SQLite-safe backup. Hold
the lock through checkout update, dependency installation, verification, app
restart, and final health/revision checks; shell exit releases it. Dry-run mode
reports this non-secret coordination state but does not acquire or create the
lock. Scheduled service commands take shared non-blocking locks, so they can run
together normally but skip safely while deployment holds the exclusive lock.
Use flock conflict exit code `75` and declare only `SuccessExitStatus=75` in the
units. The Python CLIs reserve exit code `1` for real job failures, which must
remain visible to systemd.

- [x] **Step 5: Run syntax, calendar, and operational tests**

Run:

```bash
bash -n scripts/install_artifact_delivery.sh
bash -n scripts/deploy_production.sh
systemd-analyze calendar '*:0/10'
python -m pytest tests/test_artifact_delivery_operations.py -q
```

Expected: both Bash syntax checks pass; systemd normalizes the expression to
every ten minutes; all source-contract tests pass. Do not install the units
locally or in production during source verification.

- [x] **Step 6: Review the Task 5 diff**

Confirm the installer has no broad recursive deletion, does not change the app
service, never echoes secrets, and cannot partially enable one timer before
preflight/unit validation completes. Confirm normal deployment either operates
without Task 25 installed or holds the required exclusive lock for its complete
mutable production phase. Do not stage or commit unless explicitly requested;
the conditional commit message is
`Add artifact delivery timers and installer`.

---

### Task 6: Production Runbook And Authority Reconciliation

**Files:**

- Create: `docs/production-artifact-delivery.md`
- Create: `docs/implementation-notes/production-artifact-delivery.md`
- Modify: `README.md`
- Modify: `docs/production-deployment.md`
- Modify: `docs/INFRASTRUCTURE_IMPLEMENTATION_PLAN.md`
- Modify: `v2-files/TASK-25-PRODUCTION-ARTIFACT-DELIVERY.md`
- Modify: `v2-files/PLAN.md`

**Interfaces:**

- Documents the source behavior without claiming production enablement.
- Gives one separate, explicit production-authorization gate.
- Preserves the unchanged manual restore command and Task 20/24 boundaries.

- [x] **Step 1: Write the operator runbook**

Document these exact sections in `docs/production-artifact-delivery.md`:

- fixed production paths, WebDAV base/root, and three category folders;
- required `database-backups/` manual folder creation;
- protected existing Hetzner curl config validation without displaying it;
- Discord incoming-webhook creation and a mode-`0600` curl config whose URL
  includes `wait=true`;
- dry-run installer command;
- explicitly authorized normal installation command;
- manual `systemctl start` commands for delivery and backup;
- `systemctl list-timers` and `journalctl` observation commands;
- expected local backup, outbox, and remote results;
- exact `201`/checksum-named `412` acceptance, `200`/`204` rejection, finite
  batch size, and timeout behavior;
- failure meaning, automatic retry, warning suppression, and recovery message;
- operation-lock behavior during normal production deployment;
- safe disablement of both timers without deleting anything;
- removal/revocation procedure for the Discord webhook secret;
- unchanged manual restore to a scratch database first; and
- a statement that dead-server monitoring is external and not supplied here.

Do not include real passwords, webhook URLs, or a command that prints either
config file.

- [x] **Step 2: Reconcile existing documentation**

Update `README.md` to state that Task 25 source supplies the approved scheduler
and Hetzner delivery only after it is implemented, and separately record
whether production timers remain uninstalled. Link the new runbook from the
operational section.

Update `docs/production-deployment.md` so normal app deployment remains
independent from the separately authorized timer installer. A code deploy must
not automatically enable new infrastructure, but once Task 25 units exist it
must use the shared operation lock described above.

Replace the planning-only supersession and historical Phase 7 sketch in
`docs/INFRASTRUCTURE_IMPLEMENTATION_PLAN.md` with a short final-source notice
and link to the Task 25 runbook. Do not restore its old timer as a competing
definition.

Update the Task 25/PLAN status only to the verified source state actually
reached. Preserve Task 24 as a separate future producer and Task 18 as wholly
independent.

- [x] **Step 3: Record the completed implementation and migration assessment**

In `docs/implementation-notes/production-artifact-delivery.md`, record:

- implemented module and unit boundaries;
- exact fixed categories and paths;
- conditional PUT response/idempotence behavior and its sole-writer assumption;
- transfer/process/service timeouts, batch bound, and deployment operation lock;
- local source versus disposable queue-copy ownership;
- notification state transitions;
- verification commands/results;
- `No migration` for the first slice because production SQLite schema and data
  meaning are unchanged; and
- `Not deployed` until a separately authorized production operation succeeds.

- [x] **Step 4: Run documentation consistency checks**

Run:

```bash
rg -n 'Milestone 8 does not install a scheduler|Phase 7 - Configure Backups|TASK-13-BACKUP-RESILIENCE.md' \
  README.md docs v2-files AGENTS.md
rg -n 'Task 18|Task 24|Task 25|Hetzner|Discord|144|ten minutes|10 minutes' \
  README.md docs/production-artifact-delivery.md \
  docs/implementation-notes/production-artifact-delivery.md \
  v2-files/PLAN.md v2-files/TASK-25-PRODUCTION-ARTIFACT-DELIVERY.md
```

Expected: old scheduler/Task 13 references are either removed or explicitly
historical; Task 18 stays independent; Task 24 owns report logic; Task 25 owns
delivery and backup.

- [x] **Step 5: Review the Task 6 diff**

Check that no source-ready statement claims timers are active, no future PDF
logic is described as implemented, and no deployment authorization is implied.
Do not stage or commit unless explicitly requested; the conditional commit
message is `Document production artifact delivery`.

---

### Task 7: Complete Source Verification And Review

**Files:**

- Modify only files required to correct failures found by this task.

**Interfaces:**

- Consumes the complete Tasks 1-6 source candidate.
- Produces reviewed source that remains uninstalled and undeployed.

- [x] **Step 1: Run syntax and static safety checks**

Run:

```bash
source .venv/bin/activate
python -m compileall -q app tests
bash -n scripts/install_artifact_delivery.sh
bash -n scripts/deploy_production.sh
systemd-analyze calendar '*:0/10'
rg -n 'PROPFIND|DELETE|MOVE|COPY|--request.*GET|--request.*HEAD' \
  app/artifact_outbox.py app/artifact_delivery.py app/backup_job.py
git diff --check
```

Expected: syntax/calendar/diff checks pass and the forbidden-operation search
has no matches.

- [x] **Step 2: Run the complete automated suite once**

Run:

```bash
python -m pytest
```

Expected: all repository tests pass using temporary database paths.

- [x] **Step 3: Inspect the complete diff and worktree ownership**

Run:

```bash
git status --short
git diff --stat
git diff --check
```

Confirm the Task 20 temporary file and Task 24 producer record remain unchanged,
no secret/runtime payload is tracked, and no unrelated refactor is present.

- [x] **Step 4: Stop at the production authorization gate**

Report source verification separately from deployment. Do not create the real
Discord webhook, create remote folders, install units, enable timers, start a
production backup, upload a real database backup, or run a production restore
without the user's explicit operational authorization.

If source changes are accepted and the user explicitly requests a commit, add
only reviewed Task 25 files and use the message
`Add append-only production backup delivery`.

---

## Approved Post-Review Hardening

The September 14 adversarial review found concrete crash, notification,
queue-progress, and privileged-installation gaps. The user approved this
bounded hardening pass before merge. The following rulings constrain the work:

- Preserve the fixed append-only WebDAV contract. Do not add remote reads,
  listings, overwrite, deletion, movement, retention, download, or automatic
  restore.
- Preserve the current `/opt/extrusion-terminal` layout, but make the runtime
  and maintenance trust anchors non-renamable by `sk`; only the exact runtime
  children that jobs must write may be owned by `sk`.
- If a failure warning could not be delivered before recovery, send one
  combined failure-and-recovery notification containing the original bounded
  error and both timestamps. Do not emit two delayed messages for one already
  recovered incident.
- A failed enqueue may leave one validated local image absent from the remote
  series. This is accepted because the failure is reported and the next
  ten-minute run creates a newer snapshot. Do not add a historical backup
  registry or reconciliation service.
- Keep checksum-named `412` under the approved sole-writer assumption for source
  merge. An explicitly authorized disposable interrupted-upload check remains a
  production-activation gate; source verification must not contact Hetzner.
- Discord delivery is at-least-once across a process crash. Do not mark an
  event sent before the webhook confirms it merely to suppress rare duplicate
  messages.
- Systemd sandbox expansion is optional production hardening, not a merge
  requirement. Add only directives verified compatible with the actual VM.

### Task 8: Atomic Validated Backup Publication

- [x] Add a regression test proving an interrupted/unvalidated backup cannot
  enter the final-name retention set or displace a validated image.
- [x] Back up to a non-retention staging name, validate and fsync it, then
  atomically publish the final name and fsync the backup directory before
  retention.
- [x] Retain and report stale staging residue without counting it among the 144
  validated images; never mutate the production database in tests.
- [x] Run `tests/test_backup_recovery.py` and `tests/test_backup_job.py`.

### Task 9: Confirmed And Observable Discord State

- [x] Add failing tests for confirmed `200` plus a bounded saved-message ID,
  empty/malformed `200`, `204`, redirects, nonzero curl, and oversized output.
- [x] Add failing state-machine tests for an unsent failure followed by
  recovery, a failed recovery send retried on an empty delivery run, and
  notification errors that remain visible without exposing secrets.
- [x] Require a confirmed Discord response; implement the approved combined
  failure-and-recovery event; preserve primary pipeline outcomes separately
  from notification/state outcomes.
- [x] Bound notification-state reads and stored diagnostic fields. Read state,
  queue metadata, and protected curl configuration through a no-follow,
  regular-file-only descriptor reader that stops at the configured cap plus
  one byte and handles legal short reads through EOF.
- [x] Run `tests/test_pipeline_notifications.py`,
  `tests/test_artifact_delivery.py`, and `tests/test_backup_job.py`.

### Task 10: Crash-Safe Queue Health And Progress

- [x] Add failing tests for unexpected pending entries/categories, stale
  staging, a non-directory category root, 25 malformed oldest items followed by
  one valid item, and interruption at every delivered-cleanup boundary.
- [x] Report and retain malformed evidence outside active delivery ordering so
  it cannot starve valid work. Never silently delete an undelivered item.
- [x] Atomically move confirmed deliveries to a cleanup/tombstone area before
  idempotent local reaping.
- [x] Bound filename/metadata input and queue discovery memory, and distinguish
  pre-publication enqueue failure from failure to confirm post-publication
  directory durability.
- [x] Add an internal monotonic delivery budget below the systemd ceiling so a
  worker does not deliberately begin work that only systemd can terminate.
- [x] Run the outbox, delivery, notification, and backup-job focused tests.

### Task 11: Safe Installation, Deployment, Acceptance, And Restore

- [x] Add an isolated behavioral installer harness proving symlink sentinels
  are untouched, source units are verified before live mutation, failure leaves
  the previous installation or an explicit disabled state, and reruns are
  idempotent.
- [x] Establish a protected maintenance/runtime anchor, validate every existing
  path component, and give `sk` ownership only where runtime writes require it.
- [x] Install units without starting schedules. Validate protected config
  content without displaying it, then make timer enablement a separate command
  after authorized disposable acceptance.
- [x] Serialize first installation with deployment and ensure a failed deploy
  cannot release active Task 25 timers onto an unverified checkout.
- [x] Rewrite the runbook sequence so disposable WebDAV `201`/identical `412`
  and Discord acceptance precede timer enablement and the first production
  backup.
- [x] Require both one-shot services and the app to be quiescent, with the
  maintenance and operation locks acquired in that order before an actual
  manual restore.
- [x] Run the isolated installer behavioral harness, deploy coordination
  contract tests, Bash syntax checks, and `systemd-analyze verify` without
  installing units.

### Task 12: Hardening Verification And Review

- [x] Run Python compile/import checks, the complete focused Task 25 and backup
  recovery suite, the complete repository suite, Bash syntax,
  `systemd-analyze verify`, timer calendar parsing, the forbidden WebDAV-method
  scan, and `git diff --check`.
- [x] Review the complete Task 25 diff for data integrity, secret handling,
  append-only behavior, crash recovery, deployment safety, and scope.
- [x] Keep production closed. Report source readiness separately and do not
  stage, commit, merge, install, enable, deploy, or contact external services
  without the corresponding explicit authorization.

## Separate Production Acceptance After Explicit Authorization

This section is not part of ordinary source execution. Follow
`docs/production-artifact-delivery.md` only after the user authorizes the
maintenance operation.

1. Confirm the deployed revision contains the accepted Task 25 source.
2. Confirm `database-backups/` exists under the fixed Hetzner root.
3. Create and protect the Discord curl config without displaying its URL.
4. Run the installer in dry-run mode and review all resolved paths.
5. Install and verify the four units while leaving both timers disabled.
6. Enqueue a harmless disposable file and verify a `201` conditional create;
   enqueue the identical checksum-bearing name again and verify `412` is handled
   as idempotent prior delivery. Abort one deliberately rate-limited disposable
   PUT and prove its full retry receives `201`, not a partial-object `412`.
   Confirm Discord notification against the real service and retain/diagnose
   any unexpected `200` or `204`.
7. Run the separate verified-unit enable command for the two timers.
8. Start one production backup service and confirm SQLite validation, local
   retention, queue drain, remote filename, and journal state.
9. Wait through at least one scheduled ten-minute backup and one retry-worker
   interval.
10. Restore one manually downloaded backup only to a separate scratch database,
   validate it, and leave the running production database untouched.
11. Record the active timer/unit status and exact deployed revision in the
    implementation note.
