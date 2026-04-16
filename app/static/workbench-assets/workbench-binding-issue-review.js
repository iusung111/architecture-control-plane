async function handleAssignmentSuggestionClick(event) {
  const useButton = event.target.closest(".use-assignment-suggestion-btn");
  if (useButton) {
    document.getElementById("assignment-agent-id").value = useButton.dataset.agentId || "";
    document.getElementById("assignment-role").value = useButton.dataset.role || "primary";
    document.getElementById("assignment-note").value = useButton.dataset.note || "";
    try {
      await sendAssignmentSuggestionFeedback(useButton.dataset.agentId || "", "accepted");
    } catch (error) {
      showToast(error.message, "error", "Workbench");
    }
    return;
  }

  const feedbackButton = event.target.closest(".assignment-feedback-btn");
  if (!feedbackButton) return;
  try {
    await sendAssignmentSuggestionFeedback(
      feedbackButton.dataset.agentId || "",
      feedbackButton.dataset.feedback || "accepted",
    );
  } catch (error) {
    showToast(error.message, "error", "Workbench");
  }
}

async function handlePendingApprovalClick(event) {
  const reviewButton = event.target.closest(".review-pending-approval-btn");
  if (reviewButton) {
    try {
      await reviewPendingApproval(
        reviewButton.dataset.cycleId || "",
        reviewButton.dataset.approvalId || "",
      );
    } catch (error) {
      showToast(error.message, "error", "Approval");
    }
    return;
  }

  const useButton = event.target.closest(".use-pending-approval-btn");
  if (useButton) {
    document.getElementById("issue-action-cycle-id").value = useButton.dataset.cycleId || "";
    document.getElementById("issue-action-approval-id").value = useButton.dataset.approvalId || "";
    setInlineStatus(
      issueActionStatusEl,
      `Loaded ${useButton.dataset.approvalId || ""} into issue actions.`,
    );
    return;
  }

  const openButton = event.target.closest(".open-pending-cycle-btn");
  if (openButton) {
    await selectCycle(openButton.dataset.cycleId || "");
    return;
  }

  const approveButton = event.target.closest(".quick-approve-btn");
  if (approveButton) {
    document.getElementById("issue-action-cycle-id").value = approveButton.dataset.cycleId || "";
    document.getElementById("issue-action-approval-id").value =
      approveButton.dataset.approvalId || "";
    selectedCycleId = approveButton.dataset.cycleId || selectedCycleId;
    try {
      await submitApprovalDecision("approved");
    } catch (error) {
      setInlineStatus(issueActionStatusEl, error.message);
    }
    return;
  }

  const rejectButton = event.target.closest(".quick-reject-btn");
  if (!rejectButton) return;
  document.getElementById("issue-action-cycle-id").value = rejectButton.dataset.cycleId || "";
  document.getElementById("issue-action-approval-id").value = rejectButton.dataset.approvalId || "";
  selectedCycleId = rejectButton.dataset.cycleId || selectedCycleId;
  try {
    await submitApprovalDecision("rejected");
  } catch (error) {
    setInlineStatus(issueActionStatusEl, error.message);
  }
}

async function handlePersonalInboxClick(event) {
  const openCycle = event.target.closest(".inbox-open-cycle-btn");
  if (openCycle) {
    await selectCycle(openCycle.dataset.cycleId || "");
    return;
  }

  const reviewApproval = event.target.closest(".inbox-review-approval-btn");
  if (reviewApproval) {
    try {
      await reviewPendingApproval(
        reviewApproval.dataset.cycleId || "",
        reviewApproval.dataset.approvalId || "",
      );
    } catch (error) {
      showToast(error.message, "error", "Approval");
    }
    return;
  }

  const openDiscussion = event.target.closest(".inbox-open-discussion-btn");
  if (!openDiscussion) return;
  selectedDiscussionId = openDiscussion.dataset.discussionId || null;
  document.getElementById("discussion-target").value = selectedDiscussionId || "";
  await refreshDiscussionReplies(selectedDiscussionId);
}

async function handleIssueCardClick(event) {
  const nextStep = event.target.closest(".next-step-btn");
  if (!nextStep) return;
  const action = nextStep.dataset.nextAction || "";
  if (action === "approve") {
    try {
      await submitApprovalDecision("approved");
    } catch (error) {
      setInlineStatus(issueActionStatusEl, error.message);
    }
    return;
  }

  if (action === "retry" || action === "replan") {
    try {
      await submitCycleAction(action);
    } catch (error) {
      setInlineStatus(issueActionStatusEl, error.message);
    }
    return;
  }

  if (action === "remote_checks") {
    try {
      await queueRemoteChecksForSelectedCycle();
    } catch (error) {
      setInlineStatus(issueActionStatusEl, error.message);
    }
    return;
  }

  if (action === "result") {
    showToast("Review the result artifacts shown in Issue card detail.", "info", "Result");
  }
}

async function handleApprovalReviewContextClick(event) {
  const openCycle = event.target.closest(".approval-review-open-cycle-btn");
  if (openCycle) {
    await selectCycle(openCycle.dataset.cycleId || "");
    return;
  }

  const approve = event.target.closest(".approval-review-approve-btn");
  if (approve) {
    document.getElementById("issue-action-cycle-id").value = approve.dataset.cycleId || "";
    document.getElementById("issue-action-approval-id").value = approve.dataset.approvalId || "";
    try {
      await submitApprovalDecision("approved");
    } catch (error) {
      setInlineStatus(issueActionStatusEl, error.message);
    }
    return;
  }

  const reject = event.target.closest(".approval-review-reject-btn");
  if (!reject) return;
  document.getElementById("issue-action-cycle-id").value = reject.dataset.cycleId || "";
  document.getElementById("issue-action-approval-id").value = reject.dataset.approvalId || "";
  try {
    await submitApprovalDecision("rejected");
  } catch (error) {
    setInlineStatus(issueActionStatusEl, error.message);
  }
}
