from __future__ import annotations

from .workspace_filters import (
    _build_workspace_discussion_saved_filter_view,
    _ensure_workspace_discussion_saved_filter_event,
    _workspace_discussion_saved_filter_from_audit,
)
from app.core.auth import AuthContext
from typing import Any


def _normalized_optional_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None

    stripped = value.strip()
    return stripped or None


class CycleWriteWorkspaceFilterMixin:
    def save_workspace_discussion_filter(
        self,
        *,
        name: str,
        project_id: str | None,
        mention: str | None,
        query: str | None,
        auth: AuthContext,
    ) -> dict[str, Any]:
        with self._uow:
            event = self._audit_repo.add(
                event_type="workspace.comment.filter.saved",
                actor_id=auth.user_id,
                event_payload={
                    "tenant_id": auth.tenant_id,
                    "name": name.strip(),
                    "project_id": project_id,
                    "mention": _normalized_optional_text(mention),
                    "query": _normalized_optional_text(query),
                },
            )
            self._uow.commit()

        return _workspace_discussion_saved_filter_from_audit(event)

    def update_workspace_discussion_filter(
        self,
        *,
        filter_id: str,
        name: str,
        project_id: str | None,
        mention: str | None,
        query: str | None,
        auth: AuthContext,
    ) -> dict[str, Any]:
        existing = _ensure_workspace_discussion_saved_filter_event(
            self._audit_repo,
            filter_id=filter_id,
            auth=auth,
        )
        payload = existing.event_payload if isinstance(existing.event_payload, dict) else {}

        with self._uow:
            self._audit_repo.add(
                event_type="workspace.comment.filter.updated",
                actor_id=auth.user_id,
                event_payload={
                    "filter_id": filter_id,
                    "tenant_id": payload.get("tenant_id", auth.tenant_id),
                    "name": name.strip(),
                    "project_id": project_id,
                    "mention": _normalized_optional_text(mention),
                    "query": _normalized_optional_text(query),
                },
            )
            self._uow.commit()

        built = _build_workspace_discussion_saved_filter_view(
            self._audit_repo,
            auth=auth,
            filter_id=filter_id,
        )
        return built or _workspace_discussion_saved_filter_from_audit(existing)

    def set_workspace_discussion_filter_favorite(
        self, *, filter_id: str, is_favorite: bool, auth: AuthContext
    ) -> dict[str, Any]:
        existing = _ensure_workspace_discussion_saved_filter_event(
            self._audit_repo,
            filter_id=filter_id,
            auth=auth,
        )
        payload = existing.event_payload if isinstance(existing.event_payload, dict) else {}

        with self._uow:
            self._audit_repo.add(
                event_type="workspace.comment.filter.favorited",
                actor_id=auth.user_id,
                event_payload={
                    "filter_id": filter_id,
                    "tenant_id": payload.get("tenant_id", auth.tenant_id),
                    "is_favorite": bool(is_favorite),
                },
            )
            self._uow.commit()

        built = _build_workspace_discussion_saved_filter_view(
            self._audit_repo,
            auth=auth,
            filter_id=filter_id,
        )
        return built or _workspace_discussion_saved_filter_from_audit(existing)

    def mark_workspace_discussion_filter_used(
        self, *, filter_id: str, auth: AuthContext
    ) -> dict[str, Any]:
        existing = _ensure_workspace_discussion_saved_filter_event(
            self._audit_repo,
            filter_id=filter_id,
            auth=auth,
        )
        payload = existing.event_payload if isinstance(existing.event_payload, dict) else {}

        with self._uow:
            self._audit_repo.add(
                event_type="workspace.comment.filter.used",
                actor_id=auth.user_id,
                event_payload={
                    "filter_id": filter_id,
                    "tenant_id": payload.get("tenant_id", auth.tenant_id),
                },
            )
            self._uow.commit()

        built = _build_workspace_discussion_saved_filter_view(
            self._audit_repo,
            auth=auth,
            filter_id=filter_id,
        )
        return built or _workspace_discussion_saved_filter_from_audit(existing)

    def delete_workspace_discussion_filter(
        self, *, filter_id: str, auth: AuthContext
    ) -> dict[str, Any]:
        existing = _ensure_workspace_discussion_saved_filter_event(
            self._audit_repo,
            filter_id=filter_id,
            auth=auth,
        )
        payload = existing.event_payload if isinstance(existing.event_payload, dict) else {}

        with self._uow:
            self._audit_repo.add(
                event_type="workspace.comment.filter.deleted",
                actor_id=auth.user_id,
                event_payload={
                    "filter_id": filter_id,
                    "tenant_id": payload.get("tenant_id", auth.tenant_id),
                    "is_deleted": True,
                },
            )
            self._uow.commit()

        built = _build_workspace_discussion_saved_filter_view(
            self._audit_repo,
            auth=auth,
            filter_id=filter_id,
        )
        return built or {**_workspace_discussion_saved_filter_from_audit(existing), "is_deleted": True}
