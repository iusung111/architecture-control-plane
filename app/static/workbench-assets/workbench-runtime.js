async function addRuntimeActionReceipt(actionId) {
  const runtimeId =
    selectedRuntimeId || document.getElementById("runtime-action-target").value.trim();
  if (!runtimeId || !actionId) return;
  let summary = "";
  let status = "";
  try {
    const modal = await openActionModal({
      title: "Runtime receipt",
      description: "Record receipt summary and optional status.",
      input: { value: "", placeholder: "Optional status" },
      textarea: { value: "", placeholder: "Receipt summary" },
      validate: (payload) => (payload.textarea ? "" : "Receipt summary is required."),
    });
    summary = modal.textarea || "";
    status = modal.input || "";
  } catch (error) {
    if (error.message === "cancelled") return;
    throw error;
  }
  const response = await fetch(
    `/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions/${encodeURIComponent(actionId)}/receipts`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({
        summary: summary.trim(),
        status: status || null,
        metadata: { source: "workbench" },
      }),
    },
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error")
    throw new Error(payload?.error?.message || `Runtime receipt failed (${response.status})`);
  selectedActionId = actionId;
  await refreshRuntimeActions(runtimeId);
  await refreshRuntimeActionReceipts(runtimeId, actionId);
}
async function refreshAuditExplorer() {
  const managementKey = document.getElementById("auth-management-key").value.trim();
  if (!managementKey) {
    auditExplorerEl.innerHTML =
      '<div class="empty">Enter X-Management-Key to load audit events.</div>';
    return;
  }
  try {
    const prefix = document.getElementById("audit-prefix-filter").value.trim();
    const data = await adminJson(
      `/v1/admin/audit/events${qs({ event_type_prefix: prefix || null, limit: 40 })}`,
    );
    renderAuditExplorer(data);
  } catch (error) {
    auditExplorerEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
async function enqueueRuntimeActionPanel() {
  const runtimeId =
    selectedRuntimeId || document.getElementById("runtime-action-target").value.trim();
  if (!runtimeId) {
    showToast("Select a runtime before enqueueing an action.", "error", "Runtime action");
    return;
  }
  const action = document.getElementById("runtime-action-name").value.trim();
  if (!action) {
    showToast("action name is required.", "error", "Runtime action");
    return;
  }
  let args = {};
  const rawArgs = document.getElementById("runtime-action-args").value.trim();
  if (rawArgs) {
    try {
      args = JSON.parse(rawArgs);
    } catch (_) {
      showToast("action arguments must be valid JSON.", "error", "Runtime action");
      return;
    }
  }
  const response = await fetch(
    `/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ action, arguments: args }),
    },
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error") {
    throw new Error(payload?.error?.message || `Runtime action failed (${response.status})`);
  }
  await refreshRuntimeActions(runtimeId);
}
async function acknowledgeRuntimeAction(actionId) {
  const runtimeId =
    selectedRuntimeId || document.getElementById("runtime-action-target").value.trim();
  if (!runtimeId || !actionId) return;
  let note = "";
  try {
    const modal = await openActionModal({
      title: "Acknowledge runtime action",
      description: "Add an optional acknowledgement note.",
      textarea: { value: "", placeholder: "Optional acknowledgement note" },
    });
    note = modal.textarea || "";
  } catch (error) {
    if (error.message === "cancelled") return;
    throw error;
  }
  const response = await fetch(
    `/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions/${encodeURIComponent(actionId)}/acknowledge`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ note: note || null }),
    },
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error") {
    throw new Error(
      payload?.error?.message || `Runtime action acknowledge failed (${response.status})`,
    );
  }
  await refreshRuntimeActions(runtimeId);
}
async function transitionRuntimeAction(actionId, nextStatus) {
  const runtimeId =
    selectedRuntimeId || document.getElementById("runtime-action-target").value.trim();
  if (!runtimeId || !actionId) return;
  let note = "";
  try {
    const modal = await openActionModal({
      title: "Transition runtime action",
      subtitle: nextStatus,
      description: "Add an optional note for the state transition.",
      textarea: { value: "", placeholder: `Optional note for ${nextStatus}` },
    });
    note = modal.textarea || "";
  } catch (error) {
    if (error.message === "cancelled") return;
    throw error;
  }
  const response = await fetch(
    `/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions/${encodeURIComponent(actionId)}/state`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({
        status: nextStatus,
        note: note || null,
        metadata: { source: "workbench" },
      }),
    },
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error") {
    throw new Error(
      payload?.error?.message || `Runtime action transition failed (${response.status})`,
    );
  }
  await refreshRuntimeActions(runtimeId);
}
async function registerRuntimePanel() {
  const runtimeId = document.getElementById("runtime-id").value.trim();
  const label = document.getElementById("runtime-label").value.trim();
  const projectId = document.getElementById("project-filter").value.trim();
  if (!runtimeId || !label) {
    showToast("runtime id and label are required.", "error", "Runtime registration");
    return;
  }
  const response = await fetch("/v1/runtime/registrations", {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({
      runtime_id: runtimeId,
      label,
      project_id: projectId || null,
      workspace_id: projectId || null,
      status: "online",
      mode: "daemon",
      version: "dev-ui",
      capabilities: ["board-stream", "cycle-stream"],
      metadata: { source: "workbench" },
    }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error") {
    throw new Error(payload?.error?.message || `Runtime registration failed (${response.status})`);
  }
  await refreshWorkspaceSurfaces();
}
async function refreshRuntimeActions(runtimeId) {
  if (!runtimeId) {
    runtimeActionsEl.innerHTML = '<div class="empty">Select a runtime to view actions.</div>';
    runtimeActionTimelineEl.innerHTML =
      '<div class="empty">Select a runtime action to view timeline.</div>';
    runtimeActionReceiptsEl.innerHTML =
      '<div class="empty">Select a runtime action to view receipts.</div>';
    if (runtimeActionAbortController) runtimeActionAbortController.abort();
    setStatus(runtimeActionStateEl, "idle");
    return;
  }
  try {
    const data = await apiJson(
      `/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions`,
    );
    renderRuntimeActions(data);
    if (selectedActionId) {
      await Promise.all([
        refreshRuntimeActionTimeline(runtimeId, selectedActionId),
        refreshRuntimeActionReceipts(runtimeId, selectedActionId),
      ]);
    }
  } catch (error) {
    runtimeActionsEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
async function startRuntimeActionStream(runtimeId, actionId) {
  if (!runtimeId || !actionId) return;
  if (runtimeActionAbortController) runtimeActionAbortController.abort();
  runtimeActionAbortController = new AbortController();
  setStatus(runtimeActionStateEl, "connecting");
  try {
    await consumeSSE(
      `/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions/${encodeURIComponent(actionId)}/events${qs({ poll_interval_seconds: 1, heartbeat_seconds: 15, stream_timeout_seconds: 600 })}`,
      (eventName, payload) => {
        if (eventName === "runtime.action.snapshot" && payload.runtime_action) {
          renderRuntimeActionTimeline({ items: payload.runtime_action.timeline || [] });
        }
        if (eventName !== "heartbeat") pushStreamItem(`runtime-action:${eventName}`, payload);
      },
      runtimeActionStateEl,
      runtimeActionAbortController,
    );
  } catch (error) {
    setStatus(runtimeActionStateEl, `error: ${error.message}`);
  }
}
async function refreshRuntimeActionTimeline(runtimeId, actionId) {
  if (!runtimeId || !actionId) {
    runtimeActionTimelineEl.innerHTML =
      '<div class="empty">Select a runtime action to view timeline.</div>';
    return;
  }
  try {
    const data = await apiJson(
      `/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions/${encodeURIComponent(actionId)}/timeline`,
    );
    renderRuntimeActionTimeline(data);
  } catch (error) {
    runtimeActionTimelineEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
async function refreshRuntimeActionReceipts(runtimeId, actionId) {
  if (!runtimeId || !actionId) {
    runtimeActionReceiptsEl.innerHTML =
      '<div class="empty">Select a runtime action to view receipts.</div>';
    return;
  }
  try {
    const data = await apiJson(
      `/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions/${encodeURIComponent(actionId)}/receipts`,
    );
    renderRuntimeActionReceipts(data);
  } catch (error) {
    runtimeActionReceiptsEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
async function selectRuntimeAction(runtimeId, actionId) {
  selectedRuntimeId = runtimeId;
  selectedActionId = actionId;
  await Promise.all([
    refreshRuntimeActionTimeline(runtimeId, actionId),
    refreshRuntimeActionReceipts(runtimeId, actionId),
  ]);
  startRuntimeActionStream(runtimeId, actionId);
}
