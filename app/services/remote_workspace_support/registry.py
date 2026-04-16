from __future__ import annotations

from app.core.config import Settings
from app.repositories.audit import AuditEventRepository

from .github_executor import GitHubActionsRemoteWorkspaceExecutor
from .persistent import OptionalPersistentRemoteWorkspaceExecutor
from .types import PlanningRemoteWorkspaceExecutor, RemoteWorkspaceExecutor


class RemoteWorkspaceExecutorRegistry:
    def __init__(self, settings: Settings, audit_repo: AuditEventRepository | None = None):
        self._executors: dict[str, RemoteWorkspaceExecutor] = {
            "planning": PlanningRemoteWorkspaceExecutor(),
            "github_actions": GitHubActionsRemoteWorkspaceExecutor(settings),
            "persistent": OptionalPersistentRemoteWorkspaceExecutor(settings, audit_repo),
        }

    def get(self, key: str | None) -> RemoteWorkspaceExecutor:
        if key and key in self._executors:
            return self._executors[key]
        return self._executors["planning"]

    def list(self) -> list[dict[str, object]]:
        return [executor.descriptor() for executor in self._executors.values()]
