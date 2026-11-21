"""Validate and publish an approved, release-specific hierarchy in local D1."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psgc_etl.hierarchy.validator import validate_hierarchy
from psgc_etl.load.d1_loader import _database_path


def publish_hierarchy(
    release_id: str,
    *,
    published_by: str | None = None,
    database_path: Path | None = None,
    publication_reference: str | None = None,
    validate_only: bool = False,
) -> dict[str, Any]:
    """Validate one release's approved hierarchy and optionally publish it.

    Reads and validation occur under BEGIN IMMEDIATE so the validated snapshot
    cannot be modified by another SQLite writer before publication.
    """
    if not release_id.strip():
        raise ValueError("A release ID is required.")

    if not validate_only and (
        not isinstance(publication_reference, str)
        or not publication_reference.strip()
    ):
        raise ValueError(
            "A non-empty publication reference is required unless --validate-only is used."
        )

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

        rows = connection.execute(
            """
            SELECT
                sr.psgc_code,
                srv.geographic_level,
                m.version_id
            FROM source_records AS sr
            LEFT JOIN source_record_version_memberships AS m
                ON m.release_id = sr.release_id
                AND m.psgc_code = sr.psgc_code
            LEFT JOIN source_record_versions AS srv
                ON srv.version_id = m.version_id
                AND srv.psgc_code = m.psgc_code
            WHERE sr.release_id = ?
            ORDER BY sr.psgc_code
            """,
            (release_id,),
        ).fetchall()

        if not rows:
            raise ValueError(
                f"Release {release_id} has no source records; refusing publication."
            )

        missing_versions = [
            row["psgc_code"] for row in rows if row["version_id"] is None
        ]

        if missing_versions:
            raise ValueError(
                f"Release {release_id} has {len(missing_versions)} records "
                "without version membership or version data. "
                f"Examples: {missing_versions[:10]}"
            )

        records = [
            {
                "cells": {
                    "psgc_code": {
                        "normalized_value": row["psgc_code"],
                    },
                    "geographic_level": {
                        "normalized_value": row["geographic_level"],
                    },
                }
            }
            for row in rows
        ]

        edges = [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    release_id,
                    parent_psgc_code,
                    child_psgc_code,
                    relationship_type,
                    evidence_reference,
                    rationale,
                    review_status
                FROM record_hierarchy
                WHERE release_id = ?
                  AND review_status = 'APPROVED'
                ORDER BY parent_psgc_code, child_psgc_code
                """,
                (release_id,),
            ).fetchall()
        ]

        validation = validate_hierarchy(
            {"records": records},
            {"release_id": release_id, "edges": edges},
        )

        result: dict[str, Any] = {
            "operation": "publish-hierarchy",
            "release_id": release_id,
            "database": str(db_path),
            "validate_only": validate_only,
            "record_count": len(records),
            "approved_edge_count": len(edges),
            "validation": validation,
            "published": False,
        }

        if not validation["is_valid"]:
            connection.rollback()
            result["publication_status"] = "NOT_PUBLISHED"
            return result

        if validate_only:
            connection.rollback()
            result["publication_status"] = "VALIDATION_PASSED"
            return result

        if not validate_only and (
            not isinstance(published_by, str) or not published_by.strip()
        ):
            raise ValueError(
                "A non-empty publisher identity is required unless --validate-only is used."
            )

        published_at = datetime.now(UTC).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")

        previous_publication = connection.execute(
            """
            SELECT publication_status
            FROM hierarchy_publications
            WHERE release_id = ?
            """,
            (release_id,),
        ).fetchone()
        previous_status = (
            previous_publication["publication_status"]
            if previous_publication is not None
            else None
        )
        normalized_reference = publication_reference.strip()

        connection.execute(
            """
            INSERT INTO hierarchy_publications (
                release_id,
                publication_status,
                record_count,
                approved_edge_count,
                published_at,
                publication_reference
            )
            VALUES (?, 'PUBLISHED', ?, ?, ?, ?)
            ON CONFLICT(release_id) DO UPDATE SET
                publication_status = 'PUBLISHED',
                record_count = excluded.record_count,
                approved_edge_count = excluded.approved_edge_count,
                published_at = excluded.published_at,
                publication_reference = excluded.publication_reference
            """,
            (
                release_id,
                len(records),
                len(edges),
                published_at,
                normalized_reference,
            ),
        )

        connection.execute(
            """
            INSERT INTO release_audit_log (
                audit_id, release_id, event_type, previous_status,
                new_status, actor, rationale, details_json, occurred_at
            )
            VALUES (?, ?, 'HIERARCHY_PUBLISHED', ?, 'PUBLISHED', ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                release_id,
                previous_status,
                published_by.strip(),
                normalized_reference,
                json.dumps(
                    {
                        "record_count": len(records),
                        "approved_edge_count": len(edges),
                        "published_at": published_at,
                        "publication_reference": normalized_reference,
                    },
                    sort_keys=True,
                ),
                published_at,
            ),
        )

        connection.commit()

        result.update(
            {
                "published": True,
                "publication_status": "PUBLISHED",
                "published_at": published_at,
                "publication_reference": normalized_reference,
                "published_by": published_by.strip(),
            }
        )
        return result

    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
