import type { OperationalPicture } from "../types/operationalPicture";

const operationalPicture: OperationalPicture = {
  scenario: {
    id: "scenario-001",
    name: "GNSS Sector A",
    dataMode: "Synthetic RF + Open Data Replay",
  },
  // Empty on purpose (api-019): this is the first-paint fallback, and a card
  // here showed an analyst an explanation that does not exist until the first
  // poll replaced it (qa.md 162).
  hypotheses: [],
  unexplainedConclusions: 0,
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
      state: "nominal",
    },
  ],
  // Corrected with op-006, which is the first item to render these. Both
  // fields were unfaithful to the payload api-012 actually produces: `event`
  // held the prose "Anomaly Detected" where the real field carries a finding
  // type verbatim, and `source` held a station name where the real field
  // carries a receiver id. A fixture that does not match its payload is how a
  // screen gets built against a shape nothing serves.
  timelineEvents: [
    {
      id: "FUSION-SPATIAL:sensor-001:2024-06-01T12:00:00Z",
      time: "2024-06-01T12:00:00Z",
      event: "possible_interference_zone",
      source: "sensor-001",
    },
  ],
  // The interference claim above, placed (api-017): same id as its event.
  interferenceZones: [
    {
      id: "FUSION-SPATIAL:sensor-001:2024-06-01T12:00:00Z",
      centre: { lat: 34.0522, lon: -118.2437 },
      radiusKm: 60,
      receivers: ["sensor-001"],
      startedAt: "2024-06-01T12:00:00Z",
      endedAt: "2024-06-01T12:05:00Z",
      confidence: "Medium",
      corroboration: "not_measurable",
    },
  ],
  // What the server sends when no view is asked for (api-007): everything,
  // nothing withheld. Examined, because the summary above is a reading.
  view: {
    selected: "all",
    examined: true,
    suppressed: { rfSensors: 0, aircraftTracks: 0, timelineEvents: 0, interferenceZones: 0 },
  },
};
export default operationalPicture;
