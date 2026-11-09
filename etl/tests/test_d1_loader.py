"""Tests for D1 loader evidence and release metadata."""

from psgc_etl.load.d1_loader import (
    _normalization_events,
    _release_metadata,
)


def test_source_adapter_event_preserves_raw_value_and_rationale():
    rationale = "Documented source-specific exception; review required."
    record = {
        "cells": {
            "population": {
                "normalization_action": "KNOWN_SOURCE_ERROR_AS_MISSING",
                "normalization_status": "REVIEW",
                "normalized_value_origin": "SOURCE",
                "raw_value": "#N/A",
                "normalized_value": None,
                "normalization_rationale": rationale,
            }
        }
    }

    events = _normalization_events(record)

    assert events["population"] == {
        "action": "KNOWN_SOURCE_ERROR_AS_MISSING",
        "status": "REVIEW",
        "value_origin": "SOURCE",
        "raw_value": "#N/A",
        "normalized_value": None,
        "rationale": rationale,
    }


def test_release_manifest_includes_2026_q3():
    from pathlib import Path

    metadata = _release_metadata(
        Path("PSGC-3Q-2026-Publication-Datafile.xlsx")
    )

    assert metadata == {
        "release_id": "2026-Q3",
        "publication_date": "2026-09-30",
    }


def test_finding_evidence_preserves_normalization_context():
    import json
    import sqlite3

    from psgc_etl.load.d1_loader import _insert_findings

    connection = sqlite3.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE validation_findings (
            finding_id TEXT,
            release_id TEXT,
            psgc_code TEXT,
            rule_id TEXT,
            severity TEXT,
            message TEXT,
            disposition TEXT,
            evidence_json TEXT
        )
        """
    )

    rationale = "Known source error; retained for manual review."
    normalized = {
        "records": [
            {
                "source_record_id": "row-35444",
                "cells": {
                    "psgc_code": {"normalized_value": "0990100000"},
                    "population": {
                        "normalization_action": "KNOWN_SOURCE_ERROR_AS_MISSING",
                        "normalization_rationale": rationale,
                    },
                },
            }
        ]
    }
    validation = {
        "findings": [
            {
                "source_record_id": "row-35444",
                "rule_id": "PSGC011",
                "severity": "REVIEW",
                "message": rationale,
                "worksheet_name": "PSGC",
                "source_row_number": 35444,
                "field_name": "population",
                "source_coordinate": "J35444",
                "source_value": "#N/A",
                "normalized_value": None,
            }
        ]
    }

    inserted = _insert_findings(
        connection,
        "2026-Q3",
        validation,
        normalized,
    )

    assert inserted == 1

    row = connection.execute(
        """
        SELECT psgc_code, evidence_json
        FROM validation_findings
        """
    ).fetchone()

    assert row[0] == "0990100000"

    evidence = json.loads(row[1])
    assert evidence["normalization_action"] == (
        "KNOWN_SOURCE_ERROR_AS_MISSING"
    )
    assert evidence["normalization_rationale"] == rationale

    connection.close()
