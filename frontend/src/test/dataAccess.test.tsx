import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { DEFAULT_POLL_INTERVAL_MS, OPERATIONAL_PICTURE_PATH } from "../lib/api";
import operationalPicture from "../mocks/operationalPictureMock";
import type { OperationalPicture } from "../types/operationalPicture";

// spec: api-003 — the app polls one endpoint, keeps rendering when that fails,
// and says so rather than presenting example data as though it were real.

const served: OperationalPicture = {
  ...operationalPicture,
  scenario: { id: "8", name: "replay-only", dataMode: "replayed", health: "unknown" },
  hypotheses: [],
  rfSensors: [],
  timelineEvents: [],
  detectionSummary: { anomalyLevel: null, signalIntegrity: null },
  aircraftTracks: [
    { id: "opensky-replay:AC-served", name: "AC-served", altitudeFt: 29800, lat: 51.79, lon: 10.36 },
  ],
};

const ok = (payload: OperationalPicture) =>
  ({ ok: true, status: 200, json: async () => payload }) as Response;

const failure = (status: number) =>
  ({ ok: false, status, json: async () => ({}) }) as Response;

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue(ok(served));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("polling the operational picture", () => {
  it("asks the backend for the picture on the contract's path", async () => {
    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0][0])).toContain(OPERATIONAL_PICTURE_PATH);
  });

  it("renders what the backend served rather than the example data", async () => {
    render(<App />);

    expect(await screen.findByText("replay-only")).toBeInTheDocument();
    expect(screen.queryByText(operationalPicture.scenario?.name ?? "")).not.toBeInTheDocument();
  });

  it("says the data is degraded before the first response arrives", () => {
    // The mock is on screen at that moment, and example data presented as the
    // system's own is the failure this whole project argues against.
    render(<App />);

    expect(screen.getByText(/degraded/i)).toBeInTheDocument();
  });

  it("clears the degraded indicator once real data arrives", async () => {
    render(<App />);

    await screen.findByText("replay-only");
    expect(screen.queryByText(/degraded/i)).not.toBeInTheDocument();
  });

  it("asks again after the poll interval", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<App />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await vi.advanceTimersByTimeAsync(DEFAULT_POLL_INTERVAL_MS);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("keeps rendering and reports degraded when the backend returns 500", async () => {
    fetchMock.mockResolvedValue(failure(500));
    render(<App />);

    expect(await screen.findByText(/degraded/i)).toBeInTheDocument();
    // The named failure case: a 500 must not clear the picture.
    expect(screen.getByRole("heading", { name: /active hypotheses/i })).toBeInTheDocument();
  });

  it("keeps rendering and reports degraded when the network fails", async () => {
    fetchMock.mockRejectedValue(new Error("connection refused"));
    render(<App />);

    expect(await screen.findByText(/degraded/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /active hypotheses/i })).toBeInTheDocument();
  });

  it("keeps the last good picture when a later poll fails", async () => {
    // Stale real data behind a degraded indicator beats reverting to invented
    // data: the mock is the fallback only while nothing real has ever arrived.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<App />);

    await screen.findByText("replay-only");
    fetchMock.mockRejectedValue(new Error("connection refused"));
    await vi.advanceTimersByTimeAsync(DEFAULT_POLL_INTERVAL_MS);

    await waitFor(() => expect(screen.getByText(/degraded/i)).toBeInTheDocument());
    expect(screen.getByText("replay-only")).toBeInTheDocument();
  });
});
