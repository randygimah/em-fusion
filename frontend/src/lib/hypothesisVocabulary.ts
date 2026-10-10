import type { Generator, HypothesisSummary } from "../types/hypotheses";

/**
 * Every word the rail's explanation cards use. spec: op-002, ai-010 (card half).
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
export const provenance = (summary: HypothesisSummary): { text: string; degraded: boolean } =>
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

const capitalise = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);
