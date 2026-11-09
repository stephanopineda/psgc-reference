import type { Context } from "hono";

export function success<T>(
  context: Context,
  data: T,
  meta?: Record<string, unknown>,
): Response {
  return context.json({
    data,
    ...(meta ? { meta } : {}),
  });
}
