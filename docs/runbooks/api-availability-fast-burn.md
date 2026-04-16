# API availability fast burn

## Signal
`ACPApiAvailabilityErrorBudgetFastBurn`

## What it means
API requests are producing 5xx responses quickly enough to burn the 99.5% availability budget at a critical rate.

## First checks
1. Open Grafana and inspect API request rate, 5xx rate, and recent deploy time.
2. Check `/readyz` and database health.
3. Search logs by `x-request-id` and `trace_id` for failing paths.

## Mitigation
- Roll back the most recent deploy if failures correlate with a release.
- Drain or disable failing integrations that are producing 500 responses.
- Scale API or database resources if saturation is visible.
