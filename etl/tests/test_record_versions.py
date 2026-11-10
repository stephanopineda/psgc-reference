import sqlite3

from psgc_etl.load.d1_loader import _insert_records, _version_id


def _record(
    *,
    name="City of Isabela",
    population=None,
    source_name="City of Isabela",
):
    return {
        "source_record_id": "source-1",
        "source_row_number": 10,
        "cells": {
            "psgc_code": {"normalized_value": "0990100000"},
            "name": {"normalized_value": name},
            "correspondence_code": {"normalized_value": None},
            "geographic_level": {"normalized_value": "City"},
            "old_names": {"normalized_value": None},
            "city_class": {"normalized_value": None},
            "income_classification": {"normalized_value": None},
            "urban_rural": {"normalized_value": None},
            "population": {"normalized_value": population},
            "population_annotation": {"normalized_value": None},
            "source_status_value": {"normalized_value": None},
            **{
                field: {
                    "raw_value": source_name,
                    "normalization_action": "NONE",
                    "normalized_value": source_name,
                }
                for field in ()
            },
        },
    }


def _connection():
    connection = sqlite3.connect(":memory:")

    connection.executescript("""
        CREATE TABLE source_records (
            release_id TEXT NOT NULL,
            psgc_code TEXT NOT NULL,
            source_record_id TEXT NOT NULL,
            source_row_number INTEGER NOT NULL,
            PRIMARY KEY (release_id, psgc_code),
            UNIQUE (release_id, source_record_id),
            UNIQUE (release_id, source_row_number)
        );

        CREATE TABLE source_record_versions (
            version_id TEXT PRIMARY KEY,
            psgc_code TEXT NOT NULL,
            name TEXT NOT NULL,
            correspondence_code TEXT,
            geographic_level TEXT,
            old_names TEXT,
            city_class TEXT,
            income_classification TEXT,
            urban_rural TEXT,
            population INTEGER,
            population_annotation TEXT,
            source_status_value TEXT,
            source_values_json TEXT NOT NULL,
            normalization_events_json TEXT NOT NULL,
            UNIQUE (version_id, psgc_code)
        );

        CREATE TABLE source_record_version_memberships (
            release_id TEXT NOT NULL,
            psgc_code TEXT NOT NULL,
            version_id TEXT NOT NULL,
            PRIMARY KEY (release_id, psgc_code)
        );
    """)

    return connection


def _normalized(record):
    source_fields = (
        "psgc_code",
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

    for field in source_fields:
        record["cells"][field].setdefault("raw_value", record["cells"][field]["normalized_value"])
        record["cells"][field].setdefault("normalization_action", "NONE")

    return {"records": [record]}


def test_version_id_is_deterministic():
    record = {
        "psgc_code": "0990100000",
        "name": "City of Isabela",
        "correspondence_code": None,
        "geographic_level": "City",
        "old_names": None,
        "city_class": None,
        "income_classification": None,
        "urban_rural": None,
        "population": None,
        "population_annotation": None,
        "source_status_value": None,
        "source_values_json": "{}",
        "normalization_events_json": "{}",
    }

    assert _version_id(record) == _version_id(record)


def test_identical_records_share_version_across_releases():
    connection = _connection()
    record = _record()

    _insert_records(connection, "2025-Q1", _normalized(record))
    _insert_records(connection, "2026-Q3", _normalized(record))

    assert connection.execute(
        "SELECT COUNT(*) FROM source_record_versions"
    ).fetchone()[0] == 1

    assert connection.execute(
        "SELECT COUNT(*) FROM source_record_version_memberships"
    ).fetchone()[0] == 2

    source_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(source_records)"
        ).fetchall()
    }
    assert source_columns == {
        "release_id",
        "psgc_code",
        "source_record_id",
        "source_row_number",
    }

    memberships = connection.execute(
        """
        SELECT release_id, psgc_code, version_id
        FROM source_record_version_memberships
        ORDER BY release_id
        """
    ).fetchall()

    assert [row[0] for row in memberships] == ["2025-Q1", "2026-Q3"]
    assert all(row[1] == "0990100000" for row in memberships)
    assert memberships[0][2] == memberships[1][2]

    source_records = connection.execute(
        """
        SELECT release_id, psgc_code, source_record_id, source_row_number
        FROM source_records
        ORDER BY release_id
        """
    ).fetchall()

    assert len(source_records) == 2
    assert all(row[1] == "0990100000" for row in source_records)
    assert all(row[2] == "source-1" and row[3] == 10 for row in source_records)

    connection.close()


def test_changed_attributes_create_a_new_version():
    connection = _connection()

    _insert_records(
        connection,
        "2025-Q1",
        _normalized(_record(population=100)),
    )

    _insert_records(
        connection,
        "2026-Q3",
        _normalized(_record(population=200)),
    )

    assert connection.execute(
        "SELECT COUNT(*) FROM source_record_versions"
    ).fetchone()[0] == 2

    connection.close()


def test_conflicting_existing_version_payload_is_rejected():
    import pytest

    connection = _connection()
    record = _record()
    normalized = _normalized(record)

    _insert_records(connection, "2025-Q1", normalized)

    connection.execute(
        """
        UPDATE source_record_versions
        SET name = 'Conflicting Name'
        """
    )

    with pytest.raises(
        RuntimeError,
        match="Stored version payload conflicts",
    ):
        _insert_records(connection, "2026-Q3", normalized)

    connection.close()
