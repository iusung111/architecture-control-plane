import type { ActorContext } from "../domain/types";
import { HttpError } from "./response";

export function actorFromRequest(request: Request): ActorContext {
  const userId = request.headers.get("X-User-Id");
  if (!userId) {
    throw new HttpError(401, "missing_user", "X-User-Id is required.");
  }
  return {
    userId,
    role: request.headers.get("X-User-Role") ?? "operator",
    tenantId: request.headers.get("X-Tenant-Id"),
  };
}

export function requestIdFromRequest(request: Request): string | null {
  return request.headers.get("X-Request-Id");
}

export function idempotencyKeyFromRequest(request: Request): string | undefined {
  return request.headers.get("Idempotency-Key") ?? undefined;
}
