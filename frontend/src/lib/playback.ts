/**
 * The playback cursor's arithmetic and words. spec: op-008.
 *
 * The cursor is a moment in the replayed hour, held as epoch milliseconds in
 * simulated time — never the wall clock (anom-009). Everything that moves it is
 * here as a pure function, so "the same amount of play reaches the same moment
 * at any speed" and "it never runs past the hour" are properties of arithmetic,
 * tested without a single frame.
 */

/** The speeds offered. At 60× a fifteen-minute hour plays in fifteen seconds. */
export const PLAYBACK_SPEEDS = [1, 4, 16, 60] as const;
export type PlaybackSpeed = (typeof PLAYBACK_SPEEDS)[number];

/** One scrub step: the reporting cadence, so a step moves one report. */
export const STEP_MS = 10_000;

/**
 * The longest interval one frame may carry. A browser runs no animation frames
 * in a hidden tab, so the first frame back measures the whole absence; capped,
 * the cursor resumes where it stopped instead of leaping by the time away.
 */
export const MAX_FRAME_MS = 250;

export interface PlaybackWindow {
  start: number;
  end: number;
}

/** The wall-clock interval between two frames, capped. */
export const frameInterval = (previous: number, now: number): number => Math.min(Math.max(now - previous, 0), MAX_FRAME_MS);

/** Where the cursor is after `elapsedMs` of play at `speed`, held inside the window. */
export const advance = (cursor: number, elapsedMs: number, speed: number, span: PlaybackWindow): number =>
  Math.min(Math.max(cursor + elapsedMs * speed, span.start), span.end);

/** The window an hour from the index plays over, or null when it records none. */
export const windowOf = (from: string | null, to: string | null): PlaybackWindow | null => {
  if (from === null || to === null) return null;
  const start = Date.parse(from);
  const end = Date.parse(to);
  return Number.isFinite(start) && Number.isFinite(end) && end > start ? { start, end } : null;
};

/** The cursor as the replayed hour's clock reads it, in UTC whatever the viewer's zone. */
export const clockLabel = (cursor: number): string => `${new Date(cursor).toISOString().slice(11, 19)} UTC`;

const minutes = (ms: number): string => {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
};

/** How far into the hour the cursor is, against the hour's length. */
export const elapsedLabel = (cursor: number, span: PlaybackWindow): string =>
  `${minutes(cursor - span.start)} of ${minutes(span.end - span.start)}`;

export const NO_PLAYBACK_WINDOW = "This hour has no recorded window to play back.";
