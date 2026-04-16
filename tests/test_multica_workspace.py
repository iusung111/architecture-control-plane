from fastapi.testclient import TestClient

from app.db.models import Cycle, Job, NotificationOutbox
from app.domain.enums import CycleState, JobState, OutboxDeliveryState, UserStatus


def _create_cycle(client: TestClient, *, user: str, project_id: str, key: str) -> str:
    response = client.post(
        '/v1/cycles',
        headers={'X-User-Id': user, 'Idempotency-Key': key},
        json={'project_id': project_id, 'user_input': f'work for {project_id}'},
    )
    assert response.status_code == 201
    return response.json()['data']['cycle_id']


def test_workspace_overview_and_agent_profiles_reflect_scoped_activity(client: TestClient, db_session) -> None:
    cycle_id = _create_cycle(client, user='workspace-owner', project_id='proj-alpha', key='workspace-1')
    _create_cycle(client, user='workspace-owner', project_id='proj-beta', key='workspace-2')
    _create_cycle(client, user='other-owner', project_id='proj-foreign', key='workspace-3')

    cycle = db_session.get(Cycle, cycle_id)
    assert cycle is not None
    cycle.current_state = CycleState.HUMAN_APPROVAL_PENDING
    cycle.user_status = UserStatus.APPROVAL_REQUIRED
    db_session.commit()

    comment = client.post(
        f'/v1/cycles/{cycle_id}/comments',
        headers={'X-User-Id': 'workspace-owner'},
        json={'body': 'Need legal review before release', 'mentions': ['legal', 'ops']},
    )
    assert comment.status_code == 200

    overview = client.get('/v1/workspace/overview?project_id=proj-alpha', headers={'X-User-Id': 'workspace-owner'})
    assert overview.status_code == 200
    data = overview.json()['data']
    assert data['selected_project_id'] == 'proj-alpha'
    assert data['totals']['cycles'] == 1
    assert data['totals']['pending_reviews'] == 1
    assert data['projects'][0]['project_id'] == 'proj-alpha'
    assert data['recent_comments'][0]['body'] == 'Need legal review before release'

    agents = client.get('/v1/agents/profiles?project_id=proj-alpha', headers={'X-User-Id': 'workspace-owner'})
    assert agents.status_code == 200
    items = {item['agent_id']: item for item in agents.json()['data']['items']}
    assert set(items) == {'planner-coordinator', 'verification-specialist', 'review-captain', 'recovery-operator'}
    assert items['review-captain']['metrics']['pending_reviews'] == 1
    assert items['planner-coordinator']['metrics']['active_cycles'] == 1


def test_cycle_comments_post_list_and_scope_are_enforced(client: TestClient) -> None:
    cycle_id = _create_cycle(client, user='comment-owner', project_id='proj-comments', key='comment-1')

    created = client.post(
        f'/v1/cycles/{cycle_id}/comments',
        headers={'X-User-Id': 'comment-owner', 'X-User-Role': 'admin'},
        json={'body': 'Ship this after smoke passes', 'mentions': ['qa']},
    )
    assert created.status_code == 200
    body = created.json()['data']
    assert body['body'] == 'Ship this after smoke passes'
    assert body['mentions'] == ['qa']
    assert body['actor_role'] == 'admin'

    listed = client.get(f'/v1/cycles/{cycle_id}/comments', headers={'X-User-Id': 'comment-owner'})
    assert listed.status_code == 200
    assert listed.json()['data']['items'][0]['body'] == 'Ship this after smoke passes'

    forbidden = client.get(f'/v1/cycles/{cycle_id}/comments', headers={'X-User-Id': 'comment-intruder'})
    assert forbidden.status_code == 403


def test_runtime_panel_surfaces_jobs_and_outbox_signals(client: TestClient, db_session) -> None:
    cycle_id = _create_cycle(client, user='runtime-owner', project_id='proj-runtime', key='runtime-1')
    cycle = db_session.get(Cycle, cycle_id)
    assert cycle is not None

    db_session.add(
        Job(
            job_id='runtime-job-failed',
            cycle_id=cycle_id,
            job_type='retry_cycle',
            job_state=JobState.FAILED,
            payload={'requested_by': 'runtime-owner', 'reason': 'transient'},
            dedup_key='runtime-job-failed',
        )
    )
    outbox = db_session.query(NotificationOutbox).filter(NotificationOutbox.cycle_id == cycle_id).first()
    assert outbox is not None
    outbox.delivery_state = OutboxDeliveryState.FAILED
    db_session.commit()

    response = client.get('/v1/runtime/panel?project_id=proj-runtime', headers={'X-User-Id': 'runtime-owner'})
    assert response.status_code == 200
    data = response.json()['data']
    metrics = {item['key']: item['value'] for item in data['queue_metrics']}
    assert metrics['jobs_pending'] >= 1
    assert metrics['jobs_failed'] >= 1
    assert metrics['notifications_pending'] >= 1
    assert any(signal for signal in data['signals'])
    assert data['recent_jobs'][0]['source'] == 'job'


def test_workbench_page_renders_workspace_agent_runtime_and_comments_sections(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    assert 'Workspace context' in response.text
    assert 'Agent roster' in response.text
    assert 'Runtime panel' in response.text
    assert 'Post comment' in response.text
    assert '/v1/workspace/overview' in response.text
    assert '/v1/agents/profiles' in response.text
    assert '/v1/runtime/panel' in response.text
