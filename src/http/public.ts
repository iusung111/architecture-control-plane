function shell(title: string, body: string): string {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${title}</title>
  <style>
    :root { color-scheme: light; --ink:#102033; --muted:#5e6d80; --card:#ffffffd9; --line:#d9e2ec; --sky:#dff3ff; --mint:#e8fff3; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:"Avenir Next","Segoe UI",sans-serif; color:var(--ink); background:linear-gradient(145deg,var(--sky),#fff7ea 60%,var(--mint)); }
    main { max-width:980px; margin:0 auto; padding:40px 20px 64px; }
    h1,h2 { margin:0 0 12px; letter-spacing:-0.03em; }
    p,li { line-height:1.6; color:var(--muted); }
    .hero,.grid article,pre { border:1px solid var(--line); border-radius:24px; background:var(--card); backdrop-filter:blur(10px); }
    .hero { padding:28px; box-shadow:0 20px 50px #93b9d633; }
    .actions,.grid { display:grid; gap:16px; }
    .actions { grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); margin-top:20px; }
    .grid { grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); margin-top:20px; }
    a { color:#0059b8; text-decoration:none; font-weight:600; }
    article { padding:18px; }
    code,pre { font-family:"IBM Plex Mono","SFMono-Regular",monospace; }
    pre { padding:16px; overflow:auto; white-space:pre-wrap; }
    .pill { display:inline-block; margin-bottom:12px; padding:7px 12px; border-radius:999px; background:#0d20331a; color:#0f2740; font-size:13px; }
  </style>
</head>
<body><main>${body}</main></body></html>`;
}

export function publicLanding(origin: string): Response {
  const body = `
  <section class="hero">
    <span class="pill">Architecture Control Plane</span>
    <h1>Worker-first control-plane API</h1>
    <p>The public root is intentionally human-friendly. Protected API calls live under <code>/v1</code> and require <code>X-User-Id</code>.</p>
    <div class="actions">
      <article><h2>Start here</h2><p><a href="/docs">Open workflow docs</a></p></article>
      <article><h2>Liveness</h2><p><a href="/healthz">${origin}/healthz</a></p></article>
      <article><h2>Readiness</h2><p><a href="/readyz">${origin}/readyz</a></p></article>
    </div>
  </section>
  <section class="grid">
    <article><h2>Workflow</h2><p>Create a cycle, review approvals when needed, then fetch the final result. The live docs page shows the exact header and payload shape.</p></article>
    <article><h2>Auth rule</h2><p>Only authenticated API routes require user headers. Landing and docs stay public so first contact never dead-ends into a raw error.</p></article>
  </section>`;
  return new Response(shell("Architecture Control Plane", body), {
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

export function publicDocs(): Response {
  const body = `
  <section class="hero">
    <span class="pill">Usage guide</span>
    <h1>Authenticated workflow</h1>
    <p>Use these headers on <code>/v1/*</code>: <code>X-User-Id</code>, optional <code>X-User-Role</code>, optional <code>X-Tenant-Id</code>, and <code>Idempotency-Key</code> on write operations.</p>
    <pre>curl -X POST "$BASE_URL/v1/cycles" \\
  -H "Content-Type: application/json" \\
  -H "X-User-Id: demo-user" \\
  -H "X-User-Role: operator" \\
  -H "X-Tenant-Id: tenant-a" \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -d '{"project_id":"acp","user_input":"ship safely"}'</pre>
  </section>
  <section class="grid">
    <article><h2>Public endpoints</h2><p><code>GET /</code>, <code>GET /docs</code>, <code>GET /healthz</code>, <code>GET /readyz</code></p></article>
    <article><h2>Protected endpoints</h2><p><code>/v1/cycles</code>, <code>/v1/approvals/pending</code>, and approval confirmation routes require the user header.</p></article>
    <article><h2>Next step</h2><p>Create a cycle first. If the cycle enters <code>human_approval_pending</code>, list pending approvals and confirm the matching approval.</p></article>
  </section>`;
  return new Response(shell("Architecture Control Plane Docs", body), {
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}
