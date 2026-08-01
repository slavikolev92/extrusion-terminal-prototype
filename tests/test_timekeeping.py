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
    with pytest.raises(
        StoredTimestampError,
        match="required stored UTC timestamp is missing",
    ):
        parse_stored_utc(" \t\n ", required=True)
    with pytest.raises(StoredTimestampError):
        parse_stored_utc("broken")


@pytest.mark.parametrize(
    "value",
    [
        " 2026-06-18 21:35:29",
        "2026-06-18 21:35:29 ",
        "\t2026-06-18 21:35:29\n",
    ],
)
@pytest.mark.parametrize("required", [False, True])
def test_parse_stored_utc_rejects_padding_around_nonblank_timestamp(
    value,
    required,
):
    with pytest.raises(StoredTimestampError, match="not canonical"):
        parse_stored_utc(value, required=required)


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
