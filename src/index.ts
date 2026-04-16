import { ControlPlaneState } from "./control-plane/object";
import { publicDocs, publicLanding } from "./http/public";

interface Env {
  CONTROL_PLANE: DurableObjectNamespace;
}

export { ControlPlaneState };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const pathname = url.pathname;
    if (pathname === "/") {
      return publicLanding(url.origin);
    }
    if (pathname === "/docs") {
      return publicDocs();
    }
    if (pathname === "/favicon.ico") {
      return new Response(null, { status: 204 });
    }
    if (pathname === "/healthz" || pathname === "/readyz") {
      return Response.json({ ok: true });
    }
    const id = env.CONTROL_PLANE.idFromName("global");
    return env.CONTROL_PLANE.get(id).fetch(request);
  },
};
