export type Release = {
  release_id: string;
  publication_date: string;
  source_filename: string;
  source_sha256: string;
  source_size_bytes: number;
  worksheet_name: string;
  normalization_profile_version: string;
  record_count: number;
  status: string;
  is_official_current: number;
  imported_at: string;
  created_at: string;
  population_reference_year: number | null;
  urban_rural_reference_year: number | null;
  income_classification_basis: string | null;
  source_profile_id: string | null;
  extraction_profile_version: string | null;
};

export class ReleaseRepository {
  constructor(private readonly db: D1Database) {}

  async list(): Promise<Release[]> {
    const result = await this.db
      .prepare(
        `SELECT
          release_id, publication_date, source_filename, source_sha256,
          source_size_bytes, worksheet_name, normalization_profile_version,
          record_count, status, is_official_current, imported_at, created_at,
          population_reference_year, urban_rural_reference_year,
          income_classification_basis, source_profile_id,
          extraction_profile_version
        FROM releases
        ORDER BY publication_date DESC, release_id DESC`,
      )
      .all<Release>();

    return result.results;
  }

  async findById(releaseId: string): Promise<Release | null> {
    return this.db
      .prepare(
        `SELECT
          release_id, publication_date, source_filename, source_sha256,
          source_size_bytes, worksheet_name, normalization_profile_version,
          record_count, status, is_official_current, imported_at, created_at,
          population_reference_year, urban_rural_reference_year,
          income_classification_basis, source_profile_id,
          extraction_profile_version
        FROM releases
        WHERE release_id = ?`,
      )
      .bind(releaseId)
      .first<Release>();
  }

  async findingCounts(
    releaseId: string,
  ): Promise<Array<{ severity: string; count: number }>> {
    const result = await this.db
      .prepare(
        `SELECT severity, COUNT(*) AS count
        FROM validation_findings
        WHERE release_id = ?
        GROUP BY severity
        ORDER BY severity`,
      )
      .bind(releaseId)
      .all<{ severity: string; count: number }>();

    return result.results;
  }
}
