"""Deterministic validation of normalized PSGC source records."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from psgc_etl.validate.rules import RULES, VALIDATION_RULESET_VERSION

KNOWN_GEOGRAPHIC_LEVELS = frozenset(
    {
        "Reg",
        "Prov",
        "City",
        "Mun",
        "Bgy",
        "SubMun",
        "SGU",
    }
)


def _source_value_for_report(value: Any) -> str | None:
    """Return a stable, JSON-friendly representation for finding context."""
    if value is None:
        return None
    return repr(value)


def _finding(
    rule_id: str,
    record: dict[str, Any],
    *,
    field_name: str,
    cell: dict[str, Any],
    message: str | None = None,
) -> dict[str, Any]:
    rule = RULES[rule_id]

    return {
        "rule_id": rule.rule_id,
        "severity": rule.severity,
        "message": message or rule.description,
        "source_record_id": record["source_record_id"],
        "worksheet_name": record["worksheet_name"],
        "source_row_number": record["source_row_number"],
        "field_name": field_name,
        "source_coordinate": cell.get("coordinate"),
        "source_value": _source_value_for_report(cell.get("raw_value")),
        "normalized_value": cell.get("normalized_value"),
    }


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_numeric_source_cell(cell: dict[str, Any]) -> bool:
    return (
        cell.get("cell_data_type") == "n"
        and cell.get("python_type") in {"int", "float"}
        and not isinstance(cell.get("raw_value"), bool)
    )


def _source_representation(cell: dict[str, Any]) -> str:
    """Classify the original Excel cell representation."""
    raw_value = cell.get("raw_value")

    if _is_blank(raw_value):
        return "blank"

    if _is_numeric_source_cell(cell):
        return "numeric"

    if isinstance(raw_value, str):
        return "text"

    return "other"


def validate_psgc_records(
    normalized: dict[str, Any],
    *,
    psgc_code_length: int = 10,
) -> dict[str, Any]:
    """Validate normalized records without modifying the input.

    The selected PSGC code length is explicit because historical releases may
    use a different code format. This initial validator supports fixed-length
    numeric PSGC codes only.
    """
    if psgc_code_length < 1:
        raise ValueError("psgc_code_length must be a positive integer")

    records = normalized["records"]
    findings: list[dict[str, Any]] = []
    source_representation_counts = {
        field_name: {
            "numeric": 0,
            "text": 0,
            "blank": 0,
            "other": 0,
        }
        for field_name in ("psgc_code", "correspondence_code")
    }
    psgc_occurrences: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = (
        defaultdict(list)
    )
    correspondence_occurrences: dict[
        str, list[tuple[dict[str, Any], dict[str, Any]]]
    ] = defaultdict(list)

    code_pattern = re.compile(rf"^[0-9]{{{psgc_code_length}}}$")

    for record in records:
        cells = record["cells"]
        for field_name in ("psgc_code", "correspondence_code"):
            representation = _source_representation(cells[field_name])
            source_representation_counts[field_name][representation] += 1
        psgc_cell = cells["psgc_code"]
        psgc_value = psgc_cell.get("normalized_value")

        if _is_blank(psgc_cell.get("raw_value")):
            findings.append(
                _finding(
                    "PSGC001",
                    record,
                    field_name="psgc_code",
                    cell=psgc_cell,
                )
            )
        elif not isinstance(psgc_value, str) or not code_pattern.fullmatch(
            psgc_value
        ):
            findings.append(
                _finding(
                    "PSGC002",
                    record,
                    field_name="psgc_code",
                    cell=psgc_cell,
                )
            )
        else:
            psgc_occurrences[psgc_value].append((record, psgc_cell))

        if _is_numeric_source_cell(psgc_cell):
            findings.append(
                _finding(
                    "PSGC009",
                    record,
                    field_name="psgc_code",
                    cell=psgc_cell,
                )
            )

        name_cell = cells["name"]
        if _is_blank(name_cell.get("normalized_value")):
            findings.append(
                _finding(
                    "PSGC004",
                    record,
                    field_name="name",
                    cell=name_cell,
                )
            )

        correspondence_cell = cells["correspondence_code"]
        correspondence_value = correspondence_cell.get("normalized_value")

        if isinstance(correspondence_value, str) and correspondence_value:
            correspondence_occurrences[correspondence_value].append(
                (record, correspondence_cell)
            )

        population_cell = cells["population"]
        if population_cell.get("normalization_status") == "REVIEW":
            action = population_cell.get("normalization_action")
            rule_id = {
                "FORMULA_CACHE_MISSING": "PSGC006",
                "KNOWN_SOURCE_ERROR_AS_MISSING": "PSGC011",
            }.get(action, "PSGC005")
            findings.append(
                _finding(
                    rule_id,
                    record,
                    field_name="population",
                    cell=population_cell,
                    message=population_cell.get("normalization_rationale"),
                )
            )

        geographic_level_cell = cells["geographic_level"]
        geographic_level = geographic_level_cell.get("normalized_value")

        if (
            geographic_level is not None
            and geographic_level not in KNOWN_GEOGRAPHIC_LEVELS
        ):
            findings.append(
                _finding(
                    "PSGC008",
                    record,
                    field_name="geographic_level",
                    cell=geographic_level_cell,
                )
            )

    for occurrences in psgc_occurrences.values():
        if len(occurrences) > 1:
            for record, cell in occurrences:
                findings.append(
                    _finding(
                        "PSGC003",
                        record,
                        field_name="psgc_code",
                        cell=cell,
                    )
                )

    for occurrences in correspondence_occurrences.values():
        if len(occurrences) > 1:
            for record, cell in occurrences:
                findings.append(
                    _finding(
                        "PSGC007",
                        record,
                        field_name="correspondence_code",
                        cell=cell,
                    )
                )

    severity_order = {"ERROR": 0, "REVIEW": 1, "WARNING": 2}
    findings.sort(
        key=lambda finding: (
            finding["source_row_number"],
            severity_order[finding["severity"]],
            finding["rule_id"],
            finding["field_name"],
        )
    )

    counts = {
        severity: sum(
            finding["severity"] == severity for finding in findings
        )
        for severity in ("ERROR", "REVIEW", "WARNING")
    }

    return {
        "validation_ruleset_version": VALIDATION_RULESET_VERSION,
        "source_artifact": normalized["source_artifact"],
        "worksheet_name": normalized["worksheet_name"],
        "record_count": len(records),
        "finding_count": len(findings),
        "severity_counts": counts,
        "source_representation_counts": source_representation_counts,
        "findings": findings,
    }
