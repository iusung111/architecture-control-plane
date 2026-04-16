
    const storageKey = 'acp-workbench-auth';
    const boardColumnsEl = document.getElementById('board-columns');
    const streamLogEl = document.getElementById('stream-log');
    const timelineEl = document.getElementById('timeline');
    const workspaceEl = document.getElementById('workspace-overview');
    const workspaceStateEl = document.getElementById('workspace-state');
    const agentRosterEl = document.getElementById('agent-roster');
    const runtimePanelEl = document.getElementById('runtime-panel');
    const auditExplorerEl = document.getElementById('audit-explorer');
    const remoteWorkspaceExecutorsEl = document.getElementById('remote-workspace-executors');
    const remoteWorkspaceSnapshotsEl = document.getElementById('remote-workspace-snapshots');
    const remoteWorkspaceExecutionsEl = document.getElementById('remote-workspace-executions');
    const remoteWorkspaceExecutionDetailEl = document.getElementById('remote-workspace-execution-detail');
    const remoteWorkspaceResumeEl = document.getElementById('remote-workspace-resume');
    const persistentWorkspaceSessionsEl = document.getElementById('persistent-workspace-sessions');
    const workbenchSavedViewsEl = document.getElementById('workbench-saved-views');
    const runtimeRegistrationsEl = document.getElementById('runtime-registrations');
    const runtimeActionsEl = document.getElementById('runtime-actions');
    const runtimeActionTimelineEl = document.getElementById('runtime-action-timeline');
    const runtimeActionReceiptsEl = document.getElementById('runtime-action-receipts');
    const issueCardEl = document.getElementById('issue-card-detail');
    const pendingApprovalsEl = document.getElementById('pending-approvals');
    const personalInboxEl = document.getElementById('personal-inbox');
    const personalInboxCountEl = document.getElementById('personal-inbox-count');
    const approvalReviewContextEl = document.getElementById('approval-review-context');
    const resolutionSummaryEl = document.getElementById('resolution-summary');
    const handoffBundleEl = document.getElementById('handoff-bundle');
    const createCycleStatusEl = document.getElementById('create-cycle-status');
    const issueActionStatusEl = document.getElementById('issue-action-status');
    const authStatusEl = document.getElementById('auth-status');
    const workspaceDiscussionGroupsEl = document.getElementById('workspace-discussion-groups');
    const savedDiscussionFiltersEl = document.getElementById('saved-discussion-filters');
    const workspaceDiscussionsEl = document.getElementById('workspace-discussions');
    const discussionRepliesEl = document.getElementById('discussion-replies');
    const commentsListEl = document.getElementById('comments-list');
    const cycleAssignmentsEl = document.getElementById('cycle-assignments');
    const assignmentSuggestionsEl = document.getElementById('assignment-suggestions');
    const assignmentLearningWeightsEl = document.getElementById('assignment-learning-weights');
    const lastSyncEl = document.getElementById('last-sync');
    const boardStateEl = document.getElementById('board-state');
    const cycleStateEl = document.getElementById('cycle-state');
    const runtimeActionStateEl = document.getElementById('runtime-action-state');
    const projectStateEl = document.getElementById('project-state');
    const boardTotalEl = document.getElementById('board-total');
    const selectedCycleInput = document.getElementById('selected-cycle');

    let boardAbortController = null;
    let cycleAbortController = null;
    let runtimeActionAbortController = null;
    let selectedCycleId = null;
    let selectedDiscussionId = null;
    let selectedRuntimeId = null;
    let selectedActionId = null;
    let selectedWorkspaceId = null;
    let selectedExecutionId = null;
    let latestBoardData = null;
    let latestPendingApprovalData = { items: [] };
    let latestDiscussionData = { items: [] };
    let latestWorkbenchViews = { items: [] };
    let latestIssueCardData = null;
    let latestHandoffBundle = null;
    let activeSmartFilter = 'all';
    let selectedApprovalReviewId = null;
    let defaultWorkbenchViewApplied = false;

    function setStatus(el, value) { el.textContent = value; }
    function nowLabel() { return new Date().toLocaleString(); }
    function setAuthStatus(message) { authStatusEl.textContent = message || ''; }
    function authValidationSummary() {
      const bearer = document.getElementById('auth-bearer').value.trim();
      const userId = document.getElementById('auth-user-id').value.trim();
      const userRole = document.getElementById('auth-user-role').value.trim();
      const managementKey = document.getElementById('auth-management-key').value.trim();
      const userApiReady = Boolean(bearer || userId);
      const actorReady = Boolean(userId && userRole);
      const auditReady = Boolean(managementKey);
      if (!userApiReady) return 'User API headers are incomplete. Add Bearer token or X-User-Id.';
      if (!actorReady) return 'Add X-User-Id and X-User-Role to use cycle actions safely.';
      if (!auditReady) return 'User APIs ready. Add X-Management-Key for audit explorer.';
      return 'Headers look ready for board, cycle actions, and audit explorer.';
    }
    function applyAuthPreset(kind) {
      const roleInput = document.getElementById('auth-user-role');
      const userInput = document.getElementById('auth-user-id');
      if (kind === 'operator') {
        if (!userInput.value.trim()) userInput.value = 'operator-1';
        roleInput.value = 'operator';
        setAuthStatus('Operator preset applied. Review X-User-Id before connecting.');
      } else if (kind === 'reviewer') {
        if (!userInput.value.trim()) userInput.value = 'reviewer-1';
        roleInput.value = 'operator';
        setAuthStatus('Reviewer preset applied for approval handling. Update X-User-Id as needed.');
      } else if (kind === 'audit') {
        if (!userInput.value.trim()) userInput.value = 'operator-1';
        roleInput.value = 'operator';
        setAuthStatus('Audit preset applied. Add X-Management-Key to unlock audit explorer.');
      }
    }
    function saveAuth() {
      const payload = {
        bearer: document.getElementById('auth-bearer').value.trim(),
        userId: document.getElementById('auth-user-id').value.trim(),
        userRole: document.getElementById('auth-user-role').value.trim(),
        tenantId: document.getElementById('auth-tenant-id').value.trim(),
        managementKey: document.getElementById('auth-management-key').value.trim(),
      };
      localStorage.setItem(storageKey, JSON.stringify(payload));
      setAuthStatus('Saved request headers locally in this browser.');
    }
    function loadAuth() {
      try {
        const raw = localStorage.getItem(storageKey);
        if (!raw) return;
        const payload = JSON.parse(raw);
        document.getElementById('auth-bearer').value = payload.bearer || '';
        document.getElementById('auth-user-id').value = payload.userId || '';
        document.getElementById('auth-user-role').value = payload.userRole || 'operator';
        document.getElementById('auth-tenant-id').value = payload.tenantId || '';
        document.getElementById('auth-management-key').value = payload.managementKey || '';
      } catch (_) {}
    }
    function clearAuth() {
      localStorage.removeItem(storageKey);
      loadAuth();
      document.getElementById('auth-bearer').value = '';
      document.getElementById('auth-user-id').value = '';
      document.getElementById('auth-user-role').value = 'operator';
      document.getElementById('auth-tenant-id').value = '';
      document.getElementById('auth-management-key').value = '';
      setAuthStatus('Cleared saved request headers.');
    }
    function authHeaders() {
      const headers = { 'Accept': 'application/json' };
      const bearer = document.getElementById('auth-bearer').value.trim();
      const userId = document.getElementById('auth-user-id').value.trim();
      const userRole = document.getElementById('auth-user-role').value.trim();
      const tenantId = document.getElementById('auth-tenant-id').value.trim();
      const managementKey = document.getElementById('auth-management-key').value.trim();
      if (bearer) headers['Authorization'] = bearer.startsWith('Bearer ') ? bearer : `Bearer ${bearer}`;
      if (userId) headers['X-User-Id'] = userId;
      if (userRole) headers['X-User-Role'] = userRole;
      if (tenantId) headers['X-Tenant-Id'] = tenantId;
      if (managementKey) headers['X-Management-Key'] = managementKey;
      return headers;
    }
    function managementHeaders() {
      const managementKey = document.getElementById('auth-management-key').value.trim();
      return managementKey ? { 'Accept': 'application/json', 'X-Management-Key': managementKey } : { 'Accept': 'application/json' };
    }
    function qs(params) {
      const search = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => {
        if (v !== null && v !== undefined && String(v).length) search.set(k, v);
      });
      const rendered = search.toString();
      return rendered ? `?${rendered}` : '';
    }
    async function apiJson(path) {
      const response = await fetch(path, { headers: authHeaders() });
      const body = await response.json();
      if (!response.ok || body.status === 'error') {
        throw new Error(body?.error?.message || `Request failed (${response.status})`);
      }
      return body.data;
    }
    async function adminJson(path) {
      const response = await fetch(path, { headers: managementHeaders() });
      const body = await response.json();
      if (!response.ok || body.status === 'error') {
        throw new Error(body?.error?.message || `Request failed (${response.status})`);
      }
      return body.data;
    }
    function relativeTime(value) {
      const dt = new Date(value);
      if (Number.isNaN(dt.getTime())) return String(value || '');
      return `${dt.toLocaleTimeString()} · ${dt.toLocaleDateString()}`;
    }
    function makeIdempotencyKey(prefix) {
      if (window.crypto && typeof window.crypto.randomUUID === 'function') return `${prefix}-${window.crypto.randomUUID()}`;
      return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }
    function setInlineStatus(el, message) {
      if (!el) return;
      el.textContent = message || '';
    }
    function showToast(message, tone = 'info', title = 'Workbench') {
      const stack = document.getElementById('toast-stack');
      if (!stack || !message) return;
      const el = document.createElement('div');
      el.className = `toast ${tone}`;
      el.innerHTML = `<strong>${title}</strong><div>${message}</div>`;
      stack.appendChild(el);
      window.setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, 3600);
    }
    function requireField(value, message) {
      if (value) return value;
      showToast(message, 'error', 'Validation');
      throw new Error(message);
    }
    function openActionModal(config) {
      const shell = document.getElementById('action-modal');
      const title = document.getElementById('modal-title');
      const subtitle = document.getElementById('modal-subtitle');
      const description = document.getElementById('modal-description');
      const input = document.getElementById('modal-input');
      const textarea = document.getElementById('modal-textarea');
      const select = document.getElementById('modal-select');
      const error = document.getElementById('modal-error');
      const confirm = document.getElementById('modal-confirm');
      const cancel = document.getElementById('modal-cancel');
      title.textContent = config.title || 'Action';
      subtitle.textContent = config.subtitle || '';
      description.textContent = config.description || '';
      input.hidden = !config.input;
      input.value = config.input?.value || '';
      input.placeholder = config.input?.placeholder || '';
      textarea.hidden = !config.textarea;
      textarea.value = config.textarea?.value || '';
      textarea.placeholder = config.textarea?.placeholder || '';
      select.hidden = !(config.select && config.select.options && config.select.options.length);
      if (!select.hidden) {
        select.innerHTML = config.select.options.map((opt) => `<option value="${opt.value}">${opt.label}</option>`).join('');
        select.value = config.select.value || config.select.options[0].value;
      } else {
        select.innerHTML = '';
      }
      error.textContent = '';
      shell.hidden = false;
      return new Promise((resolve, reject) => {
        const close = () => {
          shell.hidden = true;
          confirm.onclick = null;
          cancel.onclick = null;
        };
        cancel.onclick = () => { close(); reject(new Error('cancelled')); };
        confirm.onclick = () => {
          const payload = { input: input.value.trim(), textarea: textarea.value.trim(), select: select.hidden ? '' : select.value };
          if (config.validate) {
            const maybeError = config.validate(payload);
            if (maybeError) { error.textContent = maybeError; return; }
          }
          close();
          resolve(payload);
        };
      });
    }
    function artifactSummaryItems(items) {
      return (items || []).map((artifact) => `
        <div class="artifact-item">
          <div class="event-meta"><strong>${artifact.artifact_type || 'artifact'}</strong><span>${artifact.artifact_id || 'n/a'}</span></div>
          <div class="muted" style="margin-top:6px">${artifact.uri || 'uri unavailable'}${artifact.content_type ? ` · ${artifact.content_type}` : ''}</div>
        </div>
      `).join('');
    }

    function escapeHtml(value) {
      return String(value || '').replace(/[&<>"']/g, (match) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[match] || match));
    }
    function activeAuthUserId() {
      return document.getElementById('auth-user-id').value.trim() || 'current-user';
    }
    function currentWorkbenchSnapshot() {
      return {
        project_id: document.getElementById('project-filter').value.trim() || null,
        cycle_id: selectedCycleId || selectedCycleInput.value.trim() || null,
        workspace_id: document.getElementById('remote-workspace-id').value.trim() || null,
        query: document.getElementById('discussion-search-filter').value.trim() || null,
        smart_filter: activeSmartFilter,
      };
    }
    function isWorkbenchViewChanged(item) {
      const snap = currentWorkbenchSnapshot();
      return (item.project_id || '') !== (snap.project_id || '') ||
        (item.cycle_id || '') !== (snap.cycle_id || '') ||
        (item.workspace_id || '') !== (snap.workspace_id || '') ||
        (item.query || '') !== (snap.query || '') ||
        ((item.layout || {}).smart_filter || 'all') !== (snap.smart_filter || 'all');
    }
    function findDefaultWorkbenchView() {
      const items = latestWorkbenchViews?.items || [];
      return items.find((item) => item?.layout?.is_default) || null;
    }
    function renderResolutionSummary(data) {
      if (!data) {
        resolutionSummaryEl.innerHTML = '<div class="empty">Resolve a cycle to record a close summary and optional linked discussion resolution.</div>';
        return;
      }
      resolutionSummaryEl.innerHTML = `
        <article class="timeline-item">
          <div class="event-meta"><strong>Resolved cycle</strong><span>${data.cycleId}</span><span>${data.resolvedAt}</span></div>
          <div style="margin-top:8px">${escapeHtml(data.summary)}</div>
          <div class="muted" style="margin-top:8px">actor=${escapeHtml(data.actorId)}${data.linkedDiscussionId ? ` · discussion=${escapeHtml(data.linkedDiscussionId)}` : ''}</div>
        </article>
      `;
    }
    function renderHandoffBundle(data) {
      latestHandoffBundle = data || null;
      if (!data) {
        handoffBundleEl.innerHTML = '<div class="empty">Build a handoff bundle to package status, result, next action, and recent context.</div>';
        return;
      }
      handoffBundleEl.innerHTML = `
        <article class="timeline-item">
          <div class="event-meta"><strong>Handoff bundle</strong><span>${escapeHtml(data.projectId || 'workspace')}</span><span>${escapeHtml(data.cycleId || 'n/a')}</span></div>
          <div style="white-space:pre-wrap;margin-top:8px">${escapeHtml(data.body)}</div>
          <div class="muted" style="margin-top:8px">mentions=${(data.mentions || []).join(', ') || 'none'}${data.target ? ` · target=${escapeHtml(data.target)}` : ''}</div>
        </article>
      `;
    }
    function buildHandoffBody(payload) {
      const lines = [
        `[handoff] ${payload.projectId || 'workspace'} · cycle ${payload.cycleId || 'n/a'}`,
        payload.target ? `target: ${payload.target}` : null,
        `state: ${payload.state || 'n/a'}`,
        payload.resultState ? `latest_result: ${payload.resultState}` : null,
        payload.summary ? `summary: ${payload.summary}` : null,
        payload.nextAction ? `next_action: ${payload.nextAction}` : null,
        payload.assignment ? `assignment: ${payload.assignment}` : null,
        payload.lastComment ? `last_comment: ${payload.lastComment}` : null,
      ].filter(Boolean);
      return lines.join('\n');
    }
    function buildNextStepActions(data, detailedResult) {
      const steps = [];
      const cycle = data?.cycle || {};
      if (data?.active_approval?.approval_id || cycle.approval_required) {
        steps.push({ label: 'Approve pending review', detail: 'Human approval is still blocking progress.', action: 'approve' });
      }
      if (cycle.retry_allowed) {
        steps.push({ label: 'Retry current cycle', detail: 'Verification failed or action is required.', action: 'retry' });
      }
      if (cycle.replan_allowed) {
        steps.push({ label: 'Adjust plan', detail: 'A replan is available for prompt/scope changes.', action: 'replan' });
      }
      if ((detailedResult?.verification?.failed_rules || []).length || cycle.retry_allowed) {
        steps.push({ label: 'Queue remote checks', detail: 'Collect stronger evidence from the remote workspace.', action: 'remote_checks' });
      }
      if (detailedResult?.output_artifacts?.length) {
        steps.push({ label: 'Review result artifacts', detail: 'Artifacts are available from the latest result.', action: 'result' });
      }
      return steps.slice(0, 4);
    }
    function buildReplanOverride() {
      const override = {};
      const prompt = document.getElementById('replan-prompt').value.trim();
      const scope = document.getElementById('replan-scope').value.trim();
      const safety = document.getElementById('replan-safety').value.trim();
      const priority = document.getElementById('replan-priority').value.trim();
      const constraints = document.getElementById('replan-constraints').value.trim();
      if (prompt) override.prompt = prompt;
      if (scope) override.scope = scope;
      if (safety) override.safety_mode = safety;
      if (priority) override.priority = priority;
      if (constraints) override.constraints = constraints.split('\n').map((item) => item.trim()).filter(Boolean);
      return override;
    }
    function cardHtml(item) {
      const statusPills = [
        `<span class="pill">state: ${item.state}</span>`,
        `<span class="pill">user: ${item.user_status}</span>`,
        item.approval_required ? '<span class="pill">approval</span>' : '',
        item.retry_allowed ? '<span class="pill">retry</span>' : '',
        item.replan_allowed ? '<span class="pill">replan</span>' : '',
      ].join(' ');
      return `
        <button class="card ${item.cycle_id === selectedCycleId ? 'selected' : ''}" data-cycle-id="${item.cycle_id}">
          <div>
            <strong>${item.project_id}</strong>
            <div class="muted" style="margin-top:4px">${item.cycle_id}</div>
          </div>
          <div class="meta">${statusPills}</div>
          <div class="meta"><span>${relativeTime(item.updated_at)}</span><span>iteration ${item.latest_iteration_no}</span></div>
        </button>
      `;
    }
    function renderBoard(board) {
      latestBoardData = board;
      boardTotalEl.textContent = `${board.total_count} cycles`;
      boardColumnsEl.innerHTML = board.columns.map(column => `
        <section class="column">
          <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
            <div>
              <h3>${column.title}</h3>
              <small>${column.description || ''}</small>
            </div>
            <span class="count">${column.count}</span>
          </div>
          ${column.items.length ? column.items.map(cardHtml).join('') : '<div class="empty">No cycles in this column.</div>'}
        </section>
      `).join('');
      document.querySelectorAll('[data-cycle-id]').forEach((button) => {
        button.addEventListener('click', () => selectCycle(button.dataset.cycleId));
      });
      lastSyncEl.textContent = `Last board update: ${nowLabel()}`;
    }
    function pushStreamItem(eventName, payload) {
      const wrapper = document.createElement('div');
      wrapper.className = 'stream-item';
      wrapper.innerHTML = `<div class="event-meta"><strong>${eventName}</strong><span>${nowLabel()}</span></div><pre>${JSON.stringify(payload, null, 2)}</pre>`;
      streamLogEl.prepend(wrapper);
      while (streamLogEl.children.length > 24) streamLogEl.removeChild(streamLogEl.lastChild);
    }
    function renderWorkspace(data) {
      setStatus(workspaceStateEl, `${data.projects.length} projects`);
      workspaceEl.innerHTML = `
        <article class="timeline-item">
          <div class="event-meta"><strong>Workspace totals</strong><span>${relativeTime(data.generated_at)}</span></div>
          <div style="margin-top:8px">cycles=${data.totals.cycles} · active=${data.totals.active} · review=${data.totals.pending_reviews} · completed=${data.totals.completed} · failed=${data.totals.failed}</div>
        </article>
      ` + (data.projects.length ? data.projects.map((project) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${project.project_id}</strong><span>${relativeTime(project.updated_at)}</span></div>
          <div style="margin-top:8px">active=${project.active_cycles} · review=${project.pending_reviews} · done=${project.completed_cycles} · failed=${project.failed_cycles}</div>
        </article>
      `).join('') : '<div class="empty">No projects in scope.</div>') + (data.recent_comments.length ? data.recent_comments.map((comment) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>Comment · ${comment.cycle_id}</strong><span>${relativeTime(comment.occurred_at)}</span></div>
          <div style="margin-top:8px">${comment.body}</div>
        </article>
      `).join('') : '');
    }
    function renderAgentRoster(data) {
      agentRosterEl.innerHTML = data.items.length ? data.items.map((agent) => `
        <article class="runtime-item">
          <strong>${agent.name}</strong>
          <div class="muted">${agent.persona}</div>
          <div class="event-meta" style="margin-top:8px"><span>${agent.status}</span><span>load=${agent.current_load}</span>${agent.focus ? `<span>focus=${agent.focus}</span>` : ''}</div>
          <div style="margin-top:8px">${agent.specialties.join(' · ')}</div>
        </article>
      `).join('') : '<div class="empty">No agent profiles.</div>';
    }
    function renderRuntimePanel(data) {
      const metrics = data.queue_metrics.map((metric) => `
        <article class="runtime-item">
          <strong>${metric.label}</strong>
          <div>${metric.value}</div>
          ${metric.detail ? `<div class="muted" style="margin-top:6px">${metric.detail}</div>` : ''}
        </article>
      `).join('');
      const jobs = data.recent_jobs.map((job) => `
        <article class="runtime-item">
          <strong>${job.title}</strong>
          <div class="event-meta"><span>${job.status || ''}</span><span>${relativeTime(job.occurred_at)}</span></div>
          ${job.detail ? `<div style="margin-top:8px">${job.detail}</div>` : ''}
        </article>
      `).join('');
      const signals = (data.signals || []).map((signal) => `<article class="runtime-item"><strong>Signal</strong><div>${signal}</div></article>`).join('');
      runtimePanelEl.innerHTML = metrics + jobs + signals || '<div class="empty">Runtime is idle.</div>';
    }
    function renderIssueCard(data) {
      latestIssueCardData = data || null;
      const detailedResult = data.detailed_result || data.result || null;
      const result = detailedResult ? `<div class="section-divider"></div>
        <div class="stack-xs">
          <div class="event-meta"><strong>Latest result</strong><span>${detailedResult.final_state || 'n/a'}</span><span>${relativeTime(detailedResult.generated_at || data.cycle.updated_at)}</span></div>
          <div>${detailedResult.summary || 'No summary yet.'}</div>
          <div class="muted">verification=${detailedResult.verification?.status || 'n/a'}${(detailedResult.verification?.failed_rules || []).length ? ` · failed_rules=${detailedResult.verification.failed_rules.join(', ')}` : ''}</div>
          <div class="muted">approval=${detailedResult.approval?.state || (detailedResult.approval?.required ? 'required' : 'n/a')}</div>
          ${(detailedResult.output_artifacts || []).length ? `<div class="artifact-list">${artifactSummaryItems(detailedResult.output_artifacts)}</div>` : '<div class="muted">No output artifacts recorded yet.</div>'}
        </div>` : '<div class="section-divider"></div><div class="muted">No final result recorded yet.</div>';
      const approval = data.active_approval ? `<div class="muted" style="margin-top:8px">approval=${data.active_approval.state || 'required'} (${data.active_approval.approval_id || 'pending'})</div>` : '';
      const assignment = data.current_assignment ? `<div class="muted" style="margin-top:8px">assigned=${data.current_assignment.agent_id} · role=${data.current_assignment.assignment_role}${data.current_assignment.note ? ` · ${data.current_assignment.note}` : ''}</div>` : '';
      const cycleActions = [
        data.cycle.approval_required ? '<span class="pill">approval required</span>' : '',
        data.cycle.retry_allowed ? '<span class="pill">retry ready</span>' : '',
        data.cycle.replan_allowed ? '<span class="pill">replan ready</span>' : '',
      ].filter(Boolean).join(' ');
      const suggestionMeta = (data.assignment_suggestions || []).length
        ? `<div class="muted" style="margin-top:8px">suggested agents=${(data.assignment_suggestions || []).map((item) => `${item.agent_id}:${item.recommended_role}:${item.learned_weight ?? 0}`).join(', ')}</div>`
        : `<div class="muted" style="margin-top:8px">suggested agents=${(data.suggested_agents || []).join(', ') || 'n/a'}</div>`;
      const nextSteps = buildNextStepActions(data, detailedResult);
      const nextStepsHtml = nextSteps.length ? nextSteps.map((step) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${step.label}</strong><span>${step.action}</span></div>
          <div class="muted" style="margin-top:8px">${step.detail}</div>
          <div class="inline-actions" style="margin-top:10px">
            <button class="secondary next-step-btn" data-next-action="${step.action}">Run</button>
          </div>
        </article>
      `).join('') : '<div class="empty">No follow-up action is recommended yet.</div>';
      const preview = (data.timeline_preview || []).slice(0, 3).map((event) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${event.title}</strong><span>${event.source}</span><span>${relativeTime(event.occurred_at)}</span></div>
          ${event.detail ? `<div style="margin-top:8px">${event.detail}</div>` : ''}
        </article>
      `).join('') || '<div class="empty">No timeline preview available.</div>';
      document.getElementById('issue-action-cycle-id').value = data.cycle.cycle_id || '';
      document.getElementById('issue-action-approval-id').value = data.active_approval?.approval_id || '';
      issueCardEl.innerHTML = `
        <article class="timeline-item">
          <div class="event-meta"><strong>${data.cycle.project_id}</strong><span>${data.cycle.state}</span><span>${relativeTime(data.cycle.updated_at)}</span></div>
          <div style="margin-top:8px">cycle=${data.cycle.cycle_id}</div>
          ${cycleActions ? `<div class="meta" style="margin-top:8px">${cycleActions}</div>` : ''}
          ${suggestionMeta}
          <div class="muted" style="margin-top:8px">active jobs=${data.active_job_count} · comments=${data.comment_count}</div>
          ${approval}
          ${assignment}
          ${result}
        </article>
        <article class="timeline-item">
          <div class="event-meta"><strong>Suggested next steps</strong><span>${nextSteps.length} actions</span></div>
          <div class="timeline" style="max-height:none;margin-top:10px">${nextStepsHtml}</div>
        </article>
      ` + preview;
    }
    function renderWorkspaceDiscussions(data) {
      const mentionInfo = data.mention_filter ? `<div class="empty">Filter: ${data.mention_filter}</div>` : '';
      const items = data.items.length ? data.items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.project_id || 'workspace'}</strong><span>${item.actor_role || ''}</span><span>${relativeTime(item.last_updated_at || item.occurred_at)}</span></div>
          <div style="margin-top:8px">${item.body}</div>
          <div class="muted" style="margin-top:8px">replies=${item.reply_count || 0} · resolved=${item.is_resolved ? 'yes' : 'no'} · pinned=${item.is_pinned ? 'yes' : 'no'}</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
            <button class="secondary select-discussion-btn" data-discussion-id="${item.discussion_id}">Open thread</button>
            <button class="secondary discussion-resolve-btn" data-discussion-id="${item.discussion_id}" data-next-resolved="${item.is_resolved ? 'false' : 'true'}">${item.is_resolved ? 'Reopen' : 'Resolve'}</button>
            <button class="secondary discussion-pin-btn" data-discussion-id="${item.discussion_id}" data-next-pinned="${item.is_pinned ? 'false' : 'true'}">${item.is_pinned ? 'Unpin' : 'Pin'}</button>
          </div>
        </article>
      `).join('') : '<div class="empty">No workspace discussions yet.</div>';
      latestDiscussionData = data || { items: [] };
      workspaceDiscussionsEl.innerHTML = mentionInfo + items;
      renderPersonalInbox();
    }
    function renderWorkspaceDiscussionGroups(data) {
      workspaceDiscussionGroupsEl.innerHTML = data.items.length ? data.items.map((group) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${group.label}</strong><span>threads=${group.total_count}</span><span>${relativeTime(group.last_updated_at)}</span></div>
          <div class="muted" style="margin-top:8px">open=${group.unresolved_count} · resolved=${group.resolved_count} · pinned=${group.pinned_count}</div>
          ${(group.items || []).length ? `<div class="muted" style="margin-top:8px">preview=${group.items.map((item) => item.discussion_id.slice(0, 8)).join(', ')}</div>` : ''}
        </article>
      `).join('') : '<div class="empty">No grouped discussions yet.</div>';
    }
    function renderSavedDiscussionFilters(data) {
      savedDiscussionFiltersEl.innerHTML = data.items.length ? data.items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.name}</strong><span>${item.is_favorite ? '★ favorite' : 'saved'}</span><span>${relativeTime(item.last_used_at || item.updated_at || item.occurred_at)}</span></div>
          <div class="muted" style="margin-top:8px">project=${item.project_id || 'all'} · mention=${item.mention || 'any'} · query=${item.query || 'none'}</div>
          <div class="muted" style="margin-top:8px">updated=${relativeTime(item.updated_at || item.occurred_at)}${item.last_used_at ? ` · last used=${relativeTime(item.last_used_at)}` : ''}</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
            <button class="secondary apply-saved-discussion-filter-btn" data-filter-id="${item.filter_id}" data-project-id="${item.project_id || ''}" data-mention="${item.mention || ''}" data-query="${item.query || ''}">Apply filter</button>
            <button class="secondary rename-saved-discussion-filter-btn" data-filter-id="${item.filter_id}" data-name="${item.name}" data-project-id="${item.project_id || ''}" data-mention="${item.mention || ''}" data-query="${item.query || ''}">Rename</button>
            <button class="secondary favorite-saved-discussion-filter-btn" data-filter-id="${item.filter_id}" data-is-favorite="${item.is_favorite ? 'false' : 'true'}">${item.is_favorite ? 'Unfavorite' : 'Favorite'}</button>
            <button class="secondary delete-saved-discussion-filter-btn" data-filter-id="${item.filter_id}">Delete</button>
          </div>
        </article>
      `).join('') : '<div class="empty">No saved discussion filters yet.</div>';
    }
    function renderRemoteWorkspaceExecutors(data) {
      remoteWorkspaceExecutorsEl.innerHTML = data.items.length ? data.items.map((item) => `
        <article class="timeline-item"><div class="event-meta"><strong>${item.name}</strong><span>${item.key}</span><span>${item.mode}</span><span>${item.enabled ? 'enabled' : 'planned'}</span></div><div class="muted" style="margin-top:8px">${item.description}</div><div class="muted" style="margin-top:8px">capabilities=${(item.capabilities || []).join(', ') || 'none'}</div></article>
      `).join('') : '<div class="empty">No executors available.</div>';
    }
    function renderRemoteWorkspaceSnapshots(data) {
      remoteWorkspaceSnapshotsEl.innerHTML = data.items.length ? data.items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.workspace_id}</strong><span>${item.last_execution_status || 'parked'}</span><span>${relativeTime(item.updated_at)}</span></div>
          <div class="muted" style="margin-top:8px">project=${item.project_id || 'n/a'} · branch=${item.repo_branch || 'n/a'} · executor=${item.executor_key || 'planning'}</div>
          <div class="muted" style="margin-top:8px">repo=${item.repo_url || 'unset'}${item.patch_present ? ' · patch attached' : ''}</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px"><button class="secondary select-remote-workspace-btn" data-workspace-id="${item.workspace_id}" data-repo-url="${item.repo_url || ''}" data-repo-branch="${item.repo_branch || ''}">Open workspace</button></div>
        </article>
      `).join('') : '<div class="empty">No remote workspace snapshots yet.</div>';
    }
    function renderRemoteWorkspaceExecutions(data) {
      remoteWorkspaceExecutionsEl.innerHTML = data.items.length ? data.items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.execution_kind}</strong><span>${item.status}</span><span>${item.executor_key}</span><span>${relativeTime(item.last_updated_at || item.requested_at)}</span></div>
          ${item.message ? `<div style="margin-top:8px">${item.message}</div>` : ''}
          <div class="muted" style="margin-top:8px">command=${item.command || 'default'}${item.result_summary ? ` · result=${item.result_summary}` : ''}</div>
          ${(item.logs_url || item.external_url) ? `<div class="muted" style="margin-top:8px">${item.logs_url ? `logs=${item.logs_url}` : ''}${item.external_url ? `${item.logs_url ? ' · ' : ''}external=${item.external_url}` : ''}</div>` : ''}
          ${(item.artifacts || []).length ? `<div class="muted" style="margin-top:8px">artifacts=${item.artifacts.map((artifact) => artifact.artifact_type).join(', ')}</div>` : ''}
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
            <button class="secondary inspect-remote-execution-btn" data-execution-id="${item.execution_id}">Inspect</button>
            ${item.can_cancel ? `<button class="secondary cancel-remote-execution-btn" data-execution-id="${item.execution_id}">Cancel</button>` : ''}
          </div>
        </article>
      `).join('') : '<div class="empty">No remote executions yet.</div>';
    }
    function renderRemoteWorkspaceExecutionDetail(item) {
      if (!item) {
        remoteWorkspaceExecutionDetailEl.innerHTML = '<div class="empty">Inspect a remote execution to see result summary, timing, and artifacts.</div>';
        return;
      }
      remoteWorkspaceExecutionDetailEl.innerHTML = `
        <article class="timeline-item">
          <div class="event-meta"><strong>Execution detail</strong><span>${item.execution_id}</span><span>${item.status}</span></div>
          <div class="info-grid">
            <div class="info-chip"><strong>Kind</strong><span>${item.execution_kind || 'n/a'}</span></div>
            <div class="info-chip"><strong>Executor</strong><span>${item.executor_key || 'n/a'}</span></div>
            <div class="info-chip"><strong>Command</strong><span>${item.command || 'default'}</span></div>
            <div class="info-chip"><strong>Exit code</strong><span>${item.exit_code ?? 'n/a'}</span></div>
            <div class="info-chip"><strong>Started</strong><span>${item.started_at ? relativeTime(item.started_at) : 'n/a'}</span></div>
            <div class="info-chip"><strong>Completed</strong><span>${item.completed_at ? relativeTime(item.completed_at) : 'n/a'}</span></div>
          </div>
          <div class="section-divider"></div>
          <div>${item.result_summary || item.message || 'No execution summary yet.'}</div>
          ${(item.logs_url || item.external_url) ? `<div class="muted" style="margin-top:8px">${item.logs_url ? `logs=${item.logs_url}` : ''}${item.external_url ? `${item.logs_url ? ' · ' : ''}external=${item.external_url}` : ''}</div>` : ''}
          ${(item.artifacts || []).length ? `<div class="artifact-list">${artifactSummaryItems(item.artifacts)}</div>` : '<div class="muted" style="margin-top:8px">No artifacts collected for this execution.</div>'}
        </article>
      `;
    }
    function renderPersistentWorkspaceSessions(data) {
      persistentWorkspaceSessionsEl.innerHTML = (data?.items || []).length ? data.items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.workspace_id}</strong><span>${item.status}</span><span>${item.provider}</span><span>${relativeTime(item.updated_at)}</span></div>
          <div class="muted" style="margin-top:8px">project=${item.project_id || 'n/a'} · branch=${item.repo_branch || 'n/a'} · expires=${item.expires_at ? relativeTime(item.expires_at) : 'n/a'}</div>
          ${item.note ? `<div style="margin-top:8px">${item.note}</div>` : ''}
          <div class="inline-actions" style="margin-top:10px">
            <button class="secondary use-persistent-session-btn" data-workspace-id="${item.workspace_id}" data-repo-url="${item.repo_url || ''}" data-repo-branch="${item.repo_branch || ''}">Open session</button>
            ${item.hibernate_supported && item.status !== 'hibernated' ? `<button class="secondary hibernate-persistent-session-btn" data-workspace-id="${item.workspace_id}">Hibernate</button>` : ''}
            <button class="secondary delete-persistent-session-btn" data-workspace-id="${item.workspace_id}">Delete</button>
          </div>
        </article>
      `).join('') : '<div class="empty">No persistent sessions yet.</div>';
    }
    function renderAuditExplorer(data) {
      auditExplorerEl.innerHTML = data.events && data.events.length ? data.events.map((item) => `
        <article class="timeline-item"><div class="event-meta"><strong>${item.event_type}</strong><span>${item.actor_id || 'system'}</span><span>${relativeTime(item.occurred_at)}</span></div><div class="muted" style="margin-top:8px">event=${item.audit_event_id || 'n/a'} · payload=${JSON.stringify(item.event_payload || {})}</div></article>
      `).join('') : '<div class="empty">No audit events found.</div>';
    }


    function renderRemoteWorkspaceResume(data) {
      if (!data) {
        remoteWorkspaceResumeEl.innerHTML = '<div class="empty">Select or save a remote workspace snapshot to view resume memory.</div>';
        return;
      }
      const artifacts = (data.artifacts || []).map((item) => `${item.artifact_type}:${item.artifact_id}`).join(', ');
      remoteWorkspaceResumeEl.innerHTML = `
        <article class="timeline-item">
          <div class="event-meta"><strong>Resume memory</strong><span>${data.workspace_id}</span><span>resumes=${data.resume_count || 0}</span></div>
          <div class="muted" style="margin-top:8px">last failed=${data.last_failed_command || 'n/a'} · summary=${data.last_result_summary || 'n/a'}</div>
          <div class="muted" style="margin-top:8px">patch stack=${(data.patch_stack || []).length} · artifacts=${artifacts || 'none'}</div>
        </article>`;
    }

    function renderWorkbenchSavedViews(data) {
      latestWorkbenchViews = data || { items: [] };
      workbenchSavedViewsEl.innerHTML = (data.items || []).length ? data.items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.name}</strong><span>${item.project_id || 'global'}</span><span>${relativeTime(item.last_used_at || item.updated_at)}</span></div>
          <div class="meta" style="margin-top:8px">${item.layout?.is_default ? '<span class="pill">default</span>' : ''}${item.layout?.smart_filter ? `<span class="pill">${item.layout.smart_filter}</span>` : ''}${isWorkbenchViewChanged(item) ? '<span class="pill">changed</span>' : ''}</div>
          <div class="muted" style="margin-top:8px">workspace=${item.workspace_id || 'n/a'} · cycle=${item.cycle_id || 'n/a'} · panels=${(item.selected_panels || []).join(', ') || 'default'} · use=${item.use_count || 0}</div>
          <div class="muted" style="margin-top:8px">notes=${item.notes || 'none'}</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
            <button class="secondary use-workbench-view-btn" data-view-id="${item.view_id}">Apply</button>
            <button class="secondary set-default-workbench-view-btn" data-view-id="${item.view_id}">${item.layout?.is_default ? 'Default view' : 'Set default'}</button>
            <button class="secondary rename-workbench-view-btn" data-view-id="${item.view_id}" data-view-name="${escapeHtml(item.name)}" data-view-notes="${escapeHtml(item.notes || '')}">Rename</button>
            <button class="secondary delete-workbench-view-btn" data-view-id="${item.view_id}">Delete</button>
          </div>
        </article>`).join('') : '<div class="empty">No saved workbench views yet.</div>';
    }

    function renderDiscussionReplies(data) {
      const replyMentionInfo = data.mention_filter ? `<div class="empty">Filter: ${data.mention_filter}</div>` : '';
      const items = data.items.length ? data.items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.actor_id || 'unknown'}</strong><span>${item.actor_role || ''}</span><span>${relativeTime(item.occurred_at)}</span></div>
          <div style="margin-top:8px">${item.body}</div>
          ${item.mentions.length ? `<div class="muted" style="margin-top:8px">mentions=${item.mentions.join(', ')}</div>` : ''}
          ${(item.search_rank || 0) > 0 ? `<div class="muted" style="margin-top:8px">rank=${item.search_rank} · matched=${(item.matched_terms || []).join(', ')}</div>` : ''}
        </article>
      `).join('') : '<div class="empty">No replies yet.</div>';
      discussionRepliesEl.innerHTML = replyMentionInfo + items;
    }
    function renderRuntimeRegistrations(data) {
      runtimeRegistrationsEl.innerHTML = data.items.length ? data.items.map((item) => `
        <article class="runtime-item">
          <strong>${item.label}</strong>
          <div>${item.runtime_id}</div>
          <div class="muted">${item.mode} · ${item.status}${item.version ? ` · ${item.version}` : ''}</div>
          <div class="muted">${relativeTime(item.occurred_at)}</div>
          <button class="secondary select-runtime-btn" data-runtime-id="${item.runtime_id}" style="margin-top:10px">Open action panel</button>
        </article>
      `).join('') : '<div class="empty">No runtime registrations yet.</div>';
    }
    function renderRuntimeActions(data) {
      runtimeActionsEl.innerHTML = data.items.length ? data.items.map((item) => `
        <article class="runtime-item">
          <strong>${item.action}</strong>
          <div class="muted">${item.status} · ${relativeTime(item.last_updated_at || item.occurred_at)}</div>
          ${item.note ? `<div style="margin-top:8px">${item.note}</div>` : ''}
          ${item.latest_receipt_summary ? `<div class="muted" style="margin-top:8px">receipt=${item.latest_receipt_status || 'recorded'} · ${item.latest_receipt_summary}</div>` : ''}
          ${Object.keys(item.arguments || {}).length ? `<div style="margin-top:8px">${JSON.stringify(item.arguments)}</div>` : ''}
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
            <button class="secondary select-runtime-action-btn" data-action-id="${item.action_id}">Open receipts</button>
            <button class="secondary add-runtime-receipt-btn" data-action-id="${item.action_id}">Add receipt</button>
            ${item.status === 'queued' ? `<button class="secondary ack-runtime-action-btn" data-action-id="${item.action_id}">Acknowledge</button>` : ''}
            ${['queued','acknowledged'].includes(item.status) ? `<button class="secondary transition-runtime-action-btn" data-action-id="${item.action_id}" data-next-status="running">Mark running</button>` : ''}
            ${['queued','acknowledged','running'].includes(item.status) ? `<button class="secondary transition-runtime-action-btn" data-action-id="${item.action_id}" data-next-status="succeeded">Mark done</button>` : ''}
            ${['queued','acknowledged','running'].includes(item.status) ? `<button class="secondary transition-runtime-action-btn" data-action-id="${item.action_id}" data-next-status="failed">Mark failed</button>` : ''}
          </div>
        </article>
      `).join('') : '<div class="empty">No runtime actions yet.</div>';
    }
    function renderRuntimeActionTimeline(data) {
      runtimeActionTimelineEl.innerHTML = data.items.length ? data.items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.title}</strong><span>${item.status || item.event_type}</span><span>${relativeTime(item.occurred_at)}</span></div>
          ${item.detail ? `<div style="margin-top:8px">${item.detail}</div>` : ''}
        </article>
      `).join('') : '<div class="empty">No runtime action timeline yet.</div>';
    }

    function renderRuntimeActionReceipts(data) {
      runtimeActionReceiptsEl.innerHTML = data.items.length ? data.items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.status || 'receipt'}</strong><span>${relativeTime(item.occurred_at)}</span></div>
          <div style="margin-top:8px">${item.summary}</div>
          ${Object.keys(item.metadata || {}).length ? `<div class="muted" style="margin-top:8px">${JSON.stringify(item.metadata)}</div>` : ''}
        </article>
      `).join('') : '<div class="empty">No runtime action receipts yet.</div>';
    }

    function renderAssignmentSuggestions(data) {
      assignmentSuggestionsEl.innerHTML = data.items.length ? data.items.map((item) => `
        <article class="runtime-item">
          <strong>${item.name}</strong>
          <div class="muted">${item.agent_id} · role=${item.recommended_role} · score=${item.score}</div>
          <div style="margin-top:8px">${item.rationale}</div>
          <div class="muted" style="margin-top:8px">load=${item.current_load} · pressure=${item.queue_pressure}${item.capacity_hint ? ` · ${item.capacity_hint}` : ''}</div>
          ${item.last_feedback ? `<div class="muted" style="margin-top:8px">feedback=${item.last_feedback}${item.feedback_note ? ` · ${item.feedback_note}` : ''}</div>` : ''}
          <div class="muted" style="margin-top:8px">learned=${item.learned_weight} · recency=${item.recency_weight || 0}</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
            <button class="secondary use-assignment-suggestion-btn" data-agent-id="${item.agent_id}" data-role="${item.recommended_role}" data-note="${item.autofill_note || ''}">Use suggestion</button>
            <button class="secondary assignment-feedback-btn" data-agent-id="${item.agent_id}" data-feedback="accepted">Accept</button>
            <button class="secondary assignment-feedback-btn" data-agent-id="${item.agent_id}" data-feedback="dismissed">Dismiss</button>
          </div>
        </article>
      `).join('') : '<div class="empty">No assignment suggestions available.</div>';
    }

    function renderAssignmentLearningWeights(data) {
      assignmentLearningWeightsEl.innerHTML = data.items.length ? data.items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.name}</strong><span>${item.agent_id}</span><span>weight=${item.learned_weight}</span><span>recency=${item.recency_weight || 0}</span></div>
          <div class="muted" style="margin-top:8px">accepted=${item.accepted_count} · applied=${item.applied_count} · dismissed=${item.dismissed_count}</div>
          <div class="muted" style="margin-top:8px">${item.rationale}</div>
        </article>
      `).join('') : '<div class="empty">No learning weights yet.</div>';
    }

    function renderAssignments(data) {
      cycleAssignmentsEl.innerHTML = data.items.length ? data.items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.agent_id}</strong><span>${item.assignment_role}</span><span>${relativeTime(item.occurred_at)}</span></div>
          ${item.note ? `<div style="margin-top:8px">${item.note}</div>` : ''}
          <div class="muted" style="margin-top:8px">assigned by ${item.actor_id || 'unknown'}</div>
        </article>
      `).join('') : '<div class="empty">No assignments yet.</div>';
    }

    function renderComments(data) {
      commentsListEl.innerHTML = data.items.length ? data.items.map((comment) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${comment.actor_id || 'unknown'}</strong><span>${comment.actor_role || ''}</span><span>${relativeTime(comment.occurred_at)}</span></div>
          <div style="margin-top:8px">${comment.body}</div>
          ${comment.mentions.length ? `<div class="muted" style="margin-top:8px">mentions=${comment.mentions.join(', ')}</div>` : ''}
        </article>
      `).join('') : '<div class="empty">No comments yet.</div>';
    }
    function renderPendingApprovals(data) {
      latestPendingApprovalData = data || { items: [] };
      pendingApprovalsEl.innerHTML = data.items.length ? data.items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.project_id}</strong><span>${item.cycle_id}</span><span>expires ${relativeTime(item.expires_at)}</span></div>
          <div class="muted" style="margin-top:8px">approval=${item.approval_id} · role=${item.required_role} · state=${item.cycle_state}</div>
          <div class="inline-actions" style="margin-top:10px">
            <button class="secondary review-pending-approval-btn" data-cycle-id="${item.cycle_id}" data-approval-id="${item.approval_id}">Review context</button>
            <button class="secondary use-pending-approval-btn" data-cycle-id="${item.cycle_id}" data-approval-id="${item.approval_id}">Use in issue actions</button>
            <button class="secondary open-pending-cycle-btn" data-cycle-id="${item.cycle_id}">Open cycle</button>
            <button class="secondary quick-approve-btn" data-cycle-id="${item.cycle_id}" data-approval-id="${item.approval_id}">Approve</button>
            <button class="secondary quick-reject-btn" data-cycle-id="${item.cycle_id}" data-approval-id="${item.approval_id}">Reject</button>
          </div>
        </article>
      `).join('') : '<div class="empty">No pending approvals for the current user.</div>';
      renderPersonalInbox();
    }


    function smartFilterPredicate(filterKey, item) {
      if (!item) return false;
      if (filterKey === 'pending_approval') return item.type === 'approval' || item.approval_required;
      if (filterKey === 'retry_ready') return item.retry_allowed === true;
      if (filterKey === 'stale') {
        const updated = new Date(item.updated_at || item.last_updated_at || item.occurred_at || 0).getTime();
        return updated && (Date.now() - updated) > (24 * 60 * 60 * 1000);
      }
      if (filterKey === 'mentions') return item.type === 'discussion';
      return true;
    }
    function renderPersonalInbox() {
      const boardItems = (latestBoardData?.columns || []).flatMap((column) => (column.items || []).map((item) => ({ ...item, type: 'cycle' })));
      const approvalItems = (latestPendingApprovalData?.items || []).map((item) => ({
        type: 'approval',
        cycle_id: item.cycle_id,
        approval_id: item.approval_id,
        project_id: item.project_id,
        updated_at: item.expires_at,
        approval_required: true,
        title: `Approval needed · ${item.project_id}`,
        detail: `${item.required_role} · expires ${relativeTime(item.expires_at)}`,
      }));
      const mentionItems = (latestDiscussionData?.items || []).filter((item) => (item.mentions || []).length > 0).map((item) => ({
        type: 'discussion',
        discussion_id: item.discussion_id,
        project_id: item.project_id || 'workspace',
        updated_at: item.last_updated_at || item.occurred_at,
        title: `Mention thread · ${item.project_id || 'workspace'}`,
        detail: item.body,
      }));
      const dedup = new Map();
      [...approvalItems, ...boardItems, ...mentionItems].forEach((item) => {
        const key = `${item.type}:${item.approval_id || item.cycle_id || item.discussion_id || item.project_id}`;
        if (!dedup.has(key)) dedup.set(key, item);
      });
      const items = [...dedup.values()].filter((item) => smartFilterPredicate(activeSmartFilter, item)).slice(0, 12);
      personalInboxCountEl.textContent = `${items.length} items`;
      personalInboxEl.innerHTML = items.length ? items.map((item) => `
        <article class="timeline-item">
          <div class="event-meta"><strong>${item.title || item.project_id || item.cycle_id || 'item'}</strong><span>${item.type}</span><span>${relativeTime(item.updated_at || new Date().toISOString())}</span></div>
          <div class="muted" style="margin-top:8px">${item.detail || `cycle=${item.cycle_id || 'n/a'}${item.user_status ? ` · user=${item.user_status}` : ''}${item.state ? ` · state=${item.state}` : ''}`}</div>
          <div class="inline-actions" style="margin-top:10px">
            ${item.cycle_id ? `<button class="secondary inbox-open-cycle-btn" data-cycle-id="${item.cycle_id}">Open cycle</button>` : ''}
            ${item.approval_id ? `<button class="secondary inbox-review-approval-btn" data-cycle-id="${item.cycle_id}" data-approval-id="${item.approval_id}">Review approval</button>` : ''}
            ${item.discussion_id ? `<button class="secondary inbox-open-discussion-btn" data-discussion-id="${item.discussion_id}">Open thread</button>` : ''}
          </div>
        </article>
      `).join('') : '<div class="empty">No inbox items for the current smart filter.</div>';
    }
    function renderApprovalReviewContext(data) {
      if (!data) {
        approvalReviewContextEl.innerHTML = '<div class="empty">Select a pending approval to review timeline, result, comments, and assignment context.</div>';
        return;
      }
      const timeline = (data.timeline?.events || []).slice(0, 4).map((event) => `<article class="timeline-item"><div class="event-meta"><strong>${event.title}</strong><span>${event.status || event.source}</span><span>${relativeTime(event.occurred_at)}</span></div>${event.detail ? `<div style="margin-top:8px">${event.detail}</div>` : ''}</article>`).join('') || '<div class="empty">No timeline entries.</div>';
      const comments = (data.comments?.items || []).slice(0, 3).map((comment) => `<article class="timeline-item"><div class="event-meta"><strong>${comment.actor_id || 'unknown'}</strong><span>${comment.actor_role || ''}</span><span>${relativeTime(comment.occurred_at)}</span></div><div style="margin-top:8px">${comment.body}</div></article>`).join('') || '<div class="empty">No comments yet.</div>';
      const result = data.result ? `<article class="timeline-item"><div class="event-meta"><strong>Latest result</strong><span>${data.result.final_state || 'n/a'}</span><span>${relativeTime(data.result.generated_at || data.card?.cycle?.updated_at)}</span></div><div style="margin-top:8px">${data.result.summary || 'No summary yet.'}</div><div class="muted" style="margin-top:8px">verification=${data.result.verification?.status || 'n/a'}${(data.result.verification?.failed_rules || []).length ? ` · failed=${data.result.verification.failed_rules.join(', ')}` : ''}</div></article>` : '<div class="empty">No result recorded yet.</div>';
      const assignment = data.card?.current_assignment ? `<article class="timeline-item"><div class="event-meta"><strong>Current assignment</strong><span>${data.card.current_assignment.agent_id}</span><span>${data.card.current_assignment.assignment_role}</span></div><div style="margin-top:8px">${data.card.current_assignment.note || 'No assignment note.'}</div></article>` : '<div class="empty">No active assignment.</div>';
      approvalReviewContextEl.innerHTML = `
        <article class="timeline-item">
          <div class="event-meta"><strong>${data.card?.cycle?.project_id || 'approval review'}</strong><span>${data.approvalId || 'n/a'}</span><span>${data.card?.active_approval?.state || 'pending'}</span></div>
          <div class="muted" style="margin-top:8px">cycle=${data.cycleId} · comments=${data.card?.comment_count || 0} · jobs=${data.card?.active_job_count || 0}</div>
          <div class="inline-actions" style="margin-top:10px">
            <button class="secondary approval-review-open-cycle-btn" data-cycle-id="${data.cycleId}">Open cycle</button>
            <button class="secondary approval-review-approve-btn" data-cycle-id="${data.cycleId}" data-approval-id="${data.approvalId}">Approve</button>
            <button class="secondary approval-review-reject-btn" data-cycle-id="${data.cycleId}" data-approval-id="${data.approvalId}">Reject</button>
          </div>
        </article>
        ${result}
        ${assignment}
        <article class="timeline-item"><div class="event-meta"><strong>Recent timeline</strong><span>${(data.timeline?.events || []).length} events</span></div><div class="timeline" style="max-height:none;margin-top:10px">${timeline}</div></article>
        <article class="timeline-item"><div class="event-meta"><strong>Recent comments</strong><span>${(data.comments?.items || []).length} items</span></div><div class="timeline" style="max-height:none;margin-top:10px">${comments}</div></article>
      `;
    }
    async function reviewPendingApproval(cycleId, approvalId) {
      selectedApprovalReviewId = approvalId;
      document.getElementById('issue-action-cycle-id').value = cycleId || '';
      document.getElementById('issue-action-approval-id').value = approvalId || '';
      const [card, result, comments, timeline] = await Promise.all([
        apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/card`),
        apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/result`).catch(() => null),
        apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/comments`).catch(() => ({ items: [] })),
        apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/timeline`).catch(() => ({ events: [] })),
      ]);
      renderApprovalReviewContext({ cycleId, approvalId, card, result, comments, timeline });
      showToast(`Loaded approval ${approvalId} review context.`, 'success', 'Approval');
    }
    async function refreshPendingApprovals() {
      try {
        const projectId = document.getElementById('project-filter').value.trim();
        const data = await apiJson(`/v1/approvals/pending${qs({ project_id: projectId, limit: 12 })}`);
        renderPendingApprovals(data);
      } catch (error) {
        pendingApprovalsEl.innerHTML = `<div class="empty">${error.message}</div>`;
      }
    }
    function renderTimeline(data) {
      timelineEl.innerHTML = data.events.length ? data.events.map((event) => `
        <article class="timeline-item">
          <div class="event-meta">
            <strong>${event.title}</strong>
            <span>${event.source}</span>
            ${event.status ? `<span>${event.status}</span>` : ''}
            <span>${relativeTime(event.occurred_at)}</span>
          </div>
          ${event.detail ? `<div style="margin-top:8px">${event.detail}</div>` : ''}
          <div class="muted" style="margin-top:8px">${event.event_type}${event.actor_id ? ` · actor=${event.actor_id}` : ''}</div>
        </article>
      `).join('') : '<div class="empty">No timeline entries yet.</div>';
    }
    async function refreshWorkspaceSurfaces() {
      try {
        const projectId = document.getElementById('project-filter').value.trim();
        const discussionMention = document.getElementById('discussion-mention-filter').value.trim();
        const discussionQuery = document.getElementById('discussion-search-filter').value.trim();
        const [workspace, agents, runtime, discussions, discussionGroups, savedFilters, registrations] = await Promise.all([
          apiJson(`/v1/workspace/overview${qs({ project_id: projectId })}`),
          apiJson(`/v1/agents/profiles${qs({ project_id: projectId })}`),
          apiJson(`/v1/runtime/panel${qs({ project_id: projectId })}`),
          apiJson(`/v1/workspace/discussions${qs({ project_id: projectId, mention: discussionMention, query: discussionQuery })}`),
          apiJson(`/v1/workspace/discussions/groups${qs({ project_id: projectId, mention: discussionMention, query: discussionQuery })}`),
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
        const mention = document.getElementById('discussion-reply-mention-filter').value.trim();
        const data = await apiJson(`/v1/workspace/discussions/${encodeURIComponent(discussionId)}/replies${qs({ mention })}`);
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
    async function postComment() {
      const cycleId = selectedCycleId || selectedCycleInput.value.trim();
      if (!cycleId) {
        showToast('Select a cycle before posting a comment.', 'error', 'Comments');
        return;
      }
      const body = document.getElementById('comment-body').value.trim();
      const mentions = document.getElementById('comment-mentions').value.split(',').map((item) => item.trim()).filter(Boolean);
      if (!body) return;
      const response = await fetch(`/v1/cycles/${encodeURIComponent(cycleId)}/comments`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ body, mentions }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') {
        throw new Error(payload?.error?.message || `Comment post failed (${response.status})`);
      }
      document.getElementById('comment-body').value = '';
      document.getElementById('comment-mentions').value = '';
      await refreshComments(cycleId);
      await refreshWorkspaceSurfaces();
      showToast('Comment posted.', 'success', 'Comments');
    }
    async function refreshBoard() {
      try {
        const projectId = document.getElementById('project-filter').value.trim();
        const limit = document.getElementById('board-limit').value || '12';
        projectStateEl.textContent = projectId || 'all';
        const board = await apiJson(`/v1/cycles/board${qs({ project_id: projectId, limit_per_column: limit })}`);
        renderBoard(board);
      } catch (error) {
        boardColumnsEl.innerHTML = `<div class="empty">${error.message}</div>`;
      }
    }
    async function refreshIssueCard(cycleId) {
      if (!cycleId) {
        document.getElementById('issue-action-cycle-id').value = '';
        document.getElementById('issue-action-approval-id').value = '';
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

    async function setDiscussionResolved(discussionId, resolved) {
      const response = await fetch(`/v1/workspace/discussions/${encodeURIComponent(discussionId)}/resolve`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolved }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') throw new Error(payload?.error?.message || `Discussion update failed (${response.status})`);
      await refreshWorkspaceSurfaces();
      if (selectedDiscussionId === discussionId) await refreshDiscussionReplies(discussionId);
    }

    async function setDiscussionPinned(discussionId, pinned) {
      const response = await fetch(`/v1/workspace/discussions/${encodeURIComponent(discussionId)}/pin`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ pinned }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') throw new Error(payload?.error?.message || `Discussion pin failed (${response.status})`);
      await refreshWorkspaceSurfaces();
    }

    async function sendAssignmentSuggestionFeedback(agentId, feedback) {
      const cycleId = selectedCycleId || selectedCycleInput.value.trim();
      if (!cycleId) { showToast('Select a cycle before sending assignment feedback.', 'error', 'Assignment'); return; }
      let note = '';
      try {
        const modal = await openActionModal({ title: 'Assignment feedback', subtitle: feedback, description: 'Add an optional note for the assignment suggestion feedback.', textarea: { value: '', placeholder: 'Optional note' } });
        note = modal.textarea || '';
      } catch (error) {
        if (error.message === 'cancelled') return;
        throw error;
      }
      const response = await fetch(`/v1/cycles/${encodeURIComponent(cycleId)}/assignment-suggestions/feedback`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId, feedback, note: note || null }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') throw new Error(payload?.error?.message || `Suggestion feedback failed (${response.status})`);
      await refreshAssignmentSuggestions(cycleId);
      await refreshIssueCard(cycleId);
    }

    async function addRuntimeActionReceipt(actionId) {
      const runtimeId = selectedRuntimeId || document.getElementById('runtime-action-target').value.trim();
      if (!runtimeId || !actionId) return;
      let summary = '';
      let status = '';
      try {
        const modal = await openActionModal({ title: 'Runtime receipt', description: 'Record receipt summary and optional status.', input: { value: '', placeholder: 'Optional status' }, textarea: { value: '', placeholder: 'Receipt summary' }, validate: (payload) => payload.textarea ? '' : 'Receipt summary is required.' });
        summary = modal.textarea || '';
        status = modal.input || '';
      } catch (error) {
        if (error.message === 'cancelled') return;
        throw error;
      }
      const response = await fetch(`/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions/${encodeURIComponent(actionId)}/receipts`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ summary: summary.trim(), status: status || null, metadata: { source: 'workbench' } }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') throw new Error(payload?.error?.message || `Runtime receipt failed (${response.status})`);
      selectedActionId = actionId;
      await refreshRuntimeActions(runtimeId);
      await refreshRuntimeActionReceipts(runtimeId, actionId);
    }


    async function createCycleFromWorkbench(connectAfterCreate = false) {
      const projectId = document.getElementById('create-cycle-project-id').value.trim();
      const userInput = document.getElementById('create-cycle-user-input').value.trim();
      if (!projectId || !userInput) {
        setInlineStatus(createCycleStatusEl, 'project id and task description are required.');
        return;
      }
      const response = await fetch('/v1/cycles', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json', 'Idempotency-Key': makeIdempotencyKey('workbench-create') },
        body: JSON.stringify({ project_id: projectId, user_input: userInput }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || `Cycle create failed (${response.status})`);
      const cycleId = body?.data?.cycle_id;
      document.getElementById('create-cycle-user-input').value = '';
      setInlineStatus(createCycleStatusEl, `Created cycle ${cycleId}.`);
      if (!document.getElementById('project-filter').value.trim()) document.getElementById('project-filter').value = projectId;
      await refreshBoard();
      await refreshWorkspaceSurfaces();
      await refreshPendingApprovals();
      if (connectAfterCreate && cycleId) {
        await selectCycle(cycleId);
        return;
      }
      if (cycleId) {
        selectedCycleId = cycleId;
        selectedCycleInput.value = cycleId;
        await refreshIssueCard(cycleId);
      }
    }

    async function submitApprovalDecision(decision) {
      const cycleId = selectedCycleId || document.getElementById('issue-action-cycle-id').value.trim() || selectedCycleInput.value.trim();
      const approvalId = document.getElementById('issue-action-approval-id').value.trim();
      let reason = document.getElementById('issue-action-reason').value.trim();
      if (!cycleId) {
        setInlineStatus(issueActionStatusEl, 'Select a cycle first.');
        return;
      }
      if (!approvalId) {
        setInlineStatus(issueActionStatusEl, 'No active approval is attached to the selected cycle.');
        return;
      }
      let reasonCode = null;
      if (decision === 'rejected' && !reason) {
        try {
          const modal = await openActionModal({ title: 'Reject approval', description: 'Choose a reason code and provide a rejection note.', select: { value: 'needs_more_information', options: [
            { value: 'verification_failed', label: 'verification_failed' },
            { value: 'needs_more_information', label: 'needs_more_information' },
            { value: 'incorrect_approach', label: 'incorrect_approach' },
            { value: 'replan_required', label: 'replan_required' },
            { value: 'policy_block', label: 'policy_block' },
          ] }, textarea: { value: '', placeholder: 'Rejection note' }, validate: (payload) => payload.textarea ? '' : 'Rejection note is required.' });
          reason = modal.textarea;
          reasonCode = modal.select;
          document.getElementById('issue-action-reason').value = reason;
        } catch (error) {
          if (error.message === 'cancelled') return;
          throw error;
        }
      }
      const payload = {
        decision,
        comment: reason || null,
        reason_code: decision === 'rejected' ? (reasonCode || 'rejected-from-workbench') : null,
      };
      const response = await fetch(`/v1/approvals/${encodeURIComponent(approvalId)}/confirm`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json', 'Idempotency-Key': makeIdempotencyKey(`approval-${decision}`) },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || `Approval ${decision} failed (${response.status})`);
      setInlineStatus(issueActionStatusEl, `${decision} accepted for ${approvalId}.`);
      await refreshBoard();
      await refreshTimeline(cycleId);
      await refreshIssueCard(cycleId);
      await refreshWorkspaceSurfaces();
      await refreshPendingApprovals();
    }

    async function submitCycleAction(action) {
      const cycleId = selectedCycleId || document.getElementById('issue-action-cycle-id').value.trim() || selectedCycleInput.value.trim();
      if (!cycleId) {
        setInlineStatus(issueActionStatusEl, 'Select a cycle first.');
        return;
      }
      let reason = document.getElementById('issue-action-reason').value.trim();
      const overrideRaw = document.getElementById('issue-action-override-input').value.trim();
      let overrideInput = {};
      if (action === 'replan') {
        const structuredOverride = buildReplanOverride();
        if (overrideRaw) {
          try {
            overrideInput = JSON.parse(overrideRaw);
          } catch (error) {
            setInlineStatus(issueActionStatusEl, 'override_input must be valid JSON.');
            return;
          }
        }
        overrideInput = { ...overrideInput, ...structuredOverride };
      }
      const payload = action === 'replan'
        ? { reason: reason || 'replan requested from workbench', override_input: overrideInput }
        : { reason: reason || `${action} requested from workbench` };
      const response = await fetch(`/v1/cycles/${encodeURIComponent(cycleId)}/${action}`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json', 'Idempotency-Key': makeIdempotencyKey(`cycle-${action}`) },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || `${action} failed (${response.status})`);
      setInlineStatus(issueActionStatusEl, `${action} accepted for ${cycleId}.`);
      await refreshBoard();
      await refreshTimeline(cycleId);
      await refreshIssueCard(cycleId);
      await refreshWorkspaceSurfaces();
      await refreshPendingApprovals();
    }

    async function queueRemoteChecksForSelectedCycle() {
      const cycleId = selectedCycleId || document.getElementById('issue-action-cycle-id').value.trim() || selectedCycleInput.value.trim();
      if (!cycleId) {
        setInlineStatus(issueActionStatusEl, 'Select a cycle first.');
        return;
      }
      if (!document.getElementById('remote-workspace-id').value.trim()) document.getElementById('remote-workspace-id').value = `cycle:${cycleId}`;
      await requestRemoteWorkspaceExecution('run_checks');
      setInlineStatus(issueActionStatusEl, `Remote checks queued for ${cycleId}.`);
    }

    async function postDiscussionReply() {
      const discussionId = selectedDiscussionId || document.getElementById('discussion-target').value.trim();
      if (!discussionId) { showToast('Select a discussion before replying.', 'error', 'Discussion'); return; }
      const body = document.getElementById('discussion-reply-body').value.trim();
      const mentions = document.getElementById('discussion-reply-mentions').value.split(',').map((item) => item.trim()).filter(Boolean);
      if (!body) return;
      const response = await fetch(`/v1/workspace/discussions/${encodeURIComponent(discussionId)}/replies`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ body, mentions }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') {
        throw new Error(payload?.error?.message || `Discussion reply failed (${response.status})`);
      }
      document.getElementById('discussion-reply-body').value = '';
      document.getElementById('discussion-reply-mentions').value = '';
      await refreshDiscussionReplies(discussionId);
      await refreshWorkspaceSurfaces();
    }

    async function saveDiscussionFilter() {
      const payload = {
        name: `filter-${Date.now()}`,
        project_id: document.getElementById('project-filter').value.trim() || null,
        mention: document.getElementById('discussion-mention-filter').value.trim() || null,
        query: document.getElementById('discussion-search-filter').value.trim() || null,
      };
      const response = await fetch('/v1/workspace/discussion-filters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.error?.message || 'Failed to save discussion filter');
      }
      await refreshWorkspaceSurfaces();
    }
    async function updateDiscussionFilter(filterId, current) {
      let nextName = '';
      try {
        const modal = await openActionModal({ title: 'Rename saved filter', description: 'Update the saved filter name.', input: { value: current.name || '', placeholder: 'Saved filter name' }, validate: (payload) => payload.input ? '' : 'Saved filter name is required.' });
        nextName = modal.input || '';
      } catch (error) {
        if (error.message === 'cancelled') return;
        throw error;
      }
      const response = await fetch(`/v1/workspace/discussion-filters/${encodeURIComponent(filterId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ name: nextName.trim(), project_id: current.projectId || null, mention: current.mention || null, query: current.query || null }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') throw new Error(payload?.error?.message || 'Failed to update discussion filter');
      await refreshWorkspaceSurfaces();
    }
    async function favoriteDiscussionFilter(filterId, isFavorite) {
      const response = await fetch(`/v1/workspace/discussion-filters/${encodeURIComponent(filterId)}/favorite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ is_favorite: isFavorite }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') throw new Error(payload?.error?.message || 'Failed to favorite discussion filter');
      await refreshWorkspaceSurfaces();
    }
    async function deleteDiscussionFilter(filterId) {
      const response = await fetch(`/v1/workspace/discussion-filters/${encodeURIComponent(filterId)}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') throw new Error(payload?.error?.message || 'Failed to delete discussion filter');
      await refreshWorkspaceSurfaces();
    }
    async function markDiscussionFilterUsed(filterId) {
      const response = await fetch(`/v1/workspace/discussion-filters/${encodeURIComponent(filterId)}/use`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') throw new Error(payload?.error?.message || 'Failed to mark discussion filter as used');
    }
    async function refreshRemoteWorkspaceSection() {
      try {
        const projectId = document.getElementById('project-filter').value.trim();
        const cycleId = selectedCycleId || selectedCycleInput.value.trim();
        if (!document.getElementById('remote-workspace-id').value.trim() && cycleId) {
          document.getElementById('remote-workspace-id').value = `cycle:${cycleId}`;
        }
        const workspaceId = document.getElementById('remote-workspace-id').value.trim();
        const [executors, snapshots, views, persistentSessions] = await Promise.all([
          apiJson('/v1/remote-workspaces/executors'),
          apiJson(`/v1/remote-workspaces/snapshots${qs({ project_id: projectId || null })}`),
          apiJson('/v1/workbench/views'),
          apiJson('/v1/remote-workspaces/persistent/sessions').catch(() => ({ items: [] })),
        ]);
        renderRemoteWorkspaceExecutors(executors);
        renderRemoteWorkspaceSnapshots(snapshots);
        renderWorkbenchSavedViews(views);
        renderPersistentWorkspaceSessions(persistentSessions);
        if (!defaultWorkbenchViewApplied) await applyDefaultWorkbenchView();
        if (workspaceId) {
          const [executions, resume] = await Promise.all([
            apiJson(`/v1/remote-workspaces/${encodeURIComponent(workspaceId)}/executions`),
            apiJson(`/v1/remote-workspaces/${encodeURIComponent(workspaceId)}/resume`).catch(() => null),
          ]);
          renderRemoteWorkspaceExecutions(executions);
          renderRemoteWorkspaceResume(resume);
          if (selectedExecutionId && (executions.items || []).some((item) => item.execution_id === selectedExecutionId)) {
            const detail = await apiJson(`/v1/remote-workspaces/executions/${encodeURIComponent(selectedExecutionId)}`).catch(() => null);
            renderRemoteWorkspaceExecutionDetail(detail);
          } else {
            renderRemoteWorkspaceExecutionDetail((executions.items || [])[0] || null);
          }
        } else {
          renderRemoteWorkspaceExecutions({ items: [] });
          renderRemoteWorkspaceResume(null);
          renderRemoteWorkspaceExecutionDetail(null);
        }
      } catch (error) {
        remoteWorkspaceExecutorsEl.innerHTML = `<div class="empty">${error.message}</div>`;
        remoteWorkspaceSnapshotsEl.innerHTML = `<div class="empty">${error.message}</div>`;
        remoteWorkspaceExecutionsEl.innerHTML = `<div class="empty">${error.message}</div>`;
        remoteWorkspaceExecutionDetailEl.innerHTML = `<div class="empty">${error.message}</div>`;
        persistentWorkspaceSessionsEl.innerHTML = `<div class="empty">${error.message}</div>`;
      }
    }
    async function saveRemoteWorkspaceSnapshot() {
      const payload = {
        workspace_id: document.getElementById('remote-workspace-id').value.trim() || null,
        cycle_id: selectedCycleId || selectedCycleInput.value.trim() || null,
        project_id: document.getElementById('project-filter').value.trim() || null,
        repo_url: document.getElementById('remote-workspace-repo-url').value.trim() || null,
        repo_branch: document.getElementById('remote-workspace-repo-branch').value.trim() || null,
        execution_profile: 'phase1',
      };
      const response = await fetch('/v1/remote-workspaces/snapshots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || 'Failed to save remote workspace snapshot');
      selectedWorkspaceId = body?.data?.workspace_id || payload.workspace_id;
      document.getElementById('remote-workspace-id').value = selectedWorkspaceId || '';
      await refreshRemoteWorkspaceSection();
    }
    async function inspectRemoteWorkspaceExecution(executionId) {
      selectedExecutionId = executionId;
      const payload = await apiJson(`/v1/remote-workspaces/executions/${encodeURIComponent(executionId)}`);
      renderRemoteWorkspaceExecutionDetail(payload);
    }
    async function cancelRemoteWorkspaceExecution(executionId) {
      const response = await fetch(`/v1/remote-workspaces/executions/${encodeURIComponent(executionId)}/cancel`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || 'Failed to cancel remote execution');
      await refreshRemoteWorkspaceSection();
    }
    async function requestRemoteWorkspaceExecution(kind) {
      const workspaceId = document.getElementById('remote-workspace-id').value.trim();
      if (!workspaceId) { showToast('Save a remote workspace snapshot first.', 'error', 'Remote workspace'); return; }
      const payload = {
        workspace_id: workspaceId,
        execution_kind: kind,
        command: document.getElementById('remote-workspace-command').value.trim() || null,
        repo_url: document.getElementById('remote-workspace-repo-url').value.trim() || null,
        repo_branch: document.getElementById('remote-workspace-repo-branch').value.trim() || null,
      };
      const response = await fetch('/v1/remote-workspaces/executions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || 'Failed to queue remote execution');
      selectedExecutionId = body?.data?.execution_id || selectedExecutionId;
      await refreshRemoteWorkspaceSection();
    }
    async function resumeRemoteWorkspace() {
      const workspaceId = document.getElementById('remote-workspace-id').value.trim();
      if (!workspaceId) { showToast('Select a remote workspace first.', 'error', 'Remote workspace'); return; }
      const response = await fetch(`/v1/remote-workspaces/${encodeURIComponent(workspaceId)}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ note: document.getElementById('remote-resume-note').value.trim() || null }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || 'Failed to resume remote workspace');
      renderRemoteWorkspaceResume(body.data);
      await refreshRemoteWorkspaceSection();
    }

    async function savePersistentWorkspaceSession() {
      const workspaceId = document.getElementById('remote-workspace-id').value.trim();
      if (!workspaceId) { showToast('Select or save a remote workspace first.', 'error', 'Persistent workspace'); return; }
      const payload = {
        workspace_id: workspaceId,
        cycle_id: selectedCycleId || selectedCycleInput.value.trim() || null,
        project_id: document.getElementById('project-filter').value.trim() || null,
        repo_url: document.getElementById('remote-workspace-repo-url').value.trim() || null,
        repo_branch: document.getElementById('remote-workspace-repo-branch').value.trim() || null,
        note: document.getElementById('remote-resume-note').value.trim() || 'promoted from workbench',
        provider: 'workbench',
      };
      const response = await fetch('/v1/remote-workspaces/persistent/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || 'Failed to save persistent session');
      await refreshRemoteWorkspaceSection();
    }
    async function hibernatePersistentWorkspaceSession(workspaceId) {
      const response = await fetch(`/v1/remote-workspaces/persistent/sessions/${encodeURIComponent(workspaceId)}/hibernate`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || 'Failed to hibernate persistent session');
      await refreshRemoteWorkspaceSection();
    }
    async function deletePersistentWorkspaceSession(workspaceId) {
      const response = await fetch(`/v1/remote-workspaces/persistent/sessions/${encodeURIComponent(workspaceId)}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || 'Failed to delete persistent session');
      await refreshRemoteWorkspaceSection();
    }

    async function saveWorkbenchView(overrides = {}) {
      const payload = {
        name: overrides.name || document.getElementById('workbench-view-name').value.trim() || `view-${Date.now()}`,
        project_id: document.getElementById('project-filter').value.trim() || null,
        cycle_id: selectedCycleId || selectedCycleInput.value.trim() || null,
        workspace_id: document.getElementById('remote-workspace-id').value.trim() || null,
        query: document.getElementById('discussion-search-filter').value.trim() || null,
        discussion_filter_id: null,
        layout: { boardTotal: boardTotalEl.textContent, runtimeAction: runtimeActionStateEl.textContent, smart_filter: activeSmartFilter, is_default: Boolean(overrides.is_default) },
        selected_panels: ['board', 'timeline', 'remote-workspace'],
        notes: overrides.notes !== undefined ? overrides.notes : (document.getElementById('workbench-view-notes').value.trim() || 'saved from workbench'),
      };
      const response = await fetch('/v1/workbench/views', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || 'Failed to save workbench view');
      await refreshRemoteWorkspaceSection();
    }

    async function useWorkbenchView(viewId, options = {}) {
      const response = await fetch(`/v1/workbench/views/${encodeURIComponent(viewId)}/use`, { method: 'POST', headers: authHeaders() });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || 'Failed to use workbench view');
      const item = body.data;
      document.getElementById('project-filter').value = item.project_id || '';
      selectedCycleInput.value = item.cycle_id || '';
      document.getElementById('remote-workspace-id').value = item.workspace_id || '';
      document.getElementById('discussion-search-filter').value = item.query || '';
      activeSmartFilter = item.layout?.smart_filter || 'all';
      document.querySelectorAll('#smart-filters [data-smart-filter]').forEach((button) => button.classList.toggle('active', (button.dataset.smartFilter || 'all') === activeSmartFilter));
      if (item.cycle_id) selectedCycleId = item.cycle_id;
      await refreshBoard();
      await refreshWorkspaceSurfaces();
      await refreshRemoteWorkspaceSection();
      if (!options.silent) showToast(`Applied view ${item.name}.`, 'success', 'Workbench view');
      if (item.cycle_id) selectCycle(item.cycle_id);
    }

    async function deleteWorkbenchView(viewId) {
      const response = await fetch(`/v1/workbench/views/${encodeURIComponent(viewId)}`, { method: 'DELETE', headers: authHeaders() });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || 'Failed to delete workbench view');
      await refreshRemoteWorkspaceSection();
    }

    async function updateWorkbenchView(viewId, overrides) {
      const current = (latestWorkbenchViews?.items || []).find((item) => item.view_id === viewId);
      if (!current) throw new Error('workbench view not found in current session');
      const payload = {
        name: overrides?.name || current.name,
        project_id: overrides?.project_id !== undefined ? overrides.project_id : current.project_id,
        cycle_id: overrides?.cycle_id !== undefined ? overrides.cycle_id : current.cycle_id,
        workspace_id: overrides?.workspace_id !== undefined ? overrides.workspace_id : current.workspace_id,
        query: overrides?.query !== undefined ? overrides.query : current.query,
        discussion_filter_id: current.discussion_filter_id || null,
        layout: { ...(current.layout || {}), ...(overrides?.layout || {}) },
        selected_panels: overrides?.selected_panels || current.selected_panels || [],
        notes: overrides?.notes !== undefined ? overrides.notes : current.notes,
      };
      const response = await fetch(`/v1/workbench/views/${encodeURIComponent(viewId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok || body?.status === 'error') throw new Error(body?.error?.message || 'Failed to update workbench view');
      await refreshRemoteWorkspaceSection();
      return body.data;
    }

    async function markWorkbenchViewDefault(viewId) {
      const items = latestWorkbenchViews?.items || [];
      await Promise.all(items.filter((item) => item.layout?.is_default && item.view_id !== viewId).map((item) => updateWorkbenchView(item.view_id, { layout: { ...(item.layout || {}), is_default: false } })));
      await updateWorkbenchView(viewId, { layout: { is_default: true } });
      showToast('Default workbench view updated.', 'success', 'Workbench view');
    }

    async function applyDefaultWorkbenchView() {
      if (defaultWorkbenchViewApplied) return;
      const view = findDefaultWorkbenchView();
      if (!view) return;
      defaultWorkbenchViewApplied = true;
      await useWorkbenchView(view.view_id, { silent: true });
    }

    async function renameWorkbenchView(viewId) {
      const current = (latestWorkbenchViews?.items || []).find((item) => item.view_id === viewId);
      if (!current) throw new Error('workbench view not found');
      const modal = await openActionModal({
        title: 'Rename saved view',
        subtitle: current.name,
        description: 'Update the label and notes while preserving the current layout and filters.',
        input: { value: current.name, placeholder: 'view name' },
        textarea: { value: current.notes || '', placeholder: 'notes / preset hint' },
        validate: (payload) => payload.input ? '' : 'View name is required.',
      });
      await updateWorkbenchView(viewId, { name: modal.input, notes: modal.textarea });
      showToast('Saved view updated.', 'success', 'Workbench view');
    }

    async function resolveSelectedCycle() {
      const cycleId = requireField(selectedCycleId || selectedCycleInput.value.trim(), 'Select a cycle before resolving it.');
      const summary = document.getElementById('resolve-summary').value.trim();
      const linkedDiscussionId = document.getElementById('resolve-linked-discussion-id').value.trim();
      const modal = await openActionModal({
        title: 'Resolve / close cycle',
        subtitle: cycleId,
        description: 'Record the resolution summary and optionally close a linked discussion thread.',
        input: { value: summary, placeholder: 'resolution summary' },
        textarea: { value: '', placeholder: 'follow-up / prevention note (optional)' },
        validate: (payload) => payload.input ? '' : 'Resolution summary is required.',
      });
      const body = `[resolved] ${modal.input}${modal.textarea ? `\nfollow_up: ${modal.textarea}` : ''}`;
      const response = await fetch(`/v1/cycles/${encodeURIComponent(cycleId)}/comments`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ body, mentions: [] }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') throw new Error(payload?.error?.message || 'Failed to resolve cycle');
      if (linkedDiscussionId) await setDiscussionResolved(linkedDiscussionId, true);
      document.getElementById('resolve-summary').value = modal.input;
      renderResolutionSummary({ cycleId, summary: modal.input, actorId: activeAuthUserId(), linkedDiscussionId, resolvedAt: relativeTime(new Date().toISOString()) });
      await refreshComments(cycleId);
      await refreshIssueCard(cycleId);
      await refreshWorkspaceSurfaces();
      showToast('Cycle resolution recorded.', 'success', 'Resolution');
    }

    async function buildHandoffBundle() {
      const cycleId = requireField(selectedCycleId || selectedCycleInput.value.trim(), 'Select a cycle before building a handoff bundle.');
      const target = document.getElementById('handoff-target').value.trim();
      const mentions = document.getElementById('handoff-mentions').value.split(',').map((item) => item.trim()).filter(Boolean);
      const [card, result, comments] = await Promise.all([
        apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/card`),
        apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/result`).catch(() => null),
        apiJson(`/v1/cycles/${encodeURIComponent(cycleId)}/comments`).catch(() => ({ items: [] })),
      ]);
      const nextAction = buildNextStepActions({ ...card, detailed_result: result }, result)[0]?.label || 'Review cycle manually';
      const body = buildHandoffBody({
        projectId: card.cycle?.project_id,
        cycleId,
        target,
        state: card.cycle?.state,
        resultState: result?.final_state,
        summary: result?.summary || document.getElementById('resolve-summary').value.trim(),
        nextAction,
        assignment: card.current_assignment ? `${card.current_assignment.agent_id}:${card.current_assignment.assignment_role}` : null,
        lastComment: comments.items?.[0]?.body || null,
      });
      renderHandoffBundle({ cycleId, projectId: card.cycle?.project_id, target, mentions, body });
      showToast('Handoff bundle prepared.', 'success', 'Handoff');
    }

    async function postHandoffBundle() {
      if (!latestHandoffBundle) await buildHandoffBundle();
      if (!latestHandoffBundle) throw new Error('No handoff bundle available.');
      const response = await fetch('/v1/workspace/discussions', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: latestHandoffBundle.projectId || null, body: latestHandoffBundle.body, mentions: latestHandoffBundle.mentions || [] }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') throw new Error(payload?.error?.message || 'Failed to post handoff note');
      await refreshWorkspaceSurfaces();
      showToast('Handoff note posted.', 'success', 'Handoff');
    }

    async function refreshAuditExplorer() {
      const managementKey = document.getElementById('auth-management-key').value.trim();
      if (!managementKey) { auditExplorerEl.innerHTML = '<div class="empty">Enter X-Management-Key to load audit events.</div>'; return; }
      try {
        const prefix = document.getElementById('audit-prefix-filter').value.trim();
        const data = await adminJson(`/v1/admin/audit/events${qs({ event_type_prefix: prefix || null, limit: 40 })}`);
        renderAuditExplorer(data);
      } catch (error) {
        auditExplorerEl.innerHTML = `<div class="empty">${error.message}</div>`;
      }
    }

    async function postDiscussion() {
      const projectId = document.getElementById('project-filter').value.trim();
      const body = document.getElementById('discussion-body').value.trim();
      const mentions = document.getElementById('discussion-mentions').value.split(',').map((item) => item.trim()).filter(Boolean);
      if (!body) return;
      const response = await fetch('/v1/workspace/discussions', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId || null, body, mentions }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') {
        throw new Error(payload?.error?.message || `Discussion post failed (${response.status})`);
      }
      document.getElementById('discussion-body').value = '';
      document.getElementById('discussion-mentions').value = '';
      await refreshWorkspaceSurfaces();
      showToast('Discussion posted.', 'success', 'Discussion');
    }

    async function assignAgentToCycle() {
      const cycleId = selectedCycleId || selectedCycleInput.value.trim();
      if (!cycleId) { showToast('Select a cycle before assigning an agent.', 'error', 'Assignment'); return; }
      const agentId = document.getElementById('assignment-agent-id').value.trim();
      const assignmentRole = document.getElementById('assignment-role').value.trim() || 'primary';
      const note = document.getElementById('assignment-note').value.trim();
      if (!agentId) { showToast('agent id is required.', 'error', 'Assignment'); return; }
      const response = await fetch(`/v1/cycles/${encodeURIComponent(cycleId)}/assignments`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId, assignment_role: assignmentRole, note: note || null }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') {
        throw new Error(payload?.error?.message || `Assignment failed (${response.status})`);
      }
      document.getElementById('assignment-note').value = '';
      await refreshAssignments(cycleId);
      await refreshAssignmentSuggestions(cycleId);
      await refreshIssueCard(cycleId);
    }

    async function enqueueRuntimeActionPanel() {
      const runtimeId = selectedRuntimeId || document.getElementById('runtime-action-target').value.trim();
      if (!runtimeId) { showToast('Select a runtime before enqueueing an action.', 'error', 'Runtime action'); return; }
      const action = document.getElementById('runtime-action-name').value.trim();
      if (!action) { showToast('action name is required.', 'error', 'Runtime action'); return; }
      let args = {};
      const rawArgs = document.getElementById('runtime-action-args').value.trim();
      if (rawArgs) {
        try { args = JSON.parse(rawArgs); } catch (_) { showToast('action arguments must be valid JSON.', 'error', 'Runtime action'); return; }
      }
      const response = await fetch(`/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, arguments: args }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') {
        throw new Error(payload?.error?.message || `Runtime action failed (${response.status})`);
      }
      await refreshRuntimeActions(runtimeId);
    }

    async function acknowledgeRuntimeAction(actionId) {
      const runtimeId = selectedRuntimeId || document.getElementById('runtime-action-target').value.trim();
      if (!runtimeId || !actionId) return;
      let note = '';
      try {
        const modal = await openActionModal({ title: 'Acknowledge runtime action', description: 'Add an optional acknowledgement note.', textarea: { value: '', placeholder: 'Optional acknowledgement note' } });
        note = modal.textarea || '';
      } catch (error) {
        if (error.message === 'cancelled') return;
        throw error;
      }
      const response = await fetch(`/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions/${encodeURIComponent(actionId)}/acknowledge`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: note || null }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') {
        throw new Error(payload?.error?.message || `Runtime action acknowledge failed (${response.status})`);
      }
      await refreshRuntimeActions(runtimeId);
    }

    async function transitionRuntimeAction(actionId, nextStatus) {
      const runtimeId = selectedRuntimeId || document.getElementById('runtime-action-target').value.trim();
      if (!runtimeId || !actionId) return;
      let note = '';
      try {
        const modal = await openActionModal({ title: 'Transition runtime action', subtitle: nextStatus, description: 'Add an optional note for the state transition.', textarea: { value: '', placeholder: `Optional note for ${nextStatus}` } });
        note = modal.textarea || '';
      } catch (error) {
        if (error.message === 'cancelled') return;
        throw error;
      }
      const response = await fetch(`/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions/${encodeURIComponent(actionId)}/state`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: nextStatus, note: note || null, metadata: { source: 'workbench' } }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') {
        throw new Error(payload?.error?.message || `Runtime action transition failed (${response.status})`);
      }
      await refreshRuntimeActions(runtimeId);
    }

    async function registerRuntimePanel() {
      const runtimeId = document.getElementById('runtime-id').value.trim();
      const label = document.getElementById('runtime-label').value.trim();
      const projectId = document.getElementById('project-filter').value.trim();
      if (!runtimeId || !label) { showToast('runtime id and label are required.', 'error', 'Runtime registration'); return; }
      const response = await fetch('/v1/runtime/registrations', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ runtime_id: runtimeId, label, project_id: projectId || null, workspace_id: projectId || null, status: 'online', mode: 'daemon', version: 'dev-ui', capabilities: ['board-stream', 'cycle-stream'], metadata: { source: 'workbench' } }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.status === 'error') {
        throw new Error(payload?.error?.message || `Runtime registration failed (${response.status})`);
      }
      await refreshWorkspaceSurfaces();
    }

    async function refreshAssignmentSuggestions(cycleId) {
      if (!cycleId) {
        assignmentSuggestionsEl.innerHTML = '<div class="empty">Select a cycle to view assignment suggestions.</div>';
        assignmentLearningWeightsEl.innerHTML = '<div class="empty">Select a cycle to view learning weights.</div>';
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
    async function refreshRuntimeActions(runtimeId) {
      if (!runtimeId) {
        runtimeActionsEl.innerHTML = '<div class="empty">Select a runtime to view actions.</div>';
        runtimeActionTimelineEl.innerHTML = '<div class="empty">Select a runtime action to view timeline.</div>';
        runtimeActionReceiptsEl.innerHTML = '<div class="empty">Select a runtime action to view receipts.</div>';
        if (runtimeActionAbortController) runtimeActionAbortController.abort();
        setStatus(runtimeActionStateEl, 'idle');
        return;
      }
      try {
        const data = await apiJson(`/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions`);
        renderRuntimeActions(data);
        if (selectedActionId) {
          await Promise.all([
            refreshRuntimeActionTimeline(runtimeId, selectedActionId),
            refreshRuntimeActionReceipts(runtimeId, selectedActionId),
          ]);
        }
      } catch (error) {
        runtimeActionsEl.innerHTML = `<div class="empty">${error.message}</div>`;
      }
    }
    async function startRuntimeActionStream(runtimeId, actionId) {
      if (!runtimeId || !actionId) return;
      if (runtimeActionAbortController) runtimeActionAbortController.abort();
      runtimeActionAbortController = new AbortController();
      setStatus(runtimeActionStateEl, 'connecting');
      try {
        await consumeSSE(`/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions/${encodeURIComponent(actionId)}/events${qs({ poll_interval_seconds: 1, heartbeat_seconds: 15, stream_timeout_seconds: 600 })}`, (eventName, payload) => {
          if (eventName === 'runtime.action.snapshot' && payload.runtime_action) {
            renderRuntimeActionTimeline({ items: payload.runtime_action.timeline || [] });
          }
          if (eventName !== 'heartbeat') pushStreamItem(`runtime-action:${eventName}`, payload);
        }, runtimeActionStateEl, runtimeActionAbortController);
      } catch (error) {
        setStatus(runtimeActionStateEl, `error: ${error.message}`);
      }
    }

    async function refreshRuntimeActionTimeline(runtimeId, actionId) {
      if (!runtimeId || !actionId) {
        runtimeActionTimelineEl.innerHTML = '<div class="empty">Select a runtime action to view timeline.</div>';
        return;
      }
      try {
        const data = await apiJson(`/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions/${encodeURIComponent(actionId)}/timeline`);
        renderRuntimeActionTimeline(data);
      } catch (error) {
        runtimeActionTimelineEl.innerHTML = `<div class="empty">${error.message}</div>`;
      }
    }

    async function refreshRuntimeActionReceipts(runtimeId, actionId) {
      if (!runtimeId || !actionId) {
        runtimeActionReceiptsEl.innerHTML = '<div class="empty">Select a runtime action to view receipts.</div>';
        return;
      }
      try {
        const data = await apiJson(`/v1/runtime/registrations/${encodeURIComponent(runtimeId)}/actions/${encodeURIComponent(actionId)}/receipts`);
        renderRuntimeActionReceipts(data);
      } catch (error) {
        runtimeActionReceiptsEl.innerHTML = `<div class="empty">${error.message}</div>`;
      }
    }
    async function selectRuntimeAction(runtimeId, actionId) {
      selectedRuntimeId = runtimeId;
      selectedActionId = actionId;
      await Promise.all([
        refreshRuntimeActionTimeline(runtimeId, actionId),
        refreshRuntimeActionReceipts(runtimeId, actionId),
      ]);
      startRuntimeActionStream(runtimeId, actionId);
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
    async function consumeSSE(url, onEvent, stateEl, controller) {
      const response = await fetch(url, { headers: authHeaders(), signal: controller.signal });
      if (!response.ok) {
        const maybeJson = await response.json().catch(() => null);
        throw new Error(maybeJson?.error?.message || `Stream failed (${response.status})`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      setStatus(stateEl, 'connected');
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split('\n\n');
        buffer = chunks.pop() || '';
        for (const chunk of chunks) {
          const lines = chunk.split('\n');
          let eventName = 'message';
          let data = '';
          for (const line of lines) {
            if (line.startsWith('event:')) eventName = line.slice(6).trim();
            if (line.startsWith('data:')) data += line.slice(5).trim();
          }
          if (!data) continue;
          let payload = data;
          try { payload = JSON.parse(data); } catch (_) {}
          onEvent(eventName, payload);
        }
      }
      setStatus(stateEl, 'closed');
    }
    function stopStreams() {
      if (boardAbortController) boardAbortController.abort();
      if (cycleAbortController) cycleAbortController.abort();
      if (runtimeActionAbortController) runtimeActionAbortController.abort();
      boardAbortController = null;
      cycleAbortController = null;
      runtimeActionAbortController = null;
      setStatus(boardStateEl, 'idle');
      setStatus(cycleStateEl, 'idle');
      setStatus(runtimeActionStateEl, 'idle');
    }
    async function startBoardStream() {
      if (boardAbortController) boardAbortController.abort();
      boardAbortController = new AbortController();
      setStatus(boardStateEl, 'connecting');
      const projectId = document.getElementById('project-filter').value.trim();
      const limit = document.getElementById('board-limit').value || '12';
      try {
        await consumeSSE(`/v1/cycles/board/events${qs({ project_id: projectId, limit_per_column: limit, poll_interval_seconds: 2, heartbeat_seconds: 15, stream_timeout_seconds: 600 })}`, (eventName, payload) => {
          if (eventName === 'board.snapshot' && payload.board) renderBoard(payload.board);
          if (eventName !== 'heartbeat') pushStreamItem(`board:${eventName}`, payload);
        }, boardStateEl, boardAbortController);
      } catch (error) {
        setStatus(boardStateEl, `error: ${error.message}`);
      }
    }
    async function startCycleStream(cycleId) {
      if (!cycleId) return;
      if (cycleAbortController) cycleAbortController.abort();
      cycleAbortController = new AbortController();
      setStatus(cycleStateEl, 'connecting');
      try {
        await consumeSSE(`/v1/cycles/${encodeURIComponent(cycleId)}/events${qs({ poll_interval_seconds: 1, heartbeat_seconds: 15, stream_timeout_seconds: 600 })}`, (eventName, payload) => {
          pushStreamItem(`cycle:${eventName}`, payload);
          if (eventName === 'cycle.snapshot' || eventName === 'cycle.result') { refreshTimeline(cycleId); refreshComments(cycleId); refreshWorkspaceSurfaces(); }
        }, cycleStateEl, cycleAbortController);
      } catch (error) {
        setStatus(cycleStateEl, `error: ${error.message}`);
      }
    }
    async function selectCycle(cycleId) {
      selectedCycleId = cycleId;
      selectedCycleInput.value = cycleId;
      await refreshBoard();
      await refreshTimeline(cycleId);
      await refreshIssueCard(cycleId);
      await refreshComments(cycleId);
      await refreshAssignments(cycleId);
      await refreshAssignmentSuggestions(cycleId);
      await refreshWorkspaceSurfaces();
      await refreshPendingApprovals();
      await refreshRemoteWorkspaceSection();
      startCycleStream(cycleId);
    }

    document.getElementById('save-auth').addEventListener('click', saveAuth);
    document.getElementById('clear-auth').addEventListener('click', clearAuth);
    document.getElementById('auth-preset-operator').addEventListener('click', () => applyAuthPreset('operator'));
    document.getElementById('auth-preset-reviewer').addEventListener('click', () => applyAuthPreset('reviewer'));
    document.getElementById('auth-preset-audit').addEventListener('click', () => applyAuthPreset('audit'));
    document.getElementById('validate-auth').addEventListener('click', () => setAuthStatus(authValidationSummary()));
    document.getElementById('refresh-btn').addEventListener('click', () => {
      refreshBoard();
      refreshTimeline(selectedCycleId || selectedCycleInput.value.trim());
      refreshIssueCard(selectedCycleId || selectedCycleInput.value.trim());
      refreshRemoteWorkspaceSection();
      refreshPendingApprovals();
      refreshAuditExplorer();
    });
    document.getElementById('stop-btn').addEventListener('click', stopStreams);
    document.getElementById('create-cycle-btn').addEventListener('click', async () => { try { await createCycleFromWorkbench(false); } catch (error) { setInlineStatus(createCycleStatusEl, error.message); } });
    document.getElementById('create-cycle-and-run-btn').addEventListener('click', async () => { try { await createCycleFromWorkbench(true); } catch (error) { setInlineStatus(createCycleStatusEl, error.message); } });
    document.getElementById('issue-approve-btn').addEventListener('click', async () => { try { await submitApprovalDecision('approved'); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); } });
    document.getElementById('issue-reject-btn').addEventListener('click', async () => { try { await submitApprovalDecision('rejected'); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); } });
    document.getElementById('issue-retry-btn').addEventListener('click', async () => { try { await submitCycleAction('retry'); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); } });
    document.getElementById('issue-replan-btn').addEventListener('click', async () => { try { await submitCycleAction('replan'); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); } });
    document.getElementById('issue-remote-check-btn').addEventListener('click', async () => { try { await queueRemoteChecksForSelectedCycle(); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); } });
    document.getElementById('post-comment').addEventListener('click', async () => { try { await postComment(); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('post-discussion').addEventListener('click', async () => { try { await postDiscussion(); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('post-discussion-reply').addEventListener('click', async () => { try { await postDiscussionReply(); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('assign-agent').addEventListener('click', async () => { try { await assignAgentToCycle(); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('register-runtime').addEventListener('click', async () => { try { await registerRuntimePanel(); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('enqueue-runtime-action').addEventListener('click', async () => { try { await enqueueRuntimeActionPanel(); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    savedDiscussionFiltersEl.addEventListener('click', async (event) => {
      const applyButton = event.target.closest('.apply-saved-discussion-filter-btn');
      if (applyButton) {
        document.getElementById('project-filter').value = applyButton.dataset.projectId || '';
        document.getElementById('discussion-mention-filter').value = applyButton.dataset.mention || '';
        document.getElementById('discussion-search-filter').value = applyButton.dataset.query || '';
        try { await markDiscussionFilterUsed(applyButton.dataset.filterId || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); }
        await refreshWorkspaceSurfaces();
        return;
      }
      const renameButton = event.target.closest('.rename-saved-discussion-filter-btn');
      if (renameButton) {
        try { await updateDiscussionFilter(renameButton.dataset.filterId || '', { name: renameButton.dataset.name || '', projectId: renameButton.dataset.projectId || '', mention: renameButton.dataset.mention || '', query: renameButton.dataset.query || '' }); } catch (error) { showToast(error.message, 'error', 'Workbench'); }
        return;
      }
      const favoriteButton = event.target.closest('.favorite-saved-discussion-filter-btn');
      if (favoriteButton) {
        try { await favoriteDiscussionFilter(favoriteButton.dataset.filterId || '', favoriteButton.dataset.isFavorite === 'true'); } catch (error) { showToast(error.message, 'error', 'Workbench'); }
        return;
      }
      const deleteButton = event.target.closest('.delete-saved-discussion-filter-btn');
      if (deleteButton) {
        try { await deleteDiscussionFilter(deleteButton.dataset.filterId || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); }
      }
    });
    workspaceDiscussionsEl.addEventListener('click', async (event) => {
      const button = event.target.closest('.select-discussion-btn');
      if (button) {
        selectedDiscussionId = button.dataset.discussionId || null;
        document.getElementById('discussion-target').value = selectedDiscussionId || '';
        refreshDiscussionReplies(selectedDiscussionId);
        return;
      }
      const resolveButton = event.target.closest('.discussion-resolve-btn');
      if (resolveButton) {
        try { await setDiscussionResolved(resolveButton.dataset.discussionId || '', resolveButton.dataset.nextResolved === 'true'); } catch (error) { showToast(error.message, 'error', 'Workbench'); }
        return;
      }
      const pinButton = event.target.closest('.discussion-pin-btn');
      if (pinButton) {
        try { await setDiscussionPinned(pinButton.dataset.discussionId || '', pinButton.dataset.nextPinned === 'true'); } catch (error) { showToast(error.message, 'error', 'Workbench'); }
      }
    });
    assignmentSuggestionsEl.addEventListener('click', async (event) => {
      const button = event.target.closest('.use-assignment-suggestion-btn');
      if (button) {
        document.getElementById('assignment-agent-id').value = button.dataset.agentId || '';
        document.getElementById('assignment-role').value = button.dataset.role || 'primary';
        document.getElementById('assignment-note').value = button.dataset.note || '';
        try { await sendAssignmentSuggestionFeedback(button.dataset.agentId || '', 'accepted'); } catch (error) { showToast(error.message, 'error', 'Workbench'); }
        return;
      }
      const feedbackButton = event.target.closest('.assignment-feedback-btn');
      if (feedbackButton) {
        try { await sendAssignmentSuggestionFeedback(feedbackButton.dataset.agentId || '', feedbackButton.dataset.feedback || 'accepted'); } catch (error) { showToast(error.message, 'error', 'Workbench'); }
      }
    });
    runtimeActionsEl.addEventListener('click', async (event) => {
      const selectButton = event.target.closest('.select-runtime-action-btn');
      if (selectButton) {
        selectedActionId = selectButton.dataset.actionId || null;
        const runtimeId = selectedRuntimeId || document.getElementById('runtime-action-target').value.trim();
        await Promise.all([
          refreshRuntimeActionTimeline(runtimeId, selectedActionId),
          refreshRuntimeActionReceipts(runtimeId, selectedActionId),
        ]);
        return;
      }
      const receiptButton = event.target.closest('.add-runtime-receipt-btn');
      if (receiptButton) {
        try { await addRuntimeActionReceipt(receiptButton.dataset.actionId || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); }
        return;
      }
      const ackButton = event.target.closest('.ack-runtime-action-btn');
      if (ackButton) {
        try { await acknowledgeRuntimeAction(ackButton.dataset.actionId || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); }
        return;
      }
      const transitionButton = event.target.closest('.transition-runtime-action-btn');
      if (transitionButton) {
        try { await transitionRuntimeAction(transitionButton.dataset.actionId || '', transitionButton.dataset.nextStatus || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); }
      }
    });
    remoteWorkspaceSnapshotsEl.addEventListener('click', async (event) => {
      const button = event.target.closest('.select-remote-workspace-btn');
      if (!button) return;
      selectedWorkspaceId = button.dataset.workspaceId || null;
      document.getElementById('remote-workspace-id').value = selectedWorkspaceId || '';
      document.getElementById('remote-workspace-repo-url').value = button.dataset.repoUrl || '';
      document.getElementById('remote-workspace-repo-branch').value = button.dataset.repoBranch || 'main';
      await refreshRemoteWorkspaceSection();
    });
    issueCardEl.addEventListener('click', async (event) => {
      const button = event.target.closest('.next-step-btn');
      if (!button) return;
      const action = button.dataset.nextAction;
      if (action === 'approve') { try { await submitApprovalDecision('approved'); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); } return; }
      if (action === 'retry') { try { await submitCycleAction('retry'); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); } return; }
      if (action === 'replan') { try { await submitCycleAction('replan'); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); } return; }
      if (action === 'remote_checks') { try { await queueRemoteChecksForCycle(); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); } return; }
      if (action === 'result') {
        const resultNode = issueCardEl.querySelector('.artifact-list');
        if (resultNode) resultNode.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
    workbenchSavedViewsEl.addEventListener('click', async (event) => {
      const useButton = event.target.closest('.use-workbench-view-btn');
      if (useButton) { try { await useWorkbenchView(useButton.dataset.viewId || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); } return; }
      const defaultButton = event.target.closest('.set-default-workbench-view-btn');
      if (defaultButton) { try { await markWorkbenchViewDefault(defaultButton.dataset.viewId || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); } return; }
      const renameButton = event.target.closest('.rename-workbench-view-btn');
      if (renameButton) { try { await renameWorkbenchView(renameButton.dataset.viewId || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); } return; }
      const deleteButton = event.target.closest('.delete-workbench-view-btn');
      if (deleteButton) { try { await deleteWorkbenchView(deleteButton.dataset.viewId || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); } }
    });
    remoteWorkspaceExecutionsEl.addEventListener('click', async (event) => {
      const inspectButton = event.target.closest('.inspect-remote-execution-btn');
      if (inspectButton) { try { await inspectRemoteWorkspaceExecution(inspectButton.dataset.executionId || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); } return; }
      const cancelButton = event.target.closest('.cancel-remote-execution-btn');
      if (cancelButton) { try { await cancelRemoteWorkspaceExecution(cancelButton.dataset.executionId || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); } }
    });
    persistentWorkspaceSessionsEl.addEventListener('click', async (event) => {
      const useButton = event.target.closest('.use-persistent-session-btn');
      if (useButton) {
        selectedWorkspaceId = useButton.dataset.workspaceId || null;
        document.getElementById('remote-workspace-id').value = selectedWorkspaceId || '';
        document.getElementById('remote-workspace-repo-url').value = useButton.dataset.repoUrl || '';
        document.getElementById('remote-workspace-repo-branch').value = useButton.dataset.repoBranch || 'main';
        await refreshRemoteWorkspaceSection();
        return;
      }
      const hibernateButton = event.target.closest('.hibernate-persistent-session-btn');
      if (hibernateButton) { try { await hibernatePersistentWorkspaceSession(hibernateButton.dataset.workspaceId || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); } return; }
      const deleteButton = event.target.closest('.delete-persistent-session-btn');
      if (deleteButton) { try { await deletePersistentWorkspaceSession(deleteButton.dataset.workspaceId || ''); } catch (error) { showToast(error.message, 'error', 'Workbench'); } }
    });
    pendingApprovalsEl.addEventListener('click', async (event) => {
      const reviewButton = event.target.closest('.review-pending-approval-btn');
      if (reviewButton) {
        try { await reviewPendingApproval(reviewButton.dataset.cycleId || '', reviewButton.dataset.approvalId || ''); } catch (error) { showToast(error.message, 'error', 'Approval'); }
        return;
      }
      const useButton = event.target.closest('.use-pending-approval-btn');
      if (useButton) {
        document.getElementById('issue-action-cycle-id').value = useButton.dataset.cycleId || '';
        document.getElementById('issue-action-approval-id').value = useButton.dataset.approvalId || '';
        setInlineStatus(issueActionStatusEl, `Loaded ${useButton.dataset.approvalId || ''} into issue actions.`);
        return;
      }
      const openButton = event.target.closest('.open-pending-cycle-btn');
      if (openButton) {
        await selectCycle(openButton.dataset.cycleId || '');
        return;
      }
      const approveButton = event.target.closest('.quick-approve-btn');
      if (approveButton) {
        document.getElementById('issue-action-cycle-id').value = approveButton.dataset.cycleId || '';
        document.getElementById('issue-action-approval-id').value = approveButton.dataset.approvalId || '';
        selectedCycleId = approveButton.dataset.cycleId || selectedCycleId;
        try { await submitApprovalDecision('approved'); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); }
        return;
      }
      const rejectButton = event.target.closest('.quick-reject-btn');
      if (rejectButton) {
        document.getElementById('issue-action-cycle-id').value = rejectButton.dataset.cycleId || '';
        document.getElementById('issue-action-approval-id').value = rejectButton.dataset.approvalId || '';
        selectedCycleId = rejectButton.dataset.cycleId || selectedCycleId;
        try { await submitApprovalDecision('rejected'); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); }
      }
    });
    runtimeRegistrationsEl.addEventListener('click', (event) => {
      const button = event.target.closest('.select-runtime-btn');
      if (!button) return;
      selectedRuntimeId = button.dataset.runtimeId || null;
      selectedActionId = null;
      document.getElementById('runtime-action-target').value = selectedRuntimeId || '';
      refreshRuntimeActions(selectedRuntimeId);
    });

    document.getElementById('smart-filters').addEventListener('click', (event) => {
      const button = event.target.closest('[data-smart-filter]');
      if (!button) return;
      activeSmartFilter = button.dataset.smartFilter || 'all';
      document.querySelectorAll('#smart-filters [data-smart-filter]').forEach((item) => item.classList.toggle('active', item === button));
      renderPersonalInbox();
    });
    personalInboxEl.addEventListener('click', async (event) => {
      const openCycle = event.target.closest('.inbox-open-cycle-btn');
      if (openCycle) { await selectCycle(openCycle.dataset.cycleId || ''); return; }
      const reviewApproval = event.target.closest('.inbox-review-approval-btn');
      if (reviewApproval) { try { await reviewPendingApproval(reviewApproval.dataset.cycleId || '', reviewApproval.dataset.approvalId || ''); } catch (error) { showToast(error.message, 'error', 'Approval'); } return; }
      const openDiscussion = event.target.closest('.inbox-open-discussion-btn');
      if (openDiscussion) {
        selectedDiscussionId = openDiscussion.dataset.discussionId || null;
        document.getElementById('discussion-target').value = selectedDiscussionId || '';
        await refreshDiscussionReplies(selectedDiscussionId);
      }
    });
    issueCardEl.addEventListener('click', async (event) => {
      const nextStep = event.target.closest('.next-step-btn');
      if (!nextStep) return;
      const action = nextStep.dataset.nextAction || '';
      if (action === 'approve') { try { await submitApprovalDecision('approved'); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); } return; }
      if (action === 'retry' || action === 'replan') { try { await submitCycleAction(action); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); } return; }
      if (action === 'remote_checks') { try { await queueRemoteChecksForSelectedCycle(); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); } return; }
      if (action === 'result') { showToast('Review the result artifacts shown in Issue card detail.', 'info', 'Result'); }
    });
    approvalReviewContextEl.addEventListener('click', async (event) => {
      const openCycle = event.target.closest('.approval-review-open-cycle-btn');
      if (openCycle) { await selectCycle(openCycle.dataset.cycleId || ''); return; }
      const approve = event.target.closest('.approval-review-approve-btn');
      if (approve) {
        document.getElementById('issue-action-cycle-id').value = approve.dataset.cycleId || '';
        document.getElementById('issue-action-approval-id').value = approve.dataset.approvalId || '';
        try { await submitApprovalDecision('approved'); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); }
        return;
      }
      const reject = event.target.closest('.approval-review-reject-btn');
      if (reject) {
        document.getElementById('issue-action-cycle-id').value = reject.dataset.cycleId || '';
        document.getElementById('issue-action-approval-id').value = reject.dataset.approvalId || '';
        try { await submitApprovalDecision('rejected'); } catch (error) { setInlineStatus(issueActionStatusEl, error.message); }
      }
    });
    document.getElementById('discussion-mention-filter').addEventListener('change', () => { refreshWorkspaceSurfaces(); });
    document.getElementById('discussion-search-filter').addEventListener('change', () => { refreshWorkspaceSurfaces(); });
    document.getElementById('save-discussion-filter').addEventListener('click', async () => { try { await saveDiscussionFilter(); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('save-remote-workspace').addEventListener('click', async () => { try { await saveRemoteWorkspaceSnapshot(); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('prepare-remote-workspace').addEventListener('click', async () => { try { await requestRemoteWorkspaceExecution('prepare'); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('request-remote-workspace-run').addEventListener('click', async () => { try { await requestRemoteWorkspaceExecution('run_checks'); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('resume-remote-workspace').addEventListener('click', async () => { try { await resumeRemoteWorkspace(); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('save-persistent-session').addEventListener('click', async () => { try { await savePersistentWorkspaceSession(); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('save-workbench-view').addEventListener('click', async () => { try { await saveWorkbenchView(); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('save-default-workbench-view').addEventListener('click', async () => { try { await saveWorkbenchView({ is_default: true, notes: document.getElementById('workbench-view-notes').value.trim() || 'default workbench view' }); await refreshRemoteWorkspaceSection(); } catch (error) { showToast(error.message, 'error', 'Workbench'); } });
    document.getElementById('resolve-cycle-btn').addEventListener('click', async () => { try { await resolveSelectedCycle(); } catch (error) { if (error.message !== 'cancelled') showToast(error.message, 'error', 'Resolution'); } });
    document.getElementById('build-handoff-bundle-btn').addEventListener('click', async () => { try { await buildHandoffBundle(); } catch (error) { showToast(error.message, 'error', 'Handoff'); } });
    document.getElementById('post-handoff-bundle-btn').addEventListener('click', async () => { try { await postHandoffBundle(); } catch (error) { showToast(error.message, 'error', 'Handoff'); } });
    document.getElementById('refresh-audit').addEventListener('click', async () => { await refreshAuditExplorer(); });
    document.getElementById('refresh-pending-approvals').addEventListener('click', async () => { await refreshPendingApprovals(); });
    document.getElementById('discussion-reply-mention-filter').addEventListener('change', () => { if (selectedDiscussionId) refreshDiscussionReplies(selectedDiscussionId); });
    document.getElementById('connect-btn').addEventListener('click', async () => {
      saveAuth();
      setAuthStatus(authValidationSummary());
      await refreshBoard();
      await refreshWorkspaceSurfaces();
      await refreshPendingApprovals();
      await refreshRemoteWorkspaceSection();
      await refreshAuditExplorer();
      startBoardStream();
      const cycleId = selectedCycleInput.value.trim();
      if (cycleId) selectCycle(cycleId);
    });
    selectedCycleInput.addEventListener('change', () => {
      const cycleId = selectedCycleInput.value.trim();
      if (cycleId) selectCycle(cycleId);
    });

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
    setInlineStatus(createCycleStatusEl, '');
    setInlineStatus(issueActionStatusEl, '');
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
  