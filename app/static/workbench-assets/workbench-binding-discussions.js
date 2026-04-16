function bindDiscussionAndReviewEvents() {
  savedDiscussionFiltersEl.addEventListener("click", handleSavedDiscussionFilterClick);
  workspaceDiscussionsEl.addEventListener("click", handleWorkspaceDiscussionClick);
  assignmentSuggestionsEl.addEventListener("click", handleAssignmentSuggestionClick);
  pendingApprovalsEl.addEventListener("click", handlePendingApprovalClick);
  personalInboxEl.addEventListener("click", handlePersonalInboxClick);
  issueCardEl.addEventListener("click", handleIssueCardClick);
  approvalReviewContextEl.addEventListener("click", handleApprovalReviewContextClick);
  document.getElementById("discussion-mention-filter").addEventListener("change", () => {
    refreshWorkspaceSurfaces();
  });
  document.getElementById("discussion-search-filter").addEventListener("change", () => {
    refreshWorkspaceSurfaces();
  });
  document
    .getElementById("save-discussion-filter")
    .addEventListener("click", wrapToastAction(saveDiscussionFilter));
  document
    .getElementById("post-discussion")
    .addEventListener("click", wrapToastAction(postDiscussion));
  document
    .getElementById("post-discussion-reply")
    .addEventListener("click", wrapToastAction(postDiscussionReply));
  document.getElementById("post-comment").addEventListener("click", wrapToastAction(postComment));
  document
    .getElementById("assign-agent")
    .addEventListener("click", wrapToastAction(assignAgentToCycle));
  document.getElementById("discussion-reply-mention-filter").addEventListener("change", () => {
    if (selectedDiscussionId) refreshDiscussionReplies(selectedDiscussionId);
  });
}
