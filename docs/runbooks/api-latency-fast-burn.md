# API latency fast burn

## Signal
`ACPApiLatencyErrorBudgetFastBurn`

## What it means
Too many API requests are exceeding the configured latency SLO threshold.

## First checks
1. Inspect p95 and p99 latency in Grafana.
2. Check database wait time, lock conflicts, and worker backlog.
3. Verify any upstream dependency latency changes.

## Mitigation
- Roll back recent changes to hot request paths.
- Scale the bottleneck layer.
- Reduce expensive synchronous work in request handlers.
