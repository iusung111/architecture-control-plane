from __future__ import annotations

from app.core.auth import AuthContext
from app.domain.enums import CycleState
from app.domain.guards import StateConflictError
from app.db.session import get_session_factory
from app.repositories.cycles import CycleRepository
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CycleStreamSnapshot:
    summary: dict[str, Any]
    result: dict[str, Any] | None
    terminal: bool


class CycleStreamService:
    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def get_snapshot(self, cycle_id: str, auth: AuthContext) -> CycleStreamSnapshot | None:
        from . import CycleQueryService

        with self._session_factory() as db:
            query_service = CycleQueryService(cycle_repo=CycleRepository(db))
            summary = query_service.get_cycle_summary(cycle_id, auth)
            if summary is None:
                return None
            terminal = summary["state"] in {CycleState.TERMINALIZED, CycleState.TERMINAL_FAIL}
            result = None
            if terminal:
                try:
                    result = query_service.get_cycle_result(cycle_id, auth)
                except StateConflictError:
                    result = None
            return CycleStreamSnapshot(summary=summary, result=result, terminal=terminal)
