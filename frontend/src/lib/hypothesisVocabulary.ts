import type { CitationGrounding, Generator, HypothesisSummary, ReviewStatus, StoredGrounding, Verdict } from "../types/hypotheses";
import { clockLabel } from "./playback";

/**
 * Every word the rail's explanation cards and the Hypotheses screen use.
 * spec: op-002, ai-010, hyp-001, hyp-002, hyp-003, fbk-001, fbk-002, hyp-004.
 *
 * Panels carry no vocabulary of their own (the rule detectionVocabulary.ts
 * follows): the provenance phrases and the rail's sentence are declared once
 * here. Status is shown in the stored words, which need no translation.
 */

const WRITER: Record<Generator, string> = {
  hosted: "the AI model",
  local: "the local model",
  template: "the template",
};

/** Who wrote the explanation, and whether the arm that was asked degraded. */
export const provenance = (
  summary: Pick<HypothesisSummary, "generator" | "requestedGenerator" | "fellBack" | "modelId">,
): { text: string; degraded: boolean } =>
  summary.fellBack
    ? {
        text: `${capitalise(WRITER[summary.requestedGenerator])}'s answer was not used; ${WRITER[summary.generator]}'s is shown instead`,
        degraded: true,
      }
    : {
        // The model by its stored id, never a friendly name; none when no model
        // answered (qa.md 163).
        text: `Written by ${WRITER[summary.generator]}${summary.modelId === null ? "" : `, ${summary.modelId}`}`,
        degraded: false,
      };

/**
 * The sentence under the cards, or null when there is nothing to say: every
 * conclusion has an explanation. The count is null when nobody examined the
 * hour, which must never read as zero (api-019).
 */
export const unexplainedSentence = (count: number | null, explanations: number): string | null => {
  if (count === null) return "This hour has not been examined";
  if (count > 0) return count === 1 ? "1 conclusion this hour has no explanation yet" : `${count} conclusions this hour have no explanation yet`;
  return explanations === 0 ? "No conclusions this hour" : null;
};

/**
 * One citation's check, re-run on read (ai-008). The two failures are worded
 * apart, because citing a claim the rules set aside is the worse one.
 */
export const CITATION_GROUNDING_COPY: Record<CitationGrounding, string> = {
  grounded: "Found in the evidence",
  unknown: "Not found in the evidence",
  superseded: "Cites a claim the rules set aside",
};

export const citationGroundingLabel = (grounding: string): string =>
  CITATION_GROUNDING_COPY[grounding as CitationGrounding] ?? "Unrecognised check result";

/** The check recorded at generation, in three values: not checked is not passed (db-002). */
export const STORED_GROUNDING_COPY: Record<StoredGrounding, string> = {
  passed: "Checked when written: every citation found in the evidence",
  failed: "Checked when written: a citation was not found in the evidence",
  not_checked: "Not checked against the evidence when written",
};

/** The Hypotheses screen's sentences (hyp-001, hyp-003). */
export const SCREEN_COPY = {
  choose: "Choose an explanation from the list to review it.",
  emptyList: "No explanations are stored for review.",
  listFailed: "The list of explanations could not be loaded.",
  noVerdict: "No verdict recorded yet.",
  noneRecorded: "None recorded",
  noRadius: "No radius was recorded with this claim, so no area is drawn.",
  unplaced: "This conclusion's area is not on its hour's map, so no area is drawn.",
  mapLoading: "Loading the map of this hour.",
  mapFailed: "The map of this hour could not be loaded.",
  loading: (id: number) => `Loading explanation ${id}.`,
  notFound: (id: number) => `There is no explanation ${id} in the store.`,
  failed: (id: number) => `Explanation ${id} could not be loaded.`,
  notAnArea: (subject: string) => `This conclusion is a claim about ${subject}, not an area, so no area is drawn.`,
  unreviewable: (count: number) =>
    count === 1 ? "1 conclusion has explanations, but none is the one under review." : `${count} conclusions have explanations, but none is the one under review.`,
};

/** The four verdicts in words, in the design's order (fbk-001): buttons and history alike. */
export const VERDICT_COPY: Record<Verdict, string> = {
  confirm: "Confirm",
  reject: "Reject",
  "needs-more-evidence": "Needs more evidence",
  "false-positive": "False positive",
};

/** A stored verdict in words; one outside the four is named, never shown raw. */
export const verdictLabel = (verdict: string): string => VERDICT_COPY[verdict as Verdict] ?? "Unrecognised verdict";

/** The verdict card's sentences (fbk-001, fbk-002, hyp-004). */
export const VERDICT_CARD_COPY = {
  disclaimer: "Decision support only — analyst judgement is final.",
  noteLabel: "Note (optional)",
  noteCount: (length: number, limit: number) => `${length.toLocaleString("en-GB")} / ${limit.toLocaleString("en-GB")} characters`,
  noteTooLong: (limit: number) => `The note is over ${limit.toLocaleString("en-GB")} characters; shorten it to record a verdict.`,
  sending: "Recording the verdict.",
  notRecorded: "The verdict was not recorded. The status shown is the one stored.",
  recorded: (status: ReviewStatus) => `Verdict recorded. The status is now ${status}.`,
  notReviewable: "This is not the explanation scored for its conclusion, so it takes no verdict.",
};

/** A conclusion's window, e.g. 12:09:46–12:14:56 UTC. */
export const windowLabel = (start: string, end: string): string => `${clockLabel(Date.parse(start)).replace(" UTC", "")}–${clockLabel(Date.parse(end))}`;

/** When a verdict was recorded, e.g. 2026-10-11 09:00:00 UTC. */
export const instantLabel = (at: string): string => `${new Date(at).toISOString().slice(0, 10)} ${clockLabel(Date.parse(at))}`;

/** A point, e.g. 51.526° N, 5.758° E. */
export const centreLabel = (lat: number, lon: number): string =>
  `${Math.abs(lat).toFixed(3)}° ${lat < 0 ? "S" : "N"}, ${Math.abs(lon).toFixed(3)}° ${lon < 0 ? "W" : "E"}`;

const capitalise = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);
