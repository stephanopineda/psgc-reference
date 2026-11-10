import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(".wrangler/state/v3/d1/miniflare-D1DatabaseObject")

ATTRIBUTE_FIELDS = (
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

VERSION_FIELDS = (
    "psgc_code",
    *ATTRIBUTE_FIELDS,
    "source_values_json",
    "normalization_events_json",
)


def canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def calculate_version_id(record):
    identity = {
        field: record[field]
        for field in VERSION_FIELDS
    }

    return hashlib.sha256(
        canonical_json(identity).encode("utf-8")
    ).hexdigest()


def main():
    databases = [
        path
        for path in ROOT.glob("*.sqlite")
        if path.name != "metadata.sqlite"
        and "-pre-versioning-backup" not in path.name
    ]

    if len(databases) != 1:
        raise RuntimeError(
            f"Expected one active D1 database, found {len(databases)}"
        )

    database = databases[0]
    print(f"Database: {database}")

    db = sqlite3.connect(database, timeout=60)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    try:
        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(source_records)")
        }

        required_columns = {
            "release_id",
            "psgc_code",
            *ATTRIBUTE_FIELDS,
            "source_values_json",
            "normalization_events_json",
        }

        if not required_columns.issubset(columns):
            raise RuntimeError(
                "Backfill requires the pre-0004 wide source_records schema. "
                "This utility must not run against the narrowed schema."
            )

        db.execute("BEGIN IMMEDIATE")

        expected_records = db.execute(
            "SELECT COUNT(*) FROM source_records"
        ).fetchone()[0]

        existing_versions = db.execute(
            "SELECT COUNT(*) FROM source_record_versions"
        ).fetchone()[0]

        existing_memberships = db.execute(
            "SELECT COUNT(*) FROM source_record_version_memberships"
        ).fetchone()[0]

        print(f"Source records: {expected_records:,}")
        print(f"Existing versions: {existing_versions:,}")
        print(f"Existing memberships: {existing_memberships:,}")

        # Build a temporary expected-membership table.
        db.execute("""
            CREATE TEMP TABLE expected_version_memberships (
                release_id TEXT NOT NULL,
                psgc_code TEXT NOT NULL,
                version_id TEXT NOT NULL,
                PRIMARY KEY (release_id, psgc_code)
            )
        """)

        columns = ", ".join(
            ("release_id", *VERSION_FIELDS)
        )

        cursor = db.execute(
            f"SELECT {columns} FROM source_records "
            "ORDER BY release_id, psgc_code"
        )

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

        expected_sql = """
            INSERT INTO expected_version_memberships (
                release_id, psgc_code, version_id
            )
            VALUES (?, ?, ?)
        """

        version_rows = []
        membership_rows = []
        unique_versions = set()
        processed = 0

        version_columns = (
            "version_id",
            "psgc_code",
            *ATTRIBUTE_FIELDS,
            "source_values_json",
            "normalization_events_json",
        )

        def flush():
            if not version_rows:
                return

            db.executemany(version_sql, version_rows)
            db.executemany(expected_sql, membership_rows)

            # Verify every stored field, not only the PSGC code.
            for start in range(0, len(version_rows), 500):
                batch = version_rows[start:start + 500]
                version_ids = [row[0] for row in batch]
                placeholders = ", ".join("?" for _ in version_ids)

                stored = {
                    row[0]: tuple(row)
                    for row in db.execute(
                        f"""
                        SELECT {", ".join(version_columns)}
                        FROM source_record_versions
                        WHERE version_id IN ({placeholders})
                        """,
                        version_ids,
                    )
                }

                for expected in batch:
                    if stored.get(expected[0]) != expected:
                        raise RuntimeError(
                            "Stored version payload conflicts with "
                            f"calculated version ID: {expected[0]}"
                        )

            version_rows.clear()
            membership_rows.clear()

        for row in cursor:
            record = dict(row)
            version_id = calculate_version_id(record)

            version_rows.append((
                version_id,
                record["psgc_code"],
                *(record[field] for field in ATTRIBUTE_FIELDS),
                record["source_values_json"],
                record["normalization_events_json"],
            ))

            membership_rows.append((
                record["release_id"],
                record["psgc_code"],
                version_id,
            ))

            unique_versions.add(version_id)
            processed += 1

            if len(version_rows) >= 1000:
                flush()

        flush()

        # Verify that an existing version ID never represents
        # a different record payload.
        mismatch = db.execute("""
            SELECT COUNT(*)
            FROM source_record_versions AS v
            JOIN (
                SELECT DISTINCT
                    version_id,
                    psgc_code
                FROM expected_version_memberships
            ) AS e
              ON e.version_id = v.version_id
            WHERE v.psgc_code <> e.psgc_code
        """).fetchone()[0]

        if mismatch:
            raise RuntimeError(
                f"Version identity conflicts: {mismatch}"
            )

        # Reject conflicting pre-existing memberships.
        conflicts = db.execute("""
            SELECT COUNT(*)
            FROM source_record_version_memberships AS actual
            JOIN expected_version_memberships AS expected
              ON expected.release_id = actual.release_id
             AND expected.psgc_code = actual.psgc_code
            WHERE actual.version_id <> expected.version_id
        """).fetchone()[0]

        if conflicts:
            raise RuntimeError(
                f"Conflicting existing memberships: {conflicts}"
            )

        # Insert only missing memberships.
        db.execute("""
            INSERT OR IGNORE INTO source_record_version_memberships (
                release_id,
                psgc_code,
                version_id
            )
            SELECT
                release_id,
                psgc_code,
                version_id
            FROM expected_version_memberships
        """)

        actual_memberships = db.execute(
            "SELECT COUNT(*) FROM source_record_version_memberships"
        ).fetchone()[0]

        missing = db.execute("""
            SELECT COUNT(*)
            FROM expected_version_memberships AS expected
            LEFT JOIN source_record_version_memberships AS actual
              ON actual.release_id = expected.release_id
             AND actual.psgc_code = expected.psgc_code
            WHERE actual.version_id IS NULL
        """).fetchone()[0]

        if processed != expected_records:
            raise RuntimeError("Processed record count mismatch")

        if actual_memberships != expected_records:
            raise RuntimeError("Membership count mismatch")

        if missing:
            raise RuntimeError(f"Missing memberships: {missing}")

        db.execute("DROP TABLE expected_version_memberships")
        db.commit()

        actual_versions = db.execute(
            "SELECT COUNT(*) FROM source_record_versions"
        ).fetchone()[0]

        print("\n===== BACKFILL RESULTS =====")
        print(f"Processed records: {processed:,}")
        print(f"Distinct versions calculated: {len(unique_versions):,}")
        print(f"Stored versions: {actual_versions:,}")
        print(f"Stored memberships: {actual_memberships:,}")
        print(
            "Potentially deduplicated payloads:",
            f"{processed - actual_versions:,}",
        )

        print("\n===== RELEASE MEMBERSHIPS =====")

        for row in db.execute("""
            SELECT
                release_id,
                COUNT(*) AS memberships,
                COUNT(DISTINCT version_id) AS versions
            FROM source_record_version_memberships
            GROUP BY release_id
            ORDER BY release_id
        """):
            print(
                f"{row['release_id']}: "
                f"{row['memberships']:,} memberships, "
                f"{row['versions']:,} versions"
            )

        print("\nForeign-key violations:",
              len(db.execute("PRAGMA foreign_key_check").fetchall()))

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
