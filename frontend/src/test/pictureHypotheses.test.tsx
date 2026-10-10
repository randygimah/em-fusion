import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import operationalPictureMock from "../mocks/operationalPictureMock";
import OperationalPictureScreen from "../screens/operationalPicture";
import type { HypothesisSummary } from "../types/hypotheses";
import type { OperationalPicture } from "../types/operationalPicture";

// spec: api-019 — the picture's hypotheses are the list endpoint's summaries.
// Only enough of the rail to prove the new shape reaches the screen: each
// card's title and confidence. Cards are links since op-002. The link, provenance, status and the sentence
// for unexplained conclusions are op-002's.

const summary = (over: Partial<HypothesisSummary> = {}): HypothesisSummary => ({
  id: 41,
  bundleId: 7,
  runId: 480,
  hypothesisTitle: "Possible localised interference near RF-03 and RF-04",
  confidence: "Medium",
  status: "New",
  generator: "hosted",
  requestedGenerator: "hosted",
  fellBack: false,
  modelId: "gpt-4.1-2025-04-14",
  anomalyType: "possible_interference_zone",
  ruleId: "FUSION-SPATIAL",
  subject: "RF-03, RF-04",
  windowStart: "2022-06-27T12:31:00Z",
  windowEnd: "2022-06-27T12:36:00Z",
  latestVerdict: null,
  ...over,
});

const picture = (over: Partial<OperationalPicture> = {}): OperationalPicture => ({
  ...operationalPictureMock,
  ...over,
});

const rail = () => {
  const heading = screen.getByRole("heading", { name: "Hypotheses" });
  return within(heading.closest("section") as HTMLElement);
};

describe("the rail's explanations (api-019)", () => {
  it("renders each explanation's title beside its confidence level", () => {
    render(
      <OperationalPictureScreen
        operationalPicture={picture({
          hypotheses: [summary({ confidence: "High" }), summary({ id: 42, hypothesisTitle: "Possible sensor fault on RF-07", confidence: "Low" })],
        })}
      />,
    );

    const card = (title: string) => within(rail().getByText(title).closest("a") as HTMLElement);
    expect(card("Possible localised interference near RF-03 and RF-04").getByText("High")).toBeInTheDocument();
    expect(card("Possible sensor fault on RF-07").getByText("Low")).toBeInTheDocument();
  });

  it("renders no severity, which nothing in the system produces", () => {
    render(<OperationalPictureScreen operationalPicture={picture({ hypotheses: [summary()] })} />);

    expect(rail().queryByText(/severity/i)).not.toBeInTheDocument();
  });

  it("the first-paint mock carries the new shape", () => {
    for (const hypothesis of operationalPictureMock.hypotheses) {
      expect(hypothesis).toHaveProperty("hypothesisTitle");
      expect(hypothesis).not.toHaveProperty("severity");
    }
    expect(operationalPictureMock).toHaveProperty("unexplainedConclusions");
  });
});
