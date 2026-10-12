import type { HypothesisBundle } from "../types/hypotheses";
import type { InterferenceZone } from "../types/operationalPicture";

/**
 * Where the Hypotheses screen's map opens, and which zone is the conclusion's.
 * spec: hyp-001 (6), qa.md 164.
 *
 * Pure. The map is zoomed to the affected area rather than the corpus: the disc
 * at the radius recorded with the claim and the receivers the evidence names.
 * Nothing here invents a radius; with none, the box is the named points.
 */

type Point = { lat: number; lon: number };
export type Bounds = [[number, number], [number, number]];

const KM_PER_DEGREE = 111.32;
// Margin round every point, so a receiver is never drawn on the frame's edge
// and a lone point is never a box of no size.
const MARGIN_KM = 10;

const box = ({ lat, lon }: Point, km: number): Point[] => {
  const dLat = km / KM_PER_DEGREE;
  const dLon = km / (KM_PER_DEGREE * Math.cos((lat * Math.PI) / 180));
  return [
    { lat: lat - dLat, lon: lon - dLon },
    { lat: lat + dLat, lon: lon + dLon },
  ];
};

/** [[west, south], [east, north]] holding the disc and every named point. */
export const affectedAreaBounds = (centre: Point, radiusKm: number | null, points: Point[]): Bounds => {
  const corners = [...box(centre, Math.max(radiusKm ?? 0, MARGIN_KM)), ...points.flatMap((point) => box(point, MARGIN_KM))];
  const lats = corners.map((corner) => corner.lat);
  const lons = corners.map((corner) => corner.lon);
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ];
};

const sameInstant = (a: string, b: string): boolean => Date.parse(a) === Date.parse(b);

/**
 * The hour's zone for this conclusion: the same receivers, as a set, over the
 * same window. A zone id is a timeline event id, not a bundle id, so this is
 * the join. Two matches are as unplaceable as none: never one chosen.
 */
export const matchZone = (
  conclusion: Pick<HypothesisBundle, "receivers" | "windowStart" | "windowEnd">,
  zones: InterferenceZone[],
): InterferenceZone | null => {
  const named = new Set(conclusion.receivers);
  const matches = zones.filter(
    (zone) =>
      new Set(zone.receivers).size === named.size &&
      zone.receivers.every((receiver) => named.has(receiver)) &&
      sameInstant(zone.startedAt, conclusion.windowStart) &&
      sameInstant(zone.endedAt, conclusion.windowEnd),
  );
  return matches.length === 1 ? matches[0] : null;
};
