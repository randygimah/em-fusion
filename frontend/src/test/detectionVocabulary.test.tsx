import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { REPORTABLE_COPY, findingLabel } from "../lib/detectionVocabulary";
import OperationalPictureScreen from "../screens/operationalPicture";
import operationalPictureMock from "../mocks/operationalPictureMock";
import type {
  DetectionCount,
  OperationalPicture,
  ReportableFindingType,
  TimelineEvent,
} from "../types/operationalPicture";

// spec: op-003, op-006 — the detection vocabulary, in the two panels that carry
// it.
//
// The payload sends each finding type VERBATIM, which is deliberate: the
// backend sends facts and never prose, so the screen composes the wording where
// the rest of this screen's wording lives. The screen never composed any, so
// `possible_interference_zone` went to the surface.
//
// The reason these two items are one piece of work is that the timeline's
// `event` field carries the same verbatim type. Copy written inside the summary
// panel would need a second copy in the strip, and one conclusion would then
// have two sentences on one screen with nothing to notice the drift — so the
// copy is one module and both panels read it, asserted below.

const TYPES: ReportableFindingType[] = [
  "possible_interference_zone",
  "possible_sensor_fault",
  "possible_data_source_issue",
];

const INSTANT = "2022-06-27T12:45:52+00:00";

const count = (over: Partial<DetectionCount> = {}): DetectionCount => ({
  ruleId: "FUSION-SPATIAL",
  findingType: "possible_interference_zone",
  kind: "reportable",
  count: 1,
  unavailable: null,
  ...over,
});

const event = (over: Partial<TimelineEvent> = {}): TimelineEvent => ({
  id: "FUSION-SPATIAL:RF-04:2022-06-27T12:45:52+00:00",
  time: INSTANT,
  event: "possible_interference_zone",
  source: "RF-04",
  ...over,
});

const picture = (over: Partial<OperationalPicture> = {}): OperationalPicture => ({
  ...operationalPictureMock,
  scenario: { id: "207", name: "Run 207", dataMode: "mixed" },
  hypotheses: [],
  rfSensors: [],
  aircraftTracks: [],
  timelineEvents: [],
  detectionSummary: { anomalyLevel: "High", signalIntegrity: "Medium", counts: [count()] },
  ...over,
});

const summary = () => within(screen.getByRole("region", { name: /detection summary/i }));
const timeline = () => within(screen.getByRole("region", { name: /timeline/i }));

describe("the copy module", () => {
  it("covers every type the contract can name", () => {
    // A copy map that misses one prints the raw token, which is the defect
    // being fixed — so the map's keys are the union, exactly.
    expect(new Set(Object.keys(REPORTABLE_COPY))).toEqual(new Set(TYPES));
  });

  it.each(TYPES)("gives %s a sentence rather than the token", (type) => {
    const label = findingLabel(type);

    expect(label).not.toContain("_");
    expect(label).not.toEqual(type);
    expect(label.length).toBeGreaterThan(3);
  });

  it("names an unrecognised type rather than printing it or dropping it", () => {
    // A type outside the union means a rule exists that this screen has no copy
    // for. Printing it is the defect; dropping it hides a built detector.
    const label = findingLabel("possible_new_thing");

    expect(label).not.toContain("possible_new_thing");
    expect(label).toMatch(/unrecognised|unknown finding/i);
  });
});

describe("the detection summary panel", () => {
  it.each(TYPES)("renders %s as its sentence", (type) => {
    render(
      <OperationalPictureScreen
        operationalPicture={picture({
          detectionSummary: {
            anomalyLevel: "High",
            signalIntegrity: "Medium",
            counts: [count({ findingType: type })],
          },
        })}
      />,
    );

    expect(summary().getByText(findingLabel(type))).toBeInTheDocument();
  });

  it("prints no raw finding type anywhere on the screen", () => {
    // The defect, asserted over the whole screen rather than over the one panel
    // somebody thought of — which is how `possible_interference_zone` reached
    // the timeline as well as the summary.
    render(
      <OperationalPictureScreen
        operationalPicture={picture({
          detectionSummary: {
            anomalyLevel: "High",
            signalIntegrity: "Medium",
            counts: TYPES.map((findingType) => count({ findingType })),
          },
          timelineEvents: TYPES.map((type) => event({ event: type, id: type })),
        })}
      />,
    );

    for (const type of TYPES) {
      expect(screen.queryByText(type)).not.toBeInTheDocument();
    }
  });

  it("renders a real zero for a built rule that found nothing", () => {
    render(
      <OperationalPictureScreen
        operationalPicture={picture({
          detectionSummary: {
            anomalyLevel: "Low",
            signalIntegrity: "Low",
            counts: [count({ findingType: "possible_sensor_fault", count: 0 })],
          },
        })}
      />,
    );

    expect(summary().getByText("0")).toBeInTheDocument();
  });

  it.each(["rule-not-built", "not-persisted"] as const)(
    "renders a dash and never a zero for %s",
    (unavailable) => {
      // A zero for a rule that does not exist quotes the absence of a rule as
      // the accuracy of one.
      render(
        <OperationalPictureScreen
          operationalPicture={picture({
            detectionSummary: {
              anomalyLevel: "Low",
              signalIntegrity: "Low",
              counts: [count({ count: null, unavailable })],
            },
          })}
        />,
      );

      expect(summary().getByText("—")).toBeInTheDocument();
      expect(summary().queryByText("0")).not.toBeInTheDocument();
    },
  );

  it("lists no intermediate finding as an anomaly count", () => {
    // A quiet run genuinely holds ~138 of them, and an analyst shown those as
    // anomaly counts reads a correct non-detection as a storm.
    render(
      <OperationalPictureScreen
        operationalPicture={picture({
          detectionSummary: {
            anomalyLevel: "Low",
            signalIntegrity: "Low",
            counts: [
              count(),
              count({ ruleId: "TRACK-GAP", findingType: "track_continuity_gap", kind: "intermediate", count: 138 }),
            ],
          },
        })}
      />,
    );

    expect(summary().queryByText("138")).not.toBeInTheDocument();
  });
});

describe("the timeline strip", () => {
  it("renders an event with its sentence, its time and its source", () => {
    render(<OperationalPictureScreen operationalPicture={picture({ timelineEvents: [event()] })} />);

    expect(timeline().getByText(findingLabel("possible_interference_zone"))).toBeInTheDocument();
    expect(timeline().getByText(/RF-04/)).toBeInTheDocument();
  });

  it("renders the simulated instant and never a relative or local time", () => {
    // The events are instants in a replayed 2022 hour and the run was generated
    // in 2026. A relative time, or one formatted against the viewer's clock,
    // states the wrong thing — anom-009's recorded mistake.
    render(<OperationalPictureScreen operationalPicture={picture({ timelineEvents: [event()] })} />);

    const text = timeline().getByText(/2022-06-27/).textContent ?? "";
    expect(text).toContain("12:45");
    expect(text).not.toMatch(/ago|just now|yesterday/i);
  });

  it("orders by event time whatever order the payload used", () => {
    // A guard rather than a correction: api-012 already serves them oldest
    // first, so this is what stops the strip's order silently following the
    // backend's. Supplied out of order directly, which is the only way the
    // item's own failure case is testable.
    const first = event({ id: "a", time: "2022-06-27T12:10:00+00:00", source: "RF-01" });
    const second = event({ id: "b", time: "2022-06-27T12:20:00+00:00", source: "RF-02" });
    const third = event({ id: "c", time: "2022-06-27T12:30:00+00:00", source: "RF-03" });
    render(
      <OperationalPictureScreen
        operationalPicture={picture({ timelineEvents: [third, first, second] })}
      />,
    );

    const rendered = timeline().getAllByRole("listitem").map((node) => node.textContent ?? "");
    expect(rendered[0]).toContain("RF-01");
    expect(rendered[1]).toContain("RF-02");
    expect(rendered[2]).toContain("RF-03");
  });

  it("says in words that nothing happened rather than rendering a bare strip", () => {
    render(<OperationalPictureScreen operationalPicture={picture({ timelineEvents: [] })} />);

    expect(timeline().getByText(/no events/i)).toBeInTheDocument();
  });

  it("words a conclusion the same way the summary does", () => {
    // The whole reason these two items are one piece of work: two copies of the
    // wording would give one conclusion two sentences, and nothing would notice
    // when they drifted.
    render(
      <OperationalPictureScreen
        operationalPicture={picture({
          detectionSummary: {
            anomalyLevel: "High",
            signalIntegrity: "Medium",
            counts: [count({ findingType: "possible_sensor_fault" })],
          },
          timelineEvents: [event({ event: "possible_sensor_fault" })],
        })}
      />,
    );

    const wording = findingLabel("possible_sensor_fault");
    expect(summary().getByText(wording)).toBeInTheDocument();
    expect(timeline().getByText(wording)).toBeInTheDocument();
  });
});
