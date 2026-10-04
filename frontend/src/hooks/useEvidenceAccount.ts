import { useEffect, useState } from "react";
import { fetchEvidenceAccount } from "../lib/api";
import type { EvidenceAccount } from "../types/evidence";

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
 * **`undefined` and `null` are two states.** `null` is the server saying no
 * pass examined this hour; `undefined` is this hook having no answer — before
 * the first one, and after a failed fetch. The panel says a different sentence
 * for each, because reporting a transport failure as "this hour has not been
 * examined" states a fact about the store that nothing established.
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
): EvidenceAccount | null | undefined => {
  const [account, setAccount] = useState<EvidenceAccount | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    // Cleared on the way in, so the hour being asked about never has the
    // previous hour's answer on screen while the request is in flight.
    setAccount(undefined);

    void (async () => {
      try {
        const served = await fetchEvidenceAccount(runId, baseUrl);
        if (!cancelled) setAccount(served);
      } catch {
        if (!cancelled) setAccount(undefined);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [runId, baseUrl]);

  return account;
};
