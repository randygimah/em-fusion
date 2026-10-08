import { namedFlavor } from "@protomaps/basemaps";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AircraftTrack, RFSensor } from "../types/operationalPicture";

// spec: map-001, map-002, map-003, map-005 — the MapView adapter, what it shows
// when it cannot be a map, how its markers say what state each entity is in,
// and the pop-up and labels that say more.
//
// Every other test file gets a stand-in for MapView from setup.ts; this one
// tests the real adapter, with the map library replaced. MapLibre needs WebGL,
// which jsdom does not have, so what is proved here is everything around the
// drawing: which configuration means which state, that the default style
// reaches nothing but this server, and that the library is not even loaded
// when there is nothing to draw. The markers are HTML (map-001 (12)), so the
// fake attaches them to the map's container and they are queried like any
// other element.
vi.unmock("../components/map/MapView");

const lib = vi.hoisted(() => ({
  loaded: vi.fn(),
  failToStart: false,
  setWorkerUrl: vi.fn(),
  zoom: 6,
  project: null as null | ((lngLat: [number, number]) => { x: number; y: number }),
  instances: [] as FakeMapInstance[],
  markers: [] as FakeMarkerInstance[],
}));

interface FakeMapInstance {
  options: { container: HTMLElement; style: unknown; maxBounds?: unknown };
  setStyle: ReturnType<typeof vi.fn>;
  emit: (event: string, payload?: unknown) => void;
}

interface FakeMarkerInstance {
  element: HTMLElement;
  lngLat: [number, number] | { lng: number; lat: number } | undefined;
  removed: boolean;
}

vi.mock("maplibre-gl", () => {
  lib.loaded();
  class FakeMap {
    options: { container: HTMLElement; style: unknown };
    handlers: Record<string, ((payload?: unknown) => void)[]> = {};
    setStyle = vi.fn();
    addSource = vi.fn();
    addLayer = vi.fn();
    addControl = vi.fn();
    getSource = vi.fn(() => undefined);
    getLayer = vi.fn(() => undefined);
    remove = vi.fn();
    constructor(options: { container: HTMLElement; style: unknown }) {
      if (lib.failToStart) throw new Error("Failed to initialize WebGL");
      this.options = options;
      lib.instances.push(this as unknown as FakeMapInstance);
    }
    getZoom() {
      return lib.zoom;
    }
    project(lngLat: [number, number] | { lng: number; lat: number }) {
      const at: [number, number] = Array.isArray(lngLat) ? lngLat : [lngLat.lng, lngLat.lat];
      // Far apart by default, so no two labels collide unless a test says so.
      return lib.project ? lib.project(at) : { x: at[0] * 10000, y: -at[1] * 10000 };
    }
    on(event: string, a: unknown, b?: unknown) {
      const callback = (typeof a === "function" ? a : b) as (payload?: unknown) => void;
      this.handlers[event] = [...(this.handlers[event] ?? []), callback];
      return this;
    }
    off() {
      return this;
    }
    emit(event: string, payload?: unknown) {
      for (const callback of this.handlers[event] ?? []) callback(payload);
    }
  }
  class FakeMarker {
    element: HTMLElement;
    lngLat: FakeMarkerInstance["lngLat"];
    removed = false;
    constructor(options: { element: HTMLElement }) {
      this.element = options.element;
      lib.markers.push(this);
    }
    setLngLat(lngLat: FakeMarkerInstance["lngLat"]) {
      this.lngLat = lngLat;
      return this;
    }
    addTo(map: FakeMap) {
      map.options.container.appendChild(this.element);
      return this;
    }
    remove() {
      this.removed = true;
      this.element.remove();
      return this;
    }
    getElement() {
      return this.element;
    }
  }
  const module = {
    Map: FakeMap,
    Marker: FakeMarker,
    addProtocol: vi.fn(),
    setWorkerUrl: lib.setWorkerUrl,
    removeProtocol: vi.fn(),
    AttributionControl: class {},
    NavigationControl: class {},
  };
  return { ...module, default: module };
});

vi.mock("pmtiles", () => ({
  Protocol: class {
    tile = vi.fn();
  },
  PMTiles: class {
    getHeader() {
      return Promise.resolve({});
    }
  },
}));

const { MapView, buildDefaultStyle, buildSatelliteStyle, markerLook, placeLabels, readBasemapConfig } = await import("../components/map/MapView");

const ARCHIVE = "/basemap/em-fusion.pmtiles";
const OVERVIEW = "/basemap/europe-overview.pmtiles";
const SATELLITE = { tiles: "https://tiles.example.test/{z}/{x}/{y}.jpg", attribution: "Imagery © Example" };

const sensors: RFSensor[] = Array.from({ length: 7 }, (_, i) => ({
  id: `RF-0${i + 1}`,
  stationName: `Station ${i + 1}`,
  signalId: "GNSS-L1",
  health: i === 0 ? "fault" : "nominal",
  lat: 50 + i * 0.1,
  lon: 6 + i * 0.1,
}));

const tracks: AircraftTrack[] = [
  { id: "opensky-replay:AC-1", name: "AC-1", altitudeFt: 30000, lat: 51.25, lon: 7.5, state: "interrupted" },
  { id: "opensky-replay:AC-2", name: "AC-2", altitudeFt: null, lat: 52.5, lon: 4.75, state: "nominal" },
];

const readable = () => Promise.resolve();
const unreadable = () => Promise.reject(new Error("404"));

type Props = Parameters<typeof MapView>[0];

const renderMap = (overrides: Partial<Props> = {}) => {
  const props: Props = {
    config: { defaultArchive: ARCHIVE, satellite: null },
    readArchive: readable,
    sensors,
    tracks,
    ...overrides,
  };
  const view = render(<MapView {...props} />);
  return {
    ...view,
    rerenderWith: (next: Partial<Props>) =>
      view.rerender(
        <MapView
          {...props}
          {...next}
        />,
      ),
  };
};

const mapReady = () => waitFor(() => expect(lib.instances).toHaveLength(1));
const markersReady = () => waitFor(() => expect(screen.getAllByRole("button", { name: /^(Aircraft|Receiver) / })).toHaveLength(9));
const at = (marker: FakeMarkerInstance) => (Array.isArray(marker.lngLat) ? marker.lngLat : [marker.lngLat?.lng, marker.lngLat?.lat]);
const liveMarkers = () => lib.markers.filter((marker) => !marker.removed);
const shown = (text: string) => {
  const element = screen.queryByText(text);
  return element !== null && element.closest("[hidden]") === null;
};

beforeEach(() => {
  lib.loaded.mockClear();
  lib.failToStart = false;
  lib.zoom = 6;
  lib.project = null;
  lib.instances.length = 0;
  lib.markers.length = 0;
});

describe("reading the basemap configuration", () => {
  it("is unconfigured when nothing is set, or set empty", () => {
    // spec: map-002
    expect(readBasemapConfig({})).toEqual({ defaultArchive: null, satellite: null });
    expect(readBasemapConfig({ VITE_BASEMAP_ARCHIVE: "", VITE_SATELLITE_TILES: "", VITE_SATELLITE_ATTRIBUTION: "" })).toEqual({
      defaultArchive: null,
      satellite: null,
    });
  });

  it("takes a same-origin archive path", () => {
    // spec: map-001 (4)
    expect(readBasemapConfig({ VITE_BASEMAP_ARCHIVE: ARCHIVE }).defaultArchive).toBe(ARCHIVE);
  });

  it.each([
    "https://cdn.example.test/em.pmtiles",
    "//cdn.example.test/em.pmtiles",
    "basemap/em.pmtiles",
  ])("refuses a default archive that is not a path on this server: %s", (value) => {
    // spec: map-001 — the default basemap issues no request to another host.
    expect(() => readBasemapConfig({ VITE_BASEMAP_ARCHIVE: value })).toThrow(/VITE_BASEMAP_ARCHIVE/);
  });

  it("offers satellite only when both its variables are set", () => {
    // spec: map-001 (6), map-002 — the named failure case: one of two set.
    expect(readBasemapConfig({ VITE_SATELLITE_TILES: SATELLITE.tiles }).satellite).toBeNull();
    expect(readBasemapConfig({ VITE_SATELLITE_ATTRIBUTION: SATELLITE.attribution }).satellite).toBeNull();
    expect(readBasemapConfig({ VITE_SATELLITE_TILES: SATELLITE.tiles, VITE_SATELLITE_ATTRIBUTION: SATELLITE.attribution }).satellite).toEqual(
      SATELLITE,
    );
  });
});

describe("the default style", () => {
  it("reaches nothing but this server — sources, glyphs and sprite", () => {
    // spec: map-001 (3), (4), (11) — a default style points glyphs and sprites
    // at a CDN, and the map would still render perfectly.
    const style = buildDefaultStyle(ARCHIVE);
    const text = JSON.stringify(style);

    expect(text).not.toMatch(/https?:\/\//);
    expect(text).not.toMatch(/"\/\//);
    const urls = [style.glyphs, style.sprite, ...Object.values(style.sources).map((source) => (source as { url?: string }).url)];
    for (const url of urls) {
      expect(typeof url).toBe("string");
      expect(String(url).replace(/^pmtiles:\/\//, "")).toMatch(/^\/[^/]/);
    }
    expect(text).toContain(`pmtiles://${ARCHIVE}`);
  });

  it("credits OpenStreetMap and Protomaps", () => {
    // spec: map-001 (7) — ODbL requires it.
    const attribution = Object.values(buildDefaultStyle(ARCHIVE).sources)
      .map((source) => (source as { attribution?: string }).attribution ?? "")
      .join(" ");

    expect(attribution).toMatch(/OpenStreetMap/);
    expect(attribution).toMatch(/Protomaps/);
  });

  it("is the light flavour, with the light sprite", () => {
    // spec: map-001 (10)
    const style = buildDefaultStyle(ARCHIVE);
    const background = style.layers.find((layer) => layer.type === "background") as { paint?: Record<string, unknown> };

    expect(style.sprite).toBe("/basemap/sprites/v4/light");
    expect(background.paint?.["background-color"]).toBe(namedFlavor("light").background);
  });

  it("draws the Europe overview everywhere and the detailed box over it", () => {
    // spec: map-001 (11) — the named failure case: a grey area inside the overview.
    const style = buildDefaultStyle(ARCHIVE);
    const sources = style.sources as Record<string, { url?: string; minzoom?: number; attribution?: string }>;
    const layers = style.layers as { id: string; type: string; source?: string; maxzoom?: number }[];
    const overviewLayers = layers.filter((layer) => layer.source === "overview");
    const detailLayers = layers.filter((layer) => layer.source === "protomaps");

    expect(sources.overview.url).toBe(`pmtiles://${OVERVIEW}`);
    expect(sources.overview.attribution).toMatch(/OpenStreetMap/);
    expect(sources.protomaps.minzoom).toBe(7);
    expect(overviewLayers.length).toBeGreaterThan(0);
    expect(detailLayers.length).toBeGreaterThan(0);
    const lastOverview = Math.max(...overviewLayers.map((layer) => layers.indexOf(layer)));
    expect(detailLayers.every((layer) => layers.indexOf(layer) > lastOverview)).toBe(true);
  });

  it("has one background layer, and the overview's labels only below zoom 7", () => {
    // spec: map-001 (11) — a second background would paint over the overview
    // wherever the box has no tiles; overview labels above 7 would collide with the box's.
    const layers = buildDefaultStyle(ARCHIVE).layers as { type: string; source?: string; maxzoom?: number }[];

    expect(layers.filter((layer) => layer.type === "background")).toHaveLength(1);
    const overviewLabels = layers.filter((layer) => layer.source === "overview" && layer.type === "symbol");
    expect(overviewLabels.length).toBeGreaterThan(0);
    expect(overviewLabels.every((layer) => layer.maxzoom !== undefined && layer.maxzoom <= 7)).toBe(true);
  });

  it("builds satellite from the configured tiles and credits them", () => {
    // spec: map-001 (6), (7) — nothing in the repo names a provider.
    const text = JSON.stringify(buildSatelliteStyle(SATELLITE));

    expect(text).toContain(SATELLITE.tiles);
    expect(text).toContain(SATELLITE.attribution);
  });
});

describe("the three states that are not a map", () => {
  it("says no basemap is configured, counts the entities, and never loads the map library", async () => {
    // spec: map-002 — no request, no throw, and nothing loaded.
    const readArchive = vi.fn(readable);
    renderMap({ config: { defaultArchive: null, satellite: null }, readArchive });

    expect(screen.getByText(/no basemap is configured/i)).toBeInTheDocument();
    expect(screen.getByText(/7 receivers · 2 aircraft/)).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(readArchive).not.toHaveBeenCalled();
    expect(lib.loaded).not.toHaveBeenCalled();
  });

  it("says a configured archive could not be read, and names the fix", async () => {
    // spec: map-001 (5), map-002 — never "not configured", never a blank pane, never satellite.
    renderMap({ config: { defaultArchive: ARCHIVE, satellite: SATELLITE }, readArchive: unreadable });

    expect(await screen.findByText(/could not be read/i)).toBeInTheDocument();
    expect(screen.getByText(/make basemap/)).toBeInTheDocument();
    expect(screen.queryByText(/not configured/i)).not.toBeInTheDocument();
    expect(screen.getByText(/7 receivers · 2 aircraft/)).toBeInTheDocument();
    expect(lib.instances).toHaveLength(0);
  });

  it("reads both archives before making a map, and a missing overview is the same state", async () => {
    // spec: map-001 (11), map-002
    const readArchive = vi.fn((archive: string) => (archive === OVERVIEW ? unreadable() : readable()));
    renderMap({ readArchive });

    expect(await screen.findByText(/could not be read/i)).toBeInTheDocument();
    expect(readArchive).toHaveBeenCalledWith(ARCHIVE);
    expect(readArchive).toHaveBeenCalledWith(OVERVIEW);
    expect(lib.instances).toHaveLength(0);
  });

  it("says the browser could not start the map when the library fails", async () => {
    // spec: map-002 — e.g. no WebGL.
    lib.failToStart = true;
    renderMap();

    expect(await screen.findByText(/could not start the map/i)).toBeInTheDocument();
    expect(screen.getByText(/7 receivers · 2 aircraft/)).toBeInTheDocument();
  });
});

describe("the map", () => {
  it("starts on the self-hosted default", async () => {
    // spec: map-001
    renderMap();

    await mapReady();
    expect(JSON.stringify(lib.instances[0].options.style)).toContain(`pmtiles://${ARCHIVE}`);
    expect(screen.getByRole("region", { name: /map/i })).toBeInTheDocument();
  });

  it("keeps the camera inside the Europe overview", async () => {
    // spec: map-001 (11)
    renderMap();
    await mapReady();

    expect(lib.instances[0].options.maxBounds).toEqual([
      [-11, 35],
      [30, 61],
    ]);
  });

  it("points the library at its worker before making the map", async () => {
    // spec: map-001 — added after implementation: in the dev server the derived
    // worker address 404s and the map starts, attributes itself and draws nothing.
    renderMap();
    await mapReady();

    expect(lib.setWorkerUrl).toHaveBeenCalledWith(expect.stringMatching(/maplibre-gl-worker\.mjs/));
  });

  it("hands the library an absolute sprite address on this origin", async () => {
    // spec: map-001 (3), (4), (10) — added after implementation: MapLibre refuses a
    // relative sprite, and the icons went missing without an error on screen.
    renderMap();
    await mapReady();

    const { sprite } = lib.instances[0].options.style as { sprite: string };
    expect(sprite).toBe(`${window.location.origin}/basemap/sprites/v4/light`);
  });

  it("does not offer satellite when it is not configured", async () => {
    // spec: map-002 — the named failure case.
    renderMap();
    await mapReady();

    expect(screen.queryByRole("button", { name: /satellite/i })).not.toBeInTheDocument();
  });

  it("switches to satellite only when the analyst asks", async () => {
    // spec: map-001 (6) — an explicit action, never a fallback.
    renderMap({ config: { defaultArchive: ARCHIVE, satellite: SATELLITE } });
    await mapReady();
    // Tightened after the mutation pass: configured satellite must not be where the map starts.
    expect(JSON.stringify(lib.instances[0].options.style)).not.toContain(SATELLITE.tiles);
    expect(lib.instances[0].setStyle).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /satellite/i }));

    expect(JSON.stringify(lib.instances[0].setStyle.mock.calls[0][0])).toContain(SATELLITE.tiles);
  });

  it("says satellite tiles are failing, and does not substitute the default", async () => {
    // spec: map-001 (6) — a silent substitution makes the two indistinguishable.
    renderMap({ config: { defaultArchive: ARCHIVE, satellite: SATELLITE } });
    await mapReady();
    fireEvent.click(screen.getByRole("button", { name: /satellite/i }));

    act(() => lib.instances[0].emit("error", { sourceId: "satellite", error: new Error("403") }));

    expect(await screen.findByText(/satellite tiles are failing/i)).toBeInTheDocument();
    expect(lib.instances[0].setStyle).toHaveBeenCalledTimes(1);
  });
});

describe("the markers", () => {
  it("puts one marker on each receiver and aircraft, longitude first", async () => {
    // spec: map-001 (12) — swapped, Cologne lands in Somalia.
    renderMap();
    await markersReady();

    expect(liveMarkers()).toHaveLength(9);
    const aircraft = liveMarkers().find((marker) => marker.element.contains(screen.getByRole("button", { name: /^Aircraft AC-1/ })));
    expect(aircraft && at(aircraft)).toEqual([7.5, 51.25]);
  });

  it("removes a marker when its row leaves the payload", async () => {
    // spec: map-001 (12) — the named failure case: a marker left for a row no longer carried.
    const { rerenderWith } = renderMap();
    await markersReady();

    rerenderWith({ tracks: [tracks[1]] });

    await waitFor(() => expect(screen.queryByRole("button", { name: /^Aircraft AC-1/ })).not.toBeInTheDocument());
    expect(liveMarkers()).toHaveLength(8);
  });

  it("moves a marker when its row's position changes", async () => {
    // spec: map-001 (12) — a poll moves an aircraft; the marker follows.
    const { rerenderWith } = renderMap();
    await markersReady();

    rerenderWith({ tracks: [{ ...tracks[0], lat: 51.5, lon: 7.75 }, tracks[1]] });

    await waitFor(() => {
      const marker = liveMarkers().find((m) => m.element.contains(screen.getByRole("button", { name: /^Aircraft AC-1/ })));
      expect(marker && at(marker)).toEqual([7.75, 51.5]);
    });
  });

  it("keeps the markers across a basemap switch", async () => {
    // spec: map-001 (12)
    renderMap({ config: { defaultArchive: ARCHIVE, satellite: SATELLITE } });
    await markersReady();

    fireEvent.click(screen.getByRole("button", { name: /satellite/i }));

    expect(liveMarkers()).toHaveLength(9);
    expect(screen.getByRole("button", { name: /^Aircraft AC-1/ })).toBeInTheDocument();
  });
});

describe("what state each marker says it is in", () => {
  it("names each entity and its state", async () => {
    // spec: map-003 (2) — asserted through the accessible name, not CSS.
    renderMap();
    await markersReady();

    expect(screen.getByRole("button", { name: "Receiver RF-01 (Station 1), fault" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Receiver RF-02 (Station 2), nominal" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aircraft AC-1, interrupted" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aircraft AC-2, nominal" })).toBeInTheDocument();
  });

  it("names an unexamined entity as not examined, never nominal", async () => {
    // spec: map-003 (1), (2)
    renderMap({
      sensors: [{ ...sensors[1], health: "unknown" }],
      tracks: [{ ...tracks[1], state: "unknown" }],
    });

    expect(await screen.findByRole("button", { name: "Receiver RF-02 (Station 2), not examined" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aircraft AC-2, not examined" })).toBeInTheDocument();
  });

  it("gives anomalous, nominal and unexamined entities three different looks", () => {
    // spec: map-003 (1) — the named failure case: anomalous drawn like nominal.
    for (const [kind, anomalous] of [
      ["aircraft", "interrupted"],
      ["receiver", "fault"],
    ] as const) {
      const looks = [markerLook(kind, anomalous), markerLook(kind, "nominal"), markerLook(kind, "unknown")];
      expect(new Set(looks.map((look) => JSON.stringify(look))).size).toBe(3);
    }
  });

  it("draws every anomalous state alike, whatever the kind", () => {
    // spec: map-003 (1) — fault and deviating are both anomalous.
    expect(markerLook("receiver", "deviating")).toEqual(markerLook("receiver", "fault"));
    expect(markerLook("aircraft", "interrupted").fill).toBe(markerLook("receiver", "fault").fill);
  });

  it("gives each kind its own nominal colour, and an unexamined entity is hollow", () => {
    // spec: map-003 (1)
    expect(markerLook("aircraft", "nominal").fill).not.toBe(markerLook("receiver", "nominal").fill);
    expect(markerLook("aircraft", "unknown").fill).toBe("none");
    expect(markerLook("receiver", "unknown").fill).toBe("none");
  });

  it("draws each marker in the look its state calls for", async () => {
    // spec: map-003 (1) — ties the helper to what is rendered.
    renderMap();
    await markersReady();

    for (const [name, kind, state] of [
      ["Aircraft AC-1, interrupted", "aircraft", "interrupted"],
      ["Aircraft AC-2, nominal", "aircraft", "nominal"],
      ["Receiver RF-01 (Station 1), fault", "receiver", "fault"],
    ] as const) {
      const icon = screen.getByRole("button", { name }).querySelector("svg");
      expect(icon?.getAttribute("fill")).toBe(markerLook(kind, state).fill);
      expect(icon?.getAttribute("stroke")).toBe(markerLook(kind, state).stroke);
    }
  });
});

describe("the pop-up", () => {
  const openFor = async (name: string | RegExp) => {
    await markersReady();
    fireEvent.click(screen.getByRole("button", { name }));
    return within(await screen.findByRole("dialog"));
  };

  it("shows an aircraft's payload fields", async () => {
    // spec: map-005 (1)
    renderMap();
    const popup = await openFor("Aircraft AC-1, interrupted");

    expect(popup.getByText("AC-1")).toBeInTheDocument();
    expect(popup.getByText("30,000 ft")).toBeInTheDocument();
    expect(popup.getByText("interrupted")).toBeInTheDocument();
    expect(popup.getByText(/51\.25.*7\.5/)).toBeInTheDocument();
  });

  it("says an aircraft's altitude was not reported rather than inventing one", async () => {
    // spec: map-005 (1) — the exception panel's wording.
    renderMap();
    const popup = await openFor("Aircraft AC-2, nominal");

    expect(popup.getByText("not reported")).toBeInTheDocument();
  });

  it("shows a receiver's payload fields", async () => {
    // spec: map-005 (1)
    renderMap();
    const popup = await openFor("Receiver RF-01 (Station 1), fault");

    expect(popup.getByText("RF-01")).toBeInTheDocument();
    expect(popup.getByText("Station 1")).toBeInTheDocument();
    expect(popup.getByText("GNSS-L1")).toBeInTheDocument();
    expect(popup.getByText("fault")).toBeInTheDocument();
  });

  it("names an unexamined entity's state as not examined", async () => {
    // spec: map-005 (1), map-003 (2)
    renderMap({ tracks: [{ ...tracks[0], state: "unknown" }, tracks[1]] });
    const popup = await openFor("Aircraft AC-1, not examined");

    expect(popup.getByText("not examined")).toBeInTheDocument();
  });

  it("shows nothing the payload does not carry", async () => {
    // spec: map-005 — the named failure case: speed, heading, a linked hypothesis.
    renderMap();
    await openFor("Aircraft AC-1, interrupted");

    expect(screen.getByRole("dialog").textContent).not.toMatch(/kts|knot|speed|heading|hypothes/i);
  });

  it("closes on Escape, on its close button, and on a click on the map", async () => {
    // spec: map-005 (1)
    renderMap();

    await openFor("Aircraft AC-1, interrupted");
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    const popup = await openFor("Aircraft AC-1, interrupted");
    fireEvent.click(popup.getByRole("button", { name: /close/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await openFor("Aircraft AC-1, interrupted");
    act(() => lib.instances[0].emit("click", {}));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is only ever one", async () => {
    // spec: map-005 (1) — the named failure case: two open at once.
    renderMap();
    await openFor("Aircraft AC-1, interrupted");

    fireEvent.click(screen.getByRole("button", { name: "Receiver RF-01 (Station 1), fault" }));

    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(within(screen.getByRole("dialog")).getByText("RF-01")).toBeInTheDocument();
  });

  it("stays open through a poll that still carries the entity, with the new values", async () => {
    // spec: map-005 (1)
    const { rerenderWith } = renderMap();
    await openFor("Aircraft AC-1, interrupted");

    rerenderWith({ tracks: [{ ...tracks[0], altitudeFt: 31000 }, tracks[1]] });

    expect(await within(screen.getByRole("dialog")).findByText("31,000 ft")).toBeInTheDocument();
  });

  it("closes when the entity leaves the payload", async () => {
    // spec: map-005 — the named failure case: a pop-up for a row no longer carried.
    const { rerenderWith } = renderMap();
    await openFor("Aircraft AC-1, interrupted");

    rerenderWith({ tracks: [tracks[1]] });

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("the labels", () => {
  it("label every receiver with its station, and an interrupted aircraft with its name and altitude", async () => {
    // spec: map-005 (2)
    renderMap();
    await markersReady();

    expect(shown("Station 1")).toBe(true);
    expect(shown("Station 7")).toBe(true);
    expect(shown("AC-1 · 30,000 ft")).toBe(true);
  });

  it("leave a nominal aircraft unlabelled below zoom 9, and label it from zoom 9", async () => {
    // spec: map-005 (2)
    renderMap();
    await markersReady();
    expect(shown("AC-2")).toBe(false);

    lib.zoom = 9;
    act(() => lib.instances[0].emit("moveend"));

    await waitFor(() => expect(shown("AC-2")).toBe(true));
  });

  it("keep the more important label where two would overlap", async () => {
    // spec: map-005 (2) — every entity projected onto one point: only the
    // anomalous receiver's label survives.
    lib.project = () => ({ x: 100, y: 100 });
    lib.zoom = 9;
    renderMap();
    await markersReady();
    act(() => lib.instances[0].emit("moveend"));

    await waitFor(() => expect(shown("Station 1")).toBe(true));
    expect(shown("Station 2")).toBe(false);
    expect(shown("AC-1 · 30,000 ft")).toBe(false);
    expect(shown("AC-2")).toBe(false);
  });
});

describe("placing labels", () => {
  const label = (id: string, rank: number, x: number, y = 0) => ({ id, rank, x, y, text: "Station 1" });

  it("keeps the lower rank where two labels overlap, whatever order they arrive in", () => {
    // spec: map-005 (2) — the named failure case: a nominal label hiding an anomalous one.
    expect(placeLabels([label("nominal", 3, 0), label("anomalous", 2, 0)])).toEqual(new Set(["anomalous"]));
    expect(placeLabels([label("anomalous", 2, 0), label("nominal", 3, 0)])).toEqual(new Set(["anomalous"]));
  });

  it("keeps both when they are apart", () => {
    // spec: map-005 (2)
    expect(placeLabels([label("a", 3, 0), label("b", 3, 500)])).toEqual(new Set(["a", "b"]));
  });
});
