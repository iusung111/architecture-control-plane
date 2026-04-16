import { buildFinalOutput, nowIso } from "../domain/render";
import { approvalStates, cycleStates, userStatuses } from "../domain/states";
import type { ActorContext, ApprovalDecisionInput } from "../domain/types";
import { HttpError, readJson } from "../http/response";
import { buildRequestKey, getStoredReply, rememberReply } from "./idempotency";
import type { ControlPlaneStore } from "./store";

function validateDecision(input: ApprovalDecisionInput): ApprovalDecisionInput {
  if (input?.decision !== "approved" && input?.decision !== "rejected") {
    throw new HttpError(400, "invalid_decision", "decision must be approved or rejected.");
  }
  return input;
}

export async function confirmApproval(
  request: Request,
  store: ControlPlaneStore,
  actor: ActorContext,
  approvalId: string,
  requestId: string | null,
  idempotencyKey?: string,
): Promise<Response> {
  const input = validateDecision(await readJson<ApprovalDecisionInput>(request));
  const reply = await store.write((db) => {
    const replayKey = buildRequestKey("confirm-approval", actor, idempotencyKey, approvalId);
    const replay = getStoredReply(db, replayKey);
    if (replay) {
      return replay;
    }
    const approval = db.approvals[approvalId];
    if (!approval) {
      throw new HttpError(404, "approval_not_found", "Approval not found.");
    }
    if (approval.requiredRole !== actor.role) {
      throw new HttpError(403, "approval_forbidden", "Caller role cannot decide this approval.");
    }
    if (approval.approvalState !== approvalStates.PENDING) {
      throw new HttpError(409, "approval_already_decided", "Approval already decided.");
    }
    const cycle = db.cycles[approval.cycleId];
    if (!cycle) {
      throw new HttpError(404, "cycle_not_found", "Cycle not found.");
    }
    approval.approvalState =
      input.decision === "approved" ? approvalStates.APPROVED : approvalStates.REJECTED;
    approval.comment = input.comment ?? null;
    approval.reasonCode = input.reason_code ?? null;
    approval.actorId = actor.userId;
    approval.actedAt = nowIso();
    cycle.activeApprovalId = null;
    cycle.updatedAt = approval.actedAt;
    cycle.finalOutput =
      input.decision === "approved" ? buildFinalOutput(cycle, input.comment ?? "approved") : "approval rejected";
    cycle.state =
      input.decision === "approved" ? cycleStates.TERMINALIZED : cycleStates.TERMINAL_FAIL;
    cycle.userStatus =
      input.decision === "approved" ? userStatuses.COMPLETED : userStatuses.FAILED;
    const body = {
      data: {
        approval_id: approvalId,
        approval_state: approval.approvalState,
        cycle_id: cycle.cycleId,
        resume_enqueued: input.decision === "approved",
        acted_at: approval.actedAt,
      },
      request_id: requestId,
    };
    rememberReply(db, replayKey, { status: 200, body });
    return { status: 200, body };
  });
  return Response.json(reply.body, { status: reply.status });
}
