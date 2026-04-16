import type { ActorContext, ControlPlaneDatabase, StoredReply } from "../domain/types";

export function buildRequestKey(
  scope: string,
  actor: ActorContext,
  idempotencyKey?: string,
  subject = "",
): string | null {
  if (!idempotencyKey) {
    return null;
  }
  return [scope, subject, actor.userId, actor.tenantId ?? "-", idempotencyKey].join(":");
}

export function getStoredReply(db: ControlPlaneDatabase, key: string | null): StoredReply | null {
  return key ? db.requests[key] ?? null : null;
}

export function rememberReply(db: ControlPlaneDatabase, key: string | null, reply: StoredReply): void {
  if (key) {
    db.requests[key] = reply;
  }
}
