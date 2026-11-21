"""Tests for release-scoped hierarchy withdrawal."""

import json
import sqlite3

import pytest

from psgc_etl.hierarchy.withdrawal import withdraw_hierarchy


def _database(path, status="PUBLISHED"):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE releases (
            release_id TEXT PRIMARY KEY
        );

        CREATE TABLE hierarchy_publications (
            release_id TEXT PRIMARY KEY,
            publication_status TEXT NOT NULL,
            record_count INTEGER NOT NULL,
            approved_edge_count INTEGER NOT NULL,
            published_at TEXT NOT NULL,
            publication_reference TEXT NOT NULL
        );

        CREATE TABLE release_audit_log (
            audit_id TEXT PRIMARY KEY,
            release_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            previous_status TEXT,
            new_status TEXT,
            actor TEXT NOT NULL,
            rationale TEXT,
            details_json TEXT NOT NULL DEFAULT '{}'
                CHECK (json_valid(details_json)),
            occurred_at TEXT NOT NULL,
            FOREIGN KEY (release_id) REFERENCES releases (release_id)
        );

        INSERT INTO releases VALUES ('2026-Q3');

        INSERT INTO hierarchy_publications VALUES (
            '2026-Q3', 'PUBLISHED', 2, 1,
            '2026-11-21T00:00:00Z', 'PSA review reference'
        );
        """
    )

    if status != "PUBLISHED":
        connection.execute(
            """
            UPDATE hierarchy_publications
            SET publication_status = ?
            WHERE release_id = '2026-Q3'
            """,
            (status,),
        )

    connection.commit()
    connection.close()


def test_withdraw_published_hierarchy_and_record_audit(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database)

    result = withdraw_hierarchy(
        "2026-Q3",
        database_path=database,
        withdrawn_by="operator@example.test",
        reason="Correction required after review.",
    )

    assert result["publication_status"] == "WITHDRAWN"

    connection = sqlite3.connect(database)
    publication = connection.execute(
        """
        SELECT publication_status
        FROM hierarchy_publications
        WHERE release_id = '2026-Q3'
        """
    ).fetchone()
    event = connection.execute(
        """
        SELECT event_type, previous_status, new_status, actor, rationale,
               details_json
        FROM release_audit_log
        WHERE release_id = '2026-Q3'
        """
    ).fetchone()
    connection.close()

    assert publication == ("WITHDRAWN",)
    assert event[:5] == (
        "HIERARCHY_WITHDRAWN",
        "PUBLISHED",
        "WITHDRAWN",
        "operator@example.test",
        "Correction required after review.",
    )
    assert json.loads(event[5]) == {
        "published_at": "2026-11-21T00:00:00Z",
        "publication_reference": "PSA review reference",
    }


def test_withdrawal_rejects_unknown_release(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database)

    with pytest.raises(ValueError, match="Unknown release"):
        withdraw_hierarchy(
            "2025-Q1",
            database_path=database,
            withdrawn_by="operator",
            reason="Correction required.",
        )


def test_withdrawal_rejects_missing_publication(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database)

    connection = sqlite3.connect(database)
    connection.execute("DELETE FROM hierarchy_publications")
    connection.commit()
    connection.close()

    with pytest.raises(ValueError, match="no hierarchy publication"):
        withdraw_hierarchy(
            "2026-Q3",
            database_path=database,
            withdrawn_by="operator",
            reason="Correction required.",
        )


def test_withdrawal_rejects_already_withdrawn_publication(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database, status="WITHDRAWN")

    with pytest.raises(ValueError, match="only PUBLISHED"):
        withdraw_hierarchy(
            "2026-Q3",
            database_path=database,
            withdrawn_by="operator",
            reason="Correction required.",
        )


def test_withdrawal_requires_actor_and_reason(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database)

    with pytest.raises(ValueError, match="actor"):
        withdraw_hierarchy(
            "2026-Q3",
            database_path=database,
            withdrawn_by=" ",
            reason="Correction required.",
        )

    with pytest.raises(ValueError, match="reason"):
        withdraw_hierarchy(
            "2026-Q3",
            database_path=database,
            withdrawn_by="operator",
            reason=" ",
        )


def test_audit_insert_failure_rolls_back_withdrawal(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database)

    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TRIGGER reject_withdrawal_audit
        BEFORE INSERT ON release_audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit unavailable');
        END;
        """
    )
    connection.commit()
    connection.close()

    with pytest.raises(sqlite3.IntegrityError, match="audit unavailable"):
        withdraw_hierarchy(
            "2026-Q3",
            database_path=database,
            withdrawn_by="operator",
            reason="Correction required.",
        )

    connection = sqlite3.connect(database)
    status = connection.execute(
        """
        SELECT publication_status
        FROM hierarchy_publications
        WHERE release_id = '2026-Q3'
        """
    ).fetchone()[0]
    connection.close()

    assert status == "PUBLISHED"
