import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import operationalPicture from "../mocks/operationalPictureMock";
import OperationalPictureScreen from "../screens/operationalPicture";
import type { OperationalPicture } from "../types/operationalPicture";

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

    expect(valueFor("Anomaly Level")).toBe(operationalPicture.detectionSummary.anomalyLevel);
  });

  it("renders signal integrity as a band rather than a decimal", () => {
    // spec: api-002, FR-715, AC-11 — previously `0.92`, via toFixed(2).
    renderScreen();

    expect(valueFor("Signal Integrity")).toBe(
      operationalPicture.detectionSummary.signalIntegrity,
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

  it("shows an absent detection summary as a dash rather than as a value", () => {
    // spec: api-002 — the endpoint serves null while no detector exists, so
    // null is a state the screen receives in normal operation, not an error.
    renderScreen({
      ...operationalPicture,
      detectionSummary: { anomalyLevel: null, signalIntegrity: null },
    });

    expect(valueFor("Anomaly Level")).toBe("—");
    expect(valueFor("Signal Integrity")).toBe("—");
  });
});
