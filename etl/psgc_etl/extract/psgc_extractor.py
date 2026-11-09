"""Faithful extraction of source records from PSA PSGC workbooks."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.utils import get_column_letter

from psgc_etl.extract.workbook_profiler import PSGC_SHEET_NAME

EXTRACTION_PROFILE_VERSION = "2.0"


# Column positions are deliberately not hardcoded. Each profile describes
# the ordered header signature and its semantic field mapping.
SOURCE_PROFILES = {
    "psa-legacy-2024-2025": {
        "headers": (
            "10-digit PSGC",
            "Name",
            "Correspondence Code",
            "Geographic Level",
            "Old names",
            "City Class",
            "Income\nClassification",
            "Urban / Rural\n(based on 2020 CPH)",
            "2020 Population",
            None,
            "Status",
        ),
        "fields": (
            "psgc_code",
            "name",
            "correspondence_code",
            "geographic_level",
            "old_names",
            "city_class",
            "income_classification",
            "urban_rural",
            "population",
            "population_annotation",
            "source_status_value",
        ),
        "population_reference_year": 2020,
        "urban_rural_reference_year": 2020,
        "income_classification_basis": None,
    },
    "psa-2026-dof-074-2024": {
        "headers": (
            "10-digit PSGC",
            "Name",
            "Correspondence Code",
            "Geographic Level",
            "Old names",
            "City Class",
            "Income\nClassification (DOF DO No. 074.2024)",
            "Urban / Rural\n(based on 2024 CPH)",
            "2024 Population",
            None,
            "Status",
        ),
        "fields": (
            "psgc_code",
            "name",
            "correspondence_code",
            "geographic_level",
            "old_names",
            "city_class",
            "income_classification",
            "urban_rural",
            "population",
            "population_annotation",
            "source_status_value",
        ),
        "population_reference_year": 2024,
        "urban_rural_reference_year": 2024,
        "income_classification_basis": "DOF DO No. 074.2024",
    },
}


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
    return "NoneType" if value is None else type(value).__name__


def _is_populated(value: Any) -> bool:
    return value is not None and value != ""


def _detect_source_profile(worksheet: Any) -> dict[str, Any]:
    """Identify an explicitly supported contiguous header layout."""
    populated_header_columns = [
        cell.column
        for cell in worksheet._cells.values()
        if cell.row == 1 and _is_populated(cell.value)
    ]

    if not populated_header_columns:
        raise ValueError("PSGC worksheet has no populated header row.")

    for profile_id, profile in SOURCE_PROFILES.items():
        expected = [
            _normalize_header(value)
            for value in profile["headers"]
        ]
        width = len(expected)

        for start_column in range(
            min(populated_header_columns),
            max(populated_header_columns) - width + 2,
        ):
            actual = [
                _normalize_header(
                    worksheet.cell(row=1, column=start_column + offset).value
                )
                for offset in range(width)
            ]

            if actual == expected:
                return {
                    "profile_id": profile_id,
                    "definition": profile,
                    "start_column": start_column,
                    "end_column": start_column + width - 1,
                    "headers": [
                        worksheet.cell(
                            row=1,
                            column=start_column + offset,
                        ).value
                        for offset in range(width)
                    ],
                }

    raise ValueError(
        f"Unexpected PSGC worksheet headers in '{worksheet.title}'. "
        "No reviewed source profile matches the header row."
    )


def _validate_populated_columns(
    worksheet: Any,
    *,
    start_column: int,
    end_column: int,
    last_data_row: int,
) -> None:
    """Reject unexpected populated columns within the actual data region."""
    unexpected = sorted(
        {
            cell.column
            for cell in worksheet._cells.values()
            if cell.row <= last_data_row
            and _is_populated(cell.value)
            and not start_column <= cell.column <= end_column
        }
    )

    if unexpected:
        raise ValueError(
            "Unexpected populated PSGC worksheet columns within the data "
            f"region: {unexpected}"
        )


def _extract_cell(
    formula_cell: Cell,
    cached_cell: Cell,
    *,
    source_header: Any,
    field_name: str,
    column_index: int,
) -> dict[str, Any]:
    is_formula = formula_cell.data_type == "f"

    return {
        "column_index": column_index,
        "column_letter": get_column_letter(column_index),
        "coordinate": formula_cell.coordinate,
        "source_header": source_header,
        "field_name": field_name,
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


def _extract_publication_metadata(workbook: Any) -> dict[str, Any]:
    """Read release metadata without assuming all metadata cells are present."""
    if "Metadata" not in workbook.sheetnames:
        return {
            "publication_date": None,
            "publication_date_raw": None,
        }

    worksheet = workbook["Metadata"]
    values = {}

    for row in worksheet.iter_rows(
        min_row=1,
        max_row=min(worksheet.max_row, 100),
        min_col=1,
        max_col=2,
    ):
        label = row[0].value
        value = row[1].value

        if isinstance(label, str):
            values[label.strip().casefold()] = value

    raw_date = values.get("publication date:")
    publication_date = None

    if isinstance(raw_date, datetime):
        publication_date = raw_date.date().isoformat()
    elif isinstance(raw_date, str):
        try:
            publication_date = datetime.strptime(
                raw_date.strip(),
                "%d %B %Y",
            ).date().isoformat()
        except ValueError:
            publication_date = None

    return {
        "publication_date": publication_date,
        "publication_date_raw": raw_date,
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

        detected = _detect_source_profile(formula_sheet)
        start_column = detected["start_column"]
        end_column = detected["end_column"]
        headers = detected["headers"]
        profile = detected["definition"]
        fields = profile["fields"]

        # Identify data rows by their tabular structure rather than by
        # non-empty cells alone. Footnotes may occupy the PSGC-code column
        # while containing explanatory text instead of a code.
        def is_code_candidate(value: Any) -> bool:
            if isinstance(value, bool) or value is None:
                return False

            if isinstance(value, (int, float)):
                return value >= 0 and value.is_integer() if isinstance(
                    value, float
                ) else value >= 0

            return isinstance(value, str) and value.strip().isdigit()

        data_candidate_rows = set()

        for row_number in range(2, formula_sheet.max_row + 1):
            code_value = formula_sheet.cell(
                row=row_number,
                column=start_column,
            ).value

            has_other_data = any(
                _is_populated(
                    formula_sheet.cell(
                        row=row_number,
                        column=column_index,
                    ).value
                )
                for column_index in range(
                    start_column + 1,
                    end_column + 1,
                )
            )

            if is_code_candidate(code_value) or has_other_data:
                data_candidate_rows.add(row_number)

        last_data_row = max(data_candidate_rows, default=1)

        _validate_populated_columns(
            formula_sheet,
            start_column=start_column,
            end_column=end_column,
            last_data_row=last_data_row,
        )

        trailing_notes = []

        for row_number in range(last_data_row + 1, formula_sheet.max_row + 1):
            note_cells = []

            for column_index in range(1, formula_sheet.max_column + 1):
                cell = formula_sheet.cell(
                    row=row_number,
                    column=column_index,
                )

                if _is_populated(cell.value):
                    note_cells.append({
                        "coordinate": cell.coordinate,
                        "column_index": column_index,
                        "column_letter": get_column_letter(column_index),
                        "raw_value": cell.value,
                        "python_type": _python_type(cell.value),
                    })

            if note_cells:
                trailing_notes.append({
                    "source_row_number": row_number,
                    "cells": note_cells,
                })

        records: list[dict[str, Any]] = []

        for row_number in range(2, last_data_row + 1):
            formula_cells = [
                formula_sheet.cell(
                    row=row_number,
                    column=column_index,
                )
                for column_index in range(start_column, end_column + 1)
            ]

            if not any(_is_populated(cell.value) for cell in formula_cells):
                continue

            cells = {}

            for offset, formula_cell in enumerate(formula_cells):
                column_index = start_column + offset
                cached_cell = cached_sheet.cell(
                    row=row_number,
                    column=column_index,
                )
                field_name = fields[offset]

                cells[field_name] = _extract_cell(
                    formula_cell,
                    cached_cell,
                    source_header=headers[offset],
                    field_name=field_name,
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

        publication_metadata = _extract_publication_metadata(
            formula_workbook
        )

        return {
            "extraction_profile_version": EXTRACTION_PROFILE_VERSION,
            "source_profile_id": detected["profile_id"],
            "source_metadata": {
                **publication_metadata,
                "population_reference_year": profile[
                    "population_reference_year"
                ],
                "urban_rural_reference_year": profile[
                    "urban_rural_reference_year"
                ],
                "income_classification_basis": profile[
                    "income_classification_basis"
                ],
            },
            "source_artifact": {
                "filename": source_path.name,
                "size_bytes": source_path.stat().st_size,
                "sha256": source_hash,
            },
            "worksheet_name": PSGC_SHEET_NAME,
            "source_headers": headers,
            "column_mapping": [
                {
                    "column_index": start_column + offset,
                    "column_letter": get_column_letter(
                        start_column + offset
                    ),
                    "source_header": header,
                    "field_name": fields[offset],
                }
                for offset, header in enumerate(headers)
            ],
            "record_count": len(records),
            "records": records,
            "trailing_notes": trailing_notes,
        }
    finally:
        formula_workbook.close()
        cached_workbook.close()
