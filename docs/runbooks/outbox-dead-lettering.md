# Outbox dead lettering

## Signal
`ACPOutboxDeadLettering`

## What it means
Outbox deliveries are failing permanently or exhausting retries.

## First checks
1. Inspect dead-lettered outbox rows and group by `event_type`.
2. Check delivery endpoint health and recent HTTP responses.
3. Review webhook sink or downstream receiver logs.

## Mitigation
- Restore the failing endpoint or credentials.
- Replay safe outbox rows after recovery.
- Temporarily disable non-critical notification types if they create noise.
