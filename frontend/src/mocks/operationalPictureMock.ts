import type { OperationalPicture } from "../types/operationalPicture";

const operationalPicture: OperationalPicture = {
  scenario: {
    id: "scenario-001",
    name: "GNSS Sector A",
    dataMode: "Synthetic RF + Open Data Replay",
    health: "Healthy",
  },
  hypotheses: [
    {
      id: "hypothesis-001",
      title: "Possible localised GNSS degradation / interference",
      confidence: "Medium",
      severity: "High",
      status: "under_review",
      evidence: "3 Synthetic Sources",
    },
  ],
  detectionSummary: {
    anomalyLevel: "High",
    signalIntegrity: "Medium",
  },
  rfSensors: [
    {
      id: "sensor-001",
      stationName: "Station Gamma",
      signalId: "AZ-402",
      health: "healthy",
      lat: 34.0522,
      lon: -118.2437,
    },
  ],
  aircraftTracks: [
    {
      id: "track-001",
      name: "DLH420",
      altitudeFt: 30000,
      lat: 34.0522,
      lon: -118.2437,
    },
  ],
  timelineEvents: [
    {
      id: "event-001",
      time: "2024-06-01T12:00:00Z",
      event: "Anomaly Detected",
      source: "Station Gamma",
    },
  ],
};
export default operationalPicture;
