"""Build conservative, reviewable PSGC parent-child candidates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

RELATIONSHIP_TYPE = "PARENT_OF"
REVIEW_STATUS = "PROPOSED"
MANILA_CODE = "1380600000"
ISABELA_GROUP_CODE = "0990100000"
ISABELA_CITY_CODE = "0990101000"
REGION_IX_CODE = "0900000000"
SGA_GROUP_CODE = "1999900000"
BARMM_REGION_CODE = "1900000000"


def _value(record: Mapping[str, Any], field: str) -> Any:
    """Read a normalized field from the ETL cell representation."""
    return record.get("cells", {}).get(field, {}).get("normalized_value")


def _record_index(
    normalized: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    records_by_code: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []

    for record in normalized.get("records", []):
        code = _value(record, "psgc_code")
        row = record.get("source_row_number")

        if not isinstance(code, str) or len(code) != 10 or not code.isdigit():
            findings.append(
                {
                    "code": "INVALID_PSGC_CODE",
                    "psgc_code": code,
                    "source_row_number": row,
                    "message": "Record does not contain a valid 10-digit normalized PSGC code.",
                }
            )
            continue

        if code in records_by_code:
            findings.append(
                {
                    "code": "DUPLICATE_PSGC_CODE",
                    "psgc_code": code,
                    "source_row_number": row,
                    "message": "More than one source record has this PSGC code.",
                }
            )
            continue

        records_by_code[code] = dict(record)

    return records_by_code, findings


def _expected_parent(
    record: Mapping[str, Any],
) -> tuple[str | None, str | None, str]:
    """Return (parent code, rule identifier, rationale)."""
    code = _value(record, "psgc_code")
    level = _value(record, "geographic_level")
    city_class = _value(record, "city_class")

    if level == "Reg":
        return None, None, "Region is a top-level geographic record."

    if level is None and code == ISABELA_GROUP_CODE:
        return (
            REGION_IX_CODE,
            "ISABELA_GROUPING_REGION",
            "The source-defined City of Isabela grouping record belongs directly under Region IX, not under a province.",
        )

    if level is None and code == SGA_GROUP_CODE:
        return (
            BARMM_REGION_CODE,
            "SGA_GROUPING_REGION",
            "The source-defined Special Geographic Area grouping record belongs directly under BARMM.",
        )

    if level == "Prov":
        return (
            code[:2] + "00000000",
            "REGION_PROVINCE",
            "Province is matched to the Region using the two-digit region segment.",
        )

    if level == "City" and city_class in {"HUC", "ICC"}:
        return (
            code[:2] + "00000000",
            "REGION_INDEPENDENT_CITY",
            f"{city_class} is matched directly to its Region, not to a province.",
        )

    if level == "City" and code == ISABELA_CITY_CODE:
        return (
            ISABELA_GROUP_CODE,
            "ISABELA_GROUPING",
            "Source-defined City of Isabela record is grouped under its distinct unclassified Isabela record.",
        )

    if level == "City" and city_class == "CC":
        if code.startswith("13"):
            return (
                code[:2] + "00000000",
                "NCR_COMPONENT_CITY",
                "NCR has no province layer; the city is matched directly to NCR.",
            )
        return (
            code[:5] + "00000",
            "PROVINCE_COMPONENT_CITY",
            "Component city is matched to its province using the five-digit region/province segment.",
        )

    if level == "Mun":
        if code.startswith("13"):
            return (
                code[:2] + "00000000",
                "NCR_MUNICIPALITY",
                "Pateros is matched directly to NCR because NCR has no province layer.",
            )
        if code.startswith("19999"):
            return (
                SGA_GROUP_CODE,
                "SGA_CHILD",
                "Source-defined SGA municipality is grouped under the SGA record.",
            )
        return (
            code[:5] + "00000",
            "PROVINCE_MUNICIPALITY",
            "Municipality is matched to its province using the five-digit region/province segment.",
        )

    if level == "SGU":
        return (
            SGA_GROUP_CODE,
            "SGA_CHILD",
            "Source-defined SGA geographic unit is grouped under the SGA record.",
        )

    if level == "SubMun":
        if code.startswith("13806"):
            return (
                MANILA_CODE,
                "MANILA_SUBMUNICIPALITY",
                "Manila SubMunicipality is a direct child of the City of Manila.",
            )
        return None, None, "SubMunicipality has no documented parent rule in this release."

    if level == "Bgy":
        return (
            code[:7] + "000",
            "ADMINISTRATIVE_UNIT_BARANGAY",
            "Barangay is matched to the city, municipality, or SubMunicipality represented by its seven-digit administrative segment.",
        )

    return None, None, f"No parent rule is defined for geographic level {level!r}."


def build_hierarchy(
    normalized: Mapping[str, Any],
    release_id: str,
) -> dict[str, Any]:
    """Derive proposed hierarchy edges and validation findings for one release.

    The function is deterministic and side-effect free. It does not write to
    D1, approve relationships, or infer relationships across releases.
    """
    if not isinstance(release_id, str) or not release_id.strip():
        raise ValueError("release_id must be a non-empty string.")

    records_by_code, findings = _record_index(normalized)
    edges: list[dict[str, Any]] = []
    assigned_children: set[str] = set()

    for child_code, child in sorted(records_by_code.items()):
        level = _value(child, "geographic_level")
        parent_code, rule, rationale = _expected_parent(child)

        if parent_code is None:
            if level != "Reg" and child_code not in {ISABELA_GROUP_CODE, SGA_GROUP_CODE}:
                findings.append(
                    {
                        "code": "UNRESOLVED_PARENT_RULE",
                        "psgc_code": child_code,
                        "source_row_number": child.get("source_row_number"),
                        "message": rationale,
                    }
                )
            continue

        parent = records_by_code.get(parent_code)
        if parent is None:
            findings.append(
                {
                    "code": "MISSING_PARENT_RECORD",
                    "psgc_code": child_code,
                    "candidate_parent_psgc_code": parent_code,
                    "source_row_number": child.get("source_row_number"),
                    "rule": rule,
                    "message": "Expected parent code is not present in this release.",
                }
            )
            continue

        if child_code == parent_code:
            findings.append(
                {
                    "code": "SELF_PARENT",
                    "psgc_code": child_code,
                    "rule": rule,
                    "message": "A record cannot be its own parent.",
                }
            )
            continue

        parent_level = _value(parent, "geographic_level")
        if level == "Bgy" and parent_level not in {"City", "Mun", "SubMun", "SGU"}:
            findings.append(
                {
                    "code": "INVALID_PARENT_LEVEL",
                    "psgc_code": child_code,
                    "candidate_parent_psgc_code": parent_code,
                    "rule": rule,
                    "message": (
                        f"Barangay candidate parent has unsupported level {parent_level!r}."
                    ),
                }
            )
            continue

        if child_code in assigned_children:
            findings.append(
                {
                    "code": "MULTIPLE_PARENT_CANDIDATES",
                    "psgc_code": child_code,
                    "candidate_parent_psgc_code": parent_code,
                    "rule": rule,
                    "message": "Child already has a proposed immediate parent.",
                }
            )
            continue

        edges.append(
            {
                "release_id": release_id,
                "parent_psgc_code": parent_code,
                "child_psgc_code": child_code,
                "relationship_type": RELATIONSHIP_TYPE,
                "evidence_reference": (
                    f"PSGC worksheet row {child.get('source_row_number')} "
                    f"(source_record_id={child.get('source_record_id')})"
                ),
                "rationale": f"[{rule}] {rationale}",
                "review_status": REVIEW_STATUS,
            }
        )
        assigned_children.add(child_code)

    # Validate that the generated parent map is acyclic.
    parent_by_child = {edge["child_psgc_code"]: edge["parent_psgc_code"] for edge in edges}
    cycle_findings: set[str] = set()

    for child_code in parent_by_child:
        seen: set[str] = set()
        current = child_code
        while current in parent_by_child:
            if current in seen:
                cycle_findings.add(child_code)
                break
            seen.add(current)
            current = parent_by_child[current]

    for child_code in sorted(cycle_findings):
        findings.append(
            {
                "code": "HIERARCHY_CYCLE",
                "psgc_code": child_code,
                "message": "Proposed parent relationships contain a cycle.",
            }
        )

    finding_counts = Counter(item["code"] for item in findings)
    level_counts = Counter(
        _value(record, "geographic_level") or "UNCLASSIFIED" for record in records_by_code.values()
    )
    rule_counts = Counter(
        edge["rationale"].split("]", 1)[0].removeprefix("[")
        for edge in edges
        if edge.get("rationale", "").startswith("[")
    )

    return {
        "release_id": release_id,
        "record_count": len(records_by_code),
        "edge_count": len(edges),
        "finding_count": len(findings),
        "level_counts": dict(sorted(level_counts.items())),
        "rule_counts": dict(sorted(rule_counts.items())),
        "finding_counts": dict(sorted(finding_counts.items())),
        "edges": edges,
        "findings": findings,
    }
