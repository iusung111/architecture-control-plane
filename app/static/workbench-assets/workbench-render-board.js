function cardHtml(item) {
  const statusPills = [
    `<span class="pill">state: ${item.state}</span>`,
    `<span class="pill">user: ${item.user_status}</span>`,
    item.approval_required ? '<span class="pill">approval</span>' : "",
    item.retry_allowed ? '<span class="pill">retry</span>' : "",
    item.replan_allowed ? '<span class="pill">replan</span>' : "",
  ].join(" ");
  return `
        <button class="card ${item.cycle_id === selectedCycleId ? "selected" : ""}" data-cycle-id="${item.cycle_id}">
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
  boardColumnsEl.innerHTML = board.columns
    .map(
      (column) => `
        <section class="column">
          <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
            <div>
              <h3>${column.title}</h3>
              <small>${column.description || ""}</small>
            </div>
            <span class="count">${column.count}</span>
          </div>
          ${column.items.length ? column.items.map(cardHtml).join("") : '<div class="empty">No cycles in this column.</div>'}
        </section>
      `,
    )
    .join("");
  document.querySelectorAll("[data-cycle-id]").forEach((button) => {
    button.addEventListener("click", () => selectCycle(button.dataset.cycleId));
  });
  lastSyncEl.textContent = `Last board update: ${nowLabel()}`;
}
function pushStreamItem(eventName, payload) {
  const wrapper = document.createElement("div");
  wrapper.className = "stream-item";
  wrapper.innerHTML = `<div class="event-meta"><strong>${eventName}</strong><span>${nowLabel()}</span></div><pre>${JSON.stringify(payload, null, 2)}</pre>`;
  streamLogEl.prepend(wrapper);
  while (streamLogEl.children.length > 24) streamLogEl.removeChild(streamLogEl.lastChild);
}
