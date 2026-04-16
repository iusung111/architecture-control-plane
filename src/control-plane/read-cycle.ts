import { buildCycleSummary, buildResultSummary } from "../domain/render";
import { isTerminalState } from "../domain/states";
import type { ActorContext } from "../domain/types";
import { HttpError, dataResponse } from "../http/response";
import type { ControlPlaneStore } from "./store";

function actorCanRead(actor: ActorContext, tenantId: string | null): boolean {
  return !tenantId || !actor.tenantId || tenantId === actor.tenantId;
}

export async function getCycle(
  store: ControlPlaneStore,
  actor: ActorContext,
  cycleId: string,
  requestId: string | null,
): Promise<Response> {
  const db = await store.read();
  const cycle = db.cycles[cycleId];
  if (!cycle || !actorCanRead(actor, cycle.tenantId)) {
    throw new HttpError(404, "cycle_not_found", "Cycle not found.");
  }
  const approval = cycle.activeApprovalId ? db.approvals[cycle.activeApprovalId] ?? null : null;
  return dataResponse(200, buildCycleSummary(cycle, approval), requestId);
}

export async function getCycleResult(
  store: ControlPlaneStore,
  actor: ActorContext,
  cycleId: string,
  requestId: string | null,
): Promise<Response> {
  const db = await store.read();
  const cycle = db.cycles[cycleId];
  if (!cycle || !actorCanRead(actor, cycle.tenantId)) {
    throw new HttpError(404, "cycle_not_found", "Cycle not found.");
  }
  if (!isTerminalState(cycle.state) || !cycle.finalOutput) {
    throw new HttpError(409, "result_unavailable", "Final result is not available yet.");
  }
  return dataResponse(200, buildResultSummary(cycle), requestId);
}

export async function listPendingApprovals(
  store: ControlPlaneStore,
  actor: ActorContext,
  requestId: string | null,
): Promise<Response> {
  const db = await store.read();
  const items = Object.values(db.approvals)
    .filter((approval) => approval.approvalState === "pending")
    .filter((approval) => approval.requiredRole === actor.role)
    .filter((approval) => actorCanRead(actor, db.cycles[approval.cycleId]?.tenantId ?? null))
    .map((approval) => ({
      approval_id: approval.approvalId,
      cycle_id: approval.cycleId,
      required_role: approval.requiredRole,
      approval_state: approval.approvalState,
      created_at: approval.createdAt,
    }));
  return dataResponse(200, { items, count: items.length }, requestId);
}
