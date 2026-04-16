from __future__ import annotations

from .workspace_discussions import (
    _build_workspace_discussion_view,
    _comment_from_audit,
    _ensure_workspace_discussion_event,
    _ensure_workspace_discussion_root_event,
    _workspace_discussion_from_audit,
    _workspace_discussion_reply_from_audit,
)
from app.core.auth import AuthContext
from typing import Any


def _normalize_mentions(mentions: list[str]) -> list[str]:
    return [item.strip() for item in mentions if item and item.strip()]


class CycleWriteWorkspaceCommentMixin:
    def add_cycle_comment(
        self, cycle_id: str, *, body: str, mentions: list[str], auth: AuthContext
    ) -> dict[str, Any]:
        normalized_mentions = _normalize_mentions(mentions)

        with self._uow:
            cycle = self._cycle_repo.get_by_id(cycle_id)
            if cycle is None:
                raise ValueError("cycle not found")

            self._ensure_access(cycle, auth)
            event = self._audit_repo.add(
                event_type="cycle.comment.added",
                cycle_id=cycle_id,
                actor_id=auth.user_id,
                event_payload={
                    "body": body.strip(),
                    "mentions": normalized_mentions,
                    "actor_role": auth.role,
                },
            )
            self._uow.commit()

        return _comment_from_audit(event)

    def add_workspace_discussion(
        self, *, project_id: str | None, body: str, mentions: list[str], auth: AuthContext
    ) -> dict[str, Any]:
        normalized_mentions = _normalize_mentions(mentions)

        with self._uow:
            event = self._audit_repo.add(
                event_type="workspace.comment.added",
                actor_id=auth.user_id,
                event_payload={
                    "project_id": project_id,
                    "tenant_id": auth.tenant_id,
                    "body": body.strip(),
                    "mentions": normalized_mentions,
                    "actor_role": auth.role,
                },
            )
            self._uow.commit()

        built = _build_workspace_discussion_view(
            self._audit_repo,
            auth=auth,
            discussion_id=event.audit_event_id,
        )
        return built or _workspace_discussion_from_audit(event)

    def add_workspace_discussion_reply(
        self, *, discussion_id: str, body: str, mentions: list[str], auth: AuthContext
    ) -> dict[str, Any]:
        parent = _ensure_workspace_discussion_event(
            self._audit_repo,
            discussion_id=discussion_id,
            auth=auth,
        )
        parent_payload = parent.event_payload if isinstance(parent.event_payload, dict) else {}
        normalized_mentions = _normalize_mentions(mentions)

        with self._uow:
            event = self._audit_repo.add(
                event_type="workspace.comment.reply.added",
                actor_id=auth.user_id,
                event_payload={
                    "discussion_id": discussion_id,
                    "project_id": parent_payload.get("project_id"),
                    "tenant_id": parent_payload.get("tenant_id", auth.tenant_id),
                    "body": body.strip(),
                    "mentions": normalized_mentions,
                    "actor_role": auth.role,
                },
            )
            self._uow.commit()

        return _workspace_discussion_reply_from_audit(event)

    def set_workspace_discussion_resolved(
        self, *, discussion_id: str, resolved: bool, note: str | None, auth: AuthContext
    ) -> dict[str, Any]:
        root = _ensure_workspace_discussion_root_event(
            self._audit_repo,
            discussion_id=discussion_id,
            auth=auth,
        )
        root_payload = root.event_payload if isinstance(root.event_payload, dict) else {}

        with self._uow:
            self._audit_repo.add(
                event_type="workspace.comment.resolution_changed",
                actor_id=auth.user_id,
                event_payload={
                    "discussion_id": discussion_id,
                    "project_id": root_payload.get("project_id"),
                    "tenant_id": root_payload.get("tenant_id", auth.tenant_id),
                    "resolved": bool(resolved),
                    "note": note.strip() if note else None,
                    "actor_role": auth.role,
                },
            )
            self._uow.commit()

        built = _build_workspace_discussion_view(
            self._audit_repo,
            auth=auth,
            discussion_id=discussion_id,
        )
        if built is None:
            raise ValueError("discussion not found")

        return built

    def set_workspace_discussion_pinned(
        self, *, discussion_id: str, pinned: bool, note: str | None, auth: AuthContext
    ) -> dict[str, Any]:
        root = _ensure_workspace_discussion_root_event(
            self._audit_repo,
            discussion_id=discussion_id,
            auth=auth,
        )
        root_payload = root.event_payload if isinstance(root.event_payload, dict) else {}

        with self._uow:
            self._audit_repo.add(
                event_type="workspace.comment.pin_changed",
                actor_id=auth.user_id,
                event_payload={
                    "discussion_id": discussion_id,
                    "project_id": root_payload.get("project_id"),
                    "tenant_id": root_payload.get("tenant_id", auth.tenant_id),
                    "pinned": bool(pinned),
                    "note": note.strip() if note else None,
                    "actor_role": auth.role,
                },
            )
            self._uow.commit()

        built = _build_workspace_discussion_view(
            self._audit_repo,
            auth=auth,
            discussion_id=discussion_id,
        )
        if built is None:
            raise ValueError("discussion not found")

        return built
