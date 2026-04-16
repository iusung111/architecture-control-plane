from pathlib import Path

import yaml

from app.core.config import get_settings
from app.repositories.audit import AuditEventRepository
from app.services.remote_workspace import OptionalPersistentRemoteWorkspaceExecutor


def _headers(**extra):
    base = {"X-User-Id": "prod-ready-user", "X-User-Role": "operator"}
    base.update(extra)
    return base


def test_persistent_executor_supports_session_execution_artifacts_resume_and_cancel(client, monkeypatch):
    monkeypatch.setenv("REMOTE_WORKSPACE_PERSISTENT_ENABLED", "true")
    monkeypatch.setenv("REMOTE_WORKSPACE_DEFAULT_EXECUTOR", "persistent")
    monkeypatch.setenv("REMOTE_WORKSPACE_CALLBACK_TOKEN", "prod-ready-token")
    get_settings.cache_clear()

    created = client.post(
        "/v1/remote-workspaces/persistent/sessions",
        headers=_headers(),
        json={
            "workspace_id": "ws-prod-ready",
            "project_id": "proj-prod-ready",
            "repo_url": "https://github.com/example/repo",
            "repo_branch": "main",
        },
    )
    assert created.status_code == 200
    assert created.json()["data"]["status"] == "active"

    queued = client.post(
        "/v1/remote-workspaces/executions",
        headers=_headers(),
        json={
            "workspace_id": "ws-prod-ready",
            "project_id": "proj-prod-ready",
            "repo_url": "https://github.com/example/repo",
            "repo_branch": "main",
            "executor_key": "persistent",
            "execution_kind": "run_checks",
            "command": "pytest -q",
        },
    )
    assert queued.status_code == 200
    queued_payload = queued.json()["data"]
    assert queued_payload["status"] == "running"
    assert queued_payload["metadata"]["persistent_workspace"]["session_status"] == "active"
    execution_id = queued_payload["execution_id"]

    session_busy = client.get("/v1/remote-workspaces/persistent/sessions/ws-prod-ready", headers=_headers())
    assert session_busy.status_code == 200
    assert session_busy.json()["data"]["status"] == "busy"

    blocked_hibernate = client.post(
        "/v1/remote-workspaces/persistent/sessions/ws-prod-ready/hibernate",
        headers=_headers(),
    )
    assert blocked_hibernate.status_code == 409

    callback = client.post(
        f"/v1/remote-workspaces/executions/{execution_id}/result",
        headers={"X-Remote-Workspace-Callback-Token": "prod-ready-token"},
        json={
            "workspace_id": "ws-prod-ready",
            "execution_kind": "run_checks",
            "status": "succeeded",
            "result_summary": "all checks green",
            "artifacts": [
                {"artifact_id": "junit", "artifact_type": "junit", "uri": "https://example.test/junit.xml"},
            ],
        },
    )
    assert callback.status_code == 200
    callback_payload = callback.json()["data"]
    assert callback_payload["artifact_count"] == 1

    session_after_callback = client.get("/v1/remote-workspaces/persistent/sessions/ws-prod-ready", headers=_headers())
    assert session_after_callback.status_code == 200
    assert session_after_callback.json()["data"]["status"] == "active"

    resume = client.get("/v1/remote-workspaces/ws-prod-ready/resume", headers=_headers())
    assert resume.status_code == 200
    assert resume.json()["data"]["artifacts"][0]["artifact_id"] == "junit"

    hibernated = client.post(
        "/v1/remote-workspaces/persistent/sessions/ws-prod-ready/hibernate",
        headers=_headers(),
    )
    assert hibernated.status_code == 200
    assert hibernated.json()["data"]["status"] == "hibernated"

    resumed = client.post(
        "/v1/remote-workspaces/ws-prod-ready/resume",
        headers=_headers(),
        json={"note": "wake session"},
    )
    assert resumed.status_code == 200
    session = client.get("/v1/remote-workspaces/persistent/sessions/ws-prod-ready", headers=_headers())
    assert session.status_code == 200
    assert session.json()["data"]["status"] == "active"

    cancellable = client.post(
        "/v1/remote-workspaces/executions",
        headers=_headers(),
        json={
            "workspace_id": "ws-prod-ready",
            "project_id": "proj-prod-ready",
            "executor_key": "persistent",
            "execution_kind": "run_checks",
            "command": "pytest -q",
        },
    )
    assert cancellable.status_code == 200
    cancel_id = cancellable.json()["data"]["execution_id"]
    cancelled = client.post(f"/v1/remote-workspaces/executions/{cancel_id}/cancel", headers=_headers())
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"

    session_after_cancel = client.get("/v1/remote-workspaces/persistent/sessions/ws-prod-ready", headers=_headers())
    assert session_after_cancel.status_code == 200
    assert session_after_cancel.json()["data"]["status"] == "active"

    get_settings.cache_clear()


def test_persistent_execution_auto_creates_session_when_missing(client, monkeypatch):
    monkeypatch.setenv("REMOTE_WORKSPACE_PERSISTENT_ENABLED", "true")
    monkeypatch.setenv("REMOTE_WORKSPACE_DEFAULT_EXECUTOR", "persistent")
    get_settings.cache_clear()

    queued = client.post(
        "/v1/remote-workspaces/executions",
        headers=_headers(),
        json={
            "workspace_id": "ws-auto-session",
            "project_id": "proj-auto-session",
            "executor_key": "persistent",
            "execution_kind": "prepare",
        },
    )
    assert queued.status_code == 200
    session = client.get("/v1/remote-workspaces/persistent/sessions/ws-auto-session", headers=_headers())
    assert session.status_code == 200
    assert session.json()["data"]["status"] == "active"

    get_settings.cache_clear()


def test_remote_workspace_operational_assets_present_and_structured() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/remote-workspace.yml").read_text())
    assert workflow["name"] == "Remote Workspace Executor"
    dispatch_root = workflow.get("on") or workflow.get(True)
    dispatch_inputs = dispatch_root["workflow_dispatch"]["inputs"]
    assert {"execution_id", "workspace_id", "execution_kind", "callback_url", "repo_url"}.issubset(dispatch_inputs)

    release_checklist = Path("docs/RELEASE_CHECKLIST.md").read_text()
    runtime_doc = Path("docs/REMOTE_WORKSPACE_RUNTIME.md").read_text()
    assert "Persistent session flow succeeds" in release_checklist
    assert "remote.workspace.persistent.session.saved" in runtime_doc

    load_script = Path("scripts/load_remote_workspace_long_session.py").read_text()
    assert "/v1/remote-workspaces/persistent/sessions" in load_script
    assert "/v1/remote-workspaces/executions" in load_script
    assert "git clone --depth 1" in Path(".github/workflows/remote-workspace.yml").read_text()
    assert "github_artifact_url" in Path(".github/workflows/remote-workspace.yml").read_text()

    helm_api = Path("deploy/helm/architecture-control-plane/templates/deployment-api.yaml").read_text()
    assert "serviceAccountName" in helm_api
    assert "envFrom" in helm_api
    assert "volumeMounts" in helm_api


def test_persistent_executor_uses_latest_session_and_snapshot_state(client, db_session, monkeypatch):
    monkeypatch.setenv("REMOTE_WORKSPACE_PERSISTENT_ENABLED", "true")
    monkeypatch.setenv("REMOTE_WORKSPACE_DEFAULT_EXECUTOR", "persistent")
    monkeypatch.setenv("REMOTE_WORKSPACE_CALLBACK_TOKEN", "latest-state-token")
    get_settings.cache_clear()

    created = client.post(
        "/v1/remote-workspaces/persistent/sessions",
        headers=_headers(),
        json={
            "workspace_id": "ws-latest-state",
            "project_id": "proj-latest-state",
            "repo_url": "https://github.com/example/repo",
            "repo_branch": "main",
        },
    )
    assert created.status_code == 200

    queued = client.post(
        "/v1/remote-workspaces/executions",
        headers=_headers(),
        json={
            "workspace_id": "ws-latest-state",
            "project_id": "proj-latest-state",
            "executor_key": "persistent",
            "execution_kind": "run_checks",
            "command": "pytest -q",
        },
    )
    assert queued.status_code == 200
    execution_id = queued.json()["data"]["execution_id"]

    callback = client.post(
        f"/v1/remote-workspaces/executions/{execution_id}/result",
        headers={"X-Remote-Workspace-Callback-Token": "latest-state-token"},
        json={
            "workspace_id": "ws-latest-state",
            "execution_kind": "run_checks",
            "status": "succeeded",
            "artifacts": [
                {"artifact_id": "coverage", "artifact_type": "report", "uri": "https://example.test/coverage.json"},
            ],
        },
    )
    assert callback.status_code == 200

    hibernated = client.post(
        "/v1/remote-workspaces/persistent/sessions/ws-latest-state/hibernate",
        headers=_headers(),
    )
    assert hibernated.status_code == 200

    executor = OptionalPersistentRemoteWorkspaceExecutor(get_settings(), AuditEventRepository(db_session))
    latest_session = executor._latest_persistent_session("ws-latest-state")
    assert latest_session is not None
    assert latest_session["status"] == "hibernated"

    artifacts = executor.collect_artifacts("ws-latest-state")
    assert [item["artifact_id"] for item in artifacts] == ["coverage"]

    get_settings.cache_clear()


def test_busy_persistent_session_counts_toward_active_limit(client, monkeypatch):
    monkeypatch.setenv("REMOTE_WORKSPACE_PERSISTENT_ENABLED", "true")
    monkeypatch.setenv("REMOTE_WORKSPACE_PERSISTENT_MAX_ACTIVE_SESSIONS", "1")
    monkeypatch.setenv("REMOTE_WORKSPACE_DEFAULT_EXECUTOR", "persistent")
    get_settings.cache_clear()

    first = client.post(
        "/v1/remote-workspaces/persistent/sessions",
        headers=_headers(),
        json={
            "workspace_id": "ws-limit-1",
            "project_id": "proj-limit",
            "repo_url": "https://github.com/example/repo",
            "repo_branch": "main",
        },
    )
    assert first.status_code == 200

    queued = client.post(
        "/v1/remote-workspaces/executions",
        headers=_headers(),
        json={
            "workspace_id": "ws-limit-1",
            "project_id": "proj-limit",
            "executor_key": "persistent",
            "execution_kind": "run_checks",
            "command": "pytest -q",
        },
    )
    assert queued.status_code == 200

    busy = client.get("/v1/remote-workspaces/persistent/sessions/ws-limit-1", headers=_headers())
    assert busy.status_code == 200
    assert busy.json()["data"]["status"] == "busy"

    blocked = client.post(
        "/v1/remote-workspaces/persistent/sessions",
        headers=_headers(),
        json={
            "workspace_id": "ws-limit-2",
            "project_id": "proj-limit",
            "repo_url": "https://github.com/example/repo",
            "repo_branch": "main",
        },
    )
    assert blocked.status_code == 429

    get_settings.cache_clear()
