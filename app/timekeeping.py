from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo

CANONICAL_UTC_FORMAT = "%Y-%m-%d %H:%M:%S"
SOFIA_INPUT_FORMAT = "%Y-%m-%d %H:%M:%S"
CANONICAL_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
SOFIA_INPUT_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2})?$"
)
SOFIA_ZONE = ZoneInfo("Europe/Sofia")
BULGARIAN_MONTH_NAMES = (
    "", "януари", "февруари", "март", "април", "май", "юни",
    "юли", "август", "септември", "октомври", "ноември", "декември",
)


class StoredTimestampError(ValueError):
    pass


class LocalTimeInputError(ValueError):
    pass


def parse_stored_utc(value: Any, *, required: bool = False) -> datetime | None:
    raw = str(value or "")
    stripped = raw.strip()
    if not stripped:
        if required:
            raise StoredTimestampError("A required stored UTC timestamp is missing.")
        return None
    if raw != stripped:
        raise StoredTimestampError("Stored UTC timestamp is not canonical.")
    if not CANONICAL_UTC_PATTERN.fullmatch(raw):
        raise StoredTimestampError("Stored UTC timestamp is not canonical.")
    try:
        parsed = datetime.strptime(raw, CANONICAL_UTC_FORMAT)
    except ValueError as exc:
        raise StoredTimestampError("Stored UTC timestamp is invalid.") from exc
    return parsed.replace(tzinfo=timezone.utc)


def _sofia_datetime(value: Any) -> datetime | None:
    parsed = parse_stored_utc(value)
    return parsed.astimezone(SOFIA_ZONE) if parsed is not None else None


def format_display_datetime(value: Any, *, blank: str = "-") -> str:
    parsed = _sofia_datetime(value)
    return parsed.strftime("%d.%m.%Y %H:%M:%S") if parsed else blank


def format_print_datetime(value: Any) -> str:
    parsed = _sofia_datetime(value)
    return parsed.strftime("%d.%m.%Y %H:%M") if parsed else ""


def format_shift_datetime(value: Any, *, blank: str = "-") -> str:
    parsed = _sofia_datetime(value)
    if parsed is None:
        return blank
    return (
        f"{parsed.day} {BULGARIAN_MONTH_NAMES[parsed.month]} "
        f"{parsed.year}, {parsed:%H:%M}"
    )


def format_utc_datetime_attribute(value: Any) -> str:
    parsed = parse_stored_utc(value)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") if parsed else ""


def _valid_sofia_instants(local_value: datetime) -> dict[datetime, datetime]:
    candidates: dict[datetime, datetime] = {}
    for fold in (0, 1):
        localized = local_value.replace(tzinfo=SOFIA_ZONE, fold=fold)
        utc_value = localized.astimezone(timezone.utc)
        round_trip = utc_value.astimezone(SOFIA_ZONE)
        if round_trip.replace(tzinfo=None) == local_value:
            candidates[utc_value] = round_trip
    return candidates


def format_sofia_input(value: Any) -> str:
    localized = _sofia_datetime(value)
    if localized is None:
        return ""
    local_value = localized.replace(tzinfo=None)
    rendered = local_value.strftime(SOFIA_INPUT_FORMAT)
    if len(_valid_sofia_instants(local_value)) == 1:
        return rendered
    offset = localized.strftime("%z")
    return f"{rendered}{offset[:3]}:{offset[3:]}"


def parse_sofia_input(value: Any, *, label: str, required: bool) -> str:
    raw = str(value or "").strip()
    if not raw:
        if required:
            raise LocalTimeInputError(f"{label} е задължително поле.")
        return ""
    if not SOFIA_INPUT_PATTERN.fullmatch(raw):
        raise LocalTimeInputError(
            f"{label} трябва да използва формат YYYY-MM-DD HH:MM:SS "
            "или YYYY-MM-DD HH:MM:SS+HH:MM."
        )
    has_offset = raw[-6:-5] in {"+", "-"}
    local_text = raw[:-6] if has_offset else raw
    try:
        local_value = datetime.strptime(local_text, SOFIA_INPUT_FORMAT)
    except ValueError as exc:
        raise LocalTimeInputError(f"{label} съдържа невалидна дата или час.") from exc
    candidates = _valid_sofia_instants(local_value)
    if not candidates:
        raise LocalTimeInputError(
            f"{label} не съществува в Europe/Sofia заради преминаването "
            "към лятно часово време."
        )
    if has_offset:
        try:
            submitted = datetime.fromisoformat(raw.replace(" ", "T"))
        except ValueError as exc:
            raise LocalTimeInputError(f"{label} съдържа невалидно отместване.") from exc
        submitted_utc = submitted.astimezone(timezone.utc)
        if submitted_utc not in candidates:
            raise LocalTimeInputError(
                f"{label} използва отместване, което не е валидно за Europe/Sofia."
            )
        chosen = submitted_utc
    else:
        if len(candidates) != 1:
            raise LocalTimeInputError(
                f"{label} е двусмислено при смяната на часа. "
                "Добавете +02:00 или +03:00."
            )
        chosen = next(iter(candidates))
    return chosen.strftime(CANONICAL_UTC_FORMAT)
