from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Protocol
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from . import db
from .bounded_files import read_bounded_regular_file
from .curl_transport import CurlRunner, run_curl, validate_curl_config


ALLOWED_COMPONENTS = frozenset(
    {"database-backup", "database-backup-freshness", "webdav-delivery"}
)
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
NOTIFICATION_STATE_SCHEMA_VERSION = 2
_STATE_KEYS = frozenset(
    {
        "schema_version",
        "component",
        "health",
        "first_failed_at_utc",
        "last_attempt_at_utc",
        "first_error",
        "last_error",
        "failure_notice_sent",
        "recovery_notice_pending",
        "notification_attempted_at_utc",
        "notification_error",
    }
)
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
_MESSAGE_LIMIT = 1_800
_ERROR_LIMIT = 500
_NOTIFICATION_ERROR_LIMIT = 100
_CONTEXT_ITEM_LIMIT = 200
_MAX_STATE_BYTES = 16 * 1024
_MAX_DISCORD_RESPONSE_BYTES = 64 * 1024
_DISCORD_MESSAGE_ID_PATTERN = re.compile(r"[0-9]{1,32}")


class NotificationSender(Protocol):
    def send(self, message: str) -> None: ...


class DiscordNotificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class NotificationResult:
    component: str
    health: str
    state_path: Path
    notification_attempted: bool
    notification_sent: bool
    notification_pending: bool
    notification_error: str | None = None


class DiscordWebhookSender:
    def __init__(
        self,
        curl_config_path: Path | str = DEFAULT_DISCORD_CURL_CONFIG,
        runner: CurlRunner = run_curl,
    ) -> None:
        self.curl_config_path = Path(curl_config_path)
        self.runner = runner

    def send(self, message: str) -> None:
        config = validate_discord_webhook_config(self.curl_config_path)
        webhook_url = config["url"]
        secret_parts = _validate_discord_webhook_url(webhook_url)
        payload = json.dumps(
            {
                "content": message[:_MESSAGE_LIMIT],
                "allowed_mentions": {"parse": []},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        command = [
            "curl",
            "--disable",
            "--config",
            str(self.curl_config_path),
            "--silent",
            "--show-error",
            "--fail",
            "--connect-timeout",
            "10",
            "--max-time",
            "30",
            "--max-filesize",
            str(_MAX_DISCORD_RESPONSE_BYTES),
            "--write-out",
            "\n%{http_code}",
            "--request",
            "POST",
            "--header",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
        ]
        try:
            result = self.runner(command, input_bytes=payload)
        except Exception as error:
            raise DiscordNotificationError(
                "Discord notification process did not complete."
            ) from error
        if result.returncode != 0:
            diagnostic = _redact_transport_diagnostic(
                result.stderr,
                webhook_url=webhook_url,
                secret_parts=secret_parts,
            )
            raise DiscordNotificationError(
                f"Discord notification failed with curl exit {result.returncode}: {diagnostic}"
            )
        _validate_discord_confirmation(result.stdout)


def validate_discord_webhook_config(path: Path | str) -> Mapping[str, str]:
    """Validate the protected Discord curl config without sending a request."""
    config = validate_curl_config(
        path,
        required_options=frozenset({"url"}),
        allowed_options=frozenset({"url"}),
    )
    _validate_discord_webhook_url(config["url"])
    return config


def record_component_failure(
    component: str,
    error: str,
    *,
    state_dir: Path | str | None = None,
    notifier: NotificationSender | None = None,
    now: datetime | None = None,
    context: Mapping[str, object] | None = None,
    notification_grace: timedelta = timedelta(0),
) -> NotificationResult:
    _validate_component(component)
    _validate_notification_grace(notification_grace)
    timestamp = _format_utc_timestamp(now)
    state_path = _state_path(component, state_dir)
    previous = _load_state(state_path, component)
    _reject_future_state(previous, timestamp, state_path)
    incident_open = (
        previous["health"] == "failing"
        or previous["recovery_notice_pending"]
    )
    safe_error = _sanitize_text(error, _ERROR_LIMIT)
    state = {
        "schema_version": NOTIFICATION_STATE_SCHEMA_VERSION,
        "component": component,
        "health": "failing",
        "first_failed_at_utc": (
            previous["first_failed_at_utc"] if incident_open else timestamp
        ),
        "last_attempt_at_utc": timestamp,
        "first_error": previous["first_error"] if incident_open else safe_error,
        "last_error": safe_error,
        "failure_notice_sent": (
            previous["failure_notice_sent"] if incident_open else False
        ),
        "recovery_notice_pending": False,
        "notification_attempted_at_utc": previous["notification_attempted_at_utc"],
        "notification_error": previous["notification_error"],
    }
    _write_state(state_path, state)

    attempted = False
    sent = False
    notification_error = None
    grace_elapsed = _incident_age(state, timestamp) >= notification_grace
    if not state["failure_notice_sent"] and grace_elapsed:
        attempted = True
        state["notification_attempted_at_utc"] = timestamp
        message = _build_message("FAILED", state, context)
        try:
            _resolve_notifier(notifier).send(message)
        except Exception as error:
            notification_error = _notification_error(error)
            state["notification_error"] = notification_error
            _write_state(state_path, state)
            _report_notification_failure(component, "FAILED", notification_error)
        else:
            sent = True
            state["failure_notice_sent"] = True
            state["notification_error"] = None
            _write_state(state_path, state)

    return NotificationResult(
        component=component,
        health="failing",
        state_path=state_path,
        notification_attempted=attempted,
        notification_sent=sent,
        notification_pending=not state["failure_notice_sent"],
        notification_error=notification_error,
    )


def record_component_success(
    component: str,
    *,
    state_dir: Path | str | None = None,
    notifier: NotificationSender | None = None,
    now: datetime | None = None,
    context: Mapping[str, object] | None = None,
    notification_grace: timedelta = timedelta(0),
) -> NotificationResult:
    _validate_component(component)
    _validate_notification_grace(notification_grace)
    timestamp = _format_utc_timestamp(now)
    state_path = _state_path(component, state_dir)
    previous = _load_state(state_path, component)
    _reject_future_state(previous, timestamp, state_path)
    incident_was_failing = previous["health"] == "failing"
    recovery_pending = bool(previous["recovery_notice_pending"])
    if incident_was_failing:
        incident_qualified = (
            previous["failure_notice_sent"]
            or previous["notification_attempted_at_utc"] is not None
            or _incident_age(previous, timestamp) >= notification_grace
        )
        recovery_pending = bool(incident_qualified)
    state = {
        "schema_version": NOTIFICATION_STATE_SCHEMA_VERSION,
        "component": component,
        "health": "healthy",
        "first_failed_at_utc": previous["first_failed_at_utc"],
        "last_attempt_at_utc": timestamp,
        "first_error": previous["first_error"],
        "last_error": previous["last_error"],
        "failure_notice_sent": previous["failure_notice_sent"],
        "recovery_notice_pending": recovery_pending,
        "notification_attempted_at_utc": previous["notification_attempted_at_utc"],
        "notification_error": previous["notification_error"],
    }
    _write_state(state_path, state)

    attempted = False
    sent = False
    notification_error = None
    if state["recovery_notice_pending"]:
        attempted = True
        state["notification_attempted_at_utc"] = timestamp
        status = "RECOVERED" if state["failure_notice_sent"] else "FAILED AND RECOVERED"
        message = _build_message(status, state, context)
        try:
            _resolve_notifier(notifier).send(message)
        except Exception as error:
            notification_error = _notification_error(error)
            state["notification_error"] = notification_error
            _write_state(state_path, state)
            _report_notification_failure(component, status, notification_error)
        else:
            sent = True
            state["failure_notice_sent"] = True
            state["recovery_notice_pending"] = False
            state["notification_error"] = None
            _write_state(state_path, state)

    return NotificationResult(
        component=component,
        health="healthy",
        state_path=state_path,
        notification_attempted=attempted,
        notification_sent=sent,
        notification_pending=state["recovery_notice_pending"],
        notification_error=notification_error,
    )


def retry_pending_notification(
    component: str,
    *,
    state_dir: Path | str | None = None,
    notifier: NotificationSender | None = None,
    now: datetime | None = None,
    context: Mapping[str, object] | None = None,
    notification_grace: timedelta = timedelta(0),
) -> NotificationResult:
    """Retry a persisted notification without asserting new component work."""
    _validate_component(component)
    _validate_notification_grace(notification_grace)
    timestamp = _format_utc_timestamp(now)
    state_path = _state_path(component, state_dir)
    state = _load_state(state_path, component)
    _reject_future_state(state, timestamp, state_path)
    if state["health"] == "failing":
        pending = not state["failure_notice_sent"]
        status = "FAILED"
        if pending and _incident_age(state, timestamp) < notification_grace:
            return NotificationResult(
                component=component,
                health="failing",
                state_path=state_path,
                notification_attempted=False,
                notification_sent=False,
                notification_pending=True,
                notification_error=(
                    str(state["notification_error"])
                    if state["notification_error"] is not None
                    else None
                ),
            )
    else:
        pending = bool(state["recovery_notice_pending"])
        status = "RECOVERED" if state["failure_notice_sent"] else "FAILED AND RECOVERED"
    if not pending:
        return NotificationResult(
            component=component,
            health=str(state["health"]),
            state_path=state_path,
            notification_attempted=False,
            notification_sent=False,
            notification_pending=False,
            notification_error=(
                str(state["notification_error"])
                if state["notification_error"] is not None
                else None
            ),
        )

    state["notification_attempted_at_utc"] = timestamp
    message = _build_message(status, state, context)
    try:
        _resolve_notifier(notifier).send(message)
    except Exception as error:
        notification_error = _notification_error(error)
        state["notification_error"] = notification_error
        _write_state(state_path, state)
        _report_notification_failure(component, status, notification_error)
        sent = False
    else:
        notification_error = None
        sent = True
        state["failure_notice_sent"] = True
        if state["health"] == "healthy":
            state["recovery_notice_pending"] = False
        state["notification_error"] = None
        _write_state(state_path, state)

    notification_pending = (
        not state["failure_notice_sent"]
        if state["health"] == "failing"
        else bool(state["recovery_notice_pending"])
    )

    return NotificationResult(
        component=component,
        health=str(state["health"]),
        state_path=state_path,
        notification_attempted=True,
        notification_sent=sent,
        notification_pending=notification_pending,
        notification_error=notification_error,
    )


def component_incident_active(
    component: str,
    *,
    state_dir: Path | str | None = None,
) -> bool:
    _validate_component(component)
    state = _load_state(_state_path(component, state_dir), component)
    return state["health"] == "failing"


def suppress_unalerted_component_incident(
    component: str,
    *,
    state_dir: Path | str | None = None,
    now: datetime | None = None,
) -> bool:
    _validate_component(component)
    timestamp = _format_utc_timestamp(now)
    state_path = _state_path(component, state_dir)
    previous = _load_state(state_path, component)
    _reject_future_state(previous, timestamp, state_path)
    suppressible = (
        previous["health"] == "failing"
        and previous["failure_notice_sent"] is False
        and previous["notification_attempted_at_utc"] is None
    )
    if not suppressible:
        return False
    state = _empty_state(component)
    state["last_attempt_at_utc"] = timestamp
    _write_state(state_path, state)
    return True


def _resolve_notifier(notifier: NotificationSender | None) -> NotificationSender:
    return notifier if notifier is not None else DiscordWebhookSender()


def _validate_component(component: str) -> None:
    if component not in ALLOWED_COMPONENTS:
        raise ValueError(f"Unknown notification component: {component!r}")


def _state_path(component: str, state_dir: Path | str | None) -> Path:
    root = (Path(state_dir) if state_dir is not None else DEFAULT_STATE_DIR).resolve()
    return root / f"{component}.json"


def _empty_state(component: str) -> dict[str, object]:
    return {
        "schema_version": NOTIFICATION_STATE_SCHEMA_VERSION,
        "component": component,
        "health": "healthy",
        "first_failed_at_utc": None,
        "last_attempt_at_utc": None,
        "first_error": None,
        "last_error": None,
        "failure_notice_sent": False,
        "recovery_notice_pending": False,
        "notification_attempted_at_utc": None,
        "notification_error": None,
    }


def _load_state(state_path: Path, component: str) -> dict[str, object]:
    try:
        raw = read_bounded_regular_file(
            state_path,
            max_bytes=_MAX_STATE_BYTES,
            label="Notification state",
        )
    except FileNotFoundError:
        return _empty_state(component)
    try:
        state = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Notification state is invalid: {state_path}") from error
    if not isinstance(state, dict) or set(state) != _STATE_KEYS:
        raise ValueError(f"Notification state schema is invalid: {state_path}")
    if (
        type(state["schema_version"]) is not int
        or state["schema_version"] != NOTIFICATION_STATE_SCHEMA_VERSION
    ):
        raise ValueError(f"Notification state version is unsupported: {state_path}")
    if state["component"] != component or state["health"] not in {"healthy", "failing"}:
        raise ValueError(f"Notification state identity is invalid: {state_path}")
    if type(state["failure_notice_sent"]) is not bool:
        raise ValueError(f"Notification state flags are invalid: {state_path}")
    if type(state["recovery_notice_pending"]) is not bool:
        raise ValueError(f"Notification state flags are invalid: {state_path}")
    for key in (
        "first_failed_at_utc",
        "last_attempt_at_utc",
        "notification_attempted_at_utc",
    ):
        if state[key] is not None:
            _parse_state_timestamp(state[key], state_path)
    for key in ("first_error", "last_error", "notification_error"):
        if state[key] is not None and not isinstance(state[key], str):
            raise ValueError(f"Notification state values are invalid: {state_path}")
    if state["health"] == "failing" and (
        state["first_failed_at_utc"] is None
        or state["last_attempt_at_utc"] is None
        or state["first_error"] is None
        or state["last_error"] is None
        or state["recovery_notice_pending"]
    ):
        raise ValueError(
            f"Notification state incident evidence is incomplete: {state_path}"
        )
    first_failed = state["first_failed_at_utc"]
    last_attempt = state["last_attempt_at_utc"]
    if first_failed is not None and last_attempt is not None and (
        _parse_state_timestamp(first_failed, state_path)
        > _parse_state_timestamp(last_attempt, state_path)
    ):
        raise ValueError(f"Notification state timestamp order is invalid: {state_path}")
    for key in ("first_error", "last_error"):
        if state[key] is not None and len(state[key]) > _ERROR_LIMIT:
            raise ValueError(f"Notification state values are invalid: {state_path}")
    if (
        state["notification_error"] is not None
        and len(state["notification_error"]) > _NOTIFICATION_ERROR_LIMIT
    ):
        raise ValueError(f"Notification state values are invalid: {state_path}")
    return state


def _write_state(state_path: Path, state: Mapping[str, object]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_name(f".{state_path.name}.tmp-{uuid4().hex}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, state_path)
        _fsync_directory(state_path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _build_message(
    status: str,
    state: Mapping[str, object],
    context: Mapping[str, object] | None,
) -> str:
    component = str(state["component"])
    first_failure = _display_timestamp(state["first_failed_at_utc"])
    latest_attempt = _display_timestamp(state["last_attempt_at_utc"])
    reason = _sanitize_text(state["last_error"] or "Unknown error", _ERROR_LIMIT)
    pending_count = _context_count(context, "pending_count")
    recovered_count = _context_count(context, "recovered_upload_count")

    if component == "database-backup":
        if status == "FAILED":
            message = (
                "🚨 Extrusion Terminal — Database backup failed\n\n"
                f"A valid database backup could not be created at {latest_attempt}.\n"
                "The system will retry automatically in 10 minutes.\n\n"
                f"Reason: {reason}"
            )
        else:
            title = (
                "Database backup interruption resolved"
                if status == "FAILED AND RECOVERED"
                else "Database backup recovered"
            )
            message = (
                f"✅ Extrusion Terminal — {title}\n\n"
                f"A valid database backup was created at {latest_attempt}."
            )
    elif component == "database-backup-freshness":
        if status == "FAILED":
            last_success = _context_timestamp(
                context,
                "last_successful_check_at_utc",
            )
            inactivity = (
                f"The last validated database check was at {last_success}."
                if last_success is not None
                else (
                    "No recent validated database check has been recorded "
                    f"since {first_failure}."
                )
            )
            message = (
                "⚠️ Extrusion Terminal — Database backup process appears stopped\n\n"
                f"{inactivity}\n"
                "The delivery process is still running and will keep checking."
            )
        else:
            message = (
                "✅ Extrusion Terminal — Database backup checks resumed\n\n"
                f"A recent validated database check was observed at {latest_attempt}."
            )
    elif status == "FAILED":
        waiting = _waiting_sentence(pending_count)
        if context and context.get("manual_review_required") is True:
            message = (
                "⚠️ Extrusion Terminal — Backup delivery problem\n\n"
                f"A backup delivery item was isolated at {latest_attempt}.\n"
                "The evidence was retained, but manual review is required.\n\n"
                f"Reason: {reason}"
            )
        elif context and context.get("failure_kind") == "local":
            message = (
                "⚠️ Extrusion Terminal — Backup delivery problem\n\n"
                f"A local backup delivery problem was detected at {latest_attempt}.\n"
                f"{waiting}\n"
                "The system will keep retrying automatically.\n\n"
                f"Reason: {reason}"
            )
        else:
            message = (
                "⚠️ Extrusion Terminal — Cloud backups delayed\n\n"
                f"Hetzner uploads have been unavailable since {first_failure}.\n"
                f"{waiting}\n"
                "The system will keep retrying automatically.\n\n"
                f"Reason: {reason}"
            )
    else:
        title = (
            "Cloud backup interruption resolved"
            if status == "FAILED AND RECOVERED"
            else "Cloud backups recovered"
        )
        uploaded = _uploaded_sentence(recovered_count)
        message = (
            f"✅ Extrusion Terminal — {title}\n\n"
            f"Uploads resumed on {latest_attempt}.\n"
            f"{uploaded}\n"
            "Nothing remains waiting."
        )
    return message[:_MESSAGE_LIMIT]


def _waiting_sentence(count: int | None) -> str:
    if count is None:
        return "Waiting backups remain safely queued on the server."
    noun = "backup is" if count == 1 else "backups are"
    return f"{count} {noun} waiting safely on the server."


def _uploaded_sentence(count: int | None) -> str:
    if count is None:
        return "All waiting backups were uploaded."
    noun = "waiting backup was" if count == 1 else "waiting backups were"
    return f"{count} {noun} uploaded."


def _context_count(
    context: Mapping[str, object] | None,
    key: str,
) -> int | None:
    if context is None:
        return None
    value = context.get(key)
    return value if type(value) is int and value >= 0 else None


def _context_timestamp(
    context: Mapping[str, object] | None,
    key: str,
) -> str | None:
    if context is None or key not in context:
        return None
    displayed = _display_timestamp(context[key])
    return displayed if displayed != "an unknown time" else None


def _display_timestamp(value: object) -> str:
    if not isinstance(value, str):
        return "an unknown time"
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return "an unknown time"
    return parsed.astimezone(ZoneInfo("Europe/Sofia")).strftime(
        "%d %b %Y at %H:%M"
    )


def _incident_age(state: Mapping[str, object], timestamp: str) -> timedelta:
    first = state.get("first_failed_at_utc")
    if not isinstance(first, str):
        return timedelta(0)
    first_time = datetime.strptime(first, "%Y-%m-%dT%H:%M:%SZ")
    current_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    if current_time < first_time:
        raise ValueError("Notification incident state is from the future.")
    return current_time - first_time


def _parse_state_timestamp(value: object, state_path: Path) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Notification state timestamp is invalid: {state_path}")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValueError(
            f"Notification state timestamp is invalid: {state_path}"
        ) from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError(f"Notification state timestamp is invalid: {state_path}")
    return parsed


def _reject_future_state(
    state: Mapping[str, object],
    timestamp: str,
    state_path: Path,
) -> None:
    current = _parse_state_timestamp(timestamp, state_path)
    for key in (
        "first_failed_at_utc",
        "last_attempt_at_utc",
        "notification_attempted_at_utc",
    ):
        value = state.get(key)
        if value is not None and _parse_state_timestamp(value, state_path) > current:
            raise ValueError(f"Notification state timestamp is from the future: {state_path}")


def _validate_notification_grace(value: timedelta) -> None:
    if not isinstance(value, timedelta) or value < timedelta(0):
        raise ValueError("Notification grace must be a non-negative duration.")


def _sanitize_text(value: object, limit: int) -> str:
    text = str(value)
    text = _URL_PATTERN.sub("[url-redacted]", text)
    text = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in text
    )
    return " ".join(text.split())[:limit]


def _format_utc_timestamp(value: datetime | None) -> str:
    timestamp = value if value is not None else datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Notification timestamp must be timezone-aware.")
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _validate_discord_webhook_url(url: str) -> tuple[str, ...]:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise ValueError("Discord curl config contains an invalid webhook URL.") from error
    path_parts = parsed.path.split("/")
    valid_path = (
        len(path_parts) == 6
        and path_parts[0] == ""
        and path_parts[1:3] == ["api", "webhooks"]
        and bool(path_parts[3])
        and bool(path_parts[4])
        and path_parts[5] == ""
    ) or (
        len(path_parts) == 5
        and path_parts[0] == ""
        and path_parts[1:3] == ["api", "webhooks"]
        and bool(path_parts[3])
        and bool(path_parts[4])
    )
    if (
        parsed.scheme != "https"
        or parsed.hostname != "discord.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.fragment
        or not valid_path
        or parse_qsl(parsed.query, keep_blank_values=True) != [("wait", "true")]
    ):
        raise ValueError("Discord curl config contains an invalid webhook URL.")
    return tuple(path_parts[3:5])


def _redact_transport_diagnostic(
    value: str,
    *,
    webhook_url: str,
    secret_parts: tuple[str, ...],
) -> str:
    redacted = value.replace(webhook_url, "[webhook-redacted]")
    for secret_part in secret_parts:
        redacted = redacted.replace(secret_part, "[secret-redacted]")
    return _sanitize_text(redacted, 300) or "no diagnostic"


def _validate_discord_confirmation(stdout: str) -> None:
    if len(stdout.encode("utf-8")) > _MAX_DISCORD_RESPONSE_BYTES:
        raise DiscordNotificationError("Discord notification confirmation was too large.")
    body, separator, status = stdout.rpartition("\n")
    if not separator or status != "200":
        raise DiscordNotificationError(
            "Discord notification confirmation was not HTTP 200."
        )
    try:
        response = json.loads(body)
    except json.JSONDecodeError as error:
        raise DiscordNotificationError(
            "Discord notification confirmation was malformed."
        ) from error
    message_id = response.get("id") if isinstance(response, dict) else None
    if (
        not isinstance(message_id, str)
        or _DISCORD_MESSAGE_ID_PATTERN.fullmatch(message_id) is None
    ):
        raise DiscordNotificationError(
            "Discord notification confirmation did not contain a saved message ID."
        )


def _notification_error(error: Exception) -> str:
    if isinstance(error, DiscordNotificationError):
        detail = _sanitize_text(str(error), _ERROR_LIMIT)
        message = f"DiscordNotificationError: {detail}"
    else:
        message = f"{error.__class__.__name__}: notification delivery failed"
    return message[:_NOTIFICATION_ERROR_LIMIT]


def _report_notification_failure(component: str, status: str, error: str) -> None:
    print(
        f"Notification warning: component={component} event={status} "
        f"notification_pending=true error={error}",
        file=sys.stderr,
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
