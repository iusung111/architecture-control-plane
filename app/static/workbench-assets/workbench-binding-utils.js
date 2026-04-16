function wrapInlineAction(action, statusEl) {
  return async () => {
    try {
      await action();
    } catch (error) {
      setInlineStatus(statusEl, error.message);
    }
  };
}

function wrapToastAction(action, title = "Workbench") {
  return async () => {
    try {
      await action();
    } catch (error) {
      showToast(error.message, "error", title);
    }
  };
}
