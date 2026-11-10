"""Tests for conservative release-specific hierarchy derivation."""

from __future__ import annotations

import pytest

from psgc_etl.hierarchy import build_hierarchy


def _record(
    code: str,
    level: str | None,
    *,
    city_class: str | None = None,
    row: int = 2,
):
    values = {
        "psgc_code": code,
        "name": f"Record {code}",
        "geographic_level": level,
        "city_class": city_class,
    }
    return {
        "source_record_id": f"fixture:{code}",
        "source_row_number": row,
        "cells": {key: {"normalized_value": value} for key, value in values.items()},
    }


def _build(*records):
    return build_hierarchy({"records": list(records)}, "fixture-release")


def _parents(result):
    return {edge["child_psgc_code"]: edge["parent_psgc_code"] for edge in result["edges"]}


def test_region_and_province_relationship():
    result = _build(
        _record("0100000000", "Reg"),
        _record("0100100000", "Prov"),
    )
    assert _parents(result) == {"0100100000": "0100000000"}
    assert result["edges"][0]["review_status"] == "PROPOSED"


def test_huc_is_child_of_region_not_correspondence_province():
    result = _build(
        _record("0600000000", "Reg"),
        _record("0630200000", "City", city_class="HUC"),
        _record("0645000000", "Prov"),
    )
    assert _parents(result)["0630200000"] == "0600000000"


def test_manila_submunicipality_and_barangay_path():
    result = _build(
        _record("1300000000", "Reg"),
        _record("1380600000", "City", city_class="HUC"),
        _record("1380601000", "SubMun"),
        _record("1380601001", "Bgy"),
    )
    parents = _parents(result)
    assert parents["1380601000"] == "1380600000"
    assert parents["1380601001"] == "1380601000"


def test_ncr_pateros_is_child_of_ncr():
    result = _build(
        _record("1300000000", "Reg"),
        _record("1380100000", "Mun"),
    )
    assert _parents(result)["1380100000"] == "1300000000"


def test_isabela_grouping_record_is_not_merged_with_city():
    result = _build(
        _record("0900000000", "Reg"),
        _record("0990100000", None),
        _record("0990101000", "City", city_class="CC"),
        _record("0990101001", "Bgy"),
    )
    parents = _parents(result)
    assert parents["0990100000"] == "0900000000"
    assert parents["0990101000"] == "0990100000"
    assert parents["0990101001"] == "0990101000"


@pytest.mark.parametrize("child_level", ["SGU", "Mun"])
def test_sga_grouping_supports_release_specific_child_level(child_level):
    result = _build(
        _record("1900000000", "Reg"),
        _record("1999900000", None),
        _record("1999901000", child_level),
        _record("1999901001", "Bgy"),
    )
    parents = _parents(result)
    assert parents["1999900000"] == "1900000000"
    assert parents["1999901000"] == "1999900000"
    assert parents["1999901001"] == "1999901000"


def test_missing_parent_is_reported_not_guessed():
    result = _build(_record("0100100000", "Prov"))
    assert result["edge_count"] == 0
    assert result["finding_counts"] == {"MISSING_PARENT_RECORD": 1}


def test_unknown_unclassified_record_is_reported():
    result = _build(_record("0100100000", None))
    assert result["finding_counts"] == {"UNRESOLVED_PARENT_RULE": 1}


def test_invalid_code_is_reported():
    result = _build(_record("not-a-code", "Bgy"))
    assert result["record_count"] == 0
    assert result["finding_counts"] == {"INVALID_PSGC_CODE": 1}


def test_release_id_is_required():
    with pytest.raises(ValueError, match="release_id"):
        build_hierarchy({"records": []}, " ")
