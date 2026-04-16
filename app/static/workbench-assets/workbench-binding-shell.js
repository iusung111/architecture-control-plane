function bindWorkbenchShellEvents() {
  document.getElementById("save-auth").addEventListener("click", saveAuth);
  document.getElementById("clear-auth").addEventListener("click", clearAuth);
  document
    .getElementById("auth-preset-operator")
    .addEventListener("click", () => applyAuthPreset("operator"));
  document
    .getElementById("auth-preset-reviewer")
    .addEventListener("click", () => applyAuthPreset("reviewer"));
  document
    .getElementById("auth-preset-audit")
    .addEventListener("click", () => applyAuthPreset("audit"));
  document
    .getElementById("validate-auth")
    .addEventListener("click", () => setAuthStatus(authValidationSummary()));
  document
    .getElementById("refresh-btn")
    .addEventListener("click", wrapToastAction(refreshWorkbenchShell));
  document.getElementById("stop-btn").addEventListener("click", stopStreams);
  document.getElementById("create-cycle-btn").addEventListener(
    "click",
    wrapInlineAction(() => createCycleFromWorkbench(false), createCycleStatusEl),
  );
  document.getElementById("create-cycle-and-run-btn").addEventListener(
    "click",
    wrapInlineAction(() => createCycleFromWorkbench(true), createCycleStatusEl),
  );
  document.getElementById("issue-approve-btn").addEventListener(
    "click",
    wrapInlineAction(() => submitApprovalDecision("approved"), issueActionStatusEl),
  );
  document.getElementById("issue-reject-btn").addEventListener(
    "click",
    wrapInlineAction(() => submitApprovalDecision("rejected"), issueActionStatusEl),
  );
  document.getElementById("issue-retry-btn").addEventListener(
    "click",
    wrapInlineAction(() => submitCycleAction("retry"), issueActionStatusEl),
  );
  document.getElementById("issue-replan-btn").addEventListener(
    "click",
    wrapInlineAction(() => submitCycleAction("replan"), issueActionStatusEl),
  );
  document
    .getElementById("issue-remote-check-btn")
    .addEventListener(
      "click",
      wrapInlineAction(queueRemoteChecksForSelectedCycle, issueActionStatusEl),
    );
  document
    .getElementById("refresh-pending-approvals")
    .addEventListener("click", wrapToastAction(refreshPendingApprovals));
  document
    .getElementById("connect-btn")
    .addEventListener("click", wrapToastAction(connectWorkbench));
  document.getElementById("smart-filters").addEventListener("click", (event) => {
    const button = event.target.closest("[data-smart-filter]");
    if (!button) return;
    activeSmartFilter = button.dataset.smartFilter || "all";
    document.querySelectorAll("#smart-filters [data-smart-filter]").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    renderPersonalInbox();
  });
  selectedCycleInput.addEventListener("change", () => {
    const cycleId = selectedCycleInput.value.trim();
    if (cycleId) selectCycle(cycleId);
  });
}
