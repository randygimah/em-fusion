import { useEffect, useState } from "react";
import { DEFAULT_POLL_INTERVAL_MS, fetchOperationalPicture } from "../lib/api";
import operationalPictureMock from "../mocks/operationalPictureMock";
import type { OperationalPicture } from "../types/operationalPicture";

/**
 * The picture the screen should currently show, and whether to trust it.
 * spec: api-003.
 *
 * Polling rather than pushing (FR-807): a replay-based prototype does not need
 * push infrastructure, and one sentence defends that choice in the write-up.
 *
 * **It reports degraded from the first paint.** Before any response arrives the
 * screen is showing the example payload, and example data presented as though
 * it were the system's own is the failure this project exists to argue against.
 * The indicator clears on the first successful response.
 *
 * **A failed poll keeps whatever is already on screen.** Only the indicator
 * changes. Reverting real-but-stale data to invented data because a request
 * timed out would be a downgrade in honesty as well as in usefulness; the mock
 * is the fallback only while nothing real has ever arrived.
 */
export interface PictureFeed {
  picture: OperationalPicture;
  degraded: boolean;
}

export const useOperationalPicture = (
  intervalMs: number = DEFAULT_POLL_INTERVAL_MS,
  baseUrl = "",
): PictureFeed => {
  const [feed, setFeed] = useState<PictureFeed>({
    picture: operationalPictureMock,
    degraded: true,
  });

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const picture = await fetchOperationalPicture(baseUrl);
        if (!cancelled) setFeed({ picture, degraded: false });
      } catch {
        // The error itself is not surfaced to the screen. An analyst can do
        // nothing with a status code, and the one thing they need to know —
        // that what they are looking at is not live — is the indicator.
        if (!cancelled) setFeed((current) => ({ ...current, degraded: true }));
      }
    };

    void poll();
    const timer = setInterval(() => void poll(), intervalMs);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [intervalMs, baseUrl]);

  return feed;
};
