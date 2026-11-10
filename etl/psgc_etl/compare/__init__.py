"""Release comparison and identity-continuity candidate discovery."""

from psgc_etl.compare.release_comparator import (
    COMPARABLE_FIELDS,
    compare_hierarchy_edges,
    compare_normalized_releases,
)

__all__ = [
    "COMPARABLE_FIELDS",
    "compare_hierarchy_edges",
    "compare_normalized_releases",
]
