import { buildCycleSummary, buildFinalOutput, nowIso } from "../domain/render";
import { approvalStates, cycleStates, userStatuses } from "../domain/states";
import type { ActorContext, ApprovalRecord, CreateCycleInput, CycleRecord } from "../domain/types";
import { HttpError, dataResponse, readJson } from "../http/response";
import { buildRequestKey, getStoredReply, rememberReply } from "./idempotency";
import type { ControlPlaneStore } from "./store";

function validateCreateInput(input: CreateCycleInput): CreateCycleInput {
  if (!input || typeof input.project_id !== "string" || typeof input.user_input !== "string") {
    throw new HttpError(400, "invalid_payload", "project_id and user_input are required.");
  }
  return input;
}

export async function createCycle(
  request: Request,
  store: ControlPlaneStore,
  actor: ActorContext,
  requestId: string | null,
  idempotencyKey?: string,
): Promise<Response> {
  const input = validateCreateInput(await readJson<CreateCycleInput>(request));
  const reply = await store.write((db) => {
    const replayKey = buildRequestKey("create-cycle", actor, idempotencyKey);
    const replay = getStoredReply(db, replayKey);
    if (replay) {
      return replay;
    }
    const createdAt = nowIso();
    const cycleId = crypto.randomUUID();
    const approvalId = input.metadata?.requires_approval ? crypto.randomUUID() : null;
    const baseCycle: CycleRecord = {
      cycleId,
      projectId: input.project_id,
      userInput: input.user_input,
      state: cycleStates.TERMINALIZED,
      userStatus: userStatuses.COMPLETED,
      approvalRequired: Boolean(approvalId),
      activeApprovalId: approvalId,
      finalOutput: null,
      latestIteration: 1,
      createdAt,
      updatedAt: createdAt,
      actorUserId: actor.userId,
      actorRole: actor.role,
      tenantId: actor.tenantId,
      metadata: input.metadata ?? {},
    };
    let approval: ApprovalRecord | null = null;
    if (approvalId) {
      baseCycle.state = cycleStates.HUMAN_APPROVAL_PENDING;
      baseCycle.userStatus = userStatuses.APPROVAL_REQUIRED;
      approval = {
        approvalId,
        cycleId,
        approvalState: approvalStates.PENDING,
        requiredRole: input.metadata?.required_role ?? actor.role,
        comment: null,
        reasonCode: null,
        actorId: null,
        createdAt,
        actedAt: null,
      };
      db.approvals[approvalId] = approval;
    } else if (input.metadata?.force_verification_failure) {
      baseCycle.state = cycleStates.VERIFICATION_FAILED;
      baseCycle.userStatus = userStatuses.ACTION_REQUIRED;
    } else {
      baseCycle.finalOutput = buildFinalOutput(baseCycle, "initial");
    }
    db.cycles[cycleId] = baseCycle;
    const body = { data: buildCycleSummary(baseCycle, approval), request_id: requestId };
    rememberReply(db, replayKey, { status: 200, body });
    return { status: 201, body };
  });
  return Response.json(reply.body, { status: reply.status });
}
