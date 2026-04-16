function setStatus(el, value) {
  el.textContent = value;
}
function nowLabel() {
  return new Date().toLocaleString();
}
function setAuthStatus(message) {
  authStatusEl.textContent = message || "";
}
function authValidationSummary() {
  const bearer = document.getElementById("auth-bearer").value.trim();
  const userId = document.getElementById("auth-user-id").value.trim();
  const userRole = document.getElementById("auth-user-role").value.trim();
  const managementKey = document.getElementById("auth-management-key").value.trim();
  const userApiReady = Boolean(bearer || userId);
  const actorReady = Boolean(userId && userRole);
  const auditReady = Boolean(managementKey);
  if (!userApiReady) return "User API headers are incomplete. Add Bearer token or X-User-Id.";
  if (!actorReady) return "Add X-User-Id and X-User-Role to use cycle actions safely.";
  if (!auditReady) return "User APIs ready. Add X-Management-Key for audit explorer.";
  return "Headers look ready for board, cycle actions, and audit explorer.";
}
function applyAuthPreset(kind) {
  const roleInput = document.getElementById("auth-user-role");
  const userInput = document.getElementById("auth-user-id");
  if (kind === "operator") {
    if (!userInput.value.trim()) userInput.value = "operator-1";
    roleInput.value = "operator";
    setAuthStatus("Operator preset applied. Review X-User-Id before connecting.");
  } else if (kind === "reviewer") {
    if (!userInput.value.trim()) userInput.value = "reviewer-1";
    roleInput.value = "operator";
    setAuthStatus("Reviewer preset applied for approval handling. Update X-User-Id as needed.");
  } else if (kind === "audit") {
    if (!userInput.value.trim()) userInput.value = "operator-1";
    roleInput.value = "operator";
    setAuthStatus("Audit preset applied. Add X-Management-Key to unlock audit explorer.");
  }
}
function saveAuth() {
  const payload = {
    bearer: document.getElementById("auth-bearer").value.trim(),
    userId: document.getElementById("auth-user-id").value.trim(),
    userRole: document.getElementById("auth-user-role").value.trim(),
    tenantId: document.getElementById("auth-tenant-id").value.trim(),
    managementKey: document.getElementById("auth-management-key").value.trim(),
  };
  localStorage.setItem(storageKey, JSON.stringify(payload));
  setAuthStatus("Saved request headers locally in this browser.");
}
function loadAuth() {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return;
    const payload = JSON.parse(raw);
    document.getElementById("auth-bearer").value = payload.bearer || "";
    document.getElementById("auth-user-id").value = payload.userId || "";
    document.getElementById("auth-user-role").value = payload.userRole || "operator";
    document.getElementById("auth-tenant-id").value = payload.tenantId || "";
    document.getElementById("auth-management-key").value = payload.managementKey || "";
  } catch (_) {}
}
function clearAuth() {
  localStorage.removeItem(storageKey);
  loadAuth();
  document.getElementById("auth-bearer").value = "";
  document.getElementById("auth-user-id").value = "";
  document.getElementById("auth-user-role").value = "operator";
  document.getElementById("auth-tenant-id").value = "";
  document.getElementById("auth-management-key").value = "";
  setAuthStatus("Cleared saved request headers.");
}
function authHeaders() {
  const headers = { Accept: "application/json" };
  const bearer = document.getElementById("auth-bearer").value.trim();
  const userId = document.getElementById("auth-user-id").value.trim();
  const userRole = document.getElementById("auth-user-role").value.trim();
  const tenantId = document.getElementById("auth-tenant-id").value.trim();
  const managementKey = document.getElementById("auth-management-key").value.trim();
  if (bearer) headers["Authorization"] = bearer.startsWith("Bearer ") ? bearer : `Bearer ${bearer}`;
  if (userId) headers["X-User-Id"] = userId;
  if (userRole) headers["X-User-Role"] = userRole;
  if (tenantId) headers["X-Tenant-Id"] = tenantId;
  if (managementKey) headers["X-Management-Key"] = managementKey;
  return headers;
}
function managementHeaders() {
  const managementKey = document.getElementById("auth-management-key").value.trim();
  return managementKey
    ? { Accept: "application/json", "X-Management-Key": managementKey }
    : { Accept: "application/json" };
}
function qs(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && String(v).length) search.set(k, v);
  });
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}
async function apiJson(path) {
  const response = await fetch(path, { headers: authHeaders() });
  const body = await response.json();
  if (!response.ok || body.status === "error") {
    throw new Error(body?.error?.message || `Request failed (${response.status})`);
  }
  return body.data;
}
async function adminJson(path) {
  const response = await fetch(path, { headers: managementHeaders() });
  const body = await response.json();
  if (!response.ok || body.status === "error") {
    throw new Error(body?.error?.message || `Request failed (${response.status})`);
  }
  return body.data;
}
