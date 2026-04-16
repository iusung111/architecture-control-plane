
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Header
from subprocess import TimeoutExpired

from app.api.deps import (
    get_audit_event_repository,
    get_management_config_service,
    get_request_id,
    require_management_admin,
    require_management_operator,
    require_management_access,
)
from app.core.management_auth import ManagementAuthContext
from app.repositories.audit import AuditEventRepository
from app.schemas.admin_ops import (
    BackupDrillJobStatusEnvelope,
    BackupDrillJobStatusResponse,
    BackupDrillPreviewEnvelope,
    BackupDrillPreviewResponse,
    BackupDrillRunEnvelope,
    BackupDrillRunRequest,
    BackupDrillAcceptedResponse,
    ManagementConfigEnvelope,
    ManagementConfigResponseModel,
    ManagementConfigUpdateRequest,
)
from app.schemas.common import ErrorEnvelope, envelope_accepted, envelope_ok
from app.services.management_config import ManagementConfigService

router = APIRouter(prefix="/admin/ops", tags=["admin-ops"])


def _record_audit(
    audit_repo: AuditEventRepository,
    *,
    management_ctx: ManagementAuthContext,
    event_type: str,
    request_id: str,
    payload: dict,
) -> None:
    audit_repo.add(
        actor_id=management_ctx.actor_id,
        event_type=event_type,
        event_payload={
            "request_id": request_id,
            "management_role": management_ctx.role,
            "management_key_source": management_ctx.key_source,
            "management_key_fingerprint": management_ctx.key_fingerprint,
            **payload,
        },
    )


@router.get("/abuse/config", response_model=ManagementConfigEnvelope, responses={403: {"model": ErrorEnvelope}})
def get_abuse_config(
    request_id: str = Depends(get_request_id),
    _: ManagementAuthContext = Depends(require_management_operator),
    service: ManagementConfigService = Depends(get_management_config_service),
):
    return envelope_ok(data=ManagementConfigResponseModel.model_validate(asdict(service.get_abuse_config())), request_id=request_id)


@router.put("/abuse/config", response_model=ManagementConfigEnvelope, responses={403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}})
def update_abuse_config(
    payload: ManagementConfigUpdateRequest,
    request_id: str = Depends(get_request_id),
    management_ctx: ManagementAuthContext = Depends(require_management_admin),
    audit_repo: AuditEventRepository = Depends(get_audit_event_repository),
    service: ManagementConfigService = Depends(get_management_config_service),
):
    before = asdict(service.get_abuse_config())
    try:
        response = service.update_abuse_config(payload.payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"backup drill timed out after {exc.timeout} seconds") from exc
    _record_audit(audit_repo, management_ctx=management_ctx, event_type="management.abuse_config.updated", request_id=request_id, payload={"before": before, "after": asdict(response), "requested_changes": payload.payload})
    return envelope_ok(data=ManagementConfigResponseModel.model_validate(asdict(response)), request_id=request_id)


@router.get("/backups/config", response_model=ManagementConfigEnvelope, responses={403: {"model": ErrorEnvelope}})
def get_backup_config(
    request_id: str = Depends(get_request_id),
    _: ManagementAuthContext = Depends(require_management_operator),
    service: ManagementConfigService = Depends(get_management_config_service),
):
    return envelope_ok(data=ManagementConfigResponseModel.model_validate(asdict(service.get_backup_config())), request_id=request_id)


@router.put("/backups/config", response_model=ManagementConfigEnvelope, responses={403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}})
def update_backup_config(
    payload: ManagementConfigUpdateRequest,
    request_id: str = Depends(get_request_id),
    management_ctx: ManagementAuthContext = Depends(require_management_admin),
    audit_repo: AuditEventRepository = Depends(get_audit_event_repository),
    service: ManagementConfigService = Depends(get_management_config_service),
):
    before = asdict(service.get_backup_config())
    try:
        response = service.update_backup_config(payload.payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"backup drill timed out after {exc.timeout} seconds") from exc
    _record_audit(audit_repo, management_ctx=management_ctx, event_type="management.backup_config.updated", request_id=request_id, payload={"before": before, "after": asdict(response), "requested_changes": payload.payload})
    return envelope_ok(data=ManagementConfigResponseModel.model_validate(asdict(response)), request_id=request_id)


@router.post("/backups/drill/preview", response_model=BackupDrillPreviewEnvelope, responses={403: {"model": ErrorEnvelope}})
def preview_backup_drill(
    request_id: str = Depends(get_request_id),
    _: ManagementAuthContext = Depends(require_management_operator),
    service: ManagementConfigService = Depends(get_management_config_service),
):
    return envelope_ok(data=BackupDrillPreviewResponse.model_validate(service.build_backup_drill_preview()), request_id=request_id)


@router.post(
    "/backups/drill/run",
    response_model=BackupDrillRunEnvelope,
    responses={403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
    status_code=202,
)
def run_backup_drill(
    payload: BackupDrillRunRequest,
    request_id: str = Depends(get_request_id),
    idempotency_key: str = Header(alias="Idempotency-Key"),
    management_ctx: ManagementAuthContext = Depends(require_management_admin),
    audit_repo: AuditEventRepository = Depends(get_audit_event_repository),
    service: ManagementConfigService = Depends(get_management_config_service),
):
    try:
        queued = service.enqueue_backup_drill(
            request_id=request_id,
            idempotency_key=idempotency_key,
            actor_id=management_ctx.actor_id,
            management_role=management_ctx.role,
            management_key_source=management_ctx.key_source,
            management_key_fingerprint=management_ctx.key_fingerprint,
            target_name=payload.target_name,
            label=payload.label,
            restore_from_object_store=payload.restore_from_object_store,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _record_audit(
        audit_repo,
        management_ctx=management_ctx,
        event_type="management.backup_drill.triggered",
        request_id=request_id,
        payload={
            "target_name": queued["target_name"],
            "job_id": queued["job_id"],
            "state": queued["state"],
            "status_url": queued["status_url"],
            "requested_changes": payload.model_dump(exclude_none=True),
            "idempotency_key": idempotency_key,
            "deduplicated": queued.get("deduplicated", False),
        },
    )
    return envelope_accepted(data=BackupDrillAcceptedResponse.model_validate(queued), request_id=request_id)


@router.get("/backups/drill/jobs/{job_id}", response_model=BackupDrillJobStatusEnvelope, responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
def get_backup_drill_job_status(
    job_id: str,
    request_id: str = Depends(get_request_id),
    _: ManagementAuthContext = Depends(require_management_operator),
    service: ManagementConfigService = Depends(get_management_config_service),
):
    status_payload = service.get_backup_drill_job_status(job_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail="backup drill job not found")
    return envelope_ok(data=BackupDrillJobStatusResponse.model_validate(status_payload), request_id=request_id)


@router.delete("/backups/drill/jobs/{job_id}", response_model=BackupDrillJobStatusEnvelope, responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
def cancel_backup_drill_job(
    job_id: str,
    request_id: str = Depends(get_request_id),
    management_ctx: ManagementAuthContext = Depends(require_management_admin),
    audit_repo: AuditEventRepository = Depends(get_audit_event_repository),
    service: ManagementConfigService = Depends(get_management_config_service),
):
    status_payload = service.cancel_backup_drill(job_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail="backup drill job not found")
    _record_audit(
        audit_repo,
        management_ctx=management_ctx,
        event_type="management.backup_drill.cancel_requested",
        request_id=request_id,
        payload={
            "job_id": job_id,
            "target_name": status_payload["target_name"],
            "state": status_payload["state"],
            "stage": status_payload["stage"],
            "cancellation_requested": status_payload["cancellation_requested"],
        },
    )
    return envelope_ok(data=BackupDrillJobStatusResponse.model_validate(status_payload), request_id=request_id)


@router.get("/observability/status", response_model=ManagementConfigEnvelope, responses={403: {"model": ErrorEnvelope}})
def get_observability_status(
    request_id: str = Depends(get_request_id),
    _: ManagementAuthContext = Depends(require_management_access),
    service: ManagementConfigService = Depends(get_management_config_service),
):
    return envelope_ok(data=ManagementConfigResponseModel.model_validate(asdict(service.get_observability_config())), request_id=request_id)


@router.put("/observability/config", response_model=ManagementConfigEnvelope, responses={403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}})
def update_observability_config(
    payload: ManagementConfigUpdateRequest,
    request_id: str = Depends(get_request_id),
    management_ctx: ManagementAuthContext = Depends(require_management_admin),
    audit_repo: AuditEventRepository = Depends(get_audit_event_repository),
    service: ManagementConfigService = Depends(get_management_config_service),
):
    before = asdict(service.get_observability_config())
    try:
        response = service.update_observability_config(payload.payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"backup drill timed out after {exc.timeout} seconds") from exc
    _record_audit(audit_repo, management_ctx=management_ctx, event_type="management.observability_config.updated", request_id=request_id, payload={"before": before, "after": asdict(response), "requested_changes": payload.payload})
    return envelope_ok(data=ManagementConfigResponseModel.model_validate(asdict(response)), request_id=request_id)
