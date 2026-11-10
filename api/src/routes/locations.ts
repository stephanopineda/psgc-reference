import { Hono } from "hono";
import type { Bindings } from "../config/env";
import { ApiError } from "../domain/errors";
import { success } from "../http/responses";
import { HierarchyRepository } from "../repositories/d1/hierarchyRepository";
import { ReleaseRepository } from "../repositories/d1/releaseRepository";

const locations = new Hono<{ Bindings: Bindings }>();

locations.get("/", async (context) => {
  const releaseId = context.req.param("releaseId");

  if (!releaseId) {
    throw new ApiError(
      400,
      "RELEASE_REQUIRED",
      "A release identifier must be specified in the URL.",
    );
  }

  const release = await new ReleaseRepository(context.env.DB).findById(
    releaseId,
  );

  if (!release) {
    throw new ApiError(
      404,
      "RELEASE_NOT_FOUND",
      "The requested release does not exist.",
    );
  }

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
    parent_code: parentCode,
    count: children.length,
  });
});

export default locations;
