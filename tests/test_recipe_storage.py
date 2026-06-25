from __future__ import annotations

import csv
import io
import sqlite3
from decimal import Decimal

from app import db
from app.recipe_parser import ParsedRecipeComponent


def insert_card(
    connection,
    order_number: str = "RS-001",
    raw_material_a: str = "LDPE Rompetrol B20/03 | 100%",
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO cards (
            order_number,
            status,
            extrusion_flag,
            raw_material_a
        )
        VALUES (?, 'imported', 'да', ?)
        """,
        (order_number, raw_material_a),
    )
    connection.commit()
    return int(cursor.lastrowid)


def stored_components(connection, card_id: int):
    return connection.execute(
        """
        SELECT component_key, source_text, material_category,
               planned_material, recipe_percent
        FROM recipe_components
        WHERE card_id = ?
        ORDER BY id
        """,
        (card_id,),
    ).fetchall()


def valid_components():
    return (
        ParsedRecipeComponent(
            component_key="raw_material_a",
            source_text="LDPE Rompetrol Midilena B20/03 | 77%",
            material_category="LDPE",
            planned_material="Rompetrol Midilena B20/03",
            recipe_percent=Decimal("77"),
        ),
        ParsedRecipeComponent(
            component_key="linear_pe",
            source_text="LLDPE SABIC 119ZJ | 23%",
            material_category="LLDPE",
            planned_material="SABIC 119ZJ",
            recipe_percent=Decimal("23"),
        ),
    )


def csv_bytes(rows: list[dict[str, str]]) -> bytes:
    fieldnames = [
        "order_number",
        "customer",
        "product_type",
        "quantity_1",
        "unit_1",
        "material",
        "size_thickness",
        "extrusion_flag",
        "raw_material_a",
        "packaging_method",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fieldnames})
    return output.getvalue().encode("utf-8")


def extrusion_row(order_number: str, **overrides: str) -> dict[str, str]:
    row = {
        "order_number": order_number,
        "customer": "Recipe Storage Customer",
        "product_type": "PE film",
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "да",
        "raw_material_a": "LDPE Rompetrol B20/03 | 100%",
        "packaging_method": "rolls",
    }
    row.update(overrides)
    return row


def test_recipe_components_table_exists_after_init(connection):
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(recipe_components)").fetchall()
    }
    schema_sql = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'recipe_components'
        """
    ).fetchone()["sql"]

    assert {
        "id",
        "card_id",
        "component_key",
        "source_text",
        "material_category",
        "planned_material",
        "recipe_percent",
        "created_at",
        "updated_at",
    }.issubset(columns)
    assert "UNIQUE (card_id, component_key)" in schema_sql
    assert "recipe_percent > 0" in schema_sql


def test_recipe_components_reject_unknown_component_key(connection):
    card_id = insert_card(connection)

    try:
        connection.execute(
            """
            INSERT INTO recipe_components (
                card_id,
                component_key,
                source_text,
                material_category,
                planned_material,
                recipe_percent
            )
            VALUES (?, 'not_a_recipe_field', 'LDPE A | 100%', 'LDPE', 'A', 100)
            """,
            (card_id,),
        )
    except sqlite3.IntegrityError as exc:
        assert "CHECK constraint failed" in str(exc)
    else:
        raise AssertionError("recipe_components accepted an unknown component_key")


def test_recipe_components_reject_unknown_material_category(connection):
    card_id = insert_card(connection)

    try:
        connection.execute(
            """
            INSERT INTO recipe_components (
                card_id,
                component_key,
                source_text,
                material_category,
                planned_material,
                recipe_percent
            )
            VALUES (?, 'raw_material_a', 'mLLDPE A | 100%', 'mLLDPE', 'A', 100)
            """,
            (card_id,),
        )
    except sqlite3.IntegrityError as exc:
        assert "CHECK constraint failed" in str(exc)
    else:
        raise AssertionError("recipe_components accepted an unknown material_category")


def test_recipe_components_cascade_when_card_is_deleted(connection):
    card_id = insert_card(connection)
    db.replace_recipe_components_for_card(connection, card_id, valid_components())

    connection.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    connection.commit()

    row_count = connection.execute(
        "SELECT COUNT(*) AS row_count FROM recipe_components WHERE card_id = ?",
        (card_id,),
    ).fetchone()["row_count"]

    assert row_count == 0


def test_database_initialization_adds_recipe_components_to_existing_database(
    tmp_path,
    monkeypatch,
):
    legacy_data_dir = tmp_path / "legacy-data"
    legacy_data_dir.mkdir()
    legacy_db_path = legacy_data_dir / "legacy.sqlite3"
    with sqlite3.connect(legacy_db_path) as legacy_connection:
        legacy_connection.execute(
            """
            CREATE TABLE cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'imported',
                raw_material_a TEXT
            )
            """
        )
        legacy_connection.execute(
            """
            INSERT INTO cards (order_number, raw_material_a)
            VALUES ('LEGACY-RS-1', 'LDPE Legacy A | 100%')
            """
        )

    monkeypatch.setattr(db, "DATA_DIR", legacy_data_dir)
    monkeypatch.setattr(db, "DB_PATH", legacy_db_path)

    db.init_db()
    db.init_db()

    with db.connect() as migrated_connection:
        table = migrated_connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'recipe_components'
            """
        ).fetchone()
        row_count = migrated_connection.execute(
            "SELECT COUNT(*) AS row_count FROM recipe_components"
        ).fetchone()["row_count"]

    assert table is not None
    assert row_count == 0


def test_database_initialization_handles_legacy_assigned_cards_before_machines_exist(
    tmp_path,
    monkeypatch,
):
    legacy_data_dir = tmp_path / "legacy-assigned-data"
    legacy_data_dir.mkdir()
    legacy_db_path = legacy_data_dir / "legacy-assigned.sqlite3"
    with sqlite3.connect(legacy_db_path) as legacy_connection:
        legacy_connection.execute(
            """
            CREATE TABLE cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'imported',
                machine_id INTEGER,
                machine_sequence INTEGER,
                raw_material_a TEXT
            )
            """
        )
        legacy_connection.execute(
            """
            INSERT INTO cards (
                order_number, machine_id, machine_sequence, raw_material_a
            )
            VALUES ('LEGACY-RS-ASSIGNED-1', 1, 1, 'LDPE Legacy A | 100%')
            """
        )

    monkeypatch.setattr(db, "DATA_DIR", legacy_data_dir)
    monkeypatch.setattr(db, "DB_PATH", legacy_db_path)

    db.init_db()

    with db.connect() as migrated_connection:
        card = migrated_connection.execute(
            """
            SELECT order_number, machine_id, machine_sequence, raw_material_a
            FROM cards
            WHERE order_number = 'LEGACY-RS-ASSIGNED-1'
            """
        ).fetchone()
        row_count = migrated_connection.execute(
            "SELECT COUNT(*) AS row_count FROM recipe_components"
        ).fetchone()["row_count"]

    assert dict(card) == {
        "order_number": "LEGACY-RS-ASSIGNED-1",
        "machine_id": 1,
        "machine_sequence": 1,
        "raw_material_a": "LDPE Legacy A | 100%",
    }
    assert row_count == 0


def test_replace_recipe_components_for_card_stores_normalized_rows(connection):
    card_id = insert_card(connection)

    db.replace_recipe_components_for_card(connection, card_id, valid_components())
    rows = stored_components(connection, card_id)

    assert len(rows) == 2
    assert dict(rows[0]) == {
        "component_key": "raw_material_a",
        "source_text": "LDPE Rompetrol Midilena B20/03 | 77%",
        "material_category": "LDPE",
        "planned_material": "Rompetrol Midilena B20/03",
        "recipe_percent": 77,
    }
    assert dict(rows[1]) == {
        "component_key": "linear_pe",
        "source_text": "LLDPE SABIC 119ZJ | 23%",
        "material_category": "LLDPE",
        "planned_material": "SABIC 119ZJ",
        "recipe_percent": 23,
    }


def test_fetch_recipe_components_returns_parser_field_order(connection):
    card_id = insert_card(connection)
    db.replace_recipe_components_for_card(
        connection,
        card_id,
        (
            ParsedRecipeComponent(
                component_key="masterbatch",
                source_text="Masterbatch White 8000 | 3%",
                material_category="Masterbatch",
                planned_material="White 8000",
                recipe_percent=Decimal("3"),
            ),
            ParsedRecipeComponent(
                component_key="raw_material_a",
                source_text="LDPE Rompetrol B20/03 | 97%",
                material_category="LDPE",
                planned_material="Rompetrol B20/03",
                recipe_percent=Decimal("97"),
            ),
        ),
    )

    rows = db.fetch_recipe_components(connection, card_id)

    assert [row["component_key"] for row in rows] == ["raw_material_a", "masterbatch"]
    assert rows[0]["recipe_percent"] == Decimal("97")
    assert rows[1]["recipe_percent"] == Decimal("3")


def test_replace_recipe_components_for_card_removes_stale_rows(connection):
    card_id = insert_card(connection)
    db.replace_recipe_components_for_card(connection, card_id, valid_components())

    db.replace_recipe_components_for_card(
        connection,
        card_id,
        (
            ParsedRecipeComponent(
                component_key="raw_material_a",
                source_text="LDPE New Material | 100%",
                material_category="LDPE",
                planned_material="New Material",
                recipe_percent=Decimal("100"),
            ),
        ),
    )
    rows = db.fetch_recipe_components(connection, card_id)

    assert [row["component_key"] for row in rows] == ["raw_material_a"]
    assert rows[0]["source_text"] == "LDPE New Material | 100%"
    assert rows[0]["recipe_percent"] == Decimal("100")


def test_parse_and_replace_recipe_components_for_card_stores_only_valid_parse(connection):
    card_id = insert_card(connection)

    result = db.parse_and_replace_recipe_components_for_card(
        connection,
        card_id,
        {
            "raw_material_a": "LDPE Rompetrol B20/03 | 80%",
            "linear_pe": "LLDPE SABIC 119ZJ | 20%",
        },
    )

    assert result.ok
    rows = db.fetch_recipe_components(connection, card_id)
    assert [row["component_key"] for row in rows] == ["raw_material_a", "linear_pe"]


def test_recipe_components_store_category_only_planned_material_as_empty_string(connection):
    card_id = insert_card(connection, raw_material_a="reLDPE | 100%")

    result = db.parse_and_replace_recipe_components_for_card(
        connection,
        card_id,
        {"raw_material_a": "reLDPE | 100%"},
    )

    assert result.ok
    rows = db.fetch_recipe_components(connection, card_id)
    assert len(rows) == 1
    assert rows[0]["source_text"] == "reLDPE | 100%"
    assert rows[0]["material_category"] == "reLDPE"
    assert rows[0]["planned_material"] == ""
    assert rows[0]["recipe_percent"] == Decimal("100")


def test_parse_and_replace_recipe_components_for_card_does_not_mutate_on_parse_error(connection):
    card_id = insert_card(connection)
    db.replace_recipe_components_for_card(connection, card_id, valid_components())

    result = db.parse_and_replace_recipe_components_for_card(
        connection,
        card_id,
        {
            "raw_material_a": "LDPE Rompetrol B20/03 | 80%",
            "linear_pe": "LLDPE SABIC 119ZJ | 19%",
        },
    )

    assert not result.ok
    assert [error.message for error in result.errors] == [
        "сборът на процентите трябва да е точно 100%"
    ]
    rows = db.fetch_recipe_components(connection, card_id)
    assert [row["source_text"] for row in rows] == [
        "LDPE Rompetrol Midilena B20/03 | 77%",
        "LLDPE SABIC 119ZJ | 23%",
    ]


def test_recipe_component_replacement_does_not_touch_actual_recipe_entries(connection):
    card_id = insert_card(connection)
    connection.execute(
        """
        INSERT INTO recipe_actual_entries (
            card_id,
            component_key,
            component_label,
            planned_material,
            actual_material_used,
            batch_lot
        )
        VALUES (?, 'raw_material_a', 'Вид суровина A', 'Old planned', 'Actual LDPE', 'Batch 42')
        """,
        (card_id,),
    )
    connection.commit()

    db.replace_recipe_components_for_card(connection, card_id, valid_components())

    actual_entry = connection.execute(
        """
        SELECT planned_material, actual_material_used, batch_lot
        FROM recipe_actual_entries
        WHERE card_id = ?
          AND component_key = 'raw_material_a'
        """,
        (card_id,),
    ).fetchone()

    assert dict(actual_entry) == {
        "planned_material": "Old planned",
        "actual_material_used": "Actual LDPE",
        "batch_lot": "Batch 42",
    }
