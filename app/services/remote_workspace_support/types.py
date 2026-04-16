from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


EXECUTION_TERMINAL_STATES = {"succeeded", "failed", "cancelled", "dispatch_failed", "timed_out"}
EXECUTION_ACTIVE_STATES = {"queued", "requested", "dispatching", "running", "acknowledged"}


@dataclass(slots=True)
class WorkspaceExecutionRequest:
    workspace_id: str
    execution_kind: str
    command: str | None = None
    patch: str | None = None
    repo_url: str | None = None
    repo_branch: str | None = None
    repo_ref: str | None = None
    cycle_id: str | None = None
    project_id: str | None = None
    execution_profile: str | None = None
    executor_key: str | None = None
    metadata: dict[str, Any] | None = None
    execution_id: str | None = None


@dataclass(slots=True)
class WorkspaceExecutionResult:
    execution_id: str
    workspace_id: str
    execution_kind: str
    status: str
    executor_key: str
    requested_at: datetime
    message: str | None = None
    metadata: dict[str, Any] | None = None


class RemoteWorkspaceExecutor(ABC):
    key: str
    name: str
    mode: str
    description: str
    capabilities: tuple[str, ...]

    @property
    def enabled(self) -> bool:
        return True

    def descriptor(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "mode": self.mode,
            "enabled": self.enabled,
            "description": self.description,
            "capabilities": list(self.capabilities),
        }

    @abstractmethod
    def prepare_workspace(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        raise NotImplementedError

    @abstractmethod
    def run_checks(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        raise NotImplementedError

    @abstractmethod
    def apply_patch(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        raise NotImplementedError

    @abstractmethod
    def collect_artifacts(self, workspace_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def resume_snapshot(self, workspace_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def cancel_execution(self, execution_id: str, metadata: dict[str, Any] | None = None) -> bool:
        raise NotImplementedError


class PlanningRemoteWorkspaceExecutor(RemoteWorkspaceExecutor):
    key = "planning"
    name = "Planning-only executor"
    mode = "phase1"
    description = "Records remote run intents without starting external compute."
    capabilities = ("prepare", "queue_intent", "resume_snapshot", "collect_artifacts", "cancel_execution")

    def _result(self, request: WorkspaceExecutionRequest, *, status: str, message: str) -> WorkspaceExecutionResult:
        return WorkspaceExecutionResult(
            execution_id=request.execution_id or uuid4().hex,
            workspace_id=request.workspace_id,
            execution_kind=request.execution_kind,
            status=status,
            executor_key=self.key,
            requested_at=datetime.now(UTC),
            message=message,
            metadata=request.metadata or {},
        )

    def prepare_workspace(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        return self._result(request, status="prepared", message="remote workspace snapshot prepared")

    def run_checks(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        return self._result(request, status="planned", message="remote execution intent recorded for a later executor")

    def apply_patch(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        return self._result(request, status="planned", message="patch-and-test intent recorded for a later executor")

    def collect_artifacts(self, workspace_id: str) -> list[dict[str, Any]]:
        del workspace_id
        return []

    def resume_snapshot(self, workspace_id: str) -> dict[str, Any] | None:
        del workspace_id
        return None

    def cancel_execution(self, execution_id: str, metadata: dict[str, Any] | None = None) -> bool:
        del execution_id, metadata
        return False
