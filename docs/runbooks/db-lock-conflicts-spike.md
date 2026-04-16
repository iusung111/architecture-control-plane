# Database lock conflicts spike

## Signal
`ACPDbLockConflictsSpike`

## What it means
Competing transactions are colliding often enough to affect request success.

## First checks
1. Inspect lock-conflict rate and related traces.
2. Check PostgreSQL lock waits and blocked sessions.
3. Identify whether the pressure is on cycle, approval, job, or outbox rows.

## Mitigation
- Reduce concurrent mutation traffic on the hot resource.
- Shorten transaction scope.
- Verify that SKIP LOCKED and row-level locks are being used as expected.
