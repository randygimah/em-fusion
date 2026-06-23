//Types for operational picture data
export interface Scenario {
  id: string;
  name: string;
  dataMode: string;
  health: string;
}

export interface Hypothesis {
  id: string;
  title: string;
  confidence: string;
  severity: string;
  status: "new" | "under_review" | "reviewed";
  evidence: string;
}

export interface DetectionSummary {
  anomalyScore: number;
  signalIntegrity: number;
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
  altitudeFt: number;
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
  scenario: Scenario;
  hypotheses: Hypothesis[];
  detectionSummary: DetectionSummary;
  rfSensors: RFSensor[];
  aircraftTracks: AircraftTrack[];
  timelineEvents: TimelineEvent[];
}
