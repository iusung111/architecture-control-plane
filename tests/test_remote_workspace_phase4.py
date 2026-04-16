from pathlib import Path

from app.core.config import get_settings


def _headers(**extra):
    base = {"X-User-Id": "phase4-user", "X-User-Role": "operator"}
    base.update(extra)
    return base


def test_phase4_persistent_executor_is_visible_but_disabled_by_default(client):
    response = client.get('/v1/remote-workspaces/executors', headers=_headers())
    assert response.status_code == 200
    items = {item['key']: item for item in response.json()['data']['items']}
    assert 'persistent' in items
    assert items['persistent']['enabled'] is False
    assert items['persistent']['mode'] == 'persistent_opt_in'


def test_persistent_workspace_session_lifecycle_and_scope(client, monkeypatch):
    monkeypatch.setenv('REMOTE_WORKSPACE_PERSISTENT_ENABLED', 'true')
    monkeypatch.setenv('REMOTE_WORKSPACE_PERSISTENT_MAX_ACTIVE_SESSIONS', '1')
    get_settings.cache_clear()

    created = client.post(
        '/v1/remote-workspaces/persistent/sessions',
        headers=_headers(),
        json={
            'workspace_id': 'ws-persistent-1',
            'project_id': 'proj-persistent',
            'repo_url': 'https://github.com/example/repo',
            'repo_branch': 'main',
            'note': 'phase4 opt-in persistent session',
        },
    )
    assert created.status_code == 200
    assert created.json()['data']['status'] == 'active'

    listed = client.get('/v1/remote-workspaces/persistent/sessions', headers=_headers())
    assert listed.status_code == 200
    assert listed.json()['data']['items'][0]['workspace_id'] == 'ws-persistent-1'

    second = client.post(
        '/v1/remote-workspaces/persistent/sessions',
        headers=_headers(),
        json={'workspace_id': 'ws-persistent-2', 'project_id': 'proj-persistent'},
    )
    assert second.status_code == 429

    foreign = client.get('/v1/remote-workspaces/persistent/sessions/ws-persistent-1', headers={'X-User-Id': 'other-user', 'X-User-Role': 'operator'})
    assert foreign.status_code == 404

    hibernated = client.post('/v1/remote-workspaces/persistent/sessions/ws-persistent-1/hibernate', headers=_headers())
    assert hibernated.status_code == 200
    assert hibernated.json()['data']['status'] == 'hibernated'

    get_settings.cache_clear()


def test_persistent_workspace_track_rejects_when_disabled(client, monkeypatch):
    monkeypatch.setenv('REMOTE_WORKSPACE_PERSISTENT_ENABLED', 'false')
    get_settings.cache_clear()
    response = client.post('/v1/remote-workspaces/persistent/sessions', headers=_headers(), json={'workspace_id': 'ws-disabled'})
    assert response.status_code == 409
    get_settings.cache_clear()


def test_remote_workspace_phase4_security_regression_invalid_callback_token(client, monkeypatch):
    monkeypatch.setenv('REMOTE_WORKSPACE_CALLBACK_TOKEN', 'expected-token')
    get_settings.cache_clear()
    response = client.post(
        '/v1/remote-workspaces/executions/exec-123/result',
        headers={'X-Remote-Workspace-Callback-Token': 'wrong-token'},
        json={'workspace_id': 'ws-any', 'execution_kind': 'run_checks', 'status': 'failed'},
    )
    assert response.status_code == 403
    get_settings.cache_clear()


def test_phase4_workbench_and_runtime_smoke_files_exist(client):
    response = client.get('/workbench')
    assert response.status_code == 200
    assert 'Optional persistent workspace' in response.text
    assert 'Promote to persistent session' in response.text
    assert 'id="persistent-workspace-sessions"' in response.text

    assert Path('deploy/helm/architecture-control-plane/Chart.yaml').exists()
    assert Path('deploy/kubernetes/overlays/staging/kustomization.yaml').exists()
    assert Path('deploy/kubernetes/overlays/production/kustomization.yaml').exists()
    assert Path('scripts/k8s_runtime_smoke.sh').exists()
    assert Path('scripts/load_remote_workspace_long_session.py').exists()


def test_persistent_workspace_session_can_be_deleted_and_frees_quota(client, monkeypatch):
    monkeypatch.setenv('REMOTE_WORKSPACE_PERSISTENT_ENABLED', 'true')
    monkeypatch.setenv('REMOTE_WORKSPACE_PERSISTENT_MAX_ACTIVE_SESSIONS', '1')

    created = client.post(
        '/v1/remote-workspaces/persistent/sessions',
        headers=_headers(),
        json={'workspace_id': 'ws-delete-1', 'project_id': 'proj-delete'},
    )
    assert created.status_code == 200

    deleted = client.delete('/v1/remote-workspaces/persistent/sessions/ws-delete-1', headers=_headers())
    assert deleted.status_code == 200
    assert deleted.json()['data']['status'] == 'deleted'

    missing = client.get('/v1/remote-workspaces/persistent/sessions/ws-delete-1', headers=_headers())
    assert missing.status_code == 404

    listed = client.get('/v1/remote-workspaces/persistent/sessions', headers=_headers())
    assert listed.status_code == 200
    assert listed.json()['data']['items'] == []

    replacement = client.post(
        '/v1/remote-workspaces/persistent/sessions',
        headers=_headers(),
        json={'workspace_id': 'ws-delete-2', 'project_id': 'proj-delete'},
    )
    assert replacement.status_code == 200
    assert replacement.json()['data']['workspace_id'] == 'ws-delete-2'


def test_persistent_workspace_session_delete_rejects_active_execution(client, monkeypatch):
    monkeypatch.setenv('REMOTE_WORKSPACE_PERSISTENT_ENABLED', 'true')

    created = client.post(
        '/v1/remote-workspaces/persistent/sessions',
        headers=_headers(),
        json={'workspace_id': 'ws-delete-busy', 'project_id': 'proj-delete'},
    )
    assert created.status_code == 200

    execution = client.post(
        '/v1/remote-workspaces/executions',
        headers=_headers(),
        json={
            'workspace_id': 'ws-delete-busy',
            'cycle_id': 'cycle-delete-busy',
            'project_id': 'proj-delete',
            'executor_key': 'persistent',
            'execution_kind': 'checks',
            'command': 'pytest -q',
        },
    )
    assert execution.status_code in {200, 202}

    blocked = client.delete('/v1/remote-workspaces/persistent/sessions/ws-delete-busy', headers=_headers())
    assert blocked.status_code == 409
    assert 'cannot delete while a remote workspace execution is still active' in blocked.json()['error']['message']
