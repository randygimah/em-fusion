import { useCallback, useEffect, useRef, useState } from "react";
import { advance, frameInterval, type PlaybackSpeed, type PlaybackSpan } from "../lib/playback";

/**
 * The playback transport's state for one hour. spec: op-008.
 *
 * Closed by default. Opening puts the cursor at the window's start, paused.
 * Playing moves it one animation frame at a time by the capped frame interval
 * times the speed (lib/playback.ts), and reaching the end pauses it there.
 *
 * **Keyed on the hour.** When a different hour comes on screen the transport
 * closes: a cursor carried into another hour would be a moment of one hour
 * drawn over another. The screen pins the hour when playback opens, so this
 * fires only when the analyst chooses another hour.
 *
 * Frames are timed with `performance.now()`, not `Date`, and nothing here reads
 * the wall clock as a moment: the cursor starts from the hour's span and only
 * ever moves by intervals (anom-009).
 */
export const usePlayback = (hour: string | null, span: PlaybackSpan | null) => {
  const [open, setOpen] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const [cursor, setCursor] = useState(0);
  const cursorRef = useRef(cursor);
  cursorRef.current = cursor;

  // Another hour on screen closes the transport.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the hour is the trigger.
  useEffect(() => {
    setOpen(false);
    setPlaying(false);
  }, [hour]);

  useEffect(() => {
    if (!open || !playing || span === null) return;
    let frame = 0;
    let last = performance.now();
    const step = () => {
      const now = performance.now();
      const next = advance(cursorRef.current, frameInterval(last, now), speed, span);
      last = now;
      cursorRef.current = next;
      setCursor(next);
      if (next >= span.end) {
        setPlaying(false);
        return;
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [open, playing, speed, span]);

  const start = useCallback(() => {
    if (span === null) return;
    setCursor(span.start);
    setPlaying(false);
    setOpen(true);
  }, [span]);

  const close = useCallback(() => {
    setPlaying(false);
    setOpen(false);
  }, []);

  const toggle = useCallback(() => {
    if (span === null) return;
    if (playing) {
      setPlaying(false);
      return;
    }
    // Play from the end starts the hour again.
    if (cursorRef.current >= span.end) setCursor(span.start);
    setPlaying(true);
  }, [playing, span]);

  const seek = useCallback(
    (to: number) => {
      if (span === null) return;
      setCursor(Math.min(Math.max(to, span.start), span.end));
    },
    [span],
  );

  return { open: open && span !== null, playing, speed, cursor, start, close, toggle, seek, setSpeed };
};
