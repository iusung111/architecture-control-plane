from __future__ import annotations

from app.core.config import Settings
from app.repositories.audit import AuditEventRepository
from app.services.unit_of_work import SqlAlchemyUnitOfWork

from .registry import RemoteWorkspaceExecutorRegistry
from .write_execution import RemoteWorkspaceExecutionWriteMixin
from .write_state import RemoteWorkspaceWriteStateMixin
from .write_views import RemoteWorkspaceViewWriteMixin


class RemoteWorkspaceWriteService(
    RemoteWorkspaceExecutionWriteMixin,
    RemoteWorkspaceViewWriteMixin,
    RemoteWorkspaceWriteStateMixin,
):
    def __init__(self, audit_repo: AuditEventRepository, uow: SqlAlchemyUnitOfWork, settings: Settings):
        self._audit_repo = audit_repo
        self._uow = uow
        self._registry = RemoteWorkspaceExecutorRegistry(settings, audit_repo)
        self._settings = settings
