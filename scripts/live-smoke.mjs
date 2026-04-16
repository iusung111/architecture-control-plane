const baseUrl = (process.argv[2] || process.env.SMOKE_BASE_URL || "").replace(/\/$/, "");

if (!baseUrl) {
  throw new Error("Provide a base URL as argv[2] or SMOKE_BASE_URL.");
}

const actorHeaders = {
  "Content-Type": "application/json",
  "X-Tenant-Id": "tenant-live",
  "X-User-Id": "live-smoke",
  "X-User-Role": "operator",
};

async function call(method, path, body, key) {
  const headers = new Headers(actorHeaders);
  headers.set("X-Request-Id", crypto.randomUUID());
  if (key) headers.set("Idempotency-Key", key);
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`${method} ${path} failed: ${response.status} ${JSON.stringify(payload)}`);
  }
  return payload;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

console.log(`smoke target: ${baseUrl}`);
assert((await call("GET", "/healthz")).ok === true, "healthz failed");
assert((await call("GET", "/readyz")).ok === true, "readyz failed");

const idempotencyKey = crypto.randomUUID();
const created = await call("POST", "/v1/cycles", { project_id: "acp", user_input: "live happy path" }, idempotencyKey);
const replay = await call("POST", "/v1/cycles", { project_id: "acp", user_input: "live happy path" }, idempotencyKey);
assert(created.data.cycle_id === replay.data.cycle_id, "idempotency replay diverged");
await call("GET", `/v1/cycles/${created.data.cycle_id}/result`);

const approvalCycle = await call("POST", "/v1/cycles", {
  project_id: "acp",
  user_input: "approval path",
  metadata: { requires_approval: true },
});
const pending = await call("GET", "/v1/approvals/pending");
const approvalId = pending.data.items.find((item) => item.cycle_id === approvalCycle.data.cycle_id)?.approval_id;
assert(Boolean(approvalId), "approval was not listed");
await call("POST", `/v1/approvals/${approvalId}/confirm`, { decision: "approved", comment: "live approved" }, crypto.randomUUID());

const failed = await call("POST", "/v1/cycles", {
  project_id: "acp",
  user_input: "retry path",
  metadata: { force_verification_failure: true },
});
await call("POST", `/v1/cycles/${failed.data.cycle_id}/retry`, { reason: "live retry" }, crypto.randomUUID());
await call("GET", `/v1/cycles/${failed.data.cycle_id}/result`);

const replanned = await call("POST", "/v1/cycles", {
  project_id: "acp",
  user_input: "replan path",
  metadata: { force_verification_failure: true },
});
await call(
  "POST",
  `/v1/cycles/${replanned.data.cycle_id}/replan`,
  { override_input: { prompt: "live replan" } },
  crypto.randomUUID(),
);
await call("GET", `/v1/cycles/${replanned.data.cycle_id}/result`);
console.log("live smoke passed");
