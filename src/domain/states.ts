export const cycleStates = {
  HUMAN_APPROVAL_PENDING: "human_approval_pending",
  VERIFICATION_FAILED: "verification_failed",
  TERMINALIZED: "terminalized",
  TERMINAL_FAIL: "terminal_fail",
} as const;

export const userStatuses = {
  APPROVAL_REQUIRED: "approval_required",
  ACTION_REQUIRED: "action_required",
  COMPLETED: "completed",
  FAILED: "failed",
} as const;

export const approvalStates = {
  PENDING: "pending",
  APPROVED: "approved",
  REJECTED: "rejected",
} as const;

export type CycleState = (typeof cycleStates)[keyof typeof cycleStates];
export type UserStatus = (typeof userStatuses)[keyof typeof userStatuses];
export type ApprovalState = (typeof approvalStates)[keyof typeof approvalStates];

export function isRetryAllowed(state: string): boolean {
  return state === cycleStates.VERIFICATION_FAILED;
}

export function isReplanAllowed(state: string): boolean {
  return state === cycleStates.VERIFICATION_FAILED;
}

export function isTerminalState(state: string): boolean {
  return state === cycleStates.TERMINALIZED || state === cycleStates.TERMINAL_FAIL;
}
