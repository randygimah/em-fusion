import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import operationalPicture from "../mocks/operationalPictureMock";
import OperationalPictureScreen from "../screens/operationalPicture";
import type { DetectionSummary, OperationalPicture } from "../types/operationalPicture";

const renderScreen = (picture: OperationalPicture = operationalPicture) =>
  render(<OperationalPictureScreen operationalPicture={picture} />);

// The value beside a label in a definition list, read the way a person reads
// it: find the term, take the description next to it.
const valueFor = (label: string): string =>
  screen.getByText(label).parentElement?.querySelector("dd")?.textContent ?? "";

describe("OperationalPictureScreen", () => {
  it("renders the operational picture screen with correct data", () => {
    renderScreen();

    expect(screen.getByText(operationalPicture.rfSensors[0].stationName)).toBeInTheDocument();
  });

  it("renders the anomaly level as a band rather than a percentage", () => {
    // spec: api-002, FR-715, AC-11 — this screen rendered `74.2%` before the
    // endpoint existed, which is the violation the contract change removes.
    renderScreen();

    expect(valueFor("Anomaly Level")).toBe(operationalPicture.detectionSummary?.anomalyLevel);
  });

  it("renders signal integrity as a band rather than a decimal", () => {
    // spec: api-002, FR-715, AC-11 — previously `0.92`, via toFixed(2).
    renderScreen();

    expect(valueFor("Signal Integrity")).toBe(
      operationalPicture.detectionSummary?.signalIntegrity,
    );
  });

  it("renders no percentage anywhere on the screen", () => {
    // spec: api-002, AC-11 — the acceptance criterion is about the whole
    // screen, not one component, so it is asserted over the whole render.
    renderScreen();

    expect(document.body.textContent).not.toMatch(/%/);
  });

  it("renders confidence in the Low, Medium, High vocabulary and nothing else", () => {
    // spec: api-002, ui-001 — the mock carried "Medium Confidence", which is
    // not a value the contract admits and not one a component can band.
    renderScreen();

    expect(valueFor("Confidence")).toMatch(/^(Low|Medium|High)$/);
  });

  it("tells an unexamined run from a clean one in words, not by a dash", () => {
    // spec: api-012, anom-008 — the pair the whole item is about, asserted in
    // both directions in one test on purpose. The dash was the defect and not
    // the fix: a reader cannot tell "—" meaning *nothing to report* from "—"
    // meaning *nobody looked*, and the second is a broken pipeline. Written as
    // two tests, the clean half asserts only that a sentence is absent, which
    // is true of a screen that never says it — the vacuous pass api-011 was
    // caught by. One test over both payloads cannot pass that way.
    const clean = {
      anomalyLevel: "Low",
      signalIntegrity: "High",
      counts: [
        {
          ruleId: "SENSOR-FAULT",
          findingType: "possible_sensor_fault",
          kind: "reportable",
          count: 0,
          unavailable: null,
        },
      ],
    } satisfies DetectionSummary;

    const unexamined = render(
      <OperationalPictureScreen
        operationalPicture={{ ...operationalPicture, detectionSummary: null }}
      />,
    );
    expect(screen.getByText(/no detection pass/i)).toBeInTheDocument();
    unexamined.unmount();

    renderScreen({ ...operationalPicture, detectionSummary: clean });
    expect(screen.queryByText(/no detection pass/i)).not.toBeInTheDocument();
    expect(valueFor("Anomaly Level")).toBe("Low");
  });

  it("counts the reportable rules and not the intermediate ones", () => {
    // spec: api-012, anom-010 — a quiet run genuinely holds about 138 track
    // discontinuities. Shown as an anomaly count, a correct non-detection
    // reads as a storm, which is why the payload labels each producer's kind.
    renderScreen({
      ...operationalPicture,
      detectionSummary: {
        anomalyLevel: "High",
        signalIntegrity: "Low",
        counts: [
          {
            ruleId: "SENSOR-FAULT",
            findingType: "possible_sensor_fault",
            kind: "reportable",
            count: 2,
            unavailable: null,
          },
          {
            ruleId: "TRACK-GAP",
            findingType: "track_continuity_gap",
            kind: "intermediate",
            count: 138,
            unavailable: null,
          },
        ],
      },
    });

    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.queryByText("138")).not.toBeInTheDocument();
  });

  it("leaves a rule that does not exist without a number", () => {
    // spec: api-012, anom-008 — a zero here quotes the absence of a rule as
    // the accuracy of one, which is a figure that cannot be wrong because
    // nothing produced it.
    renderScreen({
      ...operationalPicture,
      detectionSummary: {
        anomalyLevel: "Low",
        signalIntegrity: "High",
        counts: [
          {
            ruleId: "SOURCE-GAP",
            findingType: "possible_data_source_issue",
            kind: "reportable",
            count: null,
            unavailable: "rule-not-built",
          },
        ],
      },
    });

    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders every receiver in the layout with the state it is in", () => {
    // spec: api-012, scn-005 — all seven, whether or not any was found to be
    // deviating, so a quiet run still has a map with reference points. The
    // screen previously labelled every receiver "Signal Noise", which with one
    // mock receiver was invisible and with seven claims noise on all of them.
    renderScreen({
      ...operationalPicture,
      rfSensors: [
        { ...operationalPicture.rfSensors[0], id: "RF-01", health: "fault" },
        {
          ...operationalPicture.rfSensors[0],
          id: "RF-02",
          stationName: "Rotterdam",
          health: "nominal",
        },
      ],
    });

    expect(screen.getByText("fault")).toBeInTheDocument();
    expect(screen.getByText("nominal")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Signal Noise/);
  });
});
