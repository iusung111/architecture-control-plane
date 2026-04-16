function activeAuthUserId() {
  return document.getElementById("auth-user-id").value.trim() || "current-user";
}
function currentWorkbenchSnapshot() {
  return {
    project_id: document.getElementById("project-filter").value.trim() || null,
    cycle_id: selectedCycleId || selectedCycleInput.value.trim() || null,
    workspace_id: document.getElementById("remote-workspace-id").value.trim() || null,
    query: document.getElementById("discussion-search-filter").value.trim() || null,
    smart_filter: activeSmartFilter,
  };
}
function isWorkbenchViewChanged(item) {
  const snap = currentWorkbenchSnapshot();
  return (
    (item.project_id || "") !== (snap.project_id || "") ||
    (item.cycle_id || "") !== (snap.cycle_id || "") ||
    (item.workspace_id || "") !== (snap.workspace_id || "") ||
    (item.query || "") !== (snap.query || "") ||
    ((item.layout || {}).smart_filter || "all") !== (snap.smart_filter || "all")
  );
}
function findDefaultWorkbenchView() {
  const items = latestWorkbenchViews?.items || [];
  return items.find((item) => item?.layout?.is_default) || null;
}
function renderResolutionSummary(data) {
  if (!data) {
    resolutionSummaryEl.innerHTML =
      '<div class="empty">Resolve a cycle to record a close summary and optional linked discussion resolution.</div>';
    return;
  }
  resolutionSummaryEl.innerHTML = `
        <article class="timeline-item">
          <div class="event-meta"><strong>Resolved cycle</strong><span>${data.cycleId}</span><span>${data.resolvedAt}</span></div>
          <div style="margin-top:8px">${escapeHtml(data.summary)}</div>
          <div class="muted" style="margin-top:8px">actor=${escapeHtml(data.actorId)}${data.linkedDiscussionId ? ` · discussion=${escapeHtml(data.linkedDiscussionId)}` : ""}</div>
        </article>
      `;
}
function renderHandoffBundle(data) {
  latestHandoffBundle = data || null;
  if (!data) {
    handoffBundleEl.innerHTML =
      '<div class="empty">Build a handoff bundle to package status, result, next action, and recent context.</div>';
    return;
  }
  handoffBundleEl.innerHTML = `
        <article class="timeline-item">
          <div class="event-meta"><strong>Handoff bundle</strong><span>${escapeHtml(data.projectId || "workspace")}</span><span>${escapeHtml(data.cycleId || "n/a")}</span></div>
          <div style="white-space:pre-wrap;margin-top:8px">${escapeHtml(data.body)}</div>
          <div class="muted" style="margin-top:8px">mentions=${(data.mentions || []).join(", ") || "none"}${data.target ? ` · target=${escapeHtml(data.target)}` : ""}</div>
        </article>
      `;
}
function buildHandoffBody(payload) {
  const lines = [
    `[handoff] ${payload.projectId || "workspace"} · cycle ${payload.cycleId || "n/a"}`,
    payload.target ? `target: ${payload.target}` : null,
    `state: ${payload.state || "n/a"}`,
    payload.resultState ? `latest_result: ${payload.resultState}` : null,
    payload.summary ? `summary: ${payload.summary}` : null,
    payload.nextAction ? `next_action: ${payload.nextAction}` : null,
    payload.assignment ? `assignment: ${payload.assignment}` : null,
    payload.lastComment ? `last_comment: ${payload.lastComment}` : null,
  ].filter(Boolean);
  return lines.join("\n");
}
function buildNextStepActions(data, detailedResult) {
  const steps = [];
  const cycle = data?.cycle || {};
  if (data?.active_approval?.approval_id || cycle.approval_required) {
    steps.push({
      label: "Approve pending review",
      detail: "Human approval is still blocking progress.",
      action: "approve",
    });
  }
  if (cycle.retry_allowed) {
    steps.push({
      label: "Retry current cycle",
      detail: "Verification failed or action is required.",
      action: "retry",
    });
  }
  if (cycle.replan_allowed) {
    steps.push({
      label: "Adjust plan",
      detail: "A replan is available for prompt/scope changes.",
      action: "replan",
    });
  }
  if ((detailedResult?.verification?.failed_rules || []).length || cycle.retry_allowed) {
    steps.push({
      label: "Queue remote checks",
      detail: "Collect stronger evidence from the remote workspace.",
      action: "remote_checks",
    });
  }
  if (detailedResult?.output_artifacts?.length) {
    steps.push({
      label: "Review result artifacts",
      detail: "Artifacts are available from the latest result.",
      action: "result",
    });
  }
  return steps.slice(0, 4);
}
function buildReplanOverride() {
  const override = {};
  const prompt = document.getElementById("replan-prompt").value.trim();
  const scope = document.getElementById("replan-scope").value.trim();
  const safety = document.getElementById("replan-safety").value.trim();
  const priority = document.getElementById("replan-priority").value.trim();
  const constraints = document.getElementById("replan-constraints").value.trim();
  if (prompt) override.prompt = prompt;
  if (scope) override.scope = scope;
  if (safety) override.safety_mode = safety;
  if (priority) override.priority = priority;
  if (constraints)
    override.constraints = constraints
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
  return override;
}
