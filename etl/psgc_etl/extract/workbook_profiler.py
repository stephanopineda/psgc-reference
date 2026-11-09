"""Read-only profiling of PSA PSGC publication workbooks."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

PROFILE_VERSION = "1.0"

PSGC_SHEET_NAME = "PSGC"


def _is_blank(value: Any) -> bool:
    return value is None or value == ""


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _value_key(value: Any) -> str:
    """Return a type-aware key for counting distinct cell values."""
    return json.dumps(
        {
            "type": type(value).__name__,
            "value": _json_value(value),
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def _normalized_header(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"\s+", " ", value).strip().casefold()
    return normalized or None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _profile_sheet(worksheet: Worksheet) -> dict[str, Any]:
    max_row = worksheet.max_row or 0
    declared_max_column = worksheet.max_column or 0

    # OpenPyXL's populated-cell registry avoids scanning large ranges that
    # contain only formatting. It is intentionally used here because PSA
    # workbooks may declare dimensions larger than their actual data.
    populated_cells = [
        cell
        for cell in worksheet._cells.values()
        if not _is_blank(cell.value)
    ]

    actual_max_column = max(
        (cell.column for cell in populated_cells),
        default=0,
    )
    max_column = actual_max_column

    header_cells = {
        cell.column: cell.value
        for cell in populated_cells
        if cell.row == 1
    }
    headers = [
        _json_value(header_cells.get(column))
        for column in range(1, max_column + 1)
    ]

    column_counters: list[Counter[str]] = [
        Counter() for _ in range(max_column)
    ]
    column_values: list[dict[str, Any]] = [
        {} for _ in range(max_column)
    ]
    column_types: list[Counter[str]] = [
        Counter() for _ in range(max_column)
    ]
    column_samples: list[list[Any]] = [
        [] for _ in range(max_column)
    ]
    column_sample_keys: list[set[str]] = [
        set() for _ in range(max_column)
    ]

    data_rows: set[int] = set()
    min_row: int | None = None
    max_non_empty_row: int | None = None
    min_column: int | None = None
    max_non_empty_column: int | None = None
    formula_count = 0

    for cell in populated_cells:
        min_row = cell.row if min_row is None else min(min_row, cell.row)
        max_non_empty_row = (
            cell.row
            if max_non_empty_row is None
            else max(max_non_empty_row, cell.row)
        )
        min_column = (
            cell.column
            if min_column is None
            else min(min_column, cell.column)
        )
        max_non_empty_column = (
            cell.column
            if max_non_empty_column is None
            else max(max_non_empty_column, cell.column)
        )

        if cell.row == 1:
            continue

        data_rows.add(cell.row)
        index = cell.column - 1
        column_types[index][cell.data_type] += 1

        key = _value_key(cell.value)
        column_counters[index][key] += 1
        column_values[index][key] = _json_value(cell.value)

        if (
            len(column_samples[index]) < 5
            and key not in column_sample_keys[index]
        ):
            column_samples[index].append(_json_value(cell.value))
            column_sample_keys[index].add(key)

        if cell.data_type == "f":
            formula_count += 1

    non_empty_rows = len(data_rows)
    data_row_span = (
        max(max(data_rows) - 1, 0)
        if data_rows
        else 0
    )

    column_statistics: list[dict[str, Any]] = []

    for index in range(max_column):
        counts = column_counters[index]
        distinct_count = len(counts)
        non_empty_count = sum(counts.values())

        statistics: dict[str, Any] = {
            "column_index": index + 1,
            "header": headers[index],
            "non_empty_count": non_empty_count,
            "blank_count": non_empty_rows - non_empty_count,
            "distinct_count": distinct_count,
            "duplicate_value_count": sum(
                1 for count in counts.values() if count > 1
            ),
            "duplicate_excess_count": sum(
                count - 1 for count in counts.values() if count > 1
            ),
            "cell_data_type_counts": dict(
                sorted(column_types[index].items())
            ),
            "sample_values": column_samples[index],
        }

        if distinct_count <= 50:
            statistics["value_counts"] = [
                {
                    "value": column_values[index][key],
                    "count": count,
                }
                for key, count in counts.most_common()
            ]

        column_statistics.append(statistics)

    normalized_headers = [
        _normalized_header(header)
        for header in headers
    ]
    duplicate_headers = sorted(
        {
            header
            for header in normalized_headers
            if header is not None and normalized_headers.count(header) > 1
        }
    )

    return {
        "sheet_name": worksheet.title,
        "sheet_state": worksheet.sheet_state,
        "declared_dimensions": {
            "max_row": max_row,
            "max_column": declared_max_column,
        },
        "actual_non_empty_bounds": (
            {
                "min_row": min_row,
                "max_row": max_non_empty_row,
                "min_column": min_column,
                "max_column": max_non_empty_column,
            }
            if min_row is not None
            else None
        ),
        "header_row": headers,
        "duplicate_headers": duplicate_headers,
        "data_row_span": data_row_span,
        "non_empty_data_rows": non_empty_rows,
        "merged_range_count": len(worksheet.merged_cells.ranges),
        "formula_count": formula_count,
        "column_statistics": column_statistics,
    }


def _find_column(
    sheet_profile: dict[str, Any],
    expected_header: str,
) -> dict[str, Any] | None:
    expected = _normalized_header(expected_header)

    for column in sheet_profile["column_statistics"]:
        if _normalized_header(column["header"]) == expected:
            return column

    return None


def _psgc_summary(sheet_profile: dict[str, Any]) -> dict[str, Any]:
    psgc_column = _find_column(sheet_profile, "10-digit PSGC")
    correspondence_column = _find_column(
        sheet_profile,
        "Correspondence Code",
    )
    geographic_level_column = _find_column(
        sheet_profile,
        "Geographic Level",
    )

    return {
        "missing_psgc_count": (
            psgc_column["blank_count"] if psgc_column else None
        ),
        "duplicate_psgc_value_count": (
            psgc_column["duplicate_value_count"] if psgc_column else None
        ),
        "duplicate_psgc_excess_count": (
            psgc_column["duplicate_excess_count"] if psgc_column else None
        ),
        "missing_correspondence_code_count": (
            correspondence_column["blank_count"]
            if correspondence_column
            else None
        ),
        "duplicate_correspondence_value_count": (
            correspondence_column["duplicate_value_count"]
            if correspondence_column
            else None
        ),
        "geographic_level_distribution": (
            geographic_level_column.get("value_counts")
            if geographic_level_column
            else None
        ),
    }


def profile_workbook(path: str | Path) -> dict[str, Any]:
    """Inspect one workbook without modifying it."""
    source_path = Path(path)

    if not source_path.is_file():
        raise FileNotFoundError(f"Workbook does not exist: {source_path}")

    if source_path.suffix.casefold() != ".xlsx":
        raise ValueError(f"Expected an .xlsx workbook: {source_path}")

    workbook = load_workbook(
        filename=source_path,
        read_only=False,
        data_only=False,
    )

    try:
        sheets = [
            _profile_sheet(workbook[sheet_name])
            for sheet_name in workbook.sheetnames
        ]

        psgc_sheet = next(
            (
                sheet
                for sheet in sheets
                if sheet["sheet_name"] == PSGC_SHEET_NAME
            ),
            None,
        )

        return {
            "profile_version": PROFILE_VERSION,
            "source": {
                "filename": source_path.name,
                "size_bytes": source_path.stat().st_size,
                "sha256": _sha256(source_path),
            },
            "workbook": {
                "sheet_names": workbook.sheetnames,
                "properties": {
                    "creator": workbook.properties.creator,
                    "title": workbook.properties.title,
                    "subject": workbook.properties.subject,
                },
            },
            "sheet_inventory": {
                "visible": [
                    sheet["sheet_name"]
                    for sheet in sheets
                    if sheet["sheet_state"] == "visible"
                ],
                "hidden": [
                    sheet["sheet_name"]
                    for sheet in sheets
                    if sheet["sheet_state"] == "hidden"
                ],
                "very_hidden": [
                    sheet["sheet_name"]
                    for sheet in sheets
                    if sheet["sheet_state"] == "veryHidden"
                ],
                "empty": [
                    sheet["sheet_name"]
                    for sheet in sheets
                    if sheet["non_empty_data_rows"] == 0
                ],
            },
            "sheets": sheets,
            "psgc_summary": (
                _psgc_summary(psgc_sheet) if psgc_sheet else None
            ),
            "warnings": (
                []
                if psgc_sheet
                else [f"Required worksheet '{PSGC_SHEET_NAME}' was not found."]
            ),
        }
    finally:
        workbook.close()


def compare_workbook_schemas(
    profiles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare required data schemas separately from workbook inventory."""
    if len(profiles) < 2:
        return []

    required_sheets = {PSGC_SHEET_NAME}
    reference = profiles[0]
    reference_sheets = {
        sheet["sheet_name"]: sheet
        for sheet in reference["sheets"]
    }
    comparisons: list[dict[str, Any]] = []

    for candidate in profiles[1:]:
        candidate_sheets = {
            sheet["sheet_name"]: sheet
            for sheet in candidate["sheets"]
        }

        common_sheet_names = sorted(
            set(reference_sheets) & set(candidate_sheets)
        )

        header_differences = []
        required_header_differences = []
        visibility_differences = []

        for sheet_name in common_sheet_names:
            reference_sheet = reference_sheets[sheet_name]
            candidate_sheet = candidate_sheets[sheet_name]

            reference_headers = reference_sheet["header_row"]
            candidate_headers = candidate_sheet["header_row"]

            if reference_headers != candidate_headers:
                difference = {
                    "sheet_name": sheet_name,
                    "reference_headers": reference_headers,
                    "candidate_headers": candidate_headers,
                }
                header_differences.append(difference)

                if sheet_name in required_sheets:
                    required_header_differences.append(difference)

            if (
                reference_sheet["sheet_state"]
                != candidate_sheet["sheet_state"]
            ):
                visibility_differences.append(
                    {
                        "sheet_name": sheet_name,
                        "reference_state": reference_sheet["sheet_state"],
                        "candidate_state": candidate_sheet["sheet_state"],
                    }
                )

        reference_only = sorted(
            set(reference_sheets) - set(candidate_sheets)
        )
        candidate_only = sorted(
            set(candidate_sheets) - set(reference_sheets)
        )

        missing_required_in_candidate = sorted(
            required_sheets - set(candidate_sheets)
        )
        missing_required_in_reference = sorted(
            required_sheets - set(reference_sheets)
        )

        supplementary_reference_only = sorted(
            set(reference_only) - required_sheets
        )
        supplementary_candidate_only = sorted(
            set(candidate_only) - required_sheets
        )

        core_schema_compatible = (
            not missing_required_in_candidate
            and not missing_required_in_reference
            and not required_header_differences
        )

        comparisons.append(
            {
                "reference_file": reference["source"]["filename"],
                "candidate_file": candidate["source"]["filename"],
                "required_sheet_differences": {
                    "missing_in_reference": missing_required_in_reference,
                    "missing_in_candidate": missing_required_in_candidate,
                },
                "required_header_differences": required_header_differences,
                "header_differences": header_differences,
                "visibility_differences": visibility_differences,
                "supplementary_sheet_differences": {
                    "reference_only": supplementary_reference_only,
                    "candidate_only": supplementary_candidate_only,
                },
                "core_schema_compatible": core_schema_compatible,
            }
        )

    return comparisons
