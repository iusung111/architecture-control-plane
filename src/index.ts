import { ControlPlaneState } from "./control-plane/object";

interface Env {
  CONTROL_PLANE: DurableObjectNamespace;
}

export { ControlPlaneState };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const pathname = new URL(request.url).pathname;
    if (pathname === "/healthz" || pathname === "/readyz") {
      return Response.json({ ok: true });
    }
    const id = env.CONTROL_PLANE.idFromName("global");
    return env.CONTROL_PLANE.get(id).fetch(request);
  },
};
