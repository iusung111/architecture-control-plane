import type { ApprovalRecord, CycleRecord } from "./types";
import { isReplanAllowed, isRetryAllowed } from "./states";

export function nowIso(): string {
  return new Date().toISOString();
}

export function buildFinalOutput(cycle: CycleRecord, note: string): string {
  if (note === "initial" && cycle.metadata.final_output) {
    return cycle.metadata.final_output;
  }
  return `${cycle.projectId} :: iteration ${cycle.latestIteration} :: ${note}`;
}

export function buildApprovalSummary(approval: ApprovalRecord | null) {
  if (!approval) {
    return null;
  }
  return {
    approval_id: approval.approvalId,
    approval_state: approval.approvalState,
    required_role: approval.requiredRole,
    acted_at: approval.actedAt,
  };
}

export function buildCycleSummary(cycle: CycleRecord, approval: ApprovalRecord | null) {
  return {
    cycle_id: cycle.cycleId,
    state: cycle.state,
    user_status: cycle.userStatus,
    approval_required: cycle.approvalRequired,
    retry_allowed: isRetryAllowed(cycle.state),
    replan_allowed: isReplanAllowed(cycle.state),
    created_at: cycle.createdAt,
    updated_at: cycle.updatedAt,
    active_approval: buildApprovalSummary(approval),
  };
}

export function buildResultSummary(cycle: CycleRecord) {
  return {
    cycle_id: cycle.cycleId,
    final_state: cycle.state,
    output: cycle.finalOutput,
    updated_at: cycle.updatedAt,
  };
}
