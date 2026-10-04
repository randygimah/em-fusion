// Types for the evidence behind an hour's reported claims. spec: api-015, op-010
//
// The server half is `backend/app/api/v1/schemas/evidence.py`. Nothing checks
// the two at compile time — they are two declarations of one shape in two
// languages — so a test in the BACKEND suite parses this file and compares
// field sets in both directions, the same arrangement `operationalPicture.ts`
// has. The parser exists once and on that side.

// Whether an evidence item cites observations or states a judgement.
//
// The one part of a bundle that cannot be inferred from the rest, and the
// reason it is declared rather than guessed: a nominal neighbour is in the
// bundle *precisely because* nothing was raised for it, so rendered unmarked
// beside a deviation it reads as a second deviation — which inverts the fault
// verdict it is evidence for.
export type Grounding = "observed" | "derived";

// The three things an absence can mean, kept apart on purpose. Never
// consulted; consulted and no basis on which to judge; looked at and found not
// to rise to a finding. Collapsed to one sentence on screen, the distinction
// the bundle builder is organised around is undone at the last boundary before
// a person.
export type AbsenceKind = "not_applicable" | "not_measurable" | "measured_negative";

// Why a reported claim has no evidence here. A closed set rather than a bare
// string, so a second reason cannot arrive with no sentence written for it.
export type UnexplainedReason = "not-bundled";

// Why stored evidence is attached to no claim.
export type UnclaimedReason = "no-current-claim";

// Every finding type the bundle builder can emit, and therefore every type the
// panel has to word. Held against the builder's own output by a test in the
// backend suite; the screen's copy map is typed on this union, so a type with
// no sentence written for it is a type error there rather than a raw token on
// screen.
//
// Five of these never reached the summary panel: they are the working material
// an explanation rests on rather than a conclusion.
export type EvidenceFindingType =
  | "rf_noise_deviation"
  | "track_continuity_gap"
  | "track_rate_excess"
  | "neighbour_nominal"
  | "channel_adjacency"
  | "possible_sensor_fault"
  | "possible_interference_zone";

// One wording, and which sources said it.
//
// Identical wording collapses to one sentence plus its sources — measured on
// run 102, where nine aircraft discontinuities carry one sentence between
// eight aircraft. It is a collapse of identical strings and never a summary:
// two neighbours measured nominal say two different things.
export interface EvidenceStatement {
  text: string;
  count: number;
  sources: string[];
}

// Every item of one rule and one finding type.
//
// Keyed on the pair and never the rule alone: the rate-excess rule borrows the
// track-gap rule's id, so a ratio and a discontinuity are identical by rule id
// in every interference bundle this corpus produces.
//
// `count` is the only number the server computed. Everything else — the span,
// the sources, each sentence — appears verbatim on one of the items.
export interface EvidenceGroup {
  ruleId: string;
  findingType: string;
  grounding: Grounding;
  dataMode: string;
  count: number;
  observedFrom: string;
  observedTo: string;
  sources: string[];
  statements: EvidenceStatement[];
}

// What the bundle does not know, and which kind of not-knowing. The kind says
// what sort it is; the statement is the only part a person can weigh, and
// crosses verbatim and untruncated.
export interface KnownUncertainty {
  kind: AbsenceKind;
  statement: string;
  subject: string;
  // How many identical absences this entry collapsed. A bundle holds one per
  // suppressed episode and real ones repeat a single sentence up to 28 times,
  // so the server factors them the same way it factors the evidence. Found by
  // looking at the running screen rather than by a test.
  count: number;
}

// A competing conclusion the precedence ladder rejected. Shown as rejected,
// never among the support: carried as support, two rules' disagreement reads
// as two rules' agreement.
export interface SupersededClaim {
  ruleId: string;
  anomalyType: string;
  claimedBy: string;
  reason: string;
}

// One reported claim and the evidence behind it.
//
// `subject` is the BUNDLE's — its own record of which receivers deviated
// together, which is what the panel has to name. The claim's own representative
// receiver already reaches the screen through the timeline, so both here would
// be two differing values for one word in front of a reader.
export interface ExplainedClaim {
  bundleId: number;
  ruleId: string;
  findingType: string;
  subject: string;
  observedFrom: string;
  observedTo: string;
  lat: number;
  lon: number;
  channels: number[];
  dataModes: string[];
  evidence: EvidenceGroup[];
  uncertainties: KnownUncertainty[];
  superseded: SupersededClaim[];
}

// A reported claim the store holds no evidence for. The common case rather
// than the edge: 140 of the 240 claim-bearing hours, and every hour the
// selector offers first.
export interface UnexplainedClaim {
  ruleId: string;
  findingType: string;
  subject: string;
  observedFrom: string;
  observedTo: string;
  reason: UnexplainedReason;
}

// Stored evidence that no current conclusion claims. Dropped silently, an hour
// would read as fully explained while some of its evidence was discarded.
export interface UnclaimedBundle {
  bundleId: number;
  ruleId: string;
  findingType: string;
  subject: string;
  observedFrom: string;
  observedTo: string;
  reason: UnclaimedReason;
}

// Every reported claim of one hour, and every bundle the store holds for it.
//
// The two pairs of lists are a two-sided completeness guarantee: `explained`
// and `unexplained` account for every reported claim, `explained` and
// `unclaimed` for every stored bundle, so nothing in the store is dropped in
// either direction.
export interface EvidenceAccount {
  runId: number;
  explained: ExplainedClaim[];
  unexplained: UnexplainedClaim[];
  unclaimed: UnclaimedBundle[];
}
