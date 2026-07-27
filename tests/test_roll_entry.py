from __future__ import annotations

import csv
import io
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app import db
from app.constants import (
    STATUS_ARCHIVED,
    STATUS_AWAITING_REWINDING,
    STATUS_COMPLETED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_RUNNING,
)
from app.importer import IMPORT_FIELDS, import_cards_from_csv


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
        "customer": "Roll Customer",
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


def import_and_release_card(
    order_number: str,
    machine_id: int = 1,
    machine_sequence: int = 1,
) -> int:
    result = import_cards_from_csv(
        f"{order_number}.csv",
        csv_bytes(extrusion_row(order_number)),
        overwrite_existing=False,
    )
    assert result.rows_imported == 1
    with db.connect() as connection:
        card_id = int(
            connection.execute(
                "SELECT id FROM cards WHERE order_number = ?",
                (order_number,),
            ).fetchone()["id"]
        )
    assert db.release_card(
        card_id,
        machine_id,
        machine_sequence,
    ).ok
    return card_id


def start_card(card_id: int) -> None:
    assert db.start_production_timing(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
    ).ok


def roll_values(card_id: int) -> list[tuple[float | None, float | None, float | None]]:
    return [
        (roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
        for roll in db.fetch_terminal_card_detail(card_id)["roll_entries"]
    ]


def insert_shift_occurrence(
    connection,
    shift_number: int,
    started_at: str,
    ended_at: str | None,
) -> int:
    occurrence_id = int(
        connection.execute(
            """
            INSERT INTO shift_occurrences (shift_number, started_at, ended_at)
            VALUES (?, ?, ?)
            RETURNING id
            """,
            (shift_number, started_at, ended_at),
        ).fetchone()["id"]
    )
    connection.commit()
    return occurrence_id


def test_running_roll_requires_active_shift_and_links_occurrence(
    connection,
    start_test_shift,
):
    card_id = import_and_release_card("25600")
    start_card(card_id)
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    blocked = db.add_roll_gross_weight(
        card_id,
        loaded_version,
        "25.00",
        tare_weight="1.00",
    )

    assert not blocked.ok
    assert blocked.messages == ("Отворете смяна, преди да добавите ролка.",)
    blocked_card = db.fetch_terminal_card_detail(card_id)
    assert blocked_card["version"] == loaded_version
    assert blocked_card["tare_weight"] is None
    assert blocked_card["roll_entries"] == []

    occurrence = start_test_shift("1")
    added = db.add_roll_gross_weight(
        card_id,
        loaded_version,
        "25.00",
        tare_weight="1.00",
    )
    roll = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]

    assert added.ok
    assert roll["shift_occurrence_id"] == occurrence["id"]


def test_active_shift_number_correction_does_not_rewrite_roll_link(
    connection,
    start_test_shift,
):
    occurrence = start_test_shift("1")
    card_id = import_and_release_card("25601")
    start_card(card_id)

    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
        tare_weight="1.00",
    ).ok
    assert db.update_active_shift_number(
        int(occurrence["id"]),
        int(occurrence["version"]),
        "3",
    ).ok

    roll = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]
    assert roll["shift_occurrence_id"] == occurrence["id"]
    assert db.fetch_active_shift()["shift_number"] == 3


def test_roll_correction_preserves_shift_occurrence(connection, start_test_shift):
    occurrence = start_test_shift("2")
    card_id = import_and_release_card("25602")
    start_card(card_id)
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
        tare_weight="1.00",
    ).ok
    card = db.fetch_terminal_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])

    corrected = db.update_roll_weight(
        card_id,
        roll_id,
        card["version"],
        "27.00",
        "1.50",
    )
    roll = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]

    assert corrected.ok
    assert roll["gross_weight"] == 27
    assert roll["shift_occurrence_id"] == occurrence["id"]


def test_completed_roll_inherits_latest_linked_occurrence_not_active_shift(connection):
    card_id = import_and_release_card("25603")
    older_id = insert_shift_occurrence(
        connection,
        1,
        "2026-07-25 06:00:00",
        "2026-07-25 14:00:00",
    )
    latest_id = insert_shift_occurrence(
        connection,
        2,
        "2026-07-25 14:00:00",
        "2026-07-25 22:00:00",
    )
    active_id = insert_shift_occurrence(connection, 3, "2026-07-25 22:00:00", None)
    connection.execute(
        "UPDATE cards SET status = ?, tare_weight = '1.00' WHERE id = ?",
        (STATUS_COMPLETED, card_id),
    )
    connection.executemany(
        """
        INSERT INTO roll_entries (
            card_id, order_number, roll_number, gross_weight, tare_weight,
            net_weight, shift_occurrence_id
        )
        VALUES (?, '25603', ?, ?, '1.00', ?, ?)
        """,
        (
            (card_id, 1, "20.00", "19.00", latest_id),
            (card_id, 2, "21.00", "20.00", older_id),
        ),
    )
    connection.commit()

    result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "22.00",
    )
    rolls = db.fetch_terminal_card_detail(card_id)["roll_entries"]

    assert result.ok
    assert rolls[-1]["shift_occurrence_id"] == latest_id
    assert rolls[-1]["shift_occurrence_id"] != active_id


def test_late_roll_without_known_order_shift_remains_unattributed(connection):
    card_id = import_and_release_card("25604")
    active_id = insert_shift_occurrence(connection, 4, "2026-07-25 22:00:00", None)
    connection.execute(
        "UPDATE cards SET status = ?, tare_weight = '1.00' WHERE id = ?",
        (STATUS_COMPLETED, card_id),
    )
    connection.commit()

    result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
    )
    roll = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]

    assert result.ok
    assert roll["shift_occurrence_id"] is None
    assert db.fetch_active_shift()["id"] == active_id


@pytest.mark.parametrize(
    "status",
    [STATUS_AWAITING_REWINDING, STATUS_COMPLETED, STATUS_ARCHIVED],
)
def test_late_roll_uses_stored_final_shift_before_linked_roll_or_active_shift(
    connection,
    status,
):
    card_id = import_and_release_card(f"2561{len(status)}")
    linked_id = insert_shift_occurrence(
        connection,
        1,
        "2026-07-25 06:00:00",
        "2026-07-25 14:00:00",
    )
    final_id = insert_shift_occurrence(
        connection,
        2,
        "2026-07-25 14:00:00",
        "2026-07-25 22:00:00",
    )
    active_id = insert_shift_occurrence(connection, 3, "2026-07-25 22:00:00", None)
    connection.execute(
        """
        UPDATE cards
        SET status = ?, tare_weight = '1.00',
            final_extrusion_shift_occurrence_id = ?
        WHERE id = ?
        """,
        (status, final_id, card_id),
    )
    connection.execute(
        """
        INSERT INTO roll_entries (
            card_id, order_number, roll_number, gross_weight, tare_weight,
            net_weight, shift_occurrence_id
        )
        VALUES (?, ?, 1, '20.00', '1.00', '19.00', ?)
        """,
        (card_id, f"2561{len(status)}", linked_id),
    )
    connection.commit()

    result = db.add_roll_gross_weight(
        card_id,
        db.fetch_admin_card_detail(card_id)["version"],
        "22.00",
        require_active_shift=True,
    )
    rolls = db.fetch_admin_card_detail(card_id)["roll_entries"]

    assert result.ok
    assert rolls[-1]["shift_occurrence_id"] == final_id
    assert rolls[-1]["shift_occurrence_id"] not in (linked_id, active_id)


def test_waiting_roll_add_and_row_correction_are_atomic_snapshots(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25620")
    connection.execute(
        """
        UPDATE cards
        SET status = ?, tare_weight = '1.25', current_pallet_number = 4,
            final_extrusion_shift_occurrence_id = ?
        WHERE id = ?
        """,
        (STATUS_AWAITING_REWINDING, active_test_shift["id"], card_id),
    )
    connection.commit()
    before = db.fetch_terminal_card_detail(card_id)

    added = db.add_roll_gross_weight(
        card_id,
        before["version"],
        "25.50",
        require_active_shift=True,
    )
    added_card = db.fetch_terminal_card_detail(card_id)
    roll = added_card["roll_entries"][0]

    assert added.ok
    assert added_card["version"] == before["version"] + 1
    assert (
        roll["roll_number"],
        roll["gross_weight"],
        roll["tare_weight"],
        roll["pallet_number"],
        roll["net_weight"],
        roll["shift_occurrence_id"],
    ) == (1, 25.5, 1.25, 4, 24.25, active_test_shift["id"])

    rejected = db.update_roll_weight(
        card_id,
        roll["id"],
        added_card["version"],
        "30.00",
        "2.00",
        "1000",
        require_active_shift=True,
    )
    unchanged = db.fetch_terminal_card_detail(card_id)
    assert not rejected.ok
    assert unchanged == added_card

    corrected = db.update_roll_weight(
        card_id,
        roll["id"],
        added_card["version"],
        "30.00",
        "2.00",
        "9",
        require_active_shift=True,
    )
    corrected_card = db.fetch_terminal_card_detail(card_id)
    assert corrected.ok
    assert corrected_card["version"] == added_card["version"] + 1
    assert (
        corrected_card["roll_entries"][0]["gross_weight"],
        corrected_card["roll_entries"][0]["tare_weight"],
        corrected_card["roll_entries"][0]["pallet_number"],
        corrected_card["roll_entries"][0]["net_weight"],
    ) == (30, 2, 9, 28)
    assert corrected_card["tare_weight"] == 1.25
    assert corrected_card["current_pallet_number"] == 4

    preserved_pallet = db.update_roll_weight(
        card_id,
        roll["id"],
        corrected_card["version"],
        "31.00",
        "2.00",
        require_active_shift=True,
    )
    preserved_card = db.fetch_terminal_card_detail(card_id)
    assert preserved_pallet.ok
    assert preserved_card["roll_entries"][0]["pallet_number"] == 9


def test_waiting_roll_terminal_write_requires_active_shift_before_historical_attribution(
    connection,
):
    final_id = insert_shift_occurrence(
        connection,
        2,
        "2026-07-25 14:00:00",
        "2026-07-25 22:00:00",
    )
    card_id = import_and_release_card("25622")
    connection.execute(
        """
        UPDATE cards
        SET status = ?, tare_weight = '1.00',
            final_extrusion_shift_occurrence_id = ?
        WHERE id = ?
        """,
        (STATUS_AWAITING_REWINDING, final_id, card_id),
    )
    connection.commit()
    before = db.fetch_terminal_card_detail(card_id)

    result = db.add_roll_gross_weight(
        card_id,
        before["version"],
        "20.00",
        require_active_shift=True,
    )
    after = db.fetch_terminal_card_detail(card_id)

    assert not result.ok
    assert result.messages == (db.NO_ACTIVE_SHIFT_MESSAGE,)
    assert after == before


def test_waiting_defaults_do_not_rewrite_roll_snapshots_and_final_roll_can_be_deleted(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25621")
    connection.execute(
        """
        UPDATE cards
        SET status = ?, tare_weight = '1.00', current_pallet_number = 2,
            final_extrusion_shift_occurrence_id = ?
        WHERE id = ?
        """,
        (STATUS_AWAITING_REWINDING, active_test_shift["id"], card_id),
    )
    connection.commit()
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "20.00",
        require_active_shift=True,
    ).ok
    with_roll = db.fetch_terminal_card_detail(card_id)

    assert db.update_tare_weight(
        card_id,
        with_roll["version"],
        "3.00",
        require_active_shift=True,
    ).ok
    after_tare = db.fetch_terminal_card_detail(card_id)
    assert db.update_current_pallet_number(
        card_id,
        after_tare["version"],
        "7",
        require_active_shift=True,
    ).ok
    after_defaults = db.fetch_terminal_card_detail(card_id)
    roll = after_defaults["roll_entries"][0]

    assert after_defaults["tare_weight"] == 3
    assert after_defaults["current_pallet_number"] == 7
    assert (roll["tare_weight"], roll["pallet_number"], roll["net_weight"]) == (1, 2, 19)

    deleted = db.delete_roll_entry(
        card_id,
        roll["id"],
        after_defaults["version"],
        require_active_shift=True,
    )
    final_card = db.fetch_terminal_card_detail(card_id)
    assert deleted.ok
    assert final_card["status"] == STATUS_AWAITING_REWINDING
    assert final_card["roll_entries"] == []


def test_waiting_roll_correction_cannot_overwrite_a_concurrent_committed_version(
    connection,
    active_test_shift,
    monkeypatch,
):
    card_id = import_and_release_card("25623")
    connection.execute(
        """
        UPDATE cards
        SET status = ?, tare_weight = '1.00',
            final_extrusion_shift_occurrence_id = ?
        WHERE id = ?
        """,
        (STATUS_AWAITING_REWINDING, active_test_shift["id"], card_id),
    )
    connection.commit()
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "20.00",
    ).ok
    loaded = db.fetch_terminal_card_detail(card_id)
    roll_id = int(loaded["roll_entries"][0]["id"])

    writer = db.connect()
    writer.execute("BEGIN IMMEDIATE")
    writer.execute(
        """
        UPDATE roll_entries
        SET gross_weight = '27.00', tare_weight = '2.00', net_weight = '25.00'
        WHERE id = ?
        """,
        (roll_id,),
    )
    writer.execute(
        "UPDATE cards SET version = version + 1 WHERE id = ?",
        (card_id,),
    )

    stale_read_reached = Event()
    release_stale_reader = Event()
    original_validate = db.validate_loaded_card_version

    def synchronize_stale_read(card, loaded_version):
        result = original_validate(card, loaded_version)
        if result.ok:
            stale_read_reached.set()
            assert release_stale_reader.wait(timeout=2)
        return result

    monkeypatch.setattr(db, "validate_loaded_card_version", synchronize_stale_read)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            db.update_roll_weight,
            card_id,
            roll_id,
            loaded["version"],
            "30.00",
            "3.00",
            "8",
        )
        stale_read_reached.wait(timeout=0.2)
        writer.commit()
        writer.close()
        release_stale_reader.set()
        result = future.result(timeout=2)

    final_card = db.fetch_terminal_card_detail(card_id)
    final_roll = final_card["roll_entries"][0]
    assert not result.ok
    assert result.messages == (db.STALE_CARD_MESSAGE,)
    assert final_card["version"] == loaded["version"] + 1
    assert (
        final_roll["gross_weight"],
        final_roll["tare_weight"],
        final_roll["pallet_number"],
        final_roll["net_weight"],
    ) == (27, 2, None, 25)


def test_tare_update_persists_and_checks_loaded_version(connection):
    card_id = import_and_release_card("25500")
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.update_tare_weight(card_id, loaded_version, "1.25")
    stale_result = db.update_tare_weight(card_id, loaded_version, "1.50")
    card = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert card["tare_weight"] == 1.25
    assert card["version"] == loaded_version + 1
    assert not stale_result.ok
    assert stale_result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )


def test_roll_defaults_update_saves_tare_and_pallet_with_one_version_increment(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25569")
    start_card(card_id)
    before = db.fetch_terminal_card_detail(card_id)

    result = db.update_roll_defaults(
        card_id,
        before["version"],
        tare_weight=" 2.50 ",
        pallet_number=" 9 ",
        require_active_shift=True,
    )
    after = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert after["tare_weight"] == 2.5
    assert after["current_pallet_number"] == 9
    assert after["version"] == before["version"] + 1
    assert after["roll_entries"] == []


def test_roll_defaults_update_rejects_invalid_pallet_without_saving_tare(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25570")
    start_card(card_id)
    assert db.update_roll_defaults(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        tare_weight="1.25",
        pallet_number="7",
        require_active_shift=True,
    ).ok
    before = db.fetch_terminal_card_detail(card_id)

    result = db.update_roll_defaults(
        card_id,
        before["version"],
        tare_weight="2.50",
        pallet_number="1000",
        require_active_shift=True,
    )
    after = db.fetch_terminal_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Палетът трябва да бъде цяло число от 1 до 999.",)
    assert after["tare_weight"] == 1.25
    assert after["current_pallet_number"] == 7
    assert after["version"] == before["version"]


def test_roll_defaults_update_blocks_stale_combined_write_without_partial_change(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25571")
    start_card(card_id)
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]
    assert db.update_tare_weight(card_id, loaded_version, "1.25").ok
    current = db.fetch_terminal_card_detail(card_id)

    result = db.update_roll_defaults(
        card_id,
        loaded_version,
        tare_weight="2.50",
        pallet_number="9",
        require_active_shift=True,
    )
    after = db.fetch_terminal_card_detail(card_id)

    assert not result.ok
    assert result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert after["tare_weight"] == current["tare_weight"] == 1.25
    assert after["current_pallet_number"] is None
    assert after["version"] == current["version"]


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("", None),
        ("   ", None),
        ("1", 1),
        (" 1 ", 1),
        ("999", 999),
        ("001", 1),
    ),
)
def test_parse_pallet_number_accepts_blank_or_ascii_numbers_in_range(value, expected):
    assert db.parse_pallet_number(value) == (expected, None)


@pytest.mark.parametrize(
    "value",
    (
        "0",
        "-1",
        "1000",
        "1.0",
        "1,0",
        "+1",
        "15+1",
        "1e2",
        "1 2",
        pytest.param("9" * 5000, id="5000-digits"),
        "A",
        "1A",
        "١",
    ),
)
def test_parse_pallet_number_rejects_invalid_values_with_one_message(value):
    assert db.parse_pallet_number(value) == (
        None,
        "Палетът трябва да бъде цяло число от 1 до 999.",
    )


def test_current_pallet_save_and_clear_trim_values_without_creating_or_rewriting_rolls(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25548")
    start_card(card_id)
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
        tare_weight="1.00",
    ).ok
    before = db.fetch_terminal_card_detail(card_id)

    saved = db.update_current_pallet_number(
        card_id,
        before["version"],
        " 001 ",
        require_active_shift=True,
    )
    saved_card = db.fetch_terminal_card_detail(card_id)
    cleared = db.update_current_pallet_number(
        card_id,
        saved_card["version"],
        "   ",
        require_active_shift=True,
    )
    stored_types = connection.execute(
        "SELECT current_pallet_number, typeof(current_pallet_number) AS value_type FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()
    rolls = db.fetch_terminal_card_detail(card_id)["roll_entries"]

    assert saved.ok
    assert saved.messages == ("Палетът е записан.",)
    assert saved_card["current_pallet_number"] == 1
    assert saved_card["version"] == before["version"] + 1
    assert cleared.ok
    assert cleared.messages == ("Палетът е изчистен.",)
    assert stored_types["current_pallet_number"] is None
    assert stored_types["value_type"] == "null"
    assert len(rolls) == 1
    assert rolls[0]["pallet_number"] is None


def test_current_pallet_invalid_or_stale_write_preserves_card_and_rolls(connection, active_test_shift):
    card_id = import_and_release_card("25549")
    start_card(card_id)
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
        tare_weight="1.00",
    ).ok
    before = db.fetch_terminal_card_detail(card_id)

    invalid = db.update_current_pallet_number(
        card_id,
        before["version"],
        "1000",
        require_active_shift=True,
    )
    assert db.update_current_pallet_number(
        card_id,
        before["version"],
        "1",
        require_active_shift=True,
    ).ok
    stale = db.update_current_pallet_number(
        card_id,
        before["version"],
        "2",
        require_active_shift=True,
    )
    after = db.fetch_terminal_card_detail(card_id)

    assert not invalid.ok
    assert invalid.messages == ("Палетът трябва да бъде цяло число от 1 до 999.",)
    assert not stale.ok
    assert stale.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert after["current_pallet_number"] == 1
    assert after["version"] == before["version"] + 1
    assert [(roll["roll_number"], roll["pallet_number"]) for roll in after["roll_entries"]] == [(1, None)]


def test_current_pallet_respects_terminal_status_and_active_shift_gates(connection, start_test_shift):
    card_id = import_and_release_card("25550")
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    blocked_shift = db.update_current_pallet_number(
        card_id,
        loaded_version,
        "1",
        require_active_shift=True,
    )
    start_test_shift("1")
    assert db.update_current_pallet_number(
        card_id,
        loaded_version,
        "1",
        require_active_shift=True,
    ).ok
    changed = db.fetch_terminal_card_detail(card_id)
    connection.execute("UPDATE cards SET status = 'imported' WHERE id = ?", (card_id,))
    connection.commit()
    blocked_status = db.update_current_pallet_number(
        card_id,
        changed["version"],
        "2",
        require_active_shift=True,
    )

    assert not blocked_shift.ok
    assert blocked_shift.messages == ("Отворете смяна, преди да продължите.",)
    assert not blocked_status.ok
    assert blocked_status.messages == ("Картата не е намерена.",)
    stored = connection.execute(
        "SELECT current_pallet_number, version FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    assert dict(stored) == {"current_pallet_number": 1, "version": changed["version"]}


def test_add_roll_while_running_assigns_roll_numbers(connection, active_test_shift):
    card_id = import_and_release_card("25501")
    start_card(card_id)
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.00",
    ).ok

    first_result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.50",
    )
    second_result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "30",
    )
    rolls = connection.execute(
        """
        SELECT roll_number, gross_weight
        FROM roll_entries
        WHERE card_id = ?
        ORDER BY roll_number
        """,
        (card_id,),
    ).fetchall()

    assert first_result.ok
    assert first_result.messages == ("Ролка 1 е записана.",)
    assert second_result.ok
    assert second_result.messages == ("Ролка 2 е записана.",)
    assert [(roll["roll_number"], roll["gross_weight"]) for roll in rolls] == [
        (1, 25.50),
        (2, 30),
    ]


def test_add_roll_requires_default_tare(connection, active_test_shift):
    card_id = import_and_release_card("25546")
    start_card(card_id)
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.add_roll_gross_weight(card_id, loaded_version, "25.00")
    card = db.fetch_terminal_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Въведете шпула преди да добавите ролка.",)
    assert card["roll_entries"] == []
    assert card["version"] == loaded_version


def test_add_roll_allows_submitted_tare_without_existing_default(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25547")
    start_card(card_id)

    result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
        tare_weight="1.50",
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert card["tare_weight"] == 1.5
    assert [
        (roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
        for roll in card["roll_entries"]
    ] == [(25, 1.5, 23.5)]


def test_add_roll_is_blocked_when_card_is_not_running(connection):
    pending_card_id = import_and_release_card("25502", machine_id=2, machine_sequence=1)
    paused_card_id = import_and_release_card("25503", machine_id=3, machine_sequence=1)
    start_card(paused_card_id)
    assert db.pause_production_timing(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
    ).ok

    pending_result = db.add_roll_gross_weight(
        pending_card_id,
        db.fetch_terminal_card_detail(pending_card_id)["version"],
        "25",
    )
    paused_result = db.add_roll_gross_weight(
        paused_card_id,
        db.fetch_terminal_card_detail(paused_card_id)["version"],
        "25",
    )

    assert db.fetch_terminal_card_detail(pending_card_id)["status"] == STATUS_PENDING
    assert db.fetch_terminal_card_detail(paused_card_id)["status"] == STATUS_PAUSED
    assert not pending_result.ok
    assert pending_result.messages == (
        "Теглата на ролките могат да се променят само когато картата е в изработване, произведена или завършена.",
    )
    assert not paused_result.ok
    assert paused_result.messages == (
        "Теглата на ролките могат да се променят само когато картата е в изработване, произведена или завършена.",
    )


def test_weight_inputs_reject_more_than_two_decimal_places(connection):
    card_id = import_and_release_card("25507")
    start_card(card_id)

    tare_result = db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.234",
    )
    gross_result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.555",
    )
    roll_count = connection.execute(
        "SELECT COUNT(*) FROM roll_entries WHERE card_id = ?",
        (card_id,),
    ).fetchone()[0]

    assert not tare_result.ok
    assert tare_result.messages == ("Шпула поддържа най-много два знака след десетичната запетая.",)
    assert not gross_result.ok
    assert gross_result.messages == ("Бруто тегло поддържа най-много два знака след десетичната запетая.",)
    assert roll_count == 0


def test_gross_and_net_totals_calculate_with_tare(connection, active_test_shift):
    card_id = import_and_release_card("25504")
    start_card(card_id)
    assert db.fetch_terminal_card_detail(card_id)["status"] == STATUS_RUNNING
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.25",
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.50",
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "30.00",
    ).ok

    card = db.fetch_terminal_card_detail(card_id)
    rolls = card["roll_entries"]

    assert card["roll_count"] == 2
    assert card["total_gross_weight"] == "55.50"
    assert card["total_net_weight"] == "53.00"
    assert rolls[0]["net_weight"] == 24.25
    assert rolls[1]["net_weight"] == 28.75


def test_total_net_is_unknown_when_gross_roll_lacks_tare(connection):
    card_id = import_and_release_card("25543")
    start_card(card_id)
    connection.execute(
        """
        INSERT INTO roll_entries (
            card_id, order_number, roll_number, gross_weight, tare_weight, net_weight
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (card_id, "25543", 1, "25.00", None, "24.00"),
    )
    connection.commit()

    card = db.fetch_terminal_card_detail(card_id)

    assert card["roll_count"] == 1
    assert card["total_gross_weight"] == "25.00"
    assert card["total_net_weight"] is None


def test_total_gross_is_unknown_when_gross_roll_is_invalid(connection):
    card_id = import_and_release_card("25544")
    start_card(card_id)
    connection.executemany(
        """
        INSERT INTO roll_entries (
            card_id, order_number, roll_number, gross_weight, tare_weight, net_weight
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (card_id, "25544", 1, "bad", "1.00", "1.00"),
            (card_id, "25544", 2, "10.00", "1.00", "9.00"),
        ),
    )
    connection.commit()

    card = db.fetch_terminal_card_detail(card_id)

    assert card["roll_count"] == 2
    assert card["total_gross_weight"] is None
    assert card["total_net_weight"] is None


def test_total_net_is_unknown_when_gross_roll_lacks_net(connection):
    card_id = import_and_release_card("25545")
    start_card(card_id)
    connection.execute(
        """
        INSERT INTO roll_entries (
            card_id, order_number, roll_number, gross_weight, tare_weight, net_weight
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (card_id, "25545", 1, "25.00", "1.00", None),
    )
    connection.commit()

    card = db.fetch_terminal_card_detail(card_id)

    assert card["roll_count"] == 1
    assert card["total_gross_weight"] == "25.00"
    assert card["total_net_weight"] is None


def test_total_net_is_unknown_when_stored_net_does_not_match_gross_minus_tare(connection):
    card_id = import_and_release_card("25546")
    start_card(card_id)
    connection.execute(
        """
        INSERT INTO roll_entries (
            card_id, order_number, roll_number, gross_weight, tare_weight, net_weight
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (card_id, "25546", 1, "25.00", "1.00", "20.00"),
    )
    connection.commit()

    card = db.fetch_terminal_card_detail(card_id)

    assert card["roll_count"] == 1
    assert card["total_gross_weight"] == "25.00"
    assert card["total_net_weight"] is None


def test_new_roll_copies_current_default_tare_without_mutating_existing_rolls(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25540")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.50").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "60.00").ok

    card = db.fetch_terminal_card_detail(card_id)

    assert card["tare_weight"] == 2.5
    assert [(roll["gross_weight"], roll["tare_weight"], roll["net_weight"]) for roll in card["roll_entries"]] == [
        (50, 2, 48),
        (60, 2.5, 57.5),
    ]
    assert card["total_gross_weight"] == "110.00"
    assert card["total_net_weight"] == "105.50"


def test_new_roll_omitting_pallet_copies_stored_current_pallet(connection, active_test_shift):
    card_id = import_and_release_card("25551")
    start_card(card_id)
    assert db.update_current_pallet_number(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1",
        require_active_shift=True,
    ).ok

    result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
        tare_weight="1.50",
        require_active_shift=True,
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert card["current_pallet_number"] == 1
    assert [
        (roll["pallet_number"], roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
        for roll in card["roll_entries"]
    ] == [(1, 25, 1.5, 23.5)]
    assert card["roll_entries"][0]["shift_occurrence_id"] is not None


def test_new_roll_submitted_pallet_updates_current_and_snapshots_once(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25552")
    start_card(card_id)
    before = db.fetch_terminal_card_detail(card_id)

    result = db.add_roll_gross_weight(
        card_id,
        before["version"],
        "25.00",
        tare_weight="1.50",
        pallet_number=" 2 ",
        require_active_shift=True,
    )
    card = db.fetch_terminal_card_detail(card_id)
    row = connection.execute(
        "SELECT pallet_number, typeof(pallet_number) AS value_type FROM roll_entries WHERE card_id = ?",
        (card_id,),
    ).fetchone()

    assert result.ok
    assert card["current_pallet_number"] == 2
    assert card["version"] == before["version"] + 1
    assert card["roll_entries"][0]["pallet_number"] == 2
    assert dict(row) == {"pallet_number": 2, "value_type": "integer"}


def test_new_roll_with_blank_submitted_pallet_clears_current_and_snapshots_blank(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25553")
    start_card(card_id)
    assert db.update_current_pallet_number(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1",
        require_active_shift=True,
    ).ok

    result = db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
        tare_weight="1.50",
        pallet_number="",
        require_active_shift=True,
    )
    card = db.fetch_terminal_card_detail(card_id)
    row = connection.execute(
        "SELECT pallet_number, typeof(pallet_number) AS value_type FROM roll_entries WHERE card_id = ?",
        (card_id,),
    ).fetchone()

    assert result.ok
    assert card["current_pallet_number"] is None
    assert card["roll_entries"][0]["pallet_number"] is None
    assert dict(row) == {"pallet_number": None, "value_type": "null"}


def test_new_roll_pallet_changes_do_not_rewrite_prior_roll_snapshot(connection, active_test_shift):
    card_id = import_and_release_card("25554")
    start_card(card_id)
    first_version = db.fetch_terminal_card_detail(card_id)["version"]
    assert db.add_roll_gross_weight(
        card_id,
        first_version,
        "25.00",
        tare_weight="1.50",
        pallet_number="1",
        require_active_shift=True,
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "30.00",
        pallet_number="2",
        require_active_shift=True,
    ).ok

    card = db.fetch_terminal_card_detail(card_id)

    assert card["current_pallet_number"] == 2
    assert [(roll["roll_number"], roll["pallet_number"]) for roll in card["roll_entries"]] == [
        (1, 1),
        (2, 2),
    ]


def test_invalid_or_stale_submitted_pallet_does_not_create_roll_or_change_current(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25555")
    start_card(card_id)
    assert db.update_current_pallet_number(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1",
        require_active_shift=True,
    ).ok
    before = db.fetch_terminal_card_detail(card_id)

    invalid = db.add_roll_gross_weight(
        card_id,
        before["version"],
        "25.00",
        tare_weight="1.50",
        pallet_number="1000",
        require_active_shift=True,
    )
    assert db.add_roll_gross_weight(
        card_id,
        before["version"],
        "25.00",
        tare_weight="1.50",
        pallet_number="2",
        require_active_shift=True,
    ).ok
    stale = db.add_roll_gross_weight(
        card_id,
        before["version"],
        "30.00",
        pallet_number="3",
        require_active_shift=True,
    )
    card = db.fetch_terminal_card_detail(card_id)

    assert not invalid.ok
    assert invalid.messages == ("Палетът трябва да бъде цяло число от 1 до 999.",)
    assert not stale.ok
    assert stale.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert card["current_pallet_number"] == 2
    assert card["version"] == before["version"] + 1
    assert [(roll["roll_number"], roll["pallet_number"]) for roll in card["roll_entries"]] == [(1, 2)]


def test_editing_roll_tare_recalculates_only_that_roll_and_not_default_tare(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25541")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "60.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    first_roll_id = int(card["roll_entries"][0]["id"])

    result = db.update_roll_weight(
        card_id=card_id,
        roll_id=first_roll_id,
        loaded_version=card["version"],
        gross_weight="50.00",
        tare_weight="3.00",
    )
    updated = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert updated["tare_weight"] == 2
    assert [(roll["tare_weight"], roll["net_weight"]) for roll in updated["roll_entries"]] == [
        (3, 47),
        (2, 58),
    ]
    assert updated["total_net_weight"] == "105.00"


def test_roll_tare_rejects_more_than_two_decimal_places_and_tare_above_gross(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25542")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])

    too_precise = db.update_roll_weight(card_id, roll_id, card["version"], "50.00", "1.234")
    unchanged = db.fetch_terminal_card_detail(card_id)
    too_large = db.update_roll_weight(card_id, roll_id, unchanged["version"], "50.00", "60.00")

    assert not too_precise.ok
    assert too_precise.messages == ("Шпула поддържа най-много два знака след десетичната запетая.",)
    assert not too_large.ok
    assert too_large.messages == ("Бруто теглото не може да бъде по-малко от шпулата.",)
    final_card = db.fetch_terminal_card_detail(card_id)
    assert final_card["tare_weight"] == 2
    assert [
        (roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
        for roll in final_card["roll_entries"]
    ] == [(50, 2, 48)]


def test_terminal_roll_corrections_update_multiple_rolls_in_one_version(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25560")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "60.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    first_id = int(card["roll_entries"][0]["id"])
    second_id = int(card["roll_entries"][1]["id"])

    result = db.update_terminal_roll_corrections(
        card_id,
        card["version"],
        {
            first_id: {"gross_weight": "51.00", "tare_weight": "2.50"},
            second_id: {"gross_weight": "62.00", "tare_weight": "3.00"},
        },
    )
    updated = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert result.messages == ("Ролките са записани.",)
    assert updated["version"] == card["version"] + 1
    assert roll_values(card_id) == [(51, 2.5, 48.5), (62, 3, 59)]
    assert updated["total_gross_weight"] == "113.00"
    assert updated["total_net_weight"] == "107.50"


def test_terminal_roll_corrections_only_touch_changed_roll_rows(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25565")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "60.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    first_id = int(card["roll_entries"][0]["id"])
    second_id = int(card["roll_entries"][1]["id"])
    connection.execute(
        "UPDATE roll_entries SET updated_at = '2000-01-01 00:00:00' WHERE id = ?",
        (second_id,),
    )
    connection.commit()

    result = db.update_terminal_roll_corrections(
        card_id,
        card["version"],
        {
            first_id: {"gross_weight": "51.00", "tare_weight": "2.50"},
            second_id: {"gross_weight": "60.00", "tare_weight": "2.00"},
        },
    )
    unchanged_row = connection.execute(
        "SELECT updated_at FROM roll_entries WHERE id = ?",
        (second_id,),
    ).fetchone()

    assert result.ok
    assert unchanged_row["updated_at"] == "2000-01-01 00:00:00"


def test_terminal_roll_corrections_block_stale_version_without_partial_update(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25561")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])
    assert db.update_tare_weight(card_id, card["version"], "2.25").ok

    result = db.update_terminal_roll_corrections(
        card_id,
        card["version"],
        {roll_id: {"gross_weight": "51.00", "tare_weight": "2.50"}},
    )

    assert not result.ok
    assert result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert roll_values(card_id) == [(50, 2, 48)]


def test_terminal_roll_corrections_validate_all_rows_before_saving(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25562")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "60.00").ok
    card = db.fetch_terminal_card_detail(card_id)
    first_id = int(card["roll_entries"][0]["id"])
    second_id = int(card["roll_entries"][1]["id"])

    result = db.update_terminal_roll_corrections(
        card_id,
        card["version"],
        {
            first_id: {"gross_weight": "55.00", "tare_weight": "2.00"},
            second_id: {"gross_weight": "1.00", "tare_weight": "3.00"},
        },
    )

    assert not result.ok
    assert result.messages == ("Бруто теглото не може да бъде по-малко от шпулата.",)
    assert roll_values(card_id) == [(50, 2, 48), (60, 2, 58)]


def test_terminal_roll_corrections_reject_unknown_roll_id(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25563")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    card = db.fetch_terminal_card_detail(card_id)

    result = db.update_terminal_roll_corrections(
        card_id,
        card["version"],
        {999999: {"gross_weight": "55.00", "tare_weight": "2.00"}},
    )

    assert not result.ok
    assert result.messages == ("Избрана ролка не принадлежи към тази карта.",)
    assert roll_values(card_id) == [(50, 2, 48)]


def test_terminal_roll_corrections_completed_card_keeps_final_gross_roll(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25564")
    start_card(card_id)
    assert db.update_tare_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "2.00").ok
    assert db.add_roll_gross_weight(card_id, db.fetch_terminal_card_detail(card_id)["version"], "50.00").ok
    assert db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok
    card = db.fetch_terminal_card_detail(card_id)
    roll_id = int(card["roll_entries"][0]["id"])

    result = db.update_terminal_roll_corrections(
        card_id,
        card["version"],
        {roll_id: {"gross_weight": "", "tare_weight": "2.00"}},
    )

    assert not result.ok
    assert result.messages == ("Завършените карти трябва да запазят поне едно бруто тегло на ролка.",)
    assert roll_values(card_id) == [(50, 2, 48)]


def test_terminal_roll_corrections_set_change_and_clear_pallet_without_changing_current_pallet(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25566")
    start_card(card_id)
    assert db.update_current_pallet_number(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "9",
        require_active_shift=True,
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "50.00",
        tare_weight="2.00",
        require_active_shift=True,
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "60.00",
        require_active_shift=True,
    ).ok
    card = db.fetch_terminal_card_detail(card_id)
    first_id = int(card["roll_entries"][0]["id"])
    second_id = int(card["roll_entries"][1]["id"])

    result = db.update_terminal_roll_corrections(
        card_id,
        card["version"],
        {
            first_id: {"pallet_number": " 1 ", "gross_weight": "51.00"},
            second_id: {"pallet_number": "", "tare_weight": "3.00"},
        },
        require_active_shift=True,
    )
    changed = db.fetch_terminal_card_detail(card_id)
    changed_first_id = int(changed["roll_entries"][0]["id"])

    changed_again = db.update_terminal_roll_corrections(
        card_id,
        changed["version"],
        {changed_first_id: {"pallet_number": "2"}},
        require_active_shift=True,
    )
    final_card = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert changed_again.ok
    assert changed["current_pallet_number"] == 9
    assert final_card["current_pallet_number"] == 9
    assert [(roll["pallet_number"], roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
            for roll in final_card["roll_entries"]] == [
        (2, 51, 2, 49),
        (None, 60, 3, 57),
    ]


def test_terminal_roll_corrections_invalid_pallet_rolls_back_all_roll_values(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25567")
    start_card(card_id)
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "50.00",
        tare_weight="2.00",
        pallet_number="1",
        require_active_shift=True,
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "60.00",
        pallet_number="2",
        require_active_shift=True,
    ).ok
    before = db.fetch_terminal_card_detail(card_id)
    first_id = int(before["roll_entries"][0]["id"])
    second_id = int(before["roll_entries"][1]["id"])

    result = db.update_terminal_roll_corrections(
        card_id,
        before["version"],
        {
            first_id: {"pallet_number": "3", "gross_weight": "55.00", "tare_weight": "2.50"},
            second_id: {"pallet_number": "1000", "gross_weight": "65.00", "tare_weight": "3.00"},
        },
        require_active_shift=True,
    )
    after = db.fetch_terminal_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Палетът трябва да бъде цяло число от 1 до 999.",)
    assert after["version"] == before["version"]
    assert [(roll["pallet_number"], roll["gross_weight"], roll["tare_weight"], roll["net_weight"])
            for roll in after["roll_entries"]] == [
        (1, 50, 2, 48),
        (2, 60, 2, 58),
    ]


def test_terminal_roll_corrections_pallet_noop_does_not_increment_version(connection, active_test_shift):
    card_id = import_and_release_card("25568")
    start_card(card_id)
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "50.00",
        tare_weight="2.00",
        pallet_number="1",
        require_active_shift=True,
    ).ok
    before = db.fetch_terminal_card_detail(card_id)
    roll_id = int(before["roll_entries"][0]["id"])

    result = db.update_terminal_roll_corrections(
        card_id,
        before["version"],
        {roll_id: {"pallet_number": "001"}},
        require_active_shift=True,
    )
    after = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert after["version"] == before["version"]
    assert after["roll_entries"][0]["pallet_number"] == 1


def test_stale_roll_add_and_update_are_blocked(connection, active_test_shift):
    card_id = import_and_release_card("25505")
    start_card(card_id)
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.00",
    ).ok
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]
    assert db.add_roll_gross_weight(card_id, loaded_version, "20").ok
    roll_id = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]["id"]

    stale_add = db.add_roll_gross_weight(card_id, loaded_version, "21")
    stale_update = db.update_roll_gross_weight(card_id, roll_id, loaded_version, "22")
    card = db.fetch_terminal_card_detail(card_id)

    assert not stale_add.ok
    assert stale_add.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert not stale_update.ok
    assert stale_update.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert card["roll_count"] == 1
    assert card["roll_entries"][0]["gross_weight"] == 20


def test_clearing_existing_gross_weight_removes_it_from_totals(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25506")
    start_card(card_id)
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.00",
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
    ).ok
    card = db.fetch_terminal_card_detail(card_id)
    roll_id = card["roll_entries"][0]["id"]

    result = db.update_roll_gross_weight(
        card_id,
        roll_id,
        card["version"],
        "",
    )
    cleared_card = db.fetch_terminal_card_detail(card_id)
    cleared_roll = cleared_card["roll_entries"][0]

    assert result.ok
    assert cleared_roll["gross_weight"] is None
    assert cleared_roll["net_weight"] is None
    assert cleared_card["roll_count"] == 0
    assert cleared_card["total_gross_weight"] == "0.00"
    assert cleared_card["total_net_weight"] == "0.00"


def test_delete_middle_roll_renumbers_remaining_rolls_and_recalculates_totals(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25508")
    start_card(card_id)
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.00",
    ).ok
    for gross_weight in ("10.00", "20.00", "30.00"):
        assert db.add_roll_gross_weight(
            card_id,
            db.fetch_terminal_card_detail(card_id)["version"],
            gross_weight,
        ).ok

    card = db.fetch_terminal_card_detail(card_id)
    middle_roll_id = card["roll_entries"][1]["id"]
    loaded_version = card["version"]

    result = db.delete_roll_entry(card_id, middle_roll_id, loaded_version)
    updated_card = db.fetch_terminal_card_detail(card_id)
    updated_rolls = updated_card["roll_entries"]

    assert result.ok
    assert result.messages == ("Ролка 2 е изтрита. Оставащите ролки са преномерирани.",)
    assert updated_card["version"] == loaded_version + 1
    assert updated_card["roll_count"] == 2
    assert updated_card["next_roll_number"] == 3
    assert updated_card["total_gross_weight"] == "40.00"
    assert updated_card["total_net_weight"] == "38.00"
    assert [
        (roll["roll_number"], roll["gross_weight"], roll["net_weight"])
        for roll in updated_rolls
    ] == [
        (1, 10, 9),
        (2, 30, 29),
    ]


def test_delete_roll_is_blocked_when_card_is_not_running_or_completed(connection):
    card_id = import_and_release_card("25509")
    connection.execute(
        """
        INSERT INTO roll_entries (card_id, order_number, roll_number, gross_weight, net_weight)
        VALUES (?, '25509', 1, 25.00, NULL)
        """,
        (card_id,),
    )
    connection.commit()
    roll_id = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]["id"]

    result = db.delete_roll_entry(
        card_id,
        roll_id,
        db.fetch_terminal_card_detail(card_id)["version"],
    )

    assert not result.ok
    assert result.messages == (
        "Теглата на ролките могат да се променят само когато картата е в изработване, произведена или завършена.",
    )
    assert db.fetch_terminal_card_detail(card_id)["roll_count"] == 1


def test_delete_roll_checks_loaded_version(connection, active_test_shift):
    card_id = import_and_release_card("25510")
    start_card(card_id)
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.00",
    ).ok
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]
    assert db.add_roll_gross_weight(card_id, loaded_version, "20.00").ok
    roll_id = db.fetch_terminal_card_detail(card_id)["roll_entries"][0]["id"]

    stale_result = db.delete_roll_entry(card_id, roll_id, loaded_version)

    assert not stale_result.ok
    assert stale_result.messages == (
        "Картата е променена след зареждането на страницата. Презаредете и опитайте отново.",
    )
    assert db.fetch_terminal_card_detail(card_id)["roll_count"] == 1


def test_completed_card_roll_delete_remains_editable_and_renumbers(
    connection,
    active_test_shift,
):
    card_id = import_and_release_card("25511")
    start_card(card_id)
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.00",
    ).ok
    for gross_weight in ("25.00", "30.00"):
        assert db.add_roll_gross_weight(
            card_id,
            db.fetch_terminal_card_detail(card_id)["version"],
            gross_weight,
        ).ok
    assert db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok

    completed_card = db.fetch_terminal_card_detail(card_id)
    first_roll_id = completed_card["roll_entries"][0]["id"]
    result = db.delete_roll_entry(card_id, first_roll_id, completed_card["version"])
    updated_card = db.fetch_terminal_card_detail(card_id)

    assert result.ok
    assert updated_card["status"] == "completed"
    assert updated_card["roll_count"] == 1
    assert updated_card["roll_entries"][0]["roll_number"] == 1
    assert updated_card["roll_entries"][0]["gross_weight"] == 30


def test_completed_card_cannot_delete_final_gross_roll(connection, active_test_shift):
    card_id = import_and_release_card("25512")
    start_card(card_id)
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.00",
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
    ).ok
    assert db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok

    completed_card = db.fetch_terminal_card_detail(card_id)
    only_roll_id = completed_card["roll_entries"][0]["id"]
    result = db.delete_roll_entry(card_id, only_roll_id, completed_card["version"])
    updated_card = db.fetch_terminal_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Завършените карти трябва да запазят поне едно бруто тегло на ролка.",)
    assert updated_card["status"] == "completed"
    assert updated_card["roll_count"] == 1
    assert updated_card["roll_entries"][0]["roll_number"] == 1
    assert updated_card["roll_entries"][0]["gross_weight"] == 25


def test_completed_card_cannot_clear_final_gross_roll(connection, active_test_shift):
    card_id = import_and_release_card("25513")
    start_card(card_id)
    assert db.update_tare_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "1.00",
    ).ok
    assert db.add_roll_gross_weight(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
        "25.00",
    ).ok
    assert db.finish_card(card_id, db.fetch_terminal_card_detail(card_id)["version"]).ok

    completed_card = db.fetch_terminal_card_detail(card_id)
    only_roll_id = completed_card["roll_entries"][0]["id"]
    result = db.update_roll_gross_weight(
        card_id,
        only_roll_id,
        completed_card["version"],
        "",
    )
    updated_card = db.fetch_terminal_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Завършените карти трябва да запазят поне едно бруто тегло на ролка.",)
    assert updated_card["status"] == "completed"
    assert updated_card["roll_count"] == 1
    assert updated_card["roll_entries"][0]["gross_weight"] == 25
