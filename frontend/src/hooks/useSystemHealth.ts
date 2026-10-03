import { useEffect, useState } from "react";
import { SYSTEM_HEALTH_INTERVAL_MS, fetchSystemHealth } from "../lib/api";

/**
 * Whether the backend is reachable, and what it says about itself.
 * spec: nav-002, ops-005.
 *
 * **Two rows, because there are two links and they fail separately.**
 * `connectivity` is whether the request reached the backend at all — the
 * browser-to-service link. `service` is what the backend said about reaching
 * its own database — the service-to-database link. The distinction is
 * `ops-005`'s, one layer further out: a database at the wrong revision is a
 * misconfiguration and an unreachable one is an outage, and collapsing them
 * makes a deployment that has not finished look like one that has broken.
 *
 * **A 503 is not a failed request.** It means the request arrived and the
 * backend could not vouch for itself, so connectivity is `up` and the refusal
 * belongs on the service row. Read the other way, a misconfigured deployment
 * reports as a lost connection — which is the conflation that cost a day of the
 * main screen returning 500 while the container called itself healthy.
 *
 * **A body missing the keys this reads is treated as unreachable.** The health
 * route answers with a plain body rather than a declared model, so there is
 * nothing for the contract parser to compare against and no parity test can
 * exist. That leaves one silent failure: rename a key and this would read
 * `undefined`, map it to a verdict, and report a plausible steady state
 * forever. Degrading to a visible failure is the cheaper half of the guard; the
 * other half pins the key set in the backend suite.
 */
export type Connectivity = "unknown" | "up" | "down";
export type Service = "unknown" | "healthy" | "refusing" | "cannot-tell";

export interface SystemHealth {
  connectivity: Connectivity;
  service: Service;
}

const UNREACHABLE: SystemHealth = { connectivity: "down", service: "unknown" };

export const useSystemHealth = (
  intervalMs: number = SYSTEM_HEALTH_INTERVAL_MS,
  baseUrl = "",
): SystemHealth => {
  const [health, setHealth] = useState<SystemHealth>({
    connectivity: "unknown",
    service: "unknown",
  });

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const answer = await fetchSystemHealth(baseUrl);
        if (cancelled) return;
        if (answer === null) {
          // The body did not carry the keys this reads. See the note above.
          setHealth(UNREACHABLE);
          return;
        }
        setHealth({
          connectivity: "up",
          service:
            answer.schema === "drifted"
              ? "refusing"
              : answer.schema === "unknown"
                ? "cannot-tell"
                : "healthy",
        });
      } catch {
        if (!cancelled) setHealth(UNREACHABLE);
      }
    };

    void poll();
    const timer = setInterval(() => void poll(), intervalMs);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [intervalMs, baseUrl]);

  return health;
};
