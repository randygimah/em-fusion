import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { DEFAULT_POLL_INTERVAL_MS, EVIDENCE_PATH, fetchOperationalPicture, OPERATIONAL_PICTURE_PATH, SELECTABLE_HOURS_PATH } from "../lib/api";
import operationalPictureMock from "../mocks/operationalPictureMock";
import OperationalPictureScreen from "../screens/operationalPicture";
import type { OperationalPicture, PictureView, RFSensor, SelectableHour, ViewSelection } from "../types/operationalPicture";

// spec: op-007 — the Anomalous only / Nominal only / All control.
//
// The server filters (api-007), so the rows a view withholds never arrive. Two
// things follow, and most of this file is about them: whatever the view empties
// has to say what it withheld, from the server's counts and never from the rows;
// and between a click and its answer the rows on screen belong to the previous
// view, so they are labelled by the view they were served under.

const RECEIVER: RFSensor = {
  id: "RF-01",
  stationName: "Station One",
  signalId: "GNSS-L1",
  health: "fault",
  lat: 51.0,
  lon: 7.0,
};

const viewOf = (selected: ViewSelection, overrides: Partial<PictureView> = {}): PictureView => ({
  selected,
  examined: true,
  suppressed: { rfSensors: 0, aircraftTracks: 0, timelineEvents: 0, interferenceZones: 0 },
  ...overrides,
});

const served = (view: PictureView, rows: Partial<OperationalPicture> = {}): OperationalPicture => ({
  ...operationalPictureMock,
  rfSensors: [],
  aircraftTracks: [],
  timelineEvents: [],
  ...rows,
  detectionSummary: view.examined ? operationalPictureMock.detectionSummary : null,
  view,
});

const renderScreen = (picture: OperationalPicture, selectedView: ViewSelection = picture.view.selected, onSelectView = vi.fn()) => {
  render(
    <OperationalPictureScreen
      onSelectView={onSelectView}
      operationalPicture={picture}
      selectedView={selectedView}
    />,
  );
  return onSelectView;
};

// op-004 moved the receiver grid and the timeline into the exception panel's
// RF and Events tabs. Re-pointed there, assertions kept: each helper opens its
// tab and answers the tab's panel.
const openTab = (name: RegExp) => {
  fireEvent.click(screen.getByRole("tab", { name }));
  return screen.getByRole("tabpanel", { name });
};
const receiverGrid = () => openTab(/^RF/);
const timeline = () => openTab(/^Events/);

describe("the control", () => {
  it("offers the three views and marks the selected one", () => {
    // spec: op-007, FR-716
    renderScreen(served(viewOf("anomalous")));
    const group = screen.getByRole("radiogroup", { name: /view/i });

    expect(
      within(group)
        .getAllByRole("radio")
        .map((radio) => radio.textContent),
    ).toEqual(["Anomalous only", "Nominal only", "All"]);
    expect(within(group).getByRole("radio", { name: "Anomalous only" })).toBeChecked();
    expect(within(group).getByRole("radio", { name: "All" })).not.toBeChecked();
  });

  it("reports the view chosen", () => {
    // spec: op-007
    const onSelectView = renderScreen(served(viewOf("anomalous")));

    fireEvent.click(screen.getByRole("radio", { name: "Nominal only" }));

    expect(onSelectView).toHaveBeenCalledWith("nominal");
  });
});

describe("rows are labelled by the view they were served under", () => {
  it("names the served view when the selection and the payload agree", () => {
    // spec: op-007
    renderScreen(served(viewOf("all")), "all");

    expect(screen.getByText(/showing all/i)).toBeInTheDocument();
    expect(screen.queryByText(/switching/i)).not.toBeInTheDocument();
  });

  it("marks the change pending until the answer arrives, naming what is still shown", () => {
    // spec: op-007 — the named failure case: rows from the previous view
    // labelled with the new one.
    renderScreen(served(viewOf("anomalous")), "all");

    expect(screen.getByText(/switching to all/i)).toBeInTheDocument();
    expect(screen.getByText(/showing anomalous only/i)).toBeInTheDocument();
    expect(screen.queryByText(/showing all/i)).not.toBeInTheDocument();
  });
});

describe("what the receiver grid says when the view empties it", () => {
  it("says no receiver is out of nominal, and how many nominal ones the view hides", () => {
    // spec: op-007 — a quiet hour under the default view. An empty grid with
    // no sentence is the named failure case.
    renderScreen(served(viewOf("anomalous", { suppressed: { rfSensors: 7, aircraftTracks: 410, timelineEvents: 0, interferenceZones: 0 } })));

    expect(within(receiverGrid()).getByText(/no receiver is out of nominal/i)).toBeInTheDocument();
    expect(within(receiverGrid()).getByText(/7 nominal hidden by this view/i)).toBeInTheDocument();
  });

  it("says no receiver is nominal under the nominal view, and how many the view hides", () => {
    // spec: op-007
    renderScreen(served(viewOf("nominal", { suppressed: { rfSensors: 2, aircraftTracks: 0, timelineEvents: 0, interferenceZones: 0 } })));

    expect(within(receiverGrid()).getByText(/no receiver is nominal/i)).toBeInTheDocument();
    // Worded "2 out of nominal" until op-004's amendment (2), which names the
    // withheld rows by what they are: under Nominal only, anomalous.
    expect(within(receiverGrid()).getByText(/2 anomalous hidden by this view/i)).toBeInTheDocument();
  });

  it("states what the view hides beside the rows it served", () => {
    // spec: op-007, FR-809 — the count is the server's, never the rows': here
    // one receiver arrived and five did not.
    renderScreen(served(viewOf("anomalous", { suppressed: { rfSensors: 5, aircraftTracks: 0, timelineEvents: 0, interferenceZones: 0 } }), { rfSensors: [RECEIVER] }));

    expect(within(receiverGrid()).getByText(RECEIVER.stationName)).toBeInTheDocument();
    expect(within(receiverGrid()).getByText(/5 nominal hidden by this view/i)).toBeInTheDocument();
  });

  it("says nothing is hidden-and-clean on an hour nobody examined", () => {
    // spec: op-007, api-007 — seven withheld rows on an unexamined hour are
    // not seven nominal receivers.
    renderScreen(served(viewOf("anomalous", { examined: false, suppressed: { rfSensors: 7, aircraftTracks: 2, timelineEvents: 0, interferenceZones: 0 } })));

    expect(within(receiverGrid()).getByText(/not been examined/i)).toBeInTheDocument();
    expect(within(receiverGrid()).queryByText(/nominal hidden/i)).not.toBeInTheDocument();
    expect(within(receiverGrid()).queryByText(/no receiver is out of nominal/i)).not.toBeInTheDocument();
  });
});

describe("what the timeline says when the view empties it", () => {
  it("counts the conclusions the view hides rather than saying there are none", () => {
    // spec: op-007 — the named failure case: "no events" while one is withheld.
    renderScreen(served(viewOf("nominal", { suppressed: { rfSensors: 0, aircraftTracks: 0, timelineEvents: 1, interferenceZones: 0 } })));

    expect(within(timeline()).getByText(/1 conclusion hidden by this view/i)).toBeInTheDocument();
    expect(within(timeline()).queryByText(/no events in this hour/i)).not.toBeInTheDocument();
  });

  it("pluralises the count", () => {
    // spec: op-007
    renderScreen(served(viewOf("nominal", { suppressed: { rfSensors: 0, aircraftTracks: 0, timelineEvents: 3, interferenceZones: 0 } })));

    expect(within(timeline()).getByText(/3 conclusions hidden by this view/i)).toBeInTheDocument();
  });

  it("reads a quiet examined hour as quiet in both places", () => {
    // spec: op-007, op-006 — no conclusion withheld and none reached, while
    // the view hides the seven nominal receivers: the timeline keeps its
    // sentence and claims nothing is hidden.
    renderScreen(served(viewOf("anomalous", { suppressed: { rfSensors: 7, aircraftTracks: 410, timelineEvents: 0, interferenceZones: 0 } })));

    expect(within(timeline()).getByText(/no events in this hour/i)).toBeInTheDocument();
    expect(within(timeline()).queryByText(/hidden by this view/i)).not.toBeInTheDocument();
    expect(within(receiverGrid()).getByText(/7 nominal hidden by this view/i)).toBeInTheDocument();
  });

  it("says an unexamined hour was not examined, under every view", () => {
    // spec: op-007, api-012 — "no events" on an hour nobody looked at is a
    // clean bill of health nothing issued.
    for (const selected of ["anomalous", "nominal", "all"] as const) {
      renderScreen(served(viewOf(selected, { examined: false })));

      expect(within(timeline()).getByText(/not been examined/i)).toBeInTheDocument();
      expect(within(timeline()).queryByText(/no events in this hour/i)).not.toBeInTheDocument();
      cleanup();
    }
  });
});

describe("the fetcher sends the view", () => {
  it("adds the view to the newest hour and to a pinned one", async () => {
    // spec: op-007, api-007
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => served(viewOf("all")) }) as Response);
    vi.stubGlobal("fetch", fetchMock);

    await fetchOperationalPicture("", null, "all");
    await fetchOperationalPicture("", 207, "nominal");

    expect(fetchMock.mock.calls.map((call) => String((call as unknown[])[0]))).toEqual([
      `${OPERATIONAL_PICTURE_PATH}?view=all`,
      `${OPERATIONAL_PICTURE_PATH}?run=207&view=nominal`,
    ]);
    vi.unstubAllGlobals();
  });
});

// ------------------------------------------------------------ through the app

const HOURS: SelectableHour[] = [
  { runId: 420, observedFrom: "2022-06-27T12:00:00Z", observedTo: "2022-06-27T12:15:00Z", examined: true },
  { runId: 207, observedFrom: "2022-06-27T09:30:00Z", observedTo: "2022-06-27T09:45:00Z", examined: true },
];

const ok = (payload: unknown) => ({ ok: true, status: 200, json: async () => payload }) as Response;

let fetchMock: ReturnType<typeof vi.fn>;

// Answers each picture request under the view it asked for, as the server does.
const route = (input: RequestInfo | URL): Response => {
  const url = String(input);
  const path = url.split("?")[0];
  if (path === SELECTABLE_HOURS_PATH) return ok(HOURS);
  if (path === EVIDENCE_PATH) return ok(null);
  const asked = /[?&]view=(\w+)/.exec(url)?.[1] ?? "all";
  return ok(served(viewOf(asked as ViewSelection)));
};

const pictureCalls = () => fetchMock.mock.calls.map((call) => String(call[0])).filter((url) => url.split("?")[0] === OPERATIONAL_PICTURE_PATH);

const chooseView = (name: string) => fireEvent.click(screen.getByRole("radio", { name }));

describe("the selection, through the app", () => {
  beforeEach(() => {
    fetchMock = vi.fn((input: RequestInfo | URL) => Promise.resolve(route(input)));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("starts at anomalous only and asks the server for it", async () => {
    // spec: op-007, US-A1
    render(<App />);

    await waitFor(() => expect(pictureCalls().length).toBeGreaterThan(0));
    expect(pictureCalls()[0]).toContain("view=anomalous");
    expect(screen.getByRole("radio", { name: "Anomalous only" })).toBeChecked();
  });

  it("asks at once for a view that is chosen, without waiting for the next tick", async () => {
    // spec: op-007
    render(<App />);
    await waitFor(() => expect(pictureCalls().length).toBeGreaterThan(0));

    chooseView("All");

    await waitFor(() => expect(pictureCalls().at(-1)).toContain("view=all"));
    expect(await screen.findByText(/showing all/i)).toBeInTheDocument();
  });

  it("keeps the view on the next poll rather than resetting to the default", async () => {
    // spec: op-007 — the named failure case.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<App />);
    await waitFor(() => expect(pictureCalls().length).toBeGreaterThan(0));
    chooseView("Nominal only");
    await waitFor(() => expect(pictureCalls().at(-1)).toContain("view=nominal"));

    const before = pictureCalls().length;
    await vi.advanceTimersByTimeAsync(DEFAULT_POLL_INTERVAL_MS);

    await waitFor(() => expect(pictureCalls().length).toBeGreaterThan(before));
    expect(pictureCalls().at(-1)).toContain("view=nominal");
  });

  it("keeps the view when an hour is pinned, and the hour when the view changes", async () => {
    // spec: op-007, op-009 — the hour and the view are independent.
    render(<App />);
    await screen.findByRole("option", { name: /207/ });
    chooseView("All");
    await waitFor(() => expect(pictureCalls().at(-1)).toContain("view=all"));

    fireEvent.change(screen.getByRole("combobox", { name: /hour/i }), { target: { value: "207" } });
    await waitFor(() => expect(pictureCalls().at(-1)).toContain("run=207"));
    expect(pictureCalls().at(-1)).toContain("view=all");

    chooseView("Nominal only");
    await waitFor(() => expect(pictureCalls().at(-1)).toContain("view=nominal"));
    expect(pictureCalls().at(-1)).toContain("run=207");
  });

  it("starts at anomalous only again on the next visit", async () => {
    // spec: op-007, US-A1 — not stored across a reload, so a visit never
    // opens on a view somebody else left.
    const first = render(<App />);
    await waitFor(() => expect(pictureCalls().length).toBeGreaterThan(0));
    chooseView("All");
    await waitFor(() => expect(pictureCalls().at(-1)).toContain("view=all"));
    first.unmount();
    fetchMock.mockClear();

    render(<App />);

    await waitFor(() => expect(pictureCalls().length).toBeGreaterThan(0));
    expect(pictureCalls()[0]).toContain("view=anomalous");
  });
});
