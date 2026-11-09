from pathlib import Path

from openpyxl import Workbook, load_workbook

from psgc_etl.extract import (
    compare_workbook_schemas,
    profile_workbook,
)


def _create_workbook(
    path: Path,
    *,
    geographic_level_header: str = "Geographic Level",
    add_extra_column: bool = False,
) -> None:
    workbook = Workbook()
    metadata = workbook.active
    metadata.title = "Metadata"
    metadata.append(["Publication Date", "2025-03-31"])

    worksheet = workbook.create_sheet("PSGC")
    headers = [
        "10-digit PSGC",
        "Name",
        "Correspondence Code",
        geographic_level_header,
    ]
    if add_extra_column:
        headers.append("New Source Field")

    worksheet.append(headers)
    worksheet.append(["0100100001", "Barangay A", 1001, "Bgy"])
    worksheet.append(["0100100001", "Barangay A Duplicate", 1002, "Bgy"])
    worksheet.append([None, "Barangay B", None, "Mun"])

    # Formatting beyond the actual data must not inflate record counts.
    worksheet["A1000"].number_format = "@"

    workbook.save(path)
    workbook.close()


def test_profile_reports_source_and_psgc_statistics(tmp_path: Path) -> None:
    source = tmp_path / "sample.xlsx"
    _create_workbook(source)

    profile = profile_workbook(source)

    assert profile["source"]["filename"] == "sample.xlsx"
    assert len(profile["source"]["sha256"]) == 64

    psgc = profile["psgc_summary"]
    assert psgc is not None
    assert psgc["missing_psgc_count"] == 1
    assert psgc["duplicate_psgc_value_count"] == 1
    assert psgc["duplicate_psgc_excess_count"] == 1
    assert psgc["missing_correspondence_code_count"] == 1
    assert psgc["geographic_level_distribution"] == [
        {"value": "Bgy", "count": 2},
        {"value": "Mun", "count": 1},
    ]

    psgc_sheet = next(
        sheet for sheet in profile["sheets"]
        if sheet["sheet_name"] == "PSGC"
    )
    assert psgc_sheet["non_empty_data_rows"] == 3
    assert psgc_sheet["declared_dimensions"]["max_row"] >= 1000
    assert psgc_sheet["actual_non_empty_bounds"]["max_row"] == 4


def test_schema_comparison_detects_header_changes(tmp_path: Path) -> None:
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"

    _create_workbook(first)
    _create_workbook(
        second,
        geographic_level_header="Geo Level",
        add_extra_column=True,
    )

    profiles = [
        profile_workbook(first),
        profile_workbook(second),
    ]

    comparisons = compare_workbook_schemas(profiles)

    assert len(comparisons) == 1
    assert comparisons[0]["core_schema_compatible"] is False
    assert comparisons[0]["header_differences"]
    assert comparisons[0]["required_header_differences"]


def test_schema_comparison_returns_empty_for_one_workbook(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.xlsx"
    _create_workbook(source)

    assert compare_workbook_schemas([profile_workbook(source)]) == []


def test_missing_workbook_is_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "missing.xlsx"

    try:
        profile_workbook(missing)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Expected FileNotFoundError")


def test_missing_psgc_sheet_is_reported(tmp_path: Path) -> None:
    source = tmp_path / "no-psgc.xlsx"
    workbook = Workbook()
    workbook.active.title = "Metadata"
    workbook.save(source)
    workbook.close()

    profile = profile_workbook(source)

    assert profile["psgc_summary"] is None
    assert profile["warnings"] == [
        "Required worksheet 'PSGC' was not found."
    ]


def test_hidden_sheets_are_reported_separately(tmp_path: Path) -> None:
    source = tmp_path / "hidden-sheet.xlsx"

    workbook = Workbook()
    visible = workbook.active
    visible.title = "PSGC"
    visible.append(["10-digit PSGC", "Name", "Correspondence Code", "Geographic Level"])
    visible.append(["0100100001", "Barangay A", 1001, "Bgy"])

    hidden = workbook.create_sheet("Prov Sum")
    hidden["A1"] = "Legacy summary"
    hidden["A2"] = "Historical content"
    hidden.sheet_state = "hidden"

    workbook.create_sheet("Coding Structure")

    workbook.save(source)
    workbook.close()

    profile = profile_workbook(source)

    assert profile["sheet_inventory"]["visible"] == [
    "PSGC",
    "Coding Structure",
]
    assert profile["sheet_inventory"]["hidden"] == ["Prov Sum"]
    assert profile["sheet_inventory"]["very_hidden"] == []
    assert profile["sheet_inventory"]["empty"] == ["Coding Structure"]

    hidden_profile = next(
        sheet for sheet in profile["sheets"]
        if sheet["sheet_name"] == "Prov Sum"
    )
    assert hidden_profile["sheet_state"] == "hidden"
    assert hidden_profile["non_empty_data_rows"] == 1


def test_schema_comparison_detects_visibility_changes(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"

    _create_workbook(first)
    _create_workbook(second)

    workbook = load_workbook(second)
    workbook["PSGC"].sheet_state = "hidden"
    workbook.save(second)
    workbook.close()

    profiles = [
        profile_workbook(first),
        profile_workbook(second),
    ]

    comparison = compare_workbook_schemas(profiles)[0]

    assert comparison["visibility_differences"] == [
        {
            "sheet_name": "PSGC",
            "reference_state": "visible",
            "candidate_state": "hidden",
        }
    ]
    assert comparison["core_schema_compatible"] is True



def test_supplementary_sheet_difference_does_not_break_core_schema(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"

    _create_workbook(first)
    _create_workbook(second)

    workbook = load_workbook(first)
    workbook.create_sheet("Provincial Summary")
    workbook.save(first)
    workbook.close()

    profiles = [
        profile_workbook(first),
        profile_workbook(second),
    ]

    comparison = compare_workbook_schemas(profiles)[0]

    assert comparison["core_schema_compatible"] is True
    assert comparison["required_sheet_differences"] == {
        "missing_in_reference": [],
        "missing_in_candidate": [],
    }
    assert comparison["required_header_differences"] == []
    assert comparison["supplementary_sheet_differences"] == {
        "reference_only": ["Provincial Summary"],
        "candidate_only": [],
    }
