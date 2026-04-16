import { SELF } from "cloudflare:test";

const baseHeaders = {
  "Content-Type": "application/json",
  "X-Tenant-Id": "tenant-a",
  "X-User-Id": "smoke-user",
  "X-User-Role": "operator",
};

export async function call(path: string, init: RequestInit = {}) {
  const headers = new Headers(baseHeaders);
  new Headers(init.headers ?? {}).forEach((value, key) => headers.set(key, value));
  const response = await SELF.fetch(`https://example.com${path}`, { ...init, headers });
  const body = await response.json();
  return { body, response };
}
