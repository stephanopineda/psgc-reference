"""Load normalized PSA PSGC releases into Wrangler's local D1 SQLite database."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psgc_etl.extract.psgc_extractor import extract_psgc_records
from psgc_etl.hierarchy import build_hierarchy, validate_hierarchy
from psgc_etl.transform.normalizer import normalize_psgc_records
from psgc_etl.validate.validator import validate_psgc_records

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "data" / "source" / "psa"
D1_LOCAL_DIR = (
    PROJECT_ROOT
    / ".wrangler"
    / "state"
    / "v3"
    / "d1"
    / "miniflare-D1DatabaseObject"
)

RELEASES = {
    "PSGC-1Q-2024-Publication-Datafile.xlsx": {
        "release_id": "2024-Q1",
        "publication_date": "2024-03-31",
    },
    "PSGC-4Q-2024-Publication-Datafile.xlsx": {
        "release_id": "2024-Q4",
        "publication_date": "2024-12-31",
    },
    "PSGC-1Q-2025-Publication-Datafile.xlsx": {
        "release_id": "2025-Q1",
        "publication_date": "2025-03-31",
    },
    "PSGC-3Q-2026-Publication-Datafile.xlsx": {
        "release_id": "2026-Q3",
        "publication_date": "2026-09-30",
    },
}

SOURCE_FIELDS = (
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

EXCEPTIONAL_NORMALIZATION_ACTIONS = {
    "MISSING_MARKER",
    "NUMERIC_INTEGER_TO_STRING",
    "FORMULA_CACHED_NUMERIC",
    "FORMULA_CACHE_MISSING",
    "UNSUPPORTED_NUMERIC_REPRESENTATION",
    "UNSUPPORTED_POPULATION_TYPE",
    "UNSUPPORTED_POPULATION_VALUE",
    "KNOWN_SOURCE_ERROR_AS_MISSING",
}


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _version_id(record: dict[str, Any]) -> str:
    identity = {
        "psgc_code": record["psgc_code"],
        "name": record["name"],
        "correspondence_code": record["correspondence_code"],
        "geographic_level": record["geographic_level"],
        "old_names": record["old_names"],
        "city_class": record["city_class"],
        "income_classification": record["income_classification"],
        "urban_rural": record["urban_rural"],
        "population": record["population"],
        "population_annotation": record["population_annotation"],
        "source_status_value": record["source_status_value"],
        "source_values_json": record["source_values_json"],
        "normalization_events_json": record["normalization_events_json"],
    }

    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _database_path() -> Path:
    if not D1_LOCAL_DIR.is_dir():
        raise FileNotFoundError(
            "Wrangler local D1 directory was not found. "
            "Run `npm run db:migrate:local` first."
        )

    candidates = sorted(
        path
        for path in D1_LOCAL_DIR.glob("*.sqlite")
        if path.name != "metadata.sqlite"
    )

    if len(candidates) != 1:
        raise RuntimeError(
            "Expected exactly one local D1 database file, "
            f"found {len(candidates)}: {candidates}"
        )

    return candidates[0]


def _release_metadata(path: Path) -> dict[str, Any]:
    metadata = RELEASES.get(path.name)

    if metadata is None:
        raise ValueError(
            f"Unsupported PSA workbook filename: {path.name}. "
            "Add an explicitly reviewed release mapping before importing it."
        )

    return metadata


def _normalization_events(record: dict[str, Any]) -> dict[str, Any]:
    events = {}

    for field_name, cell in record["cells"].items():
        action = cell["normalization_action"]

        if action not in EXCEPTIONAL_NORMALIZATION_ACTIONS:
            continue

        event = {
            "action": action,
            "status": cell["normalization_status"],
            "value_origin": cell["normalized_value_origin"],
            "raw_value": cell["raw_value"],
            "normalized_value": cell["normalized_value"],
        }

        if cell.get("normalization_rationale"):
            event["rationale"] = cell["normalization_rationale"]

        if action in {
            "FORMULA_CACHED_NUMERIC",
            "FORMULA_CACHE_MISSING",
        }:
            event["formula_expression"] = cell["formula_expression"]
            event["cached_value"] = cell["cached_value"]
            event["cached_python_type"] = cell["cached_python_type"]

        events[field_name] = event

    return events


def _source_values(record: dict[str, Any]) -> dict[str, Any]:
    return {
        field_name: record["cells"][field_name]["raw_value"]
        for field_name in SOURCE_FIELDS
    }


def _finding_id(release_id: str, finding: dict[str, Any]) -> str:
    identity = "|".join(
        (
            release_id,
            finding["rule_id"],
            finding["source_record_id"],
            finding["field_name"],
            finding.get("source_coordinate") or "",
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _insert_release(
    connection: sqlite3.Connection,
    *,
    release_id: str,
    publication_date: str,
    normalized: dict[str, Any],
    imported_at: str,
) -> None:
    artifact = normalized["source_artifact"]

    connection.execute(
        """
        INSERT INTO releases (
            release_id,
            publication_date,
            source_filename,
            source_sha256,
            source_size_bytes,
            worksheet_name,
            normalization_profile_version,
            record_count,
            population_reference_year,
            urban_rural_reference_year,
            income_classification_basis,
            source_profile_id,
            extraction_profile_version,
            status,
            is_official_current,
            imported_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'IMPORTED', 0, ?)
        """,
        (
            release_id,
            publication_date,
            artifact["filename"],
            artifact["sha256"],
            artifact["size_bytes"],
            normalized["worksheet_name"],
            normalized["normalization_profile_version"],
            normalized["record_count"],
            normalized.get("source_metadata", {}).get(
                "population_reference_year"
            ),
            normalized.get("source_metadata", {}).get(
                "urban_rural_reference_year"
            ),
            normalized.get("source_metadata", {}).get(
                "income_classification_basis"
            ),
            normalized.get("source_profile_id"),
            normalized.get("extraction_profile_version"),
            imported_at,
        ),
    )


def _insert_records(
    connection: sqlite3.Connection,
    release_id: str,
    normalized: dict[str, Any],
) -> None:
    source_record_sql = """
        INSERT INTO source_records (
            release_id,
            psgc_code,
            source_record_id,
            source_row_number
        )
        VALUES (?, ?, ?, ?)
    """

    version_sql = """
        INSERT OR IGNORE INTO source_record_versions (
            version_id,
            psgc_code,
            name,
            correspondence_code,
            geographic_level,
            old_names,
            city_class,
            income_classification,
            urban_rural,
            population,
            population_annotation,
            source_status_value,
            source_values_json,
            normalization_events_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    membership_sql = """
        INSERT INTO source_record_version_memberships (
            release_id,
            psgc_code,
            version_id
        )
        VALUES (?, ?, ?)
    """

    source_record_rows = []
    versions_by_id = {}
    membership_rows = []

    for record in normalized["records"]:
        cells = record["cells"]
        values = {
            field_name: cells[field_name]["normalized_value"]
            for field_name in SOURCE_FIELDS
        }

        psgc_code = values["psgc_code"]

        if not isinstance(psgc_code, str) or len(psgc_code) != 10:
            raise ValueError(
                "Cannot import a record without a valid 10-digit PSGC code: "
                f"{record['source_record_id']}"
            )

        if not isinstance(values["name"], str) or not values["name"].strip():
            raise ValueError(
                f"Cannot import {psgc_code}: normalized name is missing."
            )

        population = values["population"]
        if population is not None and (
            isinstance(population, bool) or not isinstance(population, int)
        ):
            raise ValueError(
                f"Cannot import {psgc_code}: population is not an integer."
            )

        source_values_json = _json(_source_values(record))
        normalization_events_json = _json(_normalization_events(record))

        version_record = {
            **values,
            "source_values_json": source_values_json,
            "normalization_events_json": normalization_events_json,
        }

        version_id = _version_id(version_record)

        source_record_rows.append(
            (
                release_id,
                psgc_code,
                record["source_record_id"],
                record["source_row_number"],
            )
        )

        # The same version may occur in multiple releases.
        versions_by_id[version_id] = (
            version_id,
            psgc_code,
            values["name"],
            values["correspondence_code"],
            values["geographic_level"],
            values["old_names"],
            values["city_class"],
            values["income_classification"],
            values["urban_rural"],
            population,
            values["population_annotation"],
            values["source_status_value"],
            source_values_json,
            normalization_events_json,
        )

        membership_rows.append(
            (release_id, psgc_code, version_id)
        )

    connection.executemany(source_record_sql, source_record_rows)

    expected_versions = list(versions_by_id.values())

    connection.executemany(version_sql, expected_versions)

    # Verify that an existing version ID represents the exact expected
    # payload. INSERT OR IGNORE must not silently accept conflicting data.
    version_columns = (
        "version_id",
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
        "source_values_json",
        "normalization_events_json",
    )

    for start in range(0, len(expected_versions), 500):
        batch = expected_versions[start:start + 500]
        version_ids = [row[0] for row in batch]
        placeholders = ", ".join("?" for _ in version_ids)

        select_sql = (
            f"SELECT {', '.join(version_columns)} "
            "FROM source_record_versions "
            f"WHERE version_id IN ({placeholders})"
        )

        stored_versions = {
            row[0]: tuple(row)
            for row in connection.execute(select_sql, version_ids)
        }

        for expected in batch:
            version_id = expected[0]

            if stored_versions.get(version_id) != expected:
                raise RuntimeError(
                    "Stored version payload conflicts with calculated "
                    f"version ID: {version_id}"
                )

    connection.executemany(membership_sql, membership_rows)


def _insert_findings(
    connection: sqlite3.Connection,
    release_id: str,
    validation: dict[str, Any],
    normalized: dict[str, Any],
) -> int:
    records_by_id = {
        record["source_record_id"]: record
        for record in normalized["records"]
    }

    sql = """
        INSERT INTO validation_findings (
            finding_id,
            release_id,
            psgc_code,
            rule_id,
            severity,
            message,
            disposition,
            evidence_json
        )
        VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?)
    """

    rows = []

    for finding in validation["findings"]:
        source_record_id = finding["source_record_id"]
        source_record = records_by_id.get(source_record_id)

        if source_record is None:
            raise ValueError(
                f"Finding references unknown source record: {source_record_id}"
            )

        psgc_code = source_record["cells"]["psgc_code"]["normalized_value"]
        field_cell = source_record["cells"].get(finding["field_name"])

        evidence = {
            "source_record_id": source_record_id,
            "worksheet_name": finding["worksheet_name"],
            "source_row_number": finding["source_row_number"],
            "field_name": finding["field_name"],
            "source_coordinate": finding["source_coordinate"],
            "source_value": finding["source_value"],
            "normalized_value": finding["normalized_value"],
        }

        if field_cell is not None:
            action = field_cell.get("normalization_action")
            rationale = field_cell.get("normalization_rationale")

            if action and action != "UNCHANGED":
                evidence["normalization_action"] = action

            if rationale:
                evidence["normalization_rationale"] = rationale

        rows.append(
            (
                _finding_id(release_id, finding),
                release_id,
                psgc_code,
                finding["rule_id"],
                finding["severity"],
                finding["message"],
                _json(evidence),
            )
        )

    connection.executemany(sql, rows)
    return len(rows)


def _insert_audit(
    connection: sqlite3.Connection,
    release_id: str,
    *,
    actor: str,
    details: dict[str, Any],
    occurred_at: str,
) -> None:
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
        VALUES (?, ?, 'IMPORT_COMPLETED', NULL, 'IMPORTED', ?, ?, ?, ?)
        """,
        (
            hashlib.sha256(
                f"{release_id}|IMPORT_COMPLETED|{details['source_sha256']}".encode()
            ).hexdigest(),
            release_id,
            actor,
            "Initial import of PSA PSGC source release.",
            _json(details),
            occurred_at,
        ),
    )


def _import_one(
    connection: sqlite3.Connection,
    path: Path,
    *,
    actor: str,
) -> dict[str, Any]:
    metadata = _release_metadata(path)
    release_id = metadata["release_id"]

    extraction = extract_psgc_records(path)
    normalized = normalize_psgc_records(extraction)

    extracted_publication_date = normalized.get(
        "source_metadata", {}
    ).get("publication_date")
    if extracted_publication_date != metadata["publication_date"]:
        raise ValueError(
            f"Publication date mismatch for {release_id}: "
            f"manifest={metadata['publication_date']!r}, "
            f"workbook={extracted_publication_date!r}"
        )

    validation = validate_psgc_records(normalized)

    if validation["record_count"] != normalized["record_count"]:
        raise RuntimeError(
            f"Validation record count mismatch for {release_id}."
        )

    artifact = normalized["source_artifact"]
    existing = connection.execute(
        """
        SELECT source_sha256, record_count
        FROM releases
        WHERE release_id = ?
        """,
        (release_id,),
    ).fetchone()

    if existing is not None:
        if existing["source_sha256"] != artifact["sha256"]:
            raise RuntimeError(
                f"Release {release_id} already exists with a different "
                "source SHA-256. Refusing to overwrite it."
            )

        actual_count = connection.execute(
            "SELECT COUNT(*) FROM source_records WHERE release_id = ?",
            (release_id,),
        ).fetchone()[0]

        if (
            existing["record_count"] != normalized["record_count"]
            or actual_count != existing["record_count"]
        ):
            raise RuntimeError(
                f"Release {release_id} has a record-count mismatch. "
                "Database integrity needs review."
            )

        return {
            "release_id": release_id,
            "status": "SKIPPED_ALREADY_IMPORTED",
            "record_count": existing["record_count"],
            "finding_count": None,
        }

    imported_at = datetime.now(UTC).isoformat(timespec="seconds")

    _insert_release(
        connection,
        release_id=release_id,
        publication_date=metadata["publication_date"],
        normalized=normalized,
        imported_at=imported_at,
    )

    _insert_records(connection, release_id, normalized)
    finding_count = _insert_findings(
        connection,
        release_id,
        validation,
        normalized,
    )

    _insert_audit(
        connection,
        release_id,
        actor=actor,
        details={
            "source_filename": artifact["filename"],
            "source_sha256": artifact["sha256"],
            "source_size_bytes": artifact["size_bytes"],
            "record_count": normalized["record_count"],
            "finding_count": finding_count,
            "severity_counts": validation["severity_counts"],
            "validation_ruleset_version": validation[
                "validation_ruleset_version"
            ],
            "normalization_profile_version": normalized[
                "normalization_profile_version"
            ],
            "source_profile_id": normalized.get("source_profile_id"),
            "extraction_profile_version": normalized.get(
                "extraction_profile_version"
            ),
            "source_metadata": normalized.get("source_metadata", {}),
        },
        occurred_at=imported_at,
    )

    return {
        "release_id": release_id,
        "status": "IMPORTED",
        "record_count": normalized["record_count"],
        "finding_count": finding_count,
        "severity_counts": validation["severity_counts"],
        "source_sha256": artifact["sha256"],
    }


def load_releases(
    paths: list[Path],
    *,
    database_path: Path | None = None,
    actor: str = "local-etl",
) -> list[dict[str, Any]]:
    """Load releases transactionally, one release at a time."""
    if not paths:
        raise ValueError("No PSA workbooks were selected for import.")

    resolved_paths = [path.resolve() for path in paths]

    if len(set(resolved_paths)) != len(resolved_paths):
        raise ValueError("The same workbook was selected more than once.")

    for path in resolved_paths:
        if not path.is_file():
            raise FileNotFoundError(f"Workbook does not exist: {path}")
        _release_metadata(path)

    db_path = database_path or _database_path()

    if not db_path.is_file():
        raise FileNotFoundError(f"Local D1 database does not exist: {db_path}")

    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    results = []

    try:
        for path in resolved_paths:
            connection.execute("BEGIN IMMEDIATE")

            try:
                result = _import_one(
                    connection,
                    path,
                    actor=actor,
                )
                connection.commit()
                results.append(result)
            except Exception:
                connection.rollback()
                raise
    finally:
        connection.close()

    return results



def _persist_hierarchy_edges(
    connection: sqlite3.Connection,
    release_id: str,
    edges: list[dict[str, Any]],
) -> dict[str, int]:
    """Insert missing hierarchy edges without changing existing review decisions."""
    expected = {}

    for edge in edges:
        key = (
            edge["parent_psgc_code"],
            edge["child_psgc_code"],
            edge["relationship_type"],
        )

        if key in expected:
            raise RuntimeError(
                f"Duplicate proposed hierarchy edge for {release_id}: {key}"
            )

        expected[key] = edge

    existing_rows = connection.execute(
        """
        SELECT
            parent_psgc_code,
            child_psgc_code,
            relationship_type,
            evidence_reference,
            rationale,
            review_status
        FROM record_hierarchy
        WHERE release_id = ?
        """,
        (release_id,),
    ).fetchall()

    existing = {}

    for row in existing_rows:
        key = (
            row["parent_psgc_code"],
            row["child_psgc_code"],
            row["relationship_type"],
        )

        if key in existing:
            raise RuntimeError(
                f"Duplicate stored hierarchy edge for {release_id}: {key}"
            )

        existing[key] = row

    unexpected = set(existing) - set(expected)
    if unexpected:
        raise RuntimeError(
            f"Stored hierarchy for {release_id} contains unexpected edges: "
            f"{sorted(unexpected)[:5]}"
        )

    for key, row in existing.items():
        edge = expected[key]

        if (
            row["evidence_reference"] != edge["evidence_reference"]
            or row["rationale"] != edge["rationale"]
        ):
            raise RuntimeError(
                f"Stored hierarchy evidence differs from the source-derived "
                f"proposal for {release_id}: {key}. Refusing to overwrite it."
            )

    inserted_count = 0

    for key, edge in expected.items():
        if key in existing:
            continue

        hierarchy_id = hashlib.sha256(
            (
                f"{release_id}|{edge['parent_psgc_code']}|"
                f"{edge['child_psgc_code']}|{edge['relationship_type']}"
            ).encode()
        ).hexdigest()

        connection.execute(
            """
            INSERT INTO record_hierarchy (
                hierarchy_id,
                release_id,
                parent_psgc_code,
                child_psgc_code,
                relationship_type,
                evidence_reference,
                rationale,
                review_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hierarchy_id,
                release_id,
                edge["parent_psgc_code"],
                edge["child_psgc_code"],
                edge["relationship_type"],
                edge["evidence_reference"],
                edge["rationale"],
                edge["review_status"],
            ),
        )
        inserted_count += 1

    return {
        "inserted_count": inserted_count,
        "existing_count": len(existing),
        "total_count": len(expected),
    }


def load_hierarchies(
    paths: list[Path],
    *,
    database_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Build, validate, and persist hierarchy for already-imported releases."""
    if not paths:
        raise ValueError("No PSA workbooks were selected for hierarchy loading.")

    resolved_paths = [path.resolve() for path in paths]

    if len(set(resolved_paths)) != len(resolved_paths):
        raise ValueError("The same workbook was selected more than once.")

    for path in resolved_paths:
        if not path.is_file():
            raise FileNotFoundError(f"Workbook does not exist: {path}")
        _release_metadata(path)

    db_path = database_path or _database_path()

    if not db_path.is_file():
        raise FileNotFoundError(f"Local D1 database does not exist: {db_path}")

    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    results = []

    try:
        for path in resolved_paths:
            connection.execute("BEGIN IMMEDIATE")

            try:
                metadata = _release_metadata(path)
                release_id = metadata["release_id"]

                extraction = extract_psgc_records(path)
                normalized = normalize_psgc_records(extraction)

                publication_date = normalized.get(
                    "source_metadata", {}
                ).get("publication_date")

                if publication_date != metadata["publication_date"]:
                    raise ValueError(
                        f"Publication date mismatch for {release_id}: "
                        f"manifest={metadata['publication_date']!r}, "
                        f"workbook={publication_date!r}"
                    )

                artifact = normalized["source_artifact"]

                stored_release = connection.execute(
                    """
                    SELECT source_sha256, record_count
                    FROM releases
                    WHERE release_id = ?
                    """,
                    (release_id,),
                ).fetchone()

                if stored_release is None:
                    raise RuntimeError(
                        f"Release {release_id} is not imported into D1. "
                        "Run load-d1 first."
                    )

                if stored_release["source_sha256"] != artifact["sha256"]:
                    raise RuntimeError(
                        f"Source SHA-256 mismatch for {release_id}. "
                        "Refusing to build hierarchy from a different workbook."
                    )

                actual_record_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM source_records
                    WHERE release_id = ?
                    """,
                    (release_id,),
                ).fetchone()[0]

                if (
                    stored_release["record_count"] != normalized["record_count"]
                    or actual_record_count != stored_release["record_count"]
                ):
                    raise RuntimeError(
                        f"Record-count mismatch for {release_id}. "
                        "Database integrity needs review."
                    )

                hierarchy = build_hierarchy(normalized, release_id)
                validation = validate_hierarchy(normalized, hierarchy)

                if hierarchy["finding_count"] != 0 or not validation["is_valid"]:
                    raise RuntimeError(
                        f"Hierarchy validation failed for {release_id}: "
                        f"builder_findings={hierarchy['finding_count']}, "
                        f"validator_errors={validation['error_count']}"
                    )

                persistence = _persist_hierarchy_edges(
                    connection,
                    release_id,
                    hierarchy["edges"],
                )

                connection.commit()

                results.append(
                    {
                        "release_id": release_id,
                        "status": (
                            "IMPORTED"
                            if persistence["inserted_count"]
                            else "ALREADY_CURRENT"
                        ),
                        "record_count": hierarchy["record_count"],
                        "edge_count": persistence["total_count"],
                        "inserted_count": persistence["inserted_count"],
                        "existing_count": persistence["existing_count"],
                        "validated_path_count": validation[
                            "validated_path_count"
                        ],
                        "maximum_depth": validation["maximum_depth"],
                    }
                )

            except Exception:
                connection.rollback()
                raise

    finally:
        connection.close()

    return results


def discover_release_workbooks(source_dir: Path) -> list[Path]:
    """Return supported PSA workbooks in publication order."""
    paths = [
        source_dir / filename
        for filename in RELEASES
        if (source_dir / filename).is_file()
    ]

    if len(paths) != len(RELEASES):
        missing = [
            filename
            for filename in RELEASES
            if not (source_dir / filename).is_file()
        ]
        raise FileNotFoundError(
            f"Missing expected PSA source workbooks: {missing}"
        )

    return paths
