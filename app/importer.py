from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any

from .constants import STATUS_IMPORTED
from .db import connect


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


def csv_template() -> str:
    sample_values = {
        "order_number": "25278",
        "customer": "Sample Customer",
        "product_type": "PE film",
        "quantity_1": "500",
        "unit_1": "kg",
        "material": "LDPE",
        "size_thickness": "600/0.050",
        "extrusion_flag": "да",
        "raw_material_a": "LDPE",
        "packaging_method": "rolls",
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
        message = "CSV file has no header row."
        result.row_errors.append(message)
        result.row_results.append(
            ImportRowResult(
                row_number=None,
                order_number="",
                action="blocked",
                message=message,
            )
        )
        return result

    header_map = build_header_map(reader.fieldnames)
    missing_required = [field for field in ("order_number", "extrusion_flag") if field not in header_map.values()]
    if missing_required:
        message = f"Missing required CSV columns: {', '.join(missing_required)}."
        result.row_errors.append(message)
        result.row_results.append(
            ImportRowResult(
                row_number=None,
                order_number="",
                action="blocked",
                message=message,
            )
        )
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
                message = "Missing order_number."
                result.skipped += 1
                result.row_errors.append(f"Row {row_number}: {message}")
                result.row_results.append(
                    ImportRowResult(
                        row_number=row_number,
                        order_number="",
                        action="skipped",
                        message=message,
                    )
                )
                continue

            if not card_has_usable_extrusion_step(card):
                message = "Skipped because this row has no extrusion step."
                result.skipped += 1
                result.row_errors.append(f"Row {row_number}: {message}")
                result.row_results.append(
                    ImportRowResult(
                        row_number=row_number,
                        order_number=order_number,
                        action="skipped",
                        message=message,
                    )
                )
                continue

            if order_number in seen_order_numbers:
                message = "Duplicate order number inside this CSV."
                result.skipped += 1
                result.duplicate_rows.append(order_number)
                result.row_errors.append(f"Row {row_number}: {message} {order_number}.")
                result.row_results.append(
                    ImportRowResult(
                        row_number=row_number,
                        order_number=order_number,
                        action="skipped",
                        message=message,
                    )
                )
                continue

            seen_order_numbers.add(order_number)

            existing = connection.execute(
                "SELECT id FROM cards WHERE order_number = ?",
                (order_number,),
            ).fetchone()

            if existing and not overwrite_existing:
                message = "Skipped duplicate existing order. Select overwrite to update imported fields."
                result.skipped += 1
                result.duplicate_rows.append(order_number)
                result.row_results.append(
                    ImportRowResult(
                        row_number=row_number,
                        order_number=order_number,
                        action="skipped",
                        message=message,
                    )
                )
                continue

            if existing:
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
            result.row_results.append(
                ImportRowResult(
                    row_number=row_number,
                    order_number=order_number,
                    action=action,
                    message=message,
                )
            )

        connection.execute(
            """
            UPDATE import_batches
            SET rows_seen = ?, rows_imported = ?
            WHERE id = ?
            """,
            (result.rows_seen, result.rows_imported, result.batch_id),
        )

    return result


def import_success_message(*, updated: bool) -> str:
    action = "Updated existing card" if updated else "Created new card"
    return f"{action}; ready for planning."


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

    connection.execute(
        f"""
        INSERT INTO cards ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        values,
    )


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
