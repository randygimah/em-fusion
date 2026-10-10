import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EmLevel } from "../components/em/EmLevel";
import OperationalPictureScreen from "../screens/operationalPicture";
import operationalPictureMock from "../mocks/operationalPictureMock";
import type { DetectionCount, Level, OperationalPicture } from "../types/operationalPicture";

// spec: ui-001 — one primitive for every level, and a RUNTIME refusal.
//
// The contract already declares Level as exactly Low | Medium | High, so
// TypeScript refuses a number at the call site. That is not the guard: the
// payload is CAST from JSON, so a backend regression delivers 87 at runtime
// with nothing between it and the screen. This is where that is caught.
//
// What the refusal does was decided rather than read off the item, whose words
// are "renders nothing and surfaces a development-time error":
//   - it renders no value, so no number reaches an analyst in any form;
//   - it keeps the surrounding label, so the row reads visibly incomplete
//     rather than silently absent;
//   - it reports the value through console.error, whose audience is the
//     developer who caused it — an invalid level is not a state the system is
//     allowed to be in, so there is nothing honest to say to an analyst;
//   - it never throws, because a primitive that raises during render takes down
//     a whole screen over one bad badge.

const LEVELS: Level[] = ["Low", "Medium", "High"];

// Every shape a defect upstream could deliver. The decimal and the percent are
// the item's own named failure case; the empty string and null are what a
// missing field becomes after a cast.
const REFUSED = [0.87, 87, "87%", "0.87", "", "high", "HIGH", "Critical", null, undefined];

const count = (over: Partial<DetectionCount> = {}): DetectionCount => ({
  ruleId: "FUSION-SPATIAL",
  findingType: "possible_interference_zone",
  kind: "reportable",
  count: 1,
  unavailable: null,
  ...over,
});

const picture = (over: Partial<OperationalPicture> = {}): OperationalPicture => ({
  ...operationalPictureMock,
  scenario: { id: "207", name: "Run 207", dataMode: "mixed" },
  hypotheses: [],
  rfSensors: [],
  timelineEvents: [],
  aircraftTracks: [],
  detectionSummary: {
    anomalyLevel: "High",
    signalIntegrity: "Medium",
    counts: [count()],
  },
  ...over,
});

let errors: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  errors = vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the level primitive", () => {
  it.each(LEVELS)("renders %s", (level) => {
    render(<EmLevel label="Anomaly level" value={level} />);

    expect(screen.getByText(level)).toBeInTheDocument();
    expect(errors).not.toHaveBeenCalled();
  });

  it.each(REFUSED)("refuses %s without rendering it", (value) => {
    render(<EmLevel label="Anomaly level" value={value as unknown as Level} />);

    // Nothing resembling the offending value reaches the DOM.
    expect(document.body.textContent ?? "").not.toMatch(/\d/);
    expect(document.body.textContent ?? "").not.toMatch(/%/);
  });

  it.each(REFUSED)("keeps the label when refusing %s", (value) => {
    // Visibly incomplete rather than silently absent: a row with a name and no
    // value reads as a fault, which is what it is.
    render(<EmLevel label="Anomaly level" value={value as unknown as Level} />);

    expect(screen.getByText(/anomaly level/i)).toBeInTheDocument();
  });

  it.each(REFUSED)("reports %s to the developer", (value) => {
    render(<EmLevel label="Anomaly level" value={value as unknown as Level} />);

    expect(errors).toHaveBeenCalled();
    expect(String(errors.mock.calls[0])).toContain("Anomaly level");
  });

  it("never throws, whatever it is given", () => {
    // A primitive that raises during render takes down a whole screen over one
    // bad badge, which is a larger failure than the one being prevented.
    for (const value of REFUSED) {
      expect(() => render(<EmLevel label="L" value={value as unknown as Level} />)).not.toThrow();
    }
  });

  it("renders no typed absence of its own", () => {
    // spec: ui-001, op-003 — a missing count and a rule that does not exist are
    // both dashes, and both are facts about a producer rather than levels.
    // Routing them through here would make "no rule exists" and "the backend
    // sent a number" render identically.
    render(<EmLevel label="Anomaly level" value={"—" as unknown as Level} />);

    expect(screen.queryByText("—")).not.toBeInTheDocument();
    expect(errors).toHaveBeenCalled();
  });
});

describe("every level on the screen goes through it", () => {
  // Asserted behaviourally rather than by scanning the source: a call site that
  // bypassed the primitive would render the number, so feeding each of the four
  // fields a bad value and finding no digit on screen proves all four are
  // routed. A source scan would prove only the spellings I thought of.
  it("refuses a bad anomaly level", () => {
    render(
      <OperationalPictureScreen
        operationalPicture={picture({
          detectionSummary: { anomalyLevel: 87 as unknown as Level, signalIntegrity: "Medium", counts: [] },
        })}
      />,
    );

    expect(screen.queryByText(/87/)).not.toBeInTheDocument();
    expect(errors).toHaveBeenCalled();
  });

  it("refuses a bad signal integrity", () => {
    render(
      <OperationalPictureScreen
        operationalPicture={picture({
          detectionSummary: { anomalyLevel: "High", signalIntegrity: 0.92 as unknown as Level, counts: [] },
        })}
      />,
    );

    expect(screen.queryByText(/0\.92/)).not.toBeInTheDocument();
    expect(errors).toHaveBeenCalled();
  });

  // api-019 removed the card's severity, which nothing produced; confidence is
  // the card's one level now.
  it("refuses a bad hypothesis confidence", () => {
    render(
      <OperationalPictureScreen
        operationalPicture={picture({
          hypotheses: [
            {
              id: 41,
              bundleId: 7,
              runId: 480,
              hypothesisTitle: "Possible localised interference",
              confidence: 74.2 as unknown as Level,
              status: "New",
              generator: "hosted",
              requestedGenerator: "hosted",
              fellBack: false,
              anomalyType: "possible_interference_zone",
              ruleId: "FUSION-SPATIAL",
              subject: "RF-04",
              windowStart: "2022-06-27T12:31:00Z",
              windowEnd: "2022-06-27T12:36:00Z",
              latestVerdict: null,
            },
          ],
        })}
      />,
    );

    expect(screen.queryByText(/74\.2/)).not.toBeInTheDocument();
    expect(errors).toHaveBeenCalled();
  });

  it("renders the good levels it is given", () => {
    render(<OperationalPictureScreen operationalPicture={picture()} />);

    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("Medium")).toBeInTheDocument();
    expect(errors).not.toHaveBeenCalled();
  });
});
