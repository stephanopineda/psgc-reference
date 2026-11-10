"""Independent structural validation for release-specific PSGC hierarchies."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

ALLOWED_TRANSITIONS = {
    ("Reg", "Prov"),
    ("Reg", "City"),
    ("Reg", "Mun"),  # Pateros directly under NCR
    ("Prov", "City"),
    ("Prov", "Mun"),
    ("City", "Bgy"),
    ("City", "SubMun"),
    ("Mun", "Bgy"),
    ("SubMun", "Bgy"),
    ("SGU", "Bgy"),
}

ALLOWED_REVIEW_STATUSES = {
    "PROPOSED",
    "APPROVED",
    "REJECTED",
}

ISABELA_GROUP_CODE = "0990100000"
ISABELA_CITY_CODE = "0990101000"
REGION_IX_CODE = "0900000000"
SGA_GROUP_CODE = "1999900000"
BARMM_REGION_CODE = "1900000000"


def _is_allowed_transition(
    parent_level: str | None,
    child_level: str | None,
    parent_code: str,
    child_code: str,
) -> bool:
    """Check standard transitions and explicitly documented exceptions."""
    if (parent_level, child_level) in ALLOWED_TRANSITIONS:
        return True

    if (
        parent_code == REGION_IX_CODE
        and child_code == ISABELA_GROUP_CODE
        and parent_level == "Reg"
        and child_level is None
    ):
        return True

    if (
        parent_code == ISABELA_GROUP_CODE
        and child_code == ISABELA_CITY_CODE
        and parent_level is None
        and child_level == "City"
    ):
        return True

    if (
        parent_code == BARMM_REGION_CODE
        and child_code == SGA_GROUP_CODE
        and parent_level == "Reg"
        and child_level is None
    ):
        return True

    return (
        parent_code == SGA_GROUP_CODE
        and parent_level is None
        and child_level in {"SGU", "Mun"}
        and child_code.startswith("19999")
        and child_code != SGA_GROUP_CODE
    )


def _value(record: Mapping[str, Any], field: str) -> Any:
    """Read a normalized field from the ETL cell representation."""
    return record.get("cells", {}).get(field, {}).get("normalized_value")


def _finding(
    code: str,
    message: str,
    *,
    psgc_code: str | None = None,
    parent_psgc_code: str | None = None,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "code": code,
        "message": message,
    }

    if psgc_code is not None:
        finding["psgc_code"] = psgc_code

    if parent_psgc_code is not None:
        finding["parent_psgc_code"] = parent_psgc_code

    return finding


def validate_hierarchy(
    normalized: Mapping[str, Any],
    hierarchy: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently validate candidate hierarchy coverage and topology.

    Checks record identity, parent uniqueness, parent existence, allowed
    geographic-level transitions, Region roots, cycles, and paths terminating
    at a Region. This function does not modify the hierarchy or write to D1.
    """
    findings: list[dict[str, Any]] = []

    release_id = hierarchy.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        findings.append(
            _finding("INVALID_RELEASE_ID", "Hierarchy must have a non-empty release ID.")
        )

    records_by_code: dict[str, Mapping[str, Any]] = {}

    for record in normalized.get("records", []):
        code = _value(record, "psgc_code")

        if not isinstance(code, str) or len(code) != 10 or not code.isdigit():
            findings.append(
                _finding(
                    "INVALID_PSGC_CODE",
                    "Source record does not have a valid 10-digit PSGC code.",
                )
            )
            continue

        if code in records_by_code:
            findings.append(
                _finding(
                    "DUPLICATE_PSGC_CODE",
                    "More than one source record has this PSGC code.",
                    psgc_code=code,
                )
            )
            continue

        records_by_code[code] = record

    parent_by_child: dict[str, str] = {}
    edge_counts: Counter[tuple[str, str]] = Counter()

    for edge in hierarchy.get("edges", []):
        parent = edge.get("parent_psgc_code")
        child = edge.get("child_psgc_code")

        if edge.get("release_id") != release_id:
            findings.append(
                _finding(
                    "EDGE_RELEASE_MISMATCH",
                    "Hierarchy edge belongs to a different release.",
                    psgc_code=child if isinstance(child, str) else None,
                    parent_psgc_code=parent if isinstance(parent, str) else None,
                )
            )

        if edge.get("relationship_type") != "PARENT_OF":
            findings.append(
                _finding(
                    "INVALID_RELATIONSHIP_TYPE",
                    "Hierarchy edge relationship_type must be PARENT_OF.",
                    psgc_code=child if isinstance(child, str) else None,
                    parent_psgc_code=parent if isinstance(parent, str) else None,
                )
            )

        if edge.get("review_status") not in ALLOWED_REVIEW_STATUSES:
            findings.append(
                _finding(
                    "INVALID_REVIEW_STATUS",
                    "Hierarchy edge has an unsupported review status.",
                    psgc_code=child if isinstance(child, str) else None,
                    parent_psgc_code=parent if isinstance(parent, str) else None,
                )
            )

        if not isinstance(edge.get("evidence_reference"), str) or not edge[
            "evidence_reference"
        ].strip():
            findings.append(
                _finding(
                    "MISSING_EDGE_EVIDENCE",
                    "Hierarchy edge must have a non-empty evidence reference.",
                    psgc_code=child if isinstance(child, str) else None,
                    parent_psgc_code=parent if isinstance(parent, str) else None,
                )
            )

        if not isinstance(edge.get("rationale"), str) or not edge[
            "rationale"
        ].strip():
            findings.append(
                _finding(
                    "MISSING_EDGE_RATIONALE",
                    "Hierarchy edge must have a non-empty rationale.",
                    psgc_code=child if isinstance(child, str) else None,
                    parent_psgc_code=parent if isinstance(parent, str) else None,
                )
            )

        if not isinstance(parent, str) or not isinstance(child, str):
            findings.append(
                _finding("INVALID_EDGE_CODE", "Edge must contain parent and child PSGC codes.")
            )
            continue

        edge_counts[(parent, child)] += 1

        if parent not in records_by_code:
            findings.append(
                _finding(
                    "MISSING_PARENT_RECORD",
                    "Parent code does not exist in this release.",
                    psgc_code=child,
                    parent_psgc_code=parent,
                )
            )

        if child not in records_by_code:
            findings.append(
                _finding(
                    "MISSING_CHILD_RECORD",
                    "Child code does not exist in this release.",
                    psgc_code=child,
                    parent_psgc_code=parent,
                )
            )

        if parent == child:
            findings.append(
                _finding(
                    "SELF_PARENT",
                    "A record cannot be its own parent.",
                    psgc_code=child,
                    parent_psgc_code=parent,
                )
            )

        if child in parent_by_child:
            findings.append(
                _finding(
                    "MULTIPLE_PARENTS",
                    "A record has more than one proposed immediate parent.",
                    psgc_code=child,
                    parent_psgc_code=parent,
                )
            )
        else:
            parent_by_child[child] = parent

        parent_record = records_by_code.get(parent)
        child_record = records_by_code.get(child)

        if parent_record is not None and child_record is not None:
            parent_level = _value(parent_record, "geographic_level")
            child_level = _value(child_record, "geographic_level")

            if not _is_allowed_transition(
                parent_level,
                child_level,
                parent,
                child,
            ):
                findings.append(
                    _finding(
                        "INVALID_LEVEL_TRANSITION",
                        (
                            "Parent-child geographic-level transition is not "
                            f"allowed: {parent_level!r} -> {child_level!r}."
                        ),
                        psgc_code=child,
                        parent_psgc_code=parent,
                    )
                )

    for (parent, child), count in edge_counts.items():
        if count > 1:
            findings.append(
                _finding(
                    "DUPLICATE_EDGE",
                    "The same parent-child edge appears more than once.",
                    psgc_code=child,
                    parent_psgc_code=parent,
                )
            )

    for code, record in records_by_code.items():
        level = _value(record, "geographic_level")

        if level == "Reg":
            if code in parent_by_child:
                findings.append(
                    _finding(
                        "REGION_HAS_PARENT",
                        "A Region must be a hierarchy root.",
                        psgc_code=code,
                        parent_psgc_code=parent_by_child[code],
                    )
                )
        elif code not in parent_by_child:
            findings.append(
                _finding(
                    "MISSING_PARENT",
                    "Every non-Region record must have exactly one immediate parent.",
                    psgc_code=code,
                )
            )

    depth_by_code: dict[str, int] = {}

    for start_code in records_by_code:
        current = start_code
        visited: set[str] = set()
        depth = 0

        while current in parent_by_child:
            if current in visited:
                findings.append(
                    _finding(
                        "HIERARCHY_CYCLE",
                        "Parent chain contains a cycle.",
                        psgc_code=start_code,
                    )
                )
                break

            visited.add(current)
            parent = parent_by_child[current]

            if parent not in records_by_code:
                break

            current = parent
            depth += 1
        else:
            if current in records_by_code:
                if _value(records_by_code[current], "geographic_level") == "Reg":
                    depth_by_code[start_code] = depth
                else:
                    findings.append(
                        _finding(
                            "PATH_DOES_NOT_END_AT_REGION",
                            "Parent chain does not terminate at a Region.",
                            psgc_code=start_code,
                        )
                    )

    finding_counts = Counter(item["code"] for item in findings)

    return {
        "release_id": release_id,
        "record_count": len(records_by_code),
        "edge_count": len(hierarchy.get("edges", [])),
        "validated_path_count": len(depth_by_code),
        "maximum_depth": max(depth_by_code.values(), default=0),
        "is_valid": not findings,
        "error_count": len(findings),
        "finding_counts": dict(sorted(finding_counts.items())),
        "findings": findings,
    }
