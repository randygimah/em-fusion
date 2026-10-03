import type { OperationalPicture } from "../types/operationalPicture";

const operationalPicture: OperationalPicture = {
  scenario: {
    id: "scenario-001",
    name: "GNSS Sector A",
    dataMode: "Synthetic RF + Open Data Replay",
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
    counts: [
      {
        ruleId: "SENSOR-FAULT",
        findingType: "possible_sensor_fault",
        kind: "reportable",
        count: 0,
        unavailable: null,
      },
      {
        ruleId: "FUSION-SPATIAL",
        findingType: "possible_interference_zone",
        kind: "reportable",
        count: 1,
        unavailable: null,
      },
      {
        ruleId: "SOURCE-GAP",
        findingType: "possible_data_source_issue",
        kind: "reportable",
        count: null,
        unavailable: "rule-not-built",
      },
      {
        ruleId: "RF-NOISE",
        findingType: "rf_noise_deviation",
        kind: "intermediate",
        count: 12,
        unavailable: null,
      },
    ],
  },
  rfSensors: [
    {
      id: "sensor-001",
      stationName: "Station Gamma",
      signalId: "GNSS-L1",
      health: "deviating",
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
