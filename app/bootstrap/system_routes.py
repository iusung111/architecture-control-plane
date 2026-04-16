from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.management_auth import resolve_management_access
from app.core.rate_limit import enforce_management_request_limit
from app.core.telemetry import render_metrics

router = APIRouter()


def _require_management_access(
    request: Request,
    presented_key: str | None,
    *,
    required_role: str = "viewer",
    apply_rate_limit: bool = True,
) -> None:
    settings = get_settings()
    if apply_rate_limit:
        enforce_management_request_limit(request, presented_key)
    resolve_management_access(presented_key, settings, required_role=required_role)


@router.get("/workbench", include_in_schema=False, response_class=HTMLResponse)
def workbench() -> HTMLResponse:
    html_path = Path(__file__).resolve().parents[1] / "static" / "workbench.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))




@router.get("/workbench-assets/{asset_path:path}", include_in_schema=False)
def workbench_asset(asset_path: str) -> FileResponse:
    asset_root = Path(__file__).resolve().parents[1] / "static" / "workbench-assets"
    asset_path_resolved = (asset_root / asset_path).resolve()
    if asset_root.resolve() not in asset_path_resolved.parents:
        raise HTTPException(status_code=404, detail="asset not found")
    if not asset_path_resolved.exists() or not asset_path_resolved.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(asset_path_resolved)

@router.get("/healthz", tags=["system"])
def healthcheck(request: Request) -> dict[str, str]:
    request.state.response_status_code = 200
    return {"status": "ok"}


@router.get("/readyz", tags=["system"], include_in_schema=False)
def readiness(
    request: Request,
    db: Session = Depends(get_db),
    x_management_key: str | None = Header(default=None, alias="X-Management-Key"),
) -> dict[str, str]:
    _require_management_access(request, x_management_key, required_role="viewer", apply_rate_limit=False)
    db.execute(text("SELECT 1"))
    request.state.response_status_code = 200
    return {"status": "ready"}


@router.get("/metrics", tags=["system"], include_in_schema=False)
def metrics(
    request: Request,
    x_management_key: str | None = Header(default=None, alias="X-Management-Key"),
) -> Response:
    _require_management_access(request, x_management_key, required_role="viewer", apply_rate_limit=False)
    settings = get_settings()
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="metrics disabled")
    payload, content_type = render_metrics()
    request.state.response_status_code = 200
    return Response(content=payload, media_type=content_type)


def _runbook_directory() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "runbooks"


def _runbook_file(slug: str) -> Path | None:
    candidate = _runbook_directory() / f"{slug}.md"
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


@router.get("/runbooks", tags=["system"], include_in_schema=False)
def runbook_index(
    request: Request,
    x_management_key: str | None = Header(default=None, alias="X-Management-Key"),
) -> dict[str, object]:
    _require_management_access(request, x_management_key, required_role="viewer")
    runbook_dir = _runbook_directory()
    runbooks = []
    for path in sorted(runbook_dir.glob("*.md")):
        if path.name == "INDEX.md":
            continue
        runbooks.append({"slug": path.stem, "title": path.read_text().splitlines()[0].lstrip("# ")})
    request.state.response_status_code = 200
    return {"count": len(runbooks), "runbooks": runbooks}


@router.get("/runbooks/{slug}", tags=["system"], include_in_schema=False)
def runbook_detail(
    slug: str,
    request: Request,
    x_management_key: str | None = Header(default=None, alias="X-Management-Key"),
) -> PlainTextResponse:
    _require_management_access(request, x_management_key, required_role="viewer")
    runbook = _runbook_file(slug)
    if runbook is None:
        raise HTTPException(status_code=404, detail="runbook not found")
    request.state.response_status_code = 200
    return PlainTextResponse(runbook.read_text(), media_type="text/markdown")
