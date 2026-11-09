import { Hono } from "hono";
import type { Bindings } from "../config/env";

const health = new Hono<{ Bindings: Bindings }>();

health.get("/", async (context) => {
  try {
    await context.env.DB.prepare("SELECT 1 AS ok").first();

    return context.json({
      data: {
        status: "ok",
        database: "ok",
      },
    });
  } catch {
    return context.json(
      {
        error: {
          code: "DATABASE_UNAVAILABLE",
          message: "The database health check failed.",
        },
      },
      503,
    );
  }
});

export default health;
