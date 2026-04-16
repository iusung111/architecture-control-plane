interface DurableObject {
  fetch(request: Request): Promise<Response> | Response;
}

interface DurableObjectId {}

interface DurableObjectState {
  storage: {
    get<T>(key: string): Promise<T | undefined>;
    put<T>(key: string, value: T): Promise<void>;
  };
}

interface DurableObjectNamespace {
  idFromName(name: string): DurableObjectId;
  get(id: DurableObjectId): {
    fetch(request: Request): Promise<Response>;
  };
}

declare module "cloudflare:test" {
  export const SELF: {
    fetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response>;
  };
}
