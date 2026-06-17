from __future__ import annotations

from dataclasses import dataclass

from .constants import (
    ACTIVE_TERMINAL_STATUSES,
    STATUS_IMPORTED,
    STATUS_PENDING,
    STATUS_PAUSED,
    STATUS_RUNNING,
)


RELEASABLE_STATUSES = (STATUS_IMPORTED,)


@dataclass(frozen=True)
class RuleResult:
    ok: bool
    messages: tuple[str, ...] = ()


def validate_release_fields(card: dict) -> RuleResult:
    messages: list[str] = []

    if card.get("status") not in RELEASABLE_STATUSES:
        messages.append("Само импортирани технологични карти могат да се изпращат.")
    if not card.get("machine_id"):
        messages.append("Изберете машина преди изпращане.")
    if card.get("machine_sequence") in (None, ""):
        messages.append("Въведете ред преди изпращане.")

    return RuleResult(ok=not messages, messages=tuple(messages))


def is_active_terminal_status(status: str) -> bool:
    return status in ACTIVE_TERMINAL_STATUSES


def machine_is_occupied(status: str) -> bool:
    return status in (STATUS_PENDING, STATUS_RUNNING, STATUS_PAUSED)
