// Where the Vite dev server forwards /api (ops-006).
//
// On the host the backend container answers on localhost:8000, which is the
// default so `pnpm dev` is unchanged. Inside the `frontend-dev` container
// localhost is the container itself, so Compose sets the backend's service name
// instead. Read from the environment rather than hard-coded, because a dev
// server forwarding to the wrong place fails every call while the operational
// picture's first-paint mock makes the screen look healthy.
//
// Not `VITE_`-prefixed: Vite publishes those into the browser bundle, and this
// is server configuration.

export const API_PROXY_ENV = "API_PROXY_TARGET";
export const DEFAULT_API_PROXY_TARGET = "http://localhost:8000";

export function apiProxyTarget(env: Record<string, string | undefined>): string {
  const value = env[API_PROXY_ENV];
  if (value === undefined || value === "") {
    return DEFAULT_API_PROXY_TARGET;
  }
  let protocol: string;
  try {
    protocol = new URL(value).protocol;
  } catch {
    protocol = "";
  }
  if (protocol !== "http:" && protocol !== "https:") {
    throw new Error(`${API_PROXY_ENV}=${JSON.stringify(value)} is not an http(s) URL; the dev server cannot forward /api to it.`);
  }
  return value;
}
