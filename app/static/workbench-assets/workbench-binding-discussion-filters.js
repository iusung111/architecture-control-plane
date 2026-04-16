async function handleSavedDiscussionFilterClick(event) {
  const applyButton = event.target.closest(".apply-saved-discussion-filter-btn");
  if (applyButton) {
    document.getElementById("project-filter").value = applyButton.dataset.projectId || "";
    document.getElementById("discussion-mention-filter").value = applyButton.dataset.mention || "";
    document.getElementById("discussion-search-filter").value = applyButton.dataset.query || "";
    try {
      await markDiscussionFilterUsed(applyButton.dataset.filterId || "");
      await refreshWorkspaceSurfaces();
    } catch (error) {
      showToast(error.message, "error", "Workbench");
    }
    return;
  }

  const renameButton = event.target.closest(".rename-saved-discussion-filter-btn");
  if (renameButton) {
    try {
      await updateDiscussionFilter(renameButton.dataset.filterId || "", {
        name: renameButton.dataset.name || "",
        projectId: renameButton.dataset.projectId || "",
        mention: renameButton.dataset.mention || "",
        query: renameButton.dataset.query || "",
      });
    } catch (error) {
      showToast(error.message, "error", "Workbench");
    }
    return;
  }

  const favoriteButton = event.target.closest(".favorite-saved-discussion-filter-btn");
  if (favoriteButton) {
    try {
      await favoriteDiscussionFilter(
        favoriteButton.dataset.filterId || "",
        favoriteButton.dataset.isFavorite === "true",
      );
    } catch (error) {
      showToast(error.message, "error", "Workbench");
    }
    return;
  }

  const deleteButton = event.target.closest(".delete-saved-discussion-filter-btn");
  if (!deleteButton) return;
  try {
    await deleteDiscussionFilter(deleteButton.dataset.filterId || "");
  } catch (error) {
    showToast(error.message, "error", "Workbench");
  }
}

async function handleWorkspaceDiscussionClick(event) {
  const selectButton = event.target.closest(".select-discussion-btn");
  if (selectButton) {
    selectedDiscussionId = selectButton.dataset.discussionId || null;
    document.getElementById("discussion-target").value = selectedDiscussionId || "";
    await refreshDiscussionReplies(selectedDiscussionId);
    return;
  }

  const resolveButton = event.target.closest(".discussion-resolve-btn");
  if (resolveButton) {
    try {
      await setDiscussionResolved(
        resolveButton.dataset.discussionId || "",
        resolveButton.dataset.nextResolved === "true",
      );
    } catch (error) {
      showToast(error.message, "error", "Workbench");
    }
    return;
  }

  const pinButton = event.target.closest(".discussion-pin-btn");
  if (!pinButton) return;
  try {
    await setDiscussionPinned(
      pinButton.dataset.discussionId || "",
      pinButton.dataset.nextPinned === "true",
    );
  } catch (error) {
    showToast(error.message, "error", "Workbench");
  }
}
