# Architecture

## Intent

This scaffold is designed for a Worker runtime first, not as a container app
ported into Workers. The implementation keeps the control-plane contract focused
on cycles, approvals, retry, and replan, then expresses those flows with the
smallest durable runtime that Cloudflare executes directly.

## Runtime shape

- one public Worker receives HTTP traffic
- one global Durable Object stores all control-plane state
- Worker health checks stay outside the Durable Object
- API routes proxy to the Durable Object for every stateful operation

The single Durable Object is deliberate. It keeps state changes serialized,
removes external database setup, and makes local integration tests match the
deployed runtime closely.

## Data model

The Durable Object stores one JSON document with:

- `cycles`
- `approvals`
- `requests` for idempotent replay

This is enough for the current contract and keeps the storage surface simple.
If the project later needs higher write volume, the next step would be sharding
by tenant or project, not reintroducing a hidden container backend.

## Contract intent

`POST /v1/cycles` is intentionally deterministic. `metadata` can request an
approval gate or a verification failure so the same API can drive:

- unit tests
- integration tests in the Workers runtime
- deployed smoke tests

That choice is documented because it is architectural, not accidental.

## Maintainability rules

- keep handlers thin and explicit
- keep domain helpers separate from transport helpers
- keep persistence behind one store adapter
- prefer one reason per file
- prefer deterministic tests over hidden timers or background work

## File-size budget

- hard ceiling: 300 lines per file
- normal target: 80 to 120 lines
- split logic before adding a second concern to a file

## Non-goals

This scaffold does not currently emulate:

- multi-process workers
- background queues
- external SQL databases
- Kubernetes, Compose, or container orchestration

Those were removed so the deployment target and the runtime model stay aligned.
