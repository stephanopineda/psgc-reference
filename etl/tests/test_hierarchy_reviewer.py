"""Tests for auditable hierarchy edge review."""

import sqlite3

import pytest

from psgc_etl.hierarchy.reviewer import review_hierarchy_edge

EDGE_ID = "edge-region-municipality"


def _database(path, *, publication_status=None):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE releases (
            release_id TEXT PRIMARY KEY
        );

        CREATE TABLE record_hierarchy (
            hierarchy_id TEXT PRIMARY KEY,
            release_id TEXT NOT NULL,
            review_status TEXT NOT NULL
        );

        CREATE TABLE hierarchy_publications (
            release_id TEXT PRIMARY KEY,
            publication_status TEXT NOT NULL
        );

        CREATE TABLE hierarchy_review_events (
            event_id TEXT PRIMARY KEY,
            hierarchy_id TEXT NOT NULL,
            previous_status TEXT NOT NULL
                CHECK (previous_status = 'PROPOSED'),
            new_status TEXT NOT NULL
                CHECK (new_status IN ('APPROVED', 'REJECTED')),
            reviewed_by TEXT NOT NULL
                CHECK (length(trim(reviewed_by)) > 0),
            reviewed_at TEXT NOT NULL,
            decision_note TEXT NOT NULL
                CHECK (length(trim(decision_note)) > 0),
            FOREIGN KEY (hierarchy_id)
                REFERENCES record_hierarchy (hierarchy_id)
        );

        CREATE TRIGGER hierarchy_review_events_no_update
        BEFORE UPDATE ON hierarchy_review_events
        BEGIN
            SELECT RAISE(ABORT, 'hierarchy review events are immutable');
        END;

        CREATE TRIGGER hierarchy_review_events_no_delete
        BEFORE DELETE ON hierarchy_review_events
        BEGIN
            SELECT RAISE(ABORT, 'hierarchy review events are immutable');
        END;

        INSERT INTO releases VALUES ('2026-Q3');

        INSERT INTO record_hierarchy VALUES (
            'edge-region-municipality',
            '2026-Q3',
            'PROPOSED'
        );
        """
    )

    if publication_status is not None:
        connection.execute(
            """
            INSERT INTO hierarchy_publications
            VALUES ('2026-Q3', ?)
            """,
            (publication_status,),
        )

    connection.commit()
    connection.close()


def _status(path):
    connection = sqlite3.connect(path)
    result = connection.execute(
        "SELECT review_status FROM record_hierarchy WHERE hierarchy_id = ?",
        (EDGE_ID,),
    ).fetchone()[0]
    connection.close()
    return result


def _events(path):
    connection = sqlite3.connect(path)
    rows = connection.execute(
        """
        SELECT hierarchy_id, previous_status, new_status,
               reviewed_by, decision_note
        FROM hierarchy_review_events
        """
    ).fetchall()
    connection.close()
    return rows


def test_approve_proposed_edge_and_record_audit_event(tmp_path):
    database = tmp_path / "review.sqlite"
    _database(database)

    result = review_hierarchy_edge(
        "2026-Q3",
        EDGE_ID,
        decision="approve",
        reviewed_by="reviewer@example.test",
        decision_note="Verified against the cited PSA publication.",
        database_path=database,
    )

    assert result["previous_status"] == "PROPOSED"
    assert result["new_status"] == "APPROVED"
    assert result["event_id"]
    assert _status(database) == "APPROVED"
    assert _events(database) == [
        (
            EDGE_ID,
            "PROPOSED",
            "APPROVED",
            "reviewer@example.test",
            "Verified against the cited PSA publication.",
        )
    ]


def test_reject_proposed_edge_and_record_audit_event(tmp_path):
    database = tmp_path / "review.sqlite"
    _database(database)

    result = review_hierarchy_edge(
        "2026-Q3",
        EDGE_ID,
        decision="reject",
        reviewed_by="reviewer@example.test",
        decision_note="Evidence does not support this parent relationship.",
        database_path=database,
    )

    assert result["new_status"] == "REJECTED"
    assert _status(database) == "REJECTED"
    assert _events(database)[0][2] == "REJECTED"


def test_already_decided_edge_cannot_be_reviewed_again(tmp_path):
    database = tmp_path / "review.sqlite"
    _database(database)

    review_hierarchy_edge(
        "2026-Q3",
        EDGE_ID,
        decision="approve",
        reviewed_by="reviewer@example.test",
        decision_note="Initial approval.",
        database_path=database,
    )

    with pytest.raises(ValueError, match="only PROPOSED"):
        review_hierarchy_edge(
            "2026-Q3",
            EDGE_ID,
            decision="reject",
            reviewed_by="reviewer@example.test",
            decision_note="Attempted second decision.",
            database_path=database,
        )

    assert _status(database) == "APPROVED"
    assert len(_events(database)) == 1


def test_published_release_cannot_be_reviewed(tmp_path):
    database = tmp_path / "review.sqlite"
    _database(database, publication_status="PUBLISHED")

    with pytest.raises(ValueError, match="is published"):
        review_hierarchy_edge(
            "2026-Q3",
            EDGE_ID,
            decision="approve",
            reviewed_by="reviewer@example.test",
            decision_note="Approval attempt.",
            database_path=database,
        )

    assert _status(database) == "PROPOSED"
    assert _events(database) == []


def test_unknown_edge_is_rejected(tmp_path):
    database = tmp_path / "review.sqlite"
    _database(database)

    with pytest.raises(ValueError, match="was not found"):
        review_hierarchy_edge(
            "2026-Q3",
            "missing-edge",
            decision="approve",
            reviewed_by="reviewer@example.test",
            decision_note="No such edge.",
            database_path=database,
        )

    assert _events(database) == []


def test_unknown_release_is_rejected(tmp_path):
    database = tmp_path / "review.sqlite"
    _database(database)

    with pytest.raises(ValueError, match="Unknown release"):
        review_hierarchy_edge(
            "2099-Q1",
            EDGE_ID,
            decision="approve",
            reviewed_by="reviewer@example.test",
            decision_note="Unknown release.",
            database_path=database,
        )


def test_review_event_cannot_be_updated_or_deleted(tmp_path):
    database = tmp_path / "review.sqlite"
    _database(database)

    review_hierarchy_edge(
        "2026-Q3",
        EDGE_ID,
        decision="approve",
        reviewed_by="reviewer@example.test",
        decision_note="Approved.",
        database_path=database,
    )

    connection = sqlite3.connect(database)

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            "UPDATE hierarchy_review_events SET decision_note = 'changed'"
        )

    connection.rollback()

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("DELETE FROM hierarchy_review_events")

    connection.rollback()
    connection.close()
    assert len(_events(database)) == 1


@pytest.mark.parametrize(
    ("decision", "reviewed_by", "note"),
    [
        ("invalid", "reviewer", "note"),
        ("approve", "", "note"),
        ("approve", "reviewer", " "),
    ],
)
def test_invalid_review_arguments_are_rejected(
    tmp_path, decision, reviewed_by, note
):
    database = tmp_path / "review.sqlite"
    _database(database)

    with pytest.raises(ValueError):
        review_hierarchy_edge(
            "2026-Q3",
            EDGE_ID,
            decision=decision,
            reviewed_by=reviewed_by,
            decision_note=note,
            database_path=database,
        )

    assert _status(database) == "PROPOSED"
    assert _events(database) == []
