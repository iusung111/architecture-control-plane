# Rate limit fail-open bypass

## Symptoms
- `acp_rate_limit_backend_decisions_total{decision="allow_on_backend_failure"}` is increasing.
- Requests continue even though Redis-backed limiting is unhealthy.

## Likely causes
- Redis backend failure while `ABUSE_RATE_LIMIT_BACKEND_FAILURE_MODE=open`.

## Actions
1. Restore Redis connectivity and confirm `acp_rate_limit_backend_healthy` returns to 1.
2. Review recent `acp_rate_limit_backend_errors_total` increases.
3. If abuse risk is high, temporarily change the policy to `closed`.
