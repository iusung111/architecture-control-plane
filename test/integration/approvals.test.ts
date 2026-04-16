import { describe, expect, it } from "vitest";
import { call } from "../support";

describe("approval flows", () => {
  it("lists and confirms pending approvals", async () => {
    const created = await call("/v1/cycles", {
      method: "POST",
      body: JSON.stringify({
        project_id: "acp",
        user_input: "needs human review",
        metadata: { requires_approval: true, required_role: "operator" },
      }),
    });
    expect(created.body.data.state).toBe("human_approval_pending");
    const pending = await call("/v1/approvals/pending");
    expect(pending.body.data.count).toBe(1);
    const approvalId = pending.body.data.items[0].approval_id;
    const decided = await call(`/v1/approvals/${approvalId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ decision: "approved", comment: "looks good" }),
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
    expect(decided.response.status).toBe(200);
    expect(decided.body.data.approval_state).toBe("approved");
    const summary = await call(`/v1/cycles/${created.body.data.cycle_id}`);
    expect(summary.body.data.state).toBe("terminalized");
    const result = await call(`/v1/cycles/${created.body.data.cycle_id}/result`);
    expect(result.body.data.output).toContain("looks good");
  });
});
