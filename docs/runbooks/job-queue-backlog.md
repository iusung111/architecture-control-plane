# Job queue backlog

## Signal
`ACPJobQueueBacklog`

## What it means
One or more ready-to-run jobs have been waiting in the worker queue for more than 5 minutes.

## First checks
1. Inspect `acp_job_oldest_ready_age_seconds` and `acp_job_queue_depth` by `job_type`.
2. Confirm the jobs worker is running and healthy.
3. Check for dead-lettering, DB lock conflicts, or recent deploy regressions.

## Mitigation
- Scale the jobs worker or increase worker concurrency.
- Drain or disable the failing job type if a handler is stuck.
- Requeue or cancel stale jobs only after confirming idempotency.
