import { test, expect, Page, Route } from "@playwright/test";

type RequestEntry = { path: string; method: string; body: any };
type InstallOptions = {
  requestLog: RequestEntry[];
  initialCycleId?: string;
  initialProjectId?: string;
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function installWorkbenchMocks(page: Page, options: InstallOptions) {
  const requestLog = options.requestLog;
  let createdCycleId = options.initialCycleId || "cycle-created-1";
  let selectedCycleId = createdCycleId;
  let savedViews = [
    {
      view_id: "view-default-1",
      name: "Default review lane",
      notes: "Pinned review cycles",
      filters: { project_id: "proj-ui", smart_filter: "pending_approval" },
      is_default: true,
      use_count: 3,
      updated_at: "2026-04-16T00:00:00Z",
    },
  ];
  let discussions = [
    {
      discussion_id: "discussion-1",
      project_id: "proj-ui",
      body: "handoff existing note",
      mentions: ["reviewer-1"],
      resolved: false,
      pinned: false,
      created_at: "2026-04-16T00:00:00Z",
      updated_at: "2026-04-16T00:00:00Z",
    },
  ];
  let latestResolutionComment = "";

  const cardPayload = (cycleId: string, mode: "approval" | "retry") => ({
    status: "ok",
    data: {
      cycle: {
        cycle_id: cycleId,
        project_id: "proj-ui",
        state: mode === "approval" ? "human_approval_pending" : "verification_failed",
        user_status: mode === "approval" ? "approval_required" : "action_required",
        approval_required: mode === "approval",
        retry_allowed: mode === "retry",
        replan_allowed: mode === "retry",
        updated_at: "2026-04-16T00:00:00Z",
      },
      result: null,
      timeline_preview: [
        {
          event_type: "cycle.created",
          title: "Created",
          source: "audit",
          occurred_at: "2026-04-16T00:00:00Z",
        },
      ],
      comment_count: latestResolutionComment ? 1 : 0,
      active_job_count: 0,
      active_approval:
        mode === "approval"
          ? { approval_id: "approval-1", state: "pending", required: true }
          : null,
      current_assignment:
        mode === "retry" ? { agent_id: "agent-7", assignment_role: "investigator" } : null,
      suggested_agents: [],
      assignment_suggestions: [],
    },
    request_id: "req-card",
  });

  await page.route("**/v1/cycles/board**", async (route) => {
    await fulfillJson(route, {
      status: "ok",
      data: {
        project_id: options.initialProjectId || "proj-ui",
        generated_at: "2026-04-16T00:00:00Z",
        total_count: 2,
        columns: [
          {
            key: "review",
            title: "Review",
            description: "Pending attention",
            count: 2,
            items: [
              {
                cycle_id: createdCycleId,
                project_id: "proj-ui",
                state: "human_approval_pending",
                user_status: "approval_required",
                next_action: null,
                approval_required: true,
                retry_allowed: false,
                replan_allowed: false,
                latest_iteration_no: 1,
                created_at: "2026-04-16T00:00:00Z",
                updated_at: "2026-04-16T00:00:00Z",
              },
              {
                cycle_id: "cycle-retry-1",
                project_id: "proj-ui",
                state: "verification_failed",
                user_status: "action_required",
                next_action: null,
                approval_required: false,
                retry_allowed: true,
                replan_allowed: true,
                latest_iteration_no: 2,
                created_at: "2026-04-16T00:00:00Z",
                updated_at: "2026-04-16T00:00:00Z",
              },
            ],
          },
        ],
      },
      request_id: "req-board",
    });
  });
  await page.route("**/v1/workspace/overview**", async (route) =>
    fulfillJson(route, {
      status: "ok",
      data: {
        generated_at: "2026-04-16T00:00:00Z",
        totals: { cycles: 2, active: 1, pending_reviews: 1, completed: 0, failed: 1 },
        projects: [],
        recent_comments: latestResolutionComment ? [{ body: latestResolutionComment }] : [],
      },
    }),
  );
  await page.route("**/v1/workspace/discussions/groups**", async (route) =>
    fulfillJson(route, { status: "ok", data: { items: [] } }),
  );
  await page.route("**/v1/workspace/discussion-filters**", async (route) =>
    fulfillJson(route, { status: "ok", data: { items: [] } }),
  );
  await page.route("**/v1/workspace/discussions", async (route) => {
    if (route.request().method() === "POST") {
      const body = JSON.parse(route.request().postData() || "{}");
      requestLog.push({ path: "/v1/workspace/discussions", method: "POST", body });
      discussions = [
        {
          discussion_id: `discussion-${discussions.length + 1}`,
          project_id: body.project_id || "proj-ui",
          body: body.body,
          mentions: body.mentions || [],
          resolved: false,
          pinned: false,
          created_at: "2026-04-16T00:00:00Z",
          updated_at: "2026-04-16T00:00:00Z",
        },
        ...discussions,
      ];
      await fulfillJson(route, { status: "ok", data: discussions[0] });
      return;
    }
    await fulfillJson(route, { status: "ok", data: { items: discussions, mention_filter: null } });
  });
  await page.route("**/v1/workspace/discussions/*/resolve", async (route) => {
    requestLog.push({
      path: route.request().url(),
      method: "POST",
      body: JSON.parse(route.request().postData() || "{}"),
    });
    await fulfillJson(route, { status: "ok", data: { resolved: true } });
  });
  await page.route("**/v1/cycles/*/timeline**", async (route) =>
    fulfillJson(route, {
      status: "ok",
      data: {
        cycle_id: selectedCycleId,
        events: [
          {
            event_type: "cycle.created",
            title: "Created",
            source: "audit",
            occurred_at: "2026-04-16T00:00:00Z",
          },
        ],
        has_more: false,
      },
    }),
  );
  await page.route("**/v1/cycles/*/comments", async (route) => {
    if (route.request().method() === "POST") {
      const body = JSON.parse(route.request().postData() || "{}");
      requestLog.push({ path: route.request().url(), method: "POST", body });
      latestResolutionComment = body.body;
      await fulfillJson(route, {
        status: "ok",
        data: { comment_id: "comment-1", body: body.body },
      });
      return;
    }
    await fulfillJson(route, {
      status: "ok",
      data: {
        cycle_id: selectedCycleId,
        items: latestResolutionComment
          ? [
              {
                comment_id: "comment-1",
                body: latestResolutionComment,
                created_at: "2026-04-16T00:00:00Z",
              },
            ]
          : [],
      },
    });
  });
  await page.route("**/v1/cycles/*/assignments", async (route) =>
    fulfillJson(route, { status: "ok", data: { cycle_id: selectedCycleId, items: [] } }),
  );
  await page.route("**/v1/cycles/*/assignment-suggestions", async (route) =>
    fulfillJson(route, { status: "ok", data: { cycle_id: selectedCycleId, items: [] } }),
  );
  await page.route("**/v1/remote-workspaces/executors", async (route) =>
    fulfillJson(route, {
      status: "ok",
      data: { items: [{ key: "persistent", enabled: true, mode: "persistent_opt_in" }] },
    }),
  );
  await page.route("**/v1/remote-workspaces/snapshots**", async (route) =>
    fulfillJson(route, { status: "ok", data: { items: [] } }),
  );
  await page.route("**/v1/remote-workspaces/executions", async (route) => {
    if (route.request().method() === "POST") {
      const body = JSON.parse(route.request().postData() || "{}");
      requestLog.push({ path: "/v1/remote-workspaces/executions", method: "POST", body });
      await fulfillJson(route, {
        status: "ok",
        data: {
          execution_id: "exec-1",
          workspace_id: body.workspace_id,
          execution_kind: body.execution_kind,
        },
      });
      return;
    }
    await fulfillJson(route, {
      status: "ok",
      data: {
        items: [
          {
            execution_id: "exec-1",
            workspace_id: "cycle:cycle-retry-1",
            execution_kind: "run_checks",
            status: "planned",
            requested_at: "2026-04-16T00:00:00Z",
          },
        ],
      },
    });
  });
  await page.route("**/v1/remote-workspaces/executions/*", async (route) =>
    fulfillJson(route, {
      status: "ok",
      data: {
        execution_id: "exec-1",
        workspace_id: "cycle:cycle-retry-1",
        execution_kind: "run_checks",
        status: "planned",
        executor_key: "persistent",
        requested_at: "2026-04-16T00:00:00Z",
        result_summary: "queued",
        artifacts: [
          { artifact_id: "artifact-1", artifact_type: "junit", uri: "memory://artifact-1" },
        ],
      },
    }),
  );
  await page.route("**/v1/remote-workspaces/*/resume", async (route) =>
    fulfillJson(route, {
      status: "ok",
      data: {
        workspace_id: "cycle:remote",
        resume_count: 1,
        artifacts: [],
        patch_stack: [],
        recent_executions: [],
      },
    }),
  );
  await page.route("**/v1/remote-workspaces/persistent/sessions", async (route) => {
    if (route.request().method() === "POST") {
      const body = JSON.parse(route.request().postData() || "{}");
      requestLog.push({ path: "/v1/remote-workspaces/persistent/sessions", method: "POST", body });
      await fulfillJson(route, {
        status: "ok",
        data: {
          workspace_id: body.workspace_id,
          status: "active",
          provider: "workbench",
          updated_at: "2026-04-16T00:00:00Z",
        },
      });
      return;
    }
    await fulfillJson(route, {
      status: "ok",
      data: {
        items: [
          {
            workspace_id: "cycle:cycle-retry-1",
            status: "active",
            provider: "workbench",
            updated_at: "2026-04-16T00:00:00Z",
          },
        ],
      },
    });
  });
  await page.route("**/v1/remote-workspaces/persistent/sessions/*/hibernate", async (route) => {
    requestLog.push({ path: route.request().url(), method: "POST", body: {} });
    await fulfillJson(route, {
      status: "ok",
      data: { workspace_id: "cycle:cycle-retry-1", status: "hibernated" },
    });
  });
  await page.route("**/v1/remote-workspaces/persistent/sessions/*", async (route) => {
    if (route.request().method() === "DELETE") {
      requestLog.push({ path: route.request().url(), method: "DELETE", body: {} });
      await fulfillJson(route, {
        status: "ok",
        data: { workspace_id: "cycle:cycle-retry-1", status: "deleted" },
      });
      return;
    }
    await fulfillJson(route, {
      status: "ok",
      data: { workspace_id: "cycle:cycle-retry-1", status: "active", provider: "workbench" },
    });
  });
  await page.route("**/v1/workbench/views", async (route) => {
    if (route.request().method() === "POST") {
      const body = JSON.parse(route.request().postData() || "{}");
      requestLog.push({ path: "/v1/workbench/views", method: "POST", body });
      savedViews = [
        {
          view_id: "view-new-1",
          name: body.name || "Saved view",
          notes: body.notes || "",
          filters: body.filters,
          is_default: Boolean(body.is_default),
          use_count: 0,
          updated_at: "2026-04-16T00:00:00Z",
        },
        ...savedViews.map((item) => ({
          ...item,
          is_default: body.is_default ? false : item.is_default,
        })),
      ];
      await fulfillJson(route, { status: "ok", data: savedViews[0] });
      return;
    }
    await fulfillJson(route, { status: "ok", data: { items: savedViews } });
  });
  await page.route("**/v1/workbench/views/*/use", async (route) => {
    requestLog.push({ path: route.request().url(), method: "POST", body: {} });
    await fulfillJson(route, { status: "ok", data: { applied: true } });
  });
  await page.route("**/v1/workbench/views/*", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = JSON.parse(route.request().postData() || "{}");
      requestLog.push({ path: route.request().url(), method: "PATCH", body });
      await fulfillJson(route, { status: "ok", data: { view_id: "view-default-1", ...body } });
      return;
    }
    if (route.request().method() === "DELETE") {
      requestLog.push({ path: route.request().url(), method: "DELETE", body: {} });
      await fulfillJson(route, { status: "ok", data: { deleted: true } });
      return;
    }
    await fulfillJson(route, { status: "ok", data: { view_id: "view-default-1" } });
  });
  await page.route("**/v1/admin/audit/events**", async (route) =>
    fulfillJson(route, { status: "ok", data: { items: [] } }),
  );
  await page.route("**/v1/runtime/panel**", async (route) =>
    fulfillJson(route, { status: "ok", data: { queue_metrics: [], recent_jobs: [], signals: [] } }),
  );
  await page.route("**/v1/agents/profiles**", async (route) =>
    fulfillJson(route, { status: "ok", data: { items: [] } }),
  );
  await page.route("**/v1/runtime/registrations", async (route) =>
    fulfillJson(route, { status: "ok", data: { items: [] } }),
  );
  await page.route("**/v1/runtime/registrations/*/actions", async (route) =>
    fulfillJson(route, { status: "ok", data: { items: [] } }),
  );
  await page.route("**/v1/cycles", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    const body = JSON.parse(route.request().postData() || "{}");
    requestLog.push({ path: "/v1/cycles", method: "POST", body });
    createdCycleId = "cycle-created-1";
    selectedCycleId = createdCycleId;
    await fulfillJson(
      route,
      {
        status: "ok",
        data: {
          cycle_id: createdCycleId,
          state: "intent_accepted",
          user_status: "accepted",
          approval_required: false,
          created_at: "2026-04-16T00:00:00Z",
        },
      },
      201,
    );
  });
  await page.route("**/v1/cycles/*/card", async (route) => {
    const cycleId = new URL(route.request().url()).pathname.split("/")[3];
    const mode = cycleId === createdCycleId ? "approval" : "retry";
    selectedCycleId = cycleId;
    await fulfillJson(route, cardPayload(cycleId, mode));
  });
  await page.route("**/v1/cycles/*/result", async (route) => {
    const cycleId = new URL(route.request().url()).pathname.split("/")[3];
    await fulfillJson(route, {
      status: "ok",
      data: {
        cycle_id: cycleId,
        final_state: cycleId === createdCycleId ? "human_approval_pending" : "verification_failed",
        summary: cycleId === createdCycleId ? "Awaiting approval" : "Threshold drift still fails",
        output_artifacts: [
          {
            artifact_id: "result-artifact-1",
            artifact_type: "result_summary",
            uri: "memory://result-artifact-1",
          },
        ],
        verification: {
          status: cycleId === createdCycleId ? "pending" : "failed",
          failed_rules: cycleId === createdCycleId ? [] : ["pressure-window"],
        },
        approval: {
          required: cycleId === createdCycleId,
          approval_id: cycleId === createdCycleId ? "approval-1" : null,
          state: cycleId === createdCycleId ? "pending" : null,
        },
        evidence_summary: {},
        generated_at: "2026-04-16T00:00:00Z",
      },
    });
  });
  await page.route("**/v1/approvals/pending**", async (route) =>
    fulfillJson(route, {
      status: "ok",
      data: {
        items: [
          {
            approval_id: "approval-1",
            cycle_id: createdCycleId,
            project_id: "proj-ui",
            required_role: "operator",
            approval_state: "pending",
            cycle_state: "human_approval_pending",
            user_status: "approval_required",
            expires_at: "2026-04-16T10:00:00Z",
            created_at: "2026-04-16T00:00:00Z",
          },
        ],
      },
    }),
  );
  await page.route("**/v1/approvals/*/confirm", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    requestLog.push({ path: route.request().url(), method: "POST", body });
    if (body.decision === "approved") selectedCycleId = "cycle-retry-1";
    await fulfillJson(route, {
      status: "ok",
      data: {
        approval_id: "approval-1",
        approval_state: body.decision,
        resume_enqueued: body.decision === "approved",
      },
    });
  });
  await page.route("**/v1/cycles/*/retry", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    requestLog.push({ path: route.request().url(), method: "POST", body });
    await fulfillJson(
      route,
      {
        status: "accepted",
        data: { cycle_id: "cycle-retry-1", action: "retry", accepted: true, job_id: "job-1" },
      },
      202,
    );
  });
  await page.route("**/v1/cycles/*/replan", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    requestLog.push({ path: route.request().url(), method: "POST", body });
    await fulfillJson(
      route,
      {
        status: "accepted",
        data: { cycle_id: "cycle-retry-1", action: "replan", accepted: true, job_id: "job-2" },
      },
      202,
    );
  });
}

test("workbench quick start and issue actions keep existing UI flow intact", async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem(
      "acp-workbench-auth",
      JSON.stringify({
        userId: "user-1",
        userRole: "operator",
        tenantId: "",
        bearer: "",
        managementKey: "",
      }),
    ),
  );
  const requestLog: RequestEntry[] = [];
  await installWorkbenchMocks(page, { requestLog });
  await page.goto("/workbench");
  await expect(page.getByRole("heading", { name: "ACP Live Workbench" })).toBeVisible();
  await page.fill("#create-cycle-project-id", "proj-ui");
  await page.fill("#create-cycle-user-input", "Review the main pump pressure drift issue");
  await page.click("#create-cycle-and-run-btn");
  await expect(page.locator("#create-cycle-status")).toContainText(
    "Created cycle cycle-created-1.",
  );
  expect(requestLog.find((item) => item.path === "/v1/cycles")?.body).toEqual({
    project_id: "proj-ui",
    user_input: "Review the main pump pressure drift issue",
  });
  await expect(page.locator("#issue-action-approval-id")).toHaveValue("approval-1");
  await expect(page.locator("#issue-card-detail")).toContainText("Suggested next steps");
  await page.fill("#issue-action-reason", "operator confirmed");
  await page.click("#issue-approve-btn");
  await expect(page.locator("#issue-action-status")).toContainText(
    "approved accepted for approval-1.",
  );
  await page.fill("#issue-action-cycle-id", "cycle-retry-1");
  await page.fill("#issue-action-reason", "rerun after adjusting thresholds");
  await page.click("#issue-retry-btn");
  await expect(page.locator("#issue-action-status")).toContainText(
    "retry accepted for cycle-retry-1.",
  );
  await page.fill("#replan-prompt", "use safe verification");
  await page.fill("#replan-safety", "strict");
  await page.fill("#replan-priority", "high");
  await page.fill("#replan-constraints", `keep workspace clean\ncollect evidence`);
  await page.click("#issue-replan-btn");
  await expect(page.locator("#issue-action-status")).toContainText(
    "replan accepted for cycle-retry-1.",
  );
  await page.click("#issue-remote-check-btn");
  await expect(page.locator("#issue-action-status")).toContainText(
    "Remote checks queued for cycle-retry-1.",
  );
  expect(
    requestLog.some(
      (item) => item.path.includes("/v1/approvals/") && item.body.decision === "approved",
    ),
  ).toBeTruthy();
  expect(
    requestLog.some(
      (item) =>
        item.path.includes("/retry") && item.body.reason === "rerun after adjusting thresholds",
    ),
  ).toBeTruthy();
  expect(
    requestLog.some(
      (item) =>
        item.path.includes("/replan") &&
        item.body.override_input.prompt === "use safe verification" &&
        item.body.override_input.safety_mode === "strict" &&
        item.body.override_input.priority === "high" &&
        item.body.override_input.constraints.length === 2,
    ),
  ).toBeTruthy();
  expect(
    requestLog.some(
      (item) =>
        item.path === "/v1/remote-workspaces/executions" &&
        item.body.execution_kind === "run_checks",
    ),
  ).toBeTruthy();
});

test("workbench pending approvals support review context and structured rejection", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem(
      "acp-workbench-auth",
      JSON.stringify({
        userId: "reviewer-1",
        userRole: "operator",
        tenantId: "",
        bearer: "",
        managementKey: "",
      }),
    ),
  );
  const requestLog: RequestEntry[] = [];
  await installWorkbenchMocks(page, { requestLog });
  await page.goto("/workbench");
  await page.click("#auth-preset-reviewer");
  await expect(page.locator("#auth-status")).toContainText("Reviewer preset applied");
  await expect(page.locator("#pending-approvals")).toContainText("approval-1");
  await page.click(".review-pending-approval-btn");
  await expect(page.locator("#approval-review-context")).toContainText("approval-1");
  await page.click(".approval-review-reject-btn");
  await expect(page.locator("#action-modal")).toBeVisible();
  await page.selectOption("#modal-select", "policy_block");
  await page.fill("#modal-textarea", "Blocked until policy review completes");
  await page.click("#modal-confirm");
  await expect(page.locator("#issue-action-status")).toContainText(
    "rejected accepted for approval-1.",
  );
  expect(
    requestLog.some(
      (item) =>
        item.path.includes("/v1/approvals/approval-1/confirm") &&
        item.body.decision === "rejected" &&
        item.body.reason_code === "policy_block" &&
        item.body.comment === "Blocked until policy review completes",
    ),
  ).toBeTruthy();
});

test("workbench resolution handoff and saved view flows remain in the existing UI style", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem(
      "acp-workbench-auth",
      JSON.stringify({
        userId: "operator-1",
        userRole: "operator",
        tenantId: "",
        bearer: "",
        managementKey: "",
      }),
    ),
  );
  const requestLog: RequestEntry[] = [];
  await installWorkbenchMocks(page, { requestLog });
  await page.goto("/workbench");
  await page.click('[data-cycle-id="cycle-retry-1"]');
  await expect(page.locator("#selected-cycle")).toHaveValue("cycle-retry-1");
  await expect(page.locator("#personal-inbox")).toContainText("Retry");
  await page.fill("#resolve-linked-discussion-id", "discussion-1");
  await page.click("#resolve-cycle-btn");
  await expect(page.locator("#action-modal")).toBeVisible();
  await page.fill("#modal-input", "Verified mitigation path");
  await page.fill("#modal-textarea", "Track preventive threshold tuning");
  await page.click("#modal-confirm");
  await expect(page.locator("#resolution-summary")).toContainText("Verified mitigation path");
  await page.fill("#handoff-target", "maintainer-2");
  await page.fill("#handoff-mentions", "maintainer-2,reviewer-1");
  await page.click("#build-handoff-bundle-btn");
  await expect(page.locator("#handoff-bundle")).toContainText("maintainer-2");
  await expect(page.locator("#handoff-bundle")).toContainText("Threshold drift still fails");
  await page.click("#post-handoff-bundle-btn");
  await page.fill("#workbench-view-name", "Retry focus");
  await page.fill("#workbench-view-notes", "Focus on retry-ready excavator diagnostics");
  await page.click('[data-smart-filter="retry_ready"]');
  await page.click("#save-default-workbench-view");
  await expect(page.locator("#workbench-saved-views")).toContainText("Retry focus");
  await page.click(".rename-workbench-view-btn");
  await expect(page.locator("#action-modal")).toBeVisible();
  await page.fill("#modal-input", "Retry focus renamed");
  await page.fill("#modal-textarea", "Updated default queue");
  await page.click("#modal-confirm");
  expect(
    requestLog.some(
      (item) =>
        item.path.includes("/comments") &&
        String(item.body.body || "").includes("[resolved] Verified mitigation path"),
    ),
  ).toBeTruthy();
  expect(
    requestLog.some(
      (item) =>
        item.path === "/v1/workspace/discussions" &&
        String(item.body.body || "").includes("next_action"),
    ),
  ).toBeTruthy();
  expect(
    requestLog.some(
      (item) =>
        item.path === "/v1/workbench/views" &&
        item.body.is_default === true &&
        item.body.filters.smart_filter === "retry_ready",
    ),
  ).toBeTruthy();
  expect(
    requestLog.some(
      (item) =>
        item.path.includes("/v1/workbench/views/") &&
        item.method === "PATCH" &&
        item.body.name === "Retry focus renamed",
    ),
  ).toBeTruthy();
});
