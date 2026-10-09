import type { AircraftTrack, TimelineEvent } from "../../types/operationalPicture";

/**
 * How a row's fields are written, shared by the exception panel (op-004) and
 * its drill-down tables (op-005), so a field reads the same in both places.
 */

// The instant an event happened, in the simulated time it happened at (op-006):
// sliced from the ISO string, because a relative time or a local format states
// the wrong hour for a replayed 2022 hour generated in 2026.
export const simulatedInstant = (iso: string): string => `${iso.slice(0, 10)} ${iso.slice(11, 16)}`;

// Oldest first, by event time and never by array order (op-006).
export const oldestFirst = (events: readonly TimelineEvent[]): TimelineEvent[] => [...events].sort((a, b) => a.time.localeCompare(b.time));

export const altitude = (feet: number | null): string => (feet === null ? "not reported" : `${feet.toLocaleString("en-GB")} ft`);

export const position = (track: AircraftTrack): string => `${track.lat.toFixed(2)}, ${track.lon.toFixed(2)}`;

export const headCell = "px-3 py-2 font-mono text-[10px] uppercase tracking-[0.05em] text-[#8c909f]";
export const cell = "px-3 py-2";
