# Test Strategy

## Intent

The test plan mirrors the Cloudflare deployment path. Local checks should prove
the same things that the deployed Worker proves, using the same API contract.

## Layers

1. Unit tests
   State guards and pure helpers.
2. Integration tests
   Full Worker requests inside the Vitest Workers pool with isolated Durable
   Object storage per test.
3. Live smoke
   A Node script that calls the deployed Worker URL and exercises the main
   contract paths.

## Commands

```bash
npm test
npm run dev
npm run smoke:local
npm run smoke -- https://architecture-control-plane.<subdomain>.workers.dev
```

## What the live smoke covers

- public landing page
- health and readiness
- create cycle
- idempotent replay
- approval-required flow
- verification-failed flow followed by retry
- verification-failed flow followed by replan
- finalized result retrieval

## Why one smoke script

The same smoke script runs against local dev and deployed Workers. That keeps
the verification surface small and avoids drift between CI-only checks and real
runtime behavior.
