// Types for the Scenario Control screen (spec: scn-004).
//
// This file mirrors two endpoints that do not exist yet — GET
// /api/v1/scenario/runs and POST /api/v1/scenario/start (api-006) — the way
// operationalPicture.ts mirrored api-002 before it was built. What keeps that
// from being guesswork is `backend/tests/test_scn_control_contract.py`, which
// parses this file and compares four of its shapes against the generator
// itself: the configuration against the batch entrypoint's arguments and their
// defaults, the recorded parameters against what a run row holds, a listed run
// against the run summary, and the type ids against the scenario enum.

// The five, and only five (FR-202). Spectral extent is a parameter of two of
// them rather than a sixth type, which is what keeps a narrowband-versus-
// broadband comparison inside one type instead of across two.
export type ScenarioTypeId = "normal-baseline" | "gnss-degradation" | "rf-sensor-fault" | "aircraft-coverage-gap" | "ambiguous-mixed-evidence";

export type SpectralExtent = "narrowband" | "broadband";

export interface ScenarioLibraryEntry {
  id: ScenarioTypeId;
  name: string;
  description: string;
}

// What the configuration form submits: exactly the dials the batch entrypoint
// accepts, and nothing else. A control the generator has no input for would be
// a control that changes nothing, which is the same defect as a seed that
// changes nothing (scn-001's fourth failure case).
//
// `baseSeed` is nullable because the harness may choose one. The screen never
// invents it: a seed the run record never saw is a run nobody can repeat.
export interface ScenarioConfiguration {
  scenarioType: ScenarioTypeId;
  baseSeed: number | null;
  runs: number;
  durationSeconds: number;
  incidentOffsetS: number;
  incidentDurationS: number;
  radiusKm: number;
  elevationDb: number;
  spectralExtent: SpectralExtent;
}

// The generator's own defaults, compared value for value against its argument
// parser. Names matching is not enough: a form defaulting to values the batch
// would refuse sends the analyst to an error rather than to a run.
export const DEFAULT_CONFIGURATION: ScenarioConfiguration = {
  scenarioType: "normal-baseline",
  baseSeed: null,
  runs: 20,
  durationSeconds: 900,
  incidentOffsetS: 120,
  incidentDurationS: 300,
  radiusKm: 60,
  elevationDb: 8,
  spectralExtent: "narrowband",
};

// The widest value a run's seed can hold. The column is a 32-bit signed
// integer, and a seed that does not round-trip through the run record is a run
// that cannot be reproduced from it.
export const SEED_MAX = 2 ** 31 - 1;

// What a run row records, verbatim — key for key, snake_case included.
//
// Served as stored rather than re-keyed to the camelCase the rest of this
// contract uses, because the backend rebuilds a run from exactly these names
// and refuses a parameter set carrying one it does not know. A conversion that
// dropped or renamed a field would turn a replayable run into an unreplayable
// one at the point furthest from the mistake.
//
// It is not the same shape as the configuration above and is not meant to be:
// it carries the baseline values and the derived window, neither of which is a
// dial, and it carries no batch count, because a recorded run is one run.
export interface RecordedParameters {
  nominal_power_dbm: number;
  noise_sigma_db: number;
  nominal_snr_db: number;
  start_offset_s: number;
  duration_s: number;
  radius_km: number;
  elevation_db: number;
  spectral_extent: SpectralExtent;
  start: string;
  duration_seconds: number;
}

// One row of the recent-runs table.
//
// `completedAt` is null when the run is not known to have finished, which
// covers a run still going and a run that died. The row cannot tell them
// apart, so neither may the screen (db-007).
//
// There is no field for ground truth, and that is the point: api-009 keeps the
// answer key off anything a detector or an analyst can read, and a shape that
// cannot hold it cannot leak it.
export interface ScenarioRunRecord {
  id: number;
  scenarioType: ScenarioTypeId;
  seed: number;
  startedAt: string;
  completedAt: string | null;
  parameters: RecordedParameters;
}

export interface ScenarioControl {
  library: ScenarioLibraryEntry[];
  runs: ScenarioRunRecord[];
}
