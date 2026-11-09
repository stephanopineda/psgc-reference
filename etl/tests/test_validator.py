"""Tests for deterministic PSGC source-record validation."""

from __future__ import annotations

from copy import deepcopy

from psgc_etl.validate import validate_psgc_records


def _cell(
    raw_value,
    normalized_value,
    *,
    python_type="str",
    cell_data_type="s",
    normalization_status="VALID",
    normalization_action="PASSTHROUGH",
    coordinate=None,
):
    return {
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "python_type": python_type,
        "cell_data_type": cell_data_type,
        "normalization_status": normalization_status,
        "normalization_action": normalization_action,
        "coordinate": coordinate,
    }


def _record(
    row_number=2,
    *,
    psgc_code="0100100001",
    correspondence_code=None,
    name="Example Barangay",
    geographic_level="Bgy",
    population=12345,
):
    return {
        "source_record_id": f"fixture:PSGC:{row_number}",
        "worksheet_name": "PSGC",
        "source_row_number": row_number,
        "cells": {
            "psgc_code": _cell(
                psgc_code,
                psgc_code,
                python_type="str",
                coordinate=f"A{row_number}",
            ),
            "name": _cell(
                name,
                name,
                coordinate=f"B{row_number}",
            ),
            "correspondence_code": _cell(
                correspondence_code,
                correspondence_code,
                coordinate=f"C{row_number}",
            ),
            "geographic_level": _cell(
                geographic_level,
                geographic_level,
                coordinate=f"D{row_number}",
            ),
            "population": _cell(
                population,
                population,
                python_type="int",
                cell_data_type="n",
                coordinate=f"I{row_number}",
            ),
        },
    }


def _normalized(records):
    return {
        "normalization_profile_version": "1.1",
        "source_artifact": {
            "filename": "fixture.xlsx",
            "size_bytes": 100,
            "sha256": "fixture-hash",
        },
        "worksheet_name": "PSGC",
        "records": records,
    }


def test_valid_record_has_no_findings() -> None:
    result = validate_psgc_records(_normalized([_record()]))

    assert result["finding_count"] == 0
    assert result["severity_counts"] == {
        "ERROR": 0,
        "REVIEW": 0,
        "WARNING": 0,
    }


def test_missing_correspondence_code_is_not_a_finding() -> None:
    result = validate_psgc_records(
        _normalized([_record(correspondence_code=None)])
    )

    assert result["finding_count"] == 0


def test_missing_psgc_code_is_an_error() -> None:
    result = validate_psgc_records(
        _normalized([_record(psgc_code=None)])
    )

    assert [(item["rule_id"], item["severity"]) for item in result["findings"]] == [
        ("PSGC001", "ERROR")
    ]


def test_invalid_psgc_code_format_is_an_error() -> None:
    result = validate_psgc_records(
        _normalized([_record(psgc_code="12345")])
    )

    assert [(item["rule_id"], item["severity"]) for item in result["findings"]] == [
        ("PSGC002", "ERROR")
    ]


def test_historical_code_length_can_be_selected_explicitly() -> None:
    result = validate_psgc_records(
        _normalized([_record(psgc_code="123456789")]),
        psgc_code_length=9,
    )

    assert result["finding_count"] == 0


def test_duplicate_psgc_codes_flag_every_occurrence() -> None:
    result = validate_psgc_records(
        _normalized(
            [
                _record(row_number=2),
                _record(row_number=3),
            ]
        )
    )

    findings = [
        item for item in result["findings"] if item["rule_id"] == "PSGC003"
    ]

    assert len(findings) == 2
    assert {item["source_row_number"] for item in findings} == {2, 3}


def test_missing_name_is_an_error() -> None:
    result = validate_psgc_records(
        _normalized([_record(name="   ")])
    )

    assert any(
        item["rule_id"] == "PSGC004"
        and item["severity"] == "ERROR"
        for item in result["findings"]
    )


def test_invalid_population_is_an_error() -> None:
    record = _record()
    record["cells"]["population"].update(
        {
            "raw_value": -1,
            "normalized_value": None,
            "normalization_status": "REVIEW",
            "normalization_action": "UNSUPPORTED_POPULATION_VALUE",
        }
    )

    result = validate_psgc_records(_normalized([record]))

    assert any(
        item["rule_id"] == "PSGC005"
        and item["severity"] == "ERROR"
        for item in result["findings"]
    )


def test_missing_formula_cache_requires_review() -> None:
    record = _record()
    record["cells"]["population"].update(
        {
            "raw_value": "=10000+2345",
            "normalized_value": None,
            "normalization_status": "REVIEW",
            "normalization_action": "FORMULA_CACHE_MISSING",
        }
    )

    result = validate_psgc_records(_normalized([record]))

    assert any(
        item["rule_id"] == "PSGC006"
        and item["severity"] == "REVIEW"
        for item in result["findings"]
    )


def test_duplicate_correspondence_codes_require_review() -> None:
    result = validate_psgc_records(
        _normalized(
            [
                _record(row_number=2, correspondence_code="001001"),
                _record(row_number=3, correspondence_code="001001"),
            ]
        )
    )

    findings = [
        item for item in result["findings"] if item["rule_id"] == "PSGC007"
    ]

    assert len(findings) == 2
    assert all(item["severity"] == "REVIEW" for item in findings)


def test_unknown_geographic_level_requires_review() -> None:
    result = validate_psgc_records(
        _normalized([_record(geographic_level="UnknownLevel")])
    )

    assert any(
        item["rule_id"] == "PSGC008"
        and item["severity"] == "REVIEW"
        for item in result["findings"]
    )


def test_null_geographic_level_is_allowed() -> None:
    result = validate_psgc_records(
        _normalized([_record(geographic_level=None)])
    )

    assert result["finding_count"] == 0


def test_numeric_psgc_source_cell_generates_warning() -> None:
    record = _record()
    record["cells"]["psgc_code"].update(
        {
            "raw_value": 100100001,
            "normalized_value": "100100001",
            "python_type": "int",
            "cell_data_type": "n",
        }
    )

    result = validate_psgc_records(_normalized([record]))

    assert any(
        item["rule_id"] == "PSGC009"
        and item["severity"] == "WARNING"
        for item in result["findings"]
    )


def test_numeric_correspondence_source_cell_is_counted_without_warning() -> None:
    record = _record(correspondence_code="1001")
    record["cells"]["correspondence_code"].update(
        {
            "raw_value": 1001,
            "normalized_value": "1001",
            "python_type": "int",
            "cell_data_type": "n",
        }
    )

    result = validate_psgc_records(_normalized([record]))

    assert not any(
        item["field_name"] == "correspondence_code"
        and item["severity"] == "WARNING"
        for item in result["findings"]
    )
    assert result["source_representation_counts"]["correspondence_code"] == {
        "numeric": 1,
        "text": 0,
        "blank": 0,
        "other": 0,
    }


def test_numeric_psgc_source_cell_is_counted_and_warned() -> None:
    record = _record(psgc_code="1001000001")
    record["cells"]["psgc_code"].update(
        {
            "raw_value": 1001000001,
            "normalized_value": "1001000001",
            "python_type": "int",
            "cell_data_type": "n",
        }
    )

    result = validate_psgc_records(_normalized([record]))

    assert any(
        item["rule_id"] == "PSGC009"
        and item["severity"] == "WARNING"
        for item in result["findings"]
    )
    assert result["source_representation_counts"]["psgc_code"] == {
        "numeric": 1,
        "text": 0,
        "blank": 0,
        "other": 0,
    }


def test_validation_does_not_modify_normalized_input() -> None:
    normalized = _normalized(
        [
            _record(),
            _record(row_number=3, psgc_code="invalid"),
        ]
    )
    original = deepcopy(normalized)

    validate_psgc_records(normalized)

    assert normalized == original


def test_invalid_code_length_configuration_is_rejected() -> None:
    normalized = _normalized([_record()])

    try:
        validate_psgc_records(normalized, psgc_code_length=0)
    except ValueError as error:
        assert "positive integer" in str(error)
    else:
        raise AssertionError("Expected ValueError for invalid code length")


def test_documented_source_population_exception_requires_review() -> None:
    record = _record(psgc_code="0990100000", population=None)
    record["cells"]["population"].update(
        {
            "raw_value": "#N/A",
            "normalized_value": None,
            "cell_data_type": "e",
            "normalization_status": "REVIEW",
            "normalization_action": "KNOWN_SOURCE_ERROR_AS_MISSING",
            "normalization_rationale": "Documented source-specific exception.",
        }
    )

    result = validate_psgc_records(_normalized([record]))

    findings = [
        item for item in result["findings"] if item["rule_id"] == "PSGC011"
    ]
    assert len(findings) == 1
    assert findings[0]["severity"] == "REVIEW"
    assert findings[0]["source_value"] == "'#N/A'"
    assert findings[0]["normalized_value"] is None
    assert findings[0]["message"] == "Documented source-specific exception."


def test_unrecognized_population_error_remains_psgc005() -> None:
    record = _record()
    record["cells"]["population"].update(
        {
            "raw_value": "#N/A",
            "normalized_value": None,
            "cell_data_type": "e",
            "normalization_status": "REVIEW",
            "normalization_action": "UNSUPPORTED_POPULATION_VALUE",
        }
    )

    result = validate_psgc_records(_normalized([record]))

    assert any(
        item["rule_id"] == "PSGC005" and item["severity"] == "ERROR"
        for item in result["findings"]
    )
    assert not any(item["rule_id"] == "PSGC011" for item in result["findings"])
