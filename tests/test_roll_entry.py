from __future__ import annotations

import csv
import io

from app import db
from app.constants import STATUS_PAUSED, STATUS_PENDING, STATUS_RUNNING
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
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "da",
        "raw_material_a": "LDPE A | 100%",
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
        max_roll_weight="60.0",
    ).ok
    return card_id


def start_card(card_id: int) -> None:
    assert db.start_production_timing(
        card_id,
        db.fetch_terminal_card_detail(card_id)["version"],
    ).ok


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


def test_add_roll_while_running_assigns_roll_numbers(connection):
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


def test_add_roll_requires_default_tare(connection):
    card_id = import_and_release_card("25546")
    start_card(card_id)
    loaded_version = db.fetch_terminal_card_detail(card_id)["version"]

    result = db.add_roll_gross_weight(card_id, loaded_version, "25.00")
    card = db.fetch_terminal_card_detail(card_id)

    assert not result.ok
    assert result.messages == ("Въведете шпула преди да добавите ролка.",)
    assert card["roll_entries"] == []
    assert card["version"] == loaded_version


def test_add_roll_allows_submitted_tare_without_existing_default(connection):
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


def test_gross_and_net_totals_calculate_with_tare(connection):
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


def test_new_roll_copies_current_default_tare_without_mutating_existing_rolls(connection):
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


def test_editing_roll_tare_recalculates_only_that_roll_and_not_default_tare(connection):
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


def test_roll_tare_rejects_more_than_two_decimal_places_and_tare_above_gross(connection):
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


def test_stale_roll_add_and_update_are_blocked(connection):
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


def test_clearing_existing_gross_weight_removes_it_from_totals(connection):
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


def test_delete_middle_roll_renumbers_remaining_rolls_and_recalculates_totals(connection):
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


def test_delete_roll_checks_loaded_version(connection):
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


def test_completed_card_roll_delete_remains_editable_and_renumbers(connection):
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


def test_completed_card_cannot_delete_final_gross_roll(connection):
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


def test_completed_card_cannot_clear_final_gross_roll(connection):
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
