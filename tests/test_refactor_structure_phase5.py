from pathlib import Path

from app.api.routes.remote_workspace import router as remote_workspace_router, workbench_router
from app.core.auth import AuthContext, authenticate_bearer_token, authenticate_oidc_token, clear_auth_caches
from app.core.config import Settings, get_settings, validate_runtime_settings
from app.schemas.cycles import CreateCycleRequest, CycleResultResponse
from app.services.orchestration import CycleExecutionOrchestrator, ExecutionSnapshot


def test_phase5_public_contracts_remain_importable() -> None:
    assert remote_workspace_router is not None
    assert workbench_router is not None
    assert AuthContext is not None
    assert authenticate_bearer_token is not None
    assert authenticate_oidc_token is not None
    assert clear_auth_caches is not None
    assert Settings is not None
    assert get_settings is not None
    assert validate_runtime_settings is not None
    assert CreateCycleRequest is not None
    assert CycleResultResponse is not None
    assert CycleExecutionOrchestrator is not None
    assert ExecutionSnapshot is not None


def test_phase5_refactored_facades_stay_small() -> None:
    targets = {
        "app/core/config.py": 80,
        "app/core/auth.py": 80,
        "app/services/orchestration.py": 80,
        "app/api/routes/remote_workspace.py": 80,
        "app/schemas/cycles.py": 120,
    }
    for relative_path, limit in targets.items():
        lines = Path(relative_path).read_text(encoding="utf-8").splitlines()
        assert len(lines) <= limit, f"{relative_path} has {len(lines)} lines > {limit}"
