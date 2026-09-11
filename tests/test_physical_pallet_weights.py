import asyncio
import csv
import io
import json
from decimal import Decimal

import pytest

from app import db, main
from app.constants import (
    STATUS_ARCHIVED,
    STATUS_AWAITING_REWINDING,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_IMPORTED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_RUNNING,
)
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.pallet_summary import (
    PalletSummaryDataError,
    parse_physical_pallet_weight,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("", None),
        ("   ", None),
        ("12", 1200),
        ("12.0", 1200),
        ("12,5", 1250),
        ("10.35", 1035),
        ("12.54", 1254),
        ("12,55", 1255),
        ("0.01", 1),
        ("0.1", 10),
        ("100", 10000),
        ("100.00", 10000),
    ),
)
def test_parse_physical_pallet_weight_accepts_approved_values(raw, expected):
    assert parse_physical_pallet_weight(raw, 3) == (expected, None)


@pytest.mark.parametrize(
    "raw",
    ("0", "0.0", "-1", "12.555", ".5", "1e1", "NaN", "12 5", "101"),
)
def test_parse_physical_pallet_weight_rejects_invalid_values(raw):
    value, message = parse_physical_pallet_weight(raw, 3)
    assert value is None
    assert message is not None
    assert "палет №3" in message


@pytest.mark.parametrize(
    "raw",
    ("100.1", "330", "0" * 5000 + "101"),
    ids=("one-tenth-over", "whole-over", "hostile-oversized"),
)
def test_parse_physical_pallet_weight_uses_the_specific_maximum_message(raw):
    assert parse_physical_pallet_weight(raw, 3) == (
        None,
        "Теглото за палет №3 не може да бъде повече от 100.00 кг.",
    )


@pytest.mark.parametrize("raw", ("-5", "0.00"))
def test_parse_physical_pallet_weight_uses_the_specific_minimum_message(raw):
    assert parse_physical_pallet_weight(raw, 3) == (
        None,
        "Теглото за палет №3 трябва да бъде поне 0.01 кг.",
    )


def test_parse_physical_pallet_weight_reports_two_decimal_format_limit():
    assert parse_physical_pallet_weight("12.555", 3) == (
        None,
        "Теглото за палет №3 трябва да бъде число "
        "с най-много два десетични знака.",
    )


def _insert_card(connection, order_number="PW-SUMMARY"):
    cursor = connection.execute(
        "INSERT INTO cards (order_number) VALUES (?)",
        (order_number,),
    )
    return int(cursor.lastrowid)


def _insert_roll(
    connection,
    card_id,
    *,
    roll_number,
    gross_weight,
    tare_weight,
    net_weight,
    pallet_number,
):
    connection.execute(
        """
        INSERT INTO roll_entries (
            card_id, order_number, roll_number, gross_weight, tare_weight,
            net_weight, pallet_number
        )
        VALUES (?, (SELECT order_number FROM cards WHERE id = ?), ?, ?, ?, ?, ?)
        """,
        (
            card_id,
            card_id,
            roll_number,
            gross_weight,
            tare_weight,
            net_weight,
            pallet_number,
        ),
    )


def _insert_weightable_card(
    connection,
    *,
    order_number,
    status=STATUS_PENDING,
    pallet_numbers=(1,),
    corrupt_net=False,
):
    cursor = connection.execute(
        "INSERT INTO cards (order_number, status) VALUES (?, ?)",
        (order_number, status),
    )
    card_id = int(cursor.lastrowid)
    for index, pallet_number in enumerate(pallet_numbers, start=1):
        gross = Decimal("20.00") + index
        tare = Decimal("1.00")
        net = gross - tare - (Decimal("1.00") if corrupt_net else Decimal("0"))
        _insert_roll(
            connection,
            card_id,
            roll_number=index,
            gross_weight=format(gross, "f"),
            tare_weight=format(tare, "f"),
            net_weight=format(net, "f"),
            pallet_number=pallet_number,
        )
    connection.commit()
    return card_id


def _stored_pallet_state(connection, card_id):
    card = connection.execute(
        "SELECT status, version FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()
    weights = connection.execute(
        """
        SELECT pallet_number, weight_hundredths
        FROM card_pallet_weights
        WHERE card_id = ?
        ORDER BY pallet_number
        """,
        (card_id,),
    ).fetchall()
    return (
        (str(card["status"]), int(card["version"])),
        tuple((int(row["pallet_number"]), int(row["weight_hundredths"])) for row in weights),
    )


def _csv_bytes(*rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")


def _extrusion_row(order_number, *, customer="Pallet Customer"):
    return {
        "order_number": order_number,
        "customer": customer,
        "product_type": "PE film",
        "ordered_gross_kg": "500",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_sequence": "1",
        "raw_material_a": "LDPE; A | 100%",
        "packaging_method": "rolls",
    }


class _MultiItemForm:
    def __init__(self, items):
        self._items = items

    def multi_items(self):
        return list(self._items)


class _FormRequest:
    def __init__(self, items):
        self._form = _MultiItemForm(items)

    async def form(self):
        return self._form


def _response_payload(response):
    return json.loads(response.body)


@pytest.mark.parametrize(
    ("items", "submitted_weight", "expected_field", "expected_pallet"),
    (
        ([('pallet_weight', ' 12,5 ')], ' 12,5 ', 'form', None),
        (
            [
                ('loaded_version', '1'),
                ('loaded_version', '1'),
                ('pallet_weight', '12.5'),
            ],
            '12.5',
            'form',
            None,
        ),
        ([('loaded_version', '1')], '', 'pallet_weight', 1),
        (
            [
                ('loaded_version', '1'),
                ('pallet_weight', ' 12.5 '),
                ('pallet_weight', '13.5'),
            ],
            ' 12.5 ',
            'pallet_weight',
            1,
        ),
        (
            [
                ('loaded_version', '1'),
                ('pallet_weight', '12.5'),
                ('unexpected', 'value'),
            ],
            '12.5',
            'form',
            None,
        ),
        (
            [('loaded_version', 'not-an-integer'), ('pallet_weight', '12.5')],
            '12.5',
            'form',
            None,
        ),
    ),
    ids=(
        'missing-version',
        'duplicate-version',
        'missing-weight',
        'duplicate-weight',
        'unexpected-field',
        'invalid-version',
    ),
)
def test_pallet_weight_form_rejects_non_exact_request_shape_without_writing(
    connection,
    active_test_shift,
    items,
    submitted_weight,
    expected_field,
    expected_pallet,
):
    card_id = _insert_weightable_card(
        connection,
        order_number=f"PW-FORM-{items!r}",
    )
    before = _stored_pallet_state(connection, card_id)

    response = asyncio.run(
        main.save_terminal_pallet_weight(
            _FormRequest(items),
            card_id,
            1,
        )
    )
    payload = _response_payload(response)

    assert response.status_code == 422
    assert set(payload) == {
        'ok',
        'submitted_weight',
        'messages',
        'field_errors',
        'reload_required',
    }
    assert payload['ok'] is False
    assert payload['submitted_weight'] == submitted_weight
    assert payload['reload_required'] is False
    assert payload['field_errors'] == [
        {
            'pallet_number': expected_pallet,
            'field': expected_field,
            'message': payload['messages'][0],
        }
    ]
    assert _stored_pallet_state(connection, card_id) == before


def test_terminal_pallet_weight_route_returns_authoritative_json_strings(
    connection,
    active_test_shift,
):
    card_id = _insert_weightable_card(
        connection,
        order_number="PW-TERMINAL-ROUTE-SUCCESS",
    )

    response = asyncio.run(
        main.save_terminal_pallet_weight(
            _FormRequest(
                [('loaded_version', '1'), ('pallet_weight', '10,35')]
            ),
            card_id,
            1,
        )
    )

    assert response.status_code == 200
    assert _response_payload(response) == {
        'ok': True,
        'card_version': 2,
        'pallet_number': 1,
        'normalized_weight': '10.35',
        'row': {
            'pallet_number': 1,
            'pallet_label': '1',
            'roll_count': 1,
            'gross_without_pallet_display': '21.0',
            'pallet_weight_display': '10.35',
            'gross_with_pallet_display': '31.35',
            'net_display': '20.0',
        },
        'total': {
            'roll_count': 1,
            'gross_without_pallet_display': '21.0',
            'pallet_weight_display': '10.35',
            'gross_with_pallet_display': '31.35',
            'net_display': '20.0',
        },
        'weight_state': 'complete',
        'messages': ['Теглото за палет №1 е записано.'],
        'reload_required': False,
    }
    assert db.fetch_card_pallet_weights(connection, card_id) == {1: 1035}

    cleared = asyncio.run(
        main.save_terminal_pallet_weight(
            _FormRequest(
                [('loaded_version', '2'), ('pallet_weight', '   ')]
            ),
            card_id,
            1,
        )
    )
    cleared_payload = _response_payload(cleared)

    assert cleared.status_code == 200
    assert cleared_payload['card_version'] == 3
    assert cleared_payload['normalized_weight'] == ''
    assert cleared_payload['row']['pallet_weight_display'] == '-'
    assert cleared_payload['row']['gross_with_pallet_display'] == '-'
    assert cleared_payload['total']['pallet_weight_display'] == '-'
    assert cleared_payload['total']['gross_with_pallet_display'] == '-'
    assert cleared_payload['weight_state'] == 'none'
    assert cleared_payload['reload_required'] is False
    assert db.fetch_card_pallet_weights(connection, card_id) == {}


def test_terminal_pallet_weight_route_preserves_invalid_raw_text_and_state(
    connection,
    active_test_shift,
):
    card_id = _insert_weightable_card(
        connection,
        order_number="PW-TERMINAL-ROUTE-INVALID",
    )
    before = _stored_pallet_state(connection, card_id)

    response = asyncio.run(
        main.save_terminal_pallet_weight(
            _FormRequest(
                [('loaded_version', '1'), ('pallet_weight', ' 12.555 ')]
            ),
            card_id,
            1,
        )
    )
    payload = _response_payload(response)

    assert response.status_code == 422
    assert payload['submitted_weight'] == ' 12.555 '
    assert payload['field_errors'] == [
        {
            'pallet_number': 1,
            'field': 'pallet_weight',
            'message': payload['messages'][0],
        }
    ]
    assert payload['reload_required'] is False
    assert _stored_pallet_state(connection, card_id) == before


@pytest.mark.parametrize('pallet_number', (0, 2, 1000))
def test_terminal_pallet_weight_route_rejects_out_of_range_or_unused_pallet(
    connection,
    active_test_shift,
    pallet_number,
):
    card_id = _insert_weightable_card(
        connection,
        order_number=f"PW-TERMINAL-ROUTE-TARGET-{pallet_number}",
    )
    before = _stored_pallet_state(connection, card_id)

    response = asyncio.run(
        main.save_terminal_pallet_weight(
            _FormRequest(
                [('loaded_version', '1'), ('pallet_weight', '12.5')]
            ),
            card_id,
            pallet_number,
        )
    )
    payload = _response_payload(response)

    assert response.status_code == 422
    assert payload['submitted_weight'] == '12.5'
    assert payload['field_errors'][0]['pallet_number'] == pallet_number
    assert payload['field_errors'][0]['field'] == 'pallet_weight'
    assert _stored_pallet_state(connection, card_id) == before


def test_terminal_pallet_weight_route_requires_shift_and_stale_requires_reload(
    connection,
    active_test_shift,
):
    card_id = _insert_weightable_card(
        connection,
        order_number="PW-TERMINAL-ROUTE-RECOVERY",
    )
    connection.execute(
        "UPDATE cards SET version = 2 WHERE id = ?",
        (card_id,),
    )
    connection.commit()
    before = _stored_pallet_state(connection, card_id)

    stale = asyncio.run(
        main.save_terminal_pallet_weight(
            _FormRequest(
                [('loaded_version', '1'), ('pallet_weight', ' 14,5 ')]
            ),
            card_id,
            1,
        )
    )
    stale_payload = _response_payload(stale)

    assert stale.status_code == 409
    assert stale_payload == {
        'ok': False,
        'submitted_weight': ' 14,5 ',
        'messages': [db.STALE_CARD_MESSAGE],
        'field_errors': [
            {
                'pallet_number': None,
                'field': 'form',
                'message': db.STALE_CARD_MESSAGE,
            }
        ],
        'reload_required': True,
    }
    assert _stored_pallet_state(connection, card_id) == before

    shift = db.fetch_active_shift()
    assert shift is not None
    assert db.end_shift(int(shift['id']), int(shift['version'])).ok
    no_shift = asyncio.run(
        main.save_terminal_pallet_weight(
            _FormRequest(
                [('loaded_version', '2'), ('pallet_weight', ' 14,5 ')]
            ),
            card_id,
            1,
        )
    )
    no_shift_payload = _response_payload(no_shift)

    assert no_shift.status_code == 422
    assert no_shift_payload['submitted_weight'] == ' 14,5 '
    assert no_shift_payload['messages'] == [db.NO_ACTIVE_SHIFT_MESSAGE]
    assert no_shift_payload['field_errors'] == [
        {
            'pallet_number': None,
            'field': 'form',
            'message': db.NO_ACTIVE_SHIFT_MESSAGE,
        }
    ]
    assert no_shift_payload['reload_required'] is False
    assert _stored_pallet_state(connection, card_id) == before


def test_fetch_card_pallet_weights_returns_integer_hundredths(connection):
    card_id = _insert_card(connection)
    connection.executemany(
        """
        INSERT INTO card_pallet_weights (card_id, pallet_number, weight_hundredths)
        VALUES (?, ?, ?)
        """,
        ((card_id, 2, 1850), (card_id, 7, 2000)),
    )

    assert db.fetch_card_pallet_weights(connection, card_id) == {2: 1850, 7: 2000}


def test_detailed_card_snapshot_includes_physical_pallet_weights(
    connection,
):
    card_id = _insert_card(connection)
    connection.execute(
        """
        INSERT INTO card_pallet_weights (card_id, pallet_number, weight_hundredths)
        VALUES (?, 2, 1850)
        """,
        (card_id,),
    )
    connection.commit()

    card = db.fetch_admin_card_detail(card_id)

    assert card is not None
    assert card["pallet_weights"] == {2: 1850}


def test_load_card_pallet_summary_uses_supplied_connection_snapshot(connection):
    card_id = _insert_card(connection)
    _insert_roll(
        connection,
        card_id,
        roll_number=1,
        gross_weight="230.00",
        tare_weight="4.00",
        net_weight="226.00",
        pallet_number=2,
    )
    connection.execute(
        """
        INSERT INTO card_pallet_weights (card_id, pallet_number, weight_hundredths)
        VALUES (?, 2, 1850)
        """,
        (card_id,),
    )

    summary = db.load_card_pallet_summary(connection, card_id)

    assert summary["weight_state"] == "complete"
    assert summary["rows"][0]["gross_with_pallet"] == Decimal("248.50")


def test_load_card_pallet_summary_propagates_the_data_error(connection):
    card_id = _insert_card(connection)
    _insert_roll(
        connection,
        card_id,
        roll_number=1,
        gross_weight="10.00",
        tare_weight="0.50",
        net_weight="9.50",
        pallet_number=1,
    )
    connection.execute(
        """
        INSERT INTO card_pallet_weights (card_id, pallet_number, weight_hundredths)
        VALUES (?, 9, 1000)
        """,
        (card_id,),
    )

    with pytest.raises(PalletSummaryDataError, match="pallet 9"):
        db.load_card_pallet_summary(connection, card_id)


def test_terminal_pallet_weight_saves_are_isolated_per_card(
    connection,
    active_test_shift,
):
    first_card_id = _insert_weightable_card(
        connection,
        order_number="PW-ISOLATED-1",
    )
    second_card_id = _insert_weightable_card(
        connection,
        order_number="PW-ISOLATED-2",
    )

    first = db.update_terminal_pallet_weight(first_card_id, 1, 1, "12,5")
    second = db.update_terminal_pallet_weight(second_card_id, 1, 1, "20")

    assert first.result.ok
    assert first.card_version == 2
    assert first.saved_weight_hundredths == 1250
    assert first.summary is not None
    assert first.summary["rows"][0]["pallet_weight_display"] == "12.50"
    assert second.result.ok
    assert second.card_version == 2
    assert second.saved_weight_hundredths == 2000
    assert db.fetch_card_pallet_weights(connection, first_card_id) == {1: 1250}
    assert db.fetch_card_pallet_weights(connection, second_card_id) == {1: 2000}


@pytest.mark.parametrize(
    "status",
    (
        STATUS_PENDING,
        STATUS_RUNNING,
        STATUS_PAUSED,
        STATUS_AWAITING_REWINDING,
        STATUS_COMPLETED,
    ),
)
def test_terminal_pallet_weight_allows_independent_partial_saves_and_targeted_clear(
    connection,
    active_test_shift,
    status,
):
    card_id = _insert_weightable_card(
        connection,
        order_number=f"PW-TERMINAL-{status}",
        status=status,
        pallet_numbers=(1, 2),
    )

    first = db.update_terminal_pallet_weight(card_id, 1, 1, "12.5")
    second = db.update_terminal_pallet_weight(card_id, 2, 2, "18")
    cleared = db.update_terminal_pallet_weight(card_id, 1, 3, "   ")

    assert first.result.ok
    assert first.card_version == 2
    assert first.summary is not None
    assert first.summary["weight_state"] == "partial"
    assert second.result.ok
    assert second.card_version == 3
    assert second.summary is not None
    assert second.summary["weight_state"] == "complete"
    assert cleared.result.ok
    assert cleared.card_version == 4
    assert cleared.saved_weight_hundredths is None
    assert db.fetch_card_pallet_weights(connection, card_id) == {2: 1800}


@pytest.mark.parametrize("status", (STATUS_COMPLETED, STATUS_ARCHIVED))
def test_admin_pallet_weight_allows_completed_and_archived_cards(
    connection,
    status,
):
    card_id = _insert_weightable_card(
        connection,
        order_number=f"PW-ADMIN-{status}",
        status=status,
        pallet_numbers=(1, 2),
    )

    first = db.update_admin_pallet_weight(card_id, 1, 1, "15")
    second = db.update_admin_pallet_weight(card_id, 2, 2, "16.5")
    cleared = db.update_admin_pallet_weight(card_id, 1, 3, "")

    assert first.result.ok and first.card_version == 2
    assert second.result.ok and second.card_version == 3
    assert cleared.result.ok and cleared.card_version == 4
    assert db.fetch_card_pallet_weights(connection, card_id) == {2: 1650}


def test_terminal_pallet_weight_requires_active_shift_and_preserves_state(connection):
    card_id = _insert_weightable_card(
        connection,
        order_number="PW-NO-SHIFT",
    )
    before = _stored_pallet_state(connection, card_id)

    blocked = db.update_terminal_pallet_weight(card_id, 1, 1, "12.5")

    assert not blocked.result.ok
    assert blocked.result.messages == (db.NO_ACTIVE_SHIFT_MESSAGE,)
    assert blocked.issues == (
        db.PalletWeightIssue(None, "form", db.NO_ACTIVE_SHIFT_MESSAGE),
    )
    assert _stored_pallet_state(connection, card_id) == before

    allowed_for_internal_use = db.update_terminal_pallet_weight(
        card_id,
        1,
        1,
        "12.5",
        require_active_shift=False,
    )
    assert allowed_for_internal_use.result.ok


@pytest.mark.parametrize("status", (STATUS_IMPORTED, STATUS_ARCHIVED, STATUS_CANCELLED))
def test_terminal_pallet_weight_rejects_non_terminal_status_without_mutation(
    connection,
    active_test_shift,
    status,
):
    card_id = _insert_weightable_card(
        connection,
        order_number=f"PW-TERMINAL-BLOCKED-{status}",
        status=status,
    )
    before = _stored_pallet_state(connection, card_id)

    outcome = db.update_terminal_pallet_weight(card_id, 1, 1, "12.5")

    assert not outcome.result.ok
    assert _stored_pallet_state(connection, card_id) == before


@pytest.mark.parametrize("status", (STATUS_PENDING, STATUS_RUNNING, STATUS_CANCELLED))
def test_admin_pallet_weight_rejects_non_complete_status_without_mutation(
    connection,
    status,
):
    card_id = _insert_weightable_card(
        connection,
        order_number=f"PW-ADMIN-BLOCKED-{status}",
        status=status,
    )
    before = _stored_pallet_state(connection, card_id)

    outcome = db.update_admin_pallet_weight(card_id, 1, 1, "12.5")

    assert not outcome.result.ok
    assert _stored_pallet_state(connection, card_id) == before


def test_pallet_weight_upsert_preserves_created_at(connection, active_test_shift):
    card_id = _insert_weightable_card(
        connection,
        order_number="PW-CREATED-AT",
    )
    assert db.update_terminal_pallet_weight(card_id, 1, 1, "12.5").result.ok
    connection.execute(
        """
        UPDATE card_pallet_weights
        SET created_at = '2020-01-02 03:04:05'
        WHERE card_id = ? AND pallet_number = 1
        """,
        (card_id,),
    )
    connection.commit()

    updated = db.update_terminal_pallet_weight(card_id, 1, 2, "14.5")
    row = connection.execute(
        """
        SELECT weight_hundredths, created_at
        FROM card_pallet_weights
        WHERE card_id = ? AND pallet_number = 1
        """,
        (card_id,),
    ).fetchone()

    assert updated.result.ok
    assert updated.card_version == 3
    assert tuple(row) == (1450, "2020-01-02 03:04:05")


def test_pallet_weight_rejects_unused_invalid_and_stale_targets_without_mutation(
    connection,
    active_test_shift,
):
    card_id = _insert_weightable_card(
        connection,
        order_number="PW-TARGETS",
        pallet_numbers=(1, 3),
    )
    assert db.update_terminal_pallet_weight(card_id, 1, 1, "10").result.ok
    accepted = db.update_terminal_pallet_weight(card_id, 3, 2, "11")
    assert accepted.result.ok
    assert accepted.card_version == 3
    baseline = _stored_pallet_state(connection, card_id)

    cases = (
        (2, 3, "12"),
        (0, 3, "12"),
        (1000, 3, "12"),
        (1, 2, "13"),
        (1, 3, "12.555"),
    )
    for pallet_number, loaded_version, raw_weight in cases:
        outcome = db.update_terminal_pallet_weight(
            card_id,
            pallet_number,
            loaded_version,
            raw_weight,
        )
        assert not outcome.result.ok
        assert outcome.issues
        assert _stored_pallet_state(connection, card_id) == baseline


def test_concurrent_card_write_wins_over_stale_pallet_weight_save(
    connection,
    active_test_shift,
    interleave_committed_card_version,
):
    card_id = _insert_weightable_card(
        connection,
        order_number="PW-CONCURRENT",
    )
    loaded_card = {"id": card_id, "version": 1}

    def stale_save_after_synchronized_read():
        db.validate_loaded_card_version(loaded_card, 1)
        return db.update_terminal_pallet_weight(card_id, 1, 1, "12.5")

    outcome = interleave_committed_card_version(
        card_id,
        1,
        stale_save_after_synchronized_read,
    )
    card = connection.execute(
        "SELECT customer, version FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()

    assert not outcome.result.ok
    assert outcome.result.messages == (db.STALE_CARD_MESSAGE,)
    assert tuple(card) == ("Concurrent writer", 2)
    assert db.fetch_card_pallet_weights(connection, card_id) == {}


def test_corrupt_roll_state_rolls_back_pallet_weight_and_parent_version(
    connection,
    active_test_shift,
):
    card_id = _insert_weightable_card(
        connection,
        order_number="PW-CORRUPT",
        corrupt_net=True,
    )
    before = _stored_pallet_state(connection, card_id)

    outcome = db.update_terminal_pallet_weight(card_id, 1, 1, "12.5")

    assert not outcome.result.ok
    assert outcome.issues == (
        db.PalletWeightIssue(
            1,
            "pallet_weight",
            "Roll entry 0 has invalid net_weight.",
        ),
    )
    assert _stored_pallet_state(connection, card_id) == before


def test_unexpected_pallet_summary_error_remains_visible_and_rolls_back(
    connection,
    active_test_shift,
    monkeypatch,
):
    card_id = _insert_weightable_card(
        connection,
        order_number="PW-PROGRAMMING-ERROR",
    )
    before = _stored_pallet_state(connection, card_id)

    def fail_unexpectedly(*args, **kwargs):
        raise RuntimeError("unexpected summary bug")

    monkeypatch.setattr(db, "load_card_pallet_summary", fail_unexpectedly)

    with pytest.raises(RuntimeError, match="unexpected summary bug"):
        db.update_terminal_pallet_weight(card_id, 1, 1, "12.5")
    assert _stored_pallet_state(connection, card_id) == before


def test_overwrite_import_preserves_pallet_weight_and_roll_production_state(
    connection,
    active_test_shift,
):
    imported = import_cards_from_csv(
        "pw-overwrite.csv",
        _csv_bytes(_extrusion_row("PW-OVERWRITE")),
        overwrite_existing=False,
    )
    assert imported.rows_imported == 1
    card_id = int(
        connection.execute(
            "SELECT id FROM cards WHERE order_number = 'PW-OVERWRITE'"
        ).fetchone()["id"]
    )
    imported_version = int(db.fetch_admin_card_detail(card_id)["version"])
    assert db.release_card(card_id, 1, 1, loaded_version=imported_version).ok
    connection.execute(
        """
        INSERT INTO roll_entries (
            card_id, order_number, roll_number, gross_weight, tare_weight,
            net_weight, pallet_number
        )
        VALUES (?, 'PW-OVERWRITE', 1, '20.00', '1.00', '19.00', 1)
        """,
        (card_id,),
    )
    connection.commit()
    version_before_weight = int(
        connection.execute(
            "SELECT version FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()["version"]
    )
    saved = db.update_terminal_pallet_weight(
        card_id,
        1,
        version_before_weight,
        "12.5",
    )
    assert saved.result.ok
    assert saved.card_version is not None

    overwritten = import_cards_from_csv(
        "pw-overwrite.csv",
        _csv_bytes(_extrusion_row("PW-OVERWRITE", customer="Updated Customer")),
        overwrite_existing=True,
    )
    card = connection.execute(
        "SELECT status, version FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()
    roll = connection.execute(
        """
        SELECT roll_number, gross_weight, tare_weight, net_weight, pallet_number
        FROM roll_entries
        WHERE card_id = ?
        """,
        (card_id,),
    ).fetchone()

    assert overwritten.updated == 1
    assert tuple(card) == (STATUS_PENDING, saved.card_version + 1)
    assert tuple(roll) == (1, 20, 1, 19, 1)
    assert db.fetch_card_pallet_weights(connection, card_id) == {1: 1250}
