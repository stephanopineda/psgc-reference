import { ApiError } from "../../domain/errors";
import type { SourceRecord } from "./recordRepository";

type HierarchyPublication = {
  publication_status: "PUBLISHED" | "WITHDRAWN";
  record_count: number;
  approved_edge_count: number;
};

type CountResult = {
  count: number;
};

export class HierarchyRepository {
  constructor(private readonly db: D1Database) {}

  async assertPublished(releaseId: string): Promise<void> {
    const publication = await this.db
      .prepare(
        `SELECT
          publication_status,
          record_count,
          approved_edge_count
        FROM hierarchy_publications
        WHERE release_id = ?`,
      )
      .bind(releaseId)
      .first<HierarchyPublication>();

    if (!publication || publication.publication_status !== "PUBLISHED") {
      throw new ApiError(
        409,
        "HIERARCHY_NOT_PUBLISHED",
        "The hierarchy for the selected release has not been published.",
      );
    }

    const [
      sourceRecordCount,
      approvedEdgeCount,
      regionCount,
      invalidParentCount,
    ] = await Promise.all([
      this.db
        .prepare(
          `SELECT COUNT(*) AS count
          FROM source_records
          WHERE release_id = ?`,
        )
        .bind(releaseId)
        .first<CountResult>(),

      this.db
        .prepare(
          `SELECT COUNT(*) AS count
          FROM record_hierarchy
          WHERE release_id = ?
            AND relationship_type = 'PARENT_OF'
            AND review_status = 'APPROVED'`,
        )
        .bind(releaseId)
        .first<CountResult>(),

      this.db
        .prepare(
          `SELECT COUNT(*) AS count
          FROM source_records AS sr
          INNER JOIN source_record_version_memberships AS vm
            ON vm.release_id = sr.release_id
            AND vm.psgc_code = sr.psgc_code
          INNER JOIN source_record_versions AS v
            ON v.version_id = vm.version_id
            AND v.psgc_code = vm.psgc_code
          WHERE sr.release_id = ?
            AND v.geographic_level = 'Reg'`,
        )
        .bind(releaseId)
        .first<CountResult>(),

      this.db
        .prepare(
          `SELECT COUNT(*) AS count
          FROM (
            SELECT sr.psgc_code
            FROM source_records AS sr
            LEFT JOIN source_record_version_memberships AS vm
              ON vm.release_id = sr.release_id
              AND vm.psgc_code = sr.psgc_code
            LEFT JOIN source_record_versions AS v
              ON v.version_id = vm.version_id
              AND v.psgc_code = vm.psgc_code
            LEFT JOIN record_hierarchy AS h
              ON h.release_id = sr.release_id
              AND h.child_psgc_code = sr.psgc_code
              AND h.relationship_type = 'PARENT_OF'
              AND h.review_status = 'APPROVED'
            WHERE sr.release_id = ?
            GROUP BY sr.psgc_code, v.version_id, v.geographic_level
            HAVING
              v.version_id IS NULL
              OR (
                v.geographic_level = 'Reg'
                AND COUNT(h.hierarchy_id) <> 0
              )
              OR (
                (v.geographic_level IS NULL OR v.geographic_level <> 'Reg')
                AND COUNT(h.hierarchy_id) <> 1
              )
          ) AS invalid_parent_records`,
        )
        .bind(releaseId)
        .first<CountResult>(),
    ]);

    const actualRecordCount = sourceRecordCount?.count ?? 0;
    const actualApprovedEdgeCount = approvedEdgeCount?.count ?? 0;
    const actualRegionCount = regionCount?.count ?? 0;
    const actualInvalidParentCount = invalidParentCount?.count ?? 0;

    if (
      actualRecordCount !== publication.record_count ||
      actualApprovedEdgeCount !== publication.approved_edge_count ||
      actualRegionCount === 0 ||
      actualInvalidParentCount !== 0
    ) {
      throw new ApiError(
        503,
        "HIERARCHY_PUBLICATION_INTEGRITY_ERROR",
        "The published hierarchy failed its database integrity checks.",
        {
          expected_record_count: publication.record_count,
          actual_record_count: actualRecordCount,
          expected_approved_edge_count: publication.approved_edge_count,
          actual_approved_edge_count: actualApprovedEdgeCount,
          region_count: actualRegionCount,
          records_with_invalid_parent_count: actualInvalidParentCount,
        },
      );
    }
  }

  async parentExists(
    releaseId: string,
    psgcCode: string,
  ): Promise<boolean> {
    const result = await this.db
      .prepare(
        `SELECT 1 AS found
        FROM source_records
        WHERE release_id = ? AND psgc_code = ?`,
      )
      .bind(releaseId, psgcCode)
      .first<{ found: number }>();

    return result !== null;
  }

  async listRegions(releaseId: string): Promise<SourceRecord[]> {
    const result = await this.db
      .prepare(
        `SELECT
          sr.release_id,
          sr.psgc_code,
          sr.source_record_id,
          sr.source_row_number,
          v.name,
          v.correspondence_code,
          v.geographic_level,
          v.old_names,
          v.city_class,
          v.income_classification,
          v.urban_rural,
          v.population,
          v.population_annotation,
          v.source_status_value
        FROM source_records AS sr
        INNER JOIN source_record_version_memberships AS vm
          ON vm.release_id = sr.release_id
          AND vm.psgc_code = sr.psgc_code
        INNER JOIN source_record_versions AS v
          ON v.version_id = vm.version_id
          AND v.psgc_code = vm.psgc_code
        WHERE sr.release_id = ?
          AND v.geographic_level = 'Reg'
        ORDER BY v.name COLLATE NOCASE ASC, sr.psgc_code ASC`,
      )
      .bind(releaseId)
      .all<SourceRecord>();

    return result.results;
  }

  async listChildren(
    releaseId: string,
    parentCode: string,
  ): Promise<SourceRecord[]> {
    const result = await this.db
      .prepare(
        `SELECT
          sr.release_id,
          sr.psgc_code,
          sr.source_record_id,
          sr.source_row_number,
          v.name,
          v.correspondence_code,
          v.geographic_level,
          v.old_names,
          v.city_class,
          v.income_classification,
          v.urban_rural,
          v.population,
          v.population_annotation,
          v.source_status_value
        FROM record_hierarchy AS h
        INNER JOIN source_records AS sr
          ON sr.release_id = h.release_id
          AND sr.psgc_code = h.child_psgc_code
        INNER JOIN source_record_version_memberships AS vm
          ON vm.release_id = sr.release_id
          AND vm.psgc_code = sr.psgc_code
        INNER JOIN source_record_versions AS v
          ON v.version_id = vm.version_id
          AND v.psgc_code = vm.psgc_code
        WHERE h.release_id = ?
          AND h.parent_psgc_code = ?
          AND h.relationship_type = 'PARENT_OF'
          AND h.review_status = 'APPROVED'
        ORDER BY v.name COLLATE NOCASE ASC, sr.psgc_code ASC`,
      )
      .bind(releaseId, parentCode)
      .all<SourceRecord>();

    return result.results;
  }
}
