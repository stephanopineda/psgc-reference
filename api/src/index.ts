import { Hono } from "hono";
import type { Bindings } from "./config/env";
import { ApiError } from "./domain/errors";
import health from "./routes/health";
import geographicLevels from "./routes/geographicLevels";
import records from "./routes/records";
import releases from "./routes/releases";

const app = new Hono<{ Bindings: Bindings }>();

app.route("/healthz", health);
app.route("/v1/releases", releases);
app.route("/v1/geographic-levels", geographicLevels);
app.route("/v1/records", records);

app.notFound((context) =>
  context.json(
    {
      error: {
        code: "NOT_FOUND",
        message: "The requested endpoint does not exist.",
      },
    },
    404,
  ),
);

app.onError((error, context) => {
  if (error instanceof ApiError) {
    return context.json(
      {
        error: {
          code: error.code,
          message: error.message,
          ...(error.details === undefined ? {} : { details: error.details }),
        },
      },
      error.status,
    );
  }

  console.error("Unhandled API error:", error);

  return context.json(
    {
      error: {
        code: "INTERNAL_SERVER_ERROR",
        message: "An unexpected error occurred.",
      },
    },
    500,
  );
});

export default app;
