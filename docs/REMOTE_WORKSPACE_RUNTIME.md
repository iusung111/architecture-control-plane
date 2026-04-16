# Remote Workspace Runtime

## Executors
- `planning`: records remote intent without external compute
- `github_actions`: dispatches to `.github/workflows/remote-workspace.yml` and expects a callback
- `persistent`: keeps a long-lived workspace session in the control plane audit trail and supports hibernate/resume semantics

## Persistent runtime contract
A persistent session is represented by `remote.workspace.persistent.session.saved` audit events. The latest event for a workspace is the session of record.

### Lifecycle
`active -> hibernated -> active`

### Required fields
- `workspace_id`
- `provider`
- `status`
- `created_at`
- `updated_at`
- `last_resumed_at`
- `expires_at`
- `idle_timeout_minutes`
- `ttl_hours`

## Callback contract
The GitHub workflow posts back to:
`/v1/remote-workspaces/executions/{execution_id}/result`

Required callback fields:
- `workspace_id`
- `execution_kind`
- `status`

Recommended metadata:
- `github_run_id`
- `github_run_attempt`
- `github_repository`
- artifact URLs / log URLs

## Artifact contract
Artifacts are stored on the workspace snapshot as:
- `artifacts`: latest execution artifacts
- `artifact_history`: rolling deduplicated history

## Cancellation semantics
- planning executor: best-effort local cancellation only
- github_actions executor: requires `github_run_id` in metadata for upstream cancellation
- persistent executor: cancellation is accepted only when a live session exists for the workspace
