# Worker dead lettering

## Signal
`ACPWorkerDeadLettering`

## What it means
One or more worker jobs exhausted retries or were marked non-retryable.

## First checks
1. Inspect dead-lettered jobs in the database.
2. Group failures by `job_type` and `last_error`.
3. Check whether the latest deploy changed handler behavior.

## Mitigation
- Fix the handler or payload shape that is failing.
- Requeue safe jobs after remediation.
- Raise the issue to the owning service if an upstream dependency is broken.
