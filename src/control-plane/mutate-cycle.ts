import { buildFinalOutput, nowIso } from "../domain/render";
import { cycleStates, userStatuses } from "../domain/states";
import type { ActorContext, ReplanInput, RetryInput } from "../domain/types";
import { HttpError, dataResponse, readJson } from "../http/response";
import { buildRequestKey, getStoredReply, rememberReply } from "./idempotency";
import type { ControlPlaneStore } from "./store";

function assertVerificationFailed(state: string): void {
  if (state !== cycleStates.VERIFICATION_FAILED) {
    throw new HttpError(409, "invalid_state", "Action requires verification_failed.");
  }
}

async function acceptMutation(
  store: ControlPlaneStore,
  actor: ActorContext,
  cycleId: string,
  requestId: string | null,
  action: "retry" | "replan",
  note: string,
  idempotencyKey?: string,
) {
  const reply = await store.write((db) => {
    const replayKey = buildRequestKey(action, actor, idempotencyKey, cycleId);
    const replay = getStoredReply(db, replayKey);
    if (replay) {
      return replay;
    }
    const cycle = db.cycles[cycleId];
    if (!cycle) {
      throw new HttpError(404, "cycle_not_found", "Cycle not found.");
    }
    assertVerificationFailed(cycle.state);
    cycle.latestIteration += 1;
    cycle.state = cycleStates.TERMINALIZED;
    cycle.userStatus = userStatuses.COMPLETED;
    cycle.finalOutput = buildFinalOutput(cycle, note);
    cycle.updatedAt = nowIso();
    const body = {
      data: { accepted: true, action, cycle_id: cycleId, state: cycle.state, updated_at: cycle.updatedAt },
      request_id: requestId,
    };
    rememberReply(db, replayKey, { status: 202, body });
    return { status: 202, body };
  });
  return Response.json(reply.body, { status: reply.status });
}

export async function retryCycle(
  request: Request,
  store: ControlPlaneStore,
  actor: ActorContext,
  cycleId: string,
  requestId: string | null,
  idempotencyKey?: string,
): Promise<Response> {
  const input = await readJson<RetryInput>(request);
  return acceptMutation(store, actor, cycleId, requestId, "retry", input.reason ?? "retry", idempotencyKey);
}

export async function replanCycle(
  request: Request,
  store: ControlPlaneStore,
  actor: ActorContext,
  cycleId: string,
  requestId: string | null,
  idempotencyKey?: string,
): Promise<Response> {
  const input = await readJson<ReplanInput>(request);
  const note = input.override_input?.prompt ?? input.reason ?? "replan";
  return acceptMutation(store, actor, cycleId, requestId, "replan", note, idempotencyKey);
}
