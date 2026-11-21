"""Tests for release-scoped hierarchy publication."""

import sqlite3

from psgc_etl.hierarchy.publisher import publish_hierarchy


def _database(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE releases (release_id TEXT PRIMARY KEY);

        CREATE TABLE source_records (
            release_id TEXT NOT NULL,
            psgc_code TEXT NOT NULL,
            PRIMARY KEY (release_id, psgc_code)
        );

        CREATE TABLE source_record_version_memberships (
            release_id TEXT NOT NULL,
            psgc_code TEXT NOT NULL,
            version_id TEXT NOT NULL,
            PRIMARY KEY (release_id, psgc_code)
        );

        CREATE TABLE source_record_versions (
            version_id TEXT NOT NULL,
            psgc_code TEXT NOT NULL,
            geographic_level TEXT,
            PRIMARY KEY (version_id, psgc_code)
        );

        CREATE TABLE record_hierarchy (
            release_id TEXT NOT NULL,
            parent_psgc_code TEXT NOT NULL,
            child_psgc_code TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            evidence_reference TEXT,
            rationale TEXT,
            review_status TEXT NOT NULL
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
            details_json TEXT NOT NULL DEFAULT '{}',
            occurred_at TEXT NOT NULL
        );

        INSERT INTO releases VALUES ('2026-Q3');

        INSERT INTO source_records VALUES
            ('2026-Q3', '0100000000'),
            ('2026-Q3', '0100100000');

        INSERT INTO source_record_version_memberships VALUES
            ('2026-Q3', '0100000000', 'version-region'),
            ('2026-Q3', '0100100000', 'version-municipality');

        INSERT INTO source_record_versions VALUES
            ('version-region', '0100000000', 'Reg'),
            ('version-municipality', '0100100000', 'Mun');

        INSERT INTO record_hierarchy VALUES (
            '2026-Q3',
            '0100000000',
            '0100100000',
            'PARENT_OF',
            'PSA PSGC publication',
            'Municipality belongs to Region',
            'APPROVED'
        );
        """
    )
    connection.commit()
    connection.close()


def _publication(path):
    connection = sqlite3.connect(path)
    row = connection.execute(
        """
        SELECT publication_status, record_count, approved_edge_count,
               publication_reference
        FROM hierarchy_publications
        WHERE release_id = '2026-Q3'
        """
    ).fetchone()
    connection.close()
    return row


def test_valid_approved_hierarchy_is_published(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database)

    result = publish_hierarchy(
        "2026-Q3",
        published_by="Test Operator",
        database_path=database,
        publication_reference="PSA 2026 Q3 hierarchy review",
    )

    assert result["published"] is True
    assert result["validation"]["is_valid"] is True
    assert _publication(database) == (
        "PUBLISHED",
        2,
        1,
        "PSA 2026 Q3 hierarchy review",
    )
    connection = sqlite3.connect(database)
    event = connection.execute(
        """
        SELECT event_type, previous_status, new_status, actor, rationale,
               details_json
        FROM release_audit_log
        WHERE release_id = '2026-Q3'
        """
    ).fetchone()
    connection.close()
    assert event[:5] == (
        "HIERARCHY_PUBLISHED", None, "PUBLISHED", "Test Operator",
        "PSA 2026 Q3 hierarchy review",
    )
    assert '"record_count": 2' in event[5]
    assert '"approved_edge_count": 1' in event[5]


def test_validate_only_does_not_create_publication(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database)

    result = publish_hierarchy(
        "2026-Q3",
        database_path=database,
        validate_only=True,
    )

    assert result["validation"]["is_valid"] is True
    assert result["publication_status"] == "VALIDATION_PASSED"
    assert _publication(database) is None


def test_proposed_edge_does_not_satisfy_approved_hierarchy(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database)

    connection = sqlite3.connect(database)
    connection.execute(
        """
        UPDATE record_hierarchy
        SET review_status = 'PROPOSED'
        WHERE release_id = '2026-Q3'
        """
    )
    connection.commit()
    connection.close()

    result = publish_hierarchy(
        "2026-Q3",
        database_path=database,
        validate_only=True,
    )

    assert result["approved_edge_count"] == 0
    assert result["validation"]["is_valid"] is False
    assert result["publication_status"] == "NOT_PUBLISHED"
    assert _publication(database) is None


def test_failed_republication_preserves_existing_publication(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database)

    publish_hierarchy(
        "2026-Q3",
        published_by="Test Operator",
        database_path=database,
        publication_reference="Original approved publication",
    )
    original = _publication(database)

    connection = sqlite3.connect(database)
    connection.execute(
        """
        UPDATE record_hierarchy
        SET review_status = 'PROPOSED'
        WHERE release_id = '2026-Q3'
        """
    )
    connection.commit()
    connection.close()

    result = publish_hierarchy(
        "2026-Q3",
        published_by="Test Operator",
        database_path=database,
        publication_reference="Attempted replacement",
    )

    assert result["validation"]["is_valid"] is False
    assert result["published"] is False
    assert _publication(database) == original


def test_republication_after_withdrawal_records_previous_status(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database)

    publish_hierarchy(
        "2026-Q3",
        published_by="First Operator",
        database_path=database,
        publication_reference="Initial publication",
    )

    connection = sqlite3.connect(database)
    connection.execute(
        """
        UPDATE hierarchy_publications
        SET publication_status = 'WITHDRAWN'
        WHERE release_id = '2026-Q3'
        """
    )
    connection.commit()
    connection.close()

    publish_hierarchy(
        "2026-Q3",
        published_by="Second Operator",
        database_path=database,
        publication_reference="Republication after review",
    )

    connection = sqlite3.connect(database)
    event = connection.execute(
        """
        SELECT previous_status, new_status, actor
        FROM release_audit_log
        WHERE event_type = 'HIERARCHY_PUBLISHED'
        ORDER BY rowid DESC
        LIMIT 1
        """
    ).fetchone()
    connection.close()
    assert event == ("WITHDRAWN", "PUBLISHED", "Second Operator")


def test_audit_insert_failure_rolls_back_publication(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database)

    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TRIGGER reject_publication_audit
        BEFORE INSERT ON release_audit_log
        WHEN NEW.event_type = 'HIERARCHY_PUBLISHED'
        BEGIN
            SELECT RAISE(ABORT, 'simulated audit failure');
        END;
        """
    )
    connection.commit()
    connection.close()

    try:
        publish_hierarchy(
            "2026-Q3",
            published_by="Test Operator",
            database_path=database,
            publication_reference="Should roll back",
        )
    except sqlite3.IntegrityError as error:
        assert "simulated audit failure" in str(error)
    else:
        raise AssertionError("Expected audit insertion to fail")

    assert _publication(database) is None
    connection = sqlite3.connect(database)
    event_count = connection.execute(
        "SELECT COUNT(*) FROM release_audit_log"
    ).fetchone()[0]
    connection.close()
    assert event_count == 0


def test_missing_version_membership_refuses_publication(tmp_path):
    database = tmp_path / "test.sqlite"
    _database(database)

    connection = sqlite3.connect(database)
    connection.execute(
        """
        DELETE FROM source_record_version_memberships
        WHERE release_id = '2026-Q3'
          AND psgc_code = '0100100000'
        """
    )
    connection.commit()
    connection.close()

    try:
        publish_hierarchy(
            "2026-Q3",
            database_path=database,
            publication_reference="Should not publish",
        )
    except ValueError as error:
        assert "without version membership" in str(error)
    else:
        raise AssertionError("Expected missing version membership to fail")

    assert _publication(database) is None
