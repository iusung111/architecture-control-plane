import httpx


def _headers(**extra):
    base = {'X-User-Id': 'phase2-user', 'X-User-Role': 'operator'}
    base.update(extra)
    return base


def test_github_actions_executor_dispatch_and_callback_lifecycle(client, monkeypatch):
    monkeypatch.setenv('REMOTE_WORKSPACE_GITHUB_ENABLED', 'true')
    monkeypatch.setenv('REMOTE_WORKSPACE_GITHUB_REPOSITORY', 'example/repo')
    monkeypatch.setenv('REMOTE_WORKSPACE_GITHUB_WORKFLOW', 'remote-workspace.yml')
    monkeypatch.setenv('REMOTE_WORKSPACE_GITHUB_TOKEN', 'ghs_test')
    monkeypatch.setenv('REMOTE_WORKSPACE_GITHUB_REF', 'main')
    monkeypatch.setenv('REMOTE_WORKSPACE_CALLBACK_TOKEN', 'callback-secret')
    monkeypatch.setenv('REMOTE_WORKSPACE_DEFAULT_EXECUTOR', 'github_actions')

    dispatched = {}

    def fake_post(self, url, **kwargs):
        if not str(url).startswith('https://api.github.com/'):
            return original_post(self, url, **kwargs)
        dispatched['url'] = url
        dispatched['headers'] = kwargs.get('headers')
        dispatched['json'] = kwargs.get('json')
        return httpx.Response(204, request=httpx.Request('POST', str(url)))

    original_post = httpx.Client.post

    monkeypatch.setattr(httpx.Client, 'post', fake_post)

    snapshot = client.post(
        '/v1/remote-workspaces/snapshots',
        headers=_headers(),
        json={
            'workspace_id': 'ws-phase2',
            'project_id': 'proj-rw',
            'repo_url': 'https://github.com/example/repo',
            'repo_branch': 'main',
        },
    )
    assert snapshot.status_code == 200

    execution = client.post(
        '/v1/remote-workspaces/executions',
        headers=_headers(),
        json={
            'workspace_id': 'ws-phase2',
            'execution_kind': 'run_checks',
            'command': 'pytest -q',
            'executor_key': 'github_actions',
            'repo_url': 'https://github.com/example/repo',
            'repo_branch': 'main',
        },
    )
    assert execution.status_code == 200
    payload = execution.json()['data']
    assert payload['status'] == 'queued'
    assert payload['executor_key'] == 'github_actions'
    execution_id = payload['execution_id']

    assert dispatched['url'].endswith('/repos/example/repo/actions/workflows/remote-workspace.yml/dispatches')
    assert dispatched['json']['ref'] == 'main'
    assert dispatched['json']['inputs']['execution_id'] == execution_id

    callback = client.post(
        f'/v1/remote-workspaces/executions/{execution_id}/result',
        headers={'X-Remote-Workspace-Callback-Token': 'callback-secret'},
        json={
            'workspace_id': 'ws-phase2',
            'execution_kind': 'run_checks',
            'status': 'succeeded',
            'result_summary': '3 passed',
            'logs_url': 'https://example.test/logs/1',
            'external_url': 'https://github.com/example/repo/actions/runs/123',
            'artifacts': [
                {'artifact_id': 'junit', 'artifact_type': 'junit', 'uri': 'https://example.test/junit.xml'},
            ],
            'project_id': 'proj-rw',
            'repo_url': 'https://github.com/example/repo',
            'repo_branch': 'main',
        },
    )
    assert callback.status_code == 200
    assert callback.json()['data']['status'] == 'succeeded'
    assert callback.json()['data']['artifact_count'] == 1

    fetched = client.get(f'/v1/remote-workspaces/executions/{execution_id}', headers=_headers())
    assert fetched.status_code == 200
    assert fetched.json()['data']['result_summary'] == '3 passed'
    assert fetched.json()['data']['logs_url'] == 'https://example.test/logs/1'
    assert fetched.json()['data']['artifact_count'] == 1

    snapshots = client.get('/v1/remote-workspaces/snapshots?project_id=proj-rw', headers=_headers())
    assert snapshots.status_code == 200
    item = snapshots.json()['data']['items'][0]
    assert item['workspace_id'] == 'ws-phase2'
    assert 'artifact_count' in item



def test_github_actions_cancel_resolves_run_id_from_workflow_runs(client, monkeypatch):
    monkeypatch.setenv('REMOTE_WORKSPACE_GITHUB_ENABLED', 'true')
    monkeypatch.setenv('REMOTE_WORKSPACE_GITHUB_REPOSITORY', 'example/repo')
    monkeypatch.setenv('REMOTE_WORKSPACE_GITHUB_WORKFLOW', 'remote-workspace.yml')
    monkeypatch.setenv('REMOTE_WORKSPACE_GITHUB_TOKEN', 'ghs_test')
    monkeypatch.setenv('REMOTE_WORKSPACE_GITHUB_REF', 'main')
    monkeypatch.setenv('REMOTE_WORKSPACE_DEFAULT_EXECUTOR', 'github_actions')

    calls = {'dispatch': None, 'lookup': None, 'cancel': None}

    original_post = httpx.Client.post
    original_get = httpx.Client.get

    def fake_post(self, url, **kwargs):
        request = httpx.Request('POST', str(url))
        if str(url).startswith('https://api.github.com/'):
            if str(url).endswith('/dispatches'):
                calls['dispatch'] = {'url': str(url), 'json': kwargs.get('json'), 'headers': kwargs.get('headers')}
                return httpx.Response(204, request=request)
            if str(url).endswith('/actions/runs/712/cancel'):
                calls['cancel'] = {'url': str(url), 'json': kwargs.get('json'), 'headers': kwargs.get('headers')}
                return httpx.Response(202, request=request)
            raise AssertionError(f'unexpected GitHub POST {url}')
        return original_post(self, url, **kwargs)

    def fake_get(self, url, **kwargs):
        request = httpx.Request('GET', str(url))
        if str(url).startswith('https://api.github.com/'):
            if str(url).endswith('/actions/workflows/remote-workspace.yml/runs'):
                calls['lookup'] = {'url': str(url), 'params': kwargs.get('params'), 'headers': kwargs.get('headers')}
                execution_id = calls['dispatch']['json']['inputs']['execution_id']
                return httpx.Response(
                    200,
                    request=request,
                    json={
                        'workflow_runs': [
                            {
                                'id': 712,
                                'display_title': f'ACP remote workspace {execution_id} · run_checks',
                                'html_url': 'https://github.com/example/repo/actions/runs/712',
                                'status': 'queued',
                                'conclusion': None,
                                'created_at': '2099-01-01T00:00:00Z',
                            }
                        ]
                    },
                )
            raise AssertionError(f'unexpected GitHub GET {url}')
        return original_get(self, url, **kwargs)

    monkeypatch.setattr(httpx.Client, 'post', fake_post)
    monkeypatch.setattr(httpx.Client, 'get', fake_get)

    snapshot = client.post(
        '/v1/remote-workspaces/snapshots',
        headers=_headers(),
        json={
            'workspace_id': 'ws-phase2-cancel',
            'project_id': 'proj-rw',
            'repo_url': 'https://github.com/example/repo',
            'repo_branch': 'main',
        },
    )
    assert snapshot.status_code == 200

    execution = client.post(
        '/v1/remote-workspaces/executions',
        headers=_headers(),
        json={
            'workspace_id': 'ws-phase2-cancel',
            'execution_kind': 'run_checks',
            'command': 'pytest -q',
            'executor_key': 'github_actions',
            'repo_url': 'https://github.com/example/repo',
            'repo_branch': 'main',
        },
    )
    assert execution.status_code == 200
    execution_id = execution.json()['data']['execution_id']
    metadata = execution.json()['data']['metadata']
    assert metadata['github_workflow_runs_url'].endswith('/actions/workflows/remote-workspace.yml/runs')
    assert metadata['dispatch_requested_at']
    assert 'github_run_id' not in metadata

    cancelled = client.post(f'/v1/remote-workspaces/executions/{execution_id}/cancel', headers=_headers())
    assert cancelled.status_code == 200
    assert cancelled.json()['data']['status'] == 'cancel_requested'

    assert calls['lookup']['params']['event'] == 'workflow_dispatch'
    assert calls['lookup']['params']['branch'] == 'main'
    assert calls['cancel']['url'].endswith('/actions/runs/712/cancel')

def test_remote_workspace_limits_and_cancel(client, monkeypatch):
    monkeypatch.setenv('REMOTE_WORKSPACE_DEFAULT_EXECUTOR', 'planning')
    monkeypatch.setenv('REMOTE_WORKSPACE_MAX_PARALLEL_REQUESTS', '1')
    monkeypatch.setenv('REMOTE_WORKSPACE_DAILY_REQUEST_LIMIT', '1')

    client.post('/v1/remote-workspaces/snapshots', headers=_headers(), json={'workspace_id': 'ws-limit', 'project_id': 'proj-limit'})
    first = client.post('/v1/remote-workspaces/executions', headers=_headers(), json={'workspace_id': 'ws-limit', 'execution_kind': 'run_checks'})
    assert first.status_code == 200
    execution_id = first.json()['data']['execution_id']

    second = client.post('/v1/remote-workspaces/executions', headers=_headers(), json={'workspace_id': 'ws-limit', 'execution_kind': 'run_checks'})
    assert second.status_code == 429

    cancelled = client.post(f'/v1/remote-workspaces/executions/{execution_id}/cancel', headers=_headers())
    assert cancelled.status_code == 200
    assert cancelled.json()['data']['status'] in {'cancelled', 'cancel_requested'}


def test_workbench_phase2_remote_workspace_surface_present(client):
    response = client.get('/workbench')
    assert response.status_code == 200
    assert 'Remote workspace phase 2' in response.text
    assert '/v1/remote-workspaces/executions/' in response.text
    assert 'Run tests remotely' in response.text or 'queue remote checks' in response.text.lower()
