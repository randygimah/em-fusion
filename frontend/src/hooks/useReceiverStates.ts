import { useEffect, useRef, useState } from "react";
import type { ReceiverStates } from "../types/operationalPicture";

export type LoadReceiverStates = (runId: number) => Promise<ReceiverStates>;

/**
 * The hour's receiver states for playback. spec: map-007, api-018.
 *
 * Asked for once, when playback opens on an hour, and kept: the answer is a
 * few hundred bytes and a replayed hour's conclusions do not change. An answer
 * naming another run is refused, as the drill-down refuses one (op-005), so a
 * late answer for the previous hour cannot colour this one. A failed request is
 * asked again the next time playback opens; until then, and until any answer
 * arrives, this is null and the receivers keep the picture's whole-hour state.
 *
 * The loader is handed down from the seam (App), so this hook reaches the
 * network only through `src/lib/api.ts`.
 */
export const useReceiverStates = ({
  load,
  runId,
  open,
}: {
  load?: LoadReceiverStates;
  runId: number | null;
  open: boolean;
}): ReceiverStates | null => {
  const [held, setHeld] = useState<ReceiverStates | null>(null);
  const asked = useRef<number | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const loader = loadRef.current;
    if (!open || !loader || runId === null || asked.current === runId) return;
    asked.current = runId;
    loader(runId).then(
      (states) => {
        if (asked.current === runId && states.runId === runId) setHeld(states);
      },
      () => {
        if (asked.current === runId) asked.current = null;
      },
    );
  }, [open, runId]);

  return held !== null && held.runId === runId ? held : null;
};
