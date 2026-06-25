from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .constants import STATUS_IMPORTED
from .db import connect, insert_import_batch_row, sync_recipe_components_for_card


IMPORT_FIELDS = (
    "order_number",
    "order_date",
    "delivery_date",
    "customer",
    "city",
    "product_type",
    "quantity_1",
    "unit_1",
    "quantity_2",
    "unit_2",
    "product_form",
    "material",
    "size_thickness",
    "notes",
    "extrusion_flag",
    "extrusion_folding",
    "extrusion_next_operation",
    "extrusion_treatment",
    "raw_material_a",
    "raw_material_b",
    "raw_material_c",
    "linear_pe",
    "antistatic",
    "masterbatch",
    "chalk",
    "packaging_method",
)

EXTRUSION_DETAIL_FIELDS = (
    "extrusion_folding",
    "extrusion_next_operation",
    "extrusion_treatment",
    "raw_material_a",
    "raw_material_b",
    "raw_material_c",
    "linear_pe",
    "antistatic",
    "masterbatch",
    "chalk",
    "packaging_method",
)

FIELD_ALIASES = {
    "order_no": "order_number",
    "order": "order_number",
    "date": "order_date",
    "company": "customer",
    "firm": "customer",
    "quantity1": "quantity_1",
    "qty1": "quantity_1",
    "unit1": "unit_1",
    "quantity2": "quantity_2",
    "qty2": "quantity_2",
    "unit2": "unit_2",
    "blank_type": "product_form",
    "form": "product_form",
    "size": "size_thickness",
    "thickness": "size_thickness",
    "extrusion": "extrusion_flag",
    "folding": "extrusion_folding",
    "next_operation": "extrusion_next_operation",
    "treatment": "extrusion_treatment",
    "material_a": "raw_material_a",
    "material_b": "raw_material_b",
    "material_c": "raw_material_c",
    "linear": "linear_pe",
    "linear_pe_percent": "linear_pe",
    "packaging": "packaging_method",
}

TRUE_EXTRUSION_FLAGS = {
    "1",
    "true",
    "yes",
    "y",
    "x",
    "da",
    "да",
    "дa",
    "ð´ð°",
}


STALE_IMPORT_MESSAGE = (
    "Блокиран ред: картата има коригирани от администратор данни след последния импорт. "
    "Прегледайте картата преди повторен импорт."
)


@dataclass
class ImportRowResult:
    row_number: int | None
    order_number: str
    action: str
    message: str


@dataclass
class ImportResult:
    filename: str
    rows_seen: int = 0
    rows_imported: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    duplicate_rows: list[str] = field(default_factory=list)
    row_errors: list[str] = field(default_factory=list)
    row_results: list[ImportRowResult] = field(default_factory=list)
    batch_id: int | None = None


def record_import_row_result(
    result: ImportResult,
    row_number: int | None,
    order_number: str,
    action: str,
    message: str,
    connection: Any | None = None,
    is_duplicate_row: bool = False,
    row_error: str | None = None,
) -> None:
    row_result = ImportRowResult(
        row_number=row_number,
        order_number=order_number,
        action=action,
        message=message,
    )
    result.row_results.append(row_result)
    if connection is not None and result.batch_id is not None:
        insert_import_batch_row(
            connection,
            int(result.batch_id),
            len(result.row_results),
            row_number,
            order_number,
            action,
            message,
            is_duplicate_row,
            row_error,
        )


def csv_template() -> str:
    sample_values = {
        "order_number": "25278",
        "customer": "Примерен клиент",
        "product_type": "PE фолио",
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "да",
        "raw_material_a": "LDPE",
        "packaging_method": "ролки",
    }
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=IMPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerow({field: sample_values.get(field, "") for field in IMPORT_FIELDS})
    return output.getvalue()


def import_cards_from_csv(filename: str, content: bytes, overwrite_existing: bool) -> ImportResult:
    result = ImportResult(filename=filename)
    text = decode_csv(content)
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        message = "CSV файлът няма заглавен ред."
        result.row_errors.append(message)
        record_import_row_result(result, None, "", "blocked", message)
        return result

    header_map = build_header_map(reader.fieldnames)
    missing_required = [field for field in ("order_number", "extrusion_flag") if field not in header_map.values()]
    if missing_required:
        message = f"Липсват задължителни CSV колони: {', '.join(missing_required)}."
        result.row_errors.append(message)
        record_import_row_result(result, None, "", "blocked", message)
        return result

    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO import_batches (source_filename, rows_seen, rows_imported)
            VALUES (?, 0, 0)
            """,
            (filename,),
        )
        result.batch_id = cursor.lastrowid

        seen_order_numbers: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            result.rows_seen += 1
            card = normalize_row(row, header_map)
            order_number = card["order_number"]

            if not order_number:
                message = "Липсва номер на поръчка."
                result.skipped += 1
                row_error = f"Ред {row_number}: {message}"
                result.row_errors.append(row_error)
                record_import_row_result(
                    result,
                    row_number,
                    "",
                    "skipped",
                    message,
                    connection,
                    row_error=row_error,
                )
                continue

            if not card_has_usable_extrusion_step(card):
                message = "Пропуснат ред: няма екструдиране."
                result.skipped += 1
                row_error = f"Ред {row_number}: {message}"
                result.row_errors.append(row_error)
                record_import_row_result(
                    result,
                    row_number,
                    order_number,
                    "skipped",
                    message,
                    connection,
                    row_error=row_error,
                )
                continue

            if order_number in seen_order_numbers:
                message = "Дублиран номер на поръчка в този CSV файл."
                result.skipped += 1
                result.duplicate_rows.append(order_number)
                row_error = f"Ред {row_number}: {message} {order_number}."
                result.row_errors.append(row_error)
                record_import_row_result(
                    result,
                    row_number,
                    order_number,
                    "skipped",
                    message,
                    connection,
                    is_duplicate_row=True,
                    row_error=row_error,
                )
                continue

            seen_order_numbers.add(order_number)

            existing = find_existing_import_card(connection, order_number)

            if existing and existing["order_number"] != order_number:
                block_import_row(result, row_number, order_number, STALE_IMPORT_MESSAGE, connection)
                continue

            if existing and not overwrite_existing:
                message = "Пропусната съществуваща поръчка. Отметнете обновяване, за да обновите данните от импорта."
                result.skipped += 1
                result.duplicate_rows.append(order_number)
                record_import_row_result(
                    result,
                    row_number,
                    order_number,
                    "skipped",
                    message,
                    connection,
                    is_duplicate_row=True,
                )
                continue

            if existing:
                if has_stale_import_overwrite_conflict(connection, int(existing["id"]), card):
                    block_import_row(result, row_number, order_number, STALE_IMPORT_MESSAGE, connection)
                    continue
                update_imported_card_fields(connection, int(existing["id"]), int(result.batch_id), card)
                result.updated += 1
                action = "updated"
                message = import_success_message(updated=True)
            else:
                insert_imported_card(connection, int(result.batch_id), card)
                result.created += 1
                action = "created"
                message = import_success_message(updated=False)

            result.rows_imported += 1
            record_import_row_result(result, row_number, order_number, action, message, connection)

        connection.execute(
            """
            UPDATE import_batches
            SET rows_seen = ?, rows_imported = ?
            WHERE id = ?
            """,
            (result.rows_seen, result.rows_imported, result.batch_id),
        )

    return result


def block_import_row(
    result: ImportResult,
    row_number: int,
    order_number: str,
    message: str,
    connection: Any | None = None,
) -> None:
    result.skipped += 1
    row_error = f"Ред {row_number}: {message} {order_number}."
    result.row_errors.append(row_error)
    record_import_row_result(
        result,
        row_number,
        order_number,
        "blocked",
        message,
        connection,
        row_error=row_error,
    )


def import_success_message(*, updated: bool) -> str:
    if updated:
        return "Обновена съществуваща технологична карта; готова за планиране."
    return "Създадена нова технологична карта; готова за планиране."


def decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8-sig", errors="replace")


def build_header_map(headers: list[str]) -> dict[str, str]:
    header_map: dict[str, str] = {}
    for header in headers:
        normalized = normalize_header(header)
        canonical = FIELD_ALIASES.get(normalized, normalized)
        if canonical in IMPORT_FIELDS:
            header_map[header] = canonical
    return header_map


def normalize_header(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.strip().casefold()
    for char in (" ", "-", ".", "/", "\\"):
        normalized = normalized.replace(char, "_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_")


def normalize_row(row: dict[str, Any], header_map: dict[str, str]) -> dict[str, str]:
    card = {field: "" for field in IMPORT_FIELDS}
    for source_header, canonical in header_map.items():
        card[canonical] = clean_cell(row.get(source_header))
    return card


def clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def card_has_usable_extrusion_step(card: dict[str, str]) -> bool:
    extrusion_flag = normalize_flag(card["extrusion_flag"])
    has_extrusion_details = any(card[field] for field in EXTRUSION_DETAIL_FIELDS)

    return extrusion_flag in TRUE_EXTRUSION_FLAGS and has_extrusion_details


def normalize_flag(value: str) -> str:
    return value.strip().casefold()


def insert_imported_card(connection, batch_id: int, card: dict[str, str]) -> None:
    columns = (
        "import_batch_id",
        "status",
        *IMPORT_FIELDS,
    )
    values = [
        batch_id,
        STATUS_IMPORTED,
        *(card[field] for field in IMPORT_FIELDS),
    ]
    placeholders = ", ".join("?" for _ in columns)

    cursor = connection.execute(
        f"""
        INSERT INTO cards ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        values,
    )
    card_id = int(cursor.lastrowid)
    upsert_card_import_source(connection, card_id, batch_id, card)
    sync_recipe_components_for_card(connection, card_id, card)


def update_imported_card_fields(connection, card_id: int, batch_id: int, card: dict[str, str]) -> None:
    assignments = [
        "import_batch_id = ?",
        *(f"{field} = ?" for field in IMPORT_FIELDS),
        "version = version + 1",
        "updated_at = CURRENT_TIMESTAMP",
    ]
    values = [
        batch_id,
        *(card[field] for field in IMPORT_FIELDS),
        card_id,
    ]

    connection.execute(
        f"""
        UPDATE cards
        SET {", ".join(assignments)}
        WHERE id = ?
        """,
        values,
    )
    upsert_card_import_source(connection, card_id, batch_id, card)
    sync_recipe_components_for_card(connection, card_id, card)


def find_existing_import_card(
    connection: sqlite3.Connection,
    order_number: str,
) -> sqlite3.Row | None:
    existing = connection.execute(
        "SELECT id, order_number FROM cards WHERE order_number = ?",
        (order_number,),
    ).fetchone()
    if existing:
        return existing

    return connection.execute(
        """
        SELECT cards.id, cards.order_number
        FROM card_import_sources
        JOIN cards ON cards.id = card_import_sources.card_id
        WHERE card_import_sources.order_number = ?
        """,
        (order_number,),
    ).fetchone()


def has_stale_import_overwrite_conflict(
    connection: sqlite3.Connection,
    card_id: int,
    incoming_card: dict[str, str],
) -> bool:
    current = fetch_import_field_values(connection, "cards", "id", card_id)
    source = fetch_import_field_values(connection, "card_import_sources", "card_id", card_id)
    if source is None:
        source = current

    if current is None:
        return False

    for field in IMPORT_FIELDS:
        current_value = normalize_import_value(current[field])
        source_value = normalize_import_value(source[field])
        incoming_value = normalize_import_value(incoming_card[field])
        if current_value != source_value and incoming_value != current_value:
            return True
    return False


def fetch_import_field_values(
    connection: sqlite3.Connection,
    table_name: str,
    id_column: str,
    id_value: int,
) -> sqlite3.Row | None:
    return connection.execute(
        f"""
        SELECT {", ".join(IMPORT_FIELDS)}
        FROM {table_name}
        WHERE {id_column} = ?
        """,
        (id_value,),
    ).fetchone()


def normalize_import_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def upsert_card_import_source(
    connection: sqlite3.Connection,
    card_id: int,
    batch_id: int,
    card: dict[str, str],
) -> None:
    columns = (
        "card_id",
        "import_batch_id",
        *IMPORT_FIELDS,
    )
    placeholders = ", ".join("?" for _ in columns)
    update_assignments = [
        "import_batch_id = excluded.import_batch_id",
        *(f"{field} = excluded.{field}" for field in IMPORT_FIELDS),
        "updated_at = CURRENT_TIMESTAMP",
    ]
    values = [
        card_id,
        batch_id,
        *(card[field] for field in IMPORT_FIELDS),
    ]

    connection.execute(
        f"""
        INSERT INTO card_import_sources ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(card_id) DO UPDATE SET
            {", ".join(update_assignments)}
        """,
        values,
    )
