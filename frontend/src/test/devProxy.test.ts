// spec: ops-006 — where the dev server forwards /api.
//
// On the host, the backend container answers on localhost:8000. Inside a
// container, localhost is the container itself, so a dev server forwarding
// there reaches nothing — and the operational picture falls back to its mock on
// first paint, so the screen would look healthy while showing invented data.
// The address therefore comes from the environment, through one helper.
import { describe, expect, it } from "vitest";
import { API_PROXY_ENV, apiProxyTarget, DEFAULT_API_PROXY_TARGET } from "../../devProxy";
import viteConfigSource from "../../vite.config.ts?raw";

describe("the dev server's /api proxy target", () => {
  it("defaults to the backend as the host sees it, so `pnpm dev` is unchanged", () => {
    // spec: ops-006
    expect(apiProxyTarget({})).toBe("http://localhost:8000");
    expect(DEFAULT_API_PROXY_TARGET).toBe("http://localhost:8000");
  });

  it("takes the address the container sets", () => {
    // spec: ops-006
    expect(apiProxyTarget({ [API_PROXY_ENV]: "http://backend:8000" })).toBe("http://backend:8000");
  });

  it("treats an empty value as unset", () => {
    // spec: ops-006 — `FOO=` in a compose file or shell is an empty string, not an address.
    expect(apiProxyTarget({ [API_PROXY_ENV]: "" })).toBe("http://localhost:8000");
  });

  it.each(["backend:8000", "ws://backend:8000", "not a url"])("refuses %s, naming the variable", (value) => {
    // spec: ops-006 — a malformed address would fail every request at runtime, far from its cause.
    expect(() => apiProxyTarget({ [API_PROXY_ENV]: value })).toThrow(API_PROXY_ENV);
  });

  it("is not a variable Vite publishes into the browser bundle", () => {
    // spec: ops-006 — `VITE_*` variables reach client code; the proxy address is server configuration.
    expect(API_PROXY_ENV).toBe("API_PROXY_TARGET");
    expect(API_PROXY_ENV.startsWith("VITE_")).toBe(false);
  });

  it("is what vite.config.ts forwards /api to", () => {
    // spec: ops-006 — a helper nothing calls would leave the hard-coded address in place.
    expect(viteConfigSource).toContain("apiProxyTarget(process.env)");
    expect(viteConfigSource).not.toContain('target: "http://localhost:8000"');
  });
});
