"""Versioned registry of deterministic PSGC validation rules."""

from __future__ import annotations

from dataclasses import dataclass

VALIDATION_RULESET_VERSION = "1.0"


@dataclass(frozen=True)
class ValidationRule:
    rule_id: str
    severity: str
    description: str


RULES = {
    rule.rule_id: rule
    for rule in (
        ValidationRule(
            "PSGC001",
            "ERROR",
            "Missing required PSGC code.",
        ),
        ValidationRule(
            "PSGC002",
            "ERROR",
            "PSGC code does not match the selected release format.",
        ),
        ValidationRule(
            "PSGC003",
            "ERROR",
            "Duplicate PSGC code within the release.",
        ),
        ValidationRule(
            "PSGC004",
            "ERROR",
            "Missing required geographic name.",
        ),
        ValidationRule(
            "PSGC005",
            "ERROR",
            "Population contains an unsupported source representation.",
        ),
        ValidationRule(
            "PSGC006",
            "REVIEW",
            "Population formula has no usable cached result.",
        ),
        ValidationRule(
            "PSGC007",
            "REVIEW",
            "Duplicate correspondence code within the release.",
        ),
        ValidationRule(
            "PSGC008",
            "REVIEW",
            "Unrecognized geographic level.",
        ),
        ValidationRule(
            "PSGC009",
            "WARNING",
            "PSGC code is stored in an Excel numeric cell.",
        ),
        ValidationRule(
            "PSGC010",
            "WARNING",
            "Correspondence code is stored in an Excel numeric cell.",
        ),
    )
}
