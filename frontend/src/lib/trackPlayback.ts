import type { AircraftTrack, InterferenceZone, PlaybackAircraft, PlaybackWindow } from "../types/operationalPicture";

/**
 * What the map draws at a playback cursor. spec: map-004.
 *
 * Every function here takes the cursor and the buffered positions and nothing
 * else, so the map at a given moment cannot depend on how fast the analyst got
 * there (the named failure case at 1× and 4×) or on when a frame happened to
 * fire. None of it touches a map library: MapView draws the answers.
 *
 * **A hole is shown, never smoothed over.** Reports arrive every 10 s; two more
 * than 20 s apart are not interpolated across, and an aircraft past 20 s
 * without a report is marked *not reporting*. That is what makes a dropout
 * visible as an event (AC-08b) rather than a straight line the aircraft never
 * flew.
 *
 * **The stored gap is the authority, not the absence of rows** (amended on
 * review). The continuity rule has two mechanisms (anom-010): rows that stop,
 * leaving a hole, and rows that keep arriving with a frozen position repeating
 * the last good fix. 17 of run 480's 22 gaps are the second kind, so reports
 * strictly inside a stored gap are set aside: through the gap the aircraft
 * holds at its last good fix, marked, and its resumption is not drawn as ten
 * seconds of flight.
 *
 * **A broken trail segment is a stored gap, nothing else.** Where the detection
 * pass stored a continuity gap (api-008, api-016), the hole across it is drawn
 * as a broken segment; any other hole leaves the trail broken and undrawn. The
 * map shows what the system concluded and does not decide again.
 */

/** Twice the reporting cadence: two missed reports. */
export const INTERPOLATE_WITHIN_MS = 20_000;
/** How long an aircraft is held after its last report before it is taken to have left. */
export const HOLD_AFTER_LAST_MS = 60_000;
/** The trail's length in simulated time. */
export const TRAIL_MS = 120_000;
/** One request's span: the tracks endpoint's bound (api-008). */
export const SPAN_MS = 300_000;

/** Half-open simulated-time ranges [from, to) the buffer holds. */
export type Loaded = readonly (readonly [number, number])[];

/** A picture track, moved to the cursor, and whether it is reporting there. */
export interface PlaybackTrack extends AircraftTrack {
  stale: boolean;
}

export interface TrailSegment {
  coordinates: [number, number][];
  /** Drawn across a stored continuity gap. */
  broken: boolean;
}

export interface Trail {
  id: string;
  segments: TrailSegment[];
}

// Parsed once per aircraft object: the buffer replaces an aircraft only when a
// span adds to it, so between spans every frame reuses these.
const timesCache = new WeakMap<PlaybackAircraft, number[]>();
const timesOf = (aircraft: PlaybackAircraft): number[] => {
  let times = timesCache.get(aircraft);
  if (!times) {
    times = aircraft.positions.map((position) => Date.parse(position.time));
    timesCache.set(aircraft, times);
  }
  return times;
};

// The reports positions and trails are drawn from: every report except those
// strictly inside a stored gap, which repeat a frozen fix.
const usableCache = new WeakMap<PlaybackAircraft, { positions: PlaybackAircraft["positions"]; times: number[] }>();
const usableOf = (aircraft: PlaybackAircraft) => {
  let usable = usableCache.get(aircraft);
  if (!usable) {
    const gaps = gapsOf(aircraft);
    const times = timesOf(aircraft);
    const keep = times.map((time) => !gaps.some(([from, to]) => from < time && time < to));
    usable = { positions: aircraft.positions.filter((_, index) => keep[index]), times: times.filter((_, index) => keep[index]) };
    usableCache.set(aircraft, usable);
  }
  return usable;
};

const gapsCache = new WeakMap<PlaybackAircraft, [number, number][]>();
const gapsOf = (aircraft: PlaybackAircraft): [number, number][] => {
  let gaps = gapsCache.get(aircraft);
  if (!gaps) {
    gaps = (aircraft.gaps ?? []).map((gap) => [Date.parse(gap.startedAt), Date.parse(gap.endedAt)]);
    gapsCache.set(aircraft, gaps);
  }
  return gaps;
};

/** The index of the last report at or before `cursor`, or -1. */
const lastAtOrBefore = (times: number[], cursor: number): number => {
  let low = 0;
  let high = times.length - 1;
  let found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (times[middle] <= cursor) {
      found = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return found;
};

const covered = (loaded: Loaded, cursor: number) => loaded.some(([from, to]) => from <= cursor && cursor < to);

/** Where the loaded data stops before the cursor: the latest range end not after it. */
const loadedEdge = (loaded: Loaded, cursor: number): number =>
  loaded.reduce((edge, [, to]) => (to <= cursor && to > edge ? to : edge), Number.NEGATIVE_INFINITY);

const inGap = (aircraft: PlaybackAircraft, cursor: number) => gapsOf(aircraft).some(([from, to]) => from <= cursor && cursor <= to);

const track = (aircraft: PlaybackAircraft, lat: number, lon: number, altitudeFt: number | null, stale: boolean): PlaybackTrack => ({
  id: aircraft.id,
  name: aircraft.name,
  state: aircraft.state,
  altitudeFt,
  lat,
  lon,
  stale,
});

/** Each aircraft at the cursor: interpolated, held and marked, or not drawn. */
export function playbackTracks(aircraft: readonly PlaybackAircraft[], cursor: number, loaded: Loaded): PlaybackTrack[] {
  const tracks: PlaybackTrack[] = [];
  for (const one of aircraft) {
    const { positions, times } = usableOf(one);
    const i = lastAtOrBefore(times, cursor);
    // Not drawn before its first report in the hour.
    if (i < 0) continue;
    const here = positions[i];
    const held = (stale: boolean) => track(one, here.lat, here.lon, here.altitudeFt, stale);

    // The span the cursor needs has not loaded: hold at the last known position,
    // marked, unless the loaded data already shows the aircraft had left.
    if (!covered(loaded, cursor)) {
      if (loadedEdge(loaded, cursor) - times[i] > HOLD_AFTER_LAST_MS && !inGap(one, cursor)) continue;
      tracks.push(held(true));
      continue;
    }

    const since = cursor - times[i];
    const next = i + 1 < times.length ? i + 1 : -1;
    if (next >= 0 && times[next] - times[i] <= INTERPOLATE_WITHIN_MS) {
      const fraction = since / (times[next] - times[i]);
      const there = positions[next];
      tracks.push(track(one, here.lat + (there.lat - here.lat) * fraction, here.lon + (there.lon - here.lon) * fraction, here.altitudeFt, false));
      continue;
    }
    // After its last report: held for a minute, or for as long as a stored gap
    // says its reporting broke, then taken to have left.
    if (next < 0 && since > HOLD_AFTER_LAST_MS && !inGap(one, cursor)) continue;
    tracks.push(held(since > INTERPOLATE_WITHIN_MS));
  }
  return tracks;
}

/** The trail behind each aircraft over the last two simulated minutes. */
export function trailsAt(aircraft: readonly PlaybackAircraft[], cursor: number): Trail[] {
  const trails: Trail[] = [];
  const from = cursor - TRAIL_MS;
  for (const one of aircraft) {
    const { positions, times } = usableOf(one);
    const last = lastAtOrBefore(times, cursor);
    if (last < 0) continue;
    let first = last;
    while (first > 0 && times[first - 1] >= from) first -= 1;
    if (times[first] < from) first += 1;

    const point = (index: number): [number, number] => [positions[index].lon, positions[index].lat];
    const crossesGap = (t1: number, t2: number) => gapsOf(one).some(([start, end]) => start < t2 && end > t1);
    const segments: TrailSegment[] = [];

    // A stored gap whose far side is inside the trail: the break that brought
    // the aircraft back into it.
    if (first <= last && first > 0 && times[first] - times[first - 1] > INTERPOLATE_WITHIN_MS && crossesGap(times[first - 1], times[first])) {
      segments.push({ coordinates: [point(first - 1), point(first)], broken: true });
    }

    let solid: [number, number][] = [];
    for (let index = first; index <= last; index += 1) {
      if (index > first && times[index] - times[index - 1] > INTERPOLATE_WITHIN_MS) {
        if (solid.length > 1) segments.push({ coordinates: solid, broken: false });
        if (crossesGap(times[index - 1], times[index])) segments.push({ coordinates: [point(index - 1), point(index)], broken: true });
        solid = [];
      }
      solid.push(point(index));
    }
    // The trail ends where the aircraft is: interpolated toward the next report
    // when it is within the cadence, otherwise at its last report.
    const next = last + 1;
    if (first <= last && next < times.length && times[last] < cursor && times[next] - times[last] <= INTERPOLATE_WITHIN_MS) {
      const fraction = (cursor - times[last]) / (times[next] - times[last]);
      const [lon1, lat1] = point(last);
      const [lon2, lat2] = point(next);
      solid.push([lon1 + (lon2 - lon1) * fraction, lat1 + (lat2 - lat1) * fraction]);
    }
    if (solid.length > 1) segments.push({ coordinates: solid, broken: false });
    if (segments.length > 0) trails.push({ id: one.id, segments });
  }
  return trails;
}

/** The zones whose window holds the cursor. */
export const zonesAt = (zones: readonly InterferenceZone[], cursor: number): InterferenceZone[] =>
  zones.filter((zone) => Date.parse(zone.startedAt) <= cursor && cursor <= Date.parse(zone.endedAt));

/** The span holding the cursor and the next, aligned to the hour's start and never past its last span. */
export function spansToLoad(cursor: number, span: { start: number; end: number }): [number, number][] {
  const lastIndex = Math.max(0, Math.floor((span.end - span.start - 1) / SPAN_MS));
  const index = Math.min(Math.max(Math.floor((cursor - span.start) / SPAN_MS), 0), lastIndex);
  const spans: [number, number][] = [[span.start + index * SPAN_MS, span.start + (index + 1) * SPAN_MS]];
  if (index < lastIndex) spans.push([span.start + (index + 1) * SPAN_MS, span.start + (index + 2) * SPAN_MS]);
  return spans;
}

/** One aircraft per id across every span loaded: positions in time order, nothing twice. */
export function mergeWindow(existing: readonly PlaybackAircraft[], served: PlaybackWindow): PlaybackAircraft[] {
  const merged = new Map(existing.map((one) => [one.id, one]));
  for (const incoming of served.aircraft) {
    const known = merged.get(incoming.id);
    if (!known) {
      merged.set(incoming.id, incoming);
      continue;
    }
    const positions = new Map([...known.positions, ...incoming.positions].map((position) => [position.time, position]));
    const gaps = new Map([...(known.gaps ?? []), ...(incoming.gaps ?? [])].map((gap) => [`${gap.startedAt}|${gap.endedAt}`, gap]));
    merged.set(incoming.id, {
      ...incoming,
      positions: [...positions.values()].sort((a, b) => Date.parse(a.time) - Date.parse(b.time)),
      gaps: known.gaps === null && incoming.gaps === null ? null : [...gaps.values()],
    });
  }
  return [...merged.values()];
}
