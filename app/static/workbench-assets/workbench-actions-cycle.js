async function createCycleFromWorkbench(connectAfterCreate = false) {
  const projectId = document.getElementById("create-cycle-project-id").value.trim();
  const userInput = document.getElementById("create-cycle-user-input").value.trim();
  if (!projectId || !userInput) {
    setInlineStatus(createCycleStatusEl, "project id and task description are required.");
    return;
  }
  const response = await fetch("/v1/cycles", {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
      "Idempotency-Key": makeIdempotencyKey("workbench-create"),
    },
    body: JSON.stringify({ project_id: projectId, user_input: userInput }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || `Cycle create failed (${response.status})`);
  const cycleId = body?.data?.cycle_id;
  document.getElementById("create-cycle-user-input").value = "";
  setInlineStatus(createCycleStatusEl, `Created cycle ${cycleId}.`);
  if (!document.getElementById("project-filter").value.trim())
    document.getElementById("project-filter").value = projectId;
  await refreshBoard();
  await refreshWorkspaceSurfaces();
  await refreshPendingApprovals();
  if (connectAfterCreate && cycleId) {
    await selectCycle(cycleId);
    return;
  }
  if (cycleId) {
    selectedCycleId = cycleId;
    selectedCycleInput.value = cycleId;
    await refreshIssueCard(cycleId);
  }
}
async function submitApprovalDecision(decision) {
  const cycleId =
    selectedCycleId ||
    document.getElementById("issue-action-cycle-id").value.trim() ||
    selectedCycleInput.value.trim();
  const approvalId = document.getElementById("issue-action-approval-id").value.trim();
  let reason = document.getElementById("issue-action-reason").value.trim();
  if (!cycleId) {
    setInlineStatus(issueActionStatusEl, "Select a cycle first.");
    return;
  }
  if (!approvalId) {
    setInlineStatus(issueActionStatusEl, "No active approval is attached to the selected cycle.");
    return;
  }
  let reasonCode = null;
  if (decision === "rejected" && !reason) {
    try {
      const modal = await openActionModal({
        title: "Reject approval",
        description: "Choose a reason code and provide a rejection note.",
        select: {
          value: "needs_more_information",
          options: [
            { value: "verification_failed", label: "verification_failed" },
            { value: "needs_more_information", label: "needs_more_information" },
            { value: "incorrect_approach", label: "incorrect_approach" },
            { value: "replan_required", label: "replan_required" },
            { value: "policy_block", label: "policy_block" },
          ],
        },
        textarea: { value: "", placeholder: "Rejection note" },
        validate: (payload) => (payload.textarea ? "" : "Rejection note is required."),
      });
      reason = modal.textarea;
      reasonCode = modal.select;
      document.getElementById("issue-action-reason").value = reason;
    } catch (error) {
      if (error.message === "cancelled") return;
      throw error;
    }
  }
  const payload = {
    decision,
    comment: reason || null,
    reason_code: decision === "rejected" ? reasonCode || "rejected-from-workbench" : null,
  };
  const response = await fetch(`/v1/approvals/${encodeURIComponent(approvalId)}/confirm`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
      "Idempotency-Key": makeIdempotencyKey(`approval-${decision}`),
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || `Approval ${decision} failed (${response.status})`);
  setInlineStatus(issueActionStatusEl, `${decision} accepted for ${approvalId}.`);
  await refreshBoard();
  await refreshTimeline(cycleId);
  await refreshIssueCard(cycleId);
  await refreshWorkspaceSurfaces();
  await refreshPendingApprovals();
}
async function submitCycleAction(action) {
  const cycleId =
    selectedCycleId ||
    document.getElementById("issue-action-cycle-id").value.trim() ||
    selectedCycleInput.value.trim();
  if (!cycleId) {
    setInlineStatus(issueActionStatusEl, "Select a cycle first.");
    return;
  }
  let reason = document.getElementById("issue-action-reason").value.trim();
  const overrideRaw = document.getElementById("issue-action-override-input").value.trim();
  let overrideInput = {};
  if (action === "replan") {
    const structuredOverride = buildReplanOverride();
    if (overrideRaw) {
      try {
        overrideInput = JSON.parse(overrideRaw);
      } catch (error) {
        setInlineStatus(issueActionStatusEl, "override_input must be valid JSON.");
        return;
      }
    }
    overrideInput = { ...overrideInput, ...structuredOverride };
  }
  const payload =
    action === "replan"
      ? { reason: reason || "replan requested from workbench", override_input: overrideInput }
      : { reason: reason || `${action} requested from workbench` };
  const response = await fetch(`/v1/cycles/${encodeURIComponent(cycleId)}/${action}`, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
      "Idempotency-Key": makeIdempotencyKey(`cycle-${action}`),
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.status === "error")
    throw new Error(body?.error?.message || `${action} failed (${response.status})`);
  setInlineStatus(issueActionStatusEl, `${action} accepted for ${cycleId}.`);
  await refreshBoard();
  await refreshTimeline(cycleId);
  await refreshIssueCard(cycleId);
  await refreshWorkspaceSurfaces();
  await refreshPendingApprovals();
}
async function queueRemoteChecksForSelectedCycle() {
  const cycleId =
    selectedCycleId ||
    document.getElementById("issue-action-cycle-id").value.trim() ||
    selectedCycleInput.value.trim();
  if (!cycleId) {
    setInlineStatus(issueActionStatusEl, "Select a cycle first.");
    return;
  }
  if (!document.getElementById("remote-workspace-id").value.trim())
    document.getElementById("remote-workspace-id").value = `cycle:${cycleId}`;
  await requestRemoteWorkspaceExecution("run_checks");
  setInlineStatus(issueActionStatusEl, `Remote checks queued for ${cycleId}.`);
}
