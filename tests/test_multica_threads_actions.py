from datetime import datetime, timedelta, timezone

from app.db.models import AuditEvent

from fastapi.testclient import TestClient

from app.core.config import get_settings


def _create_cycle(client: TestClient, *, user: str, project_id: str, key: str) -> str:
    response = client.post(
        '/v1/cycles',
        headers={'X-User-Id': user, 'Idempotency-Key': key},
        json={'project_id': project_id, 'user_input': f'work for {project_id}'},
    )
    assert response.status_code == 201
    return response.json()['data']['cycle_id']


def test_workspace_discussion_replies_round_trip_and_scope(client: TestClient) -> None:
    created = client.post(
        '/v1/workspace/discussions',
        headers={'X-User-Id': 'thread-owner', 'X-User-Role': 'lead'},
        json={'project_id': 'proj-thread', 'body': 'handoff into thread', 'mentions': ['ops']},
    )
    assert created.status_code == 200
    discussion_id = created.json()['data']['discussion_id']

    reply = client.post(
        f'/v1/workspace/discussions/{discussion_id}/replies',
        headers={'X-User-Id': 'thread-owner', 'X-User-Role': 'operator'},
        json={'body': 'reply from operator', 'mentions': ['qa']},
    )
    assert reply.status_code == 200
    assert reply.json()['data']['discussion_id'] == discussion_id

    listed = client.get(
        f'/v1/workspace/discussions/{discussion_id}/replies',
        headers={'X-User-Id': 'thread-owner'},
    )
    assert listed.status_code == 200
    data = listed.json()['data']
    assert data['discussion_id'] == discussion_id
    assert data['items'][0]['body'] == 'reply from operator'
    assert data['items'][0]['mentions'] == ['qa']

    discussions = client.get('/v1/workspace/discussions?project_id=proj-thread', headers={'X-User-Id': 'thread-owner'})
    assert discussions.status_code == 200
    assert discussions.json()['data']['items'][0]['reply_count'] >= 1

    forbidden = client.get(
        f'/v1/workspace/discussions/{discussion_id}/replies',
        headers={'X-User-Id': 'intruder'},
    )
    assert forbidden.status_code == 403


def test_cycle_assignment_round_trip_and_card_reflects_current_assignment(client: TestClient) -> None:
    cycle_id = _create_cycle(client, user='assignment-owner', project_id='proj-assignment', key='assign-1')

    created = client.post(
        f'/v1/cycles/{cycle_id}/assignments',
        headers={'X-User-Id': 'assignment-owner', 'X-User-Role': 'lead'},
        json={'agent_id': 'review-captain', 'assignment_role': 'reviewer', 'note': 'take final review'},
    )
    assert created.status_code == 200
    body = created.json()['data']
    assert body['agent_id'] == 'review-captain'
    assert body['assignment_role'] == 'reviewer'

    listed = client.get(f'/v1/cycles/{cycle_id}/assignments', headers={'X-User-Id': 'assignment-owner'})
    assert listed.status_code == 200
    assert listed.json()['data']['items'][0]['note'] == 'take final review'

    card = client.get(f'/v1/cycles/{cycle_id}/card', headers={'X-User-Id': 'assignment-owner'})
    assert card.status_code == 200
    assert card.json()['data']['current_assignment']['agent_id'] == 'review-captain'

    forbidden = client.get(f'/v1/cycles/{cycle_id}/assignments', headers={'X-User-Id': 'other-user'})
    assert forbidden.status_code == 403


def test_runtime_actions_round_trip_and_scope(client: TestClient) -> None:
    registered = client.post(
        '/v1/runtime/registrations',
        headers={'X-User-Id': 'runtime-action-owner'},
        json={
            'runtime_id': 'daemon-actions-1',
            'workspace_id': 'ws-actions',
            'project_id': 'proj-actions',
            'label': 'Action daemon',
            'status': 'online',
            'mode': 'daemon',
            'version': '1.2.3',
            'capabilities': ['cycle-stream'],
            'metadata': {'slot': 2},
        },
    )
    assert registered.status_code == 200

    action = client.post(
        '/v1/runtime/registrations/daemon-actions-1/actions',
        headers={'X-User-Id': 'runtime-action-owner', 'X-User-Role': 'operator'},
        json={'action': 'drain', 'arguments': {'reason': 'deploy'}},
    )
    assert action.status_code == 200
    assert action.json()['data']['action'] == 'drain'
    assert action.json()['data']['arguments'] == {'reason': 'deploy'}

    listed = client.get('/v1/runtime/registrations/daemon-actions-1/actions', headers={'X-User-Id': 'runtime-action-owner'})
    assert listed.status_code == 200
    assert listed.json()['data']['items'][0]['status'] == 'queued'

    foreign = client.get('/v1/runtime/registrations/daemon-actions-1/actions', headers={'X-User-Id': 'foreign-runtime-user'})
    assert foreign.status_code == 404


def test_workbench_page_renders_thread_assignment_and_runtime_action_sections(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    assert 'Discussion thread replies' in response.text
    assert 'Assignment control' in response.text
    assert 'Runtime action panel' in response.text
    assert '/v1/workspace/discussions/' in response.text
    assert '/v1/cycles/' in response.text
    assert '/v1/runtime/registrations/' in response.text


def test_workspace_discussion_mention_filters_apply_to_threads(client: TestClient) -> None:
    root = client.post(
        '/v1/workspace/discussions',
        headers={'X-User-Id': 'mention-owner'},
        json={'project_id': 'proj-mention', 'body': 'handoff for ops', 'mentions': ['ops', 'qa']},
    )
    assert root.status_code == 200
    discussion_id = root.json()['data']['discussion_id']

    client.post(
        f'/v1/workspace/discussions/{discussion_id}/replies',
        headers={'X-User-Id': 'mention-owner'},
        json={'body': 'reply for qa', 'mentions': ['qa']},
    )
    client.post(
        f'/v1/workspace/discussions/{discussion_id}/replies',
        headers={'X-User-Id': 'mention-owner'},
        json={'body': 'reply for eng', 'mentions': ['eng']},
    )

    filtered_threads = client.get('/v1/workspace/discussions?mention=ops', headers={'X-User-Id': 'mention-owner'})
    assert filtered_threads.status_code == 200
    assert filtered_threads.json()['data']['mention_filter'] == 'ops'
    assert len(filtered_threads.json()['data']['items']) == 1

    filtered_replies = client.get(
        f'/v1/workspace/discussions/{discussion_id}/replies?mention=qa',
        headers={'X-User-Id': 'mention-owner'},
    )
    assert filtered_replies.status_code == 200
    data = filtered_replies.json()['data']
    assert data['mention_filter'] == 'qa'
    assert [item['body'] for item in data['items']] == ['reply for qa']


def test_assignment_suggestions_reflect_cycle_state_and_card(client: TestClient, db_session) -> None:
    cycle_id = _create_cycle(client, user='suggest-owner', project_id='proj-suggest', key='suggest-1')

    suggestions = client.get(f'/v1/cycles/{cycle_id}/assignment-suggestions', headers={'X-User-Id': 'suggest-owner'})
    assert suggestions.status_code == 200
    bundle = suggestions.json()['data']
    assert bundle['cycle_id'] == cycle_id
    assert bundle['items'][0]['agent_id'] == 'planner-coordinator'
    assert bundle['items'][0]['recommended_role'] == 'primary'

    card = client.get(f'/v1/cycles/{cycle_id}/card', headers={'X-User-Id': 'suggest-owner'})
    assert card.status_code == 200
    assert card.json()['data']['assignment_suggestions'][0]['agent_id'] == 'planner-coordinator'


def test_runtime_action_acknowledge_and_transition_are_reflected_in_list(client: TestClient) -> None:
    registered = client.post(
        '/v1/runtime/registrations',
        headers={'X-User-Id': 'runtime-transition-owner'},
        json={
            'runtime_id': 'daemon-actions-2',
            'workspace_id': 'ws-actions',
            'project_id': 'proj-actions',
            'label': 'Action daemon',
            'status': 'online',
            'mode': 'daemon',
            'version': '2.0.0',
            'capabilities': ['cycle-stream'],
            'metadata': {'slot': 3},
        },
    )
    assert registered.status_code == 200

    enqueued = client.post(
        '/v1/runtime/registrations/daemon-actions-2/actions',
        headers={'X-User-Id': 'runtime-transition-owner', 'X-User-Role': 'operator'},
        json={'action': 'sync', 'arguments': {'target': 'workspace'}},
    )
    assert enqueued.status_code == 200
    action_id = enqueued.json()['data']['action_id']

    ack = client.post(
        f'/v1/runtime/registrations/daemon-actions-2/actions/{action_id}/acknowledge',
        headers={'X-User-Id': 'runtime-transition-owner', 'X-User-Role': 'operator'},
        json={'note': 'picked up by daemon'},
    )
    assert ack.status_code == 200
    assert ack.json()['data']['status'] == 'acknowledged'
    assert ack.json()['data']['acknowledged_by'] == 'runtime-transition-owner'

    transitioned = client.post(
        f'/v1/runtime/registrations/daemon-actions-2/actions/{action_id}/state',
        headers={'X-User-Id': 'runtime-transition-owner', 'X-User-Role': 'operator'},
        json={'status': 'running', 'note': 'starting sync', 'metadata': {'stage': 'dispatch'}},
    )
    assert transitioned.status_code == 200
    assert transitioned.json()['data']['status'] == 'running'
    assert transitioned.json()['data']['metadata']['stage'] == 'dispatch'

    completed = client.post(
        f'/v1/runtime/registrations/daemon-actions-2/actions/{action_id}/state',
        headers={'X-User-Id': 'runtime-transition-owner', 'X-User-Role': 'operator'},
        json={'status': 'succeeded', 'note': 'sync complete', 'metadata': {'items': 4}},
    )
    assert completed.status_code == 200
    assert completed.json()['data']['status'] == 'succeeded'

    listed = client.get('/v1/runtime/registrations/daemon-actions-2/actions', headers={'X-User-Id': 'runtime-transition-owner'})
    assert listed.status_code == 200
    latest = listed.json()['data']['items'][0]
    assert latest['action_id'] == action_id
    assert latest['status'] == 'succeeded'
    assert latest['acknowledged_by'] == 'runtime-transition-owner'
    assert latest['metadata']['items'] == 4


def test_workbench_page_renders_mention_suggestions_and_runtime_transition_controls(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    assert 'filter by mention' in response.text
    assert 'assignment-suggestions' in response.text
    assert '/assignment-suggestions' in response.text
    assert '/acknowledge' in response.text
    assert '/state' in response.text


def test_workspace_discussion_resolution_and_pinning_are_reflected_in_listing(client: TestClient) -> None:
    created = client.post(
        '/v1/workspace/discussions',
        headers={'X-User-Id': 'resolution-owner'},
        json={'project_id': 'proj-resolution', 'body': 'need closure and visibility', 'mentions': ['ops']},
    )
    assert created.status_code == 200
    discussion_id = created.json()['data']['discussion_id']

    pinned = client.post(
        f'/v1/workspace/discussions/{discussion_id}/pin',
        headers={'X-User-Id': 'resolution-owner', 'X-User-Role': 'lead'},
        json={'pinned': True, 'note': 'pin for standup'},
    )
    assert pinned.status_code == 200
    assert pinned.json()['data']['is_pinned'] is True

    resolved = client.post(
        f'/v1/workspace/discussions/{discussion_id}/resolve',
        headers={'X-User-Id': 'resolution-owner', 'X-User-Role': 'lead'},
        json={'resolved': True, 'note': 'handled'},
    )
    assert resolved.status_code == 200
    assert resolved.json()['data']['is_resolved'] is True
    assert resolved.json()['data']['resolved_by'] == 'resolution-owner'

    listed = client.get('/v1/workspace/discussions?project_id=proj-resolution', headers={'X-User-Id': 'resolution-owner'})
    assert listed.status_code == 200
    item = listed.json()['data']['items'][0]
    assert item['discussion_id'] == discussion_id
    assert item['is_pinned'] is True
    assert item['is_resolved'] is True


def test_assignment_suggestion_feedback_round_trip_and_card_reflection(client: TestClient) -> None:
    cycle_id = _create_cycle(client, user='feedback-owner', project_id='proj-feedback', key='feedback-1')

    feedback = client.post(
        f'/v1/cycles/{cycle_id}/assignment-suggestions/feedback',
        headers={'X-User-Id': 'feedback-owner', 'X-User-Role': 'lead'},
        json={'agent_id': 'planner-coordinator', 'feedback': 'accepted', 'note': 'good fit'},
    )
    assert feedback.status_code == 200
    assert feedback.json()['data']['feedback'] == 'accepted'

    suggestions = client.get(f'/v1/cycles/{cycle_id}/assignment-suggestions', headers={'X-User-Id': 'feedback-owner'})
    assert suggestions.status_code == 200
    first = suggestions.json()['data']['items'][0]
    assert first['agent_id'] == 'planner-coordinator'
    assert first['last_feedback'] == 'accepted'
    assert first['feedback_note'] == 'good fit'

    card = client.get(f'/v1/cycles/{cycle_id}/card', headers={'X-User-Id': 'feedback-owner'})
    assert card.status_code == 200
    assert card.json()['data']['assignment_suggestions'][0]['last_feedback'] == 'accepted'


def test_runtime_action_receipts_are_recorded_and_listed(client: TestClient) -> None:
    registered = client.post(
        '/v1/runtime/registrations',
        headers={'X-User-Id': 'receipt-owner'},
        json={
            'runtime_id': 'daemon-actions-3',
            'workspace_id': 'ws-actions',
            'project_id': 'proj-actions',
            'label': 'Receipt daemon',
            'status': 'online',
            'mode': 'daemon',
            'version': '3.0.0',
            'capabilities': ['cycle-stream'],
            'metadata': {'slot': 4},
        },
    )
    assert registered.status_code == 200

    enqueued = client.post(
        '/v1/runtime/registrations/daemon-actions-3/actions',
        headers={'X-User-Id': 'receipt-owner', 'X-User-Role': 'operator'},
        json={'action': 'refresh', 'arguments': {'scope': 'project'}},
    )
    assert enqueued.status_code == 200
    action_id = enqueued.json()['data']['action_id']

    receipt = client.post(
        f'/v1/runtime/registrations/daemon-actions-3/actions/{action_id}/receipts',
        headers={'X-User-Id': 'receipt-owner', 'X-User-Role': 'operator'},
        json={'summary': 'refresh finished', 'status': 'succeeded', 'metadata': {'updated': 7}},
    )
    assert receipt.status_code == 200
    assert receipt.json()['data']['summary'] == 'refresh finished'

    listed = client.get(
        f'/v1/runtime/registrations/daemon-actions-3/actions/{action_id}/receipts',
        headers={'X-User-Id': 'receipt-owner'},
    )
    assert listed.status_code == 200
    assert listed.json()['data']['items'][0]['status'] == 'succeeded'

    actions = client.get('/v1/runtime/registrations/daemon-actions-3/actions', headers={'X-User-Id': 'receipt-owner'})
    assert actions.status_code == 200
    item = actions.json()['data']['items'][0]
    assert item['latest_receipt_summary'] == 'refresh finished'
    assert item['receipt_count'] >= 1


def test_workbench_page_renders_resolution_feedback_and_receipt_controls(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    assert '/resolve' in response.text
    assert '/pin' in response.text
    assert '/assignment-suggestions/feedback' in response.text
    assert '/receipts' in response.text


def test_workspace_discussion_grouping_and_search(client: TestClient) -> None:
    client.post(
        '/v1/workspace/discussions',
        headers={'X-User-Id': 'group-owner'},
        json={'project_id': 'proj-alpha', 'body': 'alpha handoff for ops', 'mentions': ['ops']},
    )
    client.post(
        '/v1/workspace/discussions',
        headers={'X-User-Id': 'group-owner'},
        json={'project_id': 'proj-beta', 'body': 'beta review for qa', 'mentions': ['qa']},
    )
    client.post(
        '/v1/workspace/discussions',
        headers={'X-User-Id': 'group-owner'},
        json={'project_id': 'proj-alpha', 'body': 'alpha follow-up for release', 'mentions': ['release']},
    )

    search = client.get('/v1/workspace/discussions?query=beta', headers={'X-User-Id': 'group-owner'})
    assert search.status_code == 200
    assert search.json()['data']['query'] == 'beta'
    assert [item['project_id'] for item in search.json()['data']['items']] == ['proj-beta']

    grouped = client.get('/v1/workspace/discussions/groups', headers={'X-User-Id': 'group-owner'})
    assert grouped.status_code == 200
    groups = grouped.json()['data']['items']
    keys = {item['group_key'] for item in groups}
    assert {'proj-alpha', 'proj-beta'} <= keys
    alpha = next(item for item in groups if item['group_key'] == 'proj-alpha')
    assert alpha['total_count'] == 2
    assert alpha['unresolved_count'] == 2


def test_assignment_learning_weights_and_suggestions_reflect_feedback_history(client: TestClient) -> None:
    cycle_id = _create_cycle(client, user='learning-owner', project_id='proj-learning', key='learn-1')
    for feedback in ('accepted', 'accepted', 'applied', 'dismissed'):
        response = client.post(
            f'/v1/cycles/{cycle_id}/assignment-suggestions/feedback',
            headers={'X-User-Id': 'learning-owner', 'X-User-Role': 'lead'},
            json={'agent_id': 'planner-coordinator', 'feedback': feedback, 'note': feedback},
        )
        assert response.status_code == 200

    weights = client.get(f'/v1/cycles/{cycle_id}/assignment-learning-weights', headers={'X-User-Id': 'learning-owner'})
    assert weights.status_code == 200
    row = next(item for item in weights.json()['data']['items'] if item['agent_id'] == 'planner-coordinator')
    assert row['accepted_count'] == 2
    assert row['applied_count'] == 1
    assert row['dismissed_count'] == 1
    assert row['learned_weight'] > 0

    suggestions = client.get(f'/v1/cycles/{cycle_id}/assignment-suggestions', headers={'X-User-Id': 'learning-owner'})
    assert suggestions.status_code == 200
    suggested = next(item for item in suggestions.json()['data']['items'] if item['agent_id'] == 'planner-coordinator')
    assert suggested['accepted_count'] == 2
    assert suggested['applied_count'] == 1
    assert suggested['dismissed_count'] == 1
    assert suggested['learned_weight'] > 0


def test_runtime_action_timeline_includes_enqueue_ack_state_and_receipt(client: TestClient) -> None:
    registered = client.post(
        '/v1/runtime/registrations',
        headers={'X-User-Id': 'timeline-owner'},
        json={
            'runtime_id': 'daemon-actions-timeline',
            'workspace_id': 'ws-timeline',
            'project_id': 'proj-timeline',
            'label': 'Timeline daemon',
            'status': 'online',
            'mode': 'daemon',
            'version': '4.0.0',
            'capabilities': ['cycle-stream'],
            'metadata': {'slot': 9},
        },
    )
    assert registered.status_code == 200
    enqueued = client.post(
        '/v1/runtime/registrations/daemon-actions-timeline/actions',
        headers={'X-User-Id': 'timeline-owner', 'X-User-Role': 'operator'},
        json={'action': 'sync', 'arguments': {'scope': 'timeline'}},
    )
    assert enqueued.status_code == 200
    action_id = enqueued.json()['data']['action_id']
    assert client.post(
        f'/v1/runtime/registrations/daemon-actions-timeline/actions/{action_id}/acknowledge',
        headers={'X-User-Id': 'timeline-owner', 'X-User-Role': 'operator'},
        json={'note': 'ack now'},
    ).status_code == 200
    assert client.post(
        f'/v1/runtime/registrations/daemon-actions-timeline/actions/{action_id}/state',
        headers={'X-User-Id': 'timeline-owner', 'X-User-Role': 'operator'},
        json={'status': 'running', 'note': 'dispatch', 'metadata': {'stage': 'dispatch'}},
    ).status_code == 200
    assert client.post(
        f'/v1/runtime/registrations/daemon-actions-timeline/actions/{action_id}/receipts',
        headers={'X-User-Id': 'timeline-owner', 'X-User-Role': 'operator'},
        json={'summary': 'partial receipt', 'status': 'running', 'metadata': {'items': 2}},
    ).status_code == 200

    timeline = client.get(
        f'/v1/runtime/registrations/daemon-actions-timeline/actions/{action_id}/timeline',
        headers={'X-User-Id': 'timeline-owner'},
    )
    assert timeline.status_code == 200
    events = timeline.json()['data']['items']
    event_types = {item['event_type'] for item in events}
    assert 'runtime.action.enqueued' in event_types
    assert 'runtime.action.acknowledged' in event_types
    assert 'runtime.action.state_changed' in event_types
    assert 'runtime.action.receipt.recorded' in event_types


def test_workbench_page_renders_grouping_learning_and_action_timeline_controls(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    assert 'discussion-search-filter' in response.text
    assert '/v1/workspace/discussions/groups' in response.text
    assert 'assignment-learning-weights' in response.text
    assert '/assignment-learning-weights' in response.text
    assert 'runtime-action-timeline' in response.text
    assert '/actions/' in response.text and '/timeline' in response.text


def test_workspace_discussion_saved_filters_and_search_ranking(client: TestClient) -> None:
    client.post(
        '/v1/workspace/discussions',
        headers={'X-User-Id': 'filter-owner'},
        json={'project_id': 'proj-filter', 'body': 'alpha beta beta rollout note', 'mentions': ['ops']},
    )
    client.post(
        '/v1/workspace/discussions',
        headers={'X-User-Id': 'filter-owner'},
        json={'project_id': 'proj-filter', 'body': 'alpha only note', 'mentions': ['qa']},
    )

    saved = client.post(
        '/v1/workspace/discussion-filters',
        headers={'X-User-Id': 'filter-owner'},
        json={'name': 'ops-beta', 'project_id': 'proj-filter', 'mention': 'ops', 'query': 'beta'},
    )
    assert saved.status_code == 200
    assert saved.json()['data']['name'] == 'ops-beta'

    saved_list = client.get('/v1/workspace/discussion-filters', headers={'X-User-Id': 'filter-owner'})
    assert saved_list.status_code == 200
    assert saved_list.json()['data']['items'][0]['query'] == 'beta'

    search = client.get('/v1/workspace/discussions?project_id=proj-filter&query=beta', headers={'X-User-Id': 'filter-owner'})
    assert search.status_code == 200
    item = search.json()['data']['items'][0]
    assert item['search_rank'] > 0
    assert 'beta' in item['matched_terms']
    assert item['body'] == 'alpha beta beta rollout note'


def test_assignment_learning_weights_apply_recency_decay(client: TestClient, db_session) -> None:
    cycle_id = _create_cycle(client, user='decay-owner', project_id='proj-decay', key='decay-1')
    feedback = client.post(
        f'/v1/cycles/{cycle_id}/assignment-suggestions/feedback',
        headers={'X-User-Id': 'decay-owner', 'X-User-Role': 'lead'},
        json={'agent_id': 'planner-coordinator', 'feedback': 'accepted', 'note': 'worked well'},
    )
    assert feedback.status_code == 200
    feedback_id = feedback.json()['data']['feedback_id']

    event = db_session.get(AuditEvent, feedback_id)
    assert event is not None
    event.occurred_at = datetime.now(timezone.utc) - timedelta(days=45)
    db_session.commit()

    weights = client.get(f'/v1/cycles/{cycle_id}/assignment-learning-weights', headers={'X-User-Id': 'decay-owner'})
    assert weights.status_code == 200
    row = next(item for item in weights.json()['data']['items'] if item['agent_id'] == 'planner-coordinator')
    assert row['accepted_count'] == 1
    assert 0 < row['weighted_accepted_count'] < 1
    assert 0 < row['recency_weight'] < 1

    suggestions = client.get(f'/v1/cycles/{cycle_id}/assignment-suggestions', headers={'X-User-Id': 'decay-owner'})
    assert suggestions.status_code == 200
    suggestion = next(item for item in suggestions.json()['data']['items'] if item['agent_id'] == 'planner-coordinator')
    assert suggestion['weighted_feedback_score'] >= 0
    assert 0 < suggestion['recency_weight'] < 1


def test_runtime_action_events_stream_emits_snapshot_and_timeout(client: TestClient) -> None:
    registered = client.post(
        '/v1/runtime/registrations',
        headers={'X-User-Id': 'runtime-stream-owner'},
        json={
            'runtime_id': 'daemon-actions-stream',
            'workspace_id': 'ws-stream',
            'project_id': 'proj-stream',
            'label': 'Stream daemon',
            'status': 'online',
            'mode': 'daemon',
            'version': '1.0.0',
            'capabilities': ['runtime-action-events'],
            'metadata': {},
        },
    )
    assert registered.status_code == 200

    enqueued = client.post(
        '/v1/runtime/registrations/daemon-actions-stream/actions',
        headers={'X-User-Id': 'runtime-stream-owner', 'X-User-Role': 'operator'},
        json={'action': 'sync', 'arguments': {'scope': 'live'}},
    )
    assert enqueued.status_code == 200
    action_id = enqueued.json()['data']['action_id']

    with client.stream(
        'GET',
        f'/v1/runtime/registrations/daemon-actions-stream/actions/{action_id}/events',
        headers={'X-User-Id': 'runtime-stream-owner'},
        params={'poll_interval_seconds': 0.05, 'heartbeat_seconds': 0.05, 'stream_timeout_seconds': 0.12},
    ) as response:
        assert response.status_code == 200
        payload = ''.join(response.iter_text())

    assert 'event: runtime.action.snapshot' in payload
    assert 'event: heartbeat' in payload
    assert 'event: stream.timeout' in payload
    assert f'"action_id":"{action_id}"' in payload


def test_workbench_page_renders_saved_filters_decay_and_runtime_action_stream(client: TestClient) -> None:
    response = client.get('/workbench')
    assert response.status_code == 200
    assert '/v1/workspace/discussion-filters' in response.text
    assert 'save-discussion-filter' in response.text
    assert 'runtime-action-state' in response.text
    assert '/actions/${encodeURIComponent(actionId)}/events' in response.text


def test_assignment_suggestions_reflect_remote_workspace_outcomes(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv('REMOTE_WORKSPACE_CALLBACK_TOKEN', 'assignment-callback')
    get_settings.cache_clear()

    cycle_id = _create_cycle(client, user='assignment-remote-owner', project_id='proj-remote-learning', key='assign-remote-1')
    assigned = client.post(
        f'/v1/cycles/{cycle_id}/assignments',
        headers={'X-User-Id': 'assignment-remote-owner', 'X-User-Role': 'lead'},
        json={'agent_id': 'planner-coordinator', 'assignment_role': 'primary', 'note': 'owns remote verification'},
    )
    assert assigned.status_code == 200

    snapshot = client.post(
        '/v1/remote-workspaces/snapshots',
        headers={'X-User-Id': 'assignment-remote-owner', 'X-User-Role': 'operator'},
        json={'workspace_id': f'cycle:{cycle_id}', 'cycle_id': cycle_id, 'project_id': 'proj-remote-learning', 'repo_url': 'https://github.com/example/repo', 'repo_branch': 'main'},
    )
    assert snapshot.status_code == 200

    queued = client.post(
        '/v1/remote-workspaces/executions',
        headers={'X-User-Id': 'assignment-remote-owner', 'X-User-Role': 'operator'},
        json={'workspace_id': f'cycle:{cycle_id}', 'cycle_id': cycle_id, 'project_id': 'proj-remote-learning', 'execution_kind': 'run_checks', 'command': 'pytest -q'},
    )
    assert queued.status_code == 200
    execution_id = queued.json()['data']['execution_id']

    callback = client.post(
        f'/v1/remote-workspaces/executions/{execution_id}/result',
        headers={'X-Remote-Workspace-Callback-Token': 'assignment-callback'},
        json={'workspace_id': f'cycle:{cycle_id}', 'cycle_id': cycle_id, 'project_id': 'proj-remote-learning', 'execution_kind': 'run_checks', 'status': 'succeeded', 'result_summary': 'all green'},
    )
    assert callback.status_code == 200

    suggestions = client.get(f'/v1/cycles/{cycle_id}/assignment-suggestions', headers={'X-User-Id': 'assignment-remote-owner'})
    assert suggestions.status_code == 200
    review = next(item for item in suggestions.json()['data']['items'] if item['agent_id'] == 'planner-coordinator')
    assert 'remote_success_count' in review
    assert 'remote_total_count' in review

    weights = client.get(f'/v1/cycles/{cycle_id}/assignment-learning-weights', headers={'X-User-Id': 'assignment-remote-owner'})
    assert weights.status_code == 200
    review_weight = next(item for item in weights.json()['data']['items'] if item['agent_id'] == 'planner-coordinator')
    assert 'remote_success_count' in review_weight
    assert 'remote_total_count' in review_weight

    get_settings.cache_clear()
