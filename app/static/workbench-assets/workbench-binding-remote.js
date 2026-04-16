async function handleRemoteWorkspaceSnapshotClick(event) {
  const button = event.target.closest(".select-remote-workspace-btn");
  if (!button) return;
  selectedWorkspaceId = button.dataset.workspaceId || null;
  document.getElementById("remote-workspace-id").value = selectedWorkspaceId || "";
  document.getElementById("remote-workspace-repo-url").value = button.dataset.repoUrl || "";
  document.getElementById("remote-workspace-repo-branch").value =
    button.dataset.repoBranch || "main";
  await refreshRemoteWorkspaceSection();
}

async function handleRemoteExecutionClick(event) {
  const inspectButton = event.target.closest(".inspect-remote-execution-btn");
  if (inspectButton) {
    try {
      await inspectRemoteWorkspaceExecution(inspectButton.dataset.executionId || "");
    } catch (error) {
      showToast(error.message, "error", "Remote workspace");
    }
    return;
  }

  const cancelButton = event.target.closest(".cancel-remote-execution-btn");
  if (!cancelButton) return;
  try {
    await cancelRemoteWorkspaceExecution(cancelButton.dataset.executionId || "");
  } catch (error) {
    showToast(error.message, "error", "Remote workspace");
  }
}

async function handlePersistentSessionClick(event) {
  const openButton = event.target.closest(".use-persistent-session-btn");
  if (openButton) {
    const workspaceId = openButton.dataset.workspaceId || "";
    selectedWorkspaceId = workspaceId || null;
    document.getElementById("remote-workspace-id").value = workspaceId;
    document.getElementById("remote-workspace-repo-url").value = openButton.dataset.repoUrl || "";
    document.getElementById("remote-workspace-repo-branch").value =
      openButton.dataset.repoBranch || "main";
    await refreshRemoteWorkspaceSection();
    return;
  }

  const hibernateButton = event.target.closest(".hibernate-persistent-session-btn");
  if (hibernateButton) {
    try {
      await hibernatePersistentWorkspaceSession(hibernateButton.dataset.workspaceId || "");
    } catch (error) {
      showToast(error.message, "error", "Persistent workspace");
    }
    return;
  }

  const deleteButton = event.target.closest(".delete-persistent-session-btn");
  if (!deleteButton) return;
  try {
    await deletePersistentWorkspaceSession(deleteButton.dataset.workspaceId || "");
  } catch (error) {
    showToast(error.message, "error", "Persistent workspace");
  }
}

async function handleSavedViewClick(event) {
  const applyButton = event.target.closest(".use-workbench-view-btn");
  if (applyButton) {
    try {
      await useWorkbenchView(applyButton.dataset.viewId || "");
    } catch (error) {
      showToast(error.message, "error", "Workbench view");
    }
    return;
  }

  const defaultButton = event.target.closest(".set-default-workbench-view-btn");
  if (defaultButton) {
    try {
      await markWorkbenchViewDefault(defaultButton.dataset.viewId || "");
      await refreshRemoteWorkspaceSection();
    } catch (error) {
      showToast(error.message, "error", "Workbench view");
    }
    return;
  }

  const renameButton = event.target.closest(".rename-workbench-view-btn");
  if (renameButton) {
    try {
      await renameWorkbenchView(renameButton.dataset.viewId || "", renameButton.dataset.name || "");
    } catch (error) {
      showToast(error.message, "error", "Workbench view");
    }
    return;
  }

  const deleteButton = event.target.closest(".delete-workbench-view-btn");
  if (!deleteButton) return;
  try {
    await deleteWorkbenchView(deleteButton.dataset.viewId || "");
  } catch (error) {
    showToast(error.message, "error", "Workbench view");
  }
}

function bindRemoteAndViewEvents() {
  remoteWorkspaceSnapshotsEl.addEventListener("click", handleRemoteWorkspaceSnapshotClick);
  remoteWorkspaceExecutionsEl.addEventListener("click", handleRemoteExecutionClick);
  persistentWorkspaceSessionsEl.addEventListener("click", handlePersistentSessionClick);
  workbenchSavedViewsEl.addEventListener("click", handleSavedViewClick);
  document
    .getElementById("save-remote-workspace")
    .addEventListener("click", wrapToastAction(saveRemoteWorkspaceSnapshot));
  document.getElementById("prepare-remote-workspace").addEventListener(
    "click",
    wrapToastAction(() => requestRemoteWorkspaceExecution("prepare")),
  );
  document.getElementById("request-remote-workspace-run").addEventListener(
    "click",
    wrapToastAction(() => requestRemoteWorkspaceExecution("run_checks")),
  );
  document
    .getElementById("resume-remote-workspace")
    .addEventListener("click", wrapToastAction(resumeRemoteWorkspace));
  document
    .getElementById("save-persistent-session")
    .addEventListener("click", wrapToastAction(savePersistentWorkspaceSession));
  document
    .getElementById("save-workbench-view")
    .addEventListener("click", wrapToastAction(saveWorkbenchView));
  document.getElementById("save-default-workbench-view").addEventListener(
    "click",
    wrapToastAction(async () => {
      await saveWorkbenchView({
        is_default: true,
        notes:
          document.getElementById("workbench-view-notes").value.trim() || "default workbench view",
      });
      await refreshRemoteWorkspaceSection();
    }),
  );
  document.getElementById("resolve-cycle-btn").addEventListener("click", async () => {
    try {
      await resolveSelectedCycle();
    } catch (error) {
      if (error.message !== "cancelled") {
        showToast(error.message, "error", "Resolution");
      }
    }
  });
  document
    .getElementById("build-handoff-bundle-btn")
    .addEventListener("click", wrapToastAction(buildHandoffBundle, "Handoff"));
  document
    .getElementById("post-handoff-bundle-btn")
    .addEventListener("click", wrapToastAction(postHandoffBundle, "Handoff"));
}
