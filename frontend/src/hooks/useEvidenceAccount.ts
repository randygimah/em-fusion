import { useEffect, useState } from "react";
import { fetchEvidenceAccount } from "../lib/api";
import type { EvidenceView } from "../types/evidence";

/**
 * The evidence behind the hour on screen. spec: op-010, api-015.
 *
 * **Fetched per hour and never polled.** The account changes only when a
 * detection pass runs, which is when a batch completes, so a five-second poll
 * would re-fetch the largest payload this screen reads in order to learn
 * nothing — `op-009`'s argument for the hour index, and the cost is the same:
 * a pass completing while the screen is open does not appear until the hour is
 * changed or the screen remounted.
 *
 * **Loading, failed and `null` are three states, named.** `null` is the server
 * saying no pass examined this hour; `"loading"` is a request in flight;
 * `"failed"` is one that did not arrive. They were two until a mutation pass
 * showed what merging the first two cost — the panel said *the evidence could
 * not be loaded* for as long as a fetch was in flight — and three mutants
 * survived on it, because with the states collapsed either of the two
 * mechanisms below alone satisfied the test.
 *
 * **A failed fetch does not keep the previous answer**, and that is a departure
 * from `api-003`'s keep-what-is-on-screen rule rather than an oversight. That
 * rule governs polling one thing: a failed poll of the picture keeps the
 * picture, because the next answer would have been about the same hour. This
 * fetch is keyed on the hour, so a failure after a success can only follow a
 * change of hour — and keeping the old answer would put one hour's evidence
 * under another hour's conclusion, which is the conflation the whole item
 * exists to remove.
 */
export const useEvidenceAccount = (
  runId: number | null = null,
  baseUrl = "",
): EvidenceView => {
  const [view, setView] = useState<EvidenceView>("loading");

  useEffect(() => {
    let cancelled = false;
    // Back to loading on the way in, so the hour being asked about never has
    // the previous hour's answer on screen while its own request is in flight.
    setView("loading");

    void (async () => {
      try {
        const served = await fetchEvidenceAccount(runId, baseUrl);
        if (!cancelled) setView(served);
      } catch {
        if (!cancelled) setView("failed");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [runId, baseUrl]);

  return view;
};
