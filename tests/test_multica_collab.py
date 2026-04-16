from fastapi.testclient import TestClient

from app.db.models import Cycle
from app.domain.enums import CycleState, UserStatus


def _create_cycle(client: TestClient, *, user: str, project_id: str, key: str) -> str:
    response = client.post(
        '/v1/cycles',
        headers={'X-User-Id': user, 'Idempotency-Key': key},
        json={'project_id': project_id, 'user_input': f'work for {project_id}'},
    )
    assert response.status_code == 201
    return response.json()['data']['cycle_id']



def test_workspace_discussions_round_trip_and_project_filter(client: TestClient) -> None:
    first = client.post(
        '/v1/workspace/discussions',
        headers={'X-User-Id': 'discussion-owner', 'X-User-Role': 'lead'},
        json={'project_id': 'proj-a', 'body': 'handoff note alpha', 'mentions': ['ops']},
    )
    assert first.status_code == 200
    assert first.json()['data']['project_id'] == 'proj-a'

    second = client.post(
        '/v1/workspace/discussions',
        headers={'X-User-Id': 'discussion-owner'},
        json={'project_id': 'proj-b', 'body': 'handoff note beta', 'mentions': []},
    )
    assert second.status_code == 200

    filtered = client.get('/v1/workspace/discussions?project_id=proj-a', headers={'X-User-Id': 'discussion-owner'})
    assert filtered.status_code == 200
    items = filtered.json()['data']['items']
    assert len(items) == 1
    assert items[0]['body'] == 'handoff note alpha'

    foreign = client.get('/v1/workspace/discussions', headers={'X-User-Id': 'other-user'})
    assert foreign.status_code == 200
    assert foreign.json()['data']['items'] == []



def test_cycle_card_detail_returns_summary_and_previews(client: TestClient, db_session) -> None:
    cycle_id = _create_cycle(client, user='card-owner', project_id='proj-card', key='card-1')
    cycle = db_session.get(Cycle, cycle_id)
    assert cycle is not None
    cycle.current_state = CycleState.HUMAN_APPROVAL_PENDING
    cycle.user_status = UserStatus.APPROVAL_REQUIRED
    cycle.active_approval_id = 'approval-card-1'
    db_session.commit()

    comment = client.post(
        f'/v1/cycles/{cycle_id}/comments',
        headers={'X-User-Id': 'card-owner'},
        json={'body': 'review before merge', 'mentions': ['qa']},
    )
    assert comment.status_code == 200

    response = client.get(f'/v1/cycles/{cycle_id}/card', headers={'X-User-Id': 'card-owner'})
    assert response.status_code == 200
    data = response.json()['data']
    assert data['cycle']['cycle_id'] == cycle_id
    assert data['summary']['approval_required'] is True
    assert data['comment_count'] >= 1
    assert data['comments_preview'][0]['body'] == 'review before merge'
    assert 'review-captain' in data['suggested_agents']

    forbidden = client.get(f'/v1/cycles/{cycle_id}/card', headers={'X-User-Id': 'intruder'})
    assert forbidden.status_code == 403



def test_runtime_registrations_keep_latest_per_runtime_and_scope(client: TestClient) -> None:
    for status in ('online', 'busy'):
        response = client.post(
            '/v1/runtime/registrations',
            headers={'X-User-Id': 'runtime-user'},
            json={
                'runtime_id': 'daemon-1',
                'workspace_id': 'ws-1',
                'project_id': 'proj-runtime',
                'label': 'Primary daemon',
                'status': status,
                'mode': 'daemon',
                'version': '1.0.0',
                'capabilities': ['board-stream'],
                'metadata': {'slot': 1},
            },
        )
        assert response.status_code == 200

    client.post(
        '/v1/runtime/registrations',
        headers={'X-User-Id': 'other-runtime-user'},
        json={
            'runtime_id': 'daemon-2',
            'workspace_id': 'ws-2',
            'project_id': 'proj-other',
            'label': 'Foreign daemon',
            'status': 'online',
            'mode': 'daemon',
            'version': '1.0.0',
            'capabilities': ['cycle-stream'],
            'metadata': {},
        },
    )

    response = client.get('/v1/runtime/registrations?project_id=proj-runtime', headers={'X-User-Id': 'runtime-user'})
    assert response.status_code == 200
    items = response.json()['data']['items']
    assert len(items) == 1
    assert items[0]['runtime_id'] == 'daemon-1'
    assert items[0]['status'] == 'busy'



def test_workbench_page_renders_discussion_card_and_runtime_registration_sections(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    assert 'Workspace discussion' in response.text
    assert 'Issue card detail' in response.text
    assert 'Runtime registrations' in response.text
    assert '/v1/workspace/discussions' in response.text
    assert '/v1/runtime/registrations' in response.text
    assert '/v1/cycles/' in response.text
