"""Deterministic comparison of normalized PSGC publication releases."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

COMPARABLE_FIELDS = (
    "name",
    "correspondence_code",
    "geographic_level",
    "old_names",
    "city_class",
    "income_classification",
    "urban_rural",
    "population",
    "population_annotation",
    "source_status_value",
)


def _cell(record: dict[str, Any], field_name: str) -> dict[str, Any]:
    """Return a normalized cell, or an empty mapping when absent."""
    value = record.get("cells", {}).get(field_name)
    return value if isinstance(value, dict) else {}


def _normalized_value(record: dict[str, Any], field_name: str) -> Any:
    return _cell(record, field_name).get("normalized_value")


def _source_reference(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_record_id": record.get("source_record_id"),
        "source_row_number": record.get("source_row_number"),
        "worksheet_name": record.get("worksheet_name"),
    }


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        **_source_reference(record),
        "psgc_code": _normalized_value(record, "psgc_code"),
        "name": _normalized_value(record, "name"),
        "correspondence_code": _normalized_value(record, "correspondence_code"),
        "geographic_level": _normalized_value(record, "geographic_level"),
    }


def _value_snapshot(
    record: dict[str, Any],
    field_name: str,
) -> dict[str, Any]:
    cell = _cell(record, field_name)

    return {
        "normalized_value": cell.get("normalized_value"),
        "raw_value": cell.get("raw_value"),
        "normalization_status": cell.get("normalization_status"),
        "normalization_action": cell.get("normalization_action"),
        "source_coordinate": cell.get("coordinate"),
        **_source_reference(record),
    }


def _index_records(
    normalized_release: dict[str, Any],
    release_label: str,
) -> dict[str, dict[str, Any]]:
    records = normalized_release.get("records")

    if not isinstance(records, list):
        raise TypeError(f"{release_label} release must contain a records list")

    indexed: dict[str, dict[str, Any]] = {}

    for record in records:
        if not isinstance(record, dict):
            raise TypeError(f"{release_label} release contains an invalid record")

        code = _normalized_value(record, "psgc_code")

        if not isinstance(code, str) or not code:
            row_number = record.get("source_row_number")
            raise ValueError(
                f"{release_label} release contains a missing or invalid "
                f"normalized PSGC code at source row {row_number}"
            )

        if code in indexed:
            first_row = indexed[code].get("source_row_number")
            duplicate_row = record.get("source_row_number")
            raise ValueError(
                f"{release_label} release contains duplicate PSGC code "
                f"{code!r} at source rows {first_row} and {duplicate_row}"
            )

        indexed[code] = record

    return indexed


def _release_metadata(
    normalized_release: dict[str, Any],
    release_id: str | None,
) -> dict[str, Any]:
    metadata = normalized_release.get("source_metadata", {})
    return {
        "release_id": release_id,
        "source_artifact": normalized_release.get("source_artifact"),
        "worksheet_name": normalized_release.get("worksheet_name"),
        "record_count": normalized_release.get("record_count"),
        "source_profile_id": normalized_release.get("source_profile_id"),
        "extraction_profile_version": normalized_release.get("extraction_profile_version"),
        "population_reference_year": metadata.get("population_reference_year"),
        "urban_rural_reference_year": metadata.get("urban_rural_reference_year"),
        "income_classification_basis": metadata.get("income_classification_basis"),
    }


def _candidate_groups(
    removed_records: list[dict[str, Any]],
    added_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    removed_by_correspondence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    added_by_correspondence: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for record in removed_records:
        correspondence_code = _normalized_value(record, "correspondence_code")
        if isinstance(correspondence_code, str) and correspondence_code:
            removed_by_correspondence[correspondence_code].append(record)

    for record in added_records:
        correspondence_code = _normalized_value(record, "correspondence_code")
        if isinstance(correspondence_code, str) and correspondence_code:
            added_by_correspondence[correspondence_code].append(record)

    groups: list[dict[str, Any]] = []

    shared_codes = sorted(removed_by_correspondence.keys() & added_by_correspondence.keys())

    for correspondence_code in shared_codes:
        previous = sorted(
            removed_by_correspondence[correspondence_code],
            key=lambda record: record.get("source_row_number", 0),
        )
        current = sorted(
            added_by_correspondence[correspondence_code],
            key=lambda record: record.get("source_row_number", 0),
        )

        relationship_type = (
            "ONE_TO_ONE" if len(previous) == 1 and len(current) == 1 else "AMBIGUOUS"
        )

        groups.append(
            {
                "correspondence_code": correspondence_code,
                "relationship_type": relationship_type,
                "review_status": "REVIEW_REQUIRED",
                "previous_records": [_record_summary(record) for record in previous],
                "current_records": [_record_summary(record) for record in current],
            }
        )

    return groups


def _incomparable_fields(
    previous_release: dict[str, Any],
    current_release: dict[str, Any],
) -> list[dict[str, Any]]:
    """Identify attributes whose source reference bases differ."""
    previous_metadata = previous_release.get("source_metadata", {})
    current_metadata = current_release.get("source_metadata", {})

    basis_fields = {
        "population": "population_reference_year",
        "urban_rural": "urban_rural_reference_year",
        "income_classification": "income_classification_basis",
    }

    incomparable = []

    for field_name, metadata_key in basis_fields.items():
        previous_basis = previous_metadata.get(metadata_key)
        current_basis = current_metadata.get(metadata_key)

        if previous_basis != current_basis:
            incomparable.append(
                {
                    "field_name": field_name,
                    "basis_key": metadata_key,
                    "previous_basis": previous_basis,
                    "current_basis": current_basis,
                    "reason": "SOURCE_REFERENCE_BASIS_CHANGED",
                }
            )

    return incomparable


def compare_normalized_releases(
    previous_release: dict[str, Any],
    current_release: dict[str, Any],
    *,
    previous_release_id: str | None = None,
    current_release_id: str | None = None,
) -> dict[str, Any]:
    """Compare two normalized releases using PSGC codes as exact keys.

    The comparison reports record additions, removals, attribute changes,
    and correspondence-code candidate groups. It does not assign entity
    identities or determine whether a geographic entity was abolished.
    """
    previous = _index_records(previous_release, "Previous")
    current = _index_records(current_release, "Current")

    previous_codes = set(previous)
    current_codes = set(current)

    matched_codes = sorted(previous_codes & current_codes)
    removed_codes = sorted(previous_codes - current_codes)
    added_codes = sorted(current_codes - previous_codes)

    incomparable_fields = _incomparable_fields(previous_release, current_release)
    excluded_fields = {item["field_name"] for item in incomparable_fields}
    comparable_fields = tuple(field for field in COMPARABLE_FIELDS if field not in excluded_fields)

    changed_records: list[dict[str, Any]] = []

    for code in matched_codes:
        previous_record = previous[code]
        current_record = current[code]
        changes: list[dict[str, Any]] = []

        for field_name in comparable_fields:
            before = _normalized_value(previous_record, field_name)
            after = _normalized_value(current_record, field_name)

            if before != after:
                changes.append(
                    {
                        "field_name": field_name,
                        "before": _value_snapshot(previous_record, field_name),
                        "after": _value_snapshot(current_record, field_name),
                    }
                )

        if changes:
            changed_records.append(
                {
                    "psgc_code": code,
                    "previous_record": _record_summary(previous_record),
                    "current_record": _record_summary(current_record),
                    "changes": changes,
                }
            )

    removed_records = [previous[code] for code in removed_codes]
    added_records = [current[code] for code in added_codes]

    candidate_groups = _candidate_groups(
        removed_records,
        added_records,
    )

    unchanged_count = len(matched_codes) - len(changed_records)

    return {
        "comparison_version": "1.1",
        "previous_release": _release_metadata(previous_release, previous_release_id),
        "current_release": _release_metadata(current_release, current_release_id),
        "summary": {
            "previous_record_count": len(previous),
            "current_record_count": len(current),
            "matched_count": len(matched_codes),
            "unchanged_count": unchanged_count,
            "changed_count": len(changed_records),
            "added_count": len(added_records),
            "removed_count": len(removed_records),
            "candidate_group_count": len(candidate_groups),
        },
        "added_records": [_record_summary(record) for record in added_records],
        "removed_records": [
            {
                **_record_summary(record),
                "classification": "REMOVED_FROM_RELEASE",
            }
            for record in removed_records
        ],
        "changed_records": changed_records,
        "incomparable_fields": incomparable_fields,
        "identity_candidate_groups": candidate_groups,
    }


def _index_hierarchy_edges(
    edges: list[dict[str, Any]],
    release_label: str,
) -> dict[str, dict[str, Any]]:
    """Index proposed hierarchy edges by child PSGC code."""
    if not isinstance(edges, list):
        raise TypeError(f"{release_label} hierarchy must contain an edges list")

    indexed: dict[str, dict[str, Any]] = {}

    for edge in edges:
        if not isinstance(edge, dict):
            raise TypeError(f"{release_label} hierarchy contains an invalid edge")

        child = edge.get("child_psgc_code")
        parent = edge.get("parent_psgc_code")

        if not isinstance(child, str) or not child:
            raise ValueError(f"{release_label} hierarchy contains an invalid child code")

        if not isinstance(parent, str) or not parent:
            raise ValueError(
                f"{release_label} hierarchy contains an invalid parent code for child {child}"
            )

        if child in indexed:
            raise ValueError(f"{release_label} hierarchy contains multiple edges for child {child}")

        indexed[child] = edge

    return indexed


def _edge_snapshot(edge: dict[str, Any]) -> dict[str, Any]:
    """Preserve the relationship and its source evidence."""
    return {
        "child_psgc_code": edge.get("child_psgc_code"),
        "parent_psgc_code": edge.get("parent_psgc_code"),
        "relationship_type": edge.get("relationship_type"),
        "review_status": edge.get("review_status"),
        "rationale": edge.get("rationale"),
        "evidence_reference": edge.get("evidence_reference"),
    }


def compare_hierarchy_edges(
    previous_edges: list[dict[str, Any]],
    current_edges: list[dict[str, Any]],
    *,
    previous_release_id: str | None = None,
    current_release_id: str | None = None,
) -> dict[str, Any]:
    """Compare proposed hierarchy relationships by child PSGC code.

    This compares topology only. It does not infer geographic identity,
    legal abolition, or the reason for a parent reassignment.
    """
    previous = _index_hierarchy_edges(previous_edges, "Previous")
    current = _index_hierarchy_edges(current_edges, "Current")

    previous_children = set(previous)
    current_children = set(current)

    retained_children = sorted(previous_children & current_children)
    added_children = sorted(current_children - previous_children)
    removed_children = sorted(previous_children - current_children)

    unchanged_edges: list[dict[str, Any]] = []
    changed_parent_relationships: list[dict[str, Any]] = []

    for child in retained_children:
        before = previous[child]
        after = current[child]

        before_parent = before["parent_psgc_code"]
        after_parent = after["parent_psgc_code"]

        if before_parent == after_parent:
            unchanged_edges.append(
                {
                    "child_psgc_code": child,
                    "edge": _edge_snapshot(after),
                }
            )
        else:
            changed_parent_relationships.append(
                {
                    "child_psgc_code": child,
                    "previous_edge": _edge_snapshot(before),
                    "current_edge": _edge_snapshot(after),
                }
            )

    added_edges = [_edge_snapshot(current[child]) for child in added_children]
    removed_edges = [
        {
            "classification": "REMOVED_FROM_HIERARCHY",
            "edge": _edge_snapshot(previous[child]),
        }
        for child in removed_children
    ]

    return {
        "comparison_version": "1.0",
        "previous_release_id": previous_release_id,
        "current_release_id": current_release_id,
        "summary": {
            "previous_edge_count": len(previous),
            "current_edge_count": len(current),
            "retained_child_count": len(retained_children),
            "unchanged_edge_count": len(unchanged_edges),
            "changed_parent_count": len(changed_parent_relationships),
            "added_edge_count": len(added_edges),
            "removed_edge_count": len(removed_edges),
        },
        "changed_parent_relationships": changed_parent_relationships,
        "added_edges": added_edges,
        "removed_edges": removed_edges,
    }
