"""Auditable, transactional review of individual hierarchy edges."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psgc_etl.load.d1_loader import _database_path


def review_hierarchy_edge(
    release_id: str,
    hierarchy_id: str,
    *,
    decision: str,
    reviewed_by: str,
    decision_note: str,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Approve or reject one proposed edge and append an immutable event."""
    if not isinstance(release_id, str) or not release_id.strip():
        raise ValueError("A release ID is required.")

    if not isinstance(hierarchy_id, str) or not hierarchy_id.strip():
        raise ValueError("A hierarchy ID is required.")

    if decision not in {"approve", "reject"}:
        raise ValueError("Decision must be 'approve' or 'reject'.")

    if not isinstance(reviewed_by, str) or not reviewed_by.strip():
        raise ValueError("A reviewer identity is required.")

    if not isinstance(decision_note, str) or not decision_note.strip():
        raise ValueError("A non-empty decision note is required.")

    new_status = "APPROVED" if decision == "approve" else "REJECTED"
    db_path = database_path or _database_path()

    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("BEGIN IMMEDIATE")

        release = connection.execute(
            "SELECT release_id FROM releases WHERE release_id = ?",
            (release_id,),
        ).fetchone()

        if release is None:
            raise ValueError(f"Unknown release: {release_id}")

        publication = connection.execute(
            """
            SELECT publication_status
            FROM hierarchy_publications
            WHERE release_id = ?
            """,
            (release_id,),
        ).fetchone()

        if publication is not None and publication["publication_status"] == "PUBLISHED":
            raise ValueError(
                f"Release {release_id} is published. "
                "Withdraw the hierarchy before changing review decisions."
            )

        edge = connection.execute(
            """
            SELECT hierarchy_id, review_status
            FROM record_hierarchy
            WHERE hierarchy_id = ?
              AND release_id = ?
            """,
            (hierarchy_id, release_id),
        ).fetchone()

        if edge is None:
            raise ValueError(
                f"Hierarchy edge {hierarchy_id} was not found in release {release_id}."
            )

        previous_status = edge["review_status"]
        if previous_status != "PROPOSED":
            raise ValueError(
                f"Hierarchy edge {hierarchy_id} has status {previous_status}; "
                "only PROPOSED edges can receive an initial review decision."
            )

        reviewed_at = (
            datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        )
        event_id = uuid.uuid4().hex

        updated = connection.execute(
            """
            UPDATE record_hierarchy
            SET review_status = ?
            WHERE hierarchy_id = ?
              AND release_id = ?
              AND review_status = 'PROPOSED'
            """,
            (new_status, hierarchy_id, release_id),
        )

        if updated.rowcount != 1:
            raise RuntimeError(
                "Hierarchy edge status changed during review; no decision was recorded."
            )

        connection.execute(
            """
            INSERT INTO hierarchy_review_events (
                event_id,
                hierarchy_id,
                previous_status,
                new_status,
                reviewed_by,
                reviewed_at,
                decision_note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                hierarchy_id,
                previous_status,
                new_status,
                reviewed_by.strip(),
                reviewed_at,
                decision_note.strip(),
            ),
        )

        connection.commit()

        return {
            "operation": "review-hierarchy",
            "release_id": release_id,
            "hierarchy_id": hierarchy_id,
            "previous_status": previous_status,
            "new_status": new_status,
            "event_id": event_id,
            "reviewed_by": reviewed_by.strip(),
            "reviewed_at": reviewed_at,
            "decision_note": decision_note.strip(),
        }

    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
