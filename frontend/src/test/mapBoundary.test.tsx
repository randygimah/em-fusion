import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import operationalPictureMock from "../mocks/operationalPictureMock";
import OperationalPictureScreen from "../screens/operationalPicture";
import type { OperationalPicture } from "../types/operationalPicture";

// spec: map-001 — the adapter boundary, from outside it.
//
// MapView is the only module allowed to touch a map library, so it can be
// replaced wholesale — which setup.ts does for every test file but its own. The
// stand-in renders the props it was given as text, which is how the screen is
// checked to hand the map the same filtered payload the exception panel reads.

const MAP_LIBRARIES = ["maplibre-gl", "pmtiles", "@protomaps/basemaps"];
const ADAPTER = "../components/map/MapView.tsx";

// Read from disk, not through Vite: Vite refuses to serve .env files as modules
// (server.fs.deny), a default worth keeping rather than loosening for a test.
// Relative to the Vitest root, which is frontend/ here and in the container.
const envFile = (name: string) => readFileSync(name, "utf8");
const envDevelopment = envFile(".env.development");
const envProduction = envFile(".env.production");

const sources = import.meta.glob("../**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

const importsOf = (source: string): string[] =>
  [...source.matchAll(/(?:from\s+|import\s*\(\s*|import\s+)["']([^"']+)["']/g)].map((match) => match[1]);

describe("the boundary", () => {
  it("lets exactly one module import a map library", () => {
    // spec: map-001, FR-705 — the named failure case: a second importer.
    const importers = Object.entries(sources)
      // Test files are excluded: they mock or import the libraries on purpose. Files
      // in this folder are listed as "./x.test.tsx", not by a path through /test/.
      .filter(([path]) => !path.includes("/test/") && !path.startsWith("./"))
      .filter(([, source]) => importsOf(source).some((name) => MAP_LIBRARIES.includes(name)))
      .map(([path]) => path);

    expect(importers).toEqual([ADAPTER]);
  });

  it("scans the source it claims to", () => {
    // spec: map-001 — a glob that matched nothing would pass the check above vacuously.
    expect(Object.keys(sources)).toContain(ADAPTER);
    expect(Object.keys(sources)).toContain("../screens/operationalPicture.tsx");
  });
});

describe("the frontend's committed settings", () => {
  it("point the default basemap at this server, in development and production", () => {
    // spec: map-001 (4) — the default is configured, and configured same-origin.
    for (const file of [envDevelopment, envProduction]) {
      expect(file).toMatch(/^VITE_BASEMAP_ARCHIVE=\/basemap\/[\w.-]+\.pmtiles$/m);
    }
  });

  it("hold nothing but published VITE_ settings and name no satellite provider", () => {
    // spec: map-001 (6) — these files are committed, so nothing in them may be a
    // secret: Vite publishes every VITE_ variable into the bundle anyway.
    for (const file of [envDevelopment, envProduction]) {
      const keys = file
        .split("\n")
        .filter((line) => line.trim() && !line.trim().startsWith("#"))
        .map((line) => line.split("=")[0]);
      expect(keys.every((key) => key.startsWith("VITE_"))).toBe(true);
      expect(file).not.toMatch(/VITE_SATELLITE_TILES=\S/);
    }
  });
});

describe("the screen hands the map the filtered payload", () => {
  const picture: OperationalPicture = {
    ...operationalPictureMock,
    rfSensors: [operationalPictureMock.rfSensors[0]],
    aircraftTracks: [
      { id: "opensky-replay:AC-1", name: "AC-1", altitudeFt: 30000, lat: 51.2, lon: 7.5, state: "interrupted" },
      { id: "opensky-replay:AC-2", name: "AC-2", altitudeFt: 31000, lat: 51.3, lon: 7.6, state: "interrupted" },
    ],
    view: { selected: "anomalous", examined: true, suppressed: { rfSensors: 6, aircraftTracks: 410, timelineEvents: 0 } },
  };

  it("draws the map where the placeholder box was", () => {
    // spec: map-001, op-004 (4)
    render(<OperationalPictureScreen operationalPicture={picture} />);

    expect(screen.getByTestId("map-view-stub")).toBeInTheDocument();
    expect(screen.queryByText(/the map is not built yet/i)).not.toBeInTheDocument();
  });

  it("gives the map the same rows the panel lists, so the two cannot disagree", () => {
    // spec: map-001, op-007, FR-716 — one control drives both.
    render(<OperationalPictureScreen operationalPicture={picture} />);

    const map = within(screen.getByTestId("map-view-stub"));
    expect(map.getByText(`receivers: ${picture.rfSensors[0].id}`)).toBeInTheDocument();
    expect(map.getByText("aircraft: opensky-replay:AC-1, opensky-replay:AC-2")).toBeInTheDocument();
  });

  it("gives the map the interference zones the payload carried", () => {
    // spec: map-006, api-017 — filtered like every other row, by the same view.
    const zoneId = "FUSION-SPATIAL:RF-04:2022-06-27T12:02:00+00:00";
    const withZone = {
      ...picture,
      interferenceZones: [
        {
          id: zoneId,
          centre: { lat: 51.4, lon: 6.1 },
          radiusKm: 60,
          receivers: ["RF-04", "RF-05"],
          startedAt: "2022-06-27T12:02:00+00:00",
          endedAt: "2022-06-27T12:08:00+00:00",
          confidence: "Medium" as const,
          corroboration: "not_measurable" as const,
        },
      ],
    };
    render(<OperationalPictureScreen operationalPicture={withZone} />);

    expect(within(screen.getByTestId("map-view-stub")).getByText(`zones: ${zoneId}`)).toBeInTheDocument();
  });
});
