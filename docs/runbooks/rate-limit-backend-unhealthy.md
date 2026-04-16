# Rate limit backend unhealthy

## Symptoms
- `acp_rate_limit_backend_healthy{backend="redis"}` is 0.
- API may be failing closed or bypassing limits depending on failure mode.

## Likely causes
- Redis unavailable or timing out.
- Network policy or credential drift.

## Actions
1. Check Redis health and connectivity from the API container.
2. Inspect `acp_rate_limit_backend_errors_total` by error type.
3. Confirm `ABUSE_REDIS_URL` and backend failure mode settings.
4. If fail-open is unacceptable, switch to `closed` after Redis is healthy again.
