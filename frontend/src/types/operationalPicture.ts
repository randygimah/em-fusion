//Types for operational picture data

// Confidence, severity and any score are Low, Medium or High — never a
// percentage or a decimal (FR-715, AC-11). Declared once so the three places
// that carry a level cannot drift into three different vocabularies.
export type Level = "Low" | "Medium" | "High";

export interface Scenario {
  id: string;
  name: string;
  dataMode: string;
  health: string;
}

export interface Hypothesis {
  id: string;
  title: string;
  confidence: Level;
  severity: Level;
  status: "new" | "under_review" | "reviewed";
  evidence: string;
}

// Whether a producer's output is a conclusion or the working material behind
// one (api-012). A quiet run genuinely holds about 138 track discontinuities,
// so an intermediate count shown as an anomaly count reads a correct
// non-detection as a storm. Carried on the wire rather than left to the screen,
// because a hard-coded list of rule names outlives the reason it was written.
export type ProducerKind = "intermediate" | "reportable";

// Why a producer has no count, and the two reasons are not the same thing
// (api-012). `rule-not-built` is a rule that does not exist — a zero there
// would quote the absence of a rule as the accuracy of one. `not-persisted` is
// a rule that ran and whose output is not stored: the track clusters, whose
// citation shape the traceability check refuses by name, and the rate excess,
// which is internal to the fusion decision. Collapsing them would report a
// built detector as a missing one.
export type CountUnavailable = "rule-not-built" | "not-persisted";

// One detection rule and what it produced on this run. Exactly one of `count`
// and `unavailable` is set.
export interface DetectionCount {
  ruleId: string;
  findingType: string;
  kind: ProducerKind;
  count: number | null;
  unavailable: CountUnavailable | null;
}

// `counts` is an account of every registered rule, including the ones that
// found nothing: zero is the answer a quiet run gives and also the answer a
// pipeline that never ran gives, so the *presence* of the account is what says
// the detectors looked, never a number in it (api-012, anom-008).
//
// The two levels measure different kinds of thing and are deliberately not
// rolled into one: confidence qualifies an attribution and severity qualifies a
// deviation, so a single figure over both describes neither.
export interface DetectionSummary {
  anomalyLevel: Level;
  signalIntegrity: Level;
  counts: DetectionCount[];
}

export interface RFSensor {
  id: string;
  stationName: string;
  // The band this receiver watches, from the layout — not a per-sensor
  // identifier, which is what `id` is for.
  signalId: string;
  // The state the detection pass found it in: nominal, deviating, fault, or
  // `unknown` when no pass has run. `nominal` on an unexamined run would be a
  // reassurance nothing checked (api-012).
  health: string;
  lat: number;
  lon: number;
}

export interface AircraftTrack {
  id: string;
  name: string;
  altitudeFt: number | null;
  lat: number;
  lon: number;
}

export interface TimelineEvent {
  id: string;
  time: string;
  event: string;
  source: string;
}

export interface OperationalPicture {
  scenario: Scenario | null;
  hypotheses: Hypothesis[];
  // null means no detection pass has run on this run, which is not the same as
  // a pass that found nothing (api-012). One absence with one meaning: inside
  // a summary that is present, every value is a reading.
  detectionSummary: DetectionSummary | null;
  rfSensors: RFSensor[];
  aircraftTracks: AircraftTrack[];
  timelineEvents: TimelineEvent[];
}
