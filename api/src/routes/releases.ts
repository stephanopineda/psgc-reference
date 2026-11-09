import { Hono } from "hono";
import type { Bindings } from "../config/env";
import { ApiError } from "../domain/errors";
import { success } from "../http/responses";
import { ReleaseRepository } from "../repositories/d1/releaseRepository";

const releases = new Hono<{ Bindings: Bindings }>();

releases.get("/", async (context) => {
  const repository = new ReleaseRepository(context.env.DB);
  const items = await repository.list();

  return success(context, items, {
    count: items.length,
    ordering: "publication_date_desc",
  });
});

releases.get("/:releaseId", async (context) => {
  const releaseId = context.req.param("releaseId");
  const repository = new ReleaseRepository(context.env.DB);

  const release = await repository.findById(releaseId);

  if (!release) {
    throw new ApiError(404, "RELEASE_NOT_FOUND", "The requested release does not exist.");
  }

  const findingCounts = await repository.findingCounts(releaseId);

  return success(context, {
    ...release,
    validation_findings: findingCounts,
  });
});

export default releases;
