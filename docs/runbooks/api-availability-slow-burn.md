# API availability slow burn

## Signal
`ACPApiAvailabilityErrorBudgetSlowBurn`

## What it means
API 5xx responses are elevated for a sustained period but not yet at crisis pace.

## First checks
1. Review Grafana service overview for 1h error rate.
2. Compare error classes by route group.
3. Check dead-letter alerts and lock-conflict alerts for correlated failures.

## Mitigation
- Reduce noisy traffic sources.
- Patch or disable the highest-error code path.
- Schedule controlled remediation before the fast-burn threshold is hit.
