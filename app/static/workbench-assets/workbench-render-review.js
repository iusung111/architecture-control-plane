function inboxActionButton(className, attrs, label) {
  return `<button class="secondary ${className}" ${attrs}>${label}</button>`;
}

function renderPendingApprovals(data) {
  latestPendingApprovalData = data || { items: [] };
  pendingApprovalsEl.innerHTML = data.items.length
    ? data.items
        .map((item) => {
          const reviewButton = inboxActionButton(
            "review-pending-approval-btn",
            `data-cycle-id="${item.cycle_id}" data-approval-id="${item.approval_id}"`,
            "Review context",
          );
          const useButton = inboxActionButton(
            "use-pending-approval-btn",
            `data-cycle-id="${item.cycle_id}" data-approval-id="${item.approval_id}"`,
            "Use in issue actions",
          );
          const openButton = inboxActionButton(
            "open-pending-cycle-btn",
            `data-cycle-id="${item.cycle_id}"`,
            "Open cycle",
          );
          const approveButton = inboxActionButton(
            "quick-approve-btn",
            `data-cycle-id="${item.cycle_id}" data-approval-id="${item.approval_id}"`,
            "Approve",
          );
          const rejectButton = inboxActionButton(
            "quick-reject-btn",
            `data-cycle-id="${item.cycle_id}" data-approval-id="${item.approval_id}"`,
            "Reject",
          );
          return `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.project_id}</strong>
                <span>${item.cycle_id}</span>
                <span>expires ${relativeTime(item.expires_at)}</span>
              </div>
              <div class="muted" style="margin-top:8px">
                approval=${item.approval_id} · role=${item.required_role}
                · state=${item.cycle_state}
              </div>
              <div class="inline-actions" style="margin-top:10px">
                ${reviewButton}
                ${useButton}
                ${openButton}
                ${approveButton}
                ${rejectButton}
              </div>
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No pending approvals for the current user.</div>';
  renderPersonalInbox();
}

function smartFilterPredicate(filterKey, item) {
  if (!item) return false;
  if (filterKey === "pending_approval") {
    return item.type === "approval" || item.approval_required;
  }
  if (filterKey === "retry_ready") return item.retry_allowed === true;
  if (filterKey === "stale") {
    const updated = new Date(
      item.updated_at || item.last_updated_at || item.occurred_at || 0,
    ).getTime();
    return updated && Date.now() - updated > 24 * 60 * 60 * 1000;
  }
  if (filterKey === "mentions") return item.type === "discussion";
  return true;
}

function buildInboxDetail(item) {
  if (item.detail) return item.detail;
  const cycleLabel = `cycle=${item.cycle_id || "n/a"}`;
  const userLabel = item.user_status ? ` · user=${item.user_status}` : "";
  const stateLabel = item.state ? ` · state=${item.state}` : "";
  return `${cycleLabel}${userLabel}${stateLabel}`;
}

function renderPersonalInbox() {
  const boardItems = (latestBoardData?.columns || []).flatMap((column) =>
    (column.items || []).map((item) => ({ ...item, type: "cycle" })),
  );
  const approvalItems = (latestPendingApprovalData?.items || []).map((item) => ({
    type: "approval",
    cycle_id: item.cycle_id,
    approval_id: item.approval_id,
    project_id: item.project_id,
    updated_at: item.expires_at,
    approval_required: true,
    title: `Approval needed · ${item.project_id}`,
    detail: `${item.required_role} · expires ${relativeTime(item.expires_at)}`,
  }));
  const mentionItems = (latestDiscussionData?.items || [])
    .filter((item) => (item.mentions || []).length > 0)
    .map((item) => ({
      type: "discussion",
      discussion_id: item.discussion_id,
      project_id: item.project_id || "workspace",
      updated_at: item.last_updated_at || item.occurred_at,
      title: `Mention thread · ${item.project_id || "workspace"}`,
      detail: item.body,
    }));
  const dedup = new Map();
  [...approvalItems, ...boardItems, ...mentionItems].forEach((item) => {
    const dedupId = item.approval_id || item.cycle_id || item.discussion_id || item.project_id;
    const key = `${item.type}:${dedupId}`;
    if (!dedup.has(key)) dedup.set(key, item);
  });
  const items = [...dedup.values()]
    .filter((item) => smartFilterPredicate(activeSmartFilter, item))
    .slice(0, 12);
  personalInboxCountEl.textContent = `${items.length} items`;
  personalInboxEl.innerHTML = items.length
    ? items
        .map((item) => {
          const openCycleButton = item.cycle_id
            ? inboxActionButton(
                "inbox-open-cycle-btn",
                `data-cycle-id="${item.cycle_id}"`,
                "Open cycle",
              )
            : "";
          const reviewButton = item.approval_id
            ? inboxActionButton(
                "inbox-review-approval-btn",
                `data-cycle-id="${item.cycle_id}" data-approval-id="${item.approval_id}"`,
                "Review approval",
              )
            : "";
          const openThreadButton = item.discussion_id
            ? inboxActionButton(
                "inbox-open-discussion-btn",
                `data-discussion-id="${item.discussion_id}"`,
                "Open thread",
              )
            : "";
          const title = item.title || item.project_id || item.cycle_id || "item";
          const updatedAt = item.updated_at || new Date().toISOString();
          return `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${title}</strong>
                <span>${item.type}</span>
                <span>${relativeTime(updatedAt)}</span>
              </div>
              <div class="muted" style="margin-top:8px">
                ${buildInboxDetail(item)}
              </div>
              <div class="inline-actions" style="margin-top:10px">
                ${openCycleButton}
                ${reviewButton}
                ${openThreadButton}
              </div>
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No inbox items for the current smart filter.</div>';
}

function renderApprovalEvent(event) {
  const detail = event.detail ? `<div style="margin-top:8px">${event.detail}</div>` : "";
  return `
    <article class="timeline-item">
      <div class="event-meta">
        <strong>${event.title}</strong>
        <span>${event.status || event.source}</span>
        <span>${relativeTime(event.occurred_at)}</span>
      </div>
      ${detail}
    </article>
  `;
}

function renderApprovalComment(comment) {
  return `
    <article class="timeline-item">
      <div class="event-meta">
        <strong>${comment.actor_id || "unknown"}</strong>
        <span>${comment.actor_role || ""}</span>
        <span>${relativeTime(comment.occurred_at)}</span>
      </div>
      <div style="margin-top:8px">${comment.body}</div>
    </article>
  `;
}

function renderApprovalReviewContext(data) {
  if (!data) {
    approvalReviewContextEl.innerHTML =
      '<div class="empty">Select a pending approval to review timeline, result, comments, and assignment context.</div>';
    return;
  }
  const timelineItems = (data.timeline?.events || []).slice(0, 4);
  const timeline = timelineItems.length
    ? timelineItems.map(renderApprovalEvent).join("")
    : '<div class="empty">No timeline entries.</div>';
  const commentItems = (data.comments?.items || []).slice(0, 3);
  const comments = commentItems.length
    ? commentItems.map(renderApprovalComment).join("")
    : '<div class="empty">No comments yet.</div>';
  const result = data.result
    ? `
      <article class="timeline-item">
        <div class="event-meta">
          <strong>Latest result</strong>
          <span>${data.result.final_state || "n/a"}</span>
          <span>
            ${relativeTime(data.result.generated_at || data.card?.cycle?.updated_at)}
          </span>
        </div>
        <div style="margin-top:8px">${data.result.summary || "No summary yet."}</div>
        <div class="muted" style="margin-top:8px">
          verification=${data.result.verification?.status || "n/a"}
          ${
            (data.result.verification?.failed_rules || []).length
              ? ` · failed=${data.result.verification.failed_rules.join(", ")}`
              : ""
          }
        </div>
      </article>
    `
    : '<div class="empty">No result recorded yet.</div>';
  const assignment = data.card?.current_assignment
    ? `
      <article class="timeline-item">
        <div class="event-meta">
          <strong>Current assignment</strong>
          <span>${data.card.current_assignment.agent_id}</span>
          <span>${data.card.current_assignment.assignment_role}</span>
        </div>
        <div style="margin-top:8px">
          ${data.card.current_assignment.note || "No assignment note."}
        </div>
      </article>
    `
    : '<div class="empty">No active assignment.</div>';
  approvalReviewContextEl.innerHTML = `
    <article class="timeline-item">
      <div class="event-meta">
        <strong>${data.card?.cycle?.project_id || "approval review"}</strong>
        <span>${data.approvalId || "n/a"}</span>
        <span>${data.card?.active_approval?.state || "pending"}</span>
      </div>
      <div class="muted" style="margin-top:8px">
        cycle=${data.cycleId} · comments=${data.card?.comment_count || 0}
        · jobs=${data.card?.active_job_count || 0}
      </div>
      <div class="inline-actions" style="margin-top:10px">
        ${inboxActionButton(
          "approval-review-open-cycle-btn",
          `data-cycle-id="${data.cycleId}"`,
          "Open cycle",
        )}
        ${inboxActionButton(
          "approval-review-approve-btn",
          `data-cycle-id="${data.cycleId}" data-approval-id="${data.approvalId}"`,
          "Approve",
        )}
        ${inboxActionButton(
          "approval-review-reject-btn",
          `data-cycle-id="${data.cycleId}" data-approval-id="${data.approvalId}"`,
          "Reject",
        )}
      </div>
    </article>
    ${result}
    ${assignment}
    <article class="timeline-item">
      <div class="event-meta">
        <strong>Recent timeline</strong>
        <span>${(data.timeline?.events || []).length} events</span>
      </div>
      <div class="timeline" style="max-height:none;margin-top:10px">
        ${timeline}
      </div>
    </article>
    <article class="timeline-item">
      <div class="event-meta">
        <strong>Recent comments</strong>
        <span>${(data.comments?.items || []).length} items</span>
      </div>
      <div class="timeline" style="max-height:none;margin-top:10px">
        ${comments}
      </div>
    </article>
  `;
}
