import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { LoadTracks } from "../hooks/useTrackBuffer";
import operationalPictureMock from "../mocks/operationalPictureMock";
import OperationalPictureScreen from "../screens/operationalPicture";
import type {
  InterferenceZone,
  OperationalPicture,
  PlaybackAircraft,
  PlaybackGap,
  PlaybackWindow,
  SelectableHour,
  ViewSelection,
} from "../types/operationalPicture";

// spec: map-004 — the map follows the playback cursor.
//
// Everything drawn is a function of the cursor alone: where each aircraft is,
// whether it is reporting, the trail behind it and which zones are active. So
// most of what is tested here is pure arithmetic over a fixture whose shape is
// the point — a hole the detection pass stored as a gap, a hole it did not, an
// aircraft that leaves, one that arrives late — and the rest is the buffer that
// fetches the hour in 300 s spans and the screen handing the result to the map.

// The module under test, looked up rather than imported, so its absence fails
// each test that uses it instead of the whole file at load.
const modules = import.meta.glob<typeof import("../lib/trackPlayback")>("../lib/trackPlayback.ts", { eager: true });
const lib = () => {
  const found = modules["../lib/trackPlayback.ts"];
  if (!found) throw new Error("src/lib/trackPlayback.ts does not exist");
  return found;
};

// Run 480's window, and the first position the run holds.
const START = Date.UTC(2022, 5, 27, 12, 36, 51);
const END = Date.UTC(2022, 5, 27, 12, 51, 51);
const T0 = Date.UTC(2022, 5, 27, 12, 37, 0);
const at = (seconds: number) => T0 + seconds * 1000;
const iso = (ms: number) => new Date(ms).toISOString();

const BASE_LAT = 51.0;
const BASE_LON = 7.0;

/** An aircraft reporting at the given seconds, moving 0.01° north per ten seconds. */
const aircraft = (name: string, seconds: number[], gaps: [number, number][] | null = [], state: PlaybackAircraft["state"] = "nominal"): PlaybackAircraft => ({
  id: `opensky-replay:${name}`,
  name,
  state,
  positions: seconds.map((s) => ({ time: iso(at(s)), lat: BASE_LAT + s * 0.001, lon: BASE_LON, altitudeFt: 30000 })),
  gaps: gaps === null ? null : gaps.map(([from, to]): PlaybackGap => ({ startedAt: iso(at(from)), endedAt: iso(at(to)) })),
});

const every10 = (from: number, to: number) => Array.from({ length: (to - from) / 10 + 1 }, (_, i) => from + i * 10);

// A: reports to 120 s, a stored gap, resumes at 200 s. B: leaves after 60 s.
// C: arrives at 100 s. D: stops at 60 s inside a stored gap that lasts to 200 s.
// E: a 50 s hole the pass did not store. F: reports throughout.
const A = aircraft("AC-a", [...every10(0, 120), ...every10(200, 290)], [[125, 195]], "interrupted");
const B = aircraft("AC-b", every10(0, 60));
const C = aircraft("AC-c", every10(100, 290));
const D = aircraft("AC-d", every10(0, 60), [[60, 200]], "interrupted");
const E = aircraft("AC-e", [...every10(0, 30), ...every10(80, 290)]);
const F = aircraft("AC-f", every10(0, 300));
const LOADED: [number, number][] = [[START, START + 600_000]];
// G: a FROZEN gap, the GNSS-degradation staging and 17 of run 480's 22 gaps.
// Rows keep arriving every 10 s, but from 50 s to 140 s each repeats the last
// good fix (40 s); the stored gap runs 45 s to 150 s, and at 150 s it resumes
// well to the north. Added on review (map-004 amended): the first build drew
// this as an aircraft standing still, then sliding north along a solid line.
const G: PlaybackAircraft = {
  ...aircraft("AC-g", every10(0, 290), [[45, 150]], "interrupted"),
  positions: every10(0, 290).map((s) => ({
    time: iso(at(s)),
    lat: BASE_LAT + (s > 40 && s < 150 ? 40 : s) * 0.001,
    lon: BASE_LON,
    altitudeFt: 30000,
  })),
};

const trackOf = (cursorS: number, name: string, loaded = LOADED) =>
  lib()
    .playbackTracks([A, B, C, D, E, F], at(cursorS), loaded)
    .find((track) => track.name === name);

const trailOf = (cursorS: number, name: string) =>
  lib()
    .trailsAt([A, B, C, D, E, F], at(cursorS))
    .find((trail) => trail.id === `opensky-replay:${name}`);

describe("where an aircraft is at the cursor", () => {
  it("is interpolated between two reports ten seconds apart", () => {
    // spec: map-004 (1)
    const track = trackOf(15, "AC-f");

    expect(track?.lat).toBeCloseTo(BASE_LAT + 0.015, 6);
    expect(track?.stale).toBe(false);
  });

  it("keeps the identity, name and state the playback span carries", () => {
    // spec: map-004 — so a playback marker is the picture's marker, moved.
    const track = trackOf(15, "AC-a");

    expect(track).toMatchObject({ id: "opensky-replay:AC-a", name: "AC-a", state: "interrupted", altitudeFt: 30000 });
  });

  it("holds at the last report across a hole rather than interpolating over it", () => {
    // spec: map-004 (2) — the named failure case: a hole drawn as though reporting.
    const track = trackOf(150, "AC-a");

    expect(track?.lat).toBeCloseTo(BASE_LAT + 0.12, 6);
    expect(track?.stale).toBe(true);
  });

  it("is marked not reporting only once twice the cadence has passed", () => {
    // spec: map-004 (2) — 20 s, two missed reports.
    expect(trackOf(135, "AC-a")?.stale).toBe(false);
    expect(trackOf(145, "AC-a")?.stale).toBe(true);
  });

  it("is not drawn before its first report in the hour", () => {
    // spec: map-004 (3)
    expect(trackOf(50, "AC-c")).toBeUndefined();
    expect(trackOf(100, "AC-c")).toBeDefined();
  });

  it("holds, marked, for a minute after its last report, and is then removed", () => {
    // spec: map-004 (3) — it left coverage or landed.
    expect(trackOf(70, "AC-b")?.stale).toBe(false);
    expect(trackOf(90, "AC-b")?.stale).toBe(true);
    expect(trackOf(125, "AC-b")).toBeUndefined();
  });

  it("holds through a stored gap that outlasts the minute, and goes when it ends", () => {
    // spec: map-004 (3) — its reporting broke; the analyst should see where.
    expect(trackOf(150, "AC-d")?.stale).toBe(true);
    expect(trackOf(150, "AC-d")?.lat).toBeCloseTo(BASE_LAT + 0.06, 6);
    expect(trackOf(270, "AC-d")).toBeUndefined();
  });

  it("holds at its last known position, marked, while the span it needs has not loaded", () => {
    // spec: map-004 — the named failure case: a default coordinate, or gone.
    // Loaded to just past F's report at 300 s; the cursor is beyond it.
    const loaded: [number, number][] = [[START, at(305)]];
    const track = trackOf(320, "AC-f", loaded);

    expect(track?.lat).toBeCloseTo(BASE_LAT + 0.3, 6);
    expect(track?.lon).toBe(BASE_LON);
    expect(track?.stale).toBe(true);
  });

  it("does not hold an aircraft known to have left before the loaded data ends", () => {
    // spec: map-004 (3) — B's last report is minutes before the loaded edge.
    expect(trackOf(320, "AC-b", [[START, at(305)]])).toBeUndefined();
  });

  it("depends on the cursor alone, so any speed reaches the same picture", () => {
    // spec: map-004 — the named failure case at 1× and 4×: there is no speed
    // in the function to differ by, and the same cursor gives the same answer.
    const first = lib().playbackTracks([A, B, C, D, E, F], at(137), LOADED);
    const again = lib().playbackTracks([A, B, C, D, E, F], at(137), LOADED);

    expect(again).toEqual(first);
    expect(lib().playbackTracks.length).toBe(3);
  });
});

describe("a frozen gap, where reports keep arriving", () => {
  // spec: map-004, amended on review — the stored gap is the authority, not the
  // absence of rows.
  const frozen = (cursorS: number) => lib().playbackTracks([G], at(cursorS), LOADED)[0];
  const frozenTrail = (cursorS: number) => lib().trailsAt([G], at(cursorS))[0];

  it("marks the aircraft not reporting through the gap, at its last good fix", () => {
    // spec: map-004 — the named failure case: a frozen gap drawn as reporting.
    const track = frozen(100);

    expect(track.stale).toBe(true);
    expect(track.lat).toBeCloseTo(BASE_LAT + 0.04, 6);
  });

  it("does not slide from the frozen fix to where it resumed", () => {
    // spec: map-004 — the resumption is not ten seconds of flight.
    const track = frozen(145);

    expect(track.lat).toBeCloseTo(BASE_LAT + 0.04, 6);
    expect(track.stale).toBe(true);
    expect(frozen(150).lat).toBeCloseTo(BASE_LAT + 0.15, 6);
    expect(frozen(150).stale).toBe(false);
  });

  it("joins the last good fix to the first report after the gap with one broken segment", () => {
    // spec: map-004 — the named failure case: the resumption drawn as a solid jump.
    const segments = frozenTrail(200).segments;
    const broken = segments.filter((segment) => segment.broken);

    expect(broken).toHaveLength(1);
    expect(broken[0].coordinates[0][1]).toBeCloseTo(BASE_LAT + 0.04, 6);
    expect(broken[0].coordinates[1][1]).toBeCloseTo(BASE_LAT + 0.15, 6);
    for (const segment of segments.filter((one) => !one.broken)) {
      const lats = segment.coordinates.map(([, lat]) => lat);
      // No solid line runs through the frozen stretch.
      expect(lats.some((lat) => lat > BASE_LAT + 0.041 && lat < BASE_LAT + 0.149)).toBe(false);
    }
  });
});

describe("the trail behind an aircraft", () => {
  it("covers the last two simulated minutes and no more", () => {
    // spec: map-004 (4)
    const trail = trailOf(300, "AC-f");
    const coordinates = trail?.segments.flatMap((segment) => segment.coordinates) ?? [];

    expect(lib().TRAIL_MS).toBe(120_000);
    expect(Math.min(...coordinates.map(([, lat]) => lat))).toBeCloseTo(BASE_LAT + 0.18, 6);
    expect(trail?.segments.every((segment) => !segment.broken)).toBe(true);
  });

  it("draws a hole the pass stored as a gap as one broken segment, once reporting resumes", () => {
    // spec: map-004 (4) — where continuity broke (AC-08b).
    const segments = trailOf(250, "AC-a")?.segments ?? [];
    const broken = segments.filter((segment) => segment.broken);

    expect(broken).toHaveLength(1);
    expect(broken[0].coordinates).toHaveLength(2);
    expect(broken[0].coordinates[0][1]).toBeCloseTo(BASE_LAT + 0.12, 6);
    expect(broken[0].coordinates[1][1]).toBeCloseTo(BASE_LAT + 0.2, 6);
  });

  it("leaves a hole the pass did not store broken rather than drawn", () => {
    // spec: map-004 (4) — the named failure case: a broken segment where no gap was stored.
    const segments = trailOf(100, "AC-e")?.segments ?? [];

    expect(segments.filter((segment) => segment.broken)).toEqual([]);
    expect(segments).toHaveLength(2);
  });

  it("ends at the aircraft's interpolated position", () => {
    // spec: map-004 (4)
    const segments = trailOf(15, "AC-f")?.segments ?? [];
    const last = segments[segments.length - 1].coordinates.at(-1);

    expect(last?.[1]).toBeCloseTo(BASE_LAT + 0.015, 6);
  });
});

describe("zones over the cursor", () => {
  const zone = (id: string, from: number, to: number): InterferenceZone => ({
    id,
    centre: { lat: 51, lon: 7 },
    radiusKm: 60,
    receivers: ["RF-04", "RF-05"],
    startedAt: iso(at(from)),
    endedAt: iso(at(to)),
    confidence: "Medium",
    corroboration: "not_measurable",
  });

  it("appear only while the cursor is inside their window", () => {
    // spec: map-004 (5) — the named failure case: a zone outside its window.
    const zones = [zone("early", 0, 60), zone("late", 100, 200)];

    expect(lib().zonesAt(zones, at(30)).map((z) => z.id)).toEqual(["early"]);
    expect(lib().zonesAt(zones, at(80)).map((z) => z.id)).toEqual([]);
    expect(lib().zonesAt(zones, at(150)).map((z) => z.id)).toEqual(["late"]);
  });
});

describe("the spans to load", () => {
  const SPAN = { start: START, end: END };

  it("are the span holding the cursor and the next, aligned to the hour's start", () => {
    // spec: map-004 — buffering ahead of the cursor (FR-718).
    expect(lib().spansToLoad(START, SPAN)).toEqual([
      [START, START + 300_000],
      [START + 300_000, START + 600_000],
    ]);
  });

  it("stop at the last span of the hour", () => {
    // spec: map-004
    expect(lib().spansToLoad(START + 650_000, SPAN)).toEqual([[START + 600_000, START + 900_000]]);
    expect(lib().spansToLoad(END, SPAN)).toEqual([[START + 600_000, START + 900_000]]);
  });

  it("merge into one track per aircraft, in time order, with nothing twice", () => {
    // spec: map-004 — a span boundary must not duplicate or reorder a report.
    const window = (positions: number[], gaps: [number, number][]): PlaybackWindow => ({
      runId: 480,
      recordedFrom: iso(T0),
      recordedTo: iso(at(890)),
      servedFrom: iso(START),
      servedTo: iso(START + 300_000),
      view: "all",
      examined: true,
      withheld: 0,
      aircraft: [aircraft("AC-a", positions, gaps)],
    });

    const merged = lib().mergeWindow(lib().mergeWindow([], window([0, 10, 20], [[25, 40]])), window([20, 30, 40], [[25, 40]]));

    expect(merged).toHaveLength(1);
    expect(merged[0].positions.map((p) => p.time)).toEqual([0, 10, 20, 30, 40].map((s) => iso(at(s))));
    expect(merged[0].gaps).toHaveLength(1);
  });
});

// ------------------------------------------------------------ through the screen

const HOURS: SelectableHour[] = [{ runId: 480, observedFrom: iso(START), observedTo: iso(END), examined: true }];

const ZONE: InterferenceZone = {
  id: "FUSION-SPATIAL:RF-04:2022-06-27T12:38:00+00:00",
  centre: { lat: 51.5, lon: 5.75 },
  radiusKm: 60,
  receivers: ["RF-04", "RF-05"],
  startedAt: iso(at(60)),
  endedAt: iso(at(180)),
  confidence: "Medium",
  corroboration: "not_measurable",
};

const picture = (view: ViewSelection = "anomalous"): OperationalPicture => ({
  ...operationalPictureMock,
  scenario: { id: "480", name: "Run 480", dataMode: "mixed" },
  interferenceZones: [ZONE],
  view: { ...operationalPictureMock.view, selected: view },
});

const served = (from: number, to: number): PlaybackWindow => ({
  runId: 480,
  recordedFrom: iso(T0),
  recordedTo: iso(at(890)),
  servedFrom: iso(from),
  servedTo: iso(to),
  view: "anomalous",
  examined: true,
  withheld: 0,
  aircraft: [A, F].map((one) => ({ ...one, positions: one.positions.filter((p) => Date.parse(p.time) >= from && Date.parse(p.time) < to) })),
});

const loader = () => vi.fn(async (_run: number, from: string, to: string, _view: ViewSelection) => served(Date.parse(from), Date.parse(to)));

const show = (loadTracks: LoadTracks = loader(), view: ViewSelection = "anomalous") => {
  const props = { hours: HOURS, pinnedRun: 480, operationalPicture: picture(view), selectedView: view, loadTracks };
  const rendered = render(<OperationalPictureScreen {...props} />);
  return {
    ...rendered,
    rerenderWith: (next: Partial<typeof props>) => rendered.rerender(<OperationalPictureScreen {...props} {...next} />),
  };
};

const stub = () => within(screen.getByTestId("map-view-stub"));
const line = (prefix: string) => stub().getByText(new RegExp(`^${prefix}:`)).textContent ?? "";
const openPlayback = () => fireEvent.click(screen.getByRole("button", { name: /play back this hour/i }));
const scrubTo = (ms: number) => fireEvent.change(screen.getByRole("slider", { name: /playback position/i }), { target: { value: String(ms) } });
const calls = (load: ReturnType<typeof loader>) => load.mock.calls.map(([run, from, to, view]) => [run, from, to, view]);

describe("the buffer, through the screen", () => {
  it("asks for the span holding the cursor and the next, under the view on screen", async () => {
    // spec: map-004 — the named failure case: a request ignoring the view.
    const load = loader();
    show(load);
    openPlayback();

    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    expect(calls(load)).toEqual([
      [480, iso(START), iso(START + 300_000), "anomalous"],
      [480, iso(START + 300_000), iso(START + 600_000), "anomalous"],
    ]);
  });

  it("asks for a span the cursor is scrubbed into, and never twice for one already loaded", async () => {
    // spec: map-004 — what has loaded is kept, so scrubbing back costs nothing.
    const load = loader();
    show(load);
    openPlayback();
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));

    scrubTo(START + 610_000);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(3));
    scrubTo(START + 20_000);
    await waitFor(() => expect(line("positions")).toContain("AC-f@"));

    expect(calls(load).map(([, from]) => from)).toEqual([iso(START), iso(START + 300_000), iso(START + 600_000)]);
  });

  it("asks again under a new view", async () => {
    // spec: map-004 — the view drives the request.
    const load = loader();
    const { rerenderWith } = show(load);
    openPlayback();
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));

    rerenderWith({ operationalPicture: picture("all"), selectedView: "all" });

    await waitFor(() => expect(calls(load).some(([, , , view]) => view === "all")).toBe(true));
  });

  it("asks for nothing until playback opens", async () => {
    // spec: map-004 — the picture's own rows until playback opens. Asserted in
    // both halves: closed alone passed before the buffer existed.
    const load = loader();
    show(load);
    expect(load).not.toHaveBeenCalled();

    openPlayback();
    await waitFor(() => expect(load).toHaveBeenCalled());
  });
});

describe("what the map is handed", () => {
  it("is the aircraft at the cursor, not the picture's end of the hour", async () => {
    // spec: map-004 (1)
    show();
    openPlayback();
    scrubTo(START + 20_000);

    await waitFor(() => expect(line("positions")).toContain("opensky-replay:AC-f@"));
    expect(line("aircraft")).not.toContain(operationalPictureMock.aircraftTracks[0].id);
  });

  it("is exactly what the cursor alone determines", async () => {
    // spec: map-004 — the screen draws the pure function's answer, nothing else.
    show();
    openPlayback();
    scrubTo(START + 150_000);

    const cursor = START + 150_000;
    const expected = lib()
      .playbackTracks([served(START, START + 300_000).aircraft, served(START + 300_000, START + 600_000).aircraft].reduce(
        (all, part) => lib().mergeWindow(all, { ...served(START, START + 300_000), aircraft: part }),
        [] as PlaybackAircraft[],
      ), cursor, [[START, START + 600_000]])
      .map((track) => `${track.id}@${track.lat.toFixed(4)},${track.lon.toFixed(4)}${track.stale ? " not reporting" : ""}`)
      .join("; ");
    await waitFor(() => expect(line("positions")).toBe(`positions: ${expected}`));
  });

  it("carries trails, with the stored gap as a broken segment", async () => {
    // spec: map-004 (4)
    show();
    openPlayback();
    scrubTo(START + 260_000);

    await waitFor(() => expect(line("trails")).toContain("opensky-replay:AC-a:broken"));
    expect(line("trails")).toContain("opensky-replay:AC-f:solid");
  });

  it("shows a zone only while the cursor is inside its window", async () => {
    // spec: map-004 (5)
    show();
    openPlayback();

    expect(line("zones")).toBe("zones: ");
    scrubTo(START + 120_000);
    expect(line("zones")).toBe(`zones: ${ZONE.id}`);
    scrubTo(START + 300_000);
    expect(line("zones")).toBe("zones: ");
  });

  it("is the picture's own aircraft and zones again once playback closes", async () => {
    // spec: map-004 — the named failure case: playback positions left on the map.
    show();
    openPlayback();
    scrubTo(START + 20_000);
    await waitFor(() => expect(line("positions")).toContain("AC-f@"));

    fireEvent.click(screen.getByRole("button", { name: /close playback/i }));

    expect(line("aircraft")).toBe(`aircraft: ${operationalPictureMock.aircraftTracks.map((t) => t.id).join(", ")}`);
    expect(line("zones")).toBe(`zones: ${ZONE.id}`);
    expect(line("trails")).toBe("trails: ");
  });
});
