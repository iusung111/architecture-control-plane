# Backup drill running too long

## Signal
`ACPBackupDrillRunningTooLong`

## What it means
A backup restore drill job has remained claimed or running for more than 30 minutes.

## First checks
1. Inspect the drill job status endpoint for `stage`, `last_error`, and `cancellation_requested`.
2. Check worker logs for `backup_restore_drill` subprocess timeouts or storage errors.
3. Verify source/target database reachability and object storage health.

## Mitigation
- Cancel the drill if it is stuck and start a fresh run with a new `Idempotency-Key` only after root cause is clear.
- Increase backup command timeout only if the environment is consistently slower than expected.
- Fix storage or database reachability before replaying the drill.
