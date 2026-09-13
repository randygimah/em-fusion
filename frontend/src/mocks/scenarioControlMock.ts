// Mock for the Scenario Control screen (spec: scn-004).
//
// Deliberately untyped for now: the contract file `types/scenarioControl.ts`
// is what the parity tests in `backend/tests/test_scn_control_contract.py`
// check, so writing it at the test stage would make those tests green before
// any implementation existed. The mock is typed against the contract when the
// contract lands.
//
// The values are real. Seeds, windows and parameters come from the batch
// `make generate` produced on 2026-09-12 from base seed 20220627 over the
// recorded hour of 27 June 2022 — run 0 (seed 1412224799, window 12:25:04),
// run 4 (939060571, 12:28:16), run 15 (993559346, 12:00:16) and run 19
// (1253435964, 12:32:16). `parameters` is the flat record the run row holds,
// key for key.
const scenarioControlMock = {
  library: [
    {
      id: "normal-baseline",
      name: "Normal baseline",
      description: "Real replayed traffic and a quiet radio grid. Nothing staged; the false-positive control.",
    },
    {
      id: "gnss-degradation",
      name: "GNSS signal degradation",
      description: "A raised noise floor over a zone, with the aircraft inside it holding their last position.",
    },
    {
      id: "rf-sensor-fault",
      name: "RF sensor fault",
      description: "One receiver deviating while its neighbours stay nominal. The tracks are untouched.",
    },
    {
      id: "aircraft-coverage-gap",
      name: "Data-source coverage gap",
      description: "Aircraft inside a zone stop reporting, with no radio signature to explain it.",
    },
    {
      id: "ambiguous-mixed-evidence",
      name: "Ambiguous mixed evidence",
      description: "Both signatures at once, so the evidence supports more than one explanation.",
    },
  ],
  runs: [
    {
      id: 48,
      scenarioType: "aircraft-coverage-gap",
      seed: 1253435964,
      startedAt: "2026-09-13T09:47:03Z",
      completedAt: null,
      parameters: {
        nominal_power_dbm: -95,
        noise_sigma_db: 1.5,
        nominal_snr_db: 20,
        start_offset_s: 120,
        duration_s: 300,
        radius_km: 60,
        elevation_db: 8,
        spectral_extent: "narrowband",
        start: "2022-06-27T12:32:16+00:00",
        duration_seconds: 900,
      },
    },
    {
      id: 47,
      scenarioType: "gnss-degradation",
      seed: 1412224799,
      startedAt: "2026-09-13T09:46:11Z",
      completedAt: "2026-09-13T09:46:14Z",
      parameters: {
        nominal_power_dbm: -95,
        noise_sigma_db: 1.5,
        nominal_snr_db: 20,
        start_offset_s: 120,
        duration_s: 300,
        radius_km: 60,
        elevation_db: 8,
        spectral_extent: "narrowband",
        start: "2022-06-27T12:25:04+00:00",
        duration_seconds: 900,
      },
    },
    {
      id: 46,
      scenarioType: "normal-baseline",
      seed: 939060571,
      startedAt: "2026-09-13T09:45:58Z",
      completedAt: "2026-09-13T09:46:01Z",
      parameters: {
        nominal_power_dbm: -95,
        noise_sigma_db: 1.5,
        nominal_snr_db: 20,
        start_offset_s: 120,
        duration_s: 300,
        radius_km: 60,
        elevation_db: 8,
        spectral_extent: "narrowband",
        start: "2022-06-27T12:28:16+00:00",
        duration_seconds: 900,
      },
    },
    {
      id: 45,
      scenarioType: "rf-sensor-fault",
      seed: 993559346,
      startedAt: "2026-09-13T09:45:44Z",
      completedAt: "2026-09-13T09:45:47Z",
      parameters: {
        nominal_power_dbm: -95,
        noise_sigma_db: 1.5,
        nominal_snr_db: 20,
        start_offset_s: 120,
        duration_s: 300,
        radius_km: 60,
        elevation_db: 8,
        spectral_extent: "broadband",
        start: "2022-06-27T12:00:16+00:00",
        duration_seconds: 900,
      },
    },
  ],
};

export default scenarioControlMock;
