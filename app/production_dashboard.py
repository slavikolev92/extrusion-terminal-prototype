from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any

from . import db
from .constants import PRODUCTION_COMPLETE_STATUSES
from .timekeeping import SOFIA_ZONE, parse_stored_utc


WINDOW_DURATION = timedelta(hours=24)
WINDOW_SECONDS = int(WINDOW_DURATION.total_seconds())
AXIS_INTERVAL = timedelta(hours=3)
SOFIA_MONTH_ABBREVIATIONS = (
    "",
    "ян.",
    "фев.",
    "март",
    "апр.",
    "май",
    "юни",
    "юли",
    "авг.",
    "сеп.",
    "окт.",
    "ное.",
    "дек.",
)
DIMENSION_PART_PATTERN = re.compile(r"^\d+(?:[.,]\d+)?$")


def build_machine_time_dashboard(
    reference_time: datetime | None = None,
    selected_day: date | None = None,
) -> dict[str, Any]:
    reference_utc, start_utc, end_utc, max_day = _resolve_dashboard_window(
        reference_time,
        selected_day,
    )
    window_seconds = int((end_utc - start_utc).total_seconds())
    with db.connect() as connection:
        machines = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, name, display_order
                FROM machines
                ORDER BY display_order, id
                """
            ).fetchall()
        ]
        rows = connection.execute(
            """
            SELECT
                c.id AS card_id,
                c.order_number,
                c.status,
                c.machine_id,
                c.customer,
                c.size_thickness,
                c.first_started_at,
                c.finished_at,
                s.id AS segment_id,
                s.started_at,
                s.ended_at,
                s.end_reason
            FROM cards AS c
            JOIN production_time_segments AS s ON s.card_id = c.id
            WHERE c.machine_id IS NOT NULL
            ORDER BY c.id, s.started_at, s.id
            """
        ).fetchall()
        roll_rows = connection.execute(
            """
            SELECT card_id, net_weight
            FROM roll_entries
            WHERE net_weight IS NOT NULL
            ORDER BY card_id, roll_number, id
            """
        ).fetchall()

    cards = _group_card_rows(rows)
    _attach_card_metrics(cards, roll_rows, reference_utc)
    cards_by_id = {int(card["id"]): card for card in cards}
    machine_events: dict[int, list[dict[str, Any]]] = defaultdict(list)
    recent_order_starts: dict[int, dict[int, datetime]] = defaultdict(dict)
    for card in cards:
        events = _card_events(card, end_utc)
        machine_id = int(card["machine_id"])
        for event in events:
            clipped = _clip_event(event, start_utc, end_utc)
            if clipped is None:
                continue
            machine_events[machine_id].append(clipped)
            if clipped["kind"] == "order":
                card_id = int(card["id"])
                previous_start = recent_order_starts[machine_id].get(card_id)
                if previous_start is None or clipped["start"] < previous_start:
                    recent_order_starts[machine_id][card_id] = clipped["start"]

    machine_views = []
    for machine in machines:
        machine_id = int(machine["id"])
        timeline = _build_machine_timeline(
            machine_events[machine_id],
            start_utc,
            end_utc,
            machine_id,
        )
        active_seconds = sum(
            int(interval["duration_seconds"])
            for interval in timeline
            if interval["kind"] == "order"
        )
        order_ids = sorted(
            recent_order_starts[machine_id],
            key=lambda card_id: (
                recent_order_starts[machine_id][card_id],
                card_id,
            ),
        )
        machine_views.append(
            {
                "id": machine_id,
                "name": f"Машина {machine_id}",
                "active_seconds": active_seconds,
                "active_duration": _format_duration(active_seconds),
                "active_percent": _rounded_percentage(active_seconds, window_seconds),
                "timeline": timeline,
                "orders": [
                    _build_productivity_row(cards_by_id[card_id], cards)
                    for card_id in order_ids
                ],
            }
        )

    return {
        "window": {
            "mode": "calendar_day" if selected_day is not None else "rolling",
            "selected_day": (selected_day or max_day).isoformat(),
            "max_selectable_day": max_day.isoformat(),
            "start_utc": _utc_attribute(start_utc),
            "end_utc": _utc_attribute(end_utc),
            "seconds": window_seconds,
            "range_display": _window_range_display(start_utc, end_utc),
        },
        "axis": _build_axis(start_utc, end_utc, selected_day),
        "machines": machine_views,
    }


def normalize_dimensions(value: Any) -> tuple[Decimal, Decimal] | None:
    raw = str(value or "").strip()
    parts = [part.strip() for part in raw.split("/")]
    if len(parts) != 2 or not all(DIMENSION_PART_PATTERN.fullmatch(part) for part in parts):
        return None
    try:
        width, thickness = (
            Decimal(part.replace(",", "."))
            for part in parts
        )
    except InvalidOperation:
        return None
    if (
        not width.is_finite()
        or not thickness.is_finite()
        or width <= 0
        or thickness <= 0
    ):
        return None
    return width.normalize(), thickness.normalize()


def _canonical_reference_time(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Dashboard reference_time must include a timezone.")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def parse_dashboard_day(
    value: str | None,
    reference_time: datetime,
) -> date | None:
    if value is None or value == "":
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Invalid dashboard day.")
    try:
        selected_day = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid dashboard day.") from exc
    reference_utc = _canonical_reference_time(reference_time)
    max_day = reference_utc.astimezone(SOFIA_ZONE).date() - timedelta(days=1)
    if selected_day > max_day:
        raise ValueError("Dashboard day must be complete.")
    _resolve_selected_day_bounds(selected_day)
    return selected_day


def _resolve_dashboard_window(
    reference_time: datetime | None,
    selected_day: date | None,
) -> tuple[datetime, datetime, datetime, date]:
    reference_utc = _canonical_reference_time(reference_time)
    max_day = reference_utc.astimezone(SOFIA_ZONE).date() - timedelta(days=1)
    if selected_day is None:
        return reference_utc, reference_utc - WINDOW_DURATION, reference_utc, max_day
    if selected_day > max_day:
        raise ValueError("Dashboard day must be complete.")
    start_utc, end_utc = _resolve_selected_day_bounds(selected_day)
    return (
        reference_utc,
        start_utc,
        end_utc,
        max_day,
    )


def _resolve_selected_day_bounds(selected_day: date) -> tuple[datetime, datetime]:
    try:
        start_local = datetime.combine(selected_day, time.min, tzinfo=SOFIA_ZONE)
        end_local = datetime.combine(
            selected_day + timedelta(days=1),
            time.min,
            tzinfo=SOFIA_ZONE,
        )
        return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
    except OverflowError as exc:
        raise ValueError("Dashboard day cannot be represented.") from exc


def _group_card_rows(rows: list[Any]) -> list[dict[str, Any]]:
    cards: dict[int, dict[str, Any]] = {}
    for row in rows:
        card_id = int(row["card_id"])
        card = cards.setdefault(
            card_id,
            {
                "id": card_id,
                "order_number": str(row["order_number"]),
                "status": str(row["status"]),
                "machine_id": int(row["machine_id"]),
                "customer": str(row["customer"] or ""),
                "size_thickness": str(row["size_thickness"] or ""),
                "first_started_at": row["first_started_at"],
                "finished_at": row["finished_at"],
                "segments": [],
            },
        )
        card["segments"].append(
            {
                "id": int(row["segment_id"]),
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "end_reason": row["end_reason"],
            }
        )
    return list(cards.values())


def _attach_card_metrics(
    cards: list[dict[str, Any]],
    roll_rows: list[Any],
    end_utc: datetime,
) -> None:
    roll_totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    roll_counts: dict[int, int] = defaultdict(int)
    invalid_roll_cards: set[int] = set()
    for row in roll_rows:
        card_id = int(row["card_id"])
        try:
            value = Decimal(str(row["net_weight"]))
        except (InvalidOperation, TypeError, ValueError):
            invalid_roll_cards.add(card_id)
            continue
        if not value.is_finite() or value < 0:
            invalid_roll_cards.add(card_id)
            continue
        roll_totals[card_id] += value
        roll_counts[card_id] += 1

    for card in cards:
        card_id = int(card["id"])
        parsed_segments = []
        total_seconds = 0
        for segment in card["segments"]:
            started_at = parse_stored_utc(segment["started_at"], required=True)
            ended_at = parse_stored_utc(segment.get("ended_at")) or end_utc
            effective_end = min(ended_at, end_utc)
            if effective_end > started_at:
                total_seconds += int((effective_end - started_at).total_seconds())
            parsed_segments.append((started_at, effective_end))

        net_kg = None
        if card_id not in invalid_roll_cards and roll_counts[card_id] > 0:
            net_kg = roll_totals[card_id]
        productivity_value = None
        if net_kg is not None and net_kg > 0 and total_seconds > 0:
            productivity_value = net_kg * Decimal(3600) / Decimal(total_seconds)

        card["dimensions_value"] = normalize_dimensions(card["size_thickness"])
        card["dimensions"] = _dimensions_display(card["dimensions_value"])
        card["first_start"] = (
            min(start for start, _ in parsed_segments)
            if parsed_segments
            else None
        )
        card["finished"] = parse_stored_utc(card.get("finished_at"))
        card["net_kg"] = net_kg
        card["produced"] = _round_whole(net_kg)
        card["active_seconds"] = total_seconds
        card["active_duration"] = _format_duration(total_seconds)
        card["productivity_value"] = productivity_value
        card["productivity"] = _round_whole(productivity_value)


def _build_productivity_row(
    card: dict[str, Any],
    cards: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline = None
    if (
        card["dimensions_value"] is not None
        and card["first_start"] is not None
        and card["productivity_value"] is not None
    ):
        comparable = [
            candidate
            for candidate in cards
            if candidate["id"] != card["id"]
            and candidate["status"] in PRODUCTION_COMPLETE_STATUSES
            and candidate["machine_id"] == card["machine_id"]
            and candidate["dimensions_value"] == card["dimensions_value"]
            and candidate["finished"] is not None
            and candidate["finished"] <= card["first_start"]
            and candidate["productivity_value"] is not None
        ]
        if comparable:
            baseline = _build_baseline(card["productivity_value"], comparable)

    return {
        "id": int(card["id"]),
        "order_number": card["order_number"],
        "customer": card["customer"],
        "dimensions": card["dimensions"] or str(card["size_thickness"] or "").strip(),
        "produced": card["produced"],
        "active_seconds": int(card["active_seconds"]),
        "active_duration": card["active_duration"],
        "productivity": card["productivity"],
        "baseline": baseline,
    }


def _build_baseline(
    current_value: Decimal,
    comparable: list[dict[str, Any]],
) -> dict[str, Any]:
    minimum_value = min(card["productivity_value"] for card in comparable)
    maximum_value = max(card["productivity_value"] for card in comparable)
    positions = _gauge_positions(minimum_value, current_value, maximum_value)
    latest = sorted(
        comparable,
        key=lambda card: (card["finished"], int(card["id"])),
        reverse=True,
    )[:7]
    return {
        "minimum": _round_whole(minimum_value),
        "maximum": _round_whole(maximum_value),
        "sample_count": len(comparable),
        "is_single_sample": len(comparable) == 1,
        "samples": [
            {
                "order_number": card["order_number"],
                "dimensions": card["dimensions"],
                "productivity": card["productivity"],
            }
            for card in latest
        ],
        **positions,
    }


def _gauge_positions(
    minimum: Decimal,
    current: Decimal,
    maximum: Decimal,
) -> dict[str, float]:
    lowest = min(minimum, current, maximum)
    highest = max(minimum, current, maximum)
    spread = highest - lowest
    padding = max(
        spread * Decimal("0.25"),
        highest.copy_abs() * Decimal("0.05"),
        Decimal("1"),
    )
    scale_start = max(Decimal("0"), lowest - padding)
    scale_end = highest + padding
    if scale_end <= scale_start:
        scale_end = scale_start + Decimal("1")

    def position(value: Decimal) -> float:
        percentage = (value - scale_start) * Decimal(100) / (scale_end - scale_start)
        return float(percentage.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))

    return {
        "range_start": position(minimum),
        "range_end": position(maximum),
        "marker_position": position(current),
    }


def _dimensions_display(
    dimensions: tuple[Decimal, Decimal] | None,
) -> str:
    if dimensions is None:
        return ""
    width, thickness = dimensions
    width_display = format(width, "f")
    thickness_display = format(thickness, "f")
    if "." not in thickness_display:
        thickness_display += ".000"
    else:
        whole, fractional = thickness_display.split(".", 1)
        thickness_display = f"{whole}.{fractional.ljust(3, '0')}"
    return f"{width_display} × {thickness_display}"


def _round_whole(value: Decimal | None) -> int | None:
    if value is None:
        return None
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _card_events(card: dict[str, Any], end_utc: datetime) -> list[dict[str, Any]]:
    segments = sorted(
        card["segments"],
        key=lambda segment: (
            parse_stored_utc(segment["started_at"], required=True),
            int(segment["id"]),
        ),
    )
    events: list[dict[str, Any]] = []
    finished_at = parse_stored_utc(card.get("finished_at"))

    for index, segment in enumerate(segments):
        started_at = parse_stored_utc(segment["started_at"], required=True)
        ended_at = parse_stored_utc(segment.get("ended_at")) or end_utc
        if ended_at > started_at:
            events.append(
                {
                    "kind": "order",
                    "start": started_at,
                    "end": min(ended_at, end_utc),
                    "card_id": int(card["id"]),
                    "order_number": card["order_number"],
                    "customer": card["customer"],
                    "productivity": card["productivity"],
                }
            )

        if segment.get("end_reason") != "pause" or segment.get("ended_at") is None:
            continue

        pause_start = parse_stored_utc(segment["ended_at"], required=True)
        if index + 1 < len(segments):
            pause_end = parse_stored_utc(
                segments[index + 1]["started_at"],
                required=True,
            )
        elif finished_at is not None:
            pause_end = finished_at
        elif card["status"] == "paused":
            pause_end = end_utc
        else:
            pause_end = pause_start
        if pause_end > pause_start:
            events.append(
                {
                    "kind": "pause",
                    "start": pause_start,
                    "end": min(pause_end, end_utc),
                    "card_id": int(card["id"]),
                }
            )
    return events


def _clip_event(
    event: dict[str, Any],
    start_utc: datetime,
    end_utc: datetime,
) -> dict[str, Any] | None:
    clipped_start = max(event["start"], start_utc)
    clipped_end = min(event["end"], end_utc)
    if clipped_end <= clipped_start:
        return None
    return {**event, "start": clipped_start, "end": clipped_end}


def _build_machine_timeline(
    events: list[dict[str, Any]],
    start_utc: datetime,
    end_utc: datetime,
    machine_id: int,
) -> list[dict[str, Any]]:
    boundaries = sorted(
        {
            start_utc,
            end_utc,
            *(event["start"] for event in events),
            *(event["end"] for event in events),
        }
    )
    timeline: list[dict[str, Any]] = []
    for interval_start, interval_end in zip(boundaries, boundaries[1:]):
        if interval_end <= interval_start:
            continue
        covering_events = [
            event
            for event in events
            if event["start"] <= interval_start and event["end"] >= interval_end
        ]
        source = min(
            covering_events,
            key=lambda event: (
                0 if event["kind"] == "order" else 1,
                event["start"],
                event["end"],
                int(event.get("card_id", 0)),
            ),
            default=None,
        )
        kind = source["kind"] if source is not None else "idle"
        timeline.append(
            _present_interval(kind, interval_start, interval_end, machine_id, source)
        )
    return _merge_adjacent_intervals(timeline)


def _present_interval(
    kind: str,
    start: datetime,
    end: datetime,
    machine_id: int,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    duration_seconds = int((end - start).total_seconds())
    result = {
        "kind": kind,
        "machine_id": machine_id,
        "machine_name": f"Машина {machine_id}",
        "start": start,
        "end": end,
        "start_utc": _utc_attribute(start),
        "end_utc": _utc_attribute(end),
        "start_display": _interval_time_display(start),
        "end_display": _interval_time_display(end),
        "duration_seconds": duration_seconds,
        "duration_display": _format_duration(duration_seconds),
    }
    if source is not None:
        for field in (
            "card_id",
            "order_number",
            "customer",
            "productivity",
        ):
            if field in source:
                result[field] = source[field]
    return result


def _merge_adjacent_intervals(
    intervals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for interval in intervals:
        if merged and _can_merge(merged[-1], interval):
            merged[-1] = _present_interval(
                interval["kind"],
                merged[-1]["start"],
                interval["end"],
                int(interval["machine_id"]),
                interval if interval["kind"] != "idle" else None,
            )
        else:
            merged.append(interval)
    return merged


def _can_merge(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["kind"] != right["kind"] or left["end"] != right["start"]:
        return False
    if left["kind"] == "idle":
        return True
    return left.get("card_id") == right.get("card_id")


def _build_axis(
    start_utc: datetime,
    end_utc: datetime,
    selected_day: date | None,
) -> list[dict[str, Any]]:
    if selected_day is None:
        ticks = [start_utc + index * AXIS_INTERVAL for index in range(9)]
    else:
        ticks = [
            datetime.combine(
                selected_day + timedelta(days=hour // 24),
                time(hour % 24),
                tzinfo=SOFIA_ZONE,
            ).astimezone(timezone.utc)
            for hour in range(0, 25, 3)
        ]
    window_seconds = (end_utc - start_utc).total_seconds()
    axis = [
        {
            "position": (tick - start_utc).total_seconds() / window_seconds * 100,
            "utc": _utc_attribute(tick),
            "display": _time_display(tick),
        }
        for tick in ticks
    ]
    axis[0]["position"] = 0
    axis[-1]["position"] = 100
    return axis


def _window_range_display(start_utc: datetime, end_utc: datetime) -> str:
    start = start_utc.astimezone(SOFIA_ZONE)
    end = end_utc.astimezone(SOFIA_ZONE)
    return (
        f"{start.day} {SOFIA_MONTH_ABBREVIATIONS[start.month]} {start:%H:%M} – "
        f"{end.day} {SOFIA_MONTH_ABBREVIATIONS[end.month]} {end:%H:%M}"
    )


def _time_display(value: datetime) -> str:
    return value.astimezone(SOFIA_ZONE).strftime("%H:%M")


def _interval_time_display(value: datetime) -> str:
    local = value.astimezone(SOFIA_ZONE)
    alternate_fold = local.replace(fold=1 - local.fold)
    if alternate_fold.utcoffset() == local.utcoffset():
        return local.strftime("%H:%M")
    offset = local.strftime("%z")
    return f"{local:%H:%M} (UTC{offset[:3]}:{offset[3:]})"


def _utc_attribute(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_duration(seconds: int) -> str:
    rounded_minutes = max(0, (int(seconds) + 30) // 60)
    hours, minutes = divmod(rounded_minutes, 60)
    if hours and minutes:
        return f"{hours}ч {minutes:02d}м"
    if hours:
        return f"{hours}ч"
    if minutes:
        return f"{minutes}м"
    return "<1м"


def _rounded_percentage(part: int, whole: int) -> int:
    if whole <= 0:
        return 0
    value = Decimal(part * 100) / Decimal(whole)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
