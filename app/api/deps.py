from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import AuthContext, AuthError, authenticate_bearer_token, authenticate_oidc_token
from app.core.config import get_settings
from app.core.management_auth import ManagementAuthContext, resolve_management_access
from app.core.rate_limit import action_limit_profile, enforce_action_limit
from app.core.telemetry import record_auth_failure
from app.db.session import get_db
from app.repositories.approvals import ApprovalRepository
from app.repositories.audit import AuditEventRepository
from app.repositories.cycles import CycleRepository
from app.repositories.jobs import JobRepository
from app.repositories.management_config import ManagementConfigRepository
from app.repositories.outbox import OutboxRepository
from app.services.approvals import ApprovalService
from app.services.cycles import CycleQueryService, CycleStreamService, CycleWriteService
from app.services.remote_workspace import RemoteWorkspaceQueryService, RemoteWorkspaceWriteService
from app.services.llm_management import LLMRoutingService
from app.services.management_config import ManagementConfigService
from app.services.unit_of_work import SqlAlchemyUnitOfWork



def get_auth_context(
    request: Request,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_user_role: str = Header(default="operator"),
    x_tenant_id: str | None = Header(default=None),
) -> AuthContext:
    settings = get_settings()
    if settings.auth_mode in {"bearer_jwt", "oidc_jwks"}:
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
            try:
                if settings.auth_mode == "oidc_jwks":
                    return authenticate_oidc_token(token, settings)
                return authenticate_bearer_token(token, settings)
            except AuthError as exc:
                record_auth_failure(str(exc))
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not settings.auth_header_fallback_enabled:
            record_auth_failure("missing bearer token")
            raise HTTPException(status_code=401, detail="missing bearer token")

    if not x_user_id:
        record_auth_failure("missing x-user-id header")
        raise HTTPException(status_code=403, detail="missing x-user-id header")
    return AuthContext(user_id=x_user_id, role=x_user_role, tenant_id=x_tenant_id)



def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get("x-request-id", str(uuid4()))



def get_cycle_write_service(db: Session = Depends(get_db)) -> CycleWriteService:
    uow = SqlAlchemyUnitOfWork(db)
    return CycleWriteService(
        cycle_repo=CycleRepository(db),
        job_repo=JobRepository(db),
        outbox_repo=OutboxRepository(db),
        audit_repo=AuditEventRepository(db),
        uow=uow,
    )



def get_cycle_query_service(db: Session = Depends(get_db)) -> CycleQueryService:
    return CycleQueryService(cycle_repo=CycleRepository(db))


def get_cycle_stream_service(db: Session = Depends(get_db)) -> CycleStreamService:
    bind = db.get_bind()
    stream_session_factory = sessionmaker(bind=bind, autoflush=False, autocommit=False, expire_on_commit=False)
    return CycleStreamService(session_factory=stream_session_factory)



def get_approval_service(db: Session = Depends(get_db)) -> ApprovalService:
    uow = SqlAlchemyUnitOfWork(db)
    return ApprovalService(
        approval_repo=ApprovalRepository(db),
        cycle_repo=CycleRepository(db),
        job_repo=JobRepository(db),
        outbox_repo=OutboxRepository(db),
        audit_repo=AuditEventRepository(db),
        uow=uow,
    )


def require_management_access(
    request: Request,
    x_management_key: str | None = Header(default=None, alias="X-Management-Key"),
) -> ManagementAuthContext:
    del request
    settings = get_settings()
    return resolve_management_access(x_management_key, settings, required_role="viewer")




def require_management_operator(
    request: Request,
    x_management_key: str | None = Header(default=None, alias="X-Management-Key"),
) -> ManagementAuthContext:
    del request
    settings = get_settings()
    return resolve_management_access(x_management_key, settings, required_role="operator")


def get_audit_event_repository(db: Session = Depends(get_db)) -> AuditEventRepository:
    return AuditEventRepository(db)
def require_management_admin(
    request: Request,
    x_management_key: str | None = Header(default=None, alias="X-Management-Key"),
) -> ManagementAuthContext:
    del request
    settings = get_settings()
    return resolve_management_access(x_management_key, settings, required_role="admin")


def get_llm_routing_service(db: Session = Depends(get_db)) -> LLMRoutingService:
    return LLMRoutingService(db)




def enforce_create_cycle_rate_limit(request: Request, auth: AuthContext = Depends(get_auth_context)) -> None:
    enforce_action_limit(
        request,
        action_limit_profile("cycle_create", user_id=auth.user_id, tenant_id=auth.tenant_id, role=auth.role),
    )


def enforce_retry_cycle_rate_limit(request: Request, auth: AuthContext = Depends(get_auth_context)) -> None:
    enforce_action_limit(
        request,
        action_limit_profile("cycle_retry", user_id=auth.user_id, tenant_id=auth.tenant_id, role=auth.role),
    )


def enforce_replan_cycle_rate_limit(request: Request, auth: AuthContext = Depends(get_auth_context)) -> None:
    enforce_action_limit(
        request,
        action_limit_profile("cycle_replan", user_id=auth.user_id, tenant_id=auth.tenant_id, role=auth.role),
    )


def enforce_approval_confirm_rate_limit(request: Request, auth: AuthContext = Depends(get_auth_context)) -> None:
    enforce_action_limit(
        request,
        action_limit_profile("approval_confirm", user_id=auth.user_id, tenant_id=auth.tenant_id, role=auth.role),
    )




def get_remote_workspace_write_service(db: Session = Depends(get_db)) -> RemoteWorkspaceWriteService:
    uow = SqlAlchemyUnitOfWork(db)
    return RemoteWorkspaceWriteService(audit_repo=AuditEventRepository(db), uow=uow, settings=get_settings())


def get_remote_workspace_query_service(db: Session = Depends(get_db)) -> RemoteWorkspaceQueryService:
    return RemoteWorkspaceQueryService(audit_repo=AuditEventRepository(db), settings=get_settings())

def get_management_config_repository(db: Session = Depends(get_db)) -> ManagementConfigRepository:
    return ManagementConfigRepository(db)


def get_management_config_service(db: Session = Depends(get_db)) -> ManagementConfigService:
    return ManagementConfigService(db)
