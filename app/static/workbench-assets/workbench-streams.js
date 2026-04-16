async function consumeSSE(url, onEvent, stateEl, controller) {
  const response = await fetch(url, { headers: authHeaders(), signal: controller.signal });
  if (!response.ok) {
    const maybeJson = await response.json().catch(() => null);
    throw new Error(maybeJson?.error?.message || `Stream failed (${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  setStatus(stateEl, "connected");
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const lines = chunk.split("\n");
      let eventName = "message";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      let payload = data;
      try {
        payload = JSON.parse(data);
      } catch (_) {}
      onEvent(eventName, payload);
    }
  }
  setStatus(stateEl, "closed");
}
function stopStreams() {
  if (boardAbortController) boardAbortController.abort();
  if (cycleAbortController) cycleAbortController.abort();
  if (runtimeActionAbortController) runtimeActionAbortController.abort();
  boardAbortController = null;
  cycleAbortController = null;
  runtimeActionAbortController = null;
  setStatus(boardStateEl, "idle");
  setStatus(cycleStateEl, "idle");
  setStatus(runtimeActionStateEl, "idle");
}
async function startBoardStream() {
  if (boardAbortController) boardAbortController.abort();
  boardAbortController = new AbortController();
  setStatus(boardStateEl, "connecting");
  const projectId = document.getElementById("project-filter").value.trim();
  const limit = document.getElementById("board-limit").value || "12";
  try {
    await consumeSSE(
      `/v1/cycles/board/events${qs({ project_id: projectId, limit_per_column: limit, poll_interval_seconds: 2, heartbeat_seconds: 15, stream_timeout_seconds: 600 })}`,
      (eventName, payload) => {
        if (eventName === "board.snapshot" && payload.board) renderBoard(payload.board);
        if (eventName !== "heartbeat") pushStreamItem(`board:${eventName}`, payload);
      },
      boardStateEl,
      boardAbortController,
    );
  } catch (error) {
    setStatus(boardStateEl, `error: ${error.message}`);
  }
}
async function startCycleStream(cycleId) {
  if (!cycleId) return;
  if (cycleAbortController) cycleAbortController.abort();
  cycleAbortController = new AbortController();
  setStatus(cycleStateEl, "connecting");
  try {
    await consumeSSE(
      `/v1/cycles/${encodeURIComponent(cycleId)}/events${qs({ poll_interval_seconds: 1, heartbeat_seconds: 15, stream_timeout_seconds: 600 })}`,
      (eventName, payload) => {
        pushStreamItem(`cycle:${eventName}`, payload);
        if (eventName === "cycle.snapshot" || eventName === "cycle.result") {
          refreshTimeline(cycleId);
          refreshComments(cycleId);
          refreshWorkspaceSurfaces();
        }
      },
      cycleStateEl,
      cycleAbortController,
    );
  } catch (error) {
    setStatus(cycleStateEl, `error: ${error.message}`);
  }
}
