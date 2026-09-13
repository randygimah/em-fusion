import type { OperationalPicture } from "../types/operationalPicture";
import type { ScenarioConfiguration, ScenarioRunRecord } from "../types/scenarioControl";

/**
 * The only module in the frontend that reaches the network. spec: api-003.
 *
 * Everything else — screens, hooks, App — takes data as a value. That is what
 * makes changing the endpoint a one-file change, and it is asserted rather than
 * intended: a test scans the source for a second caller.
 *
 * The path is relative, so the same build works in development behind Vite's
 * proxy and in the container behind nginx. The backend owns the `/api/v1`
 * prefix, so nothing here rewrites it.
 */
export const OPERATIONAL_PICTURE_PATH = "/api/v1/operational-picture";

/**
 * Five seconds, chosen by hand rather than tuned (NFR-503).
 *
 * The endpoint answers in about 0.4 s warm. An interval shorter than the
 * response time produces overlapping requests rather than fresher data, which
 * is the specific way a poll gets this wrong; five seconds leaves an order of
 * magnitude of headroom and is comfortably faster than a person reads a screen.
 */
export const DEFAULT_POLL_INTERVAL_MS = 5000;

/** Fetch the current picture, or throw. */
export const fetchOperationalPicture = async (
  baseUrl = "",
  signal?: AbortSignal,
): Promise<OperationalPicture> => {
  const response = await fetch(`${baseUrl}${OPERATIONAL_PICTURE_PATH}`, { signal });
  if (!response.ok) {
    // Thrown rather than returned as a value: every caller has to handle a
    // network failure anyway, so a second "but did it work" shape would be a
    // second thing to forget to check.
    throw new Error(`${OPERATIONAL_PICTURE_PATH} responded ${response.status}`);
  }
  return (await response.json()) as OperationalPicture;
};

// ---------------------------------------------------------------- scenario
//
// The scenario control calls. spec: api-010, api-006.
//
// They live here rather than in a module of their own because `api-003` made
// this the only place in the frontend that reaches the network, and
// `src/test/transport.test.ts` scans every other module's scrubbed source to
// keep it that way. A second caller is how changing an endpoint stops being a
// one-file change.

export const SCENARIO_RUNS_PATH = "/api/v1/scenario/runs";
export const SCENARIO_START_PATH = "/api/v1/scenario/start";

/** What the backend answers a start request with, before any run exists. */
export interface BatchAcceptance {
  /** The seed actually used — drawn by the backend when none was given. */
  baseSeed: number;
  runs: number;
  seeds: number[];
}

/** The runs the database holds, newest first, or throw. */
export const fetchScenarioRuns = async (
  baseUrl = "",
  signal?: AbortSignal,
): Promise<ScenarioRunRecord[]> => {
  const response = await fetch(`${baseUrl}${SCENARIO_RUNS_PATH}`, { signal });
  if (!response.ok) {
    throw new Error(`${SCENARIO_RUNS_PATH} responded ${response.status}`);
  }
  return (await response.json()) as ScenarioRunRecord[];
};

/**
 * Ask for a batch, and get back what was accepted rather than what was run.
 *
 * The backend answers 202 and runs the batch behind the response, so this
 * resolves in milliseconds while the runs themselves appear over the following
 * minute. A refusal — an unknown type, a batch outside the run bounds, an
 * incident beginning after its run ends — is a 422 and throws here.
 */
export const startScenarioBatch = async (
  configuration: ScenarioConfiguration,
  baseUrl = "",
): Promise<BatchAcceptance> => {
  const response = await fetch(`${baseUrl}${SCENARIO_START_PATH}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(configuration),
  });
  if (!response.ok) {
    throw new Error(`${SCENARIO_START_PATH} responded ${response.status}`);
  }
  return (await response.json()) as BatchAcceptance;
};
