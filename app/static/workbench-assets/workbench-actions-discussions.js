async function postComment() {
  const cycleId = selectedCycleId || selectedCycleInput.value.trim();
  if (!cycleId) {
    showToast("Select a cycle before posting a comment.", "error", "Comments");
    return;
  }
  const body = document.getElementById("comment-body").value.trim();
  const mentions = document
    .getElementById("comment-mentions")
    .value.split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (!body) return;
  const response = await fetch(`/v1/cycles/${encodeURIComponent(cycleId)}/comments`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ body, mentions }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error") {
    throw new Error(payload?.error?.message || `Comment post failed (${response.status})`);
  }
  document.getElementById("comment-body").value = "";
  document.getElementById("comment-mentions").value = "";
  await refreshComments(cycleId);
  await refreshWorkspaceSurfaces();
  showToast("Comment posted.", "success", "Comments");
}
async function setDiscussionResolved(discussionId, resolved) {
  const response = await fetch(
    `/v1/workspace/discussions/${encodeURIComponent(discussionId)}/resolve`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ resolved }),
    },
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error")
    throw new Error(payload?.error?.message || `Discussion update failed (${response.status})`);
  await refreshWorkspaceSurfaces();
  if (selectedDiscussionId === discussionId) await refreshDiscussionReplies(discussionId);
}
async function setDiscussionPinned(discussionId, pinned) {
  const response = await fetch(
    `/v1/workspace/discussions/${encodeURIComponent(discussionId)}/pin`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ pinned }),
    },
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error")
    throw new Error(payload?.error?.message || `Discussion pin failed (${response.status})`);
  await refreshWorkspaceSurfaces();
}
async function sendAssignmentSuggestionFeedback(agentId, feedback) {
  const cycleId = selectedCycleId || selectedCycleInput.value.trim();
  if (!cycleId) {
    showToast("Select a cycle before sending assignment feedback.", "error", "Assignment");
    return;
  }
  let note = "";
  try {
    const modal = await openActionModal({
      title: "Assignment feedback",
      subtitle: feedback,
      description: "Add an optional note for the assignment suggestion feedback.",
      textarea: { value: "", placeholder: "Optional note" },
    });
    note = modal.textarea || "";
  } catch (error) {
    if (error.message === "cancelled") return;
    throw error;
  }
  const response = await fetch(
    `/v1/cycles/${encodeURIComponent(cycleId)}/assignment-suggestions/feedback`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: agentId, feedback, note: note || null }),
    },
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error")
    throw new Error(payload?.error?.message || `Suggestion feedback failed (${response.status})`);
  await refreshAssignmentSuggestions(cycleId);
  await refreshIssueCard(cycleId);
}
async function postDiscussionReply() {
  const discussionId =
    selectedDiscussionId || document.getElementById("discussion-target").value.trim();
  if (!discussionId) {
    showToast("Select a discussion before replying.", "error", "Discussion");
    return;
  }
  const body = document.getElementById("discussion-reply-body").value.trim();
  const mentions = document
    .getElementById("discussion-reply-mentions")
    .value.split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (!body) return;
  const response = await fetch(
    `/v1/workspace/discussions/${encodeURIComponent(discussionId)}/replies`,
    {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ body, mentions }),
    },
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error") {
    throw new Error(payload?.error?.message || `Discussion reply failed (${response.status})`);
  }
  document.getElementById("discussion-reply-body").value = "";
  document.getElementById("discussion-reply-mentions").value = "";
  await refreshDiscussionReplies(discussionId);
  await refreshWorkspaceSurfaces();
}
async function saveDiscussionFilter() {
  const payload = {
    name: `filter-${Date.now()}`,
    project_id: document.getElementById("project-filter").value.trim() || null,
    mention: document.getElementById("discussion-mention-filter").value.trim() || null,
    query: document.getElementById("discussion-search-filter").value.trim() || null,
  };
  const response = await fetch("/v1/workspace/discussion-filters", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message || "Failed to save discussion filter");
  }
  await refreshWorkspaceSurfaces();
}
async function updateDiscussionFilter(filterId, current) {
  let nextName = "";
  try {
    const modal = await openActionModal({
      title: "Rename saved filter",
      description: "Update the saved filter name.",
      input: { value: current.name || "", placeholder: "Saved filter name" },
      validate: (payload) => (payload.input ? "" : "Saved filter name is required."),
    });
    nextName = modal.input || "";
  } catch (error) {
    if (error.message === "cancelled") return;
    throw error;
  }
  const response = await fetch(`/v1/workspace/discussion-filters/${encodeURIComponent(filterId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      name: nextName.trim(),
      project_id: current.projectId || null,
      mention: current.mention || null,
      query: current.query || null,
    }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error")
    throw new Error(payload?.error?.message || "Failed to update discussion filter");
  await refreshWorkspaceSurfaces();
}
async function favoriteDiscussionFilter(filterId, isFavorite) {
  const response = await fetch(
    `/v1/workspace/discussion-filters/${encodeURIComponent(filterId)}/favorite`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ is_favorite: isFavorite }),
    },
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error")
    throw new Error(payload?.error?.message || "Failed to favorite discussion filter");
  await refreshWorkspaceSurfaces();
}
async function deleteDiscussionFilter(filterId) {
  const response = await fetch(`/v1/workspace/discussion-filters/${encodeURIComponent(filterId)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error")
    throw new Error(payload?.error?.message || "Failed to delete discussion filter");
  await refreshWorkspaceSurfaces();
}
async function markDiscussionFilterUsed(filterId) {
  const response = await fetch(
    `/v1/workspace/discussion-filters/${encodeURIComponent(filterId)}/use`,
    {
      method: "POST",
      headers: authHeaders(),
    },
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error")
    throw new Error(payload?.error?.message || "Failed to mark discussion filter as used");
}
async function postDiscussion() {
  const projectId = document.getElementById("project-filter").value.trim();
  const body = document.getElementById("discussion-body").value.trim();
  const mentions = document
    .getElementById("discussion-mentions")
    .value.split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (!body) return;
  const response = await fetch("/v1/workspace/discussions", {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId || null, body, mentions }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error") {
    throw new Error(payload?.error?.message || `Discussion post failed (${response.status})`);
  }
  document.getElementById("discussion-body").value = "";
  document.getElementById("discussion-mentions").value = "";
  await refreshWorkspaceSurfaces();
  showToast("Discussion posted.", "success", "Discussion");
}
async function assignAgentToCycle() {
  const cycleId = selectedCycleId || selectedCycleInput.value.trim();
  if (!cycleId) {
    showToast("Select a cycle before assigning an agent.", "error", "Assignment");
    return;
  }
  const agentId = document.getElementById("assignment-agent-id").value.trim();
  const assignmentRole = document.getElementById("assignment-role").value.trim() || "primary";
  const note = document.getElementById("assignment-note").value.trim();
  if (!agentId) {
    showToast("agent id is required.", "error", "Assignment");
    return;
  }
  const response = await fetch(`/v1/cycles/${encodeURIComponent(cycleId)}/assignments`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: agentId,
      assignment_role: assignmentRole,
      note: note || null,
    }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.status === "error") {
    throw new Error(payload?.error?.message || `Assignment failed (${response.status})`);
  }
  document.getElementById("assignment-note").value = "";
  await refreshAssignments(cycleId);
  await refreshAssignmentSuggestions(cycleId);
  await refreshIssueCard(cycleId);
}
