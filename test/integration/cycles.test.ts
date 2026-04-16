import { describe, expect, it } from "vitest";
import { call } from "../support";

describe("cycle flows", () => {
  it("creates a terminal cycle and replays idempotency", async () => {
    const key = crypto.randomUUID();
    const payload = { project_id: "acp", user_input: "ship worker rewrite" };
    const created = await call("/v1/cycles", { method: "POST", body: JSON.stringify(payload), headers: { "Idempotency-Key": key } });
    expect(created.response.status).toBe(201);
    expect(created.body.data.state).toBe("terminalized");
    const replay = await call("/v1/cycles", { method: "POST", body: JSON.stringify(payload), headers: { "Idempotency-Key": key } });
    expect(replay.response.status).toBe(200);
    expect(replay.body.data.cycle_id).toBe(created.body.data.cycle_id);
    const result = await call(`/v1/cycles/${created.body.data.cycle_id}/result`);
    expect(result.response.status).toBe(200);
  });

  it("supports retry and replan from verification failure", async () => {
    const failed = await call("/v1/cycles", {
      method: "POST",
      body: JSON.stringify({ project_id: "acp", user_input: "force retry", metadata: { force_verification_failure: true } }),
    });
    const cycleId = failed.body.data.cycle_id;
    expect(failed.body.data.retry_allowed).toBe(true);
    const retried = await call(`/v1/cycles/${cycleId}/retry`, {
      method: "POST",
      body: JSON.stringify({ reason: "rerun" }),
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
    expect(retried.response.status).toBe(202);
    const retryResult = await call(`/v1/cycles/${cycleId}/result`);
    expect(retryResult.body.data.output).toContain("rerun");
    const replannedCycle = await call("/v1/cycles", {
      method: "POST",
      body: JSON.stringify({ project_id: "acp", user_input: "force replan", metadata: { force_verification_failure: true } }),
    });
    const replanned = await call(`/v1/cycles/${replannedCycle.body.data.cycle_id}/replan`, {
      method: "POST",
      body: JSON.stringify({ override_input: { prompt: "safer plan" } }),
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
    expect(replanned.response.status).toBe(202);
    const replanResult = await call(`/v1/cycles/${replannedCycle.body.data.cycle_id}/result`);
    expect(replanResult.body.data.output).toContain("safer plan");
  });
});
