import type { Ref } from "react";
import { clockLabel, elapsedLabel, PLAYBACK_SPEEDS, type PlaybackSpeed, type PlaybackSpan, STEP_MS } from "../../lib/playback";
import { cn } from "../../lib/utils";

/**
 * The playback transport under the map. spec: op-008.
 *
 * A renderer over `usePlayback`'s state: play or pause, a scrub slider over the
 * hour's window, the cursor as the replayed hour's UTC clock and as elapsed
 * against the hour's length, the speeds, and a way back to the end of the hour.
 *
 * The slider is a native range input, so the arrow keys, Home and End work as
 * a screen reader expects: one step is the ten-second reporting cadence, and
 * `aria-valuetext` announces the time rather than an epoch number.
 */
export const EmPlaybackBar = ({
  barRef,
  span,
  cursor,
  playing,
  speed,
  onToggle,
  onSeek,
  onSpeed,
  onClose,
}: {
  // The screen measures the bar, to add its height to the page (op-008).
  barRef?: Ref<HTMLElement>;
  span: PlaybackSpan;
  cursor: number;
  playing: boolean;
  speed: PlaybackSpeed;
  onToggle: () => void;
  onSeek: (to: number) => void;
  onSpeed: (speed: PlaybackSpeed) => void;
  onClose: () => void;
}) => (
  <section
    aria-label="Playback"
    ref={barRef}
    className="flex shrink-0 flex-wrap items-center gap-3 border border-[#424754] bg-[#1d2027] px-3 py-2 font-mono text-xs"
  >
    <button
      aria-label={playing ? "Pause" : "Play"}
      className="w-8 border border-[#424754] py-1 text-[#adc6ff] hover:bg-[#272a31]"
      onClick={onToggle}
      type="button"
    >
      <span aria-hidden="true">{playing ? "❚❚" : "▶"}</span>
    </button>
    <input
      aria-label="Playback position"
      aria-valuetext={clockLabel(cursor)}
      className="min-w-40 flex-1 accent-[#adc6ff]"
      max={span.end}
      min={span.start}
      onChange={(event) => onSeek(Number(event.target.value))}
      step={STEP_MS}
      type="range"
      value={cursor}
    />
    <span className="text-[#e1e2ec]">{clockLabel(cursor)}</span>
    <span className="text-[#8c909f]">{elapsedLabel(cursor, span)}</span>
    <div
      aria-label="Speed"
      className="flex border border-[#424754]"
      role="radiogroup"
    >
      {PLAYBACK_SPEEDS.map((option) => (
        // biome-ignore lint/a11y/useSemanticElements: a segmented control; an <input type="radio"> carries no text of its own
        <button
          aria-checked={option === speed}
          className={cn("px-2 py-1", option === speed ? "bg-[#adc6ff] text-[#0b0e15]" : "text-[#c2c6d6] hover:text-[#e1e2ec]")}
          key={option}
          onClick={() => onSpeed(option)}
          role="radio"
          type="button"
        >
          {option}×
        </button>
      ))}
    </div>
    <button
      className="uppercase tracking-[0.05em] text-[#8c909f] hover:text-[#e1e2ec]"
      onClick={onClose}
      type="button"
    >
      Close playback
    </button>
  </section>
);
