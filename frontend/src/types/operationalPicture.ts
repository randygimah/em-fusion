//Types for operational picture data

import type { HypothesisSummary } from "./hypotheses";

// Confidence, severity and any score are Low, Medium or High — never a
// percentage or a decimal (FR-715, AC-11). Declared once so the three places
// that carry a level cannot drift into three different vocabularies.
export type Level = "Low" | "Medium" | "High";

// The run on screen (api-002, api-012). No `health` field: api-014 removed it.
//
// It was hard-coded to `unknown` in the payload builder, with a comment saying
// no health monitoring existed. What changed is not that a producer arrived but
// that another field took the job — `detectionSummary.signalIntegrity` is the
// state of the receiver layout and has one. Two health fields where one works is
// worse than one, because the broken one reads as a second fact that never
// arrives, and the screen printed it as a bare `unknown`.
//
// `RFSensor.health` below is untouched: that one has a producer and carries
// per-receiver state, and the two are spelled identically.
export interface Scenario {
  id: string;
  name: string;
  dataMode: string;
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

// The conclusions the precedence ladder can reach, and therefore the only
// finding types the summary panel and the timeline ever have to word (op-003,
// op-006). A closed set, compared against the backend's own register by a test
// in the BACKEND suite — the TypeScript parser exists once and on that side.
//
// It is a union rather than a string so that a copy map not covering it is a
// type error: the payload carries each type verbatim by design, so a type with
// no sentence written for it would reach an analyst as the raw token, which is
// the defect this vocabulary exists to remove.
export type ReportableFindingType =
  | "possible_interference_zone"
  | "possible_sensor_fault"
  | "possible_data_source_issue";

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

// What this run's stored findings say about an aircraft (api-016). Three words
// and not a boolean: `unknown` on a run no pass has examined, `nominal` when the
// findings say nothing about it, `interrupted` when its reporting broke. A
// continuity gap stays intermediate — this is a fact about a track, never a
// reported anomaly — and the set is compared with the backend's by a test there.
export type TrackState = "nominal" | "interrupted" | "unknown";

export interface AircraftTrack {
  id: string;
  name: string;
  altitudeFt: number | null;
  lat: number;
  lon: number;
  state: TrackState;
}

export interface TimelineEvent {
  id: string;
  time: string;
  event: string;
  source: string;
}

// What the aircraft side had to say about an interference claim (anom-005,
// anom-012). Sent verbatim; the screen words it from detectionVocabulary.
export type Corroboration = "corroborated" | "not_corroborated" | "not_measurable";

export interface ZoneCentre {
  lat: number;
  lon: number;
}

// One stored interference claim, placed (api-017). `id` equals the claim's
// timeline event id, so the zone and its conclusion join. `radiusKm` is the
// radius the rule assessed the aircraft side over, recorded with the claim —
// not a measured extent of the interference — and null when none was recorded.
export interface InterferenceZone {
  id: string;
  centre: ZoneCentre;
  radiusKm: number | null;
  receivers: string[];
  startedAt: string;
  endedAt: string;
  confidence: Level;
  corroboration: Corroboration;
}

export interface OperationalPicture {
  scenario: Scenario | null;
  // The hour's explanations (api-019): the hypotheses list's own summaries,
  // imported rather than redeclared, so the rail and the Hypotheses screen
  // cannot disagree about which explanation a conclusion has.
  hypotheses: HypothesisSummary[];
  // The hour's conclusions with no explanation to review, or null when no
  // detection pass examined the hour. Most examined hours have some, so an
  // empty list alone would read as "nothing concluded".
  unexplainedConclusions: number | null;
  // null means no detection pass has run on this run, which is not the same as
  // a pass that found nothing (api-012). One absence with one meaning: inside
  // a summary that is present, every value is a reading.
  detectionSummary: DetectionSummary | null;
  rfSensors: RFSensor[];
  aircraftTracks: AircraftTrack[];
  timelineEvents: TimelineEvent[];
  // The interference claims among the events, placed for the map (api-017).
  interferenceZones: InterferenceZone[];
  // The view served and what it withheld (api-007). detectionSummary above is
  // never filtered: it is the account of the whole run whatever the view.
  view: PictureView;
}

// What the screen may ask to see (api-007, FR-809). The server filters, so the
// withheld rows never arrive — an absent `view` parameter is "all".
export type ViewSelection = "anomalous" | "nominal" | "all";

// How many rows of each collection the selected view withheld. The screen
// cannot count rows it never received, so op-004's "+n nominal hidden" footer
// reads this and never the payload.
export interface SuppressedCounts {
  rfSensors: number;
  aircraftTracks: number;
  timelineEvents: number;
  interferenceZones: number;
}

// `examined` is false exactly when detectionSummary is null. On an unexamined
// hour nothing is anomalous and nothing is nominal, so withheld rows there are
// not an hour found clean — this is what lets a reader of the counts tell.
export interface PictureView {
  selected: ViewSelection;
  examined: boolean;
  suppressed: SuppressedCounts;
}

// One hour the Operational Picture will serve (api-013). The list of these is
// what the hour selector offers, and it is deliberately thin.
//
// There is no scenario type, and that absence is the item: the same string is
// correct on Scenario Control — the harness's own face, which exists to show
// what was generated — and is the answer key here. A shape that cannot hold it
// cannot leak it, which is stronger than a rule about not rendering it.
//
// There is also nothing the detectors concluded: no finding count, no severity.
// Not because a conclusion is secret — it is served in full for the hour
// actually selected — but because on this corpus the detectors are right
// essentially every time, so ranking hours by what was found would rank them by
// what was staged, and un-blind any later exercise in which a person reads this
// screen.
//
// `examined` is a different kind of fact and is carried: whether anybody looked,
// which no count can answer (api-012).
//
// The window is the replayed hour in simulated time, and is null for a run whose
// record holds none — a replay. It is never the wall-clock time the run was
// generated, which for the corpus is four years later than the hour it replays.
export interface SelectableHour {
  runId: number;
  observedFrom: string | null;
  observedTo: string | null;
  examined: boolean;
}

// Aircraft positions across one span of one run, for playback (api-008). The
// screen asks for at most 300 s at a time and buffers ahead of its cursor, so
// the request rate is not the frame rate (FR-718). `id` and `name` are the
// picture's own, so a playback track joins the picture's track on `id`.
//
// `gaps` is the stored continuity gaps overlapping the span, oldest first, and
// is null on an hour no pass examined: an empty list means looked and found
// none, which nobody did.
export interface PlaybackPosition {
  time: string;
  lat: number;
  lon: number;
  altitudeFt: number | null;
}

export interface PlaybackGap {
  startedAt: string;
  endedAt: string;
}

export interface PlaybackAircraft {
  id: string;
  name: string;
  state: TrackState;
  positions: PlaybackPosition[];
  gaps: PlaybackGap[] | null;
}

// The span served is exactly the one asked for, never shortened; the recorded
// window is the run's first and last position, null when it holds none.
export interface PlaybackWindow {
  runId: number;
  recordedFrom: string | null;
  recordedTo: string | null;
  servedFrom: string;
  servedTo: string;
  view: ViewSelection;
  examined: boolean;
  withheld: number;
  aircraft: PlaybackAircraft[];
}

// Receiver states through one run, for playback (api-018): per receiver in the
// layout, the stretches of simulated time in which stored findings put it out
// of nominal. The worst state wins where findings overlap, by the same ladder
// as the picture's whole-hour `health`, so the two agree on the worst moment.
// Intervals are closed, oldest first and never overlap; between them the
// receiver is nominal. `intervals` is null on an hour no pass examined, since
// an empty list would read as nominal throughout. Filtered by no view.
export type ReceiverOutOfNominal = "fault" | "deviating";

export interface ReceiverStateInterval {
  startedAt: string;
  endedAt: string;
  state: ReceiverOutOfNominal;
}

export interface ReceiverTimeline {
  id: string;
  intervals: ReceiverStateInterval[] | null;
}

export interface ReceiverStates {
  runId: number;
  examined: boolean;
  receivers: ReceiverTimeline[];
}
