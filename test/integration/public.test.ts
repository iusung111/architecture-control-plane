import { SELF } from "cloudflare:test";
import { describe, expect, it } from "vitest";

describe("public experience", () => {
  it("serves a human-friendly landing page and docs page", async () => {
    const landing = await SELF.fetch("https://example.com/");
    expect(landing.status).toBe(200);
    expect(landing.headers.get("content-type")).toContain("text/html");
    expect(await landing.text()).toContain("Worker-first control-plane API");
    const docs = await SELF.fetch("https://example.com/docs");
    expect(docs.status).toBe(200);
    expect(await docs.text()).toContain("Authenticated workflow");
  });

  it("returns a guided 401 for protected routes without a user header", async () => {
    const response = await SELF.fetch("https://example.com/v1/approvals/pending");
    const body = await response.json();
    expect(response.status).toBe(401);
    expect(response.headers.get("link")).toContain("</docs>; rel=\"help\"");
    expect(body.error.code).toBe("missing_user");
    expect(body.error.details.required_header).toBe("X-User-Id");
  });
});
