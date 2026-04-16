from pathlib import Path

from app.services.remote_workspace import (
    OptionalPersistentRemoteWorkspaceExecutor,
    RemoteWorkspaceExecutorRegistry,
    RemoteWorkspaceQueryService,
    RemoteWorkspaceWriteService,
    WorkspaceExecutionRequest,
    WorkspaceExecutionResult,
)


def test_remote_workspace_public_contracts_remain_importable() -> None:
    assert RemoteWorkspaceWriteService is not None
    assert RemoteWorkspaceQueryService is not None
    assert RemoteWorkspaceExecutorRegistry is not None
    assert OptionalPersistentRemoteWorkspaceExecutor is not None
    assert WorkspaceExecutionRequest is not None
    assert WorkspaceExecutionResult is not None


def test_remote_workspace_refactored_files_stay_within_limits() -> None:
    targets = {
        'app/services/remote_workspace.py': 80,
        'app/services/remote_workspace_support/types.py': 300,
        'app/services/remote_workspace_support/helpers.py': 300,
        'app/services/remote_workspace_support/payloads.py': 300,
        'app/services/remote_workspace_support/github_executor.py': 300,
        'app/services/remote_workspace_support/persistent.py': 300,
        'app/services/remote_workspace_support/registry.py': 120,
        'app/services/remote_workspace_support/query_service.py': 300,
        'app/services/remote_workspace_support/write_state.py': 300,
        'app/services/remote_workspace_support/write_execution.py': 300,
        'app/services/remote_workspace_support/write_views.py': 300,
        'app/services/remote_workspace_support/write_service.py': 120,
    }
    for relative_path, limit in targets.items():
        lines = Path(relative_path).read_text(encoding='utf-8').splitlines()
        assert len(lines) <= limit, f'{relative_path} has {len(lines)} lines > {limit}'
