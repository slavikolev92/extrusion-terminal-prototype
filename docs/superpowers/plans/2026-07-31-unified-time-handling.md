# Unified Time Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep SQLite/server-generated production instants canonical in UTC while every operator, admin, and printed timestamp is consistently displayed or edited in `Europe/Sofia`.

**Architecture:** Add one standard-library `app/timekeeping.py` boundary for strict UTC parsing, Sofia conversion, output formatting, HTML UTC attributes, and reversible admin input parsing. Preserve all raw database values for SQL, duration, ordering, conflict detection, and snapshot signatures; route/print view models add separate display, input, and ISO fields. Extend the existing terminal snapshot with an unsigned SQLite time sample so JavaScript can display a live server-synchronized Sofia clock without using the browser as the production source of truth.

**Tech Stack:** Python 3, `datetime`, `zoneinfo`, FastAPI, direct `sqlite3`, Jinja2, vanilla JavaScript, pytest, temporary SQLite fixtures, and repository-local Playwright/Chromium.

## Global Constraints

- Read root `AGENTS.md`, `README.md`, the approved design at `docs/superpowers/specs/2026-07-31-unified-time-handling-design.md`, `docs/implementation-notes/print-output-reference.md`, and `docs/implementation-notes/shift-management.md` before implementation.
- SQLite remains the authoritative current-time source for all production writes. Do not replace `SELECT CURRENT_TIMESTAMP` or any transactional production timestamp with Python-host or browser time.
- Canonical stored instants remain UTC `TEXT` in exact `YYYY-MM-DD HH:MM:SS` form. Do not add suffixes to stored values and do not convert raw values before SQL ordering, duration calculation, overlap validation, optimistic conflict checks, or snapshot-signature construction.
- The sole user timezone is the IANA zone `Europe/Sofia`; never use a fixed UTC+02:00/UTC+03:00 offset and never depend on the host or browser timezone.
- Ordinary admin/terminal display is `DD.MM.YYYY HH:MM:SS`; print display is `DD.MM.YYYY HH:MM`; shift display remains `D <Bulgarian month> YYYY, HH:MM`; HTML `datetime` values are `YYYY-MM-DDTHH:MM:SSZ`.
- Admin timing inputs mean Sofia local civil time. Reject nonexistent spring-transition values; reject ambiguous autumn-transition values unless they contain an applicable `+02:00` or `+03:00`; reject an offset that was not applicable in Sofia at that local time.
- Existing UTC timing values must round-trip through the complete admin form without changing, including values in the repeated autumn hour. Validate the complete ledger before any correction transaction writes.
- Preserve imported order and delivery dates as date-only fields. Preserve the browser-only roll-change countdown and operational backup filenames as documented exceptions.
- Malformed nonempty stored timestamps are integrity errors. Never return the raw malformed string as a display fallback and never silently rewrite it. A malformed required print timestamp must block print generation with a visible Bulgarian message.
- Add `server_now_utc` to terminal snapshots from SQLite in the same read transaction. Exclude it from every signature, refresh the browser offset before an unchanged-signature return, and continue from the last valid offset during a polling failure.
- Do not modify `app/schema.py`, `app/migrations.py`, migration tests, any file under `production-db/`, or `data/extrusion_terminal.sqlite3`. This feature has no schema migration, no data migration, no `M007`, and no production timestamp rewrite.
- All automated and browser checks use temporary database paths. Browser evidence goes under `artifacts/ui-checks/`; no check may open or mutate the runtime or production database.
- Use only the repository-local `.venv` and `node_modules`; do not install or download dependencies.
- Preserve unrelated working-tree changes, including the deleted `design-qa.md`, modified `v2-files/PLAN.md`, and existing untracked implementation/migration notes.
- Do not stage or commit. Repository policy requires separate explicit user authorization, which overrides the planning skill's sample commit cadence.

## File Map

- Create `app/timekeeping.py`: own the canonical UTC parser, Sofia conversion, display/print/shift/HTML/input formatters, DST validation, and input exceptions.
- Create `tests/test_timekeeping.py`: exhaustively test the conversion boundary independently of routes and SQLite.
- Modify `app/printing.py`: use the shared print formatter and block malformed required print timestamps.
- Modify `tests/test_print_output.py`: replace defect-encoding UTC expectations and cover print conversion, date rollover, malformed values, and data preservation.
- Modify `app/main.py`: enrich admin/terminal/shift view models with separate time fields and convert correction-form inputs to UTC before database calls.
- Modify `app/db.py`: sample `server_now_utc` inside the terminal snapshot read transaction without adding it to signatures.
- Modify `app/templates/admin_card_detail.html`: show Sofia display values, submit Sofia input values, and use local values in timing-deletion confirmation text.
- Modify `app/templates/admin_cards.html`: render local updated times with UTC machine-readable attributes.
- Modify `app/templates/admin_import.html`: render local import times with UTC machine-readable attributes.
- Modify `app/templates/terminal.html`: render local waiting/produced times and synchronize the live shift clock from snapshot samples.
- Modify `app/templates/_terminal_shift_window.html`: provide the initial server sample and use UTC `Z` values in existing `<time datetime>` attributes.
- Modify `tests/test_admin_card_detail_redesign.py`: cover time view-model fields, rendered inputs, global-save round trips, and atomic validation failure.
- Modify `tests/test_admin_production_corrections.py`: cover individual correction routes and preserve direct database APIs as canonical UTC interfaces.
- Modify `tests/test_admin_routes.py`: cover local admin-list and import-list output without changing raw values.
- Modify `tests/test_terminal_v8_render.py`: cover local waiting/produced output and preserve raw archive sorting.
- Modify `tests/test_shift_routes.py`: move shift formatting expectations to the shared helper and require UTC `Z` attributes.
- Modify `tests/test_terminal_sync.py`: cover the server sample, stable signatures, initial data attribute, and JavaScript refresh order.
- Modify `scripts/create_print_template_fixture.py`: use a canonical UTC fixture that crosses Bulgarian midnight for visible print verification.
- Create `scripts/verify_time_handling_ui.mjs`: run the guarded admin, terminal, and print browser workflow and capture evidence.
- Create `tests/test_time_handling_ui_script_safety.py`: ensure the verifier is syntax-valid, path-guarded, and tied to the required time assertions.
- Modify `README.md`: document the authoritative application time contract and deployment check.
- Modify `docs/implementation-notes/print-output-reference.md`: document UTC-to-Sofia print conversion and malformed-time blocking.
- Modify `docs/implementation-notes/shift-management.md`: document shared shift formatting and the server-synchronized live clock.
- Create `docs/implementation-notes/time-handling.md`: preserve the conversion API, correction/DST rules, exceptions, production inspection, and no-migration decision.

---

### Task 1: Build And Prove The Shared Timekeeping Boundary

**Files:**
- Create: `tests/test_timekeeping.py`
- Create: `app/timekeeping.py`

**Interfaces:**
- Consumes: canonical UTC strings in `YYYY-MM-DD HH:MM:SS` and Sofia-local admin strings in `YYYY-MM-DD HH:MM:SS[+HH:MM]`.
- Produces: `StoredTimestampError`, `LocalTimeInputError`, `parse_stored_utc()`, `format_display_datetime()`, `format_print_datetime()`, `format_shift_datetime()`, `format_utc_datetime_attribute()`, `format_sofia_input()`, and `parse_sofia_input()` with the exact signatures below.

- [ ] **Step 1: Write failing unit tests for strict UTC parsing and all output formats**

Create `tests/test_timekeeping.py` with focused parametrized cases:

```python
from datetime import datetime, timezone

import pytest

from app.timekeeping import (
    LocalTimeInputError,
    StoredTimestampError,
    format_display_datetime,
    format_print_datetime,
    format_shift_datetime,
    format_sofia_input,
    format_utc_datetime_attribute,
    parse_sofia_input,
    parse_stored_utc,
)


def test_parse_stored_utc_returns_aware_utc_datetime():
    assert parse_stored_utc("2026-06-18 21:35:29", required=True) == datetime(
        2026, 6, 18, 21, 35, 29, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    "value",
    ["2026-6-18 21:35:29", "2026-06-18T21:35:29", "not-a-time", "2026-02-29 10:00:00"],
)
def test_parse_stored_utc_rejects_noncanonical_or_invalid_values(value):
    with pytest.raises(StoredTimestampError):
        parse_stored_utc(value, required=True)


def test_optional_stored_time_is_distinct_from_malformed_time():
    assert parse_stored_utc(None) is None
    assert parse_stored_utc("   ") is None
    with pytest.raises(StoredTimestampError):
        parse_stored_utc("broken")


@pytest.mark.parametrize(
    ("stored", "ordinary", "printed", "shift"),
    [
        ("2026-01-26 19:30:59", "26.01.2026 21:30:59", "26.01.2026 21:30", "26 януари 2026, 21:30"),
        ("2026-07-26 18:30:59", "26.07.2026 21:30:59", "26.07.2026 21:30", "26 юли 2026, 21:30"),
        ("2026-06-18 21:35:29", "19.06.2026 00:35:29", "19.06.2026 00:35", "19 юни 2026, 00:35"),
        ("2024-02-29 22:15:00", "01.03.2024 00:15:00", "01.03.2024 00:15", "1 март 2024, 00:15"),
    ],
)
def test_formatters_use_sofia_rules(stored, ordinary, printed, shift):
    assert format_display_datetime(stored) == ordinary
    assert format_print_datetime(stored) == printed
    assert format_shift_datetime(stored) == shift


def test_optional_formatters_use_surface_blanks():
    assert format_display_datetime(None) == "-"
    assert format_print_datetime(None) == ""
    assert format_shift_datetime(None) == "-"
    assert format_utc_datetime_attribute(None) == ""
    assert format_sofia_input(None) == ""


def test_html_datetime_is_unambiguous_utc():
    assert format_utc_datetime_attribute("2026-06-18 21:35:29") == "2026-06-18T21:35:29Z"
```

- [ ] **Step 2: Write failing input and DST round-trip tests**

Append the boundary cases; use the actual 2026 Sofia transitions (spring
`2026-03-29` and autumn `2026-10-25`):

```python
def test_normal_sofia_input_converts_to_canonical_utc():
    assert parse_sofia_input(
        "2026-06-18 11:05:00", label="Начало", required=True
    ) == "2026-06-18 08:05:00"


def test_optional_local_input_can_be_blank_but_required_cannot():
    assert parse_sofia_input("", label="Край", required=False) == ""
    with pytest.raises(LocalTimeInputError, match="Начало е задължително"):
        parse_sofia_input("", label="Начало", required=True)


def test_nonexistent_spring_local_time_is_rejected():
    with pytest.raises(LocalTimeInputError, match="не съществува"):
        parse_sofia_input("2026-03-29 03:30:00", label="Начало", required=True)


def test_ambiguous_autumn_local_time_requires_an_offset():
    with pytest.raises(LocalTimeInputError, match=r"\+02:00.*\+03:00"):
        parse_sofia_input("2026-10-25 03:30:00", label="Начало", required=True)


def test_ambiguous_autumn_offsets_identify_both_real_instants():
    assert parse_sofia_input(
        "2026-10-25 03:30:00+03:00", label="Начало", required=True
    ) == "2026-10-25 00:30:00"
    assert parse_sofia_input(
        "2026-10-25 03:30:00+02:00", label="Начало", required=True
    ) == "2026-10-25 01:30:00"


def test_explicit_offset_must_match_sofia_at_that_wall_time():
    with pytest.raises(LocalTimeInputError, match="Europe/Sofia"):
        parse_sofia_input(
            "2026-06-18 11:05:00+02:00", label="Начало", required=True
        )


@pytest.mark.parametrize(
    ("stored", "rendered_input"),
    [
        ("2026-06-18 08:05:00", "2026-06-18 11:05:00"),
        ("2026-10-25 00:30:00", "2026-10-25 03:30:00+03:00"),
        ("2026-10-25 01:30:00", "2026-10-25 03:30:00+02:00"),
    ],
)
def test_stored_utc_round_trips_through_admin_input(stored, rendered_input):
    assert format_sofia_input(stored) == rendered_input
    assert parse_sofia_input(rendered_input, label="Начало", required=True) == stored
```

- [ ] **Step 3: Run the new tests and verify the intended import failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_timekeeping.py -q
```

Expected: collection fails because `app.timekeeping` does not exist.

- [ ] **Step 4: Implement the strict standard-library timekeeping module**

Create `app/timekeeping.py`. Keep the public names and behavior exact; use
round-trip validation instead of guessing DST folds:

```python
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
    raw = str(value or "").strip()
    if not raw:
        if required:
            raise StoredTimestampError("A required stored UTC timestamp is missing.")
        return None
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
```

- [ ] **Step 5: Run the boundary tests and inspect the module**

Run:

```bash
.venv/bin/python -m pytest tests/test_timekeeping.py -q
.venv/bin/python -m py_compile app/timekeeping.py
```

Expected: all `tests/test_timekeeping.py` tests pass and compilation exits `0`.
Review that every public formatter calls `parse_stored_utc()` and no helper
falls back to returning a malformed raw value.

- [ ] **Step 6: Stop at the Task 1 review boundary**

Review only `app/timekeeping.py` and `tests/test_timekeeping.py` for the exact
signatures above, DST round-trip correctness, and dependency-free operation.
Do not stage or commit.

---

### Task 2: Correct And Guard Printed Production Times

**Files:**
- Modify: `tests/test_print_output.py:1-40, 100-140, 220-245, 575-610, 650-665`
- Modify: `app/printing.py:1-12, 40-70, 145-160, 345-370`

**Interfaces:**
- Consumes: `parse_stored_utc(value, required=True)` and `format_print_datetime(value)` from Task 1.
- Produces: print readiness that rejects malformed required start/stop values and print data whose `start_display`/`stop_display` are Sofia local without changing the card's raw timestamps.

- [ ] **Step 1: Change the print expectations from raw UTC wall time to Sofia time**

In `tests/test_print_output.py`, stop importing `format_datetime` from
`app.printing`. Keep the fixture's canonical values
`2026-06-18 08:05:00`/`10:45:00`, and change the assertions to:

```python
assert result.data["back"]["start_display"] == "18.06.2026 11:05"
assert result.data["back"]["stop_display"] == "18.06.2026 13:45"
```

Replace the old helper assertion with a date-rollover integration assertion:

```python
def test_print_time_conversion_can_cross_the_bulgarian_date_boundary(connection):
    card_id = make_completed_printable_card("270-time-rollover")
    with db.connect() as connection:
        connection.execute(
            "UPDATE cards SET first_started_at = ?, finished_at = ? WHERE id = ?",
            ("2026-06-18 21:35:00", "2026-06-18 22:45:00", card_id),
        )
        connection.commit()

    before = db.fetch_admin_card_detail(card_id)
    readiness = build_print_readiness(card_id)
    after = db.fetch_admin_card_detail(card_id)

    assert readiness.ok
    assert readiness.data["back"]["start_display"] == "19.06.2026 00:35"
    assert readiness.data["back"]["stop_display"] == "19.06.2026 01:45"
    assert after["first_started_at"] == before["first_started_at"]
    assert after["finished_at"] == before["finished_at"]
```

- [ ] **Step 2: Add failing readiness tests for malformed required timestamps**

Add a parametrized test that corrupts one field at a time without touching the
other production data:

```python
@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("first_started_at", "Началният час на производство е невалиден и печатът е блокиран."),
        ("finished_at", "Крайният час на производство е невалиден и печатът е блокиран."),
    ],
)
def test_print_blocks_malformed_required_timestamp(connection, field, message):
    card_id = make_completed_printable_card(f"270-invalid-{field}")
    with db.connect() as connection:
        connection.execute(f"UPDATE cards SET {field} = ? WHERE id = ?", ("broken", card_id))
        connection.commit()

    result = build_print_readiness(card_id)

    assert not result.ok
    assert result.data is None
    assert message in result.messages
```

- [ ] **Step 3: Run the focused print tests and observe the failures**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_print_output.py::test_completed_card_with_required_production_data_is_printable \
  tests/test_print_output.py::test_print_time_conversion_can_cross_the_bulgarian_date_boundary \
  tests/test_print_output.py::test_print_blocks_malformed_required_timestamp \
  -q
```

Expected: local-time assertions fail and malformed values are not blocked.

- [ ] **Step 4: Route print validation and formatting through the shared module**

In `app/printing.py`, remove `datetime` and the local `format_datetime()`
function. Import:

```python
from .timekeeping import StoredTimestampError, format_print_datetime, parse_stored_utc
```

After the existing missing-value checks in `validate_print_readiness()`, add:

```python
for field, invalid_message in (
    (
        "first_started_at",
        "Началният час на производство е невалиден и печатът е блокиран.",
    ),
    (
        "finished_at",
        "Крайният час на производство е невалиден и печатът е блокиран.",
    ),
):
    if not card.get(field):
        continue
    try:
        parse_stored_utc(card[field], required=True)
    except StoredTimestampError:
        messages.append(invalid_message)
```

Change only the two print-data fields:

```python
"start_display": format_print_datetime(card.get("first_started_at")),
"stop_display": format_print_datetime(card.get("finished_at")),
```

Do not change print eligibility, timing totals, segment validation, or the
template layout.

- [ ] **Step 5: Run the entire print test module**

Run:

```bash
.venv/bin/python -m pytest tests/test_print_output.py -q
```

Expected: all print tests pass with canonical UTC still present in SQLite and
Sofia-local times in print data.

- [ ] **Step 6: Stop at the Task 2 review boundary**

Review the diff for `app/printing.py` and `tests/test_print_output.py`. Confirm
that the former raw-value fallback is deleted and no SQL/database file changed.
Do not stage or commit.

---

### Task 3: Apply Separate Display, Input, And ISO Fields To Every Screen

**Files:**
- Modify: `app/main.py:1-12, 210-225, 275-300, 930-960, 2595-2640, 3025-3145`
- Modify: `app/templates/admin_card_detail.html:360-460`
- Modify: `app/templates/admin_cards.html:65-85`
- Modify: `app/templates/admin_import.html:95-110`
- Modify: `app/templates/terminal.html:3995-4060`
- Modify: `app/templates/_terminal_shift_window.html:115-135, 185-195, 240-295`
- Modify: `tests/test_admin_card_detail_redesign.py`
- Modify: `tests/test_admin_routes.py`
- Modify: `tests/test_terminal_v8_render.py`
- Modify: `tests/test_shift_routes.py:180-220`

**Interfaces:**
- Consumes: the Task 1 formatters; raw dictionaries returned by existing DB queries.
- Produces: `add_time_presentation(record, *fields)`, `enrich_admin_card_times(card)`, and additive `*_display`, `*_input`, `*_iso_utc` fields. Raw keys remain byte-for-byte unchanged.

- [ ] **Step 1: Add failing view-model tests that require additive fields and raw preservation**

Add focused assertions in the existing route/render modules. Use a summer UTC
value and require all three representations where applicable:

```python
context = admin_card_detail_context(card_id)
card = context["card"]
assert card["first_started_at"] == "2026-06-18 08:05:00"
assert card["first_started_at_display"] == "18.06.2026 11:05:00"
assert card["first_started_at_input"] == "2026-06-18 11:05:00"
assert card["first_started_at_iso_utc"] == "2026-06-18T08:05:00Z"
segment = card["timing_segments"][0]
assert segment["started_at_input"] == "2026-06-18 11:05:00"
assert segment["started_at"] == "2026-06-18 08:05:00"
```

For the card and import lists, set a known `updated_at`/`created_at` directly in
the temporary test database and require `18.06.2026 11:05:00` visibly plus
`datetime="2026-06-18T08:05:00Z"`. For terminal history/waiting rows, require
the local `finished_at_display` while retaining raw UTC ordering. For shift
rows, move imports from `app.main.format_shift_datetime` to
`app.timekeeping.format_shift_datetime`, require malformed nonempty input to
raise `StoredTimestampError`, and require the new `*_iso_utc` fields.

- [ ] **Step 2: Run the four focused modules and observe missing-field failures**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_admin_card_detail_redesign.py \
  tests/test_admin_routes.py \
  tests/test_terminal_v8_render.py \
  tests/test_shift_routes.py \
  -q
```

Expected: new additive-field and local-rendering assertions fail.

- [ ] **Step 3: Add view-model enrichment helpers without overwriting raw keys**

In `app/main.py`, keep `datetime` for existing date-only parsing, remove the
unused `timezone` and `ZoneInfo` imports, and import:

```python
from .timekeeping import (
    format_display_datetime,
    format_shift_datetime,
    format_sofia_input,
    format_utc_datetime_attribute,
)
```

Add these helpers near the other presentation helpers:

```python
def add_time_presentation(record: dict[str, Any], *fields: str) -> dict[str, Any]:
    for field in fields:
        raw_value = record.get(field)
        record[f"{field}_display"] = format_display_datetime(raw_value)
        record[f"{field}_iso_utc"] = format_utc_datetime_attribute(raw_value)
    return record


def enrich_admin_card_times(card: dict[str, Any]) -> dict[str, Any]:
    add_time_presentation(
        card,
        "first_started_at",
        "finished_at",
        "created_at",
        "updated_at",
    )
    card["first_started_at_input"] = format_sofia_input(card.get("first_started_at"))
    card["finished_at_input"] = format_sofia_input(card.get("finished_at"))
    for segment in card.get("timing_segments") or []:
        add_time_presentation(segment, "started_at", "ended_at")
        segment["started_at_input"] = format_sofia_input(segment.get("started_at"))
        segment["ended_at_input"] = format_sofia_input(segment.get("ended_at"))
    return card
```

Call `enrich_admin_card_times(card)` in `admin_card_detail_context()`. Map
`add_time_presentation(row, "updated_at")` over `fetch_admin_cards(filters)`
and `add_time_presentation(batch, "created_at")` over
`fetch_recent_import_batches()` before passing rows to templates.

In `enrich_terminal_list_card()`, call:

```python
add_time_presentation(card, "finished_at")
```

Keep `sorted_terminal_archive_cards()` before enrichment and keep its sort key
on raw `finished_at`.

Delete `BULGARIAN_MONTH_NAMES`, `SHIFT_DISPLAY_TIME_ZONE`, and the local
`format_shift_datetime()` from `app/main.py`. Extend `build_shift_display()`:

```python
display["started_at_display"] = format_shift_datetime(shift.get("started_at"))
display["ended_at_display"] = format_shift_datetime(shift.get("ended_at"))
display["started_at_iso_utc"] = format_utc_datetime_attribute(shift.get("started_at"))
display["ended_at_iso_utc"] = format_utc_datetime_attribute(shift.get("ended_at"))
```

- [ ] **Step 4: Update templates to consume only derived visible values**

Make the substitutions explicit:

```jinja2
{# admin detail summaries/system metadata #}
<time datetime="{{ card.first_started_at_iso_utc }}">{{ card.first_started_at_display }}</time>
<time datetime="{{ card.finished_at_iso_utc }}">{{ card.finished_at_display }}</time>
<time datetime="{{ card.created_at_iso_utc }}">{{ card.created_at_display }}</time>
<time datetime="{{ card.updated_at_iso_utc }}">{{ card.updated_at_display }}</time>

{# timing inputs and deletion confirmation #}
value="{{ segment.started_at_input }}"
value="{{ segment.ended_at_input }}"
data-action-confirm="Да се изтрие ли времеви сегмент {{ loop.index }}: {{ segment.started_at_display }} - {{ segment.ended_at_display if segment.ended_at else 'в ход' }}?"
```

In `admin_cards.html` and `admin_import.html`, display the derived field in a
`<time>` element with the corresponding `*_iso_utc`. In both terminal history
rows, replace `card.finished_at` with:

```jinja2
<time datetime="{{ card.finished_at_iso_utc }}">{{ card.finished_at_display }}</time>
```

In `_terminal_shift_window.html`, replace every raw `datetime` attribute with
`started_at_iso_utc` or `ended_at_iso_utc` while preserving the existing shift
display text.

Do not convert `order_date`, `delivery_date`, queue sequence, countdown values,
or any hidden optimistic-version field.

- [ ] **Step 5: Run focused display tests**

Run the same four-module command from Step 2. Expected: all modules pass, all
visible production timestamps use Sofia values, and assertions still prove
that raw fields and raw archive ordering are unchanged.

- [ ] **Step 6: Stop at the Task 3 review boundary**

Search for remaining direct template output:

```bash
rg -n "\{\{[^}]*\.(first_started_at|finished_at|created_at|updated_at|started_at|ended_at)(\s+or|\s*\}\})" \
  app/templates/admin_card_detail.html app/templates/admin_cards.html \
  app/templates/admin_import.html app/templates/terminal.html \
  app/templates/_terminal_shift_window.html
```

Expected: no user-visible raw production timestamp remains; any match must be
an explicitly documented non-visible/raw data use. Do not stage or commit.

---

### Task 4: Make Admin Timing Corrections Reversible And DST-Safe

**Files:**
- Modify: `app/main.py:760-805, 1120-1220, 1590-1680`
- Modify: `tests/test_admin_card_detail_redesign.py`
- Modify: `tests/test_admin_production_corrections.py`

**Interfaces:**
- Consumes: `parse_sofia_input(value, label=..., required=...)` and Task 3's `*_input` values.
- Produces: `canonical_timing_values(started_at, ended_at)` and a converted `timing_ledger_from_form()` whose output remains the canonical-UTC input expected by `db.add_timing_segment()`, `db.update_timing_segment()`, and `db.update_admin_timing_ledger()`.

- [ ] **Step 1: Add failing individual-route and unchanged-round-trip tests**

In `tests/test_admin_production_corrections.py`, call the already imported
individual route functions with that module's `FormRequest`. For summer input:

```python
response = asyncio.run(
    add_admin_timing_segment(
        FormRequest({}),
        card_id,
        loaded_version=str(card["version"]),
        started_at="2026-06-18 11:05:00",
        ended_at="2026-06-18 12:05:00",
        end_reason="correction",
    )
)
stored = db.fetch_admin_card_detail(card_id)["timing_segments"][-1]
assert response.status_code == 303
assert stored["started_at"] == "2026-06-18 08:05:00"
assert stored["ended_at"] == "2026-06-18 09:05:00"
```

Add a route test for an existing autumn repeated-hour segment: render its
`+03:00` or `+02:00` input from Task 3, post it unchanged, and assert the exact
original UTC text remains stored.

- [ ] **Step 2: Add a failing global-save atomicity test**

In `tests/test_admin_card_detail_redesign.py`, build the full global form from
the rendered/current card, change an imported field and one roll value, but
submit `new_started_at="2026-03-29 03:30:00"`. Assert:

```python
assert response.status_code == 200
assert "не съществува в Europe/Sofia" in response.body.decode("utf-8")
assert db.fetch_admin_card_detail(card_id) == before
```

Add a parallel ambiguous-hour assertion requiring the message to mention both
`+02:00` and `+03:00`. This proves validation occurs before any imported,
material, roll, or timing write in the shared transaction.

- [ ] **Step 3: Run the focused correction tests and observe raw-local storage failures**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_admin_production_corrections.py \
  tests/test_admin_card_detail_redesign.py \
  -q
```

Expected: new route tests show local values would currently be stored without
conversion; DST tests lack the required validation.

- [ ] **Step 4: Convert individual and ledger inputs at the FastAPI boundary**

Import `LocalTimeInputError` and `parse_sofia_input` in `app/main.py`, then add:

```python
def canonical_timing_values(started_at: Any, ended_at: Any) -> tuple[str, str]:
    return (
        parse_sofia_input(started_at, label="Начало", required=True),
        parse_sofia_input(ended_at, label="Край", required=False),
    )
```

Replace the collection logic in `timing_ledger_from_form()` with a two-pass
collector so start/end values for one row are converted together. Convert the
new row only when either new start or new end is nonblank; otherwise preserve
the entirely blank row so the DB layer keeps ignoring it:

```python
def timing_ledger_from_form(
    form: Any,
) -> tuple[dict[int, dict[str, str]], set[int], list[dict[str, str]]]:
    raw_updates: dict[int, dict[str, str]] = {}
    delete_segment_ids: set[int] = set()

    for key, value in form.multi_items():
        text_value = str(value or "")
        if key == "delete_segment_id":
            delete_segment_ids.add(int(text_value))
        elif "__" in key:
            field_name, segment_id_text = key.split("__", 1)
            if field_name in {"started_at", "ended_at", "end_reason"}:
                segment_id = int(segment_id_text)
                raw_updates.setdefault(segment_id, {})[field_name] = text_value

    segment_updates: dict[int, dict[str, str]] = {}
    for segment_id, values in raw_updates.items():
        if segment_id in delete_segment_ids:
            continue
        canonical_start, canonical_end = canonical_timing_values(
            values.get("started_at", ""), values.get("ended_at", "")
        )
        segment_updates[segment_id] = {
            "started_at": canonical_start,
            "ended_at": canonical_end,
            "end_reason": values.get("end_reason", ""),
        }

    new_started_at = str(form.get("new_started_at") or "")
    new_ended_at = str(form.get("new_ended_at") or "")
    if new_started_at.strip() or new_ended_at.strip():
        canonical_start, canonical_end = canonical_timing_values(
            new_started_at, new_ended_at
        )
    else:
        canonical_start, canonical_end = "", ""
    new_segment = {
        "started_at": canonical_start,
        "ended_at": canonical_end,
        "end_reason": str(form.get("new_end_reason") or ""),
    }
    return segment_updates, delete_segment_ids, [new_segment]
```

Do not change `app/db.py` parsing or its `TIMING_TIMESTAMP_FORMAT`; DB APIs
remain canonical UTC interfaces for internal callers and direct tests.

In individual add/update routes, convert before the DB call. Catch
`LocalTimeInputError` and create:

```python
timing_result = RuleResult(False, (str(exc),))
```

Keep malformed segment-ID handling separate as the existing generic
`"Формата съдържа невалиден времеви сегмент."` message.

- [ ] **Step 5: Move complete-ledger conversion ahead of global transaction writes**

Inside `save_all_admin_card_changes()`, retain version/status and imported-card
payload checks first. Immediately after those checks—but before
`update_admin_imported_fields()`—call `timing_ledger_from_form(form)` and return
the `LocalTimeInputError` message on failure. Reuse the converted structures at
the later `update_admin_timing_ledger()` call. This ordering preserves the
special imported-card rejection and guarantees a bad time cannot be discovered
after another production field has been updated.

Apply the same exception mapping in `/timing-ledger`; its DB call must receive
only canonical values.

- [ ] **Step 6: Run correction tests plus canonical DB-layer regressions**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_timekeeping.py \
  tests/test_admin_production_corrections.py \
  tests/test_admin_card_detail_redesign.py \
  -q
```

Expected: route/global tests pass, repeated-hour round trips are exact, invalid
forms are atomic, and existing direct `db.*timing*` tests continue accepting
canonical UTC strings unchanged.

- [ ] **Step 7: Stop at the Task 4 review boundary**

Review all calls to `add_timing_segment`, `update_timing_segment`, and
`update_admin_timing_ledger`. UI route calls must convert; internal/database
tests and production action code must continue passing UTC. Do not stage or
commit.

---

### Task 5: Synchronize The Terminal Live Clock To SQLite Time

**Files:**
- Modify: `app/db.py:949-1070`
- Modify: `app/templates/_terminal_shift_window.html:13-25`
- Modify: `app/templates/terminal.html:4655-4695, 5245-5338`
- Modify: `tests/test_terminal_sync.py`
- Modify: `tests/test_shift_routes.py`

**Interfaces:**
- Consumes: `current_database_timestamp(connection) -> str` and the existing ten-second `/terminal/snapshot` poll.
- Produces: snapshot field `server_now_utc: str`, initial DOM attribute `data-server-now-utc`, and `terminal:server-time` events that refresh the JavaScript offset before signature comparison.

- [ ] **Step 1: Add failing snapshot tests for the server sample and signature exclusion**

In `tests/test_terminal_sync.py`, add:

```python
def test_terminal_snapshot_samples_database_utc_without_signing_it(connection, monkeypatch):
    samples = iter(("2026-07-31 08:00:00", "2026-07-31 08:00:10"))
    monkeypatch.setattr(db, "current_database_timestamp", lambda connection: next(samples))

    before = db.terminal_snapshot()
    after = db.terminal_snapshot()

    assert before["server_now_utc"] == "2026-07-31 08:00:00"
    assert after["server_now_utc"] == "2026-07-31 08:00:10"
    assert before["signature"] == after["signature"]
    assert before["active_signature"] == after["active_signature"]
    assert before["waiting_signature"] == after["waiting_signature"]
```

Add a route assertion that JSON includes the field and an initial-render
assertion that the shift overlay contains
`data-server-now-utc="YYYY-MM-DD HH:MM:SS"`.

- [ ] **Step 2: Add failing source-contract tests for polling order and clock fallback**

Read `app/templates/terminal.html` as text and isolate the polling block. Require:

```python
event_text = 'document.dispatchEvent(new CustomEvent("terminal:server-time"'
assert event_text in template
assert template.index(event_text) < template.index(
    "if (snapshot.signature === currentSignature)"
)
assert "Date.now() + shiftClockOffsetMs" in template
assert "const now = new Date();" not in shift_clock_block
```

Also require the `catch` block not to reset `shiftClockOffsetMs`; failed polls
must leave the last valid offset active.

- [ ] **Step 3: Run snapshot/shift tests and observe missing sample failures**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_sync.py tests/test_shift_routes.py -q
```

Expected: `server_now_utc`, the initial data attribute, and synchronization
source assertions fail.

- [ ] **Step 4: Sample SQLite time inside the existing terminal snapshot transaction**

In `db.terminal_snapshot()`, immediately after `connection.execute("BEGIN")`,
add:

```python
server_now_utc = current_database_timestamp(connection)
```

Add only this top-level return field:

```python
"server_now_utc": server_now_utc,
```

Do not add it to `active_signature`, `waiting_signature`, `selected_signature`,
`shift_signature`, or composite `signature`. Do not open another connection or
transaction for the sample.

- [ ] **Step 5: Initialize and update the live clock from server samples**

Add the raw initial sample to the shift overlay in
`_terminal_shift_window.html`:

```jinja2
data-server-now-utc="{{ terminal_snapshot.server_now_utc }}"
```

Replace the browser-only clock initialization in `terminal.html` with:

```javascript
let shiftClockOffsetMs = 0;

const parseDatabaseUtc = (value) => {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)) {
    return Number.NaN;
  }
  return Date.parse(`${value.replace(" ", "T")}Z`);
};

const synchronizeShiftClock = (serverNowUtc) => {
  const serverMillis = parseDatabaseUtc(serverNowUtc);
  if (!Number.isFinite(serverMillis)) {
    return;
  }
  shiftClockOffsetMs = serverMillis - Date.now();
  updateShiftClocks();
};

const updateShiftClocks = () => {
  const now = new Date(Date.now() + shiftClockOffsetMs);
  // Keep the existing Europe/Sofia Intl formatting and UTC dateTime assignment.
};

document.addEventListener("terminal:server-time", (event) => {
  synchronizeShiftClock(event.detail?.serverNowUtc);
});

synchronizeShiftClock(shiftWindow.dataset.serverNowUtc);
window.setInterval(updateShiftClocks, 1000);
```

In `pollSnapshot()`, immediately after `await response.json()` and before the
signature early return, dispatch:

```javascript
document.dispatchEvent(new CustomEvent("terminal:server-time", {
  detail: { serverNowUtc: snapshot.server_now_utc },
}));
```

Do not reset the offset in `catch`, do not make current time part of stale-data
alerts, and do not alter production action POSTs.

- [ ] **Step 6: Run Python and JavaScript checks**

Run:

```bash
.venv/bin/python -m pytest tests/test_terminal_sync.py tests/test_shift_routes.py -q
node --check scripts/render_print_template.mjs
```

Then render `terminal.html` through the existing test helper and run the
repository's existing terminal JavaScript execution coverage:

```bash
.venv/bin/python -m pytest tests/test_terminal_v8_render.py -q
```

Expected: all pass; advancing only `server_now_utc` leaves signatures stable,
and the clock refresh event appears before the unchanged-signature return.

- [ ] **Step 7: Stop at the Task 5 review boundary**

Inspect the snapshot return dictionary and the JavaScript poll once more. The
sample must come from the same SQLite transaction, be absent from all
signatures, and never control persisted timestamps. Do not stage or commit.

---

### Task 6: Add Guarded Browser Evidence For Admin, Terminal, And Print

**Files:**
- Modify: `scripts/create_print_template_fixture.py:65-175`
- Create: `scripts/verify_time_handling_ui.mjs`
- Create: `tests/test_time_handling_ui_script_safety.py`

**Interfaces:**
- Consumes: the existing guarded print fixture database creator, `/admin/cards/{id}`, `/terminal`, and `/cards/{id}/print`.
- Produces: a fixture whose UTC start crosses the Sofia date boundary and repeatable screenshots/PDF under `artifacts/ui-checks/unified-time-handling/`.

- [ ] **Step 1: Write failing fixture and verifier-safety tests**

Create `tests/test_time_handling_ui_script_safety.py`. Import
`scripts.create_print_template_fixture` as `fixture`, monkeypatch its
`ROOT_DIR` to `tmp_path`, and create
`tmp_path / ".test-runtime/time-handling/fixture.sqlite3"` through
`fixture.resolve_fixture_db_path()`, `fixture.reset_database()`, and
`fixture.create_dense_completed_card()`. This exercises the real path guard
while keeping all writes inside pytest's temporary directory. Read the
resulting SQLite rows and require the values below. Before calling
`fixture.reset_database()`, use `monkeypatch.setattr()` for `db.DATA_DIR` and
`db.DB_PATH` with that temporary path so pytest restores both globals after the
test; do not allow this safety test to leak its DB selection into later tests.

```python
assert card["first_started_at"] == "2026-06-18 21:35:00"
assert card["finished_at"] == "2026-06-19 04:15:00"
assert segments == [
    ("2026-06-18 21:35:00", "2026-06-18 23:40:00"),
    ("2026-06-19 00:00:00", "2026-06-19 01:50:00"),
    ("2026-06-19 02:20:00", "2026-06-19 04:15:00"),
]
assert active_shift == (1, "2026-06-19 04:00:00", None)
```

Read the new JavaScript source and require exact safety/behavior tokens:

```python
assert "artifacts/ui-checks" in source
assert "realpathSync" in source
assert "19.06.2026 00:35:00" in source
assert "2026-06-19 00:35:00" in source
assert "19.06.2026 00:35" in source
assert "#admin-card-save-form" in source
assert 'click("#history-open")' in source
assert "page.pdf" in source
assert "data/extrusion_terminal.sqlite3" not in source
assert "production-db" not in source
```

- [ ] **Step 2: Run the safety tests and observe fixture/source failures**

Run:

```bash
.venv/bin/python -m pytest tests/test_time_handling_ui_script_safety.py -q
```

Expected: the fixture times differ and the verifier file is absent.

- [ ] **Step 3: Make the existing print fixture cross Bulgarian midnight**

In `create_dense_completed_card()`, change only canonical UTC production
timestamps to:

```python
first_started_at = "2026-06-18 21:35:00"
finished_at = "2026-06-19 04:15:00"
segments = (
    (card_id, "2026-06-18 21:35:00", "2026-06-18 23:40:00", "pause"),
    (card_id, "2026-06-19 00:00:00", "2026-06-19 01:50:00", "pause"),
    (card_id, "2026-06-19 02:20:00", "2026-06-19 04:15:00", "finish"),
)
```

Keep order/delivery dates, dense content, roll count, weights, and fixture path
guard unchanged. Also insert one open shift occurrence so `/terminal` is not
blocked by the mandatory shift-start gate during the produced-history check:

```python
connection.execute(
    """
    INSERT INTO shift_occurrences (shift_number, started_at, ended_at)
    VALUES (1, '2026-06-19 04:00:00', NULL)
    """
)
```

The safety test obtains `active_shift` with a query ordered by `id DESC LIMIT
1`. The shift is test-fixture state only; do not add an active shift to a
runtime or production database.

- [ ] **Step 4: Create the guarded Playwright verifier**

Implement `scripts/verify_time_handling_ui.mjs` using the path-containment
preflight pattern from `scripts/render_print_template.mjs`. Accept `--base-url`,
`--card-id`, and `--output-dir`; resolve the output directory and reject it
unless its nearest existing real ancestor is at/below `artifacts/ui-checks`.

The browser workflow must perform these exact assertions and captures:

```javascript
await page.goto(`${baseUrl}/admin/cards/${cardId}`, { waitUntil: "networkidle" });
await expectText(page, "Първи старт", "19.06.2026 00:35:00");
const startInput = page.locator('input[name^="started_at__"]').first();
if (await startInput.inputValue() !== "2026-06-19 00:35:00") {
  throw new Error("Admin timing input is not Sofia local time");
}
await page.screenshot({ path: path.join(outputDir, "admin-local-time.png"), fullPage: true });
await page.click('#admin-card-save-form button[type="submit"], button[form="admin-card-save-form"]');
await page.waitForLoadState("networkidle");
if (await page.locator('input[name^="started_at__"]').first().inputValue() !== "2026-06-19 00:35:00") {
  throw new Error("Unchanged admin timing input did not round-trip");
}

await page.goto(`${baseUrl}/terminal`, { waitUntil: "networkidle" });
await page.click("#history-open");
await expectText(page, "#history-overlay", "19.06.2026 07:15:00");
await page.locator("#history-overlay").screenshot({ path: path.join(outputDir, "terminal-produced-local-time.png") });

await page.goto(`${baseUrl}/cards/${cardId}/print`, { waitUntil: "networkidle" });
if (await page.locator('[data-summary-field="start"]').innerText() !== "19.06.2026 00:35") {
  throw new Error("Printed start time is not Sofia local time");
}
await page.locator(".print-page-back").screenshot({ path: path.join(outputDir, "print-local-time-back.png") });
await page.pdf({
  path: path.join(outputDir, "print-local-time.pdf"),
  format: "A4",
  printBackground: true,
  margin: { top: "0", right: "0", bottom: "0", left: "0" },
});
```

Define `expectText(page, selectorOrLabel, expected)` concretely: when passed a
CSS selector, assert the locator contains the text; otherwise locate the detail
row whose `dt` has the label and assert its sibling `dd`. Launch only the
repository-imported `chromium` from `playwright`, close it in `finally`, and
write a JSON metadata file listing URL, card ID, expected UTC/local values, and
artifact paths.

- [ ] **Step 5: Run static safety and syntax checks**

Run:

```bash
.venv/bin/python -m pytest tests/test_time_handling_ui_script_safety.py -q
node --check scripts/verify_time_handling_ui.mjs
```

Expected: both pass without starting the app or touching the runtime DB.

- [ ] **Step 6: Run the guarded live workflow against a temporary database**

In terminal A:

```bash
.venv/bin/python scripts/create_print_template_fixture.py \
  --db-path .test-runtime/unified-time-handling/fixture.sqlite3 \
  --order-number TIME-HANDLING-001
EXTRUSION_DB_PATH="$PWD/.test-runtime/unified-time-handling/fixture.sqlite3" \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

The fresh fixture creates card ID `1`; confirm that ID in the printed JSON
before continuing. In terminal B:

```bash
./node_modules/.bin/playwright --version
node scripts/verify_time_handling_ui.mjs \
  --base-url http://127.0.0.1:8010 \
  --card-id 1 \
  --output-dir artifacts/ui-checks/unified-time-handling
```

Expected artifacts:

- `admin-local-time.png`
- `terminal-produced-local-time.png`
- `print-local-time-back.png`
- `print-local-time.pdf`
- `metadata.json`

Stop the temporary server with `Ctrl-C`. Do not copy or point the workflow at a
runtime/production database.

- [ ] **Step 7: Inspect the three screenshots and PDF**

Confirm visually that admin, terminal, and print all identify the same
production instant in Sofia time, the admin input includes seconds, print uses
minutes, and the print layout remains two A4 pages. Record the exact verifier
command in the final implementation report. Do not stage or commit.

---

### Task 7: Document The Contract And Run The Complete Safety Gate

**Files:**
- Modify: `README.md`
- Modify: `docs/implementation-notes/print-output-reference.md`
- Modify: `docs/implementation-notes/shift-management.md`
- Create: `docs/implementation-notes/time-handling.md`
- Verify: every file changed in Tasks 1-6

**Interfaces:**
- Consumes: the final verified behavior and exact commands from earlier tasks.
- Produces: authoritative operational documentation and evidence that the whole repository remains safe with no schema/data migration.

- [ ] **Step 1: Write the authoritative README time contract**

Add a concise `Time handling` section near runtime/database operations with
these exact rules:

```markdown
## Time handling

- SQLite/server `CURRENT_TIMESTAMP` is the source of truth for production and shift actions.
- Production instants are stored as UTC text in `YYYY-MM-DD HH:MM:SS` form.
- Operators, admins, and printed cards see `Europe/Sofia` civil time; the host and browser timezone do not select the business timezone.
- Admin timing corrections are entered as Sofia local `YYYY-MM-DD HH:MM:SS`. Repeated autumn-hour values require `+02:00` or `+03:00`; skipped spring-hour values are rejected.
- Order and delivery dates are date-only and are not timezone converted. The roll-change countdown is a non-persisted workstation reminder.
- This contract requires no schema or production-data migration. Do not shift existing stored timestamps.
```

Add a deployment checklist item: take the normal SQLite-safe backup, then
compare one known completed card's admin detail and print output in Sofia time.

- [ ] **Step 2: Update durable implementation notes with concrete behavior**

In `print-output-reference.md`, state that start/stop values are canonical UTC
converted via `app.timekeeping.format_print_datetime()` to
`DD.MM.YYYY HH:MM`, and malformed required values block print.

In `shift-management.md`, replace any implication that browser time is
authoritative with: persisted shift actions use SQLite UTC; shift displays use
the shared Sofia formatter; the live clock interpolates from
`server_now_utc`, refreshes every snapshot poll, and never participates in a
snapshot signature or production write.

Create `time-handling.md` with these headings and concrete content:

```markdown
# Time Handling

## Canonical Storage And Source Of Truth
## Shared `app/timekeeping.py` API
## Presentation Field Convention
## Admin Correction And DST Rules
## Terminal Server-Clock Synchronization
## Explicit Date/Countdown/Backup Exceptions
## Production Snapshot Assessment
## No-Migration Decision
## Deployment Verification
```

Under the production assessment, record the inspected snapshot path, SHA-256
`f3786bb80fa4bf6e99a50e1f0c918f8db766450af42e1d3d90ccb08b53e3f481`,
integrity/foreign-key results, migrations M001-M006, 35 cards, 35 segments, no
correction indicators, and unchanged inspection hash. Explicitly state that no
snapshot value was modified and no M007 exists for this feature.

- [ ] **Step 3: Run syntax and focused regression checks**

Run:

```bash
.venv/bin/python -m compileall -q app tests scripts
node --check scripts/render_print_template.mjs
node --check scripts/verify_time_handling_ui.mjs
.venv/bin/python -m pytest \
  tests/test_timekeeping.py \
  tests/test_print_output.py \
  tests/test_admin_routes.py \
  tests/test_admin_production_corrections.py \
  tests/test_admin_card_detail_redesign.py \
  tests/test_shift_routes.py \
  tests/test_shift_management.py \
  tests/test_terminal_sync.py \
  tests/test_terminal_v8_render.py \
  tests/test_time_handling_ui_script_safety.py \
  -q
```

Expected: compilation/syntax checks exit `0` and every focused test passes.
The pre-change affected baseline was 371 passing tests; investigate any
regression instead of updating unrelated expectations.

- [ ] **Step 4: Run the complete Python suite**

Run:

```bash
.venv/bin/python -m pytest
```

Expected: the complete suite passes. Do not claim completion from the focused
suite alone.

- [ ] **Step 5: Verify a fresh temporary database remains structurally healthy**

Against the Task 6 fixture only, run:

```bash
EXTRUSION_DB_PATH="$PWD/.test-runtime/unified-time-handling/fixture.sqlite3" \
  .venv/bin/python -c "from app import db; c=db.connect(); print(c.execute('PRAGMA integrity_check').fetchone()[0]); print(c.execute('PRAGMA foreign_key_check').fetchall()); c.close()"
```

Expected output is `ok` followed by `[]`. This is a verification of the
temporary fixture, not a migration step.

- [ ] **Step 6: Prove migration and production files were not touched**

Run:

```bash
git diff -- app/schema.py app/migrations.py production-db data/extrusion_terminal.sqlite3
git status --short
```

Expected: the targeted diff command is empty. In status output, distinguish
the user's pre-existing unrelated changes from this feature's files; do not
delete, stage, or rewrite either set.

- [ ] **Step 7: Run final diff checks and self-review against the specification**

Run:

```bash
git diff --check
rg -n "TO[D]O|TB[D]|FIXM[E]|PLACEH[O]LDER" \
  app/timekeeping.py tests/test_timekeeping.py \
  docs/implementation-notes/time-handling.md
```

Expected: `git diff --check` exits `0` and the placeholder scan has no matches.
Then map each section of
`docs/superpowers/specs/2026-07-31-unified-time-handling-design.md` to a passing
test, documentation paragraph, or explicit out-of-scope statement. Correct any
gap before reporting completion.

- [ ] **Step 8: Prepare the implementation handoff without staging or committing**

Report:

- the files changed;
- focused and full-suite test counts;
- the exact Playwright command and artifact paths;
- confirmation that raw UTC round trips are exact;
- confirmation that print/admin/terminal show Sofia time;
- confirmation that `server_now_utc` is not signed;
- confirmation that no schema, migration, production database, or production
  timestamp was changed; and
- the deployment-only instruction to take a SQLite-safe backup and spot-check
  one known card before rollout.

Do not stage or commit until the user gives separate explicit authorization.
