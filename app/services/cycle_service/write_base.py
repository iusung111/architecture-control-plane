from __future__ import annotations

import json

from app.core.auth import AuthContext
from app.db.models import Cycle, Receipt
from app.domain.enums import CycleState, JobType, UserStatus
from app.domain.guards import StateConflictError
from app.domain.tenancy import normalize_tenant_scope
from app.repositories.audit import AuditEventRepository
from app.repositories.cycles import CycleRepository
from app.repositories.jobs import JobRepository
from app.repositories.outbox import OutboxRepository
from app.schemas.cycles import CreateCycleRequest
from app.services.unit_of_work import SqlAlchemyUnitOfWork
from datetime import datetime, timezone
from hashlib import sha256
from sqlalchemy.exc import IntegrityError
from uuid import uuid4


class CycleWriteBaseMixin:
    def __init__(
        self,
        cycle_repo: CycleRepository,
        job_repo: JobRepository,
        outbox_repo: OutboxRepository,
        audit_repo: AuditEventRepository,
        uow: SqlAlchemyUnitOfWork,
    ):
        self._cycle_repo = cycle_repo
        self._job_repo = job_repo
        self._outbox_repo = outbox_repo
        self._audit_repo = audit_repo
        self._uow = uow

    @staticmethod
    def _ensure_access(cycle: Cycle, auth: AuthContext) -> None:
        if cycle.owner_user_id != auth.user_id:
            raise PermissionError("forbidden")
        if auth.tenant_id is not None and cycle.tenant_id != auth.tenant_id:
            raise PermissionError("forbidden")

    @staticmethod
    def _resolve_effective_tenant(
        auth_tenant_id: str | None, payload_tenant_id: str | None
    ) -> str | None:
        if (
            auth_tenant_id is not None
            and payload_tenant_id is not None
            and auth_tenant_id != payload_tenant_id
        ):
            raise PermissionError("tenant mismatch between auth context and payload")
        return auth_tenant_id or payload_tenant_id

    @staticmethod
    def _fingerprint_create_request(
        payload: CreateCycleRequest, owner_user_id: str, tenant_id: str | None
    ) -> str:
        normalized = {
            "owner_user_id": owner_user_id,
            "tenant_id": tenant_id,
            "project_id": payload.project_id,
            "user_input": payload.user_input,
            "input_artifacts": [
                artifact.model_dump(mode="json") for artifact in payload.input_artifacts
            ],
            "metadata": payload.metadata,
        }
        return sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _record_audit_event(
        self,
        *,
        event_type: str,
        actor_id: str | None,
        cycle_id: str | None = None,
        approval_id: str | None = None,
        payload: dict | None = None,
    ) -> None:
        self._audit_repo.add(
            event_type=event_type,
            cycle_id=cycle_id,
            approval_id=approval_id,
            actor_id=actor_id,
            event_payload=payload or {},
        )

    def create_cycle(
        self, payload: CreateCycleRequest, auth: AuthContext, idempotency_key: str
    ) -> tuple[bool, dict]:
        effective_tenant_id = self._resolve_effective_tenant(auth.tenant_id, payload.tenant_id)
        tenant_scope = normalize_tenant_scope(effective_tenant_id)
        fingerprint = self._fingerprint_create_request(
            payload, owner_user_id=auth.user_id, tenant_id=effective_tenant_id
        )
        existing = self._cycle_repo.get_by_idempotency(
            auth.user_id, tenant_scope, payload.project_id, idempotency_key
        )
        if existing:
            if existing.request_fingerprint != fingerprint:
                raise StateConflictError("idempotency key reused with different request payload")
            return False, {
                "cycle_id": existing.cycle_id,
                "state": existing.current_state,
                "user_status": existing.user_status,
                "next_action": None,
                "approval_required": False,
                "created_at": existing.created_at,
            }

        cycle = Cycle(
            cycle_id=str(uuid4()),
            tenant_id=effective_tenant_id,
            tenant_scope=tenant_scope,
            project_id=payload.project_id,
            owner_user_id=auth.user_id,
            current_state=CycleState.INTENT_ACCEPTED,
            user_status=UserStatus.ACCEPTED,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
        )
        try:
            with self._uow:
                self._cycle_repo.add(cycle)
                request_snapshot = Receipt(
                    receipt_id=uuid4().hex,
                    cycle_id=cycle.cycle_id,
                    iteration_id=None,
                    receipt_type="request_snapshot",
                    summary="initial request snapshot",
                    payload={
                        "project_id": payload.project_id,
                        "user_input": payload.user_input,
                        "tenant_id": effective_tenant_id,
                        "input_artifacts": [
                            artifact.model_dump(mode="json") for artifact in payload.input_artifacts
                        ],
                        "metadata": payload.metadata,
                        "override_input": {},
                    },
                )
                self._uow.session.add(request_snapshot)
                self._job_repo.enqueue(
                    cycle_id=cycle.cycle_id,
                    job_type=JobType.RUN_VERIFICATION,
                    payload=request_snapshot.payload
                    | {
                        "trigger": "create",
                        "requested_by": auth.user_id,
                        "input_snapshot_ref": request_snapshot.receipt_id,
                    },
                    dedup_key=f"run_verification:create:{cycle.cycle_id}",
                    max_attempts=3,
                    priority=50,
                )
                self._outbox_repo.add(
                    cycle.cycle_id, "cycle.accepted", {"cycle_id": cycle.cycle_id}
                )
                self._record_audit_event(
                    event_type="cycle.created",
                    actor_id=auth.user_id,
                    cycle_id=cycle.cycle_id,
                    payload={
                        "project_id": payload.project_id,
                        "tenant_id": effective_tenant_id,
                        "state": cycle.current_state,
                        "user_status": cycle.user_status,
                        "idempotency_key": idempotency_key,
                    },
                )
                self._uow.commit()
        except IntegrityError as exc:
            self._uow.rollback()
            existing = self._cycle_repo.get_by_idempotency(
                auth.user_id, tenant_scope, payload.project_id, idempotency_key
            )
            if existing is None:
                raise
            if existing.request_fingerprint != fingerprint:
                raise StateConflictError(
                    "idempotency key reused with different request payload"
                ) from exc
            return False, {
                "cycle_id": existing.cycle_id,
                "state": existing.current_state,
                "user_status": existing.user_status,
                "next_action": None,
                "approval_required": False,
                "created_at": existing.created_at,
            }
        return True, {
            "cycle_id": cycle.cycle_id,
            "state": cycle.current_state,
            "user_status": cycle.user_status,
            "next_action": None,
            "approval_required": False,
            "created_at": cycle.created_at or datetime.now(timezone.utc),
        }
