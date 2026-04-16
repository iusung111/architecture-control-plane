async function saveWorkbenchView(overrides = {}) {
  const payload = {
    name:
      overrides.name ||
      document.getElementById("workbench-view-name").value.trim() ||
      `view-${Date.now()}`,
    project_id: document.getElementById("project-filter").value.trim() || null,
    cycle_id: selectedCycleId || selectedCycleInput.value.trim() || null,
    workspace_id: document.getElementById("remote-workspace-id").value.trim() || null,
    query: document.getElementById("discussion-search-filter").value.trim() || null,
    discussion_filter_id: null,
    layout: {
      boardTotal: boardTotalEl.textContent,
      runtimeAction: runtimeActionStateEl.textContent,
      smart_filter: activeSmartFilter,
      is_default: Boolean(overrides.is_default),
    },
    selected_panels: ["board", "timeline", "remote-workspace"],
    notes:
      overrides.notes !== undefined
        ? overrides.notes
        : document.getElementById("workbench-view-notes").value.trim() || "saved from workbench",
  };
  const response = await fetch("/v1/workbench/views", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || "Failed to save workbench view");
  await refreshRemoteWorkspaceSection();
}
async function useWorkbenchView(viewId, options = {}) {
  const response = await fetch(`/v1/workbench/views/${encodeURIComponent(viewId)}/use`, {
    method: "POST",
    headers: authHeaders(),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || "Failed to use workbench view");
  const item = body.data;
  document.getElementById("project-filter").value = item.project_id || "";
  selectedCycleInput.value = item.cycle_id || "";
  document.getElementById("remote-workspace-id").value = item.workspace_id || "";
  document.getElementById("discussion-search-filter").value = item.query || "";
  activeSmartFilter = item.layout?.smart_filter || "all";
  document
    .querySelectorAll("#smart-filters [data-smart-filter]")
    .forEach((button) =>
      button.classList.toggle(
        "active",
        (button.dataset.smartFilter || "all") === activeSmartFilter,
      ),
    );
  if (item.cycle_id) selectedCycleId = item.cycle_id;
  await refreshBoard();
  await refreshWorkspaceSurfaces();
  await refreshRemoteWorkspaceSection();
  if (!options.silent) showToast(`Applied view ${item.name}.`, "success", "Workbench view");
  if (item.cycle_id) selectCycle(item.cycle_id);
}
async function deleteWorkbenchView(viewId) {
  const response = await fetch(`/v1/workbench/views/${encodeURIComponent(viewId)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || "Failed to delete workbench view");
  await refreshRemoteWorkspaceSection();
}
async function updateWorkbenchView(viewId, overrides) {
  const current = (latestWorkbenchViews?.items || []).find((item) => item.view_id === viewId);
  if (!current) throw new Error("workbench view not found in current session");
  const payload = {
    name: overrides?.name || current.name,
    project_id: overrides?.project_id !== undefined ? overrides.project_id : current.project_id,
    cycle_id: overrides?.cycle_id !== undefined ? overrides.cycle_id : current.cycle_id,
    workspace_id:
      overrides?.workspace_id !== undefined ? overrides.workspace_id : current.workspace_id,
    query: overrides?.query !== undefined ? overrides.query : current.query,
    discussion_filter_id: current.discussion_filter_id || null,
    layout: { ...(current.layout || {}), ...(overrides?.layout || {}) },
    selected_panels: overrides?.selected_panels || current.selected_panels || [],
    notes: overrides?.notes !== undefined ? overrides.notes : current.notes,
  };
  const response = await fetch(`/v1/workbench/views/${encodeURIComponent(viewId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || "Failed to update workbench view");
  await refreshRemoteWorkspaceSection();
  return body.data;
}
async function markWorkbenchViewDefault(viewId) {
  const items = latestWorkbenchViews?.items || [];
  await Promise.all(
    items
      .filter((item) => item.layout?.is_default && item.view_id !== viewId)
      .map((item) =>
        updateWorkbenchView(item.view_id, {
          layout: { ...(item.layout || {}), is_default: false },
        }),
      ),
  );
  await updateWorkbenchView(viewId, { layout: { is_default: true } });
  showToast("Default workbench view updated.", "success", "Workbench view");
}
async function applyDefaultWorkbenchView() {
  if (defaultWorkbenchViewApplied) return;
  const view = findDefaultWorkbenchView();
  if (!view) return;
  defaultWorkbenchViewApplied = true;
  await useWorkbenchView(view.view_id, { silent: true });
}
async function renameWorkbenchView(viewId) {
  const current = (latestWorkbenchViews?.items || []).find((item) => item.view_id === viewId);
  if (!current) throw new Error("workbench view not found");
  const modal = await openActionModal({
    title: "Rename saved view",
    subtitle: current.name,
    description: "Update the label and notes while preserving the current layout and filters.",
    input: { value: current.name, placeholder: "view name" },
    textarea: { value: current.notes || "", placeholder: "notes / preset hint" },
    validate: (payload) => (payload.input ? "" : "View name is required."),
  });
  await updateWorkbenchView(viewId, { name: modal.input, notes: modal.textarea });
  showToast("Saved view updated.", "success", "Workbench view");
}
async function resolveSelectedCycle() {
  const cycleId = requireField(
    selectedCycleId || selectedCycleInput.value.trim(),
    "Select a cycle before resolving it.",
  );
  const summary = document.getElementById("resolve-summary").value.trim();
  const linkedDiscussionId = document.getElementById("resolve-linked-discussion-id").value.trim();
  const modal = await openActionModal({
    title: "Resolve / close cycle",
    subtitle: cycleId,
    description: "Record the resolution summary and optionally close a linked discussion thread.",
    input: { value: summary, placeholder: "resolution summary" },
    textarea: { value: "", placeholder: "follow-up / prevention note (optional)" },
    validate: (payload) => (payload.input ? "" : "Resolution summary is required."),
  });
  const body = `[resolved] ${modal.input}${modal.textarea ? `\nfollow_up: ${modal.textarea}` : ""}`;
  const response = await fetch(`/v1/cycles/${encodeURIComponent(cycleId)}/comments`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ body, mentions: [] }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error")
    throw new Error(payload?.error?.message || "Failed to resolve cycle");
  if (linkedDiscussionId) await setDiscussionResolved(linkedDiscussionId, true);
  document.getElementById("resolve-summary").value = modal.input;
  renderResolutionSummary({
    cycleId,
    summary: modal.input,
    actorId: activeAuthUserId(),
    linkedDiscussionId,
    resolvedAt: relativeTime(new Date().toISOString()),
  });
  await refreshComments(cycleId);
  await refreshIssueCard(cycleId);
  await refreshWorkspaceSurfaces();
  showToast("Cycle resolution recorded.", "success", "Resolution");
}
async function buildHandoffBundle() {
  const cycleId = requireField(
    selectedCycleId || selectedCycleInput.value.trim(),
    "Select a cycle before building a handoff bundle.",
  );
  const target = document.getElementById("handoff-target").value.trim();
  const mentions = document
    .getElementById("handoff-mentions")
    .value.split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const [card, result, comments] = await Promise.all([
    apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/card`),
    apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/result`).catch(() => null),
    apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/comments`).catch(() => ({ items: [] })),
  ]);
  const nextAction =
    buildNextStepActions({ ...card, detailed_result: result }, result)[0]?.label ||
    "Review cycle manually";
  const body = buildHandoffBody({
    projectId: card.cycle?.project_id,
    cycleId,
    target,
    state: card.cycle?.state,
    resultState: result?.final_state,
    summary: result?.summary || document.getElementById("resolve-summary").value.trim(),
    nextAction,
    assignment: card.current_assignment
      ? `${card.current_assignment.agent_id}:${card.current_assignment.assignment_role}`
      : null,
    lastComment: comments.items?.[0]?.body || null,
  });
  renderHandoffBundle({ cycleId, projectId: card.cycle?.project_id, target, mentions, body });
  showToast("Handoff bundle prepared.", "success", "Handoff");
}
async function postHandoffBundle() {
  if (!latestHandoffBundle) await buildHandoffBundle();
  if (!latestHandoffBundle) throw new Error("No handoff bundle available.");
  const response = await fetch("/v1/workspace/discussions", {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({
      project_id: latestHandoffBundle.projectId || null,
      body: latestHandoffBundle.body,
      mentions: latestHandoffBundle.mentions || [],
    }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error")
    throw new Error(payload?.error?.message || "Failed to post handoff note");
  await refreshWorkspaceSurfaces();
  showToast("Handoff note posted.", "success", "Handoff");
}
