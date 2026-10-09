import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { DEFAULT_POLL_INTERVAL_MS, EVIDENCE_PATH, OPERATIONAL_PICTURE_PATH, SELECTABLE_HOURS_PATH } from "../lib/api";
import { findingLabel } from "../lib/detectionVocabulary";
import operationalPictureMock from "../mocks/operationalPictureMock";
import OperationalPictureScreen from "../screens/operationalPicture";
import type {
  AircraftTrack,
  OperationalPicture,
  RFSensor,
  SelectableHour,
  SuppressedCounts,
  TimelineEvent,
  ViewSelection,
} from "../types/operationalPicture";

// spec: op-005 — the drill-down tables.
//
// The exception panel shows what the view admits; *View all* opens the whole
// of the open tab's collection for the hour on screen, whatever the view says
// (FR-709, FR-716). Most of what is tested here is that "all" means all: the
// table is the hour the panel shows, served unfiltered, from the endpoint the
// panel already reads — and when it cannot be that, it says so rather than
// putting the panel's filtered rows under a heading that says *all*.

const sensor = (id: string, health: string, stationName: string): RFSensor => ({
  id,
  stationName,
  signalId: "GNSS-L1",
  health,
  lat: 51.0,
  lon: 7.0,
});

const track = (name: string, state: AircraftTrack["state"], altitudeFt: number | null): AircraftTrack => ({
  id: `opensky-replay:${name}`,
  name,
  altitudeFt,
  lat: 51.7912,
  lon: 10.3645,
  state,
});

const event = (time: string, source: string): TimelineEvent => ({
  id: `SENSOR-FAULT:${source}:${time}`,
  time,
  event: "possible_sensor_fault",
  source,
});

const NONE: SuppressedCounts = { rfSensors: 0, aircraftTracks: 0, timelineEvents: 0, interferenceZones: 0 };

const picture = (
  runId: string | null,
  selected: ViewSelection,
  rows: Partial<Pick<OperationalPicture, "rfSensors" | "aircraftTracks" | "timelineEvents">>,
  suppressed: Partial<SuppressedCounts> = {},
  examined = true,
): OperationalPicture => ({
  ...operationalPictureMock,
  scenario: runId === null ? null : { id: runId, name: `Run ${runId}`, dataMode: "mixed" },
  hypotheses: [],
  rfSensors: [],
  aircraftTracks: [],
  timelineEvents: [],
  interferenceZones: [],
  ...rows,
  detectionSummary: examined ? operationalPictureMock.detectionSummary : null,
  view: { selected, examined, suppressed: { ...NONE, ...suppressed } },
});

// The whole hour: two receivers out of nominal among seven, two aircraft whose
// reporting broke among four (one with no altitude), two conclusions served
// newest first. Neither the anomalous-first order nor the oldest-first order
// coincides with array or alphabetical order, so each is tested for itself.
// AC-alpha flies at 9,000 ft so that numeric and text order disagree: with
// 12,000 here, comparing altitudes as text survived the mutation pass.
const RECEIVERS = [
  sensor("RF-01", "nominal", "Aachen"),
  sensor("RF-07", "nominal", "Weeze"),
  sensor("RF-05", "fault", "Eindhoven"),
  sensor("RF-02", "nominal", "Venlo"),
  sensor("RF-06", "nominal", "Liege"),
  sensor("RF-03", "deviating", "Kleve"),
  sensor("RF-04", "nominal", "Essen"),
];
const AIRCRAFT = [
  track("AC-alpha", "nominal", 9000),
  track("AC-delta", "interrupted", 30000),
  track("AC-charlie", "nominal", null),
  track("AC-bravo", "interrupted", 35000),
];
const EVENTS = [event("2022-06-27T12:40:00Z", "RF-05"), event("2022-06-27T12:05:00Z", "RF-03")];

const unfiltered = (runId = "420", rows: Partial<OperationalPicture> = {}) =>
  picture(runId, "all", { rfSensors: RECEIVERS, aircraftTracks: AIRCRAFT, timelineEvents: EVENTS, ...rows });

// What the panel shows of run 420 under the default view.
const onScreen = (runId: string | null = "420") =>
  picture(
    runId,
    "anomalous",
    {
      rfSensors: [RECEIVERS[2], RECEIVERS[5]],
      aircraftTracks: [AIRCRAFT[1], AIRCRAFT[3]],
      timelineEvents: EVENTS,
    },
    { rfSensors: 5, aircraftTracks: 2 },
  );

const show = (data: OperationalPicture, loadUnfiltered?: (runId: number) => Promise<OperationalPicture>) =>
  render(
    <OperationalPictureScreen
      loadUnfiltered={loadUnfiltered}
      operationalPicture={data}
    />,
  );

const loader = (payload: OperationalPicture = unfiltered()) => vi.fn(async (_runId: number) => payload);

const viewAll = () => screen.getByRole("button", { name: /view all/i });
const openTab = (name: RegExp) => fireEvent.click(screen.getByRole("tab", { name }));
const dialog = () => screen.getByRole("dialog");
const table = () => within(dialog()).getByRole("table");
const firstColumn = () =>
  within(table())
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[0].textContent);
const headers = () =>
  within(table())
    .getAllByRole("columnheader")
    .map((cell) => cell.textContent);

const opened = async (tab: RegExp = /^RF/, load = loader()) => {
  show(onScreen(), load);
  openTab(tab);
  fireEvent.click(viewAll());
  await within(await screen.findByRole("dialog")).findByRole("table");
  return load;
};

describe("View all", () => {
  it("is enabled when an hour is on screen", () => {
    // spec: op-005 — it was disabled until this item, with a reason saying so.
    show(onScreen(), loader());

    expect(viewAll()).toBeEnabled();
    expect(screen.queryByText(/not built yet/i)).not.toBeInTheDocument();
  });

  it("is disabled, with a reason, when there is no hour to drill into", () => {
    // spec: op-005
    show(onScreen(null), loader());

    expect(viewAll()).toBeDisabled();
    expect(screen.getByText(/no hour is on screen/i)).toBeInTheDocument();
  });

  it("is disabled, with a reason, when nothing is wired to load the table", () => {
    // spec: op-005 — the pattern Scenario Control's controls follow.
    show(onScreen());

    expect(viewAll()).toBeDisabled();
    expect(screen.getByText(/full tables are not connected/i)).toBeInTheDocument();
  });
});

describe("what it opens", () => {
  it("opens the open tab's table over the screen, for the hour on screen", async () => {
    // spec: op-005, FR-709
    const load = await opened(/^RF/);

    expect(load).toHaveBeenCalledTimes(1);
    expect(load).toHaveBeenCalledWith(420);
    expect(dialog()).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("dialog", { name: /run 420 · all 7 receivers/i })).toBeInTheDocument();
  });

  it("opens the aircraft from the Tracks tab and the conclusions from the Events tab", async () => {
    // spec: op-005
    await opened(/^Tracks/);
    expect(screen.getByRole("dialog", { name: /run 420 · all 4 aircraft/i })).toBeInTheDocument();
    fireEvent.click(within(dialog()).getByRole("button", { name: /close/i }));

    openTab(/^Events/);
    fireEvent.click(viewAll());
    expect(await screen.findByRole("dialog", { name: /run 420 · all 2 conclusions/i })).toBeInTheDocument();
  });

  it("asks for the hour the panel shows, not the newest, and keeps it when the screen moves on", async () => {
    // spec: op-005 — the named failure case: a table for a different hour.
    const load = loader(unfiltered("207"));
    const { rerender } = show(onScreen("207"), load);
    fireEvent.click(viewAll());
    await screen.findByRole("dialog", { name: /run 207/i });

    rerender(
      <OperationalPictureScreen
        loadUnfiltered={load}
        operationalPicture={onScreen("420")}
      />,
    );

    expect(load).toHaveBeenCalledTimes(1);
    expect(load).toHaveBeenCalledWith(207);
    expect(screen.getByRole("dialog", { name: /run 207/i })).toBeInTheDocument();
  });

  it("says the table is not filtered by the view", async () => {
    // spec: op-005, FR-716
    await opened();

    expect(within(dialog()).getByText(/not filtered by the view/i)).toBeInTheDocument();
  });
});

describe("the rows", () => {
  it("are every receiver, nominal and anomalous, whatever the view", async () => {
    // spec: op-005 — the panel showed two; the hour has seven.
    await opened(/^RF/);

    expect(within(table()).getAllByRole("row")).toHaveLength(1 + 7);
    expect(within(table()).getAllByText("nominal")).toHaveLength(5);
  });

  it("carry the receiver's own columns and nothing the payload lacks", async () => {
    // spec: op-005, op-004 (4)
    await opened(/^RF/);

    expect(headers()).toEqual(["Receiver", "Station", "Band", "State"]);
    expect(within(table()).getByText("Eindhoven")).toBeInTheDocument();
    for (const invented of [/last signal/i, /noise floor/i, /severity/i]) {
      expect(within(dialog()).queryByText(invented)).not.toBeInTheDocument();
    }
  });

  it("carry an aircraft's pseudonym, altitude, position and state, and say an absent altitude was not reported", async () => {
    // spec: op-005, op-004 (4)
    await opened(/^Tracks/);

    expect(headers()).toEqual(["Aircraft", "Altitude", "Position", "State"]);
    expect(within(table()).getAllByRole("row")).toHaveLength(1 + 4);
    expect(within(table()).getByText("30,000 ft")).toBeInTheDocument();
    expect(within(table()).getByText("not reported")).toBeInTheDocument();
    expect(within(table()).getAllByText(/51\.79/)).toHaveLength(4);
  });

  it("carry each conclusion's simulated time, its words and its source", async () => {
    // spec: op-005, op-006 — worded from the vocabulary, never the raw type.
    await opened(/^Events/);

    expect(headers()).toEqual(["Time", "Conclusion", "Source"]);
    expect(within(table()).getByText("2022-06-27 12:05")).toBeInTheDocument();
    expect(within(table()).getAllByText(findingLabel("possible_sensor_fault"))).toHaveLength(2);
    expect(within(table()).queryByText("possible_sensor_fault")).not.toBeInTheDocument();
  });

  it("say an hour nobody examined was not examined", async () => {
    // spec: op-005, api-007
    const unexamined = picture("420", "all", { rfSensors: RECEIVERS.map((r) => ({ ...r, health: "unknown" })) }, {}, false);
    await opened(/^RF/, loader(unexamined));

    expect(within(dialog()).getByText(/not been examined/i)).toBeInTheDocument();
  });

  it("say what an empty collection means rather than drawing an empty table", async () => {
    // spec: op-005 — no aircraft in the hour's final five minutes.
    show(onScreen(), loader(unfiltered("420", { aircraftTracks: [] })));
    openTab(/^Tracks/);
    fireEvent.click(viewAll());

    expect(await within(await screen.findByRole("dialog")).findByText(/no aircraft in the final five minutes/i)).toBeInTheDocument();
    expect(within(dialog()).queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("the order", () => {
  it("puts receivers out of nominal first, then orders by receiver", async () => {
    // spec: op-005
    await opened(/^RF/);

    expect(firstColumn()).toEqual(["RF-03", "RF-05", "RF-01", "RF-02", "RF-04", "RF-06", "RF-07"]);
    expect(within(dialog()).getByRole("columnheader", { name: "State" })).toHaveAttribute("aria-sort", "ascending");
  });

  it("puts aircraft whose reporting broke first, then orders by aircraft", async () => {
    // spec: op-005
    await opened(/^Tracks/);

    expect(firstColumn()).toEqual(["AC-bravo", "AC-delta", "AC-alpha", "AC-charlie"]);
  });

  it("puts conclusions oldest first, by event time and not array order", async () => {
    // spec: op-005, op-006
    await opened(/^Events/);

    expect(firstColumn()).toEqual(["2022-06-27 12:05", "2022-06-27 12:40"]);
    expect(within(dialog()).getByRole("columnheader", { name: "Time" })).toHaveAttribute("aria-sort", "ascending");
  });

  it("sorts by a column whose header is clicked, and reverses on a second click", async () => {
    // spec: op-005 — and says so to assistive technology.
    await opened(/^Tracks/);
    const aircraft = () => within(dialog()).getByRole("columnheader", { name: "Aircraft" });

    fireEvent.click(within(aircraft()).getByRole("button"));
    expect(firstColumn()).toEqual(["AC-alpha", "AC-bravo", "AC-charlie", "AC-delta"]);
    expect(aircraft()).toHaveAttribute("aria-sort", "ascending");
    expect(within(dialog()).getByRole("columnheader", { name: "State" })).toHaveAttribute("aria-sort", "none");

    fireEvent.click(within(aircraft()).getByRole("button"));
    expect(firstColumn()).toEqual(["AC-delta", "AC-charlie", "AC-bravo", "AC-alpha"]);
    expect(aircraft()).toHaveAttribute("aria-sort", "descending");
  });

  it("sorts altitudes as numbers and an altitude not reported last, either way", async () => {
    // spec: op-005
    await opened(/^Tracks/);
    const altitude = () => within(within(dialog()).getByRole("columnheader", { name: "Altitude" })).getByRole("button");

    fireEvent.click(altitude());
    expect(firstColumn()).toEqual(["AC-alpha", "AC-delta", "AC-bravo", "AC-charlie"]);

    fireEvent.click(altitude());
    expect(firstColumn()).toEqual(["AC-bravo", "AC-delta", "AC-alpha", "AC-charlie"]);
  });
});

describe("the find box", () => {
  const find = (text: string) =>
    fireEvent.change(within(dialog()).getByRole("searchbox", { name: /find/i }), { target: { value: text } });

  it("narrows to rows whose receiver or station contains the text, in any case, and counts them", async () => {
    // spec: op-005 — a find that hides rows without saying how many is a failure case.
    await opened(/^RF/);
    expect(within(dialog()).getByText(/7 of 7 shown/i)).toBeInTheDocument();

    find("VENL");
    expect(firstColumn()).toEqual(["RF-02"]);
    expect(within(dialog()).getByText(/1 of 7 shown/i)).toBeInTheDocument();

    find("rf-05");
    expect(firstColumn()).toEqual(["RF-05"]);
  });

  it("finds aircraft by pseudonym", async () => {
    // spec: op-005
    await opened(/^Tracks/);

    find("char");
    expect(firstColumn()).toEqual(["AC-charlie"]);
    expect(within(dialog()).getByText(/1 of 4 shown/i)).toBeInTheDocument();
  });

  it("says when nothing matches", async () => {
    // spec: op-005
    await opened(/^RF/);

    find("zzz");
    expect(within(dialog()).getByText(/nothing in this table matches/i)).toBeInTheDocument();
    expect(within(dialog()).getByText(/0 of 7 shown/i)).toBeInTheDocument();
  });
});

describe("loading and failing", () => {
  it("says it is loading rather than drawing an empty table", async () => {
    // spec: op-005
    show(onScreen(), vi.fn(() => new Promise<OperationalPicture>(() => {})));
    fireEvent.click(viewAll());

    expect(within(dialog()).getByText(/loading/i)).toBeInTheDocument();
    expect(within(dialog()).queryByRole("table")).not.toBeInTheDocument();
  });

  it("says a failed load failed, shows none of the panel's rows, and tries again on request", async () => {
    // spec: op-005 — the named failure case: the panel's filtered rows under "all".
    const load = vi.fn().mockRejectedValueOnce(new Error("503")).mockResolvedValueOnce(unfiltered());
    show(onScreen(), load);
    fireEvent.click(viewAll());

    expect(await within(dialog()).findByText(/could not be loaded/i)).toBeInTheDocument();
    expect(within(dialog()).queryByRole("table")).not.toBeInTheDocument();
    expect(within(dialog()).queryByText("Eindhoven")).not.toBeInTheDocument();

    fireEvent.click(within(dialog()).getByRole("button", { name: /try again/i }));
    expect(await within(dialog()).findByRole("table")).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(2);
    expect(load).toHaveBeenLastCalledWith(420);
  });

  it("refuses an answer for another hour", async () => {
    // spec: op-005 — a table for a different hour from the one on screen.
    show(onScreen(), loader(unfiltered("421")));
    fireEvent.click(viewAll());

    expect(await within(dialog()).findByText(/could not be loaded/i)).toBeInTheDocument();
    expect(within(dialog()).queryByRole("table")).not.toBeInTheDocument();
  });

  it("refuses an answer that was filtered", async () => {
    // spec: op-005 — filtered rows shown as all.
    show(onScreen(), loader({ ...unfiltered(), view: { ...unfiltered().view, selected: "anomalous" } }));
    fireEvent.click(viewAll());

    expect(await within(dialog()).findByText(/could not be loaded/i)).toBeInTheDocument();
    expect(within(dialog()).queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("closing", () => {
  it("closes on Escape and returns focus to View all", async () => {
    // spec: op-005
    await opened();
    expect(dialog().contains(document.activeElement)).toBe(true);

    fireEvent.keyDown(dialog(), { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(viewAll()).toHaveFocus();
  });

  it("closes on the close button and leaves the panel on the tab it was opened from", async () => {
    // spec: op-005 — closing must not change the open tab.
    await opened(/^Tracks/);

    fireEvent.click(within(dialog()).getByRole("button", { name: /close/i }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Tracks/ })).toHaveAttribute("aria-selected", "true");
    expect(viewAll()).toHaveFocus();
  });
});

// ------------------------------------------------------------ through the app

const HOURS: SelectableHour[] = [
  { runId: 420, observedFrom: "2022-06-27T12:00:00Z", observedTo: "2022-06-27T12:15:00Z", examined: true },
];

const ok = (payload: unknown) => ({ ok: true, status: 200, json: async () => payload }) as Response;

let fetchMock: ReturnType<typeof vi.fn>;

// Serves run 420 under whatever view is asked for, as the server does.
const route = (input: RequestInfo | URL): Response => {
  const url = String(input);
  const path = url.split("?")[0];
  if (path === SELECTABLE_HOURS_PATH) return ok(HOURS);
  if (path === EVIDENCE_PATH) return ok(null);
  const asked = (/[?&]view=(\w+)/.exec(url)?.[1] ?? "all") as ViewSelection;
  return ok(asked === "all" ? unfiltered() : onScreen());
};

const pictureCalls = () => fetchMock.mock.calls.map((call) => String(call[0])).filter((url) => url.split("?")[0] === OPERATIONAL_PICTURE_PATH);

describe("through the app", () => {
  beforeEach(() => {
    fetchMock = vi.fn((input: RequestInfo | URL) => Promise.resolve(route(input)));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("reads the hour on screen, unfiltered, from the endpoint the panel reads", async () => {
    // spec: op-005 — following the newest hour, the table still names the hour on screen.
    render(<App />);
    await waitFor(() => expect(viewAll()).toBeEnabled());

    fireEvent.click(viewAll());

    expect(await screen.findByRole("dialog", { name: /run 420 · all 7 receivers/i })).toBeInTheDocument();
    expect(pictureCalls()).toContain(`${OPERATIONAL_PICTURE_PATH}?run=420&view=all`);
  });

  it("adds no navigation entry and changes no route", async () => {
    // spec: op-005, FR-701, nav-001 — the named failure case.
    render(<App />);
    await waitFor(() => expect(viewAll()).toBeEnabled());
    const hash = window.location.hash;

    fireEvent.click(viewAll());
    await screen.findByRole("dialog");

    expect(within(screen.getByRole("navigation", { name: /screens/i })).getAllByRole("link")).toHaveLength(3);
    expect(window.location.hash).toBe(hash);
  });

  it("leaves the view alone and the picture polling underneath", async () => {
    // spec: op-005 — closing it must not change the view.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<App />);
    await waitFor(() => expect(viewAll()).toBeEnabled());
    fireEvent.click(viewAll());
    await screen.findByRole("dialog");

    const before = pictureCalls().length;
    await vi.advanceTimersByTimeAsync(DEFAULT_POLL_INTERVAL_MS);
    await waitFor(() => expect(pictureCalls().length).toBeGreaterThan(before));
    expect(pictureCalls().at(-1)).toContain("view=anomalous");

    fireEvent.keyDown(dialog(), { key: "Escape" });
    expect(screen.getByRole("radio", { name: "Anomalous only" })).toBeChecked();
  });
});
