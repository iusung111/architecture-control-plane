# Release Checklist

A release is considered production-ready only when all items below are green for the target revision.

## Quality gates
- `python scripts/release_readiness.py --allow-non-production-runtime` for repository-level gates
- `python scripts/release_readiness.py` in a production-like env before promotion
- `ruff check .`
- `pytest -q`
- No skipped release-blocker tests without explicit waiver

## Remote workspace runtime
- `/v1/remote-workspaces/executors` exposes the intended default executor
- GitHub Actions workflow dispatch contract matches `.github/workflows/remote-workspace.yml`
- Persistent session flow succeeds: create -> execute -> hibernate -> resume -> cancel
- Callback path is validated with the configured `REMOTE_WORKSPACE_CALLBACK_TOKEN`

## Deployment readiness
- Helm render completes with environment values
- Kubernetes overlay render completes for staging and production
- `scripts/k8s_runtime_smoke.sh` passes for the target revision
- Required secrets and secret-file mounts are documented and available

## Operational checks
- Audit log entries are present for snapshot save, execution request, execution result, and persistent session transitions
- Runbooks linked from `docs/runbooks/INDEX.md` cover rollback and failure handling
- Staging smoke was executed for the release candidate when external dependencies changed
