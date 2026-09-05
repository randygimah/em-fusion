import type { OperationalPicture } from "../types/operationalPicture";

/**
 * The only module in the frontend that reaches the network. spec: api-003.
 *
 * Everything else — screens, hooks, App — takes data as a value. That is what
 * makes changing the endpoint a one-file change, and it is asserted rather than
 * intended: a test scans the source for a second caller.
 *
 * The path is relative, so the same build works in development behind Vite's
 * proxy and in the container behind nginx. The backend owns the `/api/v1`
 * prefix, so nothing here rewrites it.
 */
export const OPERATIONAL_PICTURE_PATH = "/api/v1/operational-picture";

/**
 * Five seconds, chosen by hand rather than tuned (NFR-503).
 *
 * The endpoint answers in about 0.4 s warm. An interval shorter than the
 * response time produces overlapping requests rather than fresher data, which
 * is the specific way a poll gets this wrong; five seconds leaves an order of
 * magnitude of headroom and is comfortably faster than a person reads a screen.
 */
export const DEFAULT_POLL_INTERVAL_MS = 5000;

/** Fetch the current picture, or throw. */
export const fetchOperationalPicture = async (
  baseUrl = "",
  signal?: AbortSignal,
): Promise<OperationalPicture> => {
  const response = await fetch(`${baseUrl}${OPERATIONAL_PICTURE_PATH}`, { signal });
  if (!response.ok) {
    // Thrown rather than returned as a value: every caller has to handle a
    // network failure anyway, so a second "but did it work" shape would be a
    // second thing to forget to check.
    throw new Error(`${OPERATIONAL_PICTURE_PATH} responded ${response.status}`);
  }
  return (await response.json()) as OperationalPicture;
};
