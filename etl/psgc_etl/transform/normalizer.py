"""Loss-conscious normalization of extracted PSGC source records."""

from __future__ import annotations

import math
from typing import Any

NORMALIZATION_PROFILE_VERSION = "1.1"
MAX_SAFE_INTEGER = 2**53 - 1

IDENTIFIER_FIELDS = {
    "psgc_code",
    "correspondence_code",
}


def _whole_number_as_string(value: Any) -> str | None:
    """Convert a safe, non-negative whole number to decimal-free text."""
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        if 0 <= value <= MAX_SAFE_INTEGER:
            return str(value)
        return None

    if (
        isinstance(value, float)
        and math.isfinite(value)
        and value.is_integer()
        and 0 <= value <= MAX_SAFE_INTEGER
    ):
        return str(int(value))

    return None


def _normalize_identifier(cell: dict[str, Any]) -> dict[str, Any]:
    raw_value = cell["raw_value"]

    if raw_value is None:
        return {
            "normalized_value": None,
            "normalization_action": "SOURCE_BLANK",
            "normalization_status": "MISSING",
            "normalized_value_origin": "SOURCE",
        }

    if isinstance(raw_value, str):
        return {
            "normalized_value": raw_value,
            "normalization_action": "PASSTHROUGH",
            "normalization_status": "VALID",
            "normalized_value_origin": "SOURCE",
        }

    converted = _whole_number_as_string(raw_value)

    if converted is not None:
        return {
            "normalized_value": converted,
            "normalization_action": "NUMERIC_INTEGER_TO_STRING",
            "normalization_status": "VALID",
            "normalized_value_origin": "SOURCE",
        }

    return {
        "normalized_value": None,
        "normalization_action": "UNSUPPORTED_NUMERIC_REPRESENTATION",
        "normalization_status": "REVIEW",
        "normalized_value_origin": "SOURCE",
    }


def _normalize_population(cell: dict[str, Any]) -> dict[str, Any]:
    is_formula = cell["cell_data_type"] == "f"

    if is_formula:
        value = cell["cached_value"]

        if value is None:
            return {
                "normalized_value": None,
                "normalization_action": "FORMULA_CACHE_MISSING",
                "normalization_status": "REVIEW",
                "normalized_value_origin": "FORMULA_CACHE",
            }

        origin = "FORMULA_CACHE"
    else:
        value = cell["raw_value"]
        origin = "SOURCE"

    if value is None:
        return {
            "normalized_value": None,
            "normalization_action": "SOURCE_BLANK",
            "normalization_status": "MISSING",
            "normalized_value_origin": origin,
        }

    if isinstance(value, str) and value == "-":
        return {
            "normalized_value": None,
            "normalization_action": "MISSING_MARKER",
            "normalization_status": "MISSING",
            "normalized_value_origin": origin,
        }

    if isinstance(value, bool):
        return {
            "normalized_value": None,
            "normalization_action": "UNSUPPORTED_POPULATION_TYPE",
            "normalization_status": "REVIEW",
            "normalized_value_origin": origin,
        }

    if isinstance(value, int) and 0 <= value <= MAX_SAFE_INTEGER:
        return {
            "normalized_value": value,
            "normalization_action": (
                "FORMULA_CACHED_NUMERIC" if is_formula else "SOURCE_NUMERIC"
            ),
            "normalization_status": "VALID",
            "normalized_value_origin": origin,
        }

    if (
        isinstance(value, float)
        and math.isfinite(value)
        and value.is_integer()
        and 0 <= value <= MAX_SAFE_INTEGER
    ):
        return {
            "normalized_value": int(value),
            "normalization_action": (
                "FORMULA_CACHED_NUMERIC" if is_formula else "SOURCE_NUMERIC"
            ),
            "normalization_status": "VALID",
            "normalized_value_origin": origin,
        }

    return {
        "normalized_value": None,
        "normalization_action": "UNSUPPORTED_POPULATION_VALUE",
        "normalization_status": "REVIEW",
        "normalized_value_origin": origin,
    }


def _normalize_cell(
    field_name: str,
    cell: dict[str, Any],
) -> dict[str, Any]:
    if field_name in IDENTIFIER_FIELDS:
        result = _normalize_identifier(cell)
    elif field_name == "population":
        result = _normalize_population(cell)
    else:
        result = {
            "normalized_value": cell["raw_value"],
            "normalization_action": "PASSTHROUGH",
            "normalization_status": "VALID",
            "normalized_value_origin": "SOURCE",
        }

    return {
        **cell,
        **result,
    }


def normalize_psgc_records(extraction: dict[str, Any]) -> dict[str, Any]:
    """Normalize extracted records without modifying the extraction result."""
    normalized_records = []

    for record in extraction["records"]:
        normalized_cells = {
            field_name: _normalize_cell(field_name, cell)
            for field_name, cell in record["cells"].items()
        }

        normalized_records.append(
            {
                "source_record_id": record["source_record_id"],
                "worksheet_name": record["worksheet_name"],
                "source_row_number": record["source_row_number"],
                "cells": normalized_cells,
            }
        )

    return {
        "normalization_profile_version": NORMALIZATION_PROFILE_VERSION,
        "source_artifact": extraction["source_artifact"],
        "worksheet_name": extraction["worksheet_name"],
        "source_headers": extraction["source_headers"],
        "column_mapping": extraction["column_mapping"],
        "record_count": len(normalized_records),
        "records": normalized_records,
    }
