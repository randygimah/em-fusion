import { useEffect, useState } from "react";
import { fetchSelectableHours } from "../lib/api";
import type { SelectableHour } from "../types/operationalPicture";

/**
 * The hours the picture will serve. spec: op-009, api-013.
 *
 * **Fetched once per mount and never polled**, which is a decision rather than
 * an omission. The list changes only when a batch completes, and following the
 * newest hour does not depend on it at all — the picture endpoint with no run
 * parameter always serves the actual newest — so a stale list affects which
 * hours are *offered* and never which hour is *shown*. The cost is named in the
 * item: a batch completing while the screen is open does not appear in the list
 * until the screen is remounted.
 *
 * **A failed fetch is an empty list, not a thrown error.** The selector is
 * chrome around a screen that works without it, so an index the backend cannot
 * serve must degrade to "no hours to choose from" rather than take the picture
 * down with it.
 */
export const useSelectableHours = (baseUrl = ""): SelectableHour[] => {
  const [hours, setHours] = useState<SelectableHour[]>([]);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const served = await fetchSelectableHours(baseUrl);
        if (!cancelled) setHours(served);
      } catch {
        if (!cancelled) setHours([]);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [baseUrl]);

  return hours;
};
