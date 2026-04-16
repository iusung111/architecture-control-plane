from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_cycles_create_openapi_uses_typed_envelopes() -> None:
    schema = client.get('/openapi.json').json()
    post_op = schema['paths']['/v1/cycles']['post']

    success_ref = post_op['responses']['201']['content']['application/json']['schema']['$ref']
    error_ref = post_op['responses']['409']['content']['application/json']['schema']['$ref']

    assert success_ref.endswith('OkEnvelope_CreateCycleResponse_')
    assert error_ref.endswith('ErrorEnvelope')


def test_approval_confirm_openapi_uses_typed_envelopes() -> None:
    schema = client.get('/openapi.json').json()
    post_op = schema['paths']['/v1/approvals/{approval_id}/confirm']['post']

    success_ref = post_op['responses']['200']['content']['application/json']['schema']['$ref']
    error_ref = post_op['responses']['403']['content']['application/json']['schema']['$ref']

    assert success_ref.endswith('OkEnvelope_ApprovalDecisionResponse_')
    assert error_ref.endswith('ErrorEnvelope')


def test_cycles_list_openapi_uses_typed_envelopes() -> None:
    schema = client.get('/openapi.json').json()
    get_op = schema['paths']['/v1/cycles']['get']

    success_ref = get_op['responses']['200']['content']['application/json']['schema']['$ref']
    error_ref = get_op['responses']['422']['content']['application/json']['schema']['$ref']

    assert success_ref.endswith('OkEnvelope_CycleListResponse_')
    assert error_ref.endswith('ErrorEnvelope')


def test_cycle_events_openapi_exposes_text_event_stream() -> None:
    schema = client.get('/openapi.json').json()
    get_op = schema['paths']['/v1/cycles/{cycle_id}/events']['get']

    content = get_op['responses']['200']['content']
    assert 'text/event-stream' in content
    assert content['text/event-stream']['schema']['type'] == 'string'



def test_cycles_board_openapi_uses_typed_envelopes() -> None:
    schema = client.get('/openapi.json').json()
    get_op = schema['paths']['/v1/cycles/board']['get']

    success_ref = get_op['responses']['200']['content']['application/json']['schema']['$ref']
    assert success_ref.endswith('OkEnvelope_CycleBoardResponse_')


def test_cycle_timeline_openapi_uses_typed_envelopes() -> None:
    schema = client.get('/openapi.json').json()
    get_op = schema['paths']['/v1/cycles/{cycle_id}/timeline']['get']

    success_ref = get_op['responses']['200']['content']['application/json']['schema']['$ref']
    assert success_ref.endswith('OkEnvelope_CycleTimelineResponse_')


def test_cycle_board_events_openapi_exposes_text_event_stream() -> None:
    schema = client.get('/openapi.json').json()
    get_op = schema['paths']['/v1/cycles/board/events']['get']

    content = get_op['responses']['200']['content']
    assert 'text/event-stream' in content
    assert content['text/event-stream']['schema']['type'] == 'string'


def test_workspace_and_runtime_openapi_use_typed_envelopes() -> None:
    schema = client.get('/openapi.json').json()

    workspace_ref = schema['paths']['/v1/workspace/overview']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    discussions_ref = schema['paths']['/v1/workspace/discussions']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    agent_ref = schema['paths']['/v1/agents/profiles']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    runtime_ref = schema['paths']['/v1/runtime/panel']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    runtime_reg_ref = schema['paths']['/v1/runtime/registrations']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    comments_ref = schema['paths']['/v1/cycles/{cycle_id}/comments']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    card_ref = schema['paths']['/v1/cycles/{cycle_id}/card']['get']['responses']['200']['content']['application/json']['schema']['$ref']

    assert workspace_ref.endswith('OkEnvelope_WorkspaceOverviewResponse_')
    assert discussions_ref.endswith('OkEnvelope_WorkspaceDiscussionListResponse_')
    assert agent_ref.endswith('OkEnvelope_AgentProfileListResponse_')
    assert runtime_ref.endswith('OkEnvelope_RuntimePanelResponse_')
    assert runtime_reg_ref.endswith('OkEnvelope_RuntimeRegistrationListResponse_')
    assert comments_ref.endswith('OkEnvelope_CycleCommentListResponse_')
    assert card_ref.endswith('OkEnvelope_CycleCardResponse_')


def test_multica_collab_extension_openapi_uses_typed_envelopes() -> None:
    schema = client.get('/openapi.json').json()

    discussion_reply_ref = schema['paths']['/v1/workspace/discussions/{discussion_id}/replies']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    assignment_ref = schema['paths']['/v1/cycles/{cycle_id}/assignments']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    assignment_suggestion_ref = schema['paths']['/v1/cycles/{cycle_id}/assignment-suggestions']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    runtime_action_ref = schema['paths']['/v1/runtime/registrations/{runtime_id}/actions']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    runtime_action_ack_ref = schema['paths']['/v1/runtime/registrations/{runtime_id}/actions/{action_id}/acknowledge']['post']['responses']['200']['content']['application/json']['schema']['$ref']
    runtime_action_state_ref = schema['paths']['/v1/runtime/registrations/{runtime_id}/actions/{action_id}/state']['post']['responses']['200']['content']['application/json']['schema']['$ref']

    assert discussion_reply_ref.endswith('OkEnvelope_WorkspaceDiscussionReplyListResponse_')
    assert assignment_ref.endswith('OkEnvelope_CycleAssignmentListResponse_')
    assert assignment_suggestion_ref.endswith('OkEnvelope_AssignmentSuggestionListResponse_')
    assert runtime_action_ref.endswith('OkEnvelope_RuntimeActionListResponse_')
    assert runtime_action_ack_ref.endswith('OkEnvelope_RuntimeActionResponse_')
    assert runtime_action_state_ref.endswith('OkEnvelope_RuntimeActionResponse_')


def test_multica_followup_openapi_uses_typed_envelopes() -> None:
    schema = client.get('/openapi.json').json()

    discussion_resolve_ref = schema['paths']['/v1/workspace/discussions/{discussion_id}/resolve']['post']['responses']['200']['content']['application/json']['schema']['$ref']
    discussion_pin_ref = schema['paths']['/v1/workspace/discussions/{discussion_id}/pin']['post']['responses']['200']['content']['application/json']['schema']['$ref']
    assignment_feedback_ref = schema['paths']['/v1/cycles/{cycle_id}/assignment-suggestions/feedback']['post']['responses']['200']['content']['application/json']['schema']['$ref']
    runtime_receipt_list_ref = schema['paths']['/v1/runtime/registrations/{runtime_id}/actions/{action_id}/receipts']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    runtime_receipt_ref = schema['paths']['/v1/runtime/registrations/{runtime_id}/actions/{action_id}/receipts']['post']['responses']['200']['content']['application/json']['schema']['$ref']

    assert discussion_resolve_ref.endswith('OkEnvelope_WorkspaceDiscussionResponse_')
    assert discussion_pin_ref.endswith('OkEnvelope_WorkspaceDiscussionResponse_')
    assert assignment_feedback_ref.endswith('OkEnvelope_AssignmentSuggestionFeedbackResponse_')
    assert runtime_receipt_list_ref.endswith('OkEnvelope_RuntimeActionReceiptListResponse_')
    assert runtime_receipt_ref.endswith('OkEnvelope_RuntimeActionReceiptResponse_')


def test_multica_grouping_learning_and_timeline_openapi_use_typed_envelopes() -> None:
    schema = client.get('/openapi.json').json()

    discussion_groups_ref = schema['paths']['/v1/workspace/discussions/groups']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    learning_weights_ref = schema['paths']['/v1/cycles/{cycle_id}/assignment-learning-weights']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    runtime_timeline_ref = schema['paths']['/v1/runtime/registrations/{runtime_id}/actions/{action_id}/timeline']['get']['responses']['200']['content']['application/json']['schema']['$ref']

    assert discussion_groups_ref.endswith('OkEnvelope_WorkspaceDiscussionGroupListResponse_')
    assert learning_weights_ref.endswith('OkEnvelope_AssignmentLearningWeightListResponse_')
    assert runtime_timeline_ref.endswith('OkEnvelope_RuntimeActionTimelineResponse_')


def test_multica_saved_filters_and_runtime_action_events_openapi_are_exposed() -> None:
    schema = client.get('/openapi.json').json()

    saved_filters_ref = schema['paths']['/v1/workspace/discussion-filters']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    save_filter_ref = schema['paths']['/v1/workspace/discussion-filters']['post']['responses']['200']['content']['application/json']['schema']['$ref']
    runtime_events_content = schema['paths']['/v1/runtime/registrations/{runtime_id}/actions/{action_id}/events']['get']['responses']['200']['content']

    assert saved_filters_ref.endswith('OkEnvelope_WorkspaceDiscussionSavedFilterListResponse_')
    assert save_filter_ref.endswith('OkEnvelope_WorkspaceDiscussionSavedFilterResponse_')
    assert 'text/event-stream' in runtime_events_content
    assert runtime_events_content['text/event-stream']['schema']['type'] == 'string'


def test_phase1_remote_workspace_and_saved_filter_lifecycle_openapi_are_exposed() -> None:
    schema = client.get('/openapi.json').json()

    executors_ref = schema['paths']['/v1/remote-workspaces/executors']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    snapshots_ref = schema['paths']['/v1/remote-workspaces/snapshots']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    save_snapshot_ref = schema['paths']['/v1/remote-workspaces/snapshots']['post']['responses']['200']['content']['application/json']['schema']['$ref']
    execution_schema = schema['paths']['/v1/remote-workspaces/executions']['post']['responses']['200']['content']['application/json']['schema']
    resume_ref = schema['paths']['/v1/remote-workspaces/{workspace_id}/resume']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    workbench_views_ref = schema['paths']['/v1/workbench/views']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    update_filter_ref = schema['paths']['/v1/workspace/discussion-filters/{filter_id}']['patch']['responses']['200']['content']['application/json']['schema']['$ref']
    favorite_filter_ref = schema['paths']['/v1/workspace/discussion-filters/{filter_id}/favorite']['post']['responses']['200']['content']['application/json']['schema']['$ref']
    use_filter_ref = schema['paths']['/v1/workspace/discussion-filters/{filter_id}/use']['post']['responses']['200']['content']['application/json']['schema']['$ref']
    delete_filter_ref = schema['paths']['/v1/workspace/discussion-filters/{filter_id}']['delete']['responses']['200']['content']['application/json']['schema']['$ref']

    assert executors_ref.endswith('OkEnvelope_RemoteWorkspaceExecutorListResponse_')
    assert snapshots_ref.endswith('OkEnvelope_RemoteWorkspaceSnapshotListResponse_')
    assert save_snapshot_ref.endswith('OkEnvelope_RemoteWorkspaceSnapshotResponse_')
    assert execution_schema.get('anyOf') or execution_schema.get('$ref')
    assert resume_ref.endswith('OkEnvelope_RemoteWorkspaceResumeResponse_')
    assert workbench_views_ref.endswith('OkEnvelope_WorkbenchSavedViewListResponse_')
    assert update_filter_ref.endswith('OkEnvelope_WorkspaceDiscussionSavedFilterResponse_')
    assert favorite_filter_ref.endswith('OkEnvelope_WorkspaceDiscussionSavedFilterResponse_')
    assert use_filter_ref.endswith('OkEnvelope_WorkspaceDiscussionSavedFilterResponse_')
    assert delete_filter_ref.endswith('OkEnvelope_WorkspaceDiscussionSavedFilterResponse_')


def test_phase4_persistent_workspace_openapi_and_runtime_event_paths_are_exposed() -> None:
    schema = client.get('/openapi.json').json()

    persistent_list_ref = schema['paths']['/v1/remote-workspaces/persistent/sessions']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    persistent_save_ref = schema['paths']['/v1/remote-workspaces/persistent/sessions']['post']['responses']['200']['content']['application/json']['schema']['$ref']
    persistent_get_ref = schema['paths']['/v1/remote-workspaces/persistent/sessions/{workspace_id}']['get']['responses']['200']['content']['application/json']['schema']['$ref']
    persistent_hibernate_ref = schema['paths']['/v1/remote-workspaces/persistent/sessions/{workspace_id}/hibernate']['post']['responses']['200']['content']['application/json']['schema']['$ref']

    assert persistent_list_ref.endswith('OkEnvelope_PersistentWorkspaceSessionListResponse_')
    assert persistent_save_ref.endswith('OkEnvelope_PersistentWorkspaceSessionResponse_')
    assert persistent_get_ref.endswith('OkEnvelope_PersistentWorkspaceSessionResponse_')
    assert persistent_hibernate_ref.endswith('OkEnvelope_PersistentWorkspaceSessionResponse_')


def test_openapi_operation_ids_are_unique() -> None:
    schema = client.get('/openapi.json').json()
    operation_ids: list[str] = []
    for path_item in schema['paths'].values():
        for operation in path_item.values():
            if isinstance(operation, dict) and 'operationId' in operation:
                operation_ids.append(operation['operationId'])

    assert len(operation_ids) == len(set(operation_ids))


def test_cycle_route_common_star_import_exposes_internal_sse_helpers() -> None:
    from app.api.routes.cycles import cycle_streams

    assert hasattr(cycle_streams, '_format_sse_event')
    assert hasattr(cycle_streams, '_snapshot_version')
    assert hasattr(cycle_streams, '_board_snapshot_version')
