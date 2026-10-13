import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { evidenceLabel } from "../lib/detectionVocabulary";
import { CITATION_GROUNDING_COPY, citationGroundingLabel, STORED_GROUNDING_COPY } from "../lib/hypothesisVocabulary";
import operationalPictureMock from "../mocks/operationalPictureMock";
import HypothesesScreen from "../screens/hypotheses";
import type { HypothesisCitation, HypothesisDetail } from "../types/hypotheses";

// spec: hyp-002, hyp-003 (amended 2026-10-11) — the supporting evidence with a
// grounding marker per citation, the stored check beside them, and the
// uncertainty and alternatives as two sections of plain sentences.

const citation = (over: Partial<HypothesisCitation> = {}): HypothesisCitation => ({
  position: 1,
  ruleId: "RF-NOISE",
  findingType: "rf_noise_deviation",
  statement: "Both RF-04 and RF-05 recorded repeated, significant power_dbm deviations.",
  grounding: "grounded",
  ...over,
});

const detail = (over: Partial<HypothesisDetail> = {}): HypothesisDetail => ({
  id: 104,
  bundleId: 250,
  reviewable: true,
  hypothesisTitle: "Possible interference zone affecting RF-04 and RF-05",
  confidence: "Medium",
  summary: "Both receivers deviated while aircraft nearby lost contact.",
  supportingEvidence: [
    citation(),
    citation({
      position: 2,
      ruleId: "TRACK-GAP",
      findingType: "track_rate_excess",
      statement: "A 60 km disc around the area showed 6 track discontinuities during the window.",
    }),
  ],
  evidenceAgainstOrUncertainty: ["Track discontinuities are common in normal traffic.", "Only two receivers saw the deviation."],
  alternativeExplanations: ["A shared hardware cause at both receivers."],
  recommendedHumanAction: "Check both receivers against an independent one.",
  generator: "hosted",
  requestedGenerator: "hosted",
  fellBack: false,
  modelId: "gpt-4.1-2025-04-14",
  status: "New",
  grounding: "passed",
  bundle: {
    runId: 106,
    anomalyType: "possible_interference_zone",
    ruleId: "FUSION-SPATIAL",
    subject: "RF-04, RF-05",
    windowStart: "2022-06-27T12:09:46Z",
    windowEnd: "2022-06-27T12:14:56Z",
    longitude: 5.758,
    latitude: 51.526,
    channels: [3, 4],
    receivers: ["RF-04", "RF-05"],
  },
  verdicts: [],
  ...over,
});

const show = (over: Partial<HypothesisDetail> = {}) =>
  render(
    <HypothesesScreen
      hypothesisId={104}
      loadList={() => Promise.resolve({ hypotheses: [], unreviewableBundles: 0 })}
      loadDetail={() => Promise.resolve(detail(over))}
      loadPicture={() => Promise.resolve(operationalPictureMock)}
      submitVerdict={() => new Promise(() => {})}
    />,
  );

const section = async (name: string) => within((await screen.findByRole("heading", { name })).closest("section") as HTMLElement);
const rows = async () => (await section("Supporting evidence")).getAllByRole("listitem");

describe("the supporting evidence (hyp-002)", () => {
  it("renders one row per citation, in position order", async () => {
    show({ supportingEvidence: [citation({ position: 2, statement: "second" }), citation({ position: 1, statement: "first" })] });

    const [first, second] = await rows();
    expect(first).toHaveTextContent("first");
    expect(second).toHaveTextContent("second");
  });

  it("shows each citation's rule chip, its finding type in words, and its statement", async () => {
    show();

    const [first, second] = await rows();
    expect(within(first).getByText("RF-NOISE")).toBeInTheDocument();
    expect(within(first).getByText(evidenceLabel("rf_noise_deviation"))).toBeInTheDocument();
    expect(first).toHaveTextContent(detail().supportingEvidence[0].statement);
    expect(within(second).getByText("TRACK-GAP")).toBeInTheDocument();
    expect(within(second).getByText(evidenceLabel("track_rate_excess"))).toBeInTheDocument();
  });

  it("marks a grounded citation in words", async () => {
    show();

    const [first] = await rows();
    expect(within(first).getByText(CITATION_GROUNDING_COPY.grounded)).toBeInTheDocument();
  });

  it.each(["unknown", "superseded"] as const)("shows a %s citation, marked, never hidden", async (grounding) => {
    // hyp-002's failure case: concealing it removes the analyst's ability to judge the failure.
    show({ supportingEvidence: [citation(), citation({ position: 2, statement: "the failing one", grounding })] });

    const [, failing] = await rows();
    expect(failing).toHaveTextContent("the failing one");
    expect(within(failing).getByText(CITATION_GROUNDING_COPY[grounding])).toBeInTheDocument();
    expect(within(failing).queryByText(CITATION_GROUNDING_COPY.grounded)).not.toBeInTheDocument();
  });

  it("gives every re-check value its own words, the failures distinct from success", () => {
    const words = Object.values(CITATION_GROUNDING_COPY);
    expect(Object.keys(CITATION_GROUNDING_COPY).sort()).toEqual(["grounded", "superseded", "unknown"]);
    expect(new Set(words).size).toBe(3);
    expect(words.every((word) => word.trim().length > 0)).toBe(true);
  });

  it("states an unrecognised re-check value rather than rendering blank", () => {
    expect(citationGroundingLabel("misspelt")).toMatch(/unrecognised/i);
  });

  it("states an unrecognised finding type rather than rendering blank", async () => {
    show({ supportingEvidence: [citation({ findingType: "a_type_nobody_declared" })] });

    const [first] = await rows();
    expect(within(first).getByText(/unrecognised/i)).toBeInTheDocument();
  });

  it("names no source the citation does not carry", async () => {
    // The design's "ADS-B Receiver 01", "SIGINT Array Gamma", "LEO-SAT Node 4".
    show();

    const evidence = await section("Supporting evidence");
    expect(evidence.queryByText(/sigint|leo-sat|ads-b receiver/i)).not.toBeInTheDocument();
  });

  it.each(["passed", "failed", "not_checked"] as const)("states the stored check at generation (%s) once, above the rows", async (grounding) => {
    show({ grounding });

    const evidence = await section("Supporting evidence");
    expect(evidence.getAllByText(STORED_GROUNDING_COPY[grounding])).toHaveLength(1);
  });

  it("never renders a stored not_checked as passed", () => {
    // hyp-002's failure case: not yet checked is not passed (db-002's three values).
    expect(STORED_GROUNDING_COPY.not_checked).not.toBe(STORED_GROUNDING_COPY.passed);
    expect(STORED_GROUNDING_COPY.not_checked).not.toMatch(/passed/i);
    expect(new Set(Object.values(STORED_GROUNDING_COPY)).size).toBe(3);
  });
});

describe("the uncertainty and the alternatives (hyp-003)", () => {
  it("renders two separately headed sections, each sentence verbatim", async () => {
    show();

    const uncertainty = await section("Uncertainty and evidence against");
    const alternatives = await section("Alternative explanations");
    expect(uncertainty.getAllByRole("listitem").map((item) => item.textContent)).toEqual(detail().evidenceAgainstOrUncertainty);
    expect(alternatives.getAllByRole("listitem").map((item) => item.textContent)).toEqual(detail().alternativeExplanations);
  });

  it("never merges them into one block", async () => {
    show();

    const uncertainty = await section("Uncertainty and evidence against");
    expect(uncertainty.queryByText(detail().alternativeExplanations[0])).not.toBeInTheDocument();
    expect(screen.queryByText(/counter-indicators/i)).not.toBeInTheDocument();
  });

  it("renders both open, never behind a disclosure", async () => {
    show();

    for (const name of ["Uncertainty and evidence against", "Alternative explanations"]) {
      const region = (await screen.findByRole("heading", { name })).closest("section") as HTMLElement;
      expect(region.closest("details")).toBeNull();
      expect(region.closest("[hidden]")).toBeNull();
      expect(within(region).queryByRole("button")).not.toBeInTheDocument();
    }
  });

  it.each([
    ["Uncertainty and evidence against", { evidenceAgainstOrUncertainty: [] }],
    ["Alternative explanations", { alternativeExplanations: [] }],
  ])("says None recorded when %s is empty, never omitting the section", async (name, over) => {
    show(over);

    expect((await section(name)).getByText("None recorded")).toBeInTheDocument();
  });

  it("carries no category tags", async () => {
    // The design's EXTERNAL NOISE, FALSE DEP, BASELINE: the store holds none.
    show();

    const uncertainty = await section("Uncertainty and evidence against");
    expect(uncertainty.queryByText(/external noise|false dep|baseline/i)).not.toBeInTheDocument();
  });

  it("places both beside the supporting evidence, after it", async () => {
    show();

    const evidence = (await screen.findByRole("heading", { name: "Supporting evidence" })).closest("section") as HTMLElement;
    const uncertainty = screen.getByRole("heading", { name: "Uncertainty and evidence against" }).closest("section") as HTMLElement;
    const alternatives = screen.getByRole("heading", { name: "Alternative explanations" }).closest("section") as HTMLElement;
    expect(evidence.compareDocumentPosition(uncertainty) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(uncertainty.compareDocumentPosition(alternatives) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
