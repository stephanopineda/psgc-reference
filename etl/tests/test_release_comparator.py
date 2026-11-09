"""Tests for deterministic PSGC release comparison."""

from copy import deepcopy

import pytest

from psgc_etl.compare import compare_normalized_releases


def make_cell(
    value,
    *,
    raw_value=None,
    coordinate="A2",
    status="VALID",
    action="PASSTHROUGH",
):
    return {
        "normalized_value": value,
        "raw_value": value if raw_value is None else raw_value,
        "normalization_status": status,
        "normalization_action": action,
        "coordinate": coordinate,
    }


def make_record(
    code,
    *,
    name="Sample",
    correspondence="123456789",
    population=100,
    row=2,
):
    fields = {
        "psgc_code": code,
        "name": name,
        "correspondence_code": correspondence,
        "geographic_level": "Bgy",
        "old_names": None,
        "city_class": None,
        "income_classification": None,
        "urban_rural": "R",
        "population": population,
        "population_annotation": None,
        "source_status_value": None,
    }

    return {
        "source_record_id": f"source:{row}",
        "worksheet_name": "PSGC",
        "source_row_number": row,
        "cells": {
            field: make_cell(value, coordinate=f"A{row}")
            for field, value in fields.items()
        },
    }


def make_release(*records, filename="source.xlsx"):
    return {
        "normalization_profile_version": "1.1",
        "source_artifact": {
            "filename": filename,
            "sha256": f"hash-{filename}",
        },
        "worksheet_name": "PSGC",
        "record_count": len(records),
        "records": list(records),
    }


def test_identical_releases_have_no_changes():
    record = make_record("0100100010")

    result = compare_normalized_releases(
        make_release(record),
        make_release(deepcopy(record)),
    )

    assert result["summary"] == {
        "previous_record_count": 1,
        "current_record_count": 1,
        "matched_count": 1,
        "unchanged_count": 1,
        "changed_count": 0,
        "added_count": 0,
        "removed_count": 0,
        "candidate_group_count": 0,
    }


def test_attribute_change_is_reported_with_source_values():
    previous = make_record("0100100010", name="Old Name")
    current = make_record("0100100010", name="New Name", row=3)

    result = compare_normalized_releases(
        make_release(previous),
        make_release(current),
    )

    assert result["summary"]["changed_count"] == 1

    change = result["changed_records"][0]["changes"][0]

    assert change["field_name"] == "name"
    assert change["before"]["normalized_value"] == "Old Name"
    assert change["after"]["normalized_value"] == "New Name"
    assert change["before"]["source_coordinate"] == "A2"
    assert change["after"]["source_coordinate"] == "A3"


def test_added_and_removed_records_are_reported():
    previous = make_record("0100100010")
    current = make_record("0100100020", row=3)

    result = compare_normalized_releases(
        make_release(previous),
        make_release(current),
    )

    assert result["summary"]["added_count"] == 1
    assert result["summary"]["removed_count"] == 1
    assert result["added_records"][0]["psgc_code"] == "0100100020"
    assert result["removed_records"][0]["psgc_code"] == "0100100010"


def test_one_to_one_correspondence_match_is_only_a_candidate():
    previous = make_record("0100100010", correspondence="123456789")
    current = make_record(
        "0100100020",
        correspondence="123456789",
        row=3,
    )

    result = compare_normalized_releases(
        make_release(previous),
        make_release(current),
    )

    candidate = result["identity_candidate_groups"][0]

    assert candidate["relationship_type"] == "ONE_TO_ONE"
    assert candidate["review_status"] == "REVIEW_REQUIRED"
    assert candidate["previous_records"][0]["psgc_code"] == "0100100010"
    assert candidate["current_records"][0]["psgc_code"] == "0100100020"


def test_duplicate_correspondence_matches_are_ambiguous():
    previous_a = make_record(
        "0100100010", correspondence="123456789", row=2
    )
    previous_b = make_record(
        "0100100020", correspondence="123456789", row=3
    )
    current_a = make_record(
        "0100100030", correspondence="123456789", row=4
    )

    result = compare_normalized_releases(
        make_release(previous_a, previous_b),
        make_release(current_a),
    )

    candidate = result["identity_candidate_groups"][0]

    assert candidate["relationship_type"] == "AMBIGUOUS"
    assert len(candidate["previous_records"]) == 2
    assert len(candidate["current_records"]) == 1


def test_missing_correspondence_code_does_not_create_candidate():
    previous = make_record("0100100010", correspondence=None)
    current = make_record("0100100020", correspondence=None, row=3)

    result = compare_normalized_releases(
        make_release(previous),
        make_release(current),
    )

    assert result["identity_candidate_groups"] == []


def test_raw_storage_difference_is_not_a_normalized_attribute_change():
    previous = make_record("0100100010", correspondence="123456789")
    current = make_record("0100100010", correspondence="123456789", row=3)

    previous_cell = previous["cells"]["correspondence_code"]
    previous_cell["raw_value"] = 123456789
    previous_cell["normalization_action"] = "NUMERIC_INTEGER_TO_STRING"

    current_cell = current["cells"]["correspondence_code"]
    current_cell["raw_value"] = "123456789"
    current_cell["normalization_action"] = "PASSTHROUGH"

    result = compare_normalized_releases(
        make_release(previous),
        make_release(current),
    )

    assert result["summary"]["changed_count"] == 0
    assert result["summary"]["unchanged_count"] == 1


def test_duplicate_psgc_code_is_rejected():
    first = make_record("0100100010", row=2)
    duplicate = make_record("0100100010", row=3)

    with pytest.raises(ValueError, match="duplicate PSGC code"):
        compare_normalized_releases(
            make_release(first, duplicate),
            make_release(first),
        )


def test_missing_psgc_code_is_rejected():
    invalid = make_record(None)

    with pytest.raises(ValueError, match="missing or invalid"):
        compare_normalized_releases(
            make_release(invalid),
            make_release(make_record("0100100010")),
        )


def test_release_identifiers_are_preserved():
    previous = make_release(
        make_record("0100100010"),
        filename="PSGC-1Q-2024-Publication-Datafile.xlsx",
    )
    current = make_release(
        make_record("0100100010"),
        filename="PSGC-4Q-2024-Publication-Datafile.xlsx",
    )

    result = compare_normalized_releases(
        previous,
        current,
        previous_release_id="2024-Q1",
        current_release_id="2024-Q4",
    )

    assert result["previous_release"]["release_id"] == "2024-Q1"
    assert result["current_release"]["release_id"] == "2024-Q4"
    assert (
        result["previous_release"]["source_artifact"]["filename"]
        == "PSGC-1Q-2024-Publication-Datafile.xlsx"
    )


def test_fields_with_different_source_bases_are_excluded():
    previous = make_record("0100100010", population=100)
    current = make_record("0100100010", population=200, row=3)

    previous["cells"]["income_classification"] = make_cell("1st")
    current["cells"]["income_classification"] = make_cell("2nd")

    previous_release = make_release(previous)
    current_release = make_release(current)

    previous_release["source_metadata"] = {
        "population_reference_year": 2020,
        "urban_rural_reference_year": 2020,
        "income_classification_basis": None,
    }
    current_release["source_metadata"] = {
        "population_reference_year": 2024,
        "urban_rural_reference_year": 2024,
        "income_classification_basis": "DOF DO No. 074.2024",
    }

    result = compare_normalized_releases(previous_release, current_release)

    assert result["summary"]["changed_count"] == 0
    assert result["summary"]["unchanged_count"] == 1
    assert {
        item["field_name"] for item in result["incomparable_fields"]
    } == {
        "population",
        "urban_rural",
        "income_classification",
    }
    assert result["previous_release"]["population_reference_year"] == 2020
    assert result["current_release"]["population_reference_year"] == 2024


def test_fields_with_equal_or_missing_bases_remain_comparable():
    previous = make_record("0100100010", population=100)
    current = make_record("0100100010", population=200, row=3)

    result = compare_normalized_releases(
        make_release(previous),
        make_release(current),
    )

    assert result["incomparable_fields"] == []
    assert result["summary"]["changed_count"] == 1
    assert result["changed_records"][0]["changes"][0]["field_name"] == "population"
