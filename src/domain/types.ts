import type { ApprovalState, CycleState, UserStatus } from "./states";

export interface ActorContext {
  userId: string;
  role: string;
  tenantId: string | null;
}

export interface CycleMetadata {
  requires_approval?: boolean;
  required_role?: string;
  force_verification_failure?: boolean;
  final_output?: string;
}

export interface CreateCycleInput {
  project_id: string;
  user_input: string;
  metadata?: CycleMetadata;
}

export interface RetryInput {
  reason?: string;
}

export interface ReplanInput {
  reason?: string;
  override_input?: {
    prompt?: string;
  };
}

export interface ApprovalDecisionInput {
  decision: "approved" | "rejected";
  comment?: string;
  reason_code?: string;
}

export interface ApprovalRecord {
  approvalId: string;
  cycleId: string;
  approvalState: ApprovalState;
  requiredRole: string;
  comment: string | null;
  reasonCode: string | null;
  actorId: string | null;
  createdAt: string;
  actedAt: string | null;
}

export interface CycleRecord {
  cycleId: string;
  projectId: string;
  userInput: string;
  state: CycleState;
  userStatus: UserStatus;
  approvalRequired: boolean;
  activeApprovalId: string | null;
  finalOutput: string | null;
  latestIteration: number;
  createdAt: string;
  updatedAt: string;
  actorUserId: string;
  actorRole: string;
  tenantId: string | null;
  metadata: CycleMetadata;
}

export interface StoredReply {
  status: number;
  body: unknown;
}

export interface ControlPlaneDatabase {
  approvals: Record<string, ApprovalRecord>;
  cycles: Record<string, CycleRecord>;
  requests: Record<string, StoredReply>;
}
