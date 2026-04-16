async function reviewPendingApproval(cycleId, approvalId) {
  selectedApprovalReviewId = approvalId;
  document.getElementById("issue-action-cycle-id").value = cycleId || "";
  document.getElementById("issue-action-approval-id").value = approvalId || "";
  const [card, result, comments, timeline] = await Promise.all([
    apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/card`),
    apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/result`).catch(() => null),
    apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/comments`).catch(() => ({ items: [] })),
    apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/timeline`).catch(() => ({ events: [] })),
  ]);
  renderApprovalReviewContext({ cycleId, approvalId, card, result, comments, timeline });
  showToast(`Loaded approval ${approvalId} review context.`, "success", "Approval");
}
async function refreshPendingApprovals() {
  try {
    const projectId = document.getElementById("project-filter").value.trim();
    const data = await apiJson(`/v1/approvals/pending${qs({ project_id: projectId, limit: 12 })}`);
    renderPendingApprovals(data);
  } catch (error) {
    pendingApprovalsEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
function renderTimeline(data) {
  timelineEl.innerHTML = data.events.length
    ? data.events
        .map(
          (event) => `
        <article class="timeline-item">
          <div class="event-meta">
            <strong>${event.title}</strong>
            <span>${event.source}</span>
            ${event.status ? `<span>${event.status}</span>` : ""}
            <span>${relativeTime(event.occurred_at)}</span>
          </div>
          ${event.detail ? `<div style="margin-top:8px">${event.detail}</div>` : ""}
          <div class="muted" style="margin-top:8px">${event.event_type}${event.actor_id ? ` · actor=${event.actor_id}` : ""}</div>
        </article>
      `,
        )
        .join("")
    : '<div class="empty">No timeline entries yet.</div>';
}
async function refreshWorkspaceSurfaces() {
  try {
    const projectId = document.getElementById("project-filter").value.trim();
    const discussionMention = document.getElementById("discussion-mention-filter").value.trim();
    const discussionQuery = document.getElementById("discussion-search-filter").value.trim();
    const [workspace, agents, runtime, discussions, discussionGroups, savedFilters, registrations] =
      await Promise.all([
        apiJson(`/v1/workspace/overview${qs({ project_id: projectId })}`),
        apiJson(`/v1/agents/profiles${qs({ project_id: projectId })}`),
        apiJson(`/v1/runtime/panel${qs({ project_id: projectId })}`),
        apiJson(
          `/v1/workspace/discussions${qs({ project_id: projectId, mention: discussionMention, query: discussionQuery })}`,
        ),
        apiJson(
          `/v1/workspace/discussions/groups${qs({ project_id: projectId, mention: discussionMention, query: discussionQuery })}`,
        ),
        apiJson(`/v1/workspace/discussion-filters`),
        apiJson(`/v1/runtime/registrations${qs({ project_id: projectId })}`),
      ]);
    renderWorkspace(workspace);
    renderAgentRoster(agents);
    renderRuntimePanel(runtime);
    renderWorkspaceDiscussionGroups(discussionGroups);
    renderSavedDiscussionFilters(savedFilters);
    renderWorkspaceDiscussions(discussions);
    renderRuntimeRegistrations(registrations);
  } catch (error) {
    workspaceEl.innerHTML = `<div class="empty">${error.message}</div>`;
    agentRosterEl.innerHTML = `<div class="empty">${error.message}</div>`;
    runtimePanelEl.innerHTML = `<div class="empty">${error.message}</div>`;
    workspaceDiscussionGroupsEl.innerHTML = `<div class="empty">${error.message}</div>`;
    savedDiscussionFiltersEl.innerHTML = `<div class="empty">${error.message}</div>`;
    workspaceDiscussionsEl.innerHTML = `<div class="empty">${error.message}</div>`;
    runtimeRegistrationsEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
async function refreshDiscussionReplies(discussionId) {
  if (!discussionId) {
    discussionRepliesEl.innerHTML = '<div class="empty">Select a discussion to view replies.</div>';
    return;
  }
  try {
    const mention = document.getElementById("discussion-reply-mention-filter").value.trim();
    const data = await apiJson(
      `/v1/workspace/discussions/${encodeURIComponent(discussionId)}/replies${qs({ mention })}`,
    );
    renderDiscussionReplies(data);
  } catch (error) {
    discussionRepliesEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
async function refreshComments(cycleId) {
  if (!cycleId) {
    commentsListEl.innerHTML = '<div class="empty">Select a cycle to view comments.</div>';
    return;
  }
  try {
    const data = await apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/comments`);
    renderComments(data);
  } catch (error) {
    commentsListEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
async function refreshBoard() {
  try {
    const projectId = document.getElementById("project-filter").value.trim();
    const limit = document.getElementById("board-limit").value || "12";
    projectStateEl.textContent = projectId || "all";
    const board = await apiJson(
      `/v1/cycles/board${qs({ project_id: projectId, limit_per_column: limit })}`,
    );
    renderBoard(board);
  } catch (error) {
    boardColumnsEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
async function refreshIssueCard(cycleId) {
  if (!cycleId) {
    document.getElementById("issue-action-cycle-id").value = "";
    document.getElementById("issue-action-approval-id").value = "";
    issueCardEl.innerHTML = '<div class="empty">Select a cycle to view card details.</div>';
    return;
  }
  try {
    const [card, detailedResult] = await Promise.all([
      apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/card`),
      apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/result`).catch(() => null),
    ]);
    renderIssueCard({ ...card, detailed_result: detailedResult });
  } catch (error) {
    issueCardEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
async function refreshAssignmentSuggestions(cycleId) {
  if (!cycleId) {
    assignmentSuggestionsEl.innerHTML =
      '<div class="empty">Select a cycle to view assignment suggestions.</div>';
    assignmentLearningWeightsEl.innerHTML =
      '<div class="empty">Select a cycle to view learning weights.</div>';
    return;
  }
  try {
    const [data, weights] = await Promise.all([
      apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/assignment-suggestions`),
      apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/assignment-learning-weights`),
    ]);
    renderAssignmentSuggestions(data);
    renderAssignmentLearningWeights(weights);
  } catch (error) {
    assignmentSuggestionsEl.innerHTML = `<div class="empty">${error.message}</div>`;
    assignmentLearningWeightsEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
async function refreshAssignments(cycleId) {
  if (!cycleId) {
    cycleAssignmentsEl.innerHTML = '<div class="empty">Select a cycle to view assignments.</div>';
    return;
  }
  try {
    const data = await apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/assignments`);
    renderAssignments(data);
  } catch (error) {
    cycleAssignmentsEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
async function refreshTimeline(cycleId) {
  if (!cycleId) {
    timelineEl.innerHTML = '<div class="empty">Select a cycle from the board.</div>';
    return;
  }
  try {
    const data = await apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/timeline`);
    renderTimeline(data);
  } catch (error) {
    timelineEl.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}
