async function refreshRemoteWorkspaceSection() {
  try {
    const projectId = document.getElementById("project-filter").value.trim();
    const cycleId = selectedCycleId || selectedCycleInput.value.trim();
    if (!document.getElementById("remote-workspace-id").value.trim() && cycleId) {
      document.getElementById("remote-workspace-id").value = `cycle:${cycleId}`;
    }
    const workspaceId = document.getElementById("remote-workspace-id").value.trim();
    const [executors, snapshots, views, persistentSessions] = await Promise.all([
      apiJson("/v1/remote-workspaces/executors"),
      apiJson(`/v1/remote-workspaces/snapshots${qs({ project_id: projectId || null })}`),
      apiJson("/v1/workbench/views"),
      apiJson("/v1/remote-workspaces/persistent/sessions").catch(() => ({ items: [] })),
    ]);
    renderRemoteWorkspaceExecutors(executors);
    renderRemoteWorkspaceSnapshots(snapshots);
    renderWorkbenchSavedViews(views);
    renderPersistentWorkspaceSessions(persistentSessions);
    if (!defaultWorkbenchViewApplied) await applyDefaultWorkbenchView();
    if (workspaceId) {
      const [executions, resume] = await Promise.all([
        apiJson(`/v1/remote-workspaces/${encodeURIComponent(workspaceId)}/executions`),
        apiJson(`/v1/remote-workspaces/${encodeURIComponent(workspaceId)}/resume`).catch(
          () => null,
        ),
      ]);
      renderRemoteWorkspaceExecutions(executions);
      renderRemoteWorkspaceResume(resume);
      if (
        selectedExecutionId &&
        (executions.items || []).some((item) => item.execution_id === selectedExecutionId)
      ) {
        const detail = await apiJson(
          `/v1/remote-workspaces/executions/${encodeURIComponent(selectedExecutionId)}`,
        ).catch(() => null);
        renderRemoteWorkspaceExecutionDetail(detail);
      } else {
        renderRemoteWorkspaceExecutionDetail((executions.items || [])[0] || null);
      }
    } else {
      renderRemoteWorkspaceExecutions({ items: [] });
      renderRemoteWorkspaceResume(null);
      renderRemoteWorkspaceExecutionDetail(null);
    }
  } catch (error) {
    remoteWorkspaceExecutorsEl.innerHTML = `<div class="empty">${error.message}</div>`;
    remoteWorkspaceSnapshotsEl.innerHTML = `<div class="empty">${error.message}</div>`;
    remoteWorkspaceExecutionsEl.innerHTML = `<div class="empty">${error.message}</div>`;
    remoteWorkspaceExecutionDetailEl.innerHTML = `<div class="empty">${error.message}</div>`;
    persistentWorkspaceSessionsEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
async function saveRemoteWorkspaceSnapshot() {
  const payload = {
    workspace_id: document.getElementById("remote-workspace-id").value.trim() || null,
    cycle_id: selectedCycleId || selectedCycleInput.value.trim() || null,
    project_id: document.getElementById("project-filter").value.trim() || null,
    repo_url: document.getElementById("remote-workspace-repo-url").value.trim() || null,
    repo_branch: document.getElementById("remote-workspace-repo-branch").value.trim() || null,
    execution_profile: "phase1",
  };
  const response = await fetch("/v1/remote-workspaces/snapshots", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || "Failed to save remote workspace snapshot");
  selectedWorkspaceId = body?.data?.workspace_id || payload.workspace_id;
  document.getElementById("remote-workspace-id").value = selectedWorkspaceId || "";
  await refreshRemoteWorkspaceSection();
}
async function inspectRemoteWorkspaceExecution(executionId) {
  selectedExecutionId = executionId;
  const payload = await apiJson(
    `/v1/remote-workspaces/executions/${encodeURIComponent(executionId)}`,
  );
  renderRemoteWorkspaceExecutionDetail(payload);
}
async function cancelRemoteWorkspaceExecution(executionId) {
  const response = await fetch(
    `/v1/remote-workspaces/executions/${encodeURIComponent(executionId)}/cancel`,
    {
      method: "POST",
      headers: authHeaders(),
    },
  );
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || "Failed to cancel remote execution");
  await refreshRemoteWorkspaceSection();
}
async function requestRemoteWorkspaceExecution(kind) {
  const workspaceId = document.getElementById("remote-workspace-id").value.trim();
  if (!workspaceId) {
    showToast("Save a remote workspace snapshot first.", "error", "Remote workspace");
    return;
  }
  const payload = {
    workspace_id: workspaceId,
    execution_kind: kind,
    command: document.getElementById("remote-workspace-command").value.trim() || null,
    repo_url: document.getElementById("remote-workspace-repo-url").value.trim() || null,
    repo_branch: document.getElementById("remote-workspace-repo-branch").value.trim() || null,
  };
  const response = await fetch("/v1/remote-workspaces/executions", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || "Failed to queue remote execution");
  selectedExecutionId = body?.data?.execution_id || selectedExecutionId;
  await refreshRemoteWorkspaceSection();
}
async function resumeRemoteWorkspace() {
  const workspaceId = document.getElementById("remote-workspace-id").value.trim();
  if (!workspaceId) {
    showToast("Select a remote workspace first.", "error", "Remote workspace");
    return;
  }
  const response = await fetch(`/v1/remote-workspaces/${encodeURIComponent(workspaceId)}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      note: document.getElementById("remote-resume-note").value.trim() || null,
    }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || "Failed to resume remote workspace");
  renderRemoteWorkspaceResume(body.data);
  await refreshRemoteWorkspaceSection();
}
async function savePersistentWorkspaceSession() {
  const workspaceId = document.getElementById("remote-workspace-id").value.trim();
  if (!workspaceId) {
    showToast("Select or save a remote workspace first.", "error", "Persistent workspace");
    return;
  }
  const payload = {
    workspace_id: workspaceId,
    cycle_id: selectedCycleId || selectedCycleInput.value.trim() || null,
    project_id: document.getElementById("project-filter").value.trim() || null,
    repo_url: document.getElementById("remote-workspace-repo-url").value.trim() || null,
    repo_branch: document.getElementById("remote-workspace-repo-branch").value.trim() || null,
    note: document.getElementById("remote-resume-note").value.trim() || "promoted from workbench",
    provider: "workbench",
  };
  const response = await fetch("/v1/remote-workspaces/persistent/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || "Failed to save persistent session");
  await refreshRemoteWorkspaceSection();
}
async function hibernatePersistentWorkspaceSession(workspaceId) {
  const response = await fetch(
    `/v1/remote-workspaces/persistent/sessions/${encodeURIComponent(workspaceId)}/hibernate`,
    {
      method: "POST",
      headers: authHeaders(),
    },
  );
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || "Failed to hibernate persistent session");
  await refreshRemoteWorkspaceSection();
}
async function deletePersistentWorkspaceSession(workspaceId) {
  const response = await fetch(
    `/v1/remote-workspaces/persistent/sessions/${encodeURIComponent(workspaceId)}`,
    {
      method: "DELETE",
      headers: authHeaders(),
    },
  );
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || "Failed to delete persistent session");
  await refreshRemoteWorkspaceSection();
}
