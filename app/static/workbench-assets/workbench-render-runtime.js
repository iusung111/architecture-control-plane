function renderDiscussionReplies(data) {
  const replyMentionInfo = data.mention_filter
    ? `<div class="empty">Filter: ${data.mention_filter}</div>`
    : "";
  const items = data.items.length
    ? data.items
        .map((item) => {
          const mentionMeta = item.mentions.length
            ? `
              <div class="muted" style="margin-top:8px">
                mentions=${item.mentions.join(", ")}
              </div>
            `
            : "";
          const rankMeta =
            (item.search_rank || 0) > 0
              ? `
              <div class="muted" style="margin-top:8px">
                rank=${item.search_rank}
                · matched=${(item.matched_terms || []).join(", ")}
              </div>
            `
              : "";
          return `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.actor_id || "unknown"}</strong>
                <span>${item.actor_role || ""}</span>
                <span>${relativeTime(item.occurred_at)}</span>
              </div>
              <div style="margin-top:8px">${item.body}</div>
              ${mentionMeta}
              ${rankMeta}
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No replies yet.</div>';
  discussionRepliesEl.innerHTML = replyMentionInfo + items;
}

function renderRuntimeRegistrations(data) {
  runtimeRegistrationsEl.innerHTML = data.items.length
    ? data.items
        .map(
          (item) => `
            <article class="runtime-item">
              <strong>${item.label}</strong>
              <div>${item.runtime_id}</div>
              <div class="muted">
                ${item.mode} · ${item.status}
                ${item.version ? ` · ${item.version}` : ""}
              </div>
              <div class="muted">${relativeTime(item.occurred_at)}</div>
              <button
                class="secondary select-runtime-btn"
                data-runtime-id="${item.runtime_id}"
                style="margin-top:10px"
              >
                Open action panel
              </button>
            </article>
          `,
        )
        .join("")
    : '<div class="empty">No runtime registrations yet.</div>';
}

function renderRuntimeActionButtons(item) {
  const buttons = [
    `<button class="secondary select-runtime-action-btn" data-action-id="${item.action_id}">Open receipts</button>`,
    `<button class="secondary add-runtime-receipt-btn" data-action-id="${item.action_id}">Add receipt</button>`,
  ];
  if (item.status === "queued") {
    buttons.push(
      `<button class="secondary ack-runtime-action-btn" data-action-id="${item.action_id}">Acknowledge</button>`,
    );
  }
  if (["queued", "acknowledged"].includes(item.status)) {
    buttons.push(
      `<button class="secondary transition-runtime-action-btn" data-action-id="${item.action_id}" data-next-status="running">Mark running</button>`,
    );
  }
  if (["queued", "acknowledged", "running"].includes(item.status)) {
    buttons.push(
      `<button class="secondary transition-runtime-action-btn" data-action-id="${item.action_id}" data-next-status="succeeded">Mark done</button>`,
      `<button class="secondary transition-runtime-action-btn" data-action-id="${item.action_id}" data-next-status="failed">Mark failed</button>`,
    );
  }
  return buttons.join("");
}

function renderRuntimeActions(data) {
  runtimeActionsEl.innerHTML = data.items.length
    ? data.items
        .map((item) => {
          const receiptMeta = item.latest_receipt_summary
            ? `
              <div class="muted" style="margin-top:8px">
                receipt=${item.latest_receipt_status || "recorded"}
                · ${item.latest_receipt_summary}
              </div>
            `
            : "";
          const argumentsMeta = Object.keys(item.arguments || {}).length
            ? `<div style="margin-top:8px">${JSON.stringify(item.arguments)}</div>`
            : "";
          return `
            <article class="runtime-item">
              <strong>${item.action}</strong>
              <div class="muted">
                ${item.status}
                · ${relativeTime(item.last_updated_at || item.occurred_at)}
              </div>
              ${item.note ? `<div style="margin-top:8px">${item.note}</div>` : ""}
              ${receiptMeta}
              ${argumentsMeta}
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
                ${renderRuntimeActionButtons(item)}
              </div>
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No runtime actions yet.</div>';
}

function renderRuntimeActionTimeline(data) {
  runtimeActionTimelineEl.innerHTML = data.items.length
    ? data.items
        .map(
          (item) => `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.title}</strong>
                <span>${item.status || item.event_type}</span>
                <span>${relativeTime(item.occurred_at)}</span>
              </div>
              ${item.detail ? `<div style="margin-top:8px">${item.detail}</div>` : ""}
            </article>
          `,
        )
        .join("")
    : '<div class="empty">No runtime action timeline yet.</div>';
}

function renderRuntimeActionReceipts(data) {
  runtimeActionReceiptsEl.innerHTML = data.items.length
    ? data.items
        .map((item) => {
          const metadata = Object.keys(item.metadata || {}).length
            ? `
              <div class="muted" style="margin-top:8px">
                ${JSON.stringify(item.metadata)}
              </div>
            `
            : "";
          return `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.status || "receipt"}</strong>
                <span>${relativeTime(item.occurred_at)}</span>
              </div>
              <div style="margin-top:8px">${item.summary}</div>
              ${metadata}
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No runtime action receipts yet.</div>';
}

function renderAssignmentSuggestions(data) {
  assignmentSuggestionsEl.innerHTML = data.items.length
    ? data.items
        .map((item) => {
          const loadMeta = `
            <div class="muted" style="margin-top:8px">
              load=${item.current_load} · pressure=${item.queue_pressure}
              ${item.capacity_hint ? ` · ${item.capacity_hint}` : ""}
            </div>
          `;
          const feedbackMeta = item.last_feedback
            ? `
              <div class="muted" style="margin-top:8px">
                feedback=${item.last_feedback}
                ${item.feedback_note ? ` · ${item.feedback_note}` : ""}
              </div>
            `
            : "";
          return `
            <article class="runtime-item">
              <strong>${item.name}</strong>
              <div class="muted">
                ${item.agent_id} · role=${item.recommended_role}
                · score=${item.score}
              </div>
              <div style="margin-top:8px">${item.rationale}</div>
              ${loadMeta}
              ${feedbackMeta}
              <div class="muted" style="margin-top:8px">
                learned=${item.learned_weight} · recency=${item.recency_weight || 0}
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
                <button
                  class="secondary use-assignment-suggestion-btn"
                  data-agent-id="${item.agent_id}"
                  data-role="${item.recommended_role}"
                  data-note="${item.autofill_note || ""}"
                >
                  Use suggestion
                </button>
                <button
                  class="secondary assignment-feedback-btn"
                  data-agent-id="${item.agent_id}"
                  data-feedback="accepted"
                >
                  Accept
                </button>
                <button
                  class="secondary assignment-feedback-btn"
                  data-agent-id="${item.agent_id}"
                  data-feedback="dismissed"
                >
                  Dismiss
                </button>
              </div>
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No assignment suggestions available.</div>';
}

function renderAssignmentLearningWeights(data) {
  assignmentLearningWeightsEl.innerHTML = data.items.length
    ? data.items
        .map(
          (item) => `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.name}</strong>
                <span>${item.agent_id}</span>
                <span>weight=${item.learned_weight}</span>
                <span>recency=${item.recency_weight || 0}</span>
              </div>
              <div class="muted" style="margin-top:8px">
                accepted=${item.accepted_count} · applied=${item.applied_count}
                · dismissed=${item.dismissed_count}
              </div>
              <div class="muted" style="margin-top:8px">${item.rationale}</div>
            </article>
          `,
        )
        .join("")
    : '<div class="empty">No learning weights yet.</div>';
}

function renderAssignments(data) {
  cycleAssignmentsEl.innerHTML = data.items.length
    ? data.items
        .map(
          (item) => `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.agent_id}</strong>
                <span>${item.assignment_role}</span>
                <span>${relativeTime(item.occurred_at)}</span>
              </div>
              ${item.note ? `<div style="margin-top:8px">${item.note}</div>` : ""}
              <div class="muted" style="margin-top:8px">
                assigned by ${item.actor_id || "unknown"}
              </div>
            </article>
          `,
        )
        .join("")
    : '<div class="empty">No assignments yet.</div>';
}

function renderComments(data) {
  commentsListEl.innerHTML = data.items.length
    ? data.items
        .map((comment) => {
          const mentions = comment.mentions.length
            ? `
              <div class="muted" style="margin-top:8px">
                mentions=${comment.mentions.join(", ")}
              </div>
            `
            : "";
          return `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${comment.actor_id || "unknown"}</strong>
                <span>${comment.actor_role || ""}</span>
                <span>${relativeTime(comment.occurred_at)}</span>
              </div>
              <div style="margin-top:8px">${comment.body}</div>
              ${mentions}
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No comments yet.</div>';
}
