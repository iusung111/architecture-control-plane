# Kubernetes deployment artifacts

This directory contains a production-oriented Kubernetes base for the architecture control plane.
It is intentionally split into:

- `kustomization.yaml`: long-running runtime resources
- `migrate-job.yaml`: one-shot schema migration job that should be applied and completed before rolling out the API and workers

## What is included

- API deployment and service
- Jobs worker deployment and metrics service
- Outbox worker deployment and metrics service
- API PDB and HPA
- Runtime `ConfigMap` and `Secret` placeholders
- `external-secret.example.yaml` example for external-secrets style secret managers
- Namespace and service account

## Before applying

Replace every placeholder value in `secret.yaml` and adjust the image reference in the deployment and job manifests. For production, prefer rendering `acp-secrets` from your platform secret manager and keep the mounted secret volume model intact.
The runtime base assumes external PostgreSQL and Redis instances.

At minimum you must set valid values for:

- `DATABASE_URL`
- `ABUSE_REDIS_URL`
- `AUTH_JWT_SECRET`
- `MANAGEMENT_API_KEYS_JSON`
- `MANAGEMENT_PROBE_KEY`

If you use webhook delivery in production, also replace:

- `NOTIFICATION_WEBHOOK_URL`
- `NOTIFICATION_WEBHOOK_SIGNING_SECRET`

## Recommended apply order

1. Review and edit `configmap.yaml`, `secret.yaml`, and image references.
2. Create or update the runtime base:
   - `kubectl apply -k deploy/kubernetes`
3. Run the migration job and wait for success:
   - `kubectl apply -f deploy/kubernetes/migrate-job.yaml -n architecture-control-plane`
   - `kubectl wait --for=condition=complete job/acp-migrate -n architecture-control-plane --timeout=5m`
4. Restart the API and worker deployments if the migration changed runtime behavior:
   - `kubectl rollout restart deployment/acp-api deployment/acp-worker-jobs deployment/acp-worker-outbox -n architecture-control-plane`

## Probe model

- API liveness uses `/healthz`
- API startup/readiness use `/readyz` with the management viewer probe key from `MANAGEMENT_PROBE_KEY`
- Worker readiness/liveness use the built-in metrics server endpoints on ports `9101` and `9102`

## Production notes

- The API deployment starts with two replicas so the PDB and HPA have a sane baseline.
- The migration job is intentionally **not** part of `kustomization.yaml`; this preserves the existing design goal of keeping schema migration separate from application startup.
- These manifests do not create PostgreSQL, Redis, ingress, or a Prometheus operator `ServiceMonitor`. Wire them to your platform stack explicitly.

## Secret-loading model

The manifests mount `acp-secrets` at `/var/run/acp-secrets` and pass `*_FILE` environment variables to the runtime for sensitive values. This avoids placing the highest-risk values directly into the process environment and keeps the runtime contract compatible with external secret managers. `MANAGEMENT_PROBE_KEY` remains an environment variable because the API exec probe needs direct access to it.

After rotating the mounted secret, restart the API and worker deployments so the cached runtime settings refresh.
