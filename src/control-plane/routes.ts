import { actorFromRequest, idempotencyKeyFromRequest, requestIdFromRequest } from "../http/auth";
import { HttpError, errorResponse } from "../http/response";
import { confirmApproval } from "./confirm-approval";
import { createCycle } from "./create-cycle";
import { getCycle, getCycleResult, listPendingApprovals } from "./read-cycle";
import { replanCycle, retryCycle } from "./mutate-cycle";
import type { ControlPlaneStore } from "./store";

const cyclePattern = new URLPattern({ pathname: "/v1/cycles/:cycleId" });
const resultPattern = new URLPattern({ pathname: "/v1/cycles/:cycleId/result" });
const retryPattern = new URLPattern({ pathname: "/v1/cycles/:cycleId/retry" });
const replanPattern = new URLPattern({ pathname: "/v1/cycles/:cycleId/replan" });
const approvalPattern = new URLPattern({ pathname: "/v1/approvals/:approvalId/confirm" });

function requireParam(value: string | undefined, name: string): string {
  if (!value) {
    throw new HttpError(400, "missing_param", `${name} is required.`);
  }
  return value;
}

export async function routeControlPlane(store: ControlPlaneStore, request: Request): Promise<Response> {
  const requestId = requestIdFromRequest(request);
  try {
    const actor = actorFromRequest(request);
    const idempotencyKey = idempotencyKeyFromRequest(request);
    const url = new URL(request.url);
    if (request.method === "POST" && url.pathname === "/v1/cycles") {
      return createCycle(request, store, actor, requestId, idempotencyKey);
    }
    if (request.method === "GET" && url.pathname === "/v1/approvals/pending") {
      return listPendingApprovals(store, actor, requestId);
    }
    const cycleMatch = cyclePattern.exec(url);
    if (request.method === "GET" && cycleMatch) {
      return getCycle(store, actor, requireParam(cycleMatch.pathname.groups.cycleId, "cycleId"), requestId);
    }
    const resultMatch = resultPattern.exec(url);
    if (request.method === "GET" && resultMatch) {
      return getCycleResult(store, actor, requireParam(resultMatch.pathname.groups.cycleId, "cycleId"), requestId);
    }
    const retryMatch = retryPattern.exec(url);
    if (request.method === "POST" && retryMatch) {
      return retryCycle(request, store, actor, requireParam(retryMatch.pathname.groups.cycleId, "cycleId"), requestId, idempotencyKey);
    }
    const replanMatch = replanPattern.exec(url);
    if (request.method === "POST" && replanMatch) {
      return replanCycle(request, store, actor, requireParam(replanMatch.pathname.groups.cycleId, "cycleId"), requestId, idempotencyKey);
    }
    const approvalMatch = approvalPattern.exec(url);
    if (request.method === "POST" && approvalMatch) {
      return confirmApproval(request, store, actor, requireParam(approvalMatch.pathname.groups.approvalId, "approvalId"), requestId, idempotencyKey);
    }
    throw new HttpError(404, "route_not_found", "Route not found.");
  } catch (error) {
    if (error instanceof HttpError) {
      return errorResponse(error, requestId);
    }
    const unknown = new HttpError(500, "internal_error", "Unhandled control-plane error.");
    return errorResponse(unknown, requestId);
  }
}
