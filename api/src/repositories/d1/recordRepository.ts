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

function buildWhere(filters: RecordFilters): WhereClause {
  const conditions = ["release_id = ?"];
  const values: Array<string | number> = [filters.releaseId];

  const optionalFilters: Array<[string, string | undefined]> = [
    ["geographic_level", filters.geographicLevel],
    ["city_class", filters.cityClass],
    ["income_classification", filters.incomeClassification],
    ["urban_rural", filters.urbanRural],
  ];

  for (const [column, value] of optionalFilters) {
    if (value !== undefined) {
      conditions.push(`${column} = ?`);
      values.push(value);
    }
  }

  if (filters.query !== undefined) {
    conditions.push("name LIKE ? ESCAPE '\\'");
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
            release_id, psgc_code, source_record_id, source_row_number,
            name, correspondence_code, geographic_level, old_names,
            city_class, income_classification, urban_rural, population,
            population_annotation, source_status_value
          FROM source_records
          WHERE ${where.sql}
          ORDER BY name COLLATE NOCASE ASC, psgc_code ASC
          LIMIT ? OFFSET ?`,
        )
        .bind(...where.values, filters.pageSize, offset)
        .all<SourceRecord>(),

      this.db
        .prepare(
          `SELECT COUNT(*) AS total
          FROM source_records
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
          release_id, psgc_code, source_record_id, source_row_number,
          name, correspondence_code, geographic_level, old_names,
          city_class, income_classification, urban_rural, population,
          population_annotation, source_status_value,
          source_values_json, normalization_events_json
        FROM source_records
        WHERE release_id = ? AND psgc_code = ?`,
      )
      .bind(releaseId, psgcCode)
      .first<SourceRecordDetail>();
  }
}
