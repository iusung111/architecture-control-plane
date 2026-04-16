function discussionActionButton(className, attrs, label) {
  return `<button class="secondary ${className}" ${attrs}>${label}</button>`;
}

function renderWorkspaceDiscussions(data) {
  const mentionInfo = data.mention_filter
    ? `<div class="empty">Filter: ${data.mention_filter}</div>`
    : "";
  const items = data.items.length
    ? data.items
        .map((item) => {
          const openThread = discussionActionButton(
            "select-discussion-btn",
            `data-discussion-id="${item.discussion_id}"`,
            "Open thread",
          );
          const resolveButton = discussionActionButton(
            "discussion-resolve-btn",
            `data-discussion-id="${item.discussion_id}" data-next-resolved="${
              item.is_resolved ? "false" : "true"
            }"`,
            item.is_resolved ? "Reopen" : "Resolve",
          );
          const pinButton = discussionActionButton(
            "discussion-pin-btn",
            `data-discussion-id="${item.discussion_id}" data-next-pinned="${
              item.is_pinned ? "false" : "true"
            }"`,
            item.is_pinned ? "Unpin" : "Pin",
          );
          return `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.project_id || "workspace"}</strong>
                <span>${item.actor_role || ""}</span>
                <span>${relativeTime(item.last_updated_at || item.occurred_at)}</span>
              </div>
              <div style="margin-top:8px">${item.body}</div>
              <div class="muted" style="margin-top:8px">
                replies=${item.reply_count || 0}
                · resolved=${item.is_resolved ? "yes" : "no"}
                · pinned=${item.is_pinned ? "yes" : "no"}
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
                ${openThread}
                ${resolveButton}
                ${pinButton}
              </div>
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No workspace discussions yet.</div>';
  latestDiscussionData = data || { items: [] };
  workspaceDiscussionsEl.innerHTML = mentionInfo + items;
  renderPersonalInbox();
}

function renderWorkspaceDiscussionGroups(data) {
  workspaceDiscussionGroupsEl.innerHTML = data.items.length
    ? data.items
        .map((group) => {
          const previewIds = (group.items || [])
            .map((item) => item.discussion_id.slice(0, 8))
            .join(", ");
          const preview = previewIds
            ? `
              <div class="muted" style="margin-top:8px">
                preview=${previewIds}
              </div>
            `
            : "";
          return `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${group.label}</strong>
                <span>threads=${group.total_count}</span>
                <span>${relativeTime(group.last_updated_at)}</span>
              </div>
              <div class="muted" style="margin-top:8px">
                open=${group.unresolved_count}
                · resolved=${group.resolved_count}
                · pinned=${group.pinned_count}
              </div>
              ${preview}
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No grouped discussions yet.</div>';
}

function renderSavedDiscussionFilters(data) {
  savedDiscussionFiltersEl.innerHTML = data.items.length
    ? data.items
        .map((item) => {
          const usedAt = item.last_used_at ? ` · last used=${relativeTime(item.last_used_at)}` : "";
          const applyButton = discussionActionButton(
            "apply-saved-discussion-filter-btn",
            `data-filter-id="${item.filter_id}" data-project-id="${item.project_id || ""}" data-mention="${item.mention || ""}" data-query="${item.query || ""}"`,
            "Apply filter",
          );
          const renameButton = discussionActionButton(
            "rename-saved-discussion-filter-btn",
            `data-filter-id="${item.filter_id}" data-name="${item.name}" data-project-id="${item.project_id || ""}" data-mention="${item.mention || ""}" data-query="${item.query || ""}"`,
            "Rename",
          );
          const favoriteButton = discussionActionButton(
            "favorite-saved-discussion-filter-btn",
            `data-filter-id="${item.filter_id}" data-is-favorite="${
              item.is_favorite ? "false" : "true"
            }"`,
            item.is_favorite ? "Unfavorite" : "Favorite",
          );
          const deleteButton = discussionActionButton(
            "delete-saved-discussion-filter-btn",
            `data-filter-id="${item.filter_id}"`,
            "Delete",
          );
          return `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.name}</strong>
                <span>${item.is_favorite ? "★ favorite" : "saved"}</span>
                <span>${relativeTime(item.last_used_at || item.updated_at || item.occurred_at)}</span>
              </div>
              <div class="muted" style="margin-top:8px">
                project=${item.project_id || "all"}
                · mention=${item.mention || "any"}
                · query=${item.query || "none"}
              </div>
              <div class="muted" style="margin-top:8px">
                updated=${relativeTime(item.updated_at || item.occurred_at)}${usedAt}
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
                ${applyButton}
                ${renameButton}
                ${favoriteButton}
                ${deleteButton}
              </div>
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No saved discussion filters yet.</div>';
}

function renderRemoteWorkspaceExecutors(data) {
  remoteWorkspaceExecutorsEl.innerHTML = data.items.length
    ? data.items
        .map(
          (item) => `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.name}</strong>
                <span>${item.key}</span>
                <span>${item.mode}</span>
                <span>${item.enabled ? "enabled" : "planned"}</span>
              </div>
              <div class="muted" style="margin-top:8px">${item.description}</div>
              <div class="muted" style="margin-top:8px">
                capabilities=${(item.capabilities || []).join(", ") || "none"}
              </div>
            </article>
          `,
        )
        .join("")
    : '<div class="empty">No executors available.</div>';
}

function renderRemoteWorkspaceSnapshots(data) {
  remoteWorkspaceSnapshotsEl.innerHTML = data.items.length
    ? data.items
        .map((item) => {
          const openButton = discussionActionButton(
            "select-remote-workspace-btn",
            `data-workspace-id="${item.workspace_id}" data-repo-url="${
              item.repo_url || ""
            }" data-repo-branch="${item.repo_branch || ""}"`,
            "Open workspace",
          );
          return `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.workspace_id}</strong>
                <span>${item.last_execution_status || "parked"}</span>
                <span>${relativeTime(item.updated_at)}</span>
              </div>
              <div class="muted" style="margin-top:8px">
                project=${item.project_id || "n/a"}
                · branch=${item.repo_branch || "n/a"}
                · executor=${item.executor_key || "planning"}
              </div>
              <div class="muted" style="margin-top:8px">
                repo=${item.repo_url || "unset"}
                ${item.patch_present ? " · patch attached" : ""}
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
                ${openButton}
              </div>
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No remote workspace snapshots yet.</div>';
}

function renderRemoteExecutionLinks(item) {
  if (!item.logs_url && !item.external_url) return "";
  const logsLabel = item.logs_url ? `logs=${item.logs_url}` : "";
  const externalLabel = item.external_url
    ? `${item.logs_url ? " · " : ""}external=${item.external_url}`
    : "";
  return `
    <div class="muted" style="margin-top:8px">
      ${logsLabel}${externalLabel}
    </div>
  `;
}

function renderRemoteWorkspaceExecutions(data) {
  remoteWorkspaceExecutionsEl.innerHTML = data.items.length
    ? data.items
        .map((item) => {
          const artifacts = (item.artifacts || []).length
            ? `
              <div class="muted" style="margin-top:8px">
                artifacts=${item.artifacts.map((artifact) => artifact.artifact_type).join(", ")}
              </div>
            `
            : "";
          const cancelButton = item.can_cancel
            ? discussionActionButton(
                "cancel-remote-execution-btn",
                `data-execution-id="${item.execution_id}"`,
                "Cancel",
              )
            : "";
          return `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.execution_kind}</strong>
                <span>${item.status}</span>
                <span>${item.executor_key}</span>
                <span>${relativeTime(item.last_updated_at || item.requested_at)}</span>
              </div>
              ${item.message ? `<div style="margin-top:8px">${item.message}</div>` : ""}
              <div class="muted" style="margin-top:8px">
                command=${item.command || "default"}
                ${item.result_summary ? ` · result=${item.result_summary}` : ""}
              </div>
              ${renderRemoteExecutionLinks(item)}
              ${artifacts}
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
                ${discussionActionButton(
                  "inspect-remote-execution-btn",
                  `data-execution-id="${item.execution_id}"`,
                  "Inspect",
                )}
                ${cancelButton}
              </div>
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No remote executions yet.</div>';
}

function renderRemoteWorkspaceExecutionDetail(item) {
  if (!item) {
    remoteWorkspaceExecutionDetailEl.innerHTML =
      '<div class="empty">Inspect a remote execution to see result summary, timing, and artifacts.</div>';
    return;
  }
  const artifacts = (item.artifacts || []).length
    ? `<div class="artifact-list">${artifactSummaryItems(item.artifacts)}</div>`
    : '<div class="muted" style="margin-top:8px">No artifacts collected for this execution.</div>';
  remoteWorkspaceExecutionDetailEl.innerHTML = `
    <article class="timeline-item">
      <div class="event-meta">
        <strong>Execution detail</strong>
        <span>${item.execution_id}</span>
        <span>${item.status}</span>
      </div>
      <div class="info-grid">
        <div class="info-chip"><strong>Kind</strong><span>${item.execution_kind || "n/a"}</span></div>
        <div class="info-chip"><strong>Executor</strong><span>${item.executor_key || "n/a"}</span></div>
        <div class="info-chip"><strong>Command</strong><span>${item.command || "default"}</span></div>
        <div class="info-chip"><strong>Exit code</strong><span>${item.exit_code ?? "n/a"}</span></div>
        <div class="info-chip"><strong>Started</strong><span>${item.started_at ? relativeTime(item.started_at) : "n/a"}</span></div>
        <div class="info-chip"><strong>Completed</strong><span>${item.completed_at ? relativeTime(item.completed_at) : "n/a"}</span></div>
      </div>
      <div class="section-divider"></div>
      <div>${item.result_summary || item.message || "No execution summary yet."}</div>
      ${renderRemoteExecutionLinks(item)}
      ${artifacts}
    </article>
  `;
}

function renderPersistentWorkspaceSessions(data) {
  persistentWorkspaceSessionsEl.innerHTML = (data?.items || []).length
    ? data.items
        .map((item) => {
          const openButton = discussionActionButton(
            "use-persistent-session-btn",
            `data-workspace-id="${item.workspace_id}" data-repo-url="${
              item.repo_url || ""
            }" data-repo-branch="${item.repo_branch || ""}"`,
            "Open session",
          );
          const hibernateButton =
            item.hibernate_supported && item.status !== "hibernated"
              ? discussionActionButton(
                  "hibernate-persistent-session-btn",
                  `data-workspace-id="${item.workspace_id}"`,
                  "Hibernate",
                )
              : "";
          const deleteButton = discussionActionButton(
            "delete-persistent-session-btn",
            `data-workspace-id="${item.workspace_id}"`,
            "Delete",
          );
          return `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.workspace_id}</strong>
                <span>${item.status}</span>
                <span>${item.provider}</span>
                <span>${relativeTime(item.updated_at)}</span>
              </div>
              <div class="muted" style="margin-top:8px">
                project=${item.project_id || "n/a"}
                · branch=${item.repo_branch || "n/a"}
                · expires=${item.expires_at ? relativeTime(item.expires_at) : "n/a"}
              </div>
              ${item.note ? `<div style="margin-top:8px">${item.note}</div>` : ""}
              <div class="inline-actions" style="margin-top:10px">
                ${openButton}
                ${hibernateButton}
                ${deleteButton}
              </div>
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No persistent sessions yet.</div>';
}

function renderAuditExplorer(data) {
  auditExplorerEl.innerHTML =
    data.events && data.events.length
      ? data.events
          .map(
            (item) => `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.event_type}</strong>
                <span>${item.actor_id || "system"}</span>
                <span>${relativeTime(item.occurred_at)}</span>
              </div>
              <div class="muted" style="margin-top:8px">
                event=${item.audit_event_id || "n/a"}
                · payload=${JSON.stringify(item.event_payload || {})}
              </div>
            </article>
          `,
          )
          .join("")
      : '<div class="empty">No audit events found.</div>';
}

function renderRemoteWorkspaceResume(data) {
  if (!data) {
    remoteWorkspaceResumeEl.innerHTML =
      '<div class="empty">Select or save a remote workspace snapshot to view resume memory.</div>';
    return;
  }
  const artifacts = (data.artifacts || [])
    .map((item) => `${item.artifact_type}:${item.artifact_id}`)
    .join(", ");
  remoteWorkspaceResumeEl.innerHTML = `
    <article class="timeline-item">
      <div class="event-meta">
        <strong>Resume memory</strong>
        <span>${data.workspace_id}</span>
        <span>resumes=${data.resume_count || 0}</span>
      </div>
      <div class="muted" style="margin-top:8px">
        last failed=${data.last_failed_command || "n/a"}
        · summary=${data.last_result_summary || "n/a"}
      </div>
      <div class="muted" style="margin-top:8px">
        patch stack=${(data.patch_stack || []).length}
        · artifacts=${artifacts || "none"}
      </div>
    </article>
  `;
}

function renderWorkbenchSavedViews(data) {
  latestWorkbenchViews = data || { items: [] };
  workbenchSavedViewsEl.innerHTML = (data.items || []).length
    ? data.items
        .map((item) => {
          const badges = [
            item.layout?.is_default ? '<span class="pill">default</span>' : "",
            item.layout?.smart_filter
              ? `<span class="pill">${item.layout.smart_filter}</span>`
              : "",
            isWorkbenchViewChanged(item) ? '<span class="pill">changed</span>' : "",
          ]
            .filter(Boolean)
            .join("");
          const renameButton = discussionActionButton(
            "rename-workbench-view-btn",
            `data-view-id="${item.view_id}" data-view-name="${escapeHtml(
              item.name,
            )}" data-view-notes="${escapeHtml(item.notes || "")}"`,
            "Rename",
          );
          return `
            <article class="timeline-item">
              <div class="event-meta">
                <strong>${item.name}</strong>
                <span>${item.project_id || "global"}</span>
                <span>${relativeTime(item.last_used_at || item.updated_at)}</span>
              </div>
              <div class="meta" style="margin-top:8px">${badges}</div>
              <div class="muted" style="margin-top:8px">
                workspace=${item.workspace_id || "n/a"}
                · cycle=${item.cycle_id || "n/a"}
                · panels=${(item.selected_panels || []).join(", ") || "default"}
                · use=${item.use_count || 0}
              </div>
              <div class="muted" style="margin-top:8px">notes=${item.notes || "none"}</div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
                ${discussionActionButton(
                  "use-workbench-view-btn",
                  `data-view-id="${item.view_id}"`,
                  "Apply",
                )}
                ${discussionActionButton(
                  "set-default-workbench-view-btn",
                  `data-view-id="${item.view_id}"`,
                  item.layout?.is_default ? "Default view" : "Set default",
                )}
                ${renameButton}
                ${discussionActionButton(
                  "delete-workbench-view-btn",
                  `data-view-id="${item.view_id}"`,
                  "Delete",
                )}
              </div>
            </article>
          `;
        })
        .join("")
    : '<div class="empty">No saved workbench views yet.</div>';
}
