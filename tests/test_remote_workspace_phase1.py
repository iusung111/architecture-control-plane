from pathlib import Path

from app.core.config import get_settings


def _headers(**extra):
    base = {'X-User-Id': 'phase1-user', 'X-User-Role': 'operator'}
    base.update(extra)
    return base


def test_remote_workspace_snapshot_execution_resume_and_view_lifecycle(client, monkeypatch):
    monkeypatch.setenv('REMOTE_WORKSPACE_CALLBACK_TOKEN', 'phase3-callback')
    get_settings.cache_clear()

    executors = client.get('/v1/remote-workspaces/executors', headers=_headers())
    assert executors.status_code == 200
    items = executors.json()['data']['items']
    assert any(item['key'] == 'planning' for item in items)

    created = client.post(
        '/v1/remote-workspaces/snapshots',
        headers=_headers(),
        json={
            'cycle_id': 'cycle-123',
            'project_id': 'proj-a',
            'repo_url': 'https://github.com/example/repo',
            'repo_branch': 'main',
            'patch': 'diff --git a/a.py b/a.py',
            'patch_stack': ['diff --git a/a.py b/a.py'],
        },
    )
    assert created.status_code == 200
    snapshot = created.json()['data']
    assert snapshot['workspace_id'] == 'cycle:cycle-123'
    assert snapshot['repo_branch'] == 'main'
    assert snapshot['patch_present'] is True
    assert snapshot['patch_stack']

    execution = client.post(
        '/v1/remote-workspaces/executions',
        headers=_headers(),
        json={
            'workspace_id': snapshot['workspace_id'],
            'cycle_id': 'cycle-123',
            'project_id': 'proj-a',
            'execution_kind': 'run_checks',
            'execution_profile': 'phase2',
            'command': 'pytest -q',
        },
    )
    assert execution.status_code == 200
    execution_data = execution.json()['data']
    execution_id = execution_data['execution_id']
    assert execution_data['status'] in {'planned', 'queued', 'unconfigured', 'prepared'}

    callback = client.post(
        f'/v1/remote-workspaces/executions/{execution_id}/result',
        headers={'X-Remote-Workspace-Callback-Token': 'phase3-callback'},
        json={
            'workspace_id': snapshot['workspace_id'],
            'cycle_id': 'cycle-123',
            'project_id': 'proj-a',
            'execution_kind': 'run_checks',
            'status': 'failed',
            'command': 'pytest -q',
            'result_summary': '1 failed',
            'artifacts': [{'artifact_id': 'junit', 'artifact_type': 'junit', 'uri': 'https://example.test/junit.xml'}],
        },
    )
    assert callback.status_code == 200
    assert callback.json()['data']['status'] == 'failed'

    fetched = client.get(f"/v1/remote-workspaces/snapshots/{snapshot['workspace_id']}", headers=_headers())
    assert fetched.status_code == 200

    resume = client.post(
        f"/v1/remote-workspaces/{snapshot['workspace_id']}/resume",
        headers=_headers(),
        json={'note': 'resume after failing checks'},
    )
    assert resume.status_code == 200
    resume_data = resume.json()['data']
    assert resume_data['workspace_id'] == snapshot['workspace_id']
    assert resume_data['resume_count'] >= 1
    assert resume_data['recent_executions'][0]['execution_id'] == execution_id
    assert resume_data['recent_executions'][0]['command'] == 'pytest -q'

    saved_view = client.post(
        '/v1/workbench/views',
        headers=_headers(),
        json={
            'name': 'triage phase3',
            'project_id': 'proj-a',
            'cycle_id': 'cycle-123',
            'workspace_id': snapshot['workspace_id'],
            'query': 'failure',
            'layout': {'mode': 'triage'},
            'selected_panels': ['board', 'remote-workspace'],
        },
    )
    assert saved_view.status_code == 200
    view_id = saved_view.json()['data']['view_id']

    used = client.post(f'/v1/workbench/views/{view_id}/use', headers=_headers())
    assert used.status_code == 200

    listed_views = client.get('/v1/workbench/views', headers=_headers())
    assert listed_views.status_code == 200
    assert listed_views.json()['data']['items'][0]['view_id'] == view_id

    deleted_view = client.delete(f'/v1/workbench/views/{view_id}', headers=_headers())
    assert deleted_view.status_code == 200
    assert deleted_view.json()['data']['is_deleted'] is True

    executions = client.get(f"/v1/remote-workspaces/{snapshot['workspace_id']}/executions", headers=_headers())
    assert executions.status_code == 200
    assert executions.json()['data']['items'][0]['execution_kind'] == 'run_checks'

    get_settings.cache_clear()


def test_workspace_discussion_saved_filter_lifecycle(client):
    created = client.post(
        '/v1/workspace/discussion-filters',
        headers=_headers(),
        json={'name': 'triage', 'project_id': 'proj-a', 'mention': 'alice', 'query': 'failure'},
    )
    assert created.status_code == 200
    filter_id = created.json()['data']['filter_id']

    updated = client.patch(
        f'/v1/workspace/discussion-filters/{filter_id}',
        headers=_headers(),
        json={'name': 'triage-hot', 'project_id': 'proj-a', 'mention': 'alice', 'query': 'timeout'},
    )
    assert updated.status_code == 200
    assert updated.json()['data']['name'] == 'triage-hot'

    favorite = client.post(
        f'/v1/workspace/discussion-filters/{filter_id}/favorite',
        headers=_headers(),
        json={'is_favorite': True},
    )
    assert favorite.status_code == 200
    assert favorite.json()['data']['is_favorite'] is True

    used = client.post(f'/v1/workspace/discussion-filters/{filter_id}/use', headers=_headers())
    assert used.status_code == 200
    assert used.json()['data']['last_used_at'] is not None

    listing = client.get('/v1/workspace/discussion-filters', headers=_headers())
    assert listing.status_code == 200
    listed = listing.json()['data']['items'][0]
    assert listed['filter_id'] == filter_id
    assert listed['is_favorite'] is True
    assert listed['name'] == 'triage-hot'

    deleted = client.delete(f'/v1/workspace/discussion-filters/{filter_id}', headers=_headers())
    assert deleted.status_code == 200
    assert deleted.json()['data']['is_deleted'] is True

    relisted = client.get('/v1/workspace/discussion-filters', headers=_headers())
    assert relisted.status_code == 200
    assert relisted.json()['data']['items'] == []


def test_workbench_renders_remote_workspace_resume_and_saved_views_sections(client):
    response = client.get('/workbench')
    assert response.status_code == 200
    assert 'Remote workspace' in response.text
    assert 'Audit explorer' in response.text
    assert 'Resume snapshot memory' in response.text
    assert 'Save current workbench view' in response.text
    assert '/v1/remote-workspaces/executors' in response.text
    assert '/v1/remote-workspaces/' in response.text
    assert '/v1/workbench/views' in response.text


def test_browser_e2e_baseline_files_exist():
    config_path = Path('browser_e2e/playwright.config.ts')
    spec_path = Path('browser_e2e/workbench.smoke.spec.ts')
    assert config_path.exists()
    assert spec_path.exists()
    assert '/workbench' in spec_path.read_text(encoding='utf-8')
