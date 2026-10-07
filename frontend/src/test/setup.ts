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
// unmocks it to test the real adapter.
vi.mock("../components/map/MapView", () => ({
  MapView: ({ sensors, tracks }: { sensors: { id: string }[]; tracks: { id: string }[] }) =>
    createElement(
      "div",
      { "data-testid": "map-view-stub" },
      createElement("p", null, `receivers: ${sensors.map((sensor) => sensor.id).join(", ")}`),
      createElement("p", null, `aircraft: ${tracks.map((track) => track.id).join(", ")}`),
    ),
}));
