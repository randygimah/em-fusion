import type { ReceiverOutOfNominal, ReceiverStates, RFSensor } from "../types/operationalPicture";

/**
 * Each receiver's state at a playback cursor. spec: map-007.
 *
 * The picture gives a receiver one state for the whole hour: the worst any
 * stored finding put it in. During playback that state is wrong for most of
 * the hour, so each receiver is drawn in the state of the interval holding the
 * cursor (api-018) and nominal outside every interval. Nothing is computed
 * here that the served intervals do not say: the intervals are the detection
 * pass's conclusions, joined by the server on the picture's own ladder.
 *
 * **A receiver is never shown as nominal for want of an answer.** Until the
 * intervals arrive, or if they never do, or for a receiver they do not name, it
 * keeps the picture's whole-hour state and is marked `provisional`, which the
 * map says in its name. On an hour nobody examined it is not examined, whatever
 * the cursor.
 */

export interface PlaybackSensor extends RFSensor {
  /** Showing the picture's whole-hour state, not the state at the cursor. */
  provisional: boolean;
}

/** Worse is higher; where two closed intervals touch, the worse holds the shared instant. */
const RANK: Record<ReceiverOutOfNominal, number> = { fault: 2, deviating: 1 };

const NOT_EXAMINED = "unknown";
const NOMINAL = "nominal";

export function receiversAt(sensors: readonly RFSensor[], states: ReceiverStates | null, cursor: number): PlaybackSensor[] {
  const timelines = new Map((states?.receivers ?? []).map((timeline) => [timeline.id, timeline]));
  return sensors.map((sensor) => {
    const timeline = states === null ? undefined : timelines.get(sensor.id);
    if (timeline === undefined) return { ...sensor, provisional: true };
    if (timeline.intervals === null) return { ...sensor, health: NOT_EXAMINED, provisional: false };
    let health = NOMINAL;
    let worst = 0;
    for (const interval of timeline.intervals) {
      if (Date.parse(interval.startedAt) <= cursor && cursor <= Date.parse(interval.endedAt) && RANK[interval.state] > worst) {
        worst = RANK[interval.state];
        health = interval.state;
      }
    }
    return { ...sensor, health, provisional: false };
  });
}
