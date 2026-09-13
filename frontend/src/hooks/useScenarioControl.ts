import { useCallback, useEffect, useState } from "react";
import {
  type BatchAcceptance,
  DEFAULT_POLL_INTERVAL_MS,
  fetchScenarioRuns,
  startScenarioBatch,
} from "../lib/api";
import { SCENARIO_LIBRARY } from "../lib/scenarioLibrary";
import type { ScenarioConfiguration, ScenarioControl } from "../types/scenarioControl";

/**
 * What the Scenario Control screen shows, and what starting a batch does.
 * spec: api-010.
 *
 * **There is no fixture here, and the difference from `api-003` is the point.**
 * The picture falls back to its example payload before the first response
 * arrives, because a map with nothing on it cannot be developed against and
 * the degraded badge carries the warning. A runs table is not like that: an
 * empty table is perfectly legible, and rows lifted from a real batch are
 * indistinguishable from the database's own to anyone reading them. So the
 * state before the first answer is *no rows*, not example rows.
 *
 * **A failed poll keeps what is already on screen.** Only `degraded` changes.
 * Stale truth beats fresh nothing, which is `api-003`'s posture and holds for
 * the same reason here.
 */
export interface ScenarioFeed {
  control: ScenarioControl;
  /** True until a response has arrived, and again whenever one fails. */
  degraded: boolean;
  /** What the backend accepted, once a batch has been asked for. */
  accepted: BatchAcceptance | null;
  /** The last refusal, so the screen can say why nothing started. */
  error: string | null;
  start: (configuration: ScenarioConfiguration) => void;
}

export const useScenarioControl = (
  intervalMs: number = DEFAULT_POLL_INTERVAL_MS,
  baseUrl = "",
): ScenarioFeed => {
  const [control, setControl] = useState<ScenarioControl>({
    library: SCENARIO_LIBRARY,
    runs: [],
  });
  const [degraded, setDegraded] = useState(true);
  const [accepted, setAccepted] = useState<BatchAcceptance | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const runs = await fetchScenarioRuns(baseUrl);
        if (!cancelled) {
          setControl((current) => ({ ...current, runs }));
          setDegraded(false);
        }
      } catch {
        // Deliberately not cleared. The runs already listed were true when
        // they arrived; replacing them with nothing because one request failed
        // would lose information rather than add any.
        if (!cancelled) setDegraded(true);
      }
    };

    void poll();
    const timer = setInterval(() => void poll(), intervalMs);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [intervalMs, baseUrl]);

  const start = useCallback(
    (configuration: ScenarioConfiguration) => {
      setError(null);
      void startScenarioBatch(configuration, baseUrl)
        .then((acceptance) => {
          // The seed is the point. The backend may have drawn it, and a batch
          // whose seed the analyst was never shown cannot be reproduced.
          setAccepted(acceptance);
        })
        .catch((reason: unknown) => {
          setAccepted(null);
          setError(reason instanceof Error ? reason.message : "the batch was refused");
        });
    },
    [baseUrl],
  );

  return { control, degraded, accepted, error, start };
};
