# Architecture Control Plane

This repository is a Cloudflare Worker-native control-plane scaffold.

The previous Python, Compose, and Kubernetes stack was removed on purpose. The
current codebase targets one deployment model only:

- Cloudflare Worker for HTTP ingress
- one Durable Object for durable state
- deterministic contract tests in the Workers runtime
- one live smoke script reused before and after deploy

Public entry routes now follow a user-first flow:

- `GET /` returns an HTML landing page instead of an auth error
- `GET /docs` explains the authenticated workflow with a copy-ready `curl`
- only `GET /healthz`, `GET /readyz`, and `/v1/*` keep their runtime-specific roles

## Why it was rebuilt

The goal is to keep deployment honest and maintainable. A Worker-first runtime
should not pretend to be a container stack. This version keeps the cycle and
approval contract, but strips the system down to something that can be deployed
and verified directly on Cloudflare.

## Quick start

```bash
npm install
npm test
npm run dev
npm run smoke:local
```

## Deploy

```bash
npm run check
npm run deploy
npm run smoke -- https://architecture-control-plane.<subdomain>.workers.dev
```

`wrangler whoami` must already work locally. GitHub Actions deployment uses
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.

Live deployment verified on 2026-04-16:

- `https://architecture-control-plane.iusung111.workers.dev`

## API surface

- `GET /`
- `GET /docs`
- `GET /healthz`
- `GET /readyz`
- `POST /v1/cycles`
- `GET /v1/cycles/:cycleId`
- `GET /v1/cycles/:cycleId/result`
- `POST /v1/cycles/:cycleId/retry`
- `POST /v1/cycles/:cycleId/replan`
- `GET /v1/approvals/pending`
- `POST /v1/approvals/:approvalId/confirm`

## Deterministic scaffold flags

`POST /v1/cycles` accepts `metadata` flags to drive predictable runtime paths:

- `requires_approval`
- `required_role`
- `force_verification_failure`
- `final_output`

These flags are intentional. They make the scaffold deployable and testable
without inventing fake background workers or hidden side effects.

## Layout

- [src/index.ts](/mnt/d/uieseong_workspace/workspace/architecture-control-plane/src/index.ts)
- [src/control-plane](/mnt/d/uieseong_workspace/workspace/architecture-control-plane/src/control-plane)
- [src/domain](/mnt/d/uieseong_workspace/workspace/architecture-control-plane/src/domain)
- [src/http](/mnt/d/uieseong_workspace/workspace/architecture-control-plane/src/http)
- [test](/mnt/d/uieseong_workspace/workspace/architecture-control-plane/test)
- [scripts/live-smoke.mjs](/mnt/d/uieseong_workspace/workspace/architecture-control-plane/scripts/live-smoke.mjs)
- [docs/ARCHITECTURE.md](/mnt/d/uieseong_workspace/workspace/architecture-control-plane/docs/ARCHITECTURE.md)
- [docs/TEST_STRATEGY.md](/mnt/d/uieseong_workspace/workspace/architecture-control-plane/docs/TEST_STRATEGY.md)
- [docs/CLOUDFLARE_DEPLOYMENT.md](/mnt/d/uieseong_workspace/workspace/architecture-control-plane/docs/CLOUDFLARE_DEPLOYMENT.md)

## File-size rule

The repository intentionally stays small. New source and doc files should remain
below 300 lines, and most should stay around 80 to 120 lines.
