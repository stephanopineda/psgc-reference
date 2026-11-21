import { Hono } from "hono";
import type { Bindings } from "../config/env";
import { ApiError } from "../domain/errors";
import { success } from "../http/responses";
import { HierarchyRepository } from "../repositories/d1/hierarchyRepository";
import { ReleaseRepository } from "../repositories/d1/releaseRepository";

const locations = new Hono<{ Bindings: Bindings }>();

locations.get("/", async (context) => {
  const requestedReleaseId = context.req.param("releaseId");
  const releases = new ReleaseRepository(context.env.DB);

  const release = requestedReleaseId
    ? await releases.findById(requestedReleaseId)
    : await releases.findLatest();

  if (!release) {
    throw new ApiError(
      404,
      requestedReleaseId ? "RELEASE_NOT_FOUND" : "NO_RELEASES_AVAILABLE",
      requestedReleaseId
        ? "The requested release does not exist."
        : "No PSA releases are available.",
    );
  }

  const releaseId = release.release_id;

  const parentCodes = context.req.queries("parent_code") ?? [];

  if (parentCodes.length > 1) {
    throw new ApiError(
      400,
      "INVALID_PARAMETER",
      "parent_code must be specified only once.",
    );
  }

  const parentCode = parentCodes[0];

  if (parentCode !== undefined && !/^[0-9]{10}$/.test(parentCode)) {
    throw new ApiError(
      400,
      "INVALID_PSGC_CODE",
      "parent_code must contain exactly 10 digits.",
    );
  }

  const repository = new HierarchyRepository(context.env.DB);

  await repository.assertPublished(releaseId);

  if (parentCode === undefined) {
    const regions = await repository.listRegions(releaseId);

    return success(context, regions, {
      release_id: releaseId,
      publication_date: release.publication_date,
      parent_code: null,
      count: regions.length,
    });
  }

  const parentExists = await repository.parentExists(
    releaseId,
    parentCode,
  );

  if (!parentExists) {
    throw new ApiError(
      404,
      "LOCATION_NOT_FOUND",
      "The parent PSGC code does not exist in the selected release.",
    );
  }

  const children = await repository.listChildren(releaseId, parentCode);

  return success(context, children, {
    release_id: releaseId,
    publication_date: release.publication_date,
    parent_code: parentCode,
    count: children.length,
  });
});

export default locations;
