// Types for the hypothesis read endpoints. spec: api-004
//
// The server half is `backend/app/api/v1/schemas/hypotheses.py`. A test in the
// BACKEND suite parses this file and compares field sets in both directions,
// and each closed vocabulary below against the backend's own enum, the same
// arrangement `evidence.ts` has.
//
// One explanation per conclusion is listed: the one the blind scoring used.
// Both shapes name the generator, so nothing built on them is shown to a rater
// before their scoring is done.

// Never a number, on screen or in the payload.
export type HypothesisConfidence = "Low" | "Medium" | "High";

export type ReviewStatus = "New" | "Under review" | "Confirmed" | "Rejected" | "Inconclusive";

// The stored check, as recorded at generation. Three values: "not checked" is
// not "failed".
export type StoredGrounding = "not_checked" | "passed" | "failed";

// One citation's check, re-run when the hypothesis is read. A failure is served,
// never dropped.
export type CitationGrounding = "grounded" | "unknown" | "superseded";

// Which generator was asked, and which answered. They differ exactly when the
// asked arm fell back.
export type Generator = "template" | "local" | "hosted";

export interface AnalystVerdict {
  verdict: string;
  note: string | null;
  createdAt: string;
}

export interface HypothesisCitation {
  // One-based.
  position: number;
  ruleId: string;
  findingType: string;
  statement: string;
  grounding: CitationGrounding;
}

export interface HypothesisBundle {
  runId: number;
  anomalyType: string;
  ruleId: string;
  subject: string;
  windowStart: string;
  windowEnd: string;
  longitude: number;
  latitude: number;
  channels: number[];
  // Every layout receiver the evidence names, each once, in order.
  receivers: string[];
}

export interface HypothesisSummary {
  id: number;
  bundleId: number;
  runId: number;
  hypothesisTitle: string;
  confidence: HypothesisConfidence;
  status: ReviewStatus;
  generator: Generator;
  requestedGenerator: Generator;
  fellBack: boolean;
  // The stored model id verbatim, or null where no model answered.
  modelId: string | null;
  anomalyType: string;
  ruleId: string;
  subject: string;
  windowStart: string;
  windowEnd: string;
  latestVerdict: AnalystVerdict | null;
}

export interface HypothesisList {
  hypotheses: HypothesisSummary[];
  // Conclusions holding explanations but none to review: an absence counted.
  unreviewableBundles: number;
}

export interface HypothesisDetail {
  id: number;
  bundleId: number;
  reviewable: boolean;
  hypothesisTitle: string;
  confidence: HypothesisConfidence;
  summary: string;
  supportingEvidence: HypothesisCitation[];
  evidenceAgainstOrUncertainty: string[];
  alternativeExplanations: string[];
  recommendedHumanAction: string;
  generator: Generator;
  requestedGenerator: Generator;
  fellBack: boolean;
  modelId: string | null;
  status: ReviewStatus;
  grounding: StoredGrounding;
  bundle: HypothesisBundle;
  // Oldest first; empty, never null.
  verdicts: AnalystVerdict[];
}
