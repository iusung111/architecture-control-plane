# API latency slow burn

## Signal
`ACPApiLatencyErrorBudgetSlowBurn`

## What it means
Latency is above target for a sustained window and will consume budget over time.

## First checks
1. Compare current latency against the last known good baseline.
2. Check route-level hotspots in traces and Prometheus.
3. Review database connection pool and worker saturation.

## Mitigation
- Tune the slowest endpoints first.
- Shift work out of synchronous request paths.
- Confirm database indexes and query plans.
