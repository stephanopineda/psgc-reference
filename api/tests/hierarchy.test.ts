import { describe, expect, it } from "vitest";
import app from "../src/index";

type Location = {
  release_id: string;
  psgc_code: string;
  source_record_id: string;
  source_row_number: number;
  name: string;
  correspondence_code: null;
  geographic_level: string;
  old_names: null;
  city_class: null;
  income_classification: null;
  urban_rural: null;
  population: null;
  population_annotation: null;
  source_status_value: null;
};

const releaseId = "2026-Q3";

const records: Location[] = [
  {
    release_id: releaseId,
    psgc_code: "0900000000",
    source_record_id: "region-ix",
    source_row_number: 1,
    name: "Region IX",
    correspondence_code: null,
    geographic_level: "Reg",
    old_names: null,
    city_class: null,
    income_classification: null,
    urban_rural: null,
    population: null,
    population_annotation: null,
    source_status_value: null,
  },
  {
    release_id: releaseId,
    psgc_code: "0900100000",
    source_record_id: "province-a",
    source_row_number: 2,
    name: "Province A",
    correspondence_code: null,
    geographic_level: "Prov",
    old_names: null,
    city_class: null,
    income_classification: null,
    urban_rural: null,
    population: null,
    population_annotation: null,
    source_status_value: null,
  },
  {
    release_id: releaseId,
    psgc_code: "0900101000",
    source_record_id: "municipality-a",
    source_row_number: 3,
    name: "Municipality A",
    correspondence_code: null,
    geographic_level: "Mun",
    old_names: null,
    city_class: null,
    income_classification: null,
    urban_rural: null,
    population: null,
    population_annotation: null,
    source_status_value: null,
  },
  {
    release_id: releaseId,
    psgc_code: "0900101001",
    source_record_id: "barangay-a",
    source_row_number: 4,
    name: "Barangay A",
    correspondence_code: null,
    geographic_level: "Bgy",
    old_names: null,
    city_class: null,
    income_classification: null,
    urban_rural: null,
    population: null,
    population_annotation: null,
    source_status_value: null,
  },
  {
    release_id: releaseId,
    psgc_code: "0900101002",
    source_record_id: "barangay-b",
    source_row_number: 5,
    name: "Barangay B",
    correspondence_code: null,
    geographic_level: "Bgy",
    old_names: null,
    city_class: null,
    income_classification: null,
    urban_rural: null,
    population: null,
    population_annotation: null,
    source_status_value: null,
  },
  {
    release_id: releaseId,
    psgc_code: "0900200000",
    source_record_id: "city-a",
    source_row_number: 6,
    name: "City A",
    correspondence_code: null,
    geographic_level: "City",
    old_names: null,
    city_class: null,
    income_classification: null,
    urban_rural: null,
    population: null,
    population_annotation: null,
    source_status_value: null,
  },
  {
    release_id: releaseId,
    psgc_code: "0900200001",
    source_record_id: "barangay-c",
    source_row_number: 7,
    name: "Barangay C",
    correspondence_code: null,
    geographic_level: "Bgy",
    old_names: null,
    city_class: null,
    income_classification: null,
    urban_rural: null,
    population: null,
    population_annotation: null,
    source_status_value: null,
  },
];

const edges: Array<{ parent: string; child: string }> = [
  { parent: "0900000000", child: "0900100000" },
  { parent: "0900100000", child: "0900101000" },
  { parent: "0900101000", child: "0900101001" },
  { parent: "0900101000", child: "0900101002" },
  { parent: "0900000000", child: "0900200000" },
  { parent: "0900200000", child: "0900200001" },
];

const release = {
  release_id: releaseId,
  publication_date: "2026-09-30",
  source_filename: "fixture.xlsx",
  source_sha256: "a".repeat(64),
  source_size_bytes: 1000,
  worksheet_name: "PSGC",
  normalization_profile_version: "1.0",
  record_count: records.length,
  status: "IMPORTED",
  is_official_current: 0,
  imported_at: "2026-11-10T00:00:00",
  created_at: "2026-11-10T00:00:00",
};

type MockStatement = {
  sql: string;
  values: unknown[];
  bind: (...values: unknown[]) => MockStatement;
  first: <T>() => Promise<T | null>;
  all: <T>() => Promise<{ results: T[] }>;
};

function createDatabase(options?: { published?: boolean; corruptCount?: boolean }) {
  const published = options?.published ?? true;

  return {
    prepare(sql: string): MockStatement {
      const statement: MockStatement = {
        sql,
        values: [],
        bind(...values) {
          this.values = values;
          return this;
        },
        async first<T>() {
          if (sql.includes("FROM releases")) {
            return (statement.values[0] === releaseId ? release : null) as
              | T
              | null;
          }

          if (sql.includes("FROM hierarchy_publications")) {
            if (!published) return null;

            return {
              publication_status: "PUBLISHED",
              record_count: options?.corruptCount
                ? records.length + 1
                : records.length,
              approved_edge_count: edges.length,
            } as T;
          }

          if (sql.includes("COUNT(*) AS count")) {
            if (sql.includes("FROM source_records") && !sql.includes("JOIN")) {
              return { count: records.length } as T;
            }

            if (sql.includes("FROM record_hierarchy")) {
              return { count: edges.length } as T;
            }

            if (sql.includes("invalid_parent_records")) {
              return { count: 0 } as T;
            }

            if (sql.includes("geographic_level = 'Reg'")) {
              return {
                count: records.filter((item) => item.geographic_level === "Reg")
                  .length,
              } as T;
            }
          }

          if (sql.includes("SELECT 1 AS found")) {
            return (records.some(
              (item) =>
                item.release_id === statement.values[0] &&
                item.psgc_code === statement.values[1],
            )
              ? { found: 1 }
              : null) as T | null;
          }

          return null;
        },
        async all<T>() {
          if (sql.includes("FROM record_hierarchy AS h")) {
            const [requestedRelease, parentCode] = statement.values;

            const children = edges
              .filter((edge) => edge.parent === parentCode)
              .map((edge) =>
                records.find(
                  (item) =>
                    item.release_id === requestedRelease &&
                    item.psgc_code === edge.child,
                ),
              )
              .filter((item): item is Location => item !== undefined);

            return { results: children as T[] };
          }

          if (
            sql.includes("FROM source_records AS sr") &&
            sql.includes("geographic_level = 'Reg'")
          ) {
            return {
              results: records.filter(
                (item) => item.geographic_level === "Reg",
              ) as T[],
            };
          }

          return { results: [] };
        },
      };

      return statement;
    },
  } as unknown as D1Database;
}

async function request(
  path: string,
  database: D1Database = createDatabase(),
): Promise<Response> {
  return app.fetch(
    new Request(`https://example.test${path}`),
    { DB: database },
  );
}

describe("release-scoped hierarchy API", () => {
  it("returns only regions when parent_code is omitted", async () => {
    const response = await request(
      `/v1/releases/${releaseId}/locations`,
    );
    const body = await response.json<{
      data: Location[];
      meta: { release_id: string; parent_code: string | null; count: number };
    }>();

    expect(response.status).toBe(200);
    expect(body.meta).toEqual({
      release_id: releaseId,
      parent_code: null,
      count: 1,
    });
    expect(body.data.map((item) => item.psgc_code)).toEqual([
      "0900000000",
    ]);
    expect(body.data.every((item) => item.geographic_level === "Reg")).toBe(
      true,
    );
  });

  it("returns only immediate children for a parent code", async () => {
    const response = await request(
      `/v1/releases/${releaseId}/locations?parent_code=0900100000`,
    );
    const body = await response.json<{ data: Location[] }>();

    expect(response.status).toBe(200);
    expect(body.data.map((item) => item.psgc_code)).toEqual([
      "0900101000",
    ]);
  });

  it("rejects an unpublished hierarchy instead of returning an empty list", async () => {
    const response = await request(
      `/v1/releases/${releaseId}/locations`,
      createDatabase({ published: false }),
    );

    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({
      error: { code: "HIERARCHY_NOT_PUBLISHED" },
    });
  });

  it("rejects publication metadata that no longer matches the database", async () => {
    const response = await request(
      `/v1/releases/${releaseId}/locations`,
      createDatabase({ corruptCount: true }),
    );

    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({
      error: { code: "HIERARCHY_PUBLICATION_INTEGRITY_ERROR" },
    });
  });

  it("rejects malformed parent codes", async () => {
    const response = await request(
      `/v1/releases/${releaseId}/locations?parent_code=invalid`,
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({
      error: { code: "INVALID_PSGC_CODE" },
    });
  });

  it("rejects a parent code absent from the selected release", async () => {
    const response = await request(
      `/v1/releases/${releaseId}/locations?parent_code=9999999999`,
    );

    expect(response.status).toBe(404);
    expect(await response.json()).toMatchObject({
      error: { code: "LOCATION_NOT_FOUND" },
    });
  });

  it("rejects an unknown release", async () => {
    const response = await request(
      "/v1/releases/unknown/locations",
    );

    expect(response.status).toBe(404);
    expect(await response.json()).toMatchObject({
      error: { code: "RELEASE_NOT_FOUND" },
    });
  });

  it("can traverse every record from the region roots, including all barangays", async () => {
    const visited = new Set<string>();
    const pending = ["0900000000"];

    while (pending.length > 0) {
      const parentCode = pending.shift()!;
      expect(visited.has(parentCode)).toBe(false);
      visited.add(parentCode);

      const response = await request(
        `/v1/releases/${releaseId}/locations?parent_code=${parentCode}`,
      );
      expect(response.status).toBe(200);

      const body = await response.json<{ data: Location[] }>();

      for (const child of body.data) {
        expect(visited.has(child.psgc_code)).toBe(false);
        pending.push(child.psgc_code);
      }
    }

    const expectedCodes = records.map((item) => item.psgc_code).sort();
    const actualCodes = [...visited].sort();

    expect(actualCodes).toEqual(expectedCodes);

    const barangayCodes = records
      .filter((item) => item.geographic_level === "Bgy")
      .map((item) => item.psgc_code);

    for (const code of barangayCodes) {
      expect(visited.has(code)).toBe(true);
    }
  });
});
