# Secret management

The runtime supports secret injection through either plain environment variables or file-backed secret references.

## Supported secret-loading patterns

1. `FOO=...`
2. `FOO_FILE=/path/to/file`
3. `SECRETS_DIR=/path/to/dir` containing files named either `FOO`, `foo_field_name`, `FOO.txt`, or `foo_field_name.txt`

`*_FILE` overrides win over `SECRETS_DIR`, and both override plain environment-variable values at runtime.

## Recommended production pattern

- Keep non-secret runtime values in `ConfigMap` / plain env vars.
- Mount secrets from your platform secret manager into files.
- Provide `*_FILE` paths or a shared `SECRETS_DIR` mount.
- Restart API and worker pods after secret rotation so the cached runtime settings refresh.

## Supported file-backed secrets

The runtime supports file-backed loading for at least these settings:

- `DATABASE_URL`
- `ABUSE_REDIS_URL`
- `LLM_USAGE_REDIS_URL`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `GROK_API_KEY`
- `CLAUDE_API_KEY`
- `CLOUDFLARE_AI_API_TOKEN`
- `AUTH_JWT_SECRET`
- `AUTH_JWKS_URL`
- `AUTH_OIDC_DISCOVERY_URL`
- `MANAGEMENT_API_KEY`
- `MANAGEMENT_API_KEYS_JSON`
- `NOTIFICATION_WEBHOOK_URL`
- `NOTIFICATION_WEBHOOK_SIGNING_SECRET`
- `BACKUP_ENCRYPTION_PASSPHRASE`
- `BACKUP_DRILL_TARGET_DATABASE_URL`
- `BACKUP_DRILL_TARGET_DATABASE_URLS_JSON`

## Kubernetes guidance

The Kubernetes base under `deploy/kubernetes/` now mounts `acp-secrets` as a read-only volume and passes `*_FILE` paths for the sensitive runtime values. `MANAGEMENT_PROBE_KEY` remains an environment variable because the exec probe reads it directly.

For managed secret stores, render the same `acp-secrets` object through your platform toolchain or use the included `external-secret.example.yaml` as a starting point.
