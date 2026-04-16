from __future__ import annotations

from fastapi import APIRouter

from .execution_routes import router as execution_router
from .persistent_routes import router as persistent_router
from .snapshot_routes import router as snapshot_router
from .workbench_routes import router as workbench_router

router = APIRouter()
router.include_router(snapshot_router)
router.include_router(execution_router)
router.include_router(persistent_router)

__all__ = ["router", "workbench_router"]
