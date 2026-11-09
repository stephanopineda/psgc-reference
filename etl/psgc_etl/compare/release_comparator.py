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
        "correspondence_code": _normalized_value(
            record, "correspondence_code"
        ),
        "geographic_level": _normalized_value(
            record, "geographic_level"
        ),
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
    return {
        "release_id": release_id,
        "source_artifact": normalized_release.get("source_artifact"),
        "worksheet_name": normalized_release.get("worksheet_name"),
        "record_count": normalized_release.get("record_count"),
    }


def _candidate_groups(
    removed_records: list[dict[str, Any]],
    added_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    removed_by_correspondence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    added_by_correspondence: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for record in removed_records:
        correspondence_code = _normalized_value(
            record, "correspondence_code"
        )
        if isinstance(correspondence_code, str) and correspondence_code:
            removed_by_correspondence[correspondence_code].append(record)

    for record in added_records:
        correspondence_code = _normalized_value(
            record, "correspondence_code"
        )
        if isinstance(correspondence_code, str) and correspondence_code:
            added_by_correspondence[correspondence_code].append(record)

    groups: list[dict[str, Any]] = []

    shared_codes = sorted(
        removed_by_correspondence.keys() & added_by_correspondence.keys()
    )

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
            "ONE_TO_ONE"
            if len(previous) == 1 and len(current) == 1
            else "AMBIGUOUS"
        )

        groups.append(
            {
                "correspondence_code": correspondence_code,
                "relationship_type": relationship_type,
                "review_status": "REVIEW_REQUIRED",
                "previous_records": [
                    _record_summary(record) for record in previous
                ],
                "current_records": [
                    _record_summary(record) for record in current
                ],
            }
        )

    return groups


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

    changed_records: list[dict[str, Any]] = []

    for code in matched_codes:
        previous_record = previous[code]
        current_record = current[code]
        changes: list[dict[str, Any]] = []

        for field_name in COMPARABLE_FIELDS:
            before = _normalized_value(previous_record, field_name)
            after = _normalized_value(current_record, field_name)

            if before != after:
                changes.append(
                    {
                        "field_name": field_name,
                        "before": _value_snapshot(
                            previous_record, field_name
                        ),
                        "after": _value_snapshot(
                            current_record, field_name
                        ),
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
        "comparison_version": "1.0",
        "previous_release": _release_metadata(
            previous_release, previous_release_id
        ),
        "current_release": _release_metadata(
            current_release, current_release_id
        ),
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
        "added_records": [
            _record_summary(record) for record in added_records
        ],
        "removed_records": [
            _record_summary(record) for record in removed_records
        ],
        "changed_records": changed_records,
        "identity_candidate_groups": candidate_groups,
    }
