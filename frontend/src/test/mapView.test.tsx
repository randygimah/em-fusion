import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AircraftTrack, RFSensor } from "../types/operationalPicture";

// spec: map-001, map-002 — the MapView adapter and what it shows when it cannot be a map.
//
// Every other test file gets a stand-in for MapView from setup.ts; this one
// tests the real adapter, with the map library replaced. MapLibre needs WebGL,
// which jsdom does not have, so what is proved here is everything around the
// drawing: which configuration means which state, that the default style
// reaches nothing but this server, and that the library is not even loaded
// when there is nothing to draw.
vi.unmock("../components/map/MapView");

const lib = vi.hoisted(() => ({
  loaded: vi.fn(),
  failToStart: false,
  instances: [] as FakeMapInstance[],
}));

interface FakeMapInstance {
  options: { container: HTMLElement; style: unknown };
  setStyle: ReturnType<typeof vi.fn>;
  addSource: ReturnType<typeof vi.fn>;
  addLayer: ReturnType<typeof vi.fn>;
  emit: (event: string, payload?: unknown) => void;
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
    getSource = vi.fn(() => ({ setData: vi.fn() }));
    getLayer = vi.fn(() => undefined);
    remove = vi.fn();
    constructor(options: { container: HTMLElement; style: unknown }) {
      if (lib.failToStart) throw new Error("Failed to initialize WebGL");
      this.options = options;
      lib.instances.push(this as unknown as FakeMapInstance);
    }
    on(event: string, a: unknown, b?: unknown) {
      const callback = (typeof a === "function" ? a : b) as (payload?: unknown) => void;
      this.handlers[event] = [...(this.handlers[event] ?? []), callback];
      return this;
    }
    emit(event: string, payload?: unknown) {
      for (const callback of this.handlers[event] ?? []) callback(payload);
    }
  }
  const module = { Map: FakeMap, addProtocol: vi.fn(), removeProtocol: vi.fn(), AttributionControl: class {}, NavigationControl: class {} };
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

const { MapView, buildDefaultStyle, buildSatelliteStyle, entitiesGeoJson, readBasemapConfig } = await import("../components/map/MapView");

const ARCHIVE = "/basemap/em-fusion.pmtiles";
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

beforeEach(() => {
  lib.loaded.mockClear();
  lib.failToStart = false;
  lib.instances.length = 0;
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
  it("reaches nothing but this server — source, glyphs and sprite", () => {
    // spec: map-001 (3), (4) — a default style points glyphs and sprites at a
    // CDN, and the map would still render perfectly.
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

  it("builds satellite from the configured tiles and credits them", () => {
    // spec: map-001 (6), (7) — nothing in the repo names a provider.
    const text = JSON.stringify(buildSatelliteStyle(SATELLITE));

    expect(text).toContain(SATELLITE.tiles);
    expect(text).toContain(SATELLITE.attribution);
  });
});

describe("the entities as map features", () => {
  it("puts longitude before latitude, with each entity's id and state", () => {
    // spec: map-001 — GeoJSON is [lon, lat]; swapped, Cologne lands in Somalia.
    const { receivers, aircraft } = entitiesGeoJson(sensors, tracks);

    expect(receivers.features).toHaveLength(7);
    expect(aircraft.features[0].geometry.coordinates).toEqual([7.5, 51.25]);
    expect(aircraft.features[0].properties).toMatchObject({ id: "opensky-replay:AC-1", name: "AC-1", state: "interrupted" });
    expect(receivers.features[0].properties).toMatchObject({ id: "RF-01", state: "fault" });
  });
});

describe("the three states that are not a map", () => {
  it("says no basemap is configured, counts the entities, and never loads the map library", async () => {
    // spec: map-002 — no request, no throw, and nothing loaded.
    const readArchive = vi.fn(readable);
    render(
      <MapView
        config={{ defaultArchive: null, satellite: null }}
        readArchive={readArchive}
        sensors={sensors}
        tracks={tracks}
      />,
    );

    expect(screen.getByText(/no basemap is configured/i)).toBeInTheDocument();
    expect(screen.getByText(/7 receivers · 2 aircraft/)).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(readArchive).not.toHaveBeenCalled();
    expect(lib.loaded).not.toHaveBeenCalled();
  });

  it("says a configured archive could not be read, and names the fix", async () => {
    // spec: map-001 (5), map-002 — never "not configured", never a blank pane, never satellite.
    render(
      <MapView
        config={{ defaultArchive: ARCHIVE, satellite: SATELLITE }}
        readArchive={unreadable}
        sensors={sensors}
        tracks={tracks}
      />,
    );

    expect(await screen.findByText(/could not be read/i)).toBeInTheDocument();
    expect(screen.getByText(/make basemap/)).toBeInTheDocument();
    expect(screen.queryByText(/not configured/i)).not.toBeInTheDocument();
    expect(screen.getByText(/7 receivers · 2 aircraft/)).toBeInTheDocument();
    expect(lib.instances).toHaveLength(0);
  });

  it("says the browser could not start the map when the library fails", async () => {
    // spec: map-002 — e.g. no WebGL.
    lib.failToStart = true;
    render(
      <MapView
        config={{ defaultArchive: ARCHIVE, satellite: null }}
        readArchive={readable}
        sensors={sensors}
        tracks={tracks}
      />,
    );

    expect(await screen.findByText(/could not start the map/i)).toBeInTheDocument();
    expect(screen.getByText(/7 receivers · 2 aircraft/)).toBeInTheDocument();
  });
});

describe("the map", () => {
  it("starts on the self-hosted default", async () => {
    // spec: map-001
    render(
      <MapView
        config={{ defaultArchive: ARCHIVE, satellite: null }}
        readArchive={readable}
        sensors={sensors}
        tracks={tracks}
      />,
    );

    await waitFor(() => expect(lib.instances).toHaveLength(1));
    expect(JSON.stringify(lib.instances[0].options.style)).toContain(`pmtiles://${ARCHIVE}`);
    expect(screen.getByRole("region", { name: /map/i })).toBeInTheDocument();
  });

  it("draws a layer per entity kind once the style has loaded", async () => {
    // spec: map-001 — a marker layer per entity kind.
    render(
      <MapView
        config={{ defaultArchive: ARCHIVE, satellite: null }}
        readArchive={readable}
        sensors={sensors}
        tracks={tracks}
      />,
    );
    await waitFor(() => expect(lib.instances).toHaveLength(1));

    lib.instances[0].emit("load");

    const sources = lib.instances[0].addSource.mock.calls.map((call) => call[0]);
    expect(sources).toEqual(expect.arrayContaining(["receivers", "aircraft"]));
  });

  it("does not offer satellite when it is not configured", async () => {
    // spec: map-002 — the named failure case.
    render(
      <MapView
        config={{ defaultArchive: ARCHIVE, satellite: null }}
        readArchive={readable}
        sensors={sensors}
        tracks={tracks}
      />,
    );
    await waitFor(() => expect(lib.instances).toHaveLength(1));

    expect(screen.queryByRole("button", { name: /satellite/i })).not.toBeInTheDocument();
  });

  it("switches to satellite only when the analyst asks", async () => {
    // spec: map-001 (6) — an explicit action, never a fallback.
    render(
      <MapView
        config={{ defaultArchive: ARCHIVE, satellite: SATELLITE }}
        readArchive={readable}
        sensors={sensors}
        tracks={tracks}
      />,
    );
    await waitFor(() => expect(lib.instances).toHaveLength(1));
    expect(lib.instances[0].setStyle).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /satellite/i }));

    expect(JSON.stringify(lib.instances[0].setStyle.mock.calls[0][0])).toContain(SATELLITE.tiles);
  });

  it("says satellite tiles are failing, and does not substitute the default", async () => {
    // spec: map-001 (6) — a silent substitution makes the two indistinguishable.
    render(
      <MapView
        config={{ defaultArchive: ARCHIVE, satellite: SATELLITE }}
        readArchive={readable}
        sensors={sensors}
        tracks={tracks}
      />,
    );
    await waitFor(() => expect(lib.instances).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: /satellite/i }));

    lib.instances[0].emit("error", { sourceId: "satellite", error: new Error("403") });

    expect(await screen.findByText(/satellite tiles are failing/i)).toBeInTheDocument();
    expect(lib.instances[0].setStyle).toHaveBeenCalledTimes(1);
  });
});
