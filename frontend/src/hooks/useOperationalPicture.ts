import { useEffect, useState } from "react";
import { DEFAULT_POLL_INTERVAL_MS, fetchOperationalPicture } from "../lib/api";
import operationalPictureMock from "../mocks/operationalPictureMock";
import { DEFAULT_VIEW } from "../lib/viewVocabulary";
import type { OperationalPicture, ViewSelection } from "../types/operationalPicture";

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

/**
 * **The poll follows the selection.** spec: op-009.
 *
 * `runId` of null means follow the newest, which is what the endpoint serves
 * with no parameter. Two things about pinning an hour were decided here rather
 * than defaulted: the poll keeps running, because a historical hour's detection
 * state can still change -- re-examining a run restamps it, and 380 runs'
 * findings changed in six minutes on 3 October -- and it asks for the *pinned*
 * hour, because a poll still requesting the newest would revert the screen
 * under the analyst on the next tick, which is worse than having no control.
 *
 * **The poll follows the view too** (op-007), for the same reason, and a new
 * view is fetched at once rather than on the next tick. Until it arrives the
 * feed still holds the previous view's payload, which names the view it was
 * served under — so the screen can say it is switching rather than mislabel it.
 */
export const useOperationalPicture = (
  runId: number | null = null,
  view: ViewSelection = DEFAULT_VIEW,
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
        const picture = await fetchOperationalPicture(baseUrl, runId, view);
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
  }, [runId, view, intervalMs, baseUrl]);

  return feed;
};
