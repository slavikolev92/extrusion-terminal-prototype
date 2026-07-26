from __future__ import annotations

import csv
import io

import pytest

from app import db
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


REWINDING_COUNT_ERROR = (
    "Броят за пренавиване трябва да бъде цяло число от 1 до 999."
)


def csv_bytes(*rows: dict[str, str]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue().encode("utf-8")


def extrusion_row(order_number: str, **overrides: str) -> dict[str, str]:
    row = {
        "order_number": order_number,
        "customer": "Rewinding Customer",
        "product_type": "PE film",
        "ordered_gross_kg": "500",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_sequence": "1",
        "raw_material_a": "LDPE; A | 100%",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def import_ready_card(order_number: str) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number)),
        overwrite_existing=False,
    )
    assert result.rows_imported == 1
    with db.connect() as connection:
        return int(
            connection.execute(
                "SELECT id FROM cards WHERE order_number = ?", (order_number,)
            ).fetchone()["id"]
        )


def release_ready_card(order_number: str) -> int:
    card_id = import_ready_card(order_number)
    version = int(db.fetch_admin_card_detail(card_id)["version"])
    assert db.release_card(card_id, 1, 1, version).ok
    return card_id


def set_card_status(card_id: int, status: str) -> None:
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE cards
            SET status = ?,
                finished_at = CASE WHEN ? = ? THEN CURRENT_TIMESTAMP ELSE finished_at END
            WHERE id = ?
            """,
            (status, status, STATUS_AWAITING_REWINDING, card_id),
        )


def card_state(card_id: int) -> dict[str, object]:
    with db.connect() as connection:
        row = connection.execute(
            """
            SELECT status, rewinding_roll_count, version, updated_at
            FROM cards
            WHERE id = ?
            """,
            (card_id,),
        ).fetchone()
        assert row is not None
        return dict(row)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", None),
        ("   ", None),
        ("0", None),
        ("000", None),
        ("1", 1),
        ("002", 2),
        ("999", 999),
    ],
)
def test_parse_rewinding_roll_count_accepts_supported_values(raw, expected):
    assert db.parse_rewinding_roll_count(raw) == (expected, None)


@pytest.mark.parametrize(
    "raw",
    ["-1", "1.5", "1,5", "1 5", "abc", "1000", "١"],
)
def test_parse_rewinding_roll_count_rejects_invalid_values(raw):
    assert db.parse_rewinding_roll_count(raw) == (None, REWINDING_COUNT_ERROR)


@pytest.mark.parametrize(
    "status",
    [STATUS_RUNNING, STATUS_PAUSED, STATUS_AWAITING_REWINDING],
)
def test_update_rewinding_roll_count_accepts_extrusion_and_waiting_cards(
    connection, status
):
    card_id = release_ready_card(f"610{len(status)}")
    set_card_status(card_id, status)
    before = card_state(card_id)

    result = db.update_rewinding_roll_count(
        card_id, int(before["version"]), 12
    )

    after = card_state(card_id)
    assert result.ok
    assert after["status"] == status
    assert after["rewinding_roll_count"] == 12
    assert after["version"] == int(before["version"]) + 1


def test_update_rewinding_roll_count_clears_waiting_marker_without_changing_status(
    connection,
):
    card_id = release_ready_card("61101")
    set_card_status(card_id, STATUS_AWAITING_REWINDING)
    before = card_state(card_id)
    assert db.update_rewinding_roll_count(card_id, int(before["version"]), 7).ok
    marked = card_state(card_id)

    result = db.update_rewinding_roll_count(card_id, int(marked["version"]), None)

    cleared = card_state(card_id)
    assert result.ok
    assert cleared["status"] == STATUS_AWAITING_REWINDING
    assert cleared["rewinding_roll_count"] is None
    assert cleared["version"] == int(marked["version"]) + 1


@pytest.mark.parametrize(
    "status",
    [STATUS_PENDING, STATUS_COMPLETED, STATUS_ARCHIVED, STATUS_CANCELLED],
)
def test_update_rewinding_roll_count_rejects_cards_outside_allowed_statuses(
    connection, status
):
    card_id = release_ready_card(f"612{len(status)}")
    set_card_status(card_id, status)
    before = card_state(card_id)

    result = db.update_rewinding_roll_count(card_id, int(before["version"]), 4)

    assert not result.ok
    assert card_state(card_id) == before


def test_update_rewinding_roll_count_requires_an_active_shift_for_terminal_writes(
    connection, start_test_shift
):
    card_id = release_ready_card("61301")
    set_card_status(card_id, STATUS_AWAITING_REWINDING)
    before = card_state(card_id)

    blocked = db.update_rewinding_roll_count(
        card_id, int(before["version"]), 8, require_active_shift=True
    )
    start_test_shift()
    allowed = db.update_rewinding_roll_count(
        card_id, int(before["version"]), 8, require_active_shift=True
    )

    assert not blocked.ok
    assert blocked.messages == (db.NO_ACTIVE_SHIFT_MESSAGE,)
    assert allowed.ok
    assert card_state(card_id)["rewinding_roll_count"] == 8


def test_update_rewinding_roll_count_updates_timestamp_and_rejects_stale_write(
    connection,
):
    card_id = release_ready_card("61401")
    set_card_status(card_id, STATUS_AWAITING_REWINDING)
    with db.connect() as setup_connection:
        setup_connection.execute(
            "UPDATE cards SET updated_at = '2000-01-01 00:00:00' WHERE id = ?",
            (card_id,),
        )
    before = card_state(card_id)

    assert db.update_rewinding_roll_count(card_id, int(before["version"]), 9).ok
    saved = card_state(card_id)
    stale = db.update_rewinding_roll_count(card_id, int(before["version"]), 10)

    assert saved["updated_at"] != before["updated_at"]
    assert not stale.ok
    assert stale.messages == (db.STALE_CARD_MESSAGE,)
    assert card_state(card_id) == saved


def test_rewinding_marker_is_exposed_in_terminal_and_admin_card_mappings(connection):
    card_id = release_ready_card("61501")
    set_card_status(card_id, STATUS_RUNNING)
    version = int(card_state(card_id)["version"])
    assert db.update_rewinding_roll_count(card_id, version, 15).ok

    terminal_card = db.fetch_terminal_card_detail(card_id)
    admin_card = db.fetch_admin_card_detail(card_id)
    admin_row = next(card for card in db.fetch_admin_cards() if card["id"] == card_id)
    terminal_row = next(
        card
        for card in db.fetch_cards_by_status((STATUS_RUNNING,))
        if card["id"] == card_id
    )
    with db.connect() as action_connection:
        action_card = db.fetch_admin_production_action_card(
            action_connection, card_id
        )

    assert terminal_card is not None
    assert terminal_card["rewinding_roll_count"] == 15
    assert admin_card is not None
    assert admin_card["rewinding_roll_count"] == 15
    assert admin_row["rewinding_roll_count"] == 15
    assert terminal_row["rewinding_roll_count"] == 15
    assert action_card is not None
    assert action_card["rewinding_roll_count"] == 15


def test_reimport_preserves_rewinding_marker(connection):
    card_id = release_ready_card("61601")
    set_card_status(card_id, STATUS_AWAITING_REWINDING)
    version = int(card_state(card_id)["version"])
    assert db.update_rewinding_roll_count(card_id, version, 21).ok

    result = import_cards_from_csv(
        "replacement.csv",
        csv_bytes(extrusion_row("61601", customer="Replacement Customer")),
        overwrite_existing=True,
    )

    assert result.rows_imported == 1
    detail = db.fetch_admin_card_detail(card_id)
    assert detail is not None
    assert detail["customer"] == "Replacement Customer"
    assert detail["rewinding_roll_count"] == 21
