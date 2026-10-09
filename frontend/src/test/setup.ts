import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, vi } from "vitest";

// Vitest here runs without `globals`, so Testing Library's own auto-cleanup
// never registers itself. Without this, renders accumulate across the tests in
// a file and every query that should match one element matches several — which
// reads as a duplicate-element bug in the component rather than as a missing
// teardown in the harness.
afterEach(cleanup);

// spec: map-001 — MapView is the one module that touches a map library, which
// is what lets every test file but its own replace it wholesale. The stand-in
// renders the props it was handed as text, so a screen test can check the map
// receives the same filtered rows as the exception panel. mapView.test.tsx
// unmocks it to test the real adapter. The playback cursor (op-008) is shown
// too, so the screen's tests can check the map is handed the cursor.
vi.mock("../components/map/MapView", () => ({
  MapView: ({
    sensors,
    tracks,
    zones = [],
    cursor = null,
    trails = [],
  }: {
    sensors: { id: string }[];
    tracks: { id: string; lat: number; lon: number; stale?: boolean }[];
    zones?: { id: string }[];
    cursor?: string | null;
    trails?: { id: string; segments: { broken: boolean }[] }[];
  }) =>
    createElement(
      "div",
      { "data-testid": "map-view-stub" },
      createElement("p", null, `receivers: ${sensors.map((sensor) => sensor.id).join(", ")}`),
      createElement("p", null, `aircraft: ${tracks.map((track) => track.id).join(", ")}`),
      createElement("p", null, `zones: ${zones.map((zone) => zone.id).join(", ")}`),
      createElement("p", null, `cursor: ${cursor ?? "none"}`),
      // map-004: where each aircraft is drawn, and the trails behind them.
      createElement(
        "p",
        null,
        `positions: ${tracks.map((track) => `${track.id}@${track.lat.toFixed(4)},${track.lon.toFixed(4)}${track.stale ? " not reporting" : ""}`).join("; ")}`,
      ),
      createElement(
        "p",
        null,
        `trails: ${trails.flatMap((trail) => trail.segments.map((segment) => `${trail.id}:${segment.broken ? "broken" : "solid"}`)).join(", ")}`,
      ),
    ),
}));
