import { useEffect, useRef, useState } from "react";
import type { PlaybackSpan } from "../lib/playback";
import { type Loaded, mergeWindow, SPAN_MS, spansToLoad } from "../lib/trackPlayback";
import type { PlaybackAircraft, PlaybackWindow, ViewSelection } from "../types/operationalPicture";

export type LoadTracks = (runId: number, from: string, to: string, view: ViewSelection) => Promise<PlaybackWindow>;

const iso = (ms: number) => new Date(ms).toISOString();

/**
 * The hour's aircraft positions, fetched in 300 s spans ahead of the cursor.
 * spec: map-004, api-008.
 *
 * The span holding the cursor and the next are asked for when playback is
 * open, under the view on screen, so the request rate follows the span and
 * never the frame rate (FR-718). What has loaded is kept, so scrubbing back
 * costs nothing; a span is asked for once, and again only if its request
 * failed. A different hour or view starts the buffer again, because positions
 * from one view are not the positions of another.
 *
 * The loader is handed down from the seam (App), so this hook reaches the
 * network only through `src/lib/api.ts`.
 */
export const useTrackBuffer = ({
  load,
  runId,
  view,
  span,
  cursor,
  open,
}: {
  load?: LoadTracks;
  runId: number | null;
  view: ViewSelection;
  span: PlaybackSpan | null;
  cursor: number;
  open: boolean;
}): { aircraft: PlaybackAircraft[]; loaded: Loaded } => {
  const key = runId === null || span === null ? null : `${runId}|${view}|${span.start}|${span.end}`;
  const [buffer, setBuffer] = useState<{ key: string | null; aircraft: PlaybackAircraft[]; loaded: [number, number][] }>({
    key: null,
    aircraft: [],
    loaded: [],
  });
  const requested = useRef<{ key: string | null; spans: Set<number> }>({ key: null, spans: new Set() });
  const loadRef = useRef(load);
  loadRef.current = load;
  // Which span the cursor is in: the fetch runs when that changes, not every frame.
  const index = span === null ? -1 : Math.floor((cursor - span.start) / SPAN_MS);

  // biome-ignore lint/correctness/useExhaustiveDependencies: the span index stands for the cursor.
  useEffect(() => {
    const loader = loadRef.current;
    if (!open || !loader || key === null || runId === null || span === null) return;
    if (requested.current.key !== key) {
      requested.current = { key, spans: new Set() };
      setBuffer({ key, aircraft: [], loaded: [] });
    }
    const asked = requested.current;
    for (const [from, to] of spansToLoad(cursor, span)) {
      if (asked.spans.has(from)) continue;
      asked.spans.add(from);
      loader(runId, iso(from), iso(to), view).then(
        (served) => {
          if (requested.current.key !== key) return;
          setBuffer((current) =>
            current.key === key ? { key, aircraft: mergeWindow(current.aircraft, served), loaded: [...current.loaded, [from, to]] } : current,
          );
        },
        () => {
          // Asked for again the next time the cursor needs it.
          asked.spans.delete(from);
        },
      );
    }
  }, [open, key, index]);

  return buffer.key === key ? { aircraft: buffer.aircraft, loaded: buffer.loaded } : { aircraft: [], loaded: [] };
};
