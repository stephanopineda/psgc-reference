"""Tests for faithful extraction of PSGC source records."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from openpyxl import Workbook

from psgc_etl.extract import extract_psgc_records

HEADERS = [
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
]


def _create_workbook(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "PSGC"
    worksheet.append(HEADERS)

    worksheet.append(
        [
            "0100100001",
            "Barangay A",
            1001,
            "Bgy",
            None,
            None,
            "1st",
            "U",
            12345,
            "17/",
            None,
        ]
    )

    worksheet.append(
        [
            "0100100002",
            "Barangay B",
            None,
            "Bgy",
            None,
            None,
            None,
            "R",
            "=10000+2345",
            "(excluding BAGUIO CITY)",
            "Pob.",
        ]
    )

    # A completely empty row must not become a source record.
    worksheet.append([None] * len(HEADERS))

    # Formatting alone must not create a source record.
    worksheet["A1000"].number_format = "@"

    workbook.save(path)
    workbook.close()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_extracts_source_records_and_preserves_all_columns(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.xlsx"
    _create_workbook(source)

    result = extract_psgc_records(source)

    assert result["record_count"] == 2
    assert result["worksheet_name"] == "PSGC"
    assert result["source_headers"] == HEADERS
    assert len(result["column_mapping"]) == 11

    first, second = result["records"]

    assert first["source_row_number"] == 2
    assert second["source_row_number"] == 3

    assert len(first["cells"]) == 11
    assert first["cells"]["psgc_code"]["raw_value"] == "0100100001"
    assert first["cells"]["correspondence_code"]["raw_value"] == 1001
    assert first["cells"]["population"]["raw_value"] == 12345
    assert (
        first["cells"]["population_annotation"]["raw_value"]
        == "17/"
    )

    assert (
        first["cells"]["population_annotation"]["source_header"]
        is None
    )

    # Empty cells remain represented rather than disappearing.
    assert first["cells"]["old_names"]["raw_value"] is None
    assert first["cells"]["old_names"]["coordinate"] == "E2"

    assert second["cells"]["source_status_value"]["raw_value"] == "Pob."


def test_formula_expression_and_missing_cached_result_are_preserved(
    tmp_path: Path,
) -> None:
    source = tmp_path / "formula.xlsx"
    _create_workbook(source)

    result = extract_psgc_records(source)
    population = result["records"][1]["cells"]["population"]

    assert population["raw_value"] == "=10000+2345"
    assert population["cell_data_type"] == "f"
    assert population["formula_expression"] == "=10000+2345"
    assert population["cached_value"] is None
    assert population["cached_python_type"] == "NoneType"


def test_extraction_does_not_modify_source_workbook(
    tmp_path: Path,
) -> None:
    source = tmp_path / "immutable.xlsx"
    _create_workbook(source)
    original_hash = _file_hash(source)

    extract_psgc_records(source)

    assert _file_hash(source) == original_hash


def test_rejects_unexpected_header_mapping(tmp_path: Path) -> None:
    source = tmp_path / "unexpected-header.xlsx"
    _create_workbook(source)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "PSGC"
    altered_headers = HEADERS.copy()
    altered_headers[2] = "Old Correspondence Code"
    worksheet.append(altered_headers)
    workbook.save(source)
    workbook.close()

    with pytest.raises(ValueError, match="Unexpected PSGC worksheet headers"):
        extract_psgc_records(source)


def test_rejects_unexpected_populated_column(tmp_path: Path) -> None:
    source = tmp_path / "unexpected-column.xlsx"
    _create_workbook(source)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "PSGC"
    worksheet.append(HEADERS)
    worksheet.append(["0100100001", "Barangay A"])
    worksheet["L2"] = "Unexpected value"
    workbook.save(source)
    workbook.close()

    with pytest.raises(ValueError, match="Unexpected populated PSGC worksheet columns"):
        extract_psgc_records(source)


def test_rejects_workbook_without_psgc_sheet(tmp_path: Path) -> None:
    source = tmp_path / "missing-psgc.xlsx"
    workbook = Workbook()
    workbook.active.title = "Metadata"
    workbook.save(source)
    workbook.close()

    with pytest.raises(ValueError, match="Required worksheet 'PSGC'"):
        extract_psgc_records(source)
