"""Evidence-based, narrowly scoped adaptations for known PSA source anomalies."""

from __future__ import annotations

from typing import Any


def apply_source_adapters(
    cells: dict[str, dict[str, Any]],
    *,
    source_profile_id: str | None,
) -> None:
    """Apply documented source exceptions in place to normalized cells.

    The original raw value and Excel cell metadata are never modified.
    """
    psgc_code = cells.get("psgc_code", {}).get("normalized_value")
    population = cells.get("population")

    if (
        source_profile_id == "psa-2026-dof-074-2024"
        and psgc_code == "0990100000"
        and population is not None
        and population.get("field_name", "population") == "population"
        and population.get("cell_data_type") == "e"
        and population.get("raw_value") == "#N/A"
    ):
        population.update(
            {
                "normalized_value": None,
                "normalization_action": "KNOWN_SOURCE_ERROR_AS_MISSING",
                "normalization_status": "REVIEW",
                "normalized_value_origin": "SOURCE",
                "normalization_rationale": (
                    "The 3Q 2026 PSA source represents this record's "
                    "population as Excel #N/A. The same PSGC record has "
                    "a blank population in the 1Q 2024, 4Q 2024, and "
                    "1Q 2025 releases. Raw source value and error type "
                    "are retained; this interpretation requires review."
                ),
            }
        )
