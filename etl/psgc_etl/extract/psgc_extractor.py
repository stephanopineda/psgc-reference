"""Faithful extraction of source records from PSA PSGC workbooks."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.utils import get_column_letter

from psgc_etl.extract.workbook_profiler import PSGC_SHEET_NAME

EXTRACTION_PROFILE_VERSION = "1.0"

# This profile applies to the inspected 1Q 2024, 4Q 2024, and 1Q 2025
# PSA workbooks. Other source layouts require an explicitly reviewed profile.
SOURCE_COLUMNS = (
    ("10-digit PSGC", "psgc_code"),
    ("Name", "name"),
    ("Correspondence Code", "correspondence_code"),
    ("Geographic Level", "geographic_level"),
    ("Old names", "old_names"),
    ("City Class", "city_class"),
    ("Income\nClassification", "income_classification"),
    ("Urban / Rural\n(based on 2020 CPH)", "urban_rural"),
    ("2020 Population", "population"),
    (None, "population_annotation"),
    ("Status", "source_status_value"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_header(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    return re.sub(r"\s+", " ", value).strip().casefold() or None


def _python_type(value: Any) -> str:
    if value is None:
        return "NoneType"
    return type(value).__name__


def _is_populated(value: Any) -> bool:
    return value is not None and value != ""


def _validate_headers(worksheet: Any) -> list[Any]:
    expected_headers = [header for header, _ in SOURCE_COLUMNS]
    actual_headers = [
        worksheet.cell(row=1, column=index).value
        for index in range(1, len(SOURCE_COLUMNS) + 1)
    ]

    normalized_expected = [
        _normalize_header(header) for header in expected_headers
    ]
    normalized_actual = [
        _normalize_header(header) for header in actual_headers
    ]

    if normalized_actual != normalized_expected:
        differences = [
            {
                "column": index,
                "expected": expected_headers[index - 1],
                "actual": actual_headers[index - 1],
            }
            for index in range(1, len(SOURCE_COLUMNS) + 1)
            if normalized_actual[index - 1] != normalized_expected[index - 1]
        ]
        raise ValueError(
            f"Unexpected PSGC worksheet headers in '{worksheet.title}': "
            f"{differences}"
        )

    populated_cells = [
        cell
        for cell in worksheet._cells.values()
        if _is_populated(cell.value)
    ]
    unexpected_columns = sorted(
        {
            cell.column
            for cell in populated_cells
            if cell.column > len(SOURCE_COLUMNS)
        }
    )

    if unexpected_columns:
        raise ValueError(
            "Unexpected populated PSGC worksheet columns: "
            f"{unexpected_columns}"
        )

    return actual_headers


def _extract_cell(
    formula_cell: Cell,
    cached_cell: Cell,
    *,
    source_header: Any,
    column_index: int,
) -> dict[str, Any]:
    is_formula = formula_cell.data_type == "f"

    return {
        "column_index": column_index,
        "column_letter": get_column_letter(column_index),
        "coordinate": formula_cell.coordinate,
        "source_header": source_header,
        "field_name": SOURCE_COLUMNS[column_index - 1][1],
        "raw_value": formula_cell.value,
        "python_type": _python_type(formula_cell.value),
        "cell_data_type": formula_cell.data_type,
        "number_format": formula_cell.number_format,
        "formula_expression": formula_cell.value if is_formula else None,
        "cached_value": cached_cell.value if is_formula else None,
        "cached_python_type": (
            _python_type(cached_cell.value) if is_formula else None
        ),
        "cached_data_type": (
            cached_cell.data_type if is_formula else None
        ),
    }


def extract_psgc_records(path: str | Path) -> dict[str, Any]:
    """Extract PSGC source rows without normalizing or interpreting values.

    Formula expressions and cached results are read from complementary
    workbook loads and associated by worksheet name and cell coordinate.
    The original workbook is never saved or modified.
    """
    source_path = Path(path)

    if not source_path.is_file():
        raise FileNotFoundError(f"Workbook does not exist: {source_path}")

    if source_path.suffix.casefold() != ".xlsx":
        raise ValueError(f"Expected an .xlsx workbook: {source_path}")

    source_hash = _sha256(source_path)

    formula_workbook = load_workbook(
        filename=source_path,
        read_only=False,
        data_only=False,
    )
    cached_workbook = load_workbook(
        filename=source_path,
        read_only=False,
        data_only=True,
    )

    try:
        if PSGC_SHEET_NAME not in formula_workbook.sheetnames:
            raise ValueError(
                f"Required worksheet '{PSGC_SHEET_NAME}' was not found."
            )

        formula_sheet = formula_workbook[PSGC_SHEET_NAME]
        cached_sheet = cached_workbook[PSGC_SHEET_NAME]

        headers = _validate_headers(formula_sheet)

        populated_cells = [
            cell
            for cell in formula_sheet._cells.values()
            if _is_populated(cell.value)
        ]
        last_data_row = max(
            (cell.row for cell in populated_cells if cell.row > 1),
            default=1,
        )

        records: list[dict[str, Any]] = []

        for row_number in range(2, last_data_row + 1):
            formula_cells = [
                formula_sheet.cell(row=row_number, column=column_index)
                for column_index in range(1, len(SOURCE_COLUMNS) + 1)
            ]

            if not any(_is_populated(cell.value) for cell in formula_cells):
                continue

            cells = {}

            for column_index, formula_cell in enumerate(
                formula_cells,
                start=1,
            ):
                cached_cell = cached_sheet.cell(
                    row=row_number,
                    column=column_index,
                )

                field_name = SOURCE_COLUMNS[column_index - 1][1]
                cells[field_name] = _extract_cell(
                    formula_cell,
                    cached_cell,
                    source_header=headers[column_index - 1],
                    column_index=column_index,
                )

            records.append(
                {
                    "source_record_id": (
                        f"{source_hash[:16]}:{PSGC_SHEET_NAME}:{row_number}"
                    ),
                    "worksheet_name": PSGC_SHEET_NAME,
                    "source_row_number": row_number,
                    "cells": cells,
                }
            )

        return {
            "extraction_profile_version": EXTRACTION_PROFILE_VERSION,
            "source_artifact": {
                "filename": source_path.name,
                "size_bytes": source_path.stat().st_size,
                "sha256": source_hash,
            },
            "worksheet_name": PSGC_SHEET_NAME,
            "source_headers": headers,
            "column_mapping": [
                {
                    "column_index": index,
                    "column_letter": get_column_letter(index),
                    "source_header": header,
                    "field_name": field_name,
                }
                for index, (header, field_name) in enumerate(
                    SOURCE_COLUMNS,
                    start=1,
                )
            ],
            "record_count": len(records),
            "records": records,
        }
    finally:
        formula_workbook.close()
        cached_workbook.close()
