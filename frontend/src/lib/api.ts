import type { EvidenceAccount } from "../types/evidence";
import type { OperationalPicture, SelectableHour, ViewSelection } from "../types/operationalPicture";
import type { InFlightBatch, ScenarioConfiguration, ScenarioRunRecord } from "../types/scenarioControl";

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
 * The hours the picture will serve. spec: api-013.
 *
 * A separate endpoint from the picture rather than a parameter on it, because
 * it answers a different question and is read at a different rate — the picture
 * is polled, and this changes only when a batch completes.
 *
 * Deliberately NOT `SCENARIO_RUNS_PATH` below, which serves a near-identical
 * list and carries each run's scenario type. That is correct there: Scenario
 * Control is the harness's own face. On the analyst's screen it is the answer
 * key, and this screen reaching for it is the defect api-012 found in that
 * screen's heading after a year.
 */
export const SELECTABLE_HOURS_PATH = "/api/v1/operational-picture/hours";

/**
 * Five seconds, chosen by hand rather than tuned (NFR-503).
 *
 * The endpoint answers in about 0.4 s warm. An interval shorter than the
 * response time produces overlapping requests rather than fresher data, which
 * is the specific way a poll gets this wrong; five seconds leaves an order of
 * magnitude of headroom and is comfortably faster than a person reads a screen.
 */
export const DEFAULT_POLL_INTERVAL_MS = 5000;

export const SYSTEM_HEALTH_PATH = "/api/v1/health";

/**
 * Fifteen seconds, and deliberately not the picture's five. spec: nav-002.
 *
 * What this reports changes only when somebody applies a migration or the
 * database goes away. And `ops-005` reads the database's revision on **every
 * probe** by design, so that a migration run against a live stack clears the
 * refusal on the next one rather than after a restart — which means the
 * picture's cadence here would be a database round trip every five seconds per
 * open screen, for a value that cannot change that fast.
 */
export const SYSTEM_HEALTH_INTERVAL_MS = 15000;

/** What the health route answers with, of which the strip reads two fields. */
export interface SystemHealthBody {
  status: string;
  schema: string;
}

/**
 * Ask the service about itself. spec: nav-002, ops-005.
 *
 * **It does not throw on a non-2xx**, which is the one place in this module
 * that differs from every other fetcher, and the difference is the item. A 503
 * from this route means the request *arrived* and the backend could not vouch
 * for itself — so it is an answer and not a failure, and treating it as a
 * failure would report a misconfigured deployment as a lost connection. That is
 * the conflation `ops-005` removed, and the state that cost a day of the main
 * screen returning 500 while the container called itself healthy.
 *
 * It throws only when the request itself fails, and returns **null** when the
 * body does not carry the two fields the strip reads — so a renamed key
 * degrades to a visible failure rather than to a plausible verdict.
 */
export const fetchSystemHealth = async (
  baseUrl = "",
  signal?: AbortSignal,
): Promise<SystemHealthBody | null> => {
  const response = await fetch(`${baseUrl}${SYSTEM_HEALTH_PATH}`, { signal });
  const body = (await response.json()) as Partial<SystemHealthBody>;
  if (typeof body?.status !== "string" || typeof body?.schema !== "string") return null;
  return { status: body.status, schema: body.schema };
};

/**
 * Fetch one hour's picture, or throw.
 *
 * `runId` of null asks for the newest completed hour, which is what the endpoint
 * does with no parameter — so following the newest and pinning an hour are one
 * code path with one argument, rather than two call sites that can diverge
 * (spec: api-013). `view` is the filter the server applies (api-007, op-007).
 */
export const fetchOperationalPicture = async (
  baseUrl = "",
  runId: number | null = null,
  view: ViewSelection = "all",
  signal?: AbortSignal,
): Promise<OperationalPicture> => {
  // The view is always sent, never left to the server's default (op-007): the
  // screen asks for what its control says, and a request that omitted it would
  // be served `all` under a control reading Anomalous only.
  const params = new URLSearchParams();
  if (runId !== null) params.set("run", String(runId));
  params.set("view", view);
  const response = await fetch(`${baseUrl}${OPERATIONAL_PICTURE_PATH}?${params}`, { signal });
  if (!response.ok) {
    // Thrown rather than returned as a value: every caller has to handle a
    // network failure anyway, so a second "but did it work" shape would be a
    // second thing to forget to check.
    throw new Error(`${OPERATIONAL_PICTURE_PATH} responded ${response.status}`);
  }
  return (await response.json()) as OperationalPicture;
};

/**
 * The hours that may be asked for, newest first, or throw. spec: api-013.
 *
 * A response that is not a list is treated as a failure rather than rendered.
 * The only things it can be are another endpoint's answer or an error body, and
 * mapping over either puts a crash on the screen in place of a selector.
 */
export const fetchSelectableHours = async (baseUrl = "", signal?: AbortSignal): Promise<SelectableHour[]> => {
  const response = await fetch(`${baseUrl}${SELECTABLE_HOURS_PATH}`, { signal });
  if (!response.ok) {
    throw new Error(`${SELECTABLE_HOURS_PATH} responded ${response.status}`);
  }
  const payload = await response.json();
  if (!Array.isArray(payload)) {
    throw new Error(`${SELECTABLE_HOURS_PATH} answered something that is not a list`);
  }
  return payload as SelectableHour[];
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

// ---------------------------------------------------------------- evidence
//
// Why this hour's conclusions were reached. spec: api-015, op-010.

export const EVIDENCE_PATH = "/api/v1/operational-picture/evidence";

/**
 * The evidence account for one hour, or throw.
 *
 * **`null` is an answer and not a failure.** The endpoint serves it when no
 * detection pass has examined the hour, which is `api-012`'s distinction: the
 * presence of the account is what says a detector looked, never a number in
 * it. So this returns `null` and the caller tells it apart from a thrown
 * error — the panel says a different sentence for each.
 *
 * With no run the endpoint serves the hour the picture serves with no run, so
 * the two cannot disagree about which hour is current.
 */
export const fetchEvidenceAccount = async (
  runId: number | null = null,
  baseUrl = "",
  signal?: AbortSignal,
): Promise<EvidenceAccount | null> => {
  const query = runId === null ? "" : `?run=${encodeURIComponent(runId)}`;
  const response = await fetch(`${baseUrl}${EVIDENCE_PATH}${query}`, { signal });
  if (!response.ok) {
    throw new Error(`${EVIDENCE_PATH} responded ${response.status}`);
  }
  const payload = await response.json();
  // `fetchSelectableHours`'s rule, and it earned itself here: a body that is
  // neither null nor an account is another endpoint's answer or an error body,
  // and cast blindly it reaches the panel as an object whose lists are
  // `undefined` — which crashes the render instead of saying it could not load.
  // Found by this item's own tests, through four OTHER suites whose fetch mocks
  // answer every url with a picture payload.
  if (payload !== null && !isAccount(payload)) {
    throw new Error(`${EVIDENCE_PATH} answered something that is not an account`);
  }
  return payload as EvidenceAccount | null;
};

const isAccount = (payload: unknown): boolean =>
  typeof payload === "object" &&
  payload !== null &&
  ["explained", "unexplained", "unclaimed"].every((list) =>
    Array.isArray((payload as Record<string, unknown>)[list]),
  );

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
export const fetchScenarioRuns = async (baseUrl = "", signal?: AbortSignal): Promise<ScenarioRunRecord[]> => {
  const response = await fetch(`${baseUrl}${SCENARIO_RUNS_PATH}`, { signal });
  if (!response.ok) {
    throw new Error(`${SCENARIO_RUNS_PATH} responded ${response.status}`);
  }
  return (await response.json()) as ScenarioRunRecord[];
};

/**
 * A start refused because one batch is already running. spec: api-011.
 *
 * A distinct type rather than a status code on a generic error, because the
 * screen has to say something different about it: this refusal is temporary and
 * clears itself when the running batch finishes, where a rejected configuration
 * changes nothing until the analyst changes something. The message here is for a
 * developer reading a stack trace; the analyst's sentence is composed on screen
 * out of `inFlight`.
 */
export class BatchAlreadyRunningError extends Error {
  readonly inFlight: InFlightBatch;

  constructor(inFlight: InFlightBatch) {
    super(
      `${SCENARIO_START_PATH} responded 409: a ${inFlight.scenarioType} batch from base seed ${inFlight.baseSeed} has been running since ${inFlight.startedAt}`,
    );
    this.name = "BatchAlreadyRunningError";
    this.inFlight = inFlight;
  }
}

/**
 * Ask for a batch, and get back what was accepted rather than what was run.
 *
 * The backend answers 202 and runs the batch behind the response, so this
 * resolves in milliseconds while the runs themselves appear over the following
 * minute. A refusal — an unknown type, a batch outside the run bounds, an
 * incident beginning after its run ends — is a 422 and throws here.
 */
export const startScenarioBatch = async (configuration: ScenarioConfiguration, baseUrl = ""): Promise<BatchAcceptance> => {
  const response = await fetch(`${baseUrl}${SCENARIO_START_PATH}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(configuration),
  });
  if (response.status === 409) {
    // The only refusal whose body is read. A 409 carries what is already in
    // flight, and discarding it would leave the screen with nothing to name —
    // which is the defect that prompted the item, wearing a status code.
    const body = (await response.json()) as { detail: InFlightBatch };
    throw new BatchAlreadyRunningError(body.detail);
  }
  if (!response.ok) {
    throw new Error(`${SCENARIO_START_PATH} responded ${response.status}`);
  }
  return (await response.json()) as BatchAcceptance;
};
