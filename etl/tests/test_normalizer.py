"""Tests for PSGC source-record normalization."""

from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path

import pytest

from psgc_etl.extract import extract_psgc_records
from psgc_etl.transform import normalize_psgc_records


def _cell(
    value,
    *,
    data_type="n",
    cached_value=None,
    cached_data_type=None,
):
    return {
        "raw_value": value,
        "cell_data_type": data_type,
        "cached_value": cached_value,
        "cached_data_type": cached_data_type,
    }


def _extraction(cells):
    return {
        "source_artifact": {
            "filename": "fixture.xlsx",
            "size_bytes": 100,
            "sha256": "fixture-hash",
        },
        "worksheet_name": "PSGC",
        "source_headers": [],
        "column_mapping": [],
        "records": [
            {
                "source_record_id": "fixture:PSGC:2",
                "worksheet_name": "PSGC",
                "source_row_number": 2,
                "cells": cells,
            }
        ],
    }


def test_numeric_identifiers_become_decimal_free_strings() -> None:
    extraction = _extraction(
        {
            "psgc_code": _cell(100100001),
            "correspondence_code": _cell(1001),
        }
    )

    result = normalize_psgc_records(extraction)
    cells = result["records"][0]["cells"]

    assert cells["psgc_code"]["normalized_value"] == "100100001"
    assert (
        cells["psgc_code"]["normalization_action"]
        == "NUMERIC_INTEGER_TO_STRING"
    )
    assert cells["correspondence_code"]["normalized_value"] == "1001"


def test_existing_identifier_strings_are_not_modified() -> None:
    extraction = _extraction(
        {
            "psgc_code": _cell("0100100001", data_type="s"),
            "correspondence_code": _cell("001001", data_type="s"),
        }
    )

    result = normalize_psgc_records(extraction)
    cells = result["records"][0]["cells"]

    assert cells["psgc_code"]["normalized_value"] == "0100100001"
    assert cells["correspondence_code"]["normalized_value"] == "001001"
    assert cells["psgc_code"]["normalization_action"] == "PASSTHROUGH"


def test_missing_correspondence_remains_none() -> None:
    extraction = _extraction(
        {
            "correspondence_code": _cell(None, data_type="n"),
        }
    )

    result = normalize_psgc_records(extraction)
    cell = result["records"][0]["cells"]["correspondence_code"]

    assert cell["raw_value"] is None
    assert cell["normalized_value"] is None
    assert cell["normalization_action"] == "SOURCE_BLANK"


def test_population_missing_marker_becomes_none_without_losing_raw_value() -> None:
    extraction = _extraction(
        {
            "population": _cell("-", data_type="s"),
        }
    )

    result = normalize_psgc_records(extraction)
    cell = result["records"][0]["cells"]["population"]

    assert cell["raw_value"] == "-"
    assert cell["normalized_value"] is None
    assert cell["normalization_action"] == "MISSING_MARKER"


def test_formula_population_uses_cached_value() -> None:
    extraction = _extraction(
        {
            "population": _cell(
                "=10000+2345",
                data_type="f",
                cached_value=12345,
                cached_data_type="n",
            )
        }
    )

    result = normalize_psgc_records(extraction)
    cell = result["records"][0]["cells"]["population"]

    assert cell["raw_value"] == "=10000+2345"
    assert cell["cached_value"] == 12345
    assert cell["normalized_value"] == 12345
    assert cell["normalization_action"] == "FORMULA_CACHED_NUMERIC"
    assert cell["normalized_value_origin"] == "FORMULA_CACHE"


def test_formula_without_cached_value_remains_unresolved() -> None:
    extraction = _extraction(
        {
            "population": _cell(
                "=10000+2345",
                data_type="f",
                cached_value=None,
            )
        }
    )

    result = normalize_psgc_records(extraction)
    cell = result["records"][0]["cells"]["population"]

    assert cell["raw_value"] == "=10000+2345"
    assert cell["normalized_value"] is None
    assert cell["normalization_action"] == "FORMULA_CACHE_MISSING"


def test_other_fields_are_passed_through_without_interpretation() -> None:
    extraction = _extraction(
        {
            "name": _cell("  Example Barangay  ", data_type="s"),
            "income_classification": _cell("1st* (reclass 2005)", data_type="s"),
            "urban_rural": _cell("-", data_type="s"),
            "population_annotation": _cell("17/", data_type="s"),
            "source_status_value": _cell("Pob.", data_type="s"),
        }
    )

    result = normalize_psgc_records(extraction)
    cells = result["records"][0]["cells"]

    assert cells["name"]["normalized_value"] == "  Example Barangay  "
    assert (
        cells["income_classification"]["normalized_value"]
        == "1st* (reclass 2005)"
    )
    assert cells["urban_rural"]["normalized_value"] == "-"
    assert cells["population_annotation"]["normalized_value"] == "17/"
    assert cells["source_status_value"]["normalized_value"] == "Pob."


def test_normalization_does_not_modify_extraction_input() -> None:
    extraction = _extraction(
        {
            "psgc_code": _cell(100100001),
            "population": _cell("-"),
        }
    )
    original = deepcopy(extraction)

    normalize_psgc_records(extraction)

    assert extraction == original


def test_normalizes_real_workbook_formula_cache() -> None:
    source = Path("data/source/psa/PSGC-1Q-2025-Publication-Datafile.xlsx")
    if not source.is_file():
        pytest.skip("PSA source workbook is not present in this checkout")

    extraction = extract_psgc_records(source)
    result = normalize_psgc_records(extraction)

    formula_record = next(
        record
        for record in result["records"]
        if record["cells"]["population"]["cell_data_type"] == "f"
    )
    population = formula_record["cells"]["population"]

    assert population["raw_value"].startswith("=")
    assert population["cached_value"] == 723758
    assert population["normalized_value"] == 723758
    assert population["normalized_value_origin"] == "FORMULA_CACHE"


@pytest.mark.parametrize(
    "value",
    [
        -1,
        -1.0,
        1.5,
        float("nan"),
        float("inf"),
        True,
        2**53,
    ],
)
def test_invalid_numeric_identifiers_require_review(value) -> None:
    extraction = _extraction({"psgc_code": _cell(value)})

    result = normalize_psgc_records(extraction)
    cell = result["records"][0]["cells"]["psgc_code"]

    if isinstance(value, float) and math.isnan(value):
        assert math.isnan(cell["raw_value"])
    else:
        assert cell["raw_value"] == value
    assert cell["normalized_value"] is None
    assert cell["normalization_status"] == "REVIEW"


@pytest.mark.parametrize(
    "value",
    [
        -1,
        -1.0,
        1.5,
        float("nan"),
        float("inf"),
        True,
        "not-a-population",
        2**53,
    ],
)
def test_invalid_population_values_require_review(value) -> None:
    extraction = _extraction({"population": _cell(value)})

    result = normalize_psgc_records(extraction)
    cell = result["records"][0]["cells"]["population"]

    if isinstance(value, float) and math.isnan(value):
        assert math.isnan(cell["raw_value"])
    else:
        assert cell["raw_value"] == value
    assert cell["normalized_value"] is None
    assert cell["normalization_status"] == "REVIEW"


def test_formula_with_invalid_cached_population_requires_review() -> None:
    extraction = _extraction(
        {
            "population": _cell(
                "=10000+2345",
                data_type="f",
                cached_value=-1,
                cached_data_type="n",
            )
        }
    )

    result = normalize_psgc_records(extraction)
    cell = result["records"][0]["cells"]["population"]

    assert cell["raw_value"] == "=10000+2345"
    assert cell["cached_value"] == -1
    assert cell["normalized_value"] is None
    assert cell["normalization_status"] == "REVIEW"
    assert cell["normalized_value_origin"] == "FORMULA_CACHE"


def test_missing_formula_cache_is_review_not_source_missing() -> None:
    extraction = _extraction(
        {
            "population": _cell(
                "=10000+2345",
                data_type="f",
                cached_value=None,
            )
        }
    )

    result = normalize_psgc_records(extraction)
    cell = result["records"][0]["cells"]["population"]

    assert cell["normalization_action"] == "FORMULA_CACHE_MISSING"
    assert cell["normalization_status"] == "REVIEW"


def test_literal_source_blank_is_missing() -> None:
    extraction = _extraction({"population": _cell(None)})

    result = normalize_psgc_records(extraction)
    cell = result["records"][0]["cells"]["population"]

    assert cell["normalization_action"] == "SOURCE_BLANK"
    assert cell["normalization_status"] == "MISSING"


def test_valid_numeric_population_is_marked_valid() -> None:
    extraction = _extraction({"population": _cell(12345)})

    result = normalize_psgc_records(extraction)
    cell = result["records"][0]["cells"]["population"]

    assert cell["normalized_value"] == 12345
    assert cell["normalization_status"] == "VALID"


def test_documented_2026_isabela_population_error_is_adapted() -> None:
    extraction = _extraction(
        {
            "psgc_code": _cell("0990100000", data_type="s"),
            "population": _cell("#N/A", data_type="e"),
        }
    )
    extraction["source_profile_id"] = "psa-2026-dof-074-2024"
    extraction["source_metadata"] = {
        "population_reference_year": 2024,
    }
    extraction["extraction_profile_version"] = "2.0"
    extraction["trailing_notes"] = []

    result = normalize_psgc_records(extraction)
    population = result["records"][0]["cells"]["population"]

    assert population["raw_value"] == "#N/A"
    assert population["cell_data_type"] == "e"
    assert population["normalized_value"] is None
    assert population["normalization_action"] == "KNOWN_SOURCE_ERROR_AS_MISSING"
    assert population["normalization_status"] == "REVIEW"
    assert "1Q 2024" in population["normalization_rationale"]
    assert result["source_profile_id"] == "psa-2026-dof-074-2024"
    assert result["source_metadata"]["population_reference_year"] == 2024
    assert result["extraction_profile_version"] == "2.0"


def test_unrelated_excel_population_error_is_not_adapted() -> None:
    extraction = _extraction(
        {
            "psgc_code": _cell("0100100001", data_type="s"),
            "population": _cell("#N/A", data_type="e"),
        }
    )
    extraction["source_profile_id"] = "psa-2026-dof-074-2024"

    result = normalize_psgc_records(extraction)
    population = result["records"][0]["cells"]["population"]

    assert population["raw_value"] == "#N/A"
    assert population["normalized_value"] is None
    assert population["normalization_action"] == "UNSUPPORTED_POPULATION_VALUE"
    assert population["normalization_status"] == "REVIEW"


def test_isabela_exception_is_not_applied_to_another_source_profile() -> None:
    extraction = _extraction(
        {
            "psgc_code": _cell("0990100000", data_type="s"),
            "population": _cell("#N/A", data_type="e"),
        }
    )
    extraction["source_profile_id"] = "psa-legacy-2024-2025"

    result = normalize_psgc_records(extraction)
    population = result["records"][0]["cells"]["population"]

    assert population["normalization_action"] == "UNSUPPORTED_POPULATION_VALUE"
