import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "../lib/api";
import operationalPictureMock from "../mocks/operationalPictureMock";
import OperationalPictureScreen from "../screens/operationalPicture";
import type { OperationalPicture, ReceiverStates, RFSensor, SelectableHour } from "../types/operationalPicture";

// spec: map-007 — receivers in their state at the playback cursor.
//
// The picture gives each receiver one state for the whole hour. With playback
// open the map draws each receiver in the state of the interval holding the
// cursor (api-018), nominal outside every interval, and not examined on an
// hour nobody examined. Until the intervals have loaded, or if they never do,
// a receiver keeps the picture's state and is said to be showing the whole
// hour, never shown as nominal. Closing playback restores the picture's own.

// The module under test, looked up rather than imported, so its absence fails
// each test that uses it instead of the whole file at load.
const modules = import.meta.glob<typeof import("../lib/receiverPlayback")>("../lib/receiverPlayback.ts", { eager: true });
const lib = () => {
  const found = modules["../lib/receiverPlayback.ts"];
  if (!found) throw new Error("src/lib/receiverPlayback.ts does not exist");
  return found;
};

type MapSensor = RFSensor & { provisional?: boolean };
type LoadReceiverStates = (runId: number) => Promise<ReceiverStates>;

// Run 480's window.
const START = Date.UTC(2022, 5, 27, 12, 36, 51);
const END = Date.UTC(2022, 5, 27, 12, 51, 51);
const at = (seconds: number) => START + seconds * 1000;
const iso = (ms: number) => new Date(ms).toISOString();

const sensor = (id: string, health: string): RFSensor => ({
  id,
  stationName: `Station ${id}`,
  signalId: "GNSS-L1",
  health,
  lat: 51,
  lon: 6,
});

// The picture's whole-hour states: the worst moment of each timeline below.
const SENSORS = [sensor("RF-01", "fault"), sensor("RF-02", "nominal"), sensor("RF-03", "deviating")];

const interval = (from: number, to: number, state: "fault" | "deviating") => ({ startedAt: iso(at(from)), endedAt: iso(at(to)), state });

// RF-01: faulted 100–200 s, then deviating 200–300 s, touching at 200 s.
// RF-02: nominal throughout. RF-03: deviating 400–500 s.
const STATES: ReceiverStates = {
  runId: 480,
  examined: true,
  receivers: [
    { id: "RF-01", intervals: [interval(100, 200, "fault"), interval(200, 300, "deviating")] },
    { id: "RF-02", intervals: [] },
    { id: "RF-03", intervals: [interval(400, 500, "deviating")] },
  ],
};

const UNEXAMINED: ReceiverStates = {
  runId: 480,
  examined: false,
  receivers: SENSORS.map(({ id }) => ({ id, intervals: null })),
};

const statesAt = (seconds: number, states: ReceiverStates | null = STATES, sensors = SENSORS): Record<string, string> =>
  Object.fromEntries(lib().receiversAt(sensors, states, at(seconds)).map((one: MapSensor) => [one.id, one.health]));

describe("a receiver's state at the cursor", () => {
  it("is the state of the interval holding the cursor", () => {
    expect(statesAt(150)).toEqual({ "RF-01": "fault", "RF-02": "nominal", "RF-03": "nominal" });
    expect(statesAt(250)).toEqual({ "RF-01": "deviating", "RF-02": "nominal", "RF-03": "nominal" });
    expect(statesAt(450)).toEqual({ "RF-01": "nominal", "RF-02": "nominal", "RF-03": "deviating" });
  });

  it("is nominal outside every interval, whatever the picture says of the whole hour", () => {
    // The failure case: a receiver shown faulted outside its fault's window.
    expect(statesAt(50)).toEqual({ "RF-01": "nominal", "RF-02": "nominal", "RF-03": "nominal" });
    expect(statesAt(800)).toEqual({ "RF-01": "nominal", "RF-02": "nominal", "RF-03": "nominal" });
  });

  it("holds at both bounds of an interval, which are closed", () => {
    expect(statesAt(100)["RF-01"]).toBe("fault");
    expect(statesAt(300)["RF-01"]).toBe("deviating");
    expect(statesAt(301)["RF-01"]).toBe("nominal");
  });

  it("is the worse state where two intervals touch", () => {
    // 200 s closes the fault and opens the deviation.
    expect(statesAt(200)["RF-01"]).toBe("fault");
  });

  it("is not examined on an hour nobody examined, never nominal", () => {
    // The failure case: an unexamined hour shown as nominal.
    expect(statesAt(150, UNEXAMINED)).toEqual({ "RF-01": "unknown", "RF-02": "unknown", "RF-03": "unknown" });
  });

  it("keeps the picture's state, said to be the whole hour's, until the intervals have loaded", () => {
    const drawn = lib().receiversAt(SENSORS, null, at(50)) as MapSensor[];

    expect(drawn.map((one) => [one.id, one.health, one.provisional])).toEqual([
      ["RF-01", "fault", true],
      ["RF-02", "nominal", true],
      ["RF-03", "deviating", true],
    ]);
  });

  it("keeps the picture's state, said to be the whole hour's, for a receiver the timeline does not name", () => {
    const drawn = lib().receiversAt([...SENSORS, sensor("RF-04", "fault")], STATES, at(50)) as MapSensor[];

    expect(drawn.find((one) => one.id === "RF-04")).toMatchObject({ health: "fault", provisional: true });
  });

  it("changes nothing about a receiver but its state, and is not marked once loaded", () => {
    const drawn = lib().receiversAt(SENSORS, STATES, at(150)) as MapSensor[];

    drawn.forEach((one, index) => {
      const { health: _health, ...rest } = SENSORS[index];
      expect(one).toMatchObject(rest);
      expect(one.provisional ?? false).toBe(false);
    });
  });

  it("depends on the cursor alone, so any speed reaches the same picture", () => {
    const once = lib().receiversAt(SENSORS, STATES, at(250));
    lib().receiversAt(SENSORS, STATES, at(450));

    expect(lib().receiversAt(SENSORS, STATES, at(250))).toEqual(once);
  });
});

// ------------------------------------------------------------ through the screen

const HOURS: SelectableHour[] = [{ runId: 480, observedFrom: iso(START), observedTo: iso(END), examined: true }];

const picture = (): OperationalPicture => ({
  ...operationalPictureMock,
  scenario: { id: "480", name: "Run 480", dataMode: "mixed" },
  rfSensors: SENSORS,
  view: { ...operationalPictureMock.view, selected: "all" },
});

const loader = (answer: Promise<ReceiverStates> = Promise.resolve(STATES)) => vi.fn((_run: number) => answer);

const show = (loadReceiverStates?: LoadReceiverStates) =>
  render(
    <OperationalPictureScreen
      hours={HOURS}
      pinnedRun={480}
      operationalPicture={picture()}
      selectedView="all"
      {...({ loadReceiverStates } as Record<string, unknown>)}
    />,
  );

const stub = () => within(screen.getByTestId("map-view-stub"));
const line = () => stub().getByText(/^receiver states:/).textContent ?? "";
const openPlayback = () => fireEvent.click(screen.getByRole("button", { name: /play back this hour/i }));
const closePlayback = () => fireEvent.click(screen.getByRole("button", { name: /close playback/i }));
const scrubTo = (ms: number) => fireEvent.change(screen.getByRole("slider", { name: /playback position/i }), { target: { value: String(ms) } });

const WHOLE_HOUR = "receiver states: RF-01 fault (whole hour); RF-02 nominal (whole hour); RF-03 deviating (whole hour)";

describe("receivers through the screen", () => {
  it("asks for the hour's receiver states once, when playback opens, and not before", async () => {
    const load = loader();
    show(load);
    expect(load).not.toHaveBeenCalled();

    openPlayback();
    await waitFor(() => expect(line()).toBe("receiver states: RF-01 nominal; RF-02 nominal; RF-03 nominal"));
    scrubTo(at(150));
    scrubTo(at(450));

    expect(load.mock.calls).toEqual([[480]]);
  });

  it("hands the map each receiver in its state at the cursor", async () => {
    show(loader());
    openPlayback();
    await waitFor(() => expect(line()).toBe("receiver states: RF-01 nominal; RF-02 nominal; RF-03 nominal"));

    scrubTo(at(150));
    expect(line()).toBe("receiver states: RF-01 fault; RF-02 nominal; RF-03 nominal");
    scrubTo(at(450));
    expect(line()).toBe("receiver states: RF-01 nominal; RF-02 nominal; RF-03 deviating");
  });

  it("keeps the picture's states, said to be the whole hour's, while the answer is loading", () => {
    show(loader(new Promise<ReceiverStates>(() => {})));
    openPlayback();

    expect(line()).toBe(WHOLE_HOUR);
  });

  it("keeps the picture's states, said to be the whole hour's, when the answer never comes", async () => {
    const load = loader(Promise.reject(new Error("503")));
    show(load);
    openPlayback();
    await waitFor(() => expect(load).toHaveBeenCalled());

    scrubTo(at(450));
    expect(line()).toBe(WHOLE_HOUR);
  });

  it("refuses an answer for another hour", async () => {
    const load = loader(Promise.resolve({ ...STATES, runId: 481 }));
    show(load);
    openPlayback();
    await waitFor(() => expect(load).toHaveBeenCalled());

    scrubTo(at(150));
    expect(line()).toBe(WHOLE_HOUR);
  });

  it("draws every receiver not examined on an hour nobody examined", async () => {
    show(loader(Promise.resolve(UNEXAMINED)));
    openPlayback();

    await waitFor(() => expect(line()).toBe("receiver states: RF-01 unknown; RF-02 unknown; RF-03 unknown"));
  });

  it("restores the picture's whole-hour states when playback closes", async () => {
    // The failure case: closing leaving cursor states on the map.
    show(loader());
    openPlayback();
    scrubTo(at(450));
    await waitFor(() => expect(line()).toBe("receiver states: RF-01 nominal; RF-02 nominal; RF-03 deviating"));

    closePlayback();
    expect(line()).toBe("receiver states: RF-01 fault; RF-02 nominal; RF-03 deviating");
  });
});

// ------------------------------------------------------------------ the fetcher

describe("fetching an hour's receiver states", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("asks the receiver-states endpoint for the run", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => STATES }) as Response);
    vi.stubGlobal("fetch", fetchMock);

    expect(await api.fetchReceiverStates(480)).toEqual(STATES);

    const url = new URL(String((fetchMock.mock.calls[0] as unknown[])[0]), "http://localhost");
    expect(api.RECEIVER_STATES_PATH).toBe("/api/v1/operational-picture/receiver-states");
    expect(url.pathname).toBe(api.RECEIVER_STATES_PATH);
    expect(Object.fromEntries(url.searchParams)).toEqual({ run: "480" });
  });

  it("refuses an answer that is not receiver states", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ detail: "nope" }) }) as Response));

    await expect(api.fetchReceiverStates(480)).rejects.toThrow(/not receiver states/);
  });

  it("throws on a refusal rather than returning it", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }) as Response));

    await expect(api.fetchReceiverStates(480)).rejects.toThrow(/responded 404/);
  });
});
