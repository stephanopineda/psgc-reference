import { describe, expect, it } from "vitest";
import app from "../src/index";

const release = {
  release_id: "2026-Q3",
  publication_date: "2026-09-30",
  source_filename: "PSGC-3Q-2026-Publication-Datafile.xlsx",
  source_sha256: "a".repeat(64),
  source_size_bytes: 3248857,
  worksheet_name: "PSGC",
  normalization_profile_version: "1.2",
  record_count: 43768,
  status: "IMPORTED",
  is_official_current: 0,
  imported_at: "2026-11-10T00:00:00",
  created_at: "2026-11-10T00:00:00",
  population_reference_year: 2024,
  urban_rural_reference_year: 2024,
  income_classification_basis: "DOF DO No. 074.2024",
  source_profile_id: "psa-2026-dof-074-2024",
  extraction_profile_version: "2.0",
};

const record = {
  release_id: "2026-Q3",
  psgc_code: "0990100000",
  source_record_id: "source-record-1",
  source_row_number: 35444,
  name: "City of Isabela (Not a Province)",
  correspondence_code: null,
  geographic_level: "City",
  old_names: null,
  city_class: null,
  income_classification: null,
  urban_rural: null,
  population: null,
  population_annotation: null,
  source_status_value: null,
  source_values_json: JSON.stringify({ population: "#N/A" }),
  normalization_events_json: JSON.stringify({
    population: {
      action: "KNOWN_SOURCE_ERROR_AS_MISSING",
      status: "REVIEW",
    },
  }),
};

type MockStatement = {
  sql: string;
  values: unknown[];
  bind: (...values: unknown[]) => MockStatement;
  first: <T>() => Promise<T | null>;
  all: <T>() => Promise<{ results: T[] }>;
};

function createDatabase() {
  const database = {
    prepare(sql: string): MockStatement {
      const statement: MockStatement = {
        sql,
        values: [],
        bind(...values) {
          this.values = values;
          return this;
        },
        async first<T>() {
          if (sql.includes("SELECT 1 AS ok")) {
            return { ok: 1 } as T;
          }

          if (sql.includes("FROM releases")) {
            if (sql.includes("WHERE release_id = ?")) {
              return (statement.values[0] === release.release_id
                ? release
                : null) as T | null;
            }
          }

          if (sql.includes("COUNT(*) AS total")) {
            return { total: 1 } as T;
          }

          if (sql.includes("FROM source_records")) {
            if (
              statement.values[0] === release.release_id &&
              statement.values[1] === record.psgc_code
            ) {
              return record as T;
            }
          }

          return null;
        },
        async all<T>() {
          if (sql.includes("FROM releases")) {
            return { results: [release] as T[] };
          }

          if (sql.includes("GROUP BY severity")) {
            return {
              results: [{ severity: "REVIEW", count: 1 }] as T[],
            };
          }

          if (sql.includes("GROUP BY v.geographic_level")) {
            return {
              results: [
                { geographic_level: null, record_count: 2 },
                { geographic_level: "City", record_count: 1 },
              ] as T[],
            };
          }

          if (sql.includes("FROM source_records")) {
            return { results: [record] as T[] };
          }

          return { results: [] };
        },
      };

      return statement;
    },
  };

  return database as unknown as D1Database;
}

const env = { DB: createDatabase() };

async function request(path: string): Promise<Response> {
  return app.fetch(new Request(`https://example.test${path}`), env);
}

describe("PSGC Reference API", () => {
  it("returns a successful database health check", async () => {
    const response = await request("/healthz");

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      data: { status: "ok", database: "ok" },
    });
  });

  it("lists releases with source reference metadata", async () => {
    const response = await request("/v1/releases");
    const body = await response.json<{
      data: typeof release[];
      meta: { count: number };
    }>();

    expect(response.status).toBe(200);
    expect(body.data[0].release_id).toBe("2026-Q3");
    expect(body.data[0].population_reference_year).toBe(2024);
    expect(body.data[0].is_official_current).toBe(0);
    expect(body.meta.count).toBe(1);
  });

  it("returns release details with finding counts", async () => {
    const response = await request("/v1/releases/2026-Q3");
    const body = await response.json<{
      data: typeof release & {
        validation_findings: Array<{ severity: string; count: number }>;
      };
    }>();

    expect(response.status).toBe(200);
    expect(body.data.release_id).toBe("2026-Q3");
    expect(body.data.validation_findings).toEqual([
      { severity: "REVIEW", count: 1 },
    ]);
  });

  it("requires explicit release selection for record listing", async () => {
    const response = await request("/v1/records");

    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({
      error: { code: "RELEASE_REQUIRED" },
    });
  });

  it("rejects malformed PSGC codes", async () => {
    const response = await request(
      "/v1/records/not-a-code?release_id=2026-Q3",
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({
      error: { code: "INVALID_PSGC_CODE" },
    });
  });

  it("returns a record and its source provenance", async () => {
    const response = await request(
      "/v1/records/0990100000?release_id=2026-Q3",
    );
    const body = await response.json<{
      data: {
        psgc_code: string;
        population: number | null;
        source_values: { population: string };
        normalization_events: {
          population: { action: string; status: string };
        };
      };
    }>();

    expect(response.status).toBe(200);
    expect(body.data.psgc_code).toBe("0990100000");
    expect(body.data.population).toBeNull();
    expect(body.data.source_values.population).toBe("#N/A");
    expect(body.data.normalization_events.population.action).toBe(
      "KNOWN_SOURCE_ERROR_AS_MISSING",
    );
  });

  it("returns geographic levels for an explicit release", async () => {
    const response = await request(
      "/v1/geographic-levels?release_id=2026-Q3",
    );
    const body = await response.json<{
      data: Array<{ geographic_level: string; record_count: number }>;
      meta: {
        release_id: string;
        unclassified_record_count: number;
      };
    }>();

    expect(response.status).toBe(200);
    expect(body.meta.release_id).toBe("2026-Q3");
    expect(body.data).toEqual([
      { geographic_level: "City", record_count: 1 },
    ]);
    expect(body.meta.unclassified_record_count).toBe(2);
  });

  it("returns a consistent not-found response", async () => {
    const response = await request("/unknown");

    expect(response.status).toBe(404);
    expect(await response.json()).toMatchObject({
      error: { code: "NOT_FOUND" },
    });
  });

  it("rejects page values that would overflow the SQL offset", async () => {
    const response = await request(
      "/v1/records?release_id=2026-Q3&page=9007199254740991&page_size=100",
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({
      error: { code: "INVALID_PARAMETER" },
    });
  });

  it("rejects page sizes above the configured maximum", async () => {
    const response = await request(
      "/v1/records?release_id=2026-Q3&page_size=101",
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({
      error: { code: "INVALID_PARAMETER" },
    });
  });

  it("rejects search terms longer than 200 characters", async () => {
    const response = await request(
      `/v1/records?release_id=2026-Q3&q=${"a".repeat(201)}`,
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({
      error: { code: "INVALID_PARAMETER" },
    });
  });

  it("rejects unknown release identifiers", async () => {
    const response = await request(
      "/v1/records?release_id=unknown-release",
    );

    expect(response.status).toBe(404);
    expect(await response.json()).toMatchObject({
      error: { code: "RELEASE_NOT_FOUND" },
    });
  });

});
