"""Withdraw a published, release-specific hierarchy."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psgc_etl.load.d1_loader import _database_path


def withdraw_hierarchy(
    release_id: str,
    *,
    withdrawn_by: str,
    reason: str,
    database_path: Path | None = None,
) -> dict[str, Any]:
    """Withdraw one published hierarchy and record an immutable audit event."""
    if not isinstance(release_id, str) or not release_id.strip():
        raise ValueError("A release ID is required.")

    if not isinstance(withdrawn_by, str) or not withdrawn_by.strip():
        raise ValueError("A withdrawal actor is required.")

    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A withdrawal reason is required.")

    connection = sqlite3.connect(
        database_path or _database_path(),
        timeout=30,
    )
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
            SELECT publication_status, published_at, publication_reference
            FROM hierarchy_publications
            WHERE release_id = ?
            """,
            (release_id,),
        ).fetchone()

        if publication is None:
            raise ValueError(
                f"Release {release_id} has no hierarchy publication to withdraw."
            )

        if publication["publication_status"] != "PUBLISHED":
            raise ValueError(
                f"Release {release_id} hierarchy is "
                f"{publication['publication_status']}; only PUBLISHED "
                "hierarchies can be withdrawn."
            )

        withdrawn_at = (
            datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        )

        updated = connection.execute(
            """
            UPDATE hierarchy_publications
            SET publication_status = 'WITHDRAWN'
            WHERE release_id = ?
              AND publication_status = 'PUBLISHED'
            """,
            (release_id,),
        )

        if updated.rowcount != 1:
            raise RuntimeError(
                "Publication status changed during withdrawal; no event was recorded."
            )

        details = {
            "published_at": publication["published_at"],
            "publication_reference": publication["publication_reference"],
        }

        connection.execute(
            """
            INSERT INTO release_audit_log (
                audit_id,
                release_id,
                event_type,
                previous_status,
                new_status,
                actor,
                rationale,
                details_json,
                occurred_at
            )
            VALUES (?, ?, 'HIERARCHY_WITHDRAWN', 'PUBLISHED',
                    'WITHDRAWN', ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                release_id,
                withdrawn_by.strip(),
                reason.strip(),
                json.dumps(details, ensure_ascii=False, sort_keys=True),
                withdrawn_at,
            ),
        )

        connection.commit()

        return {
            "operation": "withdraw-hierarchy",
            "release_id": release_id,
            "previous_status": "PUBLISHED",
            "publication_status": "WITHDRAWN",
            "withdrawn_by": withdrawn_by.strip(),
            "withdrawn_at": withdrawn_at,
            "reason": reason.strip(),
        }

    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
