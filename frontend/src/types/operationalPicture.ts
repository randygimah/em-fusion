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

// null means no detector has run, which is not the same as a low reading.
export interface DetectionSummary {
  anomalyLevel: Level | null;
  signalIntegrity: Level | null;
}

export interface RFSensor {
  id: string;
  stationName: string;
  signalId: string;
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
  detectionSummary: DetectionSummary;
  rfSensors: RFSensor[];
  aircraftTracks: AircraftTrack[];
  timelineEvents: TimelineEvent[];
}
