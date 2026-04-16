from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.core.config import Settings

from .types import RemoteWorkspaceExecutor, WorkspaceExecutionRequest, WorkspaceExecutionResult


class GitHubActionsRemoteWorkspaceExecutor(RemoteWorkspaceExecutor):
    key = "github_actions"
    name = "GitHub Actions executor"
    mode = "ephemeral_remote"
    description = "Dispatches remote lint/build/test runs to GitHub Actions and awaits callback results."
    capabilities = (
        "prepare",
        "run_checks",
        "apply_patch",
        "collect_artifacts",
        "cancel_execution",
        "callback_results",
    )

    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return bool(
            self._settings.remote_workspace_github_repository
            and self._settings.remote_workspace_github_workflow
            and self._settings.remote_workspace_github_token
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.remote_workspace_github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _workflow_runs_api_url(self) -> str:
        return (
            f"{self._settings.remote_workspace_github_api_base_url.rstrip('/')}/repos/"
            f"{self._settings.remote_workspace_github_repository}/actions/workflows/"
            f"{self._settings.remote_workspace_github_workflow}/runs"
        )

    def _cancel_run_api_url(self, github_run_id: int | str) -> str:
        return (
            f"{self._settings.remote_workspace_github_api_base_url.rstrip('/')}/repos/"
            f"{self._settings.remote_workspace_github_repository}/actions/runs/{github_run_id}/cancel"
        )

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _resolve_github_run(self, *, execution_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        threshold = self._parse_datetime((metadata or {}).get("dispatch_requested_at"))
        params = {
            "event": "workflow_dispatch",
            "branch": self._settings.remote_workspace_github_ref,
            "per_page": 20,
        }
        try:
            with httpx.Client(timeout=self._settings.remote_workspace_dispatch_timeout_seconds) as client:
                response = client.get(self._workflow_runs_api_url(), headers=self._headers(), params=params)
            if response.status_code >= 400:
                return None
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return None

        runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
        if not isinstance(runs, list):
            return None

        fallback: dict[str, Any] | None = None
        for item in runs:
            if not isinstance(item, dict):
                continue
            run_id = item.get("id")
            if not run_id:
                continue
            created_at = self._parse_datetime(item.get("created_at"))
            if threshold and created_at and created_at < threshold:
                continue
            display = " ".join(str(item.get(key) or "") for key in ("display_title", "name", "head_branch", "event"))
            candidate = {
                "github_run_id": run_id,
                "github_run_url": item.get("html_url"),
                "github_run_status": item.get("status"),
                "github_run_conclusion": item.get("conclusion"),
            }
            if execution_id and execution_id in display:
                return candidate
            if fallback is None:
                fallback = candidate
        return fallback

    def _result(
        self,
        request: WorkspaceExecutionRequest,
        *,
        status: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> WorkspaceExecutionResult:
        return WorkspaceExecutionResult(
            execution_id=request.execution_id or uuid4().hex,
            workspace_id=request.workspace_id,
            execution_kind=request.execution_kind,
            status=status,
            executor_key=self.key,
            requested_at=datetime.now(UTC),
            message=message,
            metadata=metadata or (request.metadata or {}),
        )

    def _dispatch(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        if not self.enabled:
            return self._result(request, status="unconfigured", message="GitHub Actions executor is not configured")

        execution_id = request.execution_id or uuid4().hex
        requested_at = datetime.now(UTC)
        api_url = (
            f"{self._settings.remote_workspace_github_api_base_url.rstrip('/')}/repos/"
            f"{self._settings.remote_workspace_github_repository}/actions/workflows/"
            f"{self._settings.remote_workspace_github_workflow}/dispatches"
        )
        metadata = dict(request.metadata or {})
        payload_inputs = {
            "execution_id": execution_id,
            "workspace_id": request.workspace_id,
            "execution_kind": request.execution_kind,
            "command": request.command or "",
            "repo_url": request.repo_url or "",
            "repo_branch": request.repo_branch or "",
            "repo_ref": request.repo_ref or "",
            "patch": request.patch or "",
            "callback_url": self._settings.remote_workspace_callback_url or "",
            "metadata_json": json.dumps(metadata, separators=(",", ":")),
        }
        body = {"ref": self._settings.remote_workspace_github_ref, "inputs": payload_inputs}
        with httpx.Client(timeout=self._settings.remote_workspace_dispatch_timeout_seconds) as client:
            response = client.post(api_url, headers=self._headers(), json=body)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"remote executor dispatch failed: github actions returned {response.status_code}")

        dispatch_metadata = {
            **metadata,
            "dispatch_url": api_url,
            "repository": self._settings.remote_workspace_github_repository,
            "workflow": self._settings.remote_workspace_github_workflow,
            "dispatch_requested_at": requested_at.isoformat(),
            "github_workflow_runs_url": self._workflow_runs_api_url(),
        }
        return WorkspaceExecutionResult(
            execution_id=execution_id,
            workspace_id=request.workspace_id,
            execution_kind=request.execution_kind,
            status="queued",
            executor_key=self.key,
            requested_at=requested_at,
            message="remote execution dispatched to GitHub Actions",
            metadata=dispatch_metadata,
        )

    def prepare_workspace(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        return self._dispatch(request)

    def run_checks(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        return self._dispatch(request)

    def apply_patch(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        return self._dispatch(request)

    def collect_artifacts(self, workspace_id: str) -> list[dict[str, Any]]:
        del workspace_id
        return []

    def resume_snapshot(self, workspace_id: str) -> dict[str, Any] | None:
        del workspace_id
        return None

    def cancel_execution(self, execution_id: str, metadata: dict[str, Any] | None = None) -> bool:
        if not self.enabled:
            return False
        github_run_id = (metadata or {}).get("github_run_id")
        if not github_run_id:
            resolved = self._resolve_github_run(execution_id=execution_id, metadata=metadata)
            github_run_id = (resolved or {}).get("github_run_id")
        if not github_run_id:
            return False
        with httpx.Client(timeout=self._settings.remote_workspace_dispatch_timeout_seconds) as client:
            response = client.post(self._cancel_run_api_url(github_run_id), headers=self._headers())
        return response.status_code < 400
