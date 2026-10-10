import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import operationalPictureMock from "../mocks/operationalPictureMock";
import OperationalPictureScreen from "../screens/operationalPicture";
import screenSource from "../screens/operationalPicture.tsx?raw";
import type { HypothesisSummary } from "../types/hypotheses";
import type { OperationalPicture } from "../types/operationalPicture";

// spec: op-002 (amended 2026-10-10) — the rail's cards over the hour's
// explanations (api-019): title, confidence, status, provenance in words (the
// card half of ai-010), each a link to its own address (nav-004), and one
// sentence for the hour's conclusions with no explanation.

const vocabularySource = Object.values(import.meta.glob("../lib/hypothesisVocabulary.ts", { query: "?raw", import: "default", eager: true }))[0] as
  | string
  | undefined;

const summary = (over: Partial<HypothesisSummary> = {}): HypothesisSummary => ({
  id: 41,
  bundleId: 248,
  runId: 102,
  hypothesisTitle: "Possible interference zone near Dusseldorf and Koln-Bonn",
  confidence: "Medium",
  status: "New",
  generator: "hosted",
  requestedGenerator: "hosted",
  fellBack: false,
  modelId: "gpt-4.1-2025-04-14",
  anomalyType: "possible_interference_zone",
  ruleId: "FUSION-SPATIAL",
  subject: "RF-06, RF-07",
  windowStart: "2022-06-27T12:29:00Z",
  windowEnd: "2022-06-27T12:34:00Z",
  latestVerdict: null,
  ...over,
});

const FELL_BACK = summary({
  id: 42,
  hypothesisTitle: "Possible receiver fault on RF-01",
  generator: "template",
  fellBack: true,
  modelId: null,
});

const show = (over: Partial<OperationalPicture>) =>
  render(<OperationalPictureScreen operationalPicture={{ ...operationalPictureMock, unexplainedConclusions: 0, ...over }} />);

const rail = () => within(screen.getByRole("heading", { name: "Hypotheses" }).closest("section") as HTMLElement);

const card = (title: string) => rail().getByRole("link", { name: new RegExp(title, "i") });

describe("the rail's cards (op-002)", () => {
  it("makes every card a link to its own explanation, named by its title", () => {
    show({ hypotheses: [summary(), FELL_BACK] });

    expect(card("Possible interference zone near Dusseldorf").getAttribute("href")).toBe("#/hypotheses/41");
    expect(card("Possible receiver fault on RF-01").getAttribute("href")).toBe("#/hypotheses/42");
  });

  it("shows each card's review status in the stored words", () => {
    show({ hypotheses: [summary({ status: "Under review" }), FELL_BACK] });

    expect(within(card("Possible interference zone")).getByText("Under review")).toBeInTheDocument();
    expect(within(card("Possible receiver fault")).getByText("New")).toBeInTheDocument();
  });

  it("names the AI model, and the model by its stored id, when the AI model answered", () => {
    // qa.md 163 — the stored id verbatim, never a friendly name.
    show({ hypotheses: [summary()] });

    expect(within(card("Possible interference zone")).getByText("Written by the AI model, gpt-4.1-2025-04-14")).toBeInTheDocument();
  });

  it("names the template when the template was asked", () => {
    show({ hypotheses: [summary({ generator: "template", requestedGenerator: "template", modelId: null })] });

    // No model to name: the template has none.
    expect(within(card("Possible interference zone")).getByText("Written by the template")).toBeInTheDocument();
  });

  it("names the local model when the local model was asked and answered", () => {
    show({ hypotheses: [summary({ generator: "local", requestedGenerator: "local" })] });

    expect(within(card("Possible interference zone")).getByText(/written by the local model/i)).toBeInTheDocument();
  });

  it("marks a fallback in words, never rendering it as an AI card", () => {
    // ai-010's failure case: the analyst must know the AI layer degraded.
    show({ hypotheses: [summary(), FELL_BACK] });

    const fallback = within(card("Possible receiver fault")).getByText(/not used/i);
    expect(fallback.textContent).toMatch(/ai model/i);
    expect(fallback.textContent).toMatch(/template/i);
    expect(within(card("Possible receiver fault")).queryByText(/written by the ai model/i)).not.toBeInTheDocument();
    expect(within(card("Possible interference zone")).queryByText(/not used/i)).not.toBeInTheDocument();
    // The fallback's stored row is the template's: it names no model rather
    // than inventing one.
    expect(card("Possible receiver fault").textContent).not.toMatch(/gpt/i);
  });

  it("does not hide a rejected explanation", () => {
    show({ hypotheses: [summary({ status: "Rejected" })] });

    expect(within(card("Possible interference zone")).getByText("Rejected")).toBeInTheDocument();
  });
});

describe("the rail's heading (op-002)", () => {
  it("is Hypotheses, fixed whatever the hour holds", () => {
    // qa.md 163 — every status is shown, so not "Active"; and a heading that
    // changed with the data would rename the region per hour.
    for (const over of [
      { hypotheses: [summary()] },
      { hypotheses: [], unexplainedConclusions: 1 },
      { hypotheses: [], unexplainedConclusions: null },
    ]) {
      const { unmount } = show(over);
      expect(screen.getByRole("heading", { name: "Hypotheses" })).toBeInTheDocument();
      expect(screen.queryByText(/active hypotheses/i)).not.toBeInTheDocument();
      unmount();
    }
  });
});

describe("the rail's sentence for unexplained conclusions (op-002)", () => {
  it("counts one conclusion with no explanation, in the singular", () => {
    show({ hypotheses: [], unexplainedConclusions: 1 });

    expect(rail().getByText("1 conclusion this hour has no explanation yet")).toBeInTheDocument();
    expect(rail().queryByText(/no active hypotheses/i)).not.toBeInTheDocument();
  });

  it("counts several, in the plural, under the cards", () => {
    show({ hypotheses: [summary()], unexplainedConclusions: 3 });

    expect(rail().getByText("3 conclusions this hour have no explanation yet")).toBeInTheDocument();
  });

  it("says there are no conclusions when the list is empty and the count is zero", () => {
    show({ hypotheses: [], unexplainedConclusions: 0 });

    expect(rail().getByText("No conclusions this hour")).toBeInTheDocument();
    expect(rail().queryByText(/no active hypotheses/i)).not.toBeInTheDocument();
  });

  it("says nothing about conclusions when every one has an explanation", () => {
    show({ hypotheses: [summary()], unexplainedConclusions: 0 });

    expect(card("Possible interference zone")).toBeInTheDocument();
    expect(rail().queryByText(/no explanation yet/i)).not.toBeInTheDocument();
    expect(rail().queryByText("No conclusions this hour")).not.toBeInTheDocument();
  });

  it("never reads an unexamined hour as zero conclusions", () => {
    show({ hypotheses: [], unexplainedConclusions: null });

    expect(rail().getByText("This hour has not been examined")).toBeInTheDocument();
    expect(rail().queryByText("No conclusions this hour")).not.toBeInTheDocument();
  });
});

describe("the cards' words live in one vocabulary module (op-002)", () => {
  it("is declared in src/lib/hypothesisVocabulary.ts", () => {
    expect(vocabularySource).toBeDefined();
    for (const words of ["no explanation yet", "No conclusions this hour", "This hour has not been examined", "not used"]) {
      expect(vocabularySource).toContain(words);
    }
  });

  it("is imported by the screen rather than written into it", () => {
    expect(screenSource).toContain("hypothesisVocabulary");
    for (const words of ["no explanation yet", "No conclusions this hour", "This hour has not been examined", "Written by"]) {
      expect(screenSource).not.toContain(words);
    }
  });
});
