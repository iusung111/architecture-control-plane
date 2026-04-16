function getSelectedCycleId() {
  return selectedCycleId || selectedCycleInput.value.trim();
}

function setSelectedCycle(cycleId) {
  selectedCycleId = cycleId;
  selectedCycleInput.value = cycleId;
}

async function refreshSelectedCyclePanels(cycleId) {
  await Promise.all([
    refreshTimeline(cycleId),
    refreshIssueCard(cycleId),
    refreshComments(cycleId),
    refreshAssignments(cycleId),
    refreshAssignmentSuggestions(cycleId),
  ]);
}

async function refreshWorkbenchContext() {
  await Promise.all([
    refreshBoard(),
    refreshWorkspaceSurfaces(),
    refreshPendingApprovals(),
    refreshRemoteWorkspaceSection(),
  ]);
}

async function selectCycle(cycleId) {
  setSelectedCycle(cycleId);
  await refreshSelectedCyclePanels(cycleId);
  await refreshWorkbenchContext();
  startCycleStream(cycleId);
}

async function refreshWorkbenchShell() {
  const cycleId = getSelectedCycleId();
  await Promise.all([
    refreshBoard(),
    refreshTimeline(cycleId),
    refreshIssueCard(cycleId),
    refreshRemoteWorkspaceSection(),
    refreshPendingApprovals(),
    refreshAuditExplorer(),
  ]);
}

async function connectWorkbench() {
  saveAuth();
  setAuthStatus(authValidationSummary());
  await Promise.all([
    refreshBoard(),
    refreshWorkspaceSurfaces(),
    refreshPendingApprovals(),
    refreshRemoteWorkspaceSection(),
    refreshAuditExplorer(),
  ]);
  startBoardStream();
  const cycleId = selectedCycleInput.value.trim();
  if (cycleId) await selectCycle(cycleId);
}

function initializeWorkbenchSurface() {
  loadAuth();
  setAuthStatus(authValidationSummary());
  refreshBoard();
  refreshWorkspaceSurfaces();
  refreshPendingApprovals();
  refreshRemoteWorkspaceSection();
  refreshAuditExplorer();
  renderRemoteWorkspaceExecutionDetail(null);
  renderPersistentWorkspaceSessions({ items: [] });
  refreshTimeline(null);
  setInlineStatus(createCycleStatusEl, "");
  setInlineStatus(issueActionStatusEl, "");
  refreshIssueCard(null);
  refreshComments(null);
  refreshAssignments(null);
  refreshAssignmentSuggestions(null);
  refreshDiscussionReplies(null);
  renderApprovalReviewContext(null);
  renderResolutionSummary(null);
  renderHandoffBundle(null);
  renderPersonalInbox();
  refreshRuntimeActions(null);
  refreshRuntimeActionTimeline(null, null);
  refreshRuntimeActionReceipts(null, null);
}
