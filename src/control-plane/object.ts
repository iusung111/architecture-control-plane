import { routeControlPlane } from "./routes";
import { ControlPlaneStore } from "./store";

export class ControlPlaneState implements DurableObject {
  private readonly store: ControlPlaneStore;

  constructor(ctx: DurableObjectState, env: unknown) {
    this.store = new ControlPlaneStore(ctx);
    void env;
  }

  async fetch(request: Request): Promise<Response> {
    return routeControlPlane(this.store, request);
  }
}
