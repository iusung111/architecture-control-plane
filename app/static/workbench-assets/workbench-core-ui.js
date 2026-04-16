function relativeTime(value) {
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return String(value || "");
  return `${dt.toLocaleTimeString()} · ${dt.toLocaleDateString()}`;
}
function makeIdempotencyKey(prefix) {
  if (window.crypto && typeof window.crypto.randomUUID === "function")
    return `${prefix}-${window.crypto.randomUUID()}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function setInlineStatus(el, message) {
  if (!el) return;
  el.textContent = message || "";
}
function showToast(message, tone = "info", title = "Workbench") {
  const stack = document.getElementById("toast-stack");
  if (!stack || !message) return;
  const el = document.createElement("div");
  el.className = `toast ${tone}`;
  el.innerHTML = `<strong>${title}</strong><div>${message}</div>`;
  stack.appendChild(el);
  window.setTimeout(() => {
    if (el.parentNode) el.parentNode.removeChild(el);
  }, 3600);
}
function requireField(value, message) {
  if (value) return value;
  showToast(message, "error", "Validation");
  throw new Error(message);
}
function openActionModal(config) {
  const shell = document.getElementById("action-modal");
  const title = document.getElementById("modal-title");
  const subtitle = document.getElementById("modal-subtitle");
  const description = document.getElementById("modal-description");
  const input = document.getElementById("modal-input");
  const textarea = document.getElementById("modal-textarea");
  const select = document.getElementById("modal-select");
  const error = document.getElementById("modal-error");
  const confirm = document.getElementById("modal-confirm");
  const cancel = document.getElementById("modal-cancel");
  title.textContent = config.title || "Action";
  subtitle.textContent = config.subtitle || "";
  description.textContent = config.description || "";
  input.hidden = !config.input;
  input.value = config.input?.value || "";
  input.placeholder = config.input?.placeholder || "";
  textarea.hidden = !config.textarea;
  textarea.value = config.textarea?.value || "";
  textarea.placeholder = config.textarea?.placeholder || "";
  select.hidden = !(config.select && config.select.options && config.select.options.length);
  if (!select.hidden) {
    select.innerHTML = config.select.options
      .map((opt) => `<option value="${opt.value}">${opt.label}</option>`)
      .join("");
    select.value = config.select.value || config.select.options[0].value;
  } else {
    select.innerHTML = "";
  }
  error.textContent = "";
  shell.hidden = false;
  return new Promise((resolve, reject) => {
    const close = () => {
      shell.hidden = true;
      confirm.onclick = null;
      cancel.onclick = null;
    };
    cancel.onclick = () => {
      close();
      reject(new Error("cancelled"));
    };
    confirm.onclick = () => {
      const payload = {
        input: input.value.trim(),
        textarea: textarea.value.trim(),
        select: select.hidden ? "" : select.value,
      };
      if (config.validate) {
        const maybeError = config.validate(payload);
        if (maybeError) {
          error.textContent = maybeError;
          return;
        }
      }
      close();
      resolve(payload);
    };
  });
}
function artifactSummaryItems(items) {
  return (items || [])
    .map(
      (artifact) => `
        <div class="artifact-item">
          <div class="event-meta"><strong>${artifact.artifact_type || "artifact"}</strong><span>${artifact.artifact_id || "n/a"}</span></div>
          <div class="muted" style="margin-top:6px">${artifact.uri || "uri unavailable"}${artifact.content_type ? ` · ${artifact.content_type}` : ""}</div>
        </div>
      `,
    )
    .join("");
}

function escapeHtml(value) {
  return String(value || "").replace(
    /[&<>"']/g,
    (match) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[match] || match,
  );
}
