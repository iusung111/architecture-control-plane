from datetime import datetime, timezone

from fastapi.testclient import TestClient
from app.db.models import Approval, AuditEvent, Cycle, Job, Receipt
from app.domain.enums import ApprovalState, CycleState, JobState, UserStatus


def test_workbench_page_renders_multica_inspired_surface(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    assert 'ACP Live Workbench' in response.text
    assert '/workbench-assets/workbench-core.js' in response.text
    assert '/workbench-assets/workbench-main.js' in response.text
    assert 'Activity timeline' in response.text




def test_workbench_asset_route_serves_split_javascript(client: TestClient) -> None:
    response = client.get('/workbench-assets/workbench-main.js')
    assert response.status_code == 200
    assert 'function selectCycle(' in response.text

def test_cycle_board_groups_cycles_into_multica_style_columns(client: TestClient, db_session) -> None:
    created = []
    for idx in range(4):
        response = client.post(
            '/v1/cycles',
            headers={'X-User-Id': 'board-owner', 'Idempotency-Key': f'board-{idx}'},
            json={'project_id': 'proj-board', 'user_input': f'payload-{idx}'},
        )
        assert response.status_code == 201
        created.append(response.json()['data']['cycle_id'])

    cycle_map = {cycle_id: db_session.get(Cycle, cycle_id) for cycle_id in created}
    assert all(cycle_map.values())
    cycle_map[created[0]].current_state = CycleState.INTENT_ACCEPTED
    cycle_map[created[1]].current_state = CycleState.EXECUTION_ATTEMPTED
    cycle_map[created[1]].user_status = UserStatus.IN_PROGRESS
    cycle_map[created[2]].current_state = CycleState.HUMAN_APPROVAL_PENDING
    cycle_map[created[2]].user_status = UserStatus.APPROVAL_REQUIRED
    cycle_map[created[3]].current_state = CycleState.TERMINALIZED
    cycle_map[created[3]].user_status = UserStatus.COMPLETED
    db_session.commit()

    response = client.get('/v1/cycles/board', headers={'X-User-Id': 'board-owner'}, params={'project_id': 'proj-board'})
    assert response.status_code == 200
    body = response.json()['data']
    assert body['total_count'] == 4
    columns = {column['key']: column for column in body['columns']}
    assert columns['queued']['count'] == 1
    assert columns['in_progress']['count'] == 1
    assert columns['review']['count'] == 1
    assert columns['done']['count'] == 1
    assert columns['blocked']['count'] == 0
    assert columns['failed']['count'] == 0


def test_cycle_timeline_merges_audit_jobs_approvals_and_receipts(client: TestClient, db_session) -> None:
    response = client.post(
        '/v1/cycles',
        headers={'X-User-Id': 'timeline-owner', 'Idempotency-Key': 'timeline-001'},
        json={'project_id': 'proj-time', 'user_input': 'timeline please'},
    )
    cycle_id = response.json()['data']['cycle_id']
    cycle = db_session.get(Cycle, cycle_id)
    assert cycle is not None

    approval = Approval(
        approval_id='approval-1',
        cycle_id=cycle_id,
        approval_state=ApprovalState.APPROVED,
        required_role='approver',
        actor_id='approver-1',
        expires_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        acted_at=datetime(2026, 1, 1, 12, 3, tzinfo=timezone.utc),
    )
    job = Job(
        job_id='job-1',
        cycle_id=cycle_id,
        job_type='run_verification',
        job_state=JobState.RUNNING,
        payload={'requested_by': 'timeline-owner', 'trigger': 'create'},
        dedup_key='timeline-job-1',
    )
    receipt = Receipt(
        receipt_id='receipt-1',
        cycle_id=cycle_id,
        iteration_id=None,
        receipt_type='completion_summary',
        summary='Cycle completed without manual approval',
        payload={'artifact_id': 'artifact-1'},
    )
    db_session.add_all([approval, job, receipt])
    db_session.add(
        AuditEvent(
            audit_event_id='audit-1',
            cycle_id=cycle_id,
            actor_id='timeline-owner',
            event_type='cycle.completed',
            event_payload={'completion_mode': 'automatic'},
        )
    )
    db_session.commit()

    timeline = client.get(f'/v1/cycles/{cycle_id}/timeline', headers={'X-User-Id': 'timeline-owner'})
    assert timeline.status_code == 200
    events = timeline.json()['data']['events']
    event_types = {item['event_type'] for item in events}
    assert 'cycle.created' in event_types
    assert 'cycle.completed' in event_types
    assert 'job.run_verification.running' in event_types
    assert 'approval.approved' in event_types
    assert 'receipt.completion_summary' in event_types


def test_cycle_board_event_stream_emits_snapshot(client: TestClient) -> None:
    created = client.post(
        '/v1/cycles',
        headers={'X-User-Id': 'board-stream-owner', 'Idempotency-Key': 'board-stream-001'},
        json={'project_id': 'proj-stream', 'user_input': 'stream board'},
    )
    assert created.status_code == 201

    with client.stream(
        'GET',
        '/v1/cycles/board/events?poll_interval_seconds=0.05&stream_timeout_seconds=0.06',
        headers={'X-User-Id': 'board-stream-owner'},
    ) as response:
        assert response.status_code == 200
        payload = ''.join(response.iter_text())

    assert 'event: board.snapshot' in payload
    assert 'proj-stream' in payload


def test_cycle_timeline_respects_owner_scope(client: TestClient) -> None:
    response = client.post(
        '/v1/cycles',
        headers={'X-User-Id': 'owner-a', 'Idempotency-Key': 'timeline-scope'},
        json={'project_id': 'proj-scope', 'user_input': 'scope check'},
    )
    cycle_id = response.json()['data']['cycle_id']

    forbidden = client.get(f'/v1/cycles/{cycle_id}/timeline', headers={'X-User-Id': 'owner-b'})
    assert forbidden.status_code == 403


def test_workbench_page_exposes_quick_start_and_issue_actions(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    body = response.text
    assert 'Quick start' in body
    assert 'Issue actions' in body
    assert 'id="create-cycle-project-id"' in body
    assert 'id="create-cycle-user-input"' in body
    assert 'id="create-cycle-btn"' in body
    assert 'id="create-cycle-and-run-btn"' in body
    assert 'id="issue-action-approval-id"' in body
    assert 'id="replan-prompt"' in body
    assert 'id="replan-constraints"' in body
    assert 'id="issue-approve-btn"' in body
    assert 'id="issue-retry-btn"' in body
    assert 'id="issue-replan-btn"' in body
    assert 'id="issue-remote-check-btn"' in body


def test_workbench_page_exposes_auth_presets_and_pending_approvals(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    body = response.text
    assert 'id="auth-preset-operator"' in body
    assert 'id="auth-preset-reviewer"' in body
    assert 'id="auth-preset-audit"' in body
    assert 'id="validate-auth"' in body
    assert 'Pending approvals' in body
    assert 'id="pending-approvals"' in body
    assert 'id="refresh-pending-approvals"' in body


def test_workbench_page_exposes_result_and_remote_execution_detail_surfaces(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    body = response.text
    assert 'id="issue-card-detail"' in body
    assert 'id="remote-workspace-execution-detail"' in body
    assert 'id="remote-workspace-execution-detail"' in body
    assert 'id="persistent-workspace-sessions"' in body
    assert 'id="save-persistent-session"' in body


def test_workbench_page_exposes_personal_inbox_approval_review_and_modal_surfaces(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    body = response.text
    assert 'Personal inbox' in body
    assert 'Approval review context' in body
    assert 'id="personal-inbox"' in body
    assert 'id="approval-review-context"' in body
    assert 'id="smart-filters"' in body
    assert 'id="action-modal"' in body
    assert 'id="toast-stack"' in body


def test_workbench_page_exposes_resolution_handoff_and_enhanced_saved_views(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    body = response.text
    assert 'Resolution & handoff' in body
    assert 'id="resolve-cycle-btn"' in body
    assert 'id="build-handoff-bundle-btn"' in body
    assert 'id="post-handoff-bundle-btn"' in body
    assert 'id="resolution-summary"' in body
    assert 'id="handoff-bundle"' in body
    assert 'id="workbench-view-notes"' in body
    assert 'id="save-default-workbench-view"' in body
    asset_response = client.get('/workbench-assets/workbench-render-remote.js')
    assert asset_response.status_code == 200
    assert 'Set default' in asset_response.text or 'Default view' in asset_response.text
