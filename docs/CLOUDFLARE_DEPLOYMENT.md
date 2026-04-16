# Cloudflare Deployment

## Local deploy flow

```bash
npm install
npm run check
npm run deploy
```

Wrangler must already be authenticated:

```bash
npx wrangler whoami
```

## Live verification

After deploy, run the smoke script against the returned `workers.dev` URL:

```bash
npm run smoke -- https://architecture-control-plane.<subdomain>.workers.dev
```

The smoke script is not optional. Deployment is only considered complete after
that script passes against the live Worker.

Good first-load UX is part of the deploy gate. The base URL must render the
landing page, and protected API routes must return a guided 401 with a help link
to `/docs` instead of an uncontextualized auth failure.

## Verified deployment

Verified on 2026-04-16:

- Worker URL: `https://architecture-control-plane.iusung111.workers.dev`
- Command: `npm run smoke -- https://architecture-control-plane.iusung111.workers.dev`

## GitHub Actions

The repository includes:

- `ci.yml` for typecheck and Worker runtime tests
- `deploy.yml` for manual or branch-based deployment

GitHub deployment needs these secrets:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

## Durable Object migration policy

This repository starts with a single migration tag, `v1`, that creates the
`ControlPlaneState` class as a SQLite-backed Durable Object. Future storage
changes should add a new migration tag instead of mutating history.
