import { Hono } from "hono";
import type { Bindings } from "../config/env";
import {
  DEFAULT_PAGE_SIZE,
  MAX_PAGE_SIZE,
} from "../config/env";
import { ApiError } from "../domain/errors";
import { success } from "../http/responses";
import { RecordRepository } from "../repositories/d1/recordRepository";
import { ReleaseRepository } from "../repositories/d1/releaseRepository";

const records = new Hono<{ Bindings: Bindings }>();

function positiveInteger(
  value: string | undefined,
  fallback: number,
  name: string,
  maximum = Number.MAX_SAFE_INTEGER,
): number {
  if (value === undefined) return fallback;

  if (!/^[0-9]+$/.test(value)) {
    throw new ApiError(400, "INVALID_PARAMETER", `${name} must be a positive integer.`);
  }

  const parsed = Number(value);

  if (!Number.isSafeInteger(parsed) || parsed < 1 || parsed > maximum) {
    throw new ApiError(
      400,
      "INVALID_PARAMETER",
      `${name} must be between 1 and ${maximum}.`,
    );
  }

  return parsed;
}

async function requireRelease(
  db: D1Database,
  releaseId: string | undefined,
): Promise<string> {
  if (!releaseId || !releaseId.trim()) {
    throw new ApiError(
      400,
      "RELEASE_REQUIRED",
      "Specify the release_id query parameter.",
    );
  }

  const release = await new ReleaseRepository(db).findById(releaseId);

  if (!release) {
    throw new ApiError(404, "RELEASE_NOT_FOUND", "The requested release does not exist.");
  }

  return releaseId;
}

records.get("/", async (context) => {
  const query = context.req.query();
  const releaseId = await requireRelease(context.env.DB, query.release_id);

  const pageSize = positiveInteger(
    query.page_size,
    DEFAULT_PAGE_SIZE,
    "page_size",
    MAX_PAGE_SIZE,
  );
  const maximumPage = Math.floor(Number.MAX_SAFE_INTEGER / pageSize);
  const page = positiveInteger(query.page, 1, "page", maximumPage);

  if (query.q !== undefined) {
    if (query.q.trim().length === 0) {
      throw new ApiError(400, "INVALID_PARAMETER", "q must not be empty.");
    }

    if (query.q.length > 200) {
      throw new ApiError(
        400,
        "INVALID_PARAMETER",
        "q must not exceed 200 characters.",
      );
    }
  }

  const repository = new RecordRepository(context.env.DB);
  const result = await repository.list({
    releaseId,
    query: query.q,
    geographicLevel: query.geographic_level,
    cityClass: query.city_class,
    incomeClassification: query.income_classification,
    urbanRural: query.urban_rural,
    page,
    pageSize,
  });

  return success(context, result.records, {
    release_id: releaseId,
    page,
    page_size: pageSize,
    total: result.total,
    total_pages: Math.ceil(result.total / pageSize),
  });
});

records.get("/:psgcCode", async (context) => {
  const releaseId = await requireRelease(
    context.env.DB,
    context.req.query("release_id"),
  );

  const psgcCode = context.req.param("psgcCode");

  if (!/^[0-9]{10}$/.test(psgcCode)) {
    throw new ApiError(
      400,
      "INVALID_PSGC_CODE",
      "psgc_code must contain exactly 10 digits.",
    );
  }

  const repository = new RecordRepository(context.env.DB);
  const record = await repository.findByCode(releaseId, psgcCode);

  if (!record) {
    throw new ApiError(
      404,
      "RECORD_NOT_FOUND",
      "The PSGC code does not exist in the selected release.",
    );
  }

  let sourceValues: unknown;
  let normalizationEvents: unknown;

  try {
    sourceValues = JSON.parse(record.source_values_json);
    normalizationEvents = JSON.parse(record.normalization_events_json);
  } catch {
    throw new ApiError(
      500,
      "INVALID_STORED_JSON",
      "The stored source provenance could not be decoded.",
    );
  }

  const {
    source_values_json: _sourceValuesJson,
    normalization_events_json: _normalizationEventsJson,
    ...publicRecord
  } = record;

  return success(context, {
    ...publicRecord,
    source_values: sourceValues,
    normalization_events: normalizationEvents,
  });
});

export default records;
