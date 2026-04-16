async function handleRuntimeActionClick(event) {
  const selectButton = event.target.closest(".select-runtime-action-btn");
  if (selectButton) {
    selectedActionId = selectButton.dataset.actionId || null;
    const runtimeId =
      selectedRuntimeId || document.getElementById("runtime-action-target").value.trim();
    await Promise.all([
      refreshRuntimeActionTimeline(runtimeId, selectedActionId),
      refreshRuntimeActionReceipts(runtimeId, selectedActionId),
    ]);
    return;
  }

  const receiptButton = event.target.closest(".add-runtime-receipt-btn");
  if (receiptButton) {
    try {
      await addRuntimeActionReceipt(receiptButton.dataset.actionId || "");
    } catch (error) {
      showToast(error.message, "error", "Workbench");
    }
    return;
  }

  const ackButton = event.target.closest(".ack-runtime-action-btn");
  if (ackButton) {
    try {
      await acknowledgeRuntimeAction(ackButton.dataset.actionId || "");
    } catch (error) {
      showToast(error.message, "error", "Workbench");
    }
    return;
  }

  const transitionButton = event.target.closest(".transition-runtime-action-btn");
  if (!transitionButton) return;
  try {
    await transitionRuntimeAction(
      transitionButton.dataset.actionId || "",
      transitionButton.dataset.nextStatus || "",
    );
  } catch (error) {
    showToast(error.message, "error", "Workbench");
  }
}

function handleRuntimeRegistrationClick(event) {
  const button = event.target.closest(".select-runtime-btn");
  if (!button) return;
  selectedRuntimeId = button.dataset.runtimeId || null;
  selectedActionId = null;
  document.getElementById("runtime-action-target").value = selectedRuntimeId || "";
  refreshRuntimeActions(selectedRuntimeId);
}

function bindRuntimeEvents() {
  document
    .getElementById("register-runtime")
    .addEventListener("click", wrapToastAction(registerRuntimePanel));
  document
    .getElementById("enqueue-runtime-action")
    .addEventListener("click", wrapToastAction(enqueueRuntimeActionPanel));
  runtimeActionsEl.addEventListener("click", handleRuntimeActionClick);
  runtimeRegistrationsEl.addEventListener("click", handleRuntimeRegistrationClick);
  document
    .getElementById("refresh-audit")
    .addEventListener("click", wrapToastAction(refreshAuditExplorer));
}
