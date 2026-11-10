"""Tests for independent PSGC hierarchy structural validation."""

from __future__ import annotations

from copy import deepcopy

from psgc_etl.hierarchy import build_hierarchy, validate_hierarchy


def _record(
    code: str,
    level: str | None,
    *,
    city_class: str | None = None,
):
    values = {
        "psgc_code": code,
        "name": f"Record {code}",
        "geographic_level": level,
        "city_class": city_class,
    }

    return {
        "source_record_id": f"fixture:{code}",
        "source_row_number": 2,
        "cells": {key: {"normalized_value": value} for key, value in values.items()},
    }


def _valid_fixture():
    records = [
        _record("1300000000", "Reg"),
        _record("1380600000", "City", city_class="HUC"),
        _record("1380601000", "SubMun"),
        _record("1380601001", "Bgy"),
        _record("1381701000", "Mun"),
        _record("0900000000", "Reg"),
        _record("0990100000", None),
        _record("0990101000", "City", city_class="CC"),
        _record("0990101001", "Bgy"),
        _record("1900000000", "Reg"),
        _record("1999900000", None),
        _record("1999901000", "SGU"),
        _record("1999901001", "Bgy"),
    ]

    normalized = {"records": records}
    hierarchy = build_hierarchy(normalized, "fixture-release")
    return normalized, hierarchy


def test_valid_hierarchy_passes_all_structural_checks():
    normalized, hierarchy = _valid_fixture()

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is True
    assert result["error_count"] == 0
    assert result["validated_path_count"] == len(normalized["records"])
    assert result["maximum_depth"] == 3


def test_pateros_and_special_grouping_transitions_are_valid():
    normalized, hierarchy = _valid_fixture()

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is True
    assert result["finding_counts"] == {}


def test_missing_parent_edge_is_reported():
    normalized, hierarchy = _valid_fixture()
    hierarchy = deepcopy(hierarchy)

    hierarchy["edges"] = [
        edge for edge in hierarchy["edges"] if edge["child_psgc_code"] != "1380601001"
    ]

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["MISSING_PARENT"] == 1


def test_multiple_parents_are_reported():
    normalized, hierarchy = _valid_fixture()
    hierarchy = deepcopy(hierarchy)

    hierarchy["edges"].append(
        {
            "release_id": "fixture-release",
            "parent_psgc_code": "1300000000",
            "child_psgc_code": "1380601001",
        }
    )

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["MULTIPLE_PARENTS"] == 1


def test_missing_parent_record_is_reported():
    normalized, hierarchy = _valid_fixture()
    hierarchy = deepcopy(hierarchy)

    edge = next(edge for edge in hierarchy["edges"] if edge["child_psgc_code"] == "1380601001")
    edge["parent_psgc_code"] = "1300000001"

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["MISSING_PARENT_RECORD"] == 1


def test_invalid_level_transition_is_reported():
    normalized, hierarchy = _valid_fixture()
    hierarchy = deepcopy(hierarchy)

    edge = next(edge for edge in hierarchy["edges"] if edge["child_psgc_code"] == "1380601001")
    edge["parent_psgc_code"] = "1300000000"

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["INVALID_LEVEL_TRANSITION"] == 1


def test_region_cannot_have_a_parent():
    normalized, hierarchy = _valid_fixture()
    hierarchy = deepcopy(hierarchy)

    hierarchy["edges"].append(
        {
            "release_id": "fixture-release",
            "parent_psgc_code": "1900000000",
            "child_psgc_code": "1300000000",
        }
    )

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["REGION_HAS_PARENT"] == 1


def test_cycle_is_reported():
    normalized = {
        "records": [
            _record("0100000000", "Reg"),
            _record("0100100000", "Prov"),
            _record("0100101000", "City", city_class="CC"),
        ]
    }

    hierarchy = {
        "release_id": "fixture-release",
        "edges": [
            {
                "release_id": "fixture-release",
                "parent_psgc_code": "0100101000",
                "child_psgc_code": "0100100000",
            },
            {
                "release_id": "fixture-release",
                "parent_psgc_code": "0100100000",
                "child_psgc_code": "0100101000",
            },
        ],
    }

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["HIERARCHY_CYCLE"] >= 1


def test_edge_from_another_release_is_reported():
    normalized, hierarchy = _valid_fixture()
    hierarchy = deepcopy(hierarchy)
    hierarchy["edges"][0]["release_id"] = "different-release"

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["EDGE_RELEASE_MISMATCH"] == 1


def test_duplicate_edge_is_reported():
    normalized, hierarchy = _valid_fixture()
    hierarchy = deepcopy(hierarchy)
    hierarchy["edges"].append(deepcopy(hierarchy["edges"][0]))

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["DUPLICATE_EDGE"] == 1


def test_invalid_relationship_type_is_reported():
    normalized, hierarchy = _valid_fixture()
    hierarchy = deepcopy(hierarchy)
    hierarchy["edges"][0]["relationship_type"] = "RELATED_TO"

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["INVALID_RELATIONSHIP_TYPE"] == 1


def test_invalid_review_status_is_reported():
    normalized, hierarchy = _valid_fixture()
    hierarchy = deepcopy(hierarchy)
    hierarchy["edges"][0]["review_status"] = "PENDING"

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["INVALID_REVIEW_STATUS"] == 1


def test_missing_edge_evidence_and_rationale_are_reported():
    normalized, hierarchy = _valid_fixture()
    hierarchy = deepcopy(hierarchy)
    hierarchy["edges"][0]["evidence_reference"] = None
    hierarchy["edges"][0]["rationale"] = " "

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["MISSING_EDGE_EVIDENCE"] == 1
    assert result["finding_counts"]["MISSING_EDGE_RATIONALE"] == 1


def test_isabela_grouping_cannot_be_attached_to_another_region():
    normalized, hierarchy = _valid_fixture()
    hierarchy = deepcopy(hierarchy)

    edge = next(
        edge
        for edge in hierarchy["edges"]
        if edge["child_psgc_code"] == "0990100000"
    )
    edge["parent_psgc_code"] = "1900000000"

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["INVALID_LEVEL_TRANSITION"] >= 1


def test_sga_grouping_cannot_be_attached_to_another_region():
    normalized, hierarchy = _valid_fixture()
    hierarchy = deepcopy(hierarchy)

    edge = next(
        edge
        for edge in hierarchy["edges"]
        if edge["child_psgc_code"] == "1999900000"
    )
    edge["parent_psgc_code"] = "0900000000"

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["INVALID_LEVEL_TRANSITION"] >= 1


def test_sga_grouping_cannot_accept_unrelated_city_records():
    normalized, hierarchy = _valid_fixture()
    normalized["records"].append(
        _record("1999902000", "City", city_class="CC")
    )
    hierarchy = deepcopy(hierarchy)
    hierarchy["edges"].append({
        "release_id": "fixture-release",
        "parent_psgc_code": "1999900000",
        "child_psgc_code": "1999902000",
        "relationship_type": "PARENT_OF",
        "evidence_reference": "fixture evidence",
        "rationale": "fixture rationale",
        "review_status": "PROPOSED",
    })

    result = validate_hierarchy(normalized, hierarchy)

    assert result["is_valid"] is False
    assert result["finding_counts"]["INVALID_LEVEL_TRANSITION"] >= 1
