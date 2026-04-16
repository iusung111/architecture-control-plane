"""Long-session scenario runner for remote workspace flows.

This script exercises the control-plane path that matters in staging:
1. create/update a persistent session
2. request remote execution
3. optionally hibernate + resume the session
4. fetch the resume snapshot and execution state

It is still safe for dry-runs because it only talks to configured ACP APIs.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
HEADERS = {
    "X-User-Id": os.getenv("USER_ID", "load-tester"),
    "X-User-Role": os.getenv("USER_ROLE", "operator"),
}
PROJECT_ID = os.getenv("PROJECT_ID", "proj-load")
REPO_URL = os.getenv("REPO_URL", "https://github.com/example/repo")
REPO_BRANCH = os.getenv("REPO_BRANCH", "main")
CONCURRENCY = max(1, int(os.getenv("CONCURRENCY", "3")))
HIBERNATE_AFTER_RUN = os.getenv("HIBERNATE_AFTER_RUN", "true").lower() == "true"
EXECUTOR_KEY = os.getenv("EXECUTOR_KEY", "planning")
EXECUTION_COMMAND = os.getenv("EXECUTION_COMMAND", "pytest -q")
TIMEOUT_SECONDS = float(os.getenv("TIMEOUT_SECONDS", "20"))


@dataclass(slots=True)
class ScenarioResult:
    workspace_id: str
    created_status: int
    execution_status: int
    resume_status: int
    hibernate_status: int | None
    latest_execution_state: str | None


async def _json_or_text(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text


async def _run_scenario(client: httpx.AsyncClient, idx: int) -> ScenarioResult:
    workspace_id = f"ws-long-session-{idx}"
    created = await client.post(
        "/v1/remote-workspaces/persistent/sessions",
        headers=HEADERS,
        json={
            "workspace_id": workspace_id,
            "project_id": PROJECT_ID,
            "repo_url": REPO_URL,
            "repo_branch": REPO_BRANCH,
            "note": f"load scenario {idx}",
        },
    )

    execution = await client.post(
        "/v1/remote-workspaces/executions",
        headers=HEADERS,
        json={
            "workspace_id": workspace_id,
            "project_id": PROJECT_ID,
            "repo_url": REPO_URL,
            "repo_branch": REPO_BRANCH,
            "executor_key": EXECUTOR_KEY,
            "execution_kind": "run_checks",
            "command": EXECUTION_COMMAND,
        },
    )

    hibernate_status: int | None = None
    if HIBERNATE_AFTER_RUN:
        hibernated = await client.post(
            f"/v1/remote-workspaces/persistent/sessions/{workspace_id}/hibernate",
            headers=HEADERS,
        )
        hibernate_status = hibernated.status_code
        await client.post(
            "/v1/remote-workspaces/persistent/sessions",
            headers=HEADERS,
            json={
                "workspace_id": workspace_id,
                "project_id": PROJECT_ID,
                "repo_url": REPO_URL,
                "repo_branch": REPO_BRANCH,
                "note": f"resume scenario {idx}",
            },
        )

    resume = await client.get(f"/v1/remote-workspaces/{workspace_id}/resume", headers=HEADERS)
    executions = await client.get(f"/v1/remote-workspaces/{workspace_id}/executions", headers=HEADERS)
    execution_payload = await _json_or_text(executions)
    latest_state = None
    if isinstance(execution_payload, dict):
        items = (((execution_payload.get("data") or {}).get("items")) or [])
        if items:
            latest_state = items[0].get("status")

    return ScenarioResult(
        workspace_id=workspace_id,
        created_status=created.status_code,
        execution_status=execution.status_code,
        resume_status=resume.status_code,
        hibernate_status=hibernate_status,
        latest_execution_state=latest_state,
    )


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT_SECONDS) as client:
        results = await asyncio.gather(*[_run_scenario(client, idx) for idx in range(CONCURRENCY)])
    print(
        {
            "base_url": BASE_URL,
            "concurrency": CONCURRENCY,
            "executor_key": EXECUTOR_KEY,
            "hibernate_after_run": HIBERNATE_AFTER_RUN,
            "results": [result.__dict__ for result in results],
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
