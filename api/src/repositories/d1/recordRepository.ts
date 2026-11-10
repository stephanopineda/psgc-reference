export type RecordFilters = {
  releaseId: string;
  query?: string;
  geographicLevel?: string;
  cityClass?: string;
  incomeClassification?: string;
  urbanRural?: string;
  page: number;
  pageSize: number;
};

export type SourceRecord = {
  release_id: string;
  psgc_code: string;
  source_record_id: string;
  source_row_number: number;
  name: string;
  correspondence_code: string | null;
  geographic_level: string | null;
  old_names: string | null;
  city_class: string | null;
  income_classification: string | null;
  urban_rural: string | null;
  population: number | null;
  population_annotation: string | null;
  source_status_value: string | null;
};

export type SourceRecordDetail = SourceRecord & {
  source_values_json: string;
  normalization_events_json: string;
};

type WhereClause = {
  sql: string;
  values: Array<string | number>;
};

const VERSIONED_RECORDS_JOIN = `
  FROM source_records AS sr
  INNER JOIN source_record_version_memberships AS vm
    ON vm.release_id = sr.release_id
    AND vm.psgc_code = sr.psgc_code
  INNER JOIN source_record_versions AS v
    ON v.version_id = vm.version_id
    AND v.psgc_code = vm.psgc_code
`;

function buildWhere(filters: RecordFilters): WhereClause {
  const conditions = ["sr.release_id = ?"];
  const values: Array<string | number> = [filters.releaseId];

  const optionalFilters: Array<[string, string | undefined]> = [
    ["v.geographic_level", filters.geographicLevel],
    ["v.city_class", filters.cityClass],
    ["v.income_classification", filters.incomeClassification],
    ["v.urban_rural", filters.urbanRural],
  ];

  for (const [column, value] of optionalFilters) {
    if (value !== undefined) {
      conditions.push(`${column} = ?`);
      values.push(value);
    }
  }

  if (filters.query !== undefined) {
    conditions.push("v.name LIKE ? ESCAPE '\\'");
    const escaped = filters.query.replace(/[\\%_]/g, "\\$&");
    values.push(`%${escaped}%`);
  }

  return {
    sql: conditions.join(" AND "),
    values,
  };
}

export class RecordRepository {
  constructor(private readonly db: D1Database) {}

  async list(filters: RecordFilters): Promise<{
    records: SourceRecord[];
    total: number;
  }> {
    const where = buildWhere(filters);
    const offset = (filters.page - 1) * filters.pageSize;

    const [recordsResult, countResult] = await Promise.all([
      this.db
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
          ${VERSIONED_RECORDS_JOIN}
          WHERE ${where.sql}
          ORDER BY v.name COLLATE NOCASE ASC, sr.psgc_code ASC
          LIMIT ? OFFSET ?`,
        )
        .bind(...where.values, filters.pageSize, offset)
        .all<SourceRecord>(),

      this.db
        .prepare(
          `SELECT COUNT(*) AS total
          ${VERSIONED_RECORDS_JOIN}
          WHERE ${where.sql}`,
        )
        .bind(...where.values)
        .first<{ total: number }>(),
    ]);

    return {
      records: recordsResult.results,
      total: countResult?.total ?? 0,
    };
  }

  async findByCode(
    releaseId: string,
    psgcCode: string,
  ): Promise<SourceRecordDetail | null> {
    return this.db
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
          v.source_status_value,
          v.source_values_json,
          v.normalization_events_json
        ${VERSIONED_RECORDS_JOIN}
        WHERE sr.release_id = ? AND sr.psgc_code = ?`,
      )
      .bind(releaseId, psgcCode)
      .first<SourceRecordDetail>();
  }
}
