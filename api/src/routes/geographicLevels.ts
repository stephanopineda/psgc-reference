import { Hono } from "hono";
import type { Bindings } from "../config/env";
import { ApiError } from "../domain/errors";
import { success } from "../http/responses";
import { ReleaseRepository } from "../repositories/d1/releaseRepository";

const geographicLevels = new Hono<{ Bindings: Bindings }>();

geographicLevels.get("/", async (context) => {
  const releaseId = context.req.query("release_id");

  if (!releaseId?.trim()) {
    throw new ApiError(
      400,
      "RELEASE_REQUIRED",
      "Specify the release_id query parameter.",
    );
  }

  const release = await new ReleaseRepository(context.env.DB).findById(releaseId);

  if (!release) {
    throw new ApiError(404, "RELEASE_NOT_FOUND", "The requested release does not exist.");
  }

  const result = await context.env.DB
    .prepare(
      `SELECT
        v.geographic_level,
        COUNT(*) AS record_count
      FROM source_records AS sr
      INNER JOIN source_record_version_memberships AS vm
        ON vm.release_id = sr.release_id
        AND vm.psgc_code = sr.psgc_code
      INNER JOIN source_record_versions AS v
        ON v.version_id = vm.version_id
        AND v.psgc_code = vm.psgc_code
      WHERE sr.release_id = ?
      GROUP BY v.geographic_level
      ORDER BY v.geographic_level COLLATE NOCASE`,
    )
    .bind(releaseId)
    .all<{ geographic_level: string | null; record_count: number }>();

  const unclassified = result.results.find(
    (item) => item.geographic_level === null,
  );

  const levels = result.results.filter(
    (item): item is { geographic_level: string; record_count: number } =>
      item.geographic_level !== null,
  );

  return success(context, levels, {
    release_id: releaseId,
    count: levels.length,
    unclassified_record_count: unclassified?.record_count ?? 0,
  });
});

export default geographicLevels;
