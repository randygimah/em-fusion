import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import operationalPictureMock from "../mocks/operationalPictureMock";
import OperationalPictureScreen from "../screens/operationalPicture";
import type {
  AircraftTrack,
  OperationalPicture,
  PictureView,
  RFSensor,
  SuppressedCounts,
  TimelineEvent,
  ViewSelection,
} from "../types/operationalPicture";

// spec: op-004 — the tabbed exception panel.
//
// The last step of the panel chain: api-016 gave an aircraft a state, api-007
// filtered on it and counted what it withheld, op-007 chose the view. This
// panel shows the three together, under the map. Most of what is tested here is
// about words that must match what is shown: a tab label naming a state its
// rows are not in, or a footer calling an unexamined hour's rows nominal, is
// the same lie in a smaller font.

const sensor = (id: string, health: string): RFSensor => ({
  id,
  stationName: `Station ${id}`,
  signalId: "GNSS-L1",
  health,
  lat: 51.0,
  lon: 7.0,
});

const track = (name: string, state: AircraftTrack["state"], altitudeFt: number | null = 30000): AircraftTrack => ({
  id: `opensky-replay:${name}`,
  name,
  altitudeFt,
  lat: 51.7912,
  lon: 10.3645,
  state,
});

const EVENT: TimelineEvent = {
  id: "SENSOR-FAULT:RF-01:2022-06-27T12:05:00Z",
  time: "2022-06-27T12:05:00Z",
  event: "possible_sensor_fault",
  source: "RF-01",
};

const NONE: SuppressedCounts = { rfSensors: 0, aircraftTracks: 0, timelineEvents: 0, interferenceZones: 0 };

const picture = (
  selected: ViewSelection,
  rows: Partial<Pick<OperationalPicture, "rfSensors" | "aircraftTracks" | "timelineEvents">>,
  suppressed: Partial<SuppressedCounts> = {},
  examined = true,
): OperationalPicture => {
  const view: PictureView = { selected, examined, suppressed: { ...NONE, ...suppressed } };
  return {
    ...operationalPictureMock,
    hypotheses: [],
    rfSensors: [],
    aircraftTracks: [],
    timelineEvents: [],
    ...rows,
    detectionSummary: examined ? operationalPictureMock.detectionSummary : null,
    view,
  };
};

// Run 420's shape under the default view: two receivers out of nominal, one
// interrupted aircraft, one conclusion; five receivers and 422 aircraft withheld.
const anomalous = () =>
  picture(
    "anomalous",
    {
      rfSensors: [sensor("RF-01", "fault"), sensor("RF-02", "deviating")],
      aircraftTracks: [track("AC-broken", "interrupted")],
      timelineEvents: [EVENT],
    },
    { rfSensors: 5, aircraftTracks: 422 },
  );

const show = (data: OperationalPicture) => render(<OperationalPictureScreen operationalPicture={data} />);

const tabNames = () => screen.getAllByRole("tab").map((tab) => tab.textContent);
const openTab = (name: RegExp) => fireEvent.click(screen.getByRole("tab", { name }));
const openPanel = () => within(screen.getByRole("tabpanel"));

describe("where the panel sits", () => {
  it("is one panel under the map and not in the rail", () => {
    // spec: op-004 (4) — WHERE, then WHAT IS EXCEPTIONAL, then WHAT IT MEANS.
    show(anomalous());

    const panel = screen.getByRole("region", { name: /exceptions/i });
    expect(within(panel).getByRole("tablist")).toBeInTheDocument();
    expect(within(screen.getByRole("complementary")).queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("lists the receivers once, in the RF tab, under the map", () => {
    // spec: op-004 (3) — one list rendered twice is the drift this item removes.
    // Re-pointed by map-001: the box above the panel is the map now, not a placeholder.
    show(anomalous());

    expect(screen.getAllByText("Station RF-01")).toHaveLength(1);
    expect(openPanel().getByText("Station RF-01")).toBeInTheDocument();
    expect(screen.getByTestId("map-view-stub")).toBeInTheDocument();
  });

  it("absorbs the timeline rather than sitting beside it", () => {
    // spec: op-004 (2), op-006
    show(anomalous());

    expect(screen.queryByRole("region", { name: /timeline/i })).not.toBeInTheDocument();
    openTab(/^Events/);
    expect(openPanel().getAllByRole("listitem")).toHaveLength(1);
  });
});

describe("the tab labels", () => {
  it("count the rows shown and name what they are under Anomalous only", () => {
    // spec: op-004 (1)
    show(anomalous());

    expect(tabNames()).toEqual(["RF (2 anomalous)", "Tracks (1 interrupted)", "Events (1)"]);
  });

  it("name the rows nominal under Nominal only", () => {
    // spec: op-004 (1) — "RF (5 anomalous)" over five nominal rows is the named failure case.
    show(
      picture(
        "nominal",
        {
          rfSensors: ["RF-03", "RF-04", "RF-05", "RF-06", "RF-07"].map((id) => sensor(id, "nominal")),
          aircraftTracks: [track("AC-fine", "nominal")],
        },
        { rfSensors: 2, aircraftTracks: 1, timelineEvents: 1, interferenceZones: 0 },
      ),
    );

    expect(tabNames()).toEqual(["RF (5 nominal)", "Tracks (1 nominal)", "Events (0)"]);
  });

  it("carry the count alone under All", () => {
    // spec: op-004 (1)
    show(
      picture("all", {
        rfSensors: [sensor("RF-01", "fault"), sensor("RF-03", "nominal")],
        aircraftTracks: [track("AC-broken", "interrupted"), track("AC-fine", "nominal")],
        timelineEvents: [EVENT],
      }),
    );

    expect(tabNames()).toEqual(["RF (2)", "Tracks (2)", "Events (1)"]);
  });

  it("name no state on an hour nobody examined, under any view", () => {
    // spec: op-004 (1), api-007 — nothing on it is anomalous or nominal.
    show(picture("anomalous", {}, { rfSensors: 7, aircraftTracks: 2 }, false));

    expect(tabNames()).toEqual(["RF (0)", "Tracks (0)", "Events (0)"]);
  });

  it("count exactly the rows beneath them", () => {
    // spec: op-004 — a tab count that disagrees with its rows is a failure case.
    show(anomalous());

    expect(openPanel().getAllByRole("row")).toHaveLength(1 + 2);
    openTab(/^Tracks/);
    expect(openPanel().getAllByRole("row")).toHaveLength(1 + 1);
  });
});

describe("the columns", () => {
  it("are the receiver's own fields and nothing the payload lacks", () => {
    // spec: op-004 (4) — Last Signal, Noise Floor and Severity have no producer.
    show(anomalous());

    expect(
      openPanel()
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Receiver", "Station", "Band", "State"]);
    for (const invented of [/last signal/i, /noise floor/i, /severity/i]) {
      expect(within(screen.getByRole("region", { name: /exceptions/i })).queryByText(invented)).not.toBeInTheDocument();
    }
    expect(openPanel().getByText("fault")).toBeInTheDocument();
  });

  it("show an aircraft's pseudonym, altitude, position and state", () => {
    // spec: op-004 (4), api-016
    show(anomalous());
    openTab(/^Tracks/);

    expect(
      openPanel()
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Aircraft", "Altitude", "Position", "State"]);
    expect(openPanel().getByText("AC-broken")).toBeInTheDocument();
    expect(openPanel().getByText("30,000 ft")).toBeInTheDocument();
    expect(openPanel().getByText(/51\.79/)).toBeInTheDocument();
    expect(openPanel().getByText("interrupted")).toBeInTheDocument();
  });

  it("say an absent altitude was not reported, never a dash", () => {
    // spec: op-004 (4) — 22.7% of positioned rows carry no altitude.
    show(picture("all", { aircraftTracks: [track("AC-low", "nominal", null)] }));
    openTab(/^Tracks/);

    expect(openPanel().getByText("not reported")).toBeInTheDocument();
    expect(openPanel().queryByText("—")).not.toBeInTheDocument();
  });
});

describe("an empty tab says what it found", () => {
  it("says no receiver is out of nominal, with no empty table", () => {
    // spec: op-004 (3) — a table with no rows states the finding not at all.
    show(picture("anomalous", {}, { rfSensors: 7, aircraftTracks: 410 }));

    expect(openPanel().getByText(/no receiver is out of nominal/i)).toBeInTheDocument();
    expect(openPanel().queryByRole("table")).not.toBeInTheDocument();
  });

  it("says no aircraft's reporting broke", () => {
    // spec: op-004 (3)
    show(picture("anomalous", {}, { rfSensors: 7, aircraftTracks: 410 }));
    openTab(/^Tracks/);

    expect(openPanel().getByText(/no aircraft's reporting broke/i)).toBeInTheDocument();
    expect(openPanel().queryByRole("table")).not.toBeInTheDocument();
  });

  it("says a quiet hour has no events", () => {
    // spec: op-004 (2), op-006
    show(picture("anomalous", {}, { rfSensors: 7 }));
    openTab(/^Events/);

    expect(openPanel().getByText(/no events in this hour/i)).toBeInTheDocument();
  });

  it("says an unexamined hour was not examined", () => {
    // spec: op-004, api-007
    show(picture("anomalous", {}, { rfSensors: 7, aircraftTracks: 2 }, false));

    expect(openPanel().getByText(/not been examined/i)).toBeInTheDocument();
    openTab(/^Tracks/);
    expect(openPanel().getByText(/not been examined/i)).toBeInTheDocument();
  });
});

describe("the footer", () => {
  it("counts the nominal rows Anomalous only withheld, per tab, from the metadata", () => {
    // spec: op-004 (2), FR-809 — the rows never arrived, so they cannot be counted.
    show(anomalous());

    expect(openPanel().getByText(/\+5 nominal hidden/i)).toBeInTheDocument();
    openTab(/^Tracks/);
    expect(openPanel().getByText(/\+422 nominal hidden/i)).toBeInTheDocument();
  });

  it("names what Nominal only withheld by what it is", () => {
    // spec: op-004 (2)
    show(picture("nominal", {}, { rfSensors: 2, aircraftTracks: 10, timelineEvents: 1, interferenceZones: 0 }));

    expect(openPanel().getByText(/\+2 anomalous hidden/i)).toBeInTheDocument();
    openTab(/^Tracks/);
    expect(openPanel().getByText(/\+10 interrupted hidden/i)).toBeInTheDocument();
    openTab(/^Events/);
    expect(openPanel().getByText(/\+1 conclusion hidden/i)).toBeInTheDocument();
  });

  it("never calls an unexamined hour's withheld rows nominal", () => {
    // spec: op-004 (2) — the named failure case.
    show(picture("anomalous", {}, { rfSensors: 7, aircraftTracks: 2 }, false));

    expect(openPanel().getByText(/\+7 receivers hidden/i)).toBeInTheDocument();
    expect(openPanel().queryByText(/nominal hidden/i)).not.toBeInTheDocument();
  });

  it("says the view hides nothing when it withheld nothing", () => {
    // spec: op-004 (2)
    show(picture("all", { rfSensors: [sensor("RF-01", "nominal")] }));

    expect(openPanel().getByText(/this view hides nothing/i)).toBeInTheDocument();
  });

  it("offers View all disabled, with the reason", () => {
    // spec: op-004 (2), op-005 — decided 2026-10-06, as RESET and REPLAY are.
    show(anomalous());

    expect(screen.getByRole("button", { name: /view all/i })).toBeDisabled();
    expect(screen.getByText(/drill-down tables are not built yet/i)).toBeInTheDocument();
  });
});

describe("the open tab", () => {
  it("opens on RF", () => {
    // spec: op-004 (5)
    show(anomalous());

    expect(screen.getByRole("tab", { name: /^RF/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: /^RF/ })).toBeInTheDocument();
    // Added after the mutation pass, where marking every tab selected survived:
    // a screen reader would announce all three as the open one.
    expect(screen.getByRole("tab", { name: /^Tracks/ })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: /^Events/ })).toHaveAttribute("aria-selected", "false");
  });

  it("stays open when the next poll, hour or view arrives", () => {
    // spec: op-004 (5) — the named failure case: the open tab lost on the next poll.
    const { rerender } = show(anomalous());
    openTab(/^Events/);

    rerender(<OperationalPictureScreen operationalPicture={{ ...anomalous(), scenario: { id: "207", name: "Run 207", dataMode: "mixed" } }} />);
    expect(screen.getByRole("tab", { name: /^Events/ })).toHaveAttribute("aria-selected", "true");

    rerender(<OperationalPictureScreen operationalPicture={picture("all", { timelineEvents: [EVENT] })} />);
    expect(screen.getByRole("tab", { name: /^Events/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: /^Events/ })).toBeInTheDocument();
  });
});
