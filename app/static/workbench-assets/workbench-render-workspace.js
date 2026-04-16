function renderWorkspace(data) {
  setStatus(workspaceStateEl, `${data.projects.length} projects`);
  const totals = `
    <article class="timeline-item">
      <div class="event-meta">
        <strong>Workspace totals</strong>
        <span>${relativeTime(data.generated_at)}</span>
      </div>
      <div style="margin-top:8px">
        cycles=${data.totals.cycles} · active=${data.totals.active}
        · review=${data.totals.pending_reviews}
        · completed=${data.totals.completed}
        · failed=${data.totals.failed}
      </div>
    </article>
  `;
  const projects = data.projects.length
    ? data.projects
        .map(
          (project) => `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${project.project_id}</strong>
                <span>${relativeTime(project.updated_at)}</span>
              </div>
              <div style="margin-top:8px">
                active=${project.active_cycles}
                · review=${project.pending_reviews}
                · done=${project.completed_cycles}
                · failed=${project.failed_cycles}
              </div>
            </article>
          `,
        )
        .join("")
    : '<div class="empty">No projects in scope.</div>';
  const comments = data.recent_comments.length
    ? data.recent_comments
        .map(
          (comment) => `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>Comment · ${comment.cycle_id}</strong>
                <span>${relativeTime(comment.occurred_at)}</span>
              </div>
              <div style="margin-top:8px">${comment.body}</div>
            </article>
          `,
        )
        .join("")
    : "";
  workspaceEl.innerHTML = totals + projects + comments;
}

function renderAgentRoster(data) {
  agentRosterEl.innerHTML = data.items.length
    ? data.items
        .map((agent) => {
          const focus = agent.focus ? `<span>focus=${agent.focus}</span>` : "";
          return `
            <article class="runtime-item">
              <strong>${agent.name}</strong>
              <div class="muted">${agent.persona}</div>
              <div class="event-meta" style="margin-top:8px">
                <span>${agent.status}</span>
                <span>load=${agent.current_load}</span>
                ${focus}
              </div>
              <div style="margin-top:8px">${agent.specialties.join(" · ")}</div>
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No agent profiles.</div>';
}

function renderRuntimePanel(data) {
  const metrics = data.queue_metrics
    .map(
      (metric) => `
        <article class="runtime-item">
          <strong>${metric.label}</strong>
          <div>${metric.value}</div>
          ${metric.detail ? `<div class="muted" style="margin-top:6px">${metric.detail}</div>` : ""}
        </article>
      `,
    )
    .join("");
  const jobs = data.recent_jobs
    .map(
      (job) => `
        <article class="runtime-item">
          <strong>${job.title}</strong>
          <div class="event-meta">
            <span>${job.status || ""}</span>
            <span>${relativeTime(job.occurred_at)}</span>
          </div>
          ${job.detail ? `<div style="margin-top:8px">${job.detail}</div>` : ""}
        </article>
      `,
    )
    .join("");
  const signals = (data.signals || [])
    .map(
      (signal) => `
        <article class="runtime-item">
          <strong>Signal</strong>
          <div>${signal}</div>
        </article>
      `,
    )
    .join("");
  runtimePanelEl.innerHTML =
    metrics + jobs + signals || '<div class="empty">Runtime is idle.</div>';
}

function renderIssueCard(data) {
  latestIssueCardData = data || null;
  const detailedResult = data.detailed_result || data.result || null;
  const verificationFailedRules = detailedResult?.verification?.failed_rules || [];
  const verificationMeta = detailedResult
    ? `verification=${detailedResult.verification?.status || "n/a"}${
        verificationFailedRules.length
          ? ` · failed_rules=${verificationFailedRules.join(", ")}`
          : ""
      }`
    : "";
  const approvalMeta = detailedResult
    ? `approval=${
        detailedResult.approval?.state || (detailedResult.approval?.required ? "required" : "n/a")
      }`
    : "";
  const resultArtifacts = (detailedResult?.output_artifacts || []).length
    ? `<div class="artifact-list">${artifactSummaryItems(detailedResult.output_artifacts)}</div>`
    : '<div class="muted">No output artifacts recorded yet.</div>';
  const result = detailedResult
    ? `
      <div class="section-divider"></div>
      <div class="stack-xs">
        <div class="event-meta">
          <strong>Latest result</strong>
          <span>${detailedResult.final_state || "n/a"}</span>
          <span>${relativeTime(detailedResult.generated_at || data.cycle.updated_at)}</span>
        </div>
        <div>${detailedResult.summary || "No summary yet."}</div>
        <div class="muted">${verificationMeta}</div>
        <div class="muted">${approvalMeta}</div>
        ${resultArtifacts}
      </div>
    `
    : '<div class="section-divider"></div><div class="muted">No final result recorded yet.</div>';
  const approval = data.active_approval
    ? `
      <div class="muted" style="margin-top:8px">
        approval=${data.active_approval.state || "required"}
        (${data.active_approval.approval_id || "pending"})
      </div>
    `
    : "";
  const assignment = data.current_assignment
    ? `
      <div class="muted" style="margin-top:8px">
        assigned=${data.current_assignment.agent_id}
        · role=${data.current_assignment.assignment_role}
        ${data.current_assignment.note ? ` · ${data.current_assignment.note}` : ""}
      </div>
    `
    : "";
  const cycleActions = [
    data.cycle.approval_required ? '<span class="pill">approval required</span>' : "",
    data.cycle.retry_allowed ? '<span class="pill">retry ready</span>' : "",
    data.cycle.replan_allowed ? '<span class="pill">replan ready</span>' : "",
  ]
    .filter(Boolean)
    .join(" ");
  const suggestionMeta = (data.assignment_suggestions || []).length
    ? `
      <div class="muted" style="margin-top:8px">
        suggested agents=${(data.assignment_suggestions || [])
          .map((item) => `${item.agent_id}:${item.recommended_role}:${item.learned_weight ?? 0}`)
          .join(", ")}
      </div>
    `
    : `
      <div class="muted" style="margin-top:8px">
        suggested agents=${(data.suggested_agents || []).join(", ") || "n/a"}
      </div>
    `;
  const nextSteps = buildNextStepActions(data, detailedResult);
  const nextStepsHtml = nextSteps.length
    ? nextSteps
        .map(
          (step) => `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${step.label}</strong>
                <span>${step.action}</span>
              </div>
              <div class="muted" style="margin-top:8px">${step.detail}</div>
              <div class="inline-actions" style="margin-top:10px">
                <button class="secondary next-step-btn" data-next-action="${step.action}">
                  Run
                </button>
              </div>
            </article>
          `,
        )
        .join("")
    : '<div class="empty">No follow-up action is recommended yet.</div>';
  const preview =
    (data.timeline_preview || [])
      .slice(0, 3)
      .map(
        (event) => `
          <article class="timeline-item">
            <div class="event-meta">
              <strong>${event.title}</strong>
              <span>${event.source}</span>
              <span>${relativeTime(event.occurred_at)}</span>
            </div>
            ${event.detail ? `<div style="margin-top:8px">${event.detail}</div>` : ""}
          </article>
        `,
      )
      .join("") || '<div class="empty">No timeline preview available.</div>';
  document.getElementById("issue-action-cycle-id").value = data.cycle.cycle_id || "";
  document.getElementById("issue-action-approval-id").value =
    data.active_approval?.approval_id || "";
  issueCardEl.innerHTML = `
    <article class="timeline-item">
      <div class="event-meta">
        <strong>${data.cycle.project_id}</strong>
        <span>${data.cycle.state}</span>
        <span>${relativeTime(data.cycle.updated_at)}</span>
      </div>
      <div style="margin-top:8px">cycle=${data.cycle.cycle_id}</div>
      ${cycleActions ? `<div class="meta" style="margin-top:8px">${cycleActions}</div>` : ""}
      ${suggestionMeta}
      <div class="muted" style="margin-top:8px">
        active jobs=${data.active_job_count} · comments=${data.comment_count}
      </div>
      ${approval}
      ${assignment}
      ${result}
    </article>
    <article class="timeline-item">
      <div class="event-meta">
        <strong>Suggested next steps</strong>
        <span>${nextSteps.length} actions</span>
      </div>
      <div class="timeline" style="max-height:none;margin-top:10px">
        ${nextStepsHtml}
      </div>
    </article>
    ${preview}
  `;
}
